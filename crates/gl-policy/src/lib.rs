//! Policy: what the organisation considers acceptable.
//!
//! The engine measures. The policy interprets. A policy names which
//! verifiers are required, recommended, optional, fallback or forbidden,
//! which determinism class may decide, the thresholds per verifier, a
//! guard band around each threshold, and how each outcome maps to a
//! regulatory control.
//!
//! ```yaml
//! id: eu_ai_act_high_risk_v1
//! version: 1.0.0
//! description: Article 15 accuracy controls for a RAG assistant in a high-risk use
//! verifiers:
//!   required: [groundlens.numeric]
//!   recommended: [nli.deberta_v3_small, groundlens.lexical]
//!   optional: [sgi, dgi]
//!   fallback: [llm_judge.default]
//!   forbidden: []
//! determinism:
//!   minimum_to_decide: reproducible     # exact | reproducible | any
//! thresholds:
//!   nli.deberta_v3_small: { support_min: 0.85, guard_band: 0.02 }
//!   groundlens.lexical:   { support_min: 0.60, guard_band: 0.02 }
//! decision:
//!   any_contradiction_from: [groundlens.numeric, groundlens.rules.*]   -> FAIL
//!   unresolved_claims: REVIEW
//!   conflicts: REVIEW
//! regulatory_mapping:
//!   - framework: EU-AI-Act-2024/1689
//!     article: "Art. 15(1)"
//!     control: accuracy-of-outputs
//!     triggered_by: [FAIL, REVIEW]
//! ```
//!
//! ## The guard band
//!
//! Functional determinism promises the same *classification* across
//! platforms while scores may drift within a tolerance. A threshold compared
//! with a drifting score is exactly where classifications flip. The guard
//! band closes that gap: a score within `guard_band` of the threshold is
//! `REVIEW` on every platform, so a platform difference can never turn a
//! `PASS` into a `FAIL`. The band must be at least twice the verifier's
//! declared tolerance; `lint` enforces that.

use gl_core::{Determinism, EvidenceGraph, EvidenceResult, Result, VerifierInfo};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum Decision {
    Pass,
    Review,
    Fail,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct VerifierSets {
    #[serde(default)]
    pub required: Vec<String>,
    #[serde(default)]
    pub recommended: Vec<String>,
    #[serde(default)]
    pub optional: Vec<String>,
    #[serde(default)]
    pub fallback: Vec<String>,
    #[serde(default)]
    pub forbidden: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MinimumDeterminism {
    Exact,
    Reproducible,
    Any,
}

impl MinimumDeterminism {
    fn admits(self, d: Determinism) -> bool {
        match self {
            MinimumDeterminism::Exact => d.rank() >= 2,
            MinimumDeterminism::Reproducible => d.rank() >= 1,
            MinimumDeterminism::Any => true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeterminismPolicy {
    pub minimum_to_decide: MinimumDeterminism,
}

impl Default for DeterminismPolicy {
    fn default() -> Self {
        DeterminismPolicy { minimum_to_decide: MinimumDeterminism::Reproducible }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Threshold {
    /// Scores at or above this count as support.
    pub support_min: f64,
    /// Half-width of the review band around `support_min`.
    #[serde(default)]
    pub guard_band: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecisionRules {
    /// A `Contradicted` from any of these verifiers (glob `prefix.*`
    /// allowed) fails the whole answer.
    #[serde(default)]
    pub any_contradiction_from: Vec<String>,
    /// What to do with claims no admitted verifier could speak to.
    #[serde(default = "review")]
    pub unresolved_claims: Decision,
    /// What to do when two verifiers disagree on the same claim.
    #[serde(default = "review")]
    pub conflicts: Decision,
    /// Claim kinds a missing verdict is acceptable for (words in a faithful
    /// paraphrase, typically).
    #[serde(default)]
    pub tolerate_unresolved_kinds: Vec<gl_core::ClaimKind>,
}

fn review() -> Decision {
    Decision::Review
}

impl Default for DecisionRules {
    fn default() -> Self {
        DecisionRules {
            any_contradiction_from: vec!["groundlens.numeric".into(), "groundlens.rules.*".into()],
            unresolved_claims: Decision::Review,
            conflicts: Decision::Review,
            tolerate_unresolved_kinds: vec![gl_core::ClaimKind::Word],
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegulatoryControl {
    pub framework: String,
    pub article: String,
    pub control: String,
    #[serde(default)]
    pub requirement: String,
    pub triggered_by: Vec<Decision>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Policy {
    pub id: String,
    pub version: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub verifiers: VerifierSets,
    #[serde(default)]
    pub determinism: DeterminismPolicy,
    #[serde(default)]
    pub thresholds: BTreeMap<String, Threshold>,
    #[serde(default)]
    pub decision: DecisionRules,
    #[serde(default)]
    pub regulatory_mapping: Vec<RegulatoryControl>,
}

impl Policy {
    pub fn from_yaml(text: &str) -> Result<Policy> {
        serde_yaml::from_str(text).map_err(|e| gl_core::Error::InvalidInput(format!("policy: {e}")))
    }

    pub fn hash(&self) -> Result<String> {
        gl_core::canonical::content_hash(self)
    }

    /// Static checks a policy must pass before it can be loaded.
    pub fn lint(&self, known: &[VerifierInfo]) -> Vec<String> {
        let mut problems = Vec::new();
        for (id, t) in &self.thresholds {
            if !(0.0..=1.0).contains(&t.support_min) {
                problems.push(format!("{id}: support_min out of [0,1]"));
            }
            if let Some(info) = known.iter().find(|k| &k.id == id) {
                if info.determinism == Determinism::Exact {
                    problems
                        .push(format!("{id}: is an exact verifier; it has no continuous score to threshold"));
                }
                let tol = info.determinism.tolerance().0;
                if t.guard_band < 2.0 * tol {
                    problems.push(format!(
                        "{id}: guard_band {} is below twice the verifier tolerance {}",
                        t.guard_band, tol
                    ));
                }
                if !self.determinism.minimum_to_decide.admits(info.determinism) {
                    problems.push(format!(
                        "{id}: has a threshold but its determinism class cannot decide under this policy"
                    ));
                }
            }
        }
        for id in &self.verifiers.required {
            if self.verifiers.forbidden.contains(id) {
                problems.push(format!("{id}: both required and forbidden"));
            }
        }
        problems
    }
}

fn glob_matches(pattern: &str, id: &str) -> bool {
    match pattern.strip_suffix(".*") {
        Some(prefix) => id == prefix || id.starts_with(&format!("{prefix}.")),
        None => pattern == id,
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClaimOutcome {
    pub claim_id: String,
    pub decision: Decision,
    pub reasons: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyOutcome {
    pub policy_id: String,
    pub policy_version: String,
    pub policy_hash: String,
    pub decision: Decision,
    pub claims: Vec<ClaimOutcome>,
    pub missing_required: Vec<String>,
    pub excluded_verifiers: Vec<(String, String)>,
    pub regulatory_mapping: Vec<RegulatoryControl>,
}

/// Evaluate a policy over an evidence graph. Pure function: same graph,
/// same policy, same outcome, on any machine.
pub fn evaluate(
    policy: &Policy,
    graph: &EvidenceGraph,
    claim_kinds: &BTreeMap<String, gl_core::ClaimKind>,
) -> Result<PolicyOutcome> {
    let mut excluded: Vec<(String, String)> = Vec::new();
    let admitted: Vec<&VerifierInfo> = graph
        .verifiers
        .iter()
        .filter(|v| {
            if policy.verifiers.forbidden.iter().any(|f| glob_matches(f, &v.id)) {
                excluded.push((v.id.clone(), "forbidden by policy".into()));
                return false;
            }
            if !policy.determinism.minimum_to_decide.admits(v.determinism) {
                excluded.push((
                    v.id.clone(),
                    "determinism class below policy minimum; recorded, not deciding".into(),
                ));
                return false;
            }
            true
        })
        .collect();

    let missing_required: Vec<String> = policy
        .verifiers
        .required
        .iter()
        .filter(|r| !admitted.iter().any(|v| glob_matches(r, &v.id)))
        .cloned()
        .collect();

    let mut claims: Vec<ClaimOutcome> = Vec::new();
    let mut overall = Decision::Pass;
    let conflicts = graph.conflicts();

    for (claim_id, kind) in claim_kinds {
        let mut decision = Decision::Pass;
        let mut reasons = Vec::new();
        let mut spoke = false;

        for e in graph.for_claim(claim_id) {
            if !admitted.iter().any(|v| v.id == e.verifier_id) {
                continue;
            }
            match e.result {
                EvidenceResult::NotApplicable | EvidenceResult::Error => continue,
                _ => spoke = true,
            }
            if e.result == EvidenceResult::Contradicted
                && policy.decision.any_contradiction_from.iter().any(|p| glob_matches(p, &e.verifier_id))
            {
                decision = Decision::Fail;
                reasons.push(format!("{} contradicted: {}", e.verifier_id, e.rationale));
                continue;
            }
            if let Some(t) = policy.thresholds.get(&e.verifier_id) {
                let s = e.score.0;
                if (s - t.support_min).abs() <= t.guard_band {
                    decision = decision.max(Decision::Review);
                    reasons.push(format!(
                        "{} score {s:.6} inside guard band of {}",
                        e.verifier_id, t.support_min
                    ));
                } else if s < t.support_min {
                    decision = decision.max(Decision::Review);
                    reasons.push(format!("{} score {s:.6} below {}", e.verifier_id, t.support_min));
                }
            } else if e.result == EvidenceResult::Contradicted {
                decision = decision.max(Decision::Review);
                reasons.push(format!(
                    "{} contradicted (not a failing verifier under this policy)",
                    e.verifier_id
                ));
            }
        }

        if conflicts.iter().any(|c| c == claim_id) {
            decision = decision.max(policy.decision.conflicts);
            reasons.push("verifiers disagree on this claim".into());
        }
        if !spoke && !policy.decision.tolerate_unresolved_kinds.contains(kind) {
            decision = decision.max(policy.decision.unresolved_claims);
            reasons.push("no admitted verifier produced evidence for this claim".into());
        }

        overall = overall.max(decision);
        claims.push(ClaimOutcome { claim_id: claim_id.clone(), decision, reasons });
    }

    if !missing_required.is_empty() {
        overall = overall.max(Decision::Review);
    }

    let regulatory_mapping =
        policy.regulatory_mapping.iter().filter(|c| c.triggered_by.contains(&overall)).cloned().collect();

    Ok(PolicyOutcome {
        policy_id: policy.id.clone(),
        policy_version: policy.version.clone(),
        policy_hash: policy.hash()?,
        decision: overall,
        claims,
        missing_required,
        excluded_verifiers: excluded,
        regulatory_mapping,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use gl_core::{ClaimKind, Evidence, Receipt, Score, Tolerance, VerifierKind};

    fn info(id: &str, d: Determinism) -> VerifierInfo {
        VerifierInfo {
            id: id.into(),
            version: "1".into(),
            kind: VerifierKind::Ml,
            determinism: d,
            applies_to: vec![],
            artefacts: vec![],
            needs_network: false,
        }
    }

    fn ev(v: &str, claim: &str, result: EvidenceResult, score: f64, d: Determinism) -> Evidence {
        Evidence {
            verifier_id: v.into(),
            verifier_version: "1".into(),
            claim_id: claim.into(),
            result,
            score: Score(score),
            confidence: Score(1.0),
            determinism: d,
            rationale: String::new(),
            receipt: Receipt::default(),
            model_hash: None,
            calibration_id: None,
        }
    }

    const POLICY: &str = r#"
id: test
version: 1.0.0
verifiers:
  required: [groundlens.numeric]
  forbidden: [llm_judge.*]
determinism:
  minimum_to_decide: reproducible
thresholds:
  nli.demo: { support_min: 0.85, guard_band: 0.02 }
regulatory_mapping:
  - framework: EU-AI-Act-2024/1689
    article: "Art. 15(1)"
    control: accuracy-of-outputs
    triggered_by: [FAIL, REVIEW]
"#;

    #[test]
    fn numeric_contradiction_fails_and_maps_to_article_15() {
        let policy = Policy::from_yaml(POLICY).unwrap();
        let mut graph = EvidenceGraph::default();
        graph.push_verifier(
            info("groundlens.numeric", Determinism::Exact),
            vec![ev("groundlens.numeric", "c2", EvidenceResult::Contradicted, 0.0, Determinism::Exact)],
        );
        let kinds = BTreeMap::from([("c2".to_string(), ClaimKind::Numeric)]);
        let out = evaluate(&policy, &graph, &kinds).unwrap();
        assert_eq!(out.decision, Decision::Fail);
        assert_eq!(out.regulatory_mapping[0].article, "Art. 15(1)");
    }

    #[test]
    fn guard_band_routes_to_review_and_judge_is_recorded_not_deciding() {
        let policy = Policy::from_yaml(POLICY).unwrap();
        let rep = Determinism::Reproducible { tolerance: Tolerance::FLOAT32_CPU };
        let mut graph = EvidenceGraph::default();
        graph.push_verifier(info("groundlens.numeric", Determinism::Exact), vec![]);
        graph.push_verifier(
            info("nli.demo", rep),
            vec![ev("nli.demo", "c0", EvidenceResult::Supported, 0.86, rep)],
        );
        graph.push_verifier(
            info("llm_judge.x", Determinism::NonDeterministic),
            vec![ev("llm_judge.x", "c0", EvidenceResult::Contradicted, 0.1, Determinism::NonDeterministic)],
        );
        let kinds = BTreeMap::from([("c0".to_string(), ClaimKind::Statement)]);
        let out = evaluate(&policy, &graph, &kinds).unwrap();
        assert_eq!(out.decision, Decision::Review);
        assert!(out.claims[0].reasons[0].contains("guard band"));
        assert_eq!(out.excluded_verifiers[0].0, "llm_judge.x");
    }

    #[test]
    fn lint_catches_a_guard_band_narrower_than_drift() {
        let mut policy = Policy::from_yaml(POLICY).unwrap();
        policy.thresholds.get_mut("nli.demo").unwrap().guard_band = 0.0;
        let known = [info("nli.demo", Determinism::Reproducible { tolerance: Tolerance::FLOAT32_CPU })];
        assert_eq!(policy.lint(&known).len(), 1);
    }
}
