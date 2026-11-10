"""One hero car, modelled procedurally in Blender (an experiment, not a generator stage).

Run:
    blender -b -P build_car.py -- --out DIR [--views hero,rear,side] [--res W H]
        [--samples N] [--night] [--glb] [--blend]

Frame: x forward, y left, z up, meters, origin on the ground under the car's middle.
The body is a loft of nine character lines over twelve stations (a closed solid), cut by
the wheel wells, split into panels, each panel given a rim and bevelled, so panel gaps
are real. Everything else (wheels, lights, vents, wing, interior) is built on the same
station points, so it follows the body when a station moves.
"""
import argparse
import math
import os
import sys
from math import atan2, cos, hypot, pi, sin
from math import radians as rad

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix
from mathutils.bvhtree import BVHTree
from mathutils import Vector as V3

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
ap.add_argument("--views", default="hero,rear,side,top,front")
ap.add_argument("--res", type=int, nargs=2, default=[1600, 900])
ap.add_argument("--samples", type=int, default=64)
ap.add_argument("--night", action="store_true")
ap.add_argument("--glb", action="store_true")
ap.add_argument("--blend", action="store_true")
ARGS = ap.parse_args(argv)
ARGS.out = os.path.abspath(ARGS.out)

bpy.ops.wm.read_factory_settings(use_empty=True)
SCN = bpy.context.scene
CAR = bpy.data.collections.new("CAR")
STUDIO = bpy.data.collections.new("STUDIO")
SCN.collection.children.link(CAR)
SCN.collection.children.link(STUDIO)

# ---------------------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------------------
FA_X, RA_X = 1.40, -1.32            # axles
F_R, F_W, F_RIM = 0.35, 0.255, 0.262   # front tire radius, width, rim radius
R_R, R_W, R_RIM = 0.37, 0.325, 0.275
F_OUT, R_OUT = 0.948, 0.968         # outer face of the tires
F_ARCH, R_ARCH = 0.405, 0.428       # wheel arch radius
ARCH_ANG = (-28, 8, 42, 74, 106, 138, 172, 208)
SUBDIV = 3

# ---------------------------------------------------------------------------------------
# materials
# ---------------------------------------------------------------------------------------
MAT = {}


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
    m, b = new_mat(name)
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    for k, v in kw.items():
        b.inputs[k].default_value = v
    MAT[name] = m
    return m, b


def emit(name, color, strength):
    k = 0.25 if not ARGS.night else 0.6
    return pbr(name, (0.02, 0.02, 0.02), 0.0, 0.3,
               **{"Emission Color": (*color, 1.0), "Emission Strength": strength * k})


def make_materials():
    m, b = pbr("paint", (0.15, 0.16, 0.185), 0.85, 0.32,
               **{"Coat Weight": 1.0, "Coat Roughness": 0.06})
    nt = m.node_tree
    # fine metallic flake: a tiny noise bump under the clear coat
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs["Scale"].default_value = 2600.0
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs["Strength"].default_value = 0.06
    bp.inputs["Distance"].default_value = 0.0005
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    # road dust on the lower body: a soft gradient by height, broken by noise
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    ramp = nt.nodes.new('ShaderNodeMapRange')
    ramp.inputs["From Min"].default_value = 0.12
    ramp.inputs["From Max"].default_value = 0.55
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
    mr.inputs["To Min"].default_value = 0.34
    mr.inputs["To Max"].default_value = 0.62
    nt.links.new(mul.outputs[0], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    # dust tints the color where it lies, and grime darkens the creases
    dust = nt.nodes.new('ShaderNodeMixRGB')
    dust.inputs["Color1"].default_value = (0.15, 0.16, 0.185, 1)
    dust.inputs["Color2"].default_value = (0.20, 0.18, 0.15, 1)
    df = nt.nodes.new('ShaderNodeMath')
    df.operation = 'MULTIPLY'
    df.inputs[1].default_value = 0.7
    nt.links.new(mul.outputs[0], df.inputs[0])
    nt.links.new(df.outputs[0], dust.inputs["Fac"])
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
    nt.links.new(dust.outputs["Color"], grime.inputs["Color1"])
    nt.links.new(aor.outputs["Result"], grime.inputs["Color2"])
    nt.links.new(grime.outputs["Color"], b.inputs["Base Color"])
    met = nt.nodes.new('ShaderNodeMapRange')
    met.inputs["To Min"].default_value = 0.85
    met.inputs["To Max"].default_value = 0.25
    nt.links.new(df.outputs[0], met.inputs["Value"])
    nt.links.new(met.outputs["Result"], b.inputs["Metallic"])

    pbr("gloss_black", (0.010, 0.010, 0.012), 0.0, 0.10, **{"Coat Weight": 1.0})
    pbr("cladding", (0.028, 0.029, 0.032), 0.3, 0.48)
    m, b = pbr("carbon", (0.020, 0.021, 0.024), 0.6, 0.34, **{"Coat Weight": 1.0,
                                                           "Coat Roughness": 0.08})
    nt = m.node_tree
    # twill weave: fine diagonal bands in color, roughness and height under the coat
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
    cm.inputs["Color1"].default_value = (0.012, 0.012, 0.014, 1)
    cm.inputs["Color2"].default_value = (0.045, 0.046, 0.05, 1)
    nt.links.new(mx.outputs[0], cm.inputs["Fac"])
    nt.links.new(cm.outputs["Color"], b.inputs["Base Color"])
    pbr("underbody", (0.02, 0.02, 0.02), 0.0, 0.85)
    pbr("void", (0.004, 0.004, 0.005), 0.0, 0.8, **{"Specular IOR Level": 0.0})
    pbr("well", (0.010, 0.010, 0.010), 0.0, 0.9, **{"Specular IOR Level": 0.1})
    pbr("grille", (0.03, 0.03, 0.032), 0.8, 0.38)
    pbr("glass", (0.30, 0.33, 0.36), 0.0, 0.0,
        **{"Transmission Weight": 1.0, "IOR": 1.5})
    pbr("rubber", (0.014, 0.014, 0.015), 0.0, 0.72)
    pbr("rim", (0.075, 0.078, 0.085), 1.0, 0.30)
    pbr("rim_bright", (0.50, 0.51, 0.53), 1.0, 0.22)
    pbr("disc", (0.30, 0.30, 0.31), 1.0, 0.38)
    pbr("caliper", (0.95, 0.24, 0.02), 0.0, 0.32, **{"Coat Weight": 1.0})
    pbr("interior", (0.018, 0.018, 0.020), 0.0, 0.6)
    pbr("seat", (0.06, 0.028, 0.02), 0.0, 0.5)
    emit("led_front", (0.72, 0.93, 1.0), 60.0)
    emit("led_rear", (1.0, 0.03, 0.015), 40.0)
    emit("led_accent", (1.0, 0.30, 0.03), 30.0)
    emit("led_wheel", (0.72, 0.93, 1.0), 30.0)
    emit("screen", (0.15, 0.6, 0.8), 2.0)
    pbr("decal", (0.55, 0.56, 0.58), 0.0, 0.5)
    emit("lamp", (0.85, 0.95, 1.0), 25.0)
    emit("ember", (1.0, 0.22, 0.03), 1.6)
    pbr("floor", (0.11, 0.11, 0.12), 0.0, 0.30)


# ---------------------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------------------
def my(p):
    return V3((p[0], -p[1], p[2]))


class Geo:
    """Accumulates closed solids into one mesh."""

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
        n = len(poly)
        vec = V3(vec)
        pts = [V3(p) for p in poly] + [V3(p) + vec for p in poly]
        faces = [tuple(range(n)), tuple(range(n, 2 * n))]
        faces += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        self.add(pts, faces, xf)

    def lathe(self, prof, n, a0=0.0, a1=2 * pi, xf=None, closed=True):
        """prof: (axial y, radius) points, turned about the y axis."""
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

    def obj(self, name, mat, bevel=0.0, segs=2, angle=30.0, mirror=False, wn=True,
            sharp=None, flip_y=False, loc=None, coll=None):
        vs = [((p.x, -p.y, p.z) if flip_y else tuple(p)) for p in self.v]
        me = bpy.data.meshes.new(name)
        me.from_pydata(vs, [], self.f)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(MAT[mat])
        ob = bpy.data.objects.new(name, me)
        (coll or CAR).objects.link(ob)
        if loc is not None:
            ob.location = loc
        finish(ob, bevel, segs, angle, mirror, wn, sharp)
        return ob


def finish(ob, bevel=0.0, segs=2, angle=30.0, mirror=False, wn=True, sharp=None):
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


# ---------------------------------------------------------------------------------------
# body: stations and character lines
# ---------------------------------------------------------------------------------------
LINES = "CHGSUMRFB"
#        C centerline top, H hood crease / roof edge, G fender inner / beltline,
#        S shoulder crest, U widest line, M cladding line, R rocker, F floor edge, B floor
ORDER = ["N0", "N1", "A1", "A2", "A3", "W0", "RF", "BP", "SC", "RA", "RB", "T1"]
PT = {}


def stations():
    T = {
        "N0": [(2.30, 0, .455), (2.275, .38, .455), (2.215, .62, .455), (2.13, .80, .45),
               (2.11, .85, .37), (2.11, .86, .26), (2.14, .84, .15), (2.22, .60, .12),
               (2.27, 0, .12)],
        "N1": [(2.05, 0, .525), (2.03, .40, .54), (2.00, .66, .585), (1.98, .885, .62),
               (1.96, .94, .50), (1.96, .935, .30), (1.98, .90, .15), (2.00, .66, .12),
               (2.05, 0, .12)],
        "A1": [(1.84, 0, .58), (1.84, .44, .60), (1.84, .70, .68), (1.84, .935, .725),
               (1.84, .975, .57), (1.84, .955, .32), (1.84, .92, .15), (1.84, .68, .12),
               (1.84, 0, .12)],
        "A2": [(1.40, 0, .685), (1.40, .50, .715), (1.40, .74, .795), (1.40, .96, .815),
               (1.40, .985, .64), (1.40, .965, .34), (1.40, .93, .15), (1.40, .68, .12),
               (1.40, 0, .12)],
        "A3": [(.975, 0, .76), (.975, .64, .775), (.975, .80, .80), (.975, .945, .795),
               (.975, .965, .61), (.975, .935, .34), (.975, .93, .15), (.975, .69, .12),
               (.975, 0, .12)],
        "W0": [(.96, 0, .79), (.86, .70, .80), (.84, .815, .80), (.84, .915, .765),
               (.84, .94, .60), (.84, .91, .34), (.84, .935, .15), (.84, .70, .12),
               (.84, 0, .12)],
        "RF": [(0.0, 0, 1.15), (-.08, .60, 1.125)] + [None] * 7,
        "BP": [(-.72, 0, 1.13), (-.72, .585, 1.105), (-.72, .86, .835), (-.72, .925, .775),
               (-.70, .82, .66), (-.70, .81, .46), (-.72, .95, .15), (-.72, .72, .12),
               (-.72, 0, .12)],
        "SC": [None, None, (-.80, .865, .85), (-.80, .95, .805), (-.775, .985, .69),
               (-.775, .975, .46), (-.78, .955, .155), (-.78, .72, .12), (-.78, 0, .12)],
        "RA": [(-1.32, 0, 1.00), (-1.32, .56, .985), (-1.32, .80, .905),
               (-1.32, .98, .865), (-1.32, 1.005, .68), (-1.32, .985, .40),
               (-1.32, .955, .16), (-1.32, .70, .13), (-1.32, 0, .13)],
        "RB": [(-1.80, 0, .915), (-1.80, .60, .905), (-1.80, .80, .87), (-1.80, .96, .845),
               (-1.80, .985, .67), (-1.80, .965, .40), (-1.80, .93, .21), (-1.80, .70, .17),
               (-1.80, 0, .17)],
        "T1": [(-2.22, 0, .885), (-2.21, .62, .875), (-2.19, .80, .845),
               (-2.15, .905, .815), (-2.13, .93, .66), (-2.13, .915, .42),
               (-2.15, .88, .28), (-2.20, .68, .25), (-2.22, 0, .25)],
    }
    T = {k: [V3(p) if p is not None else None for p in v] for k, v in T.items()}
    for j in range(2, 9):
        T["RF"][j] = T["W0"][j].lerp(T["BP"][j], 0.62)
    for j in range(0, 2):
        T["SC"][j] = T["BP"][j].lerp(T["RA"][j], 0.12)
    for k in ORDER:
        PT[k] = {LINES[j]: T[k][j] for j in range(9)}
    return [T[k] for k in ORDER]


PANELS = ["hood", "bumper_f", "fender_f", "door", "quarter", "deck", "bumper_r", "roof",
          "glass_ws", "glass_side", "glass_rear", "trim", "sill", "floor", "mouth",
          "mouth_frame", "lightband", "tail", "tail_frame", "scoop", "vent", "well"]
PMAT = dict(hood="carbon", bumper_f="paint", fender_f="paint", door="paint", quarter="paint",
            deck="carbon", bumper_r="paint", roof="carbon", glass_ws="glass",
            glass_side="glass", glass_rear="glass", trim="gloss_black", sill="cladding",
            floor="underbody", mouth="void", mouth_frame="cladding",
            lightband="gloss_black", tail="void", tail_frame="cladding", scoop="void",
            vent="void", well="well")
PI = {n: i for i, n in enumerate(PANELS)}
FRONT_C = V3((2.285, 0, 0.285))     # middle of the mouth
REAR_C = V3((-2.20, 0, 0.56))       # middle of the tail panel
BAND_W = 0.05
MOUTH_D, TAIL_D = 0.235, 0.16
CAPS = {}


def panel_of(i, j):
    if j >= 6:
        return "floor"
    if j == 5:
        return "sill"
    if i == 0:
        return "bumper_f"
    if i == 10:
        return "bumper_r"
    if j == 0:
        return ("hood", "hood", "hood", "hood", "glass_ws", "roof", "glass_rear",
                "glass_rear", "deck")[i - 1]
    if j == 1:
        return "fender_f" if i <= 4 else "glass_side" if i <= 6 else "quarter"
    if i <= 4:
        return "fender_f"
    if i <= 6:
        return "door"
    if i == 7 and j == 4:
        return "scoop"
    return "quarter"


def line_crease(i, j):
    """Crease of the edge along line j from station i to i + 1."""
    if j in (0, 8):
        return 0.0
    if j == 1:
        return 1.0 if i <= 8 else 0.7
    if j == 2:
        return 0.7 if i <= 4 else 1.0 if i <= 6 else 0.6
    if j == 3:
        return 1.0
    if j == 4:
        return 1.0 if i == 7 else 0.55
    return 1.0


def station_crease(i, j):
    """Crease of the edge on station i between lines j and j + 1."""
    if i in (0, 11):
        return 1.0
    if i == 5:
        return 1.0 if j <= 1 else 0.0
    if i == 6:
        return 1.0 if j == 0 else 0.0
    if i == 7:
        return 1.0 if j in (0, 1, 4) else 0.5 if j == 3 else 0.0
    if i == 8:
        return 1.0 if j == 4 else 0.6 if j in (3, 5) else 0.0
    if i == 1:
        return 0.5 if j <= 3 else 0.0
    return 0.0


def band_point(p, center, w, out):
    """A point w inside the lip of a cap (toward its middle), out along x."""
    d = V3((0, center.y - p.y, center.z - p.z)).normalized()
    return p + d * w + V3((out, 0, 0))


def build_hull():
    S = stations()
    bm = bmesh.new()
    qid = bm.faces.layers.int.new("qid")
    cr = bm.edges.layers.float.new("crease_edge")
    vc = bm.verts.layers.float.new("crease_vert")
    VV = [[bm.verts.new(p) for p in st] for st in S]


    def face(vs, panel, q=-1):
        f = bm.faces.new(vs)
        f.material_index = PI[panel]
        f[qid] = q
        return f

    def crease(a, b, w):
        e = bm.edges.get((a, b))
        if e is not None and w > e[cr]:
            e[cr] = w

    n = len(S)
    for i in range(n - 1):
        for j in range(8):
            face([VV[i][j], VV[i][j + 1], VV[i + 1][j + 1], VV[i + 1][j]], panel_of(i, j),
                 i * 16 + j)
    for i in range(n - 1):
        for j in range(9):
            crease(VV[i][j], VV[i + 1][j], line_crease(i, j))
    for i in range(n):
        for j in range(8):
            crease(VV[i][j], VV[i][j + 1], station_crease(i, j))

    def cap(ring, center, sgn, inner, frame, depth):
        r1, r2 = [], []
        for v in ring:
            L = hypot(center.y - v.co.y, center.z - v.co.z)
            r1.append(bm.verts.new(band_point(v.co, center, BAND_W, sgn * 0.008)))
            p = band_point(v.co, center, min(0.12, L * 0.6), 0.0)
            p.x = center.x + sgn * depth
            r2.append(bm.verts.new(p))
            CAPS.setdefault(inner, []).append(p.copy())
        fs = []
        for j in range(len(ring) - 1):
            fs.append(face([ring[j], ring[j + 1], r1[j + 1], r1[j]],
                           "lightband" if j < 5 else frame))
            fs.append(face([r1[j], r1[j + 1], r2[j + 1], r2[j]], frame))
        fs.append(face(r2, inner))
        for f in fs:
            for e in f.edges:
                e[cr] = 1.0

    cap(VV[0], FRONT_C, -1, "mouth", "mouth_frame", MOUTH_D)
    cap(VV[-1], REAR_C, 1, "tail", "tail_frame", TAIL_D)

    bmesh.ops.mirror(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], axis='Y',
                     merge_dist=1e-5)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    def recess(i, j, thick, depth, inner="vent", wall="vent"):
        for sgn in (1, -1):
            fs = [f for f in bm.faces if f[qid] == i * 16 + j
                  and f.calc_center_median().y * sgn > 0]
            r = bmesh.ops.inset_region(bm, faces=fs, thickness=thick, depth=-depth,
                                       use_even_offset=True, use_boundary=True)
            for f in r["faces"]:
                f.material_index = PI[wall]
                f[qid] = -1
                for e in f.edges:
                    e[cr] = 1.0
            for f in fs:
                f.material_index = PI[inner]

    recess(3, 0, 0.085, 0.03)      # hood extractor
    recess(4, 4, 0.035, 0.03)      # vent behind the front wheel
    recess(9, 0, 0.09, 0.025)      # deck vents
    for pn, t in (("glass_ws", 0.035), ("glass_side", 0.028), ("glass_rear", 0.04)):
        fs = [f for f in bm.faces if f.material_index == PI[pn]]
        r = bmesh.ops.inset_region(bm, faces=fs, thickness=t, depth=0.0,
                                   use_even_offset=True, use_boundary=True)
        rim = set(r["faces"])
        for f in rim:
            f.material_index = PI["trim"]
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

    me = bpy.data.meshes.new("hull")
    bm.to_mesh(me)
    bm.free()
    pm = {}
    for pn in PANELS:
        pm[pn] = bpy.data.materials.new("P_" + pn)
        me.materials.append(pm[pn])
    hull = bpy.data.objects.new("hull", me)
    CAR.objects.link(hull)
    md = hull.modifiers.new("subd", 'SUBSURF')
    md.levels = SUBDIV
    md.render_levels = SUBDIV
    md.subdivision_type = 'CATMULL_CLARK'

    # wheel wells
    g = Geo()
    for cx, cz, ra in ((FA_X, F_R, F_ARCH), (RA_X, R_R, R_ARCH)):
        for sgn in (1, -1):
            y0 = 0.675 if cx > 0 else 0.62
            pts = [V3((cx + ra * cos(rad(a)), sgn * y0, cz + ra * sin(rad(a))))
                   for a in ARCH_ANG]
            poly = [V3((pts[0].x, sgn * y0, -0.3))] + pts + [V3((pts[-1].x, sgn * y0, -0.3))]
            g.prism(poly, (0, sgn * 0.8, 0))
    cme = bpy.data.meshes.new("cut")
    cme.from_pydata([tuple(p) for p in g.v], [], g.f)
    cbm = bmesh.new()
    cbm.from_mesh(cme)
    bmesh.ops.recalc_face_normals(cbm, faces=cbm.faces)
    cbm.to_mesh(cme)
    cbm.free()
    cme.materials.append(pm["well"])
    cut = bpy.data.objects.new("cut", cme)
    CAR.objects.link(cut)
    md = hull.modifiers.new("wells", 'BOOLEAN')
    md.operation = 'DIFFERENCE'
    md.object = cut
    md.solver = 'EXACT'
    try:
        md.material_mode = 'TRANSFER'
    except Exception:
        pass
    res = evaluated_mesh(hull)
    names = [m.name[2:] for m in res.materials]
    bpy.data.objects.remove(hull)
    bpy.data.objects.remove(cut)

    # split into panels
    for idx, pn in enumerate(names):
        pb = bmesh.new()
        pb.from_mesh(res)
        dele = [f for f in pb.faces if f.material_index != idx]
        if len(dele) == len(pb.faces):
            pb.free()
            continue
        bmesh.ops.delete(pb, geom=dele, context='FACES')
        for f in pb.faces:
            f.material_index = 0
        mat = PMAT[pn]
        if pn != "well":
            shrink(pb, 0.0012)
        pme = bpy.data.meshes.new("body." + pn)
        pb.to_mesh(pme)
        pb.free()
        pme.materials.append(MAT[mat])
        ob = bpy.data.objects.new("body." + pn, pme)
        CAR.objects.link(ob)
        if pn == "well":
            continue
        md = ob.modifiers.new("solid", 'SOLIDIFY')
        md.offset = -1.0
        if mat == "glass":
            md.thickness = 0.006
            pme.shade_smooth()
            continue
        md.thickness = 0.014
        md.use_rim_only = True
        if mat == "void":
            continue
        finish(ob, bevel=0.0045 if mat == "paint" else 0.003, segs=2, angle=14.0)


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


# ---------------------------------------------------------------------------------------
# details on the body
# ---------------------------------------------------------------------------------------
def shr(quad, k, lift, out):
    """A quad pulled toward its middle by k and moved by lift along its normal."""
    q = [V3(p) for p in quad]
    c = sum(q, V3()) / 4
    n = (q[1] - q[0]).cross(q[3] - q[0]).normalized()
    if n.dot(V3(out)) < 0:
        n = -n
    return [p.lerp(c, k) + n * lift for p in q]


def lip_path(st, center, names, w, out):
    return [band_point(PT[st][n], center, w, out) for n in names]


def build_details():
    P = PT
    # ---- front lights: a strip under the nose lip, turning down the outer edge
    top = [P["N0"]["C"].lerp(P["N0"]["H"], 0.45)] + [P["N0"][n] for n in "HGSU"]
    top.append(P["N0"]["U"].lerp(P["N0"]["M"], 0.85))
    path = [band_point(p, FRONT_C, BAND_W * 0.5, 0.0) for p in top]
    g = Geo()
    g.sweep(path, [(-0.009, -0.004), (0.009, -0.004), (0.009, 0.006), (-0.009, 0.006)],
            up=(1, 0, 0))
    g.obj("led.front", "led_front", mirror=True)

    # ---- mouth: struts, honeycomb in the middle, slats in the side ducts, splitter
    xb = FRONT_C.x - MOUTH_D
    g = Geo()
    a = V3((2.262, 0.40, 0.44))
    b = V3((2.225, 0.45, 0.125))
    g.sweep([a, b], [(-0.03, -0.21), (0.03, -0.21), (0.022, 0.0), (-0.022, 0.0)], up=(1, 0, 0))
    g.obj("mouth.struts", "paint", bevel=0.004, mirror=True)
    g = Geo()
    half = [(p.y, p.z) for p in CAPS["mouth"]]
    poly = half + [(-y, z) for (y, z) in half[::-1]]
    g.honeycomb(poly, xb, 0.015, 0.0028, 0.012, 1, keep=lambda y, z: abs(y) < 0.46)
    g.obj("mouth.mesh", "grille")
    g = Geo()
    g.louvers((xb + 0.022, 0.43, 0.40), (xb + 0.03, 0.45, 0.15), (xb + 0.03, 0.80, 0.15),
              (xb + 0.022, 0.80, 0.40), 5, 0.05, 0.008, rad(28), out=(1, 0, 0), margin=0.04)
    g.obj("mouth.slats", "grille", bevel=0.002, mirror=True)
    # canards and badge
    g = Geo()
    for z0 in (0.20, 0.31):
        lo = [(2.115, 0.83, z0), (1.94, 0.91, z0 + 0.035), (1.94, 0.99, z0 + 0.05),
              (2.10, 0.905, z0 + 0.008)]
        g.hexa(lo + [(p[0], p[1], p[2] + 0.008) for p in lo])
    g.obj("canards", "carbon", bevel=0.002, mirror=True)
    g = Geo()
    g.lathe([(0.0, 0.002), (0.0, 0.028), (0.005, 0.024), (0.005, 0.002)], 6,
            xf=Matrix.Translation((2.294, 0, 0.428)) @ Matrix.Rotation(-pi / 2, 4, 'Z'))
    g.obj("badge", "rim_bright", bevel=0.001)
    g = Geo()
    g.prism([(2.335, 0, 0.095), (2.295, 0.58, 0.095), (2.215, 0.865, 0.095),
             (2.10, 0.945, 0.095), (1.88, 0.945, 0.095), (1.88, 0, 0.095)], (0, 0, 0.022))
    g.prism([(2.16, 0.932, 0.095), (2.12, 0.932, 0.235), (1.93, 0.932, 0.175),
             (1.90, 0.932, 0.095)], (0, 0.014, 0))
    g.obj("splitter", "carbon", bevel=0.003, mirror=True)

    # ---- rear lights: one bar across the tail and down both sides
    half = [P["T1"]["U"].lerp(P["T1"]["M"], 0.8)] + [P["T1"][n] for n in "USGH"]
    hp = [band_point(p, REAR_C, BAND_W * 0.5, 0.0) for p in half]
    path = hp + [band_point(P["T1"]["C"], REAR_C, BAND_W * 0.5, 0.0)] + [my(p) for p in hp[::-1]]
    g = Geo()
    g.sweep(path, [(-0.008, -0.006), (0.008, -0.006), (0.008, 0.004), (-0.008, 0.004)],
            up=(-1, 0, 0))
    g.obj("led.rear", "led_rear")
    xt = REAR_C.x + TAIL_D
    g = Geo()
    half = [(p.y, p.z) for p in CAPS["tail"]]
    poly = half + [(-y, z) for (y, z) in half[::-1]]

    def clear(y, z):
        return hypot(abs(y) - 0.21, z - 0.50) > 0.085 and not (abs(y) < 0.16 and abs(z - 0.335) < 0.07)
    g.honeycomb(poly, xt - 0.012, 0.021, 0.0035, 0.012, -1, keep=clear)
    g.obj("tail.mesh", "grille")
    g = Geo()
    g.prism([(-2.115, -0.86, 0.60), (-2.14, -0.86, 0.618), (-2.14, -0.86, 0.672),
             (-2.115, -0.86, 0.69), (-2.06, -0.86, 0.675), (-2.06, -0.86, 0.615)], (0, 1.72, 0))
    g.obj("tail.beam", "carbon", bevel=0.003)
    # ---- diffuser fins and exhausts
    g = Geo()
    for y in (0.0, 0.23, 0.46, 0.69):
        g.prism([(-1.76, y - 0.007, 0.185), (-2.235, y - 0.007, 0.268),
                 (-2.25, y - 0.007, 0.115), (-2.02, y - 0.007, 0.105),
                 (-1.80, y - 0.007, 0.135)], (0, 0.014, 0))
    g.obj("diffuser", "carbon", bevel=0.003, mirror=True)
    g = Geo()
    rz = Matrix.Translation((xt, 0.21, 0.50)) @ Matrix.Rotation(pi / 2, 4, 'Z')
    g.lathe([(0, 0.060), (0.13, 0.060), (0.145, 0.054), (0.145, 0.047), (0, 0.047)], 6, xf=rz)
    g.lathe([(0, 0.075), (0.02, 0.075), (0.03, 0.062), (0, 0.062)], 6, xf=rz)
    g.lathe([(0.0, 0.002), (0.0, 0.047), (0.03, 0.047), (0.03, 0.002)], 6, xf=rz)
    g.obj("exhaust", "rim", bevel=0.003, mirror=True)
    g = Geo()
    g.lathe([(0.031, 0.002), (0.031, 0.044), (0.034, 0.044), (0.034, 0.002)], 6, xf=rz)
    g.obj("exhaust.glow", "ember", mirror=True)

    # ---- wheel arch trims
    g = Geo()
    for cx, cz, ra, yo in ((FA_X, F_R, F_ARCH, F_OUT + 0.04), (RA_X, R_R, R_ARCH, R_OUT + 0.04)):
        ring = [(cx + r * cos(rad(a)), y, cz + r * sin(rad(a)))
                for y in (0.88, yo) for r in (ra - 0.005, ra + 0.04) for a in ARCH_ANG]
        n = len(ARCH_ANG)
        faces = []
        for k in range(n - 1):
            i0, i1, o0, o1 = k, k + 1, n + k, n + k + 1          # inner y: in, out radius
            faces += [(i0, i1, o1, o0),
                      (2 * n + i0, 2 * n + i1, 2 * n + o1, 2 * n + o0),
                      (i0, i1, 2 * n + i1, 2 * n + i0), (o0, o1, 2 * n + o1, 2 * n + o0)]
        faces += [(0, n, 3 * n, 2 * n), (n - 1, 2 * n - 1, 4 * n - 1, 3 * n - 1)]
        g.add(ring, faces)
    g.obj("arch.trims", "cladding", bevel=0.005, mirror=True)

    # ---- accent line along the sill
    g = Geo()
    path = [P[s]["M"] + V3((0, 0.004, 0.012)) for s in ("W0", "RF", "BP")]
    path[0] = path[0] + V3((-0.05, 0, 0))
    path[-1] = path[-1] + V3((0.04, 0, 0))
    g.sweep(path, [(-0.004, -0.005), (0.004, -0.005), (0.004, 0.005), (-0.004, 0.005)],
            up=(0, 0, 1))
    g.obj("led.sill", "led_accent", mirror=True)

    # ---- slats: scoop, fender vent, hood extractor, deck vents, engine cover
    g = Geo()
    g.louvers(P["BP"]["U"], P["BP"]["M"], P["SC"]["M"], P["SC"]["U"], 5, 0.04, 0.007,
              rad(20), out=(1, 0.3, 0), lift=0.004, margin=0.08)
    gp = Geo()
    q = shr([P["A3"]["U"], P["A3"]["M"], P["W0"]["M"], P["W0"]["U"]], 0.16, -0.008, (0, 1, 0))
    gp.louvers(q[0], q[3], q[2], q[1], 4, 0.034, 0.006, rad(35), out=(0, 1, 0))
    gp.obj("vent.slats", "paint", bevel=0.002, mirror=True)
    q = shr([P["A2"]["C"], P["A2"]["H"], P["A3"]["H"], P["A3"]["C"]], 0.30, -0.008, (0, 0, 1))
    g.louvers(q[0], q[3], q[2], q[1], 4, 0.045, 0.007, rad(-30), out=(0, 0, 1))
    q = shr([P["RA"]["C"], P["RA"]["H"], P["RB"]["H"], P["RB"]["C"]], 0.30, -0.008, (0, 0, 1))
    g.louvers(q[0], q[3], q[2], q[1], 4, 0.045, 0.007, rad(30), out=(0, 0, 1))
    g.obj("slats", "grille", bevel=0.002, mirror=True)
    g = Geo()
    a, b = P["BP"]["H"].lerp(P["BP"]["C"], 0.08), P["RA"]["H"].lerp(P["RA"]["C"], 0.08)
    g.louvers(a, b, my(b), my(a), 6, 0.075, 0.012, rad(10), out=(0, 0, 1), lift=0.022,
              margin=0.07)
    g.obj("engine.louvers", "gloss_black", bevel=0.003)

    # ---- mirrors: camera pods on blades
    g = Geo()
    g.sweep([(0.63, 0.895, 0.772), (0.615, 0.985, 0.800)],
            [(-0.03, -0.004), (0.03, -0.004), (0.03, 0.004), (-0.03, 0.004)], up=(0, 0, 1))
    g.obj("mirror.stalks", "cladding", bevel=0.002, mirror=True)
    g = Geo()
    g.hexa([(0.69, 0.975, 0.792), (0.69, 1.005, 0.792), (0.53, 1.03, 0.782),
            (0.53, 0.965, 0.782), (0.675, 0.978, 0.812), (0.675, 1.002, 0.812),
            (0.53, 1.025, 0.835), (0.53, 0.970, 0.835)])
    g.obj("mirror.pods", "paint", bevel=0.004, mirror=True)
    g = Geo()
    g.box((0.5285, 0.9975, 0.808), (0.004, 0.045, 0.036))
    g.obj("mirror.lens", "gloss_black", mirror=True)

    # ---- bolts on the arch trims
    g = Geo()
    for cx, cz, ra, yo in ((FA_X, F_R, F_ARCH, F_OUT + 0.04), (RA_X, R_R, R_ARCH, R_OUT + 0.04)):
        for k in range(len(ARCH_ANG) - 1):
            for t in (0.25, 0.75):
                a = rad(ARCH_ANG[k] + (ARCH_ANG[k + 1] - ARCH_ANG[k]) * t)
                r = (ra + 0.0175) / cos(rad((ARCH_ANG[k + 1] - ARCH_ANG[k]) * (t - 0.5)))
                r = (ra + 0.0175) * cos(rad((ARCH_ANG[k + 1] - ARCH_ANG[k]) / 2)) / cos(
                    rad((ARCH_ANG[k + 1] - ARCH_ANG[k]) * (t - 0.5)))
                g.lathe([(-0.002, 0.0015), (-0.002, 0.0065), (0.0035, 0.0065), (0.0035, 0.0015)],
                        6, xf=Matrix.Translation((cx + r * cos(a), yo, cz + r * sin(a))))
    g.obj("arch.bolts", "rim_bright", mirror=True)

    # ---- plate
    g = Geo()
    g.box((xt - 0.012, 0, 0.335), (0.012, 0.27, 0.095))
    g.obj("plate", "gloss_black", bevel=0.003)
    g = Geo()
    text_flat(g, "VB 27-881", 0.05, (xt - 0.0185, 0, 0.335), (0, -1, 0), (0, 0, 1), spacing=1.1)
    g.obj("plate.glyphs", "led_accent")

    build_surface_details()

    # ---- wing
    g = Geo()
    g.prism([(-2.00, -0.86, 1.022), (-2.06, -0.86, 1.042), (-2.20, -0.86, 1.048),
             (-2.32, -0.86, 1.062), (-2.32, -0.86, 1.050), (-2.20, -0.86, 1.030),
             (-2.06, -0.86, 1.016)], (0, 1.72, 0))
    g.obj("wing.blade", "carbon", bevel=0.003)
    g = Geo()
    g.box((-2.3215, 0, 1.056), (0.004, 0.50, 0.006))
    g.obj("led.wing", "led_rear")
    # side skirt blades with a winglet at the back
    g = Geo()
    g.prism([(0.93, 0.90, 0.126), (0.93, 0.975, 0.126), (-0.70, 0.995, 0.126),
             (-0.86, 1.0, 0.126), (-0.86, 0.90, 0.126)], (0, 0, 0.016))
    g.prism([(-0.60, 0.985, 0.13), (-0.86, 0.985, 0.13), (-0.86, 0.985, 0.225),
             (-0.80, 0.985, 0.225)], (0, 0.012, 0))
    g.obj("skirt", "carbon", bevel=0.003, mirror=True)
    g = Geo()
    g.prism([(-1.97, 0.86, 0.995), (-2.34, 0.86, 1.00), (-2.35, 0.86, 1.09),
             (-2.12, 0.86, 1.078), (-1.99, 0.86, 1.045)], (0, 0.014, 0))
    g.prism([(-1.86, 0.45, 0.895), (-2.10, 0.45, 0.875), (-2.21, 0.45, 1.04),
             (-2.09, 0.45, 1.035)], (0, 0.022, 0))
    g.obj("wing.plates", "paint", bevel=0.003, mirror=True)


BVH = [None]


def body_bvh():
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    vs, ps = [], []
    for ob in CAR.objects:
        if not ob.name.startswith("body.") or ob.name.endswith("well"):
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        o = len(vs)
        vs += [v.co.copy() for v in me.vertices]
        ps += [tuple(o + i for i in p.vertices) for p in me.polygons]
        ev.to_mesh_clear()
    BVH[0] = BVHTree.FromPolygons(vs, ps)


def on_body(u, v, proj):
    """The body's surface point and normal under (x, z) from the left, or (x, y) from above."""
    if proj == 'y':
        o, d = V3((u, 1.6, v)), V3((0, -1, 0))
    elif proj == 'Y':
        o, d = V3((u, -1.6, v)), V3((0, 1, 0))
    elif proj == 'x':
        o, d = V3((3.0, u, v)), V3((-1, 0, 0))
    else:
        o, d = V3((u, v, 2.0)), V3((0, 0, -1))
    loc, n, _, _ = BVH[0].ray_cast(o, d)
    if loc is None:
        return None, None
    if n.dot(d) > 0:
        n = -n
    return loc, n


def ribbon(g, pts, proj, w, lift=0.0008, closed=False, step=0.012):
    """A flat strip of width w lying on the body along a path given in projection."""
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
        loc, n = on_body(q.x, q.y, proj)
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


FONT = [None]


def text_mesh(txt, size, spacing=1.0):
    """Flat outline text as (verts, faces), centered on its origin."""
    cu = bpy.data.curves.new("txt", 'FONT')
    cu.body = txt
    cu.size = size
    cu.space_character = spacing
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    if FONT[0] is None:
        FONT[0] = False
        for p in ("/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf",
                  "C:/Windows/Fonts/bahnschrift.ttf"):
            if os.path.exists(p):
                FONT[0] = bpy.data.fonts.load(p)
                break
    if FONT[0]:
        cu.font = FONT[0]
    ob = bpy.data.objects.new("txt", cu)
    SCN.collection.objects.link(ob)
    me = evaluated_mesh(ob)
    vs = [v.co.copy() for v in me.vertices]
    fs = [tuple(p.vertices) for p in me.polygons]
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return vs, fs


def text_on_body(g, txt, size, x0, z0, side, lift=0.0012, spacing=1.0):
    """Text on the body's flank, reading left to right for someone looking at that side."""
    vs, fs = text_mesh(txt, size, spacing)
    out = []
    for p in vs:
        loc, n = on_body(x0 - side * p.x, z0 + p.y, 'y' if side > 0 else 'Y')
        if loc is None:
            return
        out.append(loc + n * lift)
    g.add(out, fs)


def text_flat(g, txt, size, origin, right, up, spacing=1.0):
    vs, fs = text_mesh(txt, size, spacing)
    o, r, u = V3(origin), V3(right), V3(up)
    g.add([o + r * p.x + u * p.y for p in vs], fs)


def build_surface_details():
    body_bvh()
    # roof: a slim light bar and a fin, seated on the roof as built
    zr = on_body(-0.10, 0.0, 'z')[0].z
    g = Geo()
    g.prism([(-0.03, -0.17, zr - 0.004), (-0.07, -0.17, zr + 0.016), (-0.13, -0.17, zr + 0.016),
             (-0.18, -0.17, zr - 0.004)], (0, 0.34, 0))
    zf = on_body(-0.60, 0.0, 'z')[0].z
    g.prism([(-0.50, -0.006, zf - 0.005), (-0.62, -0.006, zf + 0.065), (-0.66, -0.006, zf + 0.065),
             (-0.69, -0.006, zf - 0.005)], (0, 0.012, 0))
    g.obj("roof.pod", "cladding", bevel=0.004)
    g = Geo()
    g.box((-0.048, 0, zr + 0.007), (0.005, 0.28, 0.005), rot=Matrix.Rotation(rad(-22), 3, 'Y'))
    g.obj("led.roof", "led_accent")
    # parking sensors on the nose, pins on the hood
    g = Geo()
    gp = Geo()

    def stud(geo, loc, n, prof, seg):
        xf = Matrix.Translation(loc) @ V3((0, 1, 0)).rotation_difference(n).to_matrix().to_4x4()
        geo.lathe(prof, seg, xf=xf)
    for y in (0.24, 0.60, -0.24, -0.60):
        loc, n = on_body(y, 0.495, 'x')
        stud(g, loc, n, [(-0.002, 0.001), (-0.002, 0.011), (0.0015, 0.011), (0.0015, 0.001)], 12)
    for y in (0.37, -0.37):
        loc, n = on_body(1.90, y, 'z')
        stud(gp, loc, n, [(-0.002, 0.001), (-0.002, 0.019), (0.003, 0.019), (0.003, 0.001)], 16)
        stud(gp, loc, n, [(0.003, 0.001), (0.003, 0.0045), (0.013, 0.0045), (0.013, 0.001)], 8)
        stud(g, loc, n, [(0.003, 0.012), (0.003, 0.016), (0.0045, 0.016), (0.0045, 0.012)], 16)
    g.obj("sensors", "gloss_black")
    gp.obj("hood.pins", "rim_bright", bevel=0.0008)
    # lettering
    g = Geo()
    for side in (1, -1):
        text_on_body(g, "VANTA-R", 0.05, 0.50, 0.475, side, spacing=1.15)
        text_on_body(g, "HV 800", 0.016, -1.965, 0.515, side, spacing=1.2)
        text_flat(g, "09", 0.06, (-2.17, side * 0.8745, 1.04), (-side, 0, 0), (0, 0, 1))
    g.obj("lettering", "decal")
    g = Geo()
    text_flat(g, "H A L C Y O N", 0.034, (-2.1412, 0, 0.645), (0, -1, 0), (0, 0, 1), spacing=1.3)
    g.obj("led.name", "led_rear")
    # door handle slots, charge flap outlines
    g = Geo()
    ribbon(g, [(-0.36, 0.705), (-0.52, 0.712)], 'y', 0.02)
    hexa = [(-1.965 + 0.062 * cos(rad(a)), 0.60 + 0.062 * sin(rad(a))) for a in range(0, 360, 60)]
    ribbon(g, hexa, 'y', 0.004, closed=True)
    for x0, ya, yb in ((1.56, 0.80, 0.925), (-1.14, 0.845, 0.95)):
        for k in range(5):
            x = x0 - k * 0.062
            ribbon(g, [(x, ya), (x - 0.02, yb)], 'z', 0.02)
    g.obj("lines", "void", mirror=True)
    # wiper: a blade lying on the glass and its arm
    g = Geo()
    blade = []
    for k in range(9):
        t = k / 8
        loc, n = on_body(0.945 - 0.085 * t, -0.04 + 0.62 * t, 'z')
        blade.append(loc + n * 0.014)
    g.sweep(blade, [(-0.004, -0.008), (0.004, -0.008), (0.004, 0.006), (-0.004, 0.006)],
            up=(0, 0, 1))
    piv, _ = on_body(0.975, 0.14, 'z')
    g.sweep([piv + V3((0, 0, 0.012)), blade[4] + V3((0, 0, 0.012))],
            [(-0.006, -0.004), (0.006, -0.004), (0.006, 0.004), (-0.006, 0.004)], up=(0, 0, 1))
    g.obj("wiper", "cladding", bevel=0.0015)
    # markers and decals
    g = Geo()
    ribbon(g, [(2.03, 0.425), (1.935, 0.44)], 'y', 0.012)
    g.obj("led.marker", "led_accent", mirror=True)
    g = Geo()
    x = -0.30
    for k, w in enumerate((0.006, 0.012, 0.004, 0.004, 0.010, 0.006, 0.014, 0.004, 0.008,
                           0.004, 0.012, 0.006)):
        ribbon(g, [(x - w / 2, 0.515), (x - w / 2, 0.56)], 'y', w)
        x -= w + 0.006
    for k in range(4):
        ribbon(g, [(-1.86 - k * 0.04, 0.735), (-1.88 - k * 0.04, 0.775)], 'y', 0.014)
    g.obj("decals", "decal", mirror=True)


# ---------------------------------------------------------------------------------------
# interior
# ---------------------------------------------------------------------------------------
def build_interior():
    g = Geo()
    g.box((0.0, 0, 0.15), (1.45, 1.6, 0.03))
    g.prism([(-0.66, -0.80, 0.14), (-0.66, 0.80, 0.14), (-0.66, 0.84, 0.80),
             (-0.66, 0.60, 1.06), (-0.66, -0.60, 1.06), (-0.66, -0.84, 0.80)], (0.04, 0, 0))
    g.prism([(0.80, -0.78, 0.50), (0.80, -0.78, 0.775), (0.52, -0.78, 0.775),
             (0.40, -0.78, 0.70), (0.44, -0.78, 0.50)], (0, 1.56, 0))
    g.box((0.05, 0, 0.27), (0.95, 0.2, 0.24))
    g.obj("interior.tub", "interior", bevel=0.006)
    g = Geo()
    tilt = Matrix.Rotation(rad(-20), 3, 'Y')
    for y in (0.37, -0.37):
        g.box((-0.02, y, 0.30), (0.50, 0.46, 0.12))
        g.box((-0.40, y, 0.62), (0.11, 0.44, 0.62), rot=tilt)
        g.box((-0.535, y, 0.965), (0.07, 0.22, 0.15), rot=tilt)
        for s in (-1, 1):
            g.box((-0.02, y + s * 0.235, 0.33), (0.46, 0.05, 0.16))
            g.box((-0.385, y + s * 0.225, 0.58), (0.14, 0.05, 0.50), rot=tilt)
    g.obj("interior.seats", "seat", bevel=0.012, segs=3)
    g = Geo()
    wheel = (Matrix.Translation((0.33, 0.37, 0.75)) @ Matrix.Rotation(rad(-70), 4, 'Y')
             @ Matrix.Rotation(pi / 2, 4, 'X'))
    g.lathe([(-0.012, 0.155), (0.0, 0.167), (0.012, 0.155), (0.0, 0.143)], 24, xf=wheel)
    g.box((0.40, 0.37, 0.72), (0.16, 0.05, 0.05))
    g.obj("interior.wheel", "interior", sharp=40)
    g = Geo()
    scr = Matrix.Rotation(rad(-25), 3, 'Y')
    g.box((0.41, 0.0, 0.745), (0.008, 0.30, 0.08), rot=scr)
    g.box((0.47, 0.37, 0.795), (0.008, 0.26, 0.05), rot=scr)
    g.obj("interior.screens", "screen")
    # power unit under the rear glass
    g = Geo()
    ge = Geo()
    g.box((-1.03, 0, 0.80), (0.60, 1.04, 0.02))
    up = Matrix.Rotation(pi / 2, 4, 'X')
    g.lathe([(0.0, 0.004), (0.0, 0.17), (0.10, 0.17), (0.13, 0.12), (0.13, 0.004)], 8,
            xf=Matrix.Translation((-1.02, 0, 0.81)) @ up)
    ge.lathe([(0.045, 0.171), (0.045, 0.176), (0.06, 0.176), (0.06, 0.171)], 8,
             xf=Matrix.Translation((-1.02, 0, 0.81)) @ up)
    ge.lathe([(0.131, 0.02), (0.131, 0.09), (0.134, 0.09), (0.134, 0.02)], 8,
             xf=Matrix.Translation((-1.02, 0, 0.81)) @ up)
    along = Matrix.Rotation(pi / 2, 4, 'Z')
    for y in (0.30, -0.30):
        xf = Matrix.Translation((-0.80, y, 0.875)) @ along
        g.lathe([(0.0, 0.004), (0.0, 0.058), (0.44, 0.058), (0.44, 0.004)], 12, xf=xf)
        for k in range(4):
            ge.lathe([(0.06 + k * 0.1, 0.058), (0.06 + k * 0.1, 0.061), (0.075 + k * 0.1, 0.061),
                      (0.075 + k * 0.1, 0.058)], 12, xf=xf)
        g.sweep([(-1.02, y * 0.45, 0.90), (-1.02, y * 0.8, 0.93), (-1.02, y, 0.90)],
                [(-0.012, -0.012), (0.012, -0.012), (0.012, 0.012), (-0.012, 0.012)],
                up=(1, 0, 0))
    g.obj("power.unit", "rim", bevel=0.004)
    ge.obj("power.glow", "ember")


# ---------------------------------------------------------------------------------------
# wheels
# ---------------------------------------------------------------------------------------
def build_wheel(tag, cx, R, w, Rr, out_y, side):
    hw = w / 2
    flip = side < 0
    loc = (cx, side * (out_y - hw), R)
    N = 144
    # tire
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
    tire = g.obj("tire." + tag, "rubber", flip_y=flip, loc=loc)
    bm = bmesh.new()
    bm.from_mesh(tire.data)
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
    bm.to_mesh(tire.data)
    bm.free()
    tire.data.shade_smooth()
    tire.data.set_sharp_from_angle(angle=rad(32))

    # rim: barrel, blades, hub
    g = Geo()
    g.lathe([(-hw + 0.03, Rr), (hw - 0.006, Rr), (hw - 0.006, Rr - 0.006),
             (hw - 0.016, Rr - 0.006), (hw - 0.016, Rr - 0.02), (-hw + 0.03, Rr - 0.02)], 72)
    nb = 7
    r0, r1 = 0.066, Rr - 0.018
    y0, y1 = hw - 0.078, hw - 0.026
    for k in range(nb):
        th = 2 * pi * k / nb

        def pt(r, a, y):
            return (r * cos(th + a), y, r * sin(th + a))
        for (a_in0, a_in1, a_o0, a_o1) in ((-16, -3, 4, 13), (3, 16, 19, 28)):
            fr = [pt(r0, rad(a_in0), y0), pt(r1, rad(a_o0), y1), pt(r1, rad(a_o1), y1),
                  pt(r0, rad(a_in1), y0)]
            bk = [(p[0], p[1] - t, p[2]) for p, t in zip(fr, (0.034, 0.02, 0.02, 0.034))]
            g.hexa(bk + fr)
    g.lathe([(hw - 0.135, 0.004), (hw - 0.135, 0.082), (hw - 0.072, 0.082),
             (hw - 0.062, 0.068), (hw - 0.062, 0.004)], 14)
    g.obj("rim." + tag, "rim", bevel=0.005, flip_y=flip, loc=loc)
    g = Geo()
    g.lathe([(hw - 0.062, 0.004), (hw - 0.062, 0.036), (hw - 0.046, 0.030),
             (hw - 0.046, 0.004)], 6)
    for k in range(5):
        a = 2 * pi * (k + 0.5) / 5
        g.lathe([(hw - 0.064, 0.002), (hw - 0.064, 0.0095), (hw - 0.052, 0.0095),
                 (hw - 0.052, 0.002)], 6,
                xf=Matrix.Translation((0.052 * cos(a), 0, 0.052 * sin(a))))
    g.lathe([(hw - 0.0065, Rr - 0.006), (hw - 0.0065, Rr + 0.0015), (hw - 0.003, Rr + 0.0015),
             (hw - 0.003, Rr - 0.006)], 72)
    g.obj("hub." + tag, "rim_bright", bevel=0.0015, flip_y=flip, loc=loc)
    # light ring
    g = Geo()
    for k in range(6):
        g.lathe([(hw - 0.016, Rr - 0.019), (hw - 0.016, Rr - 0.008), (hw - 0.0085, Rr - 0.008),
                 (hw - 0.0085, Rr - 0.019)], 10, a0=rad(k * 60 + 5), a1=rad(k * 60 + 55))
    g.obj("ring." + tag, "led_wheel", flip_y=flip, loc=loc)
    # brake
    g = Geo()
    g.lathe([(hw - 0.165, 0.09), (hw - 0.165, Rr - 0.04), (hw - 0.135, Rr - 0.04),
             (hw - 0.135, 0.09)], 64)
    g.obj("disc." + tag, "disc", flip_y=flip, loc=loc, sharp=40)
    g = Geo()
    g.lathe([(hw - 0.185, Rr - 0.115), (hw - 0.185, Rr - 0.026), (hw - 0.112, Rr - 0.026),
             (hw - 0.112, Rr - 0.115)], 5, a0=rad(138), a1=rad(202))
    g.obj("caliper." + tag, "caliper", bevel=0.004, flip_y=flip, loc=loc)
    g = Geo()
    g.lathe([(-hw + 0.045, 0.004), (-hw + 0.045, Rr - 0.02), (-hw + 0.03, Rr - 0.02),
             (-hw + 0.03, 0.004)], 48)
    g.obj("drum." + tag, "well", flip_y=flip, loc=loc)


# ---------------------------------------------------------------------------------------
# studio, cameras, render
# ---------------------------------------------------------------------------------------
def aim(ob, target):
    d = V3(target) - ob.location
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def build_studio():
    g = Geo()
    prof = [(0.0, 0.01), (0.0, 16.0)]
    for k in range(1, 13):
        a = (pi / 2) * k / 12
        prof.append((9.0 * (1 - cos(a)), 16.0 + 9.0 * sin(a)))
    prof.append((22.0, 25.0))
    g.lathe(prof, 96, xf=Matrix.Rotation(pi / 2, 4, 'X'), closed=False)
    ob = g.obj("cyc", "floor", coll=STUDIO)
    ob.data.shade_smooth()
    if not ARGS.night:
        # the wall glows a little, so every view has the same even grey behind the car
        m = MAT["floor"]
        nt = m.node_tree
        b = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
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
    night = ARGS.night
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
        m = MAT["floor"]
        nt = m.node_tree
        b = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
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
        area("strip", (0.0, 6.5, 1.3), (0, 0, 0.6), 9.0, 0.45, 300)
        area("strip2", (0.0, -6.5, 1.3), (0, 0, 0.6), 9.0, 0.45, 300)


def car_points(prefixes=None):
    pts = []
    for ob in CAR.objects:
        if prefixes and not any(ob.name.startswith(p) for p in prefixes):
            continue
        for c in ob.bound_box:
            pts.append(ob.matrix_world @ V3(c))
    return pts


VIEWS = {
    "hero": dict(dir=(1.0, 0.78, 0.26), lens=70, target=(0, 0, 0.5), focus=(1.6, 0.8, 0.5)),
    "rear": dict(dir=(-1.0, -0.82, 0.30), lens=70, target=(0, 0, 0.5), focus=(-1.6, -0.8, 0.6)),
    "rear_l": dict(dir=(-1.0, 0.62, 0.22), lens=70, target=(0, 0, 0.5)),
    "side": dict(dir=(0.0, 1.0, 0.05), lens=110, target=(0, 0, 0.55)),
    "front": dict(dir=(1.0, 0.0, 0.07), lens=110, target=(0, 0, 0.55)),
    "back": dict(dir=(-1.0, 0.0, 0.09), lens=110, target=(0, 0, 0.55)),
    "top": dict(dir=(0.0, 0.0, 1.0), lens=110, target=(0, 0, 0.5)),
    "low": dict(dir=(1.0, 0.5, 0.045), lens=40, target=(0, 0, 0.5), focus=(1.8, 0.7, 0.4),
                fstop=2.8),
    "wheel": dict(dir=(0.55, 1.0, 0.12), lens=85, target=(FA_X, 0.9, 0.36),
                  fit=("tire.fl",), margin=0.0),
    "nose": dict(dir=(1.0, 0.45, 0.10), lens=85, target=(2.1, 0.45, 0.35), dist=2.6),
    "tail": dict(dir=(-1.0, -0.4, 0.14), lens=85, target=(-2.1, -0.3, 0.6), dist=3.0),
    "cabin": dict(dir=(0.35, 1.0, 0.5), lens=85, target=(-0.2, 0.3, 0.9), dist=3.4),
}


FOCUS = {}


def add_camera(name, v):
    cd = bpy.data.cameras.new(name)
    cd.lens = v["lens"]
    cd.sensor_width = 36
    cd.clip_start, cd.clip_end = 0.1, 200
    ob = bpy.data.objects.new("cam." + name, cd)
    STUDIO.objects.link(ob)
    d = V3(v["dir"]).normalized()
    ob.rotation_euler = d.to_track_quat('Z', 'Y').to_euler()
    tgt = V3(v["target"])
    if v.get("focus"):
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = v.get("fstop", 4.0)
        FOCUS[ob.name] = V3(v["focus"])
    if v.get("dist"):
        ob.location = tgt + d * v["dist"]
        return ob
    pts = car_points(v.get("fit"))
    lo, hi = 1.0, 60.0
    m = v.get('margin', 0.05)
    for _ in range(24):
        mid = (lo + hi) / 2
        ob.location = tgt + d * mid
        bpy.context.view_layer.update()
        ok = True
        for p in pts:
            c = world_to_camera_view(SCN, ob, p)
            if c.z <= 0 or not (m < c.x < 1 - m and m < c.y < 1 - m):
                ok = False
                break
        if ok:
            hi = mid
        else:
            lo = mid
    ob.location = tgt + d * hi
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
    SCN.cycles.samples = ARGS.samples
    SCN.cycles.use_adaptive_sampling = True
    SCN.cycles.use_denoising = True
    r.resolution_x, r.resolution_y = ARGS.res
    r.resolution_percentage = 100
    r.image_settings.file_format = 'JPEG'
    r.image_settings.quality = 93
    try:
        SCN.view_settings.view_transform = 'AgX'
        SCN.view_settings.look = 'AgX - Medium High Contrast'
    except Exception as e:
        print("view transform:", e)


def tri_count():
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    n = 0
    for ob in CAR.objects:
        me = ob.evaluated_get(dg).to_mesh()
        n += sum(len(p.vertices) - 2 for p in me.polygons)
        ob.evaluated_get(dg).to_mesh_clear()
    return n


def main():
    import time
    t0 = time.time()
    make_materials()
    build_hull()
    print("T hull %.1f" % (time.time() - t0))
    build_details()
    build_interior()
    print("T details %.1f" % (time.time() - t0))
    for side, s in ((1, "l"), (-1, "r")):
        build_wheel("f" + s, FA_X, F_R, F_W, F_RIM, F_OUT, side)
        build_wheel("r" + s, RA_X, R_R, R_W, R_RIM, R_OUT, side)
    print("T wheels %.1f" % (time.time() - t0))
    bpy.context.view_layer.update()
    for ob in CAR.objects:
        zs = [(ob.matrix_world @ V3(c)).z for c in ob.bound_box]
        if max(zs) > 1.2 or min(zs) < -0.01:
            print("BBOX", ob.name, min(zs), max(zs))
    pts = car_points()
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    print("CAR size %.3f x %.3f x %.3f m, triangles %d, objects %d" % (
        hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], tri_count(), len(CAR.objects)))
    print("T stats %.1f" % (time.time() - t0))
    build_studio()
    setup_render()
    os.makedirs(ARGS.out, exist_ok=True)
    for name in [v for v in ARGS.views.split(",") if v]:
        cam = add_camera(name, VIEWS[name])
        SCN.camera = cam
        if cam.name in FOCUS:
            cam.data.dof.focus_distance = (FOCUS[cam.name] - cam.location).length
        SCN.render.filepath = os.path.join(ARGS.out, "car_%s%s.jpg" % (
            name, "_night" if ARGS.night else ""))
        bpy.ops.render.render(write_still=True)
        print("RENDERED", SCN.render.filepath)
    if ARGS.blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ARGS.out, "car.blend"))
    if ARGS.glb:
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
        bpy.ops.export_scene.gltf(filepath=os.path.join(ARGS.out, "car.glb"),
                                  export_format='GLB', use_selection=True,
                                  export_apply=True)


main()
