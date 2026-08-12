import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

ROOT = os.path.abspath("..")
sys.path.insert(0, os.path.join(ROOT, "packages", "pigeon_client", "src"))
sys.path.insert(0, os.path.join(ROOT, "packages", "pigeon_server", "src"))
sys.path.insert(0, os.path.join(ROOT, "packages", "pigeon_dispatch", "src"))

# Required so modules with import-time env checks can be autodoc-imported.
os.environ.setdefault("PIGEON_TOKEN_KEY", "docs-token-key")
os.environ.setdefault("PIGEON_DISPATCH_KEY", "docs-dispatch-key")
os.environ.setdefault("PIGEON_DISPATCH_URL", "http://127.0.0.1:5001")

project = "pigeon"
author = "pigeon contributors"
copyright = f"{datetime.now().year}, {author}"


def _load_project_version() -> str:
    candidates = [
        Path(ROOT) / "packages" / "pigeon_server" / "pyproject.toml",
        Path(ROOT) / "packages" / "pigeon_client" / "pyproject.toml",
        Path(ROOT) / "packages" / "pigeon_dispatch" / "pyproject.toml",
    ]
    for pyproject in candidates:
        if not pyproject.exists():
            continue
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        ver = data.get("project", {}).get("version")
        if ver:
            return str(ver)
    return "0.0.0"


version = _load_project_version()
release = version
project = f"pigeon (v{release})"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
]

autosummary_generate = True

autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

master_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
templates_path = ["_templates"]

html_theme = "sphinx_rtd_theme"
html_short_title = f"pigeon (v{release})"
html_static_path = []

# Root README contains markdown links to repo files; ignore unresolved xref warnings.
suppress_warnings = ["myst.xref_missing", "toc.not_included"]
