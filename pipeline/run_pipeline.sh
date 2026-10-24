#!/bin/sh
# Corporate Core pipeline: cleanup -> plan -> 2D map -> 3D isometric render
# usage: ./run_pipeline.sh [input.svg | maps_dir] [output_dir]
#        default input: newest maps/corporate_core_v*.svg ; default output: out
# needs: Python deps in <repo>/.venv (pip install -r requirements.txt), else python3 on PATH;
#        Blender 4.2+ (BLENDER=/path/to/blender, else `blender` on PATH, else /Applications/Blender*.app)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
PY="$HERE/../.venv/bin/python"; [ -x "$PY" ] || PY=python3
SRC=${1:-$HERE/../maps}
[ -d "$SRC" ] && SRC=$("$PY" "$HERE/map_version.py" latest "$SRC")
IN=$(cd "$(dirname "$SRC")" && pwd)/$(basename "$SRC")
OUT=${2:-out}; mkdir -p "$OUT"; cd "$OUT"
[ -n "$BLENDER" ] || BLENDER=$(command -v blender || ls -d /Applications/Blender*.app/Contents/MacOS/Blender 2>/dev/null | tail -1)
echo "input: $IN"

# cleanup never overwrites the input: if it changed anything, the result becomes the next patch version
"$PY" "$HERE/cleanup_svg.py" "$IN" cleaned.svg
if cmp -s "$IN" cleaned.svg; then
  rm cleaned.svg; echo "cleanup: no changes"
else
  NEXT=$("$PY" "$HERE/map_version.py" next "$IN")
  [ -e "$NEXT" ] && { echo "cleanup: $NEXT already exists, not overwriting (cleaned result left in $PWD/cleaned.svg)"; exit 1; }
  mv cleaned.svg "$NEXT"; IN=$NEXT; echo "cleanup: wrote $IN"
fi

"$PY" "$HERE/svg_to_plan.py" "$IN" .        # geometry.json + corporate_core_plan.json (Unreal)
"$PY" "$HERE/render_map.py" "$IN"           # map_2d.png
"$PY" "$HERE/prep_render.py"                # render_geo.json
"$BLENDER" -b --factory-startup -P "$HERE/blender_render.py" -- render_geo.json "$PWD/isometric.png" 1600 1200 16
