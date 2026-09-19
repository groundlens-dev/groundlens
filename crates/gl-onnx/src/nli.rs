// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The NLI cross-encoder: a three-way entailment classifier run by tract.
//!
//! Unlike the [`TractEncoder`](crate::tract::TractEncoder), which turns one
//! text into vectors, this takes a *pair* (premise, hypothesis) and returns
//! three logits. The tokenizer joins the pair the way the model was trained
//! (`[CLS] premise [SEP] hypothesis [SEP]`); the model returns `[1, 3]`
//! logits; softmax turns them into probabilities, and `labels` says which
//! logit is entailment, which is neutral, which is contradiction.
//!
//! Same `cpu-f32` profile and reproducibility guarantee as the encoder.

use std::path::Path;

use gl_core::{Error, Result};
use serde::{Deserialize, Serialize};
use tokenizers::Tokenizer;
use tract_onnx::prelude::*;

use crate::EntailmentModel;

type Model = std::sync::Arc<TypedRunnableModel>;

/// How to load and read one entailment model. Kept parallel to
/// [`EncoderSpec`](crate::tract::EncoderSpec) so a bundle can name both.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EntailmentSpec {
    pub model: String,
    pub tokenizer: String,
    pub max_tokens: usize,
    /// The meaning of each output logit, in order. Must contain exactly
    /// `entailment`, `neutral` and `contradiction`. MoritzLaurer's mnli-xnli
    /// models use `[entailment, neutral, contradiction]`.
    pub labels: Vec<String>,
}

pub struct TractEntailment {
    id: String,
    spec: EntailmentSpec,
    tokenizer: Tokenizer,
    model: Model,
    inputs: Vec<String>,
    /// Positions of entailment / neutral / contradiction in the logit vector.
    order: (usize, usize, usize),
}

fn model_err<E: std::fmt::Display>(e: E) -> Error {
    Error::Integrity(format!("onnx: {e}"))
}

fn label_position(labels: &[String], want: &str) -> Result<usize> {
    labels
        .iter()
        .position(|l| l.eq_ignore_ascii_case(want))
        .ok_or_else(|| Error::Integrity(format!("entailment model has no {want:?} label")))
}

impl TractEntailment {
    /// Load from files already verified by the bundle. `model_sha256` becomes
    /// part of the model id, so every piece of evidence names the exact graph.
    pub fn load(
        root: &Path,
        name: &str,
        spec: &EntailmentSpec,
        model_sha256: &str,
    ) -> Result<TractEntailment> {
        if spec.labels.len() != 3 {
            return Err(Error::Integrity(format!(
                "entailment model needs exactly 3 labels, got {}",
                spec.labels.len()
            )));
        }
        let order = (
            label_position(&spec.labels, "entailment")?,
            label_position(&spec.labels, "neutral")?,
            label_position(&spec.labels, "contradiction")?,
        );
        let tokenizer = Tokenizer::from_file(root.join(&spec.tokenizer))
            .map_err(|e| Error::Integrity(format!("tokenizer {}: {e}", spec.tokenizer)))?;
        let mut proto = tract_onnx::onnx()
            .model_for_path(root.join(&spec.model))
            .map_err(|e| Error::Integrity(format!("model {}: {e}", spec.model)))?;
        let inputs: Vec<String> = proto
            .input_outlets()
            .map_err(model_err)?
            .iter()
            .map(|o| proto.node(o.node).name.clone())
            .collect();
        let seq = proto.symbols.sym("S");
        for i in 0..inputs.len() {
            proto
                .set_input_fact(
                    i,
                    InferenceFact::dt_shape(i64::datum_type(), tvec!(1.to_dim(), seq.to_dim())),
                )
                .map_err(model_err)?;
        }
        let model = proto.into_optimized().map_err(model_err)?.into_runnable().map_err(model_err)?;
        Ok(TractEntailment {
            id: format!("{name}@{model_sha256}"),
            spec: spec.clone(),
            tokenizer,
            model,
            inputs,
            order,
        })
    }

    fn logits(&self, premise: &str, hypothesis: &str) -> Result<Vec<f32>> {
        let enc = self
            .tokenizer
            .encode((premise, hypothesis), true)
            .map_err(|e| Error::InvalidInput(format!("tokenize: {e}")))?;
        let mut ids: Vec<i64> = enc.get_ids().iter().map(|&x| x as i64).collect();
        let mut mask: Vec<i64> = enc.get_attention_mask().iter().map(|&x| x as i64).collect();
        let mut types: Vec<i64> = enc.get_type_ids().iter().map(|&x| x as i64).collect();
        // Truncate to the model's window, keeping the trailing [SEP].
        if ids.len() > self.spec.max_tokens {
            let n = self.spec.max_tokens;
            ids.truncate(n);
            mask.truncate(n);
            types.truncate(n);
            if let Some(last) = ids.last_mut() {
                *last = enc.get_ids()[enc.get_ids().len() - 1] as i64;
            }
        }
        let n = ids.len();
        let mut feed: TVec<TValue> = tvec!();
        for name in &self.inputs {
            let data: &[i64] = match name.as_str() {
                "input_ids" => &ids,
                "attention_mask" => &mask,
                "token_type_ids" => &types,
                other => return Err(Error::Integrity(format!("unexpected model input {other}"))),
            };
            let t = tract_ndarray::Array2::from_shape_vec((1, n), data.to_vec())
                .map_err(|e| Error::Integrity(e.to_string()))?;
            feed.push(Tensor::from(t).into());
        }
        let out = self.model.run(feed).map_err(model_err)?;
        let logits = out[0].to_plain_array_view::<f32>().map_err(model_err)?;
        let flat: Vec<f32> = logits.iter().copied().collect();
        if flat.len() != 3 {
            return Err(Error::Integrity(format!(
                "entailment model returned {} logits, expected 3",
                flat.len()
            )));
        }
        Ok(flat)
    }
}

/// Numerically stable softmax over the three logits, in f64.
fn softmax3(logits: &[f32]) -> [f64; 3] {
    let m = logits.iter().cloned().fold(f32::MIN, f32::max) as f64;
    let exps: Vec<f64> = logits.iter().map(|&x| ((x as f64) - m).exp()).collect();
    let sum: f64 = exps.iter().sum();
    [exps[0] / sum, exps[1] / sum, exps[2] / sum]
}

impl EntailmentModel for TractEntailment {
    fn id(&self) -> &str {
        &self.id
    }

    fn classify(&self, premise: &str, hypothesis: &str) -> Result<(f32, f32, f32)> {
        let logits = self.logits(premise, hypothesis)?;
        let p = softmax3(&logits);
        let (e, n, c) = self.order;
        Ok((p[e] as f32, p[n] as f32, p[c] as f32))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn tiny() -> TractEntailment {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("testdata/tiny-nli");
        let spec = EntailmentSpec {
            model: "models/tiny.onnx".into(),
            tokenizer: "tokenizers/tiny/tokenizer.json".into(),
            max_tokens: 32,
            labels: vec!["entailment".into(), "neutral".into(), "contradiction".into()],
        };
        TractEntailment::load(&root, "tiny-nli", &spec, "sha256:test").unwrap()
    }

    #[test]
    fn probabilities_are_valid_and_deterministic() {
        let nli = tiny();
        let (e, n, c) =
            nli.classify("The invoice total is 10,000 dollars.", "The invoice is 10,000 dollars.").unwrap();
        for p in [e, n, c] {
            assert!((0.0..=1.0).contains(&p), "prob out of range: {p}");
        }
        assert!(((e + n + c) - 1.0).abs() < 1e-5, "probs sum to {}", e + n + c);
        // Same input, same output.
        let again =
            nli.classify("The invoice total is 10,000 dollars.", "The invoice is 10,000 dollars.").unwrap();
        assert_eq!((e, n, c), again);
        assert!(nli.id().starts_with("tiny-nli@"));
    }

    #[test]
    fn label_order_is_honoured() {
        // Reversing the labels must swap entailment and contradiction.
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("testdata/tiny-nli");
        let spec = EntailmentSpec {
            model: "models/tiny.onnx".into(),
            tokenizer: "tokenizers/tiny/tokenizer.json".into(),
            max_tokens: 32,
            labels: vec!["contradiction".into(), "neutral".into(), "entailment".into()],
        };
        let rev = TractEntailment::load(&root, "tiny-nli", &spec, "sha256:test").unwrap();
        let fwd = tiny();
        let (e1, _, c1) = fwd.classify("a b c", "d e f").unwrap();
        let (e2, _, c2) = rev.classify("a b c", "d e f").unwrap();
        assert!((e1 - c2).abs() < 1e-6 && (c1 - e2).abs() < 1e-6);
    }
}
