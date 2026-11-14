"""LG1: what the people library takes from Epic's Game Animation Sample (run in the editor of
the user's Game Animation Sample project, read only: `-userdir=` outside it, nothing saved).

    UnrealEditor-Cmd GAS.uproject -run=pythonscript -script=citygen/ue/people_gas.py
        -userdir=<scratch>   (env CITYGEN_GAS_JOB: a JSON job file)

The job names the packages the library needs (the walks, the idles, the mannequin's mesh and
skeleton); the script writes the closure of their hard references inside /Game (with each
package's file on disk, its class and size) to the job's `out`, so the venv side copies exactly
those files into the city project (`citygen/unreal_people.py`, `migrate`). Notifies and
other Blueprint classes the clips reference are listed apart (`skipped`): the library strips
the clips' notifies after the copy, so the sample's footstep Blueprints and their sounds
never come along.
"""

import json
import os

import unreal

JOB = json.load(open(os.environ["CITYGEN_GAS_JOB"], encoding="utf-8"))
AR = unreal.AssetRegistryHelpers.get_asset_registry()
OPTS = unreal.AssetRegistryDependencyOptions(include_soft_package_references=False,
                                             include_hard_package_references=True,
                                             include_searchable_names=False,
                                             include_soft_management_references=False,
                                             include_hard_management_references=False)
# (classes whose packages are not followed: what the clips' notifies and curves name, the
# sample's own gameplay; the library strips them)
SKIP_CLASSES = {"Blueprint", "BlueprintGeneratedClass", "SoundWave", "SoundCue", "MetaSoundSource",
                "NiagaraSystem", "World", "AnimBlueprint", "ControlRigBlueprint",
                "PoseSearchDatabase", "PoseSearchSchema", "ChooserTable"}
KEEP_FIRST = set(JOB["packages"])


def asset_class(pkg):
    data = AR.get_assets_by_package_name(pkg)
    if not data:
        return None
    return str(data[0].asset_class_path.asset_name)


def main():
    todo = list(JOB["packages"])
    seen, keep, skipped = set(), [], []
    content = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        if not p.startswith("/Game/"):
            continue
        cls = asset_class(p)
        if cls is None:
            skipped.append({"package": p, "why": "not found"})
            continue
        if cls in SKIP_CLASSES and p not in KEEP_FIRST:
            skipped.append({"package": p, "class": cls})
            continue
        rel = p[len("/Game/"):]
        f = None
        for ext in (".uasset", ".umap"):
            q = os.path.join(content, rel + ext)
            if os.path.isfile(q):
                f = q
                break
        rec = {"package": p, "class": cls, "file": f,
               "bytes": os.path.getsize(f) if f else 0}
        side = os.path.splitext(f)[0] + ".uexp" if f else None
        if side and os.path.isfile(side):
            rec["uexp"] = side
        keep.append(rec)
        for d in AR.get_dependencies(p, OPTS) or []:
            d = str(d)
            if d not in seen:
                todo.append(d)
    out = {"content": content, "keep": sorted(keep, key=lambda r: r["package"]),
           "skipped": sorted(skipped, key=lambda r: r["package"]),
           "engine": unreal.SystemLibrary.get_engine_version()}
    with open(JOB["out"], "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    unreal.log(f"CITYGEN_GAS_DONE keep={len(keep)} skipped={len(skipped)}")


main()
