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
from math import atan2, cos, hypot, pi, sin
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
# paint finishes: (metallic, roughness, clear coat)
FINISH = {"metallic": (0.85, 0.34, 1.0), "pearl": (0.45, 0.30, 1.0), "gloss": (0.0, 0.28, 1.0),
          "satin": (0.6, 0.48, 0.3), "matte": (0.15, 0.7, 0.0), "chrome": (1.0, 0.12, 1.0)}
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
    metallic, rough, coat = FINISH[finish] if isinstance(finish, str) else finish
    m, b = pbr(name, color, metallic, rough, **{"Coat Weight": coat, "Coat Roughness": 0.06})
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


def carbon(name="carbon", dark=(0.012, 0.012, 0.014), light=(0.045, 0.046, 0.05)):
    """Twill weave: fine diagonal bands in color and roughness under a clear coat."""
    mid = tuple((a + c) / 2 * 0.72 for a, c in zip(dark, light))
    m, b = pbr(name, mid, 0.6, 0.34, **{"Coat Weight": 1.0, "Coat Roughness": 0.08})
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
    carbon()
    pbr("underbody", (0.02, 0.02, 0.02), 0.0, 0.85)
    void()
    pbr("well", (0.010, 0.010, 0.010), 0.0, 0.9, **{"Specular IOR Level": 0.1})
    pbr("grille", (0.03, 0.03, 0.032), 0.8, 0.38)
    pbr("glass", p["glass"], 0.0, 0.0, **{"Transmission Weight": 1.0, "IOR": 1.5})
    pbr("rubber", (0.014, 0.014, 0.015), 0.0, 0.72)
    pbr("rim", p["rim"], 1.0, 0.30)
    pbr("rim_bright", p["rim_bright"], 1.0, 0.22)
    pbr("disc", (0.30, 0.30, 0.31), 1.0, 0.38)
    pbr("caliper", p["caliper"], 0.0, 0.32, **{"Coat Weight": 1.0})
    pbr("interior", p["interior"], 0.0, 0.6)
    pbr("seat", p["seat"], 0.0, 0.5)
    emit("led_front", p["led_front"], 60.0)
    emit("led_rear", p["led_rear"], 40.0)
    emit("led_accent", p["led_accent"], 30.0)
    emit("led_wheel", p["led_wheel"] or p["led_front"], 30.0)
    emit("screen", p["screen"], 2.0)
    pbr("decal", p["decal"], 0.0, 0.5)
    emit("lamp", (0.85, 0.95, 1.0), 25.0)
    emit("ember", p["ember"], 1.6)
    pbr("floor", (0.11, 0.11, 0.12), 0.0, 0.30)
    return MAT


# ---------------------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------------------
def my(p):
    """p mirrored to the right side."""
    return V3((p[0], -p[1], p[2]))


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

    def lathe(self, prof, n, a0=0.0, a1=2 * pi, xf=None, closed=True):
        """prof: (axial y, radius) points, turned about the y axis in n steps."""
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

    def honeycomb(self, poly, x, R, wall, depth, sgn, keep=None):
        """Hexagonal mesh over a (y, z) polygon on the plane x, standing sgn * depth off it."""
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
                self.lathe(prof, 6, xf=Matrix.Translation((x + (0 if sgn < 0 else depth), y, z)) @ rot)

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
        me.materials.append(MAT[mat])
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
               project=True, bevel=None, bevel_segs=2):
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
                    going in, and the inner face depth behind the center.
    recesses        (i, j, thickness, depth[, inner panel, wall panel]): quad (i, j) inset
                    and sunk on both sides (vents; "vent" by default).
    glass           (panel, inset[, trim panel]): a trim frame round the panel's faces with
                    sharp corners ("trim" by default).
    cutters         (Geo, panel) solids cut out of the hull, the cut faces becoming that
                    panel, which is kept as it is (no gap, rim or bevel): wheel wells.
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
        for v in ring:
            L = hypot(center.y - v.co.y, center.z - v.co.z)
            r1.append(bm.verts.new(band_point(v.co, center, band, sgn * lip)))
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
    raw = set()
    for _, pn in cutters:
        pidx(pn)
        raw.add(pn)

    me = bpy.data.meshes.new(name + ".hull")
    bm.to_mesh(me)
    bm.free()
    pm, back = {}, {}
    for pn in panels:
        pm[pn] = bpy.data.materials.new("P_" + pn)
        back[pm[pn].name] = pn
        me.materials.append(pm[pn])
    hull = bpy.data.objects.new(name + ".hull", me)
    CAR.objects.link(hull)
    md = hull.modifiers.new("subd", 'SUBSURF')
    md.levels = subdiv
    md.render_levels = subdiv
    md.subdivision_type = 'CATMULL_CLARK'
    cuts = []
    for k, (g, pn) in enumerate(cutters):
        cme = g.mesh("cut")
        cme.materials.append(pm[pn])
        cut = bpy.data.objects.new("cut", cme)
        CAR.objects.link(cut)
        cuts.append(cut)
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
    for idx, pn in enumerate(names):
        pb = bmesh.new()
        pb.from_mesh(out)
        dele = [f for f in pb.faces if f.material_index != idx]
        if len(dele) == len(pb.faces):
            pb.free()
            continue
        bmesh.ops.delete(pb, geom=dele, context='FACES')
        for f in pb.faces:
            f.material_index = 0
        mat = pmat[pn]
        if pn not in raw and gap:
            shrink(pb, gap)
        pme = bpy.data.meshes.new(name + "." + pn)
        pb.to_mesh(pme)
        pb.free()
        pme.materials.append(MAT[mat])
        ob = bpy.data.objects.new(name + "." + pn, pme)
        CAR.objects.link(ob)
        res.parts[pn] = ob
        if pn in raw:
            continue
        if project:
            BODY.append(ob)
        md = ob.modifiers.new("solid", 'SOLIDIFY')
        md.offset = -1.0
        if mat.startswith("glass"):
            md.thickness = glass_thick
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


def arch_bolts(g, cx, cz, r, y, angles, inset=0.005, width=0.04, at=(0.25, 0.75)):
    """Bolt heads on the outer face of an arch_trim, on the middle of each facet."""
    mid = r + (width - inset) / 2
    for k in range(len(angles) - 1):
        da = angles[k + 1] - angles[k]
        for t in at:
            a = rad(angles[k] + da * t)
            rr = mid * cos(rad(da / 2)) / cos(rad(da * (t - 0.5)))
            g.lathe([(-0.002, 0.0015), (-0.002, 0.0065), (0.0035, 0.0065), (0.0035, 0.0015)],
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
    objs = [objs] if isinstance(objs, bpy.types.Object) else list(objs)
    key = tuple(ob.name for ob in objs)
    if key not in _TREES:
        _TREES[key] = body_bvh(objs, default=False)
    return _TREES[key]


# projection -> (the ray's axis, the axes of u and v), where it starts, its direction
_RAYS = {'y': ((1, 0, 2), 30.0, (0, -1, 0)), 'Y': ((1, 0, 2), -30.0, (0, 1, 0)),
         'x': ((0, 1, 2), 30.0, (-1, 0, 0)), 'X': ((0, 1, 2), -30.0, (1, 0, 0)),
         'z': ((2, 0, 1), 30.0, (0, 0, -1))}


def on_body(u, v, proj, objs=None):
    """The body's surface point and normal under (u, v), or (None, None): proj 'y' (x, z)
    seen from the left, 'Y' from the right, 'x' (y, z) from the front, 'X' from the back,
    'z' (x, y) from above. objs: an object or a list of objects to project on instead of
    the body pieces (as they are at the first call with that list)."""
    tree = _tree(objs)
    (axis, a, b), far, d = _RAYS[proj]
    o = V3()
    o[axis], o[a], o[b] = far, u, v
    d = V3(d)
    loc, n, _, _ = tree.ray_cast(o, d)
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


def stud(g, loc, n, prof, seg):
    """A lathe profile standing on the surface point loc along its normal n."""
    xf = Matrix.Translation(loc) @ V3((0, 1, 0)).rotation_difference(n).to_matrix().to_4x4()
    g.lathe(prof, seg, xf=xf)


_FONT = [None]
FONTS = ("/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf",
         "C:/Windows/Fonts/bahnschrift.ttf")


def text_mesh(txt, size, spacing=1.0):
    """Flat outline text as (verts, faces), centered on its origin."""
    cu = bpy.data.curves.new("txt", 'FONT')
    cu.body = txt
    cu.size = size
    cu.space_character = spacing
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    if _FONT[0] is None:
        _FONT[0] = False
        for p in FONTS:
            if os.path.exists(p):
                _FONT[0] = bpy.data.fonts.load(p)
                break
    if _FONT[0]:
        cu.font = _FONT[0]
    ob = bpy.data.objects.new("txt", cu)
    SCN.collection.objects.link(ob)
    me = evaluated_mesh(ob)
    vs = [v.co.copy() for v in me.vertices]
    fs = [tuple(p.vertices) for p in me.polygons]
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return vs, fs


def text_on_body(g, txt, size, x0, z0, side, lift=0.0012, spacing=1.0, proj=None, turn=0.0,
                 objs=None):
    """Text on the body's flank, reading left to right for someone looking at that side
    (side 1 left, -1 right), its middle at (x0, z0).

    proj='z' lays it on a roof, hood or deck instead, seen from above: its middle at
    x = x0, y = z0, reading left to right for someone standing at the car's left (side 1)
    or right (side -1); turn (degrees, counterclockwise seen from above) turns it from
    there (side 1, turn 90: read from behind the car). objs as on_body()'s. Nothing is
    added when any of its points misses the surface."""
    vs, fs = text_mesh(txt, size, spacing)
    out = []
    if proj == 'z':
        c, s = cos(rad(turn)), sin(rad(turn))
        rx, ry = -side * c, -side * s               # along the text
        ux, uy = side * s, -side * c                # up its letters
    for p in vs:
        if proj == 'z':
            loc, n = on_body(x0 + rx * p.x + ux * p.y, z0 + ry * p.x + uy * p.y, 'z', objs)
        else:
            loc, n = on_body(x0 - side * p.x, z0 + p.y, 'y' if side > 0 else 'Y', objs)
        if loc is None:
            return
        out.append(loc + n * lift)
    g.add(out, fs)


def text_flat(g, txt, size, origin, right, up, spacing=1.0):
    """Text on a plane: its middle at origin, reading along right."""
    vs, fs = text_mesh(txt, size, spacing)
    o, r, u = V3(origin), V3(right), V3(up)
    g.add([o + r * p.x + u * p.y for p in vs], fs)


# ---------------------------------------------------------------------------------------
# wheels
# ---------------------------------------------------------------------------------------
def build_wheel(tag, cx, R, w, Rr, out_y, side, cz=None, spokes=7, style="twin",
                ring="led_wheel", caliper="caliper", rim="rim", bright="rim_bright",
                tire="rubber", loc=None, rot=None):
    """A wheel on its axle, as objects tire.<tag>, rim.<tag>, hub.<tag>, ring.<tag>,
    disc.<tag>, caliper.<tag>, drum.<tag>, all at the wheel's middle (they can turn).

    cx axle x, R tire radius, w tire width, Rr rim radius, out_y the tire's outer face,
    side 1 left or -1 right, cz axle height (R: standing on the ground). spokes and style
    ("twin" pairs of blades, "blade" single swept blades, "disc" a closed dish). ring,
    caliper: material names, None for no light ring, no brake. tire=None leaves the tire
    out and rim=None the rim and its hub (bright=None the hub alone), for a car that brings
    its own under the same names. loc puts the wheel's middle somewhere else and rot (an
    Euler, three angles or a matrix) turns it there: a spare. Nothing here needs a wheel
    well: an exposed wheel is the same call.
    """
    hw = w / 2
    flip = side < 0
    loc = (cx, side * (out_y - hw), R if cz is None else cz) if loc is None else tuple(loc)
    N = 144
    if tire:
        _tire(tag, R, w, Rr, N, tire, flip, loc, rot)
    if rim:
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


def _tire(tag, R, w, Rr, N, tire, flip, loc, rot):
    """The tire: grooves, tread blocks, sidewall lettering."""
    hw = w / 2
    g = Geo()
    grooves = [-w * 0.24, 0.0, w * 0.24]

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
        prof += [(c - 0.012, R), (c - 0.007, R - 0.009), (c + 0.007, R - 0.009), (c + 0.012, R)]
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
        if (k + 2 * land) % 4 == 0:
            sel.append(f)
    bmesh.ops.inset_individual(bm, faces=sel, thickness=0.002, depth=-0.007)
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
        # Metal on the Mac; OptiX, else CUDA, else HIP on a Windows or Linux PC (the first
        # backend this Blender offers with a GPU on it)
        kinds = [k.identifier for k in prefs.bl_rna.properties['compute_device_type'].enum_items]
        for kind in ('METAL', 'OPTIX', 'CUDA', 'HIP', 'ONEAPI'):
            if kind not in kinds:
                continue
            prefs.compute_device_type = kind
            prefs.get_devices()
            if any(dv.type != 'CPU' for dv in prefs.devices):
                break
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
    log("rendered %s %d x %d, %d samples" % (name, res[0], res[1], samples))


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
    a small tile into a corner ("tl", "tr", "bl", "br") of the first tile."""
    py = _python()
    cmd = [py or "python", os.path.join(HERE, "post.py"), "compose", dst]
    if bloom:
        cmd += ["--bloom", str(bloom[0]), str(bloom[1])]
    if inset:
        cmd += ["--inset", inset[0], inset[1]]
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
    free)."""
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
    if extra:
        e = dict(SHEET_EXTRA, **(extra if isinstance(extra, dict) else {"view": extra}))
        inset = (os.path.join(tmp, "x_%s.jpg" % e["view"]), e["corner"])
        render_view(e["view"], inset[0], tuple(e["size"]), samples, e["margin"])
    bloom = (0.9, 0.8) if ARGS.night else (0.45, 0.86)
    if compose(os.path.join(ARGS.out, "sheet.jpg"), [files[:1], files[1:]], bloom, inset):
        shutil.rmtree(tmp, ignore_errors=True)


def render_preview(views=("hero", "rear", "side", "top"), samples=24):
    """preview.jpg: four small views in a 2 x 2 grid, 1920 wide, for design iteration."""
    tmp = os.path.join(ARGS.out, ".tiles")
    os.makedirs(tmp, exist_ok=True)
    files = []
    for name in views:
        files.append(os.path.join(tmp, "p_%s.jpg" % name))
        render_view(name, files[-1], (958, 538), samples)
    if compose(os.path.join(ARGS.out, "preview.jpg"), [files[:2], files[2:]]):
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
    --blend (car.blend), --glb (car.glb). With none of them it only builds and counts.
    extra: the sheet's optional fifth tile, as render_sheet()'s."""
    stats()
    build_studio()
    setup_render()
    os.makedirs(ARGS.out, exist_ok=True)
    views = [v for v in ARGS.views.split(",") if v]
    if ARGS.preview:
        render_preview(preview, ARGS.samples or 24)
    if ARGS.sheet:
        render_sheet(sheet, ARGS.samples or 160, ARGS.extra or extra)
    for name in views:
        render_view(name, os.path.join(ARGS.out, "car_%s%s.jpg" % (
            name, "_night" if ARGS.night else "")), ARGS.res, ARGS.samples or 64)
    if ARGS.blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ARGS.out, "car.blend"))
    if ARGS.glb:
        export_glb(os.path.join(ARGS.out, "car.glb"))
    if not (ARGS.preview or ARGS.sheet or views or ARGS.blend or ARGS.glb):
        print("built only: pass --preview, --sheet or --views NAME,... to render")
    log("done, output in " + ARGS.out)
