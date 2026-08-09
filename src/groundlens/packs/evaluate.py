"""Evaluation of the eight declarative assert kinds.

One function per assert kind, each pure, each returning findings. No assert
kind reads the environment, the clock or anything not handed to it.

The severity a rule carries is the severity every finding that rule produces
carries. A rule is either worth escalating on or it is not, and encoding that
once, in the pack, is what lets a reviewer read the pack and know what will
happen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from groundlens.facts.polarity import canonical_polarity, exceeds_or_inverts
from groundlens.packs import predicates as predicates_module
from groundlens.types import FactKind, Finding, MatchState, Severity

if TYPE_CHECKING:
    import datetime
    from collections.abc import Mapping

    from groundlens.packs.loader import Pack, PackRule
    from groundlens.packs.predicates import PredicateRegistry
    from groundlens.types import Evidence, Fact, Match

__all__ = [
    "evaluate_pack",
    "missing_metadata_findings",
]

# The strength ordering used to live here, as a second definition keyed by raw
# string. It does not any more: it is
# groundlens.facts.polarity.POLARITY_STRENGTH, and every string that reaches a
# comparison goes through canonical_polarity() first. Two orderings meant the
# extractor could emit a value this module could not read, which is exactly how
# the obligation check came to be degrading to UNCHECKABLE in silence.


def _metadata_as_string(key: str, value: object) -> str:
    """Render a metadata value as the canonical string used for comparison.

    Raises:
        ValueError: If the value is a float, or is not a scalar. Floats are
            barred from the decision path; non-scalars have no stable string
            form, so comparing them would not be reproducible.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if value is None:
        return "null"
    if isinstance(value, float):
        msg = (
            f"metadata[{key!r}] is a floating-point number. Pass it as a string "
            "instead. Floating point is not comparable reproducibly and is not "
            "allowed in the decision path."
        )
        raise ValueError(msg)
    msg = (
        f"metadata[{key!r}] is a {type(value).__name__}, which has no stable "
        "string form. Pass a string, an integer, a boolean or None."
    )
    raise ValueError(msg)


def missing_metadata_findings(pack: Pack, metadata: Mapping[str, Any]) -> tuple[Finding, ...]:
    """Return one FAIL finding per required metadata key that is absent.

    This is the fail-closed trigger. It takes no options. There is no flag,
    keyword argument or environment variable anywhere in this package that
    turns it off, because a control that can be turned off by the system it
    controls is not a control.
    """
    findings: list[Finding] = []
    for key in pack.requires_metadata:
        if key not in metadata:
            findings.append(
                Finding(
                    code="pack.metadata.missing",
                    severity=Severity.FAIL,
                    message=(
                        f"The rule pack '{pack.name}' needs the caller to supply "
                        f"'{key}', and it was not supplied. Nothing was checked "
                        "against it, so this answer has to be reviewed by a person."
                    ),
                )
            )
    return tuple(findings)


# ── Fact selection ──────────────────────────────────────────────────────────


def _fact_matches_where(fact: Fact, where: tuple[tuple[str, str], ...]) -> bool:
    if not where:
        return True
    attrs = dict(fact.attrs)
    for key, value in where:
        if key == "kind":
            if fact.kind.value != value:
                return False
        elif key.startswith("attr:"):
            if attrs.get(key[5:]) != value:
                return False
        else:  # pragma: no cover - loader rejects any other key
            return False
    return True


def _select(
    facts: tuple[Fact, ...],
    where: tuple[tuple[str, str], ...],
    kind: FactKind | None = None,
) -> tuple[Fact, ...]:
    selected = tuple(fact for fact in facts if _fact_matches_where(fact, where))
    if kind is not None:
        selected = tuple(fact for fact in selected if fact.kind is kind)
    return selected


def _match_index(matches: tuple[Match, ...]) -> dict[Fact, Match]:
    index: dict[Fact, Match] = {}
    for match in matches:
        index.setdefault(match.fact, match)
    return index


def _uncheckable(fact: Fact, rule: PackRule, severity: Severity, reason: str) -> Finding:
    return Finding(
        code=f"fact.uncheckable.{fact.kind.value}",
        severity=severity,
        message=(f"'{fact.raw}' could not be checked against the evidence. {reason}"),
        fact=fact,
        rule_id=rule.id,
    )


# ── Assert handlers ─────────────────────────────────────────────────────────


def _assert_all_facts_matched(
    rule: PackRule,
    severity: Severity,
    facts: tuple[Fact, ...],
    index: dict[Fact, Match],
) -> list[Finding]:
    findings: list[Finding] = []
    for fact in _select(facts, rule.where):
        match = index.get(fact)
        if match is None:
            findings.append(_uncheckable(fact, rule, severity, "It was never compared."))
            continue
        if match.state is MatchState.MATCHED:
            continue
        if match.state is MatchState.CONTRADICTED:
            findings.append(
                Finding(
                    code=f"fact.contradicted.{fact.kind.value}",
                    severity=severity,
                    message=(
                        f"The answer says '{fact.raw}' but the source says "
                        f"'{match.evidence_value}'."
                    ),
                    fact=fact,
                    match=match,
                    rule_id=rule.id,
                    evidence_id=match.evidence_id,
                    evidence_span=match.evidence_span,
                )
            )
        elif match.state is MatchState.UNCHECKABLE:
            findings.append(
                _uncheckable(fact, rule, severity, "The comparison could not be decided.")
            )
        else:
            findings.append(
                Finding(
                    code=f"fact.unmatched.{fact.kind.value}",
                    severity=severity,
                    message=(
                        f"The answer states '{fact.raw}', which does not appear "
                        "in any of the sources provided."
                    ),
                    fact=fact,
                    match=match,
                    rule_id=rule.id,
                )
            )
    return findings


def _assert_no_contradicted_facts(
    rule: PackRule,
    severity: Severity,
    facts: tuple[Fact, ...],
    index: dict[Fact, Match],
) -> list[Finding]:
    findings: list[Finding] = []
    for fact in _select(facts, rule.where):
        match = index.get(fact)
        if match is None or match.state is not MatchState.CONTRADICTED:
            continue
        findings.append(
            Finding(
                code=f"fact.contradicted.{fact.kind.value}",
                severity=severity,
                message=(
                    f"The answer says '{fact.raw}' but the source says '{match.evidence_value}'."
                ),
                fact=fact,
                match=match,
                rule_id=rule.id,
                evidence_id=match.evidence_id,
                evidence_span=match.evidence_span,
            )
        )
    return findings


def _find_phrase(answer_folded: str, phrase: str) -> int:
    return answer_folded.find(phrase.casefold())


def _assert_absent_lexicon(
    rule: PackRule, severity: Severity, answer_folded: str
) -> list[Finding]:
    findings: list[Finding] = []
    for phrase in rule.lexicon:
        position = _find_phrase(answer_folded, phrase)
        if position >= 0:
            findings.append(
                Finding(
                    code="rule.failed",
                    severity=severity,
                    message=(
                        f"The answer uses the wording '{phrase}' at character "
                        f"{position}, which this rule does not allow. {rule.description}"
                    ),
                    rule_id=rule.id,
                )
            )
    return findings


def _assert_present_lexicon(
    rule: PackRule, severity: Severity, answer_folded: str
) -> list[Finding]:
    for phrase in rule.lexicon:
        if _find_phrase(answer_folded, phrase) >= 0:
            return []
    wanted = ", ".join(f"'{phrase}'" for phrase in rule.lexicon)
    return [
        Finding(
            code="rule.failed",
            severity=severity,
            message=(
                f"The answer contains none of the required wordings ({wanted}). {rule.description}"
            ),
            rule_id=rule.id,
        )
    ]


def _assert_obligation_polarity_consistent(
    rule: PackRule,
    severity: Severity,
    facts: tuple[Fact, ...],
    index: dict[Fact, Match],
) -> list[Finding]:
    findings: list[Finding] = []
    for fact in _select(facts, rule.where, kind=FactKind.OBLIGATION):
        # Fact.normalised, not attrs["polarity"]: the bare attribute drops the
        # ":negative" a negative recommendation carries, and "should" compared
        # against "should not" as if they were the same wording is an inversion
        # reported as agreement.
        stated = canonical_polarity(fact.normalised)
        if stated is None:
            findings.append(
                _uncheckable(
                    fact,
                    rule,
                    severity,
                    "The strength of the wording could not be read.",
                )
            )
            continue
        match = index.get(fact)
        if match is None or match.state is MatchState.UNCHECKABLE:
            findings.append(
                _uncheckable(fact, rule, severity, "The comparison could not be decided.")
            )
            continue
        if match.state is MatchState.UNMATCHED:
            findings.append(
                Finding(
                    code="rule.failed",
                    severity=severity,
                    message=(
                        f"The answer tells the reader '{fact.raw}', and no source says that."
                    ),
                    fact=fact,
                    match=match,
                    rule_id=rule.id,
                )
            )
            continue
        if match.state is MatchState.CONTRADICTED:
            supported = canonical_polarity(match.evidence_value)
            if supported is None:
                findings.append(
                    _uncheckable(
                        fact,
                        rule,
                        severity,
                        "The strength of the wording in the source could not be read.",
                    )
                )
                continue
            if exceeds_or_inverts(stated, supported):
                findings.append(
                    Finding(
                        code=f"fact.contradicted.{fact.kind.value}",
                        severity=severity,
                        message=(
                            f"The answer tells the reader that '{fact.raw}' is "
                            f"{stated.describe()}, but the source says it is "
                            f"{supported.describe()}."
                        ),
                        fact=fact,
                        match=match,
                        rule_id=rule.id,
                        evidence_id=match.evidence_id,
                        evidence_span=match.evidence_span,
                    )
                )
    return findings


def _assert_citations_resolve(
    rule: PackRule,
    severity: Severity,
    facts: tuple[Fact, ...],
    index: dict[Fact, Match],
    evidence_ids: frozenset[str],
) -> list[Finding]:
    findings: list[Finding] = []
    for fact in _select(facts, rule.where, kind=FactKind.CITATION):
        if fact.normalised in evidence_ids:
            continue
        match = index.get(fact)
        if match is None or match.state is MatchState.UNCHECKABLE:
            findings.append(
                _uncheckable(fact, rule, severity, "The reference could not be resolved.")
            )
            continue
        if match.state is MatchState.MATCHED:
            continue
        findings.append(
            Finding(
                code="rule.failed",
                severity=severity,
                message=(
                    f"The answer points at '{fact.raw}', which is not among the sources provided."
                ),
                fact=fact,
                match=match,
                rule_id=rule.id,
            )
        )
    return findings


def _assert_metadata_equals(
    rule: PackRule, severity: Severity, pack: Pack, metadata: Mapping[str, Any]
) -> list[Finding]:
    key = rule.key
    if key is None:  # pragma: no cover - loader requires it
        return []
    if key not in metadata:
        return [
            Finding(
                code="pack.metadata.missing",
                severity=Severity.FAIL,
                message=(
                    f"The rule pack '{pack.name}' needs the caller to supply "
                    f"'{key}', and it was not supplied. {rule.description}"
                ),
                rule_id=rule.id,
            )
        ]
    actual = _metadata_as_string(key, metadata[key])
    if actual == rule.equals:
        return []
    return [
        Finding(
            code="rule.failed",
            severity=severity,
            message=(
                f"The caller reported '{key}' as '{actual}', and this rule "
                f"requires '{rule.equals}'. {rule.description}"
            ),
            rule_id=rule.id,
        )
    ]


def _assert_predicate(
    rule: PackRule,
    severity: Severity,
    registry: PredicateRegistry,
    context: predicates_module.PredicateContext,
) -> list[Finding]:
    name = rule.predicate
    if name is None:  # pragma: no cover - loader requires it
        return []
    func = registry.get(name)
    if func(context):
        return []
    return [
        Finding(
            code="rule.failed",
            severity=severity,
            message=rule.description,
            rule_id=rule.id,
        )
    ]


# ── Entry point ─────────────────────────────────────────────────────────────


def evaluate_pack(
    pack: Pack,
    *,
    answer: str,
    evidence: tuple[Evidence, ...],
    facts: tuple[Fact, ...],
    matches: tuple[Match, ...],
    metadata: Mapping[str, Any],
    reference_date: datetime.date | None = None,
    tools_output: str | None = None,
    registry: PredicateRegistry | None = None,
) -> tuple[Finding, ...]:
    """Evaluate every rule in ``pack`` and return the findings, unsorted.

    Args:
        pack: The loaded pack.
        answer: The NFKC-normalised answer text.
        evidence: The evidence, already normalised and sorted by id.
        facts: Facts extracted from ``answer``.
        matches: Match outcomes for those facts.
        metadata: The caller's metadata. Values are read, never recorded.
        reference_date: Passed through to predicates.
        tools_output: Passed through to predicates.
        registry: Predicate registry. Defaults to the shipped one.

    Returns:
        The findings in rule order. The caller sorts before serialising.

    Raises:
        PredicateError: If a rule names a predicate that is not registered. An
            unresolvable predicate is an error, never a silent pass.
        ValueError: If a metadata value compared by ``metadata_equals`` has no
            reproducible string form.
    """
    active_registry = predicates_module.REGISTRY if registry is None else registry
    answer_folded = answer.casefold()
    index = _match_index(matches)
    evidence_ids = frozenset(item.id for item in evidence)
    context = predicates_module.PredicateContext(
        answer=answer,
        evidence=evidence,
        facts=facts,
        matches=matches,
        metadata=metadata,
        tools_output=tools_output,
        reference_date=reference_date,
        locale_profile=pack.locale_profile,
    )

    findings: list[Finding] = []
    for rule in pack.rules:
        severity = Severity(rule.severity)
        produced: list[Finding]
        if rule.assertion == "all_facts_matched":
            produced = _assert_all_facts_matched(rule, severity, facts, index)
        elif rule.assertion == "no_contradicted_facts":
            produced = _assert_no_contradicted_facts(rule, severity, facts, index)
        elif rule.assertion == "absent_lexicon":
            produced = _assert_absent_lexicon(rule, severity, answer_folded)
        elif rule.assertion == "present_lexicon":
            produced = _assert_present_lexicon(rule, severity, answer_folded)
        elif rule.assertion == "obligation_polarity_consistent":
            produced = _assert_obligation_polarity_consistent(rule, severity, facts, index)
        elif rule.assertion == "citations_resolve":
            produced = _assert_citations_resolve(rule, severity, facts, index, evidence_ids)
        elif rule.assertion == "metadata_equals":
            produced = _assert_metadata_equals(rule, severity, pack, metadata)
        elif rule.assertion == "predicate":
            produced = _assert_predicate(rule, severity, active_registry, context)
        else:  # pragma: no cover - loader rejects any other value
            msg = f"rule {rule.id!r}: unsupported assert {rule.assertion!r}"
            raise ValueError(msg)

        if produced:
            findings.extend(produced)
        elif rule.emit_on_pass:
            findings.append(
                Finding(
                    code="rule.passed",
                    severity=Severity.INFO,
                    message=rule.description,
                    rule_id=rule.id,
                )
            )
    return tuple(findings)
