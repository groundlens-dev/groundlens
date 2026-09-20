# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Sphinx configuration for the GroundLens documentation.

The API reference is generated from the docstrings in the ``groundlens``
Python package. The compiled Rust extension (``groundlens._engine``) is
mocked, so the docs build needs no Rust toolchain and no model bundle: it
reads the pure-Python sources on ``sys.path`` and renders their docstrings.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# The package lives at ../python/groundlens; put ../python on the path so
# `import groundlens` resolves during autodoc.
DOCS_DIR = Path(__file__).resolve().parent
REPO_ROOT = DOCS_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "python"))

# -- Project information ------------------------------------------------------

project = "GroundLens"
author = "Javier Marín"
copyright = "2026, Javier Marín"


def _read_version() -> str:
    """Read ``__version__`` from the package without importing it.

    Importing the package would pull in the compiled extension; a plain regex
    keeps the config independent of the build.
    """
    init = (REPO_ROOT / "python" / "groundlens" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', init, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


release = _read_version()
version = ".".join(release.split(".")[:2])

# -- General configuration ----------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_autodoc_typehints",
]

# Render docstrings even though the Rust extension is not built here.
autodoc_mock_imports = ["groundlens._engine"]
autosummary_generate = True
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "member-order": "bysource",
}

# Google-style docstrings.
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_use_rtype = True

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "linkify",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Markdown and reStructuredText both parse.
source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}

# -- HTML output --------------------------------------------------------------

html_theme = "furo"
html_title = f"GroundLens {version}"
html_static_path = ["_static"]
html_logo = "assets/logo.svg"
html_favicon = "assets/Ground_icon_1.svg"
html_show_sourcelink = False

html_theme_options = {
    "sidebar_hide_name": True,
    "source_repository": "https://github.com/groundlens-dev/groundlens/",
    "source_branch": "main",
    "source_directory": "docs/",
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/groundlens-dev/groundlens",
            "html": "",
            "class": "fa-brands fa-github",
        },
    ],
    "light_css_variables": {
        "color-brand-primary": "#1a4fd6",
        "color-brand-content": "#1a4fd6",
    },
    "dark_css_variables": {
        "color-brand-primary": "#6f9bff",
        "color-brand-content": "#6f9bff",
    },
}

# Don't copy the prompt when the user clicks "copy" on a shell block.
copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True

# On Read the Docs a couple of niceties.
if os.environ.get("READTHEDOCS") == "True":
    html_context = {"READTHEDOCS": True}
