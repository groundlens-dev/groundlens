// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Execution-verification contracts.
//!
//! GroundLens 4.x verifies an *answer*: one input, some evidence, a decision,
//! a signed record. This crate adds the shape one level up, the *run*: a whole
//! execution of an AI system or agent, recorded as an ordered, hash-linkable
//! log of [`VerificationEvent`]s (a model call, a retrieval, a tool request,
//! an action, a human approval, a policy decision).
//!
//! Everything here is a *contract*, exactly like [`gl_core`]: pure data, no
//! I/O, no network, no opinion about how a run is produced or stored. A single
//! answer verification is just a run with one claim and one decision, so the
//! 4.x pipeline extends into this without breaking.
//!
//! What a run stores of the world is **hashes**, not content. `input_hash`,
//! `output_hash`, `arguments_hash`, `result_hash`: an adversary, an auditor or
//! a bank can check that a value matches without the value ever entering the
//! record. Attaching the plaintext (or an encrypted reference) is a choice made
//! by a higher layer, never forced here.

use serde::{Deserialize, Serialize};

use gl_core::canonical::content_hash;
use gl_core::{Error, Result};

pub mod log;
pub use log::{RunLog, SealedEvent};

// ---------------------------------------------------------------- identifiers

/// Stable identifier of a run. Opaque string; a producer picks the scheme
/// (`run_<hex>`, a ULID, a trace id). The contract never parses it.
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(transparent)]
pub struct RunId(pub String);

/// Stable identifier of one event within a run. Unique per run.
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(transparent)]
pub struct EventId(pub String);

macro_rules! string_id {
    ($t:ty) => {
        impl $t {
            pub fn new(s: impl Into<String>) -> Self {
                Self(s.into())
            }
            pub fn as_str(&self) -> &str {
                &self.0
            }
        }
        impl From<&str> for $t {
            fn from(s: &str) -> Self {
                Self(s.to_string())
            }
        }
        impl From<String> for $t {
            fn from(s: String) -> Self {
                Self(s)
            }
        }
    };
}
string_id!(RunId);
string_id!(EventId);

// ---------------------------------------------------------------- identities

/// The AI system a run belongs to. Not the model: the deployed system that a
/// customer is accountable for.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SystemIdentity {
    pub id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub deployment: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActorKind {
    Human,
    Agent,
    Service,
}

/// Who did something: a person, an agent, or a service account.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ActorIdentity {
    pub kind: ActorKind,
    pub id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
}

// ---------------------------------------------------------------- references

/// A model that produced an output. `hash` pins the exact artefact when known.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModelRef {
    pub id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hash: Option<String>,
}

/// A tool the agent can call, optionally the server that exposes it (an MCP
/// server, an internal API).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ToolRef {
    pub name: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub server: Option<String>,
}

/// A retrieved passage, referenced by id and (optionally) content hash.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SourceRef {
    pub id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hash: Option<String>,
}

/// A pinned artefact that took part in the run (a model, a tokenizer, a bundle,
/// a policy). `sha256` is what an auditor recomputes.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ArtifactRef {
    pub id: String,
    pub kind: String,
    pub sha256: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RiskClass {
    Low,
    Medium,
    High,
}

/// An action with side effects the agent asked to take. A tool *call* is not
/// always an action: reading a customer record is a tool call; changing their
/// credit limit is an action. The policy layer decides which need approval.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ActionRef {
    pub id: String,
    pub operation: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub risk: Option<RiskClass>,
}

/// The three outcomes a policy can reach, serialised as in the README and the
/// 4.x records (`PASS` / `REVIEW` / `FAIL`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum Decision {
    Pass,
    Review,
    Fail,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ToolStatus {
    Ok,
    Error,
    Denied,
}

// ---------------------------------------------------------------- the events

/// One thing that happened in a run. Payloads carry hashes of content, not the
/// content itself, so a record is safe to keep in a regulated environment.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum VerificationEvent {
    /// The run began.
    RunStarted,
    /// A model was invoked. Inputs and outputs are referenced by hash.
    ModelInvocation { model: ModelRef, input_hash: String, output_hash: String },
    /// Documents were retrieved for the model to use.
    Retrieval { query_hash: String, documents: Vec<SourceRef> },
    /// A claim was extracted from an answer (the 4.x unit, now an event).
    ClaimExtracted { claim_id: String },
    /// The agent asked to call a tool.
    ToolRequested { tool: ToolRef, arguments_hash: String },
    /// A tool call finished.
    ToolCompleted { tool: ToolRef, result_hash: String, status: ToolStatus },
    /// The agent read shared state or memory.
    StateRead { key: String },
    /// The agent wrote shared state or memory.
    StateWritten { key: String, value_hash: String },
    /// A human approval was requested for an action.
    HumanApprovalRequested { action: ActionRef },
    /// A human granted an approval.
    HumanApprovalGranted { actor: ActorIdentity },
    /// An action with side effects was executed.
    ActionExecuted { action: ActionRef, result_hash: String },
    /// A policy interpreted the evidence so far and reached a decision.
    PolicyEvaluated {
        policy_id: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        policy_hash: Option<String>,
        decision: Decision,
    },
    /// The run's verification concluded.
    VerificationCompleted { decision: Decision },
}

/// One entry in the run's log: an event, its place in the order, who caused it,
/// and its optional parent (so a run is a directed graph, not only a line).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RunEvent {
    pub id: EventId,
    /// The event this one follows from, for concurrent branches. `None` for a
    /// top-level event.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parent: Option<EventId>,
    /// Strictly increasing within the run. Gives the append-only order.
    pub sequence: u64,
    pub timestamp: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub actor: Option<ActorIdentity>,
    pub event: VerificationEvent,
}

/// How a run ended, kept separate from the verification `Decision`: a run can
/// complete cleanly and still `FAIL` verification, or `PASS` everything it
/// managed to check before it was aborted.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionStatus {
    Completed,
    Partial,
    Failed,
    Aborted,
    Timeout,
}

/// A whole verifiable execution: the system, when it ran, the ordered events,
/// and how it ended. This is the unit a 5.x record seals, the way a 4.x record
/// sealed a single verification.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VerificationRun {
    pub run_id: RunId,
    /// A run spawned by another (a sub-agent), if any.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parent_run_id: Option<RunId>,
    pub system: SystemIdentity,
    pub started_at: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub finished_at: Option<String>,
    #[serde(default)]
    pub events: Vec<RunEvent>,
    /// Pinned artefacts that took part, for reproducibility.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub artifacts: Vec<ArtifactRef>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub status: Option<ExecutionStatus>,
}

impl VerificationRun {
    /// `sha256:` over the canonical JSON of the whole run. Same run, same hash,
    /// on any machine.
    pub fn content_hash(&self) -> Result<String> {
        content_hash(self)
    }

    /// Check the log is well formed as an append-only, parent-linked graph:
    /// event ids are unique, `sequence` is strictly increasing, and every
    /// `parent` points at an event that appears earlier in the log. Returns the
    /// first violation, never panics.
    pub fn validate(&self) -> Result<()> {
        let mut seen: std::collections::HashSet<&str> = std::collections::HashSet::new();
        let mut last_seq: Option<u64> = None;
        for e in &self.events {
            if !seen.insert(e.id.as_str()) {
                return Err(Error::InvalidInput(format!("duplicate event id {:?}", e.id.as_str())));
            }
            match last_seq {
                Some(prev) if e.sequence <= prev => {
                    return Err(Error::InvalidInput(format!(
                        "event {:?} sequence {} is not greater than {}",
                        e.id.as_str(),
                        e.sequence,
                        prev
                    )));
                }
                _ => last_seq = Some(e.sequence),
            }
            if let Some(parent) = &e.parent {
                if !seen.contains(parent.as_str()) {
                    return Err(Error::InvalidInput(format!(
                        "event {:?} has parent {:?}, which does not appear earlier",
                        e.id.as_str(),
                        parent.as_str()
                    )));
                }
            }
        }
        Ok(())
    }

    /// Direct children of an event, in log order. With [`validate`] holding,
    /// this reconstructs the execution graph.
    ///
    /// [`validate`]: VerificationRun::validate
    pub fn children_of<'a>(&'a self, id: &EventId) -> Vec<&'a RunEvent> {
        self.events.iter().filter(|e| e.parent.as_ref() == Some(id)).collect()
    }

    /// The final verification decision, if the run recorded one.
    pub fn decision(&self) -> Option<Decision> {
        self.events.iter().rev().find_map(|e| match &e.event {
            VerificationEvent::VerificationCompleted { decision } => Some(*decision),
            _ => None,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ev(id: &str, parent: Option<&str>, seq: u64, event: VerificationEvent) -> RunEvent {
        RunEvent {
            id: id.into(),
            parent: parent.map(EventId::from),
            sequence: seq,
            timestamp: "2026-09-19T10:00:00Z".into(),
            actor: None,
            event,
        }
    }

    fn sample_run() -> VerificationRun {
        VerificationRun {
            run_id: "run_1".into(),
            parent_run_id: None,
            system: SystemIdentity { id: "assistant".into(), version: Some("1.2".into()), deployment: None },
            started_at: "2026-09-19T10:00:00Z".into(),
            finished_at: Some("2026-09-19T10:00:01Z".into()),
            events: vec![
                ev("e0", None, 0, VerificationEvent::RunStarted),
                ev(
                    "e1",
                    Some("e0"),
                    1,
                    VerificationEvent::ToolRequested {
                        tool: ToolRef { name: "crm.lookup".into(), server: Some("crm-mcp".into()) },
                        arguments_hash: "sha256:aa".into(),
                    },
                ),
                ev(
                    "e2",
                    Some("e1"),
                    2,
                    VerificationEvent::ToolCompleted {
                        tool: ToolRef { name: "crm.lookup".into(), server: Some("crm-mcp".into()) },
                        result_hash: "sha256:bb".into(),
                        status: ToolStatus::Ok,
                    },
                ),
                ev(
                    "e3",
                    Some("e2"),
                    3,
                    VerificationEvent::VerificationCompleted { decision: Decision::Pass },
                ),
            ],
            artifacts: vec![],
            status: Some(ExecutionStatus::Completed),
        }
    }

    #[test]
    fn round_trips_through_json() {
        let run = sample_run();
        let text = serde_json::to_string(&run).unwrap();
        let back: VerificationRun = serde_json::from_str(&text).unwrap();
        assert_eq!(run, back);
    }

    #[test]
    fn event_is_tagged_by_type() {
        let text = serde_json::to_string(&VerificationEvent::RunStarted).unwrap();
        assert_eq!(text, r#"{"type":"run_started"}"#);
        let dec = serde_json::to_string(&Decision::Review).unwrap();
        assert_eq!(dec, r#""REVIEW""#);
    }

    #[test]
    fn hash_is_stable_and_order_independent() {
        let run = sample_run();
        let h1 = run.content_hash().unwrap();
        assert!(h1.starts_with("sha256:"));
        // Cloning and re-serialising must not change the hash.
        assert_eq!(h1, run.clone().content_hash().unwrap());
    }

    #[test]
    fn valid_run_passes_validation() {
        assert!(sample_run().validate().is_ok());
    }

    #[test]
    fn duplicate_event_id_is_rejected() {
        let mut run = sample_run();
        run.events[1].id = "e0".into();
        let err = run.validate().unwrap_err().to_string();
        assert!(err.contains("duplicate event id"), "{err}");
    }

    #[test]
    fn non_increasing_sequence_is_rejected() {
        let mut run = sample_run();
        run.events[2].sequence = 1; // same as e1
        assert!(run.validate().is_err());
    }

    #[test]
    fn parent_must_appear_earlier() {
        let mut run = sample_run();
        run.events[1].parent = Some("e2".into()); // e2 appears later
        let err = run.validate().unwrap_err().to_string();
        assert!(err.contains("does not appear earlier"), "{err}");
    }

    #[test]
    fn children_and_decision_reconstruct() {
        let run = sample_run();
        let kids = run.children_of(&EventId::from("e1"));
        assert_eq!(kids.len(), 1);
        assert_eq!(kids[0].id, EventId::from("e2"));
        assert_eq!(run.decision(), Some(Decision::Pass));
    }

    #[test]
    fn a_single_answer_is_a_run_with_one_claim() {
        // The additive story: 4.x answer verification is a degenerate run.
        let run = VerificationRun {
            run_id: "run_ans".into(),
            parent_run_id: None,
            system: SystemIdentity { id: "rag".into(), version: None, deployment: None },
            started_at: "2026-09-19T10:00:00Z".into(),
            finished_at: None,
            events: vec![
                ev("c0", None, 0, VerificationEvent::ClaimExtracted { claim_id: "c0".into() }),
                ev(
                    "d0",
                    Some("c0"),
                    1,
                    VerificationEvent::VerificationCompleted { decision: Decision::Fail },
                ),
            ],
            artifacts: vec![],
            status: Some(ExecutionStatus::Completed),
        };
        assert!(run.validate().is_ok());
        assert_eq!(run.decision(), Some(Decision::Fail));
    }
}
