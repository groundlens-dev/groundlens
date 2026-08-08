"""Rule 1: no floating point in the decision path or anywhere in the record.

A float is not a number here, it is a liability. Two hosts with
different libm builds print ``0.1 + 0.2`` the same way but a
sufficiently long chain of arithmetic does not have to agree, and a
record that cannot be reproduced byte for byte is not evidence. So the
rule is absolute rather than careful: no float, at any depth, in any
form, in a record or in a result.

These tests walk the structures rather than checking the fields anyone
remembered to check, so a float added three layers down in a new nested
type six months from now still fails.
"""

from __future__ import annotations

import dataclasses
import json
from decimal import Decimal
from enum import Enum
from typing import Any

import pytest

from groundlens.audit_record import canonical_json, to_jsonable

from ._sample import build_sample_record, build_sample_result


def _walk(value: Any, path: str = "$") -> list[str]:
    """Yield a path for every float found anywhere inside ``value``."""
    offenders: list[str] = []

    if isinstance(value, bool):
        return offenders
    if isinstance(value, float):
        return [f"{path} is a float ({value!r})"]
    if isinstance(value, Decimal):
        # Decimal is fine as an intermediate but must never be serialised
        # raw, because json cannot encode it and str() of it is not
        # canonical. Flag it in serialised form only; see the caller.
        return offenders
    if isinstance(value, Enum):
        return _walk(value.value, f"{path}.value")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for f in dataclasses.fields(value):
            offenders += _walk(getattr(value, f.name), f"{path}.{f.name}")
        return offenders
    if isinstance(value, dict):
        for key, item in value.items():
            offenders += _walk(item, f"{path}[{key!r}]")
        return offenders
    if isinstance(value, (list, tuple, set, frozenset)):
        for index, item in enumerate(value):
            offenders += _walk(item, f"{path}[{index}]")
        return offenders

    return offenders


def test_record_object_contains_no_float() -> None:
    assert _walk(build_sample_record()) == []


def test_record_jsonable_contains_no_float() -> None:
    assert _walk(to_jsonable(build_sample_record())) == []


def test_result_object_contains_no_float() -> None:
    assert _walk(build_sample_result()) == []


def test_canonical_json_has_no_float_literal() -> None:
    """Parse the bytes back and refuse any token JSON would read as a float.

    This catches the case the object walk cannot: a value that is an int
    in Python but was rendered with an exponent or a decimal point by a
    hand-written serialiser.
    """
    blob = canonical_json(build_sample_record())

    def reject(token: str) -> float:
        pytest.fail(f"canonical JSON contains a float literal: {token!r}")

    json.loads(blob.decode("utf-8"), parse_float=reject)


def test_walker_actually_detects_a_float() -> None:
    """The walker is only worth having if it fails on a planted float."""
    planted = {"counts": {"nested": [{"score": 0.87}]}}
    assert _walk(planted) == ["$['counts']['nested'][0]['score'] is a float (0.87)"]


def test_no_score_field_anywhere_in_the_record() -> None:
    """A score would be a float in waiting. The contract has none."""
    blob = canonical_json(build_sample_record()).decode("utf-8")
    for forbidden in ('"score"', '"confidence"', '"probability"', '"threshold"'):
        assert forbidden not in blob
