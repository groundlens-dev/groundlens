// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The one pipeline for a run, next to the one for an answer.
//!
//! [`verify`](crate::verify) takes an answer and its sources and seals an
//! [`EvidenceRecord`](gl_record::EvidenceRecord). This takes a real MCP
//! execution and seals a [`RunRecord`](gl_record::RunRecord): the adapter turns
//! the trace into an event log, the execution policy gates it, and the log is
//! signed and chained with the same guarantee. The CLI and the Python package
//! call this and nothing else, so there is one implementation of "verify an
//! execution under a policy and seal the record".

use gl_core::canonical::content_hash;
use gl_core::{Error, Result};
use gl_mcp::McpRecorder;
use gl_record::{seal_run, RecordSigner, RunRecord};
use gl_runtime::{ExecutionPolicy, ExecutionStatus, SystemIdentity};
use serde::{Deserialize, Serialize};

/// Everything one run verification needs. Strings and JSON, so every binding
/// shares the shape.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunVerifyRequest {
    /// The MCP trace: one JSON-RPC message per line. A message may carry a
    /// top-level `ts` (an ISO timestamp); the event uses it, otherwise the
    /// previous timestamp, otherwise `started_at`.
    pub trace: String,
    /// The execution policy, as a JSON document (a caller with YAML converts it
    /// first, the way rule sets are handled elsewhere).
    pub policy_json: String,
    pub run_id: String,
    /// The deployed system the run belongs to.
    pub system_id: String,
    #[serde(default)]
    pub system_version: Option<String>,
    /// When the run began. The current time when absent.
    #[serde(default)]
    pub started_at: Option<String>,
    /// Ed25519 seed, 32 bytes hex. Ephemeral key when absent.
    #[serde(default)]
    pub signing_key_hex: Option<String>,
    #[serde(default)]
    pub previous_record_hash: Option<String>,
}

fn now() -> String {
    chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
}

fn signer_from(seed: &Option<String>) -> Result<RecordSigner> {
    match seed {
        Some(seed) => {
            let bytes: [u8; 32] = hex::decode(seed)
                .ok()
                .and_then(|v| v.try_into().ok())
                .ok_or_else(|| Error::InvalidInput("signing key must be 32 bytes hex".into()))?;
            Ok(RecordSigner::from_bytes(&bytes))
        }
        None => Ok(RecordSigner::generate()),
    }
}

/// Build the run from the trace, gate it under the policy, and seal a signed
/// record. The record carries the gate verdict and any breaches; read
/// `record.content.gate` for the decision.
pub fn verify_run(req: &RunVerifyRequest) -> Result<RunRecord> {
    let mut policy: ExecutionPolicy =
        serde_json::from_str(&req.policy_json).map_err(|e| Error::InvalidInput(format!("policy: {e}")))?;
    // Pin the policy by hash so the record names which rules decided. Computed
    // over {id, rules, default}, since an absent hash is not serialised.
    if policy.hash.is_none() {
        policy.hash = Some(content_hash(&policy)?);
    }

    let started_at = req.started_at.clone().unwrap_or_else(now);
    let system =
        SystemIdentity { id: req.system_id.clone(), version: req.system_version.clone(), deployment: None };
    let mut rec = McpRecorder::new(req.run_id.clone(), system, started_at.clone())?;

    let mut last_ts = started_at.clone();
    for (i, line) in req.trace.lines().enumerate() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let message: serde_json::Value = serde_json::from_str(line)
            .map_err(|e| Error::InvalidInput(format!("trace line {}: {e}", i + 1)))?;
        let ts = message.get("ts").and_then(|v| v.as_str()).unwrap_or(&last_ts).to_string();
        rec.ingest_jsonrpc(&message, &ts)?;
        last_ts = ts;
    }
    rec.finish(None, ExecutionStatus::Completed, last_ts.clone())?;

    let run = rec.run();
    let run_hash = content_hash(&run)?;
    let record_id = format!("run_{}", &run_hash[7..19]);
    seal_run(
        &run,
        rec.log(),
        &policy,
        gl_core::ENGINE_VERSION,
        record_id,
        now(),
        req.previous_record_hash.clone(),
        &signer_from(&req.signing_key_hex)?,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use gl_record::verify_run_record;
    use gl_runtime::GateEffect;

    const POLICY: &str = r#"{
        "id": "eu_high_risk_v1",
        "rules": [
            {"id": "no-shell", "match": "tool", "name": "shell.exec", "effect": "DENY"}
        ],
        "default": "ALLOW"
    }"#;

    const CLEAN_TRACE: &str = r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"crm.lookup","arguments":{"account":42}},"ts":"2026-09-20T10:00:00Z"}
{"jsonrpc":"2.0","id":1,"result":{"isError":false,"content":[]},"ts":"2026-09-20T10:00:01Z"}"#;

    const SHELL_TRACE: &str = r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"shell.exec","arguments":{"cmd":"rm -rf /"}},"ts":"2026-09-20T10:00:00Z"}
{"jsonrpc":"2.0","id":1,"result":{"isError":true,"content":[]},"ts":"2026-09-20T10:00:01Z"}"#;

    fn req(trace: &str) -> RunVerifyRequest {
        RunVerifyRequest {
            trace: trace.into(),
            policy_json: POLICY.into(),
            run_id: "run_1".into(),
            system_id: "agent".into(),
            system_version: None,
            started_at: Some("2026-09-20T10:00:00Z".into()),
            signing_key_hex: None,
            previous_record_hash: None,
        }
    }

    #[test]
    fn a_clean_run_seals_and_allows() {
        let rec = verify_run(&req(CLEAN_TRACE)).unwrap();
        assert_eq!(rec.content.gate, GateEffect::Allow);
        assert!(rec.content.policy_hash.is_some());
        verify_run_record(&rec).unwrap();
    }

    #[test]
    fn a_forbidden_tool_is_denied() {
        let rec = verify_run(&req(SHELL_TRACE)).unwrap();
        assert_eq!(rec.content.gate, GateEffect::Deny);
        verify_run_record(&rec).unwrap();
    }

    #[test]
    fn the_content_hash_is_stable_across_runs_of_the_same_trace() {
        let a = verify_run(&req(CLEAN_TRACE)).unwrap();
        let b = verify_run(&req(CLEAN_TRACE)).unwrap();
        // Same trace, same policy, same run: same content, even though the
        // record id and signing time differ.
        assert_eq!(a.content_hash, b.content_hash);
    }
}
