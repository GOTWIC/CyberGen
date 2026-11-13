"""Orrin Aria: a two-seat hypercar poured as five drops (both names made up), built on
vehicles/carkit.py.

Run (always through the wrapper, one Blender job at a time on this machine):
    vehicles/blender.sh vehicles/cars/orrin_aria.py --out DIR --preview
    vehicles/blender.sh vehicles/cars/orrin_aria.py --out DIR --sheet [--night]

Five closed bodies with no crease anywhere, each a ring cage that closes on a pole at both
ends, as the Lumen's and the Pebble's hulls do:
  core    the cabin and the low nose: a teardrop from the nose pole to the tail pole, its two
          top lines the glass canopy, pole to pole;
  pods    a front fender each side (a tube beside the nose, free of it ahead of the axle) and
          a rear hip each side (a tube that stands clear of the cabin: the channel);
  yoke    one hoop over the glass behind the heads whose two legs fly back over the channels
          and sink into the hips' crests: the flying buttresses.
A blade under the nose (the through-duct's floor) and a blade across the three tails tie the
drops together; faired arms cross the channels at the rear axle. The light ribbons are
channels cut into the skin, each piece its own (core round the nose, the pods from behind
the wheels round their tips and up the slots, the buttresses and the hips' crests), a light
guide in each under a flush lens; the crescents, the door pulls, the charge flaps, the side
markers and the lidded wheel wells are cut too (the *_cutters functions, on each piece as it
stands uncut). Hairlines and dot fields lie on the surface as built (snap). The brand's
helpers are in vehicles/brands/orrin.py.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                                  # noqa: E402
from brands import orrin                                            # noqa: E402
from brands.orrin import (both, dot_field, lid_cutter, lune_cut, ring, snap,  # noqa: E402
                          spline, stone, strip, text_proj)
from carkit import Geo, Matrix, V3, cos, on_body, pi, rad, sin, text_flat   # noqa: E402

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.40, -1.35            # axles: wheelbase 2.75
R, RIM = 0.38, 0.30                 # tire radius, rim radius
F_W, R_W = 0.265, 0.31              # tire widths
F_OUT, R_OUT = 0.940, 0.955         # outer face of the tires
F_LID, R_LID = 0.60, 0.565          # top of the wheel openings: the body lids the wheels
NOSE = V3((2.345, 0, 0.405))        # the poles the core closes on
TAIL = V3((-2.375, 0, 0.53))

# ---------------------------------------------------------------------------------------
# the core: stations (rings) and lines
# ---------------------------------------------------------------------------------------
LINES = "CGESULRB"
#        C top centerline, G mid canopy, E canopy edge, S shoulder, U widest, L lower flank,
#        R rocker, B floor centerline
ORDER = ["P0", "N1", "N2", "A1", "FA", "A3", "D1", "M1", "D2", "B1", "RA", "R3", "T1", "T0"]
PT = {}


def stations():
    T = {
        # the nose: a slim drop held between the fender pods, its belly lifted off the blade
        "N1": ring(2.295, .462, (.05, .46), (.10, .455), (.155, .438), (.185, .405), (.155, .372),
                   (.09, .352), .347),
        "N2": ring(2.08, .515, (.09, .512), (.18, .502), (.27, .48), (.315, .435), (.285, .375),
                   (.17, .335), .325),
        "A1": ring(1.75, .578, (.14, .573), (.28, .558), (.39, .522), (.44, .45), (.41, .34),
                   (.27, .265), .255),
        "FA": ring(FA_X, .665, (.19, .658), (.37, .634), (.52, .585), (.62, .47), (.60, .30),
                   (.44, .17), .15),
        "A3": ring(1.05, .81, (.24, .795), (.45, .735), (.62, .67), (.72, .50), (.70, .29),
                   (.57, .14), .13),
        # the door cuts fan like petals: forward at the top, back at the top
        "D1": ring((.81, .81, .79, .755, .70, .66, .64, .64), .975, (.29, .948), (.52, .805),
                   (.70, .715), (.795, .515), (.78, .285), (.66, .135), .13),
        "M1": ring(0.20, 1.14, (.33, 1.097), (.575, .835), (.74, .725), (.83, .52), (.81, .285),
                   (.69, .135), .13),
        "D2": ring((-.40, -.40, -.375, -.34, -.30, -.275, -.265, -.265), 1.12, (.305, 1.078),
                   (.50, .86), (.615, .745), (.70, .53), (.685, .295), (.60, .145), .135),
        # behind the seats the core draws in to a slim tail: the cabin stands free of the hips
        "B1": ring(-0.82, .995, (.225, .965), (.345, .815), (.405, .71), (.44, .53), (.43, .32),
                   (.37, .17), .15),
        "RA": ring(RA_X, .825, (.15, .805), (.24, .715), (.29, .655), (.325, .53), (.315, .36),
                   (.26, .225), .195),
        "R3": ring(-1.86, .685, (.095, .675), (.16, .635), (.20, .60), (.22, .53), (.205, .435),
                   (.155, .345), .315),
        "T1": ring(-2.24, .592, (.04, .589), (.075, .58), (.095, .562), (.105, .53), (.095, .50),
                   (.065, .476), .468),
    }
    for name, src, pole in (("P0", "N1", NOSE), ("T0", "T1", TAIL)):
        T[name] = [(pole.x, p[1] * 0.22, pole.z + (p[2] - pole.z) * 0.22) for p in T[src]]
    S = K.fill([T[k] for k in ORDER])
    PT.update(K.table(ORDER, LINES, S))
    return S


PMAT = dict(front="paint", door="paint", sill="paint", rear="paint", glass="glass_dome",
            floor="underbody", well="well", slot="void", pod="paint", hip="paint", yoke="paint",
            cut="void", lamp_n="lamp_housing", lamp_p="lamp_housing", lamp_y="lamp_housing",
            lamp_h="lamp_housing", lamp_m="lamp_housing")
GAP = 0.0012                        # 2.4 mm shut lines, the kit's (the Pebble found 3.5 mm
                                    # opening dark tears round its cuts in a pack's far LODs)
LAMP = {}                           # the ribbons' channels on the skin: [(point, way out)]
RIB_W, RIB_D, RIB_TIP = 0.016, 0.009, 0.005     # a ribbon channel's width, depth, end width
LENS_SINK = 0.0012                  # the lenses under the skin: the nose's tight curve across
                                    # the channel stood a flush lens's edges proud
# the triangle budget (step A: 501,460 of 400,000): the pods and hips at subdivision 3, the
# yoke (a slim section) at 2, the channels sampled every CHAN_STEP and their lamps every
# LAMP_STEP, the liner (under the glass) at subdivision 2, the tires' tread at 80 segments
# (a 0.3 mm chord on its round), the stones hidden under the seats coarser
SUBDIV_POD, SUBDIV_YOKE = 3, 2
CHAN_STEP, LAMP_STEP = 0.018, 0.02
TREAD = dict(K.TREADS["road"], seg=80)


def panel_of(i, j):
    if j == 6 and 3 <= i <= 10:
        return "floor"
    if j <= 1:                           # the canopy: from the nose pole to the tail pole
        return "glass"
    if i <= 5:
        return "front"
    if i <= 7:
        return "sill" if j == 5 else "door"
    return "rear"


# ---------------------------------------------------------------------------------------
# the pods: tubes of egg sections that close on a pole at both ends
# ---------------------------------------------------------------------------------------
POD_M = 12
#          x     yc    zc    out   in    up    down
FRONT = [(2.24, .800, .345, .100, .100, .085, .075),
         (2.05, .800, .365, .170, .160, .200, .160),
         (1.78, .800, .410, .215, .210, .340, .215),
         (FA_X, .800, .430, .225, .235, .450, .250),
         (1.02, .795, .430, .215, .225, .370, .250),
         (0.72, .780, .440, .170, .190, .250, .230),
         (0.42, .745, .450, .110, .120, .150, .160)]
FRONT_POLES = (V3((2.305, .80, .34)), V3((0.20, .70, .46)))
HIP = [(-0.24, .910, .430, .080, .080, .100, .100),
       (-0.52, .885, .430, .140, .140, .250, .230),
       (-0.92, .825, .430, .210, .230, .400, .260),
       (RA_X, .800, .430, .240, .250, .470, .270),
       (-1.80, .775, .450, .235, .220, .400, .250),
       (-2.12, .730, .500, .180, .160, .210, .170),
       (-2.28, .690, .520, .090, .085, .085, .075)]
HIP_POLES = (V3((-0.12, .915, .43)), V3((-2.345, .675, .525)))


def egg(x, yc, zc, ro, ri, ru, rd, n=2.8, m=POD_M):
    """A ring about the x axis at x: an egg with its own radius out, in, up and down."""
    def pw(v):
        return (abs(v) ** (2.0 / n)) * (1 if v >= 0 else -1)
    out = []
    for k in range(m):
        t = 2 * pi * k / m
        c, s = sin(t), cos(t)
        out.append((x, yc + (ro if c >= 0 else ri) * pw(c), zc + (ru if s >= 0 else rd) * pw(s)))
    return out


def pod_cage(rows, poles):
    S = [egg(*r) for r in rows]
    a, b = poles
    first = [(a.x, a.y + (p[1] - rows[0][1]) * 0.22, a.z + (p[2] - rows[0][2]) * 0.22)
             for p in S[0]]
    last = [(b.x, b.y + (p[1] - rows[-1][1]) * 0.22, b.z + (p[2] - rows[-1][2]) * 0.22)
            for p in S[-1]]
    return [first] + S + [last]


CORE = []                               # the core's panels: what the liner and the yoke snap to
ANG = list(range(-25, 206, 10))


def mirrored(tr):
    return [(V3((q.x, -q.y, q.z)), V3((n.x, -n.y, n.z))) for q, n in tr]


def channel(g, key, ctrl, taper, mirror, w=RIB_W, depth=RIB_D, tip=RIB_TIP):
    """A ribbon's channel cut along the curve through ctrl on the piece being built (the
    cutters' tree is that piece alone), its path kept in LAMP[key] (and key + "_r" for the
    mirror image) with its width function."""
    pts = orrin.on_skin(ctrl)
    ln = sum((b - a).length for a, b in zip(pts, pts[1:]))

    def wf(t, ln=ln):
        return orrin.taper_width(t, ln, w, tip, taper)
    LAMP[key] = (K.groove(g, pts, width=wf, depth=depth, step=CHAN_STEP, mirror=mirror),
                 wf)
    if mirror:
        LAMP[key + "_r"] = (mirrored(LAMP[key][0]), wf)


def core_cutters():
    """The core's cuts, laid on it as it stands uncut: the crescents under the nose pole,
    the door pulls, room beside the front tires (inside the fender pods), and the nose
    ribbon's channel round the nose from slot to slot."""
    slots, cav, chan = Geo(), Geo(), Geo()
    lune_cut(slots, (2.285, .17, .385), (2.10, .305, .40), (0.45, 0.85, -0.25), (0, 0, -1),
             0.030, 0.014, depth=0.035, flare=0.010)
    # the door pulls: a small crescent recess under each shoulder
    a, _ = snap((0.34, 0.80, 0.70))
    b, _ = snap((0.20, 0.80, 0.70))
    lune_cut(slots, a, b, (0, 1, 0.1), (0, 0, 1), 0.014, 0.004, depth=0.025, flare=0.006)
    K.well_cutter(cav, FA_X, R, 0.40, 0.655, ANG, depth=0.40)
    tree = K._tree(None)                # its edge on the core, told to the checks: a cut on
    for sgn in (1, -1):                 # purpose, inside the pod
        Q = []
        for a in ANG:
            hit = tree.ray_cast(V3((FA_X + 0.40 * cos(rad(a)), sgn * 1.5,
                                    R + 0.40 * sin(rad(a)))), V3((0, -sgn, 0)), 1.0)[0]
            if hit is not None and abs(hit.y) > 0.655:
                Q.append(hit)
        if len(Q) > 1:
            K.CUTS.append(Q)
    half = [(1.565, .525, .456), (1.62, .50, .455), (1.76, .455, .45), (1.95, .375, .44),
            (2.10, .32, .43), (2.24, .24, .42), (2.31, .14, .41), (NOSE.x + 0.01, 0, NOSE.z + 0.012)]
    channel(chan, "nose", both(half), (0.05, 0.05), False)
    LAMP["peb.nose"] = snap((NOSE.x + 0.05, 0, NOSE.z + 0.02))
    LAMP["peb.tail"] = snap((TAIL.x - 0.05, 0, TAIL.z + 0.02))
    return [(slots, "slot"), (cav, "well"), (chan, "lamp_n")]


def arch_cutter(g, cx, r_side, r_top, y0, depth, cz=R):
    """A wheel well (as K.well_cutter, both sides) whose arch is r_side at its sides and
    r_top at its top: room at the tire's front and back, under a crown that falls away
    close over it."""
    for sgn in (1, -1):
        pts = []
        for a in ANG:
            r = r_side - (r_side - r_top) * max(0.0, sin(rad(a))) ** 4
            pts.append(V3((cx + r * cos(rad(a)), sgn * y0, cz + r * sin(rad(a)))))
        poly = [V3((pts[0].x, sgn * y0, -0.3))] + pts + [V3((pts[-1].x, sgn * y0, -0.3))]
        g.prism(poly, (0, sgn * depth, 0))


def lid_outline(cx, top, a=0.425, z0=0.31, n=2.6, y0=0.92):
    """The wheel opening lid_cutter() cuts, traced on the skin as it stands uncut and told
    to the checks (K.CUTS): an opening on purpose."""
    tree = K._tree(None)
    b = top - z0
    for sgn in (1, -1):
        Q = []
        for k in range(29):
            t = pi * k / 28
            c, s_ = cos(t), sin(t)
            p = V3((cx + a * (abs(c) ** (2 / n)) * (1 if c >= 0 else -1), sgn * 1.5,
                    z0 + b * (s_ ** (2 / n))))
            hit = tree.ray_cast(p, V3((0, -sgn, 0)), 1.0)[0]
            if hit is not None:
                Q.append(hit)
        if len(Q) > 1:
            K.CUTS.append(Q)


def pod_cutters():
    """The front fender pods' cuts: the wheel wells (with room beside the tires) and lids,
    the crescent in each wheel's wake, the ribbon's channel from behind the wheel over its
    lid, round the pod's tip and back up the slot."""
    cav, cav2, cav3, lids, slots, chan = Geo(), Geo(), Geo(), Geo(), Geo(), Geo()
    # the well: an arch lower at its top reaching in beside the tire's inner sidewall (under
    # the pod's inner crown), the full one from the tire's face out, and the outer part lower
    # at its top again where the pod's crown falls away (the old one broke through the skin
    # over the tire). Each its own cutter, no two ending on one plane (the boolean then
    # emptied a pod).
    arch_cutter(cav, FA_X, 0.405, 0.392, 0.655, 0.80 - 0.655)
    cav4, cav5 = Geo(), Geo()
    K.well_cutter(cav4, FA_X, R, 0.405, 0.685, ANG, depth=0.87 - 0.685)
    arch_cutter(cav2, FA_X, 0.405, 0.392, 0.86, 0.915 - 0.86)
    arch_cutter(cav5, FA_X, 0.405, 0.372, 0.905, F_OUT + 0.008 - 0.905)
    K.well_cutter(cav3, FA_X, R, 0.36, 0.93, ANG, depth=F_OUT + 0.022 - 0.93)
    lid_cutter(lids, FA_X, F_LID)
    lid_outline(FA_X, F_LID)
    lune_cut(slots, (0.905, .97, .30), (0.955, .97, .63), (0, 1, 0), (-1, 0, 0), 0.058, 0.028,
             depth=0.05, flare=0.018)                               # the wheel's wake
    half = [(0.62, .92, .535), (0.86, .975, .665), (1.12, 1.025, .69), (FA_X, 1.04, .69),
            (1.70, 1.03, .655), (1.95, 1.0, .56), (2.14, .96, .45), (2.27, .90, .37),
            (2.32, .80, .335), (2.27, .70, .355), (2.14, .625, .395), (1.95, .585, .425),
            (1.74, .575, .445), (1.60, .578, .452)]
    channel(chan, "pod", half, (0.40, 0.05), True)
    return [(cav, "well"), (cav4, "well"), (cav2, "well"), (cav5, "well"), (cav3, "well"),
            (lids, "well"),
            (slots, "slot"), (chan, "lamp_p")]


def hip_cutters():
    """The rear hips' cuts: the wheel wells (with room beside the tires) and lids, the
    paired intakes, the charge flap (left) and a service flap (right) on the hip's nose, the
    side markers and the tail ribbon's channel along the crest (from under the buttress)
    round the hip's tip."""
    cav, cav2, cav3, lids, slots, chan, mark, cut = (Geo(), Geo(), Geo(), Geo(), Geo(), Geo(),
                                                     Geo(), Geo())
    # the well as the pod's: lower at its top at both sides, where the hip's crown falls away
    # (the old one broke through the skin over the tire into the channel)
    arch_cutter(cav, RA_X, 0.405, 0.392, 0.63, 0.75 - 0.63)
    cav4, cav5 = Geo(), Geo()
    K.well_cutter(cav4, RA_X, R, 0.405, 0.69, ANG, depth=0.87 - 0.69)
    arch_cutter(cav2, RA_X, 0.405, 0.392, 0.86, 0.93 - 0.86)
    arch_cutter(cav5, RA_X, 0.405, 0.372, 0.92, R_OUT + 0.008 - 0.92)
    K.well_cutter(cav3, RA_X, R, 0.36, 0.93, ANG, depth=R_OUT + 0.022 - 0.93)
    lid_cutter(lids, RA_X, R_LID)
    lid_outline(RA_X, R_LID)
    for x0 in (-0.845, -0.775):                                     # paired crescents: intakes
        lune_cut(slots, (x0 + 0.03, 1.0, .31), (x0 - 0.02, 1.0, .60), (0, 1, 0), (1, 0, 0),
                 0.044, 0.022, depth=0.045, flare=0.014)
    # round the hip's tip in a wide turn, drawn out to the tail blade's light bar's height
    # (turned tight, the channel folded into chips at the tip)
    crest = [(-1.55, .785, .95), (-1.72, .78, .93), (-1.90, .775, .90), (-2.08, .745, .80),
             (-2.22, .715, .70), (-2.30, .70, .63), (-2.345, .69, .57), (-2.36, .665, .535),
             (-2.345, .63, .52), (-2.31, .595, .52)]
    channel(chan, "hip", crest, (0.05, 0.14), True, tip=0.008)
    channel(mark, "mark", [(-1.84, 1.05, .47), (-1.93, 1.0, .475), (-2.02, .95, .48)],
            (0.04, 0.04), True, w=0.008, depth=0.006, tip=0.003)
    K.groove(cut, [(PORT[0] + PORT[2] * cos(rad(a)), PORT[1] + PORT[2] * sin(rad(a)))
                   for a in range(5, 365, 10)], 'y', closed=True, mirror=True, round=2)
    chan.add(mark.v, mark.f)
    # the light ring in each flap, seated on the skin as it stands uncut (snapped after the
    # cut, its points fell into the flap's shut line)
    LAMP["port"] = [[on_body(PORT[0] + 0.040 * cos(rad(a)), PORT[1] + 0.040 * sin(rad(a)),
                             proj) for a in range(0, 361, 10)] for proj in ('y', 'Y')]
    return [(cav, "well"), (cav4, "well"), (cav2, "well"), (cav5, "well"), (cav3, "well"),
            (lids, "well"),
            (slots, "slot"), (chan, "lamp_h"), (cut, "cut", "drop")]


PORT = (-0.42, 0.50, 0.054)         # the charge flap on each hip's nose: x, z, radius


def finish_channels(body, parts):
    """A channel's walls cut into 4.5 cm pieces and made a 1 mm sheet (the Pebble's way: a
    game pack keeps them as a panel, and drops the pieces from its far LODs cleanly)."""
    for pn, keys in parts:
        ob = body.parts.get(pn)
        if ob is None:
            continue
        for key in keys:
            if key in LAMP:
                orrin.chop(ob, LAMP[key][0])
        md = ob.modifiers.new("solid", 'SOLIDIFY')
        md.thickness = 0.001
        md.offset = 0.0


def build_hull():
    # ---- the core
    body = K.build_body(stations(), panel_of, PMAT, 0.0, 0.0,
                        front=dict(kind="flat", panel="front", crease=0.0),
                        rear=dict(kind="flat", panel="rear", crease=0.0),
                        cutters=core_cutters, subdiv=4, thick=0.004, gap=GAP)
    CORE.extend(ob for pn, ob in body.parts.items() if pn not in ("slot", "lamp_n"))
    finish_channels(body, [("lamp_n", ("nose",))])
    # ---- the front fender pods
    body = K.build_body(pod_cage(FRONT, FRONT_POLES), lambda i, j: "pod", PMAT, 0.0, 0.0,
                        name="pod", front=dict(kind="flat", panel="pod", crease=0.0),
                        rear=dict(kind="flat", panel="pod", crease=0.0), wrap=True,
                        cutters=pod_cutters, subdiv=SUBDIV_POD, thick=0.004, gap=GAP)
    finish_channels(body, [("lamp_p", ("pod", "pod_r"))])
    # ---- the rear hips
    body = K.build_body(pod_cage(HIP, HIP_POLES), lambda i, j: "hip", PMAT, 0.0, 0.0,
                        name="hip", front=dict(kind="flat", panel="hip", crease=0.0),
                        rear=dict(kind="flat", panel="hip", crease=0.0), wrap=True,
                        cutters=hip_cutters, subdiv=SUBDIV_POD, thick=0.004, gap=GAP)
    finish_channels(body, [("lamp_h", ("hip", "hip_r", "mark", "mark_r"))])


# ---------------------------------------------------------------------------------------
# the yoke: a hoop over the glass, its legs the flying buttresses
# ---------------------------------------------------------------------------------------
#        x      y      z (None: on the core's skin)  half width, half thickness
YOKE = [(-0.30, 0.00, None, .066, .019),
        (-0.31, 0.16, None, .070, .020),
        (-0.34, 0.31, None, .080, .023),
        (-0.42, 0.445, .990, .094, .028),
        (-0.57, 0.555, .962, .105, .034),
        (-0.80, 0.640, .938, .108, .038),
        (-1.07, 0.705, .918, .112, .042),
        (RA_X, 0.770, .895, .125, .055),
        (-1.68, 0.775, .835, .120, .060)]
YOKE_POLE = V3((-2.0, 0.76, 0.74))


def build_yoke():
    tree = K.body_bvh(CORE, default=False)
    P, N = [], []
    for x, y, z, _, _ in YOKE:
        if z is None:
            loc, n, _, _ = tree.ray_cast(V3((x, y, 3.0)), V3((0, 0, -1)))
            n = n if n.z > 0 else -n
            P.append(loc + n * 0.010)
            N.append(V3((0, n.y, n.z)).normalized() if y == 0 else n)
        else:
            P.append(V3((x, y, z)))
            N.append(V3((0, 0.22, 1)).normalized())
    N[3] = (N[2] + N[4]).normalized()
    S = []
    for i, (x, y, z, hw, ht) in enumerate(YOKE):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        if i == 0:
            t = V3((0, 1, 0))
        w = t.cross(N[i]).normalized()
        n = w.cross(t).normalized()
        ringp = []
        for k in range(8):
            a = 2 * pi * k / 8
            c, s = cos(a), sin(a)
            p = P[i] + w * (hw * abs(c) ** 0.8 * (1 if c >= 0 else -1)) \
                + n * (ht * abs(s) ** 0.8 * (1 if s >= 0 else -1))
            ringp.append((p.x, 0.0 if i == 0 else p.y, p.z))
        S.append(ringp)
    c = P[-1]
    S.append([tuple(YOKE_POLE + (V3(p) - c) * 0.25) for p in S[-1]])

    def cutters():
        """The tail ribbon's channel along the top of each buttress, from the roof down to
        where the leg sinks into the hip (the hip's own channel goes on from under it)."""
        chan = Geo()
        crest = [P[i] + N[i] * 0.08 for i in range(2, len(P))]
        crest += [V3((-1.80, .772, .87)), V3((-1.90, .768, .83)), V3((-1.97, .763, .79))]
        # full width to its end, inside the hip: it runs into the hip's channel
        channel(chan, "yoke", crest, (0.35, 0.0), True)
        return [(chan, "lamp_y")]
    body = K.build_body(S, lambda i, j: "yoke", PMAT, 0.0, 0.0, name="yoke", front=None,
                        rear=dict(kind="flat", panel="yoke", crease=0.0), wrap=True,
                        subdiv=SUBDIV_YOKE, thick=0.004, cutters=cutters, gap=GAP)
    finish_channels(body, [("lamp_y", ("yoke", "yoke_r"))])
    return P, N


# ---------------------------------------------------------------------------------------
# things lying on the surface as built
# ---------------------------------------------------------------------------------------
def mir(pts, sgn):
    return [V3((p[0], sgn * p[1], p[2])) for p in pts]


LENS = [(0.5 * cos(rad(a)), 0.5 * sin(rad(a)) * abs(sin(rad(a))) ** 0.3)
        for a in range(0, 360, 20)]


def lens(cx, th):
    """A lens section: chord cx across, th thick."""
    return [(cx * a, th * b) for a, b in LENS]


def build_blades():
    # ---- under the nose: the floor of the through-duct, from pod to pod
    g = Geo()
    path = [(2.06 - 0.10 * (y / 0.70) ** 2, y, 0.172 + 0.075 * (y / 0.70) ** 4)
            for y in (-0.70, -0.6, -0.4, -0.2, 0, 0.2, 0.4, 0.6, 0.70)]
    g.sweep(spline(path, 5), lens(0.30, 0.030), up=(0, 0, 1))
    ob = g.obj("blade.nose", "paint", sharp=50)
    # ---- across the three tails
    g = Geo()
    path = [(-2.262 + 0.02 * (y / 0.63) ** 2, y, 0.526) for y in
            (-0.63, -0.5, -0.3, -0.12, 0, 0.12, 0.3, 0.5, 0.63)]
    g.sweep(spline(path, 5), lens(0.12, 0.022), up=(0, 0, 1))
    g.obj("blade.tail", "paint", sharp=50)
    g = Geo()
    g.sweep(spline([(p[0] - 0.060, p[1], p[2]) for p in path], 5),
            [(-0.004, -0.0045), (0.004, -0.0045), (0.004, 0.0045), (-0.004, 0.0045)],
            up=(0, 0, 1))
    g.obj("led.tailblade", "led_rear")
    # ---- faired arms across each channel at the rear axle (the hips hang on them)
    g = Geo()
    for sgn in (1, -1):
        for x, z in ((RA_X + 0.14, 0.275), (RA_X - 0.14, 0.275), (RA_X, 0.50)):
            g.sweep(mir([(x, 0.26, z), (x, 0.45, z + 0.006), (x, 0.66, z)], sgn),
                    lens(0.085, 0.022), up=(0, 0, 1))
    g.obj("arms", "wheel_face", sharp=50)
    return ob


def build_lights():
    """The ribbons: in each channel under its flush lens a light guide's lit face over a
    frosted sleeve (orrin.channel_lamp), white round the nose and the fender pods, red along
    the buttresses and the hips' crests; the lit pebbles on the poles, seated on the skin as
    it stood before the cuts."""
    for key, lit, lens in (("nose", "led_front", "lens_clear"), ("pod", "led_front", "lens_clear"),
                           ("pod_r", "led_front", "lens_clear"), ("yoke", "led_rear", "lens_red"),
                           ("yoke_r", "led_rear", "lens_red"), ("hip", "led_rear", "lens_red"),
                           ("hip_r", "led_rear", "lens_red"), ("mark", "led_rear", "lens_red"),
                           ("mark_r", "led_rear", "lens_red")):
        tr, wf = LAMP[key]
        depth = 0.006 if key.startswith("mark") else RIB_D
        orrin.channel_lamp("lamp." + key, tr, wf, depth, GAP, lit=lit, lens=lens,
                           step=LAMP_STEP, sink=LENS_SINK)
    g = Geo()
    orrin.seated(g, LAMP["peb.nose"], 0.040, 0.030, 0.008)
    g.obj("led.front", "led_front", sharp=50)
    g = Geo()
    orrin.seated(g, LAMP["peb.tail"], 0.036, 0.030, 0.008)
    g.obj("led.rear", "led_rear", sharp=50)


def build_details():
    P = PT
    # ---- petal doors: hairlines over the glass on the door cuts, joined along the canopy
    g = Geo()
    for sgn in (1, -1):
        for st in ("D1", "D2"):
            strip(g, mir([P[st]["E"], P[st]["E"].lerp(P[st]["G"], 0.5), P[st]["G"]], sgn),
                  0.005, lift=0.0012, n=8)
        strip(g, mir([P[st]["G"] for st in ("D1", "M1", "D2")], sgn), 0.005, lift=0.0012, n=10)
    g.obj("glass.lines", "gloss_black", sharp=50)
    # ---- the charge port: a ring of light on the left hip's nose, in its flap
    g = Geo()
    for seats in LAMP["port"]:
        vs = []
        for i, (q, n) in enumerate(seats):
            t = (seats[(i + 1) % (len(seats) - 1)][0] - seats[i - 1][0]).normalized()
            sd = n.cross(t).normalized() * 0.0025
            vs += [q + n * 0.0003 + sd, q + n * 0.0012 + sd, q + n * 0.0012 - sd,
                   q + n * 0.0003 - sd]
        m = len(seats)
        g.add(vs, [(4 * i + j, 4 * i + (j + 1) % 4, 4 * i + 4 + (j + 1) % 4, 4 * i + 4 + j)
                   for i in range(m - 1) for j in range(4)])
    g.obj("led.port", "led_accent", sharp=50)
    # ---- where it breathes: dot lenses on the pods' fronts and the hips' tails
    g = Geo()
    for sgn in (1, -1):
        dot_field(g, 'x', sgn * 0.80, 0.262, 0.15, 0.028, pitch=0.011, rmax=0.0038)
        dot_field(g, 'X', sgn * 0.705, 0.425, 0.12, 0.030, pitch=0.011, rmax=0.0038)
    g.obj("dots", "void")
    # ---- lettering: one small word each
    g = Geo()
    for side in (1, -1):
        text_proj(g, "aria", 0.034, 0.26, 0.335, 'y' if side > 0 else 'Y', spacing=1.3)
    K.text_on_body(g, "orrin", 0.026, -0.30, 0.0, 1, proj='z', turn=90, spacing=1.4)
    g.obj("lettering", "decal")
    # ---- camera pods where mirrors would be (on the fenders' tails), sensors on the nose
    g, gl = Geo(), Geo()
    for sgn in (1, -1):
        loc, n = snap((0.74, sgn * 1.0, 0.72))
        fwd = V3((1, 0, 0.05)).normalized()
        xf = (Matrix.Translation(loc + n * 0.006)
              @ V3((0, 1, 0)).rotation_difference(fwd).to_matrix().to_4x4())
        prof = [(-0.10 * cos(rad(a)), 0.024 * sin(rad(a)) ** 0.8 + 0.0005)
                for a in range(0, 181, 12)]
        g.lathe(prof, 24, xf=xf)
        gl.lathe([(-0.101, 0.001), (-0.101, 0.010), (-0.097, 0.012), (-0.097, 0.001)], 16, xf=xf)
        for y in (0.07, 0.13):
            loc, n = on_body(sgn * y, 0.372, 'x')
            if loc is not None:
                K.stud(gl, loc, n, [(-0.002, 0.001), (-0.002, 0.008), (0.0012, 0.008),
                                    (0.0012, 0.001)], 14)
    g.obj("cameras", "paint", sharp=40)
    gl.obj("camera.lens", "gloss_black")


# ---------------------------------------------------------------------------------------
# interior: a liner under the long glass (nose deck, tub, tail deck), two seats of stones
# ---------------------------------------------------------------------------------------
def build_interior():
    tree = K.body_bvh(CORE, default=False)
    rows = [(2.26, None, .004), (2.10, None, .010), (1.75, None, .022), (FA_X, None, .034),
            (1.05, None, .045), (0.90, None, .05), (0.86, .17, 0), (0.80, .17, 0),
            (0.40, .17, 0), (0.0, .17, 0), (-0.38, .17, 0), (-0.46, .17, 0),
            (-0.50, None, .05), (-0.82, None, .04), (RA_X, None, .028), (-1.86, None, .014),
            (-2.20, None, .005)]
    S, rims = [], []
    for x, zf, drop in rows:
        rm = orrin.rim_at(x, tree, pt=PT, order=ORDER)
        rims.append(rm)
        zf = rm.z - drop if zf is None else zf
        deep = rm.z - zf > 0.2
        S.append([tuple(rm), (rm.x, rm.y * 0.95, zf + (rm.z - zf) * 0.45),
                  (rm.x, rm.y * (0.82 if deep else 0.86), zf), (rm.x, 0.0, zf)])
    hold = {5: 0.6, 6: 0.75, 7: 0.5, 10: 0.5, 11: 0.75, 12: 0.6}
    K.build_body(S, lambda i, j: "liner", dict(liner="liner"), 0.0,
                 lambda i, j: hold.get(i, 0.0), name="liner", project=False, subdiv=2)
    # ---- a hair of light under the glass round both tongues, the word under the nose glass
    g = Geo()
    sec = [(-0.0025, -0.002), (0.0025, -0.002), (0.0025, 0.002), (-0.0025, 0.002)]
    for part in (rims[:6], rims[:-6:-1]):
        half = [V3((p.x, p.y - 0.012, p.z - 0.004)) for p in part[::-1]]
        tip = part[0]
        half.append(V3((tip.x + (0.004 if tip.x > 0 else -0.004), 0, tip.z - 0.006)))
        g.sweep(spline(both(half), 8), sec, up=(0, 0, 1))
    a, b = V3((rims[3].x, 0, rims[3].z - 0.030)), V3((rims[4].x, 0, rims[4].z - 0.041))
    text_flat(g, "orrin", 0.040, a.lerp(b, 0.5) + V3((0, 0, 0.012)), (0, 1, 0),
              (b - a).normalized(), spacing=1.5)
    g.obj("led.cabin", "led_accent")
    # ---- two seats, each three stones; a spine between them
    g, gi = Geo(), Geo()
    back = Matrix.Rotation(rad(-24), 3, 'Y')
    for y in (0.325, -0.325):
        stone(g, (0.14, y, 0.305), (0.26, 0.225, 0.07), Matrix.Rotation(rad(-9), 3, 'Y'), n=3.0)
        stone(g, (-0.215, y, 0.60), (0.070, 0.215, 0.30), back, n=3.0)
        stone(g, (-0.375, y, 0.935), (0.045, 0.105, 0.070), back, n=2.6)
        stone(gi, (0.10, y, 0.215), (0.20, 0.18, 0.05), n=3.0, seg=20, rows=10)
    g.obj("interior.seats", "seat", sharp=60)
    stone(gi, (0.86, 0, 0.705), (0.085, 0.56, 0.040), Matrix.Rotation(rad(14), 3, 'Y'), n=3.2)
    stone(gi, (0.25, 0, 0.27), (0.50, 0.060, 0.095), n=3.0, seg=20, rows=10)
    yoke = (Matrix.Translation((0.66, 0.325, 0.665)) @ Matrix.Rotation(rad(-66), 4, 'Y')
            @ Matrix.Rotation(pi / 2, 4, 'X'))
    gi.lathe([(-0.010, 0.140), (0.0, 0.150), (0.010, 0.140), (0.0, 0.130)], 28, xf=yoke)
    gi.tube((0.69, 0.325, 0.66), (0.80, 0.325, 0.69), 0.018)
    gi.obj("interior.fittings", "interior", sharp=60)
    g = Geo()
    stone(g, (0.775, 0, 0.705), (0.012, 0.46, 0.022), Matrix.Rotation(rad(14), 3, 'Y'), n=4)
    g.obj("interior.screen", "screen", sharp=60)


# ---------------------------------------------------------------------------------------
# views of its own, and the build
# ---------------------------------------------------------------------------------------
K.VIEWS["hero"].update(dir=(1.0, 0.80, 0.40), focus=(1.4, 0.8, 0.5))
K.VIEWS["rear"].update(dir=(-1.0, -0.62, 0.42))
K.VIEWS.update(
    quarter=dict(dir=(-1.0, 0.55, 0.50), lens=70),
    nose=dict(dir=(1.0, 0.35, 0.35), lens=85, target=(2.0, 0.3, 0.42), dist=2.6),
    tail=dict(dir=(-1.0, 0.5, 0.45), lens=85, target=(-1.7, 0.4, 0.6), dist=3.2),
    channel=dict(dir=(0.5, 1.0, 0.7), lens=85, target=(-0.9, 0.6, 0.8), dist=3.2),
)


def second_tile(view="top", size=(1000, 470)):
    """A sixth tile on the sheet, in the hero's bottom right corner: the kit lays one extra
    tile only, and this car wants the rear three-quarter and the plan both."""
    sheet = os.path.join(K.ARGS.out, "sheet.jpg")
    if not K.ARGS.sheet or not os.path.exists(sheet):
        return
    tmp = os.path.join(K.ARGS.out, "x_%s.jpg" % view)
    K.render_view(view, tmp, size, K.ARGS.samples or 160, 0.05)
    k, th = (0.9, 0.8) if K.ARGS.night else (0.45, 0.86)
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import post; from PIL import Image; "
            "s = Image.open(sys.argv[2]).convert('RGB'); "
            "q = post.bloomed(Image.open(sys.argv[3]).convert('RGB'), %r, %r); "
            "x, y = s.width - q.width, %d - q.height; "
            "s.paste((14, 14, 16), (x - 4, y - 4, s.width, %d)); s.paste(q, (x, y)); "
            "s.save(sys.argv[2], quality=93)" % (k, th, K.SHEET_TOP, K.SHEET_TOP))
    subprocess.run([K._python(), "-c", code, K.HERE, sheet, tmp], check=True)
    os.remove(tmp)
    K.log("laid %s into the sheet" % view)


def main():
    K.materials(paint=(0.010, 0.010, 0.012), paint_finish=(0.80, 0.30, 0.9), dust_amount=0.06,
                glass=(0.60, 0.56, 0.50), led_front=(0.90, 0.95, 1.0),
                led_rear=(1.0, 0.035, 0.03), led_accent=(0.30, 0.82, 1.0),
                led_wheel=(0.30, 0.82, 1.0), seat=(0.42, 0.17, 0.06),
                interior=(0.030, 0.030, 0.032), screen=(0.30, 0.82, 1.0))
    K.pbr("wheel_face", (0.19, 0.195, 0.20), 1.0, 0.30)
    K.pbr("wheel_vane", (0.24, 0.245, 0.25), 1.0, 0.26)
    K.emit("led_rear", (1.0, 0.004, 0.002), 7.0)        # deeper than the kit's: a real red
    # the canopy's glass with a coating: the kit's glass mirrors the studio all over a dome
    K.pbr("glass_dome", (0.60, 0.56, 0.50), 0.0, 0.0,
          **{"Transmission Weight": 1.0, "IOR": 1.14})
    K.pbr("liner", (0.012, 0.012, 0.014), 0.0, 0.24)   # dark and glossy under the glass
    build_hull()
    build_yoke()
    K.log("hull")
    build_blades()
    build_lights()
    build_details()
    build_interior()
    K.log("details")
    for side, s in ((1, "l"), (-1, "r")):
        orrin.disc("f" + s, FA_X, F_OUT, side, R=R, W=F_W, rim=RIM, tread=TREAD)
        orrin.disc("r" + s, RA_X, R_OUT, side, R=R, W=R_W, rim=RIM, tread=TREAD)
    K.log("wheels")
    K.shoot(extra=dict(view="quarter", size=(1040, 585), corner="tl"))
    second_tile()


main()
