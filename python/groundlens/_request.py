# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Shapes people actually have → the engine's VerifyRequest."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from groundlens._types import Evidence

EvidenceArg = (
    str
    | Sequence[str]
    | Sequence[tuple[str, str]]
    | Sequence[tuple[str, str, Mapping[str, str]]]
    | Sequence[Evidence]
    | Sequence[Mapping[str, Any]]
)


def _provenance(value: Any, index: int) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        msg = f"provenance must be a mapping of strings; got {type(value).__name__} at position {index}"
        raise TypeError(msg)
    return {str(k): str(v) for k, v in value.items()}


def as_sources(evidence: EvidenceArg) -> list[dict[str, Any]]:
    """Accept a string, strings, ``(id, text)`` pairs, ``(id, text, provenance)``
    triples, ``Evidence`` or dicts (with an optional ``provenance`` mapping).

    Ids are kept wherever they exist, because "which source backed this" is
    the question a reviewer actually asks.
    """
    if isinstance(evidence, str):
        return [{"id": "ctx-0", "text": evidence}]
    out: list[dict[str, Any]] = []
    for index, item in enumerate(evidence):
        if isinstance(item, Evidence):
            entry = {"id": item.id, "text": item.text}
            if item.provenance:
                entry["provenance"] = _provenance(item.provenance, index)
            out.append(entry)
        elif isinstance(item, str):
            out.append({"id": f"ctx-{index}", "text": item})
        elif isinstance(item, tuple) and len(item) == 2:
            out.append({"id": str(item[0]), "text": str(item[1])})
        elif isinstance(item, tuple) and len(item) == 3:
            entry = {"id": str(item[0]), "text": str(item[1])}
            provenance = _provenance(item[2], index)
            if provenance:
                entry["provenance"] = provenance
            out.append(entry)
        elif isinstance(item, Mapping) and "text" in item:
            entry = {"id": str(item.get("id", f"ctx-{index}")), "text": str(item["text"])}
            if item.get("locator"):
                entry["locator"] = str(item["locator"])
            provenance = _provenance(item.get("provenance"), index)
            if provenance:
                entry["provenance"] = provenance
            out.append(entry)
        else:
            msg = (
                "evidence items must be str, (id, text) or (id, text, provenance) tuples, "
                "Evidence or dicts with 'text'; "
                f"got {type(item).__name__} at position {index}"
            )
            raise TypeError(msg)
    return out


def build_request(
    *,
    answer: str,
    evidence: EvidenceArg,
    question: str | None = None,
    locale: str = "und",
    policy_yaml: str = "",
    rule_sets_json: Sequence[str] = (),
    units: bool = True,
    declared_precision: bool = False,
    percent_as_fraction: bool = False,
    derive: bool = True,
    rounding: str = "half_up",
    signing_key: str | None = None,
    previous_record_hash: str | None = None,
    bundle_hash: str | None = None,
    bundle: str | None = None,
    lexical: bool = True,
    metadata: Mapping[str, str] | None = None,
    scope: Mapping[str, str] | None = None,
    risk_class: str | None = None,
) -> str:
    request = {
        "answer": answer,
        "sources": as_sources(evidence),
        "question": question,
        "locale": locale,
        "policy_yaml": policy_yaml,
        "rule_sets_json": list(rule_sets_json),
        "numeric": {
            "units": units,
            "derive": derive,
            "rounding": rounding,
            "matching": {
                "declared_precision": declared_precision,
                "percent_as_fraction": percent_as_fraction,
            },
        },
        "signing_key_hex": signing_key,
        "previous_record_hash": previous_record_hash,
        "bundle_hash": bundle_hash,
        "bundle": bundle,
        "lexical": lexical,
        "metadata": dict(metadata or {}),
        "scope": {str(k): str(v) for k, v in (scope or {}).items()},
        "risk_class": risk_class,
    }
    return json.dumps(request, ensure_ascii=False)
