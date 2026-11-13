"""What a walker sees (the visible lights, after AT4): the plan's sight raster, the occluders
the runtime marches a line of sight through when it picks the lights to keep live round a
player on foot (docs/atmosgen_scope.md 4.2, docs/unreal_export.md, "Visible lights").

The raster is the lux check's occluders (`lux.Occluders`: the building masses taken
`lux.ERODE_M` inside their footprints, and the deck slabs, on a 1 m grid) brought to
`CELL_M` cells: a cell blocks the height span every one of its four 1 m cells blocks (the
lowest top over the highest bottom), so a line of sight grazing a facade, or reaching a sign
stood off it, stays clear; and the ground under it (M13's, the lowest of its corners; 0 on a
flat city) blocks everything below it. `sight.png` beside the plan, row 0 the north edge:

- red: the top of what stands in the cell, absolute, in `TOP_STEP_M` steps rounded down
  (0: nothing stands there);
- green: its bottom over the cell's ground in 1 m steps rounded up (0: it stands on the
  ground; a deck slab's underside or a mass over a passage otherwise);
- blue: the cell's ground, absolute, in 1 m steps rounded down.

Every rounding leans to seeing: a light the raster calls hidden is hidden. `visible` is the
runtime's test (`CityGenAtmosActor.cpp`, `FCityGenSight::Visible`) in Python: a walk through
the cells the segment crosses in plan, the segment's height span in each against the cell's
spans, the first `SKIP_EYE_M` from the eye and the last `SKIP_LIGHT_M` to the light left
out (the light's own wall and fixture), and the cell the eye stands in (a camera at a facade
or in a doorway stands in its building's cell)."""

from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path

import numpy as np

FILE = "sight.png"
CELL_M = 2.0              # the raster's cells (m): two of the lux check's
TOP_STEP_M = 2.0          # red: the top in these steps (0 to 510 m)
BOTTOM_STEP_M = 1.0       # green: the bottom over the ground
GROUND_STEP_M = 1.0       # blue: the ground
ON_GROUND_M = 1.0         # an occluder whose bottom is within this of the ground stands on it
SKIP_EYE_M = 0.5          # the march leaves out the first this from the eye ...
SKIP_LIGHT_M = 1.0        # ... and the last this to the light


def raster(occ, ground_many=None, cell: float = CELL_M) -> dict:
    """The sight raster from the lux check's occluders (`lux.Occluders`) and the ground
    (`City.ground_many`, None on a flat city): {rgb (ny, nx, 3) uint8 with row 0 the north,
    bounds [x0, y0, x1, y1], cell_m}."""
    k = max(1, int(round(cell / occ.cell)))
    ny, nx = occ.top.shape
    ny2, nx2 = (ny + k - 1) // k, (nx + k - 1) // k
    top = np.full((ny2 * k, nx2 * k), -np.inf, dtype=np.float32)
    bot = np.full((ny2 * k, nx2 * k), np.inf, dtype=np.float32)
    top[:ny, :nx] = occ.top
    bot[:ny, :nx] = occ.bot
    # (every 1 m cell of the 2 m cell blocks the span: the lowest top, the highest bottom)
    t = top.reshape(ny2, k, nx2, k).min(axis=(1, 3))
    b = bot.reshape(ny2, k, nx2, k).max(axis=(1, 3))
    c = occ.cell * k
    x0, y0 = occ.x0, occ.y0
    if ground_many is not None:
        xs = x0 + c * np.arange(nx2 + 1)
        ys = y0 + c * np.arange(ny2 + 1)
        gx, gy = np.meshgrid(xs, ys)
        gc = np.asarray(ground_many(gx.ravel(), gy.ravel()), dtype=np.float64).reshape(gx.shape)
        g = np.minimum(np.minimum(gc[:-1, :-1], gc[:-1, 1:]), np.minimum(gc[1:, :-1], gc[1:, 1:]))
    else:
        g = np.zeros((ny2, nx2))
    gq = np.clip(np.floor(g / GROUND_STEP_M), 0, 255)
    gz = gq * GROUND_STEP_M
    occupied = np.isfinite(t) & np.isfinite(b) & (t > b)
    tq = np.where(occupied, np.clip(np.floor(t / TOP_STEP_M), 0, 255), 0)
    # (a top no higher than the ground blocks nothing the ground does not)
    tq = np.where(tq * TOP_STEP_M > gz, tq, 0)
    over = np.where(occupied, b - gz, 0.0)
    bq = np.where((tq > 0) & (over > ON_GROUND_M),
                  np.clip(np.ceil(over / BOTTOM_STEP_M), 1, 255), 0)
    # (a span the roundings close, a top under its bottom, blocks nothing)
    tq = np.where((bq > 0) & (tq * TOP_STEP_M <= gz + bq * BOTTOM_STEP_M), 0, tq)
    bq = np.where(tq > 0, bq, 0)
    rgb = np.stack([tq, bq, gq], axis=-1).astype(np.uint8)[::-1]
    return {"rgb": np.ascontiguousarray(rgb), "cell_m": c,
            "bounds": [x0, y0, x0 + c * nx2, y0 + c * ny2]}


def png(r: dict) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(r["rgb"], "RGB").save(buf, format="PNG", compress_level=9)
    return buf.getvalue()


def write(r: dict, od: Path) -> dict:
    """Write `sight.png` (only when its bytes change) and return the plan's record."""
    data = png(r)
    f = Path(od) / FILE
    if not f.is_file() or f.read_bytes() != data:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    h, w = r["rgb"].shape[:2]
    occ = r["rgb"][..., 0] > 0
    return {"file": FILE, "bounds": [round(float(v), 3) for v in r["bounds"]],
            "cell_m": float(r["cell_m"]), "px": [int(w), int(h)],
            "top_step_m": TOP_STEP_M, "bottom_step_m": BOTTOM_STEP_M,
            "ground_step_m": GROUND_STEP_M, "skip_eye_m": SKIP_EYE_M,
            "skip_light_m": SKIP_LIGHT_M, "occupied": round(float(occ.mean()), 4),
            "sha256": hashlib.sha256(data).hexdigest()}


def load(path: Path, rec: dict) -> dict:
    from PIL import Image
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
    return {"rgb": rgb, "cell_m": float(rec["cell_m"]), "bounds": list(rec["bounds"])}


def runs(rgb: np.ndarray) -> list[int]:
    """The raster, row 0 the north, as runs over its rows in order: [count, value] pairs, the
    value red | green << 8 | blue << 16 (the exporter's packing, `unreal_atmos.sight`)."""
    v = (rgb[..., 0].astype(np.int64) | (rgb[..., 1].astype(np.int64) << 8)
         | (rgb[..., 2].astype(np.int64) << 16)).ravel()
    if v.size == 0:
        return []
    cut = np.flatnonzero(np.diff(v)) + 1
    starts = np.concatenate([[0], cut])
    ends = np.concatenate([cut, [v.size]])
    out = np.empty(2 * starts.size, dtype=np.int64)
    out[0::2] = ends - starts
    out[1::2] = v[starts]
    return out.tolist()


def visible(r: dict, eye, light) -> bool:
    """Whether the segment from `eye` to `light` (plan frame: m, x east, y north, z
    absolute) clears the raster, as the runtime tests it."""
    rgb = r["rgb"]
    ny, nx = rgb.shape[:2]
    x0, y0, x1, y1 = r["bounds"]
    c = r["cell_m"]
    ex, ey, ez = (float(v) for v in eye)
    lx, ly, lz = (float(v) for v in light)
    dx, dy, dz = lx - ex, ly - ey, lz - ez
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= SKIP_EYE_M + SKIP_LIGHT_M:
        return True
    ta, tb = SKIP_EYE_M / length, 1.0 - SKIP_LIGHT_M / length
    # cell coordinates (u east from x0, w south from y1: row 0 the north)
    ua, wa = (ex + ta * dx - x0) / c, (y1 - (ey + ta * dy)) / c
    du, dw = dx / c, -dy / c
    i, j = int(math.floor(ua)), int(math.floor(wa))
    si = 1 if du > 0 else -1
    sj = 1 if dw > 0 else -1
    inf = float("inf")
    nu = ((i + (1 if du > 0 else 0)) - ua) / du if du != 0 else inf
    nw = ((j + (1 if dw > 0 else 0)) - wa) / dw if dw != 0 else inf
    stu = abs(1.0 / du) if du != 0 else inf
    stw = abs(1.0 / dw) if dw != 0 else inf
    t = ta
    nu += ta
    nw += ta
    first = True
    while t < tb:
        t_out = min(nu, nw, tb)
        if not first and 0 <= i < nx and 0 <= j < ny:
            za, zb = ez + t * dz, ez + t_out * dz
            lo, hi = min(za, zb), max(za, zb)
            top, bq, gq = (int(v) for v in rgb[j, i])
            g = gq * GROUND_STEP_M
            if lo < g:
                return False
            if top:
                b = g + bq * BOTTOM_STEP_M if bq else -inf
                if lo < top * TOP_STEP_M and hi > b:
                    return False
        first = False
        if t_out >= tb:
            break
        if nu < nw:
            i += si
            nu += stu
        else:
            j += sj
            nw += stw
        t = t_out
    return True
