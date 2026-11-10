"""Halcyon Ridge: a performance crossover (both names made up), on vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/halcyon_ridge.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/halcyon_ridge.py --out DIR --sheet

The Vanta-R's and the Sable's sibling, raised: the carbon spine, octagonal bolted arches, the
corner-turning nose strip, the light round the tail, honeycomb, the scoop ahead of the rear
wheel and the twin-spoke turbine wheels. Its own ideas: the spine is a wishbone that opens
round the cabin (wide on the hood, up both windshield pillars, along the roof as rails, down
the hatch frame, closed again on the tail) and ends in a ribbed skid plate under the nose;
flying roof rails with a light bar between them that run on into the hatch spoiler; the
arches as rings of bolted armor plates with a hand's width of air to the tire; a scoop
twice the family's height; step blades; tow eyes; all-terrain tires.

The body is ten character lines over twelve stations, cut by the wheel wells and split
into panels. Everything else hangs on the same station points.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                                  # noqa: E402
from carkit import (Geo, Matrix, V3, band_point, cos, my, on_body, pi, rad,    # noqa: E402
                    ribbon, shr, sin, stud, text_flat, text_on_body)

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.50, -1.45            # axles: 2.95 m wheelbase
T_R, T_W, T_RIM = 0.41, 0.295, 0.27    # tire radius, width, rim radius
T_OUT = 0.985                       # outer face of the tires
ARCH = 0.52                         # wheel arch radius at its corners
ARCH_ANG = (-15, 22.5, 67.5, 112.5, 157.5, 195)     # half an octagon, its top flat
RING_W = 0.10                       # the armor ring's width
RING_IN, RING_OUT = 0.90, 1.027     # its inner and outer face (y)
SUBDIV = 3

# ---------------------------------------------------------------------------------------
# body: stations and character lines
# ---------------------------------------------------------------------------------------
LINES = "CPHGSUMRFB"
#        C centerline top, P spine edge / rail inner edge, H hood crease / rail outer edge,
#        G fender inner / beltline, S shoulder crest, U widest line, M cladding line,
#        R rocker, F floor edge, B floor
ORDER = ["N0", "N1", "A2", "A3", "W0", "RF", "BP", "D2", "SC", "RA", "RB", "T1"]
PT = {}


def stations():
    T = {
        "N0": [(2.375, 0, .815), (2.37, .24, .815), (2.345, .52, .81), (2.31, .69, .80),
               (2.25, .86, .785), (2.22, .925, .70), (2.22, .93, .56), (2.24, .90, .47),
               (2.30, .60, .445), (2.335, 0, .445)],
        "N1": [(2.08, 0, .868), (2.075, .25, .872), (2.06, .56, .895), (2.05, .72, .935),
               (2.03, .925, .945), (2.02, .965, .80), (2.02, .965, .56), (2.03, .93, .36),
               (2.02, .64, .27), (2.02, 0, .27)],
        "A2": [(1.50, 0, .958), (1.50, .27, .964), (1.50, .66, .99), (1.50, .79, 1.03),
               (1.50, .945, 1.025), (1.50, .975, .82), (1.50, .965, .56), (1.50, .94, .27),
               (1.50, .68, .24), (1.50, 0, .24)],
        "A3": [(.98, 0, 1.035), (.98, .42, 1.04), (.98, .74, 1.045), (.98, .84, 1.055),
               (.98, .94, 1.035), (.98, .968, .82), (.98, .955, .54), (.98, .94, .27),
               (.98, .70, .24), (.98, 0, .24)],
        "W0": [(.90, 0, 1.065), (.87, .66, 1.068), (.80, .80, 1.062), (.78, .875, 1.055),
               (.78, .93, 1.02), (.78, .962, .82), (.78, .945, .54), (.78, .945, .27),
               (.78, .71, .24), (.78, 0, .24)],
        "RF": [(-.02, 0, 1.512), (-.03, .60, 1.505), (-.10, .725, 1.478)] + [None] * 7,
        "BP": [(-.50, 0, 1.535), (-.50, .60, 1.528), (-.48, .725, 1.498),
               (-.14, .905, 1.045), (-.14, .95, 1.005), (-.14, .97, .82), (-.14, .945, .52),
               (-.14, .95, .27), (-.14, .72, .24), (-.14, 0, .24)],
        "D2": [(-1.00, 0, 1.522), (-1.00, .60, 1.515), (-.98, .725, 1.485),
               (-.72, .905, 1.075), (-.70, .955, 1.03), (-.66, .87, .82), (-.64, .85, .50),
               (-.64, .955, .28), (-.64, .72, .24), (-.64, 0, .24)],
        "SC": [None, None, None, (-.80, .905, 1.085), (-.78, .975, 1.04),
               (-.74, .985, .825), (-.72, .972, .50), (-.71, .955, .28),
               (-.71, .72, .24), (-.71, 0, .24)],
        "RA": [(-1.38, 0, 1.495), (-1.38, .59, 1.488), (-1.38, .715, 1.455),
               (-1.45, .90, 1.115), (-1.45, .965, 1.065), (-1.45, .985, .84),
               (-1.45, .972, .52), (-1.45, .955, .28), (-1.45, .70, .25), (-1.45, 0, .25)],
        "RB": [(-1.96, 0, 1.225), (-1.96, .52, 1.22), (-1.97, .68, 1.19), (-1.98, .84, 1.10),
               (-1.99, .945, 1.045), (-1.99, .972, .84), (-1.99, .955, .56),
               (-1.99, .93, .34), (-1.99, .70, .29), (-1.99, 0, .29)],
        "T1": [(-2.375, 0, 1.02), (-2.375, .40, 1.018), (-2.365, .62, 1.01),
               (-2.345, .78, .985), (-2.31, .885, .95), (-2.29, .915, .82),
               (-2.29, .905, .64), (-2.31, .87, .53), (-2.35, .62, .50), (-2.375, 0, .50)],
    }
    for j in range(3, 10):
        T["RF"][j] = V3(T["W0"][j]).lerp(V3(T["BP"][j]), 0.60)
    for j in range(0, 3):
        T["SC"][j] = V3(T["D2"][j]).lerp(V3(T["RA"][j]), 0.12)
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


PMAT = dict(spine="carbon_dry", hood="paint", roof="paint2", bumper_f="paint", fender_f="paint",
            door_f="paint", door_r="paint", quarter="paint", bumper_r="paint",
            glass_ws="glass", glass_rear="glass", glass_side="glass",
            trim="gloss_black", sill="cladding", floor="underbody", skid="cladding",
            mouth="void", mouth_frame="cladding", lightband="gloss_black", tail="void",
            tail_frame="cladding", scoop="void", vent="void", well="well")
FRONT_C = V3((2.36, 0, 0.625))      # middle of the mouth
REAR_C = V3((-2.36, 0, 0.76))       # middle of the tail panel
BAND_W = 0.05
MOUTH_D, TAIL_D = 0.20, 0.14
CAPS = {}


def panel_of(i, j):
    if j >= 7:
        return "skid" if i in (0, 10) else "floor"
    if j == 6:
        return "sill"
    if j == 0:                      # the middle: spine, windshield, roof, hatch, spine
        return ("spine", "spine", "spine", "spine", "glass_ws", "roof", "roof", "roof",
                "roof", "glass_rear", "spine")[i]
    if j == 1:                      # hood, then the wishbone's arms: pillars, rails, frame
        return "bumper_f" if i == 0 else "hood" if i <= 3 else "spine"
    if i == 0:
        return "bumper_f"
    if i == 10:
        return "bumper_r"
    if j == 2:
        return "fender_f" if i <= 3 else "glass_side" if i <= 8 else "quarter"
    if i <= 3:
        return "fender_f"
    if i <= 5:
        return "door_f"
    if i == 6:
        return "door_r"
    if i == 7 and j in (4, 5):
        return "scoop"
    return "quarter"


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
        return 1.0 if i == 7 else 0.55
    return 1.0


def station_crease(i, j):
    """Crease of the edge on station i between lines j and j + 1."""
    if i in (0, 11):
        return 1.0
    if i == 4:
        return 1.0 if j <= 2 else 0.0
    if i == 5:
        return 1.0 if j == 0 else 0.4 if j == 1 else 0.0
    if i == 7:
        return 1.0 if j in (4, 5, 6) else 0.5 if j == 3 else 0.0
    if i == 8:
        return 1.0 if j in (4, 5, 6) else 0.6 if j == 3 else 0.0
    if i == 9:
        return 1.0 if j == 0 else 0.6 if j == 1 else 1.0 if j == 2 else 0.0
    if i == 10:
        return 1.0 if j == 0 else 0.6 if j <= 2 else 0.0
    if i == 1:
        return 0.5 if j <= 4 else 0.8 if j >= 7 else 0.0
    return 0.0


def build_hull():
    wells = Geo()
    K.well_cutter(wells, FA_X, T_R, ARCH, 0.66, ARCH_ANG)
    K.well_cutter(wells, RA_X, T_R, ARCH, 0.66, ARCH_ANG)
    body = K.build_body(
        stations(), panel_of, PMAT, line_crease, station_crease,
        front=dict(center=FRONT_C, depth=MOUTH_D, band=BAND_W, band_panel="lightband",
                   band_lines=6, frame="mouth_frame", inner="mouth"),
        rear=dict(center=REAR_C, depth=TAIL_D, band=BAND_W, band_panel="lightband",
                  band_lines=9, frame="tail_frame", inner="tail"),
        recesses=[(2, 1, 0.085, 0.03)],     # hood extractors, one each side of the spine
        glass=[("glass_ws", 0.022), ("glass_rear", 0.022), ("glass_side", 0.02)],
        cutters=[(wells, "well")], subdiv=SUBDIV)
    CAPS["mouth"], CAPS["tail"] = body.caps["front"], body.caps["rear"]


# ---------------------------------------------------------------------------------------
# helpers of this car
# ---------------------------------------------------------------------------------------
STRIP = [(-0.009, -0.004), (0.009, -0.004), (0.009, 0.006), (-0.009, 0.006)]
BOLT = [(-0.003, 0.002), (-0.003, 0.0115), (0.0045, 0.0115), (0.0045, 0.002)]


def zb(x, y):
    """Height of the body as built under (x, y)."""
    loc, _ = on_body(x, y, 'z')
    return loc.z if loc is not None else 0.0


def slab(g, a, b, y0, y1, t0, t1, toe=None):
    """A plate under the line a-b (x, z), from y0 to y1, between t0 and t1 off the line on
    its lower side; toe: one more (x, z) point at a's end."""
    a, b = V3((a[0], 0, a[1])), V3((b[0], 0, b[1]))
    d = (b - a).normalized()
    n = V3((-d.z, 0, d.x))
    if n.z > 0:
        n = -n
    poly = [a + n * t0, b + n * t0, b + n * t1, a + n * t1]
    if toe is not None:
        poly.append(V3((toe[0], 0, toe[1])))
    g.prism([p + V3((0, y0, 0)) for p in poly], (0, y1 - y0, 0))


def honey_on(g, O, u, w, n, poly, R, wall, depth):
    """Honeycomb over a polygon given in (u, w) on the plane through O, standing off it
    along n."""
    h = Geo()
    h.honeycomb(poly, 0.0, R, wall, depth, 1)
    O, u, w, n = V3(O), V3(u), V3(w), V3(n)
    g.add([O + n * p.x + u * p.y + w * p.z for p in h.v], h.f)


def tow_eye(g, c, r=0.045, out=1):
    """A tow eye: a ring standing in the plane y = c.y on a short shank."""
    c = V3(c)
    path = [c + V3((r * cos(rad(a)), 0, r * 0.8 * sin(rad(a)))) for a in range(0, 360, 45)]
    g.sweep(path, [(-0.009, -0.009), (0.009, -0.009), (0.009, 0.009), (-0.009, 0.009)],
            up=(0, 1, 0), closed=True)
    g.box(c + V3((-out * (r + 0.03), 0, 0)), (0.07, 0.03, 0.03))


def armor_ring(g, gb, cx):
    """The arch as armor: one plate per facet with a joint between them, two bolts each."""
    r0, r1 = ARCH - 0.006, ARCH + RING_W
    for k in range(len(ARCH_ANG) - 1):
        a0, a1 = ARCH_ANG[k] + 0.55, ARCH_ANG[k + 1] - 0.55

        def pt(a, r, y):
            return (cx + r * cos(rad(a)), y, T_R + r * sin(rad(a)))
        g.hexa([pt(a0, r0, RING_IN), pt(a1, r0, RING_IN), pt(a1, r1, RING_IN),
                pt(a0, r1, RING_IN), pt(a0, r0, RING_OUT), pt(a1, r0, RING_OUT),
                pt(a1, r1 - 0.012, RING_OUT), pt(a0, r1 - 0.012, RING_OUT)])
        da = a1 - a0
        for t in (0.2, 0.8):
            a = a0 + da * t
            rr = (r0 + r1) / 2 * cos(rad(da / 2)) / cos(rad(da * (t - 0.5)))
            gb.lathe(BOLT, 6, xf=Matrix.Translation(pt(a, rr, RING_OUT)))


# ---------------------------------------------------------------------------------------
# details on the body
# ---------------------------------------------------------------------------------------
def build_front():
    P = PT
    # ---- lights: a strip under the nose lip from the spine out, turning down the corner
    top = [P["N0"]["P"].lerp(P["N0"]["H"], 0.10)] + [P["N0"][n] for n in "HGSU"]
    top.append(P["N0"]["U"].lerp(P["N0"]["M"], 0.95))
    g = Geo()
    g.sweep([band_point(p, FRONT_C, BAND_W * 0.5, 0.0) for p in top], STRIP, up=(1, 0, 0))
    g.obj("led.front", "led_front", mirror=True)

    # ---- the spine comes down the nose as a keel and ends in the skid plate
    xb = FRONT_C.x - MOUTH_D
    g = Geo()
    lo = [(2.352, 0.30, 0.44), (2.352, -0.30, 0.44), (xb, -0.36, 0.44), (xb, 0.36, 0.44)]
    hi = [(2.384, 0.225, 0.79), (2.384, -0.225, 0.79), (xb, -0.26, 0.80), (xb, 0.26, 0.80)]
    g.hexa(lo + hi)
    g.obj("mouth.keel", "carbon", bevel=0.004)
    g, gb = Geo(), Geo()                                # slots and bolts on the keel's face
    for k in range(4):
        z = 0.475 + k * 0.026
        x = 2.352 + (z - 0.44) * 0.0914
        g.box((x + 0.0006, 0, z), (0.004, 0.34 - k * 0.012, 0.011))
    for y in (0.20, -0.20):
        for z in (0.76, 0.60):
            w = 1.0 if z > 0.7 else 1.22
            stud(gb, V3((2.352 + (z - 0.44) * 0.0914, y * w, z)), V3((1, 0, -0.09)).normalized(),
                 BOLT, 6)
    g.obj("keel.slots", "void")
    gb.obj("keel.bolts", "rim_bright")
    a, b = (2.352, 0.447), (1.985, 0.258)
    g = Geo()
    slab(g, a, b, -0.58, 0.58, 0.004, 0.024, toe=(2.392, 0.462))
    for yc in (-0.42, -0.21, 0.0, 0.21, 0.42):
        slab(g, (2.30, 0.4205), (2.03, 0.2815), yc - 0.035, yc + 0.035, 0.022, 0.036)
    g.obj("skid.front", "skid", bevel=0.003)
    g = Geo()
    for y in (-0.52, -0.315, -0.105, 0.105, 0.315, 0.52):
        for t in (0.12, 0.88):
            p = V3((a[0], y, a[1])).lerp(V3((b[0], y, b[1])), t)
            stud(g, p + V3((0.0105, 0, -0.0216)), V3((0.437, 0, -0.899)), BOLT, 6)
    g.obj("skid.bolts", "rim_bright")
    g = Geo()
    for y in (0.40, -0.40):
        tow_eye(g, (2.388, y, 0.492), r=0.04)
    g.obj("tow.front", "tow", bevel=0.003)

    # ---- honeycomb either side of the keel, a stack of three hexagonal lamps in each
    g = Geo()
    half = [(p.y, p.z) for p in CAPS["mouth"]]
    poly = half + [(-y, z) for (y, z) in half[::-1]]
    g.honeycomb(poly, xb, 0.018, 0.003, 0.012, 1,
                keep=lambda y, z: abs(y) > 0.27 and not (abs(abs(y) - 0.665) < 0.06))
    g.obj("mouth.mesh", "grille")
    g, ge = Geo(), Geo()
    rot = Matrix.Rotation(-pi / 2, 4, 'Z')
    for z in (0.545, 0.625, 0.705):
        xf = Matrix.Translation((2.285, 0.665, z)) @ rot
        g.lathe([(-0.13, 0.026), (-0.13, 0.037), (0.0, 0.037), (0.0, 0.029), (-0.012, 0.026)],
                6, xf=xf)
        ge.lathe([(-0.02, 0.002), (-0.02, 0.0275), (-0.012, 0.0275), (-0.012, 0.002)], 6, xf=xf)
    g.box((2.21, 0.665, 0.625), (0.10, 0.012, 0.26))
    g.obj("beam.pods", "gloss_black", bevel=0.002, mirror=True)
    ge.obj("beam.lens", "lamp", mirror=True)
    # ---- a blade across each intake, the badge on the keel
    g = Geo()
    g.hexa([(2.30, 0.30, 0.492), (2.27, 0.80, 0.492), (2.17, 0.80, 0.50), (2.17, 0.30, 0.50),
            (2.30, 0.30, 0.504), (2.27, 0.80, 0.504), (2.17, 0.80, 0.516), (2.17, 0.30, 0.516)])
    g.obj("mouth.blade", "carbon", bevel=0.002, mirror=True)
    g = Geo()
    g.lathe([(0.0, 0.002), (0.0, 0.03), (0.006, 0.025), (0.006, 0.002)], 6,
            xf=Matrix.Translation((2.385, 0, 0.72)) @ rot)
    g.obj("badge", "rim_bright", bevel=0.001)
    g = Geo()
    text_flat(g, "R - 4 X", 0.03, (2.3722, 0, 0.60), (0, 1, 0), (0.09, 0, 1), spacing=1.2)
    g.obj("keel.glyphs", "decal")


def build_rear():
    P = PT
    # ---- lights: a closed ring round the whole tail
    half = [band_point(P["T1"][n], REAR_C, BAND_W * 0.5, 0.0) for n in "PHGSUMRF"]
    path = (half + [band_point(P["T1"]["B"], REAR_C, BAND_W * 0.5, 0.0)]
            + [my(p) for p in half[::-1]])
    g = Geo()
    g.sweep(path, [(-0.008, -0.006), (0.008, -0.006), (0.008, 0.004), (-0.008, 0.004)],
            up=(-1, 0, 0), closed=True)
    g.obj("led.rear", "led_rear")
    xt = REAR_C.x + TAIL_D
    # ---- honeycomb, the beam with the maker's name, plate, two flat outlets
    g = Geo()
    half = [(p.y, p.z) for p in CAPS["tail"]]
    poly = half + [(-y, z) for (y, z) in half[::-1]]

    def clear(y, z):
        return not (abs(abs(y) - 0.45) < 0.165 and abs(z - 0.66) < 0.06) and \
            not (abs(y) < 0.16 and abs(z - 0.66) < 0.07) and not abs(z - 0.83) < 0.062
    g.honeycomb(poly, xt - 0.012, 0.022, 0.0035, 0.012, -1, keep=clear)
    g.obj("tail.mesh", "grille")
    g = Geo()
    g.prism([(-2.275, -0.80, 0.785), (-2.30, -0.80, 0.803), (-2.30, -0.80, 0.857),
             (-2.275, -0.80, 0.875), (-2.21, -0.80, 0.86), (-2.21, -0.80, 0.80)], (0, 1.60, 0))
    g.obj("tail.beam", "carbon", bevel=0.003)
    g, ge = Geo(), Geo()
    hexa = [(0.45 + 0.135, 0.66), (0.45 + 0.10, 0.618), (0.45 - 0.10, 0.618),
            (0.45 - 0.135, 0.66), (0.45 - 0.10, 0.702), (0.45 + 0.10, 0.702)]
    g.sweep([(xt - 0.055, y, z) for y, z in hexa],
            [(-0.007, -0.05), (0.007, -0.05), (0.007, 0.05), (-0.007, 0.05)],
            up=(-1, 0, 0), closed=True)
    ge.prism([(xt - 0.02, y, z) for y, z in hexa], (-0.004, 0, 0))
    g.obj("outlet", "rim", bevel=0.002, mirror=True)
    ge.obj("outlet.glow", "ember", mirror=True)
    g = Geo()
    g.box((xt - 0.012, 0, 0.66), (0.012, 0.27, 0.095))
    g.obj("plate", "gloss_black", bevel=0.003)
    g = Geo()
    text_flat(g, "VB 44-718", 0.05, (xt - 0.0185, 0, 0.66), (0, -1, 0), (0, 0, 1), spacing=1.1)
    g.obj("plate.glyphs", "led_accent")
    g = Geo()
    text_flat(g, "H A L C Y O N", 0.042, (-2.3012, 0, 0.83), (0, -1, 0), (0, 0, 1), spacing=1.35)
    g.obj("led.name", "led_rear")
    # ---- the rear skid plate with the family's fins on it, tow eyes
    a, b = (-2.385, 0.502), (-1.97, 0.276)
    g = Geo()
    slab(g, a, b, -0.58, 0.58, 0.004, 0.022, toe=(-2.405, 0.515))
    g.obj("skid.rear", "skid", bevel=0.003)
    g = Geo()
    for y in (0.0, 0.26, 0.52):
        g.prism([(-2.02, y - 0.007, 0.285), (-2.39, y - 0.007, 0.49),
                 (-2.41, y - 0.007, 0.415), (-2.20, y - 0.007, 0.305)], (0, 0.014, 0))
    g.obj("diffuser", "carbon", bevel=0.003, mirror=True)
    g = Geo()
    for y in (0.39, -0.39):
        tow_eye(g, (-2.398, y, 0.535), r=0.04, out=-1)
    g.obj("tow.rear", "tow", bevel=0.003)
    # ---- louvres on the closed end of the spine, under the hatch glass
    g = Geo()
    a = P["RB"]["P"].lerp(P["RB"]["C"], 0.14) + V3((-0.035, 0, 0))
    b = P["RB"]["P"].lerp(P["T1"]["P"], 0.62).lerp(P["RB"]["C"].lerp(P["T1"]["C"], 0.62), 0.14)
    g.louvers(a, b, my(b), my(a), 4, 0.05, 0.010, rad(12), out=(0, 0, 1), lift=0.014,
              margin=0.08)
    g.obj("spine.louvers", "gloss_black", bevel=0.003)


def build_sides():
    P = PT
    # ---- the arches: rings of armor plates, bolted
    g, gb = Geo(), Geo()
    armor_ring(g, gb, FA_X)
    armor_ring(g, gb, RA_X)
    g.obj("arch.armor", "cladding", bevel=0.007, mirror=True)
    gb.obj("arch.bolts", "rim_bright", mirror=True)
    # ---- the scoop, twice the family's height: honeycomb, a blade at half height
    O = P["D2"]["M"] + V3((0, 0, 0.0))
    e = P["SC"]["M"] - P["D2"]["M"]
    u = V3((e.x, e.y, 0)).normalized()
    n = V3((u.y, -u.x, 0))
    L = V3((e.x, e.y, 0)).length
    g = Geo()
    honey_on(g, O + n * 0.004, u, (0, 0, 1), n,
             [(0.012, 0.03), (L - 0.008, 0.03), (L - 0.008, 0.33), (L - 0.03, 0.47),
              (0.03, 0.30), (0.012, 0.20)], 0.014, 0.0028, 0.010)
    g.obj("scoop.mesh", "grille", mirror=True)
    g = Geo()
    c = (P["D2"]["U"] + P["SC"]["U"]) / 2 + V3((0, 0, -0.01))
    g.hexa([c + u * -0.085 + n * 0.0, c + u * 0.075 + n * 0.0, c + u * 0.075 + n * 0.085,
            c + u * -0.04 + n * 0.11,
            c + u * -0.085 + V3((0, 0, 0.014)), c + u * 0.075 + V3((0, 0, 0.014)),
            c + u * 0.075 + n * 0.085 + V3((0, 0, 0.010)),
            c + u * -0.04 + n * 0.11 + V3((0, 0, 0.010))])
    g.obj("scoop.blade", "carbon", bevel=0.002, mirror=True)
    # ---- hood extractors
    g = Geo()
    q = shr([P["A2"]["P"], P["A2"]["H"], P["A3"]["H"], P["A3"]["P"]], 0.30, -0.008, (0, 0, 1))
    g.louvers(q[0], q[3], q[2], q[1], 4, 0.045, 0.007, rad(-30), out=(0, 0, 1))
    g.obj("slats", "grille", bevel=0.002, mirror=True)
    # ---- step blades standing off the sill on three brackets, a light in their edge
    g = Geo()
    g.prism([(0.82, 0.935, 0.292), (0.80, 1.027, 0.292), (-0.60, 1.027, 0.292),
             (-0.68, 0.99, 0.292), (-0.68, 0.935, 0.292)], (0, 0, 0.02))
    g.obj("step.blade", "carbon", bevel=0.003, mirror=True)
    g = Geo()
    for x in (0.62, 0.07, -0.50):
        g.prism([(x - 0.03, 0.90, 0.30), (x + 0.03, 0.90, 0.30), (x + 0.02, 0.90, 0.40),
                 (x - 0.02, 0.90, 0.40)], (0, 0.085, 0))
    g.obj("step.brackets", "cladding", bevel=0.003, mirror=True)
    g = Geo()
    g.box((0.10, 1.0275, 0.302), (1.30, 0.004, 0.006))
    g.obj("led.step", "led_accent", mirror=True)
    g = Geo()
    for k in range(9):                                  # grip bars on the step
        g.box((0.66 - k * 0.15, 0.985, 0.3135), (0.09, 0.05, 0.004))
    g.obj("step.grip", "rim", mirror=True)
    # ---- accent line along the doors' foot, running into the scoop
    g = Geo()
    path = [P[s]["M"] + V3((0, 0.004, 0.014)) for s in ("W0", "RF", "BP", "D2")]
    path[0] = path[0] + V3((-0.05, 0, 0))
    path[-1] = path[-1] + V3((0.03, 0.004, 0))
    g.sweep(path, [(-0.004, -0.005), (0.004, -0.005), (0.004, 0.005), (-0.004, 0.005)],
            up=(0, 0, 1))
    g.obj("led.sill", "led_accent", mirror=True)
    # ---- mirrors: camera pods on blades
    dx, dy, dz = -0.08, 0.018, 0.293
    g = Geo()
    g.sweep([(0.63 + dx, 0.90 + dy, 0.772 + dz), (0.615 + dx, 0.985 + dy, 0.800 + dz)],
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
    # ---- the rails: the spine's arms lifted off the roof, running on into the spoiler
    yr = 0.664
    z_end = zb(-1.36, yr) + 0.052
    path = []
    for k in range(34):
        x = -0.03 - k * 0.0485
        lift = 0.052 * min(1.0, k / 3.0)
        path.append(V3((x, yr, max(zb(x, yr) + lift, z_end) if x < -1.30 else zb(x, yr) + lift)))
    g = Geo()
    g.sweep(path, [(-0.017, -0.012), (0.017, -0.012), (0.012, 0.015), (-0.012, 0.015)],
            up=(0, 0, 1))
    for x in (-0.50, -0.88, -1.26):
        z = zb(x, yr)
        g.prism([(x - 0.05, yr - 0.012, z - 0.004), (x + 0.05, yr - 0.012, z - 0.004),
                 (x + 0.025, yr - 0.012, z + 0.045), (x - 0.025, yr - 0.012, z + 0.045)],
                (0, 0.024, 0))
    g.obj("roof.rails", "carbon_dry", bevel=0.003, mirror=True)
    # ---- the light bar between them, over the windshield's head
    z0 = path[5].z
    x0 = path[5].x
    g, ge = Geo(), Geo()
    g.prism([(x0 + 0.045, -yr, z0 - 0.022), (x0 + 0.035, -yr, z0 + 0.030),
             (x0 - 0.045, -yr, z0 + 0.034), (x0 - 0.085, -yr, z0 - 0.018)], (0, 2 * yr, 0))
    for k in range(8):
        ge.box((x0 + 0.0405, (k - 3.5) * 0.152, z0 + 0.004), (0.006, 0.128, 0.03),
               rot=Matrix.Rotation(rad(-11), 3, 'Y'))
    g.obj("roof.bar", "cladding", bevel=0.003)
    ge.obj("roof.bar.lens", "lamp")
    # ---- the spoiler: a blade between the rails' ends, clear of the hatch glass
    zr = z_end
    g = Geo()
    g.prism([(-1.34, -0.70, zr - 0.006), (-1.50, -0.70, zr + 0.006), (-1.625, -0.70, zr + 0.026),
             (-1.625, -0.70, zr + 0.012), (-1.50, -0.70, zr - 0.010), (-1.34, -0.70, zr - 0.020)],
            (0, 1.40, 0))
    g.obj("spoiler.blade", "carbon_dry", bevel=0.003)
    g = Geo()
    g.box((-1.627, 0, zr + 0.019), (0.004, 1.06, 0.006))
    g.obj("led.spoiler", "led_rear")
    # ---- a fin and ribs on the roof panel
    zf = zb(-1.08, 0.0)
    g = Geo()
    g.prism([(-0.98, -0.006, zf + 0.004), (-1.13, -0.006, zf + 0.07), (-1.17, -0.006, zf + 0.066),
             (-1.20, -0.006, zf - 0.008)], (0, 0.012, 0))
    g.obj("roof.fin", "cladding", bevel=0.003)
    g = Geo()
    for y in (0.14, 0.28, 0.42):
        ribbon(g, [(-0.42, y), (-1.22, y)], 'z', 0.022, lift=0.004)
    g.obj("roof.ribs", "paint2", mirror=True)


def build_surface_details():
    P = PT
    # ---- studs down both edges of the spine on the hood and along the rails' feet
    g = Geo()
    for x in [2.20 - 0.17 * k for k in range(8)]:
        yc = on_spine_edge(x) - 0.028
        for y in (yc, -yc):
            loc, n = on_body(x, y, 'z')
            if loc is not None:
                stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.007), (0.0028, 0.007),
                                 (0.0028, 0.001)], 6)
    for x in [-0.20 - 0.155 * k for k in range(8)] + [-2.03 - 0.1 * k for k in range(3)]:
        for y0 in (0.705, 0.615) if x > -1.5 else (0.50,):
            for y in (y0, -y0):
                loc, n = on_body(x, y - 0.11 * (-2.03 - x) * (1 if y > 0 else -1)
                                 if x < -1.5 else y, 'z')
                if loc is not None:
                    stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.007), (0.0028, 0.007),
                                     (0.0028, 0.001)], 6)
    g.obj("spine.bolts", "rim_bright")
    # ---- parking sensors on the nose
    g = Geo()
    for y in (0.42, 0.74, -0.42, -0.74):
        loc, n = on_body(y, 0.84, 'x')
        if loc is not None:
            stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.011), (0.0015, 0.011),
                             (0.0015, 0.001)], 12)
    g.obj("sensors", "gloss_black")
    # ---- lettering
    g = Geo()
    for side in (1, -1):
        text_on_body(g, "RIDGE", 0.06, 0.30, 0.655, side, spacing=1.3)
        text_on_body(g, "HR 4X", 0.02, -1.70, 1.215, side, spacing=1.2)
        text_on_body(g, "4", 0.07, -0.42, 0.66, side)
    g.obj("lettering", "decal")
    # ---- the doors: flush handles, the pillar between them on the glass, a charge flap
    g = Geo()
    ribbon(g, [(0.02, 0.975), (-0.10, 0.978)], 'y', 0.018)
    ribbon(g, [(-0.52, 0.99), (-0.63, 0.993)], 'y', 0.018)
    hexa = [(-1.70 + 0.058 * cos(rad(a)), 1.30 + 0.058 * sin(rad(a))) for a in range(0, 360, 60)]
    ribbon(g, hexa, 'y', 0.004, closed=True)
    g.obj("lines", "void", mirror=True)
    g = Geo()
    hg, hh = P["BP"]["G"], P["BP"]["H"]
    ribbon(g, [(hg.x - 0.01, hg.z + 0.012), (hh.x + 0.03, hh.z - 0.03)], 'y', 0.07, lift=0.002)
    g.obj("pillar.b", "gloss_black", mirror=True)
    # ---- wipers
    g = Geo()
    blade = []
    for k in range(9):
        t = k / 8
        loc, n = on_body(0.80 - 0.05 * t, 0.06 + 0.52 * t, 'z')
        blade.append(loc + n * 0.014)
    g.sweep(blade, [(-0.004, -0.008), (0.004, -0.008), (0.004, 0.006), (-0.004, 0.006)],
            up=(0, 0, 1))
    piv, _ = on_body(0.875, 0.30, 'z')
    g.sweep([piv + V3((0, 0, 0.012)), blade[4] + V3((0, 0, 0.012))],
            [(-0.006, -0.004), (0.006, -0.004), (0.006, 0.004), (-0.006, 0.004)], up=(0, 0, 1))
    g.obj("wiper", "cladding", bevel=0.0015, mirror=True)
    # ---- markers and decals
    g = Geo()
    ribbon(g, [(2.215, 0.745), (2.14, 0.765)], 'y', 0.012)
    g.obj("led.marker", "led_accent", mirror=True)
    g = Geo()
    x = 0.02
    for w in (0.006, 0.012, 0.004, 0.004, 0.010, 0.006, 0.014, 0.004, 0.008, 0.004, 0.012, 0.006):
        ribbon(g, [(x - w / 2, 0.635), (x - w / 2, 0.68)], 'y', w)
        x -= w + 0.006
    for k in range(4):
        ribbon(g, [(-2.13 - k * 0.035, 0.90), (-2.145 - k * 0.035, 0.935)], 'y', 0.012)
    g.obj("decals", "decal", mirror=True)


def on_spine_edge(x):
    """y of the spine's edge at x (the P line as drawn)."""
    pts = [PT[s]["P"] for s in ORDER]
    for a, b in zip(pts, pts[1:]):
        if b.x <= x <= a.x:
            t = (a.x - x) / max(a.x - b.x, 1e-6)
            return a.y + (b.y - a.y) * t
    return 0.2


# ---------------------------------------------------------------------------------------
# interior: four seats, a load floor under the hatch
# ---------------------------------------------------------------------------------------
def build_interior():
    g = Geo()
    g.prism([(0.76, -.82, 1.0), (0.76, -.78, 1.0), (0.76, -.72, .30), (0.76, .72, .30),
             (0.76, .78, 1.0), (0.76, .82, 1.0), (0.76, .82, .26), (0.76, -.82, .26)],
            (-1.66, 0, 0))                                      # floor and door cards
    g.box((-1.45, 0, 0.285), (1.10, 1.24, 0.04))                # floor between the wells
    g.box((-1.66, 0, 0.62), (0.86, 1.24, 0.04))                 # the load floor
    g.prism([(-1.20, -0.62, 0.27), (-1.20, 0.62, 0.27), (-1.26, 0.64, 1.02),
             (-1.26, -0.64, 1.02)], (-0.04, 0, 0))              # behind the rear seats
    g.box((-1.64, 0, 1.03), (0.74, 1.30, 0.016))                # the cover over the load
    g.prism([(0.76, -0.78, 0.72), (0.76, -0.78, 1.045), (0.50, -0.78, 1.045),
             (0.36, -0.78, 0.96), (0.40, -0.78, 0.72)], (0, 1.56, 0))       # dash
    g.box((-0.30, 0, 0.50), (1.90, 0.20, 0.26))                 # the console
    g.box((-0.66, 0, 0.69), (0.36, 0.17, 0.10))                 # armrest between the rear seats
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    tilt = Matrix.Rotation(rad(-18), 3, 'Y')
    for x0, tall in ((0.10, 0.0), (-0.74, -0.01)):
        for y in (0.385, -0.385):
            g.box((x0, y, 0.57), (0.50, 0.46, 0.12))
            g.box((x0 - 0.37, y, 0.89 + tall), (0.11, 0.44, 0.62), rot=tilt)
            g.box((x0 - 0.49, y, 1.245 + tall), (0.07, 0.22, 0.15), rot=tilt)
            for s in (-1, 1):
                g.box((x0, y + s * 0.235, 0.60), (0.46, 0.05, 0.16))
                g.box((x0 - 0.355, y + s * 0.225, 0.85 + tall), (0.14, 0.05, 0.50), rot=tilt)
    g.obj("interior.seats", "seat", bevel=0.014, segs=3)
    g = Geo()
    wheel = (Matrix.Translation((0.29, 0.385, 1.0)) @ Matrix.Rotation(rad(-70), 4, 'Y')
             @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.012, 0.155), (0.0, 0.167), (0.012, 0.155), (0.0, 0.143)], 24, xf=wheel)
    g.box((0.36, 0.385, 0.97), (0.16, 0.05, 0.05))
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    scr = Matrix.Rotation(rad(-25), 3, 'Y')
    g.box((0.365, 0.0, 1.0), (0.008, 0.34, 0.085), rot=scr)
    g.box((0.43, 0.385, 1.055), (0.008, 0.28, 0.05), rot=scr)
    g.box((0.43, -0.385, 1.055), (0.008, 0.28, 0.05), rot=scr)
    g.box((-0.46, 0.0, 0.72), (0.008, 0.15, 0.09), rot=scr)        # the rear seats' screen
    g.obj("interior.screens", "screen")
    g = Geo()
    for y in (0.103, -0.103):
        g.box((-0.30, y, 0.632), (1.80, 0.004, 0.004))
    g.obj("led.cabin", "led_accent")


# ---------------------------------------------------------------------------------------
# wheels: an all-terrain tire of the car's own on the kit's twin-spoke rim
# ---------------------------------------------------------------------------------------
N_LUG = 30
TIRE_TEXT = "HALCYON  TERRA  A/T    285/50 R22    "


def at_tire(tag, cx, side):
    R, w, Rr = T_R, T_W, T_RIM
    hw = w / 2
    flip = side < 0
    loc = (cx, side * (T_OUT - hw), R)
    Rb = R - 0.013
    half = [(0.0, Rb), (hw - 0.032, Rb), (hw - 0.008, Rb - 0.016), (hw + 0.006, R - 0.045),
            (hw + 0.010, R - 0.065), (hw + 0.010, Rr + 0.045), (hw + 0.005, Rr + 0.024),
            (hw + 0.002, Rr + 0.012), (hw - 0.008, Rr + 0.004), (hw - 0.026, Rr - 0.006)]
    g = Geo()
    g.lathe([(-y, r) for y, r in half[:0:-1]] + half, 96)

    def pt(th, t, y, r):
        a = th + t / R
        return (r * cos(a), y, r * sin(a))
    pitch = 2 * pi * R / N_LUG
    for k in range(N_LUG):
        th = 2 * pi * k / N_LUG
        for sg, off in ((1, 0.0), (-1, 0.5)):               # shoulder blocks, down the wall
            t0 = off * pitch
            t1 = t0 + 0.052
            sk = 0.014
            yi, yo, ys = sg * 0.082, sg * (hw + 0.001), sg * (hw + 0.0155)
            g.hexa([pt(th, t0, yi, Rb - 0.006), pt(th, t1, yi, Rb - 0.006),
                    pt(th, t1 - sk, ys, R - 0.072), pt(th, t0 - sk, ys, R - 0.072),
                    pt(th, t0, yi, R), pt(th, t1, yi, R),
                    pt(th, t1 - sk, yo, R - 0.011), pt(th, t0 - sk, yo, R - 0.011)])
            # the middle rows: two blocks a pitch, leaning into a chevron
            t0 = (off + 0.5) * pitch
            for q in range(2):
                ta = t0 + q * pitch * 0.5
                tb = ta + 0.03
                ya, yb = sg * 0.008, sg * 0.068
                lean = 0.016
                g.hexa([pt(th, ta, ya, Rb - 0.006), pt(th, tb, ya, Rb - 0.006),
                        pt(th, tb - lean, yb, Rb - 0.006), pt(th, ta - lean, yb, Rb - 0.006),
                        pt(th, ta, ya, R), pt(th, tb, ya, R),
                        pt(th, tb - lean, yb, R), pt(th, ta - lean, yb, R)])
    ob = g.obj("tire." + tag, "rubber", flip_y=flip, loc=loc)
    ob.data.shade_smooth()
    ob.data.set_sharp_from_angle(angle=rad(30))
    # sidewall lettering, reading the right way round on both sides
    g = Geo()
    rt = (R - 0.065 + Rr + 0.045) / 2
    sgn = 1 if not flip else -1
    a = rad(90) - sgn * 0.62
    for rep in range(2):
        for ch in TIRE_TEXT:
            if ch == " ":
                a += sgn * 0.012 / rt
                continue
            vs, fs = K.text_mesh(ch, 0.028)
            x0, x1 = min(v.x for v in vs), max(v.x for v in vs)
            adv = (x1 - x0) + 0.004
            am = a + sgn * (adv / 2) / rt
            rad_ = V3((cos(am), 0, sin(am)))
            rgt = V3((-sin(am), 0, cos(am))) * sgn
            o = rad_ * rt + V3((0, hw + 0.0112, 0))
            g.add([o + rgt * (v.x - (x0 + x1) / 2) + rad_ * v.y for v in vs], fs)
            a += sgn * adv / rt
        a = rad(270) - sgn * 0.62
    g.obj("tiretext." + tag, "tiremark", flip_y=flip, loc=loc)


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 0.80, 0.30))
K.VIEWS.update(
    nose=dict(dir=(1.0, 0.45, 0.10), lens=85, target=(2.2, 0.45, 0.6), dist=3.2),
    tail=dict(dir=(-1.0, -0.4, 0.14), lens=85, target=(-2.3, -0.3, 0.8), dist=3.4),
    wheel=dict(dir=(0.35, 1.0, 0.10), lens=85, target=(FA_X, 0.9, 0.5), dist=3.0),
)


def main():
    K.materials(paint=(0.50, 0.085, 0.006), paint_finish=(0.62, 0.30, 1.0), dust_amount=0.3,
                paint2=(0.42, 0.072, 0.006), paint2_finish=(0.55, 0.55, 0.0),
                dust_z=(0.18, 0.70), glass=(0.50, 0.54, 0.58), led_front=(0.80, 0.94, 1.0),
                led_accent=(0.45, 0.92, 1.0), caliper=(0.74, 0.75, 0.73),
                seat=(0.40, 0.38, 0.34), interior=(0.022, 0.022, 0.025),
                screen=(0.30, 0.75, 1.0), decal=(0.70, 0.71, 0.72))
    m, b = K.carbon("carbon_dry")                           # bare weave: no coat to mirror
    b.inputs["Coat Weight"].default_value = 0.0             # the top light on the spine
    for nd in m.node_tree.nodes:
        if nd.type == 'MAP_RANGE':
            nd.inputs["To Min"].default_value = 0.42
            nd.inputs["To Max"].default_value = 0.66
    K.pbr("tow", (0.10, 0.62, 0.72), 0.9, 0.34)             # anodized tow eyes
    K.pbr("skid", (0.40, 0.41, 0.43), 1.0, 0.42)            # the skid plates' bare alloy
    K.pbr("tiremark",(0.085, 0.085, 0.085), 0.0, 0.6)
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
            K.build_wheel(tag, cx, T_R, T_W, T_RIM, T_OUT, side, spokes=7, tire=None)
            at_tire(tag, cx, side)
    K.log("wheels")
    K.shoot(extra="top")


main()
