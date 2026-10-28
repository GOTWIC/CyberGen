"""citygen M15 importer, run inside the Unreal 5.8 editor (stdlib and the `unreal` module
only; citygen is not importable here):

    UnrealEditor-Cmd PROJECT.uproject -run=pythonscript -script=citygen/ue/import_city.py

with $CITYGEN_UE_JOB naming a job file ({"manifest": ..., "result": ...}) that
`citygen unreal` writes. It reads BUILD_DIR/unreal/manifest.json (see citygen/unreal.py) and
makes, under /Game/CityGen/<City>:

- Maps/<City>: a World Partition level, one static mesh actor per blockout object of the
  glTF tiles (complex collision, per-category materials), one BP_CityGenInstances actor per
  prop or plant kind and tile (instanced static meshes, the instances' citygen ids), a
  player start; every actor tagged `cg.city=`, `cg.key=` (its blockout name), `cg.hash=`
  (its content), `cg.id=` (its citygen ids), `cg.type=`, `cg.category=`, `cg.tile=` and
  `cg.district=` (M14: `cg.level=` on a deck);
- Meshes/<tile>/<object>, Props/<kind>: static meshes, each with its content hash as
  `cg.hash` metadata;
- Materials/MI_<material>: instances of /Game/CityGen/Core/M_CityGen;
- Data/DA_<City>_Lanes, _Walkways, _Transit: BP_CityGenGraph data assets (flat arrays).

With stage 2 in the manifest (assetgen's buildings and streets over the blockout), also:

- Assets/<Part>/<pack>, <Part>Proxies/<pack>, <Part>Parts/<pack>: the packs' static meshes
  (each in its node's frame; collision: a building's mass pieces as convex hulls through
  GeometryScript, complex for streets, none for the sky tube glass and proxies; Nanite on
  except those; the glass's LOD chain made from its LOD meshes), proxies imported only;
- Assets/Materials/MI_<part>_<slot>: instances of the stage 2 masters (Core/M_CgFacade,
  M_CgGlass, M_CgMetal, M_CgRoad, M_CgOpaque, M_CgEmissive, M_CgTranslucent, M_CgFoliage,
  ...), the tint from the actor's Custom Primitive Data;
- an actor per entry at its pivot (Custom Primitive Data, `cg.stage=2`) in place of the
  blockout actors it replaces, and a BP_CityGenInstances actor per entry and part kind.

Importing again updates by key and hash: a tile's meshes are imported again only when one
of its objects changed or is missing, an actor is changed only when its hash changed, and
what the build no longer has is deleted. The same build twice changes nothing.
"""

import hashlib
import json
import math
import os
import time
import traceback

import unreal

JOB = json.load(open(os.environ["CITYGEN_UE_JOB"], encoding="utf-8"))
CORE = "/Game/CityGen/Core"
CORE_VERSION = "2"  # of the core assets (BP_CityGenInstances, BP_CityGenGraph)
NEVER = unreal.PropertyAccessChangeNotifyMode.NEVER
T0 = time.time()
EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
BEL = unreal.BlueprintEditorLibrary
HASH_TAG = "cg.hash"
# bumped when the importer makes meshes or actors differently, so the next import of an
# unchanged build applies the change (stored hashes are "<version>.<content hash>")
MESH_VERSION = "3"
ACTOR_VERSION = "1"
GRAPH_VARS = [("City", "string"), ("Graph", "name"), ("Hash", "string"), ("Ids", "[name"),
              ("Kinds", "[name"), ("Refs", "[name"), ("Widths", "[real"),
              ("PointStart", "[int"), ("Points", "[vector"), ("LinkStart", "[int"),
              ("Links", "[int"), ("Attrs", "[string"), ("Levels", "[int")]   # (M14)
INSTANCE_VARS = [("Ids", "[name"), ("Kind", "name")]
# stage 2 (assetgen, layer 2): the masters' version (Core/M_Cg<Master>, rebuilt in place when
# it changes) and the meshes' (stored hashes "<version>.<content hash>", as MESH_VERSION)
STAGE2_VERSION = "1"
STAGE2_MESH_VERSION = "2"
TINT_CPD = (0, 8, 11, 14, 17, 20)    # citygen.unreal.TINT_CPD: the tints a master reads
LIT_CPD = 6                          # the lit-window ratio (AG1's cpd_layout)
STAGE2_FOLDER = "Assets"             # citygen.unreal.STAGE2_FOLDER


def log(msg):
    unreal.log(f"citygen: {msg} ({time.time() - T0:.1f} s)")


def ue_loc(x, y, z):
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0)


def sha16(data) -> str:
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def meta(asset, key):
    return EAL.get_metadata_tag(asset, key) or ""


# --- core assets (shared by every city) ---------------------------------------------------------

def pin_type(spec):
    arr = spec.startswith("[")
    base = spec.lstrip("[")
    t = (BEL.get_struct_type(unreal.Vector.static_struct()) if base == "vector"
         else BEL.get_basic_type_by_name(base))
    return BEL.get_array_type(t) if arr else t


def blueprint(path, parent, variables, hism=False):
    """A Blueprint class with the given member variables (instance editable; added when
    missing or when the class is of an older CORE_VERSION), compiled."""
    bp = unreal.load_asset(path) if EAL.does_asset_exist(path) else None
    if bp is not None and meta(bp, "cg.core") == CORE_VERSION:
        return BEL.generated_class(bp)
    fresh = bp is None
    if fresh:
        bp = BEL.create_blueprint_asset_with_parent(path, parent)
        if hism:
            sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
            root = sds.k2_gather_subobject_data_for_blueprint(bp)[0]
            h, fail = sds.add_new_subobject(unreal.AddNewSubobjectParams(
                parent_handle=root,
                new_class=unreal.HierarchicalInstancedStaticMeshComponent,
                blueprint_context=bp))
            sds.rename_subobject(h, "Instances")
    have = {str(n) for n in BEL.list_member_variable_names(bp)} if not fresh else set()
    for name, spec in variables:
        if name not in have:
            BEL.add_member_variable(bp, name, pin_type(spec))
        BEL.set_blueprint_variable_instance_editable(bp, name, True)
    BEL.compile_blueprint(bp)
    EAL.set_metadata_tag(bp, "cg.core", CORE_VERSION)
    EAL.save_loaded_asset(bp, only_if_is_dirty=False)
    return BEL.generated_class(bp)


def base_material():
    path = f"{CORE}/M_CityGen"
    if EAL.does_asset_exist(path):
        return unreal.load_asset(path)
    m = AT.create_asset("M_CityGen", CORE, unreal.Material, unreal.MaterialFactoryNew())
    col = MEL.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -500, 0)
    col.set_editor_property("parameter_name", "BaseColor")
    col.set_editor_property("default_value", unreal.LinearColor(0.5, 0.5, 0.5, 1.0))
    rough = MEL.create_material_expression(m, unreal.MaterialExpressionScalarParameter,
                                           -500, 200)
    rough.set_editor_property("parameter_name", "Roughness")
    rough.set_editor_property("default_value", 0.85)
    emi = MEL.create_material_expression(m, unreal.MaterialExpressionScalarParameter,
                                         -500, 320)
    emi.set_editor_property("parameter_name", "Emissive")
    emi.set_editor_property("default_value", 0.0)
    mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -250, 300)
    MEL.connect_material_expressions(col, "", mul, "A")
    MEL.connect_material_expressions(emi, "", mul, "B")
    MEL.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    m.set_editor_property("two_sided", True)
    MEL.recompile_material(m)
    EAL.save_loaded_asset(m)
    return m


# --- stage 2 masters (assetgen's materials; AG0's spike made the first) ------------------------

def expr(m, cls, x, y, **props):
    e = MEL.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, out, b, inp):
    """Connect a's output to b's input (by name, else b's only input when it has no name,
    else by the input names b lists)."""
    if MEL.connect_material_expressions(a, out, b, inp):
        return
    names = [str(n) for n in MEL.get_material_expression_input_names(b)]
    if len(names) <= 1 and MEL.connect_material_expressions(a, out, b, ""):
        return
    for name in names:
        if name.lower() == inp.lower() and MEL.connect_material_expressions(a, out, b, name):
            return
    raise RuntimeError(f"cannot connect {a.get_class().get_name()} to "
                       f"{b.get_class().get_name()}.{inp}")


def custom(m, x, y, code, inputs, out_type, name):
    ins = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    return expr(m, unreal.MaterialExpressionCustom, x, y, code=code, output_type=out_type,
                description=name, inputs=ins)


# a slot's color: its own (BaseColor), or the actor's Custom Primitive Data tint at the
# instance's TintChannel (AG1: the building's wall, trim, glass, roof, spandrel or patch
# color), times TintScale, times its own color too where TintTimesColor is set
TINT_CODE = """
float3 t = Base;
if (Ch > -0.5) {
  t = Ch < 4.0 ? C0 : (Ch < 9.5 ? C8 : (Ch < 12.5 ? C11 : (Ch < 15.5 ? C14 :
      (Ch < 18.5 ? C17 : C20))));
  t *= Scale;
  if (Mul > 0.5) { t *= Base; }
}
return t;
"""

# the room behind a window (interior mapping on UV1, one room per pane, its look from the
# window id in the vertex alpha) and whether it is lit (the actor's lit-window ratio)
ROOM_CODE = """
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
return c * (0.55 + 0.45 * saturate(1.0 + h.z / Depth));
"""
LIT_CODE = "return (Seed > 0.002 && frac(Seed * 13.37) < Lit) ? 1.0 : 0.0;"


def tint_color(m, x, y):
    """The float3 color of TINT_CODE and its parameters."""
    f3 = unreal.CustomMaterialOutputType.CMOT_FLOAT3
    base = expr(m, unreal.MaterialExpressionVectorParameter, x - 400, y - 300,
                parameter_name="BaseColor", default_value=unreal.LinearColor(0.5, 0.5, 0.5, 1))
    ch = expr(m, unreal.MaterialExpressionScalarParameter, x - 400, y - 150,
              parameter_name="TintChannel", default_value=-1.0)
    sc = expr(m, unreal.MaterialExpressionScalarParameter, x - 400, y - 80,
              parameter_name="TintScale", default_value=1.0)
    mul = expr(m, unreal.MaterialExpressionScalarParameter, x - 400, y - 10,
               parameter_name="TintTimesColor", default_value=0.0)
    cus = custom(m, x, y, TINT_CODE, ["Base", "Ch", "Scale", "Mul"] +
                 [f"C{i}" for i in TINT_CPD], f3, "CityGenTint")
    link(base, "", cus, "Base")
    link(ch, "", cus, "Ch")
    link(sc, "", cus, "Scale")
    link(mul, "", cus, "Mul")
    for k, i in enumerate(TINT_CPD):
        v = expr(m, unreal.MaterialExpressionVectorParameter, x - 400, y + 80 + 90 * k,
                 parameter_name=f"Tint{i}", default_value=unreal.LinearColor(1, 1, 1, 1),
                 use_custom_primitive_data=True, primitive_data_index=i)
        link(v, "", cus, f"C{i}")
    return cus


def stage2_master(master):
    """/Game/CityGen/Core/M_Cg<Master>: `glass` (interior mapping), `translucent` (blended,
    two-sided), else opaque (`foliage` two-sided) with an emissive strength; each takes its
    color from tint_color. Made, or rebuilt in place when of an older STAGE2_VERSION (its
    instances keep it as their parent)."""
    name = "M_Cg" + "".join(w.capitalize() for w in master.split("_"))
    path = f"{CORE}/{name}"
    m = unreal.load_asset(path) if EAL.does_asset_exist(path) else None
    if m is not None and meta(m, "cg.core2") == STAGE2_VERSION:
        return m
    if m is None:
        m = AT.create_asset(name, CORE, unreal.Material, unreal.MaterialFactoryNew())
    else:
        MEL.delete_all_material_expressions(m)
    MP = unreal.MaterialProperty
    col = tint_color(m, -600, 0)
    rough = expr(m, unreal.MaterialExpressionScalarParameter, -300, 300,
                 parameter_name="Roughness", default_value=0.85)
    metal = expr(m, unreal.MaterialExpressionScalarParameter, -300, 380,
                 parameter_name="Metallic", default_value=0.0)
    if master == "glass":
        f1, f3 = (unreal.CustomMaterialOutputType.CMOT_FLOAT1,
                  unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        uv = expr(m, unreal.MaterialExpressionTextureCoordinate, -1300, 600, coordinate_index=1)
        cam = expr(m, unreal.MaterialExpressionCameraVectorWS, -1500, 750)
        tr = expr(m, unreal.MaterialExpressionTransform, -1300, 750,
                  transform_source_type=unreal.MaterialVectorCoordTransformSource
                  .TRANSFORMSOURCE_WORLD,
                  transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_TANGENT)
        link(cam, "", tr, "Input")
        vc = expr(m, unreal.MaterialExpressionVertexColor, -1300, 900)
        depth = expr(m, unreal.MaterialExpressionConstant, -1300, 1000, r=1.0)
        room = custom(m, -1000, 700, ROOM_CODE, ["UV", "V", "Seed", "Depth"], f3, "Room")
        link(uv, "", room, "UV")
        link(tr, "", room, "V")
        link(vc, "A", room, "Seed")
        link(depth, "", room, "Depth")
        ratio = expr(m, unreal.MaterialExpressionScalarParameter, -1300, 1100,
                     parameter_name="LitRatio", default_value=0.3,
                     use_custom_primitive_data=True, primitive_data_index=LIT_CPD)
        scale = expr(m, unreal.MaterialExpressionScalarParameter, -1300, 1200,
                     parameter_name="LitScale", default_value=0.1)
        lr = expr(m, unreal.MaterialExpressionMultiply, -1100, 1150)
        link(ratio, "", lr, "A")
        link(scale, "", lr, "B")
        lit = custom(m, -1000, 1000, LIT_CODE, ["Seed", "Lit"], f1, "Lit")
        link(vc, "A", lit, "Seed")
        link(lr, "", lit, "Lit")
        # by day: the glass's tint, a little of the room behind it; the lit rooms glow
        g2 = expr(m, unreal.MaterialExpressionMultiply, -350, -100, const_b=2.0)
        link(col, "", g2, "A")
        dim = expr(m, unreal.MaterialExpressionMultiply, -600, 650, const_b=0.12)
        link(room, "", dim, "A")
        base = expr(m, unreal.MaterialExpressionAdd, -200, 0)
        link(g2, "", base, "A")
        link(dim, "", base, "B")
        glow = expr(m, unreal.MaterialExpressionMultiply, -600, 850)
        link(room, "", glow, "A")
        link(lit, "", glow, "B")
        glow2 = expr(m, unreal.MaterialExpressionMultiply, -350, 850, const_b=3.0)
        link(glow, "", glow2, "A")
        spec = expr(m, unreal.MaterialExpressionConstant, -300, 460, r=0.8)
        MEL.connect_material_property(base, "", MP.MP_BASE_COLOR)
        MEL.connect_material_property(glow2, "", MP.MP_EMISSIVE_COLOR)
        MEL.connect_material_property(spec, "", MP.MP_SPECULAR)
    elif master == "translucent":
        op = expr(m, unreal.MaterialExpressionScalarParameter, -300, 460,
                  parameter_name="Opacity", default_value=0.35)
        MEL.connect_material_property(col, "", MP.MP_BASE_COLOR)
        MEL.connect_material_property(op, "", MP.MP_OPACITY)
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
        m.set_editor_property("two_sided", True)
        mode = getattr(unreal.TranslucencyLightingMode, "TLM_SURFACE", None)
        if mode is not None:
            m.set_editor_property("translucency_lighting_mode", mode)
    else:
        emi = expr(m, unreal.MaterialExpressionScalarParameter, -300, 540,
                   parameter_name="Emissive", default_value=0.0)
        em = expr(m, unreal.MaterialExpressionMultiply, -150, 500)
        link(col, "", em, "A")
        link(emi, "", em, "B")
        MEL.connect_material_property(col, "", MP.MP_BASE_COLOR)
        MEL.connect_material_property(em, "", MP.MP_EMISSIVE_COLOR)
        m.set_editor_property("two_sided", master == "foliage")
    MEL.connect_material_property(rough, "", MP.MP_ROUGHNESS)
    MEL.connect_material_property(metal, "", MP.MP_METALLIC)
    MEL.recompile_material(m)
    EAL.set_metadata_tag(m, "cg.core2", STAGE2_VERSION)
    EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m


# --- the city ---------------------------------------------------------------------------------

def delete_assets(paths):
    """Delete the assets at `paths` in one go (one by one takes about 0.4 s each: a garbage
    collection per asset); how many were deleted. The actors that used them were destroyed
    and the level saved before, so a garbage collection first lets go of them."""
    if not paths:
        return 0
    unreal.SystemLibrary.collect_garbage()
    objs = [o for o in (EAL.load_asset(p) for p in paths) if o is not None]
    if objs:
        EAL.delete_loaded_assets(objs)
    left = [p for p in paths if EAL.does_asset_exist(p.split(".")[0])]
    for p in left:
        EAL.delete_asset(p)
    return len(paths) - sum(1 for p in left if EAL.does_asset_exist(p.split(".")[0]))


class Importer:
    def __init__(self, man, build_dir):
        self.man = man
        self.build = build_dir
        self.root = man["content_root"]
        self.city = man["slug"]
        self.stats = {"actors": {"created": 0, "updated": 0, "deleted": 0, "unchanged": 0},
                      "meshes": {"imported": 0, "kept": 0, "deleted": 0},
                      "tiles_imported": 0, "materials": {"created": 0, "updated": 0,
                                                         "kept": 0, "deleted": 0},
                      "graphs": {"written": 0, "kept": 0}, "timings": {}}
        # the keys of the actors created, updated and deleted (a test compares them with the
        # objects whose hash changed between two manifests)
        self.keys = {"created": [], "updated": [], "deleted": []}
        self.eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        self.les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.mats = {}
        # stage 2 (assetgen): its materials by (part, slot), the blockout keys it replaces
        self.s2 = man.get("stage2")
        self.mats2 = {}
        self.skip = set(self.s2["replaced"]) | {a["key"] for a in self.s2["actors"]} \
            if self.s2 else set()
        if self.s2:
            self.stats["stage2"] = {
                "actors": len(self.s2["actors"]), "instance_actors": len(self.s2["instances"]),
                "replaced": len(self.s2["replaced"]),
                "meshes": {"imported": 0, "kept": 0, "deleted": 0}, "packs_imported": 0,
                "materials": {"created": 0, "updated": 0, "kept": 0, "deleted": 0},
                "hulls": 0, "boxes_only": 0, "complex_fallback": 0, "lod_chains": 0}

    def timed(self, name, fn, *a):
        t = time.time()
        r = fn(*a)
        self.stats["timings"][name] = round(time.time() - t, 2)
        log(f"{name} done")
        return r

    # -- materials --

    def materials(self, base):
        folder = f"{self.root}/Materials"
        want = set()
        for name, p in sorted(self.man["materials"].items()):
            path = f"{folder}/MI_{name}"
            want.add(path)
            h = sha16(p)
            if EAL.does_asset_exist(path):
                mi = unreal.load_asset(path)
                if meta(mi, HASH_TAG) == h:
                    self.stats["materials"]["kept"] += 1
                    self.mats[name] = mi
                    continue
                self.stats["materials"]["updated"] += 1
            else:
                mi = AT.create_asset(f"MI_{name}", folder, unreal.MaterialInstanceConstant,
                                     unreal.MaterialInstanceConstantFactoryNew())
                MEL.set_material_instance_parent(mi, base)
                self.stats["materials"]["created"] += 1
            r, g, b = p["color"]
            MEL.set_material_instance_vector_parameter_value(
                mi, "BaseColor", unreal.LinearColor(r, g, b, 1.0))
            MEL.set_material_instance_scalar_parameter_value(mi, "Roughness", p["roughness"])
            MEL.set_material_instance_scalar_parameter_value(mi, "Emissive", p["emissive"])
            EAL.set_metadata_tag(mi, HASH_TAG, h)
            EAL.save_loaded_asset(mi)
            self.mats[name] = mi
        stale = [a for a in EAL.list_assets(folder, recursive=False)
                 if a.split(".")[0] not in want]
        self.stats["materials"]["deleted"] += delete_assets(stale)

    # -- meshes --

    def pipeline(self, nanite=True, bake=True):
        """M15's import settings; stage 2's packs keep each mesh in its node's frame (`bake`
        off: the actor stands at the node's pivot) and build Nanite only where asked."""
        gp = unreal.InterchangeGenericAssetsPipeline()
        gp.set_editor_property("asset_type_sub_folders", False)
        gp.set_editor_property("scene_name_sub_folder", False)
        gp.set_editor_property("use_source_name_for_asset", False)  # a one-node tile too
        mp = gp.get_editor_property("material_pipeline")
        mp.set_editor_property("import_materials", False)
        msh = gp.get_editor_property("mesh_pipeline")
        msh.set_editor_property("collision", False)
        msh.set_editor_property("fallback_collision_type", unreal.InterchangeMeshCollision.NONE)
        msh.set_editor_property("import_skeletal_meshes", False)
        msh.set_editor_property("build_nanite", nanite)
        if not bake:
            # (and the packs' own flat normals: recomputed, they would be smoothed across
            # the welded corners of every reveal and band)
            cmn = gp.get_editor_property("common_meshes_properties")
            cmn.set_editor_property("bake_meshes", False)
            cmn.set_editor_property("recompute_normals", False)
        # no mesh distance fields or Lumen cards: thousands of blockout meshes would take the
        # editor an hour to build them before its first frame (screen-space GI is enough)
        msh.set_editor_property("distance_field_resolution_scale", 0.0)
        msh.set_editor_property("max_lumen_mesh_cards", 0)
        stack = unreal.InterchangePipelineStackOverride()
        stack.add_pipeline(gp)
        return stack

    def import_glb(self, glb, folder, pipeline=None):
        task = unreal.AssetImportTask()
        task.filename = glb
        task.destination_path = folder
        task.automated = True
        task.replace_existing = True
        task.save = False
        task.options = pipeline or self.pipeline()
        AT.import_asset_tasks([task])
        return [str(p) for p in task.get_editor_property("imported_object_paths")]

    def finish_mesh(self, sm, h):
        """Per-category materials by slot and complex collision (set without the change
        notification, which would build the mesh again), the content hash."""
        slots = []
        for s in sm.get_editor_property("static_materials"):
            # (the array hands out copies: edit each and set the array again)
            mi = self.mats.get(str(s.material_slot_name))
            if mi is not None:
                s.set_editor_property("material_interface", mi)
            slots.append(s)
        sm.set_editor_property("static_materials", slots, NEVER)
        bs = sm.get_editor_property("body_setup")
        if bs is not None:
            bs.set_editor_property("collision_trace_flag",
                                   unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE, NEVER)
        EAL.set_metadata_tag(sm, HASH_TAG, h)
        EAL.save_loaded_asset(sm, only_if_is_dirty=False)

    def import_group(self, glb, folder, entries, pipeline=None, finish=None,
                     version=MESH_VERSION, stats=None):
        """entries: [(asset name, hash)] of one glb; imports the glb when any is missing or
        stale; {asset name: static mesh}. (Stage 2 passes its own pipeline, finish(sm,
        stored hash), mesh version and counters.)"""
        out, stale = {}, []
        finish = finish or self.finish_mesh
        stats = stats or self.stats
        entries = [(name, f"{version}.{h}") for name, h in entries]
        for name, h in entries:
            path = f"{folder}/{name}"
            sm = unreal.load_asset(path) if EAL.does_asset_exist(path) else None
            if sm is not None and meta(sm, HASH_TAG) == h:
                out[name] = sm
            else:
                stale.append((name, h))
        if not stale:
            stats["meshes"]["kept"] += len(entries)
            return out
        self.import_glb(glb, folder, pipeline)
        if stats is self.stats:
            self.stats["tiles_imported"] += 1
        else:
            stats["packs_imported"] += 1
        fresh = {n for n, _ in stale}
        for name, h in entries:
            path = f"{folder}/{name}"
            sm = unreal.load_asset(path)
            if sm is None:
                raise RuntimeError(f"{glb}: no static mesh {path} after the import")
            if name in fresh:
                finish(sm, h)
                stats["meshes"]["imported"] += 1
            else:
                # imported again with the tile (same content): keep the hash and settings
                finish(sm, h)
                stats["meshes"]["kept"] += 1
            out[name] = sm
        return out

    def meshes(self):
        self.tile_meshes = {}
        n = len(self.man["tiles"])
        for k, t in enumerate(self.man["tiles"]):
            if not t["glb"]:
                raise RuntimeError(f"tile {t['name']}: no glTF tile (run the blockout with "
                                   "its exports)")
            folder = f"{self.root}/Meshes/{t['name']}"
            entries = [(o["asset"], o["hash"]) for o in t["objects"]]
            self.tile_meshes[t["name"]] = self.import_group(
                os.path.join(self.build, t["glb"]), folder, entries)
            if k % 20 == 0:
                log(f"tile {k + 1}/{n} {t['name']}")
        kinds = self.man["prototypes"]["kinds"]
        self.protos = self.import_group(
            os.path.join(self.build, self.man["prototypes"]["glb"]), f"{self.root}/Props",
            [(v["asset"], v["hash"]) for v in kinds.values()])

    def prune_meshes(self):
        want = {f"{self.root}/Meshes/{t['name']}/{o['asset']}"
                for t in self.man["tiles"] for o in t["objects"]}
        want |= {f"{self.root}/Props/{v['asset']}"
                 for v in self.man["prototypes"]["kinds"].values()}
        for folder in (f"{self.root}/Meshes", f"{self.root}/Props"):
            if not EAL.does_directory_exist(folder):
                continue
            stale = [a for a in EAL.list_assets(folder, recursive=True)
                     if a.split(".")[0] not in want]
            self.stats["meshes"]["deleted"] += delete_assets(stale)
        # stage 2's meshes (its materials are pruned by materials2); all of them on a
        # blockout-only import
        folder = f"{self.root}/{STAGE2_FOLDER}"
        if not EAL.does_directory_exist(folder):
            return
        want = set()
        if self.s2:
            want = {f"{self.root}/{p['folder']}/{m['asset']}" for p in self.s2["packs"]
                    for m in p["meshes"]}
            want |= {f"{self.root}/{c['mesh']}" for c in self.s2["lod_chains"]}
        mats = f"{folder}/Materials/"
        stale = [a for a in EAL.list_assets(folder, recursive=True)
                 if a.split(".")[0] not in want and not a.startswith(mats)]
        n = delete_assets(stale)
        if self.s2:
            self.stats["stage2"]["meshes"]["deleted"] += n
        else:
            self.stats["meshes"]["deleted"] += n

    # -- stage 2 (assetgen's layer: buildings, streets) --

    def materials2(self):
        """A master per stage 2 master name and an instance per part and slot (its color,
        roughness, metallic, emissive strength and tint rule); stale instances deleted."""
        folder = f"{self.root}/{STAGE2_FOLDER}/Materials"
        want = set()
        if self.s2:
            masters = {m: stage2_master(m) for m in self.s2["masters"]}
            st = self.stats["stage2"]["materials"]
            for key, p in sorted(self.s2["materials"].items()):
                path = f"{folder}/{p['asset']}"
                want.add(path)
                h = sha16([p, STAGE2_VERSION])
                if EAL.does_asset_exist(path):
                    mi = unreal.load_asset(path)
                    if meta(mi, HASH_TAG) == h:
                        st["kept"] += 1
                        self.mats2[(p["part"], p["slot"])] = mi
                        continue
                    st["updated"] += 1
                else:
                    mi = AT.create_asset(p["asset"], folder, unreal.MaterialInstanceConstant,
                                         unreal.MaterialInstanceConstantFactoryNew())
                    st["created"] += 1
                MEL.set_material_instance_parent(mi, masters[p["master"]])
                r, g, b = p["color"]
                MEL.set_material_instance_vector_parameter_value(
                    mi, "BaseColor", unreal.LinearColor(r, g, b, 1.0))
                for name, v in (("Roughness", p["roughness"]), ("Metallic", p["metallic"]),
                                ("Emissive", p["emissive"]), ("TintChannel", p["tint_cpd"]),
                                ("TintScale", p["tint_scale"]),
                                ("TintTimesColor", 1.0 if p["tint_times_color"] else 0.0)):
                    MEL.set_material_instance_scalar_parameter_value(mi, name, float(v))
                EAL.set_metadata_tag(mi, HASH_TAG, h)
                EAL.save_loaded_asset(mi)
                self.mats2[(p["part"], p["slot"])] = mi
        if EAL.does_directory_exist(folder):
            stale = [a for a in EAL.list_assets(folder, recursive=False)
                     if a.split(".")[0] not in want]
            n = delete_assets(stale)
            if self.s2:
                self.stats["stage2"]["materials"]["deleted"] += n

    def mat2(self, part, slot):
        """The instance of a mesh's material slot (Interchange may have turned the slot
        name's dots into underscores)."""
        mi = self.mats2.get((part, slot))
        if mi is None:
            want = slot.replace(".", "_").lower()
            for (p, name), m in self.mats2.items():
                if p == part and name.replace(".", "_").lower() == want:
                    self.mats2[(part, slot)] = m
                    return m
        return mi

    def collision2(self, sm, col):
        """A building's simple collision, the mass pieces' boxes and convex prisms (building
        frame, meters) as exact hulls: GeometryScript makes one convex element per connected
        piece of a dynamic mesh of the prisms (`KConvexElem`'s vertices are not open to
        Python), boxes found as boxes; used as complex. Without GeometryScript, complex
        collision."""
        st = self.stats["stage2"]
        GS = getattr(unreal, "GeometryScript_Collision", None)
        bs = sm.get_editor_property("body_setup")
        if GS is None or bs is None:
            if bs is not None:
                bs.set_editor_property("collision_trace_flag",
                                       unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE,
                                       NEVER)
            st["complex_fallback"] += 1
            return
        dm = unreal.DynamicMesh()
        po = unreal.GeometryScriptPrimitiveOptions()
        base = unreal.GeometryScriptPrimitiveOriginMode.BASE
        prisms = []
        for b in col.get("boxes", []):
            (cx, cy, cz), (ex, ey, ez) = b["center"], b["extent"]
            a = math.radians(b.get("yaw_deg", 0.0))
            ux, uy = math.cos(a), math.sin(a)
            ring = [(cx + ux * x - uy * y, cy + uy * x + ux * y)
                    for x, y in ((-ex, -ey), (ex, -ey), (ex, ey), (-ex, ey))]
            prisms.append((ring, cz - ez, cz + ez))
        for c in col.get("convex", []):
            prisms.append(([tuple(p) for p in c["ring"]], c["z"][0], c["z"][1]))
        for ring, z0, z1 in prisms:
            if z1 - z0 <= 0.01 or len(ring) < 3:
                continue
            # (y flipped: the ring turns the other way round, as the extrusion wants it)
            pts = [unreal.Vector2D(x * 100.0, -y * 100.0) for x, y in ring]
            unreal.GeometryScript_Primitives.append_simple_extrude_polygon(
                dm, po, unreal.Transform(location=unreal.Vector(0.0, 0.0, z0 * 100.0)),
                pts, (z1 - z0) * 100.0, 0, True, base)
        o = unreal.GeometryScriptCollisionFromMeshOptions()
        for k, v in (("emit_transaction", False),
                     ("method", unreal.GeometryScriptCollisionGenerationMethod.CONVEX_HULLS),
                     ("auto_detect_spheres", False), ("auto_detect_capsules", False),
                     ("auto_detect_boxes", True), ("simplify_hulls", False),
                     ("remove_fully_contained_shapes", True), ("max_convex_hulls_per_mesh", 1)):
            o.set_editor_property(k, v)
        so = unreal.GeometryScriptSetStaticMeshCollisionOptions()
        GS.set_static_mesh_collision_from_mesh(dm, sm, o, so)
        bs = sm.get_editor_property("body_setup")
        bs.set_editor_property("collision_trace_flag",
                               unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX, NEVER)
        if col.get("convex"):
            st["hulls"] += 1
        else:
            st["boxes_only"] += 1

    def finish2(self, sm, rec, part, h):
        """A stage 2 mesh: its slots' instances, collision (hulls, complex, or none: the
        actor turns it off), Nanite off where the entry says (sky tube glass, proxies), the
        hash."""
        slots = []
        for s in sm.get_editor_property("static_materials"):
            mi = self.mat2(part, str(s.material_slot_name))
            if mi is not None:
                s.set_editor_property("material_interface", mi)
            slots.append(s)
        sm.set_editor_property("static_materials", slots, NEVER)
        col = rec["collision"]
        if "boxes" in col:
            self.collision2(sm, col)
        else:
            bs = sm.get_editor_property("body_setup")
            if bs is not None:
                bs.set_editor_property("collision_trace_flag",
                                       unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE,
                                       NEVER)
        ns = sm.get_editor_property("nanite_settings")
        if bool(ns.get_editor_property("enabled")) != bool(rec["nanite"]):
            ns.set_editor_property("enabled", bool(rec["nanite"]))
            sm.set_editor_property("nanite_settings", ns)     # (builds the mesh again)
        EAL.set_metadata_tag(sm, HASH_TAG, h)
        EAL.save_loaded_asset(sm, only_if_is_dirty=False)

    def meshes2(self):
        """Stage 2's glTF packs (shells, proxies, street pieces, parts), each mesh in its
        node's frame; then the LOD chains."""
        self.meshes_s2 = {}
        if not self.s2:
            return
        st = self.stats["stage2"]
        n = len(self.s2["packs"])
        for k, pk in enumerate(self.s2["packs"]):
            if not pk["glb"]:
                raise RuntimeError(f"{pk['folder']}: its glTF pack is missing (run assetgen "
                                   "build)")
            folder = f"{self.root}/{pk['folder']}"
            recs = {m["asset"]: m for m in pk["meshes"]}
            nanite = any(m["nanite"] for m in pk["meshes"])
            part = pk["part"]

            def finish(sm, h, recs=recs, part=part):
                self.finish2(sm, recs[sm.get_name()], part, h)

            got = self.import_group(
                os.path.join(self.build, pk["glb"]), folder,
                [(m["asset"], m["hash"]) for m in pk["meshes"]],
                pipeline=self.pipeline(nanite=nanite, bake=False), finish=finish,
                version=STAGE2_MESH_VERSION, stats=st)
            for a, sm in got.items():
                self.meshes_s2[f"{pk['folder']}/{a}"] = sm
            if k % 25 == 0:
                log(f"stage 2 pack {k + 1}/{n} {pk['folder']}")
        sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        for c in self.s2["lod_chains"]:
            path = f"{self.root}/{c['mesh']}"
            h = f"{STAGE2_MESH_VERSION}.{c['hash']}"
            sm = unreal.load_asset(path) if EAL.does_asset_exist(path) else None
            if sm is not None and meta(sm, HASH_TAG) == h:
                st["meshes"]["kept"] += 1
                self.meshes_s2[c["mesh"]] = sm
                continue
            if sm is not None:
                EAL.delete_asset(path)
            src = [self.meshes_s2[lo["mesh"]] for lo in c["lods"]]
            sm = EAL.duplicate_asset(src[0].get_path_name().split(".")[0], path)
            for i, lo in enumerate(src[1:], 1):
                sms.set_lod_from_static_mesh(sm, i, lo, 0, True)
            sm.set_editor_property("auto_compute_lod_screen_size", False)
            sms.set_lod_screen_sizes(sm, [float(lo["screen_size"]) for lo in c["lods"]])
            EAL.set_metadata_tag(sm, HASH_TAG, h)
            EAL.save_loaded_asset(sm, only_if_is_dirty=False)
            self.meshes_s2[c["mesh"]] = sm
            st["meshes"]["imported"] += 1
            st["lod_chains"] += 1

    # -- the level --

    def level(self):
        path = f"{self.root}/Maps/{self.man['folder']}"
        if EAL.does_asset_exist(path):
            self.les.load_level(path)
            self.load_all_actors()
        else:
            if not self.les.new_level(path, True):
                raise RuntimeError(f"could not create the World Partition level {path}")
        self.level_path = path

    def load_all_actors(self):
        """World Partition loads no actor of a level opened in a commandlet: load them all
        (an import compares every actor with the manifest)."""
        WPL = unreal.WorldPartitionBlueprintLibrary
        descs = WPL.get_actor_descs()
        guids = [d.guid for d in descs]
        if guids:
            WPL.load_actors(guids)
        log(f"loaded {len(guids)} actors of the level")

    def existing(self):
        out = {}
        city = f"cg.city={self.city}"
        for a in self.eas.get_all_level_actors():
            tags = [str(t) for t in a.tags]
            if city not in tags:
                continue
            key = next((t[7:] for t in tags if t.startswith("cg.key=")), None)
            if key is None or key in out:
                self.destroy(a, key or "")
                continue
            out[key] = a
        return out

    def destroy(self, a, key):
        """Destroy an actor of the city, its meshes let go first: World Partition holds a
        destroyed actor until the level is saved, and a mesh it still names cannot be deleted
        (`prune_meshes` deletes the meshes no object uses, all at once)."""
        for c in a.get_components_by_class(unreal.StaticMeshComponent):
            c.set_static_mesh(None)
        self.eas.destroy_actor(a)
        self.stats["actors"]["deleted"] += 1
        self.keys["deleted"].append(key)

    def tags(self, key, h, ids, typ, cat, tile, district, level=0):
        t = [f"cg.city={self.city}", f"cg.key={key}", f"{HASH_TAG}={h}", f"cg.type={typ}",
             f"cg.category={cat}", f"cg.tile={tile}", f"cg.district={district}"]
        if level:
            t.append(f"cg.level={level}")      # (M14: on a deck)
        t += [f"cg.id={i}" for i in ids]
        return [unreal.Name(x) for x in t]

    def place(self, have, key, h, cls, make, update, folder):
        """The actor of `key`: unchanged when its hash matches, else updated in place, else
        spawned; returns it."""
        h = f"{ACTOR_VERSION}.{h}"
        a = have.pop(key, None)
        if a is not None:
            if f"{HASH_TAG}={h}" in [str(t) for t in a.tags]:
                self.stats["actors"]["unchanged"] += 1
                return a
            if a.get_class() != cls:
                self.destroy(a, key)
                a = None
        if a is None:
            a = make()
            a.set_actor_label(key)
            a.set_folder_path(folder)
            self.stats["actors"]["created"] += 1
            self.keys["created"].append(key)
        else:
            # an actor whose mesh asset is the same object (its tile imported again in place)
            # and whose only change is its tags is not marked dirty by setting them: mark it,
            # or the level keeps the old hash and every import updates it again
            a.modify()
            self.stats["actors"]["updated"] += 1
            self.keys["updated"].append(key)
        update(a, h)
        return a

    def actors(self):
        have = self.existing()
        log(f"{len(have)} actors of {self.city} in the level")
        sma = unreal.StaticMeshActor.static_class()
        origin = unreal.Vector(0.0, 0.0, 0.0)
        for t in self.man["tiles"]:
            meshes = self.tile_meshes[t["name"]]
            for o in t["objects"]:
                if o["key"] in self.skip:
                    continue            # (stage 2 has its own actor in its place)
                sm = meshes[o["asset"]]

                def make():
                    return self.eas.spawn_actor_from_class(unreal.StaticMeshActor, origin)

                def update(a, h, o=o, sm=sm, t=t):
                    c = a.static_mesh_component
                    c.set_static_mesh(sm)
                    c.set_mobility(unreal.ComponentMobility.STATIC)
                    a.set_actor_location(origin, False, False)
                    a.tags = self.tags(o["key"], h, o["ids"], o["type"], o["category"],
                                       t["name"], o["district"], o.get("level", 0))

                self.place(have, o["key"], o["hash"], sma, make, update,
                           f"CityGen/{o['category']}")
        self.instances(have)
        self.actors2(have)
        self.player_start(have)
        self.lighting(have)
        for key, a in sorted(have.items()):
            self.destroy(a, key)

    def actors2(self, have):
        """Stage 2's actors: a static mesh actor per entry at its pivot (yaw -yaw), its
        Custom Primitive Data, no collision where its entry has none; an instanced actor per
        entry and part kind (HISM, the transforms relative to the pivot)."""
        if not self.s2:
            return
        sma = unreal.StaticMeshActor.static_class()
        stage = unreal.Name("cg.stage=2")
        for r in self.s2["actors"]:
            sm = self.meshes_s2[r["mesh"]]
            loc = ue_loc(*r["pivot"])
            rot = unreal.Rotator(roll=0.0, pitch=0.0, yaw=-r["yaw_deg"])

            def make(loc=loc):
                return self.eas.spawn_actor_from_class(unreal.StaticMeshActor, loc)

            def update(a, h, r=r, sm=sm, loc=loc, rot=rot):
                c = a.static_mesh_component
                c.set_static_mesh(sm)
                c.set_mobility(unreal.ComponentMobility.STATIC)
                a.set_actor_location_and_rotation(loc, rot, False, False)
                for i, v in enumerate(r["cpd"]):
                    c.set_custom_primitive_data_float(i, float(v))
                if r.get("no_collision"):
                    c.set_collision_profile_name("NoCollision")
                a.tags = self.tags(r["key"], h, r["ids"], r["type"], r["category"],
                                   r["tile"], r["district"], r.get("level", 0)) + [stage]

            self.place(have, r["key"], r["hash"], sma, make, update,
                       f"CityGen/{r['category']}")
        cls = blueprint(f"{CORE}/BP_CityGenInstances", unreal.Actor, INSTANCE_VARS, hism=True)
        for r in self.s2["instances"]:
            sm = self.meshes_s2[r["mesh"]]
            loc = ue_loc(*r["pivot"])
            rot = unreal.Rotator(roll=0.0, pitch=0.0, yaw=-r["yaw_deg"])

            def make(loc=loc):
                return self.eas.spawn_actor_from_class(cls, loc)

            def update(a, h, r=r, sm=sm, loc=loc, rot=rot):
                comp = a.get_components_by_class(
                    unreal.HierarchicalInstancedStaticMeshComponent)[0]
                comp.set_static_mesh(sm)
                a.root_component.set_mobility(unreal.ComponentMobility.STATIC)
                comp.set_mobility(unreal.ComponentMobility.STATIC)
                comp.clear_instances()
                comp.add_instances([unreal.Transform(
                    unreal.Vector(x * 100.0, -y * 100.0, z * 100.0),
                    unreal.Rotator(roll=0.0, pitch=0.0, yaw=-yaw), unreal.Vector(1, 1, 1))
                    for x, y, z, yaw in r["xforms"]], False, False)
                for i, v in enumerate(r["cpd"]):
                    comp.set_custom_primitive_data_float(i, float(v))
                a.set_actor_location_and_rotation(loc, rot, False, False)
                a.set_editor_property("Ids", [unreal.Name(r["entry"])])
                a.set_editor_property("Kind", unreal.Name(r["kind"]))
                a.tags = self.tags(r["key"], h, [r["entry"]], r["type"], r["category"],
                                   r["tile"], r["district"], r.get("level", 0)) + [stage]

            self.place(have, r["key"], r["hash"], cls, make, update,
                       f"CityGen/{r['category']}")

    def instances(self, have):
        cls = blueprint(f"{CORE}/BP_CityGenInstances", unreal.Actor, INSTANCE_VARS, hism=True)
        ts = self.man["tile_size_m"]
        tiles = {t["name"]: t for t in self.man["tiles"]}
        for inst in self.man["instances"]:
            b = tiles[inst["tile"]]["bounds"] if inst["tile"] in tiles else None
            cx, cy = (((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0) if b else
                      (inst["xforms"][0][0], inst["xforms"][0][1]))
            center = ue_loc(cx, cy, 0.0)

            def make(center=center):
                return self.eas.spawn_actor_from_class(cls, center)

            def update(a, h, inst=inst, cx=cx, cy=cy, center=center):
                comp = a.get_components_by_class(
                    unreal.HierarchicalInstancedStaticMeshComponent)[0]
                comp.set_static_mesh(self.protos[
                    self.man["prototypes"]["kinds"][inst["proto"]]["asset"]])
                a.root_component.set_mobility(unreal.ComponentMobility.STATIC)
                comp.set_mobility(unreal.ComponentMobility.STATIC)
                comp.clear_instances()
                xf = []
                for x, y, z, yaw, sx, sy, sz in inst["xforms"]:
                    xf.append(unreal.Transform(
                        unreal.Vector((x - cx) * 100.0, -(y - cy) * 100.0, z * 100.0),
                        unreal.Rotator(roll=0.0, pitch=0.0, yaw=-yaw),
                        unreal.Vector(sx, sy, sz)))
                comp.add_instances(xf, False, False)
                a.set_actor_location(center, False, False)
                a.set_editor_property("Ids", [unreal.Name(i) for i in inst["ids"]])
                a.set_editor_property("Kind", unreal.Name(inst["proto"]))
                a.tags = self.tags(inst["key"], h, [], inst["type"], inst["category"],
                                   inst["tile"], inst["district"])

            self.place(have, inst["key"], inst["hash"], cls, make, update,
                       f"CityGen/{inst['category']}")
        del ts

    def player_start(self, have):
        ps = self.man["player_start"]
        h = sha16(ps)
        x, y, z = ps["position"]

        def make():
            return self.eas.spawn_actor_from_class(unreal.PlayerStart, ue_loc(x, y, z))

        def update(a, hv):
            a.set_actor_location_and_rotation(
                ue_loc(x, y, z), unreal.Rotator(roll=0.0, pitch=0.0, yaw=-ps["yaw_deg"]),
                False, False)
            a.set_editor_property("is_spatially_loaded", False)
            a.tags = self.tags("player_start", hv, [], "player_start", "player_start", "", "")

        self.place(have, "player_start", h, unreal.PlayerStart.static_class(), make, update,
                   "CityGen")

    def lighting(self, have):
        """A sun, a sky light and the sky atmosphere, always loaded, so the
        blockout reads when played (stage 3, atmosgen, replaces them)."""
        specs = [("lighting.sun", unreal.DirectionalLight), ("lighting.sky", unreal.SkyLight),
                 ("lighting.atmosphere", unreal.SkyAtmosphere)]
        for key, cls in specs:
            h = sha16([key, "v1"])

            def make(cls=cls):
                return self.eas.spawn_actor_from_class(cls, unreal.Vector(0.0, 0.0, 0.0))

            def update(a, hv, key=key):
                a.set_editor_property("is_spatially_loaded", False)
                if key == "lighting.sun":
                    a.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=-38.0, yaw=-60.0),
                                         False)
                    lc = a.get_component_by_class(unreal.DirectionalLightComponent)
                    lc.set_editor_property("atmosphere_sun_light", True)
                    lc.set_mobility(unreal.ComponentMobility.MOVABLE)
                elif key == "lighting.sky":
                    lc = a.get_component_by_class(unreal.SkyLightComponent)
                    lc.set_editor_property("real_time_capture", True)
                    lc.set_mobility(unreal.ComponentMobility.MOVABLE)
                a.tags = self.tags(key, hv, [], "lighting", "lighting", "", "")

            self.place(have, key, h, cls.static_class(), make, update, "CityGen/Lighting")

    # -- graphs --

    def graphs(self):
        if not self.man["graphs"]:
            return
        cls = blueprint(f"{CORE}/BP_CityGenGraph", unreal.PrimaryDataAsset, GRAPH_VARS)
        path = os.path.join(self.build, "unreal", "graphs.json")
        data = json.load(open(path, encoding="utf-8"))
        folder = f"{self.root}/Data"
        for gname, summary in sorted(self.man["graphs"].items()):
            g = data[gname]
            name = f"DA_{self.man['folder']}_{gname.capitalize()}"
            apath = f"{folder}/{name}"
            if EAL.does_asset_exist(apath):
                da = unreal.load_asset(apath)
                if meta(da, HASH_TAG) == summary["hash"]:
                    self.stats["graphs"]["kept"] += 1
                    continue
            else:
                f = unreal.DataAssetFactory()
                f.set_editor_property("data_asset_class", cls)
                da = AT.create_asset(name, folder, cls, f)
            pts = g["points"]
            da.set_editor_property("City", self.man["city"])
            da.set_editor_property("Graph", unreal.Name(gname))
            da.set_editor_property("Hash", summary["hash"])
            da.set_editor_property("Ids", [unreal.Name(x) for x in g["ids"]])
            da.set_editor_property("Kinds", [unreal.Name(x) for x in g["kinds"]])
            da.set_editor_property("Refs", [unreal.Name(x or "") for x in g["refs"]])
            da.set_editor_property("Widths", [w * 100.0 for w in g["widths"]])
            da.set_editor_property("PointStart", g["point_start"])
            da.set_editor_property("Points", [ue_loc(pts[i], pts[i + 1], pts[i + 2])
                                              for i in range(0, len(pts), 3)])
            da.set_editor_property("LinkStart", g["link_start"])
            da.set_editor_property("Links", g["links"])
            da.set_editor_property("Attrs", g["attrs"])
            # (M14: each element's level, 0 the ground, 1 a deck; empty when all are on it)
            da.set_editor_property("Levels", g.get("levels", []))
            EAL.set_metadata_tag(da, HASH_TAG, summary["hash"])
            EAL.save_loaded_asset(da, only_if_is_dirty=False)
            self.stats["graphs"]["written"] += 1

    # -- digests (the same build imported twice gives the same) --

    def digests(self):
        rows = []
        for a in self.eas.get_all_level_actors():
            tags = sorted(str(t) for t in a.tags)
            if f"cg.city={self.city}" not in tags:
                continue
            tr = a.get_actor_transform()
            loc, rot = tr.translation, tr.rotation.rotator()
            mesh = ""
            if isinstance(a, unreal.StaticMeshActor):
                sm = a.static_mesh_component.static_mesh
                mesh = sm.get_path_name() if sm else ""
            rows.append([tags, mesh, [round(loc.x, 2), round(loc.y, 2), round(loc.z, 2),
                                      round(rot.yaw, 3)]])
        rows.sort()
        assets = []
        for folder in ("Meshes", "Props", "Materials", "Data", STAGE2_FOLDER):
            f = f"{self.root}/{folder}"
            if EAL.does_directory_exist(f):
                for a in sorted(EAL.list_assets(f, recursive=True)):
                    assets.append([a, meta(unreal.load_asset(a), HASH_TAG)])
        return {"actor_count": len(rows), "actor_digest": sha16(rows),
                "asset_count": len(assets), "asset_digest": sha16(assets)}

    def save(self):
        dirty = (len(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
                 + len(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()))
        self.stats["dirty_packages"] = self.stats.get("dirty_packages", 0) + dirty
        if dirty:
            self.les.save_current_level()
            unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)

    def run(self):
        base = self.timed("core", base_material)
        self.timed("materials", self.materials, base)
        self.timed("materials2", self.materials2)
        self.timed("meshes", self.meshes)
        self.timed("meshes2", self.meshes2)
        self.timed("level", self.level)
        self.timed("actors", self.actors)
        self.timed("graphs", self.graphs)
        # saved before the meshes no object uses are deleted: deleting an asset that the open
        # level still names reloads the level, which drops what was not saved
        self.timed("save", self.save)
        self.timed("prune", self.prune_meshes)
        self.timed("save_pruned", self.save)
        self.stats.update(self.timed("digests", self.digests))
        self.stats["keys"] = {k: sorted(v) for k, v in self.keys.items()}
        self.stats["level"] = self.level_path
        self.stats["content_root"] = self.root
        return self.stats


def main():
    res = {"ok": False}
    try:
        man = json.load(open(JOB["manifest"], encoding="utf-8"))
        if man.get("version") != 1:
            raise RuntimeError(f"manifest version {man.get('version')} is not 1")
        res.update(Importer(man, JOB["build_dir"]).run())
        res["ok"] = True
        res["city"] = man["city"]
        res["counts"] = man["counts"]
        res["engine"] = unreal.SystemLibrary.get_engine_version()
    except Exception:
        res["error"] = traceback.format_exc()
        unreal.log_error(res["error"])
    res["total_s"] = round(time.time() - T0, 1)
    with open(JOB["result"], "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print("CITYGEN_UE_DONE " + json.dumps({"ok": res["ok"], "total_s": res["total_s"]}))


main()
