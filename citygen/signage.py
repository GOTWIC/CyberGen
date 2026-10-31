"""M20: the large ads on the sides and tops of the buildings (scope section 12, M20), as sign
slots for stages 2 and 3 to fill, placed per district by its `signage` (density and kinds;
the archetype's by default, `presets.ArchetypePreset.signage`):

| slot | kind, mount | where |
|---|---|---|
| neon billboard | `billboard`, `facade` | landscape or portrait (`attrs.orientation`), on the facades of mid-rises (15 m and taller) and towers that face a highway, avenue, street or plaza, at levels every `LEVEL_M` up a tall facade |
| neon banner | `banner`, `facade` | a vertical strip spanning `BANNER_FLOORS` floors at a corner of a facade; where the facade round the corner is open too, a second face there (`attrs.wrap`: each names the other) |
| holo-board | `holo_ad`, `roof` | over a tower roof (as M11's holo-ads, more of them) |
| holo-board | `holo_ad`, `front` | projected `HOLO_OFF_M` in front of a tower's facade, high up |

Every billboard and banner is lit as neon (`attrs.lit`), and so are M3's roof billboards
(`gameplay.build_sign_slots`). Shop signs and the neon bands over shops stay M11's.

A facade is an edge of a building mass whose faces are vertical and plane (M21): a prism
mass of any role but the bands of twisted, tapered and leaning shafts (each band is the
shaft's plate turned and scaled a few floors at a time, so their faces step) and the thin
parts (frames, columns, struts, halos, masts, pods, links); the edge at least `BANNER_W_M[0]`
long and off the mass's arcs (a curve's chords are plane but short and turned). It faces a
road when one of the classes it needs is within reach of a point `PROBE_M` out (a plaza: the
point within `PLAZA_M` of one), and an ad on it is open when nothing (another mass, a
skybridge, a transit structure, a raised road, a deck slab) stands within `OPEN_M` in front
of it over its height (a holo-board: round its image, `HOLO_OFF_M` out). The ads keep above
the shop signs (and 10 m up at least), off the floors a skybridge lands on, apart from each
other and from the neon band on their building. Randomness is a hash of the building's id
and the facade (`props._u`), so a building's ads do not depend on the order of anything
else. Heights are in the building's frame (M13: over its base, as the masses).
"""

from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import geom as G
from . import presets
from .ids import tok
from .props import _u

q = G.q

KINDS = ("billboard", "banner", "holo")
SKIP_ROLES = ("void", "band", "frame", "column", "strut", "halo", "mast", "pod", "link",
              "spire", "leg", "ramp", "dock", "span")
THIN_ROLES = ("mast", "spire", "halo", "strut", "frame", "column")   # (not a roof)
PROBE_M = 6.0            # a facade looks at what is this far in front of it
FACE_REACH_M = {"highway": 45.0, "avenue": 45.0, "street": 30.0, "pedestrian": 25.0}
FACE_WEIGHT = {"highway": 1.0, "avenue": 1.0, "plaza": 0.9, "street": 0.75,
               "pedestrian": 0.6}
PLAZA_KINDS = ("plaza", "market", "promenade", "park", "pocket_park")
PLAZA_M = 25.0
OPEN_M = 3.0             # nothing this close in front of an ad over its height
MIN_Z_M = 10.0           # every large ad starts this high at least (over the shop signs)
SIGN_GAP_M = 0.5         # (and this far over the shop signs)
TOP_GAP_M = 1.5          # it ends this far under its mass's top
MIDRISE_M = 15.0         # billboards on buildings this tall and taller
LEVEL_M = 30.0           # one level of billboards for every this much facade height
BILLBOARD_P = 0.7        # a level's share with a billboard: this times density and facing
LANDSCAPE_W_M = (8.0, 32.0)
LANDSCAPE_ASPECT = 0.5   # height over width
PORTRAIT_W_M = (5.0, 12.0)
PORTRAIT_ASPECT = 1.6
PORTRAIT_SHARE = 0.35
BANNER_MIN_M = 18.0      # banners on buildings this tall and taller
BANNER_P = (0.1, 0.45)   # (the share of them: the first plus the second times density)
BANNER_W_M = (2.4, 4.0)
BANNER_FLOORS = (3, 10)
CORNER_GAP_M = 0.3       # a banner's outer edge this far from its corner
WRAP_TURN_DEG = 60.0     # a banner wraps a corner turning at least this much
GAP_M = 1.0              # between two ads on one facade
HOLO_ROOF_M = 50.0       # holo-boards over the roofs of towers this tall
HOLO_ROOF_P = (0.05, 0.25)   # (the share of them: the first plus the second times density)
HOLO_FRONT_M = 40.0      # and in front of the facades of towers this tall
HOLO_FRONT_P = (0.0, 0.25)
HOLO_OFF_M = 3.0         # the image this far in front of its facade
HOLO_W_M = (8.0, 24.0)
HOLO_ASPECT = 0.6
HOLO_CLEAR_M = 1.5       # nothing within this of a holo-board's image


def roof_of(b):
    """A building's roof: its highest mass that is not a thin part (a mast or spire, a halo
    and its struts, frames, columns)."""
    body = [ms for ms in b.masses if ms.role not in THIN_ROLES and ms.role != "void"]
    return max(body or b.masses, key=lambda ms: (ms.z1_m, -ms.z0_m))


def params(d) -> tuple[float, tuple[str, ...]]:
    """A district's (density, kinds): its spec `signage`, else its archetype's."""
    s = (d.params or {}).get("signage") if d is not None else None
    pre = presets.ARCHETYPES.get(d.archetype) if d is not None else None
    dens = float(pre.signage) if pre is not None else 0.4
    kinds = tuple(pre.signage_kinds) if pre is not None else KINDS
    if s:
        if s.get("density") is not None:
            dens = float(s["density"])
        if s.get("kinds") is not None:
            kinds = tuple(s["kinds"])
    return dens, kinds


class Obstacles:
    """What stands in the air an ad must keep clear of, as plan shapes with an absolute z
    range (M13: masses over their building's base, the rest over the ground)."""

    def __init__(self, m):
        from . import terrain as TE

        gf = TE.ground_of(m)
        P = G.from_model_poly
        polys, self.rows = [], []      # (z0, z1, building id, mass index) or (z0, z1)

        def g(x, y):
            return gf.at(x, y) if gf is not None else 0.0
        for b in m.buildings:
            base = b.base_m if (b.base_m is not None and gf is not None) else 0.0
            for j, ms in enumerate(b.masses):
                if ms.role == "void":
                    continue
                polys.append(P(ms.footprint))
                self.rows.append((base + ms.z0_m, base + ms.z1_m, b.id, j))
        for sb in m.skybridges:
            base = sb.base_m if (sb.base_m is not None and gf is not None) else 0.0
            polys.append(LineString(sb.line).buffer(sb.width_m / 2.0, cap_style="flat"))
            self.rows.append((base + sb.z_m - 1.0,
                              base + sb.z_m + sb.levels * sb.level_height_m, None, -1))
        for s in m.structures:
            a = s.attrs or {}
            if s.kind in ("retaining_wall", "embankment") or s.z1_m <= 0.5:
                continue
            if len(s.line) >= 2:
                line = LineString([p[:2] for p in s.line])
                c = line.interpolate(0.5, normalized=True)
                polys.append(line.buffer(a.get("width_m", 4.0) / 2.0 + 0.5,
                                         cap_style="flat"))
                self.rows.append((g(c.x, c.y) + s.z0_m, g(c.x, c.y) + s.z1_m, None, -1))
            elif s.footprint is not None:
                fp = P(s.footprint)
                c = fp.centroid
                polys.append(fp)
                self.rows.append((g(c.x, c.y) + s.z0_m, g(c.x, c.y) + s.z1_m, None, -1))
        for dk in m.decks:
            fp = P(dk.polygon)
            polys.append(fp)
            self.rows.append((dk.top_m - dk.slab_m, dk.top_m + 1.2, None, -1))
        for s in m.road_segments:
            zs = [z.z for z in s.z_profile]
            if not zs or max(zs) <= 0.5 or len(s.centerline) < 2:
                continue
            line = LineString(s.centerline)
            c = line.interpolate(0.5, normalized=True)
            polys.append(line.buffer(s.width_m / 2.0, cap_style="flat"))
            self.rows.append((g(c.x, c.y) + min(zs) - 1.8, g(c.x, c.y) + max(zs) + 1.2, None,
                              -1))
        self.polys = np.array(polys, dtype=object)
        self.tree = shapely.STRtree(polys) if polys else None

    def hit(self, geom, z0: float, z1: float, own: tuple | None = None) -> bool:
        """Whether anything but `own` (a building id and mass index) meets the shape
        between z0 and z1 (absolute)."""
        if self.tree is None:
            return False
        for k in self.tree.query(geom, predicate="intersects").tolist():
            lo, hi, bid, j = self.rows[k]
            if own is not None and (bid, j) == own:
                continue
            if lo < z1 - 0.01 and hi > z0 + 0.01:
                return True
        return False


def _edges(ring):
    """A footprint ring's edges, counterclockwise: (a, b, length, (ux, uy), outward normal)."""
    pts = [(float(x), float(y)) for x, y in ring]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    area2 = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    if area2 < 0:
        pts = pts[::-1]
    out = []
    for a, b in zip(pts, pts[1:] + pts[:1]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L > 1e-6:
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            out.append((a, b, L, (ux, uy), (uy, -ux)))
    return out


def _on_arc(ms, a, b) -> bool:
    """Whether an edge is a chord of one of the mass's arcs (both ends on its circle)."""
    for arc in ms.arcs:
        cx, cy = arc.center[0], arc.center[1]
        r = arc.radius_m
        if all(abs(math.hypot(p[0] - cx, p[1] - cy) - r) < 0.03 for p in (a, b)):
            return True
    return False


class Facade:
    """One plane face of a building mass that faces a road or plaza; what its ads take is
    kept per plane (`used`, shared by the faces of the building's masses on one plane, in
    s along the plane: an edge's t plus `s0`)."""

    def __init__(self, j, ms, i, a, b, L, u, n, face, sid, aud, planes: dict):
        self.j, self.ms, self.i = j, ms, i
        self.a, self.b, self.L, self.u, self.n = a, b, L, u, n
        self.face, self.sid, self.aud = face, sid, aud
        key = (round(n[0], 3) + 0.0, round(n[1], 3) + 0.0,
               round(a[0] * n[0] + a[1] * n[1], 1) + 0.0)
        self.used: list[tuple] = planes.setdefault(key, [])   # (s0, s1, z0, z1), taken
        self.s0 = a[0] * u[0] + a[1] * u[1]

    def point(self, t: float, out: float = 0.0) -> tuple[float, float]:
        return (self.a[0] + self.u[0] * t + self.n[0] * out,
                self.a[1] + self.u[1] * t + self.n[1] * out)

    def free(self, t0: float, t1: float, z0: float, z1: float) -> bool:
        s0, s1 = self.s0 + t0, self.s0 + t1
        return all(s1 + GAP_M <= a or s0 - GAP_M >= b or z1 + GAP_M <= c or z0 - GAP_M >= d
                   for a, b, c, d in self.used)

    def take(self, t0: float, t1: float, z0: float, z1: float) -> None:
        self.used.append((self.s0 + t0, self.s0 + t1, z0, z1))


class Placer:
    """The context of a city's large ads: roads, plazas, obstacles, audiences."""

    def __init__(self, m, dens: dict, audience):
        self.m = m
        self.dens = dens
        self.audience = audience
        self.segs = [s for s in m.road_segments if len(s.centerline) >= 2]
        lines = [LineString(s.centerline) for s in self.segs]
        self.sgeo = np.array(lines, dtype=object)
        self.stree = shapely.STRtree(lines) if lines else None
        plaza = [G.from_model_poly(o.polygon) for o in m.open_spaces
                 if o.kind in PLAZA_KINDS and o.z_m <= 0.5]
        self.ptree = shapely.STRtree(plaza) if plaza else None
        self.obst = Obstacles(m)
        self.dist = {d.id: d for d in m.districts}
        from . import terrain as TE

        self.gf = TE.ground_of(m)

    def facing(self, x: float, y: float) -> tuple[str, str | None, float] | None:
        """What a facade whose probe point is (x, y) faces: (class, road id, audience), the
        best of the roads and plazas there; None when it faces nothing."""
        best = None
        p = Point(x, y)
        if self.stree is not None:
            reach = max(FACE_REACH_M.values())
            idx = np.sort(self.stree.query(p, predicate="dwithin", distance=reach))
            if len(idx):
                d = np.round(shapely.distance(self.sgeo[idx], p), G.DIST_DIGITS)
                for k, dd in zip(idx.tolist(), d.tolist()):
                    s = self.segs[k]
                    cls = s.road_class
                    if cls not in FACE_REACH_M or dd > FACE_REACH_M[cls]:
                        continue
                    key = (FACE_WEIGHT[cls], -dd, -k)
                    if best is None or key > best[0]:
                        best = (key, cls, s.id)
        if self.ptree is not None and len(self.ptree.query(p, predicate="dwithin",
                                                           distance=PLAZA_M)):
            key = (FACE_WEIGHT["plaza"], 0.0, 0)
            if best is None or key > best[0]:
                best = (key, "plaza", best[2] if best is not None else None)
        if best is None:
            return None
        sid = best[2]
        if sid is None and self.stree is not None:
            idx = np.sort(self.stree.query(p, predicate="dwithin", distance=60.0))
            if len(idx):
                d = np.round(shapely.distance(self.sgeo[idx], p), G.DIST_DIGITS)
                sid = self.segs[int(idx[int(np.argmin(d))])].id
        return best[1], sid, self.audience(self.dens.get(sid))

    def base(self, b) -> float:
        return b.base_m if (b.base_m is not None and self.gf is not None) else 0.0

    def facades(self, b) -> list[Facade]:
        out = []
        planes: dict = {}
        for j, ms in enumerate(b.masses):
            if ms.shape != "prism" or ms.role in SKIP_ROLES:
                continue
            for i, (a, bb, L, u, n) in enumerate(_edges(G.from_model_poly(
                    ms.footprint).exterior.coords)):
                if L < BANNER_W_M[0] + 2 * CORNER_GAP_M or _on_arc(ms, a, bb):
                    continue
                mx, my = (a[0] + bb[0]) / 2.0, (a[1] + bb[1]) / 2.0
                f = self.facing(mx + n[0] * PROBE_M, my + n[1] * PROBE_M)
                if f is None:
                    continue
                out.append(Facade(j, ms, i, a, bb, L, u, n, *f, planes))
        out.sort(key=lambda f: (-FACE_WEIGHT[f.face], -f.aud, -round(f.L, 4),
                                f.a, f.b, f.ms.z0_m))
        return out

    def open(self, b, f: Facade, t0: float, t1: float, z0: float, z1: float,
             out: tuple = (0.6, OPEN_M)) -> bool:
        """Whether the strip in front of a facade from t0 to t1 along it, out to OPEN_M, is
        clear over z0 to z1 (the building's frame); its own mass too (a face into a notch of
        its footprint looks at its own wall)."""
        base = self.base(b)
        strip = shapely.Polygon([f.point(t0, out[0]), f.point(t1, out[0]),
                                 f.point(t1, out[1]), f.point(t0, out[1])])
        return not self.obst.hit(strip, base + z0, base + z1)


def _row(b, kind: str, mount: str, x: float, y: float, z: float, yaw: float, w: float,
         h: float, sid, aud: float, content: str, attrs: dict, two: bool = False) -> dict:
    return {"id": f"{b.id}.slot.{kind}.{tok(x, y)}.z{int(math.floor(z + 0.5))}",
            "type": f"sign_slot.{kind}", "kind": kind, "mount": mount, "building_id": b.id,
            "prop_id": None, "roof_item": None, "position": (q(x), q(y), q(z)),
            "yaw_deg": yaw, "width_m": q(w), "height_m": q(h), "emitter": True,
            "two_sided": two, "content": content, "segment_id": sid, "audience": aud,
            "attrs": attrs}


def _yaw(nx: float, ny: float) -> float:
    from . import dmath as M

    return round(M.degrees(M.atan2(ny, nx)), 1) + 0.0


def place(pl: Placer, b, lo_of: float, sky_clear, band, corp: bool) -> list[dict]:
    """A building's large ads (see the module docstring): `lo_of` the lowest z an ad may
    start at (over the shop signs), `sky_clear(a, b, z0, z1)` whether an edge's stretch is
    clear of skybridge landings, `band` the neon band's (edge point a, b, z0, z1) or None."""
    d = pl.dist.get(b.district_id)
    dens, kinds = params(d)
    if dens <= 0.0 or not kinds:
        return []
    floor0 = float(b.attrs.get("deck_top_m", 0.0)) if b.level else 0.0
    top = max(ms.z1_m for ms in b.masses) - floor0
    if top < MIDRISE_M:
        return []
    fs = pl.facades(b)
    if not fs:
        return []
    fh = b.floor_height_m or 3.5
    out: list[dict] = []
    content = "corporate" if corp else "ad"
    if band is not None:
        ba, bb, z0, z1 = band
        for f in fs:
            if f.a == ba and f.b == bb:
                f.take(0.0, 2.2, z0, z1)

    def span(f: Facade) -> tuple[float, float]:
        return max(lo_of, f.ms.z0_m + 1.0, floor0 + MIN_Z_M), f.ms.z1_m - TOP_GAP_M

    # vertical banners at facade corners (a pair where one wraps the corner)
    if "banner" in kinds and top >= BANNER_MIN_M and (
            _u("banner", b.id) < BANNER_P[0] + BANNER_P[1] * dens):
        want = 1 + (1 if _u("banner2", b.id) < dens * 0.5 else 0)
        made = 0
        for f in fs:
            if made >= want:
                break
            z0, z1 = span(f)
            k = BANNER_FLOORS[0] + int(_u("bfl", b.id, f.i) *
                                       (BANNER_FLOORS[1] - BANNER_FLOORS[0] + 1))
            h = min(k * fh, z1 - z0)
            if h < BANNER_FLOORS[0] * fh:
                continue
            k = int(h / fh + 0.5)     # (the floors it spans, under its mass's top)
            w = q(min(BANNER_W_M[1], max(BANNER_W_M[0], 0.18 * f.L)))
            end = 1 if _u("bend", b.id, f.i) < 0.5 else 0
            t0 = f.L - CORNER_GAP_M - w if end else CORNER_GAP_M
            t1 = t0 + w
            if not f.free(t0, t1, z0, z0 + h) or not sky_clear(f.a, f.b, z0, z0 + h) or \
                    not pl.open(b, f, t0, t1, z0, z0 + h):
                continue
            x, y = f.point((t0 + t1) / 2.0)
            zc = z0 + h / 2.0
            first = _row(b, "banner", "facade", x, y, zc, _yaw(*f.n), w, h, f.sid, f.aud,
                         content, {"edge": f.i, "lit": "neon", "floors": k})
            # round the corner: the facade at the same corner of the same mass
            corner = f.b if end else f.a
            pair = None
            for g in fs:
                if g is f or g.ms is not f.ms or (g.a if end else g.b) != corner:
                    continue
                turn = abs(math.degrees(math.atan2(f.n[0] * g.n[1] - f.n[1] * g.n[0],
                                                   f.n[0] * g.n[0] + f.n[1] * g.n[1])))
                if turn < WRAP_TURN_DEG or g.L < w + 2 * CORNER_GAP_M:
                    continue
                u0 = CORNER_GAP_M if end else g.L - CORNER_GAP_M - w
                if g.free(u0, u0 + w, z0, z0 + h) and sky_clear(g.a, g.b, z0, z0 + h) and \
                        pl.open(b, g, u0, u0 + w, z0, z0 + h):
                    gx, gy = g.point(u0 + w / 2.0)
                    pair = (g, u0, _row(b, "banner", "facade", gx, gy, zc, _yaw(*g.n), w, h,
                                        g.sid, g.aud, content,
                                        {"edge": g.i, "lit": "neon", "floors": k}))
                break
            f.take(t0, t1, z0, z0 + h)
            if pair is not None:
                g, u0, second = pair
                g.take(u0, u0 + w, z0, z0 + h)
                # (the pair named after the first face: round a sharp corner both can stand
                # in one 1 m cell)
                second["id"] = first["id"] + ".b"
                first["id"] += ".a"
                first["attrs"]["wrap"] = second["id"]
                second["attrs"]["wrap"] = first["id"]
                out += [first, second]
            else:
                out.append(first)
            made += 1
    # neon billboards, a level for every LEVEL_M of a facade's height
    if "billboard" in kinds:
        cap = 2 + int(top / 25.0)
        n = 0
        for f in fs:
            z0, z1 = span(f)
            if z1 - z0 < LANDSCAPE_W_M[0] * LANDSCAPE_ASPECT:
                continue
            levels = max(1, int((z1 - z0) / LEVEL_M))
            p = BILLBOARD_P * dens * FACE_WEIGHT[f.face]
            for lv in range(levels):
                if n >= cap:
                    break
                if _u("bb", b.id, f.i, f.ms.z0_m, lv) >= p:
                    continue
                portrait = f.L < 14.0 or _u("bbp", b.id, f.i, lv) < PORTRAIT_SHARE
                if portrait:
                    w = min(max(0.35 * f.L, PORTRAIT_W_M[0]), PORTRAIT_W_M[1], f.L - 2.0)
                    h = w * PORTRAIT_ASPECT
                else:
                    w = min(max(0.55 * f.L, LANDSCAPE_W_M[0]), LANDSCAPE_W_M[1], f.L - 2.0)
                    h = w * LANDSCAPE_ASPECT
                if w < PORTRAIT_W_M[0]:
                    continue
                lz0 = z0 + (z1 - z0) * lv / levels
                lz1 = z0 + (z1 - z0) * (lv + 1) / levels
                if h > lz1 - lz0:
                    h = lz1 - lz0
                    w = h / (PORTRAIT_ASPECT if portrait else LANDSCAPE_ASPECT)
                    if w < PORTRAIT_W_M[0] or w > f.L - 2.0:
                        continue
                w, h = q(w), q(h)
                zc = q(lz0 + (lz1 - lz0) * (0.35 + 0.3 * _u("bbz", b.id, f.i, lv)))
                zc = min(max(zc, lz0 + h / 2.0), lz1 - h / 2.0)
                tc = f.L / 2.0
                if not f.free(tc - w / 2.0, tc + w / 2.0, zc - h / 2.0, zc + h / 2.0):
                    # (beside a banner or the band: the facade's other half)
                    tc = f.L - w / 2.0 - 1.0 if _u("bbs", b.id, f.i) < 0.5 else w / 2.0 + 1.0
                    if not f.free(tc - w / 2.0, tc + w / 2.0, zc - h / 2.0, zc + h / 2.0):
                        continue
                if not sky_clear(f.a, f.b, zc - h / 2.0, zc + h / 2.0) or \
                        not pl.open(b, f, tc - w / 2.0, tc + w / 2.0, zc - h / 2.0,
                                    zc + h / 2.0):
                    continue
                x, y = f.point(tc)
                f.take(tc - w / 2.0, tc + w / 2.0, zc - h / 2.0, zc + h / 2.0)
                out.append(_row(b, "billboard", "facade", x, y, zc, _yaw(*f.n), w, h, f.sid,
                                f.aud, content,
                                {"edge": f.i, "lit": "neon",
                                 "orientation": "portrait" if portrait else "landscape"}))
                n += 1
    # a holo-board projected in front of a tower's facade, high up
    if "holo" in kinds and top >= HOLO_FRONT_M and (
            _u("holof", b.id) < HOLO_FRONT_P[0] + HOLO_FRONT_P[1] * dens):
        for f in fs:
            if f.face not in ("highway", "avenue", "plaza") or f.L < HOLO_W_M[0]:
                continue
            z0, z1 = span(f)
            w = min(max(0.5 * f.L, HOLO_W_M[0]), HOLO_W_M[1])
            h = w * HOLO_ASPECT
            if z1 - z0 < h + 4.0:
                continue
            w, h = q(w), q(h)
            zc = q(z1 - 2.0 - h / 2.0)
            tc = f.L / 2.0
            x, y = f.point(tc, HOLO_OFF_M)
            img = LineString([f.point(tc - w / 2.0, HOLO_OFF_M),
                              f.point(tc + w / 2.0, HOLO_OFF_M)]).buffer(HOLO_CLEAR_M)
            base = pl.base(b)
            if pl.obst.hit(img, base + zc - h / 2.0 - HOLO_CLEAR_M,
                           base + zc + h / 2.0 + HOLO_CLEAR_M):
                continue
            if not sky_clear(f.a, f.b, zc - h / 2.0, zc + h / 2.0):
                continue
            out.append(_row(b, "holo_ad", "front", x, y, zc, _yaw(*f.n), w, h, f.sid,
                            f.aud, content, {"edge": f.i, "off_m": HOLO_OFF_M}, two=True))
            break
    return out
