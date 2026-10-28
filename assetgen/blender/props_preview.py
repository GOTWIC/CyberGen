"""Blender preview of AG8's props, plants and signs among the blockout's buildings (stdlib
and bpy only; Blender only draws):

    blender -b --factory-startup -P assetgen/blender/props_preview.py -- \\
        BLOCKOUT_DIR ASSETS_DIR OUT_DIR [--width W] [--samples N] [--radius R] [--night] \\
        [--streets] [--shells] [--hide PREFIX]... [VIEW ...] \\
        [--eye X Y Z --target X Y Z --lens MM --name NAME]...

Opens BLOCKOUT_DIR/city.blend (a `citygen blockout` output) and removes the blockout objects
the props and signs contributions replace (M15's prototype instancers of props and plants,
by kind and tile); with --streets also those AG7's street contribution replaces, importing
its tile packs (`assets/streets/`), and with --shells the building boxes, importing AG1's
shells (`assets/tiles/`), within --radius of the views' targets. The prop and plant
variants (`assets/props/variants/`, `plants/`) are instanced with geometry nodes on a point
cloud per variant (position, yaw and scale per instance, as M15's prototypes are); the exact
props and the signs of the tiles in reach are imported and each sign placed at its slot.
Renders each VIEW (the blockout's views by name, and any --eye/--target camera) to
OUT_DIR/props_<name>.jpg; --night darkens the sky, lights the lamps and the neon, and adds
spot lights under the street lights and point lights before the signs nearest the camera.
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

T0 = time.time()
GLOW = ("light.", "neon.", "screen.", "lit.", "holo.", "billboard.lamp", "sign.white")


def log(*a):
    print(f"[ag8 preview {time.time() - T0:6.1f}s]", *a, flush=True)


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:]
    src, assets, out = (os.path.abspath(a) for a in argv[:3])
    o = {"src": src, "assets": assets, "out": out, "width": 1920, "samples": 32,
         "radius": 450.0, "views": [], "custom": [], "hide": [], "night": False,
         "streets": False, "shells": False}
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
        elif a in ("--night", "--streets", "--shells"):
            o[a[2:]] = True
            i += 1
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


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def import_glb(path, col, hide=False):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = sorted(set(bpy.data.objects) - before, key=lambda o: o.name)
    for ob in new:
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        col.objects.link(ob)
        if hide:
            ob.hide_render = True
            ob.hide_viewport = True
    return new


def instance_group(name, proto):
    ng = bpy.data.node_groups.new(f"ag8.{name}", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    iop = N.new("GeometryNodeInstanceOnPoints")
    oi = N.new("GeometryNodeObjectInfo")
    oi.transform_space = "ORIGINAL"
    oi.inputs["As Instance"].default_value = True
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


def points_object(name, pts, col):
    """pts: [(x, y, z, yaw_deg, sx, sy, sz)] in the world."""
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(pts))
    me.vertices.foreach_set("co", [v for p in pts for v in p[:3]])
    a = me.attributes.new("rot", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", [v for p in pts for v in (0.0, 0.0, math.radians(p[3]))])
    b = me.attributes.new("scl", "FLOAT_VECTOR", "POINT")
    b.data.foreach_set("vector", [v for p in pts for v in p[4:7]])
    me.update()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    return ob


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[k:k + 2], 16) / 255.0 for k in (0, 2, 4))


def tune(night):
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        b = m.node_tree.nodes.get("Principled BSDF")
        if b is None:
            continue
        n = m.name
        if n.startswith(GLOW):
            b.inputs["Emission Color"].default_value = b.inputs["Base Color"].default_value
            k = 1.0 if not night else 9.0
            if n.startswith(("neon.", "lit.")):
                k *= 2.2
            if n.startswith("holo."):
                k *= 1.5
            b.inputs["Emission Strength"].default_value = (3.0 if not night else 1.0) * k
        if n.startswith(("holo.", "glass.tube")):
            b.inputs["Alpha"].default_value = 0.45 if n.startswith("holo.") else 0.3
            try:
                m.surface_render_method = "BLENDED"
            except AttributeError:
                pass
        if night and (n.startswith("prop_light") or n.startswith("prop_neon") or
                      n.startswith("light")):
            b.inputs["Emission Color"].default_value = b.inputs["Base Color"].default_value
            b.inputs["Emission Strength"].default_value = 12.0


def night_world(scene):
    w = scene.world
    bg = w.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.012, 0.016, 0.04, 1.0)
        bg.inputs["Strength"].default_value = 0.6
    for ob in scene.objects:
        if ob.type == "LIGHT" and ob.data.type == "SUN":
            ob.data.energy = 0.08
            ob.data.color = (0.6, 0.7, 1.0)
    # windows of the blockout's buildings: a dim warm glow so the blocks read
    for m in bpy.data.materials:
        if m.name.startswith(("building", "landmark", "megabuilding")) and m.use_nodes:
            b = m.node_tree.nodes.get("Principled BSDF")
            if b is not None:
                c = b.inputs["Base Color"].default_value
                b.inputs["Base Color"].default_value = (c[0] * 0.5, c[1] * 0.5, c[2] * 0.55, 1)


def main():
    o = parse()
    plan = load(os.path.join(o["src"], "blockout_plan.json"))
    views = {v[0]: v for v in CB.views(plan, 1600)}
    todo = [views[n] for n in o["views"] if n in views]
    for c in o["custom"]:
        todo.append((c["name"], False, c["lens"], c["eye"], c["target"], 1600, 900))
    targets = [Vector(v[4][:2]) for v in todo]
    eyes = [Vector(v[3]) for v in todo]
    r = o["radius"]

    def near(p):
        return any((Vector(p[:2]) - t).length < r for t in targets)

    bpy.ops.wm.open_mainfile(filepath=os.path.join(o["src"], "city.blend"))
    scene = bpy.context.scene
    cons = {}
    for part in ("props", "signs", "streets", "buildings"):
        f = os.path.join(o["assets"], f"unreal_contribution.{part}.json")
        if os.path.isfile(f) and (part in ("props", "signs") or o[part if part != "buildings"
                                                                  else "shells"]):
            cons[part] = load(f)
    gone = set()
    for c in cons.values():
        for e in c["entries"]:
            gone.add(e["key"])
            gone.update(e.get("replaces", []))
    removed = 0
    for ob in list(bpy.data.objects):
        t = str(ob.get("citygen_type", ""))
        if ob.name in gone or any(ob.name.startswith(h) for h in o["hide"]) or \
                (o["shells"] and t.startswith("building.")):
            bpy.data.objects.remove(ob, do_unlink=True)
            removed += 1
    log(f"{removed} blockout objects removed")
    col = bpy.data.collections.new("AG8")
    scene.collection.children.link(col)
    protos_col = bpy.data.collections.new("AG8 variants")
    scene.collection.children.link(protos_col)
    # street and building packs in reach
    for part, sub in (("streets", "streets"), ("buildings", "tiles")):
        if part not in cons:
            continue
        tiles = sorted({e.get("tile") or e["tags"]["cg.tile"] for e in cons[part]["entries"]
                        if near(e["pivot"])})
        for t in tiles:
            f = os.path.join(o["assets"], sub, f"{t}.glb")
            if os.path.isfile(f):
                for ob in import_glb(f, col):
                    if ".lod" in ob.name and not ob.name.endswith(".lod0"):
                        ob.hide_render = True
        log(f"{part}: {len(tiles)} tiles")
    # the variant families, hidden, as prototypes
    protos = {}
    for sub in ("variants", "plants"):
        d = os.path.join(o["assets"], "props", sub)
        for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            for ob in import_glb(os.path.join(d, fn), protos_col):
                ob.location = (0.0, 0.0, -5000.0)
                protos[ob.name] = ob
    log(f"{len(protos)} variants")
    # instances, one point cloud per variant
    pts: dict = {}
    lamps, ids = [], 0
    for e in cons["props"]["entries"]:
        if not e.get("parts") or not near(e["pivot"]):
            continue
        px, py, pz = e["pivot"]
        for p in e["parts"]:
            for xf in p["xforms"]:
                x, y, z, yaw = xf[0] + px, xf[1] + py, xf[2] + pz, xf[3]
                sx, sy, sz = (xf[4], xf[5], xf[6]) if len(xf) > 4 else (1.0, 1.0, 1.0)
                pts.setdefault(p["node"], []).append((x, y, z, yaw, sx, sy, sz))
                if p["node"].startswith("prop.street_light."):
                    a = math.radians(yaw)
                    lamps.append((x + 1.4 * math.cos(a), y + 1.4 * math.sin(a), z + 7.6))
                elif p["node"].startswith("prop.wall_light."):
                    a = math.radians(yaw)
                    lamps.append((x + 0.3 * math.cos(a), y + 0.3 * math.sin(a), z - 0.3))
                ids += 1
    n_inst = 0
    for node in sorted(pts):
        proto = protos.get(node)
        if proto is None:
            continue
        ob = points_object(f"inst.{node}", pts[node], col)
        mod = ob.modifiers.new("instances", "NODES")
        mod.node_group = instance_group(node, proto)
        proto.location = (0.0, 0.0, 0.0)
        proto.hide_render = True
        n_inst += len(pts[node])
    for ob in protos.values():
        ob.location = (0.0, 0.0, 0.0)
    log(f"{n_inst} instances")
    # exact props and signs of the tiles in reach
    tiles = sorted({e["tile"] for c in ("props", "signs") for e in cons[c]["entries"]
                    if e.get("glb") and near(e["pivot"])})
    sign_meshes = {}
    for t in tiles:
        for sub in ("tiles", "signs"):
            f = os.path.join(o["assets"], "props", sub, f"{t}.glb")
            if not os.path.isfile(f):
                continue
            for ob in import_glb(f, col):
                if sub == "signs":
                    sign_meshes[ob.name] = ob
                    ob.hide_render = True
                    ob.hide_viewport = True
    glow_pts = []
    n_signs = 0
    for e in cons["signs"]["entries"]:
        if not near(e["pivot"]):
            continue
        node = e["node"]
        src = sign_meshes.get(node)
        if src is None:
            continue
        ob = bpy.data.objects.new(e["key"], src.data)
        ob.matrix_world = Matrix.Translation(Vector(e["pivot"])) @ \
            Matrix.Rotation(math.radians(e["yaw_deg"]), 4, "Z")
        col.objects.link(ob)
        n_signs += 1
        neon = [s for s in e.get("slots", []) if s.startswith(("neon.", "lit."))]
        if neon:
            a = math.radians(e["yaw_deg"])
            off = 1.0 if e["kind"] != "sign.holo_ad" else 0.0
            glow_pts.append((e["pivot"][0] + off * math.cos(a), e["pivot"][1] + off * math.sin(a),
                             e["pivot"][2], hexrgb(neon[0].split(".")[1])))
    log(f"{n_signs} signs placed")
    tune(o["night"])
    CB.setup_render(scene, o["samples"])
    if o["night"]:
        night_world(scene)
        eye = eyes[0] if eyes else Vector((0, 0, 0))
        lamps.sort(key=lambda p: (Vector(p) - eye).length)
        for i, p in enumerate(lamps[:160]):
            ld = bpy.data.lights.new(f"lamp{i}", "SPOT")
            ld.energy = 700.0
            ld.color = (1.0, 0.86, 0.66)
            ld.spot_size = math.radians(110.0)
            ld.spot_blend = 0.6
            lo = bpy.data.objects.new(f"lamp{i}", ld)
            lo.location = p
            col.objects.link(lo)
        glow_pts.sort(key=lambda p: (Vector(p[:3]) - eye).length)
        for i, (x, y, z, c) in enumerate(glow_pts[:200]):
            ld = bpy.data.lights.new(f"glow{i}", "POINT")
            ld.energy = 110.0
            ld.color = c
            ld.shadow_soft_size = 0.6
            lo = bpy.data.objects.new(f"glow{i}", ld)
            lo.location = (x, y, z)
            col.objects.link(lo)
        try:
            scene.eevee.use_raytracing = True
        except AttributeError:
            pass
        try:
            scene.eevee.use_bloom = True
        except AttributeError:
            pass
    os.makedirs(o["out"], exist_ok=True)
    done = []
    for v in todo:
        path = os.path.join(o["out"], f"props_{v[0]}.jpg")
        done.append(CB.render_view(scene, v, path, o["width"], plan=plan))
    print("AG8_PREVIEW_DONE " + json.dumps({"files": done, "removed": removed,
                                            "instances": n_inst, "signs": n_signs,
                                            "seconds": round(time.time() - T0, 1)}))


main()
