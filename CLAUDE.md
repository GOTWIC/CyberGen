# Nyxllor

A Cyberpunk 2077-inspired open-city game in Unreal Engine 5, at roughly a quarter of Night City's scale:
walkable streets, NPC crowds and traffic, optional combat and dialogue, no story. The owner (Swagnik)
does art direction and layout; Claude does code, tooling, procedural generation, and most asset work.
Assets can be built with Claude (Blender, PCG) or sourced (Fab, MetaHuman) where that makes more sense
(characters, clothing, weapons, cars).

## Current stage: layout of the first district (Corporate Core)

- `reference/corporate_core_reference.png`: AI-generated concept map of the district. It is drawn in a
  planometric style: the ground plan is true shape (seen straight down) and buildings rise straight up
  the screen. Buildings in this district sit on a 45-degree grid.
- `maps/corporate_core_v<version>.svg`: the working file is the highest version (compared numerically,
  so v1.10 is newer than v1.9). Swagnik traces the reference in Inkscape 1.4 and saves new versions
  himself; Claude's cleanup output becomes the next patch version (v1.0 traced -> v1.0.1 cleaned), and
  he keeps editing from there. Never overwrite or delete an existing version, and never replace one
  with a fresh export, so his layers, labels and reference image survive. All versions are committed.
  No other backup copies.
- The island is about 1019 x 1059 m. Canvas is 1200 x 1200, 1 SVG unit = 1 meter.

### SVG conventions (layers matched by name, case and spaces ignored)

| Layer | Meaning |
|---|---|
| reference | embedded concept image, locked, ignored by the pipeline |
| coast | one closed path; extra subpaths are holes (canals / water pockets at sea level) |
| highway, avenue, street, elevated road | road centerlines; stroke width = road width in meters; closed paths are loop roads; fill ignored |
| building, landmark | footprints. Open 3-point path = two traced base edges of a rectangle (cleanup completes it). Closed path = exact footprint. Height = numeric object label (e.g. `140`); unlabeled gets an automatic height |
| water, park, plaza, pier | filled areas (water layer = street-level pools, not canals) |

Road widths in use: highway 20 to 24, avenue 16 to 20, street 10 to 12. There is no `avenue` layer in
the SVG yet; add one between highway and street if needed.

## Pipeline (`pipeline/`)

`./pipeline/run_pipeline.sh` (newest `maps/corporate_core_v*.svg` into `out/`; an explicit
`input.svg` and output dir can be passed) runs, in order:

1. `cleanup_svg.py`: idempotent cleanup (a second run changes nothing).
   - building/landmark: open 3-point and closed 4-point paths become exact rectangles; angles within
     6 degrees of a 45-degree multiple are snapped; other shapes untouched; already-clean shapes untouched.
   - the path with id `megatower` is rebuilt as a symmetric three-armed shape (arms 120 degrees apart, one
     pointing north, straight cut ends, identical concave circular-arc edges), re-fitted from its current
     size and position each run, kept on the landmark layer, height label 480 if unlabeled.
   - writes with lxml so Inkscape structure is preserved.
   If cleanup changed anything, `run_pipeline.sh` saves the result as the next patch version
   (`map_version.py`) and runs the rest on it; it refuses to overwrite an existing file. An unchanged
   file produces no new version.
2. `svg_to_plan.py`: writes `geometry.json` (render geometry) and `corporate_core_plan.json`
   (box/cylinder primitives for Unreal; plan coords x=east, y=north, meters, origin at canvas center).
3. `render_map.py`: `map_2d.png`, plan alone and plan over the reference image.
4. `prep_render.py` + `blender_render.py`: isometric Cycles render from the south (`isometric.png`).
   Needs Blender. On the M4 Mac it is Blender 5.2 at `/Applications/Blender 5.2.app`; the script finds
   `/Applications/Blender*.app` automatically, or set `BLENDER=/path/to/blender`.

Python deps: `requirements.txt` (shapely, svgelements, lxml, matplotlib, pillow), installed in `.venv/`
(Python 3.13). `run_pipeline.sh` uses `.venv/bin/python` automatically.

## Unreal

- Project: C++ First Person template, created on the M4 Mac. Heavy work (City Sample, dense city) should
  move to the Windows PC (RTX 4070 Ti, 12 GB). UE 5.8 ships an official Unreal MCP server and an updated
  City Sample built with PCG (the PCG Primitives plugin); that is the intended route for Claude to drive
  the editor directly.
- `unreal/build_greybox_unreal.py`: editor Python script. Put it plus `corporate_core_plan.json` in
  `<UnrealProject>/Greybox/`, open a level, Tools > Execute Python Script. Clears and rebuilds its own
  actors (tag `CorporateCoreGreybox`), Ctrl+Z undoes a run. Buildings are currently oriented boxes, so
  the megatower becomes its bounding box; true footprint meshes are a planned upgrade.
- Keep gameplay logic in C++ where reasonable.

## Known open items

- Tracing still to do: avenues, streets, plaza, parks, piers, elevated roads (need ramps/supports),
  megatower spine (north of the tower, stepped heights), building height labels.
- path15 (west), path17 and path18 (south pills) are custom shapes left as drawn; the south pair could
  be mirrored for symmetry.
- Unreal ground is built from 4 m strips; replace with a real mesh later.

## Working preferences

- Execute tasks end to end and ask for the access you need, rather than handing back scripts to run.
- No em dashes in any output.
- No backup copies before edits (the folder is under git).
- Write math as rendered LaTeX.
- Summary/deck bullets: noun-phrase topics rather than verb-led phrasing.
