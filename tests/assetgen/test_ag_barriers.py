"""Issue #95, barriers and props at junctions: AG7's barrier runs end at their junctions with
a ramped or capped end, a junction carries its own corner barriers clear of its legs'
carriageways and its lanes, AG14's `asset_clash` finds a barrier or a prop on a carriageway,
a junction or a crosswalk or through another barrier, AG8 picks a prop variant that keeps
off the carriageway, and M6's quay railings and median barriers keep off the junctions."""

from types import SimpleNamespace

import numpy as np
import shapely

from assetgen.fit.barriers import barrier_clash
from assetgen.streets import barriers as BR
from assetgen.streets.kit import Mesh
from assetgen.streets.path import Path
from assetgen.streets.roads import Road

from agtools import small_build

STYLE = {"archetype": None, "era": "mixed_modern", "grime": 0.0, "wealth": 0.5, "wear": 1.0}


def _road(L: float = 60.0, W: float = 20.0, z: float = 0.0, ends=()) -> Road:
    seg = {"id": "rs.t", "centerline": [[0.0, 0.0], [L, 0.0]], "width_m": W,
           "road_class": "highway", "z_profile": [{"s": 0.0, "z": z}, {"s": L, "z": z}],
           "cross_section": {"sidewalk_m": [0.0, 0.0], "median_m": 2.0, "curb_m": 0.15},
           "attrs": {}}
    return Road({"seg": seg, "cls": "highway", "ends": list(ends)})


def _verts(m: Mesh, slot: str = "concrete.barrier") -> np.ndarray:
    return np.array(m.slots[slot].pos, dtype=np.float64) / 1000.0


def test_a_stopped_jersey_slopes_down_and_is_closed():
    rd = _road()
    run = BR.runs_of(rd.seg, "highway")[0]
    assert run.name == "median" and run.jersey
    m = Mesh((0.0, 0.0))
    BR.draw_run(m, rd, run, [[5.0, 55.0, "stop", "stop"]])
    P = _verts(m)
    top = P[:, 2].max()
    assert abs(top - (0.81 + 0.05)) < 1e-3
    # at both ends the barrier is down to TOE_F of its height, full height END_M in
    for s in (5.0, 55.0):
        at = P[np.abs(P[:, 0] - s) < 1e-3]
        assert at[:, 2].max() <= 0.05 + 0.81 * BR.TOE_F + 1e-3
    mid = P[np.abs(P[:, 0] - (5.0 + BR.END_M)) < 1e-3]
    assert abs(mid[:, 2].max() - top) < 1e-3
    # closed: both ends carry a cap facing out
    sl = m.slots["concrete.barrier"]
    caps = []
    for t in range(0, len(sl.idx), 3):
        a, b, c = (np.array(sl.pos[i], dtype=np.float64) for i in sl.idx[t:t + 3])
        if np.ptp([a[0], b[0], c[0]]) < 1:
            n = np.cross(b - a, c - a)
            caps.append((a[0] / 1000.0, np.sign(n[0])))
    assert {(round(x), sg) for x, sg in caps} == {(5, -1.0), (55, 1.0)}


def test_a_parapet_is_capped_and_an_open_end_is_not():
    rd = _road(z=8.0)
    rd.seg["attrs"]["elevated"] = True
    runs = {r.name: r for r in BR.runs_of(rd.seg, "highway")}
    assert {"median", "parapet_l", "parapet_r"} <= set(runs)
    assert "guard_l" not in runs            # (raised: parapets, no guard walls)
    m = Mesh((0.0, 0.0))
    BR.draw_run(m, rd, runs["parapet_l"], [[0.0, 60.0, "open", "stop"]])
    P = _verts(m)
    # its full height to the end (a parapet has no ramped end), its outer face at W/2
    assert abs(P[:, 2].max() - (8.05 + BR.PARAPET_H)) < 1e-3
    assert abs(P[:, 1].max() - 10.0) < 1e-3
    xs = {round(p[0] / 1000.0) for p in m.slots["concrete.barrier"].pos}
    assert xs == {0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60}


def test_clip_line_keeps_off_a_leg_and_a_lane():
    """A junction's own barrier is clipped where it would stand on a leg's carriageway (past
    its cut) or in one of the junction's lanes."""
    leg = {"key": "rs.a@s", "exit": (10.0, 0, 0.0), "path": Path([(0.0, 0.0), (60.0, 0.0)]),
           "h": 5.0}
    keep = BR.Keepout([leg], [], None, {"lanes": [{"line": [[-5.0, -20.0], [-5.0, 20.0]],
                                                   "h": 1.75}]})
    assert keep.blocked(20.0, 3.0) and not keep.blocked(5.0, 3.0)
    assert keep.blocked(-5.0, 10.0) and not keep.blocked(-9.0, 10.0)
    parts = BR.clip_line([(-20.0, 8.0), (30.0, 8.0)], [0.0], keep)
    # (the line at 8 m: clear of the leg's carriageway, 5 m and CLEAR_M; cut by the lane)
    assert len(parts) == 2
    assert parts[0][-1][0] < -5.0 - 1.75 + 0.3 and parts[1][0][0] > -5.0 + 1.75 - 0.3


def _fake_packs(pieces: dict):
    """A stand-in for `fit.build.Packs`: {pid: (kind, triangles, materials)}."""
    names, oid = [], {}

    def owner(name):
        if name not in oid:
            oid[name] = len(names)
            names.append(name)
        return oid[name]
    return SimpleNamespace(
        names=names, oid=oid, owner=owner, a=__import__("pathlib").Path("no_such_build/assets"),
        street_ids=lambda: sorted(pieces),
        street_kind=lambda pid: pieces[pid][0],
        street_tris=lambda pid: (np.array(pieces[pid][1], dtype=np.float64), pieces[pid][2]),
        part_mesh=lambda glb, node: None)


def _quad(x0, y0, x1, y1, z):
    return [[[x0, y0, z], [x1, y0, z], [x1, y1, z]], [[x0, y0, z], [x1, y1, z], [x0, y1, z]]]


def _box(x0, y0, x1, y1, z0, z1):
    """A barrier's sides and top (no bottom)."""
    t = _quad(x0, y0, x1, y1, z1)
    s = []
    for (a, b) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)),
                   ((x0, y1), (x0, y0))):
        s += [[[a[0], a[1], z0], [b[0], b[1], z0], [b[0], b[1], z1]],
              [[a[0], a[1], z0], [b[0], b[1], z1], [a[0], a[1], z1]]]
    return t + s


def test_the_check_finds_a_barrier_across_another_road():
    model = SimpleNamespace(road_segments=[], junctions=[], crosswalks=[], bridges=[],
                            lanes=[], props=[])
    road_b = _quad(0.0, -5.0, 100.0, 5.0, 0.05)
    clear = {"rs.b": ("street.road", road_b, ["asphalt.street"] * 2),
             "rs.a": ("street.road", _box(10.0, 8.0, 40.0, 8.45, 0.05, 1.1),
                      ["concrete.barrier"] * 10)}
    r = barrier_clash(_fake_packs(clear), model)
    assert sum(r["counts"].values()) == 0, r
    across = dict(clear)
    across["rs.a"] = ("street.road", _box(20.0, -8.0, 20.45, 8.0, 0.05, 1.1),
                      ["concrete.barrier"] * 10)
    r = barrier_clash(_fake_packs(across), model)
    assert r["counts"]["barrier_on_road"] == 1, r
    assert r["worst"]["barrier_on_road"][0]["on"] == "rs.b"
    # two pieces' barriers through each other
    both = dict(clear)
    both["rs.c"] = ("street.road", _box(20.0, 0.0, 20.45, 12.0, 6.05, 7.1),
                    ["concrete.barrier"] * 10)
    both["rs.a"] = ("street.road", _box(10.0, 8.0, 40.0, 8.45, 6.05, 7.1),
                    ["concrete.barrier"] * 10)
    r = barrier_clash(_fake_packs(both), model)
    assert r["counts"]["barrier_through_barrier"] == 1, r


def test_small_city_runs_end_at_their_junctions():
    """On the small test city every road's barrier runs lie on the road with a known end at
    each side; a jersey that stops (not carried on by its junction) keeps `CLEAR_M` off the
    junctions at its ends. (Whether any barrier crosses anything is AG14's check, which the
    small city passes: `test_ag_fit.py`.)"""
    from assetgen import brief as B
    from assetgen.streets import roads as RD
    from assetgen.streets.ctx import Ctx

    model, _, _ = B.load_model(small_build() / "base")
    cx = Ctx(model)
    spans = stops = 0
    for s in model.road_segments:
        inp = RD.gather(cx, s).inputs
        if "barriers" not in inp:
            continue
        rd = RD.Road(inp)
        polys = [shapely.Polygon(e["junction"]["ring"]) for e in inp["ends"]
                 if e.get("junction")]
        for r in inp["barriers"]:
            run = next(x for x in BR.runs_of(inp["seg"], inp["cls"]) if x.name == r["name"])
            for a, b, ea, eb in r["spans"]:
                spans += 1
                assert 0.0 <= a < b <= rd.L + 1e-6
                assert ea in ("join", "stop", "open", "corner")
                assert eb in ("join", "stop", "open", "corner")
                if not run.jersey:
                    continue
                for sv, e in ((a, ea), (b, eb)):
                    if e != "stop":
                        continue
                    stops += 1
                    x, y, nx, ny, _ = rd.path.frame(sv)
                    for t in (run.t0, run.t1):
                        q = shapely.Point(x + nx * t, y + ny * t)
                        assert all(p.distance(q) > BR.CLEAR_M - 0.05 for p in polys)
    assert spans and stops


def test_a_prop_variant_keeps_off_the_carriageway():
    """AG8 draws the first variant of a prop's family that stands clear of the carriageways
    (#95); a bench on a road's centerline has none."""
    from assetgen import brief as B
    from assetgen.props.gather import _Fit

    model, _, _ = B.load_model(small_build() / "base")
    fit = _Fit(model)
    s = next(s for s in model.road_segments if s.road_class == "street" and not s.bridge and
             max((z.z for z in s.z_profile), default=0.0) < 0.1 and len(s.centerline) >= 2)
    x, y = Path(s.centerline).point(Path(s.centerline).L / 2.0)
    assert not any(fit.clear("bench", "civic", k, x, y, 0.0, 0.0, (1.0, 1.0, 1.0))
                   for k in range(6))
    far = (max(p[0] for p in s.centerline) + 5000.0, 0.0)
    assert fit.clear("bench", "civic", 0, far[0], far[1], 0.0, 0.0, (1.0, 1.0, 1.0))
