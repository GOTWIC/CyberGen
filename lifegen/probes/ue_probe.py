"""LG0's probe of Unreal 5.8 from a script (docs/progress/LG0/README.md, "Probes"): run in
the editor of a throwaway project (never a city's), stdlib and `unreal` only:

    UnrealEditor-Cmd PROJECT.uproject -run=pythonscript -script=lifegen/probes/ue_probe.py
        (env LG0_PROBE_OUT: the result's JSON file; LG0_PROBE_FBX: a CMU-style clip, FBX,
         from lifegen/probes/cmu_style.py, to retarget)

What it tries, each step recorded with what it returned or raised:

1. **The Python API:** which classes and functions of MetaHuman Creator, MetaHuman crowds,
   Mutable, IK Rig and retargeting, Pose Search (motion matching), AnimToTexture, Mass,
   ZoneGraph, Smart Objects and StateTree the editor's Python exposes.
2. **MetaHuman from a script:** a MetaHuman Character asset made by its factory, opened for
   editing by the editor subsystem, its body's constraints (height and measurements) read and
   set, its skin set, whether it can be built, and the build (the assembled skeletal meshes).
3. **Mutable:** a Customizable Object made by its factory, and whether its graph can be
   written from Python.
4. **Retargeting by script:** a CMU-style clip (a BVH skeleton of the CMU database's
   hierarchy, its walk generated, skinned to a stick figure in Blender) imported, IK rigs
   made for it and for the template's mannequin with their auto chains, a retargeter between
   them with its auto chain mapping, and the clip retargeted onto the mannequin in a batch.
"""

import json
import os
import traceback

import unreal

OUT = os.environ.get("LG0_PROBE_OUT", "lg0_probe.json")
FBX = os.environ.get("LG0_PROBE_FBX", "")
ROOT = "/Game/LG0Probe"
EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
R = {"steps": [], "api": {}}


def step(name):
    def wrap(fn):
        def run(*a, **k):
            rec = {"step": name}
            try:
                rec["result"] = fn(*a, **k)
                rec["ok"] = True
            except Exception as e:                                  # noqa: BLE001
                rec["ok"] = False
                rec["error"] = f"{type(e).__name__}: {e}"
                rec["trace"] = traceback.format_exc()[-1500:]
            R["steps"].append(rec)
            unreal.log(f"LG0_PROBE {name}: {'ok' if rec['ok'] else rec['error']}")
            return rec.get("result")
        return run
    return wrap


def members(cls_name, words=()):
    cls = getattr(unreal, cls_name, None)
    if cls is None:
        return None
    names = [n for n in dir(cls) if not n.startswith("_")]
    if words:
        names = [n for n in names if any(w in n.lower() for w in words)]
    return names


@step("api")
def api():
    want = {
        "metahuman": ["MetaHumanCharacter", "MetaHumanCharacterEditorSubsystem",
                      "MetaHumanCharacterFactoryNew", "MetaHumanCollection",
                      "MetaHumanCharacterEditorBuildParameters",
                      "MetaHumanCharacterBodyConstraint", "MetaHumanCharacterSkinSettings",
                      "MetaHumanCharacterExportBlueprintLibrary",
                      "MetaHumanCollectionBlueprintLibrary", "MetaHumanCrowdCharacter",
                      "MetaHumanCrowdBlueprintLibrary"],
        "mutable": ["CustomizableObject", "CustomizableObjectInstance",
                    "CustomizableObjectFactoryNew", "CustomizableObjectFactory",
                    "CustomizableObjectEditorFunctionLibrary", "CustomizableSkeletalComponent",
                    "CustomizableObjectNodeObject"],
        "retarget": ["IKRigDefinition", "IKRigController", "IKRetargeter",
                     "IKRetargeterController", "IKRetargetBatchOperation",
                     "IKRigDefinitionFactory", "IKRetargetFactory"],
        "motion": ["PoseSearchDatabase", "PoseSearchSchema", "PoseSearchLibrary"],
        "baked": ["AnimToTextureBPLibrary", "AnimToTextureDataAsset"],
        "mass": ["MassEntityConfigAsset", "MassSpawner", "MassEntitySubsystem",
                 "ZoneGraphSubsystem", "ZoneGraphData", "ZoneShape", "SmartObjectDefinition",
                 "SmartObjectSubsystem", "StateTree", "StateTreeComponent"],
        "cloth": ["ChaosClothAsset", "ChaosOutfitAsset", "ChaosClothComponent"],
    }
    out = {}
    for group, names in want.items():
        out[group] = {n: getattr(unreal, n, None) is not None for n in names}
    R["api"]["subsystem_functions"] = members("MetaHumanCharacterEditorSubsystem")
    R["api"]["mutable_library"] = members("CustomizableObjectEditorFunctionLibrary")
    R["api"]["retarget_batch"] = members("IKRetargetBatchOperation")
    R["api"]["retarget_controller"] = members("IKRetargeterController",
                                              ("auto", "chain", "source", "target", "op"))
    R["api"]["ikrig_controller"] = members("IKRigController", ("auto", "skeletal", "chain"))
    R["api"]["anim_to_texture"] = members("AnimToTextureBPLibrary")
    R["api"]["crowd_library"] = members("MetaHumanCrowdBlueprintLibrary")
    return out


@step("metahuman.create")
def mh_create():
    fac_cls = getattr(unreal, "MetaHumanCharacterFactoryNew", None)
    if fac_cls is None:
        raise RuntimeError("no MetaHumanCharacterFactoryNew in Python")
    path = f"{ROOT}/MH_Probe"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    ch = AT.create_asset("MH_Probe", ROOT, unreal.MetaHumanCharacter, fac_cls())
    if ch is None:
        raise RuntimeError("the factory made nothing")
    return {"asset": ch.get_path_name()}


@step("metahuman.edit")
def mh_edit():
    ch = unreal.load_asset(f"{ROOT}/MH_Probe")
    sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
    if sub is None:
        raise RuntimeError("no MetaHumanCharacterEditorSubsystem")
    ok = sub.try_add_object_to_edit(ch)
    out = {"added_for_editing": bool(ok)}
    cons = sub.get_body_constraints(ch, False)
    out["body_constraints"] = [
        {k: str(c.get_editor_property(k)) for k in ("name", "is_active", "target_measurement",
                                                    "min_measurement", "max_measurement")}
        for c in list(cons)[:12]]
    # height and a few measurements by name, as a person's seed would draw them
    changed = []
    for c in cons:
        n = str(c.get_editor_property("name")).lower()
        if n in ("height", "chest", "waist"):
            lo, hi = c.get_editor_property("min_measurement"), c.get_editor_property(
                "max_measurement")
            c.set_editor_property("is_active", True)
            c.set_editor_property("target_measurement", lo + 0.7 * (hi - lo))
            changed.append(n)
    sub.set_body_constraints(ch, cons)
    sub.commit_body_state(ch)
    out["constraints_set"] = changed
    try:
        skin = unreal.MetaHumanCharacterSkinSettings()
        props = skin.get_editor_property("skin")
        props.set_editor_property("u", 0.7)
        props.set_editor_property("v", 0.35)
        skin.set_editor_property("skin", props)
        sub.commit_skin_settings(ch, skin)
        out["skin"] = "set (tone u 0.7, v 0.35)"
    except Exception as e:                                          # noqa: BLE001
        out["skin"] = f"{type(e).__name__}: {e}"
    out["can_build"] = bool(sub.can_build_meta_human(ch, True))
    return out


@step("metahuman.build")
def mh_build():
    ch = unreal.load_asset(f"{ROOT}/MH_Probe")
    sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
    params = unreal.MetaHumanCharacterEditorBuildParameters()
    try:
        params.set_editor_property("absolute_build_path", f"{ROOT}/Built")
    except Exception:                                               # noqa: BLE001
        pass
    sub.build_meta_human(ch, params)
    made = [a for a in EAL.list_assets(ROOT, recursive=True) if "/Built" in a or "MH_Probe" in a]
    EAL.save_directory(ROOT, only_if_is_dirty=True, recursive=True)
    return {"assets": made[:60], "count": len(made),
            "params": [n for n in dir(params) if not n.startswith("_")][:40]}


@step("mutable.create")
def mutable():
    cls = getattr(unreal, "CustomizableObject", None)
    if cls is None:
        raise RuntimeError("no CustomizableObject class (Mutable not enabled)")
    fac = None
    for n in ("CustomizableObjectFactoryNew", "CustomizableObjectFactory"):
        if getattr(unreal, n, None) is not None:
            fac = getattr(unreal, n)()
            break
    if fac is None:
        raise RuntimeError("no factory for CustomizableObject in Python")
    obj = AT.create_asset("CO_Probe", ROOT, cls, fac)
    graph = [n for n in dir(obj) if "graph" in n.lower() or "node" in n.lower()]
    return {"asset": obj.get_path_name() if obj else None, "graph_members": graph,
            "node_classes": [n for n in dir(unreal) if n.startswith("CustomizableObjectNode")][:40]}


def _import_fbx(path, dest, skeleton=None):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", path)
    task.set_editor_property("destination_path", dest)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("replace_existing", True)
    opts = unreal.FbxImportUI()
    opts.set_editor_property("import_mesh", True)
    opts.set_editor_property("import_as_skeletal", True)
    opts.set_editor_property("import_animations", True)
    opts.set_editor_property("import_materials", False)
    opts.set_editor_property("import_textures", False)
    opts.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    task.set_editor_property("options", opts)
    AT.import_asset_tasks([task])
    return [str(p) for p in task.get_editor_property("imported_object_paths")]


def _ik_rig(name, mesh):
    path = f"{ROOT}/Retarget/{name}"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    rig = AT.create_asset(name, f"{ROOT}/Retarget", unreal.IKRigDefinition,
                          unreal.IKRigDefinitionFactory())
    ctl = unreal.IKRigController.get_controller(rig)
    ctl.set_skeletal_mesh(mesh)
    done = []
    for fn in ("apply_auto_generated_retarget_definition", "apply_auto_fbik"):
        if hasattr(ctl, fn):
            getattr(ctl, fn)()
            done.append(fn)
    chains = [str(c.get_editor_property("chain_name")) for c in ctl.get_retarget_chains()] \
        if hasattr(ctl, "get_retarget_chains") else []
    return rig, {"rig": path, "auto": done, "chains": chains,
                 "root": str(ctl.get_retarget_root()) if hasattr(ctl, "get_retarget_root")
                 else None}


@step("retarget.cmu_style")
def retarget():
    if not FBX or not os.path.isfile(FBX):
        raise RuntimeError("no CMU-style clip (LG0_PROBE_FBX)")
    got = _import_fbx(FBX, f"{ROOT}/CMU")
    src_mesh = next((unreal.load_asset(p) for p in got
                     if isinstance(unreal.load_asset(p), unreal.SkeletalMesh)), None)
    anims = [p for p in got if isinstance(unreal.load_asset(p), unreal.AnimSequence)]
    if src_mesh is None or not anims:
        raise RuntimeError(f"the clip imported as {got}")
    tgt_path = next((p for p in ("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple",
                                 "/Game/Characters/Mannequins/Meshes/SKM_Manny",
                                 "/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple")
                     if EAL.does_asset_exist(p)), None)
    if tgt_path is None:
        raise RuntimeError("no mannequin in the project (the First Person template's)")
    tgt_mesh = unreal.load_asset(tgt_path)
    src_rig, src_info = _ik_rig("IK_CMU", src_mesh)
    tgt_rig, tgt_info = _ik_rig("IK_Manny", tgt_mesh)
    path = f"{ROOT}/Retarget/RTG_CMU_to_Manny"
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    rtg = AT.create_asset("RTG_CMU_to_Manny", f"{ROOT}/Retarget", unreal.IKRetargeter,
                          unreal.IKRetargetFactory())
    rc = unreal.IKRetargeterController.get_controller(rtg)
    src_side = unreal.RetargetSourceOrTarget.SOURCE
    tgt_side = unreal.RetargetSourceOrTarget.TARGET
    rc.set_ik_rig(src_side, src_rig)
    rc.set_ik_rig(tgt_side, tgt_rig)
    steps = []
    for fn, args in (("set_preview_mesh", (src_side, src_mesh)),
                     ("set_preview_mesh", (tgt_side, tgt_mesh)),
                     ("add_default_ops", ()), ("auto_map_chains", None),
                     ("auto_align_all_bones", (tgt_side,))):
        if not hasattr(rc, fn):
            continue
        try:
            if fn == "auto_map_chains":
                rc.auto_map_chains(unreal.AutoMapChainType.FUZZY, True)
            else:
                getattr(rc, fn)(*args)
            steps.append(fn)
        except Exception as e:                                      # noqa: BLE001
            steps.append(f"{fn}: {type(e).__name__}: {e}")
    EAL.save_loaded_asset(rtg)
    pairs = [EAL.find_asset_data(a) for a in anims]
    out = unreal.IKRetargetBatchOperation.duplicate_and_retarget(
        pairs, src_mesh, tgt_mesh, rtg, "", "", "_Manny", "", False, True)
    made = [str(x.get_editor_property("package_name")) for x in out]
    frames = []
    for p in made:
        seq = unreal.load_asset(p)
        if isinstance(seq, unreal.AnimSequence):
            frames.append({"asset": p, "length_s": seq.get_editor_property("sequence_length")
                           if hasattr(seq, "sequence_length") else
                           unreal.AnimationLibrary.get_sequence_length(seq),
                           "skeleton": seq.get_editor_property("skeleton").get_path_name()})
    EAL.save_directory(ROOT, only_if_is_dirty=True, recursive=True)
    return {"imported": got, "source_rig": src_info, "target_rig": tgt_info,
            "retargeter_steps": steps, "retargeted": frames}


def main():
    api()
    mh_create()
    mh_edit()
    mh_build()
    mutable()
    retarget()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(R, f, indent=1, default=str)
    unreal.log(f"LG0_PROBE done: {OUT}")


main()
