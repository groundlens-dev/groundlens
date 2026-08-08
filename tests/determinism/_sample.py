"""The one sample run every determinism test is built from.

Kept in a private module rather than a fixture so that the golden
exporter (``export_golden.py``, run by the ``Determinism`` CI job on
every cell of the matrix) can import it without pytest.

The sample answer is chosen to be hostile on purpose. It contains
full-width digits, a Latin ligature, a non-breaking space, a soft
hyphen, a zero-width space, CRLF line endings and trailing whitespace,
so the golden fixture is a regression test on ``normalise_text`` and on
the host's Unicode tables as much as on the record layout. Every
character used was assigned well before Unicode 13, so its NFKC mapping
is frozen by the Unicode normalisation stability policy and the fixture
is comparable across Python 3.10 (Unicode 13) and Python 3.14
(Unicode 16).
"""

from __future__ import annotations

from groundlens.audit_record import (
    AuditRecord,
    Counts,
    PredicateRef,
    RulesetRef,
    build_record,
)
from groundlens.determinism import normalise_text, sort_findings
from groundlens.types import (
    Decision,
    Evidence,
    Fact,
    FactKind,
    Finding,
    Match,
    MatchState,
    Result,
    Severity,
)

# Raw, as it would arrive from a model: full-width digits, a ligature,
# NBSP as a thousands separator, a soft hyphen inside a word, a
# zero-width space, CRLF, and trailing spaces.
SAMPLE_ANSWER = (
    # \ufb01 LATIN SMALL LIGATURE FI, \u00a0 NO-BREAK SPACE
    "El importe \ufb01nanciado es de 1\u00a0234,56 EUR.\r\n"
    # \u00ad SOFT HYPHEN, \uff11\uff12 FULLWIDTH DIGIT ONE and TWO
    "El plazo de amor\u00adtizaci\u00f3n es de \uff11\uff12 meses.\r\n"
    # \u200b ZERO WIDTH SPACE, and trailing spaces before the line ending
    "La comisi\u00f3n de apertura es del 0,50\u200b %.   \r\n"
)

SAMPLE_EVIDENCE = (
    Evidence(id="doc-2#p1", text="El plazo de amortizacion es de 12 meses."),
    Evidence(id="doc-1#p3", text="Importe financiado: 1.234,56 EUR."),
    Evidence(id="doc-10#p1", text="Sin comision de apertura."),
)
"""Deliberately not sorted by id, and with a lexicographic trap:
``doc-10`` sorts before ``doc-2`` as a string, which is the ordering the
contract specifies and the one the record must show."""

SAMPLE_METADATA = {
    "product_type": "mortgage",
    "disclosure_set": "es-2026-q3",
    "operator_id": "compliance_officer_42",
}
"""Values here must never reach the record. Only the key names do."""

SAMPLE_RULESET = RulesetRef(
    name="eu-retail-banking",
    version="1.2.0",
    content_sha256="3b1f8c7d2e4a5b69c0d1e2f3a4b5c6d7e8f90112233445566778899aabbccddee",
)

SAMPLE_PREDICATES = (
    PredicateRef(
        name="banking.disclosure_present",
        source_sha256="aa11bb22cc33dd44ee55ff6677889900112233445566778899aabbccddeeff00",
    ),
    PredicateRef(
        name="banking.apr_stated",
        source_sha256="bb22cc33dd44ee55ff6677889900112233445566778899aabbccddeeff0011aa",
    ),
)

SAMPLE_COUNTS = Counts(
    facts_extracted=3,
    facts_matched=1,
    facts_unmatched=1,
    facts_contradicted=1,
    rules_evaluated=12,
    rules_failed=2,
)

SAMPLE_LOCALE_PROFILE = "eu-es"
SAMPLE_REFERENCE_DATE = "2026-08-08"


def _span(needle: str) -> tuple[int, int]:
    """Return the half-open span of ``needle`` in the normalised answer.

    Spans are offsets into the normalised text, never into the raw
    input. Computing them here rather than hard-coding them means the
    golden fixture also pins ``normalise_text``.
    """
    text = normalise_text(SAMPLE_ANSWER)
    start = text.index(needle)
    return (start, start + len(needle))


def sample_facts() -> tuple[Fact, ...]:
    """Return the three facts the extractor would produce, in extraction order."""
    return (
        Fact(
            kind=FactKind.CURRENCY,
            raw="1 234,56 EUR",
            span=_span("1 234,56 EUR"),
            normalised="1234.56",
            attrs=(("currency", "EUR"), ("source", "answer")),
        ),
        Fact(
            kind=FactKind.DURATION,
            raw="12 meses",
            span=_span("12 meses"),
            normalised="P12M",
            attrs=(("granularity", "month"),),
        ),
        Fact(
            kind=FactKind.PERCENT,
            raw="0,50 %",
            span=_span("0,50 %"),
            normalised="0.5",
            attrs=(),
        ),
    )


def sample_findings() -> list[Finding]:
    """Return the findings in a deliberately non-canonical order.

    Reverse-sorted by code, so any test that forgets to sort sees it.
    """
    amount, duration, percent = sample_facts()
    return [
        Finding(
            code="rule.failed",
            severity=Severity.FAIL,
            message="A rule in the pack did not pass.",
            rule_id="BNK-031",
        ),
        Finding(
            code="fact.unmatched.percent",
            severity=Severity.FAIL,
            message="The opening fee stated in the answer does not appear in the sources.",
            fact=percent,
            match=Match(fact=percent, state=MatchState.UNMATCHED),
            rule_id="BNK-001",
        ),
        Finding(
            code="fact.contradicted.currency",
            severity=Severity.FAIL,
            message="The amount in the answer differs from the amount in the sources.",
            fact=amount,
            match=Match(
                fact=amount,
                state=MatchState.CONTRADICTED,
                evidence_id="doc-1#p3",
                evidence_span=(20, 28),
                evidence_value="1234.56",
            ),
            rule_id="BNK-001",
            evidence_id="doc-1#p3",
        ),
        Finding(
            code="rule.passed",
            severity=Severity.INFO,
            message="A rule in the pack passed.",
            rule_id="BNK-014",
        ),
        Finding(
            code="fact.unmatched.duration",
            severity=Severity.WARN,
            message="The repayment period stated in the answer does not appear in the sources.",
            fact=duration,
            match=Match(fact=duration, state=MatchState.UNMATCHED),
        ),
    ]


def build_sample_record(*, permute: bool = False) -> AuditRecord:
    """Build the sample record.

    Args:
        permute: When true, feed every collection in the opposite order
            and the metadata mapping with its keys inserted in reverse.
            The record must come out byte-identical either way; that is
            what ``test_canonical_json_stable.py`` asserts.

    Returns:
        The sample :class:`~groundlens.audit_record.AuditRecord`.
    """
    evidence = list(SAMPLE_EVIDENCE)
    findings = sample_findings()
    predicates = list(SAMPLE_PREDICATES)
    metadata = dict(SAMPLE_METADATA)

    if permute:
        evidence.reverse()
        findings.reverse()
        predicates.reverse()
        metadata = dict(reversed(list(SAMPLE_METADATA.items())))

    return build_record(
        answer=SAMPLE_ANSWER,
        evidence=evidence,
        ruleset=SAMPLE_RULESET,
        findings=findings,
        counts=SAMPLE_COUNTS,
        locale_profile=SAMPLE_LOCALE_PROFILE,
        metadata=metadata,
        tools_output="retrieval: 3 passages",
        reference_date=SAMPLE_REFERENCE_DATE,
        predicates=predicates,
    )


def build_sample_result(*, permute: bool = False) -> Result:
    """Build a full :class:`~groundlens.types.Result` around the sample record."""
    record = build_sample_record(permute=permute)
    return Result(
        decision=Decision.ESCALATE,
        findings=sort_findings(sample_findings()),
        audit=record,
    )
