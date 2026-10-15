// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The scope channel. Exact, no model.
//!
//! A request can say what it is about (`entity = UPS`, `contract_version =
//! 3`) and every passage can say where it comes from (its provenance). This
//! verifier answers one question per numeric claim: does the figure the
//! answer uses come from a passage inside the scope?
//!
//! - The figure appears in at least one passage inside the scope: `supported`.
//! - It appears only in passages outside the scope: `contradicted`, with the
//!   note `out_of_scope_source`. This is the costly error we measured most
//!   often: a real figure from another company, contract or version.
//! - It appears only in passages whose provenance does not state the scope
//!   key: `unsupported`, with the note `provenance_missing`.
//! - It appears in no passage: `not_applicable`. The numeric verifier speaks
//!   to that case.
//!
//! Figures are located by their bare numeral, ignoring scale words and
//! units, because the question here is where a figure comes from; whether it
//! is the right figure is the numeric verifier's question.
//!
//! A passage is inside the scope when, for every scope key its provenance
//! states, the value is the same. A passage that states none of the scope
//! keys has unknown provenance. With an empty scope the verifier says nothing.

use gl_core::{
    ClaimKind, Determinism, Evidence, EvidenceResult, Receipt, Result, Score, Source, Span,
    VerificationInput, Verifier, VerifierInfo, VerifierKind,
};
use gl_numeric::{compare, find_bare_numerals, find_quantities, locale, Match, MatchOptions};

pub const ID: &str = "groundlens.scope";
pub const VERSION: &str = "1.1.0";

/// Where a passage stands against the request's scope.
#[derive(Debug, Clone, PartialEq, Eq)]
enum Standing {
    Inside,
    /// The first scope key whose value differs: `(key, scope value, passage value)`.
    Outside(String, String, String),
    Unknown,
}

fn standing(source: &Source, input: &VerificationInput) -> Standing {
    let mut stated = false;
    for (key, wanted) in &input.scope {
        if let Some(found) = source.provenance.get(key) {
            stated = true;
            if found.trim() != wanted.trim() {
                return Standing::Outside(key.clone(), wanted.clone(), found.clone());
            }
        }
    }
    if stated {
        Standing::Inside
    } else {
        Standing::Unknown
    }
}

pub struct ScopeVerifier {
    info: VerifierInfo,
}

impl Default for ScopeVerifier {
    fn default() -> Self {
        Self::new()
    }
}

impl ScopeVerifier {
    pub fn new() -> Self {
        ScopeVerifier {
            info: VerifierInfo {
                id: ID.to_string(),
                version: VERSION.to_string(),
                kind: VerifierKind::Exact,
                determinism: Determinism::Exact,
                applies_to: vec![ClaimKind::Numeric],
                artefacts: vec![],
                needs_network: false,
            },
        }
    }
}

impl Verifier for ScopeVerifier {
    fn info(&self) -> &VerifierInfo {
        &self.info
    }

    fn verify(&self, input: &VerificationInput) -> Result<Vec<Evidence>> {
        // A short bare number ("2.3", "15") turns up in some passage by
        // chance: a difference the answer computed is not evidence that it
        // came from another company. A bare figure needs three or more
        // significant digits to be a contradiction; one with a unit or a
        // scale word ("$1.9 billion") does not.
        const MIN_DIGITS_OUT_OF_SCOPE: u32 = 3;
        if input.scope.is_empty() {
            return Ok(Vec::new());
        }
        let profile = locale(&input.locale)
            .ok_or_else(|| gl_core::Error::InvalidInput(format!("unknown locale {:?}", input.locale)))?;
        // Bare numerals on purpose: this channel asks where a figure comes
        // from, not whether it is right, and tables often state the scale
        // once in a header ("in millions") while the answer repeats it.
        let find = |text: &str| find_bare_numerals(text, &profile);

        let passages: Vec<(&Source, Standing, Vec<gl_numeric::Quantity>)> =
            input.sources.iter().map(|s| (s, standing(s, input), find(&s.text))).collect();

        let mut out = Vec::new();
        for claim in input.claims.iter().filter(|c| c.kind == ClaimKind::Numeric) {
            let Some(answer_q) = find(&claim.text).into_iter().next() else {
                continue;
            };
            // Every passage where the figure appears exactly, in passage order.
            let mut inside: Option<(&Source, Span)> = None;
            let mut outside: Option<(&Source, Span, &Standing)> = None;
            let mut unknown: Option<(&Source, Span)> = None;
            for (source, standing, quantities) in &passages {
                let Some(q) = quantities
                    .iter()
                    .find(|q| compare(&answer_q, q, MatchOptions::default()) == Match::Exact)
                else {
                    continue;
                };
                let span = Span::new(q.span.start, q.span.end);
                match standing {
                    Standing::Inside if inside.is_none() => inside = Some((source, span)),
                    Standing::Outside(..) if outside.is_none() => outside = Some((source, span, standing)),
                    Standing::Unknown if unknown.is_none() => unknown = Some((source, span)),
                    _ => {}
                }
            }

            let receipt = |source: &Source, span: Span, notes: Vec<String>| Receipt {
                source_id: Some(source.id.clone()),
                source_span: Some(span),
                source_text: source.text.get(span.start..span.end).map(str::to_string),
                notes,
            };
            let (result, score, rationale, receipt) = if let Some((s, span)) = inside {
                (
                    EvidenceResult::Supported,
                    1.0,
                    format!("{} found in {}, inside the request scope", claim.text, s.id),
                    receipt(s, span, vec![]),
                )
            } else if let Some((s, span, Standing::Outside(key, wanted, found))) = outside.filter(|_| {
                answer_q.numeral.significant_digits >= MIN_DIGITS_OUT_OF_SCOPE
                    || find_quantities(&claim.text, &profile).first().is_some_and(|q| {
                        q.scale_exponent > 0 || *q.dimension() != gl_numeric::Dimension::Dimensionless
                    })
            }) {
                (
                    EvidenceResult::Contradicted,
                    0.0,
                    format!(
                        "{} found only in {}, outside the request scope ({key} is {found}, the request is about {wanted})",
                        claim.text, s.id
                    ),
                    receipt(s, span, vec!["out_of_scope_source".into()]),
                )
            } else if let Some((s, span)) = unknown {
                (
                    EvidenceResult::Unsupported,
                    0.0,
                    format!(
                        "{} found only in {}, whose provenance does not state the scope",
                        claim.text, s.id
                    ),
                    receipt(s, span, vec!["provenance_missing".into()]),
                )
            } else {
                continue;
            };
            out.push(Evidence {
                verifier_id: ID.into(),
                verifier_version: VERSION.into(),
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

#[cfg(test)]
mod tests {
    use super::*;

    fn src(id: &str, text: &str, provenance: &[(&str, &str)]) -> Source {
        Source {
            id: id.into(),
            text: gl_text::normalise(text),
            locator: None,
            provenance: provenance.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect(),
        }
    }

    fn input(answer: &str, sources: Vec<Source>, scope: &[(&str, &str)]) -> VerificationInput {
        let answer = gl_text::normalise(answer);
        VerificationInput {
            question: None,
            claims: crate::extract_claims(&answer, "en"),
            answer,
            sources,
            locale: "en".into(),
            metadata: Default::default(),
            scope: scope.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect(),
        }
    }

    fn results(input: &VerificationInput) -> Vec<(EvidenceResult, Vec<String>)> {
        ScopeVerifier::default()
            .verify(input)
            .unwrap()
            .into_iter()
            .map(|e| (e.result, e.receipt.notes))
            .collect()
    }

    #[test]
    fn a_figure_from_another_entity_is_contradicted() {
        let i = input(
            "The 2006 tax expense was $1.9 billion.",
            vec![
                src("ip-75", "The tax provision was $1.9 billion.", &[("entity", "IP")]),
                src("aapl-100", "Provision for income taxes was $829 million.", &[("entity", "AAPL")]),
            ],
            &[("entity", "AAPL")],
        );
        assert_eq!(results(&i), vec![(EvidenceResult::Contradicted, vec!["out_of_scope_source".into()])]);
    }

    #[test]
    fn a_short_bare_figure_found_only_outside_is_not_a_contradiction() {
        // "2.3" is a difference the answer computed; that another company's
        // passage happens to contain 2.3 says nothing about where it came from.
        let i = input(
            "Earnings rose from $32.8 million to $35.1 million, a gain of 2.3.",
            vec![
                src(
                    "dre-15",
                    "earnings from service operations $ 35.1 million and $ 32.8 million",
                    &[("entity", "DRE")],
                ),
                src("aes-44", "a ratio of 2.3 times", &[("entity", "AES")]),
            ],
            &[("entity", "DRE")],
        );
        assert!(results(&i).iter().all(|r| r.0 != EvidenceResult::Contradicted), "{:?}", results(&i));
    }

    #[test]
    fn a_figure_found_inside_the_scope_is_supported_even_if_it_also_appears_outside() {
        let i = input(
            "Free cash flow was $487 million.",
            vec![
                src("other", "Free cash flow was $487 million.", &[("entity", "K")]),
                src("unp", "free cash flow | $ 487 | $ 516", &[("entity", "UNP")]),
            ],
            &[("entity", "UNP")],
        );
        assert_eq!(results(&i), vec![(EvidenceResult::Supported, vec![])]);
    }

    #[test]
    fn a_figure_only_in_passages_without_provenance_is_unsupported() {
        let i = input(
            "Revenue was 10 million euros.",
            vec![src("s", "Revenue was 10 million euros.", &[])],
            &[("entity", "ACME")],
        );
        assert_eq!(results(&i), vec![(EvidenceResult::Unsupported, vec!["provenance_missing".into()])]);
    }

    #[test]
    fn every_stated_scope_key_must_match() {
        let i = input(
            "The deductible is 500 euros.",
            vec![src(
                "policy-v2",
                "The deductible is 500 euros.",
                &[("contract", "P-1"), ("contract_version", "2")],
            )],
            &[("contract", "P-1"), ("contract_version", "3")],
        );
        assert_eq!(results(&i), vec![(EvidenceResult::Contradicted, vec!["out_of_scope_source".into()])]);
    }

    #[test]
    fn no_scope_means_no_evidence_and_a_missing_figure_is_left_to_the_numeric_verifier() {
        let no_scope = input("Revenue was 7 million.", vec![src("s", "Revenue was 7 million.", &[])], &[]);
        assert!(results(&no_scope).is_empty());
        let absent = input(
            "Revenue was 9 million.",
            vec![src("s", "Revenue was 7 million.", &[("entity", "A")])],
            &[("entity", "A")],
        );
        assert!(results(&absent).is_empty());
    }
}
