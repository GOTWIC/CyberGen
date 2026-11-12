"""signature.py: what a car's script builds, as a fingerprint (Blender side: stdlib and bpy).

    vehicles/blender.sh vehicles/signature.py vehicles/cars/NAME.py OUT.json
    python vehicles/survey.py --sign DIR          # every car, into DIR/<car>.json
    python vehicles/survey.py --compare A B       # two such folders, car by car

Builds the car (no render) and writes a hash of every object's geometry as built (vertices
to 0.01 mm, polygons, material slots), of every material's node tree, of the studio (lights,
light linking) and of the sheet's cameras. A change to carkit.py that should not change the
cars is proved by signing every car before and after it and comparing: the same signatures
mean the same sheets and the same game packs.
"""
import hashlib
import json
import os
import runpy
import shutil
import sys
import tempfile

argv = sys.argv[sys.argv.index("--") + 1:]
script, dst = os.path.abspath(argv[0]), os.path.abspath(argv[1])
saved = sys.argv
tmp = tempfile.mkdtemp(prefix="cybergen_sign_")
sys.argv = [saved[0], "--", "--out", tmp]
runpy.run_path(script, run_name="__main__")
sys.argv = saved
shutil.rmtree(tmp, ignore_errors=True)
import bpy  # noqa: E402

K = sys.modules["carkit"]
# node properties that say nothing about what a material looks like
SKIP = {"rna_type", "location", "location_absolute", "width", "height", "name", "label",
        "select", "dimensions", "parent", "color", "inputs", "outputs", "internal_links",
        "warning_propagation", "show_options", "show_preview", "hide", "mute", "show_texture",
        "use_custom_color", "bl_idname", "bl_label", "bl_description", "bl_icon",
        "bl_static_type", "bl_width_default", "bl_width_min", "bl_width_max",
        "bl_height_default", "bl_height_min", "bl_height_max", "type", "color_tag",
        "debug_zone_body_lazy_function_graph", "debug_zone_lazy_function_graph"}


def r(x):
    try:
        return [round(float(v), 5) for v in x]
    except TypeError:
        try:
            return round(float(x), 5)
        except (TypeError, ValueError):
            return repr(x)


def objects():
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    for ob in sorted(K.CAR.objects, key=lambda o: o.name):
        row = dict(type=ob.type, mw=[r(c) for c in ob.matrix_world])
        if ob.type == 'MESH':
            ev = ob.evaluated_get(dg)
            me = ev.to_mesh()
            h = hashlib.sha1()
            for v in me.vertices:
                h.update(("%.5f %.5f %.5f|" % tuple(v.co)).encode())
            for p in me.polygons:
                h.update((",".join(map(str, p.vertices))
                          + ";%d;%d|" % (p.material_index, p.use_smooth)).encode())
            row.update(verts=len(me.vertices), polys=len(me.polygons), sha=h.hexdigest(),
                       mats=[m.name if m else None for m in ob.data.materials])
            ev.to_mesh_clear()
        out[ob.name] = row
    return out


def materials():
    out = {}
    for m in sorted(bpy.data.materials, key=lambda m: m.name):
        nt = m.node_tree
        if nt is None:
            continue
        rows = []
        for n in sorted(nt.nodes, key=lambda n: n.name):
            props = {}
            for p in n.bl_rna.properties:
                if p.identifier in SKIP:
                    continue
                try:
                    props[p.identifier] = r(getattr(n, p.identifier))
                except Exception:
                    pass
            ins = [(i.identifier, r(i.default_value) if hasattr(i, "default_value") else None)
                   for i in n.inputs]
            rows.append([n.bl_idname, n.name, props, ins])
        links = sorted((ln.from_node.name, ln.from_socket.identifier, ln.to_node.name,
                        ln.to_socket.identifier) for ln in nt.links)
        out[m.name] = hashlib.sha1(json.dumps([rows, links], sort_keys=True,
                                              default=repr).encode()).hexdigest()
    return out


def studio():
    out = {}
    for ob in sorted(K.STUDIO.objects, key=lambda o: o.name):
        row = dict(type=ob.type, mw=[r(c) for c in ob.matrix_world],
                   vis=[ob.visible_camera, ob.visible_transmission, ob.visible_glossy,
                        ob.visible_diffuse])
        if ob.type == 'LIGHT':
            row.update(energy=r(ob.data.energy), color=r(ob.data.color),
                       size=r([ob.data.size, ob.data.size_y]))
            rc = ob.light_linking.receiver_collection
            if rc is not None:
                row["links"] = sorted((o.name, c.light_linking.link_state)
                                      for o, c in zip(rc.objects, rc.collection_objects))
        out[ob.name] = row
    return out


def cameras():
    out = {}
    for name, res in (("hero", (3840, 1536)), ("side", (1600, 620)), ("front", (1100, 620)),
                      ("back", (1100, 620)), ("rear", (958, 538)), ("top", (958, 538))):
        if name not in K.VIEWS:
            continue
        K.SCN.render.resolution_x, K.SCN.render.resolution_y = res
        cam = K.add_camera("sig_" + name, K.VIEWS[name])
        bpy.context.view_layer.update()
        out[name] = dict(mw=[r(c) for c in cam.matrix_world], lens=r(cam.data.lens))
    return out


lo, hi = K.car_size()
world = K.SCN.world.node_tree.nodes["Background"].inputs["Strength"].default_value \
    if K.SCN.world else None
sig = dict(objects=objects(), materials=materials(), studio=studio(), cams=cameras(),
           tris=K.tri_count(), size=[r(lo), r(hi)], world=r(world))
os.makedirs(os.path.dirname(dst), exist_ok=True)
with open(dst, "w") as f:
    json.dump(sig, f, indent=1, sort_keys=True)
print("SIGNATURE wrote", dst, "objects", len(sig["objects"]), "triangles", sig["tris"])
