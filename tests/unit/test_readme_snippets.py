"""Every Python snippet in README.md is executed against the real API.

Three reviewers read this repo cold and all three copied the README's examples
into a shell. All three hit `TypeError` or `ValueError`. The broken snippets,
not the maths, were what stopped them trusting the careful parts.

A first version of this file walked the AST and checked signatures. A reviewer
sabotaged the README ten ways and it still printed `37 passed`, because
AST-walking skips chained calls (`Cls(...).method(...)`), methods on local
objects, and attribute access entirely. That is most of a README.

So this runs the code. The README is read the way a reader reads it: the blocks
are executed in order, in one namespace, from a working directory that looks
like a checkout of this repository, with sockets blocked. A block is only
allowed to use names the blocks above it defined. If a snippet raises, the test
fails and prints the snippet.

That catches, by construction: wrong keyword, wrong positional, wrong method
name, invalid enum value, a field that does not exist on the result, and a
result that cannot be serialised into the audit log. That is every class of
error the reviewers found, and several they did not.

The claim tests below are the other half. A snippet that runs can still sit
under prose that is wrong, and the prose is what a buyer reads.
"""

from __future__ import annotations

import pathlib
import re
import textwrap

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
README = REPO / "README.md"

#: Blocks that cannot run here, and why. Every entry is a snippet nobody is
#: checking, so keep this list short and justified.
SKIP_CONTAINS = {
    "groundlens.verify": "loads a generative model; covered by tests/verify/",
}

#: The README is three examples: the first check, loading a pack, and the audit
#: log. The floor is not decoration. It is here so that gutting the examples --
#: the cheapest way to make this whole file pass -- fails loudly instead.
EXPECTED_BLOCKS = 3


def _python_blocks() -> list[str]:
    text = README.read_text(encoding="utf-8")
    blocks = re.findall(r"^```python\n(.*?)^```", text, re.M | re.S)
    assert len(blocks) >= EXPECTED_BLOCKS, (
        f"README.md has {len(blocks)} python blocks, expected at least "
        f"{EXPECTED_BLOCKS} (the first check, loading a pack, the audit log). "
        "Deleting an example is a way to make this file pass without fixing "
        "anything; if an example is genuinely gone for good, lower "
        "EXPECTED_BLOCKS in the same commit and say why."
    )
    return blocks


@pytest.fixture(autouse=True)
def _sandbox(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    """Run the README from a throwaway copy of a checkout, offline.

    The pack example loads ``packs/eu-retail-banking/pack.yaml`` by relative
    path, which is what a reader in a clone has. Linking the real directory in
    means the test also fails if that file is moved or renamed. Everything the
    snippets write (``audit.db``) lands in ``tmp_path`` and not in the tree.
    """
    import socket

    (tmp_path / "packs").symlink_to(REPO / "packs", target_is_directory=True)

    def _blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("a README snippet tried to open a socket")

    monkeypatch.setattr(socket.socket, "connect", _blocked, raising=False)
    monkeypatch.chdir(tmp_path)


def _ids(block: str) -> str:
    for line in block.strip().split("\n"):
        if line.strip() and not line.startswith("#"):
            return line[:56]
    return block[:56]


@pytest.mark.parametrize("index", range(len(_python_blocks())), ids=[0, 1, 2])
def test_readme_snippet_runs(index: int) -> None:
    """Run every block up to and including this one. Any exception is a bug.

    The blocks are cumulative: the audit example uses the ``result`` the first
    example produced. Executing each block on its own would need a fixture
    supplying fake values, and a fixture that supplies ``result`` is a fixture
    that hides the README saying ``result.audit.counts`` when the field is
    something else. Replaying the prefix costs milliseconds and tests the
    README as written.
    """
    blocks = _python_blocks()
    namespace: dict[str, object] = {"__name__": "__readme__"}

    for position, block in enumerate(blocks[: index + 1]):
        if any(marker in block for marker in SKIP_CONTAINS):
            why = next(w for m, w in SKIP_CONTAINS.items() if m in block)
            pytest.skip(why)
        try:
            exec(compile(textwrap.dedent(block), "README.md", "exec"), namespace)
        except Exception as exc:
            pytest.fail(
                f"README python block {position} raised {type(exc).__name__}: {exc}\n\n"
                f"--- the snippet ---\n{block}"
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
        """Every `groundlens <verb> --flag` in the README must be real.

        The README currently documents no CLI at all, so this passes over an
        empty set. It stays because the CLI is where documentation rots
        fastest: `benchmark` and `canaries` were both added after the prose
        that described the tool was written.
        """
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
        # Command lines in fenced blocks and in inline code spans alike, minus
        # `pip install groundlens`, which is not an invocation.
        invocations = re.findall(r"(?:^|[`$]\s*)groundlens ([a-z][-\w]*)([^\n`]*)", text, re.M)
        for verb, rest in invocations:
            assert verb in subs, (
                f"README documents `groundlens {verb}`, which does not exist. "
                f"Real subcommands: {sorted(subs)}"
            )
            real_flags = {opt for a in subs[verb]._actions for opt in a.option_strings}
            for flag in (token for token in rest.split() if token.startswith("--")):
                assert flag in real_flags, (
                    f"README passes {flag} to `groundlens {verb}`, which does not accept it. "
                    f"Real flags: {sorted(real_flags)}"
                )

    def test_two_decisions_and_no_score_is_explained(self) -> None:
        """The v2 promise is two decisions and no dial. Say it, and mean it.

        This replaces the old `flagged` versus `escalate` test. There is no
        review band any more, so there is no band to mis-ship; what a reader
        can still get wrong is expecting a number they can compare, tune, or
        average. The README has to name both decisions and say there is no
        score, and the code has to agree that those are the only two.
        """
        from groundlens.types import Decision

        text = README.read_text(encoding="utf-8")
        assert {d.value for d in Decision} == {"clear", "escalate"}, (
            "Decision gained or lost a member; the README's 'two decisions and "
            "nothing else' is now a false claim and needs rewriting"
        )
        for value in ("clear", "escalate"):
            assert value in text, f"README never names the {value!r} decision"
        assert re.search(r"no score,? (and )?no confidence and no threshold", text), (
            "README must state that there is no score, no confidence and no "
            "threshold. A number between zero and one is the thing every "
            "competitor ships and the thing this design refuses."
        )

    def test_documented_kinds_and_assertions_match_the_code(self) -> None:
        """Two closed lists in the prose, two closed tuples in the code.

        This replaces the old label-polarity test, which guarded the `1 =
        ungrounded` convention for calibration labels. That convention is gone
        with the scorer: there are no labels, so there is no polarity to
        invert. What survives is the failure mode behind it -- prose stating a
        fixed set that the code has quietly changed underneath.
        """
        from groundlens.packs.loader import ASSERT_KINDS
        from groundlens.types import FactKind

        text = README.read_text(encoding="utf-8")

        assert len(ASSERT_KINDS) == 8, (
            f"the pack contract now has {len(ASSERT_KINDS)} assertions; the "
            "README says 'Eight assertions are supported and no others'"
        )
        for name in ASSERT_KINDS:
            assert f"`{name}`" in text, f"README omits the `{name}` assertion"

        kinds = [k.value for k in FactKind]
        assert len(kinds) == 8, (
            f"extractors now produce {len(kinds)} kinds of statement; the "
            "README says 'Groundlens reads eight kinds of statement'"
        )
        for kind in kinds:
            assert re.search(rf"^\| {kind}\b", text, re.M | re.I), (
                f"README's 'What it checks' table has no row for {kind!r}"
            )

    def test_no_dead_api_is_documented(self) -> None:
        """`decision.allowed` shipped for weeks. The field is `write_to_state`.

        The geometry names are on the list for a different reason. They are
        real functions behind the `[geometry]` extra, and putting them back in
        the README as if they were the default path is how the pivot gets
        undone one paragraph at a time. Document them under docs/research.
        """
        text = README.read_text(encoding="utf-8")
        for dead, why in {
            "decision.allowed": "the field is `write_to_state`",
            "log.append(": "the method is `record` / `record_v2`",
            "fit_thresholds(pairs=": "removed with the scorer",
            'on_reject="block"': "never existed",
            "compute_sgi": "geometry is optional and is not the entry point",
            "compute_dgi": "geometry is optional and is not the entry point",
            "BENCHMARKS.md": "no such file exists in this repository",
        }.items():
            assert dead not in text, f"README uses {dead!r}: {why}"


# ── The number rule ─────────────────────────────────────────────────────────

#: Metric names. A number beside one of these is a performance claim whatever
#: sentence it is wearing.
_METRIC_WORD = (
    r"(?:auroc|au-roc|auprc|\bauc\b|\broc\b|\brecall\b|\bprecision\b|\bf1\b|"
    r"\baccuracy\b|false[ -](?:alarm|positive|negative)|\bfpr\b|\btpr\b|"
    r"sensitivity|specificity|\bdetect\w*|hit rate|error rate|"
    r"\bp@\d|\br@\d)"
)

#: 0.84, 1.00, 0.8, .93, 84%, 12.5%. The lookarounds are what keep version
#: strings (1.2.0), arXiv ids (2512.13771) and amounts (45,00 EUR) out.
_METRIC_NUMBER = r"(?:(?<![\w.])[01]?\.\d+(?![\d.])|(?<![\w.])\d{1,3}(?:\.\d+)?\s?%)"

_RULE = (
    "Rule: no performance number lives in README.md. A number that has been "
    "through the authorship and length controls belongs in docs/benchmarks/ "
    "next to the run that produced it, and the README links to it. A number "
    "that has not been through them does not ship at all. The 0.84 / 0.93 / "
    "1.00 recall at 0.00 false alarms table was in this file for months with "
    "no committed provenance, and it is the single claim most likely to be "
    "checked by someone deciding whether to trust the rest."
)


def _performance_claims(text: str) -> list[str]:
    """Return every fragment of ``text`` that reads as a performance claim."""
    hits: list[str] = []
    near = re.compile(
        rf"(?:{_METRIC_WORD}[^\n]{{0,40}}?{_METRIC_NUMBER}"
        rf"|{_METRIC_NUMBER}[^\n]{{0,40}}?{_METRIC_WORD})",
        re.I,
    )
    hits += [m.group(0).strip() for m in near.finditer(text)]
    # A results table needs no metric word: the header carries it and the
    # header is usually the row above.
    row = re.compile(rf"^\|.*{_METRIC_NUMBER}.*$", re.M)
    hits += [m.group(0).strip() for m in row.finditer(text)]
    return hits


def test_no_unqualified_performance_claim_in_the_readme() -> None:
    """The README must not state a detection number. Anywhere, in any shape."""
    hits = _performance_claims(README.read_text(encoding="utf-8"))
    assert not hits, "README states performance numbers:\n  " + "\n  ".join(hits) + "\n\n" + _RULE


def test_the_number_rule_catches_the_table_it_was_written_for() -> None:
    """A guard that never fires is not a guard.

    Every string below was in README.md or in a slide at some point. If a
    future tidy-up of the pattern stops matching them, the guard is decorative
    and this test says so before anyone relies on it.
    """
    for liability in (
        "| Confabulation | 0.84 | 0.93 | 1.00 |",
        "recall of 0.93 at 0.00 false alarms",
        "AUROC 0.8 on the held-out split",
        "detects 94% of hallucinations",
        "| model | accuracy |\n| t5 | .871 |",
    ):
        assert _performance_claims(liability), (
            f"the performance-claim guard no longer matches {liability!r}, "
            "which is exactly the kind of claim it exists to stop"
        )
