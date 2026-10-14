// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Determinism, checked rather than promised.
//!
//! The same input, policy and rule set must produce the same `content_hash`
//! on every OS and architecture CI runs on, and the same one that is
//! committed in `tests/golden/invoice.hash`. Change the golden file only in
//! a commit that explains why the finding changed.

use gl_engine::{gl_core::Source, gl_policy::Decision, verify, VerifyRequest};
use std::path::PathBuf;

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap()
}

fn read(path: &str) -> String {
    std::fs::read_to_string(repo_root().join(path)).unwrap()
}

#[test]
fn invoice_example_matches_committed_golden_hash() {
    let mut req = VerifyRequest::new(
        read("examples/invoice/answer.txt"),
        vec![Source {
            id: "invoice.pdf#p1".into(),
            text: read("examples/invoice/invoice.txt"),
            locator: None,
            provenance: Default::default(),
        }],
    );
    req.question = Some(read("examples/invoice/question.txt"));
    req.policy_yaml = read("policies/eu_ai_act_high_risk_v1.yaml");
    let rules: serde_yaml::Value = serde_yaml::from_str(&read("rules/es_banking_v1.yaml")).unwrap();
    req.rule_sets_json.push(serde_json::to_string(&rules).unwrap());
    req.locale = "en".into();

    let record = verify(&req).unwrap();
    assert_eq!(record.content.outcome.decision, Decision::Fail, "the invoice example must FAIL");

    let golden_path = repo_root().join("crates/gl-engine/tests/golden/invoice.hash");
    let golden = std::fs::read_to_string(&golden_path).unwrap_or_default();
    assert_eq!(
        record.content_hash,
        golden.trim(),
        "content_hash drifted from the golden file. If the change is intended, update {} in the same commit.",
        golden_path.display()
    );
}
