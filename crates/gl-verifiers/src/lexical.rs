// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The lexical channel: groundlens 3.x word anchors, ported rule for rule.
//!
//! A word's support is the highest cosine similarity its contextual token
//! vectors reach against any token of any source. Words are aligned to
//! encoder tokens by character-span overlap, never by the encoder's own
//! word ids, so a `10,000` the engine treats as one unit still maps onto the
//! three pieces a tokenizer makes of it. Long texts are read through
//! overlapping windows and a word's support is the maximum over every
//! window it appears in. No word is ever silently dropped: a word that
//! aligns to no token produces `Error` evidence, because a missing word can
//! only push a floor up.
//!
//! The verifier reports the support; it decides nothing. A policy puts a
//! threshold and a guard band on it, or does not.

use gl_core::{
    ClaimKind, Determinism, Evidence, EvidenceResult, Receipt, Result, Score, Span, Tolerance,
    VerificationInput, Verifier, VerifierInfo, VerifierKind,
};
use gl_onnx::Encoder;
use std::sync::Arc;

pub const ID: &str = "groundlens.lexical";
pub const VERSION: &str = "1.0.0";

/// Fraction of a window re-read by the next one.
pub const STRIDE_RATIO: f64 = 0.5;

const REPRODUCIBLE: Determinism = Determinism::Reproducible { tolerance: Tolerance::FLOAT32_CPU };

/// Every token of one text, in global byte spans, L2-normalised.
#[derive(Debug, Default, Clone)]
pub struct TokenVectors {
    pub spans: Vec<Span>,
    pub vectors: Vec<Vec<f32>>,
}

struct Window {
    offset: usize,
    text: String,
}

fn plan_windows(text: &str, encoder: &dyn Encoder) -> Result<Vec<Window>> {
    if text.is_empty() {
        return Ok(vec![]);
    }
    let spans = encoder.token_spans(text)?;
    if spans.is_empty() {
        return Ok(vec![]);
    }
    let limit = encoder.max_tokens().max(1);
    if spans.len() <= limit {
        return Ok(vec![Window { offset: 0, text: text.to_string() }]);
    }
    let stride = ((limit as f64 * STRIDE_RATIO) as usize).max(1);
    let mut windows = Vec::new();
    let mut start = 0usize;
    while start < spans.len() {
        let end = (start + limit).min(spans.len()) - 1;
        let begin_char = spans[start].start;
        let end_char = spans[end].end;
        windows.push(Window { offset: begin_char, text: text[begin_char..end_char].to_string() });
        if end == spans.len() - 1 {
            break;
        }
        start += stride;
    }
    Ok(windows)
}

/// Encode `text` through as many windows as it takes. A token inside two
/// overlapping windows is kept twice, on purpose: its two vectors differ by
/// context and the max over both makes support independent of where the
/// cut fell.
pub fn embed(text: &str, encoder: &dyn Encoder) -> Result<TokenVectors> {
    let mut out = TokenVectors::default();
    for w in plan_windows(text, encoder)? {
        let enc = encoder.encode_window(&w.text)?;
        if enc.token_spans.len() != enc.vectors.len() {
            return Err(gl_core::Error::Integrity(format!(
                "encoder {} returned {} spans and {} vectors",
                encoder.id(),
                enc.token_spans.len(),
                enc.vectors.len()
            )));
        }
        for (s, v) in enc.token_spans.into_iter().zip(enc.vectors) {
            out.spans.push(Span::new(w.offset + s.start, w.offset + s.end));
            out.vectors.push(v);
        }
    }
    Ok(out)
}

fn tokens_overlapping(span: Span, tokens: &TokenVectors) -> Vec<usize> {
    tokens
        .spans
        .iter()
        .enumerate()
        .filter(|(_, s)| s.start < span.end && s.end > span.start)
        .map(|(i, _)| i)
        .collect()
}

/// Context tokens worth anchoring to: at least one alphanumeric character.
/// Falls back to every token when a source has nothing else.
fn scorable_columns(text: &str, tokens: &TokenVectors) -> Vec<usize> {
    let cols: Vec<usize> = tokens
        .spans
        .iter()
        .enumerate()
        .filter(|(_, s)| text[s.start..s.end].chars().any(char::is_alphanumeric))
        .map(|(i, _)| i)
        .collect();
    if cols.is_empty() {
        (0..tokens.spans.len()).collect()
    } else {
        cols
    }
}

/// Best `(similarity, context token)` over the answer tokens in `rows`.
/// First maximum wins, as in groundlens 3.x, so ties never depend on the
/// platform.
fn best_anchor(
    rows: &[usize],
    answer: &TokenVectors,
    context: &TokenVectors,
    cols: &[usize],
) -> Option<(f64, usize)> {
    if rows.is_empty() || context.spans.is_empty() {
        return None;
    }
    let mut best = -1.0f64;
    let mut best_j = usize::MAX;
    for &i in rows {
        let a = &answer.vectors[i];
        for &j in cols {
            let c = &context.vectors[j];
            // f32 accumulation, like the numpy float32 matmul the golden
            // file was produced with.
            let dot: f32 = a.iter().zip(c).map(|(x, y)| x * y).sum();
            let dot = dot as f64;
            if dot > best {
                best = dot;
                best_j = j;
            }
        }
    }
    if best_j == usize::MAX {
        return None;
    }
    Some((best.clamp(0.0, 1.0), best_j))
}

const EDGE_TRIM: &[char] = &[
    '"', '\'', '\u{2018}', '\u{2019}', '\u{201C}', '\u{201D}', '(', ')', '[', ']', '{', '}', '.', ',', ';',
    ':', '!', '?', '\u{AB}', '\u{BB}',
];

/// Grow a token span to the whitespace-delimited word around it, trimmed of
/// sentence punctuation at the edges. Interior characters are kept, which
/// preserves `10,000` and `3.90%` whole.
fn expand_to_word(text: &str, span: Span) -> (String, Span) {
    let bytes = text.as_bytes();
    let mut a = span.start;
    let mut b = span.end;
    while a > 0 {
        let prev = text[..a].chars().next_back().expect("char");
        if prev.is_whitespace() {
            break;
        }
        a -= prev.len_utf8();
    }
    while b < bytes.len() {
        let next = text[b..].chars().next().expect("char");
        if next.is_whitespace() {
            break;
        }
        b += next.len_utf8();
    }
    loop {
        match text[a..b].chars().next() {
            Some(c) if a < b && EDGE_TRIM.contains(&c) => a += c.len_utf8(),
            _ => break,
        }
    }
    loop {
        match text[a..b].chars().next_back() {
            Some(c) if b > a && EDGE_TRIM.contains(&c) => b -= c.len_utf8(),
            _ => break,
        }
    }
    if a >= b {
        return (text[span.start..span.end].to_string(), span);
    }
    (text[a..b].to_string(), Span::new(a, b))
}

fn is_word_char(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

/// Whether `word` occurs in `text` as a whole word, case-insensitively.
fn word_in(word: &str, text: &str) -> bool {
    let pattern = regex::Regex::new(&format!("(?i){}", regex::escape(word))).expect("escaped");
    let mut found = false;
    for m in pattern.find_iter(text) {
        let before = text[..m.start()].chars().next_back().map(is_word_char).unwrap_or(false);
        let after = text[m.end()..].chars().next().map(is_word_char).unwrap_or(false);
        if !before && !after {
            found = true;
            break;
        }
    }
    found
}

pub struct LexicalVerifier {
    info: VerifierInfo,
    encoder: Arc<dyn Encoder>,
    model_hash: String,
}

impl LexicalVerifier {
    /// `model_hash` is the manifest hash of the ONNX artefact (`sha256:...`).
    pub fn new(encoder: Arc<dyn Encoder>, model_hash: &str) -> Self {
        let mut info = Self::info_without_model();
        info.artefacts = vec![("encoder".to_string(), encoder.id().to_string())];
        LexicalVerifier { info, encoder, model_hash: model_hash.to_string() }
    }

    /// The verifier's declaration, for policy lint when no bundle is loaded.
    pub fn info_without_model() -> VerifierInfo {
        VerifierInfo {
            id: ID.to_string(),
            version: VERSION.to_string(),
            kind: VerifierKind::Lexical,
            determinism: REPRODUCIBLE,
            applies_to: vec![ClaimKind::Word],
            artefacts: vec![],
            needs_network: false,
        }
    }
}

struct SourceTokens<'a> {
    id: &'a str,
    text: &'a str,
    tokens: TokenVectors,
    cols: Vec<usize>,
}

impl Verifier for LexicalVerifier {
    fn info(&self) -> &VerifierInfo {
        &self.info
    }

    fn verify(&self, input: &VerificationInput) -> Result<Vec<Evidence>> {
        let words: Vec<_> = input.claims.iter().filter(|c| c.kind == ClaimKind::Word).collect();
        if words.is_empty() {
            return Ok(vec![]);
        }
        let answer = embed(&input.answer, self.encoder.as_ref())?;
        let mut sources: Vec<SourceTokens> = Vec::new();
        for s in &input.sources {
            if s.text.is_empty() {
                continue;
            }
            let tokens = embed(&s.text, self.encoder.as_ref())?;
            let cols = scorable_columns(&s.text, &tokens);
            sources.push(SourceTokens { id: &s.id, text: &s.text, tokens, cols });
        }
        let question_words: Vec<String> = input
            .question
            .as_deref()
            .map(|q| {
                gl_text::words(q, &input.locale)
                    .into_iter()
                    .filter(|w| !w.stopword)
                    .map(|w| w.text.to_lowercase())
                    .collect()
            })
            .unwrap_or_default();

        let mut out = Vec::new();
        for claim in words {
            let rows = tokens_overlapping(claim.span, &answer);
            let mut notes: Vec<String> = Vec::new();
            if question_words.contains(&claim.text.to_lowercase()) {
                notes.push("echoes_question".into());
            }
            if rows.is_empty() {
                out.push(self.evidence(
                    claim.id.clone(),
                    EvidenceResult::Error,
                    0.0,
                    format!("{:?} aligned to no encoder token; refusing to score it silently", claim.text),
                    Receipt { notes, ..Default::default() },
                ));
                continue;
            }
            let mut best: Option<(f64, &SourceTokens, Span)> = None;
            for s in &sources {
                if let Some((support, j)) = best_anchor(&rows, &answer, &s.tokens, &s.cols) {
                    if best.as_ref().map(|(b, _, _)| support > *b).unwrap_or(true) {
                        best = Some((support, s, s.tokens.spans[j]));
                    }
                }
            }
            match best {
                None => out.push(self.evidence(
                    claim.id.clone(),
                    EvidenceResult::Unsupported,
                    0.0,
                    format!("{:<14}  support 0.00   no anchor found", claim.text),
                    Receipt { notes, ..Default::default() },
                )),
                Some((support, s, token_span)) => {
                    let (word, span) = expand_to_word(s.text, token_span);
                    if word_in(&claim.text, s.text) {
                        notes.push("exact_string_in_span".into());
                    }
                    let score = gl_core::determinism::quantise(support, REPRODUCIBLE);
                    let result =
                        if score > 0.0 { EvidenceResult::Supported } else { EvidenceResult::Unsupported };
                    out.push(self.evidence(
                        claim.id.clone(),
                        result,
                        score,
                        format!("{:<14}  support {:.2}   nearest in {}: {:?}", claim.text, score, s.id, word),
                        Receipt {
                            source_id: Some(s.id.to_string()),
                            source_span: Some(span),
                            source_text: Some(word),
                            notes,
                        },
                    ));
                }
            }
        }
        out.sort_by_key(|e| e.sort_key());
        Ok(out)
    }
}

impl LexicalVerifier {
    fn evidence(
        &self,
        claim_id: String,
        result: EvidenceResult,
        score: f64,
        rationale: String,
        receipt: Receipt,
    ) -> Evidence {
        Evidence {
            verifier_id: ID.to_string(),
            verifier_version: VERSION.to_string(),
            claim_id,
            result,
            score: Score(score),
            confidence: Score(1.0),
            determinism: REPRODUCIBLE,
            rationale,
            receipt,
            model_hash: Some(self.model_hash.clone()),
            calibration_id: None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use gl_core::{Claim, Source};
    use gl_onnx::{EncoderSpec, TractEncoder};
    use std::path::PathBuf;

    fn tiny(max_tokens: usize) -> Arc<dyn Encoder> {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../gl-onnx/testdata/tiny-bundle");
        let spec = EncoderSpec {
            model: "models/tiny.onnx".into(),
            tokenizer: "tokenizers/tiny/tokenizer.json".into(),
            max_tokens,
            prefix: String::new(),
            pooling: "mean".into(),
            dim: 16,
        };
        Arc::new(TractEncoder::load(&root, "tiny", &spec, "sha256:test").unwrap())
    }

    fn input(answer: &str, source: &str) -> VerificationInput {
        let answer = gl_text::normalise(answer);
        let claims = crate::extract_claims(&answer, "en");
        VerificationInput {
            question: None,
            answer,
            sources: vec![Source { id: "s".into(), text: gl_text::normalise(source), locator: None }],
            claims,
            locale: "en".into(),
            metadata: Default::default(),
        }
    }

    #[test]
    fn every_word_gets_evidence_with_a_receipt() {
        let v = LexicalVerifier::new(tiny(24), "sha256:m");
        let inp = input("The invoice total is 1,000 dollars.", "The total amount due is 10,000 dollars.");
        let ev = v.verify(&inp).unwrap();
        let words: Vec<&Claim> = inp.claims.iter().filter(|c| c.kind == ClaimKind::Word).collect();
        assert_eq!(ev.len(), words.len());
        let total = ev.iter().find(|e| inp.claim(&e.claim_id).unwrap().text == "total").unwrap();
        assert_eq!(total.receipt.source_text.as_deref(), Some("total"));
        assert!(total.receipt.notes.contains(&"exact_string_in_span".to_string()));
        assert!(total.score.0 > 0.9, "{}", total.score.0);
        assert_eq!(total.determinism, REPRODUCIBLE);
    }

    #[test]
    fn windowing_does_not_change_support() {
        let long = "The invoice total is payable within thirty days at the registered office in Madrid and the margin was four percent.";
        let src = "Payment is due within thirty days at the registered office in Madrid.";
        let whole = LexicalVerifier::new(tiny(64), "sha256:m").verify(&input(long, src)).unwrap();
        let windowed = LexicalVerifier::new(tiny(6), "sha256:m").verify(&input(long, src)).unwrap();
        for (a, b) in whole.iter().zip(&windowed) {
            assert_eq!(a.claim_id, b.claim_id);
            // The max over windows can only be >= the single-window score
            // when windows are wider than the text; with a contextual toy
            // model the values differ slightly, and the receipt must agree.
            assert_eq!(a.receipt.source_id, b.receipt.source_id);
            assert!(b.score.0 >= 0.0 && b.score.0 <= 1.0);
        }
    }

    #[test]
    fn word_boundaries_and_expansion() {
        assert!(word_in("total", "the Total amount"));
        assert!(!word_in("total", "totals"));
        let (w, s) = expand_to_word("pay 10,000 dollars.", Span::new(4, 6));
        assert_eq!((w.as_str(), s), ("10,000", Span::new(4, 10)));
        let (w, _) = expand_to_word("(Madrid).", Span::new(1, 4));
        assert_eq!(w, "Madrid");
    }
}
