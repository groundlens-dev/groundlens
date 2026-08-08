"""The v2 audit record: what makes a decision reproducible by a third party.

An audit record is the complete, minimal description of a
:func:`groundlens.check` run. Give a second party the same answer, the
same evidence and the same rule pack, and rebuilding the record must
produce the same bytes, on any host, in any locale, under any Python in
the supported range. That property is the product; everything in this
module exists to protect it.

Canonical serialisation is one line, fixed by the contract::

    json.dumps(obj, sort_keys=True, separators=(",", ":"),
               ensure_ascii=False).encode("utf-8")

Two things the record deliberately does not contain:

* **No metadata values.** Only :attr:`AuditRecord.metadata_keys`, sorted.
  Metadata routinely carries customer identifiers and other personal
  data, and an audit log is exactly the wrong place for it. The key
  names are enough to prove the fail-closed check on
  ``requires_metadata`` was performed.
* **No timestamp.** The wall clock is not part of the decision (rule 4).
  The time of writing belongs to the :class:`groundlens.audit.AuditLog`
  row that carries the record, where it is hash-chained but does not
  perturb the record's own hash. Two identical runs a month apart
  produce identical records, which is what makes a golden fixture
  possible at all.

Typical usage::

    from groundlens.audit_record import build_record, canonical_json

    record = build_record(
        answer=answer_text,
        evidence=evidence_units,
        ruleset=RulesetRef("eu-retail-banking", "1.2.0", pack_hash),
        findings=findings,
        counts=counts,
        locale_profile="eu-es",
        metadata={"product_type": "mortgage", "disclosure_set": "es-2026"},
        reference_date="2026-08-08",
    )
    blob = canonical_json(record)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from groundlens.determinism import UNICODE_FORM, normalise_text, sort_findings
from groundlens.types import Decision, Severity

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from groundlens.types import Evidence, Finding

__all__ = [
    "EXTRACTOR_VERSION",
    "LIBRARY_VERSION",
    "SCHEMA",
    "AuditRecord",
    "Counts",
    "DeterminismBlock",
    "EvidenceDigest",
    "FindingRecord",
    "PredicateRef",
    "RulesetRef",
    "build_record",
    "canonical_json",
    "record_sha256",
    "sha256_text",
    "to_jsonable",
]


SCHEMA: Final[str] = "groundlens.audit/2"
"""The record schema identifier. Bump only with a migration."""

LIBRARY_VERSION: Final[str] = "2.0.0"
"""The library version written into the record.

Deliberately a literal rather than a read of
``groundlens._version.__version__``: the record's version string is part
of a frozen wire format and of the golden fixture, and it must not
change because an unrelated release bumped the distribution metadata.
Callers that want the running version in the record pass it explicitly
to :func:`build_record`.
"""

EXTRACTOR_VERSION: Final[str] = "1"
"""The extractor generation. Bump when extraction output changes at all."""


# ── Record components ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EvidenceDigest:
    """One evidence unit, reduced to its identifier and a hash.

    The record never stores evidence text: it may be long, and it may be
    confidential. The hash is enough to prove which text was used.

    Attributes:
        id: The caller-supplied evidence identifier.
        sha256: Hex digest of the normalised evidence text.
    """

    id: str
    sha256: str


@dataclass(frozen=True, slots=True)
class RulesetRef:
    """The rule pack a run was checked against.

    Attributes:
        name: The pack name, e.g. ``"eu-retail-banking"``.
        version: The pack's declared version, e.g. ``"1.2.0"``.
        content_sha256: Hex digest of the pack file's raw bytes. The
            label alone is not evidence; the hash is.
    """

    name: str
    version: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class PredicateRef:
    """A named predicate a pack invoked, with the source it ran.

    Attributes:
        name: The registry entry name, e.g. ``"banking.disclosure_present"``.
        source_sha256: Hex digest of that entry's source.
    """

    name: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class DeterminismBlock:
    """The three settings that decide how text and numbers were read.

    Attributes:
        locale_profile: The profile name the pack declared, e.g.
            ``"eu-es"``. Never taken from the environment.
        reference_date: The ISO date relative expressions resolved
            against, or ``None`` when the run needed none. Supplied by
            the caller; never a wall-clock read.
        unicode_form: Always ``"NFKC"``. Recorded so a future change is
            visible in old records rather than silent.
    """

    locale_profile: str
    reference_date: str | None = None
    unicode_form: str = UNICODE_FORM


@dataclass(frozen=True, slots=True)
class Counts:
    """Integer tallies for the run. Integers only, by rule 1.

    Attributes:
        facts_extracted: Facts the extractors produced.
        facts_matched: Facts grounded in the evidence.
        facts_unmatched: Facts not found in the evidence.
        facts_contradicted: Facts found with a different value.
        rules_evaluated: Pack rules that ran.
        rules_failed: Pack rules that failed.
    """

    facts_extracted: int = 0
    facts_matched: int = 0
    facts_unmatched: int = 0
    facts_contradicted: int = 0
    rules_evaluated: int = 0
    rules_failed: int = 0


@dataclass(frozen=True, slots=True)
class FindingRecord:
    """The projection of a :class:`groundlens.types.Finding` into the record.

    The message is not recorded: it is presentation, it may be
    translated, and it would make the record's bytes depend on wording
    changes. The code, the span and the rule id are the durable facts.

    Attributes:
        code: The stable finding code.
        severity: The finding's severity.
        span: The fact's half-open offsets into the normalised answer,
            or ``None`` when the finding has no fact.
        rule_id: The pack rule that fired, when there was one.
        evidence_id: The evidence unit involved, when there was one.
    """

    code: str
    severity: Severity
    span: tuple[int, int] | None = None
    rule_id: str | None = None
    evidence_id: str | None = None


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """The complete, reproducible description of one check.

    Every collection field is already in canonical order when the record
    is built by :func:`build_record`; the record itself does no sorting,
    so that constructing one by hand from a stored JSON blob round-trips
    exactly.

    Attributes:
        answer_sha256: Hex digest of the normalised answer text.
        evidence: Evidence digests, sorted by ``id``.
        metadata_keys: Metadata key names only, sorted. Never values.
        ruleset: The pack that was applied.
        determinism: How text, numbers and dates were read.
        counts: Integer tallies.
        decision: Clear or escalate.
        findings: Finding projections in canonical order.
        tools_output_sha256: Hex digest of any tool output that fed the
            answer, or ``None``.
        predicates: Predicate registry entries the pack invoked, sorted
            by name.
        schema: The record schema identifier.
        library_version: The library version that produced the record.
        extractor_version: The extractor generation that produced it.
    """

    answer_sha256: str
    evidence: tuple[EvidenceDigest, ...]
    metadata_keys: tuple[str, ...]
    ruleset: RulesetRef
    determinism: DeterminismBlock
    counts: Counts
    decision: Decision
    findings: tuple[FindingRecord, ...]
    tools_output_sha256: str | None = None
    predicates: tuple[PredicateRef, ...] = ()
    schema: str = SCHEMA
    library_version: str = LIBRARY_VERSION
    extractor_version: str = EXTRACTOR_VERSION


# ── Hashing ─────────────────────────────────────────────────────────────────


def sha256_text(s: str) -> str:
    """Hash text the one way the whole codebase hashes text.

    The input is passed through
    :func:`groundlens.determinism.normalise_text` first, so the digest
    identifies the text the spans were computed against rather than
    whichever encoding, line ending or trailing-space convention the
    caller's pipeline happened to produce. The same paragraph delivered
    as CRLF from one system and LF from another hashes identically,
    which is the whole point.

    Args:
        s: The text to hash.

    Returns:
        Lowercase hex SHA-256 digest of the UTF-8 encoding of the
        normalised text.
    """
    return hashlib.sha256(normalise_text(s).encode("utf-8")).hexdigest()


def canonical_json(record: AuditRecord) -> bytes:
    """Serialise a record to its one canonical byte string.

    Args:
        record: The record to serialise.

    Returns:
        UTF-8 bytes. Byte-identical for equal records on every supported
        Python and operating system; ``tests/determinism`` proves it and
        the ``Determinism`` CI job proves it across the matrix.
    """
    return json.dumps(
        to_jsonable(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def record_sha256(record: AuditRecord) -> str:
    """Return the SHA-256 hex digest of a record's canonical JSON.

    Args:
        record: The record to digest.

    Returns:
        Lowercase hex digest. This is the value an examiner recomputes
        to show that a stored record was not edited.
    """
    return hashlib.sha256(canonical_json(record)).hexdigest()


# ── Serialisation ───────────────────────────────────────────────────────────


def to_jsonable(record: AuditRecord) -> dict[str, Any]:
    """Convert a record to plain JSON types.

    Enums become their string values, tuples become lists, and spans
    become two-element integer lists. No value in the returned structure
    is ever a float.

    Args:
        record: The record to convert.

    Returns:
        A dictionary of JSON-native values.
    """
    return {
        "schema": record.schema,
        "library_version": record.library_version,
        "extractor_version": record.extractor_version,
        "answer_sha256": record.answer_sha256,
        "evidence": [{"id": e.id, "sha256": e.sha256} for e in record.evidence],
        "tools_output_sha256": record.tools_output_sha256,
        "metadata_keys": list(record.metadata_keys),
        "ruleset": {
            "name": record.ruleset.name,
            "version": record.ruleset.version,
            "content_sha256": record.ruleset.content_sha256,
        },
        "predicates": [
            {"name": p.name, "source_sha256": p.source_sha256} for p in record.predicates
        ],
        "determinism": {
            "unicode_form": record.determinism.unicode_form,
            "locale_profile": record.determinism.locale_profile,
            "reference_date": record.determinism.reference_date,
        },
        "counts": {
            "facts_extracted": record.counts.facts_extracted,
            "facts_matched": record.counts.facts_matched,
            "facts_unmatched": record.counts.facts_unmatched,
            "facts_contradicted": record.counts.facts_contradicted,
            "rules_evaluated": record.counts.rules_evaluated,
            "rules_failed": record.counts.rules_failed,
        },
        "decision": record.decision.value,
        "findings": [
            {
                "code": f.code,
                "severity": f.severity.value,
                "span": None if f.span is None else [f.span[0], f.span[1]],
                "rule_id": f.rule_id,
                "evidence_id": f.evidence_id,
            }
            for f in record.findings
        ],
    }


# ── Construction ────────────────────────────────────────────────────────────


def build_record(
    *,
    answer: str,
    evidence: Sequence[Evidence],
    ruleset: RulesetRef,
    findings: Iterable[Finding],
    counts: Counts,
    locale_profile: str,
    metadata: Mapping[str, object] | None = None,
    metadata_keys: Iterable[str] = (),
    tools_output: str | None = None,
    reference_date: str | None = None,
    predicates: Iterable[PredicateRef] = (),
    decision: Decision | None = None,
    library_version: str = LIBRARY_VERSION,
    extractor_version: str = EXTRACTOR_VERSION,
) -> AuditRecord:
    """Build a canonical audit record, doing every sort the contract mandates.

    This is the only supported way to construct an
    :class:`AuditRecord` from live objects. It applies rule 5 at the one
    serialisation boundary that matters: evidence is sorted by ``id``,
    metadata keys are sorted and de-duplicated, predicates are sorted by
    name, and findings go through
    :func:`groundlens.determinism.sort_findings`. Callers may therefore
    pass sets, unordered dicts or lists in retrieval order and still get
    the same bytes out.

    Args:
        answer: The answer text, raw. Normalised and hashed here.
        evidence: The evidence units, in any order.
        ruleset: The pack reference, already content-hashed by the loader.
        findings: The findings, in any order.
        counts: Integer tallies for the run.
        locale_profile: The profile name the pack declared.
        metadata: The metadata mapping passed to ``check()``. Only its
            key names are read; values are never touched and never
            recorded.
        metadata_keys: Extra key names to record, for callers that know
            the keys without holding the values.
        tools_output: Tool output that fed the answer, hashed if given.
        reference_date: The ISO date relative expressions resolved
            against. Passed by the caller; never read from the clock.
        predicates: Predicate registry entries the pack invoked.
        decision: Overrides the derived decision. When omitted, the
            decision is ``ESCALATE`` if any finding has severity
            ``FAIL`` and ``CLEAR`` otherwise, which is the fail-closed
            default.
        library_version: Version string to record.
        extractor_version: Extractor generation to record.

    Returns:
        A fully sorted :class:`AuditRecord`.
    """
    ordered_findings = sort_findings(findings)

    digests = tuple(
        sorted(
            (EvidenceDigest(id=unit.id, sha256=sha256_text(unit.text)) for unit in evidence),
            key=lambda d: d.id,
        )
    )

    keys = set(metadata_keys)
    if metadata is not None:
        keys.update(metadata.keys())

    resolved = decision
    if resolved is None:
        resolved = (
            Decision.ESCALATE
            if any(f.severity is Severity.FAIL for f in ordered_findings)
            else Decision.CLEAR
        )

    return AuditRecord(
        answer_sha256=sha256_text(answer),
        evidence=digests,
        metadata_keys=tuple(sorted(keys)),
        ruleset=ruleset,
        determinism=DeterminismBlock(
            locale_profile=locale_profile,
            reference_date=reference_date,
        ),
        counts=counts,
        decision=resolved,
        findings=tuple(
            FindingRecord(
                code=f.code,
                severity=f.severity,
                span=(f.fact.span if f.fact is not None else None),
                rule_id=f.rule_id,
                evidence_id=f.evidence_id,
            )
            for f in ordered_findings
        ),
        tools_output_sha256=(None if tools_output is None else sha256_text(tools_output)),
        predicates=tuple(sorted(predicates, key=lambda p: (p.name, p.source_sha256))),
        library_version=library_version,
        extractor_version=extractor_version,
    )
