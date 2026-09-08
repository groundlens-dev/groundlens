//! Bare numerals: port of groundlens 3.x `_numerals.py`, same rules.
//!
//! * `Decimal`, never float.
//! * An ambiguous numeral (`1.234` under `und`) keeps every legitimate
//!   reading. Abstaining would drop a claim and inflate the floor.
//! * A sign binds only when it touches the currency symbol or the digit:
//!   "payment - $101,755" is a punctuation dash (groundlens PR #221).
//! * Digit-group repetition is bounded so adversarial input cannot make the
//!   regex backtrack quadratically.

use gl_core::Span;
use regex::Regex;
use rust_decimal::Decimal;
use std::str::FromStr;
use std::sync::OnceLock;

use crate::locale::LocaleProfile;

pub const GROUP_SIZE: usize = 3;
pub const MIN_DIGITS: usize = 2;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Numeral {
    pub text: String,
    pub span: Span,
    pub readings: Vec<Decimal>,
    pub notes: Vec<&'static str>,
    /// Currency symbol that touched the numeral, if any (`$`, `€`).
    pub currency_symbol: Option<char>,
    pub percent: bool,
    /// Number of significant digits as written, ignoring separators and
    /// leading zeros. `37.35` → 4, `37,350` → 5, `0.05` → 1.
    pub significant_digits: u32,
}

impl Numeral {
    pub fn ambiguous(&self) -> bool {
        self.readings.len() > 1
    }
}

fn pattern() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(
            r"(?x)
            (?P<open>\()?
            (?P<sign>[-−–+])?
            (?:(?P<cur>[$€£¥₹])\s?)?
            (?P<body>
                \d{1,3}(?:[\u{202F}\u{00A0}\u{2009}\u{2007}\ ]\d{3}){1,8}(?:[.,]\d{1,9})?
              | \d{1,3}(?:['’]\d{3}){1,8}(?:[.,]\d{1,9})?
              | \d{1,3}(?:[.,]\d{3}){1,8}(?:[.,]\d{1,9})?
              | \d+(?:[.,]\d{1,9})?
            )
            (?P<pct>\s?[%٪])?
            (?P<close>\))?
            ",
        )
        .expect("numeral regex")
    })
}

fn plain() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^\d+(?:[.,]\d{1,9})?").expect("plain numeral regex"))
}

fn to_decimal(digits: &str) -> Option<Decimal> {
    Decimal::from_str(digits).ok()
}

fn readings(body: &str, profile: &LocaleProfile) -> (Vec<Decimal>, Vec<&'static str>) {
    let body: String = body
        .chars()
        .filter(|c| !matches!(c, '\u{202F}' | '\u{00A0}' | '\u{2009}' | '\u{2007}' | ' ' | '\'' | '’'))
        .collect();
    let seps: Vec<char> = body.chars().filter(|c| *c == '.' || *c == ',').collect();

    if seps.is_empty() {
        return (to_decimal(&body).into_iter().collect(), vec![]);
    }

    if let (Some(dec), grp) = (profile.decimal_sep, profile.group_sep) {
        let stripped: String = body.chars().filter(|c| Some(*c) != grp).collect();
        let normalised = stripped.replace(dec, ".");
        return (to_decimal(&normalised).into_iter().collect(), vec![]);
    }

    let mut distinct = seps.clone();
    distinct.sort_unstable();
    distinct.dedup();
    if distinct.len() == 2 {
        // Both separators present: the last one is the decimal point.
        let last_dot = body.rfind('.');
        let last_comma = body.rfind(',');
        let dec = if last_dot > last_comma { '.' } else { ',' };
        let grp = if dec == '.' { ',' } else { '.' };
        let cleaned: String = body.chars().filter(|c| *c != grp).collect();
        return (to_decimal(&cleaned.replace(dec, ".")).into_iter().collect(), vec![]);
    }

    let sep = seps[0];
    let tail_len = body.rsplit(sep).next().map(str::len).unwrap_or(0);
    if seps.len() > 1 {
        let cleaned: String = body.chars().filter(|c| *c != sep).collect();
        return (to_decimal(&cleaned).into_iter().collect(), vec!["separator_repeated"]);
    }
    if tail_len != GROUP_SIZE {
        return (to_decimal(&body.replace(sep, ".")).into_iter().collect(), vec![]);
    }
    let grouped = to_decimal(&body.chars().filter(|c| *c != sep).collect::<String>());
    let fractional = to_decimal(&body.replace(sep, "."));
    let values: Vec<Decimal> = grouped.into_iter().chain(fractional).collect();
    if values.len() < 2 {
        (values, vec!["grouping_malformed"])
    } else {
        (values, vec!["grouping_vs_decimal"])
    }
}

fn significant_digits(body: &str) -> u32 {
    let digits: String = body.chars().filter(char::is_ascii_digit).collect();
    let trimmed = digits.trim_start_matches('0');
    if trimmed.is_empty() {
        1
    } else {
        trimmed.len() as u32
    }
}

/// Every numeral in `text`, with spans into `text`.
pub fn find_numerals(text: &str, profile: &LocaleProfile) -> Vec<Numeral> {
    let mut found = Vec::new();
    let mut pos = 0usize;
    while pos <= text.len() {
        let Some(caps) = pattern().captures_at(text, pos) else { break };
        let whole = caps.get(0).expect("match");
        pos = whole.end().max(pos + 1);
        let mut body = caps["body"].to_string();
        let mut end = whole.end();
        // The grouped alternatives cannot say "not followed by a digit"
        // (no lookahead in this regex engine). When a digit follows, the
        // grouping reading was an illusion: re-read the run as a plain
        // decimal from the same start.
        if text[end..].chars().next().is_some_and(|c| c.is_ascii_digit()) {
            let body_start = caps.name("body").expect("body").start();
            let Some(m) = plain().find(&text[body_start..]) else { continue };
            body = m.as_str().to_string();
            end = body_start + m.end();
            if text[end..].chars().next().is_some_and(|c| c.is_ascii_digit()) {
                pos = end;
                continue;
            }
            pos = end;
        }
        let body = body.as_str();
        if body.chars().filter(char::is_ascii_digit).count() < MIN_DIGITS {
            continue;
        }
        let (mut values, notes) = readings(body, profile);
        if values.is_empty() {
            continue;
        }
        let sign = caps.name("sign").map(|m| m.as_str());
        let negative =
            sign.is_some_and(|s| s != "+") || (caps.name("open").is_some() && caps.name("close").is_some());
        if negative {
            for v in values.iter_mut() {
                *v = -*v;
            }
        }
        let raw = &text[whole.start()..end];
        let lead = raw.len() - raw.trim_start().len();
        let trail = raw.len() - raw.trim_end().len();
        found.push(Numeral {
            text: raw.trim().to_string(),
            span: Span::new(whole.start() + lead, end - trail),
            readings: values,
            notes,
            currency_symbol: caps.name("cur").and_then(|m| m.as_str().chars().next()),
            percent: caps.name("pct").is_some(),
            significant_digits: significant_digits(body),
        });
    }
    found
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::locale::locale;

    fn vals(text: &str, loc: &str) -> Vec<Vec<String>> {
        find_numerals(text, &locale(loc).unwrap())
            .into_iter()
            .map(|n| n.readings.iter().map(|d| d.normalize().to_string()).collect())
            .collect()
    }

    #[test]
    fn grouping_and_decimal_by_locale() {
        assert_eq!(vals("1.234", "es"), vec![vec!["1234"]]);
        assert_eq!(vals("1.234", "en"), vec![vec!["1.234"]]);
        assert_eq!(vals("1.234", "und"), vec![vec!["1234", "1.234"]]);
        assert_eq!(vals("1.234.567", "und"), vec![vec!["1234567"]]);
        assert_eq!(vals("10,000.50", "und"), vec![vec!["10000.5"]]);
        assert_eq!(vals("1.23456", "und"), vec![vec!["1.23456"]]);
        assert_eq!(vals("x 3.1416 y", "en"), vec![vec!["3.1416"]]);
    }

    #[test]
    fn single_digits_are_skipped_and_signs_bind_only_when_touching() {
        assert!(vals("page 5 of 7", "en").is_empty());
        let n = find_numerals("payment - $101,755", &locale("en").unwrap());
        assert_eq!(n[0].readings[0].to_string(), "101755");
        let n = find_numerals("delta -$101,755", &locale("en").unwrap());
        assert_eq!(n[0].readings[0].to_string(), "-101755");
        assert_eq!(n[0].currency_symbol, Some('$'));
    }

    #[test]
    fn percent_and_significance() {
        let n = &find_numerals("rate of 4.75%", &locale("en").unwrap())[0];
        assert!(n.percent);
        assert_eq!(n.significant_digits, 3);
        let n = &find_numerals("0.0500 kg", &locale("en").unwrap())[0];
        assert_eq!(n.significant_digits, 3);
    }
}
