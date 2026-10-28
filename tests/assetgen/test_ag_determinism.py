"""Determinism harness (scope section 10): goldens for the small test city's briefs, a few
Vesper Bay buildings and every sample's briefs; the same bytes with another hash seed.
The goldens were made on the M4 Mac and confirmed on x86_64 Linux (docker image
`citygen-x86`). After a citygen change moves a city model, write them again with
`.venv/bin/python tests/assetgen/goldens.py` and say why in the PR."""

import json
import os
import subprocess
import sys

import pytest

from assetgen import brief as B
from assetgen import canon as C

from agtools import CITIES, ROOT, built_sample, golden, small_build


def test_small_city_briefs_golden():
    data = (small_build() / "base" / "assets" / "briefs.json").read_bytes()
    assert C.sha256_bytes(data) == golden()["testport_briefs"]


def test_same_bytes_with_another_hash_seed(tmp_path):
    base = small_build() / "base"
    outs = []
    for hs in ("1", "4242"):
        out = tmp_path / hs
        env = {**os.environ, "PYTHONHASHSEED": hs}
        proc = subprocess.run([sys.executable, "-m", "assetgen", "brief", str(base), "--out",
                               str(out), "--no-preview"], cwd=ROOT, env=env,
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        outs.append((out / "briefs.json").read_bytes())
    assert outs[0] == outs[1] == (base / "assets" / "briefs.json").read_bytes()


def _vesper_bay():
    path = next(p for p in CITIES if p.parent.name == "vesper_bay")
    return built_sample(path)


def test_vesper_bay_buildings_golden():
    """A few buildings of Vesper Bay, one per kind (landmark, podium tower, shopfront row,
    shanty stack, megabuilding, villa): their brief hashes."""
    built, _, _ = _vesper_bay()
    res = B.build_briefs(built.model)
    want = golden()["buildings"]["vesper_bay"]
    got = {k: B.brief_hash(res["briefs"][k]) for k in want}
    assert got == want


@pytest.mark.parametrize("path", CITIES, ids=lambda p: p.parent.name)
def test_sample_briefs_golden(path, tmp_path):
    built, _, data = built_sample(path)
    res = B.build_briefs(built.model)
    assert len(res["briefs"]) == len(built.model.buildings)
    out = B.write_briefs(tmp_path, built.model, C.sha256_bytes(data), res)
    assert C.sha256_bytes(out.read_bytes()) == golden()["samples"][path.parent.name]


def test_golden_file_is_complete():
    g = golden()
    assert set(g["samples"]) == {p.parent.name for p in CITIES}
    assert len(g["buildings"]["vesper_bay"]) >= 5
