"""Terrain (M13): the ground of a city with hills, ridges, cliffs and flat districts.

A spec without `terrain` builds a flat city at sea level, exactly as before M13. With it:

- `field` shapes the natural ground on a grid of points `CELL_M` apart (`Field`): hills
  and ridges as smooth bumps, a smooth random relief, a rise inland from the sea, then carved
  down to the water (every river, channel and waterway at its own level, banks at most
  `BANK_GRADE` steep), cliff districts lifted onto plateaus, flat districts and megasites
  levelled.
- `grade` (after M2) fits a grade line to every road: on the graph of all roads (every node
  and every crossing without a node shared), the profile closest to the ground in the
  largest deviation whose grade stays within the road class's maximum, less the grade the
  road's own z profile already climbs. It writes the finished ground (road corridors on their
  grade lines, embankments at 1:1.5, retaining walls where an embankment would run on too
  far), and bored tunnels where a primary road would cut deep into a hill.
- `seat` (after M3) sets each building's base at its entrance and its plinth.

Every z elsewhere in the model stays measured from the finished ground where it stands, so
clearances and depths need no change; grades are measured on ground + z.

Arithmetic: numpy elementwise operations only (+, -, *, /, sqrt, minimum, maximum: each
correctly rounded, so every machine gets the same bits), Python sums in a fixed order, values
rounded to the 0.01 m grid. No numpy reduction (its summation order depends on the CPU).
"""
from __future__ import annotations

import hashlib
import heapq
import math
from dataclasses import dataclass, field as dfield

import numpy as np
from shapely.geometry import Point

from . import geom as G

CELL_M = 4.0
BANK_M = 1.5            # ground over the water at a bank
BANK_GRADE = 0.10       # river, canal and basin banks at most this steep
SEA_GRADE = 0.12        # the land from a low shore
LEVEE_M = 0.3           # land next to water stays this much over it
FLAT_BAND_M = 160.0     # a flat district blends into its neighbors over this band
SITE_BAND_M = 60.0      # a megasite likewise

# road grade lines (M13)
STEP_M = 10.0           # stations along a road for the grade fit
LEVEL_GRADE = 0.02      # M18: a primary road's grade line over a junction and 10 m past it
LEVEL_SLOPE_MAX = 0.04  # ... where the natural ground at the junction is no steeper than this
LEVEL_DEV_MAX = 4.0     # ... and its grade line, without the runs, within this of that ground
MAX_GRADE = {"highway": 0.06, "avenue": 0.08, "street": 0.12, "alley": 0.15,
             "service": 0.12, "pedestrian": 0.15, "footbridge": 0.15}
EMBANK_SLOPE = 1.5      # embankments 1:1.5 (run per rise)
EMBANK_RUN_M = 9.0      # longest embankment run; beyond it a retaining wall
WALL_MIN_M = 1.5        # a retaining wall only where the step is at least this high
CUT_MAX_M = 20.0        # deepest open cut (between retaining walls)
FILL_MAX_M = 18.0       # highest fill (between retaining walls)
BORE_MIN_M = 14.0       # a primary road this far under the natural ground is bored through
BORE_LEN_M = 40.0       # over at least this length
VIADUCT_MIN_M = 15.0    # a primary road this far over the natural ground stands on columns
VIADUCT_LEN_M = 20.0    # over at least this length
COLUMN_STEP_M = 32.0    # columns under a terrain viaduct
COLUMN_MIN_M = 6.0      # only where the deck is at least this high
STEEP_LOT_M = 15.0      # a lot whose ground falls more than this becomes a hillside green
BORE_CLEAR_M = 5.5
BORE_ROOF_M = 1.5


def q(v: float) -> float:
    return round(v + 0.0, 2)


@dataclass
class Field:
    """Heights on grid points: arr[j, i] at (x0 + i cell, y0 + j cell)."""
    x0: float
    y0: float
    cell: float
    arr: np.ndarray

    @property
    def nx(self) -> int:
        return self.arr.shape[1]

    @property
    def ny(self) -> int:
        return self.arr.shape[0]

    def at(self, x: float, y: float) -> float:
        """Bilinear height at (x, y), clamped to the grid."""
        fx = (x - self.x0) / self.cell
        fy = (y - self.y0) / self.cell
        fx = min(max(fx, 0.0), self.nx - 1.000001)
        fy = min(max(fy, 0.0), self.ny - 1.000001)
        i, j = int(fx), int(fy)
        tx, ty = fx - i, fy - j
        a = self.arr
        h0 = a[j, i] * (1.0 - tx) + a[j, i + 1] * tx
        h1 = a[j + 1, i] * (1.0 - tx) + a[j + 1, i + 1] * tx
        return float(h0 * (1.0 - ty) + h1 * ty)

    def at_many(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """Bilinear heights at many points (elementwise, like `at`)."""
        fx = np.minimum(np.maximum((xs - self.x0) / self.cell, 0.0), self.nx - 1.000001)
        fy = np.minimum(np.maximum((ys - self.y0) / self.cell, 0.0), self.ny - 1.000001)
        i = fx.astype(np.int64)
        j = fy.astype(np.int64)
        tx, ty = fx - i, fy - j
        a = self.arr
        h0 = a[j, i] * (1.0 - tx) + a[j, i + 1] * tx
        h1 = a[j + 1, i] * (1.0 - tx) + a[j + 1, i + 1] * tx
        return h0 * (1.0 - ty) + h1 * ty

    def slope_many(self, xs: np.ndarray, ys: np.ndarray, e: float = 12.0) -> np.ndarray:
        gx = (self.at_many(xs + e, ys) - self.at_many(xs - e, ys)) / (2 * e)
        gy = (self.at_many(xs, ys + e) - self.at_many(xs, ys - e)) / (2 * e)
        return np.sqrt(gx * gx + gy * gy)

    def grads(self, x: float, y: float) -> tuple[float, float]:
        e = self.cell
        return ((self.at(x + e, y) - self.at(x - e, y)) / (2 * e),
                (self.at(x, y + e) - self.at(x, y - e)) / (2 * e))

    def slope(self, x: float, y: float) -> float:
        gx, gy = self.grads(x, y)
        return math.sqrt(gx * gx + gy * gy)

    def rows(self) -> list[list[float]]:
        return [[float(v) for v in row] for row in np.round(self.arr, 2)]

    @classmethod
    def from_rows(cls, t, rows) -> Field:
        return cls(t.x0, t.y0, t.cell_m, np.array(rows, dtype=np.float64))

    def grid(self) -> tuple[np.ndarray, np.ndarray]:
        xs = self.x0 + np.arange(self.nx, dtype=np.float64) * self.cell
        ys = self.y0 + np.arange(self.ny, dtype=np.float64) * self.cell
        return np.meshgrid(xs, ys)


@dataclass
class Levels:
    """Water levels: one per body, a profile for rivers and channels that fall."""
    level: dict[str, float] = dfield(default_factory=dict)
    profile: dict[str, list[tuple[float, float]]] = dfield(default_factory=dict)

    def rows(self) -> list[dict]:
        return [{"water_id": k, "level_m": q(v),
                 "profile": [{"s": q(s), "z": q(z)} for s, z in self.profile.get(k, [])]}
                for k, v in sorted(self.level.items())]


# --- small exact helpers ------------------------------------------------------

def smoothstep(t: np.ndarray) -> np.ndarray:
    t = np.minimum(np.maximum(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def fade(t):
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _u(seed: int, *k: int) -> float:
    """A value in [-1, 1] from a hash of integers (no RNG state, same on every machine)."""
    h = hashlib.blake2b(repr((seed,) + k).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2 ** 63 - 1.0


def seg_dist(X, Y, ax, ay, bx, by):
    """Distance from grid points to segment ab, elementwise."""
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    if ll == 0.0:
        t = 0.0
    else:
        t = np.minimum(np.maximum(((X - ax) * dx + (Y - ay) * dy) / ll, 0.0), 1.0)
    px = X - (ax + t * dx)
    py = Y - (ay + t * dy)
    return np.sqrt(px * px + py * py), t


def ring_dist(X, Y, ring) -> np.ndarray:
    """Distance from grid points to a closed ring (list of points)."""
    best = None
    for k in range(len(ring) - 1):
        (ax, ay), (bx, by) = ring[k], ring[k + 1]
        d, _ = seg_dist(X, Y, ax, ay, bx, by)
        best = d if best is None else np.minimum(best, d)
    return best


def _rings(poly) -> list[list[tuple[float, float]]]:
    out = []
    for p in G.parts(poly):
        out.append(list(p.exterior.coords))
        out += [list(r.coords) for r in p.interiors]
    return out


def ring_dist_many(X, Y, segs) -> np.ndarray:
    best = None
    for (ax, ay), (bx, by) in segs:
        d, _ = seg_dist(X, Y, ax, ay, bx, by)
        best = d if best is None else np.minimum(best, d)
    return best


def _facing_edges(poly, facing) -> tuple[list, list]:
    """A polygon's boundary edges split into those whose outward normal faces one of the
    directions (within 67.5 degrees) and the rest."""
    steep, soft = [], []
    for part in G.parts(poly):
        ring = list(part.exterior.coords)
        area2 = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))
        sgn = 1.0 if area2 > 0 else -1.0       # counterclockwise: outward is to the right
        for a, b in zip(ring, ring[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy)
            if L == 0:
                continue
            nx_, ny_ = sgn * dy / L, -sgn * dx / L
            hit = False
            for f in facing:
                vx, vy = DIRS[f]
                vl = math.hypot(vx, vy)
                if (nx_ * vx + ny_ * vy) / vl > 0.38:
                    hit = True
            (steep if hit else soft).append((a, b))
    return steep, soft


def poly_dist(X, Y, poly) -> np.ndarray:
    best = None
    for r in _rings(poly):
        d = ring_dist(X, Y, r)
        best = d if best is None else np.minimum(best, d)
    return best


def inside(X, Y, poly) -> np.ndarray:
    import shapely

    return shapely.contains_xy(poly, X, Y) | shapely.intersects_xy(poly.boundary, X, Y)


def _window(f: Field, x0, y0, x1, y1):
    """Index slices of the grid points within a box."""
    i0 = max(0, int(math.floor((x0 - f.x0) / f.cell)))
    i1 = min(f.nx, int(math.ceil((x1 - f.x0) / f.cell)) + 1)
    j0 = max(0, int(math.floor((y0 - f.y0) / f.cell)))
    j1 = min(f.ny, int(math.ceil((y1 - f.y0) / f.cell)) + 1)
    return slice(j0, j1), slice(i0, i1)


# --- where things are ---------------------------------------------------------

DIRS = {"north": (0, 1), "north_east": (1, 1), "east": (1, 0), "south_east": (1, -1),
        "south": (0, -1), "south_west": (-1, -1), "west": (-1, 0), "north_west": (-1, 1),
        "center": (0, 0)}


def place(model, at: str) -> tuple[float, float]:
    """A district's middle (its centroid, or a point on it when the centroid falls outside),
    else a direction from the map's middle, 0.75 of the way to the edge."""
    x0, y0, x1, y1 = model.bounds
    for d in model.districts:
        if d.name == at:
            poly = G.from_model_poly(d.polygon)
            c = poly.centroid
            if not poly.contains(c):
                c = poly.point_on_surface()
            return q(c.x), q(c.y)
    dx, dy = DIRS[at]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return q(cx + dx * 0.75 * (x1 - x0) / 2), q(cy + dy * 0.75 * (y1 - y0) / 2)


# --- the natural ground -------------------------------------------------------

def _relief(spec, X, Y) -> np.ndarray:
    t = spec.terrain
    out = np.zeros_like(X)
    if t.relief_m <= 0:
        return out
    for octave, (scale, amp) in enumerate(((t.relief_scale_m, 1.0),
                                           (t.relief_scale_m / 2.0, 0.45))):
        fx = X / scale
        fy = Y / scale
        ix = np.floor(fx)
        iy = np.floor(fy)
        tx = fade(fx - ix)
        ty = fade(fy - iy)
        lo_i, hi_i = int(ix.min()), int(ix.max()) + 1
        lo_j, hi_j = int(iy.min()), int(iy.max()) + 1
        lat = {(i, j): _u(spec.seed or 0, 13, octave, i, j)
               for i in range(lo_i, hi_i + 1) for j in range(lo_j, hi_j + 1)}
        tab = np.array([[lat[(i, j)] for i in range(lo_i, hi_i + 1)]
                        for j in range(lo_j, hi_j + 1)], dtype=np.float64)
        a = (ix - lo_i).astype(np.int64)
        b = (iy - lo_j).astype(np.int64)
        v00, v10 = tab[b, a], tab[b, a + 1]
        v01, v11 = tab[b + 1, a], tab[b + 1, a + 1]
        v = (v00 * (1 - tx) + v10 * tx) * (1 - ty) + (v01 * (1 - tx) + v11 * tx) * ty
        out = out + v * (amp * t.relief_m / 1.45)
    return out


def _bump(d2, r):
    qq = np.minimum(d2 / (r * r), 1.0)
    w = 1.0 - qq
    return w * w


def water_bodies(model) -> list[tuple[str, str, object, object]]:
    """(id, kind, polygon, centerline or None) of every water body, sea first."""
    out = []
    for s in model.seas:
        out.append((s.id, "sea", G.union(G.from_model_polys(s.polygons)), None))
    for r in model.rivers:
        out.append((r.id, "river", G.from_model_poly(r.polygon), r))
    for c in model.channels:
        out.append((c.id, c.kind, G.from_model_poly(c.polygon), c))
    for w in model.waterways:
        out.append((w.id, "waterway", G.from_model_poly(w.polygon), w))
    return out


def _coast_points(model, poly, step=CELL_M) -> list[tuple[float, float]]:
    """Points along a water body's banks every `step` (not along the map's edge)."""
    x0, y0, x1, y1 = model.bounds
    pts = []
    for r in _rings(poly):
        for k in range(len(r) - 1):
            (ax, ay), (bx, by) = r[k], r[k + 1]
            if (abs(ax - bx) < 1e-6 and (abs(ax - x0) < 1 or abs(ax - x1) < 1)) or \
               (abs(ay - by) < 1e-6 and (abs(ay - y0) < 1 or abs(ay - y1) < 1)):
                continue
            n = max(1, int(math.ceil(math.hypot(bx - ax, by - ay) / step)))
            for i in range(n):
                t = i / n
                pts.append((ax + (bx - ax) * t, ay + (by - ay) * t))
    return pts


def _line_samples(line, step=CELL_M * 2):
    """(x, y, s) along a polyline every `step`."""
    out = []
    s = 0.0
    for k in range(len(line) - 1):
        (ax, ay), (bx, by) = line[k], line[k + 1]
        L = math.hypot(bx - ax, by - ay)
        n = max(1, int(math.ceil(L / step)))
        for i in range(n):
            t = i / n
            out.append((ax + (bx - ax) * t, ay + (by - ay) * t, s + L * t))
        s += L
    out.append((line[-1][0], line[-1][1], s))
    return out


def levels(model, raw: Field) -> Levels:
    """The sea at 0; rivers and channels falling along their centerline (never rising
    downstream, a bank under the ground they cross); waterways at the level of what they
    join, ornamental ones at their lowest bank."""
    lv = Levels()
    sea = None
    for wid, kind, poly, ent in water_bodies(model):
        if kind == "sea":
            lv.level[wid] = 0.0
            sea = poly if sea is None else G.union([sea, poly])
    for wid, kind, poly, ent in water_bodies(model):
        if kind in ("river", "separation"):
            line = [tuple(p) for p in ent.centerline]
            if kind == "river" and ent.mouth == "sea" and sea is not None:
                from shapely.geometry import Point

                if Point(line[0]).distance(sea) < Point(line[-1]).distance(sea):
                    line = line[::-1]
                    rev = True
                else:
                    rev = False
            else:
                rev = False
            sm = _line_samples(line)
            prof, low = [], math.inf
            for x, y, s in sm:
                low = min(low, raw.at(x, y) - BANK_M)
                prof.append((s, max(0.0, q(low))))
            if kind == "separation":
                lvl = min(z for _, z in prof)
                prof = [(s, lvl) for s, _ in prof]
            if ent.flows_into == "sea" or getattr(ent, "mouth", None) == "sea":
                prof[-1] = (prof[-1][0], 0.0)
                prof = [(s, min(z, prof[-1][1] + (prof[-1][0] - s) * 0.002)) for s, z in prof]
            total = prof[-1][0]
            if rev:
                prof = [(q(total - s), z) for s, z in reversed(prof)]
            lv.profile[wid] = prof
            lv.level[wid] = min(z for _, z in prof)
        elif kind in ("delta_branch", "sea_channel"):
            lv.level[wid] = 0.0
    for wid, kind, poly, ent in water_bodies(model):
        if kind != "waterway":
            continue
        if ent.ornamental or not ent.connects_to:
            lvl = min(raw.at(x, y) for x, y in _coast_points(model, poly, 16.0)) - BANK_M
            lv.level[wid] = max(0.0, q(lvl))
        else:
            lv.level[wid] = level_near(lv, model, ent.connects_to, poly)
    return lv


def level_near(lv: Levels, model, wid: str, poly) -> float:
    if wid in ("sea",) or wid not in lv.level:
        return lv.level.get(wid, 0.0)
    prof = lv.profile.get(wid)
    if not prof:
        return lv.level[wid]
    ent = next((e for e in list(model.rivers) + list(model.channels) if e.id == wid), None)
    if ent is None:
        return lv.level[wid]
    from shapely.geometry import LineString

    ln = LineString([tuple(p) for p in ent.centerline])
    s = ln.project(poly.representative_point())
    return level_at(prof, s)


def level_at(prof, s: float) -> float:
    for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
        if s <= s1:
            t = 0.0 if s1 == s0 else min(max((s - s0) / (s1 - s0), 0.0), 1.0)
            return z0 + (z1 - z0) * t
    return prof[-1][1]


def water_groups(model, lv: Levels) -> dict:
    """Water bodies merged by level: {(kind, level or id): (kind, polygon, profile, entity)};
    a river or channel with a falling profile stays alone."""
    flat: dict[tuple, list] = {}
    out = {}
    for wid, kind, poly, ent in water_bodies(model):
        if wid in lv.profile and len({z for _, z in lv.profile[wid]}) > 1:
            out[("river", wid)] = ("river", poly, lv.profile[wid], ent)
            continue
        k = "sea" if kind in ("sea", "sea_channel", "delta_branch") else "bank"
        flat.setdefault((k, lv.level.get(wid, 0.0)), []).append(poly)
    for (k, lvl), polys in sorted(flat.items()):
        out[(k, lvl)] = (k, G.union(polys), None, None)
    return out


def field(spec, model) -> tuple[Field, Levels, dict]:
    """The natural ground of a city with `spec.terrain`."""
    t = spec.terrain
    x0, y0, x1, y1 = model.bounds
    nx = int(math.ceil((x1 - x0) / CELL_M)) + 1
    ny = int(math.ceil((y1 - y0) / CELL_M)) + 1
    f = Field(x0, y0, CELL_M, np.zeros((ny, nx)))
    X, Y = f.grid()
    seaU = G.union([p for s in model.seas for p in G.from_model_polys(s.polygons)]) \
        if model.seas else None
    H = np.full_like(X, t.shore_m)
    stats: dict = {"hills": [], "ridges": [], "cliffs": [], "flat": []}
    if t.inland_grade > 0 and seaU is not None:
        H = H + t.inland_grade * np.minimum(poly_dist(X, Y, seaU), 6000.0)
    for hl in t.hills:
        cx, cy = place(model, hl.at)
        d2 = (X - cx) * (X - cx) + (Y - cy) * (Y - cy)
        H = H + hl.height_m * _bump(d2, hl.radius_m)
        stats["hills"].append({"name": hl.name, "at": [cx, cy], "height_m": hl.height_m})
    for rd in t.ridges:
        ax, ay = place(model, rd.from_)
        bx, by = place(model, rd.to)
        d, _ = seg_dist(X, Y, ax, ay, bx, by)
        H = H + rd.height_m * _bump(d * d, rd.width_m / 2.0)
        stats["ridges"].append({"name": rd.name, "from": [ax, ay], "to": [bx, by]})
    H = H + _relief(spec, X, Y)
    raw = Field(x0, y0, CELL_M, H)
    lv = levels(model, raw)
    # carve down to the water: banks at most BANK_GRADE (SEA_GRADE from the sea) steep
    import shapely

    P = shapely.points(X.ravel(), Y.ravel())
    groups = water_groups(model, lv)
    near = {}
    for key, (kind, poly, prof, ent) in groups.items():
        D = shapely.distance(P, poly).reshape(X.shape)
        if prof is not None:
            from shapely.geometry import LineString

            ln = LineString([tuple(p) for p in ent.centerline])
            ss = shapely.line_locate_point(ln, P).reshape(X.shape)
            lvl = np.interp(ss, np.array([s for s, _ in prof]), np.array([z for _, z in prof]))
        else:
            lvl = key[1]
        g = SEA_GRADE if kind == "sea" else BANK_GRADE
        H = np.minimum(H, lvl + BANK_M + g * D)
        near[key] = (D, lvl)
    # cliffs: districts on plateaus
    for cl in t.cliffs:
        dpoly = _district_poly(model, cl.district)
        if dpoly is None:
            continue
        bx0, by0, bx1, by1 = dpoly.bounds
        js, iss = _window(f, bx0, by0, bx1, by1)
        Xs, Ys = X[js, iss], Y[js, iss]
        inn = inside(Xs, Ys, dpoly)
        if cl.facing:
            steep, soft = _facing_edges(dpoly, cl.facing)
            ds = ring_dist_many(Xs, Ys, steep) if steep else np.full(Xs.shape, np.inf)
            dw = ring_dist_many(Xs, Ys, soft) if soft else np.full(Xs.shape, np.inf)
            ramp = np.minimum(smoothstep(ds / cl.width_m), smoothstep(dw / cl.slope_m))
        else:
            ramp = smoothstep(poly_dist(Xs, Ys, dpoly) / cl.width_m)
        lift = np.where(inn, cl.height_m * ramp, 0.0)
        H[js, iss] = H[js, iss] + lift
        stats["cliffs"].append({"district": cl.district, "height_m": cl.height_m})
    # flat districts and megasites
    # (M14: a district with decks is levelled too: a slab on columns over level ground)
    names = list(t.flat) + [d.name for d in spec.districts
                            if d.decks is not None and d.name not in t.flat]
    flats = [(n, _district_poly(model, n), FLAT_BAND_M) for n in names]
    flats += [(s.name or s.id, G.from_model_poly(s.polygon), SITE_BAND_M)
              for s in model.megasites]
    for name, poly, band in flats:
        if poly is None:
            continue
        bx0, by0, bx1, by1 = poly.bounds
        js, iss = _window(f, bx0 - band, by0 - band, bx1 + band, by1 + band)
        Xs, Ys = X[js, iss], Y[js, iss]
        inn = inside(Xs, Ys, poly)
        vals = [float(v) for v in H[js, iss][inn]]
        if not vals:
            continue
        lvl = q(math.fsum(vals) / len(vals))
        d = np.where(inn, 0.0, poly_dist(Xs, Ys, poly))
        w = 1.0 - smoothstep(d / band)
        H[js, iss] = H[js, iss] + (lvl - H[js, iss]) * w
        stats["flat"].append({"name": name, "level_m": lvl})
    # water at its level, land a little over it
    wet = np.zeros(H.shape, dtype=bool)
    for key, (D, lvl) in near.items():
        H = np.where(D == 0.0, lvl, H)
        wet |= D == 0.0
    for key, (D, lvl) in near.items():
        H = np.where(~wet & (D < 3 * CELL_M), np.maximum(H, lvl + LEVEE_M), H)
    H = np.round(H, 2)
    f.arr = H
    stats["max_m"] = q(float(np.max(H)))
    return f, lv, stats


def shapely_inside(X, Y, poly):
    import shapely

    return shapely.contains_xy(poly, X, Y)


def _district_poly(model, name: str):
    for d in model.districts:
        if d.name == name:
            return G.from_model_poly(d.polygon)
    return None


def terrain_rows(f: Field, lv: Levels, stats: dict, ground: Field | None = None) -> dict:
    return {"cell_m": f.cell, "x0": f.x0, "y0": f.y0, "nx": f.nx, "ny": f.ny,
            "natural": f.rows(), "ground": ground.rows() if ground is not None else [],
            "water_levels": lv.rows(), "stats": stats}


# --- grade lines (after M2) ---------------------------------------------------

def _zp(prof) -> list[tuple[float, float]]:
    return [(p["s"], p["z"]) if isinstance(p, dict) else (p.s, p.z) for p in prof]


def z_on(prof, s: float) -> float:
    if not prof:
        return 0.0
    return level_at(prof, s)


def _cum(line) -> list[float]:
    out = [0.0]
    for (ax, ay), (bx, by) in zip(line, line[1:]):
        out.append(out[-1] + math.hypot(bx - ax, by - ay))
    return out


def point_at(line, cum, s: float) -> tuple[float, float]:
    for k in range(len(line) - 1):
        if s <= cum[k + 1] or k == len(line) - 2:
            L = cum[k + 1] - cum[k]
            t = 0.0 if L == 0 else min(max((s - cum[k]) / L, 0.0), 1.0)
            (ax, ay), (bx, by) = line[k], line[k + 1]
            return ax + (bx - ax) * t, ay + (by - ay) * t
    return tuple(line[-1])


def crossings(segments) -> dict[str, list[tuple[float, tuple]]]:
    """Points where two roads cross without a shared node (one passes over the other):
    {segment id: [(s, key)]}, the key shared by both roads."""
    import shapely
    from shapely.geometry import LineString

    lines = [LineString([tuple(p) for p in s["centerline"]]) for s in segments]
    tree = shapely.STRtree(lines)
    ends = [{tuple(s["centerline"][0]), tuple(s["centerline"][-1])} for s in segments]
    out: dict[str, list] = {}
    a_idx, b_idx = tree.query(lines, predicate="intersects")
    pairs = sorted({(min(a, b), max(a, b)) for a, b in zip(a_idx.tolist(), b_idx.tolist())
                    if a != b})
    for a, b in pairs:
        sa, sb = segments[a], segments[b]
        if {sa["start"], sa["end"]} & {sb["start"], sb["end"]} and \
                lines[a].intersection(lines[b]).geom_type == "Point":
            shared = True
        else:
            shared = False
        inter = lines[a].intersection(lines[b])
        pts = [inter] if inter.geom_type == "Point" else \
            [g for g in getattr(inter, "geoms", []) if g.geom_type == "Point"]
        for p in sorted(pts, key=lambda g: (round(g.x, 2), round(g.y, 2))):
            xy = (round(p.x, 2), round(p.y, 2))
            if shared or any(math.hypot(xy[0] - e[0], xy[1] - e[1]) < 1.0
                             for e in ends[a] | ends[b]):
                continue
            key = ("x", sa["id"], sb["id"], xy)
            out.setdefault(sa["id"], []).append((round(lines[a].project(p), 2), key))
            out.setdefault(sb["id"], []).append((round(lines[b].project(p), 2), key))
    return out


@dataclass
class Graded:
    ground: dict[str, list[tuple[float, float]]]     # segment id -> [(s, grade line)]
    node_ground: dict[str, float]
    finished: Field
    walls: list[dict]
    bores: list[dict]
    viaducts: list[dict]
    stats: dict


def _lipschitz(n: int, adj: list[list[tuple[int, int]]], target: list[int],
               frozen: frozenset = frozenset()) -> list[int]:
    """min over v of target[v] + d(v, u): Dijkstra from every vertex at once (integers);
    `frozen` vertices keep their target (bounds pass through them only from it)."""
    dist = list(target)
    heap = [(d, i) for i, d in enumerate(dist)]
    heapq.heapify(heap)
    while heap:
        d, u = heapq.heappop(heap)
        if d != dist[u]:
            continue
        for v, w in adj[u]:
            nd = d + w
            if nd < dist[v] and v not in frozen:
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def water_union(model):
    return G.union([poly for _, _, poly, _ in water_bodies(model)])


def grade(spec, segments, nodes, nat: Field, water=None, held: dict | None = None,
          level: dict | None = None) -> Graded:
    """Grade lines of every road: the profile closest to the natural ground in the largest
    deviation (the mean of the lowest and highest profiles within the grade limits) on the
    graph of all roads, every node and every crossing without a node shared. `held` (M10, a
    district regeneration): segment id -> the grade line it keeps, [(s, z)]; their vertices
    are fixed at it and the rest is fitted to them. `level`: (segment id, node id) -> the
    junction's run along that leg's centerline (out to the edge of its polygon, past its curb
    and sidewalk corners: `junctions.cutbacks`, `run_along`, and M18's LEVEL_OUT_M beyond),
    at most 0.45 of the leg; over it a local road's grade line holds the node's height, so
    its roads meet at one height at the corners, and (M18) a primary road's is at most
    LEVEL_GRADE steep (held level, its fills and cuts would pass CUT_MAX_M and FILL_MAX_M on
    a long hill); the junction carries the surface between (`junctions.surfaces`)."""
    held = held or {}
    level = dict(level or {})
    # (M18: a primary road holds a junction's run only where the natural ground there is
    # gentle; on a steeper hill it keeps its grade through, and the junction its surface; a
    # local road at a junction with a primary road takes its height from it, as in M13)
    seg_of = {s["id"]: s for s in segments}
    npos = {n["id"]: tuple(n["position"][:2]) for n in nodes}
    prim = {n for s in segments if s["road_class"] in PRIMARY or _ramp(s)
            for n in (s["start"], s["end"])}
    for k in sorted(level):
        s = seg_of.get(k[0])
        if s is None or k[1] not in npos:
            continue
        if not (s["road_class"] in PRIMARY or _ramp(s)):
            if k[1] in prim:
                del level[k]
        elif float(nat.slope_many(np.array([npos[k[1]][0]]),
                                  np.array([npos[k[1]][1]]))[0]) > LEVEL_SLOPE_MAX:
            del level[k]
    node_pos = {n["id"]: tuple(n["position"][:2]) for n in nodes}
    cross = crossings(segments)

    def solve(level):
        """The grade lines with these level runs: (elevation per vertex, vertex ids,
        chains)."""
        vid: dict = {}
        pos: list[tuple[float, float]] = []

        def vertex(key, xy):
            if key not in vid:
                vid[key] = len(pos)
                pos.append(xy)
            return vid[key]

        chains = {}
        for s in segments:
            line = [tuple(p) for p in s["centerline"]]
            cum = _cum(line)
            L = cum[-1]
            n = max(1, int(math.ceil(L / STEP_M)))
            stations = {round(L * k / n, 2): None for k in range(n + 1)}
            for sx, key in cross.get(s["id"], []):
                stations[sx] = key
            for sx in _level_runs(s, round(L, 2), level):
                stations.setdefault(sx, None)
            ss = sorted(stations)
            ch = []
            for k, sv in enumerate(ss):
                if k == 0:
                    v = vertex(("n", s["start"]), node_pos[s["start"]])
                elif k == len(ss) - 1:
                    v = vertex(("n", s["end"]), node_pos[s["end"]])
                elif stations[sv] is not None:
                    v = vertex(stations[sv], point_at(line, cum, sv))
                else:
                    v = vertex(("s", s["id"], k), point_at(line, cum, sv))
                ch.append((sv, v))
            ss[-1] = L
            chains[s["id"]] = ch
        # (M18: directed, a cm the ground may rise from one vertex to the next: the road's total,
        # grade line plus z, within the class's grade, or the z profile's own where it climbs
        # more; `rev` the same edges the other way, for the lower envelope)
        adj: list[list[tuple[int, int]]] = [[] for _ in pos]
        rev: list[list[tuple[int, int]]] = [[] for _ in pos]
        for s in segments:
            g = MAX_GRADE.get(s["road_class"], 0.12)
            if _ramp(s):
                g = MAX_GRADE["highway"]
            zp = _zp(s.get("z_profile") or [])
            ch = chains[s["id"]]
            r0, r1 = _level_runs(s, ch[-1][0], level)
            lg = LEVEL_GRADE if s["road_class"] in PRIMARY or _ramp(s) else 0.0
            for (s0, a), (s1, b) in zip(ch, ch[1:]):
                ds = s1 - s0
                dz = (z_on(zp, s1) - z_on(zp, s0)) if zp else 0.0
                gt = max(g * ds, abs(dz))
                ab = int(math.floor(max(0.0, gt - dz) * 100.0))
                ba = int(math.floor(max(0.0, gt + dz) * 100.0))
                if s1 <= r0 or s0 >= r1:
                    # inside a junction and LEVEL_OUT_M past it: level (M18: a primary road at
                    # most LEVEL_GRADE)
                    lv = int(math.floor(max(0.0, lg * ds - abs(dz)) * 100.0))
                    ab, ba = min(ab, lv), min(ba, lv)
                adj[a].append((b, ab))
                adj[b].append((a, ba))
                rev[b].append((a, ab))
                rev[a].append((b, ba))
        tgt = [int(round(nat.at(x, y) * 100.0)) for x, y in pos]
        for sid, prof in sorted(held.items()):
            for sv, v in chains[sid]:
                tgt[v] = int(round(z_on(prof, sv) * 100.0))
        frozen = frozenset(v for sid in held for _, v in chains[sid])
        hi = _lipschitz(len(pos), adj, tgt, frozen)
        lo = _lipschitz(len(pos), rev, [-v for v in tgt], frozen)
        if frozen:
            # the held vertices bound the rest both ways (a held vertex takes no bound from its
            # neighbors, so without this the envelopes would break the grade beside it)
            big = 1 << 60
            up = _lipschitz(len(pos), adj,
                            [t if v in frozen else big for v, t in enumerate(tgt)])
            dn = _lipschitz(len(pos), rev,
                            [-t if v in frozen else big for v, t in enumerate(tgt)])
            hi = [max(h, -d) for h, d in zip(hi, dn)]
            lo = [max(lw, -u) for lw, u in zip(lo, up)]
        e = [(h - lw) // 2 for h, lw in zip(hi, lo)]
        elev = [v / 100.0 for v in e]
        return elev, vid, chains

    # (M18: a primary road's run only where the grade lines without them stay near the
    # natural ground at its junction: there the run's flat costs no cut or fill the limits
    # feel, where the road is high over a valley or deep in a hill they would)
    pkeys = {k for k in level if seg_of[k[0]]["road_class"] in PRIMARY or
             _ramp(seg_of[k[0]])}
    if pkeys:
        elev, vid, chains = solve({k: v for k, v in level.items() if k not in pkeys})
        for k in sorted(pkeys):
            x, y = npos[k[1]]
            if abs(elev[vid[("n", k[1])]] - nat.at(x, y)) > LEVEL_DEV_MAX:
                del level[k]
    elev, vid, chains = solve(level)
    ground = {sid: (list(held[sid]) if sid in held else [(sv, elev[v]) for sv, v in ch])
              for sid, ch in chains.items()}
    node_ground = {k[1]: elev[v] for k, v in vid.items() if k[0] == "n"}
    fin, walls, bores, viaducts, st = finish(spec, segments, ground, nat, water)
    st["graph_vertices"] = len(elev)
    st["crossings"] = sum(len(v) for v in cross.values()) // 2
    return Graded(ground, node_ground, fin, walls, bores, viaducts, st)


def _ramp(s: dict) -> bool:
    return bool(s["attrs"].get("ramp")) or s.get("type", "").endswith(".ramp")


def _level_runs(s: dict, L: float, level: dict) -> tuple[float, float]:
    """(end of the level run at the start node, start of the one at the end node) along a
    segment of length L: stations on the 0.01 m grid, 0 and L where its node is no junction."""
    a = level.get((s["id"], s["start"]), 0.0)
    b = level.get((s["id"], s["end"]), 0.0)
    return round(min(a, 0.45 * L), 2), round(L - min(b, 0.45 * L), 2)


BLEND_M = 6.0           # the ground beside a road meets the natural ground over this run
CORRIDOR_PAD_M = 1.5    # the ground is levelled this far past a road's full width
PRIMARY = ("highway", "avenue")


def _bore_runs(s, prof, nat: Field, sign: int = 1, depth: float = BORE_MIN_M,
               length: float = BORE_LEN_M, water=None) -> list[tuple[float, float]]:
    """Stretches of a primary road at least `depth` under the natural ground (sign 1: bored
    tunnels) or over it (sign -1: terrain viaducts) for at least `length` (at grade, not on a
    bridge or in an M9 tunnel; a viaduct not over the water)."""
    if s["road_class"] not in PRIMARY or s.get("tunnel") or (sign > 0 and s.get("bridge")):
        return []
    zp = _zp(s.get("z_profile") or [])
    line = [tuple(p) for p in s["centerline"]]
    cum = _cum(line)
    runs, cur = [], None
    for sv, g in prof:
        x, y = point_at(line, cum, sv)
        deep = sign * (nat.at(x, y) - g) >= depth and abs(z_on(zp, sv)) < 0.5 and \
            (water is None or not water.contains(Point(x, y)))
        if deep and cur is None:
            cur = [sv, sv]
        elif deep:
            cur[1] = sv
        elif cur is not None:
            runs.append(tuple(cur))
            cur = None
    if cur is not None:
        runs.append(tuple(cur))
    return [(a, b) for a, b in runs if b - a >= length]


def finish(spec, segments, ground, nat: Field, water=None):
    """The finished ground: each road corridor (its full width) on its grade line, the
    ground beside it blended to the natural ground over BLEND_M where the step is small,
    else a retaining wall at the corridor's edge; bored stretches left under the hill."""
    import shapely

    F = nat.arr.copy()
    X, Y = nat.grid()
    bestK = np.full(F.shape, np.inf)
    bestG = np.zeros(F.shape)
    bores = []
    viaducts = []
    pieces = []
    for s in segments:
        prof = ground[s["id"]]
        runs = _bore_runs(s, prof, nat)
        for a, b in runs:
            bores.append({"segment": s["id"], "s0": a, "s1": b})
        vruns = _bore_runs(s, prof, nat, -1, VIADUCT_MIN_M, VIADUCT_LEN_M, water)
        for a, b in vruns:
            viaducts.append({"segment": s["id"], "s0": a, "s1": b})
        runs = runs + vruns
        line = [tuple(p) for p in s["centerline"]]
        cum = _cum(line)
        hw = s["width_m"] / 2.0
        for (s0, g0), (s1, g1) in zip(prof, prof[1:]):
            if any(a - 1e-6 <= (s0 + s1) / 2 <= b + 1e-6 for a, b in runs):
                continue
            p0, p1 = point_at(line, cum, s0), point_at(line, cum, s1)
            pieces.append((s["id"], s0, s1, p0, p1, g0, g1, hw))
    if water is not None and pieces:
        mids = shapely.points(np.array([((p[3][0] + p[4][0]) / 2, (p[3][1] + p[4][1]) / 2)
                                        for p in pieces]))
        wet = shapely.contains(water, mids).tolist()
        pieces = [p for p, w in zip(pieces, wet) if not w]
    for sid, s0, s1, p0, p1, g0, g1, hw in pieces:
        r = hw + CORRIDOR_PAD_M + BLEND_M + nat.cell
        js, iss = _window(nat, min(p0[0], p1[0]) - r, min(p0[1], p1[1]) - r,
                          max(p0[0], p1[0]) + r, max(p0[1], p1[1]) + r)
        if js.start >= js.stop or iss.start >= iss.stop:
            continue
        d, t = seg_dist(X[js, iss], Y[js, iss], p0[0], p0[1], p1[0], p1[1])
        k = d - hw - CORRIDOR_PAD_M
        sub = bestK[js, iss]
        better = k < sub
        bestK[js, iss] = np.where(better, k, sub)
        bestG[js, iss] = np.where(better, g0 + (g1 - g0) * t, bestG[js, iss])
    H = nat.arr
    inside_ = bestK <= 0.0
    near = (bestK > 0.0) & (bestK < BLEND_M) & (np.abs(bestG - H) <= WALL_MIN_M)
    w = np.where(near, bestK / BLEND_M, 0.0)
    F = np.where(inside_, bestG, np.where(near, bestG + (H - bestG) * w, H))
    fin = Field(nat.x0, nat.y0, nat.cell, np.round(F, 2))
    walls = _walls(segments, ground, nat, bestK, fin, bores, water)
    cut = fill = 0.0
    for s in segments:
        line = [tuple(p) for p in s["centerline"]]
        cum = _cum(line)
        for sv, g in ground[s["id"]]:
            x, y = point_at(line, cum, sv)
            dd = g - nat.at(x, y)
            fill, cut = max(fill, dd), max(cut, -dd)
    st = {"max_cut_m": q(cut), "max_fill_m": q(fill), "walls": len(walls),
          "wall_km": q(sum(w["length_m"] for w in walls) / 1000.0), "bores": len(bores)}
    st["viaducts"] = len(viaducts)
    return fin, walls, bores, viaducts, st


def _walls(segments, ground, nat: Field, bestK, fin: Field, bores, water=None) -> list[dict]:
    """Retaining walls traced on the finished ground: wherever grading (not the natural
    ground) steps more than WALL_MIN_M between two grid points, a wall stands between them;
    the steps are chained into walls (neighbors within a cell), each with the road nearest
    it, cut where the road side is the lower one."""
    import shapely

    F, H = fin.arr, nat.arr
    X, Y = fin.grid()
    lim = fin.cell / EMBANK_SLOPE
    pts = {}
    for axis in (0, 1):
        dF = np.diff(F, axis=axis)
        dH = np.diff(H, axis=axis)
        mask = (np.abs(dF) > WALL_MIN_M) & (np.abs(dH) <= lim)
        js, iss = np.nonzero(mask)
        for j, i in zip(js.tolist(), iss.tolist()):
            j2, i2 = (j + 1, i) if axis == 0 else (j, i + 1)
            x = q((X[j, i] + X[j2, i2]) / 2)
            y = q((Y[j, i] + Y[j2, i2]) / 2)
            lo_in = (bestK[j, i] <= 0.0) if F[j, i] < F[j2, i2] else (bestK[j2, i2] <= 0.0)
            pts[(x, y)] = (abs(float(dF[j, i])), bool(lo_in))
    if water is not None and pts:
        keys = sorted(pts)
        wet = shapely.contains_xy(water, np.array([k[0] for k in keys]),
                                  np.array([k[1] for k in keys])).tolist()
        for k, w in zip(keys, wet):
            if w:
                del pts[k]
    # chain neighbors (within a cell) into polylines
    cell = fin.cell
    grid: dict = {}
    for k in pts:
        grid.setdefault((int(math.floor(k[0] / cell)), int(math.floor(k[1] / cell))),
                        []).append(k)

    def nbrs(k):
        gi, gj = int(math.floor(k[0] / cell)), int(math.floor(k[1] / cell))
        out = []
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for o in grid.get((gi + di, gj + dj), []):
                    if o != k and math.hypot(o[0] - k[0], o[1] - k[1]) <= cell * 1.01:
                        out.append(o)
        return sorted(out)

    seen: set = set()
    chains = []
    for start in sorted(pts):
        if start in seen:
            continue
        # walk to an end of this component first, then chain greedily
        comp, stack = [], [start]
        seen_c = {start}
        while stack:
            k = stack.pop()
            comp.append(k)
            for o in nbrs(k):
                if o not in seen_c and o not in seen:
                    seen_c.add(o)
                    stack.append(o)
        left = set(comp)
        while left:
            ends = sorted(k for k in left if sum(1 for o in nbrs(k) if o in left) <= 1)
            cur = ends[0] if ends else min(left)
            chain = [cur]
            left.discard(cur)
            while True:
                nxt = [o for o in nbrs(cur) if o in left]
                if not nxt:
                    break
                cur = min(nxt, key=lambda o: (math.hypot(o[0] - cur[0], o[1] - cur[1]), o))
                chain.append(cur)
                left.discard(cur)
            chains.append(chain)
        seen |= set(comp)
    lines = [shapely.LineString([tuple(p) for p in s["centerline"]]) for s in segments]
    tree = shapely.STRtree(lines)
    walls = []
    for chain in chains:
        if len(chain) == 1:
            x, y = chain[0]
            chain = [(q(x - 1.0), y), (q(x + 1.0), y)]
            hs = [pts[(x, y)][0]] * 2
            cuts = [pts[(x, y)][1]]
        else:
            hs = [pts[k][0] for k in chain]
            cuts = [pts[k][1] for k in chain]
        mid = chain[len(chain) // 2]
        pm = shapely.Point(mid)
        near = tree.query(pm, predicate="dwithin", distance=40.0).tolist()
        sid = min(((round(lines[i].distance(pm), 3), segments[i]["id"]) for i in near),
                  default=(0.0, None))[1]
        L = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(chain, chain[1:]))
        walls.append({"segment": sid, "side": None,
                      "line": [[x, y, q(h)] for (x, y), h in zip(chain, hs)],
                      "kind": "cut" if sum(cuts) * 2 >= len(cuts) else "fill",
                      "height_m": q(max(hs)), "length_m": q(L)})
    return walls


def steep_lots(loc, fin: Field) -> int:
    """Lots whose ground falls more than STEEP_LOT_M become hillside greens (open space);
    a merged group that loses a lot is built lot by lot."""
    keep, gone = [], set()
    greens = []
    for lot in loc.lots:
        if lot.get("attrs", {}).get("pinned"):
            keep.append(lot)
            continue
        vals = footprint_ground(fin, G.from_model_poly(lot["polygon"]))
        if vals and max(vals) - min(vals) > STEEP_LOT_M:
            gone.add(lot["id"])
            # (named `<district>.os.slope.<cell>` by the M10 pass)
            greens.append({"id": f"{lot['district_id']}.os.slope{len(greens) + 1:04d}",
                           "type": "open_space.green.slope",
                           "kind": "green", "polygon": lot["polygon"],
                           "district_id": lot["district_id"],
                           "attrs": {"slope": True, "fall_m": q(max(vals) - min(vals))}})
        else:
            keep.append(lot)
    groups = {lot.get("merged_group_id") for lot in loc.lots if lot["id"] in gone}
    for lot in keep:
        if lot.get("merged_group_id") in groups and lot.get("merged_group_id"):
            lot["merged_group_id"] = None
    loc.lots = keep
    loc.open_spaces = list(loc.open_spaces) + greens
    return len(gone)


_GROUND: dict = {}


def ground_of(m) -> Field | None:
    """The finished ground of a model (cached), None on a flat city."""
    t = m.terrain
    if t is None:
        return None
    hit = _GROUND.get(id(t))
    if hit is None or hit[0] is not t:
        _GROUND.clear()
        hit = (t, Field.from_rows(t, t.ground or t.natural))
        _GROUND[id(t)] = hit
    return hit[1]


def on_ground(m, pts) -> list[float]:
    """The finished ground under points (0 everywhere on a flat city)."""
    gf = ground_of(m)
    return [0.0] * len(pts) if gf is None else [gf.at(p[0], p[1]) for p in pts]


def apply_grade(loc, gr: Graded) -> None:
    """Grade lines onto the M2 roads (dict rows)."""
    for s in loc.segments:
        s["ground"] = [{"s": q(sv), "z": q(z)} for sv, z in gr.ground[s["id"]]]
    for n in loc.nodes:
        if n["id"] in gr.node_ground:
            n["ground_m"] = q(gr.node_ground[n["id"]])


def wall_rows(walls) -> list[dict]:
    """Retaining walls as structures (named `<segment>.wall.<cell>`, or `wall.<cell>`, by
    the M10 pass)."""
    return [{"id": (f"{w['segment']}.wall{k + 1:04d}" if w["segment"] else f"wall{k + 1:04d}"),
             "type": "structure.retaining_wall",
             "kind": "retaining_wall", "line": w["line"], "z0_m": 0.0, "z1_m": w["height_m"],
             "supports": [w["segment"]] if w["segment"] else [],
             "attrs": {"segment": w["segment"], "cut": w["kind"] == "cut",
                       "length_m": w["length_m"],
                       "note": "line z: wall height over the lower side"}}
            for k, w in enumerate(walls)]


def bore_rows(bores, segments, nat: Field, dnames: dict | None = None) -> list[dict]:
    """Bored tunnels as M9 tunnel rows (kind `bored`): line z over the grade line, portals
    where the cut reaches BORE_MIN_M."""
    from . import dmath as M

    by = {s["id"]: s for s in segments}
    out = []
    used: dict[str, int] = {}
    for k, b in enumerate(bores):
        s = by[b["segment"]]
        line = [tuple(p) for p in s["centerline"]]
        cum = _cum(line)
        st = [(p["s"], p["z"]) for p in s["ground"]] if s.get("ground") else []
        zp = _zp(s.get("z_profile") or [])
        n = max(2, int(math.ceil((b["s1"] - b["s0"]) / STEP_M)) + 1)
        pts, cover = [], math.inf
        for i in range(n):
            sv = b["s0"] + (b["s1"] - b["s0"]) * i / (n - 1)
            x, y = point_at(line, cum, sv)
            pts.append([q(x), q(y), q(z_on(zp, sv))])
            g = z_on(st, sv)
            cover = min(cover, nat.at(x, y) - g - BORE_CLEAR_M - BORE_ROOF_M)
        portals = []
        for a, c in ((pts[0], pts[1]), (pts[-1], pts[-2])):
            hd = M.degrees(M.atan2(c[1] - a[1], c[0] - a[0]))
            portals.append({"position": list(a), "heading_deg": q(hd), "open_m": 0.0})
        where = s.get("name") or next((dnames[d] for d in s.get("district_ids") or []
                                       if dnames and d in dnames), None)
        name = f"{where} Tunnel" if where else None
        if name is not None:
            used[name] = used.get(name, 0) + 1
            if used[name] > 1:
                name = f"{name} {used[name]}"
        out.append({"id": f"bore{k + 1:02d}", "type": "tunnel.bored", "kind": "bored",
                    "name": name, "segment_ids": [s["id"]], "crosses": [],
                    "line": pts, "width_m": q(s["width_m"] + 2.0), "clear_m": BORE_CLEAR_M,
                    "roof_m": BORE_ROOF_M, "floor_m": 1.0, "portals": portals,
                    "attrs": {"s0": q(b["s0"]), "s1": q(b["s1"]),
                              "length_m": q(b["s1"] - b["s0"]), "min_cover_m": q(cover)}})
    return out


def footprint_ground(fin: Field, poly) -> list[float]:
    """The finished ground at a footprint's corners and at the grid points inside it."""
    import shapely

    vals = [fin.at(x, y) for r in _rings(poly) for x, y in r[:-1]]
    bx0, by0, bx1, by1 = poly.bounds
    js, iss = _window(fin, bx0, by0, bx1, by1)
    if js.start < js.stop and iss.start < iss.stop:
        X, Y = fin.grid()
        Xs, Ys = X[js, iss], Y[js, iss]
        inn = shapely.contains_xy(poly, Xs, Ys)
        vals += [float(v) for v in fin.arr[js, iss][inn]]
    return vals


def seat(model, fin: Field) -> dict:
    """Each building's base at its main entrance (buildings linked by skybridges on a common
    floor grid: each takes the floor of the first one nearest its own entrance ground), its
    plinth at the lowest ground under its footprint."""
    entr = {}
    for b in model.buildings:
        if b.footprint is None:
            continue
        e = next((e for e in b.entrances if e.kind == "main"),
                 b.entrances[0] if b.entrances else None)
        if e is not None:
            entr[b.id] = fin.at(*e.position)
        else:
            c = G.from_model_poly(b.footprint).centroid
            entr[b.id] = fin.at(c.x, c.y)
    parent: dict[str, str] = {}

    def root(a):
        while parent.get(a, a) != a:
            a = parent[a]
        return a

    for sb in model.skybridges:
        a, b = sorted(sb.building_ids)
        ra, rb = root(a), root(b)
        if ra != rb:
            lo, hi = sorted((ra, rb))
            parent[hi] = lo
    fh = {b.id: b.floor_height_m for b in model.buildings}
    base: dict[str, float] = {}
    for bid in sorted(entr):
        r = root(bid)
        if r == bid or r not in entr:
            base[bid] = q(entr[bid])
    for bid in sorted(entr):
        if bid in base:
            continue
        r = root(bid)
        b0 = base[r]
        base[bid] = q(b0 + round((entr[bid] - b0) / fh[r]) * fh[r])
    rows = []
    for b in model.buildings:
        if b.footprint is None or b.id not in base:
            rows.append(b)
            continue
        vals = footprint_ground(fin, G.from_model_poly(b.footprint))
        plinth = q(min(vals + [base[b.id]]))
        rows.append(b.model_copy(update={"base_m": base[b.id], "plinth_m": plinth}))
    bases = {b.id: b.base_m for b in rows}
    sky = [s.model_copy(update={"base_m": bases.get(s.building_ids[0])})
           for s in model.skybridges]
    return {"buildings": rows, "skybridges": sky}


PARK_MAX = 0.10          # no parked car on a street steeper than this
SEAT_MAX = 0.12          # no bench, stall, kiosk or vending machine on ground this steep
TREE_MAX = 1.00          # no tree or shrub rooted on ground this steep (a cliff face)
STEEP_PROPS = ("bench", "food_stall", "kiosk", "vending_machine", "planter")
GROUND_PLANTS = ("street_tree", "park_tree", "conifer", "palm", "median_tree", "shrub",
                 "overgrowth")


def dressing(m) -> tuple[dict, dict]:
    """Props and plants that suit the ground: parked cars off streets steeper than PARK_MAX
    (the street's own grade line), seats and stalls off steep natural ground, no tree on a
    cliff face (natural ground over TREE_MAX), nothing at the ground under a terrain
    viaduct (M13)."""
    import shapely

    fin = ground_of(m)
    nat = Field.from_rows(m.terrain, m.terrain.natural)
    st = {"parked_off_steep": 0, "seats_off_steep": 0, "trees_off_cliffs": 0,
          "under_viaducts": 0}
    segs = {s.id: s for s in m.road_segments}

    def road_grade(sid, x, y) -> float:
        """The grade of a road's grade line where a point stands beside it."""
        s = segs.get(sid)
        if s is None or not s.ground:
            return fin.slope(x, y)
        from .elevated import _project

        line = [tuple(p) for p in s.centerline]
        cum = _cum(line)
        at = _project(line, cum, (x, y))[0]
        st_ = [(p.s, p.z) for p in s.ground]
        a_, b_ = max(at - 5.0, 0.0), min(at + 5.0, cum[-1])
        return abs(z_on(st_, b_) - z_on(st_, a_)) / max(b_ - a_, 1.0)
    decks = [shapely.LineString([p[:2] for p in s.line]).buffer(s.attrs["width_m"] / 2 + 2.0)
             for s in m.structures if s.attrs.get("terrain_viaduct") and len(s.line) >= 2]
    under = G.union(decks) if decks else None

    def below(x, y, z):
        return under is not None and abs(z) < 0.5 and under.contains(Point(x, y))

    props = []
    for p in m.props:
        kind = p.type.split(".", 1)[1] if "." in p.type else p.type
        x, y, z = p.position
        if below(x, y, z):
            st["under_viaducts"] += 1
            continue
        if abs(z) < 0.5 and kind == "parked_vehicle" and \
                road_grade(p.attrs.get("segment"), x, y) > PARK_MAX:
            st["parked_off_steep"] += 1
            continue
        if abs(z) < 0.5 and kind in STEEP_PROPS and nat.slope(x, y) > SEAT_MAX:
            st["seats_off_steep"] += 1
            continue
        props.append(p)
    plants = []
    for p in m.plants:
        kind = p.type.split(".", 1)[1] if "." in p.type else p.type
        x, y, z = p.position
        if below(x, y, z):
            st["under_viaducts"] += 1
            continue
        if abs(z) < 0.5 and kind in GROUND_PLANTS and nat.slope(x, y) > TREE_MAX:
            st["trees_off_cliffs"] += 1
            continue
        plants.append(p)
    return {"props": props, "plants": plants}, st


def viaduct_rows(viaducts, segments, nat: Field) -> list[dict]:
    """Terrain viaducts: a deck under the road (line z: deck top over the natural ground) and
    columns every COLUMN_STEP_M where the deck stands at least COLUMN_MIN_M high."""
    by = {s["id"]: s for s in segments}
    out = []
    for k, v in enumerate(viaducts):
        s = by[v["segment"]]
        line = [tuple(p) for p in s["centerline"]]
        cum = _cum(line)
        st = [(p["s"], p["z"]) for p in s["ground"]]
        n = max(2, int(math.ceil((v["s1"] - v["s0"]) / STEP_M)) + 1)
        pts = []
        for i in range(n):
            sv = v["s0"] + (v["s1"] - v["s0"]) * i / (n - 1)
            x, y = point_at(line, cum, sv)
            pts.append([q(x), q(y), q(z_on(st, sv) - nat.at(x, y))])
        did = f"{s['id']}.viaduct{k + 1:02d}"     # (M10: `<segment>.viaduct.<cell>`)
        out.append({"id": did, "type": "structure.terrain_viaduct", "kind": "deck",
                    "line": pts, "z0_m": q(min(p[2] for p in pts) - 1.2),
                    "z1_m": q(max(p[2] for p in pts)), "supports": [s["id"]],
                    "attrs": {"terrain_viaduct": True, "segment": s["id"],
                              "s0": q(v["s0"]), "s1": q(v["s1"]),
                              "width_m": q(s["width_m"]), "deck_m": 1.2}})
        nc = int((v["s1"] - v["s0"]) // COLUMN_STEP_M)
        for i in range(nc + 1):
            sv = v["s0"] + (v["s1"] - v["s0"]) * (i + 0.5) / (nc + 1)
            x, y = point_at(line, cum, sv)
            h = z_on(st, sv) - nat.at(x, y) - 1.2
            if h < COLUMN_MIN_M:
                continue
            foot = G.qpoly(Point(x, y).buffer(1.25, cap_style="square"))
            out.append({"id": f"{s['id']}.tvcol{k + 1:02d}{i + 1:03d}",
                        "type": "structure.terrain_column",
                        "kind": "column", "footprint": G.to_model_poly(foot), "z0_m": 0.0,
                        "z1_m": q(h), "supports": [did],
                        "attrs": {"terrain_viaduct": True, "segment": s["id"]}})
    return out
