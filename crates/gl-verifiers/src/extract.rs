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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn numerals_win_overlaps_and_ids_follow_answer_order() {
        let claims = extract_claims("The invoice total is 1,000 dollars, due in 30 days.", "en");
        let kinds: Vec<_> = claims.iter().map(|c| (c.text.as_str(), c.kind)).collect();
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
        assert_eq!(claims[2].attributes["dimension"], "currency:USD");
        assert_eq!(claims[4].attributes["dimension"], "time");
        assert_eq!(claims[0].id, "c0");
    }
}
