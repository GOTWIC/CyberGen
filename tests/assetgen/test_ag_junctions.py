"""Junctions and their seams. Issues #82 and #89 and AG14's leftovers: AG14's `asset_clash`
finds a sidewalk, a junction's corner or a median over a junction's carriageway
(`fit.strips`). AG17: the street pieces draw M22's pavement map (`streets/pave.py`): two
faces meet on their shared vertices at one height, or a curb's wall between them; a raised
junction stands on its own slab; a cul-de-sac's bulb is drawn whole; AG8 reads a raised
junction's faces from the map."""

from types import SimpleNamespace

import numpy as np

from assetgen.fit.strips import strip_clash


def _fake_packs(pieces: dict):
    """A stand-in for `fit.build.Packs`: {pid: (kind, triangles, materials)}."""
    names, oid = [], {}

    def owner(name):
        if name not in oid:
            oid[name] = len(names)
            names.append(name)
        return oid[name]
    return SimpleNamespace(
        names=names, oid=oid, owner=owner, a=__import__("pathlib").Path("no_such_build/assets"),
        street_ids=lambda: sorted(pieces),
        street_kind=lambda pid: pieces[pid][0],
        street_tris=lambda pid: (np.array(pieces[pid][1], dtype=np.float64), pieces[pid][2]),
        part_mesh=lambda glb, node: None)


def _quad(x0, y0, x1, y1, z):
    return [[[x0, y0, z], [x1, y0, z], [x1, y1, z]], [[x0, y0, z], [x1, y1, z], [x0, y1, z]]]


def _model(sidewalks=()):
    return SimpleNamespace(road_segments=[], junctions=[], crosswalks=[], bridges=[], lanes=[],
                           props=[], sidewalks=list(sidewalks))


def test_the_check_finds_a_sidewalk_across_a_junction():
    jn = ("street.junction", _quad(0.0, 0.0, 30.0, 30.0, 0.05), ["asphalt.street"] * 2)
    walk = SimpleNamespace(id="sw.a", segment_id="rs.a")
    beside = {"jn.a": jn, "sw.a": ("street.sidewalk", _quad(-4.0, 0.0, 0.0, 30.0, 0.2),
                                   ["paving.tile"] * 2)}
    r = strip_clash(_fake_packs(beside), _model([walk]))
    assert sum(r["counts"].values()) == 0, r
    across = dict(beside)
    across["sw.a"] = ("street.sidewalk", _quad(10.0, -4.0, 13.0, 34.0, 0.2), ["paving.tile"] * 2)
    r = strip_clash(_fake_packs(across), _model([walk]))
    assert r["counts"]["strip_on_junction"] == 1, r
    assert r["worst"]["strip_on_junction"][0]["on"] == "jn.a"
    # (a walk passing over it with headroom, or a junction's own corner, is not on it)
    over = dict(beside)
    over["sw.a"] = ("street.sidewalk", _quad(10.0, -4.0, 13.0, 34.0, 6.0), ["paving.tile"] * 2)
    assert sum(strip_clash(_fake_packs(over), _model([walk]))["counts"].values()) == 0
    pad = {"jn.a": ("street.junction", jn[1] + _quad(30.0, 30.0, 34.0, 34.0, 0.2),
                    jn[2] + ["paving.tile"] * 2)}
    assert sum(strip_clash(_fake_packs(pad), _model())["counts"].values()) == 0
    # a corner of another junction over it is
    pad["jn.b"] = ("street.junction", _quad(40.0, 0.0, 60.0, 20.0, 0.05) +
                   _quad(20.0, 20.0, 28.0, 28.0, 0.2), ["asphalt.street"] * 2 +
                   ["paving.tile"] * 2)
    r = strip_clash(_fake_packs(pad), _model())
    assert r["counts"]["strip_on_junction"] == 1, r
    assert r["worst"]["strip_on_junction"][0]["strip"] == "jn.b"


# -- AG17: a tiny pavement map ---------------------------------------------------------------

STYLE = {"archetype": None, "era": "mixed_modern", "grime": 0.0, "wealth": 0.5, "wear": 1.0}


def _map(z: float = 8.0):
    """A junction `jn.a` of two faces at height z over flat ground: its carriageway
    (0, 0)-(10, 10) and a corner pad (10, 0)-(20, 5) beside it, sharing the curb edge from
    (10, 0) to (10, 5)."""
    from assetgen.streets import pave as PV
    from assetgen.streets.ctx import Ground

    pts = {"a": (0.0, 0.0), "b": (10.0, 0.0), "c": (10.0, 5.0), "d": (10.0, 10.0),
           "e": (0.0, 10.0), "f": (20.0, 0.0), "g": (20.0, 5.0)}
    V = [SimpleNamespace(id=k, p=p, z=z) for k, p in sorted(pts.items())]
    E = [SimpleNamespace(id=f"e{u}{v}", kind=k, v=[u, v]) for u, v, k in (
        ("a", "b", "outer"), ("b", "c", "curb"), ("c", "d", "outer"), ("d", "e", "outer"),
        ("e", "a", "outer"), ("b", "f", "outer"), ("f", "g", "outer"), ("g", "c", "outer"))]
    faces = [SimpleNamespace(id="jn.a.pv.jn", owner_id="jn.a", kind="junction", band="jn",
                             layer="g1", rings=[["eab", "ebc", "ecd", "ede", "eea"]],
                             samples=[]),
             SimpleNamespace(id="jn.a.pv.pad_a", owner_id="jn.a", kind="corner",
                             band="pad_a", layer="g1", rings=[["ebf", "efg", "egc", "-ebc"]],
                             samples=[])]
    m = SimpleNamespace(pavement_net=SimpleNamespace(vertices=V, edges=E), pavement=faces,
                        road_segments=[], junctions=[SimpleNamespace(id="jn.a", level=0)],
                        crosswalks=[], buildings=[], parking=[])
    PI = PV.Index(m, Ground(SimpleNamespace(seas=[], rivers=[], channels=[], waterways=[])))
    PI.ramps(m)
    return m, PI


def _cross2(u, v) -> float:
    return u[0] * v[1] - u[1] * v[0]


def _edges(mesh) -> dict:
    """Every mesh edge (its ends' positions, in a fixed order): how many triangles use it."""
    out: dict = {}
    for sl in mesh.slots.values():
        for t in range(0, len(sl.idx), 3):
            a, b, c = (sl.pos[i] for i in sl.idx[t:t + 3])
            for u, v in ((a, b), (b, c), (c, a)):
                k = (min(u, v), max(u, v))
                out[k] = out.get(k, 0) + 1
    return out


def test_two_faces_meet_on_their_shared_vertices():
    """A carriageway and a corner pad beside it: each drawn on its stored vertices, the pad
    `pave.CURB_MM` higher, a curb's wall between them on the same two vertices at the two
    heights: every mesh edge on the shared edge in exactly two triangles."""
    from assetgen.streets import pave as PV
    from assetgen.streets.kit import Mesh, check
    _, PI = _map()
    mesh = Mesh((0.0, 0.0))
    specs: list = []
    for fid in PI.faces_of("jn.a"):
        fi = PI.face_input(fid)
        PV.draw(mesh, fi, "asphalt.street" if fi["cls"] == "top" else "paving.tile")
        PV.walls(mesh, fi, "concrete", PV.ground_bottom, curb_slot="curb.granite", out=specs)
    PV.draw_walls(mesh, specs)
    assert not any(check(mesh.slots).values())
    E = _edges(mesh)
    lo, hi = 8000 + PV.ROAD_DZ_MM, 8000 + PV.ROAD_DZ_MM + PV.CURB_MM
    for z in (lo, hi):
        k = ((10000, 0, z), (10000, 5000, z))
        assert E.get(k) == 2, (z, E.get(k))
    # the curb: its two vertical edges and its foot and top on those vertices
    curb = mesh.slots["curb.granite"]
    assert {p[2] for p in curb.pos} == {lo, hi}
    assert {(p[0], p[1]) for p in curb.pos} == {(10000, 0), (10000, 5000)}


def test_a_raised_junction_stands_on_its_slab():
    """A raised junction's faces stand on a slab of their own (`deck_d` deep, its underside
    under every face, its edges walled), and nothing else under it: no girder runs under a
    junction (AG17), its roads' end on its ports."""
    from assetgen.streets import walks as W
    _, PI = _map(8.0)
    inp = {"faces": [PI.face_input(f) for f in PI.faces_of("jn.a")],
           "junction": {"id": "jn.a", "level": 0, "shape": "multi"}, "style": STYLE,
           "origin": [0.0, 0.0], "top": "avenue", "deck_d": 1.2}
    out = W.make_junction(inp)
    deck = out.mesh.slots["concrete.deck"]
    P = np.array(deck.pos)
    assert P[:, 2].min() == 8000 - 1200
    T = P[np.array(deck.idx).reshape(-1, 3)]
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    under = T[(n[:, 2] < 0)]
    assert len(under) and (under[:, :, 2] == 6800).all()
    # the underside covers both faces' plan (10 x 10 m and 10 x 5 m)
    area = sum(abs(_cross2(t[1] - t[0], t[2] - t[0])) / 2.0 for t in under)
    assert abs(area - 150.0e6) < 1.0
    assert out.notes["corner_pads"] == [1, 0]
    low = [p for sl in out.mesh.slots.values() for p in sl.pos if p[2] < 6800]
    assert not low


def test_a_prop_in_a_raised_corner_with_no_pad_is_left_out():
    """#89, AG17: AG8 leaves out a standing thing in a raised junction's reach at its height
    that stands on none of the map's faces; one on the ground under it, on a pad or on the
    carriageway stays; on a pad it stands on the pad as AG7 draws it."""
    from assetgen.props.gather import _RaisedCorners
    m, PI = _map(8.0)
    rc = _RaisedCorners(m, PI)
    assert rc.unpaved(12.0, 7.0, 8.1)           # in its reach, on no face
    assert not rc.unpaved(15.0, 2.5, 8.1)       # on the pad
    assert not rc.unpaved(5.0, 5.0, 8.1)        # on the carriageway (#95's to keep off)
    assert not rc.unpaved(12.0, 7.0, 0.0)       # on the ground under the junction
    assert not rc.unpaved(30.0, 30.0, 8.1)      # out of its reach
    assert abs(rc.pad_top(15.0, 2.5, 8.1) - 8.2) < 1e-9


def test_a_bulb_is_drawn_whole():
    """A cul-de-sac's bulb (its own face of the map, starting at its road's port: no wedge)
    is drawn whole at the carriageway's height."""
    import math

    from assetgen.streets import pave as PV
    from assetgen.streets import walks as W
    from assetgen.triangulate import area2
    n = 24
    ring = [(int(round(12000 * math.cos(2 * math.pi * k / n))),
             int(round(12000 * math.sin(2 * math.pi * k / n)))) for k in range(n)]
    fi = {"id": "jn.c.pv.jn", "kind": "bulb", "band": "jn", "layer": "g0", "cls": "top",
          "rings": [[[x, y, PV.ROAD_DZ_MM, 0, 0] for x, y in ring]],
          "segs": [[["outer"]] * n], "samples": []}
    inp = {"faces": [fi], "junction": {"id": "jn.c", "level": 0, "shape": "cul_de_sac"},
           "style": STYLE, "origin": [0.0, 0.0], "top": "street", "deck_d": 1.2}
    out = W.make_junction(inp)
    sl = out.mesh.slots["asphalt.street"]
    T = np.array(sl.pos)[np.array(sl.idx).reshape(-1, 3)]
    up = T[np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])[:, 2] > 0]
    area2_ = sum(int(_cross2(t[1] - t[0], t[2] - t[0])) for t in up)
    assert area2_ == area2(ring)
    assert {p[2] for t in up for p in t} == {PV.ROAD_DZ_MM}
