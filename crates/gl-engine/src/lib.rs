//! The one pipeline. The CLI, the Python package and any future binding call
//! this and nothing else, so there is exactly one implementation of
//! "verify an answer under a policy and seal the record".

use gl_core::{EvidenceGraph, Result, Source, VerificationInput, Verifier};
use gl_policy::Policy;
use gl_record::{seal, EvidenceRecord, RecordContent, RecordSigner, RECORD_SCHEMA};
use gl_verifiers::{extract_claims_with, NumericConfig, NumericVerifier, RuleSet};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub use gl_bundle;
pub use gl_core;
pub use gl_policy;
pub use gl_record;
pub use gl_verifiers;

pub mod bundle;

/// A policy that ships inside every build: numeric contradictions fail,
/// anything unresolved goes to review, no generative verifier decides.
pub const DEFAULT_POLICY_ID: &str = "groundlens_default_v1";
pub const DEFAULT_POLICY_YAML: &str = r#"id: groundlens_default_v1
version: 1.0.0
description: >
  Numeric claims must be exactly supported by the sources. A numeric
  contradiction fails the answer. Claims no deterministic verifier can
  resolve go to review. No generative verifier decides.
verifiers:
  required: [groundlens.numeric]
  recommended: [groundlens.rules.*]
  optional: [groundlens.lexical, nli.*, semantic.*, sgi, dgi]
  forbidden: [llm_judge.*]
determinism:
  minimum_to_decide: reproducible
decision:
  any_contradiction_from: [groundlens.numeric, groundlens.rules.*]
  unresolved_claims: REVIEW
  conflicts: REVIEW
  tolerate_unresolved_kinds: [word]
"#;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerifyRequest {
    pub answer: String,
    pub sources: Vec<Source>,
    #[serde(default)]
    pub question: Option<String>,
    #[serde(default = "und")]
    pub locale: String,
    /// Policy YAML. Empty means [`DEFAULT_POLICY_YAML`].
    #[serde(default)]
    pub policy_yaml: String,
    /// Rule sets as JSON documents.
    #[serde(default)]
    pub rule_sets_json: Vec<String>,
    #[serde(default)]
    pub numeric: NumericConfig,
    /// Ed25519 seed, 32 bytes hex. Ephemeral key when absent.
    #[serde(default)]
    pub signing_key_hex: Option<String>,
    #[serde(default)]
    pub previous_record_hash: Option<String>,
    /// Recorded when no bundle is loaded (`sha256:unbundled` otherwise).
    #[serde(default)]
    pub bundle_hash: Option<String>,
    /// A bundle directory, or the name of a known bundle (`base`). `None`
    /// uses the installed `base` bundle when there is one.
    #[serde(default)]
    pub bundle: Option<String>,
    /// Run the lexical channel when an encoder is available.
    #[serde(default = "default_true")]
    pub lexical: bool,
    #[serde(default)]
    pub metadata: BTreeMap<String, String>,
}

fn default_true() -> bool {
    true
}

fn und() -> String {
    "und".into()
}

impl VerifyRequest {
    pub fn new(answer: impl Into<String>, sources: Vec<Source>) -> Self {
        VerifyRequest {
            answer: answer.into(),
            sources,
            question: None,
            locale: "und".into(),
            policy_yaml: String::new(),
            rule_sets_json: vec![],
            numeric: NumericConfig::default(),
            signing_key_hex: None,
            previous_record_hash: None,
            bundle_hash: None,
            bundle: None,
            lexical: true,
            metadata: BTreeMap::new(),
        }
    }
}

/// Normalise, extract claims, run every admitted verifier, evaluate the
/// policy and seal a signed record.
pub fn verify(req: &VerifyRequest) -> Result<EvidenceRecord> {
    let answer = gl_text::normalise(&req.answer);
    let question = req.question.as_deref().map(gl_text::normalise);
    let sources: Vec<Source> = req
        .sources
        .iter()
        .map(|s| Source { id: s.id.clone(), text: gl_text::normalise(&s.text), locator: s.locator.clone() })
        .collect();
    let claims = extract_claims_with(&answer, &req.locale, req.numeric.units);
    let mut metadata = indexmap::IndexMap::new();
    for (k, v) in &req.metadata {
        metadata.insert(k.clone(), v.clone());
    }
    let input = VerificationInput { question, answer, sources, claims, locale: req.locale.clone(), metadata };

    let policy_yaml = if req.policy_yaml.trim().is_empty() { DEFAULT_POLICY_YAML } else { &req.policy_yaml };
    let policy = Policy::from_yaml(policy_yaml)?;

    let mut verifiers: Vec<Box<dyn Verifier>> = vec![Box::new(NumericVerifier::new(req.numeric.clone()))];
    for json in &req.rule_sets_json {
        verifiers.push(Box::new(RuleSet::from_json(json)?.compile()?));
    }
    let mut bundle_hash = req.bundle_hash.clone().unwrap_or_else(|| "sha256:unbundled".into());
    let loaded = if req.lexical { bundle::load(req.bundle.as_deref())? } else { None };
    match &loaded {
        Some(b) => {
            bundle_hash = b.manifest_hash.clone();
            #[cfg(feature = "lexical")]
            verifiers.push(Box::new(gl_verifiers::LexicalVerifier::new(b.encoder.clone(), &b.model_hash)));
        }
        None => {
            if policy.verifiers.required.iter().any(|r| r == gl_verifiers::LEXICAL_ID) {
                return Err(gl_core::Error::InvalidInput(bundle::MISSING_BASE.into()));
            }
        }
    }
    let mut infos: Vec<_> = verifiers.iter().map(|v| v.info().clone()).collect();
    for k in known_verifiers() {
        if !infos.iter().any(|i| i.id == k.id) {
            infos.push(k);
        }
    }
    let problems = policy.lint(&infos);
    if !problems.is_empty() {
        return Err(gl_core::Error::InvalidInput(format!("policy lint failed: {}", problems.join("; "))));
    }

    let mut graph = EvidenceGraph::default();
    for v in &verifiers {
        match v.verify(&input) {
            Ok(ev) => graph.push_verifier(v.info().clone(), ev),
            Err(e) => graph.push_failure(&v.info().id, &e.to_string()),
        }
    }
    let kinds: BTreeMap<String, gl_core::ClaimKind> =
        input.claims.iter().map(|c| (c.id.clone(), c.kind)).collect();
    let outcome = gl_policy::evaluate(&policy, &graph, &kinds)?;

    let content = RecordContent {
        schema: RECORD_SCHEMA.into(),
        engine_version: gl_core::ENGINE_VERSION.into(),
        bundle_hash,
        input_hash: gl_record::input_hash(&input)?,
        locale: req.locale.clone(),
        graph,
        outcome,
    };

    let signer = match &req.signing_key_hex {
        Some(seed) => {
            let bytes: [u8; 32] = hex::decode(seed)
                .ok()
                .and_then(|v| v.try_into().ok())
                .ok_or_else(|| gl_core::Error::InvalidInput("signing key must be 32 bytes hex".into()))?;
            RecordSigner::from_bytes(&bytes)
        }
        None => RecordSigner::generate(),
    };
    let timestamp = chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true);
    // The id is outside the content hash on purpose: two verifications of
    // the same input are two records. Content prefix for readability, random
    // suffix for uniqueness.
    let content_hash = gl_core::canonical::content_hash(&content)?;
    let mut nonce = [0u8; 6];
    rand_core::RngCore::fill_bytes(&mut rand_core::OsRng, &mut nonce);
    let record_id = format!("rec_{}_{}", &content_hash[7..19], hex::encode(nonce));
    seal(content, req.previous_record_hash.clone(), record_id, timestamp, &signer)
}

/// The verification input the engine would build for a request, without
/// running anything. Used by the `proofread()` facade to list claims.
pub fn prepare(req: &VerifyRequest) -> VerificationInput {
    let answer = gl_text::normalise(&req.answer);
    let claims = extract_claims_with(&answer, &req.locale, req.numeric.units);
    VerificationInput {
        question: req.question.as_deref().map(gl_text::normalise),
        answer,
        sources: req
            .sources
            .iter()
            .map(|s| Source {
                id: s.id.clone(),
                text: gl_text::normalise(&s.text),
                locator: s.locator.clone(),
            })
            .collect(),
        claims,
        locale: req.locale.clone(),
        metadata: Default::default(),
    }
}

pub fn policy_lint(yaml: &str) -> Result<(String, Vec<String>)> {
    let policy = Policy::from_yaml(yaml)?;
    let known = known_verifiers();
    Ok((policy.hash()?, policy.lint(&known)))
}

/// Declarations of every built-in verifier, model or no model.
pub fn known_verifiers() -> Vec<gl_core::VerifierInfo> {
    #[allow(unused_mut)]
    let mut known = vec![NumericVerifier::default().info().clone()];
    #[cfg(feature = "lexical")]
    known.push(gl_verifiers::LexicalVerifier::info_without_model());
    known
}

pub fn keygen_hex() -> String {
    RecordSigner::generate().seed_hex()
}

#[cfg(test)]
mod tests {
    use super::*;
    use gl_policy::Decision;

    #[test]
    fn end_to_end_numeric_contradiction_fails_and_record_verifies() {
        let req = VerifyRequest::new(
            "Revenue was €15M.",
            vec![Source { id: "10k".into(), text: "Revenue was €10M.".into(), locator: None }],
        );
        let record = verify(&req).unwrap();
        assert_eq!(record.content.outcome.decision, Decision::Fail);
        assert_eq!(record.content.outcome.policy_id, DEFAULT_POLICY_ID);
        let ev = &record.content.graph.evidence[0];
        assert_eq!(ev.verifier_id, "groundlens.numeric");
        assert_eq!(ev.result, gl_core::EvidenceResult::Contradicted);
        gl_record::verify_record(&record).unwrap();

        let again = verify(&req).unwrap();
        assert_eq!(record.content_hash, again.content_hash);
    }

    #[cfg(feature = "lexical")]
    #[test]
    fn lexical_channel_runs_from_a_bundle_and_is_hashed_into_the_record() {
        let tiny = concat!(env!("CARGO_MANIFEST_DIR"), "/../gl-onnx/testdata/tiny-bundle");
        let mut req = VerifyRequest::new(
            "The invoice total is 1,000 dollars.",
            vec![Source {
                id: "s".into(),
                text: "The total amount due is 10,000 dollars.".into(),
                locator: None,
            }],
        );
        req.bundle = Some(tiny.into());
        let record = verify(&req).unwrap();
        assert!(record.content.bundle_hash.starts_with("sha256:"));
        assert_ne!(record.content.bundle_hash, "sha256:unbundled");
        let lexical: Vec<_> =
            record.content.graph.evidence.iter().filter(|e| e.verifier_id == "groundlens.lexical").collect();
        assert_eq!(lexical.len(), 2, "invoice, total");
        assert!(lexical.iter().all(|e| e.model_hash.is_some()));
        assert_eq!(record.content.outcome.decision, Decision::Fail);
        assert_eq!(verify(&req).unwrap().content_hash, record.content_hash);

        // A policy that requires the channel refuses to run without a bundle.
        let mut strict = req.clone();
        strict.bundle = None;
        strict.policy_yaml = "id: strict
version: 1
verifiers:
  required: [groundlens.numeric, groundlens.lexical]
"
        .into();
        if gl_bundle::open_installed("base").unwrap().is_none() {
            let err = verify(&strict).unwrap_err().to_string();
            assert!(err.contains("bundle pull base"), "{err}");
        }
    }
}
