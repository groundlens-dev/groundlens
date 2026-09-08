//! Built-in verifiers.
//!
//! | id                    | kind      | determinism  | status in 0.1 |
//! |-----------------------|-----------|--------------|---------------|
//! | `groundlens.numeric`  | exact     | Exact        | implemented   |
//! | `groundlens.rules`    | symbolic  | Exact        | implemented   |
//! | `groundlens.lexical`  | lexical   | Reproducible | needs gl-onnx |
//! | `nli.*`               | ml        | Reproducible | needs gl-onnx |
//! | `sgi`, `dgi`          | geometric | Reproducible | needs gl-onnx |
//! | `llm_judge.*`         | generative| NonDet.      | adapter only  |
//!
//! Every verifier here implements the same [`gl_core::Verifier`] trait. None
//! of them decides anything.

pub mod extract;
pub mod numeric;
pub mod rules;

pub use extract::{extract_claims, extract_claims_with};
pub use numeric::{NumericConfig, NumericVerifier};
pub use rules::{Rule, RuleAction, RuleSet, RulesVerifier};
