// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Built-in verifiers. Each one is exact: the same input gives the same
//! evidence on every machine, and no model runs.
//!
//! | id                    | checks |
//! |-----------------------|--------|
//! | `groundlens.numeric`  | every figure is in a source, or follows from figures that are |
//! | `groundlens.scope`    | every figure comes from a passage about the request's entity |
//! | `groundlens.intent`   | the figure is the kind and unit the question asked for |
//! | `groundlens.rules.*`  | the organisation's own rules |
//!
//! The judge (`llm_judge.*`) is not here: the engine never calls a model.
//! The caller does and passes the reply (`groundlens::judge`).
//!
//! Every verifier implements the same [`gl_core::Verifier`] trait. None of
//! them decides anything; the policy does.

pub mod extract;
pub mod intent;
pub mod numeric;
pub mod rules;
pub mod scope;

pub use extract::{extract_claims, extract_claims_with};
pub use intent::IntentVerifier;
pub use numeric::{NumericConfig, NumericVerifier};
pub use rules::{Rule, RuleAction, RuleSet, RulesVerifier};
pub const INTENT_ID: &str = intent::ID;
pub use scope::ScopeVerifier;
pub const SCOPE_ID: &str = scope::ID;
