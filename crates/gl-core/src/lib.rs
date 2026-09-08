//! Core contracts of the Groundlens verification engine.
//!
//! Everything in this crate is a *contract*, not an implementation:
//!
//! * [`Claim`] is the unit that gets verified (an atomic span of the answer).
//! * [`Evidence`] is what a verifier returns. Never a truth value. Always
//!   evidence: a result, a score, a confidence, and a receipt.
//! * [`Verifier`] is the one trait every built-in, ML, geometric, generative
//!   or user-defined verifier implements: `input -> evidence`.
//! * [`Determinism`] is a declared property of each verifier, checked by the
//!   policy layer. It is the formal backbone of the product claim
//!   "deterministic AI response verification".
//! * [`canonical`] gives one JSON serialisation and one SHA-256 for every
//!   structure that ends up in a signed record.
//!
//! This crate performs no I/O and opens no network connection. That is
//! enforced by its dependency list, not by convention.

pub mod canonical;
pub mod determinism;
pub mod error;
pub mod evidence;
pub mod graph;
pub mod input;
pub mod verifier;

pub use determinism::{Determinism, Tolerance};
pub use error::{Error, Result};
pub use evidence::{Evidence, EvidenceResult, Receipt, Score};
pub use graph::EvidenceGraph;
pub use input::{Claim, ClaimKind, Source, Span, VerificationInput};
pub use verifier::{Verifier, VerifierId, VerifierInfo, VerifierKind};

/// Semantic version of the engine contracts. Goes into every record.
pub const ENGINE_VERSION: &str = env!("CARGO_PKG_VERSION");
