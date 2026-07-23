"""Proof that the local scoring path opens no network connections.

Blocks every socket connection, then scores with a custom (in-memory) encoder.
If any part of local scoring tried to reach the network, the test fails. This is
the runnable evidence behind DATA_HANDLING.md: the deterministic core sends
nothing out.
"""

from __future__ import annotations

import socket
from typing import Any

import numpy as np

from groundlens import check, compute_dgi, compute_sgi
from groundlens.dgi import reset_calibration_cache


def _blocked(*_args: Any, **_kwargs: Any) -> None:
    raise AssertionError("network egress attempted during local scoring")


def _encoder(texts: list[str]) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.standard_normal((len(texts), 16)).astype(np.float32)


def test_local_scoring_opens_no_sockets(monkeypatch: Any) -> None:
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    reset_calibration_cache()

    sgi = compute_sgi(question="q", context="c", response="r", encoder=_encoder)
    dgi = compute_dgi(question="q", response="r", encoder=_encoder)

    assert check(sgi).level in {"ok", "review", "risk"}
    assert check(dgi).level in {"ok", "review", "risk"}
    reset_calibration_cache()
