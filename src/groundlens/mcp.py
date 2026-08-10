"""The connector. One tool.

The previous version of this server advertised three tools -- ``groundlens_check``,
``groundlens_sgi``, ``groundlens_dgi`` -- and that is how one product turned into
three stories before anyone had installed it. If a second tool ever looks
necessary here, the product has stopped being one thing.

    pip install "groundlens[encoder,mcp]"
    python -m groundlens.mcp
"""

from __future__ import annotations

from typing import Any

TOOL_NAME = "find_unsupported_words"

TOOL_DESCRIPTION = """\
Given an answer and the sources it was supposedly drawn from, return the words \
the sources least support, each paired with the closest thing in the sources.

Numbers are checked by arithmetic, not by meaning: a value is present or it is \
not, and formatting is normalised first, so 10,000 and 10000 and $10,000 are one \
number. Words are checked by embedding similarity.

Returns evidence for a human to judge. It does NOT return a verdict on whether \
the answer is hallucinated, and there is no threshold to compare the score to. \
Report the weakest anchors and let the reader decide."""


def build_server() -> Any:
    """Construct the MCP server. Imports are local so the core stays dependency-free."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - depends on install extras
        msg = "The MCP connector needs:  pip install 'groundlens[encoder,mcp]'"
        raise ImportError(msg) from exc

    from groundlens._encode import SentenceTransformerEncoder
    from groundlens.score import score

    server = FastMCP("groundlens")
    encoder: list[SentenceTransformerEncoder] = []

    def _encoder() -> SentenceTransformerEncoder:
        if not encoder:
            encoder.append(SentenceTransformerEncoder())
        return encoder[0]

    @server.tool(name=TOOL_NAME, description=TOOL_DESCRIPTION)
    def find_unsupported_words(
        answer: str,
        sources: list[dict[str, str]],
        k: int = 4,
        locale: str = "und",
    ) -> dict[str, Any]:
        """
        Args:
            answer: the model output to check.
            sources: ``[{"id": "policy.pdf#p3", "text": "..."}]``. Ids appear in
                the findings, so a reviewer knows which document to open.
            k: how many of the weakest anchors to return.
            locale: how these documents write numbers -- ``es`` reads 1.234 as
                1234, ``en`` reads it as 1.234. ``und`` keeps both readings.
        """
        evidence = [(s.get("id") or f"ctx-{i}", s.get("text", "")) for i, s in enumerate(sources)]
        profile = score(answer, evidence, encoder=_encoder(), k=k, locale=locale)
        return {
            "weakest_anchors": [
                {
                    "word": a.text,
                    "support": round(a.support, 4),
                    "checked_by": "arithmetic" if a.kind == "numeral" else "meaning",
                    "closest_in_sources": a.evidence_text,
                    "source_id": a.evidence_id,
                    "notes": list(a.notes),
                }
                for a in profile.weakest
            ],
            "score": round(profile.score, 4),
            "n_scored": profile.n_scored,
            "encoder_id": profile.encoder_id,
            "profile_sha256": profile.profile_sha256,
            "warnings": list(profile.warnings),
            "how_to_read_this": (
                "Not a verdict. support 0.00 on a number means that value is absent "
                "from the sources; on a word it means no lexical anchor was found, "
                "which is ordinary in honest paraphrase. There is no threshold: no "
                "published method reaches a usable false-positive rate at high recall."
            ),
        }

    return server


def main() -> None:  # pragma: no cover - process entry point
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
