"""Issues #82 and #89, AG7's junctions and AG14's leftovers: AG14's `asset_clash` finds a
sidewalk, a junction's corner or a median over a junction's carriageway (`fit.strips`)."""

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


# -- AG7: overlapping junctions and clipped sidewalks ----------------------------------------

STYLE = {"archetype": None, "era": "mixed_modern", "grime": 0.0, "wealth": 0.5, "wear": 1.0}


def _leg(sid, line, zs, at_start=True, width=20.0, side=0.0, cls="avenue"):
    return {"id": sid, "at_start": at_start, "line": [list(p) for p in line],
            "z_profile": [{"s": s, "z": z} for s, z in zs], "width": width, "side": side,
            "cls": cls}


def _junction(jid, ring, node, legs):
    return {"junction": {"id": jid, "polygon": {"exterior": [list(p) for p in ring],
                                                "holes": []},
                         "level": 0, "shape": "multi", "corner_radius_m": 6.0},
            "node": list(node), "node_ground": 0.0, "legs": legs, "style": STYLE,
            "origin": [0.0, 0.0]}


def _asphalt(out) -> np.ndarray:
    return np.array([p for k, sl in out.mesh.slots.items() if k.startswith("asphalt")
                     for p in sl.pos], dtype=np.float64) / 1000.0


def test_an_overlapping_junction_leaves_the_overlap_to_its_owner():
    """#82: two junctions whose outlines overlap (M17's shared pavement of two roads between
    their nodes): the larger draws the overlap, the other only the rest, and along the
    owner's outline the other's surface takes the owner's heights (no step between them)."""
    from assetgen.streets import walks as W
    from assetgen.streets.roads import ROAD_DZ
    ramp = [(0.0, 0.0), (0.0, 50.0)]
    a = _junction("jn.a", [(-10, -10), (10, -10), (10, 50), (-10, 50)], (0.0, 0.0, 5.0),
                  [_leg("rs.s", [(0.0, 0.0), (0.0, -60.0)], [(0, 5.0), (60, 5.0)]),
                   _leg("rs.r", ramp, [(0, 5.0), (50, 0.0)])])
    b = _junction("jn.b", [(-10, 20), (10, 20), (10, 70), (-10, 70)], (0.0, 50.0, 0.0),
                  [_leg("rs.r", ramp, [(0, 5.0), (50, 0.0)], at_start=False),
                   _leg("rs.n", [(0.0, 50.0), (0.0, 100.0)], [(0, 0.0), (50, 0.0)])])
    sa = W._surface(a)
    b["overlaps"] = [{"id": "jn.a", "ring": a["junction"]["polygon"]["exterior"],
                      "owner": True,
                      "drawn": [[x, y, sa["zfun"](x, y)] for x, y in sa["cring"]]}]
    a["overlaps"] = [{"id": "jn.b", "ring": b["junction"]["polygon"]["exterior"]}]
    pa = _asphalt(W.make_junction(a))
    pb = _asphalt(W.make_junction(b))
    assert pa[:, 1].min() < -9.9 and pa[:, 1].max() > 49.9          # the owner whole
    assert pb[:, 1].min() > 49.9 and pb[:, 1].max() > 69.9          # the rest only
    seam = pb[np.abs(pb[:, 1] - 50.0) < 0.01]
    assert len(seam) >= 2
    assert np.allclose(seam[:, 2], ROAD_DZ, atol=0.002)             # the owner's height there


def test_a_sidewalk_is_not_drawn_over_a_junction():
    """#82: a sidewalk M2 laid along a whole road (its cuts at two overlapping junctions
    overlap) is drawn only where its slab is off the junctions it reaches into."""
    from assetgen.streets import walks as W
    seg = {"id": "rs.a", "centerline": [[0.0, -20.0], [0.0, 40.0]], "width_m": 20.0,
           "road_class": "avenue", "z_profile": [{"s": 0.0, "z": 0.0}, {"s": 60.0, "z": 0.0}],
           "cross_section": {"sidewalk_m": [3.0, 3.0], "median_m": 0.0, "curb_m": 0.15},
           "attrs": {}}
    road = {"seg": seg, "cls": "avenue", "ends": [], "crossings": [], "lanes": [],
            "start": "a", "end": "b", "origin": [0.0, 0.0]}
    walk = {"id": "rs.a.swl", "line": [[-8.5, -20.0], [-8.5, 40.0]], "width_m": 3.0,
            "side": "left", "curb_m": 0.15}
    inp = {"walk": walk, "road": road, "style": STYLE, "drops": [], "trees": [],
           "origin": [0.0, 0.0]}
    whole = W.make_sidewalk(dict(inp))
    y = np.array([p[1] for sl in whole.mesh.slots.values() for p in sl.pos]) / 1000.0
    assert ((y > 12.0) & (y < 28.0)).any()
    inp["clip"] = [{"id": "jn.x", "ring": [[-20.0, 10.0], [20.0, 10.0], [20.0, 30.0],
                                          [-20.0, 30.0]]}]
    cut = W.make_sidewalk(inp)
    y = np.array([p[1] for sl in cut.mesh.slots.values() for p in sl.pos]) / 1000.0
    assert not ((y > 10.06) & (y < 29.94)).any()
    assert y.min() < -19.9 and y.max() > 39.9


def test_a_prop_in_a_raised_corner_with_no_pad_is_left_out():
    """#89: AG8 leaves out a standing thing in a raised junction's corner (AG7's notes) at
    the junction's height that stands on neither its carriageway nor a pad AG7 drew; one on
    the ground under it, or on a pad, stays."""
    from assetgen.props.gather import _RaisedCorners
    note = {"area": [[[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0]]],
            "carriageway": [[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]],
            "z": [8.0, 8.5],
            "pads": [[[10.0, 0.0, 8.2], [20.0, 0.0, 8.2], [20.0, 5.0, 8.2], [10.0, 5.0, 8.2]]]}
    rc = _RaisedCorners([note])
    assert rc.unpaved(15.0, 15.0, 8.1)          # in the corner, no pad under it
    assert not rc.unpaved(15.0, 2.5, 8.1)       # on a pad
    assert not rc.unpaved(5.0, 5.0, 8.1)        # on the carriageway (#95's to keep off)
    assert not rc.unpaved(15.0, 15.0, 0.0)      # on the ground under the junction
    assert not rc.unpaved(30.0, 30.0, 8.1)      # not in its corners
