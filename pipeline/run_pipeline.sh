#!/bin/sh
# Corporate Core pipeline: cleanup -> plan -> 2D map -> 3D isometric render
# usage: ./run_pipeline.sh input.svg [output_dir]
# needs: pip install shapely svgelements lxml matplotlib pillow ; Blender 4.2+ (set BLENDER=/path/to/blender)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
IN=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
OUT=${2:-out}; mkdir -p "$OUT"; cd "$OUT"
python3 "$HERE/cleanup_svg.py" "$IN" corporate_core.svg      # cleaned, Inkscape-editable SVG (keep working from this)
python3 "$HERE/svg_to_plan.py" corporate_core.svg .          # geometry.json + corporate_core_plan.json (Unreal)
python3 "$HERE/render_map.py" corporate_core.svg             # map_2d.png
python3 "$HERE/prep_render.py"                               # render_geo.json
${BLENDER:-blender} -b --factory-startup -P "$HERE/blender_render.py" -- render_geo.json "$PWD/isometric.png" 1600 1200 16
