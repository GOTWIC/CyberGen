"""The clothing fixes' look check, Blender's half (stdlib and bpy only): each look the editor
exported (`lifegen/probes/look_export_ue.py`: the look's garments skinned as the library made
them, the body, the walk) posed along the walk, where an inner layer comes through an outer one
counted, and the worst frame rendered from behind and from the back three quarters.

    blender -b --factory-startup -P lifegen/probes/look_pose.py -- JOB.json
        (JOB: {fbx_dir, anim, looks: [...], out, frames, render})

The pairs: a vertex of one garment piece (a connected part of the look, welded by position)
whose ray along its normal meets another piece within `PAIR_M` in the reference pose lies under
that piece; in a pose it has come through when it lies more than `POKE_M` outside the piece's
posed surface (its nearest point's normal). The report (`pose_report.json`) gives per look the
pairs, the worst frame's count and every frame's, all over and in the waist's band (within
`WAIST_M` of spine_02's height in the reference pose: LG2's open item, a coat's waist over
trousers); the renders mark inner pieces dark red and the faces that came through yellow.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

PAIR_M = 0.04
POKE_M = 0.0015
WAIST_M = 0.22


def log(msg):
    print(f"CGPOSE {msg}", flush=True)


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_fbx(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(path), use_anim=True, ignore_leaf_bones=False,
                             automatic_bone_orientation=False)
    new = [o for o in bpy.data.objects if o not in before]
    arm = next((o for o in new if o.type == "ARMATURE"), None)
    meshes = [o for o in new if o.type == "MESH"]
    return arm, meshes


def components(me):
    """Each vertex's piece: connected by edges, welded by position (0.1 mm)."""
    n = len(me.vertices)
    par = list(range(n))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb
    for e in me.edges:
        union(e.vertices[0], e.vertices[1])
    seen = {}
    for v in me.vertices:
        k = (round(v.co.x * 1e4), round(v.co.y * 1e4), round(v.co.z * 1e4))
        if k in seen:
            union(v.index, seen[k])
        else:
            seen[k] = v.index
    roots = {}
    return [roots.setdefault(find(i), len(roots)) for i in range(n)]


def world_coords(ob, depsgraph=None):
    if depsgraph is None:
        me = ob.data
        mw = ob.matrix_world
        return [mw @ v.co for v in me.vertices], [(mw.to_3x3() @ v.normal).normalized()
                                                   for v in me.vertices]
    ev = ob.evaluated_get(depsgraph)
    me = ev.to_mesh()
    mw = ob.matrix_world
    co = [mw @ v.co for v in me.vertices]
    no = [(mw.to_3x3() @ v.normal).normalized() for v in me.vertices]
    ev.to_mesh_clear()
    return co, no


def piece_bvh(co, tris, comp, k):
    t = [f for f in tris if comp[f[0]] == k]
    return BVHTree.FromPolygons(co, t) if t else None


def pairs_of(look):
    """(vertex, the piece it lies under) in the reference pose."""
    me = look.data
    comp = components(me)
    co, no = world_coords(look)
    tris = [tuple(p.vertices) for p in me.polygons]
    ftri = [comp[t[0]] for t in tris]
    bvh = BVHTree.FromPolygons(co, tris)
    out = []
    for i, (p, n) in enumerate(zip(co, no)):
        o = p + n * 0.001
        hit = bvh.ray_cast(o, n, PAIR_M)
        k = 0
        while hit[0] is not None and ftri[hit[2]] == comp[i] and k < 4:
            hit = bvh.ray_cast(hit[0] + n * 0.001, n, PAIR_M)
            k += 1
        if hit[0] is not None and ftri[hit[2]] != comp[i]:
            out.append((i, ftri[hit[2]]))
    return out, comp, tris


def pokes(look, pairs, comp, tris, depsgraph):
    co, _ = world_coords(look, depsgraph)
    by = {}
    for i, k in pairs:
        by.setdefault(k, []).append(i)
    found = []
    for k, vs in by.items():
        bvh = piece_bvh(co, tris, comp, k)
        if bvh is None:
            continue
        for i in vs:
            q, n, _, d = bvh.find_nearest(co[i], 0.08)
            if q is not None and (co[i] - q).dot(n) > POKE_M:
                found.append(i)
    return found, co


def material(name, rgb, rough=0.6):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*rgb, 1.0)
    p.inputs["Roughness"].default_value = rough
    return m


def paint(look, comp, pairs, poked):
    """The look in three colors: inner pieces (a fifth of their vertices under another piece)
    dark red, the rest light grey, the faces with a vertex come through yellow."""
    me = look.data
    me.materials.clear()
    me.materials.append(material("outer", (0.55, 0.56, 0.6)))
    me.materials.append(material("inner", (0.35, 0.05, 0.04)))
    me.materials.append(material("poke", (1.0, 0.8, 0.0)))
    size, low = {}, {}
    for k in comp:
        size[k] = size.get(k, 0) + 1
    for i, _ in pairs:
        low[comp[i]] = low.get(comp[i], 0) + 1
    inner = {k for k in size if low.get(k, 0) > 0.2 * size[k]}
    hot = set(poked)
    for p in me.polygons:
        if any(v in hot for v in p.vertices):
            p.material_index = 2
        else:
            p.material_index = 1 if comp[p.vertices[0]] in inner else 0


def stage(size=(640, 900)):
    scn = bpy.context.scene
    scn.render.resolution_x, scn.render.resolution_y = size
    scn.render.engine = "CYCLES"
    scn.cycles.samples = 24
    scn.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scn.cycles.device = "GPU"
    except Exception:                                                   # noqa: BLE001
        scn.cycles.device = "CPU"
    scn.render.image_settings.file_format = "JPEG"
    scn.render.image_settings.quality = 90
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.055, 0.065, 1)
    scn.world = w
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 60
    scn.collection.objects.link(cam)
    scn.camera = cam
    return cam


def light(name, loc, target, energy, size):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.size = energy, size
    lo = bpy.data.objects.new(name, ld)
    lo.location = loc
    lo.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(lo)


def main():
    job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
    out = Path(job["out"])
    out.mkdir(parents=True, exist_ok=True)
    rep_path = out / "pose_report.json"
    rep = json.loads(rep_path.read_text(encoding="utf-8")) if rep_path.is_file() else {}
    for lid in job["looks"]:
        if lid in rep and not job.get("force"):
            continue
        clear()
        d = Path(job["fbx_dir"]) / lid
        if not (d / "look.fbx").is_file():
            continue
        arm_a, _ = import_fbx(job["anim"])
        act = arm_a.animation_data.action if arm_a and arm_a.animation_data else None
        arm_b, body = import_fbx(d / "body.fbx")
        arm_l, lk = import_fbx(d / "look.fbx")
        look = max(lk, key=lambda o: len(o.data.vertices))
        pairs, comp, tris = pairs_of(look)
        under = sorted({k for _, k in pairs})
        f0, f1 = (int(act.frame_range[0]), int(act.frame_range[1])) if act else (1, 1)
        # (each bone of the body's and the look's armatures copies the clip's bone of its name
        # in world space: the files' armatures sit under different scales and parents)
        names = {b.name for b in arm_a.pose.bones} if arm_a else set()
        for a in (arm_b, arm_l):
            if a is None or act is None:
                continue
            for pb in a.pose.bones:
                if pb.name in names:
                    c = pb.constraints.new("COPY_TRANSFORMS")
                    c.target, c.subtarget = arm_a, pb.name
        for o in (arm_a,) + tuple(o for o in bpy.data.objects
                                  if o.type == "MESH" and o.parent == arm_a):
            if o is not None:
                o.hide_render = True
                o.hide_viewport = True
        frames = sorted({round(f0 + (f1 - f0) * k / job.get("frames", 12))
                         for k in range(job.get("frames", 12))})
        # (the waist's band: the reference pose's vertices within `WAIST_M` of spine_02's
        # height, where a coat over trousers came through)
        rest, _ = world_coords(look)
        wz = None
        if arm_b is not None and "spine_02" in arm_b.data.bones:
            wz = (arm_b.matrix_world @ arm_b.data.bones["spine_02"].head_local).z
        band = {i for i, p in enumerate(rest) if wz is not None and abs(p.z - wz) < WAIST_M}
        scn = bpy.context.scene
        per, wper = {}, {}
        worst = (None, -1, [])
        for f in frames:
            scn.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            found, _ = pokes(look, pairs, comp, tris, dg)
            per[f] = len(found)
            wper[f] = sum(1 for i in found if i in band)
            if len(found) > worst[1]:
                worst = (f, len(found), found)
        rec = {"pairs": len(pairs), "pieces": len(set(comp)), "under_pieces": len(under),
               "frames": per, "worst_frame": worst[0], "worst": worst[1],
               "mean": round(sum(per.values()) / max(1, len(per)), 1),
               "waist_pairs": sum(1 for i, _ in pairs if i in band),
               "waist_frames": wper, "waist_worst": max(wper.values()) if wper else 0,
               "waist_mean": round(sum(wper.values()) / max(1, len(wper)), 1)}
        log(f"{lid} {rec}")
        if job.get("render"):
            scn.frame_set(worst[0] if worst[0] is not None else f0)
            paint(look, comp, pairs, worst[2])
            for o in body:
                o.data.materials.clear()
                o.data.materials.append(material("skin", (0.55, 0.40, 0.32), 0.5))
            B = arm_b.pose.bones if arm_b else None
            mw = arm_b.matrix_world if arm_b else None
            if B and "ball_l" in B and "foot_l" in B and "spine_02" in B:
                fwd = (mw @ B["ball_l"].head) - (mw @ B["foot_l"].head)
                fwd.z = 0
                fwd.normalize()
                waist = mw @ B["spine_02"].head
            else:
                fwd, waist = Vector((0, -1, 0)), Vector((0, 0, 1.0))
            cam = stage()
            side = fwd.cross(Vector((0, 0, 1)))
            light("key", waist - fwd * 3 + side * 2 + Vector((0, 0, 2)), waist, 600, 2.5)
            light("fill", waist + fwd * 3 - side * 2 + Vector((0, 0, 1)), waist, 250, 3.0)
            for name, eye in (("back", waist - fwd * 2.6 + Vector((0, 0, 0.15))),
                              ("back34", waist - fwd * 1.9 + side * 1.6 + Vector((0, 0, 0.2)))):
                cam.location = eye
                tgt = waist + Vector((0, 0, 0.05))
                cam.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
                scn.render.filepath = str(out / f"{lid}_{name}.jpg")
                bpy.ops.render.render(write_still=True)
        rep[lid] = rec
        rep_path.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print("CGPOSE_DONE", flush=True)


if __name__ == "__main__":
    main()
