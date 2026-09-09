//! Built-in verifiers.
//!
//! | id                    | kind      | determinism  | status in 4.0 |
//! |-----------------------|-----------|--------------|---------------|
//! | `groundlens.numeric`  | exact     | Exact        | implemented   |
//! | `groundlens.rules`    | symbolic  | Exact        | implemented   |
//! | `groundlens.lexical`  | lexical   | Reproducible | feature `lexical` |
//! | `nli.*`               | ml        | Reproducible | needs gl-onnx |
//! | `sgi`, `dgi`          | geometric | Reproducible | needs gl-onnx |
//! | `llm_judge.*`         | generative| NonDet.      | adapter only  |
//!
//! Every verifier here implements the same [`gl_core::Verifier`] trait. None
//! of them decides anything.

pub mod extract;
#[cfg(feature = "lexical")]
pub mod lexical;
pub mod numeric;
pub mod rules;

pub use extract::{extract_claims, extract_claims_with};
#[cfg(feature = "lexical")]
pub use lexical::LexicalVerifier;

/// Id of the lexical verifier, known even when the feature is off.
pub const LEXICAL_ID: &str = "groundlens.lexical";
pub use numeric::{NumericConfig, NumericVerifier};
pub use rules::{Rule, RuleAction, RuleSet, RulesVerifier};
