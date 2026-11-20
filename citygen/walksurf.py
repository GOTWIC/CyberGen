"""Walkways on the surface stage 2 draws (people_surfaces).

The model keeps a walkway's height at its vertices only (a raised road's sidewalks at the
ground, M7; AG7 puts them on the deck at the same vertices), so a lane drawn from its line runs
straight between them: over a road's hump or along a ramp's vertical curve people walked inside
the embankment, a meter or two under the sidewalk. `drape` gives each walkway the height of the
surface it is drawn on at every point where that surface bends:

- **The surface** is M22's pavement map as AG17 draws it: a face's height over the ground at
  a point by mean value coordinates of its boundary's heights (`pavement.mvc`; within
  `ON_FACE_M` of its boundary, along the edge), lifted as AG17 lifts it (`LIFT_M`: a curb
  band, sidewalk, corner pad or median 0.2 m, the rest 0.05 m; a crosswalk crosses a median at
  the road's 0.05 m, as AG17 cuts it through). A point within `ON_FACE_M` of a face is on it:
  the model's lines are on the 1 cm grid, the map's on the millimeter one, so a walkway laid
  along a face's edge (a crossing of a road's end at the map's edge) runs a few millimeters
  in and out of it, and an exact test would take the face at some samples and not at others,
  differently for `drape` and `check`, which sample apart.
- **Which face**, where faces overlap in plan (a sidewalk under a viaduct, a road crossing
  over a street): a walkway that follows a road (`attrs.segment`) takes the face nearest its
  road's own surface there (the road's z profile at its station plus the sidewalk's lift),
  any other the face nearest its own height, either within `REACH_M` (a path under a viaduct
  keeps its own height; a sidewalk's end in a steep or folded corner pad its road's, as AG7
  puts it there). A deck's walkways (level 1) take only a deck's faces, the rest none of
  them. Where no face holds a point, a road's walkway stands on its road's surface plus the
  lift, any other at its own height.
- **Rounds:** the walkways along a road first; then those with an end on one, their own
  height moved by the difference at their ends (the model keeps a raised road's crossings,
  crosswalks and the door paths to its sidewalks at the ground: they climb onto it with
  the sidewalks they join); ends that meet take one height (`drape`).
- **The line**: sampled every `STEP_M` between its vertices, a sample kept only where the
  line through the kept points around it misses its height by more than `TOL_M` (Douglas and
  Peucker in the walkway's profile, every vertex kept), so a flat walkway keeps its vertices
  and a sidewalk over a hump gets its curve.

Heights over the ground, as the model's; `exports.graphs` adds the ground on a terrain city.
`check` measures exported lines against the surface (lifegen's `walk_heights`).
"""

from __future__ import annotations

import math

import numpy as np

STEP_M = 1.0            # samples along a walkway, m
TOL_M = 0.02            # a sample kept where the profile through its neighbours misses it by more
REACH_M = 1.5           # a walkway not on a road takes a face this near its own height
CURB_LIFT_M = 0.2       # AG17: a curb band's, sidewalk's, corner pad's or median's top (50 + 150 mm)
ROAD_LIFT_M = 0.05      # AG17: a carriageway's, junction's, bulb's, bend's or walk face's (50 mm)
LIFT_M = {"curb": CURB_LIFT_M, "sidewalk": CURB_LIFT_M, "corner": CURB_LIFT_M,
          "median": CURB_LIFT_M}
ON_FACE_M = 0.01        # a point this near a face is on it, at its nearest edge's height
ROUNDS = 3              # rounds of walkways anchored on draped ones at their ends (`drape`)
CHECK_STEP_M = 0.5      # `check`: the lines sampled this often
CHECK_TOL_M = 0.05      # ... within this of the surface
CHECK_STEP_DZ_M = 0.1   # ... but at a step in the surface this high between two samples
CHECK_FAIL_M = 0.25     # ... and a line this far off it fails (a person in the ground)
VERSION = 1             # graphs.json's `walk_surface`: its walkways draped
# walkway kinds drawn on the ground's or a deck's surface (not stairs, elevators, skybridges,
# station platforms or underpasses, which have their own structures)
DRAPED = ("sidewalk", "crosswalk", "crossing", "pedestrian_street", "promenade", "footbridge",
          "alley", "path")
CROSSING = ("crosswalk", "crossing")
ROAD_KINDS = ("sidewalk", "pedestrian_street", "promenade", "footbridge", "alley")


def _g(o, k, d=None):
    if isinstance(o, dict):
        return o.get(k, d)
    return getattr(o, k, d)


def _attrs(o) -> dict:
    return _g(o, "attrs") or {}


def _cum(pts) -> list[float]:
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return out


class _Road:
    """A road's centerline and z profile: the surface at a point is the profile at its
    station (the point projected onto the centerline)."""

    def __init__(self, seg):
        self.line = [(float(p[0]), float(p[1])) for p in _g(seg, "centerline")]
        self.cum = _cum(self.line)
        self.prof = [(float(_g(z, "s")), float(_g(z, "z"))) for z in (_g(seg, "z_profile") or [])]

    def z(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        if not self.prof or len(self.line) < 2:
            return np.zeros(len(xs))
        best_d = np.full(len(xs), np.inf)
        best_s = np.zeros(len(xs))
        for (ax, ay), (bx, by), s0 in zip(self.line, self.line[1:], self.cum):
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            if L2 <= 0.0:
                continue
            t = np.clip(((xs - ax) * dx + (ys - ay) * dy) / L2, 0.0, 1.0)
            px, py = ax + t * dx - xs, ay + t * dy - ys
            d = px * px + py * py
            m = d < best_d
            best_d[m] = d[m]
            best_s[m] = s0 + t[m] * math.sqrt(L2)
        ss = np.array([p[0] for p in self.prof])
        zz = np.array([p[1] for p in self.prof])
        return np.interp(best_s, ss, zz)


def _boundary(rings, xs, ys):
    """The distance from each point to the rings' edges and the height along the nearest."""
    best_d = np.full(len(xs), np.inf)
    best_z = np.zeros(len(xs))
    for r in rings:
        for a, b in zip(r, r[1:] + r[:1]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            t = np.zeros(len(xs)) if L2 <= 0.0 else \
                np.clip(((xs - a[0]) * dx + (ys - a[1]) * dy) / L2, 0.0, 1.0)
            ex, ey = a[0] + t * dx - xs, a[1] + t * dy - ys
            d = np.sqrt(ex * ex + ey * ey)
            m = d < best_d
            best_d[m] = d[m]
            best_z[m] = a[2] + t[m] * (b[2] - a[2])
    return best_d, best_z


def face_z(rings, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """A face's height over the ground at points inside it: mean value coordinates of its
    boundary's heights (`pavement.mvc`), along the nearest edge within `ON_FACE_M` of it
    (where the coordinates divide by zero, and the points just outside it that
    `Surface.heights` counts as on it)."""
    from .pavement import mvc

    with np.errstate(divide="ignore", invalid="ignore"):
        z = mvc(rings, xs, ys)
    d, zb = _boundary(rings, xs, ys)
    use = (d <= ON_FACE_M) | ~np.isfinite(z)
    return np.where(use, zb, z)


class Surface:
    """The pavement map's faces as AG17 draws them (see the module docstring)."""

    def __init__(self, m):
        import shapely

        net = _g(m, "pavement_net")
        V = {}
        E = {}
        if net is not None:
            for v in _g(net, "vertices") or []:
                p = _g(v, "p")
                V[_g(v, "id")] = (float(p[0]), float(p[1]), float(_g(v, "z") or 0.0))
            for e in _g(net, "edges") or []:
                E[_g(e, "id")] = _g(e, "v")

        def ring_of(refs):
            pts = []
            for ref in refs:
                vs = E.get(ref.lstrip("-"))
                if vs is None:
                    return []
                vs = list(reversed(vs)) if ref.startswith("-") else vs
                for vid in vs:
                    p = V.get(vid)
                    if p is not None and (not pts or pts[-1] != p):
                        pts.append(p)
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts.pop()
            return pts

        self.rings, self.kinds, self.deck, polys = [], [], [], []
        for f in sorted(_g(m, "pavement") or [], key=lambda f: _g(f, "id")):
            rings = [ring_of(r) for r in _g(f, "rings") or []]
            rings = [r for r in rings if len(r) >= 3]
            if not rings:
                continue
            try:
                poly = shapely.Polygon([p[:2] for p in rings[0]],
                                       [[p[:2] for p in r] for r in rings[1:]])
            except Exception:                                        # noqa: BLE001
                continue
            if poly.is_empty or poly.area <= 1e-6:
                continue
            self.rings.append(rings)
            self.kinds.append(str(_g(f, "kind")))
            self.deck.append(str(_g(f, "layer") or "g0").startswith("d"))
            polys.append(poly)
        self.polys = polys
        self.tree = shapely.STRtree(polys) if polys else None
        self.roads = {_g(s, "id"): s for s in _g(m, "road_segments") or []}
        self._road = {}

    def road(self, sid) -> _Road | None:
        if sid not in self.roads:
            return None
        if sid not in self._road:
            self._road[sid] = _Road(self.roads[sid])
        return self._road[sid]

    def heights(self, xs, ys, ref, window, crossing, deck):
        """At each point the face height (lifted) nearest `ref` within `window` among the
        faces of its level (`deck`) holding it (within `ON_FACE_M`), else NaN."""
        import shapely

        n = len(xs)
        out = np.full(n, np.nan)
        if self.tree is None or n == 0:
            return out
        pts = shapely.points(xs, ys)
        pi, fi = self.tree.query(pts, predicate="dwithin", distance=ON_FACE_M)
        if len(pi) == 0:
            return out
        fdeck = np.array(self.deck)[fi]
        keep = fdeck == deck[pi]
        pi, fi = pi[keep], fi[keep]
        z = np.full(len(pi), np.nan)
        order = np.argsort(fi, kind="stable")
        pi, fi = pi[order], fi[order]
        bounds = np.flatnonzero(np.diff(fi)) + 1
        for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(fi)]):
            if a == b:
                continue
            f = int(fi[a])
            sel = pi[a:b]
            zf = face_z(self.rings[f], xs[sel], ys[sel])
            lift = LIFT_M.get(self.kinds[f], ROAD_LIFT_M)
            if self.kinds[f] == "median":
                zf = zf + np.where(crossing[sel], ROAD_LIFT_M, lift)
            else:
                zf = zf + lift
            z[a:b] = zf
        d = np.abs(z - ref[pi])
        ok = np.isfinite(d) & (d <= window[pi])
        pi, z, d = pi[ok], z[ok], d[ok]
        if len(pi) == 0:
            return out
        o = np.lexsort((d, pi))
        pi, z = pi[o], z[o]
        first = np.r_[True, pi[1:] != pi[:-1]]
        out[pi[first]] = z[first]
        return out


def _dp(s, z, keep, a, b, tol, out):
    """Douglas and Peucker in a profile: the samples between a and b whose height the line
    from a to b misses by more than `tol`."""
    if b - a < 2:
        return
    ds = s[b] - s[a]
    t = (s[a + 1:b] - s[a]) / ds if ds > 0 else np.zeros(b - a - 1)
    err = np.abs(z[a + 1:b] - (z[a] + t * (z[b] - z[a])))
    k = int(np.argmax(err))
    if err[k] > tol:
        c = a + 1 + k
        out.add(c)
        _dp(s, z, keep, a, c, tol, out)
        _dp(s, z, keep, c, b, tol, out)


def _samples(line, step):
    """Points every `step` m along a line's edges, its vertices among them: (xs, ys, own z,
    station, index of each vertex in the samples)."""
    xs, ys, zs, ss, vk = [], [], [], [], []
    s = 0.0
    for k, (p, q) in enumerate(zip(line, line[1:])):
        L = math.hypot(q[0] - p[0], q[1] - p[1])
        n = max(1, int(math.ceil(L / step - 1e-9)))
        vk.append(len(xs))
        for j in range(n):
            f = j / n
            xs.append(p[0] + (q[0] - p[0]) * f)
            ys.append(p[1] + (q[1] - p[1]) * f)
            zs.append(p[2] + (q[2] - p[2]) * f)
            ss.append(s + L * f)
        s += L
    vk.append(len(xs))
    p = line[-1]
    xs.append(p[0]); ys.append(p[1]); zs.append(p[2]); ss.append(s)
    return xs, ys, zs, ss, vk


def _key(p) -> tuple:
    return (round(float(p[0]), 2), round(float(p[1]), 2))


def _sampled(surface: Surface, items, step):
    """Walkways sampled and the surface's height at each sample, in one batch. `items`:
    (walkway, line, ref(xs, ys, own z, stations) -> the height to stand near and to fall
    back on). Returns [(walkway, xs, ys, own z, stations, vertex indices, surface z)]."""
    recs = []
    X, Y, R, W, C, D = [], [], [], [], [], []
    for w, line, ref_of in items:
        xs, ys, zs, ss, vk = _samples(line, step)
        xa, ya, za, sa = np.array(xs), np.array(ys), np.array(zs), np.array(ss)
        ref = ref_of(xa, ya, za, sa)
        recs.append((w, xa, ya, za, sa, vk, ref))
        X.append(xa); Y.append(ya); R.append(ref); W.append(np.full(len(xs), REACH_M))
        C.append(np.full(len(xs), _g(w, "kind") in CROSSING))
        D.append(np.full(len(xs), int(_g(w, "level") or 0) >= 1))
    if not recs:
        return []
    starts = np.cumsum([0] + [len(x) for x in X])
    zs = surface.heights(np.concatenate(X), np.concatenate(Y), np.concatenate(R),
                         np.concatenate(W), np.concatenate(C), np.concatenate(D))
    out = []
    for k, (w, xa, ya, za, sa, vk, ref) in enumerate(recs):
        zf = zs[starts[k]:starts[k + 1]]
        out.append((w, xa, ya, za, sa, vk, np.where(np.isfinite(zf), zf, ref)))
    return out


def _line(w) -> list:
    return [[float(v) for v in p] for p in _g(w, "line")]


def drape(m, step: float = STEP_M, tol: float = TOL_M, surface: Surface | None = None):
    """Each draped walkway's line on the surface: {id: (points [x, y, z over the ground],
    index of each of its vertices in them)}; the other walkways are left out.

    In rounds: first the walkways along a road (their reference the road's surface); then,
    up to `ROUNDS` times, the others with an end on a walkway already draped (their reference
    their own height moved by the difference at their ends, linearly along them, an end on
    none not moved: a crossing
    of a raised road, which the model keeps at the ground, climbs onto it with its
    sidewalks; a door's path rises to a raised sidewalk); then the rest at their own height.
    Ends that meet take the height of the first walkway draped there (by round, then id), so
    a lane goes on into the next at one height."""
    surface = surface if surface is not None else Surface(m)
    walks = sorted((w for w in _g(m, "walkways") or []
                    if _g(w, "kind") in DRAPED and len(_g(w, "line")) >= 2),
                   key=lambda w: _g(w, "id"))
    anchors: dict = {}
    done: dict = {}

    def by_road(rd):
        return lambda xa, ya, za, sa: rd.z(xa, ya) + CURB_LIFT_M

    def by_ends(line, d0, d1):
        def f(xa, ya, za, sa):
            L = float(sa[-1]) if len(sa) else 0.0
            t = sa / L if L > 0 else np.zeros(len(sa))
            return za + d0 + t * (d1 - d0)
        return f

    first, rest = [], []
    for w in walks:
        rd = surface.road(_attrs(w).get("segment")) if _g(w, "kind") in ROAD_KINDS else None
        (first if rd is not None else rest).append((w, rd))
    batch = [(w, _line(w), by_road(rd)) for w, rd in first]
    for rnd in range(ROUNDS + 2):
        for w, xa, ya, za, sa, vk, zf in _sampled(surface, batch, step):
            done[_g(w, "id")] = (w, xa, ya, sa, vk, zf)
            for i in (0, len(zf) - 1):
                anchors.setdefault(_key((xa[i], ya[i])), float(zf[i]))
        if not rest:
            break
        batch, left = [], []
        for w, _ in rest:
            line = _line(w)
            a, b = anchors.get(_key(line[0])), anchors.get(_key(line[-1]))
            if a is None and b is None and rnd < ROUNDS:
                left.append((w, None))
                continue
            # (an end on no draped walkway keeps its own height: a door, a stair's foot)
            d0 = (a - line[0][2]) if a is not None else 0.0
            d1 = (b - line[-1][2]) if b is not None else 0.0
            batch.append((w, line, by_ends(line, d0, d1)))
        rest = left
    out = {}
    for wid, (w, xa, ya, sa, vk, zf) in done.items():
        zf = zf.copy()
        for i in (0, len(zf) - 1):           # (ends that meet at one height)
            z = anchors.get(_key((xa[i], ya[i])))
            if z is not None and abs(z - zf[i]) <= REACH_M:
                zf[i] = z
        keep = set(vk)
        extra: set = set()
        for a, b in zip(vk, vk[1:]):
            _dp(sa, zf, keep, a, b, tol, extra)
        idx = sorted(keep | extra)
        line = _g(w, "line")
        vpos = {i: k for k, i in enumerate(vk)}
        pts = []
        for i in idx:
            if i in vpos:                    # (a vertex keeps its own plan position exactly)
                v = line[vpos[i]]
                pts.append([float(v[0]), float(v[1]), round(float(zf[i]), 3)])
            else:
                pts.append([round(float(xa[i]), 3), round(float(ya[i]), 3),
                            round(float(zf[i]), 3)])
        pos = {i: j for j, i in enumerate(idx)}
        out[wid] = (pts, [pos[i] for i in vk])
    return {k: out[k] for k in sorted(out)}


def check(m, lines: dict, step: float = CHECK_STEP_M, tol: float = CHECK_TOL_M,
          surface: Surface | None = None, ground=None) -> dict:
    """`walk_heights`: the exported lines (`lines`: {id: points}, heights over the ground, or
    absolute with `ground(id, x, y)`) of the draped walkways, sampled every `step` m between
    their points, within `tol` of the surface under them (the face nearest the line within
    `REACH_M`), except within `STEP_M` of a step in the surface (a curb, a face's edge
    another height: `CHECK_STEP_DZ_M` between two samples), which a line rounds off: the
    count, the worst, the ids off it, the samples left out at steps."""
    surface = surface if surface is not None else Surface(m)
    items = []
    for w in _g(m, "walkways") or []:
        pts = lines.get(_g(w, "id"))
        if pts is None or _g(w, "kind") not in DRAPED or len(pts) < 2:
            continue
        if ground is not None:
            pts = [[p[0], p[1], p[2] - ground(_g(w, "id"), p[0], p[1])] for p in pts]
        items.append((w, [[float(v) for v in p] for p in pts],
                      lambda xa, ya, za, sa: za))
    bad, worst, n, stepped = [], 0.0, 0, 0
    reach = int(math.ceil(STEP_M / step))
    for w, _, _, za, _, _, zf in _sampled(surface, items, step):
        n += 1
        d = np.abs(za - zf)
        jump = np.flatnonzero(np.abs(np.diff(zf)) > CHECK_STEP_DZ_M)
        if len(jump):
            near = np.zeros(len(zf), dtype=bool)
            for j in jump:
                near[max(0, j - reach):j + reach + 2] = True
            stepped += int(near.sum())
            d = np.where(near, 0.0, d)
        e = float(np.max(d)) if len(d) else 0.0
        worst = max(worst, e)
        if e > tol:
            bad.append((round(e, 3), _g(w, "id")))
    bad.sort(key=lambda r: (-r[0], r[1]))
    return {"walkways": n, "worst_m": round(worst, 3), "off": len(bad),
            "failed": sum(1 for d, _ in bad if d > CHECK_FAIL_M), "at_steps": stepped,
            "first": [f"{i}: {d} m" for d, i in bad[:10]]}
