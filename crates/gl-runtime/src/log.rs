// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The append-only, hash-chained event log of a run.
//!
//! [`VerificationRun`] holds the *shape* of an execution. A [`RunLog`] gives it
//! the property a bank asks for: every event is sealed with the hash of the one
//! before it, so a single altered event, or a reordering, breaks the chain and
//! [`RunLog::verify`] catches it. This is the same idea as the 4.x evidence
//! record chain, one level down: there each *record* links to the previous
//! record; here each *event* links to the previous event within a run.
//!
//! The chain proves the log was not modified after the fact. It does not, on
//! its own, prove the log was not *truncated* (a valid prefix is still a valid
//! chain); anchoring the head hash in a signed record does that, which is the
//! next layer's job.

use serde::{Deserialize, Serialize};

use gl_core::canonical::{canonical_json, sha256_hex};
use gl_core::{Error, Result};

use crate::{RunEvent, RunId};

/// One event sealed into the chain.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SealedEvent {
    pub entry: RunEvent,
    /// Hash of the previous sealed event, or `None` for the first.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub previous_hash: Option<String>,
    /// `sha256:` over the canonical JSON of `entry` and the previous hash.
    pub entry_hash: String,
}

/// `sha256:` seal of `entry` chained onto `previous`.
fn seal_hash(entry: &RunEvent, previous: Option<&str>) -> Result<String> {
    let material = format!("{}\n{}", canonical_json(entry)?, previous.unwrap_or(""));
    Ok(format!("sha256:{}", sha256_hex(material.as_bytes())))
}

/// An append-only log of a run's events, each chained to the last.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RunLog {
    pub run_id: RunId,
    #[serde(default)]
    pub entries: Vec<SealedEvent>,
}

impl RunLog {
    pub fn new(run_id: impl Into<RunId>) -> Self {
        RunLog { run_id: run_id.into(), entries: Vec::new() }
    }

    /// Rebuild a log from already-sealed entries (e.g. read from storage).
    /// Does not re-seal; call [`verify`](RunLog::verify) to check it.
    pub fn from_entries(run_id: impl Into<RunId>, entries: Vec<SealedEvent>) -> Self {
        RunLog { run_id: run_id.into(), entries }
    }

    /// The hash at the tip of the chain, or `None` for an empty log. This is
    /// what a higher layer signs to anchor the whole run.
    pub fn head(&self) -> Option<&str> {
        self.entries.last().map(|e| e.entry_hash.as_str())
    }

    /// Seal one more event onto the chain. Enforces the same well-formedness as
    /// [`VerificationRun::validate`](crate::VerificationRun::validate) as it
    /// goes: unique event ids, strictly increasing `sequence`, and a `parent`
    /// that was already appended.
    pub fn append(&mut self, event: RunEvent) -> Result<&SealedEvent> {
        if self.entries.iter().any(|e| e.entry.id == event.id) {
            return Err(Error::InvalidInput(format!("duplicate event id {:?}", event.id.as_str())));
        }
        if let Some(last) = self.entries.last() {
            if event.sequence <= last.entry.sequence {
                return Err(Error::InvalidInput(format!(
                    "event {:?} sequence {} is not greater than {}",
                    event.id.as_str(),
                    event.sequence,
                    last.entry.sequence
                )));
            }
        }
        if let Some(parent) = &event.parent {
            if !self.entries.iter().any(|e| &e.entry.id == parent) {
                return Err(Error::InvalidInput(format!(
                    "event {:?} has parent {:?}, which has not been appended",
                    event.id.as_str(),
                    parent.as_str()
                )));
            }
        }
        let previous_hash = self.head().map(str::to_string);
        let entry_hash = seal_hash(&event, previous_hash.as_deref())?;
        self.entries.push(SealedEvent { entry: event, previous_hash, entry_hash });
        Ok(self.entries.last().unwrap())
    }

    /// Recompute the whole chain and confirm nothing was altered: every link
    /// points at the real previous hash and every seal matches its event.
    /// Returns the first break.
    pub fn verify(&self) -> Result<()> {
        let mut previous: Option<&str> = None;
        for (i, sealed) in self.entries.iter().enumerate() {
            if sealed.previous_hash.as_deref() != previous {
                return Err(Error::Integrity(format!("event {i}: previous hash does not match the chain")));
            }
            let expected = seal_hash(&sealed.entry, previous)?;
            if expected != sealed.entry_hash {
                return Err(Error::Integrity(format!(
                    "event {i} ({:?}): seal does not match its content",
                    sealed.entry.id.as_str()
                )));
            }
            previous = Some(&sealed.entry_hash);
        }
        Ok(())
    }

    /// The plain events, in order, dropping the chain metadata.
    pub fn events(&self) -> impl Iterator<Item = &RunEvent> {
        self.entries.iter().map(|e| &e.entry)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Decision, EventId, VerificationEvent};

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

    fn log() -> RunLog {
        let mut log = RunLog::new("run_1");
        log.append(ev("e0", None, 0, VerificationEvent::RunStarted)).unwrap();
        log.append(ev("e1", Some("e0"), 1, VerificationEvent::StateRead { key: "balance".into() })).unwrap();
        log.append(ev(
            "e2",
            Some("e1"),
            2,
            VerificationEvent::VerificationCompleted { decision: Decision::Pass },
        ))
        .unwrap();
        log
    }

    #[test]
    fn chain_links_and_verifies() {
        let log = log();
        assert_eq!(log.entries[0].previous_hash, None);
        assert_eq!(log.entries[1].previous_hash.as_deref(), Some(log.entries[0].entry_hash.as_str()));
        assert_eq!(log.head(), Some(log.entries[2].entry_hash.as_str()));
        assert!(log.verify().is_ok());
    }

    #[test]
    fn altering_an_event_breaks_the_seal() {
        let mut log = log();
        // Tamper with a sealed event's content without resealing.
        log.entries[1].entry.event = VerificationEvent::StateRead { key: "limit".into() };
        let err = log.verify().unwrap_err().to_string();
        assert!(err.contains("seal does not match"), "{err}");
    }

    #[test]
    fn reordering_breaks_the_chain() {
        let mut log = log();
        log.entries.swap(1, 2);
        assert!(log.verify().is_err());
    }

    #[test]
    fn append_rejects_bad_events() {
        let mut log = log();
        assert!(log.append(ev("e2", Some("e1"), 3, VerificationEvent::RunStarted)).is_err()); // dup id
        assert!(log.append(ev("e9", Some("e1"), 2, VerificationEvent::RunStarted)).is_err()); // seq not increasing
        assert!(log.append(ev("e9", Some("ex"), 9, VerificationEvent::RunStarted)).is_err());
        // unknown parent
    }

    #[test]
    fn head_anchors_the_run() {
        // The head hash is deterministic for the same events, so a signature
        // over it anchors the whole run.
        assert_eq!(log().head(), log().head());
        assert!(RunLog::new("empty").head().is_none());
    }
}
