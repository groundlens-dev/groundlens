//! What gets verified.
//!
//! The engine never sees "an answer". It sees a set of [`Claim`]s, each one an
//! atomic span of the answer with a kind, and a set of [`Source`]s the claims
//! are checked against. Claim extraction is a stage of the pipeline, so the
//! same claim schema serves a rule-based splitter today and an ML splitter
//! tomorrow.

use serde::{Deserialize, Serialize};

/// Character offsets into the *normalised* text they belong to.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct Span {
    pub start: usize,
    pub end: usize,
}

impl Span {
    pub fn new(start: usize, end: usize) -> Self {
        Span { start, end }
    }
    pub fn overlaps(&self, other: &Span) -> bool {
        self.start < other.end && other.start < self.end
    }
    pub fn len(&self) -> usize {
        self.end.saturating_sub(self.start)
    }
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ClaimKind {
    /// A numeral, possibly with scale, currency, percent or physical unit.
    Numeric,
    /// A date or a period.
    Temporal,
    /// A named entity (organisation, person, place, product).
    Entity,
    /// A quotation the answer attributes to a source.
    Citation,
    /// A declarative statement checked by entailment or similarity.
    Statement,
    /// A single content word (the groundlens 3.x lexical channel).
    Word,
}

/// One retrieved passage. The `id` is what a reviewer opens.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Source {
    pub id: String,
    pub text: String,
    /// Optional structural anchor of the passage: page, table row, section.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub locator: Option<String>,
}

/// An atomic, verifiable unit of the answer.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Claim {
    /// Stable within one verification: `c0`, `c1`, ... in answer order.
    pub id: String,
    pub kind: ClaimKind,
    /// Verbatim text of the claim in the normalised answer.
    pub text: String,
    pub span: Span,
    /// Optional attributes the extractor attached (`unit`, `dimension`,
    /// `entity_type`, `cites`). Rules can match on them.
    #[serde(default, skip_serializing_if = "indexmap::IndexMap::is_empty")]
    pub attributes: indexmap::IndexMap<String, String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VerificationInput {
    /// The question, if known. Never a source. Used only for notes such as
    /// `echoes_question`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub question: Option<String>,
    /// The normalised answer text. Spans index into this.
    pub answer: String,
    pub sources: Vec<Source>,
    pub claims: Vec<Claim>,
    /// BCP-47-ish locale for numerals: `und`, `en`, `es`, `de`...
    #[serde(default = "default_locale")]
    pub locale: String,
    /// Free-form metadata (tenant, model id that produced the answer, trace
    /// id). Hashed into `input_hash`, never interpreted by verifiers.
    #[serde(default, skip_serializing_if = "indexmap::IndexMap::is_empty")]
    pub metadata: indexmap::IndexMap<String, String>,
}

fn default_locale() -> String {
    "und".to_string()
}

impl VerificationInput {
    pub fn claim(&self, id: &str) -> Option<&Claim> {
        self.claims.iter().find(|c| c.id == id)
    }
}
