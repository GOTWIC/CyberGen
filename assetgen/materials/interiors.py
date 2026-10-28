"""Window interior atlases (scope 5.2, decision 13.6: interior mapping only): per use
(office, apartment, capsule, shop, club, warehouse) eight rooms, each drawn by day and lit by
night, as one-point perspective images that the glass masters reproject.

A room is the box x, y in [0, 1] (across, up) and z in [0, 1] (into the building; the window
is z = 0). Its image is what a camera on the window's axis sees through the window, the
back wall drawn at `BACK` of the window's size: a room point (x, y, z) lands on the image
at

$$(u, v) = \\tfrac12 + (x - \\tfrac12,\\ y - \\tfrac12)\\, \\frac{s}{s + (1 - s) z}$$

with $s$ = `BACK`. The masters (Unreal `M_CgGlass`, Blender's glass) find the point a view
ray through a window hits in its room (rooms are cells of the building's own grid: the bay
width by the floor height, from UV0 in meters, so no per-pane data is needed) and look it
up with the same formula. Furniture is drawn into the image as seen from the window's axis,
so from other angles it slides along the walls, as in every image-based interior.

Atlas layout: column = variant (8), row = use (6, `USES`), row 0 at the top; in a cell, the
room's ceiling is at the top. Pure numpy (ray-box arithmetic) and integer hashes.
"""

from __future__ import annotations

import numpy as np

from . import noise as N

F = np.float32
USES = ("office", "apartment", "capsule", "shop", "club", "warehouse")
VARIANTS = 8
BACK = 0.5
K = (1.0 - BACK) / BACK
DIMS = (3.6, 3.0, 4.0)     # meters the room is drawn as (width, height, depth)


def _ray(cell: int):
    """Per pixel: u, v (0..1, v up) and the ray x(z), y(z) = a + b z."""
    c = ((np.arange(cell, dtype=F) + F(0.5)) / F(cell)).astype(F)
    u = np.broadcast_to(c[None, :], (cell, cell))
    v = np.broadcast_to(c[::-1][:, None], (cell, cell))      # row 0 at the top: v = 1
    ax = (u).astype(F)
    bx = ((u - F(0.5)) * F(K)).astype(F)
    ay = (v).astype(F)
    by = ((v - F(0.5)) * F(K)).astype(F)
    return u, v, ax, bx, ay, by


def _walls(u, v, bx, by):
    """z of the first wall hit and which: 0 back, 1 left, 2 right, 3 floor, 4 ceiling."""
    big = F(1e9)
    dx = np.abs(u - F(0.5))
    dy = np.abs(v - F(0.5))
    zx = np.where(dx > F(1e-6), (F(0.5) / np.maximum(dx, F(1e-6)) - F(1.0)) / F(K), big)
    zy = np.where(dy > F(1e-6), (F(0.5) / np.maximum(dy, F(1e-6)) - F(1.0)) / F(K), big)
    z = np.minimum(np.minimum(zx, zy), F(1.0)).astype(F)
    which = np.where(z >= F(1.0), 0,
                     np.where(zx <= zy, np.where(u < F(0.5), 1, 2),
                              np.where(v < F(0.5), 3, 4)))
    return z, which


def _box(ax, bx, ay, by, box):
    """Entry z and face (0 front, 1 side, 2 top or bottom) of the ray into an axis box
    (x0, x1, y0, y1, z0, z1); z = 9 where it misses."""
    x0, x1, y0, y1, z0, z1 = box
    inf = F(1e9)

    def slab(a, b, lo, hi):
        safe = np.where(np.abs(b) > F(1e-7), b, F(1e-7))
        t1 = (F(lo) - a) / safe
        t2 = (F(hi) - a) / safe
        tmin = np.minimum(t1, t2)
        tmax = np.maximum(t1, t2)
        inside = (a >= F(lo)) & (a <= F(hi))
        tmin = np.where(np.abs(b) > F(1e-7), tmin, np.where(inside, -inf, inf))
        tmax = np.where(np.abs(b) > F(1e-7), tmax, np.where(inside, inf, -inf))
        return tmin, tmax
    xmin, xmax = slab(ax, bx, x0, x1)
    ymin, ymax = slab(ay, by, y0, y1)
    enter = np.maximum(np.maximum(xmin, ymin), F(z0))
    exit_ = np.minimum(np.minimum(xmax, ymax), F(z1))
    hit = (enter <= exit_) & (exit_ >= F(0.0))
    face = np.where(enter == F(z0), 0, np.where(enter == xmin, 1, 2))
    return np.where(hit, enter, F(9.0)).astype(F), face


def _c(hexc: str) -> np.ndarray:
    return np.array([int(hexc[1 + 2 * k:3 + 2 * k], 16) / 255.0 for k in range(3)], dtype=F)


# per use: wall colors, floor kind and colors, ceiling, day and night light, boxes
LOOK = {
    "office": {"walls": ("#d8d6d0", "#c9ccd0", "#d2cfc4", "#b9c2c8"), "floor": "carpet",
               "floor_c": ("#5d6266", "#6a645c", "#4f5660"), "ceil": "#e4e4e0",
               "light": "#e8f0ff", "lamp": "panels"},
    "apartment": {"walls": ("#d9cbb4", "#b8c4b0", "#a8b8c8", "#d8b8a8", "#c4b4c8"),
                  "floor": "wood", "floor_c": ("#7a5a3c", "#8c6a48", "#5e4632"),
                  "ceil": "#ece6dc", "light": "#ffd9a8", "lamp": "bulb"},
    "capsule": {"walls": ("#d8dce0", "#c8d0d4", "#e0d8d0"), "floor": "plastic",
                "floor_c": ("#9aa0a6", "#8a8f94"), "ceil": "#e8ecef", "light": "#ff4fd8",
                "lamp": "strip"},
    "shop": {"walls": ("#f0f0ec", "#e8e4dc", "#e0e8ec"), "floor": "tile",
             "floor_c": ("#c8c8c4", "#b8b4ac"), "ceil": "#f4f4f2", "light": "#f4fbff",
             "lamp": "panels"},
    "club": {"walls": ("#2a1f33", "#1f2533", "#331f26", "#1c1c22"), "floor": "dark",
             "floor_c": ("#1a1a1e", "#22191f"), "ceil": "#141418", "light": "#c040ff",
             "lamp": "neon"},
    "warehouse": {"walls": ("#8c8a84", "#7e7c76", "#94918a"), "floor": "concrete",
                  "floor_c": ("#6e6c66", "#76736c"), "ceil": "#5e5c58", "light": "#ffc070",
                  "lamp": "bulb"},
}
ACCENTS = ("#ff3fb4", "#2fe0ff", "#9d4dff", "#ff8a1f", "#39ff8f", "#ffd23f")


def _boxes(use: str, r) -> list[tuple]:
    """Furniture as (box, color, emissive at night) in room units, drawn from r()."""
    out = []
    flip = r() < 0.5

    def bx(x0, x1, y0, y1, z0, z1, col, emit=0.0):
        if flip:
            x0, x1 = 1.0 - x1, 1.0 - x0
        out.append(((x0, x1, y0, y1, z0, z1), _c(col), emit))
    if use == "office":
        for k in range(2 if r() < 0.7 else 1):
            x = 0.08 + 0.46 * k
            bx(x, x + 0.38, 0.0, 0.25, 0.42, 0.68, "#8a8278")
            bx(x + 0.1, x + 0.24, 0.25, 0.37, 0.6, 0.62, "#151a20", 1.6)
            bx(x + 0.12, x + 0.22, 0.0, 0.2, 0.25, 0.35, "#2a2d33")
        bx(0.05, 0.4, 0.0, 0.45, 0.9, 1.0, "#9a9c9e")
        if r() < 0.5:
            bx(0.6, 0.95, 0.0, 0.7, 0.92, 1.0, "#6c6458")
    elif use == "apartment":
        if r() < 0.5:
            bx(0.1, 0.62, 0.0, 0.16, 0.55, 0.95, ("#b0a090", "#7a8aa0", "#a0786a")[int(r() * 3)])
            bx(0.1, 0.62, 0.16, 0.2, 0.86, 0.95, "#e8e0d4")
        else:
            bx(0.1, 0.6, 0.0, 0.14, 0.7, 0.92, ("#5a6a7a", "#7a5a4a", "#4a5a4a")[int(r() * 3)])
            bx(0.1, 0.6, 0.14, 0.26, 0.86, 0.92, "#4a4a50")
        bx(0.72, 0.96, 0.0, 0.62, 0.9, 1.0, "#6a4e36")
        bx(0.66, 0.7, 0.0, 0.32, 0.5, 0.54, "#3a3430")
        bx(0.63, 0.73, 0.32, 0.4, 0.48, 0.56, "#f0d8a8", 3.0)
        if r() < 0.6:
            bx(0.0, 0.02, 0.3, 0.52, 0.45, 0.75, "#101418", 1.2)
    elif use == "capsule":
        bx(0.0, 1.0, 0.0, 0.3, 0.08, 1.0, "#c8ccd0")
        bx(0.0, 1.0, 0.3, 0.36, 0.25, 1.0, ("#4a6a9a", "#9a4a6a", "#5a8a6a")[int(r() * 3)])
        bx(0.15, 0.85, 0.94, 0.97, 0.3, 0.9, ACCENTS[int(r() * len(ACCENTS))], 4.0)
        bx(0.6, 0.9, 0.55, 0.8, 0.97, 1.0, "#101418", 1.5)
    elif use == "shop":
        for side in (0, 1):
            x0 = 0.0 if side == 0 else 0.84
            bx(x0, x0 + 0.16, 0.0, 0.72, 0.15, 1.0, "#8a8a8c")
            for k in range(4):
                y = 0.08 + 0.17 * k
                col = ("#d84a3a", "#3a8ad8", "#e8c040", "#4ab86a", "#e87ab0")[int(r() * 5)]
                bx(x0 + 0.01, x0 + 0.15, y, y + 0.1, 0.12, 0.98, col)
        bx(0.35, 0.75, 0.0, 0.32, 0.35, 0.5, "#5a5a60")
        bx(0.25, 0.75, 0.5, 0.75, 0.97, 1.0, ACCENTS[int(r() * len(ACCENTS))], 2.5)
    elif use == "club":
        bx(0.08, 0.92, 0.0, 0.36, 0.78, 0.9, "#2a2028")
        bx(0.08, 0.92, 0.36, 0.38, 0.78, 0.9, ACCENTS[int(r() * len(ACCENTS))], 5.0)
        bx(0.1, 0.9, 0.55, 0.85, 0.97, 1.0, "#3a2a40", 1.0)
        for k in range(3):
            x = 0.15 + 0.25 * k + 0.05 * r()
            bx(x, x + 0.05, 0.0, 0.42, 0.35 + 0.2 * r(), 0.4 + 0.2 * r(), "#18141c")
    else:
        for k in range(5):
            x = r() * 0.8
            z = 0.3 + r() * 0.65
            h = 0.15 + r() * 0.45
            bx(x, x + 0.18, 0.0, h, z, z + 0.15, ("#9a7a50", "#8a6a44", "#6a6a6a")[int(r() * 3)])
    return out


def room(use: str, variant: int, cell: int) -> tuple[np.ndarray, np.ndarray]:
    """(day, night) RGB float images (cell x cell) of one room."""
    look = LOOK[use]
    seed = N.seed_of("ag6.room", use, variant)
    state = [seed]

    def r():
        state[0] = (state[0] * 1103515245 + 12345) & 0x7FFFFFFF
        return state[0] / 2147483648.0
    u, v, ax, bx, ay, by = _ray(cell)
    z, which = _walls(u, v, bx, by)
    W, H, D = DIMS
    X = ax + bx * z
    Y = ay + by * z
    wall_c = _c(look["walls"][int(r() * len(look["walls"]))])
    floor_c = _c(look["floor_c"][int(r() * len(look["floor_c"]))])
    ceil_c = _c(look["ceil"])
    # surface coordinates in meters for patterns
    su = np.where(which == 0, X * F(W), np.where(which <= 2, z * F(D), X * F(W)))
    sv = np.where(which == 0, Y * F(H), np.where(which <= 2, Y * F(H), z * F(D)))
    col = np.empty((cell, cell, 3), dtype=F)
    for k in range(3):
        col[:, :, k] = np.where(which == 3, floor_c[k], np.where(which == 4, ceil_c[k],
                                                                  wall_c[k]))
    g = N.white(cell, seed) - F(0.5)
    shade = F(1.0) + F(0.04) * g
    if look["floor"] == "wood":
        board = np.floor(su / F(0.14))
        tone = N.unit(N.hash2(board.astype(np.int64), board.astype(np.int64) * 0, seed)) - F(0.5)
        shade = np.where(which == 3, shade + F(0.18) * tone, shade)
    elif look["floor"] == "tile":
        fx = su / F(0.4) - np.floor(su / F(0.4))
        fy = sv / F(0.4) - np.floor(sv / F(0.4))
        line = (np.minimum(fx, F(1.0) - fx) < F(0.03)) | (np.minimum(fy, F(1.0) - fy) < F(0.03))
        shade = np.where((which == 3) & line, shade * F(0.8), shade)
    # back wall art: a poster or a window band, a door
    if use in ("apartment", "office", "club", "capsule"):
        px0 = 0.2 + 0.3 * r()
        art = (which == 0) & (X > F(px0)) & (X < F(px0 + 0.2)) & (Y > F(0.45)) & (Y < F(0.7))
        ac = _c(ACCENTS[int(r() * len(ACCENTS))]) * F(0.7)
        for k in range(3):
            col[:, :, k] = np.where(art, ac[k], col[:, :, k])
    if use in ("office", "warehouse", "shop"):
        door = (which == 0) & (X > F(0.78)) & (X < F(0.95)) & (Y < F(0.72))
        shade = np.where(door, shade * F(0.75), shade)
    # light: by day from the window (near is brighter), by night from the ceiling
    face_day = np.where(which == 3, F(1.0), np.where(which == 4, F(0.55),
                                                     np.where(which == 0, F(0.75), F(0.85))))
    day_l = (F(0.35) + F(0.65) * (F(1.0) - F(0.6) * z)) * face_day
    lx = X - F(0.5)
    ly = Y - F(1.0)
    lz = z - F(0.5)
    d2 = (lx * lx * F(W * W) + ly * ly * F(H * H) + lz * lz * F(D * D)).astype(F)
    lamp = _c(look["light"])
    night_l = F(2.4) / (F(1.0) + F(0.35) * d2)
    if look["lamp"] == "neon":
        night_l = night_l * F(0.5)
    emit = np.zeros((cell, cell, 3), dtype=F)
    # ceiling fixtures
    if look["lamp"] == "panels":
        fx = X * F(2.0) - np.floor(X * F(2.0))
        fz = z * F(2.0) - np.floor(z * F(2.0))
        panel = (which == 4) & (np.abs(fx - F(0.5)) < F(0.22)) & (np.abs(fz - F(0.5)) < F(0.12))
        for k in range(3):
            emit[:, :, k] = np.where(panel, lamp[k] * F(3.0), emit[:, :, k])
    elif look["lamp"] in ("bulb",):
        bulb = (which == 4) & ((X - F(0.5)) ** 2 + (z - F(0.5)) ** 2 < F(0.004))
        for k in range(3):
            emit[:, :, k] = np.where(bulb, lamp[k] * F(4.0), emit[:, :, k])
    elif look["lamp"] in ("strip", "neon"):
        acc = _c(ACCENTS[int(r() * len(ACCENTS))])
        strip = (which != 3) & (Y > F(0.94)) & (Y < F(0.98))
        for k in range(3):
            emit[:, :, k] = np.where(strip, acc[k] * F(3.0), emit[:, :, k])
        lamp = lamp * F(0.5) + acc * F(0.5)
    base = col * shade[:, :, None]
    # furniture over the walls
    best = np.full((cell, cell), F(9.0), dtype=F)
    for box, bc, em in _boxes(use, r):
        zt, face = _box(ax, bx, ay, by, box)
        hit = (zt < z) & (zt < best)
        fs = np.where(face == 0, F(0.85), np.where(face == 1, F(0.65), F(1.0)))
        for k in range(3):
            base[:, :, k] = np.where(hit, bc[k] * fs, base[:, :, k])
            if em > 0:
                emit[:, :, k] = np.where(hit & (face == 0), bc[k] * F(em), emit[:, :, k])
            else:
                emit[:, :, k] = np.where(hit, F(0.0), emit[:, :, k])
        best = np.where(hit, zt, best)
        zz = np.where(hit, zt, z)
        d2 = np.where(hit, ((ax + bx * zz - F(0.5)) ** 2 * F(W * W)
                            + (ay + by * zz - F(1.0)) ** 2 * F(H * H)
                            + (zz - F(0.5)) ** 2 * F(D * D)), d2).astype(F)
    zz = np.minimum(best, z)
    day_l = (F(0.35) + F(0.65) * (F(1.0) - F(0.6) * zz)) * np.where(best < z, F(0.9), face_day)
    night_l = F(2.4) / (F(1.0) + F(0.35) * d2) * (F(0.5) if look["lamp"] == "neon" else F(1.0))
    day = np.clip(base * day_l[:, :, None] * F(0.85), 0, 1)
    night = np.clip(base * night_l[:, :, None] * lamp[None, None, :] * F(0.8) + emit, 0, 1)
    # a little dimming toward the back corners (the window's own light falls off)
    vig = F(1.0) - F(0.25) * zz
    return (day * vig[:, :, None]).astype(F), (night * vig[:, :, None]).astype(F)


def atlas(cell: int) -> tuple[np.ndarray, np.ndarray]:
    """The day and night atlases: (rows x cell, VARIANTS x cell, 3) floats 0..1."""
    rows = len(USES)
    day = np.zeros((rows * cell, VARIANTS * cell, 3), dtype=F)
    night = np.zeros_like(day)
    for i, use in enumerate(USES):
        for j in range(VARIANTS):
            d, n = room(use, j, cell)
            day[i * cell:(i + 1) * cell, j * cell:(j + 1) * cell] = d
            night[i * cell:(i + 1) * cell, j * cell:(j + 1) * cell] = n
    return day, night


def use_row(use: str, btype: str = "") -> int:
    """The atlas row for a building's use (M3 `Building.use`) and type."""
    if btype in ("building.warehouse", "building.shed", "building.hangar", "building.yard"):
        return USES.index("warehouse")
    if btype == "building.shanty_stack":
        return USES.index("capsule")
    return USES.index({"office": "office", "residential": "apartment", "hotel": "apartment",
                       "retail": "shop", "civic": "office", "industrial": "warehouse",
                       "parking": "warehouse", "mixed": "apartment", "station": "office",
                       "transport": "office", "entertainment": "club",
                       "religious": "office"}.get(use, "office"))
