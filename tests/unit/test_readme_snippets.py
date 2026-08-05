"""Every Python snippet in README.md is executed against the real API.

Three reviewers read this repo cold and all three copied the README's examples
into a shell. All three hit `TypeError` or `ValueError`. The broken snippets,
not the maths, were what stopped them trusting the careful parts.

A first version of this file walked the AST and checked signatures. A reviewer
sabotaged the README ten ways and it still printed `37 passed`, because
AST-walking skips chained calls (`Cls(...).method(...)`), methods on local
objects, and attribute access entirely. That is most of a README.

So this runs the code. Every ```python block is executed with a stub encoder
installed, real placeholder values bound, and sockets blocked. If a snippet
raises, the test fails and prints the snippet.

That catches, by construction: wrong keyword, wrong positional, wrong method
name, invalid enum value, and a field that does not exist on the result. That
is every class of error the reviewers found, and several they did not.
"""

from __future__ import annotations

import pathlib
import re
import textwrap

import numpy as np
import pytest

README = pathlib.Path(__file__).resolve().parents[2] / "README.md"

#: Blocks that cannot run here, and why. Every entry is a snippet nobody is
#: checking, so keep this list short and justified.
SKIP_CONTAINS = {
    "groundlens.verify": "loads a generative model; covered by tests/verify/",
    "@software{": "bibtex, not python",
}

_DIM = 32


def _stub_encoder(texts: list[str]) -> np.ndarray:
    """Deterministic bag-of-characters embedding. No network, no torch.

    Real enough that the geometry produces finite, ordered scores; cheap
    enough that the whole README runs in milliseconds.
    """
    out = np.zeros((len(texts), _DIM), dtype=np.float64)
    for i, text in enumerate(texts):
        for j, ch in enumerate(text.lower()):
            out[i, (ord(ch) + j % 3) % _DIM] += 1.0
        out[i] += 1e-3
    return out


def _python_blocks() -> list[str]:
    text = README.read_text(encoding="utf-8")
    blocks = re.findall(r"^```python\n(.*?)^```", text, re.M | re.S)
    assert len(blocks) >= 8, f"expected the README to still have its examples, found {len(blocks)}"
    return blocks


def _placeholders() -> dict[str, object]:
    """The variables the README expects its reader to already have."""
    question = "How long is the quarantine period for a returned item?"
    context = (
        "Returned items enter a 14-day quarantine bay. A floor supervisor inspects "
        "the item against the packing slip and signs the inspection line before it "
        "is restocked."
    )
    answer = (
        "A returned item sits in quarantine for 14 days, and a floor supervisor "
        "signs the inspection line before it is restocked."
    )
    return {
        "question": question,
        "context": context,
        "source_document": context,
        "answer": answer,
        "from_source": answer,
        "not_from_source": "Items are restocked the same afternoon with no quarantine.",
        "chunks": [context, "An unrelated passage about shipping labels."],
        "metadata": {},
        "my_grounded_pairs": [(question, answer)] * 4,
        "items": [{"question": question, "response": answer, "context": context}],
        "q1": question,
        "q2": question,
        "r1": answer,
        "r2": answer,
        "src1": context,
        "examples": [
            {"question": question, "response": answer, "context": context, "label": 0},
            {"question": question, "response": "Invented.", "context": context, "label": 1},
        ],
    }


@pytest.fixture(autouse=True)
def _stubbed(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    """Install the stub encoder and make a real download impossible."""
    import socket

    import groundlens
    from groundlens.dgi import reset_calibration_cache

    groundlens.set_default_encoder(_stub_encoder)
    reset_calibration_cache()

    def _blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("a README snippet tried to open a socket")

    monkeypatch.setattr(socket.socket, "connect", _blocked, raising=False)
    monkeypatch.chdir(tmp_path)
    yield
    groundlens.set_default_encoder(None)
    reset_calibration_cache()


def _ids(block: str) -> str:
    for line in block.strip().split("\n"):
        if line.strip() and not line.startswith("#"):
            return line[:56]
    return block[:56]


@pytest.mark.parametrize("block", _python_blocks(), ids=_ids)
def test_readme_snippet_runs(block: str) -> None:
    """Execute the block. Any exception is a broken README."""
    for marker, why in SKIP_CONTAINS.items():
        if marker in block:
            pytest.skip(why)

    namespace: dict[str, object] = {"__name__": "__readme__"}
    namespace.update(_placeholders())

    try:
        exec(compile(textwrap.dedent(block), "README.md", "exec"), namespace)
    except Exception as exc:
        pytest.fail(
            f"README snippet raised {type(exc).__name__}: {exc}\n\n--- the snippet ---\n{block}"
        )


class TestReadmeClaims:
    """Specific claims a reviewer checked and found wrong. Keep them right."""

    def test_no_count_of_tools_is_claimed(self) -> None:
        """'Eight checks' was wrong three ways. Do not reintroduce any count."""
        text = README.read_text(encoding="utf-8").lower()
        words = r"(one|two|three|four|five|six|seven|eight|nine|ten|\d+)"
        for pattern in (
            rf"{words} checks for",
            rf"all {words} from the shell",
            rf"these {words} are",
        ):
            match = re.search(pattern, text)
            assert match is None, f"README claims a tool count: {match.group(0)!r}"

    def test_cli_verbs_and_flags_exist(self) -> None:
        """Every `groundlens <verb> --flag` in the README must be real."""
        import argparse

        from groundlens.cli.main import _build_parser

        text = README.read_text(encoding="utf-8")
        parser = _build_parser()
        subs = {
            name: sub
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
            for name, sub in action.choices.items()
        }
        for line in re.findall(r"^groundlens (.+)$", text, re.M):
            verb, *rest = line.split()
            assert verb in subs, f"README documents `groundlens {verb}`, which does not exist"
            real_flags = {opt for a in subs[verb]._actions for opt in a.option_strings}
            for flag in (token for token in rest if token.startswith("--")):
                assert flag in real_flags, (
                    f"README passes {flag} to `groundlens {verb}`, which does not accept it. "
                    f"Real flags: {sorted(real_flags)}"
                )

    def test_flagged_versus_escalate_is_explained(self) -> None:
        """All three reviewers would have shipped the review band as passes."""
        text = README.read_text(encoding="utf-8")
        assert "check(result).escalate" in text
        assert re.search(r"flagged.{0,200}hard cut", text, re.S), (
            "README must say that `flagged` is the hard cut and not the escalate set"
        )

    def test_label_polarity_is_stated_and_never_contradicted(self) -> None:
        """1 = ungrounded. Backwards fits inverted thresholds and never raises.

        Asserting the right string is not enough: a sabotage test showed the
        README can say both, with the wrong one in the prose a reader trusts
        and the right one in a code comment they skim past.
        """
        text = README.read_text(encoding="utf-8")
        assert "1 = ungrounded" in text, "README must state the label polarity"
        for wrong in ("1 = grounded", "1 means grounded", "label 1 = grounded"):
            assert wrong.lower() not in text.lower(), (
                f"README contradicts its own label polarity with {wrong!r}"
            )

    def test_no_dead_api_is_documented(self) -> None:
        """`decision.allowed` shipped for weeks. The field is `write_to_state`."""
        text = README.read_text(encoding="utf-8")
        for dead in (
            "decision.allowed",
            "log.append(",
            "fit_thresholds(pairs=",
            'on_reject="block"',
        ):
            assert dead not in text, f"README uses {dead!r}, which does not exist"
