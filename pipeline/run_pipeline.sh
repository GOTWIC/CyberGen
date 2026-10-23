#!/bin/sh
# Corporate Core pipeline: cleanup (in place) -> plan -> 2D map -> 3D isometric render
# usage: ./run_pipeline.sh input.svg [output_dir]
# needs: Python deps in <repo>/.venv (pip install -r requirements.txt), else python3 on PATH;
#        Blender 4.2+ (BLENDER=/path/to/blender, else `blender` on PATH, else /Applications/Blender*.app)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
IN=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
OUT=${2:-out}; mkdir -p "$OUT"; cd "$OUT"
PY="$HERE/../.venv/bin/python"; [ -x "$PY" ] || PY=python3
[ -n "$BLENDER" ] || BLENDER=$(command -v blender || ls -d /Applications/Blender*.app/Contents/MacOS/Blender 2>/dev/null | tail -1)

# cleanup writes back into the input only when something changed, so a clean file is never touched
"$PY" "$HERE/cleanup_svg.py" "$IN" cleaned.svg
if cmp -s "$IN" cleaned.svg; then rm cleaned.svg; echo "cleanup: no changes"; else mv cleaned.svg "$IN"; echo "cleanup: updated $IN"; fi

"$PY" "$HERE/svg_to_plan.py" "$IN" .        # geometry.json + corporate_core_plan.json (Unreal)
"$PY" "$HERE/render_map.py" "$IN"           # map_2d.png
"$PY" "$HERE/prep_render.py"                # render_geo.json
"$BLENDER" -b --factory-startup -P "$HERE/blender_render.py" -- render_geo.json "$PWD/isometric.png" 1600 1200 16
