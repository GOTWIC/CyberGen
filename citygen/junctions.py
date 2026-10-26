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

import shapely
from shapely.geometry import LineString, Point, Polygon

from . import dmath as M
from . import geom as G
from . import streets as ST
from . import trace as T

CORNER_R = {"highway": 15.0, "avenue": 12.0, "service": 6.0, "alley": 3.0, "pedestrian": 1.0,
            "footbridge": 1.0}
ROW_CORNER_MIN_M = 1.0
CORNER_RUN_MAX_M = 60.0      # longest corner (fillet or sharp) along a leg
CROSSWALK_W = 4.0
CROSSWALK_SETBACK_M = 1.5
SIGNAL_STREET_ARCH = ("corporate_core", "transit_hub", "midtown_mixed")
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


def cutbacks(legs: list[Leg]) -> None:
    n = len(legs)
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
        rr = max(r - max(a.sw, b.sw), ROW_CORNER_MIN_M)
        c2 = _corner(P, a, b, a.row, b.row, rr)
        if c2 is not None:
            a.cut_row = max(a.cut_row, c2[0])
            b.cut_row = max(b.cut_row, c2[1])
    for lg in legs:
        lg.cut = min(lg.cut + 1.0, 0.45 * lg.L)
        lg.cut_row = min(lg.cut_row + 0.5, 0.45 * lg.L)


def junction_polygon(legs: list[Leg], row: bool = False) -> Polygon:
    n = len(legs)
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
    return G.qpoly(shapely.make_valid(Polygon(pts)))


def classify(legs: list[Leg], arch: str | None) -> tuple[str, str, bool]:
    veh = sorted([lg.cls for lg in legs if lg.cls in ST.VEHICLE],
                 key=lambda c: -ST.RANK[c])
    n = len(legs)
    shape = {1: "dead_end", 2: "bend", 3: "T", 4: "X"}.get(n, "multi")
    if not veh:
        return "pedestrian", shape, False
    kind = veh[0] if len(veh) == 1 else f"{veh[0]}_{veh[1]}"
    sig = False
    if all(lg.cls == "highway" for lg in legs):
        return kind, shape, False  # an interchange in M7: no signals, no pedestrians
    if len(veh) >= 3:
        if veh[1] in ("highway", "avenue"):
            sig = True
        elif veh[0] in ("highway", "avenue") and veh[1] == "street" and len(veh) >= 4:
            sig = True
        elif veh[0] == "street" and veh[1] == "street" and len(veh) >= 4 and \
                arch in SIGNAL_STREET_ARCH:
            sig = True
    return kind, shape, sig


# ---------------------------------------------------------------------------
# One-way loops
# ---------------------------------------------------------------------------

def one_way_loops(net, district_arch: dict, seed: int) -> int:
    """Turn some block faces bounded only by narrow organic streets into one-way loops."""
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
            if len(set(ids)) != len(ids) or any(i in chosen for i in ids):
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
                s["one_way"] = True
                s["cross_section"] = cs_
                s["lanes"] = cs_["lanes_forward"] + cs_["lanes_backward"]
                chosen.add(sid_)
            count += 1
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


def _corner_point(P, a: Leg, b: Leg):
    """Where the sidewalks of two neighboring legs meet (sidewalk centers)."""
    oa = a.h + a.sw / 2
    ob = b.h + b.sw / 2
    na, nb = _left(a.d), _left(b.d)
    pa = (P[0] + a.cut * a.d[0] + oa * na[0], P[1] + a.cut * a.d[1] + oa * na[1])
    pb = (P[0] + b.cut * b.d[0] - ob * nb[0], P[1] + b.cut * b.d[1] - ob * nb[1])
    return _pt((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2), _pt(*pa), _pt(*pb)


def build(net, district_arch: dict, did_by_name: dict, seed: int) -> dict:
    """Junctions, sidewalks, crosswalks, lanes and walkways for a street network."""
    n_oneway = one_way_loops(net, district_arch, seed)
    T.detail("junctions/one_way", sorted(s["id"] for s in net.segments if s.get("one_way")))
    pos = {n["id"]: tuple(n["position"][:2]) for n in net.nodes}

    def arch_of(s):
        d = s["attrs"].get("district")
        if d:
            return district_arch.get(d)
        ids = s.get("district_ids") or []
        return district_arch.get(ids[0]) if ids else None

    legs = legs_at(net, arch_of)
    node_arch = {}
    for nid, lg in legs.items():
        archs = sorted(a for a in (x.arch for x in lg) if a)
        node_arch[nid] = archs[0] if archs else None
    cut: dict = {}
    cut_row: dict = {}
    junctions, crosswalks, sidewalks = [], [], []
    turnarounds = []
    W = WalkGraph()
    corner_of: dict = {}   # (node, seg id, side) -> walk node
    for nid in sorted(legs):
        lg = legs[nid]
        P = pos[nid]
        cutbacks(lg)
        for x in lg:
            cut[(x.seg["id"], nid)] = x.cut
            cut_row[(x.seg["id"], nid)] = x.cut_row
        n = len(lg)
        if n == 1:
            x = lg[0]
            q = W.node(P)
            corner_of[(nid, x.seg["id"], "L")] = q
            corner_of[(nid, x.seg["id"], "R")] = q
            if x.seg["attrs"].get("role") == "cul_de_sac":
                r = 12.0
                ring = [(P[0] + r * M.cos(a), P[1] + r * M.sin(a))
                        for a in [k * 2 * M.PI / 24 for k in range(24)]]
                turnarounds.append((nid, G.qpoly(Polygon(ring))))
            continue
        # corners between neighbors (sidewalk center points)
        for i in range(n):
            a, b = lg[i], lg[(i + 1) % n]
            c, _, _ = _corner_point(P, a, b)
            q = W.node(c)
            corner_of[(nid, a.seg["id"], "L" if a.at_start else "R")] = q
            corner_of[(nid, b.seg["id"], "R" if b.at_start else "L")] = q
        if n < 3:
            continue
        kind, shape, sig = classify(lg, node_arch[nid])
        jid = f"jn{len(junctions) + 1:05d}"
        poly = junction_polygon(lg)
        row_poly = junction_polygon(lg, row=True)
        has_avenue = any(x.cls == "avenue" for x in lg)
        xw_ids = []
        walkable = any(x.cls != "highway" for x in lg)
        for i, x in enumerate(lg if walkable else []):
            if x.cls in ST.PEDESTRIAN:
                continue
            marked = sig or (has_avenue and x.cls not in ("avenue", "highway"))
            if x.cls == "highway" and not sig:
                continue
            s = x.cut + CROSSWALK_SETBACK_M + CROSSWALK_W / 2
            s = min(s, 0.45 * x.L)
            p, t = ST._along(x.pts, s)
            nrm = _left(t)
            a_ = _pt(p[0] - nrm[0] * x.h, p[1] - nrm[1] * x.h)
            b_ = _pt(p[0] + nrm[0] * x.h, p[1] + nrm[1] * x.h)
            prev = lg[i - 1]
            nxt = lg[(i + 1) % n]
            right_corner = W.node(_corner_point(P, prev, x)[0])
            left_corner = W.node(_corner_point(P, x, nxt)[0])
            if marked:
                cid = f"cw{len(crosswalks) + 1:05d}"
                crosswalks.append({"id": cid, "junction_id": jid, "segment_id": x.seg["id"],
                                   "line": [a_, b_], "width_m": CROSSWALK_W,
                                   "signalized": sig, "attrs": {"road_class": x.cls}})
                xw_ids.append(cid)
            W.add("crosswalk" if marked else "crossing",
                  [right_corner, a_, b_, left_corner], CROSSWALK_W if marked else 2.0,
                  junction=jid, crosswalk=marked)
        junctions.append({"id": jid, "node_id": nid, "polygon": poly, "signalized": sig,
                          "crosswalk_ids": xw_ids, "row_polygon": row_poly,
                          "attrs": {"type": kind, "shape": shape, "legs": n,
                                    "corner_radius_m": min(x.r for x in lg),
                                    "archetype": node_arch[nid],
                                    "classes": sorted({x.cls for x in lg},
                                                      key=lambda c: (-ST.RANK[c], c))}})
    for nid, poly in turnarounds:
        junctions.append({"id": f"jn{len(junctions) + 1:05d}", "node_id": nid, "polygon": poly,
                          "signalized": False, "crosswalk_ids": [], "row_polygon": poly,
                          "attrs": {"type": "street", "shape": "cul_de_sac", "legs": 1,
                                    "corner_radius_m": 12.0,
                                    "archetype": node_arch[nid], "classes": ["street"]}})
    # sidewalks and centerline walkways
    for s in net.segments:
        cls = ST.street_class(s)
        pts = [tuple(p) for p in s["centerline"]]
        L = ST._plen(pts)
        a = cut.get((s["id"], s["start"]), 0.0)
        b = cut.get((s["id"], s["end"]), 0.0)
        cs = s["cross_section"]
        side = cs["sidewalk_m"][0] if cs.get("sidewalk_m") else 0.0
        if cls in ("avenue", "street") and side > 0:
            base = ST._substring(pts, a, L - b) if L - a - b > 1.0 else pts
            h = s["width_m"] / 2 - side / 2
            furn = cs.get("furniture_m", 1.5 if cls == "avenue" else 0.0)
            curb = cs.get("curb_m", 0.15)
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
    lanes = build_lanes(net, legs, cut)
    T.detail("junctions/polygons", [j["polygon"] for j in junctions])
    T.detail("junctions/lanes", [(r["id"], r["centerline"], r["successors"]) for r in lanes])
    return {"junctions": junctions, "crosswalks": crosswalks, "sidewalks": sidewalks,
            "lanes": lanes, "walk": W, "cut": cut, "cut_row": cut_row, "one_way": n_oneway,
            "legs": legs}


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
