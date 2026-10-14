// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The one pipeline. The CLI, the Python package and any future binding call
//! this and nothing else, so there is exactly one implementation of
//! "verify an answer under a policy and seal the record".

use gl_core::{EvidenceGraph, Result, Source, VerificationInput, Verifier};
use gl_policy::Policy;
use gl_record::{seal, EvidenceRecord, RecordContent, RecordSigner, UnsignedRecord, RECORD_SCHEMA};
use gl_verifiers::{
    extract_claims_with, IntentVerifier, NumericConfig, NumericVerifier, RuleSet, ScopeVerifier,
};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub use gl_core;
pub use gl_mcp;
pub use gl_policy;
pub use gl_record;
pub use gl_runtime;
pub use gl_verifiers;

pub mod judge;
pub mod run;
pub use run::{verify_run, RunVerifyRequest};

/// A policy that ships inside every build: numeric contradictions fail, a
/// figure taken from outside the request's scope fails, anything unresolved
/// goes to review, no generative verifier decides. It names no model
/// channel: the default path runs without a model.
pub const DEFAULT_POLICY_ID: &str = "groundlens_default_v1";
pub const DEFAULT_POLICY_YAML: &str = gl_policy::GROUNDLENS_DEFAULT_V1;

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
    #[serde(default)]
    pub metadata: BTreeMap<String, String>,
    /// What the request is about (`entity = UPS`). When present, the scope
    /// verifier checks that every figure the answer uses comes from a passage
    /// inside this scope. Hashed into the record's `input_hash`.
    #[serde(default)]
    pub scope: BTreeMap<String, String>,
    /// The risk class of the request, when the policy defines risk classes.
    /// `None` means the policy's default class.
    #[serde(default)]
    pub risk_class: Option<String>,
    /// What the caller's model replied to the prompt from [`judge_prompt`].
    /// The engine never calls a model; the caller does, and passes the reply.
    #[serde(default)]
    pub judge: Option<judge::JudgeReply>,
    /// For replay: the judge's evidence from an earlier record of the same
    /// input, used instead of asking again. Accepted only if it was produced
    /// by the same prompt.
    #[serde(default)]
    pub judge_evidence: Option<judge::StoredJudge>,
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
            metadata: BTreeMap::new(),
            scope: BTreeMap::new(),
            risk_class: None,
            judge: None,
            judge_evidence: None,
        }
    }
}

/// The policy a request runs under: its own YAML, or the default.
fn request_policy(req: &VerifyRequest) -> Result<Policy> {
    let policy_yaml = if req.policy_yaml.trim().is_empty() { DEFAULT_POLICY_YAML } else { &req.policy_yaml };
    Policy::from_yaml(policy_yaml)
}

/// Apply what the policy fixes over what the request asked for. The policy
/// wins: a locale or rounding rule written in the policy is the one used,
/// whatever the request says, so the same policy hash always means the same
/// reading of the numbers.
fn apply_policy(req: &VerifyRequest, policy: &Policy) -> Result<VerifyRequest> {
    let mut req = req.clone();
    if let Some(locale) = &policy.locale {
        req.locale = locale.clone();
    }
    if let Some(rule) = policy.rounding() {
        req.numeric.rounding = serde_json::from_value(serde_json::Value::String(rule.to_string()))
            .map_err(|_| gl_core::Error::InvalidInput(format!("policy: unknown rounding rule {rule:?}")))?;
    }
    Ok(req)
}

/// Normalise, extract claims, run every admitted verifier, evaluate the
/// policy and seal a signed record.
pub fn verify(req: &VerifyRequest) -> Result<EvidenceRecord> {
    verify_timed(req).map(|(record, _)| record)
}

/// How long each part of a verification took, in microseconds. Kept out of the
/// record on purpose: a duration differs on every run and every machine, and the
/// record's content must not. Observability tools read these instead.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Timings {
    /// Each verifier the engine ran, in the order it ran, with its duration.
    pub verifiers: Vec<(String, u64)>,
    /// From the request entering the engine to the sealed record.
    pub total_us: u64,
}

fn micros(d: std::time::Duration) -> u64 {
    u64::try_from(d.as_micros()).unwrap_or(u64::MAX)
}

/// [`verify`], also returning how long each verifier took.
pub fn verify_timed(req: &VerifyRequest) -> Result<(EvidenceRecord, Timings)> {
    let started = std::time::Instant::now();
    let mut timings = Timings::default();
    let policy = request_policy(req)?;
    let req = &apply_policy(req, &policy)?;
    let answer = gl_text::normalise(&req.answer);
    let question = req.question.as_deref().map(gl_text::normalise);
    let sources: Vec<Source> = req
        .sources
        .iter()
        .map(|s| Source {
            id: s.id.clone(),
            text: gl_text::normalise(&s.text),
            locator: s.locator.clone(),
            provenance: s.provenance.clone(),
        })
        .collect();
    let claims = extract_claims_with(&answer, &req.locale, req.numeric.units);
    let mut metadata = indexmap::IndexMap::new();
    for (k, v) in &req.metadata {
        metadata.insert(k.clone(), v.clone());
    }
    let scope: indexmap::IndexMap<String, String> =
        req.scope.iter().map(|(k, v)| (k.clone(), v.clone())).collect();
    let input =
        VerificationInput { question, answer, sources, claims, locale: req.locale.clone(), metadata, scope };

    let mut verifiers: Vec<Box<dyn Verifier>> = vec![Box::new(NumericVerifier::new(req.numeric.clone()))];
    // The scope channel runs only when the request states a scope, so a
    // request without one produces exactly the record it produced before.
    if !input.scope.is_empty() {
        verifiers.push(Box::new(ScopeVerifier::new()));
    }
    // The intent channel reads the question; without one it has nothing to
    // compare the answer with.
    if input.question.as_deref().is_some_and(|q| !q.trim().is_empty()) {
        verifiers.push(Box::new(IntentVerifier::new()));
    }
    for json in &req.rule_sets_json {
        verifiers.push(Box::new(RuleSet::from_json(json)?.compile()?));
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
        let t = std::time::Instant::now();
        let out = v.verify(&input);
        timings.verifiers.push((v.info().id.clone(), micros(t.elapsed())));
        match out {
            Ok(ev) => graph.push_verifier(v.info().clone(), ev),
            Err(e) => graph.push_failure(&v.info().id, &e.to_string()),
        }
    }
    if req.judge.is_some() && req.judge_evidence.is_some() {
        return Err(gl_core::Error::InvalidInput(
            "pass a judge reply or stored judge evidence, not both".into(),
        ));
    }
    if let Some(stored) = &req.judge_evidence {
        let rendered = judge::render(&input, &policy);
        let (info, evidence, failure) = judge::reuse(&rendered, stored)?;
        let id = info.id.clone();
        graph.push_verifier(info, evidence);
        if let Some(message) = failure {
            graph.push_failure(&id, &message);
        }
    }
    if let Some(reply) = &req.judge {
        let rendered = judge::render(&input, &policy);
        let info = judge::info(&rendered, reply);
        let id = info.id.clone();
        match &reply.error {
            Some(error) => {
                graph.push_verifier(info, vec![]);
                graph.push_failure(&id, error);
            }
            None => graph.push_verifier(info, judge::parse(&rendered, reply)),
        }
    }
    let kinds: BTreeMap<String, gl_core::ClaimKind> =
        input.claims.iter().map(|c| (c.id.clone(), c.kind)).collect();
    let facts = gl_policy::RequestFacts {
        scope_keys: input.scope.keys().cloned().collect(),
        risk_class: req.risk_class.clone(),
    };
    let outcome = gl_policy::evaluate_request(&policy, &graph, &kinds, &facts)?;

    let content = RecordContent {
        schema: RECORD_SCHEMA.into(),
        engine_version: gl_core::ENGINE_VERSION.into(),
        // Part of the record schema since 1.0. No model runs, so no bundle.
        bundle_hash: "sha256:unbundled".into(),
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
    let (record_id, timestamp) = record_id_and_time(&content)?;
    let record = seal(content, req.previous_record_hash.clone(), record_id, timestamp, &signer)?;
    timings.total_us = micros(started.elapsed());
    Ok((record, timings))
}

/// The id is outside the content hash on purpose: two verifications of the
/// same input are two records. Content prefix for readability, random suffix
/// for uniqueness.
fn record_id_and_time(content: &RecordContent) -> Result<(String, String)> {
    let timestamp = chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true);
    let content_hash = gl_core::canonical::content_hash(content)?;
    let mut nonce = [0u8; 6];
    rand_core::RngCore::fill_bytes(&mut rand_core::OsRng, &mut nonce);
    Ok((format!("rec_{}_{}", &content_hash[7..19], hex::encode(nonce)), timestamp))
}

/// Verify like [`verify`], but leave the signature to a key service: the
/// result carries every hash and no signature. Sign the bytes of its
/// `record_hash` and pass the signature to [`gl_record::attach_signature`].
/// `signing_key_hex` in the request is ignored.
pub fn verify_unsigned(req: &VerifyRequest) -> Result<UnsignedRecord> {
    verify_unsigned_timed(req).map(|(record, _)| record)
}

/// [`verify_unsigned`], also returning how long each verifier took.
pub fn verify_unsigned_timed(req: &VerifyRequest) -> Result<(UnsignedRecord, Timings)> {
    let mut local = req.clone();
    // Seal with a throwaway key, then drop the signature: one pipeline, so an
    // unsigned record is exactly what a signed one would have been.
    local.signing_key_hex = None;
    let (sealed, timings) = verify_timed(&local)?;
    let unsigned = UnsignedRecord {
        record_id: sealed.record_id,
        timestamp: sealed.timestamp,
        content: sealed.content,
        content_hash: sealed.content_hash,
        previous_record_hash: sealed.previous_record_hash,
        record_hash: sealed.record_hash,
    };
    Ok((unsigned, timings))
}

/// The verification input the engine would build for a request, without
/// running anything. The judge prompt is rendered from it.
pub fn prepare(req: &VerifyRequest) -> VerificationInput {
    // The locale a policy fixes changes how claims are read, so honour it
    // here too; an invalid policy is reported by `verify`, not here.
    let applied = request_policy(req).and_then(|p| apply_policy(req, &p)).ok();
    let req = applied.as_ref().unwrap_or(req);
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
                provenance: s.provenance.clone(),
            })
            .collect(),
        claims,
        locale: req.locale.clone(),
        metadata: Default::default(),
        scope: req.scope.iter().map(|(k, v)| (k.clone(), v.clone())).collect(),
    }
}

/// The exact prompt a judge is sent for this request: the policy, the scope,
/// the provenance of every passage, and the claims to label. Send `system`
/// and `user` to your model and pass its reply back in `VerifyRequest::judge`.
pub fn judge_prompt(req: &VerifyRequest) -> Result<judge::Rendered> {
    let policy = request_policy(req)?;
    Ok(judge::render(&prepare(req), &policy))
}

/// Load a policy from YAML text or, when the text is a single word naming a
/// shipped policy, from the build.
pub fn load_policy(yaml_or_name: &str) -> Result<Policy> {
    let trimmed = yaml_or_name.trim();
    match gl_policy::builtin(trimmed) {
        Some(text) => Policy::from_yaml(text),
        None => Policy::from_yaml(yaml_or_name),
    }
}

/// `(resolved policy hash, lint problems)`.
pub fn policy_lint(yaml: &str) -> Result<(String, Vec<String>)> {
    let policy = load_policy(yaml)?;
    let known = known_verifiers();
    Ok((policy.hash()?, policy.lint(&known)))
}

/// The resolved policy as YAML, headed by its id, version and hash. Loading
/// the YAML gives the same hash.
pub fn policy_resolve(yaml: &str) -> Result<String> {
    let policy = load_policy(yaml)?;
    Ok(format!("# {} v{}\n# hash: {}\n{}", policy.id, policy.version, policy.hash()?, policy.to_yaml()?))
}

/// Declarations of every built-in verifier.
pub fn known_verifiers() -> Vec<gl_core::VerifierInfo> {
    vec![
        NumericVerifier::default().info().clone(),
        ScopeVerifier::default().info().clone(),
        IntentVerifier::default().info().clone(),
    ]
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
            vec![Source {
                id: "10k".into(),
                text: "Revenue was €10M.".into(),
                locator: None,
                provenance: Default::default(),
            }],
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

    #[test]
    fn a_request_without_scope_or_question_runs_the_numeric_check_only() {
        let req = VerifyRequest::new(
            "The invoice total is 1,000 dollars.",
            vec![Source {
                id: "s".into(),
                text: "The total amount due is 10,000 dollars.".into(),
                locator: None,
                provenance: Default::default(),
            }],
        );
        let record = verify(&req).unwrap();
        assert_eq!(record.content.bundle_hash, "sha256:unbundled");
        let ids: Vec<&str> = record.content.graph.verifiers.iter().map(|v| v.id.as_str()).collect();
        assert_eq!(ids, ["groundlens.numeric"]);
    }

    fn src(text: &str) -> Source {
        Source { id: "s".into(), text: text.into(), locator: None, provenance: Default::default() }
    }

    #[test]
    fn the_policy_rounding_rule_wins_over_the_request() {
        // 2,345 / 1,000 = 2.345 exactly: 2.35 half up, 2.34 half even.
        let mut req = VerifyRequest::new(
            "Revenue was 2,345 against costs of 1,000, a ratio of 2.35.",
            vec![src("Revenue was 2,345. Costs were 1,000.")],
        );
        let half_up = verify(&req).unwrap();
        req.policy_yaml =
            "id: banker\nversion: 1.0.0\nextends: groundlens_default_v1\nrounding: half_even\n".into();
        let half_even = verify(&req).unwrap();
        assert_ne!(
            canonical(&half_up.content.graph),
            canonical(&half_even.content.graph),
            "the policy rule must change how 2.35 is read"
        );
        // The request asks for half up; the policy says half even and wins.
        req.numeric.rounding = gl_numeric_rounding("half_up");
        let still_even = verify(&req).unwrap();
        assert_eq!(canonical(&half_even.content.graph), canonical(&still_even.content.graph));
        assert_eq!(half_even.content.outcome.policy_id, "banker");
    }

    fn canonical<T: Serialize>(value: &T) -> String {
        gl_core::canonical::canonical_json(value).unwrap()
    }

    fn gl_numeric_rounding(name: &str) -> gl_numeric::arith::Rounding {
        serde_json::from_value(serde_json::Value::String(name.into())).unwrap()
    }

    #[test]
    fn a_required_scope_key_and_a_mandatory_risk_class_reach_the_record() {
        let mut req = VerifyRequest::new("Revenue was €10M.", vec![src("Revenue was €10M.")]);
        req.policy_yaml = "id: desk\nversion: 1.0.0\nextends: eu_ai_act_high_risk_v1\n\
                           pass_means: may be shown to the analyst\n\
                           scope:\n  required: [entity]\n\
                           risk_classes:\n  default: routine\n  mandatory_review: [recommendation]\n"
            .into();
        let missing = verify(&req).unwrap();
        assert_eq!(missing.content.outcome.decision, Decision::Review);
        assert!(missing.content.outcome.reasons[0].starts_with("missing_scope"));
        assert_eq!(missing.content.outcome.pass_means.as_deref(), Some("may be shown to the analyst"));
        gl_record::verify_record(&missing).unwrap();

        req.scope.insert("entity".into(), "ACME".into());
        req.sources[0].provenance.insert("entity".into(), "ACME".into());
        let ok = verify(&req).unwrap();
        assert_eq!(ok.content.outcome.decision, Decision::Pass);
        assert_eq!(ok.content.outcome.risk_class.as_deref(), Some("routine"));

        req.risk_class = Some("recommendation".into());
        assert_eq!(verify(&req).unwrap().content.outcome.decision, Decision::Review);
        req.risk_class = Some("nonsense".into());
        assert!(verify(&req).unwrap_err().to_string().contains("no risk class"));
    }

    #[test]
    fn stored_judge_evidence_replays_only_for_the_same_prompt() {
        let policy =
            "id: j\nversion: 1\nextends: groundlens_default_v1\nverifiers:\n  forbidden: []\njudge: {}\n";
        let mut req = VerifyRequest::new("Revenue was €10M.", vec![src("Revenue was €10M.")]);
        req.policy_yaml = policy.into();
        let prompt = judge_prompt(&req).unwrap();
        let reply =
            format!("{{\"claims\": [{{\"id\": \"{}\", \"label\": \"unsupported\"}}]}}", prompt.claims[0].0);
        req.judge = Some(judge::JudgeReply {
            adapter: "test".into(),
            model: "m".into(),
            response: Some(reply),
            error: None,
        });
        let first = verify(&req).unwrap();
        assert_eq!(first.content.outcome.decision, Decision::Review);

        let info = first.content.graph.verifiers.iter().find(|v| v.id == "llm_judge.test").unwrap().clone();
        let evidence: Vec<_> =
            first.content.graph.evidence.iter().filter(|e| e.verifier_id == info.id).cloned().collect();
        let stored = judge::StoredJudge { info, evidence, failure: None };
        let mut replay = req.clone();
        replay.judge = None;
        replay.judge_evidence = Some(stored.clone());
        let again = verify(&replay).unwrap();
        assert_eq!(
            canonical(&again.content),
            canonical(&first.content),
            "the same evidence, the same record content"
        );

        // Under a policy that changes the prompt, the old answer is refused.
        replay.policy_yaml = format!("{policy}pass_means: shown to clients\n");
        assert!(verify(&replay).unwrap_err().to_string().contains("another prompt"));
    }

    #[test]
    fn timings_list_every_verifier_and_stay_out_of_the_record() {
        let mut req = VerifyRequest::new("Revenue was €10M.", vec![src("Revenue was €10M.")]);
        req.question = Some("What was revenue?".into());
        let (record, timings) = verify_timed(&req).unwrap();
        let ran: Vec<&str> = timings.verifiers.iter().map(|(id, _)| id.as_str()).collect();
        assert_eq!(ran, ["groundlens.numeric", "groundlens.intent"]);
        assert!(timings.total_us >= timings.verifiers.iter().map(|(_, us)| us).sum::<u64>());
        assert!(!serde_json::to_string(&record).unwrap().contains("total_us"));
        assert_eq!(record.content_hash, verify(&req).unwrap().content_hash);
    }

    #[test]
    fn shipped_policies_load_by_name_and_resolve_to_their_own_hash() {
        for (id, text) in gl_policy::BUILTIN {
            let (hash, problems) = policy_lint(id).unwrap();
            assert!(problems.is_empty(), "{id}: {problems:?}");
            assert_eq!(hash, Policy::from_yaml(text).unwrap().hash().unwrap());
            let resolved = policy_resolve(id).unwrap();
            assert!(resolved.contains(&hash));
            assert_eq!(policy_lint(&resolved).unwrap().0, hash);
        }
    }
}
