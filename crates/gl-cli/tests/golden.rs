//! Determinism, checked rather than promised.
//!
//! The same input, policy and rule set must produce the same `content_hash`
//! on every OS and architecture CI runs on, and the same one that is
//! committed in `tests/golden/invoice.hash`. Change the golden file only in
//! a commit that explains why the finding changed.

use std::path::PathBuf;
use std::process::Command;

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap()
}

fn run_verify(with_question: bool) -> serde_json::Value {
    let root = repo_root();
    let mut cmd = Command::new(env!("CARGO_BIN_EXE_glv"));
    cmd.current_dir(&root)
        .arg("verify")
        .args(["--answer", "examples/invoice/answer.txt"])
        .args(["--source", "invoice.pdf#p1=examples/invoice/invoice.txt"])
        .args(["--policy", "policies/eu_ai_act_high_risk_v1.yaml"])
        .args(["--rules", "rules/es_banking_v1.yaml"])
        .args(["--locale", "en"]);
    if with_question {
        cmd.args(["--question", "examples/invoice/question.txt"]);
    }
    // Hostile environment on purpose: nothing here may leak into the output.
    cmd.env("LC_ALL", "tr_TR.UTF-8").env("LANG", "tr_TR.UTF-8").env("TZ", "Pacific/Kiritimati");
    let out = cmd.output().expect("glv runs");
    assert_eq!(
        out.status.code(),
        Some(1),
        "the invoice example must FAIL (exit 1): {}",
        String::from_utf8_lossy(&out.stderr)
    );
    serde_json::from_slice(&out.stdout).expect("json record")
}

#[test]
fn invoice_example_matches_committed_golden_hash() {
    let record = run_verify(true);
    let hash = record["content_hash"].as_str().unwrap();
    let golden_path = repo_root().join("crates/gl-cli/tests/golden/invoice.hash");
    let golden = std::fs::read_to_string(&golden_path).unwrap_or_default();
    assert_eq!(
        hash,
        golden.trim(),
        "content_hash drifted from the golden file. Decision was {}. If the change is intended, update {} in the same commit.",
        record["content"]["outcome"]["decision"],
        golden_path.display()
    );
    assert_eq!(record["content"]["outcome"]["decision"], "FAIL");
    assert_eq!(record["content"]["outcome"]["regulatory_mapping"][0]["article"], "Art. 15(1)");
}

#[test]
fn two_runs_are_identical_and_the_timestamp_stays_outside_the_content_hash() {
    let a = run_verify(false);
    let b = run_verify(false);
    assert_eq!(a["content_hash"], b["content_hash"]);
    assert_eq!(a["content"], b["content"]);
}
