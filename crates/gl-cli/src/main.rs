// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

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
#[command(name = "glv", version, about = "Deterministic AI response verification")]
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
        /// A bundle directory or the name of an installed bundle. Default:
        /// the installed `base` bundle, if any.
        #[arg(long)]
        bundle: Option<String>,
        /// Skip the lexical channel even when a bundle is available.
        #[arg(long)]
        no_lexical: bool,
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
    /// Whether a named bundle is installed, where, and with which hash.
    Status {
        #[arg(default_value = "base")]
        name: String,
    },
    /// Download a published bundle and install it. The only command in glv
    /// that opens a network connection; the archive hash must match the
    /// value pinned in this build.
    Pull {
        #[arg(default_value = "base")]
        name: String,
        /// Install here instead of the per-user bundle directory.
        #[arg(long)]
        into: Option<PathBuf>,
        /// Accept a bundle this build has no pinned hash for (development).
        #[arg(long)]
        trust_unpinned: bool,
    },
}

fn read(path: &PathBuf) -> anyhow_lite::Result<String> {
    std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()).into())
}

mod anyhow_lite {
    pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
}

fn pull_bundle(
    name: &str,
    into: Option<PathBuf>,
    trust_unpinned: bool,
) -> Result<gl_bundle::Bundle, Box<dyn std::error::Error>> {
    use sha2::Digest;
    let known = gl_bundle::known(name).ok_or_else(|| format!("unknown bundle {name:?}"))?;
    let target = into.unwrap_or_else(|| gl_bundle::locate(name));
    eprintln!("fetching {}", known.url);
    let mut body = ureq::get(known.url).call()?.into_body().into_reader();
    let mut bytes = Vec::new();
    std::io::Read::read_to_end(&mut body, &mut bytes)?;
    let digest = format!("sha256:{}", hex::encode(sha2::Sha256::digest(&bytes)));
    if known.archive_sha256 == "sha256:unpinned" {
        if !trust_unpinned {
            return Err(format!(
                "this build has no pinned hash for bundle {name:?} (downloaded {digest}); refusing to install it. \
                 Pass --trust-unpinned only in development."
            )
            .into());
        }
    } else if digest != known.archive_sha256 {
        return Err(format!(
            "download hash {digest} does not match the pinned {}; not installed",
            known.archive_sha256
        )
        .into());
    }
    let staging = std::env::temp_dir().join(format!("glv-bundle-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&staging);
    std::fs::create_dir_all(&staging)?;
    let mut archive = tar::Archive::new(flate2::read::GzDecoder::new(std::io::Cursor::new(bytes)));
    for entry in archive.entries()? {
        let mut entry = entry?;
        let path = entry.path()?.to_path_buf();
        if path
            .components()
            .any(|c| matches!(c, std::path::Component::ParentDir | std::path::Component::RootDir))
        {
            return Err(format!("archive entry escapes the target directory: {}", path.display()).into());
        }
        if !entry.unpack_in(&staging)? {
            return Err(format!("refused to unpack {}", path.display()).into());
        }
    }
    let root = if staging.join("manifest.json").is_file() {
        staging.clone()
    } else {
        let dirs: Vec<PathBuf> = std::fs::read_dir(&staging)?
            .filter_map(|e| e.ok())
            .map(|e| e.path())
            .filter(|p| p.is_dir())
            .collect();
        match dirs.as_slice() {
            [one] if one.join("manifest.json").is_file() => one.clone(),
            _ => return Err("archive has no manifest.json at its top level".into()),
        }
    };
    if target.exists() {
        std::fs::remove_dir_all(&target)?;
    }
    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent)?;
    }
    if std::fs::rename(&root, &target).is_err() {
        copy_dir(&root, &target)?;
    }
    let _ = std::fs::remove_dir_all(&staging);
    Ok(gl_bundle::Bundle::open(&target)?)
}

fn copy_dir(from: &std::path::Path, to: &std::path::Path) -> std::io::Result<()> {
    std::fs::create_dir_all(to)?;
    for entry in std::fs::read_dir(from)? {
        let entry = entry?;
        let dest = to.join(entry.file_name());
        if entry.path().is_dir() {
            copy_dir(&entry.path(), &dest)?;
        } else {
            std::fs::copy(entry.path(), dest)?;
        }
    }
    Ok(())
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
        Command::Verify {
            answer,
            sources,
            question,
            policy,
            rules,
            locale,
            log,
            signing_key,
            bundle,
            no_lexical,
        } => {
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
            req.bundle = bundle;
            req.lexical = !no_lexical;
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
        Command::Bundle { cmd: BundleCmd::Status { name } } => {
            let s = gl_engine::bundle::status(&name);
            if s.installed {
                println!(
                    "ok  {} v{}  {}  {}",
                    s.name,
                    s.version.unwrap_or_default(),
                    s.manifest_hash.unwrap_or_default(),
                    s.path
                );
            } else {
                println!("not installed  {}  (would go to {})", s.name, s.path);
                if !s.url.is_empty() {
                    println!("    glv bundle pull {}   ← {}", s.name, s.url);
                }
            }
        }
        Command::Bundle { cmd: BundleCmd::Pull { name, into, trust_unpinned } } => {
            let b = pull_bundle(&name, into, trust_unpinned)?;
            println!(
                "ok  {} v{}  {}  {}",
                b.manifest.name,
                b.manifest.version,
                b.manifest_hash,
                b.root.display()
            );
        }
        Command::Keygen => {
            let signer = RecordSigner::generate();
            println!("{}", signer.seed_hex());
        }
    }
    Ok(())
}
