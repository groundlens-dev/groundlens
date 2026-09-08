//! A numeral with its scale word and its unit, and how two of them compare.

use gl_core::Span;
use rust_decimal::{Decimal, RoundingStrategy};
use serde::{Deserialize, Serialize};

use crate::locale::LocaleProfile;
use crate::numeral::{find_numerals, Numeral};
use crate::units::{pow10, unit_for, Dimension, Unit, SCALES};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Quantity {
    pub numeral: Numeral,
    /// Span of numeral plus attached scale word and unit.
    pub span: Span,
    /// Every legitimate reading, already multiplied by the scale.
    pub readings: Vec<Decimal>,
    pub scale_exponent: u32,
    pub unit: Unit,
    pub notes: Vec<&'static str>,
}

impl Quantity {
    pub fn dimension(&self) -> &Dimension {
        &self.unit.dimension
    }

    /// Base-unit value of one reading as an exact fraction `(num, den)`.
    fn canonical(&self, reading: Decimal) -> (Decimal, Decimal) {
        (reading * self.unit.num + self.unit.offset_num, self.unit.den)
    }

    /// Approximate base value, only for distances and rounding, never for
    /// equality.
    fn approx_base(&self, reading: Decimal) -> Option<Decimal> {
        let (n, d) = self.canonical(reading);
        n.checked_div(d)
    }

    /// Every reading in the base unit of its dimension: `1200 m`,
    /// `37350000000 EUR`, `373.15 K`. This is the value that was compared.
    pub fn canonical_text(&self) -> String {
        let parts: Vec<String> = self
            .readings
            .iter()
            .map(|r| {
                let base = self.approx_base(*r).unwrap_or(*r).normalize();
                if self.unit.symbol.is_empty() {
                    base.to_string()
                } else {
                    format!("{base} {}", self.unit.symbol)
                }
            })
            .collect();
        parts.join(" | ")
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct MatchOptions {
    /// `37.4 billion` matches `37,350 million` because the source rounded to
    /// the answer's three significant digits is `37.4 billion`.
    pub declared_precision: bool,
    /// `4.75%` matches `0.0475`.
    pub percent_as_fraction: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Match {
    /// Same base value in the same dimension. Exact arithmetic.
    Exact,
    /// Equal once the source is rounded to the answer's declared precision.
    AtDeclaredPrecision { significant_digits: u32 },
    /// Equal under the percent-as-fraction reading.
    PercentAsFraction,
    /// Same dimension, different value. `relative_distance` is for the
    /// receipt ("nearest") and never for a decision.
    Different { relative_distance: Decimal },
    /// The two quantities cannot be compared (metres against euros).
    DimensionMismatch,
}

impl Match {
    pub fn supported(&self) -> bool {
        matches!(self, Match::Exact | Match::AtDeclaredPrecision { .. } | Match::PercentAsFraction)
    }
}

fn round_to_significant(value: Decimal, digits: u32) -> Decimal {
    if value.is_zero() {
        return value;
    }
    let magnitude = {
        let mut e: i32 = 0;
        let mut v = value.abs();
        let ten = Decimal::from(10);
        while v >= ten {
            v /= ten;
            e += 1;
        }
        while v < Decimal::ONE {
            v *= ten;
            e -= 1;
        }
        e
    };
    let dp = digits as i32 - 1 - magnitude;
    if dp >= 0 {
        value.round_dp_with_strategy(dp as u32, RoundingStrategy::MidpointAwayFromZero)
    } else {
        let factor = pow10((-dp) as u32);
        (value / factor).round_dp_with_strategy(0, RoundingStrategy::MidpointAwayFromZero) * factor
    }
}

/// Compare an answer quantity with a source quantity.
pub fn compare(answer: &Quantity, source: &Quantity, options: MatchOptions) -> Match {
    let same_dimension = answer.dimension() == source.dimension();
    let percent_pair = options.percent_as_fraction
        && matches!(
            (answer.dimension(), source.dimension()),
            (Dimension::Percent, Dimension::Dimensionless) | (Dimension::Dimensionless, Dimension::Percent)
        );
    if !same_dimension && !percent_pair {
        return Match::DimensionMismatch;
    }

    let hundred = Decimal::from(100);
    let scale_for = |q: &Quantity| {
        if percent_pair && *q.dimension() == Dimension::Percent {
            Decimal::ONE
        } else {
            hundred
        }
    };

    let mut best_distance: Option<Decimal> = None;
    for a in &answer.readings {
        for s in &source.readings {
            // Equality: every reading of both sides. Distance for the receipt:
            // the answer's primary reading only, as groundlens 3.x did, so an
            // ambiguous answer points at the number a digit was dropped from.
            let primary = std::ptr::eq(a, &answer.readings[0]);
            let (an, ad) = answer.canonical(*a);
            let (sn, sd) = source.canonical(*s);
            if same_dimension {
                if an * sd == sn * ad {
                    return Match::Exact;
                }
            } else {
                // percent pair: compare a/100 (if a is percent) with s.
                let an = an * scale_for(answer);
                let sn = sn * scale_for(source);
                if an * sd == sn * ad {
                    return Match::PercentAsFraction;
                }
            }
            if !primary {
                continue;
            }
            if let (Some(ab), Some(sb)) = (answer.approx_base(*a), source.approx_base(*s)) {
                let scale = ab.abs().max(sb.abs()).max(Decimal::ONE);
                let distance = (ab - sb).abs() / scale;
                if best_distance.is_none_or(|b| distance < b) {
                    best_distance = Some(distance);
                }
            }
        }
    }

    if options.declared_precision && same_dimension {
        let digits = answer.numeral.significant_digits;
        for a in &answer.readings {
            for s in &source.readings {
                if let (Some(ab), Some(sb)) = (answer.approx_base(*a), source.approx_base(*s)) {
                    if round_to_significant(sb, digits) == round_to_significant(ab, digits) {
                        return Match::AtDeclaredPrecision { significant_digits: digits };
                    }
                }
            }
        }
    }

    Match::Different { relative_distance: best_distance.unwrap_or(Decimal::ONE) }
}

fn is_word_boundary(text: &str, end: usize) -> bool {
    text[end..].chars().next().is_none_or(|c| !c.is_alphanumeric())
}

fn skip_spaces(text: &str, mut pos: usize) -> usize {
    while let Some(c) = text[pos..].chars().next() {
        if c == ' ' || c == '\u{202F}' {
            pos += c.len_utf8();
        } else {
            break;
        }
    }
    pos
}

fn take_scale(text: &str, pos: usize, profile: &LocaleProfile) -> Option<(u32, usize, Vec<&'static str>)> {
    let rest = &text[pos..];
    for scale in SCALES {
        // Words (`million`, `mil millones`) match case-insensitively.
        // Abbreviations (`k`, `M`, `bn`, `MM`) are case-sensitive: `K` is
        // kelvin and `m` is a metre.
        let is_word =
            scale.word.chars().count() >= 3 && scale.word.chars().all(|c| c.is_alphabetic() || c == ' ');
        let matches = if is_word {
            rest.to_lowercase().starts_with(&scale.word.to_lowercase())
        } else {
            rest.starts_with(scale.word)
        };
        if !matches || !is_word_boundary(text, pos + scale.word.len()) {
            continue;
        }
        let mut notes = vec![];
        if let (Some(required), Some(actual)) = (scale.long_scale_only, profile.long_scale) {
            if required != actual {
                // "billion" in a Spanish document: the word form wins, the
                // note records the tension for the reviewer.
                notes.push("scale_word_foreign_to_locale");
            }
        }
        return Some((scale.exponent, pos + scale.word.len(), notes));
    }
    None
}

fn take_unit(text: &str, pos: usize) -> Option<(Unit, usize)> {
    let rest = &text[pos..];
    let token_end = rest
        .char_indices()
        .find(|(_, c)| {
            !(c.is_alphanumeric() || matches!(c, '°' | 'º' | '$' | '€' | '£' | '¥' | '₹' | '%' | '²' | '³'))
        })
        .map(|(i, _)| i)
        .unwrap_or(rest.len());
    if token_end == 0 {
        return None;
    }
    let token = &rest[..token_end];
    let trimmed = token.trim_end_matches(['.', ',']);
    unit_for(trimmed).map(|u| (u, pos + trimmed.len()))
}

fn preceding_currency(text: &str, start: usize) -> Option<(Unit, usize)> {
    let before = text[..start].trim_end_matches(' ');
    let word_start = before
        .char_indices()
        .rev()
        .find(|(_, c)| !c.is_ascii_alphabetic())
        .map(|(i, c)| i + c.len_utf8())
        .unwrap_or(0);
    let token = &before[word_start..];
    if token.len() == 3 && token.chars().all(|c| c.is_ascii_uppercase()) {
        unit_for(token).map(|u| (u, word_start))
    } else {
        None
    }
}

/// A scale declared once for a whole passage: "(in millions of dollars)",
/// "(en millones de euros)", "figures in thousands". Applies to every bare
/// numeral that follows it in the same text. This is the table-header case
/// that made `$37.35 billion` and a cell reading `37,350` under "in
/// millions" look like a contradiction in groundlens 3.x.
#[derive(Debug, Clone)]
struct ContextScale {
    position: usize,
    exponent: u32,
    unit: Option<Unit>,
}

fn context_scales(text: &str, profile: &LocaleProfile) -> Vec<ContextScale> {
    let mut out = Vec::new();
    let lower = text.to_lowercase();
    for lead in [
        "in ",
        "en ",
        "figures in ",
        "cifras en ",
        "amounts in ",
        "importes en ",
        "expressed in ",
        "expresado en ",
    ] {
        let mut from = 0usize;
        while let Some(rel) = lower[from..].find(lead) {
            let at = from + rel;
            from = at + lead.len();
            // Must be at a word boundary.
            if at > 0 && lower[..at].chars().next_back().is_some_and(|c| c.is_alphanumeric()) {
                continue;
            }
            let after = at + lead.len();
            let Some((exponent, end, _)) = take_scale(text, after, profile) else { continue };
            let mut pos = skip_spaces(text, end);
            for connector in ["de ", "of "] {
                if lower[pos..].starts_with(connector) {
                    pos += connector.len();
                    break;
                }
            }
            let unit = take_unit(text, pos).map(|(u, _)| u);
            out.push(ContextScale { position: at, exponent, unit });
        }
    }
    out.sort_by_key(|c| c.position);
    out
}

/// Every numeral in `text` with its attached scale and unit.
pub fn find_quantities(text: &str, profile: &LocaleProfile) -> Vec<Quantity> {
    find_quantities_with(text, profile, true)
}

/// Bare numerals only, groundlens 3.x semantics: no scale words, no units,
/// no header-declared scales. `$37.35 billion` is the number 37.35. Used by
/// the `proofread()` compatibility facade and its golden tests.
pub fn find_bare_numerals(text: &str, profile: &LocaleProfile) -> Vec<Quantity> {
    find_quantities_with(text, profile, false)
}

fn find_quantities_with(text: &str, profile: &LocaleProfile, attach_units: bool) -> Vec<Quantity> {
    let mut out = Vec::new();
    if !attach_units {
        for numeral in find_numerals(text, profile) {
            out.push(Quantity {
                span: numeral.span,
                readings: numeral.readings.clone(),
                scale_exponent: 0,
                unit: Unit::dimensionless(),
                notes: numeral.notes.clone(),
                numeral,
            });
        }
        return out;
    }
    let declared = context_scales(text, profile);
    for numeral in find_numerals(text, profile) {
        let mut span = numeral.span;
        let mut exponent = 0u32;
        let mut notes: Vec<&'static str> = numeral.notes.clone();
        let mut unit: Option<Unit> = None;

        if numeral.percent {
            unit = Some(Unit::percent());
        } else if let Some(sym) = numeral.currency_symbol {
            unit = unit_for(&sym.to_string());
        } else if let Some((u, start)) = preceding_currency(text, span.start) {
            unit = Some(u);
            span.start = start;
        }

        let mut pos = skip_spaces(text, span.end);
        if let Some((e, end, extra)) = take_scale(text, pos, profile) {
            exponent = e;
            notes.extend(extra);
            span.end = end;
            pos = skip_spaces(text, end);
            // "millones de euros", "billion of"
            for connector in ["de ", "d'", "of "] {
                if text[pos..].to_lowercase().starts_with(connector) {
                    pos += connector.len();
                    break;
                }
            }
        }
        match (&unit, take_unit(text, pos)) {
            (None, Some((u, end))) => {
                unit = Some(u);
                span.end = end;
            }
            // "$37.35 billion dollars": redundant but consistent.
            (Some(existing), Some((u, end))) if u.dimension == existing.dimension => {
                span.end = end;
            }
            _ => {}
        }

        if exponent == 0 && !numeral.percent {
            if let Some(ctx) = declared.iter().rev().find(|c| c.position < numeral.span.start) {
                exponent = ctx.exponent;
                notes.push("scale_from_context");
                if unit.is_none() {
                    unit = ctx.unit.clone();
                }
            }
        }

        let factor = pow10(exponent);
        let readings = numeral.readings.iter().map(|r| *r * factor).collect();
        out.push(Quantity {
            span,
            readings,
            scale_exponent: exponent,
            unit: unit.unwrap_or_else(Unit::dimensionless),
            notes,
            numeral,
        });
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::locale::locale;

    fn q(text: &str, loc: &str) -> Quantity {
        find_quantities(text, &locale(loc).unwrap()).remove(0)
    }

    #[test]
    fn billion_equals_thousands_of_millions() {
        let a = q("$37.35 billion", "en");
        let s = q("37,350 million dollars", "en");
        assert_eq!(compare(&a, &s, MatchOptions::default()), Match::Exact);
        assert_eq!(a.unit.dimension, Dimension::Currency("USD".into()));
    }

    #[test]
    fn spanish_long_scale() {
        let a = q("37.350 millones de euros", "es");
        let s = q("EUR 37,35 mil millones", "es");
        assert_eq!(compare(&a, &s, MatchOptions::default()), Match::Exact);
        let b = q("1,5 billones de euros", "es");
        assert_eq!(b.readings[0], Decimal::from(1_500_000_000_000u64));
    }

    #[test]
    fn physical_units_convert_exactly() {
        assert_eq!(compare(&q("1.2 km", "en"), &q("1200 m", "en"), MatchOptions::default()), Match::Exact);
        assert_eq!(compare(&q("2.5 MWh", "en"), &q("2500 kWh", "en"), MatchOptions::default()), Match::Exact);
        assert_eq!(compare(&q("212 °F", "en"), &q("100 °C", "en"), MatchOptions::default()), Match::Exact);
        assert_eq!(compare(&q("100 °C", "en"), &q("373.15 K", "en"), MatchOptions::default()), Match::Exact);
        assert_eq!(
            compare(&q("10 km", "en"), &q("10 kg", "en"), MatchOptions::default()),
            Match::DimensionMismatch
        );
    }

    #[test]
    fn rounding_is_a_named_relaxation() {
        let a = q("about 37.4 billion", "en");
        let s = q("37,350 million", "en");
        assert!(matches!(compare(&a, &s, MatchOptions::default()), Match::Different { .. }));
        assert_eq!(
            compare(&a, &s, MatchOptions { declared_precision: true, ..Default::default() }),
            Match::AtDeclaredPrecision { significant_digits: 3 }
        );
    }

    #[test]
    fn percent_as_fraction_is_opt_in() {
        let a = q("4.75%", "en");
        let s = q("0.0475", "en");
        assert_eq!(compare(&a, &s, MatchOptions::default()), Match::DimensionMismatch);
        assert_eq!(
            compare(&a, &s, MatchOptions { percent_as_fraction: true, ..Default::default() }),
            Match::PercentAsFraction
        );
    }

    #[test]
    fn a_header_scale_applies_to_the_cells_below_it() {
        let src = "Revenue (in millions of dollars)\n2024  37,350\n2023  36,400";
        let qs = find_quantities(src, &locale("en").unwrap());
        let cell = qs.iter().find(|q| q.numeral.text == "37,350").unwrap();
        assert_eq!(cell.readings[0], Decimal::from(37_350_000_000u64));
        assert_eq!(cell.unit.dimension, Dimension::Currency("USD".into()));
        assert!(cell.notes.contains(&"scale_from_context"));
        // Years are not scaled: they carry no "scale_from_context"? They do,
        // and that is deliberate: the engine cannot know a bare 2024 is a
        // year. The temporal claim kind (roadmap M1) removes them upstream.
        assert_eq!(compare(&q("$37.35 billion", "en"), cell, MatchOptions::default()), Match::Exact);
    }

    #[test]
    fn ten_is_not_a_hundred() {
        let m = compare(&q("1,000 dollars", "en"), &q("10,000 dollars", "en"), MatchOptions::default());
        match m {
            Match::Different { relative_distance } => {
                assert_eq!(relative_distance, Decimal::from_str_exact("0.9").unwrap())
            }
            other => panic!("{other:?}"),
        }
    }
}
