"""Canary suites: fixed cases with known verdicts, run against :func:`check`.

A canary suite is a directory of YAML cases. Each case is an answer, its
evidence, and the outcome a competent reviewer would give it. Running the
suite tells you two things the unit tests cannot:

* whether the checker catches the defect it is supposed to catch, and
* **how often it escalates an answer that has nothing wrong with it.**

The second number is the one that decides whether anyone deploys this. A
checker that escalates everything has perfect recall and no value, and no
amount of unit-test coverage will show you that.

Suites are split in two:

``dev/``
    Visible while rules are being written. Gated in CI: one failure fails
    the build.
``frozen/``
    Authored from the defect-class definitions alone, before the rule
    bodies were read, and evaluated at release only. It is reported and
    never gated, because a gate on it would create pressure to tune the
    rules against it, which is the one thing it exists to prevent.

This module loads and runs. It does not compute rates; that is
:mod:`groundlens.metrics`, so that a change to the reporting cannot
quietly change what was measured.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from groundlens.control import check
from groundlens.determinism import normalise_text
from groundlens.facts import extract_facts
from groundlens.packs.loader import load_pack
from groundlens.types import Decision, FactKind, Severity

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__ = [
    "DEFECT_CLASSES",
    "DEFECT_CLASS_FACT_KINDS",
    "SURFACE_FORM_DISTANCES",
    "CanaryCase",
    "CanaryError",
    "CanaryOutcome",
    "CanaryReport",
    "load_suite",
    "run_case",
    "run_suite",
]


class CanaryError(Exception):
    """A canary file is malformed, or a suite directory does not exist.

    Raised rather than skipped. A canary that silently fails to load is a
    canary that stops warning you, which is worse than not having one.
    """


# ── The vocabulary ──────────────────────────────────────────────────────────

#: Every defect a case may carry. ``clean`` is not a defect: it is the
#: control group, and it is the reason the suite exists.
DEFECT_CLASSES: tuple[str, ...] = (
    "clean",
    "wrong_number",
    "wrong_currency",
    "shifted_deadline",
    "polarity_flip",
    "fabricated_citation",
    "missing_disclosure",
    "decision_language_where_recommendation_required",
)

#: How far the answer's wording sits from the evidence's wording.
#: Contract section 8 stratifies by this and forbids stratifying by
#: register alignment.
SURFACE_FORM_DISTANCES: tuple[str, ...] = (
    "identical",
    "reformatted",
    "paraphrased",
    "restructured",
)

#: Which fact kind the extractor must have found for a defect of this class
#: to be *catchable* at all. A class mapped to ``()`` is not fact-bearing:
#: it is a structural or lexical defect, and extraction recall does not
#: apply to it. Keeping this separate from rule outcomes is what lets a
#: miss be attributed to the extractor rather than to the rule.
DEFECT_CLASS_FACT_KINDS: Mapping[str, tuple[FactKind, ...]] = {
    "clean": (),
    "wrong_number": (FactKind.NUMBER, FactKind.PERCENT),
    "wrong_currency": (FactKind.CURRENCY,),
    "shifted_deadline": (FactKind.DEADLINE, FactKind.DATE, FactKind.DURATION),
    "polarity_flip": (FactKind.OBLIGATION,),
    "fabricated_citation": (FactKind.CITATION,),
    "missing_disclosure": (),
    "decision_language_where_recommendation_required": (),
}

_CASE_KEYS = frozenset(
    {
        "id",
        "defect_class",
        "surface_form_distance",
        "answer",
        "evidence",
        "metadata",
        "reference_date",
        "expect",
        "note",
    }
)
_EXPECT_KEYS = frozenset({"decision", "must_include_codes", "extraction_kinds"})
_REQUIRED_KEYS = ("id", "defect_class", "surface_form_distance", "answer", "expect")


# ── Values ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CanaryCase:
    """One canary: an answer, its evidence, and the verdict it should get."""

    id: str
    defect_class: str
    surface_form_distance: str
    answer: str
    evidence: tuple[tuple[str, str], ...]
    metadata: tuple[tuple[str, str], ...]
    reference_date: str | None
    expect_decision: Decision
    expect_codes: tuple[str, ...]
    extraction_kinds: tuple[FactKind, ...]
    source: str
    note: str = ""

    def evidence_mappings(self) -> list[dict[str, str]]:
        """The evidence in the shape :func:`groundlens.check` accepts."""
        return [{"id": item_id, "text": text} for item_id, text in self.evidence]

    def metadata_mapping(self) -> dict[str, str]:
        """The metadata in the shape :func:`groundlens.check` accepts."""
        return dict(self.metadata)


@dataclass(frozen=True, slots=True)
class CanaryOutcome:
    """What actually happened when one case was run."""

    case: CanaryCase
    decision: Decision
    codes: tuple[str, ...]
    fail_codes: tuple[str, ...]
    warn_codes: tuple[str, ...]
    extracted_kinds: tuple[FactKind, ...]
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """True when the case got the decision and the codes it expected."""
        return not self.failures

    @property
    def decision_correct(self) -> bool:
        """True when the decision matched, whatever the codes did."""
        return self.decision is self.case.expect_decision

    @property
    def extraction_applies(self) -> bool:
        """True when this case's defect is fact-bearing at all."""
        return bool(self.case.extraction_kinds)

    @property
    def extraction_succeeded(self) -> bool:
        """True when the extractor found a fact of the kind the defect is in.

        False for cases where extraction does not apply, so callers must
        check :attr:`extraction_applies` before counting this.
        """
        return bool(set(self.case.extraction_kinds) & set(self.extracted_kinds))


@dataclass(frozen=True, slots=True)
class CanaryReport:
    """The outcome of every case in one suite of one pack."""

    pack: str
    suite: str
    directory: str
    outcomes: tuple[CanaryOutcome, ...]

    @property
    def failed(self) -> tuple[CanaryOutcome, ...]:
        """Every outcome that did not match its expectation."""
        return tuple(outcome for outcome in self.outcomes if not outcome.passed)


# ── Loading ─────────────────────────────────────────────────────────────────


def _require_str(value: object, where: str) -> str:
    if not isinstance(value, str):
        msg = f"{where} must be a string, got {type(value).__name__}."
        raise CanaryError(msg)
    return value


def _parse_evidence(raw: object, where: str) -> tuple[tuple[str, str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        msg = f"{where}: 'evidence' must be a list of {{id, text}} mappings."
        raise CanaryError(msg)
    out: list[tuple[str, str]] = []
    for position, item in enumerate(raw):
        if not isinstance(item, dict) or set(item) != {"id", "text"}:
            msg = f"{where}: evidence[{position}] must have exactly 'id' and 'text'."
            raise CanaryError(msg)
        out.append(
            (
                _require_str(item["id"], f"{where}: evidence[{position}]['id']"),
                _require_str(item["text"], f"{where}: evidence[{position}]['text']"),
            )
        )
    return tuple(out)


def _parse_metadata(raw: object, where: str) -> tuple[tuple[str, str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        msg = f"{where}: 'metadata' must be a mapping of string to string."
        raise CanaryError(msg)
    items: list[tuple[str, str]] = []
    for key, value in raw.items():
        key_text = _require_str(key, f"{where}: metadata key")
        items.append((key_text, _require_str(value, f"{where}: metadata[{key_text!r}]")))
    return tuple(sorted(items))


def _parse_expect(
    raw: object, defect_class: str, where: str
) -> tuple[Decision, tuple[str, ...], tuple[FactKind, ...]]:
    if not isinstance(raw, dict):
        msg = f"{where}: 'expect' must be a mapping."
        raise CanaryError(msg)
    unknown = sorted(set(raw) - _EXPECT_KEYS)
    if unknown:
        msg = f"{where}: unknown key(s) under 'expect': {', '.join(unknown)}."
        raise CanaryError(msg)

    decision_text = _require_str(raw.get("decision"), f"{where}: expect.decision")
    try:
        decision = Decision(decision_text)
    except ValueError as exc:
        msg = (
            f"{where}: expect.decision is {decision_text!r}, but the only "
            "decisions are 'clear' and 'escalate'."
        )
        raise CanaryError(msg) from exc

    codes_raw = raw.get("must_include_codes") or []
    if not isinstance(codes_raw, list):
        msg = f"{where}: expect.must_include_codes must be a list of codes."
        raise CanaryError(msg)
    codes = tuple(
        _require_str(code, f"{where}: expect.must_include_codes[{i}]")
        for i, code in enumerate(codes_raw)
    )

    kinds_raw = raw.get("extraction_kinds")
    if kinds_raw is None:
        kinds = DEFECT_CLASS_FACT_KINDS[defect_class]
    else:
        if not isinstance(kinds_raw, list):
            msg = f"{where}: expect.extraction_kinds must be a list of fact kinds."
            raise CanaryError(msg)
        try:
            kinds = tuple(
                FactKind(_require_str(kind, f"{where}: expect.extraction_kinds[{i}]"))
                for i, kind in enumerate(kinds_raw)
            )
        except ValueError as exc:
            msg = f"{where}: expect.extraction_kinds names a fact kind that does not exist."
            raise CanaryError(msg) from exc

    return decision, codes, kinds


def _parse_case(raw: object, source: str) -> CanaryCase:
    if not isinstance(raw, dict):
        msg = f"{source}: a canary case must be a mapping, got {type(raw).__name__}."
        raise CanaryError(msg)

    unknown = sorted(set(raw) - _CASE_KEYS)
    if unknown:
        msg = f"{source}: unknown key(s): {', '.join(unknown)}."
        raise CanaryError(msg)
    missing = [key for key in _REQUIRED_KEYS if key not in raw]
    if missing:
        msg = f"{source}: missing required key(s): {', '.join(missing)}."
        raise CanaryError(msg)

    case_id = _require_str(raw["id"], f"{source}: 'id'")
    where = f"{source}[{case_id}]"

    defect_class = _require_str(raw["defect_class"], f"{where}: 'defect_class'")
    if defect_class not in DEFECT_CLASSES:
        msg = f"{where}: defect_class {defect_class!r} is not one of {', '.join(DEFECT_CLASSES)}."
        raise CanaryError(msg)

    distance = _require_str(raw["surface_form_distance"], f"{where}: 'surface_form_distance'")
    if distance not in SURFACE_FORM_DISTANCES:
        msg = (
            f"{where}: surface_form_distance {distance!r} is not one of "
            f"{', '.join(SURFACE_FORM_DISTANCES)}."
        )
        raise CanaryError(msg)

    reference_date = raw.get("reference_date")
    if reference_date is not None:
        reference_date = str(reference_date)

    decision, codes, kinds = _parse_expect(raw["expect"], defect_class, where)

    if defect_class == "clean" and decision is not Decision.CLEAR:
        msg = (
            f"{where}: a case in the 'clean' class expects "
            f"{decision.value!r}. A clean answer that is supposed to escalate "
            "is not clean, and counting it as clean traffic would flatter the "
            "false-alarm rate."
        )
        raise CanaryError(msg)

    return CanaryCase(
        id=case_id,
        defect_class=defect_class,
        surface_form_distance=distance,
        answer=_require_str(raw["answer"], f"{where}: 'answer'"),
        evidence=_parse_evidence(raw.get("evidence"), where),
        metadata=_parse_metadata(raw.get("metadata"), where),
        reference_date=reference_date,
        expect_decision=decision,
        expect_codes=codes,
        extraction_kinds=kinds,
        source=source,
        note=str(raw.get("note", "")),
    )


def _documents(path: Path) -> list[Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - unreadable file
        msg = f"{path}: cannot be read: {exc}"
        raise CanaryError(msg) from exc
    try:
        loaded = list(yaml.safe_load_all(text))
    except yaml.YAMLError as exc:
        msg = f"{path}: is not valid YAML: {exc}"
        raise CanaryError(msg) from exc
    return [document for document in loaded if document is not None]


def load_suite(directory: str | Path) -> tuple[CanaryCase, ...]:
    """Load every case in a suite directory, sorted by case id.

    A file may hold one case, a list of cases, or several YAML documents.
    Ids must be unique across the whole suite: two cases with the same id
    would collapse into one row in the metrics table.

    Args:
        directory: A ``canaries/dev`` or ``canaries/frozen`` directory.

    Returns:
        Every case in the directory, sorted by id.

    Raises:
        CanaryError: If the directory is missing, a file is malformed, or
            two cases share an id.
    """
    root = Path(directory)
    if not root.is_dir():
        msg = f"{root}: is not a canary suite directory."
        raise CanaryError(msg)

    cases: list[CanaryCase] = []
    for path in sorted(root.rglob("*.yaml")) + sorted(root.rglob("*.yml")):
        for position, document in enumerate(_documents(path)):
            source = f"{path.name}#{position}"
            if isinstance(document, list):
                for item in document:
                    cases.append(_parse_case(item, source))
            else:
                cases.append(_parse_case(document, source))

    seen: dict[str, str] = {}
    for case in cases:
        if case.id in seen:
            msg = (
                f"canary id {case.id!r} is used twice, in {seen[case.id]} and "
                f"in {case.source}. Ids have to be unique."
            )
            raise CanaryError(msg)
        seen[case.id] = case.source

    return tuple(sorted(cases, key=lambda case: case.id))


# ── Running ─────────────────────────────────────────────────────────────────


def run_case(case: CanaryCase, ruleset: str | Path) -> CanaryOutcome:
    """Run one case through :func:`groundlens.check` and score it.

    Extraction is run a second time, directly, so that a miss can be
    attributed: either the extractor never saw the fact, or it saw it and
    no rule acted on it. Those are different bugs with different fixes.
    """
    pack = load_pack(ruleset)
    result = check(
        case.answer,
        case.evidence_mappings(),
        ruleset=pack,
        metadata=case.metadata_mapping(),
        reference_date=case.reference_date,
    )

    codes = tuple(finding.code for finding in result.findings)
    fail_codes = tuple(
        finding.code for finding in result.findings if finding.severity is Severity.FAIL
    )
    warn_codes = tuple(
        finding.code for finding in result.findings if finding.severity is Severity.WARN
    )

    facts = extract_facts(
        normalise_text(case.answer),
        locale=pack.locale_profile,
        reference_date=(
            None
            if case.reference_date is None
            else datetime.date.fromisoformat(case.reference_date)
        ),
        config=pack.facts_config_mapping(),
    )
    extracted_kinds = tuple(sorted({fact.kind for fact in facts}, key=lambda kind: kind.value))

    failures: list[str] = []
    if result.decision is not case.expect_decision:
        failures.append(
            f"expected decision {case.expect_decision.value}, got {result.decision.value}"
        )
    for expected in case.expect_codes:
        if expected not in codes:
            failures.append(f"expected finding code {expected!r}, which was not emitted")

    return CanaryOutcome(
        case=case,
        decision=result.decision,
        codes=codes,
        fail_codes=fail_codes,
        warn_codes=warn_codes,
        extracted_kinds=extracted_kinds,
        failures=tuple(failures),
    )


def run_suite(
    pack_dir: str | Path,
    suite: str = "dev",
    *,
    cases: Sequence[CanaryCase] | None = None,
) -> CanaryReport:
    """Run one suite of one pack.

    Args:
        pack_dir: A ``packs/<name>`` directory holding ``pack.yaml`` and
            ``canaries/``.
        suite: ``"dev"`` or ``"frozen"``.
        cases: Pre-loaded cases, for callers that already loaded them.

    Returns:
        A report holding one outcome per case, in case-id order.

    Raises:
        CanaryError: If the pack or the suite directory is missing.
    """
    root = Path(pack_dir)
    pack_file = root / "pack.yaml"
    if not pack_file.is_file():
        msg = f"{root}: has no pack.yaml, so there is nothing to run the canaries against."
        raise CanaryError(msg)

    suite_dir = root / "canaries" / suite
    loaded = load_suite(suite_dir) if cases is None else tuple(cases)
    pack = load_pack(pack_file)

    return CanaryReport(
        pack=pack.name,
        suite=suite,
        directory=str(suite_dir),
        outcomes=tuple(run_case(case, pack_file) for case in loaded),
    )


def discover_packs(packs_dir: str | Path, suite: str = "dev") -> tuple[Path, ...]:
    """Every pack directory under ``packs_dir`` that has this suite."""
    root = Path(packs_dir)
    if not root.is_dir():
        msg = f"{root}: is not a directory of rule packs."
        raise CanaryError(msg)
    return tuple(
        sorted(
            child
            for child in root.iterdir()
            if (child / "pack.yaml").is_file() and (child / "canaries" / suite).is_dir()
        )
    )


def run_all(packs_dir: str | Path, suite: str = "dev") -> tuple[CanaryReport, ...]:
    """Run one suite across every pack that has one."""
    return tuple(run_suite(pack, suite) for pack in discover_packs(packs_dir, suite))


def iter_outcomes(reports: Iterable[CanaryReport]) -> tuple[CanaryOutcome, ...]:
    """Flatten several reports into one tuple of outcomes."""
    return tuple(outcome for report in reports for outcome in report.outcomes)
