// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! `semantic.cosine` runs end to end through the engine whenever the loaded
//! bundle carries an encoder. It shares that encoder with the lexical channel,
//! so the tiny test bundle (encoder only, no NLI model) is enough to exercise
//! the whole path: bundle load, encoder build, statement claim extraction, the
//! verifier, and the sealed record.

use gl_engine::gl_core::Source;
use gl_engine::{verify, VerifyRequest};

fn tiny_bundle() -> String {
    concat!(env!("CARGO_MANIFEST_DIR"), "/../gl-onnx/testdata/tiny-bundle").to_string()
}

const POLICY: &str = r#"id: semantic_demo
version: 1.0.0
verifiers:
  required: [groundlens.numeric]
  optional: [groundlens.lexical, semantic.cosine]
decision:
  any_contradiction_from: [groundlens.numeric]
  unresolved_claims: REVIEW
  tolerate_unresolved_kinds: [word, statement]
"#;

#[test]
fn semantic_runs_end_to_end_from_a_bundle_and_is_hashed_into_the_record() {
    let mut req = VerifyRequest::new(
        "The invoice total is 10,000 dollars.",
        vec![Source {
            id: "s".into(),
            text: "The total amount due is 10,000 dollars.".into(),
            locator: None,
        }],
    );
    req.policy_yaml = POLICY.into();
    req.bundle = Some(tiny_bundle());

    let record = verify(&req).unwrap();
    let ran: Vec<&str> = record.content.graph.evidence.iter().map(|e| e.verifier_id.as_str()).collect();
    assert!(ran.contains(&"semantic.cosine"), "semantic.cosine did not run; ran: {ran:?}");

    // The evidence names the exact encoder, carries a bounded score, and the
    // whole thing seals and verifies offline.
    let sem = record.content.graph.evidence.iter().find(|e| e.verifier_id == "semantic.cosine").unwrap();
    assert!(sem.model_hash.as_deref().unwrap_or("").starts_with("sha256:"));
    assert!((0.0..=1.0).contains(&sem.score.0));
    assert!(record.content.bundle_hash.starts_with("sha256:"));
    assert_ne!(record.content.bundle_hash, "sha256:unbundled");
    gl_engine::gl_record::verify_record(&record).unwrap();

    // Deterministic: the same input under the same bundle seals the same hash.
    assert_eq!(verify(&req).unwrap().content_hash, record.content_hash);
}
