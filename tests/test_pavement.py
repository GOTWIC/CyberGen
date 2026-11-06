"""M22: the pavement map (`citygen/pavement.py`, `pavetri.py`, `pavement_checks.py`)."""

import math
from types import SimpleNamespace

import numpy as np
from shapely.geometry import LineString, Polygon

from citygen import pavement as PV
from citygen import pavement_checks as PVC
from citygen import pavetri as PT
from citygen import streets as ST
from citygen.model import CityModel

from conftest import ROOT, built_sample

VESPER_BAY = ROOT / "cities" / "vesper_bay" / "city_spec.json"
SPEC = SimpleNamespace(highways=SimpleNamespace(grades=SimpleNamespace(ramp_max=0.08)))
M22 = ("pavement_edges", "pavement_tiling", "pavement_heights", "pavement_junctions")


def _seg(sid, a, b, pts, cls="street", z0=0.0, z1=None, cuts=(0.0, 0.0)) -> dict:
    cs = ST.cross_section(cls, "midtown_mixed")
    L = LineString(pts).length
    z1 = z0 if z1 is None else z1
    return {"id": sid, "start": a, "end": b, "road_class": cls, "lanes": 2,
            "width_m": cs["total_width_m"], "centerline": [list(p) for p in pts],
            "cross_section": cs, "z_profile": [{"s": 0.0, "z": z0}, {"s": L, "z": z1}],
            "attrs": {"role": "grid_u", "cuts": list(cuts)}}


def _map(nodes: dict, segs: list, junctions: list) -> CityModel:
    """The map of a network's rows ({id: (x, y, z)}, segments with their cuts, junction rows)
    as a model the checks read."""
    nrows = [{"id": k, "position": list(p), "attrs": {}} for k, p in nodes.items()]
    jrows = [dict(j, attrs=dict(j.get("attrs") or {})) for j in junctions]
    # (the segments' cuts onto the junctions at their ends, as `junctions.build` stores them)
    for j in jrows:
        ns = set(j["attrs"].get("nodes") or [j["node_id"]])
        inner = set(j["attrs"].get("inner") or [])
        cuts = sorted([s["id"], end, c] for s in segs if s["id"] not in inner
                      for end, nid, c in (("a", s["start"], s["attrs"]["cuts"][0]),
                                          ("b", s["end"], s["attrs"]["cuts"][1]))
                      if nid in ns and c > 0.0)
        if cuts:
            j["attrs"]["cuts"] = cuts
    for s in segs:
        s["attrs"].pop("cuts", None)
    mp = PV.make(segs, nrows, jrows, {})
    for j in jrows:
        if not isinstance(j["polygon"], dict):
            from citygen import geom as G

            j["polygon"] = G.to_model_poly(j["polygon"])
    return CityModel.model_validate({
        "name": "t", "seed": 1, "bounds": (-200, -200, 200, 200), "road_nodes": nrows,
        "road_segments": segs, "junctions": jrows, "pavement": mp.faces,
        "pavement_net": mp.net})


def _junction(jid, nid, legs, **attrs) -> dict:
    return {"id": jid, "type": "junction.x", "node_id": nid, "polygon": None,
            "shape": "X", "legs": legs, "signalized": False, "corner_radius_m": 8.0,
            "attrs": attrs}


def _cross(z: dict | None = None):
    """Four streets 100 m long meeting at the origin, each cut 12 m from it."""
    z = z or {}
    ends = {"e": (100, 0), "n": (0, 100), "w": (-100, 0), "s": (0, -100)}
    nodes = {"o": (0.0, 0.0, 0.0)}
    segs = []
    for k, (x, y) in ends.items():
        nodes[k] = (float(x), float(y), 0.0)
        segs.append(_seg(f"r{k}", "o", k, [(0.0, 0.0), (float(x), float(y))],
                         z0=z.get(k, (0.0, 0.0))[0], z1=z.get(k, (0.0, 0.0))[1],
                         cuts=(12.0, 0.0)))
    return nodes, segs, [_junction("jo", "o", 4)]


def _checks(m) -> dict:
    return {c.id: c for c in (PVC.check_edges(SPEC, m), PVC.check_tiling(SPEC, m),
                              PVC.check_heights(SPEC, m), PVC.check_junctions(SPEC, m))}


def test_triangulation_is_exact():
    """A square with a square hole: the triangles cover its area exactly (integer mm)."""
    outer = [(0, 0), (10000, 0), (10000, 10000), (0, 10000)]
    hole = [(3000, 3000), (3000, 6000), (6000, 6000), (6000, 3000)]
    pts, tris = PT.triangulate([outer, hole], [])
    area2 = 0
    for a, b, c in tris:
        (ax, ay), (bx, by), (cx, cy) = pts[a], pts[b], pts[c]
        area2 += (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    assert area2 == 2 * (10000 * 10000 - 3000 * 3000)


def test_mean_value_coordinates_keep_a_plane():
    """Mean value coordinates of a boundary that lies on a plane give that plane inside."""
    def z(x, y):
        return 1.0 + 0.03 * x - 0.02 * y
    ring = [(x, y, z(x, y)) for x, y in [(0, 0), (30, 0), (40, 20), (10, 35), (-5, 15)]]
    gx, gy = np.array([10.0, 20.0, 5.0]), np.array([10.0, 15.0, 20.0])
    got = PV.mvc([ring], gx, gy)
    assert np.allclose(got, [z(x, y) for x, y in zip(gx, gy)], atol=1e-9)


def test_a_cross_tiles_its_right_of_way():
    nodes, segs, jn = _cross()
    m = _map(nodes, segs, jn)
    cs = _checks(m)
    for cid in M22:
        assert cs[cid].passed, (cid, cs[cid].failures[:5])
    kinds = sorted(f.kind for f in m.pavement)
    assert kinds.count("junction") == 1 and kinds.count("corner") == 4
    # (the faces cover the four rights of way exactly, the crossing once)
    N = PVC.Net(m)
    area = sum(N.poly(f.id).area for f in m.pavement)
    w = segs[0]["width_m"]
    assert abs(area - (4 * 100 * w - w * w)) < 0.01
    # (every interior edge is shared by exactly two faces, the same vertices)
    uses: dict = {}
    for f in m.pavement:
        for ring in f.rings:
            for ref in ring:
                uses[ref.lstrip("-")] = uses.get(ref.lstrip("-"), 0) + 1
    inner = [e for e in m.pavement_net.edges if e.kind != "outer"]
    assert inner and all(uses[e.id] == 2 for e in inner)
    # (the junction's polygon is its carriageway face's outline, its curb heights given
    # where it is not flat)
    j = m.junctions[0]
    assert Polygon(j.polygon.exterior).area > w * w * 0.5


def test_a_sloped_junction_takes_its_heights_from_its_ports():
    """Legs at different heights within the grade: every port level across its road, the
    junction's faces sampled inside and within the grade."""
    nodes, segs, jn = _cross({"e": (0.4, 3.0), "w": (0.0, -2.0), "n": (0.2, 0.2),
                              "s": (0.2, 0.2)})
    m = _map(nodes, segs, jn)
    cs = _checks(m)
    for cid in M22:
        assert cs[cid].passed, (cid, cs[cid].failures[:5])
    N = PVC.Net(m)
    zs = {round(N.z(v), 3) for f in m.pavement if f.kind == "junction" for r in N.rings[f.id]
          for v in r}
    assert len(zs) > 2
    for e in m.pavement_net.edges:
        if e.kind == "port":
            hs = [N.z(v) for v in e.v]
            assert max(hs) - min(hs) <= PVC.LEVEL_TOL_M
    # (a face's triangles, its boundary and samples, cover it exactly: what AG17 draws)
    for f in m.pavement:
        if f.kind != "junction":
            continue
        tris = PVC.face_triangles(N, f)
        area = sum(abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2.0
                   for a, b, c in tris)
        assert abs(area - N.poly(f.id).area) < 1e-3


def test_two_junctions_too_close_are_one():
    """Two junctions 8 m apart along a street whose cuts meet: one junction face for both
    nodes, the street between them inside it."""
    nodes = {"a": (0.0, 0.0, 0.0), "b": (8.0, 0.0, 0.0), "w": (-100.0, 0.0, 0.0),
             "e": (108.0, 0.0, 0.0), "na": (0.0, 100.0, 0.0), "sb": (8.0, -100.0, 0.0)}
    segs = [_seg("ab", "a", "b", [(0.0, 0.0), (8.0, 0.0)], cuts=(4.0, 4.0)),
            _seg("aw", "a", "w", [(0.0, 0.0), (-100.0, 0.0)], cuts=(12.0, 0.0)),
            _seg("be", "b", "e", [(8.0, 0.0), (108.0, 0.0)], cuts=(12.0, 0.0)),
            _seg("an", "a", "na", [(0.0, 0.0), (0.0, 100.0)], cuts=(12.0, 0.0)),
            _seg("bs", "b", "sb", [(8.0, 0.0), (8.0, -100.0)], cuts=(12.0, 0.0))]
    jn = [_junction("jab", "a", 5, nodes=["a", "b"], inner=["ab"])]
    m = _map(nodes, segs, jn)
    cs = _checks(m)
    for cid in M22:
        assert cs[cid].passed, (cid, cs[cid].failures[:5])
    owners = {f.owner_id for f in m.pavement}
    assert "ab" not in owners and "jab" in owners
    assert sum(1 for f in m.pavement if f.kind == "junction") == 1


def test_a_face_off_its_owner_fails():
    """`pavement_tiling` fails a face that reaches off its owner's right of way (a hairpin's
    mitre once drew one hundreds of meters long)."""
    nodes, segs, jn = _cross()
    m = _map(nodes, segs, jn)
    f = next(x for x in m.pavement if x.kind == "carriageway")
    net = m.pavement_net.model_dump()
    first = f.rings[0][0].lstrip("-")
    e = next(x for x in net["edges"] if x["id"] == first)
    v = next(x for x in net["vertices"] if x["id"] == e["v"][0])
    v["p"] = [v["p"][0], v["p"][1] + 40.0]
    bad = m.model_copy(update={"pavement_net": type(m.pavement_net).model_validate(net)})
    c = PVC.check_tiling(SPEC, bad)
    assert any("off its owner" in x for x in c.failures)


def test_bend_faces_stay_on_their_road():
    """A street that turns back on itself (a hairpin, turn near 180 degrees) gets a bend face
    over the fold, on its own right of way, not the mitre's spike."""
    pts = [(0.0, 0.0), (60.0, 0.0), (62.0, 2.0), (0.0, 6.0)]
    seg = _seg("h", "a", "b", pts)
    rd = PV.Road(seg)
    folds = rd.folds(0.0, rd.path.L)
    assert folds
    g = rd.fold_poly(folds[0][0], folds[0][1], rd.row)
    assert g.buffer(-0.5).within(LineString(pts).buffer(rd.row + 0.01))


def test_sample_passes_the_map_checks():
    b, _, _ = built_sample(VESPER_BAY)
    checks = {c.id: c for c in b.checks}
    for cid in M22:
        assert cid in checks, cid
        assert checks[cid].passed, (cid, checks[cid].failures[:5])
    m = b.model
    assert m.pavement and m.pavement_net is not None
    jids = {j.id for j in m.junctions}
    sids = {s.id for s in m.road_segments}
    assert all(f.owner_id in jids | sids for f in m.pavement)
    # (a junction's polygon is its carriageway face's outline)
    N = PVC.Net(m)
    faces = {f.owner_id: N.poly(f.id) for f in m.pavement if f.kind == "junction"}
    for j in m.junctions:
        if j.id in faces and len([f for f in m.pavement if f.owner_id == j.id and
                                  f.kind == "junction"]) == 1:
            # (holes too: a cluster's carriageway can ring an island)
            face = Polygon(j.polygon.exterior, j.polygon.holes)
            assert abs(face.area - faces[j.id].area) < 0.05 * faces[j.id].area + 1.0
    # (every junction kept as M18 left it says what holds it)
    from citygen.junctions import why_text

    for j in m.junctions:
        if j.attrs.get("unbuildable"):
            assert why_text(j.attrs["unbuildable"])
    assert math.isfinite(sum(v.z for v in m.pavement_net.vertices))
    # (the map made again from the finished model's rows, as a district regeneration makes
    # it, is the map M2 made: its ties go by geometry, never by the ids M10 renames)
    from citygen import build as B
    from citygen import geom as G

    with G.canonical():
        again = B.pavement_of(b.spec, m)
    assert again.pavement == m.pavement and again.pavement_net == m.pavement_net
    assert [j.polygon for j in again.junctions] == [j.polygon for j in m.junctions]
