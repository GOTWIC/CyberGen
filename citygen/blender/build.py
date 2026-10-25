"""Blender blockout builder (M4): a blockout plan (`citygen/blockout.py`) as a .blend.

Run by Blender 5.2, stdlib and bpy only (citygen itself is not importable inside Blender):

    blender -b --factory-startup -P citygen/blender/build.py -- blockout_plan.json OUT_DIR \
        [--no-render] [--no-export] [--res 1600] [--samples 16]

Writes OUT_DIR/city.blend, OUT_DIR/city.usdc (the whole city), OUT_DIR/tiles/<tile>.glb (one
per 256 m tile, custom properties as glTF extras), the renders OUT_DIR/render_top.jpg,
render_iso_<district>.jpg and render_street_<n>.jpg, and OUT_DIR/blender_report.json.
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


def build_object(o, mats, cols):
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
        elif k == "ribbon":
            md.ribbon(p, mi)
        elif k == "box":
            md.box(p["c"], p["d"], p["yaw"], mi)
        elif k == "beam":
            md.beam(p["a"], p["b"], p["w"], p["h"], mi)
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


def renders(scene, plan, out, res):
    cams = plan["cameras"]
    done = []
    top = cams["top"]
    w, h = top["size"]
    cam = camera(scene, "cam_top", True)
    cam.data.ortho_scale = max(w, h) * 1.02
    look(cam, (top["center"][0], top["center"][1], 3000.0),
         (top["center"][0], top["center"][1], 0.0))
    rw = int(res * 1.25)
    done.append(render(scene, os.path.join(out, "render_top.jpg"), rw, int(rw * h / w)))
    d = Vector(cams["iso_dir"]).normalized()
    side = d.cross(Vector((0, 0, 1))).normalized()
    up = side.cross(d).normalized()
    aspect = 1.6
    for dist in cams["districts"]:
        x0, y0, z0, x1, y1, z1 = dist["box"]
        corners = [Vector((x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        c = Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 4))
        us = [(p - c).dot(side) for p in corners]
        vs = [(p - c).dot(up) for p in corners]
        cu = (max(us) + min(us)) / 2
        cv = (max(vs) + min(vs)) / 2
        c = c + side * cu + up * cv
        width = max(max(us) - min(us), (max(vs) - min(vs)) * aspect) * 1.06
        cam = camera(scene, f"cam_iso_{dist['id']}", True)
        cam.data.ortho_scale = width
        look(cam, c - d * 4000.0, c)
        done.append(render(scene, os.path.join(out, f"render_iso_{dist['id']}.jpg"), res,
                           int(res / aspect)))
    for k, v in enumerate(cams["street"], 1):
        cam = camera(scene, f"cam_street_{k}", False)
        cam.data.lens = v["lens_mm"]
        look(cam, v["eye"], v["target"])
        done.append(render(scene, os.path.join(out, f"render_street_{k}.jpg"), res,
                           int(res * 9 / 16)))
    return done


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
    for o in plan["objects"]:
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
                              export_cameras=False, export_lights=False)
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
        "vertices": verts, "faces": faces, "materials": len(mats),
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


main()
