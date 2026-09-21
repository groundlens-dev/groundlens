// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Built-in verifiers.
//!
//! | id                    | kind      | determinism  | status in 4.0 |
//! |-----------------------|-----------|--------------|---------------|
//! | `groundlens.numeric`  | exact     | Exact        | implemented   |
//! | `groundlens.rules`    | symbolic  | Exact        | implemented   |
//! | `groundlens.lexical`  | lexical   | Reproducible | feature `lexical` |
//! | `groundlens.nli`      | ml        | Reproducible | feature `nli` |
//! | `semantic.cosine`     | ml        | Reproducible | feature `semantic` |
//! | `sgi`, `dgi`          | geometric | Reproducible | needs gl-onnx |
//! | `llm_judge.*`         | generative| NonDet.      | adapter only  |
//!
//! Every verifier here implements the same [`gl_core::Verifier`] trait. None
//! of them decides anything.

pub mod extract;
#[cfg(feature = "lexical")]
pub mod lexical;
#[cfg(feature = "nli")]
pub mod nli;
pub mod numeric;
pub mod rules;
#[cfg(feature = "semantic")]
pub mod semantic;

pub use extract::{extract_claims, extract_claims_with};
#[cfg(feature = "lexical")]
pub use lexical::LexicalVerifier;

/// Id of the lexical verifier, known even when the feature is off.
pub const LEXICAL_ID: &str = "groundlens.lexical";
#[cfg(feature = "nli")]
pub use nli::NliVerifier;
/// Id of the NLI verifier, known even when the feature is off.
pub const NLI_ID: &str = "groundlens.nli";
#[cfg(feature = "semantic")]
pub use semantic::SemanticVerifier;
/// Id of the semantic verifier, known even when the feature is off.
pub const SEMANTIC_ID: &str = "semantic.cosine";
pub use numeric::{NumericConfig, NumericVerifier};
pub use rules::{Rule, RuleAction, RuleSet, RulesVerifier};
