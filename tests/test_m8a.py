"""M8a robustness sweep: the defects the sweep found, each pinned to the seed that showed it,
and the sweep tool itself."""

import copy
import json
import math

import pytest
from shapely.geometry import LineString, Point

from citygen import geom as G
from citygen import hydro as H
from citygen import sweep as SW
from citygen.build import build_city
from citygen.streets import _foot_profile
from citygen.validate import validate_spec

from conftest import ROOT, MINIMAL

SAMPLES = ROOT / "docs" / "progress" / "M1a2"


def _spec(name: str, seed: int) -> dict:
    data = json.loads((SAMPLES / name / "city_spec.json").read_text(encoding="utf-8"))
    data["seed"] = seed
    return data


def _roads(data: dict):
    result = validate_spec(data)
    assert result.ok, [str(i) for i in result.errors]
    return build_city(result, local=False)


def _failures(b, ids):
    return [f for c in b.checks if c.id in ids for f in c.failures]


def test_island_squeezed_beside_a_larger_one_is_still_built():
    # seed 8128: Kettle Island (1 km2, east) did not fit beside Crown Island at its drawn
    # proportions; it is built longer instead of being dropped
    spec = validate_spec(_spec("archipelago_free_port", 8128)).filled
    h = H.build_hydro(spec, G.canvas_for(spec.size_km), H.Variant.make(spec, 0))
    assert not [n for n in h.notes if "does not fit" in n]
    built = {i.name for i in h.islands if i.polygon is not None}
    assert built >= {i.name for i in spec.water.islands}


def test_footbridge_profile_ends_on_the_ground():
    # water reaching the far end of a footbridge left its deck height at the end node
    for L, s_in, wet in ((32.13, 4.0, 28.0), (20.0, 0.0, 20.0), (40.0, 10.0, 20.0)):
        prof = _foot_profile(L, s_in, wet, 3.8)
        assert prof[0]["z"] == 0.0 and prof[-1]["z"] == 0.0
        assert prof[-1]["s"] == pytest.approx(L)
        assert max(p["z"] for p in prof) == 3.8
    # the usual case is as before: stairs on land on both sides of the water
    assert [(p["s"], p["z"]) for p in _foot_profile(40.0, 10.0, 20.0, 3.8)] == [
        (0.0, 0.0), (1.4, 0.0), (9.0, 3.8), (31.0, 3.8), (38.6, 0.0), (40.0, 0.0)]


def test_exit_enters_square_to_the_map_edge():
    # seed 5077: the exit lay on the map border, which `contains` leaves out, so the spine
    # took it for water and hooked along the edge from it
    b = _roads(_spec("delta_megacity", 5077))
    assert not _failures(b, {"curve_radius", "road_graph"})
    m = b.model
    minx, miny, maxx, maxy = m.bounds
    exits = [n for n in m.road_nodes if n.attrs.get("kind") == "exit"]
    assert exits
    for n in exits:
        x, y = n.position[0], n.position[1]
        seg = next(s for s in m.road_segments if n.id in (s.start, s.end))
        ln = LineString(seg.centerline)
        if seg.end == n.id:
            ln = LineString(list(ln.coords)[::-1])
        if ln.length < 40.0:
            continue
        q = ln.interpolate(40.0)
        inward = min([(x - minx, (1, 0)), (maxx - x, (-1, 0)), (y - miny, (0, 1)),
                      (maxy - y, (0, -1))])[1]
        d = math.hypot(q.x - x, q.y - y)
        cos = ((q.x - x) * inward[0] + (q.y - y) * inward[1]) / d
        assert cos > math.cos(math.radians(20)), (n.id, cos)


@pytest.mark.parametrize("seed", [404, 8128])
def test_named_bridge_reaches_its_island(seed):
    # Nexus City: the west exit's bridge clips Silver Island's tip; the Silver Span must
    # still land on the island and the island get its avenue
    b = _roads(_spec("nexus_city", seed))
    assert not _failures(b, {"named_bridges", "districts_served", "road_graph",
                             "bridge_clearance"})


def test_relation_repair_moves_seeds_along_the_direction():
    # MINIMAL at seed 404: every hydrology variant had Uptown east of the Core; the repair
    # now places the seeds along the asked direction
    data = copy.deepcopy(MINIMAL)
    data["seed"] = 404
    b = build_city(validate_spec(data), roads=False)
    assert not _failures(b, {"placement"})


def test_next_variants_tried_when_no_road_network_passes():
    # MINIMAL at seed 11: the first good hydrology variant had no land at an exit edge, so no
    # road network on it passed; a later variant has one
    data = copy.deepcopy(MINIMAL)
    data["seed"] = 11
    b = _roads(data)
    assert b.passed, [f for c in b.checks for f in c.failures]
    assert any("no road network passed on the first variants" in n for n in b.notes)


def test_sweep_table_and_retries():
    rows = [{"label": "a", "seed": 1, "status": "pass", "failed": [], "seconds": 1.0,
             "hydro_variant": 0, "road_variant": 0, "city_retries": 0, "retry_fails": [],
             "layout_salt": 0},
            {"label": "a", "seed": 2, "status": "fail", "seconds": 2.0,
             "failed": [{"id": "curve_radius", "count": 1, "first": "x | y"}],
             "hydro_variant": 3, "road_variant": 1, "city_retries": 2, "retry_fails": [4, 2],
             "layout_salt": 1},
            {"label": "b", "seed": 1, "status": "crash", "failed": [], "seconds": 0.5,
             "traceback": "Traceback\nKeyError: -1"}]
    md = SW.table(rows)
    assert "1 of 3 builds pass (33%)" in md
    assert "| curve_radius | 1 |" in md and "| (crash) | 1 |" in md
    assert "hv3 rv1 city x2 (4,2) salt 1" in md
    assert "crash: KeyError: -1" in md and "x / y" in md
    jobs = SW.suite_jobs("m8a", SW.EXTRA_SEEDS[:2])
    labels = {j[0] for j in jobs}
    assert {"nyxllor", "nyxllor_pinned", "test_small", "test_pinned"} <= labels
    assert ("nyxllor", 2077) in {(j[0], j[2]) for j in jobs}


def test_roads_leaving_a_node_together_become_one():
    # peninsula s11: a waterfront avenue and a connector left one node side by side for
    # 286 m (road_duplicates); the connector now branches off the avenue where they part
    b = _roads(_spec("peninsula_city", 11))
    assert not _failures(b, {"road_duplicates", "curve_radius", "segment_length"})
