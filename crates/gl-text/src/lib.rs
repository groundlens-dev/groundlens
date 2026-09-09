//! Normalisation and segmentation. Applied exactly once, before anything
//! else looks at the text. Every span in the engine indexes the normalised
//! string, never the caller's original.

use gl_core::Span;
use regex::Regex;
use std::sync::OnceLock;
use unicode_normalization::UnicodeNormalization;

/// Codepoints deleted outright: they carry no meaning for grounding and they
/// break span arithmetic.
const INVISIBLE: &[char] = &['\u{00AD}', '\u{200B}', '\u{200C}', '\u{200D}', '\u{2060}', '\u{FEFF}'];

/// NFKC, delete invisibles, canonical thin spaces, `\n` line endings,
/// collapse horizontal runs, trim. Idempotent.
pub fn normalise(text: &str) -> String {
    let text = text.replace("\r\n", "\n").replace('\r', "\n");
    // Thin, figure, no-break and narrow no-break spaces are digit group
    // separators in real European documents (1 234,50). NFKC folds all of
    // them to a plain space, so they are parked on a private-use codepoint
    // first and restored as one canonical U+202F afterwards. This is one
    // step further than groundlens 3.x, which lost U+00A0 to NFKC.
    const PARK: char = '\u{E000}';
    let text: String = text
        .chars()
        .map(|c| match c {
            '\u{2009}' | '\u{2007}' | '\u{00A0}' | '\u{202F}' => PARK,
            c => c,
        })
        .collect();
    let text: String = text.nfkc().collect();
    let mut out = String::with_capacity(text.len());
    for ch in text.chars() {
        if INVISIBLE.contains(&ch) {
            continue;
        }
        out.push(if ch == PARK { '\u{202F}' } else { ch });
    }
    let horizontal = re(r"[ \t\x0B\x0C]+");
    let out = horizontal.replace_all(&out, " ");
    let blank = re(r"\n{3,}");
    let out = blank.replace_all(&out, "\n\n");
    out.trim().to_string()
}

pub fn is_normalised(text: &str) -> bool {
    normalise(text) == text
}

/// Function words. A wrong "the" is not a grounding defect.
pub const STOPWORDS_EN: &[&str] = &[
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "of", "to", "in", "on", "at", "by", "for",
    "with", "from", "as", "is", "are", "was", "were", "be", "been", "being", "it", "its", "this", "that",
    "these", "those", "he", "she", "they", "we", "you", "i", "his", "her", "their", "our", "your", "not",
    "no", "yes", "do", "does", "did", "done", "can", "could", "will", "would", "should", "may", "might",
    "must", "have", "has", "had", "about", "into", "over", "under", "between", "also", "such", "more",
    "most", "other", "some", "any", "each", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "than", "too", "very", "just", "only", "there", "here", "what", "while", "during", "per", "via", "upon",
    "within", "without",
];

pub const STOPWORDS_ES: &[&str] = &[
    "el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o", "u", "pero", "si", "de", "del", "a",
    "al", "en", "por", "para", "con", "sin", "sobre", "entre", "es", "son", "era", "eran", "ser", "está",
    "están", "que", "se", "su", "sus", "lo", "le", "les", "no", "sí", "como", "más", "menos", "muy", "ya",
    "también", "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas", "hay", "ha", "han",
];

pub const STOPWORDS_DE: &[&str] = &[
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "eines", "einem", "einen", "und",
    "oder", "aber", "wenn", "dann", "von", "vom", "zu", "zum", "zur", "in", "im", "an", "am", "auf", "für",
    "mit", "aus", "bei", "nach", "über", "unter", "zwischen", "ist", "sind", "war", "waren", "sein", "wird",
    "werden", "wurde", "hat", "haben", "hatte", "es", "er", "sie", "wir", "ihr", "ich", "du", "sich",
    "nicht", "kein", "keine", "ja", "auch", "noch", "nur", "sehr", "als", "wie", "dass", "dies", "diese",
    "dieser", "dieses", "jene", "so", "um",
];

pub const STOPWORDS_FR: &[&str] = &[
    "le", "la", "les", "l", "un", "une", "des", "du", "de", "d", "et", "ou", "mais", "si", "à", "au", "aux",
    "en", "dans", "sur", "sous", "par", "pour", "avec", "sans", "entre", "chez", "est", "sont", "était",
    "étaient", "être", "sera", "seront", "a", "ont", "avait", "avoir", "il", "elle", "ils", "elles", "on",
    "nous", "vous", "je", "tu", "ce", "cet", "cette", "ces", "se", "sa", "son", "ses", "leur", "leurs", "ne",
    "pas", "que", "qui", "quoi", "dont", "où", "y", "aussi", "très", "plus", "moins", "comme", "donc",
    "ainsi",
];

pub const STOPWORDS_IT: &[&str] = &[
    "il", "lo", "la", "i", "gli", "le", "l", "un", "uno", "una", "e", "ed", "o", "ma", "se", "di", "del",
    "dello", "della", "dei", "degli", "delle", "a", "al", "allo", "alla", "ai", "agli", "alle", "da", "dal",
    "dallo", "dalla", "dai", "dagli", "dalle", "in", "nel", "nello", "nella", "nei", "negli", "nelle", "su",
    "sul", "sullo", "sulla", "sui", "sugli", "sulle", "con", "per", "tra", "fra", "è", "sono", "era",
    "erano", "essere", "sarà", "ha", "hanno", "aveva", "avere", "che", "chi", "cui", "si", "non", "più",
    "meno", "molto", "come", "anche", "questo", "questa", "questi", "queste", "quello", "quella", "quelli",
    "quelle", "ci", "vi", "ne", "lui", "lei", "loro", "noi", "voi", "io", "tu",
];

/// The stopword list a locale uses. Unknown locales use English, as
/// groundlens 3.x did for every locale.
pub fn stopwords(locale: &str) -> &'static [&'static str] {
    match locale {
        "es" | "ca" | "gl" => STOPWORDS_ES,
        "de" => STOPWORDS_DE,
        "fr" => STOPWORDS_FR,
        "it" => STOPWORDS_IT,
        _ => STOPWORDS_EN,
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Word {
    pub text: String,
    pub span: Span,
    pub stopword: bool,
}

/// Content words with spans. Numerals are *not* segmented here; the numeric
/// crate claims them first and the pipeline removes overlaps.
pub fn words(text: &str, locale: &str) -> Vec<Word> {
    let pattern = re(r"[^\W\d_](?:[\w'’\-]*[^\W_])?|[^\W\d_]");
    let stop = stopwords(locale);
    pattern
        .find_iter(text)
        .map(|m| {
            let lower = m.as_str().to_lowercase();
            Word {
                text: m.as_str().to_string(),
                span: Span::new(m.start(), m.end()),
                stopword: stop.contains(&lower.as_str()),
            }
        })
        .collect()
}

/// Share of CJK/Thai/Hangul codepoints above which whitespace segmentation is
/// not a defensible way to read the text.
pub const UNSEGMENTED_LIMIT: f64 = 0.30;

pub fn segmentation_warnings(text: &str) -> Vec<String> {
    if text.is_empty() {
        return vec![];
    }
    let total = text.chars().count() as f64;
    let unsegmented = text
        .chars()
        .filter(|c| {
            matches!(*c as u32,
                0x3000..=0x9FFF | 0x0E00..=0x0E7F | 0xAC00..=0xD7AF)
        })
        .count() as f64;
    if unsegmented / total > UNSEGMENTED_LIMIT {
        vec![
            "answer is largely in an unsegmented script (CJK/Thai); whitespace segmentation does not apply and these marks should not be relied on".to_string(),
        ]
    } else {
        vec![]
    }
}

fn re(pattern: &'static str) -> &'static Regex {
    // A handful of patterns; a tiny registry keeps them compiled once.
    static CACHE: OnceLock<std::sync::Mutex<Vec<(&'static str, &'static Regex)>>> = OnceLock::new();
    let cache = CACHE.get_or_init(|| std::sync::Mutex::new(Vec::new()));
    let mut guard = cache.lock().expect("regex cache poisoned");
    if let Some((_, r)) = guard.iter().find(|(p, _)| *p == pattern) {
        return r;
    }
    let compiled: &'static Regex = Box::leak(Box::new(Regex::new(pattern).expect("valid regex")));
    guard.push((pattern, compiled));
    compiled
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalise_is_idempotent_and_folds_fullwidth_digits() {
        let n = normalise("Total:\u{FF11}\u{FF10}\u{FF0C}\u{FF10}\u{FF10}\u{FF10} \r\n\u{200B}due");
        assert_eq!(n, "Total:10,000 \ndue");
        assert!(is_normalised(&n));
    }

    #[test]
    fn nbsp_becomes_narrow_nbsp_group_separator() {
        assert_eq!(normalise("1\u{00A0}234,50"), "1\u{202F}234,50");
    }

    #[test]
    fn words_flag_stopwords_by_locale() {
        let w = words("the invoice total", "en");
        assert_eq!(w.len(), 3);
        assert!(w[0].stopword);
        assert!(!w[1].stopword);
        let w = words("el total de la factura", "es");
        assert!(w[0].stopword && w[2].stopword && w[3].stopword);
        assert!(!w[1].stopword);
    }

    #[test]
    fn cjk_text_warns() {
        assert_eq!(segmentation_warnings("これは日本語の文章です").len(), 1);
        assert!(segmentation_warnings("plain english").is_empty());
    }
}
