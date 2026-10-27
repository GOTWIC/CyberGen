"""M7: elevated highways, ramps and interchanges (scope 5.2), on the primary network of M1b.

Runs inside the road builder, after `roads.assemble`, so M2 lays its streets around the ramps:

1. **Runs.** The highway segments M1b marked `elevated` join into runs: chains through the
   nodes where two of them meet (where three or more meet, the straightest pair continues and
   the others end there, on the deck).
2. **Nodes inside a run.** Each keeps the run up or splits it back to the ground:
   - an avenue crossing (two legs, one on each side): the highway passes over, the avenue
     under; a **diamond** (up to four one-way ramps, one per quadrant) joins them;
   - an avenue ending at the highway (a T): a **diamond with a stub**: ramps on the avenue's
     side, and the far side's ramps land on a stub of the avenue that passes under the deck;
   - ground highway branches: each rises to the deck on its own segment (**direct**);
   - anything else, or a node too near the run's ends to clear a road under it: the run
     comes down to the ground there.
   A run that is too short for its ramps (both ends at the ground) goes back to the ground.
3. **Profiles.** Deck top at level 1 (9 m), raised over bridge decks, over other raised roads
   it crosses without a node (level 2 where that takes it over 16 m), down to the ground at
   its ends at a 5% design grade (6% at most) with 40 m vertical curves and a 20 m flat
   landing. A run that leaves the map stays up.
4. **Ramps.** One lane, 7 m wide, one-way (right-hand traffic), 1 m beside the deck: a 60 m
   taper on the deck from the diverge or merge point, then parallel to the highway down to
   the terminal on the avenue (a signalized junction in M2). A ramp is built only where it
   keeps clear of water, other roads and ramps, reserves and the map edge, and its diverge
   point lies on the full deck away from other nodes; a crossing whose ramps all fail stays a
   plain overpass.
5. **Re-noding.** The highway is cut only where ramps leave or join it and where branches
   meet it; the avenue legs at an overpass join under it. Every piece keeps its z profile
   (`attrs.split_of` names the run or avenue it was cut from, so the alignment checks see
   the whole road).

`road_supports` (after M3) places the columns under every deck off the water (every 25 to 40
m, never in a lane, sidewalk clear path, building or water).

Coordinates are on the 0.01 m grid; positions come from plain arithmetic on grid values,
distances from `geom.dist`, every list in a fixed order.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import dmath as M
from . import geom as G

LEVEL_Z = {1: 9.0, 2: 18.0, 3: 27.0}   # deck tops (3: a stack's upper flyovers, M12)
DECK_M = 1.8                    # viaduct structure depth (scope: 1.5 to 2 m)
CLEAR_M = 5.5                   # under any road deck
GRADE = 0.05                    # design grade of runs and ramps
MAX_GRADE = 0.06                # scope maximum for roads
FLAT_M = 20.0                   # flat landing at a ground end
CURVE_M = 40.0                  # vertical curves (moving average of this length)
STEP_M = 5.0                    # profile sampling
TAPER_M = 60.0                  # ramp taper on the deck
RAMP_W = 7.0
RAMP_LANE = 4.0
RAMP_GAP = 1.0                  # between the deck edge and a ramp
NODE_GAP_M = 40.0               # diverge and merge points from other nodes on the run
TERMINAL_GAP_M = 30.0           # a terminal from the avenue's other nodes
PLATEAU_M = 60.0                # shortest full-height stretch of a run
DIAMOND_ROOM_M = 280.0          # run on each side of a crossing for its diamond
MIN_SKEW_SIN = 0.7              # ramps only where the avenue crosses at 45 degrees or more
LOOP_SKEW_SIN = 0.7             # loop ramps (partial cloverleaf): as diamonds (the clearance test does the rest)
LOOP_MIN_R = 35.0               # loop ramp radius (from the climb: about 45 m for a 9 m deck)
LOOP_LEAD_M = 30.0              # straight from the loop to its terminal on the avenue
LOOP_CLEAR_M = 2.0              # between a loop's lead and the avenue edge
FLY_R = (60.0, 45.0)            # M8d flyover turns: off the deck line, then round to the stem
FLY_GAP_M = 3.0                 # between the flyover's descent and the stem's edge
FLY_SAMPLE_M = 2.5              # clearance samples along a flyover
FLY_SPAN_M = 50.0               # longest stretch over roads with no spot for a column
FLY_TOP_M = LEVEL_Z[2] + 4.0    # highest flyover deck
STRAIGHT_COS = 0.819            # an avenue passes under straight on (35 degrees at most)
OVERPASS_SKEW_SIN = 0.574       # and crosses under at 35 degrees or more (columns fit)
# M12: stacks and turbines where two highways cross
STACK_LIFT_M = 640.0            # ramp ends on the lifted highway within this of the crossing
STACK_GROUND_M = 700.0          # and on the one at grade
STACK_RIGHT_R = 70.0            # right-turn ramps (one quadrant each, next to the highways)
STACK_SWING = (45.0, 50.0, 150.0)   # a stack's left flyover: its lines this far out from
#                                     the highway edges, its diagonal across the core this far
#                                     from the crossing, its two 45 degree turns of this radius
STACK_CORE_M = 200.0            # a stack's core: its left flyovers hold their tier over it
STACK_SPACE_M = 75.0            # a right ramp's ends this far nearer the crossing than the
#                                 left ramp's on the same side (their lanes never cross)
STACK_TOP_M = LEVEL_Z[3] + 2.0  # highest stack ramp deck
STACK_SPAN_M = 56.0             # a directional ramp's longest stretch with no spot for a column
#                                 (columns at both its ends keep it within the supports' 66 m)
TURBINE_SWING = ((60.0, 40.0, 200.0), (60.0, 130.0, 200.0))   # a turbine's left ramps onto
TURBINE_TOP_M = STACK_TOP_M        # and off the lifted highway: wider turns, their crossings
#                                     apart (no point has more than three levels)
STACK_TRIES = 6                 # profiles tried per ramp (approach and departure 20 m longer)


def ramp_run(dz: float) -> float:
    """Length a ramp or run end needs to change height by dz: landing, grade, curve."""
    return FLAT_M + dz / GRADE + CURVE_M / 2.0


def under_m(z: float) -> float:
    """Height that must stay clear under a road deck at z: the deck and the clearance."""
    return z - DECK_M


# ---------------------------------------------------------------------------
# Polylines (plain arithmetic on grid points)
# ---------------------------------------------------------------------------

def _d(a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return math.sqrt(dx * dx + dy * dy)


def _cum(pts) -> list[float]:
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + _d(a, b))
    return out


def _at(pts, cum, s: float):
    """Point and unit tangent at arc length s."""
    s = min(max(s, 0.0), cum[-1])
    i = 0
    while i < len(cum) - 2 and cum[i + 1] < s:
        i += 1
    a, b = pts[i], pts[i + 1]
    L = cum[i + 1] - cum[i]
    f = 0.0 if L <= 0 else (s - cum[i]) / L
    ux, uy = ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L > 0 else (1.0, 0.0)
    return (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])), (ux, uy)


def _sub(pts, cum, a: float, b: float) -> list[tuple[float, float]]:
    """The stretch between arc lengths a < b, on the grid."""
    p0, _ = _at(pts, cum, a)
    p1, _ = _at(pts, cum, b)
    out = [G.qpoint(p0)]
    for p, s in zip(pts, cum):
        if a < s < b:
            q = (G.q(p[0]), G.q(p[1]))
            if q != out[-1]:
                out.append(q)
    q = G.qpoint(p1)
    if q != out[-1]:
        out.append(q)
    return out


def _project(pts, cum, p) -> tuple[float, float]:
    """(arc length of the nearest point, distance)."""
    best = (math.inf, 0.0)
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        f = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy)
                                             / L2))
        x, y = a[0] + f * dx, a[1] + f * dy
        d = _d((x, y), p)
        if d < best[0]:
            best = (d, cum[i] + f * (cum[i + 1] - cum[i]))
    return best[1], best[0]


def _z_at(prof, s: float) -> float:
    if not prof:
        return 0.0
    if s <= prof[0][0]:
        return prof[0][1]
    for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
        if s <= s1:
            return max(z0, z1) if s1 <= s0 else z0 + (z1 - z0) * (s - s0) / (s1 - s0)
    return prof[-1][1]


def _tuples(prof) -> list[tuple[float, float]]:
    return [(p["s"], p["z"]) if isinstance(p, dict) else (p[0], p[1]) for p in prof]


def _rows(prof) -> list[dict]:
    return [{"s": G.q(s), "z": G.q(z)} for s, z in prof]


def _slice(prof, a: float, b: float, rev: bool = False) -> list[tuple[float, float]]:
    """Profile of the stretch [a, b] of a line (reversed: measured from b back to a)."""
    out = [(a, _z_at(prof, a))] + [(s, z) for s, z in prof if a < s < b] + [(b, _z_at(prof, b))]
    if rev:
        return [(b - s, z) for s, z in reversed(out)]
    return [(s - a, z) for s, z in out]


def compress(prof, tol: float = 0.005) -> list[tuple[float, float]]:
    """Grid profile without the samples that lie on the line between their neighbors."""
    pts = []
    for s, z in prof:
        s, z = G.q(s), G.q(z)
        if pts and abs(pts[-1][0] - s) < 0.01:
            pts[-1] = (pts[-1][0], max(pts[-1][1], z))
        else:
            pts.append((s, z))
    if len(pts) <= 2:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, p, b = out[-1], pts[i], pts[i + 1]
        f = (p[0] - a[0]) / (b[0] - a[0])
        if abs(a[1] + f * (b[1] - a[1]) - p[1]) > tol:
            out.append(p)
    out.append(pts[-1])
    return out


def smooth(samples: list[float], width: float = CURVE_M, step: float = STEP_M) -> list[float]:
    """Moving average over `width` (vertical curves); values beyond the ends repeat the end."""
    k = int(round(width / step / 2.0))
    n = len(samples)
    out = []
    for i in range(n):
        acc = 0.0
        for j in range(i - k, i + k + 1):
            acc += samples[min(max(j, 0), n - 1)]
        out.append(acc / (2 * k + 1))
    return out


def _stations(L: float, step: float = STEP_M) -> list[float]:
    n = max(int(L / step), 1)
    out = [i * step for i in range(n + 1) if i * step < L - 0.5]
    return out + [L]


def _smoothstep(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def _turn(Q, a, b, R: float):
    """The fillet of radius R at corner Q, coming in along unit a and leaving along unit b:
    (its tangent length, its points from start to end)."""
    phi = M.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1])
    if abs(phi) < 1e-9:
        return 0.0, [tuple(Q)]
    t = R * M.tan(abs(phi) / 2.0)
    S = (Q[0] - a[0] * t, Q[1] - a[1] * t)
    side = 1.0 if phi > 0 else -1.0
    K = (S[0] - a[1] * R * side, S[1] + a[0] * R * side)
    rx, ry = S[0] - K[0], S[1] - K[1]
    n = max(int(abs(phi) * R / STEP_M) + 1, 2)
    pts = []
    for i in range(n + 1):
        al = phi * i / n
        c, s = M.cos(al), M.sin(al)
        pts.append((K[0] + rx * c - ry * s, K[1] + rx * s + ry * c))
    return t, pts


def _fillet_path(a0, corners: list, end, radii) -> list | None:
    """A path through `corners` rounded with the given radii, from the first fillet's start
    (coming in along unit a0) to `end`; None when two fillets do not fit on a leg."""
    pts: list = []
    a = a0
    prev = None
    nxt = corners[1:] + [end]
    for Q, N, R in zip(corners, nxt, radii):
        L = _d(Q, N)
        if L <= 1.0:
            return None
        b = ((N[0] - Q[0]) / L, (N[1] - Q[1]) / L)
        t, arc = _turn(Q, a, b, R)
        if prev is not None and prev[1] + t > _d(prev[0], Q) - 1.0:
            return None
        pts += arc
        prev = (Q, t)
        a = b
    if prev[1] > _d(prev[0], end) - 1.0:
        return None
    pts.append(tuple(end))
    return pts


def _near(P: np.ndarray, pts, cum) -> tuple[np.ndarray, np.ndarray]:
    """For points P (k x 2): the distance to the polyline pts (rounded to 1e-6 m) and the arc
    length of its nearest point (the first segment on a tie)."""
    A = np.asarray(pts[:-1], dtype=float)
    D = np.asarray(pts[1:], dtype=float) - A
    L2 = D[:, 0] * D[:, 0] + D[:, 1] * D[:, 1]
    PX = P[:, 0][:, None] - A[:, 0][None, :]
    PY = P[:, 1][:, None] - A[:, 1][None, :]
    t = (PX * D[:, 0][None, :] + PY * D[:, 1][None, :]) / np.where(L2 > 0, L2, 1.0)[None, :]
    t = np.where(L2[None, :] > 0, np.clip(t, 0.0, 1.0), 0.0)
    X = PX - t * D[:, 0][None, :]
    Y = PY - t * D[:, 1][None, :]
    dd = np.round(np.sqrt(X * X + Y * Y), 6)
    j = np.argmin(dd, axis=1)
    k = np.arange(len(P))
    seg = np.asarray(cum[1:], dtype=float) - np.asarray(cum[:-1], dtype=float)
    return dd[k, j], np.asarray(cum[:-1], dtype=float)[j] + t[k, j] * seg[j]


def _samples(pts, step: float = FLY_SAMPLE_M) -> tuple[list[float], np.ndarray]:
    """Stations every `step` m along a polyline (and its end) and the points there."""
    cum = _cum(pts)
    qs = [i * step for i in range(int(cum[-1] / step) + 1)]
    if cum[-1] - qs[-1] > 0.01:
        qs.append(cum[-1])
    P = np.asarray([_at(pts, cum, q)[0] for q in qs], dtype=float)
    return qs, P


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

@dataclass
class Run:
    id: str
    segs: list               # [(segment row, reversed)]
    nodes: list              # node ids n0..nk
    branch_of: str | None = None   # a ground highway rising to the deck of this run
    pts: list = field(default_factory=list)
    cum: list = field(default_factory=list)
    s_nodes: list = field(default_factory=list)
    prof: list = field(default_factory=list)   # [(s, z)]
    end_z: list = field(default_factory=list)
    level: int = 1

    def build_line(self) -> None:
        pts: list = []
        s_nodes = [0.0]
        for sg, rev in self.segs:
            cl = [tuple(p) for p in sg["centerline"]]
            if rev:
                cl = cl[::-1]
            pts += cl if not pts else cl[1:]
            s_nodes.append(_cum(pts)[-1])
        self.pts = pts
        self.cum = _cum(pts)
        self.s_nodes = s_nodes

    @property
    def L(self) -> float:
        return self.cum[-1]

    def z(self, s: float) -> float:
        return _z_at(self.prof, s)


class Elev:
    def __init__(self, ctx, net):
        self.ctx = ctx
        self.net = net
        self.pos = {n["id"]: (n["position"][0], n["position"][1]) for n in net.nodes}
        self.node = {n["id"]: n for n in net.nodes}
        self.inc: dict[str, list] = {}
        for s in net.segments:
            for n in (s["start"], s["end"]):
                self.inc.setdefault(n, []).append(s)
        for n in self.inc:
            self.inc[n].sort(key=lambda s: s["id"])
        self.notes: list[str] = []
        self.runs: list[Run] = []
        self.kind: dict = {}          # (run id, node) -> cross | tee | branch | plain | split
        self.ramps: list[dict] = []
        self.icx: list[dict] = []
        self.avenue_cuts: dict = {}   # avenue segment id -> [terminal points]
        self.stubs: dict = {}         # (avenue seg id, node) -> stub end point
        self.trim: dict = {}          # (avenue seg id, node) -> terminal it ends at
        self.cut_pts: dict = {}       # run id -> [stations where the run is cut]
        self.run_n = 0
        self.forced: set[str] = set()
        self.stack_plan: dict = {}     # M12: stack node -> its plan (`plan_stacks`)
        self.stack_notes: list[str] = []

    def reset(self) -> None:
        self.failed: dict = {}
        self.kind, self.ramps, self.icx = {}, [], []
        self.avenue_cuts, self.stubs, self.trim, self.cut_pts = {}, {}, {}, {}
        self.gcuts: dict = {}         # M12: ground corridor id -> stations of ramp ends on it

    # -- graph helpers -----------------------------------------------------------------------

    def other(self, s, n) -> str:
        return s["end"] if s["start"] == n else s["start"]

    def leg_dir(self, s, n) -> tuple[float, float]:
        """Unit direction of segment s leaving node n (over its first 20 m)."""
        cl = [tuple(p) for p in s["centerline"]]
        pts = cl if s["start"] == n else cl[::-1]
        p0 = pts[0]
        for b in pts[1:]:
            if _d(p0, b) >= 20.0 or b == pts[-1]:
                L = _d(p0, b)
                if L > 0:
                    return ((b[0] - p0[0]) / L, (b[1] - p0[1]) / L)
        return (1.0, 0.0)

    def is_elev(self, s) -> bool:
        return s["road_class"] == "highway" and bool(s["attrs"].get("elevated"))

    # -- 0. selection ------------------------------------------------------------------------

    def select(self, spec, weights: dict) -> None:
        """Which highway stretches go up: along each highway corridor (segments joined
        straight on through the nodes) the window long enough for two end ramps with the
        densest districts under it and no node that would bring it down; windows taken by
        density until `highways.elevated_share` of the highway length is up."""
        hw = sorted((s for s in self.net.segments if s["road_class"] == "highway"),
                    key=lambda s: s["id"])
        for s in hw:
            s["attrs"]["elevated"] = False
        # traced roads stay as drawn (their own `elevated road` layer marks decks)
        hw = [s for s in hw if "pinned" not in s["attrs"]]
        share = spec.highways.elevated_share
        total = sum(s["attrs"]["length_m"] for s in hw)
        if not hw or share <= 0:
            return
        corridors = self.chains(hw)
        lmin = 2.0 * ramp_run(LEVEL_Z[1]) + PLATEAU_M + 120.0
        target = share * total
        self.prim = [(LineString(s["centerline"]), s) for s in self.net.segments]
        self.prim_tree = shapely.STRtree([ln for ln, _ in self.prim])
        cands = []
        for ci, (segs, nodes) in enumerate(corridors):
            run = Run("probe", segs, nodes)
            run.build_line()
            run.prof = [(0.0, LEVEL_Z[1]), (run.L, LEVEL_Z[1])]
            ok_node, crossing = [], []
            for k in range(1, len(nodes) - 1):
                _, u = _at(run.pts, run.cum, run.s_nodes[k])
                kd = self.node_kind(nodes[k], {segs[k - 1][0]["id"], segs[k][0]["id"]}, u)
                ok_node.append(kd != "split")
                # how many ramps would fit there (on a deck all along the corridor)
                crossing.append(self.ramp_potential(run, k, kd) if kd in ("cross", "tee")
                                else 0)
            n = len(segs)
            off = [self.node[x]["attrs"].get("kind") in ("exit", "edge") for x in nodes]
            best = None
            for i in range(n):
                for j in range(i, n):
                    if not all(ok_node[i:j]):
                        break
                    L = run.s_nodes[j + 1] - run.s_nodes[i]
                    ramps = (0 if off[i] else 1) + (0 if off[j + 1] else 1)
                    if L < ramps * ramp_run(LEVEL_Z[1]) + PLATEAU_M + 120.0:
                        continue
                    if L > max(target, lmin) * 1.5:
                        break
                    w = sum(weights.get(segs[k][0]["id"], 0.0) * segs[k][0]["attrs"]["length_m"]
                            for k in range(i, j + 1))
                    # crossings with room for a diamond on both sides (a side that leaves
                    # the map stays up)
                    room = 0
                    for k in range(i + 1, j + 1):
                        a_ = math.inf if off[i] else run.s_nodes[k] - run.s_nodes[i]
                        b_ = math.inf if off[j + 1] else run.s_nodes[j + 1] - run.s_nodes[k]
                        if crossing[k - 1] and min(a_, b_) >= DIAMOND_ROOM_M:
                            room += crossing[k - 1]
                    key = (-min(room, 8), -round(w / L, 6), -round(L, 2), i)
                    if best is None or key < best[0]:
                        best = (key, i, j, L)
            if best is not None:
                cands.append((best[0], ci, best[1], best[2], best[3]))
        acc = 0.0
        for key, ci, i, j, L in sorted(cands):
            if acc >= target * 0.85:
                break
            segs, _ = corridors[ci]
            for k in range(i, j + 1):
                segs[k][0]["attrs"]["elevated"] = True
            acc += L

    def ramp_potential(self, run: Run, k: int, kd: str) -> int:
        """Ramps that would fit at node k of a probe run (a full deck all along it): its
        terminals, their ramps' room, water, roads and reserves; not each other."""
        n = run.nodes[k]
        on = {run.segs[k - 1][0]["id"], run.segs[k][0]["id"]}
        legs = [s for s in self.inc[n] if s["id"] not in on]
        hw_w = max(s["width_m"] for s, _ in run.segs)
        o = hw_w / 2.0 + RAMP_GAP + RAMP_W / 2.0
        _, u = _at(run.pts, run.cum, run.s_nodes[k])
        saved = (self.ramps, self.cut_pts)
        self.ramps, self.cut_pts = [], {}
        count = 0
        try:
            for leg in legs:
                v = self.leg_dir(leg, n)
                sigma = 1 if u[0] * v[1] - u[1] * v[0] > 0 else -1
                t = self._terminal(run, k, leg, sigma, o)
                if t is None:
                    continue
                T, sT, skew, along = t
                if skew < MIN_SKEW_SIN or self._terminal_ok(leg, n, T, along):
                    continue
                for kind in ("off", "on"):
                    res, _ = self._ramp(run, T, sT, sigma, kind, hw_w)
                    if res is not None and self._ramp_clear(res[0], run, legs, T, hw_w) is None:
                        count += 1
        finally:
            self.ramps, self.cut_pts = saved
        return count * (2 if kd == "tee" else 1)

    def chains(self, segs: list) -> list[tuple[list, list]]:
        """Maximal chains of the given segments, joined straight on through the nodes (the
        straightest pair where three or more meet): [(segs with reversed flags, nodes)]."""
        ids = {s["id"] for s in segs}
        pair: dict = {}
        for n in sorted(self.inc):
            legs = [s for s in self.inc[n] if s["id"] in ids]
            if len(legs) < 2:
                continue
            best = None
            for i, a in enumerate(legs):
                for b in legs[i + 1:]:
                    if a["id"] == b["id"]:
                        continue
                    ua, ub = self.leg_dir(a, n), self.leg_dir(b, n)
                    key = (round(ua[0] * ub[0] + ua[1] * ub[1], 9), a["id"], b["id"])
                    if best is None or key < best[0]:
                        best = (key, a, b)
            if best is None:
                continue
            _, a, b = best
            pair[(n, a["id"])] = b
            pair[(n, b["id"])] = a
        seen: set[str] = set()
        out = []
        for s0 in sorted(segs, key=lambda s: s["id"]):
            if s0["id"] in seen:
                continue
            cur, at = s0, s0["start"]
            guard = 0
            while (at, cur["id"]) in pair and guard < 10000:
                prev = pair[(at, cur["id"])]
                if prev["id"] == s0["id"]:
                    break
                at = self.other(prev, at)
                cur = prev
                guard += 1
            chain, nodes = [], [at]
            n, s = at, cur
            while s is not None and s["id"] not in seen:
                seen.add(s["id"])
                rev = s["end"] == n and s["start"] != n
                chain.append((s, rev))
                n = self.other(s, n)
                nodes.append(n)
                s = pair.get((n, s["id"]))
            out.append((chain, nodes))
        return out

    # -- 1. runs ------------------------------------------------------------------------------

    def make_runs(self) -> None:
        el = [s for s in self.net.segments if self.is_elev(s)]
        for segs, nodes in self.chains(el):
            self.runs.append(self.new_run(segs, nodes))

    def new_run(self, segs, nodes, branch_of=None) -> Run:
        self.run_n += 1
        r = Run(f"run{self.run_n:02d}", segs, nodes, branch_of)
        r.build_line()
        return r

    # -- 2. nodes -----------------------------------------------------------------------------

    def classify(self, r: Run, k: int) -> str:
        _, u = _at(r.pts, r.cum, r.s_nodes[k])
        return self.node_kind(r.nodes[k], {r.segs[k - 1][0]["id"], r.segs[k][0]["id"]}, u)

    def node_kind(self, n: str, on: set, u) -> str:
        """What a node inside a run (its two run legs `on`, run direction u) becomes:
        plain, cross, tee, branch or split."""
        others = [s for s in self.inc[n] if s["id"] not in on]
        if not others:
            return "plain"
        plan = self.stack_plan.get(n)
        if plan is not None and on == set(plan["lift"]):
            return "stack"
        if n in self.forced:
            return "split"
        cls = {s["road_class"] for s in others}
        if cls == {"avenue"}:
            if len(others) == 1:
                v = self.leg_dir(others[0], n)
                return "tee" if abs(u[0] * v[1] - u[1] * v[0]) >= OVERPASS_SKEW_SIN else \
                    "split"
            if len(others) == 2:
                sides = []
                vs = [self.leg_dir(s, n) for s in others]
                for v in vs:
                    sides.append(u[0] * v[1] - u[1] * v[0] > 0)
                straight = vs[0][0] * vs[1][0] + vs[0][1] * vs[1][1] <= -STRAIGHT_COS
                skew = min(abs(u[0] * v[1] - u[1] * v[0]) for v in vs)
                return "cross" if sides[0] != sides[1] and straight and \
                    skew >= OVERPASS_SKEW_SIN else "split"
            return "split"
        if cls == {"highway"}:
            if len(others) == 1 and not self.is_elev(others[0]):
                # a ground highway stem crossing under at 45 degrees or more: a trumpet
                v = self.leg_dir(others[0], n)
                if abs(u[0] * v[1] - u[1] * v[0]) >= MIN_SKEW_SIN:
                    return "tee"
            return "branch"
        return "split"

    def end_kind(self, r: Run, end: int) -> str:
        """ground | edge (off the map) | deck (on another run's deck)."""
        n = r.nodes[0 if end == 0 else -1]
        if r.branch_of is not None and end == 1:
            return "deck"
        kind = self.node[n]["attrs"].get("kind")
        if kind in ("exit", "edge"):
            return "edge"
        for o in self.runs:
            if o is r or o.branch_of is not None:
                continue
            if n in o.nodes[1:-1] and self.kind.get((o.id, n)) == "branch":
                return "deck"
            if len(o.nodes) > 1 and o.nodes[0] == o.nodes[-1] == n:
                return "deck"
        return "ground"

    def split(self, r: Run, k: int) -> list[Run]:
        a = self.new_run(r.segs[:k], r.nodes[:k + 1], r.branch_of)
        b = self.new_run(r.segs[k:], r.nodes[k:], r.branch_of)
        return [x for x in (a, b) if x.segs]

    def drop(self, r: Run) -> None:
        for s, _ in r.segs:
            s["attrs"]["elevated"] = False

    def settle(self) -> None:
        """Split runs at nodes that cannot stay under or beside the deck, add the branch runs
        of ground highways, drop what is too short; until nothing changes."""
        full = ramp_run(LEVEL_Z[1])
        clear_at = ramp_run(CLEAR_M + DECK_M + 0.3)
        for _ in range(30):
            changed = False
            # branch runs follow their main runs
            self.runs = [r for r in self.runs if r.branch_of is None]
            out = []
            for r in self.runs:
                ends = [self.end_kind(r, 0), self.end_kind(r, 1)]
                loop = len(r.nodes) > 2 and r.nodes[0] == r.nodes[-1]
                bad = None
                for k in range(1, len(r.nodes) - 1):
                    kd = self.classify(r, k)
                    self.kind[(r.id, r.nodes[k])] = kd
                    if kd == "plain":
                        continue
                    need = full if kd == "branch" else \
                        STACK_LIFT_M if kd == "stack" else clear_at
                    s = r.s_nodes[k]
                    if kd == "split" or (not loop and (
                            (ends[0] == "ground" and s < need) or
                            (ends[1] == "ground" and r.L - s < need))):
                        bad = k
                        break
                if bad is not None:
                    out += self.split(r, bad)
                    changed = True
                    continue
                if not loop:
                    need = PLATEAU_M + sum(full for e in ends if e == "ground")
                    if r.L < need:
                        self.drop(r)
                        changed = True
                        continue
                out.append(r)
            self.runs = out
            if changed:
                continue
            # ground highway branches rise to the deck on their own segment
            branches = []
            for r in self.runs:
                for k in range(1, len(r.nodes) - 1):
                    if self.kind.get((r.id, r.nodes[k])) != "branch":
                        continue
                    n = r.nodes[k]
                    on = {r.segs[k - 1][0]["id"], r.segs[k][0]["id"]}
                    for s in self.inc[n]:
                        if s["id"] in on or self.is_elev(s):
                            continue
                        far = self.other(s, n)
                        # the branch runs from its far node up to n
                        br = self.new_run([(s, s["start"] == n)], [far, n], branch_of=r.id)
                        far_kind = self.node[far]["attrs"].get("kind")
                        far_up = any(far in o.nodes for o in self.runs)
                        if far_up or (br.L < full and far_kind not in ("exit", "edge")):
                            # too short to rise: the main run comes down here
                            self.runs.remove(r)
                            self.runs += self.split(r, k)
                            changed = True
                            break
                        branches.append(br)
                    if changed:
                        break
                if changed:
                    break
            if changed:
                continue
            self.runs += branches
            return
        self.notes.append("elevated runs did not settle in 30 rounds")

    # -- 3. profiles --------------------------------------------------------------------------

    def seg_profile(self, r: Run, ss) -> list[float]:
        """Bridge decks (the M1b profile of each segment) at the stations ss of a run."""
        out = [0.0] * len(ss)
        for (sg, rev), a, b in zip(r.segs, r.s_nodes, r.s_nodes[1:]):
            prof = _tuples(sg["z_profile"])
            L = b - a
            for i, s in enumerate(ss):
                if a - 0.01 <= s <= b + 0.01:
                    t = s - a
                    out[i] = max(out[i], _z_at(prof, L - t if rev else t))
        return out

    def deck_z_at(self, n: str, r: Run) -> float:
        """z of the run whose deck holds node n (where r ends on it)."""
        for o in self.runs:
            if o is r or not o.prof:
                continue
            if n in o.nodes[1:-1]:
                return o.z(o.s_nodes[o.nodes.index(n)])
            if len(o.nodes) > 2 and o.nodes[0] == o.nodes[-1] == n:
                return o.z(0.0)
        return LEVEL_Z[1]

    def profiles(self) -> None:
        """z along every run: the deck level between the ends, ramps at the ground ends,
        the deck it ends on at a deck end, bridge decks kept, other raised roads crossed
        with clearance (a level-2 hump where it must pass over one)."""
        done: list[tuple] = []
        raised = [(LineString(s["centerline"]), _tuples(s["z_profile"]), s["id"])
                  for s in self.net.segments if not self.is_elev(s) and
                  any(z > 0.5 for _, z in _tuples(s["z_profile"]))]
        self.lift: list = []      # (segment id, (s, s, z)): roads to raise over a run
        for r in self.runs:
            r.prof = []
        order = sorted(self.runs, key=lambda r: (
            sum(self.end_kind(r, e) == "deck" for e in (0, 1)), r.id))
        for r in order:
            ends = [self.end_kind(r, 0), self.end_kind(r, 1)]
            loop = len(r.nodes) > 2 and r.nodes[0] == r.nodes[-1]
            ss = _stations(r.L)
            plateau = LEVEL_Z[1]
            end_val = [self.deck_z_at(r.nodes[0 if e == 0 else -1], r)
                       if ends[e] == "deck" else None for e in (0, 1)]
            line = LineString(r.pts)
            bridges = self.seg_profile(r, ss)
            base = list(zip(ss, bridges))
            need = []
            crossings = []
            meets = []      # (other road id or None, its station, its z, station on the run)
            for ln, pr, oid in raised + done:
                if G.apart(line, ln) or not line.crosses(ln):
                    continue
                for p in G_points(line.intersection(ln)):
                    t_o = ln.project(Point(p))
                    meets.append((oid, t_o, _z_at(pr, t_o), _project(r.pts, r.cum, p)[0]))
            on = {sg["id"] for sg, _ in r.segs}
            for k in range(1, len(r.nodes) - 1):
                if self.kind.get((r.id, r.nodes[k])) not in ("cross", "tee", "stack"):
                    continue
                for o in self.inc[r.nodes[k]]:
                    # the avenue legs of an overpass (they cross the run there once
                    # rebuilt), raised by a bridge approach
                    if o["id"] in on or self.is_elev(o):
                        continue
                    t_o = 0.0 if o["start"] == r.nodes[k] else _cum(o["centerline"])[-1]
                    z_o = _z_at(_tuples(o["z_profile"]), t_o)
                    if z_o > 0.5:
                        meets.append((o["id"], t_o, z_o, r.s_nodes[k]))
            for oid, t_o, z_o, s_here in meets:
                z_r = max(plateau, _z_at(base, s_here))
                if under_m(z_o) - z_r >= CLEAR_M or under_m(z_r) - z_o >= CLEAR_M:
                    continue      # one passes high enough over the other
                # over it, where the run's ground ends leave the room to climb
                room = math.inf
                for e, d in ((0, s_here), (1, r.L - s_here)):
                    if not loop and ends[e] == "ground":
                        room = min(room, GRADE * max(0.0, d - FLAT_M - CURVE_M / 2.0))
                if room >= z_o + CLEAR_M + DECK_M or oid is None:
                    need.append((s_here, z_o + CLEAR_M + DECK_M))
                else:
                    crossings.append((oid, t_o, s_here))
            raw = []
            for s in ss:
                z = plateau
                for e, d in ((0, s), (1, r.L - s)):
                    if loop:
                        continue
                    if ends[e] == "ground":
                        z = min(z, GRADE * max(0.0, d - FLAT_M))
                    elif end_val[e] is not None:
                        gap = end_val[e] - plateau
                        step = min(abs(gap), GRADE * max(0.0, d - FLAT_M))
                        z = end_val[e] - math.copysign(step, gap) if gap else z
                raw.append(z)
            for sn, zn in need:
                for i, s in enumerate(ss):
                    raw[i] = max(raw[i], zn - GRADE * max(0.0, abs(s - sn) - CURVE_M / 2.0))
            sm = smooth(raw)
            z = [max(a_, b_) for a_, b_ in zip(sm, bridges)]
            for e, i in ((0, 0), (1, -1)):
                if not loop and ends[e] == "ground":
                    z[i] = bridges[i]
                elif end_val[e] is not None:
                    z[i] = max(end_val[e], bridges[i])
            r.prof = compress(list(zip(ss, z)))
            r.level = 2 if need and max(z) >= LEVEL_Z[2] - 2.0 else 1
            done.append((line, r.prof, None))
            for oid, t_o, s_here in crossings:
                # the other road rises over the run instead
                self.lift.append((oid, (G.q(t_o), G.q(t_o),
                                        G.q(r.z(s_here) + CLEAR_M + BRIDGE_DECK_M))))

    # -- 4. interchanges ---------------------------------------------------------------------

    def interchanges(self) -> None:
        prim = [(LineString(s["centerline"]), s) for s in self.net.segments]
        self.prim_tree = shapely.STRtree([ln for ln, _ in prim])
        self.prim = prim
        # M12: stacks first (the other interchanges on their highways fit round them)
        for r in sorted(self.runs, key=lambda r: r.id):
            if r.branch_of is not None:
                continue
            self.cut_pts.setdefault(r.id, [])
            for k in range(1, len(r.nodes) - 1):
                if self.kind.get((r.id, r.nodes[k])) == "stack":
                    self.stack_ic(r, k)
        for r in sorted(self.runs, key=lambda r: r.id):
            if r.branch_of is not None:
                continue
            self.cut_pts.setdefault(r.id, [])
            for k in range(1, len(r.nodes) - 1):
                n = r.nodes[k]
                kd = self.kind.get((r.id, n))
                if kd in ("cross", "tee"):
                    self.interchange(r, k, kd)
                elif kd == "branch":
                    self.cut_pts[r.id].append(r.s_nodes[k])
                    self.icx.append({"id": f"ic{len(self.icx) + 1:02d}", "template": "direct",
                                     "node": n, "run": r.id, "ramps": []})

    def _terminal(self, r: Run, k: int, leg, sigma: int, o: float):
        """Where the offset line of side sigma meets the avenue leg: (T, station on the run,
        skew sine), or None."""
        n = r.nodes[k]
        sN = r.s_nodes[k]
        C, u = _at(r.pts, r.cum, sN)
        nx, ny = -u[1], u[0]
        cl = [tuple(p) for p in leg["centerline"]]
        A = cl if leg["start"] == n else cl[::-1]
        lat = [((p[0] - C[0]) * nx + (p[1] - C[1]) * ny) * sigma for p in A]
        acc = 0.0
        for i in range(len(A) - 1):
            seg = _d(A[i], A[i + 1])
            if lat[i] <= o <= lat[i + 1] and lat[i + 1] > lat[i]:
                f = (o - lat[i]) / (lat[i + 1] - lat[i])
                T = (A[i][0] + f * (A[i + 1][0] - A[i][0]), A[i][1] + f * (A[i + 1][1] - A[i][1]))
                along = acc + f * seg
                if along > 80.0:
                    return None
                v = ((A[i + 1][0] - A[i][0]) / seg, (A[i + 1][1] - A[i][1]) / seg)
                skew = abs(u[0] * v[1] - u[1] * v[0])
                T = G.qpoint(T)
                return T, sN + (T[0] - C[0]) * u[0] + (T[1] - C[1]) * u[1], skew, along
            acc += seg
            if acc > 80.0:
                return None
        return None

    def _ramp(self, r: Run, T, sT: float, sigma: int, kind: str, hw_w: float):
        """The shortest ramp between terminal T and the run on side sigma: its polyline (in
        driving direction), profile and the run station of its deck end; or (None, reason).
        The ramp follows the deck through the taper (sloped where the run itself rises),
        then falls to the terminal at the design grade."""
        dirn = 1 if sigma == -1 else -1      # right-hand traffic
        o = hw_w / 2.0 + RAMP_GAP + RAMP_W / 2.0
        top = max(z for _, z in r.prof)
        lo_span = TAPER_M + 10.0 + FLAT_M + CURVE_M
        hi_span = ramp_run(top) + TAPER_M + 10.0
        why = "no room"
        span = lo_span
        while span <= hi_span + 0.01:
            s_far = sT - dirn * span if kind == "off" else sT + dirn * span
            span += 10.0
            if not (0.0 < s_far < r.L):
                why = "off the run"
                break
            z_far = r.z(s_far)
            if z_far < 2.0:
                why = "diverge too low"
                continue
            if any(abs(sn - s_far) < NODE_GAP_M for sn in r.s_nodes + self.cut_pts.get(r.id, [])):
                why = "too near another node"
                continue
            P, _ = _at(r.pts, r.cum, s_far)
            if G.dist(Point(P), self.ctx.wet) < 30.0:
                why = "diverge over water"
                continue
            n_st = max(int(abs(sT - s_far) / 10.0), 2)
            pts = []
            for i in range(n_st + 1):
                st = s_far + (sT - s_far) * i / n_st
                C, u = _at(r.pts, r.cum, st)
                off = o * _smoothstep(abs(st - s_far) / TAPER_M)
                pts.append(G.qpoint((C[0] - u[1] * off * sigma, C[1] + u[0] * off * sigma)))
            pts[-1] = T
            pts = _dedupe(pts)
            Lr = _cum(pts)[-1]
            sgn = 1.0 if sT > s_far else -1.0
            qs = _stations(Lr)
            raw, ok = [], True
            for qd in qs:
                z_run = r.z(s_far + sgn * qd)
                fall = GRADE * max(0.0, Lr - qd - FLAT_M)
                if qd <= TAPER_M and fall < z_run - 0.01:
                    ok = False
                    break
                raw.append(z_run if qd <= TAPER_M else min(z_run, fall))
            if not ok:
                why = "descends on the taper"
                continue
            z = smooth(raw)
            for i, qd in enumerate(qs):
                if qd <= TAPER_M - CURVE_M / 2.0:
                    z[i] = raw[i]
            z[0], z[-1] = z_far, 0.0
            prof = compress(list(zip(qs, z)))
            steep = any(s1 > s0 and abs(z1 - z0) / (s1 - s0) > MAX_GRADE - 1e-9
                        for (s0, z0), (s1, z1) in zip(prof, prof[1:]))
            if steep:
                why = "too steep"
                continue
            if kind == "on":
                pts = pts[::-1]
                prof = [(G.q(Lr - qd), zz) for qd, zz in reversed(prof)]
                prof[0] = (0.0, prof[0][1])
            return (pts, prof, s_far), None
        return None, why

    def _ramp_clear(self, pts, r: Run, legs, T, hw_w: float, tail_m: float | None = None,
                    full=None) -> str | None:
        """Why a ramp polyline does not fit (None when it does). Its last `tail_m` toward the
        terminal may come near the avenue it lands on (a loop's lead runs beside it). `full`
        (the whole ramp and its profile) lets it pass under or over a flyover."""
        ctx = self.ctx
        line = LineString(pts)
        half = RAMP_W / 2.0
        if G.dist(line, ctx.wet) < half + 1.0:
            return "water"
        if not ctx.closed_all.is_empty and G.dist(line, ctx.closed_all) < half:
            return "reserve or open land"
        if not ctx.canvas_inner.contains(line):
            return "map edge"
        run_ids = {s["id"] for s, _ in r.segs}
        leg_ids = {s["id"] for s in legs}
        for i in sorted(int(x) for x in self.prim_tree.query(line.buffer(40.0))):
            ln, s = self.prim[i]
            if s["id"] in run_ids:
                continue
            need = s["width_m"] / 2.0 + half + 2.0
            if s["id"] in leg_ids:
                # the terminal end crosses the avenue: only the last stretch may
                d = need / MIN_SKEW_SIN + 2.0 if tail_m is None else tail_m
                tail = _tail_off(pts, d) if tuple(pts[-1]) == tuple(T) else \
                    _tail_off(pts[::-1], d)
                if tail is not None and G.dist(LineString(tail), ln) < need:
                    return f"crosses {s['id']}"
                continue
            if G.dist(line, ln) < need:
                return f"meets {s['id']}"
        for rp in self.ramps:
            if rp["T"] == T:
                continue
            if (rp.get("flyover") or rp.get("dir")) and full is not None:
                if not self._apart_in_z(full[0], full[1], rp):
                    return "another ramp"
                continue
            if G.dist(line, LineString(rp["pts"])) < RAMP_W + 1.0:
                return "another ramp"
        return None

    def _apart_in_z(self, pts, prof, rp) -> bool:
        """A ramp (pts, profile) and a flyover: wherever they come within a ramp's width plus
        1 m of each other, one passes over the other with the clearance and the deck."""
        if G.apart(LineString(pts), LineString(rp["pts"]), RAMP_W + 1.0):
            return True
        qs, P = _samples(pts)
        d, s_o = _near(P, rp["pts"], _cum(rp["pts"]))
        for i in np.nonzero(d < RAMP_W + 1.0)[0].tolist():
            dz = abs(_z_at(rp["prof"], float(s_o[i])) - _z_at(prof, qs[i]))
            if dz < CLEAR_M + DECK_M - 0.05:
                return False
        return True

    def _loop(self, r: Run, k: int, leg, sigma: int, kind: str, hw_w: float):
        """A 270 degree loop ramp (partial cloverleaf) on side sigma: an off loop leaves the
        deck just past the avenue and turns right round the quadrant beyond it down to the
        avenue; an on loop is its mirror before the avenue. Its radius is the one the climb
        needs. Returns ((polyline in driving direction, profile, run station of its deck end,
        terminal), None) or (None, reason)."""
        n = r.nodes[k]
        sN = r.s_nodes[k]
        _, u = _at(r.pts, r.cum, sN)
        v = self.leg_dir(leg, n)
        if abs(u[0] * v[1] - u[1] * v[0]) < LOOP_SKEW_SIN:
            return None, "loop: skewed crossing"
        dirn = 1 if sigma == -1 else -1             # right-hand traffic on side sigma
        o = hw_w / 2.0 + RAMP_GAP + RAMP_W / 2.0
        av = leg["width_m"] / 2.0
        x_d = av + RAMP_GAP + 2.0                   # diverge just past the avenue's edge
        mirror = 1.0 if kind == "off" else -1.0
        s_far = sN + dirn * mirror * x_d
        if not 0.0 < s_far < r.L:
            return None, "loop: off the run"
        z_d = r.z(s_far)
        if z_d < 2.0:
            return None, "loop: deck too low"
        R = max(LOOP_MIN_R, 5.0 * math.ceil((ramp_run(z_d) - LOOP_LEAD_M) /
                                            (1.5 * math.pi) / 5.0))
        # the tightest loop: its start moves along the deck (5 m at a time) until the circle
        # clears the run and the avenue it comes back to
        leg_line = LineString(leg["centerline"])
        run_line = LineString(r.pts)
        need_av = av + RAMP_W / 2.0 + LOOP_CLEAR_M
        need_run = hw_w / 2.0 + RAMP_W / 2.0 + 1.0
        found = None
        x1 = x_d + 30.0
        while x1 <= x_d + 30.0 + 3.0 * R:
            s1 = sN + dirn * mirror * x1
            if not 0.0 < s1 < r.L:
                break
            nt = max(int((x1 - x_d) / STEP_M), 2)
            pts = []
            for i in range(nt + 1):
                st = s_far + (s1 - s_far) * i / nt
                Cs, us = _at(r.pts, r.cum, st)
                off = o * _smoothstep(i / nt)
                pts.append((Cs[0] - us[1] * off * sigma, Cs[1] + us[0] * off * sigma))
            C1, u1 = _at(r.pts, r.cum, s1)
            hx, hy = dirn * u1[0], dirn * u1[1]        # traffic heading there
            if mirror < 0:
                hx, hy = -hx, -hy                       # built backwards from the merge
            rx, ry = -u1[1] * sigma, u1[0] * sigma      # outward there
            P1 = pts[-1]
            cx_, cy_ = P1[0] + rx * R, P1[1] + ry * R
            for deg in range(5, 271, 5):
                a = M.radians(float(deg))
                # from P1 (radial -r) round toward the heading and outward
                pts.append((cx_ + R * (M.sin(a) * hx - M.cos(a) * rx),
                            cy_ + R * (M.sin(a) * hy - M.cos(a) * ry)))
            arc = LineString(pts[nt + 2:])
            if G.dist(arc, run_line) >= need_run and G.dist(arc, leg_line) >= need_av:
                found = (pts, nt, rx, ry)
                break
            x1 += 5.0
        if found is None:
            return None, "loop: no room beside the avenue"
        pts, nt, rx, ry = found
        end = pts[-1]
        y_T = o + R - LOOP_LEAD_M
        t_ = self._terminal(r, k, leg, sigma, y_T)
        if t_ is None:
            return None, "loop: avenue leg too short"
        T, _, _, along = t_
        why = self._terminal_ok(leg, n, T, along)
        if why:
            return None, "loop: " + why
        # 10 m on straight off the loop (inward, toward the run), then to the terminal
        pts.append((end[0] - rx * 10.0, end[1] - ry * 10.0))
        pts = [G.qpoint(p) for p in pts]
        pts[0] = G.qpoint(_at(r.pts, r.cum, s_far)[0])
        arc = [G.qpoint(p) for p in found[0][nt:-1]]   # the loop alone
        pts = _dedupe(pts + [T])
        body = pts[nt:]          # off the deck (the taper is on it, over the avenue)
        # the profile in the off direction: on the deck along the taper, then down at the
        # design grade to the terminal
        Lr = _cum(pts)[-1]
        cum = _cum(pts)
        q1 = cum[nt]
        qs = _stations(Lr)
        raw = []
        for qd in qs:
            if qd <= q1:
                f = qd / q1 if q1 > 0 else 0.0
                raw.append(r.z(sN + dirn * mirror * (x_d + (x1 - x_d) * f)))
            else:
                raw.append(min(r.z(sN + dirn * mirror * x1), GRADE * max(0.0, Lr - qd - FLAT_M)))
        z = smooth(raw)
        for i, qd in enumerate(qs):
            if qd <= q1 - CURVE_M / 2.0:
                z[i] = raw[i]
        z[0], z[-1] = z_d, 0.0
        prof = compress(list(zip(qs, z)))
        if any(s1 > s0 and abs(z1 - z0) / (s1 - s0) > MAX_GRADE - 1e-9
               for (s0, z0), (s1, z1) in zip(prof, prof[1:])):
            return None, "loop: too steep"
        if kind == "on":
            pts, body = pts[::-1], body[::-1]
            prof = [(G.q(Lr - qd), zz) for qd, zz in reversed(prof)]
            prof[0] = (0.0, prof[0][1])
        return (pts, prof, s_far, T, body, arc), None

    def _loops(self, r: Run, k: int, n: str, leg, sigma: int, hw_w: float, legs, ic,
               kinds=("off", "on")) -> list:
        """The loop ramps that fit on side sigma (not yet added)."""
        out = []
        for kind in kinds:
            res, why = self._loop(r, k, leg, sigma, kind, hw_w)
            if res is not None:
                pts, prof, s_far, TL, body, arc = res
                why = self._ramp_clear(body, r, legs, TL, hw_w, LOOP_LEAD_M + 5.0,
                                       full=(pts, prof))
                if why is None and G.dist(LineString(pts), self.ctx.wet) < RAMP_W / 2.0 + 1.0:
                    why = "water"
                if why is None and any(abs(sn - s_far) < 1.0 for sn in
                                       self.cut_pts.get(r.id, [])):
                    why = "loop: another ramp end there"
                if why is None and any(G.dist(LineString(arc), LineString(o["arc"])) <
                                       RAMP_W + 1.0 for o in out):
                    why = "loop: the other loop"     # (their leads meet at the terminal)
            if why is not None:
                why = why.split(" rs")[0]
                self.failed[why] = self.failed.get(why, 0) + 1
                continue
            out.append({"pts": pts, "prof": prof, "kind": kind, "T": TL, "run": r.id,
                        "s_far": s_far, "ic": ic["id"], "sigma": sigma, "leg": leg["id"],
                        "node": n, "stub": False, "loop": True, "arc": arc})
        for rp in out:
            rp.pop("arc")
        return out

    def _stub_leg(self, r: Run, k: int, n: str, leg, hw_w: float, C, u, v) -> dict | None:
        """A trumpet's stem run on under the deck to the far side, as a leg the far loops come
        down to (past them: they must clear it all the way; it is cut back to their terminal
        once they are built), or None when there is no room for it."""
        sN = r.s_nodes[k]
        skew = abs(u[0] * v[1] - u[1] * v[0])
        o = hw_w / 2.0 + RAMP_GAP + RAMP_W / 2.0
        top = r.z(sN)
        R = max(LOOP_MIN_R, 5.0 * math.ceil((ramp_run(top) - LOOP_LEAD_M) /
                                            (1.5 * math.pi) / 5.0))
        y_e = o + 2.0 * R + 20.0
        Te = G.qpoint((C[0] - v[0] * y_e / skew, C[1] - v[1] * y_e / skew))
        stub = LineString([G.qpoint(C), Te])
        ctx = self.ctx
        if not ctx.dry_inner.contains(Point(Te)) or G.dist(stub, ctx.wet) <= 8.0 or (
                not ctx.closed_all.is_empty and G.dist(stub, ctx.closed_all) <= 8.0):
            self.failed["trumpet: no room for the stub"] = \
                self.failed.get("trumpet: no room for the stub", 0) + 1
            return None
        L = _d(G.qpoint(C), Te)
        return {"id": leg["id"], "centerline": [G.qpoint(C), Te], "start": n, "end": "",
                "width_m": leg["width_m"], "road_class": leg["road_class"],
                "attrs": {"length_m": G.q(L)}, "z_profile": [{"s": 0.0, "z": 0.0},
                                                            {"s": G.q(L), "z": 0.0}]}

    def _trumpet(self, r: Run, k: int, n: str, leg, sigma: int, hw_w: float, legs, ic,
                 virt) -> dict | None:
        """The two-loop trumpet (M7b, the fallback of `_trumpet_flyover`): the stem runs on
        under the deck to a stub on the far side (sigma), where a loop in each far quadrant
        comes down to it (the two left turns: far lanes to the stem, stem to the far lanes).
        The near lanes take the near ramps. Returns the far loops, the stub's end (their
        shared terminal) and the stem id, or None."""
        loops = self._loops(r, k, n, virt, sigma, hw_w, legs, ic)
        if len(loops) < 2 or tuple(loops[0]["T"]) != tuple(loops[1]["T"]):
            self.failed["trumpet: the far loops do not fit"] = \
                self.failed.get("trumpet: the far loops do not fit", 0) + 1
            return None
        for rp in loops:
            rp["stub"] = True
        return {"ramps": loops, "end": tuple(loops[0]["T"]), "leg": leg["id"]}

    # -- M8d: the trumpet's flyover ------------------------------------------------------------

    def _trumpet_flyover(self, r: Run, k: int, n: str, leg, sigma: int, hw_w: float, legs,
                         ic, virt, T_n) -> dict | None:
        """The textbook trumpet's far side (sigma): one loop and one flyover for the two left
        turns. The loop starts (or ends) at the stem's near terminal T_n, passes under the deck
        along the stem and turns round its quadrant to the far lanes; the flyover
        (`_flyover`) takes the other turn over the loop, the deck and the stem. The on loop
        with the off flyover first, then the reverse. Returns the two ramps and the near
        terminal (the stem ends there), or None."""
        for lk, fk in (("on", "off"), ("off", "on")):
            loops = self._loops(r, k, n, virt, sigma, hw_w, legs, ic, kinds=(lk,))
            if not loops:
                continue
            lp = self._through(loops[0], T_n)
            self.ramps.append(lp)
            fly, why = self._flyover(r, k, n, leg, sigma, fk, hw_w, T_n, ic)
            self.ramps.remove(lp)
            if fly is None:
                self.failed[why] = self.failed.get(why, 0) + 1
                continue
            return {"ramps": [lp, fly], "trim": tuple(T_n), "leg": leg["id"]}
        return None

    def _through(self, lp: dict, T_n) -> dict:
        """A trumpet loop run on from its terminal on the stub, under the deck along the stem,
        to the stem's near terminal (the ramp takes the stub's place)."""
        lp = dict(lp)
        D = G.q(_d(lp["T"], T_n))
        if lp["kind"] == "on":
            lp["pts"] = [tuple(T_n)] + [tuple(p) for p in lp["pts"]]
            lp["prof"] = [(0.0, 0.0)] + [(G.q(s + D), z) for s, z in lp["prof"]]
        else:
            L = lp["prof"][-1][0]
            lp["pts"] = [tuple(p) for p in lp["pts"]] + [tuple(T_n)]
            lp["prof"] = list(lp["prof"]) + [(G.q(L + D), 0.0)]
        lp["T"] = tuple(T_n)
        return lp

    def _flyover(self, r: Run, k: int, n: str, stem, sigma: int, kind: str, hw_w: float, T_n,
                 ic) -> tuple:
        """A trumpet's flyover on far side sigma (the loop is the last ramp so far). An off
        flyover leaves the far lanes before the stem (beyond the loop, which lies on that side
        too), climbs beside the deck, turns away from it over the loop (corner Q0), round
        (corner Q1) onto a line beside the stem on the side away from the loop, crosses the
        deck square, comes down beside the stem and turns into it at a terminal T_f (corner
        K2). An on flyover is its mirror (built the same way, then reversed). Its deck clears
        every road and ramp it passes over (`_fly_needs`), at the design grade with vertical
        curves, at most 6%; its own columns find room within `FLY_SPAN_M` (`_fly_span`).
        Returns (ramp, None) or (None, reason)."""
        sN = r.s_nodes[k]
        C, u = _at(r.pts, r.cum, sN)
        dirn = 1 if sigma == -1 else -1             # far lanes' traffic along u
        c = dirn * (1 if kind == "off" else -1)
        g = (c * u[0], c * u[1])                    # along the deck toward the stem
        f = (-u[1] * sigma, u[0] * sigma)           # to the far side
        v = self.leg_dir(stem, n)
        vf = -(v[0] * f[0] + v[1] * f[1])
        if vf < MIN_SKEW_SIN:
            return None, "flyover: skewed stem"
        m = (-v[1], v[0])                           # off the stem, away from the loop
        if m[0] * g[0] + m[1] * g[1] < 0:
            m = (-m[0], -m[1])
        o = hw_w / 2.0 + RAMP_GAP + RAMP_W / 2.0
        dd = stem["width_m"] / 2.0 + RAMP_W / 2.0 + FLY_GAP_M
        loop = self.ramps[-1]
        x_lo = min((p[0] - C[0]) * g[0] + (p[1] - C[1]) * g[1] for p in loop["pts"])
        y_hi = max((p[0] - C[0]) * f[0] + (p[1] - C[1]) * f[1] for p in loop["pts"])
        cl = [tuple(p) for p in stem["centerline"]]
        cl = cl if stem["start"] == n else cl[::-1]
        obst = self._fly_obstacles(C)
        mf = m[0] * f[0] + m[1] * f[1]
        why = "flyover: no room"
        # the bell (round the loop's outside) first, then the diagonal over the loop
        for shape, Y1, dx in (("bell", y_hi + 20.0, 25.0), ("bell", y_hi + 40.0, 45.0),
                              ("over", y_hi + 15.0, 15.0), ("over", y_hi + 35.0, 40.0)):
            t1 = (Y1 - dd * mf) / vf
            Q1 = (C[0] + dd * m[0] - t1 * v[0], C[1] + dd * m[1] - t1 * v[1])
            # in the node's frame (the deck may curve): the bell turns out square off the deck
            # (Q0) to its corner Qb dx short of the loop, round the loop to Q1; the diagonal
            # leaves the deck where its offset line is dx short of the loop
            Qb = (C[0] + (x_lo - dx) * g[0] + Y1 * f[0], C[1] + (x_lo - dx) * g[1] + Y1 * f[1])
            sQ0 = None
            if shape == "bell":
                st = _project(r.pts, r.cum, Qb)[0]
                if c * (st - sN) < 0.0 and 0.0 < st < r.L:
                    sQ0 = st
            else:
                for i in range(1, 400):
                    st = sN - c * 5.0 * i
                    if not 0.0 < st < r.L:
                        break
                    P, uu = _at(r.pts, r.cum, st)
                    x0 = (P[0] - uu[1] * o * sigma - C[0]) * g[0] + \
                        (P[1] + uu[0] * o * sigma - C[1]) * g[1]
                    if x0 <= x_lo - dx:
                        sQ0 = st
                        break
            if sQ0 is None:
                why = "flyover: off the run"
                continue
            P, uu = _at(r.pts, r.cum, sQ0)
            Q0 = (P[0] - uu[1] * o * sigma, P[1] + uu[0] * o * sigma)
            if shape == "bell":
                # out far enough for both turns (the bell and Q1 move out together)
                L0 = _d(Q0, Qb)
                need = FLY_R[0] + FLY_R[1] + 5.0
                if L0 < need:
                    Qb = (Q0[0] + (Qb[0] - Q0[0]) * need / L0,
                          Q0[1] + (Qb[1] - Q0[1]) * need / L0)
                    t1 = ((Qb[0] - C[0]) * f[0] + (Qb[1] - C[1]) * f[1] - dd * mf) / vf
                    Q1 = (C[0] + dd * m[0] - t1 * v[0], C[1] + dd * m[1] - t1 * v[1])
                mids, radii = [Qb, Q1], (FLY_R[0], FLY_R[1], FLY_R[1])
            else:
                mids, radii = [Q1], (FLY_R[0], FLY_R[1])
            res, why = self._fly_fit(r, k, c, sigma, o, (c * uu[0], c * uu[1]), Q0, sQ0, mids,
                                     radii, m, dd, cl, stem, n, obst, kind, ic, T_n)
            if res is not None:
                res["shape"] = shape
                return res, None
        return None, why

    def _fly_fit(self, r: Run, k: int, c: int, sigma: int, o: float, h0, Q0, sQ0: float, mids,
                 radii, m, dd: float, cl, stem, n: str, obst, kind: str, ic, T_n) -> tuple:
        """One flyover shape (its corners from Q0 to the stem's side): the landing T_f as near
        the deck as its fall allows, the diverge as near as its climb allows; checked whole."""
        ccum = _cum(cl)
        t_max = ccum[-1] - TERMINAL_GAP_M - 1.0
        tail = (dd - 1.0) * math.pi / 2.0 + 6.0

        def core_at(t2):
            Tp, ut = _at(cl, ccum, t2)
            Tf = G.qpoint(Tp)
            mt = (-ut[1], ut[0])
            if mt[0] * m[0] + mt[1] * m[1] < 0:
                mt = (-mt[0], -mt[1])
            K2 = (Tf[0] + dd * mt[0], Tf[1] + dd * mt[1])
            return Tf, _fillet_path(h0, [Q0] + mids + [K2], Tf, list(radii) + [dd - 1.0])

        if t_max < 100.0:
            return None, "flyover: stem too short"
        Tf, core = core_at(t_max)
        if core is None:
            return None, "flyover: turns do not fit"
        qs, need, _ = self._fly_needs(core, obst, r.id, stem["id"], 0.0, tail, own=True)
        L_core = qs[-1]
        L_req = max((q + FLAT_M + CURVE_M / 2.0 + z / GRADE + 5.0
                     for q, z in zip(qs, need) if z > 0.0), default=0.0)
        if L_req > L_core:
            return None, "flyover: stem too short"
        t2 = t_max - 5.0 * math.floor((L_core - L_req) / 5.0)
        Tf, core = core_at(t2)
        if core is None:
            return None, "flyover: turns do not fit"
        why = self._terminal_ok(stem, n, Tf, t2)
        if why:
            return None, "flyover: " + why
        qs, need, _ = self._fly_needs(core, obst, r.id, stem["id"], 0.0, tail, own=True)
        sF0 = sQ0 - c * _d(Q0, core[0])
        z0 = r.z(sF0)
        A = max([TAPER_M + 10.0] + [TAPER_M + CURVE_M / 2.0 + (z - z0) / GRADE - q + 5.0
                                    for q, z in zip(qs, need) if z > 0.0])
        A = 10.0 * math.ceil(A / 10.0)
        why = "flyover: no profile"
        for extra in (0.0, 20.0, 40.0):
            s_div = sF0 - c * (A + extra)
            if not 0.0 < s_div < r.L:
                return None, "flyover: off the run"
            if r.z(s_div) < 2.0:
                return None, "flyover: diverge too low"
            if any(abs(sn - s_div) < NODE_GAP_M for sn in r.s_nodes +
                   self.cut_pts.get(r.id, [])):
                why = "flyover: too near another node"
                continue
            P, _ = _at(r.pts, r.cum, s_div)
            if G.dist(Point(P), self.ctx.wet) < 30.0:
                return None, "flyover: diverge over water"
            n_st = max(int((A + extra) / 10.0), 2)
            app = []
            for i in range(n_st):
                st = s_div + (sF0 - s_div) * i / n_st
                Cs, us = _at(r.pts, r.cum, st)
                off = o * _smoothstep(abs(st - s_div) / TAPER_M)
                app.append((Cs[0] - us[1] * off * sigma, Cs[1] + us[0] * off * sigma))
            path = _dedupe([G.qpoint(p) for p in app + core])
            L_app = _cum(path[:n_st + 1])[-1]
            qs, need, under = self._fly_needs(path, obst, r.id, stem["id"], L_app, tail)
            prof = self._fly_profile(r, s_div, c, qs, need)
            if prof is None:
                continue
            why = self._fly_clear(path)
            if why:
                return None, "flyover: " + why
            if self._fly_span(qs, prof, under, path, T_n, stem["width_m"]) > FLY_SPAN_M:
                return None, "flyover: no room for its columns"
            if kind == "on":
                Lr = qs[-1]
                path = path[::-1]
                prof = [(G.q(Lr - q), z) for q, z in reversed(prof)]
                prof[0] = (0.0, prof[0][1])
            return {"pts": path, "prof": prof, "kind": kind, "T": tuple(Tf), "run": r.id,
                    "s_far": s_div, "ic": ic["id"], "sigma": sigma, "leg": stem["id"],
                    "node": r.nodes[k], "stub": False, "loop": False, "flyover": True,
                    "level": 2}, None
        return None, why

    def _fly_obstacles(self, C, beside=frozenset()) -> list:
        """What a flyover near C may pass over: the runs (with their profiles), the other
        primary roads, the ramps so far, as (key, points, arc lengths, profile, width, margin
        beside it); the roads keyed in `beside` (a stack ramp's highways) have the margin of
        a run."""
        out = []
        on_runs = set()
        for ro in sorted(self.runs, key=lambda x: x.id):
            on_runs |= {s["id"] for s, _ in ro.segs}
            w = max(s["width_m"] for s, _ in ro.segs)
            out.append((("run", ro.id), ro.pts, ro.cum, ro.prof, w, 0.5))
        for i in sorted(int(x) for x in self.prim_tree.query(Point(C).buffer(1500.0))):
            s = self.prim[i][1]
            if s["id"] in on_runs:
                continue
            cl = [tuple(p) for p in s["centerline"]]
            out.append((("seg", s["id"]), cl, _cum(cl), _tuples(s["z_profile"]), s["width_m"],
                        0.5 if ("seg", s["id"]) in beside else 2.0))
        for j, rp in enumerate(self.ramps):
            out.append((("ramp", j), rp["pts"], _cum(rp["pts"]), _tuples(rp["prof"]), RAMP_W,
                        1.0))
        return out

    def _fly_needs(self, path, obst, run_id: str, stem_id: str, app_m: float, tail_m: float,
                   own: bool = False) -> tuple:
        """Along a flyover path, every 2.5 m: the height its deck must reach there (the highest
        road or ramp it passes over, the clearance and its own deck; -inf over nothing) and
        what passes under it [(distance, width, z)]. The run itself is beside the path along
        its first `app_m` (the taper and the climb beside the deck), the stem under its last
        `tail_m` (where it lands). `own`: a stretch without its approach, which starts beside
        the run."""
        qs, P = _samples(path)
        L = qs[-1]
        need = [-math.inf] * len(qs)
        under: list = [[] for _ in qs]
        line = LineString(path)
        for key, pts, cum, prof, w, margin in obst:
            lim = w / 2.0 + RAMP_W / 2.0 + margin
            if len(pts) < 2 or G.apart(line, LineString(pts), lim):
                continue
            d, so = _near(P, pts, cum)
            for i in np.nonzero(d < lim)[0].tolist():
                q = qs[i]
                if key == ("run", run_id) and (q <= app_m or (own and q <= 1.0)):
                    continue
                if key == ("seg", stem_id) and q >= L - tail_m:
                    continue
                zo = _z_at(prof, float(so[i]))
                need[i] = max(need[i], zo + CLEAR_M + DECK_M + 0.3)
                under[i].append((float(d[i]), w, zo))
        return qs, need, under

    def _fly_profile(self, r: Run, s_div: float, c: int, qs, need) -> list | None:
        """A flyover's profile (in the off direction): on the deck along the taper, then over
        every need with a 40 m crest at the design grade, down to the landing; None where it
        cannot (a need on the taper, too steep, too high)."""
        L = qs[-1]
        hump = [(q, z) for q, z in zip(qs, need) if z > 0.0]
        z_te = r.z(s_div + c * TAPER_M)
        st = _stations(L)
        # level between crests: the lower of the highest needs before and after
        left, right = [], []
        for q, z in hump:
            left.append(max(left[-1], z) if left else z)
        for q, z in reversed(hump):
            right.append(max(right[-1], z) if right else z)
        right = right[::-1]
        hq = [q for q, _ in hump]

        def crest(x):
            h = -math.inf
            for q, z in hump:
                h = max(h, z - GRADE * max(0.0, abs(x - q) - CURVE_M / 2.0))
            i = bisect.bisect_right(hq, x)
            if 0 < i < len(hq):
                h = max(h, min(left[i - 1], right[i]))
            return h
        raw = []
        for x in st:
            if x <= TAPER_M:
                zr = r.z(s_div + c * x)
                if crest(x) > zr + 0.01:
                    return None
                raw.append(zr)
            else:
                raw.append(max(min(z_te, GRADE * max(0.0, L - x - FLAT_M)), crest(x)))
        z = smooth(raw)
        for i, x in enumerate(st):
            if x <= TAPER_M - CURVE_M / 2.0:
                z[i] = raw[i]
        z[0], z[-1] = r.z(s_div), 0.0
        prof = compress(list(zip(st, z)))
        if any(s1 > s0 and abs(z1 - z0) / (s1 - s0) > MAX_GRADE - 1e-9
               for (s0, z0), (s1, z1) in zip(prof, prof[1:])):
            return None
        if max(zz for _, zz in prof) > FLY_TOP_M:
            return None
        if any(_z_at(prof, q) < z - 0.02 for q, z in hump):
            return None
        return prof

    def _fly_clear(self, path) -> str | None:
        """Why a flyover path does not fit the ground (None when it does): water, reserves, the
        map edge."""
        ctx = self.ctx
        line = LineString(path)
        if G.dist(line, ctx.wet) < RAMP_W / 2.0 + 1.0:
            return "water"
        if not ctx.closed_all.is_empty and G.dist(line, ctx.closed_all) < RAMP_W / 2.0:
            return "reserve or open land"
        if not ctx.canvas_inner.contains(line):
            return "map edge"
        return None

    def _fly_span(self, qs, prof, under, path, T_n, stem_w: float) -> float:
        """The longest stretch of a flyover with no spot for a column (`column_free`): over a
        road or ramp lower than its deck, or a junction (a disc at each ground node near it,
        and at the stem's near terminal)."""
        cum = _cum(path)
        line = LineString(path)
        discs = [(tuple(T_n), 0.7 * stem_w + 2.0)]
        over = {x for ro in self.runs for x in ro.nodes[1:-1]}
        for nid in sorted(self.inc):
            if nid in over:
                continue
            p = self.pos[nid]
            w = max(s["width_m"] for s in self.inc[nid])
            if len(self.inc[nid]) < 2 or G.apart(line, Point(p), 0.7 * w + 2.0):
                continue
            if any(_z_at(_tuples(s["z_profile"]), 0.0 if s["start"] == nid else
                         _cum(s["centerline"])[-1]) > 0.5 for s in self.inc[nid]):
                continue
            discs.append((p, 0.7 * w + 2.0))
        size = COLUMN_DEFAULT_M
        best = run = 0.0
        prev = None
        for q, u in zip(qs, under):
            top = under_m(_z_at(prof, q))
            P, _ = _at(path, cum, q)
            blocked = top >= SUPPORT_MIN_UNDER_M and (
                any(zo < top - 1.0 and dist < w / 2.0 + size / 2.0 + 0.5 for dist, w, zo in u)
                or any(_d(P, D) < rad for D, rad in discs))
            run = run + (q - prev) if blocked and prev is not None else 0.0
            best = max(best, run)
            prev = q
        return best

    def interchange(self, r: Run, k: int, kd: str) -> None:
        n = r.nodes[k]
        on = {r.segs[k - 1][0]["id"], r.segs[k][0]["id"]}
        legs = [s for s in self.inc[n] if s["id"] not in on]
        hw_w = max(s["width_m"] for s, _ in r.segs)
        o = hw_w / 2.0 + RAMP_GAP + RAMP_W / 2.0
        C, u = _at(r.pts, r.cum, r.s_nodes[k])
        ic = {"id": f"ic{len(self.icx) + 1:02d}", "template": "overpass", "node": n,
              "run": r.id, "ramps": [], "position": G.qpoint(C)}
        sides = []
        for leg in legs:
            v = self.leg_dir(leg, n)
            sigma = 1 if u[0] * v[1] - u[1] * v[0] > 0 else -1
            sides.append((sigma, leg))
        sides.sort(key=lambda t: -t[0])
        built = []
        terminals = {}
        for sigma, leg in sides:
            t = self._terminal(r, k, leg, sigma, o)
            if t is None:
                self.failed["avenue leg too short or skewed"] = \
                    self.failed.get("avenue leg too short or skewed", 0) + 2
                continue
            T, sT, skew, along = t
            why = "skewed crossing" if skew < MIN_SKEW_SIN else \
                self._terminal_ok(leg, n, T, along)
            if why:
                self.failed[why] = self.failed.get(why, 0) + 2
                continue
            terminals[sigma] = (T, sT, leg)
        stub_side = None
        trumpet = None
        if kd == "tee" and sides[0][1]["road_class"] == "highway":
            sigma_a, leg = sides[0]
            v = self.leg_dir(leg, n)
            virt = self._stub_leg(r, k, n, leg, hw_w, C, u, v)
            if virt is not None and sigma_a in terminals:
                # M8d: one loop and a flyover, else the two loops of M7b
                trumpet = self._trumpet_flyover(r, k, n, leg, -sigma_a, hw_w, legs, ic, virt,
                                                terminals[sigma_a][0])
            if virt is not None and trumpet is None:
                trumpet = self._trumpet(r, k, n, leg, -sigma_a, hw_w, legs, ic, virt)
            if trumpet is not None:
                stub_side = None if "trim" in trumpet else -sigma_a
                for rp in trumpet["ramps"]:
                    self.ramps.append(rp)
                    self.cut_pts[r.id].append(rp["s_far"])
                built += trumpet["ramps"]
        if kd == "tee" and trumpet is None:
            sigma_a, leg = sides[0]
            v = self.leg_dir(leg, n)
            skew = abs(u[0] * v[1] - u[1] * v[0])
            if skew >= MIN_SKEW_SIN:
                d = o / skew
                Tf = G.qpoint((C[0] - v[0] * d, C[1] - v[1] * d))
                stub = LineString([G.qpoint(C), Tf])
                ok = self.ctx.dry_inner.contains(Point(Tf)) and \
                    G.dist(stub, self.ctx.wet) > 8.0 and \
                    (self.ctx.closed_all.is_empty or
                     G.dist(Point(Tf), self.ctx.closed_all) > 8.0)
                if ok:
                    sT = r.s_nodes[k] + (Tf[0] - C[0]) * u[0] + (Tf[1] - C[1]) * u[1]
                    terminals[-sigma_a] = (Tf, sT, leg)
                    stub_side = -sigma_a
        for sigma in sorted(terminals, reverse=True):
            T, sT, leg = terminals[sigma]
            side = []
            for kind in ("off", "on"):
                res, why = self._ramp(r, T, sT, sigma, kind, hw_w)
                if res is not None:
                    pts, prof, s_far = res
                    why = self._ramp_clear(pts, r, legs, T, hw_w, full=(pts, prof))
                if why is not None:
                    why = why.split(" rs")[0]
                    self.failed[why] = self.failed.get(why, 0) + 1
                    continue
                rp = {"pts": pts, "prof": prof, "kind": kind, "T": T, "run": r.id,
                      "s_far": s_far, "ic": ic["id"], "sigma": sigma, "leg": leg["id"],
                      "node": n, "stub": sigma == stub_side, "loop": False}
                self.ramps.append(rp)
                side.append(rp)
                self.cut_pts[r.id].append(s_far)
            if kd == "cross" and len(side) < 2:
                # partial cloverleaf: loops in the two quadrants of this side instead
                loops = self._loops(r, k, n, leg, sigma, hw_w, legs, ic)
                if len(loops) > len(side):
                    for rp in side:
                        self.ramps.remove(rp)
                        self.cut_pts[r.id].remove(rp["s_far"])
                    side = []
                    for rp in loops:
                        self.ramps.append(rp)
                        side.append(rp)
                        self.cut_pts[r.id].append(rp["s_far"])
            built += side
        if kd == "cross":
            # a side whose diamond terminal does not work may still take loops
            for sigma, leg in sides:
                if sigma in terminals:
                    continue
                for rp in self._loops(r, k, n, leg, sigma, hw_w, legs, ic):
                    self.ramps.append(rp)
                    built.append(rp)
                    self.cut_pts[r.id].append(rp["s_far"])
        # an avenue that ends at a terminal (a stub, or a T whose stub failed) needs both
        # ramps there: its lanes turn back nowhere else
        def unbuild(rps, why):
            for rp in rps:
                built.remove(rp)
                self.ramps.remove(rp)
                self.cut_pts[r.id].remove(rp["s_far"])
                self.failed[why] = self.failed.get(why, 0) + 1
        stub_built = [rp for rp in built if rp["stub"]]
        if len(stub_built) == 1:
            unbuild(stub_built, "stub with one ramp")
        if kd == "tee" and len([rp for rp in built if rp["stub"]]) < 2:
            near = [rp for rp in built if not rp["stub"]]
            if len(near) == 1:
                unbuild(near, "dead-end terminal with one ramp")
        if not built and kd == "tee":
            # no ramp: the run comes down to the ground here (settled again by the caller)
            ic["template"] = "none"
            self.icx.append(ic)
            return
        ic["ramps"] = [f"{rp['kind']}:{rp['sigma']}{':loop' if rp['loop'] else ''}"
                       f"{':flyover' if rp.get('flyover') else ''}" for rp in built]
        ic["template"] = ("trumpet" if trumpet is not None else
                          "parclo" if any(rp["loop"] for rp in built) else
                          "diamond" if kd == "cross" else "diamond_stub") if built else \
            "overpass"
        self.icx.append(ic)
        sides_used = sorted({rp["sigma"] for rp in built})
        for sigma in sides_used:
            if trumpet is not None and sigma == stub_side:
                # the stem runs on under the deck to the stub's end; the far ramps land on it
                self.stubs[(trumpet["leg"], n)] = trumpet["end"]
                continue
            if sigma not in terminals:
                continue      # loops only on this side (its diamond terminal failed)
            T, sT, leg = terminals[sigma]
            if sigma == stub_side:
                self.stubs[(leg["id"], n)] = T
        for T, lid in sorted({(tuple(rp["T"]), rp["leg"]) for rp in built if not rp["stub"]}):
            self.avenue_cuts.setdefault(lid, []).append(T)
        if trumpet is not None and "trim" in trumpet:
            # the stem ends at its near terminal: the loop runs on under the deck
            self.trim[(trumpet["leg"], n)] = trumpet["trim"]
        if kd == "tee" and stub_side is not None and stub_side not in sides_used:
            near = [s for s in sides_used if s != stub_side and s in terminals]
            if near:
                T, _, leg = terminals[near[0]]
                self.trim[(leg["id"], n)] = T

    def _terminal_ok(self, leg, n, T, along: float) -> str | None:
        """Why a terminal does not work (None when it does): it must stand on dry ground, at
        grade, clear of the avenue's far node."""
        if not self.ctx.dry_inner.contains(Point(T)):
            return "terminal off dry land"
        if leg["attrs"]["length_m"] - along < TERMINAL_GAP_M:
            return "avenue leg too short"
        cl = [tuple(p) for p in leg["centerline"]]
        s_on, _ = _project(cl, _cum(cl), T)
        if _z_at(_tuples(leg["z_profile"]), s_on) > 0.05:
            return "terminal on a bridge approach"
        return None

    # -- M12: stack and turbine interchanges --------------------------------------------------

    def stack_sites(self) -> list[tuple]:
        """Nodes where two generated highways cross: four highway legs and no other road, in
        two pairs that run straight on through the node (35 degrees at most) and cross at 45
        degrees or more: [(node, pair, pair)] by node id."""
        out = []
        for n in sorted(self.inc):
            legs = self.inc[n]
            if len(legs) != 4 or len({s["id"] for s in legs}) != 4:
                continue
            if self.node[n]["attrs"].get("kind") in ("exit", "edge"):
                continue
            if any(s["road_class"] != "highway" or "pinned" in s["attrs"] or
                   s["start"] == s["end"] for s in legs):
                continue
            vs = [self.leg_dir(s, n) for s in legs]
            best = None
            for i, j, k, m in ((0, 1, 2, 3), (0, 2, 1, 3), (0, 3, 1, 2)):
                d1 = vs[i][0] * vs[j][0] + vs[i][1] * vs[j][1]
                d2 = vs[k][0] * vs[m][0] + vs[k][1] * vs[m][1]
                skew = abs(vs[i][0] * vs[k][1] - vs[i][1] * vs[k][0])
                if d1 > -STRAIGHT_COS or d2 > -STRAIGHT_COS or skew < MIN_SKEW_SIN:
                    continue
                key = round(d1 + d2, 9)
                if best is None or key < best[0]:
                    best = (key, (legs[i], legs[j]), (legs[k], legs[m]))
            if best is not None:
                out.append((n, best[1], best[2]))
        return out

    def _corridor(self, n: str, pair) -> tuple[list, list] | None:
        """The highway through n along a pair of its legs and on through the nodes beyond
        (the highway leg there that runs straightest on, 35 degrees at most) to its ends, in a
        Run's form (segments with reversed flags, nodes); None where it closes on itself."""
        sides = []
        seen = {pair[0]["id"], pair[1]["id"]}
        for s in pair:
            segs, nodes = [s], [n]
            at, cur = n, s
            while True:
                far = self.other(cur, at)
                nodes.append(far)
                if far == n:
                    return None
                if self.node[far]["attrs"].get("kind") in ("exit", "edge") or len(segs) > 80:
                    break
                v = self.leg_dir(cur, far)
                nxt = None
                for o in self.inc[far]:
                    if o["id"] in seen or o["road_class"] != "highway" or o["start"] == o["end"]:
                        continue
                    w = self.leg_dir(o, far)
                    d = round(v[0] * w[0] + v[1] * w[1], 9)
                    if d <= -STRAIGHT_COS and (nxt is None or (d, o["id"]) < nxt[0]):
                        nxt = ((d, o["id"]), o)
                if nxt is None:
                    break
                cur = nxt[1]
                seen.add(cur["id"])
                segs.append(cur)
                at = far
            sides.append((segs, nodes))
        (sa, na), (sb, nb) = sides
        nodes = na[::-1] + nb[1:]
        chain = sa[::-1] + sb
        return [(sg, sg["start"] != a) for sg, a in zip(chain, nodes)], nodes

    def _window(self, n: str, pair, need: float, want: float, edge_ok: bool):
        """The corridor through n along `pair` as a Run, the index of n on it and the indices
        of its segments within `want` of n; None when it runs less than `need` on a side, or
        less than `want` on a side that does not leave the map (`edge_ok`)."""
        cor = self._corridor(n, pair)
        if cor is None:
            return None
        segs, nodes = cor
        run = Run(f"gnd-{n}", segs, nodes)
        run.build_line()
        k = nodes.index(n)
        sN = run.s_nodes[k]
        for end, room in ((nodes[0], sN), (nodes[-1], run.L - sN)):
            off = self.node[end]["attrs"].get("kind") in ("exit", "edge")
            if room < need or (room < want and not (edge_ok and off)):
                return None
        idx = [i for i in range(len(segs))
               if run.s_nodes[i + 1] > sN - want and run.s_nodes[i] < sN + want]
        return run, k, idx

    def plan_stacks(self) -> None:
        """Where two highways cross with room for a stack (or a turbine), one goes up through
        the crossing and the other stays at grade: the lifted one's segments within
        `STACK_LIFT_M` and the run down beyond join the viaducts (or it stays up to the map
        edge), the other's within `STACK_GROUND_M` leave them. The highway already up goes up,
        else the one that leaves the ground highway with fewer junctions near the crossing.
        No other highway may meet either within its window, and the lifted one may hold no
        node that would bring a run down."""
        self.stack_plan = {}
        taken: set = set()
        full = STACK_LIFT_M + ramp_run(LEVEL_Z[1])
        for n, p1, p2 in self.stack_sites():
            best = None
            for lift, gnd in ((p1, p2), (p2, p1)):
                lw = self._window(n, lift, STACK_LIFT_M, full, True)
                gw = self._window(n, gnd, STACK_GROUND_M, STACK_GROUND_M, False)
                if lw is None or gw is None:
                    continue
                ids_l = {lw[0].segs[i][0]["id"] for i in lw[2]}
                ids_g = {gw[0].segs[i][0]["id"] for i in gw[2]}
                if (ids_l | ids_g) & taken or ids_l & ids_g:
                    continue
                inner = []
                ok = True
                for w, ids in ((lw, ids_l), (gw, ids_g)):
                    run, k, idx = w
                    for i in range(idx[0] + 1, idx[-1] + 1):
                        m = run.nodes[i]
                        if m == n:
                            continue
                        if m in self.stack_plan or any(
                                o["road_class"] == "highway" and o["id"] not in ids
                                for o in self.inc[m]):
                            ok = False
                        if w is gw:
                            inner.append(m)
                if not ok:
                    continue
                up = sum(bool(s["attrs"].get("elevated")) for s in lift)
                key = (-up, len(inner), lift[0]["id"])
                if best is None or key < best[0]:
                    best = (key, lift, lw, gw, ids_l, ids_g)
            if best is None:
                continue
            _, lift, lw, gw, ids_l, ids_g = best
            old, by = {}, {}
            for w, flag in ((lw, True), (gw, False)):
                for i in w[2]:
                    s = w[0].segs[i][0]
                    old[s["id"]] = bool(s["attrs"].get("elevated"))
                    by[s["id"]] = s
                    s["attrs"]["elevated"] = flag
            # the lifted window must not hold a node that brings a run down
            run, k, idx = lw
            bad = False
            for i in range(idx[0] + 1, idx[-1] + 1):
                if run.nodes[i] == n:
                    continue
                on = {run.segs[i - 1][0]["id"], run.segs[i][0]["id"]}
                _, u = _at(run.pts, run.cum, run.s_nodes[i])
                if self.node_kind(run.nodes[i], on, u) in ("split", "branch"):
                    bad = True
            if bad:
                for sid, f in sorted(old.items()):
                    by[sid]["attrs"]["elevated"] = f
                self.stack_notes.append(f"stack at {n}: a node on the lifted highway would "
                                        "bring its viaduct down")
                continue
            taken |= ids_l | ids_g
            self.stack_plan[n] = {"lift": tuple(s["id"] for s in lift), "ground": gw[0],
                                  "gk": gw[1], "old": old, "by": by}

    def unplan(self, n: str) -> None:
        """A stack that did not fit: its highways keep the viaducts M7 chose for them."""
        plan = self.stack_plan.pop(n)
        for sid, f in sorted(plan["old"].items()):
            plan["by"][sid]["attrs"]["elevated"] = f

    def stack_ic(self, r: Run, k: int) -> None:
        """The stack (else the turbine) at node k of run r, over the highway at grade there;
        template `lost` when neither fits (the caller plans without it and builds again)."""
        n = r.nodes[k]
        plan = self.stack_plan[n]
        g = plan["ground"]
        ss = _stations(g.L)
        g.prof = compress(list(zip(ss, self.seg_profile(g, ss))))
        C, _ = _at(r.pts, r.cum, r.s_nodes[k])
        ic = {"id": f"ic{len(self.icx) + 1:02d}", "template": "lost", "node": n, "run": r.id,
              "ramps": [], "position": G.qpoint(C)}
        for variant in plan.get("order", ("stack", "turbine")):
            built, why = self._system(r, k, g, plan["gk"], variant, ic)
            if built is not None:
                ic["template"] = variant
                ic["ramps"] = [f"{rp['kind']}:{rp['turn']}:{rp['level']}" for rp in built]
                for rp in built:
                    self.avenue_cuts.setdefault(rp["leg"], []).append(tuple(rp["T"]))
                break
            self.stack_notes.append(f"{variant} at {n}: {why}")
        self.icx.append(ic)

    def _system(self, r: Run, k: int, g: Run, gk: int, variant: str, ic) -> tuple:
        """The eight directional ramps of a stack or a turbine at node k of run r (lifted, B)
        over the ground corridor g (A). The left turns first, on the lanes next to the
        highways: in a stack a diagonal across the core between two 45 degree corners, at
        tier 2 (18 m) from A onto B, then tier 3 (27 m) from B onto A over them; in a turbine
        a pinwheel sweep that crosses the two highways apart from the others, as high as the
        roads under it need. Then the right turns, one quadrant each on the lanes outside
        them: they leave each highway before its left ramp and join it after (their tapers
        never cross another ramp's lane) and pass under the left ramps where those are high
        enough, else over. All or nothing: (ramps, None) or (None, reason)."""
        n = r.nodes[k]
        sB, sA = r.s_nodes[k], g.s_nodes[gk]
        C, uB = _at(r.pts, r.cum, sB)
        _, uA = _at(g.pts, g.cum, sA)
        wB = max(s["width_m"] for s, _ in r.segs)
        wA = max(s["width_m"] for s, _ in g.segs)
        roads = {"B": (r, sB, frozenset({("run", r.id)}), wB, True, uB),
                 "A": (g, sA, frozenset(("seg", s["id"]) for s, _ in g.segs), wA, False, uA)}
        moves = []
        for xk, yk in (("A", "B"), ("B", "A")):
            for cx in (1, -1):
                for cy in (1, -1):
                    ex, ey = roads[xk][5], roads[yk][5]
                    left = cx * cy * (ex[0] * ey[1] - ex[1] * ey[0]) > 0
                    moves.append((xk, cx, yk, cy, "left" if left else "right"))
        saved = (list(self.ramps), {a: list(b) for a, b in self.cut_pts.items()},
                 {a: list(b) for a, b in self.gcuts.items()})
        self.gcuts.setdefault(g.id, [])
        cuts = {"B": self.cut_pts.setdefault(r.id, []), "A": self.gcuts[g.id]}
        built: list = []
        div_at: dict = {}
        mrg_at: dict = {}
        groups = [(variant, 2, [m for m in moves if m[4] == "left" and m[0] == "A"]),
                  (variant, 3, [m for m in moves if m[4] == "left" and m[0] == "B"]),
                  ("right", None, [m for m in moves if m[4] == "right"])]
        for shape, tier, group in groups:
            for xk, cx, yk, cy, turn in group:
                rp, why = self._sys_ramp(ic, C, roads[xk], cx, roads[yk], cy, shape, tier,
                                         div_at.get((xk, cx)), mrg_at.get((yk, cy)),
                                         cuts[xk], cuts[yk])
                if rp is None:
                    self.ramps, self.cut_pts, self.gcuts = saved
                    return None, f"{turn} ramp {xk}{'+' if cx > 0 else '-'} to " \
                                 f"{yk}{'+' if cy > 0 else '-'}: {why}"
                s_div, s_mrg = rp.pop("_ends")
                if shape != "right":
                    div_at[(xk, cx)], mrg_at[(yk, cy)] = s_div, s_mrg
                cuts[xk].append(s_div)
                cuts[yk].append(s_mrg)
                if xk == "B":
                    s_far, sigma, sg = s_div, -cx, s_mrg
                else:
                    s_far, sigma, sg = s_mrg, -cy, s_div
                j = max(i for i in range(len(g.segs)) if g.s_nodes[i] <= sg)
                rp.update({"kind": "off" if xk == "B" else "on", "run": r.id, "s_far": s_far,
                           "sigma": sigma, "node": n, "turn": turn,
                           "T": G.qpoint(_at(g.pts, g.cum, sg)[0]),
                           "leg": g.segs[min(j, len(g.segs) - 1)][0]["id"]})
                if shape == "right":
                    rp["level"] = 1
                elif variant == "stack":
                    rp["level"] = rp["tier"] = tier
                else:
                    rp["level"] = 3 if max(z for _, z in rp["prof"]) > LEVEL_Z[2] + 2.0 else 2
                self.ramps.append(rp)
                built.append(rp)
        return built, None

    def _sys_line(self, R_: Run, s: float, c: int, o: float):
        """The line o m to the right of traffic along c (+1: with the stations) on R_ at
        station s: (point, unit direction of travel)."""
        P, u = _at(R_.pts, R_.cum, s)
        e = (c * u[0], c * u[1])
        return (P[0] + o * e[1], P[1] - o * e[0]), e

    def _sys_core(self, lx: Run, s1: float, cx: int, oX: float, ly: Run, s2: float, cy: int,
                  oY: float, R: float, k: float = 0.0):
        """The turn of a directional ramp from the line oX right of X's traffic to the line oY
        right of Y's, where Q is the corner of the two lines: one fillet of radius R at Q (a
        right turn), or two (a left turn: it leaves X's line k before Q and crosses the core
        on the diagonal to Y's line, which it joins k after Q). The lines are tangent to the
        roads where the turn meets them (found in a few rounds from the crossing). Returns
        (station on X where it starts, its points, station on Y where it ends) or None."""
        pts = None
        for _ in range(4):
            A1, e1 = self._sys_line(lx, s1, cx, oX)
            A2, e2 = self._sys_line(ly, s2, cy, oY)
            den = e1[0] * e2[1] - e1[1] * e2[0]
            if abs(den) < 0.3:
                return None
            t = ((A2[0] - A1[0]) * e2[1] - (A2[1] - A1[1]) * e2[0]) / den
            Q = (A1[0] + t * e1[0], A1[1] + t * e1[1])
            if k > 0.0:
                corners = [(Q[0] - k * e1[0], Q[1] - k * e1[1]),
                           (Q[0] + k * e2[0], Q[1] + k * e2[1])]
            else:
                corners = [Q]
            last = corners[-1]
            end = (last[0] + e2[0] * (2.0 * R + 10.0), last[1] + e2[1] * (2.0 * R + 10.0))
            pts = _fillet_path(e1, corners, end, [R] * len(corners))
            if pts is None:
                return None
            n1 = _project(lx.pts, lx.cum, pts[0])[0]
            n2 = _project(ly.pts, ly.cum, pts[-2])[0]
            done = abs(n1 - s1) < 0.5 and abs(n2 - s2) < 0.5
            s1, s2 = n1, n2
            if done:
                break
        return s1, pts[:-1], s2

    def _sys_path(self, lx: Run, cx: int, oX: float, s_div: float, s1: float, core, ly: Run,
                  cy: int, oY: float, s2: float, s_mrg: float) -> tuple:
        """A directional ramp's polyline: from X's centerline at s_div out to its line (over
        `_swing` of its offset) and along it to the turn, the turn, along Y's line and in to
        its centerline at s_mrg; with the arc lengths where the turn starts and ends."""
        app, dep = [], []
        n_a = max(int(abs(s1 - s_div) / 10.0), 2)
        for i in range(n_a):
            st = s_div + (s1 - s_div) * i / n_a
            P, _ = self._sys_line(lx, st, cx, oX * _smoothstep(abs(st - s_div) / _swing(oX)))
            app.append(G.qpoint(P))
        n_d = max(int(abs(s_mrg - s2) / 10.0), 2)
        for i in range(1, n_d + 1):
            st = s2 + (s_mrg - s2) * i / n_d
            P, _ = self._sys_line(ly, st, cy, oY * _smoothstep(abs(s_mrg - st) / _swing(oY)))
            dep.append(G.qpoint(P))
        mid = _dedupe([G.qpoint(p) for p in core])
        path = _dedupe(app + mid + dep)
        cum = _cum(path)
        q1 = cum[path.index(mid[0])] if mid[0] in path else 0.0
        q2 = cum[len(path) - 1 - path[::-1].index(mid[-1])] if mid[-1] in path else cum[-1]
        return path, q1, q2

    def _sys_end(self, R_: Run, s: float, cuts, lifted: bool) -> str | None:
        """Why a ramp cannot leave or join R_ at station s (None when it can): off its ends,
        near a node or another ramp end, over the water, off the deck or on a bridge
        approach of the road at grade."""
        if not 5.0 < s < R_.L - 5.0:
            return "off the road"
        if any(abs(x - s) < NODE_GAP_M for x in R_.s_nodes + list(cuts)):
            return "too near a node"
        P, _ = _at(R_.pts, R_.cum, s)
        if G.dist(Point(P), self.ctx.wet) < 30.0:
            return "over water"
        z = R_.z(s)
        if lifted and z < LEVEL_Z[1] - 0.5:
            return "off the deck"
        if not lifted and z > 0.05:
            return "on a bridge approach"
        return None

    def _sys_needs(self, path, obst, head, q1: float, tail, q2: float) -> tuple:
        """`_fly_needs` for a directional ramp: its source road (keys `head`) is beside it up
        to arc length q1 and its target (`tail`) from q2 on; also the keys passed over at
        each sample."""
        qs, P = _samples(path)
        need = [-math.inf] * len(qs)
        under: list = [[] for _ in qs]
        hit: list = [set() for _ in qs]
        line = LineString(path)
        for key, pts, cum, prof, w, margin in obst:
            lim = w / 2.0 + RAMP_W / 2.0 + margin
            if len(pts) < 2 or G.apart(line, LineString(pts), lim):
                continue
            d, so = _near(P, pts, cum)
            for i in np.nonzero(d < lim)[0].tolist():
                q = qs[i]
                if (key in head and q <= q1) or (key in tail and q >= q2):
                    continue
                zo = _z_at(prof, float(so[i]))
                need[i] = max(need[i], zo + CLEAR_M + DECK_M + 0.3)
                under[i].append((float(d[i]), w, zo))
                hit[i].add(key)
        return qs, need, under, hit, P

    def _sys_profile(self, L: float, hump, zh, zt, cap: float) -> list | None:
        """A directional ramp's profile: on its source road along the first taper (zh, from
        the start), on its target along the last (zt, from the end), a steady grade between
        them raised over every need with a 40 m crest (level between crests, no dip below
        both ends), at most 6% and `cap`; None where it cannot."""
        hq = [q for q, _ in hump]
        left, right = [], []
        for _, z in hump:
            left.append(max(left[-1], z) if left else z)
        for _, z in reversed(hump):
            right.append(max(right[-1], z) if right else z)
        right = right[::-1]

        def crest(x):
            h = -math.inf
            for q, z in hump:
                h = max(h, z - GRADE * max(0.0, abs(x - q) - CURVE_M / 2.0))
            i = bisect.bisect_right(hq, x)
            if 0 < i < len(hq):
                h = max(h, min(left[i - 1], right[i]))
            return h
        st = _stations(L)
        za, zb = zh(TAPER_M), zt(TAPER_M)
        span = L - 2.0 * TAPER_M
        if span <= CURVE_M:
            return None
        raw = []
        for x in st:
            if x <= TAPER_M or x >= L - TAPER_M:
                z0 = zh(x) if x <= TAPER_M else zt(L - x)
                if crest(x) > z0 + 0.01:
                    return None
                raw.append(z0)
            else:
                raw.append(max(za + (zb - za) * (x - TAPER_M) / span, crest(x)))
        # no dip: a low point between higher ones comes up to the lower of them
        lo, hi = [], []
        for v in raw:
            lo.append(max(lo[-1], v) if lo else v)
        for v in reversed(raw):
            hi.append(max(hi[-1], v) if hi else v)
        raw = [min(a_, b_) for a_, b_ in zip(lo, hi[::-1])]
        z = smooth(raw)
        for i, x in enumerate(st):
            if x <= TAPER_M - CURVE_M / 2.0 or x >= L - TAPER_M + CURVE_M / 2.0:
                z[i] = raw[i]
        z[0], z[-1] = zh(0.0), zt(0.0)
        prof = compress(list(zip(st, z)))
        if any(s1 > s0 and abs(z1 - z0) / (s1 - s0) > MAX_GRADE - 1e-9
               for (s0, z0), (s1, z1) in zip(prof, prof[1:])):
            return None
        if max(zz for _, zz in prof) > cap or min(zz for _, zz in prof) < -0.005:
            return None
        if any(_z_at(prof, q) < z - 0.02 for q, z in hump):
            return None
        return prof

    def _sys_ramp(self, ic, C, X, cx: int, Y, cy: int, shape: str, pair, div_l, mrg_l,
                  cuts_x, cuts_y) -> tuple:
        """One directional ramp from X (traffic along cx) to Y (along cy). A right turn runs
        next to the highways and turns at the corner of their lanes; it leaves X at least
        `STACK_SPACE_M` nearer the crossing than the left ramp from there (`div_l`) and joins
        Y as far before the left ramp into it (`mrg_l`). A left turn swings out to a line
        beyond the right turns' quadrant and crosses the core on a diagonal between two 45
        degree turns (`STACK_SWING`; a turbine's wider, `TURBINE_SWING`, the second pair's
        diagonal further out). Returns (ramp, None) or (None, reason)."""
        lx, sxn = X[0], X[1]
        ly, syn = Y[0], Y[1]
        if shape == "right":
            out, c, R = RAMP_GAP + RAMP_W / 2.0, None, STACK_RIGHT_R
        else:
            out, c, R = STACK_SWING if shape == "stack" else TURBINE_SWING[pair - 2]
        oX, oY = X[3] / 2.0 + out, Y[3] / 2.0 + out
        core = None
        # a skewed crossing may need the diagonal's corners further out for their turns
        for f in ((1.0,) if c is None else (1.0, 1.3, 1.6)):
            core = self._sys_core(lx, sxn, cx, oX, ly, syn, cy, oY, R,
                                  0.0 if c is None else (c + oX + oY) * f)
            if core is not None and cx * (core[0] - sxn) < 0.0 and cy * (core[2] - syn) > 0.0:
                break
            core = None
        if core is None:
            return None, "the turn does not fit"
        s1, cpts, s2 = core
        lim_a = lim_d = None
        if div_l is not None:
            lim_a = cx * (s1 - div_l) - STACK_SPACE_M
            lim_d = cy * (mrg_l - s2) - STACK_SPACE_M
        return self._sys_fit(ic, C, X, cx, oX, s1, Y, cy, oY, s2, cpts, shape,
                             pair if shape == "stack" else None, lim_a, lim_d, cuts_x, cuts_y)

    def _sys_fit(self, ic, C, X, cx: int, oX: float, s1: float, Y, cy: int, oY: float,
                 s2: float, cpts, shape: str, tier, lim_a, lim_d, cuts_x, cuts_y) -> tuple:
        """A directional ramp round a given turn: its approach and departure grow until its
        profile clears every road and ramp it passes over (a stack's left ramps hold their
        tier over the core), then it must clear the ground, the other ramps of its system in
        height (a right ramp passes under a left one where that is high enough, else over it)
        and find room for its columns. Returns (ramp, None) or (None, reason)."""
        lx, _, kx, wx, upx, _ = X
        ly, _, ky, wy, upy, _ = Y
        a = _swing(oX) + 20.0
        d = _swing(oY) + 20.0
        cap = STACK_TOP_M if shape == "stack" else TURBINE_TOP_M if shape == "turbine" else \
            FLY_TOP_M
        mine = {("ramp", j): rp for j, rp in enumerate(self.ramps) if rp.get("ic") == ic["id"]}
        floor_keys = kx | ky | set(mine)
        # a right ramp may pass under its system's left ramps: they count once it meets one
        soft = set(mine) if shape == "right" else set()
        why = "no profile"
        tries = 0
        for _ in range(48):
            if (lim_a is not None and a > lim_a) or (lim_d is not None and d > lim_d):
                return None, "no room beside the left ramps"
            s_div, s_mrg = s1 - cx * a, s2 + cy * d
            bad_a = self._sys_end(lx, s_div, cuts_x, upx)
            bad_d = self._sys_end(ly, s_mrg, cuts_y, upy)
            if bad_a == "off the road" or bad_d == "off the road":
                return None, "runs off its highway"
            if bad_a or bad_d:
                why = bad_a or bad_d
                a += 10.0 if bad_a else 0.0
                d += 10.0 if bad_d else 0.0
                continue
            path, q1, q2 = self._sys_path(lx, cx, oX, s_div, s1, cpts, ly, cy, oY, s2, s_mrg)
            obst = [o for o in self._fly_obstacles(C, beside=kx | ky) if o[0] not in soft]
            qs, need, under, hit, P = self._sys_needs(path, obst, kx, q1, ky, q2)
            if tier is not None:
                for i, keys in enumerate(hit):
                    if keys & floor_keys and _d(P[i], C) <= STACK_CORE_M:
                        need[i] = max(need[i], LEVEL_Z[tier])
            L = qs[-1]
            hump = [(q, z) for q, z in zip(qs, need) if z > 0.0]
            zs, zd = lx.z(s_div + cx * TAPER_M), ly.z(s_mrg - cy * TAPER_M)
            more_a = max([0.0] + [TAPER_M + CURVE_M / 2.0 + 5.0 + max(0.0, z - zs) / GRADE - q
                                  for q, z in hump])
            more_d = max([0.0] + [TAPER_M + CURVE_M / 2.0 + 5.0 + max(0.0, z - zd) / GRADE -
                                  (L - q) for q, z in hump])
            more = 2.0 * TAPER_M + CURVE_M + 10.0 + abs(zd - zs) / GRADE - L - more_a - more_d
            if more_a > 0.0 or more_d > 0.0 or more > 0.0:
                a += 10.0 * math.ceil((more_a + max(0.0, more) / 2.0) / 10.0)
                d += 10.0 * math.ceil((more_d + max(0.0, more) / 2.0) / 10.0)
                why = "no room to climb"
                continue
            prof = self._sys_profile(L, hump, lambda x: lx.z(s_div + cx * x),
                                     lambda x: ly.z(s_mrg - cy * x), cap)
            if prof is None:
                tries += 1
                if tries > STACK_TRIES:
                    return None, "no profile"
                a += 20.0
                d += 20.0
                continue
            meet = sorted(key for key in soft if not self._apart_in_z(path, prof, mine[key]))
            if meet:
                soft -= set(meet)
                why = "meets a left ramp"
                continue
            why = self._fly_clear(path)
            if why:
                return None, why
            gk, gs, gw = (lx, s_div, wx) if not upx else (ly, s_mrg, wy)
            Tg = G.qpoint(_at(gk.pts, gk.cum, gs)[0])
            if self._fly_span(qs, prof, under, path, Tg, gw) > STACK_SPAN_M:
                return None, "no room for its columns"
            return {"pts": path, "prof": prof, "ic": ic["id"], "stub": False, "loop": False,
                    "dir": True, "shape": shape, "_ends": (s_div, s_mrg)}, None
        return None, why


def _swing(o: float) -> float:
    """Length over which a directional ramp moves out to its line o m from the centerline
    (or in from it): the ramp taper for the lanes next to the highway, longer further out."""
    return max(TAPER_M, 3.0 * o)


def _dedupe(pts):
    out = []
    for p in pts:
        if not out or p != out[-1]:
            out.append(p)
    return out


def _tail_off(pts, d: float):
    """The polyline without its last d meters (None when nothing is left)."""
    cum = _cum(pts)
    if cum[-1] <= d + 1.0:
        return None
    return _sub(pts, cum, 0.0, cum[-1] - d)


def G_points(g) -> list[tuple[float, float]]:
    if g.is_empty:
        return []
    if g.geom_type == "Point":
        return [(g.x, g.y)]
    out = []
    for p in shapely.get_parts(g):
        if p.geom_type == "Point":
            out.append((p.x, p.y))
        else:
            c = p.coords
            out.append((c[0][0], c[0][1]))
    return sorted(out)


# ---------------------------------------------------------------------------
# 5. Re-noding
# ---------------------------------------------------------------------------

RAMP_SECTION = {"total_width_m": RAMP_W, "lane_width_m": RAMP_LANE, "lanes_forward": 1,
                "lanes_backward": 0, "median_m": 0.0, "sidewalk_m": (0.0, 0.0),
                "parking": (False, False), "curb_m": 0.0}


@dataclass
class Edge:
    pts: list
    prof: list          # [(s, z)]
    row: dict
    key: str            # what it was cut from (attrs.split_of when cut or joined)
    joined: bool = False
    cuts: list = field(default_factory=list)   # grid points where it is cut
    extra: dict = field(default_factory=dict)

    @property
    def L(self) -> float:
        return _cum(self.pts)[-1]

    def oriented_to_end(self, p) -> Edge:
        """The same edge running toward p (reversed when it starts there)."""
        if tuple(self.pts[-1]) == tuple(p):
            return self
        L = self.L
        return Edge(self.pts[::-1], [(L - s, z) for s, z in reversed(self.prof)], self.row,
                    self.key, self.joined, list(self.cuts), dict(self.extra))


def _join(a: Edge, b: Edge, p) -> Edge:
    """a and b joined through their common end point p."""
    a = a.oriented_to_end(p)
    if tuple(b.pts[0]) != tuple(p):
        b = b.oriented_to_end(p)
        b = Edge(b.pts[::-1], [(b.L - s, z) for s, z in reversed(b.prof)], b.row, b.key,
                 b.joined, list(b.cuts), dict(b.extra))
    La = a.L
    row = dict(a.row)
    row["district_ids"] = sorted(set(a.row.get("district_ids", [])) |
                                 set(b.row.get("district_ids", [])))
    return Edge(a.pts + b.pts[1:], a.prof + [(La + s, z) for s, z in b.prof[1:]], row,
                f"{a.key}+{b.key}", True, a.cuts + b.cuts, {**b.extra, **a.extra})


def _insert(pts, T) -> tuple[list, int]:
    """pts with the grid point T as a vertex (on the segment nearest to it); its index."""
    T = tuple(T)
    if T in [tuple(p) for p in pts]:
        return [tuple(p) for p in pts], [tuple(p) for p in pts].index(T)
    best = None
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        f = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((T[0] - a[0]) * dx + (T[1] - a[1]) * dy)
                                             / L2))
        d = _d((a[0] + f * dx, a[1] + f * dy), T)
        if best is None or d < best[0]:
            best = (d, i)
    i = best[1]
    out = [tuple(p) for p in pts[:i + 1]] + [T] + [tuple(p) for p in pts[i + 1:]]
    return _dedupe(out), i + 1


def _cut(e: Edge) -> list[Edge]:
    """e cut at its cut points."""
    pts = [tuple(p) for p in e.pts]
    idx = []
    for T in sorted(set(e.cuts)):
        pts, _ = _insert(pts, T)
    for T in sorted(set(e.cuts)):
        k = pts.index(tuple(T))
        if 0 < k < len(pts) - 1:
            idx.append(k)
    if not idx:
        return [Edge(pts, e.prof, e.row, e.key, e.joined, [], e.extra)]
    cum = _cum(pts)
    # the old profile measured along the new vertices (an inserted point moves s by < 1 cm)
    out = []
    bounds = [0] + sorted(set(idx)) + [len(pts) - 1]
    for a, b in zip(bounds, bounds[1:]):
        piece = pts[a:b + 1]
        prof = _slice(e.prof, cum[a], cum[b])
        out.append(Edge(piece, prof, e.row, e.key, True, [], e.extra))
    return out


def rebuild(E: Elev) -> None:
    net = E.net
    pos = E.pos
    by_id = {s["id"]: s for s in net.segments}
    edges: dict[str, Edge] = {}      # by a key; avenue merges re-key
    owner: dict[str, str] = {}       # segment id -> key of the edge that holds it now
    run_ids = set()
    for r in E.runs:
        run_ids |= {s["id"] for s, _ in r.segs}
    for s in net.segments:
        if s["id"] in run_ids:
            continue
        edges[s["id"]] = Edge([tuple(p) for p in s["centerline"]], _tuples(s["z_profile"]),
                              s, s["id"])
        owner[s["id"]] = s["id"]

    def edge_of(sid: str) -> tuple[str, Edge]:
        k = owner[sid]
        return k, edges[k]

    # avenue legs join under the deck at an overpass; T stubs and trims
    for r in sorted(E.runs, key=lambda r: r.id):
        if r.branch_of is not None:
            continue
        for k in range(1, len(r.nodes) - 1):
            n = r.nodes[k]
            kd = E.kind.get((r.id, n))
            on = {r.segs[k - 1][0]["id"], r.segs[k][0]["id"]}
            legs = [s for s in E.inc[n] if s["id"] not in on]
            p = pos[n]
            if kd in ("cross", "stack"):
                (k1, e1), (k2, e2) = edge_of(legs[0]["id"]), edge_of(legs[1]["id"])
                if k1 == k2:
                    continue
                e = _join(e1, e2, p)
                e.extra["over"] = e.extra.get("over", []) + [p]
                for key in (k1, k2):
                    del edges[key]
                for sid, kk in list(owner.items()):
                    if kk in (k1, k2):
                        owner[sid] = e.key
                edges[e.key] = e
            elif kd == "tee":
                kk, e = edge_of(legs[0]["id"])
                e = e.oriented_to_end(p)
                stub = E.stubs.get((legs[0]["id"], n))
                trim = E.trim.get((legs[0]["id"], n))
                if stub is None and trim is None and E.avenue_cuts.get(legs[0]["id"]):
                    # ramps land on this leg and nothing continues under the deck: the tail
                    # past the nearest terminal would end right under the viaduct (where M2
                    # would join it to the deck)
                    near = min((tuple(T) for T in E.avenue_cuts[legs[0]["id"]]),
                               key=lambda T: (round(_d(p, T), 2), T))
                    trim = near if _d(p, near) < 300.0 else None
                if stub is not None:
                    L = e.L
                    e = Edge(e.pts + [stub], e.prof + [(L + _d(p, stub), 0.0)], e.row, e.key,
                             True, e.cuts + [], {**e.extra, "over": e.extra.get("over", []) +
                                                 [p]})
                elif trim is not None:
                    pts, i = _insert(e.pts, trim)
                    cum = _cum(pts)
                    e = Edge(pts[:i + 1], _slice(e.prof, 0.0, cum[i]), e.row, e.key, True,
                             [c for c in e.cuts if tuple(c) != tuple(trim)], e.extra)
                edges[kk] = e
    for sid, Ts in sorted(E.avenue_cuts.items()):
        kk, e = edge_of(sid)
        e.cuts += [tuple(T) for T in Ts]
    # runs, cut where ramps leave or join and where branches meet them
    out: list[Edge] = []
    for r in sorted(E.runs, key=lambda r: r.id):
        cuts = {0.0, r.L}
        for k in range(1, len(r.nodes) - 1):
            if E.kind.get((r.id, r.nodes[k])) not in ("cross", "tee", "plain", "stack"):
                cuts.add(r.s_nodes[k])
        cuts |= set(E.cut_pts.get(r.id, []))
        cuts = sorted(cuts)
        for a, b in zip(cuts, cuts[1:]):
            if b - a < 0.05:
                continue
            mid = (a + b) / 2.0
            j = max(i for i in range(len(r.segs)) if r.s_nodes[i] <= mid)
            src = r.segs[min(j, len(r.segs) - 1)][0]
            row = dict(src)
            row["district_ids"] = sorted({d for s, _ in r.segs for d in s["district_ids"]})
            attrs = dict(src["attrs"])
            attrs.update({"elevated": True, "split_of": r.id, "level": r.level})
            over = [G.qpoint(_at(r.pts, r.cum, r.s_nodes[k])[0])
                    for k in range(1, len(r.nodes) - 1)
                    if E.kind.get((r.id, r.nodes[k])) in ("cross", "tee", "stack") and
                    a < r.s_nodes[k] < b]
            if over:
                attrs["overpass_at"] = over
            if r.branch_of is not None:
                attrs["direct"] = r.branch_of
            row["attrs"] = attrs
            out.append(Edge(_sub(r.pts, r.cum, a, b), _slice(r.prof, a, b), row, r.id, True,
                            extra={"level": r.level, "elevated": True}))
    for kk in sorted(edges):
        out += _cut(edges[kk])
    for rp in E.ramps:
        src = next(s for s, _ in next(r for r in E.runs if r.id == rp["run"]).segs)
        ic = next(i for i in E.icx if i["id"] == rp["ic"])
        row = {"type": "road.highway.ramp", "road_class": "highway", "name": None,
               "lanes": 1, "width_m": RAMP_W, "cross_section": dict(RAMP_SECTION),
               "one_way": True, "district_ids": list(src["district_ids"]),
               "attrs": {"role": "ramp", "ramp": rp["kind"], "interchange": rp["ic"],
                         "template": ic["template"], "stub": rp["stub"]}}
        if rp.get("flyover"):
            row["attrs"]["flyover"] = True
        if rp.get("dir"):
            # M12: a directional ramp of a stack or turbine
            row["attrs"]["turn"] = rp["turn"]
            if rp.get("tier"):
                row["attrs"]["tier"] = rp["tier"]
            row["attrs"]["crossing"] = list(ic["position"])
        out.append(Edge(rp["pts"], rp["prof"], row, rp["ic"], False,
                        extra={"level": rp.get("level", 1), "ramp": True}))
    # nodes by coordinate
    old = {(G.q(n["position"][0]), G.q(n["position"][1])): n for n in net.nodes}
    deg: dict = {}
    zs: dict = {}
    lvl: dict = {}
    for e in out:
        for p, z in ((tuple(e.pts[0]), e.prof[0][1]), (tuple(e.pts[-1]), e.prof[-1][1])):
            deg[p] = deg.get(p, 0) + 1
            zs[p] = max(zs.get(p, 0.0), G.q(z))
            if e.extra.get("elevated") and z > 0.5:
                lvl[p] = max(lvl.get(p, 0), e.extra["level"])
    order = sorted(deg)
    nid = {c: f"rn{i + 1:04d}" for i, c in enumerate(order)}
    nodes = []
    for c in order:
        o = old.get(c)
        kind = o["attrs"]["kind"] if o and o["attrs"].get("kind") in ("exit", "edge") else (
            "end" if deg[c] == 1 else "junction")
        rec = {"id": nid[c], "position": (c[0], c[1], zs[c]), "level": lvl.get(c, 0),
               "attrs": {"kind": kind, "degree": deg[c]}}
        if o and o["attrs"].get("exit"):
            rec["attrs"]["exit"] = o["attrs"]["exit"]
        nodes.append(rec)
    out.sort(key=lambda e: (e.row["road_class"] != "highway", tuple(e.pts[0]),
                            tuple(e.pts[-1]), round(_cum(e.pts)[-1], 2)))
    segs = []
    for i, e in enumerate(out):
        row = {k: v for k, v in e.row.items()}
        attrs = dict(row.get("attrs", {}))
        attrs.pop("grade_separated_with", None)
        attrs["length_m"] = G.q(_cum(e.pts)[-1])
        attrs["z_profile"] = "m7"
        if e.joined and "split_of" not in attrs:
            attrs["split_of"] = f"m1b:{e.key}"   # pre-M7 ids (not the new ones)
        if e.extra.get("over"):
            pts_ = [tuple(p) for p in e.pts]
            attrs["overpass_at"] = [list(p) for p in e.extra["over"] if tuple(p) in pts_]
        row.update({"id": f"rs{i + 1:04d}", "start": nid[tuple(e.pts[0])],
                    "end": nid[tuple(e.pts[-1])], "centerline": [tuple(p) for p in e.pts],
                    "z_profile": _rows(compress(e.prof)), "bridge_ids": [], "bridge": False,
                    "clearance_m": None,
                    "level": e.extra.get("level", 0) if (e.extra.get("elevated") or
                                                         e.extra.get("ramp")) else 0,
                    "attrs": attrs})
        segs.append(row)
    # bridges onto the pieces that carry them
    lines = [LineString(s["centerline"]) for s in segs]
    tree = shapely.STRtree(lines)
    for b in net.bridges:
        if b.get("bridge_class") == "pedestrian" and not b.get("segment_ids"):
            continue
        bl = [(x, y) for x, y, _ in b["line"]]
        mid = LineString(bl).interpolate(0.5, normalized=True)
        cands = sorted(int(i) for i in tree.query(mid, predicate="dwithin", distance=0.5))
        cands = [i for i in cands if segs[i]["road_class"] == b.get("road_class",
                                                                    segs[i]["road_class"])
                 and segs[i]["attrs"].get("role") != "ramp"] or cands
        if not cands:
            E.notes.append(f"bridge {b['id']}: no road under it after M7")
            b["segment_ids"] = []
            continue
        i = min(cands, key=lambda i: (round(lines[i].distance(mid), 6), segs[i]["id"]))
        sg = segs[i]
        cl = sg["centerline"]
        cum = _cum(cl)
        s0 = _project(cl, cum, bl[0])[0]
        s1 = _project(cl, cum, bl[-1])[0]
        b["s0"], b["s1"] = G.q(min(s0, s1)), G.q(max(s0, s1))
        b["segment_ids"] = [sg["id"]]
        prof = _tuples(sg["z_profile"])
        b["line"] = [(x, y, G.q(max(z0, _z_at(prof, _project(cl, cum, (x, y))[0]))))
                     for x, y, z0 in b["line"]]
        sg["bridge_ids"].append(b["id"])
        sg["bridge"] = True
        sg["clearance_m"] = max(sg["clearance_m"] or 0.0, b["clearance_m"])
    net.nodes = nodes
    net.segments = segs


APPROACH_GRADE = 0.055          # bridge approaches (no vertical curves)
BRIDGE_DECK_M = 1.5             # a bridge's structure depth (M1b)


def solve_grades(net, apart: dict | None = None, extra: dict | None = None) -> None:
    """The approach envelope (`_envelope`), then roads that cross without a node (bridges
    over the same water) 7 m apart: the higher one rises over the other, again until they
    are (viaduct runs settle their own crossings in `Elev.profiles`)."""
    extra = {k: list(v) for k, v in (extra or {}).items()}
    for _ in range(4):
        _envelope(net, apart, extra)
        add = _crossing_needs(net)
        if not add:
            return
        for sid, need in add:
            extra.setdefault(sid, []).append(need)


def _crossing_needs(net) -> list:
    """(segment id, (s, s, z)) for the upper road of each crossing without a node that is
    too close to the one under it (neither on an elevated run)."""
    segs = [s for s in net.segments if not s["attrs"].get("elevated")]
    lines = [LineString(s["centerline"]) for s in segs]
    if not lines:
        return []
    tree = shapely.STRtree(lines)
    out = []
    for i, a in enumerate(lines):
        for j in sorted(int(x) for x in tree.query(a, predicate="crosses")):
            if j <= i:
                continue
            sa, sb = segs[i], segs[j]
            if {sa["start"], sa["end"]} & {sb["start"], sb["end"]}:
                continue
            for p in G_points(a.intersection(lines[j])):
                pt = Point(p)
                ta, tb = a.project(pt), lines[j].project(pt)
                za = _z_at(_tuples(sa["z_profile"]), ta)
                zb = _z_at(_tuples(sb["z_profile"]), tb)
                if za < 0.5 and zb < 0.5:
                    continue      # at grade (a junction missing: not ours to fix)
                rank_a = (round(za, 2), sa["road_class"] == "highway", sa["id"])
                rank_b = (round(zb, 2), sb["road_class"] == "highway", sb["id"])
                (up, t_up, z_up), z_lo = ((sa, ta, za), zb) if rank_a > rank_b else \
                    ((sb, tb, zb), za)
                want = z_lo + CLEAR_M + BRIDGE_DECK_M
                if z_up < want - 0.05:
                    out.append((up["id"], (G.q(t_up), G.q(t_up), G.q(want))))
    return out


def _envelope(net, apart: dict | None = None, extra: dict | None = None) -> None:
    """Bridge approaches across the network: every bridge deck falls off at the approach
    grade along the roads in every direction, through the nodes (a max-plus envelope over the
    graph, so no road anywhere is steeper than the grade); each segment's profile is that
    envelope (M1b clipped each approach at its own segment's ends). `apart[node]` holds the
    run legs of a node that becomes an overpass: they and the other legs are not joined
    there."""
    import heapq

    apart = apart or {}
    extra = extra or {}

    def end(s, n):
        return (n, 1 if s["id"] in apart.get(n, ()) else 0)

    segs = net.segments
    Ls = {s["id"]: _cum(s["centerline"])[-1] for s in segs}
    spans: dict = {}
    for b in net.bridges:
        for sid in b.get("segment_ids", []):
            if sid in Ls:
                spans.setdefault(sid, []).append((b["s0"], b["s1"], b["line"][0][2]))
        if b["attrs"].get("ramp_length_m") is not None:
            b["attrs"]["ramp_length_m"] = G.q((b["clearance_m"] + 1.5) / APPROACH_GRADE)
    for sid, ext in sorted(extra.items()):
        if sid in Ls:
            spans.setdefault(sid, []).extend(ext)
    if not spans:
        return
    adj: dict = {}
    for s in segs:
        a, b = end(s, s["start"]), end(s, s["end"])
        adj.setdefault(a, []).append((b, Ls[s["id"]], s["id"]))
        adj.setdefault(b, []).append((a, Ls[s["id"]], s["id"]))
    val: dict = {}
    heap: list = []
    for s in segs:
        for s0, s1, z in spans.get(s["id"], []):
            for n, d in ((end(s, s["start"]), s0), (end(s, s["end"]), Ls[s["id"]] - s1)):
                v = z - APPROACH_GRADE * d
                if v > val.get(n, 0.0):
                    val[n] = v
                    heapq.heappush(heap, (-v, n))
    while heap:
        v, n = heapq.heappop(heap)
        v = -v
        if v < val.get(n, 0.0):
            continue
        for m, L, _ in sorted(adj.get(n, [])):
            w = v - APPROACH_GRADE * L
            if w > val.get(m, 0.0) + 1e-9:
                val[m] = w
                heapq.heappush(heap, (-w, m))
    for s in segs:
        L = Ls[s["id"]]
        z0, z1 = val.get(end(s, s["start"]), 0.0), val.get(end(s, s["end"]), 0.0)
        sp = spans.get(s["id"], [])
        if not sp and z0 <= 0.0 and z1 <= 0.0:
            continue
        ss = set(_stations(L))
        for s0, s1, _ in sp:
            ss |= {min(max(s0, 0.0), L), min(max(s1, 0.0), L)}
        prof = []
        for x in sorted(ss):
            z = max(0.0, z0 - APPROACH_GRADE * x, z1 - APPROACH_GRADE * (L - x))
            for s0, s1, zb in sp:
                d = s0 - x if x < s0 else (x - s1 if x > s1 else 0.0)
                z = max(z, zb - APPROACH_GRADE * d)
            prof.append((x, z))
        s["z_profile"] = _rows(compress(prof))


def _node_heights(net) -> None:
    """Without a viaduct (no rebuild): every node at the height its roads meet it (a bridge
    approach can reach a node)."""
    zs: dict = {}
    for s in net.segments:
        prof = _tuples(s["z_profile"])
        if not prof:
            continue
        for nid, z in ((s["start"], prof[0][1]), (s["end"], prof[-1][1])):
            zs[nid] = max(zs.get(nid, 0.0), G.q(z))
    for n in net.nodes:
        x, y = n["position"][0], n["position"][1]
        n["position"] = (x, y, zs.get(n["id"], 0.0))


def _weights(spec, ctx, net) -> dict:
    """Per highway segment: the tallest archetype height among the districts it serves
    (dense districts get the viaducts)."""
    from . import presets

    tall = {ctx.did[d.name]: presets.ARCHETYPES[d.archetype].height_m[1]
            for d in spec.districts if d.name in ctx.polygons}
    out = {}
    for s in net.segments:
        if s["road_class"] != "highway":
            continue
        w = max((tall.get(d, 0.0) for d in s["district_ids"]), default=0.0)
        out[s["id"]] = w
    return out


def elevate(spec, ctx, net) -> dict:
    """The M7 stage on M1b's network (in place). Returns stats and notes for the report."""
    if spec.highways.elevated_share <= 0 or not any(
            s["road_class"] == "highway" for s in net.segments):
        solve_grades(net)
        _node_heights(net)
        return {"runs": 0, "notes": []}
    E = Elev(ctx, net)
    E.select(spec, _weights(spec, ctx, net))
    # M12: stacks where two highways cross (one lifted through the crossing); a stack that
    # does not fit is dropped and the stage runs again from the same roads without it
    E.plan_stacks()
    order = ("turbine", "stack") if spec.highways.crossings == "turbine" else \
        ("stack", "turbine")
    for plan in E.stack_plan.values():
        plan["order"] = order
    z0 = {s["id"]: [dict(z) for z in s["z_profile"]] for s in net.segments} \
        if E.stack_plan else None
    while True:
        E.make_runs()
        for _ in range(4):
            E.reset()
            E.settle()
            apart = {}
            for r in E.runs:
                for k in range(1, len(r.nodes) - 1):
                    if E.kind.get((r.id, r.nodes[k])) in ("cross", "tee", "stack"):
                        apart[r.nodes[k]] = {r.segs[k - 1][0]["id"], r.segs[k][0]["id"]}
            extra: dict = {}
            for _k in range(3):
                solve_grades(net, apart, extra)
                E.profiles()
                if not E.lift:
                    break
                for sid, need in E.lift:
                    extra.setdefault(sid, []).append(need)
            E.interchanges()
            bad = sorted(ic["node"] for ic in E.icx if ic["template"] == "none")
            if not bad:
                break
            E.forced |= set(bad)
        lost = sorted(ic["node"] for ic in E.icx if ic["template"] == "lost")
        if not lost:
            break
        for n in lost:
            E.unplan(n)
        for s in net.segments:
            s["z_profile"] = [dict(z) for z in z0[s["id"]]]
        E.runs, E.run_n, E.forced, E.notes = [], 0, set(), []
    E.icx = [ic for ic in E.icx if ic["template"] != "none"]
    if E.stack_notes:
        E.notes.append("stacks: " + "; ".join(dict.fromkeys(E.stack_notes)))
    if not E.runs:
        _node_heights(net)
        return {"runs": 0, "notes": E.notes}
    rebuild(E)
    if E.failed:
        E.notes.append("ramps not built: " + ", ".join(
            f"{v} {k}" for k, v in sorted(E.failed.items(), key=lambda kv: (-kv[1], kv[0]))))
    tmpl: dict = {}
    for ic in E.icx:
        tmpl[ic["template"]] = tmpl.get(ic["template"], 0) + 1
    return {"runs": sum(1 for r in E.runs if r.branch_of is None),
            "direct": sum(1 for r in E.runs if r.branch_of is not None),
            "ramps": len(E.ramps), "interchanges": dict(sorted(tmpl.items())),
            "notes": E.notes}


# ---------------------------------------------------------------------------
# Supports (after M3 and transit)
# ---------------------------------------------------------------------------

SUPPORT_STEP_M = 32.0           # scope: columns every 25 to 40 m
SUPPORT_MAX_GAP_M = 60.0        # a span over a road under the deck
SUPPORT_MIN_UNDER_M = 1.0       # a deck lower than this rests on its embankment
COLUMN_M = {"highway": 2.5, "avenue": 2.2}
COLUMN_DEFAULT_M = 1.8


def _water_polys(m) -> list:
    out = [G.from_model_poly(w.polygon) for w in m.waterways]
    out += [G.from_model_poly(r.polygon) for r in m.rivers]
    out += [G.from_model_poly(c.polygon) for c in m.channels]
    return out


def support_context(m) -> dict:
    """What a road column must stay out of: water, buildings, transit structures, and the
    roads and junctions under each deck (with their heights)."""
    roads = [(LineString(s.centerline), s) for s in m.road_segments]
    wet = _water_polys(m)
    blds = [G.from_model_poly(ms.footprint) for b in m.buildings for ms in b.masses
            if ms.z0_m <= 0.5 and ms.z1_m > ms.z0_m and ms.role != "void"]
    tst = [(G.from_model_poly(s.footprint), s.z0_m) for s in m.structures
           if s.footprint is not None and ((s.attrs or {}).get("line_id") or
                                           (s.attrs or {}).get("station"))]
    tstruct = [p for p, _ in tst]
    tracks = [(LineString([(p[0], p[1]) for p in t.path]), [p[2] for p in t.path], t.mode)
              for t in m.transit_lines if t.mode != "metro" and len(t.path) >= 2]
    junc = [(G.from_model_poly(j.polygon), j.node_id) for j in m.junctions]
    nz = {n.id: n.position[2] for n in m.road_nodes}
    return {
        "roads": roads, "rtree": shapely.STRtree([r[0] for r in roads]) if roads else None,
        "wet": wet, "wtree": shapely.STRtree(wet) if wet else None,
        "blds": blds, "btree": shapely.STRtree(blds) if blds else None,
        "ts": tstruct, "ttree": shapely.STRtree(tstruct) if tstruct else None,
        "ts_z0": [z for _, z in tst],
        "tracks": tracks,
        "junc": junc, "jtree": shapely.STRtree([j[0] for j in junc]) if junc else None,
        "nz": nz}


def raised_segments(m) -> list:
    """Road decks to carry on columns: every segment with a stretch whose underside is at
    least 2 m up, footbridges aside (their piers are their own)."""
    out = []
    for s in m.road_segments:
        if s.road_class in ("footbridge",):
            continue
        if any(under_m(z.z) >= SUPPORT_MIN_UNDER_M for z in s.z_profile):
            out.append(s)
    return out


def column_free(cx: dict, s, p, size: float, top: float) -> bool:
    """A column of this size at p under segment s (deck underside at top) stands clear of
    the water, buildings, transit structures, and every road and junction passing under."""
    pt = Point(p)
    sq = pt.buffer(size / 2.0, cap_style="square")
    for key, tk in (("wet", "wtree"), ("blds", "btree")):
        tree = cx[tk]
        if tree is not None and len(tree.query(sq, predicate="intersects")):
            return False
    if cx["ttree"] is not None:
        # a transit structure that reaches down below this deck (a platform above it is no
        # obstacle)
        for i in cx["ttree"].query(sq, predicate="intersects").tolist():
            if cx["ts_z0"][i] < top + 1.0:
                return False
    if cx["rtree"] is not None:
        for i in sorted(int(x) for x in cx["rtree"].query(pt, predicate="dwithin",
                                                         distance=40.0)):
            ln, o = cx["roads"][i]
            if o.id == s.id:
                continue
            d = G.dist(ln, pt)
            if d >= o.width_m / 2.0 + size / 2.0 + 0.5:
                continue
            z_o = _z_at([(z.s, z.z) for z in o.z_profile], ln.project(pt))
            if z_o < top - 1.0:
                return False      # a road under the deck: the column would stand in it
    if cx["jtree"] is not None:
        for i in sorted(int(x) for x in cx["jtree"].query(sq, predicate="intersects")):
            poly, nid = cx["junc"][i]
            if nid not in (s.start, s.end) and cx["nz"].get(nid, 0.0) < top - 1.0:
                return False
    for line, zs, mode in cx["tracks"]:
        if G.apart(line, pt, 12.0):
            continue
        if G.dist(line, pt) < 6.0:
            k = min(range(len(zs)), key=lambda i: _d(line.coords[i], p))
            if zs[k] < top + 2.0:
                return False      # a track passes between the column's foot and the deck
    return True


def road_supports(m) -> list[dict]:
    """Columns under every raised road deck over land: every 32 m along the centerline (in
    the median of a road that has one), moved up to 12 m along where the spot is taken;
    none in the water (bridge piers there), a building, a transit structure, or a road or
    junction passing under the deck."""
    cx = support_context(m)
    out = []
    for s in raised_segments(m):
        pts = [tuple(p) for p in s.centerline]
        cum = _cum(pts)
        L = cum[-1]
        prof = [(z.s, z.z) for z in s.z_profile]
        size = COLUMN_M.get(s.road_class, COLUMN_DEFAULT_M)
        if s.attrs.get("role") == "ramp":
            size = COLUMN_DEFAULT_M
        n = 0
        st = SUPPORT_STEP_M / 2.0
        while st < L - 5.0:
            here = st
            st += SUPPORT_STEP_M
            lat = s.width_m / 4.0
            spots = [(a, b) for a in (0.0, 6.0, -6.0, 12.0, -12.0)
                     for b in (0.0, lat, -lat)]
            for off, side in spots:
                sx = here + off
                if not (2.0 < sx < L - 2.0):
                    continue
                top = under_m(_z_at(prof, sx))
                if top < SUPPORT_MIN_UNDER_M:
                    continue
                P, u = _at(pts, cum, sx)
                P = G.qpoint((P[0] - u[1] * side, P[1] + u[0] * side))
                if not column_free(cx, s, P, size, top):
                    continue
                n += 1
                ca, sa = u[0], u[1]
                h = size / 2.0
                ring = [G.qpoint((P[0] + ca * a - sa * b, P[1] + sa * a + ca * b))
                        for a, b in ((-h, -h), (h, -h), (h, h), (-h, h))]
                out.append(_column(s, n, P, u, size, top, sx))
                break
    _fill_gaps(cx, out, m)
    return out


def _column(s, n: int, P, u, size: float, top: float, sx: float) -> dict:
    ca, sa = u[0], u[1]
    h = size / 2.0
    ring = [G.qpoint((P[0] + ca * a - sa * b, P[1] + sa * a + ca * b))
            for a, b in ((-h, -h), (h, -h), (h, h), (-h, h))]
    return {"id": f"{s.id}.col{n:03d}", "type": "structure", "kind": "column",
            "z0_m": 0.0, "z1_m": G.q(top), "footprint": G.to_model_poly(shapely.Polygon(ring)),
            "supports": [s.id],
            "attrs": {"road_id": s.id, "road_class": s.road_class, "s_m": G.q(sx)}}


def _fill_gaps(cx: dict, out: list, m) -> None:
    """Where the regular spots are all taken (a crossing crowded by the road under it and the
    ramps beside it), a stretch of deck left more than half the largest span from any column
    gets one at the nearest free spot within 30 m along it (across the whole deck width),
    past its end nodes onto the raised segments there when the segment is short."""
    half = SUPPORT_MAX_GAP_M / 2.0
    wet = cx["wtree"]
    cols = [G.from_model_poly(c["footprint"]).centroid for c in out]
    ctree = shapely.STRtree(cols) if cols else None
    added: list = []
    raised = raised_segments(m)
    geo = {}
    at_node: dict = {}
    for s in raised:
        pts = [tuple(p) for p in s.centerline]
        geo[s.id] = (pts, _cum(pts), [(z.s, z.z) for z in s.z_profile])
        at_node.setdefault(s.start, []).append(s)
        at_node.setdefault(s.end, []).append(s)
    count: dict = {}
    for c in out:
        count[c["attrs"]["road_id"]] = count.get(c["attrs"]["road_id"], 0) + 1

    def spots(s, here: float, k: int):
        """Positions k m from `here` along s, or past its ends on the raised segments
        there, as (segment, s along it)."""
        L = geo[s.id][1][-1]
        for sx in sorted({here + k, here - k}):
            if 2.0 < sx < L - 2.0:
                yield s, sx
        for nid, rest in ((s.start, k - here), (s.end, k - (L - here))):
            if rest <= 2.0:
                continue
            for o in sorted(at_node.get(nid, []), key=lambda x: x.id):
                if o.id == s.id:
                    continue
                Lo = geo[o.id][1][-1]
                sx = rest if o.start == nid else Lo - rest
                if 2.0 < sx < Lo - 2.0:
                    yield o, sx

    for s in raised:
        pts, cum, prof = geo[s.id]
        L = cum[-1]
        d = 2.5
        while d < L:
            here, d = d, d + 5.0
            if under_m(_z_at(prof, here)) < SUPPORT_MIN_UNDER_M:
                continue
            P0, _ = _at(pts, cum, here)
            p0 = Point(P0)
            if wet is not None and len(wet.query(p0.buffer(3.0), predicate="intersects")):
                continue
            if (ctree is not None and len(ctree.query(p0, predicate="dwithin",
                                                      distance=half))) or \
                    any(G.dist(q, p0) <= half for q in added):
                continue
            done = False
            for k in range(0, 31, 2):
                for o, sx in spots(s, here, k):
                    opts, ocum, oprof = geo[o.id]
                    top = under_m(_z_at(oprof, sx))
                    if top < SUPPORT_MIN_UNDER_M:
                        continue
                    size = COLUMN_DEFAULT_M if o.attrs.get("role") == "ramp" else \
                        COLUMN_M.get(o.road_class, COLUMN_DEFAULT_M)
                    lat = o.width_m / 2.0 - size / 2.0 - 0.5
                    P, u = _at(opts, ocum, sx)
                    for side in (0.0, lat / 2.0, -lat / 2.0, lat, -lat):
                        Q = G.qpoint((P[0] - u[1] * side, P[1] + u[0] * side))
                        if column_free(cx, o, Q, size, top):
                            count[o.id] = count.get(o.id, 0) + 1
                            out.append(_column(o, count[o.id], Q, u, size, top, sx))
                            added.append(Point(Q))
                            done = True
                            break
                    if done:
                        break
                if done:
                    break
