# Corporate Core city pipeline

Inkscape SVG in, cleaned SVG + Unreal plan + 2D map + 3D render out.

    ./run_pipeline.sh                    # newest maps/corporate_core_v*.svg -> out/
    ./run_pipeline.sh my_drawing.svg out

Loop: trace in Inkscape, save as a new version -> run pipeline (if cleanup changes anything it saves
the next patch version, e.g. v1.0 -> v1.0.1) -> keep editing the newest version -> run again.
The cleanup is idempotent: running it on an already-clean file changes nothing.

Cleanup rules (cleanup_svg.py):
- building/landmark layer: open 3-point paths and closed 4-point paths become exact rectangles;
  angles within 6 degrees of a 45-degree multiple are snapped. Other shapes are left alone.
- path with id "megatower": rebuilt as a symmetric three-armed shape (re-fitted from its current
  size and position each run), moved to the landmark layer, height label 480 if unlabeled.

Conventions: 1 SVG unit = 1 m. Road width = stroke width. Building height = numeric object label.
