"""Integer-hash noise for the texture library (scope 5.2, section 10).

Every pixel comes from blake2b-free integer hashing on uint32 lattices and elementwise IEEE
arithmetic (add, multiply, divide, sqrt, floor, min, max) in a fixed order: no numpy
transcendentals, no float reductions, so the decoded pixels are the same on every machine.

All fields tile: a lattice of period `p` (dividing the image size) wraps at the image edge, so
a texture repeats without a seam. Values are float32 in [0, 1] unless said otherwise.
"""

from __future__ import annotations

import hashlib

import numpy as np

F = np.float32
U32 = np.uint32


def seed_of(*parts) -> int:
    """A 32-bit seed from names (blake2b, the same everywhere)."""
    h = hashlib.blake2b("|".join(str(p) for p in parts).encode("utf-8"), digest_size=4)
    return int.from_bytes(h.digest(), "little")


def hash2(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    """uint32 hash of integer lattice coordinates (a murmur-style finalizer)."""
    x = ix.astype(U32)
    y = iy.astype(U32)
    h = (x * U32(0x8DA6B343)) ^ (y * U32(0xD8163841)) ^ U32(seed & 0xFFFFFFFF)
    h ^= h >> U32(16)
    h *= U32(0x7FEB352D)
    h ^= h >> U32(15)
    h *= U32(0x846CA68B)
    h ^= h >> U32(16)
    return h


def unit(h: np.ndarray) -> np.ndarray:
    """uint32 to [0, 1) float32 (top 24 bits, exact)."""
    return ((h >> U32(8)).astype(F) * F(1.0 / 16777216.0)).astype(F)


def grid(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Pixel centers of an n x n image in [0, 1): (x, y), rows from the top."""
    c = ((np.arange(n, dtype=F) + F(0.5)) / F(n)).astype(F)
    return np.broadcast_to(c[None, :], (n, n)), np.broadcast_to(c[:, None], (n, n))


def white(n: int, seed: int) -> np.ndarray:
    iy, ix = np.mgrid[0:n, 0:n]
    return unit(hash2(ix, iy, seed))


def _fade(t: np.ndarray) -> np.ndarray:
    return t * t * (F(3.0) - F(2.0) * t)


def value(n: int, period: int, seed: int, px: np.ndarray | None = None,
          py: np.ndarray | None = None) -> np.ndarray:
    """Value noise with `period` cells across the image (tileable), smooth (cubic fade).
    `px`, `py` (in [0, 1), image units) warp the sample positions."""
    if px is None:
        px, py = grid(n)
    fx = (px * F(period)).astype(F)
    fy = (py * F(period)).astype(F)
    x0 = np.floor(fx)
    y0 = np.floor(fy)
    tx = _fade((fx - x0).astype(F))
    ty = _fade((fy - y0).astype(F))
    ix = x0.astype(np.int64) % period
    iy = y0.astype(np.int64) % period
    jx = (ix + 1) % period
    jy = (iy + 1) % period
    lat_y, lat_x = np.mgrid[0:period, 0:period]
    L = unit(hash2(lat_x, lat_y, seed))
    a = L[iy, ix]
    b = L[iy, jx]
    c = L[jy, ix]
    d = L[jy, jx]
    top = a + (b - a) * tx
    bot = c + (d - c) * tx
    return (top + (bot - top) * ty).astype(F)


def fbm(n: int, period: int, seed: int, octaves: int = 5, gain: float = 0.5,
        px: np.ndarray | None = None, py: np.ndarray | None = None) -> np.ndarray:
    """Fractal sum of value noise, period doubling per octave, normalized to [0, 1]."""
    out = np.zeros((n, n), dtype=F)
    amp = 1.0
    total = 0.0
    p = period
    for k in range(octaves):
        if p > n:
            break
        out = out + F(amp) * value(n, p, seed + 101 * k, px, py)
        total += amp
        amp *= gain
        p *= 2
    return (out / F(total)).astype(F)


def ridged(n: int, period: int, seed: int, octaves: int = 4) -> np.ndarray:
    """1 - |2 v - 1| summed: thin bright ridges (cracks, veins)."""
    out = np.zeros((n, n), dtype=F)
    amp, total, p = 1.0, 0.0, period
    for k in range(octaves):
        if p > n:
            break
        v = value(n, p, seed + 211 * k)
        r = F(1.0) - np.abs(F(2.0) * v - F(1.0))
        out = out + F(amp) * r * r
        total += amp
        amp *= 0.5
        p *= 2
    return (out / F(total)).astype(F)


def cells(n: int, period: int, seed: int, jitter: float = 0.8,
          second: bool = False) -> tuple[np.ndarray, ...]:
    """Worley noise: distance to the nearest feature point (in cell units) and a uniform id
    of its cell, over a `period` x `period` tileable grid; with `second`, also the distance
    to the second nearest (F2 - F1 is the distance to the cell's edge, about)."""
    px, py = grid(n)
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
            h1 = hash2(wx, wy, seed)
            h2 = hash2(wx, wy, seed + 7)
            jx = F(0.5) + F(jitter) * (unit(h1) - F(0.5))
            jy = F(0.5) + F(jitter) * (unit(h2) - F(0.5))
            dx = cx.astype(F) + jx - fx
            dy = cy.astype(F) + jy - fy
            d = np.sqrt(dx * dx + dy * dy).astype(F)
            closer = d < best
            best2 = np.where(closer, best, np.minimum(best2, d))
            best = np.where(closer, d, best)
            bid = np.where(closer, unit(hash2(wx, wy, seed + 13)), bid)
    if second:
        return best.astype(F), bid.astype(F), best2.astype(F)
    return best.astype(F), bid.astype(F)


def warp(n: int, period: int, seed: int, amount: float) -> tuple[np.ndarray, np.ndarray]:
    """Sample positions pushed by two value noises (domain warping), wrapped to [0, 1)."""
    px, py = grid(n)
    wx = fbm(n, period, seed, 3) - F(0.5)
    wy = fbm(n, period, seed + 1, 3) - F(0.5)
    qx = px + F(amount) * wx
    qy = py + F(amount) * wy
    return (qx - np.floor(qx)).astype(F), (qy - np.floor(qy)).astype(F)


def smooth(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - F(e0)) / F(e1 - e0), F(0.0), F(1.0)).astype(F)
    return _fade(t)


def blur(a: np.ndarray, r: int) -> np.ndarray:
    """Box blur of radius r with wrap-around, as integer-order float sums of shifted
    copies (the same order everywhere)."""
    if r <= 0:
        return a
    out = a
    for axis in (0, 1):
        acc = np.zeros_like(out)
        for k in range(-r, r + 1):
            acc = acc + np.roll(out, k, axis=axis)
        out = (acc / F(2 * r + 1)).astype(F)
    return out


def lerp(a, b, t):
    return a + (b - a) * t
