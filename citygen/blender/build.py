"""Blender blockout builder (M4): a blockout plan (`citygen/blockout.py`) as a .blend.

Run by Blender 5.2, stdlib and bpy only (citygen itself is not importable inside Blender):

    blender -b --factory-startup -P citygen/blender/build.py -- blockout_plan.json OUT_DIR \
        [--no-render] [--no-export] [--res 1600] [--samples 16]

Writes OUT_DIR/city.blend, OUT_DIR/city.usdc (the whole city), OUT_DIR/tiles/<tile>.glb (one
per 256 m tile, custom properties as glTF extras), the renders OUT_DIR/render_top.jpg,
render_iso_city.jpg, render_iso_<district>.jpg and render_street_<n>.jpg, and OUT_DIR/blender_report.json.
`citygen blockout` runs it; the plan decides every coordinate, this file only builds meshes
(caps with holes triangulated by `mathutils.geometry.tessellate_polygon`).
"""

import json
import math
import os
import sys
import time

import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

T0 = time.perf_counter()
DOME_STEPS = [(1.0, 0.0), (0.92388, 0.382683), (0.707107, 0.707107), (0.382683, 0.92388)]


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) < 2:
        raise SystemExit("usage: blender -b -P build.py -- blockout_plan.json OUT_DIR [...]")
    opts = {"plan": argv[0], "out": argv[1], "render": True, "export": True, "res": 1600,
            "samples": 16}
    rest = argv[2:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--no-render":
            opts["render"] = False
        elif a == "--no-export":
            opts["export"] = False
        elif a in ("--res", "--samples"):
            opts[a[2:]] = int(rest[i + 1])
            i += 1
        else:
            raise SystemExit(f"unknown option {a}")
        i += 1
    return opts


def srgb(hex_color):
    h = hex_color.lstrip("#")
    out = []
    for k in range(3):
        c = int(h[2 * k:2 * k + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


# --- scene setup ------------------------------------------------------------------------------

def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    return scene


def make_materials(plan):
    mats = {}
    for name, color in plan["materials"].items():
        mat = bpy.data.materials.new(name)
        rgb = srgb(color)
        mat.diffuse_color = (*rgb, 1.0)
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.35 if name in ("sea", "water") else 0.85
            if name.startswith("bld_") or name == "landmark":
                vary(mat.node_tree, bsdf, rgb)
        mat["citygen_material"] = name
        mats[name] = mat
    return mats


def vary(nt, bsdf, rgb):
    """Each building a little lighter or darker (Object Info random, renders only; glTF and
    USD keep the flat base color)."""
    info = nt.nodes.new("ShaderNodeObjectInfo")
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.inputs["To Min"].default_value = 0.8
    rng.inputs["To Max"].default_value = 1.15
    scale = nt.nodes.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    scale.inputs[0].default_value = rgb
    nt.links.new(info.outputs["Random"], rng.inputs["Value"])
    nt.links.new(rng.outputs["Result"], scale.inputs["Scale"])
    nt.links.new(scale.outputs["Vector"], bsdf.inputs["Base Color"])


def collection_for(path, cache):
    key = tuple(path)
    if key in cache:
        return cache[key]
    parent = bpy.context.scene.collection if len(path) == 1 else collection_for(path[:-1], cache)
    name = path[-1] if len(path) == 1 else f"{path[-1]} ({path[-2]})" if len(path) == 3 else \
        path[-1]
    col = bpy.data.collections.new(name)
    parent.children.link(col)
    cache[key] = col
    return col


# --- meshes -----------------------------------------------------------------------------------

class MeshData:
    def __init__(self):
        self.verts = []
        self.faces = []
        self.mats = []

    def v(self, x, y, z):
        self.verts.append((x, y, z))
        return len(self.verts) - 1

    def face(self, idx, mat):
        self.faces.append(idx)
        self.mats.append(mat)

    def cap(self, rings, z, mat, up=True):
        """A horizontal face from an outer ring (counterclockwise) and holes (clockwise)."""
        if len(rings) == 1:
            idx = [self.v(x, y, z) for x, y in rings[0]]
            self.face(idx if up else idx[::-1], mat)
            return
        base = len(self.verts)
        flat = []
        for ring in rings:
            for x, y in ring:
                self.v(x, y, z)
                flat.append(Vector((x, y, z)))
        lists, k = [], 0
        for ring in rings:
            lists.append(flat[k:k + len(ring)])
            k += len(ring)
        for tri in tessellate_polygon(lists):
            t = [base + i for i in tri]
            # tessellate_polygon does not keep the winding: make each triangle face up/down
            a, b, c = (self.verts[i] for i in t)
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if (cross > 0) != up:
                t = t[::-1]
            self.face(t, mat)

    def drape(self, rings, mat):
        """M13: a face from 3D rings (outer counterclockwise, holes clockwise), triangulated
        in plan, each vertex at its own height."""
        base = len(self.verts)
        flat = []
        for ring in rings:
            for x, y, z in ring:
                self.v(x, y, z)
                flat.append(Vector((x, y, 0.0)))
        lists, k = [], 0
        for ring in rings:
            lists.append(flat[k:k + len(ring)])
            k += len(ring)
        for tri in tessellate_polygon(lists):
            t = [base + i for i in tri]
            a, b, c = (self.verts[i] for i in t)
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if cross < 0:
                t = t[::-1]
            self.face(t, mat)

    def grid(self, p, mat):
        """M13: a heightfield, nx by ny points `c` apart from (x0, y0), z row by row from the
        south; the cells in `skip` left open."""
        nx, ny, c = p["nx"], p["ny"], p["c"]
        x0, y0, zs = p["x0"], p["y0"], p["z"]
        base = len(self.verts)
        for j in range(ny):
            for i in range(nx):
                self.v(x0 + i * c, y0 + j * c, zs[j * nx + i])
        skip = set(p.get("skip", []))
        for j in range(ny - 1):
            for i in range(nx - 1):
                if j * (nx - 1) + i in skip:
                    continue
                a = base + j * nx + i
                self.face([a, a + 1, a + nx + 1, a + nx], mat)

    def walls(self, ring, z0, z1, mat):
        n = len(ring)
        lo = [self.v(x, y, z0) for x, y in ring]
        hi = [self.v(x, y, z1) for x, y in ring]
        for i in range(n):
            j = (i + 1) % n
            self.face([lo[i], lo[j], hi[j], hi[i]], mat)

    def prism(self, p, mat):
        rings = [p["r"]] + p["h"]
        z0, z1, shape = p["z0"], p["z1"], p.get("s", "prism")
        if shape in ("cone", "dome"):
            self.spire(p["r"], z0, z1, mat, shape)
            return
        if shape == "ring":
            self.wheel(p["r"], z0, z1, mat)
            return
        self.cap(rings, z1, mat, up=True)
        if z0 > 0.05 or z0 < -0.05:
            self.cap(rings, z0, mat, up=False)
        for ring in rings:
            self.walls(ring, z0, z1, mat)

    def spire(self, ring, z0, z1, mat, shape):
        cx = sum(x for x, _ in ring) / len(ring)
        cy = sum(y for _, y in ring) / len(ring)
        steps = DOME_STEPS if shape == "dome" else [(1.0, 0.0)]
        prev = [self.v(x, y, z0) for x, y in ring]
        self.face(prev[::-1], mat)
        for f, s in steps[1:]:
            z = z0 + (z1 - z0) * s
            cur = [self.v(cx + (x - cx) * f, cy + (y - cy) * f, z) for x, y in ring]
            for i in range(len(ring)):
                j = (i + 1) % len(ring)
                self.face([prev[i], prev[j], cur[j], cur[i]], mat)
            prev = cur
        apex = self.v(cx, cy, z1)
        for i in range(len(ring)):
            j = (i + 1) % len(ring)
            self.face([prev[i], prev[j], apex], mat)

    def wheel(self, ring, z0, z1, mat):
        """A vertical wheel: rim and spokes in the plane of the footprint's long axis."""
        cx = sum(x for x, _ in ring) / len(ring)
        cy = sum(y for _, y in ring) / len(ring)
        far = max(ring, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
        ux, uy = far[0] - cx, far[1] - cy
        L = math.hypot(ux, uy) or 1.0
        ux, uy = ux / L, uy / L
        r = (z1 - z0) / 2.0
        zc = z0 + r
        n = 32
        pts = [(cx + ux * r * math.cos(2 * math.pi * k / n), cy + uy * r * math.cos(
            2 * math.pi * k / n), zc + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        for k in range(n):
            self.beam(pts[k], pts[(k + 1) % n], 2.0, 2.0, mat, centered=True)
        for k in range(0, n, 4):
            self.beam((cx, cy, zc), pts[k], 0.8, 0.8, mat, centered=True)

    def ribbon(self, p, mat):
        left, right, t = p["l"], p["rr"], p.get("t", 0.0)
        tl = [self.v(*q) for q in left]
        tr = [self.v(*q) for q in right]
        n = len(left)
        for i in range(n - 1):
            self.face([tr[i], tr[i + 1], tl[i + 1], tl[i]], mat)
        if t <= 0:
            return
        bl = [self.v(x, y, z - t) for x, y, z in left]
        br = [self.v(x, y, z - t) for x, y, z in right]
        for i in range(n - 1):
            self.face([bl[i], bl[i + 1], br[i + 1], br[i]], mat)
            self.face([tl[i], tl[i + 1], bl[i + 1], bl[i]], mat)
            self.face([br[i], br[i + 1], tr[i + 1], tr[i]], mat)
        self.face([tl[0], bl[0], br[0], tr[0]], mat)
        self.face([tr[-1], br[-1], bl[-1], tl[-1]], mat)

    def box(self, c, d, yaw_deg, mat):
        a = math.radians(yaw_deg)
        ux, uy = math.cos(a), math.sin(a)
        hx, hy = d[0] / 2.0, d[1] / 2.0
        corners = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
        ring = [(c[0] + ux * x - uy * y, c[1] + uy * x + ux * y) for x, y in corners]
        z0, z1 = c[2], c[2] + d[2]
        self.cap([ring], z1, mat, up=True)
        self.cap([ring], z0, mat, up=False)
        self.walls(ring, z0, z1, mat)

    def beam(self, a, b, w, h, mat, centered=False):
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        L = math.sqrt(dx * dx + dy * dy + dz * dz)
        if L < 1e-6:
            return
        d = Vector((dx, dy, dz)) / L
        side = d.cross(Vector((0, 0, 1)))
        if side.length < 1e-6:
            side = Vector((1, 0, 0))
        side.normalize()
        up = side.cross(d).normalized()
        if up.z < 0:
            up = -up
        lo = -h / 2.0 if centered else 0.0
        base = []
        for s, u in ((-1, lo), (1, lo), (1, lo + h), (-1, lo + h)):
            off = side * (s * w / 2.0) + up * u
            base.append(off)
        A, B = Vector(a), Vector(b)
        ia = [self.v(*(A + o)) for o in base]
        ib = [self.v(*(B + o)) for o in base]
        self.face(ia[::-1], mat)
        self.face(ib, mat)
        for i in range(4):
            j = (i + 1) % 4
            self.face([ia[i], ia[j], ib[j], ib[i]], mat)


def build_prototypes(plan, mats, cols):
    """One mesh object per prop and plant kind, 5 km under the city and out of the renders;
    a geometry-nodes group per kind instances it on the points of an instancing object."""
    groups = {}
    for kind, parts in sorted(plan.get("prototypes", {}).items()):
        ob, _, _ = build_object({"name": f"proto.{kind}", "parts": parts, "props": {},
                                 "collection": ["Prototypes"], "tile": "", "category": ""},
                                mats, cols, tag=False)
        ob.location = (0.0, 0.0, -5000.0)
        ob.hide_render = True
        groups[kind] = instance_group(kind, ob)
    return groups


def instance_group(kind, proto):
    ng = bpy.data.node_groups.new(f"citygen_instances.{kind}", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    iop = N.new("GeometryNodeInstanceOnPoints")
    oi = N.new("GeometryNodeObjectInfo")
    oi.transform_space = "ORIGINAL"
    oi.inputs["As Instance"].default_value = True   # USD point instancers
    oi.inputs["Object"].default_value = proto
    rot = N.new("GeometryNodeInputNamedAttribute")
    rot.data_type = "FLOAT_VECTOR"
    rot.inputs["Name"].default_value = "rot"
    scl = N.new("GeometryNodeInputNamedAttribute")
    scl.data_type = "FLOAT_VECTOR"
    scl.inputs["Name"].default_value = "scl"
    L.new(gi.outputs["Geometry"], iop.inputs["Points"])
    L.new(oi.outputs["Geometry"], iop.inputs["Instance"])
    L.new(rot.outputs["Attribute"], iop.inputs["Rotation"])
    L.new(scl.outputs["Attribute"], iop.inputs["Scale"])
    L.new(iop.outputs["Instances"], go.inputs["Geometry"])
    return ng


def build_instances(o, groups, cols):
    """An instancing object: a point per prop or plant (position, yaw, scale attributes) and
    the geometry-nodes group of its kind."""
    p = o["parts"][0]
    pts = p["pts"]
    mesh = bpy.data.meshes.new(o["name"])
    mesh.vertices.add(len(pts))
    mesh.vertices.foreach_set("co", [v for x in pts for v in x[:3]])
    a = mesh.attributes.new("rot", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", [v for x in pts for v in (0.0, 0.0, math.radians(x[3]))])
    b = mesh.attributes.new("scl", "FLOAT_VECTOR", "POINT")
    b.data.foreach_set("vector", [v for x in pts for v in x[4:7]])
    mesh.update()
    obj = bpy.data.objects.new(o["name"], mesh)
    mod = obj.modifiers.new("instances", "NODES")
    mod.node_group = groups[p["proto"]]
    for k, v in o["props"].items():
        obj[k] = v
    obj["citygen_tile"] = o["tile"]
    obj["citygen_category"] = o["category"]
    obj["citygen_instances"] = len(pts)
    collection_for(o["collection"], cols).objects.link(obj)
    return obj, len(pts)


def build_object(o, mats, cols, tag=True):
    md = MeshData()
    slots = []
    index = {}
    for p in o["parts"]:
        m = p["m"]
        if m not in index:
            index[m] = len(slots)
            slots.append(m)
        mi = index[m]
        k = p["k"]
        if k == "prism":
            md.prism(p, mi)
        elif k == "flat":
            md.cap([p["r"]] + p["h"], p["z"], mi, up=True)
        elif k == "drape":
            md.drape([p["r"]] + p["h"], mi)
        elif k == "grid":
            md.grid(p, mi)
        elif k == "ribbon":
            md.ribbon(p, mi)
        elif k == "box":
            md.box(p["c"], p["d"], p["yaw"], mi)
        elif k == "beam":
            md.beam(p["a"], p["b"], p["w"], p["h"], mi)
        elif k == "mesh":
            base = len(md.verts)
            for x, y, z in p["v"]:
                md.v(x, y, z)
            for f in p["f"]:
                md.face([base + i for i in f], mi)
    mesh = bpy.data.meshes.new(o["name"])
    mesh.from_pydata(md.verts, [], md.faces)
    for name in slots:
        mesh.materials.append(mats[name])
    if md.mats:
        mesh.polygons.foreach_set("material_index", md.mats)
    mesh.validate(clean_customdata=False)
    mesh.update()
    obj = bpy.data.objects.new(o["name"], mesh)
    for k, v in o["props"].items():
        obj[k] = v
    if tag:
        obj["citygen_tile"] = o["tile"]
        obj["citygen_category"] = o["category"]
    collection_for(o["collection"], cols).objects.link(obj)
    return obj, len(md.verts), len(md.faces)


# --- light, cameras, renders --------------------------------------------------------------------

def setup_render(scene, samples):
    scene.render.engine = "BLENDER_EEVEE"
    try:
        scene.eevee.taa_render_samples = samples
    except AttributeError:
        pass
    world = bpy.data.worlds.new("citygen_world")
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.13, 0.17, 0.27, 1.0)
        bg.inputs["Strength"].default_value = 0.9
    scene.world = world
    sun_data = bpy.data.lights.new("citygen_sun", "SUN")
    sun_data.energy = 3.5
    sun_data.angle = math.radians(1.5)
    sun = bpy.data.objects.new("citygen_sun", sun_data)
    # from the west-south-west, 40 degrees up (like the matplotlib previews)
    sun.rotation_euler = (math.radians(50.0), 0.0, math.radians(-115.0))
    scene.collection.objects.link(sun)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 90
    scene.render.film_transparent = False


def camera(scene, name, ortho):
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO" if ortho else "PERSP"
    data.clip_start = 0.5
    data.clip_end = 20000.0
    cam = bpy.data.objects.new(name, data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    return cam


def look(cam, eye, target):
    cam.location = Vector(eye)
    d = Vector(target) - Vector(eye)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def render(scene, path, w, h):
    scene.render.resolution_x = w
    scene.render.resolution_y = h
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def iso_frame(box, d, aspect):
    """Center and ortho width that frame a box (x0, y0, z0, x1, y1, z1) seen along d."""
    x0, y0, z0, x1, y1, z1 = box
    side = d.cross(Vector((0, 0, 1))).normalized()
    up = side.cross(d).normalized()
    corners = [Vector((x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    c = Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 4))
    us = [(p - c).dot(side) for p in corners]
    vs = [(p - c).dot(up) for p in corners]
    c = c + side * ((max(us) + min(us)) / 2) + up * ((max(vs) + min(vs)) / 2)
    return c, max(max(us) - min(us), (max(vs) - min(vs)) * aspect) * 1.06


def views(plan, res):
    """Every render as (name, ortho, ortho scale or lens mm, eye, target, width, height):
    the top view, the whole city isometric, one isometric view per district, the street
    views. `citygen rerender` renders a chosen few of them again at another width."""
    cams = plan["cameras"]
    out = []
    top = cams["top"]
    w, h = top["size"]
    rw = int(res * 1.25)
    cx, cy = top["center"]
    out.append(("top", True, max(w, h) * 1.02, (cx, cy, 3000.0), (cx, cy, 0.0), rw,
                int(rw * h / w)))
    d = Vector(cams["iso_dir"]).normalized()
    aspect = 1.6
    boxes = [dist["box"] for dist in cams["districts"]]
    if boxes:
        # the whole city, isometric
        box = [min(b[i] for b in boxes) for i in range(3)] + \
            [max(b[i] for b in boxes) for i in range(3, 6)]
        c, width = iso_frame(box, d, aspect)
        out.append(("iso_city", True, width, c - d * 8000.0, c, rw, int(rw / aspect)))
    for dist in cams["districts"]:
        c, width = iso_frame(dist["box"], d, aspect)
        out.append((f"iso_{dist['id']}", True, width, c - d * 4000.0, c, res,
                    int(res / aspect)))
    for k, v in enumerate(cams["street"], 1):
        out.append((f"street_{k}", False, v["lens_mm"], v["eye"], v["target"], res,
                    int(res * 9 / 16)))
    for key in ("cutaway", "deck"):
        cut = cams.get(key)
        if cut:
            # M9: the section along the longest road tunnel; M14: across the biggest deck
            # (rendered last: they cut the scene)
            out.append((key, False, cut["lens_mm"], cut["eye"], cut["target"], res,
                        int(res * 9 / 16)))
    return out


CUT_KEEP = ("ground", "water", "sea", "tunnel", "tunnel_road", "junction", "crosswalk",
            "sidewalk", "quay")


def _box_obj(name, corners_xy, z0, z1, mat=None):
    """A closed box mesh from four plan corners (counterclockwise)."""
    md = MeshData()
    md.cap([corners_xy], z1, 0, up=True)
    md.cap([corners_xy], z0, 0, up=False)
    md.walls(corners_xy, z0, z1, 0)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(md.verts, [], md.faces)
    if mat is not None:
        mesh.materials.append(mat)
    mesh.validate(clean_customdata=False)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def cutaway(scene, plan, key="cutaway"):
    """Cut the scene along a cutaway plane (M9; M14 `deck`): an earth block under the
    ground; the ground, water, streets, tunnels and the buildings across the plane cut by a
    box on the camera's side, everything else on that side hidden. Returns what to undo."""
    c = plan["cameras"][key]
    ox, oy = c["origin"]
    ux, uy = c["u"]
    nx, ny = c["n"]
    H, D = c["half_len"], c["depth"]
    z0, z1 = c["z"]

    def pt(du, dn):
        return (ox + ux * du + nx * dn, oy + uy * du + ny * dn)

    ring = [pt(-H, 0.0), pt(H, 0.0), pt(H, D), pt(-H, D)]
    if (ring[1][0] - ring[0][0]) * (ring[2][1] - ring[0][1]) - \
            (ring[1][1] - ring[0][1]) * (ring[2][0] - ring[0][0]) < 0:
        ring = ring[::-1]
    # the cutters: the box on the camera's side, and the tunnels' inner volumes (a
    # collection operand: the boolean takes their union)
    coll = bpy.data.collections.new("citygen_cutters")
    scene.collection.children.link(coll)
    # (down to 20 m above the earth's bottom: the pit keeps a floor; a deck's section keeps
    # the ground and its streets whole)
    deck = key == "deck"
    cutter = _box_obj("citygen_cutter", ring, -5.0 if deck else z0 + 20.0, z1)
    scene.collection.objects.unlink(cutter)
    coll.objects.link(cutter)
    md = MeshData()
    for p in c.get("voids", []):
        md.ribbon(p, 0)
    voids = None
    if md.faces:
        mesh = bpy.data.meshes.new("citygen_voids")
        mesh.from_pydata(md.verts, [], md.faces)
        mesh.validate(clean_customdata=False)
        mesh.update()
        voids = bpy.data.objects.new("citygen_voids", mesh)
        coll.objects.link(voids)
    coll.hide_render = True
    for ob in coll.objects:
        ob.display_type = "WIRE"
    soil_mat = bpy.data.materials.new("citygen_soil")
    soil_mat.use_nodes = True
    bsdf = soil_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*srgb("#6b5a45"), 1.0)
        bsdf.inputs["Roughness"].default_value = 0.95
    back = 500.0
    sring = [pt(-H, -back), pt(H, -back), pt(H, D * 0.5), pt(-H, D * 0.5)]
    if (sring[1][0] - sring[0][0]) * (sring[2][1] - sring[0][1]) - \
            (sring[1][1] - sring[0][1]) * (sring[2][0] - sring[0][0]) < 0:
        sring = sring[::-1]
    soil = None if deck else _box_obj("citygen_soil", sring, z0, -4.0, soil_mat)
    # a low light from the camera's side into the section (the tunnels lie under their roofs)
    fill = bpy.data.lights.new("citygen_cut_light", "SUN")
    fill.energy = 2.2
    fill.angle = math.radians(3.0)
    lamp = bpy.data.objects.new("citygen_cut_light", fill)
    d = Vector((-nx, -ny, -0.12)).normalized()
    lamp.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(lamp)
    undo = {"mods": [], "hidden": [], "objects": [cutter, lamp] + ([soil] if soil else []) +
            ([voids] if voids else []), "collection": coll}

    def side(obj):
        """(min, max) of the object's corners along n from the plane, and along u."""
        dn, du = [], []
        for v in obj.bound_box:
            w = obj.matrix_world @ Vector(v)
            dn.append((w.x - ox) * nx + (w.y - oy) * ny)
            du.append((w.x - ox) * ux + (w.y - oy) * uy)
        return min(dn), max(dn), min(du), max(du)

    tunnel_cats = ("tunnel", "tunnel_road")
    for obj in list(scene.objects):
        if obj.type != "MESH" or obj in (cutter, voids, lamp):
            continue
        a0, a1, b0, b1 = side(obj)
        if a1 <= 0.0 or a0 >= D or b1 <= -H or b0 >= H:
            continue        # away from the cut
        cat = obj.get("citygen_category", "")
        straddles = a0 < 0.0 < a1
        if deck and (cat in CUT_KEEP or cat.startswith("road_") or cat.startswith("open_")):
            continue        # (the ground stays whole in front of a deck's section)
        if obj is soil or cat in CUT_KEEP or cat.startswith("road_") or \
                cat.startswith("open_") or (straddles and cat not in tunnel_cats and
                                            obj.get("citygen_tile") is not None and
                                            not obj.modifiers):
            mod = obj.modifiers.new("citygen_cut", "BOOLEAN")
            mod.operation = "DIFFERENCE"
            mod.operand_type = "COLLECTION"
            mod.collection = coll
            try:
                mod.solver = "EXACT"
                mod.use_hole_tolerant = True
            except (AttributeError, TypeError):
                pass
            undo["mods"].append((obj, mod.name))
        elif not obj.hide_render:
            obj.hide_render = True
            undo["hidden"].append(obj)
    return undo


def uncut(undo):
    for obj, name in undo["mods"]:
        mod = obj.modifiers.get(name)
        if mod is not None:
            obj.modifiers.remove(mod)
    for obj in undo["hidden"]:
        obj.hide_render = False
    for obj in undo["objects"]:
        bpy.data.objects.remove(obj, do_unlink=True)
    if undo.get("collection") is not None:
        bpy.data.collections.remove(undo["collection"])


def render_view(scene, view, path, width=None, plan=None):
    """Render one view (from `views`) to path, at its own size or at `width` pixels wide
    (the cutaway needs the plan: it cuts the scene for its render, then puts it back)."""
    name, ortho, scale, eye, target, w, h = view
    cam = camera(scene, f"cam_{name}", ortho)
    if ortho:
        cam.data.ortho_scale = scale
    else:
        cam.data.lens = scale
    look(cam, eye, target)
    if width:
        w, h = width, int(round(width * h / w))
    undo = cutaway(scene, plan, name) if name in ("cutaway", "deck") and plan is not None \
        else None
    try:
        return render(scene, path, w, h)
    finally:
        if undo is not None:
            uncut(undo)


def renders(scene, plan, out, res):
    return [render_view(scene, v, os.path.join(out, f"render_{v[0]}.jpg"), plan=plan)
            for v in views(plan, res)]


# --- exports ------------------------------------------------------------------------------------

def export_tiles(plan, by_tile, out):
    tdir = os.path.join(out, "tiles")
    os.makedirs(tdir, exist_ok=True)
    files = []
    for t in plan["tiles"]:
        objs = by_tile.get(t["name"], [])
        if not objs:
            continue
        bpy.ops.object.select_all(action="DESELECT")
        for ob in objs:
            ob.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        path = os.path.join(tdir, t["name"] + ".glb")
        bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_format="GLB",
                                  export_extras=True, export_yup=True, export_cameras=False,
                                  export_lights=False, export_animations=False)
        files.append(path)
    bpy.ops.object.select_all(action="DESELECT")
    return files


def main():
    opts = parse_args()
    out = os.path.abspath(opts["out"])
    os.makedirs(out, exist_ok=True)
    with open(opts["plan"], encoding="utf-8") as f:
        plan = json.load(f)
    scene = reset_scene()
    scene.name = plan["city"]
    timings = {}
    t = time.perf_counter()
    mats = make_materials(plan)
    cols = {}
    by_tile, verts, faces = {}, 0, 0
    counts = {}
    groups = build_prototypes(plan, mats, cols)
    instances = 0
    for o in plan["objects"]:
        if o["parts"] and o["parts"][0]["k"] == "inst":
            # props and plants: instanced, in the .blend and the USD (point instancers), not
            # in the glTF tiles (props.csv carries them for engines)
            ob, n = build_instances(o, groups, cols)
            instances += n
        else:
            ob, nv, nf = build_object(o, mats, cols)
            by_tile.setdefault(o["tile"], []).append(ob)
            verts += nv
            faces += nf
        counts[o["category"]] = counts.get(o["category"], 0) + 1
    timings["build_s"] = round(time.perf_counter() - t, 1)
    files = {}
    t = time.perf_counter()
    blend = os.path.join(out, "city.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    files["blend"] = blend
    timings["save_s"] = round(time.perf_counter() - t, 1)
    if opts["export"]:
        t = time.perf_counter()
        usd = os.path.join(out, "city.usdc")
        bpy.ops.wm.usd_export(filepath=usd, export_materials=True, selected_objects_only=False,
                              export_cameras=False, export_lights=False, use_instancing=True)
        files["usd"] = usd
        timings["usd_s"] = round(time.perf_counter() - t, 1)
        t = time.perf_counter()
        files["gltf_tiles"] = export_tiles(plan, by_tile, out)
        timings["gltf_s"] = round(time.perf_counter() - t, 1)
    if opts["render"]:
        t = time.perf_counter()
        setup_render(scene, opts["samples"])
        files["renders"] = renders(scene, plan, out, opts["res"])
        timings["render_s"] = round(time.perf_counter() - t, 1)
    timings["total_s"] = round(time.perf_counter() - T0, 1)
    sizes = {}
    for k, v in files.items():
        paths = v if isinstance(v, list) else [v]
        sizes[k] = sum(os.path.getsize(p) for p in paths if os.path.exists(p))
    report = {
        "city": plan["city"], "blender": bpy.app.version_string,
        "objects": len(plan["objects"]), "by_category": dict(sorted(counts.items())),
        "vertices": verts, "faces": faces, "instances": instances, "materials": len(mats),
        "collections": len(cols), "tiles": len(plan["tiles"]),
        "files": {k: ([os.path.relpath(p, out) for p in v] if isinstance(v, list)
                      else os.path.relpath(v, out)) for k, v in files.items()},
        "bytes": sizes, "timings": timings,
    }
    with open(os.path.join(out, "blender_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print("CITYGEN_BLOCKOUT_DONE " + json.dumps({"objects": report["objects"],
                                                 "faces": faces, **timings}))


if __name__ == "__main__":
    main()
