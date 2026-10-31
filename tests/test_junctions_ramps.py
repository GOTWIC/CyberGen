"""M18: junctions and ramps (`docs/run_through_1.md`).

Covers junction levels (legs held level out past their polygon, `edge_z` where a leg cannot
be, the surface meeting every leg with no step, and a failing case), the steeper grades
(`highways.grades`, the ramp checks and a failing case), embankments under the low raised
roads, and crossings by need (signal spacing, crosswalk widths, Old Town's signals halved,
the district knobs and a failing case).
"""

import math

import pytest

from citygen import blockout as BO
from citygen import elevated as EL
from citygen import elevated_checks as EC
from citygen import junctions as JN
from citygen import network_checks as NC
from citygen import streets as ST
from citygen.model import CityModel
from citygen.spec import Grades
from citygen.validate import load_spec

from conftest import ROOT, built_sample

VESPER_BAY = ROOT / "cities" / "vesper_bay" / "city_spec.json"
DELTA = ROOT / "docs" / "progress" / "M1a2" / "delta_megacity" / "city_spec.json"
M18 = ("junction_levels", "ramp_grades", "crossing_spacing", "road_grades", "crosswalks")


def _spec(path=VESPER_BAY):
    return load_spec(path).filled


# --- the built samples ------------------------------------------------------------------

def test_m18_checks_pass_on_a_sample():
    b, _, _ = built_sample(VESPER_BAY)
    checks = {c.id: c for c in b.checks}
    for cid in M18:
        assert cid in checks, cid
        assert checks[cid].passed, (cid, checks[cid].failures[:5])


def test_junctions_meet_their_legs():
    """Every junction's surface (its `edge_z`, else flat at its node) meets each leg where it
    leaves the polygon; most junctions of a flat city are flat, and those that carry a surface
    are drawn through it by the blockout."""
    b, _, _ = built_sample(DELTA)
    m = b.model
    at: dict = {}
    for s in m.road_segments:
        at.setdefault(s.start, []).append(s)
        at.setdefault(s.end, []).append(s)
    ground = {n.id: (n.position[2], n.ground_m) for n in m.road_nodes}
    worst = 0.0
    carry = [j for j in m.junctions if j.edge_z]
    assert carry and len(carry) < len(m.junctions) / 10
    for j in carry:
        ring, hz, legs = NC.junction_surface(m, j, at, ground)
        assert len(hz) == len(ring)
        for lg in legs:
            if lg["stairs"]:
                continue
            s, k = JN.leg_exit(lg["pts"], ring)
            if k < 0:
                continue
            ends = (hz[k], hz[(k + 1) % len(ring)])
            worst = max(worst, max(abs(z - lg["z"](s)) for z in ends))
    assert worst <= NC.LEG_TOL_M
    plan = BO.make_plan(m)
    drapes = [p for o in plan["objects"] if o["category"] == "junction"
              for p in o["parts"] if p["k"] == "drape"]
    assert len(drapes) == len(carry)


def test_levelled_profile():
    """A leg rising at the approach grade from its node: held level out to its run, back on
    its own profile at the catch-up grade, never steeper than it."""
    prof = [{"s": 0.0, "z": 0.0}, {"s": 100.0, "z": 6.5}, {"s": 300.0, "z": 6.5}]
    new, ra, rb = JN._levelled(prof, 300.0, 25.0, 0.0, 0.08)
    assert (ra, rb) == (25.0, 0.0)
    z = lambda s: JN._z_at(new, s)  # noqa: E731
    assert z(0.0) == z(25.0) == 0.0
    assert z(200.0) == pytest.approx(6.5, abs=0.01)
    for a, b in zip(new, new[1:]):
        assert (abs(b["z"] - a["z"]) - 0.01) / (b["s"] - a["s"]) <= 0.08 + 1e-6
    # the holds shrink where the ends' heights leave no room
    new, ra, rb = JN._levelled([{"s": 0.0, "z": 0.0}, {"s": 40.0, "z": 2.0}], 40.0, 20.0,
                               20.0, 0.08)
    assert ra + rb == pytest.approx(40.0 - 2.0 / 0.08, abs=0.02)
    # an end not held keeps its node's height: the hold at the other end shrinks instead
    new, ra, rb = JN._levelled([{"s": 0.0, "z": 2.0}, {"s": 50.0, "z": 0.0}], 50.0, 40.0,
                               0.0, 0.08)
    assert JN._z_at(new, 0.0) == 2.0 and JN._z_at(new, 50.0) == 0.0
    assert ra == pytest.approx(50.0 - 2.0 / 0.08, abs=0.02)


def test_stranded_highway_goes_one_way():
    """A two-way highway whose far node only has ramps leaving it (a trumpet's stem past its
    flyover's landing): no lane can enter it there, so it carries the other way only."""
    def seg(sid, a, b, pts, one_way=False):
        return {"id": sid, "start": a, "end": b, "road_class": "highway", "one_way": one_way,
                "centerline": pts, "z_profile": [{"s": 0.0, "z": 0.0}, {"s": 100.0, "z": 1.0}],
                "attrs": {}}
    net = type("Net", (), {"segments": [
        seg("stem", "a", "b", [(0.0, 0.0), (100.0, 0.0)]),
        seg("r1", "b", "c", [(100.0, 0.0), (200.0, 50.0)], True),
        seg("r2", "b", "d", [(100.0, 0.0), (200.0, -50.0)], True),
        seg("tail", "e", "a", [(-100.0, 0.0), (0.0, 0.0)]),
        seg("r3", "f", "a", [(0.0, -100.0), (0.0, 0.0)], True)]})
    assert JN.one_way_stranded(net) == ["stem"]
    stem = net.segments[0]
    assert stem["one_way"] and (stem["start"], stem["end"]) == ("a", "b")


def test_surface_meets_each_leg():
    """A square junction with a leg rising out of it: the vertices on its cut line take its
    height there, the flat legs' theirs, the curb between blends."""
    ring = [(-6.0, -6.0), (6.0, -6.0), (6.0, 6.0), (-6.0, 6.0)]
    legs = [{"pts": [(0.0, 0.0), (60.0, 0.0)], "z": lambda s: 0.08 * s, "h": 6.0},
            {"pts": [(0.0, 0.0), (-60.0, 0.0)], "z": lambda s: 0.0, "h": 6.0}]
    hz, exits = JN.surface(ring, legs)
    assert [round(s, 2) for _, s, _, _ in exits] == [6.0, 6.0]
    assert hz[1] == hz[2] == pytest.approx(0.48) and hz[0] == hz[3] == 0.0
    s, k = JN.leg_exit(legs[0]["pts"], ring)
    assert (round(s, 2), k) == (6.0, 1)


def test_check_junction_levels_fails():
    b, _, _ = built_sample(VESPER_BAY)
    m = b.model
    j = next(j for j in m.junctions if j.legs >= 3 and not j.level)
    d = m.model_dump(mode="json")
    for x in d["junctions"]:
        if x["id"] == j.id:
            x["edge_z"] = [1.5] * len(x["polygon"]["exterior"])
    c = NC.check_junction_levels(_spec(), CityModel.model_validate(d))
    assert not c.passed and j.id in c.failures[0]


# --- grades and ramps -------------------------------------------------------------------

def test_grades_knob():
    g = Grades()
    assert (g.run, g.run_max, g.ramp, g.ramp_max, g.approach, g.curve_m) == \
        (0.06, 0.07, 0.07, 0.08, 0.065, 30.0)
    with pytest.raises(ValueError):
        Grades(ramp=0.09)
    with EL.grades(Grades(ramp=0.06, ramp_max=0.065, run_max=0.065, approach=0.06,
                          curve_m=40.0)):
        assert (EL.GRADE, EL.MAX_GRADE, EL.APPROACH_GRADE, EL.CURVE_M) == \
            (0.06, 0.065, 0.06, 40.0)
    assert (EL.GRADE, EL.MAX_GRADE, EL.APPROACH_GRADE, EL.CURVE_M) == (0.07, 0.08, 0.065, 30.0)


def test_ramps_at_their_new_grades():
    """The sample's ramps and flyover climb at the ramp grade (steeper than M7's 6%), its
    runs at the run grade, its approaches at most the run maximum."""
    b, _, _ = built_sample(VESPER_BAY)
    st = b.stats["elevated"]["grades"]
    assert 0.06 < st["ramp"]["max"] <= 0.08 + 1e-4
    assert st["run"]["max"] <= 0.07 + 1e-4 and st["approach"]["max"] <= 0.07 + 1e-4


def test_check_ramp_grades_fails():
    b, _, _ = built_sample(VESPER_BAY)
    d = b.model.model_dump(mode="json")
    s = next(x for x in d["road_segments"] if x["attrs"].get("role") == "ramp")
    p = s["z_profile"]
    p[len(p) // 2]["z"] += 4.0
    m = CityModel.model_validate(d)
    assert not EC.check_ramp_grades(_spec(), m).passed


# --- embankments ------------------------------------------------------------------------

def test_embankments_under_low_raised_roads():
    """Every raised road over land lower than EMBANKMENT_M stands on an embankment there, its
    columns only where it is higher; the blockout fills under it."""
    b, _, _ = built_sample(VESPER_BAY)
    m = b.model
    emb = [s for s in m.structures if s.kind == "embankment"]
    assert emb
    seg = {s.id: s for s in m.road_segments}
    for e in emb:
        s = seg[e.attrs["road_id"]]
        assert e.supports == [s.id] and 0.05 < e.z1_m <= EL.EMBANKMENT_M + 1e-6
        assert all(0.0 < p[2] <= EL.EMBANKMENT_M + 1e-6 for p in e.line)
    for c in m.structures:
        if c.kind == "column" and (c.attrs or {}).get("road_id"):
            assert c.z1_m >= EL.SUPPORT_MIN_UNDER_M - 1e-6
    plan = BO.make_plan(m)
    fills = [p for o in plan["objects"] for p in o["parts"] if p.get("m") == "embankment"]
    assert fills
    assert b.stats["elevated"]["embankments"] == len(emb)


# --- crossings by need ------------------------------------------------------------------

def _grid(n: int, step: float, avenue_row: int | None = None) -> tuple:
    """Legs of an n x n street grid `step` apart (row `avenue_row` an avenue)."""
    segs = []

    def node(i, k):
        return f"n{i}_{k}"
    for i in range(n):
        for k in range(n):
            x, y = i * step, k * step
            if i + 1 < n:
                cls = "street"
                segs.append(_seg(f"h{i}_{k}", node(i, k), node(i + 1, k),
                                 [(x, y), (x + step, y)], "avenue" if k == avenue_row else cls))
            if k + 1 < n:
                segs.append(_seg(f"v{i}_{k}", node(i, k), node(i, k + 1),
                                 [(x, y), (x, y + step)]))
    net = type("Net", (), {"segments": segs})
    legs = JN.legs_at(net, lambda s: "midtown_mixed")
    for nid in legs:
        JN.cutbacks(legs[nid], cap=False)
    return legs


def _seg(sid, a, b, pts, cls="street"):
    from citygen import roads as RD

    cs = RD._cross_section(cls, "grid", None) if cls in ST.PRIMARY else \
        ST.cross_section(cls, "midtown_mixed")
    return {"id": sid, "start": a, "end": b, "road_class": cls, "width_m": cs["total_width_m"],
            "centerline": pts, "cross_section": cs, "z_profile": [], "attrs": {}}


def test_signals_are_spaced():
    """On an avenue crossing a grid of streets 80 m apart, every other junction along it is
    signalized (none within 120 m of another along a road), the street crossings off it
    likewise; a district with 'none' gets none."""
    legs = _grid(6, 80.0, avenue_row=2)
    arch = {nid: "midtown_mixed" for nid in legs}
    sig, gap = JN.plan_signals(legs, arch, lambda nid: ("auto", "auto"))
    assert sig
    for nid in sig:
        if sum(x.cls in ST.PRIMARY for x in legs[nid]) >= 3:
            continue
        assert not (JN.reach(legs, nid, gap[nid]) & (sig - {nid})), nid
    on_avenue = sorted(n for n in sig if n.endswith("_2"))
    assert 2 <= len(on_avenue) <= 3
    assert not JN.plan_signals(legs, arch, lambda nid: ("none", "auto"))[0]
    fewer, _ = JN.plan_signals(legs, arch, lambda nid: ("fewer", "auto"))
    assert len(fewer) < len(sig)


def test_crosswalk_widths():
    assert JN.crosswalk_w("street", "old_town") == 3.0
    assert JN.crosswalk_w("avenue", "old_town") == 4.0
    assert JN.crosswalk_w("avenue", "corporate_core") == 5.0
    assert JN.crosswalk_w("alley", "corporate_core") == 0.0


def test_old_town_keeps_half_its_signals():
    """Delta's Old Town (117 signalized junctions and 123 with crosswalks before M18) keeps
    at most half of each."""
    b, _, _ = built_sample(DELTA)
    m = b.model
    old = next(d for d in m.districts if d.archetype == "old_town")
    js = [j for j in m.junctions if j.attrs.get("archetype") == "old_town"]
    assert js, old.name
    assert sum(j.signalized for j in js) <= 117 // 2
    assert sum(bool(j.crosswalk_ids) for j in js) <= 123 // 2
    widths = {(x.attrs["road_class"], x.width_m) for x in m.crosswalks}
    assert ("street", 3.0) in widths and not any(c in ("alley", "service") for c, _ in widths)


def test_check_crossing_spacing_fails():
    b, _, _ = built_sample(VESPER_BAY)
    d = b.model.model_dump(mode="json")
    x = next(c for c in d["crosswalks"] if c["attrs"]["road_class"] == "street")
    x["width_m"] = 4.0
    c = NC.check_crossing_spacing(_spec(), CityModel.model_validate(d))
    assert not c.passed and x["id"] in " ".join(c.failures)


def test_spec_knob_for_crossings():
    spec = _spec()
    d = spec.model_dump(mode="json")
    d["districts"][0]["junctions"] = {"signals": "none", "crosswalks": "none"}
    from citygen.spec import CitySpec
    s2 = CitySpec.model_validate(d)
    assert s2.districts[0].junctions.signals == "none"
    assert math.isclose(JN.spacing("old_town", "fewer"), 400.0)
    assert math.isclose(JN.spacing("corporate_core"), 120.0)
