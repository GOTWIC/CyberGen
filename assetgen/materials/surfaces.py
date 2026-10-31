"""Surface generators for the tileable texture sets (scope 5.2: brick, tiles, panels,
corrugation, rust, concrete, paving, asphalt; procedural in numpy, exact per section 10).

Each generator takes the image size `n` (pixels), the tile's size `tile_m` (meters it covers)
and a parameter dict, and returns a `Surface`: base color (sRGB, 0 to 1), height (0 to 1),
roughness, metallic, occlusion and the tint mask (1 where the material takes the actor's tint,
0 where it keeps its own color: mortar, joints, rust, sealant). Physical sizes are in meters
and rounded so a whole number of bricks, boards or ribs fits the tile, which then repeats
without a seam.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import noise as N

F = np.float32


@dataclass
class Surface:
    color: np.ndarray          # (n, n, 3) sRGB 0..1
    height: np.ndarray         # (n, n) 0..1
    rough: np.ndarray          # (n, n)
    metal: np.ndarray          # (n, n)
    mask: np.ndarray           # (n, n) tint mask
    ao: np.ndarray | None = None
    bump: float = 1.0          # height range in millimeters at full scale (normal strength)


def rgb(hexc: str) -> np.ndarray:
    return np.array([int(hexc[1 + 2 * k:3 + 2 * k], 16) / 255.0 for k in range(3)], dtype=F)


def full(n: int, v: float) -> np.ndarray:
    return np.full((n, n), F(v), dtype=F)


def paint(n: int, c: np.ndarray, shade: np.ndarray) -> np.ndarray:
    """Color c (sRGB) times a per-pixel shade (around 1)."""
    return np.clip(c[None, None, :] * shade[:, :, None], 0.0, 1.0).astype(F)


def mix(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
    return (a + (b - a) * t[:, :, None]).astype(F)


def count(tile_m: float, size_m: float) -> int:
    """How many items of about size_m fit the tile (at least 1)."""
    return max(1, int(round(tile_m / size_m)))


def coords(n: int) -> tuple[np.ndarray, np.ndarray]:
    return N.grid(n)


def stains(n: int, seed: int, amount: float, stretch: int = 16) -> np.ndarray:
    """Vertical streaks (rain run-off): value noise with many columns and few rows, soft
    and long, 0 (clean) to 1 (dark streak)."""
    px, py = N.grid(n)
    qy = (py / F(stretch)).astype(F)
    cols = N.value(n, 32, seed, px, qy)
    fine = N.value(n, 128, seed + 3, px, qy)
    v = N.smooth(0.6, 0.98, (cols * F(0.75) + fine * F(0.25)).astype(F))
    patchy = N.smooth(0.3, 0.7, N.fbm(n, 3, seed + 5, 3))
    return (v * patchy * F(amount)).astype(F)


def grain(n: int, seed: int, r: int = 1) -> np.ndarray:
    """Fine grain around 0 (blurred white noise, -0.5..0.5)."""
    return (N.blur(N.white(n, seed), r) - F(0.5)).astype(F)


def mottle(n: int, seed: int, period: int = 4) -> np.ndarray:
    return (N.fbm(n, period, seed, 6) - F(0.5)).astype(F)


def cracks(n: int, seed: int, density: float) -> np.ndarray:
    """Thin crack lines (1 on a crack), more with density 0..1."""
    r = N.ridged(n, 6, seed, 4)
    w = N.fbm(n, 4, seed + 5, 3)
    lim = F(0.93 - 0.06 * density)
    return (N.smooth(float(lim), float(lim) + 0.04, r) * N.smooth(0.45, 0.7, w)).astype(F)


def _rows(n: int, tile_m: float, h_m: float) -> tuple[int, np.ndarray, np.ndarray]:
    k = count(tile_m, h_m)
    _, py = N.grid(n)
    fy = (py * F(k)).astype(F)
    row = np.floor(fy).astype(np.int64)
    return k, row, (fy - np.floor(fy)).astype(F)


# --- building walls ------------------------------------------------------------------------

def concrete(n: int, tile_m: float, p: dict) -> Surface:
    """Cast concrete: mottling, sand grain, pores, run-off stains; optional form panel joints
    and tie holes, board marks (`boards`), smooth or rough by `rough`."""
    s = p["seed"]
    c = rgb(p.get("color", "#8c8a86"))
    wear = float(p.get("wear", 0.4))
    px, py = N.grid(n)
    m = mottle(n, s, 3)
    g = grain(n, s + 1)
    pores_d, _ = N.cells(n, count(tile_m, 0.02) * 1, s + 2, 1.0)
    pores = N.smooth(0.18, 0.08, pores_d) * N.smooth(0.6, 0.8, N.white(n, s + 9))
    st = stains(n, s + 3, 0.35 + 0.5 * wear)
    shade = F(1.0) + F(0.22) * m + F(0.08) * g - F(0.25) * pores - F(0.3) * st
    height = F(0.6) + F(0.15) * m + F(0.1) * g - F(0.35) * pores
    mask = full(n, 1.0)
    rough = full(n, float(p.get("rough", 0.85))) + F(0.06) * g
    boards = p.get("boards")
    if boards:
        k, row, fy = _rows(n, tile_m, float(boards))
        jit = N.unit(N.hash2(row, row * 0 + 3, s + 4))
        wood = N.fbm(n, 2, s + 6, 4, 0.55, px * F(0.25),
                     (py * F(k * 24)).astype(F) - np.floor(py * F(k * 24)).astype(F))
        edge = N.smooth(0.0, 0.03, fy) * N.smooth(1.0, 0.97, fy)
        shade = shade + F(0.1) * (jit - F(0.5)) + F(0.12) * (wood - F(0.5)) \
            - F(0.12) * (F(1.0) - edge)
        height = height + F(0.12) * (jit - F(0.5)) + F(0.1) * wood - F(0.25) * (F(1.0) - edge)
    joints = p.get("joints")
    if joints:
        jw, jh = joints
        kx, ky = count(tile_m, jw), count(tile_m, jh)
        fx = px * F(kx) - np.floor(px * F(kx))
        fy = py * F(ky) - np.floor(py * F(ky))
        w = F(0.012 * n / tile_m)
        lx = np.minimum(fx, F(1.0) - fx) * F(n / kx)
        ly = np.minimum(fy, F(1.0) - fy) * F(n / ky)
        line = np.maximum(N.smooth(float(w), 0.0, lx), N.smooth(float(w), 0.0, ly))
        shade = shade - F(0.35) * line
        height = height - F(0.5) * line
        mask = mask * (F(1.0) - line)
        rough = rough + F(0.05) * line
        if p.get("ties"):
            tx = (px * F(kx * 2) - np.floor(px * F(kx * 2)) - F(0.5)) * F(n / (kx * 2))
            ty = (py * F(ky * 2) - np.floor(py * F(ky * 2)) - F(0.5)) * F(n / (ky * 2))
            r = np.sqrt(tx * tx + ty * ty)
            hole = N.smooth(F(0.014 * n / tile_m), F(0.008 * n / tile_m), r)
            shade = shade - F(0.4) * hole
            height = height - F(0.4) * hole
            mask = mask * (F(1.0) - hole)
    cr = cracks(n, s + 7, wear)
    shade = shade - F(0.25) * cr
    height = height - F(0.25) * cr
    return Surface(paint(n, c, shade), np.clip(height, 0, 1).astype(F),
                   np.clip(rough, 0, 1).astype(F), full(n, 0.0), mask.astype(F), bump=2.0)


def plaster(n: int, tile_m: float, p: dict) -> Surface:
    """Plaster or stucco: a troweled or sand-float face, hairline cracks, patches painted over,
    stains."""
    s = p["seed"]
    c = rgb(p.get("color", "#b9ad9c"))
    wear = float(p.get("wear", 0.4))
    coarse = float(p.get("coarse", 0.5))
    m = mottle(n, s, 2)
    trowel = N.ridged(n, 8, s + 1, 3)
    sand = grain(n, s + 2, 0)
    patch = N.smooth(0.55, 0.75, N.fbm(n, 3, s + 4, 4)) * F(0.5)
    st = stains(n, s + 3, 0.3 + 0.6 * wear)
    cr = cracks(n, s + 5, wear)
    shade = F(1.0) + F(0.12) * m + F(0.07 * coarse) * sand + F(0.04) * (trowel - F(0.5)) \
        + F(0.07) * patch - F(0.28) * st - F(0.25) * cr
    height = F(0.5) + F(0.25 * coarse) * sand + F(0.2) * (trowel - F(0.5)) - F(0.3) * cr
    rough = full(n, 0.88) + F(0.05) * sand - F(0.05) * patch
    return Surface(paint(n, c, shade), np.clip(height, 0, 1).astype(F),
                   np.clip(rough, 0, 1).astype(F), full(n, 0.0), full(n, 1.0),
                   bump=0.8 + 1.2 * coarse)


def brick(n: int, tile_m: float, p: dict) -> Surface:
    """Brick in running (or English, `bond`) bond: per-brick tone and burnt headers, chipped
    arrises, recessed mortar (keeps its own grey: mask 0), soot and efflorescence."""
    s = p["seed"]
    c = rgb(p.get("color", "#7a4a35"))
    mortar_c = rgb(p.get("mortar", "#9b968c"))
    wear = float(p.get("wear", 0.4))
    course = float(p.get("course_m", 0.075))
    length = float(p.get("length_m", 0.225))
    joint = float(p.get("joint_m", 0.011))
    ky = count(tile_m, course)
    kx = count(tile_m, length)
    px, py = N.grid(n)
    fy = py * F(ky)
    row = np.floor(fy).astype(np.int64)
    english = p.get("bond") == "english"
    hdr = (row % 2 == 1) if english else np.zeros_like(row, dtype=bool)
    per = np.where(hdr, kx * 2, kx)
    off = np.where(hdr, F(0.25), np.where(row % 2 == 1, F(0.5), F(0.0)))
    fx = px * per.astype(F) + off
    col = np.floor(fx).astype(np.int64) % per
    ux = (fx - np.floor(fx)).astype(F)
    uy = (fy - np.floor(fy)).astype(F)
    # mortar: distance to the brick's edge in meters, warped by chips
    ex = np.minimum(ux, F(1.0) - ux) * (F(tile_m) / per.astype(F))
    ey = np.minimum(uy, F(1.0) - uy) * F(tile_m / ky)
    chip = N.fbm(n, 32, s + 1, 3)
    e = np.minimum(ex, ey) - F(joint / 2) - F(0.006) * (chip - F(0.5))
    brick_m = N.smooth(0.0, 0.003, e)
    bid = N.unit(N.hash2(col, row, s + 2))
    bid2 = N.unit(N.hash2(col, row, s + 3))
    tone = F(1.0) + F(0.28) * (bid - F(0.5))
    burnt = np.where(bid2 < F(0.12 + 0.15 * float(p.get("burnt", 0.3))), F(0.62), F(1.0))
    warm = (bid2 - F(0.5)) * F(0.12)
    face = N.fbm(n, 64, s + 4, 3)
    shade = (tone * burnt + F(0.18) * (face - F(0.5))).astype(F)
    bc = paint(n, c, shade)
    bc[:, :, 0] = np.clip(bc[:, :, 0] + warm, 0, 1)
    bc[:, :, 2] = np.clip(bc[:, :, 2] - warm, 0, 1)
    mshade = F(1.0) + F(0.2) * grain(n, s + 5, 0)
    mc = paint(n, mortar_c, mshade.astype(F))
    color = mix(mc, bc, brick_m)
    soot = stains(n, s + 6, 0.25 + 0.6 * wear)
    eff = N.smooth(0.7, 0.9, N.fbm(n, 6, s + 7, 4)) * F(0.3 * wear)
    color = color * (F(1.0) - F(0.55) * soot)[:, :, None]
    color = color + (F(0.85) - color) * eff[:, :, None]
    height = F(0.3) + F(0.55) * brick_m + F(0.08) * (face - F(0.5)) \
        + F(0.05) * grain(n, s + 8, 0)
    rough = F(0.92) - F(0.05) * brick_m
    return Surface(np.clip(color, 0, 1).astype(F), np.clip(height, 0, 1).astype(F),
                   np.clip(rough, 0, 1).astype(F), full(n, 0.0), brick_m.astype(F), bump=6.0)


def panel(n: int, tile_m: float, p: dict) -> Surface:
    """Precast or composite panels: a grid of panels with sealant joints (mask 0), a tone per
    panel, a fine face (exposed aggregate, `aggregate`), stains."""
    s = p["seed"]
    c = rgb(p.get("color", "#a9a59d"))
    wear = float(p.get("wear", 0.3))
    pw, ph = p.get("size_m", (1.5, 1.0))
    kx, ky = count(tile_m, pw), count(tile_m, ph)
    px, py = N.grid(n)
    fx = px * F(kx)
    fy = py * F(ky)
    cx = np.floor(fx).astype(np.int64)
    cy = np.floor(fy).astype(np.int64)
    ux = fx - np.floor(fx)
    uy = fy - np.floor(fy)
    jm = float(p.get("joint_m", 0.018))
    ex = np.minimum(ux, F(1.0) - ux) * F(tile_m / kx)
    ey = np.minimum(uy, F(1.0) - uy) * F(tile_m / ky)
    e = np.minimum(ex, ey)
    face = N.smooth(jm / 2, jm / 2 + 0.004, e)
    tone = N.unit(N.hash2(cx, cy, s + 1)) - F(0.5)
    agg = float(p.get("aggregate", 0.3))
    g = grain(n, s + 2, 0)
    m = mottle(n, s + 3, 4)
    st = stains(n, s + 4, 0.25 + 0.55 * wear)
    shade = F(1.0) + F(0.1) * tone + F(0.12 * agg) * g + F(0.1) * m - F(0.3) * st
    seal = rgb(p.get("seal", "#3a3a3a"))
    color = mix(paint(n, seal, full(n, 1.0)), paint(n, c, shade.astype(F)), face)
    height = F(0.3) + F(0.6) * face + F(0.1 * agg) * g
    metal = full(n, float(p.get("metallic", 0.0))) * face
    rough = F(float(p.get("rough", 0.8))) + F(0.05) * g * F(agg) + F(0.1) * (F(1.0) - face)
    return Surface(color, np.clip(height, 0, 1).astype(F), np.clip(rough, 0, 1).astype(F),
                   metal.astype(F), face.astype(F), bump=3.0)


def _wave(t: np.ndarray) -> np.ndarray:
    """A smooth rib profile from a ramp 0..1: 0 at the ends, 1 in the middle."""
    return N._fade((F(1.0) - np.abs(F(2.0) * t - F(1.0))).astype(F))


def ribbed(n: int, tile_m: float, p: dict) -> Surface:
    """Metal cladding with ribs along v (vertical on a wall): `profile` corrugated (round
    waves), trapezoid (box ribs) or seam (flat pans with standing seams); sheet laps,
    fasteners, rust streaks with wear (mask 0 on rust)."""
    s = p["seed"]
    c = rgb(p.get("color", "#7f868c"))
    wear = float(p.get("wear", 0.3))
    prof = p.get("profile", "corrugated")
    pitch = float(p.get("pitch_m", {"corrugated": 0.076, "trapezoid": 0.25,
                                   "seam": 0.5}[prof]))
    k = count(tile_m, pitch)
    px, py = N.grid(n)
    t = (px * F(k) - np.floor(px * F(k))).astype(F)
    if prof == "corrugated":
        h = _wave(t)
    elif prof == "trapezoid":
        h = N.smooth(0.15, 0.25, t) * N.smooth(0.75, 0.65, t)
    else:
        d = np.minimum(t, F(1.0) - t) * F(pitch)
        h = N.smooth(0.012, 0.004, d) + F(0.05) * N.value(n, 3, s + 9)
    sheet_h = float(p.get("sheet_m", 3.0))
    ky = count(tile_m, sheet_h)
    fy = py * F(ky) - np.floor(py * F(ky))
    lap = N.smooth(0.006 * ky / tile_m, 0.0, fy) + N.smooth(1.0 - 0.006 * ky / tile_m, 1.0, fy)
    lap = np.clip(lap, 0, 1)
    # fasteners on every other rib at the laps and mid-sheet
    rib = np.floor(px * F(k)).astype(np.int64)
    fz = np.abs(fy - F(0.5)) * F(tile_m / ky)
    fzl = np.minimum(fy, F(1.0) - fy) * F(tile_m / ky)
    near = np.minimum(fz, fzl)
    fxd = np.abs(t - F(0.5)) * F(pitch)
    r = np.sqrt(fxd * fxd + near * near)
    screw = N.smooth(0.008, 0.004, r) * (rib % 2 == 0)
    g = grain(n, s + 1, 0)
    m = mottle(n, s + 2, 4)
    rust_n = N.fbm(n, 8, s + 3, 5)
    st = stains(n, s + 4, 1.0, 10)
    rust = np.clip(N.smooth(0.75 - 0.3 * wear, 0.85 - 0.3 * wear, rust_n)
                   + F(0.8 * wear) * st * N.smooth(0.3, 0.6, rust_n), 0, 1).astype(F)
    rust_c = paint(n, rgb("#7a3b1c"), (F(0.8) + F(0.5) * N.fbm(n, 32, s + 5, 3)).astype(F))
    shade = F(0.85) + F(0.25) * h + F(0.06) * g + F(0.1) * m - F(0.2) * lap
    color = mix(paint(n, c, shade.astype(F)), rust_c, rust)
    height = F(0.15) + F(0.75) * h - F(0.1) * lap + F(0.15) * screw
    metal = (F(float(p.get("metallic", 0.6))) * (F(1.0) - rust)).astype(F)
    rough = F(float(p.get("rough", 0.5))) + F(0.35) * rust + F(0.05) * g
    return Surface(color, np.clip(height, 0, 1).astype(F), np.clip(rough, 0, 1).astype(F),
                   metal, (F(1.0) - rust).astype(F),
                   bump={"corrugated": 18.0, "trapezoid": 30.0, "seam": 20.0}[prof])


def sheet(n: int, tile_m: float, p: dict) -> Surface:
    """Flat sheet metal (galvanized spangle, dents, rivet lines), painted or bare."""
    s = p["seed"]
    c = rgb(p.get("color", "#8a8172"))
    wear = float(p.get("wear", 0.5))
    d, sid = N.cells(n, count(tile_m, 0.05), s + 1, 1.0)
    spangle = (sid - F(0.5)) * F(float(p.get("spangle", 0.12)))
    dent = N.fbm(n, 3, s + 2, 4)
    px, py = N.grid(n)
    k = count(tile_m, float(p.get("sheet_m", 1.0)))
    fx = px * F(k) - np.floor(px * F(k))
    edge = np.minimum(fx, F(1.0) - fx) * F(tile_m / k)
    seam = N.smooth(0.008, 0.002, edge)
    rx = np.abs(edge - F(0.025))
    ry = (py * F(count(tile_m, 0.15)) - np.floor(py * F(count(tile_m, 0.15))) - F(0.5)) \
        * F(0.15)
    rivet = N.smooth(0.006, 0.003, np.sqrt(rx * rx + ry * ry))
    rust_n = N.fbm(n, 6, s + 3, 5)
    rust = N.smooth(0.8 - 0.35 * wear, 0.9 - 0.35 * wear, rust_n)
    st = stains(n, s + 4, 0.4 + 0.5 * wear)
    shade = F(1.0) + spangle + F(0.15) * (dent - F(0.5)) - F(0.3) * st - F(0.2) * seam
    rust_c = paint(n, rgb("#6f3a1e"), (F(0.85) + F(0.4) * N.white(n, s + 5)).astype(F))
    color = mix(paint(n, c, shade.astype(F)), rust_c, rust.astype(F))
    height = F(0.5) + F(0.3) * (dent - F(0.5)) + F(0.3) * rivet - F(0.3) * seam
    metal = (F(float(p.get("metallic", 0.7))) * (F(1.0) - rust)).astype(F)
    rough = F(float(p.get("rough", 0.55))) + F(0.3) * rust + F(0.2) * st
    return Surface(color, np.clip(height, 0, 1).astype(F), np.clip(rough, 0, 1).astype(F),
                   metal, (F(1.0) - rust).astype(F), bump=4.0)


def fabric(n: int, tile_m: float, p: dict) -> Surface:
    """Tarp or canvas: a weave, folds and sags, grime."""
    s = p["seed"]
    c = rgb(p.get("color", "#2f5f8a"))
    wear = float(p.get("wear", 0.5))
    px, py = N.grid(n)
    k = count(tile_m, 0.004)
    k = min(k, n // 2)
    wx = px * F(k) - np.floor(px * F(k))
    wy = py * F(k) - np.floor(py * F(k))
    weave = (_wave(wx) * F(0.5) + _wave(wy) * F(0.5)).astype(F)
    qx, qy = N.warp(n, 2, s + 1, 0.3)
    fold = N.fbm(n, 2, s + 2, 4, 0.5, qx, qy)
    st = stains(n, s + 3, 0.3 + 0.5 * wear)
    shade = F(0.9) + F(0.35) * (fold - F(0.5)) + F(0.08) * weave - F(0.3) * st
    height = F(0.3) + F(0.6) * fold + F(0.1) * weave
    return Surface(paint(n, c, shade.astype(F)), np.clip(height, 0, 1).astype(F),
                   full(n, 0.8), full(n, 0.0), full(n, 1.0), bump=25.0)


def wood(n: int, tile_m: float, p: dict) -> Surface:
    """Boards (`board_m` wide, along u or v by `along`) with grain and gaps, or plywood
    sheets (`plywood`): veneer grain, sheet seams, weathering to grey."""
    s = p["seed"]
    c = rgb(p.get("color", "#6b5038"))
    wear = float(p.get("wear", 0.4))
    px, py = N.grid(n)
    ply = bool(p.get("plywood"))
    bw = float(p.get("board_m", 1.22 if ply else 0.14))
    k = count(tile_m, bw)
    across = px if p.get("along", "v") == "v" else py
    along = py if p.get("along", "v") == "v" else px
    f = across * F(k)
    board = np.floor(f).astype(np.int64)
    t = (f - np.floor(f)).astype(F)
    bid = N.unit(N.hash2(board, board * 0, s + 1))
    # grain: noise stretched along the board, shifted per board
    ga = (along + bid).astype(F)
    ga = (ga - np.floor(ga)).astype(F)
    gb = (across * F(k * 3)).astype(F)
    gb = (gb - np.floor(gb)).astype(F)
    gr = N.fbm(n, 2, s + 2, 5, 0.6, gb if p.get("along", "v") == "v" else ga,
               ga if p.get("along", "v") == "v" else gb)
    rings = N.ridged(n, 4, s + 3, 3)
    gap = N.smooth(0.012 if not ply else 0.004, 0.0,
                   np.minimum(t, F(1.0) - t) * F(tile_m / k))
    tone = F(1.0) + F(0.25) * (bid - F(0.5))
    shade = tone + F(0.25) * (gr - F(0.5)) + F(0.08) * (rings - F(0.5)) - F(0.6) * gap
    grey = N.smooth(0.3, 0.9, N.fbm(n, 4, s + 4, 4)) * F(wear)
    col = paint(n, c, shade.astype(F))
    col = col + (F(0.45) - col) * grey[:, :, None]
    height = F(0.5) + F(0.25) * (gr - F(0.5)) - F(0.5) * gap
    return Surface(np.clip(col, 0, 1).astype(F), np.clip(height, 0, 1).astype(F),
                   (F(0.8) + F(0.1) * grey).astype(F), full(n, 0.0), (F(1.0) - gap).astype(F),
                   bump=3.0)


def smooth_paint(n: int, tile_m: float, p: dict) -> Surface:
    """Painted or coated surfaces (trim, spandrel enamel, equipment, steel): orange peel,
    scratches and chips to `under` with wear, metal under paint where `metallic`."""
    s = p["seed"]
    c = rgb(p.get("color", "#bdb6aa"))
    wear = float(p.get("wear", 0.3))
    peel = grain(n, s + 1, 2)
    m = mottle(n, s + 2, 4)
    chips = N.smooth(0.82 - 0.2 * wear, 0.86 - 0.2 * wear, N.fbm(n, 16, s + 3, 5))
    scratch = cracks(n, s + 4, 0.3 * wear)
    st = stains(n, s + 5, 0.15 + 0.4 * wear)
    under = rgb(p.get("under", "#5a5650"))
    shade = F(1.0) + F(0.03) * peel + F(0.06) * m - F(0.25) * st
    color = mix(paint(n, c, shade.astype(F)), paint(n, under, full(n, 1.0)),
                np.maximum(chips, scratch).astype(F))
    height = F(0.6) + F(0.05) * peel - F(0.3) * chips - F(0.2) * scratch
    met = float(p.get("metallic", 0.0))
    metal = full(n, met) + F(0.6) * chips * F(1.0 if p.get("metal_under") else 0.0)
    rough = F(float(p.get("rough", 0.45))) + F(0.03) * peel + F(0.25) * st + F(0.2) * chips
    return Surface(color, np.clip(height, 0, 1).astype(F), np.clip(rough, 0, 1).astype(F),
                   np.clip(metal, 0, 1).astype(F),
                   (F(1.0) - np.maximum(chips, scratch)).astype(F), bump=0.4)


def brushed(n: int, tile_m: float, p: dict) -> Surface:
    """Brushed or mill-finish metal (aluminum, steel, rail): streaks along u, smudges."""
    s = p["seed"]
    c = rgb(p.get("color", "#9aa1a8"))
    px, py = N.grid(n)
    k = min(n // 2, count(tile_m, 0.002))
    st = N.value(n, 2, s + 1, (px * F(0.0) + px).astype(F), (py * F(1.0)).astype(F))
    brush = N.fbm(n, 4, s + 2, 4, 0.6, (px / F(16.0)).astype(F), py)
    lines = N.value(n, k, s + 3, (px / F(64.0)).astype(F), py)
    smudge = N.fbm(n, 3, s + 4, 4)
    shade = F(1.0) + F(0.06) * (brush - F(0.5)) + F(0.05) * (lines - F(0.5)) \
        + F(0.08) * (st - F(0.5))
    rough = F(float(p.get("rough", 0.35))) + F(0.1) * (smudge - F(0.5)) \
        + F(0.08) * (lines - F(0.5))
    height = F(0.5) + F(0.1) * (lines - F(0.5))
    return Surface(paint(n, c, shade.astype(F)), height.astype(F),
                   np.clip(rough, 0, 1).astype(F), full(n, float(p.get("metallic", 1.0))),
                   full(n, 1.0), bump=0.2)


def perforated(n: int, tile_m: float, p: dict) -> Surface:
    """Perforated metal skin: a staggered hole grid (dark, mask 0) on a coated sheet."""
    s = p["seed"]
    base = smooth_paint(n, tile_m, {**p, "wear": p.get("wear", 0.15)})
    pitch = float(p.get("pitch_m", 0.04))
    k = count(tile_m, pitch)
    px, py = N.grid(n)
    fy = py * F(k)
    row = np.floor(fy).astype(np.int64)
    fx = px * F(k) + np.where(row % 2 == 1, F(0.5), F(0.0))
    tx = (fx - np.floor(fx) - F(0.5)) * F(tile_m / k)
    ty = (fy - np.floor(fy) - F(0.5)) * F(tile_m / k)
    r = np.sqrt(tx * tx + ty * ty)
    rad = F(float(p.get("hole", 0.32)) * pitch)
    hole = N.smooth(float(rad), float(rad) * 0.85, r)
    color = mix(base.color, paint(n, rgb("#101214"), full(n, 1.0)), hole.astype(F))
    return Surface(color, (base.height * (F(1.0) - hole)).astype(F),
                   np.minimum(base.rough + F(0.4) * hole, F(1.0)).astype(F), (base.metal * (F(1.0) - hole)).astype(F),
                   (base.mask * (F(1.0) - hole)).astype(F), bump=4.0)


def louver(n: int, tile_m: float, p: dict) -> Surface:
    """Horizontal louver blades (`pitch_m`), shaded underneath, a mullion every 1.5 m."""
    s = p["seed"]
    c = rgb(p.get("color", "#3a3f45"))
    px, py = N.grid(n)
    k = count(tile_m, float(p.get("pitch_m", 0.1)))
    t = (py * F(k) - np.floor(py * F(k))).astype(F)
    blade = N.smooth(0.0, 0.7, t)
    gap = N.smooth(0.85, 0.95, t)
    km = count(tile_m, 1.5)
    tm = np.minimum(px * F(km) - np.floor(px * F(km)), F(1.0) - (px * F(km) - np.floor(px * F(km))))
    mull = N.smooth(0.02, 0.01, tm * F(tile_m / km))
    shade = F(0.55) + F(0.6) * blade - F(0.5) * gap + F(0.1) * mull
    g = grain(n, s, 0)
    return Surface(paint(n, c, (shade + F(0.04) * g).astype(F)),
                   np.clip(F(0.2) + F(0.7) * blade - F(0.6) * gap + F(0.3) * mull, 0, 1).astype(F),
                   full(n, 0.5), full(n, float(p.get("metallic", 0.8))),
                   (F(1.0) - gap).astype(F), bump=40.0)


def stone(n: int, tile_m: float, p: dict) -> Surface:
    """Dressed stone in coursed blocks (`block_m`), or a single face when `block_m` is
    absent: veining, pitting, weathering."""
    s = p["seed"]
    c = rgb(p.get("color", "#9c978d"))
    wear = float(p.get("wear", 0.4))
    px, py = N.grid(n)
    vein = N.ridged(n, 3, s + 1, 4)
    m = mottle(n, s + 2, 3)
    g = grain(n, s + 3, 0)
    pit_d, _ = N.cells(n, count(tile_m, 0.03), s + 4, 1.0)
    pit = N.smooth(0.15, 0.05, pit_d) * F(0.6)
    st = stains(n, s + 5, 0.3 + 0.5 * wear)
    shade = F(1.0) + F(0.1) * (vein - F(0.5)) + F(0.12) * m + F(0.06) * g - F(0.2) * pit \
        - F(0.35) * st
    height = F(0.6) + F(0.1) * m + F(0.08) * g - F(0.2) * pit
    mask = full(n, 1.0)
    blk = p.get("block_m")
    if blk:
        bw, bh = blk
        ky = count(tile_m, bh)
        fy = py * F(ky)
        row = np.floor(fy).astype(np.int64)
        kx = count(tile_m, bw)
        fx = px * F(kx) + np.where(row % 2 == 1, F(0.5), F(0.0))
        cx = np.floor(fx).astype(np.int64)
        ux, uy = fx - np.floor(fx), fy - np.floor(fy)
        e = np.minimum(np.minimum(ux, F(1.0) - ux) * F(tile_m / kx),
                       np.minimum(uy, F(1.0) - uy) * F(tile_m / ky))
        jm = float(p.get("joint_m", 0.008))
        face = N.smooth(jm / 2, jm / 2 + 0.006, e + F(0.004) * (N.fbm(n, 24, s + 6, 3) - F(0.5)))
        tone = N.unit(N.hash2(cx % kx, row, s + 7)) - F(0.5)
        shade = shade + F(0.12) * tone - F(0.4) * (F(1.0) - face)
        height = height * face + F(0.2) * (F(1.0) - face)
        mask = face
    return Surface(paint(n, c, shade.astype(F)), np.clip(height, 0, 1).astype(F),
                   np.clip(F(float(p.get("rough", 0.75))) + F(0.05) * g, 0, 1).astype(F),
                   full(n, 0.0), mask.astype(F), bump=3.0)


def roof(n: int, tile_m: float, p: dict) -> Surface:
    """Flat roofs: `kind` membrane (sheets with welded laps, blisters, ponding stains),
    gravel (ballast stones), tar (bitumen with granules and patches)."""
    s = p["seed"]
    c = rgb(p.get("color", "#4d4b47"))
    wear = float(p.get("wear", 0.5))
    kind = p.get("kind", "membrane")
    px, py = N.grid(n)
    pond = N.smooth(0.55, 0.75, N.fbm(n, 2, s + 1, 4)) * F(0.4 + 0.6 * wear)
    g = grain(n, s + 2, 0)
    if kind == "gravel":
        d, sid = N.cells(n, count(tile_m, 0.025), s + 3, 0.9)
        stone_h = N.smooth(0.65, 0.1, d)
        shade = F(0.7) + F(0.5) * (sid - F(0.5)) + F(0.4) * stone_h - F(0.25) * pond
        height = stone_h
        rough = full(n, 0.95)
        bump = 12.0
    elif kind == "tar":
        gran = N.smooth(0.7, 0.9, N.white(n, s + 3))
        patch = N.smooth(0.6, 0.66, N.fbm(n, 4, s + 4, 4))
        shade = F(0.9) + F(0.15) * gran + F(0.1) * g - F(0.25) * patch - F(0.15) * pond
        height = F(0.5) + F(0.15) * gran + F(0.1) * patch
        rough = F(0.75) - F(0.2) * patch
        bump = 2.0
    else:
        k = count(tile_m, 1.8)
        fx = px * F(k) - np.floor(px * F(k))
        lap = N.smooth(0.01, 0.0, np.minimum(fx, F(1.0) - fx) * F(tile_m / k))
        blister = N.smooth(0.6, 0.8, N.fbm(n, 12, s + 3, 3))
        shade = F(1.0) + F(0.05) * g - F(0.12) * lap - F(0.3) * pond + F(0.05) * blister
        height = F(0.5) + F(0.2) * blister + F(0.2) * lap
        rough = F(0.85) - F(0.15) * pond
        bump = 3.0
    return Surface(paint(n, c, shade.astype(F)), np.clip(height, 0, 1).astype(F),
                   np.clip(rough, 0, 1).astype(F), full(n, 0.0), full(n, 1.0), bump=bump)


def tiles(n: int, tile_m: float, p: dict) -> Surface:
    """Tiles in a grid (`size_m`, `joint_m`; `shape` square, running, herringbone pavers,
    cobble cells, roof shingles), a tone per tile, worn joints (mask 0)."""
    s = p["seed"]
    c = rgb(p.get("color", "#76726c"))
    jc = rgb(p.get("joint", "#4a4743"))
    wear = float(p.get("wear", 0.4))
    shape = p.get("shape", "square")
    tw, th = p.get("size_m", (0.3, 0.3))
    jm = float(p.get("joint_m", 0.006))
    px, py = N.grid(n)
    if shape == "cobble":
        d, cid, d2 = N.cells(n, count(tile_m, tw), s + 1, 0.85, True)
        edge = d2 - d
        face = N.smooth(0.04, 0.12, edge)
        tone = cid - F(0.5)
        dome = N.smooth(0.0, 0.45, edge)
        height = F(0.2) + F(0.7) * dome * face
        bump = 18.0
    else:
        ky = count(tile_m, th)
        fy = py * F(ky)
        row = np.floor(fy).astype(np.int64)
        kx = count(tile_m, tw)
        off = np.where(row % 2 == 1, F(0.5), F(0.0)) if shape in ("running", "shingle") \
            else F(0.0)
        fx = px * F(kx) + off
        col = np.floor(fx).astype(np.int64)
        ux, uy = fx - np.floor(fx), fy - np.floor(fy)
        ex = np.minimum(ux, F(1.0) - ux) * F(tile_m / kx)
        ey = np.minimum(uy, F(1.0) - uy) * F(tile_m / ky)
        if shape == "shingle":
            ey = uy * F(tile_m / ky)
        e = np.minimum(ex, ey) + F(0.002) * (N.fbm(n, 32, s + 2, 3) - F(0.5))
        face = N.smooth(jm / 2, jm / 2 + 0.003, e)
        tone = N.unit(N.hash2(col % kx, row, s + 3)) - F(0.5)
        bevel = N.smooth(jm / 2, jm / 2 + float(p.get("bevel_m", 0.004)), e)
        height = F(0.2) + F(0.7) * bevel
        if shape == "shingle":
            height = height + F(0.3) * uy
        bump = 6.0
    g = grain(n, s + 4, 0)
    st = stains(n, s + 5, 0.2 + 0.4 * wear, 2)
    shade = F(1.0) + F(float(p.get("tone", 0.18))) * tone + F(0.08) * g - F(0.25) * st
    color = mix(paint(n, jc, (F(1.0) + F(0.1) * g).astype(F)), paint(n, c, shade.astype(F)),
                face.astype(F))
    rough = F(float(p.get("rough", 0.8))) + F(0.05) * g + F(0.1) * (F(1.0) - face)
    return Surface(color, np.clip(height + F(0.05) * g, 0, 1).astype(F),
                   np.clip(rough, 0, 1).astype(F), full(n, 0.0), face.astype(F), bump=bump)


def asphalt(n: int, tile_m: float, p: dict) -> Surface:
    """Asphalt: binder with aggregate, `wear` (lighter, rougher, cracked), sealed crack
    snakes, oil drips; `fresh` darker and smoother (patches)."""
    s = p["seed"]
    c = rgb(p.get("color", "#2c2e33"))
    wear = float(p.get("wear", 0.4))
    d, sid = N.cells(n, count(tile_m, 0.012), s + 1, 1.0)
    agg = N.smooth(0.55, 0.25, d)
    agg_tone = sid - F(0.5)
    m = mottle(n, s + 2, 3)
    cr = cracks(n, s + 3, wear)
    snake = N.smooth(0.9, 0.95, N.ridged(n, 3, s + 4, 3)) * F(0.6 + 0.4 * wear)
    oil = N.smooth(0.7, 0.85, N.fbm(n, 4, s + 5, 4)) * F(0.5)
    light = F(0.8 + 0.35 * wear)
    shade = light + F(0.8) * agg * (F(0.45) + agg_tone) + F(0.18) * m - F(0.35) * snake \
        - F(0.3) * oil - F(0.4) * cr
    height = F(0.4) + F(0.4) * agg - F(0.4) * cr + F(0.05) * snake
    rough = F(0.9) - F(0.15) * snake - F(0.25) * oil + F(0.05) * agg
    return Surface(paint(n, c, shade.astype(F)), np.clip(height, 0, 1).astype(F),
                   np.clip(rough, 0, 1).astype(F), full(n, 0.0), full(n, 1.0), bump=4.0)


def grass(n: int, tile_m: float, p: dict) -> Surface:
    """Lawn: blades as stretched noise, clover patches, dry spots."""
    s = p["seed"]
    c = rgb(p.get("color", "#3f5a2c"))
    px, py = N.grid(n)
    blades = N.fbm(n, max(4, count(tile_m, 0.01)), s + 1, 2, 0.5, px,
                   (py * F(0.25)).astype(F))
    patch = N.fbm(n, 4, s + 2, 4)
    dry = N.smooth(0.6, 0.8, N.fbm(n, 3, s + 3, 4))
    shade = F(0.8) + F(0.5) * (blades - F(0.5)) + F(0.2) * (patch - F(0.5))
    col = paint(n, c, shade.astype(F))
    col = col + (rgb("#7d7247")[None, None, :] - col) * (dry * F(0.6))[:, :, None]
    return Surface(np.clip(col, 0, 1).astype(F), blades.astype(F), full(n, 0.95),
                   full(n, 0.0), full(n, 1.0), bump=8.0)


def gravel(n: int, tile_m: float, p: dict) -> Surface:
    """Track ballast or loose gravel."""
    s = p["seed"]
    c = rgb(p.get("color", "#4f4b47"))
    d, sid = N.cells(n, count(tile_m, float(p.get("stone_m", 0.05))), s + 1, 0.95)
    h = N.smooth(0.7, 0.05, d)
    shade = F(0.6) + F(0.5) * (sid - F(0.5)) + F(0.5) * h
    return Surface(paint(n, c, shade.astype(F)), h.astype(F), full(n, 0.95), full(n, 0.0),
                   full(n, 1.0), bump=30.0)


def bark(n: int, tile_m: float, p: dict) -> Surface:
    """Tree bark, u along the branch (AG8's tubes run UV0 along them): `kind` furrowed
    (ridges and plates split by furrows), smooth (pale, with dark lenticels across the stem
    and peeling patches) or ringed (a palm's leaf scars and fibres); lichen patches keep
    their own grey-green (mask 0)."""
    s = p["seed"]
    c = rgb(p.get("color", "#4a3a2e"))
    kind = p.get("kind", "furrowed")
    px, py = N.grid(n)
    fine = grain(n, s + 1, 1)
    if kind == "smooth":
        dash = N.value(n, max(8, count(tile_m, 0.02)), s + 2, px, (py * F(0.15)).astype(F))
        lent = N.smooth(0.78, 0.86, dash)
        peel = N.smooth(0.62, 0.7, N.fbm(n, 4, s + 3, 4))
        shade = F(1.0) + F(0.04) * fine - F(0.65) * lent - F(0.25) * peel
        height = F(0.6) - F(0.3) * lent + F(0.1) * peel + F(0.03) * fine
        rough = F(0.6) + F(0.2) * lent
    elif kind == "ringed":
        k = count(tile_m, 0.09)
        fx = (px * F(k) + F(0.15) * N.fbm(n, 4, s + 2, 3)).astype(F)
        t = (fx - np.floor(fx)).astype(F)
        scar = N.smooth(0.1, 0.0, np.minimum(t, F(1.0) - t))
        fib = N.value(n, max(8, count(tile_m, 0.01)), s + 3, px, (py * F(0.2)).astype(F))
        shade = F(1.0) - F(0.45) * scar + F(0.15) * (fib - F(0.5)) + F(0.05) * fine
        height = F(0.6) - F(0.5) * scar + F(0.1) * (fib - F(0.5))
        rough = F(0.9) - F(0.0) * scar
    else:
        ridge = N.fbm(n, max(4, count(tile_m, 0.06)), s + 2, 4, 0.5, (px * F(0.2)).astype(F),
                      py)
        furrow = N.smooth(0.38, 0.62, ridge)
        d, sid = N.cells(n, count(tile_m, 0.12), s + 3, 0.9)
        plate = N.smooth(0.85, 0.5, d)
        top = (furrow * (F(0.6) + F(0.4) * plate)).astype(F)
        shade = F(0.45) + F(0.7) * top + F(0.15) * (sid - F(0.5)) + F(0.06) * fine
        height = F(0.1) + F(0.8) * top + F(0.05) * fine
        rough = F(0.95) - F(0.1) * top
    lichen = N.smooth(0.7, 0.78, N.fbm(n, 6, s + 5, 4)) * F(float(p.get("lichen", 0.3)))
    col = mix(paint(n, c, shade.astype(F)), paint(n, rgb("#7f8a6d"), (F(0.85) + F(0.3) * fine)
                                                    .astype(F)), lichen.astype(F))
    return Surface(col, np.clip(height, 0, 1).astype(F), np.clip(rough, 0, 1).astype(F),
                   full(n, 0.0), (F(1.0) - lichen).astype(F), bump=6.0)


def _r(*key) -> float:
    """A uniform number in [0, 1) from a hash of the key (the leaves' layout)."""
    return (N.seed_of(*key) >> 8) / 16777216.0


def leaves(n: int, tile_m: float, p: dict) -> Surface:
    """A clump of leaves for alpha-cut cards (AG8's trees, shrubs and ivy): twigs from the
    middle, leaves of `shape` (broad, lobed, fan, needle, small) along them within a circle
    of the tile, the rest cut away. The tint mask is the leaf cover, which the `leaves`
    master also takes as opacity; a tone per leaf, a midrib and veins, a dome for the normal
    map. Not tileable: a card shows the whole tile."""
    from citygen import dmath as M
    s = p["seed"]
    shape = p.get("shape", "broad")
    c = rgb(p.get("color", "#5b7a34"))
    L0 = float(p.get("leaf_m", 0.1)) / tile_m
    asp = float(p.get("aspect", 0.5))
    twigs, per = int(p.get("twigs", 6)), int(p.get("per", 7))
    px, py = N.grid(n)
    col = np.zeros((n, n, 3), dtype=F) + (c * F(0.7))[None, None, :]
    hgt = np.zeros((n, n), dtype=F)
    cov = np.zeros((n, n), dtype=F)
    items = []
    for t in range(twigs):
        a0 = 2.0 * M.PI * (t + 0.4 * _r(s, "ta", t)) / twigs
        tl = 0.24 + 0.12 * _r(s, "tl", t)
        for j in range(per + 1):
            f = 0.12 + 0.88 * (j + 0.5) / (per + 1)
            side = 0.0 if j == per else (1.0 if j % 2 else -1.0)
            ang = a0 + side * (0.55 + 0.35 * _r(s, "la", t, j))
            sc = (0.75 + 0.45 * _r(s, "ls", t, j)) * (1.0 - 0.25 * (1.0 - f))
            items.append((0.5 + M.cos(a0) * tl * f, 0.5 + M.sin(a0) * tl * f, ang, sc,
                          _r(s, "tone", t, j)))
    for bx, by, ang, sc, tone in items:
        L, W = L0 * sc, L0 * sc * asp
        R = L * 1.15
        i0, i1 = max(0, int((by - R) * n)), min(n, int((by + R) * n) + 2)
        j0, j1 = max(0, int((bx - R) * n)), min(n, int((bx + R) * n) + 2)
        if i0 >= i1 or j0 >= j1:
            continue
        ca, sa = F(M.cos(ang)), F(M.sin(ang))
        dx = px[i0:i1, j0:j1] - F(bx)
        dy = py[i0:i1, j0:j1] - F(by)
        u = ((dx * ca + dy * sa) / F(L)).astype(F)
        v = ((dy * ca - dx * sa) / F(W)).astype(F)
        if shape == "fan":
            r2 = u * u + (v * F(asp)) * (v * F(asp))
            inside = (u > F(0.05)) & (r2 < F(1.0)) & (np.abs(v * F(asp)) < u * F(1.15)) & \
                ~((np.abs(v) < F(0.06)) & (r2 > F(0.55)))
            hw = np.maximum(u * F(1.15) / F(asp), F(0.05))
            ribs = N.smooth(0.12, 0.0, np.abs(((v / hw) * F(6.0)) - np.round((v / hw) * F(6.0))))
        elif shape == "needle":
            inside = np.zeros(u.shape, dtype=bool)
            for k in range(5):
                b = (k - 2) * 0.22
                cb, sb = F(M.cos(b)), F(M.sin(b))
                uu = u * cb + v * F(asp) * sb
                vv = (v * F(asp) * cb - u * sb) / F(0.045)
                inside |= (uu > F(0.0)) & (uu < F(1.0)) & (np.abs(vv) < F(1.0) - uu * F(0.6))
            hw = F(1.0)
            ribs = np.zeros(u.shape, dtype=F)
        else:
            body = u * (F(1.0) - u) * F(4.0)
            hw = np.maximum(F(0.5) * body * (F(1.15) - F(0.3) * u), F(0.0))
            inside = (u > F(0.0)) & (u < F(1.0)) & (np.abs(v) < hw)
            if shape == "lobed":
                for lu, lv in ((0.45, 0.62), (0.45, -0.62), (0.2, 0.45), (0.2, -0.45)):
                    du = (u - F(lu)) / F(0.3)
                    dv = (v - F(lv)) / F(0.32)
                    inside |= (du * du + dv * dv) < F(1.0)
                hw = np.maximum(hw, F(0.6))
            ribs = N.smooth(0.1, 0.0, np.abs(((u - np.abs(v) * F(0.9)) * F(7.0))
                                              - np.round((u - np.abs(v) * F(0.9)) * F(7.0))))
        rel = np.clip(np.abs(v) / np.maximum(hw, F(0.05)), F(0.0), F(1.0))
        mid = N.smooth(0.07, 0.0, np.abs(v)) * (u > F(0.0))
        dome = F(1.0) - rel * rel
        shade = (F(0.78) + F(0.4) * F(tone) + F(0.18) * mid - F(0.12) * ribs
                 - F(0.2) * (F(1.0) - dome)).astype(F)
        lc = np.clip(c[None, None, :] * shade[:, :, None], 0.0, 1.0).astype(F)
        sub_c = col[i0:i1, j0:j1]
        col[i0:i1, j0:j1] = np.where(inside[:, :, None], lc, sub_c)
        hgt[i0:i1, j0:j1] = np.where(inside, F(0.45) + F(0.4) * dome - F(0.1) * mid,
                                     hgt[i0:i1, j0:j1])
        cov[i0:i1, j0:j1] = np.where(inside, F(1.0), cov[i0:i1, j0:j1])
    rough = full(n, float(p.get("rough", 0.6)))
    return Surface(col, hgt, rough, full(n, 0.0), cov, ao=(F(0.7) + F(0.3) * hgt).astype(F),
                   bump=1.5)


GENERATORS = {
    "concrete": concrete, "plaster": plaster, "brick": brick, "panel": panel,
    "ribbed": ribbed, "sheet": sheet, "fabric": fabric, "wood": wood,
    "smooth_paint": smooth_paint, "brushed": brushed, "perforated": perforated,
    "louver": louver, "stone": stone, "roof": roof, "tiles": tiles, "asphalt": asphalt,
    "grass": grass, "gravel": gravel, "bark": bark, "leaves": leaves,
}


def make(gen: str, n: int, tile_m: float, params: dict) -> Surface:
    fn = GENERATORS.get(gen)
    if fn is None:
        from .water_surfaces import GENERATORS as WATER     # (AG12's beds and banks)
        fn = WATER[gen]
    return fn(n, tile_m, params)


# --- AG13: ground cover (lawn, meadow, dirt, mud, gravel, sand, moss, rubble) ---------------
#
# The sets of M16's open land. Vegetation takes the tint (mask 1: a district's lawn greener or
# browner), soil, stones and water keep their own color (mask 0).

def turf(n: int, tile_m: float, p: dict) -> Surface:
    """Mown lawn: dense fine blades, faint mowing stripes (`stripe_m`), clover patches,
    thatch and a few bare spots of soil (`bare`)."""
    s = p["seed"]
    c = rgb(p.get("color", "#4f7a34"))
    px, py = N.grid(n)
    blades = N.fbm(n, max(8, count(tile_m, 0.006)), s + 1, 2, 0.55, px,
                   (py * F(0.5)).astype(F))
    fine = N.white(n, s + 2)
    patch = N.fbm(n, 4, s + 3, 4)
    k = count(tile_m, float(p.get("stripe_m", 1.0)))
    stripe = (np.floor(px * F(k)).astype(np.int64) % 2).astype(F)
    clover_d, _ = N.cells(n, count(tile_m, 0.03), s + 4, 0.9)
    clover = N.smooth(0.45, 0.2, clover_d) * N.smooth(0.62, 0.72, N.fbm(n, 4, s + 5, 3))
    bare = N.smooth(0.72, 0.8, N.fbm(n, 3, s + 6, 4)) * F(float(p.get("bare", 0.3)))
    shade = F(0.82) + F(0.45) * (blades - F(0.5)) + F(0.18) * (patch - F(0.5)) \
        + F(0.06) * (stripe - F(0.5)) + F(0.12) * (fine - F(0.5))
    col = paint(n, c, shade.astype(F))
    col = mix(col, paint(n, rgb("#5a8a3a"), (F(0.9) + F(0.2) * fine).astype(F)),
              (clover * F(0.35)).astype(F))
    thatch = N.smooth(0.55, 0.75, N.fbm(n, 6, s + 7, 3)) * F(0.35)
    col = mix(col, paint(n, rgb("#8a7a4c"), (F(0.9) + F(0.2) * fine).astype(F)),
              thatch.astype(F))
    earth = paint(n, rgb("#5a4632"), (F(0.85) + F(0.3) * fine).astype(F))
    col = mix(col, earth, bare.astype(F))
    height = F(0.5) + F(0.35) * (blades - F(0.5)) + F(0.15) * clover - F(0.3) * bare
    return Surface(np.clip(col, 0, 1).astype(F), np.clip(height, 0, 1).astype(F),
                   full(n, 0.95), full(n, 0.0), (F(1.0) - bare).astype(F), bump=10.0)


def meadow(n: int, tile_m: float, p: dict) -> Surface:
    """Long unmown grass: blades in swirling clumps, green over straw (`dry`), seed heads,
    soil between the clumps."""
    s = p["seed"]
    c = rgb(p.get("color", "#6b8a3a"))
    dry = float(p.get("dry", 0.35))
    qx, qy = N.warp(n, 4, s + 1, 0.15)
    blades = N.fbm(n, max(8, count(tile_m, 0.01)), s + 2, 2, 0.5, qx,
                   (qy * F(0.35)).astype(F))
    clump_d, cid = N.cells(n, count(tile_m, 0.25), s + 3, 0.9)
    clump = N.smooth(0.95, 0.15, clump_d) * F(0.6) + F(0.4) * N.fbm(n, count(tile_m, 0.3),
                                                                   s + 8, 3)
    fine = N.white(n, s + 4)
    straw = N.smooth(0.45, 0.7, N.fbm(n, 4, s + 5, 4)) * F(dry) + F(0.25 * dry) * cid
    heads_d, _ = N.cells(n, count(tile_m, 0.035), s + 6, 1.0)
    heads = N.smooth(0.22, 0.1, heads_d) * N.smooth(0.55, 0.7, N.white(n, s + 7))
    shade = F(0.72) + F(0.55) * (blades - F(0.5)) + F(0.35) * clump + F(0.1) * (fine - F(0.5))
    col = paint(n, c, shade.astype(F))
    col = mix(col, paint(n, rgb("#b09a5a"), shade.astype(F)), np.clip(straw, 0, 1).astype(F))
    col = mix(col, paint(n, rgb("#d8cc9a"), (F(0.9) + F(0.2) * fine).astype(F)),
              (heads * F(0.8)).astype(F))
    earth = paint(n, rgb("#4a3a2a"), (F(0.8) + F(0.3) * fine).astype(F))
    gap = N.smooth(0.25, 0.0, clump + F(0.4) * blades)
    col = mix(col, earth, (gap * F(0.8)).astype(F))
    height = F(0.3) + F(0.45) * clump + F(0.25) * (blades - F(0.5))
    return Surface(np.clip(col, 0, 1).astype(F), np.clip(height, 0, 1).astype(F),
                   full(n, 0.97), full(n, 0.0), (F(1.0) - gap).astype(F), bump=25.0)


def soil(n: int, tile_m: float, p: dict) -> Surface:
    """Bare earth: clods, pebbles, root threads, dry cracks (`dry`), trodden smooth patches
    (`trodden`)."""
    s = p["seed"]
    c = rgb(p.get("color", "#6a5038"))
    dry = float(p.get("dry", 0.4))
    m = mottle(n, s, 4)
    g = grain(n, s + 1, 1)
    clod_d, cid = N.cells(n, count(tile_m, 0.05), s + 2, 0.95)
    clod = N.smooth(0.7, 0.2, clod_d)
    peb_d, pid = N.cells(n, count(tile_m, 0.02), s + 3, 1.0)
    peb = N.smooth(0.28, 0.16, peb_d) * N.smooth(0.7, 0.8, N.white(n, s + 4))
    roots = N.smooth(0.94, 0.97, N.ridged(n, 8, s + 5, 3)) * F(0.5)
    cr = cracks(n, s + 6, dry) * F(dry)
    trod = N.smooth(0.55, 0.75, N.fbm(n, 3, s + 7, 4)) * F(float(p.get("trodden", 0.3)))
    shade = F(0.95) + F(0.3) * m + F(0.12) * g + F(0.12) * (cid - F(0.5)) * clod \
        - F(0.35) * cr - F(0.2) * roots + F(0.1) * trod
    col = paint(n, c, shade.astype(F))
    col = mix(col, paint(n, rgb("#8e877b"), (F(0.8) + F(0.5) * pid).astype(F)), peb.astype(F))
    height = F(0.45) + F(0.25) * clod * (F(1.0) - trod) + F(0.3) * peb - F(0.3) * cr \
        + F(0.08) * g
    rough = F(0.92) - F(0.12) * trod + F(0.04) * g
    return Surface(np.clip(col, 0, 1).astype(F), np.clip(height, 0, 1).astype(F),
                   np.clip(rough, 0, 1).astype(F), full(n, 0.0), full(n, 0.0), bump=12.0)


def mud(n: int, tile_m: float, p: dict) -> Surface:
    """Wet earth: smeared, rutted, with puddles that mirror the sky (low roughness)."""
    s = p["seed"]
    c = rgb(p.get("color", "#4a3a2b"))
    px, py = N.grid(n)
    m = mottle(n, s, 3)
    g = grain(n, s + 1, 1)
    ruts = N.fbm(n, 3, s + 2, 4, 0.5, px, (py * F(0.25)).astype(F))
    rut = N.smooth(0.42, 0.3, ruts) + N.smooth(0.58, 0.7, ruts)
    smear = N.fbm(n, 6, s + 3, 4, 0.5, (px * F(0.5)).astype(F), py)
    pud = N.smooth(0.62, 0.68, N.fbm(n, 3, s + 4, 4)) * F(float(p.get("puddles", 0.6)))
    shade = F(0.85) + F(0.25) * m + F(0.1) * g + F(0.2) * (smear - F(0.5)) - F(0.15) * rut
    col = paint(n, c, shade.astype(F))
    col = mix(col, paint(n, rgb("#2e261e"), full(n, 1.0)), (pud * F(0.85)).astype(F))
    height = F(0.5) + F(0.2) * m - F(0.25) * rut - F(0.3) * pud + F(0.05) * g
    rough = F(0.55) - F(0.45) * pud + F(0.08) * g
    return Surface(np.clip(col, 0, 1).astype(F), np.clip(height, 0, 1).astype(F),
                   np.clip(rough, 0.04, 1).astype(F), full(n, 0.0), full(n, 0.0), bump=8.0)


def loose_gravel(n: int, tile_m: float, p: dict) -> Surface:
    """Loose gravel and grit: stones of two sizes over dust, a few darker oil spots (`oil`)."""
    s = p["seed"]
    c = rgb(p.get("color", "#8a8378"))
    d1, id1, e1 = N.cells(n, count(tile_m, float(p.get("stone_m", 0.03))), s + 1, 0.95, True)
    d2, id2 = N.cells(n, count(tile_m, 0.012), s + 2, 1.0)
    big = N.smooth(0.02, 0.1, e1 - d1) * N.smooth(0.75, 0.3, d1)
    small = N.smooth(0.42, 0.2, d2)
    g = grain(n, s + 3, 0)
    dust = paint(n, rgb("#9c9282"), (F(0.85) + F(0.3) * g).astype(F))
    stones = paint(n, c, (F(0.7) + F(0.6) * (id1 - F(0.5)) + F(0.4) * big).astype(F))
    grit = paint(n, c, (F(0.75) + F(0.5) * (id2 - F(0.5))).astype(F))
    col = mix(dust, grit, (small * F(0.8)).astype(F))
    col = mix(col, stones, big.astype(F))
    oil = N.smooth(0.7, 0.8, N.fbm(n, 3, s + 4, 4)) * F(float(p.get("oil", 0.2)))
    col = mix(col, paint(n, rgb("#2e2c29"), full(n, 1.0)), (oil * F(0.6)).astype(F))
    height = F(0.25) + F(0.6) * big + F(0.25) * small + F(0.05) * g
    return Surface(np.clip(col, 0, 1).astype(F), np.clip(height, 0, 1).astype(F),
                   full(n, 0.9), full(n, 0.0), full(n, 0.0), bump=20.0)


def sand(n: int, tile_m: float, p: dict) -> Surface:
    """Fine sand: grain, wind ripples (`ripple_m`), a scatter of shell and stone bits,
    shallow dents of footprints."""
    s = p["seed"]
    c = rgb(p.get("color", "#d2bd8a"))
    qx, qy = N.warp(n, 3, s + 1, 0.08)
    k = count(tile_m, float(p.get("ripple_m", 0.12)))
    t = (qy * F(k)) - np.floor(qy * F(k))
    rip = _wave(t.astype(F)) * N.smooth(0.3, 0.6, N.fbm(n, 3, s + 2, 3))
    g = grain(n, s + 3, 0)
    m = mottle(n, s + 4, 3)
    bits_d, bid = N.cells(n, count(tile_m, 0.04), s + 5, 1.0)
    bits = N.smooth(0.12, 0.06, bits_d) * N.smooth(0.8, 0.88, N.white(n, s + 6))
    dent_d, _ = N.cells(n, count(tile_m, 0.35), s + 7, 0.9)
    dent = N.smooth(0.25, 0.1, dent_d) * N.smooth(0.6, 0.7, N.fbm(n, 2, s + 8, 2))
    shade = F(0.96) + F(0.12) * m + F(0.14) * g + F(0.08) * (rip - F(0.5)) - F(0.08) * dent
    col = paint(n, c, shade.astype(F))
    col = mix(col, paint(n, rgb("#eee6d2"), (F(0.85) + F(0.3) * bid).astype(F)),
              bits.astype(F))
    height = F(0.5) + F(0.25) * rip + F(0.1) * g - F(0.2) * dent + F(0.15) * bits
    return Surface(np.clip(col, 0, 1).astype(F), np.clip(height, 0, 1).astype(F),
                   (F(0.92) + F(0.04) * g).astype(F), full(n, 0.0), full(n, 0.0), bump=6.0)


def moss(n: int, tile_m: float, p: dict) -> Surface:
    """Cushion moss in the shade: rounded cushions of green and yellow green, dark gaps of
    damp soil."""
    s = p["seed"]
    c = rgb(p.get("color", "#4d6a2a"))
    d, cid = N.cells(n, count(tile_m, 0.05), s + 1, 0.9)
    soft = N.fbm(n, count(tile_m, 0.08), s + 4, 3)
    cush = N.smooth(0.85, 0.05, d) * N.smooth(0.15, 0.5, soft + F(0.1)) \
        + F(0.35) * N.smooth(0.3, 0.7, soft)
    fine = N.fbm(n, max(8, count(tile_m, 0.004)), s + 2, 2)
    g = grain(n, s + 3, 0)
    shade = F(0.7) + F(0.5) * cush + F(0.3) * (fine - F(0.5)) + F(0.06) * (cid - F(0.5))
    col = paint(n, c, shade.astype(F))
    yellow = N.smooth(0.5, 0.75, N.fbm(n, 3, s + 5, 3)) * F(0.45)
    col = mix(col, paint(n, rgb("#8a9a3a"), shade.astype(F)), yellow.astype(F))
    gap = N.smooth(0.25, 0.02, cush)
    col = mix(col, paint(n, rgb("#2f2a20"), (F(0.85) + F(0.3) * g).astype(F)),
              (gap * F(0.55)).astype(F))
    height = F(0.2) + F(0.7) * cush + F(0.1) * fine
    return Surface(np.clip(col, 0, 1).astype(F), np.clip(height, 0, 1).astype(F),
                   full(n, 0.9), full(n, 0.0), (F(1.0) - gap).astype(F), bump=15.0)


def rubble(n: int, tile_m: float, p: dict) -> Surface:
    """Rubble on dirt: angular chunks of broken concrete and brick (`brick` share), grit,
    dust."""
    s = p["seed"]
    d, cid, d2 = N.cells(n, count(tile_m, float(p.get("chunk_m", 0.12))), s + 1, 0.95, True)
    keep = N.smooth(0.3, 0.45, cid) * N.smooth(0.35, 0.55, N.fbm(n, 3, s + 6, 3) + F(0.1))
    face = N.smooth(0.01, 0.05, d2 - d) * N.smooth(0.55 + 0.3 * 0.5, 0.3, d) * keep
    sd, sid = N.cells(n, count(tile_m, 0.03), s + 2, 1.0)
    grit = N.smooth(0.4, 0.2, sd) * N.smooth(0.5, 0.6, N.white(n, s + 3))
    g = grain(n, s + 4, 1)
    m = mottle(n, s + 5, 3)
    dirt = paint(n, rgb(p.get("dirt", "#6a5642")),
                 (F(0.85) + F(0.25) * m + F(0.1) * g).astype(F))
    brick = cid > F(1.0 - float(p.get("brick", 0.3)))
    chunk_c = np.where(brick[:, :, None], rgb("#6e3c2e")[None, None, :],
                       rgb(p.get("color", "#8f8c84"))[None, None, :]).astype(F)
    chunk = np.clip(chunk_c * (F(0.6) + F(0.45) * cid + F(0.15) * g
                               + F(0.25) * (m - F(0.5)))[:, :, None], 0, 1)
    col = mix(dirt, paint(n, rgb("#8a857a"), (F(0.8) + F(0.4) * sid).astype(F)),
              (grit * F(0.7)).astype(F))
    col = mix(col, chunk.astype(F), face.astype(F))
    height = F(0.2) + F(0.7) * face * (F(0.6) + F(0.4) * cid) + F(0.15) * grit + F(0.05) * g
    return Surface(np.clip(col, 0, 1).astype(F), np.clip(height, 0, 1).astype(F),
                   full(n, 0.9), full(n, 0.0), full(n, 0.0), bump=40.0)


GENERATORS.update({"turf": turf, "meadow": meadow, "soil": soil, "mud": mud,
                   "loose_gravel": loose_gravel, "sand": sand, "moss": moss,
                   "rubble": rubble})
