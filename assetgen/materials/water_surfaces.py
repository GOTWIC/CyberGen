"""AG12's surface generators and the water atlas (procedural numpy, exact as `surfaces.py`):

- `sediment`: a water bed of mud, silt or sand: mottled deposits, worm casts and shell grit
  on mud, drag streaks on silt, ripple marks on sand (a ramp profile across warped crests,
  the steep side downstream), pebbles where asked.
- `water_rubble`: packed stones (Worley cells, rounded, dark joints of silt between them),
  the riprap band under its stones and a stony bed.
- `water_soil`: a bank's earth: crumbly soil, roots, pebbles and grass tufts.

(Named apart from AG13's `rubble` and `soil` in `surfaces.GENERATORS`, which `surfaces.make`
looks up first.)
- `water_atlas`: the water master's maps over `WATER_TILE_M`: ripple normals (OpenGL), foam
  (R a lacy foam network, G a finer one, B bubbles) and caustics (R and G two networks the
  bed master scrolls against each other, B their soft glow).
"""

from __future__ import annotations

import numpy as np

from . import noise as N
from . import pbr as P
from .surfaces import Surface, count, full, grain, mottle, paint, rgb

F = np.float32
WATER_TILE_M = 8.0


def sediment(n: int, tile_m: float, p: dict) -> Surface:
    s = p["seed"]
    kind = p.get("kind", "mud")
    c = rgb(p.get("color", "#4a4033"))
    px, py = N.grid(n)
    base = N.fbm(n, 4, s + 1, 5)
    m = mottle(n, s + 2, 6)
    g = grain(n, s + 3, 0)
    height = F(0.5) + F(0.25) * (base - F(0.5)) + F(0.05) * g
    shade = F(1.0) + F(0.18) * (base - F(0.5)) + F(0.1) * m + F(0.05) * g
    rough = np.full((n, n), F(float(p.get("rough", 0.9))))
    mask = full(n, 1.0)
    if kind == "sand":
        # ripple marks: warped crests across the tile, a ramp up and a steep fall
        k = count(tile_m, float(p.get("ripple_m", 0.14)))
        wx, wy = N.warp(n, 3, s + 4, 0.06)
        t = (wy * F(k) + F(0.35) * N.fbm(n, 4, s + 5, 3)) % F(1.0)
        rip = np.where(t < F(0.75), t / F(0.75), (F(1.0) - t) / F(0.25)).astype(F)
        height = height * F(0.4) + F(0.55) * rip
        shade = shade + F(0.12) * (rip - F(0.5))
    elif kind == "silt":
        streak = N.fbm(n, 2, s + 6, 4, 0.5, px, (py * F(0.15)).astype(F))
        height = height * F(0.6) + F(0.2) * streak
        shade = shade + F(0.08) * (streak - F(0.5))
    else:
        # worm casts (small raised blobs) and darker organic patches
        d, _ = N.cells(n, count(tile_m, 0.09), s + 7, 0.9)
        cast = N.smooth(0.28, 0.08, d) * N.smooth(0.55, 0.75, N.white(n, s + 8))
        height = height + F(0.18) * cast
        shade = shade - F(0.12) * N.smooth(0.55, 0.8, N.fbm(n, 3, s + 9, 4))
    peb = float(p.get("pebbles", 0.0))
    if peb > 0:
        d, sid = N.cells(n, count(tile_m, 0.05), s + 10, 0.95)
        on = (sid < F(peb)).astype(F) * N.smooth(0.42, 0.25, d)
        height = height + F(0.35) * on
        shade = shade * (F(1.0) - F(0.25) * on) + F(0.25) * on * (F(0.8) + F(0.4) * sid)
        mask = mask * (F(1.0) - on)
    shells = float(p.get("shells", 0.0))
    if shells > 0:
        w = N.smooth(1.0 - shells * 0.02, 1.0, N.white(n, s + 11))
        shade = shade + F(0.8) * w
        mask = mask * (F(1.0) - w)
    return Surface(paint(n, c, shade.astype(F)), np.clip(height, 0, 1).astype(F),
                   rough, full(n, 0.0), mask.astype(F), bump=float(p.get("bump", 12.0)))


def rubble(n: int, tile_m: float, p: dict) -> Surface:
    s = p["seed"]
    c = rgb(p.get("color", "#6d6a63"))
    joint = rgb(p.get("joint", "#2f2b25"))
    d1, sid, d2 = N.cells(n, count(tile_m, float(p.get("stone_m", 0.35))), s + 1, 0.9,
                          second=True)
    edge = d2 - d1
    rock = N.smooth(0.03, 0.22, edge)
    dome = np.clip(F(1.0) - d1 * F(1.1), F(0.0), F(1.0))
    g = grain(n, s + 2, 0)
    v = N.ridged(n, 6, s + 3, 3)
    height = F(0.15) + F(0.6) * rock * (F(0.5) + F(0.5) * dome) + F(0.05) * g
    shade = F(0.85) + F(0.3) * (sid - F(0.5)) + F(0.1) * (v - F(0.5)) + F(0.06) * g
    col = paint(n, c, shade.astype(F))
    col = col + (joint[None, None, :] - col) * (F(1.0) - rock)[:, :, None]
    wet = float(p.get("wet", 0.0))
    rough = F(0.85) - F(0.25 * wet) * rock
    return Surface(np.clip(col, 0, 1).astype(F), np.clip(height, 0, 1).astype(F),
                   np.clip(rough, 0, 1).astype(F), full(n, 0.0), rock.astype(F), bump=40.0)


def soil(n: int, tile_m: float, p: dict) -> Surface:
    s = p["seed"]
    c = rgb(p.get("color", "#5d5440"))
    grass = rgb(p.get("grass", "#4f6a35"))
    px, py = N.grid(n)
    crumb = N.fbm(n, count(tile_m, 0.25), s + 1, 4)
    g = grain(n, s + 2, 1)
    roots = N.smooth(0.82, 0.95, N.ridged(n, 3, s + 3, 3))
    d, sid = N.cells(n, count(tile_m, 0.06), s + 4, 0.95)
    stone = (sid < F(0.07)).astype(F) * N.smooth(0.4, 0.22, d) * F(0.75)
    tuft = N.smooth(0.58, 0.72, N.fbm(n, 3, s + 5, 4))
    blades = N.fbm(n, count(tile_m, 0.01), s + 6, 2, 0.5, px, (py * F(0.3)).astype(F))
    height = F(0.45) + F(0.2) * crumb + F(0.06) * g + F(0.25) * stone + F(0.2) * tuft * blades
    shade = F(0.9) + F(0.2) * (crumb - F(0.5)) + F(0.08) * g - F(0.25) * roots
    col = paint(n, c, shade.astype(F))
    col = col + (rgb("#6f6a60")[None, None, :] - col) * stone[:, :, None]
    gcol = paint(n, grass, (F(0.75) + F(0.5) * blades).astype(F))
    col = col + (gcol - col) * tuft[:, :, None]
    mask = (F(1.0) - stone) * (F(1.0) - tuft)
    return Surface(np.clip(col, 0, 1).astype(F), np.clip(height, 0, 1).astype(F),
                   full(n, 0.95), full(n, 0.0), mask.astype(F), bump=20.0)


GENERATORS = {"sediment": sediment, "water_rubble": rubble, "water_soil": soil}


# --- the water atlas ---------------------------------------------------------------------

def water_atlas(density: int) -> dict[str, np.ndarray]:
    """{"normal", "foam", "caustics"} maps (uint8) over WATER_TILE_M, 1024 px at 512 px/m."""
    n = max(64, min(1024, density * 2))
    s = N.seed_of("ag12.water")
    # ripples: small capillary waves over longer swell-like undulations
    h = (F(0.55) * N.fbm(n, 8, s + 1, 4, 0.55) + F(0.3) * N.fbm(n, 32, s + 2, 3, 0.5)
         + F(0.15) * N.ridged(n, 16, s + 3, 3))
    nrm = P.u8(P.normal(h.astype(F), 60.0, WATER_TILE_M))
    # foam: lacy networks (Worley edges) broken up by patches, and bubbles
    out = []
    for k, period in enumerate((10, 20)):
        d1, _, d2 = N.cells(n, period, s + 10 + k, 0.95, second=True)
        lace = F(1.0) - N.smooth(0.0, 0.18, d2 - d1)
        patch = N.smooth(0.35, 0.7, N.fbm(n, 4, s + 20 + k, 4))
        out.append(np.clip(lace * (F(0.4) + F(0.6) * patch) + F(0.35) * patch * patch, 0, 1))
    bd, bsid = N.cells(n, 48, s + 30, 0.95)
    bub = N.smooth(0.3, 0.12, bd) * (bsid < F(0.4)).astype(F)
    foam = np.stack([P.u8(out[0]), P.u8(out[1]), P.u8(bub), P.u8(full(n, 1.0))], axis=2)
    # caustics: bright thin networks
    cs = []
    for k in range(2):
        qx, qy = N.warp(n, 4, s + 40 + k, 0.05)
        d1, _, d2 = _cells_at(n, 12, s + 50 + k, qx, qy)
        c = F(1.0) - N.smooth(0.0, 0.12, d2 - d1)
        cs.append((c * c).astype(F))
    glow = N.blur(np.maximum(cs[0], cs[1]), max(1, n // 128))
    caus = np.stack([P.u8(cs[0]), P.u8(cs[1]), P.u8(glow)], axis=2)
    return {"normal": nrm, "foam": foam, "caustics": caus}


def _cells_at(n: int, period: int, seed: int, px, py):
    """Worley F1, cell id and F2 at warped sample positions (tileable)."""
    fx = (px * F(period)).astype(F)
    fy = (py * F(period)).astype(F)
    x0 = np.floor(fx).astype(np.int64)
    y0 = np.floor(fy).astype(np.int64)
    best = np.full((n, n), F(9.0), dtype=F)
    best2 = np.full((n, n), F(9.0), dtype=F)
    bid = np.zeros((n, n), dtype=F)
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            cx = x0 + ox
            cy = y0 + oy
            wx = cx % period
            wy = cy % period
            jx = F(0.5) + F(0.9) * (N.unit(N.hash2(wx, wy, seed)) - F(0.5))
            jy = F(0.5) + F(0.9) * (N.unit(N.hash2(wx, wy, seed + 7)) - F(0.5))
            dx = cx.astype(F) + jx - fx
            dy = cy.astype(F) + jy - fy
            d = np.sqrt(dx * dx + dy * dy).astype(F)
            closer = d < best
            best2 = np.where(closer, best, np.minimum(best2, d))
            best = np.where(closer, d, best)
            bid = np.where(closer, N.unit(N.hash2(wx, wy, seed + 13)), bid)
    return best, bid, best2
