"""M7: elevated highways, ramps, interchanges and road supports; each M7 check with a
failing case, the profile helpers, the grade solver, the blockout categories."""

import copy
import json

import numpy as np
import pytest
from shapely.geometry import LineString

from citygen import blockout as BO
from citygen import checks as C
from citygen import elevated as EL
from citygen.build import build_city
from citygen.model import CityModel
from citygen.validate import load_spec, validate_spec

from conftest import MINIMAL, ROOT, SMALL, built_sample

M7_CHECKS = {"road_grades", "level_continuity", "deck_clearance", "ramps_land",
             "road_supports"}


def _build(data):
    result = validate_spec(data)
    assert result.ok, [str(i) for i in result.errors]
    return build_city(result)


@pytest.fixture(scope="module")
def city():
    return _build(copy.deepcopy(SMALL))


def _rerun(model: CityModel) -> dict:
    spec = validate_spec(copy.deepcopy(SMALL)).filled
    checks, _ = C.run_checks(spec, model)
    return {c.id: c for c in checks}


def _mutate(model: CityModel, fn) -> CityModel:
    data = json.loads(model.to_json())
    fn(data)
    return CityModel.model_validate(data)


def _elevated(d):
    return [s for s in d["road_segments"] if s["attrs"].get("elevated")]


# --- the build ------------------------------------------------------------------------

def test_city_passes_with_elevated_highways(city):
    failed = [(c.id, c.failures[:3]) for c in city.checks if not c.passed]
    assert not failed, failed
    assert M7_CHECKS <= {c.id for c in city.checks}
    st = city.stats["elevated"]
    assert st["elevated_km"] > 0.5 and st["elevated_runs"] >= 1
    assert st["max_deck_m"] >= EL.LEVEL_Z[1] - 0.01
    assert st["road_columns"] > 0


def test_build_checks_equal_a_fresh_run(city):
    fresh = _rerun(city.model)
    for c in city.checks:
        if c.id in M7_CHECKS:
            assert fresh[c.id].passed == c.passed, c.id


def test_runs_land_on_the_ground(city):
    """Every elevated run is joined at both ends to the ground network or a deck, and its
    profile never goes under the ground."""
    nz = {n.id: n.position[2] for n in city.model.road_nodes}
    for s in city.model.road_segments:
        assert all(z.z >= -1e-9 for z in s.z_profile), s.id
        if s.attrs.get("elevated"):
            assert max(z.z for z in s.z_profile) > 0.5, s.id
            assert s.start in nz and s.end in nz


def test_ramps_are_one_way_single_lane(city):
    ramps = [s for s in city.model.road_segments if s.attrs.get("role") == "ramp"]
    for s in ramps:
        assert s.one_way, s.id
        assert s.road_class == "highway" and s.type == "road.highway.ramp"
        assert s.attrs.get("interchange") and s.attrs.get("template")


def test_junctions_stay_at_their_node(city):
    # a ramp leaves its deck at a few degrees: the corner fillet there would run for
    # hundreds of meters, so it is dropped and the junction closes across the gore
    from citygen import geom as G
    m = city.model
    at = {n.id: n.position for n in m.road_nodes}
    assert any(s.attrs.get("role") == "ramp" for s in m.road_segments)
    for j in m.junctions:
        x, y = at[j.node_id][:2]
        x0, y0, x1, y1 = G.from_model_poly(j.polygon).bounds
        assert max(x - x0, x1 - x, y - y0, y1 - y) < 120.0, j.id


def test_report_has_elevated_stats(city):
    rep = city.report()
    assert rep["stage"].startswith("M11") and "elevated highways" in rep["stage"]
    assert "elevated highways" in C.report_text(rep)


# --- failing checks ---------------------------------------------------------------------

def test_check_grades_fails(city):
    def fn(d):
        s = _elevated(d)[0]
        p = s["z_profile"]
        p[len(p) // 2]["z"] += 30.0
    assert not _rerun(_mutate(city.model, fn))["road_grades"].passed


def test_check_continuity_fails(city):
    def fn(d):
        s = _elevated(d)[0]
        nid = s["start"]
        n = next(n for n in d["road_nodes"] if n["id"] == nid)
        n["position"][2] += 3.0
    assert not _rerun(_mutate(city.model, fn))["level_continuity"].passed


def test_check_clearance_fails(city):
    """An elevated segment flattened to the ground crosses what it passed over."""
    m = city.model
    lines = {s.id: LineString(s.centerline) for s in m.road_segments}
    target = None
    for s in m.road_segments:
        if not s.attrs.get("elevated"):
            continue
        ln = lines[s.id]
        for o in m.road_segments:
            if o.id != s.id and not ({s.start, s.end} & {o.start, o.end}) and \
                    o.road_class != "footbridge" and ln.crosses(lines[o.id]):
                target = s.id
                break
        if target:
            break
    if target is None:
        pytest.skip("no road passes under a viaduct in the test city")

    def fn(d):
        s = next(s for s in d["road_segments"] if s["id"] == target)
        for z in s["z_profile"]:
            z["z"] = 0.0
    assert not _rerun(_mutate(m, fn))["deck_clearance"].passed


def test_check_ramps_fails(city):
    if not any(s.attrs.get("role") == "ramp" for s in city.model.road_segments):
        pytest.skip("no ramps in the test city")

    def fn(d):
        s = next(s for s in d["road_segments"] if s["attrs"].get("role") == "ramp")
        s["one_way"] = False
    assert not _rerun(_mutate(city.model, fn))["ramps_land"].passed


def test_check_supports_fails(city):
    def fn(d):
        d["structures"] = [s for s in d["structures"] if not (s.get("attrs") or {}).get(
            "road_id")]
    assert not _rerun(_mutate(city.model, fn))["road_supports"].passed


# --- helpers ----------------------------------------------------------------------------

def test_ramp_run_reaches_the_level():
    run = EL.ramp_run(EL.LEVEL_Z[1])
    assert run * EL.GRADE >= EL.LEVEL_Z[1] - 1e-9


def test_smoothed_profile_keeps_the_grade():
    ss = EL._stations(600.0)
    raw = [min(EL.LEVEL_Z[1], EL.GRADE * max(0.0, s - EL.FLAT_M),
               EL.GRADE * max(0.0, 600.0 - s - EL.FLAT_M)) for s in ss]
    prof = EL.compress(list(zip(ss, EL.smooth(raw))))
    for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
        assert abs(z1 - z0) / (s1 - s0) <= EL.MAX_GRADE + 1e-6
    assert prof[0][1] == pytest.approx(0.0, abs=0.01)
    assert max(z for _, z in prof) == pytest.approx(EL.LEVEL_Z[1], abs=0.05)


def test_grade_solver_spreads_a_bridge_deck():
    """A bridge deck on one segment falls off at the approach grade through the node into
    the next segment."""
    class Net:
        pass

    net = Net()
    net.segments = [
        {"id": "a", "start": "n0", "end": "n1", "centerline": [(0.0, 0.0), (200.0, 0.0)],
         "road_class": "avenue", "attrs": {}, "z_profile": []},
        {"id": "b", "start": "n1", "end": "n2", "centerline": [(200.0, 0.0), (600.0, 0.0)],
         "road_class": "avenue", "attrs": {}, "z_profile": []}]
    net.bridges = [{"segment_ids": ["a"], "s0": 50.0, "s1": 150.0, "clearance_m": 10.0,
                    "line": [(50.0, 0.0, 11.5), (150.0, 0.0, 11.5)], "attrs": {}}]
    EL.solve_grades(net)
    pa = EL._tuples(net.segments[0]["z_profile"])
    pb = EL._tuples(net.segments[1]["z_profile"])
    assert EL._z_at(pa, 100.0) == pytest.approx(11.5, abs=0.01)
    z_node = 11.5 - EL.APPROACH_GRADE * 50.0
    assert EL._z_at(pb, 0.0) == pytest.approx(z_node, abs=0.01)
    assert EL._z_at(pb, 400.0) == pytest.approx(0.0, abs=0.01)
    for p in (pa, pb):
        for (s0, z0), (s1, z1) in zip(p, p[1:]):
            # (1 cm of rounding on the grid)
            assert (abs(z1 - z0) - 0.01) / (s1 - s0) <= EL.APPROACH_GRADE + 1e-6


def test_blockout_draws_viaducts_and_columns(city):
    plan = BO.make_plan(city.model)
    assert "elevated" in {o["category"] for o in plan["objects"]}
    assert "road_support" in plan["materials"]


# --- M7b: partial cloverleaf and trumpet --------------------------------------------------

def test_loops_where_diamonds_do_not_fit(monkeypatch):
    """With no diamond ramp possible, crossings take loop ramps (a partial cloverleaf): every
    M7 check still passes, and each loop climbs at most 6% over its 270 degree turn."""
    monkeypatch.setattr(EL.Elev, "_ramp", lambda self, *a, **k: (None, "test: no diamond"))
    # one worker: the road variants run in this (patched) process
    b = build_city(validate_spec(copy.deepcopy(SMALL)), workers=1)
    failed = [(c.id, c.failures[:3]) for c in b.checks if not c.passed]
    assert not failed, failed
    st = b.stats["elevated"]
    assert st["interchanges"].get("parclo", 0) >= 1
    loops = [s for s in b.model.road_segments if s.attrs.get("template") == "parclo"]
    assert loops and all(s.one_way and s.attrs["role"] == "ramp" for s in loops)

    def ratio(s):
        a, z = s.centerline[0], s.centerline[-1]
        return LineString(s.centerline).length / max(
            ((a[0] - z[0]) ** 2 + (a[1] - z[1]) ** 2) ** 0.5, 1.0)
    # a loop turns about 270 degrees: much longer than the distance between its ends
    assert max(ratio(s) for s in loops) > 2.5


def test_trumpet_geometry(monkeypatch):
    """The two-loop trumpet (the fallback): a ground highway stem at a crossing of a test
    city's viaduct: the stem's stub runs under the deck to the far side, where two loops (the
    left turns) come down to its end; each loop clears the deck and the stub, at most 6%
    steep."""
    seen = {}
    orig = EL.Elev.interchanges

    def keep(self):
        seen["E"] = self
        return orig(self)

    monkeypatch.setattr(EL.Elev, "interchanges", keep)
    build_city(validate_spec(copy.deepcopy(MINIMAL)), local=False, buildings=False, workers=1)
    E = seen["E"]
    found = None
    for r in sorted(E.runs, key=lambda r: r.id):
        hw_w = max(s["width_m"] for s, _ in r.segs)
        for k in range(1, len(r.nodes) - 1):
            n = r.nodes[k]
            on = {r.segs[k - 1][0]["id"], r.segs[k][0]["id"]}
            legs = [s for s in E.inc[n] if s["id"] not in on]
            C, u = EL._at(r.pts, r.cum, r.s_nodes[k])
            for leg in legs:
                v = E.leg_dir(leg, n)
                sigma = 1 if u[0] * v[1] - u[1] * v[0] > 0 else -1
                ic = {"id": "ic99"}
                virt = E._stub_leg(r, k, n, leg, hw_w, C, u, v)
                tr = None if virt is None else E._trumpet(r, k, n, leg, -sigma, hw_w, legs,
                                                          ic, virt)
                if tr is not None:
                    found = (r, tr, hw_w)
                    break
            if found:
                break
        if found:
            break
    assert found is not None, "no crossing of the minimal test city takes a trumpet"
    r, tr, hw_w = found
    loops = tr["ramps"]
    assert sorted(rp["kind"] for rp in loops) == ["off", "on"]
    assert all(rp["loop"] and rp["stub"] for rp in loops)
    assert tuple(loops[0]["T"]) == tuple(loops[1]["T"]) == tuple(tr["end"])
    for rp in loops:
        for (s0, z0), (s1, z1) in zip(rp["prof"], rp["prof"][1:]):
            assert (abs(z1 - z0) - 0.01) / (s1 - s0) <= EL.MAX_GRADE + 1e-6
        ends = [rp["prof"][0][1], rp["prof"][-1][1]]
        assert min(ends) == 0.0 and max(ends) > 2.0


# --- M8d: the trumpet's flyover ------------------------------------------------------------

VESPER_BAY = ROOT / "cities" / "vesper_bay" / "city_spec.json"


def _roads_with_elev(monkeypatch, spec_path):
    """Vesper Bay's roads alone (no local streets or buildings) and the M7 stage that made them."""
    seen = {}
    orig = EL.Elev.interchanges

    def keep(self):
        seen["E"] = self
        return orig(self)

    monkeypatch.setattr(EL.Elev, "interchanges", keep)
    b = build_city(load_spec(spec_path), local=False, buildings=False, workers=1)
    return b, seen["E"]


def _grade_ok(prof) -> bool:
    return all((abs(z1 - z0) - 0.01) / (s1 - s0) <= EL.MAX_GRADE + 1e-6
               for (s0, z0), (s1, z1) in zip(prof, prof[1:]) if s1 > s0)


@pytest.fixture(scope="module")
def nyx_roads():
    mp = pytest.MonkeyPatch()
    try:
        yield _roads_with_elev(mp, VESPER_BAY)
    finally:
        mp.undo()


def test_trumpet_flyover_geometry(nyx_roads):
    """Vesper Bay's trumpet in its textbook form: on the far side one loop (from the stem's near
    terminal, under the deck, round its quadrant) and one flyover for the other left turn.
    The flyover is a level-2 ramp: it leaves the far lanes at the deck, wraps round the
    loop's outside, crosses the deck square with the clearance and the deck under it, comes
    down beside the stem and lands on it at grade; at most 6% steep everywhere."""
    _, E = nyx_roads
    ic = next(i for i in E.icx if i["template"] == "trumpet")
    rps = [rp for rp in E.ramps if rp["ic"] == ic["id"]]
    fly = [rp for rp in rps if rp.get("flyover")]
    loops = [rp for rp in rps if rp["loop"]]
    assert len(fly) == 1 and len(loops) == 1, ic["ramps"]
    fly, loop = fly[0], loops[0]
    assert fly["sigma"] == loop["sigma"] and {fly["kind"], loop["kind"]} == {"off", "on"}
    assert fly["level"] == 2 and not fly["stub"] and not loop["stub"]
    r = next(r for r in E.runs if r.id == ic["run"])
    # the loop starts (or ends) at the stem's near terminal, where the near ramps land, and
    # the stem ends there
    near = [rp for rp in rps if not rp["loop"] and not rp.get("flyover")]
    assert near and all(tuple(rp["T"]) == tuple(loop["T"]) for rp in near)
    assert E.trim[(fly["leg"], ic["node"])] == tuple(loop["T"])
    # ends: on the deck at its height, on the stem at grade
    prof = fly["prof"]
    deck_end, ground_end = (0, -1) if fly["kind"] == "off" else (-1, 0)
    assert prof[deck_end][1] == pytest.approx(r.z(fly["s_far"]), abs=0.02)
    assert prof[ground_end][1] == 0.0
    assert tuple(fly["T"]) == tuple(fly["pts"][ground_end])
    assert _grade_ok(prof) and _grade_ok(loop["prof"])
    # over the deck it clears the run by the clearance and both decks
    pts = fly["pts"]
    cum = EL._cum(pts)
    line = LineString(pts)
    run_line = LineString(r.pts)
    hw = max(s["width_m"] for s, _ in r.segs)
    # (past the taper, which runs on the deck itself)
    off_deck = (lambda q: q > EL.TAPER_M) if fly["kind"] == "off" else \
        (lambda q: q < cum[-1] - EL.TAPER_M)
    over = [q for q in np.arange(0.0, cum[-1], 2.5).tolist()
            if off_deck(q) and run_line.distance(line.interpolate(q)) < hw / 2.0]
    assert over, "the flyover does not cross its run"
    for q in over:
        P = line.interpolate(q)
        z_run = r.z(run_line.project(P))
        assert EL._z_at(prof, q) - z_run >= EL.CLEAR_M + EL.DECK_M - 0.05
    assert max(z for _, z in prof) >= EL.LEVEL_Z[1] + EL.CLEAR_M + EL.DECK_M
    # it wraps round the loop: never over it
    assert line.distance(LineString(loop["pts"])) >= EL.RAMP_W + 1.0


def test_trumpet_falls_back_to_two_loops(monkeypatch):
    """Where the flyover does not fit, the trumpet keeps the two far loops of M7b, both on the
    stub that runs on under the deck."""
    monkeypatch.setattr(EL.Elev, "_flyover", lambda self, *a, **k: (None, "test: no room"))
    _, E = _roads_with_elev(monkeypatch, VESPER_BAY)
    ic = next(i for i in E.icx if i["template"] == "trumpet")
    rps = [rp for rp in E.ramps if rp["ic"] == ic["id"]]
    assert not any(rp.get("flyover") for rp in rps)
    far = [rp for rp in rps if rp["loop"]]
    assert sorted(rp["kind"] for rp in far) == ["off", "on"]
    assert all(rp["stub"] for rp in far) and tuple(far[0]["T"]) == tuple(far[1]["T"])
    assert E.stubs[(far[0]["leg"], ic["node"])] == tuple(far[0]["T"])
    assert E.failed.get("test: no room", 0) >= 1


@pytest.fixture(scope="module")
def nyx_city():
    built, _, _ = built_sample(VESPER_BAY)
    return built


def _flyover_seg(m):
    return next(s for s in m.road_segments if s.attrs.get("flyover"))


def test_flyover_in_the_city(nyx_city):
    """The built city: the flyover is a one-way, single-lane ramp at level 2 on its own
    columns (none in the deck or a road under it), every M7 check passes, and the blockout
    draws it as a raised deck."""
    m = nyx_city.model
    fly = _flyover_seg(m)
    assert fly.one_way and fly.lanes == 1 and fly.level == 2
    assert fly.attrs["template"] == "trumpet" and fly.attrs["role"] == "ramp"
    failed = [(c.id, c.failures[:3]) for c in nyx_city.checks
              if c.id in M7_CHECKS and not c.passed]
    assert not failed, failed
    cols = [s for s in m.structures if (s.attrs or {}).get("road_id") == fly.id]
    assert len(cols) >= 10
    assert max(c.z1_m for c in cols) >= EL.LEVEL_Z[1] + EL.CLEAR_M
    st = nyx_city.stats["elevated"]
    assert st["flyovers"] == 1 and st["max_flyover_m"] > EL.LEVEL_Z[1] + EL.CLEAR_M
    plan = BO.make_plan(m)
    deck = [o for o in plan["objects"] if o["name"] == f"{fly.id}.deck"]
    assert deck and deck[0]["category"] == "elevated"


def _nyx_rerun(model: CityModel) -> dict:
    spec = load_spec(VESPER_BAY).filled
    checks, _ = C.run_checks(spec, model)
    return {c.id: c for c in checks}


def _on_fly(m, fn) -> CityModel:
    fid = _flyover_seg(m).id

    def go(d):
        fn(d, next(s for s in d["road_segments"] if s["id"] == fid))
    return _mutate(m, go)


def test_flyover_checks_fail_on_a_broken_copy(nyx_city):
    """Each M7 check fails on a copy of the city with the flyover broken: its crest lowered
    onto the deck it passes over (clearance), a 30 m spike (grade), its deck end lifted off
    the viaduct (continuity), its ground end lifted off the stem (ramps land), its columns
    gone (supports)."""
    m = nyx_city.model

    def low(d, s):
        top = max(z["z"] for z in s["z_profile"])
        for z in s["z_profile"]:
            z["z"] = round(min(z["z"], EL.LEVEL_Z[1]), 2) if z["z"] > top - 8.0 else z["z"]
    assert not _nyx_rerun(_on_fly(m, low))["deck_clearance"].passed

    def spike(d, s):
        p = s["z_profile"]
        p[len(p) // 2]["z"] += 30.0
    assert not _nyx_rerun(_on_fly(m, spike))["road_grades"].passed

    def step(d, s):
        hi = s["start"] if s["z_profile"][0]["z"] > s["z_profile"][-1]["z"] else s["end"]
        n = next(n for n in d["road_nodes"] if n["id"] == hi)
        n["position"][2] += 2.0
    assert not _nyx_rerun(_on_fly(m, step))["level_continuity"].passed

    def lift(d, s):
        lo_first = s["z_profile"][0]["z"] < s["z_profile"][-1]["z"]
        lo = s["start"] if lo_first else s["end"]
        n = next(n for n in d["road_nodes"] if n["id"] == lo)
        n["position"][2] = 6.0
        (s["z_profile"][0] if lo_first else s["z_profile"][-1])["z"] = 6.0
    assert not _nyx_rerun(_on_fly(m, lift))["ramps_land"].passed

    def bare(d, s):
        d["structures"] = [x for x in d["structures"]
                           if (x.get("attrs") or {}).get("road_id") != s["id"]]
    assert not _nyx_rerun(_on_fly(m, bare))["road_supports"].passed


# --- M7b: art-direction loop ----------------------------------------------------------------

def test_spec_diff_matches_named_items():
    from citygen.review import spec_diff

    a = {"seed": 1, "districts": [{"name": "A", "height_m": [10, 40]}, {"name": "B"}]}
    b = {"seed": 2, "districts": [{"name": "B"}, {"name": "A", "height_m": [12, 50]}]}
    out = spec_diff(a, b)
    assert "seed: 1 -> 2" in out
    assert "districts[A].height_m: [10, 40] -> [12, 50]" in out
    assert "districts: order changed" in out
    assert spec_diff(a, a) == []


def test_review_rounds(city, tmp_path):
    from citygen import review as RV

    r1, r2 = tmp_path / "r1", tmp_path / "r2"
    for d in (r1, r2):
        d.mkdir()
        (d / "report.json").write_text(json.dumps(city.report()))
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(SMALL))
    a = RV.review(r1, spec)
    assert a["round"] == 1 and a["passed"] and (r1 / "review.md").is_file()
    changed = copy.deepcopy(SMALL)
    changed["seed"] = 8
    spec.write_text(json.dumps(changed))
    b = RV.review(r2, spec, prev=r1)
    assert b["round"] == 2 and b["spec_changes"] == ["seed: 7 -> 8"]
    md = (r2 / "review.md").read_text()
    assert "round 2 of at most 3" in md and "`seed: 7 -> 8`" in md
