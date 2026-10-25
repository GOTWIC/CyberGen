"""M7: elevated highways, ramps, interchanges and road supports; each M7 check with a
failing case, the profile helpers, the grade solver, the blockout categories."""

import copy
import json

import pytest
from shapely.geometry import LineString

from citygen import blockout as BO
from citygen import checks as C
from citygen import elevated as EL
from citygen.build import build_city
from citygen.model import CityModel
from citygen.validate import validate_spec

from conftest import SMALL

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


def test_report_has_elevated_stats(city):
    rep = city.report()
    assert rep["stage"].startswith("M7") and "elevated highways" in rep["stage"]
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
