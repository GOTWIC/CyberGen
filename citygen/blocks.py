"""Stage 10, blocks, lots and open space.

Blocks: each district's land minus water, the right of way of every road (cross-section
width, plus the right-of-way corner of every junction and the cul-de-sac bulbs), megasite
reserves, flight cones and open land. Strips narrower than about 6 m (between a road and the
water, around a reserve) become landscaped verges.

Lots (Vanegas et al. 2012): every block is split recursively across the long side of its
oriented bounding box (with a little jitter), and a split is kept only when both sides keep
street frontage and the archetype's minimum lot area; otherwise the other axis is tried, and
when neither works the piece is a lot. Perimeter-block archetypes (old town, entertainment
market, midtown) first take out the block core beyond the deepest lot as a courtyard, so the
lots form a ring of narrow frontage lots. Lots that end up without frontage or below the
minimum are merged into the neighbor they share the most boundary with. Each lot records its
district, archetype, area and frontage (road segment, class, length, the frontage line).
Complexes of the spec (twin towers, tower clusters, megabuilding campuses, campuses, bridged
pairs, straddle buildings) get merged groups of lots for M3.

Open space: verges, blocks too small or too thin for a lot (pocket parks, or plazas in the
corporate core and transit hub), campus cores, the spec's named places (plazas, parks,
gardens, markets carved out of lots near the asked position; promenades and waterfronts
named on the promenade streets; beaches on the shore), then quotas per archetype filled with
the most awkward blocks first.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import shapely
from shapely.geometry import LineString, MultiLineString, Point, Polygon

from . import dmath as M
from . import geom as G
from . import streets as ST
from . import trace as T
from .presets import DIRECTION_VECTORS

VERGE_W_M = 6.0
MIN_BLOCK_M2 = 40.0
PLACE_AREA_M2 = {"plaza": (2500.0, 9000.0), "market": (1800.0, 6000.0),
                 "park": (9000.0, 40000.0), "garden": (1500.0, 6000.0),
                 "monument": (800.0, 2500.0), "station": (1500.0, 5000.0)}
SMALL_PLAZA = {"old_town": 0.35, "entertainment_market": 0.5}
OPEN_KIND = {"corporate_core": "plaza", "transit_hub": "plaza", "old_town": "pocket_park",
             "entertainment_market": "plaza", "midtown_mixed": "park",
             "megablock_residential": "park", "residential_heights": "park",
             "research_campus": "park", "industrial_port": "green", "spaceport": "green"}
COMPLEX_LOTS = {"twin_towers": 2, "tower_cluster": 3, "megabuilding_campus": 3, "campus": 4,
                "bridged_pair": 2, "straddle_building": 2}


def width_est(area: float, perim: float) -> float:
    """Width of a strip with this area and perimeter (a long rectangle w x L gives about w),
    from exact measures."""
    if perim <= 0:
        return 0.0
    s = perim / 2.0
    disc = s * s - 4.0 * area
    if disc < 0:
        return math.sqrt(area)
    return (s - math.sqrt(disc)) / 2.0


def _w(poly) -> float:
    return width_est(G.area1(poly), G.length1(poly.exterior))


def row_pieces(net, J) -> list:
    """Right of way of every road (snapped strips) plus the junction corners and cul-de-sac
    bulbs; each district job unions the pieces near it."""
    lines = [LineString(s["centerline"]) for s in net.segments]
    widths = np.array([s["width_m"] / 2 for s in net.segments])
    bufs = G.snap_many(shapely.buffer(np.array(lines, dtype=object), widths, cap_style="flat",
                                      join_style="mitre", mitre_limit=2.0))
    extra = [j["row_polygon"] for j in J["junctions"] if j.get("row_polygon") is not None
             and not j["row_polygon"].is_empty]
    return [g for g in list(bufs) + extra if not g.is_empty]


def row_area(net, J) -> object:
    return G.union(row_pieces(net, J))


class Frontage:
    """Road edges of a district's blocks: for each segment, the part of block boundaries
    that faces it (within the half width plus 0.6 m)."""

    def __init__(self, segments: list[dict]):
        self.segs = segments
        self.lines = [LineString(s["centerline"]) for s in segments]
        self.zone = G.snap_many(shapely.buffer(
            np.array(self.lines, dtype=object),
            np.array([s["width_m"] / 2 + 0.6 for s in segments]),
            cap_style="flat", join_style="mitre", mitre_limit=2.0))
        self.tree = shapely.STRtree(self.zone)

    def of(self, poly, min_len: float = 0.5, lines: bool = True
           ) -> list[tuple[str, str, float, list]]:
        """(segment id, class, length, line points) of the frontage of a polygon, longest
        first (exact lengths of grid-rounded linework)."""
        out = []
        ks = np.array(sorted(int(i) for i in self.tree.query(poly.buffer(0.5))), dtype=int)
        if not len(ks):
            return out
        inter = shapely.intersection(poly.exterior, self.zone[ks])
        for k, g in zip(ks.tolist(), inter):
            if g.is_empty:
                continue
            L = G.length1(g)
            if L < min_len:
                continue
            line, pts = [], []
            if lines:
                pts = _fast_lines(g)
                line = max(pts, key=lambda x: (ST._plen(x), x[0])) if pts else []
            s = self.segs[k]
            out.append((s["id"], s["road_class"], G.q(L), line, pts))
        out.sort(key=lambda t: (-t[2], t[0]))
        return out


def _fast_lines(g) -> list[list[tuple[float, float]]]:
    """Merged linework of a geometry as grid point lists (vertices rounded to the grid)."""
    if g.geom_type in ("MultiLineString", "GeometryCollection"):
        g = shapely.line_merge(shapely.union_all([x for x in shapely.get_parts(g)
                                                  if x.geom_type == "LineString"]))
    # parts and their directions in canonical order: callers take the first of equally long
    # edges, and the order GEOS returns pieces in can follow its std::sort ties
    g = shapely.normalize(g)
    out = []
    for part in shapely.get_parts(g):
        if part.geom_type not in ("LineString", "LinearRing"):
            continue
        c = np.rint(shapely.get_coordinates(part) * 100.0) / 100.0
        pts = []
        for x, y in c.tolist():
            p = (x + 0.0, y + 0.0)
            if not pts or p != pts[-1]:
                pts.append(p)
        if len(pts) >= 2:
            out.append(pts)
    return out


ACCESS = ("avenue", "street", "alley", "service", "pedestrian")


def _access_len(fr) -> float:
    return math.fsum(x[2] for x in fr if x[1] in ACCESS)


# ---------------------------------------------------------------------------
# Lot subdivision
# ---------------------------------------------------------------------------

def _halfplanes(poly, c, w, t: float):
    """The two sides of the line through c + w t perpendicular to w (snapped polygons)."""
    R = 4000.0
    m = (c[0] + w[0] * t, c[1] + w[1] * t)
    p = (-w[1], w[0])
    a = Polygon([(m[0] + p[0] * R, m[1] + p[1] * R), (m[0] - p[0] * R, m[1] - p[1] * R),
                 (m[0] - p[0] * R + w[0] * R, m[1] - p[1] * R + w[1] * R),
                 (m[0] + p[0] * R + w[0] * R, m[1] + p[1] * R + w[1] * R)])
    b = Polygon([(m[0] + p[0] * R, m[1] + p[1] * R), (m[0] - p[0] * R, m[1] - p[1] * R),
                 (m[0] - p[0] * R - w[0] * R, m[1] - p[1] * R - w[1] * R),
                 (m[0] + p[0] * R - w[0] * R, m[1] + p[1] * R - w[1] * R)])
    both = shapely.intersection(poly, np.array([a, b], dtype=object), grid_size=G.GRID_M)
    return [G._fixed(x) if not x.is_empty else Polygon() for x in both]


class Splitter:
    def __init__(self, st: ST.Style, front_geom, rng):
        self.st = st
        self.front = front_geom
        # coincident edges with different vertices meet in points, not lines: measure the
        # frontage inside a thin band around the block's street edges instead
        self.zone = G.snap(front_geom.buffer(0.15, cap_style="flat", join_style="mitre")) \
            if not front_geom.is_empty else Polygon()
        self.rng = rng
        self.amin, self.amax = st.lot_area
        self.fmin = max(3.0, 0.6 * st.frontage[0])
        self.courts: list = []   # deep interiors no lot can reach (become courtyards)

    def frontage(self, poly) -> float:
        if self.front.is_empty:
            return 0.0
        return G.length1(shapely.intersection(poly.exterior, self.zone))

    def _front_axis(self, poly):
        """(direction, span, center) of the longest straight run of this piece's frontage:
        cuts across it give every piece a share of the street."""
        if self.front.is_empty:
            return None
        g = shapely.intersection(poly.exterior, self.zone)
        best = None
        for pts in _fast_lines(g) if not g.is_empty else []:
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                L = ST._dist(a, b)
                if best is None or L > best[0] + 1e-9:
                    best = (L, a, b)
        if best is None or best[0] < 2.0 * max(self.st.frontage[0] * 0.7, 3.0):
            return None
        L, a, b = best
        d = ST._unit(b[0] - a[0], b[1] - a[1])
        return d, L, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    def split(self, poly, depth: int = 0) -> list:
        A = G.area1(poly)
        target = float(ST.uniform(self.rng, 1.3 * self.amin, 0.85 * self.amax))
        if A <= max(target, 1.6 * self.amin) or depth > 14:
            return [poly]
        c, u, v, L, W = ST._obb(poly)
        # a lot as wide as the archetype frontage: cut across the frontage first
        jit = float(ST.uniform(self.rng, -0.1, 0.1))
        big = A > 1.5 * self.amax
        offsets = (0.0, 0.16, -0.16, 0.3, -0.3) if big else (0.0, 0.16, -0.16)
        axes = [(u, L, c), (v, W, c)]
        if A > self.amax:
            fa = self._front_axis(poly)
            if fa is not None:
                axes.append(fa)
        for w, span, c in axes:
            if span < 2.0 * max(self.st.frontage[0] * 0.7, 3.0):
                continue
            for off in offsets:
                t = (jit + off) * span
                a, b = _halfplanes(poly, c, w, t)
                kids = G.parts(a) + G.parts(b)
                if len(kids) < 2:
                    continue
                ok = all(G.area1(k) >= 0.8 * self.amin and self.frontage(k) >= self.fmin
                         for k in kids)
                if ok:
                    out = []
                    for k in kids:
                        out += self.split(k, depth + 1)
                    return out
        if A > 1.5 * self.amax and depth < 12:
            # no cut keeps the street for both sides: the interior beyond the deepest lot is
            # a courtyard, and the ring around it is split again
            core = G.drop_small(G.qpoly(poly.buffer(-self.st.lot_depth[1], join_style="mitre",
                                                    mitre_limit=2.0)), 0.25 * self.amin)
            if not core.is_empty:
                self.courts.append(core)
                out = []
                for k in G.parts(G.diff(poly, core)):
                    if G.area1(k) >= 0.5 * self.amin:
                        out += self.split(k, depth + 2)
                    else:
                        self.courts.append(k)
                return out
            # too narrow for a ring: keep the street side, the far end is a back garden
            for w, span, cc in axes:
                for off in (0.3, -0.3, 0.15, -0.15):
                    a, b = _halfplanes(poly, cc, w, (jit + off) * span)
                    kids = G.parts(a) + G.parts(b)
                    front = [k for k in kids if self.frontage(k) >= self.fmin]
                    back = [k for k in kids if self.frontage(k) < self.fmin]
                    if front and back and all(G.area1(k) >= 0.8 * self.amin for k in front):
                        self.courts += back
                        out = []
                        for k in front:
                            out += self.split(k, depth + 2)
                        return out
            # last resort: the strip within the deepest lot of the street is the lot, the
            # rest a back garden
            edge = shapely.intersection(poly.exterior, self.zone)
            if not edge.is_empty:
                strip = G.qpoly(edge.buffer(self.st.lot_depth[1], cap_style="flat",
                                            join_style="mitre"))
                front = [k for k in G.parts(G.inter(poly, strip))
                         if G.area1(k) >= 0.8 * self.amin and self.frontage(k) >= self.fmin]
                if front and G.area1(front[0]) < 0.9 * A:
                    rest = G.diff(poly, G.union(front))
                    self.courts += G.parts(rest)
                    out = []
                    for k in front:
                        out += self.split(k, depth + 2)
                    return out
        return [poly]


def _merge_small(lots: list, splitter: Splitter) -> list:
    out = _merge_small_(lots, splitter)
    keep = []
    for p in out:
        if _w(p) < 3.0 or (G.area1(p) < 0.5 * splitter.amin and len(out) > 1):
            splitter.courts.append(p)  # a sliver no neighbor could take
        else:
            keep.append(p)
    return keep


def _merge_small_(lots: list, splitter: Splitter) -> list:
    """Lots below the minimum area or without frontage join the neighbor they share the
    most boundary with (one at a time, smallest first)."""
    lots = list(lots)
    for _ in range(len(lots)):
        bad = [i for i, p in enumerate(lots)
               if G.area1(p) < 0.8 * splitter.amin or splitter.frontage(p) < splitter.fmin
               or _w(p) < 3.0]
        if not bad or len(lots) == 1:
            break
        i = min(bad, key=lambda k: (G.area1(lots[k]), G.qbounds(lots[k])))
        best = None
        for j, q in enumerate(lots):
            if j == i or G.apart(lots[i], q, 0.5):
                continue
            sh = shapely.intersection(lots[i].boundary, q.boundary)
            L = G.length1(sh)
            if L > 0.5 and (best is None or L > best[0] + 1e-9):
                best = (L, j)
        if best is None:
            break
        j = best[1]
        merged = G.union([lots[i], lots[j]])
        if merged.geom_type != "Polygon":
            break
        lots = [p for k, p in enumerate(lots) if k not in (i, j)] + [merged]
    return lots


def subdivide(block, st: ST.Style, front_geom, rng) -> tuple[list, object]:
    """Lots of one block, and its courtyard (or an empty polygon)."""
    sp = Splitter(st, front_geom, rng)
    court = Polygon()
    body = block
    if st.perimeter and G.area1(block) > 2.0 * st.lot_area[1]:
        depth = st.lot_depth[1]
        core = G.qpoly(block.buffer(-depth, join_style="mitre", mitre_limit=2.0))
        core = G.drop_small(core, max(2.0 * st.lot_area[0], 150.0))
        if not core.is_empty:
            court = core
            body = G.diff(block, core)
    lots = []
    for part in G.parts(body):
        lots += sp.split(part)
    lots = _merge_small(lots, sp)
    if sp.courts:
        court = G.union([court] + sp.courts) if not court.is_empty else G.union(sp.courts)
    return lots, court


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

class Ctx:
    def __init__(self, spec, B, net, J):
        self.spec = spec
        self.B = B
        self.net = net
        self.J = J
        self.did = B.did
        self.notes: list[str] = []


def _anchor(poly, position: str | None, wet) -> tuple[float, float]:
    """Point of a district a place's `position` asks for."""
    c = G.centroid(poly)
    if not position or position == "center":
        p = poly.representative_point() if not poly.contains(Point(c)) else Point(c)
        return G.qpoint(p)
    if position == "waterfront":
        return G.nearest(poly, G.nearest(wet, Point(c))) if not wet.is_empty else c
    ux, uy = DIRECTION_VECTORS[position]
    x0, y0, x1, y1 = poly.bounds
    R = ST._dist((x0, y0), (x1, y1))
    far = Point(c[0] + ux * R, c[1] + uy * R)
    return G.nearest(poly, far)


def district_lots(job: dict, worker: bool = False) -> dict:
    with G.canonical():
        return _district_lots(job)


def _district_lots(job: dict) -> dict:
    """Blocks, verges and lots of one district (runs in a worker process when there are
    several): land minus right of way, water, reserves, cones and open land; small, thin or
    roadless pieces become open space; campus cores become grounds; blocks are subdivided."""
    st = ST.style_of(job["archetype"])
    seed = job["seed"]
    front = Frontage(job["segments"])
    land = G.diff(job["polygon"], job["wet"])
    row = G.union(job["row"])
    for g in (row, job["reserves"], job["cones"], job["open_land"]):
        land = G.diff(land, g)
    blocks, opens = [], []
    pieces = []
    for part in G.parts(land):
        clean_ = G.opening(part, 1.0)  # spikes and necks under 2 m left by the overlays
        pieces += G.parts(clean_) if not clean_.is_empty else []
    for part in pieces:
        A = G.area1(part)
        if A < MIN_BLOCK_M2:
            continue
        w = _w(part)
        if w < VERGE_W_M:
            opens.append(("green", part, None))
            continue
        fr = front.of(part, lines=False)
        if _access_len(fr) < 2.0:
            opens.append(("green" if A < 1500 else "park", part, None))
            continue
        if A < 0.8 * st.lot_area[0] or (A < 2.5 * st.lot_area[0] and w < 8.0):
            opens.append((_small_kind(job["archetype"], A), part, None))
            continue
        blocks.append(part)
    cores = job["cores"]
    if not cores.is_empty:
        kept = []
        for blk in blocks:
            g = G.inter(blk, cores)
            if G.area1(g) > 3000.0:
                opens.append(("park", g, "campus green"))
                rest = [p for p in G.parts(G.diff(blk, cores)) if G.area1(p) >= MIN_BLOCK_M2]
                kept += [p for p in rest if _w(p) >= VERGE_W_M]
                opens += [("green", p, None) for p in rest if _w(p) < VERGE_W_M]
            else:
                kept.append(blk)
        blocks = kept
    blocks.sort(key=lambda p: (-G.area1(p), G.qbounds(p)))
    items = []
    for bi, blk in enumerate(blocks):
        fr = front.of(blk)
        items.append((blk, fr, bi))
    return {"items": items, "opens": opens}


def chunk_lots(job: dict, worker: bool = False) -> list:
    """Lots of a chunk of blocks (one worker job): [(lots with frontage, courtyard)]."""
    with G.canonical():
        return _chunk_lots(job)


def _chunk_lots(job: dict) -> list:
    front = Frontage(job["segments"])
    out = []
    for blk, fr, arch, seed, bi in job["items"]:
        st = ST.style_of(arch)
        fgeom = G.line_union([LineString(p) for x in fr if x[1] in ACCESS
                              for p in x[4] if len(p) >= 2])
        lots, court = subdivide(blk, st, fgeom, ST._rng(seed, 43, bi))
        lots = sorted(lots, key=lambda p: G.qbounds(p))
        recs = [(lot, front.of(lot)) for lot in lots]
        recs, extra = _ensure_frontage(recs, front)
        if extra:
            court = G.union([court] + extra) if not court.is_empty else G.union(extra)
        out.append((recs, court))
    return out


def _ensure_frontage(recs: list, front: Frontage) -> tuple[list, list]:
    """The road frontage of each final lot decides: a lot without (under 2 m) joins the
    neighbor it shares the most boundary with, else becomes part of the courtyard."""
    extra = []
    for _ in range(len(recs)):
        bad = [i for i, (p, fr) in enumerate(recs) if _access_len(fr) < 2.0]
        if not bad:
            break
        i = bad[0]
        p = recs[i][0]
        best = None
        for j, (q, _) in enumerate(recs):
            if j == i or G.apart(p, q, 0.5):
                continue
            L = G.length1(shapely.intersection(p.exterior,
                                               G.snap(q.buffer(0.1, join_style="mitre"))))
            if L > 0.5 and (best is None or L > best[0] + 1e-9):
                best = (L, j)
        if best is None:
            extra.append(p)
            recs = [r for k, r in enumerate(recs) if k != i]
            continue
        j = best[1]
        merged = G.union([p, recs[j][0]])
        if merged.geom_type != "Polygon":
            extra.append(p)
            recs = [r for k, r in enumerate(recs) if k != i]
            continue
        keep = [r for k, r in enumerate(recs) if k not in (i, j)]
        recs = sorted(keep + [(merged, front.of(merged))], key=lambda r: G.qbounds(r[0]))
    return recs, extra


CHUNK_LOTS = 250.0   # about this many lots per worker job


def build_blocks(spec, B, net, J, mapper=None) -> dict:
    cx = Ctx(spec, B, net, J)
    pieces = row_pieces(net, J)
    ptree = shapely.STRtree(pieces)
    T.detail("blocks/row", pieces)
    out = {"blocks": [], "lots": [], "open": [], "places": [], "notes": cx.notes}
    cores = G.union([c for _, c in net.cores]) if net.cores else Polygon()
    names = [d for d in spec.districts if d.name in B.polygons]
    jobs = []
    for d in names:
        poly = B.polygons[d.name]
        clip = G.qpoly(poly.buffer(30.0, join_style="mitre"))
        segs = [s for s in net.segments
                if not G.apart(LineString(s["centerline"]), poly, s["width_m"])]
        jobs.append({"archetype": d.archetype, "seed": d.seed, "polygon": poly,
                     "wet": G.inter(B.wet, clip),
                     "row": [pieces[i] for i in sorted(int(k) for k in ptree.query(clip))],
                     "reserves": B.reserves, "cones": B.cones, "open_land": B.open_land,
                     "cores": G.inter(cores, clip) if not cores.is_empty else Polygon(),
                     "segments": segs})
    mapper = mapper or (lambda fn, js: [fn(j) for j in js])
    # the biggest districts first (the slowest jobs start early); results back in spec order
    order = sorted(range(len(jobs)), key=lambda k: (-G.area1(jobs[k]["polygon"]), k))
    done = mapper(district_lots, [jobs[k] for k in order])
    results = [None] * len(jobs)
    for k, r in zip(order, done):
        results[k] = r
    # lots: blocks in chunks of about CHUNK_LOTS lots (the result does not depend on how
    # they are grouped: each block's lots depend only on the block, its seed and its roads)
    flat = []
    for d, res in zip(names, results):
        for blk, fr, bi in res["items"]:
            amin = ST.style_of(d.archetype).lot_area[0]
            flat.append((blk, fr, d.archetype, d.seed, bi, G.area1(blk) / (2.5 * amin)))
    chunks, cur, acc = [], [], 0.0
    for it in flat:
        cur.append(it[:5])
        acc += it[5]
        if acc >= CHUNK_LOTS:
            chunks.append(cur)
            cur, acc = [], 0.0
    if cur:
        chunks.append(cur)
    seg_lines = [LineString(s["centerline"]) for s in net.segments]
    seg_tree = shapely.STRtree(seg_lines)
    cjobs = []
    for ch in chunks:
        box = shapely.box(*shapely.total_bounds(np.array([x[0] for x in ch], dtype=object)))
        near = sorted(int(i) for i in seg_tree.query(box.buffer(40.0)))
        cjobs.append({"items": ch, "segments": [net.segments[i] for i in near]})
    lot_res = [r for part in mapper(chunk_lots, cjobs) for r in part]
    k = 0
    for d, res in zip(names, results):
        did = B.did[d.name]
        st = ST.style_of(d.archetype)
        lots_by_block = []
        opens = list(res["opens"])
        for blk, fr, bi in res["items"]:
            lots, court = lot_res[k]
            k += 1
            for cp in G.parts(court):
                opens.append(("courtyard", cp, None))
            lots_by_block.append((blk, fr, lots))
        T.detail(f"blocks/{did}", [b for b, _, _ in lots_by_block])
        _district_out(cx, out, d, did, st, lots_by_block, opens, ST._rng(d.seed, 41))
    finish_lots(out)
    _merged_groups(cx, out)
    T.detail("blocks/lots", [(l["id"], l["polygon"]) for l in out["lots"]])
    return out


def _small_kind(arch: str, A: float) -> str:
    if arch in ("corporate_core", "transit_hub", "entertainment_market"):
        return "plaza"
    if arch in ("industrial_port", "spaceport"):
        return "green"
    return "pocket_park"


def _district_out(cx: Ctx, out: dict, d, did: str, st: ST.Style, lots_by_block, opens,
                  rng) -> None:
    """Records for a district: blocks, lots, open space, named places, quotas."""
    B = cx.B
    blk_recs = []
    lot_recs = []
    for bi, (blk, fr, lots) in enumerate(lots_by_block):
        bid = f"{did}.blk{bi + 1:03d}"
        blk_recs.append({"id": bid, "district_id": did, "archetype": d.archetype,
                         "polygon": blk, "area_m2": G.q(G.area1(blk)),
                         "frontage_ids": sorted({x[0] for x in fr}),
                         "attrs": {}})
        for li, (lot, lfr) in enumerate(lots):
            lot_recs.append({"block": bid, "polygon": lot, "k": li, "fr": lfr})
    # named places carve lots or name streets
    taken: set = set()
    place_recs = []
    for pl in d.places:
        rec = _place(cx, d, did, st, pl, lot_recs, blk_recs, opens, taken)
        if rec is not None:
            place_recs.append(rec)
    # quotas: open share of the district's net land
    lot_area = math.fsum(G.area1(r["polygon"]) for r in lot_recs if id(r) not in taken)
    open_area = math.fsum(G.area1(p) for _, p, _ in opens)
    open_area += math.fsum(G.area1(s.polygon) for s in B.sites if s.district == d.name and
                           s.kind in ("central_park", "grand_plaza"))
    lo, hi = st.open_share
    want = lo + 0.3 * (hi - lo)
    total = lot_area + open_area
    if total > 0 and open_area / total < want:
        need = want * total - open_area
        # whole blocks with few lots (awkward shapes first), else single lots
        cands = []
        for r in lot_recs:
            if id(r) in taken:
                continue
            p = r["polygon"]
            A = G.area1(p)
            P = G.length(p.exterior)
            cands.append((-(P * P / A), A, G.qbounds(p), r))
        cands.sort(key=lambda t: t[:3])
        for _, A, _, r in cands:
            if need <= 0:
                break
            if A > max(need * 2.5, st.lot_area[1] * 0.7) and A > 400:
                continue
            taken.add(id(r))
            opens.append((OPEN_KIND.get(d.archetype, "pocket_park")
                          if A < 4000 else "park", r["polygon"], None))
            need -= A
    # emit
    for r in lot_recs:
        if id(r) in taken:
            continue
        out["lots"].append(r)
        r["district_id"] = did
        r["archetype"] = d.archetype
    out["blocks"] += blk_recs
    for kind, poly, name in opens:
        out["open"].append({"kind": kind, "polygon": poly, "name": name, "district_id": did})
    out["places"] += place_recs


def _place(cx: Ctx, d, did: str, st: ST.Style, pl, lot_recs, blk_recs, opens, taken):
    B = cx.B
    poly = B.polygons[d.name]
    kind = pl.kind
    rec = {"name": pl.name, "kind": kind, "district_id": did, "polygon": None,
           "label_at": None, "feature_ids": [], "attrs": {"position": pl.position}}
    dry = G.diff(poly, B.wet)
    anchor = _anchor(dry if not dry.is_empty else poly, pl.position, B.wet)
    if kind in PLACE_AREA_M2:
        lo, hi = PLACE_AREA_M2[kind]
        f = SMALL_PLAZA.get(d.archetype, 1.0)
        target = (lo + hi) / 2 * f
        cands = [r for r in lot_recs if id(r) not in taken]
        if not cands:
            cx.notes.append(f"place '{pl.name}' ({kind}): no lots left in '{d.name}'")
            return None
        # the block nearest the anchor, then its lots nearest the anchor
        by_block: dict = {}
        for r in cands:
            by_block.setdefault(r["block"], []).append(r)
        bpoly = {b["id"]: b["polygon"] for b in blk_recs}

        def bscore(bid):
            A = math.fsum(G.area1(r["polygon"]) for r in by_block[bid])
            return (G.dist(bpoly[bid], Point(anchor)) + (0.0 if A >= 0.6 * target else 400.0),
                    bid)

        bid = min(by_block, key=bscore)
        chosen, acc = [], 0.0
        for r in sorted(by_block[bid], key=lambda r: (G.dist(r["polygon"], Point(anchor)),
                                                      G.qbounds(r["polygon"]))):
            if acc >= target:
                break
            chosen.append(r)
            acc += G.area1(r["polygon"])
        geom = G.union([r["polygon"] for r in chosen])
        for r in chosen:
            taken.add(id(r))
        okind = {"monument": "plaza", "station": "plaza"}.get(kind, kind)
        for p in G.parts(geom):
            opens.append((okind, p, pl.name))
        rec["polygon"] = G.parts(geom)[0] if G.parts(geom) else None
        rec["attrs"]["block_id"] = bid
    elif kind in ("promenade", "waterfront", "pedestrian_street", "street"):
        want = "pedestrian" if kind != "street" else "street"
        segs = [s for s in cx.net.segments if s["road_class"] == want and
                s["attrs"].get("district") == did]
        if kind == "waterfront" and not segs:
            segs = [s for s in cx.net.segments if s["road_class"] == "pedestrian" and
                    s["attrs"].get("district") == did]
        if not segs:
            segs = [s for s in cx.net.segments if s["road_class"] in ("street", "pedestrian")
                    and s["attrs"].get("district") == did]
        if not segs:
            cx.notes.append(f"place '{pl.name}' ({kind}): no street in '{d.name}'")
            return None
        chain = _chain_near(segs, anchor, 450.0)
        for s in chain:
            s["name"] = pl.name
        rec["feature_ids"] = [s["id"] for s in chain]
        geom = G.union([G.qpoly(LineString(s["centerline"]).buffer(
            s["width_m"] / 2, cap_style="flat", join_style="mitre")) for s in chain])
        rec["polygon"] = G.parts(geom)[0] if G.parts(geom) else None
        if kind in ("promenade", "waterfront"):
            for p in G.parts(geom):
                opens.append(("promenade", p, pl.name))
    elif kind in ("canal", "creek", "marina"):
        ww = [w for w in B.ww.items if w.district == d.name]
        hit = [w for w in ww if w.name == pl.name] or \
            [w for w in ww if w.kind == ("marina" if kind == "marina" else w.kind)
             and w.name is None and w.kind in (("canal", "creek") if kind != "marina"
                                                else ("marina",))]
        if not hit:
            cx.notes.append(f"place '{pl.name}' ({kind}): no waterway in '{d.name}'")
            return None
        w = max(hit, key=lambda w: (G.area1(w.polygon), w.id))
        rec["feature_ids"] = [w.id]
        rec["polygon"] = G.parts(w.polygon)[0]
    elif kind in ("pier", "docks", "beach"):
        coast = G.inter(G.diff(poly, B.wet), G.qpoly(B.wet.buffer(40.0)))
        near = [p for p in G.parts(coast)]
        if not near:
            cx.notes.append(f"place '{pl.name}' ({kind}): '{d.name}' has no shore")
            return None
        p = min(near, key=lambda q: (G.dist(q, Point(anchor)), G.qbounds(q)))
        rec["polygon"] = p
        if kind == "beach":
            opens.append(("beach", p, pl.name))
    elif kind == "gate":
        avenues = [s for s in cx.net.segments if s["road_class"] in ("avenue", "highway")]
        edge = poly.exterior
        best = None
        for s in avenues:
            ln = LineString(s["centerline"])
            x = shapely.intersection(ln, edge)
            for q in ST._points_of(x):
                dd = ST._dist(q, anchor)
                if best is None or dd < best[0]:
                    best = (dd, q, s["id"])
        if best is None:
            cx.notes.append(f"place '{pl.name}' (gate): no avenue enters '{d.name}'")
            return None
        rec["polygon"] = G.qpoly(Point(best[1]).buffer(25.0, quad_segs=4))
        rec["feature_ids"] = [best[2]]
    elif kind == "neighborhood":
        land = G.diff(poly, B.wet)
        ux, uy = DIRECTION_VECTORS.get(pl.position or "north", (0.0, 1.0)) \
            if pl.position and pl.position != "center" else (0.0, 0.0)
        c = G.centroid(land)
        sel = []
        for b in blk_recs:
            bc = G.centroid(b["polygon"])
            if (ux, uy) == (0.0, 0.0):
                score = -ST._dist(bc, c)
            else:
                score = (bc[0] - c[0]) * ux + (bc[1] - c[1]) * uy
            sel.append((score, b["id"], b["polygon"]))
        sel.sort(key=lambda t: (-t[0], t[1]))
        pick = sel[:max(1, len(sel) // 4)]
        geom = G.qpoly(shapely.convex_hull(G.union([p for _, _, p in pick])))
        rec["polygon"] = geom if geom.geom_type == "Polygon" else None
        rec["feature_ids"] = [b for _, b, _ in pick]
    else:
        site = [s for s in B.sites if s.name == pl.name]
        if site:
            rec["polygon"] = site[0].polygon
            rec["feature_ids"] = [site[0].id]
        else:
            rec["polygon"] = G.qpoly(Point(anchor).buffer(30.0, quad_segs=4))
    if rec["polygon"] is not None:
        p = rec["polygon"]
        lp = p.representative_point()
        rec["label_at"] = G.qpoint(lp)
    else:
        rec["label_at"] = anchor
    return rec


def _chain_near(segs: list[dict], anchor, length: float) -> list[dict]:
    """Connected segments (by shared nodes) grown from the one nearest the anchor until
    `length` meters."""
    start = min(segs, key=lambda s: (G.dist(LineString(s["centerline"]), Point(anchor)),
                                     s["id"]))
    by_node: dict = {}
    for s in segs:
        by_node.setdefault(s["start"], []).append(s)
        by_node.setdefault(s["end"], []).append(s)
    chain = [start]
    acc = start["attrs"]["length_m"]
    frontier = [start["start"], start["end"]]
    seen = {start["id"]}
    while acc < length and frontier:
        n = frontier.pop(0)
        for s in sorted(by_node.get(n, []), key=lambda s: s["id"]):
            if s["id"] in seen:
                continue
            seen.add(s["id"])
            chain.append(s)
            acc += s["attrs"]["length_m"]
            frontier += [s["start"], s["end"]]
            if acc >= length:
                break
    return chain


PROBES = 24   # candidate groups tried per complex (M3's builder decides whether one fits)


def _merged_groups(cx: Ctx, out: dict) -> None:
    """Merged lot groups for the complexes of the spec (M3 builds them). Candidates nearest
    the district center come first; each is tried with M3's own builder for its complex
    (masses only) and the first that holds it is taken, so the complex stands where it was
    grouped. When none does, the first candidate is taken (M3 then builds the complex on
    another block nearby)."""
    from . import buildings as BL
    from . import complexes as CX

    spec = cx.spec
    by_d: dict = {}
    for r in out["lots"]:
        by_d.setdefault(r["district_id"], []).append(r)
    shared = None
    for d in spec.districts:
        did = cx.did.get(d.name)
        lots = by_d.get(did, [])
        if not lots or not d.complexes:
            continue
        c = G.centroid(cx.B.polygons[d.name])
        if shared is None:
            shared = _probe_shared(cx)
        pcx = BL._prepare(_probe_ctx(cx, d, did, out, shared))
        pcx.lots = [(r["id"], r["polygon"]) for r in sorted(lots, key=lambda r: r["id"])]
        order = sorted(lots, key=lambda r: r["id"])
        idx = {id(r): k for k, r in enumerate(order)}
        views = {id(r): _lot_view(r) for r in lots}
        k = 0
        used: set = set()
        n_straddle = 0
        for cplx in d.complexes:
            n_lots = COMPLEX_LOTS.get(cplx.kind, 2)
            for _ in range(cplx.count):
                canal_first = cplx.kind == "straddle_building" and n_straddle % 2 == 0
                if cplx.kind == "straddle_building":
                    n_straddle += 1
                group = None
                for t, cand in enumerate(_candidates(lots, used, n_lots, c, cplx.kind, pcx,
                                                     canal_first)):
                    if t >= PROBES:
                        break
                    group = group or cand
                    mem = sorted(cand, key=lambda r: r["id"])
                    if CX.probe(pcx, cplx.kind, [views[id(r)] for r in mem], idx[id(mem[0])]):
                        group = cand
                        break
                if group is None:
                    cx.notes.append(f"complex {cplx.kind} in '{d.name}': no lots to merge")
                    continue
                k += 1
                gid = f"{did}.mg{k:02d}"
                for r in group:
                    r["merged_group_id"] = gid
                    r.setdefault("attrs", {})["complex"] = cplx.kind
                    used.add(id(r))


def _lot_view(r: dict) -> dict:
    """A lot as M3 sees it."""
    return {"id": r["id"], "block_id": r["block"], "polygon": r["polygon"],
            "area_m2": r["area_m2"], "merged_group_id": None, "attrs": {},
            "frontage": r["frontage"]}


def _probe_shared(cx: Ctx) -> dict:
    """What every district's probe context draws from: road lines, junction and crosswalk
    polygons (with STRtrees)."""
    segs = cx.net.segments
    lines = [LineString(sg["centerline"]) for sg in segs]
    jpolys = [j["polygon"] for j in cx.J["junctions"] if not j["polygon"].is_empty]
    cwl = [LineString(cw["line"]) for cw in cx.J["crosswalks"]]
    cwp = [G.qpoly(ln.buffer(cw["width_m"] / 2.0, cap_style="flat", join_style="mitre"))
           for ln, cw in zip(cwl, cx.J["crosswalks"])]
    return {"lines": lines, "ltree": shapely.STRtree(lines), "jpolys": jpolys,
            "jtree": shapely.STRtree(jpolys) if jpolys else None, "cwp": cwp,
            "cwtree": shapely.STRtree(cwl) if cwl else None}


def _probe_ctx(cx: Ctx, d, did: str, out: dict, shared: dict):
    """The district as M3's builders see it (roads, junctions, crosswalks, open space, water,
    flight cones), for trying merged groups."""
    from . import buildings as BL
    from . import buildout as BO

    B = cx.B
    poly = B.polygons[d.name]
    zone = G.qpoly(poly.buffer(80.0, join_style="mitre"))
    roads = []
    for k in sorted(int(i) for i in shared["ltree"].query(zone, predicate="intersects")):
        sg = cx.net.segments[k]
        zmax = max((z["z"] for z in sg["z_profile"]), default=0.0) \
            if isinstance(sg["z_profile"], list) else 0.0
        roads.append((sg["id"], sg["road_class"], [tuple(p) for p in sg["centerline"]],
                      sg["width_m"], float(zmax)))
    jt, ct = shared["jtree"], shared["cwtree"]
    junctions = [shared["jpolys"][int(i)]
                 for i in sorted(jt.query(zone, predicate="intersects"))] if jt else []
    junctions += [shared["cwp"][int(i)]
                  for i in sorted(ct.query(zone, predicate="intersects"))] if ct else []
    junctions += [o["polygon"] for o in out["open"] if o.get("district_id") == did and
                  o["polygon"].geom_type == "Polygon"]
    water = []
    for b in B.h.bodies:
        cls = "river" if b.kind in ("river", "delta_branch") else "sea" \
            if b.kind == "sea_channel" else "canal"
        if b.polygon.intersects(zone):
            water.append((b.id, b.polygon, BO.WATER_CLEAR[cls]))
    for w in B.ww.items:
        if w.polygon.intersects(zone):
            water.append((w.id, w.polygon,
                          BO.WATER_CLEAR["sea" if w.kind == "basin" else "canal"]))
    cones = [(s.flight_cone, float(s.height_limit_m)) for s in B.sites
             if s.flight_cone is not None and s.height_limit_m and
             G.dist(s.flight_cone, poly) < 3000.0]
    A = G.area1(poly)
    st = ST.style_of(d.archetype)
    return BL.Ctx(
        did=did, name=d.name, archetype=d.archetype, seed=int(d.seed),
        height=(float(d.height_m[0]), float(d.height_m[1])), grime=float(d.grime),
        neon=float(d.neon), greenery=float(d.greenery),
        skybridge_density=float(d.skybridge_density), polygon=poly, focus=G.centroid(poly),
        radius=math.sqrt(A / math.pi) * 1.1, lot_area=st.lot_area, cones=cones,
        complexes=tuple(cp.kind for cp in (d.complexes or [])), landmarks=[], roads=roads,
        junctions=junctions, water=water)


def _candidates(lots, used, n: int, c, kind: str, pcx, canal_first: bool) -> list:
    """Candidate groups for a complex, best first."""
    free = [r for r in lots if id(r) not in used and "merged_group_id" not in r]
    if not free:
        return []
    if kind in ("bridged_pair", "straddle_building"):
        streets = _street_pairs(free, c)
        if kind != "straddle_building":
            return streets
        canals = _canal_pairs(free, c, pcx)
        return itertools.chain(canals, streets) if canal_first else \
            itertools.chain(streets, canals)
    # adjacent lots in one block, nearest the center, biggest blocks preferred; each seed
    # grows by the biggest neighbor and by the neighbor it shares the longest edge with
    seeds = sorted(free, key=lambda r: (ST._dist(G.centroid(r["polygon"]), c) /
                                        math.sqrt(math.sqrt(max(G.area1(r["polygon"]), 1.0))),
                                        r["block"], r["k"]))
    out, seen = [], set()
    for s in seeds[:PROBES]:
        pool0 = [r for r in free if r["block"] == s["block"] and r is not s]
        for grow in ("area", "edge"):
            group = [s]
            pool = list(pool0)
            while len(group) < n and pool:
                nb = []
                for r in pool:
                    shared = 0.0
                    for g in group:
                        if not G.apart(r["polygon"], g["polygon"], 0.5):
                            shared += shapely.intersection(r["polygon"].boundary,
                                                           g["polygon"].boundary).length
                    if shared > 1.0:
                        nb.append((r, shared))
                if not nb:
                    break
                if grow == "area":
                    r = min(nb, key=lambda t: (-G.area1(t[0]["polygon"]),
                                               G.qbounds(t[0]["polygon"])))[0]
                else:
                    r = min(nb, key=lambda t: (-round(t[1], 3), G.qbounds(t[0]["polygon"])))[0]
                group.append(r)
                pool.remove(r)
            key = tuple(sorted(r["id"] for r in group))
            if len(group) >= min(n, 2) and key not in seen:
                seen.add(key)
                out.append(group)
    return out


def _facing(a: dict, b: dict, sid: str) -> float:
    """How far the frontages of two lots on segment sid overlap along it (m)."""
    fa = next(f for f in a["frontage"] if f["segment_id"] == sid)
    fb = next(f for f in b["frontage"] if f["segment_id"] == sid)
    p0, p1 = fa["line"][0], fa["line"][-1]
    L = ST._dist(p0, p1)
    if L <= 0:
        return 0.0
    ux, uy = (p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L
    ts = [(x - p0[0]) * ux + (y - p0[1]) * uy for x, y in fb["line"]]
    return min(L, max(ts)) - max(0.0, min(ts))


def _street_pairs(free, c) -> list:
    """Two lots of different blocks on one street (among their first two frontages), facing
    each other along at least 10 m of it, nearest the district center first."""
    by_seg: dict = {}
    for r in free:
        for f in r.get("frontage", [])[:2]:
            if len(f["line"]) >= 2 and f["length_m"] >= 10.0:
                by_seg.setdefault(f["segment_id"], []).append(r)
    cands = []
    for sid in sorted(by_seg):
        rs = by_seg[sid]
        for i, a in enumerate(rs):
            for b in rs[i + 1:]:
                if a["block"] == b["block"]:
                    continue
                da = G.centroid(a["polygon"])
                db = G.centroid(b["polygon"])
                if ST._dist(da, db) > 120.0 or _facing(a, b, sid) < 10.0:
                    continue
                score = round(ST._dist(da, c) + ST._dist(db, c), 6)
                cands.append((score, sid, a["id"], b["id"], [a, b]))
    cands.sort(key=lambda t: t[:4])
    return [t[4] for t in cands]


def _canal_pairs(free, c, pcx):
    """Two lots facing each other across a canal (see complexes._canal_fronts), nearest the
    district center first (yielded lazily: the pairs are ordered by a cheap score and tested
    only as far as they are needed)."""
    from . import complexes as CX

    canals = [wp for _, wp, clear in pcx.water if clear <= 4.0 + 1e-9]
    if not canals:
        return
    # only lots within reach of a canal can face each other across one (exact: a pair's
    # frontage midpoints lie within CANAL_REACH_M of each other with the canal between)
    ctree = shapely.STRtree(canals)
    hit = ctree.query([r["polygon"] for r in free], predicate="dwithin",
                      distance=CX.CANAL_REACH_M)[0]
    near = sorted(set(int(i) for i in hit.tolist()))
    free = [free[i] for i in near]
    if len(free) < 2:
        return
    polys = [r["polygon"] for r in free]
    cs = [G.centroid(p) for p in polys]
    tree = shapely.STRtree(polys)
    ia, ib = tree.query(polys, predicate="dwithin", distance=CX.CANAL_REACH_M * 0.75)
    pairs = sorted({(min(a, b), max(a, b)) for a, b in zip(ia.tolist(), ib.tolist())
                    if a != b})
    cands = []
    for i, j in pairs:
        a, b = free[i], free[j]
        if a["block"] == b["block"] or a["area_m2"] < 150.0 or b["area_m2"] < 150.0:
            continue
        cands.append((round(ST._dist(cs[i], c) + ST._dist(cs[j], c), 6), a["id"], b["id"],
                      i, j))
    cands.sort()
    for _, _, _, i, j in cands:
        a, b = free[i], free[j]
        if CX._canal_fronts(pcx, [_lot_view(a), _lot_view(b)]) is not None:
            yield [a, b]


def finish_lots(out: dict) -> None:
    """Ids, frontage records and areas of the lots (after places and quotas)."""
    by_block: dict = {}
    for r in out["lots"]:
        by_block.setdefault(r["block"], []).append(r)
    for bid in sorted(by_block):
        rs = sorted(by_block[bid], key=lambda r: r["k"])
        for i, r in enumerate(rs):
            r["id"] = f"{bid}.lot{i + 1:03d}"
            r["frontage"] = [{"segment_id": sid, "road_class": cls, "length_m": L,
                              "line": line} for sid, cls, L, line, _ in r.pop("fr")
                             if len(line) >= 2]
            r["frontage_ids"] = [f["segment_id"] for f in r["frontage"]]
            r["area_m2"] = G.q(G.area1(r["polygon"]))
