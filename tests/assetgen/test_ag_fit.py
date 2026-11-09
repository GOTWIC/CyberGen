"""AG14, fit and finish (scope 14.15): the fit checks read the packs back (`assetgen/fit/`);
M19's supports drawn (frames, cantilevers, piers on footings, masts with stays); a road
column in the water on a footing; a bridge whose road segments carry it draws no deck of its
own; M18's embankments under a deck; roof items on the roof the shell built; curved walls
smooth, glazed round the curve; nothing over a road with no sidewalk under the vehicles'
headroom; and the small test city passes both checks."""

import math

import numpy as np

from assetgen import gltf as GT
from assetgen.fit import glb as GL
from assetgen.fit.build import GAP_M, feet, rest_gaps
from assetgen.fit.index import Surfaces
from assetgen.streets import kit as K
from assetgen.streets.materials import gltf_materials

from agtools import small_assets, small_assets_report, small_build

STYLE = {"archetype": None, "era": "mixed_modern", "grime": 0.0, "wealth": 0.5, "wear": 1.0}


def test_surfaces_find_the_highest_floor_under_a_point():
    ground = [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]]
    roof = [[1.0, 1.0, 2.0], [4.0, 1.0, 2.0], [1.0, 4.0, 2.0]]
    wall = [[1.0, 1.0, 0.0], [4.0, 1.0, 0.0], [4.0, 1.0, 2.0]]          # vertical: no floor
    S = Surfaces(np.array([ground, roof, wall]), np.array([0, 1, 2]))
    P = np.array([[2.0, 2.0, 2.01], [2.0, 2.0, 1.0], [8.0, 1.0, 0.5], [20.0, 20.0, 0.0]])
    z = S.under(P, 0.3)
    assert abs(z[0] - 2.0) < 1e-9 and abs(z[1]) < 1e-9 and abs(z[2]) < 1e-9
    assert math.isnan(z[3])
    # a point's own owner does not hold it up
    z = S.under(P[:1], 0.3, exclude=np.array([1]))
    assert abs(z[0]) < 1e-9


def test_a_thing_rests_on_three_of_its_five_feet():
    """#105: one foot on a surface does not hold the other four up."""
    nan = float("nan")
    g = np.array([[0.0, nan, nan, nan, nan],          # one foot on the roof, four over air
                  [0.0, 0.01, 0.5, 0.5, 2.0],         # two feet on it
                  [0.0, 0.0, 0.0, 2.3, 1.8],          # three: rests
                  [0.01, -0.3, 0.0, 0.5, nan],        # a foot set into a slope counts
                  [nan, nan, nan, nan, nan]])
    r = rest_gaps(g)
    assert not r[0] <= GAP_M and not r[1] <= GAP_M and not r[4] <= GAP_M
    assert r[2] <= GAP_M and r[3] <= GAP_M and r[1] == 0.5 and np.isinf(r[0])


def test_packs_read_back_in_world_space(tmp_path):
    m = K.Mesh((100.0, 50.0))
    m.box("concrete", 100.0, 50.0, 2.0, 4.0, 2.0, 3.0)
    g = GT.Gltf(generator="test")
    mats = gltf_materials(g, set(m.slots))
    mi = g.mesh("box", m.finish(mats))
    g.node("box", mi, translation=(100000, 50000, 0), root=True, extras={"kind": "t"})
    f = tmp_path / "t.glb"
    f.write_bytes(g.to_glb())
    nodes = GL.read(f)
    assert [n.name for n in nodes] == ["box"]
    T = nodes[0].triangles()
    lo, hi = T.reshape(-1, 3).min(axis=0), T.reshape(-1, 3).max(axis=0)
    assert np.allclose(lo, [98.0, 49.0, 2.0], atol=2e-3)
    assert np.allclose(hi, [102.0, 51.0, 5.0], atol=2e-3)
    F = feet(T.reshape(-1, 3))
    assert np.allclose(F[:, 2], 2.0, atol=2e-3) and np.allclose(F[0, :2], [100.0, 50.0])


def _col(form: str, **attrs) -> dict:
    ring = [[-0.9, -0.9], [0.9, -0.9], [0.9, 0.9], [-0.9, 0.9]]
    a = {"line_id": "tl.x", "mode": attrs.pop("mode", "elevated_rail"), "form": form,
         "s_m": 10.0}
    a.update(attrs)
    return {"st": {"id": "tl.x.col0001", "kind": "column", "z0_m": 0.0, "z1_m": 14.0,
                   "footprint": {"exterior": ring, "holes": []}, "attrs": a},
            "origin": [0.0, 0.0], "ground_c": None, "dir": [1.0, 0.0]}


def test_m19_supports_are_drawn():
    from assetgen.streets.transit import make_transit_beam, make_transit_column
    plain = make_transit_column(_col("column")).mesh
    # a pier stands on its footing, down into M16's bed under the water
    inp = _col("pier")
    inp["bed"] = -6.0
    pier = make_transit_column(inp).mesh
    zs = [p[2] for s in pier.slots.values() for p in s.pos]
    assert min(zs) == -6500 and pier.triangles > plain.triangles
    # a frame's leg ends flat under its cap beam: no cap of its own
    leg = make_transit_column(_col("frame", frame="tl.x.cap0001")).mesh
    assert max(p[2] for s in leg.slots.values() for p in s.pos) == 14000
    assert leg.triangles == 10
    # a sky tube's mast: crosshead, two legs to the mast top, a tie and four stays
    mast = make_transit_column(_col("mast", mode="sky_tube", mast_top_m=40.0,
                                    stays=[[-60.0, 0.0, 21.0], [60.0, 0.0, 21.0]])).mesh
    assert "steel.cable" in mast.slots
    assert max(p[2] for s in mast.slots.values() for p in s.pos) == 40000
    for m in (plain, pier, leg, mast):
        assert not any(K.check(m.slots).values())
    # a frame's beam is haunched: deeper over its legs than in its middle
    beam = {"st": {"id": "tl.x.cap0001", "kind": "beam", "z0_m": 12.4, "z1_m": 14.0,
                   "line": [[-8.0, 0.0, 14.0], [8.0, 0.0, 14.0]],
                   "attrs": {"line_id": "tl.x", "form": "frame", "width_m": 1.8,
                             "deck_m": 1.6}}, "origin": [0.0, 0.0]}
    bm = make_transit_beam(beam).mesh
    P = np.array([p for s in bm.slots.values() for p in s.pos])
    mid = P[np.abs(P[:, 0]) < 5000]
    assert P[:, 2].min() == 12400 and mid[:, 2].min() > 12400
    assert not any(K.check(bm.slots).values())


def _band_face(x0: float, x1: float, half: float, zf, step: float = 5.0) -> dict:
    """A straight road's carriageway as a face of the pavement map (`pave.Index.face_input`):
    vertices every `step` along both edges at heights zf(x) over flat ground."""
    def mm(v):
        return int(round(v * 1000.0))
    xs = [x0 + k * step for k in range(int(round((x1 - x0) / step)) + 1)]
    ring = [(x, -half) for x in xs] + [(x, half) for x in reversed(xs)]
    verts = [[mm(x), mm(y), mm(zf(x)) + 50, mm(zf(x)), mm(zf(x))] for x, y in ring]
    return {"id": "rs.e0n0.pv.cw", "kind": "carriageway", "band": "cw", "layer": "g1",
            "cls": "top", "rings": [verts], "segs": [[["outer"]] * len(ring)], "samples": []}


def test_a_low_deck_stands_on_its_embankment():
    from assetgen.streets.path import Profile
    from assetgen.streets.roads import _spans
    from assetgen.streets.roads import make as make_road
    assert _spans(0.0, 100.0, [(20.0, 40.0), (35.0, 60.0)]) == [(0.0, 20.0), (60.0, 100.0)]
    zp = [{"s": 0.0, "z": 0.0}, {"s": 50.0, "z": 3.0}, {"s": 100.0, "z": 9.0}]
    seg = {"id": "rs.e0n0", "centerline": [[0.0, 0.0], [100.0, 0.0]], "z_profile": zp,
           "width_m": 8.0, "road_class": "street", "attrs": {"role": "ramp"},
           "cross_section": {"sidewalk_m": [0.0, 0.0], "median_m": 0.0, "shared": False}}
    inp = {"seg": seg, "cls": "street", "ends": [], "crossings": [], "lanes": [],
           "style": STYLE, "start": "a", "end": "b", "origin": [50.0, 0.0],
           "embankments": [[0.0, 70.0]], "faces": [_band_face(0.0, 100.0, 4.0, Profile.of(zp))]}
    mesh = make_road(inp).mesh
    deck = [p for p in mesh.slots["concrete.deck"].pos]
    # the girder and its fascia only past the fill (x over 70 m), the fill's faces (its
    # walls down to the ground) and its end across
    assert min(p[0] for p in deck) >= 70000 - 50000 - 1
    sl = mesh.slots["concrete"]
    P = np.array(sl.pos)
    T = P[np.array(sl.idx).reshape(-1, 3)]
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    end = (np.abs(T[:, :, 0] - 20000).max(axis=1) < 2) & (n[:, 0] > 0)
    assert end.any()                # (the fill's face across, toward the girder)
    assert P[:, 2].min() <= -100    # (its sides into the ground)
    assert not any(K.check(mesh.slots).values())


def test_curved_walls_are_smooth_and_glazed():
    import json

    from assetgen import build as AB
    from assetgen.buildings import genome as GN
    from assetgen.buildings.shell import arc_of
    br = json.loads((small_build() / "base" / "assets" / "briefs.json").read_text(
        encoding="utf-8"))
    br = br.get("briefs", br)
    ids = [b for b in sorted(br) if any(m.get("arcs") for m in br[b]["masses"]) and
           br[b]["building"].get("form", {}) and
           br[b]["building"]["form"].get("kind") == "rounded"]
    assert ids
    bid = ids[0]
    sh, _, rec = AB.building_asset(br[bid], GN.make(br[bid]))
    buf = sh["buf"]
    assert buf.arc_of and not any(v for k, v in rec["checks"]["mesh"].items()
                                  if k not in ("triangles", "parts", "uv0"))
    assert rec["checks"]["envelope"]["ok"]
    # every vertex of an arc's planes takes the radial normal (its chords shade as one)
    prims = buf.primitives(sh["shell"], {n: 0 for n in sh["shell"]})
    seen = 0
    for name, pr in zip(sh["shell"], prims):
        a = sh["shell"][name]
        on = np.isin(a["pl"], list(buf.arc_of))
        for i in np.nonzero(on)[0][:200]:
            cx, cy, side = buf.arc_of[int(a["pl"][i])]
            p = a["pos"][i]
            r = np.array([p[0] - cx, p[1] - cy]) * side
            n = pr.normals[i]
            assert abs(n[2]) < 1e-9
            assert np.dot(n[:2], r / np.linalg.norm(r)) > 0.9999
            seen += 1
    assert seen
    # the glass follows the curve: a chord of an arc carries glazing
    assert arc_of([{"center": [0.0, 0.0], "radius_m": 10.0, "start_deg": 0.0,
                    "sweep_deg": 90.0}], (10000, 0), (9980, 628), (0.9995, 0.0314))
    assert arc_of([{"center": [0.0, 0.0], "radius_m": 10.0, "start_deg": 0.0,
                    "sweep_deg": 90.0}], (10000, 0), (0, 10000), (0.7, 0.7)) is None


def test_small_city_passes_the_fit_checks():
    """The small test city: no clash; every roof item, dunnage frame and column resting on
    something; no step where a road meets its junction (#89: a road's side that runs along
    a junction past its cut, M17's shared pavement at a fork, left one)."""
    import json
    rep = small_assets_report()
    assert rep["fit"]["clashes"] == 0, rep["fit"]
    f = small_assets() / "assets" / "fit_report.json"
    g, c = json.loads(f.read_text(encoding="utf-8"))["checks"]
    assert c["ok"]
    bad = {k: v for k, v in g["by_kind"].items() if k.startswith(("roof.", "street."))}
    assert not bad, bad
    assert g["seams"]["legs"] > 1000 and g["seams"]["steps"] == 0, g["seams"]["worst"]
    assert g["ok"] and rep["fit"]["ok"] and rep["ok"]
