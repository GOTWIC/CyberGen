"""Halcyon Kite: a compact performance hatchback (both names made up), on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/halcyon_kite.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/halcyon_kite.py --out DIR --sheet

Halcyon's smallest car, a hot hatch: three doors, 2 + 2 seats, 4.05 m on a 2.64 m
wheelbase. The Vanta-R's, the Sable's and the Ridge's sibling (the dry weave spine from the
nose over the roof to the tail, octagonal bolted arches, the light strip under the nose lip
that turns down each corner, a ring of light round the tail, honeycomb, the scoop ahead of
the rear wheel, twin-spoke turbine wheels), with ideas of its own:

- The spine is a kite in plan: narrow at the nose, widest at the windshield's head, drawn
  in again to the tail, between body-colored pillars and roof rails.
- A chopped tail: the roof rails run on past the hatch glass to a fin that stands on the
  tail's corner, a blade between them, air under it. From the side the tail is cut off
  upright; from behind the glass lies deep between two fins.
- Box flares: the fenders stand 6 to 11 cm proud of the doors and end in a facet, an
  outlet under it behind the front wheel and the scoop under it ahead of the rear wheel.
  The doors between them are folded along a valley line that rises into the scoop.
- A blade across the mouth with the kite on its middle, two hexagonal beams a side on it.

The body is ten character lines over twelve stations, cut by the wheel wells and split
into panels; the nose strip and the tail ring are light channels cut into the caps' bands
under lenses, the handles, the charge flap and the fender slots are cut through the skin.
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                                  # noqa: E402
import cabin as C                                                   # noqa: E402
from brands import halcyon                                          # noqa: E402
from carkit import (Geo, Matrix, V3, my, on_body, pi, rad,         # noqa: E402
                    ribbon, shr, stud, text_flat, text_on_body)

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.31, -1.33            # axles: 2.64 m wheelbase
T_R, T_W, T_RIM = 0.345, 0.245, 0.262  # tire radius, width, rim radius
T_OUT = 0.905                       # outer face of the tires
ARCH = 0.41                         # wheel arch radius at its corners
ARCH_ANG = (-23, 22.5, 67.5, 112.5, 157.5, 203)     # half an octagon, its top flat
WELL_F, WELL_R = 0.52, 0.625        # the wells' inner walls (y)
SUBDIV = 3

# ---------------------------------------------------------------------------------------
# body: stations and character lines
# ---------------------------------------------------------------------------------------
LINES = "CPHGSUMRFB"
#        C centerline top, P spine edge / roof rail inner edge, H hood crease / rail outer
#        edge, G fender inner / beltline, S shoulder crest, U waist line, M cladding line,
#        R rocker, F floor edge, B floor
ORDER = ["N0", "N1", "A2", "A3", "W0", "RF", "BP", "SC", "RA", "RE", "HB", "T1"]
PT = {}
STATIONS = []


def stations():
    T = {
        "N0": [(2.01, 0, .60), (2.005, .24, .60), (1.98, .52, .596), (1.95, .68, .59),
               (1.895, .80, .575), (1.875, .85, .48), (1.875, .855, .33), (1.895, .83, .205),
               (1.955, .58, .17), (1.99, 0, .17)],
        "N1": [(1.82, 0, .662), (1.815, .26, .667), (1.80, .55, .684), (1.785, .70, .712),
               (1.765, .845, .72), (1.75, .89, .57), (1.75, .885, .33), (1.76, .86, .16),
               (1.78, .62, .13), (1.82, 0, .13)],
        "A2": [(1.31, 0, .758), (1.31, .32, .765), (1.31, .62, .79), (1.31, .76, .825),
               (1.31, .905, .838), (1.31, .93, .67), (1.31, .92, .33), (1.31, .90, .16),
               (1.31, .66, .13), (1.31, 0, .13)],
        "A3": [(.93, 0, .84), (.93, .46, .846), (.93, .675, .858), (.90, .775, .874),
               (.88, .895, .866), (.865, .915, .64), (.865, .905, .33), (.87, .90, .16),
               (.87, .67, .13), (.87, 0, .13)],
        "W0": [(.84, 0, .872), (.80, .62, .879), (.735, .75, .894), (.72, .785, .878),
               (.79, .855, .868), (.80, .80, .60), (.80, .855, .33), (.74, .905, .16),
               (.72, .68, .13), (.72, 0, .13)],
        "RF": [(-.02, 0, 1.30), (-.04, .555, 1.29), (-.10, .645, 1.265)] + [None] * 7,
        "BP": [(-.56, 0, 1.325), (-.56, .555, 1.313), (-.60, .66, 1.285), (-.54, .795, .955),
               (-.56, .86, .925), (-.54, .80, .72), (-.54, .855, .34), (-.56, .905, .17),
               (-.56, .69, .13), (-.56, 0, .13)],
        "SC": [None, None, None, (-.68, .805, .965), (-.66, .90, .935), (-.64, .935, .73),
               (-.64, .925, .36), (-.65, .91, .17), (-.65, .69, .13), (-.65, 0, .13)],
        "RA": [(-1.33, 0, 1.29), (-1.33, .535, 1.278), (-1.42, .632, 1.247),
               (-1.26, .787, .98), (-1.33, .905, .955), (-1.33, .94, .80), (-1.33, .925, .36),
               (-1.33, .90, .18), (-1.33, .68, .14), (-1.33, 0, .14)],
        "RE": [(-1.62, 0, 1.26), (-1.62, .515, 1.248), (-1.63, .615, 1.22),
               (-1.66, .775, .985), (-1.68, .89, .955), (-1.68, .93, .78), (-1.68, .915, .42),
               (-1.68, .885, .22), (-1.68, .67, .17), (-1.68, 0, .17)],
        "HB": [(-1.92, 0, .985), (-1.92, .49, .98), (-1.925, .61, .972), (-1.93, .765, .955),
               (-1.93, .874, .925), (-1.93, .905, .76), (-1.93, .895, .46), (-1.93, .865, .30),
               (-1.93, .64, .25), (-1.93, 0, .25)],
        "T1": [(-2.03, 0, .945), (-2.03, .42, .943), (-2.025, .62, .935), (-2.01, .77, .915),
               (-1.99, .845, .87), (-1.975, .865, .74), (-1.975, .86, .52), (-1.99, .825, .41),
               (-2.02, .60, .375), (-2.04, 0, .375)],
    }
    for j in range(3, 10):
        T["RF"][j] = V3(T["W0"][j]).lerp(V3(T["BP"][j]), 0.60)
    for j in range(0, 3):
        T["SC"][j] = V3(T["BP"][j]).lerp(V3(T["RA"][j]), 0.13)
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    STATIONS[:] = S
    return S


PMAT = dict(spine="carbon_dry", hood="paint", roof="carbon_dry", bumper_f="paint",
            fender_f="paint", door="paint", side="paint", bumper_r="paint",
            glass_ws="glass", glass_rear="glass", glass_door="glass", glass_q="glass",
            trim_d="frit", trim_q="frit", trim_r="frit", wstrim="gloss_black",
            sill="cladding", floor="underbody",
            mouth="void", mouth_frame="cladding", lightband="gloss_black",
            tail="void", tail_frame="cladding", scoop="void", vent="void", well="well",
            lamp_f="lamp_housing", lens_f="lens_clear", lamp_r="lamp_housing",
            lens_r="lens_red", cut="void", slit="void")
FRONT_C = V3((2.00, 0, 0.385))      # middle of the mouth
REAR_C = V3((-2.03, 0, 0.66))       # middle of the tail panel
BAND_W = 0.055                      # the light bands round the mouth and the tail
GAP = 0.00175                       # 3.5 mm shut lines
MOUTH_D, TAIL_D = 0.18, 0.11
LAMP_F_W, LAMP_F_D = 0.036, 0.040   # the front light channel: width, depth
LAMP_R_W, LAMP_R_D = 0.042, 0.026   # the tail ring's channel: most of the band's width
LAMP = {}                           # the light channels' paths on the skin
CHAN_STEP = 0.02                    # their sections' spacing
LAMP_STEP = 0.08                    # the lamps' sections in them
CAPS = {}


def panel_of(i, j):
    if j >= 7:
        return "floor"
    if j == 6:
        return "sill"
    if j == 0:                      # the middle: spine, windshield, roof, hatch, spine
        return ("spine", "spine", "spine", "spine", "glass_ws", "roof", "roof", "roof",
                "roof", "glass_rear", "spine")[i]
    if i == 0:
        return "bumper_f"
    if j == 1:                      # hood, then the hoop: pillars and roof rails
        return "hood" if i <= 3 else "side"
    if i <= 3:
        return "fender_f"
    if j == 2:
        return "glass_door" if i <= 5 else "glass_q" if i <= 7 else "side"
    if j == 5 and i >= 9:
        return "bumper_r"
    if i <= 5:
        return "door"
    if i == 6 and j == 5:
        return "scoop"
    return "side"


def line_crease(i, j):
    """Crease of the edge along line j from station i to i + 1."""
    if j in (0, 9):
        return 0.0
    if j == 1:
        return 1.0
    if j == 2:
        return 1.0 if i <= 9 else 0.7
    if j == 3:
        return 0.7 if i <= 3 else 1.0 if i <= 8 else 0.6
    if j == 4:
        return 1.0
    if j == 5:
        return 1.0 if 3 <= i <= 6 else 0.7
    return 1.0


def station_crease(i, j):
    """Crease of the edge on station i between lines j and j + 1."""
    if i in (0, 11):
        return 1.0
    if i == 3:
        return 0.8 if j == 4 else 1.0 if j == 5 else 0.0
    if i == 4:
        return 1.0 if j <= 2 or j == 5 else 0.7 if j == 4 else 0.0
    if i == 5:
        return 1.0 if j == 0 else 0.4 if j == 1 else 0.0
    if i == 6:
        return 1.0 if j == 5 else 0.5 if j == 4 else 0.0
    if i == 7:
        return 1.0 if j == 5 else 0.6 if j in (4, 6) else 0.0
    if i == 8:
        return 1.0 if j == 2 else 0.0
    if i == 9:
        return 1.0 if j == 0 else 0.6 if j <= 2 else 0.0
    if i == 10:
        return 1.0 if j == 0 else 0.6 if j <= 2 else 0.0
    if i == 1:
        return 0.5 if j <= 4 else 0.0
    return 0.0


def band_mid(i, center):
    """The middle line of the light band round an end of the body (station i), line by
    line: the band is BAND_W wide all round, square to the lip."""
    ring = [type("P", (), dict(co=V3(p)))() for p in STATIONS[i]]
    off = K._even_band(ring, center, BAND_W, True, False)
    return [V3(p) + o * 0.5 for p, o in zip(STATIONS[i], off)]


def cutters():
    """Everything cut into the hull, laid on it while it stands uncut: the wheel wells, the
    light channels under their lenses, the handles' and the charge flap's shut lines."""
    wells = Geo()
    K.well_cutter(wells, FA_X, T_R, ARCH, WELL_F, ARCH_ANG)
    K.well_cutter(wells, RA_X, T_R, ARCH, WELL_R, ARCH_ANG)
    # front: a channel in the band under the nose lip, from the spine's edge out, turning
    # down the corner
    mid = band_mid(0, FRONT_C)
    front = Geo()
    LAMP["front"] = K.groove(front, [mid[1].lerp(mid[2], 0.10), mid[2], mid[3],
                                     mid[3].lerp(mid[4], 0.65), mid[4].lerp(mid[5], 0.40),
                                     mid[5], mid[5].lerp(mid[6], 0.85)],
                             width=LAMP_F_W, depth=LAMP_F_D, mirror=True, step=CHAN_STEP)
    # rear: the ring, one channel round the whole tail, rounded first and traced on its own
    # points (both sides take the same sections), its way out held aft; its lens is built
    # apart on the skin's normals there
    mid = band_mid(-1, REAR_C)
    path = K.chaikin((mid[0:10] + [my(p) for p in mid[8:0:-1]])[::-1], 3, closed=True)
    LAMP["rear.skin"] = [(q, n if n.x < 0 else -n)
                         for q, n in K.trace(path, None, True, 1.0)]
    rear = Geo()
    LAMP["rear"] = K.groove(rear, path, width=LAMP_R_W, depth=LAMP_R_D, closed=True,
                            up=(-1, 0, 0), step=1.0)
    # shut lines: a flush handle in each door, the hexagonal charge flap on each quarter
    cut = Geo()
    K.groove(cut, K.rounded(-0.36, 0.835, 0.15, 0.022), 'y', closed=True, mirror=True)
    K.groove(cut, K.ngon(-1.50, 0.868, 0.044, 6, 30), 'y', closed=True, mirror=True)
    # slots over the front wheels
    slits = Geo()
    for k in range(4):
        x = 1.47 - k * 0.07
        K.pocket(slits, [(x + 0.008, 0.80), (x - 0.014, 0.885), (x - 0.032, 0.885),
                         (x - 0.010, 0.80)], 'z', depth=0.02, mirror=True)
    return [(wells, "well"), (front, "lamp_f", "skin", "lens_f"), (rear, "lamp_r"),
            (cut, "cut", "drop"), (slits, "slit")]


def build_hull():
    body = K.build_body(
        stations(), panel_of, PMAT, line_crease, station_crease,
        front=dict(center=FRONT_C, depth=MOUTH_D, band=BAND_W, band_panel="lightband",
                   band_lines=6, frame="mouth_frame", inner="mouth", even=True),
        rear=dict(center=REAR_C, depth=TAIL_D, band=BAND_W, band_panel="lightband",
                  band_lines=9, frame="tail_frame", inner="tail", even=True),
        recesses=[(2, 1, 0.07, 0.03),       # hood extractors, one each side of the spine
                  (3, 5, 0.03, 0.03)],      # the outlet behind the front wheel
        glass=[("glass_ws", 0.03, "wstrim", "frame"), ("glass_door", 0.024, "trim_d", "frit"),
               ("glass_q", 0.024, "trim_q", "frit"), ("glass_rear", 0.03, "trim_r", "frit")],
        cutters=cutters, subdiv=SUBDIV, gap=GAP)
    CAPS["mouth"], CAPS["tail"] = body.caps["front"], body.caps["rear"]


# ---------------------------------------------------------------------------------------
# helpers of this car
# ---------------------------------------------------------------------------------------
def zb(x, y):
    """Height of the body as built under (x, y)."""
    loc, _ = on_body(x, y, 'z')
    return loc.z if loc is not None else 0.0


def loft(g, secs):
    """A solid through sections of the same number of points (each a closed ring), its
    ends capped."""
    m = len(secs[0])
    vs = [V3(p) for sec in secs for p in sec]
    fs = []
    for i in range(len(secs) - 1):
        for j in range(m):
            j2 = (j + 1) % m
            fs.append((i * m + j, i * m + j2, (i + 1) * m + j2, (i + 1) * m + j))
    fs += [tuple(range(m)), tuple((len(secs) - 1) * m + j for j in range(m))]
    g.add(vs, fs)


def honey_patch(g, quad, R, wall, depth, lift=0.003, margin=0.012):
    """Honeycomb on a four-cornered patch (p00, p10, p11, p01: along its foot, then its
    head the same way), standing off it to the side its corners' order gives."""
    p00, p10, p11, p01 = [V3(p) for p in quad]
    L = ((p10 - p00).length + (p11 - p01).length) / 2
    H = ((p01 - p00).length + (p11 - p10).length) / 2
    h = Geo()
    h.honeycomb([(margin, margin), (L - margin, margin), (L - margin, H - margin),
                 (margin, H - margin)], 0.0, R, wall, depth, 1)

    def at(s, t):
        return p00.lerp(p10, s).lerp(p01.lerp(p11, s), t)
    vs = []
    for v in h.v:
        s, t = v.y / L, v.z / H
        e = 0.01
        n = (at(s + e, t) - at(s - e, t)).cross(at(s, t + e) - at(s, t - e)).normalized()
        vs.append(at(s, t) + n * (v.x + lift))
    g.add(vs, h.f)


def along(tr, s0=0.0, s1=None, step=0.03):
    """Frames every step along a traced path between the lengths s0 and s1:
    [(point, normal, tangent, side)], side = tangent x normal."""
    P = [q for q, _ in tr]
    S = [0.0]
    for a, b in zip(P, P[1:]):
        S.append(S[-1] + (b - a).length)
    s1 = S[-1] if s1 is None else min(s1, S[-1])
    n = max(1, int(round((s1 - s0) / step)))
    out, i = [], 0
    for k in range(n + 1):
        s = s0 + (s1 - s0) * k / n
        while i < len(S) - 2 and S[i + 1] < s:
            i += 1
        t = (s - S[i]) / max(S[i + 1] - S[i], 1e-9)
        tg = (P[i + 1] - P[i]).normalized()
        nn = tr[i][1].lerp(tr[i + 1][1], t).normalized()
        out.append((P[i].lerp(P[i + 1], t), nn, tg, tg.cross(nn).normalized()))
    return out


def run_len(tr):
    return sum((b[0] - a[0]).length for a, b in zip(tr, tr[1:]))


def on_spine_edge(x):
    """y of the spine's edge at x (the P line as drawn)."""
    return halcyon.on_spine_edge(x, pt=PT, order=ORDER, inset=0.0, miss=0.2)


# ---------------------------------------------------------------------------------------
# details on the body
# ---------------------------------------------------------------------------------------
def build_lamps():
    """What stands in the light channels, under their lenses: lit bars right under the
    lenses, swept on sparse sections."""
    fr = along(LAMP["front"], 0.012, run_len(LAMP["front"]) - 0.012, LAMP_STEP)
    L = K.Lamp("lamp.front", lit="led_front")
    L.bar([q - n * 0.006 - sd * 0.0105 for q, n, _, sd in fr], 0.012, 0.003,
          up=[n for _, n, _, _ in fr])
    L.obj(mirror=True)

    # rear: the ring, a red bar round the whole tail right under the lens over a chrome
    # floor, built on the left half from the top's middle round to the bottom's, mirrored
    def left_half(tr):
        rr = along(tr, 0.0, run_len(tr), LAMP_STEP)
        i0 = next(i for i in range(len(rr)) if rr[i][0].y >= 0 > rr[i - 1][0].y)
        rr = rr[i0:] + rr[:i0]
        rr = rr[:next(i for i in range(len(rr)) if rr[i][0].y < 0)]
        ends = [V3((q.x, 0.0, q.z)) for q in (rr[0][0], rr[-1][0])]
        return ([ends[0]] + [q for q, _, _, _ in rr] + [ends[1]],
                [rr[0][1]] + [n for _, n, _, _ in rr] + [rr[-1][1]])
    P, ups = left_half(LAMP["rear"])
    S, sn = left_half(LAMP["rear.skin"])
    L = K.Lamp("lamp.rear", lit="led_rear", glass="lens_red")
    hw = LAMP_R_W / 2 - GAP
    L.glass.sweep(S, [(-hw, -0.003), (hw, -0.003), (hw, 0.0), (-hw, 0.0)], up=sn)
    L.chrome.sweep([q - n * (LAMP_R_D - 0.003) for q, n in zip(P, ups)],
                   [(-0.018, -0.001), (0.018, -0.001), (0.018, 0.001), (-0.018, 0.001)],
                   up=ups)
    L.bar([q - n * 0.006 for q, n in zip(P, ups)], 0.024, 0.003, up=ups)
    L.obj(mirror=True)


def build_front():
    build_lamps()
    xb = FRONT_C.x - MOUTH_D
    rot = Matrix.Rotation(-pi / 2, 4, 'Z')

    # ---- the blade across the mouth, following the nose's plan; the kite on its middle
    le = [(1.988, 0.0), (1.984, 0.24), (1.957, 0.52), (1.925, 0.68), (1.893, 0.755)]
    zc = 0.405
    g = Geo()
    loft(g, [[(x, y, zc - 0.007), (x, y, zc + 0.007), (xb + 0.016, y, zc + 0.024),
              (xb + 0.016, y, zc - 0.03)] for x, y in le])
    g.obj("mouth.blade", "paint", bevel=0.003, mirror=True)
    g = Geo()
    g.prism([(1.992, 0.0, zc + 0.062), (1.992, 0.062, zc + 0.012), (1.992, 0.0, zc - 0.092),
             (1.992, -0.062, zc + 0.012)], (-0.03, 0, 0))
    g.obj("mouth.kite", "carbon", bevel=0.003)
    g = Geo()
    g.lathe([(0.0, 0.002), (0.0, 0.026), (0.005, 0.022), (0.005, 0.002)], 6,
            xf=Matrix.Translation((1.992, 0, zc + 0.006)) @ rot)
    g.obj("badge", "rim_bright", bevel=0.001)

    # ---- the beams: two hexagonal pods a side on the blade, a projector in each
    L = K.Lamp("beam", lit="lamp")
    g = Geo()
    for y, x in ((0.47, 1.925), (0.605, 1.90)):
        xf = Matrix.Translation((x, y, zc + 0.078)) @ rot
        g.lathe([(-0.10, 0.040), (-0.10, 0.052), (0.0, 0.052), (0.0, 0.045), (-0.014, 0.040)],
                6, xf=xf)
        L.projector((x - 0.014, y, zc + 0.078), (1, 0, 0), r=0.031, depth=0.05)
    g.obj("beam.pods", "gloss_black", bevel=0.002, mirror=True)
    L.obj(mirror=True)

    # ---- honeycomb in the middle and the upper slot, slats in the outer ducts
    half = [(p.y, p.z) for p in CAPS["mouth"]]
    poly = half + [(-y, z) for (y, z) in half[::-1]]
    g = Geo()
    g.honeycomb(poly, xb, 0.016, 0.003, 0.012, 1,
                keep=lambda y, z: abs(y) < 0.36 or z > zc + 0.03)
    g.obj("mouth.mesh", "grille")
    g = Geo()
    g.louvers((xb + 0.02, 0.385, zc - 0.035), (xb + 0.025, 0.40, 0.20),
              (xb + 0.03, 0.72, 0.215), (xb + 0.025, 0.74, zc - 0.035), 4, 0.05, 0.008,
              rad(28), out=(1, 0, 0), margin=0.05)
    g.obj("mouth.slats", "grille", bevel=0.002, mirror=True)
    g = Geo()                                           # the strakes between them
    g.prism([(1.965, 0.365, zc - 0.012), (1.98, 0.365, 0.175), (xb, 0.365, 0.18),
             (xb, 0.365, zc - 0.012)], (0, 0.012, 0))
    g.obj("mouth.strakes", "carbon", bevel=0.002, mirror=True)

    # ---- a tow strap on the right
    g = Geo()
    g.sweep([(xb + 0.01, -0.20, 0.245), (2.01, -0.20, 0.245), (2.04, -0.20, 0.232),
             (2.04, -0.20, 0.208), (2.01, -0.20, 0.195), (xb + 0.01, -0.20, 0.195)],
            [(-0.003, -0.014), (0.003, -0.014), (0.003, 0.014), (-0.003, 0.014)], up=(0, 1, 0))
    g.obj("tow.strap", "strap", bevel=0.001)
    # ---- splitter
    g = Geo()
    g.prism([(2.045, 0, 0.138), (2.03, 0.30, 0.138), (1.99, 0.60, 0.138),
             (1.925, 0.83, 0.138), (1.86, 0.905, 0.138), (1.74, 0.915, 0.138),
             (1.74, 0, 0.138)], (0, 0, 0.02))
    g.prism([(1.90, 0.895, 0.14), (1.875, 0.895, 0.25), (1.77, 0.895, 0.20),
             (1.75, 0.895, 0.14)], (0, 0.014, 0))
    g.obj("splitter", "carbon", bevel=0.003, mirror=True)


def build_rear():
    xt = REAR_C.x + TAIL_D
    # ---- honeycomb, the beam with the maker's name, plate, the twin outlets
    half = [(p.y, p.z) for p in CAPS["tail"]]
    poly = half + [(-y, z) for (y, z) in half[::-1]]

    def clear(y, z):
        return not (abs(z - 0.805) < 0.058) and not (abs(y) < 0.16 and abs(z - 0.62) < 0.07) \
            and not (abs(y) < 0.175 and abs(z - 0.485) < 0.07)
    g = Geo()
    g.honeycomb(poly, xt - 0.012, 0.02, 0.0034, 0.012, -1, keep=clear)
    g.obj("tail.mesh", "grille")
    g = Geo()
    g.prism([(-1.985, -0.74, 0.765), (-2.006, -0.74, 0.782), (-2.006, -0.74, 0.828),
             (-1.985, -0.74, 0.845), (-1.93, -0.74, 0.83), (-1.93, -0.74, 0.78)],
            (0, 1.48, 0))
    g.obj("tail.beam", "carbon", bevel=0.003)
    g = Geo()
    text_flat(g, "H A L C Y O N", 0.036, (-2.0072, 0, 0.805), (0, -1, 0), (0, 0, 1),
              spacing=1.35)
    g.obj("led.name", "led_rear")
    g = Geo()
    g.box((xt - 0.012, 0, 0.62), (0.012, 0.27, 0.095))
    g.obj("plate", "gloss_black", bevel=0.003)
    g = Geo()
    text_flat(g, "VB 61-357", 0.05, (xt - 0.0185, 0, 0.62), (0, -1, 0), (0, 0, 1), spacing=1.1)
    g.obj("plate.glyphs", "led_accent")
    g, ge = Geo(), Geo()
    for y in (0.082, -0.082):
        rz = Matrix.Translation((xt, y, 0.485)) @ Matrix.Rotation(pi / 2, 4, 'Z')
        g.lathe([(0, 0.058), (0.10, 0.058), (0.112, 0.052), (0.112, 0.046), (0, 0.046)], 6,
                xf=rz)
        g.lathe([(0, 0.070), (0.018, 0.070), (0.026, 0.060), (0, 0.060)], 6, xf=rz)
        g.lathe([(0.0, 0.002), (0.0, 0.046), (0.03, 0.046), (0.03, 0.002)], 6, xf=rz)
        ge.lathe([(0.031, 0.002), (0.031, 0.043), (0.034, 0.043), (0.034, 0.002)], 6, xf=rz)
    g.obj("exhaust", "rim", bevel=0.003)
    ge.obj("exhaust.glow", "ember")
    # ---- diffuser fins
    g = Geo()
    for y in (0.0, 0.21, 0.42, 0.63):
        g.prism([(-1.70, y - 0.007, 0.185), (-2.045, y - 0.007, 0.372),
                 (-2.062, y - 0.007, 0.262), (-1.93, y - 0.007, 0.185),
                 (-1.74, y - 0.007, 0.152)], (0, 0.014, 0))
    g.obj("diffuser", "carbon", bevel=0.003, mirror=True)


def build_sides():
    P = PT
    # ---- wheel arch trims, bolted
    g = Geo()
    K.arch_trim(g, FA_X, T_R, ARCH, 0.86, T_OUT + 0.035, ARCH_ANG)
    K.arch_trim(g, RA_X, T_R, ARCH, 0.86, T_OUT + 0.035, ARCH_ANG)
    g.obj("arch.trims", "cladding", bevel=0.005, mirror=True)
    g = Geo()
    K.arch_bolts(g, FA_X, T_R, ARCH, T_OUT + 0.035, ARCH_ANG)
    K.arch_bolts(g, RA_X, T_R, ARCH, T_OUT + 0.035, ARCH_ANG)
    g.obj("arch.bolts", "rim_bright", mirror=True)
    # ---- the outlet behind the front wheel: slats
    g = Geo()
    q = shr([P["A3"]["U"], P["A3"]["M"], P["W0"]["M"], P["W0"]["U"]], 0.14, -0.012, (0, 1, 0))
    g.louvers(q[0], q[1], q[2], q[3], 5, 0.03, 0.006, rad(30), out=(0, 1, 0))
    g.obj("vent.slats", "grille", bevel=0.002, mirror=True)
    # ---- the scoop ahead of the rear wheel: honeycomb on its face
    g = Geo()
    honey_patch(g, [P["BP"]["M"], P["SC"]["M"], P["SC"]["U"], P["BP"]["U"]], 0.013, 0.0026,
                0.010)
    g.obj("scoop.mesh", "grille", mirror=True)
    # ---- accent line along the doors' foot, running into the scoop
    g = Geo()
    path = [P[s]["M"] + V3((0, 0.004, 0.012)) for s in ("W0", "RF", "BP")]
    path[0] = path[0] + V3((-0.04, 0, 0))
    path[-1] = path[-1] + V3((0.02, 0, 0))
    g.sweep(path, [(-0.004, -0.005), (0.004, -0.005), (0.004, 0.005), (-0.004, 0.005)],
            up=(0, 0, 1))
    g.obj("led.sill", "led_accent", mirror=True)
    # ---- bolts along the top of the sill's cladding
    g = Geo()
    K.bolt_row(g, [(0.70 - 0.012 * k, 0.285 + 0.00025 * k) for k in range(101)], 0.16,
               proj='y')
    g.obj("sill.bolts", "rim_bright", mirror=True)
    # ---- side skirt blades with a winglet at the back
    g = Geo()
    g.prism([(0.88, 0.86, 0.134), (0.88, 0.935, 0.134), (-0.62, 0.95, 0.134),
             (-0.90, 0.95, 0.134), (-0.90, 0.86, 0.134)], (0, 0, 0.016))
    g.prism([(-0.62, 0.938, 0.14), (-0.90, 0.938, 0.14), (-0.90, 0.938, 0.235),
             (-0.83, 0.938, 0.235)], (0, 0.012, 0))
    g.obj("skirt", "carbon", bevel=0.003, mirror=True)
    # ---- mirrors: camera pods on blades
    dx, dy, dz = -0.05, -0.05, 0.115
    g = Geo()
    g.sweep([(0.63 + dx, 0.885 + dy, 0.772 + dz), (0.615 + dx, 0.985 + dy, 0.800 + dz)],
            [(-0.03, -0.004), (0.03, -0.004), (0.03, 0.004), (-0.03, 0.004)], up=(0, 0, 1))
    g.obj("mirror.stalks", "cladding", bevel=0.002, mirror=True)
    g = Geo()
    g.hexa([(0.69 + dx, 0.975 + dy, 0.792 + dz), (0.69 + dx, 1.005 + dy, 0.792 + dz),
            (0.53 + dx, 1.03 + dy, 0.782 + dz), (0.53 + dx, 0.965 + dy, 0.782 + dz),
            (0.675 + dx, 0.978 + dy, 0.812 + dz), (0.675 + dx, 1.002 + dy, 0.812 + dz),
            (0.53 + dx, 1.025 + dy, 0.835 + dz), (0.53 + dx, 0.970 + dy, 0.835 + dz)])
    g.obj("mirror.pods", "paint", bevel=0.004, mirror=True)
    g = Geo()
    g.box((0.5285 + dx, 0.9975 + dy, 0.808 + dz), (0.004, 0.045, 0.036))
    g.obj("mirror.lens", "gloss_black", mirror=True)


def build_roof():
    # ---- the tail frame: the roof rails run on past the hatch glass to a strut that
    # stands on the tail's corner, a blade between them, air under it
    zf = zb(-1.95, 0.59) - 0.012
    g = Geo()
    loft(g, [[(-1.60, 0.515, 1.251), (-1.61, 0.613, 1.223), (-1.61, 0.613, 1.185),
              (-1.60, 0.515, 1.205)],
             [(-1.80, 0.507, 1.266), (-1.80, 0.606, 1.239), (-1.80, 0.606, 1.204),
              (-1.80, 0.507, 1.228)],
             [(-1.962, 0.50, 1.279), (-1.962, 0.60, 1.253), (-1.962, 0.60, 1.228),
              (-1.962, 0.50, 1.25)]])
    g.prism([(-1.962, 0.577, 1.24), (-1.90, 0.577, 1.24), (-1.875, 0.577, 1.10),
             (-1.825, 0.577, zb(-1.825, 0.59) - 0.012), (-1.91, 0.577, zb(-1.91, 0.59) - 0.012),
             (-2.0, 0.577, zf)], (0, 0.023, 0))
    g.obj("tail.frame", "paint", bevel=0.004, mirror=True)
    g = Geo()
    g.prism([(-1.60, -0.505, 1.252), (-1.78, -0.505, 1.266), (-1.97, -0.505, 1.288),
             (-1.97, -0.505, 1.270), (-1.78, -0.505, 1.246), (-1.60, -0.505, 1.232)],
            (0, 1.01, 0))
    g.obj("spoiler.blade", "carbon_dry", bevel=0.003)
    g = Geo()
    g.box((-1.9715, 0, 1.279), (0.004, 0.62, 0.006))
    g.obj("led.spoiler", "led_rear")
    # ---- ribs along the roof panel, the vent over the windshield's head
    g = Geo()
    for y in (0.13, 0.26, 0.39):
        K.rib(g, [(-0.42 - 0.05 * k, y) for k in range(22)], 'z', 0.03, 0.006)
    g.obj("roof.ribs", "carbon_dry", mirror=True)
    z0 = zb(-0.10, 0.0)
    z1 = zb(-0.40, 0.0)
    g = Geo()
    loft(g, [[(-0.075, y, z0 - 0.006), (-0.09, y, z0 + 0.03), (-0.24, ys, z1 + 0.03),
              (-0.40, ys, z1 - 0.006)] for y, ys in ((-0.21, -0.15), (0.21, 0.15))])
    g.obj("roof.vent", "cladding", bevel=0.004)
    g = Geo()
    g.box((-0.0795, 0, z0 + 0.013), (0.006, 0.36, 0.02),
          rot=Matrix.Rotation(rad(-22), 3, 'Y'))
    g.obj("roof.vent.mouth", "void")
    # ---- a fin on the roof
    z0 = zb(-1.30, 0.0)
    g = Geo()
    g.prism([(-1.18, -0.006, z0 + 0.0), (-1.33, -0.006, z0 + 0.062),
             (-1.37, -0.006, z0 + 0.058), (-1.40, -0.006, z0 - 0.012)], (0, 0.012, 0))
    g.obj("roof.fin", "cladding", bevel=0.003)


def build_surface_details():
    P = PT
    # ---- slats in the hood extractors
    g = Geo()
    q = shr([P["A2"]["P"], P["A2"]["H"], P["A3"]["H"], P["A3"]["P"]], 0.30, -0.008, (0, 0, 1))
    g.louvers(q[0], q[3], q[2], q[1], 4, 0.04, 0.007, rad(-30), out=(0, 0, 1))
    g.obj("slats", "grille", bevel=0.002, mirror=True)
    # ---- studs down both edges of the spine on the hood
    g = Geo()
    for x in [1.90 - 0.15 * k for k in range(8)]:
        yc = on_spine_edge(x) - 0.026
        for y in (yc, -yc):
            loc, n = on_body(x, y, 'z')
            if loc is not None:
                stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.007), (0.0028, 0.007),
                                 (0.0028, 0.001)], 6)
    g.obj("spine.bolts", "rim_bright")
    # ---- parking sensors on the nose
    g = Geo()
    for y in (0.40, 0.72, -0.40, -0.72):
        loc, n = on_body(y, 0.635, 'x')
        if loc is not None:
            stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.011), (0.0015, 0.011),
                             (0.0015, 0.001)], 12)
    g.obj("sensors", "gloss_black")
    # ---- lettering
    g = Geo()
    for side in (1, -1):
        text_on_body(g, "KITE", 0.058, 0.36, 0.455, side, spacing=1.3)
        text_on_body(g, "HK 3", 0.018, -1.50, 0.80, side, spacing=1.2)
    g.obj("lettering", "decal")
    # ---- wipers, parked on the glass
    g, gb = Geo(), Geo()
    K.wiper(g, gb, on_body(0.865, 0.12, 'z')[0], on_body(0.775, -0.04, 'z')[0],
            on_body(0.715, 0.52, 'z')[0])
    g.obj("wiper", "cladding", bevel=0.0012)
    gb.obj("wiper.blade", "rubber")
    g, gb = Geo(), Geo()
    K.wiper(g, gb, on_body(-1.925, 0.0, 'z')[0], on_body(-1.868, -0.02, 'z')[0],
            on_body(-1.868, 0.34, 'z')[0])
    g.obj("wiper.rear", "cladding", bevel=0.0012)
    gb.obj("wiper.rear.blade", "rubber")
    # ---- markers and decals
    g = Geo()
    ribbon(g, [(1.735, 0.632), (1.655, 0.648)], 'y', 0.010)
    g.obj("led.marker", "led_accent", mirror=True)
    g = Geo()
    x = 0.02
    for w in (0.006, 0.012, 0.004, 0.004, 0.010, 0.006, 0.014, 0.004, 0.008, 0.004, 0.012, 0.006):
        ribbon(g, [(x - w / 2, 0.435), (x - w / 2, 0.48)], 'y', w)
        x -= w + 0.006
    for k in range(4):
        ribbon(g, [(-1.80 - k * 0.035, 0.84), (-1.815 - k * 0.035, 0.875)], 'y', 0.012)
    g.obj("decals", "decal", mirror=True)


# ---------------------------------------------------------------------------------------
# interior: two seats and two behind them, a load floor under the hatch
# ---------------------------------------------------------------------------------------
FLOOR = 0.21                        # the cabin floor's top
LOAD_Z = 0.57                       # the load floor's top under the hatch
WELL_IN = WELL_R - 0.03             # the load floor's half width between the rear well covers


def build_interior():
    """The cabin (vehicles/cabin.py): a lined tub from the firewall to a wall before the
    tail. A hot hatch in Halcyon's cockpit: black buckets with yellow inserts in the
    body's color and violet piping in front, two smaller buckets behind, a dash wrapped
    toward the driver with an inlay in the body's yellow, the flat-bottomed wheel, the
    console, a long door card each side and a trim panel by each rear seat (three doors),
    violet light strips like the tail's accents, a load floor between the rear wells with
    a cover over it; the interior views cab_*."""
    C.materials(carpet=(0.016, 0.016, 0.018), head=(0.040, 0.040, 0.044),
                trim=(0.74, 0.44, 0.002), trim_metal=0.0, trim_rough=0.22,
                accent=(0.56, 0.32, 0.002), piping=(0.30, 0.07, 0.62),
                belt=(0.022, 0.022, 0.025), ambient=(0.50, 0.12, 1.0))
    sb = next(n for n in K.MAT["seat"].node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    sb.inputs["Base Color"].default_value = (0.022, 0.022, 0.025, 1.0)  # black in the cabin
    sb.inputs["Roughness"].default_value = 0.70             # black suede-like cloth
    sb.inputs["Specular IOR Level"].default_value = 0.25
    cab = C.Cabin(-1.88, 0.66, FLOOR, style="halcyon")
    lin = cab.lining()
    for v in lin.data.vertices:         # held inside the fold under the quarter glass
        if -0.95 < v.co.x < -0.50 and abs(v.co.y) > 0.62 and v.co.z > 0.82:
            v.co = cab.keep(v.co, margin=0.045, wells=False)
    wells = bpy.data.objects.get("interior.wells")
    if wells is not None:               # the covers' rim at the arch's lip, under the skin
        for v in wells.data.vertices:
            if abs(v.co.y) > 0.84:
                v.co = cab.keep(v.co, margin=0.008, wells=False)
    cab.seat((-0.19, 0.37, 0.40), driver=True, quilt=5)
    cab.seat((-0.19, -0.37, 0.40), quilt=5)
    for y in (0.30, -0.30):                         # the 2: smaller, upright, in from the wells
        cab.seat((-1.06, y, 0.42), width=0.40, cushion=0.40, bolster=0.6, back=0.52, rake=24,
                 quilt=4, headrest="post")
    cab.dash()
    cab.cluster()
    cab.screen()
    cab.wheel()
    cab.pedals()
    cab.console()
    cab.door(-0.50, 0.62, tag="door", sill_text="KITE")
    cab.door(-0.93, -0.60, tag="quarter", sill=False, pull=None, release=False,
             switches=False, pocket=False)
    cab.roof_kit()
    cab.mats()
    # the load floor: between the well covers over the wells, out to the lining behind them
    p = C._Parts()
    xs = [-1.86 + 0.05 * k for k in range(10)]
    secs = []
    for x in xs:
        yw = cab.half(x, LOAD_Z - 0.01) - 0.004
        if x > -1.76:
            yw = min(yw, WELL_IN)
        secs.append([V3((x, -yw, LOAD_Z - 0.025)), V3((x, yw, LOAD_Z - 0.025)),
                     V3((x, yw, LOAD_Z)), V3((x, -yw, LOAD_Z))])
    C.loft(p["interior.carpet"], secs)
    for y in (0.20, -0.20):                         # tie-down rails along it
        p["interior.metal"].box((-1.64, y, LOAD_Z + 0.004), (0.40, 0.02, 0.008))
    cab._emit("load", p)
    cab.shelf(-1.86, -1.52, 0.90, thick=0.016, tag="cover")
    cab.views(exposure=0.3, outside=4.0, daylight=10.0)
    cab.report()
    K.meant("symmetry", *cab.one_sided)


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 0.80, 0.30))
K.VIEWS.update(
    nose=dict(dir=(1.0, 0.45, 0.10), lens=85, target=(1.9, 0.45, 0.45), dist=3.0),
    tail=dict(dir=(-1.0, -0.4, 0.14), lens=85, target=(-2.0, -0.3, 0.75), dist=3.2),
    flank=dict(dir=(0.25, 1.0, 0.12), lens=85, target=(-0.4, 0.9, 0.6), dist=3.4),
    wheel=dict(dir=(0.35, 1.0, 0.10), lens=85, target=(FA_X, 0.9, 0.45), dist=2.8),
    cabin=dict(dir=(0.35, 1.0, 0.55), lens=70, target=(-0.3, 0.3, 0.95), dist=3.6),
    outlet=dict(dir=(-0.6, 1.0, 0.2), lens=70, target=(0.85, 0.88, 0.5), dist=1.8),
    q3=dict(dir=(-0.55, 1.0, 0.22), lens=70, target=(-1.2, 0.6, 0.85), dist=3.8),
)


def main():
    K.materials(paint=(0.74, 0.44, 0.002), paint_finish=(0.70, 0.28, 1.0), dust_amount=0.2,
                led_accent=(0.50, 0.12, 1.0), caliper=(0.30, 0.02, 0.50),
                seat=(0.15, 0.05, 0.26), screen=(0.55, 0.30, 1.0),
                decal=(0.012, 0.012, 0.014), led_rear_strength=13.0,
                led_accent_strength=8.0)
    m, b = K.carbon("carbon_dry", dark=(0.007, 0.007, 0.008), light=(0.032, 0.033, 0.036),
                    coat=0.0)                               # bare weave: no coat to mirror
    b.inputs["Metallic"].default_value = 0.0                # the top light on the spine
    b.inputs["Specular IOR Level"].default_value = 0.12
    for nd in m.node_tree.nodes:
        if nd.type == 'MAP_RANGE':
            nd.inputs["To Min"].default_value = 0.58
            nd.inputs["To Max"].default_value = 0.82
    K.pbr("strap", (0.22, 0.03, 0.42), 0.0, 0.7)             # the tow strap's webbing
    build_hull()
    K.log("hull")
    build_front()
    build_rear()
    build_sides()
    build_roof()
    build_surface_details()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        for tag, cx in (("f" + s, FA_X), ("r" + s, RA_X)):
            K.build_wheel(tag, cx, T_R, T_W, T_RIM, T_OUT, side, spokes=5)
    K.log("wheels")
    K.cabin_light((-0.35, 0.0, 1.12), power=6.0)
    K.unlit("top", "body.glass_ws", "body.wstrim")          # the top box, mirrored whole
    K.meant("symmetry", "interior.wheel", "interior.screens", "wiper*", "tow.strap")
    K.shoot(extra="top")


main()
