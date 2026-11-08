"""Sidewalks, crosswalks and junctions, drawn from M22's pavement map (AG17, `pave.py`).

- **Sidewalks**: a road side's bands of the map (its curb band in the district's curb stone,
  its furniture zone and clear path in its paving family), their curb face down to the
  carriageway and their back face down to the ground (on a raised road its fascia), tree
  pits (grates) under the street trees, and the curb dropped to 2 cm (a curb ramp, `pave`'s
  `drop`) beside a crosswalk's end or a garage, loading or gate entrance. On a raised road
  the piece also writes the walkways' lines put on its deck (an M15 open item: the model's
  sidewalks and walkways are at z 0 there).
- **Crosswalks**: zebra or ladder paint by the district's era on the faces that hold it, at
  their heights, tactile paving on the curb ramps at both ends.
- **Junctions**: the junction's faces of the map (its carriageway, corner pads and a
  cul-de-sac's bulb; a cluster's whole surface), their curb faces down to the carriageway,
  their outer walls, a raised junction's slab under them (no girder runs under it: its
  roads' end on its ports), and the barriers it carries between its legs
  (`barriers.junction_plan`).
"""

from __future__ import annotations

import math

from .. import canon as C
from . import materials as MT
from . import pave as PV
from .ctx import Ctx, bbox_center, dump
from .kit import Mesh, ccw
from .path import Path, dist, unit
from .pieces import Out, Piece, maker
from .roads import DECK_D, PEDESTRIAN, RANK, ROAD_DZ, Road, deck_kind, raised, street_class

DROP_Z = 0.02
RAMP_M = 1.2
PIT_M = 1.2
XWALK_DZ = 0.006        # crosswalk paint over the faces
TACTILE_DZ = 0.004
DECAL_STEP_M = 2.0      # a mark draped on its faces row by row at most this far apart


def _road_inputs(cx: Ctx, s) -> dict:
    seg = dump(s)
    seg.pop("district_ids", None)
    out = {"seg": seg, "cls": street_class(s), "ends": [], "crossings": [], "lanes": [],
           "start": s.start, "end": s.end, "origin": [0.0, 0.0],
           "cuts": list(cx.cuts.get(s.id, (0.0, 0.0)))}
    if "ground" not in seg and not cx.ground.flat:
        out["ground_pts"] = cx.ground.samples(s.centerline)
    return out


def _district(cx: Ctx, s) -> str | None:
    return s.district_ids[0] if s.district_ids else s.attrs.get("district")


def drape(mesh: Mesh, slot: str, o, u, v, x0: float, x1: float, y0: float, y1: float,
          zf, dz: float, step: float = DECAL_STEP_M) -> None:
    """A rectangle (x0..x1 along u, y0..y1 along v from o, meters) lying on a surface
    (`zf(x, y)`) dz over it, in rows at most `step` apart both ways."""
    nx = max(1, int(math.ceil((x1 - x0) / step - 1e-9)))
    ny = max(1, int(math.ceil((y1 - y0) / step - 1e-9)))
    rows, uvs = [], []
    for i in range(nx + 1):
        a = x0 + (x1 - x0) * i / nx
        row, uvr = [], []
        for k in range(ny + 1):
            b = y0 + (y1 - y0) * k / ny
            x = o[0] + u[0] * a + v[0] * b
            y = o[1] + u[1] * a + v[1] * b
            row.append((x, y, zf(x, y) + dz))
            uvr.append((a, b))
        rows.append(row)
        uvs.append(uvr)
    # (rows along u, columns along v: counterclockwise from above where v is u's left)
    flip = u[0] * v[1] - u[1] * v[0] < 0
    mesh.grid(slot, rows, uvs, flip=flip, expect=(0.0, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Sidewalks
# ---------------------------------------------------------------------------

def sidewalk_face_ids(cx: Ctx, w) -> list[str]:
    """The faces of the map a sidewalk piece draws: its road's bands on its side."""
    sd = w.side[0]
    return [f for f in cx.pave.faces_of(w.segment_id) if PV.side_of(cx.pave.F[f].band) == sd]


def gather_sidewalk(cx: Ctx, w) -> Piece:
    s = cx.seg[w.segment_id]
    try:
        P = Path(w.line)
    except ValueError:
        P = None
    trees = []
    if P is not None:
        xs = [p[0] for p in w.line]
        ys = [p[1] for p in w.line]
        pad = w.width_m
        for pl in cx.trees.near(min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad):
            ss, t = P.project(pl.position[0], pl.position[1])
            if 0.5 <= ss <= P.L - 0.5 and abs(t) <= w.width_m / 2.0:
                trees.append([C.m(ss), C.m(t), pl.id])
    road = _road_inputs(cx, s)
    inputs = {"walk": dump(w), "road": road, "style": cx.style(_district(cx, s)),
              "trees": sorted(trees), "origin": list(bbox_center(w.line))}
    if cx.pave.on:
        inputs["faces"] = [cx.pave.face_input(f) for f in sidewalk_face_ids(cx, w)]
    emb = sorted((st for st in cx.m.structures if st.kind == "embankment" and
                  (st.attrs or {}).get("road_id") == s.id), key=lambda st: st.id)
    if emb:
        inputs["embankments"] = [[st.attrs["s0_m"], st.attrs["s1_m"]] for st in emb]
    if raised(road["seg"]):
        inputs["walkways"] = [{"id": k.id, "line": [list(p) for p in k.line]}
                              for k in sorted(cx.walkways_of.get(w.id, ()), key=lambda k: k.id)]
    return Piece(w.id, "street.sidewalk", "sidewalk", cx.tile_for(w.id, w.line),
                 cx.keys.get(w.id, []), inputs)


@maker("sidewalk", 2)
def make_sidewalk(inp: dict) -> Out:
    w = inp["walk"]
    try:
        rd = Road(inp["road"])
    except ValueError:
        return Out(empty="degenerate road")
    faces = inp.get("faces") or []
    if not faces:
        return Out(empty="inside its junctions")
    style = inp["style"]
    mesh = Mesh(inp["origin"])
    curb_slot = MT.curb(style["archetype"])
    pave = MT.paving(style["archetype"])
    dk = deck_kind(rd.seg)
    rd_s0 = max(rd.s0, 0.0)
    embs = [(max(a, rd_s0), min(b, rd.s1)) for a, b in inp.get("embankments", ())
            if min(b, rd.s1) - max(a, rd_s0) >= 0.5]
    bottom, out_slot = PV.bottoms(dk, rd.path, embs)
    surf = PV.Surface()

    def uv(x, y):
        return rd.path.project(x, y)
    specs: list = []
    for fi in faces:
        slot = curb_slot if fi["band"].startswith("cr") else pave
        for t in PV.draw(mesh, fi, slot, uv):
            surf.add(t)
        PV.walls(mesh, fi, out_slot or pave, bottom, curb_slot=curb_slot, out=specs)
    PV.draw_walls(mesh, specs)
    # tree pits, on the sidewalk as drawn
    try:
        P = Path(w["line"])
    except ValueError:
        P = None
    width = w["width_m"]
    for ts, tt, _ in inp["trees"] if P is not None else ():
        tt = max(min(tt, width / 2.0 - PIT_M / 2.0 - 0.2), -width / 2.0 + PIT_M / 2.0 + 0.2) \
            if width > PIT_M + 0.4 else 0.0
        hp = PIT_M / 2.0
        x, y, nx, ny, _ = P.frame(ts)
        tx, ty = P.tangent(ts)
        o = (x + nx * tt, y + ny * tt)
        if surf.z(o[0], o[1]) is None:
            continue
        drape(mesh, "grate", o, (tx, ty), (nx, ny), -hp, hp, -hp, hp,
              lambda a, b: surf.z(a, b, 0.0), 0.003)
    out = Out(mesh=mesh)
    if inp.get("walkways"):
        out.notes["walkways"] = {k["id"]: _on_surface(rd, surf, k["line"])
                                 for k in inp["walkways"]}
    return out


def _on_surface(rd: Road, surf: PV.Surface, line) -> list:
    """A walkway's line put on the sidewalk as drawn (z over the ground, as the model's)."""
    out = []
    for p in line:
        z = surf.z(p[0], p[1])
        s, _ = rd.path.project(p[0], p[1])
        if z is None:
            z = rd.z(s) + PV.CURB_MM / 1000.0
        out.append([p[0], p[1], C.m(z - rd.ground(s))])
    return out


# ---------------------------------------------------------------------------
# Crosswalks
# ---------------------------------------------------------------------------

def _xwalk_faces(cx: Ctx, c) -> list[str]:
    """The faces that hold a crosswalk and its ends: its road's and its junction's within
    2 m of its rectangle."""
    a, b = c.line[0], c.line[-1]
    r = c.width_m / 2.0 + 2.0
    x0, x1 = min(a[0], b[0]) - r, max(a[0], b[0]) + r
    y0, y1 = min(a[1], b[1]) - r, max(a[1], b[1]) + r
    PI = cx.pave
    owners = [c.segment_id]
    if c.junction_id:
        owners.append(c.junction_id)
    out = []
    for o in owners:
        for f in PI.faces_of(o):
            vs = [PI.V[v] for rg in PI.rings(f) for v in rg]
            if max(p[0] for p in vs) < x0 * 1000 or min(p[0] for p in vs) > x1 * 1000 or \
                    max(p[1] for p in vs) < y0 * 1000 or min(p[1] for p in vs) > y1 * 1000:
                continue
            out.append(f)
    return out


def gather_crosswalk(cx: Ctx, c) -> Piece:
    s = cx.seg.get(c.segment_id)
    road = _road_inputs(cx, s) if s is not None else None
    did = _district(cx, s) if s is not None else None
    inputs = {"cross": dump(c), "road": road, "style": cx.style(did),
              "origin": list(bbox_center(c.line))}
    if cx.pave.on and len(c.line) >= 2:
        inputs["faces"] = [cx.pave.face_input(f) for f in _xwalk_faces(cx, c)]
    return Piece(c.id, "street.crosswalk", "crosswalk", cx.tile_for(c.id, c.line),
                 cx.keys.get(c.id, []), inputs)


@maker("crosswalk", 2)
def make_crosswalk(inp: dict) -> Out:
    c = inp["cross"]
    a, b = c["line"][0], c["line"][-1]
    L = dist(a, b)
    if L < 0.5 or inp["road"] is None:
        return Out(empty="degenerate line")
    try:
        rd = Road(inp["road"])
    except ValueError:
        return Out(empty="degenerate road")
    surf = PV.Surface()
    for fi in inp.get("faces", ()):
        P_, tris = PV.triangles(fi)
        for t in tris:
            surf.add((P_[t[0]], P_[t[1]], P_[t[2]]))
    mesh = Mesh(inp["origin"])
    ux, uy = unit(b[0] - a[0], b[1] - a[1])
    dx, dy = -uy, ux

    def zf(x, y):
        z = surf.z(x, y) if surf else None
        if z is None:
            z = rd.z(rd.path.project(x, y)[0])
        return z
    style = inp["style"]
    wid = c["width_m"]
    hw = wid / 2.0
    o, u, v = (a[0], a[1]), (ux, uy), (dx, dy)
    if style["era"] in MT.LADDER_ERAS:
        for y0 in (hw - 0.3, -hw):
            drape(mesh, "marking.white", o, u, v, 0.1, L - 0.1, y0, y0 + 0.3, zf, XWALK_DZ)
        x = 0.35
        while x + 0.45 <= L - 0.3:
            drape(mesh, "marking.white", o, u, v, x, x + 0.45, -hw + 0.3, hw - 0.3, zf,
                  XWALK_DZ)
            x += 0.9
    else:
        x = 0.3
        while x + 0.5 <= L - 0.25:
            drape(mesh, "marking.white", o, u, v, x, x + 0.5, -hw, hw, zf, XWALK_DZ)
            x += 1.0
    seg = inp["road"]["seg"]
    side = seg["cross_section"]["sidewalk_m"][0]
    if inp["road"]["cls"] in ("avenue", "street") and side > 0.9:
        depth = min(0.6, side - 0.3)
        for x0, x1 in ((-0.2 - depth, -0.2), (L + 0.2, L + 0.2 + depth)):
            drape(mesh, "tactile", o, u, v, x0, x1, -hw + 0.3, hw - 0.3, zf, TACTILE_DZ)
    if not mesh.triangles:
        return Out(empty="no room for its marks")
    return Out(mesh=mesh)


# ---------------------------------------------------------------------------
# Junctions
# ---------------------------------------------------------------------------

def _top_class(cx: Ctx, j) -> str:
    legs = cx.legs_of(j)
    if not legs:
        nodes = cx.nodes_of(j)
        legs = [(s, True) for n in nodes for s in cx.seg_at_node.get(n, ())]
    return max((street_class(s) for s, _ in legs), key=lambda c: RANK.get(c, 0),
               default="street")


def gather_junction(cx: Ctx, j) -> Piece:
    ext = j.polygon.exterior
    cxy = bbox_center(ext)
    did = cx.district_of_point(*cxy)
    top = _top_class(cx, j)
    legs = cx.legs_of(j)
    D = max((DECK_D.get(street_class(s), 1.2) for s, _ in legs), default=1.2)
    inputs = {"junction": {"id": j.id, "level": j.level, "shape": j.shape},
              "style": cx.style(did), "origin": list(cxy), "top": top, "deck_d": D}
    if cx.pave.on:
        inputs["faces"] = [cx.pave.face_input(f) for f in cx.pave.faces_of(j.id)]
    if j.level:
        # M14 (AG10): a deck's junction lies on its slab; where it reaches past it (at a
        # ramp's top) a slab of its own carries it
        inputs["off_deck"] = _off_deck(cx, j)
    # (#95, AG17: the barriers it carries between its legs, `barriers.junction_plan`)
    from . import barriers as BR
    plan = BR.junction_plan(cx, j)
    if plan["corners"] or plan["median"]:
        inputs["barriers"] = {"corners": [{"kind": c["kind"], "pts": c["pts"],
                                           "ends": c["ends"]} for c in plan["corners"]],
                              "median": plan["median"]}
    return Piece(j.id, "street.junction", "junction", cx.tile_for(j.id, ext),
                 cx.keys.get(j.id, []), inputs)


def _off_deck(cx: Ctx, j) -> list:
    """The parts of a deck's junction outside its deck's slab (over 0.5 m2), as rings."""
    from citygen import geom as G

    from .decks import _rings, deck_of
    dk = None
    for s, _ in cx.legs_of(j):
        did = s.attrs.get("deck")
        if did:
            dk = next((d for d in cx.m.decks if d.id == did), None)
            break
    if dk is None:
        return []
    D = deck_of(cx, dk)
    with G.canonical():
        rest = G.diff(G.from_model_poly(j.polygon), D.poly)
        out = []
        for p in G.parts(rest):
            if G.area1(p) >= 0.5:
                e, hs = _rings(p)
                out.append([[list(q) for q in e], [[list(q) for q in h] for h in hs]])
    return out


@maker("junction", 4)
def make_junction(inp: dict) -> Out:
    faces = inp.get("faces") or []
    if not faces:
        return Out(empty="no faces")
    j = inp["junction"]
    style = inp["style"]
    mesh = Mesh(inp["origin"])
    top = inp["top"]
    slot = {"highway": "asphalt.highway", "avenue": "asphalt.avenue"}.get(
        top, "asphalt.alley" if top in ("alley", "service") else "asphalt.street")
    if top in PEDESTRIAN:
        slot = MT.paving(style["archetype"])
    pave = MT.paving(style["archetype"])
    curb = MT.curb(style["archetype"])
    D = inp.get("deck_d", 1.2)
    up = not j.get("level") and any(PV.is_raised(fi) for fi in faces)
    if j.get("level"):
        def bottom(v):
            return v[3]         # (down to its deck's slab top)
    elif up:
        def bottom(v):
            # (a raised junction's slab D deep, down to the ground where it is lower)
            return max(v[3] - int(D * 1000), v[3] - v[4] - 100)
    else:
        bottom = PV.ground_bottom
    surf = PV.Surface()
    pads = 0
    specs: list = []
    for fi in faces:
        sl = slot if fi["cls"] == "top" else pave
        tris = PV.draw(mesh, fi, sl)
        for t in tris:
            surf.add(t)
        if fi["kind"] == "corner" and tris:
            pads += 1
        out_slot = "concrete.deck" if up else (sl if fi["cls"] == "top" else pave)
        PV.walls(mesh, fi, out_slot, bottom, curb_slot=curb, out=specs)
        if up and tris:
            # (the slab's underside, under the face: no girder runs under a junction)
            low = []
            for p, q, r in tris:
                low.append(tuple((x, y, _slab_z(fi, x, y, z, bottom)) for x, y, z in (p, r, q)))
            pts, idx = [], []
            at: dict = {}
            for t in low:
                for pnt in t:
                    if pnt not in at:
                        at[pnt] = len(pts)
                        pts.append(pnt)
                idx.append(tuple(at[pnt] for pnt in t))
            mesh.tris_mm("concrete.deck", pts, idx,
                         [(p[0] / 1000.0, p[1] / 1000.0) for p in pts], expect=(0, 0, -1))
    PV.draw_walls(mesh, specs)
    if j.get("level"):
        for r_, hs_ in inp.get("off_deck", ()):
            zn = min(p[3] for fi in faces for r in fi["rings"] for p in r) / 1000.0
            mesh.prism("concrete.deck", ccw(r_), zn - 1.2, zn - 0.01,
                       top=False, bottom=True, holes=[ccw(h)[::-1] for h in hs_])
    if inp.get("barriers"):
        _junction_barriers(mesh, inp["barriers"], surf)
    out = Out(mesh=mesh)
    out.notes["corner_pads"] = [pads, 0]
    return out


def _slab_z(fi: dict, x: int, y: int, z: int, bottom) -> int:
    """A raised junction's slab under a point of its face (millimeters): its boundary
    vertices' bottoms; an interior point the face's height less the slab's depth at the
    nearest boundary vertex."""
    best = None
    for r in fi["rings"]:
        for p in r:
            if p[0] == x and p[1] == y:
                return bottom(p)
            d = (p[0] - x) ** 2 + (p[1] - y) ** 2
            if best is None or d < best[0]:
                best = (d, p)
    p = best[1]
    return z - (p[2] - bottom(p))


def _junction_barriers(mesh: Mesh, plan: dict, surf: PV.Surface):
    """#95, AG17: what a junction carries between its legs (`barriers.junction_plan`): a
    parapet along a raised junction's edge between two legs, a guard wall along an
    at-grade highway corner, a median barrier across; each on its legs' port lines."""
    from . import barriers as BR
    parapet = BR.parapet_profile(0.0, "r")
    guard = BR.shifted(BR.JERSEY, BR.GUARD_IN_M)
    for c in plan.get("corners", ()):
        pts = [[p[0] / 1000.0, p[1] / 1000.0, p[2] / 1000.0] for p in c["pts"]]
        BR.draw_chain(mesh, "concrete.barrier", pts,
                      parapet if c["kind"] == "parapet" else guard,
                      ends=tuple(c["ends"]))
    med = plan.get("median")
    if med:
        pts = [[x, y, surf.z(x, y, 0.0)] for x, y in med["pts"]]
        BR.draw_chain(mesh, "concrete.barrier", pts, BR.JERSEY, ends=tuple(med["ends"]))
