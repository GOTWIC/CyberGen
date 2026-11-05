"""Where a road's barriers end, and what a junction draws between its legs (issue #95).

AG7 draws these barriers along a road: a highway's median barrier (a jersey on the median),
an at-grade highway's guard walls (jerseys along both edges of its carriageway), a raised
road's parapets (at the edges of its deck) and an M14 deck ramp's barriers and parapets; a
footbridge has railings or stone parapets (`structures.py`). Each is a *run*: a profile in
offsets from the centerline (`Run`), drawn over the *spans* this module gives it.

- **Spans** (`road_runs`, at gather time, so a road's inputs hold them): a run goes from
  cut to cut (the junctions' cut edges at the road's ends), less where it would come
  within `CLEAR_M` of a junction at its ends (unless that junction carries it on), of the
  carriageway of another road at those nodes (a gore, an acute corner), or within
  `XWALK_CLEAR_M` of a crosswalk on its road; spans under `MIN_SPAN_M` are left out.
- **Ends**: `join` where the junction carries the run on (the run ends on the junction's
  cut edge, `cut_frame`, the junction's barrier starting there); `stop` (a terminal: a
  jersey slopes down to `TOE_F` of its height over `END_M`, a ramped end; a parapet or a
  railing is closed by a cap); `open` at a node with no junction (the next road's run goes
  on from there).
- **A raised road's parapets** end at the corner of their junction: on the cut edge's
  corner where the road has no sidewalk, else where its sidewalk ends on its property line
  (the start of the junction's corner pad, as `walks._corners` finds it). Where the road
  meets another road's carriageway first, there.
- **Junctions** (`junction_plan`, at gather time for the junction and the roads at it):
  - a raised junction (its node over `RAISED_M`, on a slab of its own) carries a parapet
    round each corner between two legs one of which has parapets: along the corner's
    sidewalk pad (its property line) where the junction draws one, else along its outline;
  - at grade, a corner between two highway legs with guard walls carries a guard wall
    along its outline (when that runs `CORNER_MIN_M` or more);
  - a junction with exactly two median legs facing each other (`MEDIAN_ANGLE_DEG` or more
    apart), with no connector lane across the line between their medians' ends, carries
    the median across (`median`); their medians join it.
  The road sides that face a corner barrier, and the medians of a link, end as `join`.

Every decision is plain arithmetic on the model's coordinates or an overlay on citygen's
1 cm grid (`geom.canonical`), and every value handed on is rounded to the centimeter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import shapely
from shapely.ops import nearest_points, substring

from citygen import dmath as M
from citygen import geom as G

from .. import canon as C
from .kit import ccw
from .path import Path, dist, first_exit, seg_cross, unit

RAISED_M = 0.5          # a junction's node over this stands on a slab of its own
CLEAR_M = 0.15          # a barrier keeps this off another road's carriageway, a junction
XWALK_CLEAR_M = 1.0     # ... and this off a crosswalk on its road
MIN_SPAN_M = 1.0        # shorter spans are left out
END_M = 3.0             # a jersey's ramped end
TOE_F = 0.12            # ... down to this share of its height
CORNER_MIN_M = 2.0      # an at-grade corner shorter than this carries no guard wall
MEDIAN_ANGLE_DEG = 120.0
BAND_STEP_M = 2.0       # stations of the band a run's spans are found on
NEAR_M = 30.0           # what a junction's barriers look out for round it
Z_NEAR_M = 2.5          # ... at its height (roads and junctions over or under it are not)
SIDE_REACH_M = 20.0     # a road's barriers look this far beside it for other roads

JERSEY = [(-0.3, 0.0), (-0.3, 0.08), (-0.15, 0.33), (-0.075, 0.81), (0.075, 0.81),
          (0.15, 0.33), (0.3, 0.08), (0.3, 0.0)]
PARAPET_H = 1.05
PARAPET_W = 0.45
GUARD_IN_M = 0.35       # a guard wall's middle inside the carriageway's edge
PEDESTRIAN = ("pedestrian", "footbridge")


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
    edge: bool = False      # a parapet at the road's edge, ending at its junction's corner

    @property
    def t0(self) -> float:
        return min(t for t, _ in self.profile)

    @property
    def t1(self) -> float:
        return max(t for t, _ in self.profile)


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
        base = 0.15 if sw > 0 else 0.0
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

def _leg_dir(pts, P) -> tuple[float, float]:
    """M2's leg direction (as `walks._leg_dir`)."""
    path = Path(pts)
    q = path.point(min(10.0, path.L / 2.0))
    return unit(q[0] - P[0], q[1] - P[1])


def leg_key(sid: str, at_start: bool) -> str:
    return f"{sid}@{'s' if at_start else 'e'}"


def _legs(cx, j) -> tuple[list, list[dict]]:
    """A junction's ring (counterclockwise) and its legs in `walks.make_junction`'s order:
    {key, seg, at_start, d, exit, ang}."""
    ring = ccw(j.polygon.exterior)
    node = cx.node.get(j.node_id)
    if node is not None:
        P = (node.position[0], node.position[1])
    else:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        P = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
    legs = []
    for s in sorted(cx.seg_at_node.get(j.node_id, ()), key=lambda s: s.id):
        for at_start in ((True, False) if s.start == s.end else (s.start == j.node_id,)):
            pts = s.centerline if at_start else s.centerline[::-1]
            try:
                path = Path(pts)
            except ValueError:
                continue
            d = _leg_dir(path.p, P)
            from .roads import street_class
            cls = street_class(s)
            h = s.width_m / 2.0 if cls in PEDESTRIAN else (
                s.width_m / 2.0 - s.cross_section.sidewalk_m[0])
            legs.append({"key": leg_key(s.id, at_start), "seg": s, "at_start": at_start,
                         "d": d, "exit": first_exit(path.p, ring), "path": path, "h": h,
                         "ang": M.atan2(d[1], d[0]), "id": s.id})
    legs.sort(key=lambda r: (r["ang"], r["id"]))
    return ring, legs


def _kinds(s) -> dict:
    """Which barriers a road has at its edges and on its median (as `runs_of`)."""
    from .roads import deck_kind as dk_of
    from .roads import street_class
    seg = s.model_dump(mode="json", exclude_none=True)
    cls = street_class(s)
    dk = dk_of(seg)
    return {"guard": cls == "highway" and dk == "none",
            "parapet": dk == "deck" and cls not in PEDESTRIAN,
            "median": cls == "highway" and s.cross_section.median_m > 0.0,
            "sidewalk": s.cross_section.sidewalk_m[0] > 0.0 and cls not in PEDESTRIAN}


def _chain(ring, ea: int, eb: int) -> list | None:
    """The outline between two legs' exit edges: ring[ea + 1] .. ring[eb]."""
    N = len(ring)
    if ea == eb:
        return None
    out = []
    k = (ea + 1) % N
    while True:
        out.append(ring[k])
        if k == eb:
            break
        k = (k + 1) % N
        if len(out) > N:
            return None
    return out if len(out) >= 2 else None


def _length(pts) -> float:
    return sum(dist(a, b) for a, b in zip(pts, pts[1:]))


def junction_plan(cx, j) -> dict:
    """What a junction draws between its legs and which of its legs' runs join it:
    {"raised", "corners": [{"i", "a", "b", "kind"}], "median": [key a, key b] | None,
    "joins": {leg key: {"l": bool, "r": bool, "m": bool}}} (sides as the road sees them:
    l its +t side). Cached on the context."""
    cache = cx.__dict__.setdefault("_barrier_plans", {})
    if j.id in cache:
        return cache[j.id]
    ring, legs = _legs(cx, j)
    node = cx.node.get(j.node_id)
    raised = bool(node is not None and node.position[2] > RAISED_M and not j.level)
    kinds = {lg["key"]: _kinds(lg["seg"]) for lg in legs}
    joins = {lg["key"]: {"l": False, "r": False, "m": False} for lg in legs}

    def road_side(lg, ccw_side: bool) -> str:
        # a leg's counterclockwise side (its left, looking away from the node) is the
        # road's +t side at its start, its -t side at its end
        return ("l" if lg["at_start"] else "r") if ccw_side else \
            ("r" if lg["at_start"] else "l")
    corners = []
    n = len(legs)
    if n >= 2 and j.shape != "cul_de_sac":
        for i in range(n):
            a, b = legs[i], legs[(i + 1) % n]
            if a["exit"] is None or b["exit"] is None or (n == 2 and i == 1 and
                                                          a["key"] == b["key"]):
                continue
            ch = _chain(ring, a["exit"][1], b["exit"][1])
            if ch is None or _spans_exit(ring, a["exit"][1], b["exit"][1], legs):
                continue
            ka, kb = kinds[a["key"]], kinds[b["key"]]
            kind = None
            if raised and (ka["parapet"] or kb["parapet"]):
                kind = "parapet"
            elif not raised and ka["guard"] and kb["guard"] and _length(ch) >= CORNER_MIN_M:
                kind = "guard"
            if kind is None:
                continue
            corners.append({"i": i, "a": a["key"], "b": b["key"], "kind": kind})
            if (kind == "parapet" and ka["parapet"]) or (kind == "guard" and ka["guard"]):
                joins[a["key"]][road_side(a, True)] = True
            if (kind == "parapet" and kb["parapet"]) or (kind == "guard" and kb["guard"]):
                joins[b["key"]][road_side(b, False)] = True
    median = None
    med = [lg for lg in legs if kinds[lg["key"]]["median"] and lg["exit"] is not None]
    if len(med) == 2 and med[0]["key"] != med[1]["key"]:
        A, B = med
        cosab = A["d"][0] * B["d"][0] + A["d"][1] * B["d"][1]
        if cosab <= M.cos(M.radians(MEDIAN_ANGLE_DEG)):
            ma = median_end(ring, A["exit"], A["path"], A["h"])
            mb = median_end(ring, B["exit"], B["path"], B["h"])
            if _clear_of_connectors(cx, j.node_id, ma, mb) and _inside_ring(ring, ma, mb):
                median = [A["key"], B["key"]]
                joins[A["key"]]["m"] = True
                joins[B["key"]]["m"] = True
    out = {"raised": raised, "corners": corners, "median": median, "joins": joins}
    cache[j.id] = out
    return out


def exit_mid(ring, ex) -> tuple[float, float]:
    """The middle of a leg's exit edge."""
    i = ex[1]
    a, b = ring[i], ring[(i + 1) % len(ring)]
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def median_end(ring, ex, path, h: float) -> tuple[float, float]:
    """Where a road's median meets its junction (as `Road.at` puts offset 0 at its cut): the
    middle of the exit edge where that edge is the road's cut (it spans the carriageway
    within `roads.CUT_TOL_M`), else the centerline's exit point; `path` from the node."""
    from .roads import CUT_TOL_M
    s, i = ex[0], ex[1]
    a, b = ring[i], ring[(i + 1) % len(ring)]
    x, y = path.point(s)
    tx, ty = path.tangent(s)
    ta = -ty * (a[0] - x) + tx * (a[1] - y)
    tb = -ty * (b[0] - x) + tx * (b[1] - y)
    tl, tr = max(ta, tb), min(ta, tb)
    if abs(tl - h) <= CUT_TOL_M and abs(tr + h) <= CUT_TOL_M:
        return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    return (x, y)


def _spans_exit(ring, ea: int, eb: int, legs) -> bool:
    """The outline from leg a's exit edge to leg b's passes another leg's exit edge (the
    legs' order round the node is not their order along the outline)."""
    N = len(ring)
    inner = set()
    k = (ea + 1) % N
    while k != eb:
        inner.add(k)
        k = (k + 1) % N
        if len(inner) > N:
            return True
    return any(lg["exit"] is not None and lg["exit"][1] in inner for lg in legs)


def cut_span(ring, ex, path, h: float) -> tuple[float, float]:
    """Where a leg's carriageway begins along its path from the node at its right (-h) and
    left (+h) edges: on the exit edge where that is the road's cut (as `Road._edge`
    decides), else square across at the exit."""
    from .roads import CUT_TOL_M
    s, i = ex[0], ex[1]
    a, b = ring[i], ring[(i + 1) % len(ring)]
    x, y = path.point(s)
    tx, ty = path.tangent(s)
    ta = -ty * (a[0] - x) + tx * (a[1] - y)
    tb = -ty * (b[0] - x) + tx * (b[1] - y)
    if abs(max(ta, tb) - h) > CUT_TOL_M or abs(min(ta, tb) + h) > CUT_TOL_M:
        return s, s
    L_, R_ = (a, b) if ta > tb else (b, a)
    return path.project(R_[0], R_[1])[0], path.project(L_[0], L_[1])[0]


def _seg_dist(x: float, y: float, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    f = 0.0 if L2 <= 0.0 else min(max(((x - a[0]) * dx + (y - a[1]) * dy) / L2, 0.0), 1.0)
    return math.hypot(x - a[0] - dx * f, y - a[1] - dy * f)


def _index(cx):
    """Plan indexes of the roads and the junctions (cached on the context)."""
    ix = cx.__dict__.get("_barrier_index")
    if ix is None:
        segs = sorted(cx.m.road_segments, key=lambda s: s.id)
        lines = [shapely.LineString([(p[0], p[1]) for p in s.centerline]) for s in segs]
        jns = sorted(cx.m.junctions, key=lambda j: j.id)
        polys = [G.from_model_poly(j.polygon) for j in jns]
        xw: dict = {}
        for c in cx.m.crosswalks:
            xw.setdefault(c.junction_id, []).append(c)
        ix = cx._barrier_index = (shapely.STRtree(lines), segs, lines,
                                  shapely.STRtree(polys), jns, polys, xw)
    return ix


def _masses(cx):
    """Every building mass's footprint with the heights it spans (absolute), indexed."""
    ms = cx.__dict__.get("_barrier_masses")
    if ms is None:
        rows, polys = [], []
        for b in sorted(cx.m.buildings, key=lambda b: b.id):
            base = float(getattr(b, "base_m", None) or 0.0)
            for k, m in enumerate(b.masses):
                if m.role == "void":
                    continue
                polys.append(G.from_model_poly(m.footprint))
                rows.append((b.id, k, base + m.z0_m, base + m.z1_m))
        ms = cx._barrier_masses = (shapely.STRtree(polys) if polys else None, polys, rows)
    return ms


def _junction_z(cx, j) -> tuple[float, float]:
    """The heights a junction's surface spans (absolute: its node's, and M18's surface
    round its outline where it has one)."""
    n = cx.node.get(j.node_id)
    if n is None:
        return 0.0, 0.0
    g = float(getattr(n, "ground_m", None) or 0.0)
    zs = [float(n.position[2]) + g] + [g + float(z) for z in (j.edge_z or ())]
    return min(zs), max(zs)


def _near_z(z: float, zr: tuple[float, float]) -> bool:
    return zr[0] - Z_NEAR_M <= z <= zr[1] + Z_NEAR_M


_ROADZ: dict = {}


def _road_z(s, x: float, y: float) -> float:
    """A road's surface (absolute: its grade line plus its z profile) nearest a point."""
    from .path import Profile
    key = (s.id, len(s.centerline), s.centerline[0], s.centerline[-1])
    got = _ROADZ.get(key)
    if got is None:
        try:
            path = Path(s.centerline)
        except ValueError:
            return 0.0
        zp = Profile.of([z.model_dump() for z in s.z_profile]) if s.z_profile else None
        g = getattr(s, "ground", None)
        gp = Profile.of([q.model_dump() for q in g]) if g else None
        if len(_ROADZ) > 4096:
            _ROADZ.clear()
        got = _ROADZ[key] = (path, zp, gp)
    path, zp, gp = got
    at, _ = path.project(x, y)
    return (zp(at) if zp is not None else 0.0) + (gp(at) if gp is not None else 0.0)


def near_of_junction(cx, j) -> dict:
    """The roads (not the junction's legs) and the other junctions within `NEAR_M` of a
    junction at its height (within `Z_NEAR_M`), and the crosswalks of it and of them, as
    `Keepout` takes them: roads as their centerline's part near it with their carriageway's
    half width."""
    from .roads import street_class
    tree, segs, lines, jtree, jns, polys, xw = _index(cx)
    poly = G.from_model_poly(j.polygon)
    zone = poly.buffer(NEAR_M)
    zj = _junction_z(cx, j)
    legs = {s.id for s in cx.seg_at_node.get(j.node_id, ())}
    roads = []
    for k in sorted(tree.query(zone).tolist()):
        s = segs[k]
        if s.id in legs:
            continue
        part = shapely.intersection(lines[k], zone)
        got = [g for g in shapely.get_parts(part)
               if g.geom_type == "LineString" and not g.is_empty and g.length >= 0.5]
        for p in sorted(got, key=lambda g: tuple(g.coords[0])):
            mid = p.interpolate(0.5, normalized=True)
            if not _near_z(_road_z(s, mid.x, mid.y), zj):
                continue
            cls = street_class(s)
            h = s.width_m / 2.0 if cls in PEDESTRIAN else \
                s.width_m / 2.0 - s.cross_section.sidewalk_m[0]
            roads.append({"line": [[C.m2(c[0]), C.m2(c[1])] for c in p.coords],
                          "h": C.m(h)})
    rings, ids = [], [j.id]
    for k in sorted(jtree.query(zone).tolist()):
        o = jns[k]
        if o.id == j.id:
            continue
        zo = _junction_z(cx, o)
        if zo[0] - Z_NEAR_M > zj[1] or zo[1] + Z_NEAR_M < zj[0]:
            continue
        rings += [[[C.m2(p[0]), C.m2(p[1])] for p in rg] for rg in junction_area(cx, o)]
        ids.append(o.id)
    xws = []
    for jid in ids:
        for c in sorted(xw.get(jid, ()), key=lambda c: c.id):
            xws.append({"line": [list(c.line[0][:2]), list(c.line[-1][:2])],
                        "width": c.width_m})
    lanes = [{"line": [[C.m2(q[0]), C.m2(q[1])] for q in ln.centerline],
              "h": C.m(ln.width_m / 2.0)}
             for ln in sorted(_connectors(cx, j.node_id), key=lambda ln: ln.id)
             if len(ln.centerline) >= 2]
    # the building masses there at its height (a corner's property line runs by them)
    mtree, mpolys, mrows = _masses(cx)
    blds = []
    if mtree is not None:
        for k in sorted(mtree.query(zone).tolist()):
            _, _, z0, z1 = mrows[k]
            if z0 > zj[1] + PARAPET_H + Z_NEAR_M or z1 < zj[0]:
                continue
            blds.append([[C.m2(p[0]), C.m2(p[1])] for p in mpolys[k].exterior.coords[:-1]])
    return {"roads": roads, "junctions": rings, "xwalks": xws, "lanes": lanes,
            "buildings": blds}


def junction_area(cx, j) -> list[list]:
    """What a junction piece may pave (`walks.make_junction`): its outline and, for each
    corner with a sidewalk, the sector its pad is cut from (`walks._corners`: from the node
    out to both sidewalks' ends and round the property line), as rings. Cached."""
    cache = cx.__dict__.setdefault("_junction_areas", {})
    if j.id in cache:
        return cache[j.id]
    from .walks import _arc, _corner, _meet
    ring, legs = _legs(cx, j)
    out = [list(ring)]
    node = cx.node.get(j.node_id)
    n = len(legs)
    if node is not None and n >= 2 and j.shape != "cul_de_sac":
        P = (node.position[0], node.position[1])
        N = len(ring)
        r_all = j.corner_radius_m
        for i in range(n):
            a, b = legs[i], legs[(i + 1) % n]
            sa = 0.0 if _cls(a["seg"]) in PEDESTRIAN else a["seg"].cross_section.sidewalk_m[0]
            sb = 0.0 if _cls(b["seg"]) in PEDESTRIAN else b["seg"].cross_section.sidewalk_m[0]
            if a["exit"] is None or b["exit"] is None or (sa <= 0.0 and sb <= 0.0):
                continue
            ea, eb = a["exit"][1], b["exit"][1]
            if ea == eb:
                continue
            Ca, Cb = ring[(ea + 1) % N], ring[eb]
            da, db = a["d"], b["d"]
            na, nb = (-da[1], da[0]), (-db[1], db[0])
            ra, rb = a["seg"].width_m / 2.0, b["seg"].width_m / 2.0
            cut_a = (Ca[0] - P[0]) * da[0] + (Ca[1] - P[1]) * da[1]
            cut_b = (Cb[0] - P[0]) * db[0] + (Cb[1] - P[1]) * db[1]
            Ra = (P[0] + cut_a * da[0] + ra * na[0], P[1] + cut_a * da[1] + ra * na[1])
            Rb = (P[0] + cut_b * db[0] - rb * nb[0], P[1] + cut_b * db[1] - rb * nb[1])
            rr = max(r_all - max(sa, sb), 1.0)
            c = _corner(P, da, db, ra, rb, rr, a["path"].L, b["path"].L)
            row = [Ra]
            if c is not None:
                ta, tb, Ta, Tb, O = c
                if ta <= cut_a + 0.01 and tb <= cut_b + 0.01:
                    row.append(Ta)
                    if O is not None:
                        row += _arc(O, Ta, Tb, rr)
                        row.append(Tb)
                else:
                    X = _meet(P, da, db, ra, rb)
                    if X is not None:
                        xa = (X[0] - P[0]) * da[0] + (X[1] - P[1]) * da[1]
                        xb = (X[0] - P[0]) * db[0] + (X[1] - P[1]) * db[1]
                        if 0.0 <= xa <= cut_a + 0.01 and 0.0 <= xb <= cut_b + 0.01:
                            row.append(X)
            row.append(Rb)
            Pa = (P[0] + cut_a * da[0], P[1] + cut_a * da[1])
            Pb = (P[0] + cut_b * db[0], P[1] + cut_b * db[1])
            out.append([P, Pa] + row + [Pb])
    cache[j.id] = out
    return out


def _valid(ring):
    p = shapely.Polygon(ring)
    return p if p.is_valid else shapely.make_valid(p)


def _cls(s) -> str:
    from .roads import street_class
    return street_class(s)


def leg_ends(cx, j) -> dict:
    """Where each leg's carriageway begins at a junction, as its road piece draws it: the
    corners of its end row (`Road.at` at its cut, at -h and +h of the road's own frame),
    by leg key; a leg whose road cannot be made is left out."""
    from .roads import Road, street_class
    out = {}
    for s in sorted(cx.seg_at_node.get(j.node_id, ()), key=lambda s: s.id):
        ends = []
        for which, nid in (("start", s.start), ("end", s.end)):
            jj = cx.junction_at.get(nid)
            e = {"at": which}
            if jj is not None:
                e["junction"] = {"ring": [list(p) for p in jj.polygon.exterior]}
            ends.append(e)
        try:
            rd = Road({"seg": s.model_dump(mode="json", exclude_none=True),
                       "cls": street_class(s), "ends": ends})
        except ValueError:
            continue
        for at_start in ((True, False) if s.start == s.end else (s.start == j.node_id,)):
            sc = rd.s0 if at_start else rd.s1
            R, L_ = rd.at(sc, -rd.h), rd.at(sc, rd.h)
            out[leg_key(s.id, at_start)] = [[C.m(R[0]), C.m(R[1])], [C.m(L_[0]), C.m(L_[1])]]
    return out


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


class Keepout:
    """What a junction's own barriers keep off (#95): each leg's carriageway as its road
    piece draws it (past its cut, within its half width and `CLEAR_M`), the carriageways of
    other roads near it, the surfaces of other junctions near it and the building masses
    there at its height, its own connector lanes (`near`), and the crosswalks near it
    (`XWALK_CLEAR_M` past their edges, `CLEAR_M` past their ends). Plain arithmetic on the
    inputs."""

    def __init__(self, legs: list[dict], xwalks: list[dict], ring=None, near=None):
        self.legs = []
        near = near or {}
        ends = near.get("ends") or {}
        for lg in legs:
            ex = lg.get("exit")
            if ex is None:
                continue
            path = lg["path"]
            s0 = ex[0]
            try:
                sub = Path(path.sub(0.0, min(path.L, s0 + 40.0)))
            except ValueError:
                continue
            sr, sl = cut_span(ring, ex, path, lg["h"]) if ring is not None else (s0, s0)
            # (the end row its road piece draws: the line through its two corners, its
            # normal away from the node)
            e = ends.get(lg.get("key"))
            line = None
            if e is not None:
                (rx, ry), (lx, ly) = e
                ux, uy = lx - rx, ly - ry
                L_ = math.hypot(ux, uy)
                if L_ > 1e-6:
                    nx, ny = uy / L_, -ux / L_
                    tx, ty = path.tangent(s0)
                    if nx * tx + ny * ty < 0.0:
                        nx, ny = -nx, -ny
                    line = ((rx + lx) / 2.0, (ry + ly) / 2.0, nx, ny)
            self.legs.append((sub, sr, sl, lg["h"], line))
        self.roads = []
        for r in near.get("roads", ()):
            try:
                self.roads.append((Path(r["line"]), r["h"]))
            except ValueError:
                continue
        # (its own connector lanes: where M17 laid a corner pad over a turning lane)
        self.lanes = []
        for r in near.get("lanes", ()):
            try:
                self.lanes.append((Path(r["line"]), r["h"]))
            except ValueError:
                continue
        self.rings = []
        for rg in list(near.get("junctions", ())) + list(near.get("buildings", ())):
            xs = [p[0] for p in rg]
            ys = [p[1] for p in rg]
            self.rings.append((rg, min(xs), min(ys), max(xs), max(ys)))
        self.xw = []
        for c in xwalks:
            a, b = c["line"][0], c["line"][-1]
            L = dist(a, b)
            if L < 0.5:
                continue
            u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            self.xw.append((a, u, L, c["width"] / 2.0))

    def blocked(self, x: float, y: float) -> bool:
        for sub, sr, sl, h, line in self.legs:
            s, t = sub.project(x, y)
            if abs(t) < h + CLEAR_M and s < sub.L - 1e-6:
                if line is not None:
                    mx, my, nx, ny = line
                    if (x - mx) * nx + (y - my) * ny > 0.05:
                        return True
                    continue
                f = min(max((t + h) / (2.0 * h), 0.0), 1.0) if h > 0 else 0.5
                if s > sr + (sl - sr) * f + 0.05:
                    return True
        for path, h in self.roads:
            s, t = path.project(x, y)
            if abs(t) < h + CLEAR_M and 1e-6 < s < path.L - 1e-6:
                return True
        for path, h in self.lanes:
            _, t = path.project(x, y)
            if abs(t) < h:
                return True
        for rg, x0, y0, x1, y1 in self.rings:
            if x0 - CLEAR_M <= x <= x1 + CLEAR_M and y0 - CLEAR_M <= y <= y1 + CLEAR_M:
                if _inside(rg, x, y) or any(
                        _seg_dist(x, y, rg[i - 1], rg[i]) < CLEAR_M for i in range(len(rg))):
                    return True
        for a, u, L, hw in self.xw:
            dx, dy = x - a[0], y - a[1]
            along = dx * u[0] + dy * u[1]
            across = -dx * u[1] + dy * u[0]
            if -CLEAR_M < along < L + CLEAR_M and abs(across) < hw + XWALK_CLEAR_M:
                return True
        return False


def clip_line(pts, offsets, keep: Keepout, step: float = 0.25) -> list[list]:
    """The parts of a polyline where a barrier along it is clear of `keep`: tested at every
    `step` at each of `offsets` (to the left of the line); parts of `MIN_SPAN_M` or more."""
    try:
        path = Path(pts)
    except ValueError:
        return []
    n = max(1, int(math.ceil(path.L / step)))
    free = []
    for k in range(n + 1):
        s = path.L * k / n
        x, y, nx, ny, _ = path.frame(s)
        free.append(not any(keep.blocked(x + nx * o, y + ny * o) for o in offsets))
    out, start = [], None
    for k, ok in enumerate(free + [False]):
        if ok and start is None:
            start = k
        elif not ok and start is not None:
            a, b = path.L * start / n, path.L * (k - 1) / n
            if b - a >= MIN_SPAN_M:
                out.append(path.sub(a, b) if (a > 0.0 or b < path.L) else list(path.p))
            start = None
    return out


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


def _inside_ring(ring, a, b) -> bool:
    """The segment a-b lies inside the ring (crosses none of its edges between its ends)."""
    L = dist(a, b)
    n = len(ring)
    for i in range(n):
        c = seg_cross(a, b, ring[i], ring[(i + 1) % n])
        if c is not None and 0.05 / max(L, 1e-9) < c[0] < 1.0 - 0.05 / max(L, 1e-9):
            return False
    return True


# ---------------------------------------------------------------------------
# A road's runs and their spans
# ---------------------------------------------------------------------------

def _band(rd, t0: float, t1: float, s0: float, s1: float):
    """The plan strip of offsets t0..t1 from s0 to s1 (perpendicular frames), shapely."""
    left, right = [], []
    for s, vi in rd.path.stations(s0, s1, BAND_STEP_M):
        x, y, nx, ny, k = rd.path.frame(s, vi)
        left.append((x + nx * k * t1, y + ny * k * t1))
        right.append((x + nx * k * t0, y + ny * k * t0))
    poly = shapely.Polygon(left + right[::-1])
    if not poly.is_valid:
        poly = shapely.make_valid(poly)
    return poly


def corner_points(rd, ring, node_xy, at: str) -> dict | None:
    """Where a road's edge parapets end at a junction: where its sidewalk ends,
    `walks._corners`' line across the leg (square to M2's leg direction d, at the
    distance from the node along d of the exit edge's corner on that side). For its +t
    (l) and -t (r) sides: (s, [x, y, nx, ny]), the distance along the road where its
    property line meets that line and the end frame along it (origin on the line at the
    leg's centerline, normal along the line, as the road's +t). None where its centerline
    does not leave the ring."""
    pp = rd.path.p if at == "start" else rd.path.p[::-1]
    r = first_exit(pp, ring)
    if r is None:
        return None
    i = r[1]
    P = node_xy
    d = _leg_dir(pp, P)
    nl = (-d[1], d[0])
    W2 = rd.W / 2.0
    out = {}
    for ccw_side, C_ in ((True, ring[(i + 1) % len(ring)]), (False, ring[i])):
        cut = (C_[0] - P[0]) * d[0] + (C_[1] - P[1]) * d[1]
        side = ("l" if at == "start" else "r") if ccw_side else \
            ("r" if at == "start" else "l")
        sg = 1.0 if side == "l" else -1.0

        def g(s, sg=sg, cut=cut):
            x, y, nx, ny, _ = rd.path.frame(s)
            px, py = x + nx * sg * W2, y + ny * sg * W2
            return (px - P[0]) * d[0] + (py - P[1]) * d[1] - cut
        s_ = _root(g, rd.L, at)
        if s_ is None:
            continue
        # (the road's +t at its end: d's left at its start, d's right at its end; the
        # frame's origin such that its outer face, offset sg W2, lands where the road's
        # property line meets the line)
        nt = nl if at == "start" else (-nl[0], -nl[1])
        x, y, nx, ny, _ = rd.path.frame(s_)
        qx, qy = x + nx * sg * W2, y + ny * sg * W2
        out[side] = (s_, [qx - nt[0] * sg * W2, qy - nt[1] * sg * W2, nt[0], nt[1]])
    return out


def _root(g, L: float, at: str, step: float = 1.0):
    """The first s from the road's end `at` where g (rising away from the node) reaches 0:
    scanned every `step`, then halved 30 times."""
    n = max(1, int(math.ceil(L / step)))
    ss = [L * k / n for k in range(n + 1)]
    if at == "end":
        ss = ss[::-1]
    prev = ss[0]
    gp = g(prev)
    if gp >= 0.0:
        return prev
    for s in ss[1:]:
        gs = g(s)
        if gs >= 0.0:
            a, b = prev, s
            for _ in range(30):
                m = (a + b) / 2.0
                if g(m) >= 0.0:
                    b = m
                else:
                    a = m
            return b
        prev = s
    return None


def road_runs(cx, s, inputs: dict, runs: list[Run] | None = None) -> list[dict]:
    """The spans of a road's barrier runs: [{"name", "spans": [[a, b, end_a, end_b]]}] with
    ends `join`, `stop` or `open` (module docstring)."""
    from .roads import Road, street_class
    if runs is None:
        runs = runs_of(inputs["seg"], inputs["cls"])
    if not runs:
        return []
    try:
        rd = Road(inputs)
    except ValueError:
        return []
    if rd.s1 - rd.s0 < MIN_SPAN_M:
        return []
    ends = {e["at"]: e for e in inputs["ends"]}
    plan = {}
    jpoly = {}
    sectors = {}
    corners = {}
    for at, nid in (("start", s.start), ("end", s.end)):
        j = cx.junction_at.get(nid)
        if j is None or "junction" not in ends.get(at, {}):
            continue
        plan[at] = junction_plan(cx, j)
        jpoly[at] = G.from_model_poly(j.polygon)
        sectors[at] = [_valid(rg) for rg in junction_area(cx, j)[1:]]
        node = cx.node.get(nid)
        if node is not None:
            corners[at] = corner_points(rd, ccw(j.polygon.exterior),
                                        (node.position[0], node.position[1]), at)
    # other roads' carriageways at the junctions of its ends
    others = []
    for at, nid in (("start", s.start), ("end", s.end)):
        if at not in plan:
            continue
        for o in cx.seg_at_node.get(nid, ()):
            if o.id == s.id:
                continue
            cls = street_class(o)
            half = o.width_m / 2.0 if cls in PEDESTRIAN else \
                o.width_m / 2.0 - o.cross_section.sidewalk_m[0]
            try:
                ln = shapely.LineString([(p[0], p[1]) for p in o.centerline])
            except Exception:       # noqa: BLE001
                continue
            if ln.length < 0.01:
                continue
            others.append(ln.buffer(half + CLEAR_M, cap_style="flat", join_style="mitre"))
    xws = []
    for c in sorted(cx.cross_on.get(s.id, ()), key=lambda c: c.id):
        a, b = c.line[0], c.line[-1]
        ln = shapely.LineString([(a[0], a[1]), (b[0], b[1])])
        if ln.length >= 0.5:
            xws.append(ln.buffer(c.width_m / 2.0 + XWALK_CLEAR_M, cap_style="flat"))
    # other junctions its barriers pass at its height (not those at its ends), and their
    # crosswalks
    _, _, _, jtree, jns, polys, xwat = _index(cx)
    ends_j = {cx.junction_at[n].id for n in (s.start, s.end) if n in cx.junction_at}
    reach = shapely.LineString([(p[0], p[1]) for p in s.centerline]).buffer(s.width_m / 2.0 + 1.0)
    for k in sorted(jtree.query(reach, predicate="intersects").tolist()):
        o = jns[k]
        if o.id in ends_j:
            continue
        c_ = polys[k].centroid
        if not _near_z(_road_z(s, c_.x, c_.y), _junction_z(cx, o)):
            continue
        others += [_valid(rg).buffer(CLEAR_M) for rg in junction_area(cx, o)]
        for c in sorted(xwat.get(o.id, ()), key=lambda c: c.id):
            a, b = c.line[0], c.line[-1]
            ln = shapely.LineString([(a[0], a[1]), (b[0], b[1])])
            if ln.length >= 0.5:
                xws.append(ln.buffer(c.width_m / 2.0 + XWALK_CLEAR_M, cap_style="flat"))
    # other roads alongside it, not those at its ends: their carriageway where it is at its
    # height (a ramp's low end beside a street it does not meet; a road it passes over or
    # under is not)
    stree, sall, slines = _index(cx)[:3]
    at_ends = {o.id for n in (s.start, s.end) for o in cx.seg_at_node.get(n, ())}
    me = shapely.LineString([(p[0], p[1]) for p in s.centerline])
    wide = me.buffer(s.width_m / 2.0 + 1.0 + SIDE_REACH_M)
    for k in sorted(stree.query(wide, predicate="intersects").tolist()):
        o = sall[k]
        if o.id in at_ends or len(o.centerline) < 2:
            continue
        cls = street_class(o)
        half = o.width_m / 2.0 if cls in PEDESTRIAN else \
            o.width_m / 2.0 - o.cross_section.sidewalk_m[0]
        others += _level_with(s, o, slines[k], wide, half + CLEAR_M)
    out = []
    for run in runs:
        key_s = leg_key(s.id, True)
        key_e = leg_key(s.id, False)
        joined = {}
        for at, key in (("start", key_s), ("end", key_e)):
            if at in plan:
                jn = plan[at]["joins"].get(key, {})
                joined[at] = bool(jn.get(run.side if run.side != "m" else "m"))
            else:
                joined[at] = None           # no junction: the run goes on
        # where the run may start and end: the cut, or (a parapet at the road's edge) its
        # junction's corner
        a0, b0 = rd.s0, rd.s1
        frames = {}
        if run.edge and rd.h < rd.W / 2.0 - 1e-6:
            for at in ("start", "end"):
                cp = corners.get(at)
                if not cp or run.side not in cp:
                    continue
                sc, fr = cp[run.side]
                if at == "start":
                    a0 = min(max(sc, 0.0), rd.L)
                else:
                    b0 = max(min(sc, rd.L), 0.0)
                frames[at] = [C.m2(fr[0]), C.m2(fr[1]), round(fr[2], 6), round(fr[3], 6)]
        if b0 - a0 < MIN_SPAN_M:
            continue
        F = list(others) + list(xws)
        sidewalk = rd.h < rd.W / 2.0 - 1e-6
        for at in ("start", "end"):
            # (a jersey stops short of a junction that does not carry it on; a parapet on a
            # sidewalk keeps off the junction too, where M17's junction reaches over it; a
            # parapet on a road without one ends on the cut edge)
            if at in jpoly and ((not run.edge and not joined[at]) or (run.edge and (
                    sidewalk or rd.cut.get(at) is None))):
                F.append(jpoly[at].buffer(CLEAR_M))
            if at in jpoly and run.edge and sidewalk:
                F += sectors[at]
        spans = _spans(rd, run, a0, b0, F)
        rows = []
        for a, b in spans:
            ea = "open" if joined["start"] is None and a <= rd.s0 + 1e-6 else \
                ("join" if joined["start"] and abs(a - a0) < 1e-6 else "stop")
            eb = "open" if joined["end"] is None and b >= rd.s1 - 1e-6 else \
                ("join" if joined["end"] and abs(b - b0) < 1e-6 else "stop")
            # (an edge parapet ends at its corner capped whether or not the junction goes
            # on; at a cut-edge corner its end lies on the cut edge)
            if run.edge:
                ea = "corner" if abs(a - a0) < 1e-6 and "start" in plan else ea
                eb = "corner" if abs(b - b0) < 1e-6 and "end" in plan else eb
            rows.append([C.m(a), C.m(b), ea, eb])
        if rows:
            r_ = {"name": run.name, "spans": rows}
            if frames:
                r_["frames"] = frames
            out.append(r_)
    return out


def _level_with(s, o, line, reach, half: float, step: float = 2.0) -> list:
    """Another road's strip (`half` either side of its centerline) along the stretches of
    it within `reach` where its surface is within `Z_NEAR_M` of road s's nearest it."""
    me = shapely.LineString([(c[0], c[1]) for c in s.centerline])
    part = shapely.intersection(line, reach)
    out = []
    for g in shapely.get_parts(part):
        if g.geom_type != "LineString" or g.is_empty or g.length < 0.5:
            continue
        n = max(1, int(math.ceil(g.length / step)))
        ds = [g.length * k / n for k in range(n + 1)]
        ok = []
        for d in ds:
            p = g.interpolate(d)
            q = nearest_points(me, p)[0]
            ok.append(abs(_road_z(s, q.x, q.y) - _road_z(o, p.x, p.y)) <= Z_NEAR_M)
        # (runs of samples at its height, each a step longer at both ends, along the road's
        # own line, mitred as AG7 draws it)
        start = None
        for k, good in enumerate(ok + [False]):
            if good and start is None:
                start = k
            elif not good and start is not None:
                a_ = max(ds[start] - g.length / n, 0.0)
                b_ = min(ds[k - 1] + g.length / n, g.length)
                if b_ - a_ > 0.1:
                    sub = substring(g, a_, b_)
                    out.append(sub.buffer(half, cap_style="flat", join_style="mitre"))
                start = None
    return out


def _spans(rd, run: Run, a0: float, b0: float, F: list) -> list[tuple[float, float]]:
    """[a0, b0] less the stretches where the run's band meets a forbidden shape."""
    if not F:
        return [(a0, b0)] if b0 - a0 >= MIN_SPAN_M else []
    band = _band(rd, run.t0, run.t1, a0, b0)
    blocked = []
    with G.canonical():
        hit = G.inter(G.qpoly(band), G.union([G.qpoly(f) for f in F]))
        for p in G.parts(hit):
            if p.area < 1e-4:
                continue
            ss = [rd.path.project(x, y)[0] for x, y in p.exterior.coords]
            blocked.append((max(min(ss), a0), min(max(ss), b0)))
    blocked.sort()
    out, at = [], a0
    for a, b in blocked:
        if a > at:
            out.append((at, a))
        at = max(at, b)
    if at < b0:
        out.append((at, b0))
    return [(a, b) for a, b in out if b - a >= MIN_SPAN_M]


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def cut_frame(rd, at: str, z: float):
    """The frame on the junction's cut edge at a road's end (as `Road.at` puts the
    carriageway's end on it): a profile offset t lands on the edge's line; None where the
    cut is square."""
    e = rd.cut.get(at)
    if e is None:
        return None
    R, Lp = e
    ex, ey = (Lp[0] - R[0]) / (2.0 * rd.h), (Lp[1] - R[1]) / (2.0 * rd.h)
    k = math.sqrt(ex * ex + ey * ey)
    if k < 1e-9:
        return None
    mx, my = (R[0] + Lp[0]) / 2.0, (R[1] + Lp[1]) / 2.0
    s = rd.s0 if at == "start" else rd.s1
    return (mx, my, z, ex / k, ey / k, k, s)


def draw_run(mesh, rd, run: Run, spans: list, step: float = 6.0, ends=None):
    """A run over its spans, with its ends (`join`, `stop`, `open`, `corner`); `ends`
    (`road_runs`' frames) the end frames of an edge parapet at its junctions' corners."""
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
        for s, vi in rd.path.stations(a, b, step, extra + rd.knots(a, b)):
            x, y, nx, ny, k = rd.path.frame(s, vi)
            z = rd.z(s) + run.base
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
        # (on the cut edge where the run joins its junction there, or at a corner)
        for idx, e, at, s_ in ((0, ea, "start", a), (-1, eb, "end", b)):
            if e == "corner" and ends and at in ends:
                x_, y_, nx_, ny_ = ends[at]
                frames[idx] = (x_, y_, frames[idx][2], nx_, ny_, 1.0, s_)
                continue
            if e in ("join", "corner") and abs(s_ - (rd.s0 if at == "start" else rd.s1)) < 0.01:
                fr = cut_frame(rd, at, frames[idx][2])
                if fr is not None:
                    frames[idx] = fr
        mesh.sweep(run.slot, frames, run.profile, zscale=scales)
        for idx, e, out in ((0, ea, -1.0), (-1, eb, 1.0)):
            if e != "open":
                cap(mesh, run.slot, frames[idx], run.profile, scales[idx], out)


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


def draw_line(mesh, slot: str, pts, profile, zfun, base: float = 0.0, jersey: bool = False,
              step: float = 3.0, caps: bool = True):
    """A barrier along a plan polyline (a junction's corner, a median across it), its
    section's t to the left of the line, heights from zfun over each station."""
    try:
        path = Path(pts)
    except ValueError:
        return
    if path.L < 0.05:
        return
    frames = []
    for s, vi in path.stations(0.0, path.L, step):
        x, y, nx, ny, k = path.frame(s, vi)
        frames.append((x, y, zfun(x, y) + base, nx, ny, k, s))
    if len(frames) < 2:
        return
    mesh.sweep(slot, frames, profile)
    if caps:
        cap(mesh, slot, frames[0], profile, 1.0, -1.0)
        cap(mesh, slot, frames[-1], profile, 1.0, 1.0)


__all__ = ["Run", "runs_of", "rail_runs", "junction_plan", "road_runs", "draw_run",
           "draw_line", "cut_frame", "end_frame", "cap", "JERSEY", "PARAPET_H", "PARAPET_W",
           "leg_key", "exit_mid", "median_end", "parapet_profile", "shifted", "Keepout",
           "clip_line"]
