"""Render chosen blockout views again from a saved city.blend, at another width (Blender 5.2).

    blender -b --factory-startup -P citygen/blender/rerender.py -- BLOCKOUT_DIR TO_DIR \
        --width 7680 [--samples 16] VIEW [VIEW ...]

BLOCKOUT_DIR holds `city.blend` and `blockout_plan.json` (a `citygen blockout` output). VIEW
names a render of `build.views`: `top`, `iso_city`, `iso_<district>` or `street_<n>`; each is
written as TO_DIR/render_<VIEW>.jpg with the same camera as the build, `--width` pixels wide
(README images use 7680). `citygen rerender` runs it.
"""

import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402  (citygen/blender/build.py; its main() only runs as a script)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) < 3:
        raise SystemExit("usage: blender -b -P rerender.py -- BLOCKOUT_DIR TO_DIR "
                         "[--width W] [--samples N] VIEW [VIEW ...]")
    src, to = os.path.abspath(argv[0]), os.path.abspath(argv[1])
    width, samples, names = 7680, 16, []
    rest = argv[2:]
    i = 0
    while i < len(rest):
        if rest[i] in ("--width", "--samples"):
            if rest[i] == "--width":
                width = int(rest[i + 1])
            else:
                samples = int(rest[i + 1])
            i += 2
            continue
        names.append(rest[i])
        i += 1
    with open(os.path.join(src, "blockout_plan.json"), encoding="utf-8") as f:
        plan = json.load(f)
    by_name = {v[0]: v for v in build.views(plan, 1600)}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise SystemExit(f"unknown views {missing}; known: {sorted(by_name)}")
    bpy.ops.wm.open_mainfile(filepath=os.path.join(src, "city.blend"))
    scene = bpy.context.scene
    build.setup_render(scene, samples)
    os.makedirs(to, exist_ok=True)
    done = [build.render_view(scene, by_name[n], os.path.join(to, f"render_{n}.jpg"), width)
            for n in names]
    print("CITYGEN_RERENDER_DONE " + json.dumps({"files": done, "width": width}))


main()
