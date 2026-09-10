# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""The evidence record: what a verification leaves behind.

One per verification, hash-chained to the previous one, signed. It carries
the verifiers that ran (with artefact hashes), the evidence they produced,
the policy that interpreted it (by hash), the decision with its reasons and
the regulatory controls it triggered. ``Record.verify_chain`` recomputes
every hash and signature offline.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from groundlens import _engine


class IntegrityError(RuntimeError):
    """A hash, a chain link or a signature did not verify."""


@dataclass(frozen=True)
class ClaimOutcome:
    claim_id: str
    decision: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceItem:
    """What one verifier said about one claim. Evidence, not truth."""

    verifier_id: str
    verifier_version: str
    claim_id: str
    result: str
    score: float
    confidence: float
    determinism: str
    rationale: str
    source_id: str | None
    #: Byte offsets into the normalised UTF-8 source text (the engine's contract).
    source_span: tuple[int, int] | None
    source_text: str | None
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Record:
    """A sealed evidence record. ``raw`` is the exact JSON the engine produced."""

    raw: dict[str, Any]

    # ---- identity and integrity -------------------------------------------------
    @property
    def record_id(self) -> str:
        return self.raw["record_id"]

    @property
    def timestamp(self) -> str:
        return self.raw["timestamp"]

    @property
    def content_hash(self) -> str:
        """Hash of everything that is a function of input, bundle and policy.
        Identical across machines for the same verification."""
        return self.raw["content_hash"]

    @property
    def record_hash(self) -> str:
        return self.raw["record_hash"]

    @property
    def previous_record_hash(self) -> str | None:
        return self.raw.get("previous_record_hash")

    @property
    def signature(self) -> str:
        return self.raw["signature"]

    @property
    def signer_public_key(self) -> str:
        return self.raw["signer_public_key"]

    # ---- content -----------------------------------------------------------------
    @property
    def decision(self) -> str:
        """``'PASS'``, ``'REVIEW'`` or ``'FAIL'``. Produced by the policy, never by a verifier."""
        return self.raw["content"]["outcome"]["decision"]

    @property
    def policy_id(self) -> str:
        return self.raw["content"]["outcome"]["policy_id"]

    @property
    def policy_hash(self) -> str:
        return self.raw["content"]["outcome"]["policy_hash"]

    @property
    def input_hash(self) -> str:
        return self.raw["content"]["input_hash"]

    @property
    def bundle_hash(self) -> str:
        return self.raw["content"]["bundle_hash"]

    @property
    def engine_version(self) -> str:
        return self.raw["content"]["engine_version"]

    @property
    def claims(self) -> tuple[ClaimOutcome, ...]:
        return tuple(
            ClaimOutcome(c["claim_id"], c["decision"], tuple(c["reasons"]))
            for c in self.raw["content"]["outcome"]["claims"]
        )

    @property
    def reasons(self) -> list[str]:
        """Every non-PASS claim, as ``'<claim>: <reason>'`` lines."""
        return [f"{c.claim_id}: {r}" for c in self.claims if c.decision != "PASS" for r in c.reasons]

    @property
    def evidence(self) -> tuple[EvidenceItem, ...]:
        items = []
        for e in self.raw["content"]["graph"]["evidence"]:
            receipt = e.get("receipt", {})
            span = receipt.get("source_span")
            items.append(
                EvidenceItem(
                    verifier_id=e["verifier_id"],
                    verifier_version=e["verifier_version"],
                    claim_id=e["claim_id"],
                    result=e["result"],
                    score=float(e["score"]),
                    confidence=float(e["confidence"]),
                    determinism=e["determinism"]["class"],
                    rationale=e["rationale"],
                    source_id=receipt.get("source_id"),
                    source_span=(span["start"], span["end"]) if span else None,
                    source_text=receipt.get("source_text"),
                    notes=tuple(receipt.get("notes", [])),
                )
            )
        return tuple(items)

    @property
    def verifiers(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.raw["content"]["graph"]["verifiers"])

    @property
    def regulatory_mapping(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.raw["content"]["outcome"]["regulatory_mapping"])

    @property
    def excluded_verifiers(self) -> tuple[tuple[str, str], ...]:
        return tuple(tuple(x) for x in self.raw["content"]["outcome"]["excluded_verifiers"])

    # ---- serialisation -----------------------------------------------------------
    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.raw, ensure_ascii=False, indent=indent, sort_keys=indent is None, separators=(",", ":") if indent is None else None)

    @classmethod
    def from_json(cls, text: str) -> Record:
        return cls(json.loads(text))

    def append_to(self, path: str | Path) -> None:
        """Append one canonical JSON line to an append-only log."""
        with Path(path).open("a", encoding="utf-8") as f:
            f.write(self.to_json() + "\n")

    @classmethod
    def read_log(cls, path: str | Path) -> list[Record]:
        text = Path(path).read_text(encoding="utf-8")
        return [cls.from_json(line) for line in text.splitlines() if line.strip()]

    # ---- verification ------------------------------------------------------------
    def verify(self) -> None:
        """Recompute content hash, record hash and Ed25519 signature. Offline."""
        Record.verify_chain([self])

    @staticmethod
    def verify_chain(records: Iterable[Record]) -> int:
        """Verify every record and every link. Returns the count; raises IntegrityError."""
        text = "\n".join(r.to_json() for r in records)
        try:
            return _engine.record_verify(text)
        except RuntimeError as e:
            raise IntegrityError(str(e)) from None

    def report(self) -> str:
        """One line per claim a human should look at."""
        lines = [f"{self.decision}  policy={self.policy_id}  record={self.record_id}"]
        for e in self.evidence:
            if e.result in ("contradicted", "unsupported"):
                where = f"  nearest in {e.source_id}: {e.source_text!r}" if e.source_text else ""
                lines.append(f"  {e.claim_id:<4} {e.verifier_id:<24} {e.result:<13} {e.score:.2f}{where}")
        return "\n".join(lines)
