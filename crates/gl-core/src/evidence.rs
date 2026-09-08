//! What a verifier returns. Evidence, never truth.

use serde::{Deserialize, Serialize};

use crate::input::Span;
use crate::Determinism;

/// A score in `[0, 1]`. Higher means more support for the claim.
#[derive(Debug, Clone, Copy, PartialEq, PartialOrd, Serialize, Deserialize)]
#[serde(transparent)]
pub struct Score(pub f64);

impl Score {
    pub fn clamp(value: f64) -> Score {
        Score(value.clamp(0.0, 1.0))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceResult {
    /// The sources back this claim under this verifier's criterion.
    Supported,
    /// The sources say something incompatible with this claim.
    Contradicted,
    /// Nothing in the sources speaks to this claim.
    Unsupported,
    /// This verifier does not apply to this claim kind.
    NotApplicable,
    /// The verifier could not run (input too long, model missing).
    Error,
}

/// Where the reviewer should look.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct Receipt {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_span: Option<Span>,
    /// The source text the claim was compared with (the number it lost to,
    /// the sentence with the highest entailment).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_text: Option<String>,
    /// Closed vocabulary of reason codes, e.g. `numeral_ambiguous`,
    /// `dimension_mismatch`, `matches_at_declared_precision`,
    /// `echoes_question`.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Evidence {
    pub verifier_id: String,
    pub verifier_version: String,
    pub claim_id: String,
    pub result: EvidenceResult,
    /// Quantised according to the verifier's determinism class.
    pub score: Score,
    /// How sure the verifier is of its own result. Exact verifiers report 1.
    pub confidence: Score,
    pub determinism: Determinism,
    /// One human-readable line. Never a decision.
    pub rationale: String,
    pub receipt: Receipt,
    /// Hash of the model artefact that produced this, if any.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model_hash: Option<String>,
    /// Calibration artefact id, if the score was mapped through one.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub calibration_id: Option<String>,
}

impl Evidence {
    /// Sort key used everywhere so that ordering never depends on hash maps
    /// or thread scheduling: claim, then verifier, then result.
    pub fn sort_key(&self) -> (String, String, u8) {
        let r = match self.result {
            EvidenceResult::Contradicted => 0,
            EvidenceResult::Unsupported => 1,
            EvidenceResult::Supported => 2,
            EvidenceResult::NotApplicable => 3,
            EvidenceResult::Error => 4,
        };
        (self.claim_id.clone(), self.verifier_id.clone(), r)
    }
}
