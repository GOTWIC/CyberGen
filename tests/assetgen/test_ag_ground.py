"""AG13, ground cover and grass (scope 5.6, 14.14): every piece of the small test city's open
land is drawn and every blockout cover object replaced, no clump stands on paving, a road, a
building or water (and the check catches one that does), the tile cap and the budgets hold,
tiles are kept by hash (a second build writes nothing), the bytes do not depend on the
worker count or the hash seed, a regenerated district rewrites only the tiles near it, the
clumps are valid and deterministic, AG6 has the ground sets, and the golden holds
(`tests/assetgen/ground_goldens.py` writes it)."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import shapely

from assetgen.brief import load_model
from assetgen.ground import build as GB
from assetgen.ground import checks as CK
from assetgen.ground import clumps as CL
from assetgen.ground import gather as GA
from assetgen.ground import kinds as K
from assetgen.ground import tile as TL
from citygen import geom as G

from agtools import HERE, ROOT, small_build, small_regen

GOLDEN = HERE / "data" / "golden_ground.json"
_DONE: dict = {}


def _ground(build_dir: Path, out: Path | None = None, workers: int = 2) -> dict:
    model, sha, bdir = load_model(build_dir)
    return GB.build(model, sha, out or bdir / "assets", None, workers=workers)


def _small() -> tuple[Path, dict]:
    if "small" not in _DONE:
        base = small_build() / "base"
        _DONE["small"] = (base, _ground(base))
    return _DONE["small"]


def test_small_city_ground_passes():
    base, rep = _small()
    assert rep["ok"], [c for c in rep["checks"] if not c["ok"]]
    model = load_model(base)[0]
    st = rep["stats"]
    assert st["pieces"] == len(model.ground_cover) > 0
    assert st["instances"] > 1000 and st["ground_triangles"] > 0
    cov = next(c for c in rep["checks"] if c["name"] == "ground_coverage")
    assert cov["short"] == 0 and cov["not_replaced"] == [] and cov["blockout_objects"] > 0
    # every kind the city has is drawn on its surface, the paved ones on AG7's paving sets
    man = json.loads((base / "assets" / "ground" / "manifest.json").read_text())
    surfs = {s for r in man["tiles"].values() for s in r["surfaces"]}
    assert any(s.startswith("paving.") for s in surfs) and "lawn" in surfs or "park_lawn" in surfs


def test_second_build_writes_nothing():
    base, _ = _small()
    gdir = base / "assets" / "ground"
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in gdir.rglob("*") if p.is_file()}
    rep = _ground(base)
    f = rep["files"]
    assert f["tiles_made"] == 0 and not f["written"] and not f["removed"]
    assert not f["manifest_written"] and not f["contribution_written"]
    after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in gdir.rglob("*") if p.is_file()}
    assert before == after


def test_same_bytes_any_workers_and_hash_seed(tmp_path):
    base, _ = _small()
    want = GB.outputs_digest(base / "assets")
    _ground(base, tmp_path / "one", workers=1)
    assert GB.outputs_digest(tmp_path / "one") == want
    env = {**os.environ, "PYTHONHASHSEED": "4242"}
    proc = subprocess.run([sys.executable, "-m", "assetgen", "ground", str(base), "--out",
                           str(tmp_path / "seed"), "--workers", "3", "--quiet"], cwd=ROOT,
                          env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert GB.outputs_digest(tmp_path / "seed") == want


def test_regenerated_district_rewrites_only_its_tiles():
    base, _ = _small()
    regen = small_regen()
    gdir = regen / "assets" / "ground"
    if gdir.exists():
        shutil.rmtree(gdir)
    shutil.copytree(base / "assets" / "ground", gdir)
    rep = _ground(regen)
    assert rep["ok"], [c for c in rep["checks"] if not c["ok"]]
    model = load_model(regen)[0]
    d = next(x for x in model.districts if x.name == "Old Quarter")
    # a tile may change only where the district, its seam or what reaches it from there
    # (shade 60 m, moisture 60 m) touches it
    reach = G.from_model_poly(d.polygon).buffer(130.0)
    written = sorted({Path(f).stem for f in rep["files"]["written"] + rep["files"]["removed"]
                      if "/t" in f})
    assert written, "the regeneration changed no tile"
    far = [t for t in written if not shapely.intersects(reach, shapely.box(*GA.tile_box(t)))]
    assert far == []
    assert len(written) < len(rep["files"]["written"]) + rep["files"]["tiles_kept"]
    assert rep["files"]["tiles_kept"] > 0


def test_clear_check_catches_a_clump_on_a_road(tmp_path):
    base, _ = _small()
    out = tmp_path / "assets"
    shutil.copytree(base / "assets" / "ground", out / "ground")
    man = json.loads((out / "ground" / "manifest.json").read_text())
    model = load_model(base)[0]
    t = next(t for t, r in sorted(man["tiles"].items()) if r.get("instances"))
    seg = next(s for s in model.road_segments if not s.tunnel and s.road_class == "street")
    x, y = seg.centerline[len(seg.centerline) // 2][:2]
    t = GA.tile_name(*GA.tile_key(x, y))
    gp = out / "ground" / "grass" / f"{t}.json"
    doc = json.loads(gp.read_text()) if gp.is_file() else \
        {"tile": t, "pivot": [GA.tile_box(t)[0] + 128.0, GA.tile_box(t)[1] + 128.0, 0.0],
         "nodes": {}}
    px, py, _ = doc["pivot"]
    node = "clump.lawn.v0"
    doc["nodes"].setdefault(node, []).append([x - px, y - py, 0.1, 0.0, 1.0, 1.0, 1.0])
    gp.write_text(json.dumps(doc))
    man["tiles"].setdefault(t, {"instances": {}})["instances"][node] = 1
    r = CK._clear(model, man, out)
    assert not r["ok"] and r["failing"] >= 1


def test_tile_cap_holds_and_scales_up(monkeypatch):
    base, _ = _small()
    model = load_model(base)[0]
    g = GA.gather(model)
    t = max(g.tiles, key=lambda t: sum(p["area"] or 0.0 for p in g.tiles[t]["pieces"]
                                       if p["kind"] in K.GRASSY))
    free = TL.make_tile(g.tiles[t])
    n_free = sum(len(v) for v in free["instances"].values())
    cap = max(50, n_free // 4)
    monkeypatch.setattr(K, "TILE_INSTANCES", cap)
    capped = TL.make_tile(g.tiles[t])
    n = sum(len(v) for v in capped["instances"].values())
    assert 0 < n <= cap < n_free
    scales = [q[4] for v in capped["instances"].values() for q in v]
    assert max(scales) > 1.25 and max(scales) <= K.MAX_SCALE_UP * 1.25 + 1e-9


def test_clumps_valid_and_deterministic():
    fams = [(k, None) for k in sorted(K.CLUMPS) if k != "flowers"] + \
        [("flowers", CL.palette_key(list(K.FLOWER_FALLBACK)))]
    pal = {CL.palette_key(list(K.FLOWER_FALLBACK)): list(K.FLOWER_FALLBACK)}
    a, info = GB.clumps_glb(fams, pal)
    b, _ = GB.clumps_glb(fams, pal)
    assert a == b
    assert len(info) == sum(K.CLUMPS[k][0] for k, _ in fams)
    for node, r in info.items():
        assert 0 < r["triangles"] <= K.CLUMP_TRIANGLES, node
        assert not node.rsplit(".", 1)[-1].isdigit(), node     # (Blender's copy suffix)
        assert all(s in CL.SLOTS or s.startswith(CL.FLOWER_PREFIX) for s in r["slots"])
        lo, hi = r["bounds"]
        assert lo[2] >= -0.02 and hi[2] <= 2.5
    for k in K.CLUMPS:
        c = CL.make(k, 0)
        for s in c.slots.values():
            assert len(s["col"]) == len(s["pos"]) == len(s["nrm"])


def test_flower_palette_from_district_colors():
    cols = K.flower_colors(["#7a4a35", "#b9a58c", "#3d3a36", "#8c2f2b", "#d8cbb3"])
    assert len(cols) == 3 and all(len(c) == 7 for c in cols)
    assert K.flower_colors(["#8a8782", "#6b6964"]) == list(K.FLOWER_FALLBACK)


def test_library_has_the_ground_sets():
    from assetgen.materials import library as LB
    from assetgen.materials import surfaces as S
    sets = LB.sets()
    for name, e in LB.GROUND_SETS.items():
        assert name in sets and e["gen"] in S.GENERATORS
        s = S.make(e["gen"], 64, e["tile_m"], dict(sets[name]["params"]))
        assert s.color.shape == (64, 64, 3) and 0.0 <= float(s.color.min())
    for sf in K.SURFACES.values():
        assert all(x in sets for x in sf[:3]), sf


def test_contribution_entries():
    base, _ = _small()
    con = json.loads((base / "assets" / "unreal_contribution.ground.json").read_text())
    assert con["part"] == "ground" and con["layer"] == 2
    grass = [e for e in con["entries"] if e["kind"] == "ground.grass"]
    assert grass
    for e in grass:
        for p in e["parts"]:
            assert p["cull_m"] == list(K.FADE_M) and p["nanite"] is False
            assert p["collision"] == {"none": True} and p["shadow"] is False
            assert (base / "assets" / p["xforms_file"]).is_file()
    ground = [e for e in con["entries"] if e["kind"] == "ground.cover"]
    for e in ground:
        assert e["glb"].startswith("ground/tiles/") and e["nanite"]
        for s in e["slots"]:
            m = con["materials"][s]
            assert m["master"] == "ground" and m["textures"]["Mask"] in con["textures"]
    assert {m["master"] for m in con["materials"].values()} == {"ground", "grass"}


def test_golden():
    base, _ = _small()
    gold = json.loads(GOLDEN.read_text())
    assert GB.outputs_digest(base / "assets")["all"] == gold["small_city"]["all"]
