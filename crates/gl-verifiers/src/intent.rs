// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The intent channel: does the answer give the kind of figure the question
//! asked for? Deterministic, no model, and a heuristic, so it never fails an
//! answer on its own: the shipped policies send its `unsupported` to review.
//!
//! It reads two things from the question.
//!
//! - **The kind of figure.** "What percentage…", "what portion…", "what was
//!   the growth rate…" ask for a percentage or a fraction. "How much…", "in
//!   millions" and "what was the total…" ask for an amount. "How many…" asks
//!   for a count. A question with none of these signals asks for nothing this
//!   channel can check, and it says nothing.
//! - **The unit.** "in euros", "in millions of dollars", "en kilómetros". When
//!   the question names a currency or a physical unit, the figure must carry
//!   it: a different unit is `unit_mismatch`, no unit at all is
//!   `unit_missing`.
//!
//! The figure checked is the answer's last figure that is not a year: answers
//! that show their work end with the result ("Therefore … was 213.45 %").
//! Evidence is attached to that figure's claim: `supported` when it is the
//! kind asked for, `unsupported` with a note when it is not.

use gl_core::{
    ClaimKind, Determinism, Evidence, EvidenceResult, Receipt, Result, Score, VerificationInput, Verifier,
    VerifierInfo, VerifierKind,
};
use gl_numeric::{find_quantities, locale, units::unit_for, Dimension, Quantity};
use regex::Regex;
use std::sync::OnceLock;

pub const ID: &str = "groundlens.intent";
pub const VERSION: &str = "1.1.0";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Kind {
    Percent,
    Amount,
    Count,
}

impl Kind {
    fn name(self) -> &'static str {
        match self {
            Kind::Percent => "a percentage",
            Kind::Amount => "an amount",
            Kind::Count => "a count",
        }
    }
    fn code(self) -> &'static str {
        match self {
            Kind::Percent => "percent",
            Kind::Amount => "amount",
            Kind::Count => "count",
        }
    }
}

fn percent_signals() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(
            r"(?xi)
            %
          | \bpercent(age)?s?\b | \bportion\b | \bproportion\b | \bshare\s+of\b | \bratio\b
          | \b(growth|return|change|decline|increase|decrease)\s+rate\b | \brate\s+of\s+(growth|change|return)\b
          | \bporcentaje\b | \bpor\s+ciento\b | \bproporci[oó]n\b | \bpercentatge\b
          | \bpourcentage\b | \bprozent | \bpercentuale\b | \bpercentagem\b
            ",
        )
        .expect("percent signals")
    })
}

fn amount_signals() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(
            r"(?xi)
            \bhow\s+much\b | \bin\s+(millions|thousands|billions)\b | \btotal\b | \bamount\b
          | \bcu[aá]nto\b | \bimporte\b | \ben\s+(millones|miles)\b | \bcombien\b | \bwie\s+viel\b
            ",
        )
        .expect("amount signals")
    })
}

fn count_signals() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r"(?xi) \bhow\s+many\b | \bcu[aá]nt[oa]s\b | \bwie\s+viele\b | \bnumber\s+of\b")
            .expect("count")
    })
}

fn asked_kind(question: &str) -> Option<Kind> {
    if percent_signals().is_match(question) {
        Some(Kind::Percent)
    } else if count_signals().is_match(question) {
        Some(Kind::Count)
    } else if amount_signals().is_match(question) {
        Some(Kind::Amount)
    } else {
        None
    }
}

/// A currency or physical unit the question names after "in", "en", "of" or
/// "de": "in euros", "in millions of dollars", "en kilómetros".
fn asked_unit(question: &str) -> Option<(String, Dimension)> {
    let lower = question.to_lowercase();
    let words: Vec<&str> = lower
        .split(|c: char| !(c.is_alphanumeric() || matches!(c, '$' | '€' | '£' | '¥')))
        .filter(|w| !w.is_empty())
        .collect();
    for (i, w) in words.iter().enumerate() {
        let lead = words[i.saturating_sub(3)..i]
            .iter()
            .any(|p| matches!(*p, "in" | "en" | "of" | "de" | "measured"));
        // One-letter units ("m", "t", "g") are too ambiguous in prose.
        let long_enough = w.chars().count() > 1 || matches!(*w, "$" | "€" | "£" | "¥");
        if !lead || !long_enough {
            continue;
        }
        if let Some(unit) = unit_for(w) {
            if !matches!(unit.dimension, Dimension::Dimensionless | Dimension::Percent) {
                return Some((w.to_string(), unit.dimension));
            }
        }
    }
    None
}

fn dimension_name(d: &Dimension) -> String {
    match d {
        Dimension::Currency(code) => code.clone(),
        other => format!("{other:?}").to_lowercase(),
    }
}

pub struct IntentVerifier {
    info: VerifierInfo,
}

impl Default for IntentVerifier {
    fn default() -> Self {
        Self::new()
    }
}

impl IntentVerifier {
    pub fn new() -> Self {
        IntentVerifier {
            info: VerifierInfo {
                id: ID.to_string(),
                version: VERSION.to_string(),
                kind: VerifierKind::Symbolic,
                determinism: Determinism::Exact,
                applies_to: vec![ClaimKind::Numeric],
                artefacts: vec![],
                needs_network: false,
            },
        }
    }
}

impl Verifier for IntentVerifier {
    fn info(&self) -> &VerifierInfo {
        &self.info
    }

    fn verify(&self, input: &VerificationInput) -> Result<Vec<Evidence>> {
        let Some(question) = input.question.as_deref().filter(|q| !q.trim().is_empty()) else {
            return Ok(Vec::new());
        };
        let kind = asked_kind(question);
        let unit = asked_unit(question);
        if kind.is_none() && unit.is_none() {
            return Ok(Vec::new());
        }
        let profile = locale(&input.locale)
            .ok_or_else(|| gl_core::Error::InvalidInput(format!("unknown locale {:?}", input.locale)))?;

        // The answer's last figure that is not a year.
        let last = input
            .claims
            .iter()
            .filter(|c| c.kind == ClaimKind::Numeric)
            .filter_map(|c| find_quantities(&c.text, &profile).into_iter().next().map(|q| (c, q)))
            .rfind(|(_, q)| !crate::numeric::is_year(q));
        let Some((claim, figure)) = last else {
            return Ok(Vec::new());
        };

        let given = figure.dimension().clone();
        let mut problems: Vec<(String, String)> = Vec::new();
        if let Some(k) = kind {
            let fits = match k {
                Kind::Percent => fraction_like(&figure),
                Kind::Amount | Kind::Count => given != Dimension::Percent,
            };
            if !fits {
                problems.push((
                    format!(
                        "the question asks for {}; the answer's figure {} is {}",
                        k.name(),
                        claim.text,
                        describe(&given)
                    ),
                    "intent_mismatch".into(),
                ));
            }
        }
        if let Some((word, wanted)) = &unit {
            if given == Dimension::Dimensionless {
                problems.push((
                    format!("the question asks for {word}; the answer's figure {} has no unit", claim.text),
                    "unit_missing".into(),
                ));
            } else if given == Dimension::Percent && kind != Some(Kind::Percent) {
                // "What was revenue in euros?" answered with "12 %": a share
                // where an amount in a unit was asked. A question that asks
                // for a percentage keeps its percentage.
                problems.push((
                    format!(
                        "the question asks for {word} ({}); the answer's figure {} is a percentage",
                        dimension_name(wanted),
                        claim.text
                    ),
                    "unit_mismatch".into(),
                ));
            } else if given != *wanted && given != Dimension::Percent {
                problems.push((
                    format!(
                        "the question asks for {word} ({}); the answer's figure {} is in {}",
                        dimension_name(wanted),
                        claim.text,
                        dimension_name(&given)
                    ),
                    "unit_mismatch".into(),
                ));
            }
        }

        let asked: Vec<String> = kind
            .map(|k| format!("asked:{}", k.code()))
            .into_iter()
            .chain(unit.as_ref().map(|(_, d)| format!("asked_unit:{}", dimension_name(d))))
            .collect();
        let (result, score, rationale, mut notes) = if problems.is_empty() {
            let what = kind.map(Kind::name).unwrap_or("the unit asked for");
            (
                EvidenceResult::Supported,
                1.0,
                format!(
                    "the question asks for {what}; the answer's figure {} is {}",
                    claim.text,
                    describe(&given)
                ),
                vec![],
            )
        } else {
            let rationale = problems.iter().map(|p| p.0.clone()).collect::<Vec<_>>().join("; ");
            (EvidenceResult::Unsupported, 0.0, rationale, problems.into_iter().map(|p| p.1).collect())
        };
        notes.extend(asked);
        Ok(vec![Evidence {
            verifier_id: ID.into(),
            verifier_version: VERSION.into(),
            claim_id: claim.id.clone(),
            result,
            score: Score(score),
            confidence: Score(1.0),
            determinism: Determinism::Exact,
            rationale,
            receipt: Receipt { notes, ..Default::default() },
            model_hash: None,
            calibration_id: None,
        }])
    }
}

/// A percentage, or a bare number that reads as a fraction or a ratio
/// (`0.13`, `1.336`). An amount in a currency or a unit is not.
fn fraction_like(q: &Quantity) -> bool {
    match q.dimension() {
        Dimension::Percent => true,
        Dimension::Dimensionless => q.scale_exponent == 0,
        _ => false,
    }
}

fn describe(d: &Dimension) -> String {
    match d {
        Dimension::Percent => "a percentage".into(),
        Dimension::Dimensionless => "a bare number".into(),
        Dimension::Currency(code) => format!("an amount in {code}"),
        other => format!("a {}", format!("{other:?}").to_lowercase()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use gl_core::Source;

    fn check(question: &str, answer: &str) -> Vec<(EvidenceResult, Vec<String>)> {
        let answer = gl_text::normalise(answer);
        let input = VerificationInput {
            question: Some(question.into()),
            claims: crate::extract_claims(&answer, "en"),
            answer,
            sources: vec![Source {
                id: "s".into(),
                text: "x".into(),
                locator: None,
                provenance: Default::default(),
            }],
            locale: "en".into(),
            metadata: Default::default(),
            scope: Default::default(),
        };
        IntentVerifier::default()
            .verify(&input)
            .unwrap()
            .into_iter()
            .map(|e| (e.result, e.receipt.notes))
            .collect()
    }

    fn has(rows: &[(EvidenceResult, Vec<String>)], note: &str) -> bool {
        rows.iter().any(|r| r.1.iter().any(|n| n == note))
    }

    #[test]
    fn a_percentage_asked_and_an_amount_given_is_flagged() {
        let rows = check(
            "What portion of the total obligations is related to equity?",
            "The portion related to equity is $1,246 million.",
        );
        assert_eq!(rows[0].0, EvidenceResult::Unsupported);
        assert!(has(&rows, "intent_mismatch") && has(&rows, "asked:percent"));
        let rows =
            check("What percentage is employee related?", "It is $105 million of $156 million, or 67.31%.");
        assert_eq!(rows[0].0, EvidenceResult::Supported, "the last figure is the result");
    }

    #[test]
    fn an_amount_or_a_count_asked_and_a_percentage_given_is_flagged() {
        let rows = check("How much did revenue grow, in millions?", "Revenue grew 12.5%.");
        assert!(has(&rows, "intent_mismatch"));
        let rows = check("How many stores were opened?", "Stores grew 15%.");
        assert!(has(&rows, "intent_mismatch") && has(&rows, "asked:count"));
        let rows = check("How many stores were opened in 2015?", "In 2015, 120 stores were opened.");
        assert_eq!(rows[0].0, EvidenceResult::Supported, "the year is not the figure");
    }

    #[test]
    fn a_percentage_where_a_unit_was_asked_is_flagged() {
        let rows = check("What was ACME's Q4 revenue in euros?", "Q4 revenue was 12%.");
        assert_eq!(rows[0].0, EvidenceResult::Unsupported);
        assert!(has(&rows, "unit_mismatch") && has(&rows, "asked_unit:EUR"), "{rows:?}");
        // A question that asks for a percentage keeps its percentage.
        let rows = check("What percentage of revenue in euros came from Spain?", "Spain was 12%.");
        assert!(!has(&rows, "unit_mismatch"), "{rows:?}");
    }

    #[test]
    fn the_unit_the_question_names_must_be_the_unit_given() {
        let rows = check("What was the fee in euros?", "The fee was $25.40.");
        assert!(has(&rows, "unit_mismatch"));
        let rows = check("What was the fee in euros?", "The fee was 25.40.");
        assert!(has(&rows, "unit_missing"));
        let rows = check("What was the fee in euros?", "The fee was 25.40 euros.");
        assert_eq!(rows[0].0, EvidenceResult::Supported);
    }

    #[test]
    fn no_signal_no_figure_or_no_question_means_no_evidence() {
        assert!(check("Who signed the contract?", "It was signed on page 12 by the CFO.").is_empty());
        assert!(check("What percentage is it?", "The excerpts do not say.").is_empty());
    }
}
