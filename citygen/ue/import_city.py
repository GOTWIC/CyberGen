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
- Data/DA_<City>_Lanes, _Walkways, _Transit: BP_CityGenGraph data assets (flat arrays);
- the level's Play: its game mode override GM_CityGenFly (Core, spawning BP_CityGenFlyPawn,
  a SpectatorPawn with no collision at the job's speed) with `play` "fly", else none (the
  project's own game mode and pawn); its World Partition grid sized for flying (`view_m`
  around the player, the HLOD partitions out to the whole city).

With stage 2 in the manifest (assetgen's buildings and streets over the blockout), also:

- Assets/<Part>/<pack>, <Part>Proxies/<pack>, <Part>Parts/<pack>: the packs' static meshes
  (each in its node's frame; collision: a building's mass pieces as convex hulls through
  GeometryScript, complex for streets, none for the sky tube glass and proxies; Nanite on
  except those; the glass's LOD chain made from its LOD meshes), proxies imported only;
- Assets/Materials/MI_<part>_<slot>: instances of the stage 2 masters (Core/M_CgFacade,
  M_CgGlass, M_CgMetal, M_CgConcrete, M_CgRoad, M_CgNeon, M_CgSign, M_CgDecal, M_CgOpaque,
  M_CgEmissive, M_CgTranslucent, M_CgFoliage), the tint from the actor's Custom Primitive
  Data; from AG6 textured (Core/Textures: the shared library, imported once per project;
  Assets/Textures: the city's sign pages; both by pixel hash), with Core/MPC_CityGen's
  `Night` (0 by day, 1 by night) switching the windows, neon and signs;
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
FLY_PAWN = f"{CORE}/BP_CityGenFlyPawn"      # what Play puts you in with `--play fly`
FLY_MODE = f"{CORE}/GM_CityGenFly"
# stage 2 (assetgen, layer 2): the masters' version (Core/M_Cg<Master>, rebuilt in place when
# it changes), the meshes' and the actors' (stored hashes "<version>.<content hash>", as
# MESH_VERSION and ACTOR_VERSION)
STAGE2_VERSION = "5"                 # AG6: textured masters; AG8: leaves, textured holo
TEXTURE_VERSION = "1"
# a prune of more assets than this deletes their package files itself, on an empty level: the
# editor's delete makes a reachability pass over every loaded object per package (8435 meshes
# a pack rename left took it over 90 minutes with the city loaded, 1000 over 6 without)
PRUNE_FILES = 500
EMPTY_LEVEL = "/Engine/Maps/Entry"
STAGE2_MESH_VERSION = "2"
STAGE2_ACTOR_VERSION = "2"
TINT_CPD = (0, 8, 11, 14, 17, 20)    # citygen.unreal.TINT_CPD: the tints a master reads
LIT_CPD = 6                          # the lit-window ratio (AG1's cpd_layout)
# AG6's Custom Primitive Data (assetgen/materials/params.py): wear, dirt height, seed (AG0),
# room width, floor height, interior row, rain streaks, top, blinds
CPD = {"wear": 3, "dirt": 4, "neon": 5, "lit": 6, "seed": 7, "room": 23, "floor": 24,
       "row": 25, "streaks": 26, "top": 27, "blinds": 28}
SAMPLER = {"color": "SAMPLERTYPE_COLOR", "normal": "SAMPLERTYPE_NORMAL",
           "mask": "SAMPLERTYPE_MASKS"}
STAGE2_FOLDER = "Assets"             # citygen.unreal.STAGE2_FOLDER
# what Unreal turns into "_" in an asset name (INVALID_OBJECTNAME_CHARACTERS): the packs' glTF
# names have dots where the manifest's asset names have underscores
BAD_NAME_CHARS = "\"' ,/.:|&!~\n\r\t@#(){}[]=;^%$`"
# the stage 2 packs being imported: glb path -> {asset name: the manifest's mesh record}
PACK_PLAN = {}
PACK_STEPS = []          # what the pack step did per pack (counts, for the result)
TEXTURE_PLAN = {}        # texture file -> [(factory node setter, value)]
TEXTURE_STEPS = []       # the texture files the texture step found in TEXTURE_PLAN


def asset_name(name):
    return "".join("_" if ch in BAD_NAME_CHARS else ch for ch in name)


def pack_key(path):
    """A file as both the importer and Interchange name it: links resolved (AG6's library is
    a symlink on a Mac, a directory junction on Windows), case and separators as the OS
    compares them."""
    return os.path.normcase(os.path.realpath(path))


if hasattr(unreal, "InterchangePythonPipelineBase"):
    @unreal.uclass()
    class CgPackStep(unreal.InterchangePythonPipelineBase):
        """After the generic pipeline: a pack's meshes the manifest has no entry for (the
        family packs' variants this city does not place) are not made at all, and each mesh
        is built once with its own Nanite settings (on or off, shape preservation, the full
        fallback), not built and then built again by `finish2`."""

        @unreal.ufunction(override=True)
        def scripted_execute_pipeline(self, container, source_datas, content_base_path):
            plan = PACK_PLAN.get(pack_key(source_datas[0].get_filename())) \
                if source_datas else None
            if plan is None:
                return
            nodes = []
            for uid in container.get_nodes(unreal.InterchangeStaticMeshFactoryNode.static_class()):
                node = container.get_factory_node(uid)
                nodes.append((node, plan.get(asset_name(node.get_asset_name()))))
            found = sum(1 for _, m in nodes if m is not None)
            step = {"pack": source_datas[0].get_filename(), "nodes": len(nodes),
                    "matched": found, "skipped": 0}
            PACK_STEPS.append(step)
            REPORT.update(len(PACK_STEPS), len(PACK_PLAN), detail="packs imported, their "
                          "meshes building")
            if found != len(plan):
                # (a name this step cannot match: leave the pack as the generic pipeline
                # made it; finish2 sets the settings and prune_meshes deletes the extras)
                step["unmatched"] = True
                return
            for node, m in nodes:
                if m is None:
                    node.set_enabled(False)
                    step["skipped"] += 1
                    continue
                node.set_custom_build_nanite(bool(m["nanite"]))
                if m.get("shape_preservation"):
                    sp = getattr(unreal.NaniteShapePreservation,
                                 m["shape_preservation"].upper(), None)
                    if sp is not None:
                        node.set_custom_nanite_shape_preservation(int(sp.value))
                if m.get("fallback_full"):
                    node.set_custom_nanite_fallback_target(
                        int(unreal.NaniteFallbackTarget.PERCENT_TRIANGLES.value))
                    node.set_custom_nanite_fallback_percent_triangles(1.0)
                    node.set_custom_nanite_fallback_relative_error(0.0)

    @unreal.uclass()
    class CgTextureStep(unreal.InterchangePythonPipelineBase):
        """After the generic pipeline: a texture's color space, compression, texture group
        and green channel set before its first build (TEXTURE_PLAN), not set one by one
        after it (each set builds it again)."""

        @unreal.ufunction(override=True)
        def scripted_execute_pipeline(self, container, source_datas, content_base_path):
            want = TEXTURE_PLAN.get(pack_key(source_datas[0].get_filename())) \
                if source_datas else None
            if want is None:
                return
            TEXTURE_STEPS.append(source_datas[0].get_filename())
            for uid in container.get_nodes(unreal.InterchangeTextureFactoryNode.static_class()):
                node = container.get_factory_node(uid)
                for fn, v in want:
                    getattr(node, fn)(v)


def log(msg):
    unreal.log(f"citygen: {msg} ({time.time() - T0:.1f} s)")


# progress lines `citygen unreal` draws as a bar (citygen.progress.MARKER and its Relay ops)
PROGRESS = "CYBERGEN_PROGRESS"
# the importer's phases by the stage they show under
STAGE_OF = {"core": "materials", "materials": "materials", "textures2": "materials",
            "materials2": "materials", "meshes": "meshes", "meshes2": "meshes2",
            "level": "level", "actors": "actors", "play": "settings", "streaming": "settings",
            "graphs": "settings", "save": "save", "prune": "prune", "save_pruned": "prune",
            "digests": "digests"}


class Report:
    """Progress for `citygen unreal`: a line per stage start and end, its count when known,
    at most one update a second (the editor log keeps them too)."""

    def __init__(self):
        self.key = None
        self.last = 0.0

    def out(self, op, **fields):
        print(PROGRESS + " " + json.dumps({"op": op, **fields}, separators=(",", ":")),
              flush=True)

    def begin(self, key, total=None):
        if key == self.key:
            return
        self.key = key
        self.last = time.time()
        self.out("begin", label=key, total=total)

    def update(self, done, total=None, detail=None, force=False):
        now = time.time()
        if force or now - self.last >= 1.0:
            self.last = now
            f = {"done": done}
            if total is not None:
                f["total"] = total
            if detail:
                f["detail"] = detail
            self.out("update", **f)

    def note(self, text):
        self.out("note", text=text)

    def end(self):
        if self.key is not None:
            self.out("end")
        self.key = None


REPORT = Report()


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


def fly_classes(speed_m_s):
    """The fly pawn, a SpectatorPawn (its built-in bindings: WASD, E or Space up, Q or C down,
    the mouse to look) at `speed_m_s` with no collision, and the game mode that spawns it;
    made once, the speed set again when it changes. The game mode's class, and whether
    either Blueprint was saved."""
    pawn_cls = blueprint(FLY_PAWN, unreal.SpectatorPawn, [])
    mode_cls = blueprint(FLY_MODE, unreal.GameModeBase, [])
    pawn = unreal.get_default_object(pawn_cls)
    mc = pawn.get_editor_property("movement_component")
    cc = pawn.get_editor_property("collision_component")
    speed = float(speed_m_s) * 100.0
    saved = False
    if mc.get_editor_property("max_speed") != speed or \
            str(cc.get_collision_profile_name()) != "NoCollision":
        mc.set_editor_property("max_speed", speed)
        mc.set_editor_property("acceleration", speed * 4.0)     # full speed in 1/4 s
        mc.set_editor_property("deceleration", speed * 8.0)
        cc.set_collision_profile_name("NoCollision")
        EAL.save_loaded_asset(unreal.load_asset(FLY_PAWN), only_if_is_dirty=False)
        saved = True
    mode = unreal.get_default_object(mode_cls)
    have = mode.get_editor_property("default_pawn_class")
    if have is None or have.get_path_name() != pawn_cls.get_path_name():
        mode.set_editor_property("default_pawn_class", pawn_cls)
        EAL.save_loaded_asset(unreal.load_asset(FLY_MODE), only_if_is_dirty=False)
        saved = True
    return mode_cls, saved


def usage_flags(m):
    """The usage flags a master needs: instanced static meshes (the props' and parts'
    instances, and the instanced HLODs of the far view) and, opaque or masked on a surface,
    Nanite (the blockout tiles and stage 2's packs). Without them a game draws the default
    material, flat gray; so does play in the editor when nothing drew them in the editor
    before (the editor sets them in memory only, and recompiles on every launch)."""
    flags = ["used_with_instanced_static_meshes"]
    if m.get_editor_property("material_domain") == unreal.MaterialDomain.MD_SURFACE and \
            m.get_editor_property("blend_mode") in (unreal.BlendMode.BLEND_OPAQUE,
                                                     unreal.BlendMode.BLEND_MASKED):
        flags.append("used_with_nanite")
    return flags


def instanced(m):
    """A master with its usage flags (`usage_flags`), saved only when one was missing."""
    missing = [f for f in usage_flags(m) if not m.get_editor_property(f)]
    for f in missing:
        m.set_editor_property(f, True)
    if missing:
        MEL.recompile_material(m)
        EAL.save_loaded_asset(m, only_if_is_dirty=False)
    return m


def base_material():
    path = f"{CORE}/M_CityGen"
    if EAL.does_asset_exist(path):
        return instanced(unreal.load_asset(path))
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
    for f in usage_flags(m):
        m.set_editor_property(f, True)
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

# AG6: a textured surface's color: the set's base color with the tint over its tinted pixels
# (mask = ORM alpha: tint / ref there), occlusion, the macro map, grime from the ground up
# to the dirt height, rain streaks (the decal atlas's leaks) under the building's top
SURFACE_CODE = """
float3 c = Base.rgb;
if (Textured > 0.5) {
  c = lerp(c, c * Tint / max(Ref, 0.02), Orm.a);
  c *= 0.35 + 0.65 * Orm.r;
} else {
  c = Tint;
}
c *= 0.86 + 0.28 * Macro.r;
float g = saturate(1.0 - Z / max(Dirt, 0.1));
g = g * g * (0.25 + 0.6 * Wear) * (0.5 + Macro.b);
c = lerp(c, float3(0.045, 0.04, 0.032), g * 0.75);
float d = (Top - Z) / 6.0;
float s = (d > 0.0 && d < 1.0) ? Leak.a * Streaks * Streak * (1.0 - abs(NZ)) : 0.0;
c = lerp(c, float3(0.03, 0.03, 0.028), s * 0.6);
if (Stains > 0.5) { c = lerp(c, Stain.rgb, Stain.a * Gate.z); }
return c;
"""
UV_CODE = "return UV / max(TileM, 0.01) + float2(Seed * 37.3, Seed * 71.9);"
MACRO_UV_CODE = "return float2(WP.x, -WP.y) / 6400.0;"
STREAK_UV_CODE = """
float d = clamp((Top - Z) / 6.0, 0.002, 0.998);
return float2((2.0 + frac(UV.x + Seed * 13.0)) / 4.0, d / 4.0);
"""
ROUGH_CODE = """
float r = Textured > 0.5 ? Orm.g + (Macro.g - 0.5) * 0.12 : Rough;
if (Stains > 0.5) { r -= 0.3 * Stain.a * Gate.z; }
return clamp(r, 0.02, 1.0);
"""
METAL_CODE = "return Textured > 0.5 ? Orm.b : Metal;"
# a road's stains: per 8 m cell of UV0 one road-atlas cell (oil, cracks, patches, tar, skid
# marks, a puddle, dust), placed and picked by a hash of the cell
STAIN_UV_CODE = """
float2 c = floor(UV / 8.0);
float h1 = frac(sin(dot(c, float2(12.9898, 78.233))) * 43758.5453);
float h2 = frac(sin(dot(c, float2(39.3468, 11.135))) * 24634.6345);
float h3 = frac(sin(dot(c, float2(73.156, 52.235))) * 15731.743);
float cells[10] = {0, 1, 2, 3, 4, 5, 6, 7, 13, 15};
float cell = cells[min(9, (int)floor(h2 * 10.0))];
float2 l = (UV - c * 8.0) / 2.0 - float2(h3, h1) * 2.0;
float ins = (l.x > 0.0 && l.x < 1.0 && l.y > 0.0 && l.y < 1.0) ? 1.0 : 0.0;
float2 auv = (float2(fmod(cell, 4.0), floor(cell / 4.0)) + clamp(l, 0.003, 0.997)) / 4.0;
return float3(auv, (h1 < 0.55 ? 1.0 : 0.0) * ins);
"""
# AG6: the room behind a window. The building's room grid on UV0 (meters: u along the
# facade, v up from the base): rooms RoomW wide and FloorH high; the view in the facade's
# tangent frame (x along u, y up, z out of the wall); the ray into the room's box, its hit
# projected onto the interior atlas's one-point image (back wall at Back of the window); a
# room per cell by hash, its use's atlas row. Nothing per pane or per vertex: panes that
# share corners show their rooms whole (AG1's per-pane UV1 and window ids came out per
# triangle in Unreal). Out: atlas u, v, lit, blind.
ROOM_CODE = """
float W = max(RoomW, 1.0);
float H = max(FloorH, 2.0);
float D = max(W * 1.1, 3.0);
float2 f = float2(UV.x / W, UV.y / H);
float2 cell = floor(f);
float2 p = frac(f);
float3 v = normalize(V);
float3 r = float3(-v.x / W, -v.y / H, max(v.z, 0.03) / D);
float tx = ((r.x > 0.0 ? 1.0 : 0.0) - p.x) / (abs(r.x) > 1e-5 ? r.x : 1e-5);
float ty = ((r.y > 0.0 ? 1.0 : 0.0) - p.y) / (abs(r.y) > 1e-5 ? r.y : 1e-5);
float t = min(min(tx, ty), 1.0 / r.z);
float3 h = saturate(float3(p, 0.0) + t * r);
float k = Back / (Back + (1.0 - Back) * h.z);
float2 i = clamp(0.5 + (h.xy - 0.5) * k, 0.004, 0.996);
float2 c = cell + Seed * 1000.0 + dot(round(N.xy * 8.0), float2(17.0, 1.0));
float h1 = frac(sin(dot(c, float2(12.9898, 78.233))) * 43758.5453);
float h2 = frac(sin(dot(c, float2(39.3468, 11.135))) * 24634.6345);
float h3 = frac(sin(dot(c, float2(73.156, 52.235))) * 15731.743);
float row = RowOverride >= 0.0 ? RowOverride : Row;
float col = floor(h1 * (Cols - 0.001));
float2 auv = float2((col + i.x) / Cols, (row + 1.0 - i.y) / Rows);
float lit = h2 < Lit ? 0.35 + 0.65 * frac(h1 * 7.31) : 0.0;
return float4(auv, lit, (h3 < Blinds && p.y > 1.0 - h2 * 0.9) ? 1.0 : 0.0);
"""
GLASS_CODE = """
float slat = 0.75 + 0.25 * frac(UV.y * 25.0);
float3 bd = float3(0.55, 0.53, 0.5) * slat;
float3 day = lerp(Day.rgb, bd, Room.w) * 0.2;
float3 nite = lerp(Nite.rgb * Room.z, float3(1.0, 0.85, 0.65) * 0.45 * Room.z, Room.w)
            + Nite.rgb * 0.02;
return Interior * lerp(day, nite * 1.2, Night);
"""
DECAL_UV_CODE = "return (frac(UV) + float2(fmod(Cell, Cols), floor(Cell / Cols))) / float2(Cols, Rows);"


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


def mpc():
    """/Game/CityGen/Core/MPC_CityGen: `Night` (0 by day, 1 by night), which stage 3 drives;
    the windows' rooms light, neon and signs glow with it."""
    path = f"{CORE}/MPC_CityGen"
    if EAL.does_asset_exist(path):
        return unreal.load_asset(path)
    c = AT.create_asset("MPC_CityGen", CORE, unreal.MaterialParameterCollection,
                        unreal.MaterialParameterCollectionFactoryNew())
    p = unreal.CollectionScalarParameter()
    p.set_editor_property("parameter_name", "Night")
    p.set_editor_property("default_value", 0.0)
    c.set_editor_property("scalar_parameters", [p])
    EAL.save_loaded_asset(c)
    return c


def night(m, x, y):
    return expr(m, unreal.MaterialExpressionCollectionParameter, x, y, collection=mpc(),
                parameter_name="Night")


def sparam(m, name, x, y, default=0.0, cpd=None):
    """A scalar parameter, read from the actor's Custom Primitive Data at `cpd` if given."""
    if cpd is None:
        return expr(m, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name,
                    default_value=float(default))
    return expr(m, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name,
                default_value=float(default), use_custom_primitive_data=True,
                primitive_data_index=cpd)


def tparam(m, name, kind, x, y, uv, defaults):
    """A texture sample parameter of `kind` (color, normal, mask) at the uv expression."""
    t = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, x, y, parameter_name=name,
             sampler_type=getattr(unreal.MaterialSamplerType, SAMPLER[kind]))
    if defaults.get(kind) is not None:
        t.set_editor_property("texture", defaults[kind])
    link(uv, "", t, "UVs")
    return t


def vparam(m, name, x, y, default=(1.0, 1.0, 1.0)):
    return expr(m, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name,
                default_value=unreal.LinearColor(default[0], default[1], default[2], 1.0))


F1, F2, F3, F4 = ("CMOT_FLOAT1", "CMOT_FLOAT2", "CMOT_FLOAT3", "CMOT_FLOAT4")


def cmot(name):
    return getattr(unreal.CustomMaterialOutputType, name)


def textured_surface(m, master, defaults):
    """The textured opaque masters (facade, metal, concrete, foliage, road): base color,
    roughness, metallic and normal from the set, tint, macro map, grime, streaks, stains."""
    MP = unreal.MaterialProperty
    col = tint_color(m, -1400, -200)
    uv0 = expr(m, unreal.MaterialExpressionTextureCoordinate, -2400, 200, coordinate_index=0)
    tile = sparam(m, "TileM", -2400, 300, 2.0)
    seed = sparam(m, "Seed", -2400, 380, 0.0, CPD["seed"])
    uvc = custom(m, -2100, 260, UV_CODE, ["UV", "TileM", "Seed"], cmot(F2), "CgUV")
    link(uv0, "", uvc, "UV")
    link(tile, "", uvc, "TileM")
    link(seed, "", uvc, "Seed")
    base = tparam(m, "BaseTex", "color", -1800, 100, uvc, defaults)
    nrm = tparam(m, "NormalTex", "normal", -1800, 400, uvc, defaults)
    orm = tparam(m, "OrmTex", "mask", -1800, 700, uvc, defaults)
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -2400, 1000)
    muv = custom(m, -2100, 1000, MACRO_UV_CODE, ["WP"], cmot(F2), "CgMacroUV")
    link(wp, "", muv, "WP")
    mac = tparam(m, "Macro", "mask", -1800, 1000, muv, defaults)
    lp = expr(m, unreal.MaterialExpressionLocalPosition, -2400, 1300)
    z = expr(m, unreal.MaterialExpressionComponentMask, -2200, 1300, r=False, g=False, b=True,
             a=False)
    link(lp, "", z, "Input")
    zm = expr(m, unreal.MaterialExpressionMultiply, -2050, 1300, const_b=0.01)
    link(z, "", zm, "A")
    top = sparam(m, "Top", -2400, 1450, 1000.0, CPD["top"])
    suv = custom(m, -2100, 1450, STREAK_UV_CODE, ["UV", "Z", "Top", "Seed"], cmot(F2),
                 "CgStreakUV")
    for a, b in ((uv0, "UV"), (zm, "Z"), (top, "Top"), (seed, "Seed")):
        link(a, "", suv, b)
    leak = tparam(m, "Decals", "color", -1800, 1450, suv, defaults)
    stains = sparam(m, "Stains", -2400, 1750, 0.0)
    if master == "road":
        guv = custom(m, -2100, 1750, STAIN_UV_CODE, ["UV"], cmot(F3), "CgStainUV")
        link(uv0, "", guv, "UV")
        gmask = expr(m, unreal.MaterialExpressionComponentMask, -1950, 1750, r=True, g=True,
                     b=False, a=False)
        link(guv, "", gmask, "Input")
        stain = tparam(m, "RoadAtlas", "color", -1800, 1750, gmask, defaults)
    else:
        guv = expr(m, unreal.MaterialExpressionConstant3Vector, -2100, 1750,
                   constant=unreal.LinearColor(0, 0, 0, 0))
        stain = expr(m, unreal.MaterialExpressionConstant4Vector, -1800, 1750,
                     constant=unreal.LinearColor(0, 0, 0, 0))
    nz = expr(m, unreal.MaterialExpressionVertexNormalWS, -2400, 2000)
    nzm = expr(m, unreal.MaterialExpressionComponentMask, -2200, 2000, r=False, g=False,
               b=True, a=False)
    link(nz, "", nzm, "Input")
    params = {"Textured": sparam(m, "Textured", -1500, 2100, 0.0),
              "Ref": vparam(m, "RefColor", -1500, 2200, (0.2, 0.2, 0.2)),
              "Dirt": sparam(m, "Dirt", -1500, 2300, 0.8, CPD["dirt"]),
              "Wear": sparam(m, "Wear", -1500, 2380, 0.5, CPD["wear"]),
              "Streaks": sparam(m, "Streaks", -1500, 2460, 0.0, CPD["streaks"]),
              "Streak": sparam(m, "StreakScale", -1500, 2540, 0.0)}
    sur = custom(m, -1000, 0, SURFACE_CODE,
                 ["Base", "Orm", "Tint", "Ref", "Macro", "Leak", "Z", "Dirt", "Wear",
                  "Streaks", "Streak", "Top", "NZ", "Textured", "Stains", "Stain", "Gate"],
                 cmot(F3), "CgSurface")
    for a, out, b in ((base, "RGBA", "Base"), (orm, "RGBA", "Orm"), (col, "", "Tint"),
                      (mac, "RGBA", "Macro"), (leak, "RGBA", "Leak"), (zm, "", "Z"),
                      (top, "", "Top"), (nzm, "", "NZ"), (stains, "", "Stains"),
                      (stain, "RGBA" if master == "road" else "", "Stain"), (guv, "", "Gate")):
        link(a, out, sur, b)
    for name, node in params.items():
        link(node, "", sur, name)
    rough = sparam(m, "Roughness", -1500, 2650, 0.85)
    metal = sparam(m, "Metallic", -1500, 2730, 0.0)
    rc = custom(m, -1000, 400, ROUGH_CODE, ["Orm", "Macro", "Textured", "Rough", "Stains",
                                            "Stain", "Gate"], cmot(F1), "CgRough")
    for a, out, b in ((orm, "RGBA", "Orm"), (mac, "RGBA", "Macro"),
                      (params["Textured"], "", "Textured"), (rough, "", "Rough"),
                      (stains, "", "Stains"),
                      (stain, "RGBA" if master == "road" else "", "Stain"), (guv, "", "Gate")):
        link(a, out, rc, b)
    mc = custom(m, -1000, 550, METAL_CODE, ["Orm", "Textured", "Metal"], cmot(F1), "CgMetal")
    for a, out, b in ((orm, "RGBA", "Orm"), (params["Textured"], "", "Textured"),
                      (metal, "", "Metal")):
        link(a, out, mc, b)
    flat = expr(m, unreal.MaterialExpressionConstant3Vector, -1300, 700,
                constant=unreal.LinearColor(0, 0, 1, 0))
    nl = expr(m, unreal.MaterialExpressionLinearInterpolate, -1000, 700)
    link(flat, "", nl, "A")
    link(nrm, "RGB", nl, "B")
    link(params["Textured"], "", nl, "Alpha")
    MEL.connect_material_property(sur, "", MP.MP_BASE_COLOR)
    MEL.connect_material_property(rc, "", MP.MP_ROUGHNESS)
    MEL.connect_material_property(mc, "", MP.MP_METALLIC)
    MEL.connect_material_property(nl, "", MP.MP_NORMAL)
    m.set_editor_property("two_sided", master == "foliage")


LEAF_CODE = """
float3 c = Base.rgb;
c = lerp(c, c * Tint / max(Ref, 0.02), Orm.a);
return c * (0.35 + 0.65 * Orm.r);
"""
HOLO_CODE = "return Tint * Strength * lerp(float3(1, 1, 1), Tex.rgb * 2.0, Textured);"
HOLO_OPACITY_CODE = """
float l = max(Tex.r, max(Tex.g, Tex.b));
return Opacity * lerp(1.0, 0.25 + 0.75 * l, Textured);
"""


def leaves_master(m, defaults):
    """AG8's leaf cards: a leaf clump tile on UV0 / TileM, the tint over its leaves, cut
    where the tile has no leaf (the tint mask, ORM alpha), two-sided."""
    MP = unreal.MaterialProperty
    col = tint_color(m, -1400, -200)
    uv0 = expr(m, unreal.MaterialExpressionTextureCoordinate, -2100, 200, coordinate_index=0)
    tile = sparam(m, "TileM", -2100, 300, 1.0)
    uvd = expr(m, unreal.MaterialExpressionDivide, -1950, 250)
    link(uv0, "", uvd, "A")
    link(tile, "", uvd, "B")
    base = tparam(m, "BaseTex", "color", -1800, 100, uvd, defaults)
    nrm = tparam(m, "NormalTex", "normal", -1800, 400, uvd, defaults)
    orm = tparam(m, "OrmTex", "mask", -1800, 700, uvd, defaults)
    ref = vparam(m, "RefColor", -1500, 900, (0.2, 0.2, 0.2))
    c = custom(m, -1000, 0, LEAF_CODE, ["Base", "Orm", "Tint", "Ref"], cmot(F3), "CgLeaf")
    for a, out, b in ((base, "RGBA", "Base"), (orm, "RGBA", "Orm"), (col, "", "Tint"),
                      (ref, "", "Ref")):
        link(a, out, c, b)
    MEL.connect_material_property(c, "", MP.MP_BASE_COLOR)
    MEL.connect_material_property(orm, "G", MP.MP_ROUGHNESS)
    MEL.connect_material_property(nrm, "RGB", MP.MP_NORMAL)
    MEL.connect_material_property(orm, "A", MP.MP_OPACITY_MASK)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    m.set_editor_property("opacity_mask_clip_value", 0.5)      # as the Blender preview cuts
    m.set_editor_property("two_sided", True)


def glass_master(m, defaults):
    """Opaque reflective glass with interior mapping (ROOM_CODE, GLASS_CODE)."""
    MP = unreal.MaterialProperty
    col = tint_color(m, -1400, -300)
    uv0 = expr(m, unreal.MaterialExpressionTextureCoordinate, -2400, 300, coordinate_index=0)
    cam = expr(m, unreal.MaterialExpressionCameraVectorWS, -2600, 450)
    tv = expr(m, unreal.MaterialExpressionTransform, -2400, 450,
              transform_source_type=unreal.MaterialVectorCoordTransformSource
              .TRANSFORMSOURCE_WORLD,
              transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_TANGENT)
    link(cam, "", tv, "Input")
    nrm = expr(m, unreal.MaterialExpressionVertexNormalWS, -2400, 550)
    ins = {"UV": uv0, "V": tv, "N": nrm,
           "RoomW": sparam(m, "RoomW", -2400, 650, 3.0, CPD["room"]),
           "FloorH": sparam(m, "FloorH", -2400, 730, 3.5, CPD["floor"]),
           "Row": sparam(m, "Row", -2400, 810, 0.0, CPD["row"]),
           "RowOverride": sparam(m, "RowOverride", -2400, 890, -1.0),
           "Seed": sparam(m, "Seed", -2400, 970, 0.0, CPD["seed"]),
           "Lit": sparam(m, "LitRatio", -2400, 1050, 0.3, CPD["lit"]),
           "Blinds": sparam(m, "Blinds", -2400, 1130, 0.3, CPD["blinds"]),
           "Back": sparam(m, "InteriorBack", -2400, 1210, 0.5),
           "Cols": sparam(m, "InteriorCols", -2400, 1290, 8.0),
           "Rows": sparam(m, "InteriorRows", -2400, 1370, 6.0)}
    room = custom(m, -2000, 600, ROOM_CODE, list(ins), cmot(F4), "CgRoom")
    for name, node in ins.items():
        link(node, "", room, name)
    ruv = expr(m, unreal.MaterialExpressionComponentMask, -1800, 600, r=True, g=True,
               b=False, a=False)
    link(room, "", ruv, "Input")
    day = tparam(m, "InteriorDay", "color", -1600, 450, ruv, defaults)
    nite = tparam(m, "InteriorNight", "color", -1600, 750, ruv, defaults)
    inter = sparam(m, "Interior", -1600, 1000, 0.0)
    nt = night(m, -1600, 1100)
    g = custom(m, -1200, 700, GLASS_CODE, ["Day", "Nite", "Room", "Night", "UV", "Interior"],
               cmot(F3), "CgGlass")
    for a, out, b in ((day, "RGBA", "Day"), (nite, "RGBA", "Nite"), (room, "", "Room"),
                      (nt, "", "Night"), (uv0, "", "UV"), (inter, "", "Interior")):
        link(a, out, g, b)
    g2 = expr(m, unreal.MaterialExpressionMultiply, -900, -300, const_b=2.0)
    link(col, "", g2, "A")
    rough = sparam(m, "Roughness", -900, 200, 0.06)
    metal = sparam(m, "Metallic", -900, 280, 0.15)
    spec = expr(m, unreal.MaterialExpressionConstant, -900, 360, r=0.8)
    MEL.connect_material_property(g2, "", MP.MP_BASE_COLOR)
    MEL.connect_material_property(g, "", MP.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(rough, "", MP.MP_ROUGHNESS)
    MEL.connect_material_property(metal, "", MP.MP_METALLIC)
    MEL.connect_material_property(spec, "", MP.MP_SPECULAR)


def stage2_master(master, defaults=None):
    """/Game/CityGen/Core/M_Cg<Master>. AG6's textured masters: `facade`, `metal`,
    `concrete`, `foliage`, `road` (textured_surface), `glass` (interior mapping), `neon`
    (emissive with Night), `sign` (an atlas page, emissive with Night, masked), `decal`
    (deferred, a cell of the decal atlas), `leaves` (AG8's leaf cards: masked by the leaf
    cover, two-sided); AG1's and AG7's `translucent` (blended, two-sided; `holo` the same
    with an emissive strength and AG6's holo ad page, AG8's holo-ads), `opaque` and
    `emissive` (flat, an emissive strength). Each takes its color
    from tint_color. Made, or rebuilt in place when of an older STAGE2_VERSION (its
    instances keep it as their parent)."""
    defaults = defaults or {}
    name = "M_Cg" + "".join(w.capitalize() for w in master.split("_"))
    path = f"{CORE}/{name}"
    m = unreal.load_asset(path) if EAL.does_asset_exist(path) else None
    if m is not None and meta(m, "cg.core2") == STAGE2_VERSION:
        return instanced(m)
    if m is None:
        m = AT.create_asset(name, CORE, unreal.Material, unreal.MaterialFactoryNew())
    else:
        MEL.delete_all_material_expressions(m)
    MP = unreal.MaterialProperty
    if master in ("facade", "metal", "concrete", "foliage", "road"):
        textured_surface(m, master, defaults)
    elif master == "glass":
        glass_master(m, defaults)
    elif master == "leaves":
        leaves_master(m, defaults)
    elif master == "sign":
        uv0 = expr(m, unreal.MaterialExpressionTextureCoordinate, -900, 0, coordinate_index=0)
        tex = tparam(m, "SignTex", "color", -700, 0, uv0, defaults)
        st = sparam(m, "SignStrength", -700, 300, 4.0)
        masked = sparam(m, "Masked", -700, 380, 0.0)
        nt = night(m, -700, 460)
        e = custom(m, -400, 200, "return Tex.rgb * Strength * (0.25 + 0.75 * Night);",
                   ["Tex", "Strength", "Night"], cmot(F3), "CgSign")
        for a, out, b in ((tex, "RGBA", "Tex"), (st, "", "Strength"), (nt, "", "Night")):
            link(a, out, e, b)
        op = custom(m, -400, 400, "return lerp(1.0, Tex.a, Masked);", ["Tex", "Masked"],
                    cmot(F1), "CgSignMask")
        link(tex, "RGBA", op, "Tex")
        link(masked, "", op, "Masked")
        b = expr(m, unreal.MaterialExpressionMultiply, -400, 0, const_b=0.15)
        link(tex, "RGB", b, "A")
        MEL.connect_material_property(b, "", MP.MP_BASE_COLOR)
        MEL.connect_material_property(e, "", MP.MP_EMISSIVE_COLOR)
        MEL.connect_material_property(op, "", MP.MP_OPACITY_MASK)
        MEL.connect_material_property(expr(m, unreal.MaterialExpressionConstant, -400, 600,
                                           r=0.35), "", MP.MP_ROUGHNESS)
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    elif master == "decal":
        uv0 = expr(m, unreal.MaterialExpressionTextureCoordinate, -1200, 0, coordinate_index=0)
        ins = {"UV": uv0, "Cell": sparam(m, "Cell", -1200, 100, 0.0),
               "Cols": sparam(m, "Cols", -1200, 180, 4.0),
               "Rows": sparam(m, "Rows", -1200, 260, 4.0)}
        duv = custom(m, -1000, 100, DECAL_UV_CODE, list(ins), cmot(F2), "CgDecalUV")
        for k2, node in ins.items():
            link(node, "", duv, k2)
        base = tparam(m, "BaseTex", "color", -700, 0, duv, defaults)
        nrm = tparam(m, "NormalTex", "normal", -700, 300, duv, defaults)
        orm = tparam(m, "OrmTex", "mask", -700, 600, duv, defaults)
        MEL.connect_material_property(base, "RGB", MP.MP_BASE_COLOR)
        MEL.connect_material_property(base, "A", MP.MP_OPACITY)
        MEL.connect_material_property(nrm, "RGB", MP.MP_NORMAL)
        MEL.connect_material_property(orm, "G", MP.MP_ROUGHNESS)
        m.set_editor_property("material_domain", unreal.MaterialDomain.MD_DEFERRED_DECAL)
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    elif master in ("translucent", "holo"):
        col = tint_color(m, -600, 0)
        op = expr(m, unreal.MaterialExpressionScalarParameter, -300, 460,
                  parameter_name="Opacity", default_value=0.35 if master == "translucent"
                  else 0.45)
        MEL.connect_material_property(col, "", MP.MP_BASE_COLOR)
        if master == "holo":
            # (AG8's holo-ads: they glow, showing AG6's holo ad page where Textured)
            uv0 = expr(m, unreal.MaterialExpressionTextureCoordinate, -900, 300,
                       coordinate_index=0)
            tex = tparam(m, "SignTex", "color", -700, 300, uv0, defaults)
            txd = sparam(m, "Textured", -700, 620, 0.0)
            emi = expr(m, unreal.MaterialExpressionScalarParameter, -300, 540,
                       parameter_name="Emissive", default_value=0.0)
            em = custom(m, -150, 500, HOLO_CODE, ["Tint", "Strength", "Tex", "Textured"],
                        cmot(F3), "CgHolo")
            for a, out, b in ((col, "", "Tint"), (emi, "", "Strength"), (tex, "RGBA", "Tex"),
                              (txd, "", "Textured")):
                link(a, out, em, b)
            MEL.connect_material_property(em, "", MP.MP_EMISSIVE_COLOR)
            oc = custom(m, -150, 640, HOLO_OPACITY_CODE, ["Opacity", "Tex", "Textured"],
                        cmot(F1), "CgHoloOpacity")
            for a, out, b in ((op, "", "Opacity"), (tex, "RGBA", "Tex"), (txd, "", "Textured")):
                link(a, out, oc, b)
            MEL.connect_material_property(oc, "", MP.MP_OPACITY)
        else:
            MEL.connect_material_property(op, "", MP.MP_OPACITY)
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
        m.set_editor_property("two_sided", True)
        mode = getattr(unreal.TranslucencyLightingMode, "TLM_SURFACE", None)
        if mode is not None:
            m.set_editor_property("translucency_lighting_mode", mode)
    else:
        # opaque, emissive, neon: a flat color; neon glows more by night (Night) and with
        # the actor's neon level
        col = tint_color(m, -600, 0)
        emi = expr(m, unreal.MaterialExpressionScalarParameter, -300, 540,
                   parameter_name="Emissive", default_value=0.0)
        em = expr(m, unreal.MaterialExpressionMultiply, -150, 500)
        link(col, "", em, "A")
        link(emi, "", em, "B")
        out = em
        if master == "neon":
            nt = night(m, -300, 640)
            lvl = sparam(m, "NeonLevel", -300, 720, 0.0, CPD["neon"])
            k = custom(m, -150, 650, "return (0.15 + 0.85 * Night) * (1.0 + Level);",
                       ["Night", "Level"], cmot(F1), "CgNeon")
            link(nt, "", k, "Night")
            link(lvl, "", k, "Level")
            out = expr(m, unreal.MaterialExpressionMultiply, 0, 550)
            link(em, "", out, "A")
            link(k, "", out, "B")
        rough = expr(m, unreal.MaterialExpressionScalarParameter, -300, 300,
                     parameter_name="Roughness", default_value=0.85)
        metal = expr(m, unreal.MaterialExpressionScalarParameter, -300, 380,
                     parameter_name="Metallic", default_value=0.0)
        MEL.connect_material_property(col, "", MP.MP_BASE_COLOR)
        MEL.connect_material_property(out, "", MP.MP_EMISSIVE_COLOR)
        MEL.connect_material_property(rough, "", MP.MP_ROUGHNESS)
        MEL.connect_material_property(metal, "", MP.MP_METALLIC)
        m.set_editor_property("two_sided", master == "foliage")
    for f in usage_flags(m):
        m.set_editor_property(f, True)        # (HLODs, HISMs, Nanite)
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


def delete_files(paths):
    """Delete the assets at `paths` by their package files (`PRUNE_FILES`): nothing names them
    (their actors were destroyed, the level saved and unloaded), so their packages are
    unloaded, their files deleted and the asset registry scans their folders again (a forced
    scan drops what is gone); how many were deleted."""
    if not paths:
        return 0
    names = sorted({p.split(".")[0] for p in paths})
    loaded = [k for k in (unreal.find_package(n) for n in names) if k is not None]
    if loaded:
        unreal.EditorLoadingAndSavingUtils.unload_packages(loaded)
    del loaded
    unreal.SystemLibrary.collect_garbage()
    content = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())
    for n in names:
        base = os.path.join(content, n[len("/Game/"):])
        for ext in (".uasset", ".uexp", ".ubulk"):
            if os.path.exists(base + ext):
                os.remove(base + ext)
    folders = sorted({n.rsplit("/", 1)[0] for n in names})
    unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(folders, True)
    gone = sum(1 for n in names if not EAL.does_asset_exist(n))
    log(f"deleted {gone} of {len(names)} assets by their files")
    return gone


def own_textures(mi, names):
    """Whether the instance `mi` holds a texture of its own for every parameter in `names`
    (one deleted under it leaves the parameter empty; reading it through
    get_material_instance_texture_parameter_value would give the master's default)."""
    have = {str(v.parameter_info.name): v.parameter_value
            for v in mi.get_editor_property("texture_parameter_values")}
    return all(have.get(n) is not None for n in names)


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
                      "graphs": {"written": 0, "kept": 0}, "timings": {}, "subtimings": {}}
        # the keys of the actors created, updated and deleted (a test compares them with the
        # objects whose hash changed between two manifests)
        self.keys = {"created": [], "updated": [], "deleted": []}
        self.eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        self.les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.placed, self.to_place = 0, None
        self.mats = {}
        # stage 2 (assetgen): its materials by (part, slot), the blockout keys it replaces
        self.s2 = man.get("stage2")
        self.mats2 = {}
        self.mi2, self.tex2 = {}, {}          # AG6: instances by asset, textures by name
        # the fast first import (exp_fast_import): stage 2's packs queued at once, each mesh
        # built once with its own settings; CITYGEN_UE_FAST=0 imports them one at a time
        self.fast = os.environ.get("CITYGEN_UE_FAST", "1") != "0" and \
            "CgPackStep" in globals() and hasattr(unreal.AssetImportTask(), "async_")
        self.pack_step = CgPackStep() if self.fast else None
        self.texture_step = CgTextureStep() if self.fast else None
        # (fast: the actors made are saved and unloaded every `offload_n`, see offload)
        self.offload_n = int(os.environ.get("CITYGEN_UE_OFFLOAD", "2000")) if self.fast else 0
        self.live, self.offloaded = [], []
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
        if name != "meshes2" or self.s2:        # (no stage 2: no stage of its own)
            REPORT.begin(STAGE_OF.get(name, name))
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

    def pipeline(self, nanite=True, bake=True, pack=False):
        """M15's import settings; stage 2's packs keep each mesh in its node's frame (`bake`
        off: the actor stands at the node's pivot) and build Nanite only where asked (`pack`:
        per mesh, by the pack step)."""
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
        if pack and self.pack_step is not None:
            stack.add_python_pipeline(self.pack_step)
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

    def current(self, folder, entries):
        """entries: [(asset name, stored hash)]; the meshes already there with that hash
        ({name: static mesh}) and the entries missing or stale."""
        out, stale = {}, []
        for name, h in entries:
            path = f"{folder}/{name}"
            sm = unreal.load_asset(path) if EAL.does_asset_exist(path) else None
            if sm is not None and meta(sm, HASH_TAG) == h:
                out[name] = sm
            else:
                stale.append((name, h))
        return out, stale

    def import_packs(self, todo):
        """Every stage 2 pack in `todo` queued as one async Interchange import (with the pack
        step), then waited for: Interchange runs half the worker threads' worth at a time,
        and each mesh's build goes to the asset compiling pool as its import ends."""
        tasks = []
        for pk, folder, entries, fresh in todo:
            glb = os.path.join(self.build, pk["glb"])
            PACK_PLAN[pack_key(glb)] = {m["asset"]: m for m in pk["meshes"]}
            task = unreal.AssetImportTask()
            task.filename = glb
            task.destination_path = folder
            task.automated = True
            task.replace_existing = True
            task.save = False
            task.set_editor_property("async_", True)
            task.options = self.pipeline(nanite=any(m["nanite"] for m in pk["meshes"]),
                                         bake=False, pack=True)
            tasks.append(task)
        if not tasks:
            return
        AT.import_asset_tasks(tasks)
        unreal.InterchangeManager.get_interchange_manager_scripted() \
            .wait_until_all_tasks_done(False)
        steps = PACK_STEPS
        self.stats["stage2"]["pack_step"] = {
            "packs": len(steps), "unmatched": sum(1 for x in steps if x.get("unmatched")),
            "skipped": sum(x["skipped"] for x in steps)}
        PACK_PLAN.clear()

    def import_group(self, glb, folder, entries, pipeline=None, finish=None,
                     version=MESH_VERSION, stats=None):
        """entries: [(asset name, hash)] of one glb; imports the glb when any is missing or
        stale; {asset name: static mesh}. (Stage 2 passes its own pipeline, finish(sm,
        stored hash), mesh version and counters.)"""
        finish = finish or self.finish_mesh
        stats = stats or self.stats
        entries = [(name, f"{version}.{h}") for name, h in entries]
        out, stale = self.current(folder, entries)
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
            REPORT.update(k + 1, n, force=k + 1 == n)
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
        stale = []
        for folder in (f"{self.root}/Meshes", f"{self.root}/Props"):
            if EAL.does_directory_exist(folder):
                stale += [a for a in EAL.list_assets(folder, recursive=True)
                          if a.split(".")[0] not in want]
        if stale:
            REPORT.note(f"deleting {len(stale)} blockout meshes no object uses")
        # stage 2's meshes no entry uses (its materials are pruned by materials2). A
        # blockout-only import leaves them as they are: its actors go, the assets stay for the
        # next import with stage 2 (deleting tens of thousands of meshes takes Unreal an hour)
        folder = f"{self.root}/{STAGE2_FOLDER}"
        stale2 = []
        if self.s2 and EAL.does_directory_exist(folder):
            want = {f"{self.root}/{p['folder']}/{m['asset']}" for p in self.s2["packs"]
                    for m in p["meshes"]}
            want |= {f"{self.root}/{c['mesh']}" for c in self.s2["lod_chains"]}
            # (the city's texture pages too: textures2 prunes them; they were deleted here
            # after every import, under the sign instances that use them)
            keep = (f"{folder}/Materials/", f"{folder}/Textures/")
            stale2 = [a for a in EAL.list_assets(folder, recursive=True)
                      if a.split(".")[0] not in want and not a.startswith(keep)]
        if stale2:
            REPORT.note(f"deleting {len(stale2)} stage 2 meshes no entry uses")
        files = len(stale) + len(stale2) > PRUNE_FILES
        if files:
            self.les.load_level(EMPTY_LEVEL)
        delete = delete_files if files else delete_assets
        self.stats["meshes"]["deleted"] += delete(stale)
        if stale2:
            self.stats["stage2"]["meshes"]["deleted"] += delete(stale2)
        if files:
            self.level()            # (the digests read its actors)

    # -- stage 2 (assetgen's layer: buildings, streets) --

    def textures2(self):
        """AG6's textures (the shared library under Core/Textures, the city's pages under
        Assets/Textures), each imported once and again only when its pixels change (its
        hash), with its color space, compression (normal maps with the green channel
        flipped: the library's are OpenGL) and texture group."""
        self.tex2 = {}
        if not self.s2 or not self.s2.get("textures"):
            return
        st = self.stats["stage2"].setdefault("textures", {"imported": 0, "kept": 0,
                                                          "deleted": 0})
        TCS = unreal.TextureCompressionSettings
        TG = unreal.TextureGroup
        todo = []
        for name, t in sorted(self.s2["textures"].items()):
            path = f"{t['folder']}/{t['asset']}"
            h = f"{TEXTURE_VERSION}.{t['hash']}"
            if EAL.does_asset_exist(path):
                tex = unreal.load_asset(path)
                if meta(tex, HASH_TAG) == h:
                    st["kept"] += 1
                    self.tex2[name] = tex
                    continue
            kind = t["kind"]
            want = [("srgb", bool(t["srgb"])),
                    ("compression_settings", TCS.TC_NORMALMAP if kind == "normal" else
                     (TCS.TC_MASKS if kind == "mask" else TCS.TC_DEFAULT))]
            if kind == "normal":
                want.append(("flip_green_channel", True))
            want.append(("lod_group", TG.TEXTUREGROUP_WORLD_NORMAL_MAP if kind == "normal"
                         else TG.TEXTUREGROUP_WORLD))
            todo.append((name, t, path, h, want))
        setters = self.texture_setters() if self.fast and todo else None
        tasks = []
        REPORT.update(0, len(todo), detail="textures", force=True)
        for i, (name, t, path, h, want) in enumerate(todo):
            task = unreal.AssetImportTask()
            f = os.path.join(self.build, t["file"])
            for k, v in (("filename", f), ("destination_path", t["folder"]),
                         ("destination_name", t["asset"]), ("automated", True),
                         ("replace_existing", True), ("save", False)):
                task.set_editor_property(k, v)
            if setters is None:
                AT.import_asset_tasks([task])
                self.finish_texture(name, t, path, h, want, save=True)
                REPORT.update(i + 1, len(todo), detail="textures")
                continue
            # (fast: every texture queued at once, each built once with its settings)
            TEXTURE_PLAN[pack_key(f)] = [(setters[k], int(getattr(v, "value", v)))
                                         if not isinstance(v, bool) else (setters[k], v)
                                         for k, v in want]
            task.set_editor_property("async_", True)
            stack = unreal.InterchangePipelineStackOverride()
            stack.add_pipeline(unreal.load_asset(
                "/Interchange/Pipelines/DefaultTexturePipeline.DefaultTexturePipeline"))
            stack.add_python_pipeline(self.texture_step)
            task.options = stack
            tasks.append(task)
        if tasks:
            AT.import_asset_tasks(tasks)
            unreal.InterchangeManager.get_interchange_manager_scripted() \
                .wait_until_all_tasks_done(False)
            TEXTURE_PLAN.clear()
            # (a texture the step did not find gets its settings after its import)
            st["texture_step"] = {"textures": len(tasks), "matched": len(TEXTURE_STEPS)}
            done = []
            for i, (name, t, path, h, want) in enumerate(todo):
                done.append(self.finish_texture(name, t, path, h, want, save=False))
                REPORT.update(i + 1, len(todo), detail="textures")
            EAL.save_loaded_assets(done, False)
        REPORT.update(len(todo), len(todo), detail="textures", force=True)
        # the city's pages it no longer has (the shared library's stay: other cities)
        folder = f"{self.root}/{STAGE2_FOLDER}/Textures"
        want = {f"{t['folder']}/{t['asset']}" for t in self.s2["textures"].values()}
        if EAL.does_directory_exist(folder):
            stale = [a for a in EAL.list_assets(folder, recursive=False)
                     if a.split(".")[0] not in want]
            st["deleted"] += delete_assets(stale)

    def texture_setters(self):
        """The texture factory node's setters by texture property (the pack step's for
        textures: their Python names as Unreal makes them)."""
        cls = unreal.InterchangeTextureFactoryNode
        names = {n.replace("_", "").lower(): n for n in dir(cls) if n.startswith("set_custom")}
        out = {}
        for prop, fn in (("srgb", "setcustomsrgb"),
                         ("compression_settings", "setcustomcompressionsettings"),
                         ("flip_green_channel", "setcustombflipgreenchannel"),
                         ("lod_group", "setcustomlodgroup")):
            if fn not in names:
                return None
            out[prop] = names[fn]
        return out

    def finish_texture(self, name, t, path, h, want, save=True):
        """A texture after its import: its settings (only those the texture step did not
        set already: each set builds it again), the hash."""
        tex = unreal.load_asset(path)
        if tex is None:
            raise RuntimeError(f"texture {name}: import of {t['file']} failed")
        for k, v in want:
            if not self.fast or tex.get_editor_property(k) != v:      # (main sets them all)
                tex.set_editor_property(k, v)
        EAL.set_metadata_tag(tex, HASH_TAG, h)
        if save:
            EAL.save_loaded_asset(tex, only_if_is_dirty=False)
        self.tex2[name] = tex
        self.stats["stage2"]["textures"]["imported"] += 1
        return tex

    def texture_defaults(self):
        """A texture of each kind for the masters' sample parameters (any the build has)."""
        out = {"color": None, "normal": None, "mask": None}
        for name, t in sorted((self.s2 or {}).get("textures", {}).items()):
            if out.get(t["kind"]) is None and name in self.tex2 and \
                    not name.startswith("city."):
                out[t["kind"]] = self.tex2[name]
        return out

    def materials2(self):
        """A master per stage 2 master name and an instance per part and material key (its
        color, roughness, metallic, emissive strength and tint rule; from AG6 its textures,
        scalars and vectors); stale instances deleted (none on a blockout-only import:
        stage 2's meshes, kept, still use them)."""
        if not self.s2:
            return
        folder = f"{self.root}/{STAGE2_FOLDER}/Materials"
        want = set()
        defaults = self.texture_defaults()
        masters = {m: stage2_master(m, defaults) for m in self.s2["masters"]}
        self.mi2 = {}
        st = self.stats["stage2"]["materials"]
        for key, p in sorted(self.s2["materials"].items()):
            path = f"{folder}/{p['asset']}"
            want.add(path)
            h = sha16([p, STAGE2_VERSION])
            key = p.get("key", p["slot"])
            if EAL.does_asset_exist(path):
                mi = unreal.load_asset(path)
                if meta(mi, HASH_TAG) == h and own_textures(mi, p.get("textures") or {}):
                    st["kept"] += 1
                    self.mats2[(p["part"], key)] = mi
                    self.mi2[p["asset"]] = mi
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
            # AG6: textures by parameter, scalars (TileM, Textured, StreakScale, Stains,
            # Interior, ...) and vectors (RefColor, linear)
            for name, t in sorted((p.get("textures") or {}).items()):
                MEL.set_material_instance_texture_parameter_value(mi, name,
                                                                 self.tex2[t["texture"]])
            for name, v in sorted((p.get("scalars") or {}).items()):
                MEL.set_material_instance_scalar_parameter_value(
                    mi, "StreakScale" if name == "Streaks" else name, float(v))
            for name, v in sorted((p.get("vectors") or {}).items()):
                MEL.set_material_instance_vector_parameter_value(
                    mi, name, unreal.LinearColor(v[0], v[1], v[2], 1.0))
            EAL.set_metadata_tag(mi, HASH_TAG, h)
            EAL.save_loaded_asset(mi)
            self.mats2[(p["part"], key)] = mi
            self.mi2[p["asset"]] = mi
        if EAL.does_directory_exist(folder):
            stale = [a for a in EAL.list_assets(folder, recursive=False)
                     if a.split(".")[0] not in want]
            self.stats["stage2"]["materials"]["deleted"] += delete_assets(stale)

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
        if self.fast:
            # (the flag set below, set first: the call cooks the body's collision again, and
            # with the default flag it cooks the whole shell's triangles as well; cooked data
            # is not saved with the asset)
            bs.set_editor_property("collision_trace_flag",
                                   unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX, NEVER)
        GS.set_static_mesh_collision_from_mesh(dm, sm, o, so)
        bs = sm.get_editor_property("body_setup")
        bs.set_editor_property("collision_trace_flag",
                               unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX, NEVER)
        if col.get("convex"):
            st["hulls"] += 1
        else:
            st["boxes_only"] += 1

    def nanite_as_asked(self, ns, rec):
        """Whether a mesh's Nanite settings are already what its entry asks (the pack step
        set them before the build): then finish2 builds it no second time."""
        if bool(ns.get_editor_property("enabled")) != bool(rec["nanite"]):
            return False
        shape = rec.get("shape_preservation")
        if shape:
            sp = getattr(getattr(unreal, "NaniteShapePreservation", None), shape.upper(), None)
            if sp is not None and ns.get_editor_property("shape_preservation") != sp:
                return False
        if rec.get("fallback_full"):
            tgt = getattr(getattr(unreal, "NaniteFallbackTarget", None), "PERCENT_TRIANGLES",
                          None)
            try:
                if tgt is not None and ns.get_editor_property("fallback_target") != tgt:
                    return False
                if ns.get_editor_property("fallback_percent_triangles") != 1.0 or \
                        ns.get_editor_property("fallback_relative_error") != 0.0:
                    return False
            except Exception:           # (a property this engine version lacks)
                return False
        return True

    def finish2(self, sm, rec, part, h, save=True):
        """A stage 2 mesh: its slots' instances, collision (hulls, complex, or none: the
        actor turns it off), Nanite off where the entry says (sky tube glass, proxies), the
        hash (`save` False: saved with the others once they are all built)."""
        t0 = time.perf_counter()
        mats = sm.get_editor_property("static_materials")     # (waits for the build)
        t1 = time.perf_counter()
        slots = []
        for s in mats:
            mi = self.mat2(part, str(s.material_slot_name))
            if mi is not None:
                s.set_editor_property("material_interface", mi)
            slots.append(s)
        sm.set_editor_property("static_materials", slots, NEVER)
        col = rec["collision"]
        t2 = time.perf_counter()
        if "boxes" in col:
            self.collision2(sm, col)
            self.add_sub("finish2.hulls", time.perf_counter() - t2)
        else:
            bs = sm.get_editor_property("body_setup")
            if bs is not None:
                bs.set_editor_property("collision_trace_flag",
                                       unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE,
                                       NEVER)
        ns = sm.get_editor_property("nanite_settings")
        shape = rec.get("shape_preservation")
        full = rec.get("fallback_full")
        again = not self.nanite_as_asked(ns, rec) if self.fast else \
            (bool(ns.get_editor_property("enabled")) != bool(rec["nanite"]) or shape or full)
        if again:                                  # (fast: the pack step set them already)
            ns.set_editor_property("enabled", bool(rec["nanite"]))
            if full:
                # AG3's street fronts: complex collision is built from the fallback mesh, so
                # the fallback keeps every triangle (doorways, steps and posts as drawn)
                tgt = getattr(unreal, "NaniteFallbackTarget", None)
                for k, v in (("fallback_target", getattr(tgt, "PERCENT_TRIANGLES", None)),
                             ("fallback_percent_triangles", 1.0),
                             ("fallback_relative_error", 0.0)):
                    if v is None:
                        continue
                    try:
                        ns.set_editor_property(k, v)
                    except Exception as ex:     # (a property this engine version lacks)
                        log(f"nanite {k}: {ex}")
            if shape:
                # AG8's plants: Nanite foliage (5.8, experimental; AG0 built its test tree so)
                sp = getattr(getattr(unreal, "NaniteShapePreservation", None),
                             shape.upper(), None)
                if sp is not None:
                    ns.set_editor_property("shape_preservation", sp)
            sm.set_editor_property("nanite_settings", ns)     # (builds the mesh again)
            self.stats["stage2"]["nanite_rebuilt"] = \
                self.stats["stage2"].get("nanite_rebuilt", 0) + 1
        EAL.set_metadata_tag(sm, HASH_TAG, h)
        t3 = time.perf_counter()
        if save:
            EAL.save_loaded_asset(sm, only_if_is_dirty=False)
        self.add_sub("finish2.wait_build", t1 - t0)
        self.add_sub("finish2.save", time.perf_counter() - t3)
        self.add_sub("finish2.all", time.perf_counter() - t0)

    def add_sub(self, k, dt):
        sub = self.stats["subtimings"]
        sub[k] = round(sub.get(k, 0.0) + dt, 3)

    def meshes2(self):
        """Stage 2's glTF packs (shells, proxies, street pieces, parts), each mesh in its
        node's frame; then the LOD chains. With `fast` every pack to import is queued at once
        (Interchange runs several imports at a time and the meshes build on every core while
        the next packs import), each mesh built once with its own settings (the pack step),
        then finished and saved in one batch; else one pack at a time, each mesh saved once
        built."""
        self.meshes_s2 = {}
        if not self.s2:
            return
        st = self.stats["stage2"]
        sub = self.stats["subtimings"]
        # (counted in meshes, not packs: the packs differ a lot in size)
        total = sum(len(pk["meshes"]) for pk in self.s2["packs"])
        todo = []
        for pk in self.s2["packs"]:
            if not pk["glb"]:
                raise RuntimeError(f"{pk['folder']}: its glTF pack is missing (run assetgen "
                                   "build)")
            folder = f"{self.root}/{pk['folder']}"
            entries = [(m["asset"], f"{STAGE2_MESH_VERSION}.{m['hash']}") for m in pk["meshes"]]
            got, stale = self.current(folder, entries)
            if stale:
                todo.append((pk, folder, entries, {name for name, _ in stale}))
                continue
            st["meshes"]["kept"] += len(entries)
            for a, sm in got.items():
                self.meshes_s2[f"{pk['folder']}/{a}"] = sm
        t = time.time()
        if self.fast:
            self.import_packs(todo)        # (its count: packs imported; then meshes finished)
        sub["meshes2.import"] = round(time.time() - t, 2)
        t = time.time()
        done = []
        seen = total - sum(len(x[2]) for x in todo)       # (the packs kept)
        built, nanite_built = 0, 0
        REPORT.update(seen, total, force=True)
        for k, (pk, folder, entries, fresh) in enumerate(todo):
            glb = os.path.join(self.build, pk["glb"])
            if not self.fast:
                self.import_glb(glb, folder, self.pipeline(
                    nanite=any(m["nanite"] for m in pk["meshes"]), bake=False))
            st["packs_imported"] += 1
            recs = {m["asset"]: m for m in pk["meshes"]}
            for name, h in entries:
                sm = unreal.load_asset(f"{folder}/{name}")
                if sm is None:
                    raise RuntimeError(f"{glb}: no static mesh {folder}/{name} after the import")
                # (one imported again with its pack, the same content: hash and settings kept)
                self.finish2(sm, recs[name], pk["part"], h, save=not self.fast)
                st["meshes"]["imported" if name in fresh else "kept"] += 1
                self.meshes_s2[f"{pk['folder']}/{name}"] = sm
                done.append(sm)
            built += len(entries)
            nanite_built += sum(1 for m in pk["meshes"] if m["nanite"])
            seen += len(entries)
            REPORT.update(seen, total, detail=f"pack {k + 1} of {len(todo)}, {built} built, "
                          f"{nanite_built} with Nanite", force=k + 1 == len(todo))
            if k % 25 == 0:
                log(f"stage 2 pack {k + 1}/{len(todo)} {pk['folder']}")
        sub["meshes2.finish"] = round(time.time() - t, 2)
        if self.fast and done:
            t = time.time()
            EAL.save_loaded_assets(done, False)
            sub["meshes2.save"] = round(time.time() - t, 2)
        t = time.time()
        # (the subsystem is not made in a commandlet; its LOD functions keep no state, so its
        # class default object serves)
        sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem) or \
            unreal.get_default_object(unreal.StaticMeshEditorSubsystem)
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
            sms.set_lod_screen_sizes(sm, [float(lo["screen_size"]) for lo in c["lods"]])
            EAL.set_metadata_tag(sm, HASH_TAG, h)
            EAL.save_loaded_asset(sm, only_if_is_dirty=False)
            self.meshes_s2[c["mesh"]] = sm
            st["meshes"]["imported"] += 1
            st["lod_chains"] += 1
        sub["meshes2.lod_chains"] = round(time.time() - t, 2)

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

    def actor_count(self):
        """How many actors `actors` places (the blockout's not replaced, its instancers not
        replaced, stage 2's, the player start and the lights)."""
        n = sum(1 for t in self.man["tiles"] for o in t["objects"] if o["key"] not in self.skip)
        n += sum(1 for i in self.man["instances"] if i["key"] not in self.skip)
        if self.s2:
            n += len(self.s2["actors"]) + len(self.s2["instances"])
        return n + 1 + 3                 # (the sun, the sky light, the atmosphere)

    def place(self, have, key, h, cls, make, update, folder, version=ACTOR_VERSION):
        """The actor of `key`: unchanged when its hash matches, else updated in place, else
        spawned; returns it."""
        self.placed += 1
        REPORT.update(self.placed, self.to_place)
        h = f"{version}.{h}"
        a = have.pop(key, None)
        created = a is None
        if a is not None:
            if f"{HASH_TAG}={h}" in [str(t) for t in a.tags]:
                self.stats["actors"]["unchanged"] += 1
                return a
            if a.get_class() != cls:
                self.destroy(a, key)
                a = None
                created = True
        if a is None:
            t0 = time.perf_counter()
            a = make()
            t1 = time.perf_counter()
            a.set_actor_label(key)
            a.set_folder_path(folder)
            self.add_sub("actors.spawn", t1 - t0)
            self.add_sub("actors.label_folder", time.perf_counter() - t1)
            self.stats["actors"]["created"] += 1
            self.keys["created"].append(key)
        else:
            # an actor whose mesh asset is the same object (its tile imported again in place)
            # and whose only change is its tags is not marked dirty by setting them: mark it,
            # or the level keeps the old hash and every import updates it again
            a.modify()
            self.stats["actors"]["updated"] += 1
            self.keys["updated"].append(key)
        t0 = time.perf_counter()
        update(a, h)
        self.add_sub("actors.update", time.perf_counter() - t0)
        if self.offload_n and created:
            self.live.append(key)
            if len(self.live) >= self.offload_n:
                self.offload()
        return a

    def offload(self):
        """Save the actors made since the last offload and unload them (World Partition keeps
        them on disk; `reload` brings them all back after the last one is made). Every spawn
        through the editor's placement path labels the new actor uniquely by collecting the
        label of every actor in the world first, so a first import that keeps all its actors
        loaded spends time growing with the square of their number; few loaded, it stays
        linear."""
        if not self.live:
            return
        t = time.perf_counter()
        self.save()
        want = set(self.live)
        WPL = unreal.WorldPartitionBlueprintLibrary
        guids = [d.guid for d in WPL.get_actor_descs() if str(d.label) in want]
        if guids:
            WPL.load_actors(guids)          # (the library's references, then let go of them)
            WPL.unload_actors(guids)
            self.offloaded += guids
        self.live = []
        self.add_sub("actors.offload", time.perf_counter() - t)

    def reload(self):
        if not self.offloaded:
            return
        REPORT.note(f"loading the {len(self.offloaded)} actors saved meanwhile back")
        t = time.perf_counter()
        unreal.WorldPartitionBlueprintLibrary.load_actors(self.offloaded)
        self.stats["offloaded"] = len(self.offloaded)
        self.offloaded = []
        self.add_sub("actors.reload", time.perf_counter() - t)

    def actors(self):
        have = self.existing()
        log(f"{len(have)} actors of {self.city} in the level")
        self.placed = 0
        self.to_place = self.actor_count()
        REPORT.update(0, self.to_place, force=True)
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
        REPORT.update(self.placed, self.to_place, force=True)
        self.offload_n = 0
        self.live = []
        self.reload()
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
                # (the defaults: the run-time values are not saved with the level)
                c.set_default_custom_primitive_data_float_array(0, [float(v) for v in r["cpd"]])
                # AG6: the slots this actor takes another instance for (its era's walls)
                for slot, asset in sorted((r.get("materials") or {}).items()):
                    mi = self.mi2.get(asset)
                    i = c.get_material_index(unreal.Name(slot))
                    if mi is not None and i >= 0:
                        c.set_material(i, mi)
                if r.get("no_collision"):
                    c.set_collision_profile_name("NoCollision")
                # (AG3: a street front's doors, `cg.door=<door id>@<walkway id>`, stage 4's)
                doors = [unreal.Name(f"cg.door={d}") for d in r.get("doors", [])]
                a.tags = self.tags(r["key"], h, r["ids"], r["type"], r["category"],
                                   r["tile"], r["district"], r.get("level", 0)) + [stage] + \
                    doors

            self.place(have, r["key"], r["hash"], sma, make, update,
                       f"CityGen/{r['category']}", STAGE2_ACTOR_VERSION)
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
                # [x, y, z, yaw] or, with a scale (AG8's props and plants), [..., sx, sy, sz]
                comp.add_instances([unreal.Transform(
                    unreal.Vector(xf[0] * 100.0, -xf[1] * 100.0, xf[2] * 100.0),
                    unreal.Rotator(roll=0.0, pitch=0.0, yaw=-xf[3]),
                    unreal.Vector(*(xf[4:7] if len(xf) >= 7 else (1, 1, 1))))
                    for xf in r["xforms"]], False, False)
                comp.set_default_custom_primitive_data_float_array(
                    0, [float(v) for v in r["cpd"]])
                for slot, asset in sorted((r.get("materials") or {}).items()):
                    mi = self.mi2.get(asset)
                    i = comp.get_material_index(unreal.Name(slot))
                    if mi is not None and i >= 0:
                        comp.set_material(i, mi)
                if r.get("no_collision"):
                    comp.set_collision_profile_name("NoCollision")
                a.set_actor_location_and_rotation(loc, rot, False, False)
                a.set_editor_property("Ids", [unreal.Name(i) for i in r.get("ids") or
                                              [r["entry"]]])
                a.set_editor_property("Kind", unreal.Name(r["kind"]))
                a.tags = self.tags(r["key"], h, [r["entry"]], r["type"], r["category"],
                                   r["tile"], r["district"], r.get("level", 0)) + [stage]

            self.place(have, r["key"], r["hash"], cls, make, update,
                       f"CityGen/{r['category']}", STAGE2_ACTOR_VERSION)

    def instances(self, have):
        cls = blueprint(f"{CORE}/BP_CityGenInstances", unreal.Actor, INSTANCE_VARS, hism=True)
        ts = self.man["tile_size_m"]
        tiles = {t["name"]: t for t in self.man["tiles"]}
        for inst in self.man["instances"]:
            if inst["key"] in self.skip:
                continue            # (AG8's variants in its place)
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

    # -- what Play puts you in, and how far the level streams around you --

    def world_settings(self):
        return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world() \
            .get_world_settings()

    def play(self):
        """The level's game mode override: the fly pawn's game mode (`fly`), else none, so
        the project's own game mode and pawn (`walk`). The fly classes are made either way
        (the check flies the city with them)."""
        mode = JOB.get("play", "fly")
        fly, saved = fly_classes(JOB.get("fly_speed_m_s", 50.0))
        want = fly if mode == "fly" else None
        ws = self.world_settings()
        have = ws.get_editor_property("default_game_mode")
        if (have.get_path_name() if have else "") != (want.get_path_name() if want else ""):
            ws.set_editor_property("default_game_mode", want)
        self.stats["play"] = {"mode": mode, "fly_speed_m_s": JOB.get("fly_speed_m_s", 50.0),
                              "game_mode": want.get_path_name() if want else "",
                              "fly_classes_saved": saved}

    def streaming(self):
        """World Partition for flying over the city: the main partition's cells a tile wide
        (256 m), loaded `view_m` around the player; the far view (the HLODs `citygen unreal`
        builds after the import) the level's instanced HLOD layer alone, the city's own
        meshes and materials in cells twice as wide out to the whole city, nothing baked
        (the merged layer the engine puts over it is cut off), the last HLOD partition left
        unused at twice that. Set only where they differ."""
        view = int(round(float(JOB.get("view_m", 1500.0)) * 100.0))
        b = self.man["bounds"]
        span = int(math.ceil(math.hypot(b[2] - b[0], b[3] - b[1]) * 100.0))
        wp = self.world_settings().get_editor_property("world_partition")
        base = wp.get_path_name() + ".WorldPartitionRuntimeHashSet_0"
        parts = [p for p in (unreal.find_object(None, f"{base}.RuntimePartitionLHGrid_{i}")
                             for i in range(8)) if p is not None]
        if len(parts) != 3:
            self.stats["streaming"] = {"set": False, "partitions": len(parts)}
            log(f"streaming: {len(parts)} grid partitions, not the main and two HLOD ones; "
                "left as they are")
            return
        # the main partition has the smallest cells, each HLOD one twice its parent's
        parts.sort(key=lambda p: (p.get_editor_property("CellSize"), p.get_name()))
        cell = int(self.man["tile_size_m"] * 100.0)
        want = [(cell, view), (2 * cell, max(2 * view, span)),
                (4 * cell, max(4 * view, span))]
        changed = 0
        for p, (c, r) in zip(parts, want):
            if p.get_editor_property("CellSize") != c or p.get_editor_property("LoadingRange") != r:
                p.modify()
                p.set_editor_property("CellSize", c)
                p.set_editor_property("LoadingRange", r)
                changed += 1
        hl = wp.get_editor_property("default_hlod_layer")
        if hl is not None and hl.get_editor_property("parent_layer") is not None:
            hl.set_editor_property("parent_layer", None)
            EAL.save_loaded_asset(hl, only_if_is_dirty=False)
            changed += 1
        self.stats["streaming"] = {"set": True, "changed": changed,
                                   "hlod_layer": hl.get_name() if hl else "",
                                   "cells_m": [c / 100.0 for c, _ in want],
                                   "loading_ranges_m": [r / 100.0 for _, r in want]}

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
        REPORT.out("plan", first=not EAL.does_asset_exist(
            f"{self.root}/Maps/{self.man['folder']}"),
            objects=sum(len(t["objects"]) for t in self.man["tiles"]),
            tiles=len(self.man["tiles"]), actors=self.actor_count(),
            packs=len(self.s2["packs"]) if self.s2 else 0,
            meshes2=sum(len(pk["meshes"]) for pk in self.s2["packs"]) if self.s2 else 0,
            textures=len(self.s2.get("textures") or {}) if self.s2 else 0)
        base = self.timed("core", base_material)
        self.timed("materials", self.materials, base)
        self.timed("textures2", self.textures2)
        self.timed("materials2", self.materials2)
        self.timed("meshes", self.meshes)
        self.timed("meshes2", self.meshes2)
        self.timed("level", self.level)
        self.timed("actors", self.actors)
        self.timed("play", self.play)
        self.timed("streaming", self.streaming)
        self.timed("graphs", self.graphs)
        # saved before the meshes no object uses are deleted: deleting an asset that the open
        # level still names reloads the level, which drops what was not saved
        self.timed("save", self.save)
        self.timed("prune", self.prune_meshes)
        self.timed("save_pruned", self.save)
        self.stats.update(self.timed("digests", self.digests))
        REPORT.end()
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
