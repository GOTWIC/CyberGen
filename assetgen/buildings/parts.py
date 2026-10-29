"""Facade parts (scope 5.1.4, AG2): windows, mullion and transom caps, spandrel panels,
balconies, louvers, fins, sunshades, shutters, grilles, boards and infills, structural
members, capsule pods, screen blades, AC units and dishes.

Each part is generated in its own frame from quantized parameters (lengths in whole
centimeters, angles in 5 degree steps, discrete styles) and named by the hash of its type
and parameters, so two placements with the same parameters are one mesh. Within a building
a part placed at least `INSTANCE_MIN` times is an instance of that mesh (a hierarchical
instanced mesh in Unreal, the transforms relative to the building's pivot); one placed
fewer times is merged into the shell, unless turning it to its facade and rounding to the
millimeter would fold a thin triangle flat (`survives`): then it stays an instance. Across
buildings of a tile a part is one mesh when their parameters coincide (decision 13.2:
`share_parts`).

Part frame, millimeters: x along the facade (the viewer's right; parts are centered on
x = 0 unless said), y into the wall (the facade plane at y = 0, outward negative), z up. A
part is placed at a point on a facade with the facade's direction as its yaw (and an extra
yaw for angled fins and blades): the instance's x axis is the facade's direction and its y
axis the inward normal, so yaw = atan2(u_y, u_x).

Rules every generator keeps, so nothing fights the shell's faces: a proud element spans
y from -p to 0 exactly (its back face on the wall plane), a recessed one lies in front of
the pane (y < reveal), and a frame reaches 10 mm past its opening into the jambs, head and
sill so a part quantized to whole centimeters always meets the shell's millimeter opening.
Every part is closed (the mesh check runs on every part mesh).
"""

from __future__ import annotations

import hashlib

from citygen import dmath as M

from ..triangulate import area2, triangulate
from . import meshbuf as MB
from .meshbuf import Buf

PARTS_VERSION = 1
INSTANCE_MIN = 8             # placed fewer times in a building: merged into its shell
INSTANCE_ALWAYS: frozenset = frozenset()   # (AG4: roof equipment, `roofparts`) never merged
Q = 10                       # length step (mm)
A = 5                        # angle step (degrees)
OVERLAP = 10                 # frames reach this far into the jambs


def q(v: float) -> int:
    """A length to whole centimeters (mm)."""
    return int(round(v / Q)) * Q


def qa(v: float) -> int:
    return int(round(v / A)) * A


# ---------------------------------------------------------------------------
# Mesh kit: closed solids on a Buf, in the part frame
# ---------------------------------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _axes(n):
    """UV axes for a face of normal n: horizontal along the face and up for walls, x and y
    for floors and ceilings."""
    if abs(n[2]) > 0.9:
        return (1.0, 0.0, 0.0), (0.0, 1.0 if n[2] > 0 else -1.0, 0.0)
    h = (-n[1], n[0], 0.0)
    L = (h[0] * h[0] + h[1] * h[1]) ** 0.5
    return (h[0] / L, h[1] / L, 0.0), (0.0, 0.0, 1.0)


def face(b: Buf, slot: str, pts, n, tris=None) -> None:
    """A planar face of integer points with outward normal n (unit); the points are put in
    the order that makes their winding agree with n."""
    if tris is None:
        tris = [(0, k, k + 1) for k in range(1, len(pts) - 1)]
    p0, p1, p2 = pts[tris[0][0]], pts[tris[0][1]], pts[tris[0][2]]
    c = _cross(_sub(p1, p0), _sub(p2, p0))
    flip = c[0] * n[0] + c[1] * n[1] + c[2] * n[2] < 0
    ua, va = _axes(n)
    pl = b.plane(n, (0, 0, 0), ua, va)
    ix = [i for t in tris for i in ((t[0], t[2], t[1]) if flip else t)]
    b.add(slot, pl, pts, ix)


def box(b: Buf, slot: str, x0, x1, y0, y1, z0, z1) -> None:
    x0, x1, y0, y1, z0, z1 = (int(v) for v in (x0, x1, y0, y1, z0, z1))
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        return
    b.new_part()
    face(b, slot, [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], (0.0, -1.0, 0.0))
    face(b, slot, [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], (0.0, 1.0, 0.0))
    face(b, slot, [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)], (-1.0, 0.0, 0.0))
    face(b, slot, [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], (1.0, 0.0, 0.0))
    face(b, slot, [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)], (0.0, 0.0, -1.0))
    face(b, slot, [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0.0, 0.0, 1.0))


def _ccw(ring, want: bool):
    ring = [(int(p[0]), int(p[1])) for p in ring]
    return ring if (area2(ring) > 0) == want else ring[::-1]


def prism(b: Buf, slot: str, outer, holes, a0: int, a1: int, axis: str) -> None:
    """A polygon (with holes) in the plane across `axis`, extruded from a0 to a1 along it:
    axis "y": points (x, z); "x": points (y, z); "z": points (x, y)."""
    if a1 <= a0:
        return
    outer = _ccw(outer, True)
    holes = [_ccw(h, False) for h in holes]
    try:
        tris = triangulate(outer, holes, keep_straight=True)
    except Exception:
        return
    if not tris:
        return

    def p3(p, a):
        if axis == "y":
            return (p[0], a, p[1])
        if axis == "x":
            return (a, p[0], p[1])
        return (p[0], p[1], a)
    # the axis' unit vector and the in-plane normal of an edge (d0, d1) -> 3D, outward for
    # a counterclockwise outer ring, as the plane (u, v) maps into 3D
    if axis == "y":
        ax = (0.0, 1.0, 0.0)
        flipcap = True        # (x, z) counterclockwise is seen from -y
    elif axis == "x":
        ax = (1.0, 0.0, 0.0)
        flipcap = False       # (y, z) counterclockwise is seen from +x
    else:
        ax = (0.0, 0.0, 1.0)
        flipcap = False       # (x, y) counterclockwise is seen from +z
    b.new_part()
    pts = outer + [p for h in holes for p in h]
    n_lo = tuple(-c for c in ax)
    face(b, slot, [p3(p, a0) for p in pts], n_lo, tris)
    face(b, slot, [p3(p, a1) for p in pts], ax, tris)
    del flipcap
    for ring in [outer] + holes:
        n = len(ring)
        for i in range(n):
            p, r = ring[i], ring[(i + 1) % n]
            if p == r:
                continue
            d0, d1 = r[0] - p[0], r[1] - p[1]
            L = (d0 * d0 + d1 * d1) ** 0.5
            e = (d1 / L, -d0 / L)                 # right of the edge: out of the solid
            if axis == "y":
                nrm = (e[0], 0.0, e[1])
            elif axis == "x":
                nrm = (0.0, e[0], e[1])
            else:
                nrm = (e[0], e[1], 0.0)
            face(b, slot, [p3(p, a0), p3(r, a0), p3(r, a1), p3(p, a1)], nrm)


def frame_y(b: Buf, slot: str, x0, x1, z0, z1, fw, y0, y1) -> None:
    """A rectangular frame in the facade plane (outer x0..x1, z0..z1, bars fw wide)."""
    if x1 - x0 <= 2 * fw + 20 or z1 - z0 <= 2 * fw + 20:
        box(b, slot, x0, x1, y0, y1, z0, z1)
        return
    prism(b, slot, [(x0, z0), (x1, z0), (x1, z1), (x0, z1)],
          [[(x0 + fw, z0 + fw), (x1 - fw, z0 + fw), (x1 - fw, z1 - fw), (x0 + fw, z1 - fw)]],
          y0, y1, "y")


def ngon(cx, cz, r, n, phase=0.0):
    out = []
    for k in range(n):
        t = 2.0 * M.PI * (k + phase) / n
        out.append((int(round(cx + r * float(M.cos(t)))), int(round(cz + r * float(M.sin(t))))))
    return out


# ---------------------------------------------------------------------------
# Generators: one per family, from the parameter dict
# ---------------------------------------------------------------------------

def _bars(style: str, w: int, h: int):
    """Mullions (x positions) and transoms (z positions) of a window by style, inside its
    w x h opening (x from -w/2)."""
    xs, zs = [], []
    if style == "casement":
        k = 3 if w >= 2100 else (2 if w >= 900 else 1)
        xs = [-w // 2 + w * j // k for j in range(1, k)]
        if h >= 1500:
            zs = [h * 72 // 100]
    elif style == "sash":
        zs = [h // 2]
        k = 3 if w >= 900 else 2
        xs = [-w // 2 + w * j // k for j in range(1, k)]
        zs += [h // 4, 3 * h // 4] if h >= 1200 else []
    elif style == "awning":
        zs = [h * 75 // 100]
        if w >= 1500:
            xs = [0]
    elif style in ("industrial", "lattice"):
        step = 450 if style == "industrial" else 260
        kx = max(2, min(12, w // step))
        kz = max(2, min(12, h // step))
        xs = [-w // 2 + w * j // kx for j in range(1, kx)]
        zs = [h * j // kz for j in range(1, kz)]
    elif style == "ribbon":
        if w >= 1200:
            xs = [0]
    elif style == "unit":
        if h >= 2600:
            zs = [h - 600]
    return xs, zs


def gen_window(p: dict, b: Buf) -> None:
    w, h, r = p["w"], p["h"], p["r"]
    fw, fd = p["fw"], p["fd"]
    style = p["style"]
    y1 = r - 3
    y0 = max(r - fd, 4)
    if y1 - y0 < 15:
        y0 = y1 - 15
    o = OVERLAP
    frame_y(b, "frame", -w // 2 - o, w // 2 + o, -o, h + o, fw + o, y0, y1)
    bw = max(20, fw * 2 // 3)
    xs, zs = _bars(style, w, h)
    for x in xs:
        box(b, "frame", x - bw // 2, x + bw // 2, y0 + 8, y1, fw, h - fw)
    for z in zs:
        box(b, "frame", -w // 2 + fw, w // 2 - fw, y0 + 8, y1, z - bw // 2, z + bw // 2)
    if p.get("sill"):
        sp, sh, sx = p["sill"]
        box(b, "sill", -w // 2 - sx, w // 2 + sx, -sp, 0, -sh, 0)
    if p.get("lintel"):
        lp, lh, lx = p["lintel"]
        box(b, "sill", -w // 2 - lx, w // 2 + lx, -lp, 0, h, h + lh)


def gen_cap(p: dict, b: Buf) -> None:
    """A mullion cap (vertical, w wide, h tall from z 0) or a transom cap (horizontal, L long
    centered, t tall centered on z 0), p proud."""
    if p["dir"] == "v":
        box(b, p.get("slot", "mullion"), -p["w"] // 2, p["w"] // 2, -p["p"], 0, 0, p["h"])
    else:
        box(b, p.get("slot", "mullion"), -p["L"] // 2, p["L"] // 2, -p["p"], 0,
            -p["t"] // 2, p["t"] // 2)


def gen_spandrel(p: dict, b: Buf) -> None:
    """An opaque panel in front of the lower pane of a door row's opening (z 0 to h)."""
    w, h, r = p["w"], p["h"], p["r"]
    y1 = r - 4
    box(b, "spandrel_panel", -w // 2 - OVERLAP, w // 2 + OVERLAP, max(y1 - 50, 2), y1,
        -OVERLAP, h)


def gen_balcony(p: dict, b: Buf) -> None:
    """A balcony on the floor line (z 0 its top): slab w wide, d out, t thick, and its
    railing by style: solid (a parapet), rail (posts and rails), glass (glazing and a top
    rail), enclosed (parapet, glazing to the ceiling, a roof slab)."""
    w, d, t = p["w"], p["d"], p["t"]
    st = p["style"]
    x0, x1 = -w // 2, w // 2
    box(b, "balcony", x0, x1, -d, 0, -t, 0)
    rh = p["rh"]
    k = 70
    if st in ("solid", "enclosed"):
        box(b, "balcony", x0, x1, -d, -d + k, 0, rh)
        box(b, "balcony", x0, x0 + k, -d + k, 0, 0, rh)
        box(b, "balcony", x1 - k, x1, -d + k, 0, 0, rh)
    elif st == "glass":
        box(b, "glazing", x0 + 20, x1 - 20, -d + 20, -d + 40, 60, rh - 40)
        box(b, "glazing", x0 + 20, x0 + 40, -d + 40, -20, 60, rh - 40)
        box(b, "glazing", x1 - 40, x1 - 20, -d + 40, -20, 60, rh - 40)
        box(b, "railing", x0, x1, -d, -d + 50, rh - 40, rh)
        box(b, "railing", x0, x0 + 50, -d + 50, 0, rh - 40, rh)
        box(b, "railing", x1 - 50, x1, -d + 50, 0, rh - 40, rh)
    else:                                   # rail: posts, a top and a middle rail
        n = max(2, (w + 1499) // 1500 + 1)
        for j in range(n):
            x = x0 + (w - 50) * j // (n - 1)
            box(b, "railing", x, x + 50, -d, -d + 50, 0, rh - 40)
        box(b, "railing", x0 + 10, x0 + 60, -d + 50, -10, 0, rh - 40)
        box(b, "railing", x1 - 60, x1 - 10, -d + 50, -10, 0, rh - 40)
        for z0, z1 in ((rh - 40, rh), (rh // 2 - 20, rh // 2 + 20)):
            box(b, "railing", x0, x1, -d, -d + 50, z0, z1)
            box(b, "railing", x0, x0 + 50, -d + 50, 0, z0, z1)
            box(b, "railing", x1 - 50, x1, -d + 50, 0, z0, z1)
    if st == "enclosed":
        top = p["eh"]
        box(b, "glazing", x0 + 30, x1 - 30, -d + 30, -d + 50, rh, top - 60)
        box(b, "glazing", x0 + 30, x0 + 50, -d + 50, -20, rh, top - 60)
        box(b, "glazing", x1 - 50, x1 - 30, -d + 50, -20, rh, top - 60)
        nm = max(2, (w + 1199) // 1200 + 1)
        for j in range(nm):
            x = x0 + (w - 60) * j // (nm - 1)
            box(b, "railing", x, x + 60, -d, -d + 60, rh, top - 60)
        box(b, "balcony", x0, x1, -d, 0, top - 60, top)


def gen_louver(p: dict, b: Buf) -> None:
    """A louver panel filling an opening (w x h, the reveal r): a frame and n tilted blades."""
    w, h, r = p["w"], p["h"], p["r"]
    fw = 60
    y1 = r - 3
    y0 = max(r - 200, 6)
    frame_y(b, "louver", -w // 2 - OVERLAP, w // 2 + OVERLAP, -OVERLAP, h + OVERLAP, fw + OVERLAP,
            y0, y1)
    n = p["n"]
    bd = min(p["bd"], y1 - y0)
    tilt = p["tilt"]
    rise = int(round(bd * float(M.tan(M.radians(tilt))))) if tilt else 0
    th = 18
    span = h - 2 * fw
    for j in range(n):
        zc = fw + span * (2 * j + 1) // (2 * n)
        # profile in (y, z): the blade's outer edge lower by `rise`
        prof = [(y0, zc - rise // 2 - th), (y0 + bd, zc + rise // 2 - th),
                (y0 + bd, zc + rise // 2), (y0, zc - rise // 2)]
        prism(b, "louver", prof, [], -w // 2 + fw, w // 2 - fw, "x")


def gen_fin(p: dict, b: Buf) -> None:
    """A vertical fin t thick, d deep and h tall from z 0: proud (y -d to 0) or, for crown
    screens, inside the mass (y 0 to d)."""
    t, d, h = p["t"], p["d"], p["h"]
    if p.get("inward"):
        box(b, p.get("slot", "fin"), -t // 2, t // 2, 0, d, 0, h)
    else:
        box(b, p.get("slot", "fin"), -t // 2, t // 2, -d, 0, 0, h)


def gen_shade(p: dict, b: Buf) -> None:
    """A horizontal sunshade blade over an opening: L long, d out, t thick (top at z 0)."""
    box(b, "fin", -p["L"] // 2, p["L"] // 2, -p["d"], 0, -p["t"], 0)


def gen_shutter(p: dict, b: Buf) -> None:
    """One open shutter flat against the wall, w x h (z 0 up), with three rails."""
    w, h = p["w"], p["h"]
    box(b, "shutter", -w // 2, w // 2, -45, 0, 0, h)
    for z in (h // 6, h // 2, 5 * h // 6):
        box(b, "shutter", -w // 2 + 25, w // 2 - 25, -65, -45, z - 30, z + 30)


def gen_grille(p: dict, b: Buf) -> None:
    """A security grille in front of an opening: frame and vertical bars, 60 mm proud."""
    w, h = p["w"], p["h"]
    frame_y(b, "grille", -w // 2 - 40, w // 2 + 40, -40, h + 40, 40, -60, 0)
    n = max(1, min(16, w // 130))
    for j in range(1, n):
        x = -w // 2 + w * j // n
        box(b, "grille", x - 10, x + 10, -50, -30, 0, h)


def gen_panel(p: dict, b: Buf) -> None:
    """A flat panel: a board nailed over an opening (proud), an infill set into it, or a
    screen blade standing out from the wall."""
    st, w, h = p["style"], p["w"], p["h"]
    if st == "board":
        box(b, "patch_ply", -w // 2 - 40, w // 2 + 40, -25, 0, -40, h + 40)
    elif st == "infill":
        box(b, p["slot"], -w // 2 - OVERLAP, w // 2 + OVERLAP, 40, p["r"] - 2, -OVERLAP,
            h + OVERLAP)
    elif st == "screen":
        t, off = p["t"], p["off"]
        box(b, "perforated", -w // 2, w // 2, -off - t // 2, -off + t // 2, 0, h)
        # two brackets back to the wall
        for z in (h // 5, 4 * h // 5):
            box(b, "perforated", -15, 15, -off + t // 2, 0, z - 40, z + 40)
    elif st == "eggcrate":
        d, t = p["d"], p["t"]
        frame_y(b, p["slot"], -w // 2 - t, w // 2 + t, -t, h + t, t + OVERLAP, -d, 0)
    elif st == "addon":
        # a shanty add-on box bolted over an opening, d out, a small window in its front
        d = p["d"]
        box(b, "patch_sheet", -w // 2, w // 2, -d, 40, 0, h)
        ww = min(w - 400, 900)
        if ww >= 400 and h >= 1200:
            box(b, "glazing", -ww // 2, ww // 2, -d - 30, -d, h // 2 - 300, h // 2 + 300)


def gen_member(p: dict, b: Buf) -> None:
    """A structural member in the facade plane from (0, 0) to (dx, dz): w wide in the
    plane, y from y0 to y1 (proud members negative): a column, a beam or a diagonal."""
    dx, dz, w = p["dx"], p["dz"], p["w"]
    y0, y1 = p["y0"], p["y1"]
    slot = p.get("slot", "member")
    if dx == 0:
        box(b, slot, -w // 2, w // 2, y0, y1, 0, dz)
        return
    if dz == 0:
        box(b, slot, 0, dx, y0, y1, -w // 2, w // 2)
        return
    # a diagonal is cut level at both nodes (its width w across it), so it stays between
    # z 0 and dz like the floors it spans
    L = (dx * dx + dz * dz) ** 0.5
    hw = int(round(w / 2.0 * L / abs(dz)))
    ring = [(-hw, 0), (hw, 0), (dx + hw, dz), (dx - hw, dz)]
    prism(b, slot, ring, [], y0, y1, "y")


def gen_pod(p: dict, b: Buf) -> None:
    """A capsule pod filling a bay of one floor (w x h from z 0, its back in the reveal r),
    d out from the wall, with a porthole of radius pr on its front."""
    w, h, d, r, pr = p["w"], p["h"], p["d"], p["r"], p["pr"]
    x0, x1 = -w // 2 + 25, w // 2 - 25
    z0, z1 = 25, h - 25
    box(b, "pod", x0, x1, -d + 60, max(r - 10, -d + 120), z0, z1)
    zc = (z0 + z1) // 2
    hole = ngon(0, zc, pr, 16, 0.5)
    prism(b, "pod", [(x0, z0), (x1, z0), (x1, z1), (x0, z1)], [hole], -d, -d + 60, "y")
    prism(b, "glazing", ngon(0, zc, pr + 5, 16, 0.5), [], -d + 30, -d + 40, "y")
    prism(b, "pod", ngon(0, zc, pr + 70, 16, 0.5), [ngon(0, zc, pr - 5, 16, 0.5)], -d - 25,
          -d + 20, "y")


def gen_ac(p: dict, b: Buf) -> None:
    """A window AC unit on an opening's sill (z 0), d_out out and into the opening."""
    w, h, do, di = p["w"], p["h"], p["do"], p["di"]
    box(b, "ac", -w // 2, w // 2, -do, di, 0, h)
    box(b, "ac", -w // 2 + 40, w // 2 - 40, -do - 15, -do, 60, h - 60)


def gen_dish(p: dict, b: Buf) -> None:
    """A satellite dish on a wall bracket: a disc of radius rd facing out, its arm."""
    rd = p["rd"]
    zc = rd + 40
    box(b, "dish", -30, 30, -260, 0, zc - 30, zc + 30)
    prism(b, "dish", ngon(0, zc, rd, 10, 0.5), [], -330, -260, "y")


def gen_column(p: dict, b: Buf) -> None:
    """An arcade column under a cantilevered floor: w square, h tall, its outer face on the
    facade plane above (y 0 to w)."""
    box(b, "column", -p["w"] // 2, p["w"] // 2, 0, p["w"], 0, p["h"])


def gen_balconette(p: dict, b: Buf) -> None:
    """A French balcony railing across an opening's lower part (z 0 up to rh), 120 mm out."""
    w, rh = p["w"], p["rh"]
    x0, x1 = -w // 2 - 60, w // 2 + 60
    box(b, "railing", x0, x1, -140, -100, rh - 40, rh)
    box(b, "railing", x0, x1, -140, -100, 40, 80)
    n = max(2, w // 300 + 1)
    for j in range(n + 1):
        x = x0 + (x1 - x0 - 30) * j // n
        box(b, "railing", x, x + 30, -135, -105, 80, rh - 40)
    box(b, "railing", x0, x0 + 40, -100, 0, 40, 80)
    box(b, "railing", x1 - 40, x1, -100, 0, 40, 80)


def gen_canopy(p: dict, b: Buf) -> None:
    """A podium canopy: a slab L long and d deep off the wall, t thick, a fascia at its
    front edge (z 0 its underside)."""
    L, d, t = p["L"], p["d"], p["t"]
    box(b, "canopy", -L // 2, L // 2, -d, 0, 60, t - 60)
    box(b, "canopy", -L // 2, L // 2, -d, -d + 80, 0, t)


def gen_mast(p: dict, b: Buf) -> None:
    """A crown mast (a base and a shaft of three tapering lengths) or a spire (a base and a
    four-sided pyramid), h tall from the roof (z 0)."""
    h = p["h"]
    if p["style"] == "mast":
        box(b, "mast", -1200, 1200, -1200, 1200, 0, 1500)
        z = 1500
        for wd, frac in ((400, 40), (275, 35), (150, 25)):
            dz = (h - 1500) * frac // 100
            box(b, "mast", -wd, wd, -wd, wd, z, z + dz)
            z += dz
        return
    box(b, "mast", -1000, 1000, -1000, 1000, 0, 1000)
    r = 700
    base = [(-r, -r, 1000), (r, -r, 1000), (r, r, 1000), (-r, r, 1000)]
    apex = (0, 0, h)
    b.new_part()
    face(b, "mast", base, (0.0, 0.0, -1.0))
    for k in range(4):
        p0, p1 = base[k], base[(k + 1) % 4]
        n = _cross(_sub(p1, p0), _sub(apex, p0))
        L = (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) ** 0.5
        face(b, "mast", [p0, p1, apex], (n[0] / L, n[1] / L, n[2] / L))


GEN = {"window": gen_window, "cap": gen_cap, "spandrel": gen_spandrel,
       "balcony": gen_balcony, "louver": gen_louver, "fin": gen_fin, "shade": gen_shade,
       "shutter": gen_shutter, "grille": gen_grille, "panel": gen_panel,
       "member": gen_member, "pod": gen_pod, "ac": gen_ac, "dish": gen_dish,
       "column": gen_column, "balconette": gen_balconette, "canopy": gen_canopy,
       "mast": gen_mast}

# how far out of the wall a family may reach (the envelope check's allowance; scope 9):
# "flush" up to 0.16 m at any height (frames, sills, caps, shutters, grilles), "strip" up
# to 0.6 m at least 3 m up (fins, louvers, AC units, pods, screens, as AG1's cornices),
# "deep" up to 1.8 m at least 3 m up (balconies over a lot, a park or a sidewalk, never a lane)
REACH = {"window": "flush", "cap": "flush", "spandrel": "flush", "balcony": "deep",
         "louver": "flush", "fin": "strip", "shade": "strip", "shutter": "flush",
         "grille": "flush", "panel": "strip", "member": "flush", "pod": "strip",
         "ac": "strip", "dish": "strip", "column": "flush", "balconette": "flush",
         "canopy": "deep", "mast": "roof"}


TYPE_KEY: dict[str, str] = {}      # families whose type names one parameter (AG3's: use)
TYPE_SUB: dict[str, str] = {}      # and families with a fixed second word


def type_of(family: str, p: dict) -> str:
    """The part's semantic type (`part.window.casement`, `part.shopfront.bar`, scope
    principle 6)."""
    if family in TYPE_KEY:
        return f"part.{family}.{p[TYPE_KEY[family]]}"
    if family in TYPE_SUB:
        return f"part.{family}.{TYPE_SUB[family]}"
    sub = p.get("style") or {"cap": "mullion" if p.get("dir") == "v" else "transom",
                             "fin": "crown" if p.get("inward") else "vertical",
                             "member": "column" if p.get("dx") == 0 else
                             ("beam" if p.get("dz") == 0 else "diagonal"),
                             "louver": "panel", "shade": "blade", "shutter": "open",
                             "grille": "bars", "pod": "capsule", "ac": "window",
                             "dish": "satellite", "column": "arcade",
                             "balconette": "rail", "spandrel": "panel",
                             "canopy": "podium"}.get(family, "part")
    return f"part.{family}.{sub}"


def key_of(family: str, p: dict) -> str:
    return family + "|" + "|".join(f"{k}={p[k]}" for k in sorted(p))


def node_name(family: str, p: dict) -> str:
    h = hashlib.blake2b(f"{PARTS_VERSION}|{key_of(family, p)}".encode("utf-8"),
                        digest_size=5).hexdigest()
    return f"{type_of(family, p)}.h{h}"     # (a name ending in digits reads as a copy number)


_MESHES: dict[str, tuple] = {}


def mesh(family: str, p: dict) -> tuple[Buf, dict]:
    """(Buf, arrays) of one part, made once per process."""
    k = key_of(family, p)
    got = _MESHES.get(k)
    if got is None:
        b = Buf()
        GEN[family](p, b)
        got = (b, b.arrays())
        if len(_MESHES) > 20000:
            _MESHES.clear()
        _MESHES[k] = got
    return got


def bounds(arrs: dict):
    lo = hi = None
    for a in arrs.values():
        pl, ph = a["pos"].min(axis=0), a["pos"].max(axis=0)
        lo = pl if lo is None else lo.clip(max=pl)
        hi = ph if hi is None else hi.clip(min=ph)
    return lo.tolist(), hi.tolist()


# ---------------------------------------------------------------------------
# A building's parts
# ---------------------------------------------------------------------------

class PartSet:
    """The parts one building places: per part (family, parameters) its placements, each
    (x, y, z) mm in the building frame and the direction (cos, sin) of its yaw."""

    def __init__(self):
        self.defs: dict[str, tuple[str, dict]] = {}
        self.at: dict[str, list[tuple]] = {}

    def add(self, family: str, p: dict, x: int, y: int, z: int, ux: float, uy: float,
            extra_deg: int = 0) -> None:
        k = key_of(family, p)
        if k not in self.defs:
            self.defs[k] = (family, p)
            self.at[k] = []
        if extra_deg:
            c, s = float(M.cos(M.radians(extra_deg))), float(M.sin(M.radians(extra_deg)))
            ux, uy = ux * c - uy * s, ux * s + uy * c
        self.at[k].append((int(x), int(y), int(z), ux, uy))

    def on(self, fa, family: str, p: dict, s: int, z: int, y: int = 0,
           extra_deg: int = 0) -> None:
        """Place at s along facade `fa` (its `P`, `ux`, `uy`), height z, y into the wall."""
        x0, y0, _ = fa.P(s, z)
        self.add(family, p, x0 - int(round(fa.nx * y)), y0 - int(round(fa.ny * y)), z,
                 fa.ux, fa.uy, extra_deg)

    def count(self) -> int:
        return sum(len(v) for v in self.at.values())


def yaw_deg(ux: float, uy: float) -> float:
    d = round(float(M.degrees(M.atan2(uy, ux))), 2)
    return 0.0 if d == 0.0 else d


def place(arrs: dict, x: int, y: int, z: int, ux: float, uy: float) -> dict:
    """A part's arrays moved to a placement: positions rotated by (ux, uy) and rounded to
    the millimeter (IEEE products and sums in a fixed order)."""
    import numpy as np
    out = {}
    for name, a in arrs.items():
        pos = a["pos"].astype(np.float64)
        px = pos[:, 0] * ux - pos[:, 1] * uy
        py = pos[:, 0] * uy + pos[:, 1] * ux
        P = np.stack([np.rint(px).astype(np.int64) + x, np.rint(py).astype(np.int64) + y,
                      a["pos"][:, 2] + z], axis=1)
        out[name] = dict(a, pos=P)
    return out


def survives(arrs: dict, at: tuple) -> bool:
    """Whether a part keeps every triangle when turned to a placement and rounded to the
    millimeter (a thin sliver may fold flat; such a part stays an instance)."""
    import numpy as np
    for a in place(arrs, *at).values():
        pos, t = a["pos"], a["tri"]
        e1, e2 = pos[t[:, 1]] - pos[t[:, 0]], pos[t[:, 2]] - pos[t[:, 0]]
        c = np.stack([e1[:, 1] * e2[:, 2] - e1[:, 2] * e2[:, 1],
                      e1[:, 2] * e2[:, 0] - e1[:, 0] * e2[:, 2],
                      e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]], axis=1)
        if (c == 0).all(axis=1).any():
            return False
    return True


def merge_into(buf: Buf, part: Buf, arrs: dict, at: tuple) -> None:
    """Bake one placement of a part into the shell's buffer: its planes turned, each of its
    faces added at once, each of its closed pieces a new part of the shell."""
    import numpy as np
    x, y, z, ux, uy = at
    moved = place(arrs, x, y, z, ux, uy)
    pl_map: dict[int, int] = {}
    piece: dict[int, int] = {}
    for name in sorted(moved):
        a = moved[name]
        tri = a["tri"]
        pids = a["pl"][tri[:, 0]]
        key = a["part"] * (1 << 32) + pids
        _, first = np.unique(key, return_index=True)
        pos = a["pos"].tolist()
        for t0 in sorted(first.tolist()):
            pc, pid = int(a["part"][t0]), int(pids[t0])
            T = tri[key == key[t0]]
            vs = np.unique(T).tolist()
            loc = {v: k for k, v in enumerate(vs)}
            if pid not in pl_map:
                P = part.planes[pid]
                n = (P[0] * ux - P[1] * uy, P[0] * uy + P[1] * ux, P[2])
                o = (P[3] * ux - P[4] * uy + x, P[3] * uy + P[4] * ux + y, P[5] + z)
                ua = (P[6] * ux - P[7] * uy, P[6] * uy + P[7] * ux, P[8])
                va = (P[9] * ux - P[10] * uy, P[9] * uy + P[10] * ux, P[11])
                pl_map[pid] = buf.plane(n, o, ua, va, P[12], P[13])
            if pc not in piece:
                piece[pc] = buf.new_part()
            buf.part = piece[pc]
            buf.add(name, pl_map[pid], [tuple(pos[v]) for v in vs],
                    [loc[v] for v in T.reshape(-1).tolist()])


def check_mesh(arrs: dict) -> dict:
    return MB.check(arrs)


# AG3: the street-front families (shopfronts, doors, mounts...) join the kit
from . import frontparts  # noqa: E402,F401
# AG4: roof equipment and facade details
from . import roofparts  # noqa: E402,F401
