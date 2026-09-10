// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Model hosting. Everything a Reproducible verifier needs and nothing else.
//!
//! The reference execution profile is `cpu-f32`: float32 graph run by tract
//! (pure Rust, single thread, no native library). Under that profile the
//! same ONNX file (by sha256) gives scores within `1e-6` across x86_64 and
//! arm64. That is the tolerance the `Reproducible` class declares.
//!
//! Encoders expose token-level vectors with character offsets so the lexical
//! channel (the groundlens 3.x word anchors) aligns words to tokens by span
//! overlap, exactly as the Python library does.

use gl_core::{Result, Span};

/// One window of encoded text. Vectors are L2-normalised.
#[derive(Debug, Clone)]
pub struct WindowEncoding {
    pub token_spans: Vec<Span>,
    pub vectors: Vec<Vec<f32>>,
}

/// The one thing the lexical, semantic and geometric verifiers need.
pub trait Encoder: Send + Sync {
    /// `name@sha256` of the ONNX graph, never a bare model name.
    fn id(&self) -> &str;
    fn max_tokens(&self) -> usize;
    fn token_spans(&self, text: &str) -> Result<Vec<Span>>;
    fn encode_window(&self, text: &str) -> Result<WindowEncoding>;
    /// Pooled sentence vector, L2-normalised. Used by SGI, DGI and semantic
    /// similarity.
    fn encode_sentence(&self, text: &str) -> Result<Vec<f32>>;
}

/// Three-way entailment classifier.
pub trait EntailmentModel: Send + Sync {
    fn id(&self) -> &str;
    /// `(entailment, neutral, contradiction)` probabilities.
    fn classify(&self, premise: &str, hypothesis: &str) -> Result<(f32, f32, f32)>;
}

/// Angular distance on the unit sphere, `arccos(clip(a·b))`, in `[0, π]`.
pub fn angular_distance(a: &[f32], b: &[f32]) -> f64 {
    let dot: f64 = a.iter().zip(b).map(|(x, y)| (*x as f64) * (*y as f64)).sum();
    dot.clamp(-1.0, 1.0).acos()
}

/// Semantic Grounding Index, `θ(r,q) / θ(r,c)` (Marín 2025, arXiv:2512.13771).
/// Above 1 the response departed from the question toward the context.
pub fn sgi(response: &[f32], question: &[f32], context: &[f32]) -> f64 {
    let rq = angular_distance(response, question);
    let rc = angular_distance(response, context);
    rq / (rc + 1e-8)
}

/// Directional Grounding Index, cosine between the unit displacement
/// `(r - q)/|r - q|` and a reference grounding direction `mu_hat`
/// (Marín 2026, arXiv:2602.13224). In `[-1, 1]`.
pub fn dgi(response: &[f32], question: &[f32], mu_hat: &[f32]) -> f64 {
    let delta: Vec<f64> = response.iter().zip(question).map(|(r, q)| (*r as f64) - (*q as f64)).collect();
    let norm = delta.iter().map(|x| x * x).sum::<f64>().sqrt();
    if norm == 0.0 {
        return 0.0;
    }
    delta.iter().zip(mu_hat).map(|(d, m)| d / norm * (*m as f64)).sum::<f64>().clamp(-1.0, 1.0)
}

#[cfg(feature = "runtime")]
pub mod tract;
#[cfg(feature = "runtime")]
pub use tract::{encoder_from_bundle, EncoderSpec, TractEncoder};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sgi_reads_geometry_as_the_paper_defines_it() {
        let q = [1.0f32, 0.0];
        let c = [0.0f32, 1.0];
        let r_lazy = [0.9848f32, 0.1736]; // 10° from q
        let r_grounded = [0.1736f32, 0.9848]; // 10° from c
        assert!(sgi(&r_lazy, &q, &c) < 1.0);
        assert!(sgi(&r_grounded, &q, &c) > 1.0);
    }

    #[test]
    fn dgi_is_plus_one_along_the_reference_direction() {
        let q = [1.0f32, 0.0];
        let r = [0.0f32, 1.0];
        let mu = [-0.70710677f32, 0.70710677];
        assert!((dgi(&r, &q, &mu) - 1.0).abs() < 1e-6);
    }
}

#[cfg(all(test, feature = "runtime"))]
mod tract_tests {
    use super::*;
    use std::path::PathBuf;

    fn tiny() -> TractEncoder {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("testdata/tiny-bundle");
        let spec = EncoderSpec {
            model: "models/tiny.onnx".into(),
            tokenizer: "tokenizers/tiny/tokenizer.json".into(),
            max_tokens: 24,
            prefix: String::new(),
            pooling: "mean".into(),
            dim: 16,
        };
        TractEncoder::load(&root, "tiny", &spec, "sha256:test").unwrap()
    }

    #[test]
    fn spans_are_byte_offsets_and_vectors_are_unit_length() {
        let enc = tiny();
        let text = "Café total 10,000 €";
        let spans = enc.token_spans(text).unwrap();
        // Pieces of "Café" tile the word exactly, on byte boundaries.
        let cafe: Vec<&str> =
            spans.iter().take_while(|s| s.end <= 5).map(|s| &text[s.start..s.end]).collect();
        assert_eq!(cafe.concat(), "Café");
        assert!(spans.iter().any(|s| &text[s.start..s.end] == "total"));
        let w = enc.encode_window(text).unwrap();
        assert_eq!(w.token_spans, spans);
        for v in &w.vectors {
            let n: f32 = v.iter().map(|x| x * x).sum::<f32>().sqrt();
            assert!((n - 1.0).abs() < 1e-5);
        }
        let s = enc.encode_sentence(text).unwrap();
        assert_eq!(s.len(), 16);
    }

    #[test]
    fn prefix_is_invisible_to_spans() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("testdata/tiny-bundle");
        let spec = EncoderSpec {
            model: "models/tiny.onnx".into(),
            tokenizer: "tokenizers/tiny/tokenizer.json".into(),
            max_tokens: 24,
            prefix: "query: ".into(),
            pooling: "mean".into(),
            dim: 16,
        };
        let enc = TractEncoder::load(&root, "tiny", &spec, "sha256:test").unwrap();
        let text = "invoice total";
        let spans = enc.token_spans(text).unwrap();
        assert_eq!(&text[spans[0].start..spans[0].end], "invoice");
        assert_eq!(spans.len(), 2);
    }
}
