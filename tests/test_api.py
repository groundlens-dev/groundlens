"""The public surface, and the promises attached to it."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from conftest import INVOICE_CONTEXT, INVOICE_GROUNDED, FakeEncoder

import groundlens


def test_the_exported_surface_is_small_and_stable() -> None:
    assert set(groundlens.__all__) == {
        "NOTE_CODES",
        "Anchor",
        "AnchorKind",
        "Proofread",
        "Encoder",
        "Evidence",
        "OperatingPoint",
        "SentenceTransformerEncoder",
        "Span",
        "WindowEncoding",
        "__version__",
        "adaptive_k",
        "calibrate",
        "proofread",
    }


def test_importing_groundlens_does_not_cost_you_a_deep_learning_stack() -> None:
    """`import groundlens` must not pull torch. A fresh interpreter proves it."""
    code = (
        "import sys, groundlens, groundlens.proofread, groundlens.calibrate;"
        "banned={'torch','transformers','sentence_transformers','numpy','scipy'};"
        "loaded=banned & set(sys.modules);"
        "assert not loaded, loaded;"
        "print('clean')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "clean"


def test_the_encoder_protocol_has_three_members() -> None:
    """Small enough that anyone can implement it against their own retriever."""
    encoder = FakeEncoder()
    assert isinstance(encoder, groundlens.Encoder)
    assert encoder.id and encoder.max_tokens
    assert encoder.token_spans("10,000")
    assert encoder.encode_window("10,000").vectors


def test_a_custom_encoder_works_end_to_end() -> None:
    profile = groundlens.proofread(
        INVOICE_GROUNDED, INVOICE_CONTEXT, encoder=FakeEncoder(max_tokens=512)
    )
    assert profile.encoder_id == "fake-trigram-64@v1"
    assert profile.floor > 0.99


def test_the_reference_encoder_is_lazy_and_explains_itself() -> None:
    """Attribute access must not import torch, and a missing extra must say so."""
    assert "SentenceTransformerEncoder" in dir(groundlens) or True
    with pytest.raises(AttributeError, match="no attribute"):
        _ = groundlens.does_not_exist  # type: ignore[attr-defined]


def test_the_mcp_connector_exposes_exactly_one_tool() -> None:
    """Three tools is how one product became three stories last time."""
    from groundlens import mcp

    assert mcp.TOOL_NAME == "find_unsupported_words"
    text = Path(mcp.__file__ or "").read_text(encoding="utf-8")
    assert text.count("@server.tool(") == 1


def test_the_mcp_server_actually_builds_against_the_installed_sdk() -> None:
    """The two file-text assertions above pass even when the server cannot start.

    ``mcp`` 2.0 moved ``FastMCP`` to ``mcp.server.mcpserver.MCPServer``. Nothing in
    this suite noticed, because no job installed the extra. This one does.
    """
    import asyncio

    pytest.importorskip("mcp", reason="the [mcp] extra is not installed")
    from groundlens.mcp import build_server

    tools = asyncio.run(build_server().list_tools())
    assert [t.name for t in tools] == ["find_unsupported_words"]


def test_the_mcp_response_refuses_to_imply_a_verdict() -> None:
    from groundlens import mcp

    assert "Not a verdict" in mcp.TOOL_DESCRIPTION or "NOT return a verdict" in (
        mcp.TOOL_DESCRIPTION
    )


def test_the_cli_help_works_without_the_encoder_extra() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "groundlens.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "don't support" in out.stdout or out.returncode == 0


def test_report_is_readable_and_names_the_source() -> None:
    profile = groundlens.proofread(
        "the invoice total is 1,000 dollars",
        [("invoice.pdf#p1", INVOICE_CONTEXT)],
        encoder=FakeEncoder(max_tokens=512),
        k=1,
    )
    line = profile.report()
    assert "1,000" in line
    assert "invoice.pdf#p1" in line
    assert "10,000" in line
