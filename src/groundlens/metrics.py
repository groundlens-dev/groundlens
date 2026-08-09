"""Canary metrics, as contract section 8 defines them.

The primary reported metric is **escalation rate at fixed defect recall,
per defect class**. Not AUROC, not accuracy, not F1.

Three things follow from that, and all three are deliberate:

**No AUROC.** A receiver operating characteristic needs a score to sweep a
threshold along. :func:`groundlens.check` emits no score, by design: it
returns clear or escalate and nothing in between. There is no threshold to
sweep, so an AUROC would have to be manufactured from a proxy, and the
number it produced would be about the proxy. Worse, a single aggregate
figure is exactly the shape that hides the failure this measurement exists
to find: a checker that escalates almost everything scores respectably on
any pooled metric while being useless in a queue.

**No floats.** Every rate here is a pair of integers rendered as
``"numerator/denominator"``, unreduced. Unreduced because ``"3/4"`` and
``"75/100"`` are the same number and very different evidence. Contract
section 5 forbids floating point in the decision path and in the audit
record; the reporting path keeps to it too, so that a number copied out of
this table into a document is the number that was measured.

**Stratified by surface-form distance, never by register alignment.**
Section 8 is explicit. Register alignment is the variable the register-wall
work showed a detector can read instead of grounding, and stratifying by it
would let a shortcut look like a result.

The three per-class columns:

``recall``
    Of the cases carrying this defect, how many escalated. This is the
    number a compliance team is buying.
``escalation_rate_on_clean_traffic``
    Of the clean cases, how many escalated anyway. This is the price. It is
    a property of the whole checker rather than of one defect class, so it
    repeats down the column: the same false-alarm rate is what every row's
    recall was bought with.
``extraction_recall``
    Of the cases in this class whose defect is fact-bearing, how many had a
    fact of the relevant kind extracted at all. It separates "the extractor
    never saw it" from "the extractor saw it and no rule acted". Those are
    different bugs. Blank where the class is structural or lexical and no
    fact kind applies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from groundlens.canaries import (
    DEFECT_CLASSES,
    SURFACE_FORM_DISTANCES,
)
from groundlens.types import Decision

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from groundlens.canaries import CanaryOutcome

__all__ = [
    "ClassMetrics",
    "MetricsTable",
    "Rate",
    "compute_metrics",
    "render_cross_tab",
    "render_noise",
    "render_table",
]

_NOT_APPLICABLE = "n/a"


@dataclass(frozen=True, slots=True)
class Rate:
    """An exact rate: two integers, never divided.

    ``str(rate)`` is ``"numerator/denominator"``, or ``"n/a"`` when the
    denominator is zero. There is no ``float`` accessor and there will not
    be one; anyone who needs a percentage can do the division at the point
    of reading it, where the rounding is visible.
    """

    numerator: int
    denominator: int

    def __str__(self) -> str:
        """Render as an unreduced fraction, or ``n/a`` when undefined."""
        if self.denominator == 0:
            return _NOT_APPLICABLE
        return f"{self.numerator}/{self.denominator}"

    @property
    def defined(self) -> bool:
        """False when there were no cases to measure."""
        return self.denominator > 0

    def at_least(self, numerator: int, denominator: int) -> bool:
        """True when this rate is at least ``numerator/denominator``.

        Compared by cross-multiplication on integers, so no float enters
        a gate that a build depends on.
        """
        if not self.defined or denominator <= 0:
            return False
        return self.numerator * denominator >= numerator * self.denominator


@dataclass(frozen=True, slots=True)
class ClassMetrics:
    """One row of the table: the numbers for a single defect class."""

    defect_class: str
    cases: int
    recall: Rate
    escalation_rate_on_clean_traffic: Rate
    extraction_recall: Rate
    code_assertions: Rate

    @property
    def is_clean(self) -> bool:
        """True for the control class."""
        return self.defect_class == "clean"


@dataclass(frozen=True, slots=True)
class MetricsTable:
    """Every row, plus the cross-tabulation section 8 asks for."""

    rows: tuple[ClassMetrics, ...]
    cross_tab: tuple[tuple[str, str, Rate], ...]
    clean_escalation: Rate
    clean_cases: int
    clean_with_any_warn: Rate
    warn_findings_on_clean: Rate
    total_cases: int
    failures: tuple[str, ...]

    def row(self, defect_class: str) -> ClassMetrics | None:
        """The row for one defect class, or None if the suite had none."""
        for row in self.rows:
            if row.defect_class == defect_class:
                return row
        return None


# ── Computation ─────────────────────────────────────────────────────────────


def _escalated(outcome: CanaryOutcome) -> bool:
    return outcome.decision is Decision.ESCALATE


def compute_metrics(outcomes: Sequence[CanaryOutcome] | Iterable[CanaryOutcome]) -> MetricsTable:
    """Compute the section 8 table over a set of canary outcomes.

    Recall for a defect class counts *escalations*, not passed cases. A
    case may escalate for the wrong reason and still count towards recall,
    because recall is about what reaches a reviewer's queue; whether it
    escalated for the stated reason is the separate ``codes`` column, and
    keeping the two apart is what stops a coincidentally-right answer from
    reading as a working rule.

    Args:
        outcomes: Outcomes from one or more canary runs.

    Returns:
        The full table, including the defect-class by surface-form
        cross-tabulation.
    """
    items = tuple(outcomes)

    clean = [item for item in items if item.case.defect_class == "clean"]
    clean_escalated = sum(1 for item in clean if _escalated(item))
    clean_escalation = Rate(clean_escalated, len(clean))
    clean_with_warn = Rate(sum(1 for item in clean if item.warn_codes), len(clean))
    warn_findings = Rate(sum(len(item.warn_codes) for item in clean), len(clean))

    rows: list[ClassMetrics] = []
    for defect_class in DEFECT_CLASSES:
        in_class = [item for item in items if item.case.defect_class == defect_class]
        if not in_class:
            continue

        if defect_class == "clean":
            # A clean case is "recalled" when it is correctly left alone.
            # Reporting the escalation rate in the recall column instead
            # would put a number in that column meaning the opposite of
            # every other number in it.
            recall = Rate(sum(1 for item in in_class if not _escalated(item)), len(in_class))
        else:
            recall = Rate(sum(1 for item in in_class if _escalated(item)), len(in_class))

        extractable = [item for item in in_class if item.extraction_applies]
        extraction_recall = Rate(
            sum(1 for item in extractable if item.extraction_succeeded),
            len(extractable),
        )

        asserting = [item for item in in_class if item.case.expect_codes]
        code_assertions = Rate(
            sum(
                1
                for item in asserting
                if all(code in item.codes for code in item.case.expect_codes)
            ),
            len(asserting),
        )

        rows.append(
            ClassMetrics(
                defect_class=defect_class,
                cases=len(in_class),
                recall=recall,
                escalation_rate_on_clean_traffic=clean_escalation,
                extraction_recall=extraction_recall,
                code_assertions=code_assertions,
            )
        )

    cross: list[tuple[str, str, Rate]] = []
    for defect_class in DEFECT_CLASSES:
        for distance in SURFACE_FORM_DISTANCES:
            cell = [
                item
                for item in items
                if item.case.defect_class == defect_class
                and item.case.surface_form_distance == distance
            ]
            if not cell:
                continue
            if defect_class == "clean":
                hits = sum(1 for item in cell if not _escalated(item))
            else:
                hits = sum(1 for item in cell if _escalated(item))
            cross.append((defect_class, distance, Rate(hits, len(cell))))

    failures = tuple(f"{item.case.id}: {reason}" for item in items for reason in item.failures)

    return MetricsTable(
        rows=tuple(rows),
        cross_tab=tuple(cross),
        clean_escalation=clean_escalation,
        clean_cases=len(clean),
        clean_with_any_warn=clean_with_warn,
        warn_findings_on_clean=warn_findings,
        total_cases=len(items),
        failures=failures,
    )


# ── Rendering ───────────────────────────────────────────────────────────────


def _render(rows: Sequence[Sequence[str]], headers: Sequence[str]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def line(cells: Sequence[str]) -> str:
        parts = [
            cell.ljust(widths[index]) if index == 0 else cell.rjust(widths[index])
            for index, cell in enumerate(cells)
        ]
        return "  ".join(parts).rstrip()

    out = [line(headers), "  ".join("-" * width for width in widths)]
    out.extend(line(row) for row in rows)
    return "\n".join(out)


def render_table(table: MetricsTable) -> str:
    """The primary table: one row per defect class."""
    headers = ("defect class", "n", "recall", "escalation on clean", "extraction recall", "codes")
    rows = [
        (
            row.defect_class,
            str(row.cases),
            str(row.recall),
            str(row.escalation_rate_on_clean_traffic),
            str(row.extraction_recall),
            str(row.code_assertions),
        )
        for row in table.rows
    ]
    body = _render(rows, headers)
    footnote = (
        "\nrecall            : defect cases escalated / defect cases"
        "\n                    (clean row: cases correctly left alone / clean cases)"
        "\nescalation on clean: clean cases escalated / clean cases. One number for the"
        "\n                    whole checker, repeated: it is what every row's recall cost."
        "\nextraction recall : cases where a fact of the defect's kind was extracted at all."
        "\ncodes             : cases whose asserted finding codes were all emitted."
        "\nAll rates are exact unreduced fractions. There are no floats and no AUROC."
    )
    return body + "\n" + footnote


def render_cross_tab(table: MetricsTable) -> str:
    """Defect class crossed with surface-form distance, as section 8 requires."""
    headers = ("defect class", "surface form", "recall")
    rows = [
        (defect_class, distance, str(rate)) for defect_class, distance, rate in table.cross_tab
    ]
    if not rows:
        return "cross-tabulation: no cases."
    return _render(rows, headers)


def render_noise(table: MetricsTable) -> str:
    """What clean traffic costs a reviewer even when it does not escalate.

    A warn finding does not escalate, so it never appears in the escalation
    rate. It still lands in front of a person as a line of output. A checker
    that attaches nine warnings to every correct answer trains its reader to
    stop looking, which costs exactly as much as a false escalation and is
    invisible to the primary table. Hence this section.
    """
    lines = [
        f"clean cases                         : {table.clean_cases}",
        f"clean cases escalated (false alarms): {table.clean_escalation}",
        f"clean cases carrying >= 1 warning   : {table.clean_with_any_warn}",
        f"warnings emitted per clean case     : {table.warn_findings_on_clean}",
    ]
    return "\n".join(lines)
