// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! `glv` — check GroundLens records without Python.
//!
//! A single static binary for whoever has to trust the records and does not
//! run the application: an auditor, a second team, a CI job. It verifies
//! answer records and run records offline and shows the policy a record
//! names, with its hash. It produces nothing; the `groundlens` command in
//! the Python package does.
//!
//! ```text
//! glv record verify records.jsonl [more.jsonl | records/ ...]
//! glv run check runs.jsonl
//! glv policy lint p.yaml
//! glv policy show p.yaml --resolved
//! ```

use clap::{Parser, Subcommand};
use gl_policy::Policy;
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "glv", version, about = "Check GroundLens records offline")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Answer records.
    Record {
        #[command(subcommand)]
        cmd: RecordCmd,
    },
    /// Run records: whole agent executions.
    Run {
        #[command(subcommand)]
        cmd: RunCmd,
    },
    /// Policies.
    Policy {
        #[command(subcommand)]
        cmd: PolicyCmd,
    },
}

#[derive(Subcommand)]
enum RunCmd {
    /// Verify a run-record JSON Lines log: every record and every link.
    Check { path: PathBuf },
}

#[derive(Subcommand)]
enum PolicyCmd {
    /// Check a policy: schema, extends, rounding rule.
    Lint {
        /// A policy file, or the id of a shipped policy.
        policy: String,
    },
    /// Print a policy. With --resolved: `extends` merged in and every
    /// default written out, headed by the hash that goes into records.
    Show {
        /// A policy file, or the id of a shipped policy.
        policy: String,
        #[arg(long)]
        resolved: bool,
    },
}

#[derive(Subcommand)]
enum RecordCmd {
    /// Verify one or more chains: every hash, link and signature. Each file
    /// is one chain; a directory means every `.jsonl` file in it.
    Verify {
        #[arg(required = true)]
        paths: Vec<PathBuf>,
    },
}

fn read(path: &PathBuf) -> Result<String> {
    std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()).into())
}

/// A policy argument: a file, or the id of a shipped policy.
fn read_policy(arg: &str) -> Result<String> {
    let path = PathBuf::from(arg);
    if path.is_file() {
        return read(&path);
    }
    match gl_policy::builtin(arg) {
        Some(text) => Ok(text.to_string()),
        None => Err(format!("{arg}: no such file, and not a shipped policy").into()),
    }
}

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

fn main() {
    if let Err(e) = run() {
        eprintln!("glv: {e}");
        std::process::exit(2);
    }
}

fn run() -> Result<()> {
    match Cli::parse().command {
        Command::Policy { cmd: PolicyCmd::Lint { policy } } => {
            let text = read_policy(&policy)?;
            let (hash, problems) = gl_engine::policy_lint(&text)?;
            let policy = Policy::from_yaml(&text)?;
            if problems.is_empty() {
                println!("ok  {} v{}  {}", policy.id, policy.version, hash);
            } else {
                for p in problems {
                    println!("problem  {p}");
                }
                std::process::exit(1);
            }
        }
        Command::Policy { cmd: PolicyCmd::Show { policy, resolved } } => {
            let text = read_policy(&policy)?;
            if resolved {
                print!("{}", gl_engine::policy_resolve(&text)?);
            } else {
                print!("{text}");
            }
        }
        Command::Record { cmd: RecordCmd::Verify { paths } } => {
            let mut files = Vec::new();
            for p in paths {
                if p.is_dir() {
                    let mut inside: Vec<PathBuf> = std::fs::read_dir(&p)?
                        .filter_map(|e| e.ok().map(|e| e.path()))
                        .filter(|f| f.extension().is_some_and(|x| x == "jsonl"))
                        .collect();
                    inside.sort();
                    files.extend(inside);
                } else {
                    files.push(p);
                }
            }
            if files.is_empty() {
                return Err("no .jsonl files to verify".into());
            }
            let mut chains = Vec::new();
            for f in &files {
                chains.push(gl_record::from_jsonl(&read(f)?)?);
            }
            let n = gl_record::verify_chains(&chains)?;
            if chains.len() == 1 {
                println!("ok  {n} records, chain intact, all signatures verify");
            } else {
                println!(
                    "ok  {n} records in {} chains, every chain intact, all signatures verify",
                    chains.len()
                );
            }
        }
        Command::Run { cmd: RunCmd::Check { path } } => {
            let records = gl_record::run_records_from_jsonl(&read(&path)?)?;
            gl_record::verify_run_chain(&records)?;
            println!("ok  {} run records, chain intact, all signatures verify", records.len());
        }
    }
    Ok(())
}
