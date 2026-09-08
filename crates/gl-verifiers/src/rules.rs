//! Symbolic rules. Logic the organisation writes, not the engine.
//!
//! A rule looks at claims (kind, attributes, text) and at the answer, and
//! emits evidence. It never looks at other verifiers' evidence: composing
//! evidence is the policy's job. Keeping the two apart is what lets a rule
//! set be versioned, hashed and reviewed on its own.
//!
//! ```yaml
//! id: es_banking_v1
//! version: 1.0.0
//! rules:
//!   - id: no_apr_without_percent
//!     description: "An APR must be stated as a percentage"
//!     scope: { claim_kind: numeric }
//!     when: { text_matches: "(?i)\\bTAE\\b|\\bAPR\\b" }
//!     unless: { attribute: { dimension: percent } }
//!     emit: contradicted
//!   - id: currency_claims_need_currency
//!     scope: { claim_kind: numeric, attribute: { dimension: dimensionless } }
//!     when: { answer_matches: "(?i)euros?|€|dólares|\\$" }
//!     emit: unsupported
//! ```

use gl_core::{
    ClaimKind, Determinism, Evidence, EvidenceResult, Receipt, Result, Score, VerificationInput, Verifier,
    VerifierInfo, VerifierKind,
};
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const ID: &str = "groundlens.rules";

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Scope {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub claim_kind: Option<ClaimKind>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub attribute: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Condition {
    /// Regex over the claim text.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub text_matches: Option<String>,
    /// Regex over the whole answer.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub answer_matches: Option<String>,
    /// Regex that must match some source.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_matches: Option<String>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub attribute: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RuleAction {
    Supported,
    Unsupported,
    Contradicted,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Rule {
    pub id: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub scope: Scope,
    #[serde(default)]
    pub when: Condition,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub unless: Option<Condition>,
    pub emit: RuleAction,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuleSet {
    pub id: String,
    pub version: String,
    pub rules: Vec<Rule>,
}

impl RuleSet {
    /// Rule sets are exchanged as JSON at this layer. The CLI accepts YAML
    /// and converts it before handing the set over, so JSON is what gets
    /// hashed into records.
    pub fn from_json(text: &str) -> Result<RuleSet> {
        serde_json::from_str::<RuleSet>(text)
            .map_err(|e| gl_core::Error::InvalidInput(format!("rule set: {e}")))
    }

    /// Compile every regex once. Fails early on an invalid pattern, which is
    /// what you want from a rule set that will be hashed into records.
    pub fn compile(self) -> Result<RulesVerifier> {
        RulesVerifier::new(self)
    }
}

struct CompiledCondition {
    text: Option<Regex>,
    answer: Option<Regex>,
    source: Option<Regex>,
    attribute: BTreeMap<String, String>,
}

impl CompiledCondition {
    fn compile(c: &Condition) -> Result<Self> {
        let rx = |p: &Option<String>| -> Result<Option<Regex>> {
            p.as_deref()
                .map(|p| {
                    Regex::new(p).map_err(|e| gl_core::Error::InvalidInput(format!("bad regex {p:?}: {e}")))
                })
                .transpose()
        };
        Ok(CompiledCondition {
            text: rx(&c.text_matches)?,
            answer: rx(&c.answer_matches)?,
            source: rx(&c.source_matches)?,
            attribute: c.attribute.clone(),
        })
    }

    fn holds(&self, claim: &gl_core::Claim, input: &VerificationInput) -> bool {
        if let Some(r) = &self.text {
            if !r.is_match(&claim.text) {
                return false;
            }
        }
        if let Some(r) = &self.answer {
            if !r.is_match(&input.answer) {
                return false;
            }
        }
        if let Some(r) = &self.source {
            if !input.sources.iter().any(|s| r.is_match(&s.text)) {
                return false;
            }
        }
        self.attribute.iter().all(|(k, v)| claim.attributes.get(k).is_some_and(|a| a == v || v == "*"))
    }
}

struct CompiledRule {
    rule: Rule,
    when: CompiledCondition,
    unless: Option<CompiledCondition>,
}

pub struct RulesVerifier {
    info: VerifierInfo,
    rules: Vec<CompiledRule>,
}

impl RulesVerifier {
    pub fn new(set: RuleSet) -> Result<Self> {
        let hash = gl_core::canonical::content_hash(&set)?;
        let mut rules = Vec::new();
        for r in &set.rules {
            rules.push(CompiledRule {
                when: CompiledCondition::compile(&r.when)?,
                unless: r.unless.as_ref().map(CompiledCondition::compile).transpose()?,
                rule: r.clone(),
            });
        }
        Ok(RulesVerifier {
            info: VerifierInfo {
                id: format!("{ID}.{}", set.id),
                version: set.version.clone(),
                kind: VerifierKind::Symbolic,
                determinism: Determinism::Exact,
                applies_to: vec![
                    ClaimKind::Numeric,
                    ClaimKind::Temporal,
                    ClaimKind::Entity,
                    ClaimKind::Citation,
                    ClaimKind::Statement,
                    ClaimKind::Word,
                ],
                artefacts: vec![("ruleset".to_string(), hash)],
                needs_network: false,
            },
            rules,
        })
    }
}

impl Verifier for RulesVerifier {
    fn info(&self) -> &VerifierInfo {
        &self.info
    }

    fn verify(&self, input: &VerificationInput) -> Result<Vec<Evidence>> {
        let mut out: Vec<Evidence> = Vec::new();
        for claim in &input.claims {
            // First matching rule per claim wins; rule order is part of the
            // rule set and therefore of its hash.
            for cr in &self.rules {
                let scope = &cr.rule.scope;
                if scope.claim_kind.is_some_and(|k| k != claim.kind) {
                    continue;
                }
                if !scope
                    .attribute
                    .iter()
                    .all(|(k, v)| claim.attributes.get(k).is_some_and(|a| a == v || v == "*"))
                {
                    continue;
                }
                if !cr.when.holds(claim, input) {
                    continue;
                }
                if cr.unless.as_ref().is_some_and(|u| u.holds(claim, input)) {
                    continue;
                }
                let (result, score) = match cr.rule.emit {
                    RuleAction::Supported => (EvidenceResult::Supported, 1.0),
                    RuleAction::Unsupported => (EvidenceResult::Unsupported, 0.0),
                    RuleAction::Contradicted => (EvidenceResult::Contradicted, 0.0),
                };
                out.push(Evidence {
                    verifier_id: self.info.id.clone(),
                    verifier_version: self.info.version.clone(),
                    claim_id: claim.id.clone(),
                    result,
                    score: Score(score),
                    confidence: Score(1.0),
                    determinism: Determinism::Exact,
                    rationale: format!("rule {}: {}", cr.rule.id, cr.rule.description),
                    receipt: Receipt { notes: vec![format!("rule:{}", cr.rule.id)], ..Default::default() },
                    model_hash: None,
                    calibration_id: None,
                });
                break;
            }
        }
        out.sort_by_key(|e| e.sort_key());
        Ok(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::extract_claims;
    use gl_core::Source;

    #[test]
    fn a_rule_fires_on_scope_and_condition() {
        let set: RuleSet = serde_json::from_str(
            r#"{
            "id": "demo", "version": "1.0.0",
            "rules": [{
                "id": "apr_must_be_percent",
                "description": "an APR is a percentage",
                "scope": {"claim_kind": "numeric"},
                "when": {"answer_matches": "(?i)\\bAPR\\b"},
                "unless": {"attribute": {"dimension": "percent"}},
                "emit": "contradicted"
            }]
        }"#,
        )
        .unwrap();
        let v = set.compile().unwrap();
        let answer = "The APR is 4.75 and the term is 30 days.";
        let input = VerificationInput {
            question: None,
            answer: answer.into(),
            sources: vec![Source { id: "s".into(), text: "".into(), locator: None }],
            claims: extract_claims(answer, "en"),
            locale: "en".into(),
            metadata: Default::default(),
        };
        let ev = v.verify(&input).unwrap();
        assert_eq!(ev.len(), 2);
        assert!(ev.iter().all(|e| e.result == EvidenceResult::Contradicted));
        assert!(v.info().artefacts[0].1.starts_with("sha256:"));
    }
}
