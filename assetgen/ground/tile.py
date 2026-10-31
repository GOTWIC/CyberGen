"""One tile of the ground stage (in a worker): a pure function of its job (`gather.py`).

**Mask** (`MASK_PX` square, a pixel per `CELL_M`, row 0 the tile's south edge, as AG6's
images run with v): R wear (each desire line its own wear across its width, falling to 0 a
meter past it; the piece's own wear under it at 0.35), G shade (M16's 4 m raster bilinear,
tree crowns at 0.55 to 0.8, 1 under a deck), B edge (1 at the border of a surface, 2/3 and
1/3 one and two pixels in), A moisture (1 at the water's edge, 0 from 60 m, on a 2 m grid
bilinear).

**Ground mesh**: every piece clipped to the tile (on the 1 cm grid), triangulated exactly
on its millimeters, `Z_LIFT_M` over the ground (on M13's terrain cut by its 4 m cells, each
vertex on the ground grid with the ground's normal), a primitive per surface
(`ground.<surface>.<tile>`); UV0 the plan position in meters.

**Grass**: a candidate per mask pixel inside a grass-bearing piece (not under a deck),
jittered in it, kept with `kinds`' probability under the tile's cap; its clump kind from the
piece's mix (more ferns in deep shade and under crowns, reeds on wet ground, weeds where it
is neglected), a variant, yaw and scale by hashes of its world cell (so a tile's grass does
not depend on how the city is cut into jobs). A clump stands only where its footprint (its
kind's radius times its scale) lies inside the grass-bearing land, clear of the desire
lines, decks and tree trunks.
"""

from __future__ import annotations

import io
import math
import time

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon

from citygen import geom as G

from .. import canon as C
from ..gltf import Gltf, Primitive
from ..triangulate import TriangulationError, triangulate
from . import clumps as CL
from . import kinds as K

TRUNK_M = 0.35
FINE_M = 0.001                 # the grass's footprint overlays
SLOPE_FEW = 0.577              # tan 30 degrees: half the grass
SLOPE_NONE = 0.839             # tan 40 degrees: none
STEEP_NZ = 0.82                # a ground triangle steeper than about 35 degrees is box mapped
DESIRE_FADE_M = 1.0
CANOPY = (0.55, 0.25)          # shade under a crown: base + rise toward the trunk
KL = sorted(K.CLUMPS)
SALT = {"keep": 1, "jx": 2, "jy": 3, "kind": 4, "var": 5, "yaw": 6, "scale": 7}
FERNY = ("mown_lawn", "park_lawn", "meadow", "wasteland", "planted_bed")
REEDY = ("park_lawn", "meadow", "wasteland", "marsh")
WEEDY = ("mown_lawn", "park_lawn", "meadow", "planted_bed")
_M1 = np.uint64(0xBF58476D1CE4E5B9)
_M2 = np.uint64(0x94D049BB133111EB)
_G = np.uint64(0x9E3779B97F4A7C15)


def _mix(x: np.ndarray) -> np.ndarray:
    x = (x ^ (x >> np.uint64(30))) * _M1
    x = (x ^ (x >> np.uint64(27))) * _M2
    return x ^ (x >> np.uint64(31))


def uhash(ix: np.ndarray, iy: np.ndarray, salt: int) -> np.ndarray:
    """A uniform number in [0, 1) per world cell (splitmix64 on integer arithmetic that wraps
    the same everywhere)."""
    with np.errstate(over="ignore"):
        a = ix.astype(np.int64).view(np.uint64)
        b = iy.astype(np.int64).view(np.uint64)
        h = _mix(a * _G + _mix(b + np.uint64(salt * 0x632BE59BD9B4E019 & 0xFFFFFFFFFFFFFFFF)))
    return (h >> np.uint64(11)).astype(np.float64) * (1.0 / 9007199254740992.0)


def _poly(rings) -> Polygon:
    return Polygon(rings[0], rings[1:])


def _bilinear(rows, ox, oy, cell, X, Y, centered: bool) -> np.ndarray:
    A = np.asarray(rows, dtype=np.float64)
    ny, nx = A.shape
    fx = (X - ox) / cell - (0.5 if centered else 0.0)
    fy = (Y - oy) / cell - (0.5 if centered else 0.0)
    fx = np.clip(fx, 0.0, nx - 1.000001)
    fy = np.clip(fy, 0.0, ny - 1.000001)
    i = fx.astype(np.int64)
    j = fy.astype(np.int64)
    tx, ty = fx - i, fy - j
    if nx == 1 or ny == 1:
        return A[np.minimum(j, ny - 1), np.minimum(i, nx - 1)]
    i1, j1 = np.minimum(i + 1, nx - 1), np.minimum(j + 1, ny - 1)
    h0 = A[j, i] * (1.0 - tx) + A[j, i1] * tx
    h1 = A[j1, i] * (1.0 - tx) + A[j1, i1] * tx
    return h0 * (1.0 - ty) + h1 * ty


class _Ground:
    """M13's ground under the tile (node grid, bilinear), or flat."""

    def __init__(self, g):
        self.g = g
        if g is not None:
            self.A = np.asarray(g["rows_mm"], dtype=np.float64) / 1000.0

    def at(self, X, Y) -> np.ndarray:
        if self.g is None:
            return np.zeros(np.shape(X))
        return _bilinear(self.A, self.g["x0"], self.g["y0"], self.g["cell"], np.asarray(X),
                         np.asarray(Y), False)

    def normal(self, x, y) -> tuple[float, float, float]:
        if self.g is None:
            return (0.0, 0.0, 1.0)
        e = 0.25
        dzx = (float(self.at(x + e, y)) - float(self.at(x - e, y))) / (2.0 * e)
        dzy = (float(self.at(x, y + e)) - float(self.at(x, y - e))) / (2.0 * e)
        L = math.sqrt(dzx * dzx + dzy * dzy + 1.0)
        return (-dzx / L, -dzy / L, 1.0 / L)


def _segments(geom) -> list[LineString]:
    out = []
    for p in G.parts(geom):
        for r in [p.exterior, *p.interiors]:
            cs = list(r.coords)
            out += [LineString([cs[k], cs[k + 1]]) for k in range(len(cs) - 1)]
    return out


def _items(job) -> list[dict]:
    """The pieces and the verges as one list (a verge a mown lawn of its own)."""
    out = []
    for p in job["pieces"]:
        out.append({**p, "mode": "piece"})
    for v in job["verges"]:
        out.append({"id": v["id"], "kind": "mown_lawn", "surface": "lawn",
                    "district": v["district"], "rings": v["rings"], "area": None,
                    "maint": 0.6, "wear": 0.05, "shade": 0.0, "moist": 0.0, "slope": 0.0,
                    "desire": [], "palette": v["palette"], "mode": v["mode"],
                    "zline": v["zline"]})
    return out


def _mask(job, items, polys, gr: _Ground, X, Y):
    n, c = K.MASK_PX, K.CELL_M
    x0, y0, x1, y1 = job["box"]
    pidx = np.full((n, n), -1, dtype=np.int32)
    for k, p in enumerate(polys):
        bx0, by0, bx1, by1 = p.bounds
        i0, i1 = max(0, int(math.floor((bx0 - x0) / c))), min(n, int(math.ceil((bx1 - x0) / c)))
        j0, j1 = max(0, int(math.floor((by0 - y0) / c))), min(n, int(math.ceil((by1 - y0) / c)))
        if i1 <= i0 or j1 <= j0:
            continue
        ins = shapely.contains_xy(p, X[j0:j1, i0:i1], Y[j0:j1, i0:i1])
        sub = pidx[j0:j1, i0:i1]
        sub[ins] = k
    # surfaces (an island verge draws none: AG7's median top is its ground)
    surfs = sorted({it["surface"] for it in items})
    sid = np.array([surfs.index(it["surface"]) if it["mode"] != "island" else -2
                    for it in items] + [-1], dtype=np.int32)
    S = sid[pidx]                                  # (pidx -1 picks the trailing -1)
    # shade: M16's raster, tree crowns, decks
    sh = job["shade"]
    shade = _bilinear(sh["rows"], sh["x0"], sh["y0"], sh["cell"], X, Y, True) / 255.0
    trunks = []
    for tid, tx, ty, r in job["trees"]:
        trunks.append((tx, ty))
        i0, i1 = max(0, int((tx - r - x0) / c)), min(n, int((tx + r - x0) / c) + 2)
        j0, j1 = max(0, int((ty - r - y0) / c)), min(n, int((ty + r - y0) / c) + 2)
        if i1 <= i0 or j1 <= j0:
            continue
        d = np.hypot(X[j0:j1, i0:i1] - tx, Y[j0:j1, i0:i1] - ty)
        v = np.where(d < r, CANOPY[0] + CANOPY[1] * (1.0 - d / max(r, 0.1)), 0.0)
        shade[j0:j1, i0:i1] = np.maximum(shade[j0:j1, i0:i1], v)
    canopy = np.zeros((n, n), dtype=bool)
    for tid, tx, ty, r in job["trees"]:
        i0, i1 = max(0, int((tx - r - x0) / c)), min(n, int((tx + r - x0) / c) + 2)
        j0, j1 = max(0, int((ty - r - y0) / c)), min(n, int((ty + r - y0) / c) + 2)
        if i1 > i0 and j1 > j0:
            canopy[j0:j1, i0:i1] |= np.hypot(X[j0:j1, i0:i1] - tx, Y[j0:j1, i0:i1] - ty) < r
    decked = np.zeros((n, n), dtype=bool)
    decks = [_poly(r) for r in job["decks"]]
    for dp in decks:
        decked |= shapely.contains_xy(dp, X, Y)
    shade = np.where(decked, 1.0, np.clip(shade, 0.0, 1.0))
    # moisture on a 2 m grid
    k4 = 4
    xs2 = X[k4 // 2::k4, k4 // 2::k4]
    ys2 = Y[k4 // 2::k4, k4 // 2::k4]
    moist = np.zeros((n, n))
    if job["water"]:
        segs = []
        for poly_rings in job["water"]:
            segs += _segments(_poly(poly_rings))
        if segs:
            tree = shapely.STRtree(segs)
            pts = shapely.points(xs2.ravel(), ys2.ravel())
            _, dist = tree.query_nearest(pts, return_distance=True, all_matches=False)
            m2 = np.clip(1.0 - np.round(dist, 3) / 60.0, 0.0, 1.0).reshape(xs2.shape)
            moist = _bilinear(m2, x0, y0, c * k4, X, Y, True)
    # wear: the pieces' own, then their desire lines
    wbg = np.array([0.35 * float(it["wear"]) for it in items] + [0.0])
    wear = wbg[pidx]
    corridors = []
    for it in items:
        for line, w, dw in it["desire"]:
            ln = LineString(line)
            corridors.append(ln.buffer(w / 2.0 + 0.1, cap_style="flat"))
            reach = w / 2.0 + DESIRE_FADE_M
            bx0, by0, bx1, by1 = ln.bounds
            i0 = max(0, int(math.floor((bx0 - reach - x0) / c)))
            i1 = min(n, int(math.ceil((bx1 + reach - x0) / c)))
            j0 = max(0, int(math.floor((by0 - reach - y0) / c)))
            j1 = min(n, int(math.ceil((by1 + reach - y0) / c)))
            if i1 <= i0 or j1 <= j0:
                continue
            d = np.round(shapely.distance(ln, shapely.points(X[j0:j1, i0:i1],
                                                             Y[j0:j1, i0:i1])), 3)
            core = w / 2.0 - 0.1
            v = float(dw) * np.clip(1.0 - (d - core) / (DESIRE_FADE_M + 0.1), 0.0, 1.0) ** 1.5
            wear[j0:j1, i0:i1] = np.maximum(wear[j0:j1, i0:i1], v)
    # edges: one to three pixels in from where the surface changes
    pad = np.pad(S, 3, mode="edge")
    edge = np.zeros((n, n))
    for t in (1, 2, 3):
        diff = np.zeros((n, n), dtype=bool)
        for dx, dy in ((t, 0), (-t, 0), (0, t), (0, -t), (t, t), (-t, -t), (t, -t), (-t, t)):
            diff |= pad[3 + dy:3 + dy + n, 3 + dx:3 + dx + n] != S
        edge = np.where((edge == 0.0) & diff, (4 - t) / 3.0, edge)
    edge = np.where(S < 0, 1.0, edge)

    def u8(a):
        return np.floor(np.clip(a, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    mask = np.stack([u8(wear), u8(shade), u8(edge), u8(moist)], axis=2)
    return {"pidx": pidx, "mask": mask, "canopy": canopy, "decked": decked,
            "corridors": corridors, "decks": decks, "trunks": trunks}


def _scatter(job, items, polys, mk, gr: _Ground, X, Y):
    n, c = K.MASK_PX, K.CELL_M
    x0, y0, x1, y1 = job["box"]
    pidx, mask = mk["pidx"], mk["mask"]
    dens = np.array([K.GRASS[it["kind"]][0] for it in items] + [0.0])
    D = dens[pidx]
    D = np.where(mk["decked"], 0.0, D)
    w = mask[:, :, 0].astype(np.float64) / 255.0
    s = mask[:, :, 1].astype(np.float64) / 255.0
    m = mask[:, :, 3].astype(np.float64) / 255.0
    fs = np.clip(np.where(s <= 0.5, 1.0, 1.0 - 1.4 * (s - 0.5)), 0.3, 1.0)
    fg = np.ones((n, n))
    if gr.g is not None:
        # the slope at each candidate (M13): fewer from 30 degrees, none past 40 (the steps
        # of the retaining walls, cliffs)
        e = c / 2.0
        gx = (gr.at(X + e, Y) - gr.at(X - e, Y)) / c
        gy = (gr.at(X, Y + e) - gr.at(X, Y - e)) / c
        t = np.hypot(gx, gy)
        fg = np.where(t > SLOPE_NONE, 0.0, np.where(t > SLOPE_FEW, 0.5, 1.0))
    p = D * (c * c) * (1.0 - w) ** 2 * fs * (1.0 + 0.6 * m) * fg
    total = math.fsum(p[p > 0.0].tolist())
    kt = min(1.0, K.TILE_INSTANCES / total) if total > 0.0 else 1.0
    ix0, iy0 = int(round(x0 / c)), int(round(y0 / c))
    IX = ix0 + np.arange(n)[None, :] + np.zeros((n, 1), dtype=np.int64)
    IY = iy0 + np.arange(n)[:, None] + np.zeros((1, n), dtype=np.int64)
    keep = (p > 0.0) & (uhash(IX, IY, SALT["keep"]) < p * kt)
    jj, ii = np.nonzero(keep)
    if not len(jj):
        return {}, {"candidates": 0, "kept": 0, "cap": kt, "expected": total}
    ixs, iys = IX[jj, ii], IY[jj, ii]
    px = (ixs + uhash(ixs, iys, SALT["jx"])) * c
    py = (iys + uhash(ixs, iys, SALT["jy"])) * c
    it_k = pidx[jj, ii]
    sv, mv, cv = s[jj, ii], m[jj, ii], mk["canopy"][jj, ii]
    # the mix: the kind's, then shade, wet and neglect
    W = np.zeros((len(jj), len(KL)))
    kinds_i = [items[k]["kind"] for k in range(len(items))]
    for k, it in enumerate(items):
        sel = it_k == k
        if not sel.any():
            continue
        for name, wt in K.GRASS[it["kind"]][1].items():
            W[sel, KL.index(name)] = wt
        kd = it["kind"]
        if kd in FERNY:
            W[sel, KL.index("fern")] += 2.5 * np.maximum(0.0, sv[sel] - 0.6) + 0.25 * cv[sel]
        if kd in REEDY:
            W[sel, KL.index("reeds")] += 1.2 * np.maximum(0.0, mv[sel] - 0.7)
        if kd in WEEDY and float(it["maint"]) < 0.4:
            W[sel, KL.index("weeds")] += 0.4 - float(it["maint"])
    cum = np.cumsum(W, axis=1)
    pick = uhash(ixs, iys, SALT["kind"]) * cum[:, -1]
    ki = np.minimum((cum <= pick[:, None]).sum(axis=1), len(KL) - 1)
    scale = np.round((0.8 + 0.45 * uhash(ixs, iys, SALT["scale"])) *
                     min(K.MAX_SCALE_UP, kt ** -0.5), 2)
    foot = np.array([K.CLUMPS[KL[k]][1] for k in ki]) * scale
    # where a footprint may stand: the grass-bearing land, clear of desire lines, decks and
    # trunks; the pieces and the verges apart (a median lawn may lie a few millimeters from a
    # lot across the road's edge: their union would bridge the road)
    cut = list(mk["corridors"]) + list(mk["decks"])
    cut += [shapely.Point(tx, ty).buffer(TRUNK_M, 8) for tx, ty in mk["trunks"]]
    for it in items:
        if it["mode"] == "strip":
            cut.append(LineString([q[:2] for q in it["zline"]]).buffer(
                0.45, cap_style="flat"))
    # (on a 1 mm grid: the pieces' vertices are on the 1 cm grid, and a 1 cm overlay would
    # close a building's sub-centimeter sliver between two of them)
    ko = job.get("keep_out") or {}
    hard = [_poly(r) for r in ko.get("hard", [])] + [_poly(r) for r in job["water"]]
    row = [_poly(r) for r in ko.get("row", [])]
    cutg = shapely.union_all(cut + hard, grid_size=FINE_M) if cut or hard else None
    rowg = shapely.union_all(row, grid_size=FINE_M) if row else None
    ok = np.zeros(len(px), dtype=bool)
    verge = np.array([it["mode"] != "piece" for it in items])[it_k]
    for want in (False, True):
        grassy = [polys[k] for k, it in enumerate(items)
                  if K.GRASS[it["kind"]][0] > 0.0 and (it["mode"] != "piece") == want]
        allowed = shapely.union_all(grassy, grid_size=FINE_M) if grassy else Polygon()
        if cutg is not None and not allowed.is_empty:
            allowed = shapely.difference(allowed, cutg, grid_size=FINE_M)
        if rowg is not None and not want and not allowed.is_empty:
            # (a verge lies in its road's right of way: only the pieces keep off it)
            allowed = shapely.difference(allowed, rowg, grid_size=FINE_M)
        sel = np.nonzero(verge == want)[0]
        if allowed.is_empty or not len(sel):
            continue
        sel = sel[shapely.contains_xy(allowed, px[sel], py[sel])]
        segs = _segments(allowed)
        if segs and len(sel):
            tree = shapely.STRtree(segs)
            _, dist = tree.query_nearest(shapely.points(px[sel], py[sel]),
                                         return_distance=True, all_matches=False)
            ok[sel] = np.round(dist, 4) >= foot[sel]
    # heights: the ground (or a verge's surface) under each clump
    z = gr.at(px, py) + K.Z_LIFT_M
    for k, it in enumerate(items):
        if it["mode"] in ("island", "strip"):
            sel = np.nonzero(it_k == k)[0]
            if not len(sel):
                continue
            ln = LineString(it["zline"])
            d = shapely.line_locate_point(ln, shapely.points(px[sel], py[sel]))
            q = shapely.get_coordinates(shapely.line_interpolate_point(ln, d), include_z=True)
            z[sel] = q[:, 2]
    if int(ok.sum()) > K.TILE_INSTANCES:
        # (the cap holds the expected count; a tile over it by chance drops the clumps its
        # draw kept by the least margin)
        ukeep = uhash(ixs, iys, SALT["keep"])
        ratio = ukeep / (p[jj, ii] * kt)
        order = np.lexsort((iys, ixs, ratio))
        live = order[ok[order]]
        ok[live[K.TILE_INSTANCES:]] = False
    var = uhash(ixs, iys, SALT["var"])
    yaw = np.round(360.0 * uhash(ixs, iys, SALT["yaw"]), 1)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    out: dict[str, list] = {}
    for t in np.nonzero(ok)[0].tolist():
        kind = KL[int(ki[t])]
        nv = K.CLUMPS[kind][0]
        fam = CL.family(kind, items[int(it_k[t])]["palette"])
        nd = CL.node(fam, min(int(var[t] * nv), nv - 1))
        sc = float(scale[t])
        out.setdefault(nd, []).append([C.m(float(px[t]) - cx), C.m(float(py[t]) - cy),
                                       C.m(float(z[t])), float(yaw[t]), sc, sc, sc])
    for nd in out:
        out[nd].sort()
    return dict(sorted(out.items())), {"candidates": int(len(px)), "kept": int(ok.sum()),
                                       "cap": round(kt, 4), "expected": round(total, 1),
                                       "kinds": {KL[k]: int(((ki == k) & ok).sum())
                                                 for k in range(len(KL))
                                                 if ((ki == k) & ok).any()}}


def _cdt(q, mm) -> list[tuple[int, int, int]] | None:
    """Triangles of a polygon by GEOS's constrained Delaunay triangulation, as indices into
    its rings' vertices (mm: the rings in integer millimeters), counterclockwise; None when a
    triangle has a vertex that is not one of them."""
    idx = {}
    for i, p in enumerate(p for r in mm for p in r):
        idx.setdefault(p, i)
    ox = mm[0][0][0] - int(round(q.exterior.coords[0][0] * 1000.0))
    oy = mm[0][0][1] - int(round(q.exterior.coords[0][1] * 1000.0))
    out = []
    for t in shapely.get_parts(shapely.constrained_delaunay_triangles(q)):
        cs = list(t.exterior.coords)[:3]
        tri = []
        for x, y in cs:
            k = idx.get((int(round(x * 1000.0)) + ox, int(round(y * 1000.0)) + oy))
            if k is None:
                return None
            tri.append(k)
        flat = [p for r in mm for p in r]
        a, b, c = flat[tri[0]], flat[tri[1]], flat[tri[2]]
        o = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if o == 0:
            continue
        out.append((tri[0], tri[1], tri[2]) if o > 0 else (tri[0], tri[2], tri[1]))
    return sorted(out)


def _mesh(job, items, gr: _Ground):
    """The tile's ground: a primitive per surface."""
    x0, y0, x1, y1 = job["box"]
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    ox, oy = int(round(cx * 1000.0)), int(round(cy * 1000.0))
    tile = job["tile"]
    box = shapely.box(x0, y0, x1, y1)
    buf: dict[str, dict] = {}
    areas: dict[str, float] = {}
    failed, cdt = [], []
    cells = None
    if gr.g is not None:
        g = gr.g
        cs = g["cell"]
        ncx = len(g["rows_mm"][0]) - 1
        ncy = len(g["rows_mm"]) - 1
        cells = (g["x0"], g["y0"], cs, ncx, ncy)
    for it in items:
        if it["mode"] == "island":
            continue
        poly = _poly(it["rings"])
        parts = G.parts(G.inter(G.qpoly(poly), box))
        if not parts:
            continue
        slot = K.slot_of(it["surface"], tile)
        b = buf.setdefault(slot, {"pos": [], "nrm": [], "uv": [], "idx": []})
        zline = LineString(it["zline"]) if it["mode"] == "strip" else None
        for part in parts:
            pieces = [part]
            if cells is not None and zline is None:
                gx0, gy0, cs, ncx, ncy = cells
                bx0, by0, bx1, by1 = part.bounds
                i0 = max(0, int(math.floor((bx0 - gx0) / cs)))
                i1 = min(ncx, int(math.ceil((bx1 - gx0) / cs)))
                j0 = max(0, int(math.floor((by0 - gy0) / cs)))
                j1 = min(ncy, int(math.ceil((by1 - gy0) / cs)))
                ii, jj = np.meshgrid(np.arange(i0, i1), np.arange(j0, j1))
                boxes = shapely.box(gx0 + ii.ravel() * cs, gy0 + jj.ravel() * cs,
                                    gx0 + (ii.ravel() + 1) * cs, gy0 + (jj.ravel() + 1) * cs)
                got = shapely.intersection(part, boxes, grid_size=0.01)
                pieces = [q for gg in got.tolist() if not gg.is_empty for q in G.parts(gg)]
            for q in pieces:
                q = shapely.geometry.polygon.orient(q, 1.0)
                rings = [list(q.exterior.coords)[:-1]] + \
                    [list(h.coords)[:-1] for h in q.interiors]
                mm = [[(int(round(x * 1000.0)) - ox, int(round(y * 1000.0)) - oy)
                       for x, y in r] for r in rings]
                try:
                    tris = triangulate(mm[0], mm[1:])
                except TriangulationError:
                    # (a hole touching its outer ring at a vertex, valid but not simple for
                    # ear clipping: GEOS's constrained Delaunay triangles, on the same
                    # vertices)
                    tris = _cdt(q, mm)
                    if tris is None:
                        failed.append(it["id"])
                        continue
                    cdt.append(it["id"])
                if not tris:
                    continue
                flat = [p for r in rings for p in r]
                base = len(b["pos"])
                used = sorted({i for tt in tris for i in tt})
                where = {}
                fl = [p for r in mm for p in r]
                for i in used:
                    x, y = flat[i]
                    if zline is not None:
                        zz = float(shapely.get_coordinates(zline.interpolate(
                            zline.project(shapely.Point(x, y))), include_z=True)[0, 2])
                        nrm = (0.0, 0.0, 1.0)
                    else:
                        zz = float(gr.at(x, y)) + K.Z_LIFT_M
                        nrm = gr.normal(x, y)
                    where[i] = len(b["pos"])
                    b["pos"].append((fl[i][0], fl[i][1], int(round(zz * 1000.0))))
                    b["nrm"].append(nrm)
                    b["uv"].append((round(x, 3), round(y, 3)))
                for a, bb, cc in tris:
                    ia, ib, ic = where[a], where[bb], where[cc]
                    if gr.g is not None and zline is None:
                        pa, pb, pc = b["pos"][ia], b["pos"][ib], b["pos"][ic]
                        ux, uy, uz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
                        vx, vy, vz = pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]
                        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                        L = math.sqrt(float(nx) * nx + float(ny) * ny + float(nz) * nz) or 1.0
                        if abs(nz) / L < STEEP_NZ:
                            # (box mapping: the plan UV stretches on a wall's step; the
                            # triangle's own vertices with UV0 on the axis plane it faces most)
                            k = 0 if abs(nx) >= abs(ny) else 1
                            if abs(nz) >= max(abs(nx), abs(ny)):
                                k = 2
                            ids = []
                            for q3, n3 in ((pa, b["nrm"][ia]), (pb, b["nrm"][ib]),
                                           (pc, b["nrm"][ic])):
                                wx, wy, wz = ((q3[0] + ox) / 1000.0, (q3[1] + oy) / 1000.0,
                                              q3[2] / 1000.0)
                                uvq = ((wy, wz), (wx, wz), (wx, wy))[k]
                                ids.append(len(b["pos"]))
                                b["pos"].append(q3)
                                b["nrm"].append(n3)
                                b["uv"].append((round(uvq[0], 3), round(uvq[1], 3)))
                            ia, ib, ic = ids
                    b["idx"] += [ia, ib, ic]
                del base
                areas[it["id"]] = areas.get(it["id"], 0.0) + G.area(q)
    g = Gltf(generator="assetgen AG13 ground")
    prims = []
    tris_n = 0
    for slot in sorted(buf):
        b = buf[slot]
        if not b["idx"]:
            continue
        sf = K.SURFACES[K.surface_of_slot(slot)]
        mi = g.material(slot, (0.3, 0.35, 0.2, 1.0), 0.0, 0.95,
                        extras={"slot": slot, "master": "ground", "set": sf[0]})
        prims.append(Primitive(material=mi, positions=np.array(b["pos"], dtype=np.int64),
                               indices=np.array(b["idx"], dtype=np.int64),
                               normals=np.array(b["nrm"], dtype=np.float64),
                               uv0=np.array(b["uv"], dtype=np.float64)))
        tris_n += len(b["idx"]) // 3
    if not prims:
        return b"", {}, areas, failed + [f"cdt:{i}" for i in cdt], []
    name = f"ground.{tile}"
    mesh = g.mesh(name, prims)
    g.node(name, mesh, translation=(ox, oy, 0), root=True,
           extras={"citygen_type": "ground_cover", "tile": tile})
    slots = sorted(s for s in buf if buf[s]["idx"])
    failed = failed + [f"cdt:{i}" for i in cdt]          # (the fallback's: reported)
    return g.to_glb(), {"node": name, "triangles": tris_n, "slots": slots}, areas, failed, \
        slots


def make_tile(job: dict) -> dict:
    t0 = time.perf_counter()
    n, c = K.MASK_PX, K.CELL_M
    x0, y0, x1, y1 = job["box"]
    xs = x0 + (np.arange(n) + 0.5) * c
    ys = y0 + (np.arange(n) + 0.5) * c
    X, Y = np.meshgrid(xs, ys)
    gr = _Ground(job.get("ground"))
    with G.canonical():
        items = _items(job)
        polys = [_poly(it["rings"]) for it in items]
        mk = _mask(job, items, polys, gr, X, Y)
        inst, sc = _scatter(job, items, polys, mk, gr, X, Y)
        glb, node, areas, failed, slots = _mesh(job, items, gr)
    from PIL import Image
    bio = io.BytesIO()
    Image.fromarray(mk["mask"], "RGBA").save(bio, "PNG", compress_level=6)
    from ..materials import pbr as PB
    return {"tile": job["tile"], "glb": glb, "node": node, "mask": bio.getvalue(),
            "mask_pixels_sha256": PB.pixels_sha256(mk["mask"]), "instances": inst,
            "scatter": sc, "areas": {k: round(v, 3) for k, v in sorted(areas.items())},
            "failed": sorted(set(failed)), "surfaces": [K.surface_of_slot(s) for s in slots],
            "seconds": round(time.perf_counter() - t0, 3)}
