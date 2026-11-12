"""carkit: what every hand-designed vehicle script shares (Blender 5.2, stdlib and bpy only).

A car script puts this folder on sys.path, imports the kit (which reads the arguments after
"--", empties the scene and makes the CAR and STUDIO collections), calls materials(), builds
its body pieces, details and wheels, and ends with shoot(). See vehicles/README.md.

Frame: x forward, y left, z up, meters, origin on the ground under the car's middle.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from math import asin, atan2, cos, hypot, pi, sin
from math import radians as rad

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix
from mathutils.bvhtree import BVHTree
from mathutils import Vector as V3

HERE = os.path.dirname(os.path.abspath(__file__))
T0 = time.time()


def _script():
    for flag in ("-P", "--python"):
        if flag in sys.argv:
            return os.path.abspath(sys.argv[sys.argv.index(flag) + 1])
    return os.path.join(HERE, "car.py")


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    stem = os.path.splitext(os.path.basename(_script()))[0]
    ap = argparse.ArgumentParser(prog="blender.sh " + os.path.basename(_script()))
    ap.add_argument("--out", default=os.path.join(os.path.expanduser("~"), ".cache", "cybergen",
                                                  "vehicles", stem))
    ap.add_argument("--sheet", action="store_true", help="the one 4K multi-view image, sheet.jpg")
    ap.add_argument("--preview", action="store_true", help="four small views, preview.jpg")
    ap.add_argument("--views", default="", help="full frames, car_<view>.jpg, comma separated")
    ap.add_argument("--res", type=int, nargs=2, default=[1600, 900], help="size of --views frames")
    ap.add_argument("--samples", type=int, default=None)
    ap.add_argument("--night", action="store_true")
    ap.add_argument("--glb", action="store_true")
    ap.add_argument("--blend", action="store_true")
    ap.add_argument("--extra", default="", help="a fifth small tile on the sheet: a view name")
    ap.add_argument("--clay", action="store_true",
                    help="clay.jpg: the preview's views in one matte clay, to judge the form")
    ap.add_argument("--zebra", action="store_true",
                    help="zebra.jpg: the preview's views mirroring stripes, to judge surfaces")
    ap.add_argument("--turntable", type=int, nargs="?", const=12, default=0, metavar="N",
                    help="turntable.jpg (and .gif): N views round the car (12), in clay or "
                         "zebra with those flags")
    ap.add_argument("--check", action="store_true",
                    help="the kit's checks: a table, and check.json")
    a = ap.parse_args(argv)
    a.out = os.path.abspath(a.out)      # Blender's file writer breaks on a relative path
    return a


ARGS = _args()
bpy.ops.wm.read_factory_settings(use_empty=True)
SCN = bpy.context.scene
CAR = bpy.data.collections.new("CAR")
STUDIO = bpy.data.collections.new("STUDIO")
SCN.collection.children.link(CAR)
SCN.collection.children.link(STUDIO)


def log(msg):
    print("T %5.1f  %s" % (time.time() - T0, msg))
    sys.stdout.flush()


# ---------------------------------------------------------------------------------------
# materials
# ---------------------------------------------------------------------------------------
MAT = {}
USED = {}           # the palette materials() was last called with (the checks record it)
# paint finishes: (metallic, roughness, clear coat)
# (a fourth number is the specular level, 0.5 when left out)
FINISH = {"metallic": (0.85, 0.34, 1.0), "pearl": (0.45, 0.30, 1.0), "gloss": (0.0, 0.28, 1.0),
          "satin": (0.6, 0.48, 0.3), "matte": (0.15, 0.7, 0.0), "chrome": (1.0, 0.12, 1.0),
          "lacquer": (0.0, 0.22, 0.45),         # a thin coat: black stays black under the box
          "skin": (0.0, 0.78, 0.0, 0.12)}       # matte with little specular: no pale sheen
PALETTE = dict(
    paint=(0.15, 0.16, 0.185), paint_finish="metallic",        # the body color
    paint2=(0.45, 0.05, 0.03), paint2_finish="gloss",          # a second color: spine, panels
    dust=(0.20, 0.18, 0.15), dust_amount=0.7,                  # road dust low on the paint
    dust_z=(0.12, 0.55),                                       # all of it below, none above
    cladding=(0.028, 0.029, 0.032),
    glass=(0.30, 0.33, 0.36),
    led_front=(0.72, 0.93, 1.0), led_rear=(1.0, 0.03, 0.015), led_accent=(1.0, 0.30, 0.03),
    led_wheel=None,                                            # None: the front light's color
    caliper=(0.95, 0.24, 0.02), seat=(0.06, 0.028, 0.02), interior=(0.018, 0.018, 0.020),
    screen=(0.15, 0.6, 0.8), rim=(0.075, 0.078, 0.085), rim_bright=(0.50, 0.51, 0.53),
    decal=(0.55, 0.56, 0.58), ember=(1.0, 0.22, 0.03),
    # what the design sessions asked for; the defaults are what the kit always did
    glass_ior=1.5,                                             # 1.1 to 1.2: a coated glass
    floor=(0.11, 0.11, 0.12),                                  # the studio's floor
    carbon_coat=1.0,                                           # 0: a dry weave
    led_front_strength=60.0, led_rear_strength=40.0, led_accent_strength=30.0,
    led_wheel_strength=30.0, screen_strength=2.0, lamp_strength=25.0, ember_strength=1.6,
)


def new_mat(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if b is None:
        nt.nodes.clear()
        b = nt.nodes.new('ShaderNodeBsdfPrincipled')
        o = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(b.outputs[0], o.inputs[0])
    return m, b


def pbr(name, color, metallic=0.0, rough=0.5, **kw):
    """A plain material, MAT[name]; kw are further Principled inputs by their names."""
    m, b = new_mat(name)
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    for k, v in kw.items():
        b.inputs[k].default_value = v
    MAT[name] = m
    return m, b


def emit(name, color, strength):
    """A light: strengths are day values, raised by night."""
    k = 0.25 if not ARGS.night else 0.6
    return pbr(name, (0.02, 0.02, 0.02), 0.0, 0.3,
               **{"Emission Color": (*color, 1.0), "Emission Strength": strength * k})


def void(name="void"):
    """Black with no specular: a hole. With specular it goes grey under the lights."""
    return pbr(name, (0.004, 0.004, 0.005), 0.0, 0.8, **{"Specular IOR Level": 0.0})


def paint(name, color, finish="metallic", dust=(0.20, 0.18, 0.15), dust_amount=0.7, flake=0.06,
          dust_z=(0.12, 0.55)):
    """Car paint: fine flake under the coat, road dust low down (all of it at dust_z[0] and
    below, none from dust_z[1] up: raise both for a truck or a hover car), grime in the
    creases."""
    fin = FINISH[finish] if isinstance(finish, str) else tuple(finish)
    metallic, rough, coat = fin[:3]
    m, b = pbr(name, color, metallic, rough, **{"Coat Weight": coat, "Coat Roughness": 0.06})
    if len(fin) > 3:
        b.inputs["Specular IOR Level"].default_value = fin[3]
    nt = m.node_tree
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs["Scale"].default_value = 2600.0
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs["Strength"].default_value = flake
    bp.inputs["Distance"].default_value = 0.0005
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    # road dust on the lower body: a soft gradient by height, broken by noise
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    ramp = nt.nodes.new('ShaderNodeMapRange')
    ramp.inputs["From Min"].default_value = dust_z[0]
    ramp.inputs["From Max"].default_value = dust_z[1]
    ramp.inputs["To Min"].default_value = 1.0
    ramp.inputs["To Max"].default_value = 0.0
    nt.links.new(sep.outputs["Z"], ramp.inputs["Value"])
    n2 = nt.nodes.new('ShaderNodeTexNoise')
    n2.inputs["Scale"].default_value = 9.0
    n2.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
    mul = nt.nodes.new('ShaderNodeMath')
    mul.operation = 'MULTIPLY'
    nt.links.new(ramp.outputs["Result"], mul.inputs[0])
    nt.links.new(n2.outputs["Fac"], mul.inputs[1])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs["From Min"].default_value = 0.0
    mr.inputs["From Max"].default_value = 1.0
    mr.inputs["To Min"].default_value = rough
    mr.inputs["To Max"].default_value = max(rough, 0.62)
    nt.links.new(mul.outputs[0], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    # dust tints the color where it lies, and grime darkens the creases
    dm = nt.nodes.new('ShaderNodeMixRGB')
    dm.inputs["Color1"].default_value = (*color, 1)
    dm.inputs["Color2"].default_value = (*dust, 1)
    df = nt.nodes.new('ShaderNodeMath')
    df.operation = 'MULTIPLY'
    df.inputs[1].default_value = dust_amount
    nt.links.new(mul.outputs[0], df.inputs[0])
    nt.links.new(df.outputs[0], dm.inputs["Fac"])
    ao = nt.nodes.new('ShaderNodeAmbientOcclusion')
    ao.inputs["Distance"].default_value = 0.06
    ao.samples = 8
    aor = nt.nodes.new('ShaderNodeMapRange')
    aor.inputs["From Min"].default_value = 0.35
    aor.inputs["From Max"].default_value = 0.95
    aor.inputs["To Min"].default_value = 0.35
    aor.inputs["To Max"].default_value = 1.0
    nt.links.new(ao.outputs["AO"], aor.inputs["Value"])
    grime = nt.nodes.new('ShaderNodeMixRGB')
    grime.blend_type = 'MULTIPLY'
    grime.inputs["Fac"].default_value = 1.0
    nt.links.new(dm.outputs["Color"], grime.inputs["Color1"])
    nt.links.new(aor.outputs["Result"], grime.inputs["Color2"])
    nt.links.new(grime.outputs["Color"], b.inputs["Base Color"])
    met = nt.nodes.new('ShaderNodeMapRange')
    met.inputs["To Min"].default_value = metallic
    met.inputs["To Max"].default_value = min(metallic, 0.25)
    nt.links.new(df.outputs[0], met.inputs["Value"])
    nt.links.new(met.outputs["Result"], b.inputs["Metallic"])
    return m, b


def carbon(name="carbon", dark=(0.012, 0.012, 0.014), light=(0.045, 0.046, 0.05), coat=1.0):
    """Twill weave: fine diagonal bands in color and roughness under a clear coat (coat=0:
    a dry weave, which does not mirror the top light on faces that look up)."""
    mid = tuple((a + c) / 2 * 0.72 for a, c in zip(dark, light))
    m, b = pbr(name, mid, 0.6, 0.34, **{"Coat Weight": coat, "Coat Roughness": 0.08})
    nt = m.node_tree
    tc = nt.nodes.new('ShaderNodeTexCoord')
    wv = nt.nodes.new('ShaderNodeTexWave')
    wv.wave_type = 'BANDS'
    wv.bands_direction = 'DIAGONAL'
    wv.inputs["Scale"].default_value = 260.0
    wv.inputs["Distortion"].default_value = 0.0
    nt.links.new(tc.outputs["Object"], wv.inputs["Vector"])
    w2 = nt.nodes.new('ShaderNodeTexChecker')
    w2.inputs["Scale"].default_value = 330.0
    nt.links.new(tc.outputs["Object"], w2.inputs["Vector"])
    mx = nt.nodes.new('ShaderNodeMath')
    mx.operation = 'MULTIPLY'
    nt.links.new(wv.outputs["Fac"], mx.inputs[0])
    nt.links.new(w2.outputs["Fac"], mx.inputs[1])
    cr_ = nt.nodes.new('ShaderNodeMapRange')
    cr_.inputs["To Min"].default_value = 0.22
    cr_.inputs["To Max"].default_value = 0.5
    nt.links.new(mx.outputs[0], cr_.inputs["Value"])
    nt.links.new(cr_.outputs["Result"], b.inputs["Roughness"])
    cm = nt.nodes.new('ShaderNodeMixRGB')
    cm.inputs["Color1"].default_value = (*dark, 1)
    cm.inputs["Color2"].default_value = (*light, 1)
    nt.links.new(mx.outputs[0], cm.inputs["Fac"])
    nt.links.new(cm.outputs["Color"], b.inputs["Base Color"])
    return m, b


def glass(name="glass", color=(0.30, 0.33, 0.36), ior=1.5, rough=0.0):
    """Glass, MAT[name]. ior 1.5 is plain glass, which mirrors the studio's lights where it
    leans or looks at the sky; 1.1 to 1.2 is a coated glass that does not. A dark color is
    a smoked glass. Name it glass... and build_body makes its panels thin glass."""
    return pbr(name, color, 0.0, rough, **{"Transmission Weight": 1.0, "IOR": ior})


def lens(name, color=(1.0, 1.0, 1.0), ior=1.49, rough=0.0):
    """A lamp's lens, MAT[name]: clear or tinted glass that lets light through to what is
    behind it (a shadow ray passes, tinted), so the reflectors and the housing of a lamp are
    lit by the studio as the eye expects. Name it lens... and build_body makes its panels
    thin lenses."""
    m, b = glass(name, color, ior, rough)
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    lp = nt.nodes.new('ShaderNodeLightPath')
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    tr.inputs["Color"].default_value = (*[0.25 + 0.75 * c for c in color], 1.0)
    mx = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(lp.outputs["Is Shadow Ray"], mx.inputs["Fac"])
    nt.links.new(b.outputs[0], mx.inputs[1])
    nt.links.new(tr.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return m, b


# materials made when first asked for (need(), build_body's pmat, Geo.obj): a car that asks
# for none of them builds exactly as it did before they were there
LAZY = dict(
    lamp_housing=lambda: pbr("lamp_housing", (0.012, 0.012, 0.014), 0.0, 0.32),
    chrome=lambda: pbr("chrome", (0.86, 0.87, 0.89), 1.0, 0.07),
    lens_clear=lambda: lens("lens_clear"),
    lens_smoke=lambda: lens("lens_smoke", (0.40, 0.42, 0.45)),
    lens_red=lambda: lens("lens_red", (0.85, 0.035, 0.02)),
    lens_amber=lambda: lens("lens_amber", (0.95, 0.42, 0.03)),
    optic=lambda: lens("optic", (0.94, 0.96, 1.0), 1.49, 0.28),
    frit=lambda: pbr("frit", (0.004, 0.004, 0.005), 0.0, 0.05,
                     **{"Coat Weight": 1.0, "Coat Roughness": 0.02}),
    mirror=lambda: pbr("mirror", (0.82, 0.84, 0.86), 1.0, 0.015),
    seal=lambda: pbr("seal", (0.011, 0.011, 0.012), 0.0, 0.62),
)


def need(*names):
    """MAT[name] for the first name, every name given made if it is one of the kit's
    later materials (LAZY: lamp_housing, chrome, lens_clear, lens_smoke, lens_red,
    lens_amber, optic, frit, mirror, seal) and not there yet."""
    for n in names:
        if n not in MAT and n in LAZY:
            LAZY[n]()
    return MAT[names[0]]


def materials(**palette):
    """The library, MAT[name], with the car's palette over PALETTE's defaults.

    paint, paint2 (flake, dust, grime), carbon (weave), gloss_black, cladding, underbody,
    void, well, grille, glass, rubber, rim, rim_bright, disc, caliper, interior, seat,
    screen, decal, floor, and the lights led_front, led_rear, led_accent, led_wheel, lamp,
    ember. Add a car's own with pbr(), emit(), paint(), carbon() or void().
    """
    p = dict(PALETTE)
    unknown = set(palette) - set(p)
    if unknown:
        raise KeyError("materials(): unknown palette keys %s" % sorted(unknown))
    p.update(palette)
    paint("paint", p["paint"], p["paint_finish"], p["dust"], p["dust_amount"],
          dust_z=p["dust_z"])
    paint("paint2", p["paint2"], p["paint2_finish"], p["dust"], p["dust_amount"],
          dust_z=p["dust_z"])
    pbr("gloss_black", (0.010, 0.010, 0.012), 0.0, 0.10, **{"Coat Weight": 1.0})
    pbr("cladding", p["cladding"], 0.3, 0.48)
    carbon(coat=p["carbon_coat"])
    pbr("underbody", (0.02, 0.02, 0.02), 0.0, 0.85)
    void()
    pbr("well", (0.010, 0.010, 0.010), 0.0, 0.9, **{"Specular IOR Level": 0.1})
    pbr("grille", (0.03, 0.03, 0.032), 0.8, 0.38)
    glass("glass", p["glass"], p["glass_ior"])
    pbr("rubber", (0.014, 0.014, 0.015), 0.0, 0.72)
    pbr("rim", p["rim"], 1.0, 0.30)
    pbr("rim_bright", p["rim_bright"], 1.0, 0.22)
    pbr("disc", (0.30, 0.30, 0.31), 1.0, 0.38)
    pbr("caliper", p["caliper"], 0.0, 0.32, **{"Coat Weight": 1.0})
    pbr("interior", p["interior"], 0.0, 0.6)
    pbr("seat", p["seat"], 0.0, 0.5)
    emit("led_front", p["led_front"], p["led_front_strength"])
    emit("led_rear", p["led_rear"], p["led_rear_strength"])
    emit("led_accent", p["led_accent"], p["led_accent_strength"])
    emit("led_wheel", p["led_wheel"] or p["led_front"], p["led_wheel_strength"])
    emit("screen", p["screen"], p["screen_strength"])
    pbr("decal", p["decal"], 0.0, 0.5)
    emit("lamp", (0.85, 0.95, 1.0), p["lamp_strength"])
    emit("ember", p["ember"], p["ember_strength"])
    pbr("floor", p["floor"], 0.0, 0.30)
    USED.clear()
    USED.update(p)
    return MAT


# ---------------------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------------------
def my(p):
    """p mirrored to the right side."""
    return V3((p[0], -p[1], p[2]))


def _axis_vec(axis):
    return V3({'x': (1, 0, 0), 'y': (0, 1, 0), 'z': (0, 0, 1)}[axis]) if isinstance(axis, str) \
        else V3(axis).normalized()


def _axis_frame(axis, at=None):
    """The matrix that turns the y axis onto axis and moves the origin to at."""
    m = V3((0, 1, 0)).rotation_difference(_axis_vec(axis)).to_matrix().to_4x4()
    if at is not None:
        m.translation = V3(at)
    return m


class Geo:
    """Accumulates closed solids into one mesh; obj() makes the object."""

    def __init__(self):
        self.v = []
        self.f = []

    def add(self, verts, faces, xf=None):
        o = len(self.v)
        for p in verts:
            p = V3(p)
            self.v.append(xf @ p if xf is not None else p)
        self.f += [tuple(o + i for i in f) for f in faces]

    def hexa(self, p, xf=None):
        """Eight corners: a bottom quad, then the top quad in the same order."""
        self.add(p, [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6),
                     (3, 0, 4, 7)], xf)

    def box(self, c, size, rot=None, xf=None):
        hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
        R = rot if rot is not None else Matrix.Identity(3)
        c = V3(c)
        pts = [c + R @ V3((sx * hx, sy * hy, sz * hz)) for sz in (-1, 1)
               for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        self.hexa(pts, xf)

    def prism(self, poly, vec, xf=None):
        """A planar polygon pushed along vec."""
        n = len(poly)
        vec = V3(vec)
        pts = [V3(p) for p in poly] + [V3(p) + vec for p in poly]
        faces = [tuple(range(n)), tuple(range(n, 2 * n))]
        faces += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        self.add(pts, faces, xf)

    def lathe(self, prof, n, a0=0.0, a1=2 * pi, xf=None, closed=True, axis='y', at=None):
        """prof: (axial, radius) points, turned in n steps about the y axis through the
        origin, or about axis ('x', 'y', 'z' or a vector) through the point at."""
        if axis != 'y' or at is not None:
            xf = (xf if xf is not None else Matrix.Identity(4)) @ _axis_frame(axis, at)
        full = abs((a1 - a0) - 2 * pi) < 1e-6
        m = len(prof)
        cols = n if full else n + 1
        pts = []
        for k in range(cols):
            a = a0 + (a1 - a0) * k / n
            for (y, r) in prof:
                pts.append((r * cos(a), y, r * sin(a)))
        faces = []
        for k in range(n):
            k2 = (k + 1) % cols
            for j in range(m if closed else m - 1):
                j2 = (j + 1) % m
                faces.append((k * m + j, k * m + j2, k2 * m + j2, k2 * m + j))
        if not full and closed:
            faces.append(tuple(range(m)))
            faces.append(tuple((cols - 1) * m + j for j in range(m)))
        self.add(pts, faces, xf)

    def sweep(self, path, sec, up=(0, 0, 1), closed=False, xf=None):
        """sec: (side, up) offsets of a closed section carried along path, mitred."""
        path = [V3(p) for p in path]
        n = len(path)
        m = len(sec)
        ups = [V3(u) for u in up] if isinstance(up, list) else [V3(up)] * n
        pts = []
        for i in range(n):
            if closed:
                tp = (path[i] - path[i - 1]).normalized()
                tn = (path[(i + 1) % n] - path[i]).normalized()
            else:
                tp = (path[i] - path[i - 1]).normalized() if i > 0 else None
                tn = (path[i + 1] - path[i]).normalized() if i < n - 1 else None
                tp = tp if tp is not None else tn
                tn = tn if tn is not None else tp
            t = (tp + tn).normalized()
            side = t.cross(ups[i]).normalized()
            upv = side.cross(t).normalized()
            cosh = max(0.09, (1 + tp.dot(tn)) / 2) ** 0.5
            ax = tp.cross(tn)
            mdir = ax.normalized().cross(t) if ax.length > 1e-6 else None
            for (a, b) in sec:
                o = side * a + upv * b
                if mdir is not None:
                    o += mdir * (o.dot(mdir)) * (1 / cosh - 1)
                pts.append(path[i] + o)
        faces = []
        for i in range(n if closed else n - 1):
            i2 = (i + 1) % n
            for j in range(m):
                j2 = (j + 1) % m
                faces.append((i * m + j, i * m + j2, i2 * m + j2, i2 * m + j))
        if not closed:
            faces += [tuple(range(m)), tuple((n - 1) * m + j for j in range(m))]
        self.add(pts, faces, xf)

    def ring(self, center, axis, R, r=None, sec=None, n=48, m=10):
        """A ring of radius R about axis ('x', 'y', 'z' or a vector) through center: a round
        bar of radius r (m sides), or a band with sec = (width along the axis, thickness)."""
        if sec is not None:
            w, t = sec[0] / 2, sec[1] / 2
            prof = [(-w, R - t), (-w, R + t), (w, R + t), (w, R - t)]
        else:
            prof = [(r * sin(2 * pi * k / m), R - r * cos(2 * pi * k / m)) for k in range(m)]
        self.lathe(prof, n, axis=axis, at=center)

    def cyl(self, base, h, r, n=24, axis='z'):
        """A closed cylinder of radius r standing h along axis on the point base."""
        base = V3(base)
        self.tube(base, base + _axis_vec(axis) * h, r, n)

    def pipe(self, path, r, n=10, closed=False, up=(0, 0, 1)):
        """A round bar of radius r along a path of points, mitred at its bends."""
        self.sweep(path, [(r * cos(2 * pi * k / n), r * sin(2 * pi * k / n)) for k in range(n)],
                   up=up, closed=closed)

    def prism_on(self, plane, poly, at, depth):
        """A polygon drawn in a named plane ('xy', 'xz' or 'yz': its 2D points in that
        order) at the coordinate at of the third axis, pushed depth along that axis."""
        i, j = "xyz".index(plane[0]), "xyz".index(plane[1])
        k = 3 - i - j
        pts, vec = [], [0.0, 0.0, 0.0]
        for a, b in poly:
            q = [0.0, 0.0, 0.0]
            q[i], q[j], q[k] = a, b, at
            pts.append(q)
        vec[k] = depth
        self.prism(pts, vec)

    def tube(self, a, b, r, n=12, xf=None):
        """A straight round bar of radius r from a to b, n sides, its ends closed."""
        a, b = V3(a), V3(b)
        t = (b - a).normalized()
        u = t.cross(V3((0, 0, 1)) if abs(t.z) < 0.9 else V3((1, 0, 0))).normalized()
        w = t.cross(u)
        ring = [u * (r * cos(2 * pi * k / n)) + w * (r * sin(2 * pi * k / n)) for k in range(n)]
        faces = [tuple(range(n)), tuple(range(n, 2 * n))]
        faces += [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
        self.add([a + o for o in ring] + [b + o for o in ring], faces, xf)

    def louvers(self, a, b, c, d, n, w, th, tilt, out, lift=0.0, margin=0.06):
        """n slats, each from the a-b edge to the d-c edge, spread from a to b."""
        a, b, c, d = V3(a), V3(b), V3(c), V3(d)
        nrm = (b - a).cross(d - a).normalized()
        if nrm.dot(V3(out)) < 0:
            nrm = -nrm
        for k in range(n):
            t = margin + (1 - 2 * margin) * (k + 0.5) / n
            p0 = a.lerp(b, t) + nrm * lift
            p1 = d.lerp(c, t) + nrm * lift
            L = (p1 - p0).normalized()
            W = nrm.cross(L).normalized()
            Wt = W * cos(tilt) + nrm * sin(tilt)
            Nt = nrm * cos(tilt) - W * sin(tilt)
            pts = [p + Wt * sw * w / 2 + Nt * sn * th / 2 for sn in (-1, 1)
                   for (p, sw) in ((p0, -1), (p1, -1), (p1, 1), (p0, 1))]
            self.hexa(pts)

    def honeycomb(self, poly, x, R, wall, depth, sgn, keep=None, frame=None):
        """Hexagonal mesh over a (y, z) polygon on the plane x, standing sgn * depth off it.
        frame=(origin, u, v) puts it on any plane instead: the polygon is then (a, b) along
        u and v from the origin, and the mesh stands along u x v (x is an offset along it)."""
        F = None
        if frame is not None:
            o, u, v = V3(frame[0]), V3(frame[1]).normalized(), V3(frame[2]).normalized()
            w = u.cross(v).normalized()
            F = Matrix((w, u, v)).transposed().to_4x4()
            F.translation = o
        def inside(y, z):
            c = False
            for (y0, z0), (y1, z1) in zip(poly, poly[1:] + poly[:1]):
                if (z0 > z) != (z1 > z) and y < y0 + (y1 - y0) * (z - z0) / (z1 - z0):
                    c = not c
            return c
        ys = [p[0] for p in poly]
        zs = [p[1] for p in poly]
        dy, dz = 1.5 * R, 3 ** 0.5 * R
        rot = Matrix.Rotation(pi / 2, 4, 'Z')
        for i in range(int(min(ys) / dy) - 1, int(max(ys) / dy) + 2):
            for k in range(int(min(zs) / dz) - 1, int(max(zs) / dz) + 2):
                y, z = i * dy, k * dz + (dz / 2 if i % 2 else 0.0)
                if not inside(y, z) or (keep is not None and not keep(y, z)):
                    continue
                prof = [(0, R - wall), (0, R), (depth, R), (depth, R - wall)]
                xf = Matrix.Translation((x + (0 if sgn < 0 else depth), y, z)) @ rot
                self.lathe(prof, 6, xf=xf if F is None else F @ xf)

    def mesh(self, name, flip_y=False):
        vs = [((p.x, -p.y, p.z) if flip_y else tuple(p)) for p in self.v]
        me = bpy.data.meshes.new(name)
        me.from_pydata(vs, [], self.f)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        return me

    def obj(self, name, mat, bevel=0.0, segs=2, angle=30.0, mirror=False, wn=True,
            sharp=None, flip_y=False, loc=None, coll=None, rot=None):
        """The object: material MAT[mat], then finish()'s mirror, bevel and shading. loc
        moves it and rot (an Euler, three angles or a matrix) turns it about its origin; a
        mirror is then about the turned object's own y = 0."""
        me = self.mesh(name, flip_y)
        me.materials.append(need(mat))
        ob = bpy.data.objects.new(name, me)
        (coll or CAR).objects.link(ob)
        if loc is not None:
            ob.location = loc
        if rot is not None:
            ob.rotation_euler = rot.to_euler() if isinstance(rot, Matrix) else rot
        finish(ob, bevel, segs, angle, mirror, wn, sharp)
        return ob


def finish(ob, bevel=0.0, segs=2, angle=30.0, mirror=False, wn=True, sharp=None):
    """Mirror to the right side, bevel edges sharper than angle, smooth shading."""
    me = ob.data
    if mirror:
        md = ob.modifiers.new("mirror", 'MIRROR')
        md.use_axis = (False, True, False)
    if bevel:
        md = ob.modifiers.new("bevel", 'BEVEL')
        md.width = bevel
        md.segments = segs
        md.limit_method = 'ANGLE'
        md.angle_limit = rad(angle)
    if sharp is not None:
        me.shade_smooth()
        me.set_sharp_from_angle(angle=rad(sharp))
    elif wn and bevel:
        me.shade_smooth()
        md = ob.modifiers.new("wn", 'WEIGHTED_NORMAL')
        md.keep_sharp = True
        md.weight = 60


def evaluated_mesh(ob):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    return bpy.data.meshes.new_from_object(ob.evaluated_get(dg))


def shr(quad, k, lift, out):
    """A quad pulled toward its middle by k and moved by lift along its normal."""
    q = [V3(p) for p in quad]
    c = sum(q, V3()) / 4
    n = (q[1] - q[0]).cross(q[3] - q[0]).normalized()
    if n.dot(V3(out)) < 0:
        n = -n
    return [p.lerp(c, k) + n * lift for p in q]


def band_point(p, center, w, out=0.0):
    """A point w inside the lip of an end cap (toward its middle), moved out along x."""
    d = V3((0, center.y - p.y, center.z - p.z)).normalized()
    return p + d * w + V3((out, 0, 0))


# ---------------------------------------------------------------------------------------
# body: character lines over stations, a creased subdivision cage
# ---------------------------------------------------------------------------------------
BODY = []           # the body parts the projector sees
PIECES = {}         # every body piece built, by name (the checks read it)
CUTS = []           # the paths of the grooves and pockets laid while a hull stands uncut
_BVH = [None]


def fill(stations):
    """Stations as lists of V3, every None filled along its line between the nearest
    stations that have the point (by the station's x where it has other points)."""
    S = [[V3(p) if p is not None else None for p in st] for st in stations]
    n = len(S)
    for i, st in enumerate(S):
        known = [p.x for p in st if p is not None]
        xi = sum(known) / len(known) if known else None
        for j, p in enumerate(st):
            if p is not None:
                continue
            a = next((k for k in range(i - 1, -1, -1) if S[k][j] is not None), None)
            b = next((k for k in range(i + 1, n) if stations[k][j] is not None), None)
            if a is None and b is None:
                raise ValueError("fill(): line %d has no point at all" % j)
            if a is None or b is None:
                st[j] = S[a if b is None else b][j].copy()
                continue
            pa, pb = S[a][j], V3(stations[b][j])
            t = (i - a) / (b - a)
            if xi is not None and abs(pa.x - pb.x) > 1e-6:
                t = min(1.0, max(0.0, (pa.x - xi) / (pa.x - pb.x)))
            st[j] = pa.lerp(pb, t)
    return S


def table(names, lines, S):
    """PT[station name][line letter] -> point, for building details on the cage's points."""
    return {k: {lines[j]: S[i][j] for j in range(len(lines))} for i, k in enumerate(names)}


def _weight(spec, i, j):
    if callable(spec):
        return spec(i, j)
    if isinstance(spec, dict):
        return spec.get((i, j), 0.0)
    if isinstance(spec, (int, float)):
        return float(spec)
    return spec[i][j]


class Body:
    """What build_body returns: parts[panel] -> object, caps["front"|"rear"] -> the inner
    ring's points (left half, top to bottom, when mirrored)."""

    def __init__(self, name):
        self.name = name
        self.parts = {}
        self.caps = {}
        self.raw = set()            # the cutters' panels
        self.closed = True          # a closed hull (both caps given, mirrored or wrapped)
        self.gap = 0.0              # the gap its panels were built with
        self.skin = None            # the uncut hull's tree, when the cutters were a function
        self.cuts = []              # the paths of its grooves and pockets (the checks)


def _even_band(ring, center, band, mirror, wrap):
    """Offsets (in y, z) that take each point of a cap's ring band inward, square to the
    ring: a band of one width all round."""
    q = [(v.co.y, v.co.z) for v in ring]
    n = len(q)

    def inward(a, b):
        ex, ey = b[0] - a[0], b[1] - a[1]
        ln = hypot(ex, ey) or 1.0
        nx, ny = -ey / ln, ex / ln
        mx, my_ = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        if nx * (center.y - mx) + ny * (center.z - my_) < 0:
            nx, ny = -nx, -ny
        return nx, ny

    out = []
    for i in range(n):
        if wrap:
            a, b = q[i - 1], q[(i + 1) % n]
        else:
            a = q[i - 1] if i > 0 else ((-q[1][0], q[1][1]) if mirror else None)
            b = q[i + 1] if i < n - 1 else ((-q[n - 2][0], q[n - 2][1]) if mirror else None)
        ns = [inward(a, q[i])] if a is not None and a != q[i] else []
        ns += [inward(q[i], b)] if b is not None and b != q[i] else []
        if len(ns) == 2:
            d = max(0.3, 1 + ns[0][0] * ns[1][0] + ns[0][1] * ns[1][1])
            o = ((ns[0][0] + ns[1][0]) / d, (ns[0][1] + ns[1][1]) / d)
        else:
            o = ns[0] if ns else (0.0, 0.0)
        out.append(V3((0.0, o[0] * band, o[1] * band)))
    return out


def shrink(bm, d):
    """Pull a panel's open boundary in by d, in the surface, so panels have gaps."""
    bm.normal_update()
    mv = {}
    for f in bm.faces:
        for l in f.loops:
            if len(l.edge.link_faces) != 1:
                continue
            a, b = l.vert, l.link_loop_next.vert
            inw = f.normal.cross(b.co - a.co).normalized()
            mv.setdefault(a, []).append(inw)
            mv.setdefault(b, []).append(inw)
    for v, ns in mv.items():
        if len(ns) == 2:
            o = (ns[0] + ns[1]) / max(1 + ns[0].dot(ns[1]), 0.3)
        else:
            o = sum(ns, V3()) / len(ns)
        v.co += o * d


def build_body(stations, panel_of, pmat, line_crease=0.0, station_crease=0.0, name="body",
               front=None, rear=None, recesses=(), glass=(), cutters=(), subdiv=3,
               mirror=True, wrap=False, gap=0.0012, thick=0.014, glass_thick=0.006,
               project=True, bevel=None, bevel_segs=2, lens_thick=0.003):
    """One body piece: a quad cage of len(stations) x lines points, creased, subdivided,
    cut, split into panels with gaps, each panel given a rim and bevelled edges.

    stations        rows of points front to rear, one per line, None filled by fill(). With
                    mirror the lines run from the top centerline (y = 0) down the left side
                    to the floor's centerline (y = 0); the right side is the mirror image.
    panel_of(i, j)  panel name of the quad between stations i, i + 1 and lines j, j + 1.
    pmat            panel name -> material name (every panel named anywhere).
    line_crease     crease of the edge along line j from station i to i + 1: a function
                    (i, j), a number, a dict {(i, j): w} or a table [i][j]. 1 is sharp.
    station_crease  crease of the edge on station i between lines j and j + 1, likewise.
    front, rear     end caps on the first and last station: None leaves the end open;
                    dict(kind="flat", panel=P) closes it with one face; dict(center=,
                    depth=, inner=P, frame=P, band=0.05, band_panel=P, band_lines=N,
                    lip=0.008, reach=0.12) makes a recessed mouth: a band round the lip
                    (band_panel on its first N intervals, frame on the rest), a frame
                    going in, and the inner face depth behind the center. The band's
                    points are drawn toward the center, so it is narrow where the lip
                    runs past the center (the top of a wide mouth); even=True makes it
                    band wide all round, measured square to the lip: room for a lamp.
                    caps[key + ".band"] holds the band's (lip point, inner point) pairs.
    recesses        (i, j, thickness, depth[, inner panel, wall panel]): quad (i, j) inset
                    and sunk on both sides (vents; "vent" by default).
    glass           (panel, inset[, trim panel]): a trim frame round the panel's faces with
                    sharp corners ("trim" by default). (panel, inset, trim, "frame") is the
                    same frame made on the left half before it is mirrored, so it is the
                    same on both sides and faces out; (panel, inset, trim, "frit") makes
                    the band part of the glass instead: no gap between them, the glass's
                    thickness, for a trim panel in a frit material (a black border printed
                    on the glass).
    cutters         (Geo, panel) solids cut out of the hull, the cut faces becoming that
                    panel, which is kept as it is (no gap, rim or bevel): wheel wells.
                    (Geo, panel, "drop") drops the cut faces instead: a hole (a window, an
                    open locker), or with groove() a shut line. (Geo, panel, "skin", P)
                    keeps the cut faces as panel (a pocket) and makes the skin the cutter
                    took away a panel P of its own with the gap all round: a lamp's lens
                    over its housing (a lens... material makes it a thin lens), a handle or
                    a flap over its recess. (Geo, P, "cover") makes the skin panel P and
                    drops the cut faces. A cutter on one side only cuts that side.
                    A function instead of the list is called once the cage stands, uncut:
                    on_body() and snap() then see that hull, so groove() and pocket() can
                    lay cutters on the surface; it returns the list.
    mirror, wrap    mirror=False builds the cage as given; wrap=True joins the last line
                    to the first (a tube about the x axis).
    project         whether on_body(), ribbon() and text_on_body() see this piece.
    bevel           width of the panels' edge bevel: None is 0.0045 on paint and 0.003 on
                    the rest, a number is for every panel, a dict {panel: width} for some
                    (0 for none); bevel_segs its segments.
    """
    S = fill(stations)
    res = Body(name)
    panels = []

    def pidx(pn):
        if pn not in pmat:
            raise KeyError("build_body(%s): panel %r is not in pmat" % (name, pn))
        if pn not in panels:
            panels.append(pn)
        return panels.index(pn)

    bm = bmesh.new()
    qid = bm.faces.layers.int.new("qid")                # layers before the vertices
    cr = bm.edges.layers.float.new("crease_edge")
    vc = bm.verts.layers.float.new("crease_vert")
    VV = [[bm.verts.new(p) for p in st] for st in S]
    n, m = len(S), len(S[0])
    jn = m if wrap else m - 1

    def face(vs, panel, q=-1):
        f = bm.faces.new(vs)
        f.material_index = pidx(panel)
        f[qid] = q
        return f

    def crease(a, b, w):
        e = bm.edges.get((a, b))
        if e is not None and w > e[cr]:
            e[cr] = w

    for i in range(n - 1):
        for j in range(jn):
            j2 = (j + 1) % m
            face([VV[i][j], VV[i][j2], VV[i + 1][j2], VV[i + 1][j]], panel_of(i, j), i * m + j)
    for i in range(n - 1):
        for j in range(m):
            crease(VV[i][j], VV[i + 1][j], _weight(line_crease, i, j))
    for i in range(n):
        for j in range(jn):
            crease(VV[i][j], VV[i][(j + 1) % m], _weight(station_crease, i, j))

    def cap(ring, spec, sgn, key):
        if spec is None:
            return
        k = len(ring) if wrap else len(ring) - 1
        if spec.get("kind") == "flat":
            face(ring, spec["panel"])
            for j in range(k):
                crease(ring[j], ring[(j + 1) % len(ring)], spec.get("crease", 1.0))
            res.caps[key] = [v.co.copy() for v in ring]
            return
        center = V3(spec["center"])
        band, lip = spec.get("band", 0.05), spec.get("lip", 0.008)
        frame, inner = spec["frame"], spec["inner"]
        band_panel = spec.get("band_panel", frame)
        band_lines = spec.get("band_lines", k)
        r1, r2 = [], []
        even = _even_band(ring, center, band, mirror, wrap) if spec.get("even") else None
        for iv, v in enumerate(ring):
            L = hypot(center.y - v.co.y, center.z - v.co.z)
            if even is not None:
                r1.append(bm.verts.new(v.co + even[iv] + V3((sgn * lip, 0, 0))))
            else:
                r1.append(bm.verts.new(band_point(v.co, center, band, sgn * lip)))
            res.caps.setdefault(key + ".band", []).append((v.co.copy(), r1[-1].co.copy()))
            p = band_point(v.co, center, min(spec.get("reach", 0.12), L * 0.6), 0.0)
            p.x = center.x + sgn * spec["depth"]
            r2.append(bm.verts.new(p))
            res.caps.setdefault(key, []).append(p.copy())
        fs = []
        for j in range(k):
            j2 = (j + 1) % len(ring)
            fs.append(face([ring[j], ring[j2], r1[j2], r1[j]],
                           band_panel if j < band_lines else frame))
            fs.append(face([r1[j], r1[j2], r2[j2], r2[j]], frame))
        fs.append(face(r2, inner))
        for f in fs:
            for e in f.edges:
                e[cr] = 1.0

    cap(VV[0], front, -1, "front")
    cap(VV[-1], rear, 1, "rear")

    group = {}                                          # frit: panels shrunk as one
    for gl in glass:
        if len(gl) <= 3:
            continue
        pn, t, trim = gl[:3]
        if gl[3] not in ("frame", "frit"):
            raise ValueError("build_body(%s): glass mode %r" % (name, gl[3]))
        fs = [f for f in bm.faces if f.material_index == pidx(pn)]
        r = bmesh.ops.inset_region(bm, faces=fs, thickness=t, depth=0.0,
                                   use_even_offset=True, use_boundary=not mirror)
        rim = set(r["faces"])
        for f in rim:
            f.material_index = pidx(trim)
        loop = {e for f in fs for e in f.edges if any(g in rim for g in e.link_faces)}
        for e in loop:
            e[cr] = 1.0
        for v in {v for e in loop for v in e.verts}:
            es = [e for e in v.link_edges if e in loop]
            if len(es) == 2:
                d1 = (es[0].other_vert(v).co - v.co).normalized()
                d2 = (es[1].other_vert(v).co - v.co).normalized()
                if d1.angle(d2) < rad(150):
                    v[vc] = 1.0
        if gl[3] == "frit":
            both = sorted(set(group.get(pn, (pn,))) | set(group.get(trim, (trim,))))
            for q in both:
                group[q] = both

    if mirror:
        bmesh.ops.mirror(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], axis='Y',
                         merge_dist=1e-5)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    for rc in recesses:
        i, j, t, depth = rc[:4]
        inner = rc[4] if len(rc) > 4 else "vent"
        wall = rc[5] if len(rc) > 5 else inner
        for sgn in ((1, -1) if mirror else (0,)):
            fs = [f for f in bm.faces if f[qid] == i * m + j
                  and (sgn == 0 or f.calc_center_median().y * sgn > 0)]
            r = bmesh.ops.inset_region(bm, faces=fs, thickness=t, depth=-depth,
                                       use_even_offset=True, use_boundary=True)
            for f in r["faces"]:
                f.material_index = pidx(wall)
                f[qid] = -1
                for e in f.edges:
                    e[cr] = 1.0
            for f in fs:
                f.material_index = pidx(inner)
    for gl in glass:
        if len(gl) > 3:
            continue
        pn, t = gl[:2]
        trim = gl[2] if len(gl) > 2 else "trim"
        fs = [f for f in bm.faces if f.material_index == pidx(pn)]
        r = bmesh.ops.inset_region(bm, faces=fs, thickness=t, depth=0.0,
                                   use_even_offset=True, use_boundary=True)
        rim = set(r["faces"])
        for f in rim:
            f.material_index = pidx(trim)
        loop = {e for f in fs for e in f.edges if any(g in rim for g in e.link_faces)}
        for e in loop:
            e[cr] = 1.0
        for v in {v for e in loop for v in e.verts}:
            es = [e for e in v.link_edges if e in loop]
            if len(es) == 2:
                d1 = (es[0].other_vert(v).co - v.co).normalized()
                d2 = (es[1].other_vert(v).co - v.co).normalized()
                if d1.angle(d2) < rad(150):
                    v[vc] = 1.0
    res.closed = bool(front is not None and rear is not None and (mirror or wrap))
    res.gap = gap
    PIECES[name] = res

    me = bpy.data.meshes.new(name + ".hull")
    bm.to_mesh(me)
    bm.free()
    hull = bpy.data.objects.new(name + ".hull", me)
    CAR.objects.link(hull)
    md = hull.modifiers.new("subd", 'SUBSURF')
    md.levels = subdiv
    md.render_levels = subdiv
    md.subdivision_type = 'CATMULL_CLARK'
    if callable(cutters):
        # the cage stands, uncut: the car lays its cutters on it
        res.skin = body_bvh([hull])
        del CUTS[:]
        cutters = list(cutters() or ())
        res.cuts = list(CUTS)
        del CUTS[:]
        _BVH[0] = None
    raw, dropped, skins = set(), set(), {}
    for ct in cutters:
        mode = ct[2] if len(ct) > 2 else None
        if mode not in (None, "drop", "skin", "cover"):
            raise ValueError("build_body(%s): cutter mode %r" % (name, mode))
        pidx(ct[1])
        if mode == "cover":
            dropped.add(ct[1])
            continue
        raw.add(ct[1])
        if mode == "drop":
            dropped.add(ct[1])
        elif mode == "skin":
            pidx(ct[3])
    res.raw = raw
    pm, back = {}, {}
    for pn in panels:
        pm[pn] = bpy.data.materials.new("P_" + pn)
        back[pm[pn].name] = pn
        me.materials.append(pm[pn])
    cuts = []
    for k, ct in enumerate(cutters):
        g, pn = ct[0], ct[1]
        cme = g.mesh("cut")
        cme.materials.append(pm[pn])
        cut = bpy.data.objects.new("cut", cme)
        CAR.objects.link(cut)
        cuts.append(cut)
        mode = ct[2] if len(ct) > 2 else None
        if mode in ("skin", "cover"):
            # the skin this cutter takes away: the hull inside it, less the cutter's faces
            tmp = bpy.data.objects.new("skin", me)
            CAR.objects.link(tmp)
            sd = tmp.modifiers.new("subd", 'SUBSURF')
            sd.levels = sd.render_levels = subdiv
            sd.subdivision_type = 'CATMULL_CLARK'
            bo = tmp.modifiers.new("skin", 'BOOLEAN')
            bo.operation = 'INTERSECT'
            bo.object = cut
            bo.solver = 'EXACT'
            try:
                bo.material_mode = 'TRANSFER'
            except Exception:
                pass
            sm = evaluated_mesh(tmp)
            bpy.data.objects.remove(tmp)
            skins.setdefault(ct[3] if mode == "skin" else pn, []).append((sm, pm[pn].name))
        md = hull.modifiers.new("cut%d" % k, 'BOOLEAN')
        md.operation = 'DIFFERENCE'
        md.object = cut
        md.solver = 'EXACT'
        try:
            md.material_mode = 'TRANSFER'
        except Exception:
            pass
    out = evaluated_mesh(hull)
    names = [back[mt.name] for mt in out.materials]
    for ob in [hull] + cuts:
        old = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(old)

    # split into panels
    jobs = []
    for idx, pn in enumerate(names):
        pb = bmesh.new()
        pb.from_mesh(out)
        grp = [names.index(q) for q in group.get(pn, (pn,)) if q in names]
        dele = [f for f in pb.faces if f.material_index not in grp]
        if not any(f.material_index == idx for f in pb.faces) or pn in dropped:
            pb.free()
            continue
        bmesh.ops.delete(pb, geom=dele, context='FACES')
        if pn not in raw and gap:
            shrink(pb, gap)
        if len(grp) > 1:
            bmesh.ops.delete(pb, geom=[f for f in pb.faces if f.material_index != idx],
                             context='FACES')
        jobs.append((pn, pb))
    for pn, lst in skins.items():
        pb = bmesh.new()
        for sm, cutmat in lst:
            tb = bmesh.new()
            tb.from_mesh(sm)
            ci = {i for i, mt in enumerate(sm.materials) if mt is not None and mt.name == cutmat}
            bmesh.ops.delete(tb, geom=[f for f in tb.faces if f.material_index in ci],
                             context='FACES')
            tme = bpy.data.meshes.new("skin")
            tb.to_mesh(tme)
            tb.free()
            pb.from_mesh(tme)
            bpy.data.meshes.remove(tme)
            bpy.data.meshes.remove(sm)
        if not pb.faces:
            log("build_body(%s): the cutter of %r takes no skin away" % (name, pn))
            pb.free()
            continue
        if gap:
            shrink(pb, gap)
        jobs.append((pn, pb))
    for pn, pb in jobs:
        for f in pb.faces:
            f.material_index = 0
        mat = pmat[pn]
        pme = bpy.data.meshes.new(name + "." + pn)
        pb.to_mesh(pme)
        pb.free()
        pme.materials.append(need(mat))
        ob = bpy.data.objects.new(name + "." + pn, pme)
        CAR.objects.link(ob)
        res.parts[pn] = ob
        if pn in raw:
            continue
        if project:
            BODY.append(ob)
        md = ob.modifiers.new("solid", 'SOLIDIFY')
        md.offset = -1.0
        if mat.startswith(("glass", "lens", "frit")):
            md.thickness = lens_thick if mat.startswith("lens") else glass_thick
            pme.shade_smooth()
            continue
        md.thickness = thick
        md.use_rim_only = True
        if mat.startswith("void"):
            continue
        bw = 0.0045 if mat.startswith("paint") else 0.003
        if isinstance(bevel, dict):
            bw = bevel.get(pn, bw)
        elif bevel is not None:
            bw = bevel
        finish(ob, bevel=bw, segs=bevel_segs, angle=14.0)
    bpy.data.meshes.remove(out)
    for mt in pm.values():
        bpy.data.materials.remove(mt)
    _BVH[0] = None
    return res


def well_cutter(g, cx, cz, r, y0, angles, depth=0.8, floor=-0.3, sides=(1, -1)):
    """Adds a wheel well to the cutter g: an arch of radius r about (cx, cz) through the
    angles (degrees, front to rear over the top), from y0 outward, open to below."""
    for sgn in sides:
        pts = [V3((cx + r * cos(rad(a)), sgn * y0, cz + r * sin(rad(a)))) for a in angles]
        poly = [V3((pts[0].x, sgn * y0, floor))] + pts + [V3((pts[-1].x, sgn * y0, floor))]
        g.prism(poly, (0, sgn * depth, 0))


def arch_trim(g, cx, cz, r, y_in, y_out, angles, inset=0.005, width=0.04):
    """A faceted trim round a wheel arch (left side; mirror the object), y_in to y_out."""
    ring = [(cx + rr * cos(rad(a)), y, cz + rr * sin(rad(a)))
            for y in (y_in, y_out) for rr in (r - inset, r + width) for a in angles]
    n = len(angles)
    faces = []
    for k in range(n - 1):
        i0, i1, o0, o1 = k, k + 1, n + k, n + k + 1          # inner y: in, out radius
        faces += [(i0, i1, o1, o0),
                  (2 * n + i0, 2 * n + i1, 2 * n + o1, 2 * n + o0),
                  (i0, i1, 2 * n + i1, 2 * n + i0), (o0, o1, 2 * n + o1, 2 * n + o0)]
    faces += [(0, n, 3 * n, 2 * n), (n - 1, 2 * n - 1, 4 * n - 1, 3 * n - 1)]
    g.add(ring, faces)


def arch_bolts(g, cx, cz, r, y, angles, inset=0.005, width=0.04, at=(0.25, 0.75),
               bolt=(0.0065, 0.0035)):
    """Bolt heads (bolt: radius, height) on the outer face of an arch_trim, on the middle
    of each facet."""
    br, bh = bolt
    mid = r + (width - inset) / 2
    for k in range(len(angles) - 1):
        da = angles[k + 1] - angles[k]
        for t in at:
            a = rad(angles[k] + da * t)
            rr = mid * cos(rad(da / 2)) / cos(rad(da * (t - 0.5)))
            g.lathe([(-0.002, 0.0015), (-0.002, br), (bh, br), (bh, 0.0015)],
                    6, xf=Matrix.Translation((cx + rr * cos(a), y, cz + rr * sin(a))))


# ---------------------------------------------------------------------------------------
# details lying on the body as built
# ---------------------------------------------------------------------------------------
def body_bvh(objs=None, default=True):
    """The projector's target, returned: every body piece as built, or the objects given.
    With default it also becomes what on_body() sees when given no objects (body_bvh()
    alone puts the body pieces back); on_body(..., objs=...) needs none of this."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    vs, ps = [], []
    for ob in (objs if objs is not None else BODY):
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        o = len(vs)
        mw = ob.matrix_world
        vs += [mw @ v.co for v in me.vertices]
        ps += [tuple(o + i for i in p.vertices) for p in me.polygons]
        ev.to_mesh_clear()
    tree = BVHTree.FromPolygons(vs, ps)
    if default:
        _BVH[0] = tree
    return tree


_TREES = {}         # on_body(objs=...): trees by the objects' names


def _tree(objs):
    if objs is None:
        if _BVH[0] is None:
            body_bvh()
        return _BVH[0]
    if isinstance(objs, BVHTree):
        return objs
    objs = [objs] if isinstance(objs, bpy.types.Object) else list(objs)
    key = tuple(ob.name for ob in objs)
    if key not in _TREES:
        _TREES[key] = body_bvh(objs, default=False)
    return _TREES[key]


# projection -> (the ray's axis, the axes of u and v), where it starts, its direction
_RAYS = {'y': ((1, 0, 2), 30.0, (0, -1, 0)), 'Y': ((1, 0, 2), -30.0, (0, 1, 0)),
         'x': ((0, 1, 2), 30.0, (-1, 0, 0)), 'X': ((0, 1, 2), -30.0, (1, 0, 0)),
         'z': ((2, 0, 1), 30.0, (0, 0, -1))}


def on_body(u, v, proj, objs=None, tol=0.0):
    """The body's surface point and normal under (u, v), or (None, None): proj 'y' (x, z)
    seen from the left, 'Y' from the right, 'x' (y, z) from the front, 'X' from the back,
    'z' (x, y) from above. objs: an object or a list of objects to project on instead of
    the body pieces (as they are at the first call with that list). tol: a ray that slips
    through a panel gap looks again this far to each side (0.003 covers every gap)."""
    tree = _tree(objs)
    (axis, a, b), far, d = _RAYS[proj]
    o = V3()
    o[axis], o[a], o[b] = far, u, v
    d = V3(d)
    loc, n, _, _ = tree.ray_cast(o, d)
    if loc is None and tol:
        for du, dv in ((tol, 0), (-tol, 0), (0, tol), (0, -tol)):
            o[a], o[b] = u + du, v + dv
            loc, n, _, _ = tree.ray_cast(o, d)
            if loc is not None:
                break
    if loc is None:
        return None, None
    if n.dot(d) > 0:
        n = -n
    return loc, n


def ribbon(g, pts, proj, w, lift=0.0008, closed=False, step=0.012, objs=None):
    """A flat strip of width w lying on the body (or on objs) along a path given in
    projection."""
    pts = [V3((p[0], p[1], 0)) for p in pts]
    if closed:
        pts = pts + [pts[0]]
    sam = []
    for a, b in zip(pts, pts[1:]):
        n = max(1, int((b - a).length / step))
        sam += [a.lerp(b, k / n) for k in range(n)]
    sam.append(pts[-1])
    P, N = [], []
    for q in sam:
        loc, n = on_body(q.x, q.y, proj, objs)
        if loc is not None:
            P.append(loc)
            N.append(n)
    if len(P) < 2:
        return
    vs = []
    for i in range(len(P)):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        sd = N[i].cross(t).normalized()
        vs += [P[i] + N[i] * lift + sd * w / 2, P[i] + N[i] * lift - sd * w / 2]
    g.add(vs, [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(len(P) - 1)])


def snap(p, objs=None, out=None):
    """The nearest point of the body as built (or of objs) to p, and its normal there. The
    normal looks toward p when p is off the surface (give points a little outside it), else
    along out (a direction) when given. For what a projection along an axis cannot reach:
    round a nose, over a shoulder, on a dome."""
    p = V3(p)
    loc, n, _, _ = _tree(objs).find_nearest(p)
    if loc is None:
        return None, None
    if out is not None:
        if n.dot(V3(out)) < 0:
            n = -n
    elif (p - loc).length > 5e-4 and n.dot(p - loc) < 0:
        n = -n
    return loc, n


def spline(ctrl, n=12):
    """A smooth curve through the control points (Catmull-Rom), n points a span."""
    P = [V3(p) for p in ctrl]
    out = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
        for k in range(n):
            t = k / n
            out.append(0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (3 * p1 - p0 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1])
    return out


def strip(g, ctrl, w, lift=0.0026, sink=-0.0003, taper=(0.0, 0.0), n=12, objs=None, out=None):
    """A band of width w lying on the surface along a smooth 3D curve through ctrl (points
    near the surface, snapped onto it): a closed solid from sink under the skin to lift over
    it, its ends drawn out to points over the taper lengths. Light strips, trims and seams
    that run round a nose or over a shoulder. The default sink is negative, a hair over the
    skin: panels have no thickness, and a light under the skin shines into the shell."""
    P, N = [], []
    for q in spline(ctrl, n):
        loc, nn = snap(q, objs, out)
        if loc is not None and (not P or (loc - P[-1]).length > 1e-4):
            P.append(loc)
            N.append(nn)
    if len(P) < 2:
        return
    s = [0.0]
    for a, b in zip(P, P[1:]):
        s.append(s[-1] + (b - a).length)
    vs = []
    for i in range(len(P)):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        sd = N[i].cross(t).normalized()
        k = 1.0
        if taper[0]:
            k = min(k, (s[i] / taper[0]) ** 0.6)
        if taper[1]:
            k = min(k, ((s[-1] - s[i]) / taper[1]) ** 0.6)
        h = w * max(k, 0.06) / 2
        vs += [P[i] - N[i] * sink + sd * h, P[i] + N[i] * lift + sd * h,
               P[i] + N[i] * lift - sd * h, P[i] - N[i] * sink - sd * h]
    m = len(P)
    faces = [(4 * i + j, 4 * i + (j + 1) % 4, 4 * i + 4 + (j + 1) % 4, 4 * i + 4 + j)
             for i in range(m - 1) for j in range(4)]
    faces += [(0, 1, 2, 3), tuple(4 * (m - 1) + j for j in range(4))]
    g.add(vs, faces)


def rib(g, pts, proj, w, h, objs=None, sink=0.003, top=0.56):
    """A raised rib on the body (or on objs) along a path given in projection: w wide at
    its foot, top x w at its crest, h proud, a closed solid."""
    P, N = [], []
    for q in pts:
        loc, n = on_body(q[0], q[1], proj, objs)
        if loc is not None:
            P.append(loc)
            N.append(n)
    if len(P) < 2:
        return
    vs = []
    for i in range(len(P)):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        sd = N[i].cross(t).normalized()
        b = P[i] - N[i] * sink
        vs += [b + sd * w / 2, b - sd * w / 2, P[i] + N[i] * h - sd * w * top / 2,
               P[i] + N[i] * h + sd * w * top / 2]
    k = len(P) - 1
    faces = [(0, 1, 2, 3), tuple(4 * k + j for j in range(4))]
    for i in range(k):
        faces += [(4 * i + j, 4 * i + (j + 1) % 4, 4 * i + 4 + (j + 1) % 4, 4 * i + 4 + j)
                  for j in range(4)]
    g.add(vs, faces)


def plate(g, base, along, up, poly, th0, th1=None, tmax=1.0):
    """A flat blade: poly as (a, t) in the plane through base spanned by along and up, th0
    thick at t = 0 and th1 at t = tmax. Returns the plane's normal."""
    base, along, up = V3(base), V3(along).normalized(), V3(up).normalized()
    n = along.cross(up).normalized()
    th1 = th0 if th1 is None else th1
    lo, hi = [], []
    for (a, t) in poly:
        q = base + along * a + up * t
        th = th0 + (th1 - th0) * min(1.0, max(0.0, t / tmax))
        lo.append(q - n * th / 2)
        hi.append(q + n * th / 2)
    m = len(poly)
    g.add(lo + hi, [tuple(range(m)), tuple(range(m, 2 * m))]
          + [(i, (i + 1) % m, m + (i + 1) % m, m + i) for i in range(m)])
    return n


def chine(x, objs=None, reach=1.6):
    """The widest point of the body as built at x, seen from above (None off the body)."""
    lo, hi = 0.0, reach
    if on_body(x, lo, 'z', objs)[0] is None:
        return None
    for _ in range(18):
        mid = (lo + hi) / 2
        if on_body(x, mid, 'z', objs)[0] is not None:
            lo = mid
        else:
            hi = mid
    loc = on_body(x, lo - 0.0015, 'z', objs)[0]
    return V3((x, lo, loc.z)) if loc is not None else None


def walk(path, step, closed=True):
    """Points every step along a path of (x, y) or 3D points (the step fitted to its
    length; a closed path by default): [(point, tangent, normal)], the normal in plan, to
    the right of the way round (outward on a counterclockwise outline)."""
    pts = [V3((q[0], q[1], q[2] if len(q) > 2 else 0.0)) for q in path]
    segs = list(zip(pts, pts[1:] + pts[:1])) if closed else list(zip(pts, pts[1:]))
    total = sum((b - a).length for a, b in segs)
    n = max(1, int(round(total / step)))
    out, k, s0 = [], 0, 0.0
    for a, b in segs:
        ln = (b - a).length
        if ln < 1e-9:
            continue
        t = (b - a) / ln
        while k < n and (k + 0.5) * total / n <= s0 + ln + 1e-9:
            nr = V3((t.y, -t.x, 0))
            out.append((a + t * ((k + 0.5) * total / n - s0), t,
                        nr.normalized() if nr.length > 1e-6 else V3((0, 1, 0))))
            k += 1
        s0 += ln
    return out


def flutes(g, run, lo, hi, pitch, proj='y', a=0.008, b=0.0035, h=0.006, sink=0.002,
           objs=None, keep=None):
    """A row of flutes on the body: bars from the surface at v = lo to the surface at
    v = hi, every pitch along u over run = (u0, u1), seen along proj (as on_body: on a flank
    u is x and v is z). Each is 2a wide at its foot, 2b at its crest and h proud; keep(p_lo,
    p_hi) may refuse one. Returns how many were laid."""
    u0, u1 = run
    span = abs(u1 - u0)
    n = int(span / pitch)
    off = (span - n * pitch) / 2
    sg = 1.0 if u1 >= u0 else -1.0
    laid = 0
    for k in range(n + 1):
        u = u0 + sg * (off + k * pitch)
        p0, n0 = on_body(u, lo, proj, objs)
        p1, n1 = on_body(u, hi, proj, objs)
        if p0 is None or p1 is None or (keep is not None and not keep(p0, p1)):
            continue
        ax = (p1 - p0).normalized()
        ring = []
        for q, nn in ((p0, n0), (p1, n1)):
            sd = ax.cross(nn).normalized()
            ring += [q - nn * sink - sd * a, q - nn * sink + sd * a, q + nn * h + sd * b,
                     q + nn * h - sd * b]
        g.hexa(ring)
        laid += 1
    return laid


BOLT = [(-0.002, 0.0015), (-0.002, 0.0065), (0.0035, 0.0065), (0.0035, 0.0015)]


def bolt_row(g, pts, pitch, proj=None, objs=None, prof=None, seg=6, ends=True):
    """Bolt heads every pitch (fitted) along a path on the body: pts in projection with
    proj (as on_body), else 3D points near the surface (snapped onto it). prof: the head's
    lathe profile (BOLT: a 13 mm hexagon 3.5 mm proud). ends: one at each end of the path
    too. Returns how many were laid."""
    P = [V3((q[0], q[1], q[2] if len(q) > 2 else 0.0)) for q in pts]
    total = sum((b - a).length for a, b in zip(P, P[1:]))
    n = max(1, int(round(total / pitch)))
    want = [total * k / n for k in range(n + 1)] if ends else \
        [total * (k + 0.5) / n for k in range(n)]
    laid, s0, i = 0, 0.0, 0
    for (a, b) in zip(P, P[1:]):
        ln = (b - a).length
        while i < len(want) and want[i] <= s0 + ln + 1e-9:
            q = a.lerp(b, (want[i] - s0) / ln if ln > 1e-9 else 0.0)
            loc, nn = on_body(q.x, q.y, proj, objs) if proj else snap(q, objs)
            if loc is not None:
                stud(g, loc, nn, prof or BOLT, seg)
                laid += 1
            i += 1
        s0 += ln
    return laid


def built_at(xs, i):
    """Where station i's edge is built along an uncreased line whose stations stand at xs:
    subdivision draws it toward its neighbors, (previous + 4 x + next) / 6."""
    return (xs[i - 1] + 4 * xs[i] + xs[i + 1]) / 6.0


def solve_stations(xs, want):
    """xs with the stations in want = {index: where its edge should be built} moved so
    that their edges are built there (a door's shut lines, a hatch's edge); the others stay.
    For a line that is not creased across those stations; use it on x, y or z alike."""
    x = list(xs)
    for _ in range(60):
        for i, w in want.items():
            x[i] = (6.0 * w - x[i - 1] - x[i + 1]) / 4.0
    return x


def stud(g, loc, n, prof, seg):
    """A lathe profile standing on the surface point loc along its normal n."""
    xf = Matrix.Translation(loc) @ V3((0, 1, 0)).rotation_difference(n).to_matrix().to_4x4()
    g.lathe(prof, seg, xf=xf)


# ---------------------------------------------------------------------------------------
# cut lines, pockets and lamps
# ---------------------------------------------------------------------------------------
def rounded(cx, cy, w, h, r=None, n=5):
    """A rounded rectangle as 2D points, counterclockwise: w by h about (cx, cy), corners
    of radius r (half the shorter side by default: a slot) in n steps."""
    r = min(w, h) / 2 if r is None else min(r, w / 2, h / 2)
    out = []
    for sx, sy, a0 in ((1, -1, -90), (1, 1, 0), (-1, 1, 90), (-1, -1, 180)):
        ox, oy = cx + sx * (w / 2 - r), cy + sy * (h / 2 - r)
        for k in range(n + 1):
            a = rad(a0 + 90.0 * k / n)
            q = (ox + r * cos(a), oy + r * sin(a))
            if not out or hypot(q[0] - out[-1][0], q[1] - out[-1][1]) > 1e-6:
                out.append(q)
    if hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


def ngon(cx, cy, r, n, rot=0.0):
    """A regular polygon as 2D points, counterclockwise, its first corner at rot degrees."""
    return [(cx + r * cos(rad(rot) + 2 * pi * k / n), cy + r * sin(rad(rot) + 2 * pi * k / n))
            for k in range(n)]


def trace(pts, proj=None, closed=False, step=0.008, objs=None, out=None, smooth=3):
    """A path laid on the surface, [(point, normal)]: pts in projection with proj (as
    on_body), else 3D points near the surface, snapped onto it; a point every step and at
    every corner. Points that miss the surface are left out. smooth: rounds of averaging
    each normal with its neighbors along the path (a path beside a crease finds normals of
    both sides of it, and what is swept along it would twist)."""
    P = [V3((q[0], q[1], q[2] if len(q) > 2 else 0.0)) for q in pts]
    if closed:
        P = P + [P[0]]
    sam = []
    for a, b in zip(P, P[1:]):
        n = max(1, int((b - a).length / step + 0.999))
        sam += [a.lerp(b, k / n) for k in range(n)]
    if not closed:
        sam.append(P[-1])
    res = []
    for q in sam:
        loc, nn = on_body(q.x, q.y, proj, objs) if proj else snap(q, objs, out)
        if loc is not None and (not res or (loc - res[-1][0]).length > 1e-5):
            res.append((loc, nn))
    if closed and len(res) > 2 and (res[0][0] - res[-1][0]).length < 1e-5:
        res.pop()
    m = len(res)
    for _ in range(smooth if m > 2 else 0):
        N = [n for _, n in res]
        for i in range(m):
            a = N[i - 1] if (closed or i > 0) else N[i]
            b = N[(i + 1) % m] if (closed or i < m - 1) else N[i]
            res[i] = (res[i][0], (a + 2 * N[i] + b).normalized())
    return res


def _both(P, mirror):
    return [(1, P)] + ([(-1, [V3((p.x, -p.y, p.z)) for p in P])] if mirror else [])


def groove(g, pts, proj=None, width=0.0006, depth=0.006, proud=0.006, closed=False,
           step=0.008, mirror=False, objs=None, out=None, up=None):
    """A cut line's cutter in g: a thin blade through the skin along a path (as trace()),
    for build_body's cutters function. Passed as (g, panel, "drop") the panels it cuts get
    the body's gap on both sides of it, so the line is width + 2 gap wide, a shut line like
    any other: a hood's or a hatch's edge, the split between two doors; closed for an
    outline (a flap, a flush handle). Wider and deeper, as (g, housing, "skin", lens), it is
    a light channel under a lens: width and depth may then be functions of the share of
    the path run (0 to 1), and up the one way out of the channel where it should not be
    the skin's normal (a channel cut level into a nose that leans). mirror: the right side
    too. Returns the path [(point, way out)]."""
    tr = trace(pts, proj, closed, step, objs, out)
    if len(tr) < (3 if closed else 2):
        log("groove(): the path misses the body")
        return tr
    P = [q for q, _ in tr]
    N = [n for _, n in tr] if up is None else [V3(up).normalized()] * len(P)
    wf = width if callable(width) else (lambda t: width)
    df = depth if callable(depth) else (lambda t: depth)
    while True:
        # the sections; one that folds back over the one before it (the inside of a turn
        # tighter than the channel is wide or deep) is left out, the straighter of the two
        m = len(P)
        S = [0.0]
        for a, b in zip(P, P[1:] + (P[:1] if closed else [])):
            S.append(S[-1] + (b - a).length)
        ring, E, T, turn = [], [[], []], [], []
        for i in range(m):
            tp = (P[i] - P[i - 1]).normalized() if (closed or i > 0) else None
            tn = (P[(i + 1) % m] - P[i]).normalized() if (closed or i < m - 1) else None
            tp, tn = tp or tn, tn or tp
            t = (tp + tn).normalized()
            sd = t.cross(N[i]).normalized()
            upv = sd.cross(t).normalized()
            k = 1.0 / max(0.35, ((1 + tp.dot(tn)) / 2) ** 0.5)
            f = S[i] / S[-1]
            a = sd * (wf(f) / 2 * k)
            ring += [P[i] - a - upv * df(f), P[i] + a - upv * df(f), P[i] + a + upv * proud,
                     P[i] - a + upv * proud]
            E[0].append(P[i] + a)
            E[1].append(P[i] - a)
            T.append(t)
            turn.append(1 - tp.dot(tn))
        bad = None
        for i in range(m if closed else m - 1):
            i2 = (i + 1) % m
            tt = (P[i2] - P[i]).normalized()
            if any((ring[4 * i2 + j] - ring[4 * i + j]).dot(tt) <= 1e-5 for j in range(4)):
                cand = [c for c in (i, i2) if closed or 0 < c < m - 1]
                if cand:
                    bad = min(cand, key=lambda c: turn[c])
                    break
        if bad is None or m <= (4 if closed else 3):
            break
        P.pop(bad)
        N.pop(bad)
    faces = []
    for i in range(m if closed else m - 1):
        i2 = (i + 1) % m
        faces += [(4 * i + j, 4 * i + (j + 1) % 4, 4 * i2 + (j + 1) % 4, 4 * i2 + j)
                  for j in range(4)]
    if not closed:
        faces += [(0, 1, 2, 3), tuple(4 * (m - 1) + j for j in range(4))]
    wide = max(wf(0.0), wf(0.5), wf(1.0)) >= 0.004
    for sgn, Q in _both(ring, mirror):
        g.add(Q, faces)
        for e in (E if wide else [P]):
            q = [V3((v.x, sgn * v.y, v.z)) for v in e]
            CUTS.append(q + ([q[0]] if closed else []))
    return list(zip(P, N))


class Pocket:
    """What pocket() returns: where a pocket was cut (its left one when mirrored), for
    building what stands in it. P, N: its outline on the skin; d: the way in; b: the
    floor's normal (pointing in); c, n: the skin's point and normal at its middle."""

    def __init__(self, P, N, d, b, c0, proj, tree):
        self.P, self.N, self.d, self.b, self._c0 = P, N, d, b, c0
        self.proj, self.tree = proj, tree
        mid = sum(P, V3()) / len(P)
        hit = tree.ray_cast(mid - d * 0.5, d)
        self.c = hit[0] if hit[0] is not None else mid
        self.n = (hit[1] if hit[0] is not None else -d).copy()
        if self.n.dot(d) > 0:
            self.n = -self.n

    def on(self, a, b=None, back=0.0):
        """The skin's point at (a, b) of the pocket's projection (or under the 3D point a,
        seen along the way in), moved back along the way in. None off the skin."""
        if b is not None and self.proj:
            loc = on_body(a, b, self.proj, self.tree)[0]
        else:
            loc = self.tree.ray_cast(V3(a) - self.d * 0.5, self.d)[0]
        return None if loc is None else loc + self.d * back

    def at(self, a, b=None, lift=0.0):
        """The floor's point behind on(a, b), lift off it toward the outside."""
        q = self.on(a, b)
        if q is None:
            return None
        return q + self.d * ((self._c0 - q.dot(self.b)) / self.d.dot(self.b) - lift)

    def deep(self, a, b=None):
        """How deep the pocket is behind on(a, b)."""
        q = self.on(a, b)
        return None if q is None else (self.at(a, b) - q).length


def pocket(g, pts, proj=None, depth=0.05, proud=0.006, dir=None, back=None, step=0.01,
           mirror=False, objs=None, out=None):
    """A pocket's cutter in g, for build_body's cutters function: the outline pts (as
    trace(), closed) pushed straight in along dir (the skin's own way in at the outline by
    default) to a flat floor at least depth behind every point of the outline (back: the
    floor's normal when it should not be dir, such as a lamp's back standing upright in a
    leaning nose). Passed as (g, housing, "skin", lens) it is a lamp's housing under its
    lens, or a recess under a handle; as (g, panel) a plain recess; as (g, panel, "drop")
    a hole. mirror: the right side too. Returns a Pocket (None when the outline misses)."""
    tr = trace(pts, proj, True, step, objs, out)
    if len(tr) < 3:
        log("pocket(): the outline misses the body")
        return None
    P, N = [q for q, _ in tr], [n for _, n in tr]
    d = V3(dir).normalized() if dir is not None else -sum(N, V3()).normalized()
    b = V3(back).normalized() if back is not None else d
    if b.dot(d) < 0:
        b = -b
    tree = _tree(objs)
    # the lid: a flat cap in front of everything of the skin inside the outline
    mid = sum(P, V3()) / len(P)
    front = min(q.dot(d) for q in P)
    for q in [mid] + [mid.lerp(q, 0.5) for q in P[::max(1, len(P) // 12)]]:
        hit = tree.ray_cast(q - d * 0.5, d)[0]
        if hit is not None and (hit - q).length < 0.3:
            front = min(front, hit.dot(d))
    c0 = max((q + d * depth).dot(b) for q in P)
    top = [q + d * (front - proud - q.dot(d)) for q in P]
    bot = [q + d * ((c0 - q.dot(b)) / d.dot(b)) for q in P]
    n = len(P)
    faces = [tuple(range(n)), tuple(range(n, 2 * n))]
    faces += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    for sgn, Q in _both(top + bot, mirror):
        g.add(Q, faces)
    for sgn, Q in _both(P, mirror):
        CUTS.append(Q + [Q[0]])
    return Pocket(P, N, d, b, c0, proj, tree)


class Lamp:
    """The inside of a lamp, gathered by material and made into objects by obj():
    <name>.housing (dark plastic), .chrome (reflectors, bezels), .glass (clear lenses),
    .optic (frosted light guides) and .lit (the emitters, in the lit material: led_front,
    led_rear, led_accent, ... ; a call's own lit= puts its emitter in another one, such as
    an amber turn signal beside a white lamp). The Geos are open to a car's own parts:
    lamp.housing.box(...), lamp.chrome.prism(...), lamp.emit("led_rear").box(...)."""

    def __init__(self, name, lit="led_front", housing="lamp_housing", chrome="chrome",
                 glass="lens_clear", optic="optic"):
        self.name, self.lit = name, lit
        self.mats = dict(housing=housing, chrome=chrome, glass=glass, optic=optic)
        self.housing, self.chrome, self.glass, self.optic = Geo(), Geo(), Geo(), Geo()
        self.lits = {}

    def emit(self, lit=None):
        return self.lits.setdefault(lit or self.lit, Geo())

    def projector(self, at, dir, r=0.032, depth=0.055, lit=None, seg=24):
        """A projector module shining along dir, its bezel's front at at: a bright bezel,
        a dark barrel, a clear convex lens and the emitter behind it."""
        kw = dict(axis=dir, at=at)
        self.chrome.lathe([(0.0, r), (0.0, r * 1.22), (-0.004, r * 1.28), (-0.016, r * 1.28),
                           (-0.016, r)], seg, **kw)
        self.housing.lathe([(-0.016, r), (-0.016, r * 1.05), (-depth, r * 0.66),
                            (-depth, r * 0.6)], seg, **kw)
        self.housing.lathe([(-depth, 0.0006), (-depth, r * 0.66), (-depth - 0.003, r * 0.66),
                            (-depth - 0.003, 0.0006)], seg, **kw)
        a, h = r * 0.97, r * 0.5
        rs = (a * a + h * h) / (2 * h)
        tm = asin(min(1.0, a / rs))
        dome = [(-0.006 + h - rs * (1 - cos(tm * k / 8)), max(0.0006, rs * sin(tm * k / 8)))
                for k in range(9)]
        self.glass.lathe([(-0.014, 0.0006), (-0.014, a)] + dome[::-1], seg, **kw)
        e0 = -depth * 0.78
        self.emit(lit).lathe([(e0, 0.0006), (e0, r * 0.5), (e0 + 0.003, r * 0.5),
                              (e0 + 0.003, 0.0006)], max(8, seg // 2), **kw)

    def reflector(self, at, dir, r=0.04, depth=0.03, lit=None, seg=10, led=None):
        """A faceted reflector bowl opening along dir, its rim at at, an emitter in its
        base."""
        kw = dict(axis=dir, at=at)
        r0 = led or r * 0.2
        inner = []
        for k in range(7):
            q = r0 + (r - r0) * k / 6
            inner.append((-depth * (1 - (q / r) ** 2), q))
        self.chrome.lathe(inner + [(0.0, r * 1.07), (-depth - 0.003, r0 * 1.2),
                                   (-depth - 0.003, r0 * 0.5), (inner[0][0], r0 * 0.5)],
                          seg, **kw)
        e0 = inner[0][0] - 0.001
        self.emit(lit).lathe([(e0, 0.0005), (e0, r0), (e0 + 0.006, r0 * 0.85),
                              (e0 + 0.006, 0.0005)], max(8, seg), **kw)

    def leds(self, a, b, n, dir, r=0.008, lit=None, seg=8):
        """n small emitters in cups, spread from a to b, shining along dir."""
        a, b = V3(a), V3(b)
        for k in range(n):
            self.reflector(a.lerp(b, (k + 0.5) / n), dir, r, r * 0.8, lit, seg)

    def guide(self, path, r=0.0045, sleeve=1.7, lit=None, closed=False, up=(0, 0, 1), n=8):
        """A light guide along a path: a lit core in a frosted sleeve sleeve times as thick
        (0: the bare core)."""
        self.emit(lit).pipe(path, r, n, closed, up)
        if sleeve:
            self.optic.pipe(path, r * sleeve, max(n, 10), closed, up)

    def bar(self, path, w, h, up=(0, 0, 1), lit=None, closed=False):
        """A lit bar along a path: w across (square to up), h along up."""
        self.emit(lit).sweep(path, [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2),
                                    (-w / 2, h / 2)], up=up, closed=closed)

    def fins(self, a, b, c, d, n, w, th, tilt, out, which="housing", **kw):
        """n blades from the a-b edge to the d-c edge (Geo.louvers) in the housing's
        material, or the chrome's: the inner structure behind a tail lamp's lens."""
        getattr(self, which).louvers(a, b, c, d, n, w, th, tilt, out, **kw)

    def obj(self, mirror=False, coll=None):
        """The objects, {part: object}."""
        res = {}
        for key, bev, sharp in (("housing", 0.0012, None), ("chrome", 0.0, 35.0),
                                ("glass", 0.0, 40.0), ("optic", 0.0, 40.0)):
            g = getattr(self, key)
            if g.v:
                res[key] = g.obj("%s.%s" % (self.name, key), self.mats[key], bevel=bev,
                                 mirror=mirror, sharp=sharp, coll=coll)
        many = len(self.lits) > 1
        for lit, g in self.lits.items():
            if g.v:
                nm = "%s.lit" % self.name + ("." + lit if many else "")
                res["lit." + lit] = g.obj(nm, lit, mirror=mirror, coll=coll)
        return res


def wiper(arm, blade, pivot, a, b, objs=None, out=None, boss=0.016):
    """A wiper at rest on the glass: a boss on the surface at pivot, a tapered arm from it
    to the blade's middle, a yoke, the blade's spine and its rubber lying on the glass from
    a to b (3D points near the surface, snapped onto it as built). arm and blade are the
    Geos of the metal and of the rubber."""
    tr = trace([a, b], None, False, 0.03, objs, out)
    pv, pn = snap(pivot, objs, out)
    if len(tr) < 2 or pv is None:
        log("wiper(): off the glass")
        return
    P, N = [q for q, _ in tr], [n for _, n in tr]
    xf = Matrix.Translation(pv) @ V3((0, 1, 0)).rotation_difference(pn).to_matrix().to_4x4()
    arm.lathe([(-0.002, 0.001), (-0.002, boss), (0.010, boss), (0.016, boss * 0.6),
               (0.016, 0.001)], 16, xf=xf)
    k = len(P) // 2
    mid, mn = P[k] + N[k] * 0.022, N[k]
    top = pv + pn * 0.014
    t = (mid - top).normalized()
    sd0, sd1 = pn.cross(t).normalized(), mn.cross(t).normalized()
    arm.hexa([top + sd0 * 0.008, top - sd0 * 0.008, mid - sd1 * 0.0045, mid + sd1 * 0.0045,
              top + sd0 * 0.008 + pn * 0.006, top - sd0 * 0.008 + pn * 0.006,
              mid - sd1 * 0.0045 + mn * 0.004, mid + sd1 * 0.0045 + mn * 0.004])
    along = (P[-1] - P[0]).normalized()
    arm.box(P[k] + mn * 0.016, (0.05, 0.012, 0.012),
            rot=Matrix((along, mn.cross(along).normalized(), mn)).transposed())
    arm.sweep([q + n * 0.0115 for q, n in tr],
              [(-0.005, -0.002), (0.005, -0.002), (0.0035, 0.003), (-0.0035, 0.003)], up=N)
    blade.sweep([q + n * 0.005 for q, n in tr],
                [(-0.0022, -0.0048), (0.0022, -0.0048), (0.003, 0.0046), (-0.003, 0.0046)],
                up=N)


_FONT = [None]
FONTS = ("/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf",
         "C:/Windows/Fonts/bahnschrift.ttf")
# the faces a car may ask for by name with font= (the first file found; else the default)
FONT_SETS = {
    "din": FONTS,
    "condensed": ("/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf",
                  "C:/Windows/Fonts/bahnschrift.ttf"),
    "serif": ("/System/Library/Fonts/Supplemental/Didot.ttc",
              "/System/Library/Fonts/Supplemental/Bodoni 72.ttc",
              "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
              "C:/Windows/Fonts/timesbd.ttf"),
    "mono": ("/System/Library/Fonts/Menlo.ttc",
             "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
             "C:/Windows/Fonts/consolab.ttf"),
}
_FONTS = {}


def load_font(name):
    """A loaded font: a name of FONT_SETS or a file's path (None when nothing is found)."""
    if name not in _FONTS:
        _FONTS[name] = None
        for p in FONT_SETS.get(name, (name,)):
            if os.path.exists(p):
                _FONTS[name] = bpy.data.fonts.load(p)
                break
    return _FONTS[name]


def text_mesh(txt, size, spacing=1.0, font=None, align=None):
    """Flat outline text as (verts, faces), centered on its origin. font: a name of
    FONT_SETS ("din", "condensed", "serif", "mono") or a font file; align: "baseline" puts
    the origin on the baseline (the middle of the text's height otherwise)."""
    cu = bpy.data.curves.new("txt", 'FONT')
    cu.body = txt
    cu.size = size
    cu.space_character = spacing
    cu.align_x = 'CENTER'
    cu.align_y = 'BOTTOM_BASELINE' if align == "baseline" else 'CENTER'
    if _FONT[0] is None:
        _FONT[0] = False
        for p in FONTS:
            if os.path.exists(p):
                _FONT[0] = bpy.data.fonts.load(p)
                break
    own = load_font(font) if font else None
    if own or _FONT[0]:
        cu.font = own or _FONT[0]
    ob = bpy.data.objects.new("txt", cu)
    SCN.collection.objects.link(ob)
    me = evaluated_mesh(ob)
    vs = [v.co.copy() for v in me.vertices]
    fs = [tuple(p.vertices) for p in me.polygons]
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return vs, fs


def text_on_body(g, txt, size, x0, z0, side, lift=0.0012, spacing=1.0, proj=None, turn=0.0,
                 objs=None, font=None, align=None, tol=0.0):
    """Text on the body's flank, reading left to right for someone looking at that side
    (side 1 left, -1 right), its middle at (x0, z0).

    proj='z' lays it on a roof, hood or deck instead, seen from above: its middle at
    x = x0, y = z0, reading left to right for someone standing at the car's left (side 1)
    or right (side -1); turn (degrees, counterclockwise seen from above) turns it from
    there (side 1, turn 90: read from behind the car). proj='x' writes on the nose and
    proj='X' on the tail, read by someone facing it: its middle at y = x0, z = z0 (side is
    not used). objs and tol as on_body()'s, font and align as text_mesh()'s. Nothing is
    added when any of its points misses the surface (the log says so); returns whether it
    was laid."""
    vs, fs = text_mesh(txt, size, spacing, font, align)
    out = []
    if proj == 'z':
        c, s = cos(rad(turn)), sin(rad(turn))
        rx, ry = -side * c, -side * s               # along the text
        ux, uy = side * s, -side * c                # up its letters
    for p in vs:
        if proj == 'z':
            loc, n = on_body(x0 + rx * p.x + ux * p.y, z0 + ry * p.x + uy * p.y, 'z', objs,
                             tol)
        elif proj in ('x', 'X'):
            loc, n = on_body(x0 + (p.x if proj == 'x' else -p.x), z0 + p.y, proj, objs, tol)
        else:
            loc, n = on_body(x0 - side * p.x, z0 + p.y, 'y' if side > 0 else 'Y', objs, tol)
        if loc is None:
            log("text_on_body: %r is not laid, one of its points misses the surface" % txt)
            return False
        out.append(loc + n * lift)
    g.add(out, fs)
    return True


def text_flat(g, txt, size, origin, right, up, spacing=1.0, font=None, align=None):
    """Text on a plane: its middle at origin, reading along right."""
    vs, fs = text_mesh(txt, size, spacing, font, align)
    o, r, u = V3(origin), V3(right), V3(up)
    g.add([o + r * p.x + u * p.y for p in vs], fs)


# ---------------------------------------------------------------------------------------
# wheels
# ---------------------------------------------------------------------------------------
TREADS = {      # grooves (shares of the width), their half widths (top, bottom) and depth,
                # every which block sunk and its shift a land, the blocks' inset and depth
    "road": dict(grooves=(-0.24, 0.0, 0.24), gw=(0.012, 0.007), gd=0.009, mod=4, shift=2,
                 inset=(0.002, 0.007), seg=144),
    "all_terrain": dict(grooves=(-0.2, 0.2), gw=(0.016, 0.009), gd=0.013, mod=2, shift=1,
                        inset=(0.004, 0.011), seg=96),
    "lug": dict(grooves=(0.0,), gw=(0.022, 0.012), gd=0.018, mod=2, shift=1,
                inset=(0.006, 0.016), seg=72),
}


def build_wheel(tag, cx, R, w, Rr, out_y, side, cz=None, spokes=7, style="twin",
                ring="led_wheel", caliper="caliper", rim="rim", bright="rim_bright",
                tire="rubber", loc=None, rot=None, tread="road"):
    """A wheel on its axle, as objects tire.<tag>, rim.<tag>, hub.<tag>, ring.<tag>,
    disc.<tag>, caliper.<tag>, drum.<tag>, all at the wheel's middle (they can turn).

    cx axle x, R tire radius, w tire width, Rr rim radius, out_y the tire's outer face,
    side 1 left or -1 right, cz axle height (R: standing on the ground). spokes and style
    ("twin" pairs of blades, "blade" single swept blades, "disc" a closed dish). ring,
    caliper: material names, None for no light ring, no brake. tire=None leaves the tire
    out and rim=None the rim and its hub (bright=None the hub alone), for a car that brings
    its own under the same names. rim may also be the car's own rim builder, called as
    rim(tag, w, Rr, flip, loc, rot) to make rim.<tag> at loc (the kit's hub, ring and
    brake still come unless switched off). tread: a name of TREADS ("road", "all_terrain",
    "lug") or such a dict. loc puts the wheel's middle somewhere else and rot (an Euler,
    three angles or a matrix) turns it there: a spare. Nothing here needs a wheel well: an
    exposed wheel is the same call.
    """
    hw = w / 2
    flip = side < 0
    loc = (cx, side * (out_y - hw), R if cz is None else cz) if loc is None else tuple(loc)
    td = TREADS[tread] if isinstance(tread, str) else tread
    N = td["seg"]
    if tire:
        _tire(tag, R, w, Rr, N, tire, flip, loc, rot, td)
    if callable(rim):
        rim(tag, w, Rr, flip, loc, rot)
    elif rim:
        _rim(tag, w, Rr, spokes, style, rim, flip, loc, rot)
    if rim and bright:
        g = Geo()
        g.lathe([(hw - 0.062, 0.004), (hw - 0.062, 0.036), (hw - 0.046, 0.030),
                 (hw - 0.046, 0.004)], 6)
        for k in range(5):
            a = 2 * pi * (k + 0.5) / 5
            g.lathe([(hw - 0.064, 0.002), (hw - 0.064, 0.0095), (hw - 0.052, 0.0095),
                     (hw - 0.052, 0.002)], 6,
                    xf=Matrix.Translation((0.052 * cos(a), 0, 0.052 * sin(a))))
        g.lathe([(hw - 0.0065, Rr - 0.006), (hw - 0.0065, Rr + 0.0015),
                 (hw - 0.003, Rr + 0.0015), (hw - 0.003, Rr - 0.006)], 72)
        g.obj("hub." + tag, bright, bevel=0.0015, flip_y=flip, loc=loc, rot=rot)
    if ring:
        g = Geo()
        for k in range(6):
            g.lathe([(hw - 0.016, Rr - 0.019), (hw - 0.016, Rr - 0.008), (hw - 0.0085, Rr - 0.008),
                     (hw - 0.0085, Rr - 0.019)], 10, a0=rad(k * 60 + 5), a1=rad(k * 60 + 55))
        g.obj("ring." + tag, ring, flip_y=flip, loc=loc, rot=rot)
    if caliper:
        g = Geo()
        g.lathe([(hw - 0.165, 0.09), (hw - 0.165, Rr - 0.04), (hw - 0.135, Rr - 0.04),
                 (hw - 0.135, 0.09)], 64)
        g.obj("disc." + tag, "disc", flip_y=flip, loc=loc, sharp=40, rot=rot)
        g = Geo()
        g.lathe([(hw - 0.185, Rr - 0.115), (hw - 0.185, Rr - 0.026), (hw - 0.112, Rr - 0.026),
                 (hw - 0.112, Rr - 0.115)], 5, a0=rad(138), a1=rad(202))
        g.obj("caliper." + tag, caliper, bevel=0.004, flip_y=flip, loc=loc, rot=rot)
    g = Geo()
    g.lathe([(-hw + 0.045, 0.004), (-hw + 0.045, Rr - 0.02), (-hw + 0.03, Rr - 0.02),
             (-hw + 0.03, 0.004)], 48)
    g.obj("drum." + tag, "well", flip_y=flip, loc=loc, rot=rot)


def _tire(tag, R, w, Rr, N, tire, flip, loc, rot, td=None):
    """The tire: grooves, tread blocks, sidewall lettering."""
    td = td or TREADS["road"]
    hw = w / 2
    g = Geo()
    grooves = [w * k for k in td["grooves"]]
    g0, g1 = td["gw"]
    gd = td["gd"]

    def wall(sg):
        return [(sg * (hw - 0.048), R), (sg * (hw - 0.030), R - 0.006),
                (sg * (hw - 0.012), R - 0.018), (sg * (hw - 0.002), R - 0.030),
                (sg * (hw + 0.002), R - 0.034), (sg * (hw + 0.005), R - 0.035),
                (sg * (hw + 0.005), R - 0.039), (sg * (hw + 0.003), R - 0.041),
                (sg * (hw + 0.004), R - 0.046), (sg * (hw + 0.004), Rr + 0.024),
                (sg * (hw + 0.002), Rr + 0.019), (sg * (hw + 0.004), Rr + 0.016),
                (sg * (hw + 0.004), Rr + 0.011), (sg * (hw - 0.004), Rr + 0.006),
                (sg * (hw - 0.022), Rr - 0.004)]
    prof = wall(-1)[::-1]
    for c in grooves:
        prof += [(c - g0, R), (c - g1, R - gd), (c + g1, R - gd), (c + g0, R)]
    prof += wall(1)
    g.lathe(prof, N)
    tob = g.obj("tire." + tag, tire, flip_y=flip, loc=loc, rot=rot)
    bm = bmesh.new()
    bm.from_mesh(tob.data)
    edges = [-hw] + grooves + [hw]
    sel = []
    for f in bm.faces:
        c = f.calc_center_median()
        if hypot(c.x, c.z) < R * cos(pi / N) - 1e-4:
            continue
        k = int((atan2(c.z, c.x) % (2 * pi)) / (2 * pi / N))
        land = sum(1 for e in edges if abs(c.y) * (1 if c.y > 0 else -1) > e)
        if (k + td["shift"] * land) % td["mod"] == 0:
            sel.append(f)
    bmesh.ops.inset_individual(bm, faces=sel, thickness=td["inset"][0], depth=-td["inset"][1])
    word = "1110110111011001111011011100000000001011101101110110011110000000000000"
    bm.faces.ensure_lookup_table()
    let = []
    for f in bm.faces:
        c = f.calc_center_median()
        r = hypot(c.x, c.z)
        if abs(c.y) > hw + 0.0035 and Rr + 0.026 < r < R - 0.048:
            k = int((atan2(c.z, c.x) % (2 * pi)) / (2 * pi / N))
            if word[k % len(word)] == "1":
                let.append(f)
    bmesh.ops.inset_individual(bm, faces=let, thickness=0.0012, depth=0.0012)
    bm.to_mesh(tob.data)
    bm.free()
    tob.data.shade_smooth()
    tob.data.set_sharp_from_angle(angle=rad(32))


def _rim(tag, w, Rr, spokes, style, rim, flip, loc, rot):
    """The rim: barrel, blades, hub."""
    hw = w / 2
    g = Geo()
    g.lathe([(-hw + 0.03, Rr), (hw - 0.006, Rr), (hw - 0.006, Rr - 0.006),
             (hw - 0.016, Rr - 0.006), (hw - 0.016, Rr - 0.02), (-hw + 0.03, Rr - 0.02)], 72)
    r0, r1 = 0.066, Rr - 0.018
    y0, y1 = hw - 0.078, hw - 0.026
    ks = 7.0 / spokes
    blades = {"twin": ((-16, -3, 4, 13), (3, 16, 19, 28)), "blade": ((-11, 11, 6, 20),)}
    if style == "disc":
        g.lathe([(y0 - 0.03, r0), (y1 - 0.016, r1), (y1, r1), (y0, r0)], 72)
        for k in range(spokes):
            a = 2 * pi * k / spokes
            rm = (r0 + r1) / 2
            g.box((rm * cos(a), (y0 + y1) / 2 + 0.004, rm * sin(a)),
                  ((r1 - r0) * 0.62, 0.012, 0.012), rot=Matrix.Rotation(-a, 3, 'Y'))
    else:
        for k in range(spokes):
            th = 2 * pi * k / spokes

            def pt(r, a, y):
                return (r * cos(th + a), y, r * sin(th + a))
            for (a_in0, a_in1, a_o0, a_o1) in blades[style]:
                fr = [pt(r0, rad(a_in0 * ks), y0), pt(r1, rad(a_o0 * ks), y1),
                      pt(r1, rad(a_o1 * ks), y1), pt(r0, rad(a_in1 * ks), y0)]
                bk = [(p[0], p[1] - t, p[2]) for p, t in zip(fr, (0.034, 0.02, 0.02, 0.034))]
                g.hexa(bk + fr)
    g.lathe([(hw - 0.135, 0.004), (hw - 0.135, 0.082), (hw - 0.072, 0.082),
             (hw - 0.062, 0.068), (hw - 0.062, 0.004)], 14)
    g.obj("rim." + tag, rim, bevel=0.005, flip_y=flip, loc=loc, rot=rot)


# ---------------------------------------------------------------------------------------
# studio, cameras, render
# ---------------------------------------------------------------------------------------
def aim(ob, target):
    d = V3(target) - ob.location
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


STUDIO_R, COVE_R = 16.0, 9.0        # the floor is flat to STUDIO_R, the cove's radius beyond
# The day studio's lights (name: where it stands, what it aims at, its size, watts). The top
# box is long ACROSS the car (7.5 m along y, 2.8 m along x), so glass that looks at the sky
# or leans in more than about 25 degrees mirrors it; unlit() keeps a light off such glass.
LIGHTS = {"top": ((0.2, 0, 5.5), (0, 0, 0), (7.5, 2.8), 900),
          "key": ((5.0, 5.5, 3.2), (0.5, 0, 0.5), (4.0, 2.5), 620),
          "rim": ((-6.0, -5.0, 5.0), (0, 0, 0.6), (5.0, 1.2), 800),
          "fill": ((5.5, -4.5, 1.6), (0.5, 0, 0.5), (3.0, 2.0), 200),
          "strip": ((0.0, 6.5, 1.3), (0, 0, 0.6), (9.0, 0.45), 300),
          "strip2": ((0.0, -6.5, 1.3), (0, 0, 0.6), (9.0, 0.45), 300)}
UNLIT = {}          # light name -> names of the objects it does not light (unlit())
CABIN_LIGHTS = []   # cabin_light()'s lamps
STUDIO_HOOKS = []   # after_studio()'s functions
VIEW_HOOKS = []     # on_view()'s functions


def unlit(lights, *objs):
    """Keeps studio lights off some objects (light linking): lights is a name of LIGHTS or
    several, objs are objects, names, or names ending in * for every object that starts so.
    unlit("top", "body.canopy") stops the top box from being mirrored whole in a raked
    windshield; the paint and everything else still take it. Call it before shoot()."""
    for name in ([lights] if isinstance(lights, str) else lights):
        UNLIT.setdefault(name, []).extend(o if isinstance(o, str) else o.name for o in objs)


def cabin_light(loc, power=8.0, size=0.5, color=(1.0, 0.95, 0.88), target=None):
    """A soft lamp inside the cabin (a dome light), so the cabin reads through the glass.
    It belongs to the studio, not the car: loc where it hangs, target what it aims at
    (straight down when not given). Call it before shoot()."""
    CABIN_LIGHTS.append((tuple(loc), power, size, tuple(color),
                         tuple(target) if target is not None else None))


def after_studio(fn):
    """fn() is called once the studio is built: a car's own change to its lights."""
    STUDIO_HOOKS.append(fn)


def on_view(fn):
    """fn(view name, True) is called before a view renders and fn(view name, False) after:
    a state of the car's own for some views (a lifted canopy, an open door)."""
    VIEW_HOOKS.append(fn)


def _studio_extras():
    for k, (loc, power, size, color, target) in enumerate(CABIN_LIGHTS):
        L = bpy.data.lights.new("cabin%d" % k, 'AREA')
        L.shape = 'SQUARE'
        L.size = size
        L.energy = power
        L.color = color
        o = bpy.data.objects.new("cabin%d" % k, L)
        STUDIO.objects.link(o)
        o.location = loc
        aim(o, target if target is not None else (loc[0], loc[1], loc[2] - 1.0))
        o.visible_camera = False
    for name, skip in UNLIT.items():
        light = STUDIO.objects.get(name)
        if light is None:
            continue
        exact = {n for n in skip if not n.endswith("*")}
        heads = tuple(n[:-1] for n in skip if n.endswith("*"))
        rec = bpy.data.collections.new(name + ".receivers")
        for ob in list(CAR.objects) + list(STUDIO.objects):
            if ob.type == 'MESH' and ob.name not in exact and not (heads and
                                                                   ob.name.startswith(heads)):
                rec.objects.link(ob)
        try:
            light.light_linking.receiver_collection = rec
        except Exception as e:
            print("light linking:", e)
    for fn in STUDIO_HOOKS:
        fn()


class Group:
    """Parts that move as one: a door, a hatch, a hood, a canopy. The objects hang on an
    empty at the pivot (outside the car's collection, so nothing counts it); pose() moves
    them from where they were built and rest() puts them back.

        door = K.Group("door", [panel, glass, handle], pivot=(0.6, 0.95, 0.4))
        door.pose_for(("hero", "side"), loc=(-0.9, 0.06, 0))       # slid open in those views
        lid = K.Group("canopy", parts, pivot=hinge)
        lid.pose(rot=(0, rad(-40), 0))                             # swung about its pivot
    """

    def __init__(self, name, objs, pivot=(0, 0, 0)):
        rig = bpy.data.collections.get("RIG")
        if rig is None:
            rig = bpy.data.collections.new("RIG")
            SCN.collection.children.link(rig)
        self.ob = bpy.data.objects.new(name, None)
        rig.objects.link(self.ob)
        self.ob.location = pivot
        self.pivot = V3(pivot)
        bpy.context.view_layer.update()
        inv = self.ob.matrix_world.inverted()
        self.objs = list(objs)
        for o in self.objs:
            o.parent = self.ob
            o.matrix_parent_inverse = inv
        _PTS.clear()

    def pose(self, loc=(0, 0, 0), rot=(0, 0, 0)):
        """Moved by loc and turned by rot (an Euler, three angles) about the pivot."""
        self.ob.location = self.pivot + V3(loc)
        self.ob.rotation_euler = rot
        bpy.context.view_layer.update()
        _PTS.clear()

    def rest(self):
        self.pose()

    def pose_for(self, views, loc=(0, 0, 0), rot=(0, 0, 0)):
        """The pose in those views (names) and at rest in every other."""
        views = (views,) if isinstance(views, str) else tuple(views)

        def hook(name, before):
            if name in views:
                self.pose(loc, rot) if before else self.rest()
        on_view(hook)


def build_studio():
    """A round cove with soft boxes by day; by night a wet floor and two colored rims.
    The floor is flat to 16 m from the middle, the cove rises to a wall 25 m out, 22 m
    high: room for every view of a vehicle 7 m long (add_camera keeps cameras inside)."""
    g = Geo()
    prof = [(0.0, 0.01), (0.0, STUDIO_R)]
    for k in range(1, 13):
        a = (pi / 2) * k / 12
        prof.append((COVE_R * (1 - cos(a)), STUDIO_R + COVE_R * sin(a)))
    prof.append((22.0, STUDIO_R + COVE_R))
    g.lathe(prof, 96, xf=Matrix.Rotation(pi / 2, 4, 'X'), closed=False)
    ob = g.obj("cyc", "floor", coll=STUDIO)
    ob.data.shade_smooth()
    night = ARGS.night
    m = MAT["floor"]
    nt = m.node_tree
    b = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    if not night:
        # the wall glows a little, so every view has the same even grey behind the car
        tc = nt.nodes.new('ShaderNodeTexCoord')
        sep = nt.nodes.new('ShaderNodeSeparateXYZ')
        nt.links.new(tc.outputs["Object"], sep.inputs[0])
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs["From Min"].default_value = 0.3
        mr.inputs["From Max"].default_value = 7.0
        mr.inputs["To Min"].default_value = 0.0
        mr.inputs["To Max"].default_value = 0.22
        nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
        b.inputs["Emission Color"].default_value = (0.5, 0.5, 0.54, 1)
        nt.links.new(mr.outputs["Result"], b.inputs["Emission Strength"])

    w = bpy.data.worlds.new("world")
    SCN.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs["Color"].default_value = (0.5, 0.5, 0.55, 1.0)
    bg.inputs["Strength"].default_value = 0.004 if night else 0.30

    def area(name, loc, target, sx, sy, power, color=(1, 1, 1)):
        L = bpy.data.lights.new(name, 'AREA')
        L.shape = 'RECTANGLE'
        L.size, L.size_y = sx, sy
        L.energy = power
        L.color = color
        o = bpy.data.objects.new(name, L)
        STUDIO.objects.link(o)
        o.location = loc
        aim(o, target)
        return o

    if night:
        # wet floor, a teal and a magenta rim, just enough white to read the form
        b.inputs["Base Color"].default_value = (0.02, 0.02, 0.023, 1)
        tc = nt.nodes.new('ShaderNodeTexCoord')
        nz = nt.nodes.new('ShaderNodeTexNoise')
        nz.inputs["Scale"].default_value = 0.55
        nz.inputs["Detail"].default_value = 5.0
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs["From Min"].default_value = 0.42
        mr.inputs["From Max"].default_value = 0.62
        mr.inputs["To Min"].default_value = 0.03
        mr.inputs["To Max"].default_value = 0.42
        nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
        area("top", (0.2, 0, 5.5), (0, 0, 0), 7.0, 2.6, 220)
        area("teal", (-5.5, 5.0, 2.4), (0, 0, 0.6), 6.0, 1.6, 900, (0.05, 0.85, 1.0))
        area("magenta", (5.0, -5.5, 2.0), (0, 0, 0.6), 6.0, 1.6, 900, (1.0, 0.08, 0.55))
        area("front", (7.0, 2.5, 0.9), (1.0, 0, 0.5), 3.0, 0.4, 60)
    else:
        area("top", (0.2, 0, 5.5), (0, 0, 0), 7.5, 2.8, 900)
        area("key", (5.0, 5.5, 3.2), (0.5, 0, 0.5), 4.0, 2.5, 620, (1.0, 0.97, 0.93))
        area("rim", (-6.0, -5.0, 5.0), (0, 0, 0.6), 5.0, 1.2, 800, (0.85, 0.92, 1.0))
        area("fill", (5.5, -4.5, 1.6), (0.5, 0, 0.5), 3.0, 2.0, 200)
        # the two low strips light the flanks and show in the paint, but not to the camera
        # or through glass: a side view looks through both side windows at the far one
        for name, y in (("strip", 6.5), ("strip2", -6.5)):
            o = area(name, (0.0, y, 1.3), (0, 0, 0.6), 9.0, 0.45, 300)
            o.visible_camera = False
            o.visible_transmission = False
    _studio_extras()


_PTS = {}


def _hull(bm):
    """The corners of the convex hull of a bmesh's vertices (none when it has no hull)."""
    try:
        r = bmesh.ops.convex_hull(bm, input=bm.verts[:])
        return [v.co.copy() for v in r["geom"] if isinstance(v, bmesh.types.BMVert)]
    except Exception:
        return []


def car_points(prefixes=None):
    """World points that bound the car as built (or its objects whose names start with one
    of the prefixes): the corners of the convex hull of every vertex, modifiers applied.
    What a view is fitted to, so the fit follows the real silhouette, not the objects'
    boxes."""
    key = (tuple(prefixes) if prefixes else None, len(CAR.objects))
    if key in _PTS:
        return _PTS[key]
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for ob in CAR.objects:
        if prefixes and not any(ob.name.startswith(p) for p in prefixes):
            continue
        own = []
        if ob.type == 'MESH':
            ev = ob.evaluated_get(dg)
            bm = bmesh.new()
            bm.from_mesh(ev.to_mesh())
            ev.to_mesh_clear()
            own = _hull(bm)
            if len(own) < 4:                    # flat or tiny: its own vertices, thinned
                vs = bm.verts[:]
                own = [v.co.copy() for v in vs[::max(1, len(vs) // 2000)]]
            bm.free()
        if not own:
            own = [V3(c) for c in ob.bound_box]
        mw = ob.matrix_world
        pts += [mw @ p for p in own]
    if len(pts) > 8:
        bm = bmesh.new()
        for p in pts:
            bm.verts.new(p)
        all_ = _hull(bm)
        bm.free()
        pts = all_ if len(all_) >= 4 else pts
    _PTS[key] = pts
    return pts


# center=True moves a fitted view's target until the silhouette sits in the middle of the
# frame (a tall car's hero); ortho=True makes it an orthographic drawing (a long vehicle's
# side with no perspective, whatever the studio's depth).
# A view: dir (from the target toward the camera), lens, and either dist or a fit of the
# whole car (fit=(name prefixes) for some objects) with a margin; focus and fstop give
# depth of field. target is optional: without one a view aims at the middle of what it
# fits (the whole car: the middle of its length and of its own height, on the centerline),
# so a hover car or a truck is framed like a low coupe. no_floor hides the studio for the
# view (a camera under the floor). A car changes or adds views in this table before shoot().
VIEWS = {
    "hero": dict(dir=(1.0, 0.78, 0.26), lens=70, focus=(1.6, 0.8, 0.5)),
    "rear": dict(dir=(-1.0, -0.82, 0.30), lens=70, focus=(-1.6, -0.8, 0.6)),
    "rear_l": dict(dir=(-1.0, 0.62, 0.22), lens=70),
    "side": dict(dir=(0.0, 1.0, 0.05), lens=110),
    "front": dict(dir=(1.0, 0.0, 0.07), lens=110),
    "back": dict(dir=(-1.0, 0.0, 0.09), lens=110),
    "top": dict(dir=(0.0, 0.0, 1.0), lens=110),
    "under": dict(dir=(0.0, 0.0, -1.0), lens=110, no_floor=True),
    "low": dict(dir=(1.0, 0.5, 0.045), lens=40, focus=(1.8, 0.7, 0.4), fstop=2.8),
}
FOCUS = {}
# Where a camera may stand (in_studio): inside the cove, CAM_PAD clear of its rising wall,
# CAM_LOW over the flat floor, under CAM_TOP (the wall's top is at 22 m).
CAM_PAD, CAM_LOW, CAM_TOP = 0.5, 0.15, 21.0


def view_target(v):
    """What a view aims at: its target, else the middle of the box of what it fits (on the
    centerline when that is the whole car)."""
    if v.get("target") is not None:
        return V3(v["target"])
    pts = car_points(v.get("fit"))
    mid = V3([(min(p[i] for p in pts) + max(p[i] for p in pts)) / 2 for i in range(3)])
    if not v.get("fit"):
        mid.y = 0.0
    return mid


def in_studio(p, no_floor=False):
    """Whether a camera at p stands inside the cove, CAM_PAD clear of its floor and wall
    (no_floor: a view that hides the studio and may go under the floor)."""
    r = hypot(p[0], p[1]) + CAM_PAD
    if abs(p[2]) > CAM_TOP or r >= STUDIO_R + COVE_R:
        return False
    if no_floor:
        return True
    floor = 0.0 if r <= STUDIO_R else COVE_R - (COVE_R ** 2 - (r - STUDIO_R) ** 2) ** 0.5
    return p[2] >= floor + (CAM_PAD if r > STUDIO_R else CAM_LOW)


def _reach(tgt, d, v):
    """How far from tgt along d a camera can go and still stand inside the studio."""
    nf = bool(v.get("no_floor"))
    t = 0.5
    while t < 80.0 and in_studio(tgt + d * (t + 0.25), nf):
        t += 0.25
    return t


def _fit(tgt, d, quat, v):
    """The distance from tgt along d at which a fitted view's silhouette fills its frame."""
    rm = quat.to_matrix()
    right, up = rm.col[0], rm.col[1]
    rx, ry = SCN.render.resolution_x, SCN.render.resolution_y
    ax, ay = (1.0, rx / ry) if rx >= ry else (ry / rx, 1.0)
    k = max(0.05, 1 - 2 * v.get('margin', 0.05))
    rel = [(max(abs(q.dot(right)) * ax, abs(q.dot(up)) * ay), q.dot(d))
           for q in (p - tgt for p in car_points(v.get("fit")))]
    half = 18.0 / v["lens"] * k
    return max(max(e / half + c for e, c in rel), max(c for _, c in rel) + 0.2)


def _centered(tgt, d, quat, v):
    """tgt moved in the view's plane until the silhouette is as far from the frame's left
    edge as from its right, and from its top as from its bottom (center=True on a view)."""
    rm = quat.to_matrix()
    right, up = rm.col[0], rm.col[1]
    pts = car_points(v.get("fit"))
    for _ in range(4):
        t = _fit(tgt, d, quat, v)
        sx = [(q - tgt).dot(right) / (t - (q - tgt).dot(d)) for q in pts]
        sy = [(q - tgt).dot(up) / (t - (q - tgt).dot(d)) for q in pts]
        tgt = tgt + right * ((min(sx) + max(sx)) / 2 * t) + up * ((min(sy) + max(sy)) / 2 * t)
    return tgt


def add_camera(name, v):
    """A camera for the view at the scene's current resolution (set that first). A fitted
    view stands where the car's silhouette (car_points) just fills the frame less its
    margin; no camera leaves the studio: one that would is held at its edge, and a fitted
    view then takes the shorter lens that still shows the whole car."""
    cd = bpy.data.cameras.new(name)
    cd.lens = v["lens"]
    cd.sensor_width = 36
    cd.clip_start, cd.clip_end = 0.1, 200
    ob = bpy.data.objects.new("cam." + name, cd)
    STUDIO.objects.link(ob)
    d = V3(v["dir"]).normalized()
    quat = d.to_track_quat('Z', 'Y')
    ob.rotation_euler = quat.to_euler()
    tgt = view_target(v)
    if v.get("focus"):
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = v.get("fstop", 4.0)
        FOCUS[ob.name] = V3(v["focus"])
    if v.get("center") and not v.get("dist"):
        tgt = _centered(tgt, d, quat, v)
    if v.get("ortho"):
        rm = quat.to_matrix()
        rx, ry = SCN.render.resolution_x, SCN.render.resolution_y
        k = max(0.05, 1 - 2 * v.get('margin', 0.05))
        qs = [q - tgt for q in car_points(v.get("fit"))]
        ex = max(abs(q.dot(rm.col[0])) for q in qs)
        ey = max(abs(q.dot(rm.col[1])) for q in qs)
        cd.type = 'ORTHO'
        cd.ortho_scale = 2 * max(ex, ey * rx / ry) / k if rx >= ry else \
            2 * max(ey, ex * ry / rx) / k
        ob.location = tgt + d * min(_reach(tgt, d, v), 14.0)
        return ob
    far = _reach(tgt, d, v)
    if v.get("dist"):
        if v["dist"] > far:
            log("view %s: its camera is held inside the studio, %.1f m away, not %.1f"
                % (name, far, v["dist"]))
        ob.location = tgt + d * min(v["dist"], far)
        return ob
    # the frame's half width and height at distance 1 are 18 / lens along its longer side
    # (sensor fit AUTO) and that times the aspect along the other
    rm = quat.to_matrix()
    right, up = rm.col[0], rm.col[1]
    rx, ry = SCN.render.resolution_x, SCN.render.resolution_y
    ax, ay = (1.0, rx / ry) if rx >= ry else (ry / rx, 1.0)
    k = max(0.05, 1 - 2 * v.get('margin', 0.05))
    rel = [(max(abs(q.dot(right)) * ax, abs(q.dot(up)) * ay), q.dot(d))
           for q in (p - tgt for p in car_points(v.get("fit")))]
    half = 18.0 / v["lens"] * k
    t = max(max(e / half + c for e, c in rel), max(c for _, c in rel) + 0.2)
    if t > far:
        t = max(far, max(c for _, c in rel) + 0.2)
        cd.lens = 18.0 * k / max(e / (t - c) for e, c in rel)
        log("view %s: its camera is held inside the studio, %.1f m away, with a %.0f mm lens "
            "(not %.0f)" % (name, t, cd.lens, v["lens"]))
    ob.location = tgt + d * t
    return ob


def setup_render():
    r = SCN.render
    r.engine = 'CYCLES'
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'METAL'
        prefs.get_devices()
        for dv in prefs.devices:
            dv.use = True
        SCN.cycles.device = 'GPU'
    except Exception as e:
        print("GPU setup failed:", e)
    SCN.cycles.use_adaptive_sampling = True
    SCN.cycles.use_denoising = True
    r.use_persistent_data = True        # several views of one scene: keep it loaded
    r.resolution_percentage = 100
    r.image_settings.file_format = 'JPEG'
    r.image_settings.quality = 93
    try:
        SCN.view_settings.view_transform = 'AgX'
        SCN.view_settings.look = 'AgX - Medium High Contrast'
    except Exception as e:
        print("view transform:", e)


def render_view(name, path, res, samples, margin=None):
    """One view to a file at res = (w, h), the camera fitted to that shape."""
    SCN.render.resolution_x, SCN.render.resolution_y = res
    SCN.cycles.samples = samples
    v = VIEWS[name]
    for fn in VIEW_HOOKS:
        fn(name, True)
    if LOOK[0] == "zebra":
        _zebra_axis(v)
    cam = add_camera(name, v if margin is None else dict({"margin": margin}, **v))
    SCN.camera = cam
    if cam.name in FOCUS:
        cam.data.dof.focus_distance = (FOCUS[cam.name] - cam.location).length
    SCN.render.filepath = path
    cyc = STUDIO.objects.get("cyc") if v.get("no_floor") else None
    if cyc is not None:
        cyc.hide_render = True
    bpy.ops.render.render(write_still=True)
    if cyc is not None:
        cyc.hide_render = False
    for fn in VIEW_HOOKS:
        fn(name, False)
    log("rendered %s %d x %d, %d samples" % (name, res[0], res[1], samples))


# ---------------------------------------------------------------------------------------
# looks for judging the form: clay and zebra stripes
# ---------------------------------------------------------------------------------------
LOOK = [None]               # the look the car wears now: None, "clay" or "zebra"
ZEBRA_PAIRS = 60            # black and white pairs round the turn (6 degrees a pair)
_WORN = {}
_LINKS = {}


def clay_material():
    """One matte clay for every part: the form with no paint, glass or light to flatter it."""
    m = bpy.data.materials.get("look.clay")
    if m is None:
        m, b = new_mat("look.clay")
        b.inputs["Base Color"].default_value = (0.30, 0.265, 0.235, 1.0)
        b.inputs["Roughness"].default_value = 0.5
        b.inputs["Specular IOR Level"].default_value = 0.35
    return m


def zebra_material():
    """Zebra stripes: every point shows black or white by the direction its mirror image
    of the view comes from, as if the car stood in a tunnel of light tubes running along
    it. Stripes flow smoothly over a fair surface, kink at a crease, and wobble, pinch or
    break where the surface is not fair. The tubes run along x, or along y for views that
    look along the car (front, back)."""
    m = bpy.data.materials.get("look.zebra")
    if m is not None:
        return m
    m = bpy.data.materials.new("look.zebra")
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs["Reflection"], sep.inputs[0])
    ax = nt.nodes.new('ShaderNodeValue')            # 0: tubes along x, 1: along y
    ax.name = "axis"
    mixu = nt.nodes.new('ShaderNodeMix')            # the coordinate across the tubes
    mixu.data_type = 'FLOAT'
    nt.links.new(ax.outputs[0], mixu.inputs[0])
    nt.links.new(sep.outputs["Y"], mixu.inputs[2])
    nt.links.new(sep.outputs["X"], mixu.inputs[3])
    at = nt.nodes.new('ShaderNodeMath')
    at.operation = 'ARCTAN2'
    nt.links.new(sep.outputs["Z"], at.inputs[0])
    nt.links.new(mixu.outputs[0], at.inputs[1])
    mul = nt.nodes.new('ShaderNodeMath')
    mul.operation = 'MULTIPLY'
    mul.inputs[1].default_value = ZEBRA_PAIRS / (2 * pi)
    nt.links.new(at.outputs[0], mul.inputs[0])
    fr = nt.nodes.new('ShaderNodeMath')
    fr.operation = 'FRACT'
    nt.links.new(mul.outputs[0], fr.inputs[0])
    gt = nt.nodes.new('ShaderNodeMath')
    gt.operation = 'GREATER_THAN'
    gt.inputs[1].default_value = 0.5
    nt.links.new(fr.outputs[0], gt.inputs[0])
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.inputs[6].default_value = (0.012, 0.012, 0.014, 1.0)
    mix.inputs[7].default_value = (0.92, 0.92, 0.90, 1.0)
    nt.links.new(gt.outputs[0], mix.inputs[0])
    em = nt.nodes.new('ShaderNodeEmission')
    nt.links.new(mix.outputs[2], em.inputs["Color"])
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(em.outputs[0], out.inputs[0])
    return m


def _zebra_axis(v):
    d = V3(v["dir"]).normalized()
    m = bpy.data.materials.get("look.zebra")
    if m is not None:
        m.node_tree.nodes["axis"].outputs[0].default_value = 1.0 if abs(d.x) > 0.93 else 0.0


def wear(look):
    """Dresses every part of the car in a look ("clay", "zebra") or, with None, in its own
    materials again."""
    for data, (mats, added) in _WORN.items():
        if added:
            data.materials.clear()
        for i, m in enumerate(mats):
            data.materials[i] = m
    _WORN.clear()
    for ob, rec in _LINKS.items():
        ob.light_linking.receiver_collection = rec
    _LINKS.clear()
    LOOK[0] = look
    if look is None:
        return
    # every light on every part: a canopy the car keeps the top box off would be dark clay
    for ob in STUDIO.objects:
        if ob.type == 'LIGHT' and ob.light_linking.receiver_collection is not None:
            _LINKS[ob] = ob.light_linking.receiver_collection
            ob.light_linking.receiver_collection = None
    m = clay_material() if look == "clay" else zebra_material()
    for ob in CAR.objects:
        mats = getattr(ob.data, "materials", None)
        if mats is None or ob.data in _WORN:
            continue
        _WORN[ob.data] = (list(mats), not len(mats))
        if not len(mats):
            mats.append(m)
        for i in range(len(mats)):
            mats[i] = m


def render_turntable(n=12, samples=24, size=(640, 360), name="turntable"):
    """<name>.jpg: n views round the car from the hero's height, all at one distance, in
    rows of four (and <name>.gif, the same frames in turn). The first looks at the nose,
    the next ones walk round by the car's left."""
    hero = V3(VIEWS["hero"]["dir"]).normalized()
    el = atan2(hero.z, hypot(hero.x, hero.y))
    SCN.render.resolution_x, SCN.render.resolution_y = size
    dirs = [(cos(2 * pi * k / n) * cos(el), sin(2 * pi * k / n) * cos(el), sin(el))
            for k in range(n)]
    base = dict(lens=70, margin=0.06)
    tgt = view_target(base)
    dist = max(_fit(tgt, V3(d), V3(d).to_track_quat('Z', 'Y'), base) for d in dirs)
    tmp = os.path.join(ARGS.out, ".tiles")
    os.makedirs(tmp, exist_ok=True)
    files = []
    for k, d in enumerate(dirs):
        VIEWS["_turn"] = dict(dir=d, lens=70, dist=dist, target=tuple(tgt))
        files.append(os.path.join(tmp, "t_%02d.jpg" % k))
        render_view("_turn", files[-1], size, samples)
    del VIEWS["_turn"]
    rows = [files[i:i + 4] for i in range(0, n, 4)]
    py = _python()
    if compose(os.path.join(ARGS.out, name + ".jpg"), rows) and py:
        subprocess.run([py, os.path.join(HERE, "post.py"), "gif",
                        os.path.join(ARGS.out, name + ".gif")] + files, check=True)
        shutil.rmtree(tmp, ignore_errors=True)


def tri_count():
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    n = 0
    for ob in CAR.objects:
        me = ob.evaluated_get(dg).to_mesh()
        n += sum(len(p.vertices) - 2 for p in me.polygons)
        ob.evaluated_get(dg).to_mesh_clear()
    return n


def car_size():
    """The car's box, (lo, hi), from its objects' bounding boxes."""
    bpy.context.view_layer.update()
    pts = [ob.matrix_world @ V3(c) for ob in CAR.objects for c in ob.bound_box]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return lo, hi


def stats():
    """Prints the car's size, triangles and objects, and anything under the floor."""
    lo, hi = car_size()
    for ob in CAR.objects:
        z = min((ob.matrix_world @ V3(c)).z for c in ob.bound_box)
        if z < -0.01:
            print("UNDER THE FLOOR: %s reaches z = %.3f" % (ob.name, z))
    log("CAR size %.3f x %.3f x %.3f m, triangles %d, objects %d" % (
        hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], tri_count(), len(CAR.objects)))
    if abs(lo[2]) > 0.01:
        log("CAR lowest point at z = %.3f, top at z = %.3f over the ground" % (lo[2], hi[2]))


def _python():
    """A Python with PIL and numpy, for post.py: $CYBERGEN_PYTHON, else the repo's venv."""
    cands = [os.environ.get("CYBERGEN_PYTHON")]
    d = HERE
    for _ in range(8):
        d = os.path.dirname(d)
        cands += [os.path.join(d, ".venv", "bin", "python"),
                  os.path.join(d, ".venv", "Scripts", "python.exe")]
    cands.append("/Users/swag/Projects/CyberGen/.venv/bin/python")
    return next((c for c in cands if c and os.path.exists(c)), None)


def compose(dst, rows, bloom=None, inset=None):
    """post.py puts the tiles (rows of files) together into dst; inset=(file, corner) lays
    a small tile into a corner ("tl", "tr", "bl", "br") of the first tile (a list of such
    pairs lays several)."""
    py = _python()
    cmd = [py or "python", os.path.join(HERE, "post.py"), "compose", dst]
    if bloom:
        cmd += ["--bloom", str(bloom[0]), str(bloom[1])]
    for one in ([inset] if inset and isinstance(inset[0], str) else inset or []):
        cmd += ["--inset", one[0], one[1]]
    for row in rows:
        cmd += ["--row"] + row
    if py is None:
        print("NO PYTHON WITH PIL FOUND (set CYBERGEN_PYTHON); the tiles are kept. Run:\n  "
              + " ".join(cmd))
        return False
    subprocess.run(cmd, check=True)
    log("wrote " + dst)
    return True


SHEET_W, SHEET_TOP, SHEET_ROW, SHEET_GAP = 3840, 1536, 620, 4


SHEET_EXTRA = dict(size=(840, 400), corner="tl", margin=0.06)


def render_sheet(views=("hero", "front", "side", "back"), samples=160, extra=None):
    """sheet.jpg: the first view on top, three below, each rendered at its tile's size.
    extra: a fifth view of the car's choice ("top", "under", one of its own), a view name
    or dict(view=, size=(w, h), corner="tl"|"tr"|"bl"|"br", margin=), laid as a small tile
    into a corner of the first, over it (SHEET_EXTRA's defaults: top left, the empty wall
    over the nose of a hero seen from the front left; pick the corner your hero leaves
    free). A list of them lays several, each in its own corner (top left, then top right,
    bottom right, bottom left when not said)."""
    lo, hi = car_size()
    L, W = hi[0] - lo[0], hi[1] - lo[1]
    room = SHEET_W - 2 * SHEET_GAP
    wf = int(min(max(room * W / (2 * W + L), 560), 1150)) // 2 * 2    # one scale for all three
    sizes = [(SHEET_W, SHEET_TOP), (wf, SHEET_ROW), (room - 2 * wf, SHEET_ROW), (wf, SHEET_ROW)]
    tmp = os.path.join(ARGS.out, ".tiles")
    os.makedirs(tmp, exist_ok=True)
    files = []
    for name, size in zip(views, sizes):
        files.append(os.path.join(tmp, "%s.jpg" % name))
        render_view(name, files[-1], size, samples, 0.025 if not files[1:] else 0.04)
    inset = None
    if extra and isinstance(extra, (list, tuple)):
        inset = []
        for k, one in enumerate(extra):
            e = dict(SHEET_EXTRA, corner=("tl", "tr", "br", "bl")[k % 4],
                     **({} if isinstance(one, dict) else {"view": one}))
            e.update(one if isinstance(one, dict) else {})
            inset.append((os.path.join(tmp, "x%d_%s.jpg" % (k, e["view"])), e["corner"]))
            render_view(e["view"], inset[-1][0], tuple(e["size"]), samples, e["margin"])
    elif extra:
        e = dict(SHEET_EXTRA, **(extra if isinstance(extra, dict) else {"view": extra}))
        inset = (os.path.join(tmp, "x_%s.jpg" % e["view"]), e["corner"])
        render_view(e["view"], inset[0], tuple(e["size"]), samples, e["margin"])
    bloom = (0.9, 0.8) if ARGS.night else (0.45, 0.86)
    if compose(os.path.join(ARGS.out, "sheet.jpg"), [files[:1], files[1:]], bloom, inset):
        shutil.rmtree(tmp, ignore_errors=True)


def render_preview(views=("hero", "rear", "side", "top"), samples=24, name="preview"):
    """preview.jpg: four small views in a 2 x 2 grid, 1920 wide, for design iteration
    (clay.jpg and zebra.jpg are the same grid in those looks)."""
    tmp = os.path.join(ARGS.out, ".tiles")
    os.makedirs(tmp, exist_ok=True)
    files = []
    for view in views:
        files.append(os.path.join(tmp, "p_%s.jpg" % view))
        render_view(view, files[-1], (958, 538), samples)
    if compose(os.path.join(ARGS.out, name + ".jpg"), [files[:2], files[2:]]):
        shutil.rmtree(tmp, ignore_errors=True)


def export_glb(path):
    # glTF carries no node graphs: every material goes out with its flat values
    for m in MAT.values():
        nt = m.node_tree
        b = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
        for name in ("Base Color", "Metallic", "Roughness", "Normal", "Emission Strength"):
            for l in list(b.inputs[name].links):
                nt.links.remove(l)
    root = bpy.data.objects.new("car", None)
    CAR.objects.link(root)
    for ob in CAR.objects:
        if ob is not root:
            ob.parent = root
    for ob in bpy.data.objects:
        ob.select_set(ob.name in CAR.objects)
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True,
                              export_apply=True)


def shoot(sheet=("hero", "front", "side", "back"), preview=("hero", "rear", "side", "top"),
          extra=None):
    """The end of every car script: stats, studio, then what the arguments ask for:
    --preview (preview.jpg), --sheet (sheet.jpg), --views (car_<view>.jpg at --res),
    --blend (car.blend), --glb (car.glb), --clay and --zebra (clay.jpg, zebra.jpg: the
    preview's views in those looks), --turntable (turntable.jpg), --check (the checks).
    With none of them it only builds and counts. extra: the sheet's optional small tiles,
    as render_sheet()'s."""
    stats()
    build_studio()
    setup_render()
    os.makedirs(ARGS.out, exist_ok=True)
    views = [v for v in ARGS.views.split(",") if v]
    looks = [k for k in ("clay", "zebra") if getattr(ARGS, k)]
    if ARGS.check:
        check()
    if ARGS.preview:
        render_preview(preview, ARGS.samples or 24)
    if ARGS.sheet:
        render_sheet(sheet, ARGS.samples or 160, ARGS.extra or extra)
    night = "_night" if ARGS.night else ""
    for look in looks or [None]:
        # with a look, --views and --turntable are rendered in it (and not in the paint)
        wear(look)
        tag = "_" + look if look else ""
        few = ARGS.samples or (16 if look == "zebra" else 24)
        if look:
            render_preview(preview, few, look)
        for name in views:
            render_view(name, os.path.join(ARGS.out, "car_%s%s%s.jpg" % (name, tag, night)),
                        ARGS.res, ARGS.samples or (few if look else 64))
        if ARGS.turntable:
            render_turntable(ARGS.turntable, few, name="turntable" + tag)
    wear(None)
    if ARGS.blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ARGS.out, "car.blend"))
    if ARGS.glb:
        export_glb(os.path.join(ARGS.out, "car.glb"))
    if not (ARGS.preview or ARGS.sheet or views or ARGS.blend or ARGS.glb or looks
            or ARGS.turntable or ARGS.check):
        print("built only: pass --preview, --sheet or --views NAME,... to render")
    log("done, output in " + ARGS.out)


MEANT = {}          # check name -> name patterns a car says are meant (meant())


def meant(check, *names):
    """Tells the checks that a finding is meant: check is "tires" (wheel tags), "ground",
    "symmetry", "through" (object names) or "panels" (panel objects such as "body.roof");
    names may end in * . The finding is still listed, marked meant, and no longer counts
    in the verdict: a taxi's open doorway, a mast on one side, a driver's wheel."""
    MEANT.setdefault(check, []).extend(names)


def check(write=True):
    """The kit's checks on the car as built (carcheck.py): tire and ground clearances,
    symmetry, open edges and holes in the panels, parts through the skin, triangles. Prints
    a table and, with write, check.json in the output folder; returns the findings."""
    import carcheck
    return carcheck.run(sys.modules[__name__], write)
