"""Blender previews of a build's assets (stdlib and bpy only; Blender only draws):

    blender -b --factory-startup -P assetgen/blender/preview_assets.py -- JOB.json

`assetgen preview` writes the job. With a blockout (`citygen blockout`'s city.blend) the
scene starts from it, its building boxes removed (ground, water, streets, props, plants and
skybridges stay); else from a plain ground. Every far proxy is loaded once; each view then
loads the full shells of the tiles it needs and hides those buildings' proxies:

- `city`: the whole city from proxies, isometric (the blockout's iso_city camera);
- `iso_<district>`: a district at full detail, its neighbors from proxies;
- `street_<n>`: the blockout's street cameras, shells within the view's radius;
- contact sheets: one building per render, isometric, framed on its bounds.

Materials: one per slot (`ag_<slot>`), its color times the building's tint from the
object's custom properties (`cg_wall`, `cg_trim`, ...: the glTF node extras), brick and
panel joints, corrugation and window grids drawn from UV0 in meters; glass lit by its
window id (vertex alpha) for a few rooms.

AG2's instanced parts: each tile's part pack is loaded with its shells, every part mesh a
hidden prototype, and a point cloud per part mesh (per building on contact sheets) carries
its placements with the building's tints as point attributes; geometry nodes instance the
prototype on it, and the parts' materials (`ag_<slot>.inst`) read the tints from the
instances.
"""

import json
import math
import sys
import time

import bpy
from mathutils import Vector

JOB = json.loads(open(sys.argv[sys.argv.index("--") + 1]).read())
T0 = time.time()


def log(*a):
    print(f"[ag preview {time.time() - T0:6.1f}s]", *a, flush=True)


def mark(what, name):
    """`CGPROGRESS start|done <name>`: the driver's progress bar (`assetgen/blenderrun.py`)."""
    print(f"CGPROGRESS {what} {name}", flush=True)


# --- scene ---------------------------------------------------------------------------------

def start_scene():
    if JOB.get("blend"):
        bpy.ops.wm.open_mainfile(filepath=JOB["blend"])
        gone = 0
        for o in list(bpy.data.objects):
            t = str(o.get("citygen_type", ""))
            if t.startswith("building."):
                bpy.data.objects.remove(o, do_unlink=True)
                gone += 1
        for m in list(bpy.data.meshes):
            if m.users == 0:
                bpy.data.meshes.remove(m)
        log(f"blockout: {gone} building boxes removed")
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        g = JOB.get("ground") or [-5000, -5000, 5000, 5000]
        me = bpy.data.meshes.new("ground")
        me.from_pydata([(g[0], g[1], -0.05), (g[2], g[1], -0.05), (g[2], g[3], -0.05),
                        (g[0], g[3], -0.05)], [], [(0, 1, 2, 3)])
        ob = bpy.data.objects.new("ground", me)
        mat = bpy.data.materials.new("ground")
        mat.use_nodes = True
        mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
            0.16, 0.16, 0.17, 1.0)
        me.materials.append(mat)
        bpy.context.scene.collection.objects.link(ob)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    try:
        scene.eevee.taa_render_samples = JOB.get("samples", 32)
    except AttributeError:
        pass
    for attr, val in (("use_shadows", True), ("use_raytracing", True)):
        try:
            setattr(scene.eevee, attr, val)
        except AttributeError:
            pass
    world = bpy.data.worlds.new("ag_world")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.42, 0.5, 0.62, 1.0)
    bg.inputs["Strength"].default_value = 0.75
    scene.world = world
    for o in list(bpy.data.objects):
        if o.type == "LIGHT":
            bpy.data.objects.remove(o, do_unlink=True)
    sun_data = bpy.data.lights.new("ag_sun", "SUN")
    sun_data.energy = 3.2
    sun_data.angle = math.radians(2.0)
    sun = bpy.data.objects.new("ag_sun", sun_data)
    sun.rotation_euler = (math.radians(48.0), 0.0, math.radians(-128.0))
    scene.collection.objects.link(sun)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    scene.view_settings.view_transform = "AgX" if "AgX" in [
        v.identifier for v in type(scene.view_settings).bl_rna.properties["view_transform"]
        .enum_items] else "Filmic"
    return scene


# --- materials -----------------------------------------------------------------------------

def _attr(nt, name, kind=None):
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_type = kind or ATTR_KIND
    a.attribute_name = name
    return a


def _uv(nt):
    t = nt.nodes.new("ShaderNodeUVMap")
    t.uv_map = "UVMap"
    return t


def _math(nt, op, a=None, b=None, va=None, vb=None):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    if a is not None:
        nt.links.new(a, m.inputs[0])
    elif va is not None:
        m.inputs[0].default_value = va
    if b is not None:
        nt.links.new(b, m.inputs[1])
    elif vb is not None:
        m.inputs[1].default_value = vb
    return m.outputs[0]


def _mix(nt, fac, a, b):
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    nt.links.new(fac, m.inputs["Factor"])
    for sock, v in ((m.inputs["A"], a), (m.inputs["B"], b)):
        if isinstance(v, tuple):
            sock.default_value = v
        else:
            nt.links.new(v, sock)
    return m.outputs["Result"]


def _value(nt, v):
    n = nt.nodes.new("ShaderNodeValue")
    n.outputs[0].default_value = v
    return n.outputs[0]


def _scale_rgb(nt, col, k):
    m = nt.nodes.new("ShaderNodeVectorMath")
    m.operation = "SCALE"
    nt.links.new(col, m.inputs[0])
    m.inputs["Scale"].default_value = k
    return m.outputs[0]


ATTR_KIND = "OBJECT"


def make_material(slot, spec, inst=False):
    global ATTR_KIND
    ATTR_KIND = "INSTANCER" if inst else "OBJECT"
    master, rgb, rough, metal, tint = spec
    mat = bpy.data.materials.new(f"ag_{slot}.inst" if inst else f"ag_{slot}")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    base = (rgb[0], rgb[1], rgb[2], 1.0)
    col = None
    if tint == "patch":
        col = _scale_rgb(nt, _attr(nt, "cg_patch").outputs["Vector"], 3.1)
        mul = nt.nodes.new("ShaderNodeVectorMath")
        mul.operation = "MULTIPLY"
        nt.links.new(col, mul.inputs[0])
        mul.inputs[1].default_value = rgb
        col = mul.outputs[0]
    elif tint:
        col = _attr(nt, f"cg_{tint}").outputs["Vector"]
    uv = _uv(nt).outputs["UV"]
    if slot == "brick" or slot == "panel":
        br = nt.nodes.new("ShaderNodeTexBrick")
        nt.links.new(uv, br.inputs["Vector"])
        br.inputs["Scale"].default_value = 1.0
        if slot == "brick":
            br.inputs["Brick Width"].default_value = 0.25
            br.inputs["Row Height"].default_value = 0.075
            br.inputs["Mortar Size"].default_value = 0.01
            br.offset = 0.5
        else:
            br.inputs["Brick Width"].default_value = 3.0
            br.inputs["Row Height"].default_value = 1.5
            br.inputs["Mortar Size"].default_value = 0.025
            br.offset = 0.0
        c1 = col if col is not None else base
        c2 = _scale_rgb(nt, col, 0.82) if col is not None else (
            rgb[0] * 0.82, rgb[1] * 0.82, rgb[2] * 0.82, 1.0)
        if isinstance(c1, tuple):
            br.inputs["Color1"].default_value = c1
        else:
            nt.links.new(c1, br.inputs["Color1"])
        if isinstance(c2, tuple):
            br.inputs["Color2"].default_value = c2
        else:
            nt.links.new(c2, br.inputs["Color2"])
        br.inputs["Mortar"].default_value = (0.32, 0.31, 0.29, 1.0) if slot == "brick" else \
            (0.18, 0.18, 0.18, 1.0)
        nt.links.new(br.outputs["Color"], bsdf.inputs["Base Color"])
    elif slot in ("cladding", "patch_sheet", "patch_rust"):
        wv = nt.nodes.new("ShaderNodeTexWave")
        nt.links.new(uv, wv.inputs["Vector"])
        wv.wave_type = "BANDS"
        wv.bands_direction = "X"
        wv.inputs["Scale"].default_value = 5.0
        f = _math(nt, "MULTIPLY", wv.outputs["Fac"], vb=0.25)
        f = _math(nt, "ADD", f, vb=0.75)
        c = col if col is not None else nt.nodes.new("ShaderNodeRGB").outputs[0]
        if col is None:
            c.node.outputs[0].default_value = base
        m = nt.nodes.new("ShaderNodeVectorMath")
        m.operation = "SCALE"
        nt.links.new(c, m.inputs[0])
        nt.links.new(f, m.inputs["Scale"])
        nt.links.new(m.outputs[0], bsdf.inputs["Base Color"])
    elif slot in ("glass", "storefront"):
        # day glass: the building's tint lifted toward the sky it reflects
        g = _scale_rgb(nt, col, 2.0) if col is not None else None
        sky = (0.24, 0.34, 0.48, 1.0)
        mixed = _mix(nt, _value(nt, 0.5), g if g is not None else base, sky)
        nt.links.new(mixed, bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.12
        bsdf.inputs["Metallic"].default_value = 0.25
        # a few rooms lit: the window id (vertex alpha) under the building's lit ratio
        ca = nt.nodes.new("ShaderNodeVertexColor")
        ca.layer_name = "Color"
        lit = _math(nt, "MULTIPLY", _math(nt, "LESS_THAN", ca.outputs["Alpha"],
                                          vb=JOB.get("lit", 0.03)),
                    _math(nt, "GREATER_THAN", ca.outputs["Alpha"], vb=0.002))
        warm = (1.0, 0.82, 0.6, 1.0) if slot == "glass" else (1.0, 0.92, 0.8, 1.0)
        bsdf.inputs["Emission Color"].default_value = warm
        nt.links.new(_math(nt, "ADD", _math(nt, "MULTIPLY", lit,
                                            vb=0.25 if slot == "glass" else 0.5), vb=0.02),
                     bsdf.inputs["Emission Strength"])
    elif slot == "proxy":
        # a window grid from UV0 (meters: u around the mass, v up) and the building's bay
        # and floor height
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(uv, sep.inputs[0])
        bay = _attr(nt, "cg_bay").outputs["Fac"]
        flo = _attr(nt, "cg_floor").outputs["Fac"]
        fu = _math(nt, "FRACT", _math(nt, "DIVIDE", sep.outputs["X"], bay))
        fv = _math(nt, "FRACT", _math(nt, "DIVIDE", sep.outputs["Y"], flo))
        wu = _math(nt, "MULTIPLY", _math(nt, "GREATER_THAN", fu, vb=0.2),
                   _math(nt, "LESS_THAN", fu, vb=0.8))
        wz = _math(nt, "MULTIPLY", _math(nt, "GREATER_THAN", fv, vb=0.3),
                   _math(nt, "LESS_THAN", fv, vb=0.82))
        hi = _math(nt, "GREATER_THAN", sep.outputs["Y"], vb=1.0)
        w = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", wu, wz), hi)
        glass = _attr(nt, "cg_glass").outputs["Vector"]
        out = _mix(nt, w, col, glass)
        nt.links.new(out, bsdf.inputs["Base Color"])
    else:
        if col is not None:
            nt.links.new(col, bsdf.inputs["Base Color"])
        else:
            bsdf.inputs["Base Color"].default_value = base
    return mat


def materials():
    return {slot: make_material(slot, spec) for slot, spec in sorted(JOB["slots"].items())}


def inst_materials():
    return {slot: make_material(slot, spec, True) for slot, spec in sorted(JOB["slots"].items())}


MATS = {}
MATS_INST = {}
TINTS = ("cg_wall", "cg_trim", "cg_glass", "cg_roof", "cg_spandrel", "cg_patch")


def instance_group(coll):
    """A geometry-node group that puts, at every point, the child of `coll` its `proto`
    attribute picks (children sorted by name, as Collection Info sorts them). One group
    and one instancer per pack: a group per part mesh would make every new link update
    thousands of trees, and Blender 5 has no Python access to a modifier's inputs."""
    ng = bpy.data.node_groups.new(f"ag_parts.{coll.name}", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    iop = N.new("GeometryNodeInstanceOnPoints")
    iop.inputs["Pick Instance"].default_value = True
    ci = N.new("GeometryNodeCollectionInfo")
    ci.transform_space = "ORIGINAL"
    ci.inputs["Collection"].default_value = coll
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    rot = N.new("GeometryNodeInputNamedAttribute")
    rot.data_type = "FLOAT_VECTOR"
    rot.inputs["Name"].default_value = "rot"
    idx = N.new("GeometryNodeInputNamedAttribute")
    idx.data_type = "INT"
    idx.inputs["Name"].default_value = "proto"
    L.new(gi.outputs["Geometry"], iop.inputs["Points"])
    L.new(ci.outputs["Instances"], iop.inputs["Instance"])
    L.new(idx.outputs["Attribute"], iop.inputs["Instance Index"])
    L.new(rot.outputs["Attribute"], iop.inputs["Rotation"])
    L.new(iop.outputs["Instances"], go.inputs["Geometry"])
    return ng


PACKS = [0]


def load_parts(glb, inst, tag, by_building=False):
    """A part pack's meshes as hidden prototypes in a collection of their own (renamed in
    the order of their node names) and their placements as one instancer, or one per
    building (`by_building`)."""
    objs = import_glb(glb, tag)
    protos = {}
    for o in objs:
        if o.type != "MESH":
            continue
        protos[o.name.split(".")[0] + "." + o.name.split(".")[1] + "." +
               o.name.split(".")[2] + "." + o.name.split(".")[3]
               if o.name.count(".") >= 4 else o.name] = o
        for i, ms in enumerate(o.material_slots):
            if ms.material is not None:
                base = ms.material.name.split(".")[0]
                if base in MATS_INST:
                    o.material_slots[i].material = MATS_INST[base]
        o.hide_render = True
        o.location = (0.0, 0.0, -5000.0)
    made = list(objs)
    PACKS[0] += 1
    coll = bpy.data.collections.new(f"agp{PACKS[0]:05d}")
    coll["ag_parts"] = True
    index = {}
    for k, node in enumerate(sorted(n for n in inst.get("parts", {}) if n in protos)):
        o = protos[node]
        o.name = f"agp{PACKS[0]:05d}.{k:06d}"
        coll.objects.link(o)
        index[node] = k
    if not index:
        return made
    ng = instance_group(coll)
    tints = inst.get("tints", [])
    groups = {}
    for node, k in sorted(index.items()):
        for p in inst["parts"][node]:
            groups.setdefault(p[4] if by_building else -1, []).append((k, p))
    for bi, pl in sorted(groups.items()):
        me = bpy.data.meshes.new(f"inst.{coll.name}")
        me.vertices.add(len(pl))
        me.vertices.foreach_set("co", [v for _, p in pl for v in (p[0], p[1], p[2])])
        a = me.attributes.new("rot", "FLOAT_VECTOR", "POINT")
        a.data.foreach_set("vector", [v for _, p in pl for v in (0.0, 0.0, p[3])])
        a = me.attributes.new("proto", "INT", "POINT")
        a.data.foreach_set("value", [k for k, _ in pl])
        for j, name in enumerate(TINTS):
            at = me.attributes.new(name, "FLOAT_VECTOR", "POINT")
            at.data.foreach_set("vector", [v for _, p in pl for v in tints[p[4]][j]])
        me.update()
        ob = bpy.data.objects.new(f"inst.{coll.name}", me)
        mod = ob.modifiers.new("parts", "NODES")
        mod.node_group = ng
        ob["ag_tag"] = tag
        ob["ag_building"] = int(bi)
        bpy.context.scene.collection.objects.link(ob)
        made.append(ob)
    return made


GLTF_TMP = []


def _defer_gltf_tmp():
    """The glTF importer makes a temporary object per mesh and deletes it at once, and a
    deletion scans the whole file: with a city's packs loaded that is quadratic. Deleted
    here in one batch per import instead (the importer's own steps otherwise)."""
    try:
        from io_scene_gltf2.blender.imp import mesh as GM
    except ImportError:
        return

    def create_mesh(gltf, mesh_idx, skin_idx):
        pymesh = gltf.data.meshes[mesh_idx]
        GM.import_user_extensions('gather_import_mesh_before_hook', gltf, pymesh)
        mesh = bpy.data.meshes.new(pymesh.name or 'Mesh_%d' % mesh_idx)
        tmp_ob = bpy.data.objects.new('##gltf-import:tmp-object##', mesh)
        GLTF_TMP.append(tmp_ob)
        GM.do_primitives(gltf, mesh_idx, skin_idx, mesh, tmp_ob)
        GM.set_extras(mesh, pymesh.extras, exclude=['targetNames'])
        GM.import_user_extensions('gather_import_mesh_after_hook', gltf, pymesh, mesh)
        return mesh

    if all(hasattr(GM, n) for n in ("create_mesh", "do_primitives", "set_extras",
                                    "import_user_extensions")):
        GM.create_mesh = create_mesh


def import_glb(path, tag):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path, import_shading="FLAT")
    if GLTF_TMP:
        bpy.data.batch_remove(GLTF_TMP)
        GLTF_TMP.clear()
    new = [o for o in bpy.data.objects if o not in before]
    old_mats = set()
    for o in new:
        o["ag_tag"] = tag
        if o.type != "MESH":
            continue
        cols = o.data.color_attributes
        if len(cols) and cols[0].name != "Color":
            cols[0].name = "Color"
        for i, ms in enumerate(o.material_slots):
            if ms.material is None:
                continue
            base = ms.material.name.split(".")[0]
            if base in MATS:
                old_mats.add(ms.material)
                o.material_slots[i].material = MATS[base]
    bpy.data.batch_remove([m for m in old_mats if m.users == 0])
    return new


def remove(objs):
    """Objects and their meshes, at once (one by one is quadratic in Blender)."""
    meshes = {o.data for o in objs if o.type == "MESH" and o.data is not None}
    groups = {m.node_group for o in objs for m in o.modifiers
              if m.type == "NODES" and m.node_group is not None}
    bpy.data.batch_remove(list(objs))
    bpy.data.batch_remove([m for m in meshes if m.users == 0])
    bpy.data.batch_remove([g for g in groups if g.users == 0])
    bpy.data.batch_remove([c for c in bpy.data.collections if c.get("ag_parts") and
                           c.users == 0])


# --- cameras -------------------------------------------------------------------------------

def camera(scene, ortho):
    data = bpy.data.cameras.new("ag_cam")
    data.type = "ORTHO" if ortho else "PERSP"
    data.clip_start = 0.3
    data.clip_end = 30000.0
    cam = bpy.data.objects.new("ag_cam", data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    return cam


def look(cam, eye, target):
    cam.location = Vector(eye)
    cam.rotation_euler = (Vector(target) - Vector(eye)).to_track_quat("-Z", "Y").to_euler()


def render(scene, v, path):
    cam = camera(scene, v["ortho"])
    if v["ortho"]:
        cam.data.ortho_scale = v["scale"]
    else:
        cam.data.lens = v["lens"]
    look(cam, v["eye"], v["target"])
    scene.render.resolution_x, scene.render.resolution_y = v["w"], v["h"]
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    try:
        scene.eevee.taa_render_samples = v.get("samples", JOB.get("samples", 32))
    except AttributeError:
        pass
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


# --- main ----------------------------------------------------------------------------------

def main():
    global MATS, MATS_INST
    _defer_gltf_tmp()
    scene = start_scene()
    MATS = materials()
    MATS_INST = inst_materials()
    insts = {}
    if JOB.get("instances") and JOB.get("parts_on", True):
        with open(JOB["instances"]) as f:
            insts = json.load(f)
    out = JOB["out"]
    report = {"views": [], "sheets": []}
    proxies = {}
    if JOB["views"]:
        for t in JOB["proxy_tiles"]:
            for o in import_glb(f"{JOB['assets']}/proxies/{t}.glb", "proxy"):
                if o.type == "MESH":
                    proxies[o.name.rsplit(".proxy", 1)[0]] = o
        log(f"proxies: {len(proxies)}")
    for v in JOB["views"]:
        mark("start", v["name"])
        t = time.time()
        shells = []
        hidden = []
        for tile in v.get("shell_tiles", []):
            shells += import_glb(f"{JOB['assets']}/tiles/{tile}.glb", "shell")
            if tile in insts:
                shells += load_parts(f"{JOB['assets']}/parts/{tile}.glb", insts[tile], "parts")
        for o in shells:
            if o.type == "EMPTY" and o.name in proxies:
                proxies[o.name].hide_render = True
                hidden.append(proxies[o.name])
        tris = sum(len(o.data.polygons) for o in shells
                   if o.type == "MESH" and not o.name.startswith("inst."))
        log(f"{v['name']}: loaded in {time.time() - t:.1f} s")
        render(scene, v, f"{out}/{v['name']}.jpg")
        report["views"].append({"name": v["name"], "shell_tiles": len(v.get("shell_tiles", [])),
                                "faces": tris, "seconds": round(time.time() - t, 1)})
        log(f"{v['name']}: {len(v.get('shell_tiles', []))} tiles, {tris} faces, "
            f"{time.time() - t:.1f} s")
        remove(shells)
        for o in hidden:
            o.hide_render = False
        mark("done", v["name"])
    if JOB["sheets"]:
        for o in proxies.values():
            o.hide_render = True
        for o in bpy.data.objects:
            if o.type == "MESH" and o.get("ag_tag") is None:
                o.hide_render = True
        ground = bpy.data.meshes.new("sheet_ground")
        ground.from_pydata([(-600, -600, -0.02), (600, -600, -0.02), (600, 600, -0.02),
                            (-600, 600, -0.02)], [], [(0, 1, 2, 3)])
        gob = bpy.data.objects.new("sheet_ground", ground)
        gm = bpy.data.materials.new("sheet_ground")
        gm.use_nodes = True
        gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
            0.2, 0.2, 0.21, 1.0)
        ground.materials.append(gm)
        scene.collection.objects.link(gob)
    for sh in JOB["sheets"]:
        objs = import_glb(sh["glb"], "sheet")
        roots = {o.name: o for o in objs if o.type == "EMPTY"}
        parts = []
        if sh.get("parts_glb") and sh.get("instances") and JOB.get("parts_on", True):
            parts = load_parts(sh["parts_glb"], sh["instances"], "sheet_parts", True)
        inst_of = {}
        for o in parts:
            if o.name.startswith("inst."):
                inst_of.setdefault(int(o["ag_building"]), []).append(o)
        for k, cell in enumerate(sh["cells"]):
            for o in objs + parts:
                o.hide_render = True
            root = roots.get(cell["key"])
            if root is None:
                mark("done", cell["file"])
                continue
            for o in [root] + list(root.children_recursive) + inst_of.get(k, []):
                o.hide_render = False
            render(scene, cell["view"], f"{out}/{cell['file']}")
            mark("done", cell["file"])
        remove(objs + parts)
        report["sheets"].append({"name": sh["name"], "cells": len(sh["cells"])})
        log(f"sheet {sh['name']}: {len(sh['cells'])}")
    with open(f"{out}/preview_report.json", "w") as f:
        json.dump(report, f, indent=1)
    log("done")


main()
