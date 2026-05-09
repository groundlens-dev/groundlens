"""Tests for groundlens._internal.csv_loader."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from groundlens._internal.csv_loader import _load_user_csv

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Comma-delimited CSV
# ---------------------------------------------------------------------------


class TestLoadUserCsvComma:
    """Test _load_user_csv with comma-delimited files."""

    def test_basic_comma_csv(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(
            "question,response\n"
            "What is Python?,Python is a programming language.\n"
            "What is 2+2?,The answer is 4.\n",
            encoding="utf-8",
        )
        pairs = _load_user_csv(str(csv_file))
        assert len(pairs) == 2
        assert pairs[0] == ("What is Python?", "Python is a programming language.")

    def test_answer_column_name(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(
            "question,answer\nWhat is X?,X is Y.\n",
            encoding="utf-8",
        )
        pairs = _load_user_csv(str(csv_file))
        assert len(pairs) == 1
        assert pairs[0][1] == "X is Y."

    def test_output_column_name(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(
            "question,output\nWhat is X?,X is Y.\n",
            encoding="utf-8",
        )
        pairs = _load_user_csv(str(csv_file))
        assert len(pairs) == 1

    def test_grounded_response_column_name(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(
            "question,grounded_response\nWhat is X?,X is Y.\n",
            encoding="utf-8",
        )
        pairs = _load_user_csv(str(csv_file))
        assert len(pairs) == 1

    def test_skips_empty_rows(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(
            "question,response\nWhat is X?,X is Y.\n,\n  ,  \nWhat is Z?,Z is W.\n",
            encoding="utf-8",
        )
        pairs = _load_user_csv(str(csv_file))
        assert len(pairs) == 2

    def test_extra_columns_ignored(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(
            "question,response,category,notes\nWhat is X?,X is Y.,science,verified\n",
            encoding="utf-8",
        )
        pairs = _load_user_csv(str(csv_file))
        assert len(pairs) == 1
        assert pairs[0] == ("What is X?", "X is Y.")


# ---------------------------------------------------------------------------
# Semicolon-delimited CSV
# ---------------------------------------------------------------------------


class TestLoadUserCsvSemicolon:
    """Test _load_user_csv with semicolon-delimited files."""

    def test_semicolon_delimiter(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(
            "question;response\n"
            "What is Python?;Python is a programming language.\n"
            "What is 2+2?;The answer is 4.\n",
            encoding="utf-8",
        )
        pairs = _load_user_csv(str(csv_file))
        assert len(pairs) == 2

    def test_semicolon_with_commas_in_values(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(
            "question;response\nWhat is Python?;Python is a language, created by Guido.\n",
            encoding="utf-8",
        )
        pairs = _load_user_csv(str(csv_file))
        assert len(pairs) == 1
        assert "created by Guido" in pairs[0][1]


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestLoadUserCsvErrors:
    """Test error handling in _load_user_csv."""

    def test_missing_question_column_raises_value_error(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text(
            "prompt,response\nWhat is X?,X is Y.\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="question"):
            _load_user_csv(str(csv_file))

    def test_missing_response_column_raises_value_error(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text(
            "question,text\nWhat is X?,X is Y.\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="response column"):
            _load_user_csv(str(csv_file))

    def test_empty_file_raises_value_error(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text(
            "question,response\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="No valid pairs"):
            _load_user_csv(str(csv_file))

    def test_file_not_found_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            _load_user_csv("/nonexistent/path/data.csv")

    def test_completely_empty_file(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "blank.csv"
        csv_file.write_text("", encoding="utf-8")
        with pytest.raises((ValueError, StopIteration)):
            _load_user_csv(str(csv_file))

    def test_whitespace_only_values_treated_as_empty(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(
            "question,response\n   ,   \n   ,Some answer\nSome question,   \n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="No valid pairs"):
            _load_user_csv(str(csv_file))
