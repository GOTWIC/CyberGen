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

Importing again updates by key and hash: a tile's meshes are imported again only when one
of its objects changed or is missing, an actor is changed only when its hash changed, and
what the build no longer has is deleted. The same build twice changes nothing.
"""

import hashlib
import json
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

    def pipeline(self):
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
        msh.set_editor_property("build_nanite", True)
        # no mesh distance fields or Lumen cards: thousands of blockout meshes would take the
        # editor an hour to build them before its first frame (screen-space GI is enough)
        msh.set_editor_property("distance_field_resolution_scale", 0.0)
        msh.set_editor_property("max_lumen_mesh_cards", 0)
        stack = unreal.InterchangePipelineStackOverride()
        stack.add_pipeline(gp)
        return stack

    def import_glb(self, glb, folder):
        task = unreal.AssetImportTask()
        task.filename = glb
        task.destination_path = folder
        task.automated = True
        task.replace_existing = True
        task.save = False
        task.options = self.pipeline()
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

    def import_group(self, glb, folder, entries):
        """entries: [(asset name, hash)] of one glb; imports the glb when any is missing or
        stale; {asset name: static mesh}."""
        out, stale = {}, []
        entries = [(name, f"{MESH_VERSION}.{h}") for name, h in entries]
        for name, h in entries:
            path = f"{folder}/{name}"
            sm = unreal.load_asset(path) if EAL.does_asset_exist(path) else None
            if sm is not None and meta(sm, HASH_TAG) == h:
                out[name] = sm
            else:
                stale.append((name, h))
        if not stale:
            self.stats["meshes"]["kept"] += len(entries)
            return out
        self.import_glb(glb, folder)
        self.stats["tiles_imported"] += 1
        fresh = {n for n, _ in stale}
        for name, h in entries:
            path = f"{folder}/{name}"
            sm = unreal.load_asset(path)
            if sm is None:
                raise RuntimeError(f"{glb}: no static mesh {path} after the import")
            if name in fresh:
                self.finish_mesh(sm, h)
                self.stats["meshes"]["imported"] += 1
            else:
                # imported again with the tile (same content): keep the hash and settings
                self.finish_mesh(sm, h)
                self.stats["meshes"]["kept"] += 1
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
        self.player_start(have)
        self.lighting(have)
        for key, a in sorted(have.items()):
            self.destroy(a, key)

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
        for folder in ("Meshes", "Props", "Materials", "Data"):
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
        self.timed("meshes", self.meshes)
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
