"""Contact-sheet thumbnails and their perceptual hash (scope 5.1.1: the second half of the
uniqueness check).

Each building is drawn as the contact sheet draws it (`front_dir`: looking at its main
front, turned 30 degrees to show a corner, 35 degrees down; orthographic, framed on what it
draws) at `SIZE` x `SIZE` pixels by a small z-buffered rasterizer: every shell triangle
facing the view and the box of every instanced part that stands out of the wall
(balconies, fins, members, pods, screens, shutters, canopies: frames and caps sit in the
openings), flat shaded from the slot's color (the building's tint where the slot takes
one) and a fixed sun. The hash compares the image's `GRID` x `GRID` block sums with their
right and lower neighbors (a difference hash, 480 bits) and codes each block's mean shade
in four steps (1,024 bits: the tone a difference hash drops); two thumbnails are told
apart by the number of bits that differ. How much of the thumbnail a building fills is kept beside
it: a sliver (a shed 300 m long and 4 m wide) draws as a line in any contact sheet.

Everything is IEEE element-wise arithmetic in a fixed order and integer sums (scope section
10): the same bits on every machine.
"""

from __future__ import annotations

import math

import numpy as np

from citygen import dmath as M

from . import parts as PT
from . import systems as SY

SIZE = 64
GRID = 16
TONES = (48, 96, 144, 192)      # a block's mean shade (0 to 255) at or over each: one bit
BITS = 2 * GRID * (GRID - 1) + len(TONES) * GRID * GRID
BG = 0.16                       # the background's shade (linear)
SUN = (0.42, -0.58, 0.70)       # toward the sun
# instanced families drawn as boxes (the rest sit in their openings)
DRAWN = ("balcony", "fin", "shade", "panel", "member", "pod", "ac", "dish", "column",
         "canopy", "shutter", "balconette", "mast")


def _norm(v):
    L = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / L, v[1] / L, v[2] / L)


def front_dir(brief: dict) -> tuple[float, float, float]:
    """A view direction onto a building's main front (its longest `front` edge, else its
    longest window-bearing one), turned 30 degrees to show a corner, 35 degrees down."""
    best = None
    for e in brief["edges"]:
        rank = 0 if e["class"] == "front" else (1 if e["class"] in ("street", "plaza", "park",
                                                                    "canal", "open") else 2)
        key = (rank, -e["length_m"])
        if e["ring"] == 0 and (best is None or key < best[0]):
            best = (key, e["normal_deg"])
    if best is None:
        return _norm((0.280167, 0.769751, -0.573576))
    a = float(M.radians(best[1] + 30.0))
    c = float(M.cos(M.radians(35.0)))
    return _norm((-float(M.cos(a)) * c, -float(M.sin(a)) * c,
                  -float(M.sin(M.radians(35.0)))))


def _lum(rgb) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def slot_shade(slot: str, tints: dict) -> float:
    """The linear luminance a slot draws with (its tint where it takes one, as the preview
    materials do)."""
    master, hex_c, rough, metal, tint = SY.SLOTS[slot]
    base = SY.srgb_linear(hex_c)
    if tint == "patch":
        t = tints.get("patch", base)
        return min(_lum([3.1 * t[k] * base[k] for k in range(3)]), 1.0)
    if tint and tint in tints:
        return _lum(tints[tint])
    return _lum(base)


_BOX = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                 [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]],
                dtype=np.int64)


def _boxes(inst: list[dict], tints: dict):
    """(p0, p1, p2, shade) of the boxes of the drawn instanced parts at every placement."""
    out = []
    for x in inst:
        if x["family"] not in DRAWN:
            continue
        _, arrs = PT.mesh(x["family"], x["params"])
        lo, hi = PT.bounds(arrs)
        sh = slot_shade(sorted(arrs, key=lambda k: (-len(arrs[k]["tri"]), k))[0], tints)
        cx = np.array([lo[0], hi[0]] * 4, dtype=np.float64)
        cy = np.array([lo[1], lo[1], hi[1], hi[1]] * 2, dtype=np.float64)
        cz = np.array([lo[2]] * 4 + [hi[2]] * 4, dtype=np.float64)
        at = np.array([a[:3] for a in x["at"]], dtype=np.float64)
        rot = np.array([a[3:] for a in x["at"]], dtype=np.float64)
        ux, uy = rot[:, 0:1], rot[:, 1:2]
        px = (cx[None, :] * ux - cy[None, :] * uy) + at[:, 0:1]
        py = (cx[None, :] * uy + cy[None, :] * ux) + at[:, 1:2]
        pz = cz[None, :] + at[:, 2:3]
        P = np.stack([px, py, pz], axis=2)               # (k, 8, 3)
        tri = P[:, _BOX, :]                                # (k, 12, 3, 3)
        tri = tri.reshape(-1, 3, 3)
        out.append((tri[:, 0], tri[:, 1], tri[:, 2], np.full(len(tri), sh)))
    return out


def render(brief: dict, arrs: dict, inst: list[dict], tints: dict) -> np.ndarray:
    """The building's thumbnail: SIZE x SIZE shades 0 to 255 (uint8)."""
    d = front_dir(brief)
    side = _norm((d[1], -d[0], 0.0))                      # d x z
    up = (side[1] * d[2] - side[2] * d[1], side[2] * d[0] - side[0] * d[2],
          side[0] * d[1] - side[1] * d[0])
    sun = _norm(SUN)
    groups = []
    for name in sorted(arrs):
        a = arrs[name]
        pos = a["pos"].astype(np.float64)
        t = a["tri"]
        groups.append((pos[t[:, 0]], pos[t[:, 1]], pos[t[:, 2]],
                       np.full(len(t), slot_shade(name, tints))))
    groups += _boxes(inst, tints)
    if not groups:
        return np.full((SIZE, SIZE), int(np.minimum(np.sqrt(np.float64(BG)) * 255.0 + 0.5,
                                                    255.0)), dtype=np.uint8)
    p0 = np.concatenate([g[0] for g in groups])
    p1 = np.concatenate([g[1] for g in groups])
    p2 = np.concatenate([g[2] for g in groups])
    base = np.concatenate([g[3] for g in groups])
    e1, e2 = p1 - p0, p2 - p0
    nx = e1[:, 1] * e2[:, 2] - e1[:, 2] * e2[:, 1]
    ny = e1[:, 2] * e2[:, 0] - e1[:, 0] * e2[:, 2]
    nz = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    nl = np.sqrt((nx * nx + ny * ny) + nz * nz)
    facing = ((nx * d[0] + ny * d[1]) + nz * d[2]) < 0.0
    keep = facing & (nl > 0.0)
    p0, p1, p2, base = p0[keep], p1[keep], p2[keep], base[keep]
    nx, ny, nz, nl = nx[keep] / nl[keep], ny[keep] / nl[keep], nz[keep] / nl[keep], None
    lam = np.maximum((nx * sun[0] + ny * sun[1]) + nz * sun[2], 0.0)
    shade = base * (0.35 + 0.65 * lam)

    def uv(p):
        return ((p[:, 0] * side[0] + p[:, 1] * side[1]) + p[:, 2] * side[2],
                (p[:, 0] * up[0] + p[:, 1] * up[1]) + p[:, 2] * up[2],
                (p[:, 0] * d[0] + p[:, 1] * d[1]) + p[:, 2] * d[2])
    u0, v0, w0 = uv(p0)
    u1, v1, w1 = uv(p1)
    u2, v2, w2 = uv(p2)
    if not len(u0):
        return np.full((SIZE, SIZE), int(np.minimum(np.sqrt(np.float64(BG)) * 255.0 + 0.5,
                                                    255.0)), dtype=np.uint8)
    umin = min(u0.min(), u1.min(), u2.min())
    umax = max(u0.max(), u1.max(), u2.max())
    vmin = min(v0.min(), v1.min(), v2.min())
    vmax = max(v0.max(), v1.max(), v2.max())
    span = max(umax - umin, vmax - vmin, 1.0) / (SIZE * 0.92)
    cu, cv = (umin + umax) / 2.0, (vmin + vmax) / 2.0
    half = SIZE / 2.0

    def px(u, v):
        return (u - cu) / span + half, (cv - v) / span + half
    x0, y0 = px(u0, v0)
    x1, y1 = px(u1, v1)
    x2, y2 = px(u2, v2)
    depth = ((w0 + w1) + w2) / 3.0
    area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    sgn = np.where(area < 0.0, -1.0, 1.0)
    bx0 = np.maximum(np.ceil(np.minimum(np.minimum(x0, x1), x2) - 0.5), 0).astype(np.int64)
    bx1 = np.minimum(np.floor(np.maximum(np.maximum(x0, x1), x2) - 0.5), SIZE - 1).astype(np.int64)
    by0 = np.maximum(np.ceil(np.minimum(np.minimum(y0, y1), y2) - 0.5), 0).astype(np.int64)
    by1 = np.minimum(np.floor(np.maximum(np.maximum(y0, y1), y2) - 0.5), SIZE - 1).astype(np.int64)
    ext = np.maximum(bx1 - bx0, by1 - by0) + 1
    live = (bx1 >= bx0) & (by1 >= by0) & (area != 0.0)
    pix_l, dep_l, tid_l, sh_l = [], [], [], []
    tid = np.arange(len(x0), dtype=np.int64)
    lo_k = 0
    for K in (1, 2, 4, 8, 16, 32, SIZE):
        sel = live & (ext > lo_k) & (ext <= K)
        lo_k = K
        if not sel.any():
            continue
        oy, ox = np.divmod(np.arange(K * K, dtype=np.int64), K)
        cx = bx0[sel][:, None] + ox[None, :]
        cy = by0[sel][:, None] + oy[None, :]
        ok = (cx <= bx1[sel][:, None]) & (cy <= by1[sel][:, None])
        fx, fy = cx + 0.5, cy + 0.5
        X0, Y0 = x0[sel][:, None], y0[sel][:, None]
        X1, Y1 = x1[sel][:, None], y1[sel][:, None]
        X2, Y2 = x2[sel][:, None], y2[sel][:, None]
        s = sgn[sel][:, None]
        e0 = ((X1 - X0) * (fy - Y0) - (Y1 - Y0) * (fx - X0)) * s
        e1_ = ((X2 - X1) * (fy - Y1) - (Y2 - Y1) * (fx - X1)) * s
        e2_ = ((X0 - X2) * (fy - Y2) - (Y0 - Y2) * (fx - X2)) * s
        ok &= (e0 >= 0.0) & (e1_ >= 0.0) & (e2_ >= 0.0)
        r, c = np.nonzero(ok)
        pix_l.append(cy[r, c] * SIZE + cx[r, c])
        dep_l.append(depth[sel][r])
        tid_l.append(tid[sel][r])
        sh_l.append(shade[sel][r])
    img = np.full(SIZE * SIZE, BG)
    if pix_l:
        pix = np.concatenate(pix_l)
        dep = np.concatenate(dep_l)
        tids = np.concatenate(tid_l)
        shs = np.concatenate(sh_l)
        order = np.lexsort((tids, dep, pix))
        ps = pix[order]
        first = np.ones(len(ps), dtype=bool)
        first[1:] = ps[1:] != ps[:-1]
        img[ps[first]] = shs[order][first]
    img = np.minimum(np.sqrt(np.minimum(img, 1.0)) * 255.0 + 0.5, 255.0)
    return img.astype(np.uint8).reshape(SIZE, SIZE)


def dhash(img: np.ndarray) -> str:
    """The hash of a thumbnail, hex: over GRID x GRID blocks, each block's sum compared with
    its right and lower neighbors (a difference hash: the drawing's structure), then each
    block's mean shade as a thermometer code over `TONES` (its tone, which a difference
    hash drops: a white roof and a grey one of the same shed differ only there)."""
    b = SIZE // GRID
    g = img.astype(np.int64).reshape(GRID, b, GRID, b).sum(axis=(1, 3))
    tone = (g // (b * b))[:, :, None] >= np.array(TONES, dtype=np.int64)[None, None, :]
    bits = np.concatenate([(g[:, :-1] > g[:, 1:]).reshape(-1), (g[:-1, :] > g[1:, :]).reshape(-1),
                           tone.reshape(-1)])
    return np.packbits(bits).tobytes().hex()


def hash_of(brief: dict, arrs: dict, inst: list[dict], tints: dict) -> tuple[str, float]:
    """(difference hash, the share of the thumbnail the building fills)."""
    img = render(brief, arrs, inst, tints)
    bg = int(np.minimum(np.sqrt(np.float64(BG)) * 255.0 + 0.5, 255.0))
    fill = round(int((img != bg).sum()) / float(SIZE * SIZE), 3)
    return dhash(img), fill


def distances(hashes: list[str]) -> np.ndarray:
    """The hashes as rows of bytes, for Hamming distances (`np.bitwise_count` of XORs)."""
    return np.array([np.frombuffer(bytes.fromhex(h), dtype=np.uint8) for h in hashes],
                    dtype=np.uint8).reshape(len(hashes), -1)
