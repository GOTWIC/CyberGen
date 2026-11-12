"""Kestrel's shared helpers: the chine as built, the twin tail fins' plane, and the emitter
pods (a faceted housing on each side with its emitter collar and ring, vanes over a core,
the skid, the stern thruster, the ribbing and the emitter numbers).

Lifted from the Dart, the Meridian and the Atlas: chine, fin_pt, build_pod, pod_ribs,
POD_SEC. Differences kept by parameters:

- chine keeps its cache and its search reach (1.3 m): the kit's chine(x, objs, reach)
  searches to 1.6 m, does not cache and gives None where the body misses x, so its points
  differ in the last digits; Kestrel bodies keep this one.
- fin_pt: the fin's foot and up direction were the car's FIN_BASE and FIN_UP (base, up).
- build_pod: the pod's materials were the car's POD_MAT (mat); heavy=True gives the
  Atlas's heavy sled skid on braced legs and the ribbed outrigger arm over the pod, the
  default the Dart's and the Meridian's skid folded up beside the emitter.
- pod_ribs: the pods were the car's PODS (pods, tag to xc, yc, zc, L, s); chamfer=True
  adds the Dart's three short ribs on the top chamfer.

Covered by the kit: rib and plate are now carkit's rib() and plate() (the same code; the
Dart's, Meridian's and Atlas's copies build the same), re-exported here.

Left in the cars: fin_half (the Meridian's and the Atlas's fins taper by numbers of their
own, one line each), the Meridian's slab and the Atlas's strap (one car each), the hulls.
"""
import carkit as K
from carkit import Geo, Matrix, V3, on_body, rad, text_on_body

rib = K.rib
plate = K.plate

_CH = {}                # chine() by x (one car is built per process)


def chine(x):
    """The chine as built at x: the widest point of the hull seen from above."""
    key = round(x, 4)
    if key not in _CH:
        lo, hi = 0.0, 1.3
        for _ in range(18):
            mid = (lo + hi) / 2
            if on_body(x, mid, 'z')[0] is not None:
                lo = mid
            else:
                hi = mid
        loc = on_body(x, lo - 0.0015, 'z')[0]
        _CH[key] = V3((x, lo, loc.z)) if loc is not None else None
    return _CH[key]


def fin_pt(a, t, off=0.0, side=1, *, base, up):
    """A point of the fin's plane (its foot at base, leaning along up), a along x and t up
    the fin, off toward the outside; side -1 the right fin."""
    n = V3((1, 0, 0)).cross(up).normalized()        # inboard and up
    p = base + V3((a, 0, 0)) + up * t - n * off
    return V3((p.x, side * p.y, p.z))


# the pod's section (y, z) at s = 1: a flattened octagon
POD_SEC = [(-.11, .14), (.09, .14), (.19, .05), (.19, -.06), (.13, -.14), (-.13, -.14),
           (-.19, -.06), (-.19, .05)]


def build_pod(tag, xc, yc, zc, L, s, *, mat, heavy=False):
    """An emitter pod (mirrored) at (xc, yc, zc), L long, its section scaled by s; mat the
    pod's panels' materials (pod_top, pod_side, pod_low, pod_belly, pod_nose, tip_<tag>,
    vent, pod_frame, pod_end)."""
    def sec(x, ky=1.0, kz=1.0, dz=0.0):
        return [(x, yc + y * s * ky, zc + dz + z * s * kz) for (y, z) in POD_SEC]
    h = L / 2
    S = [sec(xc + h, 0.13, 0.40, 0.025 * s), sec(xc + h - 0.34 * s), sec(xc + 0.28 * s),
         sec(xc - 0.28 * s), sec(xc - h + 0.14 * s, 0.97, 0.97),
         sec(xc - h, 0.80, 0.78, 0.012 * s)]

    def pod_panel(i, j):
        if i == 0:
            return "pod_nose" if j in (7, 0, 1, 2, 6) else "pod_low"
        if j == 4:
            return "pod_belly"
        if j in (3, 5):
            return "pod_low"
        return "pod_side" if j in (2, 6) else "pod_top"

    K.build_body(S, pod_panel, mat, 1.0, 1.0, name="pod." + tag,
                 front=dict(kind="flat", panel="tip_" + tag),
                 rear=dict(center=(xc - h, yc, zc + 0.012 * s), depth=0.08 * s, band=0.022 * s,
                           frame="pod_frame", inner="pod_end", reach=0.05 * s),
                 recesses=[(2, 4, 0.022 * s, 0.03, "vent", "pod_belly")],
                 subdiv=1, wrap=True, project=False)
    zb = zc - 0.14 * s

    # the emitter: a collar under the pod, a glowing ring on its lip, vanes over a core
    ring = [(xc + 0.25 * s, yc, zb), (xc + 0.17 * s, yc + 0.098 * s, zb),
            (xc - 0.17 * s, yc + 0.098 * s, zb), (xc - 0.25 * s, yc, zb),
            (xc - 0.17 * s, yc - 0.098 * s, zb), (xc + 0.17 * s, yc - 0.098 * s, zb)]
    g = Geo()
    g.sweep(ring, [(-0.013, -0.030), (0.013, -0.030), (0.013, 0.004), (-0.013, 0.004)],
            closed=True)
    for k in range(6):                                  # clamps on the collar
        a, b = V3(ring[k]), V3(ring[(k + 1) % 6])
        c = a.lerp(b, 0.5)
        d = (b - a).normalized()
        o = V3((d.y, -d.x, 0))
        g.box(c + V3((0, 0, -0.012)), (0.05, 0.034, 0.03),
              rot=Matrix(((d.x, o.x, 0), (d.y, o.y, 0), (0, 0, 1))))
    g.obj("pod.collar." + tag, "rim", bevel=0.003, mirror=True)
    g = Geo()
    g.sweep(ring, [(-0.017, -0.048), (0.017, -0.048), (0.017, -0.030), (-0.017, -0.030)],
            closed=True)
    g.obj("pod.ring." + tag, "emitter", mirror=True)
    g = Geo()
    g.box((xc, yc, zb + 0.024), (0.47 * s, 0.17 * s, 0.004))
    g.obj("pod.core." + tag, "emitter_core", mirror=True)
    g = Geo()
    zv = zb + 0.004
    g.louvers((xc + 0.225 * s, yc - 0.085 * s, zv), (xc - 0.225 * s, yc - 0.085 * s, zv),
              (xc - 0.225 * s, yc + 0.085 * s, zv), (xc + 0.225 * s, yc + 0.085 * s, zv),
              9, 0.03, 0.004, rad(32), out=(0, 0, -1), margin=0.03)
    g.box((xc, yc, zv - 0.004), (0.50 * s, 0.014, 0.022))
    g.obj("pod.vanes." + tag, "grille", bevel=0.0015, mirror=True)

    if heavy:
        # the skid: a heavy sled outboard of the emitter on two braced legs, a pad at each end
        ys = yc + 0.172 * s
        zs = zb - 0.045
        g = Geo()
        g.sweep([(xc + 0.47 * s, ys, zb + 0.06), (xc + 0.38 * s, ys, zs),
                 (xc - 0.38 * s, ys, zs), (xc - 0.47 * s, ys, zb + 0.06)],
                [(-0.021, -0.013), (0.021, -0.013), (0.021, 0.013), (-0.021, 0.013)],
                up=(0, 1, 0))
        for x in (xc + 0.22 * s, xc - 0.22 * s):
            g.box((x, ys - 0.012, (zs + zb + 0.05) / 2), (0.05, 0.03, zb + 0.05 - zs))
            g.lathe([(-0.03, 0.002), (-0.03, 0.022), (0.03, 0.022), (0.03, 0.002)], 8,
                    xf=Matrix.Translation((x, ys - 0.012, zb + 0.05)))
            g.box((x, ys, zs - 0.012), (0.16, 0.06, 0.014))
        g.obj("pod.skid." + tag, "rim_bright", bevel=0.003, mirror=True)

        # the outrigger: a ribbed arm from the lower hull over the pod's back
        zt = zc + 0.14 * s
        g = Geo()
        g.hexa([(xc + 0.27 * s, 0.60, zt - 0.05), (xc - 0.27 * s, 0.60, zt - 0.05),
                (xc - 0.22 * s, yc + 0.02, zt - 0.02), (xc + 0.22 * s, yc + 0.02, zt - 0.02),
                (xc + 0.27 * s, 0.60, zt + 0.075), (xc - 0.27 * s, 0.60, zt + 0.075),
                (xc - 0.22 * s, yc + 0.02, zt + 0.028), (xc + 0.22 * s, yc + 0.02, zt + 0.028)])
        g.obj("pod.arm." + tag, "paint2", bevel=0.004, mirror=True)
        g = Geo()
        for k in range(7):
            x = xc + (0.18 - 0.06 * k) * s
            g.hexa([(x + 0.008, 0.66, zt + 0.062), (x - 0.008, 0.66, zt + 0.062),
                    (x - 0.008, yc + 0.01, zt + 0.024), (x + 0.008, yc + 0.01, zt + 0.024),
                    (x + 0.005, 0.66, zt + 0.078), (x - 0.005, 0.66, zt + 0.078),
                    (x - 0.005, yc + 0.01, zt + 0.036), (x + 0.005, yc + 0.01, zt + 0.036)])
        g.obj("pod.armribs." + tag, "cladding", mirror=True)
    else:
        # the skid, folded up beside the emitter, on two struts
        ys = yc + 0.168 * s
        g = Geo()
        g.sweep([(xc + 0.40 * s, ys, zb + 0.045), (xc + 0.33 * s, ys, zb - 0.02),
                 (xc - 0.33 * s, ys, zb - 0.02), (xc - 0.40 * s, ys, zb + 0.045)],
                [(-0.013, -0.009), (0.013, -0.009), (0.013, 0.009), (-0.013, 0.009)],
                up=(0, 1, 0))
        for x in (xc + 0.2 * s, xc - 0.2 * s):
            g.box((x, ys - 0.012, zb + 0.012), (0.03, 0.02, 0.06))
            g.lathe([(-0.02, 0.002), (-0.02, 0.016), (0.02, 0.016), (0.02, 0.002)], 8,
                    xf=Matrix.Translation((x, ys - 0.012, zb + 0.04)))
        g.obj("pod.skid." + tag, "rim_bright", bevel=0.003, mirror=True)

    # thruster in the pod's stern
    g = Geo()
    g.box((xc - h + 0.07 * s, yc, zc + 0.012 * s), (0.006, 0.20 * s, 0.045 * s))
    g.obj("pod.jet." + tag, "thrust", mirror=True)
    g = Geo()
    for k in (-1, 0, 1):
        g.box((xc - h + 0.045 * s, yc + k * 0.075 * s, zc + 0.012 * s),
              (0.06 * s, 0.008, 0.11 * s))
    g.obj("pod.jetvanes." + tag, "grille", mirror=True)


def pod_ribs(pods, chamfer=False):
    """Fine ribbing on the housings: on the pods as built, seen from the side (with chamfer,
    three short ribs on the top chamfer too); emitter numbers on the pods' noses. pods: tag
    to dict(xc, yc, zc, L, s), as given to build_pod."""
    parts = [ob for ob in K.CAR.objects if ob.name.startswith("pod.") and ob.type == 'MESH'
             and ob.name.split(".")[1] in pods]
    g = Geo()
    for tag, p in pods.items():
        xc, zc, L, s = p["xc"], p["zc"], p["L"], p["s"]
        x0, x1 = xc + L / 2 - 0.36 * s, xc - L / 2 + 0.16 * s
        n = int((x0 - x1) / 0.05)
        for k in range(7):
            z = zc + (0.038 - k * 0.0215) * s
            rib(g, [(x0 + (x1 - x0) * i / n - 0.03 * k * s * (1 if i == 0 else 0), z)
                    for i in range(n + 1)], 'y', 0.009, 0.005, parts)
        if chamfer:
            for k in range(3):                          # three short ribs on the top chamfer
                z = zc + (0.075 + k * 0.022) * s
                rib(g, [(xc + (0.30 - 0.6 * i / 12) * s, z) for i in range(13)], 'y', 0.008,
                    0.004, parts)
    g.obj("pod.ribs", "cladding", mirror=True)
    g = Geo()                                           # emitter numbers on the pods' noses
    for side in (1, -1):
        for k, p in enumerate(pods.values()):
            text_on_body(g, "E%d" % (2 * k + (1 if side > 0 else 2)), 0.062 * p["s"],
                         p["xc"] + p["L"] / 2 - 0.235 * p["s"], p["zc"] + 0.012 * p["s"], side,
                         objs=parts)
    g.obj("pod.stencils", "stencil")
