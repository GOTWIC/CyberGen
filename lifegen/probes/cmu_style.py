"""LG0's CMU-style clip for the retargeting probe (ue_probe.py): no download. A BVH in the
CMU motion capture database's skeleton (its joint names and hierarchy: hip, lhipjoint,
lfemur, ltibia, lfoot, ltoes, lowerback, upperback, thorax, lowerneck, upperneck, head,
lclavicle, lhumerus, lradius, lwrist, lhand and the right side's), a walk cycle generated as
sines, written as text, imported by Blender's BVH importer, skinned to a stick figure (a box
per bone) and written as an FBX that Unreal imports as a skeletal mesh with its clip.

    blender -b --factory-startup -P lifegen/probes/cmu_style.py -- OUT_DIR
"""

import math
import sys
from pathlib import Path

import bpy

# joint: (parent, offset cm (x right, y up, z forward, BVH's), channels)
J = [
    ("hip", None, (0, 95, 0)),
    ("lowerback", "hip", (0, 8, 0)), ("upperback", "lowerback", (0, 12, 0)),
    ("thorax", "upperback", (0, 12, 0)), ("lowerneck", "thorax", (0, 14, 0)),
    ("upperneck", "lowerneck", (0, 6, 0)), ("head", "upperneck", (0, 8, 0)),
]
for s, x in (("l", 1), ("r", -1)):
    J += [(f"{s}hipjoint", "hip", (9 * x, -5, 0)), (f"{s}femur", f"{s}hipjoint", (0, -4, 0)),
          (f"{s}tibia", f"{s}femur", (0, -42, 0)), (f"{s}foot", f"{s}tibia", (0, -42, 0)),
          (f"{s}toes", f"{s}foot", (0, -6, 13)),
          (f"{s}clavicle", "thorax", (4 * x, 10, 0)),
          (f"{s}humerus", f"{s}clavicle", (14 * x, 0, 0)),
          (f"{s}radius", f"{s}humerus", (0, -29, 0)), (f"{s}wrist", f"{s}radius", (0, -25, 0)),
          (f"{s}hand", f"{s}wrist", (0, -8, 0))]
END = {"head": (0, 12, 0), "ltoes": (0, 0, 5), "rtoes": (0, 0, 5), "lhand": (0, -8, 0),
       "rhand": (0, -8, 0)}
FRAMES, FPS = 60, 30


def children(name):
    return [j for j in J if j[1] == name]


def hierarchy(name, depth=0):
    j = next(x for x in J if x[0] == name)
    pad = "  " * depth
    root = j[1] is None
    out = [f"{pad}{'ROOT' if root else 'JOINT'} {name}", f"{pad}{{",
           f"{pad}  OFFSET {j[2][0]:.2f} {j[2][1]:.2f} {j[2][2]:.2f}",
           f"{pad}  CHANNELS {'6 Xposition Yposition Zposition ' if root else '3 '}"
           "Zrotation Xrotation Yrotation"]
    for c in children(name):
        out += hierarchy(c[0], depth + 1)
    if name in END:
        e = END[name]
        out += [f"{pad}  End Site", f"{pad}  {{", f"{pad}    OFFSET {e[0]} {e[1]} {e[2]}",
                f"{pad}  }}"]
    out.append(f"{pad}}}")
    return out


def order(name="hip"):
    out = [name]
    for c in children(name):
        out += order(c[0])
    return out


def pose(f):
    """A walk: legs swing about x, knees bend, arms counter-swing, the hips bob and travel."""
    t = 2 * math.pi * f / FRAMES
    rot = {n: (0.0, 0.0, 0.0) for n, _, _ in J}            # (z, x, y) degrees
    for s, ph in (("l", 0.0), ("r", math.pi)):
        sw = math.sin(t + ph)
        rot[f"{s}femur"] = (0.0, -28 * sw, 0.0)
        rot[f"{s}tibia"] = (0.0, 30 * max(0.0, math.sin(t + ph + 1.2)), 0.0)
        rot[f"{s}foot"] = (0.0, -8 * sw, 0.0)
        rot[f"{s}humerus"] = (0.0, 22 * sw, 0.0)
        rot[f"{s}radius"] = (0.0, -15 - 10 * max(0.0, sw), 0.0)
    rot["lowerback"] = (0.0, 3.0, 4 * math.sin(t))
    root = (0.0, 95.0 + 2.5 * math.cos(2 * t), 130.0 * f / FRAMES)
    vals = list(root)
    for n in order():
        vals += list(rot[n])
    return vals


def write_bvh(path: Path):
    lines = ["HIERARCHY", *hierarchy("hip"), "MOTION", f"Frames: {FRAMES}",
             f"Frame Time: {1.0 / FPS:.6f}"]
    for f in range(FRAMES):
        lines.append(" ".join(f"{v:.4f}" for v in pose(f)))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    out = Path(sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "cmu_out").resolve()
    out.mkdir(parents=True, exist_ok=True)
    bvh = out / "cmu_style_walk.bvh"
    write_bvh(bvh)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_anim.bvh(filepath=str(bvh), global_scale=0.01, frame_start=1,
                            use_fps_scale=False, rotate_mode="NATIVE")
    arm = bpy.context.object
    arm.name = "cmu"
    # a stick figure: a box along each bone, weighted wholly to it
    import mathutils
    me = bpy.data.meshes.new("cmu_body")
    verts, faces, vg = [], [], []
    for b in arm.data.bones:
        h, tl = arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local
        d = tl - h
        if d.length < 1e-4:
            continue
        r = 0.035 if any(k in b.name for k in ("femur", "tibia", "back", "thorax")) else 0.025
        q = d.to_track_quat("Z", "Y")
        base = len(verts)
        for z in (0.0, d.length):
            for x, y in ((-r, -r), (r, -r), (r, r), (-r, r)):
                verts.append(h + q @ mathutils.Vector((x, y, z)))
        faces += [(base, base + 1, base + 2, base + 3), (base + 4, base + 7, base + 6, base + 5),
                  (base, base + 4, base + 5, base + 1), (base + 1, base + 5, base + 6, base + 2),
                  (base + 2, base + 6, base + 7, base + 3), (base + 3, base + 7, base + 4, base)]
        vg.append((b.name, list(range(base, base + 8))))
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    body = bpy.data.objects.new("cmu_body", me)
    bpy.context.scene.collection.objects.link(body)
    for name, idx in vg:
        g = body.vertex_groups.new(name=name)
        g.add(idx, 1.0, "REPLACE")
    body.parent = arm
    mod = body.modifiers.new("arm", "ARMATURE")
    mod.object = arm
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = arm
    fbx = out / "cmu_style_walk.fbx"
    bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, add_leaf_bones=False,
                             bake_anim=True, bake_anim_use_all_actions=False,
                             bake_anim_use_nla_strips=False, object_types={"ARMATURE", "MESH"},
                             armature_nodetype="NULL")
    print(f"CITYGEN_CMU {fbx} bones {len(arm.data.bones)} frames {FRAMES}", flush=True)


if __name__ == "__main__":
    main()
