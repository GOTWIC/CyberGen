"""Barriers along the roads and round the junctions (issue #95; AG17: on M22's pavement map).

AG7 draws these barriers along a road: a highway's median barrier (a jersey on the median),
an at-grade highway's guard walls (jerseys along both edges of its carriageway), a raised
road's parapets (at the edges of its deck) and an M14 deck ramp's barriers and parapets; a
footbridge has railings or stone parapets (`structures.py`). Each is a *run*: a profile in
offsets from the centerline (`Run`), drawn over the *spans* this module gives it.

AG17: a road's faces end on its ports and never overlap another road's or a junction's (the
map tiles the pavement, `pave.py`), so a run needs no keep-outs round its junctions:

- **Spans** (`road_runs`, at gather time, so a road's inputs hold them): a run goes from cut
  to cut (where the road's faces end), less within `XWALK_CLEAR_M` of a crosswalk it would
  cross; spans under `MIN_SPAN_M` are left out.
- **Ends**, each on the road's port line at its cut (`Road.port_frame`): `join` where its
  junction carries the run on (the junction's barrier starts on the same line), `open`
  where the road goes on as another (whose run starts there), else `stop` (a jersey slopes
  down to `TOE_F` of its height over `END_M`, a ramped end; a parapet or a railing is
  closed by a cap).
- **Junctions** (`junction_plan`, at gather time for the junction and the roads at it), on
  the boundary of its faces (`_loops`), between the ports of two legs:
  - a raised junction carries a parapet along the right of way's outer edge between two
    legs one of which has parapets (its corner pads' property line, else its
    carriageway's edge), from the one leg's outer port vertex to the other's;
  - at grade, a corner between two highway legs with guard walls carries a guard wall along
    its carriageway's edge between their ports (when that runs `CORNER_MIN_M` or more);
  - a junction with exactly two median legs facing each other (`MEDIAN_ANGLE_DEG` or more
    apart), with no connector lane across the line between their ports' middles, carries
    the median across; their medians join it.
  Each junction barrier starts and ends on its legs' port lines, so it meets the legs' runs
  on the same section.

Every value handed on is rounded to the centimeter (heights to the millimeter).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import shapely

from citygen import dmath as M
from citygen import geom as G

from .. import canon as C
from .path import Path, dist, seg_cross, unit

RAISED_M = 0.5          # a junction this far over its ground stands on a slab of its own
XWALK_CLEAR_M = 1.0     # a run keeps this off a crosswalk on its road
MIN_SPAN_M = 1.0        # shorter spans are left out
END_M = 3.0             # a jersey's ramped end
TOE_F = 0.12            # ... down to this share of its height
CORNER_MIN_M = 2.0      # an at-grade corner shorter than this carries no guard wall
MEDIAN_ANGLE_DEG = 120.0
MITER_CAP = 2.0

JERSEY = [(-0.3, 0.0), (-0.3, 0.08), (-0.15, 0.33), (-0.075, 0.81), (0.075, 0.81),
          (0.15, 0.33), (0.3, 0.08), (0.3, 0.0)]
PARAPET_H = 1.05
PARAPET_W = 0.45
GUARD_IN_M = 0.35       # a guard wall's middle inside the carriageway's edge
PEDESTRIAN = ("pedestrian", "footbridge")
CURB_M = 0.15           # a parapet on a sidewalk stands this over the carriageway


@dataclass
class Run:
    """A barrier along a road: `side` l (left, +t), r (right, -t) or m (the median);
    `profile` [(t, dz)] in offsets from the centerline, as `Mesh.sweep` takes it; `base`
    over the road's surface; `jersey` (a ramped end) or a capped end."""
    name: str
    side: str
    profile: list
    base: float = 0.0
    jersey: bool = False
    slot: str = "concrete.barrier"
    edge: bool = False      # a parapet at the road's edge, carried round its junction's corner

    @property
    def t0(self) -> float:
        return min(t for t, _ in self.profile)

    @property
    def t1(self) -> float:
        return max(t for t, _ in self.profile)

    @property
    def tc(self) -> float:
        return (self.t0 + self.t1) / 2.0


def parapet_profile(t_out: float, side: str, h: float = PARAPET_H, w: float = PARAPET_W):
    """A parapet's section, its outer face at offset t_out on side l (+) or r (-)."""
    if side == "l":
        return [(t_out - w, 0.0), (t_out - w + 0.1, h), (t_out, h), (t_out, 0.0)]
    return [(-t_out, 0.0), (-t_out, h), (-t_out + w - 0.1, h), (-t_out + w, 0.0)]


def shifted(profile, tc: float) -> list:
    return [(t + tc, z) for t, z in profile]


def deck_kind(seg: dict) -> str:
    from .roads import deck_kind as dk
    return dk(seg)


def runs_of(seg: dict, cls: str) -> list[Run]:
    """The barrier runs AG7 draws along a road piece (not its footbridge railings, which the
    bridge draws: `rail_runs`)."""
    from .roads import RAMP_PARAPET_H, RAMP_PARAPET_M, RAMP_WALK_M
    cs = seg["cross_section"]
    W2 = seg["width_m"] / 2.0
    side = cs["sidewalk_m"][0]
    h = W2 if cls in PEDESTRIAN else W2 - side
    dk = deck_kind(seg)
    out: list[Run] = []
    if cls in PEDESTRIAN:
        return out
    if cls == "highway":
        if cs.get("median_m", 0.0) > 0.0:
            out.append(Run("median", "m", list(JERSEY), jersey=True))
        if dk == "none":
            for sd, sg in (("l", 1.0), ("r", -1.0)):
                out.append(Run(f"guard_{sd}", sd, shifted(JERSEY, sg * (h - GUARD_IN_M)),
                               jersey=True))
    if dk == "deck":
        sw = side if cls in ("avenue", "street") else 0.0
        base = CURB_M if sw > 0 else 0.0
        for sd in ("l", "r"):
            out.append(Run(f"parapet_{sd}", sd, parapet_profile(W2, sd), base=base,
                           edge=True))
    elif dk == "ramp":
        wi, wo = W2 + RAMP_WALK_M, W2 + RAMP_WALK_M + RAMP_PARAPET_M
        top = RAMP_PARAPET_H
        for sd, sg in (("l", 1.0), ("r", -1.0)):
            out.append(Run(f"ramp_barrier_{sd}", sd, parapet_profile(W2, sd)))
            prof = [(wi, 0.0), (wi, top), (wo, top), (wo, 0.0)] if sd == "l" else \
                [(-wo, 0.0), (-wo, top), (-wi, top), (-wi, 0.0)]
            out.append(Run(f"ramp_parapet_{sd}", sd, prof, base=0.15))
    return out


def rail_runs(seg: dict, kind: str) -> list[Run]:
    """A footbridge's railings (steel) or stone parapets, as runs."""
    W2 = seg["width_m"] / 2.0
    if kind == "footbridge.stone":
        return [Run("stone_l", "l", [(W2 - 0.3, 0.0), (W2 - 0.3, 0.95), (W2, 0.95), (W2, 0.0)],
                    slot="stone.coping"),
                Run("stone_r", "r", [(-W2, 0.0), (-W2, 0.95), (-W2 + 0.3, 0.95),
                                     (-W2 + 0.3, 0.0)], slot="stone.coping")]
    return [Run("rail_l", "l", [(W2 - 0.09, 0.0), (W2 - 0.09, 1.1), (W2 - 0.01, 1.1),
                                (W2 - 0.01, 0.0)], slot="steel.painted"),
            Run("rail_r", "r", [(-W2 + 0.01, 0.0), (-W2 + 0.01, 1.1), (-W2 + 0.09, 1.1),
                                (-W2 + 0.09, 0.0)], slot="steel.painted")]


# ---------------------------------------------------------------------------
# Junctions
# ---------------------------------------------------------------------------

def leg_key(sid: str, at_start: bool) -> str:
    return f"{sid}@{'s' if at_start else 'e'}"


def _kinds(s) -> dict:
    """Which barriers a road has at its edges and on its median (as `runs_of`)."""
    from .roads import deck_kind as dk_of
    from .roads import street_class
    seg = s.model_dump(mode="json", exclude_none=True)
    cls = street_class(s)
    dk = dk_of(seg)
    return {"guard": cls == "highway" and dk == "none",
            "parapet": dk == "deck" and cls not in PEDESTRIAN,
            "median": cls == "highway" and s.cross_section.median_m > 0.0}


def _segs(PI, fid: str) -> list[tuple[str, str, str]]:
    """A face's ring segments (vertex a, vertex b, edge id), every ring in turn."""
    out = []
    for refs in PI.F[fid].rings:
        ids = PI.ring(refs)
        n = len(ids)
        k = 0
        for ref in refs:
            eid = ref.lstrip("-")
            for _ in range(len(PI.E[eid][1]) - 1):
                out.append((ids[k % n], ids[(k + 1) % n], eid))
                k += 1
    return out


def _loops(PI, fids: list[str]) -> list[list[tuple[str, str, str]]]:
    """The boundary of the union of some faces: loops of directed segments (a, b, edge id)
    whose reverse is no segment of another of them (counterclockwise round the outside)."""
    segs: dict = {}
    for fid in fids:
        for a, b, eid in _segs(PI, fid):
            segs[(a, b)] = eid
    bd = {k: v for k, v in segs.items() if (k[1], k[0]) not in segs}
    nxt: dict = defaultdict(list)
    for a, b in sorted(bd):
        nxt[a].append(b)
    used: set = set()
    loops = []
    for st in sorted(bd):
        if st in used:
            continue
        loop = []
        e = st
        while e not in used:
            used.add(e)
            loop.append((e[0], e[1], bd[e]))
            cand = sorted(b for b in nxt[e[1]] if (e[1], b) not in used)
            if not cand:
                break
            e = (e[1], cand[0])
        loops.append(loop)
    return loops


def _leg_info(cx, j) -> dict:
    """A junction's legs by key: road, at its start, path, port line at that end, kinds."""
    from .roads import port_lines
    out = {}
    for s, at_start in cx.legs_of(j):
        try:
            path = Path(s.centerline)
        except ValueError:
            continue
        cuts = list(cx.cuts.get(s.id, (0.0, 0.0)))
        pl = port_lines(cx, s, path, cuts).get("start" if at_start else "end")
        out[leg_key(s.id, at_start)] = {"seg": s, "at_start": at_start, "path": path,
                                        "cut": cuts[0] if at_start else path.L - cuts[1],
                                        "port": pl, "kinds": _kinds(s)}
    return out


def _label(cx, j, PI, legs: dict, S: set, a: str, b: str, eid: str) -> str:
    """What lies across a boundary segment of a junction's faces S: a leg (its key), `out`
    (nothing: the right of way's edge), `pad` (the junction's own faces not in S), or
    `other`."""
    others = [g for g in PI.edge_faces.get(eid, ()) if g not in S]
    if not others:
        return "out"
    owner = PI.F[others[0]].owner_id
    if owner == j.id:
        return "pad"
    cand = [k for k, lg in legs.items() if lg["seg"].id == owner]
    if not cand:
        return "other"
    if len(cand) == 1:
        return cand[0]
    # (a road with both ends at the junction: the end whose cut is nearer the segment)
    x = (PI.V[a][0] + PI.V[b][0]) / 2000.0
    y = (PI.V[a][1] + PI.V[b][1]) / 2000.0
    return min(cand, key=lambda k: (abs(legs[k]["path"].project(x, y)[0] - legs[k]["cut"]),
                                    k))


def _side(lg: dict, x: float, y: float) -> str:
    _, t = lg["path"].project(x, y)
    return "l" if t > 0 else "r"


def _port_frame(lg: dict, v, W: float):
    """A junction barrier's frame at a leg's outer port vertex v (x, y mm): inward along
    the port line, stretched as the leg's runs are (`Road.port_frame`)."""
    pl = lg["port"]
    if not pl:
        return None
    R, Lp = pl
    x, y = v[0] / 1000.0, v[1] / 1000.0
    dR, dL = dist((x, y), R), dist((x, y), Lp)
    far = R if dL < dR else Lp
    dx, dy = far[0] - x, far[1] - y
    n = math.sqrt(dx * dx + dy * dy)
    if n < 1e-6:
        return None
    k = dist(R, Lp) / W
    return [C.m2(x), C.m2(y), round(dx / n, 6), round(dy / n, 6), round(k, 6)]


def junction_plan(cx, j) -> dict:
    """What a junction draws between its legs and which of its legs' runs join it:
    {"raised", "corners": [{"a", "b", "kind", "pts": [[x, y, top]] (millimeters, its
    faces' boundary), "ends": [frame | None, frame | None]}], "median": {"a", "b", "pts",
    "ends"} | None, "joins": {leg key: {"l", "r", "m"}}} (sides as the road sees them: l
    its +t side). Cached on the context."""
    cache = cx.__dict__.setdefault("_barrier_plans", {})
    if j.id in cache:
        return cache[j.id]
    PI = cx.pave
    legs = _leg_info(cx, j)
    fids = PI.faces_of(j.id) if PI.on else []
    raised = bool(fids) and not j.level and any(
        PI.V[v][3] > RAISED_M * 1000 for f in fids for r in PI.rings(f) for v in r)
    joins = {k: {"l": False, "r": False, "m": False} for k in legs}
    corners = []
    got_lanes: list = []

    def lanes():
        if not got_lanes:
            got_lanes.append(_lane_corridors(cx, j))
        return got_lanes[0]
    if fids and len(legs) >= 1 and j.shape != "cul_de_sac":
        tops = [f for f in fids if PI.cls[f] == "top"]
        for kind, S in (("parapet", fids), ("guard", tops)):
            if (kind == "parapet") != raised or not S:
                continue
            Sset = set(S)
            for loop in _loops(PI, S):
                lab = [_label(cx, j, PI, legs, Sset, a, b, e) for a, b, e in loop]
                n = len(loop)
                at_leg = [i for i in range(n) if lab[i] in legs]
                if not at_leg:
                    continue
                for i in at_leg:
                    if lab[(i + 1) % n] in legs:
                        continue
                    # the run after leg segment i up to the next leg segment
                    run = []
                    k = (i + 1) % n
                    while lab[k] not in legs and len(run) < n:
                        run.append(k)
                        k = (k + 1) % n
                    A, B = lab[i], lab[k]
                    ka, kb = legs[A]["kinds"], legs[B]["kinds"]
                    if kind == "parapet" and not (ka["parapet"] or kb["parapet"]):
                        continue
                    if kind == "guard" and not (ka["guard"] and kb["guard"]):
                        continue
                    # (its stretches along the edge: outer edges, and for a guard wall the
                    # carriageway's curbs; never along another road or junction)
                    ok = ("out",) if kind == "parapet" else ("out", "pad")
                    pieces, cur = [], []
                    for q in run:
                        if lab[q] in ok:
                            cur.append(q)
                        elif cur:
                            pieces.append(cur)
                            cur = []
                    if cur:
                        pieces.append(cur)
                    reach = PARAPET_W if kind == "parapet" else GUARD_IN_M + 0.3
                    for pc in pieces:
                        vs = [loop[pc[0]][0]] + [loop[q][1] for q in pc]
                        whole = [[PI.V[v][0], PI.V[v][1], _top_of(PI, S, v)] for v in vs]
                        for pts, at0, at1 in _off_lanes(whole, lanes(), reach):
                            L = sum(math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)
                                    for a, b in zip(pts, pts[1:])) / 1000.0
                            if L < (CORNER_MIN_M if kind == "guard" else 0.05):
                                continue
                            first = pc[0] == run[0] and at0
                            last = pc[-1] == run[-1] and at1
                            _corner(corners, joins, legs, A, B, kind, ka, kb, pts, first, last)
    median = _median_across(cx, j, PI, legs, fids)
    if median is not None:
        joins[median["a"]]["m"] = True
        joins[median["b"]]["m"] = True
    out = {"raised": raised, "corners": corners, "median": median, "joins": joins}
    cache[j.id] = out
    return out


def _corner(corners, joins, legs, A, B, kind, ka, kb, pts, first, last) -> None:
    """A corner barrier along pts (millimeters), on its legs' port lines where it reaches
    them (first, last); the legs' runs on those sides join it."""
    lga, lgb = legs[A], legs[B]
    fa = _port_frame(lga, pts[0], lga["seg"].width_m) if first else None
    fb = _port_frame(lgb, pts[-1], lgb["seg"].width_m) if last else None
    corners.append({"a": A, "b": B, "kind": kind, "pts": pts, "ends": [fa, fb]})
    if first and ka[kind]:
        joins[A][_side(lga, pts[0][0] / 1000.0, pts[0][1] / 1000.0)] = True
    if last and kb[kind]:
        joins[B][_side(lgb, pts[-1][0] / 1000.0, pts[-1][1] / 1000.0)] = True


LANE_IN_M = 0.1         # a junction's barrier keeps out of its connector lanes but this
                        # (AG14's check: within the lane's half width less `INSET_M`)


def _lane_corridors(cx, j):
    """The junction's connector lanes as corridors (half their width less `LANE_IN_M`),
    one shape (meters), or None."""
    gs = []
    for n in cx.nodes_of(j):
        for ln in sorted(_connectors(cx, n), key=lambda ln: ln.id):
            if len(ln.centerline) < 2:
                continue
            h = ln.width_m / 2.0 - LANE_IN_M
            if h <= 0.1:
                continue
            gs.append(shapely.LineString([(p[0], p[1]) for p in ln.centerline]).buffer(
                h, cap_style="flat"))
    if not gs:
        return None
    with G.canonical():
        return G.union([G.qpoly(g) for g in gs])


def _off_lanes(pts, corr, reach: float) -> list:
    """A junction barrier's chain (points in millimeters) less where its section (`reach`
    to the left of travel) would stand in a connector lane's corridor: [(points, reaches
    its first point, reaches its last)], the cut ends on the chain at 1 mm."""
    if corr is None or len(pts) < 2:
        return [(pts, True, True)]
    line = shapely.LineString([(p[0] / 1000.0, p[1] / 1000.0) for p in pts])
    if line.length < 0.01:
        return [(pts, True, True)]
    strip = line.buffer(reach, single_sided=True)
    hit = shapely.intersection(strip, corr)
    if hit.is_empty or hit.area < 0.005:
        return [(pts, True, True)]
    cut = []
    for g in shapely.get_parts(hit):
        if g.geom_type != "Polygon" or g.area < 0.005:
            continue
        ds = [line.project(shapely.Point(c)) for c in g.exterior.coords]
        cut.append((min(ds), max(ds)))
    if not cut:
        return [(pts, True, True)]
    cut.sort()
    keep, at = [], 0.0
    for a, b in cut:
        if a > at:
            keep.append((at, a))
        at = max(at, b)
    if at < line.length:
        keep.append((at, line.length))
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) / 1000.0)

    def at_d(d):
        for k in range(len(pts) - 1):
            if cum[k] <= d <= cum[k + 1]:
                f = 0.0 if cum[k + 1] == cum[k] else (d - cum[k]) / (cum[k + 1] - cum[k])
                a, b = pts[k], pts[k + 1]
                return [int(round(a[0] + (b[0] - a[0]) * f)), int(round(a[1] + (b[1] - a[1]) * f)),
                        int(round(a[2] + (b[2] - a[2]) * f))]
        return list(pts[-1])
    out = []
    for a, b in keep:
        if b - a < 0.05:
            continue
        inner = [list(p) for k, p in enumerate(pts) if a + 1e-6 < cum[k] < b - 1e-6]
        part = [at_d(a) if a > 1e-6 else list(pts[0])] + inner + \
            [at_d(b) if b < line.length - 1e-6 else list(pts[-1])]
        out.append((part, a <= 1e-6, b >= line.length - 1e-6))
    return out


def _top_of(PI, S, v: str) -> int:
    """A vertex's drawn height on the faces S (the highest of their lifts there)."""
    best = None
    for f in S:
        for r in PI.rings(f):
            if v in r:
                t = PI.top(f, v)
                best = t if best is None else max(best, t)
                break
    return best if best is not None else PI.V[v][2]


def _median_across(cx, j, PI, legs: dict, fids) -> dict | None:
    """Two median legs facing each other: a median barrier between the middles of their
    ports, where no connector lane crosses it and it stays on the junction's carriageway."""
    med = [k for k in sorted(legs) if legs[k]["kinds"]["median"] and legs[k]["port"]]
    if len(med) != 2 or not fids:
        return None
    A, B = (legs[k] for k in med)
    pa = [(A["port"][0][0] + A["port"][1][0]) / 2.0, (A["port"][0][1] + A["port"][1][1]) / 2.0]
    pb = [(B["port"][0][0] + B["port"][1][0]) / 2.0, (B["port"][0][1] + B["port"][1][1]) / 2.0]
    da, db = _leg_dir(A), _leg_dir(B)
    if da[0] * db[0] + da[1] * db[1] > M.cos(M.radians(MEDIAN_ANGLE_DEG)):
        return None
    if not all(_clear_of_connectors(cx, n, pa, pb) for n in cx.nodes_of(j)):
        return None
    import shapely
    tops = [f for f in fids if PI.cls[f] == "top"]
    polys = []
    for f in tops:
        rs = PI.rings(f)
        polys.append(shapely.Polygon([(PI.V[v][0] / 1000.0, PI.V[v][1] / 1000.0) for v in rs[0]],
                                     [[(PI.V[v][0] / 1000.0, PI.V[v][1] / 1000.0) for v in h]
                                      for h in rs[1:]]))
    if not polys:
        return None
    area = shapely.union_all([p if p.is_valid else shapely.make_valid(p) for p in polys])
    ln = shapely.LineString([pa, pb])
    if ln.length < 0.5 or shapely.difference(ln, area.buffer(0.01)).length > 0.05:
        return None
    ends = []
    for lg, p in ((A, pa), (B, pb)):
        R, Lp = lg["port"]
        dx, dy = Lp[0] - R[0], Lp[1] - R[1]
        n = math.sqrt(dx * dx + dy * dy)
        k = n / lg["seg"].width_m
        ends.append([C.m2(p[0]), C.m2(p[1]), round(dx / n, 6), round(dy / n, 6), round(k, 6)])
    return {"a": med[0], "b": med[1], "pts": [[C.m2(pa[0]), C.m2(pa[1])],
                                              [C.m2(pb[0]), C.m2(pb[1])]], "ends": ends}


def _leg_dir(lg: dict) -> tuple[float, float]:
    """A leg's direction away from its junction (min(10 m, half of it) from its cut)."""
    P = lg["path"]
    c = lg["cut"]
    d = min(10.0, P.L / 2.0)
    if lg["at_start"]:
        a, b = P.point(c), P.point(min(c + d, P.L))
    else:
        a, b = P.point(c), P.point(max(c - d, 0.0))
    return unit(b[0] - a[0], b[1] - a[1])


def _connectors(cx, node_id: str) -> list:
    cache = cx.__dict__.get("_connectors_at")
    if cache is None:
        cache = {}
        for ln in cx.m.lanes:
            if ln.kind == "connector" and ln.node_id:
                cache.setdefault(ln.node_id, []).append(ln)
        cx._connectors_at = cache
    return cache.get(node_id, [])


def _clear_of_connectors(cx, node_id: str, a, b) -> bool:
    """No connector lane through the node crosses the segment a-b (away from its ends)."""
    L = dist(a, b)
    if L < 0.5:
        return False
    for ln in _connectors(cx, node_id):
        pts = [(p[0], p[1]) for p in ln.centerline]
        for p, q in zip(pts, pts[1:]):
            c = seg_cross(a, b, p, q)
            if c is not None and 0.3 / L < c[0] < 1.0 - 0.3 / L:
                return False
    return True


# ---------------------------------------------------------------------------
# A road's runs and their spans
# ---------------------------------------------------------------------------

def road_runs(cx, s, inputs: dict, runs: list[Run] | None = None,
              by: set | None = None) -> list[dict]:
    """The spans of a road's barrier runs: [{"name", "spans": [[a, b, end_a, end_b]]}] with
    ends `join`, `open` or `stop` (module docstring), between its cuts."""
    if runs is None:
        runs = runs_of(inputs["seg"], inputs["cls"])
    if not runs:
        return []
    try:
        P = Path(s.centerline)
    except ValueError:
        return []
    cuts = inputs.get("cuts") or list(cx.cuts.get(s.id, (0.0, 0.0)))
    s0, s1 = cuts[0], P.L - cuts[1]
    if s1 - s0 < MIN_SPAN_M:
        return []
    by = set() if by is None else by
    joins = {}
    for at, nid in (("start", s.start), ("end", s.end)):
        j = cx.junction_at.get(nid)
        if j is not None:
            plan = junction_plan(cx, j)
            joins[at] = plan["joins"].get(leg_key(s.id, at == "start"), {})
            by.add(j.id)
        else:
            on = [o for o in cx.seg_at_node.get(nid, ()) if o.id != s.id]
            joins[at] = "open" if on else None
    xws = []
    for c in sorted(cx.cross_on.get(s.id, ()), key=lambda c: c.id):
        if len(c.line) < 2:
            continue
        a, b = c.line[0], c.line[-1]
        ln = shapely.LineString([(a[0], a[1]), (b[0], b[1])])
        if ln.length >= 0.5:
            xws.append(ln.buffer(c.width_m / 2.0 + XWALK_CLEAR_M, cap_style="flat"))
            by.add(c.id)
    own = _faces_union(cx, s.id)
    out = []
    for run in runs:
        holes = _holes(P, run, s0, s1, own, xws)
        spans, cur = [], s0
        for a, b in holes:
            if a > cur:
                spans.append((cur, min(a, s1)))
            cur = max(cur, b)
        if cur < s1:
            spans.append((cur, s1))
        rows = []
        for a, b in spans:
            if b - a < MIN_SPAN_M:
                continue
            ends = []
            for at, sv in (("start", a), ("end", b)):
                if abs(sv - (s0 if at == "start" else s1)) > 1e-6:
                    ends.append("stop")
                    continue
                jn = joins[at]
                if jn == "open":
                    ends.append("open")
                elif isinstance(jn, dict) and jn.get(run.side if run.side != "m" else "m"):
                    ends.append("join")
                else:
                    ends.append("stop")
            rows.append([C.m(a), C.m(b), ends[0], ends[1]])
        if rows:
            out.append({"name": run.name, "spans": rows})
    return out


BAND_STEP_M = 2.0       # stations of the band a run's holes are found on
OWN_PAD_M = 0.08        # a run stands on its road's faces within this (the map's mitres and
                        # the run's own differ by millimeters; AG14's check allows 0.1 m)


def _faces_union(cx, sid: str):
    """The union of a road's faces of the map (all of them: its sidewalk bands too), meters,
    grown by `OWN_PAD_M`; None without any."""
    PI = cx.pave
    if not PI.on:
        return None
    gs = []
    for fid in PI.faces_of(sid):
        rs = PI.rings(fid)
        if not rs or len(rs[0]) < 3:
            continue
        g = shapely.Polygon([(PI.V[v][0] / 1000.0, PI.V[v][1] / 1000.0) for v in rs[0]],
                            [[(PI.V[v][0] / 1000.0, PI.V[v][1] / 1000.0) for v in h]
                             for h in rs[1:] if len(h) >= 3])
        gs.append(g if g.is_valid else shapely.make_valid(g))
    if not gs:
        return None
    with G.canonical():
        return G.qpoly(G.union([G.qpoly(g) for g in gs]).buffer(OWN_PAD_M))


def _band(P: Path, t0: float, t1: float, s0: float, s1: float):
    """The plan strip of offsets t0..t1 from s0 to s1 (mitred at the path's vertices, as a
    run is swept), shapely."""
    left, right = [], []
    for s, vi in P.stations(s0, s1, BAND_STEP_M):
        x, y, nx, ny, k = P.frame(s, vi)
        right.append((x + nx * k * t0, y + ny * k * t0))
        left.append((x + nx * k * t1, y + ny * k * t1))
    g = shapely.Polygon(right + left[::-1])
    return g if g.is_valid else shapely.make_valid(g)


def _holes(P: Path, run: Run, s0: float, s1: float, own, xws) -> list:
    """Stretches [a, b] of a run that would stand off its road's own faces (where M22 cut
    them at a seam with another road) or within `XWALK_CLEAR_M` of a crosswalk."""
    band = _band(P, run.t0, run.t1, s0, s1)
    if band.is_empty:
        return []
    bad = []
    with G.canonical():
        if own is not None:
            bad.append(G.diff(G.qpoly(band), own))
        for x in xws:
            bad.append(G.inter(G.qpoly(band), G.qpoly(x)))
        out = []
        for g in bad:
            for p in G.parts(g):
                if p.area < 0.01:
                    continue
                ss = [P.project(x, y)[0] for x, y in p.exterior.coords]
                out.append((max(min(ss), s0), min(max(ss), s1)))
    return sorted(out)


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _port_z(rd, at: str, run: Run) -> float | None:
    """A run's height on a port (meters): the port's outer vertex on the run's side (its
    middle for a median), over sea level, plus the carriageway's lift and the run's base."""
    pl = rd.ports.get(at)
    if not pl or len(pl[0]) < 3:
        return None
    R, Lp = pl
    if run.side == "l":
        z = Lp[2]
    elif run.side == "r":
        z = R[2]
    else:
        z = (R[2] + Lp[2]) / 2.0
    from .roads import ROAD_DZ
    return z + ROAD_DZ + run.base


def draw_run(mesh, rd, run: Run, spans: list, step: float = 6.0):
    """A run over its spans, with its ends (`join`, `stop`, `open`), each end on the port
    line where it is at the road's cut."""
    for a, b, ea, eb in spans:
        if b - a < 0.05:
            continue
        extra = []
        L = b - a
        ramp = min(END_M, L / 2.0) if run.jersey else 0.0
        if run.jersey:
            for sgn, e, s_ in ((1.0, ea, a), (-1.0, eb, b)):
                if e == "stop":
                    k = 0.5
                    while k < ramp:
                        extra.append(s_ + sgn * k)
                        k += 0.5
                    extra.append(s_ + sgn * ramp)
        frames, scales = [], []
        tc = run.tc
        for s, vi in rd.path.stations(a, b, step, extra + rd.knots(a, b)):
            x, y, nx, ny, k = rd.path.frame(s, vi)
            z = rd.zxy(x + nx * k * tc, y + ny * k * tc) + run.base
            frames.append((x, y, z, nx, ny, k, s))
            f = 1.0
            if run.jersey:
                if ea == "stop" and s - a < ramp:
                    f = min(f, TOE_F + (1.0 - TOE_F) * (s - a) / ramp)
                if eb == "stop" and b - s < ramp:
                    f = min(f, TOE_F + (1.0 - TOE_F) * (b - s) / ramp)
            scales.append(f)
        if len(frames) < 2:
            continue
        # (on the port line where the run reaches the road's cut)
        for idx, at, s_ in ((0, "start", a), (-1, "end", b)):
            if abs(s_ - (rd.s0 if at == "start" else rd.s1)) > 0.01:
                continue
            z = _port_z(rd, at, run)
            fr = rd.port_frame(at, frames[idx][2] if z is None else z)
            if fr is not None:
                frames[idx] = fr
        mesh.sweep(run.slot, frames, run.profile, zscale=scales)
        for idx, e, out in ((0, ea, -1.0), (-1, eb, 1.0)):
            if e == "stop":
                cap(mesh, run.slot, frames[idx], run.profile, scales[idx], out)


def chain_frames(pts, base: float = 0.0, ends=(None, None)) -> list:
    """Frames along a plan polyline of [x, y, z] (meters): mitred at its vertices, the
    given end frames ([x, y, nx, ny, k]: a port line) at its ends, z each point's plus
    base."""
    P = [(float(p[0]), float(p[1])) for p in pts]
    n = len(P)
    if n < 2:
        return []
    dirs = []
    for a, b in zip(P, P[1:]):
        dirs.append(unit(b[0] - a[0], b[1] - a[1]))
    frames = []
    s = 0.0
    for i in range(n):
        if i > 0:
            s += dist(P[i - 1], P[i])
        if i == 0:
            d0 = d1 = dirs[0]
        elif i == n - 1:
            d0 = d1 = dirs[-1]
        else:
            d0, d1 = dirs[i - 1], dirs[i]
        nx, ny = -(d0[1] + d1[1]), d0[0] + d1[0]
        L = math.sqrt(nx * nx + ny * ny)
        if L < 1e-9:
            nx, ny, k = -d1[1], d1[0], 1.0
        else:
            nx, ny = nx / L, ny / L
            c = nx * -d1[1] + ny * d1[0]
            k = 1.0 / max(c, 1.0 / MITER_CAP)
        frames.append((P[i][0], P[i][1], float(pts[i][2]) + base, nx, ny, k, s))
    for idx, e in ((0, ends[0]), (-1, ends[1])):
        if e is None:
            continue
        x, y, ex, ey, k = e
        # (the profile's t to the left of travel: the port line's direction that way)
        fx, fy = frames[idx][3], frames[idx][4]
        if ex * fx + ey * fy < 0.0:
            ex, ey = -ex, -ey
        if ex * fx + ey * fy < 0.2:
            continue        # (a port line along the run: keep the mitre)
        frames[idx] = (x, y, frames[idx][2], ex, ey, k, frames[idx][6])
    return frames


def draw_chain(mesh, slot: str, pts, profile, base: float = 0.0, ends=(None, None)):
    """A barrier along a junction's edge (points [x, y, z] in meters), its section's t to
    the left of travel; capped at an end that is not on a port line, and split (each part
    capped) where the edge turns back more than `SHARP_DEG` (a notch in a junction's
    outline: a section swept round it would fold through itself)."""
    for part, e in _split_sharp(pts, ends):
        frames = chain_frames(part, base, e)
        if len(frames) < 2:
            continue
        mesh.sweep(slot, frames, profile)
        for idx, ee, out in ((0, e[0], -1.0), (-1, e[1], 1.0)):
            if ee is None:
                cap(mesh, slot, frames[idx], profile, 1.0, out)


SHARP_DEG = 120.0


def _split_sharp(pts, ends) -> list:
    P = []
    for p in pts:
        if not P or dist(P[-1], p) > 0.002:
            P.append(p)
    if len(P) < 2:
        return []
    c_lim = M.cos(M.radians(SHARP_DEG))
    # (and at a vertex the edge passes twice: a region pinched at a point)
    seen: dict = {}
    for p in P:
        k = (round(p[0], 3), round(p[1], 3))
        seen[k] = seen.get(k, 0) + 1
    out, cur, e0 = [], [P[0]], ends[0]
    for i in range(1, len(P) - 1):
        cur.append(P[i])
        d0 = unit(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1])
        d1 = unit(P[i + 1][0] - P[i][0], P[i + 1][1] - P[i][1])
        twice = seen[(round(P[i][0], 3), round(P[i][1], 3))] > 1
        if twice or d0[0] * d1[0] + d0[1] * d1[1] < c_lim:
            # (each part 1 cm short of the turn: their caps never share an edge)
            q = P[i]
            cur[-1] = [q[0] - d0[0] * 0.01, q[1] - d0[1] * 0.01, q[2]]
            out.append((cur, (e0, None)))
            cur, e0 = [[q[0] + d1[0] * 0.01, q[1] + d1[1] * 0.01, q[2]]], None
    cur.append(P[-1])
    out.append((cur, (e0, ends[1])))
    return out


def end_frame(rd, s: float, base: float = 0.0):
    """The plain (square) frame of a road at s, base over its surface."""
    x, y, nx, ny, k = rd.path.frame(s)
    return (x, y, rd.z(s) + base, nx, ny, k, s)


def cap(mesh, slot: str, frame, profile, f: float, out: float):
    """Close a run's end: the section (scaled by f in height) at a frame, facing along
    (out 1) or against (out -1) the direction of travel."""
    x, y, z, nx, ny, k, _ = frame
    ring = [(t, dz * f) for t, dz in profile]
    if len(ring) < 3:
        return
    area = 0.0
    for i in range(len(ring)):
        (a0, b0), (a1, b1) = ring[i], ring[(i + 1) % len(ring)]
        area += a0 * b1 - a1 * b0
    if abs(area) < 1e-6:
        return
    # (the triangulation turns every ring counterclockwise in (u, v); with u along the
    # section's t and v up the cap faces along travel, (ny, -nx); a cap facing back takes
    # u = -t)
    face = (ny * out, -nx * out, 0.0)
    sg = 1.0 if out > 0 else -1.0
    ring = [(sg * u, v) for u, v in ring]
    mesh.poly_map(slot, ring, (),
                  lambda u, v: (x + nx * k * sg * u, y + ny * k * sg * u, z + v),
                  expect=face)


__all__ = ["Run", "runs_of", "rail_runs", "junction_plan", "road_runs", "draw_run",
           "draw_chain", "chain_frames", "end_frame", "cap", "JERSEY", "PARAPET_H",
           "PARAPET_W", "leg_key", "parapet_profile", "shifted"]
