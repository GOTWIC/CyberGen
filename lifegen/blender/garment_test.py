"""LG0's garment test (docs/lifegen_scope.md 6.2, decision 12.3): a tee sewn from two flat
panels and draped on a plain body by Blender's cloth solver, headless, baked, rendered.

    blender -b --factory-startup -P lifegen/blender/garment_test.py -- --out DIR [--frames 90]
        [--res 0.022] [--samples 48] [--width 1600]

stdlib and bpy only (as citygen's Blender scripts). The tee is a sewing pattern in code: one
outline (front and back alike: body, sleeves, a neck opening), each panel triangulated by a
constrained Delaunay fill (`mathutils.geometry.delaunay_2d_cdt`) at `--res`, the two hung in
front of and behind a plain body (a mannequin of primitives in an A pose), their side,
underarm, shoulder and sleeve-top seams joined by sewing springs (loose edges between matching
outline points), the hem, cuffs and neck left open. The cloth solver pulls the seams shut
round the body and lets the tee hang; every frame is stepped (the point cache baked), the last
frame's mesh kept as a mesh of its own (`tee_baked`, written as `tee_baked.glb`), and the body
and the tee rendered from the front and three quarters (`garment_front.jpg`,
`garment_34.jpg`). `garment_report.json`: vertex and triangle counts, the seams' gaps at the
end (how well they closed), the simulation's time.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector, geometry

# the outline (x across, y up, meters over the floor); the body is 1.78 m
OUTLINE = [(-0.27, 0.92), (0.27, 0.92), (0.27, 1.27), (0.46, 1.19), (0.50, 1.35),
           (0.22, 1.48), (0.085, 1.51), (-0.085, 1.51), (-0.22, 1.48), (-0.50, 1.35),
           (-0.46, 1.19), (-0.27, 1.27)]
# outline edges (by their first point) sewn front to back: sides, underarms, sleeve tops and
# shoulders; open: the hem (0), the cuffs (3, 9) and the neck (6)
SEAMS = (1, 2, 4, 5, 7, 8, 10, 11)
PANEL_Y = 0.2                        # the panels hang this far in front and behind
SEW_FRAMES = 30                      # frames sewn without gravity


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"out": "garment_out", "frames": 90, "res": 0.022, "samples": 48, "width": 1600}
    for i in range(0, len(a), 2):
        k = a[i].lstrip("-")
        out[k] = type(out[k])(a[i + 1]) if k in out and not isinstance(out[k], str) else a[i + 1]
    return out


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def body():
    """A plain body of primitives (torso, hips, neck, head, arms in an A pose, legs), joined
    into one mesh, a collision object for the cloth."""
    parts = []

    def add(obj):
        parts.append(obj)
        return obj

    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=(0, 0, 1.25))
    t = add(bpy.context.object)
    t.scale = (0.19, 0.12, 0.26)                         # chest and belly
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=(0, 0, 0.98))
    add(bpy.context.object).scale = (0.18, 0.12, 0.16)   # hips
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.055, depth=0.14,
                                        location=(0, 0, 1.53))
    add(bpy.context.object)                              # neck
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=(0, 0, 1.66))
    add(bpy.context.object).scale = (0.095, 0.11, 0.12)  # head
    for s in (-1, 1):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8,
                                             location=(s * 0.2, 0, 1.43))
        add(bpy.context.object).scale = (0.075, 0.075, 0.07)          # shoulder
        a, b = Vector((s * 0.21, 0, 1.42)), Vector((s * 0.62, 0, 1.18))
        mid, d = (a + b) / 2, b - a
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.05, depth=d.length,
                                            location=mid)
        arm = add(bpy.context.object)
        arm.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.075, depth=0.9,
                                            location=(s * 0.1, 0, 0.45))
        add(bpy.context.object)                          # leg
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    b = bpy.context.object
    b.name = "body"
    bpy.ops.object.shade_smooth()
    b.modifiers.new("collision", "COLLISION")
    c = b.collision
    c.thickness_outer = 0.012
    c.cloth_friction = 6.0
    return b


def sample_outline(res):
    """Outline points every `res` (at least one a segment), each with the outline edge it
    starts and its share along it."""
    pts = []
    for i, a in enumerate(OUTLINE):
        b = OUTLINE[(i + 1) % len(OUTLINE)]
        n = max(1, round(math.dist(a, b) / res))
        for k in range(n):
            t = k / n
            pts.append(((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), i, t))
    return pts


def inside(x, y):
    n, c = len(OUTLINE), False
    for i in range(n):
        (x1, y1), (x2, y2) = OUTLINE[i], OUTLINE[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def panel_2d(res):
    """The panel's 2D mesh: the outline's points and a grid inside it (kept off the outline by
    half a step), filled by a constrained Delaunay triangulation; (verts, tris, boundary index
    of each outline sample in the output)."""
    bnd = sample_outline(res)
    verts = [Vector((p[0][0], p[0][1])) for p in bnd]
    edges = [(i, (i + 1) % len(bnd)) for i in range(len(bnd))]
    xs = [p[0] for p in OUTLINE]
    ys = [p[1] for p in OUTLINE]
    y = min(ys) + res
    row = 0
    while y < max(ys):
        x = min(xs) + res * (0.5 if row % 2 else 1.0)
        while x < max(xs):
            if inside(x, y) and all(math.dist((x, y), (v.x, v.y)) > 0.55 * res for v in
                                    verts[:len(bnd)]):
                verts.append(Vector((x, y)))
            x += res
        y += res * 0.866
        row += 1
    out = geometry.delaunay_2d_cdt(verts, edges, [], 2, 1e-6)
    vco, _, faces, orig, _, _ = out
    where = {}
    for vi, srcs in enumerate(orig):
        for s in srcs:
            if s < len(bnd):
                where[s] = vi
    return [Vector((v.x, v.y)) for v in vco], [tuple(f) for f in faces], bnd, where


def tee(res):
    """The tee: front and back panels in one mesh, sewing springs as loose edges between the
    seams' matching outline points; returns (object, seam vertex pairs)."""
    v2, tris, bnd, where = panel_2d(res)
    n = len(v2)
    me = bpy.data.meshes.new("tee")
    co = [(v.x, -PANEL_Y, v.y) for v in v2] + [(v.x, PANEL_Y, v.y) for v in v2]
    faces = [t for t in tris] + [tuple(n + i for i in reversed(t)) for t in tris]
    pairs = []
    for s, (_, edge, _) in enumerate(bnd):
        # (a seam's points, and the point that ends it: the next edge's first)
        prev_edge = bnd[s - 1][1]
        if edge in SEAMS or (prev_edge in SEAMS and bnd[s][2] == 0.0):
            pairs.append((where[s], n + where[s]))
    me.from_pydata(co, [p for p in pairs], faces)
    me.update()
    ob = bpy.data.objects.new("tee", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob, pairs


def drape(ob, frames):
    m = ob.modifiers.new("cloth", "CLOTH")
    s = m.settings
    s.quality = 8
    s.mass = 0.05                          # kg a vertex: a light cotton at this resolution
    s.tension_stiffness = 12.0
    s.compression_stiffness = 12.0
    s.shear_stiffness = 6.0
    s.bending_stiffness = 0.15
    s.air_damping = 1.0
    s.use_sewing_springs = True
    s.sewing_force_max = 12.0
    s.shrink_min = 0.0
    cs = m.collision_settings
    cs.distance_min = 0.006
    cs.use_self_collision = True
    cs.self_distance_min = 0.004
    cs.collision_quality = 4
    m.point_cache.frame_start = 1
    m.point_cache.frame_end = frames
    # (sewn first, then let hang: no gravity until the seams have closed round the body, as a
    # tailoring tool sews before it drapes)
    ew = s.effector_weights
    ew.gravity = 0.0
    ew.keyframe_insert("gravity", frame=1)
    ew.keyframe_insert("gravity", frame=SEW_FRAMES)
    ew.gravity = 1.0
    ew.keyframe_insert("gravity", frame=SEW_FRAMES + 10)
    scn = bpy.context.scene
    scn.frame_start, scn.frame_end = 1, frames
    t = time.time()
    for f in range(1, frames + 1):
        scn.frame_set(f)
        if f % 10 == 0:
            print(f"CGPROGRESS frame {f}/{frames} {time.time() - t:.1f} s", flush=True)
    return round(time.time() - t, 1)


def baked(ob):
    """The last frame's draped mesh as an object of its own (the cloth's result kept)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    out = bpy.data.objects.new("tee_baked", me)
    bpy.context.scene.collection.objects.link(out)
    out.matrix_world = ob.matrix_world.copy()
    ob.hide_render = True
    ob.hide_set(True)
    return out


def seam_gaps(me, pairs):
    return [(me.vertices[a].co - me.vertices[b].co).length for a, b in pairs]


def material(name, rgb, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*rgb, 1.0)
    p.inputs["Roughness"].default_value = rough
    if "Sheen Weight" in p.inputs:
        p.inputs["Sheen Weight"].default_value = 0.4
    return m


def render(out: Path, samples: int, width: int, body_ob, tee_ob):
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.samples = samples
    scn.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scn.cycles.device = "GPU"
    except Exception:
        scn.cycles.device = "CPU"
    scn.render.resolution_x = width
    scn.render.resolution_y = int(width * 1.25)
    scn.render.image_settings.file_format = "JPEG"
    scn.render.image_settings.quality = 92
    body_ob.data.materials.append(material("skin", (0.55, 0.4, 0.33), 0.55))
    tee_ob.data.materials.append(material("cotton", (0.08, 0.32, 0.45), 0.85))
    sub = tee_ob.modifiers.new("smooth", "SUBSURF")
    sub.levels = sub.render_levels = 1
    bpy.ops.object.select_all(action="DESELECT")
    tee_ob.select_set(True)
    bpy.context.view_layer.objects.active = tee_ob
    bpy.ops.object.shade_smooth()
    bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
    floor = bpy.context.object
    floor.data.materials.append(material("floor", (0.18, 0.18, 0.2), 0.7))
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.03, 0.035, 0.045, 1)
    scn.world = w
    for name, loc, energy, size in (("key", (2.0, -3.0, 3.2), 900, 2.5),
                                    ("rim", (-2.5, 2.5, 2.8), 500, 2.0),
                                    ("fill", (-2.5, -2.5, 1.2), 220, 3.0)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.size = energy, size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((0, 0, 1.2)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        scn.collection.objects.link(lo)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 60
    scn.collection.objects.link(cam)
    scn.camera = cam
    files = []
    for name, eye in (("garment_front", (0.0, -3.4, 1.3)), ("garment_34", (2.3, -2.5, 1.55))):
        cam.location = eye
        cam.rotation_euler = (Vector((0, 0, 1.18)) - Vector(eye)).to_track_quat("-Z", "Y").to_euler()
        scn.render.filepath = str(out / f"{name}.jpg")
        bpy.ops.render.render(write_still=True)
        files.append(scn.render.filepath)
    return files


def main():
    a = args()
    out = Path(a["out"]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    clear()
    b = body()
    ob, pairs = tee(float(a["res"]))
    me0 = ob.data
    start = seam_gaps(me0, pairs)
    secs = drape(ob, int(a["frames"]))
    tb = baked(ob)
    end = seam_gaps(tb.data, pairs)
    bpy.ops.object.select_all(action="DESELECT")
    tb.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(out / "tee_baked.glb"), use_selection=True,
                              export_format="GLB")
    tris = sum(len(p.vertices) - 2 for p in tb.data.polygons)
    rep = {"panel_vertices": len(me0.vertices) // 2, "vertices": len(tb.data.vertices),
           "triangles": tris, "seam_pairs": len(pairs), "frames": int(a["frames"]),
           "res_m": float(a["res"]), "simulate_s": secs,
           "seam_gap_start_m": round(max(start), 3),
           "seam_gap_end_m": {"max": round(max(end), 4),
                              "mean": round(sum(end) / len(end), 4)},
           "lowest_z_m": round(min((tb.matrix_world @ v.co).z for v in tb.data.vertices), 3)}
    rep["renders"] = render(out, int(a["samples"]), int(a["width"]), b, tb)
    (out / "garment_report.json").write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    print("CITYGEN_GARMENT " + json.dumps(rep), flush=True)


if __name__ == "__main__":
    main()
