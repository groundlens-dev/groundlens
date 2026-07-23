"""Deprecated module path; the pipeline lives in :mod:`groundlens.verify.pipeline`.

Kept as a thin re-export so any code importing this path keeps working. Import
from :mod:`groundlens.verify` (``two_stage``, ``TwoStageResult``) or from
:mod:`groundlens.verify.pipeline` instead.
"""

from __future__ import annotations

from groundlens.verify.pipeline import TwoStageResult, two_stage

__all__ = ["TwoStageResult", "two_stage"]
