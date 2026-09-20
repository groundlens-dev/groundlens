// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! `groundlens.nli` runs end to end through the engine when the loaded bundle
//! carries an entailment model. The bundle here is assembled from the tiny test
//! encoder and the tiny test NLI model, so the whole path exercises: bundle
//! load, entailment model build, statement claim extraction, the verifier, and
//! the sealed record.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use gl_engine::gl_bundle::{Artefact, EncoderSpec, EntailmentSpec, Manifest, MANIFEST_SCHEMA};
use gl_engine::gl_core::canonical::sha256_hex;
use gl_engine::gl_core::Source;
use gl_engine::{verify, VerifyRequest};

fn testdata(rel: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../gl-onnx/testdata").join(rel)
}

fn artefact(dir: &Path, path: &str, kind: &str) -> Artefact {
    let bytes = fs::read(dir.join(path)).unwrap();
    Artefact {
        path: path.into(),
        sha256: format!("sha256:{}", sha256_hex(&bytes)),
        bytes: bytes.len() as u64,
        kind: kind.into(),
        used_by: vec![],
    }
}

/// Assemble a bundle with both a tiny encoder and a tiny NLI model.
fn build_bundle(dir: &Path) {
    fs::create_dir_all(dir.join("models")).unwrap();
    fs::create_dir_all(dir.join("tokenizers/enc")).unwrap();
    fs::create_dir_all(dir.join("tokenizers/nli")).unwrap();
    fs::copy(testdata("tiny-bundle/models/tiny.onnx"), dir.join("models/enc.onnx")).unwrap();
    fs::copy(
        testdata("tiny-bundle/tokenizers/tiny/tokenizer.json"),
        dir.join("tokenizers/enc/tokenizer.json"),
    )
    .unwrap();
    fs::copy(testdata("tiny-nli/models/tiny.onnx"), dir.join("models/nli.onnx")).unwrap();
    fs::copy(testdata("tiny-nli/tokenizers/tiny/tokenizer.json"), dir.join("tokenizers/nli/tokenizer.json"))
        .unwrap();

    let mut artefacts = BTreeMap::new();
    for (path, kind) in [
        ("models/enc.onnx", "onnx-model"),
        ("tokenizers/enc/tokenizer.json", "tokenizer"),
        ("models/nli.onnx", "onnx-model"),
        ("tokenizers/nli/tokenizer.json", "tokenizer"),
    ] {
        artefacts.insert(path.to_string(), artefact(dir, path, kind));
    }

    let mut encoders = BTreeMap::new();
    encoders.insert(
        "default".to_string(),
        EncoderSpec {
            model: "models/enc.onnx".into(),
            tokenizer: "tokenizers/enc/tokenizer.json".into(),
            max_tokens: 24,
            prefix: String::new(),
            pooling: "mean".into(),
            dim: 16,
        },
    );

    let mut entailment = BTreeMap::new();
    entailment.insert(
        "default".to_string(),
        EntailmentSpec {
            model: "models/nli.onnx".into(),
            tokenizer: "tokenizers/nli/tokenizer.json".into(),
            max_tokens: 32,
            labels: vec!["entailment".into(), "neutral".into(), "contradiction".into()],
        },
    );

    let manifest = Manifest {
        schema: MANIFEST_SCHEMA.into(),
        name: "tiny-nli-bundle".into(),
        version: "1.0.0".into(),
        engine_version: gl_engine::gl_core::ENGINE_VERSION.into(),
        execution_profile: "cpu-f32".into(),
        artefacts,
        offline_only: true,
        encoders,
        entailment,
        provenance: None,
    };
    fs::write(dir.join("manifest.json"), serde_json::to_string_pretty(&manifest).unwrap()).unwrap();
}

const POLICY: &str = r#"id: nli_demo
version: 1.0.0
verifiers:
  required: [groundlens.numeric]
  optional: [groundlens.lexical, groundlens.nli]
decision:
  any_contradiction_from: [groundlens.numeric]
  unresolved_claims: REVIEW
  tolerate_unresolved_kinds: [word, statement]
"#;

#[test]
fn nli_runs_end_to_end_when_the_bundle_carries_a_model() {
    let dir = std::env::temp_dir().join(format!("gl-nli-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    build_bundle(&dir);

    let mut req = VerifyRequest::new(
        "The invoice total is 10,000 dollars.",
        vec![Source {
            id: "s".into(),
            text: "The total amount due is 10,000 dollars.".into(),
            locator: None,
        }],
    );
    req.policy_yaml = POLICY.into();
    req.bundle = Some(dir.display().to_string());

    let record = verify(&req).unwrap();
    let ran: Vec<&str> = record.content.graph.evidence.iter().map(|e| e.verifier_id.as_str()).collect();
    assert!(ran.contains(&"groundlens.nli"), "groundlens.nli did not run; ran: {ran:?}");

    // The evidence names the exact model, and the whole thing seals and verifies.
    let nli = record.content.graph.evidence.iter().find(|e| e.verifier_id == "groundlens.nli").unwrap();
    assert!(nli.model_hash.as_deref().unwrap_or("").starts_with("sha256:"));
    gl_engine::gl_record::verify_record(&record).unwrap();

    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn a_policy_that_requires_nli_without_a_model_is_a_clear_error() {
    // No bundle: groundlens.nli required but unavailable.
    let policy = "id: p\nversion: 1\nverifiers:\n  required: [groundlens.numeric, groundlens.nli]\n"
        .to_string()
        + "decision:\n  any_contradiction_from: [groundlens.numeric]\n  unresolved_claims: REVIEW\n  tolerate_unresolved_kinds: [word, statement]\n";
    let mut req = VerifyRequest::new(
        "A statement.",
        vec![Source { id: "s".into(), text: "A statement.".into(), locator: None }],
    );
    req.policy_yaml = policy;
    req.lexical = false;
    let err = verify(&req).unwrap_err().to_string();
    assert!(err.contains("groundlens.nli"), "unexpected error: {err}");
}
