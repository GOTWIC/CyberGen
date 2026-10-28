"""AG1's generators on small made-up briefs: the genome (draws, families, overrides), ring
strips, triangulation that keeps straight vertices, closed shells with courts, reveals and
strips, the mesh and envelope checks, proxies within budget, collision boxes, uniqueness."""

import copy

from assetgen import asset_checks as AC
from assetgen import build as BD
from assetgen.buildings import collision as CO
from assetgen.buildings import envelope as EN
from assetgen.buildings import genome as GN
from assetgen.buildings import meshbuf as MB
from assetgen.buildings import proxy as PX
from assetgen.buildings import rings as RG
from assetgen.buildings import shell as SH
from assetgen.buildings import systems as SY
from assetgen.triangulate import area2, triangulate

ERA = {"systems": {"punched_brick": 0.5, "stucco_shutters": 0.5}, "palette":
       ["#7a4a35", "#b9a58c", "#3d3a36"], "crowns": ["parapet"], "window_to_wall": [0.2, 0.35],
       "bay_m": [2.4, 3.6], "wear": 0.8, "signage_scripts": {"latin": 1.0}}


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def region(L, z1, cls="street"):
    return [{"class": cls, "s": [0.0, L], "z": [0.0, z1], "ref": None}]


def edges_for(masses, classes=None):
    out = []
    for k, m in enumerate(masses):
        rings = [m["footprint"]["exterior"]] + m["footprint"]["holes"]
        for r, ring in enumerate(rings):
            n = len(ring)
            for i in range(n):
                a, b = ring[i], ring[(i + 1) % n]
                L = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
                cls = (classes or {}).get((k, r, i), "street" if r == 0 else "courtyard")
                out.append({"mass": k, "ring": r, "i": i, "a": a, "b": b, "length_m": L,
                            "class": cls, "regions": region(L, m["z"][1], cls),
                            "normal_deg": 0.0})
    return out


def brief_of(masses, btype="building.courtyard_block", bid="d01.lot.e0n0.bld",
             classes=None, era=ERA, prop=None):
    return {
        "id": bid, "origin": [0.0, 0.0],
        "building": {"type": btype, "use": "residential", "name": None, "landmark": False,
                     "attrs": {}, "floors": max(m["floors"]["count"] for m in masses),
                     "height_m": max(m["z"][1] for m in masses),
                     "style": {"era": "heritage", "grime": 0.4, "neon": 0.3},
                     "floor_grid": {"floor_height_m": 3.0, "base_m": None, "plinth_m": None}},
        "masses": masses, "edges": edges_for(masses, classes), "neighbors": [],
        "units": [], "entrances": [], "roof_items": [], "portals": [], "skybridges": [],
        "sign_slots": [], "props": [], "plants": [], "green_roofs": [], "pois": [],
        "lot": None, "property": prop, "district": {"id": "d01", "name": "Test"},
        "spec": {"era": "heritage", "era_style": era, "district": None, "owner": None,
                 "landmark": None, "min_gene_distance": 4},
        "override": None}


def mass(ext, z0, z1, floors, holes=(), role="body"):
    return {"role": role, "shape": "prism", "z": [z0, z1],
            "footprint": {"exterior": ext, "holes": [list(h) for h in holes]},
            "floors": {"first": 0, "count": floors, "height_m": (z1 - z0) / max(floors, 1)}}


def court_block():
    # an L with a court, on a 45 degree corner, and a tower on it
    ext = [[-20.0, -15.0], [20.0, -15.0], [20.0, 5.0], [5.0, 20.0], [-20.0, 20.0]]
    hole = [[-8.0, 8.0], [2.0, 8.0], [2.0, -4.0], [-8.0, -4.0]]      # clockwise
    tower = [[-18.0, -13.0], [-10.0, -13.0], [-10.0, 0.0], [-18.0, 0.0]]
    return brief_of([mass(ext, 0.0, 15.0, 5, [hole]), mass(tower, 15.0, 39.0, 8,
                                                          role="tower")])


def test_genome_is_a_function_of_the_brief():
    br = court_block()
    a, b = GN.make(br), GN.make(copy.deepcopy(br))
    assert a == b
    assert set(SY.AG1_SYSTEMS) >= {a["genes"][f"{g}.system"] for g in GN.GROUPS}
    other = copy.deepcopy(br)
    other["id"] = "d01.lot.e9n9.bld"
    assert GN.make(other) != a


def test_every_era_maps_onto_ag1_systems():
    from assetgen.presets import ERA_PRESETS
    for era, style in ERA_PRESETS.items():
        w = GN.system_weights({"era_style": style}, "building.tower", 30)
        assert w and set(w) <= set(SY.AG1_SYSTEMS), era


def test_family_shares_discrete_genes_and_overrides_apply():
    prop = {"id": "d01.p1", "owner": "x", "complex": "twin_towers", "name": None,
            "building_ids": ["d01.lot.e0n0.bld", "d01.lot.e9n9.bld"]}
    a = court_block()
    a["property"] = prop
    b = copy.deepcopy(a)
    b["id"] = "d01.lot.e9n9.bld"
    ga, gb = GN.make(a), GN.make(b)
    assert ga["genes"] == gb["genes"] and ga["family"] == gb["family"] == "d01.p1"
    c = copy.deepcopy(a)
    c["override"] = {"style": {"body.window": "paired"}}
    assert GN.make(c)["genes"]["body.window"] == "paired"


def test_triangulate_keeps_straight_vertices():
    ring = [(0, 0), (500, 0), (1000, 0), (1000, 1000), (0, 1000)]
    used = {i for t in triangulate(ring, keep_straight=True) for i in t}
    assert used == set(range(5))


def test_strips_and_offsets():
    ring = [(0, 0), (10000, 0), (10000, 6000), (0, 6000)]
    o, h = RG.strip(ring, 0, 4, 400, 0, 0)
    assert area2(o) > 0 > area2(h) and RG.is_simple(o)
    poly, hole = RG.strip(ring, 0, 2, 0, -250, 250)
    assert hole is None and RG.is_simple(poly) and area2(poly) > 0
    # an acute corner is beveled, not mitered past 1.5 offsets
    tri = [(0, 0), (20000, 0), (0, 4000)]
    out = RG.offset_ring(tri, [300, 300, 300])
    assert out is not None and len(out) > 3


def test_convex_pieces_cover_the_polygon():
    L = [(0, 0), (6000, 0), (6000, 2000), (2000, 2000), (2000, 6000), (0, 6000)]
    pieces = RG.convex_pieces(L)
    assert all(RG.convex(p) for p in pieces)
    assert sum(area2(p) for p in pieces) == area2(L)


def test_shell_is_closed_with_courts_reveals_and_strips():
    br = court_block()
    gm = GN.make(br)
    res = SH.build(br, gm)
    ck = MB.check(res["arrays"])
    assert ck["triangles"] > 0
    assert ck["degenerate"] == ck["duplicate"] == ck["open_edges"] == ck["bad_edges"] == 0
    assert res["stats"]["openings"] > 0
    env = EN.check(br, res["arrays"])
    assert env["ok"], env
    for slot in SY.GLASS_SLOTS:
        a = res["arrays"].get(slot)
        if a is not None:
            assert a["uv1"] is not None and a["win"] is not None


def test_party_walls_get_no_openings():
    ext = rect(0.0, 0.0, 12.0, 10.0)
    br = brief_of([mass(ext, 0.0, 9.0, 3)], classes={(0, 0, i): "party" for i in range(4)})
    res = SH.build(br, GN.make(br))
    assert res["stats"]["openings"] == 0
    assert MB.check(res["arrays"])["open_edges"] == 0


def test_mesh_check_finds_a_hole():
    br = court_block()
    res = SH.build(br, GN.make(br))
    arrs = res["arrays"]
    name = sorted(arrs)[0]
    arrs[name]["tri"] = arrs[name]["tri"][1:]
    arrs[name]["part"] = arrs[name]["part"][1:]
    assert MB.check(arrs)["open_edges"] > 0


def test_envelope_check_finds_a_vertex_outside():
    br = court_block()
    res = SH.build(br, GN.make(br))
    arrs = res["arrays"]
    name = sorted(arrs)[0]
    arrs[name]["pos"][0] = [99000, 0, 1000]
    assert not EN.check(br, arrs)["ok"]


def test_proxy_budget_and_collision():
    br = court_block()
    px = PX.build(br)
    assert 0 < px["triangles"] <= PX.MAX_TRIS
    assert MB.check(px["arrays"])["degenerate"] == 0
    col = CO.build(br)
    assert col["boxes"] and all(b["extent"][2] > 0 for b in col["boxes"])
    many = brief_of([mass([[30.0 * __import__("math").cos(k / 40.0 * 6.2831853),
                            30.0 * __import__("math").sin(k / 40.0 * 6.2831853)]
                           for k in range(40)], 0.0, 30.0 + j, 10) for j in range(12)])
    assert PX.build(many)["triangles"] <= PX.MAX_TRIS


def test_uniqueness_flags_twins_outside_a_family():
    br = court_block()
    _, _, rec = BD.building_asset(br, GN.make(br))
    recs = {"a": copy.deepcopy(rec), "b": copy.deepcopy(rec)}
    assert not AC.unique(recs, 4)["ok"]
    recs["a"]["family"] = recs["b"]["family"] = "p1"
    assert AC.unique(recs, 4)["ok"]


def test_tidy_removes_spikes_and_crossings_and_keeps_edge_indices():
    # a spike of no width (out to x=20000 and back 10 mm apart) on a 10 m square
    ring = [(0, 0), (10000, 0), (10000, 5000), (20000, 5000), (10000, 5010),
            (10000, 10000), (0, 10000)]
    pts, idx = RG.tidy(ring)
    assert RG.is_simple(pts) and (20000, 5000) not in pts
    assert idx[0] == 0 and idx[-1] == 6
    # a long thin triangle is not a spike
    thin = [(-88960, -3870), (88960, -3870), (88430, 3870)]
    assert RG.tidy(thin)[0] == thin
    # a ring that crosses itself is cut at the crossing
    bow = [(0, 0), (10000, 0), (10000, 10000), (5000, 10000), (5200, 11000),
           (4800, 11000), (5000, 9000), (0, 10000)]
    pts, idx = RG.tidy(bow)
    assert RG.is_simple(pts)


def test_shell_survives_a_spiked_footprint():
    ext = [[0.0, 0.0], [12.0, 0.0], [12.0, 5.0], [20.0, 5.0], [12.0, 5.01], [12.0, 10.0],
           [0.0, 10.0]]
    br = brief_of([mass(ext, 0.0, 9.0, 3)])
    res = SH.build(br, GN.make(br))
    ck = MB.check(res["arrays"])
    assert ck["open_edges"] == ck["bad_edges"] == ck["degenerate"] == 0
    assert EN.check(br, res["arrays"])["ok"]
