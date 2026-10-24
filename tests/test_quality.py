"""M1a2 visual-quality pass: organic district boundaries, the water_preferred budget,
meandering rivers, deltas without orphan wedges, island bearings, canal quality."""

import copy
import json
import math

import pytest
import shapely
from shapely import affinity
from shapely.geometry import LineString, Point

from citygen import checks as C
from citygen import geom as G
from citygen import hydro as H
from citygen import relations as R
from citygen.build import build_city
from citygen.model import CityModel
from citygen.validate import validate_spec

from conftest import SMALL

# A mainland city with many land boundaries (one river, a bay, seven districts).
MAINLAND = {
    "name": "Budget Bay", "seed": 31, "size_km": [3.0, 3.0],
    "water": {"coast": {"form": "bay", "side": "west", "sea_share": 0.25},
              "rivers": [{"name": "Slate", "from": "east", "to": "bay", "width_m": [50, 90]}]},
    "districts": [
        {"name": "Core", "archetype": "corporate_core", "placement": {"edge": "center"}},
        {"name": "North", "archetype": "megablock_residential", "placement": {"north_of": "Core"}},
        {"name": "Hills", "archetype": "residential_heights",
         "placement": {"edge": "north_east"}},
        {"name": "Docks", "archetype": "industrial_port",
         "placement": {"coast": True, "south_of": "Core"}},
        {"name": "Strand", "archetype": "entertainment_market",
         "placement": {"coast": True, "west_of": "Core"}},
        {"name": "Old", "archetype": "old_town", "placement": {"edge": "south_east"}},
        {"name": "Campus", "archetype": "research_campus", "placement": {"edge": "east"}},
    ],
}

DELTA = {
    "name": "Fanmouth", "seed": 12, "size_km": [3.0, 3.0],
    "water": {"coast": {"form": "delta", "side": "south"},
              "rivers": [{"name": "Main", "from": "north", "to": "sea", "width_m": [80, 120],
                          "meander": 0.4, "delta_branches": 3,
                          "branch_names": ["East Arm", "West Arm", "Far East Arm"]}],
              "islands": [{"name": "Delta Isle", "position": "south", "setting": "delta",
                           "river": "Main", "area_km2": 0.3}],
              "district_separation": "water_preferred"},
    "districts": [
        {"name": "West Bank", "archetype": "old_town", "placement": {"edge": "west"}},
        {"name": "East Bank", "archetype": "corporate_core", "placement": {"edge": "east"}},
        {"name": "Delta Isle", "archetype": "research_campus",
         "placement": {"on_island": "Delta Isle"}},
    ],
}


def _build(data):
    result = validate_spec(data)
    assert result.ok, [str(i) for i in result.errors]
    return build_city(result)


@pytest.fixture(scope="module")
def mainland():
    return _build(copy.deepcopy(MAINLAND))


@pytest.fixture(scope="module")
def delta():
    return _build(copy.deepcopy(DELTA))


def _passes(b):
    assert b.passed, [f for c in b.checks for f in c.failures]


# --- 1. organic district boundaries ----------------------------------------------------

def test_land_boundaries_are_curved(mainland):
    """Shared land boundaries are longer than their chords (power-diagram edges would be
    straight: ratio 1.0)."""
    _passes(mainland)
    polys = {d.name: G.from_model_poly(d.polygon) for d in mainland.model.districts}
    ratios = []
    names = sorted(polys)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared = polys[a].boundary.intersection(polys[b].buffer(0.5))
            if shared.is_empty:
                continue
            merged = shapely.line_merge(shared) if shared.geom_type != "LineString" else shared
            for part in getattr(merged, "geoms", [merged]):
                if isinstance(part, LineString) and part.length > 300:
                    chord = math.dist(part.coords[0], part.coords[-1])
                    if chord > 200:
                        ratios.append(part.length / chord)
    assert ratios, "no shared land boundary longer than 300 m"
    # (M1b: with deterministic math this city builds on hydrology variant 1, whose boundaries
    # are gentler than variant 0's; the 400 m window measure below is the scope-level bar)
    assert all(r > 1.0 for r in ratios) and max(ratios) > 1.015, ratios
    st = mainland.stats
    assert st["land_boundary_curvature"] is not None and st["land_boundary_curvature"] > 1.02


def test_some_district_is_concave(mainland):
    """Organic partition: at least one district is clearly non-convex."""
    concave = [d.name for d in mainland.model.districts
               if G.from_model_poly(d.polygon).area
               < 0.93 * G.from_model_poly(d.polygon).convex_hull.area]
    assert concave


def test_boundary_curvature_measure():
    """Two squares sharing a straight edge read as 1.0; the measure is not inflated."""
    a = G.canvas_for((1.0, 1.0))
    b = affinity.translate(a, 1000.0, 0.0)
    canvas = G.canvas_for((4.0, 4.0))
    samples = R.boundary_samples({"a": a, "b": b}, a.buffer(-1e6), canvas)
    assert R.boundary_curvature(samples, kinds=(1,)) == pytest.approx(1.0, abs=0.01)


# --- 2. water_preferred budget ------------------------------------------------------------

def test_water_preferred_budget(mainland):
    st = mainland.stats
    target = MAINLAND.get("water", {}).get("boundary_water_share", 0.6)
    assert st["boundary_on_water_target"] == target
    assert st["boundary_on_water"] is not None
    # Preferred, not total: land boundaries remain, and the share lands near the target.
    assert st["boundary_km"]["land"] > 0.5
    assert abs(st["boundary_on_water"] - target) < 0.2, st["boundary_on_water"]
    assert "separation_budget" in st and st["separation_budget"]["target"] == target


def test_budget_follows_target():
    low, high = copy.deepcopy(MAINLAND), copy.deepcopy(MAINLAND)
    low["water"]["boundary_water_share"] = 0.0
    high["water"]["boundary_water_share"] = 0.9
    b_low, b_high = _build(low), _build(high)
    n_low = b_low.stats["separation_channels"]
    n_high = b_high.stats["separation_channels"]
    assert n_low == 0
    assert n_high > n_low
    assert b_high.stats["boundary_on_water"] > b_low.stats["boundary_on_water"]


def test_preferred_channels_start_at_water(mainland):
    """A preferred separation channel always connects to other water at one end at least: it
    is never cut just because a boundary touches the map edge."""
    m = mainland.model
    canvas = G.canvas_for(MAINLAND["size_km"])
    for ch in m.channels:
        if ch.kind != "separation":
            continue
        others = [G.from_model_poly(s.polygons[0]) for s in m.seas] + [
            G.from_model_poly(r.polygon) for r in m.rivers] + [
            G.from_model_poly(c.polygon) for c in m.channels if c.id != ch.id]
        ends = [Point(ch.centerline[0]), Point(ch.centerline[-1])]
        wet = [any(o.distance(e) < 15 for o in others) for e in ends]
        assert any(wet), ch.id
        edge = [canvas.exterior.distance(e) < 5 for e in ends]
        assert not all(edge), ch.id


def test_separation_channels_vary_and_meander(mainland):
    seps = [c for c in mainland.model.channels if c.kind == "separation"]
    if not seps:
        pytest.skip("budget met without separation channels")
    for c in seps:
        assert 20.0 <= min(c.width_m) and max(c.width_m) <= 85.0
    assert any(max(c.width_m) - min(c.width_m) > 5.0 for c in seps)


# --- 3. rivers -----------------------------------------------------------------------------

def _hydro(data):
    spec = validate_spec(data).filled
    return spec, H.build_hydro(spec, G.canvas_for(spec.size_km), H.Variant())


def test_river_meanders_and_widens():
    data = copy.deepcopy(SMALL)
    data["water"]["rivers"][0]["meander"] = 0.5
    _, h = _hydro(data)
    r = next(b for b in h.bodies if b.kind == "river")
    cs = r.centerline.coords
    assert r.centerline.length / math.dist(cs[0], cs[-1]) > 1.04
    assert r.widths[-1] > r.widths[0] + 15
    assert not r.centerline.is_ring and r.centerline.is_simple


def test_tributary_joins_downstream_at_acute_angle():
    data = copy.deepcopy(SMALL)
    data["size_km"] = [3.0, 3.0]
    data["water"] = {"coast": {"form": "straight", "side": "south", "sea_share": 0.25},
                     "rivers": [{"name": "Main", "from": "north", "to": "sea"},
                                {"name": "Side", "from": "east", "to": "Main"}]}
    _, h = _hydro(data)
    main = next(b for b in h.bodies if b.name == "Main")
    side = next(b for b in h.bodies if b.name == "Side")
    end = Point(side.centerline.coords[-1])
    d = main.centerline.project(end)
    t = H._tangent(main.centerline, d)
    cs = side.centerline.coords
    v = (cs[-1][0] - cs[-6][0], cs[-1][1] - cs[-6][1])
    cos = (v[0] * t[0] + v[1] * t[1]) / math.hypot(*v)
    assert cos > math.cos(math.radians(75)), math.degrees(math.acos(cos))


def test_tributary_to_at_pins_junction():
    data = copy.deepcopy(SMALL)
    data["size_km"] = [3.0, 3.0]
    data["water"] = {"coast": {"form": "straight", "side": "south", "sea_share": 0.25},
                     "rivers": [{"name": "Main", "from": "north", "to": "sea"},
                                {"name": "Side", "from": "east",
                                 "to": {"edge": "Main", "at": 0.3}}]}
    _, h = _hydro(data)
    main = next(b for b in h.bodies if b.name == "Main")
    side = next(b for b in h.bodies if b.name == "Side")
    frac = main.centerline.project(Point(side.centerline.coords[-1]), normalized=True)
    assert abs(frac - 0.3) < 0.06, frac


# --- 4. deltas -------------------------------------------------------------------------------

def test_delta_splits_inland_and_fans_out(delta):
    _passes(delta)
    h = delta.hydro
    sea = h.sea
    branches = [b for b in h.bodies if b.kind == "delta_branch"]
    assert len(branches) >= 2
    forks = [Point(b.centerline.coords[0]) for b in branches]
    assert max(sea.distance(p) for p in forks) > 300.0
    mouths = [Point(b.centerline.coords[-1]) for b in branches]
    spread = max(a.distance(b) for a in mouths for b in mouths)
    assert spread > 500.0
    for b in branches:  # curved, not straight wedges
        cs = b.centerline.coords
        assert b.centerline.length / math.dist(cs[0], cs[-1]) > 1.01


def test_no_unassigned_delta_wedges(delta):
    m = delta.model
    open_lm = {o.attrs["landmass_id"] for o in m.open_spaces}
    branches = [G.from_model_poly(c.polygon) for c in m.channels if c.kind == "delta_branch"]
    for lm in m.landmasses:
        poly = G.from_model_poly(lm.polygon)
        if any(poly.distance(b) < 5 for b in branches):
            assert lm.district_ids or lm.id in open_lm, lm.id
    for o in m.open_spaces:
        assert o.name and o.kind in ("marsh", "park")
    assert delta.stats["unassigned_land_km2"] == 0.0


def test_land_use_check_catches_orphans(delta):
    data = json.loads(delta.model.to_json())
    if not data["open_spaces"]:
        pytest.skip("no open land in this build")
    data["open_spaces"] = []
    broken = CityModel.model_validate(data)
    spec = validate_spec(copy.deepcopy(DELTA)).filled
    checks, _ = C.run_checks(spec, broken)
    assert not next(c for c in checks if c.id == "land_use").passed


def test_bay_delta_mouth_not_at_center():
    """A delta into a bay gets a lobe, so the river ends well away from the map center."""
    data = copy.deepcopy(SMALL)
    data["size_km"] = [3.0, 3.0]
    data["water"] = {"coast": {"form": "bay", "side": "west"},
                     "rivers": [{"name": "R", "from": "east", "to": "bay", "delta_branches": 2}]}
    _, h = _hydro(data)
    main = next(b for b in h.bodies if b.name == "R")
    mouth = main.centerline.interpolate(H._coast_hit(main.centerline, h.sea))
    assert mouth.x < -500.0, mouth


# --- 5. inner waterways ------------------------------------------------------------------------

def _model_with_canals(lines):
    data = json.loads(_SMALL_MODEL[0].model.to_json())
    did = data["districts"][0]["id"]
    data["waterways"] = [
        {"id": f"t{k}", "kind": "canal", "district_id": did, "centerline": list(ln.coords),
         "polygon": G.to_model_poly(ln.buffer(7))} for k, ln in enumerate(lines)]
    data["quays"] = []
    return CityModel.model_validate(data)


_SMALL_MODEL: list = []


@pytest.fixture(scope="module", autouse=True)
def _small_model():
    if not _SMALL_MODEL:
        _SMALL_MODEL.append(_build(copy.deepcopy(SMALL)))


def test_canal_quality_shallow_crossing():
    a = LineString([(0, 0), (600, 0)])
    b = LineString([(0, -40), (600, 120)])  # crosses a at about 15 degrees
    assert any("deg" in p for p in C.canal_problems(_model_with_canals([a, b])))
    c = LineString([(300, -200), (300, 200)])  # square crossing is fine
    assert C.canal_problems(_model_with_canals([a, c])) == []


def test_canal_quality_near_duplicates():
    a = LineString([(0, 0), (600, 0)])
    b = LineString([(0, 20), (600, 20)])  # 20 m apart for 600 m
    assert any("within" in p for p in C.canal_problems(_model_with_canals([a, b])))
    far = LineString([(0, 150), (600, 150)])
    assert C.canal_problems(_model_with_canals([a, far])) == []


def test_canal_quality_branch_junction_ok():
    a = LineString([(0, 0), (600, 0)])
    br = LineString([(300, 0), (300 + 200 * math.cos(1.0), 200 * math.sin(1.0))])  # 57 deg
    assert C.canal_problems(_model_with_canals([a, br])) == []


def test_harbor_slips_are_parallel(mainland):
    basins = [w for w in mainland.model.waterways if w.kind == "basin"]
    if len(basins) < 2:
        pytest.skip("fewer than two slips")
    angs = []
    for w in basins:
        (x0, y0), (x1, y1) = w.centerline[0], w.centerline[-1]
        angs.append(math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180)
    by_district: dict[str, list[float]] = {}
    for w, a in zip(basins, angs):
        by_district.setdefault(w.district_id, []).append(a)
    for group in by_district.values():
        assert max(group) - min(group) < 30 or max(group) - min(group) > 150


# --- 6. island bearings ----------------------------------------------------------------------

def test_sea_island_keeps_its_bearing():
    data = copy.deepcopy(SMALL)
    data["size_km"] = [3.0, 3.0]
    data["water"] = {"coast": {"form": "archipelago", "side": "south", "sea_share": 0.75},
                     "rivers": [],
                     "islands": [{"name": "Big", "position": "center_offshore", "area_km2": 1.0},
                                 {"name": "West", "position": "west_offshore", "area_km2": 0.5},
                                 {"name": "SW", "position": "south_west_offshore",
                                  "area_km2": 0.2}]}
    _, h = _hydro(data)
    c = H._sea_aim(h.canvas, h.sea, "center", 0.0)
    sw = next(i for i in h.islands if i.name == "SW").polygon.centroid
    ang = math.degrees(math.atan2(sw.y - c.y, sw.x - c.x))
    assert -180 <= ang <= -90 + 10 or ang >= 170, ang  # toward the south west


def test_cli_variant_default_matches_build():
    from citygen import build, cli
    assert cli.MAX_VARIANTS == build.MAX_VARIANTS
