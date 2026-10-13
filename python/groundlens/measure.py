# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""``measure`` and ``replay``: what a policy lets through, and what a change would do.

**measure.** Your team labels a small sample of past answers as right or
wrong, without seeing GroundLens's verdict. From those labels and the full log,
``measure`` estimates the rate of wrong answers among those that passed, with a
confidence interval, per risk class, and what a decision costs: review minutes
and the expected cost of a wrong answer that got through. The report says how
it was computed and is signed.

**replay.** Before you change a policy, run your past traffic under the new
one. Each answer is checked again by the deterministic checks; the judge is not
asked again when its earlier evidence answered the very same prompt. The
report counts how many decisions would change, and which.

How the estimate works. Records are split into strata by decision and risk
class. The labels come from a sample drawn within each stratum (``sample``
draws one). Within a stratum, the wrong rate is estimated with the
Agresti-Coull interval, which stays sensible with few labels and rates near
zero. If you also pass a prediction for every record, a score from another
model that tends to be high on wrong answers, the stratum estimate is the
prediction-powered one: the mean prediction over all records plus the mean
error of the prediction on the labelled ones, which narrows the interval when
the prediction is good and costs nothing when it is not. Strata are combined
by their share of the passed answers.
"""

from __future__ import annotations

import csv
import json
import math
import random
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from groundlens import _engine
from groundlens.record import Record

Z95 = 1.959963984540054
#: Above this half-width the report says the interval is too wide to rely on.
WIDE = 0.05


def _key(record: Record) -> tuple[str, str]:
    return record.decision, record.risk_class or "-"


# ---- sampling -------------------------------------------------------------------------


def sample(records: Sequence[Record], n: int = 50, seed: int = 0) -> list[str]:
    """Record ids to label, drawn within each stratum (decision and risk
    class), in proportion to its size and at least two per stratum when it has
    them. The list is shuffled and carries no decision, so the people labelling
    do not see the verdict."""
    rng = random.Random(seed)
    strata: dict[tuple[str, str], list[str]] = {}
    for r in records:
        strata.setdefault(_key(r), []).append(r.record_id)
    total = sum(len(v) for v in strata.values())
    chosen: list[str] = []
    for key in sorted(strata):
        ids = sorted(strata[key])
        want = max(min(2, len(ids)), round(n * len(ids) / total)) if total else 0
        chosen.extend(rng.sample(ids, min(want, len(ids))))
    rng.shuffle(chosen)
    return chosen


# ---- labels ---------------------------------------------------------------------------

_WRONG = {"wrong", "1", "true", "yes", "incorrect", "error"}
_RIGHT = {"correct", "right", "0", "false", "no", "ok"}


def read_labels(path: str | Path) -> tuple[dict[str, bool], dict[str, float]]:
    """Labels from a CSV (``record_id,label[,prediction]``) or JSON Lines file.
    A label is ``wrong`` or ``correct`` (also 1/0, true/false). Returns
    ``(wrong_by_id, prediction_by_id)``."""
    p = Path(path)
    rows: list[Mapping[str, Any]]
    if p.suffix == ".jsonl":
        rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        with p.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    labels: dict[str, bool] = {}
    predictions: dict[str, float] = {}
    for row in rows:
        rid = str(row["record_id"]).strip()
        raw = row.get("label")
        if raw not in (None, ""):
            value = str(raw).strip().lower()
            if value not in _WRONG | _RIGHT:
                raise ValueError(f"{path}: label {raw!r} for {rid} is neither wrong nor correct")
            labels[rid] = value in _WRONG
        if row.get("prediction") not in (None, ""):
            predictions[rid] = float(row["prediction"])
    return labels, predictions


# ---- estimation -----------------------------------------------------------------------


def _agresti(wrong: int, n: int) -> tuple[float, float]:
    z2 = Z95 * Z95
    p = (wrong + z2 / 2) / (n + z2)
    return p, p * (1 - p) / (n + z2)


def _ppi(labelled: list[tuple[bool, float]], all_predictions: list[float]) -> tuple[float, float]:
    big_n, n = len(all_predictions), len(labelled)
    mean_f = sum(all_predictions) / big_n
    residuals = [float(y) - f for y, f in labelled]
    mean_r = sum(residuals) / n
    var_f = sum((f - mean_f) ** 2 for f in all_predictions) / max(big_n - 1, 1)
    var_r = sum((r - mean_r) ** 2 for r in residuals) / max(n - 1, 1)
    return min(max(mean_f + mean_r, 0.0), 1.0), var_f / big_n + var_r / n


def _stratum(records: list[Record], labels: Mapping[str, bool], predictions: Mapping[str, float]) -> dict[str, Any]:
    ids = [r.record_id for r in records]
    labelled = [rid for rid in ids if rid in labels]
    wrong = sum(labels[rid] for rid in labelled)
    out: dict[str, Any] = {"records": len(ids), "labelled": len(labelled), "labelled_wrong": wrong}
    if not labelled:
        out.update(estimate=None, variance=None, method="none")
        return out
    if predictions and all(rid in predictions for rid in ids):
        est, var = _ppi([(labels[rid], predictions[rid]) for rid in labelled], [predictions[rid] for rid in ids])
        out["method"] = "prediction-powered"
    else:
        est, var = _agresti(wrong, len(labelled))
        out["method"] = "agresti-coull"
    out.update(estimate=est, variance=var)
    return out


def _combine(strata: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(s["records"] for s in strata)
    if total == 0:
        return {"estimate": None, "low": None, "high": None, "note": "no records in these strata"}
    if any(s["estimate"] is None for s in strata if s["records"]):
        return {"estimate": None, "low": None, "high": None, "note": "a stratum has records but no labels; label some"}
    est = sum(s["records"] / total * s["estimate"] for s in strata)
    var = sum((s["records"] / total) ** 2 * s["variance"] for s in strata)
    half = Z95 * math.sqrt(var)
    out = {"estimate": est, "low": max(est - half, 0.0), "high": min(est + half, 1.0)}
    if half > WIDE:
        out["note"] = f"the interval is wider than ±{WIDE:.0%}; label more answers that passed"
    return out


def measure(
    records: Sequence[Record],
    labels: Mapping[str, bool],
    *,
    predictions: Mapping[str, float] | None = None,
    review_minutes: float | None = None,
    review_cost_per_hour: float | None = None,
    error_cost: float | None = None,
    sample_seed: int | None = None,
) -> dict[str, Any]:
    """Estimate, from labels on a sample, the rate of wrong answers among those
    the policy passed. Returns the report content (see :func:`sign`)."""
    predictions = predictions or {}
    unknown = sorted(set(labels) - {r.record_id for r in records})
    if unknown:
        raise ValueError(f"labels name records that are not in the log: {', '.join(unknown[:5])}")
    groups: dict[tuple[str, str], list[Record]] = {}
    for r in records:
        groups.setdefault(_key(r), []).append(r)
    strata = {key: _stratum(group, labels, predictions) for key, group in sorted(groups.items())}
    total = len(records)
    passed = [s for (d, _), s in strata.items() if d == "PASS"]
    n_pass = sum(s["records"] for s in passed)
    n_review = sum(s["records"] for (d, _), s in strata.items() if d == "REVIEW")
    overall = _combine(passed)
    per_class = {
        cls: _combine([s for (d, c), s in strata.items() if d == "PASS" and c == cls])
        for cls in sorted({c for (d, c) in strata if d == "PASS"})
    }
    report: dict[str, Any] = {
        "question": "Of the answers this policy passed, what share were wrong?",
        "records": total,
        "decisions": {d: sum(s["records"] for (dd, _), s in strata.items() if dd == d) for d in ("PASS", "REVIEW", "FAIL")},
        "policies": sorted({f"{r.policy_id} {r.policy_hash}" for r in records}),
        "labelled": len(labels),
        "wrong_among_passed": overall,
        "wrong_passed_per_1000_answers": _scale(overall, 1000 * n_pass / total if total else 0.0),
        "by_risk_class": per_class,
        "strata": [{"decision": d, "risk_class": c, **s} for (d, c), s in strata.items()],
        "method": {
            "interval": "95 %, normal approximation over strata",
            "stratum": "Agresti-Coull; prediction-powered when every record of the stratum has a prediction",
            "combination": "strata weighted by their share of the answers that passed",
            "labels": "drawn within each decision and risk class, labelled without seeing the verdict",
            "sample_seed": sample_seed,
        },
    }
    if review_minutes is not None and review_cost_per_hour is not None:
        review = n_review * review_minutes / 60 * review_cost_per_hour
        escaped = n_pass * overall["estimate"] * error_cost if error_cost is not None and overall["estimate"] is not None else None
        report["cost"] = {
            "review_minutes_per_answer": review_minutes,
            "review_cost_per_hour": review_cost_per_hour,
            "error_cost": error_cost,
            "review_total": review,
            "expected_escaped_error_total": escaped,
            "per_decision": (review + (escaped or 0.0)) / total if total else None,
        }
    return report


def _scale(interval: Mapping[str, Any], factor: float) -> dict[str, Any]:
    return {k: (v * factor if isinstance(v, float) else v) for k, v in interval.items()}


# ---- replay ---------------------------------------------------------------------------


def _stored_judge(record: Record) -> dict[str, Any] | None:
    graph = record.raw["content"]["graph"]
    infos = [v for v in graph["verifiers"] if v["id"].startswith("llm_judge.")]
    if not infos:
        return None
    info = infos[0]
    evidence = [e for e in graph["evidence"] if e["verifier_id"] == info["id"]]
    failure = next((m for vid, m in graph.get("failures", []) if vid == info["id"]), None)
    return {"info": info, "evidence": evidence, "failure": failure}


def replay(traffic: Iterable[Mapping[str, Any]], records: Sequence[Record], verifier: Any) -> dict[str, Any]:
    """Check past traffic again under ``verifier``'s policy.

    ``traffic`` holds what each request was: ``answer``, ``passages``, and
    optionally ``question``, ``scope``, ``risk_class`` and the ``record_id`` of
    the record it produced. The judge's evidence in that record is reused when
    it answered the same prompt; otherwise the verifier's own judge is asked,
    or none. Nothing is stored.
    """
    by_id = {r.record_id: r for r in records}
    rows = []
    reused = asked = not_reusable = 0
    for item in traffic:
        old = by_id.get(str(item.get("record_id", "")))
        kwargs = {
            "answer": item["answer"],
            "passages": [(p["id"], p["text"], p.get("provenance") or {}) if isinstance(p, Mapping) else p for p in item["passages"]],
            "question": item.get("question"),
            "scope": item.get("scope"),
            "risk_class": item.get("risk_class"),
        }
        stored = _stored_judge(old) if old else None
        new: Record | None = None
        if stored is not None:
            request = verifier._request(kwargs["answer"], kwargs["passages"], kwargs["question"], kwargs["scope"], kwargs["risk_class"], None, None)
            request = json.dumps(dict(json.loads(request), judge_evidence=stored), ensure_ascii=False)
            try:
                new = Record.from_json(_engine.verify_json(request))
                reused += 1
            except ValueError as e:
                if "another prompt" not in str(e):
                    raise
                not_reusable += 1
        if new is None:
            if verifier.judge is not None:
                asked += 1
            new = verifier.seal(**kwargs)
        rows.append({"record_id": old.record_id if old else None, "old": old.decision if old else None, "new": new.decision})
    matrix: dict[str, dict[str, int]] = {}
    for row in rows:
        if row["old"] is not None:
            matrix.setdefault(row["old"], {}).setdefault(row["new"], 0)
            matrix[row["old"]][row["new"]] += 1
    changed = [r for r in rows if r["old"] is not None and r["old"] != r["new"]]
    return {
        "question": "How many past decisions would this policy change?",
        "policy": f"{verifier.policy.id} {verifier.policy.hash}",
        "requests": len(rows),
        "compared": sum(1 for r in rows if r["old"] is not None),
        "changed": len(changed),
        "transitions": matrix,
        "changes": changed,
        "judge": {"reused": reused, "asked_again": asked, "not_reusable": not_reusable},
    }


# ---- signing --------------------------------------------------------------------------


def sign(kind: str, content: Mapping[str, Any], signing_key: str | None = None) -> dict[str, Any]:
    """Sign a report with an Ed25519 seed (a new one if ``None``)."""
    doc = _engine.sign_document_json(kind, json.dumps(content, ensure_ascii=False), signing_key or _engine.keygen())
    return json.loads(doc)


def verify_signed(doc: Mapping[str, Any]) -> None:
    """Recompute a signed report's hash and check its signature."""
    try:
        _engine.verify_document_json(json.dumps(doc, ensure_ascii=False))
    except RuntimeError as e:
        from groundlens.record import IntegrityError  # noqa: PLC0415

        raise IntegrityError(str(e)) from None
