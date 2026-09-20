// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The NLI channel: does a source *entail* the claim, *contradict* it, or
//! neither?
//!
//! For each statement claim the verifier runs the entailment model over every
//! source with the source as premise and the claim as hypothesis, and keeps
//! the source with the highest entailment. The three probabilities decide the
//! result (entailment, contradiction or neither) and the entailment
//! probability is the score, on the same "higher means more support" scale as
//! every other verifier. It reports evidence; a policy puts a threshold and a
//! guard band on it, or does not.

use std::sync::Arc;

use gl_core::{
    ClaimKind, Determinism, Evidence, EvidenceResult, Receipt, Result, Score, Tolerance, VerificationInput,
    Verifier, VerifierInfo, VerifierKind,
};
use gl_onnx::EntailmentModel;

pub const ID: &str = "groundlens.nli";
pub const VERSION: &str = "1.0.0";

const REPRODUCIBLE: Determinism = Determinism::Reproducible { tolerance: Tolerance::FLOAT32_CPU };

pub struct NliVerifier {
    info: VerifierInfo,
    model: Arc<dyn EntailmentModel>,
    model_hash: String,
}

impl NliVerifier {
    /// `model_hash` is the manifest hash of the ONNX artefact (`sha256:...`).
    pub fn new(model: Arc<dyn EntailmentModel>, model_hash: &str) -> Self {
        let mut info = Self::info_without_model();
        info.artefacts = vec![("model".to_string(), model.id().to_string())];
        NliVerifier { info, model, model_hash: model_hash.to_string() }
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

    #[allow(clippy::too_many_arguments)]
    fn evidence(
        &self,
        claim_id: String,
        result: EvidenceResult,
        score: f64,
        confidence: f64,
        rationale: String,
        receipt: Receipt,
    ) -> Evidence {
        Evidence {
            verifier_id: ID.to_string(),
            verifier_version: VERSION.to_string(),
            claim_id,
            result,
            score: Score(score),
            confidence: Score(confidence),
            determinism: REPRODUCIBLE,
            rationale,
            receipt,
            model_hash: Some(self.model_hash.clone()),
            calibration_id: None,
        }
    }
}

/// The three probabilities and which of them won.
fn label_of(entail: f32, neutral: f32, contra: f32) -> EvidenceResult {
    if entail >= neutral && entail >= contra {
        EvidenceResult::Supported
    } else if contra >= neutral {
        EvidenceResult::Contradicted
    } else {
        EvidenceResult::Unsupported
    }
}

impl Verifier for NliVerifier {
    fn info(&self) -> &VerifierInfo {
        &self.info
    }

    fn verify(&self, input: &VerificationInput) -> Result<Vec<Evidence>> {
        let claims: Vec<_> = input.claims.iter().filter(|c| c.kind == ClaimKind::Statement).collect();
        if claims.is_empty() {
            return Ok(vec![]);
        }
        let mut out = Vec::new();
        for claim in claims {
            // Best source by entailment probability. First maximum wins, so a
            // tie never depends on the platform.
            let mut best: Option<(f32, f32, f32, &str, &str)> = None;
            for s in &input.sources {
                if s.text.is_empty() {
                    continue;
                }
                let (e, n, c) = self.model.classify(&s.text, &claim.text)?;
                if best.as_ref().map(|(be, ..)| e > *be).unwrap_or(true) {
                    best = Some((e, n, c, &s.id, &s.text));
                }
            }
            match best {
                None => out.push(self.evidence(
                    claim.id.clone(),
                    EvidenceResult::Unsupported,
                    0.0,
                    1.0,
                    format!("{:?}: no source to check against", claim.text),
                    Receipt { notes: vec!["no_sources".into()], ..Default::default() },
                )),
                Some((e, n, c, sid, stext)) => {
                    let result = label_of(e, n, c);
                    let score = gl_core::determinism::quantise(e as f64, REPRODUCIBLE);
                    let confidence = gl_core::determinism::quantise(e.max(n).max(c) as f64, REPRODUCIBLE);
                    out.push(self.evidence(
                        claim.id.clone(),
                        result,
                        score,
                        confidence,
                        format!("entailment {score:.2} (neutral {n:.2}, contradiction {c:.2}) against {sid}"),
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
    use gl_onnx::{EntailmentSpec, TractEntailment};
    use indexmap::IndexMap;
    use std::path::PathBuf;

    fn tiny() -> Arc<dyn EntailmentModel> {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../gl-onnx/testdata/tiny-nli");
        let spec = EntailmentSpec {
            model: "models/tiny.onnx".into(),
            tokenizer: "tokenizers/tiny/tokenizer.json".into(),
            max_tokens: 32,
            labels: vec!["entailment".into(), "neutral".into(), "contradiction".into()],
        };
        Arc::new(TractEntailment::load(&root, "tiny-nli", &spec, "sha256:m").unwrap())
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
        let v = NliVerifier::new(tiny(), "sha256:m");
        let inp = input(
            vec![statement("c0", "The invoice total is 10,000 dollars.")],
            vec![("s", "The total amount due is 10,000 dollars.")],
        );
        let ev = v.verify(&inp).unwrap();
        assert_eq!(ev.len(), 1);
        let e = &ev[0];
        assert_eq!(e.claim_id, "c0");
        assert!((0.0..=1.0).contains(&e.score.0) && (0.0..=1.0).contains(&e.confidence.0));
        assert!(matches!(
            e.result,
            EvidenceResult::Supported | EvidenceResult::Contradicted | EvidenceResult::Unsupported
        ));
        assert_eq!(e.receipt.source_id.as_deref(), Some("s"));
        assert_eq!(e.determinism, REPRODUCIBLE);
        assert_eq!(e.model_hash.as_deref(), Some("sha256:m"));
    }

    #[test]
    fn no_sources_is_unsupported_not_a_panic() {
        let v = NliVerifier::new(tiny(), "sha256:m");
        let inp = input(vec![statement("c0", "Anything at all.")], vec![]);
        let ev = v.verify(&inp).unwrap();
        assert_eq!(ev.len(), 1);
        assert_eq!(ev[0].result, EvidenceResult::Unsupported);
        assert!(ev[0].receipt.notes.contains(&"no_sources".to_string()));
    }

    #[test]
    fn non_statement_claims_are_ignored() {
        let v = NliVerifier::new(tiny(), "sha256:m");
        let mut word = statement("w0", "total");
        word.kind = ClaimKind::Word;
        let inp = input(vec![word], vec![("s", "the total")]);
        assert!(v.verify(&inp).unwrap().is_empty());
    }
}
