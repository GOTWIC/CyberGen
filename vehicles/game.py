"""game.py: one car of the roster into a game-ready pack (UVs, baked textures, LODs, collision).

    vehicles/blender.sh vehicles/game.py --car vanta_r [--out DIR] [--docs]
    vehicles/blender.sh vehicles/game.py --car vanta_r --test          # 1024 / 512, quick

The pack's format is the contract in vehicles/GAME.md. One run, one job under blender.sh's
lock:

1. builds the car in this Blender by running its own script (cars/<car>.py, unchanged) and
   renders the procedural original from its hero view;
2. turns its objects into parts (body, glass, a node per wheel, a brake node per wheel
   that has a caliper), each a single mesh in the car's frame, wheels about their axles;
3. bakes down what is wasteful in a game (lettering, ribbons and other flat relief always;
   dense arrays such as honeycombs onto cards; over the budget, taller relief such as bolt
   rows, dense tires rebuilt as lathes, then a collapse of the densest small parts) and
   removes faces nothing can see (inside the hull, coincident, the backs of merged solids);
4. unwraps an atlas per material slot (exterior favored over underside and cabin) and bakes
   the procedural materials in Cycles: the kept surfaces directly, the baked-down detail
   from the original objects onto the surface under it;
5. makes the LOD chain, the collision hulls and the light data, exports the glTF files,
   then (in the repo's venv Python, this same file) packs the textures, and in a fresh
   Blender loads the pack alone to render the proof, then checks the pack.

Blender side: stdlib and bpy only. Venv side (PIL, numpy): `python game.py post|check PACK`.
"""
import argparse
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import time
from math import acos, atan2, cos, pi, sin, sqrt

try:
    import bpy
    import bmesh
    from mathutils import Matrix, Vector as V3
    from mathutils.bvhtree import BVHTree
except ImportError:                                     # the venv side
    bpy = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "cybergen", "vehicles", "game")
FORMAT = "cybergen.vehicle_pack"
VERSION = 1
T0 = time.time()

# budgets and rules (GAME.md says why)
LOD_TRIS = (150000, 60000, 20000, 5000)
# the size class: a vehicle whose body has this much exterior (m2, after the unseen faces
# are removed: trucks, vans, the hauler class) is large: a larger far LOD, a lower floor
LARGE_EXTERIOR_M2 = 55.0
LOD_TRIS_LARGE = (150000, 60000, 20000, 8000)
FLAT_RELIEF_M = 0.0032          # relief this low is always baked onto the surface under it
RELIEF_ONE_SURFACE = 0.7       # a lamp is relief on one piece: this share of its points
TALL_RELIEF_M = 0.0125          # relief up to this tall is baked down when over the budget
CARD_DENSITY = 15000.0          # triangles per m2 of a dense array's outline: a card
CARD_MIN_TRIS = 1500
CARD_MIN_PARTS = 8
CARD_THICK_M = 0.045
TIRE_LATHE_TRIS = 6000          # a tire denser than this is rebuilt as a lathe (over budget)
TIRE_SEGMENTS = 64
WEIGHT = {0: 1.0, 1: 0.35, 2: 0.4, 3: 0.35, 4: 0.5}  # texel density by face class: exterior,
CLASS_NAMES = {0: "exterior", 1: "underside", 2: "cabin", 3: "lamp_in_gaps",  # ... (below),
               4: "rim_face"}                 # the far LODs' rim faces (rim_disc)
CAGE_M, REACH_M = 0.015, 0.035  # baking the detail: cage out, ray reach under the surface
TEXEL_FLOOR = {"body": 300.0, "wheels": 300.0}  # px/m on exterior faces at 4096 / 2048
TEXEL_FLOOR_LARGE = {"body": 240.0, "wheels": 240.0}  # ... for the large class (never under 220)
CORE_WHEEL = ("tire", "rim", "hub", "ring", "disc", "drum", "caliper")
DETAIL_BOOST = 2.0              # texel density under baked lettering and decals, at most
DETAIL_MARGIN = 1.03            # ... while the exterior's 5th percentile stays this over the floor
DETAIL_COST = 0.2               # ... and the atlas grows by this share at most (the rest shrinks)
DETAIL_FINE_UNDER = 1.25        # a boost under this goes to islands under fine relief:
DETAIL_FINE_PX = 4.0            # ... relief whose parts are under this many texels wide
OVER_SHARE = 0.2                # fine relief kept at LOD0: this share of the budget
OVER_ONLY_PX = 8.0              # ... with no image under it: parts this few texels long
THIN_PX = 2.0                   # texels across every island at least (2 area / perimeter)
THIN_COST = 0.1                 # ... while that grows the atlas by this share at most


DEBUG = bool(os.environ.get("CYBERGEN_GAME_DEBUG"))     # more in the log (the wrecks, one by one)


def log(msg):
    print("G %6.1f  %s" % (time.time() - T0, msg))
    sys.stdout.flush()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def venv_python():
    cands = [os.environ.get("CYBERGEN_PYTHON")]
    d = HERE
    for _ in range(8):
        d = os.path.dirname(d)
        cands.append(os.path.join(d, ".venv", "bin", "python"))
        cands.append(os.path.join(d, ".venv", "Scripts", "python.exe"))
    cands.append("/Users/swag/Projects/CyberGen/.venv/bin/python")
    return next((c for c in cands if c and os.path.exists(c)), None)


# =========================================================================================
# Blender side
# =========================================================================================
def blender_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="blender.sh vehicles/game.py")
    ap.add_argument("--car", help="a car of vehicles/cars/ (file name without .py)")
    ap.add_argument("--out", default=None, help="the pack's folder (default %s/<car>)" % CACHE)
    ap.add_argument("--body-size", type=int, default=4096)
    ap.add_argument("--wheel-size", type=int, default=2048)
    ap.add_argument("--lods", type=int, nargs=4, default=None,
                    help="triangle budgets (default by the size class)")
    ap.add_argument("--samples", type=float, default=1.0, help="bake and render samples scale")
    ap.add_argument("--test", action="store_true", help="1024 / 512 textures, few samples")
    ap.add_argument("--docs", action="store_true",
                    help="also write docs/progress/AG18/<car>/game.jpg and game_report.json")
    ap.add_argument("--views", default="", help="more views to compare, e.g. nose,tail,wheel")
    ap.add_argument("--keep-work", action="store_true", help="keep the raw bakes (work/)")
    ap.add_argument("--lods-only", action="store_true",
                    help="only the LODs again, from an earlier --keep-work run's LOD0")
    ap.add_argument("--proof", default=None, help=argparse.SUPPRESS)   # internal: PACK
    ap.add_argument("--proof-lods", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.proof is None and not a.car:
        ap.error("--car NAME is needed")
    if a.test:
        a.body_size, a.wheel_size = min(a.body_size, 1024), min(a.wheel_size, 512)
        a.samples = min(a.samples, 0.25)
    if a.car:
        a.out = os.path.abspath(a.out or os.path.join(CACHE, a.car))
    return a


# ---------------------------------------------------------------------------------------
# the car as designed
# ---------------------------------------------------------------------------------------
# A pack is the car parked and shut: a script that poses an opening part for its sheet (a
# taxi's sliding door) builds it closed when CYBERGEN_SHUT is set, and the scripts written
# before that convention by the variable of their own named here. (carkit.Group's poses are
# per view and never reach a pack.)
SHUT_ENV = {"tanager_cab": "CAB_SHUT"}


def build_car(car, out):
    """Runs the car's own script here (it empties the scene, builds, and with no render
    argument only counts), shut (SHUT_ENV), and returns the kit module it used."""
    script = os.path.join(HERE, "cars", car + ".py")
    if not os.path.exists(script):
        raise SystemExit("no car %s (%s)" % (car, script))
    saved = sys.argv
    sys.argv = [saved[0], "--", "--out", os.path.join(out, "build")]
    shut = ["CYBERGEN_SHUT"] + ([SHUT_ENV[car]] if car in SHUT_ENV else [])
    before = {k: os.environ.get(k) for k in shut}
    os.environ.update({k: "1" for k in shut})
    try:
        runpy.run_path(script, run_name="__main__")
    finally:
        sys.argv = saved
        for k, v in before.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return sys.modules["carkit"]


def cam_record(cam):
    d = cam.data
    return dict(matrix=[list(r) for r in cam.matrix_world], lens=d.lens, sensor=d.sensor_width,
                dof=bool(d.dof.use_dof), focus=d.dof.focus_distance, fstop=d.dof.aperture_fstop)


STUDIO_UNLIT_SHARE = 0.3        # a part a light skips when it skips this share of its area


def studio_record(K, pieces):
    """The studio as the car's own script set it up for the original's renders (a car may
    change the kit's lights, or keep a light off some of its objects by light linking: a
    soft box mirrored whole in a windshield): each light's energy and color, and the pack
    parts it does not light (those whose objects it skips hold STUDIO_UNLIT_SHARE of the
    part's area or more). The proof sets the same up, so it compares like with like."""
    area, obj_part = {}, {}
    for p in pieces:
        a = sum(f.area for f in p.me.polygons)
        node = p.part.replace(":", "_")
        obj_part.setdefault(p.ob.name, []).append((node, a))
        area[node] = area.get(node, 0.0) + a
    out = {}
    for ob in K.STUDIO.objects:
        row = {}
        if ob.type == 'LIGHT':
            row["energy"] = round(float(ob.data.energy), 4)
            row["color"] = [round(float(c), 4) for c in ob.data.color]
        ll = getattr(ob, "light_linking", None)
        rc = ll.receiver_collection if ll is not None else None
        if rc is not None:
            inside = {o.name for o in rc.all_objects}
            unlit = {}
            for name, lst in obj_part.items():
                if name not in inside:
                    for node, a in lst:
                        unlit[node] = unlit.get(node, 0.0) + a
            row["unlit"] = sorted(n for n, a in unlit.items()
                                  if a >= STUDIO_UNLIT_SHARE * area[n] and a > 0)
            log("studio: %s does not light %s" % (ob.name, row["unlit"]))
        if row:
            out[ob.name] = row
    return out


def render_views(K, names, res, samples, folder, prefix):
    """The car's own views (the kit's fit), each to folder/<prefix>_<view>.jpg; returns the
    cameras, so the baked pack is seen from exactly the same place."""
    cams = {}
    for name in names:
        if name not in K.VIEWS:
            log("no view %s on this car" % name)
            continue
        path = os.path.join(folder, "%s_%s.jpg" % (prefix, name))
        K.render_view(name, path, res, samples)
        cams[name] = cam_record(K.SCN.camera)
        cams[name]["no_floor"] = bool(K.VIEWS[name].get("no_floor"))
    return cams


# ---------------------------------------------------------------------------------------
# materials: what each one is, and its channels as emission for the bakes
# ---------------------------------------------------------------------------------------
def bsdf_of(m):
    if m is None or m.node_tree is None:
        return None
    return next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)


def out_of(m):
    nodes = [n for n in m.node_tree.nodes if n.type == 'OUTPUT_MATERIAL']
    return next((n for n in nodes if n.is_active_output), nodes[0] if nodes else None)


def src(sock):
    return sock.links[0].from_socket if sock.is_linked else None


def val(b, name, default):
    if b is None or name not in b.inputs:
        return default
    v = b.inputs[name].default_value
    try:
        return tuple(v)
    except TypeError:
        return v


def paint_nodes(m):
    """The kit's paint(): Base Color <- grime (multiply) <- dm (paint mixed with dust by
    the dust weight), grime's second color the crease factor. None if m is not one."""
    b = bsdf_of(m)
    if b is None:
        return None
    g = src(b.inputs["Base Color"])
    if g is None or g.node.type != 'MIX_RGB' or g.node.blend_type != 'MULTIPLY':
        return None
    dm = src(g.node.inputs["Color1"])
    if dm is None or dm.node.type != 'MIX_RGB' or not dm.node.inputs["Fac"].is_linked:
        return None
    return dict(grime=g.node, dm=dm.node, dust_w=src(dm.node.inputs["Fac"]),
                crease=src(g.node.inputs["Color2"]),
                color=tuple(dm.node.inputs["Color1"].default_value)[:3],
                dust=tuple(dm.node.inputs["Color2"].default_value)[:3])


LENS_MATS = ("lens", "optic")


class MatInfo:
    def __init__(self, m):
        self.m = m
        self.name = m.name
        b = bsdf_of(m)
        self.b = b
        self.glass = b is not None and not b.inputs["Transmission Weight"].is_linked and \
            b.inputs["Transmission Weight"].default_value >= 0.5
        # a lamp's lens or light guide sleeve (the kit's lens... and optic materials): left
        # out of the pack, so the lamp behind it is baked as it is seen through it
        self.lens = self.glass and m.name.startswith(LENS_MATS)
        es = val(b, "Emission Strength", 0.0)
        ec = val(b, "Emission Color", (0, 0, 0, 1))
        self.strength = es if b is not None and not b.inputs["Emission Strength"].is_linked else 0.0
        self.emit_color = ec[:3]
        self.emissive = self.strength > 0 and max(self.emit_color) > 0
        self.paint = paint_nodes(m)
        self.color = self.paint["color"] if self.paint else (
            val(b, "Base Color", (0.5, 0.5, 0.5, 1))[:3] if b is not None and
            not b.inputs["Base Color"].is_linked else None)
        self.channel = None             # 0 primary, 1 secondary, 2 accent (tintable)


def analyze_materials(K):
    """Every material of the car, and which tint channel each one follows: the kit's paint
    (R), paint2 (G), caliper (B), and any other material in exactly one of those colors."""
    infos = {m.name: MatInfo(m) for m in bpy.data.materials if m.node_tree is not None}
    ref = {}
    for ch, name in ((0, "paint"), (1, "paint2"), (2, "caliper")):
        if name in infos and infos[name].color is not None:
            ref[ch] = infos[name].color
    for mi in infos.values():
        if mi.glass or mi.emissive or mi.color is None:
            continue
        for ch, c in ref.items():
            if max(abs(a - b) for a, b in zip(mi.color, c)) < 2e-3:
                mi.channel = ch
                break
    return infos


MICRO_SCALE = 150.0     # a procedural texture finer than this (cells a meter) is below a texel


def strip_flake(infos):
    """Detail finer than a texel cannot be baked without aliasing: the paint's flake (a
    bump at 0.4 mm) is dropped and every texture finer than MICRO_SCALE (the carbon
    weave) gives its mean, 0.5. Both are left to the engine's detail maps; returns
    {material: [what]} for pack.json."""
    micro = {}
    for mi in infos.values():
        nt = mi.m.node_tree
        if mi.paint and mi.b.inputs["Normal"].is_linked:
            for l in list(mi.b.inputs["Normal"].links):
                nt.links.remove(l)
            micro.setdefault(mi.name, []).append("flake")
        for n in list(nt.nodes):
            if not n.type.startswith("TEX_") or "Scale" not in n.inputs or \
                    n.inputs["Scale"].is_linked or n.inputs["Scale"].default_value < MICRO_SCALE:
                continue
            links = [l for o in n.outputs for l in o.links]
            if not links:
                continue
            c = nt.nodes.new('ShaderNodeValue')
            c.outputs[0].default_value = 0.5
            for l in links:
                to = l.to_socket
                nt.links.remove(l)
                nt.links.new(c.outputs[0], to)
            micro.setdefault(mi.name, []).append("%s %.0f" % (n.type.lower()[4:],
                                                              n.inputs["Scale"].default_value))
    return micro


class Channels:
    """Emission rewiring of one material for the bakes. Each pass shows one thing as
    emission: BASE (what is not paint, and the dust and grime on the paint), TINT (the
    weights of the three tint channels), RMC (roughness, metallic, coat), SSE (the shade on
    the tinted color, specular level, coverage), EMIT (emission over the car's strongest)."""

    def __init__(self, mi, infos, emax, cover, low):
        self.mi = mi
        m = mi.m
        nt = m.node_tree
        self.nt = nt
        self.out = out_of(m)
        self.surface = src(self.out.inputs["Surface"])
        b = mi.b
        N = nt.nodes
        if low:                         # the joined parts keep each piece's object space
            for tc in [n for n in N if n.type == 'TEX_COORD']:
                for l in list(tc.outputs["Object"].links):
                    at = N.new('ShaderNodeAttribute')
                    at.attribute_type = 'GEOMETRY'
                    at.attribute_name = "cg_obj"
                    nt.links.new(at.outputs["Vector"], l.to_socket)
        self.E = N.new('ShaderNodeEmission')
        self.E.inputs["Strength"].default_value = 1.0
        self.src = {}

        def inp(name, default):
            if b is None or name not in b.inputs:
                return default
            s = b.inputs[name]
            if s.is_linked:
                return src(s)
            v = s.default_value
            try:
                return tuple(v)
            except TypeError:
                return float(v)

        def comb(r, g, bl):
            c = N.new('ShaderNodeCombineColor')
            for sock, v in zip(c.inputs, (r, g, bl)):
                if isinstance(v, (int, float)):
                    sock.default_value = float(v)
                else:
                    nt.links.new(v, sock)
            return c.outputs[0]

        def one_minus(s):
            n = N.new('ShaderNodeMath')
            n.operation = 'SUBTRACT'
            n.inputs[0].default_value = 1.0
            nt.links.new(s, n.inputs[1])
            return n.outputs[0]

        p = mi.paint
        if p is not None:
            mul = N.new('ShaderNodeMixRGB')
            mul.blend_type = 'MULTIPLY'
            mul.inputs["Fac"].default_value = 1.0
            mul.inputs["Color1"].default_value = (*p["dust"], 1.0)
            if p["crease"] is not None:
                nt.links.new(p["crease"], mul.inputs["Color2"])
            self.src["BASE"] = mul.outputs[0]
        else:
            self.src["BASE"] = inp("Base Color", (0.5, 0.5, 0.5, 1.0))
        w = [0.0, 0.0, 0.0]
        if mi.channel is not None:
            w[mi.channel] = one_minus(p["dust_w"]) if p is not None else 1.0
        self.src["TINT"] = comb(*w)
        self.src["RMC"] = comb(_f(inp("Roughness", 0.5)), _f(inp("Metallic", 0.0)),
                               _f(inp("Coat Weight", 0.0)))
        shade = 1.0
        if p is not None and mi.channel is not None and p["crease"] is not None:
            shade = p["crease"]
        self.src["SSE"] = comb(shade, _f(inp("Specular IOR Level", 0.5)), 1.0 if cover else 0.0)
        if mi.emissive and emax > 0:
            vm = N.new('ShaderNodeVectorMath')
            vm.operation = 'SCALE'
            vm.inputs[0].default_value = mi.emit_color
            # an emitter over the scale (cabin only) is clipped keeping its hue
            vm.inputs["Scale"].default_value = min(mi.strength / emax,
                                                   1.0 / max(max(mi.emit_color), 1.0))
            self.src["EMIT"] = vm.outputs[0]
        else:
            self.src["EMIT"] = (0.0, 0.0, 0.0, 1.0)
        self.img = N.new('ShaderNodeTexImage')
        nt.nodes.active = self.img

    def show(self, what):
        """what: a pass name, or None for the material as it is (NORMAL and AO bakes)."""
        L = self.nt.links
        for l in list(self.out.inputs["Surface"].links):
            L.remove(l)
        if what is None:
            if self.surface is not None:
                L.new(self.surface, self.out.inputs["Surface"])
            return
        s = self.src[what]
        ci = self.E.inputs["Color"]
        for l in list(ci.links):
            L.remove(l)
        if isinstance(s, (tuple, float)):
            s = s if isinstance(s, tuple) else (s, s, s, 1.0)
            ci.default_value = tuple(s[:3]) + (1.0,)
        else:
            L.new(s, ci)
        L.new(self.E.outputs[0], self.out.inputs["Surface"])


def _f(v):
    """A Principled input's value: a socket stays a socket, a value becomes a float."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, tuple):
        return float(v[0])
    return v


def slot_copy(m, slot, infos, emax):
    """A slot's own copy of a material (its own image node, object space read from the
    cg_obj attribute), with its emission channels."""
    cp = m.copy()
    cp.name = slot + "::" + m.name
    mi = MatInfo(cp)
    orig = infos.get(m.name)
    if orig is not None:
        mi.channel = orig.channel
    return cp, Channels(mi, infos, emax, False, True)


# ---------------------------------------------------------------------------------------
# pieces: every object split by material, evaluated, in the car's frame
# ---------------------------------------------------------------------------------------
class Piece:
    def __init__(self, name, ob, mat, me):
        self.name = name
        self.ob = ob                    # the original object (a bake source when replaced)
        self.mat = mat                  # material name
        self.me = me                    # bpy mesh in world space, attributes cg_obj, cg_n
        self.tris = sum(len(p.vertices) - 2 for p in me.polygons)
        self.part = "body"
        self.op = "keep"                # keep, relief, card, lathe, collapse
        self.over = False               # relief also kept as it is at LOD0 (fine_over)
        self.relief = None              # height over the surface under it, m
        self.panel = any(md.type == 'SOLIDIFY' for md in ob.modifiers)
        self.idx = -1


def piece_meshes(ob, dg):
    """The object's evaluated mesh split by material: [(material name, mesh)] in world
    space; cg_obj holds each vertex in the object's own space (what its materials read),
    cg_n each corner's normal in world space (the designs' custom normals)."""
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    if len(me.polygons) == 0:
        bpy.data.meshes.remove(me)
        return []
    M = ob.matrix_world.copy()
    nM = M.to_3x3().inverted_safe().transposed()
    co = [v.co.copy() for v in me.vertices]
    a = me.attributes.new("cg_obj", 'FLOAT_VECTOR', 'POINT')
    a.data.foreach_set("vector", [c for p in co for c in p])
    ns = [V3(n.vector) for n in me.corner_normals]
    me.transform(M)
    a = me.attributes.new("cg_n", 'FLOAT_VECTOR', 'CORNER')
    a.data.foreach_set("vector", [c for n in ns for c in (nM @ n).normalized()])
    for nm in [x.name for x in me.attributes if x.name not in
               ("cg_obj", "cg_n", "position", "sharp_face", "material_index") and
               not x.name.startswith(".")]:
        try:
            me.attributes.remove(me.attributes[nm])
        except Exception:
            pass
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    mats = [m.name if m else "void" for m in me.materials] or ["void"]
    idxs = sorted({p.material_index for p in me.polygons})
    out = []
    for i in idxs:
        if len(idxs) == 1:
            sub = me
        else:
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != i],
                             context='FACES')
            sub = bpy.data.meshes.new(me.name + "." + str(i))
            bm.to_mesh(sub)
            bm.free()
        sub.materials.clear()
        for p in sub.polygons:
            p.material_index = 0
        out.append((mats[min(i, len(mats) - 1)], sub))
    if len(idxs) > 1:
        bpy.data.meshes.remove(me)
    return out


def void_material():
    m = bpy.data.materials.get("void")
    if m is None:
        m = bpy.data.materials.new("void")
        m.use_nodes = True
        b = bsdf_of(m)
        b.inputs["Base Color"].default_value = (0.004, 0.004, 0.005, 1)
        b.inputs["Roughness"].default_value = 0.8
        b.inputs["Specular IOR Level"].default_value = 0.0
    return m


def axis_of(ob):
    return (ob.matrix_world.to_3x3() @ V3((0, 1, 0))).normalized()


def wheel_groups(objs, dg):
    """tire.<tag> objects that stand on the ground on a sideways axle, each with the
    objects named <kind>.<tag> sharing its origin: [(tag, pivot, [objects])]. A tire on a
    turned axle or off the ground (a spare) stays with the body."""
    out = []
    for t in objs:
        if not t.name.startswith("tire.") or t.type != 'MESH':
            continue
        tag = t.name[5:]
        piv = t.matrix_world.translation.copy()
        if abs(axis_of(t).y) < 0.98:
            continue
        zs = [(t.matrix_world @ V3(c)).z for c in t.bound_box]
        if min(zs) > 0.03:
            continue
        # (<kind>.<tag> with a kind of one word or more: cover.slots.<tag> too)
        mem = [o for o in objs if o.type == 'MESH' and o.name.endswith("." + tag) and
               (o.matrix_world.translation - piv).length < 1e-3]
        out.append((tag, piv, mem))
    return out


def gather(K, infos):
    dg = bpy.context.evaluated_depsgraph_get()
    objs = [o for o in K.CAR.objects if o.type in ('MESH', 'CURVE', 'FONT', 'SURFACE')
            and not o.hide_render]
    wheels = wheel_groups(objs, dg)
    member = {}
    for tag, piv, mem in wheels:
        for o in mem:
            member[o.name] = (tag, o.name.split(".", 1)[0])
    pieces = []
    lenses = 0
    for ob in objs:
        for mat, me in piece_meshes(ob, dg):
            if infos.get(mat) is not None and infos[mat].lens:
                bpy.data.meshes.remove(me)
                lenses += 1
                continue
            me.materials.append(bpy.data.materials.get(mat) or void_material())
            p = Piece("%s#%s" % (ob.name, mat), ob, mat, me)
            mi = infos.get(mat)
            if ob.name in member:
                tag, kind = member[ob.name]
                p.part = ("brake:" if kind == "caliper" else "wheel:") + tag
            elif mi is not None and mi.glass:
                p.part = "glass"
            pieces.append(p)
    for i, p in enumerate(pieces):
        p.idx = i
    if lenses:
        log("lenses left out: %d pieces (the lamps behind them are baked as seen)" % lenses)
    return pieces, wheels


# ---------------------------------------------------------------------------------------
# small geometry helpers (stdlib and mathutils)
# ---------------------------------------------------------------------------------------
def mesh_tris(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def loose_parts(bm):
    """Lists of faces connected by edges."""
    seen = set()
    parts = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, part = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            part.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        parts.append(part)
    return parts


def jacobi3(A):
    """Eigenvalues and eigenvectors (columns) of a symmetric 3 x 3 matrix (lists)."""
    a = [row[:] for row in A]
    v = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _ in range(60):
        p, q, big = 0, 1, 0.0
        for i in range(3):
            for j in range(i + 1, 3):
                if abs(a[i][j]) > big:
                    p, q, big = i, j, abs(a[i][j])
        if big < 1e-14:
            break
        th = 0.5 * atan2(2 * a[p][q], a[q][q] - a[p][p])
        c, s = cos(th), sin(th)
        for k in range(3):
            akp, akq = a[k][p], a[k][q]
            a[k][p], a[k][q] = c * akp - s * akq, s * akp + c * akq
        for k in range(3):
            apk, aqk = a[p][k], a[q][k]
            a[p][k], a[q][k] = c * apk - s * aqk, s * apk + c * aqk
        for k in range(3):
            vkp, vkq = v[k][p], v[k][q]
            v[k][p], v[k][q] = c * vkp - s * vkq, s * vkp + c * vkq
    return [a[i][i] for i in range(3)], [V3((v[0][i], v[1][i], v[2][i])) for i in range(3)]


def hull2d(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def poly_area2d(poly):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))) / 2


def rdp(pts, tol):
    """Douglas-Peucker on an open polyline of 2D points."""
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = sqrt(dx * dx + dy * dy) or 1e-12
    k, dm = 0, -1.0
    for i in range(1, len(pts) - 1):
        d = abs(dy * (pts[i][0] - a[0]) - dx * (pts[i][1] - a[1])) / L
        if d > dm:
            k, dm = i, d
    if dm <= tol:
        return [a, b]
    return rdp(pts[:k + 1], tol)[:-1] + rdp(pts[k:], tol)


def fib_dirs(n):
    """n directions over the sphere, mirror symmetric in y (so twin wheels match)."""
    half = []
    g = pi * (3 - sqrt(5))
    m = n // 2
    for i in range(m):
        z = 1 - 2 * (i + 0.5) / m
        r = sqrt(max(0.0, 1 - z * z))
        a = g * i
        x, y = r * cos(a), abs(r * sin(a))
        half.append(V3((x, y, z)))
    return half + [V3((d.x, -d.y, d.z)) for d in half]


def new_obj(name, me, coll):
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def join_meshes(name, meshes, coll):
    """One object from several meshes (all in one space), attributes kept."""
    obs = [new_obj(name + ".%d" % i, me, coll) for i, me in enumerate(meshes)]
    if len(obs) > 1:
        with bpy.context.temp_override(active_object=obs[0], object=obs[0],
                                       selected_objects=obs, selected_editable_objects=obs):
            bpy.ops.object.join()
    ob = obs[0]
    ob.name = name
    ob.data.name = name
    return ob


# ---------------------------------------------------------------------------------------
# baking down: relief, cards, lathes, collapse
# ---------------------------------------------------------------------------------------
def world_bvh(pieces):
    vs, ps, owner = [], [], []
    for p in pieces:
        o = len(vs)
        vs += [v.co.copy() for v in p.me.vertices]
        for poly in p.me.polygons:
            ps.append([o + i for i in poly.vertices])
            owner.append(p.idx)
    return BVHTree.FromPolygons(vs, ps), owner


def find_relief(pieces, lit=()):
    """Each piece's height over the surfaces of other pieces it lies on, when every one of
    its vertices is within TALL_RELIEF_M of another piece's surface."""
    tree, owner = world_bvh([p for p in pieces if p.part != "glass"])
    for p in pieces:
        if p.part == "glass" or p.panel or p.op != "keep":
            continue
        kind = p.ob.name.split(".", 1)[0]
        if p.part != "body" and kind in CORE_WHEEL:
            continue
        # its vertices and the middles of its faces and edges: a long bar whose vertices
        # all sit in its end plates is no relief
        pts = [v.co for v in p.me.vertices] + [f.center for f in p.me.polygons]
        vs = p.me.vertices
        pts += [(vs[e.vertices[0]].co + vs[e.vertices[1]].co) / 2 for e in p.me.edges]
        step = max(1, len(pts) // 4000)
        h = 0.0
        under = {}
        for co in pts[::step]:
            best = None
            for loc, nrm, i, d in tree.find_nearest_range(co, TALL_RELIEF_M):
                if owner[i] != p.idx and (best is None or d < best[0]):
                    best = (d, owner[i])
            if best is None:
                h = None
                break
            h = max(h, best[0])
            under[best[1]] = under.get(best[1], 0) + 1
        # a lamp is relief only on one surface: one whose points fall on many others (a
        # light band behind a row of flutes) would bake in patches; it stays as it is
        if h is not None and p.mat in lit and \
                max(under.values()) < RELIEF_ONE_SURFACE * sum(under.values()):
            log("  not relief: %s lies on %d pieces, %.0f%% on the most" % (
                p.name, len(under), 100 * max(under.values()) / sum(under.values())))
            h = None
        p.relief = h


def clusters_of(me):
    """Loose parts of a mesh grouped by nearness: [(faces' vertex lists, n parts, tris)]."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    parts = loose_parts(bm)
    boxes = []
    for part in parts:
        cs = [v.co for f in part for v in f.verts]
        boxes.append(([min(c[i] for c in cs) for i in range(3)],
                      [max(c[i] for c in cs) for i in range(3)]))
    n = len(parts)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    gap = 0.02
    order = sorted(range(n), key=lambda i: boxes[i][0][0])
    for a_i, i in enumerate(order):
        lo, hi = boxes[i]
        for j in order[a_i + 1:]:
            lo2, hi2 = boxes[j]
            if lo2[0] > hi[0] + gap:
                break
            if all(lo2[k] <= hi[k] + gap and lo[k] <= hi2[k] + gap for k in range(3)):
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = []
    for idxs in groups.values():
        pts = [v.co.copy() for i in idxs for f in parts[i] for v in f.verts]
        tris = sum(len(f.verts) - 2 for i in idxs for f in parts[i])
        out.append((pts, len(idxs), tris))
    bm.free()
    return out


def plane_of(pts):
    c = sum(pts, V3()) / len(pts)
    C = [[0.0] * 3 for _ in range(3)]
    step = max(1, len(pts) // 4000)
    for p in pts[::step]:
        d = p - c
        for i in range(3):
            for j in range(3):
                C[i][j] += d[i] * d[j]
    w, vecs = jacobi3(C)
    k = min(range(3), key=lambda i: w[i])
    return c, vecs[k].normalized()


def find_cards(pieces, tree_all, owner):
    """Dense arrays of small parts lying in a slab (honeycombs, mesh grilles): a flat card
    in the slab's back face replaces each, its look baked from the original."""
    pts_all = [v.co for q in pieces if q.part == "body" for v in list(q.me.vertices)[::50]]
    mid = V3([(min(x[k] for x in pts_all) + max(x[k] for x in pts_all)) / 2 for k in range(3)])
    cards = []
    for p in pieces:
        if p.part != "body" or p.panel or p.op != "keep" or p.tris < CARD_MIN_TRIS:
            continue
        mine = []
        others = None
        for pts, nparts, tris in clusters_of(p.me):
            if nparts < CARD_MIN_PARTS or tris < CARD_MIN_TRIS:
                continue
            c, n = plane_of(pts)
            ds = [(q - c).dot(n) for q in pts]
            thick = max(ds) - min(ds)
            u = n.orthogonal().normalized()
            v = n.cross(u).normalized()
            hull = hull2d([(round((q - c).dot(u), 5), round((q - c).dot(v), 5)) for q in pts])
            area = poly_area2d(hull)
            if area <= 0 or thick > CARD_THICK_M or tris / area < CARD_DENSITY:
                continue
            # outward: the side a ray from the slab's middle leaves the car on, cast at the
            # car without the array itself; a tie goes to the side away from the car's
            # middle
            if others is None:
                others = world_bvh([q for q in pieces if q.part == "body" and q is not p])[0]
            free = []
            for sgn in (1, -1):
                hit = others.ray_cast(c, n * sgn)
                free.append(1e9 if hit[0] is None else hit[3])
            if abs(free[0] - free[1]) < 1e-6:
                free = [(c - mid).dot(n), -(c - mid).dot(n)]
            if free[1] > free[0]:
                n, v = -n, -v
                ds = [-d for d in ds]
                hull = [(a, -b) for a, b in hull]
            # the card lies in the array's back face, so what stands inside the array's
            # depth (a plate, an exhaust in a hole) stays in front of it
            off = min(ds) + 0.001      # 1 mm inside: the back may lie flush on a wall
            ring = [c + n * off + u * a + v * b for a, b in hull]
            mine.append(dict(piece=p, ring=ring, normal=n, tris=tris, area=area,
                             thick=thick))
        if mine and sum(c["tris"] for c in mine) >= 0.9 * p.tris:
            cards += mine
    return cards


def card_mesh(card):
    me = bpy.data.meshes.new("card")
    ring = card["ring"]
    me.from_pydata([tuple(p) for p in ring], [], [list(range(len(ring)))])
    me.update()
    if me.polygons[0].normal.dot(card["normal"]) < 0:
        me.polygons[0].flip()
        me.update()
    a = me.attributes.new("cg_obj", 'FLOAT_VECTOR', 'POINT')
    a.data.foreach_set("vector", [c for p in ring for c in p])
    n = card["normal"]
    a = me.attributes.new("cg_n", 'FLOAT_VECTOR', 'CORNER')
    a.data.foreach_set("vector", [c for _ in me.loops for c in n])
    me.materials.append(void_material())
    return me


def lathe_mesh(p):
    """A tire rebuilt as a lathe of its outer envelope: the cross section's outline in
    (axial y, radius) around its middle, the deepest pockets and the letters left to the
    bake. Built in the tire's own space, then put where the tire is."""
    co = [V3(v.vector) for v in p.me.attributes["cg_obj"].data]
    yr = [(c.y, sqrt(c.x * c.x + c.z * c.z)) for c in co]
    y0, y1 = min(a for a, _ in yr), max(a for a, _ in yr)
    r0, r1 = min(b for _, b in yr), max(b for _, b in yr)
    yc, rc, hy, hr = (y0 + y1) / 2, (r0 + r1) / 2, (y1 - y0) / 2 or 1e-3, (r1 - r0) / 2 or 1e-3
    K_ = 256
    best = [None] * K_
    for y, r in yr:
        a, b = (y - yc) / hy, (r - rc) / hr
        k = int(((atan2(b, a) + pi) / (2 * pi)) * K_) % K_
        d = a * a + b * b
        if best[k] is None or d > best[k][0]:
            best[k] = (d, y, r)
    known = [k for k in range(K_) if best[k] is not None]
    prof = []
    for k in range(K_):
        if best[k] is not None:
            prof.append((best[k][1], best[k][2]))
            continue
        lo = max((j for j in known if j < k), default=known[-1] - K_)
        hi = min((j for j in known if j > k), default=known[0] + K_)
        t = (k - lo) / (hi - lo)
        A, B = best[lo % K_], best[hi % K_]
        prof.append((A[1] + (B[1] - A[1]) * t, A[2] + (B[2] - A[2]) * t))
    # start at the innermost point, simplify the closed outline
    s = min(range(K_), key=lambda i: prof[i][1])
    ring = prof[s:] + prof[:s]
    far = max(range(K_), key=lambda i: (ring[i][0] - ring[0][0]) ** 2 +
              (ring[i][1] - ring[0][1]) ** 2)
    ring = rdp(ring[:far + 1], 0.0006)[:-1] + rdp(ring[far:] + [ring[0]], 0.0006)[:-1]
    N = TIRE_SEGMENTS
    m = len(ring)
    verts, faces = [], []
    for k in range(N):
        a = 2 * pi * k / N
        for (y, r) in ring:
            verts.append((r * cos(a), y, r * sin(a)))
    for k in range(N):
        k2 = (k + 1) % N
        for j in range(m):
            j2 = (j + 1) % m
            faces.append((k * m + j, k * m + j2, k2 * m + j2, k2 * m + j))
    me = bpy.data.meshes.new("lathe")
    me.from_pydata(verts, [], faces)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    a = me.attributes.new("cg_obj", 'FLOAT_VECTOR', 'POINT')
    a.data.foreach_set("vector", [c for v in me.vertices for c in v.co])
    me.transform(p.ob.matrix_world)
    me.shade_smooth()
    me.set_sharp_from_angle(angle=0.6)
    a = me.attributes.new("cg_n", 'FLOAT_VECTOR', 'CORNER')
    a.data.foreach_set("vector", [c for n in me.corner_normals for c in n.vector])
    me.materials.append(p.me.materials[0])
    return me, len(ring)


def collapse_mesh(p, ratio):
    """The piece's mesh collapsed to ratio of its triangles (Blender's decimate), its
    attributes carried along by the collapse."""
    me = p.me.copy()
    ob = new_obj("tmp_collapse", me, bpy.context.scene.collection)
    md = ob.modifiers.new("dec", 'DECIMATE')
    md.decimate_type = 'COLLAPSE'
    md.ratio = ratio
    dg = bpy.context.evaluated_depsgraph_get()
    out = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True,
                                          depsgraph=dg)
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    out.shade_smooth()
    out.set_sharp_from_angle(angle=0.6)
    # its shading normals weighted by face area, as the designs' panels have them: a large
    # flat face keeps its own normal to its edges. Plain smooth normals leaned a flat
    # panel's corners toward its neighbors, the normal map baked from the original had to
    # bend them back, and the panel's triangles showed as a glossy zigzag
    ob = new_obj("tmp_weighted", out, bpy.context.scene.collection)
    md = ob.modifiers.new("wn", 'WEIGHTED_NORMAL')
    md.keep_sharp = True
    md.weight = 60
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    ns = [c for n in ev.data.corner_normals for c in n.vector]
    bpy.data.objects.remove(ob)
    if len(ns) != 3 * len(out.loops):
        ns = [c for n in out.corner_normals for c in n.vector]
    if "cg_n" in out.attributes:
        out.attributes.remove(out.attributes["cg_n"])
    a = out.attributes.new("cg_n", 'FLOAT_VECTOR', 'CORNER')
    a.data.foreach_set("vector", ns)
    return out


# ---------------------------------------------------------------------------------------
# parts: meshes joined, hidden faces removed
# ---------------------------------------------------------------------------------------
def find_twins(objs, wheels, lettered=()):
    """Wheels (and brakes) that are another wheel's mesh moved (on the same side: the six
    alike wheels of a truck) or mirrored (on the other side), vertex for vertex about their
    pivots: {twin key: source key}. A wheel with lettering baked onto it (tags in lettered)
    is never mirrored (its text would read backwards). A twin is made from its source
    after the UVs, so they share their texels. Sources are taken left side first, front to
    rear."""
    from collections import Counter
    twins = {}
    order = sorted(wheels, key=lambda w: (w[1].y <= 0, -w[1].x, w[0]))

    def key_of(va, piv, sy):
        return Counter((round(v.co.x - piv.x, 3), round((v.co.y - piv.y) * sy, 3),
                        round(v.co.z - piv.z, 3)) for v in va)
    for kind in ("wheel", "brake"):
        prim = []
        for tag, piv, mem in order:
            a = objs.get(kind + ":" + tag)
            if a is None:
                continue
            va = a.data.vertices
            found = None
            for tag2, piv2, b, kb in prim:
                if len(b.data.vertices) != len(va) or \
                        len(b.data.polygons) != len(a.data.polygons):
                    continue
                if abs(piv2.z - piv.z) > 1e-3:
                    continue
                mirror = (piv.y > 0) != (piv2.y > 0)
                if mirror and (tag in lettered or tag2 in lettered):
                    continue
                # the same points about the pivot (in any order: a mirrored bevel numbers
                # its vertices its own way), allowing a few to round the other way
                ka = key_of(va, piv, -1 if mirror else 1)
                if sum((ka & kb).values()) >= 0.98 * len(va):
                    found = tag2
                    break
            if found is not None:
                twins[kind + ":" + tag] = kind + ":" + found
            else:
                prim.append((tag, piv, a, key_of(va, piv, 1)))
    return twins


def tag_mesh(me, piece_idx):
    a = me.attributes.get("cg_piece") or me.attributes.new("cg_piece", 'INT', 'FACE')
    a.data.foreach_set("value", [piece_idx] * len(me.polygons))


def part_meshes(pieces, cards):
    """The low meshes of every part (world space): kept pieces as they are, replacements
    in place of what they replace. Returns {part: [(mesh, piece)]}."""
    out = {}
    for p in pieces:
        if p.op == "card_src" or (p.op == "relief" and not p.over):
            continue
        if p.op == "lathe":
            me = p.lathe
        elif p.op == "collapse":
            me = p.low
        else:
            me = p.me.copy()
        if p.op in ("lathe", "collapse"):
            me = me.copy()
        tag_mesh(me, p.idx)
        if p.over:
            a = me.attributes.new("cg_over", 'INT', 'FACE')
            a.data.foreach_set("value", [1] * len(me.polygons))
        out.setdefault(p.part, []).append((me, p))
    for k, c in enumerate(cards):
        me = card_mesh(c)
        tag_mesh(me, -2 - k)
        out.setdefault("body", []).append((me, c["piece"]))
    return out


def dedupe_faces(bm):
    """Coincident faces: one of two facing the same way is kept, two facing apart (the
    backs of solids merged face to face) both go."""
    seen = {}
    gone = set()
    for f in bm.faces:
        key = tuple(sorted((round(v.co.x, 4), round(v.co.y, 4), round(v.co.z, 4))
                           for v in f.verts))
        g = seen.get(key)
        if g is None:
            seen[key] = f
            continue
        if f.normal.dot(g.normal) > 0:
            gone.add(f)
        else:
            gone.add(f)
            gone.add(g)
    return list(gone)


DIRS = None
RANK = {-1: 0, 1: 1, 2: 2, 0: 3}    # face classes, worst to best seen


BELLY_EYE_M = 0.5       # under a floating vehicle: no eye looks up from lower than this
VIS_AGAIN_M2 = 0.002    # a face this large that no ray left is looked at again
VIS_AGAIN_DIRS = 600    # ... along this many directions (96 at first)


def visibility(bm, glass_tree, floats=False):
    """Face classes by rays: 0 seen from outside (exterior), 1 seen only from below
    (underside), 2 seen only through glass (cabin), 3 seen only in gaps (a large face found
    on the second, finer look), -1 never seen (removed). On a vehicle
    with no wheels (floats: it hovers, and sets down when parked) a ray going down counts
    as from below when it leaves a point under BELLY_EYE_M: its belly is underside, as a
    wheeled car's floor behind its sills and wheels (the texels go to what is seen). A face never
    seen from its front but seen from its back is a face the design turned the wrong way
    (Blender draws both sides; an engine culls back faces): its class from the back, and
    its index in the second list, to be turned round. So is a face seen better from its
    back than from its front (exterior over cabin over underside: a deck under the glass
    turned down, seen through the glass from above and through a gap from below)."""
    global DIRS
    if DIRS is None:
        DIRS = fib_dirs(96)
    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    cls, flip = [], []
    eps = 2e-4

    fine = fib_dirs(VIS_AGAIN_DIRS)

    def seen(samples, n, among=None):
        dirs = [n] + [d for d in (among or DIRS) if d.dot(n) > 0.12]
        best = -1
        for p in samples:
            o = p + n * eps
            for d in dirs:
                if tree.ray_cast(o, d)[0] is not None:
                    continue
                through = glass_tree is not None and glass_tree.ray_cast(o, d)[0] is not None
                below = d.z <= -0.3 or (floats and d.z < 0 and o.z < BELLY_EYE_M)
                k = 2 if through else (1 if below else 0)
                if best == -1 or (k == 0) or (k == 1 and best == 2):
                    best = k
                if best == 0:
                    return 0
        return best
    again = 0
    for f in bm.faces:
        n = f.normal
        if n.length < 0.5:
            cls.append(0)
            continue
        c = f.calc_center_median()
        samples = [c]
        if f.calc_area() > 2e-4:
            samples += [c.lerp(v.co, 0.85) for v in f.verts]
        best = seen(samples, n)
        if best != 0:
            back = seen(samples, -n)
            if RANK[back] > RANK[best]:
                best = back
                flip.append(f.index)
        if best == -1 and f.calc_area() > VIS_AGAIN_M2:
            # a large face no ray left: looked at again from more points along many more
            # directions (the back of a vent behind its louvres is seen only between the
            # slats, along their tilt; removed, the vent showed black and the pod's inside)
            vs = [v.co for v in f.verts]
            more = [c.lerp(v, t) for v in vs for t in (0.3, 0.6, 0.92)] + \
                [c.lerp((a + b) / 2, 0.7) for a, b in zip(vs, vs[1:] + vs[:1])]
            best = seen(more, n, fine)
            again += best != -1
            if best in (0, 1):
                best = 3            # seen only in gaps: kept, at that class's low weight
        cls.append(best)
    if again:
        log("  %d large faces seen only on a second, finer look (kept)" % again)
    return cls, flip


def cull(ob, glass_tree, lit=(), floats=False):
    """Removes coincident and never seen faces of a part, stores each face's class (FACE
    int cg_class). A lamp's faces (materials in lit) are never removed as unseen: a light
    band seen only through the gaps of a row of flutes catches too few of the rays.
    Returns (faces removed as coincident, as hidden)."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.normal_update()
    dup = dedupe_faces(bm) + [f for f in bm.faces if f.calc_area() < 1e-9]
    bmesh.ops.delete(bm, geom=list(set(dup)), context='FACES')
    bm.faces.ensure_lookup_table()
    cls, flip = visibility(bm, glass_tree, floats)
    if flip:
        fl = [bm.faces[i] for i in flip]
        bmesh.ops.reverse_faces(bm, faces=fl)
        ln = bm.loops.layers.float_vector.get("cg_n")
        if ln is not None:
            for f in fl:
                for l in f.loops:
                    l[ln] = -l[ln]
        log("  %s: %d faces seen only from behind turned round" % (ob.name, len(fl)))
    lay = bm.faces.layers.int.get("cg_class") or bm.faces.layers.int.new("cg_class")
    hidden = []
    mats = ob.data.materials
    lamp = {i for i, m in enumerate(mats) if m is not None and m.name in lit}
    for f, k in zip(bm.faces, cls):
        if k < 0 and f.material_index not in lamp:
            hidden.append(f)
        else:
            f[lay] = k if k >= 0 else 3     # a lamp no ray reached: seen only in gaps
    bmesh.ops.delete(bm, geom=hidden, context='FACES')
    bm.to_mesh(ob.data)
    bm.free()
    return len(dup), len(hidden)


def triangulate_low(ob):
    """A part's quads and larger faces cut into triangles, in place, before anything is
    baked on it: a tangent space normal map is only right on the triangles it was baked
    with, and a quad left to the bake, the exporter and the engine is cut by each as it
    likes. Where a flat panel carries slanted shading normals (a collapsed panel that keeps
    its bevels' normals) the other diagonal showed as a glossy zigzag across it. Returns
    how many faces were cut."""
    me = ob.data
    if all(len(p.vertices) == 3 for p in me.polygons):
        return 0
    bm = bmesh.new()
    bm.from_mesh(me)
    big = [f for f in bm.faces if len(f.verts) > 3]
    bmesh.ops.triangulate(bm, faces=big, quad_method='BEAUTY', ngon_method='BEAUTY')
    bm.to_mesh(me)
    bm.free()
    set_normals(me)
    return len(big)


def set_normals(me):
    if "cg_n" not in me.attributes:
        return
    a = me.attributes["cg_n"].data
    ns = [tuple(V3(x.vector).normalized()) for x in a]
    me.normals_split_custom_set(ns)


# ---------------------------------------------------------------------------------------
# UVs
# ---------------------------------------------------------------------------------------
def edit(ob):
    bpy.ops.object.mode_set(mode='OBJECT') if bpy.context.object and \
        bpy.context.object.mode != 'OBJECT' else None
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.reveal()
    bpy.ops.mesh.select_all(action='SELECT')


def fine_relief(relief, floor):
    """The relief pieces whose loose parts are narrow (the middle of their box's three
    sizes: a flute's or a slot's width, a small letter's) under DETAIL_FINE_PX texels at the
    floor's density, by their median."""
    return [p for p in relief if part_sizes(p)[0] * floor < DETAIL_FINE_PX]


def part_sizes(p):
    """A piece's loose parts by their boxes: the median of their middle size (a flute's or
    a slot's width, a letter's), and the largest of their largest (a flute's length, the
    tallest letter's height), in meters."""
    bm = bmesh.new()
    bm.from_mesh(p.me)
    bm.faces.ensure_lookup_table()
    mid, big = [], []
    for part in loose_parts(bm):
        cs = [v.co for f in part for v in f.verts]
        d = sorted(max(c[i] for c in cs) - min(c[i] for c in cs) for i in range(3))
        mid.append(d[1])
        big.append(d[2])
    bm.free()
    mid.sort()
    return (mid[len(mid) // 2], max(big)) if mid else (1e9, 1e9)


def under_tree(me):
    """A tree of a low mesh's faces without the relief kept at LOD0 over its baked image
    (cg_over: what lies under relief is the panel, never the relief's own copy), and each
    of its faces' index in the mesh."""
    a = me.attributes.get("cg_over")
    skip = [x.value for x in a.data] if a else None
    index = [p.index for p in me.polygons if not (skip and skip[p.index])]
    tree = BVHTree.FromPolygons([v.co for v in me.vertices],
                                [list(me.polygons[i].vertices) for i in index])
    return tree, index


def detail_faces(target, relief):
    """The faces of target (world space) right under baked-down relief: each point of a
    relief piece (vertices, face middles) marks the nearest face within reach."""
    if not relief:
        return set()
    tree, index = under_tree(target.data)
    out = set()
    for p in relief:
        pts = [v.co for v in p.me.vertices] + [f.center for f in p.me.polygons]
        for q in pts:
            hit = tree.find_nearest(q, TALL_RELIEF_M + 0.004)
            if hit[2] is not None:
                out.add(index[hit[2]])
    return out


def unwrap(ob, size, pad_px=None, boost=None, floor=None, thin=True, again=None, fine=None):
    """Smart projection, even texel density, islands scaled by face class (exterior over
    underside and cabin), packed into the unit square with pad_px between islands."""
    me = ob.data
    pad_px = pad_px or max(4, size // 512)          # 8 px between islands at 4096
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    edit(ob)
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.0, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    for k, faces in enumerate((again or [])[:len(UV_AGAIN_ANGLES)]):
        # the faces of islands that lay over themselves, projected again in smaller charts
        # (a second, a third and a fourth time, smaller still, those that still did)
        bpy.ops.mesh.select_all(action='DESELECT')
        bme = bmesh.from_edit_mesh(me)
        bme.faces.ensure_lookup_table()
        for i in faces:
            bme.faces[i].select_set(True)
        bme.select_flush_mode()
        bmesh.update_edit_mesh(me)
        log("  projected again: %d faces selected" % sum(1 for f in bme.faces if f.select))
        bpy.ops.uv.smart_project(angle_limit=UV_AGAIN_ANGLES[k], island_margin=0.0,
                                 area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    for faces in (again or [])[len(UV_AGAIN_ANGLES):]:
        # still over themselves at the smallest angle (layers that face one way and meet
        # at a vertex: no projection by direction parts them): each of those faces laid
        # flat in its own plane, an island of its own
        uvd = me.uv_layers.active.data
        for i in sorted(faces):
            poly = me.polygons[i]
            nrm = V3(poly.normal)
            if nrm.length < 0.5:
                continue
            e1 = nrm.orthogonal().normalized()
            e2 = nrm.cross(e1)
            for li, vi in zip(poly.loop_indices, poly.vertices):
                d_ = me.vertices[vi].co - poly.center
                uvd[li].uv = (d_.dot(e1), d_.dot(e2))
        log("  %d faces laid flat one by one" % len(faces))
    log("  smart projection %s: %s" % (ob.name, _uvbox(me)))
    from bpy_extras import mesh_utils
    islands = mesh_utils.mesh_linked_uv_islands(me)
    uv = me.uv_layers.active.data
    cls = me.attributes.get("cg_class")
    fc = [x.value for x in cls.data] if cls else [0] * len(me.polygons)
    U = [0.0] * (2 * len(uv))
    uv.foreach_get("uv", U)
    bad = sum(1 for u in U if u != u or abs(u) > 1e6)
    if bad:
        U = [0.0 if (u != u or abs(u) > 1e6) else u for u in U]
        log("  %d UV coordinates of degenerate faces were not numbers: set to 0" % bad)
    polys = me.polygons
    # every island to one texel density (a UV unit a meter), times its class's weight; an
    # island with no UV area (degenerate faces) is left as it is
    polys = me.polygons
    for isl in islands:
        w = max(WEIGHT.get(fc[i], 1.0) for i in isl)
        loops = [l for i in isl for l in polys[i].loop_indices]
        A3 = sum(polys[i].area for i in isl)
        Auv = 0.0
        for i in isl:
            ls = list(polys[i].loop_indices)
            Auv += abs(sum(U[2 * a] * U[2 * b + 1] - U[2 * b] * U[2 * a + 1]
                           for a, b in zip(ls, ls[1:] + ls[:1]))) / 2
        if Auv < 1e-12 or A3 < 1e-10:
            continue
        s = sqrt(A3 / Auv) * w
        cx = sum(U[2 * l] for l in loops) / len(loops)
        cy = sum(U[2 * l + 1] for l in loops) / len(loops)
        for l in loops:
            U[2 * l] = cx + (U[2 * l] - cx) * s
            U[2 * l + 1] = cy + (U[2 * l + 1] - cy) * s
    # whole islands: a seam cut round the detail across a flat panel would let the LODs'
    # collapse smear the texture along it
    boosted = [k for k, isl in enumerate(islands) if boost and any(i in boost for i in isl)]
    loops_of = [[l for i in isl for l in polys[i].loop_indices] for isl in islands]
    U0 = U
    U, fill = pack_uv(U0, loops_of, pad_px / size)
    f = 1.0
    if floor and thin:
        # 1. thin islands (a letter's strokes, a hairline lamp, a trim strip) thickened to
        # THIN_PX texels at least (2 area / perimeter), else they cover no texel center and
        # bake to nothing; up to 4 times, while it grows the atlas by THIN_COST at most
        A_k, t_k = island_thickness(me, islands, U)
        tot = sum(A_k) or 1.0
        g = [1.0] * len(islands)
        for T in (THIN_PX, THIN_PX * 0.75, THIN_PX * 0.5, 0.0):
            if T == 0.0:
                g = [1.0] * len(islands)
                break
            g = [min(4.0, T / (t * size)) if 0 < t * size < T else 1.0 for t in t_k]
            if sum(A * (x * x - 1) for A, x in zip(A_k, g)) <= THIN_COST * tot:
                break
        # 2. the islands under baked lettering and decals get more texels: DETAIL_BOOST times
        # the density, less where that would grow the atlas by more than DETAIL_COST or take
        # the exterior's 5th percentile under DETAIL_MARGIN over the floor (packed again,
        # measured, the boost halved until it holds)
        p5 = texel_p5(me, U, size)
        A_all = sum(polys[i].area * WEIGHT.get(fc[i], 1.0) ** 2 for isl in islands for i in isl)
        A_mark = sum(polys[i].area for k in boosted for i in islands[k])
        if p5 and A_mark > 0:
            grow = min(DETAIL_COST, (p5 / (floor * DETAIL_MARGIN)) ** 2 - 1)
            f = sqrt(max(1.0, min(DETAIL_BOOST ** 2, 1 + grow * A_all / A_mark)))
            if f < DETAIL_FINE_UNDER and fine:
                # the boost spread thin over large panels: it goes to the islands under
                # fine relief alone (flutes, slots, small lettering on the exterior), which
                # need it to bake as lines and letters
                only = [k for k in boosted if any(i in fine and fc[i] == 0 for i in islands[k])]
                A_fine = sum(polys[i].area for k in only for i in islands[k])
                if only and A_fine > 0:
                    f2 = sqrt(max(1.0, min(DETAIL_BOOST ** 2, 1 + grow * A_all / A_fine)))
                    log("  the boost of %.2f over %.2f m2 goes to the %d islands under fine "
                        "relief alone (%.2f m2): %.2f" % (f, A_mark, len(only), A_fine, f2))
                    boosted, A_mark, f = only, A_fine, f2
        mark = set(boosted)
        nthin = sum(1 for x in g if x > 1.0)
        for _ in range(5):
            sc = [max(gk, f if k in mark else 1.0) for k, gk in enumerate(g)]
            if max(sc) <= 1.0:
                break
            Ub = list(U0)
            for k, x in enumerate(sc):
                if x <= 1.0:
                    continue
                ls = loops_of[k]
                cx = sum(Ub[2 * l] for l in ls) / len(ls)
                cy = sum(Ub[2 * l + 1] for l in ls) / len(ls)
                for l in ls:
                    Ub[2 * l] = cx + (Ub[2 * l] - cx) * x
                    Ub[2 * l + 1] = cy + (Ub[2 * l + 1] - cy) * x
            U2, fill2 = pack_uv(Ub, loops_of, pad_px / size)
            p5b = texel_p5(me, U2, size)
            if p5b is not None and p5b >= floor * 1.01:
                U, fill = U2, fill2
                break
            if f > 1.05:
                f = 1 + (f - 1) / 2
            else:
                f, g, nthin = 1.0, [1.0] * len(islands), 0
        else:
            f, nthin = 1.0, 0
        log("  %d islands under baked detail (%.3f m2) at %.2f times the density; %d thin "
            "islands thickened" % (len(boosted), A_mark, f, nthin))
    uv.foreach_set("uv", U)
    me.update()
    log("  packed %s: %d islands, %.0f%% of the square, uv box %s" % (
        ob.name, len(islands), fill * 100, _uvbox(me)))
    ob["cg_detail_boost"] = f
    if len(again or []) <= len(UV_AGAIN_ANGLES):
        # an island the projection laid over itself (a lip curling under its frame within
        # the angle limit) is projected again in smaller charts; four times at most, and
        # what still lies over itself then is laid flat face by face
        lay = self_overlap(me, U, islands)
        if lay:
            n = len(again or [])
            log("  %d islands (%d faces) overlap themselves: %s" % (
                lay[0], len(lay[1]), "projected again at %.2f rad" % UV_AGAIN_ANGLES[n]
                if n < len(UV_AGAIN_ANGLES) else "laid flat face by face"))
            return unwrap(ob, size, pad_px, boost, floor, thin,
                          again=list(again or []) + [lay[1]], fine=fine)
    return len(islands)


UV_AGAIN_ANGLES = (0.6, 0.35, 0.2, 0.1)  # radians: the angle limits for islands that overlapped
UV_AGAIN_SHARE = 0.001          # ... when this share of the texels is covered twice


def self_overlap(me, U, islands, res=2048):
    """Islands whose triangles cover texels another triangle of the atlas covers too, when
    over UV_AGAIN_SHARE of the covered texels are covered twice: (count, their faces)."""
    import numpy as np
    lts = list(_loop_tris(me))
    if not lts:
        return None
    L = np.array([lt.loops[:] for lt in lts], np.int64)
    A = np.asarray(U, np.float64).reshape(-1, 2)
    T = A[L].copy()
    T[..., 1] = 1 - T[..., 1]
    cnt = raster_count(T, res)
    cov = int((cnt > 0).sum())
    if cov == 0 or (cnt > 1).sum() <= UV_AGAIN_SHARE * cov:
        return None
    c = np.clip((T.mean(1) * res).astype(int), 0, res - 1)
    hot = cnt[c[:, 1], c[:, 0]] > 1
    faces = {lts[i].polygon_index for i in np.nonzero(hot)[0]}
    owner = {}
    for k, isl in enumerate(islands):
        for i in isl:
            owner[i] = k
    ks = {owner[f] for f in faces if f in owner}
    return len(ks), {i for k in ks for i in islands[k]}


def island_thickness(me, islands, U):
    """Per island its UV area and its thickness, 2 area / perimeter (UV units)."""
    polys = me.polygons
    lv = [l.vertex_index for l in me.loops]
    A_k, t_k = [], []
    for isl in islands:
        A = 0.0
        edges = {}
        for i in isl:
            ls = list(polys[i].loop_indices)
            A += abs(sum(U[2 * a] * U[2 * b + 1] - U[2 * b] * U[2 * a + 1]
                         for a, b in zip(ls, ls[1:] + ls[:1]))) / 2
            for a, b in zip(ls, ls[1:] + ls[:1]):
                key = (min(lv[a], lv[b]), max(lv[a], lv[b]))
                e = edges.get(key)
                if e is None:
                    edges[key] = [1, sqrt((U[2 * a] - U[2 * b]) ** 2 +
                                          (U[2 * a + 1] - U[2 * b + 1]) ** 2)]
                else:
                    e[0] += 1
        per = sum(L for n, L in edges.values() if n == 1)
        A_k.append(A)
        t_k.append(2 * A / per if per > 0 else 0.0)
    return A_k, t_k


def texel_p5(me, U, size):
    """The exterior's 5th percentile px/m for UVs U (flat u, v pairs of every loop)."""
    rows = []
    cls = me.attributes.get("cg_class")
    for p in me.polygons:
        if cls is not None and cls.data[p.index].value != 0:
            continue
        A = p.area
        if A < 1e-8:
            continue
        ls = list(p.loop_indices)
        ua = abs(sum(U[2 * a] * U[2 * b + 1] - U[2 * b] * U[2 * a + 1]
                     for a, b in zip(ls, ls[1:] + ls[:1]))) / 2
        rows.append((sqrt(ua * size * size / A), A))
    if not rows:
        return None
    rows.sort()
    tot = sum(a for _, a in rows)
    acc = 0.0
    for d, a in rows:
        acc += a
        if acc >= 0.05 * tot:
            return d
    return rows[-1][0]


PAD_MIN = 0.25                  # the least pad, a share of the full pad (2 px at 4096)


def pack_uv(U, islands, pad):
    """Islands (lists of loop indices into U, flat u, v pairs) packed into the unit square
    at one common scale, the largest that fits: each turned to its smallest bounding
    rectangle (lying flat), then laid in shelves tallest first, pad between them.
    Returns (U, share of the square the islands' rectangles take)."""
    rects = []
    for loops in islands:
        pts = list({(U[2 * l], U[2 * l + 1]) for l in loops})
        hull = hull2d(pts) if len(pts) > 2 else pts
        best = None
        for i in range(max(1, len(hull))):
            a, b = hull[i], hull[(i + 1) % len(hull)]
            ang = atan2(b[1] - a[1], b[0] - a[0]) if hull else 0.0
            c, s = cos(-ang), sin(-ang)
            xs = [p[0] * c - p[1] * s for p in hull]
            ys = [p[0] * s + p[1] * c for p in hull]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if best is None or w * h < best[0] - 1e-15:
                best = (w * h, -ang, min(xs), min(ys), w, h)
        _, ang, x0, y0, w, h = best
        if h > w:                                   # lie flat: shelves of low rows
            ang += pi / 2
            c, s = cos(ang), sin(ang)
            xs = [p[0] * c - p[1] * s for p in hull]
            ys = [p[0] * s + p[1] * c for p in hull]
            x0, y0, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        rects.append([loops, ang, x0, y0, max(w, 1e-6), max(h, 1e-6)])
    order = sorted(range(len(rects)), key=lambda i: (-rects[i][5], -rects[i][4]))

    def gap(i, S):
        """The pad round island i at scale S: pad, but half the island's width for an
        island narrower than two pads (it is under a texel by the mip whose texels the
        full pad keeps apart), PAD_MIN of the pad at least."""
        return min(pad, max(pad * PAD_MIN, 0.5 * min(rects[i][4], rects[i][5]) * S))

    def skyline(S):
        """Bottom-left on a skyline: each rectangle where its top ends lowest; a rectangle
        that fits a gap a taller one left under the skyline goes there first (the waste
        map: gaps cut guillotine-wise, the best short side fit)."""
        sky = [[0.0, 1.0, 0.0]]                     # segments: x, width, height
        free = []                                   # gaps under the skyline: x, y, w, h
        tiny = pad
        pos = {}
        for i in order:
            g_ = gap(i, S)
            wi, hi = rects[i][4] * S + g_, rects[i][5] * S + g_
            fit = None
            for fi, (fx, fy, fw, fh) in enumerate(free):
                for rot, (w, h) in ((False, (wi, hi)), (True, (hi, wi))):
                    if w <= fw + 1e-12 and h <= fh + 1e-12:
                        side = min(fw - w, fh - h)
                        if fit is None or side < fit[0]:
                            fit = (side, fi, rot, w, h)
            if fit is not None:
                _, fi, rot, w, h = fit
                fx, fy, fw, fh = free.pop(fi)
                pos[i] = (fx, fy, rot)
                if fw - w > tiny:
                    free.append((fx + w, fy, fw - w, h if fw - w < fh - h else fh))
                if fh - h > tiny:
                    free.append((fx, fy + h, fw if fw - w < fh - h else w, fh - h))
                continue
            best = None
            for rot in (False, True):           # lying flat, or stood up where that fits lower
                w, h = wi, hi
                if rot:
                    w, h = h, w
                if w > 1 or h > 1:
                    continue
                for k in range(len(sky)):
                    x = sky[k][0]
                    if x + w > 1 + 1e-12:
                        break
                    y, j, reach = 0.0, k, x + w
                    while j < len(sky) and sky[j][0] < reach - 1e-12:
                        y = max(y, sky[j][2])
                        j += 1
                    if y + h <= 1 and (best is None or y + h < best[1] + best[4] - 1e-12):
                        best = (x, y, w, rot, h)
            if best is None:
                return None
            x, y, w, rot, h = best
            pos[i] = (x, y, rot)
            new = []
            for seg in sky:
                sx, sw, sy = seg
                if sx + sw <= x + 1e-12 or sx >= x + w - 1e-12:
                    new.append(seg)
                    continue
                a0, a1 = max(sx, x), min(sx + sw, x + w)
                if y - sy > tiny and a1 - a0 > tiny:
                    free.append((a0, sy, a1 - a0, y - sy))
                if sx < x:
                    new.append([sx, x - sx, sy])
                if sx + sw > x + w:
                    new.append([x + w, sx + sw - x - w, sy])
            new.append([x, w, y + h])
            new.sort(key=lambda s: s[0])
            merged = [new[0]]
            for seg in new[1:]:
                if abs(seg[2] - merged[-1][2]) < 1e-12:
                    merged[-1][1] += seg[1]
                else:
                    merged.append(seg)
            sky = merged
        return pos
    A_ = sum((r[4] + 0) * (r[5] + 0) for r in rects)
    lo, hi = sqrt(0.3 / A_), sqrt(1.0 / A_)
    while skyline(lo) is None and lo > 1e-9:
        lo *= 0.7
    for _ in range(12):
        mid = (lo + hi) / 2
        if skyline(mid) is not None:
            lo = mid
        else:
            hi = mid
    S = lo
    pos = skyline(S)
    used = 0.0
    out = list(U)
    for i, (loops, ang, x0, y0, w, h) in enumerate(rects):
        px, py, rot = pos[i]
        c, s = cos(ang), sin(ang)
        for l in loops:
            u, v = U[2 * l], U[2 * l + 1]
            a, b = (u * c - v * s - x0) * S, (u * s + v * c - y0) * S
            if rot:                                 # a quarter turn: (a, b) -> (b, w - a)
                a, b = b, w * S - a
            out[2 * l] = px + gap(i, S) / 2 + a
            out[2 * l + 1] = py + gap(i, S) / 2 + b
        used += (w * S) * (h * S)
    return out, used


def _uvbox(me):
    U = [0.0] * (2 * len(me.loops))
    me.uv_layers.active.data.foreach_get("uv", U)
    xs, ys = U[0::2], U[1::2]
    z = 0
    for p in me.polygons:
        ls = list(p.loop_indices)
        a = abs(sum(U[2 * i] * U[2 * j + 1] - U[2 * j] * U[2 * i + 1]
                    for i, j in zip(ls, ls[1:] + ls[:1])))
        z += a < 1e-14
    return [round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3),
            "zero-area %d of %d" % (z, len(me.polygons))]


def texel_stats(ob, size):
    """px/m per face class, area weighted: median and 5th percentile."""
    me = ob.data
    n = len(me.polygons)
    U = [0.0] * (2 * len(me.loops))
    me.uv_layers.active.data.foreach_get("uv", U)
    ls0, lt, ar = [0] * n, [0] * n, [0.0] * n
    me.polygons.foreach_get("loop_start", ls0)
    me.polygons.foreach_get("loop_total", lt)
    me.polygons.foreach_get("area", ar)
    cls = me.attributes.get("cg_class")
    fc = [0] * n
    if cls is not None:
        cls.data.foreach_get("value", fc)
    rows = {}
    for i in range(n):
        A = ar[i]
        if A < 1e-8:
            continue
        ls = range(ls0[i], ls0[i] + lt[i])
        ls2 = list(ls[1:]) + [ls[0]]
        ua = abs(sum(U[2 * a] * U[2 * b + 1] - U[2 * b] * U[2 * a + 1]
                     for a, b in zip(ls, ls2))) / 2
        rows.setdefault(fc[i], []).append((sqrt(ua * size * size / A), A))
    out = {}
    for k, r in rows.items():
        r.sort()
        tot = sum(a for _, a in r)
        acc, p5, med = 0.0, None, None
        for d, a in r:
            acc += a
            if p5 is None and acc >= 0.05 * tot:
                p5 = d
            if med is None and acc >= 0.5 * tot:
                med = d
        out[CLASS_NAMES.get(k, str(k))] = dict(area_m2=round(tot, 3), p5=round(p5, 1),
                                                median=round(med, 1))
    return out


DISC_PIECE = -2000              # the pieces of the rim discs (-2000 - the wheel's index)
DISC_CLASS = 4                  # their face class (texel weight WEIGHT[4])
DISC_SEGS = 48
DISC_LIFT_M = 0.003             # the disc stands this far outside the wheel's outermost point
DISC_CAGE_M = 0.002


def rim_disc(ob, i):
    """The far LODs' rim face of a wheel node (its mesh about its pivot, placed at it): a
    flat disc of the tire's bead radius on the wheel's outside, just outside its outermost
    point, in the car's frame, faces of piece DISC_PIECE - i and class DISC_CLASS; it is
    unwrapped with the wheels and baked from the wheel's objects along the axle (what the
    wheel shows from the side). Returns (mesh, ray reach) or None (no tire)."""
    tire = tire_of(ob)
    if tire is None:
        return None
    rt = tire[1]
    side = 1 if ob.location.y > 0 else -1
    ys = [v.co.y * side for v in ob.data.vertices]
    y = max(ys) + DISC_LIFT_M
    reach = y - min(ys) + 0.01
    t = ob.location
    bm = bmesh.new()
    mid = bm.verts.new((t.x, t.y + side * y, t.z))
    ring = [bm.verts.new((t.x + rt * cos(2 * pi * k / DISC_SEGS), t.y + side * y,
                          t.z + rt * sin(2 * pi * k / DISC_SEGS))) for k in range(DISC_SEGS)]
    fs = [bm.faces.new((ring[k], ring[(k + 1) % DISC_SEGS], mid)) for k in range(DISC_SEGS)]
    bm.normal_update()
    flip = [f for f in fs if f.normal.y * side < 0]
    if flip:
        bmesh.ops.reverse_faces(bm, faces=flip)
    me = bpy.data.meshes.new("rim_disc_%d" % i)
    bm.to_mesh(me)
    bm.free()
    if ob.data.materials:       # one of the wheel's (a slot with the bake's image node)
        me.materials.append(ob.data.materials[0])
    me.attributes.new("cg_piece", 'INT', 'FACE').data.foreach_set(
        "value", [DISC_PIECE - i] * len(me.polygons))
    me.attributes.new("cg_class", 'INT', 'FACE').data.foreach_set(
        "value", [DISC_CLASS] * len(me.polygons))
    return me, reach


def split_discs(wheel_bake, prim, coll, reach):
    """After the wheels' unwrap: each rim disc's UVs as an affine map of the wheel's own
    (x, z) (the node mesh's cg_disc_uv: u = a x + b z + c, v = d x + e z + f; a mirrored
    twin shares it), the discs taken out of wheel_bake into an object of their own (the
    target of their bake). Returns that object or None."""
    me = wheel_bake.data
    pa = me.attributes.get("cg_piece")
    if pa is None:
        return None
    pv = [x.value for x in pa.data]
    uv = me.uv_layers.active.data
    disc = [p for p in me.polygons if pv[p.index] <= DISC_PIECE]
    if not disc:
        return None
    rows = {}
    for p in disc:
        i = DISC_PIECE - pv[p.index]
        t = prim[i].location
        for li in p.loop_indices:
            q = me.vertices[me.loops[li].vertex_index].co
            rows.setdefault(i, []).append((q.x - t.x, q.z - t.z, uv[li].uv[0], uv[li].uv[1]))
    for i, r in rows.items():
        M = Matrix(((0.0,) * 3, (0.0,) * 3, (0.0,) * 3))
        bu, bv = V3((0, 0, 0)), V3((0, 0, 0))
        for x, z, u, v in r:
            a = V3((x, z, 1.0))
            for j in range(3):
                for k in range(3):
                    M[j][k] += a[j] * a[k]
            bu += a * u
            bv += a * v
        Mi = M.inverted()
        cu, cv = Mi @ bu, Mi @ bv
        prim[i].data["cg_disc_uv"] = [cu[0], cu[1], cu[2], cv[0], cv[1], cv[2]]
    dme = me.copy()
    for dst, keep in ((dme, True), (me, False)):
        bm = bmesh.new()
        bm.from_mesh(dst)
        lay = bm.faces.layers.int.get("cg_piece")
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if (f[lay] <= DISC_PIECE) != keep],
                         context='FACES')
        bm.to_mesh(dst)
        bm.free()
    ob = new_obj("LOW_rim_discs", dme, coll)
    ob.matrix_world = wheel_bake.matrix_world
    log("  rim discs: %d, their faces baked along the axle (reach %.2f m)" % (len(rows), reach))
    return ob


def mirror_copy(src_ob, name, coll):
    """The left wheel's final mesh mirrored to the right (y negated): the same UVs, so a
    pair shares its texels."""
    me = src_ob.data.copy()
    bm = bmesh.new()
    bm.from_mesh(me)
    for v in bm.verts:
        v.co.y = -v.co.y
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    lay = bm.loops.layers.float_vector.get("cg_n")
    if lay is not None:
        for f in bm.faces:
            for l in f.loops:
                n = l[lay]
                l[lay] = V3((n.x, -n.y, n.z))
    bm.to_mesh(me)
    bm.free()
    ob = new_obj(name, me, coll)
    t = src_ob.location.copy()
    ob.location = (t.x, -t.y, t.z)
    return ob


# ---------------------------------------------------------------------------------------
# bakes
# ---------------------------------------------------------------------------------------
PASSES = ("BASE", "TINT", "RMC", "SSE", "EMIT", "NORMAL", "AO")
SRGB = ("BASE", "EMIT")


def make_image(name, size, srgb):
    img = bpy.data.images.new(name, size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    img.generated_color = (0, 0, 0, 0)
    return img


def layer_coll(name):
    def walk(lc):
        if lc.collection.name == name:
            return lc
        for c in lc.children:
            r = walk(c)
            if r:
                return r
    return walk(bpy.context.view_layer.layer_collection)


def select(objs, active):
    bpy.context.view_layer.update()
    for o in bpy.data.objects:
        try:
            o.select_set(False)
        except RuntimeError:
            pass                                        # not in the view layer
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def ray_vis(objs, on):
    for o in objs:
        for k in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission",
                  "visible_volume_scatter", "visible_shadow"):
            setattr(o, k, on)


def bake_slot(slot, targets, receiver, sources, chans_low, chans_src, size, work, samples,
              K, low_coll, hide, extra=None):
    """Pass A: each target's own surface, its materials as they are, against the low parts.
    Pass B: the baked-down detail, from the original objects (sources) onto the receiver
    (the faces under it), against the original car; with extra (an object, its sources,
    their channels, a ray reach: the rim discs), that too, into the same images, its rays
    from just outside it along its normals up to the reach. hide: objects out of both
    (glass, the other copies of the targets). Every pass a PNG in work/:
    <slot>_<A|B>_<pass>.png."""
    scn = bpy.context.scene
    car_lc, st_lc = layer_coll(K.CAR.name), layer_coll(K.STUDIO.name)
    st_lc.exclude = True
    for g in hide:
        g.hide_render = True
    scn.render.bake.normal_space = 'TANGENT'
    scn.render.bake.normal_r, scn.render.bake.normal_g, scn.render.bake.normal_b = \
        'POS_X', 'POS_Y', 'POS_Z'
    scn.world.light_settings.distance = 0.3
    files = {}
    for side in ("A", "B"):
        jobs = [(targets, targets)]
        if side == "B":
            jobs = [([receiver], [receiver] + sources)] if receiver is not None and sources \
                else []
            if extra is not None:
                jobs.append(([extra[0]], [extra[0]] + extra[1]))
            if not jobs:
                break
        car_lc.exclude = side == "A"
        if receiver is not None:
            receiver.hide_render = side == "A"
        if extra is not None:
            extra[0].hide_render = side == "A"
        ray_vis(low_coll.objects, side == "A")
        more = extra[2] if side == "B" and extra is not None else []
        for ps in PASSES:
            img = make_image("%s_%s_%s" % (slot, side, ps), size, ps in SRGB)
            for c in chans_low:
                c.img.image = img
                c.nt.nodes.active = c.img
            what = None if ps in ("NORMAL", "AO") else ps
            for c in chans_low + (chans_src if side == "B" else []) + more:
                c.show(what)
            n = {"NORMAL": 4, "AO": 64}.get(ps, 16)
            scn.cycles.samples = max(1, int(n * samples))
            t = time.time()
            for j, (tgt, sel) in enumerate(jobs):
                select(sel, tgt[0])
                kw = dict(type='EMIT' if what else ps, margin=0 if side == "B" else
                          max(2, size // 512), margin_type='EXTEND', use_clear=False,
                          target='IMAGE_TEXTURES', use_selected_to_active=side == "B")
                if side == "B" and extra is not None and tgt[0] is extra[0]:
                    kw.update(cage_extrusion=DISC_CAGE_M,
                              max_ray_distance=DISC_CAGE_M + extra[3])
                elif side == "B":
                    kw.update(cage_extrusion=CAGE_M, max_ray_distance=CAGE_M + REACH_M)
                if ps == PASSES[0] or j > 0:
                    # the first bake after the scene changes writes nothing (Blender 5.2):
                    # it only primes the bake, the second is the real one
                    bpy.ops.object.bake(**kw)
                bpy.ops.object.bake(**kw)
            path = os.path.join(work, "%s_%s_%s.png" % (slot, side, ps))
            img.filepath_raw = path
            img.file_format = 'PNG'
            img.save()
            files[(side, ps)] = path
            log("  baked %s %s %s at %d, %d samples, %.1f s" % (slot, side, ps, size,
                                                                scn.cycles.samples,
                                                                time.time() - t))
            bpy.data.images.remove(img)
        for c in chans_low + chans_src + more:
            c.show(None)
    ray_vis(low_coll.objects, True)
    if extra is not None:
        extra[0].hide_render = False
    car_lc.exclude = False
    st_lc.exclude = False
    for g in hide:
        g.hide_render = False
    return files


# ---------------------------------------------------------------------------------------
# collision, lights
# ---------------------------------------------------------------------------------------
def support_hull(pts, n_dirs=128):
    """A convex hull of at most n_dirs corners: the farthest points along many directions
    (game engines want few corners a hull)."""
    if len(pts) < 4:
        return None
    ds = fib_dirs(n_dirs)
    keep = {}
    for d in ds:
        i = max(range(len(pts)), key=lambda k: pts[k].dot(d))
        keep[i] = pts[i]
    bm = bmesh.new()
    for p in keep.values():
        bm.verts.new(p)
    try:
        r = bmesh.ops.convex_hull(bm, input=bm.verts[:])
    except Exception:
        bm.free()
        return None
    gone = {g for g in r["geom_interior"] + r["geom_unused"] if isinstance(g, bmesh.types.BMVert)}
    bmesh.ops.delete(bm, geom=list(gone), context='VERTS')
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new("hull")
    bm.to_mesh(me)
    bm.free()
    return me


def collision(obs):
    """Convex hulls along the car: slabs along x, each split at its beltline (the highest
    height where it is still most of its widest) when what stands above is narrower."""
    pts = []
    for ob in obs:
        M = ob.matrix_world
        pts += [M @ v.co for v in ob.data.vertices]
    if not pts:
        return []
    x0, x1 = min(p.x for p in pts), max(p.x for p in pts)
    L = x1 - x0
    ns = max(3, min(6, int(round(L / 0.95))))
    hulls = []
    for k in range(ns):
        a, b = x0 + L * k / ns, x0 + L * (k + 1) / ns
        pad = 0.02
        sl = [p for p in pts if a - pad <= p.x <= b + pad]
        if len(sl) < 8:
            continue
        z0, z1 = min(p.z for p in sl), max(p.z for p in sl)
        nb = 24
        wid = [0.0] * nb
        for p in sl:
            i = min(nb - 1, int((p.z - z0) / max(z1 - z0, 1e-6) * nb))
            wid[i] = max(wid[i], abs(p.y))
        wmax = max(wid)
        top = max(i for i in range(nb) if wid[i] >= 0.85 * wmax)
        zb = z0 + (z1 - z0) * (top + 1) / nb
        upper = [p for p in sl if p.z >= zb - 0.03]
        above = [p for p in sl if p.z > zb + 0.05]
        split = (z1 - zb) > 0.12 and len(above) > 8 and \
            max(abs(p.y) for p in above) < 0.9 * wmax
        groups = [[p for p in sl if p.z <= zb + 0.03], upper] if split else [sl]
        for g in groups:
            me = support_hull(g)
            if me is not None:
                hulls.append(me)
    return hulls[:12]


ROLE = {"led_front": "head", "led_rear": "tail", "led_accent": "marker", "led_wheel": "wheel",
        "screen": "cabin", "lamp": "lamp", "ember": "glow"}


def lights_of(pieces, infos):
    """Every emissive surface as data: grouped into lamps (parts closer than 3 cm), each
    with its middle, size, facing, area, color and strength."""
    out = []
    for p in pieces:
        mi = infos.get(p.mat)
        if mi is None or not mi.emissive:
            continue
        bm = bmesh.new()
        bm.from_mesh(p.me)
        bm.normal_update()
        parts = loose_parts(bm)
        groups = []
        for part in parts:
            cs = [v.co.copy() for f in part for v in f.verts]
            lo = V3([min(c[i] for c in cs) for i in range(3)])
            hi = V3([max(c[i] for c in cs) for i in range(3)])
            area = sum(f.calc_area() for f in part)
            nrm = sum((f.normal * f.calc_area() for f in part), V3())
            cen = sum((f.calc_center_median() * f.calc_area() for f in part), V3())
            for g in groups:
                if all(lo[i] <= g["hi"][i] + 0.03 and g["lo"][i] <= hi[i] + 0.03
                       for i in range(3)):
                    g["lo"] = V3([min(g["lo"][i], lo[i]) for i in range(3)])
                    g["hi"] = V3([max(g["hi"][i], hi[i]) for i in range(3)])
                    g["area"] += area
                    g["n"] += nrm
                    g["c"] += cen
                    break
            else:
                groups.append(dict(lo=lo, hi=hi, area=area, n=nrm, c=cen))
        bm.free()
        for g in groups:
            if g["area"] <= 0:
                continue
            c = g["c"] / g["area"]
            role = ROLE.get(p.mat, "emitter")
            if p.part.startswith("wheel:"):
                role = "wheel"
            out.append(dict(
                name=p.ob.name, part=p.part.split(":")[0], material=p.mat, role=role,
                position=[round(x, 4) for x in c], size=[round(g["hi"][i] - g["lo"][i], 4)
                                                         for i in range(3)],
                facing=[round(x, 3) for x in (g["n"].normalized() if g["n"].length > 1e-9
                                              else V3((0, 0, 0)))],
                area_m2=round(g["area"], 5), color=[round(x, 4) for x in mi.emit_color],
                strength=round(mi.strength, 3)))
    out.sort(key=lambda d: (d["role"], -d["position"][0], -d["position"][1], d["position"][2]))
    return out


# ---------------------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------------------
def final_material(name):
    m = bpy.data.materials.get("pack_" + name) or bpy.data.materials.new("pack_" + name)
    return m


def single_slot(ob, matname):
    me = ob.data
    for p in me.polygons:
        p.material_index = 0
    me.materials.clear()
    me.materials.append(final_material(matname))


def strip_attrs(me):
    for nm in [a.name for a in me.attributes if a.name.startswith("cg_")]:
        me.attributes.remove(me.attributes[nm])


def export_glb(path, objs, names):
    """objs under one empty "car" at the origin, each named as given, written as GLB with
    normals, tangents and one UV set; no images (the pack's PNGs are the textures)."""
    root = bpy.data.objects.new("car", None)
    bpy.context.scene.collection.objects.link(root)
    saved = []
    for ob, nm in zip(objs, names):
        saved.append((ob, ob.name, ob.data.name))
        other = bpy.data.objects.get(nm)
        if other is not None and other not in objs:
            other.name = "orig_" + nm                   # a design object of that name
    for ob, nm in zip(objs, names):
        ob.name = "tmpx_" + nm
    for ob, nm in zip(objs, names):
        ob.name = nm
        ob.data.name = nm
        ob.parent = root
    select(objs + [root], root)
    kw = dict(filepath=path, export_format='GLB', use_selection=True, export_apply=False,
              export_tangents=True, export_normals=True, export_texcoords=True,
              export_image_format='NONE', export_materials='EXPORT', export_yup=True,
              export_animations=False, export_extras=False)
    try:
        kw["export_vertex_color"] = 'NONE'
        bpy.ops.export_scene.gltf(**kw)
    except TypeError:
        kw.pop("export_vertex_color")
        bpy.ops.export_scene.gltf(**kw)
    for ob, nm, dn in saved:
        ob.parent = None
        ob.name = "tmpy_" + nm
    for ob, nm, dn in saved:
        ob.name = nm
        ob.data.name = dn
    bpy.data.objects.remove(root)


def world_box(obs):
    """The box of the faces of objects placed by location alone (matrix_world is stale on
    new ones; a vertex no face uses is not exported)."""
    pts = []
    for o in obs:
        vs = o.data.vertices
        used = {i for poly in o.data.polygons for i in poly.vertices}
        t = o.location
        pts += [(vs[i].co.x + t.x, vs[i].co.y + t.y, vs[i].co.z + t.z) for i in used]
    lo = [min(q[i] for q in pts) for i in range(3)]
    hi = [max(q[i] for q in pts) for i in range(3)]
    return lo, hi


# ---------------------------------------------------------------------------------------
# LODs
# ---------------------------------------------------------------------------------------
LOD_PLANAR_DEG = {1: 0.5, 2: 1.0, 3: 2.0}  # faces this close to coplanar merged first
LOD_SMALL_M = {2: 0.05, 3: 0.12}           # parts no larger than this left out (lamps kept)
LOD_SMALL_M2 = {3: 0.02}                    # ... and parts with no more area than this
LOD_STARVED = 0.03                          # a far LOD collapsed under this ratio: starved
LOD_STARVED_SCALES = (2.0, 3.0)             # ... again, small parts this much larger left out
SMALL_SCALE = [1.0]
LOD_SLENDER_M = 0.05                        # ... unless slender (a cable: two sides this thin)
LOD_BOX_KEEP_M = 0.01                       # ... never one within this of the box's sides
LOD_PART_FROM = 3                           # small parts judged as loose parts, not pieces
LOD_FLOAT_FROM = 3                          # small parts left floating by those left out too
LOD_TOUCH_M = 0.004                         # ... pieces this close touch
LOD_TOUCH_SAMPLES = 300                     # ... vertices of a piece tried
LOD_FLOOR = {2: (8, 150.0, 0.5), 3: (6, 120.0, 0.25)}  # a piece keeps a + b x its area (m2)
#                                             triangles, a lamp c of its own
LOD_WHEEL_LATHE = 3                         # wheels are lathes from this LOD on
LOD_WHEEL_MADE = 3                          # ... and the whole wheel a tube and a disc
LOD_OPAQUE_FROM = 3                         # faces not seen with the glass opaque left out
LOD_WELD_FROM = 3                           # pieces welded where their vertices meet
LOD_WELD_M = 0.0015
LOD_LATHE_SEGS = 20
LOD_WRECK_FROM = 3                          # wrecked pieces put right (stand_ins)
LOD_WRECK_M = 0.01                          # ... off their shape by more than this
LOD_WRECK_SHARE = 0.12                      # ... or this share of their size
LOD_STANDIN_M = 0.6                         # ... a hull or gone up to this size
LOD_HULL_DIRS = 26
LOD_HULL_DIRS_LARGE = 96                    # ... a larger part's second try
LOD_PIECE_HULL_PARTS = 6                    # a piece of this many loose parts: one hull
LOD_PIECE_HULL_FILL = 0.35                  # ... whose parts' own hulls fill this share
LOD_HULL_NORMAL = 0.866                     # a hull face takes LOD0's normal within 30 degrees
LOD_HULL_SHARE = 0.2                       # ... the hulls' extra triangles, a share of the LOD
LOD_HULL_LARGE_M = 0.03                     # ... a larger part's hull this close to it
LOD_WRECK_LARGE = 0.02                      # ... a larger part off by this share of its size
LOD_WRECK_MORE = 2.0                        # ... a larger one collapsed again at 3 times
LOD_LATHE_SHARP = 0.6                       # radians
LATHE_PIECE = -1000                         # the piece of a far LOD's tire tube
LOD_GLASS_ITER = 4
LOD_COARSE_SHARE = 0.1                      # glass this share of corners 15 deg off: coarse
LOD_GLASS_SHARE = {1: 0.3, 2: 0.3, 3: 0.2}  # ... kept whole while under this share of a LOD
LOD_GLASS_WHOLE_FROM = 3                    # any glass kept whole from this LOD on
LOD_GLASS_WHOLE = 0.12                      # ... while under this share of the LOD
LOD_GLASS_FAR_DEG = (4.0, 7.0, 11.0, 16.0)  # ... else its facets merged at these angles
REPROJECT_M = 0.02                          # LOD0 looked for this far along a LOD face's normal
FID_SAMPLE_M2 = 0.004                      # one fidelity sample per this much area at least
FID_REACH_M = 0.03                          # LOD0 looked for this far along the face normal
FID_RES = 1024                              # textures compared at this size
FID_TEX_ERR = 0.25                          # a texel this far off in a channel is wrong
# per LOD: the exterior's shading normal off LOD0's by at most p95 degrees, at most `bent`
# of its area over 25 degrees, at most `tex` of its area on the wrong texture
FID_LIMITS = {1: dict(p95=12.0, bent=0.02, tex=0.01),
              2: dict(p95=25.0, bent=0.05, tex=0.025),
              3: dict(p95=40.0, bent=0.10, tex=0.04)}


LOD_BENT_MORE = 2.5         # short of the fidelity limits: the pieces most off LOD0's normals
LOD_BENT_SHARE = 0.7        # ... (those that carry this share of the area off, LOD_BENT_PIECES
LOD_BENT_PIECES = 12        # ... at most) are given this many times their triangles


def fid_over(fid, k):
    """A LOD's fidelity as a share of its limits: the worst of its measures over its limit
    (over 1: the check fails)."""
    lim = FID_LIMITS.get(k)
    if lim is None or fid is None:
        return 0.0
    r = [fid["normal_p95_deg"] / lim["p95"], fid["bent_share"] / lim["bent"]]
    if fid.get("texture_share") is not None:
        r.append(fid["texture_share"] / lim["tex"])
    return max(r)


def mark_islands(ob):
    """cg_island: the UV island of each face."""
    from bpy_extras import mesh_utils
    me = ob.data
    ids = [0] * len(me.polygons)
    if me.uv_layers:
        for k, isl in enumerate(mesh_utils.mesh_linked_uv_islands(me)):
            for i in isl:
                ids[i] = k
    a = me.attributes.get("cg_island") or me.attributes.new("cg_island", 'INT', 'FACE')
    a.data.foreach_set("value", ids)


def _loop_tris(me):
    if hasattr(me, "calc_loop_triangles"):
        try:
            me.calc_loop_triangles()
        except Exception:
            pass
    return me.loop_triangles


BARY = (V3((1, 0, 0)), V3((0, 1, 0)), V3((0, 0, 1))) if bpy is not None else None


def _bary(p, a, b, c):
    from mathutils.geometry import barycentric_transform
    w = barycentric_transform(p, a, b, c, *BARY)
    w = [max(0.0, x) if x == x else 0.0 for x in w]
    s = sum(w)
    return [x / s for x in w] if s > 1e-12 else [1 / 3.0] * 3


class Surface:
    """A part's LOD0 surface: the UV and the shading normal LOD0 draws at any point, looked
    up per UV island (a LOD's face reads only its own island, so a texture cannot tear
    across an island's border however the collapse moved the face)."""

    def __init__(self, ob):
        me = ob.data
        uv = me.uv_layers.active.data if me.uv_layers else None
        self.uv = [tuple(x.uv) for x in uv] if uv else None
        self.n = [V3(x.vector) for x in me.corner_normals]
        co = [v.co.copy() for v in me.vertices]
        a = me.attributes.get("cg_island")
        isl = [x.value for x in a.data] if a else [0] * len(me.polygons)
        lts = list(_loop_tris(me))
        groups = {}
        for lt in lts:
            groups.setdefault(isl[lt.polygon_index], []).append(lt)
        self.trees, self.tris = {}, {}
        for k, g in groups.items():
            vs, ix, fs, tri = [], {}, [], []
            for lt in g:
                f = []
                for v in lt.vertices:
                    if v not in ix:
                        ix[v] = len(vs)
                        vs.append(co[v])
                    f.append(ix[v])
                fs.append(f)
                tri.append((tuple(lt.loops), tuple(co[v] for v in lt.vertices)))
            self.trees[k] = BVHTree.FromPolygons(vs, fs)
            self.tris[k] = tri
        self.all_isl = [isl[lt.polygon_index] for lt in lts]
        self.all = BVHTree.FromPolygons(co, [tuple(lt.vertices) for lt in lts])
        self.all_tris = [(tuple(lt.loops), tuple(co[v] for v in lt.vertices)) for lt in lts]

    def interp(self, tri, p):
        loops, (a, b, c) = tri
        w = _bary(p, a, b, c)
        n = (self.n[loops[0]] * w[0] + self.n[loops[1]] * w[1] + self.n[loops[2]] * w[2])
        n = n.normalized() if n.length > 1e-9 else None
        if self.uv is None:
            return None, n
        u = sum(self.uv[l][0] * x for l, x in zip(loops, w))
        v = sum(self.uv[l][1] * x for l, x in zip(loops, w))
        return (u, v), n

    def apply(self, me):
        """The LOD mesh's UVs and shading normals from LOD0's surface: each corner from the
        nearest point of its face's island to a point a little inside the face (so the two
        sides of a crease keep their own normals); a normal that would face away from its
        face takes the face's."""
        a = me.attributes.get("cg_island")
        isl = [x.value if x.value >= 0 else None for x in a.data] if a else \
            [None] * len(me.polygons)
        vco = [v.co for v in me.vertices]
        lv = [l.vertex_index for l in me.loops]
        U = [0.0] * (2 * len(me.loops))
        N = [(0.0, 0.0, 1.0)] * len(me.loops)
        ha = me.attributes.get("cg_hull")
        hull = [x.value for x in ha.data] if ha else None
        da, ra = me.attributes.get("cg_disc"), me.attributes.get("cg_disc_reach")
        disc = [x.value for x in da.data] if da else [0.0] * len(me.polygons)
        dreach = [x.value for x in ra.data] if ra else [0.0] * len(me.polygons)
        aff = me.get("cg_disc_uv")
        for p in me.polygons:
            c = p.center
            fn = p.normal
            k = isl[p.index]
            if disc[p.index] and aff is not None:
                # a far wheel's rim face: its own baked island (rim_disc), flat
                a_, b_, c_, d_, e_, f_ = aff
                for li in p.loop_indices:
                    q = vco[lv[li]]
                    U[2 * li] = a_ * q.x + b_ * q.z + c_
                    U[2 * li + 1] = d_ * q.x + e_ * q.z + f_
                    N[li] = tuple(fn)
                continue
            # without it, the disc looks along the axle from outside the wheel (the first
            # surface LOD0 shows there); any other face a little either side of itself
            off = dreach[p.index] if disc[p.index] else REPROJECT_M
            reach = off + (0.6 if disc[p.index] else REPROJECT_M)
            if k is None:           # a face of no island (a lathe): the island it covers
                hit = self.all.ray_cast(c + fn * max(off, 0.01), -fn, max(reach, 0.5))
                if hit[0] is None:
                    hit = self.all.find_nearest(c)
                k = self.all_isl[hit[2]] if hit[2] is not None else None
            tree, tris = (self.trees[k], self.tris[k]) if k in self.trees else \
                (self.all, self.all_tris)
            for li in p.loop_indices:
                q = vco[lv[li]].lerp(c, 0.05)
                # straight under the face first (a corner by a bevel takes the surface it
                # lies on, not the bevel's rim), else the nearest point
                loc, _, ti, _ = tree.ray_cast(q + fn * off, -fn, reach)
                if loc is None:
                    loc, _, ti, _ = tree.find_nearest(q)
                if loc is None:
                    N[li] = tuple(fn)
                    continue
                uv, n = self.interp(tris[ti], loc)
                if uv is not None:
                    U[2 * li], U[2 * li + 1] = uv
                if n is None or n.dot(fn) < 0.2:
                    n = fn
                elif hull is not None and hull[p.index] and n.dot(fn) < LOD_HULL_NORMAL:
                    # a stand-in hull's face keeps its own normal where LOD0's under its
                    # corner is far off it (a rib's flank under a hull laid over a row of
                    # ribs would shade the whole face askew)
                    n = fn
                N[li] = tuple(n)
        if self.uv is not None:
            if not me.uv_layers:
                me.uv_layers.new(name="UVMap")
            # a degenerate face (no area, no normal) can land on no number: its corner
            # takes the UV of another corner of its face, else 0
            for p in me.polygons:
                good = [li for li in p.loop_indices if U[2 * li] == U[2 * li] and
                        U[2 * li + 1] == U[2 * li + 1]]
                for li in p.loop_indices:
                    if li not in good:
                        U[2 * li], U[2 * li + 1] = (U[2 * good[0]], U[2 * good[0] + 1]) \
                            if good else (0.0, 0.0)
            N = [n if all(x == x for x in n) and any(n) else (0.0, 0.0, 1.0) for n in N]
            me.uv_layers.active.data.foreach_set("uv", U)
        me.shade_smooth()
        tire = me.attributes.get("cg_tire")
        if tire is not None:
            # a far LOD's tire (add_tire) keeps its own round normals, sharp at the tread
            me.set_sharp_from_angle(angle=LOD_LATHE_SHARP)
            own = [tuple(x.vector) for x in me.corner_normals]
            for p, x in zip(me.polygons, tire.data):
                if x.value:
                    for li in p.loop_indices:
                        N[li] = own[li]
        me.normals_split_custom_set(N)


def tire_of(ob):
    """The tire of a wheel node: (its piece, inner radius, outer radius, its points as
    (y, radius)), the piece the outermost point belongs to; None when there is none."""
    me = ob.data
    pa = me.attributes.get("cg_piece")
    if pa is None or not me.vertices:
        return None
    rs = [sqrt(v.co.x * v.co.x + v.co.z * v.co.z) for v in me.vertices]
    far = max(range(len(rs)), key=lambda i: rs[i])
    piece = next((x.value for p, x in zip(me.polygons, pa.data) if far in p.vertices), None)
    tv = {i for p, x in zip(me.polygons, pa.data) if x.value == piece for i in p.vertices}
    R = rs[far]
    rt = min(rs[i] for i in tv) if tv else 0.8 * R
    if not 0.45 * R < rt < 0.97 * R:
        return None
    return piece, rt, R, [(me.vertices[i].co.y, rs[i]) for i in tv]


def add_tire(bm, tire, side=0, out=0.0):
    """A far LOD's tire: a round tube about the axle (y), LOD_LATHE_SEGS segments, through
    the tire's envelope (its outermost faces at the bead, the middle of the sidewall and
    the tread's edges, each side), in place of the tire's own faces (taken out before).
    Its faces carry the piece LATHE_PIECE (the collapse keeps them whole) and cg_tire (they
    keep their own round normals); their UVs come from the island under each (Surface).
    With side (+1 the wheel's outside is +y, -1 is -y), the whole wheel: the tube and a
    flat disc on the outside across the bead ring, which shows the rim as LOD0 draws it
    seen along the axle (out: the wheel's outermost y times side)."""
    piece, rt, R, pts = tire
    prof_o, prof_i = [], []
    for r in (rt, 0.5 * (rt + R)):
        ys = [y for y, rr in pts if abs(rr - r) <= 0.04 * R] or [y for y, rr in pts]
        prof_o.append((r, max(ys)))
        prof_i.append((r, min(ys)))
    ys = [y for y, rr in pts if rr >= 0.97 * R]
    prof = prof_o + [(R, max(ys)), (R, min(ys))] + prof_i[::-1]
    S = LOD_LATHE_SEGS
    fl = bm.faces.layers.int
    pc = fl.get("cg_piece") or fl.new("cg_piece")
    il = fl.get("cg_island") or fl.new("cg_island")
    tl = fl.get("cg_tire") or fl.new("cg_tire")
    ff = bm.faces.layers.float
    dl = ff.get("cg_disc") or ff.new("cg_disc")     # (layers made before any new face)
    rl = ff.get("cg_disc_reach") or ff.new("cg_disc_reach")
    rings = [[bm.verts.new((r * cos(2 * pi * i / S), y, r * sin(2 * pi * i / S)))
              for i in range(S)] for r, y in prof]
    new = []
    for a, b in zip(rings, rings[1:]):
        for i in range(S):
            j = (i + 1) % S
            f = bm.faces.new((a[i], a[j], b[j], b[i]))
            f[pc], f[il], f[tl] = LATHE_PIECE, -1, 1
            new.append(f)
    bm.normal_update()
    # outward: away from the axle on the tread, away from the middle on the sidewalls
    ymid = 0.5 * (prof[0][1] + prof[-1][1])
    flip = [f for f in new if (lambda c, n: n.x * c.x + n.z * c.z + n.y * (c.y - ymid))(
        f.calc_center_median(), f.normal) < 0]
    if flip:
        bmesh.ops.reverse_faces(bm, faces=flip)
    if side:
        # the rim's faces: a flat disc closing each bead ring (its vertices), facing out;
        # the outside one wears the rim face baked for it (rim_disc), the inside one too
        # (cg_disc 1 and 2: their UVs from the wheel's cg_disc_uv; without it, what LOD0
        # shows along the axle from outside, the ray starting cg_disc_reach out)
        outer = (prof[0][1] - ymid) * side > 0
        reach = max(0.0, out - rings[0 if outer else -1][0].co.y * side) + 0.01
        disc = []
        for ring, mark in ((rings[0], 1 if outer else 2), (rings[-1], 2 if outer else 1)):
            mid = bm.verts.new((0.0, ring[0].co.y, 0.0))
            fs = [bm.faces.new((ring[i], ring[(i + 1) % S], mid)) for i in range(S)]
            bm.normal_update()
            sgn = side if mark == 1 else -side
            flip = [f for f in fs if f.normal.y * sgn < 0]
            if flip:
                bmesh.ops.reverse_faces(bm, faces=flip)
            for f in fs:
                f[pc], f[il], f[tl], f[dl], f[rl] = LATHE_PIECE, -1, 0, mark, reach
            disc += fs
        new += disc
    bmesh.ops.triangulate(bm, faces=new)


def lod_prep(ob, k, glass=False, wheel=False, unsub=False, unseen=None, planar=None):
    """A part's mesh made ready for LOD k's collapse: from LOD2 the cabin's faces and the
    parts no larger than LOD_SMALL_M (lamps never) left out; then faces within
    LOD_PLANAR_DEG of coplanar merged and triangulated again (a flat door is a few long
    triangles, its budget left to the curves), never across a UV island's border, a face
    class's or a part's. planar (degrees): far opaque glass, its faces merged to that angle
    whatever their shading (a canopy's curve in a few facets, every corner one of LOD0's)."""
    tire = tire_of(ob) if wheel and k >= LOD_WHEEL_LATHE else None
    src = ob.data
    far_wheel = tire is not None and k >= LOD_WHEEL_MADE
    side = (1 if ob.location.y > 0 else -1) if far_wheel else 0
    out = max((v.co.y * side for v in src.vertices), default=0.0) if far_wheel else 0.0
    cn = [V3(x.vector) for x in src.corner_normals]
    bend = [max((1.0 - cn[li].dot(p.normal) for li in p.loop_indices), default=0.0)
            for p in src.polygons]
    me = src.copy()
    a = me.attributes.new("cg_bend", 'FLOAT', 'FACE')
    a.data.foreach_set("value", bend)
    bm = bmesh.new()
    bm.from_mesh(me)
    me.attributes.remove(me.attributes["cg_bend"])
    bl = bm.faces.layers.float.get("cg_bend")
    fl = bm.faces.layers.int
    cls, pc, em, isl = (fl.get("cg_class"), fl.get("cg_piece"), fl.get("cg_emit"),
                        fl.get("cg_island"))
    # (a new layer drops the face references taken before it: made first)
    lp = fl.new("cg_lp") if k >= LOD_PART_FROM and pc is not None and not wheel else None
    gone = set()
    ov = fl.get("cg_over")
    if ov is not None:          # fine relief kept at LOD0 over its baked image: the image
        gone |= {f for f in bm.faces if f[ov]}
    if far_wheel:               # the whole wheel made anew: tube and disc
        gone |= set(bm.faces)
    elif tire is not None:
        gone |= {f for f in bm.faces if f[pc] == tire[0]}
    if unseen:
        bm.faces.ensure_lookup_table()
        gone |= {bm.faces[i] for i in unseen}
    if k >= 2 and cls is not None:
        gone |= {f for f in bm.faces if f[cls] == 2 or (k >= 3 and f[cls] == 1)}
    small = LOD_SMALL_M.get(k)
    small = small * SMALL_SCALE[0] if small else small
    small_m2 = LOD_SMALL_M2.get(k, 0.0) * SMALL_SCALE[0] ** 2
    if small and pc is not None:
        # from LOD_PART_FROM the units are loose parts (a piece's connected faces: one
        # object's mirrored bolts are many parts), else pieces
        unit = None
        if lp is not None:
            unit = loose_units(bm, pc)
            for f, u in unit.items():
                f[lp] = u
        key = (lambda f: unit[f]) if unit is not None else (lambda f: f[pc])
        box, lit, area, piece = {}, set(), {}, {}
        for f in bm.faces:
            q = key(f)
            piece[q] = f[pc]
            if f not in gone:
                area[q] = area.get(q, 0.0) + f.calc_area()
            if em is not None and f[em]:
                lit.add(q)
            for v in f.verts:
                b = box.get(q)
                if b is None:
                    box[q] = [v.co.copy(), v.co.copy()]
                else:
                    for i in range(3):
                        b[0][i] = min(b[0][i], v.co[i])
                        b[1][i] = max(b[1][i], v.co[i])

        def dims(q):
            b = box[q]
            return sorted(b[1][i] - b[0][i] for i in range(3))
        # a slender part (a cable, a rod, a handle: two sides of LOD_SLENDER_M at most)
        # is not dropped for its small area: what hangs on it would hang in the air
        # a part on the edge of the mesh's box stays (the LOD keeps LOD0's size)
        lo = [min(b[0][i] for b in box.values()) for i in range(3)]
        hi = [max(b[1][i] for b in box.values()) for i in range(3)]
        edge = {q for q, b in box.items() if unit is not None and any(
            b[0][i] - lo[i] < LOD_BOX_KEEP_M or hi[i] - b[1][i] < LOD_BOX_KEEP_M
            for i in range(3))}
        drop = {q for q, b in box.items() if q not in lit and q not in edge and
                piece[q] >= 0 and
                (dims(q)[2] <= small or
                 (area.get(q, 0.0) <= small_m2 and
                  not (dims(q)[1] <= LOD_SLENDER_M and dims(q)[2] > small)))}
        if unit is not None and k >= LOD_FLOAT_FROM and not wheel and not glass and drop:
            more, back = floating(bm, key, drop, edge, box, area, lit)
            drop = (drop - back) | more
        gone |= {f for f in bm.faces if key(f) in drop}
    if gone:
        bmesh.ops.delete(bm, geom=list(gone), context='FACES')
    if k >= LOD_WELD_FROM and not wheel:
        # pieces that meet edge to edge (panels) welded where their vertices coincide, so
        # the collapse moves their shared border as one and opens no gap between them; never
        # a lamp (welded to its bezel, the collapse drew its faces across the panel round it)
        em2 = bm.faces.layers.int.get("cg_emit")
        bmesh.ops.remove_doubles(bm, verts=[v for v in bm.verts if em2 is None or
                                            not any(f[em2] for f in v.link_faces)],
                                 dist=LOD_WELD_M)
    deg = planar or LOD_PLANAR_DEG.get(k)
    # a face LOD0 shades curved (its normals off its plane: a bevel, glass drawn smooth
    # over flat facets) is never merged: a larger face could not carry that shading
    flat = 1.0 - cos(max(deg or 0.0, 1.0) * pi / 180)
    for e in bm.edges:
        lf = e.link_faces
        e.seam = len(lf) == 2 and (
            any(lay is not None and lf[0][lay] != lf[1][lay] for lay in (cls, pc, isl)) or
            (bl is not None and not planar and (lf[0][bl] > flat or lf[1][bl] > flat)))
    if glass and unsub:
        # glass: a coarse sheet LOD0 shades through its normals (a fold drawn smooth across
        # a face) is never collapsed; when it is too much to keep, its grid is halved each
        # way, every kept corner where LOD0 had it
        bmesh.ops.unsubdivide(bm, verts=bm.verts[:], iterations=LOD_GLASS_ITER)
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY',
                              ngon_method='BEAUTY')
    elif deg:
        delimit = {'SEAM', 'UV'} if bm.loops.layers.uv.active is not None else {'SEAM'}
        bmesh.ops.dissolve_limit(bm, angle_limit=deg * pi / 180, use_dissolve_boundaries=False,
                                 verts=bm.verts[:], edges=bm.edges[:], delimit=delimit)
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY',
                              ngon_method='BEAUTY')
    if tire is not None:
        add_tire(bm, tire, side, out)
    bm.to_mesh(me)
    bm.free()
    if glass or far_wheel:
        me["cg_whole"] = True
    return me


def loose_units(bm, pc):
    """{face: loose part}: a piece's faces joined through edges, numbered from 0."""
    unit, n = {}, 0
    for f in bm.faces:
        if f in unit:
            continue
        unit[f] = n
        stack = [f]
        while stack:
            g = stack.pop()
            for e in g.edges:
                for h in e.link_faces:
                    if h not in unit and h[pc] == g[pc]:
                        unit[h] = n
                        stack.append(h)
        n += 1
    return unit


def floating(bm, key, drop, keep, box, area, lit=()):
    """The parts no larger than LOD_STANDIN_M that would float once the parts in drop are
    left out: no chain of parts touching (within LOD_TOUCH_M) leads from them to the
    largest part (a hook whose cable went, a bracket whose stay went). A lamp (lit) never
    goes: the dropped parts that hold it up stay. Returns (more to drop, dropped parts to
    keep)."""
    tree = BVHTree.FromBMesh(bm)
    owner = [key(f) for f in bm.faces]
    by = {}
    for v in bm.verts:
        if v.link_faces:
            by.setdefault(key(v.link_faces[0]), []).append(v.co)
    near = {q: set() for q in by}
    for q, pts in by.items():
        step = max(1, len(pts) // LOD_TOUCH_SAMPLES)
        for co in pts[::step]:
            for hit in tree.find_nearest_range(co, LOD_TOUCH_M):
                o = owner[hit[2]]
                if o != q:
                    near[q].add(o)
                    near.setdefault(o, set()).add(q)
    kept = [q for q in by if q not in drop]
    if not kept:
        return set(), set()
    root = max(kept, key=lambda q: area.get(q, 0.0))

    def reach(blocked):
        seen, stack = {root}, [root]
        while stack:
            q = stack.pop()
            for o in near.get(q, ()):
                if o not in seen and o not in blocked:
                    seen.add(o)
                    stack.append(o)
        return seen
    seen = reach(drop)
    back = set()
    for q in kept:
        if q in lit and q not in seen:
            # the shortest chain through dropped parts to what is held
            prev, stack, found = {q: None}, [q], None
            while stack and found is None:
                nxt = []
                for x in stack:
                    for o in sorted(near.get(x, ())):
                        if o in prev:
                            continue
                        prev[o] = x
                        if o in seen:
                            found = o
                            break
                        if o in drop:
                            nxt.append(o)
                    if found is not None:
                        break
                stack = nxt
            x = prev.get(found) if found is not None else None
            while x is not None and x != q:
                back.add(x)
                x = prev[x]
    if back:
        seen = reach(drop - back)
    out = set()
    for q in kept:
        if q in seen or q in keep or q in lit or q not in box:
            continue
        b = box[q]
        if sqrt(sum((b[1][i] - b[0][i]) ** 2 for i in range(3))) <= LOD_STANDIN_M:
            out.add(q)
    return out, back


def _collapse(me, ratio, coll, symmetric):
    """A new mesh: me collapsed to ratio of its triangles (Blender's decimate)."""
    tmp = new_obj("tmp_collapse", me, coll)
    if ratio < 0.999:
        md = tmp.modifiers.new("dec", 'DECIMATE')
        md.decimate_type = 'COLLAPSE'
        md.ratio = max(0.003, ratio)
        md.use_collapse_triangulate = True
        if symmetric:
            md.use_symmetry = True
            md.symmetry_axis = 'Y'
    dg = bpy.context.evaluated_depsgraph_get()
    out = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg), preserve_all_data_layers=True,
                                          depsgraph=dg)
    bpy.data.objects.remove(tmp)
    return out


def _piece_tris(me):
    a = me.attributes.get("cg_piece")
    out = {}
    if a is None:
        return out
    for p, x in zip(me.polygons, a.data):
        out[x.value] = out.get(x.value, 0) + len(p.vertices) - 2
    return out


def _only(me, keep, key="cg_piece"):
    """A copy of me with only the faces of the pieces (or other key) in keep."""
    m = me.copy()
    bm = bmesh.new()
    bm.from_mesh(m)
    lay = bm.faces.layers.int.get(key)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[lay] not in keep], context='FACES')
    bm.to_mesh(m)
    bm.free()
    return m


def _piece_faces(me, skip=(), key="cg_piece"):
    """{piece (or other key): (vertices, faces)} of a mesh, each its own vertex list."""
    pa = me.attributes.get(key)
    if pa is None:
        return {}
    co = [v.co for v in me.vertices]
    out = {}
    for p, x in zip(me.polygons, pa.data):
        if x.value in skip:
            continue
        vs, ix, fs = out.setdefault(x.value, ([], {}, []))
        f = []
        for i in p.vertices:
            if i not in ix:
                ix[i] = len(vs)
                vs.append(co[i].copy())
            f.append(ix[i])
        fs.append(f)
    return {q: (vs, fs) for q, (vs, ix, fs) in out.items()}


def _samples(vs, fs):
    """Points of faces: each face's middle and its edges' middles."""
    pts = []
    for f in fs:
        c = sum((vs[i] for i in f), V3((0, 0, 0))) / len(f)
        pts.append(c)
        pts += [(vs[a] + vs[b]) / 2 for a, b in zip(f, f[1:] + f[:1])]
    return pts


def _dev(pts, tree, q=1.0):
    """The q quantile of the distances from pts to a tree's surface."""
    if not pts:
        return 0.0
    ds = sorted((tree.find_nearest(p)[3] or 0.0) for p in pts)
    return ds[min(len(ds) - 1, int(q * (len(ds) - 1)))]


def _volume(vs, fs):
    """The volume a closed triangle mesh encloses (its faces turned any one way)."""
    v = 0.0
    for f in fs:
        a, b, c = vs[f[0]], vs[f[1]], vs[f[2]]
        v += a.dot(b.cross(c))
    return abs(v) / 6.0


def _closed(fs):
    """Whether faces make closed surfaces: every edge between exactly two of them."""
    n = {}
    for f in fs:
        for a, b in zip(f, list(f[1:]) + list(f[:1])):
            k = (a, b) if a < b else (b, a)
            n[k] = n.get(k, 0) + 1
    return bool(n) and all(c == 2 for c in n.values())


def _wreck(vs, fs, o):
    """How far a part's collapse (o: its (vertices, faces), None when it went) is off the
    part as prepared (vs, fs): (size, tolerance, deviation, the part's tree). The
    deviation: the farthest point of the collapse (faces' and edges' middles; a large
    part's 98th percentile) from the part, or the part's 95th percentile from the
    collapse. The tolerance: LOD_WRECK_M or LOD_WRECK_SHARE of a small part's size; for a
    larger part LOD_HULL_LARGE_M or LOD_WRECK_LARGE of its size. A small closed solid the
    collapse left open (a flute or a bolt folded into a sliver: a shard showing its dark
    inside, though every point of it is near the solid) is off by any measure."""
    lo = [min(v[i] for v in vs) for i in range(3)]
    hi = [max(v[i] for v in vs) for i in range(3)]
    e = sqrt(sum((hi[i] - lo[i]) ** 2 for i in range(3)))
    small = e <= LOD_STANDIN_M
    tol = max(LOD_WRECK_M, LOD_WRECK_SHARE * e) if small else \
        max(LOD_HULL_LARGE_M, LOD_WRECK_LARGE * e)
    tp = BVHTree.FromPolygons(vs, fs)
    if o is None:
        return e, tol, float("inf"), tp
    ov, of = o
    if small and _closed(fs) and not _closed(of):
        return e, tol, float("inf"), tp
    to = BVHTree.FromPolygons(ov, of)
    dev = max(_dev(_samples(ov, of), tp, 1.0 if small else 0.98),
              _dev(_samples(vs, fs), to, 0.95))
    return e, tol, dev, tp


def stand_ins(prep, out, coll, budget):
    """A far LOD's wrecks put right: a loose part the collapse took far from its own shape
    (a point of the collapsed part, its faces' and edges' middles, more than LOD_WRECK_M or
    LOD_WRECK_SHARE of its size from the part as prepared, or the prepared part's that far
    from the collapsed one: a flange folded through its drum, a step or a tow hook
    flattened into a spike). One no larger than LOD_STANDIN_M becomes its convex hull
    (LOD_HULL_DIRS corners at most, closed and clean) where the hull stays as close to it
    (both ways, the hull's faces on the part or on what it stands against, whose faces
    there are gone); a part on the edge of the box never goes; a larger one becomes its hull
    where that is within LOD_HULL_LARGE_M of it (a cable coiled on a drum), else is
    collapsed again alone at LOD_WRECK_MORE times its triangles, as is a lamp. The
    cheapest first, while they cost no more than budget triangles over the collapses;
    past it a small part goes. The far tire is left as it is. Returns (the mesh,
    {part: what})."""
    key = "cg_lp" if "cg_lp" in prep.attributes else "cg_piece"
    pa = prep.attributes.get(key)
    if pa is None or key not in out.attributes:
        return out, {}
    piece = {x.value: y.value for x, y in zip(pa.data, prep.attributes["cg_piece"].data)}
    # each part's material slot (a hull made for it wears it: a hull with none joined into
    # the LOD came out as a glTF primitive with no material, which an engine draws with its
    # default material, Unreal's checker; found importing the Aurels into Unreal)
    mat_of = {}
    for poly, x in zip(prep.polygons, pa.data):
        mat_of.setdefault(x.value, poly.material_index)
    lit = set()
    if "cg_emit" in prep.attributes:
        lit = {x.value for x, e in zip(pa.data, prep.attributes["cg_emit"].data) if e.value}
    P = _piece_faces(prep, key=key)
    # each part's faces' UV islands, in _piece_faces' order
    ia = prep.attributes.get("cg_island")
    isl = {}
    for x, y in zip(pa.data, ia.data if ia else pa.data):
        isl.setdefault(x.value, []).append(y.value if ia else -1)
    trees, edges = {}, set()
    O = _piece_faces(out, key=key)
    every = BVHTree.FromPolygons([v.co for v in prep.vertices],
                                 [list(p.vertices) for p in prep.polygons])
    co = [v.co for v in prep.vertices]
    blo = [min(c[i] for c in co) for i in range(3)] if co else [0.0] * 3
    bhi = [max(c[i] for c in co) for i in range(3)] if co else [0.0] * 3
    what, cand, again = {}, [], {}
    W = {q: _wreck(vs, fs, O.get(q)) for q, (vs, fs) in P.items()
         if piece.get(q) != LATHE_PIECE}
    # a piece of many loose parts, most of them wrecked, that is one convex shape as a
    # whole (a cable's turns on a drum are a cylinder; each turn alone collapses to a
    # crumpled ring and its own hull is a disc): one hull for the piece, where that keeps
    # within LOD_HULL_LARGE_M of it both ways
    whole_hulls = []
    by_piece = {}
    for q in W:
        by_piece.setdefault(piece.get(q), []).append(q)
    for g, qs in sorted(by_piece.items()):
        bad = [q for q in qs if W[q][2] > W[q][1]]
        if len(qs) < LOD_PIECE_HULL_PARTS or len(bad) < 0.5 * len(qs) or \
                any(q in lit for q in qs):
            continue
        qs = sorted(qs)
        uv_, uf_, ui_ = [], [], []
        for q in qs:
            b_ = len(uv_)
            uv_ += P[q][0]
            uf_ += [[b_ + i for i in f] for f in P[q][1]]
            ui_ += isl[q]
        h = support_hull(uv_, LOD_HULL_DIRS_LARGE)
        if h is None:
            continue
        hv = [v.co.copy() for v in h.vertices]
        hf = [list(p_.vertices) for p_ in h.polygons]
        th = BVHTree.FromPolygons(hv, hf)
        hdev = max(_dev(_samples(hv, hf), every, 0.9), _dev(_samples(uv_, uf_), th, 0.9))
        got = sum(len(O[q][1]) for q in qs if q in O)
        # ... and only where the parts fill that hull (their own hulls LOD_PIECE_HULL_FILL
        # of its volume: a coil's turns stack into a cylinder; six panels round a nose do
        # not, and their common hull cut through the cab as one dark wedge)
        fill = 0.0
        if hdev <= LOD_HULL_LARGE_M and len(h.polygons) - got <= budget:
            whole = _volume(hv, hf)
            for q in qs:
                hq = support_hull(P[q][0], LOD_HULL_DIRS)
                if hq is not None:
                    fill += _volume([v.co for v in hq.vertices],
                                    [list(p_.vertices) for p_ in hq.polygons])
                    bpy.data.meshes.remove(hq)
            fill = fill / whole if whole > 1e-9 else 0.0
        if fill < LOD_PIECE_HULL_FILL:
            bpy.data.meshes.remove(h)
            continue
        log("    piece %s: %d loose parts (%d wrecked) become one hull of %d triangles "
            "(off %.3f m, filled %.2f)" % (g, len(qs), len(bad), len(h.polygons), hdev, fill))
        budget -= max(0, len(h.polygons) - got)
        tu = BVHTree.FromPolygons(uv_, uf_)
        for nm_, val in (("cg_piece", g), ("cg_lp", qs[0]), ("cg_class", 0),
                         ("cg_hull", 1)):
            h.attributes.new(nm_, 'INT', 'FACE').data.foreach_set(
                "value", [val] * len(h.polygons))
        hi_ = []
        for poly in h.polygons:
            hit = tu.find_nearest(poly.center)
            hi_.append(ui_[hit[2]] if hit[2] is not None else -1)
        h.attributes.new("cg_island", 'INT', 'FACE').data.foreach_set("value", hi_)
        for m in out.materials:
            h.materials.append(m)
        if len(h.materials):
            h.polygons.foreach_set("material_index",
                                   [mat_of.get(qs[0], 0)] * len(h.polygons))
        whole_hulls.append(h)
        for q in qs:
            what[q] = "one hull"
    for q, (vs, fs) in P.items():
        if q not in W or q in what:
            continue
        lo = [min(v[i] for v in vs) for i in range(3)]
        hi = [max(v[i] for v in vs) for i in range(3)]
        e, tol, dev, tp = W[q]
        if dev <= tol:
            continue
        got = len(O[q][1]) if q in O else 0
        more = min(len(fs), int(LOD_WRECK_MORE * max(got, 4))) - got
        if q in lit:            # a lamp keeps its own shape: collapsed again, more kept
            cand.append((-e, q, None, more))
            continue
        big = e > LOD_STANDIN_M
        edge = not big and any(lo[i] - blo[i] < LOD_BOX_KEEP_M or
                               bhi[i] - hi[i] < LOD_BOX_KEEP_M for i in range(3))
        # (a large part's hull also with more corners: 26 round a coil of cable on a drum
        # leave it a crude prism, 3 cm off the coil)
        taken, hdev = False, None
        for dirs in (LOD_HULL_DIRS,) + ((LOD_HULL_DIRS_LARGE,) if big else ()):
            h = support_hull(vs, dirs)
            if h is None:
                break
            hv = [v.co.copy() for v in h.vertices]
            hf = [list(p.vertices) for p in h.polygons]
            th = BVHTree.FromPolygons(hv, hf)
            hdev = max(_dev(_samples(hv, hf), every, 0.9), _dev(_samples(vs, fs), th, 0.9))
            # a large part's hull only where it is that part to within LOD_HULL_LARGE_M (a
            # fluted sill strip, a box)
            if edge:
                edges.add(q)
            if hdev <= (LOD_HULL_LARGE_M if big else tol):
                cand.append((-e, q, h, len(h.polygons) - got))
                trees[q] = tp
                taken = True
                break
            bpy.data.meshes.remove(h)
        if DEBUG and e > 0.15:
            log("    wreck %d (piece %s) at %s size %.2f: off %.3f (allowed %.3f), hull off %s: "
                "%s" % (q, piece.get(q), tuple(round((lo[i] + hi[i]) / 2, 2) for i in range(3)),
                        e, dev, tol, "%.3f" % hdev if hdev is not None else "none",
                        "hull" if taken else "collapsed again" if big else
                        "stays" if edge else "dropped"))
        if taken:
            continue
        if big:
            cand.append((-e, q, None, more))
        elif not edge:          # (a part on the edge of the box stays as it is)
            what[q] = "dropped"
    # the cheapest first (most parts put right for the triangles), while the budget lasts;
    # past it a small part goes, a large one stays as the collapse left it. The small
    # wrecked parts of one piece (a row of flutes, a bolt circle) fare alike: hulls for all
    # of them when the budget has room for them all, else none (a row with gaps reads as
    # damage)
    row_of = {r[1]: r for r in cand}
    members = {}
    for ne, q, h, extra in cand:
        if h is not None and -ne <= LOD_STANDIN_M and q not in lit:
            members.setdefault(piece.get(q), []).append(q)
    members = {g: sorted(qs) for g, qs in members.items() if len(qs) > 1}
    grouped = {q: g for g, qs in members.items() for q in qs}
    units, seen = [], set()
    for r in cand:
        g = grouped.get(r[1])
        if g is None:
            units.append((r[3], (r[0], r[1]), [r]))
        elif g not in seen:
            seen.add(g)
            rows = [row_of[q] for q in members[g]]
            units.append((sum(x[3] for x in rows), (0.0, members[g][0]), rows))
    hulls, spent = [], 0
    for cost, _, rows in sorted(units, key=lambda u: (u[0], u[1])):
        over = spent + cost > budget
        if not over:
            spent += cost
        for ne, q, h, extra in rows:
            if over:
                if h is not None:
                    bpy.data.meshes.remove(h)
                if -ne <= LOD_STANDIN_M and q not in lit and q not in edges:
                    what[q] = "dropped"
                continue
            if h is None:
                again[q] = len(P[q][1])
                what[q] = "collapsed again"
                continue
            for nm_, val in (("cg_piece", piece[q]), ("cg_lp", q), ("cg_class", 0),
                             ("cg_hull", 1)):
                h.attributes.new(nm_, 'INT', 'FACE').data.foreach_set(
                    "value", [val] * len(h.polygons))
            # a hull face wears the island of its own part's face nearest it (never a
            # lamp's or a neighbor's the ray would find first)
            hi_ = []
            for poly in h.polygons:
                hit = trees[q].find_nearest(poly.center)
                hi_.append(isl[q][hit[2]] if hit[2] is not None else -1)
            h.attributes.new("cg_island", 'INT', 'FACE').data.foreach_set("value", hi_)
            for m in out.materials:
                h.materials.append(m)
            if len(h.materials):
                h.polygons.foreach_set("material_index", [mat_of.get(q, 0)] * len(h.polygons))
            hulls.append(h)
            what[q] = "hull"
    if not what:
        return out, what
    parts = [_only(out, set(O) - set(what), key)]
    for q, n in sorted(again.items()):
        m = _only(prep, {q}, key)
        got = len(O[q][1]) if q in O else 0
        parts.append(_collapse(m, min(1.0, LOD_WRECK_MORE * max(got, 4) / max(n, 1)), coll,
                               False))
        bpy.data.meshes.remove(m)
    parts += hulls + whole_hulls
    bpy.data.meshes.remove(out)
    jo = join_meshes("tmp_stand_ins", parts, coll)
    out = jo.data
    bpy.data.objects.remove(jo)
    return out, what


def lod_part(ob, prep, ratio, name, coll, surf, symmetric=False, floor=None, far=None,
             clamp=False, more=None):
    """A part of a LOD: its prepared mesh collapsed to ratio of its triangles; a piece the
    collapse took under its floor (LOD_FLOOR: a few triangles and so many a square meter
    of its area, never more than it has) collapsed again alone to that floor, so no panel
    vanishes; a piece in more ({piece: factor}) collapsed again alone to that many times
    the triangles the common ratio left it; UVs and shading normals laid on again from
    LOD0's surface."""
    if prep.get("cg_whole"):
        ratio = 1.0
    me = prep.copy()
    out = _collapse(me, ratio, coll, symmetric)
    bpy.data.meshes.remove(me)
    fl = floor
    if (fl is not None or more) and ratio < 0.999 and "cg_piece" in prep.attributes:
        have, got = _piece_tris(prep), _piece_tris(out)
        area = {}
        for p, x in zip(prep.polygons, prep.attributes["cg_piece"].data):
            area[x.value] = area.get(x.value, 0.0) + p.area
        lit = set()
        if "cg_emit" in prep.attributes:
            lit = {x.value for x, e in zip(prep.attributes["cg_piece"].data,
                                           prep.attributes["cg_emit"].data) if e.value}
        redo = {}
        for q, n in have.items():
            want = 0
            if fl is not None:
                want = min(n, int(fl[0] + fl[1] * area[q]))
                if q == LATHE_PIECE:
                    want = n
                if q in lit:        # a lamp keeps its shape (a light strip collapsed breaks)
                    want = max(want, min(n, int(fl[2] * n)))
            if more and q in more:
                want = max(want, min(n, int(more[q] * max(got.get(q, 0), 4))))
            if got.get(q, 0) < want:
                redo[q] = want
        if redo:
            parts = [_only(out, set(got) - set(redo))]
            for q, want in sorted(redo.items()):
                m = _only(prep, {q})
                parts.append(_collapse(m, want / have[q], coll, symmetric))
                bpy.data.meshes.remove(m)
            bpy.data.meshes.remove(out)
            jo = join_meshes("tmp_floor", parts, coll)
            out = jo.data
            bpy.data.objects.remove(jo)
    if far is not None:
        out, what = stand_ins(prep, out, coll, far)
        if what:
            n = {}
            for w in what.values():
                n[w] = n.get(w, 0) + 1
            log("  %s: pieces the collapse wrecked: %s" % (name, n))
    if far is not None or clamp:
        # a vertex the collapse placed past the part's box (its error minimum outside the
        # surface) is put back on the box: the LOD is never larger than LOD0
        co = [v.co for v in prep.vertices]
        if co:
            lo = [min(c[i] for c in co) for i in range(3)]
            hi = [max(c[i] for c in co) for i in range(3)]
            for v in out.vertices:
                v.co = [min(hi[i], max(lo[i], v.co[i])) for i in range(3)]
    if "cg_disc_uv" in ob.data:
        out["cg_disc_uv"] = list(ob.data["cg_disc_uv"])
    surf.apply(out)
    res = new_obj(name, out, coll)
    res.location = ob.location
    return res


def hold_bounds(parts_final, objs_k, ratio, target, k, coll, prep, surf, floor=None,
                hb=None, more=None):
    """A LOD whose box falls short of LOD0's by more than the check allows (lod_bounds: 2 cm
    or 1.5% of the size; a glass dome's crown collapsed away): the parts that reach LOD0's
    box on that side are collapsed again at twice their ratio, the others a little more to
    keep the budget, up to three times. Returns (objects, triangles)."""
    lo0, hi0 = world_box([o for _, o in parts_final])
    tol = [max(0.02, 0.015 * (hi0[i] - lo0[i])) for i in range(3)]
    rat = {nm: ratio for nm, _ in parts_final}
    for _ in range(3):
        lo, hi = world_box(objs_k)
        short = [(i, -1) for i in range(3) if lo[i] - lo0[i] > tol[i]] + \
                [(i, 1) for i in range(3) if hi0[i] - hi[i] > tol[i]]
        # (and past it: a collapse's vertex placed beyond the surface)
        over = [(i, -1) for i in range(3) if lo0[i] - lo[i] > tol[i]] + \
               [(i, 1) for i in range(3) if hi[i] - hi0[i] > tol[i]]
        if not short and not over:
            break
        bump = set()
        for (nm, o), ok_ in zip(parts_final, objs_k):
            plo, phi = world_box([o])
            klo, khi = world_box([ok_])
            for i, sd in short:
                if (sd < 0 and plo[i] - lo0[i] < 0.002) or (sd > 0 and hi0[i] - phi[i] < 0.002):
                    bump.add(nm)
            for i, sd in over:
                if (sd < 0 and lo0[i] - klo[i] > tol[i]) or (sd > 0 and khi[i] - hi0[i] > tol[i]):
                    bump.add(nm)
        if not bump:
            break
        for nm in bump:
            rat[nm] = min(1.0, rat[nm] * 2)
        tri0 = {nm: mesh_tris(prep[nm]) for nm, o in parts_final}
        fixed = sum(tri0[nm] * rat[nm] for nm in bump)
        rest = sum(tri0[nm] for nm in tri0 if nm not in bump)
        if rest > 0:
            r2 = max(0.003, (target - fixed) / rest)
            for nm in tri0:
                if nm not in bump:
                    rat[nm] = min(rat[nm], r2)
        log("  LOD%d short of LOD0's box %s, past it %s: %s collapsed again at %s" % (
            k, short, over, sorted(bump), {nm: round(rat[nm], 4) for nm in sorted(bump)}))
        for o in objs_k:
            me = o.data
            bpy.data.objects.remove(o)
            bpy.data.meshes.remove(me)
        objs_k = [lod_part(o, prep[nm], rat[nm],
                           "LOD%d_%s" % (k, nm), coll, surf[nm],
                           symmetric=(nm in ("body", "glass")), floor=floor,
                           far=hb if nm == "body" else None, clamp=k >= LOD_WRECK_FROM,
                           more=more if nm == "body" else None)
                  for nm, o in parts_final]
    return objs_k, sum(mesh_tris(o.data) for o in objs_k)


def fid_textures(work, slot="body"):
    """The bake's base color and paint weights at FID_RES, as rows from the bottom (UV v
    up), for the fidelity measure; None without the bakes."""
    import numpy as np
    out = []
    for ps in ("BASE", "TINT"):
        path = os.path.join(work, "%s_A_%s.png" % (slot, ps)) if work else None
        if not path or not os.path.exists(path):
            return None
        img = bpy.data.images.load(path)
        img.colorspace_settings.name = "Non-Color"
        if img.size[0] != FID_RES:
            img.scale(FID_RES, FID_RES)
        a = np.empty(FID_RES * FID_RES * 4, np.float32)
        img.pixels.foreach_get(a)
        out.append(a.reshape(FID_RES, FID_RES, 4)[..., :3])
        bpy.data.images.remove(img)
    return np.concatenate(out, 2)


def fidelity(ob, surf, tex, off=None):
    """How a LOD's exterior draws next to LOD0's, measured where LOD0 lies under each point
    of it (a ray back along the face normal, FID_REACH_M either way): the angle between the
    two shading normals and, through the two UVs, the bake's colors (a torn texture shows
    another island's). Points spread by area, one a FID_SAMPLE_M2 at least. Returns the
    area weighted 95th percentile angle, the share over 25 degrees, the share with a texel
    off by FID_TEX_ERR, and the share with no LOD0 within reach. off = (a dict, degrees):
    the dict is filled with each piece's area whose normal is more than that off LOD0's."""
    me = ob.data
    a = me.attributes.get("cg_class")
    cls = [x.value for x in a.data] if a else [0] * len(me.polygons)
    pa = me.attributes.get("cg_piece")
    pcs = [x.value for x in pa.data] if pa else [0] * len(me.polygons)
    uvl = me.uv_layers.active.data if me.uv_layers else None
    cn = [V3(x.vector) for x in me.corner_normals]
    co = [v.co for v in me.vertices]
    rows, miss, tot = [], 0.0, 0.0
    R = FID_RES
    for lt in _loop_tris(me):
        if cls[lt.polygon_index] != 0 or lt.area < 1e-10:
            continue
        A = lt.area
        tot += A
        n = min(24, 1 + int(A / FID_SAMPLE_M2))
        fn = lt.normal
        L = lt.loops
        P = [co[v] for v in lt.vertices]
        for s in range(n):
            # an R2 sequence folded into the triangle
            r1 = (0.5 + 0.7548776662 * (s + 1)) % 1.0 if n > 1 else 1 / 3.0
            r2 = (0.5 + 0.5698402910 * (s + 1)) % 1.0 if n > 1 else 1 / 3.0
            if r1 + r2 > 1:
                r1, r2 = 1 - r1, 1 - r2
            w = (1 - r1 - r2, r1, r2)
            p = P[0] * w[0] + P[1] * w[1] + P[2] * w[2]
            # the LOD0 surface nearest the point along the normal line, facing its way
            # (every surface the line meets within reach, not only the outermost: a trim
            # over a panel would stand in for the panel; the far side of a thin plate is
            # not it)
            hit, o_, left = (None,), p + fn * FID_REACH_M, 2 * FID_REACH_M
            for _ in range(6):
                h = surf.all.ray_cast(o_, -fn, left)
                if h[0] is None:
                    break
                if h[1].dot(fn) > 0 and (hit[0] is None or
                                         (h[0] - p).length < (hit[0] - p).length):
                    hit = h
                step = (h[0] - o_).length + 1e-5
                o_, left = o_ - fn * step, left - step
                if left <= 0:
                    break
            if hit[0] is None:
                miss += A / n
                continue
            uv0, n0 = surf.interp(surf.all_tris[hit[2]], hit[0])
            ns = cn[L[0]] * w[0] + cn[L[1]] * w[1] + cn[L[2]] * w[2]
            ang = 0.0
            if n0 is not None and ns.length > 1e-9:
                d = max(-1.0, min(1.0, ns.normalized().dot(n0)))
                ang = acos(d) * 180 / pi
            terr = 0.0
            if tex is not None and uvl is not None and uv0 is not None:
                u = sum(uvl[l].uv[0] * x for l, x in zip(L, w))
                v = sum(uvl[l].uv[1] * x for l, x in zip(L, w))
                i0 = min(R - 1, max(0, int(v * R))), min(R - 1, max(0, int(u * R)))
                i1 = min(R - 1, max(0, int(uv0[1] * R))), min(R - 1, max(0, int(uv0[0] * R)))
                terr = float(abs(tex[i0] - tex[i1]).max())
            rows.append((ang, terr, A / n))
            if off is not None and ang > off[1]:
                q = pcs[lt.polygon_index]
                off[0][q] = off[0].get(q, 0.0) + A / n
    if not rows:
        return None
    rows.sort()
    wsum = sum(r[2] for r in rows)
    acc, p95 = 0.0, rows[-1][0]
    for r in rows:
        acc += r[2]
        if acc >= 0.95 * wsum:
            p95 = r[0]
            break
    return dict(normal_p95_deg=round(p95, 2),
                bent_share=round(sum(r[2] for r in rows if r[0] > 25) / wsum, 4),
                texture_share=round(sum(r[2] for r in rows if r[1] > FID_TEX_ERR) / wsum, 4)
                if tex is not None else None,
                miss_share=round(miss / max(tot, 1e-9), 4))


def opaque_unseen(parts_final):
    """The faces of the body and glass no ray from outside reaches when the glass is opaque
    (from opaque_from_lod: no cabin, the glass drawn dark): the inner sheet of thick glass,
    the backs of panels seen only through the glass. Rays as in visibility (the face's
    normal and the directions of DIRS in front of it, from its middle and corners), against
    every part at LOD0, wheels included. Lamps are kept. {part: [face index, ...]}."""
    global DIRS
    if DIRS is None:
        DIRS = fib_dirs(96)
    vs, ps = [], []
    for nm, o in parts_final:
        t = o.location.copy()
        b = len(vs)
        vs += [v.co + t for v in o.data.vertices]
        ps += [[b + i for i in p.vertices] for p in o.data.polygons]
    tree = BVHTree.FromPolygons(vs, ps)
    eps = 2e-4
    out = {}
    for nm, o in parts_final:
        if nm not in ("body", "glass"):
            continue
        me = o.data
        em = me.attributes.get("cg_emit")
        lit = [x.value for x in em.data] if em else [0] * len(me.polygons)
        t = o.location
        co = [v.co + t for v in me.vertices]
        gone = []
        for p in me.polygons:
            if lit[p.index]:
                continue
            n = V3(p.normal)
            if n.length < 0.5:
                continue
            c = p.center + t
            samples = [c] + ([c.lerp(co[i], 0.85) for i in p.vertices] if p.area > 2e-4
                             else [])
            dirs = [n] + [d for d in DIRS if d.dot(n) > 0.12 and d.z > -0.3]
            if not any(tree.ray_cast(q + n * eps, d)[0] is None for q in samples
                       for d in dirs):
                gone.append(p.index)
        out[nm] = gone
    return out


def make_lods(parts_final, budgets, coll, work=None):
    """LOD1 to LOD3 from LOD0's parts: each lod_prep'ed, then collapsed (body and glass
    symmetric in y) at one ratio for every part to the budget (at most 60% of the LOD
    before it), UVs and normals laid on from LOD0 (Surface), the box held (hold_bounds);
    each measured against LOD0 (fidelity). Returns [dict(lod, objs, fidelity)]."""
    for nm, o in parts_final:
        mark_islands(o)
    surf = {nm: Surface(o) for nm, o in parts_final}
    tex = fid_textures(work)
    body0 = dict(parts_final).get("body")
    # glass drawn by its normals (a coarse sheet shaded smooth: many corners far off their
    # face's plane) is kept whole while it is cheap; dense glass is collapsed as any part
    coarse = set()
    for nm, o in parts_final:
        if nm == "glass":
            me = o.data
            cn = me.corner_normals
            off = sum(1 for p in me.polygons for li in p.loop_indices
                      if V3(cn[li].vector).dot(p.normal) < cos(15 * pi / 180))
            if off > LOD_COARSE_SHARE * max(1, len(me.loops)):
                coarse.add(nm)
    log("LODs: glass kept whole (coarse, shaded by its normals): %s" % sorted(coarse))
    lods = [dict(lod=0, objs=[o for _, o in parts_final], fidelity=None)]
    prev = sum(mesh_tris(o.data) for _, o in parts_final)
    unseen = None
    for k, budget_k in enumerate(budgets[1:], 1):
        t = time.time()
        target = min(budget_k, int(0.6 * prev))     # a car under budget still steps down
        if k >= LOD_OPAQUE_FROM and unseen is None:
            t1 = time.time()
            unseen = opaque_unseen(parts_final)
            log("LOD%d: faces not seen with the glass opaque %s (%.1f s)" % (
                k, {nm: len(v) for nm, v in unseen.items()}, time.time() - t1))
        hid = unseen or {}
        SMALL_SCALE[0] = 1.0
        while True:
            prep = {nm: lod_prep(o, k, nm in coarse, nm.startswith("wheel_"),
                                 unseen=hid.get(nm))
                    for nm, o in parts_final}
            for nm in coarse:       # too much to keep whole: unsubdivided, else collapsed
                if k >= LOD_GLASS_WHOLE_FROM:
                    # (far and opaque: first its facets merged at growing angles, which keeps
                    # the sheet on LOD0's surface and its edge on its frame; unsubdivided it
                    # came out wavy)
                    for deg in LOD_GLASS_FAR_DEG:
                        if mesh_tris(prep[nm]) <= LOD_GLASS_SHARE.get(k, 0.3) * target:
                            break
                        bpy.data.meshes.remove(prep[nm])
                        prep[nm] = lod_prep(dict(parts_final)[nm], k, glass=True,
                                            unseen=hid.get(nm), planar=deg)
                        log("  LOD%d: %s merged at %g degrees: %d triangles" % (
                            k, nm, deg, mesh_tris(prep[nm])))
                for kw in (dict(glass=True, unsub=True), dict()):
                    if mesh_tris(prep[nm]) <= LOD_GLASS_SHARE.get(k, 0.3) * target:
                        break
                    bpy.data.meshes.remove(prep[nm])
                    prep[nm] = lod_prep(dict(parts_final)[nm], k, unseen=hid.get(nm), **kw)
            if k >= LOD_GLASS_WHOLE_FROM and "glass" in prep and "glass" not in coarse:
                if mesh_tris(prep["glass"]) > LOD_GLASS_WHOLE * target:
                    # dense glass (a canopy's subdivided sheet), too much to keep: its facets
                    # merged at growing angles, every kept corner where LOD0 had it, when that
                    # fits (collapsed, a far LOD's dark opaque glass comes out wavy and off its
                    # frame)
                    for deg in LOD_GLASS_FAR_DEG:
                        un = lod_prep(dict(parts_final)["glass"], k, glass=True,
                                      unseen=hid.get("glass"), planar=deg)
                        if mesh_tris(un) <= LOD_GLASS_SHARE.get(k, 0.2) * target:
                            log("  LOD%d: dense glass merged at %g degrees, %d to %d triangles, "
                                "kept whole" % (k, deg, mesh_tris(prep["glass"]), mesh_tris(un)))
                            bpy.data.meshes.remove(prep["glass"])
                            prep["glass"] = un
                            break
                        bpy.data.meshes.remove(un)
                elif mesh_tris(prep["glass"]) <= LOD_GLASS_WHOLE * target:
                    # flat panes merged to a few triangles: kept as they are (a pane collapsed
                    # further pulls away from its frame)
                    prep["glass"]["cg_whole"] = True
            base = sum(mesh_tris(m) for m in prep.values())
            fixed = sum(mesh_tris(m) for m in prep.values() if m.get("cg_whole"))
            ratio = min(1.0, max(0.003, target - fixed) / max(base - fixed, 1))
            # the floors take half the budget left at most
            floor = None
            if k in LOD_FLOOR:
                area = sum(p.area for nm, m in prep.items() if not m.get("cg_whole")
                           for p in m.polygons)
                a_, b_, c_ = LOD_FLOOR[k]
                floor = (a_, min(b_, 0.6 * max(0, target - fixed) / max(area, 1e-6)), c_)
            hb0 = int(LOD_HULL_SHARE * target) if k >= LOD_WRECK_FROM else None

            def solve(ratio, floor, hb, more):
                """The LOD's parts at the budget (more: body pieces given more triangles, the
                rest paying), its box held, and how its body draws next to LOD0's."""
                objs_k = []
                for i in range(10 if k >= LOD_WRECK_FROM else 6):
                    for o in objs_k:
                        me = o.data
                        bpy.data.objects.remove(o)
                        bpy.data.meshes.remove(me)
                    objs_k = [lod_part(o, prep[nm], ratio,
                                       "LOD%d_%s" % (k, nm), coll, surf[nm],
                                       symmetric=(nm in ("body", "glass")), floor=floor,
                                       far=hb if nm == "body" else None,
                                       clamp=k >= LOD_WRECK_FROM,
                                       more=more if nm == "body" else None)
                              for nm, o in parts_final]
                    got = sum(mesh_tris(o.data) for o in objs_k)
                    if got <= target * 1.03 or ratio >= 0.999:
                        break
                    if hb and ratio < 0.03:
                        hb //= 2            # the hulls too, when the collapse alone cannot pay
                    if floor is not None and ratio < 0.03:
                        # the floors alone are over the budget: lowered with the rest
                        s = max(0.3, (target - fixed) / max(1, got - fixed) * 0.95)
                        floor = (floor[0], floor[1] * s, floor[2] * s)
                    ratio *= max(1, target - fixed) / max(1, got - fixed) * 0.98
                objs_k, got = hold_bounds(parts_final, objs_k, ratio, target, k, coll, prep, surf,
                                          floor, hb, more)
                fid, bent = None, {}
                if body0 is not None:
                    lim = FID_LIMITS.get(k)
                    fid = fidelity(objs_k[[nm for nm, _ in parts_final].index("body")],
                                   surf["body"], tex, (bent, lim["p95"]) if lim else None)
                return objs_k, got, ratio, fid, bent

            objs_k, got, ratio1, fid, bent = solve(ratio, floor, hb0, None)
            # short of the fidelity limits: the pieces that carry most of the area drawn off
            # LOD0's normals (round bars and springs collapsed to a few sides) are given
            # LOD_BENT_MORE times their triangles, the rest pay, and the LOD is kept when its
            # body then draws nearer LOD0; twice at most
            for _ in range(2):
                if fid is None or fid_over(fid, k) <= 1.0 or not bent:
                    break
                tot_bent, acc, more = sum(bent.values()), 0.0, {}
                for q, a_ in sorted(bent.items(), key=lambda kv: (-kv[1], kv[0])):
                    if q < 0 or acc >= LOD_BENT_SHARE * tot_bent or len(more) >= LOD_BENT_PIECES:
                        continue
                    more[q] = LOD_BENT_MORE
                    acc += a_
                if not more:
                    break
                objs2, got2, ratio2, fid2, bent2 = solve(ratio, floor, hb0, more)
                better = fid2 is not None and fid_over(fid2, k) < fid_over(fid, k)
                log("  LOD%d short of its fidelity limits (%.2f of them): %d pieces off LOD0's "
                    "normals given %.1f times their triangles: %.2f, %s" % (
                        k, fid_over(fid, k), len(more), LOD_BENT_MORE,
                        fid_over(fid2, k) if fid2 else -1, "kept" if better else "not kept"))
                drop = objs_k if better else objs2
                if better:
                    objs_k, got, ratio1, fid, bent = objs2, got2, ratio2, fid2, bent2
                for o in drop:
                    me = o.data
                    bpy.data.objects.remove(o)
                    bpy.data.meshes.remove(me)
                if not better:
                    break
            ratio = ratio1
            for m in prep.values():
                bpy.data.meshes.remove(m)
            if k >= LOD_PART_FROM and ratio < LOD_STARVED and \
                    SMALL_SCALE[0] < LOD_STARVED_SCALES[-1]:
                # the collapse is starved (the hulls, floors, wheels and lamps take the
                # budget, and what is left tears the panels apart at their gaps): the
                # LOD is prepared again with larger small parts left out
                nxt = next(x for x in LOD_STARVED_SCALES if x > SMALL_SCALE[0])
                log("  LOD%d starved (ratio %.3f): made again with the small parts left "
                    "out up to %g times the size" % (k, ratio, nxt))
                SMALL_SCALE[0] = nxt
                for o in objs_k:
                    me = o.data
                    bpy.data.objects.remove(o)
                    bpy.data.meshes.remove(me)
                continue
            break
        SMALL_SCALE[0] = 1.0
        log("LOD%d: %d triangles (prepared %d, target %d, ratio %.3f), %.1f s; fidelity %s" % (
            k, got, base, target, ratio, time.time() - t, fid))
        prev = got
        lods.append(dict(lod=k, objs=objs_k, fidelity=fid))
    return lods


# ---------------------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------------------
def mark_emit(ob, infos):
    """cg_emit: the faces of a lamp (an emissive material), before the slot's one material
    replaces theirs; the LODs never leave a lamp out."""
    me = ob.data
    lit = []
    for m in me.materials:
        nm = m.name.split("::", 1)[-1] if m else ""
        mi = infos.get(nm)
        lit.append(1 if mi is not None and mi.emissive else 0)
    a = me.attributes.get("cg_emit") or me.attributes.new("cg_emit", 'INT', 'FACE')
    a.data.foreach_set("value", [lit[p.material_index] if p.material_index < len(lit) else 0
                                 for p in me.polygons])


def save_lod_input(work, parts_final):
    """LOD0's parts as they enter the LODs (attributes kept), for --lods-only."""
    for i, (nm, o) in enumerate(parts_final):
        o["cg_part"] = nm
        o["cg_order"] = i
    bpy.data.libraries.write(os.path.join(work, "lod_input.blend"),
                             {o for _, o in parts_final}, fake_user=True)


def export_lods(out, lods, names, budgets):
    rows = []
    for L in lods:
        for o in L["objs"]:
            strip_attrs(o.data)
        path = os.path.join(out, "lod%d.glb" % L["lod"])
        export_glb(path, L["objs"], names)
        tri = {nm: mesh_tris(o.data) for nm, o in zip(names, L["objs"])}
        row = dict(lod=L["lod"], file="lod%d.glb" % L["lod"], triangles=sum(tri.values()),
                   budget=budgets[L["lod"]], parts=tri)
        if L.get("fidelity") is not None:
            row["fidelity"] = L["fidelity"]
        rows.append(row)
    return rows


def size_class(exterior_m2):
    """The size class of a vehicle by its body's exterior area: large (LOD_TRIS_LARGE,
    TEXEL_FLOOR_LARGE) from LARGE_EXTERIOR_M2, else standard."""
    big = exterior_m2 >= LARGE_EXTERIOR_M2
    return dict(name="large" if big else "standard", exterior_m2=round(exterior_m2, 2),
                rule="large when the body's exterior is %.0f m2 or more" % LARGE_EXTERIOR_M2,
                lod_budgets=list(LOD_TRIS_LARGE if big else LOD_TRIS),
                texel_floor_px_per_m=dict(TEXEL_FLOOR_LARGE if big else TEXEL_FLOOR))


def main_lods(A):
    """--lods-only: the LODs made again from an earlier run's LOD0 (kept by --keep-work),
    written over its pack (LOD files, pack.json's lods); the proof's LOD views and the
    checks follow."""
    work = os.path.join(A.out, "work")
    path = os.path.join(work, "lod_input.blend")
    if not os.path.exists(path):
        raise SystemExit("no %s: run once with --keep-work" % path)
    with open(os.path.join(A.out, "pack.json")) as f:
        pack = json.load(f)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    coll = bpy.data.collections.new("LOW")
    bpy.context.scene.collection.children.link(coll)
    with bpy.data.libraries.load(path) as (src, dst):
        dst.objects = list(src.objects)
    obs = sorted([o for o in dst.objects if o is not None], key=lambda o: o["cg_order"])
    for o in obs:
        coll.objects.link(o)
    parts_final = [(o["cg_part"], o) for o in obs]
    if A.lods is None:
        sc = pack.get("size_class") or size_class(
            pack["uv"]["texel_px_per_m"]["body"]["exterior"]["area_m2"])
        A.lods = list(sc["lod_budgets"])
        pack["size_class"] = dict(sc, lod_budgets=list(A.lods))
    t = time.time()
    lods = make_lods(parts_final, A.lods, coll, work)
    rows = export_lods(A.out, lods[1:], [nm for nm, _ in parts_final], A.lods)
    pack["lods"] = pack["lods"][:1] + rows
    pack["source"]["game_sha256"] = sha256(os.path.abspath(__file__))
    pack["build"]["seconds"]["lods_only"] = round(time.time() - t, 1)
    with open(os.path.join(A.out, "pack.json"), "w") as f:
        json.dump(pack, f, indent=1)
    log("wrote LODs %s" % [r["triangles"] for r in pack["lods"]])
    return pack


def main_build(A):
    out = A.out
    work = os.path.join(out, "work")
    proof = os.path.join(out, "proof")
    if os.path.isdir(out):
        for f in os.listdir(out):
            fp = os.path.join(out, f)
            if f in ("build",):
                continue
            shutil.rmtree(fp) if os.path.isdir(fp) else os.remove(fp)
    for d in (out, work, proof):
        os.makedirs(d, exist_ok=True)
    times = {}
    t = time.time()
    K = build_car(A.car, out)
    times["build"] = time.time() - t
    script = os.path.join(HERE, "cars", A.car + ".py")
    title = ""
    with open(script) as f:
        src_txt = f.read()
    if src_txt.startswith('"""'):
        title = src_txt[3:].split("\n", 1)[0].split(":")[0].strip()
    log("built %s (%s)" % (A.car, title))

    # 1. the original, from the car's own views
    t = time.time()
    res = (1920, 1080) if not A.test else (960, 540)
    sm = max(8, int(96 * A.samples))
    views = ["hero"] + [v for v in A.views.split(",") if v and v != "hero"]
    cams = render_views(K, views, res, sm, proof, "original")
    hero_view = {k: (list(v) if isinstance(v, tuple) else v) for k, v in K.VIEWS["hero"].items()}
    times["render_original"] = time.time() - t
    orig_tris = K.tri_count()
    n_objects = len([o for o in K.CAR.objects])

    # 2. materials and pieces
    t = time.time()
    infos = analyze_materials(K)
    micro = strip_flake(infos)
    pieces, wheels = gather(K, infos)
    log("%d pieces from %d objects, %d triangles; %d wheels" % (
        len(pieces), n_objects, sum(p.tris for p in pieces), len(wheels)))
    studio = studio_record(K, pieces)

    # 3. bake down: flat relief and cards always
    find_relief(pieces, {mi.name for mi in infos.values() if mi.emissive})
    tree_all, owner = world_bvh([p for p in pieces if p.part == "body"])
    cards = find_cards(pieces, tree_all, owner)
    for c in cards:
        c["piece"].op = "card_src"
        log("  card: %s, %d triangles over %.3f m2 (%.0f mm deep)" % (
            c["piece"].name, c["tris"], c["area"], c["thick"] * 1000))
    for p in pieces:
        if p.op == "keep" and p.relief is not None and p.relief <= FLAT_RELIEF_M:
            p.op = "relief"
            log("  relief: %s, %d triangles, %.1f mm" % (p.name, p.tris, p.relief * 1000))
    for p in pieces:        # tires with tread pockets and lettering cut into them
        if p.op == "keep" and p.ob.name.startswith("tire.") and p.tris > TIRE_LATHE_TRIS:
            p.lathe, nprof = lathe_mesh(p)
            p.op = "lathe"
            log("  tire %s rebuilt as a lathe (%d -> %d triangles, %d profile points)" % (
                p.name, p.tris, mesh_tris(p.lathe), nprof))
    budget = (A.lods or LOD_TRIS)[0]
    low_coll = bpy.data.collections.new("LOW")
    bpy.context.scene.collection.children.link(low_coll)
    # over the budget, in this order: taller relief; then every part of 600 triangles or
    # more alike, panels too, at most halved a round (a round that crushed the small dense
    # parts alone turned turbine wheels and light strips into polygons), four rounds; the
    # glass never (a collapsed canopy shows its facets in every reflection)
    steps = ["tall", "collapse", "collapse", "collapse", "collapse"]
    over_tried = False
    while True:
        parts = part_meshes(pieces, cards)
        objs = {part: join_meshes("tmp_" + part, [m for m, _ in lst], low_coll)
                for part, lst in parts.items()}
        lettered = {p.part.split(":")[1] for p in pieces
                    if p.op == "relief" and p.part.startswith("wheel:")}
        twins = find_twins(objs, wheels, lettered)
        glass_tree = None
        if "glass" in objs:
            bmg = bmesh.new()
            bmg.from_mesh(objs["glass"].data)
            glass_tree = BVHTree.FromBMesh(bmg)
            bmg.free()
        culled = {}
        for part, ob in objs.items():
            if part != "glass" and part not in twins:
                culled[part] = cull(ob, glass_tree if part == "body" else None,
                                    {mi.name for mi in infos.values() if mi.emissive},
                                    floats=not wheels)
        total = sum(mesh_tris(objs[twins.get(k, k)].data) for k in objs)
        log("low: %d triangles (%s); removed (coincident, hidden) %s; twins %s" % (
            total, ", ".join("%s %d" % (k, mesh_tris(o.data)) for k, o in sorted(objs.items())),
            culled, twins))
        if total <= budget and len(steps) == 5 and not over_tried:
            # under the budget with nothing shed: fine relief (flutes, slots, small
            # lettering: parts under DETAIL_FINE_PX texels wide at the floor, which no
            # atlas draws as lines and letters) is also kept as it is at LOD0, over its
            # baked image, smallest first while there is room; from LOD1 the image alone
            over_tried = True
            floor_px = TEXEL_FLOOR["body"] * A.body_size / 4096
            lit_ = {mi.name for mi in infos.values() if mi.emissive}
            cand = [p for p in fine_relief([p for p in pieces if p.op == "relief" and
                                            p.part == "body" and p.mat not in lit_],
                                           floor_px)]
            room = min(budget * 0.97 - total, OVER_SHARE * budget)
            for p in sorted(cand, key=lambda p: (p.tris, p.name)):
                if p.tris <= room:
                    p.over = True
                    room -= p.tris
                    if part_sizes(p)[1] * floor_px < OVER_ONLY_PX:
                        # every part of it too small for any image (letters a few
                        # texels tall, screw heads): at LOD0 as it is, and nothing baked
                        # under it (its image was dots, and showed round the letters). A
                        # piece with one larger part keeps its image: a hull number among
                        # small print must still be there from LOD1 on
                        p.op = "keep"
            kept = [p for p in cand if p.over]
            if kept:
                log("  fine relief kept at LOD0 over its baked image: %d pieces, %d "
                    "triangles (%s); of them at LOD0 only, with no image: %s" % (
                        len(kept), sum(p.tris for p in kept),
                        ", ".join(sorted(p.name for p in kept))[:300],
                        ", ".join(sorted(p.name for p in kept if p.op == "keep"))[:300]))
                for ob in list(objs.values()):
                    me = ob.data
                    bpy.data.objects.remove(ob)
                    bpy.data.meshes.remove(me)
                continue
        if total <= budget or not steps:
            break
        step = steps.pop(0)
        per_piece = {}
        for part, ob in objs.items():
            a = ob.data.attributes.get("cg_piece")
            if a is None or part in twins:
                continue
            k = 1 + sum(1 for v in twins.values() if v == part)
            for poly, x in zip(ob.data.polygons, a.data):
                per_piece[x.value] = per_piece.get(x.value, 0) + k * (len(poly.vertices) - 2)
        for ob in list(objs.values()):
            me = ob.data
            bpy.data.objects.remove(ob)
            bpy.data.meshes.remove(me)
        excess = total - budget * 0.97
        if step == "tall":
            cand = [p for p in pieces if p.op == "keep" and p.relief is not None and
                    p.relief <= TALL_RELIEF_M and not (infos.get(p.mat) and
                                                       infos[p.mat].emissive)]
            cand.sort(key=lambda p: -per_piece.get(p.idx, 0))
            for p in cand:
                if excess <= 0:
                    break
                p.op = "relief"
                excess -= per_piece.get(p.idx, 0)
                log("  over budget: relief %s (%.1f mm) baked down" % (p.name, p.relief * 1000))
        else:
            # lamps never (a thin light strip collapsed breaks into dashes), wheels never
            # (seen close and turning; a collapsed wheel unwraps folded, its UVs overlapping)
            cand = [p for p in pieces if p.op in ("keep", "collapse") and
                    per_piece.get(p.idx, 0) >= 600 and
                    p.part != "glass" and
                    p.part.split(":")[0] not in ("wheel", "brake") and
                    not (infos.get(p.mat) and infos[p.mat].emissive)]
            pool = sum(per_piece.get(p.idx, 0) for p in cand)
            if pool <= 0:
                continue
            r = max(0.5, 1 - excess / pool)
            for p in cand:
                cur = mesh_tris(p.low) / p.tris if p.op == "collapse" else 1.0
                p.low = collapse_mesh(p, r * cur)
                p.op = "collapse"
            log("  over budget (%s): %d pieces collapsed to %.0f%%" % (step, len(cand),
                                                                     r * 100))
    times["parts"] = time.time() - t

    # 4. the parts as nodes: body, glass, wheels and brakes about their axles
    t = time.time()
    body = objs.get("body")
    glass = objs.get("glass")
    if body is not None:
        body.name = "LOW_body"
    if glass is not None:
        glass.name = "LOW_glass"
        glass.data.attributes.new("cg_class", 'INT', 'FACE')
    wheel_info = {tag: dict(pivot=piv) for tag, piv, mem in wheels}
    nodes = {}
    for key, ob in objs.items():
        if ":" not in key:
            continue
        kind, tag = key.split(":")
        piv = wheel_info[tag]["pivot"]
        ob.data.transform(Matrix.Translation(-piv))
        ob.location = piv
        ob.name = "LOW_%s_%s" % (kind, tag)
        nodes[key] = ob
    times["nodes"] = time.time() - t

    # the size class, by the body's exterior (faces of class 0)
    ext = 0.0
    if body is not None and "cg_class" in body.data.attributes:
        ext = sum(p.area for p, x in zip(body.data.polygons,
                                         body.data.attributes["cg_class"].data) if x.value == 0)
    size_cls = size_class(ext)
    if A.lods is None:
        A.lods = list(size_cls["lod_budgets"])
    floors = size_cls["texel_floor_px_per_m"]
    log("size class %s (body exterior %.1f m2): LODs %s, texel floor %s" % (
        size_cls["name"], ext, A.lods, floors))

    # 5. normals, UVs
    t = time.time()
    for ob in [body, glass] + list(nodes.values()):
        if ob is not None:
            set_normals(ob.data)
    uvinfo = {}
    if body is not None:
        relief = [p for p in pieces if p.op == "relief" and p.part == "body"]
        marked = detail_faces(body, relief)
        floor_px = TEXEL_FLOOR["body"] * A.body_size / 4096
        fine = fine_relief(relief, floor_px)
        log("fine relief (under %.0f mm wide): %s" % (
            1000 * DETAIL_FINE_PX / floor_px, sorted({p.ob.name for p in fine})))
        uvinfo["body"] = unwrap(body, A.body_size, boost=marked, floor=floor_px,
                                fine=detail_faces(body, fine))
        # (the detail boost keeps the standard floor's margin in every class: the large
        # class's lower floor is what the check asks, not room to spend on detail)
    if glass is not None:
        unwrap(glass, 1024)
    prim = [nodes[k] for k in sorted(nodes) if k not in twins]
    wheel_bake = None
    disc_ob, disc_reach = None, 0.0
    if prim:
        # the primaries joined (in place) for one unwrap, then their UVs handed back
        ms = []
        for ob in prim:
            me = ob.data.copy()
            me.transform(Matrix.Translation(ob.location))
            ms.append(me)
        # the far LODs' rim faces: a disc on each primary wheel's outside, unwrapped with
        # the wheels (an island of its own) and baked from the wheel as seen along its axle
        discs = [rim_disc(ob, i) for i, ob in enumerate(prim)]
        ms += [d[0] for d in discs if d is not None]
        disc_reach = max([d[1] for d in discs if d is not None] or [0.0])
        wheel_bake = join_meshes("LOW_wheels_bake", ms, low_coll)
        uvinfo["wheels"] = unwrap(wheel_bake, A.wheel_size)
        uv = wheel_bake.data.uv_layers.active.data
        U = [0.0] * (2 * len(uv))
        uv.foreach_get("uv", U)
        o = 0
        for ob in prim:
            me = ob.data
            if not me.uv_layers:
                me.uv_layers.new(name="UVMap")
            n = len(me.loops)
            me.uv_layers.active.data.foreach_set("uv", U[2 * o:2 * (o + n)])
            o += n
        disc_ob = split_discs(wheel_bake, prim, low_coll, disc_reach)
        for key, src_key in twins.items():
            old = nodes[key]
            me = old.data
            piv = old.location.copy()
            src_ob = nodes[src_key]
            if (piv.y > 0) != (src_ob.location.y > 0):
                new = mirror_copy(src_ob, "tmp_twin", low_coll)
            else:                   # the same wheel further along: a copy
                new = new_obj("tmp_twin", src_ob.data.copy(), low_coll)
            new.location = piv
            bpy.data.objects.remove(old)
            bpy.data.meshes.remove(me)
            nodes[key] = new
            new.name = "LOW_%s_%s" % tuple(key.split(":"))
            set_normals(new.data)
    times["uv"] = time.time() - t
    texel = {}
    if body is not None:
        texel["body"] = texel_stats(body, A.body_size)
    if wheel_bake is not None:
        texel["wheels"] = texel_stats(wheel_bake, A.wheel_size)
    log("texel density px/m: %s" % json.dumps(texel))

    # every part in triangles before the bakes, so the bake, the file and an engine all see
    # the same ones (below)
    n_tri = sum(triangulate_low(o) for o in [body, glass, wheel_bake] + list(nodes.values())
                if o is not None)
    log("faces of four corners or more cut into triangles before the bakes: %d" % n_tri)

    # 6. bakes
    t = time.time()
    emax, clipped = emissive_scale(infos, [o for o in [body] + list(nodes.values()) if o])
    if clipped:
        log("emissive scale %.2f; cabin-only emitters clipped to it: %s" % (emax, clipped))
    sources = {"body": [], "wheels": []}
    replaced = {"body": set(), "wheels": set()}
    relief = {"body": [], "wheels": []}
    for p in pieces:
        if p.op == "keep" or p.part == "glass":
            continue
        slot = "body" if p.part == "body" else "wheels"
        if p.ob not in sources[slot]:
            sources[slot].append(p.ob)
        if p.op in ("lathe", "collapse"):
            replaced[slot].add(p.idx)
        if p.op == "relief" and p.ob not in relief[slot]:
            relief[slot].append(p.ob)
    for k in range(len(cards)):
        replaced["body"].add(-2 - k)
    slot_mats = {}
    chans = {"body": [], "wheels": []}
    for slot, ob in (("body", body), ("wheels", wheel_bake)):
        if ob is None:
            continue
        for i, m in enumerate(ob.data.materials):
            if m is None:
                continue
            if (slot, m.name) not in slot_mats:
                cp, ch = slot_copy(m, slot, infos, emax)
                slot_mats[(slot, m.name)] = cp
                chans[slot].append(ch)
            ob.data.materials[i] = slot_mats[(slot, m.name)]
    if disc_ob is not None:     # the discs bake into the wheels' images (their slot copies)
        for i in range(min(len(disc_ob.data.materials), len(wheel_bake.data.materials))):
            disc_ob.data.materials[i] = wheel_bake.data.materials[i]
    # the rim discs' sources: every object of the primary wheels
    tags = {k.split(":")[1] for k in nodes if k not in twins and k.startswith("wheel:")}
    disc_src = [o for tag, piv, mem in wheels if tag in tags for o in mem
                if o.type in ('MESH', 'CURVE', 'FONT', 'SURFACE')] if disc_ob is not None else []
    src_chans = {}
    for slot in ("body", "wheels"):
        for ob in sources[slot] + (disc_src if slot == "wheels" else []):
            for m in ob.data.materials:
                if m is not None and m.name not in src_chans:
                    src_chans[m.name] = Channels(infos.get(m.name) or MatInfo(m), infos, emax,
                                                 True, False)
    files = {}
    glass_hide = [p.ob for p in pieces if p.part == "glass"] + ([glass] if glass else [])
    node_obs = list(nodes.values())
    for slot, target, size in (("body", body, A.body_size), ("wheels", wheel_bake,
                                                              A.wheel_size)):
        if target is None:
            continue
        rec = receiver_of(target, replaced[slot], sources[slot], relief[slot], low_coll)
        srcs = sources[slot]
        sc = [src_chans[m.name] for o in srcs for m in o.data.materials if m is not None]
        sc = list({id(c): c for c in sc}.values())
        log("baking %s: %d faces, %d of them under baked-down detail, %d source objects" % (
            slot, len(target.data.polygons), len(rec.data.polygons) if rec else 0, len(srcs)))
        hide = glass_hide + ([wheel_bake] if slot == "body" and wheel_bake else node_obs
                             if slot == "wheels" else [])
        extra = None
        if slot == "wheels" and disc_ob is not None and disc_src:
            dc = [src_chans[m.name] for o in disc_src for m in o.data.materials
                  if m is not None]
            extra = (disc_ob, disc_src, list({id(c): c for c in dc}.values()), disc_reach)
        files[slot] = bake_slot(slot, [target], rec, srcs, chans[slot], sc, size, work,
                                A.samples, K, low_coll, hide, extra)
        if rec is not None:
            me = rec.data
            bpy.data.objects.remove(rec)
            bpy.data.meshes.remove(me)
    times["bake"] = time.time() - t

    # 7. LODs, collision, export
    t = time.time()
    parts_final = []
    if body is not None:
        mark_emit(body, infos)
        single_slot(body, "body")
        parts_final.append(("body", body))
    if glass is not None:
        single_slot(glass, "glass")
        parts_final.append(("glass", glass))
    for key in sorted(nodes, key=lambda k: (k.split(":")[0] != "wheel", k)):
        single_slot(nodes[key], "wheels")
        kind, tag = key.split(":")
        parts_final.append(("%s_%s" % (kind, tag), nodes[key]))
    if A.keep_work:
        save_lod_input(work, parts_final)
    lods = make_lods(parts_final, A.lods, low_coll, work)
    hulls = collision([o for nm, o in parts_final if nm in ("body", "glass")])
    hull_obs = []
    for i, me in enumerate(hulls):
        hull_obs.append(new_obj("UCX_body_%02d" % i, me, low_coll))
    names = [nm for nm, _ in parts_final]
    lod_rows = export_lods(out, lods, names, A.lods)
    export_glb(os.path.join(out, "collision.glb"), hull_obs, [o.name for o in hull_obs])
    times["lods_export"] = time.time() - t

    # 8. pack.json
    lo = [min((o.matrix_world @ v.co)[i] for o in lods[0]["objs"] for v in o.data.vertices)
          for i in range(3)]
    hi = [max((o.matrix_world @ v.co)[i] for o in lods[0]["objs"] for v in o.data.vertices)
          for i in range(3)]
    body_lo = min(v.co.z for v in body.data.vertices) if body is not None else 0.0
    parts_json = []
    axles = sorted({round(wheel_info[t]["pivot"].x, 3) for t in wheel_info}, reverse=True)
    for nm, o in parts_final:
        row = dict(name=nm, material="glass" if nm == "glass" else
                   ("wheels" if nm.startswith(("wheel_", "brake_")) else "body"),
                   pivot=[round(x, 5) for x in o.location])
        if nm in ("body", "glass"):
            row["kind"] = nm
        else:
            kind, tag = nm.split("_", 1)
            row["kind"] = kind
            piv = wheel_info[tag]["pivot"]
            tire = next(p for p in pieces if p.ob.name == "tire." + tag)
            co = [V3(v.vector) for v in tire.me.attributes["cg_obj"].data]
            row["radius"] = round(max(sqrt(c.x * c.x + c.z * c.z) for c in co), 4)
            row["width"] = round(max(c.y for c in co) - min(c.y for c in co), 4)
            row["side"] = "left" if piv.y > 0 else "right"
            row["axle"] = axles.index(round(piv.x, 3))
            row["steers"] = row["axle"] == 0 and len(axles) > 1
            row["spins"] = kind == "wheel"
            if kind == "brake":
                row["follows"] = "wheel_" + tag
            tw = twins.get(kind + ":" + tag)
            row["uv_shared_with"] = tw.replace(":", "_") if tw else None
        parts_json.append(row)
    wl = [r for r in parts_json if r["kind"] == "wheel"]
    colors = {}
    for ch, name, key in ((0, "paint", "primary"), (1, "paint2", "secondary"),
                          (2, "caliper", "accent")):
        mi = infos.get(name)
        if mi is None or mi.color is None:
            continue
        b = mi.b
        colors[key] = dict(color=[round(x, 4) for x in mi.color], channel="RGB"[ch],
                           metallic=round(val(b, "Metallic", 0.0), 3),
                           roughness=round(val(b, "Roughness", 0.5), 3),
                           coat=round(val(b, "Coat Weight", 0.0), 3))
    tinted = sorted({mi.name for mi in infos.values() if mi.channel is not None})
    baked_down = []
    for p in pieces:
        if p.op == "keep" and p.over:
            baked_down.append(dict(piece=p.name, op="lod0_only", triangles=p.tris,
                                   relief_mm=round(p.relief * 1000, 1) if p.relief else None,
                                   into="LOD0 as it is, left out from LOD1"))
        if p.op != "keep":
            baked_down.append(dict(piece=p.name, op=p.op, triangles=p.tris,
                                   relief_mm=round(p.relief * 1000, 1) if p.relief else None,
                                   into="card" if p.op == "card_src" else
                                   ("surface under it" if p.op == "relief" else p.op),
                                   **({"kept_at_lod0": True} if p.over else {})))
    # the glass's own material: the one most of the glass area wears (a car may tune its
    # own, a dome's lower IOR), else the kit's
    garea = {}
    for p in pieces:
        if p.part == "glass" and p.mat in infos:
            garea[p.mat] = garea.get(p.mat, 0.0) + sum(f.area for f in p.me.polygons)
    gls = infos.get(max(garea, key=lambda m: (garea[m], m)) if garea else "glass") or \
        infos.get("glass")
    glass_params = dict(material=gls.name if gls else None,color=list(gls.color) if gls and gls.color else [0.3, 0.33, 0.36],
                        roughness=round(val(gls.b, "Roughness", 0.0), 3) if gls else 0.0,
                        ior=round(val(gls.b, "IOR", 1.5), 3) if gls else 1.5,
                        transmission=1.0, opaque_from_lod=2)
    pack = dict(
        format=FORMAT, version=VERSION, car=A.car, title=title,
        frame=dict(x="forward", y="left", z="up", units="m",
                   origin="on the ground under the middle of the car",
                   gltf="the glTF files use glTF's own axes (+Y up); importers convert"),
        source=dict(script="vehicles/cars/%s.py" % A.car, script_sha256=sha256(script),
                    carkit_sha256=sha256(os.path.join(HERE, "carkit.py")),
                    game_sha256=sha256(os.path.abspath(__file__)),
                    original_triangles=orig_tris, original_objects=n_objects),
        kind="wheeled" if wl else "hover",
        dimensions=dict(length=round(hi[0] - lo[0], 4), width=round(hi[1] - lo[1], 4),
                        height=round(hi[2] - lo[2], 4), min=[round(x, 4) for x in lo],
                        max=[round(x, 4) for x in hi]),
        wheelbase=round(axles[0] - axles[-1], 4) if len(axles) > 1 else None,
        track={str(i): round(max(r["pivot"][1] for r in wl if r["axle"] == i) -
                             min(r["pivot"][1] for r in wl if r["axle"] == i), 4)
               for i in range(len(axles))} if wl else None,
        ride_height=round(body_lo, 4),
        lods=lod_rows,
        parts=parts_json,
        materials=dict(
            body=slot_json("body", A.body_size, emax) if body is not None else None,
            wheels=slot_json("wheels", A.wheel_size, emax) if wheel_bake is not None else None,
            glass=dict(textures={}, params=glass_params)),
        colors=colors, tinted_materials=tinted,
        emissive_strength=round(emax, 4), emissive_clipped=clipped,
        micro_detail=dict(materials=micro, note="finer than a texel, not baked (the bake "
                          "holds their mean): the paint's flake (2600 cells a meter, bump "
                          "0.06) and textures such as the carbon weave, for the engine's "
                          "detail maps"),
        lights=lights_of(pieces, infos),
        collision=dict(file="collision.glb", hulls=[
            dict(name=o.name, vertices=len(o.data.vertices), triangles=mesh_tris(o.data))
            for o in hull_obs]),
        views=dict(hero=hero_view, studio=studio), cameras=cams,
        baked_down=baked_down,
        size_class=dict(size_cls, lod_budgets=list(A.lods)),
        uv=dict(islands=uvinfo, texel_px_per_m=texel,
                detail_boost=round(body.get("cg_detail_boost", 1.0), 3) if body else None,
                texel_floor_px_per_m={k: round(v * (A.body_size if k == "body"
                                                    else A.wheel_size) /
                                               (4096 if k == "body" else 2048), 1)
                                      for k, v in floors.items()}),
        build=dict(test=A.test, samples=A.samples, seconds={k: round(v, 1)
                                                           for k, v in times.items()}),
    )
    with open(os.path.join(out, "pack.json"), "w") as f:
        json.dump(pack, f, indent=1)
    log("wrote pack.json; LODs %s" % [r["triangles"] for r in lod_rows])
    return pack


def emissive_scale(infos, obs):
    """The emissive texture's 1.0: the strongest emitter seen from outside. An emitter
    only ever seen through glass (a cabin's ceiling light) does not count, so it cannot
    squeeze the 8-bit range of the lamps; it is clipped to the scale. A baked-down emitter
    (no faces of its own left) counts. Returns (scale, [materials clipped])."""
    seen = {}
    for ob in obs:
        me = ob.data
        cls = me.attributes.get("cg_class")
        for poly in me.polygons:
            m = me.materials[poly.material_index] if me.materials else None
            if m is None:
                continue
            k = cls.data[poly.index].value if cls is not None else 0
            seen.setdefault(m.name, set()).add(k)
    em = [mi for mi in infos.values() if mi.emissive]
    cabin = {mi.name for mi in em if seen.get(mi.name) == {2}}
    out = [mi.strength for mi in em if mi.name not in cabin]
    emax = max(out or [mi.strength for mi in em] or [0.0])
    return emax, sorted(mi.name for mi in em if mi.name in cabin and mi.strength > emax)


def receiver_of(target, replaced, sources, relief, coll):
    """The faces of the target the baked-down detail lands on: the replacements (cards,
    lathes, collapsed parts) and, for relief, the faces right under it: every point of a
    relief source (vertices, face and edge middles) marks the face of the target nearest
    it. A face merely near some detail is left alone. None if there are none."""
    if not sources:
        return None
    me = target.data.copy()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    lay = bm.faces.layers.int.get("cg_piece")
    keep = set()
    if lay is not None:
        keep = {f for f in bm.faces if f[lay] in replaced}
    if relief:
        M = target.matrix_world
        Mi = M.inverted()
        tree, index = under_tree(me)
        dg = bpy.context.evaluated_depsgraph_get()
        for ob in relief:
            ev = ob.evaluated_get(dg)
            m = ev.to_mesh()
            W = Mi @ ob.matrix_world
            pts = [W @ v.co for v in m.vertices] + [W @ f.center for f in m.polygons]
            vv = m.vertices
            pts += [W @ ((vv[e.vertices[0]].co + vv[e.vertices[1]].co) / 2) for e in m.edges]
            ev.to_mesh_clear()
            for q in pts:
                hit = tree.find_nearest(q, TALL_RELIEF_M + 0.004)
                if hit[2] is not None:
                    keep.add(bm.faces[index[hit[2]]])
    if relief:      # and the faces round them: a strip crosses faces between its points
        ov = bm.faces.layers.int.get("cg_over")
        ring = set()
        for f in keep:
            for v in f.verts:
                ring.update(g for g in v.link_faces if ov is None or not g[ov])
        keep |= ring
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f not in keep], context='FACES')
    if not bm.faces:
        bm.free()
        bpy.data.meshes.remove(me)
        return None
    bm.to_mesh(me)
    bm.free()
    ob = new_obj(target.name + "_receiver", me, coll)
    ob.matrix_world = target.matrix_world
    set_normals(me)
    return ob


TEX = (("base_color", "sRGB", "RGB: the color of everything that is not tinted, and on the "
        "tinted surfaces the dust and grime that lie on the paint. A: unused (1)"),
       ("normal", "linear", "RGB: tangent space normal, OpenGL convention (+Y up, glTF's); "
        "flip green for DirectX"),
       ("orm", "linear", "R: ambient occlusion, G: roughness, B: metallic, A: clear coat weight"),
       ("mask", "linear", "R: primary paint weight, G: secondary paint weight, B: accent "
        "weight, A: shade on the tinted color (crease grime, 1 = clean)"),
       ("emissive", "sRGB", "RGB: emission color times its strength over emissive_strength. "
        "A: specular level (0.5 standard, 0 for voids)"))


def slot_json(slot, size, emax):
    return dict(textures={k: dict(file="%s_%s.png" % (slot, k), size=size, color_space=cs,
                                  channels=ch) for k, cs, ch in TEX},
                params=dict(coat_roughness=0.06, emissive_strength=round(emax, 4)))


# ---------------------------------------------------------------------------------------
# proof: the pack alone in an empty scene
# ---------------------------------------------------------------------------------------
def proof_main(pack_dir, lods_only=False):
    with open(os.path.join(pack_dir, "pack.json")) as f:
        pack = json.load(f)
    out = os.path.join(pack_dir, "proof")
    saved = sys.argv
    sys.argv = [saved[0], "--", "--out", out]
    sys.path.insert(0, HERE)
    import carkit as K
    sys.argv = saved
    K.pbr("floor", (0.11, 0.11, 0.12), 0.0, 0.30)
    K.build_studio()
    K.setup_render()
    test = pack["build"]["test"]
    res = (1920, 1080) if not test else (960, 540)
    sm = max(8, int(96 * pack["build"]["samples"]))

    def material(slot, paint):
        spec = pack["materials"].get(slot)
        m = bpy.data.materials.new("proof_" + slot)
        try:
            m.use_nodes = True
        except Exception:
            pass
        nt = m.node_tree
        b = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
        N, L = nt.nodes, nt.links
        if slot in ("glass", "glass_opaque"):
            gp = pack["materials"]["glass"]["params"]
            b.inputs["IOR"].default_value = gp["ior"]
            if slot == "glass":
                b.inputs["Base Color"].default_value = (*gp["color"], 1)
                b.inputs["Roughness"].default_value = gp["roughness"]
                b.inputs["Transmission Weight"].default_value = gp["transmission"]
            else:                   # from opaque_from_lod: no cabin behind it, as an engine
                b.inputs["Base Color"].default_value = (*[c * 0.06 for c in gp["color"]], 1)
                b.inputs["Roughness"].default_value = max(0.05, gp["roughness"])
                b.inputs["Transmission Weight"].default_value = 0.0
            return m

        def tex(key, srgb):
            n = N.new('ShaderNodeTexImage')
            n.image = bpy.data.images.load(os.path.join(pack_dir, spec["textures"][key]["file"]))
            n.image.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
            n.image.alpha_mode = 'CHANNEL_PACKED'       # alpha is data, as in an engine
            n.interpolation = 'Linear'
            return n
        bc, nm, orm, mk, em = (tex("base_color", True), tex("normal", False), tex("orm", False),
                               tex("mask", False), tex("emissive", True))
        # albedo = base (1 - w) + (R P1 + G P2 + B P3) shade, w = R + G + B
        sep = N.new('ShaderNodeSeparateColor')
        L.new(mk.outputs["Color"], sep.inputs[0])

        def mul(a, bcol):
            n = N.new('ShaderNodeMixRGB')
            n.blend_type = 'MULTIPLY'
            n.inputs["Fac"].default_value = 1.0
            n.inputs["Color2"].default_value = (*bcol, 1)
            L.new(a, n.inputs["Color1"])
            return n.outputs[0]

        def add(a, c):
            n = N.new('ShaderNodeMixRGB')
            n.blend_type = 'ADD'
            n.inputs["Fac"].default_value = 1.0
            L.new(a, n.inputs["Color1"])
            L.new(c, n.inputs["Color2"])
            return n.outputs[0]
        tint = None
        for ch, key in ((0, "primary"), (1, "secondary"), (2, "accent")):
            col = paint.get(key)
            if col is None:
                continue
            g = N.new('ShaderNodeCombineColor')
            for s in g.inputs:
                L.new(sep.outputs[ch], s)
            t_ = mul(g.outputs[0], col)
            tint = t_ if tint is None else add(tint, t_)
        wsum = N.new('ShaderNodeMath')
        wsum.operation = 'ADD'
        L.new(sep.outputs[0], wsum.inputs[0])
        L.new(sep.outputs[1], wsum.inputs[1])
        w2 = N.new('ShaderNodeMath')
        w2.operation = 'ADD'
        L.new(wsum.outputs[0], w2.inputs[0])
        L.new(sep.outputs[2], w2.inputs[1])
        inv = N.new('ShaderNodeMath')
        inv.operation = 'SUBTRACT'
        inv.use_clamp = True
        inv.inputs[0].default_value = 1.0
        L.new(w2.outputs[0], inv.inputs[1])
        under = N.new('ShaderNodeMixRGB')
        under.blend_type = 'MULTIPLY'
        under.inputs["Fac"].default_value = 1.0
        L.new(bc.outputs["Color"], under.inputs["Color1"])
        g = N.new('ShaderNodeCombineColor')
        for s in g.inputs:
            L.new(inv.outputs[0], s)
        L.new(g.outputs[0], under.inputs["Color2"])
        alb = under.outputs[0]
        if tint is not None:
            sh = N.new('ShaderNodeMixRGB')
            sh.blend_type = 'MULTIPLY'
            sh.inputs["Fac"].default_value = 1.0
            L.new(tint, sh.inputs["Color1"])
            g2 = N.new('ShaderNodeCombineColor')
            for s in g2.inputs:
                L.new(mk.outputs["Alpha"], s)
            L.new(g2.outputs[0], sh.inputs["Color2"])
            alb = add(alb, sh.outputs[0])
        L.new(alb, b.inputs["Base Color"])
        so = N.new('ShaderNodeSeparateColor')
        L.new(orm.outputs["Color"], so.inputs[0])
        L.new(so.outputs[1], b.inputs["Roughness"])
        L.new(so.outputs[2], b.inputs["Metallic"])
        L.new(orm.outputs["Alpha"], b.inputs["Coat Weight"])
        b.inputs["Coat Roughness"].default_value = spec["params"]["coat_roughness"]
        nmap = N.new('ShaderNodeNormalMap')
        nmap.space = 'TANGENT'
        L.new(nm.outputs["Color"], nmap.inputs["Color"])
        L.new(nmap.outputs["Normal"], b.inputs["Normal"])
        L.new(em.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = spec["params"]["emissive_strength"]
        L.new(em.outputs["Alpha"], b.inputs["Specular IOR Level"])
        return m

    def load(lod):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=os.path.join(pack_dir, "lod%d.glb" % lod))
        new = [o for o in bpy.data.objects if o not in before]
        for o in new:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            K.CAR.objects.link(o)
        return new

    def assign(objs, mats, opaque=False):
        for o in objs:
            if o.type != 'MESH':
                continue
            for i, m in enumerate(o.data.materials):
                nm = m.name if m else ""
                key = "glass" if "glass" in nm else ("wheels" if "wheels" in nm else "body")
                if key == "glass" and opaque and "glass_opaque" in mats:
                    key = "glass_opaque"
                o.data.materials[i] = mats[key]

    def cam_from(rec):
        cd = bpy.data.cameras.new("pc")
        cd.lens = rec["lens"]
        cd.sensor_width = rec["sensor"]
        cd.clip_start, cd.clip_end = 0.1, 200
        if rec["dof"]:
            cd.dof.use_dof = True
            cd.dof.focus_distance = rec["focus"]
            cd.dof.aperture_fstop = rec["fstop"]
        ob = bpy.data.objects.new("pcam", cd)
        K.STUDIO.objects.link(ob)
        ob.matrix_world = Matrix(rec["matrix"])
        return ob

    def shot(cam, path, r, no_floor=False):
        cyc = K.STUDIO.objects.get("cyc")      # a view from under the floor hides it
        if cyc is not None:
            cyc.hide_render = bool(no_floor)
        K.SCN.camera = cam
        K.SCN.render.resolution_x, K.SCN.render.resolution_y = r
        K.SCN.cycles.samples = sm
        K.SCN.render.filepath = path
        bpy.ops.render.render(write_still=True)
        log("proof %s" % os.path.basename(path))

    paint = {k: v["color"] for k, v in pack["colors"].items()}
    mats = {s: material(s, paint) for s in ("body", "wheels", "glass")
            if pack["materials"].get(s)}
    if "glass" in mats:
        mats["glass_opaque"] = material("glass_opaque", paint)
    opaque_from = pack["materials"].get("glass", {}).get("params", {}).get("opaque_from_lod", 99)
    lod_objs = {}
    for L_ in pack["lods"]:
        lod_objs[L_["lod"]] = load(L_["lod"])
        assign(lod_objs[L_["lod"]], mats, L_["lod"] >= opaque_from)
    cams = {k: cam_from(v) for k, v in pack["cameras"].items()}
    # the studio as the original's: the car's own light energies and colors, and the parts
    # a light was linked off (a node per LOD file: body, body.001, ...)
    for lname, row in (pack["views"].get("studio") or {}).items():
        lob = K.STUDIO.objects.get(lname)
        if lob is None:
            continue
        if lob.type == 'LIGHT' and "energy" in row:
            lob.data.energy = row["energy"]
            lob.data.color = row["color"]
        if row.get("unlit"):
            rec = bpy.data.collections.new(lname + ".receivers")
            skip = set(row["unlit"])
            for ob in list(K.CAR.all_objects) + list(K.STUDIO.objects):
                if ob.type == 'MESH' and ob.name.split(".")[0] not in skip:
                    rec.objects.link(ob)
            lob.light_linking.receiver_collection = rec
            log("proof: %s does not light %s" % (lname, sorted(skip)))

    def show(lod):
        for k, objs in lod_objs.items():
            for o in objs:
                o.hide_render = k != lod
    alt = {"primary": (0.02, 0.30, 0.36), "secondary": (0.60, 0.42, 0.06),
           "accent": (0.10, 0.55, 0.12)}
    if not lods_only:
        show(0)
        for name, cam in cams.items():
            shot(cam, os.path.join(out, "baked_%s.jpg" % name), res,
                 pack["cameras"][name].get("no_floor"))
        # recolored: the primary and secondary paints swapped for others
        mats2 = {s: material(s, {k: alt[k] for k in paint}) for s in mats}
        assign(lod_objs[0], mats2)
        shot(cams["hero"], os.path.join(out, "recolor_hero.jpg"), res)
        assign(lod_objs[0], mats)
    small = (res[0] // 2, res[1] // 2)
    for k in sorted(lod_objs):
        show(k)
        shot(cams["hero"], os.path.join(out, "lod%d_hero.jpg" % k), small)
    with open(os.path.join(out, "alt_colors.json"), "w") as f:
        json.dump(alt, f)


def main_blender():
    A = blender_args()
    if A.proof:
        proof_main(os.path.abspath(A.proof), A.proof_lods)
        return
    t0 = time.time()
    py = venv_python()
    if py is None:
        raise SystemExit("no Python with PIL and numpy (set CYBERGEN_PYTHON)")
    if A.lods_only:
        pack = main_lods(A)
        pack_secs = 0.0
    else:
        pack = main_build(A)
        t = time.time()
        subprocess.run([py, os.path.abspath(__file__), "post", A.out], check=True)
        if not A.keep_work:
            shutil.rmtree(os.path.join(A.out, "work"), ignore_errors=True)
        pack_secs = time.time() - t
    t = time.time()
    rc = subprocess.run([bpy.app.binary_path, "-b", "--python-exit-code", "1", "-P",
                         os.path.abspath(__file__), "--", "--proof", A.out] +
                        (["--proof-lods"] if A.lods_only else [])).returncode
    if rc:
        raise SystemExit("proof render failed")
    proof_secs = time.time() - t
    cmd = [py, os.path.abspath(__file__), "check", A.out,
           "--seconds", "%.1f" % (time.time() - t0 + 0.0),
           "--stage-seconds", json.dumps(dict(pack["build"]["seconds"], textures=pack_secs,
                                              proof=proof_secs))]
    if A.docs:
        cmd += ["--docs", os.path.join(ROOT, "docs", "progress", "AG18", A.car)]
    rc = subprocess.run(cmd).returncode
    log("done in %.0f s; pack in %s" % (time.time() - t0, A.out))
    if rc:
        raise SystemExit("CHECKS FAILED (see %s)" % os.path.join(A.out, "game_report.json"))


# =========================================================================================
# venv side: textures, checks, the proof image
# =========================================================================================
def venv_main():
    ap = argparse.ArgumentParser(prog="python vehicles/game.py")
    ap.add_argument("what", choices=["post", "check"])
    ap.add_argument("pack")
    ap.add_argument("--docs", default=None)
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--stage-seconds", default=None)
    a = ap.parse_args()
    if a.what == "post":
        post(a.pack)
    else:
        sys.exit(check(a.pack, a.docs, a.seconds, a.stage_seconds))


def _load(path, n=None):
    import numpy as np
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    return np.asarray(im).astype(np.float32) / 255.0


def post(pack_dir):
    """The raw bakes (work/) into each slot's five textures: the detail (pass B) laid over
    the surfaces (pass A) where it was hit, channels packed."""
    import numpy as np
    from PIL import Image
    with open(os.path.join(pack_dir, "pack.json")) as f:
        pack = json.load(f)
    work = os.path.join(pack_dir, "work")
    for slot in ("body", "wheels"):
        spec = pack["materials"].get(slot)
        if not spec:
            continue
        A = {p: _load(os.path.join(work, "%s_A_%s.png" % (slot, p))) for p in PASSES}
        hasB = os.path.exists(os.path.join(work, "%s_B_BASE.png" % slot))
        B = {p: _load(os.path.join(work, "%s_B_%s.png" % (slot, p))) for p in PASSES} \
            if hasB else None
        if B is not None:
            cov = (B["SSE"][..., 2] > 0.5).astype(np.float32)[..., None]
            n = grow_detail(B, cov, slot_inside(pack_dir, pack, slot, A["BASE"].shape[0]),
                            max(2, A["BASE"].shape[0] // 512))
            print("detail grown into %d margin texels of %s" % (n, slot))
        else:
            cov = np.zeros(A["BASE"].shape[:2] + (1,), np.float32)

        def lay(p, extra=None):
            a = A[p][..., :3]
            if B is None:
                return a
            b = B[p][..., :3] if extra is None else extra
            return a * (1 - cov) + b * cov
        # the detail's own occlusion darkens its color a little (cavity), the rest as is
        lin = lambda c: np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
        enc = lambda c: np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.clip(c, 0, 1),
                                                                             1 / 2.4) - 0.055)
        if B is not None:
            cav = 0.25 + 0.75 * B["AO"][..., :1]
            bb = enc(lin(B["BASE"][..., :3]) * cav)
        else:
            bb = None
        base = lay("BASE", bb)
        nrm = lay("NORMAL")
        v = nrm * 2 - 1
        v[..., 2] = np.maximum(v[..., 2], 0.05)
        v /= np.linalg.norm(v, axis=2, keepdims=True)
        nrm = (v + 1) / 2
        ao = lay("AO")[..., :1]
        rmc = lay("RMC")
        tint = lay("TINT")
        sse = lay("SSE")
        emit = lay("EMIT")
        one = np.ones(base.shape[:2] + (1,), np.float32)

        def save(arr, key):
            arr = np.clip(arr * 255 + 0.5, 0, 255).astype(np.uint8)
            mode = "RGBA" if arr.shape[2] == 4 else "RGB"
            Image.fromarray(arr, mode).save(os.path.join(pack_dir, spec["textures"][key]["file"]),
                                            optimize=False, compress_level=6)
        save(np.concatenate([base, one], 2), "base_color")
        save(nrm, "normal")
        save(np.concatenate([ao, rmc[..., 0:1], rmc[..., 1:2], rmc[..., 2:3]], 2), "orm")
        save(np.concatenate([tint, sse[..., 0:1]], 2), "mask")
        save(np.concatenate([emit, sse[..., 1:2]], 2), "emissive")
        print("textures for %s: %d px, detail over %.1f%% of the texels" % (
            slot, base.shape[0], 100 * float(cov.mean())))


def slot_inside(pack_dir, pack, slot, res):
    """The texels some LOD0 triangle of the slot covers (image rows; PIL's fill)."""
    import numpy as np
    from PIL import Image, ImageDraw
    g = read_glb(os.path.join(pack_dir, pack["lods"][0]["file"]))
    im = Image.new("1", (res, res), 0)
    d = ImageDraw.Draw(im)
    for nd in g.values():
        for pr in nd["prims"]:
            if slot not in pr["material"] or pr["uv"] is None:
                continue
            T = pr["uv"][pr["idx"]] * res - 0.5          # v is already down in glTF
            for t in T.tolist():
                d.polygon([tuple(q) for q in t], fill=1)
    return np.asarray(im, dtype=bool)


def grow_detail(B, cov, inside, steps):
    """The baked-down detail (pass B, baked with no margin: a margin would spill it onto
    faces that are not under it) carried out into the margin texels round its islands,
    steps texels at most, each the mean of its covered neighbors, so a seam across a
    lettering or a lamp samples the detail on both sides, not the paint under it. Changes
    B and cov in place; returns the texels grown."""
    import numpy as np
    c = cov[..., 0] > 0.5
    out = ~inside
    H, W = c.shape
    nbr = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
    grown = 0
    for _ in range(steps):
        nb = np.zeros((H, W), np.uint8)
        for dy, dx in nbr:
            nb += np.roll(c, (dy, dx), axis=(0, 1))
        ys, xs = np.nonzero(out & ~c & (nb > 0))
        if len(ys) == 0:
            break
        for arr in B.values():
            acc = np.zeros((len(ys), arr.shape[2]), np.float32)
            for dy, dx in nbr:
                yy, xx = (ys - dy) % H, (xs - dx) % W
                acc += arr[yy, xx] * c[yy, xx][:, None]
            arr[ys, xs] = acc / nb[ys, xs][:, None]
        c[ys, xs] = True
        grown += len(ys)
    cov[..., 0] = c
    return grown


# ---- glTF reading (numpy) ------------------------------------------------------------
def read_glb(path):
    import struct
    import numpy as np
    with open(path, "rb") as f:
        data = f.read()
    magic, ver, length = struct.unpack("<III", data[:12])
    if magic != 0x46546C67:
        raise ValueError("not a GLB: " + path)
    off = 12
    js, binc = None, b""
    while off < length:
        cl, ct = struct.unpack("<II", data[off:off + 8])
        chunk = data[off + 8:off + 8 + cl]
        if ct == 0x4E4F534A:
            js = json.loads(chunk.decode("utf-8"))
        elif ct == 0x004E4942:
            binc = chunk
        off += 8 + cl
    comp = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def acc(i):
        a = js["accessors"][i]
        bv = js["bufferViews"][a["bufferView"]]
        dt = np.dtype(comp[a["componentType"]])
        n = ncomp[a["type"]]
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", 0)
        if stride and stride != dt.itemsize * n:
            raw = np.frombuffer(binc, np.uint8, count=stride * a["count"], offset=start)
            arr = np.ndarray((a["count"], n), dt, raw.data, 0, (stride, dt.itemsize))
            return np.array(arr)
        return np.frombuffer(binc, dt, count=a["count"] * n, offset=start).reshape(-1, n)

    nodes = {}
    for nd in js.get("nodes", []):
        if "mesh" not in nd:
            continue
        t = np.array(nd.get("translation", [0, 0, 0]), np.float64)
        prims = []
        for pr in js["meshes"][nd["mesh"]]["primitives"]:
            pos = acc(pr["attributes"]["POSITION"]).astype(np.float64)
            uv = acc(pr["attributes"]["TEXCOORD_0"]).astype(np.float64) \
                if "TEXCOORD_0" in pr["attributes"] else None
            idx = acc(pr["indices"]).reshape(-1) if "indices" in pr else np.arange(len(pos))
            mat = js["materials"][pr["material"]]["name"] if "material" in pr else ""
            prims.append(dict(pos=pos, uv=uv, idx=idx.reshape(-1, 3), material=mat))
        nodes[nd["name"]] = dict(t=t, rot=nd.get("rotation"), prims=prims)
    return nodes


def to_car(p):
    """glTF (+Y up) to the car's frame (x forward, y left, z up)."""
    import numpy as np
    p = np.asarray(p)
    return np.stack([p[..., 0], -p[..., 2], p[..., 1]], axis=-1)


def uv_overlap(tris_uv, res=2048):
    """Share of the covered texels (pixel centers at res x res) that two or more triangles
    cover."""
    import numpy as np
    cnt = raster_count(tris_uv, res)
    cov = int((cnt > 0).sum())
    over = int((cnt > 1).sum())
    out_of_unit = float(((tris_uv < -1e-4) | (tris_uv > 1 + 1e-4)).any(axis=2).mean())
    return over / max(cov, 1), cov / (res * res), out_of_unit


def raster_count(tris_uv, res):
    """How many triangles (UVs with v down, as image rows) cover each pixel center."""
    import numpy as np
    cnt = np.zeros((res, res), np.uint16)
    T = tris_uv * res - 0.5                        # pixel centers at integers
    x0 = np.floor(T[:, :, 0].min(1)).astype(int) + 1
    x1 = np.floor(T[:, :, 0].max(1)).astype(int)
    y0 = np.floor(T[:, :, 1].min(1)).astype(int) + 1
    y1 = np.floor(T[:, :, 1].max(1)).astype(int)
    w = x1 - x0 + 1
    h = y1 - y0 + 1
    ok = (w > 0) & (h > 0)
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    ok &= np.abs(area) > 1e-12
    sz = np.maximum(w, h)
    for lo, hi in ((1, 4), (5, 8), (9, 16), (17, 32), (33, 64), (65, 128), (129, 4096)):
        sel = np.where(ok & (sz >= lo) & (sz <= hi))[0]
        for chunk in np.array_split(sel, max(1, len(sel) * hi * hi // 4000000 + 1)):
            if len(chunk) == 0:
                continue
            gy, gx = np.mgrid[0:hi, 0:hi]
            X = x0[chunk, None, None] + gx[None]
            Y = y0[chunk, None, None] + gy[None]
            inb = (gx[None] < w[chunk, None, None]) & (gy[None] < h[chunk, None, None])
            s = np.sign(area[chunk])[:, None, None]

            def edge(p, q):
                return s * ((q[chunk, 0, None, None] - p[chunk, 0, None, None]) *
                            (Y - p[chunk, 1, None, None]) -
                            (q[chunk, 1, None, None] - p[chunk, 1, None, None]) *
                            (X - p[chunk, 0, None, None]))
            m = inb & (edge(a, b) > 0) & (edge(b, c) > 0) & (edge(c, a) > 0)
            m &= (X >= 0) & (X < res) & (Y >= 0) & (Y < res)
            np.add.at(cnt, (Y[m], X[m]), 1)
    return cnt


def check(pack_dir, docs, seconds, stage_seconds):
    import numpy as np
    from PIL import Image
    with open(os.path.join(pack_dir, "pack.json")) as f:
        pack = json.load(f)
    checks = []

    def ok(name, cond, detail):
        checks.append(dict(check=name, ok=bool(cond), detail=detail))

    # files present and readable
    files = [r["file"] for r in pack["lods"]] + [pack["collision"]["file"]]
    for slot, spec in pack["materials"].items():
        if spec:
            files += [t["file"] for t in spec["textures"].values()]
    missing, bad = [], []
    glbs = {}
    for fn in files:
        p = os.path.join(pack_dir, fn)
        if not os.path.exists(p):
            missing.append(fn)
            continue
        try:
            if fn.endswith(".glb"):
                glbs[fn] = read_glb(p)
            else:
                with Image.open(p) as im:
                    im.load()
                    want = next(t["size"] for s in pack["materials"].values() if s
                                for t in s["textures"].values() if t["file"] == fn)
                    if im.size != (want, want):
                        bad.append("%s is %s, not %d" % (fn, im.size, want))
        except Exception as e:
            bad.append("%s: %s" % (fn, e))
    ok("files", not missing and not bad, dict(files=len(files), missing=missing, unreadable=bad))

    # budgets per LOD
    rows = []
    for r in pack["lods"]:
        g = glbs.get(r["file"])
        if g is None:
            continue
        n = sum(len(pr["idx"]) for nd in g.values() for pr in nd["prims"])
        tol = 1.0 if r["lod"] == 0 else 1.1
        rows.append(dict(lod=r["lod"], triangles=n, budget=r["budget"],
                         ok=n <= r["budget"] * tol))
    ok("budgets", all(x["ok"] for x in rows), rows)

    # UV overlap per slot (LOD0; a node sharing another's UVs counted once)
    g0 = glbs.get(pack["lods"][0]["file"], {})
    shared = {p["name"] for p in pack["parts"] if p.get("uv_shared_with")}
    uvres = {}
    for slot in ("body", "wheels"):
        tris = []
        for name, nd in g0.items():
            if name in shared:
                continue
            for pr in nd["prims"]:
                if slot in pr["material"] and pr["uv"] is not None:
                    tris.append(pr["uv"][pr["idx"]])
        if not tris:
            continue
        T = np.concatenate(tris)
        T = T.copy()
        T[..., 1] = 1 - T[..., 1]
        ov, cover, outside = uv_overlap(T)
        uvres[slot] = dict(overlap=round(ov, 5), coverage=round(cover, 4),
                           outside_unit=round(outside, 5))
    ok("uv_overlap", all(v["overlap"] <= 0.005 and v["outside_unit"] <= 0.001
                         for v in uvres.values()),
       dict(limit=0.005, slots=uvres))

    # texel density on the exterior (measured in Blender on the face classes)
    tex = pack["uv"]["texel_px_per_m"]
    floors = pack["uv"]["texel_floor_px_per_m"]
    td = {}
    for slot, st in tex.items():
        ext = st.get("exterior")
        if ext:
            td[slot] = dict(p5=ext["p5"], median=ext["median"], floor=floors[slot],
                            ok=ext["p5"] >= floors[slot])
    ok("texel_density", all(v["ok"] for v in td.values()), td)

    # wheel pivots on their axles
    wrows = []
    for part in pack["parts"]:
        if part["kind"] != "wheel":
            continue
        nd = g0.get(part["name"])
        if nd is None:
            wrows.append(dict(part=part["name"], ok=False, why="missing"))
            continue
        P = to_car(np.concatenate([pr["pos"] for pr in nd["prims"]]))
        piv = to_car(nd["t"])
        r = np.sqrt(P[:, 0] ** 2 + P[:, 2] ** 2)
        tread = P[r > 0.94 * r.max()]
        cx = (tread[:, 0].max() + tread[:, 0].min()) / 2
        cz = (tread[:, 2].max() + tread[:, 2].min()) / 2
        cy = (tread[:, 1].max() + tread[:, 1].min()) / 2
        d = dict(part=part["name"], pivot=[round(float(x), 4) for x in piv],
                 center_offset_mm=[round(float(cx) * 1000, 2), round(float(cy) * 1000, 2),
                                   round(float(cz) * 1000, 2)],
                 radius=round(float(r.max()), 4), radius_pack=part["radius"],
                 json_pivot=part["pivot"])
        d["ok"] = bool(abs(cx) < 0.003 and abs(cz) < 0.003 and abs(cy) < 0.006 and
                       abs(r.max() - part["radius"]) < 0.004 and
                       np.abs(np.array(part["pivot"]) - piv).max() < 1e-3 and
                       piv[2] >= r.max() - 0.012)
        wrows.append(d)
    ok("wheel_pivots", all(x["ok"] for x in wrows), wrows)

    # LOD bounds match LOD0's
    def bounds(g):
        P = np.concatenate([to_car(pr["pos"] + nd["t"]) for nd in g.values()
                            for pr in nd["prims"]])
        return P.min(0), P.max(0)
    lo0, hi0 = bounds(g0)
    brow = []
    for r in pack["lods"][1:]:
        g = glbs.get(r["file"])
        if g is None:
            continue
        lo, hi = bounds(g)
        tol = np.maximum(0.02, 0.015 * (hi0 - lo0))
        dev = np.maximum(np.abs(lo - lo0), np.abs(hi - hi0))
        brow.append(dict(lod=r["lod"], deviation_m=[round(float(x), 4) for x in dev],
                         tolerance_m=[round(float(x), 4) for x in tol],
                         ok=bool((dev <= tol).all())))
    ok("lod_bounds", all(x["ok"] for x in brow), brow)

    # LODs drawn as LOD0: shading normals and textures measured against it (make_lods)
    frow = []
    for r in pack["lods"][1:]:
        f, lim = r.get("fidelity"), FID_LIMITS.get(r["lod"])
        if lim is None:
            continue
        if f is None:
            frow.append(dict(lod=r["lod"], ok=False, why="not measured"))
            continue
        good = (lim["p95"] is None or f["normal_p95_deg"] <= lim["p95"]) and \
            f["bent_share"] <= lim["bent"] and \
            (f["texture_share"] is None or f["texture_share"] <= lim["tex"])
        frow.append(dict(f, lod=r["lod"], limits=lim, ok=bool(good)))
    ok("lod_fidelity", all(x["ok"] for x in frow), frow)

    # collision: a handful of hulls
    gc = glbs.get(pack["collision"]["file"], {})
    nh = len(gc)
    ok("collision", 4 <= nh <= 12, dict(hulls=nh, vertices=[
        int(sum(len(pr["pos"]) for pr in nd["prims"])) for nd in gc.values()]))

    size = sum(os.path.getsize(os.path.join(pack_dir, f)) for f in os.listdir(pack_dir)
               if os.path.isfile(os.path.join(pack_dir, f)))
    tex_sizes = {s: v["textures"]["base_color"]["size"] for s, v in pack["materials"].items()
                 if v and v.get("textures")}
    groups = {}
    for b in pack["baked_down"]:
        groups.setdefault(b["op"], []).append(b)
    report = dict(
        car=pack["car"], title=pack["title"], ok=all(c["ok"] for c in checks),
        triangles=dict(original=pack["source"]["original_triangles"],
                       lods=[r["triangles"] for r in pack["lods"]],
                       lod0_parts=pack["lods"][0]["parts"]),
        objects=dict(original=pack["source"]["original_objects"], parts=len(pack["parts"])),
        size_class=pack.get("size_class"),
        textures=tex_sizes, pack_bytes=size, seconds=seconds,
        stage_seconds=json.loads(stage_seconds) if stage_seconds else None,
        baked_down={k: dict(pieces=len(v), triangles=sum(x["triangles"] for x in v),
                            names=sorted({x["piece"].split("#")[0] for x in v}))
                    for k, v in groups.items()},
        texel_px_per_m=pack["uv"]["texel_px_per_m"],
        lights=len(pack["lights"]), collision_hulls=nh,
        source=pack["source"], test=pack["build"]["test"],
        checks=checks)
    with open(os.path.join(pack_dir, "game_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    compose_proof(pack_dir, pack, report)
    if docs:
        os.makedirs(docs, exist_ok=True)
        shutil.copy(os.path.join(pack_dir, "game.jpg"), os.path.join(docs, "game.jpg"))
        small = dict(report)
        with open(os.path.join(docs, "game_report.json"), "w") as f:
            json.dump(small, f, indent=1)
    for c in checks:
        print("%s %-14s %s" % ("ok  " if c["ok"] else "FAIL", c["check"],
                               json.dumps(c["detail"])[:300]))
    print("pack %.1f MB, LODs %s" % (size / 1e6, report["triangles"]["lods"]))
    return 0 if report["ok"] else 1


def compose_proof(pack_dir, pack, report):
    """game.jpg: the original and the baked pack from the hero view, the recolored copy and
    the textures, the four LODs."""
    from PIL import Image, ImageDraw, ImageFont
    proof = os.path.join(pack_dir, "proof")
    W = 3840
    font = None
    for p in ("/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf",
              "C:/Windows/Fonts/bahnschrift.ttf"):
        if os.path.exists(p):
            font = ImageFont.truetype(p, 34)
            small_font = ImageFont.truetype(p, 26)
            break
    if font is None:
        font = small_font = ImageFont.load_default()

    def tile(path, size, label):
        im = Image.open(path).convert("RGB") if os.path.exists(path) else \
            Image.new("RGB", size, (40, 0, 0))
        im = im.resize(size, Image.LANCZOS)
        d = ImageDraw.Draw(im)
        f = font if size[0] >= 1200 else small_font
        tw = d.textlength(label, font=f)
        d.rectangle((0, 0, tw + 28, (44 if f is font else 36)), fill=(14, 14, 16))
        d.text((14, 5), label, font=f, fill=(230, 232, 236))
        return im
    lods = pack["lods"]
    half = (W // 2, W * 9 // 32)
    orig = pack["source"]["original_triangles"]
    row1 = [tile(os.path.join(proof, "original_hero.jpg"), half,
                 "original: procedural materials, %s triangles, %d objects" % (
                     format(orig, ","), pack["source"]["original_objects"])),
            tile(os.path.join(proof, "baked_hero.jpg"), half,
                 "game pack LOD0: baked textures only, %s triangles, %d parts" % (
                     format(lods[0]["triangles"], ","), len(pack["parts"])))]
    tq = (W // 8, W // 8)
    texs = []
    for slot in ("body", "wheels"):
        spec = pack["materials"].get(slot)
        if not spec:
            continue
        for key in ("base_color", "mask", "normal", "orm"):
            texs.append(tile(os.path.join(pack_dir, spec["textures"][key]["file"]), tq,
                             "%s %s" % (slot, key.replace("_", " "))))
    row2 = [tile(os.path.join(proof, "recolor_hero.jpg"), half,
                 "the same pack recolored through its paint mask")]
    tw_ = Image.new("RGB", (W // 2, half[1]), (14, 14, 16))
    for i, t in enumerate(texs[:8]):
        tw_.paste(t, ((i % 4) * (W // 8), (i // 4) * (W // 8)))
    row2.append(tw_)
    q = (W // 4, W * 9 // 64)
    row3 = [tile(os.path.join(proof, "lod%d_hero.jpg" % r["lod"]), q,
                 "LOD%d  %s triangles" % (r["lod"], format(r["triangles"], ",")))
            for r in lods]
    gap = 4
    H = half[1] * 2 + q[1] + 2 * gap + 70
    out = Image.new("RGB", (W, H), (14, 14, 16))
    y = 0
    for row in (row1, row2, row3):
        x = 0
        for im in row:
            out.paste(im, (x, y))
            x += im.width
        y += row[0].height + gap
    d = ImageDraw.Draw(out)
    fails = [c["check"] for c in report["checks"] if not c["ok"]]
    sc = pack.get("size_class") or {}
    d.text((16, H - 56), "%s (%s, %s): checks %s; textures %s; pack %.0f MB" % (
        pack["title"], pack["car"], sc.get("name", "standard"),
        "all pass" if not fails else "FAILED: " + ", ".join(fails),
        ", ".join("%s %d" % kv for kv in report["textures"].items()),
        report["pack_bytes"] / 1e6), font=font, fill=(200, 204, 210))
    out.save(os.path.join(pack_dir, "game.jpg"), quality=90)


if __name__ == "__main__":
    if bpy is not None:
        main_blender()
    else:
        venv_main()
