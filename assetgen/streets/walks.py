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
  surface where it carries one (`edge_z`; AG14: else, where the legs meet it at other
  heights, each leg's cut edge at the leg's height and the curb between two legs running
  evenly from one to the other: no step anywhere a leg meets it), the sidewalk corners
  between neighboring legs
  (the curb return from the junction polygon, the property-line fillet rebuilt as M2 builds
  it), their curb faces, and a deck slab under a raised junction.
"""

from __future__ import annotations

import math

import shapely

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
CUT_ALONG_M = 1.0       # AG14: how far along a leg an outline vertex still lies on its cut
                        # (a road piece ends on its cut edge within `roads.CUT_TOL_M`)
CLIP_M = 0.02           # #82: a sidewalk's slab stops this far into a junction's carriageway
RAISED_M = 0.5          # #89: a junction this far over its ground is raised (`barriers.RAISED_M`)
HEAD_M = 4.5            # #82: a strip keeps off a carriageway it is over by less than this
UNDER_M = 1.0           # ... or under by less than this (AG14's `fit.strips`)


def _under(zs, zc) -> bool:
    """#82: whether a carriageway at heights zc (lo, hi) is where a strip at heights zs
    (lo, hi) would stand on it or over it without headroom (`fit.strips`: from `UNDER_M`
    over the strip to `HEAD_M` under it)."""
    return zc[1] >= zs[0] - HEAD_M and zc[0] <= zs[1] + UNDER_M
CLIP_M2 = 0.0005        # ... where it reaches over this much of it
FILL_M2 = 0.05          # #82: a piece of a stretch it drops, off those carriageways, this big
FILL_W_M = 0.1          # ... and this wide (twice its area over its perimeter) is drawn flat


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
    clip = _clip_rings(cx, s, w)
    if clip:
        inputs["clip"] = clip
    if raised(road["seg"]):
        inputs["walkways"] = [{"id": k.id, "line": [list(p) for p in k.line]}
                              for k in sorted(cx.walkways_of.get(w.id, ()), key=lambda k: k.id)]
    return Piece(w.id, "street.sidewalk", "sidewalk", cx.tile_for(w.id, w.line),
                 cx.keys.get(w.id, []), inputs)


def _clip_rings(cx: Ctx, s, w) -> list:
    """#82: the junction outlines a sidewalk's slab reaches into (by over `CLIP_M2` past
    `CLIP_M`): any junction at its height (within `barriers.Z_NEAR_M` of the road there),
    its road's own end junctions always; and the carriageways of other roads at its height
    (`_carriageways`). M2 lays a sidewalk along the whole road where the road's cuts at its
    two junctions overlap (a short road between two junctions whose polygons overlap), so
    it runs through both; M17's long junctions reach over their legs' sidewalks; a road's
    sidewalk can also run into a neighboring junction or road. Rings in the model's
    coordinates, by junction or road id."""
    from citygen import geom as G

    from . import barriers as BR
    try:
        band = shapely.LineString([(p[0], p[1]) for p in w.line]).buffer(
            w.width_m / 2.0, cap_style="flat", join_style="mitre", mitre_limit=2.0)
    except (ValueError, shapely.errors.GEOSException):
        return []
    _, _, _, jtree, jns, polys, _ = BR._index(cx)
    ends = {cx.junction_at[n].id for n in (s.start, s.end) if n in cx.junction_at}
    out = []
    for k in sorted(jtree.query(band).tolist()):
        j = jns[k]
        inner = polys[k].buffer(-CLIP_M, join_style="mitre")
        if inner.is_empty:
            continue
        x = shapely.intersection(band, inner)
        if x.is_empty or x.area <= CLIP_M2:
            continue
        if j.id not in ends:
            c = x.representative_point()
            zs = BR._road_z(s, c.x, c.y)
            if not _under((zs, zs), BR._junction_z(cx, j)):
                continue
        out.append({"id": j.id, "ring": [[C.m2(p[0]), C.m2(p[1])]
                                         for p in G.from_model_poly(j.polygon).exterior.coords[:-1]]})
    for o, poly in _carriageways(cx, band, {s.id}):
        inner = poly.buffer(-CLIP_M, join_style="mitre")
        x = shapely.intersection(band, inner) if not inner.is_empty else None
        if x is None or x.is_empty or x.area <= CLIP_M2:
            continue
        c = x.representative_point()
        zs, zo = BR._road_z(s, c.x, c.y), BR._road_z(o, c.x, c.y)
        if not _under((zs, zs), (zo, zo)):
            continue
        with G.canonical():
            parts = sorted(G.parts(G.qpoly(poly)), key=lambda q: (G.qbounds(q), G.area1(q)))
        for part in parts:
            out.append({"id": o.id, "by": _ends_of(cx, o),
                        "ring": [[C.m2(p[0]), C.m2(p[1])] for p in part.exterior.coords[:-1]]})
    return out


def _ends_of(cx: Ctx, s) -> list:
    """The junctions at a road's ends (its carriageway as drawn ends on their outlines)."""
    return sorted(cx.junction_at[n].id for n in {s.start, s.end} if n in cx.junction_at)


def _carriageways(cx: Ctx, g, skip=()) -> list:
    """#82: the vehicle roads whose carriageway as
    AG7 draws it (from cut edge to cut edge, `Road`) meets a shapely geometry, with that
    carriageway; roads in `skip` left out. Cached on the context."""
    from . import barriers as BR
    tree, segs, lines, _, _, _, _ = BR._index(cx)
    cache = cx.__dict__.setdefault("_carriage_polys", {})
    out = []
    for k in sorted(tree.query(g.buffer(30.0)).tolist()):
        o = segs[k]
        if o.id in skip:
            continue
        if o.id not in cache:
            cache[o.id] = _carriage_poly(cx, o)
        poly = cache[o.id]
        if poly is not None and poly.intersects(g):
            out.append((o, poly))
    return out


def _carriage_poly(cx: Ctx, s):
    """A road's carriageway as its road piece draws it (`roads.Road`: from its junctions' cut
    edges), shapely; None where it has none (a pedestrian street or footbridge, or a road
    inside its junctions)."""
    if street_class(s) in PEDESTRIAN or len(s.centerline) < 2:
        return None
    ends = []
    for which, nid in (("start", s.start), ("end", s.end)):
        e = {"at": which}
        jj = cx.junction_at.get(nid)
        if jj is not None:
            e["junction"] = {"ring": [list(p) for p in jj.polygon.exterior]}
        ends.append(e)
    try:
        rd = Road({"seg": s.model_dump(mode="json", exclude_none=True),
                   "cls": street_class(s), "ends": ends})
    except ValueError:
        return None
    if rd.s1 - rd.s0 < 0.3:
        return None
    left, right = [], []
    for sv, vi in rd.stations(rd.s0, rd.s1):
        left.append(rd.at(sv, rd.h, vi))
        right.append(rd.at(sv, -rd.h, vi))
    poly = shapely.Polygon(left + right[::-1])
    return poly if poly.is_valid else shapely.make_valid(poly)


def _clear_spans(P: Path, t0: float, t1: float, rings: list) -> list:
    """#82: the stretches [(a, b)] of a strip along a line P (a sidewalk's slab, a median:
    offsets t0..t1 either side of it) that are off the rings: the strip (P grown by its
    half width, mitred as it is drawn) less the rings shrunk by `CLIP_M`, each piece of the
    overlap blocking the stretch of P its points project onto (a centimeter more each
    way); stretches under 0.3 m are left out."""
    from citygen import geom as G
    half = max(abs(t0), abs(t1))
    with G.canonical():
        band = G.qpoly(shapely.LineString(P.p).buffer(half, cap_style="flat",
                                                      join_style="mitre", mitre_limit=2.0))
        inner = [G.qpoly(shapely.make_valid(shapely.Polygon(r)).buffer(-CLIP_M,
                                                                       join_style="mitre"))
                 for r in rings if len(r) >= 3]
        inner = [g for g in inner if not g.is_empty]
        u = G.union(inner) if inner else None
        x = G.inter(band, u) if u is not None else None
        parts = G.parts(x) if x is not None and not x.is_empty else []
    blocked = []
    for part in parts:
        if G.area1(part) <= 1e-6:
            continue
        ss = [P.project(q[0], q[1])[0] for q in part.exterior.coords]
        blocked.append((max(0.0, C.m2(min(ss) - 0.01)), min(P.L, C.m2(max(ss) + 0.01))))
    blocked.sort()
    spans, at = [], 0.0
    for lo, hi in blocked:
        if lo - at >= 0.3:
            spans.append((C.m2(at), C.m2(lo)))
        at = max(at, hi)
    if P.L - at >= 0.3:
        spans.append((C.m2(at), P.L))
    if not parts:
        return spans
    # (each stretch as drawn, mitred at the line's vertices, where the grown line is not:
    # shortened 10 cm at a time at the end nearer what it still covers)
    out = []
    for a, b in spans:
        while b - a >= 0.3:
            with G.canonical():
                ov = G.inter(G.qpoly(_drawn(P, a, b, t0, t1)), u)
            if ov.is_empty or G.area1(ov) <= 1e-4:
                out.append((a, b))
                break
            sc = min(P.project(q[0], q[1])[0] for g in G.parts(ov) for q in g.exterior.coords)
            if sc - a <= b - sc:
                a = C.m2(a + 0.1)
            else:
                b = C.m2(b - 0.1)
    return out


def _fills(P: Path, spans: list, t0: float, t1: float, rings: list) -> list:
    """#82: the pieces of a sidewalk's band between the stretches `_clear_spans` keeps, off
    the rings (counterclockwise rings on the grid, with their holes): where a junction or
    road reaches over the band's inner edge, the stretch goes, and the rest of its width is
    drawn flat (`_fill`). Pieces under `FILL_M2` or `FILL_W_M` wide are left out."""
    from citygen import geom as G
    gaps, at = [], 0.0
    for a, b in spans:
        if a - at > 0.01:
            gaps.append((at, a))
        at = b
    if P.L - at > 0.01:
        gaps.append((at, P.L))
    if not gaps:
        return []
    out = []
    with G.canonical():
        inner = [G.qpoly(shapely.make_valid(shapely.Polygon(r))) for r in rings if len(r) >= 3]
        inner = [g for g in inner if not g.is_empty]
        u = G.union(inner) if inner else None
        for a, b in gaps:
            g = G.qpoly(_drawn(P, a, b, t0, t1))
            if u is not None:
                g = G.diff(g, u)
            for part in G.parts(g):
                ar = G.area1(part)
                if ar < FILL_M2:
                    continue
                per = sum(math.hypot(q[0] - p_[0], q[1] - p_[1])
                          for rg in [part.exterior, *part.interiors]
                          for p_, q in zip(rg.coords[:-1], rg.coords[1:]))
                if 2.0 * ar < FILL_W_M * per:
                    continue
                part = shapely.geometry.polygon.orient(part, 1.0)
                ring = [(C.m2(x), C.m2(y)) for x, y in part.exterior.coords[:-1]]
                holes = [[(C.m2(x), C.m2(y)) for x, y in h.coords[:-1]]
                         for h in part.interiors]
                out.append((ring, holes))
    return out


def _fill(mesh: Mesh, rd: Road, ring, holes, curb_h: float, curb_slot: str, pave: str,
          ends) -> bool:
    """#82: a piece of a sidewalk (`_fills`) flat at its height (the road's at the point,
    plus the curb), with a face down to under the road along every edge but where it meets
    a slab the sidewalk draws (`ends`); left out where it would fold."""
    def zf(x, y):
        return rd.z(rd.path.project(x, y)[0]) + curb_h
    slots = (pave, curb_slot)
    marks = {}
    for sn in slots:
        sl = mesh._slot(sn)
        marks[sn] = (len(sl.pos), len(sl.idx), sl.auto, mesh_check({sn: sl})["winding"])
    ok = mesh.poly(pave, ring, holes, zfun=zf)
    if ok:
        for r in [ring] + list(holes):
            for k in range(len(r)):
                a, b = r[k], r[(k + 1) % len(r)]
                mid = shapely.Point((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
                if ends is not None and ends.boundary.distance(mid) <= 0.02:
                    continue
                lo = curb_h + ROAD_DZ + 0.02
                mesh.wall(curb_slot, a, b, zf(*a) - lo, zf(*a), zf(*b) - lo, zf(*b))
        ok = all(mesh_check({sn: mesh._slot(sn)})["winding"] <= marks[sn][3] for sn in slots)
    if not ok:
        for sn in slots:
            sl = mesh._slot(sn)
            n, i, auto, _ = marks[sn]
            del sl.pos[n:], sl.nrm[n:], sl.uv[n:], sl.idx[i:]
            sl.auto = auto
    return ok


def _drawn(P: Path, a: float, b: float, t0: float, t1: float):
    """A strip along P from a to b between offsets t0 and t1, as its rows draw it (square at
    its ends, mitred at the line's vertices), shapely."""
    left, right = [], []
    for sv, vi in P.stations(a, b, 1e9):
        x, y, nx, ny, k = P.frame(sv, vi)
        left.append((x + nx * k * t1, y + ny * k * t1))
        right.append((x + nx * k * t0, y + ny * k * t0))
    g = shapely.Polygon(left + right[::-1])
    return g if g.is_valid else shapely.make_valid(g)


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
    spans, fills = [(0.0, P.L)], []
    if inp.get("clip"):
        # (#82: only where the slab is off every junction's carriageway it reaches into;
        # where it is not, the rest of its width flat)
        rings = [c["ring"] for c in inp["clip"]]
        spans = _clear_spans(P, t_curb, t_curb + sgn * width, rings)
        fills = _fills(P, spans, t_curb, t_curb + sgn * width, rings)
        if not spans and not fills:
            return Out(empty="inside its junctions")
    for s0, s1 in spans:
        _slab(mesh, P, rd, s0, s1, extra, drops, offs, t_curb, sgn, curb_h, curb_slot, pave)
    if fills:
        ends = shapely.union_all([_drawn(P, a, b, t_curb, t_curb + sgn * width)
                                  for a, b in spans]) if spans else None
        for ring, holes in fills:
            _fill(mesh, rd, ring, holes, curb_h, curb_slot, pave, ends)
    # tree pits
    for ts, tt, _ in inp["trees"]:
        if inp.get("clip") and not any(a + PIT_M / 2.0 <= ts <= b - PIT_M / 2.0
                                       for a, b in spans):
            continue
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


def _slab(mesh: Mesh, P: Path, rd: Road, s0: float, s1: float, extra, drops, offs, t_curb,
          sgn, curb_h, curb_slot, pave):
    """A sidewalk's slab, curb stone, curb face and back face from s0 to s1."""
    st = P.stations(s0, s1, 5.0, extra)
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

def _junction_base(cx: Ctx, j) -> dict:
    """What a junction's surface is made from (`_surface`): itself, its node and its legs."""
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
            # (#89: the junction at its far end, where its road piece's far cut is)
            far = cx.junction_at.get(s.end if at_start else s.start)
            if far is not None and far.id != j.id:
                leg["far"] = {"id": far.id, "ring": [list(q) for q in far.polygon.exterior]}
            legs.append(leg)
    cxy = bbox_center(j.polygon.exterior)
    return {"junction": dump(j), "node": list(node.position) if node else [*cxy, 0.0],
            "node_ground": getattr(node, "ground_m", None) or 0.0, "legs": legs}


def gather_junction(cx: Ctx, j) -> Piece:
    ext = j.polygon.exterior
    cxy = bbox_center(ext)
    did = cx.district_of_point(*cxy)
    inputs = _junction_base(cx, j)
    inputs.update({"style": cx.style(did), "origin": list(cxy)})
    # #82: the junctions overlapping it, and the connector lanes that run off its outline
    ov = _overlaps(cx, j)
    if ov:
        inputs["overlaps"] = ov
    ln = _lanes_off(cx, j)
    if ln:
        inputs["lanes"] = ln
        ms = _masses_near(cx, j)
        if ms:
            inputs["masses"] = ms
    rd = _roads_near(cx, j)
    if rd:
        inputs["roads"] = rd
    sw = _walks_in(cx, j)
    if sw:
        inputs["walks"] = sw
    if j.level:
        # M14 (AG10): a deck's junction lies on its slab; where it reaches past it (at a
        # ramp's top) a slab of its own carries it
        inputs["off_deck"] = _off_deck(cx, j)
    # (#95: the barriers it carries between its legs, `barriers.junction_plan`)
    from . import barriers as BR
    plan = BR.junction_plan(cx, j)
    if plan["corners"] or plan["median"]:
        near = BR.near_of_junction(cx, j)
        near["ends"] = BR.leg_ends(cx, j)
        inputs["barriers"] = {"corners": [{"a": c["a"], "b": c["b"], "kind": c["kind"]}
                                          for c in plan["corners"]],
                              "median": plan["median"], "xwalks": near.pop("xwalks"),
                              "near": near}
    return Piece(j.id, "street.junction", "junction", cx.tile_for(j.id, ext),
                 cx.keys.get(j.id, []), inputs)


OVERLAP_M2 = 0.5        # #82: junction outlines overlapping by more than this share it
LANE_IN_M = 0.25        # ... and a connector lane is paved this far in from its edges


def _overlaps(cx: Ctx, j) -> list:
    """#82: the junctions whose outline overlaps this one's by over `OVERLAP_M2` at its
    height (their surfaces within `barriers.Z_NEAR_M`): {"id", "ring" (their outline), and
    where it owns the overlap (the larger outline, else the earlier id) "owner" and "drawn"
    (its outline with its legs' carriageway corners, as (x, y, z): the heights its surface
    has there, `_surface`)}. M17 joins the pavement two roads share to the junctions it
    runs out of; where two roads run side by side between the same two nodes, both
    junctions took the whole stretch between them (Delta's `jn.e217s328` and
    `jn.e170s444`, 11 m apart in height), and each drew it at its own heights."""
    from citygen import geom as G

    from . import barriers as BR
    _, _, _, jtree, jns, polys, _ = BR._index(cx)
    at = {o.id: k for k, o in enumerate(jns)}
    k0 = at.get(j.id)
    if k0 is None:
        return []
    me = polys[k0]
    zj = BR._junction_z(cx, j)
    area = BR.junction_area(cx, j)
    sec = None
    if len(area) >= 2:
        with G.canonical():
            sec = G.diff(G.union([G.qpoly(shapely.make_valid(shapely.Polygon(r)))
                                  for r in area[1:]]), me)
    out = []
    for k in sorted(jtree.query(me if sec is None else G.union([me, sec])).tolist()):
        o = jns[k]
        if o.id == j.id:
            continue
        with G.canonical():
            x = G.inter(me, polys[k])
            ar = G.area1(x) if not x.is_empty else 0.0
            # (or one that reaches into its corners: its pads keep off it)
            reach = 0.0 if sec is None else G.area1(G.inter(sec, polys[k]))
        if ar <= OVERLAP_M2 and reach <= CLIP_M2:
            continue
        zo = BR._junction_z(cx, o)
        level = not (zo[0] - BR.Z_NEAR_M > zj[1] or zo[1] + BR.Z_NEAR_M < zj[0])
        if not level and not _under(zj, zo):
            continue
        a0, a1 = round(G.area1(me), 2), round(G.area1(polys[k]), 2)
        rec = {"id": o.id, "ring": [[C.m2(q[0]), C.m2(q[1])]
                                    for q in G.from_model_poly(o.polygon).exterior.coords[:-1]]}
        # (its corners: the lanes this one paves keep off them, and where it owns the
        # overlap this one's pads too)
        rec["area"] = [[[C.m2(q[0]), C.m2(q[1])] for q in rg]
                       for rg in BR.junction_area(cx, o)[1:]]
        rec["by"] = sorted(BR._area_by(cx, o))
        if level and ar > OVERLAP_M2 and (a1 > a0 or (a1 == a0 and o.id < j.id)):
            sf = _surface(_junction_base(cx, o))
            rec["owner"] = True
            rec["drawn"] = [[x_, y_, C.m(sf["zfun"](x_, y_))] for x_, y_ in sf["cring"]]
        out.append(rec)
    return out


def _roads_near(cx: Ctx, j) -> list:
    """#82: the carriageways (as AG7 draws them) of roads other than its legs that reach
    into a junction's corners (`barriers.junction_area`) at its height, as rings: its
    pads keep off them."""
    from citygen import geom as G

    from . import barriers as BR
    area = BR.junction_area(cx, j)
    if len(area) < 2:
        return []
    with G.canonical():
        sec = G.union([G.qpoly(shapely.make_valid(shapely.Polygon(r))) for r in area[1:]])
    zj = BR._junction_z(cx, j)
    out = []
    for o, poly in _carriageways(cx, sec, set()):
        x = shapely.intersection(sec, poly)
        if x.is_empty or x.area <= CLIP_M2:
            continue
        c = x.representative_point()
        zo = BR._road_z(o, c.x, c.y)
        if not _under(zj, (zo, zo)):
            continue
        with G.canonical():
            parts = sorted(G.parts(G.qpoly(poly)), key=lambda q: (G.qbounds(q), G.area1(q)))
        for part in parts:
            out.append({"id": o.id, "by": _ends_of(cx, o),
                        "ring": [[C.m2(p[0]), C.m2(p[1])] for p in part.exterior.coords[:-1]]})
    return out


def _walks_in(cx: Ctx, j) -> list:
    """#82: the sidewalks whose slab reaches into a junction's corners at its height (by over
    `CLIP_M2`: a leg's own sidewalk beside a ramp it runs on inside the junction, or a
    neighboring road's beside a corner), as {"id", "ring"}: its pads and paved lanes keep
    off them (the sidewalk piece paves them)."""
    from citygen import geom as G

    from . import barriers as BR
    area = BR.junction_area(cx, j)
    if len(area) < 2:
        return []
    with G.canonical():
        sec = G.union([G.qpoly(shapely.make_valid(shapely.Polygon(r))) for r in area[1:]])
        sec = G.diff(sec, G.from_model_poly(j.polygon))
    if sec.is_empty:
        return []
    tree, walks, bands = _walk_index(cx)
    zj = BR._junction_z(cx, j)
    out = []
    for k in sorted(tree.query(sec).tolist()):
        w, band = walks[k], bands[k]
        x = shapely.intersection(band, sec)
        if x.is_empty or x.area <= CLIP_M2:
            continue
        c = x.representative_point()
        s = cx.seg.get(w.segment_id)
        if s is None or not BR._near_z(BR._road_z(s, c.x, c.y), zj):
            continue
        with G.canonical():
            parts = sorted(G.parts(G.qpoly(band)), key=lambda q: (G.qbounds(q), G.area1(q)))
        for part in parts:
            out.append({"id": w.id, "ring": [[C.m2(q[0]), C.m2(q[1])]
                                             for q in part.exterior.coords[:-1]]})
    return out


def _walk_index(cx: Ctx):
    """Every sidewalk's slab (its line grown by half its width), indexed; cached."""
    got = cx.__dict__.get("_walk_index")
    if got is None:
        walks, bands = [], []
        for w in sorted(cx.m.sidewalks, key=lambda w: w.id):
            if len(w.line) < 2:
                continue
            walks.append(w)
            bands.append(shapely.LineString([(p[0], p[1]) for p in w.line]).buffer(
                w.width_m / 2.0, cap_style="flat", join_style="mitre", mitre_limit=2.0))
        got = cx._walk_index = (shapely.STRtree(bands), walks, bands)
    return got


MASS_CLEAR_M = 2.0      # #82: paved lanes keep this off a building (its balconies, canopies)


def _masses_near(cx: Ctx, j) -> list:
    """#82: the building masses in a junction's corners (`barriers.junction_area`, grown by
    `MASS_CLEAR_M`) from its height up to `HEAD_M` over it, as {"id", "ring"}: the lanes it
    paves keep `MASS_CLEAR_M` off them (a lane M2 laid past the curb ran into a building or
    under its balconies)."""
    from citygen import geom as G

    from . import barriers as BR
    area = BR.junction_area(cx, j)
    with G.canonical():
        reach = G.union([G.qpoly(shapely.make_valid(shapely.Polygon(r))) for r in area])
    tree, polys, rows = BR._masses(cx)
    if tree is None:
        return []
    zj = BR._junction_z(cx, j)
    out = []
    for k in sorted(tree.query(reach.buffer(MASS_CLEAR_M)).tolist()):
        bid, _, z0, z1 = rows[k]
        if z0 > zj[1] + HEAD_M or z1 < zj[0]:
            continue
        out.append({"id": bid, "ring": [[C.m2(q[0]), C.m2(q[1])]
                                        for q in polys[k].exterior.coords[:-1]]})
    return out


def _lanes_off(cx: Ctx, j) -> list:
    """#82: the junction's connector lanes whose corridor (its width less `LANE_IN_M` a
    side) runs off its outline by over `OVERLAP_M2`: {"line", "h"}."""
    from citygen import geom as G

    from . import barriers as BR
    lanes = [ln for ln in sorted(BR._connectors(cx, j.node_id), key=lambda ln: ln.id)
             if len(ln.centerline) >= 2 and ln.width_m / 2.0 - LANE_IN_M > 0.5]
    if not lanes:
        return []
    poly = G.from_model_poly(j.polygon)
    out = []
    for ln in lanes:
        h = ln.width_m / 2.0 - LANE_IN_M
        line = shapely.LineString([(q[0], q[1]) for q in ln.centerline])
        cor = line.buffer(h, cap_style="flat", join_style="mitre", mitre_limit=2.0)
        if shapely.difference(cor, poly).area > OVERLAP_M2:
            out.append({"id": ln.id, "line": [[C.m2(q[0]), C.m2(q[1])] for q in ln.centerline],
                        "h": C.m(h)})
    return out


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


@maker("junction", 3)
def make_junction(inp: dict) -> Out:
    sf = _surface(inp)
    j = inp["junction"]
    ring, holes, legs, zn, zfun, vz = sf["ring"], sf["holes"], sf["legs"], sf["zn"], \
        sf["zfun"], sf["vz"]
    cring = sf["cring"]
    P = (inp["node"][0], inp["node"][1])
    style = inp["style"]
    mesh = Mesh(inp["origin"])
    top = max((r["cls"] for r in legs), key=lambda c: RANK.get(c, 0), default="street")
    slot = {"highway": "asphalt.highway", "avenue": "asphalt.avenue"}.get(
        top, "asphalt.alley" if top in ("alley", "service") else "asphalt.street")
    if top in PEDESTRIAN:
        slot = MT.paving(style["archetype"])
    # #82: the carriageway as drawn: the outline less what an overlapping junction that owns
    # it draws, with the connector lanes that run off it round its corners
    sectors = _sectors(ring, P, legs, j)
    car = _carriageway(inp, sf, sectors)
    others = [o["ring"] for o in inp.get("overlaps", ())] + \
        [r["ring"] for r in inp.get("roads", ())]
    if car is None:
        ok = mesh.poly(slot, cring, holes, zfun=zfun, keep_straight=cring is not ring)
        if not ok:
            # a ring that touches itself: its valid parts, in a fixed order
            ok = any([mesh.poly(slot, r, hs, zfun=zfun) for r, hs in _valid_parts(ring, holes)])
        if not ok:
            return Out(empty="untriangulable polygon")
        drawn = [(cring, holes)]
        hz = zfun
        bz = zfun if vz is None else _edge_z([[(x, y, zfun(x, y)) for x, y in cring]])
    else:
        drawn, hz, paved = car
        if not drawn:
            return Out(empty="inside an overlapping junction")
        for r, hs in drawn:
            mesh.poly(slot, r, hs, zfun=hz, keep_straight=True)
        rz = [[(x, y, hz(x, y)) for x, y in r] for r, _ in drawn]
        rz += [[(p[0], p[1], p[2]) for p in o["drawn"]] for o in inp.get("overlaps", ())
               if o.get("drawn")]
        bz = _edge_z(rz)
    # (raised: its node or a leg where it leaves it over its ground by `RAISED_M`)
    up = zn - inp["node_ground"] - ROAD_DZ > RAISED_M or \
        any(r["zo"] > RAISED_M for r in sf["lz"])
    if j.get("level"):
        for r_, hs_ in inp.get("off_deck", ()):
            mesh.prism("concrete.deck", ccw(r_), zn - ROAD_DZ - 1.2, zn - ROAD_DZ - 0.01,
                       top=False, bottom=True, holes=[ccw(h)[::-1] for h in hs_])
    elif car is None and vz is None:
        if zn - inp["node_ground"] - ROAD_DZ > 0.5:
            D = max(DECK_D.get(r["cls"], 1.2) for r in legs) if legs else 1.2
            mesh.prism("concrete.deck", ring, zn - ROAD_DZ - D, zn - ROAD_DZ - 0.01,
                       top=False, bottom=True)
    elif up:
        # (#82: under a raised junction whose surface is not level, the slab follows it: a
        # flat slab at its node's height stood through its lower stretches)
        D = max(DECK_D.get(r["cls"], 1.2) for r in legs) if legs else 1.2
        for r, hs in drawn:
            _draped(mesh, "concrete.deck", r, hs, hz, D)
    rows: dict = {}
    curbs = [r for r, _ in drawn] + [h for _, hs in drawn for h in hs] + list(others)
    block = None
    if car is not None or others or inp.get("walks"):
        from citygen import geom as G
        with G.canonical():
            gs = [G.qpoly(shapely.make_valid(shapely.Polygon(r, hs))) for r, hs in drawn]
            gs += [G.qpoly(shapely.make_valid(shapely.Polygon(o))) for o in others]
            gs += [G.qpoly(shapely.make_valid(shapely.Polygon(rg)))
                   for o in inp.get("overlaps", ()) if o.get("owner")
                   for rg in o.get("area", ())]
            gs += [G.qpoly(shapely.make_valid(shapely.Polygon(w["ring"])))
                   for w in inp.get("walks", ())]
            block = G.union(gs) if gs else None
    made: list = []
    pads = _corners(mesh, ring, holes, P, legs, j, style, bz, rows, sectors=sectors,
                    block=block, curbs=curbs, pads_out=made)
    if inp.get("barriers"):
        _junction_barriers(mesh, ring, legs, inp["barriers"], rows, bz)
    out = Out(mesh=mesh)
    out.notes["corner_pads"] = pads
    if car is not None and car[2]:
        # (#82: the connector lanes' runs it paves past its outline; AG8 keeps props off them)
        out.notes["paved"] = car[2]
    if not j.get("level") and drawn and up:
        # (#89: on a raised junction a thing stands only where AG7 paves: its carriageway
        # and the corner pads it drew, in the corners between its legs (a corner with no
        # sidewalk has none); AG8 reads this)
        out.notes["raised"] = {
            "area": [[[C.m2(x), C.m2(y)] for x, y in sc["sector"]] for sc in sectors
                     if "sector" in sc],
            "carriageway": [[[C.m2(x), C.m2(y)] for x, y in r] for r, _ in drawn],
            "z": [C.m(min(hz(x, y) for r, _ in drawn for x, y in r)),
                  C.m(max(hz(x, y) for r, _ in drawn for x, y in r))],
            "pads": made,
            # (and its legs' rights of way from the node to their cuts: between two twin
            # legs, or a corner with no pad, nothing is drawn there)
            "rows": _leg_rows(sf["lz"])}
    return out


def _leg_rows(legs) -> list:
    """#89: each leg's right of way from its junction's node out to its cut, as rings."""
    out = []
    for r in legs:
        if r.get("exit") is None or r["exit"][0] <= 0.05:
            continue
        g = _drawn(r["path"], 0.0, min(r["exit"][0], r["path"].L), -r["row"], r["row"])
        for q in getattr(g, "geoms", [g]):
            if q.geom_type == "Polygon" and q.area > 0.01:
                out.append([[C.m2(x), C.m2(y)] for x, y in q.exterior.coords[:-1]])
    return out


def _surface(inp: dict) -> dict:
    """A junction's outline, legs and heights: {ring, holes, legs, lz, flat, zn, vz (height
    of each outline vertex, None where level at its node), zfun, cring (the outline with
    its legs' carriageway corners)}. Shared by its piece and (#82) the pieces of junctions
    that overlap it."""
    j = inp["junction"]
    ring = ccw(j["polygon"]["exterior"])
    # holes: M2 leaves only slivers (a ring touching the outline); a junction is paved through
    holes = [ccw(h)[::-1] for h in j["polygon"].get("holes", [])
             if abs(_area(h)) >= HOLE_M2 and not any(tuple(p) in {tuple(q) for q in ring} for p in h)]
    P = (inp["node"][0], inp["node"][1])
    zn = inp["node"][2] + inp["node_ground"] + ROAD_DZ
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
            gp = Profile(list(zip(Path(lg["line"]).cum, lg["ground_pts"])))
        else:
            gp = Profile([])
        Lr = path.L
        ex = first_exit(path.p, ring)
        cls = lg["cls"]
        side = 0.0 if cls in PEDESTRIAN else lg["side"]
        d = _leg_dir(path.p, P)
        rec = {"cls": cls, "d": d, "ang": M.atan2(d[1], d[0]), "L": Lr, "row": lg["width"] / 2.0,
               "side": side, "id": lg["id"], "exit": ex,
               "key": f"{lg['id']}@{'s' if lg['at_start'] else 'e'}",
               "path": path, "h": lg["width"] / 2.0 - side,
               "zs": (lambda s, gp=gp, zp=zp, a=lg["at_start"], L=Lr:
                      gp(s if a else L - s) + zp(s if a else L - s) + ROAD_DZ),
               "knots": sorted({(k if lg["at_start"] else Lr - k) for k in zp.s + gp.s})}
        if lg.get("far"):
            fx = first_exit(path.p[::-1], ccw(lg["far"]["ring"]))
            if fx is not None:
                rec["far"] = Lr - min(fx[0], Lr)
        if ex is not None:
            s = ex[0]
            rec["z"] = rec["zs"](s)
            rec["zo"] = zp(s if lg["at_start"] else Lr - s)   # (over its ground)
            a, b = ring[ex[1]], ring[(ex[1] + 1) % len(ring)]
            rec["mid"] = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
            rec["at"] = path.point(s)
            rec["tan"] = path.tangent(s)
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
    else:
        vz = None
    if vz is not None:
        # AG14: the two ends of a leg's cut edge (where its road piece ends) at the leg's
        # height there, as the road meets them (M18's curb runs from a cut's corner a few
        # centimeters off it where the cut is skewed)
        for r in lz:
            for k in _cut_run(ring, r):
                if (ring[k][0], ring[k][1]) in vz:
                    vz[(ring[k][0], ring[k][1])] = _run_z(ring, r, k)
    if vz is None and not flat and lz:
        # AG14: no surface in the model (a junction M18 left flat whose legs AG7 sees at
        # other heights): each leg's cut edge at the leg's height there, the curb between
        # two legs running evenly along the outline from one to the other (as M18 draws
        # its surfaces), so every leg meets the junction with no step
        anchor = {}
        for r in lz:
            for k in _cut_run(ring, r):
                anchor[k] = _run_z(ring, r, k)
        n = len(ring)
        cum = [0.0]
        for k in range(n):
            cum.append(cum[-1] + dist(ring[k], ring[(k + 1) % n]))
        per = cum[-1] or 1.0
        ks = sorted(anchor)
        vz = {}
        for k in range(n):
            if k in anchor:
                vz[(ring[k][0], ring[k][1])] = anchor[k]
                continue
            # the anchors before and after k along the ring
            a = max([q for q in ks if q < k], default=ks[-1])
            b = min([q for q in ks if q > k], default=ks[0])
            da = (cum[k] - cum[a]) % per
            db = (cum[b] - cum[k]) % per
            f = da / (da + db) if da + db > 0 else 0.0
            vz[(ring[k][0], ring[k][1])] = anchor[a] + (anchor[b] - anchor[a]) * f
    if vz is None and flat and lz:
        # #89: a junction level at its node whose outline runs on along a leg's side past
        # its cut, where the road already climbs: those outline vertices at the road's
        # height (`_run_z`, `_with_corners`), the rest at the node's
        runs = {k: _run_z(ring, r, k) for r in lz for k in _cut_run(ring, r)}
        _, extra = _with_corners(ring, legs, inp["legs"])
        if any(abs(z - zn) > 0.002 for z in runs.values()) or \
                any(abs(z - zn) > 0.002 for _, z in extra):
            vz = {(p[0], p[1]): zn for p in ring}
            for k, z in runs.items():
                vz[(ring[k][0], ring[k][1])] = z
    if vz is not None:
        _along_legs(ring, lz, vz)
    vpts = list(vz.items()) if vz is not None else []

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
    cring = ring
    if vz is not None:
        # AG14: a leg's carriageway corners where they fall on the outline between its
        # vertices (a road cut square across, not along the outline's own cut edge) become
        # vertices of it at the leg's height, so the leg meets the junction there too
        cring, extra = _with_corners(ring, legs, inp["legs"])
        for p, z in extra:
            vz[p] = z
    return {"ring": ring, "holes": holes, "legs": legs, "lz": lz, "flat": flat, "zn": zn,
            "vz": vz, "zfun": zfun, "cring": cring}


LONG_LEG_M = 40.0       # #82: a leg running this far inside its junction ...
ALONG_FROM_M = 15.0     # ... gives the outline beside it its height from here on


def _along_legs(ring, lz: list, vz: dict) -> None:
    """#82: where a leg runs on inside its junction past `LONG_LEG_M` (M17 laid two roads
    between the same two nodes side by side, and their shared pavement joined both
    junctions: the whole ramp between them), the outline beside it (within its right of
    way, from `ALONG_FROM_M` off the node to a meter short of its exit) takes the leg's
    height there: M18's curb, running evenly from one leg's cut to the next round the
    outline, stood meters off the ramp. A vertex beside two such legs takes the nearer's."""
    long = [r for r in lz if r["exit"][0] >= LONG_LEG_M]
    if not long:
        return
    cuts = {k for r in lz for k in _cut_run(ring, r)}
    for k, p in enumerate(ring):
        if k in cuts:
            continue
        best = None
        for r in long:
            s, t = r["path"].project(p[0], p[1])
            if ALONG_FROM_M <= s <= r["exit"][0] - 1.0 and abs(t) <= r["row"] + 0.05 and \
                    (best is None or abs(t) < best[0]):
                best = (abs(t), r["zs"](s))
        if best is not None:
            vz[(p[0], p[1])] = best[1]


def _edge_z(rings) -> callable:
    """#82: the height at a point of the nearest point on rings of (x, y, z) vertices (linear
    along each edge; ties to the first): what a corner pad, its curb and a junction's own
    barriers stand on (an inverse-distance blend of the outline's vertices stood off the
    curb between them)."""
    segs = []
    for r in rings:
        n = len(r)
        for i in range(n):
            segs.append((r[i], r[(i + 1) % n]))

    def f(x: float, y: float) -> float:
        best = None
        for (ax, ay, az), (bx, by, bz) in segs:
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 <= 0.0 else min(max(((x - ax) * dx + (y - ay) * dy) / L2, 0.0), 1.0)
            ex, ey = x - ax - dx * t, y - ay - dy * t
            d2 = ex * ex + ey * ey
            if best is None or d2 < best[0] - 1e-12:
                best = (d2, az + (bz - az) * t)
        return best[1] if best is not None else 0.0
    return f


def _draped(mesh: Mesh, slot: str, ring, holes, zf, D: float) -> bool:
    """A slab D deep under a surface (its vertices at zf): its sides and underside; left
    out where it would fold over what the slot holds (a sliver of an overlap)."""
    sl = mesh._slot(slot)
    mark = (len(sl.pos), len(sl.idx), sl.auto, mesh_check({slot: sl})["winding"])
    for rr in [ring] + list(holes):
        n = len(rr)
        for i in range(n):
            a, b = rr[i], rr[(i + 1) % n]
            mesh.wall(slot, a, b, zf(*a) - ROAD_DZ - D, zf(*a) - ROAD_DZ - 0.01,
                      zf(*b) - ROAD_DZ - D, zf(*b) - ROAD_DZ - 0.01)
    mesh.poly(slot, ring, holes, zfun=lambda x, y: zf(x, y) - ROAD_DZ - D, up=False,
              keep_straight=True)
    if mesh_check({slot: sl})["winding"] <= mark[3]:
        return True
    del sl.pos[mark[0]:], sl.nrm[mark[0]:], sl.uv[mark[0]:], sl.idx[mark[1]:]
    sl.auto = mark[2]
    return False


CAR_MIN_M2 = 0.5        # #82: pieces of a lane's run off its junction smaller than this go
HOLE_M2 = 4.0           # a junction is paved through holes smaller than this
SPIKE_COS = 0.99863     # ... and a vertex where its outline turns back within 3 degrees (a
                        # needle the overlay leaves) (`_despike`)


def _despike(r: list) -> list:
    """#82: a ring without its needles: vertices where it turns back within 3 degrees (or
    repeats), plain arithmetic on its grid points."""
    r = list(r)
    changed = True
    while changed and len(r) > 3:
        changed = False
        for i in range(len(r)):
            a, p, b = r[i - 1], r[i], r[(i + 1) % len(r)]
            ux, uy, vx, vy = p[0] - a[0], p[1] - a[1], b[0] - p[0], b[1] - p[1]
            lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
            if lu < 1e-9 or lv < 1e-9 or ux * vx + uy * vy < -SPIKE_COS * lu * lv:
                del r[i]
                changed = True
                break
    return r


def _carriageway(inp: dict, sf: dict, sectors: list):
    """#82: the carriageway a junction draws, as ([(ring, holes)], height function), or None
    where it is its outline (as before): its outline less the junctions that overlap it and
    own the overlap (`overlaps`: the larger outline draws it whole), with each connector
    lane's run off the outline within the corners between its legs (`lanes`: M2 lays a
    turning lane over the sidewalk corner, past the curb). Heights: the outline's own
    vertices as before; a vertex on an owner's outline its height there (so the two
    surfaces meet along it); a vertex of a lane's run the curb's at its nearest point."""
    from citygen import geom as G
    own = [o for o in inp.get("overlaps", ()) if o.get("owner")]
    lanes = inp.get("lanes") or []
    if not own and not lanes:
        return None
    holes, cring, zfun = sf["holes"], sf["cring"], sf["zfun"]
    with G.canonical():
        base = G.qpoly(shapely.make_valid(shapely.Polygon(cring, holes)))
        add = None
        if lanes and any("sector" in s for s in sectors):
            cor = G.union([G.qpoly(shapely.LineString(ln["line"]).buffer(
                ln["h"], cap_style="flat", join_style="mitre", mitre_limit=2.0))
                for ln in lanes])
            sec = G.union([G.qpoly(shapely.make_valid(shapely.Polygon(s["sector"])))
                           for s in sectors if "sector" in s])
            add = G.diff(G.inter(cor, sec), base)
            # (not over its legs' sidewalks, another road or junction or its corners:
            # they are drawn there; nor near a building)
            keep = [w["ring"] for w in inp.get("walks", ())] + \
                [r["ring"] for r in inp.get("roads", ())] + \
                [o["ring"] for o in inp.get("overlaps", ())] + \
                [rg for o in inp.get("overlaps", ()) for rg in o.get("area", ())]
            gs = [G.qpoly(shapely.make_valid(shapely.Polygon(q))) for q in keep]
            gs += [G.qpoly(shapely.make_valid(shapely.Polygon(m_["ring"])).buffer(
                MASS_CLEAR_M, join_style="mitre", mitre_limit=2.0))
                for m_ in inp.get("masses", ())]
            if gs and not add.is_empty:
                add = G.diff(add, G.union(gs))
            parts = [p for p in G.parts(add) if G.area1(p) >= CAR_MIN_M2]
            add = G.union(parts) if parts else None
        if add is None and not own:
            return None
        g = base if add is None else G.union([base, add])
        if own:
            g = G.diff(g, G.union([G.qpoly(shapely.make_valid(shapely.Polygon(o["ring"])))
                                   for o in own]))
        drawn = []
        for p in sorted(G.parts(g), key=lambda q: (G.qbounds(q), G.area1(q))):
            if G.area1(p) < CAR_MIN_M2:
                continue
            e = _despike(ccw([(c[0], c[1]) for c in p.exterior.coords[:-1]]))
            hs = [_despike(ccw([(c[0], c[1]) for c in h.coords[:-1]])[::-1])
                  for h in p.interiors]
            if len(e) < 3:
                continue
            # (paved through its small holes, as its outline's: two touching at a point
            # fold the triangulation)
            drawn.append((e, [h for h in hs if len(h) >= 3 and abs(_area(h)) >= HOLE_M2]))
    if (add is None and len(drawn) == 1 and not drawn[0][1] and
            {tuple(p) for p in drawn[0][0]} == {tuple(p) for p in cring}):
        return None       # (the owners only touch it)
    own_rings = [[(q[0], q[1]) for q in o["drawn"]] for o in own]
    seam = _edge_z([[(q[0], q[1], q[2]) for q in o["drawn"]] for o in own]) if own else None
    curb = _edge_z([[(x, y, zfun(x, y)) for x, y in cring]])
    vz = sf["vz"]
    hz_of: dict = {}
    for r, hs in drawn:
        for x, y in list(r) + [q for h in hs for q in h]:
            if (x, y) in hz_of:
                continue
            if seam is not None and any(_near((x, y), o, True, 0.015) for o in own_rings):
                z = seam(x, y)
            elif vz is not None and (x, y) in vz:
                z = vz[(x, y)]
            elif vz is None:
                z = zfun(x, y)
            else:
                z = curb(x, y)
            hz_of[(x, y)] = z

    def hz(x, y):
        z = hz_of.get((x, y))
        return z if z is not None else curb(x, y)
    paved = []
    if add is not None:
        for p_ in sorted(G.parts(add), key=lambda q: (G.qbounds(q), G.area1(q))):
            e = [(c[0], c[1]) for c in p_.exterior.coords[:-1]]
            paved.append([[C.m2(x), C.m2(y), C.m(hz(x, y) - inp["node_ground"] - ROAD_DZ)]
                          for x, y in e])
    return drawn, hz, paved


def _junction_barriers(mesh: Mesh, ring, legs, plan: dict, rows: dict, zfun):
    """#95: what a junction carries between its legs (`barriers.junction_plan`): a parapet
    round a raised junction's corner (along its sidewalk pad's property line where one is
    drawn, else its outline), a guard wall along an at-grade highway corner, a median
    barrier across."""
    from . import barriers as BR
    n = len(legs)
    at = {r["key"]: i for i, r in enumerate(legs)}
    keep = BR.Keepout(legs, plan.get("xwalks", ()), ring, plan.get("near"))
    parapet = BR.parapet_profile(0.0, "r")
    guard = BR.shifted(BR.JERSEY, BR.GUARD_IN_M)

    def draw(pts, prof, base=0.0):
        # (each part clear of the legs' carriageways and the crosswalks)
        offs = (min(t for t, _ in prof), sum(t for t, _ in prof) / len(prof),
                max(t for t, _ in prof))
        for part in BR.clip_line(pts, offs, keep):
            BR.draw_line(mesh, "concrete.barrier", part, prof, zfun, base=base)
    for c in plan.get("corners", ()):
        i = at.get(c["a"])
        if i is None or n < 2 or legs[(i + 1) % n]["key"] != c["b"]:
            continue
        a, b = legs[i], legs[(i + 1) % n]
        if a["exit"] is None or b["exit"] is None:
            continue
        if c["kind"] == "parapet" and i in rows:
            for line in rows[i]:
                draw(line, parapet, 0.15)
            continue
        ch = BR._chain(ring, a["exit"][1], b["exit"][1])
        if ch is not None:
            draw(ch, parapet if c["kind"] == "parapet" else guard)
    med = plan.get("median")
    if med:
        ends = [legs[at[k]] for k in med if k in at]
        if len(ends) == 2 and all(r["exit"] is not None for r in ends):
            pa, pb = (BR.median_end(ring, r["exit"], r["path"], r["h"]) for r in ends)
            draw([pa, pb], BR.JERSEY)


RUN_ROW_M = 3.0         # #89: a road row this far past its cut can reach back onto the outline
SHORT_ROAD_M = 12.0     # ... and every row of a road this short between its cuts (its far cut
                        # can lie on the outline of a junction that overlaps the other)


def _run_z(ring, r: dict, k: int) -> float:
    """#89: the height of an outline vertex on a leg's cut (`_cut_run`): the leg's at its
    cut where the road piece's end row lies on the cut edge (its two ends, when the edge
    spans the carriageway as `roads.Road._edge` takes it); else, where the vertex is a side
    point of one of the road piece's rows (its cut row, or a mitred row at a bend of its
    line within `RUN_ROW_M` past the cut, which reaches back over the cut where the road
    turns sharply), that row's height; else, past the cut beside the road (M17's shared
    pavement), the leg's height there; else the leg's at its cut. (The leg's height at the
    cut stood 2 to 40 cm off the road piece there on a steep leg.)"""
    n = len(ring)
    i = r["exit"][1]
    if k in (i, (i + 1) % n) and _spans(ring, r):
        return r["z"]
    p = ring[k]
    path, s0, h = r["path"], r["exit"][0], r["h"]
    rows = _road_rows(r)
    best = None
    for sv, vi in rows:
        x, y, nx, ny, kk = path.frame(sv, vi)
        for t in (-h, h):
            d = dist((x + nx * kk * t, y + ny * kk * t), p)
            if d <= 0.05 and (best is None or d < best[0]):
                best = (d, sv)
    if best is not None:
        return r["zs"](best[1]) if best[1] > s0 else r["z"]
    s_k, _ = path.project(p[0], p[1])
    return r["zs"](s_k) if s_k > s0 + 0.01 else r["z"]


def _road_rows(r: dict) -> list:
    """#89: the stations (s along the leg from its node, vertex index or None) of the leg's
    road piece's rows from its cut out to `RUN_ROW_M` past it (to its far cut where the
    road is under `SHORT_ROAD_M` between them), as `roads.Road.stations` lays them (the
    cut, the line's vertices, the height profiles' knots, and the first gap cut evenly at
    `roads.STEP_M`)."""
    from .roads import STEP_M
    path = r["path"]
    s0 = min(r["exit"][0], path.L)
    vs = {path.cum[q]: q for q in range(1, len(path.p) - 1)}
    far = r.get("far")
    short = far is not None and s0 + 1e-6 < far <= s0 + SHORT_ROAD_M and far < path.L - 1e-6
    lim = far if short else s0 + RUN_ROW_M
    marks = sorted([c for c in vs if c > s0 + 1e-6] +
                   [c for c in r.get("knots", ()) if s0 + 1e-6 < c < path.L - 1e-6] +
                   ([far] if short else []))
    out = [(s0, None)]
    nxt = marks[0] if marks else path.L
    gap = nxt - s0
    n = int(gap / STEP_M)
    if gap > STEP_M * n + 1e-9:
        n += 1
    cand = [s0 + gap * q / n for q in range(1, n)] + marks
    for c in sorted(set(cand)):
        if c > lim + 1e-9:
            break
        if c - out[-1][0] < 0.02:
            continue
        out.append((c, vs.get(c)))
    return out


def _spans(ring, r: dict) -> bool:
    """Whether a leg's exit edge spans its carriageway, as `roads.Road._edge` decides where
    its road piece's end row lies on it."""
    from .roads import CUT_TOL_M
    n = len(ring)
    i = r["exit"][1]
    a, b = ring[i], ring[(i + 1) % n]
    s = r["exit"][0]
    x, y = r["path"].point(s)
    tx, ty = r["path"].tangent(s)
    ta = -ty * (a[0] - x) + tx * (a[1] - y)
    tb = -ty * (b[0] - x) + tx * (b[1] - y)
    return abs(max(ta, tb) - r["h"]) <= CUT_TOL_M and abs(min(ta, tb) + r["h"]) <= CUT_TOL_M


def _cut_run(ring, r: dict) -> list[int]:
    """AG14: the outline vertices on a leg's cut: the two ends of the edge its centerline
    leaves by, and the vertices before and after them along the outline that lie across
    the leg within its half width of where its centerline crosses and within `CUT_ALONG_M`
    of that point along it (M2 splits a cut at the centerline; on a steep junction M18's
    curb may take another leg's height a few centimeters past the carriageway's corner,
    a step the road piece would meet)."""
    n = len(ring)
    i = r["exit"][1]
    if "at" not in r:
        return [i, (i + 1) % n]
    cx, cy = r["at"]
    tx, ty = r["tan"]

    def on(k):
        p = ring[k]
        ox, oy = p[0] - cx, p[1] - cy
        return abs(ox * tx + oy * ty) <= CUT_ALONG_M and \
            abs(-ox * ty + oy * tx) <= r["row"] + 0.05
    out = [i, (i + 1) % n]
    k = (i - 1) % n
    while k not in out and on(k):
        out.append(k)
        k = (k - 1) % n
    k = (i + 2) % n
    while k not in out and on(k):
        out.append(k)
        k = (k + 1) % n
    return out


def _with_corners(ring, legs: list, raw: list):
    """AG14: the outline with each leg's carriageway corners at its cut (as the road piece
    draws them, square across the leg) inserted where they lie on an outline edge within
    3 cm and not at a vertex; (ring, [((x, y), z)])."""
    pts = []
    by_id = {}
    for lg in raw:
        by_id.setdefault(lg["id"], []).append(lg)
    for r in legs:
        if "z" not in r or r.get("exit") is None:
            continue
        h = r["row"] - r["side"]
        if h <= 0.3:
            continue
        for lg in by_id.get(r["id"], ()):
            pts_ = lg["line"] if lg["at_start"] else lg["line"][::-1]
            try:
                path = Path(pts_)
            except ValueError:
                continue
            s = min(r["exit"][0], path.L)
            x, y = path.point(s)
            tx, ty = path.tangent(s)
            for sg in (1.0, -1.0):
                pts.append(((C.m(x - ty * h * sg), C.m(y + tx * h * sg)), r["z"]))
            # (#89: and the side points of its rows just past the cut, where the outline
            # runs on along the road's side: there they are its vertices at the road's
            # height, as at its corners)
            ends = pts[-2:]
            for sv, vi in _road_rows(r)[1:]:
                x, y, nx, ny, kk = path.frame(sv, vi)
                for sg in (1.0, -1.0):
                    q = (C.m(x + nx * kk * h * sg), C.m(y + ny * kk * h * sg))
                    if all(dist(q, e[0]) > 0.1 for e in ends):
                        pts.append((q, r["zs"](sv)))
            break
    if not pts:
        return ring, []
    out = list(ring)
    extra = []
    for (px, py), z in pts:
        n = len(out)
        best = None
        near = None
        for i in range(n):
            a, b = out[i], out[(i + 1) % n]
            if dist(a, (px, py)) < 0.05 or dist(b, (px, py)) < 0.05:
                near = a if dist(a, (px, py)) < 0.05 else b
                best = None
                break
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            if L2 <= 0.0:
                continue
            f = ((px - a[0]) * dx + (py - a[1]) * dy) / L2
            if not 0.0 < f < 1.0:
                continue
            d = abs((px - a[0]) * dy - (py - a[1]) * dx) / math.sqrt(L2)
            if d <= 0.03 and (best is None or d < best[0]):
                best = (d, i, (C.m2(a[0] + f * dx), C.m2(a[1] + f * dy)))
        if best is not None:
            _, i, q = best
            out.insert(i + 1, q)
            extra.append((q, z))
        elif near is not None:
            extra.append(((near[0], near[1]), z))     # (a vertex already there: its height)
    inserted = any(q not in ring for q, _ in extra)
    return (out if inserted else ring), extra


def _minus(sector, ring, holes, taken=(), block=None):
    """The sector polygon less the junction polygon (#82: and `block`) and the corners
    already made, as counterclockwise rings (citygen's snapped overlay), or None."""
    import shapely
    from shapely.geometry import Polygon

    from citygen import geom as G
    try:
        with G.canonical():
            a = G.qpoly(shapely.make_valid(Polygon(sector)))
            b = G.qpoly(shapely.make_valid(Polygon(ring, holes)))
            if block is not None:
                b = G.union([b, block])
            if taken:
                b = G.union([b] + [Polygon(t) for t in taken])
            d = G.diff(a, b)
            parts = G.parts(d)
    except (shapely.errors.GEOSException, ValueError):
        return None
    out = []
    for p in parts:
        r = _onto(ccw(list(p.exterior.coords)[:-1]), taken)
        if len(r) >= 3 and not p.interiors:
            out.append(r)
    out.sort(key=lambda r: (min(r), len(r)))
    return out


SNAP_M = 0.0075         # half a diagonal of the overlay's 1 cm grid


def _onto(ring, taken) -> list:
    """The ring without a vertex the overlay's grid put beside an earlier corner's edge:
    one within `SNAP_M` of the chord between its neighbors where that chord is an edge of
    an earlier corner. Rounded to the grid, the point where the new corner leaves that
    edge can fall a few millimeters inside the earlier one, a sliver of both (their
    shared edge running the same way in each)."""
    if not taken:
        return ring
    edges = {(r[k], r[(k + 1) % len(r)]) for r in taken for k in range(len(r))}
    out = list(ring)
    k = 0
    while k < len(out) and len(out) > 3:
        u, v, w = out[k - 1], out[k], out[(k + 1) % len(out)]
        if ((w, u) in edges or (u, w) in edges) and _near(v, [u, w], False, SNAP_M):
            del out[k]
            k = max(k - 1, 0)
            continue
        k += 1
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


def _chains(edges: list) -> list[list]:
    """Edges (p, q) joined end to start into polylines, each edge once: a line from each edge
    no other ends at (in the edges' order), then the closed loops. (#82: in any order: a
    corner drawn in parts gives its edges part by part, and two lines meeting end to end
    fold their end faces into each other.)"""
    starts: dict = {}
    for k, (p, _) in enumerate(edges):
        starts.setdefault(p, []).append(k)
    ends = {q for _, q in edges}
    used = [False] * len(edges)

    def run(k):
        line = [edges[k][0]]
        while k is not None:
            used[k] = True
            line.append(edges[k][1])
            k = next((c for c in starts.get(edges[k][1], ()) if not used[c]), None)
        return line
    out: list[list] = []
    for k, (p, _) in enumerate(edges):
        if not used[k] and p not in ends:
            out.append(run(k))
    for k in range(len(edges)):
        if not used[k]:
            out.append(run(k))
    return out


def _sectors(ring, P, legs, j) -> list:
    """The corners between neighboring legs: {"i" (its first leg's index), "sector" (from
    the node out to both legs' cut lines and round the property line), "row" (the property
    line), "sidewalk" (whether either leg has one)} or {"i", "skip": why}."""
    out: list = []
    n = len(legs)
    if n < 2 or j.get("shape") == "cul_de_sac":
        return out
    r_all = j.get("corner_radius_m", 6.0)
    N = len(ring)
    for i in range(n):
        a, b = legs[i], legs[(i + 1) % n]
        if a["exit"] is None or b["exit"] is None:
            continue
        side = not (a["side"] <= 0.0 and b["side"] <= 0.0)
        if _twins(a, b):
            out.append({"i": i, "skip": "twin legs", "sidewalk": side})
            continue
        ea, eb = a["exit"][1], b["exit"][1]
        if ea == eb:
            out.append({"i": i, "skip": "same edge", "sidewalk": side})
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
            out.append({"i": i, "skip": "chain", "sidewalk": side})
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
        Pa = (P[0] + cut_a * da[0], P[1] + cut_a * da[1])
        Pb = (P[0] + cut_b * db[0], P[1] + cut_b * db[1])
        sector = [P, Pa] + row + [Pb]
        if _bends(a, P, Ca) or _bends(b, P, Cb):
            # #82: a leg that bends before its cut (a curving avenue run on inside its
            # junction to the next node, one that turns inside it): the sector along its own
            # line and property line, not straight on from the node (a wedge 100 m long
            # beside a curving ramp, or a sliver where the leg turns away)
            if c is not None and len(row) >= 4:
                ka, kb = _along(a, P, Ca, a["row"], ta), _along(b, P, Cb, -b["row"], tb)
                if ka is not None and kb is not None:
                    (ca, oa), (cb, ob) = ka, kb
                    row = [oa[-1]] + oa[::-1][1:-1] + row[1:-1] + ob[1:-1] + [ob[-1]]
                    sector = ca + row + cb[::-1]
            else:
                got = _meet_along(a, P, Ca, b, Cb)
                if got is not None:
                    row, sector = got
        out.append({"i": i, "sector": sector, "row": row, "sidewalk": side})
    return out


BEND_M = 0.5            # #82: a leg bends where its line leaves its direction by this


def _bulb(ring, lg: dict) -> list:
    """#82: a cul-de-sac's sidewalk: a band of its leg's sidewalk width round the bulb (its
    outline grown by it), less the leg's right of way (its own sidewalks run up to the bulb
    there), as one corner [{"i", "sector", "row", "sidewalk", "less"}]; none where the leg
    has no sidewalk. (A bulb had none: the leg's sidewalks ran on into it, over its
    carriageway.)"""
    from citygen import geom as G
    if lg["side"] <= 0.0 or lg["exit"] is None:
        return []
    with G.canonical():
        bulb = G.qpoly(shapely.make_valid(shapely.Polygon(ring)))
        outer = G.qpoly(bulb.buffer(lg["side"], quad_segs=6, join_style="mitre",
                                    mitre_limit=2.0))
        parts = G.parts(outer)
        if not parts:
            return []
        outer = max(parts, key=lambda q: (G.area1(q), G.qbounds(q)))
        cor = G.qpoly(shapely.LineString(lg["path"].p).buffer(lg["row"], cap_style="flat"))
    sector = ccw([(c[0], c[1]) for c in outer.exterior.coords[:-1]])
    return [{"i": 0, "sector": sector, "row": sector + sector[:1], "sidewalk": True,
             "less": cor}]


def _twins(a: dict, b: dict) -> bool:
    """#82: two legs run side by side inside their junction to the same far node (both
    past `LONG_LEG_M`): the ground between them is the pavement they share, no corner."""
    pa, pb = a["path"].p[-1], b["path"].p[-1]
    return a["exit"][0] >= LONG_LEG_M and b["exit"][0] >= LONG_LEG_M and \
        abs(pa[0] - pb[0]) <= 0.05 and abs(pa[1] - pb[1]) <= 0.05


def _bends(lg: dict, P, C_) -> bool:
    """Whether a leg's line leaves its direction from the node by over `BEND_M` before its
    cut (the outline vertex C_ there)."""
    path, d = lg["path"], lg["d"]
    s_cut, _ = path.project(C_[0], C_[1])
    for q, sq in zip(path.p[1:-1], path.cum[1:-1]):
        if sq >= s_cut:
            break
        if abs((q[0] - P[0]) * d[1] - (q[1] - P[1]) * d[0]) > BEND_M:
            return True
    return False


def _meet_along(a: dict, P, Ca, b: dict, Cb):
    """#82: a corner between two legs one of which bends, with no fillet: leg a's property
    line (left) and leg b's (right) along their own lines from the node out to their cuts,
    joined where they cross (the crossing nearest a's node end), else end to end at the
    node; (row, sector) or None."""
    from shapely.ops import substring
    ka, kb = _along(a, P, Ca, a["row"], 0.0), _along(b, P, Cb, -b["row"], 0.0)
    if ka is None or kb is None:
        return None
    (ca, oa), (cb, ob) = ka, kb
    if len(oa) < 2 or len(ob) < 2:
        return None
    la, lb = shapely.LineString(oa), shapely.LineString(ob)
    x = la.intersection(lb)
    pts = [g for g in shapely.get_parts(x) if g.geom_type == "Point"] if not x.is_empty else []
    if pts:
        X = min(pts, key=lambda g: (la.project(g), g.x, g.y))
        ra = [(C.m2(q[0]), C.m2(q[1])) for q in
              substring(la, la.project(X), la.length).coords][::-1]
        rb = [(C.m2(q[0]), C.m2(q[1])) for q in
              substring(lb, lb.project(X), lb.length).coords]
        row = ra + rb[1:]
    else:
        row = oa[::-1] + ob
    return row, ca + row + cb[::-1]


def _along(lg: dict, P, C_, off: float, t0: float):
    """A leg's centerline from the node to its cut and its property line (offset `off`,
    left positive) from `t0` along it out to the cut, as point lists from the node out;
    None where the cut is not past t0."""
    path = lg["path"]
    s_cut, _ = path.project(C_[0], C_[1])
    if s_cut <= t0 + 0.5:
        return None
    center = [P] + [q for q, sq in zip(path.p[1:-1], path.cum[1:-1]) if sq < s_cut] + \
        [path.point(s_cut)]
    offs = []
    for sv, vi in path.stations(t0, s_cut, 1e9):
        x, y, nx, ny, k = path.frame(sv, vi)
        offs.append((C.m2(x + nx * k * off), C.m2(y + ny * k * off)))
    return center, offs


def _corners(mesh: Mesh, ring, holes, P, legs, j, style, zfun, rows_out=None, sectors=None,
             block=None, curbs=None, pads_out=None) -> list:
    """Sidewalk corners between neighboring legs; [made, skipped, why skipped];
    `rows_out` (#95) gets each drawn corner's outer edges along its property line (its
    pads' edges there, counterclockwise: the pad on their left), by its first leg's index.
    #82: `block` (shapely) is the carriageway as drawn where it is not the outline (less an
    overlapping junction's, with the connector lanes run off it) and the overlapping
    junctions' outlines, which no pad covers; `curbs` the rings the pads' curbs face;
    `zfun` the carriageway's height at the curb nearest a point (the pads stand 0.15 m
    over it); `pads_out` (#89) gets each pad drawn as a ring of (x, y, top)."""
    made = skipped = 0
    n = len(legs)
    if j.get("shape") == "cul_de_sac" and n == 1:
        # (#82: a turning bulb's sidewalk round it: its leg's sidewalks run up to it)
        sectors = _bulb(ring, legs[0])
        if not sectors:
            return [0, 0, {}]
    elif n < 2 or j.get("shape") == "cul_de_sac":
        return [0, 0, {}]
    if sectors is None:
        sectors = _sectors(ring, P, legs, j)
    if curbs is None:
        curbs = [ring] + list(holes)
    outer = [ring] if block is None else [c for c in curbs if c not in holes]
    why: dict[str, int] = {}
    taken: list = []          # earlier corners: a later one never overlaps them
    drawn: list = []
    pave = MT.paving(style["archetype"])
    curb_slot = MT.curb(style["archetype"])
    for sc in sectors:
        if not sc["sidewalk"]:
            continue
        if "skip" in sc:
            skipped += 1
            why[sc["skip"]] = why.get(sc["skip"], 0) + 1
            continue
        i, row = sc["i"], sc["row"]
        # the corner: the sector from the node out to both sidewalks' ends and round the
        # property line, less the carriageway (the junction polygon); a leg without a
        # sidewalk leaves at most a sliver, which is dropped
        blk = block
        if sc.get("less") is not None:
            blk = sc["less"] if blk is None else blk.union(sc["less"])
        parts = _minus(sc["sector"], ring, holes, taken, blk)
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
        drawn.append((parts, row, i))
    # faces along the pads' edges, in a second pass: an edge two pads share gets none
    uses: dict = {}
    for parts, _, _ in drawn:
        for r in parts:
            for k in range(len(r)):
                key = tuple(sorted((r[k], r[(k + 1) % len(r)])))
                uses[key] = uses.get(key, 0) + 1
    ends: set = set()
    for parts, row, i in drawn:
        drew = False
        edge: list = []         # (#95) the pads' edges on the property line, as drawn
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
            if pads_out is not None:
                pads_out.append([[C.m2(x), C.m2(y), C.m(zfun(x, y) + 0.15)] for x, y in r])
            for k in range(len(r)):
                p, q = r[k], r[(k + 1) % len(r)]
                mid = ((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0)
                if uses[tuple(sorted((p, q)))] == 1 and \
                        not any(_near(mid, c, True) for c in curbs) and _near(mid, row, False):
                    edge.append((p, q))
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
                if any(_near(mid, c, True) for c in curbs):
                    mesh.wall(curb_slot, p, q, zfun(*p), zfun(*p) + 0.15, zfun(*q),
                              zfun(*q) + 0.15)
                elif _near(mid, row, False):
                    mesh.wall(pave, p, q, zfun(*p) - ROAD_DZ - 0.02, zfun(*p) + 0.15,
                              zfun(*q) - ROAD_DZ - 0.02, zfun(*q) + 0.15)
        if drew:
            made += 1
            if rows_out is not None and edge:
                rows_out[i] = edge
        else:
            skipped += 1
    if rows_out is not None:
        # (#95: a corner's barrier only on those edges with open ground outside them: not
        # the outline, another corner's pad or a leg's right of way, where two corners'
        # pads abut along their property lines)
        pads = [r for parts, _, _ in drawn for r in parts]
        for i in sorted(rows_out):
            keep = [e for e in rows_out[i] if _open_out(e, outer, pads, legs)]
            if keep:
                rows_out[i] = _chains(keep)
            else:
                del rows_out[i]
    return [made, skipped, dict(sorted(why.items()))]


def _open_out(e, outer, pads, legs, out_m: float = 0.3) -> bool:
    """Whether the ground 0.3 m outside an edge (to its right: counterclockwise rings) is
    open: off the junction's outline (#82: the carriageway's outer rings as drawn and the
    overlapping junctions' outlines), every pad and every leg's right of way."""
    from .barriers import _inside
    (px, py), (qx, qy) = e
    dx, dy = qx - px, qy - py
    L = math.sqrt(dx * dx + dy * dy)
    if L < 1e-6:
        return False
    ox, oy = (px + qx) / 2.0 + dy / L * out_m, (py + qy) / 2.0 - dx / L * out_m
    if any(_inside(r, ox, oy) for r in outer) or any(_inside(r, ox, oy) for r in pads):
        return False
    for lg in legs:
        path = lg.get("path")
        if path is None:
            continue
        s, t = path.project(ox, oy)
        if abs(t) <= lg["row"] + 0.05 and 1e-6 < s < path.L - 1e-6:
            return False
    return True


__all__ = ["gather_sidewalk", "gather_crosswalk", "gather_junction", "math"]
