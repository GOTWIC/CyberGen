"""Blender preview of AG0's spike buildings (stdlib and bpy only; Blender only draws):

    blender -b --python assetgen/blender/spike_preview.py -- SPIKE_DIR OUT_DIR

Imports `<name>_gpuinst.glb` of the three buildings (parts as instances through
EXT_mesh_gpu_instancing), places them side by side and renders EEVEE views: the tower
whole, its base up close, the shopfront row and the shanty stack from the street.
"""

import math
import sys
import time

import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:]
SPIKE, OUT = ARGS[0], ARGS[1]
PLACES = {"tower": (0.0, 0.0), "shopfront_row": (70.0, -40.0), "shanty_stack": (110.0, -40.0)}


def setup(scene):
    scene.render.engine = "BLENDER_EEVEE"
    try:
        scene.eevee.taa_render_samples = 32
    except AttributeError:
        pass
    world = bpy.data.worlds.new("spike_world")
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.42, 0.52, 0.66, 1.0)
    bg.inputs["Strength"].default_value = 0.8
    scene.world = world
    sun_data = bpy.data.lights.new("spike_sun", "SUN")
    sun_data.energy = 3.5
    sun_data.angle = math.radians(1.5)
    sun = bpy.data.objects.new("spike_sun", sun_data)
    sun.rotation_euler = (math.radians(52.0), 0.0, math.radians(-125.0))
    scene.collection.objects.link(sun)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 90
    ground = bpy.data.meshes.new("ground")
    ground.from_pydata([(-400, -400, -0.02), (400, -400, -0.02), (400, 400, -0.02),
                        (-400, 400, -0.02)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new("ground", ground)
    mat = bpy.data.materials.new("ground")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
        0.18, 0.18, 0.19, 1.0)
    ground.materials.append(mat)
    scene.collection.objects.link(g)


def tune_materials():
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf is None:
            continue
        if m.name.startswith("sign"):
            bsdf.inputs["Emission Color"].default_value = (1.0, 0.1, 0.35, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 4.0


def look(cam, eye, target):
    cam.location = Vector(eye)
    cam.rotation_euler = (Vector(target) - Vector(eye)).to_track_quat("-Z", "Y").to_euler()


def render(scene, cam, name, eye, target, lens, w=1600, h=1000):
    cam.data.lens = lens
    look(cam, eye, target)
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.filepath = f"{OUT}/{name}.jpg"
    bpy.ops.render.render(write_still=True)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    setup(scene)
    t = time.time()
    for name, (x, y) in PLACES.items():
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=f"{SPIKE}/{name}_gpuinst.glb")
        for o in set(bpy.data.objects) - before:
            if o.parent is None:
                o.location = (x, y, 0.0)
    print(f"SPIKE imported in {time.time() - t:.1f} s, {len(bpy.data.objects)} objects")
    tune_materials()
    cam_data = bpy.data.cameras.new("cam")
    cam_data.clip_end = 5000.0
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    render(scene, cam, "spike_tower", (-520.0, -700.0, 210.0), (20.0, 0.0, 165.0), 50)
    render(scene, cam, "spike_tower_base", (-48.0, -62.0, 8.0), (-10.0, -20.0, 22.0), 24)
    render(scene, cam, "spike_shopfront_row", (52.0, -75.0, 3.0), (72.0, -45.0, 6.0), 24)
    render(scene, cam, "spike_shanty_stack", (96.0, -68.0, 4.0), (110.0, -42.0, 5.0), 24)


main()
