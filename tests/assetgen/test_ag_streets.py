"""AG7, street elements (scope 5.3, 9, 14.8): every street element of the small test city
has a valid mesh and (AG17) the pieces drawn from M22's pavement map meet with no gap, packs are kept by hash (a second build writes nothing), the bytes do not
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


def test_sky_tube_rings_and_led_bands():
    """#97: the ribs stand at the model's rings (the piece's stretch of the line's), an LED
    band in the line's color at full brightness on each lit one; a model without rings
    keeps one every 10 m from 5 m in, none lit."""
    from assetgen.streets.materials import led_slot, slot_spec
    from assetgen.streets.transit import LED_W, make_sky_tube
    st = {"id": "tl.x.tb.e0n0", "kind": "tube", "z0_m": 89.0, "z1_m": 96.0,
          "line": [[0.0, 0.0, 96.0], [40.0, 0.0, 96.0], [80.0, 10.0, 96.0]],
          "attrs": {"line_id": "tl.x", "mode": "sky_tube", "width_m": 7.0, "deck_m": 7.0,
                    "color": "#0aa6bd",
                    "rings": [[3.0, True], [12.5, False], [22.0, False], [31.5, True]]}}
    out = make_sky_tube({"st": st, "origin": [40.0, 5.0], "ground_c": None})
    led = led_slot("#0aa6bd")
    assert led == "led.0de0ff" and slot_spec(led) == ("emissive", "#0de0ff", 0.3, 0.0)
    assert not any(K.check(out.mesh.slots).values())
    # 12 beams of 4 quads a ring: 4 ribs, the first and the last lit
    ribs, bands = out.mesh.slots["steel.painted"], out.mesh.slots[led]
    assert len(ribs.idx) == 4 * 12 * 4 * 2 * 3 and len(bands.idx) == 2 * 12 * 4 * 2 * 3
    xs = {round(p[0] / 1000.0 + 40.0, 2) for p in bands.pos}
    assert min(xs) >= 3.0 - LED_W and max(xs) <= 31.5 + LED_W
    assert not any(3.0 + LED_W < x < 31.5 - LED_W for x in xs)
    old = dict(st, attrs={k: v for k, v in st["attrs"].items() if k != "rings"})
    out2 = make_sky_tube({"st": old, "origin": [40.0, 5.0], "ground_c": None})
    assert led not in out2.mesh.slots
    assert len(out2.mesh.slots["steel.painted"].idx) == 8 * 12 * 4 * 2 * 3   # 5, 15, ..., 75


def test_m13_ground_lifts_roads_and_structures():
    """M13's contract: anything stands on the terrain grid at its point (bilinear); AG17: a
    vertex of M22's pavement map stands at its height over that ground, and a road draws its
    faces there (`ROAD_DZ` over it)."""
    from assetgen.streets import pave as PV
    from assetgen.streets.roads import make as make_road
    t = SimpleNamespace(x0=0.0, y0=0.0, cell_m=10.0, natural=[[0.0] * 3] * 3,
                        ground=[[0.0, 10.0, 20.0], [0.0, 10.0, 20.0], [0.0, 10.0, 20.0]],
                        water_levels=[])
    # (AG12: Ground reads M16's water surfaces of the model's water bodies)
    dry = dict(seas=[], rivers=[], channels=[], waterways=[])
    g = Ground(SimpleNamespace(terrain=t, **dry))
    assert g.at(5.0, 5.0) == 5.0 and g.at(15.0, 0.0) == 15.0
    assert abs(g.at(30.0, 30.0) - 20.0) < 1e-3       # clamped to the grid, as M13 samples
    assert Ground(SimpleNamespace(**dry)).samples([(1.0, 2.0)]) is None
    pts = {"a": (0.0, -4.0), "b": (20.0, -4.0), "c": (20.0, 4.0), "d": (0.0, 4.0)}
    net = SimpleNamespace(vertices=[SimpleNamespace(id=k, p=p, z=0.5) for k, p in pts.items()],
                          edges=[SimpleNamespace(id=f"e{u}{v}", kind="outer", v=[u, v])
                                 for u, v in (("a", "b"), ("b", "c"), ("c", "d"), ("d", "a"))])
    face = SimpleNamespace(id="rs.e0n0.pv.cw", owner_id="rs.e0n0", kind="carriageway",
                           band="cw", layer="g0", rings=[["eab", "ebc", "ecd", "eda"]],
                           samples=[])
    m = SimpleNamespace(pavement_net=net, pavement=[face], road_segments=[], **dry)
    PI = PV.Index(m, g)
    assert PI.V["b"][2:] == (20500, 500)              # 20 m of ground and 0.5 m over it
    seg = {"id": "rs.e0n0", "centerline": [[0.0, 0.0], [20.0, 0.0]],
           "z_profile": [{"s": 0.0, "z": 0.5}, {"s": 20.0, "z": 0.5}],
           "ground": [{"s": 0.0, "z": 0.0}, {"s": 20.0, "z": 20.0}], "width_m": 8.0,
           "road_class": "street", "attrs": {},
           "cross_section": {"sidewalk_m": [0.0, 0.0], "median_m": 0.0, "shared": False}}
    inp = {"seg": seg, "cls": "street", "ends": [], "crossings": [], "lanes": [],
           "style": {"archetype": None, "era": "mixed_modern", "grime": 0.0, "wealth": 0.5,
                     "wear": 1.0}, "start": "a", "end": "b", "origin": [10.0, 0.0],
           "faces": [PI.face_input("rs.e0n0.pv.cw")]}
    sl = make_road(inp).mesh.slots["asphalt.street"]
    up = set()
    for k in range(0, len(sl.idx), 3):
        a, b, c = (sl.pos[i] for i in sl.idx[k:k + 3])
        if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 0:
            up |= {a[2], b[2], c[2]}
    assert sorted(up) == [550, 20550]           # (its outer walls reach into the ground)


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


def test_bridge_piers_keep_out_of_the_channel():
    """City open items: a bridge spans a short stretch of water whole and keeps its piers out
    of a canal's or river's navigable channel (AG7 stood one in the middle of every crossing:
    Delta's Old Town canal and two canals' boats turned short of them); the open sea has
    none."""
    from assetgen.streets import structures as ST
    assert ST.pier_spots(0.0, 30.0, 40.0, 8.0) == []           # a canal: spanned whole
    assert ST.pier_spots(0.0, 44.0, 40.0, None) == []          # short, even on the sea
    river = ST.pier_spots(10.0, 130.0, 40.0, 40.0)             # a 120 m river
    assert river and all(s <= 10.0 + 40.0 or s >= 130.0 - 40.0 for s in river)
    assert min(abs(s - 70.0) for s in river) >= 20.0 + ST.PIER_HALF_M - 0.01
    assert len(ST.pier_spots(0.0, 200.0, 40.0, None)) == 5     # the sea: evenly
    inp = {"bridge": {"water_class": "river", "line": [[0.0, 0.0, 9.0], [140.0, 0.0, 9.0]]},
           "wet": [0, 0] + [1] * 25 + [0] * 2}
    (c0, c1), = ST.channels(inp)
    (r0, r1), = ST._wet_runs(inp["wet"], 140.0)
    assert c0 < (r0 + r1) / 2.0 < c1 and c1 - c0 >= 40.0
    spots = ST.pier_spots(r0, r1, 40.0, 40.0)
    assert spots and all(s + 1.2 < c0 or s - 1.2 > c1 for s in spots)


def test_quay_stairs_are_closed():
    """#131: each flight down a quay wall is a closed solid: its only open edges lie on the
    quay wall's face (where it stands against the wall) or at the wall's foot, and its faces
    point up (treads), down the flight (risers, its foot), back along the wall (its top end)
    or out to the water (its side), for the water on either side of the quay's line."""
    from assetgen.streets import water as SW
    for side in (1, -1):
        inp = {"quay": {"line": [[0.0, 0.0], [100.0, 0.0]], "width_m": 5.0}, "side": side,
               "water_z": -1.5, "origin": [0.0, 0.0], "style": {"archetype": "old_town"}}
        out = SW.make_quay(inp)
        assert not any(K.check(out.mesh.slots).values())
        sl = out.mesh.slots["stone.quay"]
        t0, t1, bot = side * 2500, side * 3900, -3000
        for s0 in (30000, 90000):
            tris = []
            for k in range(0, len(sl.idx), 3):
                t = [sl.pos[i] for i in sl.idx[k:k + 3]]
                if all(s0 - 10 <= p[0] <= s0 + 2710 and
                       min(t0, t1) - 10 <= p[1] <= max(t0, t1) + 10 for p in t):
                    tris.append(t)
            assert tris, (side, s0)
            used: dict = {}
            dirs = set()
            for a, b, c in tris:
                for e in ((a, b), (b, c), (c, a)):
                    k = tuple(sorted(e))
                    used[k] = used.get(k, 0) + 1
                n = [(b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]),
                     (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
                     (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])]
                i = max(range(3), key=lambda j: abs(n[j]))
                dirs.add((i, 1 if n[i] > 0 else -1))
            open_ = [e for e, k in used.items() if k == 1]
            assert all((p[1] == t0 and q[1] == t0) or (p[2] == bot and q[2] == bot)
                       for p, q in open_), (side, s0, open_[:4])
            assert dirs == {(2, 1), (0, 1), (0, -1), (1, side)}, (side, s0, dirs)


def _surface_misses(out, origin, line, step: float = 0.5) -> list:
    """The points of a walkway line (every `step`) with no surface of the mesh under them:
    a triangle whose plan holds the point, at most 0.5 m under it and 0.2 m over it (a
    stair's treads round its sloped line)."""
    import math

    import numpy as np
    tris = []
    for sl in out.mesh.slots.values():
        if not sl.idx:
            continue
        P = np.array(sl.pos, dtype=np.float64) / 1000.0
        P[:, 0] += origin[0]
        P[:, 1] += origin[1]
        tris.append(P[np.array(sl.idx).reshape(-1, 3)])
    T = np.concatenate(tris)
    a0, v0, v1 = T[:, 0], T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    flat = np.abs(den) > 1e-9
    miss = []
    segs = list(zip(line, line[1:]))
    for j, (p, q) in enumerate(segs):
        Lp = math.hypot(q[0] - p[0], q[1] - p[1])
        n = max(1, int(math.ceil(Lp / step)))
        # (the walkway's two ends 5 cm in: on the 1 cm grid they may lie a few millimeters
        # past the landing's edge)
        f0 = 0.05 / Lp if j == 0 and Lp > 0.1 else 0.0
        f1 = 1.0 - 0.05 / Lp if j == len(segs) - 1 and Lp > 0.1 else 1.0
        for k in range(n + 1):
            f = f0 + (f1 - f0) * k / n
            x, y, z = (p[i] + (q[i] - p[i]) * f for i in range(3))
            dx, dy = x - a0[:, 0], y - a0[:, 1]
            with np.errstate(divide="ignore", invalid="ignore"):
                u = (dx * v1[:, 1] - v1[:, 0] * dy) / den
                v = (v0[:, 0] * dy - dx * v0[:, 1]) / den
            inside = flat & (u >= -1e-4) & (v >= -1e-4) & (u + v <= 1.0001)
            zs = a0[:, 2] + u * v0[:, 2] + v * v1[:, 2]
            if not np.any(inside & (zs >= z - 0.5) & (zs <= z + 0.2)):
                miss.append((round(x, 2), round(y, 2), round(z, 2)))
    return miss


def test_station_stairs_and_elevators_drawn():
    """Station stairs: AG7 draws every station stair from its structure (citygen's
    `stair_plan`: a stair tower's flights, landings, rails and posts from a 31 m platform; a
    metro's well down 8 m, lined and railed), so every point of its walkway has a tread or
    landing under it; and every elevator's shaft round its walkway from stop to stop."""
    from citygen import transit as CT
    from shapely.geometry import Polygon

    from assetgen.streets import transit as ST
    for z_hi, z_lo in ((31.0, 0.0), (15.8, 0.0), (0.0, -8.0), (3.0, 0.0)):
        n, h, run, L, W, pts = CT.stair_plan(z_hi, z_lo)
        assert h <= CT.FLIGHT_RISE_M + 1e-9 and h / run <= CT.STAIR_GRADE + 1e-9
        c, u = (100.0, 50.0), (0.6, 0.8)
        line = CT._stair_world(c, u, pts)
        v = (-u[1], u[0])
        ring = [[c[0] + u[0] * s * L / 2 + v[0] * t * W / 2,
                 c[1] + u[1] * s * L / 2 + v[1] * t * W / 2]
                for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        st = {"id": "stn.x.sta", "kind": "stair", "z0_m": min(z_lo, 0.0) - 0.3 * (z_lo < 0),
              "z1_m": max(z_hi, 0.0) + 1.1, "footprint": {"exterior": ring, "holes": []},
              "line": [list(p) for p in line],
              "attrs": CT._stair_attrs("stn.x", c, u, L, W, n, h, run)}
        assert ST.maker_for(SimpleNamespace(kind="stair", attrs=st["attrs"])) == \
            "station_stair"
        out = ST.make_station_stair({"st": st, "origin": list(c), "ground_c": None})
        assert out.mesh.triangles > 0 and not any(K.check(out.mesh.slots).values())
        assert _surface_misses(out, c, line) == [], (z_hi, z_lo)
        lo, hi = out.mesh.bounds_mm()
        assert hi[2] / 1000.0 >= z_hi - 0.01 and lo[2] / 1000.0 <= min(z_lo, 0.0) + 0.01
    for z_hi, z_lo in ((20.0, 0.0), (0.0, -8.0)):
        sq = Polygon([(10, 10), (13.2, 10), (13.2, 13.2), (10, 13.2)])
        st = {"id": "stn.x.ela", "kind": "elevator", "z0_m": z_lo - (1.0 if z_lo < 0 else 0),
              "z1_m": z_hi + 3.0, "footprint": {"exterior": [list(p) for p in
                                                            sq.exterior.coords[:-1]],
                                                "holes": []},
              "line": [[11.6, 11.6, 0.0], [11.6, 11.6, z_hi if z_hi else z_lo]],
              "attrs": {"station": "stn.x", "role": "station_elevator", "width_m": 3.2,
                        "doors": [[1.0, 0.0], [0.0, 1.0]], "clear": True}}
        assert ST.maker_for(SimpleNamespace(kind="elevator", attrs=st["attrs"])) == \
            "station_elevator"
        out = ST.make_station_elevator({"st": st, "origin": [11.6, 11.6], "ground_c": None})
        assert not any(K.check(out.mesh.slots).values())
        lo, hi = out.mesh.bounds_mm()
        assert lo[2] / 1000.0 <= z_lo + 0.01 and hi[2] / 1000.0 >= z_hi + 2.5
        assert lo[0] / 1000.0 <= -1.5 and hi[0] / 1000.0 >= 1.5

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
