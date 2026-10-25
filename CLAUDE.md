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

## City generator (citygen)

`docs/citygen_scope.md` is the spec for citygen, the prompt-to-city layout generator that is
replacing hand tracing (milestones M0 to M7, built in cloud sessions). Hard rule: citygen makes no
API calls and no network calls, in development or in the final product, and has no LLM SDK
dependency. The prompt-to-spec step is done by a Claude Code session through the repo's `citygen`
skill; that session may start other Claude sessions or subagents.

M0 is in place: package `citygen/` (spec schema, archetype presets, fill-defaults, city model
schema, schematic renderer), skill `.claude/skills/citygen/SKILL.md`, examples in
`docs/progress/M0/`, tests in `tests/` (`.venv/bin/python -m pytest`). Commands:
`.venv/bin/python -m citygen spec validate|render|schema ...` and `... model schema`. After
changing `citygen/spec.py` or `citygen/model.py`, regenerate `citygen/schemas/*.json` with the
schema commands (a test checks they match).

M1a (water and districts) is in place: `.venv/bin/python -m citygen build <spec.json> <out_dir>`
writes `city_model.json` (coast, rivers, delta branches, islands, landmasses, district polygons,
separation channels, inner waterways, quays), `preview_map.png`, `report.json` and
`report.txt`, and exits 1 when a check fails. Stages live in `citygen/hydro.py`,
`districts.py`, `waterways.py`; checks in `checks.py` (placement rules in `relations.py`);
driver in `build.py`. M1a2 (visual-quality pass) made it organic: warped power-diagram
districts with curved boundaries, meandering rivers and separation channels, a
`water.boundary_water_share` budget for `water_preferred`, fan-shaped deltas with named marsh
or park open land instead of orphan wedges, port slips, marinas, sparse canal trees.
Sample builds: `docs/progress/M1a2/` (before/after against `docs/progress/M1a/`; the sample
specs now live in M1a2).

M1b (primary roads) is in place: the same build reserves megasite ground (`megasites.py`) and
lays highways by `highways.pattern` with exits, avenues and bridges (`roads.py`: 25 m cost
raster, A* routing, straight crossings at the narrowest point, fillet curves), writes
`road_nodes`, `road_segments` and `bridges` into the model, and runs eight road checks.
Builds are byte-identical across machines (x86 and ARM): the generator uses `dmath.py`
(deterministic sin, cos, exp, log, atan2) instead of numpy/libm transcendentals, every stage
hands on coordinates on the 0.01 m grid, and decisions only see exact measures and
grid-snapped GEOS output (`geom.area`, `length`, `inter`, `diff`, `union`; the district
contours come from the in-repo `marching.py`). `tests/data/golden_hashes.json` holds the sha256
of each sample `city_model.json` (pytest asserts them; `tests/test_determinism.py` injects
ULP noise into the district search). `citygen build ... --trace FILE` hashes every stage and
`citygen trace diff A B` finds the first one where two machines part
(`docs/progress/M1b_det/`). Variants run in worker processes (`CITYGEN_WORKERS`, 1 = one
process); the result does not depend on it. Sample builds: `docs/progress/M1b/`.

M2 (local streets, blocks, lots) is in place: the same build lays local streets by archetype
pattern (`streets.py`: frame of frontage and boundary streets, promenades and quay roads, then
rotated grids, superblocks, organic growth, loops, campus loops, radial rings, reserve service
roads, infill and alleys, footbridges; exact noding), junctions with corner fillets, signals,
crosswalks, sidewalks, the lane graph and the walkway graph (`junctions.py`), blocks, OBB-split
lots with frontage and open space (`blocks.py`), driver `local.py`, 13 checks in
`street_checks.py`, and `preview_detail.png` (four 400 m street-level insets,
`preview_detail.py`). M2 stages run in `geom.canonical()` (pointwise grid rounding,
fixed-precision overlays); never let set or dict order of strings reach the model (string
hashes change per process; a test builds under two `PYTHONHASHSEED` values). GEOS on macOS is
built against libc++, on Linux against libstdc++, and their `std::sort` orders ties
differently: never let the order of GEOS output (parts, STRtree hits, a many-input
`union_all`) reach a decision (`geom.union` merges in its own fixed order; normalize or sort
otherwise). Emulated aarch64 Linux does not catch this; a GEOS rebuilt with clang and libc++
does (`docs/progress/M2/README.md`). Sample builds: `docs/progress/M2/`. M3 (buildings) is
next.

### Rules for cloud sessions building citygen milestones

- **Work-in-progress images:** after each major sub-step (and at least every hour or so), build
  the sample cities, commit their preview images to `docs/progress/<milestone>/wip/<NN>_<step>/`
  and push to the session branch, so Swagnik can watch progress on GitHub before the PR exists.
  Keep only images and short notes there; overwrite nothing from earlier milestones.
- **Root `README.md`:** when the milestone PR is ready, update the Progress table and the
  "Latest maps" images to point at the new milestone's previews.

## Working preferences

- Execute tasks end to end and ask for the access you need, rather than handing back scripts to run.
- No em dashes in any output.
- No backup copies before edits (the folder is under git).
- Write math as rendered LaTeX.
- Summary/deck bullets: noun-phrase topics rather than verb-led phrasing.
