"""The product entry point: :func:`check`.

One call, one decision, one audit record::

    from groundlens.control import check

    result = check(
        answer,
        [{"id": "policy.pdf#p4", "text": "..."}],
        ruleset="eu-retail-banking",
        metadata={"product_type": "mortgage", "disclosure_set": "es-2026"},
        reference_date=date(2026, 8, 8),
    )
    result.decision   # Decision.CLEAR or Decision.ESCALATE

The decision rule is the whole rule: escalate if anything failed, otherwise
clear. There is no score, no threshold and no float, because a number between
zero and one invites the reader to move the line later, and a control whose
line moves is not a control.

Orchestration order is fixed: normalise, extract facts, match them against the
evidence, evaluate the pack's rules, decide, build the audit record.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from groundlens.audit_record import (
    Counts,
    PredicateRef,
    RulesetRef,
    build_record,
)
from groundlens.determinism import normalise_text
from groundlens.facts import extract_facts, match_facts
from groundlens.packs.evaluate import evaluate_pack, missing_metadata_findings
from groundlens.packs.loader import Pack, load_pack
from groundlens.types import Decision, Evidence, Finding, MatchState, Result, Severity

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from groundlens.packs.predicates import PredicateRegistry
    from groundlens.types import Fact, Match

__all__ = ["check"]

_UNDECLARED_LOCALE = "undeclared"


# ── Input normalisation ─────────────────────────────────────────────────────


def _nfkc(text: str) -> str:
    """Normalise once. Every span in the result indexes into this output.

    :func:`groundlens.determinism.normalise_text` is NFKC plus the fixed
    whitespace and invisible-character policy, and it is idempotent. Using it
    here rather than a bare ``unicodedata.normalize`` is what makes
    ``answer_sha256`` in the audit record the digest of *exactly* the string
    the spans point into: :func:`groundlens.audit_record.sha256_text` runs the
    same function, so hashing an already-normalised string is a no-op.
    A record whose hash identifies a slightly different string than the one
    that was analysed is not an audit trail.
    """
    return normalise_text(text)


def _coerce_evidence(evidence: object) -> tuple[Evidence, ...]:
    """Turn the caller's evidence into normalised, id-sorted :class:`Evidence`.

    Raises:
        TypeError: If a bare string is passed, or an item is neither an
            ``Evidence`` nor a mapping with ``id`` and ``text``.
        ValueError: If two pieces of evidence share an id.
    """
    if isinstance(evidence, str | bytes):
        msg = (
            "evidence must be a sequence of Evidence objects or of "
            '{"id": ..., "text": ...} mappings, not a single string. Every '
            "piece of evidence needs an id so that a finding can point at the "
            "source a reviewer has to open."
        )
        raise TypeError(msg)
    try:
        items = list(cast("Sequence[object]", evidence))
    except TypeError as exc:
        msg = (
            "evidence must be a sequence of Evidence objects or of "
            f'{{"id": ..., "text": ...}} mappings, got {type(evidence).__name__}.'
        )
        raise TypeError(msg) from exc

    out: list[Evidence] = []
    for position, item in enumerate(items):
        if isinstance(item, Evidence):
            out.append(Evidence(id=item.id, text=_nfkc(item.text)))
            continue
        if isinstance(item, str | bytes):
            msg = (
                f"evidence[{position}] is a bare string. Pass "
                '{"id": "...", "text": "..."} instead: a finding has to name the '
                "source it came from, and a string carries no id."
            )
            raise TypeError(msg)
        if isinstance(item, dict):
            unknown = sorted(set(item) - {"id", "text"})
            if unknown:
                msg = (
                    f"evidence[{position}] has unexpected key(s) "
                    f"{', '.join(repr(key) for key in unknown)}. Only 'id' and "
                    "'text' are read."
                )
                raise TypeError(msg)
            missing = sorted({"id", "text"} - set(item))
            if missing:
                msg = (
                    f"evidence[{position}] is missing "
                    f"{', '.join(repr(key) for key in missing)}. Every piece of "
                    "evidence needs an id and a text."
                )
                raise TypeError(msg)
            item_id = item["id"]
            item_text = item["text"]
            if not isinstance(item_id, str) or not item_id.strip():
                msg = f"evidence[{position}]['id'] must be a non-empty string."
                raise TypeError(msg)
            if not isinstance(item_text, str):
                msg = f"evidence[{position}]['text'] must be a string."
                raise TypeError(msg)
            out.append(Evidence(id=item_id, text=_nfkc(item_text)))
            continue
        msg = (
            f"evidence[{position}] is a {type(item).__name__}. Pass an Evidence "
            'object or a {"id": ..., "text": ...} mapping.'
        )
        raise TypeError(msg)

    seen: set[str] = set()
    for item_evidence in out:
        if item_evidence.id in seen:
            msg = (
                f"evidence id {item_evidence.id!r} appears more than once. Ids "
                "have to be unique so a finding points at exactly one source."
            )
            raise ValueError(msg)
        seen.add(item_evidence.id)

    return tuple(sorted(out, key=lambda item: item.id))


def _coerce_reference_date(reference_date: object) -> datetime.date | None:
    """Accept a ``date`` or an ISO ``YYYY-MM-DD`` string, and nothing else."""
    if reference_date is None:
        return None
    if isinstance(reference_date, datetime.datetime):
        msg = (
            "reference_date must be a date, not a datetime. A time of day would "
            "make the same inputs resolve differently depending on when they "
            "were run."
        )
        raise TypeError(msg)
    if isinstance(reference_date, datetime.date):
        return reference_date
    if isinstance(reference_date, str):
        try:
            return datetime.date.fromisoformat(reference_date)
        except ValueError as exc:
            msg = f"reference_date {reference_date!r} is not an ISO date (YYYY-MM-DD)."
            raise ValueError(msg) from exc
    msg = (
        "reference_date must be a date or an ISO date string, got "
        f"{type(reference_date).__name__}."
    )
    raise TypeError(msg)


def _resolve_pack(ruleset: object) -> Pack:
    if isinstance(ruleset, Pack):
        return ruleset
    if isinstance(ruleset, str | Path):
        return load_pack(ruleset)
    msg = (
        "ruleset must be a pack name, a path to a pack.yaml, or a Pack loaded "
        f"with groundlens.packs.load_pack, got {type(ruleset).__name__}."
    )
    raise TypeError(msg)


# ── Ordering and counting ───────────────────────────────────────────────────


def _finding_sort_key(finding: Finding) -> tuple[str, tuple[int, int], str]:
    span = finding.fact.span if finding.fact is not None else (-1, -1)
    return (finding.code, span, finding.rule_id or "")


def _counts(
    facts: tuple[Fact, ...],
    matches: tuple[Match, ...],
    pack: Pack,
    findings: tuple[Finding, ...],
) -> Counts:
    states = [match.state for match in matches]
    failed_rules = {
        finding.rule_id
        for finding in findings
        if finding.rule_id is not None and finding.code != "rule.passed"
    }
    return Counts(
        facts_extracted=len(facts),
        facts_matched=sum(1 for state in states if state is MatchState.MATCHED),
        facts_unmatched=sum(1 for state in states if state is MatchState.UNMATCHED),
        facts_contradicted=sum(1 for state in states if state is MatchState.CONTRADICTED),
        rules_evaluated=len(pack.rules),
        rules_failed=len(failed_rules),
    )


def _extractor_version() -> str:
    from groundlens import facts as facts_module

    version = getattr(facts_module, "EXTRACTOR_VERSION", "1")
    return str(version)


def _predicate_entries(pack: Pack, registry: PredicateRegistry | None) -> tuple[PredicateRef, ...]:
    from groundlens.packs import predicates as predicates_module

    active = predicates_module.REGISTRY if registry is None else registry
    return tuple(
        PredicateRef(
            name=active.entry(name).name,
            source_sha256=active.entry(name).source_sha256,
        )
        for name in pack.predicate_names()
    )


# ── Entry point ─────────────────────────────────────────────────────────────


def check(
    answer: str,
    evidence: Sequence[Evidence] | Sequence[Mapping[str, str]],
    *,
    ruleset: str | Path | Pack,
    tools_output: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    reference_date: datetime.date | str | None = None,
    registry: PredicateRegistry | None = None,
) -> Result:
    """Check an answer against its evidence under a rule pack.

    Args:
        answer: The text to check. NFKC-normalised once, here; every span in
            the result indexes into the normalised form.
        evidence: A sequence of :class:`~groundlens.types.Evidence` or of
            ``{"id": ..., "text": ...}`` mappings. A bare string is rejected.
        ruleset: A shipped pack name, a path to a ``pack.yaml``, or an already
            loaded :class:`~groundlens.packs.loader.Pack`.
        tools_output: Optional tool transcript. Hashed into the audit record
            and passed to predicates.
        metadata: Caller-supplied context. Keys the pack declares under
            ``requires_metadata`` must be present; absence is a FAIL. Values
            are read but never written to the audit record, because they may
            carry personal data.
        reference_date: The date relative dates resolve against, as a
            ``date`` or an ISO string. There is no wall clock in this path, so
            a pack that reads relative dates requires this argument.
        registry: Predicate registry override, for tests and for callers who
            ship their own predicates.

    Returns:
        A :class:`~groundlens.types.Result`: a decision, sorted findings and
        an audit record. No score.

    Raises:
        TypeError: If ``answer`` is not a string, or the evidence is not
            shaped as documented.
        ValueError: If two pieces of evidence share an id, or the pack needs a
            reference date and none was given.
        PackError: If the pack cannot be loaded or fails validation.
    """
    if not isinstance(answer, str):
        msg = f"answer must be a string, got {type(answer).__name__}."
        raise TypeError(msg)

    pack = _resolve_pack(ruleset)
    normalised_answer = _nfkc(answer)
    normalised_tools = _nfkc(tools_output) if tools_output is not None else None
    evidence_items = _coerce_evidence(evidence)
    resolved_date = _coerce_reference_date(reference_date)
    meta: Mapping[str, Any] = {} if metadata is None else metadata

    facts_config = pack.facts_config_mapping()
    if (
        facts_config.get("date", {}).get("relative_requires_reference_date") == "true"
        and resolved_date is None
    ):
        msg = (
            f"the rule pack '{pack.name}' reads dates that are written relative "
            "to some other date, so check() needs reference_date. It is not "
            "read from the clock: the same inputs have to give the same answer "
            "tomorrow."
        )
        raise ValueError(msg)

    findings: list[Finding] = list(missing_metadata_findings(pack, meta))

    if not evidence_items:
        findings.append(
            Finding(
                code="evidence.empty",
                severity=Severity.WARN,
                message=(
                    "No sources were provided, so nothing in this answer could "
                    "be compared against anything."
                ),
            )
        )
    if pack.locale_profile == _UNDECLARED_LOCALE:
        findings.append(
            Finding(
                code="pack.locale.undeclared",
                severity=Severity.WARN,
                message=(
                    f"The rule pack '{pack.name}' does not say which country's "
                    "number and date conventions to read. Amounts and dates may "
                    "be read the wrong way round."
                ),
            )
        )

    facts = extract_facts(
        normalised_answer,
        locale=pack.locale_profile,
        reference_date=resolved_date,
        config=facts_config,
    )
    matches = match_facts(
        facts,
        evidence_items,
        locale=pack.locale_profile,
        config=facts_config,
    )

    findings.extend(
        evaluate_pack(
            pack,
            answer=normalised_answer,
            evidence=evidence_items,
            facts=facts,
            matches=matches,
            metadata=meta,
            reference_date=resolved_date,
            tools_output=normalised_tools,
            registry=registry,
        )
    )

    sorted_findings = tuple(sorted(findings, key=_finding_sort_key))
    decision = (
        Decision.ESCALATE
        if any(finding.severity is Severity.FAIL for finding in sorted_findings)
        else Decision.CLEAR
    )

    # The record is a wire format, so it is built from the typed constructors
    # in audit_record and never from loose dictionaries. build_record owns the
    # hashing, the schema string and every sort rule 5 mandates; this call
    # site's only job is to hand it the right objects. Passing dicts here is
    # what broke canonical_json() and, with it, record_sha256() and the whole
    # audit trail — so a wrong type is now a TypeError at the boundary rather
    # than an AttributeError three layers away at serialisation time.
    audit = build_record(
        answer=normalised_answer,
        evidence=evidence_items,
        ruleset=RulesetRef(
            name=pack.name,
            version=pack.version,
            content_sha256=pack.content_sha256,
        ),
        findings=sorted_findings,
        counts=_counts(facts, matches, pack, sorted_findings),
        locale_profile=pack.locale_profile,
        # Key names only. The values never leave this function.
        metadata_keys=sorted(meta),
        tools_output=normalised_tools,
        reference_date=(None if resolved_date is None else resolved_date.isoformat()),
        predicates=_predicate_entries(pack, registry),
        decision=decision,
        extractor_version=_extractor_version(),
    )

    return Result(decision=decision, findings=sorted_findings, audit=audit)
