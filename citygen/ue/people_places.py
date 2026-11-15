"""LG4: the people library's clips for life at places (stdlib and `unreal` only), run in the
project's editor after the library is in place (`citygen/unreal_people.py`,
`ensure_place_clips`):

    UnrealEditor PROJECT.uproject -ExecCmds="py citygen/ue/people_places.py" -RenderOffscreen
        (env CITYGEN_UE_JOB: {result, manifest, hash, lib_hash, content, gas_mesh, clips,
         groups})

Epic's Game Animation Sample clips the places need (a bench's sitting loop, a few standing
idle breaks for talking, smoking, eating), copied into the project from the user's sample
first (the library's `migrate`), retargeted onto each clip group's body skeleton with the
library's own retargeter (`<content>/Anim/<group>/RTG_GasToBody_<library hash>`), their
notifies stripped, made in place as the library's walks and idles are; written to the
manifest (`Saved/CityGenPeople/places.json`): per group, per clip, its path. The library's own
assets and hash are untouched, so its cache stays valid; every clip made keeps the places'
hash as metadata (`cg.places`), and a run with the same hash keeps it.
"""

import json
import os
import time
import traceback

import unreal

JOB = json.load(open(os.environ["CITYGEN_UE_JOB"], encoding="utf-8"))
HASH = JOB["hash"]
EAL = unreal.EditorAssetLibrary
R = {"ok": False, "hash": HASH, "groups": {}, "missing": []}
T0 = time.time()


def log(msg):
    unreal.log(f"CITYGEN_PLACES {msg}")


def save_result():
    R["wall_in_editor_s"] = round(time.time() - T0, 1)
    with open(JOB["result"], "w", encoding="utf-8") as f:
        json.dump(R, f, indent=1, default=str)


def meta(asset, key="cg.places"):
    try:
        return EAL.get_metadata_tag(asset, key) or ""
    except Exception:                                               # noqa: BLE001
        return ""


def in_place(seq):
    """The library's own rule (people_library.in_place): the root still at every key, the
    pelvis taking the root's height and turn, any travel dropped."""
    AL = unreal.AnimationLibrary
    n = AL.get_num_keys(seq) if hasattr(AL, "get_num_keys") else AL.get_num_frames(seq)
    roots = [AL.get_bone_pose_for_frame(seq, "root", k, False) for k in range(n)]
    pelvis = [AL.get_bone_pose_for_frame(seq, "pelvis", k, False) for k in range(n)]
    x0, y0 = roots[0].translation.x, roots[0].translation.y
    xn, yn = roots[-1].translation.x, roots[-1].translation.y
    pos, rot = [], []
    for k in range(n):
        g = unreal.MathLibrary.compose_transforms(pelvis[k], roots[k])
        f = k / max(1, n - 1)
        t = g.translation
        pos.append(unreal.Vector(t.x - (x0 + (xn - x0) * f), t.y - (y0 + (yn - y0) * f), t.z))
        rot.append(g.rotation)
    ctrl = seq.get_editor_property("controller")
    ctrl.set_bone_track_keys("pelvis", pos, rot, [unreal.Vector(1, 1, 1)] * n, False)
    ctrl.set_bone_track_keys("root", [unreal.Vector(0, 0, 0)] * n, [unreal.Quat()] * n,
                             [unreal.Vector(1, 1, 1)] * n, False)
    for prop, v in (("force_root_lock", False), ("enable_root_motion", False)):
        try:
            seq.set_editor_property(prop, v)
        except Exception:                                           # noqa: BLE001
            pass
    log(f"in place {seq.get_name()}: {n} keys, travel {round(xn - x0, 1)}, {round(yn - y0, 1)} "
        f"cm, pelvis z {round(pos[0].z, 1)}")
    return {"keys": n, "travel_cm": [round(xn - x0, 1), round(yn - y0, 1)],
            "pelvis_z_cm": round(pos[0].z, 1)}


def group_clips(key, rec):
    folder = f"{JOB['content']}/Anim/{key}"
    have = {k: f"{folder}/A_place_{k}" for k in JOB["clips"]}
    if all(EAL.does_asset_exist(p) and meta(unreal.load_asset(p)) == HASH for p in have.values()):
        log(f"{key}: kept")
        return {k: {"anim": p} for k, p in have.items()}
    rtg = unreal.load_asset(rec["retargeter"])
    if rtg is None:
        raise RuntimeError(f"no retargeter {rec['retargeter']} (the library's)")
    src_mesh = unreal.load_asset(JOB["gas_mesh"])
    body = unreal.load_asset(rec["body"])
    if src_mesh is None or body is None:
        raise RuntimeError(f"the sample's mannequin {JOB['gas_mesh']} or the body {rec['body']} "
                           "is not in the project")
    out = {}
    for k, src in JOB["clips"].items():
        seq = unreal.load_asset(src)
        if seq is None:
            R["missing"].append(src)
            raise RuntimeError(f"no clip {src} in the project (the sample's, migrated first)")
        dst = have[k]
        if EAL.does_asset_exist(dst):
            EAL.delete_asset(dst)
        made = unreal.IKRetargetBatchOperation.duplicate_and_retarget(
            [EAL.find_asset_data(src)], src_mesh, body, rtg, search="", replace="",
            prefix="", suffix=f"_{key}_place", target_path=folder)
        got = [str(x.get_editor_property("package_name")) for x in made]
        got = [g for g in got if unreal.load_asset(g) and
               isinstance(unreal.load_asset(g), unreal.AnimSequence)]
        if not got:
            raise RuntimeError(f"the retarget of {src} made nothing")
        EAL.rename_asset(got[0], dst)
        seq2 = unreal.load_asset(dst)
        try:
            unreal.AnimationLibrary.remove_all_animation_notify_tracks(seq2)
        except Exception as e:                                      # noqa: BLE001
            log(f"notifies of {k}: {e}")
        info = in_place(seq2)
        info["length_s"] = round(unreal.AnimationLibrary.get_sequence_length(seq2), 3)
        EAL.set_metadata_tag(seq2, "cg.places", HASH)
        EAL.save_loaded_asset(seq2, only_if_is_dirty=False)
        out[k] = {"anim": dst, **info}
        log(f"{key} {k}: {dst} {info}")
        yield
    return out


def run():
    yield
    unreal.AssetRegistryHelpers.get_asset_registry().wait_for_completion()
    try:
        for key, rec in sorted(JOB["groups"].items()):
            res = yield from group_clips(key, rec)
            R["groups"][key] = res
        man = {"hash": HASH, "lib_hash": JOB["lib_hash"], "clips": list(JOB["clips"]),
               "groups": R["groups"]}
        os.makedirs(os.path.dirname(JOB["manifest"]), exist_ok=True)
        with open(JOB["manifest"], "w", encoding="utf-8") as f:
            json.dump(man, f, indent=1)
        R["ok"] = True
    except Exception as e:                                          # noqa: BLE001
        R["error"] = f"{type(e).__name__}: {e}"
        R["trace"] = traceback.format_exc()[-3000:]
        log(f"FAILED: {e}")
    save_result()


GEN = run()
HANDLE = None
BUSY = [False]


def finish():
    save_result()
    print("CITYGEN_UE_DONE " + json.dumps({"ok": R["ok"]}))
    unreal.unregister_slate_post_tick_callback(HANDLE)
    unreal.SystemLibrary.quit_editor()


def tick(dt):
    if BUSY[0]:
        return
    BUSY[0] = True
    try:
        next(GEN)
    except StopIteration:
        finish()
    except Exception:                                               # noqa: BLE001
        R["error"] = traceback.format_exc()
        unreal.log_error(R["error"])
        finish()
    finally:
        BUSY[0] = False


HANDLE = unreal.register_slate_post_tick_callback(tick)
