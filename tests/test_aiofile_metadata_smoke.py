"""Smoke test: importing `aiofile` must not raise on package-metadata access.

Regression guard for the 2026-05-16 incident. aiofile 3.9.0 and 3.10.0 ship a
`version.py` that reads distribution metadata with required-key subscripts::

    __author__ = package_metadata["Author"]
    package_license = package_metadata["License"]

Wheels built under PEP 621 metadata only carry `Author-email` (no `Author`,
no `License` header), so each subscript raises `KeyError` the moment the
module is imported. `aiofile` is pulled transitively
(fastmcp -> py-key-value-aio[filetree] -> aiofile), so that import happens on
*every* workspace-mcp invocation — taking the whole MCP server down before
any Google API call runs.

aiofile 3.11.1+ reads metadata with `.get()` and fallbacks. `pyproject.toml`
carries `[tool.uv] constraint-dependencies = ["aiofile>=3.11.1"]` to keep the
buggy versions out of the resolution. This test fails fast in CI if that
constraint is ever dropped, or if a future aiofile release reintroduces the
required-key pattern — so a regression surfaces here, not as a production
import crash.
"""

import importlib


def test_aiofile_imports_without_metadata_keyerror():
    """`import aiofile` triggers aiofile.version's module-scope metadata read."""
    aiofile = importlib.import_module("aiofile")

    resolved_version = getattr(aiofile, "__version__", None)
    assert resolved_version, "aiofile.__version__ should be populated, not empty"


def test_aiofile_version_is_at_least_3_11_1():
    """The constraint floor must keep the buggy 3.9.0 / 3.10.0 series out."""
    aiofile = importlib.import_module("aiofile")

    version_text = aiofile.__version__
    version_parts = tuple(int(part) for part in version_text.split(".")[:3])
    minimum_safe_version = (3, 11, 1)
    assert version_parts >= minimum_safe_version, (
        f"aiofile {version_text} is below the 3.11.1 floor; "
        f"3.9.x/3.10.x crash workspace-mcp at import"
    )
