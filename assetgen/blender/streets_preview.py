"""Blender preview of AG7's street packs among the blockout's buildings (stdlib and bpy only;
Blender only draws):

    blender -b --factory-startup -P assetgen/blender/streets_preview.py -- \\
        BLOCKOUT_DIR ASSETS_DIR OUT_DIR [--width W] [--samples N] [--radius R] \\
        [--hide PREFIX]... [VIEW ...] [--eye X Y Z --target X Y Z --lens MM --name NAME]...

Opens BLOCKOUT_DIR/city.blend (a `citygen blockout` output), removes every blockout object
that the street contribution replaces (ASSETS_DIR/unreal_contribution.streets.json: its
`replaces` and its own keys), imports the street tiles (`ASSETS_DIR/streets/<tile>.glb`)
within --radius of the views' targets, places the container instances from the
contribution, and renders each VIEW (the blockout's views by name: `street_<n>`,
`iso_<district>`, ...; and any --eye/--target camera) to OUT_DIR/streets_<name>.jpg.
--hide also removes the blockout objects whose names start with PREFIX (`city.sea.`: the
blockout's sea plane fills each whole tile under the ground and shows through the open
approaches of road tunnels).
"""

import json
import math
import os
import sys
import time

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "citygen", "blender"))
import build as CB  # noqa: E402  (citygen/blender/build.py: views, render setup)


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:]
    src, assets, out = (os.path.abspath(a) for a in argv[:3])
    o = {"src": src, "assets": assets, "out": out, "width": 1920, "samples": 32,
         "radius": 700.0, "views": [], "custom": [], "hide": []}
    rest = argv[3:]
    i = 0
    cur = None
    while i < len(rest):
        a = rest[i]
        if a in ("--width", "--samples"):
            o[a[2:]] = int(rest[i + 1])
            i += 2
        elif a == "--radius":
            o["radius"] = float(rest[i + 1])
            i += 2
        elif a == "--hide":
            o["hide"].append(rest[i + 1])
            i += 2
        elif a in ("--eye", "--target"):
            if a == "--eye":
                cur = {"lens": 35.0, "name": f"custom{len(o['custom']) + 1}"}
                o["custom"].append(cur)
            cur[a[2:]] = tuple(float(x) for x in rest[i + 1:i + 4])
            i += 4
        elif a in ("--lens", "--name"):
            cur[a[2:]] = float(rest[i + 1]) if a == "--lens" else rest[i + 1]
            i += 2
        else:
            o["views"].append(a)
            i += 1
    return o


def tune_materials():
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf is None:
            continue
        if m.name.startswith("light"):
            col = bsdf.inputs["Base Color"].default_value
            bsdf.inputs["Emission Color"].default_value = col
            bsdf.inputs["Emission Strength"].default_value = 8.0
        if m.name.startswith("glass.tube"):
            bsdf.inputs["Alpha"].default_value = 0.3
            try:
                m.surface_render_method = "BLENDED"
            except AttributeError:
                pass


def main():
    o = parse()
    t0 = time.time()
    with open(os.path.join(o["src"], "blockout_plan.json"), encoding="utf-8") as f:
        plan = json.load(f)
    with open(os.path.join(o["assets"], "unreal_contribution.streets.json"),
              encoding="utf-8") as f:
        con = json.load(f)
    views = {v[0]: v for v in CB.views(plan, 1600)}
    todo = [views[n] for n in o["views"] if n in views]
    for c in o["custom"]:
        todo.append((c["name"], False, c["lens"], c["eye"], c["target"], 1600, 900))
    bpy.ops.wm.open_mainfile(filepath=os.path.join(o["src"], "city.blend"))
    scene = bpy.context.scene
    gone = set()
    for e in con["entries"]:
        gone.add(e["key"])
        gone.update(e.get("replaces", []))
    removed = 0
    for ob in list(bpy.data.objects):
        if ob.name in gone or any(ob.name.startswith(h) for h in o["hide"]):
            bpy.data.objects.remove(ob, do_unlink=True)
            removed += 1
    targets = [Vector(v[4][:2]) for v in todo]
    r = o["radius"]
    tiles = sorted({e["tile"] for e in con["entries"]
                    if any((Vector(e["pivot"][:2]) - t).length < r for t in targets)})
    col = bpy.data.collections.new("AG7 streets")
    scene.collection.children.link(col)
    for t in tiles:
        f = os.path.join(o["assets"], "streets", f"{t}.glb")
        if not os.path.isfile(f):
            continue
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=f)
        for ob in set(bpy.data.objects) - before:
            for c in list(ob.users_collection):
                c.objects.unlink(ob)
            col.objects.link(ob)
            if ".glass.lod" in ob.name and not ob.name.endswith(".lod0"):
                ob.hide_render = True
    # container instances
    parts = os.path.join(o["assets"], "streets", "parts.glb")
    n_inst = 0
    if os.path.isfile(parts):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=parts)
        protos = {ob.name: ob for ob in set(bpy.data.objects) - before}
        for ob in protos.values():
            ob.hide_render = True
            ob.hide_viewport = True
        for e in con["entries"]:
            if not e.get("parts") or not any((Vector(e["pivot"][:2]) - t).length < r
                                             for t in targets):
                continue
            px, py, pz = e["pivot"]
            for p in e["parts"]:
                proto = protos.get(p["node"])
                if proto is None:
                    continue
                for x, y, z, yaw in p["xforms"]:
                    ob = bpy.data.objects.new(f"{e['key']}.{n_inst}", proto.data)
                    ob.matrix_world = Matrix.Translation((px + x, py + y, pz + z)) @ \
                        Matrix.Rotation(math.radians(yaw), 4, "Z")
                    col.objects.link(ob)
                    n_inst += 1
    tune_materials()
    CB.setup_render(scene, o["samples"])
    os.makedirs(o["out"], exist_ok=True)
    done = []
    for v in todo:
        path = os.path.join(o["out"], f"streets_{v[0]}.jpg")
        done.append(CB.render_view(scene, v, path, o["width"], plan=plan))
    print("AG7_PREVIEW_DONE " + json.dumps({"files": done, "removed": removed,
                                            "tiles": len(tiles), "instances": n_inst,
                                            "seconds": round(time.time() - t0, 1)}))


main()
