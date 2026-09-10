# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Shapes people actually have → the engine's VerifyRequest."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from groundlens._types import Evidence

EvidenceArg = str | Sequence[str] | Sequence[tuple[str, str]] | Sequence[Evidence] | Sequence[Mapping[str, str]]


def as_sources(evidence: EvidenceArg) -> list[dict[str, Any]]:
    """Accept a string, strings, ``(id, text)`` pairs, ``Evidence`` or dicts.

    Ids are kept wherever they exist, because "which source backed this" is
    the question a reviewer actually asks.
    """
    if isinstance(evidence, str):
        return [{"id": "ctx-0", "text": evidence}]
    out: list[dict[str, Any]] = []
    for index, item in enumerate(evidence):
        if isinstance(item, Evidence):
            out.append({"id": item.id, "text": item.text})
        elif isinstance(item, str):
            out.append({"id": f"ctx-{index}", "text": item})
        elif isinstance(item, tuple) and len(item) == 2:
            out.append({"id": str(item[0]), "text": str(item[1])})
        elif isinstance(item, Mapping) and "text" in item:
            entry = {"id": str(item.get("id", f"ctx-{index}")), "text": str(item["text"])}
            if item.get("locator"):
                entry["locator"] = str(item["locator"])
            out.append(entry)
        else:
            msg = (
                "evidence items must be str, (id, text) tuples, Evidence or dicts with 'text'; "
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
    signing_key: str | None = None,
    previous_record_hash: str | None = None,
    bundle_hash: str | None = None,
    bundle: str | None = None,
    lexical: bool = True,
    metadata: Mapping[str, str] | None = None,
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
    }
    return json.dumps(request, ensure_ascii=False)
