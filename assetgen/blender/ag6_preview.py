"""AG6's textured previews (stdlib and bpy only; Blender only draws):

    blender -b --factory-startup -P assetgen/blender/ag6_preview.py -- JOB.json

`assetgen materials preview` writes the job (`assetgen/materials/preview.py`). The scene is
the blockout's city.blend without its building boxes and the street objects AG7 replaces;
every far proxy is loaded once, and AG8's variant families as hidden prototypes; per view
the shells of its tiles, the street pieces near it, AG8's instances (geometry nodes on a
point cloud per variant), exact props and signs near it are imported, their slots given
AG6's materials (`ag6_materials.py`: a building's era for its walls and roof, its
parameters as object properties), sign quads placed on the sign slots with their atlas
cells where AG8 has not made the signs, and the view rendered by day and, with lights at
the street lights and the windows, signs and neon lit, by night.

AG3: the street fronts (`<id>.front`) and the tiles' decal meshes (`decals.<tile>`, alpha
quads from the decal atlas) come with the shells; AG2's instanced parts (`parts/<tile>.glb`)
are put on points by geometry nodes, one instancer per pack, their materials reading the
building's tints from the instance.
"""

import json
import math
import os
import re
import sys
import time

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ag6_materials as AM  # noqa: E402

JOB = json.loads(open(sys.argv[sys.argv.index("--") + 1]).read())
T0 = time.time()
SUFFIX = re.compile(r"\.\d{3}$")


def log(*a):
    print(f"[ag6 {time.time() - T0:6.1f}s]", *a, flush=True)


def mark(what, name):
    """`CGPROGRESS start|done <name>`: the driver's progress bar (`assetgen/blenderrun.py`)."""
    print(f"CGPROGRESS {what} {name}", flush=True)


MATS = {}


def mat_for(part, key, inst=False):
    k = (part, key, inst)
    if k not in MATS:
        rec = JOB["materials"]["buildings" if part == "buildings" else part].get(key)
        if rec is None:
            return None
        AM.ATTR[0] = "INSTANCER" if inst else "OBJECT"
        MATS[k] = AM.make(f"ag6_{part}_{key}{'.inst' if inst else ''}", rec, JOB["files"],
                          part)
        AM.ATTR[0] = "OBJECT"
    return MATS[k]


OWN = (".shell", ".front", ".proxy")


def start():
    bpy.ops.wm.open_mainfile(filepath=JOB["blend"])
    gone = set(JOB["removed"])
    drop = [o for o in bpy.data.objects
            if str(o.get("citygen_type", "")).startswith("building.") or o.name in gone
            or o.type in ("LIGHT", "CAMERA")]
    n = len(drop)
    bpy.data.batch_remove(drop)             # (one by one is quadratic in Blender)
    bpy.data.batch_remove([m for m in bpy.data.meshes if m.users == 0])
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    try:
        sc.eevee.taa_render_samples = JOB.get("samples", 32)
    except AttributeError:
        pass
    for attr, val in (("use_shadows", True), ("use_raytracing", True)):
        try:
            setattr(sc.eevee, attr, val)
        except AttributeError:
            pass
    try:
        sc.eevee.ray_tracing_options.resolution_scale = "2"
    except (AttributeError, TypeError):
        pass
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 90
    names = [v.identifier for v in type(sc.view_settings).bl_rna.properties["view_transform"]
             .enum_items]
    sc.view_settings.view_transform = "AgX" if "AgX" in names else "Filmic"
    world = bpy.data.worlds.new("ag6_world")
    world.use_nodes = True
    sc.world = world
    sun_d = bpy.data.lights.new("ag6_sun", "SUN")
    sun = bpy.data.objects.new("ag6_sun", sun_d)
    sun.rotation_euler = (math.radians(50.0), 0.0, math.radians(-128.0))
    sc.collection.objects.link(sun)
    log(f"blockout: {n} objects removed")
    return sc, sun


def lighting(sc, sun, mode):
    bg = sc.world.node_tree.nodes.get("Background")
    if mode == "day":
        bg.inputs["Color"].default_value = (0.42, 0.5, 0.62, 1.0)
        bg.inputs["Strength"].default_value = 0.8
        sun.data.energy = 3.4
        sun.data.color = (1.0, 0.96, 0.9)
        sun.data.angle = math.radians(2.0)
        AM.set_night(0.0)
        sc.view_settings.exposure = 0.0
    else:
        bg.inputs["Color"].default_value = (0.012, 0.016, 0.035, 1.0)
        bg.inputs["Strength"].default_value = 1.0
        sun.data.energy = 0.04
        sun.data.color = (0.6, 0.7, 1.0)
        AM.set_night(1.0)
        sc.view_settings.exposure = 1.0
    glare(sc, mode == "night")


def _comp_tree(sc):
    """The scene's compositor nodes and its output socket (Blender 5's node group, else the
    older scene node tree)."""
    if hasattr(sc, "compositing_node_group"):
        ng = sc.compositing_node_group
        if ng is None:
            ng = bpy.data.node_groups.new("ag6_comp", "CompositorNodeTree")
            sc.compositing_node_group = ng
            ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        for n in list(ng.nodes):
            ng.nodes.remove(n)
        out = ng.nodes.new("NodeGroupOutput")
        return ng, out.inputs[0]
    sc.use_nodes = True
    nt = sc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("CompositorNodeComposite")
    return nt, out.inputs["Image"]


def _set(node, name, value):
    if name in node.inputs:
        try:
            node.inputs[name].default_value = value
            return
        except (AttributeError, TypeError, ValueError):
            pass
    try:
        setattr(node, name.lower(), value)
    except (AttributeError, TypeError, ValueError):
        pass


def glare(sc, on):
    """A fog glow over the bright pixels by night (EEVEE has no bloom of its own)."""
    try:
        sc.render.use_compositing = True
        nt, sink = _comp_tree(sc)
        rl = nt.nodes.new("CompositorNodeRLayers")
        img = rl.outputs["Image"]
        if on:
            g = nt.nodes.new("CompositorNodeGlare")
            for name, v in (("Type", "Fog Glow"), ("glare_type", "FOG_GLOW"),
                            ("Quality", "Medium"), ("Threshold", 0.9), ("Strength", 0.5),
                            ("Size", 0.6), ("size", 7), ("mix", -0.5)):
                _set(g, name, v)
            nt.links.new(img, g.inputs["Image"])
            img = g.outputs["Image"]
        nt.links.new(img, sink)
    except Exception as e:              # a preview without glare is still a preview
        log(f"no glare: {e}")


GLTF_TMP = []


def _defer_gltf_tmp():
    """The glTF importer's temporary object per mesh deleted in one batch per import, not
    one by one (each deletion scans the whole file: quadratic over a whole city's packs;
    as `preview_assets._defer_gltf_tmp`)."""
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


def import_glb(path, part, shared=False):
    """A pack's objects with AG6's materials. `shared`: meshes that other objects draw too
    (AG2's parts and AG8's families through geometry nodes, AG8's signs as copies), whose
    materials go on the mesh; every other object's go on the object (a slot linked to the
    mesh walks every object of the file on each assignment, quadratic over a whole city)."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path, import_shading="FLAT")
    if GLTF_TMP:
        bpy.data.batch_remove(GLTF_TMP)
        GLTF_TMP.clear()
    new = [o for o in bpy.data.objects if o not in before]
    props = JOB["props"]
    old_mats = set()
    for o in new:
        o["ag6"] = part
        if o.type != "MESH":
            continue
        key = None
        era = None
        if part in ("buildings", "parts"):
            base = next((o.name.rsplit(x, 1)[0] for x in OWN if x in o.name), o.name)
            pr = props.get(base) if part == "buildings" else None
            if pr is not None:
                era = pr["era"]
                for k, v in pr.items():
                    if k.startswith("cg_"):
                        o[k] = float(v)
        for i, ms in enumerate(o.material_slots):
            if ms.material is None:
                continue
            slot = SUFFIX.sub("", ms.material.name)
            key = slot
            if part == "buildings" and era and slot in JOB["era_slots"]:
                key = f"{slot}@{era}"
                if key not in JOB["materials"]["buildings"]:
                    key = slot
            if part == "buildings" and pr is not None and \
                    f"{key}#{base}" in JOB["materials"]["buildings"]:
                key = f"{key}#{base}"          # (AG5: a hero's own, its mask on UV1)
            m = mat_for("buildings" if part == "parts" else part, key, part == "parts")
            if m is not None:
                old_mats.add(ms.material)
                if not shared:
                    ms.link = "OBJECT"
                ms.material = m
    # (in one batch: one by one is quadratic)
    bpy.data.batch_remove([m for m in old_mats if m.users == 0])
    return new


TINTS = ("cg_wall", "cg_trim", "cg_glass", "cg_roof", "cg_spandrel", "cg_patch")


def _points(name, pts, attrs):
    """A point cloud: pts [(x, y, z, yaw_rad, ...)], attrs {name: (kind, values)}."""
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(pts))
    me.vertices.foreach_set("co", [v for p in pts for v in p[:3]])
    a = me.attributes.new("rot", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", [v for p in pts for v in (0.0, 0.0, p[3])])
    for an, (kind, vals) in attrs.items():
        at = me.attributes.new(an, kind, "POINT")
        at.data.foreach_set("vector" if kind == "FLOAT_VECTOR" else "value", vals)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _group(name, coll):
    """Geometry nodes putting, at every point, the child of `coll` its `proto` attribute
    picks (AG2's parts: one group per pack)."""
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    iop = N.new("GeometryNodeInstanceOnPoints")

    def named(attr, kind):
        n = N.new("GeometryNodeInputNamedAttribute")
        n.data_type = kind
        n.inputs["Name"].default_value = attr
        return n.outputs["Attribute"]
    iop.inputs["Pick Instance"].default_value = True
    ci = N.new("GeometryNodeCollectionInfo")
    ci.transform_space = "ORIGINAL"
    ci.inputs["Collection"].default_value = coll
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    L.new(ci.outputs["Instances"], iop.inputs["Instance"])
    L.new(named("proto", "INT"), iop.inputs["Instance Index"])
    L.new(gi.outputs["Geometry"], iop.inputs["Points"])
    L.new(named("rot", "FLOAT_VECTOR"), iop.inputs["Rotation"])
    L.new(iop.outputs["Instances"], go.inputs["Geometry"])
    return ng


def _proto_key(name):
    """A part node's name without Blender's copy number (`part.<family>.<style>.h<hash>`)."""
    return SUFFIX.sub("", name)


def load_parts(glb, inst):
    """AG2's part pack of a tile: its meshes hidden in a collection of their own (in the
    order of their node names), their placements one instancer with the building's tints
    on every point."""
    objs = import_glb(glb, "parts", shared=True)
    protos = {}
    for o in objs:
        if o.type == "MESH":
            protos.setdefault(_proto_key(o.name), o)
        o.hide_render = True
    nodes = sorted(n for n in inst.get("parts", {}) if n in protos)
    if not nodes:
        return objs
    coll = bpy.data.collections.new(f"ag6p.{os.path.basename(glb)}")
    for k, node in enumerate(nodes):
        o = protos[node]
        o.name = f"{coll.name}.{k:06d}"
        o.location = (0.0, 0.0, 0.0)
        coll.objects.link(o)
    pts, idx = [], []
    for k, node in enumerate(nodes):
        for p in inst["parts"][node]:
            pts.append(p)
            idx.append(k)
    tints = inst.get("tints", [])
    attrs = {"proto": ("INT", idx)}
    for j, name in enumerate(TINTS):
        attrs[name] = ("FLOAT_VECTOR", [v for p in pts for v in tints[p[4]][j]])
    ob = _points(f"inst.{coll.name}", pts, attrs)
    ob.modifiers.new("parts", "NODES").node_group = _group(f"ag6p.{coll.name}", coll=coll)
    return objs + [ob]


def remove(objs):
    data = {o.data for o in objs if o.data is not None}
    bpy.data.batch_remove(objs)
    bpy.data.batch_remove([d for d in data if d.users == 0])


SIGN_MATS = {}


def sign_mat(path):
    m = SIGN_MATS.get(path)
    if m is None:
        m = bpy.data.materials.new(f"ag6_sign_{os.path.basename(path)}")
        m.use_nodes = True
        AM.sign(m, path, 5.0 if "ads_1" not in path else 3.0)
        SIGN_MATS[path] = m
    return m


def signs(items):
    """A quad per sign face (two for a two-sided blade), its atlas cell on it."""
    objs = []
    for s in items:
        a = math.radians(s["yaw"])
        fx, fy = math.cos(a), math.sin(a)          # the face looks along (fx, fy)
        sx, sy = -fy, fx
        w, h = s["w"], s["h"]
        x, y, z = s["pos"]
        u0, v0, u1, v1 = s["uv"]
        faces = [1.0, -1.0] if s["two"] else [1.0]
        for side in faces:
            off = 0.13 if s["mount"] == "blade" else 0.04
            cx, cy = x + fx * off * side, y + fy * off * side
            ax, ay = sx * side, sy * side
            pts = [(cx - ax * w / 2, cy - ay * w / 2, z - h / 2),
                   (cx + ax * w / 2, cy + ay * w / 2, z - h / 2),
                   (cx + ax * w / 2, cy + ay * w / 2, z + h / 2),
                   (cx - ax * w / 2, cy - ay * w / 2, z + h / 2)]
            me = bpy.data.meshes.new(f"sign_{s['id']}")
            me.from_pydata(pts, [], [(0, 1, 2, 3)])
            uvl = me.uv_layers.new(name="UVMap")
            # glTF v (from the top) to Blender's (from the bottom)
            for li, (uu, vv) in enumerate(((u0, v1), (u1, v1), (u1, v0), (u0, v0))):
                uvl.data[li].uv = (uu, 1.0 - vv)
            me.materials.append(sign_mat(s["file"]))
            ob = bpy.data.objects.new(me.name, me)
            bpy.context.scene.collection.objects.link(ob)
            objs.append(ob)
    return objs


def instance_group(name, proto):
    """Geometry nodes: the prototype on every point, turned by `rot`, scaled by `scl`."""
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
    att = {}
    for a in ("rot", "scl"):
        att[a] = N.new("GeometryNodeInputNamedAttribute")
        att[a].data_type = "FLOAT_VECTOR"
        att[a].inputs["Name"].default_value = a
    L.new(gi.outputs["Geometry"], iop.inputs["Points"])
    L.new(oi.outputs["Geometry"], iop.inputs["Instance"])
    L.new(att["rot"].outputs["Attribute"], iop.inputs["Rotation"])
    L.new(att["scl"].outputs["Attribute"], iop.inputs["Scale"])
    L.new(iop.outputs["Instances"], go.inputs["Geometry"])
    return ng


def ag8(v, protos):
    """AG8's instances, exact props and signs near a view; the objects made."""
    objs = []
    a8 = v.get("ag8") or {}
    for node, pts in a8.get("points", {}).items():
        proto = protos.get(node)
        if proto is None:
            continue
        me = bpy.data.meshes.new(f"inst.{node}")
        me.vertices.add(len(pts))
        me.vertices.foreach_set("co", [c for p in pts for c in p[:3]])
        r = me.attributes.new("rot", "FLOAT_VECTOR", "POINT")
        r.data.foreach_set("vector", [c for p in pts for c in (0.0, 0.0, math.radians(p[3]))])
        sc = me.attributes.new("scl", "FLOAT_VECTOR", "POINT")
        sc.data.foreach_set("vector", [c for p in pts for c in p[4:7]])
        me.update()
        ob = bpy.data.objects.new(f"inst.{node}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.modifiers.new("instances", "NODES").node_group = instance_group(node, proto)
        objs.append(ob)
    for path in a8.get("exact", []):
        objs += import_glb(path, "props")
    meshes = {}
    for path in sorted({s["glb"] for s in a8.get("signs", [])}):
        for o in import_glb(path, "signs", shared=True):
            o.hide_render = True
            meshes.setdefault(SUFFIX.sub("", o.name), o)    # (a sign shared by two tiles)
            objs.append(o)
    for s in a8.get("signs", []):
        src = meshes.get(s["node"])
        if src is None or src.type != "MESH":
            continue
        ob = bpy.data.objects.new(s["key"], src.data)
        ob.matrix_world = Matrix.Translation(Vector(s["pivot"])) @ \
            Matrix.Rotation(math.radians(s["yaw"]), 4, "Z")
        bpy.context.scene.collection.objects.link(ob)
        objs.append(ob)
    return objs


def lamps(points):
    objs = []
    for k, (x, y, z) in enumerate(points):
        d = bpy.data.lights.new(f"lamp{k}", "POINT")
        d.energy = 9000.0
        d.color = (1.0, 0.78, 0.52)
        d.shadow_soft_size = 0.4
        try:
            d.use_shadow = k < 24
        except AttributeError:
            pass
        ob = bpy.data.objects.new(f"lamp{k}", d)
        ob.location = (x, y, z)
        bpy.context.scene.collection.objects.link(ob)
        objs.append(ob)
    return objs


def camera(sc, v):
    data = bpy.data.cameras.new("ag6_cam")
    data.type = "ORTHO" if v["ortho"] else "PERSP"
    data.clip_start = 0.3
    data.clip_end = 30000.0
    if v["ortho"]:
        data.ortho_scale = v["scale"]
    else:
        data.lens = v["lens"]
    cam = bpy.data.objects.new("ag6_cam", data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = Vector(v["eye"])
    cam.rotation_euler = (Vector(v["target"]) - Vector(v["eye"])).to_track_quat(
        "-Z", "Y").to_euler()
    return cam


def section(sc, cam, v):
    """AG10: a section along a vertical plane (`v["section"]`: a point on it and its normal
    toward the camera): the camera's near clip on the plane, and every mesh lying wholly on
    the camera's side hidden (so it casts no shadow into the cut). Returns what it hid."""
    s = v["section"]
    cam.data.clip_start = max(float(s["clip"]), 0.3)
    ox, oy = s["origin"]
    nx, ny = s["n"]
    hid = []
    for o in sc.objects:
        if o.type != "MESH" or o.hide_render:
            continue
        dn = [((o.matrix_world @ Vector(c)).x - ox) * nx +
              ((o.matrix_world @ Vector(c)).y - oy) * ny for c in o.bound_box]
        if min(dn) > 0.05:
            o.hide_render = True
            hid.append(o)
    return hid


def main():
    _defer_gltf_tmp()
    sc, sun = start()
    proxies = {}
    for t in JOB["proxy_tiles"]:
        p = f"{JOB['assets']}/proxies/{t}.glb"
        if os.path.isfile(p):
            for o in import_glb(p, "buildings"):
                if o.type == "MESH":
                    proxies[o.name.rsplit(".proxy", 1)[0]] = o
    log(f"proxies: {len(proxies)}")
    protos = {}
    for p in JOB.get("ag8_families", []):
        for o in import_glb(p, "props", shared=True):
            o.hide_render = True
            o.hide_viewport = True
            protos[SUFFIX.sub("", o.name)] = o
    log(f"AG8 variants: {len(protos)}")
    rep = {"files": [], "views": []}
    for v in JOB["views"]:
        mark("start", v["name"])
        t = time.time()
        objs, hidden = [], []
        for tile in v.get("shell_tiles", []):
            objs += import_glb(f"{JOB['assets']}/tiles/{tile}.glb", "buildings")
        for o in objs:
            if o.type == "EMPTY" and o.name in proxies:
                proxies[o.name].hide_render = True
                hidden.append(proxies[o.name])
        for tile in v.get("street_tiles", []):
            p = f"{JOB['assets']}/streets/{tile}.glb"
            if os.path.isfile(p):
                objs += import_glb(p, "streets")
        for tile in v.get("connection_tiles", []):
            p = f"{JOB['assets']}/connections/{tile}.glb"
            if os.path.isfile(p):
                objs += import_glb(p, "connections")
        for tile, inst in sorted(v.get("parts", {}).items()):
            p = f"{JOB['assets']}/parts/{tile}.glb"
            if os.path.isfile(p):
                objs += load_parts(p, inst)
        for o in objs:
            if ".glass.lod" in o.name and not o.name.endswith(".lod0"):
                o.hide_render = True
        sobjs = signs(v.get("signs", [])) + ag8(v, protos)
        cam = camera(sc, v)
        if v.get("section"):
            hidden += section(sc, cam, v)
        try:
            sc.eevee.taa_render_samples = v.get("samples") or JOB.get("samples", 32)
        except AttributeError:
            pass
        sc.render.resolution_x, sc.render.resolution_y = v["w"], v["h"]
        sc.render.resolution_percentage = 100
        lobjs = []
        for mode in JOB["modes"]:
            lighting(sc, sun, mode)
            if mode == "night" and not lobjs:
                lobjs = lamps(v.get("lights", []))
            for o in lobjs:
                o.hide_render = mode != "night"
            name = v["name"] if mode == "day" else f"{v['name']}_night"
            sc.render.filepath = f"{JOB['out']}/{name}.jpg"
            bpy.ops.render.render(write_still=True)
            rep["files"].append(f"{name}.jpg")
        faces = sum(len(o.data.polygons) for o in objs if o.type == "MESH")
        rep["views"].append({"name": v["name"], "faces": faces, "signs": len(sobjs),
                             "lights": len(lobjs), "seconds": round(time.time() - t, 1)})
        log(f"{v['name']}: {faces} faces, {len(sobjs)} sign faces, {len(lobjs)} lights, "
            f"{time.time() - t:.1f} s")
        remove(objs + sobjs + lobjs + [cam])
        for o in hidden:
            o.hide_render = False
        mark("done", v["name"])
    with open(f"{JOB['out']}/ag6_report.json", "w") as f:
        json.dump(rep, f, indent=1)
    log("done")


main()
