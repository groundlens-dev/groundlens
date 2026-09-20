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
    for c in text.chars() {
        let end = idx + c.len_utf8();
        if matches!(c, '.' | '!' | '?' | '\u{3002}' | '\u{FF01}' | '\u{FF1F}' | '\n') {
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
    fn each_sentence_becomes_one_statement_claim() {
        let claims = extract_claims("Revenue grew. The margin held steady.", "en");
        let statements: Vec<&str> =
            claims.iter().filter(|c| c.kind == ClaimKind::Statement).map(|c| c.text.as_str()).collect();
        assert_eq!(statements, vec!["Revenue grew.", "The margin held steady."]);
    }
}
