"""Pipeline stage 1, the brief (scope sections 3, 4.1 and 4.4).

Per building, everything its asset will be made from, in its own frame (origin at the middle
of its footprint's bounding box, on the 0.01 m grid; x east, y north, z up, meters to the
millimeter), as canonical JSON with a sha256:

- its record (masses, floors, units, entrances, roof items, portals, style), its lot and
  frontage, its property and district, the asset spec's sections for it, its overrides;
- every mass edge classified (scope 5.1.2) and split into regions of the facade, each a
  rectangle (s along the edge, z up) with a class: `front` (faces the main frontage road),
  `street` (another road, by class), `alley` (alley or service lane), `canal` (water),
  `plaza`, `park`, `courtyard` or `atrium` (a footprint hole or a courtyard open space),
  `party` (another building within 0.5 m), `blind` (within 3 m), `open` (setback, yard, a
  building further off), `upper` (above every neighbor that covers the part below), or
  `hidden` (behind another mass of the same building);
- the floor grid of every mass;
- neighbors within 3 m, skybridges, portals, sign slots, POIs, facade plants, green roofs;
- mounted props: scaffolding by `attrs.building`, and AC units, awnings, wall lights, signs
  and overhead cable ends by position on a facade.

What faces an edge is found by probes stepping out from it (0.75 to 60 m): the first one in
a road corridor, water, an open space or another mass at eye height decides. Everything is
exact arithmetic on the model's grid coordinates or IEEE operations in a fixed order, with
blake2b nowhere needed yet: the same bytes on every machine and for any worker count.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from citygen import dmath as M
from citygen.model import CityModel

from . import __version__
from . import canon as C
from . import planar as PL
from . import spec as S

BRIEF_VERSION = 2      # 2: AG4 (clearances, portal tube lines, skybridges in the building frame)
PARTY_M = 0.5          # another building this close: a party wall
BLIND_M = 3.0          # this close: a blind wall (and a neighbor in the brief)
HIDE_M = 0.05          # another mass of the same building this close outside: hidden
MOUNT_M = 0.5          # a facade prop's mount point within this of a facade: on the wall
MOUNT_OFF_M = 2.0      # within this: still the building's, off the wall
PROBES_M = (0.75, 1.5, 2.5, 4.0, 6.0, 9.0, 13.0, 18.0, 24.0, 32.0, 40.0, 50.0, 60.0)
EYE_M = 1.5            # probes look out at the facade part's base plus this
MIN_LEN_M = 0.0005     # stretches and bands are on the millimeter grid: drop only empty ones
CELL_M = 64.0

CLASSES = ("front", "street", "alley", "canal", "plaza", "park", "courtyard", "atrium",
           "party", "blind", "open", "upper", "hidden")
COVER_RANK = {"hidden": 0, "party": 1, "blind": 2}
DOOR_RANK = {"avenue": 0, "street": 1, "pedestrian": 2, "alley": 3, "service": 4,
             "footbridge": 5, "highway": 9}
ALLEY_CLASSES = ("alley", "service")
PARK_KINDS = ("park", "pocket_park", "garden", "green", "marsh", "beach")
PLAZA_KINDS = ("plaza", "market", "promenade")
# How far a facade prop's position sits out from the wall it hangs on (M6 places them so):
# the mount point is that much nearer the facade. Overhead cables end up to 1.6 m before it.
MOUNT_REACH = {"ac_unit": 0.3, "wall_light": 0.2, "sign": 0.7, "awning": None,
               "overhead_cable": 1.6}
FACADE_PROPS = ("ac_unit", "awning", "wall_light", "sign", "overhead_cable")
DISTRICT_KEYS = ("grime", "neon", "greenery", "wealth", "danger")
NO_FLOOR_ROLES = ("spire", "mast", "void")


def load_model(path: str | Path) -> tuple[CityModel, str, Path]:
    """(model, sha256 of its file, its build directory) from a build dir or the file."""
    p = Path(path)
    f = p / "city_model.json" if p.is_dir() else p
    data = f.read_bytes()
    return CityModel.model_validate_json(data), C.sha256_bytes(data), f.parent


# ---------------------------------------------------------------------------
# Masses and edges
# ---------------------------------------------------------------------------

@dataclass
class Mass:
    b: int                      # building index
    k: int                      # mass index in its building
    rings: list                 # [exterior ccw, holes cw]
    z0: float
    z1: float
    box: tuple


@dataclass
class Edge:
    mass: Mass
    ring: int
    i: int
    a: tuple
    b: tuple
    L: float
    u: tuple
    n: tuple
    covers: list = field(default_factory=list)     # (kind, s0, s1, z0, z1, ref, dist)
    regions: list = field(default_factory=list)


class MassIndex:
    """Masses of every building bucketed by a square grid of their bounding boxes."""

    def __init__(self, masses: list[Mass], cell: float = CELL_M):
        self.masses, self.cell = masses, cell
        self.cells: dict[tuple[int, int], list[int]] = {}
        for j, mm in enumerate(masses):
            x0, y0, x1, y1 = mm.box
            for cx in range(math.floor(x0 / cell), math.floor(x1 / cell) + 1):
                for cy in range(math.floor(y0 / cell), math.floor(y1 / cell) + 1):
                    self.cells.setdefault((cx, cy), []).append(j)

    def query(self, x0, y0, x1, y1) -> list[int]:
        c = self.cell
        out = set()
        for cx in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
            for cy in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
                for j in self.cells.get((cx, cy), ()):
                    bx0, by0, bx1, by1 = self.masses[j].box
                    if bx0 <= x1 and bx1 >= x0 and by0 <= y1 and by1 >= y0:
                        out.add(j)
        return sorted(out)


def mass_rings(m) -> list:
    ext = PL.oriented(PL.ring(m.footprint.exterior), ccw=True)
    holes = [PL.oriented(PL.ring(h), ccw=False) for h in m.footprint.holes]
    return [ext] + holes


def edges_of(mass: Mass) -> list[Edge]:
    out = []
    for r, pts in enumerate(mass.rings):
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            L = PL.seg_len(a, b)
            if L < 0.001:
                continue
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            # outward: right of the direction of travel (exterior ccw, holes cw)
            out.append(Edge(mass, r, i, a, b, L, (ux, uy), (uy, -ux)))
    return out


# ---------------------------------------------------------------------------
# The city context: everything a brief looks up
# ---------------------------------------------------------------------------

class City:
    def __init__(self, model: CityModel):
        self.m = model
        self.bidx = {b.id: k for k, b in enumerate(model.buildings)}
        self.masses: list[Mass] = []
        self.by_b: list[list[Mass]] = []
        for k, b in enumerate(model.buildings):
            row = []
            for j, mm in enumerate(b.masses):
                rings = mass_rings(mm)
                row.append(Mass(k, j, rings, float(mm.z0_m), float(mm.z1_m),
                                PL.bbox(rings[0])))
            self.by_b.append(row)
            self.masses.extend(row)
        self.index = MassIndex(self.masses)
        self.lots = {lt.id: lt for lt in model.lots}
        self.props_ = {p.id: p for p in model.properties}
        self.districts = {d.id: d for d in model.districts}
        self.segments = {s.id: s for s in model.road_segments}

    def main_segment(self, b) -> str | None:
        """The frontage the building's facade sits on (M3's `main_front`), else the road
        of its main entrance."""
        lot = self.lots.get(b.lot_id) if b.lot_id else None
        fronts = [f for f in (lot.frontage if lot else []) if len(f.line) >= 2]
        if fronts:
            best = fronts[0]
            for f in fronts[1:]:
                better = DOOR_RANK.get(f.road_class, 9) < DOOR_RANK.get(best.road_class, 9)
                if better and (f.length_m >= 0.5 * fronts[0].length_m or
                               (best.road_class == "highway" and f.length_m >= 6.0)):
                    best = f
            return best.segment_id
        for e in b.entrances:
            if e.kind == "main" and e.segment_id:
                return e.segment_id
        return None


# ---------------------------------------------------------------------------
# Coverage: hidden, party and blind parts of every edge
# ---------------------------------------------------------------------------

def cover_edges(city: City, k: int) -> list[Edge]:
    out = []
    for mass in city.by_b[k]:
        for e in edges_of(mass):
            ux, uy = e.u
            nx, ny = e.n
            ax, ay = e.a
            bx, by = e.b
            pad = BLIND_M
            x0 = min(ax, bx, ax + nx * pad, bx + nx * pad)
            x1 = max(ax, bx, ax + nx * pad, bx + nx * pad)
            y0 = min(ay, by, ay + ny * pad, by + ny * pad)
            y1 = max(ay, by, ay + ny * pad, by + ny * pad)
            for j in city.index.query(x0, y0, x1, y1):
                o = city.masses[j]
                if o is mass:
                    continue
                if o.b == k:
                    if o.z1 <= mass.z0 or o.z0 >= mass.z1:
                        continue
                    hit = PL.clip_strip(PL.to_edge(o.rings[0], e.a, ux, uy, nx, ny), e.L,
                                        HIDE_M)
                    if hit is not None and _inside_holes(o, hit, e) is False:
                        e.covers.append(("hidden", hit[0], hit[1], o.z0, o.z1,
                                         f"m{o.k}", 0.0))
                    continue
                if o.z1 <= mass.z0 or o.z0 >= mass.z1:
                    continue
                oid = city.m.buildings[o.b].id
                loc = PL.to_edge(o.rings[0], e.a, ux, uy, nx, ny)
                hit = PL.clip_strip(loc, e.L, BLIND_M)
                if hit is None:
                    continue
                party = PL.clip_strip(loc, e.L, PARTY_M)
                if party is not None:
                    e.covers.append(("party", party[0], party[1], o.z0, o.z1, oid,
                                     max(party[2], 0.0)))
                e.covers.append(("blind", hit[0], hit[1], o.z0, o.z1, oid, max(hit[2], 0.0)))
            out.append(e)
    return out


def _inside_holes(o: Mass, hit, e: Edge) -> bool:
    """Whether the covered stretch lies in a hole of the covering mass (a court): then it
    is not covered. Tested at the stretch's middle, just outside the edge."""
    if len(o.rings) == 1:
        return False
    s = (hit[0] + hit[1]) / 2.0
    px = e.a[0] + e.u[0] * s + e.n[0] * (HIDE_M / 2.0)
    py = e.a[1] + e.u[1] * s + e.n[1] * (HIDE_M / 2.0)
    xs, ys = np.array([px]), np.array([py])
    return any(bool(PL.inside_ring(xs, ys, h)[0]) for h in o.rings[1:])


@dataclass
class Ray:
    edge: Edge
    s: float            # middle of the stretch along the edge
    z: float            # eye height of the probes


def split_edge(e: Edge, z0: float, z1: float, rays: list[Ray]) -> None:
    """Regions of the edge's facade from its covers; stretches that face out get a ray."""
    bps = {0.0, C.m(e.L)}
    for c in e.covers:
        for s in (c[1], c[2]):
            s = C.m(s)
            if 0.0 < s < C.m(e.L):
                bps.add(s)
    bps = sorted(bps)
    for p, q in zip(bps, bps[1:]):
        if q - p < MIN_LEN_M:
            continue
        mid = (p + q) / 2.0
        active = [c for c in e.covers if c[1] <= mid <= c[2]]
        zs = {z0, z1}
        for c in active:
            for z in (c[3], c[4]):
                if z0 < z < z1:
                    zs.add(z)
        zs = sorted(zs)
        top = max((c[4] for c in active), default=None)
        bands = []
        ray = None
        for za, zb in zip(zs, zs[1:]):
            if zb - za < MIN_LEN_M:
                continue
            zm = (za + zb) / 2.0
            cov = [c for c in active if c[3] <= zm <= c[4]]
            if cov:
                best = min(cov, key=lambda c: (COVER_RANK[c[0]], c[6], c[5]))
                cls, ref = best[0], best[5]
            elif top is not None and za >= top:
                cls, ref = "upper", None
            else:
                if ray is None:
                    ray = Ray(e, mid, za + EYE_M)
                    rays.append(ray)
                cls, ref = ray, None
            if bands and bands[-1][2] is cls and bands[-1][3] == ref and bands[-1][1] == za:
                bands[-1][1] = zb
            elif bands and bands[-1][2] == cls and not isinstance(cls, Ray) and \
                    bands[-1][3] == ref and bands[-1][1] == za:
                bands[-1][1] = zb
            else:
                bands.append([za, zb, cls, ref])
        e.regions.append([p, q, bands])


# ---------------------------------------------------------------------------
# Facing: probes stepping out from every stretch that faces out
# ---------------------------------------------------------------------------

def face_rays(city: City, rays: list[Ray]) -> list[tuple]:
    """(class code, ref id) per ray: the first probe that lands in a road corridor,
    water, an open space or a mass at its eye height decides."""
    nr, nk = len(rays), len(PROBES_M)
    if nr == 0:
        return []
    d = np.array(PROBES_M)
    mx = np.array([r.edge.a[0] + r.edge.u[0] * r.s for r in rays])
    my = np.array([r.edge.a[1] + r.edge.u[1] * r.s for r in rays])
    nx = np.array([r.edge.n[0] for r in rays])
    ny = np.array([r.edge.n[1] for r in rays])
    px = (mx[:, None] + nx[:, None] * d[None, :]).ravel()
    py = (my[:, None] + ny[:, None] * d[None, :]).ravel()
    pz = np.repeat(np.array([r.z for r in rays]), nk)
    grid = PL.PointGrid(px, py)
    n = len(px)
    # per probe: (category rank, key, ref index); lower wins
    cat = np.full(n, 9, dtype=np.int64)
    key = np.full(n, np.inf)
    ref = np.full(n, -1, dtype=np.int64)
    refs: list[tuple[str, str]] = []

    def take(idx, mask, rank, k_val, label):
        if not mask.any():
            return
        sel = idx[mask]
        kv = k_val[mask] if isinstance(k_val, np.ndarray) else np.full(len(sel), k_val)
        r = len(refs)
        refs.append(label)
        better = (rank < cat[sel]) | ((rank == cat[sel]) & (kv < key[sel]))
        sel, kv = sel[better], kv[better]
        cat[sel] = rank
        key[sel] = kv
        ref[sel] = r

    m = city.m
    for s in m.road_segments:
        if s.tunnel or s.road_class == "footbridge" or len(s.centerline) < 2:
            continue
        half = s.width_m / 2.0
        x0, y0, x1, y1 = PL.bbox(s.centerline)
        idx = grid.query(x0 - half, y0 - half, x1 + half, y1 + half)
        if not len(idx):
            continue
        dd = PL.dist_polyline(px[idx], py[idx], s.centerline)
        take(idx, dd <= half, 0, dd, ("road", s.id))
    waters = []
    for coll in (m.waterways, m.rivers, m.channels):
        for w in coll:
            waters.append((w.id, w.polygon))
    for sea in m.seas:
        for k, pg in enumerate(sea.polygons):
            waters.append((sea.id, pg))
    for wid, pg in waters:
        ext = PL.ring(pg.exterior)
        x0, y0, x1, y1 = PL.bbox(ext)
        idx = grid.query(x0, y0, x1, y1)
        if not len(idx):
            continue
        ins = PL.inside_poly(px[idx], py[idx], ext, [PL.ring(h) for h in pg.holes])
        take(idx, ins, 1, 0.0, ("water", wid))
    for q in m.quays:
        half = q.width_m / 2.0
        x0, y0, x1, y1 = PL.bbox(q.line)
        idx = grid.query(x0 - half, y0 - half, x1 + half, y1 + half)
        if not len(idx):
            continue
        dd = PL.dist_polyline(px[idx], py[idx], q.line)
        take(idx, dd <= half, 1, dd, ("water", q.id))
    for o in m.open_spaces:
        if o.z_m > 0.5:
            continue
        ext = PL.ring(o.polygon.exterior)
        x0, y0, x1, y1 = PL.bbox(ext)
        idx = grid.query(x0, y0, x1, y1)
        if not len(idx):
            continue
        ins = PL.inside_poly(px[idx], py[idx], ext, [PL.ring(h) for h in o.polygon.holes])
        take(idx, ins, 2, 0.0, ("open_space:" + o.kind, o.id))
    for mass in city.masses:
        x0, y0, x1, y1 = mass.box
        idx = grid.query(x0, y0, x1, y1)
        if not len(idx):
            continue
        zz = pz[idx]
        hz = (zz >= mass.z0) & (zz < mass.z1)
        if not hz.any():
            continue
        idx = idx[hz]
        ins = PL.inside_poly(px[idx], py[idx], mass.rings[0], mass.rings[1:])
        take(idx, ins, 3, 0.0, ("building", m.buildings[mass.b].id))
    cat = cat.reshape(nr, nk)
    ref = ref.reshape(nr, nk)
    out = []
    for i in range(nr):
        hit = np.nonzero(cat[i] < 9)[0]
        out.append(refs[int(ref[i, hit[0]])] if len(hit) else None)
    return out


def facing_class(city: City, hit, main_seg: str | None, own_id: str) -> tuple:
    if hit is None:
        return "open", None, None
    kind, rid = hit
    if kind == "road":
        s = city.segments[rid]
        if rid == main_seg:
            return "front", rid, s.road_class
        if s.road_class in ALLEY_CLASSES:
            return "alley", rid, s.road_class
        return "street", rid, s.road_class
    if kind == "water":
        return "canal", rid, None
    if kind.startswith("open_space:"):
        k = kind.split(":", 1)[1]
        if k in PARK_KINDS:
            return "park", rid, k
        if k in PLAZA_KINDS:
            return "plaza", rid, k
        if k == "courtyard":
            return "courtyard", rid, k
        return "open", rid, k
    return "open", (None if rid == own_id else rid), None


def ring_dist(a: np.ndarray, b: np.ndarray) -> float:
    """Smallest distance between two closed rings (0 where they touch, cross or one holds
    the other's first vertex); the same value either way round."""
    def pt_seg(p, r):
        q = np.roll(r, -1, axis=0)
        d = q - r
        L2 = d[:, 0] * d[:, 0] + d[:, 1] * d[:, 1]
        L2 = np.where(L2 == 0.0, 1.0, L2)
        f = ((p[:, None, 0] - r[None, :, 0]) * d[None, :, 0] +
             (p[:, None, 1] - r[None, :, 1]) * d[None, :, 1]) / L2[None, :]
        f = np.clip(f, 0.0, 1.0)
        ex = p[:, None, 0] - (r[None, :, 0] + f * d[None, :, 0])
        ey = p[:, None, 1] - (r[None, :, 1] + f * d[None, :, 1])
        return np.sqrt(ex * ex + ey * ey).min()

    d = min(pt_seg(a, b), pt_seg(b, a))
    if d == 0.0:
        return 0.0
    if PL.inside_ring(a[:1, 0], a[:1, 1], b)[0] or PL.inside_ring(b[:1, 0], b[:1, 1], a)[0]:
        return 0.0
    a2, b2 = np.roll(a, -1, axis=0), np.roll(b, -1, axis=0)

    def orient(p, q, r):
        return ((q[..., 0] - p[..., 0]) * (r[..., 1] - p[..., 1]) -
                (q[..., 1] - p[..., 1]) * (r[..., 0] - p[..., 0]))

    A, A2, B, B2 = a[:, None], a2[:, None], b[None, :], b2[None, :]
    o1, o2 = orient(A, A2, B), orient(A, A2, B2)
    o3, o4 = orient(B, B2, A), orient(B, B2, A2)
    if (((o1 > 0) & (o2 < 0) | (o1 < 0) & (o2 > 0)) &
            ((o3 > 0) & (o4 < 0) | (o3 < 0) & (o4 > 0))).any():
        return 0.0
    return float(d)


def neighbors_of(city: City, k: int) -> list[tuple[str, float]]:
    """(id, distance) of every other building with a mass within 3 m of one of this
    building's masses at a height they share, by id. Symmetric: each pair is measured the
    same way from both sides."""
    best: dict[str, float] = {}
    for mass in city.by_b[k]:
        x0, y0, x1, y1 = mass.box
        a = np.array(mass.rings[0])
        for j in city.index.query(x0 - BLIND_M, y0 - BLIND_M, x1 + BLIND_M, y1 + BLIND_M):
            o = city.masses[j]
            if o.b == k or o.z1 <= mass.z0 or o.z0 >= mass.z1:
                continue
            bx0, by0, bx1, by1 = o.box
            if bx0 > x1 + BLIND_M or bx1 < x0 - BLIND_M or by0 > y1 + BLIND_M or \
                    by1 < y0 - BLIND_M:
                continue
            oid = city.m.buildings[o.b].id
            d = ring_dist(a, np.array(o.rings[0]))
            if d <= BLIND_M and (oid not in best or d < best[oid]):
                best[oid] = d
    return sorted(best.items())


# ---------------------------------------------------------------------------
# Locating things on facades
# ---------------------------------------------------------------------------

def locate(edges: list[Edge], x: float, y: float, z: float, tol_z: float = 0.5):
    """(distance, mass, edge index in the brief, s) of the facade nearest to (x, y) among
    edges whose mass spans z; None if no mass does."""
    best = None
    for j, e in enumerate(edges):
        ms = e.mass
        if z < ms.z0 - tol_z or z > ms.z1 + tol_z:
            continue
        d, s = PL.point_seg_dist((x, y), e.a, e.b)
        key = (d, ms.k, j)
        if best is None or key < best[0]:
            best = (key, ms.k, j, s)
    if best is None:
        return None
    return best[0][0], best[1], best[2], best[3]


def at(loc) -> dict | None:
    if loc is None:
        return None
    d, k, j, s = loc
    return {"mass": k, "edge": j, "s": C.m(s), "d": C.m(d)}


def mount_points(p) -> list[tuple]:
    """(end, x, y, z, reach) of a facade prop: where it meets the wall it hangs on."""
    kind = p.type.split(".")[1]
    x, y, z = p.position
    if kind == "overhead_cable":
        a = M.radians(p.yaw_deg)
        c, s = M.cos(a), M.sin(a)
        h = p.scale[0] / 2.0
        return [(0, x + c * h, y + s * h, z, MOUNT_REACH[kind]),
                (1, x - c * h, y - s * h, z, MOUNT_REACH[kind])]
    if kind == "awning":
        return [(None, x, y, z, p.scale[1] / 2.0)]
    if kind == "wall_light" and p.attrs.get("mount") == "deck":
        return []
    reach = MOUNT_REACH[kind]
    if kind == "sign" and not p.attrs.get("blade", False):
        reach = 0.15
    return [(None, x, y, z, reach)]


def mount_props(city: City, edges_by_b: list[list[Edge]]) -> dict[int, list[dict]]:
    """Props on each building: scaffolding by `attrs.building`; facade props on the
    building whose facade their mount point is nearest. A prop is `on_wall` when that
    point is within 0.5 m of a facade whose mass spans its height; one up to 2 m off, or
    beside a wall that ends below it (M6 places by ground-floor units and floor numbers,
    not by the mass at that height), is still the building's, with `on_wall` false and its
    gap, for AG3 to bracket or drop. Ties go to the smaller id."""
    out: dict[int, list[dict]] = {}
    m = city.m
    stats: dict[str, list[int]] = {}
    for p in m.props:
        kind = p.type.split(".")[1]
        if kind == "scaffolding":
            k = city.bidx.get(p.attrs.get("building"))
            if k is not None:
                loc = locate(edges_by_b[k], p.position[0], p.position[1], 0.5)
                out.setdefault(k, []).append(_prop_entry(city, k, p, None, loc, True, 0.0))
            continue
        if kind not in FACADE_PROPS:
            continue
        for end, x, y, z, reach in mount_points(p):
            tol = reach + MOUNT_OFF_M
            best = None
            seen = set()
            for j in city.index.query(x - tol, y - tol, x + tol, y + tol):
                k = city.masses[j].b
                if k in seen:
                    continue
                seen.add(k)
                loc = locate(edges_by_b[k], x, y, z)
                gap = None if loc is None else max(loc[0] - reach, 0.0)
                on = gap is not None and gap <= MOUNT_M
                if not on:
                    loc = locate(edges_by_b[k], x, y, z, tol_z=math.inf)
                    gap = max(loc[0] - reach, 0.0)
                    if gap > MOUNT_OFF_M:
                        continue
                key = (not on, gap, m.buildings[k].id)
                if best is None or key < best[0]:
                    best = (key, k, loc, on, gap)
            st = stats.setdefault(kind, [0, 0, 0])
            if best is None:
                st[2] += 1
                continue
            st[0 if best[3] else 1] += 1
            out.setdefault(best[1], []).append(
                _prop_entry(city, best[1], p, end, best[2], best[3], best[4]))
    city.mount_stats = stats
    for k in out:
        out[k].sort(key=lambda e: (e["id"], -1 if e.get("end") is None else e["end"]))
    return out


def _prop_entry(city: City, k: int, p, end, loc, on: bool, gap: float) -> dict:
    ox, oy = city.origins[k]
    e = {"id": p.id, "kind": p.type.split(".")[1], "position": C.pt3(p.position, ox, oy),
         "yaw_deg": C.deg(p.yaw_deg), "scale": [C.m(v) for v in p.scale],
         "attrs": p.attrs, "at": at(loc), "on_wall": on, "gap_m": C.m(gap)}
    if end is not None:
        e["end"] = end
    return e


# ---------------------------------------------------------------------------
# The briefs
# ---------------------------------------------------------------------------

def origin_of(b) -> tuple[float, float]:
    xs, ys = [], []
    for mm in b.masses:
        for x, y in mm.footprint.exterior:
            xs.append(x)
            ys.append(y)
    return C.m2((min(xs) + max(xs)) / 2.0), C.m2((min(ys) + max(ys)) / 2.0)


def floors_of(mm, fh: float, base: float = 0.0) -> dict:
    """Floors of a mass on the building's floor grid (M14: counted from its deck's top for a
    building on a deck)."""
    h = mm.z1_m - mm.z0_m
    if mm.role in NO_FLOOR_ROLES or h < 0.5 * fh:
        return {"first": None, "count": 0, "height_m": None}
    n, k0 = h / fh, (mm.z0_m - base) / fh
    first = int(round(k0)) if abs(k0 - round(k0)) < 1e-3 else None
    if abs(n - round(n)) < 1e-3:
        return {"first": first, "count": int(round(n)), "height_m": C.m(fh)}
    count = max(int(round(n)), 1)
    return {"first": first, "count": count, "height_m": C.m(h / count)}


def _poly(pg, ox, oy) -> dict:
    return {"exterior": [C.pt(p, ox, oy) for p in PL.ring(pg.exterior)],
            "holes": [[C.pt(p, ox, oy) for p in PL.ring(h)] for h in pg.holes]}


def _edge_record(e: Edge, ox: float, oy: float, faced: dict, k: int) -> dict:
    regions = []
    area: dict[str, float] = {}
    for p, q, bands in e.regions:
        for za, zb, cls, ref in bands:
            extra = None
            if isinstance(cls, Ray):
                cls, ref, extra = faced[id(cls)]
            reg = {"s": [C.m(p), C.m(q)], "z": [C.m(za), C.m(zb)], "class": cls}
            if ref is not None:
                reg["ref"] = ref
            if extra is not None:
                reg["road_class" if cls in ("front", "street", "alley") else "kind"] = extra
            regions.append(reg)
            if cls != "hidden":
                area[cls] = area.get(cls, 0.0) + (q - p) * (zb - za)
    regions = _merge_regions(regions)
    if area:
        dom = min(area, key=lambda c: (-round(area[c], 6), CLASSES.index(c)))
    else:
        dom = "hidden"
    yaw = M.degrees(M.atan2(e.n[1], e.n[0]))
    return {"ring": e.ring, "i": e.i, "a": C.pt(e.a, ox, oy), "b": C.pt(e.b, ox, oy),
            "length_m": C.m(e.L), "normal_deg": C.deg(yaw), "class": dom, "regions": regions}


def _merge_regions(regions: list[dict]) -> list[dict]:
    """Merge neighboring stretches along the edge whose bands are the same."""
    by_s: list[list] = []
    for r in regions:
        if by_s and by_s[-1][0] == r["s"]:
            by_s[-1][1].append(r)
        else:
            by_s.append([r["s"], [r]])

    def sig(rs):
        return [(r["z"], r["class"], r.get("ref"), r.get("road_class"), r.get("kind"))
                for r in rs]

    merged: list[list] = []
    for s, rs in by_s:
        if merged and merged[-1][0][1] == s[0] and sig(merged[-1][1]) == sig(rs):
            merged[-1][0] = [merged[-1][0][0], s[1]]
        else:
            merged.append([list(s), rs])
    out = []
    for s, rs in merged:
        for r in rs:
            out.append({**r, "s": s})
    return out


def build_briefs(model: CityModel, spec: S.AssetSpec | None = None,
                 overrides: dict | None = None) -> dict:
    """{building id: brief} and stats for every building of the model."""
    t0 = time.perf_counter()
    spec = S.fill(spec or S.AssetSpec())
    sdata = S.dump(spec)
    city = City(model)
    city.origins = [origin_of(b) for b in model.buildings]
    city.mains = [city.main_segment(b) for b in model.buildings]
    edges_by_b: list[list[Edge]] = []
    rays: list[Ray] = []
    for k, b in enumerate(model.buildings):
        es = cover_edges(city, k)
        for e in es:
            split_edge(e, e.mass.z0, e.mass.z1, rays)
        edges_by_b.append(es)
    t_cover = time.perf_counter()
    hits = face_rays(city, rays)
    faced = {}
    for r, h in zip(rays, hits):
        k = r.edge.mass.b
        b = model.buildings[k]
        if r.edge.ring > 0:
            cls = "atrium" if b.attrs.get("atrium_m2") else "courtyard"
            faced[id(r)] = (cls, None, None)
        else:
            faced[id(r)] = facing_class(city, h, city.mains[k], b.id)
    t_face = time.perf_counter()
    props = mount_props(city, edges_by_b)
    t_props = time.perf_counter()
    briefs = {}
    look = _Lookups(model)
    from .streets.ctx import Ground
    ground = Ground(model)
    cors = corridors(model, ground)
    for k, b in enumerate(model.buildings):
        briefs[b.id] = _brief(city, k, b, edges_by_b[k], faced, props.get(k, []), look,
                              sdata, overrides, cors, ground)
    t_end = time.perf_counter()
    stats = _stats(briefs, city)
    stats["seconds"] = {"cover": round(t_cover - t0, 2), "facing": round(t_face - t_cover, 2),
                        "props": round(t_props - t_face, 2), "briefs": round(t_end - t_props, 2)}
    stats["rays"] = len(rays)
    return {"briefs": briefs, "stats": stats, "spec": sdata}


class _Lookups:
    def __init__(self, model: CityModel):
        def group(rows, key):
            out: dict = {}
            for r in rows:
                kv = key(r)
                if kv is not None:
                    out.setdefault(kv, []).append(r)
            return out
        self.sky = {}
        for s in model.skybridges:
            for j, bid in enumerate(s.building_ids):
                self.sky.setdefault(bid, []).append((s, j))
        self.slots = group(model.sign_slots, lambda s: s.building_id)
        self.pois = group(model.pois, lambda p: p.building_id)
        self.plants = group(model.plants, lambda p: p.attrs.get("building"))
        self.green = group(model.green_areas, lambda g: g.building_id
                           if g.kind == "green_roof" else None)
        # AG4: the sky tubes of every line (their top lines, in pieces), sky stations by
        # their tower
        self.tubes: dict[str, list] = {}
        for st in model.structures:
            a = st.attrs or {}
            if st.kind == "tube" and a.get("line_id") and len(st.line) >= 2:
                self.tubes.setdefault(a["line_id"], []).append(st)
        self.sky_stations = group([s for s in model.stations if s.kind == "sky"],
                                  lambda s: s.building_id)


# AG4: what a building's asset must keep out of (scope 9): skybridges, transit guideways and
# sky tubes passing near it, as corridors (a line with a floor and a top at every point, a
# half width); a building's tops are tested up to its height and this much over it (roof
# equipment, masts)
CLEAR_MARGIN_M = 4.0          # corridors within this of the footprint's box (plan)
CLEAR_OVER_M = 16.0
TUBE_D_M = 7.0                # citygen's sky tube (transit.DECK_M): its line is the top
SKYBRIDGE_DECK_M = 1.0        # what a skybridge's deck structure reaches under z_m
SKYBRIDGE_H = {"open_deck": 1.4, "catwalk": 1.4, "cable": 1.4}     # rail heights (else levels)
# a train's envelope over the rail (elevated rail, maglev) or round the beam (monorail), and
# under it the deck (citygen's transit.DECK_M) and the pad
TRAIN_UP_M = {"elevated_rail": 5.0, "maglev": 4.5, "monorail": 3.8}
DECK_DOWN_M = {"elevated_rail": 1.6, "maglev": 2.0, "monorail": 1.8}
GUIDE_HALF_M = {"elevated_rail": 4.5, "maglev": 3.5, "monorail": 1.75}


def corridors(model: CityModel, ground) -> list[dict]:
    """Every clearance corridor of the city in world coordinates: kind, id, mode, half
    width and its line [(x, y, z_lo, z_hi)] (z over the finished ground where it stands,
    as the model measures transit; skybridges from their base)."""
    out = []
    for s in sorted(model.skybridges, key=lambda s: s.id):
        base = float(getattr(s, "base_m", None) or 0.0)
        h = SKYBRIDGE_H.get(s.kind) or s.levels * s.level_height_m
        out.append({"kind": "skybridge", "id": s.id, "mode": s.kind,
                    "half_m": s.width_m / 2.0 + 0.2, "base": base,
                    "line": [(p[0], p[1], s.z_m - SKYBRIDGE_DECK_M, s.z_m + h + 0.3)
                             for p in s.line], "abs": True})
    for st in sorted(model.structures, key=lambda s: s.id):
        a = st.attrs or {}
        if not a.get("line_id") or a.get("station") or len(st.line) < 2:
            continue
        mode = a.get("mode")
        if st.kind == "tube":
            # the tube: a square corridor round its axis (the line is its top), 1 m clear
            d = float(a.get("deck_m", TUBE_D_M))
            out.append({"kind": "sky_tube", "id": st.id, "mode": "sky_tube",
                        "half_m": d / 2.0 + 1.0, "line_id": a["line_id"],
                        "line": [(p[0], p[1], p[2] - d - 1.0, p[2] + 1.0) for p in st.line]})
        elif st.kind == "deck" and mode in TRAIN_UP_M:
            out.append({"kind": "guideway", "id": st.id, "mode": mode,
                        "half_m": GUIDE_HALF_M[mode] + 0.5, "line_id": a["line_id"],
                        "line": [(p[0], p[1], p[2] - DECK_DOWN_M[mode] - 0.3,
                                  p[2] + TRAIN_UP_M[mode]) for p in st.line]})
    for c in out:
        if c.get("abs"):
            continue
        # (M13: transit z over the ground where it stands)
        c["line"] = [(x, y, z0 + ground.at(x, y), z1 + ground.at(x, y))
                     for x, y, z0, z1 in c["line"]]
    for c in out:
        xs = [p[0] for p in c["line"]]
        ys = [p[1] for p in c["line"]]
        c["box"] = (min(xs) - c["half_m"], min(ys) - c["half_m"], max(xs) + c["half_m"],
                    max(ys) + c["half_m"])
    return out


def clearances_of(city: "City", k: int, cors: list[dict], ground) -> list[dict]:
    """The corridors a building's asset keeps out of (AG4), in its frame: the stretches of
    each corridor near its footprint's box, z from its base (M13: the building's base_m)."""
    b = city.m.buildings[k]
    ox, oy = city.origins[k]
    ms = city.by_b[k]
    x0 = min(mm.box[0] for mm in ms) - CLEAR_MARGIN_M
    y0 = min(mm.box[1] for mm in ms) - CLEAR_MARGIN_M
    x1 = max(mm.box[2] for mm in ms) + CLEAR_MARGIN_M
    y1 = max(mm.box[3] for mm in ms) + CLEAR_MARGIN_M
    base = float(getattr(b, "base_m", None) or 0.0)
    top = float(b.height_m) + max(CLEAR_OVER_M, 0.2 * float(b.height_m) + 1.5)
    out = []
    for c in cors:
        bx = c["box"]
        if bx[0] > x1 or bx[2] < x0 or bx[1] > y1 or bx[3] < y0:
            continue
        h = c["half_m"]
        ln = c["line"]
        keep = set()
        for i in range(len(ln) - 1):
            p, q = ln[i], ln[i + 1]
            if min(p[0], q[0]) - h > x1 or max(p[0], q[0]) + h < x0 or \
                    min(p[1], q[1]) - h > y1 or max(p[1], q[1]) + h < y0:
                continue
            keep.update((i, i + 1))
        if not keep:
            continue
        # the corridor's z in the building frame: from the building's base (a skybridge's
        # from its own base, the first building's)
        off = (c.get("base", 0.0) - base) if c.get("abs") else -base
        pts = [ln[i] for i in sorted(keep)]
        if min(p[2] for p in pts) + off > top or max(p[3] for p in pts) + off < 0.0:
            continue
        # runs of consecutive kept points (a corridor may pass by twice)
        runs, cur = [], []
        for i in sorted(keep):
            if cur and i != cur[-1] + 1:
                runs.append(cur)
                cur = []
            cur.append(i)
        runs.append(cur)
        for r in runs:
            if len(r) < 2:
                continue
            out.append({"kind": c["kind"], "id": c["id"], "mode": c["mode"],
                        "half_m": C.m(h),
                        "line": [[C.m(ln[i][0] - ox), C.m(ln[i][1] - oy),
                                  C.m(ln[i][2] + off), C.m(ln[i][3] + off)] for i in r]})
    return sorted(out, key=lambda c: (c["kind"], c["id"], c["line"][0]))


def _portal_rec(city: "City", k: int, b, p, look: "_Lookups", ground) -> dict:
    """A sky tube portal (M5) with what AG4 cuts it from: the tube's top line near the
    tower (building frame, z from its base) and its diameter, and the sky station it hosts
    (its platform footprint, track height), if any."""
    ox, oy = city.origins[k]
    base = float(getattr(b, "base_m", None) or 0.0)
    ms = city.by_b[k]
    x0 = min(mm.box[0] for mm in ms) - 12.0
    y0 = min(mm.box[1] for mm in ms) - 12.0
    x1 = max(mm.box[2] for mm in ms) + 12.0
    y1 = max(mm.box[3] for mm in ms) + 12.0
    lines, diam = [], TUBE_D_M
    for st in sorted(look.tubes.get(p.line_id, []), key=lambda s: s.id):
        pts = [tuple(q) for q in st.line]
        near = [i for i in range(len(pts) - 1)
                if not (min(pts[i][0], pts[i + 1][0]) > x1 or
                        max(pts[i][0], pts[i + 1][0]) < x0 or
                        min(pts[i][1], pts[i + 1][1]) > y1 or
                        max(pts[i][1], pts[i + 1][1]) < y0)]
        if not near:
            continue
        diam = float((st.attrs or {}).get("deck_m", TUBE_D_M))
        # each run of the tube piece near the tower its own polyline (a loop's seam may lie
        # in the tower, so pieces are never joined end to end)
        runs: list[list[int]] = []
        for i in sorted({j for i in near for j in (i, i + 1)}):
            if runs and i == runs[-1][-1] + 1:
                runs[-1].append(i)
            else:
                runs.append([i])
        for r in runs:
            if len(r) >= 2:
                lines.append([[C.m(pts[i][0] - ox), C.m(pts[i][1] - oy),
                               C.m(pts[i][2] + ground.at(pts[i][0], pts[i][1]) - base)]
                              for i in r])
    rec = {"line_id": p.line_id, "z": [C.m(p.z0_m), C.m(p.z1_m)], "station": p.station,
           "lines": lines, "diameter_m": C.m(diam)}
    if p.station:
        for s in sorted(look.sky_stations.get(b.id, []), key=lambda s: s.id):
            if p.line_id not in s.line_ids:
                continue
            tz = float((s.attrs or {}).get("track_z_m", s.position[2]))
            rec["station_id"] = s.id
            rec["station_name"] = s.name
            rec["track_z_m"] = C.m(tz + ground.at(s.position[0], s.position[1]) - base)
            rec["platform"] = _poly(s.footprint, ox, oy) if s.footprint else None
            break
    return rec


def _brief(city: City, k: int, b, edges: list[Edge], faced: dict, props: list, look: _Lookups,
           sdata: dict, overrides: dict | None, cors: list | None = None,
           ground=None) -> dict:
    ox, oy = city.origins[k]
    if ground is None:
        from .streets.ctx import Ground
        ground = Ground(city.m)
    fh = b.floor_height_m
    deck = float(b.attrs.get("deck_top_m", 0.0)) if getattr(b, "level", 0) else 0.0
    masses = []
    for j, mm in enumerate(b.masses):
        mass = city.by_b[k][j]
        masses.append({
            "role": mm.role, "shape": mm.shape, "z": [C.m(mm.z0_m), C.m(mm.z1_m)],
            "footprint": {"exterior": [C.pt(p, ox, oy) for p in mass.rings[0]],
                          "holes": [[C.pt(p, ox, oy) for p in h] for h in mass.rings[1:]]},
            "floors": floors_of(mm, fh, deck)})
    edge_recs = [_edge_record(e, ox, oy, faced, k) for e in edges]
    for rec, e in zip(edge_recs, edges):
        rec["mass"] = e.mass.k
    nb = []
    for nid, d in neighbors_of(city, k):
        o = city.m.buildings[city.bidx[nid]]
        nb.append({"id": nid, "d_m": C.m(d), "relation": "party" if d <= PARTY_M else "blind",
                   "height_m": C.m(o.height_m), "type": o.type})

    def loc(x, y, z):
        """On the facade of a mass that spans z, else on the nearest facade at any height
        (a blade sign over a lower shack, a skybridge end on a setback)."""
        return at(locate(edges, x, y, z) or locate(edges, x, y, z, tol_z=math.inf))

    units = []
    for u in b.units:
        (ax, ay), (bx, by) = u.edge
        units.append({"edge": [C.pt(u.edge[0], ox, oy), C.pt(u.edge[1], ox, oy)],
                      "use": u.use, "width_m": C.m(u.width_m), "segment_id": u.segment_id,
                      "awning_m": C.m(u.awning_m), "sign": u.sign,
                      "entrance": C.pt(u.entrance, ox, oy) if u.entrance else None,
                      "at": loc((ax + bx) / 2.0, (ay + by) / 2.0, 0.5)})
    ents = [{"position": C.pt(e.position, ox, oy), "kind": e.kind, "segment_id": e.segment_id,
             "walkway_id": e.walkway_id, "at": loc(e.position[0], e.position[1], 0.5)}
            for e in b.entrances]
    roof = []
    for r in b.roof_items:
        on = None
        for j, mass in enumerate(city.by_b[k]):
            if abs(mass.z1 - r.position[2]) < 0.05 and PL.inside_poly(
                    np.array([r.position[0]]), np.array([r.position[1]]),
                    mass.rings[0], mass.rings[1:])[0]:
                on = j
                break
        roof.append({"kind": r.kind, "position": C.pt3(r.position, ox, oy),
                     "size": [C.m(v) for v in r.size], "yaw_deg": C.deg(r.yaw_deg),
                     "mass": on})
    sky = []
    for s, j in sorted(look.sky.get(b.id, []), key=lambda t: t[0].id):
        end = s.line[0] if j == 0 else s.line[-1]
        # (its deck in the building frame: M13 measures it from the bridge's own base)
        sz = s.z_m + float(getattr(s, "base_m", None) or 0.0) - \
            float(getattr(b, "base_m", None) or 0.0)
        sky.append({"id": s.id, "kind": s.kind, "z_m": C.m(sz), "width_m": C.m(s.width_m),
                    "levels": s.levels, "level_height_m": C.m(s.level_height_m),
                    "other": s.building_ids[1 - j], "end": C.pt(end, ox, oy),
                    "at": loc(end[0], end[1], sz + 0.5)})
    slots = [{"id": s.id, "kind": s.kind, "mount": s.mount, "position": C.pt3(s.position, ox, oy),
              "yaw_deg": C.deg(s.yaw_deg), "width_m": C.m(s.width_m),
              "height_m": C.m(s.height_m), "content": s.content, "prop_id": s.prop_id,
              "roof_item": s.roof_item, "emitter": s.emitter, "two_sided": s.two_sided,
              "at": loc(s.position[0], s.position[1], s.position[2])
              if s.mount != "roof" else None}
             for s in sorted(look.slots.get(b.id, []), key=lambda s: s.id)]
    pois = [{"id": p.id, "kind": p.kind, "sub": p.sub, "name": p.name,
             "unit_index": p.unit_index, "floor": p.floor, "hours": list(p.hours),
             "host_id": p.host_id}
            for p in sorted(look.pois.get(b.id, []), key=lambda p: p.id)]
    plants = [{"id": p.id, "type": p.type, "species": p.species,
               "position": C.pt3(p.position, ox, oy), "height_m": C.m(p.height_m),
               "attrs": p.attrs, "at": loc(p.position[0], p.position[1], p.position[2])}
              for p in sorted(look.plants.get(b.id, []), key=lambda p: p.id)]
    green = [{"id": g.id, "z_m": C.m(g.z_m),
              "polygon": _poly(g.polygon, ox, oy) if g.polygon else None}
             for g in sorted(look.green.get(b.id, []), key=lambda g: g.id)]
    lot = city.lots.get(b.lot_id) if b.lot_id else None
    lot_rec = None
    if lot is not None:
        lot_rec = {"id": lot.id, "polygon": _poly(lot.polygon, ox, oy),
                   "frontage": [{"segment_id": f.segment_id, "road_class": f.road_class,
                                 "length_m": C.m(f.length_m),
                                 "line": [C.pt(p, ox, oy) for p in f.line]}
                                for f in lot.frontage],
                   "main_segment_id": city.mains[k]}
    prop = city.props_.get(b.property_id) if b.property_id else None
    prop_rec = None if prop is None else {
        "id": prop.id, "owner": prop.owner, "complex": prop.complex, "name": prop.name,
        "building_ids": sorted(prop.building_ids)}
    d = city.districts.get(b.district_id) if b.district_id else None
    dist_rec = None if d is None else {
        "id": d.id, "name": d.name, "archetype": d.archetype,
        **{key: d.params.get(key) for key in DISTRICT_KEYS}}
    dstyle = sdata["districts"].get(d.name) if d is not None else None
    era = (dstyle or {}).get("era") or b.style.get("era")
    spec_rec = {key: sdata[key] for key in ("uniqueness", "hero_uniqueness",
                                            "min_gene_distance", "share_parts",
                                            "texel_density_px_m", "texel_density_upper_px_m")}
    spec_rec.update({"era": era, "era_style": sdata["eras"].get(era) if era else None,
                     "district": dstyle,
                     "owner": sdata["owners"].get(prop.owner) if prop else None,
                     "landmark": sdata["landmarks"].get(b.name) if b.landmark and b.name
                     else None})
    rec = {
        "brief_version": BRIEF_VERSION, "id": b.id, "origin": [C.m2(ox), C.m2(oy)],
        "building": {"type": b.type, "use": b.use, "name": b.name, "landmark": b.landmark,
                     "attrs": b.attrs, "lot_id": b.lot_id, "property_id": b.property_id,
                     "district_id": b.district_id, "megasite_id": b.megasite_id,
                     "floors": b.floors, "height_m": C.m(b.height_m), "style": b.style,
                     "floor_grid": {"floor_height_m": C.m(fh),
                                    "base_m": _opt(getattr(b, "base_m", None)),
                                    "plinth_m": _opt(getattr(b, "plinth_m", None))}},
        "masses": masses, "edges": edge_recs, "neighbors": nb,
        "units": units, "entrances": ents, "roof_items": roof,
        "portals": [_portal_rec(city, k, b, p, look, ground) for p in b.portals],
        "skybridges": sky, "sign_slots": slots, "props": props, "plants": plants,
        "green_roofs": green, "pois": pois, "lot": lot_rec, "property": prop_rec,
        "district": dist_rec, "spec": spec_rec,
        "override": (overrides or {}).get(b.id),
        "clearances": clearances_of(city, k, cors or [], ground),
    }
    if getattr(b, "level", 0):
        # M14: a building on a deck: its level and the deck top its ground floor stands on
        rec["building"]["floor_grid"].update(level=b.level, deck_m=C.m(deck))
    return json.loads(C.dumps(rec))


def _opt(v):
    return None if v is None else C.m(v)


def _stats(briefs: dict, city: City) -> dict:
    edges: dict[str, int] = {}
    area: dict[str, float] = {}
    for br in briefs.values():
        for e in br["edges"]:
            edges[e["class"]] = edges.get(e["class"], 0) + 1
            for r in e["regions"]:
                a = (r["s"][1] - r["s"][0]) * (r["z"][1] - r["z"][0])
                area[r["class"]] = area.get(r["class"], 0.0) + a
    return {"buildings": len(briefs),
            "edges": {c: edges[c] for c in CLASSES if c in edges},
            "facade_area_m2": {c: round(area[c]) for c in CLASSES if c in area},
            "props_on_wall": {k: v[0] for k, v in sorted(city.mount_stats.items())},
            "props_off_wall": {k: v[1] for k, v in sorted(city.mount_stats.items())},
            "props_unmounted": {k: v[2] for k, v in sorted(city.mount_stats.items())}}


def brief_hash(brief: dict) -> str:
    return C.digest(brief)


def write_briefs(out_dir: str | Path, model: CityModel, model_sha: str, result: dict) -> Path:
    """`briefs.json`: the briefs and their hashes, canonical JSON."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    hashes = {bid: brief_hash(br) for bid, br in result["briefs"].items()}
    doc = {"assetgen": __version__, "brief_version": BRIEF_VERSION, "city": model.name,
           "model_sha256": model_sha, "spec_sha256": C.digest(result["spec"]),
           "count": len(hashes), "hashes": hashes, "briefs": result["briefs"]}
    path = out / "briefs.json"
    path.write_text(C.dumps(doc) + "\n", encoding="utf-8", newline="\n")
    return path
