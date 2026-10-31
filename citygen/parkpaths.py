"""Park paths on open land (the park paths fix, between milestones; `docs/run_through_1.md`).

Open space (parks, plazas, pocket parks, markets, gardens, promenades, beaches) joins the
walkway graph by paths from a point inside it to the walkways near it. Since M2 those paths
ran straight to the nearest walk nodes across whatever lay between, lots and the buildings M3
puts on them included. Here a path runs from the open space's middle to the nearest point of
a walkway beside it (the walkway split there), straight where that stays off every lot, the
water and the megasite reserves, else bending at the open space's own corners (a shortest
path among them). An open space that no such path reaches (one the lots enclose, with no
street frontage) gets a passage: a strip `PASSAGE_W_M` wide carved from the lots along their
common boundary, from the open space to the nearest street (it joins the open space, so the
path runs through it); lots that M3 builds as a complex, traced and held lots are never cut.
An open space still without a way in says why (`attrs.access` none, `attrs.no_access`).

Every decision is an exact predicate on grid geometry (a segment against the lots shrunk by
`LOT_PAD_M`) or plain arithmetic, in a fixed order, so the paths are the same on every
machine."""

from __future__ import annotations

import heapq
import math

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient

from . import geom as G
from . import streets as ST

PATH_KINDS = ("park", "plaza", "pocket_park", "market", "garden", "promenade", "beach")
PATH_REACH_M = 30.0     # a path joins a walkway this close to its open space
PATH_GAP_M = 25.0       # paths of one open space join the walkways this far apart
PATH_MAX = 4            # at most this many paths per open space
PATH_W_M = 3.0
ATTACH_KINDS = ("sidewalk", "pedestrian_street", "promenade", "alley", "path")
LOT_PAD_M = 0.1         # a path may run along a lot's edge, not this far into it ...
PATH_CLEAR_M = 0.75     # ... but keeps this far from the lots where it can
BETWEEN_M = 0.5         # a path along the line between two lots for more than this has no
#                         room there
DETOUR = 2.5            # a bent path at most this many times the straight line (plus 15 m)
CORNERS_MAX = 32        # the open space's reflex corners a path may bend at (nearest first)
CANDIDATES_MAX = 8      # walkways tried per open space
PASSAGE_W_M = 3.0       # a passage carved from the lots to an enclosed open space
PASSAGE_REACH_M = 150.0  # ... along lot boundaries at most this long
PASSAGE_LOSS = 0.35     # ... taking at most this share of a lot's area
EDGE_SNAP_M = 0.05


class Blocked:
    """The ground a path may not cross: the lots, the water and the megasite reserves, grown
    by `pad` (PATH_CLEAR_M: a path clear of them; -LOT_PAD_M: one that may run along their
    edges, but never between two lots, where there is no room for it: a passage is for
    that). `replace` puts a lot's new polygon in (a passage cut from it)."""

    def __init__(self, lots: list, others: list, pad: float, between: bool = True):
        self.pad = pad
        self.between = between
        self.lots = [self._shrunk(p) for p in lots]
        self.rims = [self._rim(p) for p in lots]
        self.others = []
        for g in others:
            if g is not None and not g.is_empty:
                self.others += self._shrunk(g)
        self._index()

    def _shrunk(self, p) -> list:
        s = G.qpoly(p.buffer(self.pad, join_style="mitre"))
        out = [q for q in G.parts(s) if not q.is_empty]
        for q in out:
            shapely.prepare(q)
        return out

    def _rim(self, p):
        """The lot grown by LOT_PAD_M: a path within it runs along the lot's edge."""
        if self.pad >= 0.0 or not self.between:
            return None
        g = G.qpoly(p.buffer(LOT_PAD_M, join_style="mitre"))
        shapely.prepare(g)
        return g

    def _index(self) -> None:
        self.polys = [q for ps in self.lots for q in ps] + self.others
        self.tree = shapely.STRtree(self.polys) if self.polys else None
        rims = [g for g in self.rims if g is not None]
        self.rim_of = [i for i, g in enumerate(self.rims) if g is not None]
        self.rim_tree = shapely.STRtree(rims) if rims else None

    def replace(self, i: int, poly) -> None:
        self.lots[i] = self._shrunk(poly)
        self.rims[i] = self._rim(poly)
        self._index()

    def clear(self, a, b) -> bool:
        if self.tree is None:
            return True
        seg = LineString([a, b]) if a != b else Point(a)
        for i in self.tree.query(seg).tolist():
            if self.polys[i].intersects(seg):
                return False
        if self.rim_tree is None or a == b:
            return True
        ks = sorted(int(k) for k in self.rim_tree.query(seg, predicate="intersects"))
        if len(ks) < 2:
            return True
        rims = [self.rims[self.rim_of[k]] for k in ks]
        hugs = [G.line_inter(seg, g) for g in rims]
        for x in range(len(ks)):
            if G.length1(hugs[x]) <= BETWEEN_M:
                continue
            for y in range(x + 1, len(ks)):
                if G.length1(hugs[y]) > BETWEEN_M and \
                        G.length1(G.line_inter(hugs[x], rims[y])) > BETWEEN_M:
                    return False      # (along the line between two lots)
        return True

    def clear_line(self, pts) -> bool:
        return all(self.clear(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _reflex(poly) -> list[tuple[float, float]]:
    """The corners of a polygon a shortest path inside it can bend at: its exterior's reflex
    corners and its holes' convex ones (the ring oriented counterclockwise, holes clockwise:
    a right turn either way)."""
    p = orient(poly, 1.0)
    out = []
    for ring in [p.exterior, *p.interiors]:
        pts = G._ring(ring.coords)
        n = len(pts)
        if n < 3:
            continue
        for i in range(n):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
            cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if cr < 0:
                out.append(ST._pt(*b))
    return out


def route(c, foot, poly, blocked: Blocked, corners=None):
    """A path from c to foot that keeps off the blocked ground: straight, else the shortest
    bending at the polygon's reflex corners and where it is nearest the foot; None when there
    is none within DETOUR."""
    if blocked.clear(c, foot):
        return [c, foot]
    direct = ST._dist(c, foot)
    cap = DETOUR * direct + 15.0
    q = G.nearest(poly, Point(foot))
    cs = corners if corners is not None else _reflex(poly)
    seg = LineString([c, foot])
    cs = sorted(set(cs) - {c, foot, q},
                key=lambda v: (round(seg.distance(Point(v)), 6), v))[:CORNERS_MAX]
    nodes = [c, foot, q] + cs
    # (the last leg first: no way out of the open space to the foot, no path)
    if not any(blocked.clear(v, foot) for v in nodes[2:]):
        return None
    dist = {0: 0.0}
    prev: dict = {}
    heap = [(0.0, 0)]
    done = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in done:
            continue
        done.add(u)
        if u == 1:
            break
        for v in range(len(nodes)):
            if v in done or v == u:
                continue
            nd = d + ST._dist(nodes[u], nodes[v])
            if nd > cap or nd >= dist.get(v, math.inf) - 1e-9:
                continue
            if not blocked.clear(nodes[u], nodes[v]):
                continue
            dist[v] = nd
            prev[v] = u
            heapq.heappush(heap, (nd, v))
    if 1 not in dist:
        return None
    out = [1]
    while out[-1] != 0:
        out.append(prev[out[-1]])
    return [nodes[i] for i in reversed(out)]


class Attach:
    """The walkways a park path may join (ground, at grade, not another park's path)."""

    def __init__(self, W):
        self.idx = [i for i, e in enumerate(W.edges)
                    if e["kind"] in ATTACH_KINDS and abs(e["z"]) < 1e-9 and
                    not e["attrs"].get("open_space") and len(e["pts"]) >= 2]
        self.lines = [LineString(W.edges[i]["pts"]) for i in self.idx]
        self.tree = shapely.STRtree(self.lines) if self.lines else None
        self.W = W

    def near(self, geom, d: float) -> list[int]:
        """Positions of the walkways within d of geom, nearest first."""
        if self.tree is None:
            return []
        ks = sorted(int(k) for k in self.tree.query(geom, predicate="dwithin", distance=d))
        return sorted(ks, key=lambda k: (G.dist(geom, self.lines[k]), k))

    def foot(self, k: int, geom) -> tuple[float, float]:
        """The point of walkway k nearest geom (its end when that close to one)."""
        pts = self.W.edges[self.idx[k]]["pts"]
        f = G.nearest(self.lines[k], geom)
        if ST._dist(f, pts[0]) <= EDGE_SNAP_M:
            return ST._pt(*pts[0])
        if ST._dist(f, pts[-1]) <= EDGE_SNAP_M:
            return ST._pt(*pts[-1])
        return f


def paths_for(poly, attach: Attach, tiers: tuple) -> list:
    """Up to PATH_MAX paths from inside poly to the walkways near it: [(walkway position,
    foot, points)]. `tiers`: (clear, edge) Blocked grounds; a path clear of the lots by
    PATH_CLEAR_M (bending at the corners of the open space taken in by as much) where there
    is one, else one that may run along their edges."""
    c = G.qpoint(poly.representative_point())
    out = []
    regions = None
    for k in attach.near(poly, PATH_REACH_M)[:CANDIDATES_MAX * 3]:
        foot = attach.foot(k, poly)
        if any(ST._dist(foot, f) < PATH_GAP_M for _, f, _ in out):
            continue
        if regions is None:
            inner = [p for p in G.parts(G.qpoly(poly.buffer(-PATH_CLEAR_M - LOT_PAD_M,
                                                             join_style="mitre")))]
            regions = []
            if inner:
                big = max(inner, key=lambda p: (G.area1(p), G.qbounds(p)))
                regions.append((tiers[0], big, _reflex(big)))
            regions.append((tiers[1], poly, _reflex(poly)))
        r = None
        for blocked, region, corners in regions:
            r = route(c, foot, region, blocked, corners)
            if r is not None:
                break
        if r is None:
            continue
        out.append((k, foot, ST._dedupe(r)))
        if len(out) >= PATH_MAX:
            break
    return out


def split_edges(W, splits: dict) -> None:
    """Walk edges split at the path feet on them (edge index -> feet; the pieces keep the
    edge's kind, width, height and attributes)."""
    for i in sorted(splits, reverse=True):
        e = W.edges[i]
        pts = e["pts"]
        L = ST._plen(pts)
        ds = sorted({round(ST._project(pts, f)[0], 6) for f in splits[i]})
        ds = [d for d in ds if EDGE_SNAP_M < d < L - EDGE_SNAP_M]
        if not ds:
            continue
        feet = {round(ST._project(pts, f)[0], 6): ST._pt(*f) for f in splits[i]}
        cuts = [0.0] + ds + [L]
        pieces = []
        for a, b in zip(cuts, cuts[1:]):
            pc = ST._substring(pts, a, b)
            if a in feet:
                pc[0] = feet[a]
            if b in feet:
                pc[-1] = feet[b]
            pc = ST._dedupe(pc)
            if len(pc) >= 2:
                pieces.append(pc)
        W.edges[i:i + 1] = [{**e, "pts": pc} for pc in pieces]


# ---------------------------------------------------------------------------
# Passages to enclosed open space
# ---------------------------------------------------------------------------

def _segments(lines) -> list[tuple]:
    out = []
    for g in shapely.get_parts(lines).tolist() if not lines.is_empty else []:
        if g.geom_type != "LineString":
            continue
        pts = [ST._pt(*p[:2]) for p in g.coords]
        out += [(pts[i], pts[i + 1]) for i in range(len(pts) - 1) if pts[i] != pts[i + 1]]
    return out


def passage(o: dict, lots: list, attach: Attach, blocked: Blocked, frontage) -> dict | None:
    """A passage to an enclosed open space: the shortest run along lot boundaries (between
    two lots that may be cut) from its edge to a point from which a straight path reaches a
    walkway; a strip PASSAGE_W_M wide along it is taken from the lots and joins the open
    space. Returns {"polygon": the open space with it, "lots": {lot index: new polygon}} or
    None."""
    poly = o["polygon"]
    zone = poly.buffer(PASSAGE_REACH_M)
    near = [i for i, lt in enumerate(lots) if not G.apart(lt["polygon"], poly, PASSAGE_REACH_M)
            and lt["polygon"].intersects(zone)]
    if not near:
        return None
    cut_ok = {i for i in near if _cuttable(lots[i])}
    rings = [lots[i]["polygon"].exterior for i in near]
    segs = _segments(G.line_union([LineString(r.coords) for r in rings] +
                                  [LineString(poly.exterior.coords)]))
    lp = [lots[i]["polygon"] for i in near]
    ltree = shapely.STRtree(lp)
    shapely.prepare(poly)

    def touching(m):
        pt = Point(m)
        return [near[int(k)] for k in sorted(ltree.query(pt, predicate="dwithin",
                                                         distance=EDGE_SNAP_M).tolist())]

    adj: dict = {}
    on_open = set()
    for a, b in segs:
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if poly.boundary.distance(Point(m)) <= EDGE_SNAP_M:
            on_open.update((a, b))
            continue
        t = touching(m)
        if len(t) < 2 or not all(i in cut_ok for i in t):
            continue      # (a lot's frontage, or the edge of one that may not be cut)
        L = ST._dist(a, b)
        adj.setdefault(a, []).append((b, L))
        adj.setdefault(b, []).append((a, L))
    for v in list(adj):
        if poly.boundary.distance(Point(v)) <= EDGE_SNAP_M:
            on_open.add(v)
    src = sorted(v for v in on_open if v in adj)
    if not src:
        return None
    dist = {v: 0.0 for v in src}
    prev: dict = {}
    heap = [(0.0, v) for v in src]
    heapq.heapify(heap)
    best = None
    seen = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in seen:
            continue
        seen.add(u)
        if best is not None and d >= best[0]:
            break
        if d > 0.0:
            link = _link(u, attach, blocked)
            if link is not None and (best is None or d + link[0] < best[0] - 1e-9):
                best = (d + link[0], u)
        for v, L in adj.get(u, []):
            nd = d + L
            if nd > PASSAGE_REACH_M or nd >= dist.get(v, math.inf) - 1e-9:
                continue
            dist[v] = nd
            prev[v] = u
            heapq.heappush(heap, (nd, v))
    if best is None:
        return None
    run = [best[1]]
    while run[-1] in prev:
        run.append(prev[run[-1]])
    run = run[::-1]
    strip = G.qpoly(LineString(run).buffer(PASSAGE_W_M / 2, cap_style="flat",
                                           join_style="mitre", mitre_limit=2.0))
    out = _carve(poly, strip, near, lots, cut_ok, frontage)
    if out is None:
        # (the strip's first end only touches the open space at a corner: a round end)
        disk = G.qpoly(Point(run[0]).buffer(PASSAGE_W_M / 2, quad_segs=4))
        out = _carve(poly, G.union([strip, disk]), near, lots, cut_ok, frontage)
    if out is not None:
        out["run"] = run
    return out


def _carve(poly, strip, near: list, lots: list, cut_ok: set, frontage) -> dict | None:
    """The strip taken from the lots it cuts (each kept whole, with most of its area and its
    frontage) and joined to the open space, or None."""
    new_lots = {}
    taken = [poly]
    for i in near:
        lt = lots[i]["polygon"]
        if not lt.intersects(strip) or G.area1(G.inter(lt, strip)) < 0.01:
            continue
        if i not in cut_ok:
            return None
        rest = G.diff(lt, strip)
        ps = G.parts(rest)
        if not ps:
            return None
        big = max(ps, key=lambda p: (G.area1(p), G.qbounds(p)))
        if math.fsum(G.area1(p) for p in ps) - G.area1(big) > 1.0:
            return None       # (it would cut the lot in two)
        if G.area1(big) < (1.0 - PASSAGE_LOSS) * G.area1(lt):
            return None
        fr = frontage.of(big)
        if _access(fr) < 2.0:
            return None
        new_lots[i] = (big, fr)
        taken.append(G.diff(lt, big))
    joined = G.union(taken)
    if joined.geom_type != "Polygon":
        return None
    return {"polygon": joined, "lots": new_lots}


def _cuttable(lt: dict) -> bool:
    a = lt.get("attrs") or {}
    return not (lt.get("merged_group_id") or a.get("pinned") or a.get("pin") or
                a.get("held") or lt.get("level"))


def _access(fr) -> float:
    from .blocks import ACCESS

    return math.fsum(x[2] for x in fr if x[1] in ACCESS)


def _link(v, attach: Attach, blocked: Blocked):
    """(length, position, foot) of a straight path from v to the nearest walkway it reaches
    within PATH_REACH_M, or None."""
    p = Point(v)
    for k in attach.near(p, PATH_REACH_M)[:CANDIDATES_MAX]:
        f = attach.foot(k, p)
        if blocked.clear(v, f):
            return (ST._dist(v, f), k, f)
    return None


def open_paths(W, opens: list[dict], lots: list[dict], others: list, segments: list) -> dict:
    """Paths from every park, plaza, pocket park, market, garden, promenade and beach of
    `opens` (dicts with id, kind, polygon) to the ground walkways of W beside it, passages to
    the enclosed ones (their polygons and the lots they cut are updated in place: `lots`
    dicts with polygon, area_m2, frontage, frontage_ids). Returns counts and the open spaces
    left with no way in, with why."""
    from .blocks import Frontage

    attach = Attach(W)
    tiers = (Blocked([lt["polygon"] for lt in lots], others, PATH_CLEAR_M),
             Blocked([lt["polygon"] for lt in lots], others, -LOT_PAD_M))
    blocked = tiers[1]
    frontage = Frontage(segments)
    splits: dict = {}
    info = {"paths": 0, "bent": 0, "passages": 0, "passage_m2": 0.0, "no_access": []}
    for o in opens:
        if o["kind"] not in PATH_KINDS:
            continue
        poly = o["polygon"]
        if poly.geom_type != "Polygon" or poly.is_empty:
            continue
        ps = paths_for(poly, attach, tiers)
        if not ps:
            pg = passage(o, lots, attach, blocked, frontage)
            if pg is not None:
                A0 = G.area1(poly)
                o["polygon"] = poly = pg["polygon"]
                o["passage"] = [list(p) for p in pg["run"]]
                for i, (big, fr) in sorted(pg["lots"].items()):
                    _set_lot(lots[i], big, fr)
                    for t in tiers:
                        t.replace(i, big)
                info["passages"] += 1
                info["passage_m2"] = G.q(info["passage_m2"] + G.area1(poly) - A0)
                ps = paths_for(poly, attach, tiers)
        if not ps:
            why = ("no walkway within %g m" % PATH_REACH_M
                   if not attach.near(poly, PATH_REACH_M) else
                   "every walkway near it lies past a lot, the water or a megasite")
            o["no_access"] = why + " and no passage along lot boundaries"
            info["no_access"].append((o.get("id"), o["no_access"]))
            continue
        for k, foot, pts in ps:
            W.add("path", pts, PATH_W_M, open_space=o.get("id"))
            splits.setdefault(attach.idx[k], []).append(foot)
            info["paths"] += 1
            info["bent"] += len(pts) > 2
    split_edges(W, splits)
    return info


def _set_lot(lt: dict, poly, fr) -> None:
    """A lot after a passage took a strip of it: polygon, area and frontage again (as
    `blocks.finish_lots` records them)."""
    lt["polygon"] = poly
    lt["area_m2"] = G.q(G.area1(poly))
    lt["frontage"] = [{"segment_id": sid, "road_class": cls, "length_m": L, "line": line}
                      for sid, cls, L, line, _ in fr if len(line) >= 2]
    lt["frontage_ids"] = [f["segment_id"] for f in lt["frontage"]]
    lt.setdefault("attrs", {})["passage"] = True


# ---------------------------------------------------------------------------
# Every ground walkway off the lots
# ---------------------------------------------------------------------------

DETOUR_PAD_M = 0.3      # a walkway led round a lot passes its corners this far out
DETOUR_NODES = 60


def keep_off(W, lots: list[dict], any_z: bool = False) -> dict:
    """Every ground walkway of W off the lots: a stretch that cuts into a lot (a sidewalk's
    chord across a block's rounded corner, a crossing's leg to a corner, a link between two
    walkway groups) is led round it by the shortest way past the lots' corners
    (DETOUR_PAD_M out). Returns {"rerouted": stretches led round, "left": stretches with no
    way round (an end inside a lot)}. `any_z`: every edge of W (a deck's walk graph, whose
    edges sit at its top), not only those at z 0."""
    polys = [lt["polygon"] for lt in lots]
    bl = Blocked(polys, [], -LOT_PAD_M, between=False)
    if bl.tree is None:
        return {"rerouted": 0, "left": 0}
    raw = shapely.STRtree(polys)
    out = {"rerouted": 0, "left": 0}
    for e in W.edges:
        if abs(e["z"]) > 1e-9 and not any_z:
            continue
        pts = e["pts"]
        new = [pts[0]]
        changed = False
        for a, b in zip(pts, pts[1:]):
            if bl.clear(a, b):
                new.append(b)
                continue
            r = _detour(a, b, polys, raw, bl)
            if r is None:
                new.append(b)
                out["left"] += 1
                continue
            new += r[1:]
            changed = True
            out["rerouted"] += 1
        if changed:
            e["pts"] = ST._dedupe(new)
    return out


def _detour(a, b, polys, raw, bl: Blocked):
    """The shortest way from a to b past the corners of the lots near them, clear of the
    lots; None when there is none within DETOUR."""
    L = ST._dist(a, b)
    win = LineString([a, b]).buffer(max(15.0, L), cap_style="square")
    cand = set()
    for i in sorted(int(k) for k in raw.query(win, predicate="intersects")):
        g = G.qpoly(polys[i].buffer(DETOUR_PAD_M, join_style="mitre", mitre_limit=2.0))
        for part in G.parts(g):
            cand.update(ST._pt(*p) for p in G._ring(part.exterior.coords))
    seg = LineString([a, b])
    cand -= {a, b}
    cand = [v for v in cand if bl.clear(v, v)]
    cand = sorted(cand, key=lambda v: (round(seg.distance(Point(v)), 6), v))[:DETOUR_NODES]
    nodes = [a, b] + cand
    cap = DETOUR * L + 15.0
    dist = {0: 0.0}
    prev: dict = {}
    heap = [(0.0, 0)]
    done = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in done:
            continue
        done.add(u)
        if u == 1:
            break
        for v in range(len(nodes)):
            if v in done or v == u:
                continue
            nd = d + ST._dist(nodes[u], nodes[v])
            if nd > cap or nd >= dist.get(v, math.inf) - 1e-9:
                continue
            if not bl.clear(nodes[u], nodes[v]):
                continue
            dist[v] = nd
            prev[v] = u
            heapq.heappush(heap, (nd, v))
    if 1 not in dist:
        return None
    path = [1]
    while path[-1] != 0:
        path.append(prev[path[-1]])
    return [nodes[i] for i in reversed(path)]
