"""AG0's spike (scope 14.1): three generated test buildings to measure Unreal's import.

- `tower`: a 92-floor curtain-wall tower on a podium, about a million unique triangles in its
  shell (walls with window and spandrel openings, reveals, sills, drips, fins, slab bands),
  window frames as one part instanced on every window, roof equipment as parts;
- `shopfront_row`: five shop units with glazed fronts, awnings and sign boxes, three floors
  of punched brick windows over them, party walls on both sides;
- `shanty_stack`: shacks stacked four high with corrugated walls, tarps, stairs, windows,
  AC units and dishes as parts.

The generators are simple (AG1 builds the real ones) but use the real contract: integer
millimeters in the building frame, exact triangulation, material slots, two UV sets, vertex
vertex colors (a gray darkening toward the ground, which glTF multiplies into the base color;
a random id per window in alpha for the glass master's interior mapping), parts in their own
frame instanced by transform, simple collision boxes per mass and Custom Primitive Data per
building. Randomness is blake2b of (salt, id, purpose).

`write_spike(out)` writes per building `<name>.glb` (shell and part prototypes, the import
the exporter uses), `<name>_gpuinst.glb` (parts with EXT_mesh_gpu_instancing),
`<name>_quant.glb` (KHR_mesh_quantization), `<name>_ubx.glb` (UBX_ collision nodes) and
`tower_lean.glb` (no UV1 or vertex colors, to measure what they cost in Nanite), plus
`unreal_contribution.json` (assetgen's entries in the exporter's manifest format) and
`spike_report.json`.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from citygen import dmath as M

from . import __version__
from . import canon as C
from . import gltf as G
from .mesh import MeshBuilder, quad3, wall_frame

SALT = "ag0.spike"


def rnd(key: str, purpose: str) -> float:
    h = hashlib.blake2b(f"{SALT}|{key}|{purpose}".encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "little") / 2.0 ** 64


def rint(key: str, purpose: str, lo: int, hi: int) -> int:
    return lo + int(rnd(key, purpose) * (hi - lo + 1))


# material slots: master material, sRGB color, roughness, metallic
SLOTS = {
    "concrete": ("facade", "#8c8a86", 0.85, 0.0),
    "brick": ("facade", "#7a4a35", 0.9, 0.0),
    "plaster": ("facade", "#b9a58c", 0.9, 0.0),
    "spandrel": ("facade", "#2a3440", 0.5, 0.3),
    "metal": ("metal", "#3a3f45", 0.45, 0.9),
    "corrugated": ("metal", "#7e7466", 0.7, 0.6),
    "rust": ("metal", "#8f4a2b", 0.8, 0.4),
    "tarp": ("facade", "#2f5f8a", 0.8, 0.0),
    "glass": ("glass", "#1b2430", 0.08, 0.0),
    "shopglass": ("glass", "#22303c", 0.08, 0.0),
    "roof": ("facade", "#4d4b47", 0.95, 0.0),
    "sign": ("neon", "#ff2a6d", 0.5, 0.0),
    "awning": ("facade", "#8c2f2b", 0.85, 0.0),
    "bark": ("facade", "#4a3b2c", 0.95, 0.0),
    "leaf": ("foliage", "#3f6b2a", 0.7, 0.0),
}


def srgb_linear(hex_color: str) -> list[float]:
    out = []
    for k in range(3):
        c = int(hex_color[1 + 2 * k:3 + 2 * k], 16) / 255.0
        out.append(round(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4, 6))
    return out


# ---------------------------------------------------------------------------
# Walls in plan: P(s, t, d) = a + u s + n d at height t (integer mm)
# ---------------------------------------------------------------------------

@dataclass
class Wall:
    a: tuple[int, int]
    b: tuple[int, int]

    def __post_init__(self):
        dx, dy = self.b[0] - self.a[0], self.b[1] - self.a[1]
        self.L = int(round(math.sqrt(dx * dx + dy * dy)))
        self.u = (dx / self.L, dy / self.L)
        self.n = (self.u[1], -self.u[0])          # outward: right of a -> b

    def P(self, s: int, t: int, d: int = 0) -> tuple[int, int, int]:
        return (int(round(self.a[0] + self.u[0] * s + self.n[0] * d)),
                int(round(self.a[1] + self.u[1] * s + self.n[1] * d)), int(t))

    @property
    def yaw(self) -> float:
        return M.degrees(M.atan2(self.u[1], self.u[0]))


def wbox(mb: MeshBuilder, mat: str, w: Wall, s0, s1, t0, t1, d0, d1, color,
         faces="fltrb"):
    """A box on a wall: s0..s1 along, t0..t1 up, d0..d1 out (front at d1). faces: f front,
    l and r ends, t top, b bottom."""
    P = w.P
    if "f" in faces:
        quad3(mb, mat, P(s0, t0, d1), P(s1, t0, d1), P(s1, t1, d1), P(s0, t1, d1), color)
    if "t" in faces:
        quad3(mb, mat, P(s0, t1, d1), P(s1, t1, d1), P(s1, t1, d0), P(s0, t1, d0), color)
    if "b" in faces:
        quad3(mb, mat, P(s0, t0, d0), P(s1, t0, d0), P(s1, t0, d1), P(s0, t0, d1), color)
    if "l" in faces:
        quad3(mb, mat, P(s0, t0, d0), P(s0, t0, d1), P(s0, t1, d1), P(s0, t1, d0), color)
    if "r" in faces:
        quad3(mb, mat, P(s1, t0, d1), P(s1, t0, d0), P(s1, t1, d0), P(s1, t1, d1), color)


def opening(mb: MeshBuilder, mat: str, w: Wall, s0, s1, t0, t1, depth, color):
    """The four reveals of an opening, `depth` into the wall."""
    P = w.P
    quad3(mb, mat, P(s0, t0, 0), P(s1, t0, 0), P(s1, t0, -depth), P(s0, t0, -depth), color)
    quad3(mb, mat, P(s1, t1, 0), P(s0, t1, 0), P(s0, t1, -depth), P(s1, t1, -depth), color)
    quad3(mb, mat, P(s0, t1, 0), P(s0, t0, 0), P(s0, t0, -depth), P(s0, t1, -depth), color)
    quad3(mb, mat, P(s1, t0, 0), P(s1, t1, 0), P(s1, t1, -depth), P(s1, t0, -depth), color)


def pane(mb: MeshBuilder, mat: str, w: Wall, s0, s1, t0, t1, d, color):
    quad3(mb, mat, w.P(s0, t0, d), w.P(s1, t0, d), w.P(s1, t1, d), w.P(s0, t1, d), color)


def grime(t: int, top: int, wear: float = 1.0) -> tuple[int, int, int, int]:
    """Vertex color: a gray that darkens toward the ground (glTF multiplies COLOR_0 into the
    base color); alpha 255."""
    v = 255 - min(int(round(90 * wear * max(0.0, 1.0 - t / max(top, 1)) ** 2)), 135)
    return (v, v, v, 255)


def window_id(key: str, k: int) -> tuple[int, int, int, int]:
    """A window's vertex color: white, and a random id in alpha (opaque materials ignore
    it; the glass master reads it to vary the room behind)."""
    return (255, 255, 255, 1 + int(rnd(key, f"win{k}") * 254))


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def ring_walls(pts) -> list[Wall]:
    return [Wall(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]


@dataclass
class Spike:
    key: str
    shell: MeshBuilder = field(default_factory=MeshBuilder)
    parts: dict = field(default_factory=dict)       # kind -> MeshBuilder (own frame)
    xforms: dict = field(default_factory=dict)      # kind -> [(x, y, z, yaw)]
    masses: list = field(default_factory=list)      # (x0, y0, x1, y1, z0, z1) mm, axis aligned
    cpd: list = field(default_factory=list)

    def part(self, kind: str) -> MeshBuilder:
        return self.parts.setdefault(kind, MeshBuilder())

    def place(self, kind: str, x: int, y: int, z: int, yaw: float):
        self.xforms.setdefault(kind, []).append((int(x), int(y), int(z), float(yaw)))


# ---------------------------------------------------------------------------
# Parts (own frame: x along the wall, -y out of it, z up)
# ---------------------------------------------------------------------------

def _pbox(mb, mat, x0, y0, z0, x1, y1, z1, color=(255, 255, 255, 255)):
    mb.box(mat, x0, y0, z0, x1, y1, z1, color, bottom=True)


def part_window_frame(w: int, h: int) -> MeshBuilder:
    """A window frame of w x h mm: four rails and a mullion, 60 mm deep."""
    mb = MeshBuilder()
    r = 50
    hw = w // 2
    _pbox(mb, "metal", -hw, -30, 0, hw, 30, r)
    _pbox(mb, "metal", -hw, -30, h - r, hw, 30, h)
    _pbox(mb, "metal", -hw, -30, r, -hw + r, 30, h - r)
    _pbox(mb, "metal", hw - r, -30, r, hw, 30, h - r)
    _pbox(mb, "metal", -r // 2, -20, r, r // 2, 20, h - r)
    return mb


def part_ac_unit() -> MeshBuilder:
    mb = MeshBuilder()
    _pbox(mb, "metal", -450, -300, 0, 450, 300, 700)
    for k in range(5):
        _pbox(mb, "metal", -400 + k * 160, -320, 120, -340 + k * 160, -300, 620)
    return mb


def part_water_tank() -> MeshBuilder:
    mb = MeshBuilder()
    n, r = 16, 1500
    pts = [(int(round(r * M.cos(2 * M.PI * k / n))),
            int(round(r * M.sin(2 * M.PI * k / n)))) for k in range(n)]
    for k in range(n):
        a, b = pts[k], pts[(k + 1) % n]
        quad3(mb, "rust", (a[0], a[1], 600), (b[0], b[1], 600), (b[0], b[1], 3600),
              (a[0], a[1], 3600))
    from .mesh import flat_frame
    mb.face("rust", flat_frame(3600), pts)
    for x, y in ((-900, -900), (900, -900), (900, 900), (-900, 900)):
        _pbox(mb, "metal", x - 80, y - 80, 0, x + 80, y + 80, 600)
    return mb


def part_dish() -> MeshBuilder:
    """A mast and a dish (a 12-sided disk, both faces) facing -y."""
    from .mesh import Frame
    mb = MeshBuilder()
    _pbox(mb, "metal", -30, -30, 0, 30, 30, 600)
    n, r = 12, 450
    disk = [(int(round(r * M.cos(2 * M.PI * k / n))),
             int(round(r * M.sin(2 * M.PI * k / n)))) for k in range(n)]
    mb.face("metal", Frame((0, -150, 900), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), disk)
    mb.face("metal", Frame((0, -100, 900), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), disk)
    return mb


def part_awning(w: int, depth: int) -> MeshBuilder:
    """An awning w mm wide sloping out `depth` mm (front at -y), both sides, with
    side cheeks."""
    mb = MeshBuilder()
    hw = w // 2
    a, b = (-hw, 0, 600), (hw, 0, 600)
    c, d = (hw, -depth, 0), (-hw, -depth, 0)
    quad3(mb, "awning", d, c, b, a)
    quad3(mb, "awning", a, b, c, d)
    quad3(mb, "awning", (-hw, -depth, 0), (-hw, -depth, -250), (hw, -depth, -250),
          (hw, -depth, 0))
    return mb


def part_sign(w: int, h: int) -> MeshBuilder:
    mb = MeshBuilder()
    _pbox(mb, "sign", -w // 2, -200, 0, w // 2, 0, h)
    return mb


# ---------------------------------------------------------------------------
# The tower
# ---------------------------------------------------------------------------

def tower(floors: int = 92) -> Spike:
    sp = Spike("spike.tower.bld")
    mb = sp.shell
    W, D = 54000, 42000
    PW, PD, PH = 72000, 60000, 15000
    fh, bw = 3600, 1200
    z0 = PH
    top = z0 + floors * fh
    fw, fhh = bw - 300, fh - 1200
    sp.parts["part.window.frame"] = part_window_frame(fw, fhh)
    # podium: three 5 m floors of 6 m storefront bays
    pod = ring_walls(rect(-PW // 2, -PD // 2, PW // 2, PD // 2))
    for w in pod:
        nb = w.L // 6000
        for f in range(3):
            for i in range(nb):
                s0, s1 = i * 6000, (i + 1) * 6000
                t0, t1 = f * 5000, (f + 1) * 5000
                ho = (s0 + 300, t0 + 600, s1 - 300, t1 - 600)
                col = grime(t0, top)
                fr = wall_frame(w.a, w.b, 0)
                mb.face("concrete", fr, rect(s0, t0, s1, t1), [rect(*ho)], col)
                opening(mb, "concrete", w, ho[0], ho[2], ho[1], ho[3], 250, col)
                pane(mb, "shopglass", w, ho[0], ho[2], ho[1], ho[3], -250,
                     window_id(sp.key, 900000 + f * 1000 + i))
            wbox(mb, "metal", w, 0, w.L, f * 5000 + 4700, f * 5000 + 5000, 0, 300,
                 grime(f * 5000, top), faces="ftb")
    from .mesh import flat_frame
    mb.face("roof", flat_frame(PH), rect(-PW // 2, -PD // 2, PW // 2, PD // 2),
            [rect(-W // 2, -D // 2, W // 2, D // 2)])
    for w in pod:
        wbox(mb, "concrete", w, 0, w.L, PH, PH + 1100, -250, 0, grime(PH, top), faces="ftb")
    sp.masses.append((-PW // 2, -PD // 2, PW // 2, PD // 2, 0, PH))
    # the tower: 1.2 m bays, a window and a spandrel panel each, fins, sills, drips, bands
    k = 0
    for w in ring_walls(rect(-W // 2, -D // 2, W // 2, D // 2)):
        nb = w.L // bw
        fr = wall_frame(w.a, w.b, 0)
        for f in range(floors):
            t0 = z0 + f * fh
            col = grime(t0, top)
            for i in range(nb):
                s0 = i * bw
                win = (s0 + 150, t0 + 900, s0 + bw - 150, t0 + fh - 300)
                spd = (s0 + 150, t0 + 250, s0 + bw - 150, t0 + 750)
                mb.face("concrete", fr, rect(s0, t0, s0 + bw, t0 + fh),
                        [rect(*win), rect(*spd)], col)
                opening(mb, "concrete", w, win[0], win[2], win[1], win[3], 150, col)
                pane(mb, "glass", w, win[0], win[2], win[1], win[3], -150, window_id(sp.key, k))
                opening(mb, "spandrel", w, spd[0], spd[2], spd[1], spd[3], 80, col)
                pane(mb, "spandrel", w, spd[0], spd[2], spd[1], spd[3], -80, col)
                wbox(mb, "concrete", w, win[0] - 50, win[2] + 50, win[1] - 80, win[1], 0, 60,
                     col)
                wbox(mb, "metal", w, win[0] - 30, win[2] + 30, win[3], win[3] + 60, 0, 40,
                     col)
                wbox(mb, "metal", w, s0 - 50, s0 + 50, t0, t0 + fh, 0, 350, col,
                     faces="flr")
                wbox(mb, "concrete", w, s0, s0 + bw, t0, t0 + 200, 0, 40, col, faces="ftb")
                cx = (win[0] + win[2]) // 2
                x, y, _ = w.P(cx, 0, -100)
                sp.place("part.window.frame", x, y, win[1], w.yaw)
                k += 1
    mb.face("roof", flat_frame(top), rect(-W // 2, -D // 2, W // 2, D // 2))
    for w in ring_walls(rect(-W // 2, -D // 2, W // 2, D // 2)):
        wbox(mb, "metal", w, 0, w.L, top, top + 1500, -300, 0, (255, 255, 255, 255), faces="ftb")
    sp.masses.append((-W // 2, -D // 2, W // 2, D // 2, PH, top))
    # crown: a setback lantern of louvers
    cw, cd, ch = W - 12000, D - 12000, 9000
    for w in ring_walls(rect(-cw // 2, -cd // 2, cw // 2, cd // 2)):
        fr = wall_frame(w.a, w.b, 0)
        mb.face("spandrel", fr, rect(0, top, w.L, top + ch))
        for i in range(w.L // 600):
            wbox(mb, "metal", w, i * 600, i * 600 + 120, top, top + ch, 0, 500,
                 (255, 255, 255, 255), faces="flr")
    mb.face("roof", flat_frame(top + ch), rect(-cw // 2, -cd // 2, cw // 2, cd // 2))
    sp.masses.append((-cw // 2, -cd // 2, cw // 2, cd // 2, top, top + ch))
    sp.parts["part.roof.ac_unit"] = part_ac_unit()
    sp.parts["part.roof.water_tank"] = part_water_tank()
    for j in range(8):
        sp.place("part.roof.ac_unit", -PW // 2 + 4000 + j * 3000, -PD // 2 + 3000, PH, 0.0)
        sp.place("part.roof.ac_unit", -PW // 2 + 4000 + j * 3000, PD // 2 - 3000, PH, 180.0)
    sp.place("part.roof.water_tank", -cw // 2 + 4000, 0, top + ch, 0.0)
    sp.place("part.roof.water_tank", cw // 2 - 4000, 0, top + ch, 0.0)
    sp.cpd = [0.82, 0.86, 0.9, 0.15, 6.0, 0.4, 0.55, rnd(sp.key, "seed")]
    return sp


# ---------------------------------------------------------------------------
# The shopfront row
# ---------------------------------------------------------------------------

def shopfront_row(units: int = 5) -> Spike:
    sp = Spike("spike.shopfront_row.bld")
    mb = sp.shell
    uw, depth, gh, fh, upper = 7000, 14000, 4500, 3300, 3
    W = units * uw
    top = gh + upper * fh
    x0, y0 = -W // 2, -depth // 2
    front = Wall((x0, y0), (x0 + W, y0))
    back = Wall((x0 + W, y0 + depth), (x0, y0 + depth))
    sides = [Wall((x0 + W, y0), (x0 + W, y0 + depth)), Wall((x0, y0 + depth), (x0, y0))]
    sp.parts["part.window.frame"] = part_window_frame(1100, 1600)
    sp.parts["part.shop.awning"] = part_awning(6200, 1500)
    sp.parts["part.shop.sign"] = part_sign(4000, 700)
    sp.parts["part.roof.ac_unit"] = part_ac_unit()
    sp.parts["part.roof.water_tank"] = part_water_tank()
    fr = wall_frame(front.a, front.b, 0)
    k = 0
    for u in range(units):
        s0 = u * uw
        col = grime(0, top)
        shop = (s0 + 500, 300, s0 + uw - 2000, 3400)
        door = (s0 + uw - 1700, 0, s0 + uw - 500, 2600)
        # the door is a notch in the wall's outline (it reaches the ground), the shop
        # window a hole
        outline = [(s0, 0), (door[0], 0), (door[0], door[3]), (door[2], door[3]),
                   (door[2], 0), (s0 + uw, 0), (s0 + uw, gh), (s0, gh)]
        mb.face("plaster", fr, outline, [rect(*shop)], col)
        opening(mb, "plaster", front, shop[0], shop[2], shop[1], shop[3], 200, col)
        pane(mb, "shopglass", front, shop[0], shop[2], shop[1], shop[3], -200,
             window_id(sp.key, 1000 + u))
        opening(mb, "plaster", front, door[0], door[2], door[1], door[3], 200, col)
        pane(mb, "metal", front, door[0], door[2], door[1], door[3], -200, col)
        x, y, _ = front.P(s0 + uw // 2, 0, 0)
        sp.place("part.shop.awning", x, y, 3600, front.yaw)
        sp.place("part.shop.sign", x, y, 3700 + 600 + 200, front.yaw)
        for f in range(upper):
            t0 = gh + f * fh
            col = grime(t0, top, 1.3)
            wins = [(s0 + 1200, t0 + 900, s0 + 2300, t0 + 2500),
                    (s0 + 4700, t0 + 900, s0 + 5800, t0 + 2500)]
            mb.face("brick", fr, rect(s0, t0, s0 + uw, t0 + fh), [rect(*h) for h in wins], col)
            for h in wins:
                opening(mb, "brick", front, h[0], h[2], h[1], h[3], 220, col)
                pane(mb, "glass", front, h[0], h[2], h[1], h[3], -220, window_id(sp.key, k))
                wbox(mb, "concrete", front, h[0] - 80, h[2] + 80, h[1] - 120, h[1], 0, 80, col)
                x, y, _ = front.P((h[0] + h[2]) // 2, 0, -150)
                sp.place("part.window.frame", x, y, h[1], front.yaw)
                k += 1
        wbox(mb, "brick", front, s0, s0 + uw, gh - 300, gh, 0, 150, col, faces="ftb")
    frb = wall_frame(back.a, back.b, 0)
    for f in range(1 + upper):
        t0 = 0 if f == 0 else gh + (f - 1) * fh
        t1 = gh if f == 0 else t0 + fh
        holes = [] if f == 0 else [rect(s, t0 + 1000, s + 900, t0 + 2200)
                                   for s in range(2000, W - 1000, 7000)]
        mb.face("brick", frb, rect(0, t0, W, t1), holes, grime(t0, top, 1.4))
        for h in holes:
            hh = (h[0][0], h[0][1], h[2][0], h[2][1])
            opening(mb, "brick", back, hh[0], hh[2], hh[1], hh[3], 200, grime(t0, top))
            pane(mb, "glass", back, hh[0], hh[2], hh[1], hh[3], -200, window_id(sp.key, k))
            k += 1
    for w in sides:
        mb.face("brick", wall_frame(w.a, w.b, 0), rect(0, 0, w.L, top), (), grime(0, top, 1.6))
    from .mesh import flat_frame
    mb.face("roof", flat_frame(top), rect(x0, y0, x0 + W, y0 + depth))
    for w in [front, sides[0], back, sides[1]]:
        wbox(mb, "brick", w, 0, w.L, top, top + 900, -250, 0, grime(top, top), faces="ftb")
    for j in range(units + 3):
        sp.place("part.roof.ac_unit", x0 + 2500 + j * 4300, y0 + depth - 2500, top, 180.0)
    sp.place("part.roof.water_tank", x0 + W - 4000, y0 + 4000, top, 0.0)
    sp.masses.append((x0, y0, x0 + W, y0 + depth, 0, top))
    sp.cpd = [0.95, 0.9, 0.85, 0.6, 3.0, 0.8, 0.4, rnd(sp.key, "seed")]
    return sp


# ---------------------------------------------------------------------------
# The shanty stack
# ---------------------------------------------------------------------------

def corrugated(mb: MeshBuilder, mat: str, w: Wall, s0: int, s1: int, t0: int, t1: int,
               color, pitch: int = 150, amp: int = 35):
    """A corrugated wall: ridges `pitch` mm apart, `amp` mm out, as a zig-zag of quads."""
    n = max((s1 - s0) // pitch, 1)
    step = (s1 - s0) / n
    xs = [s0 + int(round(i * step / 2)) for i in range(2 * n + 1)]
    for i in range(2 * n):
        da, db = (0, amp) if i % 2 == 0 else (amp, 0)
        quad3(mb, mat, w.P(xs[i], t0, da), w.P(xs[i + 1], t0, db), w.P(xs[i + 1], t1, db),
              w.P(xs[i], t1, da), color)


def shanty_stack(levels: int = 4) -> Spike:
    sp = Spike("spike.shanty_stack.bld")
    mb = sp.shell
    from .mesh import flat_frame
    sp.parts["part.roof.ac_unit"] = part_ac_unit()
    sp.parts["part.roof.dish"] = part_dish()
    sp.parts["part.window.frame"] = part_window_frame(800, 900)
    top_all = levels * 2900
    k = 0
    for lv in range(levels):
        z0 = lv * 2900
        x = -9000
        j = 0
        while x < 9000:
            key = f"{lv}.{j}"
            w_ = rint(sp.key, "w" + key, 3000, 6000)
            d_ = rint(sp.key, "d" + key, 3500, 6000)
            h_ = rint(sp.key, "h" + key, 2500, 2900)
            off = rint(sp.key, "o" + key, -1200, 1200) if lv else 0
            xa, xb = x, min(x + w_, 9000)
            if xb - xa < 1500:
                break
            ya, yb = -6000 + off, -6000 + off + d_ + 6000 - (lv * 900)
            mat = ("corrugated", "rust", "plaster")[rint(sp.key, "m" + key, 0, 2)]
            col = grime(z0, top_all, 1.6)
            for w in ring_walls(rect(xa, ya, xb, yb)):
                if mat == "plaster":
                    win = (w.L // 2 - 450, z0 + 900, w.L // 2 + 450, z0 + 2000)
                    mb.face("plaster", wall_frame(w.a, w.b, 0), rect(0, z0, w.L, z0 + h_),
                            [rect(*win)], col)
                    opening(mb, "plaster", w, win[0], win[2], win[1], win[3], 120, col)
                    pane(mb, "glass", w, win[0], win[2], win[1], win[3], -120,
                         window_id(sp.key, k))
                    k += 1
                else:
                    corrugated(mb, mat, w, 0, w.L, z0, z0 + h_, col)
                    if rnd(sp.key, f"win{key}.{w.a}") < 0.5:
                        x_, y_, _ = w.P(w.L // 2, 0, 60)
                        sp.place("part.window.frame", x_, y_, z0 + 1000, w.yaw)
                if rnd(sp.key, f"ac{key}.{w.a}") < 0.3:
                    x_, y_, _ = w.P(w.L // 3, 0, 400)
                    sp.place("part.roof.ac_unit", x_, y_, z0 + 1600, w.yaw)
            mb.face("roof", flat_frame(z0 + h_), rect(xa, ya, xb, yb), (), col)
            if rnd(sp.key, "tarp" + key) < 0.5:
                tw = Wall((xa, ya), (xb, ya))
                quad3(mb, "tarp", tw.P(0, z0 + h_, 0), tw.P(tw.L, z0 + h_, 0),
                      tw.P(tw.L, z0 + h_ - 600, 1800), tw.P(0, z0 + h_ - 600, 1800))
                quad3(mb, "tarp", tw.P(0, z0 + h_ - 600, 1800), tw.P(tw.L, z0 + h_ - 600, 1800),
                      tw.P(tw.L, z0 + h_, 0), tw.P(0, z0 + h_, 0))
            if lv == levels - 1 and rnd(sp.key, "dish" + key) < 0.6:
                sp.place("part.roof.dish", (xa + xb) // 2, (ya + yb) // 2, z0 + h_, 0.0)
            sp.masses.append((xa, ya, xb, yb, z0, z0 + h_))
            x = xb
            j += 1
        # a stair up the west side to the next level
        if lv < levels - 1:
            sw = Wall((-9800, -6000), (-9800, -2000))
            for st in range(14):
                t = z0 + st * 200
                wbox(mb, "metal", sw, st * 280, st * 280 + 300, t, t + 60, -900, 0,
                     (255, 255, 255, 255))
    sp.cpd = [0.9, 0.85, 0.8, 1.2, 4.0, 0.7, 0.35, rnd(sp.key, "seed")]
    return sp


def tree(leaves: int = 1600) -> Spike:
    """Not a building: a 9 m tree of thin leaf cards (both faces) on a trunk, to try
    Nanite's foliage settings (voxel shape preservation) on the kind of mesh AG8 makes."""
    from .mesh import Frame
    sp = Spike("spike.tree.plt")
    mb = sp.shell
    mb.oriented_box("bark", 0, 0, 0, 450, 450, 4200, 1.0, 0.0)
    for k in range(6):
        a = 2 * M.PI * k / 6
        ux, uy = M.cos(a), M.sin(a)
        mb.oriented_box("bark", int(1100 * ux), int(1100 * uy), 3600 + 300 * (k % 3), 2200,
                        160, 160, ux, uy)
    for k in range(leaves):
        # a point in the crown (an ellipsoid 3.2 m across, 3.6 m high, at 6.2 m)
        u, v, w = rnd(sp.key, f"lu{k}"), rnd(sp.key, f"lv{k}"), rnd(sp.key, f"lw{k}")
        th, ph = 2 * M.PI * u, M.acos(2 * v - 1)
        r = M.power(w, 1.0 / 3.0)
        x = int(3200 * r * M.sin(ph) * M.cos(th))
        y = int(3200 * r * M.sin(ph) * M.sin(th))
        z = int(6200 + 1800 * r * M.cos(ph))
        a = 2 * M.PI * rnd(sp.key, f"la{k}")
        tilt = 0.6 * (rnd(sp.key, f"lt{k}") - 0.5)
        uax, uay = M.cos(a), M.sin(a)
        leaf = [(-150, 0), (150, 0), (150, 220), (-150, 220)]
        fr = Frame((x, y, z), (uax, uay, 0.0), (-uay * tilt, uax * tilt, 1.0 - abs(tilt)))
        mb.face("leaf", fr, leaf)
        back = Frame((x, y, z), (-uax, -uay, 0.0), (-uay * tilt, uax * tilt, 1.0 - abs(tilt)))
        mb.face("leaf", back, leaf)
    sp.masses.append((-225, -225, 225, 225, 0, 4200))
    sp.cpd = [1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, rnd(sp.key, "seed")]
    return sp


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _materials(g: G.Gltf) -> dict[str, int]:
    out = {}
    for name, (master, hex_c, rough, metal) in SLOTS.items():
        out[name] = g.material(name, srgb_linear(hex_c) + [1.0], metal, rough,
                               extras={"master": master, "slot": name})
    return out


def _glb(sp: Spike, variant: str) -> tuple[bytes, dict]:
    g = G.Gltf(generator=f"assetgen {__version__}", quantized=(variant == "quant"))
    mats = _materials(g)
    shell = g.mesh(sp.key + ".shell", sp.shell.primitives(mats, lean=(variant == "lean")),
                   extras={"kind": "shell"})
    children = [g.node(sp.key + ".shell", mesh=shell)]
    for kind in sorted(sp.parts):
        mesh = g.mesh(f"{sp.key}.{kind}", sp.parts[kind].primitives(mats),
                      extras={"kind": kind})
        xf = sp.xforms.get(kind, [])
        if variant == "gpuinst" and xf:
            inst = {"translation": [x[:3] for x in xf], "yaw_deg": [x[3] for x in xf]}
            children.append(g.node(f"{sp.key}.{kind}", mesh=mesh, instances=inst))
        else:
            children.append(g.node(f"{sp.key}.{kind}", mesh=mesh))
    if variant == "ubx":
        for j, (x0, y0, x1, y1, z0, z1) in enumerate(sp.masses):
            mb = MeshBuilder()
            mb.box("concrete", x0, y0, z0, x1, y1, z1, bottom=True)
            mesh = g.mesh(f"UBX_{sp.key}.shell_{j:02d}", mb.primitives(mats))
            children.append(g.node(f"UBX_{sp.key}.shell_{j:02d}", mesh=mesh))
    g.node(sp.key, children=children, root=True,
           extras={"cg": {"key": sp.key, "kind": "building", "cpd": sp.cpd}})
    data = g.to_glb()
    tri = sp.shell.triangles
    return data, {"triangles": tri, "part_triangles": {k: v.triangles
                                                       for k, v in sorted(sp.parts.items())}}


def _contribution_entry(sp: Spike, glb: str, h: str) -> dict:
    def part_entry(kind):
        xf = sp.xforms.get(kind, [])
        return {"kind": kind, "node": f"{sp.key}.{kind}", "asset": _asset(f"{sp.key}.{kind}"),
                "count": len(xf), "triangles": sp.parts[kind].triangles,
                "xforms": [[C.m(x / 1000.0), C.m(y / 1000.0), C.m(z / 1000.0), C.deg(yaw)]
                           for x, y, z, yaw in xf]}
    return {
        "key": sp.key, "kind": "building", "hash": h, "replaces": [],
        "glb": glb, "node": sp.key + ".shell", "asset": _asset(sp.key),
        "pivot": [0.0, 0.0, 0.0], "yaw_deg": 0.0, "nanite": True,
        "triangles": sp.shell.triangles,
        "slots": sorted(sp.shell.slots),
        "collision": {"simple": [{"center": [C.m((x0 + x1) / 2000.0), C.m((y0 + y1) / 2000.0),
                                             C.m((z0 + z1) / 2000.0)],
                                  "extent": [C.m((x1 - x0) / 2000.0), C.m((y1 - y0) / 2000.0),
                                             C.m((z1 - z0) / 2000.0)], "yaw_deg": 0.0}
                                 for x0, y0, x1, y1, z0, z1 in sp.masses]},
        "cpd": [round(v, 4) for v in sp.cpd],
        "parts": [part_entry(k) for k in sorted(sp.parts)],
    }


def _asset(name: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_+\-]", "_", name)


def contribution(entries: list[dict]) -> dict:
    """assetgen's part of the Unreal manifest (docs/unreal_export.md): entries by key,
    layered over the blockout's."""
    mats = {name: {"master": master, "color": srgb_linear(hex_c), "roughness": rough,
                   "metallic": metal} for name, (master, hex_c, rough, metal) in SLOTS.items()}
    return {"version": 1, "stage": "assetgen", "generator": f"assetgen {__version__} (AG0)",
            "frame": "building frame: citygen x east, y north, z up, m; glTF y up; Unreal "
                     "(100 x, -100 y, 100 z) cm, yaw -> -yaw",
            "layer": 2, "masters": ["facade", "glass", "metal", "neon", "foliage"],
            "materials": mats,
            "entries": entries}


SPIKES = {"tower": tower, "shopfront_row": shopfront_row, "shanty_stack": shanty_stack,
          "foliage_test": tree}


def write_spike(out_dir: str | Path, quantized: bool = True, which=None) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rep = {"buildings": {}}
    entries = []
    for name, make in SPIKES.items():
        if which and name not in which:
            continue
        sp = make()
        info = None
        variants = ("main", "gpuinst", "ubx") + (("quant",) if quantized else ())
        if name == "tower":
            variants += ("lean",)
        for variant in variants:
            data, info_v = _glb(sp, variant)
            fn = f"{name}.glb" if variant == "main" else f"{name}_{variant}.glb"
            (out / fn).write_bytes(data)
            if variant == "main":
                info = info_v
                info["bytes"] = len(data)
                info["sha256"] = C.sha256_bytes(data)
            else:
                info[f"{variant}_bytes"] = len(data)
                info[f"{variant}_sha256"] = C.sha256_bytes(data)
        info["instances"] = sum(len(v) for v in sp.xforms.values())
        info["masses"] = len(sp.masses)
        rep["buildings"][name] = info
        entries.append(_contribution_entry(sp, f"{name}.glb", info["sha256"][:16]))
    (out / "unreal_contribution.json").write_text(
        json.dumps(contribution(entries), indent=1) + "\n", encoding="utf-8", newline="\n")
    (out / "spike_report.json").write_text(json.dumps(rep, indent=1) + "\n",
                                           encoding="utf-8", newline="\n")
    return rep
