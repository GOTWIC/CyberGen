"""Sidewalks, crosswalks and junctions.

- **Sidewalks**: the slab in the district's paving family, a curb stone strip along the
  road, the curb face down to the asphalt, a back face to the ground, tree pits (grates)
  under the street trees, and the curb dropped to 2 cm (a 1.2 m ramp) where a crosswalk or a
  garage, loading or gate entrance meets it. Heights follow the road's profile, so on a
  raised road the sidewalk stays on its deck (an M15 open item: the model's sidewalks and
  walkways are at z 0 there; the piece also writes the walkways' corrected lines).
- **Crosswalks**: zebra or ladder paint by the district's era, tactile paving at both
  curbs, on the dropped curb.
- **Junctions**: the carriageway polygon at its node's height, or (M18) through the model's
  surface where it carries one (`edge_z`; else blended toward each leg's height at its
  cut-back where they differ), the sidewalk corners between neighboring legs
  (the curb return from the junction polygon, the property-line fillet rebuilt as M2 builds
  it), their curb faces, and a deck slab under a raised junction.
"""

from __future__ import annotations

import math

from citygen import dmath as M

from .. import canon as C
from . import materials as MT
from .ctx import Ctx, bbox_center, dump
from .kit import Mesh, ccw
from .kit import check as mesh_check
from .path import Path, Profile, dist, first_exit, unit
from .pieces import Out, Piece, maker
from .roads import DECK_D, PEDESTRIAN, RANK, ROAD_DZ, Road, raised, street_class, \
    walkway_fix

DROP_Z = 0.02
RAMP_M = 1.2
CURB_STONE_M = 0.18
PIT_M = 1.2


def _road_inputs(cx: Ctx, s) -> dict:
    seg = dump(s)
    seg.pop("district_ids", None)
    out = {"seg": seg, "cls": street_class(s), "ends": [], "crossings": [], "lanes": [],
           "start": s.start, "end": s.end, "origin": [0.0, 0.0]}
    if "ground" not in seg and not cx.ground.flat:
        out["ground_pts"] = cx.ground.samples(s.centerline)
    return out


def _district(cx: Ctx, s) -> str | None:
    return s.district_ids[0] if s.district_ids else s.attrs.get("district")


# ---------------------------------------------------------------------------
# Sidewalks
# ---------------------------------------------------------------------------

def gather_sidewalk(cx: Ctx, w) -> Piece:
    s = cx.seg[w.segment_id]
    try:
        P = Path(w.line)
    except ValueError:
        P = None
    drops = []
    trees = []
    if P is not None:
        sgn = 1.0 if w.side == "left" else -1.0
        for c in sorted(cx.cross_on.get(s.id, ()), key=lambda c: c.id):
            for p in (c.line[0], c.line[-1]):
                ss, t = P.project(p[0], p[1])
                # the crosswalk's end on this sidewalk's curb line
                if abs(t + sgn * w.width_m / 2.0) < 1.5 and -1.0 <= ss <= P.L + 1.0:
                    drops.append([C.m(ss - c.width_m / 2.0), C.m(ss + c.width_m / 2.0),
                                  "crosswalk", c.id])
        for owner, e in sorted(cx.doors_on.get(s.id, ()), key=lambda d: (d[0], d[1].kind)):
            pos = e.position
            ss, t = P.project(pos[0], pos[1])
            if 0.0 <= ss <= P.L and sgn * t >= w.width_m / 2.0 - 0.5 and \
                    sgn * t <= w.width_m / 2.0 + 8.0:
                half = 3.0 if e.kind == "garage" else 2.5
                drops.append([C.m(ss - half), C.m(ss + half), e.kind, owner])
        xs = [p[0] for p in w.line]
        ys = [p[1] for p in w.line]
        pad = w.width_m
        for pl in cx.trees.near(min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad):
            ss, t = P.project(pl.position[0], pl.position[1])
            if 0.5 <= ss <= P.L - 0.5 and abs(t) <= w.width_m / 2.0:
                trees.append([C.m(ss), C.m(t), pl.id])
    road = _road_inputs(cx, s)
    inputs = {"walk": dump(w), "road": road, "style": cx.style(_district(cx, s)),
              "drops": sorted(drops), "trees": sorted(trees),
              "origin": list(bbox_center(w.line))}
    if raised(road["seg"]):
        inputs["walkways"] = [{"id": k.id, "line": [list(p) for p in k.line]}
                              for k in sorted(cx.walkways_of.get(w.id, ()), key=lambda k: k.id)]
    return Piece(w.id, "street.sidewalk", "sidewalk", cx.tile_for(w.id, w.line),
                 cx.keys.get(w.id, []), inputs)


def _drop_f(s: float, drops) -> float:
    f = 0.0
    for a, b, *_ in drops:
        if a <= s <= b:
            return 1.0
        if a - 1.0 < s < a:
            f = max(f, 1.0 - (a - s))
        elif b < s < b + 1.0:
            f = max(f, 1.0 - (s - b))
    return f


@maker("sidewalk", 1)
def make_sidewalk(inp: dict) -> Out:
    w = inp["walk"]
    try:
        P = Path(w["line"])
        rd = Road(inp["road"])
    except ValueError:
        return Out(empty="degenerate line")
    style = inp["style"]
    mesh = Mesh(inp["origin"])
    curb_h = w.get("curb_m", 0.15) or 0.15
    width = w["width_m"]
    sgn = 1.0 if w["side"] == "left" else -1.0
    t_curb = -sgn * width / 2.0
    drops = inp["drops"]
    extra = []
    for a, b, *_ in drops:
        extra += [a - 1.0, a, b, b + 1.0]
    offs = [0.0, CURB_STONE_M] + ([RAMP_M] if width > RAMP_M + 0.3 else []) + [width]
    curb_slot = MT.curb(style["archetype"])
    pave = MT.paving(style["archetype"])
    st = P.stations(0.0, P.L, 5.0, extra)
    rows, uvs, zs, hs, nrm = [], [], [], [], []
    for s, vi in st:
        x, y, nx, ny, k = P.frame(s, vi)
        rs, _ = rd.path.project(x, y)
        z = rd.z(rs)
        f = _drop_f(s, drops)
        hc = curb_h - f * (curb_h - DROP_Z)
        row = []
        for o in offs:
            t = t_curb + sgn * o
            h = hc if o <= CURB_STONE_M else curb_h
            row.append((x + nx * k * t, y + ny * k * t, z + h))
        rows.append(row)
        uvs.append([(s, t_curb + sgn * o) for o in offs])
        zs.append(z)
        hs.append(hc)
        nrm.append((nx, ny))
    flip = sgn < 0
    up = (0.0, 0.0, 1.0)
    mesh.grid(curb_slot, [r[:2] for r in rows], [u[:2] for u in uvs], flip=flip, expect=up)
    mesh.grid(pave, [r[1:] for r in rows], [u[1:] for u in uvs], flip=flip, expect=up)
    # curb face (toward the road) and back face (toward the lot)
    face, back, fuv, buv = [], [], [], []
    for (s, vi), row, z in zip(st, rows, zs):
        c = row[0]
        b = row[-1]
        bot = (c[0], c[1], z)
        # the back face down to the lot's ground, or on a deck down to the deck
        g = rd.ground(rd.path.project(b[0], b[1])[0])
        gnd = (b[0], b[1], g - 0.02 if z - g < 0.5 else z - ROAD_DZ)
        if sgn > 0:
            face.append([bot, c])
            back.append([b, gnd])
            fuv.append([(s, 0.0), (s, c[2] - z)])
            buv.append([(s, b[2]), (s, gnd[2])])
        else:
            face.append([c, bot])
            back.append([gnd, b])
            fuv.append([(s, c[2] - z), (s, 0.0)])
            buv.append([(s, gnd[2]), (s, b[2])])
    mesh.grid(curb_slot, face, fuv, expect=[(-sgn * a, -sgn * b, 0.0) for a, b in nrm])
    mesh.grid(pave, back, buv, expect=[(sgn * a, sgn * b, 0.0) for a, b in nrm])
    # tree pits
    for ts, tt, _ in inp["trees"]:
        tt = max(min(tt, width / 2.0 - PIT_M / 2.0 - 0.2), -width / 2.0 + PIT_M / 2.0 + 0.2) \
            if width > PIT_M + 0.4 else 0.0
        hp = PIT_M / 2.0
        ring = [(ts - hp, tt - hp), (ts + hp, tt - hp), (ts + hp, tt + hp), (ts - hp, tt + hp)]

        def fmap(u, v):
            x, y, nx, ny, _ = P.frame(u)
            rs, _ = rd.path.project(x, y)
            return x + nx * v, y + ny * v, rd.z(rs) + curb_h + 0.003
        mesh.poly_map("grate", ring, (), fmap)
    out = Out(mesh=mesh)
    if inp.get("walkways"):
        out.notes["walkways"] = {k["id"]: walkway_fix(rd, k["line"], curb_h)
                                 for k in inp["walkways"]}
    return out


# ---------------------------------------------------------------------------
# Crosswalks
# ---------------------------------------------------------------------------

def gather_crosswalk(cx: Ctx, c) -> Piece:
    s = cx.seg.get(c.segment_id)
    road = _road_inputs(cx, s) if s is not None else None
    did = _district(cx, s) if s is not None else None
    inputs = {"cross": dump(c), "road": road, "style": cx.style(did),
              "origin": list(bbox_center(c.line))}
    return Piece(c.id, "street.crosswalk", "crosswalk", cx.tile_for(c.id, c.line),
                 cx.keys.get(c.id, []), inputs)


@maker("crosswalk", 1)
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
    mesh = Mesh(inp["origin"])
    ux, uy = unit(b[0] - a[0], b[1] - a[1])
    dx, dy = -uy, ux
    wid = c["width_m"]

    def fmap(x_, y_, dz=0.006):
        px, py = a[0] + ux * x_ + dx * y_, a[1] + uy * x_ + dy * y_
        rs, _ = rd.path.project(px, py)
        return px, py, rd.z(rs) + dz

    style = inp["style"]
    hw = wid / 2.0
    if style["era"] in MT.LADDER_ERAS:
        for y0 in (hw - 0.3, -hw):
            mesh.poly_map("marking.white", [(0.1, y0), (L - 0.1, y0), (L - 0.1, y0 + 0.3),
                                            (0.1, y0 + 0.3)], (), fmap)
        x = 0.35
        while x + 0.45 <= L - 0.3:
            mesh.poly_map("marking.white", [(x, -hw + 0.3), (x + 0.45, -hw + 0.3),
                                            (x + 0.45, hw - 0.3), (x, hw - 0.3)], (), fmap)
            x += 0.9
    else:
        x = 0.3
        while x + 0.5 <= L - 0.25:
            mesh.poly_map("marking.white", [(x, -hw), (x + 0.5, -hw), (x + 0.5, hw),
                                            (x, hw)], (), fmap)
            x += 1.0
    seg = inp["road"]["seg"]
    side = seg["cross_section"]["sidewalk_m"][0]
    curb_h = seg["cross_section"].get("curb_m", 0.15) or 0.15
    if inp["road"]["cls"] in ("avenue", "street") and side > 0.9:
        depth = min(0.6, side - 0.3)

        def ramp(o):
            return DROP_Z + (curb_h - DROP_Z) * min(o / RAMP_M, 1.0) + 0.004
        for x0, x1, o0 in ((-0.2 - depth, -0.2, 0.2 + depth), (L + 0.2, L + 0.2 + depth, 0.2)):
            def tmap(x_, y_, x0=x0):
                o = (-x_) if x0 < 0 else (x_ - L)
                return fmap(x_, y_, ramp(o))
            mesh.poly_map("tactile", [(x0, -hw + 0.3), (x1, -hw + 0.3), (x1, hw - 0.3),
                                      (x0, hw - 0.3)], (), tmap)
    return Out(mesh=mesh)


# ---------------------------------------------------------------------------
# Junctions
# ---------------------------------------------------------------------------

def gather_junction(cx: Ctx, j) -> Piece:
    node = cx.node.get(j.node_id)
    legs = []
    for s in sorted(cx.seg_at_node.get(j.node_id, ()), key=lambda s: s.id):
        for at_start in ((True, False) if s.start == s.end else (s.start == j.node_id,)):
            leg = {"id": s.id, "at_start": at_start, "line": [list(p) for p in s.centerline],
                   "z_profile": [z.model_dump() for z in s.z_profile],
                   "width": s.width_m, "side": s.cross_section.sidewalk_m[0],
                   "cls": street_class(s)}
            g = getattr(s, "ground", None)
            if g:
                leg["ground"] = [z.model_dump() for z in g]
            elif not cx.ground.flat:
                leg["ground_pts"] = cx.ground.samples(s.centerline)
            legs.append(leg)
    ext = j.polygon.exterior
    cxy = bbox_center(ext)
    did = cx.district_of_point(*cxy)
    inputs = {"junction": dump(j), "node": list(node.position) if node else [*cxy, 0.0],
              "node_ground": getattr(node, "ground_m", None) or 0.0,
              "legs": legs, "style": cx.style(did), "origin": list(cxy)}
    if j.level:
        # M14 (AG10): a deck's junction lies on its slab; where it reaches past it (at a
        # ramp's top) a slab of its own carries it
        inputs["off_deck"] = _off_deck(cx, j)
    return Piece(j.id, "street.junction", "junction", cx.tile_for(j.id, ext),
                 cx.keys.get(j.id, []), inputs)


def _off_deck(cx: Ctx, j) -> list:
    """The parts of a deck's junction outside its deck's slab (over 0.5 m2), as rings."""
    from citygen import geom as G

    from .decks import _rings, deck_of
    dk = None
    for s in cx.seg_at_node.get(j.node_id, ()):
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


def _valid_parts(ring, holes) -> list:
    import shapely
    from shapely.geometry import Polygon

    from citygen import geom as G
    with G.canonical():
        g = G.qpoly(shapely.make_valid(Polygon(ring, holes)))
        parts = G.parts(g)
    out = []
    for p in parts:
        ext = ccw(list(p.exterior.coords)[:-1])
        hs = [ccw(list(h.coords)[:-1])[::-1] for h in p.interiors]
        out.append((ext, hs))
    out.sort(key=lambda r: (min(r[0]), len(r[0])))
    return out


def _leg_dir(pts, P) -> tuple[float, float]:
    """M2's leg direction: from the node to the point min(10 m, half the leg) along it."""
    path = Path(pts)
    q = path.point(min(10.0, path.L / 2.0))
    return unit(q[0] - P[0], q[1] - P[1])


def _corner(P, da, db, ha: float, hb: float, r: float, La: float, Lb: float):
    """As citygen's `junctions._corner`: the fillet between leg a's left edge (offset ha)
    and leg b's right edge (offset hb), b counterclockwise from a. (ta, tb, Ta, Tb, O) or
    None when the edges do not converge."""
    na, nb = (-da[1], da[0]), (-db[1], db[0])
    sinp = da[0] * db[1] - da[1] * db[0]
    cosp = da[0] * db[0] + da[1] * db[1]
    gap = M.degrees(M.atan2(sinp, cosp)) % 360.0
    if gap >= 178.0 or gap <= 0.5:
        return None
    rx = -hb * nb[0] - ha * na[0]
    ry = -hb * nb[1] - ha * na[1]
    det = da[0] * (-db[1]) - da[1] * (-db[0])
    t1 = (rx * (-db[1]) - ry * (-db[0])) / det
    t2 = (da[0] * ry - da[1] * rx) / det
    tl = r * (1.0 + cosp) / sinp
    ta = max(t1 + tl, 0.0)
    tb = max(t2 + tl, 0.0)
    ra = min(0.45 * La, 60.0)
    rb = min(0.45 * Lb, 60.0)
    if ta > ra or tb > rb:
        if t1 <= ra and t2 <= rb:
            X = (P[0] + ha * na[0] + t1 * da[0], P[1] + ha * na[1] + t1 * da[1])
            return max(t1, 0.0), max(t2, 0.0), X, X, None
        return None
    Ta = (P[0] + ha * na[0] + ta * da[0], P[1] + ha * na[1] + ta * da[1])
    Tb = (P[0] - hb * nb[0] + tb * db[0], P[1] - hb * nb[1] + tb * db[1])
    O = (Ta[0] + r * na[0], Ta[1] + r * na[1])
    return ta, tb, Ta, Tb, O


def _meet(P, da, db, ha: float, hb: float):
    """Where leg a's left edge (offset ha) meets leg b's right edge (offset hb)."""
    na, nb = (-da[1], da[0]), (-db[1], db[0])
    det = da[0] * (-db[1]) - da[1] * (-db[0])
    if abs(det) < 1e-9:
        return None
    rx = -hb * nb[0] - ha * na[0]
    ry = -hb * nb[1] - ha * na[1]
    t1 = (rx * (-db[1]) - ry * (-db[0])) / det
    return (P[0] + ha * na[0] + t1 * da[0], P[1] + ha * na[1] + t1 * da[1])


def _arc(O, A, B, r: float) -> list:
    a0 = M.atan2(A[1] - O[1], A[0] - O[0])
    a1 = M.atan2(B[1] - O[1], B[0] - O[0])
    sweep = (a1 - a0) % (2 * M.PI)
    if sweep > M.PI:
        sweep -= 2 * M.PI
    n = max(2, int(abs(sweep) / M.radians(15.0)) + 1)
    return [(O[0] + r * M.cos(a0 + sweep * k / n), O[1] + r * M.sin(a0 + sweep * k / n))
            for k in range(1, n)]


def _simple(ring) -> bool:
    """No two edges of the ring cross or touch (exact, on millimeters)."""
    q = [(int(round(x * 1000)), int(round(y * 1000))) for x, y in ring]
    n = len(q)
    if n < 3:
        return False

    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def on(a, b, p):
        return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and \
            min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
    for i in range(n):
        a, b = q[i], q[(i + 1) % n]
        if a == b:
            return False
        for k in range(i + 1, n):
            if k == i or (k + 1) % n == i or k == (i + 1) % n:
                continue
            c, d = q[k], q[(k + 1) % n]
            o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
            if ((o1 > 0) != (o2 > 0)) and o1 != 0 and o2 != 0 and \
                    ((o3 > 0) != (o4 > 0)) and o3 != 0 and o4 != 0:
                return False
            if (o1 == 0 and on(a, b, c)) or (o2 == 0 and on(a, b, d)) or \
                    (o3 == 0 and on(c, d, a)) or (o4 == 0 and on(c, d, b)):
                return False
    return True


def _area(ring) -> float:
    s = 0.0
    for i in range(len(ring)):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % len(ring)]
        s += x0 * y1 - x1 * y0
    return s / 2.0


@maker("junction", 1)
def make_junction(inp: dict) -> Out:
    j = inp["junction"]
    ring = ccw(j["polygon"]["exterior"])
    # holes: M2 leaves only slivers (a ring touching the outline); a junction is paved through
    holes = [ccw(h)[::-1] for h in j["polygon"].get("holes", [])
             if abs(_area(h)) >= 4.0 and not any(tuple(p) in {tuple(q) for q in ring} for p in h)]
    P = (inp["node"][0], inp["node"][1])
    zn = inp["node"][2] + inp["node_ground"] + ROAD_DZ
    style = inp["style"]
    mesh = Mesh(inp["origin"])
    legs = []
    for lg in inp["legs"]:
        pts = lg["line"] if lg["at_start"] else lg["line"][::-1]
        try:
            path = Path(pts)
        except ValueError:
            continue
        zp = Profile.of(lg["z_profile"])
        if lg.get("ground"):
            gp = Profile.of(lg["ground"])
        elif lg.get("ground_pts"):
            g = lg["ground_pts"] if lg["at_start"] else lg["ground_pts"][::-1]
            gp = Profile(list(zip(Path(lg["line"]).cum, lg["ground_pts"])))
        else:
            gp = Profile([])
        Lr = path.L
        ex = first_exit(path.p, ring)
        cls = lg["cls"]
        side = 0.0 if cls in PEDESTRIAN else lg["side"]
        d = _leg_dir(path.p, P)
        rec = {"cls": cls, "d": d, "ang": M.atan2(d[1], d[0]), "L": Lr, "row": lg["width"] / 2.0,
               "side": side, "id": lg["id"], "exit": ex}
        if ex is not None:
            s = ex[0]
            sm = s if lg["at_start"] else Lr - s
            rec["z"] = gp(sm) + zp(sm) + ROAD_DZ
            a, b = ring[ex[1]], ring[(ex[1] + 1) % len(ring)]
            rec["mid"] = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        legs.append(rec)
    legs.sort(key=lambda r: (r["ang"], r["id"]))
    lz = [r for r in legs if "z" in r]
    flat = all(abs(r["z"] - zn) < 0.002 for r in lz)
    # M18: the model's surface where it carries one (`edge_z`, over the node's ground): every
    # vertex at its height, so the legs meet it with no step (AG14 draws the rest from it)
    ez = j.get("edge_z")
    if ez and len(ez) == len(j["polygon"]["exterior"]):
        vz = {(p[0], p[1]): inp["node_ground"] + z + ROAD_DZ
              for p, z in zip(j["polygon"]["exterior"], ez)}
        vpts = list(vz.items())
    else:
        vz = None

    def zfun(x, y):
        if vz is not None:
            z = vz.get((x, y))
            if z is not None:
                return z
            acc = wt = 0.0
            for (px, py), pz in vpts:
                w = 1.0 / ((x - px) ** 2 + (y - py) ** 2 + 1.0)
                acc += pz * w
                wt += w
            return acc / wt
        if flat:
            return zn
        w0 = 1.0 / ((x - P[0]) ** 2 + (y - P[1]) ** 2 + 4.0)
        acc, wt = zn * w0, w0
        for r in lz:
            w = 1.0 / ((x - r["mid"][0]) ** 2 + (y - r["mid"][1]) ** 2 + 4.0)
            acc += r["z"] * w
            wt += w
        return acc / wt
    top = max((r["cls"] for r in legs), key=lambda c: RANK.get(c, 0), default="street")
    slot = {"highway": "asphalt.highway", "avenue": "asphalt.avenue"}.get(
        top, "asphalt.alley" if top in ("alley", "service") else "asphalt.street")
    if top in PEDESTRIAN:
        slot = MT.paving(style["archetype"])
    ok = mesh.poly(slot, ring, holes, zfun=zfun)
    if not ok:
        # a ring that touches itself: its valid parts, in a fixed order
        ok = any([mesh.poly(slot, r, hs, zfun=zfun) for r, hs in _valid_parts(ring, holes)])
    if not ok:
        return Out(empty="untriangulable polygon")
    if j.get("level"):
        for r_, hs_ in inp.get("off_deck", ()):
            mesh.prism("concrete.deck", ccw(r_), zn - ROAD_DZ - 1.2, zn - ROAD_DZ - 0.01,
                       top=False, bottom=True, holes=[ccw(h)[::-1] for h in hs_])
    elif zn - inp["node_ground"] - ROAD_DZ > 0.5:
        D = max(DECK_D.get(r["cls"], 1.2) for r in legs) if legs else 1.2
        mesh.prism("concrete.deck", ring, zn - ROAD_DZ - D, zn - ROAD_DZ - 0.01, top=False,
                   bottom=True)
    pads = _corners(mesh, ring, holes, P, legs, j, style, zfun)
    out = Out(mesh=mesh)
    out.notes["corner_pads"] = pads
    return out


def _minus(sector, ring, holes, taken=()):
    """The sector polygon less the junction polygon and the corners already made, as
    counterclockwise rings (citygen's snapped overlay), or None."""
    import shapely
    from shapely.geometry import Polygon

    from citygen import geom as G
    try:
        with G.canonical():
            a = G.qpoly(shapely.make_valid(Polygon(sector)))
            b = G.qpoly(shapely.make_valid(Polygon(ring, holes)))
            if taken:
                b = G.union([b] + [Polygon(t) for t in taken])
            d = G.diff(a, b)
            parts = G.parts(d)
    except (shapely.errors.GEOSException, ValueError):
        return None
    out = []
    for p in parts:
        r = ccw(list(p.exterior.coords)[:-1])
        if len(r) >= 3 and not p.interiors:
            out.append(r)
    out.sort(key=lambda r: (min(r), len(r)))
    return out


def _near(p, line, closed: bool, tol: float = 0.03) -> bool:
    """Whether p is within tol of a polyline (or ring)."""
    n = len(line)
    for i in range(n if closed else n - 1):
        a, b = line[i], line[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        f = 0.0 if L2 == 0.0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy)
                                             / L2))
        ex, ey = p[0] - (a[0] + f * dx), p[1] - (a[1] + f * dy)
        if ex * ex + ey * ey <= tol * tol:
            return True
    return False


def _corners(mesh: Mesh, ring, holes, P, legs, j, style, zfun) -> list:
    """Sidewalk corners between neighboring legs; [made, skipped, why skipped]."""
    made = skipped = 0
    n = len(legs)
    if n < 2 or j.get("shape") == "cul_de_sac":
        return [0, 0, {}]
    why: dict[str, int] = {}
    taken: list = []          # earlier corners: a later one never overlaps them
    drawn: list = []
    pave = MT.paving(style["archetype"])
    curb_slot = MT.curb(style["archetype"])
    r_all = j.get("corner_radius_m", 6.0)
    N = len(ring)
    for i in range(n):
        a, b = legs[i], legs[(i + 1) % n]
        if a["exit"] is None or b["exit"] is None or (a["side"] <= 0.0 and b["side"] <= 0.0):
            continue
        ea, eb = a["exit"][1], b["exit"][1]
        if ea == eb:
            skipped += 1
            why["same edge"] = why.get("same edge", 0) + 1
            continue
        chain = []
        k = (ea + 1) % N
        while True:
            chain.append(ring[k])
            if k == eb:
                break
            k = (k + 1) % N
            if len(chain) > N:
                break
        if len(chain) < 2 or len(chain) > N:
            skipped += 1
            why["chain"] = why.get("chain", 0) + 1
            continue
        Ca, Cb = chain[0], chain[-1]
        da, db = a["d"], b["d"]
        na, nb = (-da[1], da[0]), (-db[1], db[0])
        cut_a = (Ca[0] - P[0]) * da[0] + (Ca[1] - P[1]) * da[1]
        cut_b = (Cb[0] - P[0]) * db[0] + (Cb[1] - P[1]) * db[1]
        Ra = (P[0] + cut_a * da[0] + a["row"] * na[0], P[1] + cut_a * da[1] + a["row"] * na[1])
        Rb = (P[0] + cut_b * db[0] - b["row"] * nb[0], P[1] + cut_b * db[1] - b["row"] * nb[1])
        rr = max(r_all - max(a["side"], b["side"]), 1.0)
        c = _corner(P, da, db, a["row"], b["row"], rr, a["L"], b["L"])
        row = [Ra]
        if c is not None:
            ta, tb, Ta, Tb, O = c
            if ta <= cut_a + 0.01 and tb <= cut_b + 0.01:
                row.append(Ta)
                if O is not None:
                    row += _arc(O, Ta, Tb, rr)
                    row.append(Tb)
            else:
                # the property-line fillet reaches past the sidewalks' ends: the corner
                # where the property lines meet, if it is before them, else a chord
                X = _meet(P, da, db, a["row"], b["row"])
                if X is not None:
                    xa = (X[0] - P[0]) * da[0] + (X[1] - P[1]) * da[1]
                    xb = (X[0] - P[0]) * db[0] + (X[1] - P[1]) * db[1]
                    if 0.0 <= xa <= cut_a + 0.01 and 0.0 <= xb <= cut_b + 0.01:
                        row.append(X)
        row.append(Rb)
        # the corner: the sector from the node out to both sidewalks' ends and round the
        # property line, less the carriageway (the junction polygon); a leg without a
        # sidewalk leaves at most a sliver, which is dropped
        Pa = (P[0] + cut_a * da[0], P[1] + cut_a * da[1])
        Pb = (P[0] + cut_b * db[0], P[1] + cut_b * db[1])
        parts = _minus([P, Pa] + row + [Pb], ring, holes, taken)
        if parts is None:
            skipped += 1
            why["overlay"] = why.get("overlay", 0) + 1
            continue
        parts = [r for r in parts if abs(_area(r)) >= 0.3]
        if not parts:
            skipped += 1
            why["no sidewalk"] = why.get("no sidewalk", 0) + 1
            continue
        taken += parts
        drawn.append((parts, row))
    # faces along the pads' edges, in a second pass: an edge two pads share gets none
    uses: dict = {}
    for parts, _ in drawn:
        for r in parts:
            for k in range(len(r)):
                key = tuple(sorted((r[k], r[(k + 1) % len(r)])))
                uses[key] = uses.get(key, 0) + 1
    ends: set = set()
    for parts, row in drawn:
        drew = False
        for r in parts:
            sl = mesh._slot(pave)
            mark = (len(sl.pos), len(sl.idx), sl.auto)
            before = mesh_check({pave: sl})["winding"]
            if not mesh.poly(pave, r, zfun=lambda x, y: zfun(x, y) + 0.15):
                why["triangulation"] = why.get("triangulation", 0) + 1
                continue
            if mesh_check({pave: sl})["winding"] > before:
                # (M18: a pad that folds over one drawn before it, on a polygon whose
                # corners crowd each other: left out)
                del sl.pos[mark[0]:], sl.nrm[mark[0]:], sl.uv[mark[0]:], sl.idx[mark[1]:]
                sl.auto = mark[2]
                why["fold"] = why.get("fold", 0) + 1
                continue
            drew = True
            for k in range(len(r)):
                p, q = r[k], r[(k + 1) % len(r)]
                if uses[tuple(sorted((p, q)))] > 1:
                    continue
                # where two corners touch at a point, their faces there would share an
                # edge running the same way: the second face is left out
                if (q, 1) in ends or (p, -1) in ends:
                    continue
                ends.add((q, 1))
                ends.add((p, -1))
                mid = ((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0)
                if _near(mid, ring, True) or any(_near(mid, h, True) for h in holes):
                    mesh.wall(curb_slot, p, q, zfun(*p), zfun(*p) + 0.15, zfun(*q),
                              zfun(*q) + 0.15)
                elif _near(mid, row, False):
                    mesh.wall(pave, p, q, zfun(*p) - ROAD_DZ - 0.02, zfun(*p) + 0.15,
                              zfun(*q) - ROAD_DZ - 0.02, zfun(*q) + 0.15)
        if drew:
            made += 1
        else:
            skipped += 1
    return [made, skipped, dict(sorted(why.items()))]


__all__ = ["gather_sidewalk", "gather_crosswalk", "gather_junction", "math"]
