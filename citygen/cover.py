"""M16, ground cover: every piece of open land (not a building, road, sidewalk or water) and
what covers it, for stage 2's ground cover and grass (AG13). Runs on the finished city.

- **Open land** (`Ctx.zone`): per district (and the land outside every district) its ground
  minus the water, the roads' right of way (each segment's cross-section, as the blocks take
  it, and the junctions), the buildings' footprints, the solid site elements and the stairs,
  elevators, vents and portals standing on it. The pieces come from what the land belongs
  to, in this order: open spaces, lot yards (the lot minus what stands on it), flat site
  elements, megasites, and the land left between them (strips narrower than `SLIVER_M` there
  are curb corners of the right of way, not open land). So the pieces tile the open land
  once, and each depends only on its own district's entities and the roads at it.
- **Kind** (`model.COVER_KINDS`): by what it is (a park's lawn, a plaza's paving, a villa's
  garden, a shanty yard's bare dirt, a warehouse's gravel, a marsh, a beach's sand, a narrow
  setback's planted bed) and how it is kept (paving overgrown, lawns gone to meadow, meadows
  to wasteland as the maintenance falls; wet ground by the water a marsh); land outside every
  district is wild meadow (or marsh), whatever its maintenance.
- **Attributes**: maintenance (the district's wealth and danger, what the piece is), wear
  (its desire lines, the crowds of the street beside it), shade (a 4 m raster: the share of
  8 directions in which a building within 60 m rises above 45 degrees; 1 under a deck),
  moisture (1 at the water's edge, 0 from 60 m), slope (M13's finished ground).
- **Desire lines**: the walkway graph's paths across a lawn (worn by the crowds of the
  nearest street), and shortcuts people cut across a lawn between two walkway ends where the
  way round its edge is 1.35 times longer (two per piece at most, the busiest).

Ids: `<source>.gc.<anchor>` (`d03.lot.e512n88.gc.e510n90`), `<district>.gc.<anchor>` for land
between sources, `gc.<anchor>` outside every district; equal ids told apart by content.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import dmath as M
from . import geom as G
from . import ids as ID

SLIVER_M = 3.0              # land left between the sources narrower than this is curb corner
MIN_PIECE_M2 = 1.0
SHADE_CELL_M = 4.0
SHADE_REACH_M = 60.0
MOIST_M = 60.0
SAMPLE_M = 8.0              # moisture and slope samples
CROWD_REF = 60.0            # pedestrians per 100 m that wear a lawn through
DESIRE_W = {"path": 1.2, "shortcut": 1.5}
DETOUR = 1.35
SHORTCUT_MIN_M = 25.0
SHORTCUT_MIN_M2 = 600.0
LAWNS = ("mown_lawn", "park_lawn", "meadow", "wasteland")
PAVED = ("paving", "overgrown_paving")
SOLID_STRUCTURES = ("stair", "elevator", "vent", "portal")
FLAT_ELEMENTS = {"apron": "paving", "berth": "paving", "bus_bay": "paving", "drop_off": "paving",
                 "truck_gate": "paving", "plaza": "paving", "courtyard": "paving",
                 "lawn": "mown_lawn", "pitch": "mown_lawn", "rail_track": "gravel"}
OPEN_KIND = {"park": "park_lawn", "pocket_park": "park_lawn", "garden": "planted_bed",
             "green": "mown_lawn", "marsh": "marsh", "beach": "sand", "plaza": "paving",
             "market": "paving", "promenade": "paving", "courtyard": "paving",
             "podium_roof": "paving"}
SITE_KIND = {"freight_terminal": "paving", "spaceport": "gravel", "temple_complex": "gravel",
             "central_park": "park_lawn", "grand_plaza": "paving", "stadium": "paving",
             "transit_nexus": "paving"}
YARD_KIND = {"shanty_stack": "bare_dirt", "villa": "mown_lawn", "lab": "mown_lawn",
             "pavilion": "mown_lawn", "warehouse": "gravel", "yard": "gravel", "shed": "gravel",
             "hangar": "gravel", "container_yard": "gravel"}
LAWN_ARCHETYPES = ("residential_heights", "research_campus")
ROUGH_ARCHETYPES = ("industrial_port", "spaceport")
COVER_COLOR = {"mown_lawn": "#5fb85a", "park_lawn": "#3f9a4f", "meadow": "#9bbf5a",
               "marsh": "#4a8f86", "wasteland": "#8a7f52", "bare_dirt": "#8b5e3c",
               "gravel": "#a8a29a", "sand": "#e6cf8a", "planted_bed": "#c0559a",
               "overgrown_paving": "#6f7a5a", "paving": "#7d7f86"}
# maintenance: the district's wealth, less its danger, plus what the piece is (a megasite is
# a working facility, kept whatever its district)
CARE = {"open": 0.15, "lot": 0.0, "site": 0.3, "element": 0.3, "rest": -0.25}


@dataclass
class Src:
    """A piece's source: what it is the open land of."""
    id: str | None
    what: str            # open, lot, element, site, rest
    kind: str            # its cover kind before maintenance and moisture
    poly: object


class Ctx:
    def __init__(self, m):
        from . import water as WA
        from .streets import TUNNEL_SIDE_M

        P = G.from_model_poly
        self.m = m
        self.P = P
        self.dist = {d.id: d for d in m.districts}
        # right of way: every road at the ground (deck twins share their ground street's)
        row = []
        for s in m.road_segments:
            if "deck" in s.attrs and s.attrs.get("role") != "deck_ramp":
                continue
            w = s.width_m / 2.0 + (TUNNEL_SIDE_M if s.tunnel else 0.0)
            row.append(LineString(s.centerline).buffer(w, cap_style="flat", join_style="mitre",
                                                       mitre_limit=2.0))
        row = list(G.snap_many(np.array(row, dtype=object))) if row else []
        row += [P(j.polygon) for j in m.junctions if not j.level]
        self.row = [g for g in row if not g.is_empty]
        self.rtree = shapely.STRtree(self.row) if self.row else None
        hard = [P(b.footprint) for b in m.buildings if not b.level and b.footprint is not None]
        hard += [P(e.footprint) for e in m.site_elements
                 if e.footprint is not None and (e.masses or e.kind == "pond") and
                 e.kind not in FLAT_ELEMENTS]
        hard += [P(st.footprint) for st in m.structures
                 if st.kind in SOLID_STRUCTURES and st.footprint is not None]
        self.hard = [g for g in hard if not g.is_empty]
        self.htree = shapely.STRtree(self.hard) if self.hard else None
        self.wet = [b.poly for b in WA.bodies(m)]
        self.wtree = shapely.STRtree(self.wet) if self.wet else None
        self.land = G.union([P(p) for lnd in m.land for p in lnd.polygons])

    def _near(self, tree, geoms, poly) -> list:
        if tree is None:
            return []
        return [geoms[k] for k in sorted(int(i) for i in tree.query(poly,
                                                                     predicate="intersects"))]

    def clear(self, poly):
        """A polygon minus the water, the roads and what stands on it near it."""
        cut = self._near(self.wtree, self.wet, poly) + self._near(self.rtree, self.row, poly) + \
            self._near(self.htree, self.hard, poly)
        return G.diff(poly, G.union_local(cut)) if cut else poly


def _sources(cx: Ctx, did: str | None) -> list[Src]:
    m, P = cx.m, cx.P
    out = []
    for o in m.open_spaces:
        if o.district_id == did and not o.level and o.z_m <= 0.5:
            out.append(Src(o.id, "open", OPEN_KIND.get(o.kind, "park_lawn"), P(o.polygon)))
    yard = {}
    for b in m.buildings:
        if b.lot_id and not b.level and b.footprint is not None:
            a = G.area(P(b.footprint))
            cur = yard.get(b.lot_id)
            if cur is None or a > cur[0] or (a == cur[0] and b.type < cur[1]):
                yard[b.lot_id] = (a, b.type)
    arch = cx.dist[did].archetype if did in cx.dist else None
    for lt in m.lots:
        if lt.district_id != did or lt.level:
            continue
        t = yard.get(lt.id, (0.0, None))[1]
        t = t.split(".")[1] if t else None
        if t is None:
            kind = "gravel" if arch in ROUGH_ARCHETYPES else "wasteland"
        elif t in YARD_KIND:
            kind = YARD_KIND[t]
        elif arch in LAWN_ARCHETYPES:
            kind = "mown_lawn"
        else:
            kind = "paving"
        out.append(Src(lt.id, "lot", kind, P(lt.polygon)))
    sites = [s for s in m.megasites if s.district_id == did]
    for s in sites:
        for e in m.site_elements:
            if e.megasite_id == s.id and e.kind in FLAT_ELEMENTS and e.footprint is not None:
                out.append(Src(e.id, "element", FLAT_ELEMENTS[e.kind], P(e.footprint)))
    for s in sites:
        out.append(Src(s.id, "site", SITE_KIND.get(s.kind, "paving"), P(s.polygon)))
    return out


def _zones(cx: Ctx) -> list[tuple[str | None, object]]:
    m, P = cx.m, cx.P
    zs = [(d.id, P(d.polygon)) for d in m.districts]
    rest = G.diff(cx.land, G.union_local([z for _, z in zs])) if zs else cx.land
    if not rest.is_empty:
        zs.append((None, rest))
    return zs


def width_of(p) -> float:
    from .blocks import width_est

    return width_est(G.area(p), G.length(p.exterior))


def pieces(cx: Ctx) -> list[tuple]:
    """(district id, Src, polygon part) of every piece of open land."""
    out = []
    for did, zone in _zones(cx):
        srcs = _sources(cx, did)
        polys = [s.poly for s in srcs]
        stree = shapely.STRtree(polys) if polys else None
        clip = zone
        for k, s in enumerate(srcs):
            g = G.inter(s.poly, clip)
            if g.is_empty:
                continue
            # (earlier sources win where two overlap)
            earlier = [polys[j] for j in sorted(int(i) for i in stree.query(
                s.poly, predicate="intersects")) if j < k]
            if earlier:
                g = G.diff(g, G.union_local(earlier))
            g = cx.clear(g)
            for p in G.parts(g):
                if G.area(p) >= MIN_PIECE_M2:
                    out.append((did, s, p))
        # the land between the sources
        cut = cx._near(cx.rtree, cx.row, zone) + cx._near(cx.wtree, cx.wet, zone) + \
            cx._near(cx.htree, cx.hard, zone) + polys
        left = G.diff(zone, G.union_local(cut)) if cut else zone
        left = G.inter(left, cx.land)
        arch = cx.dist[did].archetype if did in cx.dist else None
        for p in G.parts(left):
            if G.area(p) < MIN_PIECE_M2 * 20 or width_of(p) < SLIVER_M:
                continue
            # (land outside every district is wild, not neglected: meadow)
            kind = ("meadow" if did is None else
                    "gravel" if arch in ROUGH_ARCHETYPES else "wasteland")
            out.append((did, Src(None, "rest", kind, p), p))
    return out


# --- fields ----------------------------------------------------------------------------------

class Raster:
    """Shade on a 4 m raster over the city (see the module docstring)."""

    def __init__(self, m):
        x0, y0, x1, y1 = m.bounds
        c = SHADE_CELL_M
        self.x0, self.y0, self.c = x0, y0, c
        self.nx = int(math.ceil((x1 - x0) / c))
        self.ny = int(math.ceil((y1 - y0) / c))
        H = np.zeros((self.ny, self.nx))
        P = G.from_model_poly
        for b in m.buildings:
            if b.footprint is None or b.level:
                continue
            self._paint(H, P(b.footprint), float(b.height_m), np.maximum)
        deck = np.zeros((self.ny, self.nx), dtype=bool)
        for d in m.decks:
            self._paint(deck, P(d.polygon), True, np.logical_or)
        blocked = np.zeros((self.ny, self.nx))
        for dx, dy in ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)):
            step = c * math.hypot(dx, dy)
            hit = np.zeros((self.ny, self.nx), dtype=bool)
            for k in range(1, int(SHADE_REACH_M // step) + 1):
                sh = _shift(H, k * dx, k * dy)
                hit |= sh > k * step          # above 45 degrees
            blocked += hit
        self.shade = np.where(deck, 1.0, blocked / 8.0)

    def _paint(self, A, poly, v, op):
        bx0, by0, bx1, by1 = poly.bounds
        i0 = max(0, int(math.floor((bx0 - self.x0) / self.c)))
        i1 = min(self.nx - 1, int(math.ceil((bx1 - self.x0) / self.c)))
        j0 = max(0, int(math.floor((by0 - self.y0) / self.c)))
        j1 = min(self.ny - 1, int(math.ceil((by1 - self.y0) / self.c)))
        if i1 < i0 or j1 < j0:
            return
        X, Y = np.meshgrid(self.x0 + (np.arange(i0, i1 + 1) + 0.5) * self.c,
                           self.y0 + (np.arange(j0, j1 + 1) + 0.5) * self.c)
        inside = shapely.contains_xy(poly, X, Y)
        sub = A[j0:j1 + 1, i0:i1 + 1]
        A[j0:j1 + 1, i0:i1 + 1] = np.where(inside, op(sub, v), sub)

    def mean(self, poly) -> float:
        bx0, by0, bx1, by1 = poly.bounds
        i0 = max(0, int(math.floor((bx0 - self.x0) / self.c)))
        i1 = min(self.nx - 1, int(math.ceil((bx1 - self.x0) / self.c)))
        j0 = max(0, int(math.floor((by0 - self.y0) / self.c)))
        j1 = min(self.ny - 1, int(math.ceil((by1 - self.y0) / self.c)))
        if i1 >= i0 and j1 >= j0:
            X, Y = np.meshgrid(self.x0 + (np.arange(i0, i1 + 1) + 0.5) * self.c,
                               self.y0 + (np.arange(j0, j1 + 1) + 0.5) * self.c)
            inside = shapely.contains_xy(poly, X, Y)
            if inside.any():
                return float(math.fsum(self.shade[j0:j1 + 1, i0:i1 + 1][inside].tolist())
                             / int(inside.sum()))
        x, y = G.qpoint(poly.representative_point())
        i = min(max(int((x - self.x0) / self.c), 0), self.nx - 1)
        j = min(max(int((y - self.y0) / self.c), 0), self.ny - 1)
        return float(self.shade[j, i])


def _shift(A, dx: int, dy: int):
    """A[j + dy, i + dx] at (j, i), 0 off the raster."""
    out = np.zeros_like(A)
    ny, nx = A.shape
    if abs(dx) >= nx or abs(dy) >= ny:
        return out
    ys = slice(max(0, -dy), ny - max(0, dy))
    xs = slice(max(0, -dx), nx - max(0, dx))
    yd = slice(max(0, dy), ny - max(0, -dy))
    xd = slice(max(0, dx), nx - max(0, -dx))
    out[ys, xs] = A[yd, xd]
    return out


def _samples(poly) -> np.ndarray:
    """Points inside a polygon on an 8 m grid (its representative point if none)."""
    bx0, by0, bx1, by1 = poly.bounds
    c = SAMPLE_M
    xs = np.arange(math.floor(bx0 / c), math.ceil(bx1 / c)) * c + c / 2
    ys = np.arange(math.floor(by0 / c), math.ceil(by1 / c)) * c + c / 2
    if len(xs) and len(ys):
        X, Y = np.meshgrid(xs, ys)
        inside = shapely.contains_xy(poly, X, Y)
        if inside.any():
            return np.stack([X[inside], Y[inside]], axis=1)
    return np.array([G.qpoint(poly.representative_point())])


class Fields:
    def __init__(self, m, cx: Ctx):
        from . import terrain as TE

        self.raster = Raster(m)
        lines = []
        for g in cx.wet:
            for p in G.parts(g):
                for r in [p.exterior, *p.interiors]:
                    c = list(r.coords)
                    lines += [LineString([c[k], c[k + 1]]) for k in range(len(c) - 1)]
        self.edges = lines
        self.etree = shapely.STRtree(lines) if lines else None
        self.ground = TE.ground_of(m)
        segs = [s for s in m.road_segments if not s.tunnel]
        dens = {d.segment_id: d.crowd_per_100m[2] for d in m.densities}
        self.crowd_segs = [(LineString(s.centerline), dens.get(s.id, 0.0)) for s in segs]
        self.ctree = shapely.STRtree([x[0] for x in self.crowd_segs]) \
            if self.crowd_segs else None

    def moisture(self, pts: np.ndarray) -> float:
        if self.etree is None:
            return 0.0
        _, d = self.etree.query_nearest(shapely.points(pts), return_distance=True,
                                        all_matches=False)
        d = np.round(d, 3)
        # (query_nearest gives one distance per point; ties carry the same distance)
        v = np.clip(1.0 - d / MOIST_M, 0.0, 1.0)
        return float(math.fsum(v.tolist()) / len(v)) if len(v) else 0.0

    def slope(self, pts: np.ndarray) -> tuple[float, float]:
        if self.ground is None:
            return 0.0, 0.0
        g = self.ground.slope_many(pts[:, 0], pts[:, 1])
        deg = [M.atan2(float(v), 1.0) * 180.0 / math.pi for v in g.tolist()]
        return math.fsum(deg) / len(deg), max(deg)

    def crowd(self, x: float, y: float, r: float = 50.0) -> float:
        """Pedestrians per 100 m (day) on the nearest street within r, else 0."""
        if self.ctree is None:
            return 0.0
        pt = Point(x, y)
        best = None
        for k in sorted(int(i) for i in self.ctree.query(pt, predicate="dwithin", distance=r)):
            d = G.dist(self.crowd_segs[k][0], pt)
            if best is None or d < best[0]:
                best = (d, self.crowd_segs[k][1])
        return best[1] if best else 0.0


# --- desire lines --------------------------------------------------------------------------

class Walks:
    def __init__(self, m):
        self.paths = [(w.id, LineString([(p[0], p[1]) for p in w.line]))
                      for w in m.walkways if not w.level and w.kind == "path"
                      and len(w.line) >= 2]
        self.ptree = shapely.STRtree([x[1] for x in self.paths]) if self.paths else None
        ends = set()
        for w in m.walkways:
            if w.level or w.kind not in ("sidewalk", "crosswalk", "crossing", "path",
                                         "promenade", "pedestrian_street"):
                continue
            for p in (w.line[0], w.line[-1]):
                ends.add((G.q(p[0]), G.q(p[1])))
        self.ends = sorted(ends)
        self.etree = shapely.STRtree(shapely.points(self.ends)) if self.ends else None


def _desire(poly, walks: Walks, fields: Fields) -> list[dict]:
    out = []
    if walks.ptree is not None:
        for k in sorted(int(i) for i in walks.ptree.query(poly, predicate="intersects")):
            g = walks.paths[k][1].intersection(poly)
            for ln in _lines(g):
                if G.length(ln) < 3.0:
                    continue
                pts = [(G.q(x), G.q(y)) for x, y in ln.coords]
                mx, my = pts[len(pts) // 2]
                c = fields.crowd(mx, my)
                out.append({"line": pts, "width_m": DESIRE_W["path"],
                            "wear": G.q(min(1.0, 0.3 + 0.7 * c / CROWD_REF))})
    if walks.etree is None or G.area(poly) < SHORTCUT_MIN_M2:
        return out
    ring = poly.exterior
    near = sorted(int(i) for i in walks.etree.query(ring, predicate="dwithin", distance=8.0))
    cand = [walks.ends[k] for k in near]
    # (the busiest ends, 2 m apart at least, 12 at most)
    scored = sorted(((-fields.crowd(x, y), (x, y)) for x, y in cand))
    pts = []
    for _, p in scored:
        if all(abs(p[0] - q[0]) + abs(p[1] - q[1]) >= 2.0 for q in pts):
            pts.append(p)
        if len(pts) >= 12:
            break
    per = G.length(ring)
    best = []
    shrunk = poly.buffer(0.5)
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            a, b = pts[i], pts[j]
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            if d < SHORTCUT_MIN_M:
                continue
            sa, sb = ring.project(Point(a)), ring.project(Point(b))
            around = abs(sa - sb)
            around = min(around, per - around)
            if around < DETOUR * d:
                continue
            seg = LineString([a, b])
            if not shrunk.covers(seg):
                continue
            c = (fields.crowd(*a) + fields.crowd(*b)) / 2.0
            if c <= 0:
                continue
            score = c * (around - d)
            best.append((-round(score, 6), a, b, c, around / d))
    best.sort()
    for _, a, b, c, ratio in best[:2]:
        out.append({"line": [a, b], "width_m": DESIRE_W["shortcut"],
                    "wear": G.q(min(1.0, (c / CROWD_REF) * (ratio - 1.0) + 0.2))})
    return out


def _lines(g) -> list:
    if g.is_empty:
        return []
    if g.geom_type == "LineString":
        return [g]
    return [x for p in getattr(g, "geoms", []) for x in _lines(p)]


# --- the stage ---------------------------------------------------------------------------

def _maintenance(cx: Ctx, did, what: str, kind: str) -> float:
    d = cx.dist.get(did)
    w = float(d.params.get("wealth", 0.5)) if d is not None else 0.4
    dg = float(d.params.get("danger", 0.4)) if d is not None else 0.4
    v = w - 0.2 * dg + CARE[what]
    if kind == "bare_dirt":
        v -= 0.15
    return G.q(min(1.0, max(0.0, v)))


def _kind(base: str, what: str, maint: float, moist: float, width: float, area: float,
          arch, wild: bool = False) -> str:
    k = base
    if wild:
        return "marsh" if moist >= 0.9 else "meadow"
    if what == "lot" and width < 2.5 and maint >= 0.55 and k in ("paving", "mown_lawn"):
        return "planted_bed"
    if what == "open" and k == "park_lawn" and area < 250.0:
        k = "planted_bed"
    if what in ("open", "rest") and k in ("mown_lawn", "wasteland", "meadow") and \
            moist >= 0.9 and arch not in ROUGH_ARCHETYPES:
        return "marsh"
    if k == "mown_lawn" and what == "open" and maint < 0.5:
        k = "meadow"
    if k in PAVED and maint < 0.3:
        return "overgrown_paving"
    if k in ("park_lawn", "mown_lawn") and maint < 0.3:
        k = "meadow"
    if k == "meadow" and maint < 0.15:
        k = "wasteland"
    if k == "wasteland" and maint >= 0.6:
        k = "meadow"
    return k


@dataclass
class Out:
    rows: list
    info: dict


def build(m) -> Out:
    """M16's ground cover on a finished city model."""
    with G.canonical():
        cx = Ctx(m)
        ps = pieces(cx)
        if not ps:
            return Out([], {"pieces": 0})
        fields = Fields(m, cx)
        walks = Walks(m)
        rows = []
        for did, src, p in ps:
            pts = _samples(p)
            moist = fields.moisture(pts)
            arch = cx.dist[did].archetype if did in cx.dist else None
            maint = _maintenance(cx, did, src.what, src.kind)
            A = G.area(p)
            kind = _kind(src.kind, src.what, maint, moist, width_of(p), A, arch,
                         wild=did is None and src.what == "rest")
            if src.kind == "marsh":
                moist = 1.0
            s_mean, s_max = fields.slope(pts)
            shade = fields.raster.mean(p)
            desire = _desire(p, walks, fields) if kind in LAWNS else []
            worn = math.fsum(G.length(LineString(d["line"])) * d["width_m"] * d["wear"]
                             for d in desire)
            rx, ry = G.qpoint(p.representative_point())
            crowd = min(1.0, fields.crowd(rx, ry) / CROWD_REF)
            wear = min(1.0, worn / A + (0.3 if kind in LAWNS else 0.6) * crowd) if A > 0 \
                else 0.0
            rows.append({"kind": kind, "type": f"ground_cover.{kind}",
                         "polygon": G.to_model_poly(p), "area_m2": G.q(A),
                         "district_id": did, "source_id": src.id,
                         "maintenance": maint, "wear": G.q(wear), "shade": G.q(shade),
                         "moisture": G.q(moist), "slope_deg": G.q(s_mean),
                         "slope_max_deg": G.q(s_max), "desire_lines": desire, "attrs": {}})
    rows = _named(rows)
    area: dict[str, float] = {}
    for r in rows:
        area[r["kind"]] = area.get(r["kind"], 0.0) + r["area_m2"]
    return Out(rows, {"pieces": len(rows),
                      "area_m2": {k: round(v, 1) for k, v in sorted(area.items())},
                      "desire_lines": sum(len(r["desire_lines"]) for r in rows)})


def _named(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        head = r["source_id"] or r["district_id"]
        base = f"{head}.gc.{ID.anchor(r)}" if head else f"gc.{ID.anchor(r)}"
        groups.setdefault(base, []).append(r)
    out = []
    for base in sorted(groups):
        rs = sorted(groups[base], key=lambda r: json.dumps(r, sort_keys=True))
        for k, r in enumerate(rs):
            r["id"] = base if k == 0 else f"{base}.{k + 1}"
            out.append(r)
    return out
