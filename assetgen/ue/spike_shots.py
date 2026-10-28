"""assetgen AG0 spike shots, run inside the Unreal 5.8 editor with a renderer:

    UnrealEditor PROJECT.uproject "-ExecCmds=py assetgen/ue/spike_shots.py" -unattended
        -RenderOffscreen

with $ASSETGEN_UE_JOB naming a job file ({"shots": dir, "result", "width"}). It opens
/Game/AssetgenSpike/Maps/Spike (made by spike_import.py), renders views of the spike
buildings (high-resolution screenshots from camera actors, as M15's check does), and quits.
The script runs as a generator on the editor's tick (rendering needs frames).
"""

import json
import os
import time
import traceback

import unreal

JOB = json.load(open(os.environ["ASSETGEN_UE_JOB"], encoding="utf-8"))
T0 = time.time()
RES = {"ok": False, "shots": []}
# (name, eye, target, horizontal field of view): citygen meters, the spike level's layout
VIEWS = [
    ("tower", (-560.0, -820.0, 120.0), (-50.0, 0.0, 180.0), 45.0),
    ("tower_base", (-48.0, -62.0, 8.0), (-10.0, -20.0, 22.0), 80.0),
    ("shopfront_row", (52.0, -75.0, 3.0), (72.0, -45.0, 6.0), 80.0),
    ("shanty_stack", (96.0, -68.0, 4.0), (110.0, -42.0, 5.0), 80.0),
    ("foliage_test", (80.0, -32.0, 5.0), (90.0, -15.0, 6.0), 70.0),
    ("tower_glass", (-20.0, -45.0, 60.0), (0.0, -21.0, 66.0), 60.0),
]


def log(msg):
    unreal.log(f"assetgen shots: {msg} ({time.time() - T0:.1f} s)")


def ue(x, y, z):
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0)


def wait(seconds):
    t = time.time()
    while time.time() - t < seconds:
        yield


def run():
    unreal.SystemLibrary.execute_console_command(None, "Slate.bAllowThrottling 0")
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not les.load_level("/Game/AssetgenSpike/Maps/Spike"):
        raise RuntimeError("no spike level (run spike_import.py first)")
    WPL = unreal.WorldPartitionBlueprintLibrary
    WPL.load_actors([d.guid for d in WPL.get_actor_descs()])
    yield from wait(5.0)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    out = JOB["shots"]
    os.makedirs(out, exist_ok=True)
    w = int(JOB.get("width") or 2560)
    for name, eye, target, fov in VIEWS:
        cam = eas.spawn_actor_from_class(unreal.CameraActor, ue(*eye), transient=True)
        cam.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(ue(*eye), ue(*target)),
                               False)
        cam.camera_component.set_editor_property("field_of_view", fov)
        path = os.path.join(out, f"unreal_{name}.png")
        if os.path.exists(path):
            os.remove(path)
        unreal.AutomationLibrary.finish_loading_before_screenshot()
        yield from wait(3.0)
        t = time.time()
        unreal.AutomationLibrary.take_high_res_screenshot(w, w * 9 // 16, path, cam)
        while not os.path.exists(path) and time.time() - t < 300:
            yield
        yield from wait(1.0)
        eas.destroy_actor(cam)
        if os.path.exists(path):
            RES["shots"].append(path)
            log(f"wrote {path} in {time.time() - t:.1f} s")
    RES["ok"] = len(RES["shots"]) == len(VIEWS)


GEN = run()
HANDLE = None
BUSY = [False]


def finish():
    RES["total_s"] = round(time.time() - T0, 1)
    with open(JOB["result"], "w", encoding="utf-8") as f:
        json.dump(RES, f, indent=1)
    print("ASSETGEN_UE_DONE " + json.dumps({"ok": RES["ok"], "total_s": RES["total_s"]}))
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
    except Exception:
        RES["error"] = traceback.format_exc()
        unreal.log_error(RES["error"])
        finish()
    finally:
        BUSY[0] = False


HANDLE = unreal.register_slate_post_tick_callback(tick)
