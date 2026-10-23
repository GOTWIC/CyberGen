"""
Builds the Corporate Core greybox in the currently open Unreal level.

Setup: put this file and corporate_core_plan.json in <YourProject>/Greybox/,
open a level, then Tools > Execute Python Script and pick this file.
Rerunning deletes the previous greybox first, so iterate freely.
Ctrl+Z undoes a whole run.
"""
import json, os
import unreal

TAG = "CorporateCoreGreybox"
FOLDER = "Greybox/CorporateCore"
MAT_DIR = "/Game/Greybox"
PLAN_NAME = "corporate_core_plan.json"

COLORS = {  # linear RGB
    "water": (0.03, 0.10, 0.18), "ground": (0.55, 0.53, 0.49), "pier": (0.38, 0.36, 0.33),
    "bridge": (0.10, 0.11, 0.12), "highway": (0.04, 0.045, 0.05), "avenue": (0.06, 0.065, 0.075),
    "street": (0.09, 0.095, 0.10), "plaza": (0.72, 0.69, 0.62), "green": (0.20, 0.34, 0.14),
    "canal": (0.05, 0.22, 0.38), "podium": (0.42, 0.45, 0.50), "tower": (0.55, 0.57, 0.60),
    "lowrise": (0.46, 0.47, 0.49), "landmark": (0.60, 0.42, 0.15),
}
MESHES = {"box": "/Engine/BasicShapes/Cube", "cyl": "/Engine/BasicShapes/Cylinder"}

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def find_plan():
    candidates = []
    try:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), PLAN_NAME))
    except NameError:
        pass
    proj = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
    candidates.append(os.path.join(proj, "Greybox", PLAN_NAME))
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise RuntimeError("Could not find %s. Looked in: %s" % (PLAN_NAME, candidates))


def base_material():
    path = MAT_DIR + "/M_Greybox"
    if eal.does_asset_exist(path):
        return eal.load_asset(path)
    mat = tools.create_asset("M_Greybox", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    color = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -400, 0)
    color.set_editor_property("parameter_name", "Color")
    color.set_editor_property("default_value", unreal.LinearColor(0.5, 0.5, 0.5, 1.0))
    mel.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    rough = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 250)
    rough.set_editor_property("r", 0.85)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(mat)
    eal.save_asset(path)
    return mat


def category_material(cat, parent):
    name = "MI_Greybox_" + cat
    path = MAT_DIR + "/" + name
    if eal.does_asset_exist(path):
        mi = eal.load_asset(path)
    else:
        mi = tools.create_asset(name, MAT_DIR, unreal.MaterialInstanceConstant,
                                unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mi, parent)
    r, g, b = COLORS.get(cat, (0.5, 0.5, 0.5))
    mel.set_material_instance_vector_parameter_value(mi, "Color", unreal.LinearColor(r, g, b, 1.0))
    mel.update_material_instance(mi)
    eal.save_asset(path)
    return mi


def clear_previous():
    old = [a for a in actors.get_all_level_actors() if TAG in [str(t) for t in a.tags]]
    for a in old:
        actors.destroy_actor(a)
    return len(old)


def to_ue(x, y, z):
    # plan: meters, x=east, y=north  ->  Unreal: cm, X=north (forward), Y=east (right)
    return unreal.Vector(y * 100.0, x * 100.0, z * 100.0)


def main():
    plan = json.load(open(find_plan()))
    prims = plan["primitives"]
    parent = base_material()
    mats = {c: category_material(c, parent) for c in sorted({p["cat"] for p in prims})}
    meshes = {k: eal.load_asset(v) for k, v in MESHES.items()}

    with unreal.ScopedEditorTransaction("Build Corporate Core greybox"):
        removed = clear_previous()
        with unreal.ScopedSlowTask(len(prims), "Building Corporate Core greybox") as task:
            task.make_dialog(True)
            counts = {}
            for p in prims:
                if task.should_cancel():
                    break
                task.enter_progress_frame(1)
                cat = p["cat"]
                counts[cat] = counts.get(cat, 0) + 1
                x, y, z = p["center"]
                sx, sy, sz = p["size"]
                # plan yaw is CCW from east; Unreal yaw is clockwise (seen from above) from north
                rot = unreal.Rotator(roll=0.0, pitch=0.0, yaw=90.0 - p["yaw"])
                a = actors.spawn_actor_from_object(meshes[p["kind"]], to_ue(x, y, z), rot)
                # basic shapes are 1 m cubes/cylinders, so scale == size in meters
                # (local X = length, local Y = width; plan size is [length, width, height])
                a.set_actor_scale3d(unreal.Vector(sx, sy, sz))
                a.static_mesh_component.set_material(0, mats[cat])
                a.set_actor_label("%s_%03d" % (cat, counts[cat]))
                a.set_folder_path("%s/%s" % (FOLDER, cat))
                a.set_editor_property("tags", [unreal.Name(TAG)])

        # move any PlayerStart onto the south boulevard, facing the megatower
        sx, sy, sz = plan["meta"]["player_start"]
        for a in actors.get_all_level_actors():
            if isinstance(a, unreal.PlayerStart):
                a.set_actor_location(to_ue(sx, sy, sz), False, False)
                a.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=0.0, yaw=0.0), False)

    unreal.log("Corporate Core greybox: removed %d old actors, spawned %d." % (removed, sum(counts.values())))


main()
