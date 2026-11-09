"""Issue #95, barriers and props at junctions: AG7's barrier runs end at their junctions with
a ramped or capped end, or (AG17) on the road's port line where the junction carries them
on, a junction's own barriers follow its edge, AG14's `asset_clash` finds a barrier or a
prop on a carriageway, a junction or a crosswalk or through another barrier, AG8 picks a
prop variant that keeps off the carriageway, and M6's quay railings and median barriers keep
off the junctions."""

import math
from types import SimpleNamespace

import numpy as np
import pytest
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


def test_a_junction_chain_splits_where_its_edge_turns_back():
    """AG17: a junction's barrier along its edge is split (each part capped, 1 cm short of
    the turn) where the edge turns back or passes a vertex twice, so no section folds
    through itself."""
    from assetgen.streets.kit import check
    pts = [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [9.0, 1.0, 0.0], [9.0, 6.0, 0.0]]
    parts = BR._split_sharp(pts, (None, None))
    assert len(parts) == 2
    assert abs(parts[0][0][-1][0] - 9.99) < 1e-9 and parts[0][1] == (None, None)
    m = Mesh((0.0, 0.0))
    BR.draw_chain(m, "concrete.barrier", pts, BR.parapet_profile(0.0, "r"))
    assert not any(check(m.slots).values())
    # a port line at an end: the section lies along it, no cap there
    f = BR.chain_frames([[0.0, 0.0, 1.0], [10.0, 0.0, 1.0]], 0.0,
                        ([0.0, 0.0, 0.0, 1.0, 1.25], None))
    assert f[0][3:6] == (0.0, 1.0, 1.25) and f[0][2] == 1.0


def test_a_lane_hit_outside_a_sharp_turn_cuts_both_sides():
    """AG17: a connector lane's corridor met only outside a sharp turn of a junction's
    barrier (it projects onto the turn's vertex) cuts the chain 1 cm either side of the
    vertex, so the two parts' caps never share an edge."""
    pts = [[0, 0, 0], [10000, 0, 0], [5000, -3000, 0]]      # (mm; a sharp right turn)
    corr = shapely.Point(10.3, 0.0).buffer(0.15)            # (outside the turn, meters)
    parts = BR._off_lanes(pts, corr, 0.35)
    assert len(parts) == 2
    (a, _, _), (b, _, _) = parts
    assert a[-1] != b[0]
    assert abs(a[-1][0] - 9990) <= 1 and a[-1][1] == 0
    assert math.hypot(b[0][0] - 10000, b[0][1]) == pytest.approx(10, abs=1)
    assert b[0][1] < 0                                      # (on the leg after the turn)


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
    """On the small test city every road's barrier runs lie between its cuts (where its
    faces of M22's map end, AG17) with a known end at each side, and an end at a cut has
    the road's port line to lie on. (Whether any barrier crosses anything is AG14's check,
    which the small city passes: `test_ag_fit.py`.)"""
    from assetgen import brief as B
    from assetgen.streets import roads as RD
    from assetgen.streets.ctx import Ctx

    model, _, _ = B.load_model(small_build() / "base")
    cx = Ctx(model)
    spans = ported = 0
    for s in model.road_segments:
        inp = RD.gather(cx, s).inputs
        if "barriers" not in inp:
            continue
        rd = RD.Road(inp)
        for r in inp["barriers"]:
            for a, b, ea, eb in r["spans"]:
                spans += 1
                assert rd.s0 - 1e-3 <= a < b <= rd.s1 + 1e-3
                assert ea in ("join", "stop", "open") and eb in ("join", "stop", "open")
                for sv, at in ((a, "start"), (b, "end")):
                    if abs(sv - (rd.s0 if at == "start" else rd.s1)) > 1e-3:
                        continue
                    fr = rd.port_frame(at, 0.0)
                    if fr is None:
                        continue
                    ported += 1
                    R, L = rd.ports[at][0], rd.ports[at][1]
                    assert abs(fr[0] - (R[0] + L[0]) / 2.0) < 1e-9
    assert spans and ported


def test_small_city_footbridge_railings_run_along_the_walk():
    """M22's map leaves footbridges out: a footbridge's railings (the bridge piece's) run
    along its walking surface (`roads.walk_span`, from the junction's outline at each end),
    within it and starting at most a meter in (`FOOT_CLEAR_M` off the junction at the
    railing's own offset), not from M22's cuts about 2 m further in, past the top of its
    stairs."""
    from assetgen import brief as B
    from assetgen.streets import structures as ST
    from assetgen.streets.ctx import Ctx
    from assetgen.streets.roads import gather

    model, _, _ = B.load_model(small_build() / "base")
    cx = Ctx(model)
    n = 0
    for b in sorted(model.bridges, key=lambda b: b.id):
        inp = ST.gather_bridge(cx, b).inputs
        if not inp.get("rails"):
            continue
        ids = list(b.segment_ids) or ST._carriers(cx, b)
        walk = gather(cx, cx.seg[ids[0]]).inputs.get("walk")
        assert walk, b.id
        for r in inp["rails"]:
            assert r["spans"], (b.id, r["name"])
            a, e = r["spans"][0][0], r["spans"][-1][1]
            assert walk[0] - 1e-3 <= a < e <= walk[1] + 1e-3, (b.id, r, walk)
            assert a - walk[0] < 1.0 and walk[1] - e < 1.0, (b.id, r, walk)
            n += 1
    assert n


def test_a_prop_variant_keeps_off_the_carriageway():
    """AG8 draws the first variant of a prop's family that stands clear of the carriageways
    (#95); a bench on a road's centerline has none."""
    from assetgen import brief as B
    from assetgen.props.gather import _Fit

    from assetgen.streets import pave as PV
    from assetgen.streets.ctx import Ground

    model, _, _ = B.load_model(small_build() / "base")
    PI = PV.Index(model, Ground(model))
    fit = _Fit(model, PI)
    s = next(s for s in model.road_segments if s.road_class == "street" and not s.bridge and
             max((z.z for z in s.z_profile), default=0.0) < 0.1 and len(s.centerline) >= 2)
    x, y = Path(s.centerline).point(Path(s.centerline).L / 2.0)
    assert not any(fit.clear("bench", "civic", k, x, y, 0.0, 0.0, (1.0, 1.0, 1.0))
                   for k in range(6))
    far = (max(p[0] for p in s.centerline) + 5000.0, 0.0)
    assert fit.clear("bench", "civic", 0, far[0], far[1], 0.0, 0.0, (1.0, 1.0, 1.0))
