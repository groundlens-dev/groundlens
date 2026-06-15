"""RAG agent triage — deprecated dispatcher kept for backwards compatibility.

The 2026.6.11 / 2026.6.12 API exposed a :func:`rag_rules` dispatcher that
returned different rule sets depending on the ``domain`` argument:

- ``rag_rules(domain="banking")`` returned the 20-rule decision-rationale set
  (now :func:`groundlens.rules.decision_rationale_rules`).
- ``rag_rules(domain="customer_support")`` returned the 7-rule customer-support
  set (now :func:`groundlens.agents.customer_support_rules`).

That dispatch was semantically confusing: the banking branch returned a
*decision-rationale* set, not a *RAG* set. Phase 2 of the rule-set API
refactor (ADR 0001, release 2026.6.13) introduces archetype-named factories
and demotes :func:`rag_rules` to a deprecated alias.

New code should call the canonical factory directly:

- For informational FAQ-RAG agents:
  :func:`groundlens.agents.customer_support_rules` (with ``rag=True``).
- For credit / AML / KYC / sanctions decision rationales:
  :func:`groundlens.rules.decision_rationale_rules` (with ``domain="finance"``).
"""

from __future__ import annotations

import warnings

from groundlens.agents.customer_support import customer_support_rag_rules
from groundlens.rules import RuleSet, groundlens_banking_rules

_SUPPORTED_DOMAINS = ("banking", "customer_support")


def rag_rules(domain: str = "banking") -> RuleSet:
    """Deprecated dispatcher — use the archetype-named factories directly.

    Args:
        domain: ``"banking"`` (default) returns
            :func:`groundlens.rules.decision_rationale_rules` (the 20-rule
            decision-rationale set). ``"customer_support"`` returns
            :func:`groundlens.agents.customer_support_rules` with ``rag=True``
            (the 7-rule informational-agent set).

    Returns:
        The selected :class:`RuleSet`.

    Raises:
        ValueError: If ``domain`` is not in :data:`_SUPPORTED_DOMAINS`.

    .. deprecated:: 2026.6.13
        Call the canonical factory directly:
        :func:`groundlens.rules.decision_rationale_rules` for credit / AML /
        KYC decision rationales, or
        :func:`groundlens.agents.customer_support_rules` for informational
        FAQ-RAG agents. The :func:`rag_rules` dispatcher will be removed in a
        future release.
    """
    if domain not in _SUPPORTED_DOMAINS:
        msg = (
            f"rag_rules(domain={domain!r}) — supported domains are "
            f"{_SUPPORTED_DOMAINS}. The dispatcher is also deprecated; "
            "prefer decision_rationale_rules() or customer_support_rules() "
            "directly."
        )
        raise ValueError(msg)

    if domain == "banking":
        warnings.warn(
            'rag_rules(domain="banking") is deprecated; use '
            'decision_rationale_rules(domain="finance") from groundlens.rules instead. '
            "The dispatcher will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Return the legacy-named ruleset for backwards compatibility with
        # downstream code that asserts on `rs.name`.
        return groundlens_banking_rules()

    # domain == "customer_support"
    warnings.warn(
        'rag_rules(domain="customer_support") is deprecated; use '
        "customer_support_rules(rag=True) from groundlens.agents instead. "
        "The dispatcher will be removed in a future release.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Use the legacy alias so the returned RuleSet keeps its legacy name
    # ("customer_support_rag_v1") for backwards compatibility.
    with warnings.catch_warnings():
        # Suppress the inner DeprecationWarning emitted by the legacy alias —
        # the outer one above is the one the caller should see.
        warnings.simplefilter("ignore", DeprecationWarning)
        return customer_support_rag_rules()
