"""Stage 6, junctions and cross-sections: intersection polygons, corner radii, sidewalks,
curbs, medians, crosswalks, signals, one-way streets, the lane graph and the walkway graph.

Junction polygons come from the cross-sections of the roads that meet: at every corner
between two neighboring legs (counterclockwise order), the left curb line of one leg and the
right curb line of the next meet at a corner point; a circular fillet of the corner radius of
the lesser class (highway 15 m, avenue 12 m, street by archetype 4 to 15 m, alley 3 m) is
tangent to both, and each leg's carriageway starts where its fillets end (its cut-back). The
same construction at the back of the sidewalks (property line, smaller radius) gives the
right-of-way corner that blocks lose.

Signals by junction class: two primary roads (highway or avenue), an avenue crossing a street
(four legs or more), and four-way street crossings in the corporate core, transit hub and
midtown are signalized. Crosswalks: every approach of a signalized junction; at unsignalized
junctions on avenues, every side street mouth. Other junctions get unmarked crossings (in the
walkway graph, not as crosswalk entities). Highways get no sidewalks and no unsignalized
crossings.

One-way streets: in the old town and the entertainment market some blocks bounded only by
narrow streets become one-way loops (all edges of the block face in one turning sense), which
keeps the lane graph strongly connected (a directed cycle can replace each lost direction).

Lane graph: the driving lanes of every road (inner lane index 0), trimmed to the cut-backs,
and connector lanes through every junction (straight from any lane, left turns from the
inner lane, right turns from the outer lane, U-turns at dead ends and map exits); alleys have
one shared lane used both ways.

Walkway graph: sidewalks on both sides of every road that has them, corners around each
junction, crossings and crosswalks, the centerlines of pedestrian streets, promenades,
footbridges, alleys and service lanes (shared with vehicles), and paths into open space
(added by the block stage).
"""

from __future__ import annotations

import math

import numpy as np
import shapely
import shapely.ops
from shapely.geometry import LineString, Point, Polygon

from . import decks as DK
from . import dmath as M
from . import geom as G
from . import pavement as PV
from . import streets as ST
from . import trace as T

CORNER_R = {"highway": 15.0, "avenue": 12.0, "service": 6.0, "alley": 3.0, "pedestrian": 1.0,
            "footbridge": 1.0}
ROW_CORNER_MIN_M = 1.0
CORNER_RUN_MAX_M = 60.0      # longest corner (fillet or sharp) along a leg
CUT_SHARE = 0.9              # M17: the cut-backs at a road's two ends take at most this of it
NODE_REACH_M = 0.5           # M22: an overlap of two legs this near their node is the node's
XWALK_PAD_M = 0.25           # M22: a crosswalk keeps this far off a port (wholly on one face)
CROSSWALK_SETBACK_M = 1.5
# M18: crossings by need. Crosswalk widths by the class of the road crossed (4 m on every
# crosswalk before; none on alleys and service roads), 5 m on a downtown avenue
CROSSWALK_W = {"highway": 4.0, "avenue": 4.0, "street": 3.0}
DOWNTOWN_ARCH = ("corporate_core", "transit_hub")
DOWNTOWN_AVENUE_W = 5.0
SIGNAL_STREET_ARCH = ("corporate_core", "transit_hub", "midtown_mixed")
SIGNAL_SPACING_M = 120.0    # a junction where a street meets a primary road (or a street
#                             crossing in SIGNAL_STREET_ARCH) gets signals only where no
#                             signalized junction is this near along either road
SPARSE_ARCH = ("old_town", "entertainment_market")    # (the old town and slum archetypes)
SPARSE_SPACING_M = 200.0    # ... in them
FEWER = 2.0                 # `junctions.signals` "fewer": the spacing this many times
ONE_WAY_SHARE = 0.4
TURN_STRAIGHT_DEG = 35.0


def _dist(a, b) -> float:
    return ST._dist(a, b)


def _unit(x, y):
    return ST._unit(x, y)


def _left(d):
    return (-d[1], d[0])


def _pt(x, y):
    return ST._pt(x, y)


class Leg:
    """A road at a node: direction away from the node, half widths, class."""

    def __init__(self, seg: dict, at_start: bool, arch: str | None):
        self.seg = seg
        self.at_start = at_start
        pts = [tuple(p) for p in seg["centerline"]]
        self.pts = pts if at_start else pts[::-1]
        self.L = ST._plen(self.pts)
        q, _ = ST._along(self.pts, min(10.0, self.L / 2))
        p = self.pts[0]
        self.p = p
        self.d = _unit(q[0] - p[0], q[1] - p[1])
        self.ang = M.atan2(self.d[1], self.d[0])
        cs = seg["cross_section"]
        self.cls = ST.street_class(seg)
        total = seg["width_m"]
        side = cs["sidewalk_m"][0] if cs.get("sidewalk_m") else 0.0
        if self.cls in ST.PEDESTRIAN:
            self.h = total / 2
            self.sw = 0.0
        else:
            self.h = total / 2 - side
            self.sw = side
        self.row = total / 2
        self.arch = arch
        if self.cls == "street":
            self.r = ST.style_of(arch or "midtown_mixed").radius
        elif self.cls == "service" and arch in ("industrial_port", "spaceport"):
            self.r = 10.0
        else:
            self.r = CORNER_R[self.cls]
        self.cut = 0.0
        self.cut_row = 0.0
        self.capped = False     # M17: its cut is short of where it parts from a neighbor
        self.need = 0.0         # M22: the cut its overlaps with other legs need


def _corner(P, a: Leg, b: Leg, ha: float, hb: float, r: float):
    """Fillet between leg a's left edge (offset ha) and leg b's right edge (offset hb), b
    counterclockwise from a. Returns (ta, tb, tangent point on a, on b, center, gap deg) or
    None when the edges do not converge (a gap of 180 degrees or more). A fillet whose run
    does not fit on the legs (0.45 of each, at most CORNER_RUN_MAX_M) becomes the sharp
    corner where the edges meet (center None); where that does not fit either (a ramp gore,
    whose edges meet hundreds of meters out), the corner is the node itself.
    """
    da, db = a.d, b.d
    na, nb = _left(da), _left(db)
    sinp = da[0] * db[1] - da[1] * db[0]
    cosp = da[0] * db[0] + da[1] * db[1]
    gap = M.degrees(M.atan2(sinp, cosp)) % 360.0
    if gap >= 178.0 or gap <= 0.5:
        return None
    # P + ha na + t1 da = P - hb nb + t2 db
    rx = -hb * nb[0] - ha * na[0]
    ry = -hb * nb[1] - ha * na[1]
    det = da[0] * (-db[1]) - da[1] * (-db[0])
    t1 = (rx * (-db[1]) - ry * (-db[0])) / det
    t2 = (da[0] * ry - da[1] * rx) / det
    tl = r * (1.0 + cosp) / sinp
    ta = max(t1 + tl, 0.0)
    tb = max(t2 + tl, 0.0)
    ra = min(0.45 * a.L, CORNER_RUN_MAX_M)
    rb = min(0.45 * b.L, CORNER_RUN_MAX_M)
    if ta > ra or tb > rb:
        if t1 <= ra and t2 <= rb:
            X = (P[0] + ha * na[0] + t1 * da[0], P[1] + ha * na[1] + t1 * da[1])
            return max(t1, 0.0), max(t2, 0.0), X, X, None, gap
        return 0.0, 0.0, P, P, None, gap
    Ta = (P[0] + ha * na[0] + ta * da[0], P[1] + ha * na[1] + ta * da[1])
    Tb = (P[0] - hb * nb[0] + tb * db[0], P[1] - hb * nb[1] + tb * db[1])
    O = (Ta[0] + r * na[0], Ta[1] + r * na[1])
    return ta, tb, Ta, Tb, O, gap


def _arc(O, A, Bp, r: float) -> list:
    a0 = M.atan2(A[1] - O[1], A[0] - O[0])
    a1 = M.atan2(Bp[1] - O[1], Bp[0] - O[0])
    sweep = (a1 - a0) % (2 * M.PI)
    if sweep > M.PI:
        sweep -= 2 * M.PI
    n = max(2, int(abs(sweep) / M.radians(15.0)) + 1)
    out = []
    for k in range(1, n):
        a = a0 + sweep * k / n
        out.append((O[0] + r * M.cos(a), O[1] + r * M.sin(a)))
    return out


def legs_at(net, arch_of) -> dict[str, list[Leg]]:
    """Legs at every node, counterclockwise."""
    out: dict[str, list[Leg]] = {}
    for s in net.segments:
        a = arch_of(s)
        out.setdefault(s["start"], []).append(Leg(s, True, a))
        out.setdefault(s["end"], []).append(Leg(s, False, a))
    for k in out:
        out[k].sort(key=lambda lg: (lg.ang, lg.seg["id"], lg.at_start))
    return out


def cutbacks(legs: list[Leg], cap: bool = True, one: bool = False) -> None:
    """Each leg's cut-back at a node; `cap` limits it to 0.45 of the leg (else `share_cuts`
    shares each road between its two junctions); `one` (M22): one cut per leg, past every
    overlap that reaches the node however far (`overlap_cuts(..., cap=False)`)."""
    n = len(legs)
    if n == 2:
        # M17: a bend between two roads (an avenue that ends in a street, a street that goes
        # on as a promenade) cuts back where their rights of way overlap
        overlap_cuts(legs, not one)
        if any(lg.cut > 0.0 for lg in legs):
            for lg in legs:
                lg.cut = min(lg.cut + 1.0, 0.45 * lg.L) if cap else lg.cut + 1.0
                lg.cut_row = min(lg.cut_row + 0.5, 0.45 * lg.L) if cap else lg.cut_row + 0.5
                if one:
                    lg.cut = lg.cut_row = max(lg.cut, lg.cut_row)     # (M22: one cut)
        return
    if n < 3:
        return
    P = legs[0].p
    for i in range(n):
        a, b = legs[i], legs[(i + 1) % n]
        r = min(a.r, b.r)
        c = _corner(P, a, b, a.h, b.h, r)
        if c is not None:
            a.cut = max(a.cut, c[0])
            b.cut = max(b.cut, c[1])
            if c[4] is None:
                # (M17: a corner too sharp for its fillet, or a fork: their rights of way
                # share pavement out past the curb corner)
                a.capped = b.capped = True
        rr = max(r - max(a.sw, b.sw), ROW_CORNER_MIN_M)
        c2 = _corner(P, a, b, a.row, b.row, rr)
        if c2 is not None:
            a.cut_row = max(a.cut_row, c2[0])
            b.cut_row = max(b.cut_row, c2[1])
    overlap_cuts(legs, not one)
    for lg in legs:
        lg.cut = min(lg.cut + 1.0, 0.45 * lg.L) if cap else lg.cut + 1.0
        lg.cut_row = min(lg.cut_row + 0.5, 0.45 * lg.L) if cap else lg.cut_row + 0.5
        if one:
            # M22: one cut per leg, where every band, sidewalk, crosswalk and lane ends
            lg.cut = lg.cut_row = max(lg.cut, lg.cut_row)


def lock_cuts(net, legs: dict) -> int:
    """M22: a leg's cut stops LOCK_GAP_M short of the nearest locked stretch on it (a
    bridge span, a road crossing over or under: `_locks`) where only its corner fillets ask
    for more (its overlaps with other legs still have it), so a junction does not reach onto
    a bridge and its port can be levelled. Returns how many cuts it shortened."""
    locks = _locks(net)
    n = 0
    for nid in sorted(legs):
        for x in legs[nid]:
            lk = locks.get(x.seg["id"])
            if not lk or x.cls == "footbridge":
                continue
            L = x.L
            near = min((s0 if x.at_start else L - s1) for s0, s1 in lk)
            if near <= 0.0:
                continue
            c = max(x.need + 1.0, near - LOCK_GAP_M)
            if c < x.cut - 0.0005:
                x.cut = x.cut_row = c
                n += 1
    return n


LOCK_GAP_M = 1.0        # M22: a junction's port this far short of a locked stretch
FOLD_REACH = 3.0        # M22: a fold this many half widths past a cut is the junction's


def fold_cuts(net, legs: dict) -> int:
    """M22: `_fold_cuts` until no cut moves (a cut moved past one fold or corner can land
    in the next), at most FOLD_ROUNDS times."""
    n = 0
    for _ in range(FOLD_ROUNDS):
        k = _fold_cuts(net, legs)
        n += k
        if not k:
            break
    return n


FOLD_ROUNDS = 6         # M22: rounds of `_fold_cuts`


def _fold_cuts(net, legs: dict) -> int:
    """M22: a leg whose right of way folds (a turn tighter than its half width:
    `pavement.Road.folds`) within FOLD_REACH half widths past its cut is cut past the fold,
    so the junction takes the bend and no bend face meets a port. Returns how many."""
    n = 0
    for nid in sorted(legs):
        lg = legs[nid]
        if len(lg) < 2 or not any(x.cut > 0.0 for x in lg):
            continue
        for x in lg:
            if x.cls == "footbridge":
                continue
            rd = PV.Road(x.seg)
            L = rd.path.L
            reach = x.cut + FOLD_REACH * rd.row
            if x.at_start:
                fs = rd.folds(min(x.cut, L), min(reach, L))
                far = max((b for a, b in fs), default=None)
            else:
                fs = rd.folds(max(L - reach, 0.0), max(L - x.cut, 0.0))
                far = max((L - a for a, b in fs), default=None)
            if far is not None and far + 0.5 > x.cut:
                x.cut = x.cut_row = far + 0.5
                n += 1
            # (a turn inside the cut whose inner corner reaches back past it: the cut past
            # that corner, half the width times tan(half the turn), sin / (1 + cos))
            acc = 0.0
            for i in range(1, len(x.pts) - 1):
                a, v, b = x.pts[i - 1], x.pts[i], x.pts[i + 1]
                acc += ST._dist(a, v)
                if acc >= x.cut or acc >= x.L - 1.0:
                    break
                la, lb = ST._dist(a, v), ST._dist(v, b)
                if la <= 0.0 or lb <= 0.0:
                    continue
                ux, uy = (v[0] - a[0]) / la, (v[1] - a[1]) / la
                wx, wy = (b[0] - v[0]) / lb, (b[1] - v[1]) / lb
                cr, dt = abs(ux * wy - uy * wx), ux * wx + uy * wy
                if cr < MITRE_TAN_MIN * (1.0 + dt):
                    continue        # (a gentle turn, a curve's vertices: no corner)
                t = MITRE_TAN_MAX if 1.0 + dt <= cr / MITRE_TAN_MAX else cr / (1.0 + dt)
                back = acc + x.row * t
                if back > x.cut:
                    x.cut = x.cut_row = min(G.q(back + 0.5), max(x.L - 1.0, x.cut))
                    n += 1
    return n


MITRE_TAN_MAX = 6.0     # M22: tan(half a turn) counted at most (a turn near a reversal)
MITRE_TAN_MIN = 0.2679  # M22: tan(half a turn) of a corner (a turn of 30 degrees or more)


def plan_units(net, legs: dict, heads: dict, gr=None) -> list[dict]:
    """M22: the junctions of a network as regions. A cul-de-sac's leg is cut where its
    carriageway and sidewalks meet the bulb; a road whose two cuts leave less than
    `pavement.MIN_ROAD_M` has no face of its own: its two junctions (or a junction and the
    plain node it reaches) are one, a cluster, the road inside it. Cuts are put on the 1 mm
    grid, so the model's copy is the cut itself. Returns [{nodes, inner, head}] by first
    node."""
    from .pavement import MIN_ROAD_M

    for nid in sorted(legs):
        lg = legs[nid]
        r = heads.get(nid, 0.0)
        if len(lg) == 1 and r:
            x = lg[0]
            x.cut = x.cut_row = math.sqrt(max((r + x.sw) ** 2 - x.row ** 2, r * r - x.h * x.h,
                                              0.0)) + 0.5
        for x in lg:
            x.cut = x.cut_row = math.floor(x.cut * 1000.0 + 0.5) / 1000.0
    jn = {nid for nid, lg in legs.items()
          if len(lg) >= 3 or (len(lg) == 2 and any(x.cut > 0.0 for x in lg)) or
          (len(lg) == 1 and heads.get(nid, 0.0) > 0.0)}
    g = gr.ramp_max if gr is not None else None
    for _ in range(CLUSTER_ROUNDS):
        groups, inner = _clusters(net, legs, jn, MIN_ROAD_M, g)
        # (the legs of a cluster that leave it from different nodes: their cuts past where
        # their rights of way overlap near it, as at one node; that may join more)
        if not _cluster_overlaps(legs, groups, inner):
            break
    groups, inner = _clusters(net, legs, jn, MIN_ROAD_M, g)
    out = []
    for ns in groups:
        if not any(n in jn for n in ns):
            continue
        inn = sorted(sid for sid in inner
                     if any(x.seg["id"] == sid for n in ns for x in legs.get(n, [])))
        out.append({"nodes": ns, "inner": inn,
                    "head": heads.get(ns[0], 0.0) if len(ns) == 1 and len(legs[ns[0]]) == 1
                    else 0.0,
                    # (a cul-de-sac's node a cluster takes in keeps its bulb)
                    "heads": {n: heads[n] for n in ns if len(ns) > 1 and
                              len(legs.get(n, [])) == 1 and heads.get(n, 0.0) > 0.0}})
    out.sort(key=lambda u: u["nodes"][0])
    return out


CLUSTER_ROUNDS = 4
CLUSTER_DZ_M = 3.0      # M22: junctions this far apart in height are not joined for it


def _clusters(net, legs: dict, jn: set, min_road: float, g=None) -> tuple[list, set]:
    """Groups of nodes joined by roads whose two cuts leave less than `min_road`, or (`g`)
    less than the road needs to climb from one junction's height to the other's at that
    grade (one with no bridge or tunnel on it, not a deck's): sorted lists, by first node;
    and those roads."""
    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    cut = {(x.seg["id"], x.at_start): x.cut for lg in legs.values() for x in lg}
    inner = set()
    for s in net.segments:
        if s["road_class"] == "footbridge" or not (s["start"] in jn or s["end"] in jn):
            continue
        a = cut.get((s["id"], True), 0.0) if s["start"] in jn else 0.0
        b = cut.get((s["id"], False), 0.0) if s["end"] in jn else 0.0
        L = ST._plen([tuple(p) for p in s["centerline"]])
        need = min_road
        if g and s["start"] in jn and s["end"] in jn and not (
                s.get("bridge") or s.get("bridge_ids") or _fixed22(s, None)):
            zp = s["z_profile"]
            dz = abs(_z_at(zp, L) - _z_at(zp, 0.0))
            if dz <= CLUSTER_DZ_M:     # (never one surface across two levels)
                need = max(need, dz / g)
        if a + b > L - need:
            parent[find(s["start"])] = find(s["end"])
            inner.add(s["id"])
    groups: dict = {}
    for nid in sorted(jn | set(parent)):
        groups.setdefault(find(nid), []).append(nid)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0]), inner


def _cluster_overlaps(legs: dict, groups: list, inner: set) -> bool:
    """M22: in a cluster, each leg's cut past every stretch where its right of way overlaps
    that of a leg leaving from another of its nodes, near the cluster (within NODE_REACH_M
    of its nodes and inner roads). Whether a cut grew."""
    grew = False
    for ns in groups:
        if len(ns) < 2:
            continue
        ext = [x for n in ns for x in legs.get(n, [])
               if x.seg["id"] not in inner and x.cls != "footbridge"]
        core = G.union([Point(x.p).buffer(0.5) for x in ext] +
                       [strip(x, x.L, x.row) for n in ns for x in legs.get(n, [])
                        if x.seg["id"] in inner])
        rows = [strip(x, x.L, x.row) for x in ext]
        for i in range(len(ext)):
            for j in range(i + 1, len(ext)):
                if ext[i].p == ext[j].p:
                    continue        # (one node: `overlap_cuts` has them)
                ov = G.inter(rows[i], rows[j])
                if ov.is_empty or G.area1(ov) < 0.5:
                    continue
                near = [q for q in G.parts(ov) if G.area1(q) >= 0.5 and
                        q.distance(core) <= NODE_REACH_M]
                if not near:
                    continue
                pts = shapely.points(shapely.get_coordinates(G.union(near)))
                for x in (ext[i], ext[j]):
                    far = float(shapely.line_locate_point(LineString(x.pts), pts).max())
                    c = math.floor((far + 1.5) * 1000.0 + 0.5) / 1000.0
                    x.need = max(x.need, far + 0.5)
                    if c > x.cut + 0.0005:
                        x.cut = x.cut_row = c
                        grew = True
    return grew


def share_cuts(legs: dict) -> None:
    """M17: the two junctions of a road share CUT_SHARE of it by need (one that needs less
    than half leaves the rest to the other), so a junction next to a small one reaches past
    its overlaps on a short road."""
    by_seg: dict = {}
    for nid in sorted(legs):
        for x in legs[nid]:
            by_seg.setdefault(x.seg["id"], []).append(x)
    for sid in sorted(by_seg):
        xs = by_seg[sid]
        avail = CUT_SHARE * xs[0].L
        for attr in ("cut", "cut_row"):
            need = [getattr(x, attr) for x in xs]
            if len(xs) == 2 and need[0] + need[1] > avail:
                a, b = need
                if a <= avail / 2:
                    b = avail - a
                elif b <= avail / 2:
                    a = avail - b
                else:
                    a = b = avail / 2
                need = [a, b]
            for x, c in zip(xs, need):
                if attr == "cut" and getattr(x, attr) > min(c, avail) + 0.01:
                    x.capped = True
                setattr(x, attr, min(c, avail))


def strip(lg: Leg, s: float, h: float):
    """A leg's band of half width h from the node to s along its centerline (flat ends)."""
    pts = ST._substring(lg.pts, 0.0, min(s, lg.L))
    if len(pts) < 2 or h <= 0.0:
        return Polygon()
    return G.qpoly(LineString(pts).buffer(h, cap_style="flat", join_style="mitre",
                                          mitre_limit=2.0))


def overlap_cuts(legs: list[Leg], cap: bool = True) -> None:
    """M17: each leg's cut reaches past every stretch where its right of way overlaps
    another leg's (an acute corner, a leg that bends inside the junction, a gore where a
    ramp leaves), as far as 0.45 of the leg, so two roads overlap only inside the junction
    polygon (`junction_polygon` adds a bent leg's carriageway out to its cut). M22 (`cap`
    False): as far along the whole leg as the overlap that reaches the node goes (one that
    does not reach it is another junction's); where a road's two cuts meet, its junctions
    are one (`plan_units`)."""
    reach = [CUT_SHARE * lg.L if cap else lg.L for lg in legs]
    rows = [strip(lg, r, lg.row) for lg, r in zip(legs, reach)]
    lines = [LineString(lg.pts) for lg in legs]
    P = Point(legs[0].p) if legs else None
    for i in range(len(legs)):
        for j in range(i + 1, len(legs)):
            ov = G.inter(rows[i], rows[j])
            if ov.is_empty or G.area1(ov) < 0.5:
                continue
            if not cap:
                # (the overlap that reaches the node, or runs on near it: two roads that part
                # from it at a small angle and run together a while)
                reach_n = max(NODE_REACH_M, legs[i].row + legs[j].row,
                              0.5 * min(legs[i].L, legs[j].L))
                near = [p for p in G.parts(ov) if p.distance(P) <= reach_n and
                        G.area1(p) >= 0.5]
                if not near:
                    continue
                ov = G.union(near)
            pts = shapely.points(shapely.get_coordinates(ov))
            for k in (i, j):
                far = float(shapely.line_locate_point(lines[k], pts).max())
                legs[k].cut = max(legs[k].cut, G.q(far + 0.5))
                legs[k].cut_row = max(legs[k].cut_row, legs[k].cut)
                legs[k].need = max(legs[k].need, G.q(far + 0.5))
                if far >= reach[k] - 1.0:
                    legs[k].capped = True    # (they overlap on past its reach)


def run_along(lg: Leg, c: float) -> float:
    """Length along a leg's centerline to where it crosses the line square to the leg's
    direction c from the node (the junction polygon's edge across the leg): c on a straight
    leg, more where the leg bends inside the junction."""
    if c <= 0.0:
        return 0.0
    P, d = lg.p, lg.d
    acc = 0.0
    for a, b in zip(lg.pts, lg.pts[1:]):
        ta = (a[0] - P[0]) * d[0] + (a[1] - P[1]) * d[1]
        tb = (b[0] - P[0]) * d[0] + (b[1] - P[1]) * d[1]
        ab = ST._dist(a, b)
        if tb >= c > ta:
            return round(acc + ab * (c - ta) / (tb - ta), 2)
        acc += ab
    return round(lg.L, 2)


def junction_polygon(legs: list[Leg], row: bool = False) -> Polygon:
    n = len(legs)
    if n == 2:
        return bend_polygon(legs, row)
    P = legs[0].p
    ring = []
    for i in range(n):
        a, b = legs[i], legs[(i + 1) % n]
        ha = a.row if row else a.h
        hb = b.row if row else b.h
        ca = a.cut_row if row else a.cut
        cb = b.cut_row if row else b.cut
        na = _left(a.d)
        nb = _left(b.d)
        ring.append((P[0] + ca * a.d[0] - ha * na[0], P[1] + ca * a.d[1] - ha * na[1]))
        ring.append((P[0] + ca * a.d[0] + ha * na[0], P[1] + ca * a.d[1] + ha * na[1]))
        r = min(a.r, b.r)
        if row:
            r = max(r - max(a.sw, b.sw), ROW_CORNER_MIN_M)
        c = _corner(P, a, b, ha, hb, r)
        if c is not None:
            _, _, Ta, Tb, O, _ = c
            ring.append(Ta)
            if O is not None:
                ring += _arc(O, Ta, Tb, r)
                ring.append(Tb)
        ring.append((P[0] + cb * b.d[0] - hb * nb[0], P[1] + cb * b.d[1] - hb * nb[1]))
    pts = ST._dedupe(ring)
    if len(pts) < 3:
        return Polygon()
    poly = G.qpoly(shapely.make_valid(Polygon(pts)))
    # M17: a leg that bends inside the junction keeps its band out to the cut (the ring
    # runs straight along its direction at the node)
    bent = [s for s in (strip(lg, lg.cut_row if row else lg.cut, lg.row if row else lg.h)
                        for lg in legs if _bends(lg, lg.cut_row if row else lg.cut))
            if G.area1(G.diff(s, poly)) > 0.5]
    return G.union([poly] + bent) if bent else poly


def shared_pavement(legs: list[Leg], poly):
    """M17: where two legs' rights of way overlap farther out than their cuts reach (a
    crossing or a fork at a small angle, a junction close to the next one), the overlap is
    pavement both share: the junction polygon takes it."""
    if not any(lg.capped for lg in legs):
        return poly
    rows = [strip(lg, lg.L, lg.row) for lg in legs]
    extra = []
    for i in range(len(legs)):
        for j in range(i + 1, len(legs)):
            if legs[i].capped or legs[j].capped:
                ov = G.inter(rows[i], rows[j])
                if G.area1(ov) > 0.5:
                    extra.append(ov)
    if not extra:
        return poly
    u = G.union([poly] + extra)
    ps = G.parts(u)
    if len(ps) <= 1:
        return u
    P = Point(legs[0].p)
    return min(ps, key=lambda q: (q.distance(P), G.qbounds(q)))


SHARED_M2 = 5.0     # M17: two primary roads' leftover overlap this big joins a junction


def absorb_shared(net, junctions: list[dict]) -> None:
    """M17: where two roads at one level still share pavement past their junction polygon
    (a fork that runs on past the next junction of one of them, two legs of a hairpin), the
    overlap joins the junction polygon it runs out of (the part that touches it): any two
    primary roads, and any two roads at a node they share. One that touches no junction
    stays (the check `road_overlaps` reports it)."""
    segs = net.segments
    if len(segs) < 2 or not junctions:
        return
    lines = [LineString(x["centerline"]) for x in segs]
    rows = np.array([G.qpoly(ln.buffer(x["width_m"] / 2, cap_style="flat", join_style="mitre",
                                       mitre_limit=2.0)) for x, ln in zip(segs, lines)],
                    dtype=object)
    prim = np.array([x["road_class"] in ("highway", "avenue") for x in segs], dtype=bool)
    jp = [j["polygon"] for j in junctions]
    at_node = {j["node_id"]: k for k, j in enumerate(junctions)}
    jtree = shapely.STRtree(jp)
    a, b = ST._pairs(shapely.STRtree(rows).query(rows, predicate="intersects"))
    shared = [sorted({segs[i]["start"], segs[i]["end"]} & {segs[k]["start"], segs[k]["end"]})
              for i, k in zip(a.tolist(), b.tolist())]
    keep = (a < b) & (prim[a] & prim[b] | np.array([bool(x) for x in shared], dtype=bool))
    # (a first pass in floating point: past the junction polygon at the node they share)
    jn = np.array([jp[at_node[x[0]]] if x and x[0] in at_node else Polygon() for x in shared],
                  dtype=object)
    ov = shapely.intersection(rows[a], rows[b])
    keep &= shapely.area(shapely.difference(ov, jn)) > SHARED_M2
    for i, k, sh in zip(a[keep].tolist(), b[keep].tolist(),
                        [x for x, y in zip(shared, keep) if y]):
        ov = G.inter(rows[i], rows[k])
        if G.area1(ov) <= SHARED_M2:
            continue
        near = sorted(int(x) for x in jtree.query(ov.buffer(1.5)))
        if not near:
            continue
        ov = G.diff(ov, G.union([jp[x] for x in near]))
        for part in G.parts(ov):
            if G.area1(part) <= SHARED_M2:
                continue
            p = part.representative_point()
            za = _z_at(segs[i]["z_profile"], lines[i].project(p))
            zb = _z_at(segs[k]["z_profile"], lines[k].project(p))
            if abs(za - zb) >= 4.0:
                continue
            touch = [x for x in near if jp[x].distance(part) <= 0.05]
            if not touch and sh and sh[0] in at_node:
                touch = [at_node[sh[0]]]     # (the junction of the node they share)
            if not touch:
                continue
            x = min(touch, key=lambda x: (jp[x].distance(part), junctions[x]["id"]))
            # (bridged to it where a sliver starts a few meters out)
            q = shapely.ops.nearest_points(jp[x], part)[0]
            hull = shapely.convex_hull(shapely.MultiPoint(
                list(shapely.get_coordinates(part)) + [(q.x, q.y)]))
            u = G.union([jp[x], G.qpoly(hull.buffer(0.05, join_style="mitre"))])
            ps = G.parts(u)
            jp[x] = junctions[x]["polygon"] = u if len(ps) <= 1 else max(
                ps, key=lambda q: (G.area1(q), G.qbounds(q)))


def bend_polygon(legs: list[Leg], row: bool = False) -> Polygon:
    """M17: a bend's surface: both carriageways (rights of way with `row`) out to their cuts
    and where the two rights of way overlap."""
    a, b = legs
    parts = [strip(x, x.cut_row if row else x.cut, x.row if row else x.h) for x in (a, b)]
    parts.append(G.inter(strip(a, a.cut_row if row else a.cut, a.row),
                         strip(b, b.cut_row if row else b.cut, b.row)))
    u = G.union(parts)
    ps = G.parts(u)
    return u if len(ps) <= 1 else max(ps, key=lambda q: (G.area1(q), G.qbounds(q)))


def _bends(lg: Leg, c: float) -> bool:
    """Whether a leg's centerline leaves its direction at the node by over 5 cm within c."""
    P, d = lg.p, lg.d
    acc = 0.0
    for a, b in zip(lg.pts, lg.pts[1:]):
        if abs((b[0] - P[0]) * d[1] - (b[1] - P[1]) * d[0]) > 0.05:
            return True
        acc += ST._dist(a, b)
        if acc >= c:
            return False
    return False


def classify(legs: list[Leg], arch: str | None) -> tuple[str, str, bool]:
    """(kind, shape, signal candidate). M18's candidates (`plan_signals` spaces them): two
    primary roads meeting (always signalized), a street meeting a primary road, a four-way
    street crossing in SIGNAL_STREET_ARCH; never an interchange of highways alone (M7), nor
    an alley or a service road meeting a road."""
    veh = sorted([lg.cls for lg in legs if lg.cls in ST.VEHICLE],
                 key=lambda c: -ST.RANK[c])
    n = len(legs)
    shape = {1: "dead_end", 2: "bend", 3: "T", 4: "X"}.get(n, "multi")
    if not veh:
        return "pedestrian", shape, False
    kind = veh[0] if len(veh) == 1 else f"{veh[0]}_{veh[1]}"
    if all(lg.cls == "highway" for lg in legs) or len(veh) < 3:
        return kind, shape, False  # an interchange in M7: no signals, no pedestrians
    n_p = sum(c in ST.PRIMARY for c in veh)
    n_s = veh.count("street")
    cand = n_p >= 3 or (n_p >= 1 and n_s >= 1) or \
        (n_p == 0 and n_s >= 4 and arch in SIGNAL_STREET_ARCH)
    return kind, shape, cand


def spacing(arch: str | None, signals: str = "auto") -> float:
    """M18: how far apart along a road the spaced signals of a district stand (and the
    marked crossings of an avenue away from them)."""
    d = SPARSE_SPACING_M if arch in SPARSE_ARCH else SIGNAL_SPACING_M
    return d * (FEWER if signals == "fewer" else 1.0)


def straight_on(legs: dict, nid: str, x: Leg, reach: float) -> list[tuple[str, float]]:
    """The nodes along a road from node nid out along leg x, going on straight through each
    node (the vehicle leg within TURN_STRAIGHT_DEG of straight ahead) until `reach`:
    [(node, distance)]."""
    out = []
    acc = 0.0
    seen = {nid}
    cmin = M.cos(M.radians(TURN_STRAIGHT_DEG))
    while True:
        s = x.seg
        far = s["end"] if x.at_start else s["start"]
        acc += x.L
        if acc > reach or far in seen:
            return out
        out.append((far, acc))
        seen.add(far)
        here = legs.get(far, [])
        back = [y for y in here if y.seg["id"] == s["id"] and y.at_start != x.at_start]
        if not back:
            return out
        bd = back[0].d
        best = None
        for y in here:
            if y is back[0] or y.cls not in ST.VEHICLE:
                continue
            c = -(y.d[0] * bd[0] + y.d[1] * bd[1])
            if c >= cmin and (best is None or (c, y.seg["id"]) > (best[0], best[1].seg["id"])):
                best = (c, y)
        if best is None:
            return out
        x = best[1]


def reach(legs: dict, nid: str, d: float, only=None) -> set:
    """The nodes within d along a road out of nid (`straight_on` along its vehicle legs, or
    those `only` picks)."""
    out: set = set()
    for x in legs[nid]:
        if x.cls in ST.VEHICLE and (only is None or only(x)):
            out |= {n for n, _ in straight_on(legs, nid, x, d)}
    return out


def _spaced(cands, legs: dict, gap: dict, marked: set, only=None) -> set:
    """Greedy spacing (candidates in order): a candidate is taken where no node of `marked`
    (which grows) lies within its spacing along its roads, and it lies within that of none
    taken before it (the walks along a road may part differently either way)."""
    taken: set = set()
    blocked: set = set()
    for nid in cands:
        r = reach(legs, nid, gap[nid], only)
        if nid in blocked or r & marked:
            continue
        marked.add(nid)
        taken.add(nid)
        blocked |= r
    return taken


def plan_signals(legs: dict, node_arch: dict, control) -> tuple[set, dict]:
    """M18: crossings by need. Signals where two primary roads meet; where a street meets a
    primary road, or at a four-way street crossing in SIGNAL_STREET_ARCH, only where no
    signalized junction is within `spacing` along either road (greedy: primary roads first,
    then the junctions with more vehicle legs, then from the west: a node's place, not its
    build-order id, so a district regeneration decides the same away from the district).
    `control(nid)` is the district's `junctions` (signals, crosswalks). Returns
    (signalized nodes, {candidate node: its spacing})."""
    sig: set = set()
    gap: dict = {}
    cands = []
    for nid in sorted(legs):
        lg = legs[nid]
        if len(lg) < 3:
            continue
        sigs = control(nid)[0]
        if sigs == "none":
            continue
        _, _, cand = classify(lg, node_arch.get(nid))
        if not cand:
            continue
        gap[nid] = spacing(node_arch.get(nid), sigs)
        n_p = sum(x.cls in ST.PRIMARY for x in lg)
        if n_p >= 3:
            sig.add(nid)
            continue
        if sigs == "fewer" and not n_p:
            continue      # ("fewer": no street crossing signalized)
        cands.append((n_p == 0, -sum(x.cls in ST.VEHICLE for x in lg), lg[0].p, nid))
    _spaced([c[-1] for c in sorted(cands)], legs, gap, sig)
    return sig, gap


def plan_crossings(legs: dict, node_arch: dict, control, signals: set) -> set:
    """M18: the unsignalized junctions with a marked crossing of their avenue: where neither a
    signalized junction nor another such crossing is within the district's spacing along the
    avenue (`junctions.crosswalks` "auto"; from the west)."""
    cands, gap = [], {}
    for nid in sorted(legs):
        lg = legs[nid]
        sigs, xws = control(nid)
        if nid in signals or xws != "auto" or len(lg) < 2 or \
                not any(x.cls == "avenue" for x in lg) or all(x.cls == "highway" for x in lg):
            continue
        if len(lg) == 2 and not any(x.cut > 0.0 for x in lg):
            continue      # (no junction there)
        cands.append((lg[0].p, nid))
        gap[nid] = spacing(node_arch.get(nid), sigs)
    return _spaced([c[-1] for c in sorted(cands)], legs, gap, set(signals),
                   lambda x: x.cls == "avenue")


def crosswalk_w(cls: str, arch: str | None) -> float:
    """M18: a crosswalk's width by the class of the road it crosses (0: none)."""
    if cls == "avenue" and arch in DOWNTOWN_ARCH:
        return DOWNTOWN_AVENUE_W
    return CROSSWALK_W.get(cls, 0.0)


# ---------------------------------------------------------------------------
# One-way loops
# ---------------------------------------------------------------------------

def one_way_loops(net, district_arch: dict, seed: int) -> int:
    """Turn some block faces bounded only by narrow organic streets into one-way loops. (M10:
    in a district regeneration a face with a held road stays as it is; the held roads keep
    their old state.)"""
    frame = getattr(net.builder, "frame", None) if net.builder is not None else None
    held = {s["id"] for s in net.segments if frame is not None and
            frame.match(s["centerline"]) is not None}
    segs = {s["id"]: s for s in net.segments}
    pos = {n["id"]: n["position"][:2] for n in net.nodes}
    out_edges: dict[str, list] = {}
    for s in net.segments:
        a, b = s["start"], s["end"]
        pa, pb = s["centerline"][1], s["centerline"][-2]
        out_edges.setdefault(a, []).append((M.atan2(pa[1] - pos[a][1], pa[0] - pos[a][0]),
                                            s["id"], b))
        out_edges.setdefault(b, []).append((M.atan2(pb[1] - pos[b][1], pb[0] - pos[b][0]),
                                            s["id"], a))
    for k in out_edges:
        out_edges[k].sort()
    seen = set()
    chosen = set()
    rng = ST._rng(seed, 31)
    count = 0
    for u in sorted(out_edges):
        for _, sid, v in out_edges[u]:
            if (u, sid) in seen:
                continue
            face = []
            cu, cs, cv = u, sid, v
            ok = True
            for _ in range(14):
                seen.add((cu, cs))
                face.append((cu, cs, cv))
                lst = out_edges[cv]
                j = next(i for i, e in enumerate(lst) if e[1] == cs and e[2] == cu)
                _, ns, nv = lst[(j - 1) % len(lst)]
                cu, cs, cv = cv, ns, nv
                if (cu, cs) == (u, sid):
                    break
            else:
                ok = False
            if not ok or len(face) < 3:
                continue
            ids = [f[1] for f in face]
            if len(set(ids)) != len(ids) or any(i in chosen or i in held for i in ids):
                continue
            area2 = 0.0
            for cu_, _, cv_ in face:
                area2 += pos[cu_][0] * pos[cv_][1] - pos[cv_][0] * pos[cu_][1]
            if area2 <= 0:
                continue  # the outer face
            good = True
            for i in ids:
                s = segs[i]
                d = s["attrs"].get("district")
                if s["road_class"] != "street" or district_arch.get(d) not in (
                        "old_town", "entertainment_market"):
                    good = False
                    break
            if not good or rng.uniform() > ONE_WAY_SHARE:
                continue
            for cu_, sid_, cv_ in face:
                s = segs[sid_]
                arch = district_arch.get(s["attrs"].get("district"))
                cs_ = ST.cross_section("street", arch, narrow=True)
                if s["start"] != cu_:
                    s["start"], s["end"] = s["end"], s["start"]
                    s["centerline"] = s["centerline"][::-1]
                    prof = s.get("z_profile") or []
                    if any(p["z"] != 0.0 for p in prof):
                        # (a street ramping up to a raised road keeps its ramp at that end)
                        L = prof[-1]["s"]
                        s["z_profile"] = [{"s": G.q(L - p["s"]), "z": p["z"]}
                                          for p in reversed(prof)]
                s["one_way"] = True
                s["cross_section"] = cs_
                s["lanes"] = cs_["lanes_forward"] + cs_["lanes_backward"]
                chosen.add(sid_)
            count += 1
    if frame is not None:
        frame.restore(net.segments)
    return count


# ---------------------------------------------------------------------------
# Lanes
# ---------------------------------------------------------------------------

def _offset(pts, d: float) -> list:
    if abs(d) < 1e-9:
        return [tuple(p) for p in pts]
    off = shapely.offset_curve(LineString(pts), d, join_style="mitre", mitre_limit=2.0)
    lines = ST._lines_of(off)
    if not lines:
        return []
    best = max(lines, key=lambda x: (ST._plen(x), x[0]))
    # offset_curve keeps the direction of the input (GEOS >= 3.11)
    return best


def _z_at(prof: list[dict], s: float) -> float:
    if not prof:
        return 0.0
    for a, b in zip(prof[:-1], prof[1:]):
        if a["s"] <= s <= b["s"]:
            if b["s"] == a["s"]:
                return max(a["z"], b["z"])
            return a["z"] + (s - a["s"]) / (b["s"] - a["s"]) * (b["z"] - a["z"])
    return prof[-1]["z"]


LEVEL_OUT_M = 10.0      # M18: a junction holds its height this far past its polygon on a leg
LEVEL_SHARE = 0.5       # at most this share of a leg (from both ends: all of it)
LEVEL_STEP_M = 1.0      # sampling of a levelled profile
LOCK_PAD_M = 3.0        # past the deck of a crossing road or a bridge span, a profile holds


def _fixed(s: dict, held) -> bool:
    """M18: a road whose profile the levelling leaves as it is: tunnels (M9), viaducts (M7),
    a deck's streets and ramps (M14), footbridge stairs, a held road (M10)."""
    a = s["attrs"]
    return bool(s.get("tunnel") or a.get("elevated") or "deck" in a or
                a.get("role") == "deck_ramp" or s["road_class"] == "footbridge" or
                (held is not None and held(s)))


def catch_grade(s: dict, gr) -> float:
    """M18: the grade a levelled leg rejoins its profile at (`highways.grades`): a ramp's
    maximum on ramps and local streets (M7's raised joins), a run's on primary roads."""
    # (M22: G_SAFE of it, so a cone sampled on the 1 cm grid stays within the grade)
    if s["attrs"].get("role") == "ramp" or s["road_class"] not in ("highway", "avenue"):
        return gr.ramp_max * G_SAFE
    return gr.run_max * G_SAFE


def _crossings(segments) -> dict[str, list[tuple[float, tuple]]]:
    """Points where two roads cross without a shared node (as `terrain.crossings`, which
    runs after M2): {segment id: [(s, key)]}; the point on the 1 cm grid, s by plain
    arithmetic on the centerline (`ST._project`), so no measure GEOS rounds reaches M2."""
    pts = [[tuple(p) for p in s["centerline"]] for s in segments]
    lines = [LineString(p) for p in pts]
    tree = shapely.STRtree(lines)
    ends = [{p[0], p[-1]} for p in pts]
    out: dict[str, list] = {}
    a_idx, b_idx = tree.query(lines, predicate="intersects")
    pairs = sorted({(min(a, b), max(a, b)) for a, b in zip(a_idx.tolist(), b_idx.tolist())
                    if a != b})
    for a, b in pairs:
        sa, sb = segments[a], segments[b]
        inter = lines[a].intersection(lines[b])
        if {sa["start"], sa["end"]} & {sb["start"], sb["end"]} and inter.geom_type == "Point":
            continue
        hits = [inter] if inter.geom_type == "Point" else \
            [g for g in getattr(inter, "geoms", []) if g.geom_type == "Point"]
        for xy in sorted({(G.q(p.x), G.q(p.y)) for p in hits}):
            if any(_dist(xy, e) < 1.0 for e in ends[a] | ends[b]):
                continue
            key = ("x", sa["id"], sb["id"], xy)
            out.setdefault(sa["id"], []).append((G.q(ST._project(pts[a], xy)[0]), key))
            out.setdefault(sb["id"], []).append((G.q(ST._project(pts[b], xy)[0]), key))
    return out


def _locks(net) -> dict:
    """Stretches of each road whose height the levelling keeps (s0, s1): bridge spans and the
    crossings of roads that pass over or under it, a deck's width and LOCK_PAD_M wide."""
    out: dict = {}
    by = {s["id"]: s for s in net.segments}
    for b in net.bridges:
        for sid in b.get("segment_ids") or []:
            s = by.get(sid)
            if s is None or len(b.get("line") or []) < 2:
                continue
            pts = [tuple(p) for p in s["centerline"]]
            ss = [ST._project(pts, (p[0], p[1]))[0] for p in (b["line"][0], b["line"][-1])]
            out.setdefault(sid, []).append((min(ss) - LOCK_PAD_M, max(ss) + LOCK_PAD_M))
    for sid, xs in _crossings(net.segments).items():
        for sx, key in xs:
            other = by[key[2] if key[1] == sid else key[1]]
            h = other["width_m"] / 2.0 + LOCK_PAD_M
            out.setdefault(sid, []).append((sx - h, sx + h))
    return out


def _levelled(prof: list[dict], L: float, ra: float, rb: float, g: float,
              za: float | None = None, zb: float | None = None) -> tuple:
    """A profile held at za (default: its start's height) over [0, ra] and at zb (its end's)
    over [L - rb, L] (0: not held), rejoining itself at grade g: the profile clamped between
    the cones of slope g from the held stretches (the median of the three keeps it within g
    where it was). An end not held keeps its height too (a cone from it with no hold: the
    hold at the other end cannot lift it off its node), and the holds shrink alike where the
    two heights leave them no room. Returns (profile, ra, rb)."""
    za = _z_at(prof, 0.0) if za is None else za
    zb = _z_at(prof, L) if zb is None else zb
    room = max(L - abs(za - zb) / g, 0.0)
    if ra + rb > room:
        f = room / (ra + rb)
        ra, rb = ra * f, rb * f
    n = max(int(math.ceil(L / LEVEL_STEP_M)), 1)
    ss = sorted({G.q(L * k / n) for k in range(n + 1)} | {G.q(p["s"]) for p in prof} |
                ({G.q(ra)} if ra else set()) | ({G.q(L - rb)} if rb else set()))
    out = []
    for s in ss:
        z = _z_at(prof, s)
        da, db = max(0.0, s - ra), max(0.0, L - s - rb)
        lo = max(za - g * da, zb - g * db)
        hi = min(za + g * da, zb + g * db)
        out.append((s, min(max(z, lo), hi)))
    from .elevated import compress

    return [{"s": s, "z": z} for s, z in compress(out)], G.q(ra), G.q(rb)


RAISE_MAX_M = 2.5       # M18: a junction raised at most this much to hold its legs level


def _steepest(prof: list[dict]) -> float:
    """The steepest grade of a z profile (both on the 1 cm grid: 1 cm of rounding)."""
    return max(((abs(b["z"] - a["z"]) - 0.01) / (b["s"] - a["s"])
                for a, b in zip(prof, prof[1:]) if b["s"] > a["s"]), default=0.0)


def _changed(a: list[dict], b: list[dict]) -> bool:
    return any(abs(p["z"] - _z_at(a, p["s"])) > 0.005 for p in b) or \
        any(abs(p["z"] - _z_at(b, p["s"])) > 0.005 for p in a)


def level_legs(net, legs: dict, gr, held=None, exits: dict | None = None) -> dict:
    """M18: every leg of a junction graded to arrive level: held at its node's height out to
    its polygon's edge (the farther of its run along to the cut and where it leaves the
    polygon, `exits`: (segment id, at its start) -> distance) and LEVEL_OUT_M beyond, at
    most LEVEL_SHARE of it, then back onto its own profile at `catch_grade` (`_levelled`).
    A leg whose levelling would move a locked stretch (a bridge span, a road crossing over
    or under it: `_locks`) keeps its profile at that end; its junction is then raised to
    its highest leg out at its run instead (at most RAISE_MAX_M, never under another road,
    every other leg brought up to it), else it carries the surface (`surfaces`). Roads
    `_fixed` keep theirs, as do the legs at a node on a viaduct (a ramp leaves it along the
    deck). Returns {"held": {(segment id, node id): run held}, counts}."""
    if gr is None:
        return {"held": {}, "levelled": 0, "kept": 0, "raised": 0}
    exits = exits or {}
    want: dict = {}
    for nid in sorted(legs):
        lg = legs[nid]
        n = len(lg)
        if n < 2 or (n == 2 and not any(x.cut > 0.0 for x in lg)):
            continue
        if any(x.seg["attrs"].get("elevated") for x in lg):
            continue
        for x in lg:
            k = (x.seg["id"], x.at_start)
            r = max(run_along(x, max(x.cut, x.cut_row)), exits.get(k, 0.0)) + LEVEL_OUT_M
            want[k] = (nid, min(r, LEVEL_SHARE * x.L))
    locks = _locks(net)
    by = {s["id"]: s for s in net.segments}
    runs: dict = {}       # (segment id, at start) -> run held (0: not)

    def fits(s, new, old) -> bool:
        L = G.q(ST._plen([tuple(p) for p in s["centerline"]]))
        return all(abs(_z_at(new, t) - _z_at(old, t)) <= 0.01
                   for s0, s1 in locks.get(s["id"], []) for t in _samples(s0, s1, L))

    for s in net.segments:
        a = want.get((s["id"], True))
        b = want.get((s["id"], False))
        if (a is None and b is None) or _fixed(s, held):
            continue
        prof = s["z_profile"]
        ra, rb = (a[1] if a else 0.0), (b[1] if b else 0.0)
        if all(p["z"] == 0.0 for p in prof):
            runs[(s["id"], True)], runs[(s["id"], False)] = ra, rb
            continue
        L = G.q(ST._plen([tuple(p) for p in s["centerline"]]))
        g = catch_grade(s, gr)
        best = None
        if _steepest(prof) > g + 1e-4:
            # (steeper than its catch-up grade somewhere already: the cones from its two
            # ends could not both hold it)
            runs[(s["id"], True)], runs[(s["id"], False)] = 0.0, 0.0
            continue
        for xa, xb in dict.fromkeys(((ra, rb), (ra, 0.0), (0.0, rb))):
            if not (xa or xb):
                continue
            new, xa, xb = _levelled(prof, L, xa, xb, g)
            if fits(s, new, prof):
                best = (xa, xb, new)
                break
        xa, xb = (best[0], best[1]) if best else (0.0, 0.0)
        if best is not None and _changed(prof, best[2]):
            s["z_profile"] = best[2]
        runs[(s["id"], True)], runs[(s["id"], False)] = xa, xb
    # a junction a leg of which could not be held level (or not out to its polygon's edge)
    # is raised to its highest leg out at its run, its other legs brought up to it
    node = {n["id"]: n for n in net.nodes}
    over = _overhead(net)
    raised = 0
    for nid in sorted(legs):
        lg = legs[nid]
        ks = [(x, (x.seg["id"], x.at_start)) for x in lg]
        if not all(k in want for _, k in ks) or any(_fixed(x.seg, held) for x in lg):
            continue
        if all(runs.get(k, 0.0) >= min(want[k][1], exits.get(k, 0.0) + 0.5) for _, k in ks):
            continue
        zn = node[nid]["position"][2]
        top = max(_z_at(x.seg["z_profile"], want[k][1] if x.at_start else x.L - want[k][1])
                  for x, k in ks)
        # (M7: a local road meets a primary road at most LOCAL_JUNCTION_Z_M up)
        cap = ST.LOCAL_JUNCTION_Z_M if any(x.cls not in ST.PRIMARY for x in lg) else math.inf
        if not (zn + 0.01 < top <= min(zn + RAISE_MAX_M, cap)) or over(node[nid], top) or \
                len({k[0] for _, k in ks}) < len(ks):
            continue
        new = {}
        for x, k in ks:
            s = x.seg
            L = G.q(x.L)
            ro = runs.get((s["id"], not x.at_start), 0.0)
            if x.at_start:
                prof, ra, rb = _levelled(s["z_profile"], L, want[k][1], ro,
                                         catch_grade(s, gr), za=top)
            else:
                prof, ra, rb = _levelled(s["z_profile"], L, ro, want[k][1],
                                         catch_grade(s, gr), zb=top)
            g = catch_grade(s, gr)
            near, far = (0.0, L) if x.at_start else (L, 0.0)
            if not fits(s, prof, s["z_profile"]) or abs(_z_at(prof, near) - top) > 0.01 or \
                    abs(_z_at(prof, far) - _z_at(s["z_profile"], far)) > 0.01 or \
                    _steepest(prof) > g + 1e-4:
                new = None
                break
            new[k] = (prof, ra if x.at_start else rb)
        if not new:
            continue
        for x, k in ks:
            prof, r = new[k]
            by[x.seg["id"]]["z_profile"] = prof
            runs[k] = r
        pos = node[nid]["position"]
        node[nid]["position"] = (pos[0], pos[1], G.q(top))
        raised += 1
    raised += _held_heights(net, legs, gr, held, want, runs, node, fits)
    held_runs = {}
    n_lev = n_kept = 0
    for (sid, at_start), (nid, r) in sorted(want.items()):
        got = runs.get((sid, at_start))
        if got is None:
            continue      # (a fixed road)
        if got:
            held_runs[(sid, nid)] = got
            n_lev += 1
        else:
            n_kept += 1
    return {"held": held_runs, "levelled": n_lev, "kept": n_kept, "raised": raised,
            "runs": runs, "fits": fits}


BUILD_TOL = 0.005       # M22: slope rounding (heights on the 1 cm grid)


def junction_grade(legs, gr) -> float:
    """M22: the grade a junction's surface may have: the steepest its roads' classes may
    climb (M13's class grades: highway 6%, avenue 8%, street 12%, alley 15%), never less
    than M18's ramp maximum."""
    from .terrain import MAX_GRADE

    g = gr.ramp_max
    for x in legs:
        g = max(g, MAX_GRADE.get(x.cls if hasattr(x, "cls") else x, gr.ramp_max))
    return g


def _fixed22(s: dict, held) -> bool:
    """M22: the roads whose profile no levelling moves: tunnels (M9), a deck's streets and
    ramps (M14), footbridge stairs, held roads (M10). Viaducts and ramps may be held level
    over a junction their ports leave (where M18's locks allow)."""
    a = s["attrs"]
    return bool(s.get("tunnel") or "deck" in a or a.get("role") == "deck_ramp" or
                s["road_class"] == "footbridge" or (held is not None and held(s)))


def port_slopes(ports: list) -> float:
    """The steepest slope between two of a junction's ports [(z, end a, end b)] (ends in
    meters): their heights over the least distance between their lines."""
    worst = 0.0
    for i in range(len(ports)):
        for j in range(i + 1, len(ports)):
            za, a0, a1 = ports[i]
            zb, b0, b1 = ports[j]
            d = min(_pseg(a0, b0, b1), _pseg(a1, b0, b1), _pseg(b0, a0, a1), _pseg(b1, a0, a1))
            worst = max(worst, abs(za - zb) / max(d, 0.5))
    return worst


def _pseg(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    x, y = a[0] + t * dx - p[0], a[1] + t * dy - p[1]
    return math.sqrt(x * x + y * y)


def buildable(net, units: list, legs: dict, gr, held, plan, lev: dict) -> dict:
    """M22: invariant 5 of the pavement map, the slope between any two ports of a junction
    within the grade one surface can carry (M18's ramp maximum), levelled further where
    M18's levelling leaves it broken.

    The heights of every junction (its nodes are one), of each of its ports and of every
    plain node are fitted on one graph, M13's grade-line fit on the network: a port lies
    within PORT_SHARE of the grade times half its least distance to another port of its
    junction (and the leg's run to it) from the junction's height, so two ports are always
    within the grade of each other; two ports joined by a road within the road's catch grade
    times its length between them. The fit is the one closest in the largest deviation to
    the heights as they are: per variable U = min over all (target + distance), Lo = max
    (target - distance), their mean, clamped between the anchors' bounds: a fixed road's
    ports (`_fixed22`) and a road whose locked stretch (a bridge span, a road crossing
    over or under: `_locks`) reaches into a junction as they are, a locked stretch's ends,
    a map exit; a node under another road not raised, a junction of a local road at most
    LOCAL_JUNCTION_Z_M up (M7), none under the ground. A junction no height fits (or whose
    roads that fit cannot reach within their grade) is kept as it was, its own ties cut so
    it holds nothing else back, and the fit made again, until none is left. Each road
    changed is then run from its node's height to its ports' and clamped between the cones
    from its ports and locks (`_conform`). Returns counts: junctions over the grade before
    and after (first nodes; they fail `pavement_junctions`), junctions kept."""
    import heapq

    out = {"unbuildable": 0, "levelled_further": 0, "unresolved": []}
    if gr is None:
        return out
    lim = gr.ramp_max
    _GR[0] = gr
    ulim = {u["nodes"][0]: junction_grade([x for nd in u["nodes"] for x in legs[nd]
                                           if x.seg["id"] not in set(u["inner"]) and
                                           x.cls != "footbridge"], gr)
            for u in units}
    before = _port_report(net, units, legs, plan, lim)
    out["unbuildable"] = len(before)
    # (and the junctions whose faces, drawn as the map will draw them, would be too steep)
    steep0 = [u["nodes"][0] for u in units if not u["head"] and
              u["nodes"][0] not in before and
              PV.unit_grade(plan, u["id"], _port_heights(u, legs, plan)) >
              ulim[u["nodes"][0]] + BUILD_TOL]
    out["steep"] = len(steep0)
    if not before and not steep0:
        return out
    gj = lim * PORT_SHARE
    node = {n["id"]: n for n in net.nodes}
    inner_all = {sid for u in units for sid in u["inner"]}
    var = {nid: ("j", nid) for nid in node}    # every node its own variable
    unit_first = {nd: u["nodes"][0] for u in units for nd in u["nodes"]}
    locks = _locks(net)
    over = _overhead(net)
    target: dict = {}
    for nid in sorted(node):
        target[var[nid]] = node[nid]["position"][2]
    ties: list = []             # (variable, variable, weight, junction or None)
    anchors: list = []          # (variable, value, distance, kind: both | up)
    port_var: dict = {}         # (segment id, at start) -> variable
    for u in units:
        if u["head"]:
            continue
        inner = set(u["inner"])
        ext = [(nd, x) for nd in u["nodes"] for x in legs[nd] if x.seg["id"] not in inner and
               x.cls != "footbridge" and x.seg["id"] in plan.roads]
        lines = []
        for nd, x in ext:
            rd = plan.roads[x.seg["id"]]
            sp, pts = rd.port("start" if x.at_start else "end")
            lines.append((nd, x, sp, (pts[0][1][0] / 1000.0, pts[0][1][1] / 1000.0),
                          (pts[-1][1][0] / 1000.0, pts[-1][1][1] / 1000.0)))
        jk = ("j", u["nodes"][0])
        for i, (nd, x, sp, a0, a1) in enumerate(lines):
            pv = ("p", x.seg["id"], x.at_start)
            port_var[(x.seg["id"], x.at_start)] = pv
            target[pv] = _z_at(x.seg["z_profile"], sp)
            # (no steeper from its node to its port than its road's catch grade, or than it
            # is there already)
            gw = max(catch_grade(x.seg, gr), _steepest(_window(x.seg["z_profile"],
                                                                       x, sp)))
            ties.append((var[nd], pv, gw * max(x.cut, 0.0), jk))
            for j in range(i):
                _, y, _, b0, b1 = lines[j]
                d = min(_pseg(a0, b0, b1), _pseg(a1, b0, b1), _pseg(b0, a0, a1),
                        _pseg(b1, a0, a1))
                # (invariant 5: two ports of a junction within its grade of each other)
                ties.append((pv, ("p", y.seg["id"], y.at_start),
                             ulim[u["nodes"][0]] * PORT_SHARE * d, jk))
        for sid in inner:
            sg = next((x.seg for nd in u["nodes"] for x in legs[nd] if x.seg["id"] == sid),
                      None)
            if sg is not None and not _fixed22(sg, held) and not locks.get(sid):
                L = ST._plen([tuple(q) for q in sg["centerline"]])
                ties.append((var[sg["start"]], var[sg["end"]],
                             max(catch_grade(sg, gr), _steepest(sg["z_profile"])) * L, jk))
            # (a port beside an inner road: within the junction's grade of the inner road's
            # surface beside it, so within that and the inner road's own climb from its
            # nearer node; a long cluster, a bridge landing beside a ramp inside it)
            rd_in = plan.roads.get(sid)
            if sg is None or rd_in is None:
                continue
            g_in = max(catch_grade(sg, gr), _steepest(sg["z_profile"]))
            L_in = rd_in.path.L
            for nd, x, sp, a0, a1 in lines:
                best = None
                for q in (a0, a1):
                    st = rd_in.path.project(q[0], q[1], 0.0, L_in)
                    cx, cy = rd_in.path.point(st, 0.0)
                    gap = max(math.hypot(q[0] - cx / 1000.0, q[1] - cy / 1000.0) - rd_in.row,
                              0.0)
                    if best is None or gap < best[0]:
                        best = (gap, st)
                gap, st = best
                if gap > BESIDE_M or not (0.0 < st < L_in):
                    continue
                near, sd = (sg["start"], st) if st <= L_in - st else (sg["end"], L_in - st)
                ties.append((("p", x.seg["id"], x.at_start), var[near],
                             g_in * sd + ulim[u["nodes"][0]] * PORT_SHARE * gap, jk))
    group: dict = {}            # a junction (its first node) or plain node -> its variables
    ends = {x["id"]: (x["start"], x["end"]) for x in net.segments}
    for k in target:
        nd = k[1] if k[0] == "j" else ends[k[1]][0 if k[2] else 1]
        group.setdefault(("j", unit_first.get(nd, nd)), set()).add(k)
    of = {k: jk for jk, ks in group.items() for k in ks}
    roads = []
    for sg in net.segments:
        rd = plan.roads.get(sg["id"])
        if sg["road_class"] == "footbridge" or rd is None:
            # (a road the map does not draw keeps its profile: its nodes stay where its ends
            # are, so it meets them at their height, `level_continuity`)
            prof = sg["z_profile"]
            if prof:
                why = ("fixed", sg["id"])
                anchors.append((var[sg["start"]], prof[0]["z"], 0.0, "both", why))
                anchors.append((var[sg["end"]], prof[-1]["z"], 0.0, "both", why))
            continue
        L = rd.path.L
        prof = sg["z_profile"]
        va = port_var.get((sg["id"], True), var[sg["start"]])
        vb = port_var.get((sg["id"], False), var[sg["end"]])
        if sg["id"] in inner_all:
            if _fixed22(sg, held) or locks.get(sg["id"]):
                anchors.append((var[sg["start"]], _z_at(prof, 0.0), 0.0, "both",
                                ("inner fixed", sg["id"])))
                anchors.append((var[sg["end"]], _z_at(prof, L), 0.0, "both",
                                ("inner fixed", sg["id"])))
            continue
        ca, cb = rd.a, L - rd.b
        g = max(catch_grade(sg, gr), _steepest(prof))
        lk = sorted((max(s0, 0.0), min(s1, L)) for s0, s1 in locks.get(sg["id"], [])
                    if s1 > s0)
        if _fixed22(sg, held) or any(s0 < ca or s1 > cb for s0, s1 in lk):
            # (a fixed road, or one whose locked stretch reaches into a junction, as it is)
            why = ("fixed" if _fixed22(sg, held) else "lock in window", sg["id"])
            anchors.append((va, _z_at(prof, ca), 0.0, "both", why))
            anchors.append((vb, _z_at(prof, cb), 0.0, "both", why))
            if va[0] == "p":
                anchors.append((var[sg["start"]], _z_at(prof, 0.0), 0.0, "both", why))
            if vb[0] == "p":
                anchors.append((var[sg["end"]], _z_at(prof, L), 0.0, "both", why))
            continue
        cur_s, cur_v = ca, ("var", va)
        free = []
        for s0, s1 in lk:
            free.append((cur_s, cur_v, s0, ("val", _z_at(prof, s0))))
            cur_s, cur_v = s1, ("val", _z_at(prof, s1))
        free.append((cur_s, cur_v, cb, ("var", vb)))
        for s0, p0, s1, p1 in free:
            w = g * max(s1 - s0, 0.0)
            if p0[0] == "var" and p1[0] == "var":
                ties.append((p0[1], p1[1], w, None))
            elif p0[0] == "var":
                anchors.append((p0[1], p1[1], w, "both", ("lock", sg["id"])))
            elif p1[0] == "var":
                anchors.append((p1[1], p0[1], w, "both", ("lock", sg["id"])))
        roads.append((sg, rd, va, vb, ca, cb, g, lk))
    deg: dict = {}
    loc: dict = {}
    for sg in net.segments:
        for e in (sg["start"], sg["end"]):
            deg[e] = deg.get(e, 0) + 1
            if sg["road_class"] not in ST.PRIMARY:
                loc[e] = True
    for nid, n in sorted(node.items()):
        v = var[nid]
        z = n["position"][2]
        if (n.get("attrs") or {}).get("kind") == "exit":
            anchors.append((v, z, 0.0, "both", ("exit", nid)))
        elif over(n, z + 0.5):
            anchors.append((v, z, 0.0, "up", ("under", nid)))  # (not raised under a road)
        if deg.get(nid, 0) >= 3 and loc.get(nid):
            anchors.append((v, max(z, ST.LOCAL_JUNCTION_Z_M), 0.0, "up", ("local cap", nid)))

    def spread(adj: dict, seeds: dict) -> dict:
        """Multi-source shortest paths: value(v) = min over seeds (seed + distance)."""
        dist = dict(seeds)
        hq = [(d, k) for k, d in sorted(seeds.items())]
        heapq.heapify(hq)
        while hq:
            d, k = heapq.heappop(hq)
            if d > dist.get(k, math.inf):
                continue
            for nb, w in adj.get(k, []):
                nd = d + w
                if nd < dist.get(nb, math.inf) - 1e-12:
                    dist[nb] = nd
                    heapq.heappush(hq, (nd, nb))
        return dist

    def nodez(nid, zv, kept):
        """A node's height (as it was where its junction is kept)."""
        return node[nid]["position"][2] if of[var[nid]] in kept else zv[var[nid]]

    def solve(kept: set, flat: set = frozenset()) -> tuple[dict, set]:
        adj: dict = {}
        for u, v, w, jk in ties:
            if jk is not None and jk in kept:
                continue        # (a kept junction's own ties cut)
            if jk is not None and jk in flat and u[0] == "p" and v[0] == "p":
                w = 0.0         # (a junction whose face would be too steep: flat)
            adj.setdefault(u, []).append((v, w))
            adj.setdefault(v, []).append((u, w))
        up_seed: dict = {}
        lo_seed: dict = {}
        for v, val, w, kind, _ in anchors:
            up_seed[v] = min(up_seed.get(v, math.inf), val + w)
            if kind == "both":
                lo_seed[v] = min(lo_seed.get(v, math.inf), -(val - w))
        for jk in kept:
            for k in group[jk]:
                up_seed[k] = min(up_seed.get(k, math.inf), target[k])
                lo_seed[k] = min(lo_seed.get(k, math.inf), -target[k])
        UA = spread(adj, up_seed)
        LA = {k: -x for k, x in spread(adj, lo_seed).items()}
        U = spread(adj, {k: min(z, UA.get(k, math.inf)) for k, z in target.items()})
        Lo = {k: -x for k, x in spread(adj, {k: -max(z, LA.get(k, -math.inf))
                                              for k, z in target.items()}).items()}
        zv = {}
        bad = set()
        for k in sorted(target):
            if of[k] in kept:
                zv[k] = target[k]
                continue
            lo_h, up_h = LA.get(k, -math.inf), UA.get(k, math.inf)
            if lo_h > up_h + 1e-6:
                bad.add(of[k])
                zv[k] = target[k]
                continue
            z = (U.get(k, target[k]) + Lo.get(k, target[k])) / 2.0
            z = min(max(z, lo_h), up_h)
            if up_h >= 0.0:
                z = max(z, 0.0)     # (none under the ground: tunnels are fixed roads)
            zv[k] = G.q(z)
        for sg, rd, va, vb, ca, cb, g, lk in roads:
            vs = (var[sg["start"]], va, vb, var[sg["end"]])
            if all(of[v] in kept for v in vs):
                continue
            _, crossed = _conform(sg["z_profile"], rd.path.L, ca, cb,
                                  nodez(sg["start"], zv, kept), zv[va], zv[vb],
                                  nodez(sg["end"], zv, kept), g, lk)
            if crossed:
                bad |= {of[v] for v in vs if of[v] not in kept}
        return zv, bad
    kept: set = set()
    flat: set = set()
    ulist = [u for u in units if not u["head"]]
    for _ in range(FLAT_ROUNDS):
        for _ in range(KEEP_ROUNDS):
            zv, bad = solve(kept, flat)
            if not bad:
                break
            kept |= bad
        else:
            zv, _ = solve(kept, flat)
        # (a junction whose carriageway face, drawn as the map will draw it, would be steeper
        # than its grade is made flat, and the fit made again)
        steep = set()
        for u in ulist:
            jk = ("j", u["nodes"][0])
            if jk in kept or jk in flat:
                continue
            pz = {(k[1], k[2]): zv[k] for k in group[jk] if k[0] == "p"}
            if PV.unit_grade(plan, u["id"], pz) > ulim[u["nodes"][0]] + BUILD_TOL:
                steep.add(jk)
        if not steep:
            break
        flat |= steep
    # (the roads changed: a junction one of whose roads still cannot be run kept too, until
    # every road runs)
    for _ in range(KEEP_ROUNDS):
        hit = {k for k in zv if abs(zv[k] - target[k]) > 0.005}
        plan_new = {}
        more = set()
        for sg, rd, va, vb, ca, cb, g, lk in roads:
            vs = (var[sg["start"]], va, vb, var[sg["end"]])
            if not (set(vs) & hit) or all(of[v] in kept for v in vs):
                continue
            new, crossed = _conform(sg["z_profile"], rd.path.L, ca, cb,
                                    nodez(sg["start"], zv, kept), zv[va], zv[vb],
                                    nodez(sg["end"], zv, kept), g, lk)
            # (and within the grade checks: `road_grades`, `ramp_grades`)
            cap = max(catch_grade(sg, gr) / G_SAFE, _steepest(sg["z_profile"]))
            if crossed or _steepest(new) > cap + 1e-4:
                more |= {of[v] for v in vs} - kept
            else:
                plan_new[sg["id"]] = new
        if not more:
            break
        kept |= more
        for jk in more:
            for k in group[jk]:
                zv[k] = target[k]
    # (what holds each junction kept: the two bounds that clash on it)
    out["held"] = {}
    whys = _why_kept(ties, anchors, group, kept, flat) if kept else []
    for first, k, ups, los in whys:
        # (ids in lists, so M10's renaming finds them: `ids.Renamer._attrs`)
        if ups and los and los[0][0] > ups[0][0] + 1e-6:
            out["held"][first] = {"low": [los[0][1][0], los[0][1][1], round(los[0][0], 2)],
                                  "high": [ups[0][1][0], ups[0][1][1], round(ups[0][0], 2)]}
        else:
            out["held"][first] = {"grade": True}
    by_id = {x["id"]: x for x in net.segments}
    for sid, new in sorted(plan_new.items()):
        if _changed(by_id[sid]["z_profile"], new):
            by_id[sid]["z_profile"] = new
    for sid in sorted(inner_all):
        sg = next((x for x in net.segments if x["id"] == sid), None)
        if sg is None or _fixed22(sg, held) or sg["road_class"] == "footbridge" or \
                locks.get(sid):
            continue
        if of[var[sg["start"]]] in kept:
            continue
        L = G.q(ST._plen([tuple(p) for p in sg["centerline"]]))
        z0, z1 = zv[var[sg["start"]]], zv[var[sg["end"]]]
        flat = [{"s": 0.0, "z": z0}, {"s": L, "z": z1}]
        if _changed(sg["z_profile"], flat):
            sg["z_profile"] = flat
    moved = 0
    for nid, n in node.items():
        pos = n["position"]
        if of[var[nid]] in kept:
            continue            # (a kept junction's nodes as they were, each its own)
        z = zv[var[nid]]
        if abs(pos[2] - z) > 0.005:
            n["position"] = (pos[0], pos[1], z)
            moved += 1
    after = _port_report(net, units, legs, plan, lim)
    after += [u["nodes"][0] for u in units if not u["head"] and
              u["nodes"][0] not in after and
              PV.unit_grade(plan, u["id"], _port_heights(u, legs, plan)) >
              ulim[u["nodes"][0]] + BUILD_TOL]
    out["levelled_further"] = len(set(before) | set(steep0)) - len(after)
    out["unresolved"] = sorted(after)
    out["nodes_moved"] = moved
    out["no_fit"] = len(kept)
    return out


KEEP_ROUNDS = 12        # M22: rounds of the fit, each keeping the junctions no height fits
G_SAFE = 0.985          # M22: the fit keeps this share of a grade (profiles on the 1 cm grid)


def _window(prof: list, x, sp: float) -> list:
    """The stretch of a profile between a leg's node and its port at sp."""
    a, b = (0.0, sp) if x.at_start else (sp, prof[-1]["s"] if prof else sp)
    return [p for p in prof if a - 1e-9 <= p["s"] <= b + 1e-9]
FLAT_ROUNDS = 6         # M22: rounds that make the junctions whose faces would be steep flat
PORT_SHARE = 0.98       # M22: two ports of a junction within this share of its grade
BESIDE_M = 6.0          # M22: a port this near an inner road's right of way is tied to it
CROSS_TOL_M = 0.02      # M22: cones that cross by more than this: no height fits there


def _why_kept(ties, anchors, group, kept, flat) -> list:
    """M22: for each junction the fit kept, the two anchors that clash on it: of its
    variables, the one whose lowest bound from above (an anchor's value plus its distance
    on the graph) is furthest under its highest bound from below; (first node, variable,
    [(bound, why, anchor variable)] from above, the same from below). Bounds within
    WHY_REACH_M of height are searched (a farther anchor binds nothing here)."""
    import heapq

    adj: dict = {}
    for u, v, w, jk in ties:
        if jk is not None and jk in flat and u[0] == "p" and v[0] == "p":
            w = 0.0
        adj.setdefault(u, []).append((v, w))
        adj.setdefault(v, []).append((u, w))
    at: dict = {}
    for v, val, w, kind, why in anchors:
        at.setdefault(v, []).append((val, w, kind, why))

    def bounds(src):
        dist = {src: 0.0}
        hq = [(0.0, src)]
        up, lo = None, None
        while hq:
            d, k = heapq.heappop(hq)
            if d > dist.get(k, math.inf):
                continue
            for val, w, kind, why in at.get(k, []):
                if up is None or val + w + d < up[0]:
                    up = (val + w + d, why, k)
                if kind == "both" and (lo is None or val - w - d > lo[0]):
                    lo = (val - w - d, why, k)
            for nb, w in adj.get(k, []):
                nd = d + w
                if nd <= WHY_REACH_M and nd < dist.get(nb, math.inf) - 1e-12:
                    dist[nb] = nd
                    heapq.heappush(hq, (nd, nb))
        return up, lo
    out = []
    for jk in sorted(kept):
        best = None
        for k in sorted(group[jk]):
            up, lo = bounds(k)
            gap = (lo[0] if lo else -math.inf) - (up[0] if up else math.inf)
            if best is None or gap > best[0]:
                best = (gap, k, up, lo)
        _, k, up, lo = best
        out.append((jk[1], k, [up] if up else [], [lo] if lo else []))
    return out


WHY_REACH_M = 40.0      # M22: how far in height `_why_kept` searches for a binding anchor


def why_text(why: dict) -> str:
    """M22: what holds a junction the height fit kept (`attrs.unbuildable`), in words."""
    if why.get("grade"):
        return "its roads, which cannot reach its ports within their grade"
    if why.get("drawn"):
        return (f"its faces, which the map draws at {why['drawn']:.1%} from its ports where "
                f"the fit's estimate did not (two of its roads parting at different grades "
                f"inside it, a concave outline)")

    def one(kind, ref):
        return {"local cap": f"M7's {ST.LOCAL_JUNCTION_Z_M:g} m limit at local junction {ref}",
                "lock": f"the locked stretch of {ref}",
                "lock in window": f"the locked stretch of {ref} reaching into a junction",
                "inner fixed": f"fixed road {ref}",
                "fixed": f"fixed road {ref}",
                "exit": f"map exit {ref}",
                "under": f"the road over {ref}"}.get(kind, f"{kind} {ref}")
    lo, hi = why["low"], why["high"]
    return (f"{one(lo[0], lo[1])} ({lo[2]:.2f} m at least) against {one(hi[0], hi[1])} "
            f"({hi[2]:.2f} m at most)")


def _port_heights(u: dict, legs: dict, plan) -> dict:
    """{(segment id, at start): height} of a junction's ports on the profiles as they are."""
    inner = set(u["inner"])
    out = {}
    for nd in u["nodes"]:
        for x in legs[nd]:
            if x.seg["id"] in inner or x.cls == "footbridge" or x.seg["id"] not in plan.roads:
                continue
            rd = plan.roads[x.seg["id"]]
            sp, _ = rd.port("start" if x.at_start else "end")
            out[(x.seg["id"], x.at_start)] = _z_at(x.seg["z_profile"], sp)
    return out


def _port_report(net, units: list, legs: dict, plan, lim: float) -> list:
    """The junctions (their first nodes) whose ports break invariant 5 (`port_slopes`) on
    the profiles as they are."""
    bad = []
    for u in units:
        if u["head"]:
            continue
        inner = set(u["inner"])
        ext = [x for nd in u["nodes"] for x in legs[nd] if x.seg["id"] not in inner and
               x.cls != "footbridge" and x.seg["id"] in plan.roads]
        if len(ext) < 2:
            continue
        ps = []
        for x in ext:
            rd = plan.roads[x.seg["id"]]
            sp, pts = rd.port("start" if x.at_start else "end")
            a, b = pts[0][1], pts[-1][1]
            ps.append((_z_at(x.seg["z_profile"], sp), (a[0] / 1000.0, a[1] / 1000.0),
                       (b[0] / 1000.0, b[1] / 1000.0)))
        if port_slopes(ps) > junction_grade([x for x in ext], _GR[0]) + BUILD_TOL:
            bad.append(u["nodes"][0])
    return bad


_GR = [None]            # (the grades `buildable` runs with, for `_port_report`)


def _conform(prof: list, L: float, ca: float, cb: float, n0: float, za: float, zb: float,
             n1: float, g: float, locks: list):
    """M22: a road's profile run from its start node's height n0 to its port's za at ca
    (straight), likewise from zb at cb to its end node's n1, its locked stretches as they
    are, and the rest clamped between the cones of slope g from its ports and locks (the
    fit `buildable` found keeps them within reach). None where they cross (no change)."""
    fixed = [(ca, za), (cb, zb)]
    for s0, s1 in locks:
        fixed += [(s0, _z_at(prof, s0)), (s1, _z_at(prof, s1))]
    n = max(int(math.ceil(L / LEVEL_STEP_M)), 1)
    ss = sorted({G.q(L * k / n) for k in range(n + 1)} | {G.q(p["s"]) for p in prof} |
                {G.q(min(max(x, 0.0), L)) for x, _ in fixed} | {0.0, G.q(L)})
    out = []
    crossed = False
    for t in ss:
        if t <= ca:
            out.append((t, n0 + (za - n0) * (t / ca) if ca > 0 else za))
            continue
        if t >= cb:
            out.append((t, zb + (n1 - zb) * ((t - cb) / (L - cb)) if L > cb else zb))
            continue
        if any(s0 <= t <= s1 for s0, s1 in locks):
            out.append((t, _z_at(prof, t)))
            continue
        lo = max(zf - g * abs(t - sf) for sf, zf in fixed)
        hi = min(zf + g * abs(t - sf) for sf, zf in fixed)
        if lo > hi:
            crossed = crossed or lo > hi + CROSS_TOL_M
            out.append((t, (lo + hi) / 2.0))    # (rounding: the middle)
            continue
        out.append((t, min(max(_z_at(prof, t), lo), hi)))
    from .elevated import compress

    return [{"s": t, "z": G.q(z)} for t, z in compress(out)], crossed


def _held_heights(net, legs: dict, gr, held, want: dict, runs: dict, node: dict,
                  fits) -> int:
    """M18 with M10: a junction its held roads all meet at one height other than its node's
    (the old build raised it, `level_legs`; the node comes back at M1b's height) takes
    theirs, its other legs brought up to it as a raise does. Returns how many."""
    if held is None:
        return 0
    n_set = 0
    for nid in sorted(legs):
        lg = legs[nid]
        hl = [x for x in lg if held(x.seg)]
        if not hl:
            continue
        ends = {G.q(_z_at(x.seg["z_profile"], 0.0 if x.at_start else G.q(x.L))) for x in hl}
        zn = node[nid]["position"][2]
        if len(ends) != 1 or abs(min(ends) - zn) <= 0.01:
            continue
        top = min(ends)
        new = {}
        for x in lg:
            if held(x.seg):
                continue
            s = x.seg
            L = G.q(x.L)
            near, far = (0.0, L) if x.at_start else (L, 0.0)
            if _fixed(s, None):
                if abs(_z_at(s["z_profile"], near) - top) > 0.01:
                    new = None
                    break
                continue
            k = (s["id"], x.at_start)
            r = want[k][1] if k in want else 0.0
            ro = runs.get((s["id"], not x.at_start), 0.0)
            g = catch_grade(s, gr)
            if x.at_start:
                prof, ra, rb = _levelled(s["z_profile"], L, r, ro, g, za=top)
            else:
                prof, ra, rb = _levelled(s["z_profile"], L, ro, r, g, zb=top)
            if not fits(s, prof, s["z_profile"]) or abs(_z_at(prof, near) - top) > 0.01 or \
                    abs(_z_at(prof, far) - _z_at(s["z_profile"], far)) > 0.01 or \
                    _steepest(prof) > g + 1e-4:
                new = None
                break
            new[k] = (prof, ra if x.at_start else rb)
        if new is None:
            continue
        for x in lg:
            k = (x.seg["id"], x.at_start)
            if k in new:
                x.seg["z_profile"], runs[k] = new[k]
        pos = node[nid]["position"]
        node[nid]["position"] = (pos[0], pos[1], top)
        n_set += 1
    return n_set


def _overhead(net):
    """A test whether a road passes over a node (another road's corridor over it, higher
    than z): raising the node would take its clearance."""
    pts = [[tuple(p) for p in s["centerline"]] for s in net.segments]
    tree = shapely.STRtree([LineString(p) for p in pts])

    def over(n, z: float) -> bool:
        xy = (n["position"][0], n["position"][1])
        for i in sorted(int(k) for k in tree.query(Point(xy), predicate="dwithin",
                                                   distance=40.0)):
            s = net.segments[i]
            if n["id"] in (s["start"], s["end"]):
                continue
            # (plain arithmetic: no measure GEOS rounds reaches M2)
            along, off = ST._project(pts[i], xy)[:2]
            if off > s["width_m"] / 2.0 + 3.0:
                continue
            if _z_at(s["z_profile"], along) > z - 0.5:
                return True
        return False
    return over


# ---------------------------------------------------------------------------
# M18: junction surfaces
# ---------------------------------------------------------------------------

FLAT_TOL_M = 0.005      # a junction with every vertex this near its node's height is flat
ON_CUT_M = 0.02         # a vertex this near a leg's cut line takes the leg's height


def leg_exit(pts, ring) -> tuple[float, int]:
    """Where a leg (its centerline from the node) first leaves a junction polygon's exterior
    ring: (distance along it, index of the ring edge it crosses), plain arithmetic on the
    grid points; its whole length and -1 where it never does."""
    from shapely import contains_xy
    from shapely.geometry import Polygon as _P

    poly = _P(ring)
    n = len(ring)
    acc = 0.0
    hits = []
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        seg = _dist(a, b)
        if seg <= 0.0:
            continue
        for k in range(n):
            c, d = ring[k], ring[(k + 1) % n]
            ex, ey = d[0] - c[0], d[1] - c[1]
            den = dx * ey - dy * ex
            if den == 0.0:
                continue
            t = ((c[0] - a[0]) * ey - (c[1] - a[1]) * ex) / den
            u = ((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / den
            if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= u <= 1.0 + 1e-9:
                hits.append((acc + t * seg, k))
        acc += seg
    for s, k in sorted(hits):
        if s <= 0.05:
            continue
        p, _ = ST._along(pts, min(s + 0.1, acc))
        if s + 0.1 >= acc or not bool(contains_xy(poly, p[0], p[1])):
            return s, k
    return acc, -1


def prof_at(prof, s: float) -> float:
    """A [(s, z)] profile at s (its ends beyond them)."""
    if not prof:
        return 0.0
    if s <= prof[0][0]:
        return prof[0][1]
    for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
        if s0 <= s <= s1:
            return z0 if s1 == s0 else z0 + (s - s0) / (s1 - s0) * (z1 - z0)
    return prof[-1][1]


def _cut_dist(p, E, nrm, h: float) -> float:
    """Distance from p to a leg's cut line: through E along nrm, h either side."""
    vx, vy = p[0] - E[0], p[1] - E[1]
    t = max(-h, min(h, vx * nrm[0] + vy * nrm[1]))
    return _dist((vx - t * nrm[0], vy - t * nrm[1]), (0.0, 0.0))


def anchors_of(ring, legs: list[dict]) -> tuple[list, list, list]:
    """The vertices a junction's legs fix (`surface`): per ring vertex the heights of the
    legs whose cut line it is on (or whose crossed ring edge it ends); the legs' exits
    [(leg index, s, ring edge, height)] and cut lines [(E, normal, h, height, ring edge)]."""
    exits = []
    cuts = []
    for i, lg in enumerate(legs):
        s, k = leg_exit(lg["pts"], ring)
        if lg.get("stairs"):
            continue
        z = lg["z"](s)
        E, t = ST._along(lg["pts"], s)
        exits.append((i, s, k, z))
        cuts.append((E, (-t[1], t[0]), lg["h"], z, k))
    n = len(ring)
    on: list[list[float]] = [[] for _ in range(n)]
    for E, nrm, h, z, k in cuts:
        for v in range(n):
            if _cut_dist(ring[v], E, nrm, h + 0.05) <= ON_CUT_M:
                on[v].append(z)
    for E, nrm, h, z, k in cuts:
        if k >= 0:
            for v in (k, (k + 1) % n):
                if not on[v]:
                    on[v].append(z)
    return on, exits, cuts


def surface(ring, legs: list[dict]) -> tuple[list[float], list[tuple]]:
    """M18: a junction's surface: the height of every exterior vertex. Each leg ({pts from
    the node, z: s -> its surface height, h: half width, stairs}) leaves the polygon at its
    exit (`leg_exit`); a vertex on its cut line there (square to the leg) or on the ring
    edge it crosses takes the leg's height there, so the surface meets every leg where it
    leaves, with no step; the curb lines between two legs' cut edges run evenly from one
    height to the other along the ring (the least slope there is). Stairs (footbridges)
    stand on the junction and shape nothing. Returns (heights, [(leg index, exit s, ring
    edge, height)])."""
    on, exits, cuts = anchors_of(ring, legs)
    n = len(ring)
    out = [sum(x) / len(x) if x else None for x in on]
    anchors = [v for v in range(n) if out[v] is not None]
    if anchors:
        # (the curbs between: linear in the length along the ring from anchor to anchor)
        cum = [0.0]
        for v in range(n):
            cum.append(cum[-1] + _dist(ring[v], ring[(v + 1) % n]))
        per = cum[-1]
        for i, a in enumerate(anchors):
            b = anchors[(i + 1) % len(anchors)]
            span = (cum[b] - cum[a]) % per if b != a else per
            v = (a + 1) % n
            while v != b:
                f = ((cum[v] - cum[a]) % per) / span if span > 0.0 else 0.0
                out[v] = out[a] + f * (out[b] - out[a])
                v = (v + 1) % n
    for v in range(n):
        if out[v] is not None:
            continue
        elif cuts:
            acc = wt = 0.0
            for E, nrm, h, z, k in cuts:
                w = 1.0 / (_cut_dist(ring[v], E, nrm, h) ** 2 + 1.0)
                acc += w * z
                wt += w
            out[v] = acc / wt
        else:
            out[v] = 0.0
    return [G.q(z) for z in out], exits


def model_legs(m_segments, node_id: str, ground_of=None) -> list[dict]:
    """The legs of a node for `surface`, from model rows (dicts or entities): their
    centerlines from the node, heights over the node's ground (z profile, and on a terrain
    city the grade line less `ground_of` the node), half widths, stairs."""
    out = []
    for s in m_segments:
        g = s if isinstance(s, dict) else s.model_dump()
        ends = [e for e in (True, False) if (g["start"] if e else g["end"]) == node_id]
        for at_start in ends:
            pts = [tuple(p[:2]) for p in g["centerline"]]
            L = ST._plen(pts)
            zp = [(p["s"], p["z"]) for p in g["z_profile"]]
            gp = [(p["s"], p["z"]) for p in g.get("ground") or []]
            base = ground_of or 0.0

            def z(s, zp=zp, gp=gp, L=L, a=at_start, base=base):
                t = s if a else L - s
                return prof_at(zp, t) + (prof_at(gp, t) - base if gp else 0.0)
            out.append({"pts": pts if at_start else pts[::-1], "z": z, "id": g["id"],
                        "h": g["width_m"] / 2.0, "stairs": g["road_class"] == "footbridge",
                        "cls": g["road_class"]})
    return out


def surfaces(segments: list[dict], nodes: list[dict], junctions: list[dict]) -> int:
    """M18: `edge_z` on every junction that is not flat at its node's height (rows, after
    the grading on a terrain city). Returns how many carry one."""
    at: dict = {}
    for s in segments:
        at.setdefault(s["start"], []).append(s)
        if s["end"] != s["start"]:
            at.setdefault(s["end"], []).append(s)
    node = {n["id"]: n for n in nodes}
    k = 0
    for j in junctions:
        j.pop("edge_z", None)
        n = node.get(j["node_id"])
        if n is None or j.get("polygon") is None:
            continue
        ring = [tuple(p) for p in j["polygon"]["exterior"]]
        legs = model_legs(at.get(j["node_id"], []), j["node_id"], n.get("ground_m"))
        hz, _ = surface(ring, legs)
        zn = n["position"][2]
        if any(abs(z - zn) > FLAT_TOL_M for z in hz):
            j["edge_z"] = hz
            k += 1
    return k


def _samples(s0: float, s1: float, L: float) -> list[float]:
    a, b = max(s0, 0.0), min(s1, L)
    if b < a:
        return []
    n = max(int(math.ceil((b - a) / LEVEL_STEP_M)), 1)
    return [a + (b - a) * k / n for k in range(n + 1)]


def one_way_stranded(net) -> list[str]:
    """M18: a two-way highway one of whose directions no lane can enter (at the node it
    starts from, every other road one-way away from it: a trumpet's stem between the
    flyover's landing and its near terminal where no near ramp arrives, now that the ramps
    are shorter) carries the other direction only. Returns the roads made one-way (start
    and end swapped where the direction kept runs end to start, so `one_way` runs start to
    end; a highway has no sidewalks to turn with it)."""
    at: dict = {}
    for s in net.segments:
        if s["road_class"] in ST.VEHICLE:
            at.setdefault(s["start"], []).append(s)
            at.setdefault(s["end"], []).append(s)

    def enters(nid: str, s) -> bool:
        others = [t for t in at.get(nid, []) if t is not s]
        if not others:
            return True       # (a dead end: U-turns)
        return any(not t.get("one_way") or t["end"] == nid for t in others)
    out = []
    for s in sorted(net.segments, key=lambda s: s["id"]):
        if s["road_class"] != "highway" or s.get("one_way") or s["start"] == s["end"]:
            continue
        fwd, bwd = enters(s["start"], s), enters(s["end"], s)
        if fwd == bwd:
            continue
        if bwd:
            # (the direction kept runs end to start)
            s["start"], s["end"] = s["end"], s["start"]
            s["centerline"] = s["centerline"][::-1]
            L = s["z_profile"][-1]["s"] if s["z_profile"] else 0.0
            s["z_profile"] = [{"s": G.q(L - p["s"]), "z": p["z"]}
                              for p in reversed(s["z_profile"])]
            if s["attrs"].get("cuts"):
                s["attrs"]["cuts"] = s["attrs"]["cuts"][::-1]     # (M22)
        s["one_way"] = True
        out.append(s["id"])
    return out


def _with_z(pts, base, prof, s0: float) -> list:
    if all(p["z"] == 0.0 for p in prof):
        return [(G.q(p[0]), G.q(p[1]), 0.0) for p in pts]
    out = []
    for p in pts:
        s = ST._project(base, p)[0]
        out.append((G.q(p[0]), G.q(p[1]), G.q(_z_at(prof, s))))
    return out


def _bezier(p0, t0, p3, t3, k: float, n: int = 6) -> list:
    c1 = (p0[0] + t0[0] * k, p0[1] + t0[1] * k)
    c2 = (p3[0] - t3[0] * k, p3[1] - t3[1] * k)
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
        out.append((G.q(a * p0[0] + b * c1[0] + c * c2[0] + d * p3[0]),
                    G.q(a * p0[1] + b * c1[1] + c * c2[1] + d * p3[1]), 0.0))
    dd = []
    for p in out:
        if not dd or p[:2] != dd[-1][:2]:
            dd.append(p)
    if len(dd) < 2:
        dd = [out[0], out[-1]]
    return dd


def build_lanes(net, legs: dict, cut: dict) -> list[dict]:
    """Driving lanes per road and connector lanes through every node."""
    lanes: list[dict] = []
    ins: dict[str, list] = {}   # node -> lanes arriving
    outs: dict[str, list] = {}  # node -> lanes leaving
    for s in net.segments:
        if s["road_class"] not in ST.VEHICLE:
            continue
        cs = s["cross_section"]
        pts = [tuple(p) for p in s["centerline"]]
        L = ST._plen(pts)
        a = cut.get((s["id"], s["start"]), 0.0)
        b = cut.get((s["id"], s["end"]), 0.0)
        if a + b > 0.9 * L:
            f = 0.9 * L / (a + b)
            a, b = a * f, b * f
        base = ST._substring(pts, a, L - b) if L - b - a > 2.0 else pts
        lw = cs["lane_width_m"]
        med = cs.get("median_m", 0.0)
        shared = cs.get("shared") or s["road_class"] == "alley"
        specs = []
        if shared:
            specs = [(True, 0, 0.0), (False, 0, 0.0)]
        elif s.get("one_way") and cs["lanes_backward"] == 0:
            # M7 ramps: one-way lanes centered on the road
            n_f = cs["lanes_forward"]
            for i in range(n_f):
                specs.append((True, i, (n_f / 2 - (i + 0.5)) * lw))
        else:
            for i in range(cs["lanes_forward"]):
                specs.append((True, i, -(med / 2 + (i + 0.5) * lw)))
            if not s.get("one_way"):
                for i in range(cs["lanes_backward"]):
                    specs.append((False, i, med / 2 + (i + 0.5) * lw))
        made: dict = {}
        for fwd, i, off in specs:
            line = _offset(base, off)
            if len(line) < 2:
                line = _offset(pts, off)
            if len(line) < 2:
                line = [tuple(p) for p in base]  # a stub too short to offset
            if not fwd:
                line = line[::-1]
            lid = f"ln{len(lanes) + 1:06d}"
            n_dir = cs["lanes_forward"] if fwd else cs["lanes_backward"]
            rec = {"id": lid, "kind": "lane", "segment_id": s["id"], "junction_id": None,
                   "index": i, "forward": fwd, "centerline": _with_z(line, pts, s["z_profile"],
                                                                     0.0),
                   "width_m": lw, "successors": [],
                   "attrs": {"lanes_in_direction": 1 if shared else n_dir}}
            if shared:
                rec["attrs"]["shared"] = True
            lanes.append(rec)
            made[(fwd, i)] = rec
            prev = made.get((fwd, i - 1))
            if prev is not None:
                prev.setdefault("adjacent_ids", []).append(lid)
                rec.setdefault("adjacent_ids", []).append(prev["id"])
            end_node = s["end"] if fwd else s["start"]
            start_node = s["start"] if fwd else s["end"]
            ins.setdefault(end_node, []).append(rec)
            outs.setdefault(start_node, []).append(rec)
    conn: list[dict] = []
    for node in sorted(set(ins) | set(outs)):
        li, lo = ins.get(node, []), outs.get(node, [])
        segs_here = {r["segment_id"] for r in li + lo}
        dead = len(segs_here) == 1
        pairs = []
        for a in li:
            pa = a["centerline"]
            ta = _unit(pa[-1][0] - pa[-2][0], pa[-1][1] - pa[-2][1])
            for b in lo:
                if b["segment_id"] == a["segment_id"] and not dead:
                    continue
                pb = b["centerline"]
                tb = _unit(pb[1][0] - pb[0][0], pb[1][1] - pb[0][1])
                turn = M.degrees(M.atan2(ta[0] * tb[1] - ta[1] * tb[0],
                                         ta[0] * tb[0] + ta[1] * tb[1]))
                pairs.append((a, b, turn, ta, tb))
        chosen = []
        for a, b, turn, ta, tb in pairs:
            na = a["attrs"]["lanes_in_direction"]
            nb = b["attrs"]["lanes_in_direction"]
            if dead and b["segment_id"] == a["segment_id"]:
                ok = a["index"] == b["index"] or nb == 1
            elif abs(turn) > 160.0:
                ok = False
            elif abs(turn) <= TURN_STRAIGHT_DEG:
                ok = b["index"] == min(a["index"], nb - 1)
            elif turn > 0:
                ok = a["index"] == 0 and b["index"] == 0
            else:
                ok = a["index"] == na - 1 and b["index"] == nb - 1
            if ok:
                chosen.append((a, b, turn, ta, tb))
        # every lane keeps a way on and a way in
        have_out = {id(c[0]) for c in chosen}
        have_in = {id(c[1]) for c in chosen}
        for a in li:
            if id(a) not in have_out:
                cand = [p for p in pairs if p[0] is a and abs(p[2]) <= 160.0] or \
                    [p for p in pairs if p[0] is a]
                if cand:
                    chosen.append(min(cand, key=lambda p: (abs(p[2]), p[1]["id"])))
        have_in = {id(c[1]) for c in chosen}
        for b in lo:
            if id(b) not in have_in:
                cand = [p for p in pairs if p[1] is b and abs(p[2]) <= 160.0] or \
                    [p for p in pairs if p[1] is b]
                if cand:
                    chosen.append(min(cand, key=lambda p: (abs(p[2]), p[0]["id"])))
        seen = set()
        for a, b, turn, ta, tb in chosen:
            key = (a["id"], b["id"])
            if key in seen:
                continue
            seen.add(key)
            p0, p3 = a["centerline"][-1], b["centerline"][0]
            gap = _dist(p0, p3)
            uturn = a["segment_id"] == b["segment_id"]
            k = max(gap * (1.2 if uturn else 0.4), 2.0)
            cid = f"lc{len(conn) + 1:06d}"
            kind_turn = "u_turn" if uturn else ("straight" if abs(turn) <= TURN_STRAIGHT_DEG
                                                else ("left" if turn > 0 else "right"))
            line = _bezier(p0[:2], ta, p3[:2], tb, k)
            conn.append({"id": cid, "kind": "connector", "segment_id": None,
                         "junction_id": node, "index": 0, "forward": True,
                         "centerline": line, "width_m": a["width_m"], "successors": [b["id"]],
                         "attrs": {"turn": kind_turn, "from": a["id"]}})
            a["successors"].append(cid)
    for r in lanes:
        r["successors"] = sorted(r["successors"])
        r["adjacent_ids"] = sorted(r.get("adjacent_ids", []))
        r["attrs"].pop("lanes_in_direction", None)
    return lanes + conn


# ---------------------------------------------------------------------------
# Walkways
# ---------------------------------------------------------------------------

class WalkGraph:
    def __init__(self):
        self.nodes: dict[tuple, str] = {}
        self.edges: list[dict] = []

    def node(self, p) -> str:
        p = _pt(*p[:2])
        if p not in self.nodes:
            self.nodes[p] = p
        return p

    def add(self, kind: str, pts, width: float, z: float = 0.0, **attrs) -> None:
        pts = ST._dedupe(pts)
        if len(pts) < 2:
            return
        self.edges.append({"kind": kind, "pts": pts, "width": width, "z": z, "attrs": attrs})


def _walk_offset(x: Leg) -> float:
    """How far from a leg's centerline its walkers go: the sidewalk's middle, or 1 m inside
    the edge of a road with no sidewalk (a path's, an alley's)."""
    return x.h + x.sw / 2 if x.sw > 0 else max(x.h - 1.0, x.h / 2)


def _corner_point(P, a: Leg, b: Leg, jrow=None):
    """Where the sidewalks of two neighboring legs meet (sidewalk centers), b
    counterclockwise from a. Park paths fix: where the two sidewalk lines cross when the gap
    between the legs is under 180 degrees (the corner of the sidewalks, always on the right
    of way), else on the gap's bisector at the sidewalks' offset (inside the junction's
    polygon). The middle of the two sidewalk points at the cuts, which it was, lies in the
    block's corner once the cuts are longer than the right of way is wide (a street with no
    sidewalk, M17's long cuts), and walkers went through the corner building. `jrow`: the
    junction's right of way taken in by ROW_IN_M (prepared), where there is a junction."""
    oa = _walk_offset(a)
    ob = _walk_offset(b)
    na, nb = _left(a.d), _left(b.d)
    pa = (P[0] + a.cut * a.d[0] + oa * na[0], P[1] + a.cut * a.d[1] + oa * na[1])
    pb = (P[0] + b.cut * b.d[0] - ob * nb[0], P[1] + b.cut * b.d[1] - ob * nb[1])
    mid = _pt((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
    ux, uy = na[0] - nb[0], na[1] - nb[1]
    s2 = math.sqrt(ux * ux + uy * uy) / 2        # sin of half the gap
    if s2 < 1e-6:
        return _on_row(P, mid, a, b, jrow), _pt(*pa), _pt(*pb)   # (on one line)
    ux, uy = ux / (2 * s2), uy / (2 * s2)       # the gap's bisector
    cross = a.d[0] * b.d[1] - a.d[1] * b.d[0]
    dot = a.d[0] * b.d[0] + a.d[1] * b.d[1]
    if cross > 0.05 or (cross > 0.0 and dot > 0.0):
        # under 180 degrees (less a few): the two sidewalk lines' crossing, t along a and s
        # along b from P: P + oa na + t da = P - ob nb + s db
        rx, ry = -ob * nb[0] - oa * na[0], -ob * nb[1] - oa * na[1]
        t = (rx * b.d[1] - ry * b.d[0]) / cross
        s = (rx * a.d[1] - ry * a.d[0]) / cross
        if -1e-6 <= t <= max(a.cut, oa) + oa and -1e-6 <= s <= max(b.cut, ob) + ob and \
                t <= a.L and s <= b.L:
            X = (P[0] + oa * na[0] + t * a.d[0], P[1] + oa * na[1] + t * a.d[1])
        else:
            X = mid                               # (a sharp fork: pa and pb lie close)
    else:
        o = (oa + ob) / 2
        X = (P[0] + o * ux, P[1] + o * uy)
    return _on_row(P, X, a, b, jrow), _pt(*pa), _pt(*pb)


ROW_IN_M = 0.25     # a sidewalk corner keeps this far inside the right of way


def _on_strip(x: Leg, q) -> bool:
    """q on leg x's right of way (the flat-capped strip along its centerline as it runs, not
    along its direction at the node: a leg that curves leaves that line), ROW_IN_M inside."""
    s, d, _, _ = ST._project(x.pts, q)
    return 1e-6 < s < x.L - 1e-6 and d <= x.row - ROW_IN_M


def _on_row(P, X, a: Leg, b: Leg, jrow=None):
    """X, or the point nearest it toward the node that lies on the right of way of leg a or
    b or of the junction (`jrow`)."""
    for lam in (1.0, 0.85, 0.7, 0.55, 0.4, 0.25, 0.1):
        q = _pt(P[0] + lam * (X[0] - P[0]), P[1] + lam * (X[1] - P[1]))
        if _on_strip(a, q) or _on_strip(b, q) or (jrow is not None and
                                                  jrow.contains(Point(q))):
            return q
    return _pt(*P)


def _jrow(lg: list):
    """The right of way of the junction at a node (taken in by ROW_IN_M, prepared), or None
    where there is none (a node of two legs with no cut)."""
    n = len(lg)
    if n < 2 or (n == 2 and not any(x.cut > 0.0 for x in lg)):
        return None
    g = junction_polygon(lg, row=True)
    if g.is_empty:
        return None
    g = G.qpoly(g.buffer(-ROW_IN_M, join_style="mitre"))
    if g.is_empty:
        return None
    shapely.prepare(g)
    return g


def build(net, district_arch: dict, did_by_name: dict, seed: int, gr=None,
          control: dict | None = None) -> dict:
    """Junctions, sidewalks, crosswalks, lanes and walkways for a street network (`gr`, the
    spec's `highways.grades`: M18 levels the legs of every junction, `level_legs`;
    `control`, district id -> its `junctions` (signals, crosswalks): M18's crossings by
    need, `plan_signals`)."""
    n_oneway = one_way_loops(net, district_arch, seed)
    T.detail("junctions/one_way", sorted(s["id"] for s in net.segments if s.get("one_way")))
    pos = {n["id"]: tuple(n["position"][:2]) for n in net.nodes}
    heads = {n["id"]: n["attrs"].get("turning_head_m", 0.0) for n in net.nodes}

    def arch_of(s):
        d = s["attrs"].get("district")
        if d:
            return district_arch.get(d)
        ids = s.get("district_ids") or []
        return district_arch.get(ids[0]) if ids else None

    def did_of(s):
        d = s["attrs"].get("district")
        if d:
            return d
        ids = s.get("district_ids") or []
        return ids[0] if ids else None

    legs = legs_at(net, arch_of)
    node_arch = {}
    node_ctl = {}
    for nid, lg in legs.items():
        archs = sorted(a for a in (x.arch for x in lg) if a)
        node_arch[nid] = archs[0] if archs else None
        dids = sorted(d for d in (did_of(x.seg) for x in lg) if d)
        node_ctl[nid] = (control or {}).get(dids[0], ("auto", "auto")) if dids else \
            ("auto", "auto")
    cut: dict = {}
    cut_row: dict = {}
    junctions, crosswalks, sidewalks = [], [], []
    # M14: one walk graph per level (a deck's corners lie over the ground's)
    Ws = {0: WalkGraph()}
    nlev = {n["id"]: DK.walk_level(n) for n in net.nodes}
    corner_of: dict = {}   # (node, seg id, side) -> walk node
    # (M13's grade lines hold each junction's height out to M17's cut on its legs, as before
    # M22: out to M22's, longer, a hillside's short streets go flat; `local.py`)
    legs17 = legs_at(net, arch_of)
    for nid in sorted(legs17):
        cutbacks(legs17[nid], cap=False)
    share_cuts(legs17)
    runs17 = {(x.seg["id"], nid): run_along(x, max(x.cut, x.cut_row))
              for nid, lg in legs17.items() for x in lg
              if len(lg) >= 3 or (len(lg) == 2 and any(y.cut > 0.0 for y in lg))}
    for nid in sorted(legs):
        cutbacks(legs[nid], cap=False, one=True)
    # M22: the junctions as regions of the pavement map, one cut per leg (where its bands,
    # sidewalks, crosswalks and lanes end); a road whose two cuts meet joins its junctions
    fold_cuts(net, legs)
    lock_cuts(net, legs)
    fold_cuts(net, legs)        # (a lock's cut can land in a fold)
    units = plan_units(net, legs, heads, gr)
    inner = {sid for u in units for sid in u["inner"]}
    unit_of = {n: k for k, u in enumerate(units) for n in u["nodes"]}
    pvu = []
    for k, u in enumerate(units):
        u["id"] = f"jn{k + 1:05d}"
        ext = [x for n in u["nodes"] for x in legs[n] if x.seg["id"] not in inner]
        pvu.append(PV.Unit(u["id"], u["nodes"], ext, u["inner"], u["head"], PV.unit_layer(ext),
                           {n: legs[n] for n in u["nodes"]}, heads=u["heads"]))
    plan = PV.Plan(net.segments, pos, pvu)
    jrows = {}
    for u in units:
        _, R = plan.regions[u["id"]]
        g = G.qpoly(R.buffer(-ROW_IN_M, join_style="mitre")) if not R.is_empty else R
        if not g.is_empty:
            shapely.prepare(g)
            jrows[u["id"]] = g
    cutx = {(x.seg["id"], x.at_start): x.cut for lg in legs.values() for x in lg}
    signals, _ = plan_signals(legs, node_arch, lambda nid: node_ctl[nid])
    av_marked = plan_crossings(legs, node_arch, lambda nid: node_ctl[nid], signals)
    for nid in sorted(legs):
        lg = legs[nid]
        P = pos[nid]
        W = Ws.setdefault(nlev.get(nid, 0), WalkGraph())
        for x in lg:
            cut[(x.seg["id"], nid)] = x.cut
            cut_row[(x.seg["id"], nid)] = x.cut_row
        n = len(lg)
        if n == 1:
            x = lg[0]
            q = W.node(P)
            corner_of[(nid, x.seg["id"], "L")] = q
            corner_of[(nid, x.seg["id"], "R")] = q
            continue
        # corners between neighbors (sidewalk center points)
        k = unit_of.get(nid)
        jrow = jrows.get(units[k]["id"]) if k is not None else None
        for i in range(n):
            a, b = lg[i], lg[(i + 1) % n]
            c, _, _ = _corner_point(P, a, b, jrow)
            q = W.node(c)
            corner_of[(nid, a.seg["id"], "L" if a.at_start else "R")] = q
            corner_of[(nid, b.seg["id"], "R" if b.at_start else "L")] = q
    for u in units:
        jid, nodes = u["id"], u["nodes"]
        C, R = plan.regions[jid]
        poly = max(PV.polys(C), key=lambda p: (p.area, p.bounds), default=Polygon())
        if poly.is_empty:
            poly = G.qpoly(Point(pos[nodes[0]]).buffer(1.0))
        nid0 = nodes[0]
        if u["head"]:
            # (M17: a cul-de-sac or a quay end with room for its turning bulb)
            cls = ST.street_class(legs[nid0][0].seg)
            junctions.append({"id": jid, "node_id": nid0, "polygon": poly,
                              "signalized": False, "crosswalk_ids": [], "row_polygon": R,
                              "attrs": {"type": cls, "shape": "cul_de_sac", "legs": 1,
                                        "corner_radius_m": heads[nid0],
                                        "archetype": node_arch[nid0], "classes": [cls]}})
            continue
        allg = [x for nd in nodes for x in legs[nd]]
        ext = [x for x in allg if x.seg["id"] not in inner]
        kind, shape, _ = classify(ext or allg, node_arch[nid0])
        if len(nodes) > 1:
            shape = "multi"
        sig = any(nd in signals for nd in nodes)
        xw_ids = []
        jrow = jrows.get(jid)
        walkable = any(x.cls != "highway" for x in allg)
        for nd in nodes:
            lg = legs[nd]
            n = len(lg)
            P = pos[nd]
            W = Ws.setdefault(nlev.get(nd, 0), WalkGraph())
            xws = node_ctl[nd][1]
            # M18: crosswalks on the approaches of signalized junctions; at an unsignalized
            # one, across its avenue where no signalized junction or marked crossing is
            # within the district's spacing along it; elsewhere unmarked crossings. M22: on
            # the road's face between its cuts (none on a road inside a cluster; unmarked
            # where the road's face is too short for it)
            av = nd in av_marked
            for i, x in enumerate(lg if walkable else []):
                if x.cls in ST.PEDESTRIAN or x.seg["id"] in inner:
                    continue
                if x.cls == "highway" and not sig:
                    continue
                far = cutx.get((x.seg["id"], not x.at_start), 0.0)
                xw = crosswalk_w(x.cls, node_arch[nid0])
                marked = xw > 0.0 and xws != "none" and (sig or (av and x.cls == "avenue"))
                s = x.cut + CROSSWALK_SETBACK_M + (xw / 2 if marked else 2.0)
                if marked and s + xw / 2 > x.L - far - XWALK_PAD_M:
                    # (no room on the road's face between its cuts: on the junction's face,
                    # inside its port)
                    s = max(x.cut - xw / 2 - XWALK_PAD_M, xw / 2)
                s = min(s, max(x.L - far - 0.5, x.cut), 0.95 * x.L)
                p, t = ST._along(x.pts, s)
                nrm = _left(t)
                a_ = _pt(p[0] - nrm[0] * x.h, p[1] - nrm[1] * x.h)
                b_ = _pt(p[0] + nrm[0] * x.h, p[1] + nrm[1] * x.h)
                prev = lg[i - 1]
                nxt = lg[(i + 1) % n]
                right_corner = W.node(_corner_point(P, prev, x, jrow)[0])
                left_corner = W.node(_corner_point(P, x, nxt, jrow)[0])
                if marked:
                    cid = f"cw{len(crosswalks) + 1:05d}"
                    xa = {"road_class": x.cls}
                    if len(nodes) > 1:
                        xa["node"] = nd
                    crosswalks.append({"id": cid, "junction_id": jid,
                                       "segment_id": x.seg["id"], "line": [a_, b_],
                                       "width_m": xw, "signalized": sig,
                                       "attrs": xa})
                    xw_ids.append(cid)
                W.add("crosswalk" if marked else "crossing",
                      [right_corner, a_, b_, left_corner], xw if marked else 2.0,
                      junction=jid, crosswalk=marked)
        attrs = {"type": kind, "shape": shape, "legs": len(ext),
                 "corner_radius_m": min(x.r for x in allg), "archetype": node_arch[nid0],
                 "classes": sorted({x.cls for x in ext or allg},
                                   key=lambda c: (-ST.RANK[c], c))}
        if len(nodes) > 1:
            attrs["nodes"] = list(nodes)
            attrs["inner"] = list(u["inner"])
            attrs["signals"] = [nd for nd in nodes if nd in signals]
            if u["heads"]:
                attrs["bulbs"] = sorted(u["heads"])
        junctions.append({"id": jid, "node_id": nid0, "polygon": poly, "signalized": sig,
                          "crosswalk_ids": xw_ids, "row_polygon": R, "attrs": attrs})
    # M18: the legs of every junction held level out past where they leave its polygon (the
    # lanes take their heights)
    exits = {}
    for j in junctions:
        if j["polygon"].is_empty or j["polygon"].geom_type != "Polygon":
            continue
        ring = G._ring(j["polygon"].exterior.coords)
        for x in legs.get(j["node_id"], []):
            exits[(x.seg["id"], x.at_start)] = leg_exit(x.pts, ring)[0]
    fr = getattr(getattr(net, "builder", None), "frame", None)
    held = None if fr is None else (lambda s: fr.match(s["centerline"], s) is not None)
    lev = level_legs(net, legs, gr, held, exits)
    # M22: a junction whose ports one surface cannot carry is levelled further; one that
    # stays so, held by what the levelling may not move, says so
    lev.update(buildable(net, units, legs, gr, held, plan, lev))
    first_of = {u["nodes"][0]: u["id"] for u in units}
    for j in junctions:
        why = lev.get("held", {}).get(j["node_id"])
        if why and j["node_id"] in first_of and j["node_id"] in set(lev.get("unresolved", [])):
            j["attrs"]["unbuildable"] = why
    # sidewalks and centerline walkways
    for s in net.segments:
        if s["attrs"].get("role") == "deck_ramp":
            continue      # (M14: a deck ramp carries no walkway; stairs join the levels)
        W = Ws.setdefault(DK.walk_level(s), WalkGraph())
        cls = ST.street_class(s)
        pts = [tuple(p) for p in s["centerline"]]
        L = ST._plen(pts)
        a = cut.get((s["id"], s["start"]), 0.0)
        b = cut.get((s["id"], s["end"]), 0.0)
        cs = s["cross_section"]
        side = cs["sidewalk_m"][0] if cs.get("sidewalk_m") else 0.0
        if cls in ("avenue", "street") and side > 0:
            h = s["width_m"] / 2 - side / 2
            curb = min(cs.get("curb_m", 0.15), side)
            furn = min(max(cs.get("furniture_m", 1.5 if cls == "avenue" else 0.0), 0.0),
                       side - curb)
            rd = plan.roads.get(s["id"])
            # (M22: the sidewalk's middle from port to port, square to the road at its ends
            # as its right of way ends: the map's mitred frame where a road goes on as
            # another reaches past it, into the lots there; a road inside a cluster, whose
            # sidewalks are its junction's corner pads, end to end, as stations' stairs and
            # the props find sidewalks by their records)
            L = ST._plen(pts)
            ra, rb = (0.0, 0.0) if s["id"] in inner or rd is None else (rd.a, rd.b)
            base = ST._substring(pts, ra, L - rb) if L - ra - rb > 1.0 else pts
            for sd, sign in (("L", 1.0), ("R", -1.0)):
                line = _offset(base, sign * h)
                if len(line) < 2:
                    continue
                sid = f"sw{len(sidewalks) + 1:06d}"
                sidewalks.append({"id": sid, "segment_id": s["id"], "side":
                                  "left" if sd == "L" else "right",
                                  "line": line, "width_m": side,
                                  "clear_path_m": G.q(side - furn - curb), "curb_m": curb,
                                  "furniture_m": furn})
                c0 = corner_of.get((s["start"], s["id"], sd))
                c1 = corner_of.get((s["end"], s["id"], sd))
                chain = ([c0] if c0 else []) + line + ([c1] if c1 else [])
                W.add("sidewalk", chain, side, sidewalk=sid, segment=s["id"])
        elif cls != "highway":
            kind = {"pedestrian": "pedestrian_street", "footbridge": "footbridge"}.get(
                cls, "alley" if cls in ("alley", "service") else "path")
            if s["attrs"].get("role") == "promenade":
                kind = "promenade"
            z = max((p["z"] for p in s["z_profile"]), default=0.0)
            W.add(kind, pts, s["width_m"] if cls != "service" else 2.0, z=z, segment=s["id"])
            # link the centerline ends to the corners on both sides of this leg
            for end, nid in ((pts[0], s["start"]), (pts[-1], s["end"])):
                for sd in ("L", "R"):
                    c = corner_of.get((nid, s["id"], sd))
                    if c is not None and c != _pt(*end):
                        W.add("path", [end, c], 2.0)
    # M22: each road's cuts (at its start and end) in the model, so the pavement map can be
    # made again from the rows (`pavement.units_from_rows`)
    for s in net.segments:
        a, b = cutx.get((s["id"], True), 0.0), cutx.get((s["id"], False), 0.0)
        if s["road_class"] != "footbridge" and (a or b):
            s["attrs"]["cuts"] = [a, b]
    stranded = one_way_stranded(net)
    T.detail("junctions/stranded", stranded)
    lanes = build_lanes(net, legs, cut)
    T.detail("junctions/polygons", [j["polygon"] for j in junctions])
    T.detail("junctions/lanes", [(r["id"], r["centerline"], r["successors"]) for r in lanes])
    return {"junctions": junctions, "crosswalks": crosswalks, "sidewalks": sidewalks,
            "lanes": lanes, "walk": Ws[0], "walk_levels": {k: v for k, v in Ws.items() if k},
            "corners": corner_of, "cut": cut, "cut_row": cut_row, "one_way": n_oneway,
            "legs": legs, "level": lev, "exits": exits, "units": units, "runs17": runs17}


def walkways(W: WalkGraph) -> list[dict]:
    """Walkway records with neighbors (sharing an end point)."""
    recs = []
    at: dict = {}
    for k, e in enumerate(W.edges):
        wid = f"wk{k + 1:06d}"
        a, b = e["pts"][0], e["pts"][-1]
        at.setdefault(a, []).append(wid)
        at.setdefault(b, []).append(wid)
        recs.append((wid, e, a, b))
    out = []
    for wid, e, a, b in recs:
        nb = sorted(set(at[a] + at[b]) - {wid})
        out.append({"id": wid, "kind": e["kind"],
                    "line": [(x, y, e["z"]) for x, y in e["pts"]],
                    "width_m": e["width"], "neighbors": nb,
                    "attrs": {k: v for k, v in e["attrs"].items() if v is not None}})
    return out


def walk_components(edges: list[tuple]) -> dict:
    """Union-find root of every walk node (edges as (a, b) end points)."""
    parent: dict = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)
    return {x: find(x) for x in list(parent)}
