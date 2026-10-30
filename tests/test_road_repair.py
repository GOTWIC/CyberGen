"""M17: road network repair (`docs/run_through_1.md`).

Covers the four new checks on a sample city and each with a failing case on a small model
(an untagged or mistagged dead end, two streets overlapping outside a junction, two bridges
at one height, a building on a road), the dead-end tags and turning bulbs of a built city,
and the junction cut-backs that keep two legs from overlapping past their junction (an acute
corner, a sharp bend between two roads).
"""

import math

from shapely.geometry import LineString

from citygen import dmath as M
from citygen import geom as G
from citygen import junctions as JN
from citygen import network_checks as NC
from citygen import streets as ST
from citygen.model import CityModel
from citygen.validate import load_spec

from conftest import ROOT, built_sample

VESPER_BAY = ROOT / "cities" / "vesper_bay" / "city_spec.json"
M17 = ("road_dead_ends", "road_overlaps", "bridge_clash", "road_building_clash")


def _seg(sid: str, a: str, b: str, pts, cls: str = "street", z: float = 0.0, **kw) -> dict:
    cs = ST.cross_section(cls, "midtown_mixed")
    L = LineString(pts).length
    return {"id": sid, "start": a, "end": b, "road_class": cls,
            "lanes": 0 if cls in ST.PEDESTRIAN else 2, "width_m": cs["total_width_m"],
            "centerline": pts, "cross_section": cs,
            "z_profile": [{"s": 0.0, "z": z}, {"s": L, "z": z}],
            "attrs": {"role": "grid_u"}, **kw}


def _model(nodes: dict, segs: list, **rows) -> CityModel:
    """Nodes {id: (x, y, attrs)} and segments on a 400 m map."""
    return CityModel.model_validate({
        "name": "t", "seed": 1, "bounds": (-200, -200, 200, 200),
        "road_nodes": [{"id": k, "position": (x, y, 0.0), "attrs": at}
                       for k, (x, y, at) in nodes.items()],
        "road_segments": segs, **rows})


def _spec():
    return load_spec(VESPER_BAY).filled


def test_m17_checks_pass_on_a_sample():
    b, _, _ = built_sample(VESPER_BAY)
    checks = {c.id: c for c in b.checks}
    for cid in M17:
        assert cid in checks, cid
        assert checks[cid].passed, (cid, checks[cid].failures[:5])


def test_every_dead_end_says_what_it_is():
    b, _, _ = built_sample(VESPER_BAY)
    m = b.model
    deg: dict = {}
    for s in m.road_segments:
        for n in (s.start, s.end):
            deg[n] = deg.get(n, 0) + 1
    ends = [n for n in m.road_nodes if deg.get(n.id) == 1]
    assert ends and all(n.attrs.get("dead_end") in ST.DEAD_END_KINDS for n in ends)
    bulbs = {j.node_id: j for j in m.junctions if j.shape == "cul_de_sac"}
    culs = [n for n in ends if n.attrs["dead_end"] == "cul_de_sac" and
            n.attrs.get("turning_head_m")]
    assert culs and all(n.id in bulbs and bulbs[n.id].corner_radius_m ==
                        n.attrs["turning_head_m"] for n in culs)


def test_check_dead_ends_fails():
    nodes = {"a": (-100.0, 0.0, {"dead_end": "map_edge"}), "b": (0.0, 0.0, {}),
             "c": (100.0, 0.0, {}), "d": (0.0, 100.0, {"dead_end": "path_end"})}
    segs = [_seg("s1", "a", "b", [(-100.0, 0.0), (0.0, 0.0)]),
            _seg("s2", "b", "c", [(0.0, 0.0), (100.0, 0.0)]),
            _seg("s3", "b", "d", [(0.0, 0.0), (0.0, 100.0)])]
    c = NC.check_dead_ends(_spec(), _model(nodes, segs))
    text = " ".join(c.failures)
    assert len(c.failures) == 3, c.failures
    assert "says nothing" in text                   # c: no tag
    assert "a map edge 100 m from it" in text       # a: not at the edge
    assert "a path end on a street" in text         # d: a street
    nodes["a"] = (-200.0, 0.0, {"dead_end": "map_edge"})
    nodes["c"] = (100.0, 0.0, {"dead_end": "cul_de_sac", "turning_head_m": 12.0})
    nodes["d"] = (0.0, 100.0, {"dead_end": "cul_de_sac"})
    segs[0] = _seg("s1", "a", "b", [(-200.0, 0.0), (0.0, 0.0)])
    c = NC.check_dead_ends(_spec(), _model(nodes, segs, junctions=[
        {"id": "j1", "node_id": "c", "shape": "cul_de_sac", "legs": 1, "corner_radius_m": 12.0,
         "polygon": G.to_model_poly(G.qpoly(LineString([(100, 0), (100, 0.1)]).buffer(12)))}]))
    assert c.failures == ["node d (street s3) at (0, 100): a cul-de-sac without its turning "
                          "bulb"]


def test_check_overlaps_fails():
    def two(dy: float, z: float = 0.0):
        nodes = {"a": (-100.0, 0.0, {}), "b": (100.0, 0.0, {}),
                 "c": (-100.0, dy, {}), "d": (100.0, dy, {})}
        segs = [_seg("s1", "a", "b", [(-100.0, 0.0), (100.0, 0.0)]),
                _seg("s2", "c", "d", [(-100.0, dy), (100.0, dy)], z=z)]
        return _model(nodes, segs)

    w = ST.cross_section("street", "midtown_mixed")["total_width_m"]
    bad = NC.check_overlaps(_spec(), two(w - 4.0))
    assert len(bad.failures) == 1 and "overlap by 800 m2" in bad.failures[0]
    assert NC.check_overlaps(_spec(), two(w + 1.0)).passed       # apart
    assert NC.check_overlaps(_spec(), two(w - 4.0, 9.0)).passed  # one over the other


def test_check_bridge_clash_fails():
    def crossing(z2: float):
        nodes = {"a": (-100.0, 0.0, {}), "b": (100.0, 0.0, {}),
                 "c": (0.0, -100.0, {}), "d": (0.0, 100.0, {})}
        segs = [_seg("s1", "a", "b", [(-100.0, 0.0), (100.0, 0.0)], z=10.0, bridge=True,
                     bridge_ids=["b1"]),
                _seg("s2", "c", "d", [(0.0, -100.0), (0.0, 100.0)], z=z2, bridge=True,
                     bridge_ids=["b2"])]
        br = [{"id": k, "bridge_class": "road", "crosses": "w1", "clearance_m": 10.0,
               "line": [(*p, 10.0) for p in pts], "segment_ids": [sid]}
              for k, sid, pts in (("b1", "s1", [(-100, 0), (100, 0)]),
                                  ("b2", "s2", [(0, -100), (0, 100)]))]
        return _model(nodes, segs, bridges=br)

    bad = NC.check_bridge_clash(_spec(), crossing(10.0))
    assert len(bad.failures) == 1 and "0.0 m apart in height (needs 7 m)" in \
        bad.failures[0]
    assert NC.check_bridge_clash(_spec(), crossing(20.0)).passed


def test_check_building_clash_fails():
    def on_road(z0: float):
        nodes = {"a": (-100.0, 0.0, {}), "b": (100.0, 0.0, {})}
        segs = [_seg("s1", "a", "b", [(-100.0, 0.0), (100.0, 0.0)])]
        fp = G.to_model_poly(G.qpoly(LineString([(-10, 0), (10, 0)]).buffer(15, cap_style=3)))
        bld = {"id": "b1", "lot_id": "l1", "district_id": "d1",
               "use": "office", "height_m": 40.0, "footprint": fp,
               "masses": [{"footprint": fp, "z0_m": z0, "z1_m": 40.0}]}
        return _model(nodes, segs, buildings=[bld])

    bad = NC.check_building_clash(_spec(), on_road(0.0))
    assert len(bad.failures) == 1 and "runs through building b1" in bad.failures[0]
    assert NC.check_building_clash(_spec(), on_road(8.0)).passed   # a span over the road


def _legs(dirs: list, L: float = 120.0) -> list:
    """Streets leaving a node at the origin in these directions (degrees)."""
    out = []
    for k, a in enumerate(dirs):
        e = (G.q(L * M.cos(M.radians(a))), G.q(L * M.sin(M.radians(a))))
        out.append(JN.Leg(_seg(f"s{k}", "n", f"e{k}", [(0.0, 0.0), e]), True,
                          "midtown_mixed"))
    out.sort(key=lambda lg: lg.ang)
    return out


def _past_cut_overlap(legs: list) -> float:
    """Area where two legs' rights of way overlap past their cuts."""
    worst = 0.0
    for i, a in enumerate(legs):
        for b in legs[i + 1:]:
            ra = LineString(ST._substring(a.pts, a.cut, a.L)).buffer(a.row, cap_style=2)
            rb = LineString(ST._substring(b.pts, b.cut, b.L)).buffer(b.row, cap_style=2)
            worst = max(worst, ra.intersection(rb).area)
    return worst


def test_cuts_reach_past_the_overlap():
    for dirs in ([0.0, 35.0, 180.0], [0.0, 90.0, 180.0, 270.0], [0.0, 25.0, 200.0]):
        legs = _legs(dirs)
        JN.cutbacks(legs)
        assert _past_cut_overlap(legs) < 0.5, dirs
        poly = JN.junction_polygon(legs)
        assert poly.is_valid and poly.contains(G.qpoly(LineString(
            [(0, 0), (1, 0)]).buffer(0.5)))
    # an acute corner: the cut is past where the two rights of way part
    legs = _legs([0.0, 35.0, 180.0])
    JN.cutbacks(legs)
    row = legs[0].row
    assert legs[0].cut >= row / math.tan(math.radians(35.0)) + row / math.sin(
        math.radians(35.0)) - 1.0


def test_bend_between_two_roads():
    straight = _legs([0.0, 180.0])
    JN.cutbacks(straight)
    assert all(lg.cut == 0.0 for lg in straight)        # no junction where a road runs on
    bend = _legs([0.0, 90.0])
    JN.cutbacks(bend)
    assert all(lg.cut > 0.0 for lg in bend) and _past_cut_overlap(bend) < 0.5
    assert JN.classify(bend, "midtown_mixed")[1] == "bend"
