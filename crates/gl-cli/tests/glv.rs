// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! `glv` checks records written by a released version, with nothing but the
//! binary: the job it exists for.

use std::path::PathBuf;
use std::process::Command;

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../gl-record/tests/fixtures/5.3.0")
}

fn glv(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_glv")).args(args).output().expect("glv runs")
}

#[test]
fn checks_answer_and_run_records_from_a_release() {
    let dir = fixtures();
    let answers = glv(&["record", "verify", dir.join("answer-records.jsonl").to_str().unwrap()]);
    assert!(answers.status.success(), "{}", String::from_utf8_lossy(&answers.stderr));
    let runs = glv(&["run", "check", dir.join("run-records.jsonl").to_str().unwrap()]);
    assert!(runs.status.success(), "{}", String::from_utf8_lossy(&runs.stderr));
}

#[test]
fn shows_a_shipped_policy_with_its_hash() {
    let out = glv(&["policy", "show", "eu_ai_act_high_risk_v1", "--resolved"]);
    assert!(out.status.success());
    let text = String::from_utf8(out.stdout).unwrap();
    assert!(text.starts_with("# eu_ai_act_high_risk_v1 v1.4.0\n# hash: sha256:"), "{text}");
}

#[test]
fn a_tampered_record_fails() {
    let text = std::fs::read_to_string(fixtures().join("answer-records.jsonl")).unwrap();
    let tampered = text.replacen("\"decision\":\"FAIL\"", "\"decision\":\"PASS\"", 1);
    assert_ne!(text, tampered, "the fixture has a FAIL to tamper with");
    let path = std::env::temp_dir().join(format!("glv-tampered-{}.jsonl", std::process::id()));
    std::fs::write(&path, tampered).unwrap();
    let out = glv(&["record", "verify", path.to_str().unwrap()]);
    let _ = std::fs::remove_file(&path);
    assert_eq!(out.status.code(), Some(2));
}
