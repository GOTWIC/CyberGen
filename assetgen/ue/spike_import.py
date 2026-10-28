"""assetgen AG0 spike, run inside the Unreal 5.8 editor (stdlib and the `unreal` module only):

    UnrealEditor-Cmd PROJECT.uproject -run=pythonscript -script=assetgen/ue/spike_import.py

with $ASSETGEN_UE_JOB naming a job file ({"spike": dir with the glTF files and
unreal_contribution.json, "project_dir", "result"}). Under /Game/AssetgenSpike it:

1. makes the masters: M_AgOpaque (base color times the vertex color and a Custom Primitive
   Data tint, roughness, metallic, emissive) and M_AgGlass (opaque glass: interior mapping
   on UV1 with a room per window, its random id from the vertex alpha, lit rooms by the
   Custom Primitive Data lit ratio), and a material instance per slot of the contribution;
2. imports the spike's glTF files through Interchange in several variants and times each
   import and save: `Plain` (Nanite, no distance field, no Lumen cards: M15's settings),
   `DF` (distance field and Lumen cards on), `Quant` (KHR_mesh_quantization),
   `GpuInst` (EXT_mesh_gpu_instancing), `UBX` (collision boxes by mesh name);
3. tries Nanite voxel foliage on the test tree and a Nanite Assembly of the tower (its
   window frames and roof parts as assembly parts, experimental plugin);
4. builds the level Maps/Spike: each building's shell as a static mesh actor (simple
   collision boxes from its masses, Custom Primitive Data), its parts as hierarchical
   instanced meshes, the assembly tower beside it, a sun, sky light and atmosphere;
5. imports one glTF as a scene (Interchange's level import) to see what it does with
   EXT_mesh_gpu_instancing;
6. writes the result (timings, triangle counts, files on disk per asset) and quits.
"""

import json
import os
import time
import traceback

import unreal

JOB = json.load(open(os.environ["ASSETGEN_UE_JOB"], encoding="utf-8"))
ROOT = "/Game/AssetgenSpike"
CORE = f"{ROOT}/Core"
T0 = time.time()
EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
BEL = unreal.BlueprintEditorLibrary
NEVER = unreal.PropertyAccessChangeNotifyMode.NEVER
RES = {"ok": False, "imports": {}, "meshes": {}, "notes": [], "errors": {}}
CON = json.load(open(os.path.join(JOB["spike"], "unreal_contribution.json"), encoding="utf-8"))
NAMES = ("tower", "shopfront_row", "shanty_stack", "foliage_test")
OFFSET = {"tower": (0.0, 0.0), "shopfront_row": (70.0, -40.0),
          "shanty_stack": (110.0, -40.0), "foliage_test": (90.0, -15.0)}


def log(msg):
    unreal.log(f"assetgen spike: {msg} ({time.time() - T0:.1f} s)")


def ue(x, y, z):
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0)


def attempt(name, fn, *a):
    """Run one measurement; record its error and go on."""
    try:
        return fn(*a)
    except Exception:
        RES["errors"][name] = traceback.format_exc()
        unreal.log_error(f"assetgen spike: {name} failed\n{RES['errors'][name]}")
        return None


# --- masters ----------------------------------------------------------------------------------

def expr(m, cls, x, y, **props):
    e = MEL.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, out, b, inp):
    """Connect a's output to b's input; when the pin name is not taken, try b's own input
    names (they differ between expression kinds)."""
    if MEL.connect_material_expressions(a, out, b, inp):
        return True
    for name in [""] + [str(n) for n in MEL.get_material_expression_input_names(b)]:
        if MEL.connect_material_expressions(a, out, b, name):
            RES["notes"].append(f"{b.get_class().get_name()}: input '{inp}' is '{name}'")
            return True
    RES["notes"].append(f"could not connect {a.get_class().get_name()} -> "
                        f"{b.get_class().get_name()}.{inp}")
    return False


def opaque_master():
    path = f"{CORE}/M_AgOpaque"
    if EAL.does_asset_exist(path):
        return unreal.load_asset(path)
    m = AT.create_asset("M_AgOpaque", CORE, unreal.Material, unreal.MaterialFactoryNew())
    col = expr(m, unreal.MaterialExpressionVectorParameter, -900, -200, parameter_name="BaseColor",
               default_value=unreal.LinearColor(0.5, 0.5, 0.5, 1.0))
    tint = expr(m, unreal.MaterialExpressionVectorParameter, -900, 0, parameter_name="Tint",
                default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0),
                use_custom_primitive_data=True, primitive_data_index=0)
    vc = expr(m, unreal.MaterialExpressionVertexColor, -900, 200)
    m1 = expr(m, unreal.MaterialExpressionMultiply, -600, -100)
    link(col, "", m1, "A")
    link(tint, "", m1, "B")
    m2 = expr(m, unreal.MaterialExpressionMultiply, -400, 0)
    link(m1, "", m2, "A")
    link(vc, "", m2, "B")
    rough = expr(m, unreal.MaterialExpressionScalarParameter, -600, 250,
                 parameter_name="Roughness", default_value=0.85)
    metal = expr(m, unreal.MaterialExpressionScalarParameter, -600, 350,
                 parameter_name="Metallic", default_value=0.0)
    emi = expr(m, unreal.MaterialExpressionScalarParameter, -600, 450,
               parameter_name="Emissive", default_value=0.0)
    m3 = expr(m, unreal.MaterialExpressionMultiply, -400, 400)
    link(col, "", m3, "A")
    link(emi, "", m3, "B")
    MEL.connect_material_property(m2, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(metal, "", unreal.MaterialProperty.MP_METALLIC)
    MEL.connect_material_property(m3, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


INTERIOR = """
float3 d = -normalize(V);
d.z = min(d.z, -0.05);
float2 p = frac(UV);
float dx = abs(d.x) > 1e-4 ? d.x : 1e-4;
float dy = abs(d.y) > 1e-4 ? d.y : 1e-4;
float tx = ((d.x > 0 ? 1.0 : 0.0) - p.x) / dx;
float ty = ((d.y > 0 ? 1.0 : 0.0) - p.y) / dy;
float tz = -Depth / d.z;
float t = min(min(tx, ty), tz);
float3 h = float3(p, 0.0) + t * d;
float r = frac(sin(Seed * 91.7 + 1.3) * 43758.5);
float3 wall = lerp(float3(0.55, 0.50, 0.45), float3(0.33, 0.40, 0.48), r);
float3 c = wall * 0.65;
if (t == tz) { c = wall * 0.85; }
else if (t == ty) { c = d.y < 0 ? float3(0.22, 0.19, 0.17) : float3(0.85, 0.85, 0.80); }
float lit = step(frac(Seed * 13.37), Lit);
return c * (0.55 + 0.45 * saturate(1.0 + h.z / Depth)) * (0.15 + 2.5 * lit);
"""


def custom_input(name):
    ci = unreal.CustomInput()
    ci.set_editor_property("input_name", name)
    return ci


def glass_master():
    path = f"{CORE}/M_AgGlass"
    if EAL.does_asset_exist(path):
        return unreal.load_asset(path)
    m = AT.create_asset("M_AgGlass", CORE, unreal.Material, unreal.MaterialFactoryNew())
    uv = expr(m, unreal.MaterialExpressionTextureCoordinate, -1200, -200, coordinate_index=1)
    cam = expr(m, unreal.MaterialExpressionCameraVectorWS, -1400, 0)
    tr = expr(m, unreal.MaterialExpressionTransform, -1200, 0,
              transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
              transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_TANGENT)
    link(cam, "", tr, "Input")
    vc = expr(m, unreal.MaterialExpressionVertexColor, -1200, 200)
    lit = expr(m, unreal.MaterialExpressionScalarParameter, -1200, 350, parameter_name="LitRatio",
               default_value=0.5, use_custom_primitive_data=True, primitive_data_index=6)
    depth = expr(m, unreal.MaterialExpressionConstant, -1200, 450, r=1.0)
    cus = expr(m, unreal.MaterialExpressionCustom, -900, 0, code=INTERIOR,
               output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3,
               description="InteriorMapping",
               inputs=[custom_input(n) for n in ("UV", "V", "Seed", "Lit", "Depth")])
    link(uv, "", cus, "UV")
    link(tr, "", cus, "V")
    link(vc, "A", cus, "Seed")
    link(lit, "", cus, "Lit")
    link(depth, "", cus, "Depth")
    tint = expr(m, unreal.MaterialExpressionVectorParameter, -900, 300, parameter_name="BaseColor",
                default_value=unreal.LinearColor(0.1, 0.12, 0.15, 1.0))
    base = expr(m, unreal.MaterialExpressionMultiply, -600, -100)
    link(cus, "", base, "A")
    link(tint, "", base, "B")
    rough = expr(m, unreal.MaterialExpressionConstant, -600, 200, r=0.04)
    spec = expr(m, unreal.MaterialExpressionConstant, -600, 300, r=0.9)
    MEL.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(cus, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(spec, "", unreal.MaterialProperty.MP_SPECULAR)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


def material_instances():
    opaque = opaque_master()
    glass = attempt("glass_master", glass_master)
    if glass is None:
        RES["notes"].append("glass master failed: glass uses M_AgOpaque")
    masters = {"glass": glass or opaque, "other": opaque}
    out = {}
    for name, p in sorted(CON["materials"].items()):
        path = f"{ROOT}/Materials/MI_{name}"
        if EAL.does_asset_exist(path):
            out[name] = unreal.load_asset(path)
            continue
        mi = AT.create_asset(f"MI_{name}", f"{ROOT}/Materials", unreal.MaterialInstanceConstant,
                             unreal.MaterialInstanceConstantFactoryNew())
        master = masters["glass" if p["master"] == "glass" else "other"]
        MEL.set_material_instance_parent(mi, master)
        r, g, b = p["color"]
        MEL.set_material_instance_vector_parameter_value(
            mi, "BaseColor", unreal.LinearColor(r, g, b, 1.0))
        if master is masters["other"]:
            MEL.set_material_instance_scalar_parameter_value(mi, "Roughness", p["roughness"])
            MEL.set_material_instance_scalar_parameter_value(mi, "Metallic", p["metallic"])
            if p["master"] == "neon":
                MEL.set_material_instance_scalar_parameter_value(mi, "Emissive", 8.0)
        EAL.save_loaded_asset(mi)
        out[name] = mi
    return out


# --- imports ----------------------------------------------------------------------------------

def pipeline(df=False, by_name=False):
    gp = unreal.InterchangeGenericAssetsPipeline()
    gp.set_editor_property("asset_type_sub_folders", False)
    gp.set_editor_property("scene_name_sub_folder", False)
    gp.set_editor_property("use_source_name_for_asset", False)
    gp.get_editor_property("material_pipeline").set_editor_property("import_materials", False)
    msh = gp.get_editor_property("mesh_pipeline")
    msh.set_editor_property("import_skeletal_meshes", False)
    msh.set_editor_property("build_nanite", True)
    msh.set_editor_property("collision", by_name)
    if by_name:
        msh.set_editor_property("import_collision_according_to_mesh_name", True)
    else:
        msh.set_editor_property("fallback_collision_type", unreal.InterchangeMeshCollision.NONE)
    msh.set_editor_property("distance_field_resolution_scale", 1.0 if df else 0.0)
    msh.set_editor_property("max_lumen_mesh_cards", 12 if df else 0)
    stack = unreal.InterchangePipelineStackOverride()
    stack.add_pipeline(gp)
    return stack


def content_files(folder):
    """{file: bytes} of a content folder's package files on disk."""
    rel = folder[len("/Game/"):]
    base = os.path.join(JOB["project_dir"], "Content", rel)
    out = {}
    for dp, _, files in os.walk(base):
        for f in files:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, base)] = os.path.getsize(p)
    return out


def import_one(variant, name, glb, df=False, by_name=False):
    folder = f"{ROOT}/{variant}/{name}"
    task = unreal.AssetImportTask()
    task.filename = glb
    task.destination_path = folder
    task.automated = True
    task.replace_existing = True
    task.save = False
    task.options = pipeline(df, by_name)
    t = time.time()
    AT.import_asset_tasks([task])
    t_import = time.time() - t
    paths = [str(p) for p in task.get_editor_property("imported_object_paths")]
    t = time.time()
    EAL.save_directory(folder, only_if_is_dirty=False, recursive=True)
    t_save = time.time() - t
    meshes = {}
    for p in sorted(EAL.list_assets(folder, recursive=True)):
        a = unreal.load_asset(p.split(".")[0])
        if isinstance(a, unreal.StaticMesh):
            info = {"lod0_triangles": a.get_num_triangles(0),
                    "nanite": a.get_editor_property("nanite_settings").get_editor_property(
                        "enabled"),
                    "slots": [str(s.material_slot_name)
                              for s in a.get_editor_property("static_materials")]}
            bs = a.get_editor_property("body_setup")
            if bs is not None:
                ag = bs.get_editor_property("agg_geom")
                info["box_elems"] = len(ag.get_editor_property("box_elems"))
                info["convex_elems"] = len(ag.get_editor_property("convex_elems"))
            meshes[p.split(".")[0]] = info
    files = content_files(folder)
    rec = {"import_s": round(t_import, 2), "save_s": round(t_save, 2),
           "objects": len(paths), "static_meshes": len(meshes), "meshes": meshes,
           "disk_bytes": sum(files.values()), "files": files}
    RES["imports"].setdefault(variant, {})[name] = rec
    log(f"{variant}/{name}: import {t_import:.1f} s, save {t_save:.1f} s, "
        f"{len(meshes)} meshes, {rec['disk_bytes']} bytes")
    return rec


def imports():
    sp = JOB["spike"]
    for name in NAMES:
        attempt(f"Plain/{name}", import_one, "Plain", name, f"{sp}/{name}.glb")
    for name in NAMES:
        attempt(f"DF/{name}", import_one, "DF", name, f"{sp}/{name}.glb", True)
    for name in ("tower", "shopfront_row", "shanty_stack"):
        attempt(f"Quant/{name}", import_one, "Quant", name, f"{sp}/{name}_quant.glb")
        attempt(f"GpuInst/{name}", import_one, "GpuInst", name, f"{sp}/{name}_gpuinst.glb")
        attempt(f"UBX/{name}", import_one, "UBX", name, f"{sp}/{name}_ubx.glb", False, True)


def mesh_of(variant, name, suffix):
    folder = f"{ROOT}/{variant}/{name}"
    for p in sorted(EAL.list_assets(folder, recursive=True)):
        base = p.split(".")[0]
        if base.endswith(suffix):
            a = unreal.load_asset(base)
            if isinstance(a, unreal.StaticMesh):
                return a
    return None


def entry(name):
    key = f"spike.{name}.bld" if name != "foliage_test" else "spike.tree.plt"
    return next(e for e in CON["entries"] if e["key"] == key)


# --- finishing the meshes -----------------------------------------------------------------------

def finish_mesh(sm, mats, boxes):
    """Material instances by slot name, simple collision boxes from the masses."""
    slots = []
    for s in sm.get_editor_property("static_materials"):
        mi = mats.get(str(s.material_slot_name))
        if mi is not None:
            s.set_editor_property("material_interface", mi)
        slots.append(s)
    sm.set_editor_property("static_materials", slots, NEVER)
    if boxes:
        bs = sm.get_editor_property("body_setup")
        ag = bs.get_editor_property("agg_geom")
        elems = []
        for b in boxes:
            e = unreal.KBoxElem()
            c, x = b["center"], b["extent"]
            e.set_editor_property("center", ue(*c))
            e.set_editor_property("x", 200.0 * x[0])
            e.set_editor_property("y", 200.0 * x[1])
            e.set_editor_property("z", 200.0 * x[2])
            elems.append(e)
        ag.set_editor_property("box_elems", elems)
        bs.set_editor_property("agg_geom", ag)
        bs.set_editor_property("collision_trace_flag",
                               unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    EAL.save_loaded_asset(sm, only_if_is_dirty=False)
    bs = sm.get_editor_property("body_setup")
    return len(bs.get_editor_property("agg_geom").get_editor_property("box_elems"))


def voxel_foliage():
    sm = mesh_of("Plain", "foliage_test", "shell")
    ns = sm.get_editor_property("nanite_settings")
    ns.set_editor_property("shape_preservation", unreal.NaniteShapePreservation.VOXELIZE)
    t = time.time()
    sm.set_editor_property("nanite_settings", ns)
    EAL.save_loaded_asset(sm, only_if_is_dirty=False)
    got = sm.get_editor_property("nanite_settings").get_editor_property("shape_preservation")
    RES["voxel_foliage"] = {"rebuild_s": round(time.time() - t, 2), "shape_preservation": str(got)}


def assembly():
    """The tower shell with its window frames and roof parts as Nanite Assembly parts."""
    if not hasattr(unreal, "NaniteAssemblyStaticMeshBuilder"):
        RES["assembly"] = {"available": False}
        return
    shell = mesh_of("Plain", "tower", "shell")
    dst = f"{ROOT}/Assembly/SM_tower_assembly"
    if EAL.does_asset_exist(dst):
        EAL.delete_asset(dst)
    base = EAL.duplicate_asset(shell.get_path_name().split(".")[0], dst)
    t = time.time()
    b = unreal.NaniteAssemblyStaticMeshBuilder.begin_edit_static_mesh_assembly_build(base)
    n = 0
    for part in entry("tower")["parts"]:
        pm = mesh_of("Plain", "tower", part["asset"][len("spike_tower_bld_"):])
        xf = [unreal.Transform(ue(x, y, z), unreal.Rotator(0.0, 0.0, -yaw), unreal.Vector(1, 1, 1))
              for x, y, z, yaw in part["xforms"]]
        ok = b.add_assembly_parts(pm, xf, unreal.NaniteAssemblyMaterialMergeOptions())
        n += len(xf) if ok else 0
    res = b.finish_assembly_build()
    ok, mesh = res if isinstance(res, tuple) else (bool(res), base)
    t_build = time.time() - t
    EAL.save_directory(f"{ROOT}/Assembly", only_if_is_dirty=False, recursive=True)
    RES["assembly"] = {"available": True, "ok": bool(ok), "parts_added": n,
                       "build_s": round(t_build, 2),
                       "disk_bytes": sum(content_files(f"{ROOT}/Assembly").values())}
    log(f"assembly: {n} parts in {t_build:.1f} s")


# --- the level ---------------------------------------------------------------------------------

def instances_class():
    path = f"{CORE}/BP_AgInstances"
    bp = unreal.load_asset(path) if EAL.does_asset_exist(path) else None
    if bp is None:
        bp = BEL.create_blueprint_asset_with_parent(path, unreal.Actor)
        sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
        root = sds.k2_gather_subobject_data_for_blueprint(bp)[0]
        h, _ = sds.add_new_subobject(unreal.AddNewSubobjectParams(
            parent_handle=root, new_class=unreal.HierarchicalInstancedStaticMeshComponent,
            blueprint_context=bp))
        sds.rename_subobject(h, "Instances")
        BEL.compile_blueprint(bp)
        EAL.save_loaded_asset(bp, only_if_is_dirty=False)
    return BEL.generated_class(bp)


def level(mats):
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    path = f"{ROOT}/Maps/Spike"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    if not les.new_level(path, True):
        raise RuntimeError("cannot create the level")
    cls = instances_class()
    placed = {}
    for name in NAMES:
        e = entry(name)
        sm = mesh_of("Plain", name, "shell")
        boxes = finish_mesh(sm, mats, e["collision"]["simple"])
        ox, oy = OFFSET[name]
        a = eas.spawn_actor_from_class(unreal.StaticMeshActor, ue(ox, oy, 0.0))
        a.set_actor_label(e["key"])
        comp = a.static_mesh_component
        comp.set_static_mesh(sm)
        for i, v in enumerate(e["cpd"]):
            comp.set_custom_primitive_data_float(i, float(v))
        a.tags = [unreal.Name(f"cg.key={e['key']}"), unreal.Name(f"cg.hash={e['hash']}")]
        n_inst = 0
        for part in e["parts"]:
            pm = mesh_of("Plain", name, part["asset"][len(e["asset"]) + 1:])
            if pm is None or not part["xforms"]:
                continue
            finish_mesh(pm, mats, None)
            ia = eas.spawn_actor_from_class(cls, ue(ox, oy, 0.0))
            ia.set_actor_label(f"{e['key']}.{part['kind']}")
            h = ia.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)[0]
            h.set_static_mesh(pm)
            xf = [unreal.Transform(ue(x, y, z), unreal.Rotator(0.0, 0.0, -yaw),
                                   unreal.Vector(1, 1, 1)) for x, y, z, yaw in part["xforms"]]
            h.add_instances(xf, False, False)
            for i, v in enumerate(e["cpd"]):
                h.set_custom_primitive_data_float(i, float(v))
            n_inst += len(xf)
        placed[name] = {"collision_boxes": boxes, "instances": n_inst}
    if RES.get("assembly", {}).get("ok"):
        am = unreal.load_asset(f"{ROOT}/Assembly/SM_tower_assembly")
        a = eas.spawn_actor_from_class(unreal.StaticMeshActor, ue(-110.0, 0.0, 0.0))
        a.set_actor_label("spike.tower.assembly")
        a.static_mesh_component.set_static_mesh(am)
        for i, v in enumerate(entry("tower")["cpd"]):
            a.static_mesh_component.set_custom_primitive_data_float(i, float(v))
    sun = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 50000))
    sun.set_actor_rotation(unreal.Rotator(0.0, -38.0, 125.0), False)
    sun.light_component.set_editor_property("atmosphere_sun_light", True)
    sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 40000))
    sky.light_component.set_editor_property("real_time_capture", True)
    eas.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
    floor = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, -5))
    floor.static_mesh_component.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/Plane"))
    floor.set_actor_scale3d(unreal.Vector(800.0, 800.0, 1.0))
    les.save_current_level()
    RES["level"] = {"path": path, "placed": placed}


def scene_import():
    """Interchange's level import of a glTF with EXT_mesh_gpu_instancing: what lands."""
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    path = f"{ROOT}/Maps/SceneTest"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    les.new_level(path, False)
    before = len(eas.get_all_level_actors())
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    src = unreal.InterchangeManager.create_source_data(f"{JOB['spike']}/shopfront_row_gpuinst.glb")
    params = unreal.ImportAssetParameters()
    params.is_automated = True
    mgr.import_scene(f"{ROOT}/SceneTest", src, params)
    if hasattr(mgr, "wait_until_all_tasks_done"):
        mgr.wait_until_all_tasks_done(False)
    actors = eas.get_all_level_actors()
    comps = {}
    for a in actors:
        for c in a.get_components_by_class(unreal.StaticMeshComponent):
            k = c.get_class().get_name()
            comps[k] = comps.get(k, 0) + 1
    inst = 0
    for a in actors:
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            inst += c.get_instance_count()
    RES["scene_import"] = {"actors": len(actors) - before, "components": comps,
                           "ism_instances": inst,
                           "parts_in_file": sum(p["count"] for p in entry("shopfront_row")["parts"])}
    les.save_current_level()


def main():
    log("start")
    mats = material_instances()
    imports()
    attempt("voxel_foliage", voxel_foliage)
    attempt("assembly", assembly)
    attempt("level", level, mats)
    attempt("scene_import", scene_import)
    RES["ok"] = not RES["errors"]
    RES["total_s"] = round(time.time() - T0, 1)


try:
    main()
except Exception:
    RES["errors"]["main"] = traceback.format_exc()
    unreal.log_error(RES["errors"]["main"])
with open(JOB["result"], "w", encoding="utf-8") as f:
    json.dump(RES, f, indent=1, default=str)
print("ASSETGEN_UE_DONE " + json.dumps({"ok": RES["ok"], "total_s": RES.get("total_s")}))
