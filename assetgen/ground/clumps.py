"""Grass and small plant clumps (scope 14.14): a few variants per clump kind, each a small
mesh in its own frame (z up from the ground at its root, meters, then integer millimeters),
built from blades, leaves and heads drawn by a hash of (kind, variant), angles from citygen's
`dmath`, so a clump is the same on every machine.

- **lawn**: short dense blades; **clover**: trefoils on thin stems with a few white heads;
  **flowers**: stems with leaves and five or six petal heads in a district's palette (a
  family per palette: `flowers.<c0>_<c1>_<c2>`), over a tuft of blades;
- **meadow** (green over straw, seed stalks) and **meadow_dry** (straw), **reeds** (long
  narrow blades with plumes), **cattails** (sword leaves and brown heads), **weeds**
  (rosettes and a seed stalk), **fern** (arching fronds with paired pinnae);
- **scrub** and **sedum**: AG8's species (`assetgen.props.trees`) at ground cover scale,
  their foliage on the grass master.

Every vertex carries COLOR_0 for the grass master (`M_CgGrass`): R the height share of its
blade (0 at the root, 1 at the tip: the root darkening and the wind's sway weight), G a hash
per blade (tone), B dryness (toward the slot's dry color). UV0 runs across (u) and along (v)
each blade. Normals lean toward the vertical (grass lit as a canopy, not as cards). The
master is two-sided and untextured: a slot's color is its own.
"""

from __future__ import annotations

import math

import numpy as np

from citygen import dmath as M

from ..gltf import Primitive
from . import kinds as K

# slot -> (color, dry color)
SLOTS: dict[str, tuple[str, str]] = {
    "grass.lawn": ("#4f7c31", "#9a9452"), "grass.meadow": ("#6c8c38", "#b5a25e"),
    "grass.straw": ("#b3a060", "#cdbd84"), "grass.seed": ("#cbbd8a", "#d8cc9e"),
    "grass.reed": ("#6a8450", "#a89a62"), "grass.plume": ("#9a8468", "#c2ae8a"),
    "grass.cattail": ("#56371f", "#6e4a2a"), "grass.weed": ("#5b7b33", "#8f8a4a"),
    "grass.clover": ("#4d8838", "#7f9a48"), "grass.clover_flower": ("#efece2", "#e6dfc8"),
    "grass.fern": ("#3e7a2d", "#8a8a3e"), "grass.stem": ("#4c6a2b", "#857f48"),
    "grass.eye": ("#e6b622", "#d0a62a"), "grass.scrub": ("#5e6c32", "#8a7a46"),
    "grass.scrub_dry": ("#8a7a46", "#a08e5a"), "grass.sedum": ("#7a8a36", "#8f8a46"),
    "grass.sedum_red": ("#8a4a32", "#93603e"),
}
FLOWER_PREFIX = "grass.flower."
ROUGHNESS = 0.8


def u(*key) -> float:
    from ..props.styles import u as _u
    return _u("ag13", *key)


def slot_colors(slot: str) -> tuple[str, str]:
    if slot.startswith(FLOWER_PREFIX):
        c = "#" + slot[len(FLOWER_PREFIX) + 1:]
        return c, c
    return SLOTS[slot]


class Clump:
    """Triangles per slot with their own vertices (position m, normal, color, uv)."""

    def __init__(self):
        self.slots: dict[str, dict[str, list]] = {}

    def _s(self, slot):
        s = self.slots.get(slot)
        if s is None:
            s = self.slots[slot] = {"pos": [], "nrm": [], "col": [], "uv": [], "idx": []}
        return s

    def strip(self, slot, rows, tip, tone, dry, up_lean=0.65):
        """A blade or leaf: rows [(left, right, t), ...] from the root up, then a tip point
        (t = 1); two triangles per row pair, one to the tip."""
        s = self._s(slot)
        b = len(s["pos"])
        pts = []
        for lft, rgt, t in rows:
            pts += [(lft, t, 0.0), (rgt, t, 1.0)]
        pts.append((tip, 1.0, 0.5))
        # one normal per blade: its face normal (mid row to tip) leaned toward the vertical
        lft, rgt, _ = rows[len(rows) // 2]
        e1 = (rgt[0] - lft[0], rgt[1] - lft[1], rgt[2] - lft[2])
        mid = ((lft[0] + rgt[0]) / 2.0, (lft[1] + rgt[1]) / 2.0, (lft[2] + rgt[2]) / 2.0)
        e2 = (tip[0] - mid[0], tip[1] - mid[1], tip[2] - mid[2])
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2],
             e1[0] * e2[1] - e1[1] * e2[0])
        L = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
        n = (n[0] / L, n[1] / L, n[2] / L)
        if n[2] < 0.0:
            n = (-n[0], -n[1], -n[2])
        n = (n[0] * (1.0 - up_lean), n[1] * (1.0 - up_lean), n[2] * (1.0 - up_lean) + up_lean)
        L = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        n = (n[0] / L, n[1] / L, n[2] / L)
        for p, t, side in pts:
            s["pos"].append(p)
            s["nrm"].append(n)
            s["col"].append((int(round(255 * min(max(p[2] / max(tip[2], 1e-3), 0.0), 1.0))),
                             int(tone * 255), int(dry * 255), 255))
            s["uv"].append((side, t))
        k = len(rows)
        for i in range(k - 1):
            a, bb, c, d = b + 2 * i, b + 2 * i + 1, b + 2 * i + 3, b + 2 * i + 2
            s["idx"] += [a, bb, c, a, c, d]
        s["idx"] += [b + 2 * (k - 1), b + 2 * (k - 1) + 1, b + 2 * k]

    def fan(self, slot, center, ring_pts, tone, dry, h_share=1.0, up=(0.0, 0.0, 1.0)):
        """A flat fan (a petal head, a leaflet) round its center, facing `up`."""
        s = self._s(slot)
        b = len(s["pos"])
        c8 = (int(round(255 * h_share)), int(tone * 255), int(dry * 255), 255)
        for p in [center] + list(ring_pts):
            s["pos"].append(p)
            s["nrm"].append(up)
            s["col"].append(c8)
            s["uv"].append((0.5, 1.0))
        n = len(ring_pts)
        for i in range(n):
            s["idx"] += [b, b + 1 + i, b + 1 + (i + 1) % n]

    @property
    def triangles(self) -> int:
        return sum(len(s["idx"]) // 3 for s in self.slots.values())

    def primitives(self, materials: dict[str, int]) -> list[Primitive]:
        out = []
        for name in sorted(self.slots):
            s = self.slots[name]
            pos = np.array([[int(round(c * 1000.0)) for c in p] for p in s["pos"]],
                           dtype=np.int64)
            idx = np.array(s["idx"], dtype=np.int64).reshape(-1, 3)
            # (triangles the millimeter grid flattens to a line are dropped)
            a, b, c = pos[idx[:, 0]], pos[idx[:, 1]], pos[idx[:, 2]]
            cr = np.cross(b - a, c - a)
            idx = idx[(cr != 0).any(axis=1)]
            if not len(idx):
                continue
            out.append(Primitive(material=materials[name], positions=pos,
                                 indices=idx.reshape(-1),
                                 normals=np.array(s["nrm"], dtype=np.float64),
                                 uv0=np.array(s["uv"], dtype=np.float64),
                                 colors=np.array(s["col"], dtype=np.uint8)))
        return out

    def bounds(self):
        pts = [p for s in self.slots.values() for p in s["pos"]]
        if not pts:
            return None
        return ([round(min(p[k] for p in pts), 3) for k in range(3)],
                [round(max(p[k] for p in pts), 3) for k in range(3)])


# ---------------------------------------------------------------------------------------
# blades, leaves, heads
# ---------------------------------------------------------------------------------------

def _dir(a: float) -> tuple[float, float]:
    return M.cos(a), M.sin(a)


def blade(c: Clump, slot, x, y, h, w, a, lean, key, segs=3, dry=0.0, z0=0.0):
    """A tapering blade from (x, y, z0) up h, its flat side facing along angle a, bending
    `lean` meters that way at the tip (a quadratic arc)."""
    dx, dy = _dir(a)
    sx, sy = -dy, dx
    rows = []
    for i in range(segs):
        t = i / segs
        cx = x + dx * lean * t * t
        cy = y + dy * lean * t * t
        z = z0 + h * t * (1.0 - 0.25 * (lean / max(h, 1e-3)) * t)
        ww = w * (1.0 - t) ** 0.7 / 2.0
        rows.append(((cx - sx * ww, cy - sy * ww, z), (cx + sx * ww, cy + sy * ww, z), t))
    tip = (x + dx * lean, y + dy * lean, z0 + h * (1.0 - 0.25 * lean / max(h, 1e-3)))
    c.strip(slot, rows, tip, u(*key, "tone"), dry)
    return tip


def leaf(c: Clump, slot, base, a, length, width, rise, key, dry=0.0, droop=0.0):
    """A lanceolate leaf from `base` along angle a: widest at 40 %, rising `rise` m at its
    middle and drooping `droop` at its tip."""
    dx, dy = _dir(a)
    sx, sy = -dy, dx
    x, y, z = base
    rows = []
    for t, wf in ((0.0, 0.15), (0.4, 1.0), (0.75, 0.6)):
        cx, cy = x + dx * length * t, y + dy * length * t
        cz = z + rise * math.sin(math.pi * t) - droop * t * t
        ww = width * wf / 2.0
        rows.append(((cx - sx * ww, cy - sy * ww, cz), (cx + sx * ww, cy + sy * ww, cz), t))
    tip = (x + dx * length, y + dy * length, z + rise * 0.0 - droop)
    c.strip(slot, rows, tip, u(*key, "tone"), dry, up_lean=0.5)


def head(c: Clump, slot, center, r, n, key, tilt=0.15, phase=0.0):
    """A flower head: n petals round its center, tilted a little."""
    a0 = 2.0 * M.PI * u(*key, "ta")
    tx, ty = _dir(a0)
    pts = []
    for i in range(2 * n):
        a = 2.0 * M.PI * i / (2 * n) + phase
        rr = r if i % 2 == 0 else r * 0.45
        px, py = center[0] + rr * M.cos(a), center[1] + rr * M.sin(a)
        dz = tilt * ((px - center[0]) * tx + (py - center[1]) * ty)
        pts.append((px, py, center[2] + dz))
    up = (-tilt * tx, -tilt * ty, 1.0)
    L = math.sqrt(up[0] ** 2 + up[1] ** 2 + 1.0)
    c.fan(slot, center, pts, u(*key, "tone"), 0.0, 1.0, (up[0] / L, up[1] / L, up[2] / L))


def _disc(key, r):
    a = 2.0 * M.PI * u(*key, "a")
    rr = r * math.sqrt(u(*key, "r"))
    return rr * M.cos(a), rr * M.sin(a)


# ---------------------------------------------------------------------------------------
# the kinds
# ---------------------------------------------------------------------------------------

def lawn(c: Clump, k: int) -> None:
    r, h = K.CLUMPS["lawn"][1], K.CLUMPS["lawn"][2]
    n = 32 + int(10 * u("lawn", k, "n"))
    for i in range(n):
        key = ("lawn", k, i)
        x, y = _disc(key, r)
        hh = h * (0.6 + 0.6 * u(*key, "h"))
        dry = 1.0 if u(*key, "d") < 0.12 else 0.0
        blade(c, "grass.lawn", x, y, hh, 0.0055 + 0.0025 * u(*key, "w"),
              2.0 * M.PI * u(*key, "l"), hh * (0.15 + 0.3 * u(*key, "b")), key, 2, dry)


def clover(c: Clump, k: int) -> None:
    r = K.CLUMPS["clover"][1]
    for i in range(8):
        key = ("clover", k, i)
        x, y = _disc(key, r)
        h = 0.04 + 0.05 * u(*key, "h")
        blade(c, "grass.stem", x, y, h, 0.0025, 2.0 * M.PI * u(*key, "a"), 0.01, key, 1)
        a0 = 2.0 * M.PI * u(*key, "r")
        for j in range(3):
            a = a0 + 2.0 * M.PI * j / 3
            dx, dy = _dir(a)
            lr = 0.009 + 0.004 * u(*key, "s")
            leaf(c, "grass.clover", (x, y, h), a, lr * 1.6, lr * 1.5, 0.002, (*key, j))
    for i in range(1 + int(2 * u("clover", k, "f"))):
        key = ("clover", k, "f", i)
        x, y = _disc(key, r * 0.8)
        h = 0.07 + 0.04 * u(*key, "h")
        blade(c, "grass.stem", x, y, h, 0.002, 2.0 * M.PI * u(*key, "a"), 0.01, key, 1)
        head(c, "grass.clover_flower", (x, y, h), 0.009, 6, key, 0.0)


def flowers(c: Clump, k: int, colors: list[str]) -> None:
    r = K.CLUMPS["flowers"][1]
    for i in range(10):
        key = ("flowers", k, "t", i)
        x, y = _disc(key, r)
        hh = 0.06 + 0.06 * u(*key, "h")
        blade(c, "grass.lawn", x, y, hh, 0.005, 2.0 * M.PI * u(*key, "l"), 0.02, key, 2)
    n = 4 + int(3 * u("flowers", k, "n"))
    for i in range(n):
        key = ("flowers", k, i)
        x, y = _disc(key, r * 0.8)
        h = K.CLUMPS["flowers"][2] * (0.55 + 0.6 * u(*key, "h"))
        a = 2.0 * M.PI * u(*key, "a")
        tip = blade(c, "grass.stem", x, y, h, 0.004, a, h * 0.12, key, 2)
        for j in range(2):
            leaf(c, "grass.stem", (x, y, h * (0.15 + 0.2 * j)), a + M.PI * (j + 0.3),
                 0.05, 0.016, 0.01, (*key, "lf", j), droop=0.01)
        col = colors[(k + i) % len(colors)] if u(*key, "c") < 0.75 else colors[k % len(colors)]
        petals = 5 + int(2 * u(*key, "p"))
        hr = 0.016 + 0.012 * u(*key, "hr")
        head(c, FLOWER_PREFIX + "c" + col.lstrip("#"), tip, hr, petals, key)
        head(c, "grass.eye", (tip[0], tip[1], tip[2] + 0.002), hr * 0.3, 4, (*key, "e"), 0.0)


def meadow(c: Clump, k: int, dry_share: float, kind: str = "meadow") -> None:
    r, h = K.CLUMPS[kind][1], K.CLUMPS[kind][2]
    n = 40 + int(12 * u(kind, k, "n"))
    for i in range(n):
        key = (kind, k, i)
        x, y = _disc(key, r)
        hh = h * (0.45 + 0.75 * u(*key, "h"))
        straw = u(*key, "d") < dry_share
        blade(c, "grass.straw" if straw else "grass.meadow", x, y, hh,
              0.007 + 0.004 * u(*key, "w"), 2.0 * M.PI * u(*key, "l"),
              hh * (0.25 + 0.45 * u(*key, "b")), key, 3, 0.4 if straw else 0.1 * u(*key, "dd"))
    for i in range(3 + int(3 * u(kind, k, "s"))):
        key = (kind, k, "s", i)
        x, y = _disc(key, r * 0.6)
        hh = h * (1.0 + 0.3 * u(*key, "h"))
        a = 2.0 * M.PI * u(*key, "a")
        tip = blade(c, "grass.straw", x, y, hh, 0.003, a, hh * 0.2, key, 3, 0.5)
        dx, dy = _dir(a)
        leaf(c, "grass.seed", (tip[0] - dx * 0.05, tip[1] - dy * 0.05, tip[2] - 0.06), a,
             0.08, 0.014, 0.03, (*key, "sd"))


def reeds(c: Clump, k: int) -> None:
    r, h = K.CLUMPS["reeds"][1], K.CLUMPS["reeds"][2]
    for i in range(12 + int(5 * u("reeds", k, "n"))):
        key = ("reeds", k, i)
        x, y = _disc(key, r)
        hh = h * (0.55 + 0.6 * u(*key, "h"))
        blade(c, "grass.reed", x, y, hh, 0.009 + 0.004 * u(*key, "w"),
              2.0 * M.PI * u(*key, "l"), hh * (0.12 + 0.22 * u(*key, "b")), key, 4,
              0.3 * u(*key, "d"))
    for i in range(2 + int(2 * u("reeds", k, "p"))):
        key = ("reeds", k, "p", i)
        x, y = _disc(key, r * 0.5)
        hh = h * (1.05 + 0.2 * u(*key, "h"))
        a = 2.0 * M.PI * u(*key, "a")
        tip = blade(c, "grass.reed", x, y, hh, 0.006, a, 0.12, key, 3, 0.4)
        dx, dy = _dir(a)
        leaf(c, "grass.plume", (tip[0] - dx * 0.1, tip[1] - dy * 0.1, tip[2] - 0.22), a, 0.26,
             0.07, 0.06, (*key, "pl"), droop=0.05)


def cattails(c: Clump, k: int) -> None:
    r, h = K.CLUMPS["cattails"][1], K.CLUMPS["cattails"][2]
    for i in range(9 + int(4 * u("cattails", k, "n"))):
        key = ("cattails", k, i)
        x, y = _disc(key, r)
        hh = h * (0.6 + 0.45 * u(*key, "h"))
        blade(c, "grass.reed", x, y, hh, 0.014 + 0.006 * u(*key, "w"),
              2.0 * M.PI * u(*key, "l"), hh * (0.1 + 0.25 * u(*key, "b")), key, 4,
              0.25 * u(*key, "d"))
    for i in range(2 + int(2 * u("cattails", k, "s"))):
        key = ("cattails", k, "s", i)
        x, y = _disc(key, r * 0.5)
        hh = h * (0.95 + 0.15 * u(*key, "h"))
        a = 2.0 * M.PI * u(*key, "a")
        tip = blade(c, "grass.stem", x, y, hh, 0.006, a, 0.04, key, 3)
        # the brown head: a hexagonal column 0.18 m long under the tip, a point over it
        hr = 0.012
        z0, z1 = tip[2] - 0.24, tip[2] - 0.06
        cx, cy = tip[0], tip[1]
        ring_ = [(cx + hr * M.cos(2.0 * M.PI * j / 6), cy + hr * M.sin(2.0 * M.PI * j / 6))
                 for j in range(6)]
        for j in range(6):
            p, q = ring_[j], ring_[(j + 1) % 6]
            rows = [((p[0], p[1], z0), (q[0], q[1], z0), 0.0)]
            mid = ((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0, z1)
            c.strip("grass.cattail", rows + [((p[0], p[1], z1), (q[0], q[1], z1), 0.9)],
                    (mid[0] * 0.5 + cx * 0.5, mid[1] * 0.5 + cy * 0.5, z1 + 0.02),
                    u(*key, "tone"), 0.0, up_lean=0.3)


def weeds(c: Clump, k: int) -> None:
    r = K.CLUMPS["weeds"][1]
    n = 6 + int(4 * u("weeds", k, "n"))
    a0 = 2.0 * M.PI * u("weeds", k, "a0")
    for i in range(n):
        key = ("weeds", k, i)
        a = a0 + 2.0 * M.PI * (i + 0.3 * u(*key, "j")) / n
        L = r * (0.8 + 0.5 * u(*key, "l"))
        leaf(c, "grass.weed", (0.0, 0.0, 0.005), a, L, L * 0.38, 0.03 + 0.04 * u(*key, "r"),
             key, 0.3 * u(*key, "d"), droop=0.004)
    for i in range(1 + int(2 * u("weeds", k, "s"))):
        key = ("weeds", k, "s", i)
        x, y = _disc(key, r * 0.3)
        hh = K.CLUMPS["weeds"][2] * (0.7 + 0.6 * u(*key, "h"))
        a = 2.0 * M.PI * u(*key, "a")
        tip = blade(c, "grass.stem", x, y, hh, 0.005, a, hh * 0.1, key, 3, 0.3)
        for j in range(3):
            t = 0.35 + 0.2 * j
            leaf(c, "grass.weed", (x + (tip[0] - x) * t, y + (tip[1] - y) * t, hh * t),
                 a + 2.2 * j, 0.05, 0.02, 0.01, (*key, "l", j), droop=0.01)
        head(c, "grass.seed", tip, 0.012, 5, (*key, "h"), 0.2)


def fern(c: Clump, k: int) -> None:
    r, h = K.CLUMPS["fern"][1], K.CLUMPS["fern"][2]
    n = 4 + int(3 * u("fern", k, "n"))
    a0 = 2.0 * M.PI * u("fern", k, "a0")
    for i in range(n):
        key = ("fern", k, i)
        a = a0 + 2.0 * M.PI * (i + 0.3 * u(*key, "j")) / n
        dx, dy = _dir(a)
        sx, sy = -dy, dx
        L = (r + h) * (0.75 + 0.35 * u(*key, "l"))
        rise = h * (0.8 + 0.4 * u(*key, "r"))
        # the rachis: an arch out and up, its tip drooping
        pts = []
        for j in range(7):
            t = j / 6
            pts.append((dx * L * t * 0.75, dy * L * t * 0.75,
                        rise * math.sin(math.pi * 0.62 * t) * (1.0 - 0.25 * t)))
        rows = [((p[0] - sx * 0.003, p[1] - sy * 0.003, p[2]),
                 (p[0] + sx * 0.003, p[1] + sy * 0.003, p[2]), j / 6)
                for j, p in enumerate(pts[:-1])]
        c.strip("grass.fern", rows, pts[-1], u(*key, "tone"), 0.0)
        for j in range(1, 6):
            t = j / 6
            p = pts[j]
            pl = 0.075 * (1.0 - 0.6 * t) * (0.8 + 0.4 * u(*key, "p", j))
            for side in (-1.0, 1.0):
                b = math.atan2(dy, dx) + side * (M.PI / 2.0 - 0.5)
                leaf(c, "grass.fern", p, b, pl, pl * 0.38, 0.004, (*key, j, side),
                     droop=pl * 0.25)


def ag8(c: Clump, species: str, k: int, scale: float) -> None:
    """AG8's scrub or sedum (`assetgen.props.trees`) at ground cover scale, on the grass
    master: its foliage slots become grass slots, its normals lean up, its height share the
    sway weight."""
    from ..props import trees as TR
    from ..streets.kit import _normals
    m = TR.make(species, k)
    names = {"foliage.scrub": "grass.scrub", "foliage.dry": "grass.scrub_dry",
             "foliage.sedum": "grass.sedum", "foliage.sedum_red": "grass.sedum_red"}
    zmax = max((p[2] for sl in m.slots.values() for p in sl.pos), default=1) or 1
    for name in sorted(m.slots):
        sl = m.slots[name]
        if not sl.idx:
            continue
        s = c._s(names.get(name, "grass.scrub"))
        b = len(s["pos"])
        nrm = _normals(sl)
        for p, n in zip(sl.pos, nrm):
            s["pos"].append((p[0] * scale / 1000.0, p[1] * scale / 1000.0,
                             p[2] * scale / 1000.0))
            nx, ny, nz = n[0] * 0.5, n[1] * 0.5, abs(n[2]) * 0.5 + 0.5
            L = math.sqrt(nx * nx + ny * ny + nz * nz)
            s["nrm"].append((nx / L, ny / L, nz / L))
            s["col"].append((int(round(255 * min(max(p[2] / zmax, 0.0), 1.0))),
                             int(255 * u(species, k, len(s["pos"]) % 7)), 0, 255))
            s["uv"].append((0.5, min(max(p[2] / zmax, 0.0), 1.0)))
        s["idx"] += [b + i for i in sl.idx]


AG8_SCALE = {"scrub": 0.5, "sedum": 0.34}


def make(kind: str, k: int, colors: list[str] | None = None) -> Clump:
    c = Clump()
    if kind == "lawn":
        lawn(c, k)
    elif kind == "clover":
        clover(c, k)
    elif kind == "flowers":
        flowers(c, k, colors or list(K.FLOWER_FALLBACK))
    elif kind == "meadow":
        meadow(c, k, 0.25)
    elif kind == "meadow_dry":
        meadow(c, k, 0.8, "meadow_dry")
    elif kind == "reeds":
        reeds(c, k)
    elif kind == "cattails":
        cattails(c, k)
    elif kind == "weeds":
        weeds(c, k)
    elif kind == "fern":
        fern(c, k)
    elif kind in AG8_SCALE:
        ag8(c, kind, k, AG8_SCALE[kind])
    else:
        raise ValueError(kind)
    return c


def family(kind: str, palette: str | None = None) -> str:
    """A clump family's name: the kind, or flowers of a palette (`flowers.<c0>_<c1>_<c2>`)."""
    return kind if kind != "flowers" else f"flowers.{palette}"


def palette_key(colors: list[str]) -> str:
    return "_".join(c.lstrip("#") for c in colors)


def node(fam: str, k: int) -> str:
    """A clump variant's node (never ending in digits after a dot: Blender's copy suffix)."""
    return f"clump.{fam}.v{k}"
