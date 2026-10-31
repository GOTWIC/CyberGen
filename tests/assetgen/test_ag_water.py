"""AG12, water (scope 5.6, 14.13): every water body of the small test city has its surface,
bed and banks with every water check passing; the fields are M16's where M16 defines them;
packs are kept by hash and do not depend on the worker count or the hash seed; a regenerated
district rewrites only the water within reach of what changed; the Unreal contribution
matches the packs (non-Nanite surface LOD chains, Nanite beds, the drop of the blockout's
water, an underwater volume per swim box); AG7's walls reach the bed and no longer dam a
canal's mouth; the goldens hold (write them again with
`.venv/bin/python tests/assetgen/water_goldens.py`)."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, box

from assetgen.brief import load_model
from assetgen.water import build as WB
from assetgen.water import fields as F
from assetgen.water import grid as GR
from assetgen.water.pieces import WCtx, gather

from agtools import HERE, ROOT, small_build, small_regen

GOLDEN = HERE / "data" / "golden_water.json"
_DONE: dict = {}


def _water(build_dir: Path, out: Path | None = None, workers: int = 2) -> dict:
    model, sha, bdir = load_model(build_dir)
    return WB.build(model, sha, out or bdir / "assets", None, workers=workers)


def _small() -> tuple[Path, dict]:
    if "small" not in _DONE:
        base = small_build() / "base"
        _DONE["small"] = (base, _water(base))
    return _DONE["small"]


def test_small_city_water_passes():
    base, rep = _small()
    assert rep["ok"], [c for c in rep["checks"] if not c["ok"]]
    model, _, _ = load_model(base)
    man = json.loads((base / "assets" / "water" / "manifest.json").read_text())
    bodies = {p.partition("@")[0] for p, r in man["pieces"].items() if r["maker"] == "body"}
    assert bodies == {b.id for b in (*model.seas, *model.rivers, *model.channels,
                                     *model.waterways)}
    for pid, r in man["pieces"].items():
        if r["maker"] == "body":
            assert r["lods"][0]["triangles"] > 0, pid
            assert r["lods"][0]["triangles"] > r["lods"][-1]["triangles"] or \
                len(r["lods"]) == 1, pid
    kinds = {k.kind for k in model.banks}
    drawn = {r["kind"].rsplit(".", 1)[1] for r in man["pieces"].values()
             if r["maker"] == "bank"}
    assert drawn == kinds - {"quay"} - ({"canal_wall"} if not any(
        k.kind == "canal_wall" and k.water_id not in {w.id for w in model.waterways}
        for k in model.banks) else set())
    assert rep["stats"]["instances"] > 0 or "riprap" not in kinds


def test_fields_are_m16s():
    """A body piece's own bed (from its inputs alone, the banks within reach of its tile)
    is M16's `Beds.depth_many` exactly, and its level M13's (a flat city's surface)."""
    from citygen import water as WA
    base, _ = _small()
    model, _, _ = load_model(base)
    cx = WCtx(model)
    pieces, _ = gather(cx)
    beds = WA.Beds(model)
    lv = WA.Levels(model)
    rng = np.random.default_rng(3)
    n = 0
    for p in pieces:
        if p.maker != "body":
            continue
        reg = shapely.unary_union([shapely.Polygon(r["exterior"], r.get("holes", []))
                                   for r in p.inputs["region"]])
        x0, y0, x1, y1 = reg.bounds
        xs = rng.uniform(x0, x1, 400)
        ys = rng.uniform(y0, y1, 400)
        ins = shapely.contains_xy(reg, xs, ys)
        xs, ys = xs[ins], ys[ins]
        if not len(xs):
            continue
        fd = F.Field(p.inputs)
        wid = p.inputs["body"]["id"]
        assert np.array_equal(fd.depth16(xs, ys), beds.depth_many(wid, xs, ys)), p.id
        lev = fd.level(xs, ys)
        assert max(abs(lev[i] - lv.at(wid, xs[i], ys[i])) for i in range(len(xs))) < 1e-9
        b = fd.bottom(xs, ys)
        assert (b >= F.SURFACE_GAP_M - 1e-12).all()
        n += len(xs)
    assert n > 1000


def test_second_build_writes_nothing():
    base, _ = _small()
    rep = _water(base)
    f = rep["files"]
    assert f["tiles_made"] == 0 and f["written"] == []
    assert not f["parts_written"] and not f["manifest_written"] and not f["contribution_written"]


def test_same_bytes_any_workers_and_hash_seed(tmp_path):
    base, _ = _small()
    # (the water reads AG7's bridge piers from the streets manifest beside it, which other
    # tests may build into the small city's assets: the same piers in every output)
    streets = base / "assets" / "streets" / "manifest.json"
    for d in ("two", "one", "seed"):
        if streets.is_file():
            (tmp_path / d / "streets").mkdir(parents=True)
            shutil.copy(streets, tmp_path / d / "streets" / "manifest.json")
    _water(base, tmp_path / "two", workers=2)
    want = WB.outputs_digest(tmp_path / "two")
    _water(base, tmp_path / "one", workers=1)
    assert WB.outputs_digest(tmp_path / "one") == want
    env = {**os.environ, "PYTHONHASHSEED": "4242"}
    proc = subprocess.run([sys.executable, "-m", "assetgen", "water", str(base), "--out",
                           str(tmp_path / "seed"), "--workers", "3", "--no-textures"], cwd=ROOT,
                          env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert WB.outputs_digest(tmp_path / "seed") == want


def test_regenerated_district_rewrites_only_water_near_it():
    """Old Quarter regenerated: every water piece that changed is one of its banks, or a
    body piece whose tile lies within reach of a bank that changed (M16's banks keep to their
    district, a bed reads only banks within reach)."""
    base, _ = _small()
    regen = small_regen()
    if (regen / "assets" / "water").exists():
        shutil.rmtree(regen / "assets" / "water")
    shutil.copytree(base / "assets" / "water", regen / "assets" / "water")
    rep = _water(regen)
    assert rep["ok"], [c for c in rep["checks"] if not c["ok"]]
    a = json.loads((base / "assets" / "water" / "manifest.json").read_text())["pieces"]
    b = json.loads((regen / "assets" / "water" / "manifest.json").read_text())["pieces"]
    changed = sorted(k for k in a.keys() | b.keys()
                     if a.get(k, {}).get("hash") != b.get(k, {}).get("hash"))
    assert changed
    ma, _, _ = load_model(base)
    mb, _, _ = load_model(regen)
    did = next(d.id for d in mb.districts if d.name == "Old Quarter")
    ka = {k.id: k for k in ma.banks}
    kb = {k.id: k for k in mb.banks}
    moved = [k for k in ka.keys() ^ kb.keys()] + [
        k for k in ka.keys() & kb.keys() if ka[k].model_dump() != kb[k].model_dump()]
    assert moved
    assert all((kb.get(k) or ka.get(k)).district_id == did for k in moved), moved
    lines = shapely.unary_union([LineString((kb.get(k) or ka.get(k)).line) for k in moved])
    cx = WCtx(mb)
    reach = max(cx.reach(x) for x in cx.bodies)
    for pid in changed:
        if pid in ka or pid in kb:
            assert pid in moved, pid
            continue
        body, _, tile = pid.partition("@")
        tb = _tile_box(tile)
        assert box(*tb).distance(lines) <= reach, pid
    assert len({b[p]["tile"] for p in changed if p in b}) < len({r["tile"] for r in b.values()})


def _tile_box(name: str):
    ix, iy = int(name[1:4]), int(name[4:7])
    return ix * 256.0, iy * 256.0, (ix + 1) * 256.0, (iy + 1) * 256.0


def test_contribution_matches_packs():
    from assetgen.water.preview import read
    base, _ = _small()
    con = json.loads((base / "assets" / "unreal_contribution.water.json").read_text())
    man = json.loads((base / "assets" / "water" / "manifest.json").read_text())
    assert con["stage"] == "assetgen" and con["layer"] == 2 and con["part"] == "water"
    nodes = {}
    for tile in {e["tile"] for e in con["entries"] if e.get("tile")}:
        for r in read(base / "assets" / "water" / f"{tile}.glb"):
            nodes[r["node"]] = nodes.get(r["node"], 0) + len(r["tri"])
    surfaces = beds = 0
    for e in con["entries"]:
        if e.get("drop"):
            assert e["key"] == WB.DROP_KEY and e["replaces"]
            continue
        assert e["node"] in nodes, e["key"]
        assert set(e["slots"]) <= set(con["materials"])
        if e["kind"].startswith("water.surface."):
            surfaces += 1
            assert e["nanite"] is False and e["collision"] == {"none": True}
            assert [lo["node"] for lo in e["lods"]][0] == e["node"]
            assert all(lo["node"] in nodes for lo in e["lods"])
            assert all(r.startswith(("city.sea.", "city.water.")) for r in e["replaces"])
        elif e["kind"] == "water.bed":
            beds += 1
            assert e["nanite"] is True and e["collision"] == {"complex": True}
            assert all(r.startswith("city.bed.") for r in e["replaces"])
    assert surfaces == beds == sum(1 for r in man["pieces"].values() if r["maker"] == "body")
    assert set(con["underwater"]) == {b for b in man["bodies"]}
    for slot, m in con["materials"].items():
        assert m["master"] == {"water": "water", "bed": "bed"}.get(slot.split(".")[0],
                                                                    "concrete"), slot


def test_exporter_takes_the_water(tmp_path):
    """The Unreal manifest's stage 2: the water entries over the blockout's sea, water, bed
    and bank objects, the surfaces as LOD chains, an underwater volume per swim box."""
    from citygen import unreal as UN
    base, _ = _small()
    contribs = [(f"assets/{f.name}", json.loads(f.read_text()), "x")
                for f in [base / "assets" / "unreal_contribution.water.json"]]
    man = {"tiles": [], "instances": [], "content_root": "/Game/CityGen/Testport",
           "swim": [{"key": "swim.sea.t+00-03.1", "water_id": "sea", "tile": "t+00-03",
                     "box": [0.0, -700.0, 16.0, -684.0], "z": [-13.0, -1.5]},
                    {"key": "swim.nowhere.t+00-03.1", "water_id": "nowhere",
                     "tile": "t+00-03", "box": [0.0, 0.0, 1.0, 1.0], "z": [-1.0, 0.0]}]}
    s2 = UN.stage2(man, base, contribs)
    assert [u["key"] for u in s2["underwater"]] == ["underwater.sea.t+00-03.1"]
    assert s2["counts"]["underwater_volumes"] == 1
    assert s2["lod_chains"] and all(c["lods"] for c in s2["lod_chains"])
    assert "water" in s2["masters"] and "bed" in s2["masters"]
    kinds = UN.actor_kinds({"tiles": [], "instances": [], "stage2": s2})
    assert kinds["underwater.sea.t+00-03.1"] == "underwater"


def test_ag7_walls_reach_the_bed_and_leave_mouths_open():
    from assetgen.streets.build import build as street_build
    base, _ = _small()
    model, sha, _ = load_model(base)
    out = base / "assets"
    if not (out / "streets" / "manifest.json").is_file():
        street_build(model, sha, out, None, workers=2)
    man = json.loads((out / "streets" / "manifest.json").read_text())["pieces"]
    for q in model.quays:
        assert man[q.id]["notes"]["foot"], q.id
    walls = {k.water_id for k in model.banks if k.kind == "canal_wall"}
    for w in model.waterways:
        if w.id in walls and w.kind != "creek":
            assert man[w.id]["triangles"] > 0
    rep = _water(base)
    gaps = next(c for c in rep["checks"] if c["id"] == "water_gaps")
    assert gaps["ok"], gaps["detail"]


def test_mesher_takes_a_hole_touching_its_outline():
    """A cell piece whose hole touches its outline at a point (a fold of a bank's offset)
    is split and meshed with no directed edge twice and its area whole."""
    outer = [(0, 0), (2, 0), (2, 2), (0, 2)]
    hole = [(1.0, 0.0), (1.3, 0.6), (0.7, 0.6)]
    poly = shapely.Polygon(outer, [hole])
    v, t = GR.mesh(poly, (0.0, 0.0, 2.0, 2.0), 4.0)
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    _, c = np.unique(e, axis=0, return_counts=True)
    assert (c == 1).all()
    p = v.astype(float) / 1000.0
    a, b, cc = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    area = ((b[:, 0] - a[:, 0]) * (cc[:, 1] - a[:, 1]) -
            (b[:, 1] - a[:, 1]) * (cc[:, 0] - a[:, 0])).sum() / 2.0
    assert abs(area - poly.area) < 1e-6


def test_small_city_golden(tmp_path):
    """(Built into a folder of its own, without AG7's street stage: its bridge piers would add
    foam.)"""
    base, _ = _small()
    _water(base, tmp_path)
    gold = json.loads(GOLDEN.read_text())
    assert WB.outputs_digest(tmp_path)["all"] == gold["small"]["all"]


def test_vesper_bay_water_golden(tmp_path):
    from assetgen import canon as C
    from assetgen.streets import build as SB
    from agtools import CITIES, built_sample
    path = next(p for p in CITIES if p.parent.name == "vesper_bay")
    built, _, data = built_sample(path)
    SB.build(built.model, C.sha256_bytes(data), tmp_path, None, workers=2)
    rep = WB.build(built.model, C.sha256_bytes(data), tmp_path, None, workers=2)
    assert rep["ok"], [c for c in rep["checks"] if not c["ok"]]
    want = json.loads(GOLDEN.read_text())["vesper_bay"]
    got = WB.outputs_digest(tmp_path)
    assert {t: got["tiles"][t] for t in want["tiles"]} == want["tiles"]
    assert got["all"] == want["all"]
