"""M6: props and ground clutter (scope 5.6), with the placement machinery the vegetation
(`vegetation.py`, scope 5.8) shares. Runs last, on the city with its buildings and transit.

Every generator proposes candidates (kind, position, yaw, ground radius, the keep-outs that
apply); the keep-outs are tested in bulk against the model (lanes, crosswalks, junctions,
buildings, water, entrances and driveways, ground structures, park paths, quay edges, the
sidewalk clear path); then the survivors are accepted one by one in a fixed order when they
overlap nothing placed before them. Randomness is a hash of the element's ids (`_u`), so the
result does not depend on the order of anything but the candidates themselves.

| kind | where |
|---|---|
| street_light | sidewalk furniture zone, every 25 to 35 m, staggered across the street |
| traffic_signal | both ends of every crosswalk at a signalized junction |
| trash_can | beside crosswalks, bus stops, benches |
| bus_stop (shelter) | avenues and wide streets, every 350 m on each side |
| hydrant | sidewalk furniture zone, every 100 m |
| bollard | across both ends of pedestrian streets |
| bench | park paths, plazas, quays, bus stops |
| kiosk, vending_machine | plazas, station feet |
| food_stall | markets (rows), plazas and quays of market and entertainment districts |
| planter | plazas, pedestrian streets |
| parked_vehicle | parking lanes |
| boat | quays of canals, basins and marinas |
| barrier | jersey barriers along highway medians; railings along quay edges |
| overhead_cable | across alleys and narrow streets, by grime |
| sign, awning | ground-floor units (signs also by neon) |
| ac_unit | street facades of residential and old buildings, by grime |
| scaffolding | a few buildings |
| gate | market entrances |
| dumpster | building backs along alleys and service lanes |
| trash | bags, boxes and cans in alleys and on sidewalks, by grime |
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import dmath as M
from . import geom as G

q = G.q

# ground radius (overlap), blockout size (along, across, up)
KINDS = {
    "street_light": (0.3, (0.3, 0.3, 8.0)),
    "wall_light": (None, (0.4, 0.8, 0.4)),
    "traffic_signal": (0.3, (0.3, 0.3, 5.5)),
    "trash_can": (0.35, (0.6, 0.6, 0.9)),
    "bus_stop": (2.2, (4.0, 1.4, 2.6)),
    "hydrant": (0.3, (0.35, 0.35, 0.8)),
    "bollard": (0.15, (0.2, 0.2, 0.9)),
    "bench": (0.9, (1.8, 0.6, 0.5)),
    "kiosk": (1.4, (2.2, 2.2, 2.8)),
    "vending_machine": (0.7, (1.0, 0.8, 1.9)),
    "food_stall": (1.9, (3.0, 2.0, 2.6)),
    "planter": (0.85, (1.2, 1.2, 0.7)),
    "parked_vehicle": (2.4, (4.6, 1.9, 1.5)),
    "boat": (4.3, (8.0, 3.0, 2.0)),
    "barrier": (None, (4.0, 0.6, 0.9)),
    "railing": (None, (3.0, 0.1, 1.1)),
    "overhead_cable": (None, (1.0, 0.05, 0.05)),
    "sign": (None, (0.2, 1.2, 1.8)),
    "awning": (None, (1.0, 1.0, 0.2)),
    "ac_unit": (None, (1.0, 0.6, 0.8)),
    "scaffolding": (None, (1.0, 1.5, 1.0)),
    "gate": (None, (1.0, 1.0, 6.0)),
    "dumpster": (1.0, (2.0, 1.2, 1.3)),
    "trash": (0.25, (0.5, 0.5, 0.4)),
}

# radius for the keep-out tests where the thing is long and narrow (its half width)
KEEP_R = {"parked_vehicle": 0.95, "bus_stop": 0.7, "bench": 0.35, "food_stall": 1.0,
          "boat": 1.5, "dumpster": 0.6}

# keep-outs (bit flags)
LANE, XWALK, JUNCTION, BUILDING, WATER, ENTRANCE, STRUCT, PATH, QUAY, CLEAR, CARRIAGE = (
    1 << k for k in range(11))
# what every thing on the ground keeps out of (the M6 checks test these), less the exceptions
REQUIRED = LANE | XWALK | JUNCTION | BUILDING | WATER | ENTRANCE | STRUCT | CLEAR
EXCEPT = {"traffic_signal": XWALK, "bollard": JUNCTION}
GROUND = REQUIRED | PATH | QUAY
SIDEWALK = GROUND
PARKED = REQUIRED
LITTER = REQUIRED
CLEAR_PATH_M = 1.8


def _u(*key) -> float:
    """A uniform number in [0, 1) from the key (the same on every machine and process)."""
    h = hashlib.blake2b("|".join(map(str, key)).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 18446744073709551616.0


def yaw_of(ux: float, uy: float) -> float:
    return round(M.degrees(M.atan2(uy, ux)), 1) + 0.0


def walk(line, step: float, start: float = 0.0, end_pad: float = 0.0):
    """Points every `step` m along a polyline from `start` (end_pad short of the end):
    (x, y, ux, uy, s) with the unit direction there."""
    pts = [(float(p[0]), float(p[1])) for p in line]
    out = []
    if len(pts) < 2 or step <= 0:
        return out
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    L = cum[-1]
    s = start
    j = 0
    while s <= L - end_pad + 1e-9:
        while j < len(pts) - 2 and cum[j + 1] < s:
            j += 1
        seg = cum[j + 1] - cum[j]
        if seg > 1e-9:
            f = (s - cum[j]) / seg
            a, b = pts[j], pts[j + 1]
            ux, uy = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, ux, uy, s))
        s += step
    return out


def length(line) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line, line[1:]))


@dataclass
class Cand:
    kind: str
    x: float
    y: float
    z: float = 0.0
    yaw: float = 0.0
    r: float = 0.0               # ground radius (0: not on the ground, no overlap test)
    keep: int = GROUND
    scale: tuple = (1.0, 1.0, 1.0)
    attrs: dict = field(default_factory=dict)
    plant: dict | None = None    # vegetation: height_m, crown_radius_m, species, class


class Ctx:
    """The model's keep-outs as arrays and trees, the district parameters, and the
    occupancy grid of everything accepted so far."""

    def __init__(self, spec, m):
        self.spec, self.m = spec, m
        P = G.from_model_poly
        self.dist = list(m.districts)
        self.dpolys = [P(d.polygon) for d in self.dist]
        self.dtree = shapely.STRtree(self.dpolys)
        self.params = {d.id: d.params for d in self.dist}
        self.arch = {d.id: d.archetype for d in self.dist}
        self.seg = {s.id: s for s in m.road_segments}
        # lanes (driving lanes and connectors)
        self.lanes = [LineString([p[:2] for p in x.centerline]) for x in m.lanes]
        self.lane_pad = np.array([x.width_m / 2.0 for x in m.lanes])
        # crosswalks
        self.xw = [LineString(x.line) for x in m.crosswalks]
        self.xw_pad = np.array([x.width_m / 2.0 + 0.5 for x in m.crosswalks])
        # junction areas, carriageways (between the curbs) of ground roads
        self.junc = [P(j.polygon) for j in m.junctions]
        self.carr, self.carr_pad = [], []
        for s in m.road_segments:
            if s.bridge or s.road_class in ("pedestrian", "footbridge"):
                continue
            cs = s.cross_section
            half = (cs.total_width_m - cs.sidewalk_m[0] - cs.sidewalk_m[1]) / 2.0
            self.carr.append(LineString(s.centerline))
            self.carr_pad.append(max(half, s.width_m / 2.0 if not any(cs.sidewalk_m) else
                                     half))
        self.carr_pad = np.array(self.carr_pad)
        # buildings at the ground, ground structures, site element masses
        self.bld, self.bld_ids = [], []
        for b in m.buildings:
            fp = b.footprint
            polys = [P(ms.footprint) for ms in b.masses if ms.z0_m <= 0.5 and ms.z1_m > 0.5
                     and ms.role != "void"]
            if fp is not None:
                polys.append(P(fp))
            if polys:
                self.bld.append(G.union(polys) if len(polys) > 1 else polys[0])
                self.bld_ids.append(b.id)
        for e in m.site_elements:
            for ms in e.masses:
                if ms.z0_m <= 0.5 and ms.z1_m > 0.5:
                    self.bld.append(P(ms.footprint))
                    self.bld_ids.append(e.id)
        # (M18: an embankment is the fill under its road, which the road's own keep-outs
        # cover; the props on its sidewalks stand on it)
        self.struct = [P(s.footprint) for s in m.structures if s.footprint is not None and
                       s.z0_m <= 0.5 and s.z1_m > 0.0 and s.kind != "embankment"]
        # water (seas, rivers, channels, waterways)
        self.water = [P(p) for e in m.seas for p in e.polygons] + \
            [P(e.polygon) for e in m.rivers] + [P(e.polygon) for e in m.channels] + \
            [P(e.polygon) for e in m.waterways]
        # entrances (driveways wider)
        self.ent, self.ent_pad = [], []
        for b in m.buildings:
            for e in b.entrances:
                self.ent.append(Point(e.position))
                self.ent_pad.append(3.0 if e.kind in ("garage", "loading") else 1.5)
        self.ent_pad = np.array(self.ent_pad)
        # park paths and other ground walkways inside open space
        self.paths = [LineString([p[:2] for p in w.line]) for w in m.walkways
                      if w.kind == "path"]
        self.path_pad = np.array([w.width_m / 2.0 + 0.6 for w in m.walkways
                                  if w.kind == "path"])
        self.quays = [LineString(x.line) for x in m.quays]
        # sidewalks: line, its road centerline, and the clear path
        self.sw = [w for w in m.sidewalks if w.segment_id in self.seg]
        self.sw_lines = [LineString(w.line) for w in self.sw]
        self.sw_road = [LineString(self.seg[w.segment_id].centerline) for w in self.sw]
        self.trees = {}
        for name, geoms in (("lanes", self.lanes), ("xw", self.xw), ("junc", self.junc),
                            ("carr", self.carr), ("bld", self.bld), ("struct", self.struct),
                            ("water", self.water), ("ent", self.ent), ("paths", self.paths),
                            ("quays", self.quays), ("sw", self.sw_lines)):
            self.trees[name] = (shapely.STRtree(geoms) if geoms else None,
                                np.array(geoms, dtype=object))
        self.grid: dict = {}
        # no trees within 3 m of these: station stairs and elevator feet, metro entrances
        # (bus stops join when placed)
        self.no_tree: list = []
        for w in m.walkways:
            if w.kind in ("stairs", "escalator", "elevator"):
                self.no_tree += [(p[0], p[1]) for p in (w.line[0], w.line[-1])
                                 if abs(p[2]) < 0.5]
        for s in m.structures:
            if (s.attrs or {}).get("role") == "metro_entrance" and s.footprint is not None:
                cc = P(s.footprint).centroid
                self.no_tree.append((cc.x, cc.y))

    # -- lookups ---------------------------------------------------------------------------

    def district_of(self, pts: np.ndarray) -> list[str | None]:
        """District id of each point (the first district, in id order, that covers it)."""
        out: list = [None] * len(pts)
        if not len(pts):
            return out
        ip, idist = self.dtree.query(shapely.points(pts), predicate="intersects")
        for i, k in sorted(zip(ip.tolist(), idist.tolist())):
            if out[i] is None:
                out[i] = self.dist[k].id
        return out

    def param(self, did: str | None, key: str, default: float = 0.3) -> float:
        v = (self.params.get(did) or {}).get(key)
        return float(v) if v is not None else default

    # -- keep-outs in bulk -----------------------------------------------------------------

    def _near(self, name: str, pts, radii, pad, mask, sel) -> None:
        tree, geoms = self.trees[name]
        idx = np.nonzero(sel)[0]
        if tree is None or not len(idx):
            return
        pad_arr = np.full(len(geoms), float(pad)) if np.isscalar(pad) else pad
        reach = float(pad_arr.max()) + float(radii[idx].max()) + 0.01
        ip, ig = tree.query(pts[idx], predicate="dwithin", distance=reach)
        if not len(ip):
            return
        d = shapely.distance(pts[idx][ip], geoms[ig])
        bad = d < pad_arr[ig] + radii[idx][ip] - 1e-9
        mask[idx[ip[bad]]] = True

    def _inside(self, name: str, pts, mask, sel) -> None:
        tree, geoms = self.trees[name]
        idx = np.nonzero(sel)[0]
        if tree is None or not len(idx):
            return
        ip, _ = tree.query(pts[idx], predicate="intersects")
        mask[idx[ip]] = True

    def blocked(self, cands: list[Cand]) -> np.ndarray:
        """True for each candidate a keep-out rules out."""
        n = len(cands)
        mask = np.zeros(n, bool)
        if not n:
            return mask
        xy = np.array([(c.x, c.y) for c in cands], dtype=np.float64)
        pts = shapely.points(xy)
        radii = np.array([max(KEEP_R.get(c.kind, c.r), 0.05) for c in cands])
        keep = np.array([c.keep for c in cands], dtype=np.int64)

        def has(flag):
            return (keep & flag) != 0
        self._near("lanes", pts, radii, self.lane_pad, mask, has(LANE))
        self._near("carr", pts, radii, self.carr_pad, mask, has(CARRIAGE))
        self._near("xw", pts, radii, self.xw_pad, mask, has(XWALK))
        self._near("junc", pts, radii, 0.0, mask, has(JUNCTION))
        self._near("bld", pts, radii, 0.3, mask, has(BUILDING))
        self._near("struct", pts, radii, 0.3, mask, has(STRUCT))
        self._near("water", pts, radii, 0.3, mask, has(WATER))
        self._near("ent", pts, radii, self.ent_pad, mask, has(ENTRANCE))
        self._near("paths", pts, radii, self.path_pad, mask, has(PATH))
        self._near("quays", pts, radii, 1.0, mask, has(QUAY))
        sel = has(CLEAR) & ~mask
        if sel.any():
            mask |= ~self.sidewalk_clear(xy, radii, sel)
        return mask

    def sidewalk_clear(self, xy: np.ndarray, radii: np.ndarray, sel=None) -> np.ndarray:
        """True where a round thing of that radius leaves the clear path of every sidewalk it
        stands on: off the sidewalk, or with the clear path (at most 1.8 m) free between it
        and the property line."""
        ok = np.ones(len(xy), bool)
        tree = self.trees["sw"][0]
        idx = np.nonzero(sel)[0] if sel is not None else np.arange(len(xy))
        if tree is None or not len(idx):
            return ok
        pts = shapely.points(xy[idx])
        reach = max(w.width_m for w in self.sw) / 2.0 + float(radii[idx].max()) + 0.01
        ip, ig = tree.query(pts, predicate="dwithin", distance=reach)
        if not len(ip):
            return ok
        lines = self.trees["sw"][1][ig]
        roads = np.array(self.sw_road, dtype=object)[ig]
        p = pts[ip]
        dist = shapely.distance(p, lines)
        width = np.array([self.sw[k].width_m for k in ig.tolist()])
        clear = np.array([self.sw[k].clear_path_m for k in ig.tolist()])
        r = radii[idx][ip]
        on = dist < width / 2.0 + r - 0.01
        if not on.any():
            return ok
        foot = shapely.line_interpolate_point(lines, shapely.line_locate_point(lines, p))
        toward = shapely.distance(foot, roads) - shapely.distance(p, roads)
        o = np.where(toward >= 0.0, dist, -dist)
        need = np.minimum(CLEAR_PATH_M, clear)
        good = (o - r >= -width / 2.0 + need - 0.01) & (o + r <= width / 2.0 + 0.01)
        bad = on & ~good
        ok[idx[ip[bad]]] = False
        return ok

    # -- occupancy -------------------------------------------------------------------------

    def fits(self, c: Cand) -> bool:
        if c.r <= 0:
            return True
        k = (int(math.floor(c.x / 4.0)), int(math.floor(c.y / 4.0)))
        reach = int(math.ceil((c.r + 4.3) / 4.0))
        for i in range(k[0] - reach, k[0] + reach + 1):
            for j in range(k[1] - reach, k[1] + reach + 1):
                for x, y, r in self.grid.get((i, j), ()):
                    if (x - c.x) ** 2 + (y - c.y) ** 2 < (r + c.r) ** 2 - 1e-9:
                        return False
        return True

    def occupy(self, c: Cand) -> None:
        if c.r > 0:
            k = (int(math.floor(c.x / 4.0)), int(math.floor(c.y / 4.0)))
            self.grid.setdefault(k, []).append((c.x, c.y, c.r))

    def place(self, cands: list[Cand]) -> list[Cand]:
        """The candidates no keep-out rules out and that overlap nothing placed before,
        in their order."""
        for c in cands:
            c.x, c.y = q(c.x), q(c.y)
            if c.r > 0:
                need = REQUIRED & ~EXCEPT.get(c.kind, 0)
                assert c.keep & need == need, (c.kind, c.keep)
        mask = self.blocked(cands)
        out = []
        for c, bad in zip(cands, mask.tolist()):
            if bad or not self.fits(c):
                continue
            self.occupy(c)
            out.append(c)
        return out


# ---------------------------------------------------------------------------
# Sidewalk geometry
# ---------------------------------------------------------------------------

def _road_side(w) -> float:
    """+1 when the road is left of the sidewalk line (a right-side sidewalk), else -1."""
    return 1.0 if w.side == "right" else -1.0


def furniture_points(w, step: float, start: float, size: float, end_pad: float = 4.0):
    """Points of the sidewalk's furniture zone (centered in it, or just behind the curb when
    it is narrower than the thing): (x, y, ux, uy, s), or [] when the sidewalk cannot keep
    1.8 m clear beside it."""
    half = w.width_m / 2.0
    zone = max(w.furniture_m, size)
    o = half - w.curb_m - zone / 2.0          # toward the road, from the center line
    if (o - size / 2.0) < -half + min(CLEAR_PATH_M, w.clear_path_m) - 0.01:
        return []
    sgn = _road_side(w)
    out = []
    for x, y, ux, uy, s in walk(w.line, step, start, end_pad):
        nx, ny = -uy * sgn, ux * sgn
        out.append((x + nx * o, y + ny * o, ux, uy, s))
    return out


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def street_lights(c: Ctx) -> list[Cand]:
    """Poles in the furniture zone; where the sidewalk is too narrow for one, a pole just
    behind it (`narrow_lights`)."""
    out = []
    for w in c.sw:
        s = c.seg[w.segment_id]
        L = length(w.line)
        if L < 12.0 or s.road_class in ("footbridge",):
            continue
        step = {"highway": 34.0, "avenue": 28.0, "street": 30.0}.get(s.road_class, 32.0)
        # staggered: the right side starts half a step later
        start = 3.0 + (step / 2.0 if w.side == "right" else 0.0)
        for x, y, ux, uy, _ in furniture_points(w, step, start, 0.3):
            out.append(Cand("street_light", x, y, yaw=yaw_of(-uy * _road_side(w),
                                                               ux * _road_side(w)),
                            r=0.3, keep=SIDEWALK, attrs={"sidewalk": w.id, "emitter": True}))
    return out


def narrow_lights(c: Ctx) -> tuple[list[Cand], list]:
    """For sidewalks with no room for a pole in the furniture zone: poles 0.6 m behind the
    property line (yards, docks), and where a facade stands there, the spots for wall
    lights instead (returned apart, placed after the poles)."""
    poles, spots = [], []
    for w in c.sw:
        s = c.seg[w.segment_id]
        if length(w.line) < 12.0 or s.road_class in ("footbridge",):
            continue
        if furniture_points(w, 1000.0, 0.0, 0.3):
            continue
        step = 24.0
        start = 3.0 + (step / 2.0 if w.side == "right" else 0.0)
        sgn = _road_side(w)
        half = w.width_m / 2.0
        for x, y, ux, uy, sv in walk(w.line, step, start, 4.0):
            nx, ny = -uy * sgn, ux * sgn      # toward the road
            poles.append(Cand("street_light", x - nx * (half + 0.6), y - ny * (half + 0.6),
                              yaw=yaw_of(nx, ny), r=0.3, keep=GROUND,
                              attrs={"sidewalk": w.id, "emitter": True, "behind": True}))
            spots.append((w.id, x - nx * half, y - ny * half, nx, ny))
    return poles, spots


def wall_lights(c: Ctx, spots: list) -> list[Cand]:
    """Lamps on the facade (4.5 m up) at the spots where no pole could stand behind the
    sidewalk, when a facade is within 1 m of the property line."""
    if not spots:
        return []
    near = _facade_hits(c, np.array([(x, y) for _, x, y, _, _ in spots]), 1.0)
    taken = _poles_near(c, spots)
    out = []
    for (wid, x, y, nx, ny), d, t in zip(spots, near.tolist(), taken):
        if d > 1.0 or t:
            continue
        out.append(Cand("wall_light", x - nx * min(d, 1.0) + nx * 0.2,
                        y - ny * min(d, 1.0) + ny * 0.2, z=4.5, yaw=yaw_of(nx, ny), r=0.0,
                        keep=0, attrs={"sidewalk": wid, "emitter": True}))
    return out


def _poles_near(c: Ctx, spots: list) -> list[bool]:
    """Whether a street light already stands within 6 m of each spot."""
    out = []
    for _, x, y, _, _ in spots:
        hit = False
        k = (int(math.floor(x / 4.0)), int(math.floor(y / 4.0)))
        for i in range(k[0] - 2, k[0] + 3):
            for j in range(k[1] - 2, k[1] + 3):
                for px, py, r in c.grid.get((i, j), ()):
                    if abs(r - 0.3) < 1e-9 and (px - x) ** 2 + (py - y) ** 2 < 36.0:
                        hit = True
        out.append(hit)
    return out


def traffic_signals(c: Ctx) -> list[Cand]:
    out = []
    xw = {x.id: x for x in c.m.crosswalks}
    for j in c.m.junctions:
        if not j.signalized:
            continue
        for cid in j.crosswalk_ids:
            x = xw.get(cid)
            if x is None:
                continue
            (ax, ay), (bx, by) = x.line[0], x.line[-1]
            L = math.hypot(bx - ax, by - ay)
            if L < 1.0:
                continue
            ux, uy = (bx - ax) / L, (by - ay) / L
            for px, py, sx in ((ax, ay, -1.0), (bx, by, 1.0)):
                # 1 m back from the curb, beside the crosswalk
                out.append(Cand("traffic_signal", px + ux * sx * 1.0 + uy * (x.width_m / 2 +
                                                                              0.8),
                                py + uy * sx * 1.0 - ux * (x.width_m / 2 + 0.8),
                                yaw=yaw_of(-ux * sx, -uy * sx), r=0.3,
                                keep=SIDEWALK & ~XWALK, attrs={"junction": j.id}))
    return out


def crosswalk_cans(c: Ctx) -> list[Cand]:
    out = []
    for x in c.m.crosswalks:
        (ax, ay), (bx, by) = x.line[0], x.line[-1]
        L = math.hypot(bx - ax, by - ay)
        if L < 1.0 or _u("can", x.id) > 0.45:
            continue
        ux, uy = (bx - ax) / L, (by - ay) / L
        out.append(Cand("trash_can", ax - ux * 1.2 - uy * (x.width_m / 2 + 2.0),
                        ay - uy * 1.2 + ux * (x.width_m / 2 + 2.0), r=0.35, keep=SIDEWALK))
    return out


def hydrants(c: Ctx) -> list[Cand]:
    out = []
    for w in c.sw:
        if length(w.line) < 40.0:
            continue
        start = 20.0 + 60.0 * _u("hyd", w.id)
        for x, y, ux, uy, _ in furniture_points(w, 100.0, start, 0.35, 10.0):
            out.append(Cand("hydrant", x, y, r=0.3, keep=SIDEWALK))
    return out


def bus_stops(c: Ctx) -> list[Cand]:
    """Shelters on avenues and wide streets, every 350 m on each side, with a bench inside
    and a trash can beside."""
    out = []
    for w in c.sw:
        s = c.seg[w.segment_id]
        if s.road_class not in ("avenue", "street") or w.width_m < 4.0:
            continue
        if s.road_class == "street" and s.cross_section.lanes_forward + \
                s.cross_section.lanes_backward < 2:
            continue
        L = length(w.line)
        if L < 60.0:
            continue
        start = 25.0 + 300.0 * _u("bus", w.id)
        for x, y, ux, uy, sv in furniture_points(w, 350.0, start, 1.4, 25.0):
            stop = f"{w.id}.{int(sv)}"
            out.append(Cand("bus_stop", x, y, yaw=yaw_of(ux, uy), r=2.2, keep=SIDEWALK,
                            attrs={"stop": stop}))
            out.append(Cand("trash_can", x + ux * 3.2, y + uy * 3.2, r=0.35, keep=SIDEWALK,
                            attrs={"stop": stop}))
    return out


def bollards(c: Ctx) -> list[Cand]:
    out = []
    junc = {j.node_id: G.from_model_poly(j.polygon) for j in c.m.junctions}
    for s in c.m.road_segments:
        if s.road_class != "pedestrian" or len(s.centerline) < 2:
            continue
        line = LineString(s.centerline)
        L = line.length
        if L < 12.0:
            continue
        for node, t0, sgn in ((s.start, 0.0, 1.0), (s.end, L, -1.0)):
            jp = junc.get(node)
            t = t0
            if jp is not None:
                for k in range(0, int(L / 2)):
                    t = t0 + sgn * (1.0 + k)
                    if not jp.covers(line.interpolate(t)):
                        break
            t = t + sgn * 1.0
            a = line.interpolate(max(0.0, min(L, t - 0.5)))
            b = line.interpolate(max(0.0, min(L, t + 0.5)))
            ux, uy = b.x - a.x, b.y - a.y
            n = math.hypot(ux, uy) or 1.0
            ux, uy = ux / n, uy / n
            p = line.interpolate(max(0.0, min(L, t)))
            half = s.width_m / 2.0 - 0.6
            k = int(half // 1.6)
            for i in range(-k, k + 1):
                out.append(Cand("bollard", p.x - uy * 1.6 * i, p.y + ux * 1.6 * i, r=0.15,
                                keep=GROUND & ~JUNCTION, attrs={"street": s.id}))
    return out


def _open_kind(c: Ctx, kinds) -> list:
    return [o for o in c.m.open_spaces if o.kind in kinds and o.z_m <= 0.5]


def _scatter(poly, spacing: float, key: str, inset: float = 1.5, limit: int = 400):
    """Points on a jittered grid inside the polygon, inset from its edge (deterministic)."""
    x0, y0, x1, y1 = poly.bounds
    inner = poly.buffer(-inset) if inset > 0 else poly
    if inner.is_empty:
        return []
    shapely.prepare(inner)
    out = []
    nx = int((x1 - x0) / spacing) + 1
    ny = int((y1 - y0) / spacing) + 1
    for i in range(nx):
        for j in range(ny):
            jx = (_u(key, i, j, "x") - 0.5) * spacing * 0.8
            jy = (_u(key, i, j, "y") - 0.5) * spacing * 0.8
            x, y = x0 + (i + 0.5) * spacing + jx, y0 + (j + 0.5) * spacing + jy
            if shapely.contains_xy(inner, x, y):
                out.append((x, y, _u(key, i, j, "k")))
                if len(out) >= limit:
                    return out
    return out


def plaza_props(c: Ctx) -> list[Cand]:
    out = []
    for o in _open_kind(c, ("plaza", "promenade", "market", "pocket_park")):
        poly = G.from_model_poly(o.polygon)
        did = o.district_id or c.district_of(np.array([[poly.representative_point().x,
                                                        poly.representative_point().y]]))[0]
        neon = c.param(did, "neon", 0.4)
        arch = c.arch.get(did, "")
        if o.kind == "market":
            for x, y, k in _scatter(poly, 6.0, o.id, 2.0, 300):
                out.append(Cand("food_stall", x, y, yaw=yaw_of(1.0, 0.0), r=1.9,
                                attrs={"emitter": k < neon}))
            continue
        for x, y, k in _scatter(poly, 14.0, o.id, 2.0, 60):
            if k < 0.25:
                out.append(Cand("bench", x, y, yaw=round(360.0 * _u("bench", o.id, x), 1),
                                r=0.9))
            elif k < 0.40:
                out.append(Cand("planter", x, y, r=0.85))
            elif k < 0.48 and o.kind == "plaza":
                out.append(Cand("kiosk", x, y, r=1.4, attrs={"emitter": True}))
            elif k < 0.58 and o.kind == "plaza" and arch in (
                    "entertainment_market", "old_town", "transit_hub", "midtown_mixed"):
                out.append(Cand("food_stall", x, y, yaw=round(360.0 * k, 1), r=1.9,
                                attrs={"emitter": True}))
            elif k < 0.66:
                out.append(Cand("trash_can", x, y, r=0.35))
            elif k < 0.70:
                out.append(Cand("vending_machine", x, y, yaw=round(360.0 * k, 1), r=0.7,
                                attrs={"emitter": True}))
    return out


def park_benches(c: Ctx) -> list[Cand]:
    """Benches beside the park paths, every 30 m (alternating sides), with a trash can at
    every other one."""
    out = []
    for w in c.m.walkways:
        if w.kind != "path":
            continue
        line = [p[:2] for p in w.line]
        if length(line) < 20.0 or _u("pb", w.id) > 0.6:
            continue
        off = w.width_m / 2.0 + 1.4
        for k, (x, y, ux, uy, _) in enumerate(walk(line, 30.0, 10.0, 8.0)):
            sgn = 1.0 if k % 2 == 0 else -1.0
            bx, by = x - uy * off * sgn, y + ux * off * sgn
            out.append(Cand("bench", bx, by, yaw=yaw_of(ux, uy), r=0.9, keep=GROUND & ~PATH,
                            attrs={"path": w.id}))
            if k % 2 == 0:
                out.append(Cand("trash_can", bx + ux * 1.6, by + uy * 1.6, r=0.35,
                                keep=GROUND & ~PATH))
    return out


def quay_props(c: Ctx) -> list[Cand]:
    """Railings along every quay edge, benches 2.5 m inland every 35 m, boats moored at
    canals, basins and marinas."""
    out = []
    ww = {w.id: w for w in c.m.waterways}
    for qy in c.m.quays:
        line = qy.line
        w = ww.get(qy.waterway_id)
        wpoly = G.from_model_poly(w.polygon) if w is not None else None
        for x, y, ux, uy, _ in walk(line, 3.0, 1.5, 1.0):
            out.append(Cand("railing", x, y, z=qy.deck_z_m, yaw=yaw_of(ux, uy), r=0.0,
                            keep=0, attrs={"quay": qy.id}))
        for k, (x, y, ux, uy, _) in enumerate(walk(line, 35.0, 12.0, 8.0)):
            # inland: the side away from the water
            nx, ny = -uy, ux
            if wpoly is not None and shapely.contains_xy(wpoly, x + nx * 3.0, y + ny * 3.0):
                nx, ny = -nx, -ny
            out.append(Cand("bench", x + nx * 2.5, y + ny * 2.5, z=qy.deck_z_m,
                            yaw=yaw_of(ux, uy), r=0.9, keep=GROUND & ~QUAY,
                            attrs={"quay": qy.id}))
            if w is not None and w.kind in ("canal", "basin", "marina") and \
                    _u("boat", qy.id, k) < (0.7 if w.kind == "marina" else 0.35):
                small = w.kind == "canal"
                beam = 2.4 if small else 3.0
                out.append(Cand("boat", x - nx * (beam / 2 + 1.0), y - ny * (beam / 2 + 1.0),
                                yaw=yaw_of(ux, uy), r=0.0, keep=0,
                                scale=(0.75, 0.8, 0.8) if small else (1.0, 1.0, 1.0),
                                attrs={"quay": qy.id, "waterway": w.id, "moored": True}))
    return out


def boats_in_water(c: Ctx, cands: list[Cand]) -> list[Cand]:
    """Boats whose hull lies in its waterway, clear of bridges and each other."""
    ww = {w.id: G.from_model_poly(w.polygon) for w in c.m.waterways}
    bridges = [LineString(s.centerline).buffer(s.width_m / 2.0 + 3.0)
               for s in c.m.road_segments if s.bridge]
    btree = shapely.STRtree(bridges) if bridges else None
    out = []
    for b in cands:
        poly = ww.get(b.attrs["waterway"])
        a = math.radians(b.yaw)
        hx, hy = 4.0 * b.scale[0], 1.5 * b.scale[1]
        ca, sa = math.cos(a), math.sin(a)
        hull = shapely.Polygon([(b.x + ca * u - sa * v, b.y + sa * u + ca * v)
                                for u, v in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))])
        if poly is None or not poly.contains(hull):
            continue
        if btree is not None and len(btree.query(hull, predicate="intersects")):
            continue
        b.r = hx
        b.x, b.y = q(b.x), q(b.y)
        if c.fits(b):
            c.occupy(b)
            out.append(b)
    return out


def parked_vehicles(c: Ctx) -> list[Cand]:
    out = []
    for s in c.m.road_segments:
        cs = s.cross_section
        if s.bridge or not any(cs.parking) or len(s.centerline) < 2:
            continue
        carriage = (cs.total_width_m - cs.sidewalk_m[0] - cs.sidewalk_m[1]) / 2.0
        occ = 0.55 + 0.3 * _u("occ", s.id)
        for side, sgn in ((0, 1.0), (1, -1.0)):
            if not cs.parking[side]:
                continue
            # the parking lane: what the carriageway half leaves beside the driving lanes
            n = cs.lanes_backward if side == 0 else cs.lanes_forward
            pw = carriage - cs.median_m / 2.0 - n * cs.lane_width_m
            if pw < 2.0:
                continue
            o = carriage - pw / 2.0
            for k, (x, y, ux, uy, _) in enumerate(walk(s.centerline, 6.5, 12.0, 12.0)):
                if _u("car", s.id, side, k) > occ:
                    continue
                nx, ny = -uy * sgn, ux * sgn
                yaw = yaw_of(ux, uy) if side == 1 else yaw_of(-ux, -uy)
                out.append(Cand("parked_vehicle", x + nx * o, y + ny * o, yaw=yaw, r=2.4,
                                keep=PARKED,
                                attrs={"segment": s.id}))
    return out


def highway_barriers(c: Ctx) -> list[Cand]:
    out = []
    for s in c.m.road_segments:
        if s.road_class != "highway" or s.cross_section.median_m <= 0:
            continue
        zs = [(z.s, z.z) for z in s.z_profile]
        for x, y, ux, uy, sv in walk(s.centerline, 4.0, 2.0, 2.0):
            out.append(Cand("barrier", x, y, z=_z_at(zs, sv), yaw=yaw_of(ux, uy), r=0.0,
                            keep=0, attrs={"segment": s.id}))
    return out


def _z_at(prof, s: float) -> float:
    if not prof:
        return 0.0
    if s <= prof[0][0]:
        return q(prof[0][1])
    for (s0, z0), (s1, z1) in zip(prof, prof[1:]):
        if s <= s1:
            return q(z0 if s1 <= s0 else z0 + (z1 - z0) * (s - s0) / (s1 - s0))
    return q(prof[-1][1])


def _facade_hits(c: Ctx, pts: np.ndarray, reach: float) -> np.ndarray:
    """For each point, the distance to the nearest building at the ground within reach (inf
    when none)."""
    out = np.full(len(pts), np.inf)
    tree, geoms = c.trees["bld"]
    if tree is None or not len(pts):
        return out
    p = shapely.points(pts)
    ip, ig = tree.query(p, predicate="dwithin", distance=reach)
    if len(ip):
        d = shapely.distance(p[ip], geoms[ig])
        np.minimum.at(out, ip, d)
    return out


def overhead_cables(c: Ctx) -> list[Cand]:
    """Cables across alleys and narrow streets between the facades on both sides, by
    grime."""
    out = []
    cand = []
    for s in c.m.road_segments:
        if s.bridge or s.road_class not in ("alley", "street") or len(s.centerline) < 2:
            continue
        half = s.cross_section.total_width_m / 2.0
        if s.road_class == "street" and half > 8.0:
            continue
        mid = s.centerline[len(s.centerline) // 2]
        did = c.district_of(np.array([mid]))[0]
        g = c.param(did, "grime", 0.4)
        if g < 0.25:
            continue
        step = 26.0 - 16.0 * g
        for k, (x, y, ux, uy, _) in enumerate(walk(s.centerline, step, step / 2.0, 6.0)):
            if _u("cable", s.id, k) > g:
                continue
            nx, ny = -uy, ux
            cand.append((s.id, k, x, y, nx, ny, half))
    if not cand:
        return out
    a = np.array([(x + nx * (h + 1.5), y + ny * (h + 1.5)) for _, _, x, y, nx, ny, h in cand])
    b = np.array([(x - nx * (h + 1.5), y - ny * (h + 1.5)) for _, _, x, y, nx, ny, h in cand])
    da, db = _facade_hits(c, a, 2.0), _facade_hits(c, b, 2.0)
    for (sid, k, x, y, nx, ny, h), ha, hb in zip(cand, da.tolist(), db.tolist()):
        if ha > 1.6 or hb > 1.6:
            continue        # a facade on both sides, at most 1.6 m behind the property line
        span = 2.0 * h + 3.0
        z = q(6.0 + 5.0 * _u("cz", sid, k))
        out.append(Cand("overhead_cable", x, y, z=z, yaw=yaw_of(nx, ny), r=0.0, keep=0,
                        scale=(q(span), 1.0, 1.0), attrs={"segment": sid,
                                                          "sag_m": q(0.3 + 0.5 * h / 8.0)}))
    return out


def unit_dressing(c: Ctx) -> list[Cand]:
    """Signs and awnings of the ground-floor units, facade AC units by grime, and extra
    blade signs by neon."""
    out = []
    for b in c.m.buildings:
        if not b.units:
            continue
        did = b.district_id
        neon, grime = c.param(did, "neon", 0.4), c.param(did, "grime", 0.4)
        for k, u in enumerate(b.units):
            (ax, ay), (bx, by) = u.edge
            L = math.hypot(bx - ax, by - ay)
            if L < 2.0:
                continue
            ux, uy = (bx - ax) / L, (by - ay) / L
            nx, ny = uy, -ux            # outward guess: away from the footprint
            if b.footprint is not None:
                fp = G.from_model_poly(b.footprint)
                mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
                if shapely.contains_xy(fp, mx + nx * 0.5, my + ny * 0.5):
                    nx, ny = -nx, -ny
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
            if u.awning_m > 0:
                out.append(Cand("awning", mx + nx * u.awning_m / 2.0, my + ny * u.awning_m / 2.0,
                                z=3.2, yaw=yaw_of(ux, uy), keep=0,
                                scale=(q(L * 0.9), q(u.awning_m), 1.0), attrs={"unit": u.use}))
            if u.sign or _u("sign", b.id, k) < neon * 0.6:
                blade = _u("blade", b.id, k) < neon
                out.append(Cand("sign", ax + ux * 0.8 + nx * (0.7 if blade else 0.15),
                                ay + uy * 0.8 + ny * (0.7 if blade else 0.15),
                                z=q(4.0 + 2.0 * _u("sz", b.id, k)),
                                yaw=yaw_of(nx, ny) if blade else yaw_of(ux, uy), keep=0,
                                scale=(1.0, 1.0 if blade else q(min(L * 0.7, 6.0) / 1.2),
                                       q(1.0 + 1.5 * neon) if blade else 0.5),
                                attrs={"emitter": True, "blade": blade, "use": u.use}))
            if b.floors >= 2 and _u("ac", b.id, k) < grime * 0.8 and \
                    b.use in ("residential", "mixed", "retail", "hotel"):
                floor = 1 + int(_u("acf", b.id, k) * min(b.floors - 1, 6))
                out.append(Cand("ac_unit", mx + nx * 0.3 + ux * L * 0.25,
                                my + ny * 0.3 + uy * L * 0.25,
                                z=q(floor * b.floor_height_m + 0.8), yaw=yaw_of(nx, ny),
                                keep=0, attrs={"facade": True}))
    return out


def scaffolding(c: Ctx) -> list[Cand]:
    out = []
    for b in c.m.buildings:
        if b.landmark or b.megasite_id or not b.units or b.height_m > 60.0 or \
                _u("scaff", b.id) > 0.012:
            continue
        u = max(b.units, key=lambda u: (u.width_m, u.edge))
        (ax, ay), (bx, by) = u.edge
        L = math.hypot(bx - ax, by - ay)
        if L < 4.0:
            continue
        ux, uy = (bx - ax) / L, (by - ay) / L
        nx, ny = uy, -ux
        fp = G.from_model_poly(b.footprint) if b.footprint is not None else None
        mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
        if fp is not None and shapely.contains_xy(fp, mx + nx * 0.5, my + ny * 0.5):
            nx, ny = -nx, -ny
        out.append(Cand("scaffolding", mx + nx * 0.8, my + ny * 0.8, z=0.0,
                        yaw=yaw_of(ux, uy), keep=0,
                        scale=(q(L), 1.0, q(min(b.height_m, 6 * b.floor_height_m))),
                        attrs={"building": b.id}))
    return out


def market_gates(c: Ctx) -> list[Cand]:
    out = []
    for p in c.m.places:
        if p.kind not in ("market",) or p.polygon is None:
            continue
        poly = G.from_model_poly(p.polygon)
        tree, geoms = c.trees["carr"]
        if tree is None:
            continue
        rp = poly.representative_point()
        hit = tree.query(rp, predicate="dwithin", distance=400.0)
        if not len(hit):
            continue
        k = min(hit.tolist(), key=lambda i: (round(geoms[i].distance(rp), 2), i))
        a, b = shapely.ops.nearest_points(poly.exterior, geoms[k])
        ux, uy = b.x - a.x, b.y - a.y
        n = math.hypot(ux, uy) or 1.0
        out.append(Cand("gate", a.x, a.y, yaw=yaw_of(-uy / n, ux / n), keep=0,
                        scale=(8.0, 1.0, 1.0), attrs={"place": p.id, "name": p.name}))
    return out


def alley_clutter(c: Ctx) -> list[Cand]:
    """Dumpsters at building backs along alleys and service lanes, trash in alleys and on
    sidewalks, by grime."""
    out = []
    for s in c.m.road_segments:
        if s.bridge or s.road_class not in ("alley", "service") or len(s.centerline) < 2:
            continue
        mid = s.centerline[len(s.centerline) // 2]
        did = c.district_of(np.array([mid]))[0]
        g = c.param(did, "grime", 0.4)
        half = s.cross_section.total_width_m / 2.0
        for k, (x, y, ux, uy, _) in enumerate(walk(s.centerline, 22.0, 8.0, 6.0)):
            if _u("dump", s.id, k) > 0.25 + 0.6 * g:
                continue
            sgn = 1.0 if _u("dside", s.id, k) < 0.5 else -1.0
            nx, ny = -uy * sgn, ux * sgn
            out.append(Cand("dumpster", x + nx * (half + 1.1), y + ny * (half + 1.1),
                            yaw=yaw_of(ux, uy), r=1.0, keep=GROUND | CARRIAGE,
                            attrs={"segment": s.id}))
        if g < 0.2:
            continue
        for k, (x, y, ux, uy, _) in enumerate(walk(s.centerline, 3.0 / g, 2.0, 2.0)):
            sgn = 1.0 if _u("tside", s.id, k) < 0.5 else -1.0
            nx, ny = -uy * sgn, ux * sgn
            o = half - 0.35
            out.append(Cand("trash", x + nx * o + ux * _u("tj", s.id, k),
                            y + ny * o + uy * _u("tj", s.id, k), r=0.25,
                            yaw=round(360.0 * _u("ty", s.id, k), 1),
                            keep=LITTER,
                            attrs={"item": ("bag", "box", "can")[int(3 * _u("ti", s.id, k))]}))
    for w in c.sw:
        did = None
        g = None
        L = length(w.line)
        if L < 20.0:
            continue
        mid = w.line[len(w.line) // 2]
        did = c.district_of(np.array([mid]))[0]
        g = c.param(did, "grime", 0.4)
        if g < 0.35:
            continue
        for x, y, ux, uy, sv in furniture_points(w, 12.0 / g, 5.0 + 6.0 * _u("ts", w.id), 0.5,
                                                 3.0):
            out.append(Cand("trash", x, y, r=0.25, yaw=round(360.0 * _u("tw", w.id, sv), 1),
                            keep=SIDEWALK,
                            attrs={"item": ("bag", "box", "can")[int(3 * _u("tk", w.id, sv))]}))
    return out


def station_props(c: Ctx) -> list[Cand]:
    """Vending machines and a kiosk at the street foot of every station's stairs."""
    out = []
    walks = {w.id: w for w in c.m.walkways}
    for st in c.m.stations:
        for k, wid in enumerate(st.access_ids):
            w = walks.get(wid)
            if w is None or w.kind not in ("stairs", "escalator", "elevator"):
                continue
            ground = [p for p in (w.line[0], w.line[-1]) if abs(p[2]) < 0.5]
            if not ground:
                continue
            x, y = ground[0][0], ground[0][1]
            ang = 2.0 * math.pi * _u("vend", st.id, k)
            out.append(Cand("vending_machine", x + 3.0 * M.cos(ang), y + 3.0 * M.sin(ang),
                            yaw=round(math.degrees(ang), 1), r=0.7, keep=SIDEWALK,
                            attrs={"station": st.id, "emitter": True}))
    return out


GENERATORS = [
    ("traffic_signals", traffic_signals), ("bus_stops", bus_stops),
    ("street_lights", street_lights), ("hydrants", hydrants), ("crosswalk_cans", crosswalk_cans),
    ("bollards", bollards), ("station_props", station_props), ("plaza_props", plaza_props),
    ("park_benches", park_benches), ("parked_vehicles", parked_vehicles),
    ("alley_clutter", alley_clutter),
]


# ---------------------------------------------------------------------------
# The stage
# ---------------------------------------------------------------------------

@dataclass
class Out:
    rows: dict
    info: dict
    notes: list


def build(spec, m) -> Out:
    with G.canonical():
        return _build(spec, m)


def _headroom(c: Ctx, oh):
    """A filter: ground props that fit under what is over them (M7: a street light under a
    viaduct deck is too tall, so it becomes a lamp hung under the deck)."""
    polys, under = oh
    tree = shapely.STRtree(polys) if polys else None

    def ok(cands: list[Cand]) -> list[Cand]:
        if tree is None or not cands:
            return cands
        pts = shapely.points(np.array([(x.x, x.y) for x in cands], dtype=np.float64))
        ip, ig = tree.query(pts, predicate="intersects")
        low = np.full(len(cands), np.inf)
        np.minimum.at(low, ip, np.asarray(under)[ig])
        out = []
        for x, u in zip(cands, low.tolist()):
            h = KINDS.get(x.kind, (None, (0.0, 0.0, 0.0)))[1][2]
            if x.z > 0.5 or u >= h + 0.3:
                out.append(x)
            elif x.kind == "street_light" and u >= 3.0:
                out.append(Cand("wall_light", x.x, x.y, z=q(u - 0.5), yaw=x.yaw, r=0.0,
                                keep=0, attrs={**x.attrs, "mount": "deck", "emitter": True}))
        return out
    return ok


def _build(spec, m) -> Out:
    import shapely.ops  # noqa: F401  (nearest_points)

    from . import vegetation as V

    c = Ctx(spec, m)
    placed: list[Cand] = []
    info: dict = {}
    under_ok = _headroom(c, V.overhead(c, fill=False))
    # ground things in priority order: what the street needs first, clutter last; the trees
    # go between the street furniture and the clutter (vegetation.py)
    for name, fn in GENERATORS[:7]:
        got = c.place(under_ok(fn(c)))
        info[name] = len(got)
        placed += got
        if name == "street_lights":
            poles, spots = narrow_lights(c)
            got = c.place(poles)
            got += wall_lights(c, spots)
            info["narrow_lights"] = len(got)
            placed += got
        if name == "bus_stops":
            c.no_tree += [(p.x, p.y) for p in got if p.kind == "bus_stop"]
    got = c.place(V.fit_crowns(c, V.street_trees(c)))
    info["street_trees"] = len(got)
    placed += got
    for name, fn in GENERATORS[7:]:
        got = c.place(under_ok(fn(c)))
        info[name] = len(got)
        placed += got
    for name, fn in V.GENERATORS:
        got = c.place(V.fit_crowns(c, fn(c)))
        info[name] = len(got)
        placed += got
    qp = quay_props(c)
    boats = [x for x in qp if x.kind == "boat"]
    got = c.place([x for x in qp if x.kind != "boat"]) + boats_in_water(c, boats)
    info["quay_props"] = len(got)
    placed += got
    for name, fn in (("highway_barriers", highway_barriers),
                     ("overhead_cables", overhead_cables), ("unit_dressing", unit_dressing),
                     ("scaffolding", scaffolding), ("market_gates", market_gates)):
        got = fn(c)
        info[name] = len(got)
        placed += got
    props, plants = rows(c, placed)
    green = V.green_rows(c)
    info["props"] = len(props)
    info["plants"] = len(plants)
    return Out({"props": props, "plants": plants,
                "green_areas": list(m.green_areas) + green}, info, [])


def rows(c: Ctx, placed: list[Cand]) -> tuple[list, list]:
    xy = np.array([(p.x, p.y) for p in placed], dtype=np.float64) if placed else \
        np.zeros((0, 2))
    dids = c.district_of(xy)
    props, plants = [], []
    count: dict = {}
    for p, did in zip(placed, dids):
        owner = did or "city"
        if p.plant is not None:
            key = (owner, "plant", p.kind)
        else:
            key = (owner, "prop", p.kind)
        n = count.get(key, 0) + 1
        count[key] = n
        pid = f"{owner}.{key[1]}.{p.kind}.{n:05d}"
        if p.plant is not None:
            plants.append({"id": pid, "type": f"plant.{p.kind}",
                           "position": [q(p.x), q(p.y), q(p.z)],
                           "height_m": q(p.plant["height_m"]),
                           "crown_radius_m": q(p.plant["crown_radius_m"]),
                           "species": p.plant.get("species"),
                           "attrs": ({**p.attrs, "yaw_deg": p.yaw, "length_m": q(p.scale[0])}
                                     if p.kind == "facade_greenery" else p.attrs)})
        else:
            props.append({"id": pid, "type": f"prop.{p.kind}",
                          "position": [q(p.x), q(p.y), q(p.z)], "yaw_deg": p.yaw,
                          "scale": [q(v) for v in p.scale],
                          "attrs": p.attrs})
    return props, plants
