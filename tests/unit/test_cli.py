"""Unit tests for groundlens CLI — parser and command handlers.

All tests mock the scoring / calibration functions so no embedding
model is loaded.  Tests exercise argument parsing, output formatting,
error handling, and edge cases.

Note: CLI handlers use deferred imports (``from groundlens.evaluate import
evaluate`` inside function bodies).  We patch at the source module via
``patch.object`` on the explicitly imported ``groundlens.evaluate`` module.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path  # noqa: TC003
from unittest.mock import patch

import numpy as np
import pytest

import groundlens.calibrate
import groundlens.evaluate  # noqa: F401

_eval_mod = sys.modules["groundlens.evaluate"]
_cal_mod = sys.modules["groundlens.calibrate"]

from groundlens.cli.main import (  # noqa: E402
    _build_parser,
    _cmd_calibrate,
    _cmd_check,
    _cmd_doctor,
    _cmd_evaluate,
    main,
)
from groundlens.score import DGIResult, GroundlensScore, SGIResult  # noqa: E402

# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParser:
    """Verify argparse configuration."""

    def test_parser_creates_successfully(self) -> None:
        parser = _build_parser()
        assert parser is not None

    def test_check_subcommand_parsed(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            ["check", "--question", "Q?", "--response", "A.", "--context", "C."]
        )
        assert args.command == "check"
        assert args.question == "Q?"
        assert args.response == "A."
        assert args.context == "C."

    def test_evaluate_subcommand_parsed(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["evaluate", "input.csv", "--output", "out.csv"])
        assert args.command == "evaluate"
        assert args.input_csv == "input.csv"
        assert args.output == "out.csv"

    def test_calibrate_subcommand_parsed(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["calibrate", "--pairs", "pairs.csv", "--output", "cal.json"])
        assert args.command == "calibrate"
        assert args.pairs == "pairs.csv"

    def test_doctor_subcommand_parsed(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["doctor"])
        assert args.command == "doctor"

    def test_benchmark_subcommand_parsed(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["benchmark"])
        assert args.command == "benchmark"

    def test_default_model(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["check", "--question", "Q?", "--response", "A."])
        assert args.model == "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# _cmd_check
# ---------------------------------------------------------------------------

_MOCK_SCORE = GroundlensScore(
    value=1.25,
    normalized=0.62,
    flagged=False,
    method="sgi",
    explanation="SGI=1.250 — strong context engagement (pass)",
    detail=SGIResult(value=1.25, normalized=0.62, flagged=False, q_dist=0.8, ctx_dist=0.64),
)


class TestCmdCheck:
    """Test the check subcommand handler."""

    @patch.object(_eval_mod, "evaluate", return_value=_MOCK_SCORE)
    def test_check_prints_score(self, mock_eval, capsys) -> None:
        parser = _build_parser()
        args = parser.parse_args(["check", "--question", "Q?", "--response", "A."])
        _cmd_check(args)

        captured = capsys.readouterr().out
        assert "1.2500" in captured
        assert "0.6200" in captured
        assert "False" in captured
        assert "sgi" in captured


# ---------------------------------------------------------------------------
# _cmd_evaluate
# ---------------------------------------------------------------------------


class TestCmdEvaluate:
    """Test the evaluate subcommand handler."""

    def _write_csv(self, path: Path, rows: list[dict[str, str]]) -> None:
        fieldnames = list(rows[0].keys()) if rows else ["question", "response"]
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @patch.object(_eval_mod, "evaluate", return_value=_MOCK_SCORE)
    def test_evaluate_writes_output(self, mock_eval, tmp_path) -> None:
        inp = tmp_path / "input.csv"
        out = tmp_path / "output.csv"
        self._write_csv(inp, [{"question": "Q?", "response": "A.", "context": "C."}])

        parser = _build_parser()
        args = parser.parse_args(["evaluate", str(inp), "--output", str(out)])
        _cmd_evaluate(args)

        assert out.exists()
        with out.open(encoding="utf-8") as fh:
            reader = list(csv.DictReader(fh))
        assert len(reader) == 1
        assert reader[0]["groundlens_method"] == "sgi"
        assert reader[0]["groundlens_flagged"] == "False"

    def test_evaluate_missing_file_exits(self, tmp_path) -> None:
        parser = _build_parser()
        args = parser.parse_args(["evaluate", str(tmp_path / "nope.csv"), "--output", "out.csv"])
        with pytest.raises(SystemExit, match="1"):
            _cmd_evaluate(args)

    def test_evaluate_empty_csv_exits(self, tmp_path) -> None:
        inp = tmp_path / "empty.csv"
        inp.write_text("question,response\n", encoding="utf-8")

        parser = _build_parser()
        args = parser.parse_args(["evaluate", str(inp), "--output", "out.csv"])
        with pytest.raises(SystemExit, match="1"):
            _cmd_evaluate(args)

    @patch.object(_eval_mod, "evaluate", return_value=_MOCK_SCORE)
    def test_evaluate_skips_rows_missing_question(self, mock_eval, tmp_path, capsys) -> None:
        inp = tmp_path / "input.csv"
        self._write_csv(
            inp,
            [
                {"question": "", "response": "A."},
                {"question": "Q?", "response": "A2."},
            ],
        )
        out = tmp_path / "output.csv"

        parser = _build_parser()
        args = parser.parse_args(["evaluate", str(inp), "--output", str(out)])
        _cmd_evaluate(args)

        with out.open(encoding="utf-8") as fh:
            reader = list(csv.DictReader(fh))
        # Only the row with a question should be written
        assert len(reader) == 1


# ---------------------------------------------------------------------------
# main() no-command
# ---------------------------------------------------------------------------


class TestCmdCalibrate:
    """Test the calibrate subcommand handler."""

    def test_calibrate_missing_file_exits(self, tmp_path) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            ["calibrate", "--pairs", str(tmp_path / "nope.csv"), "--output", "out.json"]
        )
        with pytest.raises(SystemExit, match="1"):
            _cmd_calibrate(args)

    @patch.object(_cal_mod, "calibrate")
    def test_calibrate_happy_path(self, mock_cal, tmp_path, capsys) -> None:
        from groundlens.calibrate import CalibrationResult

        mock_result = CalibrationResult(
            model="test",
            n_pairs=20,
            embedding_dim=384,
            mu_hat=np.zeros(384, dtype=np.float32),
            concentration=15.0,
        )
        mock_cal.return_value = mock_result

        pairs_file = tmp_path / "pairs.csv"
        pairs_file.write_text("question,response\nQ?,A.\n", encoding="utf-8")
        out_file = tmp_path / "cal.json"

        parser = _build_parser()
        args = parser.parse_args(
            ["calibrate", "--pairs", str(pairs_file), "--output", str(out_file)]
        )
        _cmd_calibrate(args)

        captured = capsys.readouterr().out
        assert "Calibration complete" in captured
        assert "20" in captured


# ---------------------------------------------------------------------------
# _cmd_doctor (partial — test structure, not every import)
# ---------------------------------------------------------------------------


class TestCmdDoctor:
    """Test the doctor subcommand handler."""

    @patch("groundlens._internal.embeddings.encode_texts")
    @patch.object(_eval_mod, "evaluate")
    def test_doctor_runs_without_crash(self, mock_eval, mock_encode, capsys) -> None:
        """Doctor should run to completion when all imports succeed."""
        mock_encode.return_value = (
            np.random.default_rng(0).standard_normal((1, 384)).astype(np.float32)
        )

        mock_sgi = SGIResult(value=1.2, normalized=0.6, flagged=False, q_dist=0.8, ctx_dist=0.64)
        mock_dgi = DGIResult(value=0.4, normalized=0.7, flagged=False)
        mock_eval.side_effect = [
            GroundlensScore(
                value=1.2,
                normalized=0.6,
                flagged=False,
                method="sgi",
                explanation="ok",
                detail=mock_sgi,
            ),
            GroundlensScore(
                value=0.4,
                normalized=0.7,
                flagged=False,
                method="dgi",
                explanation="ok",
                detail=mock_dgi,
            ),
        ]

        parser = _build_parser()
        args = parser.parse_args(["doctor"])
        _cmd_doctor(args)

        captured = capsys.readouterr().out
        assert "groundlens doctor" in captured
        assert "Core dependencies" in captured


# ---------------------------------------------------------------------------
# main() dispatch
# ---------------------------------------------------------------------------


class TestMain:
    """Test top-level main() entry point."""

    def test_no_command_prints_help_and_exits(self) -> None:
        with patch("sys.argv", ["groundlens"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    @patch.object(_eval_mod, "evaluate", return_value=_MOCK_SCORE)
    def test_main_dispatches_check(self, mock_eval) -> None:
        with patch(
            "sys.argv",
            ["groundlens", "check", "--question", "Q?", "--response", "A."],
        ):
            main()
        mock_eval.assert_called_once()
