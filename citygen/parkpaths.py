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
PATH_OUT_M = 20.0       # a path runs at most this far outside its open space (else it runs on
#                         beside the walkways round it to a far foot)
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
UNDER_REACH_M = 90.0    # access fix (#86): a path passing under raised roads joins a walkway
#                         this close to its open space ...
UNDER_DECK_M = 5.0      # ... under road decks at least this high (surface: M17 lets a path
#                         pass under 4.5 m, M18 fills under the decks lower than 4.5 m)
UNDER_STEP_M = 2.0      # a road's height sampled this often along it


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
    """The walkways a park path may join (ground, at grade, not another park's path; access
    fix: with `parks`, only the paths of the other open spaces, `own` the open space's
    own)."""

    def __init__(self, W, parks: bool = False, own=None):
        self.idx = [i for i, e in enumerate(W.edges)
                    if e["kind"] in ATTACH_KINDS and abs(e["z"]) < 1e-9 and
                    bool(e["attrs"].get("open_space")) == parks and len(e["pts"]) >= 2 and
                    (own is None or e["attrs"].get("open_space") != own)]
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


def _outside(pts, poly) -> float:
    """How far a path runs outside its open space (on a 1 mm scale)."""
    return round(G.length1(shapely.difference(LineString(pts), poly)), 3)


def paths_for(poly, attach: Attach, tiers: tuple, reach: float = PATH_REACH_M,
              foot_ok=None) -> list:
    """Up to PATH_MAX paths from inside poly to the walkways near it (within `reach`, at a
    foot `foot_ok(k, foot)` accepts): [(walkway position, foot, points)]. `tiers`: (clear,
    edge) Blocked grounds; a path clear of the lots by PATH_CLEAR_M (bending at the corners
    of the open space taken in by as much) where there is one, else one that may run along
    their edges."""
    c = G.qpoint(poly.representative_point())
    out = []
    regions = None
    for k in attach.near(poly, reach)[:CANDIDATES_MAX * 3]:
        foot = attach.foot(k, poly)
        if any(ST._dist(foot, f) < PATH_GAP_M for _, f, _ in out):
            continue
        if foot_ok is not None and not foot_ok(k, foot):
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
        if r is None or (out and _outside(r, poly) > PATH_OUT_M):
            continue      # (none, or a second that runs on beside a walkway to a far foot)
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


def _z_on(prof, s: float) -> float:
    return ST._z_on(prof, s)


def low_roads(segments: list, junctions: list, nodes: list, zone) -> object:
    """Access fix (#86): the carriageways near `zone` a path may not cross: every stretch of
    a road whose surface is lower than UNDER_DECK_M (at grade, a ramp's low end, a bridge
    approach), from curb to curb (its sidewalks are walkways a path may join), and the
    junctions of nodes that low. A covered tunnel's lid is not one (M9: streets cross it)."""
    out = []
    for s in segments:
        pts = [tuple(p[:2]) for p in s["centerline"]]
        if len(pts) < 2:
            continue
        line = LineString(pts)
        if G.apart(line, zone, s["width_m"]):
            continue
        cs = s.get("cross_section") or {}
        side = max(cs.get("sidewalk_m") or [0.0])
        half = max(s["width_m"] / 2.0 - side, 1.0)
        prof = s.get("z_profile") or []
        tun = bool(s.get("tunnel"))

        def low(z):
            return z < UNDER_DECK_M and not (tun and z <= ST.OVER_TUNNEL_Z_M + 0.5)

        if not prof:
            runs = [(0.0, ST._plen(pts))]
        else:
            L = ST._plen(pts)
            n = max(1, int(math.ceil(L / UNDER_STEP_M)))
            xs = [L * k / n for k in range(n + 1)]
            runs, cur = [], None
            for x in xs:
                if low(_z_on(prof, x)):
                    cur = [x, x] if cur is None else [cur[0], x]
                elif cur is not None:
                    runs.append(tuple(cur))
                    cur = None
            if cur is not None:
                runs.append(tuple(cur))
        for a, b in runs:
            a = max(0.0, a - UNDER_STEP_M)
            b = min(ST._plen(pts), b + UNDER_STEP_M)
            sub = ST._dedupe(ST._substring(pts, a, b))
            if len(sub) >= 2:
                out.append(G.qpoly(LineString(sub).buffer(half, cap_style="flat",
                                                          join_style="mitre")))
    zs = {n["id"]: (n.get("position") or [0.0, 0.0, 0.0])[2] if len(
        n.get("position") or []) > 2 else 0.0 for n in nodes}
    for j in junctions:
        if zs.get(j["node_id"], 0.0) >= UNDER_DECK_M:
            continue
        poly = j["polygon"]
        if isinstance(poly, dict):
            poly = G.from_model_poly(poly)
        if poly is None or poly.is_empty or G.apart(poly, zone, 0.0):
            continue
        out.append(G.qpoly(poly.buffer(-0.5, join_style="mitre")))
    return G.union([g for g in out if not g.is_empty])


GRADE_FOOT_M = 0.5      # ... and joins a walkway whose road is this low at its foot (the
#                         sidewalks of a raised road are at z 0 in the walk graph)


def foot_z(W, i: int, foot, segs: dict, node_z: dict, jnode: dict) -> float:
    """The height of the road a walkway runs on at foot: its segment's surface there (a
    sidewalk, an alley), its junction's node (a crossing), else 0 (a path)."""
    a = W.edges[i]["attrs"]
    s = segs.get(a.get("segment"))
    if s is not None and s.get("z_profile"):
        pts = [tuple(p[:2]) for p in s["centerline"]]
        return _z_on(s["z_profile"], ST._project(pts, foot)[0])
    if a.get("junction") in jnode:
        return node_z.get(jnode[a["junction"]], 0.0)
    return 0.0


def _grade_of(W, segments: list, junctions: list, nodes: list):
    segs = {s["id"]: s for s in segments}
    node_z = {n["id"]: (n.get("position") or [0.0, 0.0, 0.0])[2]
              if len(n.get("position") or []) > 2 else 0.0 for n in nodes}
    jnode = {j["id"]: j["node_id"] for j in junctions}
    return lambda i, foot: foot_z(W, i, foot, segs, node_z, jnode)


def _rows_near(segments: list, zone) -> list:
    """(segment id, right of way) of the roads near zone."""
    out = []
    for s in segments:
        pts = [tuple(p[:2]) for p in s["centerline"]]
        if len(pts) >= 2 and not G.apart(LineString(pts), zone, s["width_m"]):
            out.append((s["id"], LineString(pts).buffer(s["width_m"] / 2.0, cap_style="flat")))
    return out


def _under(W, ps: list, att: Attach, rows: list) -> bool:
    """Whether a path of ps crosses the right of way of a road other than the one its
    walkway runs on at its foot (it passes under that road)."""
    for k, _, pts in ps:
        own = W.edges[att.idx[k]]["attrs"].get("segment")
        line = LineString(pts)
        if any(sid != own and r.intersects(line) for sid, r in rows):
            return True
    return False


def under_paths(o: dict, attach: Attach, lots: list, others: list, low, at_grade=None) -> list:
    """Access fix (#86): paths from an open space that only roads cut off to the walkways
    up to UNDER_REACH_M away, passing under the raised roads between (never across a
    carriageway at grade): `paths_for` with the low carriageways blocked too, joining only
    walkways at grade (`at_grade(k, foot)`)."""
    poly = o["polygon"]
    zone = poly.buffer(UNDER_REACH_M + 20.0)
    near = [lt["polygon"] for lt in lots if not G.apart(lt["polygon"], zone, 0.0)]
    blk = list(others) + [low]
    tiers = (Blocked(near, blk, PATH_CLEAR_M), Blocked(near, blk, -LOT_PAD_M))
    return paths_for(poly, attach, tiers, reach=UNDER_REACH_M, foot_ok=at_grade)


def open_paths(W, opens: list[dict], lots: list[dict], others: list, segments: list,
               junctions: list | None = None, nodes: list | None = None) -> dict:
    """Paths from every park, plaza, pocket park, market, garden, promenade and beach of
    `opens` (dicts with id, kind, polygon) to the ground walkways of W beside it, passages to
    the enclosed ones (their polygons and the lots they cut are updated in place: `lots`
    dicts with polygon, area_m2, frontage, frontage_ids); access fix (#86): paths under the
    raised roads to the ones only roads cut off, and a park that has no street and still no
    way in becomes a green verge (`o["verge"]`, as the smaller roadless pieces are).
    Returns counts and the open spaces left with no way in, with why."""
    from .blocks import Frontage

    attach = Attach(W)
    tiers = (Blocked([lt["polygon"] for lt in lots], others, PATH_CLEAR_M),
             Blocked([lt["polygon"] for lt in lots], others, -LOT_PAD_M))
    blocked = tiers[1]
    frontage = Frontage(segments)
    splits: dict = {}
    info = {"paths": 0, "bent": 0, "passages": 0, "passage_m2": 0.0, "no_access": [],
            "under_roads": 0, "far_paths": 0, "via_open_space": 0, "verges": 0}
    late: list = []
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
            late.append(o)      # (access fix: the ways in of the second pass, below)
            continue
        _add(W, o, ps, attach, splits, info)
    # access fix (#86): the open spaces the first pass left without a way in (none in most
    # cities, so theirs are as they were): a path to a neighbor open space's path, else
    # under the raised roads that cut it off or to a walkway farther off, else a park with
    # no street becomes a green verge (as M2 makes the smaller roadless pieces), else it
    # says why
    grade = None
    for o in late:
        poly = o["polygon"]
        zone = poly.buffer(UNDER_REACH_M + 20.0)
        low = low_roads(segments, junctions or [], nodes or [], zone) if segments else None
        near = [lt["polygon"] for lt in lots if not G.apart(lt["polygon"], zone, 0.0)]
        blk = list(others) + ([low] if low is not None else [])
        mates = Attach(W, parks=True, own=o.get("id"))
        ps = paths_for(poly, mates, (Blocked(near, blk, PATH_CLEAR_M),
                                     Blocked(near, blk, -LOT_PAD_M)))
        if ps:
            o["far_path"] = "via_open_space"
            info["via_open_space"] += 1
            under = _under(W, ps, mates, _rows_near(segments, zone) if segments else [])
            _add(W, o, ps, mates, splits, info, under_road=under)
            continue
        if segments:
            if grade is None:
                grade = _grade_of(W, segments, junctions or [], nodes or [])
            ps = under_paths(o, attach, lots, others, low,
                             lambda k, f: grade(attach.idx[k], f) <= GRADE_FOOT_M)
            if ps:
                under = _under(W, ps, attach, _rows_near(segments, zone))
                o["far_path"] = "under_road" if under else "path"
                info["under_roads" if under else "far_paths"] += 1
                _add(W, o, ps, attach, splits, info, under_road=under)
                continue
        why = ("no walkway within %g m" % PATH_REACH_M
               if not attach.near(poly, PATH_REACH_M) else
               "every walkway near it lies past a lot, the water or a megasite")
        why += ", no passage along lot boundaries and no way under the roads round it"
        if o["kind"] == "park" and _access(frontage.of(poly)) < 2.0:
            # (land with no street that no walkway reaches, an interchange's infield, a
            # strip between the sea and a megasite: a verge)
            o["kind"] = "green"
            o["verge"] = why
            info["verges"] += 1
            continue
        o["no_access"] = why
        info["no_access"].append((o.get("id"), o["no_access"]))
    split_edges(W, splits)
    return info


def _add(W, o: dict, ps: list, attach: Attach, splits: dict, info: dict,
         under_road: bool = False) -> None:
    """The paths of an open space into W, their feet split in at the end."""
    for k, foot, pts in ps:
        if under_road:
            W.add("path", pts, PATH_W_M, open_space=o.get("id"), under_road=True)
        else:
            W.add("path", pts, PATH_W_M, open_space=o.get("id"))
        splits.setdefault(attach.idx[k], []).append(foot)
        info["paths"] += 1
        info["bent"] += len(pts) > 2


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
KEEP_PAD_M = 0.02       # ... and keeps out of it but this far in (the buildings on a lot keep
#                         their walls inside it, the check tests them 0.1 m in)
DETOUR_NODES = 60


def keep_off(W, lots: list[dict], any_z: bool = False) -> dict:
    """Every ground walkway of W off the lots: a stretch that cuts into a lot (a sidewalk's
    chord across a block's rounded corner, a crossing's leg to a corner, a link between two
    walkway groups) is led round it by the shortest way past the lots' corners
    (DETOUR_PAD_M out). Returns {"rerouted": stretches led round, "left": stretches with no
    way round (an end inside a lot)}. `any_z`: every edge of W (a deck's walk graph, whose
    edges sit at its top), not only those at z 0."""
    polys = [lt["polygon"] for lt in lots]
    bl = Blocked(polys, [], -KEEP_PAD_M, between=False)
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
                r = _detour(a, b, polys, raw, bl, blocks=True)
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


def _detour(a, b, polys, raw, bl: Blocked, blocks: bool = False):
    """The shortest way from a to b past the corners of the lots near them, clear of the
    lots; None when there is none within DETOUR. `blocks`: past the corners of the outline
    the lots near make together (a block and its neighbors), for a long way round that the
    lots' own corners, too many to try, miss."""
    L = ST._dist(a, b)
    win = LineString([a, b]).buffer(max(15.0, L), cap_style="square")
    cand = set()
    near = sorted(int(k) for k in raw.query(win, predicate="intersects"))
    if blocks:
        out = G.qpoly(G.union([polys[i] for i in near]).buffer(
            DETOUR_PAD_M, join_style="mitre", mitre_limit=2.0).simplify(0.5))
        for part in G.parts(out):
            for ring in [part.exterior, *part.interiors]:
                cand.update(ST._pt(*p) for p in G._ring(ring.coords))
    for i in near if not blocks else ():
        g = G.qpoly(polys[i].buffer(DETOUR_PAD_M, join_style="mitre", mitre_limit=2.0))
        for part in G.parts(g):
            cand.update(ST._pt(*p) for p in G._ring(part.exterior.coords))
    seg = LineString([a, b])
    cand -= {a, b}
    cand = [v for v in cand if bl.clear(v, v)]
    cap_n = min(DETOUR_NODES + int(L / 4.0), 3 * DETOUR_NODES)   # (more for a long way)
    cand = sorted(cand, key=lambda v: (round(seg.distance(Point(v)), 6), v))[:cap_n]
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
