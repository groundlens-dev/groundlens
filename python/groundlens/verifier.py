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
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from groundlens import _engine
from groundlens._request import EvidenceArg
from groundlens.policy import Policy
from groundlens.record import Record
from groundlens.judges import Judge, ask
from groundlens.observe import CheckEvent, JudgeCall, Observer, Span, notify
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
        judge: the model you already use (:mod:`groundlens.judges`). It
            labels each sentence of the answer; the policy's ``judge``
            section says what its labels may do. It is asked only when the
            exact checks have not already failed the answer, since it can
            escalate but never pass. Without one, no model is called.
        locale, rounding, units, derive: how numbers are read, as in
            :func:`groundlens.verify`. A ``locale`` or ``rounding`` written in
            the policy wins.
        rules: rule sets run as symbolic verifiers.
        observers: told about every stored record and how long each step
            took (:mod:`groundlens.observe`, :mod:`groundlens.integrations`).
            They report; they never change a decision.
    """

    def __init__(
        self,
        policy: Policy | str | Path | None = None,
        *,
        signer: Signer | LocalKey | None = None,
        sink: Sink | None = None,
        judge: Judge | None = None,
        locale: str = "und",
        rounding: str = "half_up",
        units: bool = True,
        derive: bool = True,
        rules: Sequence[str | Path | Mapping] = (),
        observers: Sequence[Observer] = (),
    ) -> None:
        self.policy = Policy.coerce(policy)
        self.signer = signer
        self.sink = sink
        self.judge = judge
        self.locale = locale
        self.rounding = rounding
        self.units = units
        self.derive = derive
        self.rules = tuple(rules)
        self.observers = tuple(observers)

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
        timer = _Timer(time.time_ns())
        # The judge is asked once; a retry after a chain conflict reuses its
        # reply, since the prompt does not depend on the chain.
        reply = self._ask_judge(
            answer=answer, passages=passages, question=question, scope=scope, risk_class=risk_class, timer=timer
        )
        for attempt in range(CONFLICT_RETRIES):
            record = self._seal(
                answer=answer,
                passages=passages,
                question=question,
                scope=scope,
                risk_class=risk_class,
                metadata=metadata,
                previous=self.sink.head(),
                judge_reply=reply,
                timer=timer,
            )
            store_start = time.time_ns()
            try:
                self.sink.append(record)
            except ChainConflict:
                continue
            end = time.time_ns()
            timer.store = Span("store", store_start, end)
            if self.observers:
                notify(self.observers, timer.event(record, end, attempt, metadata))
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
        :meth:`store`. ``previous`` is the ``record_hash`` to chain to.
        Observers are not called: nothing has been stored yet."""
        reply = self._ask_judge(answer=answer, passages=passages, question=question, scope=scope, risk_class=risk_class)
        return self._seal(
            answer=answer,
            passages=passages,
            question=question,
            scope=scope,
            risk_class=risk_class,
            metadata=metadata,
            previous=previous,
            judge_reply=reply,
        )

    def judge_prompt(
        self,
        *,
        answer: str,
        passages: EvidenceArg,
        question: str | None = None,
        scope: Mapping[str, str] | None = None,
        risk_class: str | None = None,
    ) -> dict:
        """The exact prompt the judge would be sent: ``system``, ``user``,
        ``template_id``, ``prompt_hash`` and the ``claims`` it labels."""
        request = self._request(answer, passages, question, scope, risk_class, None, None)
        return json.loads(_engine.judge_prompt_json(request))

    def _ask_judge(self, *, answer, passages, question, scope, risk_class, timer=None) -> dict | None:
        if self.judge is None:
            return None
        # The judge can only escalate. If the exact checks already fail the
        # answer, nothing it says can change the decision: it is not asked.
        exact = json.loads(_engine.verify_unsigned_json(self._request(answer, passages, question, scope, risk_class, None, None)))
        if exact["content"]["outcome"]["decision"] == "FAIL":
            return None
        prompt = self.judge_prompt(answer=answer, passages=passages, question=question, scope=scope, risk_class=risk_class)
        start = time.time_ns()
        reply = ask(self.judge, prompt)
        if timer is not None:
            timer.judge = JudgeCall(
                "judge",
                start,
                time.time_ns(),
                adapter=reply["adapter"],
                model=reply["model"],
                error=reply["error"],
                response=reply["response"],
                system=prompt["system"],
                user=prompt["user"],
            )
        return reply

    def _request(self, answer, passages, question, scope, risk_class, metadata, previous) -> str:
        local_seed = self.signer.seed_hex if isinstance(self.signer, LocalKey) else None
        return _request(
            answer=answer,
            evidence=passages,
            policy=self.policy,
            question=question,
            locale=self.locale,
            rules=self.rules,
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

    def _seal(
        self, *, answer, passages, question, scope, risk_class, metadata, previous, judge_reply, timer=None
    ) -> Record:
        request = self._request(answer, passages, question, scope, risk_class, metadata, previous)
        if judge_reply is not None:
            request = json.dumps(dict(json.loads(request), judge=judge_reply), ensure_ascii=False)
        local = self.signer is None or isinstance(self.signer, LocalKey)
        start = time.time_ns()
        out = json.loads((_engine.verify_timed_json if local else _engine.verify_unsigned_timed_json)(request))
        if timer is not None:
            timer.engine(start, time.time_ns(), out["timings"])
        if local:
            return Record.from_json(json.dumps(out["record"]))
        unsigned = json.dumps(out["record"])
        sign_start = time.time_ns()
        signature = self.signer.sign(out["record"]["record_hash"].encode("utf-8"))
        public_key = self.signer.public_key()
        if timer is not None:
            timer.sign = Span("sign", sign_start, time.time_ns())
        return Record.from_json(
            _engine.attach_signature_json(unsigned, self.signer.algorithm, public_key.hex(), bytes(signature).hex())
        )

    def store(self, record: Record) -> None:
        """Store a sealed record. Raises :class:`groundlens.sinks.StoreError`."""
        if self.sink is None:
            raise ValueError("no sink configured")
        self.sink.append(record)


class _Timer:
    """What one ``check`` measured, until it becomes a :class:`CheckEvent`.
    A retry after a chain conflict overwrites the engine and signer times, so
    the event describes the attempt that was stored."""

    def __init__(self, start_ns: int) -> None:
        self.start_ns = start_ns
        self.judge: JudgeCall | None = None
        self.sign: Span | None = None
        self.store: Span | None = None
        self.engine_span = Span("engine", start_ns, start_ns)
        self.verifiers: tuple[Span, ...] = ()

    def engine(self, start: int, end: int, timings: dict) -> None:
        self.engine_span = Span("engine", start, end)
        spans, at = [], start
        for verifier_id, micros in timings["verifiers"]:
            spans.append(Span(verifier_id, at, at + micros * 1000))
            at += micros * 1000
        self.verifiers = tuple(spans)

    def event(self, record: Record, end_ns: int, retries: int, metadata) -> CheckEvent:
        return CheckEvent(
            record=record,
            start_ns=self.start_ns,
            end_ns=end_ns,
            verifiers=self.verifiers,
            engine=self.engine_span,
            judge=self.judge,
            sign=self.sign,
            store=self.store,
            retries=retries,
            metadata=dict(metadata or {}),
        )
