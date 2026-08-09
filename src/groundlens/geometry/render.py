"""Plain-language rendering for geometric scores.

In 1.x this was ``groundlens.check(score)``. That name now belongs to the
product entry point, :func:`groundlens.check`, which checks an answer against
evidence and a rule pack. The renderer moved here rather than being deleted,
because it is still the single source of truth for how an SGI or DGI result is
worded, and because a 1.x caller needs somewhere to land.

This module is part of the optional geometry surface. It is not exported from
the top-level package.

Example:
    >>> from groundlens import compute_sgi                 # doctest: +SKIP
    >>> from groundlens.geometry.render import render_check  # doctest: +SKIP
    >>> render_check(compute_sgi(question=q, context=c, response=r)).render()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from groundlens.check import Check, check_for_dgi, check_for_sgi
from groundlens.score import DGIResult, SGIResult

if TYPE_CHECKING:  # pragma: no cover - typing only
    from groundlens.score import GroundlensScore

__all__ = ["render_check"]


def render_check(result: SGIResult | DGIResult | GroundlensScore) -> Check:
    """Render any geometric result as a plain-language check.

    Args:
        result: An :class:`~groundlens.score.SGIResult`, a
            :class:`~groundlens.score.DGIResult`, or a
            :class:`~groundlens.score.GroundlensScore` carrying either.

    Returns:
        The :class:`~groundlens.check.Check` for that result. The wording is
        identical to what the docs and the MCP servers show, because they
        render from this same function.

    Raises:
        TypeError: If ``result`` is not a geometric result. This most often
            means a 1.x call site reached here with a v2 ``Result``, which is
            already plain language and needs no rendering.
    """
    if isinstance(result, SGIResult):
        return check_for_sgi(result)
    if isinstance(result, DGIResult):
        return check_for_dgi(result)

    inner = getattr(result, "sgi", None) or getattr(result, "dgi", None)
    if isinstance(inner, SGIResult):
        return check_for_sgi(inner)
    if isinstance(inner, DGIResult):
        return check_for_dgi(inner)

    msg = (
        f"render_check() takes a geometric result (SGIResult, DGIResult or a "
        f"GroundlensScore carrying one), got {type(result).__name__}. "
        "If this is a v2 groundlens.check() Result, read its .decision and "
        ".findings directly; they are already plain language."
    )
    raise TypeError(msg)
