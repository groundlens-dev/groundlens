// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The gate: turn an execution policy plus what an agent is about to do (or
//! already did) into `ALLOW`, `REVIEW` or `DENY`.
//!
//! The rest of `gl-runtime` *observes* a run: it records model calls, tool
//! calls, actions and their outcomes, and seals them into a tamper-evident
//! chain. None of that stops anything. This module *decides*. Without it the
//! runtime watches but never intervenes.
//!
//! Same contract as the rest of the crate: pure data and pure functions, no
//! I/O and no network. A policy is a list of rules; each rule matches a tool
//! call or an action and carries an effect. The first rule that matches wins,
//! and when none matches the policy's `default` applies. `DENY` means do not
//! run it, `REVIEW` means hold it for a human approval, `ALLOW` means let it
//! proceed. Because matching is first-wins, an author orders the strict rules
//! first, the way a firewall lists its deny rules before its allow rules.
//!
//! Two ways to use it. Live, a runtime calls [`ExecutionPolicy::gate_tool`] or
//! [`ExecutionPolicy::gate_action`] before letting a step happen and records
//! the outcome. After the fact, an auditor calls
//! [`ExecutionPolicy::audit_run`] over a finished [`VerificationRun`] to prove
//! the policy was actually honoured, catching an action that ran even though
//! the policy forbade it or required an approval that never came.

use serde::{Deserialize, Serialize};

use crate::{ActionRef, EventId, RiskClass, ToolRef, VerificationEvent, VerificationRun};

/// What the gate lets happen. Serialised in upper case, like [`Decision`].
///
/// [`Decision`]: crate::Decision
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum GateEffect {
    /// Let the step proceed.
    Allow,
    /// Hold the step for a human approval before it may proceed.
    Review,
    /// Do not let the step run.
    Deny,
}

impl GateEffect {
    fn rank(self) -> u8 {
        match self {
            GateEffect::Allow => 0,
            GateEffect::Review => 1,
            GateEffect::Deny => 2,
        }
    }

    /// The stricter of two effects (`DENY` over `REVIEW` over `ALLOW`). Used to
    /// roll a whole run up to its worst outcome.
    pub fn stricter(self, other: GateEffect) -> GateEffect {
        if self.rank() >= other.rank() {
            self
        } else {
            other
        }
    }
}

/// What a rule matches: a tool call, an action, or anything.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "match", rename_all = "snake_case")]
pub enum Match {
    /// A tool by name, optionally scoped to the server that exposes it. A
    /// `server` of `None` matches the tool whatever server it comes from.
    Tool {
        name: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        server: Option<String>,
    },
    /// An action by its operation name.
    Action { operation: String },
    /// Any action whose declared risk is at or above this class. An action
    /// with no declared risk never matches this.
    RiskAtLeast { risk: RiskClass },
    /// The catch-all, useful as an explicit final rule.
    Any,
}

impl Match {
    fn matches_tool(&self, tool: &ToolRef) -> bool {
        match self {
            Match::Tool { name, server } => {
                *name == tool.name && server.as_ref().is_none_or(|s| Some(s) == tool.server.as_ref())
            }
            Match::Any => true,
            _ => false,
        }
    }

    fn matches_action(&self, action: &ActionRef) -> bool {
        match self {
            Match::Action { operation } => *operation == action.operation,
            Match::RiskAtLeast { risk } => action.risk.is_some_and(|r| r >= *risk),
            Match::Any => true,
            _ => false,
        }
    }
}

/// One rule: what it matches and what happens when it does.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Rule {
    pub id: String,
    #[serde(flatten)]
    pub selector: Match,
    pub effect: GateEffect,
}

/// An ordered list of rules and what to do when none of them matches. A
/// conservative deployment sets `default` to `DENY` so anything not explicitly
/// allowed is stopped.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ExecutionPolicy {
    pub id: String,
    /// The policy artefact hash, pinned into records so an auditor knows which
    /// rules produced a decision. The gate does not compute it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hash: Option<String>,
    #[serde(default)]
    pub rules: Vec<Rule>,
    pub default: GateEffect,
}

/// The gate's verdict on one candidate, and why.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GateOutcome {
    pub effect: GateEffect,
    /// The rule that decided, or `None` when the default applied.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub rule_id: Option<String>,
    pub reason: String,
}

/// A gate outcome tied to the event it was reached for.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GatedEvent {
    pub event_id: EventId,
    pub outcome: GateOutcome,
}

/// An action that ran against the policy: either the policy denied it outright
/// or it needed an approval that never appears earlier in the run.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Breach {
    pub action_id: String,
    pub reason: String,
}

/// The result of auditing a whole run.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RunGate {
    /// The strictest effect reached over every gated step, raised to `DENY` if
    /// there is any breach.
    pub effect: GateEffect,
    /// Per-event outcomes, only for the events the gate acted on.
    pub events: Vec<GatedEvent>,
    /// Actions that were executed in breach of the policy. Empty means every
    /// executed action was allowed, or approved when approval was required.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub breaches: Vec<Breach>,
}

impl ExecutionPolicy {
    /// Gate a tool call. Only [`Match::Tool`] and [`Match::Any`] rules can match.
    pub fn gate_tool(&self, tool: &ToolRef) -> GateOutcome {
        for rule in &self.rules {
            if rule.selector.matches_tool(tool) {
                return GateOutcome {
                    effect: rule.effect,
                    rule_id: Some(rule.id.clone()),
                    reason: format!("tool {:?} matched rule {:?}", tool.name, rule.id),
                };
            }
        }
        GateOutcome {
            effect: self.default,
            rule_id: None,
            reason: format!("tool {:?} matched no rule; policy default", tool.name),
        }
    }

    /// Gate an action. [`Match::Action`], [`Match::RiskAtLeast`] and
    /// [`Match::Any`] rules can match.
    pub fn gate_action(&self, action: &ActionRef) -> GateOutcome {
        for rule in &self.rules {
            if rule.selector.matches_action(action) {
                return GateOutcome {
                    effect: rule.effect,
                    rule_id: Some(rule.id.clone()),
                    reason: format!("action {:?} matched rule {:?}", action.operation, rule.id),
                };
            }
        }
        GateOutcome {
            effect: self.default,
            rule_id: None,
            reason: format!("action {:?} matched no rule; policy default", action.operation),
        }
    }

    /// Gate whatever a single event carries. Returns `None` for events with
    /// nothing to gate (a retrieval, a state read, the run's start), so a caller
    /// can walk a log and act only where the gate has something to say.
    pub fn gate_event(&self, event: &VerificationEvent) -> Option<GateOutcome> {
        match event {
            VerificationEvent::ToolRequested { tool, .. } | VerificationEvent::ToolCompleted { tool, .. } => {
                Some(self.gate_tool(tool))
            }
            VerificationEvent::HumanApprovalRequested { action }
            | VerificationEvent::ActionExecuted { action, .. } => Some(self.gate_action(action)),
            _ => None,
        }
    }

    /// Audit a finished run: gate every step, roll the outcomes up to the
    /// strictest one, and check the approval invariant.
    ///
    /// The invariant: an [`ActionExecuted`] whose action the policy marks
    /// `REVIEW` (needs approval) must be preceded, somewhere earlier in the
    /// run, by a [`HumanApprovalGranted`]. An action executed under a `DENY`
    /// rule is a breach whether or not it was approved. Any breach raises the
    /// run's effect to `DENY`.
    ///
    /// The check is run-wide, not action-by-action: the contracts record who
    /// granted an approval but not which action it was for, so a granted
    /// approval anywhere earlier satisfies the invariant. Tying an approval to
    /// one specific action is left to a later revision that follows the event
    /// graph.
    ///
    /// [`ActionExecuted`]: crate::VerificationEvent::ActionExecuted
    /// [`HumanApprovalGranted`]: crate::VerificationEvent::HumanApprovalGranted
    pub fn audit_run(&self, run: &VerificationRun) -> RunGate {
        let mut effect = GateEffect::Allow;
        let mut events = Vec::new();
        let mut breaches = Vec::new();
        let mut approval_seen = false;

        for e in &run.events {
            if matches!(e.event, VerificationEvent::HumanApprovalGranted { .. }) {
                approval_seen = true;
            }
            let Some(outcome) = self.gate_event(&e.event) else { continue };
            effect = effect.stricter(outcome.effect);

            if let VerificationEvent::ActionExecuted { action, .. } = &e.event {
                match outcome.effect {
                    GateEffect::Deny => breaches.push(Breach {
                        action_id: action.id.clone(),
                        reason: format!("executed a denied action ({})", action.operation),
                    }),
                    GateEffect::Review if !approval_seen => breaches.push(Breach {
                        action_id: action.id.clone(),
                        reason: format!(
                            "executed action {} without a preceding human approval",
                            action.operation
                        ),
                    }),
                    _ => {}
                }
            }
            events.push(GatedEvent { event_id: e.id.clone(), outcome });
        }

        if !breaches.is_empty() {
            effect = GateEffect::Deny;
        }
        RunGate { effect, events, breaches }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{RunEvent, SystemIdentity};

    fn tool(name: &str, server: Option<&str>) -> ToolRef {
        ToolRef { name: name.into(), server: server.map(Into::into) }
    }

    fn action(id: &str, operation: &str, risk: Option<RiskClass>) -> ActionRef {
        ActionRef { id: id.into(), operation: operation.into(), target: None, risk }
    }

    /// Deny a dangerous tool, hold high-risk actions for approval, allow the
    /// rest.
    fn policy() -> ExecutionPolicy {
        ExecutionPolicy {
            id: "eu_high_risk_v1".into(),
            hash: None,
            rules: vec![
                Rule {
                    id: "no-shell".into(),
                    selector: Match::Tool { name: "shell.exec".into(), server: None },
                    effect: GateEffect::Deny,
                },
                Rule {
                    id: "no-wire".into(),
                    selector: Match::Action { operation: "wire_transfer".into() },
                    effect: GateEffect::Deny,
                },
                Rule {
                    id: "high-risk-needs-human".into(),
                    selector: Match::RiskAtLeast { risk: RiskClass::High },
                    effect: GateEffect::Review,
                },
            ],
            default: GateEffect::Allow,
        }
    }

    #[test]
    fn first_matching_rule_wins() {
        let p = policy();
        assert_eq!(p.gate_tool(&tool("shell.exec", None)).effect, GateEffect::Deny);
        assert_eq!(p.gate_tool(&tool("crm.lookup", Some("crm-mcp"))).effect, GateEffect::Allow);
    }

    #[test]
    fn tool_server_scoping() {
        let p = ExecutionPolicy {
            id: "p".into(),
            hash: None,
            rules: vec![Rule {
                id: "only-trusted".into(),
                selector: Match::Tool { name: "db.write".into(), server: Some("trusted".into()) },
                effect: GateEffect::Allow,
            }],
            default: GateEffect::Deny,
        };
        // Same tool, wrong server: the scoped rule does not match, default denies.
        assert_eq!(p.gate_tool(&tool("db.write", Some("trusted"))).effect, GateEffect::Allow);
        assert_eq!(p.gate_tool(&tool("db.write", Some("rogue"))).effect, GateEffect::Deny);
    }

    #[test]
    fn risk_threshold_matches_at_or_above() {
        let p = policy();
        assert_eq!(p.gate_action(&action("a", "refund", Some(RiskClass::High))).effect, GateEffect::Review);
        assert_eq!(p.gate_action(&action("a", "refund", Some(RiskClass::Low))).effect, GateEffect::Allow);
        // No declared risk never matches RiskAtLeast.
        assert_eq!(p.gate_action(&action("a", "refund", None)).effect, GateEffect::Allow);
    }

    #[test]
    fn default_applies_and_is_reported_without_a_rule_id() {
        let p = policy();
        let out = p.gate_tool(&tool("anything", None));
        assert_eq!(out.effect, GateEffect::Allow);
        assert!(out.rule_id.is_none());
    }

    #[test]
    fn non_gated_events_return_none() {
        let p = policy();
        assert!(p.gate_event(&VerificationEvent::RunStarted).is_none());
        assert!(p.gate_event(&VerificationEvent::StateRead { key: "balance".into() }).is_none());
    }

    #[test]
    fn stricter_rolls_up() {
        assert_eq!(GateEffect::Allow.stricter(GateEffect::Review), GateEffect::Review);
        assert_eq!(GateEffect::Deny.stricter(GateEffect::Review), GateEffect::Deny);
        assert_eq!(GateEffect::Allow.stricter(GateEffect::Allow), GateEffect::Allow);
    }

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

    fn run(events: Vec<RunEvent>) -> VerificationRun {
        VerificationRun {
            run_id: "run_1".into(),
            parent_run_id: None,
            system: SystemIdentity { id: "agent".into(), version: None, deployment: None },
            started_at: "2026-09-19T10:00:00Z".into(),
            finished_at: None,
            events,
            artifacts: vec![],
            status: None,
        }
    }

    #[test]
    fn audit_flags_a_high_risk_action_executed_without_approval() {
        let g = policy().audit_run(&run(vec![
            ev("e0", 0, VerificationEvent::RunStarted),
            ev(
                "e1",
                1,
                VerificationEvent::ActionExecuted {
                    action: action("act1", "refund", Some(RiskClass::High)),
                    result_hash: "sha256:aa".into(),
                },
            ),
        ]));
        assert_eq!(g.effect, GateEffect::Deny);
        assert_eq!(g.breaches.len(), 1);
        assert_eq!(g.breaches[0].action_id, "act1");
    }

    #[test]
    fn audit_passes_when_the_action_was_approved_first() {
        let g = policy().audit_run(&run(vec![
            ev("e0", 0, VerificationEvent::RunStarted),
            ev(
                "e1",
                1,
                VerificationEvent::HumanApprovalGranted {
                    actor: crate::ActorIdentity {
                        kind: crate::ActorKind::Human,
                        id: "reviewer".into(),
                        name: None,
                    },
                },
            ),
            ev(
                "e2",
                2,
                VerificationEvent::ActionExecuted {
                    action: action("act1", "refund", Some(RiskClass::High)),
                    result_hash: "sha256:aa".into(),
                },
            ),
        ]));
        assert!(g.breaches.is_empty());
        // The action still required review, so the run rolls up to REVIEW.
        assert_eq!(g.effect, GateEffect::Review);
    }

    #[test]
    fn audit_flags_a_denied_action_even_if_approved() {
        let g = policy().audit_run(&run(vec![
            ev(
                "e0",
                0,
                VerificationEvent::HumanApprovalGranted {
                    actor: crate::ActorIdentity {
                        kind: crate::ActorKind::Human,
                        id: "reviewer".into(),
                        name: None,
                    },
                },
            ),
            ev(
                "e1",
                1,
                VerificationEvent::ActionExecuted {
                    action: action("act1", "wire_transfer", Some(RiskClass::High)),
                    result_hash: "sha256:aa".into(),
                },
            ),
        ]));
        assert_eq!(g.effect, GateEffect::Deny);
        assert_eq!(g.breaches.len(), 1);
        assert!(g.breaches[0].reason.contains("denied"));
    }

    #[test]
    fn rule_round_trips_through_json() {
        let rule = Rule {
            id: "no-shell".into(),
            selector: Match::Tool { name: "shell.exec".into(), server: None },
            effect: GateEffect::Deny,
        };
        let text = serde_json::to_string(&rule).unwrap();
        assert!(text.contains(r#""match":"tool""#), "{text}");
        assert!(text.contains(r#""effect":"DENY""#), "{text}");
        let back: Rule = serde_json::from_str(&text).unwrap();
        assert_eq!(rule, back);
    }
}
