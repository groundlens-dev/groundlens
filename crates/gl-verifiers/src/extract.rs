// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Claim extraction, rule-based. Numerals are claimed first so `10,000` is
//! one claim rather than three; content words fill the rest. An ML claim
//! splitter can replace this stage without touching any verifier, because
//! verifiers only see [`Claim`]s.

use gl_core::{Claim, ClaimKind, Span};
use gl_numeric::{find_quantities, locale, Dimension};
use gl_text::words;

pub fn extract_claims(answer: &str, locale_name: &str) -> Vec<Claim> {
    extract_claims_with(answer, locale_name, true)
}

/// `units = false` reproduces groundlens 3.x segmentation: numeral spans
/// exclude scale words and units.
pub fn extract_claims_with(answer: &str, locale_name: &str, units: bool) -> Vec<Claim> {
    let profile = locale(locale_name).unwrap_or_else(|| locale("und").expect("und"));
    let mut claims: Vec<Claim> = Vec::new();

    let quantities = if units {
        find_quantities(answer, &profile)
    } else {
        gl_numeric::find_bare_numerals(answer, &profile)
    };
    for q in quantities {
        if formula_constant(answer, &q) || day_of_a_date(answer, &q) {
            continue;
        }
        let mut attributes = indexmap::IndexMap::new();
        attributes.insert("canonical".to_string(), q.canonical_text());
        attributes.insert("dimension".to_string(), dimension_name(q.dimension()));
        if !q.unit.symbol.is_empty() {
            attributes.insert("unit".to_string(), q.unit.symbol.to_string());
        }
        if q.numeral.ambiguous() {
            attributes.insert("ambiguous".to_string(), "true".to_string());
        }
        claims.push(Claim {
            id: String::new(),
            kind: ClaimKind::Numeric,
            text: answer[q.span.start..q.span.end].to_string(),
            span: q.span,
            attributes,
        });
    }

    let claimed: Vec<Span> = claims.iter().map(|c| c.span).collect();
    for w in words(answer, locale_name) {
        if w.stopword || claimed.iter().any(|s| s.overlaps(&w.span)) {
            continue;
        }
        claims.push(Claim {
            id: String::new(),
            kind: ClaimKind::Word,
            text: w.text,
            span: w.span,
            attributes: Default::default(),
        });
    }

    // Whole sentences, for the verifiers that read meaning (entailment,
    // similarity). Statements span the numeric and word claims they contain;
    // that overlap is fine because a verifier only ever sees its own kind.
    for span in sentences(answer) {
        claims.push(Claim {
            id: String::new(),
            kind: ClaimKind::Statement,
            text: answer[span.start..span.end].to_string(),
            span,
            attributes: Default::default(),
        });
    }

    claims.sort_by_key(|c| c.span);
    for (i, c) in claims.iter_mut().enumerate() {
        c.id = format!("c{i}");
    }
    claims
}

/// A number that belongs to a formula the answer wrote, not to the world:
/// the `100` of `× 100` that turns a ratio into a percentage, and the small
/// divisor of an average, `(47 + 47) / 2`. These are not claims; checking
/// them against the sources only produced false alarms.
fn formula_constant(answer: &str, q: &gl_numeric::Quantity) -> bool {
    if *q.dimension() != Dimension::Dimensionless
        || q.scale_exponent != 0
        || q.numeral.readings.len() != 1
        || q.numeral.readings[0].scale() != 0
    {
        return false;
    }
    let value = q.numeral.readings[0];
    let before = answer[..q.span.start].trim_end();
    let after = answer[q.span.end..].trim_start();
    let times = |s: &str| ["*", "×", "·", "\\times", "\\cdot"].iter().any(|op| s.ends_with(op));
    let times_after = |s: &str| ["*", "×", "·", "\\times", "\\cdot"].iter().any(|op| s.starts_with(op));
    let scaling = (value == 100.into() || value == 1000.into()) && (times(before) || times_after(after));
    let divisor = value >= 2.into()
        && value <= 12.into()
        && ["/", "÷"].iter().any(|op| before.strip_suffix(op).is_some_and(|b| b.trim_end().ends_with(')')));
    scaling || divisor
}

/// The day of a written date: the `31` of "December 31, 2015" or
/// "31 de diciembre". It names a day, not an amount; checking it against the
/// sources only produced false alarms.
fn day_of_a_date(answer: &str, q: &gl_numeric::Quantity) -> bool {
    const MONTHS: &[&str] = &[
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "sept",
        "oct",
        "nov",
        "dec",
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "setiembre",
        "octubre",
        "noviembre",
        "diciembre",
        "gener",
        "febrer",
        "març",
        "maig",
        "juny",
        "juliol",
        "agost",
        "setembre",
        "octubre",
        "novembre",
        "desembre",
        "januar",
        "februar",
        "märz",
        "mai",
        "juni",
        "juli",
        "oktober",
        "dezember",
        "janvier",
        "février",
        "mars",
        "avril",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "décembre",
    ];
    let text = &answer[q.span.start..q.span.end];
    if !text.chars().all(|c| c.is_ascii_digit())
        || text.len() > 2
        || *q.dimension() != Dimension::Dimensionless
    {
        return false;
    }
    let Ok(day) = text.parse::<u32>() else { return false };
    if !(1..=31).contains(&day) {
        return false;
    }
    let is_month = |w: &str| MONTHS.contains(&w.trim_end_matches('.').to_lowercase().as_str());
    let before = answer[..q.span.start].trim_end();
    let prev = before.rsplit(|c: char| c.is_whitespace()).next().unwrap_or("");
    let mut after = answer[q.span.end..].trim_start().trim_start_matches(['.', 'º', 'ª']).trim_start();
    for connector in ["de ", "of "] {
        if let Some(rest) = after.strip_prefix(connector) {
            after = rest;
            break;
        }
    }
    let next: String = after.chars().take_while(|c| c.is_alphabetic() || *c == '.').collect();
    is_month(prev) || is_month(&next)
}

fn dimension_name(d: &Dimension) -> String {
    match d {
        Dimension::Currency(code) => format!("currency:{code}"),
        other => format!("{other:?}").to_lowercase(),
    }
}

/// Sentence spans over `text`, split on `. ! ?` (and their CJK forms) and on
/// line breaks. Whitespace is trimmed and a span with no letter (a bare number
/// or punctuation) is dropped, so only sentences a meaning verifier can use
/// survive.
fn sentences(text: &str) -> Vec<Span> {
    let mut spans = Vec::new();
    let mut start = 0usize;
    let mut idx = 0usize;
    let chars: Vec<char> = text.chars().collect();
    for (i, &c) in chars.iter().enumerate() {
        let end = idx + c.len_utf8();
        // A point between two digits is a decimal point (`$37.35`), not the
        // end of a sentence.
        let decimal = c == '.'
            && i > 0
            && chars[i - 1].is_ascii_digit()
            && chars.get(i + 1).is_some_and(|n| n.is_ascii_digit());
        if !decimal && matches!(c, '.' | '!' | '?' | '\u{3002}' | '\u{FF01}' | '\u{FF1F}' | '\n') {
            if let Some(s) = trim_to_span(text, start, end) {
                spans.push(s);
            }
            start = end;
        }
        idx = end;
    }
    if let Some(s) = trim_to_span(text, start, text.len()) {
        spans.push(s);
    }
    spans
}

fn trim_to_span(text: &str, start: usize, end: usize) -> Option<Span> {
    let slice = &text[start..end];
    let s = start + (slice.len() - slice.trim_start().len());
    let e = end - (slice.len() - slice.trim_end().len());
    if e <= s || !text[s..e].chars().any(|c| c.is_alphabetic()) {
        return None;
    }
    Some(Span::new(s, e))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_decimal_point_does_not_end_a_sentence() {
        let text = "Revenue was $37.35 billion. The line is 1.2 km long.";
        let statements: Vec<&str> = sentences(text).iter().map(|s| &text[s.start..s.end]).collect();
        assert_eq!(statements, ["Revenue was $37.35 billion.", "The line is 1.2 km long."]);
    }

    #[test]
    fn numerals_win_overlaps_and_ids_follow_answer_order() {
        let claims = extract_claims("The invoice total is 1,000 dollars, due in 30 days.", "en");
        // Ignore the whole-sentence Statement claim; check the word/numeric ones.
        let kinds: Vec<_> = claims
            .iter()
            .filter(|c| c.kind != ClaimKind::Statement)
            .map(|c| (c.text.as_str(), c.kind))
            .collect();
        assert_eq!(
            kinds,
            vec![
                ("invoice", ClaimKind::Word),
                ("total", ClaimKind::Word),
                ("1,000 dollars", ClaimKind::Numeric),
                ("due", ClaimKind::Word),
                ("30 days", ClaimKind::Numeric),
            ]
        );
        let usd = claims.iter().find(|c| c.text == "1,000 dollars").unwrap();
        assert_eq!(usd.attributes["dimension"], "currency:USD");
        // Every id is unique and follows answer order.
        assert_eq!(claims[0].id, "c0");
    }

    #[test]
    fn formula_constants_are_not_claims() {
        let claims = extract_claims("(22.1 - 24.0) / 24.0 * 100 = -7.92%, and (47 + 47) / 2 = 47.", "en");
        let numbers: Vec<&str> =
            claims.iter().filter(|c| c.kind == ClaimKind::Numeric).map(|c| c.text.as_str()).collect();
        assert!(!numbers.contains(&"100"), "{numbers:?}");
        assert!(!numbers.contains(&"2"), "{numbers:?}");
        assert!(numbers.contains(&"-7.92%"), "{numbers:?}");
        // A 100 that is a figure stays a claim.
        let claims = extract_claims("The fleet has 100 trucks.", "en");
        assert!(claims
            .iter()
            .any(|c| c.kind == ClaimKind::Numeric && c.text == "100 trucks" || c.text == "100"));
    }

    #[test]
    fn the_day_of_a_date_is_not_a_claim() {
        for answer in [
            "As of December 31, 2015 the balance was $120 million.",
            "At 31 December 2015 the balance was $120 million.",
            "A 31 de diciembre de 2015 el saldo era de 120 millones.",
            "Dec. 31, 2015: $120 million.",
        ] {
            let claims = extract_claims(answer, "en");
            let numeric: Vec<_> =
                claims.iter().filter(|c| c.kind == ClaimKind::Numeric).map(|c| c.text.as_str()).collect();
            assert!(!numeric.contains(&"31"), "{answer}: {numeric:?}");
            assert!(numeric.iter().any(|t| t.contains("120")), "{answer}: {numeric:?}");
        }
        // A count next to a month name that is not a day stays a claim.
        let claims = extract_claims("Revenue grew 45 percent in May.", "en");
        assert!(claims.iter().any(|c| c.kind == ClaimKind::Numeric && c.text.starts_with("45")));
    }

    #[test]
    fn each_sentence_becomes_one_statement_claim() {
        let claims = extract_claims("Revenue grew. The margin held steady.", "en");
        let statements: Vec<&str> =
            claims.iter().filter(|c| c.kind == ClaimKind::Statement).map(|c| c.text.as_str()).collect();
        assert_eq!(statements, vec!["Revenue grew.", "The margin held steady."]);
    }
}
