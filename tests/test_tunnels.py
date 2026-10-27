"""M9: tunnels. The profile envelope, the spec fields, a small city with a cut-and-cover
tunnel (its network, parts, metro and underpasses), each tunnel check with a failing case,
the sample tunnels (Nexus City cut-and-cover, Peninsula City immersed tube) and the
blockout plan."""

import copy
import json

import pytest
from shapely.geometry import LineString, Point

from citygen import blockout as BO
from citygen import checks as C
from citygen import tunnel_checks as TNC
from citygen import tunnels as TN
from citygen.build import build_city
from citygen.model import CityModel
from citygen.validate import validate_spec

from conftest import ROOT, SMALL, built_sample

TUNNEL_CHECKS = {"tunnel_grades", "tunnel_cover", "tunnel_portals", "tunnel_clash"}
# the small city with tunnels asked under three districts: one fits (under Harbor)
SPEC = {"under": ["Core", "Uptown", "Harbor"], "water": "prefer"}


def _spec(**tunnels):
    d = copy.deepcopy(SMALL)
    d["highways"] = {"tunnels": tunnels}
    return d


@pytest.fixture(scope="module")
def city():
    result = validate_spec(_spec(**SPEC))
    assert result.ok, [str(i) for i in result.errors]
    return build_city(result)


def _rerun(model: CityModel) -> dict:
    spec = validate_spec(_spec(**SPEC)).filled
    return {c.id: c for c in TNC.run(spec, model)}


def _mutate(model: CityModel, fn) -> CityModel:
    data = json.loads(model.to_json())
    fn(data)
    return CityModel.model_validate(data)


def _road(d):
    return [t for t in d["tunnels"] if t["kind"] in ("cut_and_cover", "immersed_tube")]


# --- profiles and spec ------------------------------------------------------------------------

def test_envelope_meets_the_needs_at_the_grade():
    needs = [(400.0, 480.0, TN.water_need("river") + TN.PAD_M),
             (650.0, 680.0, TN.covered_need("immersed_tube") + TN.PAD_M)]
    prof = TN.envelope(1200.0, needs)
    for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
        assert abs(z1 - z0) / (s1 - s0) <= TN.GRADE + 0.003
    assert max(z for s, z in prof if 400.0 <= s <= 480.0) <= -TN.water_need("river") + 0.1
    lo, hi = TN.sunk(prof)
    assert 0.0 < lo < 400.0 - TN.water_need("river") / TN.GRADE + 30.0
    assert hi < 1200.0
    a, b = TN.crossing_at(prof, TN.portal_z("immersed_tube"))
    assert lo < a < 400.0 and 680.0 < b < hi


def test_depth_rules():
    assert TN.water_need("sea") > TN.water_need("river") > TN.water_need("canal")
    # a portal is where the roof top meets the ground
    assert TN.portal_z("cut_and_cover") == -(TN.CLEAR_M + TN.ROOF_M)
    assert TN.covered_need("cut_and_cover") - TN.CLEAR_M - TN.ROOF_M == TN.COVER_M
    assert TN.foundation_m(10) < TN.foundation_m(40) < TN.foundation_m(100) < \
        TN.foundation_m(300)


def test_spec_fields_validate():
    ok = validate_spec(_spec(water="prefer", under=["Core"], underpasses=0.2))
    assert ok.ok
    assert ok.filled.highways.tunnels.under == ["Core"]
    bad = validate_spec(_spec(under=["Nowhere"]))
    assert not bad.ok and any("tunnels.under" in str(i) for i in bad.errors)
    d = _spec()
    d["water"]["bridges"] = {"named": [{"name": "Foot Way", "kind": "pedestrian",
                                        "connects": ["Core", "Harbor"], "tunnel": True}]}
    assert not validate_spec(d).ok
    assert validate_spec(_spec()).filled.highways.tunnels.water == "auto"


# --- the small city ---------------------------------------------------------------------------

def test_city_passes_with_a_tunnel(city):
    failed = [(c.id, c.failures[:3]) for c in city.checks if not c.passed]
    assert not failed, failed
    assert TUNNEL_CHECKS <= {c.id for c in city.checks}
    road = [t for t in city.model.tunnels if t.kind == "cut_and_cover"]
    assert len(road) == 1
    t = road[0]
    assert t.attrs["district"] == next(d.id for d in city.model.districts
                                       if d.name == "Harbor")
    assert len(t.portals) == 2 and all(p.position[2] == TN.portal_z(t.kind)
                                       for p in t.portals)
    assert t.segment_ids
    segs = {s.id: s for s in city.model.road_segments}
    for sid in t.segment_ids:
        s = segs[sid]
        assert s.tunnel and s.level == -1 and t.id in s.tunnel_ids
        assert min(z.z for z in s.z_profile) <= -TN.covered_need(t.kind) + 0.01
    assert city.stats["tunnels"]["by_kind"]["cut_and_cover"]["count"] == 1


def test_tunnel_parts(city):
    m = city.model
    t = next(t for t in m.tunnels if t.kind == "cut_and_cover")
    kinds = sorted(s.kind for s in m.structures if (s.attrs or {}).get("tunnel") == t.id)
    assert kinds.count("portal") == 2 and kinds.count("trench") == 2
    if t.attrs["covered_m"] >= TN.VENT_MIN_M:
        assert t.vent_ids and "vent" in kinds
    # nothing junctions on the sunk stretch: the tunnel road's own nodes are at the ground
    nz = {n.id: n.position[2] for n in m.road_nodes}
    for s in m.road_segments:
        if s.tunnel:
            assert nz[s.start] == 0.0 and nz[s.end] == 0.0


def test_metro_runs_in_tunnels(city):
    m = city.model
    metro = [t for t in m.tunnels if t.kind == "metro"]
    if not any(ln.mode == "metro" for ln in m.transit_lines):
        pytest.skip("no metro")
    assert metro
    st = {s.id: s for s in m.stations}
    for t in metro:
        assert t.line_id
        for end in (t.attrs["from_station"], t.attrs["to_station"]):
            assert end is None or end in st


def test_build_checks_equal_a_fresh_run(city):
    fresh = _rerun(city.model)
    built = {c.id: c for c in city.checks}
    for cid in TUNNEL_CHECKS:
        assert fresh[cid].passed == built[cid].passed, cid


def test_check_grades_fails(city):
    def steep(d):
        t = _road(d)[0]
        mid = len(t["line"]) // 2
        t["line"][mid][2] -= 6.0
    assert not _rerun(_mutate(city.model, steep))["tunnel_grades"].passed


def test_check_cover_fails(city):
    def shallow(d):
        t = _road(d)[0]
        mid = len(t["line"]) // 2
        for p in t["line"][mid - 3:mid + 4]:
            p[2] = -5.0
    assert not _rerun(_mutate(city.model, shallow))["tunnel_cover"].passed


def test_check_portals_fails(city):
    def road_over(d):
        t = _road(d)[0]
        a = t["line"][1][:2]
        # a street across the open approach
        s = copy.deepcopy(next(x for x in d["road_segments"] if x["road_class"] == "street"))
        s["id"] = "rs99999"
        s["centerline"] = [[a[0] - 30.0, a[1] - 30.0], [a[0] + 30.0, a[1] + 30.0]]
        s["z_profile"] = [{"s": 0.0, "z": 0.0}, {"s": 84.85, "z": 0.0}]
        d["road_segments"].append(s)
    assert not _rerun(_mutate(city.model, road_over))["tunnel_portals"].passed


def test_check_clash_fails(city):
    def tower(d):
        t = _road(d)[0]
        p = t["line"][len(t["line"]) // 2]
        b = copy.deepcopy(d["buildings"][0])
        b["id"] = "zz.bld"
        ring = [[p[0] - 5, p[1] - 5], [p[0] + 5, p[1] - 5], [p[0] + 5, p[1] + 5],
                [p[0] - 5, p[1] + 5]]
        b["footprint"] = {"exterior": ring, "holes": []}
        b["height_m"] = 200.0
        d["buildings"].append(b)
    assert not _rerun(_mutate(city.model, tower))["tunnel_clash"].passed


def test_underpasses_join_the_walkway_graph(city):
    m = city.model
    walks = {w.id: w for w in m.walkways}
    for t in m.tunnels:
        if t.kind != "pedestrian":
            continue
        kinds = sorted(walks[w].kind for w in t.walkway_ids)
        assert kinds == ["stairs", "stairs", "underpass"]
        for w in t.walkway_ids:
            assert walks[w].neighbors


# --- samples ------------------------------------------------------------------------------------

def test_nexus_city_has_a_cut_and_cover_tunnel():
    b, _, _ = built_sample(ROOT / "docs" / "progress" / "M1a2" / "nexus_city" /
                           "city_spec.json")
    road = [t for t in b.model.tunnels if t.kind == "cut_and_cover"]
    assert len(road) == 1
    names = {d.id: d.name for d in b.model.districts}
    assert names[road[0].attrs["district"]] == "Midtown"
    assert road[0].name == "Midtown Tunnel"
    assert all(c.passed for c in b.checks if c.id in TUNNEL_CHECKS)


def test_peninsula_city_has_an_immersed_tube():
    b, _, _ = built_sample(ROOT / "docs" / "progress" / "M1a2" / "peninsula_city" /
                           "city_spec.json")
    tubes = [t for t in b.model.tunnels if t.kind == "immersed_tube"]
    assert len(tubes) == 1
    t = tubes[0]
    assert t.crosses and t.attrs["under_water_m"] > 0 and t.attrs["replaces"]
    assert t.attrs["deepest_m"] <= -TN.water_need("river") + 0.1
    assert not {x.id for x in b.model.bridges} & set(t.attrs["replaces"])
    assert all(c.passed for c in b.checks if c.id in TUNNEL_CHECKS)


# --- blockout -------------------------------------------------------------------------------

def test_blockout_draws_tunnels(city):
    plan = BO.make_plan(city.model)
    cats = plan["stats"]["by_category"]
    assert cats.get("tunnel", 0) >= 1 and cats.get("tunnel_road", 0) >= 1
    cut = plan["cameras"]["cutaway"]
    t = next(t for t in city.model.tunnels if t.id == cut["tunnel"])
    assert t.kind in ("cut_and_cover", "immersed_tube")
    # the camera looks from the cut side at the tunnel's middle, below the ground
    o, n = cut["origin"], cut["n"]
    assert (cut["eye"][0] - o[0]) * n[0] + (cut["eye"][1] - o[1]) * n[1] > 30.0
    assert cut["target"][2] < 0.0
