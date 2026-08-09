"""Optional geometry surface. Not required to use groundlens.

The geometric scores SGI and DGI were the product in 1.x. They are not the
product in 2.x. They remain here as an optional signal for research and for
routing, behind the ``geometry`` extra::

    pip install "groundlens[geometry]"

Nothing in the control path imports this package, and ``import groundlens``
does not import it either. That is what keeps the default install free of
numpy, torch and a model download.

See ``MIGRATING.md`` for the 1.x mapping.
"""

from __future__ import annotations

__all__ = ["render"]
