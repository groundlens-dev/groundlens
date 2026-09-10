// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Determinism as a declared, checkable property.
//!
//! The product promise is *functional* determinism, not bit-exact
//! determinism:
//!
//! * same input, same configuration, same bundle  →  same classification;
//! * every score within a declared tolerance of the reference run;
//! * the hash of the quantised result is identical across platforms.
//!
//! Each verifier declares which class it belongs to. A policy can then
//! require a class ("only `Exact` and `Reproducible` verifiers may decide")
//! and the record carries the declared class of everything that ran.

use serde::{Deserialize, Serialize};

/// Absolute tolerance on a score in `[0, 1]`.
#[derive(Debug, Clone, Copy, PartialEq, PartialOrd, Serialize, Deserialize)]
#[serde(transparent)]
pub struct Tolerance(pub f64);

impl Tolerance {
    /// The default tolerance for float32 inference on CPU: wider than
    /// cross-platform drift, far narrower than any difference a reader cares
    /// about. Matches the six-decimal rounding of groundlens 3.x.
    pub const FLOAT32_CPU: Tolerance = Tolerance(1e-6);

    /// Number of decimals to keep so that two runs within tolerance quantise
    /// to the same value in the overwhelming majority of cases. Boundary
    /// cases are handled by the policy guard band, not here.
    pub fn decimals(self) -> u32 {
        if self.0 <= 0.0 {
            return 12;
        }
        ((-self.0.log10()) - 1e-9).ceil().clamp(0.0, 12.0) as u32
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(tag = "class", rename_all = "snake_case")]
pub enum Determinism {
    /// Bit-identical on every platform. Integer and decimal arithmetic,
    /// string rules, symbolic checks. No floats involved in the decision.
    Exact,
    /// Identical classification, scores within `tolerance`, given pinned
    /// artefacts (ONNX graph hash, tokenizer hash, execution provider).
    Reproducible { tolerance: Tolerance },
    /// No reproducibility guarantee (sampling, remote model, temperature).
    /// Still auditable: the record stores model id, prompt hash, settings.
    NonDeterministic,
}

impl Determinism {
    pub fn is_deterministic(self) -> bool {
        !matches!(self, Determinism::NonDeterministic)
    }

    /// Ordering used by policies: `Exact` is the strongest guarantee.
    pub fn rank(self) -> u8 {
        match self {
            Determinism::Exact => 2,
            Determinism::Reproducible { .. } => 1,
            Determinism::NonDeterministic => 0,
        }
    }

    pub fn tolerance(self) -> Tolerance {
        match self {
            Determinism::Exact => Tolerance(0.0),
            Determinism::Reproducible { tolerance } => tolerance,
            Determinism::NonDeterministic => Tolerance(1.0),
        }
    }
}

/// Round a score so that platform drift below `tolerance` disappears from
/// hashes and decisions. Exact verifiers pass through unchanged.
pub fn quantise(score: f64, determinism: Determinism) -> f64 {
    match determinism {
        Determinism::Exact => score,
        other => {
            let d = other.tolerance().decimals();
            let factor = 10f64.powi(d as i32);
            (score * factor).round() / factor
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn float32_tolerance_quantises_to_six_decimals() {
        assert_eq!(Tolerance::FLOAT32_CPU.decimals(), 6);
        let d = Determinism::Reproducible { tolerance: Tolerance::FLOAT32_CPU };
        assert_eq!(quantise(0.123_456_789, d), 0.123_457);
        assert_eq!(quantise(0.123_456_4, d), 0.123_456);
    }

    #[test]
    fn exact_is_untouched() {
        assert_eq!(quantise(0.123_456_789, Determinism::Exact), 0.123_456_789);
    }
}
