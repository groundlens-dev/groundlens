// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The exact channel. Support is 1.0 or 0.0. Similarity is not allowed to
//! vote. What is new against groundlens 3.x: scale words, currencies,
//! percentages and physical units are compared in a canonical base unit, and
//! two named relaxations can be switched on by configuration (and therefore
//! by policy), each one leaving a note on the receipt.
//!
//! Since 1.1.0 the verifier also recomputes. Answers show their work: "from
//! $77 million to $75 million, a decline of $2 million, or 2.60 %". The
//! decline and the percentage are in no source, and they are right. A figure
//! that no source contains is checked against the other figures of the same
//! answer that the sources do support: their sum, difference, ratio or
//! percentage change, computed as exact fractions and compared under the
//! rounding rule at the precision the answer wrote. A match is `supported`
//! with the formula in the rationale and the note `derived`; no match leaves
//! the figure `contradicted`, as before. Only the answer's own supported
//! figures are operands, never arbitrary pairs of source figures: with a
//! table of forty numbers some pair matches almost anything.
//!
//! A bare four-digit year that no source contains (`in 2015`) is
//! `unsupported` with the note `year_not_in_sources`, not `contradicted`: a
//! year is a label, and its absence from a passage is not a wrong figure.

use gl_core::{
    ClaimKind, Determinism, Evidence, EvidenceResult, Receipt, Result, Score, Span, VerificationInput,
    Verifier, VerifierInfo, VerifierKind,
};
use gl_numeric::{
    compare, find_bare_numerals, find_quantities, locale, rounds_to, Dimension, Match, MatchOptions,
    Quantity, Ratio, Rounding,
};
use serde::{Deserialize, Serialize};

pub const ID: &str = "groundlens.numeric";
pub const VERSION: &str = "1.2.0";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NumericConfig {
    #[serde(default)]
    pub matching: MatchOptions,
    /// Attach scale words, currencies, percent and physical units and compare
    /// in base units. `false` gives groundlens 3.x semantics (bare numbers).
    #[serde(default = "default_true")]
    pub units: bool,
    /// Recompute figures that no source contains from the answer's own
    /// supported figures. `false` gives 1.0.0 behaviour.
    #[serde(default = "default_true")]
    pub derive: bool,
    /// How a recomputed value may differ from the figure written, at the
    /// precision written.
    #[serde(default)]
    pub rounding: Rounding,
}

fn default_true() -> bool {
    true
}

impl Default for NumericConfig {
    fn default() -> Self {
        NumericConfig {
            matching: MatchOptions::default(),
            units: true,
            derive: true,
            rounding: Rounding::default(),
        }
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
    /// The scale the passage declares once for its table, "( in millions )":
    /// a power of ten applied to the bare cells under it.
    declared_scale: Option<u32>,
}

/// The scale a passage declares for its figures: "( in millions )",
/// "(in thousands of dollars)", "dollars in billions". Tables state it once in
/// a header and leave the cells bare; the answer usually writes it out
/// ("$217,692,000" for a cell "217692" in thousands).
fn declared_scale(text: &str) -> Option<u32> {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    let re = RE.get_or_init(|| {
        regex::Regex::new(
            r"(?i)\(\s*(?:\$|€|£|dollars|usd|eur|euros?)?\s*in\s+(thousands|millions|billions)\b|\b(?:dollars|usd|euros?)\s+in\s+(thousands|millions|billions)\b",
        )
        .expect("declared scale")
    });
    let word = re.captures(text)?.iter().skip(1).flatten().next()?.as_str().to_lowercase();
    match word.as_str() {
        "thousands" => Some(3),
        "millions" => Some(6),
        "billions" => Some(9),
        _ => None,
    }
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
                let declared_scale = declared_scale(&s.text);
                find(&s.text).into_iter().map(move |quantity| SourceQuantity {
                    source_id: &s.id,
                    quantity,
                    declared_scale,
                })
            })
            .collect();

        let question_quantities: Vec<Quantity> = input.question.as_deref().map(find).unwrap_or_default();

        let mut rows: Vec<Row> = Vec::new();
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

            let (mut result, mut score, mut rationale, mut receipt) = match best {
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

            // A table cell often carries the number and leaves the unit to a
            // header we could not read: the answer says "$5,312 million", the
            // cell says "5,312". The same written number with a unit on one
            // side only is support, with a note; with three or more
            // significant digits a coincidence is unlikely.
            if result != EvidenceResult::Supported
                && answer_q.numeral.significant_digits >= MIN_DIGITS_UNIT_ON_ONE_SIDE
            {
                if let Some(sq) =
                    source_quantities.iter().find(|sq| unit_on_one_side(&answer_q, &sq.quantity))
                {
                    let span = Span::new(sq.quantity.span.start, sq.quantity.span.end);
                    let shown = input_source_text(input, sq.source_id, sq.quantity.span);
                    result = EvidenceResult::Supported;
                    score = 1.0;
                    rationale = format!(
                        "{} = {} in {}; the unit or scale is stated on one side only",
                        claim.text, shown, sq.source_id
                    );
                    receipt = Receipt {
                        source_id: Some(sq.source_id.to_string()),
                        source_span: Some(span),
                        source_text: Some(shown),
                        notes: notes
                            .iter()
                            .cloned()
                            .chain(["unit_or_scale_on_one_side".to_string()])
                            .collect(),
                    };
                }
            }
            // The table says "( in millions )" once and the cell says "-57";
            // the answer says "-$57 million". The same figure, with the
            // scale the passage declares.
            if result != EvidenceResult::Supported && answer_q.numeral.significant_digits >= 2 {
                if let Some(sq) = source_quantities.iter().find(|sq| header_scale_matches(&answer_q, sq)) {
                    let span = Span::new(sq.quantity.span.start, sq.quantity.span.end);
                    let shown = input_source_text(input, sq.source_id, sq.quantity.span);
                    result = EvidenceResult::Supported;
                    score = 1.0;
                    rationale = format!(
                        "{} = {} in {}, under the scale its table declares",
                        claim.text, shown, sq.source_id
                    );
                    receipt = Receipt {
                        source_id: Some(sq.source_id.to_string()),
                        source_span: Some(span),
                        source_text: Some(shown),
                        notes: notes.iter().cloned().chain(["scale_from_header".to_string()]).collect(),
                    };
                }
            }
            // "$52 million" against a bare "52" in a table that states no
            // scale: two digits are too few to call it the same figure, and
            // too many to call it a different one. Not a contradiction.
            if result == EvidenceResult::Contradicted && answer_q.numeral.significant_digits == 2 {
                if let Some(sq) =
                    source_quantities.iter().find(|sq| unit_on_one_side(&answer_q, &sq.quantity))
                {
                    result = EvidenceResult::Unsupported;
                    score = 0.0;
                    rationale = format!(
                        "{} matches {} in {} only if the unit or scale stated on one side applies to the other",
                        claim.text,
                        input_source_text(input, sq.source_id, sq.quantity.span),
                        sq.source_id
                    );
                    receipt.notes.push("unit_or_scale_on_one_side_unconfirmed".into());
                }
            }
            rows.push(Row {
                claim_id: claim.id.clone(),
                text: claim.text.clone(),
                quantity: answer_q,
                result,
                score,
                rationale,
                receipt,
            });
        }

        for row in rows.iter_mut() {
            if row.result != EvidenceResult::Supported && is_year(&row.quantity) {
                row.result = EvidenceResult::Unsupported;
                row.score = 0.0;
                row.rationale = format!("{} reads as a year and appears in no source", row.text);
                row.receipt.notes.push("year_not_in_sources".into());
            }
        }
        if self.config.derive {
            derive(&mut rows, self.config.rounding);
            wrong_recomputations(&mut rows);
        }

        let mut out: Vec<Evidence> = rows
            .into_iter()
            .map(|row| Evidence {
                verifier_id: ID.to_string(),
                verifier_version: VERSION.to_string(),
                claim_id: row.claim_id,
                result: row.result,
                score: Score(row.score),
                confidence: Score(1.0),
                determinism: Determinism::Exact,
                rationale: row.rationale,
                receipt: row.receipt,
                model_hash: None,
                calibration_id: None,
            })
            .collect();
        out.sort_by_key(|e| e.sort_key());
        Ok(out)
    }
}

/// One numeric claim on its way to becoming evidence.
struct Row {
    claim_id: String,
    text: String,
    quantity: Quantity,
    result: EvidenceResult,
    score: f64,
    rationale: String,
    receipt: Receipt,
}

const MIN_DIGITS_UNIT_ON_ONE_SIDE: u32 = 3;

/// The same written number, where the unit or the scale is stated on one
/// side only: `$31.9 million` against a cell `$ 31.9`, `$5,312 million`
/// against `5312`. Two different units (`EUR` against `USD`) or two
/// different scales (`thousand` against `million`) are not this case: that
/// is a different figure.
fn unit_on_one_side(answer: &Quantity, source: &Quantity) -> bool {
    let (da, ds) = (answer.dimension(), source.dimension());
    let dims_agree = da == ds || *da == Dimension::Dimensionless || *ds == Dimension::Dimensionless;
    let (ea, es) = (answer.scale_exponent, source.scale_exponent);
    let scales_agree = ea == es || ea == 0 || es == 0;
    let something_missing = da != ds || ea != es;
    dims_agree
        && scales_agree
        && something_missing
        && answer.numeral.readings.iter().any(|a| source.numeral.readings.iter().any(|s| a == s))
}

/// The answer's figure is the source cell times the scale its passage
/// declares: `$217,692,000` against `217692` under "( in thousands )". The
/// cell must be bare (no scale word, no unit of another dimension).
fn header_scale_matches(answer: &Quantity, sq: &SourceQuantity) -> bool {
    let source = &sq.quantity;
    if is_year(source) {
        return false;
    }
    let (da, ds) = (answer.dimension(), source.dimension());
    if !(da == ds || *ds == Dimension::Dimensionless) {
        return false;
    }
    let (Some(a), Some(s)) = (answer.base_ratio(0), source.base_ratio(0)) else {
        return false;
    };
    // The reader already applied the table's scale to the cell, but the
    // header named no currency: "( in millions )" over "-57".
    if source.scale_exponent > 0 && source.notes.contains(&"scale_from_context") {
        return s == a;
    }
    // A header the reader does not take as a scale context, such as
    // "( in thousands )" after a title: apply it here.
    let Some(exp) = sq.declared_scale.filter(|_| source.scale_exponent == 0) else {
        return false;
    };
    Ratio::pow10(exp as i32).and_then(|f| s.checked_mul(f)).is_some_and(|scaled| scaled == a)
}

/// A bare four-digit year: `2015`, `(2011)`. No separator, no decimals, no
/// unit, no scale, between 1900 and 2100.
pub(crate) fn is_year(q: &Quantity) -> bool {
    let digits = q.numeral.text.chars().filter(char::is_ascii_digit).count();
    // `(2011)` and the second half of `2022-2023` are years too.
    let only_digits =
        q.numeral.text.chars().all(|c| c.is_ascii_digit() || matches!(c, '(' | ')' | '-' | '−' | '–'));
    only_digits
        && digits == 4
        && q.scale_exponent == 0
        && *q.dimension() == Dimension::Dimensionless
        && q.numeral.readings.len() == 1
        && q.numeral.readings[0].scale() == 0
        && q.numeral.readings[0].abs() >= 1900.into()
        && q.numeral.readings[0].abs() <= 2100.into()
}

/// A figure the answer states and the sources (or an earlier derivation)
/// support: an operand for recomputing the others.
struct Operand {
    claim_id: String,
    text: String,
    dimension: Dimension,
    base: Ratio,
    written: Ratio,
}

impl Operand {
    fn of(row: &Row) -> Option<Operand> {
        Some(Operand {
            claim_id: row.claim_id.clone(),
            text: row.text.clone(),
            dimension: row.quantity.dimension().clone(),
            base: row.quantity.base_ratio(0)?,
            written: row.quantity.written_ratio(0)?,
        })
    }
}

/// A recomputed value: what it is, in which dimension, and how it was made.
struct Candidate {
    value: Ratio,
    dimension: Dimension,
    formula: String,
    from: Vec<String>,
}

/// Largest group of same-dimension operands whose sums and averages are
/// tried: 2^10 subsets at most.
const MAX_GROUP: usize = 10;

fn candidates(ops: &[Operand]) -> Vec<Candidate> {
    let hundred = Ratio::from_int(100);
    let two = Ratio::from_int(2);
    let mut out = Vec::new();
    let mut push = |value: Option<Ratio>, dimension: Dimension, formula: String, from: Vec<String>| {
        if let Some(value) = value {
            out.push(Candidate { value, dimension, formula, from });
        }
    };
    for (i, a) in ops.iter().enumerate() {
        for (j, b) in ops.iter().enumerate() {
            if i == j {
                continue;
            }
            let from = vec![a.claim_id.clone(), b.claim_id.clone()];
            let (at, bt) = (&a.text, &b.text);
            // An amount per unit: "$217,692 / 139,255 = $1.56" per share.
            if a.dimension != Dimension::Dimensionless
                && b.dimension == Dimension::Dimensionless
                && !b.base.is_zero()
            {
                push(a.base.checked_div(b.base), a.dimension.clone(), format!("{at} / {bt}"), from.clone());
            }
            if a.dimension != b.dimension {
                continue;
            }
            if i < j {
                let sum = a.base.checked_add(b.base);
                push(sum, a.dimension.clone(), format!("{at} + {bt}"), from.clone());
                push(
                    sum.and_then(|x| x.checked_div(two)),
                    a.dimension.clone(),
                    format!("({at} + {bt}) / 2"),
                    from.clone(),
                );
            }
            let diff = a.base.checked_sub(b.base);
            push(diff, a.dimension.clone(), format!("{at} − {bt}"), from.clone());
            if i < j {
                push(
                    diff.and_then(Ratio::checked_abs),
                    a.dimension.clone(),
                    format!("|{at} − {bt}|"),
                    from.clone(),
                );
            }
            if !b.base.is_zero() {
                let ratio = a.base.checked_div(b.base);
                push(ratio, Dimension::Dimensionless, format!("{at} / {bt}"), from.clone());
                push(
                    ratio.and_then(|r| r.checked_mul(hundred)),
                    Dimension::Percent,
                    format!("{at} / {bt} × 100"),
                    from.clone(),
                );
                let change = diff.and_then(|d| d.checked_div(b.base)).and_then(|r| r.checked_mul(hundred));
                push(change, Dimension::Percent, format!("({at} − {bt}) / {bt} × 100"), from.clone());
                push(
                    change.and_then(Ratio::checked_abs),
                    Dimension::Percent,
                    format!("|({at} − {bt}) / {bt}| × 100"),
                    from,
                );
            }
        }
    }
    // Sums and averages of three or more figures of the same kind: "the
    // total for 2008 to 2010", "the average of the three categories".
    let mut dims: Vec<&Dimension> = Vec::new();
    for op in ops {
        if !dims.contains(&&op.dimension) {
            dims.push(&op.dimension);
        }
    }
    for dim in dims {
        let group: Vec<&Operand> = ops.iter().filter(|o| &o.dimension == dim).collect();
        if group.len() < 3 || group.len() > MAX_GROUP {
            continue;
        }
        for mask in 0u32..(1u32 << group.len()) {
            let members: Vec<&Operand> =
                group.iter().enumerate().filter(|(k, _)| mask & (1 << k) != 0).map(|(_, o)| *o).collect();
            if members.len() < 3 {
                continue;
            }
            let Some(sum) = members.iter().try_fold(Ratio::from_int(0), |acc, o| acc.checked_add(o.base))
            else {
                continue;
            };
            let texts: Vec<&str> = members.iter().map(|o| o.text.as_str()).collect();
            let from: Vec<String> = members.iter().map(|o| o.claim_id.clone()).collect();
            push(Some(sum), dim.clone(), texts.join(" + "), from.clone());
            let n = Ratio::from_int(members.len() as i128);
            push(
                sum.checked_div(n),
                dim.clone(),
                format!("({}) / {}", texts.join(" + "), members.len()),
                from,
            );
        }
    }
    out
}

/// A recomputed figure written within half a percent of the exact value:
/// "1,095.6 / 2,719.3 × 100 ≈ 40.4 %" (40.29) or "2.0 / 22.885 ≈ 8.75 %"
/// (8.74). Models slip in the last digit when they divide by hand; a slip
/// that small is not a wrong figure. "24.0 % to 22.1 %, a change of −7.5 %"
/// (−7.92) is 5 % off, and stays wrong. Only recomputed figures get this
/// tolerance, and only under the default `within_last_digit` rule; `half_up`
/// and `half_even` stay strict. A figure compared with a source must match
/// it exactly whatever the rule.
fn close_enough(value: Ratio, written: Ratio) -> bool {
    let check = || -> Option<bool> {
        let gap = value
            .checked_sub(written)?
            .checked_abs()?
            .checked_mul(Ratio::from_int(RELATIVE_TOLERANCE_INV))?;
        Some(!value.is_zero() && gap.checked_cmp(value.checked_abs()?)? != std::cmp::Ordering::Greater)
    };
    check().unwrap_or(false)
}

/// 1 / 200 = 0.5 %.
const RELATIVE_TOLERANCE_INV: i128 = 200;

/// Turn figures no source contains into `supported` when they restate or
/// recompute the answer's own supported figures. Runs to a fixed point (at
/// most three rounds), so a derived figure can feed the next one: the
/// decline of $2 million, then 2.60 % of $77 million.
fn derive(rows: &mut [Row], rounding: Rounding) {
    for _ in 0..3 {
        // A year is a label, not an amount: never an operand.
        let ops: Vec<Operand> = rows
            .iter()
            .filter(|r| r.result == EvidenceResult::Supported && !is_year(&r.quantity))
            .filter_map(Operand::of)
            .collect();
        if ops.is_empty() {
            return;
        }
        let cands = candidates(&ops);
        let mut changed = false;
        for row in rows.iter_mut() {
            if row.result == EvidenceResult::Supported || is_year(&row.quantity) {
                continue;
            }
            let (Some(base), Some(written), Some(step)) =
                (row.quantity.base_ratio(0), row.quantity.written_ratio(0), row.quantity.step_ratio(0))
            else {
                continue;
            };
            let dimension = row.quantity.dimension().clone();
            let bare = dimension == Dimension::Dimensionless;

            // A restatement: the same figure written again, often bare inside
            // a formula ("24.0" for "24.0 %").
            if let Some(op) = ops.iter().find(|op| {
                op.claim_id != row.claim_id
                    && ((op.dimension == dimension && op.base == base) || (bare && op.written == written))
            }) {
                row.result = EvidenceResult::Supported;
                row.score = 1.0;
                row.rationale =
                    format!("{} restates {} ({}), which the sources support", row.text, op.text, op.claim_id);
                row.receipt.notes.push("restates_answer_figure".into());
                changed = true;
                continue;
            }

            // A recomputation. An exact result needs no rounding and is
            // accepted at any precision; a rounded one needs at least two
            // significant digits written, so "5 %" is not "explained" by
            // whatever happens to round to it.
            let rounded_ok = row.quantity.numeral.significant_digits >= 2;
            let found = cands.iter().find(|c| {
                if c.from.contains(&row.claim_id) {
                    return false;
                }
                let comparable = c.dimension == dimension || (bare && c.dimension == Dimension::Percent);
                comparable
                    && (c.value == base
                        || (rounded_ok
                            && (rounds_to(c.value, base, step, rounding)
                                || (rounding == Rounding::WithinLastDigit && close_enough(c.value, base)))))
            });
            if let Some(c) = found {
                let exact = c.value == base;
                let slip = !exact && !rounds_to(c.value, base, step, rounding);
                row.result = EvidenceResult::Supported;
                row.score = 1.0;
                row.rationale = format!(
                    "{} = {} = {}{}",
                    row.text,
                    c.formula,
                    c.value.display(),
                    if exact { String::new() } else { format!(", rounded {}", rounding_name(rounding)) }
                );
                row.receipt.notes.push("derived".into());
                row.receipt.notes.push(format!("derived_from:{}", c.from.join(",")));
                if !exact {
                    row.receipt.notes.push(format!("rounding:{}", rounding_name(rounding)));
                }
                if slip {
                    row.receipt.notes.push("last_digit_slip".into());
                }
                changed = true;
            }
        }
        if !changed {
            return;
        }
    }
}

/// A figure that no source contains and that is the kind of figure the
/// answer's own supported figures can produce (a percentage from two amounts,
/// an amount from two amounts) was checked by [`derive`] and matched nothing:
/// it is wrong arithmetic, not a figure the sources are silent about. "From
/// €38.0 million to €41.2 million, up 12 %" is a contradiction (8.4 % is the
/// change), even when no source states a percentage. A bare number is left
/// alone: "2 quarters" next to two amounts is not a computation.
fn wrong_recomputations(rows: &mut [Row]) {
    let ops: Vec<Operand> = rows
        .iter()
        .filter(|r| r.result == EvidenceResult::Supported && !is_year(&r.quantity))
        .filter_map(Operand::of)
        .collect();
    let cands = candidates(&ops);
    for row in rows.iter_mut() {
        if row.result != EvidenceResult::Unsupported || is_year(&row.quantity) {
            continue;
        }
        let dimension = row.quantity.dimension().clone();
        if dimension == Dimension::Dimensionless {
            continue;
        }
        let mut from: Vec<&str> = cands
            .iter()
            .filter(|c| c.dimension == dimension && !c.from.contains(&row.claim_id))
            .flat_map(|c| c.from.iter().map(String::as_str))
            .collect();
        if from.is_empty() {
            continue;
        }
        from.sort_unstable();
        from.dedup();
        let operands: Vec<&str> =
            ops.iter().filter(|op| from.contains(&op.claim_id.as_str())).map(|op| op.text.as_str()).collect();
        row.result = EvidenceResult::Contradicted;
        row.score = 0.0;
        row.rationale = format!(
            "{} is in no source and matches no sum, difference, ratio or change of {}",
            row.text,
            operands.join(", ")
        );
        row.receipt.notes.push("recomputation_mismatch".into());
    }
}

fn rounding_name(r: Rounding) -> &'static str {
    match r {
        Rounding::HalfUp => "half_up",
        Rounding::HalfEven => "half_even",
        Rounding::WithinLastDigit => "within_last_digit",
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
                provenance: Default::default(),
            }],
            locale: "en".into(),
            metadata: Default::default(),
            scope: Default::default(),
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

    fn results(
        answer: &str,
        source: &str,
        config: NumericConfig,
    ) -> Vec<(String, EvidenceResult, Vec<String>)> {
        let mut i = input(answer, source, None);
        i.claims = crate::extract_claims(&i.answer, "en");
        NumericVerifier::new(config)
            .verify(&i)
            .unwrap()
            .into_iter()
            .map(|e| {
                let text = i.claims.iter().find(|c| c.id == e.claim_id).unwrap().text.clone();
                (text, e.result, e.receipt.notes)
            })
            .collect()
    }

    fn result_of(rows: &[(String, EvidenceResult, Vec<String>)], text: &str) -> EvidenceResult {
        rows.iter().find(|r| r.0 == text).unwrap_or_else(|| panic!("no claim {text:?} in {rows:?}")).1
    }

    #[test]
    fn a_difference_and_a_percentage_the_answer_computed_are_recomputed() {
        let rows = results(
            "Expense was $77 million in 2016 and $65 million in 2017, a decline of $12 million, or 15.58%.",
            "amortization expense: $77 million (2016), $65 million (2017)",
            NumericConfig { rounding: Rounding::HalfUp, ..Default::default() },
        );
        assert_eq!(result_of(&rows, "$12 million"), EvidenceResult::Supported);
        assert_eq!(result_of(&rows, "15.58%"), EvidenceResult::Supported, "12/77 = 15.584…");
        let pct = rows.iter().find(|r| r.0 == "15.58%").unwrap();
        assert!(pct.2.iter().any(|n| n == "derived"));
        assert!(pct.2.iter().any(|n| n == "rounding:half_up"));
    }

    #[test]
    fn a_single_digit_figure_with_a_unit_is_checked_too() {
        let rows = results(
            "Expense was $77 million and then $75 million, a decline of $2 million, or 2.60%.",
            "amortization expense: $77 million (2016), $75 million (2017)",
            NumericConfig::default(),
        );
        assert_eq!(result_of(&rows, "$2 million"), EvidenceResult::Supported);
        assert_eq!(result_of(&rows, "2.60%"), EvidenceResult::Supported);
        let rows = results(
            "A decline of $3 million.",
            "expense $77 million and $75 million",
            NumericConfig::default(),
        );
        assert_eq!(result_of(&rows, "$3 million"), EvidenceResult::Contradicted);
    }

    #[test]
    fn wrong_arithmetic_is_still_a_contradiction() {
        let rows = results(
            "It fell from 24.0% to 22.1%, a change of -7.5%.",
            "expected volatility 24.0 % (2012) and 22.1 % (2013)",
            NumericConfig::default(),
        );
        assert_eq!(result_of(&rows, "-7.5%"), EvidenceResult::Contradicted);
        let rows = results(
            "It fell from 24.0% to 22.1%, a change of -7.92%.",
            "expected volatility 24.0 % (2012) and 22.1 % (2013)",
            NumericConfig::default(),
        );
        assert_eq!(result_of(&rows, "-7.92%"), EvidenceResult::Supported);
    }

    #[test]
    fn a_wrong_percentage_change_fails_even_when_no_source_states_a_percentage() {
        let source = "In 2024, revenue reached €41.2 million, up from €38.0 million in 2023.";
        let rows = results(
            "Revenue rose from €38.0 million to €41.2 million, up 12%.",
            source,
            NumericConfig::default(),
        );
        assert_eq!(result_of(&rows, "12%"), EvidenceResult::Contradicted, "the change is 8.42 %");
        let pct = rows.iter().find(|r| r.0 == "12%").unwrap();
        assert!(pct.2.iter().any(|n| n == "recomputation_mismatch"));
        let rows = results(
            "Revenue rose from €38.0 million to €41.2 million, up 8.4%.",
            source,
            NumericConfig::default(),
        );
        assert_eq!(result_of(&rows, "8.4%"), EvidenceResult::Supported);
    }

    #[test]
    fn a_percentage_with_nothing_to_recompute_it_from_stays_unsupported() {
        // No supported amounts in the answer: nothing was computed, so
        // nothing is wrong arithmetic. The policy decides what silence means.
        let rows = results(
            "Revenue grew 12%.",
            "In 2024, revenue reached €41.2 million, up from €38.0 million in 2023.",
            NumericConfig::default(),
        );
        assert_eq!(result_of(&rows, "12%"), EvidenceResult::Unsupported);
    }

    #[test]
    fn the_rounding_rule_decides_truncated_figures() {
        let answer = "Cash flow was $957.4 million of $1,410.5 million, or 67.8%.";
        let source = "net cash provided $1,410.5 million; cash flow $957.4 million";
        let half_up =
            results(answer, source, NumericConfig { rounding: Rounding::HalfUp, ..Default::default() });
        assert_ne!(result_of(&half_up, "67.8%"), EvidenceResult::Supported, "67.876… rounds to 67.9");
        let lenient = results(
            answer,
            source,
            NumericConfig { rounding: Rounding::WithinLastDigit, ..Default::default() },
        );
        assert_eq!(result_of(&lenient, "67.8%"), EvidenceResult::Supported);
    }

    #[test]
    fn operands_come_from_the_answer_never_from_pairs_of_source_figures() {
        // 30 - 20 = 10 in the source, but the answer does not state 30 or 20.
        let rows =
            results("The gap is 10 million.", "units: 30 million and 20 million", NumericConfig::default());
        assert_eq!(result_of(&rows, "10 million"), EvidenceResult::Contradicted);
    }

    #[test]
    fn derive_false_keeps_the_previous_behaviour() {
        let rows = results(
            "From $77 million to $65 million, a decline of $12 million.",
            "$77 million and $65 million",
            NumericConfig { derive: false, ..Default::default() },
        );
        assert_eq!(result_of(&rows, "$12 million"), EvidenceResult::Contradicted);
    }

    #[test]
    fn a_year_missing_from_the_sources_is_not_a_wrong_figure() {
        let rows =
            results("In 2015 revenue was $10 million.", "revenue: $10 million", NumericConfig::default());
        assert_eq!(result_of(&rows, "2015"), EvidenceResult::Unsupported);
        assert_eq!(result_of(&rows, "$10 million"), EvidenceResult::Supported);
    }

    #[test]
    fn a_unit_or_scale_stated_on_one_side_only_is_support_with_a_note() {
        let rows =
            results("Leases were $5,312 million.", "operating leases | 5312 | 576", NumericConfig::default());
        assert_eq!(result_of(&rows, "$5,312 million"), EvidenceResult::Supported);
        assert!(rows[0].2.iter().any(|n| n == "unit_or_scale_on_one_side"));
        // Two different scales are a different figure.
        let rows = results(
            "Leases were $5,312 million.",
            "operating leases $5,312 thousand",
            NumericConfig::default(),
        );
        assert_eq!(result_of(&rows, "$5,312 million"), EvidenceResult::Contradicted);
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
