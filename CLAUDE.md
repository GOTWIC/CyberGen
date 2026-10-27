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
- citygen's blockout exports `city.usdc` (whole city) and one `tiles/<tile>.glb` per 256 m tile
  (custom properties as glTF extras) for World Partition style imports, plus
  `unreal/corporate_core_plan.json`, which `build_greybox_unreal.py` reads unchanged.
- Keep gameplay logic in C++ where reasonable.

## Known open items

- Tracing still to do: avenues, streets, plaza, parks, piers, elevated roads (need ramps/supports),
  megatower spine (north of the tower, stepped heights), building height labels.
- path15 (west), path17 and path18 (south pills) are custom shapes left as drawn; the south pair could
  be mirrored for symmetry.
- Unreal ground is built from 4 m strips; replace with a real mesh later.

## City generator (citygen)

`docs/citygen_scope.md` is the spec for citygen, the prompt-to-city layout generator that is
replacing hand tracing (milestones M0 to M7, built in cloud sessions and locally). Hard rule:
citygen makes no API calls and no network calls, in development or in the final product, and
has no LLM SDK dependency. The prompt-to-spec step is done by a Claude Code session through
the repo's `citygen` skill; that session may start other Claude sessions or subagents.

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
does (`docs/progress/M2/README.md`). Sample builds: `docs/progress/M2/`.

M3 (buildings) is in place: the same build fills every lot (`buildings.py`: a program per
archetype with setbacks by frontage class, podium towers, slabs, megabuildings with atriums and
stepped tiers, courtyard and perimeter blocks, terraced, shopfront rows, shanty stacks,
warehouses with docks, container yards, villas, labs, hangars; facade on the main frontage,
heights from a district height field within `height_m`, capped near spaceport flight cones;
ground-floor units 4 to 12 m with uses, entrances, rooftop items, green roofs), builds
landmarks and complexes (`complexes.py`: three-armed megatower, spires, arcology, wheel; twin
towers, clusters, megabuilding campuses, campuses, bridged pairs, straddle buildings),
skybridges (`skybridges.py`) and the megasite generators (`sites.py`), with shape helpers in
`massing.py` and the driver `buildout.py` (three rounds of worker jobs: landmarks and
complexes per district, lots in chunks of 300, skybridges and rows per district; the M1/M2
checks run on the M2 model meanwhile, the walkway graph is rechecked at the end). The model
gains buildings, properties, skybridges, site elements and `Mass.shape`; 13 checks in
`building_checks.py` (44 in all); previews `preview_heights.png` and `preview_massing.png`
(`preview_massing.py`). Any shape decision is an exact predicate on grid geometry or plain
arithmetic; oriented boxes come from `massing.obb_angle`, never GEOS's minimum rotated
rectangle. Sample builds: `docs/progress/M3/`.

M3p (polish of M3) is in place: megablock megabuildings are a podium with a court open to the
sky and separate towers on it (at least 16 m apart, stepped heights, mid and crown setbacks,
open decks between them), joined to neighbors by podium-level open decks
(`skybridges._podium_decks`); M2 picks each merged lot group by trying candidates with M3's
own complex builder (`complexes.probe`, masses only, on a district context built from M2's
roads, junctions and water in `blocks._probe_ctx`), so complexes stand where they were grouped;
straddle buildings also span a canal and its quay roads at the navigable clearance (the
footprint check verifies every road and water body a span crosses, `span_crosses`); heights
rise along the boulevard through a district's center (`buildings.boulevards`); and
`roads._merge_degree2` no longer breaks when a smoothed joint collapses or drifts off its
node (`roads._on_ends`). Sample builds: `docs/progress/M3p/`.

M4 (Blender blockout) is in place: `.venv/bin/python -m citygen blockout <city_model.json>
<out_dir>` (or `citygen build ... --blockout`) makes the blockout plan in the venv
(`citygen/blockout.py`: every coordinate, in canonical geometry, its sha256 in
`tests/data/golden_hashes.json` under `blockout_plans`; land and water clipped to 256 m tiles,
streets joined per district, category and tile, one object per building, skybridge, deck and
megasite element group), then runs Blender (`citygen/blender/build.py`, stdlib and bpy only,
it only triangulates and draws): `city.blend`, `city.usdc`, `tiles/<tile>.glb`, EEVEE renders
(`render_top.jpg`, `render_iso_city.jpg`, `render_iso_<district>.jpg`, `render_street_<n>.jpg`), then reopens the
.blend in a fresh Blender and checks its objects, tiles and renders (`blockout_report.txt`).
`citygen/exports.py` writes the layered `map_2d.svg` (readable by `pipeline/svg_to_plan.py`)
and `map_2d.png`, `unreal/corporate_core_plan.json` for the greybox script, `graphs.json`,
`tiles.json` and `props.csv`. `citygen rerender <blockout_dir> VIEW... [--width 7680] [--to DIR]`
(`citygen/blender/rerender.py`) renders chosen views (`top`, `iso_city`, `iso_<district>`,
`street_<n>`) again from the saved `city.blend` with the build's cameras. The Blender test skips when Blender is missing. Sample builds:
`docs/progress/M4/`.

M5 (transit) is in place: the same build runs `citygen/transit.py` after the buildings (stops
resolved to junctions, nexus platforms or sites; elevated rail and monorail routed on the road
graph, maglev, sky tubes and metro on a 15 m raster; curves fitted at 1.15 times the mode's
minimum radius with obstacle-checked arcs; a height profile between lower bounds (water,
road decks, roofs) and upper bounds (tower portals); stations with stairs, elevators,
canopies and walkways split onto the sidewalks; decks, tubes and supports in medians or at
the curbs) and ten transit checks (`citygen/transit_checks.py`), and writes
`preview_transit.png`. Route order matters for the fast modes: the spec, not the code, fixes
a line that turns back. Sample builds: `docs/progress/M5/`.

M6 (props and vegetation) is in place: the build ends with `citygen/props.py` (street
lights, wall lights where a sidewalk is too narrow, signals, bus shelters, hydrants, trash
cans, bollards, benches, kiosks, stalls, parked cars, boats, barriers, railings, cables,
signs, awnings, facade AC units, scaffolding, dumpsters, litter) and `citygen/vegetation.py`
(street, median, promenade and park trees, conifers, palms, shrubs, roof plants, facade
greenery, overgrowth, median lawns, park hedges). Every generator proposes candidates; the
keep-outs (lanes, crosswalks, junctions, buildings, water, entrances, ground structures, park
paths, quay edges, the 1.8 m sidewalk clear path) are tested in bulk, then an occupancy grid
accepts them in a fixed order; randomness is a blake2b hash of ids (`props._u`); crowns are
fitted to facades and overhead decks. Six checks in `prop_checks.py`, `preview_props.png`
(`preview_props.py`). The blockout draws props and plants as geometry-nodes instances of
per-kind prototypes (one object per kind and tile; USD point instancers; left out of the glTF
tiles, which `props.csv` complements). Sample builds: `docs/progress/M6/`.

M7a (elevated highways) is in place: at the end of M1b, `citygen/elevated.py` lifts highway
windows chosen by ramp room and district density (`highways.elevated_share`) onto viaducts
(deck top 9 m, ramps at 5%, at most 6%, 40 m vertical curves, humps over raised roads or the
other road lifted), classifies the nodes on a run (plain, cross, tee, branch, split), builds
diamonds and tee stubs (one-lane one-way ramps that follow the deck through a 60 m taper and
land on an avenue leg at grade), and re-nodes the network (`attrs.split_of`, `overpass_at`,
ramps `road.highway.ramp`). `solve_grades` replaces M1b's bridge ramps with a network
envelope at 5.5% and keeps crossing roads 7 m apart. M2 passes local streets under decks,
adds underpass streets every 200 m, and lets local streets join primary roads up to 3 m up;
after transit, `road_supports` puts columns every 32 m under every raised deck over land.
Five checks in `elevated_checks.py` (65 in all), `preview_elevated.png`; `build_city`
retries a failing city with other layout salts on the same roads, then other road networks.
Sample builds: `docs/progress/M7/`.

M7b is in place, which completes the scope's milestones:
- **Pinned import** (`citygen/pinned.py`, scope 4.3): `water.islands[].pinned` (`source` SVG,
  `rotation_deg`) imports a traced district in the `maps/` conventions with its own
  deterministic path parser (arcs through `dmath`).
  - Hydro places the island with its exact traced outline (kept through the land opening);
    its holes become ornamental basins.
  - M1b adds the traced roads as drawn (role `pinned`, kept by every clean-up, exempt from
    the curve and length checks and from viaducts). Roads drawn off the coast run straight to
    the next district land and join the network; routing stays off the island.
  - M2 gives each traced building its own lot (block `blk000`, attrs `pinned`), keeps local
    streets 15 m from traced buildings, and treats traced highways as at-grade avenues
    (`streets.street_class`).
  - M3 builds traced buildings as prisms (label heights, else the legacy rule within the
    district range); transit never removes them.
- **Interchanges:** partial cloverleaf loops (`Elev._loop`: 270 degree loops in the two
  quadrants of a side whose diamond ramps do not fit) and trumpets (a ground highway stem
  passes under to a stub where two far loops land).
- **Art-direction loop:** `citygen review <out_dir> --spec S --prev P` writes `review.md`;
  `citygen spec diff A B`; rounds as in the skill.
- **Junction corners:** `junctions._corner` uses the fillet only when its run fits
  min(0.45 L, 60 m) on both legs, else the sharp curb corner, else the node (ramp gores
  leave at a few degrees), so junction polygons stay at their node.
- **Columns:** `elevated._fill_gaps` fills any column gap over 60 m, searching past a short
  segment's end nodes.

Demo: `docs/progress/M7b/nyxllor_pinned/`. Sample builds: `docs/progress/M7b/`.

M8a (robustness sweep) is in place: `.venv/bin/python -m citygen sweep [SPEC...] [--suite m8a]
[--seeds ...] [--only LABEL] [--workers 4] [--upto roads|local|full] --out DIR`
(`citygen/sweep.py`) builds many specs at many seeds, one build per worker process
(`CITYGEN_WORKERS=1` inside), and writes `sweep.md` and `sweep.json`: pass or fail, failing
checks with their first failure, retries (hydro and road variant, the full-city tries from
the report's `city_tries` stat), build time, sha256, crash tracebacks. The `m8a` suite is the
five samples and the pinned demo at their own seed plus seven more, and the test specs at five
seeds. Fixes from it, in short:
- exits on the map border count as land (`covers`, not `contains`), and every exit route
  enters square to the edge (`Fitter._edge_entry`);
- crossings keep room for their approach and avoid spanning a district's tip;
- road groups meet only on land, and a landmass counts where a road runs on it, not where a
  bridge clips its tip; named bridges land inland and are matched by alignment;
- four-way water crossings unnode by straightness, and primary forks that run side by side
  merge (`roads._merge_forks`);
- an island that would not be built is tried longer, and placement retries each missed
  island first;
- loop-road pieces at the seam and footbridge ends keep their levels; tee tails under a
  viaduct are trimmed;
- relation repair moves seeds along the asked direction;
- `build_city` looks at further hydrology variants when no road network passes, and
  `CITY_RETRIES` is 8.

Transit loop routing is M8b's. Sweep tables before and after, fixes and open items:
`docs/progress/M8a/README.md`.

M8b (transit loops) is in place, in `citygen/transit.py`: a loop is one simple ring through
its stops in route order. `_loop_points` moves a loop's district stops to junctions that come
in route order around the stops' middle (a star-shaped ring is simple; a dynamic program over
one junction per 10 degree sector, both ways round, near a circle and evenly spaced), and
`_deepen` pushes a stop deeper where the 1.15 r_min curve at its corner would leave its
district. Every leg keeps off the line's earlier legs (`_keep_off`, but within 60 m of its
own start); a road leg may end at any junction within 150 m of a district stop
(`RoadGraph.targets`), runs on the raster where the roads cannot keep it off (one bridge both
ways) or where it winds round the blocks, and a loop's last leg arrives to go on as its
first left. A road-mode loop is also routed off the roads (`_off_roads`) and kept so when
that serves more stops, meets itself less, or the road ring is 1.35 times longer; a loop off
the roads is also drawn along its guide ring (`_guide_loop`: the stop polygon with arcs,
waypoints every 120 m). Stations follow route order (`ordered_stops`; a loop's track starts
at its first stop), heights are graded round a loop's seam (`_graded`). Check
`transit_self_crossing` (66 in all): parts of a line more than 100 m apart along it stay a
structure width apart in plan or 5.5 m plus the structure apart in height, a loop closes,
stations in route order; the transit preview marks where a line meets itself and numbers a
loop's stops. Fast open lines (maglev, sky tube: r_min at least 300 m) place a middle stop
with `_fast_point` (a junction where the curve's apex stays inside, else a corner on a 60 m
grid beside the district whose guide runs a station length 40 m inside it) and are also
drawn along their guide line (`_guide_line`: the stops with arcs at those corners, waypoints
every 120 m), kept when better by `_line_key`. A line ending at a megasite stops where the
site's zone begins (`_site_point`, `RoadGraph.targets`), not at its middle. The raster
search uses flat integer states, an exact turn-free cost to go (`_togo`) over 600 m, and a
reachability flood fill (`reachable`) after 20000 steps. A line's track does not depend on
the other lines (its heights see the buildings they remove); a whole-city retry
(`build_city`) after any failed check still moves every line. A sky tube tower it cannot
climb within its altitude range keeps its portal with 3 m headroom (`_fit_portals`), and an
open road line still under its radius is tried with legs free to run back along the line
(`_spurs`). M8b is stacked on M8a: nyxllor builds on its first layout (8 tries on M8a
alone), Delta still takes 9 (its sky tube loops and monorail on M8a's layouts). Sample
builds and the sweep on the combined code: `docs/progress/M8b/`.

M8c (transit on a city's first layout) is in place, in `citygen/transit.py`: a flying loop
(sky tube, maglev) is one ring of Dubins paths (`dubins`, `dubins_points`, `_dubins_track`:
straight runs and arcs of 1.15, then 1.06, times the mode's radius; each stop passed at a
point 30 m inside its zone, a sky tube's nexus inside its tower, in one of 16 headings; the
poses found by coordinate descent from the `_loop_points` ring, fewest blocked cells, then
the raster cost plus curve length; up to two free poses where blocked; kept only when clear
of itself), else M8b's routes. An open road line still flawed after M8b's retries goes off
the roads, then with its middle site, place or island stops on its way
(`_off_roads_line`, `_way_point`); any open line still flawed is tried as Dubins paths from
stop to stop (`_dubins_line`), kept when better (`_line_score`). A line to an exit counts as
missing it unless a track end is within 250 m (`_served`); sky stations only use portal
towers that still serve their stop; metro stairs step 12 m along the concourse where a
concourse end sits on a walkway. Delta Megacity builds on its first full-city try (9
before); the sweep passes 58 of 68 with no transit failure. Sample builds, same-layout
before and after maps and the sweep: `docs/progress/M8c/`.

### Rules for cloud sessions building citygen milestones

- **Work-in-progress images:** after each major sub-step (and at least every hour or so), build
  the sample cities, commit their preview images to `docs/progress/<milestone>/wip/<NN>_<step>/`
  and push to the session branch, so Swagnik can watch progress on GitHub before the PR exists.
  Keep only images and short notes there; overwrite nothing from earlier milestones.
- **Root `README.md`:** when the milestone PR is ready, update the Progress table and the
  "Latest maps" images to point at the new milestone's previews. Every 3D render shown in the root
  README is 8K: `citygen rerender <blockout_dir> iso_city ... --to docs/progress/<M>/<city>`
  (7680 px wide by default, a few seconds each; fall back to 3840 or 2048 only if 8K fails).
  Always include the whole-city isometric views (`render_iso_city.jpg`).

## Working preferences

- Execute tasks end to end and ask for the access you need, rather than handing back scripts to run.
- No em dashes in any output.
- No backup copies before edits (the folder is under git).
- Write math as rendered LaTeX.
- Summary/deck bullets: noun-phrase topics rather than verb-led phrasing.
