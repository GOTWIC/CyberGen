"""AT5: the weather (scope 6.4): where the rain cannot reach, how wet each surface gets, where
water stands, where the covers drip, the wind, and the weather states the runtime moves
between.

- **The rain shadow** (`Weather.covers`): everything that hangs over the ground within
  `presets.WIND["cover_max_m"]` of it shelters what is under it: M14's deck slabs, M3's
  masses whose floor is off the ground (an overhang, a tower over its podium's edge, a
  cantilever), skybridges, M6's awnings and bus shelters, the canopies, the transit decks
  and cap beams, the raised roads (as the sight raster takes them: `sight.road_decks`), the
  road tunnels' lids. The rain falls leaning downwind (`WIND`: its heading and lean), so a
  cover's shadow on the ground is its footprint moved downwind by its height times the lean
  (at most `shift_max_m`): the lee of an awning is dry, its windward edge wet.
- **The masks** (`masks/<tile>.png`, scope 4.2: per 256 m tile, `MASK["texel_m"]` texels,
  row 0 the north edge, RGBA): red the cover, the lowest underside over the texel of what
  shelters it (absolute, in the plan's `cover` steps over its datum: a surface under it is
  dry, one over it, a deck's top over the street, wet); green the puddles; blue the drip
  band under the low covers' edges; alpha the surface's gloss when wet (the pavement map's
  faces, M16's ground cover, roofs, the raised decks, the water none).
- **Puddles** (`Weather.puddles`): water stands in the low spots of the streets: a value
  noise on the plan for the worn spots, the gutter along the curb (the road's crown sheds
  the rain to it), a road's sags (the low points of its grade line: M13's ground plus its
  own profile), round AG7's drains (clogged in gritty districts); fewer in clean districts,
  more in gritty ones (decision 12.5); never under a cover, on a roof, a raised deck, a curb
  or the water.
- **Drips** (`drips/<tile>.json`): a line under each low cover's edge (awnings, deck slabs,
  raised roads, canopies, bus shelters) in pieces, its edge's height and the ground under it,
  for the runtime's drip streaks.
- **States** (`Weather.settings`): clear, drizzle, rain, fog and smog, each with its rain,
  streaks, puddles, wetness, fog (the look's, as AT4's air makes it), clouds, fog volumes'
  gain and wind; the rain's age (how fast the streets wet and dry and the puddles fill and
  drain) and the transition's time; the wind's heading.
- **The check** (`Weather.check`, scope 8): every low cover's middle sheltered, no puddle
  under a cover, in a building or on the water, every tile's mask, the drips' budget per
  tile.

Deterministic as the rest of the plan: the noise is an integer hash of the world's lattice
(splitmix64), polygons drawn on the texel grid by PIL, coordinates on the millimeter grid,
every file written only when its bytes change.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np

from . import presets as P

MASK_DIR = "masks"
DRIP_DIR = "drips"
PREVIEW = "preview_weather.png"
DETAIL = "preview_weather_detail.png"
CLASSES = ("open", "road", "walk", "curb", "paving", "soil", "lawn", "roof", "deck", "water")
CI = {c: k for k, c in enumerate(CLASSES)}
PAD = 8                    # texels drawn past each tile's edge (dilations see the neighbors)
DRIP_KINDS = ("awning", "deck", "road", "canopy", "shelter")


# --- small helpers ------------------------------------------------------------------------------

def _u64(a) -> np.ndarray:
    return np.asarray(a, dtype=np.int64).astype(np.uint64)


def hash01(ix, iy, salt: int) -> np.ndarray:
    """A deterministic draw in [0, 1) per integer lattice point (splitmix64 of the point)."""
    with np.errstate(over="ignore"):
        h = _u64(ix) * np.uint64(0x9E3779B97F4A7C15)
        h ^= _u64(iy) * np.uint64(0xC2B2AE3D27D4EB4F)
        h ^= np.uint64(salt & 0xFFFFFFFFFFFFFFFF)
        h ^= h >> np.uint64(33)
        h *= np.uint64(0xFF51AFD7ED558CCD)
        h ^= h >> np.uint64(33)
        h *= np.uint64(0xC4CEB9FE1A85EC53)
        h ^= h >> np.uint64(33)
    return (h >> np.uint64(11)).astype(np.float64) / float(2 ** 53)


def value_noise(x: np.ndarray, y: np.ndarray, cell: float, salt: int) -> np.ndarray:
    """A smooth value noise in [0, 1] on the plan (lattice `cell` m apart)."""
    fx, fy = x / cell, y / cell
    ix, iy = np.floor(fx), np.floor(fy)
    tx, ty = fx - ix, fy - iy
    tx = tx * tx * (3.0 - 2.0 * tx)
    ty = ty * ty * (3.0 - 2.0 * ty)
    ix = ix.astype(np.int64)
    iy = iy.astype(np.int64)
    a = hash01(ix, iy, salt)
    b = hash01(ix + 1, iy, salt)
    c = hash01(ix, iy + 1, salt)
    d = hash01(ix + 1, iy + 1, salt)
    return (a + (b - a) * tx) * (1.0 - ty) + (c + (d - c) * tx) * ty


def _dilate(m: np.ndarray, k: int) -> np.ndarray:
    """A boolean mask grown by k texels (the 8 neighbors each step)."""
    out = m.copy()
    for _ in range(k):
        g = out.copy()
        g[1:, :] |= out[:-1, :]
        g[:-1, :] |= out[1:, :]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        g[1:, 1:] |= out[:-1, :-1]
        g[:-1, :-1] |= out[1:, 1:]
        g[1:, :-1] |= out[:-1, 1:]
        g[:-1, 1:] |= out[1:, :-1]
        out = g
    return out


def _ring(r) -> list[tuple[float, float]]:
    return [(float(p[0]), float(p[1])) for p in r]


def _bbox(rings) -> tuple[float, float, float, float]:
    xs = [p[0] for p in rings[0]]
    ys = [p[1] for p in rings[0]]
    return min(xs), min(ys), max(xs), max(ys)


class Grid:
    """A tile's texel grid with `PAD` texels round it: texel (j, i) is row j from the north
    edge, column i from the west; its middle at (x0 + (i + 0.5) t, y1 - (j + 0.5) t)."""

    def __init__(self, bounds, t: float, pad: int = PAD):
        x0, y0, x1, y1 = bounds
        self.t, self.pad = t, pad
        self.x0, self.y1 = x0 - pad * t, y1 + pad * t
        self.n = int(round((x1 - x0) / t)) + 2 * pad
        k = np.arange(self.n)
        self.xs = self.x0 + (k + 0.5) * t
        self.ys = self.y1 - (k + 0.5) * t

    def window(self, box):
        """The texel window over a box (x0, y0, x1, y1): (j0, j1, i0, i1) or None."""
        bx0, by0, bx1, by1 = box
        i0 = max(0, int(math.floor((bx0 - self.x0) / self.t)) - 1)
        i1 = min(self.n, int(math.ceil((bx1 - self.x0) / self.t)) + 1)
        j0 = max(0, int(math.floor((self.y1 - by1) / self.t)) - 1)
        j1 = min(self.n, int(math.ceil((self.y1 - by0) / self.t)) + 1)
        if i1 <= i0 or j1 <= j0:
            return None
        return j0, j1, i0, i1

    def mask(self, rings, dx: float = 0.0, dy: float = 0.0):
        """The texels whose middle lies in the polygon (exterior, holes) moved by (dx, dy):
        (j0, i0, bool mask) or None."""
        from PIL import Image, ImageDraw
        ext = rings[0]
        if len(ext) < 3:
            return None
        xs = [p[0] + dx for p in ext]
        ys = [p[1] + dy for p in ext]
        w = self.window((min(xs), min(ys), max(xs), max(ys)))
        if w is None:
            return None
        j0, j1, i0, i1 = w
        img = Image.new("L", (i1 - i0, j1 - j0), 0)
        dr = ImageDraw.Draw(img)
        t = self.t
        for k, r in enumerate(rings):
            if len(r) < 3:
                continue
            dr.polygon([((p[0] + dx - self.x0) / t - i0 - 0.5, (self.y1 - p[1] - dy) / t - j0 - 0.5)
                        for p in r], fill=1 if k == 0 else 0)
        m = np.asarray(img, dtype=bool)
        return (j0, i0, m) if m.any() else None

    def crop(self, a: np.ndarray) -> np.ndarray:
        p = self.pad
        return a[p:self.n - p, p:self.n - p]


# --- the weather --------------------------------------------------------------------------------

class Weather:
    def __init__(self, plan, filled: dict):
        from . import plan as PL
        self.PL = PL
        self.p = plan
        self.c = plan.c
        self.filled = filled
        self.t = float(P.MASK["texel_m"])
        w = P.WIND
        self.heading = float(filled.get("wind_deg") if filled.get("wind_deg") is not None
                             else w["heading_deg"])
        a = math.radians(self.heading)
        self.wind = (math.cos(a), math.sin(a))
        self.lean = float(w["lean"])
        self.cover_list: list[dict] = []
        self.drip_list: list[dict] = []
        self.report: dict = {"covers": {}, "skipped": {}}
        m = self.c.m
        if m.get("bounds"):
            self.bounds = [float(v) for v in m["bounds"]]
        else:
            self.bounds = [-1000.0, -1000.0, 1000.0, 1000.0]
        self.masks: list[dict] = []
        self.drip_tiles: list[dict] = []
        self.stats: dict = {}

    # -- the ground and the datum --

    def ground_many(self, xs, ys) -> np.ndarray:
        return self.c.ground_many(xs, ys)

    def datum(self) -> tuple[float, float]:
        """The cover channel's datum and step: `below_m` under the city's lowest ground,
        `MASK["step_m"]` steps (1 m where the covers would not fit in 255)."""
        t = self.c.m.get("terrain")
        lo, hi = 0.0, 0.0
        if t and self.c._grid is not None:
            a = self.c._grid[3]
            lo, hi = float(np.min(a)), float(np.max(a))
        z0 = math.floor(lo) - float(P.MASK["below_m"])
        top = hi + float(P.WIND["cover_max_m"]) + 2.0
        step = float(P.MASK["step_m"])
        if (top - z0) / step > 254.0:
            step = max(1.0, math.ceil((top - z0) / 254.0))
        return z0, step

    # -- what shelters the ground --

    def _add(self, *, cid: str, kind: str, rings, under: float, ground: float,
             drips=(), shelter: bool = True) -> None:
        h = under - ground
        if h < 0.8 and kind != "tunnel":
            return
        if h > float(P.WIND["cover_max_m"]):
            self.report["skipped"][f"{kind}: higher than the rain shelters"] = \
                self.report["skipped"].get(f"{kind}: higher than the rain shelters", 0) + 1
            return
        rings = [_ring(r) for r in rings if len(r) >= 3]
        if not rings:
            return
        s = min(float(P.WIND["shift_max_m"]), max(0.0, h) * self.lean)
        dx, dy = self.wind[0] * s, self.wind[1] * s
        bb = _bbox(rings)
        self.cover_list.append({"id": cid, "kind": kind, "rings": rings, "under": under,
                                "ground": ground, "h": h, "dx": dx, "dy": dy,
                                "box": (min(bb[0], bb[0] + dx), min(bb[1], bb[1] + dy),
                                        max(bb[2], bb[2] + dx), max(bb[3], bb[3] + dy)),
                                "drips": list(drips) if h <= float(P.DRIPS["max_m"]) else [],
                                "shelter": shelter})
        r = self.cover_list[-1]
        r["bands"] = []
        if r["drips"]:
            cx = sum(p[0] for p in rings[0]) / len(rings[0])
            cy = sum(p[1] for p in rings[0]) / len(rings[0])
            bw = float(P.DRIPS["band_m"])
            for (a, b), _z in r["drips"]:
                L = math.dist(a, b)
                if L < 0.2:
                    continue
                ox, oy = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
                mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
                if ox * (mx - cx) + oy * (my - cy) < 0.0:
                    ox, oy = -ox, -oy
                pa = (a[0] + dx, a[1] + dy)
                pb = (b[0] + dx, b[1] + dy)
                r["bands"].append([pa, pb, (pb[0] + ox * bw, pb[1] + oy * bw),
                                   (pa[0] + ox * bw, pa[1] + oy * bw)])
        self.report["covers"][kind] = self.report["covers"].get(kind, 0) + 1

    def covers(self) -> None:
        """Every cover the rain shadow is made of (module docstring)."""
        from shapely.geometry import LineString, Polygon
        c, m = self.c, self.c.m
        gm = self.ground_many
        # M3's masses whose floor is off the ground: overhangs, towers over their podium's
        # edge, cantilevers (their footprint as drawn; the lowest ground under its corners)
        for b in sorted(m.get("buildings", []), key=lambda b: b["id"]):
            base = c.ground_at_base(b)
            for k, ms in enumerate(b.get("masses") or []):
                z0 = float(ms.get("z0_m", 0.0))
                if z0 < 0.8:
                    continue
                fp = ms.get("footprint") or {}
                ext = fp.get("exterior") or []
                if len(ext) < 3:
                    continue
                g = float(np.min(gm([p[0] for p in ext], [p[1] for p in ext])))
                self._add(cid=f"{b['id']}.m{k}", kind="mass",
                          rings=[ext] + list(fp.get("holes") or []), under=base + z0,
                          ground=g)
        # M14's deck slabs (their light wells open)
        for dk in sorted(m.get("decks", []) or [], key=lambda d: d["id"]):
            poly = dk.get("polygon") or {}
            ext = poly.get("exterior") or []
            if len(ext) < 3:
                continue
            g = c.ground(ext[0][0], ext[0][1])
            under = g + float(dk.get("top_m", 9.0)) - float(dk.get("slab_m", 1.2))
            rings = [ext] + list(poly.get("holes") or [])
            self._add(cid=dk["id"], kind="deck", rings=rings, under=under, ground=g,
                      drips=[(e, under) for r in rings for e in zip(r, r[1:] + r[:1])])
        # skybridges (their underside: the floor less the slab)
        for sb in sorted(m.get("skybridges", []) or [], key=lambda s: s["id"]):
            ln = sb.get("line") or []
            if len(ln) < 2:
                continue
            g = LineString([q[:2] for q in ln]).buffer(float(sb.get("width_m", 4.0)) / 2.0,
                                                        cap_style="flat")
            if g.is_empty or g.geom_type != "Polygon":
                continue
            mid = g.representative_point()
            gz = c.ground(mid.x, mid.y)
            under = gz + float(sb.get("clearance_m", float(sb.get("z_m", 6.0)) - 1.0))
            self._add(cid=sb["id"], kind="skybridge", rings=[list(g.exterior.coords)[:-1]],
                      under=under, ground=gz)
        # M6's awnings (a rectangle at its height, its outer long edge dripping) and bus
        # shelters (their roof)
        occ = c.occluders()
        for pr in sorted(m.get("props", []), key=lambda p: p["id"]):
            typ = pr.get("type") or ""
            if typ not in ("prop.awning", "prop.bus_stop"):
                continue
            x, y, z = (list(pr["position"]) + [0.0])[:3]
            a = math.radians(float(pr.get("yaw_deg", 0.0)))
            ux, uy = math.cos(a), math.sin(a)
            nx, ny = -uy, ux
            sc = pr.get("scale") or [1.0, 1.0, 1.0]
            if typ == "prop.awning":
                L, D, zz, kind = float(sc[0]), float(sc[1]), float(z), "awning"
            else:
                L, D, zz, kind = 4.0 * float(sc[0]), 1.4 * float(sc[1]), 2.5, "shelter"
            gz = c.ground(x, y)
            corners = [(x + ux * L / 2 * su + nx * D / 2 * sv, y + uy * L / 2 * su + ny * D / 2 * sv)
                       for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            edges = []
            if kind == "awning":
                # (its outer edge: the long side away from its wall)
                # (1.5 m past its wall side: inside the building past the occluders' erosion)
                far = 0.5 * D + 1.5
                wall_p = bool(occ.blocked(np.array([x + nx * far]), np.array([y + ny * far]),
                                          np.array([gz + max(1.0, zz - 1.0)]))[0])
                sv = -1 if wall_p else 1
                edges = [((x - ux * L / 2 + nx * D / 2 * sv, y - uy * L / 2 + ny * D / 2 * sv),
                          (x + ux * L / 2 + nx * D / 2 * sv, y + uy * L / 2 + ny * D / 2 * sv))]
            else:
                edges = [(corners[0], corners[1]), (corners[2], corners[3])]
            self._add(cid=pr["id"], kind=kind, rings=[corners], under=gz + zz - 0.05,
                      ground=gz, drips=[(e, gz + zz) for e in edges])
        # the canopies, the transit decks and cap beams (as the model draws them)
        for s in sorted(m.get("structures", []) or [], key=lambda s: s["id"]):
            kind = s.get("kind")
            at = s.get("attrs") or {}
            if kind == "canopy":
                ext = (s.get("footprint") or {}).get("exterior") or []
                if len(ext) < 3:
                    continue
                gz = c.ground(ext[0][0], ext[0][1])
                under = gz + float(s.get("z0_m", 3.0))
                self._add(cid=s["id"], kind="canopy", rings=[ext], under=under, ground=gz,
                          drips=[(e, under) for e in zip(ext, ext[1:] + ext[:1])])
            elif kind in ("deck", "beam", "tube") and not at.get("underground"):
                ext = (s.get("footprint") or {}).get("exterior") or []
                ln = s.get("line") or []
                if len(ext) >= 3:
                    rings = [ext]
                    mx, my = ext[0][0], ext[0][1]
                elif len(ln) >= 2:
                    w = float(at.get("width_m", at.get("deck_m", 6.0)))
                    g = LineString([q[:2] for q in ln]).buffer(w / 2.0, cap_style="flat")
                    if g.is_empty or g.geom_type != "Polygon":
                        continue
                    rings = [list(g.exterior.coords)[:-1]]
                    mid = g.representative_point()
                    mx, my = mid.x, mid.y
                else:
                    continue
                gz = c.ground(mx, my)
                z0 = float(s.get("z0_m", 0.0))
                if kind == "tube":
                    z0 = float(s.get("z0_m", 0.0)) - float(at.get("deck_m", 7.0)) / 2.0
                self._add(cid=s["id"], kind=f"transit_{kind}", rings=rings, under=gz + z0,
                          ground=gz)
        # the raised roads (as the sight raster takes them: 8 m pieces, from the deck's
        # underside), their edges along the road dripping
        from . import sight as SI
        gmf = c.ground_many if c._grid is not None else None
        decks = SI.road_decks(m, gmf)
        self.road_rings = []
        for k, (ring, z0, z1) in enumerate(decks):
            r = [(float(p[0]), float(p[1])) for p in ring[:-1]]
            if len(r) < 3:
                continue
            xs = [p[0] for p in r]
            ys = [p[1] for p in r]
            gz = float(np.min(gm(xs, ys)))
            self.road_rings.append(r)
            # (the long sides: the edges along the road; the piece's short ends are cuts)
            edges = []
            pts = r + r[:1]
            lens = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
            for (a, b), L in zip(zip(pts, pts[1:]), lens):
                if L >= 2.0:
                    edges.append((a, b))
            # (keep the two longest: a piece's two sides; its caps are its width across)
            edges = sorted(edges, key=lambda e: -math.dist(*e))[:2] if len(edges) > 2 else edges
            self._add(cid=f"road.{k:05d}", kind="road", rings=[r], under=z0, ground=gz,
                      drips=[(e, z0 + float(SI.DECK_UNDER_M) - 0.3) for e in edges])
        # the road tunnels' lids over their covered stretch
        for tn in sorted(m.get("tunnels", []) or [], key=lambda t: t["id"]):
            if tn.get("kind") in ("metro",) or len(tn.get("line") or []) < 2:
                continue
            g = LineString([q[:2] for q in tn["line"]]).buffer(
                float(tn.get("width_m", 8.0)) / 2.0, cap_style="flat")
            if g.is_empty or g.geom_type != "Polygon":
                continue
            mid = g.representative_point()
            gz = c.ground(mid.x, mid.y)
            self._add(cid=tn["id"], kind="tunnel", rings=[list(g.exterior.coords)[:-1]],
                      under=gz - 0.3, ground=gz - 1.0)
        self.cover_list.sort(key=lambda r: r["id"])

    # -- what the masks are drawn from --

    def surfaces(self) -> None:
        """The surfaces by class (drawn in this order, later over earlier): the land (else
        water), the open spaces, M16's ground cover, the water bodies, the pavement map's
        faces, the buildings' roofs, the raised roads' decks."""
        m = self.c.m
        out: list[tuple[str, list]] = []
        for land in m.get("land", []) or []:
            for poly in land.get("polygons") or []:
                out.append(("open", [poly.get("exterior") or []] + list(poly.get("holes") or [])))
        for o in sorted(m.get("open_spaces", []) or [], key=lambda o: o["id"]):
            cls = P.OPEN_SPACE_CLASS.get(o.get("kind"))
            poly = o.get("polygon") or {}
            if cls and len(poly.get("exterior") or []) >= 3:
                out.append((cls, [poly["exterior"]] + list(poly.get("holes") or [])))
        for gc in sorted(m.get("ground_cover", []) or [], key=lambda g: g["id"]):
            cls = P.COVER_CLASS.get(gc.get("kind"))
            poly = gc.get("polygon") or {}
            if cls and len(poly.get("exterior") or []) >= 3:
                out.append((cls, [poly["exterior"]] + list(poly.get("holes") or [])))
        for key in ("rivers", "channels", "waterways"):
            for w in sorted(m.get(key, []) or [], key=lambda w: w["id"]):
                poly = w.get("polygon") or {}
                if len(poly.get("exterior") or []) >= 3:
                    out.append(("water", [poly["exterior"]] + list(poly.get("holes") or [])))
        # the pavement map's faces (M22): their rings from the net's edges
        net = m.get("pavement_net") or {}
        V = {v["id"]: v["p"] for v in net.get("vertices", [])}
        E = {e["id"]: e["v"] for e in net.get("edges", [])}

        def ring_of(refs):
            pts = []
            for ref in refs:
                rev = ref.startswith("-")
                vs = E.get(ref[1:] if rev else ref)
                if vs is None:
                    return []
                vs = list(reversed(vs)) if rev else vs
                for vid in vs:
                    p = V.get(vid)
                    if p is not None and (not pts or pts[-1] != p):
                        pts.append(p)
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts.pop()
            return pts

        for f in sorted(m.get("pavement", []) or [], key=lambda f: f["id"]):
            cls = P.PAVEMENT_CLASS.get(f.get("kind"))
            if cls is None:
                continue
            rings = [ring_of(r) for r in f.get("rings") or []]
            rings = [r for r in rings if len(r) >= 3]
            if rings:
                out.append((cls if f.get("layer", "g0") in ("g0", "u1") else "deck", rings))
        for b in sorted(m.get("buildings", []), key=lambda b: b["id"]):
            for ms in b.get("masses") or []:
                if float(ms.get("z0_m", 0.0)) >= 0.8:
                    continue
                fp = ms.get("footprint") or {}
                if len(fp.get("exterior") or []) >= 3:
                    out.append(("roof", [fp["exterior"]] + list(fp.get("holes") or [])))
        for r in getattr(self, "road_rings", []):
            out.append(("deck", [r]))
        self.surface_list = [(CI[c], [_ring(x) for x in rings], _bbox([_ring(x) for x in rings]))
                             for c, rings in out]
        self.stats["surfaces"] = len(self.surface_list)

    def spots(self) -> None:
        """The puddles' point features: the roads' sags (the low points of their grade line)
        and AG7's drains (read from the street packs, as AT4's steam)."""
        from . import air as AR
        pd = P.PUDDLE
        c = self.c
        sags = []
        for s in sorted(c.m.get("road_segments", []), key=lambda s: s["id"]):
            ln = s.get("centerline") or []
            if len(ln) < 2:
                continue
            L = self.PL.Line([q[:2] for q in ln])
            if L.L < 2.0 * pd["sag_reach_m"]:
                continue
            n = int(L.L // 2.0) + 1
            ss = np.linspace(0.0, L.L, n)
            pts = [L.at(float(v)) for v in ss]
            xs = np.array([p[0] for p in pts])
            ys = np.array([p[1] for p in pts])
            h = self.ground_many(xs, ys) + np.array([self.PL.seg_z(s, float(v)) for v in ss])
            if float(h.max() - h.min()) < pd["sag_min_m"]:
                continue
            k = int(round(pd["sag_reach_m"] / 2.0))
            for i in range(k, n - k):
                win = h[i - k:i + k + 1]
                if h[i] <= win.min() and min(h[i - k:i].max(), h[i + 1:i + k + 1].max()) - h[i] \
                        >= pd["sag_min_m"] and (i == k or h[i] < h[i - 1]):
                    sags.append((float(xs[i]), float(ys[i])))
        self.sags = sags
        if getattr(c, "_street_details", None) is None:
            c._street_details = AR.street_details(c.build)
        det = {k: v for k, v in c._street_details.items() if k in c.segments}
        self.drains = sorted((p[0], p[1]) for v in det.values() for mt, p in v if mt == "drain")
        self.stats["sags"] = len(sags)
        self.stats["drains"] = len(self.drains)

    # -- per tile --

    def _bucket(self, items, box_of):
        """Items by the 256 m tiles their box (padded) touches."""
        T = self.PL.TILE_M
        pad = PAD * self.t + 1.0
        out: dict[tuple[int, int], list] = {}
        for it in items:
            x0, y0, x1, y1 = box_of(it)
            for i in range(math.floor((x0 - pad) / T), math.floor((x1 + pad) / T) + 1):
                for j in range(math.floor((y0 - pad) / T), math.floor((y1 + pad) / T) + 1):
                    out.setdefault((i, j), []).append(it)
        return out

    def masks_of(self, od: Path) -> None:
        """Every tile's mask (module docstring), written to `masks/<tile>.png` only when its
        bytes change; tiles the city's bounds leave out are removed."""
        from PIL import Image
        t = self.t
        z0, step = self.datum()
        self.z0, self.step = z0, step
        T = self.PL.TILE_M
        bx0, by0, bx1, by1 = self.bounds
        cov_t = self._bucket(self.cover_list, lambda r: r["box"])
        srf_t = self._bucket(self.surface_list, lambda r: r[2])
        sag_t = self._bucket(self.sags, lambda p: (p[0] - 8, p[1] - 8, p[0] + 8, p[1] + 8))
        drn_t = self._bucket(self.drains, lambda p: (p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3))
        dpolys = []
        for did in sorted(self.c.districts):
            poly = self.c.districts[did].get("polygon") or {}
            if len(poly.get("exterior") or []) >= 3:
                rings = [_ring(poly["exterior"])] + [_ring(h) for h in poly.get("holes") or []]
                dpolys.append((float(self.p.mood(did).get("grit", 0.5)), rings, _bbox(rings)))
        dis_t = self._bucket(dpolys, lambda r: r[2])
        pd = P.PUDDLE
        md = od / MASK_DIR
        md.mkdir(parents=True, exist_ok=True)
        keep = set()
        n_puddle = n_cover = n_drip = 0
        texels = 0
        for i in range(math.floor(bx0 / T), math.ceil(bx1 / T)):
            for j in range(math.floor(by0 / T), math.ceil(by1 / T)):
                name = f"t{i:+03d}{j:+03d}"
                G = Grid([i * T, j * T, (i + 1) * T, (j + 1) * T], t)
                n = G.n
                # the surfaces
                cls = np.full((n, n), CI["water"], dtype=np.uint8)
                for ci, rings, _ in srf_t.get((i, j), []):
                    hit = G.mask(rings)
                    if hit:
                        j0, i0, mk = hit
                        v = cls[j0:j0 + mk.shape[0], i0:i0 + mk.shape[1]]
                        v[mk] = ci
                # (past the map's edge: nothing, as the land ends there)
                out_x = (G.xs < bx0) | (G.xs > bx1)
                out_y = (G.ys < by0) | (G.ys > by1)
                cls[out_y, :] = CI["water"]
                cls[:, out_x] = CI["water"]
                # the cover (lowest underside), the drip bands of the low covers
                cover = np.full((n, n), np.inf, dtype=np.float64)
                drip = np.zeros((n, n), dtype=np.float64)
                for r in cov_t.get((i, j), []):
                    hit = G.mask(r["rings"], r["dx"], r["dy"])
                    if not hit:
                        continue
                    j0, i0, mk = hit
                    v = cover[j0:j0 + mk.shape[0], i0:i0 + mk.shape[1]]
                    v[mk] = np.minimum(v[mk], r["under"])
                    # (the band just past each dripping edge, out from the cover, moved
                    # downwind as its shadow is: where the drops land)
                    for quad in r.get("bands") or []:
                        hb = G.mask([quad])
                        if hb:
                            b0, c0, bm = hb
                            dv = drip[b0:b0 + bm.shape[0], c0:c0 + bm.shape[1]]
                            dv[bm] = 1.0
                covered = np.isfinite(cover)
                # the puddles
                X, Y = np.meshgrid(G.xs, G.ys)
                w0, w1 = pd["noise_w"]
                noise = w0 * value_noise(X, Y, pd["noise_m"][0], 0x51) + \
                    w1 * value_noise(X, Y, pd["noise_m"][1], 0xA7)
                road = cls == CI["road"]
                edge = (cls == CI["curb"]) | (cls == CI["walk"])
                gut = np.zeros((n, n))
                g0, g1 = pd["gutter_m"]
                steps = int(math.ceil(g1 / t))
                grown = edge.copy()
                for k in range(1, steps + 1):
                    grown = _dilate(grown, 1)
                    d = k * t
                    val = 1.0 if d <= g0 else max(0.0, 1.0 - (d - g0) / (g1 - g0))
                    newly = grown & road & (gut == 0.0)
                    gut[newly] = val
                spot = np.zeros((n, n))
                for (x, y) in sag_t.get((i, j), []):
                    d = np.hypot(X - x, Y - y)
                    spot = np.maximum(spot, pd["sag_w"] * np.clip(1.0 - d / pd["sag_r_m"], 0, 1))
                grit = np.full((n, n), 0.5)
                for gv, rings, _ in dis_t.get((i, j), []):
                    hit = G.mask(rings)
                    if hit:
                        j0, i0, mk = hit
                        v = grit[j0:j0 + mk.shape[0], i0:i0 + mk.shape[1]]
                        v[mk] = gv
                for (x, y) in drn_t.get((i, j), []):
                    d = np.hypot(X - x, Y - y)
                    near = np.clip(1.0 - d / pd["drain_r_m"], 0, 1)
                    spot = np.maximum(spot, near * (pd["drain_w"] + pd["drain_grit"] * grit))
                cw = np.zeros(len(CLASSES))
                for name_c, k in CI.items():
                    cw[k] = P.PUDDLE_CLASS.get(name_c, 0.0)
                pot = cw[cls] * (noise + pd["gutter_w"] * gut + spot)
                th = pd["threshold"] - pd["grit_drop"] * grit
                pud = np.clip((pot - th) / pd["depth"], 0.0, 1.0)
                pud[covered | (cw[cls] == 0.0)] = 0.0
                # the gloss when wet
                gl = np.array([P.SURFACE_GLOSS[k] for k in CLASSES])[cls]
                # (the drip band only on open ground, not on the water or under a cover)
                drip[covered | (cls == CI["water"])] = 0.0
                cq = np.where(covered, np.clip(np.floor((np.where(covered, cover, 0.0) - z0) /
                                                         step), 1, 255), 0)
                rgba = np.stack([cq, np.round(pud * 255.0), np.round(drip * 255.0),
                                 np.round(gl * 255.0)], axis=-1)
                rgba = G.crop(rgba).astype(np.uint8)
                texels += rgba.shape[0] * rgba.shape[1]
                n_cover += int((rgba[..., 0] > 0).sum())
                n_puddle += int((rgba[..., 1] > 0).sum())
                n_drip += int((rgba[..., 2] > 0).sum())
                buf = io.BytesIO()
                Image.fromarray(np.ascontiguousarray(rgba), "RGBA").save(
                    buf, format="PNG", compress_level=9)
                data = buf.getvalue()
                f = md / f"{name}.png"
                if not f.is_file() or f.read_bytes() != data:
                    f.write_bytes(data)
                keep.add(f.name)
                self.masks.append({"tile": name, "file": f"{MASK_DIR}/{name}.png",
                                   "px": int(rgba.shape[0]),
                                   "sha256": hashlib.sha256(data).hexdigest()})
        for f in sorted(md.glob("t*.png")):
            if f.name not in keep:
                f.unlink()
        self.stats.update({"texels": texels, "covered": round(n_cover / max(1, texels), 4),
                           "puddled": round(n_puddle / max(1, texels), 4),
                           "drip_band": round(n_drip / max(1, texels), 4)})

    # -- the drips --

    def drips_of(self, od: Path) -> None:
        """The drip lines of the low covers in pieces of at most `DRIPS["step_m"]`, by tile
        (`drips/<tile>.json`)."""
        PL = self.PL
        st, mn = float(P.DRIPS["step_m"]), float(P.DRIPS["min_m"])
        recs = []
        for r in self.cover_list:
            if not r["drips"]:
                continue
            kind = r["kind"] if r["kind"] in DRIP_KINDS else None
            if kind is None:
                continue
            k = 0
            for (a, b), z in r["drips"]:
                L = math.dist(a, b)
                if L < mn:
                    continue
                parts = max(1, int(math.ceil(L / st)))
                for q in range(parts):
                    f0, f1 = q / parts, (q + 1) / parts
                    pa = (a[0] + (b[0] - a[0]) * f0, a[1] + (b[1] - a[1]) * f0)
                    pb = (a[0] + (b[0] - a[0]) * f1, a[1] + (b[1] - a[1]) * f1)
                    mx, my = (pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0
                    gz = float(self.ground_many([mx], [my])[0])
                    if z - gz < 0.8:
                        continue
                    rec = {"id": f"{r['id']}.drip{k:02d}", "owner_id": r["id"], "kind": kind,
                           "tile": PL.tile_of(mx, my),
                           "a": [PL.mm(pa[0]), PL.mm(pa[1])], "b": [PL.mm(pb[0]), PL.mm(pb[1])],
                           "z_m": PL.mm(z), "ground_m": PL.mm(gz),
                           "rate": PL.r3(0.6 + 0.4 * PL.u(r["id"], k, "drip"))}
                    rec["hash"] = PL.sha(PL.dumps(rec))[:16]
                    recs.append(rec)
                    k += 1
        recs.sort(key=lambda r: r["id"])
        if len({r["id"] for r in recs}) != len(recs):
            raise RuntimeError("atmos plan: duplicate drip ids")
        self.drip_list = recs
        by: dict[str, list] = {}
        for r in recs:
            by.setdefault(r["tile"], []).append(r)
        dd = od / DRIP_DIR
        dd.mkdir(parents=True, exist_ok=True)
        keep = set()
        for t in sorted(by):
            text = PL.dumps({"version": 1, "city": self.c.name, "tile": t,
                             "drips": by[t]}) + "\n"
            f = dd / f"{t}.json"
            PL._write(f, text)
            keep.add(f.name)
            kinds: dict[str, int] = {}
            for r in by[t]:
                kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
            self.drip_tiles.append({"tile": t, "file": f"{DRIP_DIR}/{t}.json",
                                    "count": len(by[t]), "kinds": dict(sorted(kinds.items())),
                                    "sha256": PL.sha(text)})
        for f in sorted(dd.glob("t*.json")):
            if f.name not in keep:
                f.unlink()

    # -- the states, the settings --

    def settings(self) -> dict:
        PL = self.PL
        al = P.AIR_LOOK[self.filled["preset"]]
        states = {}
        for name in P.WEATHERS:
            ws, wl = P.WEATHER[name], P.WEATHER_LOOK[name]
            states[name] = {
                "rain": float(ws["rain"]), "streak": float(wl["streak"]),
                "drops": float(wl["drops"]), "wetness": float(ws["wetness"]),
                "puddles": float(wl["puddles"]), "cover": float(wl["cover"]),
                "volumes": float(wl["volumes"]), "gust": float(wl["gust"]),
                "wind_m_s": float(ws["wind_m_s"]),
                "fog_density": PL.r3(float(ws["fog_density"]) * al["density"]),
                "fog_falloff": float(al.get("falloff", ws["fog_falloff"])),
                "fog_extinction": PL.r3(float(ws["volumetric"]) * al["extinction"]),
                "fog_albedo": PL.hex_linear(ws["fog_albedo"])}
        counts: dict[str, int] = {}
        for r in self.drip_list:
            counts[f"drip.{r['kind']}"] = counts.get(f"drip.{r['kind']}", 0) + 1
        counts["drips"] = len(self.drip_list)
        counts["covers"] = len(self.cover_list)
        bx0, by0, bx1, by1 = self.bounds
        T = PL.TILE_M
        return {"start": self.filled["weather"], "states": states,
                "times": dict(P.WEATHER_TIMES),
                "wind": {"heading_deg": self.heading, "lean": self.lean,
                         "shift_max_m": float(P.WIND["shift_max_m"]),
                         "cover_max_m": float(P.WIND["cover_max_m"]),
                         "gale_m_s": float(P.WIND["gale_m_s"])},
                "texel_m": self.t,
                "extent": [math.floor(bx0 / T) * T, math.floor(by0 / T) * T,
                           math.ceil(bx1 / T) * T, math.ceil(by1 / T) * T],
                "cover": {"z0_m": float(self.z0), "step_m": float(self.step)},
                "gloss": {k: float(P.SURFACE_GLOSS[k]) for k in CLASSES},
                "drip_tiles": self.drip_tiles, "live": dict(P.WEATHER_LIVE),
                "counts": dict(sorted(counts.items())),
                "stats": dict(sorted(self.stats.items()))}

    # -- the check --

    def check(self, od: Path) -> dict:
        """Scope 8 for the weather: every tile's mask; every low cover's middle in its rain
        shadow (the mask's cover at or under its underside); no puddle under a cover, inside
        a building mass or on the water (the land polygons); the drips' budget per tile; every
        state."""
        from PIL import Image
        from shapely import contains_xy
        from shapely.geometry import Polygon
        bad: list[str] = []
        t = self.t
        T = self.PL.TILE_M
        tiles = {}
        for mk in self.masks:
            tiles[mk["tile"]] = mk
        bx0, by0, bx1, by1 = self.bounds
        want = {f"t{i:+03d}{j:+03d}" for i in range(math.floor(bx0 / T), math.ceil(bx1 / T))
                for j in range(math.floor(by0 / T), math.ceil(by1 / T))}
        missing = sorted(want - set(tiles))
        cache: dict[str, np.ndarray] = {}

        def texel(x, y):
            name = self.PL.tile_of(x, y)
            if name not in tiles:
                return None
            if name not in cache:
                with Image.open(od / tiles[name]["file"]) as im:
                    cache[name] = np.asarray(im.convert("RGBA"), dtype=np.uint8)
            a = cache[name]
            x0, y0, x1, y1 = self.PL.tile_bounds(name)
            i = min(a.shape[1] - 1, max(0, int((x - x0) / t)))
            j = min(a.shape[0] - 1, max(0, int((y1 - y) / t)))
            return a[j, i]

        unsheltered = 0
        checked = 0
        for r in self.cover_list:
            if not r["drips"] or not r["shelter"]:
                continue
            g = Polygon(r["rings"][0], r["rings"][1:])
            if not g.is_valid:
                g = g.buffer(0)
            if g.is_empty or g.area < 1.0:
                continue
            pt = g.buffer(-t).representative_point() if g.buffer(-t).area > 0 else \
                g.representative_point()
            px, py = pt.x + r["dx"], pt.y + r["dy"]
            v = texel(px, py)
            if v is None:
                continue
            checked += 1
            cz = self.z0 + float(v[0]) * self.step if v[0] > 0 else None
            if cz is None or cz > r["under"] + self.step:
                unsheltered += 1
                if len(bad) < 12:
                    bad.append(f"{r['id']}: not in its rain shadow")
        # puddles: never under a cover, in a building, on the water
        land = []
        for ld in self.c.m.get("land", []) or []:
            for poly in ld.get("polygons") or []:
                land.append(Polygon(poly.get("exterior") or [], poly.get("holes") or []))
        occ = self.c.occluders()
        # (a bridge's deck over the water: the roads' corridors)
        from shapely import STRtree, points
        from shapely.geometry import LineString
        corr = [LineString([q[:2] for q in s["centerline"]]).buffer(
            float(s.get("width_m", 8.0)) / 2.0 + 1.0, cap_style="flat")
            for s in self.c.m.get("road_segments", []) if len(s.get("centerline") or []) >= 2]
        tree = STRtree(corr) if corr else None
        wet_bad = 0
        n_pud = 0
        R = 1.2 * t + float(getattr(occ, "cell", 1.0))
        for name in sorted(tiles):
            with Image.open(od / tiles[name]["file"]) as im:
                a = np.asarray(im.convert("RGBA"), dtype=np.uint8)
            jj, ii = np.nonzero(a[..., 1] > 0)
            if jj.size == 0:
                continue
            x0, y0, x1, y1 = self.PL.tile_bounds(name)
            xs = x0 + (ii + 0.5) * t
            ys = y1 - (jj + 0.5) * t
            n_pud += int(jj.size)
            under = a[jj, ii, 0] > 0
            gz = self.ground_many(xs, ys)
            # (inside a building: the texel and the points R round it all in a mass, as lux's
            # occluders take them on their 1 m cells; a texel at a wall is outside it)
            inside = np.ones(xs.shape, dtype=bool)
            for ox, oy in ((0.0, 0.0), (R, 0.0), (-R, 0.0), (0.0, R), (0.0, -R)):
                inside &= occ.blocked(xs + ox, ys + oy, gz + 0.3)
            # (on the water: the texel and the points R round it all off the land, at a shore
            # drawn on the texel grid; a bridge's deck excepted)
            wet = np.ones(xs.shape, dtype=bool)
            for ox, oy in ((0.0, 0.0), (R, 0.0), (-R, 0.0), (0.0, R), (0.0, -R)):
                for g in land:
                    wet &= ~contains_xy(g, xs + ox, ys + oy)
            if wet.any() and tree is not None:
                ww = np.nonzero(wet)[0]
                pi, _ = tree.query(points(xs[ww], ys[ww]), predicate="intersects")
                wet[ww[np.unique(pi)]] = False
            k = int((under | inside | wet).sum())
            wet_bad += k
            if k and len(bad) < 12:
                bad.append(f"{name}: {int(under.sum())} puddle texels under a cover, "
                           f"{int(inside.sum())} in a building, {int(wet.sum())} on the water")
        per = {r["tile"]: r["count"] for r in self.drip_tiles}
        over = sorted(tt for tt, k in per.items() if k > P.WEATHER_BUDGETS["drips_per_tile"])
        states_ok = all(s in P.WEATHER and s in P.WEATHER_LOOK for s in P.WEATHERS)
        # (a cover whose middle the rasterizing at the texel misses, a sliver under a texel
        # across: at most 1% of them)
        shelter_ok = unsheltered <= max(2, int(0.01 * checked))
        # (a puddle texel in a passage narrower than the occluders' cells: a handful at most)
        ok = not missing and shelter_ok and wet_bad <= max(20, int(1e-4 * n_pud)) and \
            not over and states_ok
        return {"ok": ok, "tiles": len(tiles), "missing_tiles": missing[:12],
                "covers_checked": checked, "covers_unsheltered": unsheltered,
                "puddle_texels": n_pud, "puddles_misplaced": wet_bad,
                "drips": len(self.drip_list),
                "max_drips_per_tile": max(per.values(), default=0),
                "over_budget_tiles": over, "budgets": dict(P.WEATHER_BUDGETS),
                "states": list(P.WEATHERS), "examples": bad}


def check_text(c: dict) -> str:
    s = (f"weather check: {'PASS' if c['ok'] else 'FAIL'}: {c['tiles']} masks, "
         f"{c['covers_checked']} low covers checked ({c['covers_unsheltered']} out of their "
         f"rain shadow), {c['puddle_texels']} puddle texels ({c['puddles_misplaced']} "
         f"misplaced), {c['drips']} drip lines (at most {c['max_drips_per_tile']} in a tile; "
         f"budget {c['budgets']['drips_per_tile']})")
    if c["missing_tiles"]:
        s += "; tiles without a mask: " + ", ".join(c["missing_tiles"])
    if c["over_budget_tiles"]:
        s += "; over budget: " + ", ".join(c["over_budget_tiles"])
    if c["examples"]:
        s += "; " + "; ".join(c["examples"])
    return s + "\n"


# --- previews -----------------------------------------------------------------------------------

def preview(od: Path, plan: dict, scale_m: float = 2.0) -> dict:
    """`preview_weather.png` (the city at `scale_m` a pixel: the rain shadow blue, puddles
    cyan, the drip bands yellow, the surfaces by their gloss, the water dark) and
    `preview_weather_detail.png` (the tile with the most puddles and drips at full size, the
    drip lines over it)."""
    from PIL import Image, ImageDraw
    w = plan["weather_plan"]
    t = float(w["texel_m"])
    x0, y0, x1, y1 = w["extent"]
    k = max(1, int(round(scale_m / t)))
    W = int(round((x1 - x0) / (t * k)))
    H = int(round((y1 - y0) / (t * k)))
    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    best, best_n = None, -1
    for mk in plan.get("masks") or []:
        name = mk["tile"]
        ix, iy = int(name[1:4]), int(name[4:7])
        with Image.open(od / mk["file"]) as im:
            a = np.asarray(im.convert("RGBA"), dtype=np.uint8)
        img = _colors(a)
        n = int((a[..., 1] > 0).sum() + (a[..., 2] > 0).sum())
        if n > best_n:
            best, best_n = (name, img), n
        sm = img[::k, ::k]
        ci = int(round((ix * 256.0 - x0) / (t * k)))
        cj = int(round((y1 - (iy + 1) * 256.0) / (t * k)))
        canvas[cj:cj + sm.shape[0], ci:ci + sm.shape[1]] = sm[:max(0, H - cj), :max(0, W - ci)]
    im = Image.fromarray(canvas, "RGB")
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, W, 22], fill=(5, 7, 13))
    c = w["counts"]
    dr.text((6, 5), f"{plan['city']}: rain shadow (blue), puddles (cyan), drip bands (yellow), "
                    f"{c.get('covers', 0)} covers, {c.get('drips', 0)} drip lines; wind toward "
                    f"{w['wind']['heading_deg']:g} deg", fill=(216, 222, 234))
    dest = od / PREVIEW
    im.save(dest)
    out = {"image": str(dest)}
    if best is not None:
        name, img = best
        big = Image.fromarray(img, "RGB").resize((img.shape[1] * 2, img.shape[0] * 2),
                                                  Image.NEAREST)
        d2 = ImageDraw.Draw(big)
        tx0, ty0, tx1, ty1 = [float(v) for v in (int(name[1:4]) * 256.0, int(name[4:7]) * 256.0,
                                                  int(name[1:4]) * 256.0 + 256.0,
                                                  int(name[4:7]) * 256.0 + 256.0)]
        f = od / DRIP_DIR / f"{name}.json"
        if f.is_file():
            for r in json.loads(f.read_text(encoding="utf-8"))["drips"]:
                pa = ((r["a"][0] - tx0) / t * 2, (ty1 - r["a"][1]) / t * 2)
                pb = ((r["b"][0] - tx0) / t * 2, (ty1 - r["b"][1]) / t * 2)
                d2.line([pa, pb], fill=(255, 64, 160), width=2)
        d2.rectangle([0, 0, big.size[0], 22], fill=(5, 7, 13))
        d2.text((6, 5), f"{name} at {t / 2:g} m a pixel: shadow blue, puddles cyan, drip bands "
                        f"yellow, drip lines magenta", fill=(216, 222, 234))
        big.save(od / DETAIL)
        out["detail"] = str(od / DETAIL)
        out["detail_tile"] = name
    return out


def _colors(a: np.ndarray) -> np.ndarray:
    gl = a[..., 3].astype(np.float32) / 255.0
    base = np.stack([30 + 90 * gl, 30 + 90 * gl, 34 + 96 * gl], axis=-1)
    water = (a[..., 3] == 0) & (a[..., 0] == 0)
    base[water] = (8, 20, 38)
    cov = a[..., 0] > 0
    base[cov] = base[cov] * 0.45 + np.array([20, 60, 170]) * 0.55
    pud = a[..., 1].astype(np.float32)[..., None] / 255.0
    base = base * (1 - np.minimum(1.0, 0.4 + pud) * (pud > 0)) + \
        np.array([40, 230, 255]) * np.minimum(1.0, 0.4 + pud) * (pud > 0)
    dr = a[..., 2] > 0
    base[dr] = (255, 205, 40)
    return np.clip(base, 0, 255).astype(np.uint8)
