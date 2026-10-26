"""M7b: pinned geometry (scope 4.3): the traced Corporate Core imported as fixed, the
generator building around it; the SVG path parser; the city built around a pinned island."""

import copy
import math

import pytest
from shapely.geometry import LineString, Polygon

from citygen import geom as G
from citygen import pinned as PN
from citygen.build import build_city
from citygen.validate import validate_spec

from conftest import ROOT

SOURCE = "maps/corporate_core_v1.0.1.svg"
PINNED = {
    "name": "Pinport", "seed": 17, "size_km": [3.0, 2.6],
    "water": {"coast": {"form": "bay", "side": "south", "sea_share": 0.42}, "rivers": [],
              "islands": [{"name": "Core Island", "position": "south", "setting": "nearshore",
                           "pinned": {"source": SOURCE}}]},
    "highways": {"pattern": "spine"},
    "districts": [
        {"name": "Core", "archetype": "corporate_core",
         "placement": {"on_island": "Core Island"}, "grid_angle_deg": 45},
        {"name": "Harbor", "archetype": "midtown_mixed",
         "placement": {"coast": True, "edge": "west"}},
        {"name": "Uptown", "archetype": "residential_heights", "placement": {"edge": "north"}},
        {"name": "Old Quarter", "archetype": "old_town",
         "placement": {"coast": True, "edge": "east"}},
    ],
}


@pytest.fixture(scope="module")
def city():
    result = validate_spec(copy.deepcopy(PINNED))
    assert result.ok, [str(i) for i in result.errors]
    return build_city(result)


# --- the tracing ------------------------------------------------------------------------

def test_load_the_traced_core():
    pin = PN.load(SOURCE, ROOT)
    assert pin.land.area == pytest.approx(692502, abs=5)
    assert len(pin.land.interiors) == 7              # the water pockets
    ring = [r for r in pin.roads if r.closed]
    assert len(ring) == 1 and ring[0].road_class == "highway" and ring[0].width_m == 20.0
    assert len(pin.roads) == 10
    marks = [b for b in pin.buildings if b.kind == "landmark"]
    assert len(marks) == 1 and marks[0].id == "megatower" and marks[0].height_m == 480.0
    assert len(pin.buildings) == 57
    # traced footprints that overlap give way, so all are disjoint
    for i, a in enumerate(pin.buildings):
        for b in pin.buildings[i + 1:]:
            assert a.footprint.intersection(b.footprint).area < 0.01, (a.id, b.id)
    assert any("gives way" in w for w in pin.warnings)


def test_path_parser_arcs_and_relative_commands():
    (pts, closed), = PN.subpaths("M 0,0 A 10,10 0 1 0 20,0 A 10,10 0 1 0 0,0 Z")
    assert closed
    for x, y in pts:
        assert math.hypot(x - 10.0, y) == pytest.approx(10.0, abs=1e-9)
    (pts, closed), = PN.subpaths("m 10,10 h 5 v 5 l -5,0 z")
    assert closed and pts == [(10.0, 10.0), (15.0, 10.0), (15.0, 15.0), (10.0, 15.0)]
    (pts, _), = PN.subpaths("M 0,0 C 0,10 10,10 10,0")
    assert pts[-1] == (10.0, 0.0) and len(pts) == PN.CURVE_PIECES + 1


def test_open_three_point_footprint_is_squared():
    corners = PN.complete_rect((10.0, 0.5), (0.0, 0.0), (0.0, 6.0))
    p = Polygon(corners)
    assert p.area == pytest.approx(10.0 * 6.0, rel=0.02)
    a, b, c = corners[1], corners[0], corners[3]
    dot = (a[0] - b[0]) * (c[0] - b[0]) + (a[1] - b[1]) * (c[1] - b[1])
    assert abs(dot) < 1e-6


def test_placed_moves_and_turns_on_the_grid():
    pin = PN.load(SOURCE, ROOT)
    p = pin.placed((100.0, -50.0), 90.0)
    x0, y0, x1, y1 = pin.land.bounds
    a0, b0, a1, b1 = p.land.bounds
    assert (a1 - a0) == pytest.approx(y1 - y0, abs=0.05)
    assert (b1 - b0) == pytest.approx(x1 - x0, abs=0.05)
    for x, y in p.land.exterior.coords:
        assert G.q(x) == x and G.q(y) == y


# --- the city around it --------------------------------------------------------------

def test_city_passes_around_the_pinned_island(city):
    failed = [(c.id, c.failures[:3]) for c in city.checks if not c.passed]
    assert not failed, failed


def test_traced_buildings_as_drawn(city):
    m = city.model
    traced = [b for b in m.buildings if b.attrs.get("pinned")]
    assert len(traced) == 57
    tower = next(b for b in traced if b.attrs["pinned"]["id"] == "megatower")
    assert tower.landmark and tower.height_m == 480.0
    lots = {lt.id: lt for lt in m.lots}
    for b in traced:
        assert b.lot_id in lots and lots[b.lot_id].attrs["pinned"] == b.attrs["pinned"]["id"]
        assert b.entrances and b.entrances[0].kind == "main"
    # no generated building on the traced lots
    assert not [b for b in m.buildings if not b.attrs.get("pinned") and
                b.lot_id in lots and lots[b.lot_id].attrs.get("pinned")]


def test_traced_roads_as_drawn(city):
    m = city.model
    pin_roads = [s for s in m.road_segments if "pinned" in s.attrs]
    ids = {s.attrs["pinned"]["id"] for s in pin_roads}
    assert "path9" in ids                            # the ring
    isl = next(i for i in m.islands if i.name == "Core Island")
    land = G.from_model_poly(isl.polygon)
    on = sum(LineString(s.centerline).intersection(land).length for s in pin_roads)
    assert on > 3000.0
    # the island is joined to the mainland by traced roads that land there
    assert any(s.bridge for s in pin_roads)
    assert not any(s.attrs.get("elevated") for s in pin_roads)


def test_water_pockets_are_basins(city):
    m = city.model
    core = next(d for d in m.districts if d.name == "Core")
    pools = [w for w in m.waterways if w.district_id == core.id and w.kind == "basin"]
    assert len(pools) >= 7 and all(w.ornamental for w in pools)
