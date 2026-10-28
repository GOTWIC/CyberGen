"""AG7, street elements (scope 5.3, 9, 14.8): every street element of the small test city
has a valid mesh, packs are kept by hash (a second build writes nothing), the bytes do not
depend on the worker count or the hash seed, a regenerated district rewrites only its own
tiles' packs and its seam's, the Unreal contribution matches the packs, M13's ground lifts
everything, and the goldens hold (made on the Mac, confirmed in the `citygen-x86` image;
write them again with `.venv/bin/python tests/assetgen/streets_goldens.py`)."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from assetgen import canon as C
from assetgen.brief import load_model
from assetgen.streets import build as SB
from assetgen.streets import kit as K
from assetgen.streets.ctx import Ground
from assetgen.streets.preview import read_glb

from agtools import CITIES, HERE, ROOT, built_sample, small_build, small_regen

GOLDEN = HERE / "data" / "golden_streets.json"
_DONE: dict = {}


def _lib() -> dict:
    """AG6's library at the default spec's density (its textures in the contribution, as
    `assetgen build` and `assetgen streets` write it)."""
    if "lib" not in _DONE:
        from assetgen import spec as S
        from assetgen.materials.build import library_for
        _DONE["lib"] = library_for(S.dump(S.fill(S.AssetSpec())), log=lambda *a: None)
    return _DONE["lib"]


def _streets(build_dir: Path, out: Path | None = None, workers: int = 2) -> dict:
    model, sha, bdir = load_model(build_dir)
    return SB.build(model, sha, out or bdir / "assets", None, workers=workers, lib=_lib())


def _small() -> tuple[Path, dict]:
    if "small" not in _DONE:
        base = small_build() / "base"
        _DONE["small"] = (base, _streets(base))
    return _DONE["small"]


def test_small_city_streets_pass():
    base, rep = _small()
    assert rep["ok"], [c for c in rep["checks"] if not c["ok"]]
    cov = rep["coverage"]
    for name in SB.COVERED:
        assert cov[name]["assets"] + cov[name]["declared"] == cov[name]["entities"], name
    assert cov["road_segments"]["assets"] > 100
    assert rep["stats"]["corner_pads"]["made"] > 0
    assert rep["stats"]["triangles"] > 0


def test_second_build_writes_nothing():
    base, _ = _small()
    sdir = base / "assets" / "streets"
    before = {f.name: (f.stat().st_mtime_ns, f.read_bytes()) for f in sdir.iterdir()}
    rep = _streets(base)
    f = rep["files"]
    assert f["tiles_made"] == 0 and f["tiles_written"] == 0
    assert not f["manifest_written"] and not f["contribution_written"]
    assert not f["parts_written"]
    after = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in sdir.iterdir()}
    assert after == before


def test_same_bytes_any_workers_and_hash_seed(tmp_path):
    base, _ = _small()
    want = SB.outputs_digest(base / "assets")
    one = tmp_path / "one"
    _streets(base, one, workers=1)
    assert SB.outputs_digest(one) == want
    env = {**os.environ, "PYTHONHASHSEED": "4242"}
    proc = subprocess.run([sys.executable, "-m", "assetgen", "streets", str(base), "--out",
                           str(tmp_path / "seed"), "--workers", "3"], cwd=ROOT, env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert SB.outputs_digest(tmp_path / "seed") == want


def test_regenerated_district_rewrites_only_its_tiles():
    from assetgen.streets.seam import seam
    base, _ = _small()
    regen = small_regen()
    if (regen / "assets" / "streets").exists():
        shutil.rmtree(regen / "assets" / "streets")
    shutil.copytree(base / "assets" / "streets", regen / "assets" / "streets")
    rep = _streets(regen)
    assert rep["ok"]
    r = seam(base, regen, "Old Quarter")
    assert r["unexplained"] == []
    assert r["tiles_without_a_changed_piece"] == []
    assert sorted(rep["files"]["written"]) == [
        t for t in r["changed_tiles"] if (regen / "assets" / "streets" / f"{t}.glb").exists()]
    assert 0 < len(r["changed_tiles"]) < r["tiles"]


def test_contribution_matches_packs():
    base, _ = _small()
    con = json.loads((base / "assets" / "unreal_contribution.streets.json").read_text())
    man = json.loads((base / "assets" / "streets" / "manifest.json").read_text())
    assert con["stage"] == "assetgen" and con["layer"] == 2 and con["part"] == "streets"
    nodes = {}
    for tile in {e["tile"] for e in con["entries"]}:
        for name, _, _, T in read_glb(base / "assets" / "streets" / f"{tile}.glb"):
            nodes[name] = nodes.get(name, 0) + len(T)
    for e in con["entries"]:
        assert e["node"] in nodes, e["key"]
        if e["nanite"]:
            assert nodes[e["node"]] == e["triangles"] == man["pieces"][e["key"]]["triangles"]
        assert set(e["slots"]) <= set(con["materials"])
        assert e["asset"] == e["key"].replace(".", "_")
    # every blockout object a piece replaces is a joined street piece or the piece's own
    keys = {e["key"] for e in con["entries"]}
    assert keys == {k for k, r in man["pieces"].items() if r["triangles"] > 0 or r.get("parts")}
    assert any(e["replaces"] for e in con["entries"])


def test_sky_tube_lods_non_nanite():
    from assetgen.streets.transit import make_sky_tube
    inp = {"st": {"id": "tl.x.tb.e0n0", "kind": "tube", "z0_m": 89.0, "z1_m": 96.0,
                  "line": [[0.0, 0.0, 96.0], [40.0, 0.0, 96.0], [80.0, 10.0, 96.0]],
                  "attrs": {"line_id": "tl.x", "mode": "sky_tube", "width_m": 7.0,
                            "deck_m": 7.0}},
           "origin": [40.0, 5.0], "ground_c": None}
    out = make_sky_tube(inp)
    assert out.mesh.triangles > 0 and out.nanite
    ex = out.extra[0]
    assert not ex["nanite"] and len(ex["lods"]) == 3
    tris = [m.triangles for m in ex["lods"]]
    assert tris[0] > tris[1] > tris[2] > 0
    for m in ex["lods"]:
        assert not any(K.check(m.slots).values())


def test_m13_ground_lifts_roads_and_structures():
    """M13's contract: a road's surface is its grade line plus its z profile; anything else
    stands on the terrain grid at its point (bilinear)."""
    from assetgen.streets.roads import make as make_road
    t = SimpleNamespace(x0=0.0, y0=0.0, cell_m=10.0, natural=[[0.0] * 3] * 3,
                        ground=[[0.0, 10.0, 20.0], [0.0, 10.0, 20.0], [0.0, 10.0, 20.0]],
                        water_levels=[])
    g = Ground(SimpleNamespace(terrain=t))
    assert g.at(5.0, 5.0) == 5.0 and g.at(15.0, 0.0) == 15.0
    assert abs(g.at(30.0, 30.0) - 20.0) < 1e-3       # clamped to the grid, as M13 samples
    assert Ground(SimpleNamespace()).samples([(1.0, 2.0)]) is None
    seg = {"id": "rs.e0n0", "centerline": [[0.0, 0.0], [20.0, 0.0]],
           "z_profile": [{"s": 0.0, "z": 0.0}, {"s": 20.0, "z": 0.0}],
           "ground": [{"s": 0.0, "z": 30.0}, {"s": 20.0, "z": 31.0}], "width_m": 8.0,
           "road_class": "street", "attrs": {},
           "cross_section": {"sidewalk_m": [0.0, 0.0], "median_m": 0.0, "shared": False}}
    inp = {"seg": seg, "cls": "street", "ends": [], "crossings": [], "lanes": [],
           "style": {"archetype": None, "era": "mixed_modern", "grime": 0.0, "wealth": 0.5,
                     "wear": 1.0}, "start": "a", "end": "b", "origin": [10.0, 0.0]}
    mesh = make_road(inp).mesh
    zs = sorted({p[2] for p in mesh.slots["asphalt.street"].pos})
    assert zs[0] == 30050 and zs[-1] == 31050


def test_kit_drops_folds_and_checks_clean():
    m = K.Mesh((0.0, 0.0))
    # a strip that turns back on itself: the folded quads are left out
    rows = [[(0.0, -1.0, 0.0), (0.0, 1.0, 0.0)], [(1.0, -1.0, 0.0), (1.0, 1.0, 0.0)],
            [(0.5, -1.0, 0.0), (0.5, 1.0, 0.0)]]
    uvs = [[(0, 0), (0, 1)]] * 3
    m.grid("asphalt.street", rows, uvs, expect=(0.0, 0.0, 1.0))
    assert m.folds == 2 and m.triangles == 2
    b = K.Mesh((0.0, 0.0))
    b.box("concrete", 0.0, 0.0, 0.0, 4.0, 2.0, 3.0, 30.0, bottom=True)
    b.cylinder("steel", 5.0, 0.0, 1.0, 0.0, 2.0, n=12)
    assert b.triangles == 12 + 24 + 10
    assert not any(K.check(b.slots).values())


def _golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_small_city_golden():
    base, _ = _small()
    assert SB.outputs_digest(base / "assets")["all"] == _golden()["testport"]["all"]


def test_vesper_bay_tiles_golden(tmp_path):
    path = next(p for p in CITIES if p.parent.name == "vesper_bay")
    built, _, data = built_sample(path)
    rep = SB.build(built.model, C.sha256_bytes(data), tmp_path, None, workers=2, lib=_lib())
    assert rep["ok"], [c for c in rep["checks"] if not c["ok"]]
    want = _golden()["vesper_bay"]
    got = SB.outputs_digest(tmp_path)
    assert {t: got["tiles"][t] for t in want["tiles"]} == want["tiles"]
    assert got["all"] == want["all"]


def test_road_with_a_micro_kink_is_made_again_from_a_tidied_line():
    """Greyhook's `rs.w1338n148` (its inputs, tests/assetgen/data/road_micro_kink.json): two
    vertices 6 and 8 cm apart, 5 mm off the line, swing the 9 m curb offsets over each other
    and leave a directed edge in two triangles; `make` remakes such a road from its line
    without the kink."""
    from assetgen.streets import roads
    inp = json.loads((HERE / "data" / "road_micro_kink.json").read_text(encoding="utf-8"))
    assert K.check(roads._make(inp, False).mesh.slots)["winding"] == 1
    out = roads.make(inp)
    assert not any(K.check(out.mesh.slots).values())
    assert out.mesh.triangles == 266
