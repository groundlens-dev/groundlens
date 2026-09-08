//! The one trait.

use serde::{Deserialize, Serialize};

use crate::{ClaimKind, Determinism, Evidence, Result, VerificationInput};

pub type VerifierId = String;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum VerifierKind {
    /// Arithmetic, units, dates. Deterministic by construction.
    Exact,
    /// User rules, regex, citations. Deterministic by construction.
    Symbolic,
    /// Word anchors on a frozen encoder (the groundlens lexical channel).
    Lexical,
    /// NLI, classifiers. Reproducible under pinned ONNX artefacts.
    Ml,
    /// SGI, DGI. Reproducible under pinned artefacts and reference sets.
    Geometric,
    /// LLM-as-a-judge. Recorded, never trusted as truth.
    Generative,
    /// Loaded from a plugin (Python, WASM). Guarantees declared by the user.
    UserDefined,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct VerifierInfo {
    /// Dotted, stable: `groundlens.numeric`, `nli.deberta_v3_small`, `sgi`.
    pub id: VerifierId,
    pub version: String,
    pub kind: VerifierKind,
    pub determinism: Determinism,
    /// Which claim kinds this verifier produces evidence for.
    pub applies_to: Vec<ClaimKind>,
    /// Model, tokenizer and calibration artefacts, as `name = sha256`.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub artefacts: Vec<(String, String)>,
    /// True when the verifier may leave the process (a remote judge).
    /// Bundles built for air-gapped deployments refuse such verifiers.
    #[serde(default)]
    pub needs_network: bool,
}

/// `input -> evidence`. Never `input -> truth`.
pub trait Verifier: Send + Sync {
    fn info(&self) -> &VerifierInfo;

    /// Produce evidence for every applicable claim in `input`. The returned
    /// vector must be sorted by [`Evidence::sort_key`] and must contain at
    /// most one entry per claim.
    fn verify(&self, input: &VerificationInput) -> Result<Vec<Evidence>>;
}

impl std::fmt::Debug for dyn Verifier {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Verifier({}@{})", self.info().id, self.info().version)
    }
}
