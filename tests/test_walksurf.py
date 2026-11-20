"""people_surfaces: walkways on the surface stage 2 draws (`citygen.walksurf`): a sidewalk over
a road's hump follows the hump between its vertices, a crossing of a raised road climbs onto
it, a face over the walkway (a viaduct) is not taken, the lines that meet meet at one height,
and the check measures exported lines against the surface. (The small city's graphs.json:
`test_unreal.test_graphs_carry_the_draped_walkways`.)"""

from __future__ import annotations

import numpy as np

from citygen import walksurf as WS

MID, HALF, TOP = 150.0, 110.0, 4.5      # a hump 4.5 m high over 220 m: 6.4% at most


def _z(x: float) -> float:
    """The road's hump, a cosine (its vertical curves)."""
    return round(TOP * 0.5 * (1.0 + float(np.cos(np.pi * (x - MID) / HALF))), 3) \
        if abs(x - MID) < HALF else 0.0


PROFILE = [(float(x), _z(x)) for x in range(0, 301)]


class _Net:
    """A pavement map built face by face: vertices by their cell, an edge per side."""

    def __init__(self):
        self.vertices, self.edges, self.faces = {}, [], []

    def vid(self, p) -> str:
        k = f"v{round(p[0] * 1000)}_{round(p[1] * 1000)}_{round(p[2] * 1000)}"
        self.vertices[k] = {"id": k, "p": [p[0], p[1]], "z": p[2]}
        return k

    def face(self, fid, owner, kind, ring, layer="g0"):
        ids = [self.vid(p) for p in ring]
        refs = []
        for k, (a, b) in enumerate(zip(ids, ids[1:] + ids[:1])):
            eid = f"{fid}.e{k}"
            self.edges.append({"id": eid, "kind": "band", "v": [a, b]})
            refs.append(eid)
        self.faces.append({"id": fid, "owner_id": owner, "kind": kind, "band": "b",
                           "layer": layer, "rings": [refs]})


def _strip(net, fid, owner, kind, y0, y1):
    xs = [float(x) for x in range(0, 301)]                    # (stations every meter)
    ring = [(x, y0, _z(x)) for x in xs] + [(x, y1, _z(x)) for x in reversed(xs)]
    net.face(fid, owner, kind, ring)


def _model():
    """A road over a hump (4.5 m at x 150), its sidewalk north of it split at x 150 (the model
    keeps both at the ground), a crossing at x 150 to a sidewalk south, a door's path to the
    north sidewalk, and a viaduct's deck 9 m over the north sidewalk between x 140 and 160."""
    net = _Net()
    _strip(net, "rs.a.pv.cw", "rs.a", "carriageway", -5.0, 5.0)
    _strip(net, "rs.a.pv.swl", "rs.a", "sidewalk", 5.0, 8.0)
    _strip(net, "rs.a.pv.swr", "rs.a", "sidewalk", -8.0, -5.0)
    net.face("rs.v.pv.cw", "rs.v", "carriageway",
             [(140.0, 0.0, 9.0), (160.0, 0.0, 9.0), (160.0, 12.0, 9.0), (140.0, 12.0, 9.0)],
             "g1")
    seg = {"id": "rs.a", "centerline": [[0.0, 0.0], [300.0, 0.0]],
           "z_profile": [{"s": s, "z": z} for s, z in PROFILE]}
    walks = [
        {"id": "wk.n1", "kind": "sidewalk", "line": [[0.0, 6.5, 0.0], [MID, 6.5, 0.0]],
         "attrs": {"segment": "rs.a"}, "level": 0},
        {"id": "wk.n2", "kind": "sidewalk", "line": [[MID, 6.5, 0.0], [300.0, 6.5, 0.0]],
         "attrs": {"segment": "rs.a"}, "level": 0},
        {"id": "wk.s", "kind": "sidewalk", "line": [[0.0, -6.5, 0.0], [MID, -6.5, 0.0]],
         "attrs": {"segment": "rs.a"}, "level": 0},
        {"id": "wk.x", "kind": "crossing", "line": [[MID, 6.5, 0.0], [MID, -6.5, 0.0]],
         "attrs": {"junction": "jn.a"}, "level": 0},
        {"id": "wk.door", "kind": "path", "line": [[MID, 20.0, 0.0], [MID, 6.5, 0.0]],
         "attrs": {"door": True}, "level": 0},
        {"id": "wk.lift", "kind": "elevator", "line": [[10.0, 6.5, 0.0], [10.0, 6.5, 9.0]],
         "attrs": {}, "level": 1},
    ]
    return {"pavement": net.faces,
            "pavement_net": {"vertices": list(net.vertices.values()), "edges": net.edges},
            "road_segments": [seg], "walkways": walks}


def test_a_sidewalk_follows_its_roads_hump():
    m = _model()
    out = WS.drape(m)
    assert set(out) == {"wk.n1", "wk.n2", "wk.s", "wk.x", "wk.door"}     # (not the elevator)
    pts, vk = out["wk.n1"]
    # its vertices kept where they were, in plan; points added where the profile bends
    assert [pts[i][:2] for i in vk] == [[0.0, 6.5], [MID, 6.5]] and len(pts) > 6
    for x, y, z in pts:
        assert abs(z - (_z(x) + WS.CURB_LIFT_M)) < 0.03, (x, z)
    # between its points, every eighth of a stretch, on the sidewalk (not the deck 9 m over
    # it; the model's straight line from 0 to 0 is 4.7 m under the crest)
    for a, b in zip(pts, pts[1:]):
        for t in np.linspace(0.0, 1.0, 9):
            x = a[0] + t * (b[0] - a[0])
            z = a[2] + t * (b[2] - a[2])
            assert abs(z - (_z(x) + WS.CURB_LIFT_M)) <= WS.TOL_M + 0.03, (x, z)
    # the flat stretch keeps only what it needs
    assert sum(1 for p in pts if p[0] < MID - HALF - 1.0) <= 2


def test_crossings_and_paths_climb_with_the_walkways_they_join():
    m = _model()
    out = WS.drape(m)
    x = out["wk.x"][0]
    # the crossing of the raised road (at the ground in the model): on its sidewalks at the
    # ends, on its carriageway between
    assert abs(x[0][2] - (TOP + WS.CURB_LIFT_M)) < 0.03
    assert abs(x[-1][2] - (TOP + WS.CURB_LIFT_M)) < 0.03
    mid = min(x, key=lambda p: abs(p[1]))
    # (10 m across, the face's mean value coordinates round the crest off by a few cm, as
    # AG17's samples inside it do)
    assert abs(mid[2] - (TOP + WS.ROAD_LIFT_M)) < 0.08
    # ends that meet, at one height
    n1, n2, door = out["wk.n1"][0], out["wk.n2"][0], out["wk.door"][0]
    assert n1[-1][2] == n2[0][2] == x[0][2] == door[-1][2]
    # the door's path off the map: from its door at the ground up to the sidewalk
    assert door[0][2] == 0.0


def test_check_measures_lines_against_the_surface():
    m = _model()
    out = WS.drape(m)
    lines = {k: v[0] for k, v in out.items()}
    r = WS.check(m, lines)
    assert r["walkways"] == 5 and r["failed"] == 0 and r["worst_m"] <= WS.CHECK_TOL_M, r
    # the model's own lines: straight from 0 to 0 under a 4.5 m hump
    r = WS.check(m, {w["id"]: w["line"] for w in m["walkways"]})
    assert r["failed"] >= 1 and r["worst_m"] > 1.0


def test_a_walkway_along_a_faces_edge_is_on_it():
    """A crossing laid along a road's end (the crossings fix's crossing of a dead end at the
    map's edge), its line on the 1 cm grid a few millimeters in and out of the faces' end
    edge: on the road's surface all the way, not on it only where it falls inside (the hilly
    test city's `wk.e460n1200` stood 0.7 m off the median past the middle)."""
    net = _Net()
    net.face("rs.e.pv.cw", "rs.e", "carriageway",
             [(250.0, -5.0, 0.6), (300.0, -5.0, 0.6), (300.0, 5.0, 0.6), (250.0, 5.0, 0.6)])
    walk = {"id": "wk.end", "kind": "crossing", "line": [[300.006, 5.0, 0.0],
                                                         [299.994, -5.0, 0.0]],
            "attrs": {"segment": "rs.e"}, "level": 0}
    m = {"pavement": net.faces,
         "pavement_net": {"vertices": list(net.vertices.values()), "edges": net.edges},
         "road_segments": [], "walkways": [walk]}
    pts = WS.drape(m)["wk.end"][0]
    assert all(abs(p[2] - (0.6 + WS.ROAD_LIFT_M)) < 1e-6 for p in pts), pts
    r = WS.check(m, {"wk.end": pts})
    assert r["failed"] == 0 and r["worst_m"] < 1e-6, r


def test_lifegen_checks_the_lines_it_will_walk(tmp_path):
    """lifegen's `walk_heights` reads BUILD/graphs.json: draped lines pass, a raised road's
    walkways at the ground (the model's) fail, a graphs.json from before is not measured."""
    import json

    from lifegen.airwater import Ground
    from lifegen.plan import walk_heights

    m = _model()
    out = WS.drape(m)
    walks = [{"id": w["id"], "kind": w["kind"], "line": out[w["id"]][0] if w["id"] in out
              else w["line"]} for w in m["walkways"]]
    g = tmp_path / "graphs.json"
    g.write_text(json.dumps({"walkways": walks, "walk_surface": WS.VERSION}))
    assert walk_heights(tmp_path, m, Ground(m))["ok"]
    g.write_text(json.dumps({"walkways": m["walkways"], "walk_surface": WS.VERSION}))
    r = walk_heights(tmp_path, m, Ground(m))
    assert not r["ok"] and "wk.n1" in r["detail"]
    g.write_text(json.dumps({"walkways": m["walkways"]}))
    assert walk_heights(tmp_path, m, Ground(m))["ok"]
