"""Make the vendored TiMini-Print package importable.

Our scripts live in this repo's ``src/`` while the upstream ``timiniprint`` package
lives in the ``TiMini-Print/`` git submodule at the repo root. Importing this module
(before importing ``timiniprint``) puts the submodule on ``sys.path``.

Override the location with the ``TIMINIPRINT_DIR`` environment variable if your
checkout differs.
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TIMINIPRINT_DIR = os.environ.get(
    "TIMINIPRINT_DIR", os.path.join(_REPO_ROOT, "TiMini-Print")
)

if os.path.isdir(os.path.join(_TIMINIPRINT_DIR, "timiniprint")):
    if _TIMINIPRINT_DIR not in sys.path:
        sys.path.insert(0, _TIMINIPRINT_DIR)
else:  # pragma: no cover - surfaced only on a broken checkout
    raise ImportError(
        f"Could not find the 'timiniprint' package under {_TIMINIPRINT_DIR!r}. "
        "Did you clone with submodules (git clone --recursive) or run "
        "'git submodule update --init'? You can also set TIMINIPRINT_DIR."
    )
