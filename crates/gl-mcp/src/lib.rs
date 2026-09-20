// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The MCP adapter: turn a real Model Context Protocol execution into a
//! GroundLens run.
//!
//! [`gl_runtime`] defines what a run *is*: an ordered, hash-chained log of
//! events (a model call, a tool request, a tool result, an action). This crate
//! is the first thing that fills one from a real execution. An agent driving
//! MCP servers exchanges JSON-RPC messages: `tools/call` requests, their
//! results, `sampling/createMessage` for a model turn. Feed those messages to
//! an [`McpRecorder`] and it produces the same [`RunLog`] and
//! [`VerificationRun`] the rest of the engine gates, seals and signs.
//!
//! Two ways in. The typed methods ([`McpRecorder::record_tool_requested`] and
//! friends) are for an integration that already has structured data. The
//! [`McpRecorder::ingest_jsonrpc`] path takes raw JSON-RPC messages straight
//! off an MCP transport and does the request/response correlation itself, so a
//! recorded MCP trace becomes evidence with no glue code.
//!
//! Like the runtime, the adapter stores **hashes**, not content: a tool's
//! arguments and result, a model's input and output, are hashed into the event
//! and never kept. An auditor recomputes the hash from data held elsewhere; the
//! run itself is safe to keep in a regulated place. The adapter does no I/O and
//! keeps no clock: the caller passes the timestamp of each message, so the same
//! trace replays to the same run on any machine.

use std::collections::HashMap;

use serde_json::Value as Json;

use gl_core::canonical::content_hash;
use gl_core::{Error, Result};
use gl_runtime::{
    ActionRef, Decision, EventId, ExecutionStatus, ModelRef, RunEvent, RunId, RunLog, SourceRef,
    SystemIdentity, ToolRef, ToolStatus, VerificationEvent, VerificationRun,
};

/// A tool call or a model turn waiting for its response, keyed by JSON-RPC id.
enum Pending {
    /// A `tools/call` in flight: the event that requested it and which tool.
    Tool { requested: EventId, tool: ToolRef },
    /// A `sampling/createMessage` in flight: the input to hash with the output.
    Model { input: Json },
}

/// Records an MCP execution into a [`RunLog`]. Build one with [`new`], feed it
/// the execution, then read [`run`] or [`log`] for the rest of the engine.
///
/// [`new`]: McpRecorder::new
/// [`run`]: McpRecorder::run
/// [`log`]: McpRecorder::log
pub struct McpRecorder {
    run_id: RunId,
    parent_run_id: Option<RunId>,
    system: SystemIdentity,
    default_server: Option<String>,
    started_at: String,
    finished_at: Option<String>,
    status: Option<ExecutionStatus>,
    log: RunLog,
    seq: u64,
    pending: HashMap<String, Pending>,
}

impl McpRecorder {
    /// Start a recorder. Appends the opening `RunStarted` event at `started_at`.
    pub fn new(
        run_id: impl Into<RunId>,
        system: SystemIdentity,
        started_at: impl Into<String>,
    ) -> Result<Self> {
        let run_id = run_id.into();
        let started_at = started_at.into();
        let mut rec = McpRecorder {
            log: RunLog::new(run_id.clone()),
            run_id,
            parent_run_id: None,
            system,
            default_server: None,
            started_at: started_at.clone(),
            finished_at: None,
            status: None,
            seq: 0,
            pending: HashMap::new(),
        };
        rec.push(None, &started_at, VerificationEvent::RunStarted)?;
        Ok(rec)
    }

    /// The server name recorded for a tool that does not name its own.
    pub fn with_server(mut self, server: impl Into<String>) -> Self {
        self.default_server = Some(server.into());
        self
    }

    /// Mark this run as spawned by another (a sub-agent).
    pub fn with_parent(mut self, parent: impl Into<RunId>) -> Self {
        self.parent_run_id = Some(parent.into());
        self
    }

    fn push(&mut self, parent: Option<EventId>, ts: &str, event: VerificationEvent) -> Result<EventId> {
        let id = EventId::from(format!("ev-{}", self.seq));
        self.log.append(RunEvent {
            id: id.clone(),
            parent,
            sequence: self.seq,
            timestamp: ts.to_string(),
            actor: None,
            event,
        })?;
        self.seq += 1;
        Ok(id)
    }

    /// Record a model turn. `input` and `output` are hashed, not stored.
    pub fn record_model_invocation(
        &mut self,
        model_id: &str,
        model_hash: Option<&str>,
        input: &Json,
        output: &Json,
        ts: &str,
    ) -> Result<EventId> {
        let event = VerificationEvent::ModelInvocation {
            model: ModelRef { id: model_id.into(), hash: model_hash.map(Into::into) },
            input_hash: content_hash(input)?,
            output_hash: content_hash(output)?,
        };
        self.push(None, ts, event)
    }

    /// Record a tool call being requested. `call_id` is the JSON-RPC id, kept so
    /// the matching result links back to this event.
    pub fn record_tool_requested(
        &mut self,
        call_id: Option<&str>,
        name: &str,
        server: Option<&str>,
        arguments: &Json,
        ts: &str,
    ) -> Result<EventId> {
        let tool = ToolRef {
            name: name.into(),
            server: server.map(Into::into).or_else(|| self.default_server.clone()),
        };
        let id = self.push(
            None,
            ts,
            VerificationEvent::ToolRequested { tool: tool.clone(), arguments_hash: content_hash(arguments)? },
        )?;
        if let Some(cid) = call_id {
            self.pending.insert(cid.to_string(), Pending::Tool { requested: id.clone(), tool });
        }
        Ok(id)
    }

    /// Record a tool call finishing. When `call_id` matches a pending request,
    /// the completion links to it and reuses its tool; otherwise pass `tool`.
    pub fn record_tool_completed(
        &mut self,
        call_id: Option<&str>,
        tool: Option<ToolRef>,
        result: &Json,
        status: ToolStatus,
        ts: &str,
    ) -> Result<EventId> {
        let (parent, tool) = match call_id.and_then(|c| self.pending.remove(c)) {
            Some(Pending::Tool { requested, tool: pending_tool }) => {
                (Some(requested), tool.unwrap_or(pending_tool))
            }
            _ => (
                None,
                tool.ok_or_else(|| {
                    Error::InvalidInput(
                        "tool completed without a matching request needs an explicit tool".into(),
                    )
                })?,
            ),
        };
        self.push(
            parent,
            ts,
            VerificationEvent::ToolCompleted { tool, result_hash: content_hash(result)?, status },
        )
    }

    /// Record an action with side effects that was executed. Whether a tool call
    /// counts as an action is a policy question, not the adapter's; a caller
    /// that knows a call changed the world records it here as well.
    pub fn record_action_executed(&mut self, action: ActionRef, result: &Json, ts: &str) -> Result<EventId> {
        self.push(None, ts, VerificationEvent::ActionExecuted { action, result_hash: content_hash(result)? })
    }

    /// Record a retrieval. `query` is hashed; `documents` are referenced.
    pub fn record_retrieval(&mut self, query: &Json, documents: Vec<SourceRef>, ts: &str) -> Result<EventId> {
        self.push(None, ts, VerificationEvent::Retrieval { query_hash: content_hash(query)?, documents })
    }

    /// Ingest one JSON-RPC message off an MCP transport. Returns the event it
    /// recorded, or `None` for a message that carries nothing to record (an
    /// unrelated method, a notification, a response with no pending request).
    ///
    /// Handled: a `tools/call` request becomes a [`ToolRequested`]; its result
    /// becomes a [`ToolCompleted`] linked back to it, with the status read from
    /// a protocol error or the result's `isError`; a `sampling/createMessage`
    /// request is held until its result and the pair becomes a
    /// [`ModelInvocation`].
    ///
    /// [`ToolRequested`]: gl_runtime::VerificationEvent::ToolRequested
    /// [`ToolCompleted`]: gl_runtime::VerificationEvent::ToolCompleted
    /// [`ModelInvocation`]: gl_runtime::VerificationEvent::ModelInvocation
    pub fn ingest_jsonrpc(&mut self, message: &Json, ts: &str) -> Result<Option<EventId>> {
        let id_str = message.get("id").filter(|v| !v.is_null()).map(json_id_to_string);

        if let Some(method) = message.get("method").and_then(|m| m.as_str()) {
            return match method {
                "tools/call" => {
                    let params = message.get("params").cloned().unwrap_or(Json::Null);
                    let name = params
                        .get("name")
                        .and_then(|n| n.as_str())
                        .ok_or_else(|| Error::InvalidInput("tools/call without a name".into()))?;
                    let args = params.get("arguments").cloned().unwrap_or(Json::Null);
                    Ok(Some(self.record_tool_requested(id_str.as_deref(), name, None, &args, ts)?))
                }
                "sampling/createMessage" => {
                    if let Some(cid) = id_str {
                        let input = message.get("params").cloned().unwrap_or(Json::Null);
                        self.pending.insert(cid, Pending::Model { input });
                    }
                    Ok(None) // recorded when its result arrives
                }
                _ => Ok(None), // other methods and notifications are not gated evidence yet
            };
        }

        // No method: a response. Record it only if it answers something pending.
        let Some(cid) = id_str else { return Ok(None) };
        match self.pending.remove(&cid) {
            Some(Pending::Tool { requested, tool }) => {
                let is_error = message.get("error").is_some()
                    || message
                        .get("result")
                        .and_then(|r| r.get("isError"))
                        .and_then(|b| b.as_bool())
                        .unwrap_or(false);
                let result =
                    message.get("result").or_else(|| message.get("error")).cloned().unwrap_or(Json::Null);
                let status = if is_error { ToolStatus::Error } else { ToolStatus::Ok };
                let id = self.push(
                    Some(requested),
                    ts,
                    VerificationEvent::ToolCompleted { tool, result_hash: content_hash(&result)?, status },
                )?;
                Ok(Some(id))
            }
            Some(Pending::Model { input }) => {
                let result = message.get("result").cloned().unwrap_or(Json::Null);
                let model_id = result.get("model").and_then(|m| m.as_str()).unwrap_or("unknown");
                let id = self.push(
                    None,
                    ts,
                    VerificationEvent::ModelInvocation {
                        model: ModelRef { id: model_id.into(), hash: None },
                        input_hash: content_hash(&input)?,
                        output_hash: content_hash(&result)?,
                    },
                )?;
                Ok(Some(id))
            }
            None => Ok(None),
        }
    }

    /// Ingest one line of a JSON-RPC stream (an MCP stdio transport is exactly
    /// this: one JSON object per line).
    pub fn ingest_line(&mut self, line: &str, ts: &str) -> Result<Option<EventId>> {
        let message: Json = serde_json::from_str(line).map_err(Error::from)?;
        self.ingest_jsonrpc(&message, ts)
    }

    /// Close the run. Appends `VerificationCompleted` when a decision is given,
    /// then records how the execution ended.
    pub fn finish(
        &mut self,
        decision: Option<Decision>,
        status: ExecutionStatus,
        finished_at: impl Into<String>,
    ) -> Result<()> {
        let ts = finished_at.into();
        if let Some(d) = decision {
            self.push(None, &ts, VerificationEvent::VerificationCompleted { decision: d })?;
        }
        self.finished_at = Some(ts);
        self.status = Some(status);
        Ok(())
    }

    /// The hash-chained event log, ready to seal.
    pub fn log(&self) -> &RunLog {
        &self.log
    }

    /// Assemble the whole run from what has been recorded so far.
    pub fn run(&self) -> VerificationRun {
        VerificationRun {
            run_id: self.run_id.clone(),
            parent_run_id: self.parent_run_id.clone(),
            system: self.system.clone(),
            started_at: self.started_at.clone(),
            finished_at: self.finished_at.clone(),
            events: self.log.events().cloned().collect(),
            artifacts: vec![],
            status: self.status,
        }
    }
}

/// A JSON-RPC id is a string or a number. Render it the same way whether it
/// arrives on the request or the response, so the two correlate.
fn json_id_to_string(v: &Json) -> String {
    match v {
        Json::String(s) => s.clone(),
        other => other.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn recorder() -> McpRecorder {
        McpRecorder::new(
            "run_1",
            SystemIdentity { id: "agent".into(), version: None, deployment: None },
            "2026-09-20T10:00:00Z",
        )
        .unwrap()
        .with_server("crm-mcp")
    }

    #[test]
    fn typed_api_records_a_valid_sealable_run() {
        let mut r = recorder();
        r.record_model_invocation("claude", None, &json!({"q": "balance?"}), &json!({"a": "1,000"}), "t1")
            .unwrap();
        let req = r.record_tool_requested(Some("7"), "crm.lookup", None, &json!({"id": 42}), "t2").unwrap();
        let done = r
            .record_tool_completed(
                Some("7"),
                None,
                &json!({"isError": false, "content": []}),
                ToolStatus::Ok,
                "t3",
            )
            .unwrap();
        r.finish(Some(Decision::Pass), ExecutionStatus::Completed, "2026-09-20T10:00:05Z").unwrap();

        // The completion links back to its request.
        let run = r.run();
        let completed = run.events.iter().find(|e| e.id == done).unwrap();
        assert_eq!(completed.parent.as_ref(), Some(&req));
        // The log is a valid, verifiable chain and the run is well formed.
        r.log().verify().unwrap();
        run.validate().unwrap();
        assert_eq!(run.decision(), Some(Decision::Pass));
        assert_eq!(run.finished_at.as_deref(), Some("2026-09-20T10:00:05Z"));
    }

    #[test]
    fn arguments_are_hashed_not_stored() {
        let mut r = recorder();
        r.record_tool_requested(Some("1"), "crm.lookup", None, &json!({"secret": "acct-999"}), "t1").unwrap();
        let run = r.run();
        let ev = run.events.iter().find_map(|e| match &e.event {
            VerificationEvent::ToolRequested { arguments_hash, .. } => Some(arguments_hash.clone()),
            _ => None,
        });
        let h = ev.unwrap();
        assert!(h.starts_with("sha256:"));
        assert_eq!(h, content_hash(&json!({"secret": "acct-999"})).unwrap());
        // The raw value appears nowhere in the serialised run.
        let text = serde_json::to_string(&run).unwrap();
        assert!(!text.contains("acct-999"), "raw arguments leaked into the run");
    }

    #[test]
    fn ingests_a_tool_call_and_its_result() {
        let mut r = recorder();
        assert!(r
            .ingest_jsonrpc(
                &json!({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                "params": {"name": "crm.lookup", "arguments": {"id": 42}}}),
                "t1"
            )
            .unwrap()
            .is_some());
        let done = r
            .ingest_jsonrpc(
                &json!({"jsonrpc": "2.0", "id": 7, "result": {"isError": false, "content": []}}),
                "t2",
            )
            .unwrap();
        assert!(done.is_some());
        let run = r.run();
        // RunStarted + ToolRequested + ToolCompleted.
        assert_eq!(run.events.len(), 3);
        let (req_id, completed) = (
            run.events
                .iter()
                .find(|e| matches!(e.event, VerificationEvent::ToolRequested { .. }))
                .unwrap()
                .id
                .clone(),
            run.events.iter().find(|e| matches!(e.event, VerificationEvent::ToolCompleted { .. })).unwrap(),
        );
        assert_eq!(completed.parent.as_ref(), Some(&req_id));
        match &completed.event {
            VerificationEvent::ToolCompleted { tool, status, .. } => {
                assert_eq!(tool.name, "crm.lookup");
                assert_eq!(tool.server.as_deref(), Some("crm-mcp"));
                assert_eq!(*status, ToolStatus::Ok);
            }
            _ => unreachable!(),
        }
        r.log().verify().unwrap();
    }

    #[test]
    fn a_tool_error_result_is_recorded_as_error() {
        let mut r = recorder();
        r.ingest_jsonrpc(
            &json!({"jsonrpc": "2.0", "id": "abc", "method": "tools/call",
            "params": {"name": "crm.lookup", "arguments": {}}}),
            "t1",
        )
        .unwrap();
        r.ingest_jsonrpc(
            &json!({"jsonrpc": "2.0", "id": "abc", "result": {"isError": true, "content": []}}),
            "t2",
        )
        .unwrap();
        let run = r.run();
        let status = run.events.iter().find_map(|e| match &e.event {
            VerificationEvent::ToolCompleted { status, .. } => Some(*status),
            _ => None,
        });
        assert_eq!(status, Some(ToolStatus::Error));
    }

    #[test]
    fn a_protocol_error_response_is_recorded_as_error() {
        let mut r = recorder();
        r.ingest_jsonrpc(
            &json!({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "t", "arguments": {}}}),
            "t1",
        )
        .unwrap();
        r.ingest_jsonrpc(
            &json!({"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "boom"}}),
            "t2",
        )
        .unwrap();
        let run = r.run();
        let status = run.events.iter().find_map(|e| match &e.event {
            VerificationEvent::ToolCompleted { status, .. } => Some(*status),
            _ => None,
        });
        assert_eq!(status, Some(ToolStatus::Error));
    }

    #[test]
    fn sampling_request_and_result_become_one_model_invocation() {
        let mut r = recorder();
        assert!(r
            .ingest_jsonrpc(
                &json!({"jsonrpc": "2.0", "id": 3, "method": "sampling/createMessage",
                "params": {"messages": [{"role": "user", "content": "hi"}]}}),
                "t1"
            )
            .unwrap()
            .is_none()); // nothing recorded yet
        assert!(r
            .ingest_jsonrpc(
                &json!({"jsonrpc": "2.0", "id": 3,
                "result": {"model": "claude-x", "role": "assistant", "content": {"text": "hello"}}}),
                "t2"
            )
            .unwrap()
            .is_some());
        let run = r.run();
        let model = run.events.iter().find_map(|e| match &e.event {
            VerificationEvent::ModelInvocation { model, .. } => Some(model.id.clone()),
            _ => None,
        });
        assert_eq!(model.as_deref(), Some("claude-x"));
        assert_eq!(run.events.len(), 2); // RunStarted + ModelInvocation
    }

    #[test]
    fn unrelated_messages_record_nothing() {
        let mut r = recorder();
        assert!(r
            .ingest_jsonrpc(&json!({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}), "t1")
            .unwrap()
            .is_none());
        assert!(r
            .ingest_jsonrpc(&json!({"jsonrpc": "2.0", "method": "notifications/message", "params": {}}), "t2")
            .unwrap()
            .is_none());
        // A response to something we never saw.
        assert!(r
            .ingest_jsonrpc(&json!({"jsonrpc": "2.0", "id": 99, "result": {}}), "t3")
            .unwrap()
            .is_none());
        assert_eq!(r.run().events.len(), 1); // only RunStarted
    }

    #[test]
    fn ingest_line_parses_a_stdio_frame() {
        let mut r = recorder();
        let line = r#"{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"t","arguments":{}}}"#;
        assert!(r.ingest_line(line, "t1").unwrap().is_some());
    }
}
