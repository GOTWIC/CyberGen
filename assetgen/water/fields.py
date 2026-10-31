"""A water body's fields at many points, from a piece's inputs alone (no model), with M16's
arithmetic (`citygen/water.py`) wherever M16 defines a value:

- **Depth** (`Field.depth16`): M16's `Beds.depth_many` exactly: the nearest bank (its line,
  the land's edge; distances rounded, ties to the first bank in model order), 0 up to its
  waterline, then toe + (D - toe) ramp((d - width) / span); a river's or channel's D and span
  from its centerline (`along`, its widths). A piece carries the body's banks within
  `reach` of its tile, which is all that can set the depth there.
- **Bottom** (`Field.bottom`, `bottom`): the depth AG12 draws, one surface from the
  waterline down: M16's bed raised to every sloped bank's slope carried on under the water
  (a bank falls `height` over `width` to its waterline and on at that slope until it meets
  the bed; M16's bed steps from 0 to the toe at the waterline, and from one bank's profile to
  another's where the nearest bank changes), never within `SURFACE_GAP_M` of the surface
  (under a bank's dry strip, which the bed leaves out). Beside a wall (quay, canal wall) the
  bed is at the wall's toe up to its face (the bank's line), where AG7 and AG12 draw the
  walls, not M16's thickness out.
- **Level** (`Field.level`): the surface: a flat city's `WaterBed.surface_m`, else M13's
  level (a river's along its centerline, `Levels.at`).
- **Flow** (`Field.flow`): the current in m/s (x east, y north): along the body's flow line
  (rivers, channels, canals, creeks), the sea's tide along its nearest shore; its speed
  M16's, times the square root of the depth over the deepest depth there (slower over the
  shallows), none where still.
- **Foam** (`Field.foam`): 0 to 1, at a wall's face, a sloped bank's waterline (wider on a
  beach, faint by a marsh) and round bridge piers.
- **Waves** (`Field.waves`, the sea): the exposure's weight (open 1, sheltered 0.5, harbor
  0.15, from M16's zones on a blurred 16 m raster), zero at the waterline and full 20 m out.

Everything is elementwise numpy arithmetic (no transcendental but sqrt) or exact GEOS
distances, rounded where they decide anything, so the meshes are the same on every machine.
"""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import LineString

from citygen import water as WA

SURFACE_GAP_M = 0.05        # the bed stays this far under the surface
WALLS = ("quay", "canal_wall")
WALL_FOAM_M = 2.5           # foam fades over this from a wall's face
FOAM_M = {"natural_bank": 1.5, "riprap": 2.5, "road_embankment": 2.0, "beach": 7.0,
          "marsh_edge": 3.0}
FOAM_K = {"natural_bank": 0.55, "riprap": 1.0, "road_embankment": 0.9, "beach": 1.0,
          "marsh_edge": 0.35}
PIER_FOAM_M = 2.0
WAVE_RAMP_M = 20.0          # waves grow from nothing at the waterline over this
EXPOSURE_W = {"open": 1.0, "sheltered": 0.5, "harbor": 0.15}


def _arr(v) -> np.ndarray:
    return np.asarray(v, dtype=np.float64)


class Field:
    """The fields of one water body near one tile (`inputs` of a piece: `body`, `level`,
    `banks`; `piers` and `waves` where it has them)."""

    def __init__(self, inp: dict):
        b = inp["body"]
        self.b = b
        self.D0 = float(b["depth_m"])
        self.profile = b["profile"]
        self.reach0 = float(b["reach_m"])
        self.cl = None
        if b.get("centerline") and b.get("along"):
            pts = [tuple(p) for p in b["centerline"]]
            self.cl = (pts, WA._cum(pts), [float(w) for w in b["widths"]])
            self.along_s = _arr([a[0] for a in b["along"]])
            self.along_z = _arr([a[1] for a in b["along"]])
        lv = inp["level"]
        self.level_z = float(lv["z"])
        self.level_line = None
        if lv.get("profile") and lv.get("line"):
            lp = [tuple(p) for p in lv["line"]]
            self.level_line = (lp, WA._cum(lp), _arr([p[0] for p in lv["profile"]]),
                               _arr([p[1] for p in lv["profile"]]))
        bks = inp.get("banks") or []
        self.banks = bks
        self.kind = [k["kind"] for k in bks]
        self.lines = np.array([LineString(k["line"]) for k in bks], dtype=object)
        self.tree = shapely.STRtree(self.lines) if bks else None
        self.W = _arr([k["w"] for k in bks])
        self.TOE = _arr([k["toe"] for k in bks])
        self.H = _arr([k["h"] if k.get("h") is not None else 0.0 for k in bks])
        self.wall = np.array([k["kind"] in WALLS for k in bks], dtype=bool)
        fl = b.get("flow") or {}
        self.flow_kind = fl.get("kind", "still")
        self.speed = float(fl.get("speed", 0.0))
        self.flow_line = None
        if fl.get("line") and len(fl["line"]) >= 2:
            fp = [tuple(p) for p in fl["line"]]
            self.flow_line = (fp, WA._cum(fp))
        self.piers = [shapely.Polygon(p) for p in inp.get("piers") or []]
        self.ptree = shapely.STRtree(self.piers) if self.piers else None
        wv = inp.get("waves")
        self.wv = None
        if wv:
            self.wv = (float(wv["x0"]), float(wv["y0"]), float(wv["cell"]),
                       np.array(wv["v"], dtype=np.float64).reshape(wv["ny"], wv["nx"]))

    # -- the bank nearest a point --------------------------------------------------------

    def nearest(self, xs, ys) -> tuple[np.ndarray, np.ndarray]:
        """(index of the nearest bank, distance to its line), M16's `Beds._nearest`."""
        if self.tree is None:
            n = len(xs)
            return np.zeros(n, dtype=np.int64), np.full(n, 1e9)
        pts = shapely.points(np.stack([_arr(xs), _arr(ys)], axis=1))
        return WA.Beds._nearest(self.tree, self.lines, pts)

    def _d_reach(self, xs, ys) -> tuple[np.ndarray, np.ndarray]:
        n = len(xs)
        D = np.full(n, self.D0)
        reach = np.full(n, self.reach0)
        if self.cl is not None:
            pts, cum, ws = self.cl
            s = WA._project_many(pts, cum, _arr(xs), _arr(ys))
            D = np.interp(s, self.along_s, self.along_z)
            reach = np.maximum(1.0, np.interp(s, cum, ws) / 2.0)
        return D, reach

    def depth16(self, xs, ys, kd=None) -> np.ndarray:
        """M16's depth (`Beds.depth_many`)."""
        D, reach = self._d_reach(xs, ys)
        if self.tree is None:
            return D
        k, d = kd if kd is not None else self.nearest(xs, ys)
        w = self.W[k]
        toe = np.minimum(self.TOE[k], D)
        if self.profile == "flat":
            span = np.maximum(1.0, np.full(len(xs), WA.FLAT_REACH_M))
        else:
            span = np.maximum(1.0, reach - w)
        u = np.minimum(1.0, np.maximum(0.0, d - w) / span)
        ramp = u * (2.0 - u) if self.profile == "channel" else u
        return np.where(d < w, 0.0, toe + (D - toe) * ramp)

    def bottom(self, xs, ys, kd=None) -> np.ndarray:
        """AG12's depth of the bottom under the surface (see the module docstring)."""
        if kd is None:
            kd = self.nearest(xs, ys)
        d16 = self.depth16(xs, ys, kd)
        if self.tree is None:
            return np.maximum(d16, SURFACE_GAP_M)
        k, d = kd
        D, _ = self._d_reach(xs, ys)
        base = np.where(self.wall[k] & (d < self.W[k]), np.minimum(self.TOE[k], D), d16)
        return bottom(base, self.lines, self.W, self.H, ~self.wall, _arr(xs), _arr(ys))

    # -- the surface ---------------------------------------------------------------------

    def level(self, xs, ys) -> np.ndarray:
        n = len(xs)
        if self.level_line is None:
            return np.full(n, self.level_z)
        pts, cum, ps, pz = self.level_line
        return np.interp(WA._project_many(pts, cum, _arr(xs), _arr(ys)), ps, pz)

    def flow(self, xs, ys, depth, kd=None) -> tuple[np.ndarray, np.ndarray]:
        n = len(xs)
        vx, vy = np.zeros(n), np.zeros(n)
        if self.flow_kind == "still" or self.speed <= 0.0 or n == 0:
            return vx, vy
        if self.flow_line is not None:
            pts, cum = self.flow_line
            tx, ty = _tangent_many(pts, cum, _arr(xs), _arr(ys))
        elif self.tree is not None:
            k, _ = kd if kd is not None else self.nearest(xs, ys)
            tx, ty = _bank_tangent(self.lines[k], _arr(xs), _arr(ys))
        else:
            return vx, vy
        D, _ = self._d_reach(xs, ys)
        f = np.sqrt(np.clip(depth / np.maximum(D, 0.1), 0.0, 1.0))
        return self.speed * f * tx, self.speed * f * ty

    def foam(self, xs, ys, kd=None) -> np.ndarray:
        n = len(xs)
        out = np.zeros(n)
        if self.tree is not None:
            k, d = kd if kd is not None else self.nearest(xs, ys)
            w = self.W[k]
            fm = np.array([FOAM_M.get(x, 2.0) for x in self.kind])[k]
            fk = np.array([FOAM_K.get(x, 1.0) for x in self.kind])[k]
            slope_f = np.clip(1.0 - np.abs(d - w) / fm, 0.0, 1.0) * fk
            wall_f = np.clip(1.0 - d / WALL_FOAM_M, 0.0, 1.0)
            out = np.where(self.wall[k], wall_f, slope_f)
        if self.ptree is not None and n:
            pts = shapely.points(np.stack([_arr(xs), _arr(ys)], axis=1))
            _, dp = self.ptree.query_nearest(pts, all_matches=False, return_distance=True)
            dp = np.round(dp, 6)
            out = np.maximum(out, np.clip(1.0 - dp / PIER_FOAM_M, 0.0, 1.0))
        return out

    def waves(self, xs, ys, kd=None) -> np.ndarray:
        n = len(xs)
        if self.wv is None:
            return np.zeros(n)
        x0, y0, c, v = self.wv
        fx = np.clip((_arr(xs) - x0) / c - 0.5, 0.0, v.shape[1] - 1.000001)
        fy = np.clip((_arr(ys) - y0) / c - 0.5, 0.0, v.shape[0] - 1.000001)
        i, j = fx.astype(np.int64), fy.astype(np.int64)
        tx, ty = fx - i, fy - j
        i1, j1 = np.minimum(i + 1, v.shape[1] - 1), np.minimum(j + 1, v.shape[0] - 1)
        a = v[j, i] * (1.0 - tx) + v[j, i1] * tx
        b = v[j1, i] * (1.0 - tx) + v[j1, i1] * tx
        amp = a * (1.0 - ty) + b * ty
        if self.tree is not None:
            k, d = kd if kd is not None else self.nearest(xs, ys)
            amp = amp * np.clip((d - self.W[k]) / WAVE_RAMP_M, 0.0, 1.0)
        return amp


def bottom(base, lines, W, H, sloped, xs, ys) -> np.ndarray:
    """AG12's bottom: the depth `base` (M16's bed, at a wall's toe beside it) raised to every
    sloped bank's slope carried on under the water, h (d / w - 1) at distance d from its
    line (all of them, not only the nearest: where a slope meets a wall, or two slopes of
    different widths meet, the nearer bank's bed would step under the other's waterline),
    never within `SURFACE_GAP_M` of the surface."""
    out = np.array(base, dtype=np.float64)
    idx = np.flatnonzero(sloped)
    if len(idx) and len(xs):
        Wk = np.maximum(W[idx], 0.01)
        Hk = np.maximum(H[idx], 0.01)
        cap = float(np.max(out)) if len(out) else 0.0
        reach = Wk * (1.0 + cap / Hk)                 # (past this a slope is deeper than any)
        tree = shapely.STRtree(lines[idx])
        pts = shapely.points(np.stack([xs, ys], axis=1))
        pi, li = tree.query(pts, predicate="dwithin", distance=float(reach.max()))
        if len(pi):
            d = np.round(shapely.distance(lines[idx][li], pts[pi]), 6)
            s = Hk[li] * (d / Wk[li] - 1.0)
            np.minimum.at(out, pi, s)
    return np.maximum(out, SURFACE_GAP_M)


def bed_depth(bottom, lift: float) -> np.ndarray:
    """The bed's depth under the surface as drawn: the bottom, less the lift a terrain city's
    bed takes over M13's ground grid (which carries M16's beds too), never within
    `SURFACE_GAP_M` of the surface."""
    return np.maximum(np.asarray(bottom) - lift, SURFACE_GAP_M)


def _tangent_many(pts, cum, xs, ys) -> tuple[np.ndarray, np.ndarray]:
    """The unit direction of a polyline at the nearest point to each point."""
    A = np.asarray(pts[:-1], dtype=np.float64)
    B = np.asarray(pts[1:], dtype=np.float64)
    AB = B - A
    L = np.sqrt((AB * AB).sum(axis=1))
    L = np.where(L > 0, L, 1.0)
    T = AB / L[:, None]
    s = WA._project_many(pts, cum, xs, ys)
    c = np.asarray(cum)
    j = np.clip(np.searchsorted(c, s, side="right") - 1, 0, len(A) - 1)
    return T[j, 0], T[j, 1]


def _bank_tangent(lines, xs, ys) -> tuple[np.ndarray, np.ndarray]:
    """The direction of each point's bank line at its nearest point (water on the left)."""
    pts = shapely.points(np.stack([xs, ys], axis=1))
    s = shapely.line_locate_point(lines, pts)
    L = shapely.length(lines)
    a = shapely.line_interpolate_point(lines, np.maximum(s - 0.5, 0.0))
    b = shapely.line_interpolate_point(lines, np.minimum(s + 0.5, L))
    ax, ay = shapely.get_x(a), shapely.get_y(a)
    bx, by = shapely.get_x(b), shapely.get_y(b)
    dx, dy = bx - ax, by - ay
    n = np.sqrt(dx * dx + dy * dy)
    n = np.where(n > 1e-9, n, 1.0)
    return np.round(dx / n, 4), np.round(dy / n, 4)
