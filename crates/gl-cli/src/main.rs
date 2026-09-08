//! `glv` — deterministic AI response verification, from the shell.
//!
//! ```text
//! glv verify --answer a.txt --source invoice.pdf#p1=invoice.txt --policy p.yaml [--rules r.yaml] [--question q.txt] [--log records.jsonl]
//! glv policy lint p.yaml
//! glv record verify records.jsonl
//! glv bundle build ./bundle --name acme-verification --version 1.0.0
//! glv bundle verify ./bundle
//! glv keygen > signer.key
//! ```

use clap::{Parser, Subcommand};
use gl_core::{Source, Verifier};
use gl_engine::VerifyRequest;
use gl_policy::Policy;
use gl_record::RecordSigner;
use gl_verifiers::NumericVerifier;
use std::io::Write;
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "glv", version, about = "GroundLens: the verification and evidence layer for AI")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Verify an answer against its sources under a policy.
    Verify {
        #[arg(long)]
        answer: PathBuf,
        /// `id=path`, repeatable.
        #[arg(long = "source")]
        sources: Vec<String>,
        #[arg(long)]
        question: Option<PathBuf>,
        #[arg(long)]
        policy: PathBuf,
        /// Rule set, YAML or JSON. Repeatable.
        #[arg(long = "rules")]
        rules: Vec<PathBuf>,
        #[arg(long, default_value = "und")]
        locale: String,
        /// Append the signed record to this JSON Lines log.
        #[arg(long)]
        log: Option<PathBuf>,
        /// 32-byte hex Ed25519 seed. A fresh ephemeral key is used if absent.
        #[arg(long, env = "GLV_SIGNING_KEY")]
        signing_key: Option<String>,
        /// Bundle directory; its manifest hash goes into the record.
        #[arg(long)]
        bundle: Option<PathBuf>,
    },
    /// Policy tools.
    Policy {
        #[command(subcommand)]
        cmd: PolicyCmd,
    },
    /// Record tools.
    Record {
        #[command(subcommand)]
        cmd: RecordCmd,
    },
    /// Bundle tools.
    Bundle {
        #[command(subcommand)]
        cmd: BundleCmd,
    },
    /// Print a fresh Ed25519 signing seed (hex) to stdout.
    Keygen,
}

#[derive(Subcommand)]
enum PolicyCmd {
    Lint { path: PathBuf },
}

#[derive(Subcommand)]
enum RecordCmd {
    Verify { path: PathBuf },
}

#[derive(Subcommand)]
enum BundleCmd {
    Build {
        root: PathBuf,
        #[arg(long)]
        name: String,
        #[arg(long)]
        version: String,
    },
    Verify {
        root: PathBuf,
    },
}

fn read(path: &PathBuf) -> anyhow_lite::Result<String> {
    std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()).into())
}

mod anyhow_lite {
    pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
}

fn load_rules_json(path: &PathBuf) -> anyhow_lite::Result<String> {
    let text = read(path)?;
    if path.extension().is_some_and(|e| e == "yaml" || e == "yml") {
        let v: serde_yaml::Value = serde_yaml::from_str(&text)?;
        Ok(serde_json::to_string(&v)?)
    } else {
        Ok(text)
    }
}

fn main() {
    if let Err(e) = run() {
        eprintln!("glv: {e}");
        std::process::exit(2);
    }
}

fn run() -> anyhow_lite::Result<()> {
    match Cli::parse().command {
        Command::Verify { answer, sources, question, policy, rules, locale, log, signing_key, bundle } => {
            let mut srcs = Vec::new();
            for s in sources {
                let (id, path) = s.split_once('=').ok_or("--source expects id=path")?;
                srcs.push(Source { id: id.to_string(), text: read(&PathBuf::from(path))?, locator: None });
            }
            let mut req = VerifyRequest::new(read(&answer)?, srcs);
            req.question = question.map(|p| read(&p)).transpose()?;
            req.locale = locale;
            req.policy_yaml = read(&policy)?;
            for r in &rules {
                req.rule_sets_json.push(load_rules_json(r)?);
            }
            req.signing_key_hex = signing_key;
            req.bundle_hash = match bundle {
                Some(root) => Some(gl_bundle::Bundle::open(root)?.manifest_hash),
                None => None,
            };
            req.previous_record_hash = match &log {
                Some(p) if p.exists() => {
                    gl_record::from_jsonl(&read(p)?)?.last().map(|r| r.record_hash.clone())
                }
                _ => None,
            };
            let record = gl_engine::verify(&req)?;

            if let Some(p) = log {
                let mut f = std::fs::OpenOptions::new().create(true).append(true).open(&p)?;
                writeln!(f, "{}", gl_record::to_jsonl_line(&record)?)?;
            }
            println!("{}", serde_json::to_string_pretty(&record)?);
            match record.content.outcome.decision {
                gl_policy::Decision::Fail => std::process::exit(1),
                gl_policy::Decision::Review => std::process::exit(3),
                gl_policy::Decision::Pass => {}
            }
        }
        Command::Policy { cmd: PolicyCmd::Lint { path } } => {
            let policy = Policy::from_yaml(&read(&path)?)?;
            let known = [NumericVerifier::default().info().clone()];
            let problems = policy.lint(&known);
            if problems.is_empty() {
                println!("ok  {} v{}  {}", policy.id, policy.version, policy.hash()?);
            } else {
                for p in problems {
                    println!("problem  {p}");
                }
                std::process::exit(1);
            }
        }
        Command::Record { cmd: RecordCmd::Verify { path } } => {
            let records = gl_record::from_jsonl(&read(&path)?)?;
            gl_record::verify_chain(&records)?;
            println!("ok  {} records, chain intact, all signatures verify", records.len());
        }
        Command::Bundle { cmd: BundleCmd::Build { root, name, version } } => {
            let manifest = gl_bundle::build_manifest(&root, &name, &version, gl_core::ENGINE_VERSION)?;
            std::fs::write(root.join("manifest.json"), serde_json::to_string_pretty(&manifest)?)?;
            println!("ok  {} artefacts  {}", manifest.artefacts.len(), manifest.hash()?);
        }
        Command::Bundle { cmd: BundleCmd::Verify { root } } => {
            let b = gl_bundle::Bundle::open(&root)?;
            println!("ok  {} v{}  {}", b.manifest.name, b.manifest.version, b.manifest_hash);
        }
        Command::Keygen => {
            let signer = RecordSigner::generate();
            println!("{}", signer.seed_hex());
        }
    }
    Ok(())
}
