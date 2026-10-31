"""AG12's makers: a body piece's bed and surface, a bank piece's slope, wall and stones, and
the riprap stone parts; each from its piece's inputs alone (`pieces.py`).

- **Bed** (`<body>.bed.<tile>`, Nanite): the body's water on a lattice (`BED_CELL_M`), each
  point at the level less `fields.Field.bottom` (plus M13's lift on a terrain city), a slot
  by M16's material, and where a bank's slope runs on under the water (out to its toe) the
  bank's (riprap and road embankments stone, a beach sand, a marsh edge mud); UV0 the plan
  in meters, UV1 the depth (the caustics' strength). Along the edges it shares with other
  water a skirt hangs from the bed `SKIRT_M` down, facing out, so a step between two bodies'
  beds is closed from the shallower side.
- **Surface** (`<body>.water.<tile>`, non-Nanite LODs on lattices of `SURFACE_CELLS_M`): at
  the level; UV0 the plan in meters, UV1 the current (m/s, x east, y north), COLOR_0 foam,
  depth over 12 m, the sea's wave weight.
- **Bank**: a slope from the line (the land's edge, at the ground) out to the waterline at
  the level, a slot by kind (the bed carries it on under the water); riprap stones on it
  from the line to the toe; a stone wall (canal walls along rivers and the sea) from a
  coping at the ground down past the toe.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import shapely

from citygen import dmath as M

from .. import canon as C
from ..streets.kit import Mesh
from ..streets.path import Path, Profile
from . import fields as F
from . import grid as GR
from . import materials as MT

BED_CELL_M = {"sea": 8.0}           # (else 4 m)
BED_CELL_DEFAULT = 4.0
SURFACE_CELLS_M = {"sea": (2.0, 4.0, 8.0, 16.0)}
SURFACE_CELLS_DEFAULT = (4.0, 8.0, 16.0)
LOD_SCREEN = (1.0, 0.4, 0.15, 0.05)
SKIRT_M = 13.0                      # the skirts' depth under the bed
SKIRT_STEP_M = 2.0
DEPTH_SCALE_M = 12.0                # COLOR_0.g: the depth over this
RIPRAP_STEP_M = 0.85
RIPRAP_VARIANTS = 6
WALL_EMBED_M = 0.5                  # a wall goes this far into the bed
COPING_M = 0.45

MAKERS: dict = {}
VERSIONS: dict[str, int] = {}


def maker(name: str, version: int = 1):
    def wrap(fn):
        MAKERS[name] = fn
        VERSIONS[name] = version
        return fn
    return wrap


@dataclass
class NMesh:
    """A numpy mesh of one slot: positions in integer mm (piece frame), the rest per vertex."""
    slot: str
    pos: np.ndarray
    idx: np.ndarray
    nrm: np.ndarray
    uv0: np.ndarray
    uv1: np.ndarray | None = None
    col: np.ndarray | None = None

    @property
    def triangles(self) -> int:
        return len(self.idx) // 3


@dataclass
class Out:
    bed: list = field(default_factory=list)          # [NMesh]
    lods: list = field(default_factory=list)         # [[NMesh]] (surface LODs)
    mesh: Mesh | None = None                         # (a bank's wall)
    nm: list = field(default_factory=list)           # (a bank's slope: [NMesh])
    parts: list = field(default_factory=list)
    notes: dict = field(default_factory=dict)
    empty: str | None = None


def rnd(*parts) -> float:
    h = hashlib.blake2b("|".join(str(p) for p in parts).encode("utf-8"),
                        digest_size=8).digest()
    return int.from_bytes(h, "big") / 18446744073709551616.0


def _region(inp: dict):
    ps = [shapely.Polygon(p["exterior"], p.get("holes", [])) for p in inp["region"]]
    ps = [p for p in ps if not p.is_empty]
    if not ps:
        return None
    return ps[0] if len(ps) == 1 else shapely.MultiPolygon(ps)


def _origin_mm(inp: dict) -> np.ndarray:
    o = inp["origin"]
    return np.array([C.mm(o[0]), C.mm(o[1]), 0], dtype=np.int64)


def _pos(vmm: np.ndarray, z: np.ndarray, org: np.ndarray) -> np.ndarray:
    zmm = np.rint(z * 1000.0).astype(np.int64)
    return np.stack([vmm[:, 0] - org[0], vmm[:, 1] - org[1], zmm], axis=1)


def _drop_flat(pos: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """Triangles whose rounded plan corners are not counterclockwise (none should be)."""
    a, b, c = pos[tri[:, 0]], pos[tri[:, 1]], pos[tri[:, 2]]
    o = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    return tri[o > 0]


STEEP_NZ = 0.6          # a bed triangle facing up less than this is a step


def _steep(slot, pos, nrm, uv1, tri, cr, org) -> NMesh:
    """Steep bed triangles on vertices of their own, UV0 projected on the vertical plane each
    faces most (meters: along it and up)."""
    n = len(tri)
    v = tri.ravel()
    p = pos[v]
    wx = (p[:, 0] + org[0]) / 1000.0
    wy = (p[:, 1] + org[1]) / 1000.0
    wz = p[:, 2] / 1000.0
    xface = np.repeat(np.abs(cr[:, 0]) >= np.abs(cr[:, 1]), 3)
    uv0 = np.stack([np.where(xface, wy, wx), wz], axis=1)
    return NMesh(slot, p, np.arange(3 * n, dtype=np.int64), nrm[v], uv0, uv1[v], None)


def _sub(slot, pos, nrm, uv0, uv1, col, tri) -> NMesh:
    """The vertices a slot's triangles use, reindexed."""
    used, inv = np.unique(tri.ravel(), return_inverse=True)
    return NMesh(slot, pos[used], inv.astype(np.int64), nrm[used], uv0[used],
                 None if uv1 is None else uv1[used], None if col is None else col[used])


@maker("body", 1)
def make_body(inp: dict) -> Out:
    fd = F.Field(inp)
    region = _region(inp)
    out = Out()
    if region is None:
        out.empty = "no water"
        return out
    water = inp["body"]["water"]
    sea = inp["body"]["kind"] == "sea"
    org = _origin_mm(inp)
    box = inp["box"]
    lift = float(inp.get("lift", 0.0))
    # -- the bed
    cell = BED_CELL_M.get(inp["body"]["kind"], BED_CELL_DEFAULT)
    # (the bed leaves out each sloped bank's dry strip, which the bank's mesh covers, so its
    # edge runs along the bank's waterline and they meet there, not across a lattice cell)
    bed_region = _bed_region(region, inp.get("banks") or [])
    dry = round(region.area - (bed_region.area if bed_region is not None else 0.0), 1)
    out.notes["dry_m2"] = dry
    vmm, tri = GR.mesh(bed_region, box, cell)
    if len(tri):
        xs, ys = vmm[:, 0] / 1000.0, vmm[:, 1] / 1000.0
        kd = fd.nearest(xs, ys)
        depth = fd.bottom(xs, ys, kd)
        z = fd.level(xs, ys) - depth + lift
        pos = _pos(vmm, z, org)
        tri = _drop_flat(pos, tri)
        nrm = GR.normals(pos, tri)
        uv0 = np.stack([xs, ys], axis=1)
        uv1 = np.stack([np.round(depth, 3), np.zeros(len(xs))], axis=1)
        own = MT.BED_SLOT[inp["body"]["material"]]
        slot_of = np.full(len(tri), own, dtype=object)
        if fd.tree is not None:
            cx = (xs[tri[:, 0]] + xs[tri[:, 1]] + xs[tri[:, 2]]) / 3.0
            cy = (ys[tri[:, 0]] + ys[tri[:, 1]] + ys[tri[:, 2]]) / 3.0
            k, d = fd.nearest(cx, cy)
            w = fd.W[k]
            toe_d = w * (1.0 + fd.TOE[k] / np.maximum(fd.H[k], 0.1))
            for kind, slot in MT.BANK_BED.items():
                if slot is None or slot == own:
                    continue
                kk = np.array([x == kind for x in fd.kind])[k]
                slot_of = np.where(kk & (d < toe_d + 0.5), slot, slot_of)
        # (a steep triangle, a step where the nearest bank changes or beside a wall, takes its
        # UV0 from the vertical plane it faces most, on vertices of its own: from above its
        # texels would stretch down the step)
        a, b, c = pos[tri[:, 0]], pos[tri[:, 1]], pos[tri[:, 2]]
        cr = np.cross((b - a).astype(np.float64), (c - a).astype(np.float64))
        L = np.sqrt((cr * cr).sum(axis=1))
        steep = cr[:, 2] < STEEP_NZ * np.maximum(L, 1e-9)
        for slot in sorted(set(slot_of.tolist())):
            sel = tri[(slot_of == slot) & ~steep]
            if len(sel):
                out.bed.append(_sub(slot, pos, nrm, uv0, uv1, None, sel))
            st = tri[(slot_of == slot) & steep]
            if len(st):
                out.bed.append(_steep(slot, pos, nrm, uv1, st, cr[(slot_of == slot) & steep],
                                      org))
        out.notes["bed"] = {"cell_m": cell, "min_z": C.m(float(z.min())),
                            "max_depth": C.m(float(depth.max()))}
    skirt = _skirts(inp, fd, org, lift)
    if inp.get("open"):
        out.notes["open"] = len(inp["open"])
    if skirt is not None:
        own = MT.BED_SLOT[inp["body"]["material"]]
        out.bed.append(NMesh(own, *skirt))
        out.notes["skirt"] = len(skirt[1]) // 3
    # -- the surface, a LOD per lattice
    cells = SURFACE_CELLS_M.get(inp["body"]["kind"], SURFACE_CELLS_DEFAULT)
    for c in cells:
        vmm, tri = GR.mesh(region, box, c)
        if not len(tri):
            break
        xs, ys = vmm[:, 0] / 1000.0, vmm[:, 1] / 1000.0
        kd = fd.nearest(xs, ys)
        z = fd.level(xs, ys)
        pos = _pos(vmm, z, org)
        tri = _drop_flat(pos, tri)
        depth = fd.bottom(xs, ys, kd) - lift
        vx, vy = fd.flow(xs, ys, depth, kd)
        foam = fd.foam(xs, ys, kd)
        wav = fd.waves(xs, ys, kd) if sea else np.zeros(len(xs))
        col = np.stack([foam, np.clip(depth / DEPTH_SCALE_M, 0.0, 1.0), wav,
                        np.ones(len(xs))], axis=1)
        col = np.rint(np.clip(col, 0.0, 1.0) * 255.0).astype(np.uint8)
        nm = NMesh(f"water.{water}", pos, tri.ravel().astype(np.int64), GR.normals(pos, tri),
                   np.stack([xs, ys], axis=1),
                   np.stack([np.round(vx, 3), np.round(vy, 3)], axis=1), col)
        out.lods.append([nm])
    if not out.bed and not out.lods:
        out.empty = "no water"
    return out


def _skirts(inp, fd, org, lift):
    """Quads down from the bed along the edges shared with other water, facing out."""
    lines = inp.get("open") or []
    if not lines:
        return None
    region = _region(inp)
    P, Nn, U, I = [], [], [], []
    for ln in lines:
        pts = [tuple(p) for p in ln]
        if len(pts) < 2:
            continue
        dense = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            L = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            n = max(1, int(L / SKIRT_STEP_M + 0.999))
            for k in range(1, n + 1):
                dense.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
        xs = np.array([p[0] for p in dense])
        ys = np.array([p[1] for p in dense])
        top = fd.level(xs, ys) - fd.bottom(xs, ys) + lift
        bot = top - SKIRT_M
        s = 0.0
        for i in range(len(dense) - 1):
            (ax, ay), (bx, by) = dense[i], dense[i + 1]
            L = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
            if L < 0.01:
                continue
            tx, ty = (bx - ax) / L, (by - ay) / L
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
            # the outward side: away from the body's own water
            left_in = region.covers(shapely.Point(mx - ty * 0.2, my + tx * 0.2))
            nx, ny = (ty, -tx) if left_in else (-ty, tx)
            q = [(ax, ay, top[i], s), (bx, by, top[i + 1], s + L), (bx, by, bot[i + 1], s + L),
                 (ax, ay, bot[i], s)]
            if not left_in:
                q = q[::-1]                    # (counterclockwise seen from outside)
            base = len(P)
            for x, y, z, u in q:
                P.append((C.mm(x) - org[0], C.mm(y) - org[1], C.mm(z)))
                Nn.append((nx, ny, 0.0))
                U.append((u, z))
            I += [base, base + 1, base + 2, base, base + 2, base + 3]
            s += L
    if not I:
        return None
    pos = np.array(P, dtype=np.int64)
    idx = np.array(I, dtype=np.int64).reshape(-1, 3)
    a, b, c = pos[idx[:, 0]], pos[idx[:, 1]], pos[idx[:, 2]]
    ok = np.any(np.cross(b - a, c - a) != 0, axis=1)
    idx = idx[ok]
    return pos, idx.ravel(), np.array(Nn, dtype=np.float64), np.array(U, dtype=np.float64)


# --- banks ---------------------------------------------------------------------------------

def _level_fn(level: dict):
    fd = F.Field({"body": {"depth_m": 0.0, "profile": "flat", "reach_m": 1.0},
                  "level": level})
    return lambda x, y: float(fd.level(np.array([x]), np.array([y]))[0])


@maker("bank", 1)
def make_bank(inp: dict) -> Out:
    k = inp["bank"]
    try:
        P = Path(k["line"])
    except ValueError:
        return Out(empty="degenerate line")
    out = Out()
    mesh = Mesh(inp["origin"])
    lv = _level_fn(inp["level"])
    gnd = inp.get("ground")
    gp = None
    if gnd and len(gnd) == len(k["line"]):
        cum = [0.0]
        for a, b in zip(k["line"], k["line"][1:]):
            cum.append(cum[-1] + ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5)
        gp = Profile(list(zip(cum, gnd)))

    def ground(s):
        return gp(s) if gp is not None else 0.0
    kind = k["kind"]
    if kind == "canal_wall":
        _wall(mesh, P, k, lv, ground, out)
        out.mesh = mesh
    else:
        _slope(k, inp, ground, out)
        if kind == "riprap":
            out.parts = _stones(P, k, lv, ground, inp["origin"])
    return out


BANK_STEP_M = 2.0


def _stations(k: dict):
    """(s, x, y, nx, ny, miter) along a bank's line every `BANK_STEP_M` and at its vertices."""
    try:
        P = Path(k["line"])
    except ValueError:
        return None, []
    return P, [(s, *P.frame(s, vi)) for s, vi in P.stations(0.0, P.L, BANK_STEP_M)]


def _wl(x, y, nx, ny, mk, w) -> tuple[float, float]:
    """A point of a bank's waterline (on citygen's 0.01 m grid, as the bed's edge): `width`
    out along the normal, not mitered, so it is `width` from the line also at a vertex (where
    the bed's slope, measured from the nearest point of the line, meets the surface)."""
    return C.m2(x + nx * w), C.m2(y + ny * w)


def strip(k: dict):
    """A sloped bank's dry strip: from its line out to its waterline (its line moved `width`
    out over the water), the polygon its mesh covers; None if degenerate."""
    w = max(float(k["w"]), 0.05)
    _, st = _stations(k)
    if len(st) < 2:
        return None
    line = [(C.m2(x), C.m2(y)) for s, x, y, nx, ny, mk in st]
    wl = [_wl(x, y, nx, ny, mk, w) for s, x, y, nx, ny, mk in st]
    p = shapely.make_valid(shapely.Polygon(line + wl[::-1]))
    # (where the waterline folds over at a bend the ring crosses itself: its loops are the
    # strip too, and the holes they leave are filled)
    parts = [shapely.Polygon(q.exterior) for q in GR._polys(p) if q.area > 1e-6]
    if not parts:
        return None
    p = shapely.union_all(parts, grid_size=0.001)
    return p if not p.is_empty else None


def _bed_region(region, banks):
    strips = [s for k in banks if k["kind"] not in F.WALLS for s in [strip(k)]
              if s is not None]
    if not strips:
        return region
    dry = shapely.union_all(strips, grid_size=0.01)
    out = shapely.difference(region, dry, grid_size=0.01)
    ps = [p for p in GR._polys(out) if p.area > 1e-6]
    if not ps:
        return None
    out = ps[0] if len(ps) == 1 else shapely.MultiPolygon(ps)
    return shapely.normalize(out)


BANK_CELL_M = 2.0


def _slope(k: dict, inp: dict, ground, out: Out) -> None:
    """A sloped bank: its dry strip (the polygon the bed leaves out) on a 2 m lattice, each
    point at the ground at the line's nearest point, falling to the level at `width` from
    the line (the bed's slope: they meet along the waterline, where the strip's vertices are
    at the level); UV0 the plan in meters (the slopes are gentle: 1 in 1.5 at the most)."""
    poly = strip(k)
    if poly is None:
        out.empty = "degenerate strip"
        return
    ps = [p for p in GR._polys(poly) if p.area > 1e-6]
    if not ps:
        out.empty = "degenerate strip"
        return
    poly = ps[0] if len(ps) == 1 else shapely.MultiPolygon(ps)
    x0, y0, x1, y1 = poly.bounds
    vmm, tri = GR.mesh(poly, (x0, y0, x1, y1), BANK_CELL_M)
    if not len(tri):
        out.empty = "degenerate strip"
        return
    w = max(float(k["w"]), 0.05)
    xs, ys = vmm[:, 0] / 1000.0, vmm[:, 1] / 1000.0
    line = shapely.LineString(k["line"])
    pts = shapely.points(np.stack([xs, ys], axis=1))
    d = np.round(shapely.distance(line, pts), 6)
    s = shapely.line_locate_point(line, pts)
    top = np.array([ground(v) for v in s.tolist()])
    fd = F.Field({"body": {"depth_m": 0.0, "profile": "flat", "reach_m": 1.0},
                  "level": inp["level"]})
    lvl = fd.level(xs, ys)
    z = top - (top - lvl) * np.clip(d / w, 0.0, 1.0)
    # (the waterline's own vertices at the level, where the bed's edge runs)
    _, st = _stations(k)
    wl = {(C.mm(a), C.mm(b)) for sx, x, y, nx, ny, mk in st for a, b in [_wl(x, y, nx, ny, mk, w)]}
    on = np.array([(int(a), int(b)) in wl for a, b in vmm.tolist()], dtype=bool)
    z = np.where(on, lvl, z)
    org = _origin_mm(inp)
    pos = _pos(vmm, z, org)
    tri = _drop_flat(pos, tri)
    nm = NMesh(f"bank.{k['kind']}", pos, tri.ravel().astype(np.int64), GR.normals(pos, tri),
               np.stack([xs, ys], axis=1))
    out.nm = [nm]
    edge = [(x, y) for sx, x, y, nx, ny, mk in st]
    step = max(1, len(st) // 40)
    out.notes["edge"] = [[C.m(a), C.m(b), C.m(float(fd.level(np.array([a]), np.array([b]))[0]))]
                         for sx, x, y, nx, ny, mk in st[::step] for a, b in [_wl(x, y, nx, ny,
                                                                               mk, w)]]


def _wall(mesh: Mesh, P: Path, k: dict, lv, ground, out: Out) -> None:
    """A stone wall along the line (the water on its left) from a coping at the ground down
    past the toe into the bed."""
    toe = float(k["toe"])
    u = 0.0
    feet = []
    pts = P.p
    cums = P.cum
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        L = cums[i + 1] - cums[i]
        if L < 0.01:
            continue
        za, zb = ground(cums[i]) + 0.03, ground(cums[i + 1]) + 0.03
        ba = lv(a[0], a[1]) - toe - WALL_EMBED_M
        bb = lv(b[0], b[1]) - toe - WALL_EMBED_M
        mesh.wall("wall.stone", b, a, bb, zb, ba, za, u)        # (facing the water, left)
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        ox, oy = uy * COPING_M, -ux * COPING_M                  # (the land side, right)
        mesh.quad("wall.coping", (a[0], a[1], za + 0.02), (a[0] + ox, a[1] + oy, za + 0.02),
                  (b[0] + ox, b[1] + oy, zb + 0.02), (b[0], b[1], zb + 0.02))
        feet.append((a[0] - uy * 0.3, a[1] + ux * 0.3, ba))
        u += L
    step = max(1, len(feet) // 40)
    out.notes["foot"] = [[C.m(x), C.m(y), C.m(z)] for x, y, z in feet[::step]]


def _stones(P: Path, k: dict, lv, ground, origin) -> list[dict]:
    """Riprap stones on a jittered lattice over the slope, from the line to the toe."""
    w = max(float(k["w"]), 0.05)
    h = max(float(k["h"]), 0.1)
    toe = float(k["toe"])
    reach = w * (1.0 + toe / h)
    ox, oy = origin
    by_kind: dict[str, list] = {}
    nt = max(1, int(reach / RIPRAP_STEP_M))
    s = RIPRAP_STEP_M / 2.0
    i = 0
    while s < P.L:
        x, y, nx, ny, _ = P.frame(s)
        zt = ground(s)
        for j in range(nt):
            key = (k["id"], i, j)
            t = (j + 0.25 + 0.5 * rnd(*key, "t")) * reach / nt
            ds = (rnd(*key, "s") - 0.5) * RIPRAP_STEP_M * 0.6
            px, py, pnx, pny, _ = P.frame(min(max(s + ds, 0.0), P.L))
            sx, sy = px + pnx * t, py + pny * t
            zw = lv(sx, sy)
            if t <= w:
                z = zt + (zw - zt) * t / w
            else:
                z = zw - h * (t - w) / w
            sc = 0.55 + 0.7 * rnd(*key, "scale")
            yaw = C.deg(360.0 * rnd(*key, "yaw"))
            var = int(rnd(*key, "v") * RIPRAP_VARIANTS) % RIPRAP_VARIANTS
            by_kind.setdefault(f"part.riprap.r{var}", []).append(
                [C.m(sx - ox), C.m(sy - oy), C.m(z - 0.18 * sc), yaw, C.m2(sc),
                 C.m2(sc * (0.8 + 0.3 * rnd(*key, "sy"))), C.m2(sc * 0.75)])
        s += RIPRAP_STEP_M
        i += 1
    return [{"kind": kd, "xforms": xf} for kd, xf in sorted(by_kind.items())]


def stone_part(k: int) -> Mesh:
    """A riprap stone (about 0.9 x 0.7 x 0.5 m, its base 0.2 m under z 0): a sphere of 6 by
    10 vertices, each radius jittered by a hash, squashed."""
    mesh = Mesh((0.0, 0.0))
    nlat, nlon = 6, 10
    rows, uvs = [], []
    for a in range(nlat + 1):
        phi = M.PI * a / nlat - M.PI / 2.0
        row, uv = [], []
        for b in range(nlon + 1):
            th = 2.0 * M.PI * (b % nlon) / nlon
            pole = a in (0, nlat)
            r = 1.0 if pole else 0.78 + 0.4 * rnd("riprap", k, a, b % nlon)
            cx = M.cos(phi) * M.cos(th) * r * 0.45
            cy = M.cos(phi) * M.sin(th) * r * 0.35
            cz = (M.sin(phi) * r * 0.27) + 0.07
            if cz < -0.2:
                cz = -0.2 + (cz + 0.2) * 0.3                   # (a flatter base)
            row.append((cx, cy, cz))
            uv.append((b * 0.25, a * 0.2))
        rows.append(row)
        uvs.append(uv)
    mesh.grid("stone.riprap", rows, uvs, flip=True)          # (outward)
    return mesh
