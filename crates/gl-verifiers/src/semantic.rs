// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The semantic channel: how close, in the encoder's meaning space, is the
//! claim to the nearest source?
//!
//! For each statement claim the verifier pools a sentence vector for the claim
//! and for every source, and keeps the source with the highest cosine
//! similarity. Both vectors are L2-normalised, so cosine is their dot product;
//! it is clamped to `[0, 1]` and reported on the same "higher means more
//! support" scale as every other verifier. Similarity is not entailment: two
//! sentences can be close and still disagree, so this channel never reports a
//! contradiction. It reports the support; a policy puts a threshold and a
//! guard band on it, or does not.

use std::sync::Arc;

use gl_core::{
    ClaimKind, Determinism, Evidence, EvidenceResult, Receipt, Result, Score, Tolerance, VerificationInput,
    Verifier, VerifierInfo, VerifierKind,
};
use gl_onnx::Encoder;

pub const ID: &str = "semantic.cosine";
pub const VERSION: &str = "1.0.0";

const REPRODUCIBLE: Determinism = Determinism::Reproducible { tolerance: Tolerance::FLOAT32_CPU };

pub struct SemanticVerifier {
    info: VerifierInfo,
    encoder: Arc<dyn Encoder>,
    model_hash: String,
}

impl SemanticVerifier {
    /// `model_hash` is the manifest hash of the ONNX artefact (`sha256:...`).
    pub fn new(encoder: Arc<dyn Encoder>, model_hash: &str) -> Self {
        let mut info = Self::info_without_model();
        info.artefacts = vec![("encoder".to_string(), encoder.id().to_string())];
        SemanticVerifier { info, encoder, model_hash: model_hash.to_string() }
    }

    /// The verifier's declaration, for policy lint when no bundle is loaded.
    pub fn info_without_model() -> VerifierInfo {
        VerifierInfo {
            id: ID.to_string(),
            version: VERSION.to_string(),
            kind: VerifierKind::Ml,
            determinism: REPRODUCIBLE,
            applies_to: vec![ClaimKind::Statement],
            artefacts: vec![],
            needs_network: false,
        }
    }

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

/// Cosine of two L2-normalised vectors, accumulated in f32 like the numpy
/// float32 matmul the reference values are produced with, then clamped to the
/// support scale.
fn cosine(a: &[f32], b: &[f32]) -> f64 {
    let dot: f32 = a.iter().zip(b).map(|(x, y)| x * y).sum();
    (dot as f64).clamp(0.0, 1.0)
}

impl Verifier for SemanticVerifier {
    fn info(&self) -> &VerifierInfo {
        &self.info
    }

    fn verify(&self, input: &VerificationInput) -> Result<Vec<Evidence>> {
        let claims: Vec<_> = input.claims.iter().filter(|c| c.kind == ClaimKind::Statement).collect();
        if claims.is_empty() {
            return Ok(vec![]);
        }
        // Encode every non-empty source once; claims are compared against all.
        let mut sources: Vec<(&str, &str, Vec<f32>)> = Vec::new();
        for s in &input.sources {
            if s.text.is_empty() {
                continue;
            }
            sources.push((&s.id, &s.text, self.encoder.encode_sentence(&s.text)?));
        }

        let mut out = Vec::new();
        for claim in claims {
            let cv = self.encoder.encode_sentence(&claim.text)?;
            // Best source by cosine. First maximum wins, so a tie never
            // depends on the platform.
            let mut best: Option<(f64, &str, &str)> = None;
            for (sid, stext, sv) in &sources {
                let sim = cosine(&cv, sv);
                if best.as_ref().map(|(b, ..)| sim > *b).unwrap_or(true) {
                    best = Some((sim, sid, stext));
                }
            }
            match best {
                None => out.push(self.evidence(
                    claim.id.clone(),
                    EvidenceResult::Unsupported,
                    0.0,
                    format!("{:?}: no source to compare against", claim.text),
                    Receipt { notes: vec!["no_sources".into()], ..Default::default() },
                )),
                Some((sim, sid, stext)) => {
                    let score = gl_core::determinism::quantise(sim, REPRODUCIBLE);
                    let result =
                        if score > 0.0 { EvidenceResult::Supported } else { EvidenceResult::Unsupported };
                    out.push(self.evidence(
                        claim.id.clone(),
                        result,
                        score,
                        format!("cosine {score:.2} against {sid}"),
                        Receipt {
                            source_id: Some(sid.to_string()),
                            source_text: Some(stext.to_string()),
                            notes: vec![],
                            ..Default::default()
                        },
                    ));
                }
            }
        }
        out.sort_by_key(|e| e.sort_key());
        Ok(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use gl_core::{Claim, ClaimKind, Source, Span};
    use gl_onnx::{EncoderSpec, TractEncoder};
    use indexmap::IndexMap;
    use std::path::PathBuf;

    fn tiny() -> Arc<dyn Encoder> {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../gl-onnx/testdata/tiny-bundle");
        let spec = EncoderSpec {
            model: "models/tiny.onnx".into(),
            tokenizer: "tokenizers/tiny/tokenizer.json".into(),
            max_tokens: 32,
            prefix: String::new(),
            pooling: "mean".into(),
            dim: 16,
        };
        Arc::new(TractEncoder::load(&root, "tiny", &spec, "sha256:test").unwrap())
    }

    fn statement(id: &str, text: &str) -> Claim {
        Claim {
            id: id.into(),
            kind: ClaimKind::Statement,
            text: text.into(),
            span: Span::new(0, text.len()),
            attributes: IndexMap::new(),
        }
    }

    fn input(claims: Vec<Claim>, sources: Vec<(&str, &str)>) -> VerificationInput {
        VerificationInput {
            question: None,
            answer: claims.first().map(|c| c.text.clone()).unwrap_or_default(),
            sources: sources
                .into_iter()
                .map(|(id, t)| Source { id: id.into(), text: t.into(), locator: None })
                .collect(),
            claims,
            locale: "en".into(),
            metadata: Default::default(),
        }
    }

    #[test]
    fn one_evidence_per_statement_with_a_receipt() {
        let v = SemanticVerifier::new(tiny(), "sha256:m");
        let inp = input(
            vec![statement("c0", "The invoice total is 10,000 dollars.")],
            vec![("s", "The total amount due is 10,000 dollars.")],
        );
        let ev = v.verify(&inp).unwrap();
        assert_eq!(ev.len(), 1);
        let e = &ev[0];
        assert_eq!(e.claim_id, "c0");
        assert!((0.0..=1.0).contains(&e.score.0));
        assert_eq!(e.receipt.source_id.as_deref(), Some("s"));
        assert_eq!(e.determinism, REPRODUCIBLE);
        assert_eq!(e.model_hash.as_deref(), Some("sha256:m"));
    }

    #[test]
    fn score_is_deterministic_across_runs() {
        let v = SemanticVerifier::new(tiny(), "sha256:m");
        let inp = input(
            vec![statement("c0", "The invoice total is 10,000 dollars.")],
            vec![("s", "The total amount due is 10,000 dollars.")],
        );
        assert_eq!(v.verify(&inp).unwrap()[0].score.0, v.verify(&inp).unwrap()[0].score.0);
    }

    #[test]
    fn no_sources_is_unsupported_not_a_panic() {
        let v = SemanticVerifier::new(tiny(), "sha256:m");
        let inp = input(vec![statement("c0", "Anything at all.")], vec![]);
        let ev = v.verify(&inp).unwrap();
        assert_eq!(ev.len(), 1);
        assert_eq!(ev[0].result, EvidenceResult::Unsupported);
        assert!(ev[0].receipt.notes.contains(&"no_sources".to_string()));
    }

    #[test]
    fn non_statement_claims_are_ignored() {
        let v = SemanticVerifier::new(tiny(), "sha256:m");
        let mut word = statement("w0", "total");
        word.kind = ClaimKind::Word;
        let inp = input(vec![word], vec![("s", "the total")]);
        assert!(v.verify(&inp).unwrap().is_empty());
    }
}
