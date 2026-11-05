"""Park paths fix (between milestones; `docs/run_through_1.md`, PR #67's open items).

Covers the park paths of a built sample (on open land, every open space reached or saying
why, no entrance link through a building, both new checks passing), each new check with a
failing case on a small model, the park path router (straight, bent round a lot, never
between two lots), a passage carved to an enclosed park, every ground walkway led off the
lots, and the sidewalk corner of a junction on the right of way when the cuts are long.
"""

from shapely.geometry import LineString, Point, Polygon, box

from citygen import geom as G
from citygen import junctions as JN
from citygen import network_checks as NC
from citygen import parkpaths as PP
from citygen import streets as ST
from citygen.model import CityModel

from conftest import ROOT, built_sample
from test_road_repair import _legs, _seg, _spec

VESPER_BAY = ROOT / "cities" / "vesper_bay" / "city_spec.json"
NEW = ("walkway_building_clash", "park_access")


def test_checks_pass_on_a_sample():
    b, _, _ = built_sample(VESPER_BAY)
    checks = {c.id: c for c in b.checks}
    for cid in NEW:
        assert cid in checks, cid
        assert checks[cid].passed, (cid, checks[cid].failures[:5])


def test_park_paths_on_open_land():
    b, _, _ = built_sample(VESPER_BAY)
    m = b.model
    lots = [G.qpoly(G.from_model_poly(lt.polygon).buffer(-0.1, join_style="mitre"))
            for lt in m.lots if not lt.level]
    paths = [w for w in m.walkways if (w.attrs or {}).get("open_space")]
    assert paths
    for w in paths:
        line = LineString([p[:2] for p in w.line])
        assert not any(lt.intersects(line) for lt in lots if not G.apart(lt, line)), w.id
    reached = {(w.attrs or {}).get("open_space") for w in paths}
    walks = [LineString([p[:2] for p in w.line]) for w in m.walkways
             if not w.level and len(w.line) >= 2 and not (w.attrs or {}).get("open_space")]
    for o in m.open_spaces:
        # (access fix, #86: every open space has a way in, a path or a walkway beside it)
        if o.kind in PP.PATH_KINDS and not o.level and o.id not in reached:
            assert o.attrs.get("access") != "none", o.id
            poly = G.from_model_poly(o.polygon)
            assert o.district_id is None or any(
                G.dist(poly, w) <= NC.BESIDE_M for w in walks if not G.apart(poly, w, 4.0)), \
                o.id


def test_no_entrance_links_through_a_building():
    b, _, _ = built_sample(VESPER_BAY)
    m = b.model
    walks = {w.id: w for w in m.walkways}
    feet = []
    for bl in m.buildings:
        for e in bl.entrances:
            w = walks.get(e.walkway_id)
            if w is not None and len(w.line) >= 2:
                feet.append(NC.entrance_foot(LineString([p[:2] for p in w.line]), e.position))
    assert feet
    assert NC.check_walkway_clash(_spec(), m).passed


# ---------------------------------------------------------------------------
# The checks fail where they should
# ---------------------------------------------------------------------------

def _bld(bid: str, poly, z0: float = 0.0, entrances=()) -> dict:
    fp = G.to_model_poly(G.qpoly(poly))
    return {"id": bid, "lot_id": f"{bid}.lot", "district_id": "d1", "use": "office",
            "height_m": 20.0, "footprint": fp,
            "masses": [{"footprint": fp, "z0_m": z0, "z1_m": 20.0}],
            "entrances": list(entrances)}


def _walk(wid: str, pts, kind: str = "sidewalk", z: float = 0.0, **attrs) -> dict:
    return {"id": wid, "kind": kind, "line": [(x, y, z) for x, y in pts], "width_m": 2.0,
            "attrs": attrs}


def _model(**rows) -> CityModel:
    return CityModel.model_validate({"name": "t", "seed": 1, "bounds": (-200, -200, 200, 200),
                                     **rows})


def test_check_walkway_clash_fails():
    house = box(0, 0, 20, 20)

    def city(walk, z0=0.0, entrances=()):
        return _model(buildings=[_bld("b1", house, z0, entrances)], walkways=[walk])

    through = _walk("w1", [(-10, 10), (30, 10)])
    bad = NC.check_walkway_clash(_spec(), city(through))
    assert len(bad.failures) == 1 and "runs through building b1" in bad.failures[0]
    # a mass high over the walkway leaves room under it; a walkway along the wall is clear
    assert NC.check_walkway_clash(_spec(), city(through, z0=6.0)).passed
    assert NC.check_walkway_clash(_spec(), city(_walk("w1", [(-10, 0), (30, 0)]))).passed
    # a door path into its own building is fine, into another one is not
    door = _walk("w1", [(10, 10), (10, -5)], kind="path", building="b1", door=True)
    assert NC.check_walkway_clash(_spec(), city(door)).passed
    door["attrs"]["building"] = "b2"
    assert not NC.check_walkway_clash(_spec(), city(door)).passed
    # an entrance whose link to its walkway runs through another building
    side = _walk("w1", [(-10, -10), (-10, 30)])
    ent = {"position": (25.0, 10.0), "kind": "main", "walkway_id": "w1", "link_m": 35.0}
    m = _model(buildings=[_bld("b1", house), _bld("b2", box(25, 0, 40, 20), entrances=[ent])],
               walkways=[side])
    bad = NC.check_walkway_clash(_spec(), m)
    assert len(bad.failures) == 1 and "links to w1 through building b1" in bad.failures[0]


def test_check_walkway_clash_fails_a_walled_in_entrance():
    # (access fix, #87: no longer a note)
    ent = {"position": (20.0, 10.0), "kind": "main", "walkway_id": "w1", "link_m": 30.0}
    b = _bld("b1", box(0, 0, 20, 20), entrances=[ent])
    b["attrs"] = {"walled_in": [0]}
    m = _model(buildings=[b], walkways=[_walk("w1", [(50, -10), (50, 30)])])
    bad = NC.check_walkway_clash(_spec(), m)
    assert len(bad.failures) == 1 and "walled in" in bad.failures[0]


def _link(buildings: list, walks: list):
    from citygen import buildout as BO
    from citygen.model import COLLECTIONS

    with G.canonical():
        out = BO.Out(buildings=[COLLECTIONS["buildings"].model_validate(b) for b in buildings])
        rows = BO.link_entrances(out, [{**w, "neighbors": []} for w in walks])
    return out, rows


def test_gateway_through_a_low_building_that_walls_an_entrance_in():
    # an office behind a long shed (11 m) along the street: no way round within reach, so a
    # gateway is cut through the shed, its roof running on over the gateway
    ent = {"position": (10.0, 5.0), "kind": "main"}
    office = {**_bld("b1", box(0, 0, 10, 10), entrances=[ent]), "property_id": "p1"}
    shed = _bld("b2", box(12, -100, 16, 100))
    shed.update(property_id="p2", height_m=11.0, type="building.shed", use="industrial",
                entrances=[{"position": (16.0, 60.0), "kind": "main"}])
    shed["masses"][0]["z1_m"] = 11.0
    out, _ = _link([office, shed], [_walk("w1", [(20, -120), (20, 120)])])
    o, s = out.buildings
    assert not o.attrs.get("walled_in") and out.info["entrances_gateways"] == 1
    assert s.attrs.get("passage_cut") and len(s.masses) == 3
    low = [ms for ms in s.masses if ms.z0_m == 0.0]
    over = [ms for ms in s.masses if ms.z0_m > 0.0]
    assert len(low) == 2 and len(over) == 1 and over[0].z0_m == 4.5 and over[0].z1_m == 11.0
    gap = G.from_model_poly(over[0].footprint)
    assert abs(G.area1(gap) - 4.0 * 3.0) < 0.05 and gap.contains(Point(14.0, 5.0))
    # the check sees no walkway through it, and the entrance's link is clear
    m = _model(buildings=[b.model_dump(mode="python") for b in out.buildings],
               walkways=[_walk("w1", [(20, -120), (20, 120)])])
    assert NC.check_walkway_clash(_spec(), m).passed


def test_entrance_its_complex_walls_in_leaves_through_its_lobby():
    # twin towers on one podium, the east one's entrance on a face its sibling and a
    # neighbor close: its door path runs through the complex (property p1)
    ent = {"position": (30.0, 30.0), "kind": "main"}
    a = {**_bld("b1", box(20, 0, 40, 30), entrances=[ent]), "property_id": "p1"}
    sib = {**_bld("b2", box(10, 30, 50, 50)), "property_id": "p1",
           "entrances": [{"position": (30.0, 50.0), "kind": "main"}]}
    others = [{**_bld(f"b{k}", g), "property_id": f"p{k}", "entrances": [
        {"position": e, "kind": "main"}]} for k, g, e in (
        (3, box(0, -10, 20, 50), (0.0, 20.0)), (4, box(40, -10, 60, 50), (60.0, 20.0)),
        (5, box(20, -10, 40, 0), (30.0, -10.0)))]
    walks = [_walk("w1", [(-40, 55), (100, 55)])]
    out, rows = _link([a, sib] + others, walks)
    b1 = out.buildings[0]
    assert not b1.attrs.get("walled_in") and out.info["entrances_through_complex"] == 1
    door = [w for w in rows if (w.get("attrs") or {}).get("building") == "b1" and
            w["attrs"].get("door")]
    assert door and door[0]["attrs"].get("through") == "p1"
    m = _model(buildings=[b.model_dump(mode="python") for b in out.buildings],
               walkways=[_walk(w["id"], [p[:2] for p in w["line"]], w["kind"], **w["attrs"])
                         for w in rows])
    assert NC.check_walkway_clash(_spec(), m).passed


def test_check_park_access_fails():
    park = G.to_model_poly(box(0, 0, 30, 30))
    lot = {"id": "l1", "block_id": "k1", "district_id": "d1", "archetype": "midtown_mixed",
           "polygon": G.to_model_poly(box(30, 0, 60, 30)), "area_m2": 900.0}

    def city(walks, attrs=None):
        os_ = {"id": "o1", "kind": "park", "polygon": park, "attrs": attrs or {}}
        return _model(open_spaces=[os_], lots=[lot], walkways=walks)

    far = _walk("w9", [(-100, -100), (-100, 100)])
    bad = NC.check_park_access(_spec(), city([far]))
    assert len(bad.failures) == 1 and "no way in" in bad.failures[0]
    # (access fix, #86: saying why is no longer enough)
    said = city([far], {"access": "none", "no_access": "no walkway within 30 m"})
    bad = NC.check_park_access(_spec(), said)
    assert len(bad.failures) == 1 and "no walkway within 30 m" in bad.failures[0]
    across = _walk("w1", [(15, 15), (70, 15)], kind="path", open_space="o1")
    bad = NC.check_park_access(_spec(), city([far, across]))
    assert any("crosses a lot" in f for f in bad.failures)
    good = _walk("w1", [(15, 15), (15, -5)], kind="path", open_space="o1")
    assert NC.check_park_access(_spec(), city([far, good])).passed


# ---------------------------------------------------------------------------
# The router, the passages, the walkways off the lots
# ---------------------------------------------------------------------------

def _graph(lines: list) -> JN.WalkGraph:
    W = JN.WalkGraph()
    for pts in lines:
        W.add("sidewalk", pts, 2.0, sidewalk="sw")
    return W


def _lot(poly, **kw) -> dict:
    return {"id": kw.pop("id", "l"), "polygon": G.qpoly(poly), "area_m2": poly.area,
            "frontage": [], "frontage_ids": [], "attrs": {}, **kw}


def test_route_keeps_off_a_lot():
    with G.canonical():
        # an L-shaped park, a lot in its crook, the walkway past the lot
        park = G.union([box(0, 0, 40, 20), box(0, 20, 15, 45)])
        lot = box(15, 20, 40, 45)
        bl = PP.Blocked([lot], [], -PP.LOT_PAD_M)
        assert not bl.clear((30.0, 10.0), (30.0, 50.0))
        r = PP.route((30.0, 10.0), (30.0, 50.0), park, bl)
        assert r is not None and len(r) > 2 and (15.0, 20.0) in r
        assert all(bl.clear(a, b) for a, b in zip(r, r[1:]))
        # no way past the lot from a park without that arm: none
        assert PP.route((30.0, 10.0), (30.0, 50.0), box(0, 0, 40, 20), bl) is None


def test_route_never_runs_between_two_lots():
    with G.canonical():
        park = box(0, 0, 40, 20)
        lots = [box(0, 20, 20, 40), box(20, 20, 40, 40)]
        bl = PP.Blocked(lots, [], -PP.LOT_PAD_M)
        assert not bl.clear((20.0, 20.0), (20.0, 40.0))       # the line between them
        assert bl.clear((0.0, 20.0), (40.0, 20.0))            # along the park's edge


def test_passage_to_an_enclosed_park():
    with G.canonical():
        # a 3 x 2 block of lots, the middle back lot made a park, a street along the south
        street = [(-10.0, -6.0), (130.0, -6.0)]
        W = _graph([street])
        lots = [_lot(box(0, 0, 40, 30), id="a"), _lot(box(40, 0, 80, 30), id="b"),
                _lot(box(80, 0, 120, 30), id="c"), _lot(box(0, 30, 40, 60), id="d"),
                _lot(box(80, 30, 120, 60), id="f")]
        park = {"id": "o1", "kind": "park", "polygon": G.qpoly(box(40, 30, 80, 60))}
        seg = {"id": "s1", "road_class": "street", "width_m": 10.0,
               "centerline": [(-10.0, -5.0), (130.0, -5.0)]}
        info = PP.open_paths(W, [park], lots, [], [seg])
        assert info["passages"] == 1 and info["paths"] >= 1 and not info["no_access"]
        poly = park["polygon"]
        assert poly.geom_type == "Polygon" and poly.area > 1200.0
        assert poly.bounds[1] <= 0.01                 # it reaches the street now
        cut = [lt for lt in lots if lt["attrs"].get("passage")]
        assert len(cut) == 2 and all(lt["area_m2"] < 1200.0 for lt in cut)
        assert all(not poly.overlaps(lt["polygon"]) or
                   G.area1(G.inter(poly, lt["polygon"])) < 0.01 for lt in lots)


def _highway(z: float, sid: str = "h1", y: float = 45.0) -> dict:
    return {"id": sid, "road_class": "highway", "width_m": 30.0,
            "centerline": [(-60.0, y), (120.0, y)],
            "z_profile": [{"s": 0.0, "z": z}, {"s": 180.0, "z": z}],
            "cross_section": {"sidewalk_m": [0.0, 0.0]}}


def _cut_off(z: float, segs=None):
    """A park only a highway (deck at z) borders, a sidewalk 45 m off past the highway."""
    W = _graph([[(-60.0, 75.0), (120.0, 75.0)]])
    park = {"id": "o1", "kind": "park", "polygon": G.qpoly(box(0, 0, 40, 30))}
    info = PP.open_paths(W, [park], [], [], segs if segs is not None else [_highway(z)])
    return W, park, info


def test_path_under_a_viaduct_to_a_park_only_roads_border():
    with G.canonical():
        W, park, info = _cut_off(9.0)
        assert info["under_roads"] == 1 and not info["no_access"] and not info["verges"]
        assert park.get("far_path") == "under_road" and park["kind"] == "park"
        paths = [e for e in W.edges if e["attrs"].get("open_space") == "o1"]
        assert paths and all(e["attrs"].get("under_road") for e in paths)
        assert park["polygon"].covers(Point(paths[0]["pts"][0]))
        assert abs(paths[0]["pts"][-1][1] - 75.0) < 0.01


def test_park_behind_an_at_grade_highway_is_a_verge():
    with G.canonical():
        # (an at-grade or low deck: no path crosses its carriageway; a park with no street
        # that no walkway reaches is a green verge, as M2 makes the small roadless pieces)
        for z in (0.0, 4.0):
            W, park, info = _cut_off(z)
            assert info["verges"] == 1 and info["under_roads"] == 0, z
            assert park["kind"] == "green" and park.get("verge"), z
            assert not [e for e in W.edges if e["attrs"].get("open_space")], z
        # one with a street frontage (no walkway on it here) stays a park and says why
        street = {"id": "s1", "road_class": "street", "width_m": 10.0,
                  "centerline": [(-60.0, -5.0), (120.0, -5.0)]}
        W, park, info = _cut_off(0.0, [_highway(0.0), street])
        assert park["kind"] == "park" and info["no_access"] and not info["verges"]


def test_strip_park_joins_its_neighbors_path():
    with G.canonical():
        # a park beside the street and a strip park behind it, no walkway within 30 m of the
        # strip: its path joins the first park's
        W = _graph([[(-20.0, -5.0), (60.0, -5.0)]])
        front = {"id": "o1", "kind": "park", "polygon": G.qpoly(box(0, 0, 40, 40))}
        strip = {"id": "o2", "kind": "park", "polygon": G.qpoly(box(0, 40, 40, 50))}
        info = PP.open_paths(W, [strip, front], [], [], [])
        assert info["via_open_space"] == 1 and not info["no_access"] and not info["verges"]
        assert strip.get("far_path") == "via_open_space"
        mine = [e for e in W.edges if e["attrs"].get("open_space") == "o2"]
        assert mine and strip["polygon"].covers(Point(mine[0]["pts"][0]))
        assert front["polygon"].covers(Point(mine[0]["pts"][-1]))
        # (it joins the neighbor's path at an end, its middle: no park path is split, so
        # each still starts inside its own open space)
        theirs = [e for e in W.edges if e["attrs"].get("open_space") == "o1"]
        assert len(theirs) == 1 and mine[0]["pts"][-1] == theirs[0]["pts"][0]


def test_far_path_joins_no_raised_sidewalk():
    with G.canonical():
        # (the sidewalks of a raised road are at z 0 in the walk graph: a path that passes
        # under a viaduct never joins one where its road is up)
        W = JN.WalkGraph()
        W.add("sidewalk", [(-60.0, 75.0), (120.0, 75.0)], 2.0, segment="s2")
        up = {"id": "s2", "road_class": "avenue", "width_m": 10.0,
              "centerline": [(-60.0, 78.0), (120.0, 78.0)],
              "z_profile": [{"s": 0.0, "z": 9.0}, {"s": 180.0, "z": 9.0}],
              "cross_section": {"sidewalk_m": [3.0, 3.0]}}
        park = {"id": "o1", "kind": "park", "polygon": G.qpoly(box(0, 0, 40, 30))}
        info = PP.open_paths(W, [park], [], [], [_highway(9.0), up])
        assert info["under_roads"] == 0 and info["verges"] == 1 and park["kind"] == "green"
        # a path with no road between, to a walkway past 30 m: a plain path
        W = _graph([[(-60.0, 75.0), (120.0, 75.0)]])
        park = {"id": "o1", "kind": "park", "polygon": G.qpoly(box(0, 0, 40, 30))}
        info = PP.open_paths(W, [park], [], [], [_highway(9.0, y=-60.0)])
        assert info["far_paths"] == 1 and park.get("far_path") == "path"
        assert not any(e["attrs"].get("under_road") for e in W.edges)


def test_keep_off_leads_a_walkway_round_a_lot():
    with G.canonical():
        W = _graph([[(0.0, 0.0), (30.0, 30.0)]])
        lot = _lot(box(10, 0, 30, 20))
        info = PP.keep_off(W, [lot])
        assert info == {"rerouted": 1, "left": 0}
        pts = W.edges[0]["pts"]
        assert pts[0] == (0.0, 0.0) and pts[-1] == (30.0, 30.0) and len(pts) > 2
        inner = G.qpoly(lot["polygon"].buffer(-0.1, join_style="mitre"))
        assert not inner.intersects(LineString(pts))


def test_corner_on_the_right_of_way():
    # two streets at a right angle with cuts far longer than the road is wide: the old
    # corner (the middle of the two sidewalk points at the cuts) lay in the block
    legs = _legs([0.0, 90.0])
    for lg in legs:
        lg.cut = 20.0
    a, b = legs
    c, pa, pb = JN._corner_point((0.0, 0.0), a, b)
    block = Polygon([(a.row, a.row), (200, a.row), (200, 200), (a.row, 200)])
    assert not block.contains(Point(c))
    old = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
    assert block.contains(Point(old))
    assert abs(c[0] - JN._walk_offset(a)) < 0.05 and abs(c[1] - JN._walk_offset(b)) < 0.05
    assert ST._dist(c, (0.0, 0.0)) < a.row * 2
