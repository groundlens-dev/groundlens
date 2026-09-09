//! The reference encoder: an ONNX transformer run by tract (pure Rust),
//! tokenised by HF `tokenizers` with the pure-Rust regex backend.
//!
//! Execution profile `cpu-f32`: float32 graph, single thread, no fused
//! kernels chosen at run time by CPU feature. tract is deterministic for a
//! given model file and input; the residual drift between CPU vendors
//! comes from libm and is far inside the `1e-6` tolerance the
//! `Reproducible` class declares.

use std::path::Path;

use gl_core::{Error, Result, Span};
use tokenizers::Tokenizer;
use tract_onnx::prelude::*;

use crate::{Encoder, WindowEncoding};

type Model = std::sync::Arc<TypedRunnableModel>;

/// `(token offsets, attention mask, hidden rows)` for one forward pass.
type Forward = (Vec<(usize, usize)>, Vec<i64>, Vec<Vec<f32>>);

pub use gl_bundle::EncoderSpec;

pub struct TractEncoder {
    id: String,
    spec: EncoderSpec,
    tokenizer: Tokenizer,
    model: Model,
    inputs: Vec<String>,
}

impl TractEncoder {
    /// Load from files already verified by the bundle. `model_sha256` is the
    /// artefact hash from the manifest and becomes part of the encoder id.
    pub fn load(root: &Path, name: &str, spec: &EncoderSpec, model_sha256: &str) -> Result<TractEncoder> {
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
        Ok(TractEncoder {
            id: format!("{name}@{model_sha256}"),
            spec: spec.clone(),
            tokenizer,
            model,
            inputs,
        })
    }

    /// Run the graph on one already-prefixed text. Returns `(offsets, mask,
    /// hidden)` with hidden as `[tokens][dim]`, special tokens included.
    fn forward(&self, text: &str) -> Result<Forward> {
        let enc =
            self.tokenizer.encode(text, true).map_err(|e| Error::InvalidInput(format!("tokenize: {e}")))?;
        let ids: Vec<i64> = enc.get_ids().iter().map(|&x| x as i64).collect();
        let mask: Vec<i64> = enc.get_attention_mask().iter().map(|&x| x as i64).collect();
        let types: Vec<i64> = enc.get_type_ids().iter().map(|&x| x as i64).collect();
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
        let hidden = out[0].to_plain_array_view::<f32>().map_err(model_err)?;
        let dim = hidden.shape()[2];
        let rows: Vec<Vec<f32>> = (0..n).map(|i| (0..dim).map(|d| hidden[[0, i, d]]).collect()).collect();
        Ok((enc.get_offsets().to_vec(), mask, rows))
    }

    fn with_prefix(&self, text: &str) -> String {
        format!("{}{}", self.spec.prefix, text)
    }

    /// Drop prefix and special tokens; shift offsets back to `text`; trim
    /// the whitespace SentencePiece tokenizers fold into a piece's offsets,
    /// so a span never starts on the space before the word.
    fn content_tokens(&self, text: &str, offsets: &[(usize, usize)]) -> Vec<(usize, Span)> {
        let p = self.spec.prefix.len();
        let mut out = Vec::new();
        for (i, (a, b)) in offsets.iter().enumerate() {
            if b <= a || *a < p {
                continue;
            }
            let (mut start, mut end) = (a - p, b - p);
            while start < end {
                match text[start..end].chars().next() {
                    Some(c) if c.is_whitespace() => start += c.len_utf8(),
                    _ => break,
                }
            }
            while end > start {
                match text[start..end].chars().next_back() {
                    Some(c) if c.is_whitespace() => end -= c.len_utf8(),
                    _ => break,
                }
            }
            if end > start {
                out.push((i, Span::new(start, end)));
            }
        }
        out
    }
}

/// Load the encoder a bundle names under `role` (`default` for the lexical
/// channel). The model hash is taken from the manifest, which `Bundle::open`
/// has already checked against the file.
pub fn encoder_from_bundle(bundle: &gl_bundle::Bundle, role: &str) -> Result<(TractEncoder, String)> {
    let spec = bundle.manifest.encoders.get(role).ok_or_else(|| {
        Error::Integrity(format!("bundle {} has no encoder {role:?}", bundle.manifest.name))
    })?;
    let model_hash =
        bundle.manifest.artefacts.get(&spec.model).map(|a| a.sha256.clone()).ok_or_else(|| {
            Error::Integrity(format!("encoder model {} is not an artefact of the bundle", spec.model))
        })?;
    let name = std::path::Path::new(&spec.model)
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| role.to_string());
    let enc = TractEncoder::load(&bundle.root, &name, spec, &model_hash)?;
    Ok((enc, model_hash))
}

fn model_err<E: std::fmt::Display>(e: E) -> Error {
    Error::Integrity(format!("onnx: {e}"))
}

fn l2(v: &mut [f32]) {
    let norm = v.iter().map(|x| (*x as f64) * (*x as f64)).sum::<f64>().sqrt().max(1e-12) as f32;
    for x in v.iter_mut() {
        *x /= norm;
    }
}

impl Encoder for TractEncoder {
    fn id(&self) -> &str {
        &self.id
    }

    fn max_tokens(&self) -> usize {
        self.spec.max_tokens
    }

    fn token_spans(&self, text: &str) -> Result<Vec<Span>> {
        let enc = self
            .tokenizer
            .encode(self.with_prefix(text), false)
            .map_err(|e| Error::InvalidInput(format!("tokenize: {e}")))?;
        Ok(self.content_tokens(text, enc.get_offsets()).into_iter().map(|(_, s)| s).collect())
    }

    fn encode_window(&self, text: &str) -> Result<WindowEncoding> {
        let (offsets, _mask, rows) = self.forward(&self.with_prefix(text))?;
        let mut spans = Vec::new();
        let mut vectors = Vec::new();
        for (i, span) in self.content_tokens(text, &offsets) {
            let mut v = rows[i].clone();
            l2(&mut v);
            spans.push(span);
            vectors.push(v);
        }
        Ok(WindowEncoding { token_spans: spans, vectors })
    }

    fn encode_sentence(&self, text: &str) -> Result<Vec<f32>> {
        let (_offsets, mask, rows) = self.forward(&self.with_prefix(text))?;
        let dim = rows.first().map(Vec::len).unwrap_or(0);
        let mut v = vec![0f32; dim];
        if self.spec.pooling == "cls" {
            v = rows[0].clone();
        } else {
            let mut count = 0f32;
            for (row, m) in rows.iter().zip(&mask) {
                if *m == 1 {
                    for (acc, x) in v.iter_mut().zip(row) {
                        *acc += x;
                    }
                    count += 1.0;
                }
            }
            for x in v.iter_mut() {
                *x /= count.max(1.0);
            }
        }
        l2(&mut v);
        Ok(v)
    }
}
