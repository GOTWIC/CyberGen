"""Shared helpers for the assetgen tests: the small test city built once per process (and
one of its districts regenerated), with briefs; the goldens.

(Plain cached functions, not fixtures: a second conftest.py would shadow tests/conftest.py,
which the citygen tests import by name.)
"""

import copy
import json
import tempfile
from pathlib import Path

from conftest import CITIES, ROOT, SMALL, built_sample, write  # noqa: F401

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "data" / "golden_hashes.json"
_CACHE: dict = {}


def golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def small_build() -> Path:
    """The small test city (tests/conftest.py SMALL) built with the citygen CLI into
    DIR/base, with its briefs (DIR/base/assets/briefs.json); DIR."""
    if "small" not in _CACHE:
        from assetgen.cli import main as ag
        from citygen.cli import main as cg
        d = Path(tempfile.mkdtemp(prefix="ag_small_"))
        spec = write(d, copy.deepcopy(SMALL), "spec.json")
        assert cg(["build", str(spec), str(d / "base")]) == 0
        assert ag(["brief", str(d / "base"), "--no-preview"]) == 0
        _CACHE["small"] = d
    return _CACHE["small"]


def small_regen() -> Path:
    """The small city with Old Quarter regenerated on a new seed (M10), with briefs."""
    if "regen" not in _CACHE:
        from assetgen.cli import main as ag
        from citygen.cli import main as cg
        d = small_build()
        out = d / "regen"
        assert cg(["build", str(d / "spec.json"), str(out), "--base", str(d / "base"),
                   "--district", "Old Quarter"]) == 0
        assert ag(["brief", str(out), "--no-preview"]) == 0
        _CACHE["regen"] = out
    return _CACHE["regen"]
