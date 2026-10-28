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

def _attr(nt, name, kind="OBJECT"):
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_type = kind
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


def make_material(slot, spec):
    master, rgb, rough, metal, tint = spec
    mat = bpy.data.materials.new(f"ag_{slot}")
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


MATS = {}


def import_glb(path, tag):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path, import_shading="FLAT")
    new = [o for o in bpy.data.objects if o not in before]
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
                old = ms.material
                o.material_slots[i].material = MATS[base]
                if old.users == 0:
                    bpy.data.materials.remove(old)
    return new


def remove(objs):
    for o in objs:
        me = o.data if o.type == "MESH" else None
        bpy.data.objects.remove(o, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


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
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


# --- main ----------------------------------------------------------------------------------

def main():
    global MATS
    scene = start_scene()
    MATS = materials()
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
        t = time.time()
        shells = []
        hidden = []
        for tile in v.get("shell_tiles", []):
            shells += import_glb(f"{JOB['assets']}/tiles/{tile}.glb", "shell")
        for o in shells:
            if o.type == "EMPTY" and o.name in proxies:
                proxies[o.name].hide_render = True
                hidden.append(proxies[o.name])
        tris = sum(len(o.data.polygons) for o in shells if o.type == "MESH")
        render(scene, v, f"{out}/{v['name']}.jpg")
        report["views"].append({"name": v["name"], "shell_tiles": len(v.get("shell_tiles", [])),
                                "faces": tris, "seconds": round(time.time() - t, 1)})
        log(f"{v['name']}: {len(v.get('shell_tiles', []))} tiles, {tris} faces, "
            f"{time.time() - t:.1f} s")
        remove(shells)
        for o in hidden:
            o.hide_render = False
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
        for cell in sh["cells"]:
            for o in objs:
                o.hide_render = True
            root = roots.get(cell["key"])
            if root is None:
                continue
            for o in [root] + list(root.children_recursive):
                o.hide_render = False
            render(scene, cell["view"], f"{out}/{cell['file']}")
        remove(objs)
        report["sheets"].append({"name": sh["name"], "cells": len(sh["cells"])})
        log(f"sheet {sh['name']}: {len(sh['cells'])}")
    with open(f"{out}/preview_report.json", "w") as f:
        json.dump(report, f, indent=1)
    log("done")


main()
