"""GroundingSwitch — protect agent/RAG state from ungrounded answers.

The Switch sits between Geometry (SGI/DGI) and Consistency. It converts a
geometric score into a decision: may this response be written into the next
turn's context, or would that contaminate the state?

Run::

    python examples/grounding_switch.py
"""

from __future__ import annotations

from groundlens import GroundingSwitch, SwitchAction, check, compute_dgi, compute_sgi

# ── Shared fixtures ─────────────────────────────────────────────────────────

question = (
    "A user of our cloud backup service wants to understand the data retention "
    "rules for the Business plan: how long deleted files can still be recovered."
)

context = (
    "On the Business plan, deleted files are moved to a recovery area and can be "
    "restored for 90 days from the date of deletion; after 90 days they are "
    "permanently purged and cannot be recovered."
)

answer_grounded = (
    "On the Business plan you can restore a deleted file for 90 days after it was "
    "deleted; once those 90 days pass it is purged for good."
)

answer_ungrounded = (
    "Deleted files on the Business plan are kept forever and can always be "
    "restored at any time, so there is no purge window to worry about."
)

# ── Default switch (on_reject=fallback) ─────────────────────────────────────

switch = GroundingSwitch()

print("=== RAG path (SGI) ===")
for label, answer in (("grounded", answer_grounded), ("ungrounded", answer_ungrounded)):
    sgi = compute_sgi(question=question, context=context, response=answer)
    decision = switch.decide(sgi)
    print(f"\n[{label}]")
    print("  ", check(sgi).line())
    print("  action        :", decision.action.value)
    print("  write_to_state:", decision.write_to_state)
    print("  reason        :", decision.reason)

print("\n=== No-source path (DGI) ===")
dgi = compute_dgi(
    question="What is the primary function of red blood cells?",
    response=(
        "Red blood cells provide the characteristic red coloration to blood, "
        "which serves as a visual indicator of circulatory health."
    ),
)
decision = switch.decide(dgi)
print("  ", check(dgi).line())
print("  action        :", decision.action.value)
print("  write_to_state:", decision.write_to_state)
print("  reason        :", decision.reason)

# ── Typical agent loop pattern ──────────────────────────────────────────────

print("\n=== Agent loop pattern ===")
state: list[str] = []
for answer in (answer_grounded, answer_ungrounded):
    sgi = compute_sgi(question=question, context=context, response=answer)
    decision = switch.decide(sgi)
    if decision.write_to_state:
        state.append(answer)
        print("  accepted into state")
    elif decision.action is SwitchAction.FALLBACK:
        print("  fallback — context influence discarded, not written to state")
    elif decision.action is SwitchAction.ESCALATE:
        print("  escalate — send to Consistency / LLM-as-judge")
    else:
        print(f"  {decision.action.value} — not written to state")

print("  state size:", len(state))
