// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The exact channel. Support is 1.0 or 0.0. Similarity is not allowed to
//! vote. What is new against groundlens 3.x: scale words, currencies,
//! percentages and physical units are compared in a canonical base unit, and
//! two named relaxations can be switched on by configuration (and therefore
//! by policy), each one leaving a note on the receipt.

use gl_core::{
    ClaimKind, Determinism, Evidence, EvidenceResult, Receipt, Result, Score, Span, VerificationInput,
    Verifier, VerifierInfo, VerifierKind,
};
use gl_numeric::{compare, find_bare_numerals, find_quantities, locale, Match, MatchOptions, Quantity};
use serde::{Deserialize, Serialize};

pub const ID: &str = "groundlens.numeric";
pub const VERSION: &str = "1.0.0";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NumericConfig {
    #[serde(default)]
    pub matching: MatchOptions,
    /// Attach scale words, currencies, percent and physical units and compare
    /// in base units. `false` gives groundlens 3.x semantics (bare numbers).
    #[serde(default = "default_true")]
    pub units: bool,
}

fn default_true() -> bool {
    true
}

impl Default for NumericConfig {
    fn default() -> Self {
        NumericConfig { matching: MatchOptions::default(), units: true }
    }
}

pub struct NumericVerifier {
    info: VerifierInfo,
    config: NumericConfig,
}

impl Default for NumericVerifier {
    fn default() -> Self {
        Self::new(NumericConfig::default())
    }
}

impl NumericVerifier {
    pub fn new(config: NumericConfig) -> Self {
        NumericVerifier {
            info: VerifierInfo {
                id: ID.to_string(),
                version: VERSION.to_string(),
                kind: VerifierKind::Exact,
                determinism: Determinism::Exact,
                applies_to: vec![ClaimKind::Numeric],
                artefacts: vec![],
                needs_network: false,
            },
            config,
        }
    }
}

struct SourceQuantity<'a> {
    source_id: &'a str,
    quantity: Quantity,
}

impl Verifier for NumericVerifier {
    fn info(&self) -> &VerifierInfo {
        &self.info
    }

    fn verify(&self, input: &VerificationInput) -> Result<Vec<Evidence>> {
        let profile = locale(&input.locale)
            .ok_or_else(|| gl_core::Error::InvalidInput(format!("unknown locale {:?}", input.locale)))?;

        let find = |text: &str| {
            if self.config.units {
                find_quantities(text, &profile)
            } else {
                find_bare_numerals(text, &profile)
            }
        };
        let source_quantities: Vec<SourceQuantity> = input
            .sources
            .iter()
            .flat_map(|s| {
                find(&s.text).into_iter().map(move |quantity| SourceQuantity { source_id: &s.id, quantity })
            })
            .collect();

        let question_quantities: Vec<Quantity> = input.question.as_deref().map(&find).unwrap_or_default();

        let mut out = Vec::new();
        for claim in input.claims.iter().filter(|c| c.kind == ClaimKind::Numeric) {
            let Some(answer_q) = find(&claim.text).into_iter().next() else {
                continue;
            };

            let mut best: Option<(&SourceQuantity, Match)> = None;
            for sq in &source_quantities {
                let m = compare(&answer_q, &sq.quantity, self.config.matching);
                let better = match (&best, &m) {
                    (None, _) => true,
                    (Some((_, b)), m) => rank(m) < rank(b) || (rank(m) == rank(b) && closer(m, b)),
                };
                if better {
                    best = Some((sq, m));
                }
                if matches!(best, Some((_, Match::Exact))) {
                    break;
                }
            }

            let mut notes: Vec<String> = answer_q.notes.iter().map(|n| n.to_string()).collect();
            if answer_q.numeral.ambiguous() {
                notes.push("numeral_ambiguous".into());
            }
            if question_quantities
                .iter()
                .any(|qq| compare(&answer_q, qq, MatchOptions::default()) == Match::Exact)
            {
                notes.push("echoes_question".into());
            }

            let (result, score, rationale, receipt) = match best {
                None => (
                    EvidenceResult::Unsupported,
                    0.0,
                    format!("{} : no numeral in any source", claim.text),
                    Receipt { notes: notes.clone(), ..Default::default() },
                ),
                Some((sq, m)) => {
                    let mut receipt = Receipt {
                        source_id: Some(sq.source_id.to_string()),
                        source_span: Some(Span::new(sq.quantity.span.start, sq.quantity.span.end)),
                        source_text: Some(input_source_text(input, sq.source_id, sq.quantity.span)),
                        notes: notes.clone(),
                    };
                    match &m {
                        Match::Exact => {
                            let shown = receipt.source_text.clone().unwrap_or_default();
                            (
                                EvidenceResult::Supported,
                                1.0,
                                format!(
                                    "{} = {} in {} ({})",
                                    claim.text,
                                    shown,
                                    sq.source_id,
                                    sq.quantity.canonical_text()
                                ),
                                receipt,
                            )
                        }
                        Match::AtDeclaredPrecision { significant_digits } => {
                            receipt.notes.push("matches_at_declared_precision".into());
                            (
                                EvidenceResult::Supported,
                                1.0,
                                format!(
                                    "{} matches {} at {} significant digits",
                                    claim.text,
                                    sq.quantity.canonical_text(),
                                    significant_digits
                                ),
                                receipt,
                            )
                        }
                        Match::PercentAsFraction => {
                            receipt.notes.push("percent_as_fraction".into());
                            (
                                EvidenceResult::Supported,
                                1.0,
                                format!(
                                    "{} matches {} read as a fraction",
                                    claim.text,
                                    sq.quantity.canonical_text()
                                ),
                                receipt,
                            )
                        }
                        Match::Different { relative_distance } => (
                            EvidenceResult::Contradicted,
                            0.0,
                            format!(
                                "{} not in sources; nearest {} in {} (relative distance {})",
                                claim.text,
                                sq.quantity.canonical_text(),
                                sq.source_id,
                                relative_distance.round_dp(3)
                            ),
                            receipt,
                        ),
                        Match::DimensionMismatch => {
                            receipt.notes.push("dimension_mismatch".into());
                            (
                                EvidenceResult::Unsupported,
                                0.0,
                                format!("{} has no source value of the same dimension", claim.text),
                                receipt,
                            )
                        }
                    }
                }
            };

            out.push(Evidence {
                verifier_id: ID.to_string(),
                verifier_version: VERSION.to_string(),
                claim_id: claim.id.clone(),
                result,
                score: Score(score),
                confidence: Score(1.0),
                determinism: Determinism::Exact,
                rationale,
                receipt,
                model_hash: None,
                calibration_id: None,
            });
        }
        out.sort_by_key(|e| e.sort_key());
        Ok(out)
    }
}

fn rank(m: &Match) -> u8 {
    match m {
        Match::Exact => 0,
        Match::AtDeclaredPrecision { .. } => 1,
        Match::PercentAsFraction => 2,
        Match::Different { .. } => 3,
        Match::DimensionMismatch => 4,
    }
}

fn closer(a: &Match, b: &Match) -> bool {
    match (a, b) {
        (Match::Different { relative_distance: x }, Match::Different { relative_distance: y }) => x < y,
        _ => false,
    }
}

fn input_source_text(input: &VerificationInput, id: &str, span: Span) -> String {
    input
        .sources
        .iter()
        .find(|s| s.id == id)
        .map(|s| s.text[span.start..span.end].to_string())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::extract_claims;
    use gl_core::Source;

    fn input(answer: &str, source: &str, question: Option<&str>) -> VerificationInput {
        let answer = gl_text::normalise(answer);
        VerificationInput {
            question: question.map(str::to_string),
            claims: extract_claims(&answer, "en"),
            answer,
            sources: vec![Source {
                id: "invoice.pdf#p1".into(),
                text: gl_text::normalise(source),
                locator: None,
            }],
            locale: "en".into(),
            metadata: Default::default(),
        }
    }

    #[test]
    fn ten_is_not_a_hundred_with_receipt() {
        let v = NumericVerifier::default();
        let ev = v
            .verify(&input(
                "The invoice total is 1,000 dollars, due in 30 days.",
                "...the total amount due is 10,000 dollars, payable within 30 days...",
                Some("What is the invoice total?"),
            ))
            .unwrap();
        assert_eq!(ev.len(), 2);
        let wrong = &ev[0];
        assert_eq!(wrong.result, EvidenceResult::Contradicted);
        assert_eq!(wrong.score.0, 0.0);
        assert_eq!(wrong.receipt.source_text.as_deref(), Some("10,000 dollars"));
        assert_eq!(ev[1].result, EvidenceResult::Supported);
    }

    #[test]
    fn units_are_resolved_before_comparison() {
        let v = NumericVerifier::default();
        let ev = v
            .verify(&input("Revenue was $37.35 billion.", "Revenue (in millions): 37,350 dollars", None))
            .unwrap();
        assert_eq!(ev[0].result, EvidenceResult::Supported);
        let ev = v.verify(&input("The line is 1.2 km long.", "line length: 1200 m", None)).unwrap();
        assert_eq!(ev[0].result, EvidenceResult::Supported);
    }
}
