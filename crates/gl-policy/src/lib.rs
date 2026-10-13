// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

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
//!   unsupported_from: [groundlens.scope]                                -> REVIEW
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
//!
//! ## Strict keys and `extends`
//!
//! Every key is checked: a key the schema does not know is an error, so a
//! typo cannot silently switch a rule off. A policy may `extends` a shipped
//! baseline ([`BUILTIN`]) and write only what differs: maps merge key by
//! key, lists and scalars replace. The policy that decides, and whose hash
//! goes into every record, is the resolved one; `Policy::to_yaml` prints it.
//!
//! ## Failure semantics
//!
//! Nothing that went wrong can pass. A verifier that could not run, a verifier
//! error on a claim that needs a verdict, a missing required verifier and a
//! missing required scope key all lead to `REVIEW` at least.

use gl_core::{Determinism, EvidenceGraph, EvidenceResult, Result, VerifierInfo};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// The policies shipped inside every build, by id. A policy can `extends`
/// any of them. The repository keeps copies under `policies/` and in the
/// Python package; tests check the copies are byte-identical.
pub const BUILTIN: [(&str, &str); 2] =
    [("groundlens_default_v1", GROUNDLENS_DEFAULT_V1), ("eu_ai_act_high_risk_v1", EU_AI_ACT_HIGH_RISK_V1)];

/// `groundlens_default_v1`: numeric contradictions and out-of-scope figures
/// fail, anything unresolved goes to review, no model and no judge.
pub const GROUNDLENS_DEFAULT_V1: &str = include_str!("../policies/groundlens_default_v1.yaml");

/// `eu_ai_act_high_risk_v1`: the default rules, mapped to Articles 12, 14
/// and 15 of Regulation (EU) 2024/1689.
pub const EU_AI_ACT_HIGH_RISK_V1: &str = include_str!("../policies/eu_ai_act_high_risk_v1.yaml");

/// The YAML of a shipped policy, by id.
pub fn builtin(id: &str) -> Option<&'static str> {
    BUILTIN.iter().find(|(name, _)| *name == id).map(|(_, text)| *text)
}

/// The rounding rules a policy may name. The numeric verifier implements them.
pub const ROUNDING_RULES: [&str; 3] = ["half_up", "half_even", "within_last_digit"];

fn err(message: impl Into<String>) -> gl_core::Error {
    gl_core::Error::InvalidInput(format!("policy: {}", message.into()))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum Decision {
    Pass,
    Review,
    Fail,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
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
#[serde(deny_unknown_fields)]
pub struct DeterminismPolicy {
    pub minimum_to_decide: MinimumDeterminism,
}

impl Default for DeterminismPolicy {
    fn default() -> Self {
        DeterminismPolicy { minimum_to_decide: MinimumDeterminism::Reproducible }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Threshold {
    /// Scores at or above this count as support.
    pub support_min: f64,
    /// Half-width of the review band around `support_min`.
    #[serde(default)]
    pub guard_band: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DecisionRules {
    /// A `Contradicted` from any of these verifiers (glob `prefix.*`
    /// allowed) fails the whole answer.
    #[serde(default)]
    pub any_contradiction_from: Vec<String>,
    /// An `Unsupported` from any of these verifiers (glob allowed) sends the
    /// claim to review: the verifier could not establish what it checks, for
    /// example a figure whose passage does not state its provenance.
    /// Omitted from the policy hash when empty, so policies written before
    /// this field existed keep their hash.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub unsupported_from: Vec<String>,
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
            unsupported_from: vec![],
            unresolved_claims: Decision::Review,
            conflicts: Decision::Review,
            tolerate_unresolved_kinds: vec![gl_core::ClaimKind::Word],
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RegulatoryControl {
    pub framework: String,
    pub article: String,
    pub control: String,
    #[serde(default)]
    pub requirement: String,
    pub triggered_by: Vec<Decision>,
}

/// What a request must say about what it is about.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScopeRules {
    /// Scope keys every request must carry (`entity`, `contract`...).
    #[serde(default)]
    pub required: Vec<String>,
    /// The decision when a required key is missing. `REVIEW` by default; a
    /// policy may make it `FAIL`, never `PASS`.
    #[serde(default = "review")]
    pub missing_scope: Decision,
}

/// Risk classes sort requests by what an error would cost. A request names
/// its class; a class listed under `mandatory_review` goes to `REVIEW` even
/// when every check passes. A class the policy does not list is an error, so
/// a typo cannot route a request around review.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RiskClasses {
    /// The class of a request that names none.
    pub default: String,
    /// Further classes decided by the checks alone.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub routine: Vec<String>,
    /// Classes that always go to human review.
    #[serde(default)]
    pub mandatory_review: Vec<String>,
}

impl RiskClasses {
    fn knows(&self, class: &str) -> bool {
        self.default == class
            || self.routine.iter().any(|c| c == class)
            || self.mandatory_review.iter().any(|c| c == class)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Policy {
    pub id: String,
    pub version: String,
    /// The shipped baseline this policy was written on top of. Kept in the
    /// resolved policy, so the record says where the defaults came from.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub extends: Option<String>,
    #[serde(default)]
    pub description: String,
    /// What `PASS` means for this application, in one sentence. A decision of
    /// the verifier is not a decision to publish; this says which one it is.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pass_means: Option<String>,
    /// How the documents write numbers. When set, it wins over the request.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub locale: Option<String>,
    /// How a recomputed figure may differ from the one written
    /// ([`ROUNDING_RULES`]). When set, it wins over the request.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub rounding: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub scope: Option<ScopeRules>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub risk_classes: Option<RiskClasses>,
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

/// How deep `extends` may chain. The shipped baselines extend nothing, so
/// one level is all a policy needs; the limit only stops a cycle.
const MAX_EXTENDS_DEPTH: usize = 4;

/// Parse a policy and resolve `extends` against the shipped baselines.
/// Returns the merged YAML document, before it is checked against the schema.
fn resolve_value(text: &str, depth: usize) -> Result<serde_yaml::Value> {
    let value: serde_yaml::Value = serde_yaml::from_str(text).map_err(|e| err(e.to_string()))?;
    let serde_yaml::Value::Mapping(map) = &value else {
        return Err(err("a policy is a YAML mapping"));
    };
    let Some(base_name) = map.get("extends") else {
        return Ok(value);
    };
    let base_name = base_name.as_str().ok_or_else(|| err("extends must name a shipped policy"))?;
    if depth >= MAX_EXTENDS_DEPTH {
        return Err(err(format!("extends is nested more than {MAX_EXTENDS_DEPTH} levels deep")));
    }
    for key in ["id", "version"] {
        if !map.contains_key(key) {
            return Err(err(format!(
                "a policy that extends {base_name} must set its own {key}, so its records are not \
                 mistaken for the baseline's"
            )));
        }
    }
    let base_text = builtin(base_name).ok_or_else(|| {
        let names: Vec<&str> = BUILTIN.iter().map(|(n, _)| *n).collect();
        err(format!("extends {base_name:?}: not a shipped policy; use one of {}", names.join(", ")))
    })?;
    let mut merged = resolve_value(base_text, depth + 1)?;
    merge(&mut merged, value);
    Ok(merged)
}

/// Maps merge key by key; every other value (lists included) replaces.
fn merge(base: &mut serde_yaml::Value, over: serde_yaml::Value) {
    match (base, over) {
        (serde_yaml::Value::Mapping(b), serde_yaml::Value::Mapping(o)) => {
            for (k, v) in o {
                match b.get_mut(&k) {
                    Some(existing) => merge(existing, v),
                    None => {
                        b.insert(k, v);
                    }
                }
            }
        }
        (b, o) => *b = o,
    }
}

impl Policy {
    /// Parse a policy, resolve `extends`, and reject any key the schema does
    /// not know.
    pub fn from_yaml(text: &str) -> Result<Policy> {
        let value = resolve_value(text, 0)?;
        let extends = value.get("extends").and_then(|v| v.as_str()).map(str::to_string);
        let Some(base) = extends else {
            // No baseline: read the text as written, so an error points at
            // the line the author wrote.
            return serde_yaml::from_str(text).map_err(|e| err(e.to_string()));
        };
        // Through text rather than `from_value`: a YAML document read from
        // text takes `version: 3` as the string "3", as policies always have.
        let merged = serde_yaml::to_string(&value).map_err(|e| err(e.to_string()))?;
        serde_yaml::from_str(&merged).map_err(|e| {
            // A line number would point into the merged document, which the
            // author never saw; drop it and say where the keys came from.
            let message = e.to_string();
            let message = message.split(" at line ").next().unwrap_or(&message).to_string();
            err(format!("{message} (in this policy or in {base}, which it extends)"))
        })
    }

    /// A shipped policy, by id.
    pub fn builtin(id: &str) -> Result<Policy> {
        Policy::from_yaml(builtin(id).ok_or_else(|| err(format!("{id:?} is not a shipped policy")))?)
    }

    /// The hash of the resolved policy. This is the value in every record.
    pub fn hash(&self) -> Result<String> {
        gl_core::canonical::content_hash(self)
    }

    /// The resolved policy as YAML: `extends` merged in and every default
    /// written out. Loading this text gives the same policy and the same hash.
    pub fn to_yaml(&self) -> Result<String> {
        serde_yaml::to_string(self).map_err(|e| err(e.to_string()))
    }

    /// The rounding rule the policy sets, if any.
    pub fn rounding(&self) -> Option<&str> {
        self.rounding.as_deref()
    }

    /// Static checks a policy must pass before it can be loaded.
    pub fn lint(&self, known: &[VerifierInfo]) -> Vec<String> {
        let mut problems = Vec::new();
        if let Some(rule) = &self.rounding {
            if !ROUNDING_RULES.contains(&rule.as_str()) {
                problems.push(format!("rounding: unknown rule {rule:?}; use {}", ROUNDING_RULES.join(", ")));
            }
        }
        if let Some(locale) = &self.locale {
            if locale.trim().is_empty() {
                problems.push("locale: empty; remove the key or name a locale".into());
            }
        }
        if let Some(text) = &self.pass_means {
            if text.trim().is_empty() {
                problems.push("pass_means: empty; say what PASS means for this application".into());
            }
        }
        if let Some(scope) = &self.scope {
            if scope.missing_scope == Decision::Pass {
                problems.push("scope.missing_scope: a missing scope key can never PASS".into());
            }
            if scope.required.iter().any(|k| k.trim().is_empty()) {
                problems.push("scope.required: empty key".into());
            }
        }
        if let Some(classes) = &self.risk_classes {
            let mut seen: Vec<&str> = Vec::new();
            for class in classes.routine.iter().chain(&classes.mandatory_review) {
                if seen.contains(&class.as_str()) {
                    problems.push(format!("risk_classes: {class:?} is listed twice"));
                }
                seen.push(class);
            }
            if classes.routine.contains(&classes.default) {
                problems.push(format!(
                    "risk_classes: {:?} is the default; it need not be listed as routine",
                    classes.default
                ));
            }
        }
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
    /// Reasons that concern the whole request rather than one claim: a
    /// missing scope key, a verifier that could not run, a risk class that
    /// requires review. Omitted when empty, so older records keep their hash.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub reasons: Vec<String>,
    /// The risk class the request was decided under, when the policy has them.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub risk_class: Option<String>,
    /// What `PASS` means for this application, copied from the policy.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pass_means: Option<String>,
}

/// What the policy needs to know about the request itself, beyond the
/// evidence: which scope keys it carries and which risk class it names.
#[derive(Debug, Clone, Default)]
pub struct RequestFacts {
    pub scope_keys: Vec<String>,
    pub risk_class: Option<String>,
}

/// Evaluate a policy over an evidence graph, for a request that carries no
/// scope and names no risk class. See [`evaluate_request`].
pub fn evaluate(
    policy: &Policy,
    graph: &EvidenceGraph,
    claim_kinds: &BTreeMap<String, gl_core::ClaimKind>,
) -> Result<PolicyOutcome> {
    evaluate_request(policy, graph, claim_kinds, &RequestFacts::default())
}

/// Evaluate a policy over an evidence graph. Pure function: same graph,
/// same policy, same request facts, same outcome, on any machine.
///
/// Errors only when the request names a risk class the policy does not list.
pub fn evaluate_request(
    policy: &Policy,
    graph: &EvidenceGraph,
    claim_kinds: &BTreeMap<String, gl_core::ClaimKind>,
    facts: &RequestFacts,
) -> Result<PolicyOutcome> {
    let risk_class = match (&policy.risk_classes, &facts.risk_class) {
        (None, None) => None,
        (None, Some(class)) => {
            return Err(err(format!(
                "the request names risk class {class:?} but policy {} defines no risk_classes",
                policy.id
            )))
        }
        (Some(classes), None) => Some(classes.default.clone()),
        (Some(classes), Some(class)) => {
            if !classes.knows(class) {
                return Err(err(format!("policy {} has no risk class {class:?}", policy.id)));
            }
            Some(class.clone())
        }
    };
    let mut request_reasons: Vec<String> = Vec::new();
    let mut request_decision = Decision::Pass;

    if let Some(scope) = &policy.scope {
        for key in &scope.required {
            if !facts.scope_keys.iter().any(|k| k == key) {
                request_decision = request_decision.max(scope.missing_scope);
                request_reasons.push(format!("missing_scope: the request does not say its {key}"));
            }
        }
    }
    for (verifier_id, message) in &graph.failures {
        if policy.verifiers.forbidden.iter().any(|f| glob_matches(f, verifier_id)) {
            continue;
        }
        request_decision = request_decision.max(Decision::Review);
        request_reasons.push(format!("verifier_failed: {verifier_id} could not run: {message}"));
    }
    if let (Some(classes), Some(class)) = (&policy.risk_classes, &risk_class) {
        if classes.mandatory_review.contains(class) {
            request_decision = request_decision.max(Decision::Review);
            request_reasons.push(format!("mandatory_review: risk class {class} always goes to review"));
        }
    }

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
                EvidenceResult::NotApplicable => continue,
                EvidenceResult::Error => {
                    // A claim kind the policy tolerates without a verdict
                    // stays tolerated; any other claim cannot pass on an error.
                    if !policy.decision.tolerate_unresolved_kinds.contains(kind) {
                        decision = decision.max(Decision::Review);
                        reasons
                            .push(format!("{} could not check this claim: {}", e.verifier_id, e.rationale));
                    }
                    continue;
                }
                _ => spoke = true,
            }
            if e.result == EvidenceResult::Contradicted
                && policy.decision.any_contradiction_from.iter().any(|p| glob_matches(p, &e.verifier_id))
            {
                decision = Decision::Fail;
                reasons.push(format!("{} contradicted: {}", e.verifier_id, e.rationale));
                continue;
            }
            if e.result == EvidenceResult::Unsupported
                && policy.decision.unsupported_from.iter().any(|p| glob_matches(p, &e.verifier_id))
            {
                decision = decision.max(Decision::Review);
                reasons.push(format!("{} unsupported: {}", e.verifier_id, e.rationale));
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
    overall = overall.max(request_decision);

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
        reasons: request_reasons,
        risk_class,
        pass_means: policy.pass_means.clone(),
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

    #[test]
    fn unsupported_from_a_listed_verifier_goes_to_review_and_an_empty_list_keeps_the_hash() {
        let rules = "decision:\n  any_contradiction_from: [groundlens.numeric]\n";
        let before = Policy::from_yaml(&format!("{POLICY}{rules}")).unwrap();
        let with_field = Policy::from_yaml(&format!("{POLICY}{rules}  unsupported_from: []\n")).unwrap();
        assert_eq!(
            before.hash().unwrap(),
            with_field.hash().unwrap(),
            "an empty list must not change the hash"
        );

        let policy =
            Policy::from_yaml(&format!("{POLICY}{rules}  unsupported_from: [groundlens.scope]\n")).unwrap();
        let mut graph = EvidenceGraph::default();
        graph.push_verifier(
            info("groundlens.numeric", Determinism::Exact),
            vec![ev("groundlens.numeric", "c0", EvidenceResult::Supported, 1.0, Determinism::Exact)],
        );
        graph.push_verifier(
            info("groundlens.scope", Determinism::Exact),
            vec![ev("groundlens.scope", "c0", EvidenceResult::Unsupported, 0.0, Determinism::Exact)],
        );
        let kinds = BTreeMap::from([("c0".to_string(), ClaimKind::Numeric)]);
        assert_eq!(evaluate(&policy, &graph, &kinds).unwrap().decision, Decision::Review);
        assert_eq!(evaluate(&before, &graph, &kinds).unwrap().decision, Decision::Pass);
    }

    /// One supported numeric claim: every check passes.
    fn passing_graph() -> (EvidenceGraph, BTreeMap<String, ClaimKind>) {
        let mut graph = EvidenceGraph::default();
        graph.push_verifier(
            info("groundlens.numeric", Determinism::Exact),
            vec![ev("groundlens.numeric", "c0", EvidenceResult::Supported, 1.0, Determinism::Exact)],
        );
        (graph, BTreeMap::from([("c0".to_string(), ClaimKind::Numeric)]))
    }

    #[test]
    fn an_unknown_key_is_an_error_at_every_level() {
        for typo in [
            "verifers:\n  required: [groundlens.numeric]\n",
            "verifiers:\n  requird: [groundlens.numeric]\n",
            "decision:\n  any_contradiction_frm: [groundlens.numeric]\n",
            "determinism:\n  minimum: exact\n",
            "thresholds:\n  nli.demo: { support_min: 0.9, guardband: 0.02 }\n",
            "regulatory_mapping:\n  - {framework: x, article: y, control: z, triggered_by: [FAIL], tag: t}\n",
            "scope:\n  require: [entity]\n",
            "risk_classes:\n  default: routine\n  mandatory: [recommendation]\n",
        ] {
            let text = format!("id: t\nversion: 1.0.0\n{typo}");
            let e = Policy::from_yaml(&text).unwrap_err().to_string();
            assert!(e.contains("unknown field"), "{typo:?} gave: {e}");
        }
    }

    #[test]
    fn the_shipped_policies_load_and_their_resolved_yaml_keeps_the_hash() {
        for (id, text) in BUILTIN {
            let policy = Policy::from_yaml(text).unwrap();
            assert_eq!(policy.id, id);
            let again = Policy::from_yaml(&policy.to_yaml().unwrap()).unwrap();
            assert_eq!(policy.hash().unwrap(), again.hash().unwrap(), "{id}");
        }
    }

    #[test]
    fn the_repository_copies_of_the_shipped_policies_are_identical() {
        let root = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");
        let eu = builtin("eu_ai_act_high_risk_v1").unwrap();
        for copy in
            ["policies/eu_ai_act_high_risk_v1.yaml", "python/groundlens/policies/eu_ai_act_high_risk_v1.yaml"]
        {
            let text = std::fs::read_to_string(format!("{root}/{copy}")).unwrap();
            assert_eq!(text, eu, "{copy} differs from crates/gl-policy/policies; edit both");
        }
    }

    #[test]
    fn extends_merges_maps_replaces_lists_and_hashes_the_resolved_policy() {
        let child = "id: credit_desk\nversion: 3.0.0\nextends: eu_ai_act_high_risk_v1\n\
                     rounding: half_even\n\
                     decision:\n  unsupported_from: [groundlens.scope]\n";
        let policy = Policy::from_yaml(child).unwrap();
        let base = Policy::builtin("eu_ai_act_high_risk_v1").unwrap();
        assert_eq!(policy.id, "credit_desk");
        assert_eq!(policy.extends.as_deref(), Some("eu_ai_act_high_risk_v1"));
        assert_eq!(policy.rounding(), Some("half_even"));
        // The map merged: the key not written is inherited ...
        assert_eq!(policy.decision.any_contradiction_from, base.decision.any_contradiction_from);
        // ... and the list written replaced the baseline's list.
        assert_eq!(policy.decision.unsupported_from, ["groundlens.scope"]);
        assert_eq!(policy.regulatory_mapping.len(), base.regulatory_mapping.len());
        // The resolved text is a complete policy with the same hash.
        let resolved = policy.to_yaml().unwrap();
        assert!(resolved.contains("regulatory_mapping"));
        assert_eq!(Policy::from_yaml(&resolved).unwrap().hash().unwrap(), policy.hash().unwrap());
        assert_ne!(policy.hash().unwrap(), base.hash().unwrap());
    }

    #[test]
    fn extends_needs_a_shipped_base_and_its_own_id_and_version() {
        let e = Policy::from_yaml("id: x\nversion: 1\nextends: finance_rag\n").unwrap_err().to_string();
        assert!(e.contains("not a shipped policy"), "{e}");
        let e =
            Policy::from_yaml("version: 1.0.0\nextends: groundlens_default_v1\n").unwrap_err().to_string();
        assert!(e.contains("its own id"), "{e}");
        // A bare number as version reads as text, with or without extends.
        assert_eq!(
            Policy::from_yaml("id: x\nversion: 3\nextends: groundlens_default_v1\n").unwrap().version,
            "3"
        );
        assert_eq!(Policy::from_yaml("id: x\nversion: 3\n").unwrap().version, "3");
    }

    #[test]
    fn a_missing_required_scope_key_goes_to_review_and_never_passes() {
        let policy = Policy::from_yaml(&format!("{POLICY}scope:\n  required: [entity, contract]\n")).unwrap();
        let (graph, kinds) = passing_graph();
        let none = evaluate(&policy, &graph, &kinds).unwrap();
        assert_eq!(none.decision, Decision::Review);
        assert_eq!(none.reasons.len(), 2);
        assert!(none.reasons[0].starts_with("missing_scope"));
        let facts = RequestFacts { scope_keys: vec!["entity".into(), "contract".into()], risk_class: None };
        assert_eq!(evaluate_request(&policy, &graph, &kinds, &facts).unwrap().decision, Decision::Pass);

        let lax =
            Policy::from_yaml(&format!("{POLICY}scope:\n  required: [entity]\n  missing_scope: PASS\n"))
                .unwrap();
        assert_eq!(lax.lint(&[]).len(), 1);
    }

    #[test]
    fn a_mandatory_risk_class_reviews_even_when_every_check_passes() {
        let policy = Policy::from_yaml(&format!(
            "{POLICY}pass_means: may be shown to the analyst\n\
             risk_classes:\n  default: routine\n  routine: [lookup]\n  mandatory_review: [recommendation]\n"
        ))
        .unwrap();
        let (graph, kinds) = passing_graph();
        let facts = |c: &str| RequestFacts { scope_keys: vec![], risk_class: Some(c.into()) };

        let default = evaluate(&policy, &graph, &kinds).unwrap();
        assert_eq!(default.decision, Decision::Pass);
        assert_eq!(default.risk_class.as_deref(), Some("routine"));
        assert_eq!(default.pass_means.as_deref(), Some("may be shown to the analyst"));
        assert_eq!(
            evaluate_request(&policy, &graph, &kinds, &facts("lookup")).unwrap().decision,
            Decision::Pass
        );

        let rec = evaluate_request(&policy, &graph, &kinds, &facts("recommendation")).unwrap();
        assert_eq!(rec.decision, Decision::Review);
        assert!(rec.reasons[0].starts_with("mandatory_review"));

        let typo = evaluate_request(&policy, &graph, &kinds, &facts("recomendation")).unwrap_err();
        assert!(typo.to_string().contains("no risk class"));
        let plain = Policy::from_yaml(POLICY).unwrap();
        assert!(evaluate_request(&plain, &graph, &kinds, &facts("routine")).is_err());
    }

    #[test]
    fn a_verifier_that_could_not_run_is_review_unless_forbidden() {
        let policy = Policy::from_yaml(POLICY).unwrap();
        let (mut graph, kinds) = passing_graph();
        graph.push_failure("llm_judge.x", "timeout");
        assert_eq!(evaluate(&policy, &graph, &kinds).unwrap().decision, Decision::Pass);
        graph.push_failure("groundlens.scope", "bad input");
        let out = evaluate(&policy, &graph, &kinds).unwrap();
        assert_eq!(out.decision, Decision::Review);
        assert!(out.reasons[0].starts_with("verifier_failed: groundlens.scope"));
    }

    #[test]
    fn a_verifier_error_on_a_claim_that_needs_a_verdict_cannot_pass() {
        let policy = Policy::from_yaml(POLICY).unwrap();
        let (mut graph, kinds) = passing_graph();
        graph.push_verifier(
            info("groundlens.intent", Determinism::Exact),
            vec![ev("groundlens.intent", "c0", EvidenceResult::Error, 0.0, Determinism::Exact)],
        );
        assert_eq!(evaluate(&policy, &graph, &kinds).unwrap().decision, Decision::Review);
        // A word claim the policy tolerates without a verdict stays tolerated.
        let words = BTreeMap::from([("c0".to_string(), ClaimKind::Word)]);
        let mut word_graph = EvidenceGraph::default();
        word_graph.push_verifier(info("groundlens.numeric", Determinism::Exact), vec![]);
        word_graph.push_verifier(
            info("groundlens.lexical", Determinism::Exact),
            vec![ev("groundlens.lexical", "c0", EvidenceResult::Error, 0.0, Determinism::Exact)],
        );
        assert_eq!(evaluate(&policy, &word_graph, &words).unwrap().decision, Decision::Pass);
    }

    #[test]
    fn lint_rejects_an_unknown_rounding_rule() {
        let policy = Policy::from_yaml(&format!("{POLICY}rounding: bankers\n")).unwrap();
        assert!(policy.lint(&[])[0].starts_with("rounding"));
        let ok = Policy::from_yaml(&format!("{POLICY}rounding: half_even\nlocale: es-ES\n")).unwrap();
        assert!(ok.lint(&[]).is_empty());
    }

    #[test]
    fn new_keys_left_out_do_not_change_the_hash_of_an_old_policy() {
        // The hash of a 5.3 policy, which predates every key this version
        // added, is pinned: records written under it must keep naming it.
        let eu = Policy::builtin("eu_ai_act_high_risk_v1").unwrap();
        let json = gl_core::canonical::canonical_json(&eu).unwrap();
        for key in ["extends", "pass_means", "locale", "rounding", "scope", "risk_classes"] {
            assert!(!json.contains(&format!("\"{key}\"")), "{key} serialised while absent");
        }
    }
}
