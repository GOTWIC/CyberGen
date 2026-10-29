"""AG6's material boards (stdlib and bpy only):

    blender -b --factory-startup -P assetgen/blender/ag6_board.py -- JOB.json

`assetgen materials board OUT` writes the job (`assetgen/materials/preview.py`): per board
(an era, the shared building parts, the streets) its materials, each drawn on a 3 x 3 m slab
(UV0 in meters, as the packs have it) with AG6's Blender materials, a label under it, under
a low sun that shows the normal maps; a window slab shows two floors of rooms by day and
one by night.
"""

import json
import math
import os
import sys
import time

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ag6_materials as AM  # noqa: E402

JOB = json.loads(open(sys.argv[sys.argv.index("--") + 1]).read())
T0 = time.time()
COLS = 6
SIZE = 3.0
GAP = 0.9
TINTS = ("cg_wall", "cg_trim", "cg_glass", "cg_roof", "cg_spandrel", "cg_patch")


def log(*a):
    print(f"[ag6 board {time.time() - T0:6.1f}s]", *a, flush=True)


def slab(name, x, z, w, h):
    """A slab facing -y (toward the camera): its front face's UV0 is meters (u along x, v up
    from its foot), stored as Blender's glTF import stores it (v flipped)."""
    me = bpy.data.meshes.new(name)
    d = 0.2
    pts = [(x, 0, z), (x + w, 0, z), (x + w, 0, z + h), (x, 0, z + h),
           (x, d, z), (x + w, d, z), (x + w, d, z + h), (x, d, z + h)]
    faces = [(0, 1, 2, 3), (5, 4, 7, 6), (4, 0, 3, 7), (1, 5, 6, 2), (3, 2, 6, 7), (4, 5, 1, 0)]
    me.from_pydata(pts, [], faces)
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            p = pts[me.loops[li].vertex_index]
            if poly.index == 0:
                u, v = p[0] - x, p[2] - z
            else:
                u, v = p[0] - x + p[1], p[2] - z
            uv.data[li].uv = (u, 1.0 - v)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def label(text, x, z):
    cu = bpy.data.curves.new(f"lbl_{text}", "FONT")
    cu.body = text
    cu.size = 0.38
    ob = bpy.data.objects.new(f"lbl_{text}", cu)
    ob.location = (x, -0.05, z)
    ob.rotation_euler = (math.radians(90), 0, 0)
    m = bpy.data.materials.new("lbl")
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.9, 0.9, 0.88,
                                                                               1)
    cu.materials.append(m)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def scene_setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    try:
        sc.eevee.taa_render_samples = 32
        sc.eevee.use_shadows = True
        sc.eevee.use_raytracing = True
    except AttributeError:
        pass
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.32, 0.36, 0.42, 1.0)
    bg.inputs["Strength"].default_value = 0.7
    sc.world = world
    sd = bpy.data.lights.new("sun", "SUN")
    sd.energy = 3.6
    sd.angle = math.radians(1.0)
    sun = bpy.data.objects.new("sun", sd)
    # low from the upper left, so the relief shows
    sun.rotation_euler = (math.radians(62.0), 0.0, math.radians(-38.0))
    sc.collection.objects.link(sun)
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 90
    names = [v.identifier for v in type(sc.view_settings).bl_rna.properties["view_transform"]
             .enum_items]
    sc.view_settings.view_transform = "AgX" if "AgX" in names else "Filmic"
    return sc


def board(b):
    sc = scene_setup()
    AM.NIGHT.clear()
    AM.IMAGES.clear()           # (a factory reset drops the images loaded for the last board)
    mats = b["materials"]
    rows = (len(mats) + COLS - 1) // COLS
    for i, it in enumerate(mats):
        r, c = divmod(i, COLS)
        x = c * (SIZE + GAP)
        z = (rows - 1 - r) * (SIZE + GAP + 0.6)
        rec = it["rec"]
        part = "streets" if rec.get("part") == "streets" else "buildings"
        glass = rec["master"] == "glass"
        ob = slab(f"s{i}", x, z, SIZE, SIZE)
        col = rec["color"]
        if part == "buildings":
            for k in TINTS:
                ob[k] = list(col)
        for k, v in (("cg_seed", 0.0), ("cg_dirt", 0.9), ("cg_wear", 0.4), ("cg_top", SIZE),
                     ("cg_streaks", 0.5), ("cg_room", SIZE / 2), ("cg_floorh", SIZE / 2),
                     ("cg_row", 1.0), ("cg_lit", 0.6), ("cg_blinds", 0.3)):
            ob[k] = v
        if glass:
            rec = dict(rec)
            rec["tint_cpd"] = 11
        m = AM.make(f"m{i}_{it['label']}", rec, JOB["files"], part)
        ob.data.materials.append(m)
        label(it["label"], x, z - 0.55)
    w = COLS * (SIZE + GAP) - GAP
    h = rows * (SIZE + GAP + 0.6)
    t = label(b.get("title", b["name"]), 0.0, h + 0.2)
    t.data.size = 0.6
    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = max(w, h * 16 / 9) * 1.06
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    cam.location = Vector((w / 2, -40.0, h / 2 - 0.6))
    cam.rotation_euler = (math.radians(90), 0, 0)
    sc.camera = cam
    sc.render.resolution_x = JOB["width"]
    sc.render.resolution_y = int(JOB["width"] * 9 / 16)
    out = []
    for mode in ("day", "night") if any(it["rec"]["master"] == "glass" for it in mats) \
            else ("day",):
        AM.set_night(1.0 if mode == "night" else 0.0)
        if mode == "night":
            sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.08
            bpy.data.objects["sun"].data.energy = 0.3
        name = f"board_{b['name']}" + ("_night" if mode == "night" else "")
        sc.render.filepath = os.path.join(JOB["out"], f"{name}.jpg")
        bpy.ops.render.render(write_still=True)
        out.append(f"{name}.jpg")
    log(b["name"], len(mats))
    return out


def main():
    files = []
    for b in JOB["boards"]:
        files += board(b)
    with open(os.path.join(JOB["out"], "ag6_report.json"), "w") as f:
        json.dump({"files": files}, f, indent=1)


main()
