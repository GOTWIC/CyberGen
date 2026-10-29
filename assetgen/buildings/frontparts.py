"""Street-front parts (scope 5.1.3, AG3): shopfronts by use, entrance doors (main, service,
loading docks, roll-up doors, garage mouths, gates), queue rails, wall mounts (plates,
trellises, scaffold ties), downpipes and painted wall surfaces (murals, graffiti).

Each is a part like AG2's (`parts.py`: generated in its own frame from quantized
parameters, named by their hash, merged into its building or instanced): x along the
facade (centered on the opening), y into the wall (the facade plane at y = 0, outward
negative), z up from the opening's foot. The shell cuts the opening (`fronts.py`: a notch
down to the pavement for shopfronts and doors, its pane `r` behind the facade); these
fill it. Everything at street level stays inside the opening's recess or within
`parts.REACH` "flush" (0.16 m) of the wall, except the queue rail ("street": on a street
or avenue sidewalk, at most 0.8 m out and 1.2 m high) and the entrance canopy ("deep", 3 m
up at least). Nothing goes below the opening's foot (the pavement).

Shopfronts by use (one per ground-floor unit; `use` in the type, `part.shopfront.bar`):

| use | what it is |
|---|---|
| food | glazing over a riser, a counter ledge inside a deep recess, a lit menu board |
| bar | dark glazing (the shell's pane), a neon frame round it |
| club | a blank dark panel with a door, a neon line on top (a canopy and a queue rail beside, `fronts.py`) |
| arcade | an open front (a dark pane) with lit game cabinets, the shutter rolled up |
| cyberware, clinic | a white frame, a lit riser, frosted glass (clinic) |
| pawn | grilles, a shutter half down, a barred door |
| convenience | full glazing on a low riser, posters inside the glass |
| laundromat | wide windows on a high riser, few mullions |
| lobby | tall glazing without a riser, a transom, double doors or a revolving door in a deep recess |
"""

from __future__ import annotations

from . import parts as PT
from .parts import box, frame_y, ngon, prism

OV = PT.OVERLAP


def _door_leaf(b, style: str, slot: str, x0: int, x1: int, z0: int, z1: int, y0: int,
               y1: int) -> None:
    """One door leaf from x0 to x1, z0 to z1, y0 to y1: a glazed leaf (a frame on the
    pane behind, a push bar), a panel leaf (a box with a kick plate) or a barred one."""
    if style == "glass":
        frame_y(b, slot, x0, x1, z0, z1, 70, y0, y1)
        box(b, slot, x0 + 70, x1 - 70, y0 - 12, y0, z0 + 950, z0 + 1010)
    elif style == "barred":
        frame_y(b, slot, x0, x1, z0, z1, 60, y0, y1)
        n = max(2, (x1 - x0) // 120)
        for j in range(1, n):
            x = x0 + (x1 - x0) * j // n
            box(b, slot, x - 10, x + 10, y0 + 5, y0 + 25, z0 + 60, z1 - 60)
        box(b, slot, x0 + 60, x1 - 60, y0 + 5, y0 + 25, (z0 + z1) // 2 - 15, (z0 + z1) // 2 + 15)
    else:
        box(b, slot, x0, x1, y0, y1, z0, z1)
        box(b, "frame", x0 + 40, x1 - 40, y0 - 8, y0, z0, z0 + 250)
        box(b, "frame", x1 - 140 if x1 - x0 > 600 else x0 + 60,
            x1 - 100 if x1 - x0 > 600 else x0 + 100, y0 - 40, y0, z0 + 950, z0 + 1150)


def gen_shopfront(p: dict, b) -> None:
    w, h, r = p["w"], p["h"], p["r"]
    use = p["use"]
    fw, fs = p["fw"], p["frame"]
    hw = w // 2
    y1 = r - 3
    y0 = max(r - 70, 6)
    dx, dw, dh = p["dx"], p["dw"], p["dh"]
    d0, d1 = dx - dw // 2, dx + dw // 2           # the door opening
    riser = p["riser"]
    tr = p["tr"]
    # the frame round the opening (from the pavement: nothing below it), the door's jambs
    # and head
    prism(b, fs, [(-hw - OV, 0), (hw + OV, 0), (hw + OV, h + OV), (-hw - OV, h + OV)],
          [[(-hw + fw, fw), (hw - fw, fw), (hw - fw, h - fw), (-hw + fw, h - fw)]],
          y0, y1, "y")
    for x in (d0, d1):
        box(b, fs, x - fw // 2, x + fw // 2, y0, y1, fw, dh)
    box(b, fs, max(d0 - fw // 2, -hw + fw), min(d1 + fw // 2, hw - fw), y0, y1, dh,
        dh + fw)
    # the glazed bays either side of the door: riser, mullions, transom
    sides = [(-hw + fw, d0 - fw // 2), (d1 + fw // 2, hw - fw)]
    for xa, xb in sides:
        if xb - xa < 200:
            continue
        if use == "club":
            box(b, p["panel"], xa, xb, r - 40, r - 3, fw, h - fw)
            continue
        if riser:
            box(b, p["rslot"], xa, xb, max(r - 140, 4), r - 2, fw, riser)
            box(b, fs, xa, xb, y0, y1, riser, riser + fw)
        n = p["mull"]
        for j in range(1, n + 1):
            x = xa + (xb - xa) * j // (n + 1)
            box(b, fs, x - fw // 3, x + fw // 3, y0 + 10, y1, riser + fw, h - fw)
        if tr and tr > riser + 600:
            box(b, fs, xa, xb, y0 + 10, y1, tr - fw // 3, tr + fw // 3)
    # the door
    style = p["door"]
    slot = p["dslot"]
    if style == "revolve":
        _revolving(b, dx, dw, dh)
    elif dw >= 1500:
        _door_leaf(b, style, slot, d0 + fw // 2, dx - 10, 0, dh, y0 - 10, y0 + 40)
        _door_leaf(b, style, slot, dx + 10, d1 - fw // 2, 0, dh, y0 - 10, y0 + 40)
    else:
        _door_leaf(b, style, slot, d0 + fw // 2, d1 - fw // 2, 0, dh, y0 - 10, y0 + 40)
    # by use
    if use == "food" and p.get("counter"):
        xa, xb = sides[p["counter"] - 1]
        if xb - xa >= 900 and r >= 300:
            box(b, "sill", xa, xb, 4, r - 72, 1000, 1060)
            box(b, "frame", xa + 60, xa + 120, r - 300, r - 72, 0 + max(riser, 300), 1000)
            if tr:
                box(b, "lit_menu", xa + 80, xb - 80, r - 24, r - 6, tr + 80, h - fw - 60)
    if p.get("neon"):
        # a neon frame inside the opening, round the glazing
        t, yn0, yn1 = 30, max(r - 110, 5), max(r - 80, 35)
        ns = p["neon"]
        for xa, xb in sides:
            if xb - xa < 400:
                continue
            za, zb = max(riser, 0) + fw + 80, h - fw - 80
            box(b, ns, xa + 60, xb - 60, yn0, yn1, za, za + t)
            box(b, ns, xa + 60, xb - 60, yn0, yn1, zb - t, zb)
            box(b, ns, xa + 60, xa + 60 + t, yn0, yn1, za + t, zb - t)
            box(b, ns, xb - 60 - t, xb - 60, yn0, yn1, za + t, zb - t)
    if use == "club":
        box(b, p.get("neon") or "neon_ff2a6d", -hw + fw, hw - fw, max(r - 60, 5), r - 45,
            h - fw - 60, h - fw - 30)
    if use == "arcade":
        n = p.get("screens", 0)
        for xa, xb in sides:
            if xb - xa < 900 or r < 260:
                continue
            m = max(1, min(n, (xb - xa) // 750))
            for j in range(m):
                cx = xa + (xb - xa) * (2 * j + 1) // (2 * m)
                box(b, "cabinet", cx - 300, cx + 300, r - 220, r - 6, 0, 1650)
                box(b, p["screen"], cx - 230, cx + 230, r - 232, r - 220, 950, 1450)
    if p.get("lightbox") and riser >= 300:
        for xa, xb in sides:
            if xb - xa >= 400:
                box(b, "lit_white", xa + 40, xb - 40, max(r - 152, 2), max(r - 140, 14),
                    80, riser - 60)
    if p.get("frost"):
        ft = p["frost"]
        for xa, xb in sides:
            if xb - xa >= 400:
                box(b, "frosted", xa + 20, xb - 20, r - 14, r - 4, riser + fw, ft)
    for px, pz, pw, ph, slot in p.get("posters") or ():
        box(b, slot, px - pw // 2, px + pw // 2, r - 16, r - 8, pz, pz + ph)
    # shutter box (inside the recess, at the head) and its curtain
    sh = p.get("shutter", "none")
    if sh != "none" and r >= 230:
        ys0, ys1 = max(5, r - 300), r - 80
        box(b, "rollup", -hw + fw, hw - fw, ys0, ys1, h - fw - 260, h - fw)
        if sh in ("half", "down"):
            for xa, xb in sides:
                if xb - xa < 400:
                    continue
                zs = max(riser + fw, (h - fw - 260) // 2) if sh == "half" else riser + fw
                box(b, "rollup", xa, xb, ys0 + 30, ys0 + 50, zs, h - fw - 260)
                z = zs + 40
                while z < h - fw - 300:
                    box(b, "rollup", xa, xb, ys0 + 22, ys0 + 30, z, z + 20)
                    z += 160
    if p.get("grille") and r >= 160:
        for xa, xb in sides:
            if xb - xa < 400:
                continue
            za, zb = riser + fw, h - fw
            yg0, yg1 = max(r - 135, 8), max(r - 115, 28)
            box(b, "grille", xa, xb, yg0, yg1, za, za + 40)
            box(b, "grille", xa, xb, yg0, yg1, zb - 40, zb)
            nb = max(2, (xb - xa) // 140)
            for j in range(1, nb):
                x = xa + (xb - xa) * j // nb
                box(b, "grille", x - 9, x + 9, yg0 + 2, yg1 - 2, za + 40, zb - 40)
    # the fascia over the opening (where an awning and a facade sign hang)
    fz = p.get("fz", 0)
    if fz:
        fx = p.get("fx", 0)
        box(b, p["fslot"], -hw - fx, hw + fx, -p.get("fd", 40), 0, h + 30, h + 30 + fz)


def _revolving(b, dx: int, dw: int, dh: int) -> None:
    """A revolving door: a glazed drum of radius dw / 2 in the recess (its front 40 mm
    behind the facade), open toward the street and the lobby, a canopy disc on it, two
    crossed wings."""
    R = dw // 2
    cy = 40 + R
    ring_o = ngon(dx, cy, R, 16, 0.5)
    ring_i = ngon(dx, cy, R - 30, 16, 0.5)
    for k0, k1 in ((3, 6), (11, 14)):
        for k in range(k0, k1):
            prism(b, "glazing", [ring_o[k], ring_o[k + 1], ring_i[k + 1], ring_i[k]], [], 0,
                  dh, "z")
    prism(b, "frame", ngon(dx, cy, R + 60, 16, 0.5), [], dh, dh + 220, "z")
    box(b, "frame", dx - R + 60, dx + R - 60, cy - 15, cy + 15, 0, dh)
    box(b, "frame", dx - 15, dx + 15, cy - R + 60, cy - 15, 0, dh)
    box(b, "frame", dx - 15, dx + 15, cy + 15, cy + R - 60, 0, dh)


def gen_door(p: dict, b) -> None:
    """An entrance door in its opening (w x h, the recess r): by `kind` a main entrance
    (one or two leaves, a transom, steps up inside a deep recess), a service door, a loading
    dock (a roll-up door, the leveler's lip, bumpers and a seal round it; the opening starts
    at the dock's height), a roll-up door at grade, a garage mouth (a height bar, a barrier
    arm, a grille half up, the dark garage behind) or a gate (a sliding gate of bars)."""
    kind, w, h, r = p["kind"], p["w"], p["h"], p["r"]
    hw = w // 2
    fw = p.get("fw", 70)
    y1 = r - 3
    y0 = max(r - 70, 6)
    slot = p.get("slot", "door_metal")
    if kind == "main":
        n, sh, sd = p.get("steps", 0), p.get("sh", 150), p.get("sd", 300)
        lift = n * sh
        for k in range(n):
            box(b, "step", -hw, hw, k * sd, r, k * sh, (k + 1) * sh)
        prism(b, "frame", [(-hw - OV, lift), (hw + OV, lift), (hw + OV, h + OV),
                           (-hw - OV, h + OV)],
              [[(-hw + fw, lift + fw), (hw - fw, lift + fw), (hw - fw, h - fw),
                (-hw + fw, h - fw)]], y0, y1, "y")
        dh = p["dh"]
        if dh + fw < h - fw:
            box(b, "frame", -hw + fw, hw - fw, y0, y1, dh, dh + fw)
        style = p.get("style", "glass")
        if p.get("leaves", 2) == 2:
            _door_leaf(b, style, slot, -hw + fw, -10, lift, dh, y0 - 10, y0 + 40)
            _door_leaf(b, style, slot, 10, hw - fw, lift, dh, y0 - 10, y0 + 40)
        else:
            _door_leaf(b, style, slot, -hw + fw, hw - fw, lift, dh, y0 - 10, y0 + 40)
        return
    if kind == "service":
        frame_y(b, "frame", -hw - OV, hw + OV, 0, h + OV, fw + OV, y0, y1)
        _door_leaf(b, "panel", slot, -hw + fw, hw - fw, 0, h - fw, y0 - 10, y0 + 40)
        return
    if kind in ("dock", "rollup"):
        # the roll-up door (slats on a panel), its guides and the housing at the head
        box(b, "rollup", -hw, hw, r - 60, r - 3, 0, h - 300)
        z = 120
        while z < h - 380:
            box(b, "rollup", -hw + 20, hw - 20, r - 72, r - 60, z, z + 30)
            z += 220
        box(b, "frame", -hw - OV, -hw + 80, max(r - 140, 4), r - 3, 0, h)
        box(b, "frame", hw - 80, hw + OV, max(r - 140, 4), r - 3, 0, h)
        box(b, "rollup", -hw - OV, hw + OV, max(r - 300, 4), r - 3, h - 300, h)
        if kind == "dock":
            # the leveler's lip at the sill, two bumpers under it, a seal round the opening
            box(b, "steel", -hw + 150, hw - 150, 4, min(r - 70, 400), -20, 0)
            for x in (-hw + 250, hw - 250):
                box(b, "rubber", x - 120, x + 120, -110, 0, -330, -80)
            t = 140
            box(b, "seal", -hw - t, -hw, -130, 0, -60, h + 60)
            box(b, "seal", hw, hw + t, -130, 0, -60, h + 60)
            box(b, "seal", -hw - t, hw + t, -130, 0, h, h + t)
        return
    if kind == "garage":
        # a height bar across the mouth, a barrier arm inside, a grille half up
        box(b, "frame", -hw - OV, -hw + 120, 4, 160, 0, h)
        box(b, "frame", hw - 120, hw + OV, 4, 160, 0, h)
        box(b, "paint_yellow", -hw + 120, hw - 120, 40, 120, h - 260, h - 180)
        if r >= 900:
            px = -hw + 400
            box(b, "paint_yellow", px - 120, px + 120, r - 500, r - 260, 0, 1050)
            box(b, "paint_white", px + 120, hw - 400, r - 420, r - 340, 900, 980)
        zg = h - 700
        box(b, "grille", -hw + 120, hw - 120, max(r - 160, 170), max(r - 130, 200), zg,
            h - 40)
        n = max(2, (w - 240) // 160)
        for j in range(1, n):
            x = -hw + 120 + (w - 240) * j // n
            box(b, "grille", x - 10, x + 10, max(r - 155, 175), max(r - 135, 195), zg - 120,
                zg)
        return
    if kind == "gate":
        # posts, a frame and vertical bars: a sliding gate
        box(b, "frame", -hw - OV, -hw + 140, 4, 160, 0, h)
        box(b, "frame", hw - 140, hw + OV, 4, 160, 0, h)
        yg0, yg1 = max(r - 80, 40), max(r - 40, 80)
        box(b, slot, -hw + 140, hw - 140, yg0, yg1, 60, 140)
        box(b, slot, -hw + 140, hw - 140, yg0, yg1, h - 220, h - 140)
        n = max(3, (w - 280) // 150)
        for j in range(1, n):
            x = -hw + 140 + (w - 280) * j // n
            box(b, slot, x - 15, x + 15, yg0 + 5, yg1 - 5, 140, h - 220)
        return
    raise ValueError(f"door kind {kind}")


def gen_rail(p: dict, b) -> None:
    """A queue rail on the sidewalk along the wall: posts every 1.2 m or less, a top rail,
    `out` in front of the facade, L long from x 0."""
    L, out = p["L"], p["out"]
    n = max(1, -(-L // 1200))
    for j in range(n + 1):
        x = L * j // n
        box(b, "stanchion", x - 30, x + 30, -out - 30, -out + 30, 0, 1000)
        box(b, "stanchion", x - 90, x + 90, -out - 90, -out + 90, 0, 30)
    box(b, "rope", 0, L, -out - 15, -out + 15, 880, 940)


def gen_mount(p: dict, b) -> None:
    """What a facade prop hangs on: a plate (wall lights, blade-sign arms, cable ends), a
    trellis for facade greenery (posts and wires 60 mm out on standoffs) or a scaffold tie
    (a plate and a short tube)."""
    st, w, h = p["style"], p["w"], p["h"]
    if st == "plate":
        box(b, "mount", -w // 2, w // 2, -25, 0, 0, h)
    elif st == "tie":
        box(b, "mount", -w // 2, w // 2, -20, 0, 0, h)
        box(b, "steel", -25, 25, -150, -20, h // 2 - 25, h // 2 + 25)
    elif st == "trellis":
        nx = max(2, w // 400)
        nz = max(2, h // 500)
        for j in range(nx + 1):
            x = -w // 2 + w * j // nx
            box(b, "trellis", x - 12, x + 12, -60, -36, 0, h)
            for k in (0, nz):
                z = h * k // nz
                box(b, "trellis", x - 8, x + 8, -36, 0, max(z - 30, 0), max(z - 30, 0) + 60)
        for k in range(1, nz):
            z = h * k // nz
            box(b, "trellis", -w // 2 - 12, w // 2 + 12, -56, -40, z - 8, z + 8)
    else:
        raise ValueError(f"mount style {st}")


def gen_pipe(p: dict, b) -> None:
    """A downpipe from the pavement to h: an eight-sided tube 110 mm across, 40 mm off the
    wall, brackets every 2 m, a shoe at the foot."""
    h = p["h"]
    prism(b, "pipe", ngon(0, -95, 55, 8, 0.5), [], 0, h, "z")
    z = 1500
    while z < h - 300:
        box(b, "pipe", -40, 40, -60, 0, z, z + 40)
        z += 2000
    box(b, "pipe", -70, 70, -155, -35, 0, 120)


def gen_surface(p: dict, b) -> None:
    """A painted surface on a blank wall, 8 mm proud: a mural (an ad painted on a fire
    wall, a rectangle) or graffiti (an irregular patch from its outline points)."""
    if p["style"] == "mural":
        box(b, p["slot"], -p["w"] // 2, p["w"] // 2, -8, 0, 0, p["h"])
        box(b, "fascia", -p["w"] // 2 - 120, p["w"] // 2 + 120, -12, 0, -120, 0)
        return
    ring = [tuple(q) for q in p["ring"]]
    prism(b, p["slot"], ring, [], -6, 0, "y")


FAMILIES = {"shopfront": gen_shopfront, "door": gen_door, "rail": gen_rail,
            "mount": gen_mount, "pipe": gen_pipe, "surface": gen_surface}
REACH = {"shopfront": "flush", "door": "flush", "rail": "street", "mount": "flush",
         "pipe": "flush", "surface": "flush"}
SUB = {"shopfront": "use", "door": "kind", "rail": None, "mount": "style", "pipe": None,
       "surface": "style"}


def register() -> None:
    """Add the street-front families to the part kit (`parts.GEN`, `REACH`)."""
    for k, g in FAMILIES.items():
        PT.GEN[k] = g
        PT.REACH[k] = REACH[k]
    PT.TYPE_KEY.update({k: v for k, v in SUB.items() if v})
    PT.TYPE_SUB.update({"rail": "queue", "pipe": "down"})


register()
