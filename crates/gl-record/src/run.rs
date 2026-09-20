// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The run record: the same signed, hash-chained, offline-verifiable guarantee
//! that [`EvidenceRecord`](crate::EvidenceRecord) gives one answer, given to a
//! whole execution.
//!
//! GroundLens 4.x seals a single verification: which verifiers ran, what
//! evidence they produced, what policy decided, all signed and chained. A run
//! is that one level up: a whole execution of an AI system or agent, recorded
//! as an ordered, hash-linked log of events. This module seals the run with the
//! *same* Ed25519 signature and record chain as an answer, so a bank can verify
//! an execution offline exactly the way it verifies an answer.
//!
//! What the record stores is **hashes**, not content: the run's content hash
//! (which pins the ordered events), the event log's chain head (which anchors
//! the tamper-evident log and, once signed, rules out silent truncation), the
//! execution policy that gated it, the gate's verdict and any breaches. The
//! full run and its log live alongside, bound to the record by those hashes.
//!
//! The timestamp and record id sit outside the content hash, so the same run
//! sealed on two machines has the same `content_hash` while staying two
//! distinct, separately signed records.

use serde::{Deserialize, Serialize};

use gl_core::canonical::{canonical_json, content_hash};
use gl_core::{Error, Result};
use gl_runtime::gate::{Breach, ExecutionPolicy, GateEffect};
use gl_runtime::{RunLog, VerificationRun};

use crate::{sign_envelope, verify_envelope, RecordSigner};

pub const RUN_RECORD_SCHEMA: &str = "groundlens.run-record/1";

/// Everything that is a function of the run, the policy and the artefacts.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RunRecordContent {
    pub schema: String,
    pub engine_version: String,
    pub run_id: String,
    /// A run spawned by another (a sub-agent), if any.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parent_run_id: Option<String>,
    /// `sha256:` content hash of the [`VerificationRun`]: pins the ordered
    /// events. An auditor recomputes it from the run stored alongside.
    pub run_hash: String,
    /// The event log's chain head, or `None` for an empty log. Signing this
    /// anchors the whole log against truncation.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub log_head: Option<String>,
    pub policy_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub policy_hash: Option<String>,
    /// The gate's verdict over the whole run.
    pub gate: GateEffect,
    /// Actions executed in breach of the policy, if any.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub breaches: Vec<Breach>,
}

/// A signed run record. Field for field the same envelope as
/// [`EvidenceRecord`](crate::EvidenceRecord); only the content differs.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunRecord {
    pub record_id: String,
    pub timestamp: String,
    pub content: RunRecordContent,
    pub content_hash: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub previous_record_hash: Option<String>,
    pub record_hash: String,
    pub signature: String,
    pub signer_public_key: String,
}

/// Seal a run into a signed record. Audits the run against `policy` so the
/// record carries the gate verdict and any breaches, hashes the run and reads
/// the log head, then signs and chains the whole thing.
///
/// The log's chain is not re-verified here (that is [`RunLog::verify`], done
/// when the log is read). This binds the record to the log's current head; a
/// verifier that wants the full guarantee runs [`RunLog::verify`] and checks
/// the head against `content.log_head`.
#[allow(clippy::too_many_arguments)]
pub fn seal_run(
    run: &VerificationRun,
    log: &RunLog,
    policy: &ExecutionPolicy,
    engine_version: &str,
    record_id: String,
    timestamp: String,
    previous_record_hash: Option<String>,
    signer: &RecordSigner,
) -> Result<RunRecord> {
    let gate = policy.audit_run(run);
    let content = RunRecordContent {
        schema: RUN_RECORD_SCHEMA.into(),
        engine_version: engine_version.into(),
        run_id: run.run_id.0.clone(),
        parent_run_id: run.parent_run_id.as_ref().map(|r| r.0.clone()),
        run_hash: run.content_hash()?,
        log_head: log.head().map(str::to_string),
        policy_id: policy.id.clone(),
        policy_hash: policy.hash.clone(),
        gate: gate.effect,
        breaches: gate.breaches,
    };
    let content_hash = content_hash(&content)?;
    let (record_hash, signature, signer_public_key) =
        sign_envelope(&content_hash, previous_record_hash.as_deref(), &record_id, &timestamp, signer);
    Ok(RunRecord {
        record_id,
        timestamp,
        content,
        content_hash,
        previous_record_hash,
        record_hash,
        signature,
        signer_public_key,
    })
}

/// Recompute every hash and check the signature of one run record.
pub fn verify_run_record(record: &RunRecord) -> Result<()> {
    let recomputed = content_hash(&record.content)?;
    verify_envelope(
        &recomputed,
        &record.content_hash,
        record.previous_record_hash.as_deref(),
        &record.record_id,
        &record.timestamp,
        &record.record_hash,
        &record.signature,
        &record.signer_public_key,
    )
}

/// Verify a whole run-record log: every record individually, and every link.
pub fn verify_run_chain(records: &[RunRecord]) -> Result<()> {
    let mut previous: Option<&str> = None;
    for r in records {
        verify_run_record(r)?;
        if r.previous_record_hash.as_deref() != previous {
            return Err(Error::Integrity(format!("{}: broken chain link", r.record_id)));
        }
        previous = Some(&r.record_hash);
    }
    Ok(())
}

/// Confirm a record actually attests to *this* run and log: the run hashes to
/// `run_hash`, the log chain is intact, and its head matches `log_head`. Pair
/// this with [`verify_run_record`] for the full offline check.
pub fn verify_run_against_record(run: &VerificationRun, log: &RunLog, record: &RunRecord) -> Result<()> {
    if run.content_hash()? != record.content.run_hash {
        return Err(Error::Integrity(format!("{}: run hash does not match the record", record.record_id)));
    }
    log.verify()?;
    if log.head().map(str::to_string) != record.content.log_head {
        return Err(Error::Integrity(format!("{}: log head does not match the record", record.record_id)));
    }
    Ok(())
}

/// One run record as a canonical JSON Lines line.
pub fn run_record_to_jsonl_line(record: &RunRecord) -> Result<String> {
    canonical_json(record)
}

/// Parse a JSON Lines run-record log.
pub fn run_records_from_jsonl(text: &str) -> Result<Vec<RunRecord>> {
    text.lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| serde_json::from_str(l).map_err(Error::from))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use gl_runtime::gate::{Match, Rule};
    use gl_runtime::{ActionRef, RiskClass, RunEvent, RunId, SystemIdentity, ToolStatus, VerificationEvent};

    fn ev(id: &str, seq: u64, event: VerificationEvent) -> RunEvent {
        RunEvent {
            id: id.into(),
            parent: None,
            sequence: seq,
            timestamp: "2026-09-19T10:00:00Z".into(),
            actor: None,
            event,
        }
    }

    fn clean_run() -> VerificationRun {
        VerificationRun {
            run_id: RunId::from("run_1"),
            parent_run_id: None,
            system: SystemIdentity { id: "agent".into(), version: None, deployment: None },
            started_at: "2026-09-19T10:00:00Z".into(),
            finished_at: None,
            events: vec![
                ev("e0", 0, VerificationEvent::RunStarted),
                ev(
                    "e1",
                    1,
                    VerificationEvent::ToolCompleted {
                        tool: gl_runtime::ToolRef { name: "crm.lookup".into(), server: None },
                        result_hash: "sha256:aa".into(),
                        status: ToolStatus::Ok,
                    },
                ),
            ],
            artifacts: vec![],
            status: None,
        }
    }

    fn breaching_run() -> VerificationRun {
        let mut run = clean_run();
        run.events.push(ev(
            "e2",
            2,
            VerificationEvent::ActionExecuted {
                action: ActionRef {
                    id: "act1".into(),
                    operation: "wire_transfer".into(),
                    target: None,
                    risk: Some(RiskClass::High),
                },
                result_hash: "sha256:bb".into(),
            },
        ));
        run
    }

    fn log_of(run: &VerificationRun) -> RunLog {
        let mut log = RunLog::new(run.run_id.clone());
        for e in &run.events {
            log.append(e.clone()).unwrap();
        }
        log
    }

    fn policy() -> ExecutionPolicy {
        ExecutionPolicy {
            id: "eu_high_risk_v1".into(),
            hash: Some("sha256:pol".into()),
            rules: vec![Rule {
                id: "no-wire".into(),
                selector: Match::Action { operation: "wire_transfer".into() },
                effect: GateEffect::Deny,
            }],
            default: GateEffect::Allow,
        }
    }

    #[test]
    fn a_clean_run_seals_verifies_and_binds() {
        let run = clean_run();
        let log = log_of(&run);
        let signer = RecordSigner::generate();
        let rec = seal_run(
            &run,
            &log,
            &policy(),
            "5.0.0",
            "rr1".into(),
            "2026-09-19T10:00:02Z".into(),
            None,
            &signer,
        )
        .unwrap();
        assert_eq!(rec.content.gate, GateEffect::Allow);
        assert!(rec.content.breaches.is_empty());
        assert_eq!(rec.content.log_head.as_deref(), log.head());
        verify_run_record(&rec).unwrap();
        verify_run_against_record(&run, &log, &rec).unwrap();
    }

    #[test]
    fn the_gate_verdict_is_sealed_into_the_record() {
        let run = breaching_run();
        let log = log_of(&run);
        let signer = RecordSigner::generate();
        let rec = seal_run(
            &run,
            &log,
            &policy(),
            "5.0.0",
            "rr1".into(),
            "2026-09-19T10:00:02Z".into(),
            None,
            &signer,
        )
        .unwrap();
        assert_eq!(rec.content.gate, GateEffect::Deny);
        assert_eq!(rec.content.breaches.len(), 1);
        verify_run_record(&rec).unwrap();
    }

    #[test]
    fn tampering_with_content_is_caught() {
        let run = breaching_run();
        let log = log_of(&run);
        let signer = RecordSigner::generate();
        let mut rec = seal_run(
            &run,
            &log,
            &policy(),
            "5.0.0",
            "rr1".into(),
            "2026-09-19T10:00:02Z".into(),
            None,
            &signer,
        )
        .unwrap();
        rec.content.gate = GateEffect::Allow; // pretend a denied run passed
        rec.content.breaches.clear();
        assert!(verify_run_record(&rec).is_err());
    }

    #[test]
    fn a_swapped_run_fails_the_binding() {
        let run = clean_run();
        let log = log_of(&run);
        let signer = RecordSigner::generate();
        let rec = seal_run(
            &run,
            &log,
            &policy(),
            "5.0.0",
            "rr1".into(),
            "2026-09-19T10:00:02Z".into(),
            None,
            &signer,
        )
        .unwrap();
        // The record still verifies on its own, but it does not attest to a
        // different run.
        verify_run_record(&rec).unwrap();
        let other = breaching_run();
        assert!(verify_run_against_record(&other, &log_of(&other), &rec).is_err());
    }

    #[test]
    fn content_hash_is_independent_of_time_and_id() {
        let run = clean_run();
        let log = log_of(&run);
        let signer = RecordSigner::generate();
        let a = seal_run(
            &run,
            &log,
            &policy(),
            "5.0.0",
            "a".into(),
            "2026-01-01T00:00:00Z".into(),
            None,
            &signer,
        )
        .unwrap();
        let b = seal_run(
            &run,
            &log,
            &policy(),
            "5.0.0",
            "b".into(),
            "2027-01-01T00:00:00Z".into(),
            None,
            &signer,
        )
        .unwrap();
        assert_eq!(a.content_hash, b.content_hash);
        assert_ne!(a.record_hash, b.record_hash);
    }

    #[test]
    fn chain_links_verify_and_jsonl_round_trips() {
        let run = clean_run();
        let log = log_of(&run);
        let signer = RecordSigner::generate();
        let r1 = seal_run(
            &run,
            &log,
            &policy(),
            "5.0.0",
            "r1".into(),
            "2026-09-19T10:00:02Z".into(),
            None,
            &signer,
        )
        .unwrap();
        let r2 = seal_run(
            &run,
            &log,
            &policy(),
            "5.0.0",
            "r2".into(),
            "2026-09-19T10:00:03Z".into(),
            Some(r1.record_hash.clone()),
            &signer,
        )
        .unwrap();
        verify_run_chain(&[r1.clone(), r2.clone()]).unwrap();
        assert!(verify_run_chain(&[r2.clone(), r1.clone()]).is_err());

        let line = run_record_to_jsonl_line(&r1).unwrap();
        let back = run_records_from_jsonl(&line).unwrap();
        verify_run_record(&back[0]).unwrap();
        assert_eq!(back[0].content, r1.content);
    }
}
