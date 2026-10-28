"""Variant sheets of AG8's prop and plant families (stdlib and bpy only; Blender only draws):

    blender -b --factory-startup -P assetgen/blender/props_sheet.py -- OUT.jpg GLB... \\
        [--match PREFIX]... [--width W] [--samples N] [--night] [--title TEXT]

Imports the family packs (`BUILD/assets/props/variants/<kind>.glb`, `plants/<species>.glb`),
keeps the nodes whose names start with one of the --match prefixes (`prop.street_light.sleek.`,
`plant.oak.`; all when none), lays each family out as a row (its variants side by side, in
index order; rows in the order of the prefixes, then by name), labels the rows and renders
an isometric view from the south-west, by day or (--night) with the lamps and neon lit.
"""

import json
import math
import os
import re
import sys
import time

import bpy
from mathutils import Vector

T0 = time.time()


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:]
    o = {"out": os.path.abspath(argv[0]), "glbs": [], "match": [], "width": 2400,
         "samples": 32, "night": False, "title": ""}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in ("--width", "--samples"):
            o[a[2:]] = int(argv[i + 1])
            i += 2
        elif a in ("--match", "--title"):
            if a == "--match":
                o["match"].append(argv[i + 1])
            else:
                o["title"] = argv[i + 1]
            i += 2
        elif a == "--night":
            o["night"] = True
            i += 1
        else:
            o["glbs"].append(os.path.abspath(a))
            i += 1
    return o


GLOW = ("light.", "neon.", "screen.", "lit.", "holo.", "billboard.lamp", "sign.white")


def tune(night):
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        b = m.node_tree.nodes.get("Principled BSDF")
        if b is None:
            continue
        if m.name.startswith(GLOW):
            b.inputs["Emission Color"].default_value = b.inputs["Base Color"].default_value
            b.inputs["Emission Strength"].default_value = (14.0 if night else 3.0) * (
                1.6 if m.name.startswith("neon.") else 1.0)
        if m.name.startswith("holo."):
            b.inputs["Alpha"].default_value = 0.45
            try:
                m.surface_render_method = "BLENDED"
            except AttributeError:
                pass


def family_of(name):
    """(family, index): `prop.street_light.sleek.v3` -> (`prop.street_light.sleek`, 3)."""
    mt = re.match(r"^(.*)\.v(\d+)$", name)
    return (mt.group(1), int(mt.group(2))) if mt else (name, 0)


def main():
    o = parse()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    for f in o["glbs"]:
        bpy.ops.import_scene.gltf(filepath=f)
    keep = []
    for ob in list(bpy.data.objects):
        name = ob.name.split(".0")[0] if re.search(r"\.\d{3}$", ob.name) else ob.name
        if ob.type != "MESH" or (o["match"] and not any(name.startswith(p) for p in o["match"])):
            bpy.data.objects.remove(ob, do_unlink=True)
            continue
        ob["fam"], ob["k"] = family_of(name)
        keep.append(ob)
    order = {p: i for i, p in enumerate(o["match"])}

    def rank(f):
        for p, i in order.items():
            if f.startswith(p):
                return (i, f)
        return (len(order), f)
    fams = {}
    for ob in keep:
        fams.setdefault(ob["fam"], []).append(ob)
    rows = sorted(fams, key=rank)
    # each family a row; rows in two columns of about equal length
    sizes = {}
    for f in rows:
        dx = dy = dz = 0.0
        for ob in fams[f]:
            d = ob.dimensions
            dx, dy, dz = max(dx, d.x), max(dy, d.y), max(dz, d.z)
        sizes[f] = (max(dx, dy) + 0.8, max(dx, dy) + 0.8, dz)
    # rows in columns, as many as make the sheet about 1.5 times as wide as it is deep
    best = None
    for nc in range(1, 6):
        cols, acc = [[] for _ in range(nc)], [0.0] * nc
        target = sum(sizes[f][1] for f in rows) / nc
        c = 0
        for f in rows:
            if acc[c] >= target and c < nc - 1:
                c += 1
            cols[c].append(f)
            acc[c] += sizes[f][1]
        widths = [max((len(fams[f]) * sizes[f][0] for f in fl), default=0.0) for fl in cols]
        W = sum(widths) + 8.0 * (nc - 1)
        H = max(acc)
        score = abs(W / max(H, 1.0) - 1.5)
        if best is None or score < best[0]:
            best = (score, cols, widths)
    _, cols, widths = best
    labels = []
    x0 = 0.0
    for c, fl in enumerate(cols):
        y = 0.0
        for f in fl:
            cell = sizes[f][0]
            y -= sizes[f][1] / 2.0
            for ob in sorted(fams[f], key=lambda b: b["k"]):
                ob.location = (x0 + cell * (ob["k"] + 0.5), y, 0.0)
            labels.append((f, x0 - 0.5, y))
            y -= sizes[f][1] / 2.0
        x0 += widths[c] + 8.0
    for text, x, y in labels:
        cu = bpy.data.curves.new(f"label.{text}", "FONT")
        cu.body = text.split(".", 1)[1] if text.count(".") >= 1 else text
        cu.align_x = "RIGHT"
        cu.size = 0.9
        tob = bpy.data.objects.new(f"label.{text}", cu)
        tob.location = (x, y, 0.02)
        scene.collection.objects.link(tob)
        mat = bpy.data.materials.new("label")
        mat.use_nodes = True
        mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
            (0.9, 0.9, 0.9, 1) if o["night"] else (0.05, 0.05, 0.05, 1))
        tob.data.materials.append(mat)
    # ground
    pts = [ob.location for ob in keep]
    lo = Vector((min(p.x for p in pts) - 12.0, min(p.y for p in pts) - 8.0, 0.0))
    hi = Vector((max(p.x for p in pts) + 8.0, max(p.y for p in pts) + 8.0, 0.0))
    me = bpy.data.meshes.new("ground")
    me.from_pydata([(lo.x, lo.y, -0.01), (hi.x, lo.y, -0.01), (hi.x, hi.y, -0.01),
                    (lo.x, hi.y, -0.01)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new("ground", me)
    gm = bpy.data.materials.new("ground")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
        (0.03, 0.03, 0.035, 1) if o["night"] else (0.55, 0.55, 0.53, 1))
    me.materials.append(gm)
    scene.collection.objects.link(g)
    tune(o["night"])
    # render setup
    scene.render.engine = "BLENDER_EEVEE"
    try:
        scene.eevee.taa_render_samples = o["samples"]
    except AttributeError:
        pass
    world = bpy.data.worlds.new("w")
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.01, 0.012, 0.025, 1) if o["night"] else (0.6, 0.65, 0.72, 1)
    bg.inputs["Strength"].default_value = 0.4 if o["night"] else 1.0
    scene.world = world
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 0.15 if o["night"] else 3.5
    sun.rotation_euler = (math.radians(45.0), 0.0, math.radians(-125.0))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    cx, cy = (lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0
    d = Vector((-0.55, -1.0, 0.9)).normalized()
    cam.location = Vector((cx, cy, 0.0)) + d * 600.0
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_end = 3000.0
    scene.collection.objects.link(cam)
    scene.camera = cam
    bpy.context.view_layer.update()
    # frame every object: its bounding box corners in the camera's frame
    inv = cam.matrix_world.inverted()
    xs, ys = [], []
    for ob in keep:
        for c in ob.bound_box:
            p = inv @ (ob.matrix_world @ Vector(c))
            xs.append(p.x)
            ys.append(p.y)
    aspect = 0.62
    span = max(max(xs) - min(xs), (max(ys) - min(ys)) / aspect) * 1.06
    mid = cam.matrix_world @ Vector(((max(xs) + min(xs)) / 2.0, (max(ys) + min(ys)) / 2.0, 0.0))
    cam.location = mid - (-d) * 0.0
    cam.data.ortho_scale = span
    w = o["width"]
    scene.render.resolution_x = w
    scene.render.resolution_y = int(w * 0.62)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 88
    scene.render.filepath = o["out"]
    bpy.ops.render.render(write_still=True)
    print("AG8_SHEET_DONE " + json.dumps({"out": o["out"], "objects": len(keep),
                                          "families": len(rows),
                                          "seconds": round(time.time() - T0, 1)}))


main()
