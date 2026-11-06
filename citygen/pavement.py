"""M22: the pavement map (docs/assetgen_scope.md 14.18).

One exact map of the pavement, so the pieces drawn from it meet with no gap and no step by
construction. Every face (carriageway each way, median, curb, furniture zone and clear path
of a road; a junction's carriageway, its corner pads, a cul-de-sac's bulb; a bend where a
road's band would fold) is owned by a road segment or a junction. Where two faces meet, the
boundary is one stored edge, a polyline of vertex ids both faces reference; every vertex
has one stored height.

Construction (on the graded M2 roads, `build`):
- **Ribbons:** each road's cross-section bands as offsets of its centerline at stations
  (its vertices and every `STEP_M` or less), the same stations on every band edge, so a
  road is level across. A polyline vertex takes the mitre (the point on the bisector), a
  road end without a junction the mitre with the road it goes on as (a degree-2 node), so
  two roads meet on one line. Where a band would fold (a hairpin), that stretch is a bend
  face.
- **One cut per leg** (`junctions.build`): each road end's port, where every band,
  sidewalk, crosswalk and lane ends; a road whose two cuts meet has no face, its two
  junctions are one (a cluster).
- **Junction regions:** the carriageway bounded by the legs' ports and the curb lines
  between (corner fillets), the corner pads between the curb line, two legs' sidewalk ports
  and the property line; a cul-de-sac's bulb from its road's port. Built on the 1 mm grid
  (GEOS overlays at `GRID`) less the legs' ribbons, so a region ends on its ports.
- **Shared edges:** a vertex of one face that lies on another face's edge (within snap
  rounding, `TOL_MM`) is put into it; then every directed segment of a face meets its twin
  in the face on its other side, or none (the right of way's outer edge). Faces at one
  level that still overlap (two roads laid over each other with no node between them) are
  cut by priority (junctions, then carriageways by class, curbs, corner pads, sidewalks);
  the boundary is a seam edge.
- **Heights:** a road's vertices take its surface at their station (ground plus profile);
  a junction's curb lines run linearly by length between its ports, as M18's surfaces do;
  a face whose boundary is not one plane gets interior samples on a `SAMPLE_M` grid by mean
  value coordinates (closed form: square roots only). Heights are stored over the finished
  ground at the vertex, as every z in the model (0 on a flat city).

Ids (M10): a face is `<owner>.pv.<band>`; a vertex is named by its 1 mm cell
(`e1234567n89012`), an edge by its first segment from its lesser end, so neither moves
unless its geometry does, and a held road's ports keep theirs.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import Point, Polygon

from . import dmath as M
from . import streets as ST

GRID = 0.001            # the map's plan grid (1 mm)
STEP_M = 4.0            # band edge samples along a road, at most this far apart
SAMPLE_M = 2.0          # interior samples of a face that is not planar
SAMPLE_IN_M = 0.5       # ... at least this far inside its boundary
TOL_MM = 0.75           # a vertex this near another face's edge lies on it (snap rounding)
SAME_Z_M = 4.5          # faces nearer than this in height are one level (no road passes under
                        # another with less clearance)
STEP_Z_M = 0.3          # faces of roads or junctions that do not meet, this far apart in
#                         height where they touch, keep a vertex each there (a step)
MITER_MAX = 2.0         # a mitre longer than this (a turn over 120 degrees) folds the band
MIN_ROAD_M = 1.0        # a road whose two cuts leave less than this has no face: a cluster
ISLAND_M2 = 4.0         # a hole in a junction's region smaller than this is filled
SNAP_MM = 1             # junction vertices this near (each axis) are one (overlay rounding)
FLAT_MM = 1             # a face whose boundary lies on one plane within this is planar
CELL_MM = 2000          # spatial hash cell of the shared-edge pass
GAP_M2 = 1.0            # a hole in a layer's pavement this small is a sliver, filled
END_STRIP_M = 0.5       # a bend face's ends: strips this long on its road's frames
LONG_CURB_M = 40.0      # a cluster's curb this long between two ports follows its inner roads
STEP_TOL_M = 0.02       # a step this high between two vertices under 1 m apart is no grade
DEGENERATE_M = 2.0      # a road this short has no direction to build a junction corner on
LONG_MARGIN_M = 15.0    # a long curb follows its inner roads this far from its ports on
INNER_NEAR_M = 1.0      # ... where it is within this of an inner road's right of way
PINCH_MM2 = 1000        # a loop of a ring this small (mm2) where it touches itself is cut out
JUNCTION_KINDS = ("junction", "corner", "bulb", "bend")
ROAD_KINDS = ("carriageway", "median", "curb", "sidewalk", "walk")
# priority of a face where two at one level overlap (higher keeps the overlap)
KIND_RANK = {"junction": 6, "bulb": 6, "bend": 5, "carriageway": 4, "median": 4, "walk": 3,
             "curb": 2, "corner": 1, "sidewalk": 1}


def mm(v: float) -> int:
    return int(math.floor(v * 1000.0 + 0.5))


def m(i: int) -> float:
    return i / 1000.0


def vtok(p) -> str:
    """A vertex id: its 1 mm cell as compass offsets from the city center."""
    x, y = p
    return f"{'e' if x >= 0 else 'w'}{abs(x)}{'n' if y >= 0 else 's'}{abs(y)}"


def prof(pr, s: float) -> float:
    """A [(s, z)] profile at s (its ends beyond them)."""
    if not pr:
        return 0.0
    if s <= pr[0][0]:
        return pr[0][1]
    if s >= pr[-1][0]:
        return pr[-1][1]
    k = bisect.bisect_right([p[0] for p in pr], s) - 1
    (s0, z0), (s1, z1) = pr[k], pr[k + 1]
    return z0 if s1 == s0 else z0 + (s - s0) / (s1 - s0) * (z1 - z0)


# ---------------------------------------------------------------------------
# Paths: stations, frames and offsets
# ---------------------------------------------------------------------------

class Path:
    """A centerline: stations along it and the frame (point, left normal, mitre factor) at
    a station: a vertex takes the mitre of its two segments, a station between vertices the
    segment's normal; its ends a frame of their own where it goes on as another road."""

    def __init__(self, pts):
        p: list = []
        for q in pts:
            q = (float(q[0]), float(q[1]))
            if not p or q != p[-1]:
                p.append(q)
        if len(p) < 2:
            p = [p[0], (p[0][0] + 0.01, p[0][1])] if p else [(0.0, 0.0), (0.01, 0.0)]
        self.p = p
        self.cum = [0.0]
        self.dir = []
        self.nrm = []
        for a, b in zip(p, p[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.sqrt(dx * dx + dy * dy)
            self.cum.append(self.cum[-1] + L)
            self.dir.append((dx / L, dy / L))
            self.nrm.append((-dy / L, dx / L))
        self.L = self.cum[-1]
        self.start = None       # (nx, ny, k) at s = 0 where it goes on as another road
        self.end = None

    def seg(self, s: float) -> int:
        i = bisect.bisect_right(self.cum, s) - 1
        return min(max(i, 0), len(self.p) - 2)

    def frame(self, s: float):
        if s <= 0.0:
            x, y = self.p[0]
            if self.start is not None:
                return (x, y) + self.start
            n = self.nrm[0]
            return x, y, n[0], n[1], 1.0
        if s >= self.L:
            x, y = self.p[-1]
            if self.end is not None:
                return (x, y) + self.end
            n = self.nrm[-1]
            return x, y, n[0], n[1], 1.0
        i = self.seg(s)
        if i > 0 and s == self.cum[i]:
            n0, n1 = self.nrm[i - 1], self.nrm[i]
            nx, ny = n0[0] + n1[0], n0[1] + n1[1]
            ln = math.sqrt(nx * nx + ny * ny)
            x, y = self.p[i]
            if ln < 1e-9:
                return x, y, n1[0], n1[1], 1.0
            nx, ny = nx / ln, ny / ln
            return x, y, nx, ny, 1.0 / (nx * n1[0] + ny * n1[1])
        a, b = self.p[i], self.p[i + 1]
        t = (s - self.cum[i]) / (self.cum[i + 1] - self.cum[i])
        n = self.nrm[i]
        return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), n[0], n[1], 1.0

    def point(self, s: float, w: float) -> tuple[int, int]:
        x, y, nx, ny, k = self.frame(s)
        return mm(x + w * k * nx), mm(y + w * k * ny)

    def mitre(self, s: float) -> float:
        return self.frame(s)[4]

    def stations(self, a: float, b: float) -> list[float]:
        key = [a] + [c for c in self.cum[1:-1] if a < c < b] + [b]
        out = [key[0]]
        for u, v in zip(key, key[1:]):
            n = max(1, math.ceil((v - u) / STEP_M - 1e-9))
            for j in range(1, n):
                out.append(u + (v - u) * j / n)
            out.append(v)
        return out

    def project(self, x: float, y: float, s0: float = 0.0, s1: float | None = None) -> float:
        """Distance along the path of the point nearest (x, y), searched between s0 and
        s1 (plain arithmetic)."""
        s1 = self.L if s1 is None else s1
        i0, i1 = self.seg(s0), self.seg(s1)
        best = None
        for i in range(i0, i1 + 1):
            a, b = self.p[i], self.p[i + 1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 == 0 else ((x - a[0]) * dx + (y - a[1]) * dy) / L2
            t = min(max(t, 0.0), 1.0)
            qx, qy = a[0] + t * dx - x, a[1] + t * dy - y
            d = qx * qx + qy * qy
            if best is None or d < best[0] - 1e-12:
                best = (d, self.cum[i] + t * (self.cum[i + 1] - self.cum[i]))
        return min(max(best[1], s0), s1)


def unit_layer(legs) -> str:
    """A junction's layer: a deck's where all its roads are on the deck, else the lowest
    level of its roads that are not in a tunnel."""
    segs = [x.seg for x in legs if x.cls != "footbridge"]
    if segs and all("deck" in (s.get("attrs") or {}) for s in segs):
        return "d1"
    lv = [max(int(s.get("level") or 0), 0) for s in segs
          if not s.get("tunnel") and "deck" not in (s.get("attrs") or {})]
    if lv:
        return f"g{min(lv)}"
    return "u1" if any(s.get("tunnel") for s in segs) else "g0"


def units_from_rows(segments: list[dict], nodes: list[dict], junctions: list[dict],
                    darch: dict) -> list:
    """The junction regions of a network from its rows (`junctions.build` stores each road's
    cuts in `attrs.cuts` and a cluster's nodes and inner roads in its junction's attrs), so
    the map can be made again from a model (a regenerated district, overrides)."""
    from types import SimpleNamespace

    from . import junctions as JN

    def arch_of(s):
        d = s["attrs"].get("district")
        if d:
            return darch.get(d)
        ids = s.get("district_ids") or []
        return darch.get(ids[0]) if ids else None
    legs = JN.legs_at(SimpleNamespace(segments=segments), arch_of)
    for lg in legs.values():
        for x in lg:
            c = (x.seg["attrs"].get("cuts") or [0.0, 0.0])[0 if x.at_start else 1]
            x.cut = x.cut_row = c
    node = {n["id"]: n for n in nodes}
    out = []
    for j in junctions:
        a = j.get("attrs") or {}
        ns = a.get("nodes") or [j["node_id"]]
        inner = list(a.get("inner") or [])
        ext = [x for n in ns for x in legs.get(n, []) if x.seg["id"] not in inner]
        head = (node[j["node_id"]].get("attrs") or {}).get("turning_head_m", 0.0) \
            if j.get("shape") == "cul_de_sac" else 0.0
        heads = {n: (node[n].get("attrs") or {}).get("turning_head_m", 0.0)
                 for n in a.get("bulbs") or []}
        out.append(Unit(j["id"], ns, ext, inner, head, unit_layer(ext),
                        {n: legs.get(n, []) for n in ns}, heads=heads))
    return out


def bands(seg: dict) -> list[tuple[float, float, str, str]]:
    """A road's cross-section bands, (offset from, to, face kind, band), left of the
    centerline (seen along the road) positive: clear path, furniture zone, curb and
    carriageway each side (forward traffic on the right), a median; one walking surface on
    a pedestrian street, path or promenade."""
    cls = ST.street_class(seg)
    row = seg["width_m"] / 2.0
    if cls in ST.PEDESTRIAN:
        return [(-row, row, "walk", "wk")]
    cs = seg["cross_section"]
    side = min(cs["sidewalk_m"][0] if cs.get("sidewalk_m") else 0.0, row)
    h = row - side
    if h <= 0.05:
        return [(-row, row, "walk", "wk")]
    out = []
    if side > 0.005:
        curb = min(cs.get("curb_m", 0.15), side)
        furn = min(max(cs.get("furniture_m", 0.0), 0.0), side - curb) \
            if cls in ("avenue", "street") else 0.0
        e1, e2 = h + curb, h + curb + furn
        for lo, hi, kind, band in ((e2, row, "sidewalk", "cl"), (e1, e2, "sidewalk", "fn"),
                                   (h, e1, "curb", "cr")):
            if hi - lo > 0.005:
                out.append((-hi, -lo, kind, band + "r"))
                out.append((lo, hi, kind, band + "l"))
    med = min(cs.get("median_m", 0.0) or 0.0, 2.0 * h - 1.0)
    one = cs.get("shared") or cls == "alley" or (seg.get("one_way") and
                                                 cs.get("lanes_backward", 0) == 0)
    if one:
        out.append((-h, h, "carriageway", "cw"))
    elif med > 0.005:
        out += [(-h, -med / 2.0, "carriageway", "cwf"), (-med / 2.0, med / 2.0, "median", "md"),
                (med / 2.0, h, "carriageway", "cwb")]
    else:
        out += [(-h, 0.0, "carriageway", "cwf"), (0.0, h, "carriageway", "cwb")]
    return sorted(out)


def offsets(bd) -> list[float]:
    ws = sorted({b[0] for b in bd} | {b[1] for b in bd})
    return ws


def layer_of(seg: dict) -> str:
    """The surface layer of a road: the ground's roads (g0), raised networks by M7's levels
    (g1 to g3), a district's deck (d1), tunnels (u1)."""
    a = seg.get("attrs") or {}
    if "deck" in a:
        return "d1"
    if seg.get("tunnel"):
        return "u1"
    return f"g{max(int(seg.get('level') or 0), 0)}"


# ---------------------------------------------------------------------------
# Faces
# ---------------------------------------------------------------------------

@dataclass
class Face:
    fid: str
    owner: str
    kind: str
    band: str
    layer: str
    prio: tuple
    rings: list            # [exterior CCW, holes CW], each a list of (x_mm, y_mm)
    road: str | None = None          # its road (road faces, bends)
    unit: str | None = None          # its junction (junction faces)
    legs: frozenset = frozenset()    # roads a junction face meets at its ports
    span: tuple | None = None        # (s0, s1) of a road face along its road
    ports: list = field(default_factory=list)   # road faces: indices of port segments
    samples: list = field(default_factory=list)

    def poly(self) -> Polygon:
        rs = [[(m(x), m(y)) for x, y in r] for r in self.rings]
        return Polygon(rs[0], rs[1:])


def _ring_area2(r) -> int:
    a = 0
    n = len(r)
    for i in range(n):
        x0, y0 = r[i]
        x1, y1 = r[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a


def _clean(r) -> list:
    out = []
    for p in r:
        if not out or p != out[-1]:
            out.append(p)
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    # (spikes: a vertex where the ring turns straight back, its neighbors on one line with
    # it, exact on the grid)
    changed = True
    while changed and len(out) >= 3:
        changed = False
        n = len(out)
        for i in range(n):
            a, b, c = out[i - 1], out[i], out[(i + 1) % n]
            if a == c:
                k = (i + 1) % n
                for j in sorted({i, k}, reverse=True):
                    out.pop(j)
                changed = True
                break
            ux, uy, vx, vy = b[0] - a[0], b[1] - a[1], c[0] - b[0], c[1] - b[1]
            if ux * vy - uy * vx == 0 and ux * vx + uy * vy < 0:
                out.pop(i)
                changed = True
                break
        if changed:
            continue
        # (a pinch: a vertex twice, the loop between under PINCH_MM2 cut out)
        seen: dict = {}
        for i, v in enumerate(out):
            j = seen.get(v)
            if j is not None:
                loop = out[j:i]
                if len(loop) < 3 or abs(_ring_area2(loop)) < 2 * PINCH_MM2:
                    del out[j:i]
                    changed = True
                    break
            seen[v] = i
    return out


def mm_polys(geom) -> list[list]:
    """The polygons of a geometry on the map's grid as ring lists (`rings_of`), each simple:
    a polygon that rounding pinched or folded is split at the pinch, its slivers dropped."""
    out = []
    for p in polys(geom):
        rs = rings_of(p)
        if not rs:
            continue
        q = Polygon([(m(x), m(y)) for x, y in rs[0]], [[(m(x), m(y)) for x, y in r]
                                                        for r in rs[1:]])
        if q.is_valid:
            out.append(rs)
            continue
        for part in polys(shapely.make_valid(q)):
            if part.area < 1e-4:
                continue
            r2 = rings_of(part)
            if r2:
                out.append(r2)
    return out


def rings_of(poly) -> list[list]:
    """Rings of a shapely polygon on the map's grid: the exterior counterclockwise, holes
    clockwise, (x_mm, y_mm), no closing repeat."""
    ext = _clean([(mm(x), mm(y)) for x, y in poly.exterior.coords])
    if len(ext) < 3:
        return []
    if _ring_area2(ext) < 0:
        ext.reverse()
    out = [ext]
    for h in poly.interiors:
        r = _clean([(mm(x), mm(y)) for x, y in h.coords])
        if len(r) < 3:
            continue
        if _ring_area2(r) > 0:
            r.reverse()
        out.append(r)
    return out


def _rs_area(rs) -> int:
    """Twice the area (mm^2) of a ring list (holes clockwise)."""
    return sum(_ring_area2(r) for r in rs) // 2


def _rs_key(rs):
    xs = [p[0] for p in rs[0]]
    ys = [p[1] for p in rs[0]]
    return (-_rs_area(rs), min(xs), min(ys), max(xs), max(ys))


def polys(geom) -> list:
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    out = []
    for g in getattr(geom, "geoms", []):
        out += polys(g)
    return out


def _areal(g):
    """The polygonal part of a geometry (an overlay on the grid can leave lines)."""
    if g is None or g.is_empty:
        return Polygon()
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    ps = polys(g)
    if not ps:
        return Polygon()
    return ps[0] if len(ps) == 1 else shapely.MultiPolygon(ps)


def _ov(op, a, b):
    return _areal(op(_areal(a), _areal(b), grid_size=GRID))


def union(geoms):
    gs = [_areal(g) for g in geoms]
    gs = [g for g in gs if not g.is_empty]
    if not gs:
        return Polygon()
    return _areal(shapely.union_all(gs, grid_size=GRID))


# ---------------------------------------------------------------------------
# Roads
# ---------------------------------------------------------------------------

class Road:
    def __init__(self, seg: dict, ground=None):
        self.seg = seg
        self.sid = seg["id"]
        self.cls = ST.street_class(seg)
        self.path = Path(seg["centerline"])
        self.bands = bands(seg)
        self.ws = offsets(self.bands)
        self.row = seg["width_m"] / 2.0
        self.zp = [(p["s"], p["z"]) for p in seg.get("z_profile") or []]
        g = seg.get("ground") or []
        self.gp = [(p["s"], p["z"]) for p in g]
        self.layer = layer_of(seg)
        self.rank = ST.RANK.get(seg["road_class"], 0)
        cs = seg["cross_section"]
        side = min(cs["sidewalk_m"][0] if cs.get("sidewalk_m") else 0.0, self.row)
        self.h = self.row if self.cls in ST.PEDESTRIAN else max(self.row - side, 0.0)
        self.a = 0.0            # cut at its start
        self.b = 0.0            # cut at its end (from its end)
        self.unit_a = None      # the junction at its start (its id), if any
        self.unit_b = None      # ... at its end

    def z(self, s: float) -> float:
        """Its surface over sea level at s (ground plus profile; the profile alone on a
        flat city)."""
        return prof(self.gp, s) + prof(self.zp, s)

    def port(self, end: str) -> tuple[float, list]:
        """(station, [(offset, point)]) of the port at one end, offsets ascending."""
        s = self.a if end == "start" else self.path.L - self.b
        return s, [(w, self.path.point(s, w)) for w in self.ws]

    def strip(self, s0: float, s1: float, w0: float, w1: float) -> list:
        """A ring (counterclockwise) of the band between offsets w0 < w1 from s0 to s1; its
        ends through every band offset between (the port points), so every polygon that
        ends on a port has the same vertices there (points on the 1 mm grid are not exactly
        on one line)."""
        ss = self.path.stations(s0, s1)
        lo = [self.path.point(s, w0) for s in ss]
        hi = [self.path.point(s, w1) for s in ss]
        mid = [w for w in self.ws if w0 + 1e-9 < w < w1 - 1e-9]
        end = [self.path.point(s1, w) for w in mid]
        start = [self.path.point(s0, w) for w in mid[::-1]]
        return _clean(lo + end + hi[::-1] + start)

    def strip_poly(self, s0: float, s1: float, w0: float, w1: float):
        r = self.strip(s0, s1, w0, w1)
        if len(r) < 3:
            return Polygon()
        p = Polygon([(m(x), m(y)) for x, y in r])
        if not p.is_valid:
            p = union(polys(shapely.make_valid(p)))
        return p

    def fold_poly(self, a: float, b: float, w: float):
        """The ground a stretch that folds covers, w either side: its centerline buffered
        (round at its turns), its ends square on its frames (short strips there, not the
        whole stretch, whose mitres at a turn near a reversal reach hundreds of meters out)."""
        ss = self.path.stations(a, b)
        line = shapely.LineString([self.path.frame(st)[:2] for st in ss])
        g = shapely.buffer(line, w, cap_style="flat", join_style="round", quad_segs=4)
        # (each end strip short of the path's first vertex inside the stretch, whose mitre
        # may be the fold itself)
        inside = [c for c in self.path.cum[1:-1] if a + 1e-6 < c < b - 1e-6]
        ea = min(END_STRIP_M, (b - a) / 2.0, (inside[0] - a) / 2.0 if inside else math.inf)
        eb = min(END_STRIP_M, (b - a) / 2.0, (b - inside[-1]) / 2.0 if inside else math.inf)
        return _ov(shapely.union, g, union([self.strip_poly(a, a + ea, -w, w),
                                            self.strip_poly(b - eb, b, -w, w)]))

    def band_poly(self, s0: float, s1: float, w: float):
        """The ground its right of way (w either side) covers from s0 to s1: strips, and
        `fold_poly` where it folds."""
        parts, cur = [], s0
        for a, b in self.folds(s0, s1):
            if a > cur + 0.001:
                parts.append(self.strip_poly(cur, a, -w, w))
            parts.append(self.fold_poly(a, b, w))
            cur = b
        if s1 > cur + 0.001:
            parts.append(self.strip_poly(cur, s1, -w, w))
        return union([q for q in parts if not q.is_empty])

    def folds(self, s0: float, s1: float) -> list[tuple[float, float]]:
        """Stretches between s0 and s1 where an edge of its right of way would fold back
        (a turn tighter than its half width, a mitre over MITER_MAX)."""
        ss = self.path.stations(s0, s1)
        bad = []
        for w in (-self.row, self.row):
            prev = None
            for s in ss:
                x, y, nx, ny, k = self.path.frame(s)
                q = (x + w * k * nx, y + w * k * ny)
                if k > MITER_MAX:
                    bad.append((s, s))
                if prev is not None:
                    t = self.path.dir[self.path.seg((prev[0] + s) / 2.0)]
                    if (q[0] - prev[1][0]) * t[0] + (q[1] - prev[1][1]) * t[1] <= 1e-6:
                        bad.append((prev[0], s))
                prev = (s, q)
        if not bad:
            return []
        bad.sort()
        out = []
        for a, b in bad:
            a, b = max(s0, a - self.row), min(s1, b + self.row)
            if out and a <= out[-1][1]:
                out[-1] = (out[-1][0], max(out[-1][1], b))
            else:
                out.append((a, b))
        return out


def end_frames(roads: dict, at: dict, junction_nodes: set) -> None:
    """The ends of two roads that go on as each other at a node without a junction take one
    frame there, the mitre of their two directions, so they meet on one line."""
    for nid in sorted(at):
        if nid in junction_nodes:
            continue
        ends = [(sid, which) for sid, which in at[nid] if sid in roads]
        if len(ends) != 2:
            continue
        (sa, wa), (sb, wb) = ends
        A, B = roads[sa].path, roads[sb].path
        ta = A.dir[-1] if wa == "end" else (-A.dir[0][0], -A.dir[0][1])
        tb = B.dir[0] if wb == "start" else (-B.dir[-1][0], -B.dir[-1][1])
        la, lb = (-ta[1], ta[0]), (-tb[1], tb[0])
        nx, ny = la[0] + lb[0], la[1] + lb[1]
        ln = math.sqrt(nx * nx + ny * ny)
        if ln < 1e-9:
            continue
        nx, ny = nx / ln, ny / ln
        k = 1.0 / (nx * la[0] + ny * la[1])
        if k > MITER_MAX:
            continue
        for path, which, sign in ((A, wa, 1.0 if wa == "end" else -1.0),
                                  (B, wb, 1.0 if wb == "start" else -1.0)):
            fr = (sign * nx, sign * ny, k)
            if which == "start":
                path.start = fr
            else:
                path.end = fr


def road_faces(rd: Road) -> tuple[list[Face], list[tuple]]:
    """A road's band faces between its cuts (bend faces where a band would fold) and the
    stretches it leaves to bends."""
    s0, s1 = rd.a, rd.path.L - rd.b
    rd.ends = []        # (station, [points]) at each ribbon piece's ends
    rd.known = {}       # point -> station
    if s1 - s0 < 0.001:
        return [], []
    folds = rd.folds(s0, s1)
    pieces = []
    cur = s0
    for a, b in folds:
        if a > cur + 0.001:
            pieces.append(("rib", cur, a))
        pieces.append(("bend", a, b))
        cur = b
    if s1 > cur + 0.001:
        pieces.append(("rib", cur, s1))
    out = []
    bends = []
    nrib = sum(1 for p in pieces if p[0] == "rib")
    k = 0
    for kind, a, b in pieces:
        if kind == "bend":
            bends.append((a, b))
            continue
        suffix = "" if nrib == 1 else "_" + _letters(k)
        k += 1
        ss = rd.path.stations(a, b)
        edges = {w: [rd.path.point(s, w) for s in ss] for w in rd.ws}
        for w, pts in edges.items():
            for s, p in zip(ss, pts):
                rd.known.setdefault(p, s)
        rd.ends.append((a, [edges[w][0] for w in rd.ws]))
        rd.ends.append((b, [edges[w][-1] for w in rd.ws]))
        for w0, w1, fk, band in rd.bands:
            lo, hi = edges[w0], edges[w1]
            ring = _clean(lo + hi[::-1])
            if len(ring) < 3 or _ring_area2(ring) <= 0:
                continue
            out.append(Face(f"{rd.sid}.pv.{band}{suffix}", rd.sid, fk, band + suffix,
                            rd.layer, (KIND_RANK[fk], rd.rank), [ring], road=rd.sid,
                            span=(a, b)))
    return out, bends


def _letters(k: int) -> str:
    s = ""
    k += 1
    while k:
        k, r = divmod(k - 1, 26)
        s = chr(97 + r) + s
    return s


# ---------------------------------------------------------------------------
# Junctions
# ---------------------------------------------------------------------------

@dataclass
class Unit:
    """A junction's region: its nodes (more than one for a cluster), the legs that leave
    it (Leg objects of `junctions`, cut set), the roads inside it, a bulb's radius."""
    jid: str
    nodes: list
    legs: list
    inner: list = field(default_factory=list)      # segment ids inside a cluster
    head: float = 0.0
    layer: str = "g0"
    by_node: dict = field(default_factory=dict)    # node id -> its legs (inner ones too)
    ports: list = field(default_factory=list)      # (road id, z, end a, end b) per leg
    heads: dict = field(default_factory=dict)      # a cluster's cul-de-sac nodes -> bulb


def _leg_port(rd: Road, lg, c: float | None = None, carriageway: bool = False) -> list:
    """A leg's port points from its right to its left (seen from the node)."""
    if c is None:
        s = rd.a if lg.at_start else rd.path.L - rd.b
    else:
        s = c if lg.at_start else rd.path.L - c
    ws = [w for w in rd.ws if not carriageway or abs(w) <= rd.h + 1e-9]
    pts = [rd.path.point(s, w) for w in ws]
    return pts if lg.at_start else pts[::-1]


def _stub(rd: Road, lg, c: float, w: float):
    """A leg's band of half width w from its node to c along it (`Road.band_poly`: a turn
    inside the cut that folds the band is its centerline buffered, not a mitre's spike)."""
    if lg.at_start:
        return rd.band_poly(0.0, min(c, rd.path.L), w)
    return rd.band_poly(max(rd.path.L - c, 0.0), rd.path.L, w)


def _ring_poly(pts):
    ps = []
    for p in pts:
        q = (m(p[0]), m(p[1])) if isinstance(p[0], int) else (float(p[0]), float(p[1]))
        if not ps or q != ps[-1]:
            ps.append(q)
    if len(ps) < 3:
        return Polygon()
    g = Polygon(ps)
    if not g.is_valid:
        g = shapely.make_valid(g)
    return union(polys(g))


def _core(P, lg: list, roads: dict, row: bool, cut_of) -> object:
    """The ring of a node's legs: each leg's port (carriageway, or the whole right of way
    with `row`) and the corner between it and the next counterclockwise (`junctions`'
    fillets)."""
    from . import junctions as JN

    # (a road of no length, a layout's leftover, has no direction to build a corner on)
    lg = [x for x in lg if x.L >= DEGENERATE_M]
    n = len(lg)
    if n < 2:
        return Polygon()

    def cut(x):
        c = cut_of(x)
        if c is not None:
            return c
        rd = roads[x.seg["id"]]
        return rd.a if x.at_start else rd.b
    ring = []
    for i in range(n):
        a, b = lg[i], lg[(i + 1) % n]
        ra = roads[a.seg["id"]]
        ring += _leg_port(ra, a, cut_of(a), carriageway=not row)
        ha = a.row if row else a.h
        hb = b.row if row else b.h
        r = min(a.r, b.r)
        if row:
            r = max(r - max(a.sw, b.sw), JN.ROW_CORNER_MIN_M)
        ca, cb = cut(a), cut(b)
        c = JN._corner(P, a, b, ha, hb, r) if n > 2 else None
        if c is not None and c[4] is not None and c[0] <= ca and c[1] <= cb:
            _, _, Ta, Tb, O, _ = c
            ring.append(Ta)
            ring += JN._arc(O, Ta, Tb, r)
            ring.append(Tb)
            continue
        # (no fillet inside both ports, or a bend: the sharp corner where the edges meet,
        # where it lies inside both ports; else the curb runs straight between them)
        X = _sharp(P, a, b, ha, hb)
        if X is not None and 0.0 <= X[0] <= ca and 0.0 <= X[1] <= cb:
            ring.append(X[2])
    return _ring_poly(ring)


def _sharp(P, a, b, ha: float, hb: float):
    """Where leg a's left edge (offset ha) meets leg b's right edge (offset hb), b
    counterclockwise from a, along their directions at the node: (t along a, t along b,
    point), or None where they do not meet ahead (parallel, or a gap of 180 degrees or
    more)."""
    da, db = a.d, b.d
    na, nb = (-da[1], da[0]), (-db[1], db[0])
    sinp = da[0] * db[1] - da[1] * db[0]
    if sinp <= 1e-9:
        return None
    rx = -hb * nb[0] - ha * na[0]
    ry = -hb * nb[1] - ha * na[1]
    det = da[0] * (-db[1]) - da[1] * (-db[0])
    t1 = (rx * (-db[1]) - ry * (-db[0])) / det
    t2 = (da[0] * ry - da[1] * rx) / det
    return t1, t2, (P[0] + ha * na[0] + t1 * da[0], P[1] + ha * na[1] + t1 * da[1])


def unit_regions(u: Unit, roads: dict, pos: dict) -> tuple:
    """(carriageway, right of way, corner pads) of a junction's region, each on the map's
    grid, less its legs' ribbons (so each ends on its ports)."""
    ext = [x for x in u.legs if x.seg["id"] in roads and x.cls != "footbridge"]
    beyond = []
    for x in ext:
        rd = roads[x.seg["id"]]
        s0, s1 = rd.a, rd.path.L - rd.b
        if s1 - s0 > 0.0005:
            beyond.append(rd.band_poly(s0, s1, rd.row))
    cw, rw = [], []
    inner = set(u.inner)
    for nid in u.nodes:
        P = pos[nid]
        lg = [x for x in u.by_node[nid] if x.cls != "footbridge" and x.seg["id"] in roads]

        def cut_of(x):
            if x.seg["id"] in inner:
                return roads[x.seg["id"]].path.L / 2.0
            return None
        cw.append(_core(P, lg, roads, False, cut_of))
        rw.append(_core(P, lg, roads, True, cut_of))
        for x in lg:
            rd = roads[x.seg["id"]]
            if x.seg["id"] in inner:
                continue
            c = rd.a if x.at_start else rd.b
            cw.append(_stub(rd, x, c, rd.h))
            rw.append(_stub(rd, x, c, rd.row))
    for sid in sorted(inner):
        rd = roads.get(sid)
        if rd is None:
            continue
        cw.append(rd.band_poly(0.0, rd.path.L, rd.h))
        rw.append(rd.band_poly(0.0, rd.path.L, rd.row))
    heads = dict(u.heads)
    if u.head:
        heads[u.nodes[0]] = u.head
    for nid in sorted(heads):
        x = u.by_node[nid][0] if u.by_node.get(nid) else None
        sw = (x.row - x.h) if x is not None else 0.0
        cw.append(_circle(pos[nid], heads[nid]))
        rw.append(_circle(pos[nid], heads[nid] + sw))
    C = _fill_small(union(cw))
    R = _fill_small(union(rw + [C]))
    if beyond:
        B = union(beyond)
        C = _ov(shapely.difference, C, B)
        R = _ov(shapely.difference, R, B)
    pads = _ov(shapely.difference, R, C) if not R.is_empty else Polygon()
    return C, R, pads


def _fill_small(g):
    """A region with its holes under ISLAND_M2 filled (slivers the union of a junction's
    pieces leaves between them, not islands)."""
    out = []
    for p in polys(g):
        holes = [h for h in p.interiors if Polygon(h).area >= ISLAND_M2]
        out.append(Polygon(p.exterior, holes) if len(holes) != len(p.interiors) else p)
    return union(out) if out else g


def _circle(P, r: float, n: int = 24):
    pts = [(P[0] + r * M.cos(a), P[1] + r * M.sin(a))
           for a in [k * 2 * M.PI / n for k in range(n)]]
    return Polygon(pts)


def unit_faces(u: Unit, roads: dict, pos: dict) -> tuple[list[Face], object, object]:
    C, R, pads = unit_regions(u, roads, pos)
    legs = frozenset(x.seg["id"] for x in u.legs if x.seg["id"] in roads)
    out = []
    kind = "bulb" if u.head else "junction"
    cps = sorted((rs for rs in mm_polys(C) if _rs_area(rs) >= 100), key=_rs_key)
    for k, rs in enumerate(cps):
        band = "jn" if k == 0 else "jn_" + _letters(k)
        out.append(Face(f"{u.jid}.pv.{band}", u.jid, kind, band, u.layer,
                        (KIND_RANK[kind], 9), rs, unit=u.jid, legs=legs))
    P = pos[u.nodes[0]]
    pp = [rs for rs in mm_polys(pads) if _rs_area(rs) >= 100]

    def ang(rs):
        c = Polygon([(m(x), m(y)) for x, y in rs[0]]).representative_point()
        return (M.atan2(c.y - P[1], c.x - P[0]), _rs_key(rs))
    for k, rs in enumerate(sorted(pp, key=ang)):
        band = "pad_" + _letters(k)
        out.append(Face(f"{u.jid}.pv.{band}", u.jid, "corner", band, u.layer,
                        (KIND_RANK["corner"], 9), rs, unit=u.jid, legs=legs))
    return out, C, R


def bend_faces(rd: Road, bends: list) -> list[Face]:
    """A road's stretches where a band would fold, each one face of its whole right of way,
    less the ribbons beside it."""
    out = []
    for a, b in bends:
        # (its ends are ports too: their points known, at the road's height there)
        for st in (a, b):
            pts = [rd.path.point(st, w) for w in rd.ws]
            for q in pts:
                rd.known.setdefault(q, st)
            rd.ends.append((st, pts))
    for k, (a, b) in enumerate(bends):
        g = rd.fold_poly(a, b, rd.row)
        side = []
        if a > rd.a + 0.001:
            side.append(rd.strip_poly(max(rd.a, a - 3.0 * rd.row), a, -rd.row, rd.row))
        if b < rd.path.L - rd.b - 0.001:
            side.append(rd.strip_poly(b, min(rd.path.L - rd.b, b + 3.0 * rd.row),
                                      -rd.row, rd.row))
        if side:
            g = _ov(shapely.difference, g, union(side))
        parts = sorted((rs for rs in mm_polys(g) if _rs_area(rs) >= 100), key=_rs_key)
        for j, rs in enumerate(parts):
            band = "bend_" + _letters(k) + ("" if j == 0 else _letters(j))
            out.append(Face(f"{rd.sid}.pv.{band}", rd.sid, "bend", band, rd.layer,
                            (KIND_RANK["bend"], rd.rank), rs, road=rd.sid, span=(a, b)))
    return out


# ---------------------------------------------------------------------------
# Shared edges
# ---------------------------------------------------------------------------

def _on_seg(p, q, v) -> bool:
    """Whether v lies on segment pq strictly between its ends, within TOL_MM (exact integer
    arithmetic: cross^2 / |pq|^2 <= TOL^2)."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    ex, ey = v[0] - p[0], v[1] - p[1]
    den = dx * dx + dy * dy
    num = ex * dx + ey * dy
    if num <= 0 or num >= den:
        return False
    cr = ex * dy - ey * dx
    return cr * cr * 16 <= 9 * den


def _param(p, q, v) -> float:
    dx, dy = q[0] - p[0], q[1] - p[1]
    return ((v[0] - p[0]) * dx + (v[1] - p[1]) * dy) / (dx * dx + dy * dy)


def _seg_d2(a, b, p) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
    t = min(max(t, 0.0), 1.0)
    qx, qy = a[0] + t * dx - p[0], a[1] + t * dy - p[1]
    return qx * qx + qy * qy


class _Hash:
    def __init__(self):
        self.cells: dict = {}

    def add(self, v, fi: int) -> None:
        key = (v[0] // CELL_MM, v[1] // CELL_MM)
        self.cells.setdefault(key, set()).add((v[0], v[1], fi))

    def near(self, p, q):
        x0, x1 = min(p[0], q[0]) - 2, max(p[0], q[0]) + 2
        y0, y1 = min(p[1], q[1]) - 2, max(p[1], q[1]) + 2
        out = []
        for i in range(x0 // CELL_MM, x1 // CELL_MM + 1):
            for j in range(y0 // CELL_MM, y1 // CELL_MM + 1):
                c = self.cells.get((i, j))
                if c:
                    out.extend(c)
        out.sort()
        return out


class Assembly:
    """The faces of a city and what they meet: the pass that makes shared edges exact, the
    overlap repair, the edge extraction, the heights and samples."""

    def __init__(self, faces: list[Face], roads: dict, units: dict, adj: dict, ground=None,
                 level: dict | None = None):
        self.faces = faces
        self.roads = roads
        self.units = units
        self.adj = adj              # owner id -> owners it meets
        self.ground = ground        # the finished ground (terrain.Field) or None
        self.level = level or {}    # point -> (road id, station): one height on a port line
        self.ports: set = set()
        self.port_owner: dict = {}
        for fi, f in enumerate(faces):
            if f.road is None or f.kind == "bend":
                continue
            rd = roads[f.road]
            for _, pts in rd.ends:
                for p in pts:
                    self.ports.add(p)
            for r in f.rings:
                for v in r:
                    if v in self.ports and v not in self.port_owner:
                        self.port_owner[v] = fi
        self.stats: dict = {}

    # -- what meets what ---------------------------------------------------------------

    def owner_key(self, f: Face) -> str:
        return f.unit if f.unit is not None else f.road

    def related(self, f: Face, g: Face) -> bool:
        a, b = self.owner_key(f), self.owner_key(g)
        return a == b or b in self.adj.get(a, ()) or a in self.adj.get(b, ())

    def zf(self, f: Face, x: float, y: float) -> float:
        """A face's height at a plan point, roughly (to tell levels apart where faces meet
        in plan): a road's at its station, a junction's from its ports."""
        if f.road is not None:
            rd = self.roads[f.road]
            s0, s1 = f.span if f.span else (0.0, rd.path.L)
            return rd.z(rd.path.project(x, y, s0, s1))
        # (a junction's: its ports' heights blended by inverse square distance, so a face
        # near its low ports reads low though a raised leg's port is the nearest one)
        u = self.units.get(f.unit)
        num = den = 0.0
        for _, z, a, b in (u.ports if u is not None else []):
            d2 = _seg_d2(a, b, (x, y))
            if d2 < 1e-6:
                return z
            num += z / d2
            den += 1.0 / d2
        return num / den if den else 0.0

    def _inner_z(self, u: Unit, x: float, y: float, near: float | None = None):
        """A cluster's height at a plan point: its nearest inner road's at its station (None
        where `near` is given and no inner road's right of way is within it)."""
        best = None
        for sid in sorted(u.inner):
            rd = self.roads.get(sid)
            if rd is None:
                continue
            s = rd.path.project(x, y, 0.0, rd.path.L)
            px, py = rd.path.point(s, 0.0)
            d = (m(px) - x) ** 2 + (m(py) - y) ** 2
            if near is not None and math.sqrt(d) > rd.row + near:
                continue
            if best is None or d < best[0]:
                best = (d, rd.z(s))
        return best[1] if best else (None if near is not None else 0.0)

    def compatible(self, f: Face, g: Face, v) -> bool:
        if self.related(f, g):
            return True
        if f.layer != g.layer:
            return False
        x, y = m(v[0]), m(v[1])
        return abs(self.zf(f, x, y) - self.zf(g, x, y)) <= SAME_Z_M

    # -- vertices onto edges -----------------------------------------------------------

    def snap_ports(self) -> int:
        """Junction, corner, bulb and bend faces' vertices within SNAP_MM (each axis) of a
        port point, or of each other, are one point: the port point, else the least (the
        overlays that make them round their intersections onto the grid independently)."""
        H = _Hash()
        for p in sorted(self.ports):
            H.add(p, -1)
        canon: dict = {}
        verts = sorted({v for f in self.faces if f.kind in JUNCTION_KINDS
                        for r in f.rings for v in r} - self.ports)
        for v in verts:
            rep = None
            for x, y, _ in H.near(v, v):
                if abs(x - v[0]) <= SNAP_MM and abs(y - v[1]) <= SNAP_MM:
                    rep = (x, y)
                    break
            if rep is None:
                H.add(v, 0)
            else:
                canon[v] = rep
        n = 0
        for f in self.faces:
            if f.kind not in JUNCTION_KINDS:
                continue
            new = []
            for r in f.rings:
                rr = [canon.get(v, v) for v in r]
                n += sum(1 for v in r if v in canon)
                rr = _clean(rr)
                if len(rr) >= 3:
                    new.append(rr)
            f.rings = new
        return n

    def tfix(self, targets: list[int], sources: list[int], all_segs: bool,
             src_ports: bool = False) -> int:
        """Puts every vertex of the source faces (with `src_ports` every port point too)
        that lies on an edge of a target face into that edge. Without `all_segs` a road
        face's edges between two port points only (its ends), every edge of the others."""
        H = _Hash()
        for fi in sources:
            for r in self.faces[fi].rings:
                for v in r:
                    H.add(v, fi)
        if src_ports:
            for v, fi in self.port_owner.items():
                H.add(v, fi)
        n = 0
        for fi in targets:
            f = self.faces[fi]
            if not f.rings:
                continue
            road_face = f.kind in ROAD_KINDS
            new_rings = []
            for r in f.rings:
                out = []
                k = len(r)
                for i in range(k):
                    p, q = r[i], r[(i + 1) % k]
                    out.append(p)
                    if road_face and not all_segs and not (p in self.ports and
                                                           q in self.ports):
                        continue
                    hits = []
                    for x, y, gi in H.near(p, q):
                        if gi == fi:
                            continue
                        v = (x, y)
                        if v == p or v == q or not _on_seg(p, q, v):
                            continue
                        if not self.compatible(f, self.faces[gi], v):
                            continue
                        hits.append((_param(p, q, v), v))
                    if hits:
                        hits.sort()
                        prev = None
                        for _, v in hits:
                            if v != prev:
                                out.append(v)
                                n += 1
                            prev = v
                new_rings.append(_clean(out))
            f.rings = [r for r in new_rings if len(r) >= 3]
        return n

    # -- overlaps ----------------------------------------------------------------------

    def _geoms(self, idx):
        out = []
        for i in idx:
            if not self.faces[i].rings:
                out.append(Polygon())
                continue
            g = self.faces[i].poly()
            if not g.is_valid:
                g = union(polys(shapely.make_valid(g)))
            out.append(g)
        return np.array(out, dtype=object)

    def overlaps(self) -> list[tuple[int, int, float]]:
        """Pairs of faces whose interiors overlap at one level: (greater, lesser, m2)."""
        idx = [i for i, f in enumerate(self.faces) if f.rings]
        geoms = self._geoms(idx)
        tree = shapely.STRtree(geoms)
        a, b = tree.query(geoms, predicate="intersects")
        keep = a < b
        a, b = a[keep], b[keep]
        if not len(a):
            return []
        rel = shapely.relate_pattern(geoms[a], geoms[b], "2********")
        out = []
        for i, j in zip(a[rel].tolist(), b[rel].tolist()):
            fi, fj = idx[i], idx[j]
            F, Gf = self.faces[fi], self.faces[fj]
            ov = shapely.intersection(geoms[i], geoms[j])
            area = float(ov.area)
            if area < 1e-6:
                continue
            c = ov.representative_point()
            if not self.related(F, Gf) and \
                    abs(self.zf(F, c.x, c.y) - self.zf(Gf, c.x, c.y)) > SAME_Z_M:
                continue        # (one over the other: an overpass, a tunnel under a road)
            hi, lo = (fi, fj) if self.above(F, Gf) else (fj, fi)
            out.append((hi, lo, area))
        return out

    @staticmethod
    def above(f: Face, g: Face) -> bool:
        """Whether f keeps an overlap with g (priority, then the lesser id)."""
        if f.prio != g.prio:
            return f.prio > g.prio
        return f.fid < g.fid

    def resolve(self) -> None:
        """Faces at one level that overlap: the lesser loses the overlap to the greater
        (their shared edge a seam), its new vertices put onto the faces around it."""
        n_pairs = n_cut = 0
        area = 0.0
        for _ in range(3):
            ovs = self.overlaps()
            if not ovs:
                break
            by_lo: dict = {}
            for hi, lo, a in ovs:
                by_lo.setdefault(lo, set()).add(hi)
                area += a
            n_pairs += len(ovs)
            clipped = []
            extra = []
            cutters = {lo: union(list(self._geoms(sorted(his)))) for lo, his in by_lo.items()}
            for lo in sorted(by_lo):
                F = self.faces[lo]
                cut = cutters[lo]
                g = _ov(shapely.difference, self._geoms([lo])[0], cut)
                ps = sorted((rs for rs in mm_polys(g) if _rs_area(rs) >= 100), key=_rs_key)
                if not ps:
                    F.rings = []
                    n_cut += 1
                    continue
                F.rings = ps[0]
                clipped.append(lo)
                for rs in ps[1:]:
                    if rs:
                        fid, band = self._fresh(F)
                        extra.append(Face(fid, F.owner, F.kind, band, F.layer, F.prio,
                                          rs, F.road, F.unit, F.legs, F.span))
            for e in extra:
                self.faces.append(e)
                clipped.append(len(self.faces) - 1)
            n_cut += len(clipped)
            near = self._near(clipped)
            self.tfix(near, clipped, all_segs=True)
            self.tfix(clipped, near, all_segs=True)
        self.faces = [f for f in self.faces if f.rings]
        self.stats.update({"overlaps_cut": n_pairs, "overlap_m2": round(area, 3),
                           "faces_cut": n_cut})

    def fill_gaps(self) -> int:
        """A hole in a layer's pavement smaller than GAP_M2 (where faces built apart leave
        a sliver between them) joins the face around it it shares most boundary with."""
        n = 0
        layers = sorted({f.layer for f in self.faces if f.rings})
        for lv in layers:
            idx = [i for i, f in enumerate(self.faces) if f.rings and f.layer == lv]
            geoms = list(self._geoms(idx))
            u = union(geoms)
            holes = []
            for p in polys(u):
                for h in p.interiors:
                    hp = Polygon(h)
                    if 1e-6 <= hp.area < GAP_M2:
                        holes.append(hp)
            if not holes:
                continue
            tree = shapely.STRtree(geoms)
            for hp in sorted(holes, key=lambda h: h.bounds):
                best = None
                for k in sorted(tree.query(hp.buffer(0.01)).tolist()):
                    shared = shapely.intersection(geoms[k].boundary, hp.buffer(0.002)).length
                    if shared > 0 and (best is None or shared > best[0] + 1e-9):
                        best = (shared, k)
                if best is None:
                    continue
                fi = idx[best[1]]
                F = self.faces[fi]
                g = _ov(shapely.union, geoms[best[1]], hp)
                ps = sorted((rs for rs in mm_polys(g) if _rs_area(rs) >= 100), key=_rs_key)
                if ps:
                    F.rings = ps[0]
                    geoms[best[1]] = F.poly()
                    n += 1
        if n:
            near = list(range(len(self.faces)))
            self.tfix(near, near, all_segs=True)
        self.stats["gaps_filled"] = n
        return n

    def split_invalid(self) -> int:
        """A face the shared-edge pass left self-touching is split at the touch."""
        out = []
        n = 0
        for f in self.faces:
            if not f.rings:
                continue
            g = f.poly()
            if g.is_valid:
                out.append(f)
                continue
            n += 1
            ps = sorted((rs for rs in mm_polys(g) if _rs_area(rs) >= 100), key=_rs_key)
            if not ps:
                continue
            f.rings = ps[0]
            out.append(f)
            for rs in ps[1:]:
                fid, band = self._fresh(f)
                out.append(Face(fid, f.owner, f.kind, band, f.layer, f.prio, rs, f.road,
                                f.unit, f.legs, f.span))
        self.faces = out
        self.stats["faces_split"] = n
        return n

    def _fresh(self, F: Face) -> tuple[str, str]:
        """An id for another part of a face that an overlap cut in two."""
        if getattr(self, "_taken", None) is None:
            self._taken = {f.fid for f in self.faces}
        k = 1
        while f"{F.fid}_{_letters(k)}" in self._taken:
            k += 1
        self._taken.add(f"{F.fid}_{_letters(k)}")
        return f"{F.fid}_{_letters(k)}", f"{F.band}_{_letters(k)}"

    def _near(self, idx: list[int]) -> list[int]:
        boxes = [self.faces[i].poly().envelope.buffer(0.01) for i in idx
                 if self.faces[i].rings]
        if not boxes:
            return []
        live = [i for i, f in enumerate(self.faces) if f.rings]
        tree = shapely.STRtree([self.faces[i].poly().envelope for i in live])
        hit = set()
        for b in boxes:
            for k in tree.query(b).tolist():
                hit.add(live[k])
        return sorted(hit)

    # -- edges -------------------------------------------------------------------------

    def extract(self) -> None:
        """Vertices (one per 1 mm cell and level), directed segments matched with their
        twins, edges (maximal runs between the same two faces), face boundaries as edges."""
        faces = self.faces
        use: dict = {}
        for fi, f in enumerate(faces):
            seen = set()
            for r in f.rings:
                for v in r:
                    if v not in seen:
                        seen.add(v)
                        use.setdefault(v, []).append(fi)
        vid: dict = {}           # (face, point) -> vertex id
        self.vpos: dict = {}     # vertex id -> point
        split = 0
        for v in sorted(use):
            fis = use[v]
            groups = self._levels(v, fis)
            if len(groups) > 1:
                split += 1
            for k, g in enumerate(groups):
                name = vtok(v) if k == 0 else f"{vtok(v)}.{k + 1}"
                self.vpos[name] = v
                for fi in g:
                    vid[(fi, v)] = name
        self.vid = vid
        rings = []
        seg: dict = {}
        dup = 0
        for fi, f in enumerate(faces):
            rr = []
            for r in f.rings:
                ids = [vid[(fi, v)] for v in r]
                rr.append(ids)
                for i in range(len(ids)):
                    key = (ids[i], ids[(i + 1) % len(ids)])
                    if key in seg and seg[key] != fi:
                        dup += 1
                        continue
                    seg[key] = fi
            rings.append(rr)
        nbr: dict = {}
        for u, w in seg:
            nbr.setdefault(u, set()).add(w)
            nbr.setdefault(w, set()).add(u)

        def twin(u, w):
            return seg.get((w, u), -1)
        edges: dict = {}
        face_refs = []
        for fi, rr in enumerate(rings):
            refs = []
            for ids in rr:
                k = len(ids)
                pp = [self._portish(ids[i]) for i in range(k)]
                lab = [(fi, twin(ids[i], ids[(i + 1) % k]), pp[i] and pp[(i + 1) % k])
                       for i in range(k)]
                brk = [i for i in range(k) if lab[i - 1] != lab[i] or len(nbr[ids[i]]) != 2]
                if not brk:
                    i0 = min(range(k), key=lambda i: self._vkey(ids[i]))
                    brk = [i0]
                runs = []
                for j, i0 in enumerate(brk):
                    i1 = brk[(j + 1) % len(brk)]
                    n = (i1 - i0) % k or k
                    runs.append([ids[(i0 + t) % k] for t in range(n + 1)])
                ring_refs = []
                for chain in runs:
                    canon, fwd = self._canon(chain)
                    eid = f"{canon[0]}.{canon[1]}"
                    if eid not in edges:
                        g = twin(chain[0], chain[1])
                        kind = self._kind(fi, g)
                        if kind == "port" and not all(self._portish(v) for v in chain):
                            kind = "seam"     # (a face reaching past a port, along the road)
                        edges[eid] = (kind, canon)
                    ring_refs.append(eid if fwd else "-" + eid)
                refs.append(ring_refs)
            face_refs.append(refs)
        # (an edge two faces use is no right of way's edge, whichever face named it first)
        uses: dict = {}
        for refs in face_refs:
            for ring_refs in refs:
                for ref in ring_refs:
                    uses[ref.lstrip("-")] = uses.get(ref.lstrip("-"), 0) + 1
        for eid, (kind, canon) in list(edges.items()):
            if kind == "outer" and uses.get(eid, 0) >= 2:
                edges[eid] = ("seam", canon)
        self.edges = edges
        self.face_refs = face_refs
        self.vrings = rings
        self.stats.update({"split_vertices": split, "duplicate_segments": dup})

    def _portish(self, name: str) -> bool:
        """Whether a vertex is a port point (of a road's end, a bend's end, a port line two
        roads share)."""
        p = self.vpos[name]
        return p in self.ports or p in self.level

    def _levels(self, v, fis) -> list[list[int]]:
        """The faces using a point, grouped by level (faces that meet are one level)."""
        if len(fis) == 1:
            return [list(fis)]
        par = {fi: fi for fi in fis}

        def find(x):
            while par[x] != x:
                par[x] = par[par[x]]
                x = par[x]
            return x
        for i in range(len(fis)):
            for j in range(i + 1, len(fis)):
                if self.related(self.faces[fis[i]], self.faces[fis[j]]):
                    par[find(fis[i])] = find(fis[j])
        comps: dict = {}
        for fi in fis:
            comps.setdefault(find(fi), []).append(fi)
        if len(comps) == 1:
            return [list(fis)]
        x, y = m(v[0]), m(v[1])
        cs = sorted((self.zf(self.faces[g[0]], x, y), sorted(g)) for g in comps.values())
        out = [list(cs[0][1])]
        z0 = cs[0][0]
        for z, g in cs[1:]:
            if z - z0 <= STEP_Z_M:
                out[-1] += g
            else:
                out.append(list(g))
                z0 = z
        return [sorted(g) for g in out]

    def _vkey(self, name: str):
        p = self.vpos[name]
        return (p[0], p[1], name)

    def _canon(self, chain: list) -> tuple[list, bool]:
        """An edge's vertices from its lesser end (a closed one from its least vertex,
        toward its lesser neighbor), and whether that is the face's direction."""
        a, b = chain[0], chain[-1]
        if a != b:
            if self._vkey(a) <= self._vkey(b):
                return chain, True
            return chain[::-1], False
        body = chain[:-1]
        i0 = min(range(len(body)), key=lambda i: self._vkey(body[i]))
        fwd = body[i0:] + body[:i0] + [body[i0]]
        rev = fwd[::-1]
        rev = [rev[-1]] + rev[:-1] if rev[0] != body[i0] else rev
        if self._vkey(fwd[1]) <= self._vkey(rev[1]):
            return fwd, True
        return rev, False

    def _kind(self, fi: int, gi: int) -> str:
        if gi < 0:
            return "outer"
        f, g = self.faces[fi], self.faces[gi]
        fr, gr = f.kind in ROAD_KINDS, g.kind in ROAD_KINDS
        if fr and gr:
            return "band" if f.road == g.road else "port"
        if fr != gr:
            road, other = (f, g) if fr else (g, f)
            if other.kind == "bend" and other.road == road.road:
                return "port"
            if other.unit is not None and road.road in other.legs:
                return "port"
            return "seam"
        if f.unit is not None and f.unit == g.unit:
            return "curb"
        bend, other = (f, g) if f.kind == "bend" else (g, f)
        if bend.kind == "bend" and other.unit is not None and bend.road in other.legs:
            return "port"       # (a bend that reaches its junction)
        return "seam"

    # -- heights -----------------------------------------------------------------------

    def heights(self) -> None:
        """One height per vertex (over sea level, `self.abs`): a road's at the station of
        each of its vertices; a port line where two roads go on as each other at one of
        them; a junction's curb lines between its ports by length along its outline; a
        corner pad's property line likewise."""
        z: dict = {}
        faces = self.faces
        # (a ribbon vertex a junction's face shares, where the junction reaches over the
        # ribbon short of its port: the junction's surface there, its port's height)
        jv: dict = {}
        for fi, f in enumerate(faces):
            if f.kind in JUNCTION_KINDS and f.road is None:
                for ids in self.vrings[fi]:
                    for name in ids:
                        jv.setdefault(name, set()).add(f.unit)

        def at_port(rd, name, s):
            ends = [st for st, uid in ((rd.a, rd.unit_a), (rd.path.L - rd.b, rd.unit_b))
                    if uid is not None and uid in jv.get(name, ())]
            return min(ends, key=lambda st: abs(st - s)) if ends else s
        for fi, f in enumerate(faces):
            if f.road is None or f.kind == "bend":
                continue
            rd = self.roads[f.road]
            for r, ids in zip(f.rings, self.vrings[fi]):
                for v, name in zip(r, ids):
                    if name in z:
                        continue
                    lv = self.level.get(v)
                    if lv is not None:
                        z[name] = self.roads[lv[0]].z(lv[1])
                        continue
                    s = rd.known.get(v)
                    if s is not None:
                        z[name] = rd.z(at_port(rd, name, s))
        for fi, f in enumerate(faces):
            if f.road is None or f.kind == "bend":
                continue
            rd = self.roads[f.road]
            # (a ribbon lies between its road's cuts: a vertex of one past a bend in the road
            # inside its junction projects onto its port, not beyond it)
            s0, s1 = f.span if f.span else (rd.a, max(rd.a, rd.path.L - rd.b))
            for r, ids in zip(f.rings, self.vrings[fi]):
                for v, name in zip(r, ids):
                    if name not in z:
                        s = rd.path.project(m(v[0]), m(v[1]), s0, s1)
                        z[name] = rd.z(at_port(rd, name, s))
        # (a port no ribbon reaches, a bend's end at its junction: its road's height there)
        for fi, f in enumerate(faces):
            if f.kind not in JUNCTION_KINDS:
                continue
            own = [f.road] if f.road is not None else sorted(f.legs)
            for r, ids in zip(f.rings, self.vrings[fi]):
                for v, name in zip(r, ids):
                    if name in z:
                        continue
                    for sid in own:
                        rd = self.roads.get(sid)
                        s = rd.known.get(v) if rd is not None else None
                        if s is not None:
                            z[name] = rd.z(s)
                            break
        # (a cluster's curbs longer than LONG_CURB_M between two ports, along its inner
        # roads: their heights there, kept between the two ports' heights)
        for fi, f in enumerate(faces):
            u = self.units.get(f.unit) if f.road is None else None
            if f.kind == "junction" and u is not None and u.inner:
                for r, ids in zip(f.rings, self.vrings[fi]):
                    self._long_curbs(u, r, ids, z)
        for kinds in (("junction", "bulb", "bend"), ("corner",)):
            for fi, f in enumerate(faces):
                if f.kind not in kinds:
                    continue
                for r, ids in zip(f.rings, self.vrings[fi]):
                    self._along_ring(f, r, ids, z)
        for fi, f in enumerate(faces):
            for r, ids in zip(f.rings, self.vrings[fi]):
                for v, name in zip(r, ids):
                    if name not in z:
                        z[name] = self.zf(f, m(v[0]), m(v[1]))
        self.abs = z

    def _long_curbs(self, u: Unit, r, ids, z: dict) -> None:
        k = len(ids)
        known = [i for i in range(k) if ids[i] in z]
        if len(known) < 2:
            return
        cum = [0.0]
        for i in range(k):
            a, b = r[i], r[(i + 1) % k]
            cum.append(cum[-1] + math.hypot((b[0] - a[0]) / 1000.0, (b[1] - a[1]) / 1000.0))
        per = cum[-1]
        new = {}
        for j, a in enumerate(known):
            b = known[(j + 1) % len(known)]
            span = (cum[b] - cum[a]) % per if b != a else per
            if span < LONG_CURB_M:
                continue
            lo, hi = sorted((z[ids[a]], z[ids[b]]))
            i = (a + 1) % k
            while i != b:
                t = (cum[i] - cum[a]) % per
                if ids[i] not in z and LONG_MARGIN_M <= t <= span - LONG_MARGIN_M:
                    zi = self._inner_z(u, m(r[i][0]), m(r[i][1]), INNER_NEAR_M)
                    if zi is not None:
                        new[ids[i]] = min(max(zi, lo), hi)
                i = (i + 1) % k
        z.update(new)

    def _along_ring(self, f: Face, r, ids, z: dict) -> None:
        k = len(ids)
        known = [i for i in range(k) if ids[i] in z]
        u = self.units.get(f.unit) if f.road is None else None
        if len(known) < 2 and u is not None and u.inner:
            # (a ring no two ports anchor, a hole in a cluster between its inner roads: the
            # nearest inner road's height at each vertex)
            for v, name in zip(r, ids):
                if name not in z:
                    z[name] = self._inner_z(u, m(v[0]), m(v[1]))
            return
        if not known:
            for v, name in zip(r, ids):
                z[name] = self.zf(f, m(v[0]), m(v[1]))
            return
        cum = [0.0]
        for i in range(k):
            a, b = r[i], r[(i + 1) % k]
            dx, dy = (b[0] - a[0]) / 1000.0, (b[1] - a[1]) / 1000.0
            cum.append(cum[-1] + math.sqrt(dx * dx + dy * dy))
        per = cum[-1]
        new = {}
        for j, a in enumerate(known):
            b = known[(j + 1) % len(known)]
            span = (cum[b] - cum[a]) % per if b != a else per
            i = (a + 1) % k
            while i != b:
                if ids[i] not in z and ids[i] not in new:
                    t = ((cum[i] - cum[a]) % per) / span if span > 0 else 0.0
                    new[ids[i]] = z[ids[a]] + t * (z[ids[b]] - z[ids[a]])
                i = (i + 1) % k
        z.update(new)

    # -- interior samples --------------------------------------------------------------

    def samples(self) -> int:
        """Interior samples of every junction, corner, bulb and bend face whose boundary is
        not one plane: a SAMPLE_M grid strictly inside (SAMPLE_IN_M from its boundary), each
        by mean value coordinates of its boundary's heights."""
        n = 0
        for fi, f in enumerate(self.faces):
            f.samples = []
            if f.kind not in JUNCTION_KINDS:
                continue
            pts = [(m(v[0]), m(v[1]), self.abs[name])
                   for r, ids in zip(f.rings, self.vrings[fi]) for v, name in zip(r, ids)]
            if _planar(pts):
                continue
            g = f.poly()
            if not g.is_valid:
                continue
            inner = g.buffer(-SAMPLE_IN_M, join_style="mitre")
            if inner.is_empty:
                continue
            x0, y0, x1, y1 = inner.bounds
            i0, i1 = math.ceil(x0 / SAMPLE_M), math.floor(x1 / SAMPLE_M)
            j0, j1 = math.ceil(y0 / SAMPLE_M), math.floor(y1 / SAMPLE_M)
            if i1 < i0 or j1 < j0:
                continue
            gx, gy = np.meshgrid(np.arange(i0, i1 + 1) * SAMPLE_M,
                                 np.arange(j0, j1 + 1) * SAMPLE_M)
            gx, gy = gx.ravel(), gy.ravel()
            ins = shapely.contains_xy(inner, gx, gy)
            gx, gy = gx[ins], gy[ins]
            if not len(gx):
                continue
            rings = [[(m(v[0]), m(v[1]), self.abs[name]) for v, name in zip(r, ids)]
                     for r, ids in zip(f.rings, self.vrings[fi])]
            zs = mvc(rings, gx, gy)
            f.samples = [(float(x), float(y), float(zz)) for x, y, zz in zip(gx, gy, zs)]
            n += len(gx)
        return n


def ring_heights(r: list, known: dict) -> list:
    """Heights of a ring's vertices: the known ones, the rest linear by length along the
    ring between them (a junction's curb lines between its ports); None where none is
    known."""
    k = len(r)
    idx = [i for i in range(k) if r[i] in known]
    if not idx:
        return [None] * k
    cum = [0.0]
    for i in range(k):
        a, b = r[i], r[(i + 1) % k]
        dx, dy = (b[0] - a[0]) / 1000.0, (b[1] - a[1]) / 1000.0
        cum.append(cum[-1] + math.sqrt(dx * dx + dy * dy))
    per = cum[-1]
    out = [known.get(v) for v in r]
    for j, a in enumerate(idx):
        b = idx[(j + 1) % len(idx)]
        span = (cum[b] - cum[a]) % per if b != a else per
        i = (a + 1) % k
        while i != b:
            if out[i] is None:
                t = ((cum[i] - cum[a]) % per) / span if span > 0 else 0.0
                out[i] = known[r[a]] + t * (known[r[b]] - known[r[a]])
            i = (i + 1) % k
    return out


def step_tol(d: float) -> float:
    """How much of a height difference between two boundary vertices d m apart is a step
    on the 1 mm grid, not a grade: 2 mm, STEP_TOL_M under a meter (a step, not a slope)."""
    return STEP_TOL_M if d < 1.0 else 0.002


def unit_grade(plan, jid: str, port_z: dict) -> float:
    """How steep a junction's carriageway face would be with its ports at these heights
    ({(segment id, at start): z}): its curbs along its outline between the ports, its
    interior by mean value coordinates on the SAMPLE_M grid, as `build_map` draws it
    (before the shared-edge pass): the steepest slope along the outline, between
    neighboring samples and from a sample to the outline within SAMPLE_M."""
    u = plan.units.get(jid)
    C, R = plan.regions.get(jid, (None, None))
    if u is None or C is None or C.is_empty:
        return 0.0
    known: dict = {}
    for x in u.legs:
        rd = plan.roads.get(x.seg["id"])
        z = port_z.get((x.seg["id"], x.at_start))
        if rd is None or z is None:
            continue
        _, pts = rd.port("start" if x.at_start else "end")
        for w, p in pts:
            known[p] = z
    worst = 0.0
    # (the carriageway first, its curbs then known to the corner pads)
    parts = polys(C)
    pads = polys(_ov(shapely.difference, R, C)) if R is not None and not R.is_empty else []
    for poly in parts + [q for q in pads if q.area >= 1.0]:
        rs = rings_of(poly)
        if not rs:
            continue
        hs = [ring_heights(r, known) for r in rs]
        if any(h is None for hh in hs for h in hh):
            continue
        for r, hh in zip(rs, hs):
            for v, h in zip(r, hh):
                known.setdefault(v, h)
        bpts = []
        for r, hh in zip(rs, hs):
            for i in range(len(r)):
                a, b = r[i], r[(i + 1) % len(r)]
                d = math.dist(a, b) / 1000.0
                bpts.append((a[0] / 1000.0, a[1] / 1000.0, hh[i]))
                if d >= 0.25:
                    worst = max(worst, (abs(hh[i] - hh[(i + 1) % len(r)]) - step_tol(d)) / d)
        if max(p[2] for p in bpts) - min(p[2] for p in bpts) <= 0.005:
            continue
        inner = poly.buffer(-SAMPLE_IN_M, join_style="mitre")
        if inner.is_empty:
            continue
        x0, y0, x1, y1 = inner.bounds
        gx, gy = np.meshgrid(np.arange(math.ceil(x0 / SAMPLE_M), math.floor(x1 / SAMPLE_M) + 1)
                             * SAMPLE_M,
                             np.arange(math.ceil(y0 / SAMPLE_M), math.floor(y1 / SAMPLE_M) + 1)
                             * SAMPLE_M)
        gx, gy = gx.ravel(), gy.ravel()
        if not len(gx):
            continue
        ins = shapely.contains_xy(inner, gx, gy)
        gx, gy = gx[ins], gy[ins]
        if not len(gx):
            continue
        rings3 = [[(p[0] / 1000.0, p[1] / 1000.0, h) for p, h in zip(r, hh)]
                  for r, hh in zip(rs, hs)]
        zs = mvc(rings3, gx, gy)
        cell = {(round(x / SAMPLE_M), round(y / SAMPLE_M)): z for x, y, z in
                zip(gx.tolist(), gy.tolist(), zs.tolist())}
        for (i, j), z in cell.items():
            for di, dj in ((1, 0), (0, 1)):
                o = cell.get((i + di, j + dj))
                if o is not None:
                    worst = max(worst, (abs(z - o) - 0.002) / SAMPLE_M)
        # (from each sample to the outline within SAMPLE_M, across the face only, as
        # `pavement_checks.face_grade` measures it)
        B = np.array(bpts)
        pairs = []
        for x, y, z in zip(gx.tolist(), gy.tolist(), zs.tolist()):
            d = np.sqrt((B[:, 0] - x) ** 2 + (B[:, 1] - y) ** 2)
            for k in np.nonzero((d <= SAMPLE_M) & (d >= 0.25))[0].tolist():
                pairs.append(((x, y, z), (float(B[k, 0]), float(B[k, 1]), float(B[k, 2]))))
        if pairs:
            segs = shapely.linestrings([[a[:2], b[:2]] for a, b in pairs])
            ok = shapely.covers(poly.buffer(0.01), segs)
            for (a, b), inside in zip(pairs, ok.tolist()):
                if inside:
                    worst = max(worst, (abs(a[2] - b[2]) - 0.002) / math.dist(a[:2], b[:2]))
    return worst


def _planar(pts) -> bool:
    """Whether 3D points lie on one plane within FLAT_MM (the plane through the first point,
    the farthest from it and the farthest from their line)."""
    if len(pts) < 4:
        return True
    zs = [p[2] for p in pts]
    if max(zs) - min(zs) <= FLAT_MM / 1000.0:
        return True
    p0 = pts[0]
    p1 = max(pts, key=lambda p: (p[0] - p0[0]) ** 2 + (p[1] - p0[1]) ** 2)
    ux, uy = p1[0] - p0[0], p1[1] - p0[1]

    def off(p):
        return abs((p[0] - p0[0]) * uy - (p[1] - p0[1]) * ux)
    p2 = max(pts, key=off)
    a = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    b = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
    nx = a[1] * b[2] - a[2] * b[1]
    ny = a[2] * b[0] - a[0] * b[2]
    nz = a[0] * b[1] - a[1] * b[0]
    if abs(nz) < 1e-12:
        return False
    for p in pts:
        zz = p0[2] - (nx * (p[0] - p0[0]) + ny * (p[1] - p0[1])) / nz
        if abs(zz - p[2]) > FLAT_MM / 1000.0:
            return False
    return True


def mvc(rings, xs, ys) -> np.ndarray:
    """Mean value coordinates (Floater 2003, with holes: every boundary edge counts) of the
    heights on a face's rings at the points (xs, ys) strictly inside it: weights
    w_i = (tan(a_{i-1}/2) + tan(a_i/2)) / r_i, tan(a/2) = (u x v) / (|u||v| + u . v)
    for the vectors u, v from the point to two consecutive vertices. Elementwise numpy
    arithmetic and square roots only."""
    num = np.zeros(len(xs))
    den = np.zeros(len(xs))
    for r in rings:
        k = len(r)
        X = np.array([p[0] for p in r])
        Y = np.array([p[1] for p in r])
        Z = np.array([p[2] for p in r])
        ux = X[None, :] - xs[:, None]
        uy = Y[None, :] - ys[:, None]
        rr = np.sqrt(ux * ux + uy * uy)
        nx = np.roll(ux, -1, axis=1)
        ny = np.roll(uy, -1, axis=1)
        nr = np.roll(rr, -1, axis=1)
        cr = ux * ny - uy * nx
        dt = ux * nx + uy * ny
        t = cr / (rr * nr + dt)          # tan(a_i / 2) of the edge from vertex i to i + 1
        w = (np.roll(t, 1, axis=1) + t) / rr
        for i in range(k):              # (elementwise, in a fixed order: no reductions)
            num += w[:, i] * Z[i]
            den += w[:, i]
    return num / den


# ---------------------------------------------------------------------------
# The map of a network
# ---------------------------------------------------------------------------

class Plan:
    """The faces of a road network, before heights: every road's ribbons between its cuts
    (`Unit` legs carry them), bends, every junction's region."""

    def __init__(self, segments: list[dict], pos: dict, units: list[Unit]):
        self.roads: dict = {}
        at: dict = {}
        for s in segments:
            if s["road_class"] == "footbridge":
                continue
            self.roads[s["id"]] = Road(s)
            at.setdefault(s["start"], []).append((s["id"], "start"))
            at.setdefault(s["end"], []).append((s["id"], "end"))
        self.inner = {sid for u in units for sid in u.inner}
        jnodes = {n for u in units for n in u.nodes}
        for u in units:
            for x in u.legs:
                rd = self.roads.get(x.seg["id"])
                if rd is None or x.seg["id"] in self.inner:
                    continue
                if x.at_start:
                    rd.a, rd.unit_a = x.cut, u.jid
                else:
                    rd.b, rd.unit_b = x.cut, u.jid
        end_frames(self.roads, at, jnodes)
        self.at, self.pos = at, pos
        self.units = {u.jid: u for u in units}
        self.faces: list[Face] = []
        self.regions: dict = {}
        self.n_bends = 0
        for sid in sorted(self.roads):
            rd = self.roads[sid]
            if sid in self.inner:
                rd.ends, rd.known = [], {}
                continue
            fs, bends = road_faces(rd)
            self.faces += fs
            if bends:
                self.n_bends += len(bends)
                self.faces += bend_faces(rd, bends)
        for u in units:
            fs, C, R = unit_faces(u, self.roads, pos)
            self.faces += fs
            self.regions[u.jid] = (C, R)
        # one height on the port line where two roads go on as each other (the lesser id's)
        self.level: dict = {}
        for nid in sorted(at):
            if nid in jnodes:
                continue
            ends = sorted(e for e in at[nid] if e[0] in self.roads and e[0] not in self.inner)
            if len(ends) != 2:
                continue
            sa = ends[0][0]
            ra = self.roads[sa]
            s_a = 0.0 if ends[0][1] == "start" else ra.path.L
            for sid, which in ends:
                rd = self.roads[sid]
                s = 0.0 if which == "start" else rd.path.L
                for st, pts in rd.ends:
                    if abs(st - s) < 1e-9:
                        for p in pts:
                            self.level.setdefault(p, (sa, s_a))
        self.adj: dict = {}
        for nid, ends in at.items():
            ids = sorted({sid for sid, _ in ends})
            for a in ids:
                self.adj.setdefault(a, set()).update(x for x in ids if x != a)
        for u in units:
            for x in u.legs:
                sid = x.seg["id"]
                self.adj.setdefault(u.jid, set()).add(sid)
                self.adj.setdefault(sid, set()).add(u.jid)
            for sid in u.inner:
                self.adj.setdefault(u.jid, set()).add(sid)
                self.adj.setdefault(sid, set()).add(u.jid)
            u.ports = []
            for x in u.legs:
                rd = self.roads.get(x.seg["id"])
                if rd is None or x.seg["id"] in self.inner:
                    continue
                s, pts = rd.port("start" if x.at_start else "end")
                a, b = pts[0][1], pts[-1][1]
                u.ports.append((rd.sid, rd.z(s), (m(a[0]), m(a[1])), (m(b[0]), m(b[1]))))


@dataclass
class Map:
    faces: list            # model rows of `pavement`
    net: dict              # `pavement_net`: vertices and edges
    junctions: dict        # junction id -> (polygon row, edge_z or None)
    stats: dict


def build_map(segments: list[dict], nodes: list[dict], units: list[Unit],
              ground=None) -> Map:
    """The pavement map of a graded network (`ground`: the finished ground, a
    `terrain.Field` on the 1 cm grid as the model stores it, or None on a flat city)."""
    pos = {n["id"]: (n["position"][0], n["position"][1]) for n in nodes}
    plan = Plan(segments, pos, units)
    A = Assembly(plan.faces, plan.roads, plan.units, plan.adj, ground, plan.level)
    n_snap = A.snap_ports()
    idx = list(range(len(A.faces)))
    junc = [i for i, f in enumerate(A.faces) if f.kind in JUNCTION_KINDS]
    n_fix = A.tfix(idx, junc, all_segs=True, src_ports=True)
    A.resolve()
    if A.fill_gaps():
        A.resolve()         # (what the gaps' own shared-edge pass leaves overlapping)
    A.split_invalid()
    A.extract()
    A.heights()
    n_samp = A.samples()
    return _rows(A, plan, nodes, ground, {"snapped": n_snap, "shared_points": n_fix,
                                          "samples": n_samp, "bends": plan.n_bends})


def _q3(v: float) -> float:
    return math.floor(v * 1000.0 + 0.5) / 1000.0


def _rows(A: Assembly, plan: Plan, nodes: list[dict], ground, st: dict) -> Map:
    gat = (lambda x, y: 0.0) if ground is None else ground.at
    used = set()
    for rr in A.vrings:
        for ids in rr:
            used.update(ids)
    verts = []
    for name in sorted(used):
        x, y = A.vpos[name]
        verts.append({"id": name, "p": (m(x), m(y)),
                      "z": _q3(A.abs[name] - gat(m(x), m(y)))})
    edges = [{"id": eid, "kind": kind, "v": chain}
             for eid, (kind, chain) in sorted(A.edges.items())]
    faces = []
    for fi, f in enumerate(A.faces):
        faces.append({"id": f.fid, "type": f"pavement.{f.kind}", "owner_id": f.owner,
                      "kind": f.kind, "band": f.band, "layer": f.layer,
                      "rings": A.face_refs[fi],
                      "samples": [(_q3(x), _q3(y), _q3(z - gat(x, y)))
                                  for x, y, z in f.samples],
                      "attrs": {}})
    faces.sort(key=lambda r: r["id"])
    node = {n["id"]: n for n in nodes}
    jrows = {}
    for fi, f in enumerate(A.faces):
        if f.unit is None or f.band != "jn":
            continue
        u = plan.units[f.unit]
        n = node[u.nodes[0]]
        base = n.get("ground_m") or 0.0
        ext = [(m(x), m(y)) for x, y in f.rings[0]]
        holes = [[(m(x), m(y)) for x, y in r] for r in f.rings[1:]]
        ez = [_q3(A.abs[name] - base) for name in A.vrings[fi][0]]
        zn = n["position"][2]
        flat = all(abs(z - zn) <= 0.005 for z in ez)
        jrows[f.unit] = ({"exterior": ext, "holes": holes}, None if flat else ez)
    kinds: dict = {}
    for f in faces:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    ek: dict = {}
    for e in edges:
        ek[e["kind"]] = ek.get(e["kind"], 0) + 1
    stats = {"faces": len(faces), "faces_by_kind": dict(sorted(kinds.items())),
             "vertices": len(verts), "edges": len(edges),
             "edges_by_kind": dict(sorted(ek.items())),
             "clusters": sum(1 for u in plan.units.values() if len(u.nodes) > 1),
             "nonplanar_faces": sum(1 for f in A.faces if f.samples),
             **st, **A.stats}
    return Map(faces, {"vertices": verts, "edges": edges}, jrows, stats)


def make(segments: list[dict], nodes: list[dict], junctions: list[dict], darch: dict,
         ground=None) -> Map:
    """The pavement map of a network's rows, and onto its junction rows: each junction's
    polygon its carriageway face's outline, `edge_z` the map's heights over its node's
    ground where it is not flat at its node's height."""
    units = units_from_rows(segments, nodes, junctions, darch)
    mp = build_map(segments, nodes, units, ground)
    for j in junctions:
        r = mp.junctions.get(j["id"])
        if r is None:
            continue
        j["polygon"], ez = r
        if ez is None:
            j.pop("edge_z", None)
        else:
            j["edge_z"] = ez
    return mp
