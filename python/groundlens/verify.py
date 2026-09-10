# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""``verify()``: the GroundLens 4.0 entry point.

    answer + evidence
        → claims
        → verifiers (each one produces evidence, never truth)
        → evidence graph
        → policy (turns evidence into PASS / REVIEW / FAIL)
        → signed, hash-chained record
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from groundlens import _engine
from groundlens._request import EvidenceArg, build_request
from groundlens.bundle import Bundle
from groundlens.policy import Policy
from groundlens.record import Record


def verify(
    answer: str,
    evidence: EvidenceArg,
    *,
    policy: Policy | str | Path | None = None,
    question: str | None = None,
    locale: str = "und",
    rules: Sequence[str | Path | Mapping] = (),
    bundle: Bundle | str | Path | None = None,
    lexical: bool = True,
    signing_key: str | None = None,
    previous: Record | str | None = None,
    log: str | Path | None = None,
    units: bool = True,
    declared_precision: bool = False,
    percent_as_fraction: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> Record:
    """Verify ``answer`` against ``evidence`` under ``policy`` and seal a record.

    Args:
        answer: the model output to verify.
        evidence: the retrieved sources. Pass ``(id, text)`` pairs so the
            record can say which source backed or contradicted each claim.
        policy: a :class:`Policy`, a built-in name (``"eu_ai_act_high_risk_v1"``),
            a path, or YAML text. ``None`` means ``groundlens_default_v1``.
        question: what the model was asked. Never a source; claims that echo
            it are noted.
        locale: how the documents write numbers: ``"und"``, ``"en"``, ``"es"``...
        rules: rule sets (YAML/JSON paths or dicts) run as symbolic verifiers.
        bundle: a :class:`Bundle`, a bundle directory, or a bundle name.
            ``None`` uses the installed ``base`` bundle when there is one
            (``groundlens bundle pull base``). The bundle hash goes into the
            record and its encoder runs the lexical channel.
        lexical: run the lexical channel when an encoder is available.
        signing_key: 32-byte hex Ed25519 seed. An ephemeral key is used if absent.
        previous: the previous record (or its ``record_hash``) to chain to.
        log: an append-only JSON Lines file; the record is appended and the
            chain continues from its last record.
        units: compare numerals as quantities (scale, currency, percent,
            physical units). ``False`` gives groundlens 3.x bare-number semantics.
        declared_precision, percent_as_fraction: named relaxations of numeric
            equality, off by default; every relaxed match is noted in the receipt.

    Returns:
        A :class:`Record`. ``record.decision`` is the policy's decision;
        ``record.evidence`` is what each verifier said; ``record.reasons``
        is what a reviewer should read first.
    """
    pol = Policy.coerce(policy)
    previous_hash: str | None
    if isinstance(previous, Record):
        previous_hash = previous.record_hash
    else:
        previous_hash = previous
    if log is not None and previous_hash is None:
        path = Path(log)
        if path.exists():
            existing = Record.read_log(path)
            if existing:
                previous_hash = existing[-1].record_hash

    request = build_request(
        answer=answer,
        evidence=evidence,
        question=question,
        locale=locale,
        policy_yaml=pol.yaml,
        rule_sets_json=[_rules_json(r) for r in rules],
        units=units,
        declared_precision=declared_precision,
        percent_as_fraction=percent_as_fraction,
        signing_key=signing_key,
        previous_record_hash=previous_hash,
        bundle=str(bundle.root) if isinstance(bundle, Bundle) else (str(bundle) if bundle else None),
        lexical=lexical,
        metadata=metadata,
    )
    record = Record.from_json(_engine.verify_json(request))
    if log is not None:
        record.append_to(log)
    return record


def _rules_json(value: str | Path | Mapping) -> str:
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False)
    path = Path(value)
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        return _engine.yaml_to_json(text)
    return text
