# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""``Verifier``: set up once, then ``check()`` every answer.

    verifier = groundlens.Verifier(
        policy="eu_ai_act_high_risk_v1",
        signer=groundlens.signers.aws_kms(boto3.client("kms"), key_id),
        sink=groundlens.sinks.jsonl("records/"),
    )
    record = verifier.check(question=q, answer=a, passages=passages, scope={"entity": "UPS"})
    record.decision   # 'PASS' | 'REVIEW' | 'FAIL'

``check`` returns only after the record is signed and stored. If it cannot
be stored, ``check`` raises :class:`groundlens.sinks.StoreError` and returns
no decision: a decision without its record is not one GroundLens gives.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from groundlens import _engine
from groundlens._request import EvidenceArg
from groundlens.policy import Policy
from groundlens.record import Record
from groundlens.signers import LocalKey, Signer
from groundlens.sinks import ChainConflict, Sink, StoreError
from groundlens.verify import _request

#: How many times ``check`` re-seals when another writer extended the chain first.
CONFLICT_RETRIES = 3


class Verifier:
    """A policy, a signer and a sink, fixed once for an application.

    Args:
        policy: a :class:`Policy`, a shipped name, a path or YAML. ``None``
            means ``groundlens_default_v1``.
        signer: who signs records (:mod:`groundlens.signers`). ``None`` signs
            with a new Ed25519 key for every record, which proves integrity
            but not who wrote it; use it only in development.
        sink: where records go (:mod:`groundlens.sinks`). Required by
            :meth:`check`; :meth:`seal` works without one.
        locale, rounding, units, derive: how numbers are read, as in
            :func:`groundlens.verify`. A ``locale`` or ``rounding`` written in
            the policy wins.
        rules: rule sets run as symbolic verifiers.
    """

    def __init__(
        self,
        policy: Policy | str | Path | None = None,
        *,
        signer: Signer | LocalKey | None = None,
        sink: Sink | None = None,
        locale: str = "und",
        rounding: str = "half_up",
        units: bool = True,
        derive: bool = True,
        rules: Sequence[str | Path | Mapping] = (),
    ) -> None:
        self.policy = Policy.coerce(policy)
        self.signer = signer
        self.sink = sink
        self.locale = locale
        self.rounding = rounding
        self.units = units
        self.derive = derive
        self.rules = tuple(rules)

    def check(
        self,
        *,
        answer: str,
        passages: EvidenceArg,
        question: str | None = None,
        scope: Mapping[str, str] | None = None,
        risk_class: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> Record:
        """Verify, sign, store, and only then return the record.

        Raises :class:`groundlens.sinks.StoreError` when the record cannot be
        stored; no decision is returned without a stored record.
        """
        if self.sink is None:
            raise ValueError("check() stores the record before it returns; pass sink=, or use seal() and store()")
        for _ in range(CONFLICT_RETRIES):
            record = self.seal(
                answer=answer,
                passages=passages,
                question=question,
                scope=scope,
                risk_class=risk_class,
                metadata=metadata,
                previous=self.sink.head(),
            )
            try:
                self.sink.append(record)
            except ChainConflict:
                continue
            return record
        raise StoreError(f"the chain kept moving under {CONFLICT_RETRIES} attempts; give each writer its own chain")

    def seal(
        self,
        *,
        answer: str,
        passages: EvidenceArg,
        question: str | None = None,
        scope: Mapping[str, str] | None = None,
        risk_class: str | None = None,
        metadata: Mapping[str, str] | None = None,
        previous: str | None = None,
    ) -> Record:
        """Verify and sign, without storing. For batch writers, who store with
        :meth:`store`. ``previous`` is the ``record_hash`` to chain to."""
        local_seed = self.signer.seed_hex if isinstance(self.signer, LocalKey) else None
        request = _request(
            answer=answer,
            evidence=passages,
            policy=self.policy,
            question=question,
            locale=self.locale,
            rules=self.rules,
            bundle=None,
            lexical=True,
            signing_key=local_seed,
            previous_hash=previous,
            units=self.units,
            declared_precision=False,
            percent_as_fraction=False,
            derive=self.derive,
            rounding=self.rounding,
            metadata=metadata,
            scope=scope,
            risk_class=risk_class,
        )
        if self.signer is None or isinstance(self.signer, LocalKey):
            return Record.from_json(_engine.verify_json(request))
        unsigned = _engine.verify_unsigned_json(request)
        record_hash = json.loads(unsigned)["record_hash"]
        signature = self.signer.sign(record_hash.encode("utf-8"))
        public_key = self.signer.public_key()
        return Record.from_json(
            _engine.attach_signature_json(unsigned, self.signer.algorithm, public_key.hex(), bytes(signature).hex())
        )

    def store(self, record: Record) -> None:
        """Store a sealed record. Raises :class:`groundlens.sinks.StoreError`."""
        if self.sink is None:
            raise ValueError("no sink configured")
        self.sink.append(record)
