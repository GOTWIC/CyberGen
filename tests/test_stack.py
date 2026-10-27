"""M12: stack and turbine interchanges where two highways cross, on a test crossing of two
straight highways on open land (the M7 stage alone), and their checks on a built city."""

import math
from types import SimpleNamespace as NS

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, Polygon, box

from citygen import elevated as EL
from citygen import geom as G

HALF = 1900.0


def _seg(i, a, b, pa, pb, n=40):
    pts = [G.qpoint((pa[0] + (pb[0] - pa[0]) * k / n, pa[1] + (pb[1] - pa[1]) * k / n))
           for k in range(n + 1)]
    L = EL._cum(pts)[-1]
    return {"id": f"rs{i:04d}", "start": a, "end": b, "centerline": pts, "width_m": 30.0,
            "road_class": "highway", "district_ids": ["d0"], "type": "road.highway",
            "name": None, "attrs": {"length_m": G.q(L), "role": "grid"},
            "z_profile": [{"s": 0.0, "z": 0.0}, {"s": G.q(L), "z": 0.0}], "bridge_ids": [],
            "bridge": False}


def _crossing(angle: float = 90.0):
    """Two highways crossing at rn0001 (the origin): one along x, one at `angle` to it."""
    t = math.radians(angle)
    pos = {"rn0001": (0.0, 0.0), "rn0002": (-HALF, 0.0), "rn0003": (HALF, 0.0),
           "rn0004": (-HALF * math.cos(t), -HALF * math.sin(t)),
           "rn0005": (HALF * math.cos(t), HALF * math.sin(t))}
    segs = [_seg(1, "rn0002", "rn0001", pos["rn0002"], pos["rn0001"]),
            _seg(2, "rn0001", "rn0003", pos["rn0001"], pos["rn0003"]),
            _seg(3, "rn0004", "rn0001", pos["rn0004"], pos["rn0001"]),
            _seg(4, "rn0001", "rn0005", pos["rn0001"], pos["rn0005"])]
    nodes = [{"id": k, "position": (G.q(v[0]), G.q(v[1]), 0.0),
              "attrs": {"kind": "junction" if k == "rn0001" else "edge"}}
             for k, v in sorted(pos.items())]
    return NS(nodes=nodes, segments=segs, bridges=[])


def _ctx(wet=None):
    canvas = box(-2000.0, -2000.0, 2000.0, 2000.0)
    return NS(wet=wet if wet is not None else
              Polygon([(2500, 2500), (2600, 2500), (2600, 2600)]),
              closed_all=shapely.Polygon(), canvas_inner=canvas.buffer(-5.0),
              dry_inner=canvas.buffer(-10.0), did={}, polygons={})


def _spec(crossings="stack"):
    return NS(highways=NS(elevated_share=0.3, crossings=crossings), districts=[])


def _build(crossings="stack", angle=90.0, wet=None):
    net = _crossing(angle)
    st = EL.elevate(_spec(crossings), _ctx(wet), net)
    return net, st


def _ramps(net):
    return [s for s in net.segments if s["attrs"].get("role") == "ramp"]


def _prof(s):
    return [(z["s"], z["z"]) for z in s["z_profile"]]


@pytest.fixture(scope="module")
def stack():
    return _build("stack")


@pytest.fixture(scope="module")
def turbine():
    return _build("turbine")


def test_crossing_is_a_stack_site():
    E = EL.Elev(_ctx(), _crossing())
    sites = E.stack_sites()
    assert [s[0] for s in sites] == ["rn0001"]
    E.plan_stacks()
    plan = E.stack_plan["rn0001"]
    up = {s["id"] for s in E.net.segments if s["attrs"].get("elevated")}
    assert up == set(plan["lift"]) and len(up) == 2


def test_stack_has_eight_directional_ramps(stack):
    net, st = stack
    assert st["interchanges"] == {"stack": 1}, st
    rs = _ramps(net)
    assert len(rs) == 8
    turns = sorted(s["attrs"]["turn"] for s in rs)
    assert turns == ["left"] * 4 + ["right"] * 4
    for s in rs:
        assert s["one_way"] and s["attrs"]["template"] == "stack"
        assert not s["attrs"].get("loop") and s["attrs"]["crossing"] == [0.0, 0.0]


def test_stack_levels(stack):
    """Four levels: the highway at grade, the lifted one at 9 m over it, the left ramps from
    the ground highway at tier 2 (18 m) and those from the lifted one at tier 3 (27 m)."""
    net, _ = stack
    up = [s for s in net.segments if s["attrs"].get("elevated")]
    over = [s for s in up if s["attrs"].get("overpass_at")]
    assert over and all(max(z for _, z in _prof(s)) == EL.LEVEL_Z[1] for s in over)
    left = [s for s in _ramps(net) if s["attrs"]["turn"] == "left"]
    for s in left:
        tier = s["attrs"]["tier"]
        assert s["level"] == tier
        assert abs(max(z for _, z in _prof(s)) - EL.LEVEL_Z[tier]) < 0.05, s["id"]
    for s in _ramps(net):
        if s["attrs"]["turn"] == "right":
            assert s["level"] == 1 and max(z for _, z in _prof(s)) <= EL.LEVEL_Z[1] + 0.01


def test_stack_grades_and_ends(stack):
    """Every ramp at most 6% steep, from one highway at its height to the other at its."""
    net, _ = stack
    nz = {n["id"]: n["position"][2] for n in net.nodes}
    for s in net.segments:
        p = _prof(s)
        for (s0, z0), (s1, z1) in zip(p, p[1:]):
            if s1 - s0 > 1e-6:
                assert (abs(z1 - z0) - 0.01) / (s1 - s0) <= EL.MAX_GRADE + 1e-4, s["id"]
        assert abs(p[0][1] - nz[s["start"]]) < 0.05 and abs(p[-1][1] - nz[s["end"]]) < 0.05
    for s in _ramps(net):
        ends = sorted([_prof(s)[0][1], _prof(s)[-1][1]])
        assert ends == [0.0, EL.LEVEL_Z[1]], (s["id"], ends)


def _clear(net):
    """Pairs of roads that cross without a node and lack the clearance (5.5 m and the deck)."""
    segs = net.segments
    bad = []
    for i, a in enumerate(segs):
        la = LineString(a["centerline"])
        for b in segs[i + 1:]:
            if {a["start"], a["end"]} & {b["start"], b["end"]}:
                continue
            lb = LineString(b["centerline"])
            if not la.crosses(lb):
                continue
            for p in EL.G_points(la.intersection(lb)):
                za = EL._z_at(_prof(a), la.project(shapely.Point(p)))
                zb = EL._z_at(_prof(b), lb.project(shapely.Point(p)))
                if abs(za - zb) < EL.CLEAR_M + EL.DECK_M - 0.05:
                    bad.append((a["id"], b["id"], round(za, 1), round(zb, 1)))
    return bad


def test_stack_clearances(stack):
    net, _ = stack
    assert not _clear(net)


def test_stack_crossings_are_shared(stack):
    """In a stack each tier-3 ramp crosses both tier-2 ramps over a highway (the fourth
    level); the two ramps of a tier never meet."""
    net, _ = stack
    left = [s for s in _ramps(net) if s["attrs"]["turn"] == "left"]
    t2 = [LineString(s["centerline"]) for s in left if s["attrs"]["tier"] == 2]
    t3 = [LineString(s["centerline"]) for s in left if s["attrs"]["tier"] == 3]
    assert not t2[0].intersects(t2[1]) and not t3[0].intersects(t3[1])
    hw = [LineString(s["centerline"]) for s in net.segments
          if s["attrs"].get("role") != "ramp"]
    for a in t3:
        for b in t2:
            pts = EL.G_points(a.intersection(b))
            assert len(pts) == 1
            assert min(h.distance(shapely.Point(pts[0])) for h in hw) < 1.0


def test_turbine(turbine):
    """The turbine: eight directional ramps, its left ramps crossing each highway at points
    of their own, as high as the roads under them need (below the stack's tier 3)."""
    net, st = turbine
    assert st["interchanges"] == {"turbine": 1}, st
    rs = _ramps(net)
    assert len(rs) == 8 and not _clear(net)
    left = [s for s in rs if s["attrs"]["turn"] == "left"]
    assert all("tier" not in s["attrs"] for s in left)
    assert max(z for s in left for _, z in _prof(s)) < EL.LEVEL_Z[3] - 2.0
    for h in (s for s in net.segments if s["attrs"].get("role") != "ramp"):
        hl = LineString(h["centerline"])
        hits = sorted(hl.project(shapely.Point(p)) for s in left
                      for p in EL.G_points(hl.intersection(LineString(s["centerline"]))))
        assert all(b - a >= 15.0 for a, b in zip(hits, hits[1:])), h["id"]


def test_turbine_is_the_stacks_fallback(monkeypatch):
    """A stack that does not fit falls back to the turbine, and the reverse."""
    orig = EL.Elev._system

    def no_stack(self, r, k, g, gk, variant, ic):
        if variant == "stack":
            return None, "test: no room"
        return orig(self, r, k, g, gk, variant, ic)

    monkeypatch.setattr(EL.Elev, "_system", no_stack)
    net, st = _build("stack")
    assert st["interchanges"] == {"turbine": 1}
    assert any("stack at rn0001: test: no room" in n for n in st["notes"])


def test_no_room_keeps_the_old_crossing(monkeypatch):
    """Where neither fits, the stage runs again without the plan: the crossing is what M7
    made of it before (the lifted highway's window back to the ground)."""
    monkeypatch.setattr(EL.Elev, "_system", lambda self, *a: (None, "test: no room"))
    net, st = _build("stack")
    assert not _ramps(net)
    assert any("stacks:" in n for n in st["notes"])
    monkeypatch.setattr(EL.Elev, "plan_stacks", lambda self: None)
    ref, st_ref = _build("stack")
    assert [s["centerline"] for s in net.segments] == [s["centerline"] for s in ref.segments]
    assert [s["z_profile"] for s in net.segments] == [s["z_profile"] for s in ref.segments]
    assert {k: v for k, v in st.items() if k != "notes"} == \
        {k: v for k, v in st_ref.items() if k != "notes"}


def test_water_in_the_way():
    """A canal across the ground highway inside the stack's reach: no stack, no turbine."""
    wet = Polygon([(-2000, -360), (2000, -360), (2000, -300), (-2000, -300)])
    net, st = _build("stack", wet=wet)
    assert not _ramps(net) or "stack" not in st.get("interchanges", {})


@pytest.mark.parametrize("angle", [80.0, 70.0])
def test_skewed_stack(angle):
    net, st = _build("stack", angle=angle)
    assert st["interchanges"] == {"stack": 1}, st["notes"]
    assert len(_ramps(net)) == 8 and not _clear(net)


def test_deterministic():
    a, _ = _build("stack")
    b, _ = _build("stack")
    assert [s["centerline"] for s in a.segments] == [s["centerline"] for s in b.segments]
    assert [s["z_profile"] for s in a.segments] == [s["z_profile"] for s in b.segments]


def test_stack_columns_fit(stack):
    """Over the core, a left ramp's stretches over the highways (where no column can stand)
    stay within `STACK_SPAN_M`: its diagonal crosses them square enough, apart."""
    net, _ = stack
    hw = [LineString(h["centerline"]) for h in net.segments if h["attrs"].get("role") != "ramp"]
    reach = 15.0 + EL.COLUMN_DEFAULT_M / 2.0 + 0.5
    for s in (s for s in _ramps(net) if s["attrs"]["turn"] == "left"):
        line = LineString(s["centerline"])
        run = best = 0.0
        for d in np.arange(0.0, line.length, 2.5).tolist():
            p = line.interpolate(d)
            core = p.distance(shapely.Point(0.0, 0.0)) <= EL.STACK_CORE_M
            run = run + 2.5 if core and min(h.distance(p) for h in hw) < reach else 0.0
            best = max(best, run)
        assert 0.0 < best <= EL.STACK_SPAN_M, (s["id"], best)


def _with_tee(x: float, side: int):
    """The test crossing with an avenue meeting the lifted highway (along x) at (x, 0)."""
    net = _crossing()
    segs = [s for s in net.segments if s["id"] != "rs0002"]
    segs.insert(1, _seg(2, "rn0001", "rn0006", (0.0, 0.0), (x, 0.0), n=20))
    segs.append(_seg(5, "rn0006", "rn0003", (x, 0.0), (HALF, 0.0), n=20))
    av = _seg(6, "rn0006", "rn0007", (x, 0.0), (x, side * 900.0), n=20)
    av.update(road_class="avenue", type="road.avenue", width_m=20.0)
    segs.append(av)
    net.segments = segs
    net.nodes += [{"id": "rn0006", "position": (G.q(x), 0.0, 0.0), "attrs": {"kind": "junction"}},
                  {"id": "rn0007", "position": (G.q(x), G.q(side * 900.0), 0.0),
                   "attrs": {"kind": "edge"}}]
    return net


@pytest.mark.parametrize("x,side", [(450.0, 1), (600.0, -1)])
def test_avenue_junction_under_the_lifted_deck(x, side):
    """An avenue meeting the lifted highway among the stack's ramps, whose own ramps do not
    fit there, stays at grade under the deck (the viaduct does not come down for it)."""
    net = _with_tee(x, side)
    st = EL.elevate(_spec(), _ctx(), net)
    assert st["interchanges"] == {"stack": 1}, st["notes"]
    av = [s for s in net.segments if s["road_class"] == "avenue"]
    assert av and all(z["z"] == 0.0 for s in av for z in s["z_profile"])
    deck = [s for s in net.segments if s["attrs"].get("elevated")]
    assert all(z["z"] >= EL.LEVEL_Z[1] - 0.01 for s in deck for z in s["z_profile"]
               if abs(G.q(s["centerline"][0][1])) < 1.0 and abs(_at_x(s, z["s"]) - x) < 60.0)
    assert not _clear(net)


def _at_x(s, d):
    return LineString(s["centerline"]).interpolate(d).x


def test_a_stack_never_built_is_dropped(monkeypatch):
    """A planned stack the stage did not build (its node no longer inside a run, say) is
    dropped like one that did not fit: the crossing is what M7 makes of it."""
    monkeypatch.setattr(EL.Elev, "stack_ic", lambda self, r, k: None)
    net, st = _build("stack")
    monkeypatch.setattr(EL.Elev, "plan_stacks", lambda self: None)
    ref, st_ref = _build("stack")
    assert [s["centerline"] for s in net.segments] == [s["centerline"] for s in ref.segments]
    assert [s["z_profile"] for s in net.segments] == [s["z_profile"] for s in ref.segments]


def test_winding():
    """The builder's own measure of a ramp's turn (left positive), as the check takes it."""
    quarter = [(100.0 * math.sin(math.radians(a)), 100.0 - 100.0 * math.cos(math.radians(a)))
               for a in range(0, 91, 3)]
    from citygen import elevated_checks as EC

    for pts, sign in ((quarter, 1.0), ([(x, -y) for x, y in quarter], -1.0)):
        w = EL._winding(pts)
        assert 75.0 < sign * w <= 90.0 and abs(w - EC._turning(pts)) < 1.0
    assert abs(EL._winding([(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)])) < 1e-9
