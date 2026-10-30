"""M14's decks (AG10): the slab of every deck per 256 m tile, its columns, and the stairs and
elevators of its light wells, each a piece keyed by M14's ids in place of the blockout's
object (`citygen/blockout.py`, `_decks`).

- **Slab** (`<deck>.slab.<tile>`): the deck's polygon in the tile (the holes under 2 m2 the
  union of its lots and streets leaves filled), its top the deck's top and its soffit
  `slab_m` under it, both over the ground the deck stands on: on M13's terrain the finished
  ground, or the base of a building on or under the deck where one stands (so the slab
  meets them), a level deck flat. Under it a ribbed soffit (downstand ribs every 3 m along
  the deck's long axis) or, in the planned eras, a coffered one (ribs both ways), the ribs
  stopping at the fascia and round the undercity buildings, whose tops meet the soffit
  (`assetgen/buildings/decks.py`); on its real edges (never a tile's) a fascia with an
  upstand over the top and a drip edge under the soffit, grime streaks down it and a stained
  band on the soffit along it; a rail on the upstand (posts with top, mid and bottom rails,
  glass panels in the wealthy eras) except where a building on the deck stands at the
  edge, a ramp or its junction meets it or a stair or elevator lands on it; soffit lights in
  two rows every 8 m over the ground streets under it and one over each junction; a
  colonnade where the edge passes over a park or plaza (a deeper edge beam and slim columns
  every 7.5 m off the park's paths); a steel collar round a building it is cut round.
- **Columns** (each its own piece, the joined blockout object of its district and tile): a
  round shaft from a square pier cap on the ground to a flared capital under a drop panel at
  the soffit, a grime band at its foot.
- **Stairs**: the two flights of a switchback (steps, stringers, handrails on posts), the
  half landing on two posts and a top landing across to the slab's edge.
- **Elevators**: a glazed shaft on a steel frame (a concrete core in the plain eras) from
  the ground to its machine room over the deck, a cab door at each level facing the street,
  and a bridge across to the slab's edge.

Geometry in world meters until the mesh kit rounds it to millimeters; every decision on
geometry is plain arithmetic in a fixed order or GEOS output on the 0.01 m grid, sorted.
"""

from __future__ import annotations

import math

import shapely
import shapely.ops
from shapely.geometry import LineString, Point, Polygon, box

from citygen import dmath as M
from citygen import geom as G

from .. import canon as C
from . import materials as MT
from .ctx import TILE_M, Ctx, bbox_center, dump, tile_name
from .kit import Mesh, ccw
from .path import Path
from .pieces import Out, Piece, maker, rnd

HOLE_FILL_M2 = 2.0      # holes the union of lots and streets leaves smaller than this are slab
LEVEL_TOL_M = 0.05      # a deck whose ground varies less than this is flat
DRAPE_M = 8.0           # where it is not: the slab in cells this size, each corner on its ground
FASCIA_T = 0.3          # the edge fascia's thickness
FASCIA_DROP = 0.45      # its drip edge under the soffit
UPSTAND = 0.15          # its upstand over the deck top, the rail on it
RAIL_H = 1.1
POST_STEP = 1.6
RIB_STEP = 3.0
RIB_W = 0.3
RIB_D = 0.45
STAIN_BAND = 0.9        # the stained band on the soffit along an edge
LIGHT_STEP = 8.0
LIGHT_EDGE = 1.5        # lights keep this far inside the slab
COLONNADE_STEP = 7.5
COLONNADE_T = 0.8       # the edge beam over a colonnade: as thick, and as deep under the soffit
COLONNADE_DROP = 0.9
COLONNADE_R = 0.3
PATH_GAP = 0.6          # colonnade columns keep this far off a park's paths
COLUMN_GAP = 3.0        # and off M14's own columns
COLLAR_REACH = 0.5      # a building this near the slab and over its soffit is cut round
COLLAR_GAP = 0.1
EDGE_NEAR = 0.6         # an edge with a building on the deck this near takes no rail
LINK_GAP = 1.6          # half the rail's opening where a stair or elevator lands
RAMP_PAD = 1.0          # past a ramp's walkways: no rail
# soffits: coffered (both ways) in the planned eras, ribbed in the rest; glass rails in the
# wealthy ones
COFFERED = ("corporate_glass", "clean_tech", "transit_modern", "aerospace", "suburban_modern")
GLASS_RAIL = ("corporate_glass", "clean_tech", "transit_modern", "aerospace",
              "suburban_modern", "mixed_modern")
# stairs and elevators
RISER_M = 0.175
STAIR_SLAB = 0.25
HAND_H = 1.0
ELEV_FRAME = 0.15
DOOR_W, DOOR_H = 1.4, 2.2
LANDING_T = 0.3


# ---------------------------------------------------------------------------
# Plain geometry
# ---------------------------------------------------------------------------

def _area2(ring) -> float:
    a = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def _rings(poly) -> tuple[list, list]:
    """A polygon's exterior (counterclockwise) and holes (clockwise), open, to the cm."""
    ext = [(C.m2(x), C.m2(y)) for x, y in list(poly.exterior.coords)[:-1]]
    if _area2(ext) < 0:
        ext = ext[::-1]
    holes = []
    for h in poly.interiors:
        r = [(C.m2(x), C.m2(y)) for x, y in list(h.coords)[:-1]]
        if _area2(r) > 0:
            r = r[::-1]
        holes.append(r)
    return ext, holes


def _inside(ring, x: float, y: float) -> bool:
    inside = False
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i - 1]
        x1, y1 = ring[i]
        if (y0 > y) != (y1 > y):
            if x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                inside = not inside
    return inside


def spans(rings, px: float, py: float, ux: float, uy: float) -> list[tuple[float, float]]:
    """Where the line p + t u runs inside the rings (even-odd over all of them): sorted
    (t0, t1) intervals, from the crossings with every ring edge in a fixed order."""
    ts = []
    for ring in rings:
        n = len(ring)
        for i in range(n):
            ax, ay = ring[i]
            bx, by = ring[(i + 1) % n]
            sa = ux * (ay - py) - uy * (ax - px)
            sb = ux * (by - py) - uy * (bx - px)
            if (sa > 0.0) == (sb > 0.0):
                continue
            # where the edge crosses the line, measured along u
            f = sa / (sa - sb)
            qx, qy = ax + (bx - ax) * f, ay + (by - ay) * f
            ts.append((qx - px) * ux + (qy - py) * uy)
    ts.sort()
    return [(ts[k], ts[k + 1]) for k in range(0, len(ts) - 1, 2)]


def _cut(iv: list, holes: list) -> list:
    """Intervals less other intervals."""
    out = []
    for a, b in iv:
        cur = [(a, b)]
        for c, d in holes:
            nxt = []
            for x, y in cur:
                if d <= x or c >= y:
                    nxt.append((x, y))
                    continue
                if c > x:
                    nxt.append((x, c))
                if d < y:
                    nxt.append((d, y))
            cur = nxt
        out += cur
    return out


def _miters(ring, d: float = 1.0, cap: float = 2.5) -> list[tuple[float, float]]:
    """Per vertex the inward (left of a counterclockwise ring, or of a clockwise hole: into
    the slab) offset for a unit distance, mitered, its length capped."""
    n = len(ring)
    out = []
    for i in range(n):
        p0, p1, p2 = ring[i - 1], ring[i], ring[(i + 1) % n]
        d0 = _unit(p1[0] - p0[0], p1[1] - p0[1])
        d1 = _unit(p2[0] - p1[0], p2[1] - p1[1])
        n0 = (-d0[1], d0[0])
        n1 = (-d1[1], d1[0])
        mx, my = n0[0] + n1[0], n0[1] + n1[1]
        L = math.hypot(mx, my)
        if L < 1e-9:
            out.append(n1)
            continue
        mx, my = mx / L, my / L
        k = 1.0 / max(mx * n1[0] + my * n1[1], 1.0 / cap)
        out.append((mx * k * d, my * k * d))
    return out


def _unit(dx: float, dy: float) -> tuple[float, float]:
    L = math.hypot(dx, dy)
    return (1.0, 0.0) if L < 1e-12 else (dx / L, dy / L)


def _seg_dist(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0.0 else min(max(((px - ax) * dx + (py - ay) * dy) / L2, 0.0), 1.0)
    return math.hypot(px - ax - dx * t, py - ay - dy * t)


def _line_dist(px, py, line) -> float:
    return min(_seg_dist(px, py, *a[:2], *b[:2]) for a, b in zip(line, line[1:]))


# ---------------------------------------------------------------------------
# The ground a deck stands on
# ---------------------------------------------------------------------------

class Ref:
    """The ground under a deck as its pieces read it: a constant on a level deck, else M13's
    finished ground (a window of its grid, bilinear as M13's `Field.at`) with the bases of
    the buildings on and under the deck over their footprints."""

    def __init__(self, rec: dict):
        self.level = rec.get("level")
        g = rec.get("grid")
        if g is not None:
            self.x0, self.y0, self.cell = g["x0"], g["y0"], g["cell"]
            self.rows = g["rows"]
            self.nx, self.ny = len(self.rows[0]), len(self.rows)
        self.bases = [(r, b) for r, b in rec.get("bases", [])]

    def ground(self, x: float, y: float) -> float:
        if self.level is not None:
            return self.level
        fx = min(max((x - self.x0) / self.cell, 0.0), self.nx - 1.000001)
        fy = min(max((y - self.y0) / self.cell, 0.0), self.ny - 1.000001)
        i, j = int(fx), int(fy)
        tx, ty = fx - i, fy - j
        a = self.rows
        h0 = a[j][i] * (1.0 - tx) + a[j][i + 1] * tx
        h1 = a[j + 1][i] * (1.0 - tx) + a[j + 1][i + 1] * tx
        return h0 * (1.0 - ty) + h1 * ty

    def __call__(self, x: float, y: float) -> float:
        """The ground the slab is measured from at (x, y)."""
        if self.level is not None:
            return self.level
        for ring, base in self.bases:
            if _inside(ring, x, y):
                return base
        return self.ground(x, y)


def _ref_rec(cx: Ctx, P, bases: list, x0, y0, x1, y1) -> dict:
    """The ground record of a deck (or of the box (x0, y0, x1, y1) of a piece of it): level,
    or a grid window and the bases over it."""
    gd = cx.ground
    if gd.flat:
        return {"level": 0.0}
    lv = _level(cx, P)
    if lv is not None:
        return {"level": lv}
    i0 = max(int(math.floor((x0 - gd.x0) / gd.cell)) - 1, 0)
    j0 = max(int(math.floor((y0 - gd.y0) / gd.cell)) - 1, 0)
    i1 = min(int(math.ceil((x1 - gd.x0) / gd.cell)) + 1, gd.nx - 1)
    j1 = min(int(math.ceil((y1 - gd.y0) / gd.cell)) + 1, gd.ny - 1)
    rows = [[C.m(float(gd.arr[j, i])) for i in range(i0, i1 + 1)] for j in range(j0, j1 + 1)]
    bb = box(x0 - 1.0, y0 - 1.0, x1 + 1.0, y1 + 1.0)
    near = [[[list(p) for p in ring], b] for ring, b in bases
            if Polygon(ring).intersects(bb)]
    return {"grid": {"x0": C.m(gd.x0 + i0 * gd.cell), "y0": C.m(gd.y0 + j0 * gd.cell),
                     "cell": gd.cell, "rows": rows}, "bases": near}


_LEVELS: dict = {}


def _level(cx: Ctx, P) -> float | None:
    """The deck's ground when it is level (within LEVEL_TOL_M on a 4 m grid under it): the
    most common value to the centimeter; else None."""
    key = (id(cx), P.wkb)
    if key in _LEVELS and _LEVELS[key][0] is cx:
        return _LEVELS[key][1]
    gd = cx.ground
    x0, y0, x1, y1 = P.bounds
    xs, ys = [], []
    y = math.floor(y0 / 4.0) * 4.0
    while y <= y1:
        x = math.floor(x0 / 4.0) * 4.0
        while x <= x1:
            xs.append(x)
            ys.append(y)
            x += 4.0
        y += 4.0
    inside = shapely.contains_xy(P, xs, ys)
    vals = [gd.at(x, y) for x, y, k in zip(xs, ys, inside.tolist()) if k]
    out = None
    if vals and max(vals) - min(vals) <= LEVEL_TOL_M:
        counts: dict = {}
        for v in vals:
            counts[C.m2(v)] = counts.get(C.m2(v), 0) + 1
        out = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))[0]
    _LEVELS[key] = (cx, out)
    return out


# ---------------------------------------------------------------------------
# Gather
# ---------------------------------------------------------------------------

class _Deck:
    """What every piece of a deck reads, worked out once."""

    def __init__(self, cx: Ctx, dk):
        m = cx.m
        self.dk = dk
        self.id = dk.id
        self.top, self.slab = float(dk.top_m), float(dk.slab_m)
        self.style = cx.style(dk.district_id)
        era = self.style["era"]
        self.soffit = "coffered" if era in COFFERED else "ribbed"
        self.rail = "glass" if era in GLASS_RAIL else "bars"
        P, through = slab_of(m, dk)
        self.poly = P
        with G.canonical():
            self.inner = G.qpoly(P.buffer(-FASCIA_T, join_style="mitre"))
        self.through = through
        self.ang = _obb(P)
        # buildings on and under it (their bases: the ground the slab meets over them)
        self.up = [b for b in m.buildings if b.level and b.attrs.get("deck") == dk.id]
        self.under = [b for b in m.buildings if b.attrs.get("deck_under") == dk.id]
        self.bases = []
        for b in sorted(self.up, key=lambda b: b.id) + sorted(self.under, key=lambda b: b.id):
            if getattr(b, "base_m", None) is not None and b.footprint is not None:
                self.bases.append(([tuple(p) for p in ccw(b.footprint.exterior)],
                                   C.m(float(b.base_m))))
        x0, y0, x1, y1 = P.bounds
        self.ref = _ref_rec(cx, P, self.bases, x0, y0, x1, y1)
        self.R = Ref(self.ref)
        self.flat = self.ref.get("level") is not None
        # its streets, ramps and junctions
        segs = [s for s in m.road_segments if s.attrs.get("deck") == dk.id]
        self.ramps = [s for s in segs if s.attrs.get("role") == "deck_ramp"]
        nodes = {s.start for s in segs} | {s.end for s in segs}
        self.junctions = [j for j in m.junctions if j.level and j.node_id in nodes]
        self.links = [s for s in m.structures if (s.attrs or {}).get("deck") == dk.id and
                      s.kind in ("stair", "elevator")]

    def z_top(self, x: float, y: float) -> float:
        return self.R(x, y) + self.top

    def z_soffit(self, x: float, y: float) -> float:
        return self.R(x, y) + self.top - self.slab


def slab_of(m, dk) -> tuple:
    """The slab's plan (the deck's polygon with the holes under HOLE_FILL_M2 filled, less
    every building it is cut round) and those buildings [(id, footprint)]: on the ground,
    not under it, reaching over its soffit, at most COLLAR_REACH from it."""
    key = (id(m), dk.id)
    if key in _SLABS and _SLABS[key][0] is m:
        return _SLABS[key][1]
    top, sd = float(dk.top_m), float(dk.slab_m)
    with G.canonical():
        P = G.from_model_poly(dk.polygon)
        ext, holes = _rings(P)
        keep = [h for h in holes if abs(_area2(h)) >= HOLE_FILL_M2]
        P = G.qpoly(Polygon(ext, keep))
        through = []
        x0, y0, x1, y1 = P.bounds
        r = COLLAR_REACH
        for b in sorted(m.buildings, key=lambda b: b.id):
            if b.level or b.attrs.get("deck_under") or b.footprint is None:
                continue
            if b.height_m <= top - sd:
                continue
            ext = b.footprint.exterior
            if min(p[0] for p in ext) > x1 + r or max(p[0] for p in ext) < x0 - r or \
                    min(p[1] for p in ext) > y1 + r or max(p[1] for p in ext) < y0 - r:
                continue
            f = G.from_model_poly(b.footprint)
            if f.distance(P) <= r:
                through.append((b.id, f))
        if through:
            P = G.qpoly(G.diff(P, G.union([f.buffer(COLLAR_GAP, join_style="mitre")
                                           for _, f in through])))
            ps = G.parts(P)
            P = max(ps, key=lambda p: (G.area1(p), p.wkb)) if ps else P
    _SLABS[key] = (m, (P, through))
    return P, through


_SLABS: dict = {}


def _obb(P) -> float:
    from citygen import massing as MS
    with G.canonical():
        return float(MS.obb_angle(P))


_DECKS: dict = {}


def deck_of(cx: Ctx, dk) -> _Deck:
    key = (id(cx), dk.id)
    if key not in _DECKS or _DECKS[key][0] is not cx:
        _DECKS[key] = (cx, _Deck(cx, dk))
    return _DECKS[key][1]


def gather(cx: Ctx) -> list[Piece]:
    """Every deck's pieces: its slab per tile, columns, stairs and elevators."""
    m = cx.m
    out = []
    if not m.decks:
        return out
    by_id = {dk.id: dk for dk in m.decks}
    for dk in sorted(m.decks, key=lambda d: d.id):
        D = deck_of(cx, dk)
        out += _slab_pieces(cx, D)
    for st in sorted(m.structures, key=lambda s: s.id):
        did = (st.attrs or {}).get("deck")
        if not did or did not in by_id:
            continue
        D = deck_of(cx, by_id[did])
        if st.kind == "column":
            out.append(_column_piece(cx, D, st))
        elif st.kind == "stair":
            out.append(_link_piece(cx, D, st, "deck_stair"))
        elif st.kind == "elevator":
            out.append(_link_piece(cx, D, st, "deck_elevator"))
    reset()
    return out


def reset() -> None:
    """Let go of the cached decks (they hold the model)."""
    _DECKS.clear()
    _SLABS.clear()
    _LEVELS.clear()


def is_deck_structure(st) -> bool:
    return bool((st.attrs or {}).get("deck")) and st.kind in ("column", "stair", "elevator")


# -- the slab ---------------------------------------------------------------------------

def _edge_kinds(cx: Ctx, D: _Deck, rings: list) -> list[list[str]]:
    """Per ring edge of the slab: `collar` round a building it is cut round, `plain` (no
    rail: a building on the deck at it, a ramp or its junction, a stair or elevator landing),
    `colonnade` over a park or plaza, else `rail`."""
    m = cx.m
    with G.canonical():
        parks = [G.from_model_poly(o.polygon) for o in m.open_spaces
                 if not o.level and o.kind in ("park", "plaza", "pocket_park", "green",
                                               "courtyard")
                 and not (o.attrs or {}).get("light_well")]
        park = G.union(parks) if parks else None
    if park is not None and not park.is_empty:
        shapely.prepare(park)
    ups = [G.from_model_poly(b.footprint) for b in D.up if b.footprint is not None]
    up = G.union(ups) if ups else None
    ramps = []
    for s in D.ramps:
        h = s.width_m / 2.0 + 2.0 + RAMP_PAD
        ramps.append(([tuple(p) for p in s.centerline], h))
    jps = [G.from_model_poly(j.polygon) for j in D.junctions]
    jn = G.union(jps) if jps else None
    lands = [tuple(p) for p in _landing_points(D)]
    out = []
    for ring in rings:
        kinds = []
        n = len(ring)
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
            mp = Point(mx, my)
            if any(f.distance(mp) <= COLLAR_GAP + 0.05 for _, f in D.through):
                kinds.append("collar")
                continue
            if up is not None and up.distance(mp) <= EDGE_NEAR:
                kinds.append("plain")
                continue
            if any(_line_dist(mx, my, line) <= h for line, h in ramps) or \
                    (jn is not None and jn.distance(mp) <= 0.5):
                kinds.append("plain")
                continue
            if any(_seg_dist(lx, ly, *a, *b) <= LINK_GAP for lx, ly in lands):
                kinds.append("plain")
                continue
            if park is not None:
                ux, uy = _unit(b[0] - a[0], b[1] - a[1])
                # (outside is to the right of the edge, the slab to its left)
                ox, oy = mx + uy * 1.0, my - ux * 1.0
                ix, iy = mx - uy * 1.0, my + ux * 1.0
                if shapely.contains_xy(park, ox, oy) and shapely.contains_xy(park, ix, iy):
                    kinds.append("colonnade")
                    continue
            kinds.append("rail")
        out.append(kinds)
    return out


def _landing_points(D: _Deck) -> list:
    """Where each stair and elevator lands on the slab's edge."""
    out = []
    for st in sorted(D.links, key=lambda s: s.id):
        e = _edge_point(D, st)
        if e is not None:
            out.append(e)
    return out


def _edge_point(D: _Deck, st):
    """The point of the slab's edge a stair's top landing or an elevator's bridge reaches:
    from its head (an elevator's middle) square to its flights toward the street, where that
    ray leaves the well (the slab's nearest edge)."""
    head = st.line[-1]
    if st.kind == "stair" and len(st.line) >= 4:
        a, b = st.line[1], st.line[2]
        n = _unit(a[0] - b[0], a[1] - b[1])          # (from the second flight to the first)
    else:
        q = shapely.ops.nearest_points(D.poly.boundary, Point(head[0], head[1]))[0]
        n = _unit(q.x - head[0], q.y - head[1])
    ray = LineString([(head[0], head[1]), (head[0] + n[0] * 30.0, head[1] + n[1] * 30.0)])
    with G.canonical():
        hit = D.poly.boundary.intersection(ray)
    pts = []
    for g in getattr(hit, "geoms", [hit]):
        if g.is_empty:
            continue
        for c in g.coords:
            pts.append((C.m2(c[0]), C.m2(c[1])))
    if not pts:
        return None
    return min(pts, key=lambda p: (round(math.hypot(p[0] - head[0], p[1] - head[1]), 4), p))


def _ground_streets(cx: Ctx, D: _Deck) -> tuple[list, list]:
    """The ground streets under the slab, clipped to it (LIGHT_EDGE inside): lines with
    their half carriageway, and the ground junctions whose middle it covers."""
    m = cx.m
    with G.canonical():
        inner = G.qpoly(D.poly.buffer(-LIGHT_EDGE, join_style="mitre"))
    lines = []
    for s in sorted(m.road_segments, key=lambda s: s.id):
        if s.level or "deck" in s.attrs or s.tunnel or s.bridge:
            continue
        ln = LineString(s.centerline)
        if not ln.intersects(D.poly):
            continue
        with G.canonical():
            part = G.line_inter(ln, inner)
        gs = [g for g in getattr(part, "geoms", [part]) if not g.is_empty and
              g.geom_type == "LineString" and g.length >= 4.0]
        for g in sorted(gs, key=lambda g: g.coords[0]):
            h = s.width_m / 2.0 - s.cross_section.sidewalk_m[0]
            lines.append([[[C.m2(x), C.m2(y)] for x, y in g.coords], C.m2(max(h, 1.5)), s.id])
    lines.sort(key=lambda r: (r[2], r[0][0]))
    jcs = []
    for j in sorted(m.junctions, key=lambda j: j.id):
        if j.level:
            continue
        c = bbox_center(j.polygon.exterior)
        if shapely.contains_xy(inner, c[0], c[1]):
            jcs.append(list(c))
    return lines, jcs


def _lights(lines, jcs) -> list:
    """Soffit lights: two rows every LIGHT_STEP over each ground street, one over each
    junction; [x, y, heading]."""
    out = []
    for pts, h, sid in lines:
        try:
            P = Path(pts)
        except ValueError:
            continue
        s = (P.L % LIGHT_STEP) / 2.0 + 0.5 * LIGHT_STEP * rnd(sid, "deck.light")
        while s <= P.L - 1.0:
            x, y, nx, ny, _ = P.frame(s)
            tx, ty = P.tangent(s)
            hd = C.deg(M.degrees(M.atan2(ty, tx)))
            for side in (-0.5, 0.5):
                out.append([C.m2(x + nx * h * side), C.m2(y + ny * h * side), hd])
            s += LIGHT_STEP
    for c in jcs:
        out.append([c[0], c[1], 0.0])
    # (one light where streets meet or overlap: the first in order)
    keep = []
    for li in out:
        if all(math.hypot(li[0] - k[0], li[1] - k[1]) >= 2.0 for k in keep):
            keep.append(li)
    return keep


def _colonnade(cx: Ctx, D: _Deck, rings, kinds) -> list:
    """Columns under the edge beam over a park or plaza: every COLONNADE_STEP along each run
    of colonnade edges, COLONNADE_T / 2 inside, off the park's paths, M14's columns, props,
    plants and buildings: [x, y, ground]."""
    m = cx.m
    walks = [(w.line, w.width_m / 2.0 + PATH_GAP) for w in m.walkways
             if not w.level and w.kind != "sidewalk" and all(abs(p[2]) < 0.5 for p in w.line)]
    cols = [bbox_center(s.footprint.exterior) for s in m.structures
            if (s.attrs or {}).get("deck") == D.id and s.kind == "column"]
    things = [(p.position[0], p.position[1]) for p in list(m.props) + list(m.plants)
              if not p.level]
    with G.canonical():
        foots = [G.from_model_poly(b.footprint) for b in m.buildings
                 if not b.level and b.footprint is not None]
    ftree = shapely.STRtree(foots) if foots else None
    bx0, by0, bx1, by1 = D.poly.bounds
    near_walks = [(ln, r) for ln, r in walks
                  if LineString([p[:2] for p in ln]).intersects(box(bx0, by0, bx1, by1))]
    out = []
    for ring, ks in zip(rings, kinds):
        n = len(ring)
        carry = 0.0
        for i in range(n):
            if ks[i] != "colonnade":
                carry = 0.0
                continue
            a, b = ring[i], ring[(i + 1) % n]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            ux, uy = _unit(b[0] - a[0], b[1] - a[1])
            s = COLONNADE_STEP / 2.0 - carry if carry else COLONNADE_STEP / 2.0
            while s < L:
                inx, iny = -uy, ux
                x = a[0] + ux * s + inx * COLONNADE_T / 2.0
                y = a[1] + uy * s + iny * COLONNADE_T / 2.0
                ok = all(_line_dist(x, y, ln) > r for ln, r in near_walks) and \
                    all(math.hypot(x - c[0], y - c[1]) > COLUMN_GAP for c in cols) and \
                    all(math.hypot(x - p[0], y - p[1]) > 1.0 for p in things)
                if ok and ftree is not None and len(ftree.query(Point(x, y).buffer(0.8),
                                                                  predicate="intersects")):
                    ok = False
                if ok:
                    out.append([C.m2(x), C.m2(y), C.m(cx.ground.at(x, y))])
                s += COLONNADE_STEP
            carry = (L - (s - COLONNADE_STEP)) if L > 0 else 0.0
    return out


def _slab_pieces(cx: Ctx, D: _Deck) -> list[Piece]:
    """One piece per blockout slab object of the deck (`<deck>.slab.<tile>`)."""
    ext, holes = _rings(D.poly)
    rings = [ext] + holes
    kinds = _edge_kinds(cx, D, rings)
    lines, jcs = _ground_streets(cx, D)
    lights = _lights(lines, jcs)
    colon = _colonnade(cx, D, rings, kinds)
    unders = []
    for b in sorted(D.under, key=lambda b: b.id):
        if b.footprint is not None:
            unders.append([[C.m2(p[0]), C.m2(p[1])] for p in ccw(b.footprint.exterior)])
    names = sorted(n for n in cx.keys.get(D.id, ()) if n.startswith(f"{D.id}.slab."))
    tiles = {n.rsplit(".", 1)[1]: n for n in names}
    # (a tile the slab reaches the blockout drew nothing in: a piece of its own too)
    with G.canonical():
        x0, y0, x1, y1 = D.poly.bounds
        for ix in range(math.floor(x0 / TILE_M), math.floor(x1 / TILE_M) + 1):
            for iy in range(math.floor(y0 / TILE_M), math.floor(y1 / TILE_M) + 1):
                t = tile_name(ix, iy)
                if t in tiles:
                    continue
                tb = box(ix * TILE_M, iy * TILE_M, (ix + 1) * TILE_M, (iy + 1) * TILE_M)
                if any(G.area1(p) > 0.5 for p in G.parts(G.inter(D.poly, tb))):
                    tiles[t] = f"{D.id}.slab.{t}"
    out = []
    for t in sorted(tiles):
        ix, iy = int(t[1:4]), int(t[4:7])
        tb = (ix * TILE_M, iy * TILE_M, (ix + 1) * TILE_M, (iy + 1) * TILE_M)
        with G.canonical():
            parts = [p for p in G.parts(G.inter(D.poly, box(*tb))) if G.area1(p) > 0.01]
        prs = []
        for p in parts:
            e, hs = _rings(p)
            prs.append({"exterior": [list(q) for q in e], "holes": [[list(q) for q in h]
                                                                   for h in hs]})
        edges = []
        for r, (ring, ks) in enumerate(zip(rings, kinds)):
            mit = _miters(ring)
            n = len(ring)
            for i in range(n):
                a, b = ring[i], ring[(i + 1) % n]
                mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
                if not (tb[0] <= mx < tb[2] and tb[1] <= my < tb[3]):
                    continue
                edges.append([r, i, list(a), list(b), [C.m(v) for v in mit[i]],
                              [C.m(v) for v in mit[(i + 1) % n]], ks[i]])
        if not prs and not edges:
            continue
        bx = (tb[0] - 2.0, tb[1] - 2.0, tb[2] + 2.0, tb[3] + 2.0)

        def inb(x, y):
            return bx[0] <= x <= bx[2] and bx[1] <= y <= bx[3]
        ref = D.ref if D.flat else _ref_rec(cx, D.poly, D.bases, *bx)
        # (the ribs: the slab less its fascia band along its real edges, near the tile)
        rib_rings = []
        if D.flat:
            with G.canonical():
                for p in G.parts(G.inter(D.inner, box(*bx))):
                    e, hs = _rings(p)
                    rib_rings += [[list(q) for q in e]] + [[list(q) for q in h] for h in hs]
        cxy = [C.m2((tb[0] + tb[2]) / 2.0), C.m2((tb[1] + tb[3]) / 2.0)]
        if prs:
            xs = [q[0] for p in prs for q in p["exterior"]]
            ys = [q[1] for p in prs for q in p["exterior"]]
            cxy = [C.m2((min(xs) + max(xs)) / 2.0), C.m2((min(ys) + max(ys)) / 2.0)]
        inputs = {"deck": D.id, "top": D.top, "slab": D.slab, "ref": ref,
                  "parts": prs, "edges": edges, "tile_box": list(tb), "rib_rings": rib_rings,
                  "soffit": D.soffit, "rail": D.rail, "angle": C.m(D.ang * 1000.0) / 1000.0,
                  "grid_origin": [C.m2(D.poly.bounds[0]), C.m2(D.poly.bounds[1])],
                  "paving": MT.paving(D.style["archetype"]), "grime": D.style["grime"],
                  "unders": [u for u in unders if any(inb(*q) for q in u)],
                  "lights": [li for li in lights if tb[0] <= li[0] < tb[2] and
                             tb[1] <= li[1] < tb[3]],
                  "colonnade": [c for c in colon if tb[0] <= c[0] < tb[2] and
                                tb[1] <= c[1] < tb[3]],
                  "origin": cxy}
        name = tiles[t]
        out.append(Piece(name, "street.deck.slab", "deck_slab", t,
                         [name] if name in names else [], inputs, covers=[D.id]))
    return out


# -- columns, stairs and elevators ----------------------------------------------------------

def _column_piece(cx: Ctx, D: _Deck, st) -> Piece:
    ring = st.footprint.exterior
    c = bbox_center(ring)
    r = max(math.hypot(p[0] - c[0], p[1] - c[1]) for p in ring)
    inside = any(_inside([tuple(p) for p in b.footprint.exterior], c[0], c[1])
                 for b in D.under if b.footprint is not None)
    inputs = {"col": st.id, "origin": list(c), "r": C.m(r),
              "z0": C.m(cx.ground.at(*c)) if not cx.ground.flat else 0.0,
              "z1": C.m(D.z_soffit(*c)), "angle": C.m(D.ang * 1000.0) / 1000.0,
              "soffit": D.soffit, "in_building": inside}
    return Piece(st.id, "street.deck.column", "deck_column", cx.tile_for(st.id, ring),
                 cx.keys.get(st.id, []), inputs)


def _link_piece(cx: Ctx, D: _Deck, st, mk: str) -> Piece:
    fp = st.footprint.exterior
    c = bbox_center(fp)
    gd = cx.ground
    line = [[C.m2(p[0]), C.m2(p[1]), C.m(p[2])] for p in st.line]
    ground = [C.m(gd.at(p[0], p[1])) if not gd.flat else 0.0 for p in st.line]
    tops = [C.m(D.z_top(p[0], p[1])) for p in st.line]
    e = _edge_point(D, st)
    inputs = {"st": dump(st), "line": line, "ground": ground, "tops": tops,
              "edge": list(e) if e is not None else None, "origin": list(c),
              "era": D.style["era"], "rail": D.rail,
              "edge_top": C.m(D.z_top(*e)) if e is not None else None}
    kind = "street.deck.stair" if mk == "deck_stair" else "street.deck.elevator"
    return Piece(st.id, kind, mk, cx.tile_for(st.id, fp), cx.keys.get(st.id, []), inputs)


# ---------------------------------------------------------------------------
# Make: the slab
# ---------------------------------------------------------------------------

def _split(x0, y0, x1, y1, n):
    """n + 1 points evenly from (x0, y0) to (x1, y1)."""
    return [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(n + 1)]


@maker("deck_slab", 1)
def make_slab(inp: dict) -> Out:
    R = Ref(inp["ref"])
    top, sd = inp["top"], inp["slab"]
    mesh = Mesh(inp["origin"])

    def zt(x, y):
        return R(x, y) + top

    def zs(x, y):
        return R(x, y) + top - sd
    pave = inp["paving"]
    notes = {"ribs": 0, "lights": len(inp["lights"]), "colonnade": len(inp["colonnade"])}
    # top and soffit
    for p in inp["parts"]:
        ext = [tuple(q) for q in p["exterior"]]
        holes = [[tuple(q) for q in h] for h in p["holes"]]
        if R.level is not None:
            mesh.poly(pave, ext, holes, z=top + R.level)
            mesh.poly("concrete.soffit", ext, holes, z=top + R.level - sd, up=False)
        else:
            for cell_ext, cell_holes in _cells(ext, holes):
                mesh.poly(pave, cell_ext, cell_holes, zfun=zt)
                mesh.poly("concrete.soffit", cell_ext, cell_holes, zfun=zs, up=False)
    # ribs and coffers (on a level deck), stopping at the fascia and round the undercity
    if R.level is not None and inp["parts"]:
        notes["ribs"] = _ribs(mesh, inp, top + R.level - sd)
    # edges
    for r, i, a, b, ma, mb, kind in inp["edges"]:
        _edge(mesh, inp, R, top, sd, tuple(a), tuple(b), tuple(ma), tuple(mb), kind, r, i)
    _rails(mesh, inp, R, top)
    # soffit lights (and what hangs lowest over the ground streets: their clearance)
    clear = None
    for x, y, hd in inp["lights"]:
        z = zs(x, y) - RIB_D
        c = z - 0.125 - R.ground(x, y)
        clear = c if clear is None else min(clear, c)
        mesh.box("steel.painted", x, y, z - 0.12, 1.4, 0.35, 0.12 + RIB_D, hd)
        h = M.radians(hd)
        ux, uy = M.cos(h), M.sin(h)
        vx, vy = -uy, ux
        q = [(x - ux * 0.6 - vx * 0.12, y - uy * 0.6 - vy * 0.12),
             (x + ux * 0.6 - vx * 0.12, y + uy * 0.6 - vy * 0.12),
             (x + ux * 0.6 + vx * 0.12, y + uy * 0.6 + vy * 0.12),
             (x - ux * 0.6 + vx * 0.12, y - uy * 0.6 + vy * 0.12)]
        mesh.poly("light.cool", q, z=z - 0.125, up=False)
    # colonnade columns under the edge beam
    for x, y, g in inp["colonnade"]:
        zb = zs(x, y) - COLONNADE_DROP
        mesh.box("concrete.column", x, y, g - 0.05, 0.9, 0.9, 0.35, inp["angle"] * 180.0 / math.pi)
        mesh.cylinder("concrete.column", x, y, COLONNADE_R, g + 0.3, zb - 0.35, n=12, top=False)
        mesh.cylinder("concrete.column", x, y, COLONNADE_R, zb - 0.35, zb, n=12, top=False,
                      r1=COLONNADE_R + 0.15)
    if clear is not None:
        notes["clear_m"] = C.m(clear)
    if not mesh.triangles:
        return Out(empty="no slab in the tile")
    return Out(mesh=mesh, notes={"deck": notes})


def _cells(ext, holes):
    """The polygon cut into DRAPE_M cells (on terrain that is not level), each as rings."""
    with G.canonical():
        P = G.qpoly(Polygon(ext, holes))
        x0, y0, x1, y1 = P.bounds
        out = []
        for j in range(int(math.floor(y0 / DRAPE_M)), int(math.ceil(y1 / DRAPE_M))):
            for i in range(int(math.floor(x0 / DRAPE_M)), int(math.ceil(x1 / DRAPE_M))):
                cb = box(i * DRAPE_M, j * DRAPE_M, (i + 1) * DRAPE_M, (j + 1) * DRAPE_M)
                for p in G.parts(G.inter(P, cb)):
                    if G.area1(p) > 0.001:
                        out.append(_rings(p))
    return out


def _ribs(mesh: Mesh, inp: dict, z: float) -> int:
    """Downstand ribs along the deck's long axis every RIB_STEP (coffered: both ways, the
    cross ribs 5 cm shallower), within the tile, the slab less its fascia band and the
    undercity buildings' footprints."""
    a = inp["angle"]
    ux, uy = math.cos(a), math.sin(a)
    tb = inp["tile_box"]
    rings = [[tuple(q) for q in r] for r in inp["rib_rings"]]
    if not rings:
        return 0
    unders = [[tuple(q) for q in u] for u in inp["unders"]]
    ox, oy = inp["grid_origin"]
    n = 0
    dirs = [(ux, uy, RIB_D)]
    if inp["soffit"] == "coffered":
        dirs.append((-uy, ux, RIB_D - 0.05))
    x0, y0, x1, y1 = tb
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for dx, dy, depth in dirs:
        vx, vy = -dy, dx
        vs = [(cx_ - ox) * vx + (cy_ - oy) * vy for cx_, cy_ in corners]
        k0 = int(math.floor(min(vs) / RIB_STEP))
        k1 = int(math.ceil(max(vs) / RIB_STEP))
        for k in range(k0, k1 + 1):
            v = (k + 0.5) * RIB_STEP
            px, py = ox + vx * v, oy + vy * v
            iv = spans(rings, px, py, dx, dy)
            if not iv:
                continue
            # (within the tile: its box along the line)
            lo, hi = -math.inf, math.inf
            for c, d, q in ((dx, px, (x0, x1)), (dy, py, (y0, y1))):
                if abs(c) < 1e-12:
                    if not (q[0] <= d < q[1]):
                        lo, hi = 1.0, 0.0
                    continue
                t0, t1 = (q[0] - d) / c, (q[1] - d) / c
                lo, hi = max(lo, min(t0, t1)), min(hi, max(t0, t1))
            if lo >= hi:
                continue
            iv = _cut(iv, [(-math.inf, lo), (hi, math.inf)])
            holes = []
            for u in unders:
                for c, d in spans([u], px, py, dx, dy):
                    holes.append((c - 0.15, d + 0.15))
            for c, d in _cut(iv, holes):
                if d - c < 0.6:
                    continue
                m = (c + d) / 2.0
                mesh.obox("concrete.soffit", px + dx * m, py + dy * m, z - depth, d - c,
                          RIB_W, depth, dx, dy, bottom=True)
                n += 1
    return n


def _edge(mesh: Mesh, inp: dict, R: Ref, top: float, sd: float, a, b, ma, mb, kind: str,
          r: int, i: int) -> None:
    """The fascia (or collar, or a colonnade's edge beam) along one edge, its grime streaks
    and the stained band on the soffit inside it."""
    t = COLONNADE_T if kind == "colonnade" else FASCIA_T
    drop = {"colonnade": COLONNADE_DROP, "collar": 0.3}.get(kind, FASCIA_DROP)
    up = UPSTAND if kind in ("rail", "colonnade") else 0.0
    slot = "steel.painted" if kind == "collar" else "concrete.fascia"
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L < 0.005:
        return
    n = 1 if R.level is not None else max(1, int(math.ceil(L / DRAPE_M)))
    ps = _split(a[0], a[1], b[0], b[1], n)
    qs = [(x + (ma[0] + (mb[0] - ma[0]) * k / n) * t, y + (ma[1] + (mb[1] - ma[1]) * k / n) * t)
          for k, (x, y) in enumerate(ps)]
    for k in range(n):
        p0, p1, q0, q1 = ps[k], ps[k + 1], qs[k], qs[k + 1]
        z0, z1 = R(*p0) + top, R(*p1) + top
        s0, s1 = z0 - sd, z1 - sd
        # outer face, down to the drip edge and up to the upstand
        mesh.wall(slot, p0, p1, s0 - drop, z0 + up, s1 - drop, z1 + up)
        # the drip edge's underside, and the downstand's inner face up to the soffit
        mesh.quad(slot, (*p0, s0 - drop), (*q0, s0 - drop), (*q1, s1 - drop), (*p1, s1 - drop))
        mesh.wall(slot, q1, q0, s1 - drop, s1, s0 - drop, s0)
        if up:
            mesh.quad(slot, (*p0, z0 + up), (*p1, z1 + up), (*q1, z1 + up), (*q0, z0 + up))
            mesh.wall(slot, q1, q0, z1, z1 + up, z0, z0 + up)
    if kind == "collar":
        return
    # grime streaks down the fascia from its top, and the stained soffit band inside it
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    ox_, oy_ = uy * 0.004, -ux * 0.004
    s = 0.6 * rnd(inp["deck"], r, i, "streak")
    k = 0
    while s < L - 0.3:
        w = 0.25 + 0.7 * rnd(inp["deck"], r, i, k, "w")
        e = min(s + w, L - 0.05)
        if rnd(inp["deck"], r, i, k, "on") < 0.35 + 0.5 * inp["grime"]:
            pa = (a[0] + ux * s + ox_, a[1] + uy * s + oy_)
            pb = (a[0] + ux * e + ox_, a[1] + uy * e + oy_)
            za, zb = R(*pa) + top - sd - drop, R(*pb) + top - sd - drop
            hgt = (sd + drop) * (0.3 + 0.65 * rnd(inp["deck"], r, i, k, "h"))
            mesh.wall("stain", pa, pb, za, za + hgt, zb, zb + hgt)
        s = e + 0.4 + 2.5 * rnd(inp["deck"], r, i, k, "gap")
        k += 1
    d0, d1 = t, t + STAIN_BAND
    for k in range(n):
        p0, p1 = ps[k], ps[k + 1]
        f0, f1 = k / n, (k + 1) / n
        m0 = (ma[0] + (mb[0] - ma[0]) * f0, ma[1] + (mb[1] - ma[1]) * f0)
        m1 = (ma[0] + (mb[0] - ma[0]) * f1, ma[1] + (mb[1] - ma[1]) * f1)
        q = [(p0[0] + m0[0] * d0, p0[1] + m0[1] * d0), (p1[0] + m1[0] * d0, p1[1] + m1[1] * d0),
             (p1[0] + m1[0] * d1, p1[1] + m1[1] * d1), (p0[0] + m0[0] * d1, p0[1] + m0[1] * d1)]
        zz = [R(*p0) + top - sd - 0.004, R(*p1) + top - sd - 0.004]
        mesh.quad("stain", (*q[0], zz[0]), (*q[3], zz[0]), (*q[2], zz[1]), (*q[1], zz[1]))


def _rails(mesh: Mesh, inp: dict, R: Ref, top: float) -> None:
    """The rail on the upstand of every run of `rail` edges: posts every POST_STEP, top, mid
    and bottom rails, glass panels between the posts in the wealthy eras."""
    runs = []
    cur = None
    for r, i, a, b, ma, mb, kind in inp["edges"]:
        if kind != "rail":
            cur = None
            continue
        pa = (a[0] + ma[0] * FASCIA_T / 2.0, a[1] + ma[1] * FASCIA_T / 2.0)
        pb = (b[0] + mb[0] * FASCIA_T / 2.0, b[1] + mb[1] * FASCIA_T / 2.0)
        if cur is not None and cur["r"] == r and cur["i"] == i - 1:
            cur["pts"].append(pb)
            cur["i"] = i
        else:
            cur = {"r": r, "i": i, "pts": [pa, pb]}
            runs.append(cur)
    glass = inp["rail"] == "glass"
    posts: set = set()
    for run in runs:
        try:
            P = Path(run["pts"])
        except ValueError:
            continue
        if P.L < 0.3:
            continue
        frames = []
        for s, vi in P.stations(0.0, P.L, 4.0 if R.level is None else 1e9):
            x, y, nx, ny, k = P.frame(s, vi)
            frames.append((x, y, R(x, y) + top + UPSTAND, nx, ny, k, s))
        if len(frames) < 2:
            continue
        for z0, z1, w in ((RAIL_H - 0.05, RAIL_H, 0.06), (0.5, 0.54, 0.04), (0.08, 0.12, 0.04)):
            if glass and z0 < 0.6:
                continue
            mesh.sweep("steel.painted", frames, [(w / 2.0, z0), (w / 2.0, z1), (-w / 2.0, z1),
                                                 (-w / 2.0, z0)], closed=True)
        if glass:
            mesh.sweep("glass.panel", frames, [(0.0, 0.05), (0.0, RAIL_H - 0.06)])
        npost = max(1, int(math.ceil(P.L / POST_STEP)))
        for k in range(npost + 1):
            s = P.L * k / npost
            x, y = P.point(s)
            key = (round(x * 20.0), round(y * 20.0))
            if key in posts:
                continue                # (where two runs meet: one post)
            posts.add(key)
            tx, ty = P.tangent(min(s, P.L - 1e-6))
            mesh.obox("steel.painted", x, y, R(x, y) + top + UPSTAND, 0.07, 0.07, RAIL_H,
                      tx, ty)


# ---------------------------------------------------------------------------
# Make: columns, stairs, elevators
# ---------------------------------------------------------------------------

@maker("deck_column", 1)
def make_column(inp: dict) -> Out:
    """A round shaft on a square pier cap, a flared capital and a drop panel under the
    soffit (none of them inside an undercity building, where the shaft alone stands)."""
    x, y = inp["origin"]
    r, z0, z1 = inp["r"], inp["z0"], inp["z1"]
    ang = inp["angle"] * 180.0 / math.pi
    mesh = Mesh(inp["origin"])
    if inp["in_building"]:
        mesh.cylinder("concrete.column", x, y, r, z0, z1, n=12, top=False)
        return Out(mesh=mesh)
    drop_z = z1 - RIB_D - 0.3
    mesh.box("concrete.column", x, y, z0 - 0.1, 1.4, 1.4, 0.45, ang)
    mesh.cylinder("concrete.column", x, y, r, z0 + 0.35, drop_z - 0.9, n=16, top=False)
    mesh.cylinder("concrete.column", x, y, r, drop_z - 0.9, drop_z, n=16, top=False,
                  r1=r * 2.0)
    mesh.box("concrete.column", x, y, drop_z, 2.2, 2.2, z1 - drop_z, ang, bottom=True)
    # grime at the foot: splashes up the shaft
    mesh.cylinder("stain", x, y, r + 0.004, z0 + 0.35, z0 + 0.35 + 0.6 + 0.5 * rnd(
        inp["col"], "grime"), n=16, top=False)
    return Out(mesh=mesh)


def _frame(line):
    """A stair's axes from its line (foot, the two ends of its half landing, head): along
    its first flight, and across from its first flight to its second."""
    f, a, b = line[0], line[1], line[2]
    t = _unit(a[0] - f[0], a[1] - f[1])
    n = _unit(b[0] - a[0], b[1] - a[1])
    return t, n


@maker("deck_stair", 1)
def make_stair(inp: dict) -> Out:
    """Two flights of a switchback (each step a block on a sloped soffit, stringers and
    handrails), the half landing on two posts, and a top landing across to the slab."""
    line = inp["line"]
    mesh = Mesh(inp["origin"])
    if len(line) < 4:
        return Out(empty="no flights")
    st = inp["st"]
    (tx, ty), (nx, ny) = _frame(line)
    gap = math.hypot(line[2][0] - line[1][0], line[2][1] - line[1][1])
    fp = st["footprint"]["exterior"]
    acr = [(p[0] - line[1][0]) * nx + (p[1] - line[1][1]) * ny for p in fp]
    W = max((max(acr) - min(acr)) - gap, 1.2)
    zf = inp["ground"][0]
    zh = inp["tops"][-1]
    zm = (zf + zh) / 2.0
    foot, mid1, mid2, head = [tuple(p[:2]) for p in line[:4]]
    _flight(mesh, foot, mid1, zf, zm, W, inp)
    _flight(mesh, mid2, head, zm, zh, W, inp)
    # the half landing, past the flights' ends by half a width, on two posts
    ux, uy = tx, ty
    c0 = (mid1[0] - nx * W / 2.0, mid1[1] - ny * W / 2.0)
    c1 = (mid2[0] + nx * W / 2.0 + ux * W / 2.0, mid2[1] + ny * W / 2.0 + uy * W / 2.0)
    ring = [c0, (c0[0] + ux * W / 2.0, c0[1] + uy * W / 2.0), c1,
            (mid2[0] + nx * W / 2.0, mid2[1] + ny * W / 2.0)]
    mesh.prism("concrete", ccw(ring), zm - LANDING_T, zm, bottom=True)
    for px, py in ((c0[0] + ux * (W / 2.0 - 0.2) + nx * 0.2, c0[1] + uy * (W / 2.0 - 0.2) + ny * 0.2),
                   (c1[0] - ux * 0.2 - nx * 0.2, c1[1] - uy * 0.2 - ny * 0.2)):
        mesh.box("steel.painted", px, py, zf, 0.2, 0.2, zm - LANDING_T - zf, 0.0)
    _guard(mesh, [(c0[0] + ux * W / 2.0, c0[1] + uy * W / 2.0), c1], zm)
    # the top landing: from the head across to the slab's edge
    e = inp.get("edge")
    if e is not None and math.hypot(e[0] - head[0], e[1] - head[1]) > 0.05:
        ez = inp.get("edge_top") or zh
        mesh.prism("concrete", ccw(_rect(head, e, tx, ty, W)), min(zh, ez) - LANDING_T,
                   max(zh, ez), bottom=True)
    return Out(mesh=mesh, notes={"link": _reach(mesh, inp, zf, zh)})


def _reach(mesh: Mesh, inp: dict, low: float, high: float) -> dict:
    """What the deck check reads of a stair or elevator: the ground and deck top it should
    join, how far its mesh reaches down and up, and whether it lands on the slab's edge."""
    lo, hi = mesh.bounds_mm()
    return {"ground": C.m(inp["ground"][0]), "top": C.m(inp["tops"][-1]),
            "low": C.m(lo[2] / 1000.0) if lo[0] is not None else None,
            "high": C.m(high), "mesh_high": C.m(hi[2] / 1000.0) if hi[0] is not None else None,
            "edge": inp.get("edge") is not None, "low_at": C.m(low)}


def _rect(head, e, tx, ty, W):
    """The top landing's plan: the head's width W along the flight (back past the head by W)
    and across from the head to the slab's edge e."""
    hx, hy = head
    dx, dy = e[0] - hx, e[1] - hy
    nxv, nyv = -ty, tx
    d = dx * nxv + dy * nyv          # (how far across: the edge square to the flight)
    if d < 0:
        nxv, nyv, d = -nxv, -nyv, -d
    back = (hx - tx * W, hy - ty * W)
    ahead = (hx, hy)
    w2 = W / 2.0
    p0 = (back[0] - nxv * w2, back[1] - nyv * w2)
    p1 = (ahead[0] - nxv * w2, ahead[1] - nyv * w2)
    p2 = (ahead[0] + nxv * (d + 0.05), ahead[1] + nyv * (d + 0.05))
    p3 = (back[0] + nxv * (d + 0.05), back[1] + nyv * (d + 0.05))
    return [p0, p1, p2, p3]


def _flight(mesh: Mesh, a, b, za: float, zb: float, W: float, inp: dict) -> None:
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L < 0.3:
        return
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    vx, vy = -uy, ux
    rise = zb - za
    n = max(1, int(math.ceil(abs(rise) / RISER_M)))
    run = L / n
    hs = rise / n
    for k in range(n):
        s = run * (k + 0.5)
        cx_, cy_ = a[0] + ux * s, a[1] + uy * s
        zt = za + hs * (k + 1)
        mesh.obox("concrete", cx_, cy_, zt - abs(hs) - STAIR_SLAB, run, W, abs(hs) + STAIR_SLAB,
                  ux, uy, bottom=True)
    # stringers and handrails on both sides, posts every 1.5 m
    for side in (-1.0, 1.0):
        ox, oy = vx * side * (W / 2.0 + 0.06), vy * side * (W / 2.0 + 0.06)
        p = (a[0] + ox, a[1] + oy, za + 0.1)
        q = (b[0] + ox, b[1] + oy, zb + 0.1)
        mesh.beam("steel.painted", (p[0], p[1], p[2] - 0.25), (q[0], q[1], q[2] - 0.25), 0.1,
                  0.45)
        mesh.beam("steel.painted", (p[0], p[1], p[2] + HAND_H), (q[0], q[1], q[2] + HAND_H),
                  0.05, 0.05)
        npost = max(1, int(math.ceil(L / 1.5)))
        for k in range(npost + 1):
            f = k / npost
            x = a[0] + ox + (b[0] - a[0]) * f
            y = a[1] + oy + (b[1] - a[1]) * f
            z = za + rise * f
            mesh.obox("steel.painted", x, y, z, 0.05, 0.05, HAND_H + 0.1, ux, uy)


def _guard(mesh: Mesh, pts, z: float) -> None:
    """A guard rail along a landing's open edge."""
    a, b = pts
    mesh.beam("steel.painted", (a[0], a[1], z + HAND_H), (b[0], b[1], z + HAND_H), 0.05, 0.05)
    for p in (a, b):
        mesh.box("steel.painted", p[0], p[1], z, 0.05, 0.05, HAND_H, 0.0)


@maker("deck_elevator", 1)
def make_elevator(inp: dict) -> Out:
    """The shaft from the ground to its machine room over the deck: glass between a steel
    frame (a concrete core in the plain eras), a cab door at the ground and at the deck,
    both facing the street, and a bridge across to the slab's edge."""
    st = inp["st"]
    ring = ccw(st["footprint"]["exterior"])
    mesh = Mesh(inp["origin"])
    zg = inp["ground"][0]
    zd = inp["tops"][-1]
    z1 = zd + max(st["z1_m"] - st["z0_m"] - (inp["line"][-1][2] - inp["line"][0][2]), 2.5)
    glass = inp["rail"] == "glass"
    cxy = inp["origin"]
    e = inp.get("edge")
    # the face toward the street: the one the edge point lies beyond
    n = len(ring)
    face = 0
    if e is not None:
        best = None
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
            d = math.hypot(e[0] - mx, e[1] - my)
            if best is None or d < best:
                best, face = d, i
    if glass:
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            mesh.wall("glass.panel", a, b, zg, zd + 2.4, zg, zd + 2.4)
        for p in ring:
            # (corner posts, inset by half their size)
            px, py = p[0] + (cxy[0] - p[0]) * 0.05, p[1] + (cxy[1] - p[1]) * 0.05
            mesh.box("steel.painted", px, py, zg, ELEV_FRAME, ELEV_FRAME, zd + 2.4 - zg, 0.0)
        z = zg + 3.0
        while z < zd - 1.0:
            _band(mesh, ring, z, 0.12)
            z += 3.0
        _band(mesh, ring, zd - 0.3, 0.3)
    else:
        mesh.prism("concrete", ring, zg, zd + 2.4, top=False)
    # the shaft's head (its machine room) over the deck
    _band(mesh, ring, zd + 2.4, z1 - zd - 2.4)
    a, b = ring[face], ring[(face + 1) % n]
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    ox, oy = uy * 0.02, -ux * 0.02
    m = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    for zl in (zg, zd):
        p0 = (m[0] - ux * DOOR_W / 2.0 + ox, m[1] - uy * DOOR_W / 2.0 + oy)
        p1 = (m[0] + ux * DOOR_W / 2.0 + ox, m[1] + uy * DOOR_W / 2.0 + oy)
        mesh.wall("steel", p0, p1, zl, zl + DOOR_H, zl, zl + DOOR_H)
    mesh.box("grate", m[0] + ox * 2, m[1] + oy * 2, z1 - 1.2, L * 0.6, 0.05, 0.6,
             M.degrees(M.atan2(uy, ux)))
    # the bridge from the door at the deck to the slab's edge
    if e is not None:
        ez = inp.get("edge_top") or zd
        outx, outy = uy, -ux                 # (out of the shaft through that face)
        d = (e[0] - m[0]) * outx + (e[1] - m[1]) * outy
        if d > 0.02:
            hw = DOOR_W / 2.0 + 0.3
            br = [(m[0] - ux * hw, m[1] - uy * hw), (m[0] + ux * hw, m[1] + uy * hw),
                  (m[0] + ux * hw + outx * (d + 0.05), m[1] + uy * hw + outy * (d + 0.05)),
                  (m[0] - ux * hw + outx * (d + 0.05), m[1] - uy * hw + outy * (d + 0.05))]
            mesh.prism("concrete", ccw(br), min(zd, ez) - LANDING_T, max(zd, ez), bottom=True)
    return Out(mesh=mesh, notes={"link": _reach(mesh, inp, zg, zd)})


def _band(mesh: Mesh, ring, z: float, h: float) -> None:
    """A steel band round a glass shaft at z."""
    c = (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
    out = [(p[0] + (p[0] - c[0]) * 0.02, p[1] + (p[1] - c[1]) * 0.02) for p in ring]
    mesh.prism("steel.painted", out, z, z + h, bottom=True)


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------

def check(model, cx: Ctx, recs: dict) -> dict:
    """`street_decks` (AG10, a city with decks only): every deck's slab objects, columns,
    stairs and elevators replaced by pieces with meshes; the lowest thing the slab hangs
    over a ground street (a light under its ribs) clears it by M14's headroom; every stair
    and elevator reaches the ground and the deck's top and lands on the slab's edge."""
    from citygen.decks import CLEAR_M
    bad = []
    n_slab = n_cols = n_links = 0
    clear = None
    for dk in sorted(model.decks, key=lambda d: d.id):
        for name in sorted(cx.keys.get(dk.id, ())):
            if not name.startswith(f"{dk.id}.slab."):
                continue
            n_slab += 1
            r = recs.get(name)
            if r is None or not r.get("triangles"):
                bad.append(f"{name}: no slab")
                continue
            c = ((r.get("notes") or {}).get("deck") or {}).get("clear_m")
            if c is not None:
                clear = c if clear is None else min(clear, c)
                if c < CLEAR_M:
                    bad.append(f"{name}: {c:.2f} m over a ground street")
    for st in sorted(model.structures, key=lambda s: s.id):
        if not is_deck_structure(st):
            continue
        r = recs.get(st.id)
        if r is None or not r.get("triangles") or not r.get("replaces"):
            bad.append(f"{st.id}: no {st.kind} replacing its blockout object")
            continue
        if st.kind == "column":
            n_cols += 1
            continue
        n_links += 1
        k = (r.get("notes") or {}).get("link") or {}
        if not k.get("edge"):
            bad.append(f"{st.id}: does not land on the slab's edge")
        elif k.get("low") is None or k["low"] > k["ground"] + 0.05 or \
                abs(k["high"] - k["top"]) > 0.05 or k.get("mesh_high", 0.0) < k["top"]:
            bad.append(f"{st.id}: runs {k.get('low')} to {k.get('high')}, not "
                       f"{k['ground']} to {k['top']}")
    return {"id": "street_decks", "ok": not bad,
            "detail": f"{len(model.decks)} decks: {n_slab} slab pieces, {n_cols} columns, "
                      f"{n_links} stairs and elevators; lowest over a ground street "
                      f"{clear if clear is not None else '-'} m (at least {CLEAR_M:g})"
                      + (f"; {len(bad)} failures: {'; '.join(bad[:6])}" if bad else "")}


__all__ = ["gather", "is_deck_structure", "deck_of", "spans", "Ref", "check"]
