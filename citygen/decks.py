"""M14: layered districts. A district with `decks` gets an upper street level, a slab on
columns over a cluster of its blocks and the local streets between them, with streets, lots
and buildings of its own (level 1), ramps down to the ground streets, light wells with stairs
and elevators, and everything under it kept usable (clear height, light, columns off the
lanes and the clear paths).

1. **Plan** (`plan`, in M2 right after the local streets, before the junctions): the faces of
   the at-grade street graph inside the district (blocks bounded by street centerlines); a
   cluster of eligible faces grown from the one nearest the district's middle, across local
   streets only, until it covers `cover` of the district; a street whose two sides are in the
   cluster is an *interior* street, a node all of whose streets are interior an interior
   node. Every interior street gets an upper twin (level 1, z the deck top) between the
   twins of its nodes; a *spoke* (an interior street with one interior end) ends on the deck
   at the property line of the edge street (a dead end over it), or is a *ramp*: the ground
   street replaced by a two-way ramp from the upper node down to the edge junction at 10% at
   most (`RAMP_GRADE`), chosen long, straight and spread round the deck, never cutting the
   ground network apart.
2. **Finish** (`finish`, after the blocks): the lots of the cluster that front an interior
   street go under the deck; the deck is their union with the interior street corridors (to
   the spoke ends), less the ramp slots (where a ramp is too high to pass under the slab).
   Light wells: lots under the deck become plazas open to the sky, chosen greedily until no
   ground walkway under the deck is farther than `light_m` from the sky (two per deck at
   least); each well gets a stair and an elevator from the ground sidewalk to the upper one.
   Upper lots: the other lots under the deck, with their frontage on the twins.
3. **Supports** (`supports`, after transit and tunnels): columns on a grid of `column_m`,
   moved off lanes, crosswalks, junctions, clear paths, ramps and wells.

Ids: upper nodes and segments `l1.<id>` (stable: `rn.<cell>.l1`, `l1.rs.<cell>`), upper lots
`<lot>.l1` (stable `<district>.lot.<cell>.l1`), upper walkways `l1.wk<n>`.
"""

from __future__ import annotations

import copy
import heapq
import math
from dataclasses import dataclass, field

import shapely
import shapely.ops
from shapely.geometry import LineString, Point, Polygon

from . import dmath as M
from . import geom as G
from . import streets as ST

SLAB_M = 1.2            # slab depth
CLEAR_M = 5.5           # clear height for traffic under the slab or over a ramp
RAMP_GRADE = 0.12       # steepest ramp grade (a street's, as M13 grades them)
RAMP_TOP_M = 10.0       # level run at the upper node (its junction)
RAMP_FOOT_M = 12.0      # level run before the edge junction
RAMP_CURVE_M = 15.0     # vertical curve at each change of grade
RAMP_LANE_M = 3.2
RAMP_BARRIER_M = 0.5
END_GAP_M = 6.0         # a spoke's twin ends this far short of the edge street's property line
FACE_MIN_M2 = 1500.0
FACE_IN = 0.9           # share of a face inside its district
RAISED_PAD_M = 8.0
RIM_M = 4.0            # the slab past its streets over a park or plaza (a colonnade)
HELD_PAD_M = 14.0      # a held transit line (M10) a new deck keeps off: half its width and more
HELD_DECK_M = 3.0      # its guideway under the track, over the deck clearance
FACE_MAX_M2 = 80000.0
CAR = ("street", "alley")
INTERIOR = ("street", "alley", "pedestrian")


def ramp_need(h: float) -> float:
    """Shortest spoke a ramp to a deck of top h fits on."""
    return RAMP_TOP_M + RAMP_FOOT_M + h / RAMP_GRADE + RAMP_CURVE_M


@dataclass
class Deck:
    id: str
    did: str
    name: str
    spec: object
    top: float
    faces: list = field(default_factory=list)          # cluster faces (polygons)
    interior: set = field(default_factory=set)         # interior segment ids
    nodes: set = field(default_factory=set)            # interior node ids
    edge_nodes: set = field(default_factory=set)
    twin: dict = field(default_factory=dict)           # lower segment id -> upper id
    node_twin: dict = field(default_factory=dict)      # lower node id -> upper id
    ends: dict = field(default_factory=dict)           # spoke id -> (end node id, end point)
    ramps: list = field(default_factory=list)          # ramp (former spoke) ids
    orig: dict = field(default_factory=dict)           # ramp id -> the spoke it replaced
    notes: list = field(default_factory=list)
    # after the blocks
    polygon: object = None
    under: list = field(default_factory=list)          # lot ids under the deck
    wells: list = field(default_factory=list)          # lot ids opened as wells
    upper_lots: list = field(default_factory=list)


@dataclass
class Plan:
    decks: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def deck_of(self, did: str):
        return next((d for d in self.decks if d.did == did), None)


# ---------------------------------------------------------------------------
# Plan (M2, before the junctions)
# ---------------------------------------------------------------------------

def _graded(s: dict) -> bool:
    return s.get("level", 0) == 0 and not s.get("tunnel") and not s.get("bridge") and \
        all(p["z"] == 0.0 for p in s["z_profile"])


def _faces(segs: list[dict], pos: dict):
    """Faces of a plane graph: lists of (node, segment id, next node), each face to the left
    of its half-edges (bounded faces counterclockwise); half-edge -> face."""
    out: dict = {}
    for s in segs:
        a, b = s["start"], s["end"]
        if a == b:
            continue
        pa, pb = s["centerline"][1], s["centerline"][-2]
        out.setdefault(a, []).append((M.atan2(pa[1] - pos[a][1], pa[0] - pos[a][0]),
                                      s["id"], b))
        out.setdefault(b, []).append((M.atan2(pb[1] - pos[b][1], pb[0] - pos[b][0]),
                                      s["id"], a))
    for k in out:
        out[k].sort()
    face_of: dict = {}
    faces: list = []
    for u in sorted(out):
        for _, sid, v in out[u]:
            if (u, sid) in face_of:
                continue
            cyc = []
            cu, cs, cv = u, sid, v
            for _ in range(20000):
                face_of[(cu, cs)] = len(faces)
                cyc.append((cu, cs, cv))
                lst = out[cv]
                j = next(i for i, e in enumerate(lst) if e[1] == cs and e[2] == cu)
                _, ns, nv = lst[(j - 1) % len(lst)]
                cu, cs, cv = cv, ns, nv
                if (cu, cs) == (u, sid):
                    break
            faces.append(cyc)
    return faces, face_of


def _ring(cyc, segs: dict) -> list:
    pts = []
    for cu, sid, cv in cyc:
        s = segs[sid]
        line = s["centerline"] if s["start"] == cu else s["centerline"][::-1]
        for p in line:
            p = (p[0], p[1])
            if not pts or pts[-1] != p:
                pts.append(p)
    return pts


def _signed2(pts) -> float:
    return math.fsum(pts[i][0] * pts[(i + 1) % len(pts)][1] -
                     pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


def _face_poly(pts):
    if len(pts) < 3:
        return Polygon()
    ps = G.parts(G.qpoly(shapely.make_valid(Polygon(pts))))
    return ps[0] if ps else Polygon()


def plan(spec, net, B, did_by_name: dict, held: dict | None = None) -> Plan:
    """The decks of every district with `decks`: the cluster, the interior streets, the upper
    twins and the ramps, added to `net` (upper nodes and segments appended, ramps in place of
    their spokes). `held`: the transit lines a district regeneration keeps (M10), whose old
    heights a new deck must pass under."""
    pl = Plan()
    want = [d for d in spec.districts if d.decks is not None and d.name in B.polygons]
    if not want:
        return pl
    segs = {s["id"]: s for s in net.segments}
    pos = {n["id"]: tuple(n["position"][:2]) for n in net.nodes}
    at: dict = {}
    for s in net.segments:
        at.setdefault(s["start"], []).append(s["id"])
        if s["end"] != s["start"]:
            at.setdefault(s["end"], []).append(s["id"])
    # (decks keep clear of viaducts and ramps: no face beside a road raised over 3 m)
    raised = [G.qpoly(LineString(s["centerline"]).buffer(s["width_m"] / 2 + RAISED_PAD_M,
                                                          cap_style="flat"))
              for s in net.segments if not s.get("bridge") and not s.get("tunnel") and
              (s.get("level", 0) >= 1 or max(p["z"] for p in s["z_profile"]) > 3.0)]
    raised_u = G.union(raised) if raised else Polygon()
    # (and of a held elevated line too low over it, piece by piece by its lowest end)
    lines = []
    for name in sorted(held or {}):
        row = held[name]
        if row["mode"] == "metro":
            continue
        pts = row["path"]
        for a, b in zip(pts, pts[1:]):
            if (a[0], a[1]) != (b[0], b[1]):
                lines.append((G.qpoly(LineString([a[:2], b[:2]]).buffer(
                    HELD_PAD_M, cap_style="flat")), min(a[2], b[2])))
    for d in want:
        did = did_by_name[d.name]
        dk = Deck(id=f"{did}.deck01", did=did, name=d.name, spec=d.decks,
                  top=G.q(d.decks.height_m))
        low = [p for p, z in lines if z < dk.top + CLEAR_M + HELD_DECK_M]
        _cluster(dk, d, B, net, segs, pos, at, G.union([raised_u] + low) if low else raised_u)
        if not dk.faces:
            pl.notes.append(f"{d.name}: no blocks fit a deck")
            continue
        _upper(dk, net, segs, pos, at, B)
        if not dk.nodes:
            pl.notes.append(f"{d.name}: no ramp fits the deck's streets")
            continue
        pl.decks.append(dk)
    return pl


def _cluster(dk: Deck, d, B, net, segs: dict, pos: dict, at: dict, raised_u) -> None:
    poly = B.polygons[d.name]
    zone = G.qpoly(poly.buffer(400.0, join_style="mitre"))
    local = [s for s in net.segments if _graded(s) and not G.apart(
        LineString(s["centerline"]), zone)]
    faces, face_of = _faces(local, pos)
    closed = G.union([B.closed, B.wet]) if hasattr(B, "closed") else B.wet
    inside = G.qpoly(poly.buffer(2.0, join_style="mitre"))
    ok: dict = {}
    for k, cyc in enumerate(faces):
        ring = _ring(cyc, segs)
        if len(ring) < 3 or _signed2(ring) <= 0:
            continue
        fp = _face_poly(ring)
        A = G.area1(fp)
        if not FACE_MIN_M2 <= A <= FACE_MAX_M2:
            continue
        if G.area1(G.inter(fp, inside)) < FACE_IN * A:
            continue
        if not closed.is_empty and G.area1(G.inter(fp, closed)) > 0.01 * A:
            continue
        if not raised_u.is_empty and fp.intersects(raised_u):
            continue
        if any(segs[sid]["road_class"] not in ("street", "alley", "pedestrian", "service",
                                               "avenue") for _, sid, _ in cyc):
            continue
        ok[k] = fp
    if not ok:
        return
    # adjacency across interior-class streets
    adj: dict = {k: set() for k in ok}
    for s in local:
        f1, f2 = face_of.get((s["start"], s["id"])), face_of.get((s["end"], s["id"]))
        if f1 in ok and f2 in ok and f1 != f2 and s["road_class"] in INTERIOR:
            adj[f1].add(f2)
            adj[f2].add(f1)
    cen = {k: G.centroid(fp) for k, fp in ok.items()}
    mid = G.centroid(poly)
    seed = min(ok, key=lambda k: (round(ST._dist(cen[k], mid), 2), cen[k]))
    target = d.decks.cover * G.area1(poly)
    chosen: list = []
    total = 0.0
    seen = {seed}
    heap = [(0.0, cen[seed], seed)]
    while heap and total < target:
        _, _, k = heapq.heappop(heap)
        chosen.append(k)
        total += G.area1(ok[k])
        for j in sorted(adj[k]):
            if j not in seen:
                seen.add(j)
                heapq.heappush(heap, (round(ST._dist(cen[j], cen[seed]), 2), cen[j], j))
    C = set(chosen)
    cls = _classify(C, local, face_of, at, segs)
    if not cls["nodes"]:
        return
    dk.faces = [ok[k] for k in sorted(C, key=lambda f: cen[f])]
    dk.interior = cls["interior"]
    dk.nodes = cls["nodes"]
    dk.edge_nodes = cls["edge"]


def _classify(C: set, local: list, face_of: dict, at: dict, segs: dict) -> dict:
    interior = set()
    for s in local:
        f1, f2 = face_of.get((s["start"], s["id"])), face_of.get((s["end"], s["id"]))
        if f1 in C and f2 in C and s["road_class"] in INTERIOR:
            interior.add(s["id"])
    nodes, edge = set(), set()
    for sid in interior:
        for n in (segs[sid]["start"], segs[sid]["end"]):
            if all(x in interior for x in at[n]):
                nodes.add(n)
            else:
                edge.add(n)
    # a chord (two edge ends) is left open like an edge street: no twin, no deck over it
    interior = {sid for sid in interior if segs[sid]["start"] in nodes or
                segs[sid]["end"] in nodes}
    return {"interior": interior, "nodes": nodes, "edge": edge}


def _straight(pts) -> float:
    """Farthest a polyline strays from its chord."""
    a, b = pts[0], pts[-1]
    return max((ST._seg_dist(p, a, b)[0] for p in pts[1:-1]), default=0.0)


def _upper(dk: Deck, net, segs: dict, pos: dict, at: dict, B) -> None:
    H = dk.top
    spokes = sorted(sid for sid in dk.interior
                    if (segs[sid]["start"] in dk.nodes) != (segs[sid]["end"] in dk.nodes))
    inner = sorted(sid for sid in dk.interior
                   if segs[sid]["start"] in dk.nodes and segs[sid]["end"] in dk.nodes)
    # ramps: long straight car spokes, spread round the deck
    need = ramp_need(H)
    cand = []
    for sid in spokes:
        s = segs[sid]
        L = ST._plen(s["centerline"])
        if s["road_class"] != "street" or L < need or s.get("one_way"):
            continue
        edge = s["end"] if s["start"] in dk.nodes else s["start"]
        cars = [x for x in at[edge] if x != sid and segs[x]["road_class"] in
                ("street", "avenue", "alley", "service") and _graded(segs[x])]
        if not cars:
            continue
        cand.append((round(L, 2), sid, pos[edge]))
    cand.sort(key=lambda c: (-c[0], c[1]))
    # the upper network's parts (interior nodes joined by inner streets): one ramp each
    # first, the longest; then the rest, spread round the deck
    comp = _uf_nodes(dk.nodes, [(segs[x]["start"], segs[x]["end"]) for x in inner])
    chosen: list = []
    deg: dict = {}
    for n in dk.nodes:
        deg[n] = sum(1 for x in at[n] if segs[x]["road_class"] in CAR)

    def fits(sid):
        a = _inner(segs[sid], dk)
        return deg[a] - 1 >= 2 and _connected_without(net, segs, chosen + [sid], dk)

    def take(c):
        cand.remove(c)
        chosen.append(c[1])
        deg[_inner(segs[c[1]], dk)] -= 1

    roots = sorted({comp[n] for n in dk.nodes},
                   key=lambda r: (-sum(1 for n in dk.nodes if comp[n] == r), r))
    for r in roots:
        for c in list(cand):
            if comp[_inner(segs[c[1]], dk)] == r and fits(c[1]):
                take(c)
                break
    while cand and len(chosen) < max(dk.spec.ramps, len(roots)):
        cand.sort(key=lambda c: (-round(min(ST._dist(c[2], pos[_edge(segs[x], dk)])
                                            for x in chosen), 1), -c[0], c[1]))
        pick = next((c for c in cand if fits(c[1])), None)
        if pick is None:
            break
        take(pick)
    dk.ramps = sorted(chosen)
    served = {comp[_inner(segs[x], dk)] for x in dk.ramps}
    gone = {n for n in dk.nodes if comp[n] not in served}
    if gone:
        # (a part no ramp reaches gets no deck)
        dk.notes.append(f"{len(gone)} interior nodes left without a deck: no ramp fits "
                        f"their streets ({need:.0f} m)")
        dk.nodes -= gone
        dk.interior = {x for x in dk.interior if segs[x]["start"] in dk.nodes or
                       segs[x]["end"] in dk.nodes}
        spokes = [x for x in spokes if x in dk.interior and
                  (segs[x]["start"] in dk.nodes) != (segs[x]["end"] in dk.nodes)]
        inner = [x for x in inner if x in dk.interior and segs[x]["start"] in dk.nodes and
                 segs[x]["end"] in dk.nodes]
    if not dk.nodes:
        return
    # upper nodes
    for nid in sorted(dk.nodes):
        n = next(x for x in net.nodes if x["id"] == nid)
        un = f"l1.{nid}"
        dk.node_twin[nid] = un
        net.nodes.append({"id": un, "position": (n["position"][0], n["position"][1], H),
                          "level": 1, "attrs": {**n["attrs"], "deck": dk.id, "twin": nid}})
    car = True
    for sid in inner:
        s = segs[sid]
        net.segments.append(_twin(s, f"l1.{sid}", dk.node_twin[s["start"]],
                                  dk.node_twin[s["end"]], s["centerline"], dk, car))
        dk.twin[sid] = f"l1.{sid}"
    for sid in spokes:
        s = segs[sid]
        if sid in dk.ramps:
            _ramp(s, dk)
            continue
        e = _edge(s, dk)
        half = max((segs[x]["width_m"] / 2 for x in at[e] if x not in dk.interior),
                   default=0.0)
        pts = [tuple(p) for p in s["centerline"]]
        L = ST._plen(pts)
        cut = half + END_GAP_M
        if L - cut < 20.0:
            continue
        if s["start"] == e:
            line = ST._substring(pts, cut, L)
        else:
            line = ST._substring(pts, 0.0, L - cut)
        end_pt = line[0] if s["start"] == e else line[-1]
        en = f"l1.{sid}.e"
        net.nodes.append({"id": en, "position": (end_pt[0], end_pt[1], H), "level": 1,
                          "attrs": {"kind": "end", "degree": 1, "primary_degree": 0,
                                    "deck": dk.id, "deck_end": True,
                                    "dead_end": "deck_end"}})
        a = dk.node_twin[_inner(s, dk)]
        st, en_ = (en, a) if s["start"] == e else (a, en)
        tw = _twin(s, f"l1.{sid}", st, en_, line, dk, car)
        tw["attrs"]["role"] = "deck_end"
        net.segments.append(tw)
        dk.twin[sid] = tw["id"]
        dk.ends[sid] = (en, end_pt, half)


def _uf_nodes(nodes, pairs) -> dict:
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return {n: find(n) for n in nodes}


def _edge(s: dict, dk: Deck) -> str:
    return s["end"] if s["start"] in dk.nodes else s["start"]


def _inner(s: dict, dk: Deck) -> str:
    return s["start"] if s["start"] in dk.nodes else s["end"]


def _connected_without(net, segs: dict, gone: list, dk: Deck) -> bool:
    """The ground car network keeps the components it had without these spokes."""
    gone = set(gone)

    def comps(skip):
        parent: dict = {}

        def find(x):
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for s in net.segments:
            if s["id"] in skip or s.get("level", 0) != 0 or "deck" in s["attrs"] or \
                    s["road_class"] not in ST.VEHICLE:
                continue
            parent[find(s["start"])] = find(s["end"])
        return len({find(x) for x in list(parent)}), {x for x in parent}
    n0, nodes0 = comps(set())
    n1, nodes1 = comps(gone)
    return n1 == n0 and nodes1 == nodes0


def _twin(s: dict, sid: str, start: str, end: str, line, dk: Deck, car: bool) -> dict:
    t = copy.deepcopy(s)
    pts = [(G.q(p[0]), G.q(p[1])) for p in line]
    L = G.q(ST._plen(pts))
    t.update({"id": sid, "start": start, "end": end, "centerline": pts, "level": 1,
              "z_profile": [{"s": 0.0, "z": dk.top}, {"s": L, "z": dk.top}],
              "bridge": False, "bridge_ids": [], "clearance_m": None,
              "district_ids": [dk.did]})     # (the blockout joins a deck's streets by it)
    t["attrs"] = {**s["attrs"], "length_m": L, "deck": dk.id, "twin": s["id"]}
    if t.get("name"):
        t["name"] = f"Upper {t['name']}"
    if not car and t["road_class"] in CAR:
        cs = ST.cross_section("pedestrian", None)
        cs["total_width_m"] = t["width_m"]
        cs["sidewalk_m"] = (t["width_m"] / 2, t["width_m"] / 2)
        t.update({"road_class": "pedestrian", "type": "road.pedestrian", "lanes": 0,
                  "cross_section": cs, "one_way": False})
    return t


def _ramp(s: dict, dk: Deck) -> None:
    """The spoke becomes a two-way ramp from its upper node down to the edge junction: level
    on top, a constant grade with vertical curves, level at the foot."""
    H = dk.top
    a = _inner(s, dk)
    dk.orig[s["id"]] = copy.deepcopy(s)
    pts = [tuple(p) for p in s["centerline"]]
    L = ST._plen(pts)
    prof = ramp_profile(L, H)
    if s["start"] != a:
        prof = [(G.q(L - x), z) for x, z in reversed(prof)]
    w = G.q(2 * RAMP_LANE_M + 2 * RAMP_BARRIER_M)
    cs = ST.section((1, 1), RAMP_LANE_M)
    cs["total_width_m"] = w
    if s["start"] == a:
        s["start"] = dk.node_twin[a]
    else:
        s["end"] = dk.node_twin[a]
    s.update({"level": 1, "z_profile": [{"s": x, "z": z} for x, z in prof],
              "cross_section": cs, "width_m": w, "lanes": 2, "one_way": False,
              "district_ids": [dk.did]})
    s["attrs"] = {**s["attrs"], "role": "deck_ramp", "deck": dk.id}


def ramp_profile(L: float, H: float) -> list:
    """(s, z) from the top (s 0, z H) to the foot (s L, z 0): level runs, a constant grade
    between them, parabolic vertical curves of RAMP_CURVE_M at both changes, every 5 m on
    the curves."""
    run = L - RAMP_TOP_M - RAMP_FOOT_M
    g = H / (run - RAMP_CURVE_M)       # grade between the curves
    c = RAMP_CURVE_M
    out = [(0.0, H), (RAMP_TOP_M, H)]
    # curve 1 (convex): z = H - g x^2 / (2c) for x in [0, c]
    for k in range(1, 4):
        x = c * k / 4
        out.append((RAMP_TOP_M + x, H - g * x * x / (2 * c)))
    s1 = RAMP_TOP_M + c
    z1 = H - g * c / 2
    s2 = L - RAMP_FOOT_M - c
    out.append((s1, z1))
    out.append((s2, g * c / 2))
    for k in range(1, 4):
        x = c * k / 4
        out.append((s2 + x, g * c / 2 - g * x + g * x * x / (2 * c)))
    out.append((L - RAMP_FOOT_M, 0.0))
    out.append((L, 0.0))
    return [(G.q(x), G.q(max(z, 0.0))) for x, z in out]


def ramp_grade(L: float, H: float) -> float:
    return H / (L - RAMP_TOP_M - RAMP_FOOT_M - RAMP_CURVE_M)


# ---------------------------------------------------------------------------
# Finish (M2, after the blocks)
# ---------------------------------------------------------------------------

WELL_FRONT_M = 21.0     # a light well fronts an upper street this long at least (its stair)
WELL_AREA_M2 = (350.0, 12000.0)
MIN_WELLS = 2
SAMPLE_M = 8.0          # walkway sample spacing for the light test
STAIR_W = 2.4
STAIR_RUN = 1.75        # stair run per meter of rise (about 30 degrees)
STAIR_IN_M = 2.2        # stair (first flight) and elevator centers behind the property line
STAIR_GAP_M = 2.6       # between the two flights of a stair (a switchback)
STAIR_START_M = 3.0
ELEV_W = 3.0
DECK_MIN_M2 = 3000.0
UPPER_FRONT_M = 6.0     # an upper lot fronts its deck's streets this long at least
LIGHT_KINDS = ("sidewalk", "crosswalk", "crossing", "path", "alley", "pedestrian_street",
               "promenade")


def street_view(net, jx: dict, pl: Plan):
    """The ground level of the street network, as the block stage sees it: no deck streets,
    each ramp as the street it replaced (so the lots beside it are those of a city without
    the deck)."""
    if not pl.decks:
        return net, jx
    orig = {sid: rec for dk in pl.decks for sid, rec in dk.orig.items()}
    segs = [orig.get(s["id"], s) for s in net.segments
            if not is_deck(s) or s["attrs"].get("role") == "deck_ramp"]
    gn = copy.copy(net)
    gn.segments = segs
    gn.nodes = [n for n in net.nodes if "deck" not in n["attrs"]]
    up = {n["id"] for n in net.nodes if "deck" in n["attrs"]}
    gj = dict(jx)
    gj["junctions"] = [j for j in jx["junctions"] if j["node_id"] not in up]
    jids = {j["id"] for j in gj["junctions"]}
    gj["crosswalks"] = [c for c in jx["crosswalks"] if c["junction_id"] in jids]
    keep = {s["id"] for s in segs}
    gj["sidewalks"] = [w for w in jx["sidewalks"] if w["segment_id"] in keep]
    return gn, gj


@dataclass
class Link:
    """A stair or an elevator of a light well: where it meets each level's sidewalk."""
    kind: str             # stairs, elevator
    deck: str
    well: str             # the lot it stands on (an open space after numbering)
    foot: tuple           # ground end (on the lot)
    head: tuple           # deck end
    low: tuple            # point on the ground sidewalk
    high: tuple           # point on the deck sidewalk
    footprint: object
    low_sw: str
    high_sw: str
    walkway_id: str = ""
    mid: list = field(default_factory=list)   # (x, y, z) between foot and head


def finish(pl: Plan, net, jx: dict, blk: dict) -> dict:
    """Lots under the decks, the deck slabs, light wells with their stairs and elevators,
    and the upper lots; changes `blk` (wells leave the lots for the open space) and the walk
    graphs of `jx` (the sidewalks split where a stair or an elevator meets them)."""
    out = {"links": [], "upper_lots": [], "decks": []}
    if not pl.decks:
        return out
    segs = {s["id"]: s for s in net.segments}
    for dk in pl.decks:
        _finish(dk, segs, net, jx, blk, out)
    return out


def _finish(dk: Deck, segs: dict, net, jx: dict, blk: dict, out: dict) -> None:
    H = dk.top
    faces = G.union(dk.faces)
    lots = [r for r in blk["lots"] if r["district_id"] == dk.did and
            not (r.get("attrs") or {}).get("pinned") and not (r.get("attrs") or {}).get("pin")]
    under = []
    for r in lots:
        A = G.area1(r["polygon"])
        if A <= 0 or not any(f["segment_id"] in dk.twin for f in r["frontage"]):
            continue
        if G.area1(G.inter(r["polygon"], faces)) < 0.98 * A:
            continue
        under.append(r)
    row = []
    for sid, tid in sorted(dk.twin.items()):
        t = segs[tid]
        line = [tuple(p) for p in t["centerline"]]
        if sid in dk.ends:
            # (a spoke's deck runs on past its dead end to the edge street's property line)
            s = segs[sid]
            pts = [tuple(p) for p in s["centerline"]]
            L = ST._plen(pts)
            half = dk.ends[sid][2]
            line = ST._substring(pts, half, L) if s["start"] == _edge(s, dk) else \
                ST._substring(pts, 0.0, L - half)
        row.append(G.qpoly(LineString(line).buffer(t["width_m"] / 2, cap_style="flat",
                                                   join_style="mitre", mitre_limit=2.0)))
    up = set(dk.node_twin.values())
    js = [j for j in jx["junctions"] if j["node_id"] in up and
          j.get("row_polygon") is not None and not j["row_polygon"].is_empty]
    row += [j["row_polygon"] for j in js]
    # (where its streets pass a park or plaza, no lot under the deck reaches them: the slab
    # runs on over its edge, a colonnade in the park carries it)
    parks = [o["polygon"] for o in blk["open"] if o.get("district_id") == dk.did]
    if parks:
        rim = G.qpoly(G.union(row).buffer(RIM_M, join_style="mitre"))
        row.append(G.inter(rim, G.union(parks)))
    body = G.union([r["polygon"] for r in under] + row)
    ps = [p for p in G.parts(body) if G.area1(p) >= DECK_MIN_M2]
    if not ps:
        dk.notes.append("no ground left for a deck")
        return
    deck = ps[0]
    under = [r for r in under if G.area1(G.inter(r["polygon"], deck)) >= 0.98 * G.area1(
        r["polygon"])]
    # light wells: lots opened to the sky until every ground walkway under the deck is
    # within light_m of it
    pts = []
    for e in jx["walk"].edges:
        if e["kind"] not in LIGHT_KINDS:
            continue
        line = e["pts"]
        L = ST._plen(line)
        n = max(1, int(L / SAMPLE_M))
        for k in range(n + 1):
            pts.append(ST._pt(*ST._along(line, L * k / n)[0]))
    pts = sorted(set(pts))
    arr = shapely.points(pts) if pts else None
    inside = shapely.contains(deck, arr).tolist() if pts else []
    pts = [p for p, i in zip(pts, inside) if i]
    lim = dk.spec.light_m
    cands = []
    for r in under:
        f = _well_front(r, dk)
        A = G.area1(r["polygon"])
        if f is not None and WELL_AREA_M2[0] <= A <= WELL_AREA_M2[1]:
            cands.append(r)
    wells: list = []
    if pts:
        parr = shapely.points(pts)
        sky = G.dists(deck.boundary, parr) <= lim
        while True:
            need = not bool(sky.all()) or len(wells) < MIN_WELLS
            if not need:
                break
            best = None
            taken = {w["id"] for w in wells}
            for r in cands:
                if r["id"] in taken:
                    continue
                d = G.dists(r["polygon"], parr) <= lim
                gain = int((d & ~sky).sum())
                spread = min((ST._dist(G.centroid(r["polygon"]), G.centroid(w["polygon"]))
                              for w in wells), default=0.0)
                k = (gain, round(spread, 1), r["id"])
                if best is None or k > best[0]:
                    best = (k, r, d)
            if best is None or (best[0][0] == 0 and len(wells) >= MIN_WELLS):
                break
            wells.append(best[1])
            sky = sky | best[2]
        if not bool(sky.all()):
            dk.notes.append(f"{int((~sky).sum())} walkway points under the deck farther "
                            f"than {lim:g} m from the sky")
    for w in wells:
        deck = G.diff(deck, w["polygon"])
        deck = G.parts(deck)[0]
    dk.polygon = deck
    dk.wells = [w["id"] for w in wells]
    dk.under = [r["id"] for r in under if r not in wells]
    # stairs and elevators of every well
    for w in wells:
        out["links"] += _links(dk, w, segs, jx)
    # the lots: wells leave them, the rest under the deck get a twin up on it
    wid = {w["id"] for w in wells}
    groups = {r.get("merged_group_id") for r in under if r.get("merged_group_id")}
    for r in blk["lots"]:
        if r.get("merged_group_id") in groups:
            r["merged_group_id"] = None     # (no complex across the deck's edge)
    blk["lots"] = [r for r in blk["lots"] if r["id"] not in wid]
    for w in wells:
        blk["open"].append({"kind": "plaza", "polygon": w["polygon"], "name": None,
                            "district_id": dk.did, "light_well": dk.id, "lot": w["id"]})
    for r in under:
        if r["id"] in wid:
            continue
        r.setdefault("attrs", {})["deck_under"] = dk.id
        poly = G.parts(G.inter(r["polygon"], deck))
        if not poly or G.area1(poly[0]) < 0.6 * G.area1(r["polygon"]):
            continue
        fr = []
        for f in r["frontage"]:
            t = dk.twin.get(f["segment_id"])
            if t is not None:
                fr.append({**f, "segment_id": t, "road_class": segs[t]["road_class"]})
        if math.fsum(f["length_m"] for f in fr) < UPPER_FRONT_M:
            continue      # (a corner of a lot touching its street: no lot up there)
        u = {**{k: v for k, v in r.items() if k not in ("attrs",)},
             "id": f"{r['id']}.l1", "polygon": poly[0], "frontage": fr,
             "frontage_ids": [f["segment_id"] for f in fr], "merged_group_id": None,
             "area_m2": G.q(G.area1(poly[0])), "level": 1,
             "attrs": {**{k: v for k, v in (r.get("attrs") or {}).items()
                          if k != "deck_under"}, "deck": dk.id, "under": r["id"]}}
        out["upper_lots"].append(u)
        dk.upper_lots.append(u["id"])


def _well_front(r: dict, dk: Deck):
    """The longest straight frontage of a lot on a street with a twin (the stair runs along
    it), or None."""
    best = None
    for f in r["frontage"]:
        if f["segment_id"] not in dk.twin:
            continue
        line = [tuple(p) for p in f["line"]]
        L = ST._plen(line)
        if L < WELL_FRONT_M or _straight(line) > 1.5:
            continue
        if best is None or (L, f["segment_id"]) > (best[0], best[1]["segment_id"]):
            best = (L, f)
    return None if best is None else best[1]


def _sidewalk(jx: dict, sid: str, p):
    """The sidewalk of road sid nearest to p: (id, line)."""
    best = None
    for w in jx["sidewalks"]:
        if w["segment_id"] != sid:
            continue
        d = ST._project([tuple(x) for x in w["line"]], p)[1]
        if best is None or (round(d, 6), w["id"]) < best[0]:
            best = ((round(d, 6), w["id"]), w)
    return None if best is None else best[1]


def _links(dk: Deck, w: dict, segs: dict, jx: dict) -> list:
    f = _well_front(w, dk)
    line = [tuple(p) for p in f["line"]]
    a, b = line[0], line[-1]
    L = ST._dist(a, b)
    t = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    c = G.centroid(w["polygon"])
    n = (-t[1], t[0])
    if (c[0] - a[0]) * n[0] + (c[1] - a[1]) * n[1] < 0:
        n = (-n[0], -n[1])

    def at(s, d):
        return ST._pt(a[0] + t[0] * s + n[0] * d, a[1] + t[1] * s + n[1] * d)

    run = dk.top * STAIR_RUN
    low = _sidewalk(jx, f["segment_id"], at(L / 2, 0.0))
    high = _sidewalk(jx, dk.twin[f["segment_id"]], at(L / 2, 0.0))
    if low is None or high is None:
        dk.notes.append(f"well {w['id']}: no sidewalk to join")
        return []
    out = []
    # a switchback: up along the frontage half the rise, a landing, back up the other half
    s0, s1 = STAIR_START_M, STAIR_START_M + run / 2
    d1, d2 = STAIR_IN_M, STAIR_IN_M + STAIR_GAP_M
    foot, head = at(s0, d1), at(s0, d2)
    hw = STAIR_W / 2
    fp = Polygon([at(s0, d1 - hw), at(s1 + hw, d1 - hw), at(s1 + hw, d2 + hw),
                  at(s0, d2 + hw)])
    lo_line = [tuple(x) for x in low["line"]]
    hi_line = [tuple(x) for x in high["line"]]
    zm = G.q(dk.top / 2)
    out.append(Link("stairs", dk.id, w["id"], foot, head,
                    ST._pt(*ST._project(lo_line, at(s0, 0.0))[2]),
                    ST._pt(*ST._project(hi_line, at(s0, 0.0))[2]),
                    G.qpoly(fp), low["id"], high["id"],
                    mid=[(*at(s1, d1), zm), (*at(s1, d2), zm)]))
    se = L - STAIR_START_M - ELEV_W / 2
    e = at(se, STAIR_IN_M)
    he = ELEV_W / 2
    fe = Polygon([at(se - he, STAIR_IN_M - he), at(se + he, STAIR_IN_M - he),
                  at(se + he, STAIR_IN_M + he), at(se - he, STAIR_IN_M + he)])
    out.append(Link("elevator", dk.id, w["id"], e, e,
                    ST._pt(*ST._project(lo_line, at(se, 0.0))[2]),
                    ST._pt(*ST._project(hi_line, at(se, 0.0))[2]),
                    G.qpoly(fe), low["id"], high["id"]))
    return out


def split_walk(W, sidewalk: str, p) -> None:
    """Split the walk edge of a sidewalk at p (on it), so p is a walk node."""
    best = None
    for i, e in enumerate(W.edges):
        if e["attrs"].get("sidewalk") != sidewalk:
            continue
        s, d, _, _ = ST._project(e["pts"], p)
        if best is None or (round(d, 6), i) < best[0]:
            best = ((round(d, 6), i), i, s)
    if best is None:
        return
    _, i, s = best
    e = W.edges[i]
    L = ST._plen(e["pts"])
    if s <= 0.05 or s >= L - 0.05:
        return
    a = ST._substring(e["pts"], 0.0, s)
    b = ST._substring(e["pts"], s, L)
    a[-1] = p
    b[0] = p
    W.edges[i] = {**e, "pts": ST._dedupe(a)}
    W.edges.insert(i + 1, {**e, "pts": ST._dedupe(b)})


def link_walks(pl: Plan, jx: dict, links: list) -> None:
    """The ground and deck ends of every stair and elevator: sidewalks split there, a path
    from the sidewalk to the foot (ground) and from the head to the sidewalk (deck)."""
    W0 = jx["walk"]
    W1 = jx["walk_levels"].get(1)
    for k in links:
        split_walk(W0, k.low_sw, k.low)
        if W1 is not None:
            split_walk(W1, k.high_sw, k.high)
        if k.low != k.foot:
            W0.add("path", [k.low, k.foot], 2.0, link=k.kind)
        if W1 is not None and k.head != k.high:
            W1.add("path", [k.head, k.high], 2.0, link=k.kind)


RAMP_WALK_M = 2.0       # walkway beside a ramp (within the street it replaced)


def ramp_walks(pl: Plan, net, jx: dict) -> list:
    """A walkway beside each side of every ramp, from the corner at its foot (the ground's
    walk graph) to the corner at its top (the deck's): (points with z, levels)."""
    from . import junctions as JN

    out = []
    lev = {n["id"]: n.get("level", 0) for n in net.nodes}
    segs = {s["id"]: s for s in net.segments}
    for dk in pl.decks:
        for rid in dk.ramps:
            s = segs[rid]
            pts = [tuple(p) for p in s["centerline"]]
            L = ST._plen(pts)
            a = jx["cut"].get((rid, s["start"]), 0.0)
            b = jx["cut"].get((rid, s["end"]), 0.0)
            base = ST._substring(pts, a, L - b) if L - a - b > 1.0 else pts
            h = s["width_m"] / 2 + RAMP_WALK_M / 2
            prof = s["z_profile"]
            for sd, sign in (("L", 1.0), ("R", -1.0)):
                line = JN._offset(base, sign * h)
                c0 = jx["corners"].get((s["start"], rid, sd))
                c1 = jx["corners"].get((s["end"], rid, sd))
                if len(line) < 2 or c0 is None or c1 is None:
                    continue
                chain = ST._dedupe([c0] + line + [c1])
                z = []
                for p in chain:
                    t = ST._project(pts, p)[0]
                    z.append(G.q(JN._z_at(prof, t)))
                z[0] = 0.0 if lev[s["start"]] == 0 else dk.top
                z[-1] = 0.0 if lev[s["end"]] == 0 else dk.top
                out.append({"pts": [(x, y, zz) for (x, y), zz in zip(chain, z)],
                            "levels": [lev[s["start"]], lev[s["end"]]], "ramp": rid,
                            "deck": dk.id})
    return out


def walk_rows(jx: dict, links: list, base: list, tops: dict, deck_of, ramps=()) -> list:
    """Walkway records of every level: the ground's (`base`, from `junctions.walkways`), the
    decks' (`l1.wk...`, z the deck top) and the stairs and elevators between them, with
    neighbors on (point, level)."""
    from . import junctions as JN

    rows = list(base)
    W1 = jx["walk_levels"].get(1)
    if W1 is not None:
        up = JN.walkways(W1)
        ren = {r["id"]: f"l1.{r['id']}" for r in up}
        for r in up:
            z = tops[deck_of(r["attrs"])]
            r["id"] = ren[r["id"]]
            r["neighbors"] = [ren[x] for x in r["neighbors"]]
            r["line"] = [(x, y, G.q(zz + z)) for x, y, zz in r["line"]]
            r["level"] = 1
            rows.append(r)
    for i, k in enumerate(links):
        z = tops[k.deck]
        wid = f"l1.{'st' if k.kind == 'stairs' else 'el'}{i + 1:04d}"
        line = [(k.foot[0], k.foot[1], 0.0)] + [tuple(p) for p in k.mid] + \
            [(k.head[0], k.head[1], z)]
        rows.append({"id": wid, "kind": k.kind, "line": line,
                     "width_m": STAIR_W if k.kind == "stairs" else ELEV_W, "neighbors": [],
                     "level": 1, "attrs": {"levels": [0, 1], "deck": k.deck, "well": k.well}})
        k.walkway_id = wid
    for i, r in enumerate(ramps):
        rows.append({"id": f"l1.rw{i + 1:04d}", "kind": "path", "line": r["pts"],
                     "width_m": RAMP_WALK_M, "neighbors": [], "level": 1,
                     "attrs": {"levels": r["levels"], "deck": r["deck"], "ramp": r["ramp"]}})
    neighbors(rows)
    return rows


def neighbors(walks: list) -> None:
    """Neighbors of every walkway: the walkways that share an end, on its level."""
    at: dict = {}
    ends = []
    for w in walks:
        a, b = walk_ends(w)
        ends.append((a, b))
        at.setdefault(a, []).append(w["id"])
        at.setdefault(b, []).append(w["id"])
    for w, (a, b) in zip(walks, ends):
        w["neighbors"] = sorted(set(at[a] + at[b]) - {w["id"]})


def rows(pl: Plan, net, dko: dict, well_os: dict) -> tuple[list, list]:
    """Model rows: the decks, and the stair and elevator shafts of their wells."""
    P = G.to_model_poly
    decks, structs = [], []
    for dk in pl.decks:
        if dk.polygon is None:
            continue
        links = [k for k in dko["links"] if k.deck == dk.id]
        segs = sorted(set(dk.twin.values()) | set(dk.ramps))
        decks.append({"id": dk.id, "type": "deck", "district_id": dk.did, "level": 1,
                      "polygon": P(dk.polygon), "top_m": dk.top, "slab_m": SLAB_M,
                      "area_m2": G.q(G.area1(dk.polygon)), "segment_ids": segs,
                      "well_ids": [well_os[w] for w in dk.wells if w in well_os],
                      "column_ids": [], "walkway_ids": [k.walkway_id for k in links],
                      "attrs": {"under_lots": len(dk.under), "upper_lots": len(dk.upper_lots),
                                "ramps": len(dk.ramps), "column_m": dk.spec.column_m,
                                "light_m": dk.spec.light_m}})
        for i, k in enumerate(links):
            z1 = dk.top if k.kind == "stairs" else G.q(dk.top + 3.0)
            structs.append({"id": f"{dk.id}.{'st' if k.kind == 'stairs' else 'el'}{i + 1:02d}",
                            "type": f"structure.{'stair' if k.kind == 'stairs' else 'elevator'}",
                            "kind": "stair" if k.kind == "stairs" else "elevator",
                            "footprint": P(k.footprint),
                            "line": [(k.foot[0], k.foot[1], 0.0)] +
                            [tuple(p) for p in k.mid] + [(k.head[0], k.head[1], dk.top)],
                            "z0_m": 0.0, "z1_m": z1, "supports": [k.walkway_id],
                            "attrs": {"deck": dk.id, "well": well_os.get(k.well)}})
    return decks, structs


def info(pl: Plan, dko: dict) -> dict:
    out = {}
    for dk in pl.decks:
        if dk.polygon is None:
            continue
        out[dk.id] = {"area_m2": G.q(G.area1(dk.polygon)), "faces": len(dk.faces),
                      "upper_streets": len(dk.twin), "ramps": len(dk.ramps),
                      "under_lots": len(dk.under), "upper_lots": len(dk.upper_lots),
                      "wells": len(dk.wells),
                      "links": sum(1 for k in dko["links"] if k.deck == dk.id)}
    return out


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------

def is_deck(s) -> bool:
    """A street of a deck (its twin streets and ramps)."""
    a = s["attrs"] if isinstance(s, dict) else s.attrs
    return "deck" in a


def walk_level(e) -> int:
    """Walk level of a node or segment in M2's junction stage: the deck's level for its own
    streets and nodes (ramps carry no walkways), else 0."""
    a = e["attrs"]
    if "deck" not in a or a.get("role") == "deck_ramp":
        return 0
    return e.get("level", 0) or 0


def end_levels(w) -> tuple[int, int]:
    """Levels of a walkway's two ends: stairs and elevators join two (`attrs.levels`)."""
    if isinstance(w, dict):
        a, lv = w.get("attrs") or {}, w.get("level", 0) or 0
    else:
        a, lv = w.attrs, w.level
    ls = a.get("levels")
    return (ls[0], ls[1]) if ls else (lv, lv)


def key(p, lv: int) -> tuple:
    """A walk node: its plan point, and its level where that is not the ground (so a deck's
    sidewalk corner over a ground one is a node of its own)."""
    return (p[0], p[1]) if not lv else (p[0], p[1], lv)


def walk_ends(w) -> tuple[tuple, tuple]:
    la, lb = end_levels(w)
    line = w["line"] if isinstance(w, dict) else w.line
    return key(line[0], la), key(line[-1], lb)


def on_ground(w) -> bool:
    """A ground walkway of its level: on the ground (z 0) for the ground, at the deck top
    for a deck; never a stair, an elevator or a ramp's walkway between two levels."""
    from .buildout import GROUND_WALKS

    kind, line = (w["kind"], w["line"]) if isinstance(w, dict) else (w.kind, w.line)
    if kind not in GROUND_WALKS:
        return False
    la, lb = end_levels(w)
    if la != lb:
        return False
    if not la:
        return all(abs(p[2]) < 1e-9 for p in line)
    return all(abs(p[2] - line[0][2]) < 1e-9 for p in line)


# ---------------------------------------------------------------------------
# Level views (M6 and its checks see one ground at a time)
# ---------------------------------------------------------------------------

TREES = ("street_tree", "median_tree", "palm", "park_tree", "conifer")


def _deck_streets(m, dk) -> set:
    return {s.id for s in m.road_segments if s.attrs.get("deck") == dk.id and
            s.attrs.get("role") != "deck_ramp"}


def ground_view(m):
    """The ground level of a city with decks: without the decks' streets, junctions,
    walkways, lots and buildings, with each slab as an overhead structure (so a street light
    under it is hung from it and trees fit under it)."""
    from .model import Structure

    up = {sid for dk in m.decks for sid in _deck_streets(m, dk)}
    ups = {b.id for b in m.buildings if b.level}
    slabs = [Structure(id=f"{dk.id}.slab", type="structure.deck", kind="deck",
                       footprint=dk.polygon, z0_m=G.q(dk.top_m - dk.slab_m), z1_m=dk.top_m)
             for dk in m.decks]
    return m.model_copy(update={
        "road_segments": [s for s in m.road_segments if s.id not in up],
        "junctions": [x for x in m.junctions if not x.level],
        "crosswalks": [x for x in m.crosswalks if not x.level],
        "sidewalks": [x for x in m.sidewalks if not x.level],
        "lanes": [x for x in m.lanes if not x.level],
        "walkways": [x for x in m.walkways if not x.level],
        "lots": [x for x in m.lots if not x.level],
        "buildings": [x for x in m.buildings if not x.level],
        "open_spaces": [x for x in m.open_spaces if not x.level],
        "green_areas": [x for x in m.green_areas if not x.level],
        "skybridges": [x for x in m.skybridges if not set(x.building_ids) & ups],
        "props": [x for x in m.props if not x.level],
        "plants": [x for x in m.plants if not x.level],
        "structures": list(m.structures) + slabs})


def deck_view(m, dk):
    """A deck as a ground of its own: its streets, junctions, walkways, lots and buildings,
    every z measured from its top."""
    H = dk.top_m
    segs = _deck_streets(m, dk)
    nodes = {s.start for s in m.road_segments if s.id in segs} | \
        {s.end for s in m.road_segments if s.id in segs}
    jns = {j.id for j in m.junctions if j.node_id in nodes}
    blds = {b.id for b in m.buildings if b.level and b.attrs.get("deck") == dk.id}
    lots = {lt.id for lt in m.lots if lt.level and lt.attrs.get("deck") == dk.id}

    def down(e, fn):
        d = e.model_dump(mode="python")
        fn(d)
        return type(e).model_validate(d)

    def seg(d):
        d["z_profile"] = [{"s": z["s"], "z": G.q(z["z"] - H)} for z in d["z_profile"]]

    def node(d):
        x, y, z = d["position"]
        d["position"] = (x, y, G.q(z - H))

    def line3(key):
        def f(d):
            d[key] = [(p[0], p[1], G.q(p[2] - H)) for p in d[key]]
        return f

    def bld(d):
        for ms in d["masses"]:
            ms["z0_m"] = G.q(ms["z0_m"] - H)
            ms["z1_m"] = G.q(ms["z1_m"] - H)
        d["height_m"] = G.q(d["height_m"] - H)
        for it in d["roof_items"]:
            x, y, z = it["position"]
            it["position"] = (x, y, G.q(z - H))

    def zm(d):
        d["z_m"] = G.q(d["z_m"] - H)

    return m.model_copy(update={
        "road_nodes": [down(n, node) for n in m.road_nodes if n.id in nodes],
        "road_segments": [down(s, seg) for s in m.road_segments if s.id in segs],
        "junctions": [j for j in m.junctions if j.id in jns],
        "crosswalks": [c for c in m.crosswalks if c.junction_id in jns],
        "sidewalks": [w for w in m.sidewalks if w.segment_id in segs],
        "lanes": [down(ln, line3("centerline")) for ln in m.lanes if
                  (ln.segment_id in segs if ln.kind == "lane" else ln.node_id in nodes)],
        "walkways": [down(w, line3("line")) for w in m.walkways if w.level and on_ground(w)
                     and (w.attrs.get("deck") in (None, dk.id))],
        "lots": [lt for lt in m.lots if lt.id in lots],
        "buildings": [down(b, bld) for b in m.buildings if b.id in blds],
        "open_spaces": [o for o in m.open_spaces if o.level and
                        o.district_id == dk.district_id],
        "green_areas": [down(g, zm) for g in m.green_areas if g.level and
                        g.building_id in blds],
        "skybridges": [down(s, zm) for s in m.skybridges if set(s.building_ids) & blds],
        "site_elements": [down(e, zm) for e in m.site_elements if e.lot_id in lots],
        "structures": [], "tunnels": [], "stations": [], "transit_lines": [],
        "props": [down(p, _pos_down(H)) for p in m.props if p.level],
        "plants": [down(p, _pos_down(H)) for p in m.plants if p.level],
        "bridges": [], "quays": []})


def _pos_down(H: float):
    def f(d):
        x, y, z = d["position"]
        d["position"] = (x, y, G.q(z - H))
    return f


def props(spec, m, build):
    """M6 on every level: the ground (no trees under a slab, lights hung from it) and each
    deck (its props and plants lifted onto it, level 1, ids `.up<n>`)."""
    from .props import Out

    if not m.decks:
        return build(spec, m)
    g = build(spec, ground_view(m))
    polys = [G.from_model_poly(dk.polygon) for dk in m.decks]
    covered = G.union(polys)
    shapely.prepare(covered)
    rows = {"props": list(g.rows["props"]),
            "plants": [p for p in g.rows["plants"]
                       if not (p["type"].split(".", 1)[1] in TREES and
                               covered.contains(Point(p["position"][:2])))],
            "green_areas": list(g.rows["green_areas"])}
    info = {"ground": g.info}
    notes = list(g.notes)
    for dk, poly in zip(m.decks, polys):
        H = dk.top_m
        inner = G.qpoly(poly.buffer(-0.3, join_style="mitre"))
        shapely.prepare(inner)
        u = build(spec, deck_view(m, dk))
        for key in ("props", "plants"):
            for p in u.rows[key]:
                x, y, z = p["position"]
                if not inner.contains(Point(x, y)):
                    continue
                head, n = p["id"].rsplit(".", 1)
                rows[key].append({**p, "id": f"{head}.up{n}", "level": 1,
                                  "position": [x, y, G.q(z + H)]})
        have = {x.id if hasattr(x, "id") else x["id"] for x in rows["green_areas"]}
        for ga in u.rows["green_areas"]:
            gid = ga.id if hasattr(ga, "id") else ga["id"]
            if gid not in have:
                d = ga.model_dump(mode="python") if hasattr(ga, "model_dump") else dict(ga)
                d["z_m"] = G.q(d.get("z_m", 0.0) + H)
                d["level"] = 1
                rows["green_areas"].append(d)
        info[dk.id] = u.info
        notes += u.notes
    return Out(rows, info, notes)


def per_level(m, run) -> list:
    """Checks run on every level (`run(view)`), their failures and notes merged by check,
    each deck's prefixed with its id."""
    if not m.decks:
        return run(m)
    out = run(ground_view(m))
    by = {c.id: c for c in out}
    for dk in m.decks:
        for c in run(deck_view(m, dk)):
            o = by.get(c.id)
            if o is None:
                by[c.id] = c
                out.append(c)
                continue
            o.failures += [f"{dk.id}: {f}" for f in c.failures]
            o.notes += [f"{dk.id}: {n}" for n in c.notes]
    return out


# ---------------------------------------------------------------------------
# Supports (after transit and tunnels)
# ---------------------------------------------------------------------------

COLUMN_R = 0.45         # round columns (octagons), 0.9 m across
COLUMN_STRIP_M = 1.2    # at a curb: the column strip of a sidewalk without a furniture zone
CLEAR_PATH_M = 1.8      # (the sidewalk's clear path it leaves, M6)
COLUMN_REACH = 0.75     # every point of a slab within this share of column_m of a column
JUNCTION_REACH = 1.3    # (over a ground street or junction: the slab spans it on girders)
CANTILEVER_M = 6.0      # (within this of its edge a slab may reach this much farther)
DOOR_GAP_M = 2.5        # columns keep this far from a door
FINE = 4                # the fill-in candidates: a grid of column_m / FINE


def _keepout(m, P):
    """Where a column may not stand under a slab: lanes, crosswalks, junctions, the
    sidewalks' clear paths, walkways off the sidewalks, doors, structures, tunnels."""
    F = G.from_model_poly
    near = P.buffer(5.0)
    out = []
    for ln in m.lanes:
        if ln.level:
            continue
        g = LineString([p[:2] for p in ln.centerline])
        if g.intersects(near):
            out.append(g.buffer(ln.width_m / 2 + 0.3, cap_style="flat"))
    for c in m.crosswalks:
        if not c.level and LineString(c.line).intersects(near):
            out.append(LineString(c.line).buffer(c.width_m / 2 + 0.5, cap_style="flat"))
    for j in m.junctions:
        if not j.level:
            jp = F(j.polygon)
            if jp.intersects(near):
                out.append(jp.buffer(0.5))
    segs = {s.id: s for s in m.road_segments}
    for w in m.sidewalks:
        if w.level or not LineString(w.line).intersects(near):
            continue
        s = segs.get(w.segment_id)
        if s is None:
            continue
        band = LineString(w.line).buffer(w.width_m / 2, cap_style="flat")
        side = s.cross_section.sidewalk_m[0]
        zone = w.furniture_m
        if zone < COLUMN_STRIP_M and side - w.curb_m - COLUMN_STRIP_M >= CLEAR_PATH_M:
            zone = COLUMN_STRIP_M     # (a column strip at the curb, the clear path kept)
        keep = s.width_m / 2 - side + w.curb_m + zone
        out.append(band.difference(LineString(s.centerline).buffer(keep, cap_style="flat")))
    for w in m.walkways:
        if w.level or w.kind == "sidewalk" or any(abs(p[2]) > 0.5 for p in w.line):
            continue
        g = LineString([p[:2] for p in w.line])
        if g.intersects(near):
            out.append(g.buffer(w.width_m / 2 + 0.3))
    for b in m.buildings:
        if b.level:
            continue
        for e in b.entrances:
            if near.contains(Point(e.position)):
                out.append(Point(e.position).buffer(DOOR_GAP_M))
    for st in m.structures:
        if st.footprint is not None and st.z0_m < 0.5:
            sp = F(st.footprint)
            if sp.intersects(near):
                out.append(sp.buffer(1.0))
        elif len(st.line) >= 2 and min(p[2] for p in st.line) < 0.5:
            g = LineString([p[:2] for p in st.line])
            if g.intersects(near):
                out.append(g.buffer(2.0))
    for t in m.tunnels:
        g = LineString([p[:2] for p in t.line])
        if g.intersects(near):
            out.append(g.buffer(t.width_m / 2 + 2.0, cap_style="flat"))
    return G.union([G.qpoly(x) for x in out if not x.is_empty])


def _grid(P, step: float, ang: float) -> list:
    """Points of a square grid (rotated by ang, from the slab's lower corner) inside P."""
    ca, sa = M.cos(ang), M.sin(ang)
    cs = [(x * ca + y * sa, -x * sa + y * ca)
          for x, y in shapely.get_coordinates(P).tolist()]
    if not cs:
        return []
    u0, u1 = min(c[0] for c in cs), max(c[0] for c in cs)
    v0, v1 = min(c[1] for c in cs), max(c[1] for c in cs)
    pts = []
    nu = int((u1 - u0) / step) + 1
    nv = int((v1 - v0) / step) + 1
    for i in range(nu + 1):
        for j in range(nv + 1):
            u = u0 + step / 2 + i * step
            v = v0 + step / 2 + j * step
            pts.append(ST._pt(u * ca - v * sa, u * sa + v * ca))
    if not pts:
        return []
    inside = shapely.contains(P, shapely.points(pts)).tolist()
    return [p for p, k in zip(pts, inside) if k]


def supports(m) -> tuple[list, list]:
    """(column rows, deck rows with their column ids): columns under every slab on a grid of
    its column_m, in the furniture zones along its streets and in the lots under it, then
    filled in where a part of the slab is farther than COLUMN_REACH x column_m from one."""
    from . import massing as MS

    cols, decks = [], []
    for dk in m.decks:
        P = G.from_model_poly(dk.polygon)
        g = float(dk.attrs.get("column_m", 18.0))
        reach = COLUMN_REACH * g
        bad = _keepout(m, P)
        inner = G.qpoly(P.buffer(-0.8, join_style="mitre"))
        # (a column's center keeps its radius off the keep-out)
        ok_zone = G.diff(inner, G.qpoly(bad.buffer(COLUMN_R + 0.05, join_style="mitre")))
        shapely.prepare(ok_zone)
        cand = []
        # along the streets under the slab: their furniture zones (or just behind the curb)
        under = {x.attrs.get("twin") for x in m.road_segments if x.attrs.get("deck") == dk.id}
        for s in m.road_segments:
            if s.level or s.attrs.get("deck") or s.id not in under:
                continue
            cs = s.cross_section
            side = cs.sidewalk_m[0]
            off = s.width_m / 2 - side + cs.curb_m + max(cs.furniture_m, COLUMN_STRIP_M) / 2
            pts = [tuple(p) for p in s.centerline]
            for sign in (1.0, -1.0):
                line = _offset_line(pts, sign * off)
                if len(line) < 2:
                    continue
                Ll = ST._plen(line)
                k = 0
                while g / 2 + k * g < Ll:
                    cand.append(ST._pt(*ST._along(line, g / 2 + k * g)[0]))
                    k += 1
        cand += _grid(inner, g, MS.obb_angle(P))
        fine = _grid(inner, g / FINE, MS.obb_angle(P))
        keep = []
        if cand:
            ok = shapely.contains(ok_zone, shapely.points(cand)).tolist()
            for p, k in zip(cand, ok):
                if k and all(ST._dist(p, q) >= g / 3 for q in keep):
                    keep.append(p)
        # fill in: every sample of the slab within reach of a column
        samples = _grid(P, 6.0, MS.obb_angle(P))
        over = span_zone(m, P)
        wide = shapely.contains(over, shapely.points(samples)).tolist() if samples and \
            not over.is_empty else [False] * len(samples)
        edge = (G.dists(P.boundary, shapely.points(samples)) <= CANTILEVER_M).tolist() \
            if samples else []
        fine_ok = [p for p, k in zip(fine, shapely.contains(ok_zone, shapely.points(fine))
                                     .tolist()) if k] if fine else []
        thin = None
        for sp, w, e in zip(samples, wide, edge):
            r = (JUNCTION_REACH * g if w else reach) + (CANTILEVER_M if e else 0.0)
            if keep and min(ST._dist(sp, q) for q in keep) <= r:
                continue
            near = [p for p in fine_ok if ST._dist(p, sp) <= reach]
            if near:
                keep.append(min(near, key=lambda p: (round(ST._dist(p, sp), 6), p)))
                continue
            # (a strip too thin for the fine grid: its nearest point, a little inside it)
            if thin is None:
                thin = G.qpoly(ok_zone.buffer(-0.1, join_style="mitre"))
            if thin.is_empty:
                continue
            q = ST._pt(*shapely.ops.nearest_points(thin, Point(sp))[0].coords[0])
            if ST._dist(q, sp) <= r - 0.1 and thin.contains(Point(q)):
                keep.append(q)
        ids = []
        oct_ = [(COLUMN_R * M.cos(M.PI * (2 * k + 1) / 8), COLUMN_R * M.sin(M.PI * (2 * k + 1) / 8))
                for k in range(8)]
        for i, (x, y) in enumerate(sorted(keep)):
            cid = f"{dk.id}.col{i + 1:04d}"
            ids.append(cid)
            cols.append({"id": cid, "type": "structure.column", "kind": "column",
                         "footprint": G.to_model_poly(Polygon([ST._pt(x + u, y + v)
                                                               for u, v in oct_])),
                         "line": [], "z0_m": 0.0, "z1_m": G.q(dk.top_m - dk.slab_m),
                         "supports": [dk.id], "attrs": {"deck": dk.id}})
        d = dk.model_dump(mode="python")
        d["column_ids"] = ids
        decks.append(d)
    return cols, decks


def span_zone(m, P):
    """The ground streets and junctions under a slab (the slab spans them on deep girders,
    from the columns at their curbs or behind their property lines)."""
    js = [G.from_model_poly(j.polygon) for j in m.junctions if not j.level]
    rs = [G.qpoly(LineString(s.centerline).buffer(s.width_m / 2, cap_style="flat"))
          for s in m.road_segments if not s.level and "deck" not in s.attrs and
          not G.apart(LineString(s.centerline), P)]
    return G.union([G.inter(x, P) for x in js + rs if x.intersects(P)])


def _offset_line(pts, d: float) -> list:
    from . import junctions as JN

    return JN._offset(pts, d)


def walk_points(line, step: float) -> list:
    """Points every `step` along a polyline (both ends), on the grid."""
    pts = [tuple(p[:2]) for p in line]
    L = ST._plen(pts)
    n = max(1, int(L / step))
    return [ST._pt(*ST._along(pts, L * k / n)[0]) for k in range(n + 1)]
