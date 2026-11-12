"""The lux check and map (scope 8, AT1): the plan's illuminance on every walkway and lane of
the city by night, with occlusion against the building masses, against targets by walkway
class; and its map round the corporate core (`preview_lux.png`).

$$E(p) = \\sum_i \\frac{I_i(\\gamma_i)\\,\\cos\\theta_i}{d_i^2}\\,w_i(d_i)\\,V_i(p)\\,k_i$$

with $I_i(\\gamma)$ the light's intensity toward $p$ by its profile (`presets.PHOTOMETRY`,
Unreal's own: a spot's peak inside its inner cone falling as $t^2$ to its outer, a point's
alike all round, a lit face's times the cosine off its normal, nothing past its barn doors
or behind it), $\\theta_i$ the angle of incidence on the ground (a level floor at the
point's height), $d_i$ the distance, $w_i = \\mathrm{clamp}(1 - (d/R)^4)^2$ Unreal's window
at the light's reach $R$, $k_i$ its schedule at the check's hour (broken lights dark) and
$V_i(p) \\in \\{0, 1\\}$ whether the light sees $p$: the segment between them clear of the
building masses and deck slabs (`Occluders`: per 1 m cell the lowest bottom and highest
top of what covers its middle, a mass's footprint taken 0.5 m in so a ray grazing its facade
stays clear, marched every meter, the first meter from the light and the last 0.75 m to the
point left out, where a facade's own fixture and the curb stand).

The check's points (`samples`): every walkway and lane every 2 m by class (sidewalks,
promenades, pedestrian streets and footbridges `sidewalk`; crosswalks and the crossings at
the junctions `crosswalk`; the lanes of every road and junction `carriageway`; alleys and
their lanes `alley`; anything on the ground under a deck slab `under_deck`), at its height
(a raised road's sidewalks on its deck). A class passes (`check`) when its average over the
city meets its target, at most `presets.UNDER_MIN_SHARE` of its points are under its
minimum and no alley point is dark, and in every district its average is at least half the
target with at most `DISTRICT_UNDER_SHARE` under the minimum. Park paths are reported, not
judged. The plan is not delivered unless every class passes.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import presets as P

CHECK_HOUR = 23.0         # the check's hour: by night whatever the look's start hour
OCC_CELL = 1.0            # the occluders' raster (m)
ERODE_M = 0.5             # ... a cell the building's when its middle is this far inside
STEP = 1.0                # the occlusion march (m along the ground)
SKIP_LIGHT = 1.0          # ... from this far from the light
SKIP_POINT = 0.75         # ... to this far short of the point
BIN = 16.0                # the points' spatial bins (m)

# walkway kind -> class
CLASS = {"sidewalk": "sidewalk", "promenade": "sidewalk", "pedestrian_street": "sidewalk",
         "footbridge": "sidewalk", "underpass": "sidewalk", "crosswalk": "crosswalk",
         "crossing": "crosswalk", "alley": "alley", "path": "path"}
CLASSES = ("sidewalk", "crosswalk", "carriageway", "under_deck", "alley", "path")
JUDGED = ("sidewalk", "crosswalk", "carriageway", "under_deck", "alley")


# --- the occluders ------------------------------------------------------------------------

class Occluders:
    """The building masses and deck slabs on a raster over the city: per cell the lowest
    bottom and highest top (absolute m) of what covers its middle (a deck slab only from
    its underside: the streets under it stay open)."""

    def __init__(self, m: dict, ground=None, cell: float = OCC_CELL):
        from PIL import Image, ImageDraw
        if m.get("bounds"):
            x0, y0, x1, y1 = (float(v) for v in m["bounds"])
        else:
            pts = [p for b in m.get("buildings", []) for ms in b.get("masses") or []
                   for p in (ms.get("footprint") or {}).get("exterior") or []]
            pts = pts or [[0.0, 0.0]]
            x0 = min(p[0] for p in pts) - 1.0
            y0 = min(p[1] for p in pts) - 1.0
            x1 = max(p[0] for p in pts) + 1.0
            y1 = max(p[1] for p in pts) + 1.0
        self.x0, self.y0, self.cell = x0, y0, cell
        self.nx = int(math.ceil((x1 - x0) / cell))
        self.ny = int(math.ceil((y1 - y0) / cell))
        self.bot = np.full((self.ny, self.nx), np.inf, dtype=np.float32)
        self.top = np.full((self.ny, self.nx), -np.inf, dtype=np.float32)

        def put(rings, z0, z1, erode=True):
            ext = rings[0]
            if len(ext) < 3:
                return
            if erode:
                # (a cell is the building's when its middle is ERODE_M inside the footprint:
                # a ray grazing a facade, from a fixture on it along the street, stays clear;
                # a mass thinner than twice that, a fin or a column, blocks nothing)
                from shapely.geometry import Polygon
                g = Polygon(ext, [h for h in rings[1:] if len(h) >= 3])
                if not g.is_valid:
                    g = g.buffer(0)
                g = g.buffer(-ERODE_M, join_style="mitre")
                if g.is_empty:
                    return
                parts = list(getattr(g, "geoms", [g]))
                if len(parts) > 1:
                    for q in parts:
                        put([list(q.exterior.coords)] + [list(h.coords) for h in q.interiors],
                            z0, z1, erode=False)
                    return
                rings = [list(g.exterior.coords)] + [list(h.coords) for h in g.interiors]
                ext = rings[0]
            xs = [p[0] for p in ext]
            ys = [p[1] for p in ext]
            i0 = max(0, int(math.floor((min(xs) - x0) / cell)))
            j0 = max(0, int(math.floor((min(ys) - y0) / cell)))
            i1 = min(self.nx, int(math.ceil((max(xs) - x0) / cell)) + 1)
            j1 = min(self.ny, int(math.ceil((max(ys) - y0) / cell)) + 1)
            if i1 <= i0 or j1 <= j0:
                return
            img = Image.new("L", (i1 - i0, j1 - j0), 0)
            dr = ImageDraw.Draw(img)
            for k, ring in enumerate(rings):
                if len(ring) < 3:
                    continue
                pts = [((p[0] - x0) / cell - i0 - 0.5, (p[1] - y0) / cell - j0 - 0.5)
                       for p in ring]
                dr.polygon(pts, fill=1 if k == 0 else 0)
            mask = np.asarray(img, dtype=bool)
            if not mask.any():
                return
            b = self.bot[j0:j1, i0:i1]
            t = self.top[j0:j1, i0:i1]
            b[mask] = np.minimum(b[mask], np.float32(z0))
            t[mask] = np.maximum(t[mask], np.float32(z1))

        self.masses = 0
        for bld in m.get("buildings", []):
            base = bld.get("base_m")
            if base is None:
                fp = (bld.get("footprint") or {}).get("exterior") or [[0.0, 0.0]]
                base = ground(fp[0][0], fp[0][1]) if ground is not None else 0.0
            base = float(base)
            for ms in bld.get("masses") or []:
                fp = ms.get("footprint") or {}
                rings = [fp.get("exterior") or []] + list(fp.get("holes") or [])
                z0 = base + float(ms.get("z0_m", 0.0))
                z1 = base + float(ms.get("z1_m", 0.0))
                # (a plinth down to the lowest ground under it: M13's slopes)
                if ms.get("z0_m", 0.0) <= 0.0 and bld.get("plinth_m") is not None:
                    z0 = min(z0, float(bld["plinth_m"]))
                put(rings, z0 - 0.5, z1)
                self.masses += 1
        self.decks = []
        for dk in m.get("decks", []) or []:
            poly = dk.get("polygon") or {}
            ext = poly.get("exterior") or []
            if len(ext) < 3:
                continue
            g = ground(ext[0][0], ext[0][1]) if ground is not None else 0.0
            top = g + float(dk.get("top_m", 9.0))
            under = top - float(dk.get("slab_m", 1.0))
            put([ext] + list(poly.get("holes") or []), under, top, erode=False)
            self.decks.append((dk["id"], poly, under, top))

    def blocked(self, x, y, z) -> np.ndarray:
        """Whether each point (arrays) lies inside an occluder's cell between its bottom and
        top."""
        i = np.floor((x - self.x0) / self.cell).astype(np.int64)
        j = np.floor((y - self.y0) / self.cell).astype(np.int64)
        ok = (i >= 0) & (i < self.nx) & (j >= 0) & (j < self.ny)
        i = np.where(ok, i, 0)
        j = np.where(ok, j, 0)
        return ok & (self.bot[j, i] < z) & (z < self.top[j, i])

    def visible(self, lx, ly, lz, px, py, pz) -> np.ndarray:
        """Whether the light at (lx, ly, lz) sees each point (arrays px, py, pz)."""
        dx, dy, dz = px - lx, py - ly, pz - lz
        dh = np.hypot(dx, dy)
        n = int(math.ceil(max(0.0, float(dh.max(initial=0.0)) - SKIP_LIGHT - SKIP_POINT)
                          / STEP)) if dh.size else 0
        if n <= 0:
            return np.ones(px.shape, dtype=bool)
        s = SKIP_LIGHT + STEP * np.arange(n)[None, :]                     # along the ground
        valid = s < (dh[:, None] - SKIP_POINT)
        t = s / np.maximum(dh[:, None], 1e-9)
        bx = lx + t * dx[:, None]
        by = ly + t * dy[:, None]
        bz = lz + t * dz[:, None]
        hit = self.blocked(bx, by, bz) & valid
        return ~hit.any(axis=1)


# --- intensity ----------------------------------------------------------------------------

def _aim(L) -> tuple[float, float, float]:
    yaw, pitch = math.radians(L["aim"][0]), math.radians(L["aim"][1])
    return (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw),
            math.sin(pitch))


def _intensity(L: dict, gx, gy, gz, d) -> np.ndarray:
    """A light's intensity (cd) toward points offset (gx, gy, gz) from it, by its profile,
    times Unreal's window at its reach."""
    ax, ay, az = _aim(L)
    cos_g = (gx * ax + gy * ay + gz * az) / d
    if L["shape"] == "spot":
        ci, co = (math.cos(math.radians(a)) for a in L["cone"])
        t = np.clip((cos_g - co) / max(ci - co, 1e-6), 0.0, 1.0)
        I = L["cd"] * t * t
    elif L["shape"] == "rect":
        barn = math.cos(math.radians(float(L.get("barn_deg") or 90.0)))
        I = np.where(cos_g >= barn, L["cd"] * np.clip(cos_g, 0.0, 1.0), 0.0)
    else:
        I = np.full_like(d, float(L["cd"]))
    R = float(L["reach_m"])
    return I * np.clip(1.0 - (d / R) ** 4, 0.0, 1.0) ** 2


def contribution(L: dict, gx, gy, gz) -> np.ndarray:
    """A light's illuminance on a level floor at points offset (gx, gy, gz) from it (point
    minus light, m), before occlusion and its schedule."""
    d2 = gx * gx + gy * gy + gz * gz
    d = np.sqrt(np.maximum(d2, 1e-6))
    cos_in = np.clip(-gz / d, 0.0, 1.0)          # (a floor lit from above)
    return _intensity(L, gx, gy, gz, d) * cos_in / np.maximum(d2, 0.01)


def on_surface(L: dict, pts: np.ndarray, normal) -> np.ndarray:
    """A light's illuminance on surfaces at points `pts` (n x 3, absolute) facing `normal`
    (a unit vector, the same for all), before occlusion and its schedule (AT2: a wall)."""
    g = pts - np.array([float(v) for v in L["pos"]])
    d2 = (g * g).sum(axis=1)
    d = np.sqrt(np.maximum(d2, 1e-6))
    cos_in = np.clip(-(g @ np.asarray(normal, dtype=np.float64)) / d, 0.0, 1.0)
    return _intensity(L, g[:, 0], g[:, 1], g[:, 2], d) * cos_in / np.maximum(d2, 0.01)


def face_check(walls: list[dict], occ: "Occluders | None") -> dict:
    """AT2's faces check: each lit face's light (a billboard's, banner's or holo-board's rect)
    on its own wall, probed `presets.FACE_WALL_OUT_M` out of it (what stands out of a
    facade) at eight points `FACE_WALL_RING_M` round the face, must stay under
    `FACE_WALL_MAX_LX` (AT0's band flooded its wall); and what it throws on the facade
    opposite (the first building it meets straight out, within its reach) is reported."""
    out_m, ring = P.FACE_WALL_OUT_M, P.FACE_WALL_RING_M
    worst, over, first = 0.0, 0, []
    opp, reached = [], 0
    for f in walls:
        # (without its barn doors: Unreal's are 20 cm, which hardly cut a face meters wide)
        L = {**f["light"], "barn_deg": 90.0}
        a = math.radians(f["yaw"])
        n = np.array([math.cos(a), math.sin(a), 0.0])
        t = np.array([-math.sin(a), math.cos(a), 0.0])
        up = np.array([0.0, 0.0, 1.0])
        w, h = f["size"]
        wall = np.array(f["wall"], dtype=np.float64)
        e = 0.0
        # the wall and the fronts of what stands out of it (facing out), and the sides of
        # what stands out half way (facing along the wall, both ways), round the face
        for o, normals in ((0.0, (n,)), (0.5 * out_m, (n, t, -t)), (out_m, (n,))):
            c = wall + n * o
            pts = np.array([c + t * i * (w / 2.0 + ring) + up * j * (h / 2.0 + ring)
                            for i in (-1, 0, 1) for j in (-1, 0, 1) if i or j])
            for nv in normals:
                e = max(e, float(on_surface(L, pts, nv).max()))
        worst = max(worst, e)
        if e > P.FACE_WALL_MAX_LX:
            over += 1
            if len(first) < 5:
                first.append(f"{L['id']} {e:.1f} lx")
        if occ is None:
            continue
        # straight out from the light, every meter, to the first building cell at its height
        lx, ly, lz = (float(v) for v in L["pos"])
        s = np.arange(1.0, float(L["reach_m"]), 1.0)
        bx, by = lx + n[0] * s, ly + n[1] * s
        hit = np.flatnonzero(occ.blocked(bx, by, np.full(s.shape, lz)))
        if hit.size:
            k = int(hit[0])
            p = np.array([[bx[k] - n[0] * 0.6, by[k] - n[1] * 0.6, lz]])
            opp.append(float(on_surface(L, p, -n)[0]))
            reached += 1
    o = np.array(opp) if opp else np.zeros(0)
    return {"ok": over == 0, "faces": len(walls), "own_wall_max_lx": round(worst, 3),
            "own_wall_limit_lx": P.FACE_WALL_MAX_LX, "over": over, "first_over": first,
            "opposite": {"reached": reached,
                         "share": round(reached / len(walls), 3) if walls else 0.0,
                         "median_lx": round(float(np.median(o)), 2) if o.size else 0.0,
                         "p90_lx": round(float(np.percentile(o, 90)), 2) if o.size else 0.0}}


def face_text(res: dict) -> str:
    o = res["opposite"]
    return (f"lit faces: {res['faces']}, their own walls at most {res['own_wall_max_lx']} lx "
            f"(limit {res['own_wall_limit_lx']}): {'PASS' if res['ok'] else 'FAIL'}"
            + (f" ({res['over']} over: {', '.join(res['first_over'])})" if res["over"] else "")
            + f"\n  the facade opposite reached by {o['reached']} ({100 * o['share']:.0f}%), "
              f"median {o['median_lx']} lx, 90th percentile {o['p90_lx']} lx\n")


def share(L: dict, schedules: dict, hour: float = CHECK_HOUR) -> float:
    if not L.get("on", True):
        return 0.0
    return float(schedules.get(L["schedule"], [1.0] * 24)[int(math.floor(hour)) % 24])


class Points:
    """Points with a spatial index (bins of BIN m), for the lights to find theirs."""

    def __init__(self, xyz: np.ndarray):
        self.xyz = xyz
        self.n = len(xyz)
        if not self.n:
            self.keys = np.zeros(0, dtype=np.int64)
            self.order = np.zeros(0, dtype=np.int64)
            self.bins = {}
            return
        bi = np.floor(xyz[:, 0] / BIN).astype(np.int64)
        bj = np.floor(xyz[:, 1] / BIN).astype(np.int64)
        key = bi * 1_000_003 + bj
        self.order = np.argsort(key, kind="stable")
        ks = key[self.order]
        starts = np.flatnonzero(np.r_[True, ks[1:] != ks[:-1]])
        ends = np.r_[starts[1:], len(ks)]
        self.bins = {(int(bi[self.order[s]]), int(bj[self.order[s]])): (int(s), int(e))
                     for s, e in zip(starts, ends)}

    def near(self, x: float, y: float, r: float) -> np.ndarray:
        i0, i1 = int(math.floor((x - r) / BIN)), int(math.floor((x + r) / BIN))
        j0, j1 = int(math.floor((y - r) / BIN)), int(math.floor((y + r) / BIN))
        parts = []
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                se = self.bins.get((i, j))
                if se is not None:
                    parts.append(self.order[se[0]:se[1]])
        if not parts:
            return np.zeros(0, dtype=np.int64)
        idx = np.concatenate(parts)
        dx = self.xyz[idx, 0] - x
        dy = self.xyz[idx, 1] - y
        return idx[dx * dx + dy * dy <= r * r]


def light_on(L: dict, pts: Points, occ: Occluders | None, schedules: dict,
             hour: float = CHECK_HOUR) -> tuple[np.ndarray, np.ndarray]:
    """One light's lux on the points it reaches: (indices, lux)."""
    k = share(L, schedules, hour)
    if k < 0.05:
        return np.zeros(0, dtype=np.int64), np.zeros(0)
    lx, ly, lz = (float(v) for v in L["pos"])
    idx = pts.near(lx, ly, float(L["reach_m"]))
    if not idx.size:
        return idx, np.zeros(0)
    p = pts.xyz[idx]
    e = contribution(L, p[:, 0] - lx, p[:, 1] - ly, p[:, 2] - lz) * k
    keep = e > 1e-4
    idx, e, p = idx[keep], e[keep], p[keep]
    if occ is not None and idx.size:
        vis = occ.visible(lx, ly, lz, p[:, 0], p[:, 1], p[:, 2])
        idx, e = idx[vis], e[vis]
    return idx, e


def light_at(L: dict, xyz: np.ndarray, occ: Occluders | None, schedules: dict,
             hour: float = CHECK_HOUR) -> np.ndarray:
    """One light's lux on each of a few points (no index: a junction's)."""
    out = np.zeros(len(xyz))
    k = share(L, schedules, hour)
    if k < 0.05 or not len(xyz):
        return out
    lx, ly, lz = (float(v) for v in L["pos"])
    g = xyz - np.array([lx, ly, lz])
    R = float(L["reach_m"])
    near = g[:, 0] ** 2 + g[:, 1] ** 2 <= R * R
    if not near.any():
        return out
    e = contribution(L, g[near, 0], g[near, 1], g[near, 2]) * k
    if occ is not None:
        p = xyz[near]
        e = e * occ.visible(lx, ly, lz, p[:, 0], p[:, 1], p[:, 2])
    out[near] = e
    return out


def illuminance_points(lights: list[dict], pts: Points, occ: Occluders | None,
                       schedules: dict, hour: float = CHECK_HOUR) -> np.ndarray:
    E = np.zeros(pts.n, dtype=np.float64)
    for L in lights:
        idx, e = light_on(L, pts, occ, schedules, hour)
        if idx.size:
            np.add.at(E, idx, e)
    return E


def illuminance(lights: list[dict], x0: float, y0: float, n: int, cell: float, hour: float,
                schedules: dict, occ: Occluders | None = None, z=0.0) -> np.ndarray:
    """E (lux) on an n x n raster from (x0, y0), rows from the south, on a level floor at
    `z` (a number, or an n x n array of heights)."""
    xs = x0 + (np.arange(n) + 0.5) * cell
    ys = y0 + (np.arange(n) + 0.5) * cell
    gx, gy = np.meshgrid(xs, ys)
    gz = np.broadcast_to(np.asarray(z, dtype=np.float64), gx.shape)
    pts = Points(np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1))
    return illuminance_points(lights, pts, occ, schedules, hour).reshape(n, n)


# --- the check's points -------------------------------------------------------------------

def _along(line, step: float = P.SAMPLE_M):
    """A line's points every `step` m, each in the middle of its stretch (its vertices alone
    sit at its ends, at the junctions)."""
    out = []
    for a, b in zip(line, line[1:]):
        L = math.dist(a[:2], b[:2])
        if L <= 1e-6:
            continue
        k = max(1, int(round(L / step)))
        za, zb = (a[2] if len(a) > 2 else 0.0), (b[2] if len(b) > 2 else 0.0)
        for s in range(k):
            f = (s + 0.5) / k
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f,
                        za + (zb - za) * f))
    return out


class Samples:
    """The check's points: absolute xyz, class, district and junction (or -1) per point."""

    def __init__(self, city):
        from shapely import contains_xy, line_locate_point
        from shapely.geometry import LineString, Polygon
        m = city.m
        rows: list[tuple] = []           # (x, y, z over the ground, class, junction, owner)
        segs = city.segments
        jn_of_node = {j.get("node_id"): j["id"] for j in m.get("junctions", [])}
        nz = {n["id"]: float(n["position"][2]) for n in m.get("road_nodes", [])
              if len(n.get("position") or []) > 2}
        jn_z = {j["id"]: nz[j["node_id"]] for j in m.get("junctions", [])
                if j.get("node_id") in nz}
        jids: list[str] = []
        jix: dict[str, int] = {}

        def jcode(jid):
            if jid is None:
                return -1
            if jid not in jix:
                jix[jid] = len(jids)
                jids.append(jid)
            return jix[jid]

        raised: dict[str, tuple] = {}

        def seg_z(sid, pts):
            """A walkway along a raised road on the road's surface: the walk graph keeps a
            raised road's sidewalks at 0, and a quay road's walk at one height where the
            road climbs."""
            s = segs.get(sid)
            prof = (s or {}).get("z_profile") or []
            if not prof or max(abs(float(q["z"])) for q in prof) < 0.5:
                return None
            if sid not in raised:
                raised[sid] = (LineString([c[:2] for c in s["centerline"]]),
                               np.array([float(q["s"]) for q in prof]),
                               np.array([float(q["z"]) for q in prof]))
            ln, ss, zz = raised[sid]
            from shapely import distance as sdist
            from shapely import points as spoints
            q = spoints(np.array([p[:2] for p in pts]))
            sv = line_locate_point(ln, q)
            # (only where the walkway runs along the road, within its half width and a
            # sidewalk: a walkway that only names the road keeps the walk graph's height)
            along = sdist(ln, q) <= float(s.get("width_m", 8.0)) / 2.0 + 1.0
            return np.where(along, np.interp(sv, ss, zz), np.array([p[2] for p in pts]))

        for w in m.get("walkways", []):
            c = CLASS.get(w.get("kind"))
            if c is None:
                continue
            pts = _along(w["line"])
            if not pts:
                continue
            at = w.get("attrs") or {}
            jc = jcode(at.get("junction")) if c == "crosswalk" else -1
            zs = None
            if c in ("sidewalk", "alley") and at.get("segment"):
                zs = seg_z(at["segment"], pts)
            elif c == "crosswalk" and at.get("junction") in jn_z and \
                    abs(jn_z[at["junction"]]) > 0.5 and all(abs(p[2]) < 0.05 for p in pts):
                # (a raised junction's crossings at its node's height: the walk graph keeps
                # them on the ground, as a raised road's sidewalks)
                zs = np.full(len(pts), jn_z[at["junction"]])
            own = ("walk", w["id"], at.get("segment"), float(w.get("width_m") or 2.0))
            for k, p in enumerate(pts):
                rows.append((p[0], p[1], float(zs[k]) if zs is not None else p[2], c, jc, own))
        for ln in m.get("lanes", []):
            pts = _along(ln.get("centerline") or [])
            if not pts:
                continue
            if ln.get("node_id"):
                c, jc = "carriageway", jcode(jn_of_node.get(ln["node_id"]))
            else:
                rc = (segs.get(ln.get("segment_id")) or {}).get("road_class")
                if rc in ("pedestrian", "footbridge", "path", "promenade", None):
                    continue
                c, jc = ("alley" if rc == "alley" else "carriageway"), -1
            own = ("lane", ln.get("segment_id") or ln.get("node_id"), ln.get("segment_id"),
                   float(ln.get("width_m") or 3.0))
            for p in pts:
                rows.append((p[0], p[1], p[2], c, jc, own))
        n = len(rows)
        xy = np.array([(r[0], r[1]) for r in rows], dtype=np.float64).reshape(n, 2)
        zl = np.array([r[2] for r in rows], dtype=np.float64)
        cls = np.array([CLASSES.index(r[3]) for r in rows], dtype=np.int8)
        self.junction = np.array([r[4] for r in rows], dtype=np.int64)
        self.junction_ids = jids
        # what each point lies on (a walkway, or a road's lanes), for the plan's fill
        self.owners: list[tuple] = []
        oix: dict[tuple, int] = {}
        own = np.zeros(n, dtype=np.int64)
        for k, r in enumerate(rows):
            key = r[5][:2]
            if key not in oix:
                oix[key] = len(self.owners)
                self.owners.append(r[5])
            own[k] = oix[key]
        self.owner = own
        # under a deck slab: what stands on the ground under it
        occ_decks = []
        for dk in m.get("decks", []) or []:
            poly = dk.get("polygon") or {}
            if len((poly.get("exterior") or [])) >= 3:
                occ_decks.append(Polygon(poly["exterior"], [h for h in poly.get("holes") or []
                                                            if len(h) >= 3]))
        for g in occ_decks:
            inside = contains_xy(g, xy[:, 0], xy[:, 1]) & (zl < 3.0)
            cls[inside & (cls != CLASSES.index("path"))] = CLASSES.index("under_deck")
        gz = city.ground_many(xy[:, 0], xy[:, 1]) if n else np.zeros(0)
        self.xyz = np.column_stack([xy, zl + gz]) if n else np.zeros((0, 3))
        self.cls = cls
        # district by point
        self.district_ids = sorted(city.districts)
        dist = np.full(n, -1, dtype=np.int64)
        for k, did in enumerate(self.district_ids):
            poly = city.districts[did].get("polygon") or {}
            if len(poly.get("exterior") or []) < 3:
                continue
            g = Polygon(poly["exterior"], [h for h in poly.get("holes") or [] if len(h) >= 3])
            dist[(dist < 0) & contains_xy(g, xy[:, 0], xy[:, 1])] = k
        self.district = dist
        self.points = Points(self.xyz)


# --- the check ----------------------------------------------------------------------------

def _stats(E: np.ndarray, avg_t: float, min_t: float) -> dict:
    return {"points": int(E.size), "average_lx": round(float(E.mean()), 2) if E.size else 0.0,
            "min_lx": round(float(E.min()), 3) if E.size else 0.0,
            "under_min": round(float((E < min_t).mean()), 4) if E.size else 0.0,
            "dark": int((E < P.ZERO_LX).sum()),
            "target_average_lx": avg_t, "target_min_lx": min_t}


def check(S: Samples, E: np.ndarray, levels: dict | None = None) -> dict:
    """The lux check on the samples' illuminance `E`: per class over the city and per
    district (module docstring); {ok, classes, districts, junctions, failures}."""
    levels = {**{k: list(v) for k, v in P.LIGHT_LEVELS.items()}, **(levels or {})}
    out = {"hour": CHECK_HOUR, "classes": {}, "districts": {}, "failures": []}
    for ci, c in enumerate(CLASSES):
        sel = S.cls == ci
        if not sel.any():
            continue
        avg_t, min_t = levels.get(c, (0.0, 0.0))
        st = _stats(E[sel], avg_t, min_t)
        judged = c in JUDGED
        ok = (not judged) or (st["average_lx"] >= avg_t and
                              st["under_min"] <= P.UNDER_MIN_SHARE and
                              (c != "alley" or st["dark"] == 0))
        st["ok"] = bool(ok)
        st["judged"] = judged
        out["classes"][c] = st
        if not ok:
            out["failures"].append(
                f"{c}: average {st['average_lx']} lx (target {avg_t}), "
                f"{100 * st['under_min']:.1f}% under {min_t} lx (at most "
                f"{100 * P.UNDER_MIN_SHARE:.0f}%)" + (f", {st['dark']} points dark"
                                                       if c == "alley" and st["dark"] else ""))
        if not judged:
            continue
        for di, did in enumerate(S.district_ids):
            dsel = sel & (S.district == di)
            if int(dsel.sum()) < P.DISTRICT_MIN_POINTS:
                continue
            dst = _stats(E[dsel], avg_t, min_t)
            dok = (dst["average_lx"] >= P.DISTRICT_AVG_SHARE * avg_t and
                   dst["under_min"] <= P.DISTRICT_UNDER_SHARE)
            dst["ok"] = bool(dok)
            out["districts"].setdefault(did, {})[c] = dst
            if not dok:
                out["failures"].append(
                    f"{c} in {did}: average {dst['average_lx']} lx (at least "
                    f"{P.DISTRICT_AVG_SHARE * avg_t:g}), {100 * dst['under_min']:.1f}% under "
                    f"{min_t} lx (at most {100 * P.DISTRICT_UNDER_SHARE:.0f}%)")
    # the junctions (their lanes and crosswalks; the run-through's and AT0's dark spots)
    sel = S.junction >= 0
    if sel.any():
        jl = sel & (S.cls == CLASSES.index("carriageway"))
        jc = sel & (S.cls == CLASSES.index("crosswalk"))
        out["junctions"] = {
            "lanes": _stats(E[jl], *levels["carriageway"]) if jl.any() else {},
            "crosswalks": _stats(E[jc], *levels["crosswalk"]) if jc.any() else {}}
    out["ok"] = not out["failures"]
    return out


def check_text(res: dict) -> str:
    lines = [f"lux check at {res['hour']:g}:00: {'PASS' if res['ok'] else 'FAIL'}"]
    for c, st in res["classes"].items():
        lines.append(f"  {c}: {st['points']} points, average {st['average_lx']} lx "
                     f"(target {st['target_average_lx']}), {100 * st['under_min']:.1f}% under "
                     f"{st['target_min_lx']} lx" + ("" if st["judged"] else " (reported)")
                     + ("" if st["ok"] else "  FAIL"))
    for k, st in (res.get("junctions") or {}).items():
        if st:
            lines.append(f"  junction {k}: average {st['average_lx']} lx, "
                         f"{100 * st['under_min']:.1f}% under {st['target_min_lx']} lx")
    for f in res["failures"]:
        lines.append(f"  failure: {f}")
    return "\n".join(lines) + "\n"


# --- the map ------------------------------------------------------------------------------

def _core(m: dict) -> tuple[float, float, str]:
    """The middle of the corporate core (else the city's first district's), and its name."""
    from shapely.geometry import Polygon
    ds = sorted(m["districts"], key=lambda d: (d.get("archetype") != "corporate_core", d["id"]))
    d = ds[0]
    g = Polygon(d["polygon"]["exterior"])
    c = g.representative_point()
    return c.x, c.y, d.get("name") or d["id"]


def lux_preview(build, plan=None, out=None, size_m: float = 600.0, cell_m: float = 1.0,
                hour: float = CHECK_HOUR, city=None) -> dict:
    """`preview_lux.png`: the plan's illuminance on the ground (with occlusion) round the
    corporate core, its contours at 2 and 10 lx, the buildings dark, and the check's
    result for the whole city under it (from the plan's `checks`)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    from .plan import City
    build = Path(build)
    pdir = Path(plan) if plan else build / "atmos"
    pl = json.loads((pdir / "atmos_plan.json").read_text(encoding="utf-8"))
    city = city or City(build)
    m = city.m
    cx, cy, name = _core(m)
    x0, y0 = cx - size_m / 2.0, cy - size_m / 2.0
    n = int(round(size_m / cell_m))
    lights = []
    for t in pl["tiles"]:
        ix, iy = int(t["tile"][1:4]), int(t["tile"][4:7])
        if (ix + 1) * 256.0 < x0 - 150 or ix * 256.0 > x0 + size_m + 150 or \
                (iy + 1) * 256.0 < y0 - 150 or iy * 256.0 > y0 + size_m + 150:
            continue
        lights += json.loads((pdir / t["file"]).read_text(encoding="utf-8"))["lights"]
    xs = x0 + (np.arange(n) + 0.5) * cell_m
    ys = y0 + (np.arange(n) + 0.5) * cell_m
    gx, gy = np.meshgrid(xs, ys)
    gz = city.ground_many(gx.ravel(), gy.ravel()).reshape(n, n) + 0.05
    occ = city.occluders()
    E = illuminance(lights, x0, y0, n, cell_m, hour, pl["schedules"], occ, gz)
    fig = plt.figure(figsize=(10, 10.6), dpi=150)
    ax = fig.add_axes([0.04, 0.08, 0.92, 0.86])
    im = ax.imshow(np.maximum(E, 0.05), origin="lower", cmap="inferno",
                   norm=LogNorm(vmin=0.1, vmax=200.0),
                   extent=[x0, x0 + size_m, y0, y0 + size_m])
    for b in m.get("buildings", []):
        fp = b.get("footprint") or {}
        ex = fp.get("exterior") or []
        if len(ex) < 3:
            continue
        bx = [p[0] for p in ex]
        by = [p[1] for p in ex]
        if max(bx) < x0 or min(bx) > x0 + size_m or max(by) < y0 or min(by) > y0 + size_m:
            continue
        ax.fill(bx, by, color="#1c2333", lw=0)
    ax.contour(xs, ys, E, levels=[2.0, 10.0], colors=["#5ad0ff", "#ffffff"], linewidths=0.4)
    ax.set_xlim(x0, x0 + size_m)
    ax.set_ylim(y0, y0 + size_m)
    ax.set_title(f"{pl['city']}: the plan's light on the ground round {name} at "
                 f"{hour:g}:00, lux, with occlusion (contours 2 and 10 lx)", fontsize=9)
    cb = fig.add_axes([0.2, 0.035, 0.6, 0.015])
    fig.colorbar(im, cax=cb, orientation="horizontal")
    res = (pl.get("checks") or {}).get("lux") or {}
    txt = "; ".join(f"{c} avg {s['average_lx']:g} lx (target {s['target_average_lx']:g}), "
                    f"{100 * s['under_min']:.1f}% under {s['target_min_lx']:g}"
                    for c, s in (res.get("classes") or {}).items() if s.get("judged"))
    fig.text(0.5, 0.005, (f"the city: {'PASS' if res.get('ok') else 'FAIL'}; " if res else "")
             + txt, ha="center", fontsize=6.0)
    dest = Path(out) if out else pdir / "preview_lux.png"
    fig.savefig(dest)
    plt.close(fig)
    return {"image": str(dest), "district": name, "center": [round(cx, 1), round(cy, 1)],
            "size_m": size_m, "cell_m": cell_m, "lights": len(lights), "hour": hour,
            "max_lx": round(float(E.max()), 1), "check": res.get("ok")}


KIND_COLORS = {"street_light": "#ffd27a", "wall_light": "#ff9a3d", "sign": "#ff2a6d",
               "shop_sign": "#b967ff", "spill": "#05d9e8", "signal": "#ff4040",
               "corner": "#ffffff", "road": "#ffe066", "alley": "#c08040",
               "soffit": "#9fd8ff", "tunnel": "#80ff80", "underpass": "#80ff80",
               "station": "#40c0ff", "neon": "#39ff8a", "flood": "#f2f6ff",
               "aviation": "#ff200a", "searchlight": "#ffffff", "high_mast": "#ffb35c",
               "runway": "#2a5cff"}


def plan_map(build, plan=None, out=None) -> dict:
    """`preview_plan.png`: every light of the plan over the districts, by kind (broken ones
    grey), the city at a glance."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    build = Path(build)
    pdir = Path(plan) if plan else build / "atmos"
    pl = json.loads((pdir / "atmos_plan.json").read_text(encoding="utf-8"))
    m = json.loads((build / "city_model.json").read_text(encoding="utf-8"))
    pts: dict[str, list] = {}
    for t in pl["tiles"]:
        for L in json.loads((pdir / t["file"]).read_text(encoding="utf-8"))["lights"]:
            pts.setdefault(L["kind"] if L["on"] else "broken", []).append(L["pos"][:2])
    x0, y0, x1, y1 = m["bounds"]
    fig = plt.figure(figsize=(10, 10.4), dpi=200)
    ax = fig.add_axes([0.02, 0.05, 0.96, 0.9])
    ax.set_facecolor("#05070d")
    for d in m["districts"]:
        ex = d["polygon"]["exterior"]
        ax.fill([p[0] for p in ex], [p[1] for p in ex], color="#111827", lw=0.4,
                ec="#2a3550")
    order = ("spill", "shop_sign", "neon", "sign", "wall_light", "street_light", "alley",
             "road", "signal", "corner", "soffit", "tunnel", "underpass", "station",
             "high_mast", "runway", "flood", "searchlight", "aviation", "broken")
    for k in order + tuple(sorted(set(pts) - set(order))):
        if k not in pts:
            continue
        a = np.array(pts[k])
        ax.scatter(a[:, 0], a[:, 1], s=0.15 if k in ("spill", "shop_sign") else 0.35,
                   c=KIND_COLORS.get(k, "#555555"), lw=0,
                   label=f"{k.replace('_', ' ')} ({len(a)})")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    leg = ax.legend(loc="lower left", fontsize=7, markerscale=12, facecolor="#0b0f1a",
                    labelcolor="#d8deea", framealpha=0.9)
    leg.get_frame().set_edgecolor("#2a3550")
    ax.set_title(f"{pl['city']}: the atmos plan's {pl['counts']['all']} lights by kind "
                 f"({pl['preset']}, {pl['hour']:g}:00)", fontsize=9, color="#d8deea")
    dest = Path(out) if out else pdir / "preview_plan.png"
    fig.savefig(dest, facecolor="#05070d")
    plt.close(fig)
    return {"image": str(dest), "kinds": {k: len(v) for k, v in pts.items()}}
