"""The clothing fixes' look check, the editor's half (stdlib and `unreal` only): exports looks of
the people library as FBX (the look's garments with their skin weights, the character's body,
the walk clip) for `lifegen/probes/look_pose.py`, which poses them in Blender along the walk and
measures and renders where an inner layer comes through an outer one.

    UnrealEditor PROJECT.uproject -ExecCmds="py lifegen/probes/look_export_ue.py" -RenderOffscreen
        (env CITYGEN_UE_JOB: {result, out, items: [{look, look_mesh, body, anim}]}; the full
        editor: a skeletal mesh's FBX export asserts with no renderer)

Nothing it exports goes in the repo (the bodies and clips are Epic's and MetaHuman's).
"""

import json
import os
import traceback

import unreal

JOB = json.load(open(os.environ["CITYGEN_UE_JOB"], encoding="utf-8"))
R = {"ok": False, "items": {}}


def export(asset_path, filename, exporter, anim=False):
    a = unreal.load_asset(asset_path)
    if a is None:
        raise RuntimeError(f"no asset {asset_path}")
    t = unreal.AssetExportTask()
    t.set_editor_property("object", a)
    t.set_editor_property("filename", filename)
    t.set_editor_property("automated", True)
    t.set_editor_property("prompt", False)
    t.set_editor_property("replace_identical", True)
    t.set_editor_property("exporter", exporter)
    o = unreal.FbxExportOption()
    o.set_editor_property("ascii", False)
    o.set_editor_property("collision", False)
    o.set_editor_property("level_of_detail", False)
    o.set_editor_property("vertex_color", True)
    o.set_editor_property("export_morph_targets", False)
    if anim:
        o.set_editor_property("export_preview_mesh", False)
    t.set_editor_property("options", o)
    if not unreal.Exporter.run_asset_export_task(t):
        raise RuntimeError(f"the export of {asset_path} failed")
    return filename


def main():
    out = JOB["out"]
    os.makedirs(out, exist_ok=True)
    done = set()
    for it in JOB["items"]:
        rec = {}
        try:
            d = os.path.join(out, it["look"])
            os.makedirs(d, exist_ok=True)
            rec["look"] = export(it["look_mesh"], os.path.join(d, "look.fbx"),
                                 unreal.SkeletalMeshExporterFBX())
            rec["body"] = export(it["body"], os.path.join(d, "body.fbx"),
                                 unreal.SkeletalMeshExporterFBX())
            key = it["anim"]
            af = os.path.join(out, "anim_" + key.rsplit("/", 2)[-2] + ".fbx")
            if key not in done:
                export(key, af, unreal.AnimSequenceExporterFBX(), anim=True)
                done.add(key)
            rec["anim"] = af
            rec["ok"] = True
        except Exception as e:                                          # noqa: BLE001
            rec = {"ok": False, "error": f"{type(e).__name__}: {e}",
                   "trace": traceback.format_exc()[-1500:]}
        R["items"][it["look"]] = rec
        unreal.log(f"CITYGEN_LOOKS {it['look']} {rec.get('ok')}")
    R["ok"] = all(r.get("ok") for r in R["items"].values())


try:
    main()
except Exception:                                                       # noqa: BLE001
    R["error"] = traceback.format_exc()
with open(JOB["result"], "w", encoding="utf-8") as f:
    json.dump(R, f, indent=1)
print("CITYGEN_UE_DONE " + json.dumps({"ok": R["ok"]}))
if "-run=" not in unreal.SystemLibrary.get_command_line().lower():
    # (the full editor, which a skeletal mesh's FBX export needs: it quits itself)
    unreal.SystemLibrary.quit_editor()
