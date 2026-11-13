# CyberGen

City-agnostic generators for cyberpunk open cities, in five stages: 1 layoutgen (`citygen`, the
prompt-to-city layout generator, current), 2 assetgen (a unique 3D model for every building,
plus street elements and textures), 3 atmosgen (lighting, sky, atmospherics), 4 lifegen
(traffic, crowds, trains, aircraft, generated), 5 storygen. CyberGen is a standalone city
generator that anyone could use for their own cities: it knows of no particular game or
engine project, and nothing in the repo (docs, code, comments, sample names) refers to one.
Its cities are sized for open-world games, roughly a quarter of Night City's scale (walkable
streets, crowds and traffic). The owner (Swagnik) does art direction and layout; Claude does
code, tooling, procedural generation, and most asset work.

**Layout by stage.** Each stage has its own generator package (`citygen/` for stage 1), spec
(`docs/<generator>_scope.md`), full milestone log (`docs/<generator>_milestones.md`, the
detailed per-milestone record for sessions) and section in the root README (images, then a
high-level milestone table). Stage 1's milestones are M0 to M22 (M17 to M21 the fixes from the first run-through,
`docs/run_through_1.md`; M22 from the second),
built in `docs/progress/M*`; later stages give their milestones a prefix of their own (set in
their scope doc) so their progress folders never clash with stage 1's.

**Unreal exporter.** One exporter takes every stage's output into Unreal Engine 5.8. It is
not a stage and has no milestones of its own: stage 1 introduces it (M15, `citygen unreal`,
in `citygen/unreal.py` and `citygen/ue/` until it moves to a package of its own after M15
merges), and every later milestone, in any stage, updates it in the same PR for what that
milestone adds or changes, so the exporter always matches the generators. Each stage
contributes its part of the manifest keyed by M10's stable ids, layered in stage order (a
later stage's entry replaces an earlier one's for the same key; a key it has no entry for
keeps the earlier one). A milestone session does not have to run Unreal: the coordinating
session decides whether a finished milestone needs an Unreal check and, if so, dispatches a
separate local session for it (import the cities it touches into a throwaway project of the
check's own, import again, `--check`, shots). Spec and the record of what each milestone
changed in it: `docs/unreal_export.md`.

**Validation (every stage, every PR; Swagnik's rules, 2026-10-27, 2026-11-05 and 2026-11-10).**
Before pushing a PR, make sure the outputs look good and nothing breaks, at the scale of the
change: a check earns its place by what it can find, not by habit. Test only what changed: no
PR, milestone or not, runs the full test suite.
- **Small fixes** (one feature or issue, code local to it, such as #93, #94, #95): the change's
  own tests and the test files of the modules it touched; builds of only the cities that have
  the feature (every check passes) and only the asset stages it touches (`assetgen streets`,
  `props`, ..., then `fit`, not a whole `assetgen build`); their previews and renders; the
  recorded hashes of the cities it moved rewritten from those builds, saying why. No full test
  suite, no builds of cities without the feature, no builds of main to show a failure predates
  the change (name it if it is a known one).
- **Milestones and changes to shared code** (roads, junctions, ids, geometry, the build
  driver, anything every city goes through): build the cities the change touches, every check
  passes, look at their previews and renders, and the tests of what changed pass: the test
  files of the modules it touched and the tests that run that code (recorded hashes
  regenerated where a change moves a model on purpose, saying why).
- **Main:** a full test suite only now and then, not after every merge or milestone; the
  coordinating session runs it on main in the background and fixes or files what it finds. It
  does not validate a PR again (it reviews the outputs and the diff, and has the PR merge the
  latest main first when they overlap).
- **Test runs show their progress** (Swagnik, 2026-11-06): write pytest's output straight to
  a log file as it runs, never only through `| tail` or another filter that holds it back
  until the end:
  - use `-rfE --durations=25`, and `-v` for a run of a few files;
  - say where the log is, so anyone can see how far a long run has got and which test is
    slow;
  - the same for long builds: their progress lines go to a log, not a pipe.
- **Every test run can be paused** (Swagnik, 2026-11-08). `tests/conftest.py` loads
  `tests/testctl.py`, so every pytest run in a checkout gets a folder in its
  `.pytest_runs/` (a journal of each finished test, flushed as it goes). From that checkout:
  - `python tests/testctl.py status`: the runs, newest first, how far each got, the test
    running now, and the command to continue a run that stopped;
  - `python tests/testctl.py pause`: freezes the run now, pytest and every process it started
    (no CPU; the memory is kept, and nothing survives a restart); `resume` thaws it;
  - `python tests/testctl.py stop`: ends the run after the test running now;
    `python -m pytest <same arguments> --resume` continues it later, leaving out every test
    that passed or was skipped (failures run again). This also works after a crash, a kill or
    a reboot.

  Tell Swagnik where a run is and how to pause it; never pause or stop one unasked.

Nothing more: no x86, Docker, Windows or other cross-platform comparisons, no stage-trace
diffs, no `lock --verify` runs, no seed sweeps (unless the work is about robustness), no
repeated validation runs. Where a scope's "done when" asks for Mac = x86, that part waits for
the deferred determinism check in `docs/determinism_check.md`, which runs only when Swagnik
asks for it.

The sample city is **Vesper Bay** (`cities/vesper_bay`, golden key `vesper_bay`; pinned demo
"Vesper Bay Pinned" in `cities/vesper_bay_pinned`).

## Corporate Core (hand-traced demo district)

The traced map is the pinned demo's input (`cities/vesper_bay_pinned`); `pipeline/`, `maps/`,
`reference/` and `unreal/` are the earlier hand-tracing pipeline that made it.

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

- Testing Unreal imports: UE 5.8 at `/Users/Shared/Epic Games/UE_5.8` (it ships an official Unreal
  MCP server and the PCG plugins, the route for Claude to drive the editor), always in a throwaway
  test project of the generator's own. Heavy scenes run better on the owner's Windows PC
  (RTX 4070 Ti, 12 GB; UE 5.8 at `C:\Games\UE_5.8`, found through the Epic Games Launcher's
  install list; Visual Studio 2022 17.14 for the play features' plugin; Blender 5.2 in
  Program Files, found without `BLENDER`).
- `unreal/build_greybox_unreal.py`: editor Python script. Put it plus `corporate_core_plan.json` in
  `<UnrealProject>/Greybox/`, open a level, Tools > Execute Python Script. Clears and rebuilds its own
  actors (tag `CorporateCoreGreybox`), Ctrl+Z undoes a run. Buildings are currently oriented boxes, so
  the megatower becomes its bounding box; true footprint meshes are a planned upgrade.
- citygen's blockout exports `city.usdc` (whole city) and one `tiles/<tile>.glb` per 256 m tile
  (custom properties as glTF extras) for World Partition style imports, plus
  `unreal/corporate_core_plan.json`, which `build_greybox_unreal.py` reads unchanged.
- `citygen unreal <build_dir> <uproject>` (M15) imports a whole built city headless: a World
  Partition level with collision, per-category materials, instanced props, actor tags by
  citygen id, the graphs as data assets and a player start; importing again updates by id.

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
`street_<n>`) again from the saved `city.blend` with the build's cameras; `--eye X Y Z --target X Y
Z [--lens MM] [--name N]` adds a perspective camera of one's own. The Blender test skips when Blender is missing. Sample builds:
`docs/progress/M4/`.

M5 (transit) is in place: the same build runs `citygen/transit.py` after the buildings (stops
resolved to junctions, nexus platforms or sites; elevated rail and monorail routed on the road
graph, maglev, sky tubes and metro on a 15 m raster; curves fitted at 1.15 times the mode's
minimum radius with obstacle-checked arcs; a height profile between lower bounds (water,
road decks, roofs) and upper bounds (tower portals); stations with stairs, elevators
and walkways split onto the sidewalks (no canopy over a stair foot since the play fixes); decks, tubes and supports in medians or at
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
tiles, which `props.csv` complements). Boats moor past their quay's band (`width_m` across
its line, half over the water) by `MOOR_GAP_M`, their hull (`boat_hull`, AG8's 8 x 3 m)
clear of every quay band and `SHORE_CLEAR_M` off the shore (`Moorings`; issue #113, they lay
in the quay wall), which `boats_afloat` checks with M16's banks. Sample builds:
`docs/progress/M6/`.

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

Demo: `cities/vesper_bay_pinned/` (first built in M7b). Sample builds: `docs/progress/M7b/`.

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
(`_spurs`). M8b is stacked on M8a: Vesper Bay builds on its first layout (8 tries on M8a
alone), Delta still takes 9 (its sky tube loops and monorail on M8a's layouts). Sample
builds and the sweep on the combined code: `docs/progress/M8b/`.

M8d (trumpet flyover) is in place, in `citygen/elevated.py`: a trumpet is the textbook one
loop and one flyover (`Elev._trumpet_flyover`), with M7b's two far loops (`_trumpet`) as the
fallback. The loop runs on from its stub terminal under the deck along the stem to the stem's
near terminal (the stem ends there, no stub). The flyover (`_flyover`, `_fly_fit`) leaves the
far lanes, turns square off the deck, runs round the loop's outside (the bell; a diagonal
over the loop as a second shape), crosses the deck square beside the stem, comes down beside
it and turns into it at its own terminal. Its profile (`_fly_profile`) clears every road and
ramp under it by 5.5 m plus the deck (`_fly_needs`), level between crests, at 5% with 40 m
vertical curves, at most 6%. Its stretches with no room for a column stay within 50 m
(`_fly_span`). Ramps built later test a flyover in height (`_apart_in_z`). The ramp has
`attrs.flyover` and `level` 2; the stats gain `flyovers` and `max_flyover_m`;
`preview_elevated.png` casts it on top, puts a flyover trumpet in its inset and its profile in
the profile panel. Only Vesper Bay has a trumpet among the samples (crest 16.6 m). Sample builds:
`docs/progress/M8d/`.

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

M9 (tunnels) is in place, in `citygen/tunnels.py` (checks in `tunnel_checks.py`, preview
`preview_tunnels.py`), road tunnels being a negative level (-1) of the road network:
- **Road tunnels** (end of M1b, before the viaducts): a tunnel is a window on a corridor
  (segments of one class joined straight on through the nodes) whose profile is a graded
  envelope of depth needs, z(s) = -max(0, max_i(d_i - g dist(s, I_i))) at 5% (5.8% where
  that does not fit), with M7's 40 m vertical curves: under water the bed (canal 3, river 7,
  sea 12 m) plus 1.5 m backfill, the roof and 5.5 m clear; under a road crossing at a node
  inside the window the clear height, roof and 1 m of cover (the node goes: the crossing road
  passes over, `attrs.over_tunnel_at`; a tee avenue ends beside the lid, `ends_at_tunnel`).
  A window fails on a node it cannot pass under (a highway, a fork, an exit), a corridor
  end, an open approach over water or under another road, a bridge approach reaching its
  descent (`Ctx.lifts`, solve_grades' envelope), or a network it would cut apart. Immersed
  tubes replace bridges (`highways.tunnels.water`: auto (sea crossings over 600 m), prefer,
  never; a named crossing only when its `tunnel` is true); cut-and-cover tunnels go under
  the districts of `highways.tunnels.under` (the longest covered stretch between the
  interchanges). Highways only for now. The window's segments become one segment (`tunnel`,
  `tunnel_ids`, level -1) whose profile `_envelope` keeps (`attrs._tunnel_prof`, dropped
  after M7); the network is renumbered as M1b numbers it. Model: `tunnels` (kind
  immersed_tube, cut_and_cover, metro, pedestrian; line, box width, clear height, roof,
  floor, portals where the roof meets the ground, vent ids). M2 forbids local junctions on
  sunk stretches and lays streets over covered lids from frontage to frontage (role
  `over_tunnel`, like M7's underpass streets).
- **After transit** (`tunnels.build`): open approaches (structure `trench`), portals,
  ventilation buildings on the lid near each portal of a tunnel over 300 m and every 800 m;
  the metro lowered at 3% under the water bed, road tunnels, building foundations (4 to 18 m
  by height, `foundation_m`) and earlier metro lines, its tunnels cut between the station
  boxes; pedestrian underpasses (`highways.tunnels.underpasses`, default 0.5) under at-grade
  highways, stairs from a sidewalk on each side, the sidewalk walkways split there. Transit
  columns keep off road tunnel boxes.
- **Checks** (70 in all): `tunnel_grades` (roads 6%, metro 4%), `tunnel_cover` (1 m of
  ground past 40 m from a portal, 1.5 m under the water bed), `tunnel_portals` (on land,
  nothing on the open approaches, no node within 20 m of their top), `tunnel_clash` (no
  tunnel within 1 m in height of another tunnel, a metro station box, a foundation or a
  column footing).
- **Blockout**: road tunnels as open boxes (floor, walls, roof over the covered stretch,
  portal lintels) with their roads as own objects, the ground open over the approaches,
  metro tunnels and underpasses as solid boxes, ventilation buildings; `render_cutaway.jpg`
  (view `cutaway`, also for `citygen rerender`): the city cut along the longest road tunnel,
  earth under the ground, from over its first open approach.
Samples: Nexus City's ring highway dips under Midtown in a cut-and-cover tunnel (Vesper Bay
keeps its trumpet: a tunnel on its ring takes the flyover's stem). Greyhook's earlier layout
(one round tip) crossed its river in an immersed tube; it is kept as the test fixture
`tests/data/peninsula_round_tip.json`, since the reshaped Greyhook crosses its river beside
the map edge, with no room for a tube's approaches. Sample builds: `docs/progress/M9/`.

M11 (gameplay layer) is in place: the build ends with `citygen/gameplay.py` on the finished
city (after props) and nine checks in `gameplay_checks.py` (75 in all on M8c, 79 with M9):
- **Factions and zones:** a gang per district with `danger` at 0.45 or more, a corporation
  for corporate, campus, port and spaceport districts, else the city police (spec
  `faction` names or shares one); each district split into 1 to 4 turfs by straight bisectors
  between seed blocks, a rival gang on the turf nearest its home; a police precinct per
  district with its station building.
- **Fields:** wealth, danger and police on a 32 m raster (`fields`): spec `wealth`, `danger`,
  `police` per district (archetype defaults in `presets.py`), blended with an integer box
  blur, raised or lowered near parks and water, landmarks, alleys, raised decks, stations and
  precinct stations.
- **Points of interest** (`pois`): bars, clinics and vendors from ground-floor units (budget
  per km2 by archetype, spacing), apartments, gang hideouts, fixers in a bar; named from word
  lists by hash, unique. Every place has an `Access`: door, ground walkway (main walkway
  component of its landmass), drive lane (largest strongly connected part of the lane graph)
  and curb point; candidates without one are skipped, so `poi_reachable_foot` and
  `poi_reachable_car` hold by construction.
- **Lifegen data:** `densities` per road segment and hour band (`model.HOUR_BANDS`): traffic,
  vehicles, crowds, gang members and police per 100 m. `parking` (structures, underground
  garages, setback lots, curb), `travel_points` (taxi stands, fast travel).
- **Sign slots** (`sign_slots`): one per M6 shop sign and M3 roof billboard, plus facade
  billboards facing highways and avenues, holo-ads over tower roofs and neon bands above the
  shop signs.
- **Outputs:** `preview_gameplay.png` (`preview_gameplay.py`), `gameplay.json` beside the
  blockout exports with a per-tile index; no blockout geometry. Ids come from what a place is
  (building, unit, segment, district), not build order.
- **Rule:** a gameplay check may only ask for what the stage can always build, and the stage
  only places what passes it (setback lots use the check's own `lot_clash`; fast travel falls
  back to junctions and lane middles), so the layer never makes a city retry: the sweep is
  build for build the same as M8c's (58 of 68). Sample builds: `docs/progress/M11/`.

M12 (stack interchanges) is in place, in `citygen/elevated.py`: where two generated highways
cross (four highway legs, two straight pairs, 45 degrees or more; `Elev.stack_sites`) and the
footprint fits, `plan_stacks` lifts one through the crossing (640 m of ramp room both ways
plus its run down, or up to the map edge) and keeps the other at grade (700 m), no other
highway meeting either window, no M9 tunnel in either or at their nodes; avenue nodes under
the lifted window stay at grade (node kind
`under`, also an avenue junction whose own ramps do not fit; a one-sided avenue then ends
`UNDER_END_M` clear of the deck). `stack_ic` builds eight one-way directional ramps
(`_system`): the left turns first, out to lines 45 m beyond the highway edges and across the
core on a diagonal pinned 50 m before and after the crossing on the two roads (`_sys_core`,
150 m turns), tier 2 (18 m, from the highway at grade) and tier 3 (27 m) over the 200 m core;
then the right turns in their quadrants, under the left ramps where those are high enough.
Profiles as M8d's flyover (5.5 m plus the deck, 40 m crests, 5%, 6% at most; the climb's
length goes to either end, `bias`), no 60 m stretch without a column spot (`_fly_span`), at
most 140 degrees of turning (`_winding`). The turbine (`highways.crossings: "turbine"`, else
the stack's fallback) sweeps the left turns wider so their crossings fall apart. Where neither
fits, or a planned stack is not built, the stage runs again without the plan (M7's crossing,
same bytes). Ramps carry `attrs.template`, `turn`, `tier`, `crossing`; stack left ramps
`level` 2 or 3. `NamedHighway.reuse: false` makes a crosstown that crosses the highways it
meets. Two checks (`stack_ramps`, `stack_levels`, 77 in all on M11, 81 with M9);
`preview_elevated.png` puts a stack in its inset and its ramp profiles in the profile panel. No sample has room for a stack,
so the stack demo `cities/vesper_bay_stacks` is the pinned demo with only its highways changed
(art direction): two crosstowns that cross in a stack in The Stacks (a separate city, so the
pinned demo and its sweep seeds stay as they were). Sample builds: `docs/progress/M12/`.

M10 (edit, lock, regenerate) is in place:
- **Stable ids** (`citygen/ids.py`): one renaming pass gives every entity an id from what it
  is and where it sits: its name (`rv.great_river`, `stn.crown_exchange`), else district,
  kind and the 1 m cell of its middle as compass offsets from the city center
  (`rs.e1234n567`, `d03.lot.e512n88`), else its parent's id and a suffix
  (`d03.lot.e512n88.bld`, `rs.e1234n567.f0`); collisions get `.2` in content order (one
  reference deep), set-like id lists and id-sorted gameplay rows are sorted by new id. It runs
  after the road supports (before the props, so props, plants and gameplay draw on stable
  ids) and at the end of `build_city`; the stages keep build-order ids internally. A new
  collection or id field must go into `ids.REFS` and `ids.ORDER` (a test fails on any
  reference the pass misses or any id that still looks like a build counter).
- **Locality fixes:** `blocks.build_blocks` takes only the road pieces that touch a
  district's clip and unions them with `geom.union_local` (Z-order merge tree), so a far
  change does not move a block by 1 cm.
- **`citygen build SPEC OUT --district NAME`** (`citygen/edit.py`, state in
  `city_state.json`): M1 replayed at the search's choices (`build.replay`, `choices`), M2 to
  M11 run for the whole city under a `streets.Frame` (every road not inside the district held
  and restored as it was, new streets meet held roads only at old nodes, held streets see
  the old build's junctions at their turn (`Builder._junction_near`: not the new streets'
  `Line.fresh` ones, the district's old gates once past its turn), clean-ups remove the new
  street, held footbridges re-injected on canals that reach the district) with transit
  lines held (a held metro back at its base depth, M9 lowers it again), then `splice`: the
  district and its seam from the new build, the rest from the old city byte for byte, a
  reference closure both ways, props and plants near changed ground, taxi spacing, fields,
  factions, names. 14 to 42 s for a sample district (the stack demo's The Stacks too), with
  the garbage collector paused (`edit.no_gc`); the state's `choices` must name the winning
  layout salt (`stats["layout_salt"]`).
- **Overrides** (`citygen/overrides.py`, `overrides.json` beside the spec): pins (held roads;
  pinned buildings on a lot of their own put back before the props, `blocks._frame_lots`,
  `buildout.frame_pins`) and edits (`move`, `replace`, `plaza`, `remove`) on stable ids.
- **`citygen lock`** (`citygen/lock.py`): `city.lock.json` (spec, overrides, regenerations,
  choices, code hash, model hash); `--verify` rebuilds from it byte for byte.
  **`citygen model diff A B [--png]`** (`diff.py`, `preview_diff.py`).
Sample builds (the five, the pinned and the stack demo, each with a release lock),
regenerations, sweep: `docs/progress/M10/`.

M13 (terrain) is in place, in `citygen/terrain.py` (checks in `terrain_checks.py`, preview
`preview_terrain.py`). A spec without `terrain` builds exactly the flat city it built before
(the new model fields are left out of the JSON: `Field(exclude_if=...)`); every z elsewhere in
the model stays measured from the finished ground where it stands, so M7/M9/M5 clearances need
no change, and grades are measured on ground + z:
- **Field** (`field`, at the start of each road attempt): the natural ground on a 4 m grid
  (`terrain.natural`, rows from the south): `hills` and `ridges` as smooth bumps, `relief_m`
  value noise (blake2b lattice), an `inland_grade`, banks carved down to the water (10%, 12%
  from the sea), `cliffs` (a district on a plateau; `facing` keeps the cliff to those sides,
  the rest a `slope_m` escarpment), `flat` districts and every megasite levelled; water at its
  level (`water_levels`: the sea 0, rivers and separation channels falling to the mouth,
  waterways at the level of what they join). Numpy elementwise arithmetic and GEOS distances
  only, no reductions; values on the 1 cm grid. Highways route round steep ground
  (`roads.SLOPE_COST` on the A* raster).
- **Grade lines** (`grade`, after M2): one graph of every road (nodes and crossings without a
  node shared, stations every 10 m), the profile closest to the natural ground in the largest
  deviation within each class's grade (highway 6%, avenue 8%, street 12%, alley 15%, less what
  the road's own z profile climbs): integer min-plus Dijkstra from every vertex both ways, the
  mean of the two; a junction of local roads holds its node's height along each leg out to
  its polygon's edge, past the curb and sidewalk corners, at most 0.45 of the leg
  (`Local.cuts`, `junctions.run_along`, the stage 1 fixes), a primary road keeps its grade through
  its junctions. `RoadSegment.ground`, `RoadNode.ground_m`. The finished ground
  (`terrain.ground`) puts each corridor (width plus 1.5 m) on its grade line, blends small steps
  over 6 m, and leaves the rest as retaining walls traced on the grid (`structure`
  `retaining_wall`, line z the wall height); primary roads 14 m under the hill for 40 m are
  `bored` tunnels, 15 m over the ground for 20 m terrain viaducts (deck and columns). Lots whose
  ground falls over 15 m become hillside greens (`open_space` green, `attrs.slope`).
- **After M3**: buildings seated (`base_m` at the main entrance, buildings linked by skybridges
  on a common floor grid, `plinth_m` at the lowest ground under the footprint); the metro graded
  on ground + z; props and plants off steep streets, cliffs and terrain viaducts.
- **Checks** (86 in all): `ground_grades`, `cut_fill` (20 m cut, 18 m fill), `retaining_walls`
  (no graded step steeper than 1:1.5 without a wall), `building_seats`, `water_levels`;
  `transit_grades` and the metro in `tunnel_grades` measure on the ground.
- **Blockout**: the ground a 4 m heightfield per tile (part `grid`), flats draped cell by cell
  (part `drape`), roads on their grade lines, buildings on their bases with stepped plinths,
  water at its level, retaining walls; the cameras frame the ground.
- **With M10**: ids from what and where (`<segment>.wall.<cell>`, `<segment>.viaduct.<cell>`,
  `<segment>.tvcol.<cell>`, `bore.<cell>`, `<district>.os.slope.<cell>`; `ids.Renamer`
  also renames `terrain.water_levels[].water_id`). `--district` holds every road's grade
  line outside the district (`grade(..., held)`: held vertices fixed, the envelopes clamped
  to the bounds they set), the splice takes `terrain` and the retaining walls from the new
  build, and `edit._close` lets a building's gameplay rows follow it and drops old lots and
  open spaces under changed new ground (`_ground_cover`). `junctions.one_way_loops` now reverses a street's
  z profile with it (main bug: six m8a sweep builds now pass on an earlier try).
Sample: `cities/cragmouth` (a cliffside port; hills, a ridge, the Crown Heights plateau with a
cliff over the bay). Its golden hash is under `terrain_cities`. Sample builds:
`docs/progress/M13/`.

M15 (Unreal export, the end of stage 1) is in place: `citygen unreal <build_dir> <uproject>
[--check] [--shots DIR] [--new-project]` imports a blockout output into an Unreal 5.8 project.
`citygen/unreal.py` (venv side, no Unreal) writes `<build_dir>/unreal/manifest.json` (an actor
per blockout object of the glTF tiles, keyed by its name, with the sha256 of its plan entry;
props and plants as one instanced actor per kind and tile with their citygen ids; a
material per blockout material; the player start on the sidewalk of the fast-travel point
nearest the middle; the blockout cameras), `prototypes.glb` (the prop and plant kinds, written
there from the plan's parts) and `graphs.json` (lane, walkway and transit graphs as flat
arrays), enables PythonScriptPlugin and EditorScriptingUtilities in the .uproject and runs
`UnrealEditor-Cmd -run=pythonscript` on `citygen/ue/import_city.py` (stdlib and `unreal`
only). Under `/Game/CityGen/<City>` that makes a World Partition level, static meshes through
Interchange (no imported materials, no distance fields or Lumen cards, complex collision,
the hash as `cg.hash` metadata), material instances of `/Game/CityGen/Core/M_CityGen`,
`BP_CityGenInstances` actors (an HISM and the instances' ids) and `BP_CityGenGraph` data
assets (Blueprint classes the importer makes, so no C++ compile), a player start, a sun, a
sky light and the sky atmosphere. Actors carry `cg.city=`, `cg.key=`, `cg.hash=`, `cg.id=`,
`cg.type=`, `cg.category=`, `cg.tile=` and `cg.district=` tags. Importing again updates by
key and hash (a tile's glTF only when one of its objects changed; `MESH_VERSION` and
`ACTOR_VERSION` re-apply importer changes); the same build twice writes no file, and
`unreal.manifest_changes(old, new)` is exactly what an import over another does (the result's
`keys`: created, updated, deleted). An updated actor is marked modified (setting tags alone
does not dirty it), a destroyed one lets go of its meshes, and the meshes no object uses are
deleted after the save in one batch (deleting an asset the open level still names reloads
the level and drops unsaved changes). `--check` runs `citygen/ue/check_city.py` in the full
editor (`-ExecCmds="py ..."`; `-ExecutePythonScript` quits when the script returns;
`Slate.bAllowThrottling 0` or play-in-editor does not tick unfocused; it waits on
`WorldPartitionSubsystem.is_streaming_completed`, found through `unreal.ObjectIterator`):
streaming, traces onto ground, roofs and facades, a walk along sidewalks with head room (the
sidewalks of a raised road stay at z 0 in the model, an open item), and with `--shots`
renders from the blockout cameras (`--view NAME EX EY EZ TX TY TZ [LENS]` adds one). On a
terrain city (M13) the ground is a heightfield actor per tile and `graphs.json` carries
absolute heights (`exports.graphs(m, ground)`, `"heights": "absolute"`), which the data
assets, the player start and the walk use; the blockout draws one object per retaining wall,
so walls, bored tunnels and terrain viaduct columns are keyed by their ids. Each import
makes the city the project's startup and default map (`unreal.set_startup_map`;
`--no-startup`) and sets what Play puts you in: the walker (`--play walk`, the default since
the play fixes of 2026-11-12; the play plugin's first-person `ACityGenWalker` as
`Core/BP_CityGenWalker` wearing the project's own character's body, spawned by
`GM_CityGenWalk`, the level's game mode override), the fly pawn (`--play fly`;
`Core/BP_CityGenFlyPawn`, a SpectatorPawn with no collision at `--fly-speed`, spawned by
`GM_CityGenFly`) or the project's own (`--play project`);
World Partition's main grid is 128 m cells (256 m before AG16) loaded `--view-range` (768 m since AG16) around the
player and the level's instanced HLOD layer reaches the whole city (its merged parent
layer cut off; partitions set by C++ property name, `CellSize`, `LoadingRange`; every
master `used_with_instanced_static_meshes`, or the HLODs draw flat gray), and the HLODs are
built after the import (the WorldPartitionHLODsBuilder
commandlet, rebuilding only what changed; `--no-hlod` skips it); `--check` walks with the
walker (its spawn, body and a curb climbed), then flies. User guide: `docs/unreal_export.md`, "Import, open and
play". citygen makes no network call; the
official Unreal MCP plugin (`Experimental/ModelContextProtocol`, an HTTP server in the
editor) is the interactive route for a Claude session. Testing is always in a throwaway
project of the exporter's own (`--new-project` makes one from the First Person template,
outside the repo); never import into any other project unasked. Spec and record:
`docs/unreal_export.md`. Sample imports: `docs/progress/M15/`.

The fast import is the importer's default (an exporter update, no milestone): stage 2's packs
queued as one async Interchange import, a Python pipeline step (`CgPackStep`,
`CgTextureStep`) setting each mesh's Nanite settings and each texture's settings before the
build and skipping meshes the city does not place, meshes saved in one batch, actors saved and
unloaded every 2,000 spawned (`CITYGEN_UE_OFFLOAD`), the editor run with `-fastexit` and no
distance field or card tasks (`unreal.FAST_INI`). Same level, same hashes;
`CITYGEN_UE_FAST=0` takes the one-at-a-time path. Notes: `docs/progress/exp_fast_import/`.

The exporter's play features are in place (an exporter update, no milestone):
`citygen/unreal_play.py` writes `unreal/map.png` (the city from above, drawn from the
blockout plan, again only when the plan changes) and `unreal/play.json` (walkway points every
5 m, one per 3 m cell; lamp heads from the prototypes' `prop_light` parts; district labels),
the manifest's `play`; it copies the C++ plugin `citygen/ue/CityGenPlay` into the project and
builds it with UnrealBuildTool (`-NoHotReloadFromIDE`, skipped when unchanged; when no
compiler builds it the city imports without the features, a plugin never built taken out
again, one built before kept as built; `--no-play`).
The importer places its `CityGenPlay` actor (key `play`, always loaded) with the map texture
(`Play/T_<City>_Map`), points, lamps, labels and `MPC_CityGen`: in the game a minimap, M the
map (wheel zoom, right drag pan, left click teleport onto the nearest walkway, held until
streamed in), `.` a free camera (a spectator pawn, back to the player after), Tab the
developer menu (day or night: `Night`, a dim moon, a fixed night exposure, the 48 lamps
nearest the view as real lights); console commands `CityGen.*`; `--check` drives them
(Python calls the actor's UFUNCTIONs) and shoots them with `shot showui`. Python cannot write
Blueprint graphs, hence the C++. Spec:
`docs/unreal_export.md`, "Play features". Results: `docs/progress/play_features/`.

Greyhook reshape (its coastline made more natural and interesting: a peninsula that fans out
into headlands): `water.coast.headlands` (2 to 5, peninsula only, in `hydro._fan_plan`,
`_fan_outline`, `_fan_peninsula`) gives a mainland strip 0.17 of the map deep, a short neck
(shoulders, a waist), a bay on each side, then the headlands rooted on an arc and splayed, a
U-shaped cove between each two; a centripetal Catmull-Rom spline runs through the control
points (`_spline`), moved along its normals by the coast noise (`_wobble`); the sea share
solve scales the headland widths, and a cove the smoothing pinches shut becomes land. Its draws
come from `derive_seed(seed, "hydro.fan")` (a hydrology variant past 0 draws the fan afresh),
and a spec without `headlands` builds as before.
Greyhook (3.6 x 3.6 km) has three headlands and two islets (parks); its river is pinned with
meander 0, so the walled heights north of it keep their share at every seed. Builds:
`docs/progress/greyhook_reshape/`.

M14 (layered districts) is in place, in `citygen/decks.py` (checks in `deck_checks.py`,
preview `preview_decks.py`): a district with `decks` (spec `District.decks`: `height_m` 9,
`cover` 0.45, `column_m` 18, `light_m` 70, `ramps` 2, `upper` archetype and `upper_height_m`
for what stands on it) gets a deck city at level 1 over its ground streets. A city without
decks is byte-identical (every new field is left out of the JSON at its default: `level` on
junctions, crosswalks, sidewalks, lanes, walkways, lots, open spaces, buildings, props,
plants, green areas; `decks`):
- **Plan** (M2, after the local streets, before the junctions; `DK.plan`): the faces of the
  at-grade street graph, a cluster grown from the face nearest the district's middle across
  interior streets until `cover` of the district, keeping off roads raised over 3 m (and, in
  a regeneration, the held transit lines too low over it). Interior streets get an upper twin
  (`l1.<id>`, level 1, z the deck top; nodes `<id>.l1`), spokes out of the cluster end 6 m
  short of the edge street or become ramps (`deck_ramp`, two lanes, 12% with 10 m top and
  12 m foot runs and 15 m curves, `ramp_profile`), at least one per upper component (one
  without is dropped); the ground network stays connected.
- **Per level:** `JN.build` makes the lane and walkway graphs per level (walk keys `(x, y)` on
  the ground, `(x, y, level)` up; `DK.key`, `walk_ends`, `end_levels`); a walkway between
  levels carries `attrs.levels`.
- **Finish** (after the blocks; `DK.finish`): the slab is the lots under the deck (in its
  faces, fronting a twin) with the twins' corridors and the upper junctions, and 4 m over a
  park or plaza its streets pass (a colonnade carries it); light wells (lots opened to the
  sky, greedily until every ground walkway under it is within `light_m`, at least two), each
  with a switchback stair and an elevator from the ground sidewalk to the deck's; upper lots
  (`<lot>.l1`) where a lot under has 6 m on a twin.
- **M3:** lots under the deck build the low `undercity` program up to the slab's underside
  (`attrs.deck_under`); upper lots build the `upper` archetype from the deck top
  (`attrs.deck`, `deck_top_m`, level 1); skybridges per level.
- **After transit and tunnels** (`DK.supports`): round columns under every slab in the
  furniture zones of the streets under it, on its grid in the lots, then filled in (the
  nearest allowed point of a thin strip) wherever the slab is farther than 0.75 x the grid
  from one (1.3 x over a ground street or junction, 6 m more at the edge); none in a lane,
  crosswalk, junction, clear path, door, tunnel or structure.
- **Views:** `DK.ground_view` (the ground with each slab as an overhead structure: lights
  hang from it, trees fit under it) and `DK.deck_view` (a deck as a ground of its own, z
  from its top); props and plants (`DK.props`) and the prop checks (`DK.per_level`, also in
  `checks.run_checks`) run on every level. Gameplay places are reached on their own level's
  walkways and lanes; transit routes off the deck streets and passes over the slabs at the
  road clearance; elevated roads keep off the deck streets.
- **Checks** (five, only on a city with decks; 91 on the sample): `deck_columns` (reach,
  ground to underside, keep-outs), `deck_headroom` (5.5 m over the ground streets, the
  buildings under it below the slab, nothing else through it), `deck_light`, `deck_links`
  (two stairs and an elevator, one walkway component with the ground's, a ramp, the deck's
  lanes in the largest strongly connected part), `deck_levels`.
- **Blockout:** the slab per tile with its rail, columns, stair flights, elevator shafts,
  deck streets, junctions, crosswalks and sidewalks at their level, ramps; buildings under a
  deck in their own color; `render_deck.jpg` (view `deck`, also for `citygen rerender`): a
  section across the deck from beside it, the ground whole.
- **assetgen:** a brief of a building on a deck has `floor_grid.level` and `deck_m`.
- **Unreal exporter:** actors on a deck tagged `cg.level=1` (manifest `level`), the
  manifest's `decks` (id, level, top, district, slab keys), lanes and walkways with their
  `level` in `graphs.json` and a `levels` array in the flat graphs (data assets' `Levels`,
  `CORE_VERSION` 2); a road's own `level` (M7, M9) is not a deck's; the check's walk never
  takes an elevator, its traces cover each deck. A city without decks exports exactly as
  before. Unreal check: `docs/progress/M14/unreal/`.
- **Terrain:** a district with decks is levelled like a `flat` district (a slab on columns
  over level ground); the deck checks run only on a finished city (`checks.run_checks` also
  serves the build's early checks on the M2 model, before the columns).
Sample: `cities/vesper_bay_decks` (Vesper Bay Decks: Vesper Bay with a deck over Highcrest,
its long residential streets leaving room for the ramps; a separate city so Vesper Bay and
its sweep seeds stay as they were). Its golden hash is under `deck_cities`. A district
regeneration (`--district Highcrest`) builds a new deck. Terrain test: Cragmouth with decks on
Hollow and Ridgeback (`docs/progress/M14/cragmouth_decks/`, not a sample). Sample builds:
`docs/progress/M14/`.

The stage 1 fixes (three open items of M13 to M15) are in place:
- **District regeneration** (`streets.py`, `edit.py`): every district but the regenerated
  one is laid without the frame, exactly as in the old city; at the district's turn
  `_Ghosts` replays its old fill (`Frame.old_entry`, salted in `build.replay`) on a snapshot,
  and the districts after it are laid against those old streets with its new ones hidden.
  The shared frame is laid as in the old city unless the district's archetype changed. In the
  later passes a held street never joins a street the district laid anew
  (`Builder._laid_anew`; its frame streets are as they were), a held group's link starts at an
  old node or vertex (`Frame.old_point`), a highway access only at an old node, an avenue's
  dead end keeps the held link it had (`_end_target`), a new street meeting a bent held road
  at an old node makes the angle with both legs (`Builder._meets`). `_reconnect` also runs
  before the clean-up on the vehicle network (`_frame_join`) and picks a link at the district's
  junction angle. New streets keep off the old bored stretches (`Frame.bored_spans`,
  `Line.bored`, `BORE_PAD_M`). The splice reassigns seam blocks to territories (`_turfs`),
  takes walkway-island links from the new build and drops a sign with its slot. A
  regeneration that picks its seed draws a failing layout again (`REGEN_TRIES` 4, the fewest
  failures win). Every Cragmouth district regenerates with all 86 checks passing.
- **Level local junctions** (`terrain.grade(..., level)`): above; Cragmouth's retaining
  walls 84 to 133 km, cut and fill unchanged, corners stepping over 0.45 m 1223 to 451 (the
  rest at junctions with a primary road, an open item).
- **Deck streets' district:** `decks._twin` and `_ramp` set `district_ids`, so the blockout
  joins them as `d03.deck_road.<tile>`, `d03.deck_sidewalk.<tile>`.
Cragmouth and Vesper Bay Decks have new goldens; every other city is unchanged. Outputs:
`docs/progress/stage1_fixes/`.

M16 (water and ground detail) is in place, for stage 2's water (AG12) and ground cover
(AG13): the build ends with `build.water_ground` (after the gameplay layer) on the finished
city, `citygen/water.py` and `citygen/cover.py`, checks in `water_checks.py`, previews
`preview_water.py` and `preview_ground.py`:
- **Vertical frame:** on a flat city the ground stands `water.FREEBOARD_M` (1.5 m,
  `model.QUAY_DECK_M`, a quay's `deck_z_m`: the quay deck is the ground) over every water
  body, so the surface is at -1.5 (`WaterBed.surface_m`); on a terrain city the water stands at
  M13's level. No bed lies under the bed M9's tunnels assume (`tunnels.BED_M` under the ground
  datum, `water.max_depth`): the deepest water is canal 1.5, river 5.5, sea 10.5 m on a flat
  city, 3, 7 and 12 m on a terrain city.
- **Water bodies** (seas, rivers, channels, waterways) gain `depth_m`, `bed` (`WaterBed`:
  profile `flat` for canals, basins and marinas, `channel` deepest along the centerline with
  the depth by width along it, `along`, for rivers, channels, creeks and inlets, `shelf` for
  the sea, falling over `reach_m` 250 m; material) and `flow` (`Flow`: downstream toward
  `flows_into` or the mouth with the centerline oriented that way, a slow tide in canals and
  inlets, still in basins, marinas and ornamental pools, tidal for the sea); the sea its
  `exposure` (`Exposure` zones: open, sheltered under 1500 m, harbor under 400 m of mean fetch
  over 16 integer directions on a 32 m raster, the map edge counting as open sea). All left
  out of the JSON while unset (`model._m16`).
- **Banks** (`banks`, `model.Bank`, id `<water>.bank.<anchor>`): the land's edge against the
  water (`water.shore_lines`: the rings of land minus water without the map edge, water on the
  left) sampled every 4 m and classed by what stands there: the model's quay (`quay_id`;
  `height_m` None: the quay's `deck_z_m` is its height, one field), a canal wall (canals,
  basins, inlets, marinas, ornamental pools; a building within 2 m), a road embankment (a road
  within 5 m, `segment_id`), a beach (a beach open space, or a sea shore with a park or green
  and 20 m clear of buildings), a marsh edge (a marsh open space), riprap (port and spaceport
  shores, a megasite, a building within 6 m) or a natural bank; runs under 12 m join their
  longer neighbor (never a quay). `width_m` is the slope's run from the line out to the
  waterline (inside the water polygon: a wall's thickness, else slope by kind times the
  height, at most 0.3 of the water's width at the run's lower quartile, steeper kinds where
  it does not fit), `toe_m` the depth at its foot. A bank keeps to one water body and one
  district and is classed only on its own district's buildings, roads and open spaces.
- **The bed at a point** (`water.Beds.depth`, `depth_many`): the nearest bank (rounded
  distance, ties to the first, never GEOS's pick), 0 up to its waterline, then toe + (D - toe)
  ramp((d - width) / (reach - width)), ramp linear (shelf, flat with a 4 m reach) or u (2 - u)
  (channel, the reach the local half width); `bed_z` in M9's frame.
- **Ground cover** (`ground_cover`, `model.GroundCover`, id `<source>.gc.<anchor>`, else
  `<district>.gc.<anchor>`): per district, its ground minus the water, the right of way (each
  segment's cross-section as the blocks take it, the junctions), building footprints, solid
  site elements and stairs, elevators, vents and portals; pieces from open spaces, lot yards,
  flat site elements, megasites and the land left between them (parts under
  `cover.SLIVER_M`, 3 m, are curb corners, not open land). Eleven kinds (`COVER_KINDS`: the
  scope's ten and `paving` for plazas, forecourts and yards) by what a piece is and its
  maintenance (district wealth and danger, what it is; megasites are kept); attributes
  maintenance, wear, shade (4 m raster: share of 8 directions with a building above 45
  degrees within 60 m, 1 under a deck), moisture (0 from 60 m off the water), slope (M13) and
  `desire_lines` (walkway paths across a lawn worn by the nearest street's crowds, and
  shortcuts across a lawn between walkway ends where the way round is 1.35 times longer).
- **Checks** (three, on a city with M16's data: 95 on a flat sample with M17's and M21's,
  100 on the deck sample):
  `water_beds` (every body's data, no bed under M9's, tunnels under the water with 1.5 m of
  backfill under the bed as it is, bridge foundations in the water on bed no deeper than their
  footing), `water_banks` (the banks cover every edge once; quays, embankments, widths,
  toes), `ground_cover` (no overlap, nothing under a building, road or water, the open land it
  leaves only curb corners); a regeneration adds `regen_locality`.
- **With M10:** `banks` and `ground_cover` are in `ids.KEEP` (named by their stage), in
  `ids.REFS` and `ids.ORDER`; the splice leaves them out (and out of its closure) and
  `edit._regenerate_once` runs `water_ground` on the spliced city, then
  `water_checks.check_locality` against the old one (outside the district and `SEAM_M`, 60 m,
  an M16 row changes only within 60 m of a changed input, `water_checks.INPUTS`: the splice's
  own seam, a crowd density or a walkway, can reach farther); `overrides.apply` runs it again
  after its edits.
- **Blockout:** water and the sea at -1.5 on a flat city (the sea sheet 5 cm lower), a bed
  heightfield per tile (`city.bed.<tile>`, 8 m cells; on a terrain city the ground grid carries
  M16's beds), banks as bands from the line down to the toe joined per district, kind and tile
  (`bank_<kind>`), the ground cover joined per district, kind and tile in a color per kind
  (`cover_<kind>`) in place of the open spaces at the ground, bridge piers from the bed; the
  plan's `swim` boxes (`blockout.swim_volumes`).
- **Unreal exporter:** a water `PhysicsVolume` per swim box (`Importer.swim`), a material per
  cover kind (`docs/unreal_export.md`, M16).
A city without water or open land builds as before. Every sample has new goldens. Sample
builds: `docs/progress/M16/`.

M17 (road network repair, from the first run-through) is in place:
- **Dead ends** (`streets.settle_dead_ends`, at the end of `clean_graph`, on the noded
  edges, in rounds): a local road's dead end runs on to the road straight ahead
  (`DEAD_END_REACH_M` 60, a junction there or at a node of it within `MIN_JUNCTION_GAP_M`, 8 m
  for paths, turning at most 35 degrees, at the district's junction angle; on land, off closed
  ground, crossing nothing but under a deck high enough: `under_deck(..., cls)`, a path under
  4.5 m, `PATH_UNDER_CLEAR_M`, which `node_lines` also lets pass under), or joins a dead end
  facing it (30 m); an M1b road's dead end runs on the same way as a short street
  (`end_link`); else it stays as what it is, `RoadNode.attrs.dead_end` (`DEAD_END_KINDS`:
  `map_edge`, `water_end`, `park_gate`, `plaza_gate` within `GATE_M` 8 m past its half width,
  30 m for a primary road; `site_gate` within `SITE_GATE_M` 40 m of a megasite reserve, the
  road `megasite_access` asks for; `path_end` on a path; `cul_de_sac` with a turning bulb
  that fits, `attrs.turning_head_m`, street 12, service 10, alley 8 m, a primary road's half
  width and 4 m; `deck_end` on M14's deck spokes; `traced_end` on a traced road, as drawn),
  else its street goes back to its last junction (a vehicle road under `CUL_DE_SAC_MIN_M`
  40 m from it, or with no room for a bulb). A run-on meets the roads at its junction at the
  district angle there, legs measured 10 m out as `fix_angles` and `junction_angles` do.
  A `water_end` is beside the water the model keeps (`Builder.water`: sea, water bodies,
  waterways; not `wet`'s sliver between the land and the map edge, which grows edge
  promenades); a dead end within `ON_ROAD_M` 0.1 m of another road is noded onto it (an M1b
  road ending on another, off it by the grid's rounding).
  A dead end reaching into another road's right of way is cut back clear of it (`_poke`; a
  primary road's dead end cuts the local road it reaches into, `_poked`); a local road laid
  along another (rights of way overlapping by `OVERLAP_M2` away from the nodes they share,
  `_reach`) goes (`_overlaps`, never one whose loss parts the vehicle network, `_splits`);
  `fix_angles` and `fix_duplicates` run again after each round of run-ons, and
  `pedestrianize_islands` after the repair (a cut-back can leave a lane island). A cut-back
  never takes a primary road (`_chain` stops at one); M1b is as it was (the sweep showed
  that changing its forks and lenses moves every city's road search). `junctions.build`
  draws the bulbs from the tag.
- **Junctions** (`junctions.py`): each leg's cut reaches past where its right of way overlaps
  another leg's (`overlap_cuts`: an acute corner, a leg that bends in the junction, a gore);
  a road's two junctions share `CUT_SHARE` 0.9 of it by need (`share_cuts`, the old cap was
  0.45 a side); a leg that bends gets its band to the cut; a degree-2 node where two roads
  meet at an angle is a `bend` junction (`Junction.shape`, `bend_polygon`); where rights of way
  still overlap past the cuts (a fork, a crossing at a small angle, a corner with no room for
  its fillet), the junction polygon takes the shared pavement (`shared_pavement`); two
  primary roads, or two roads at a node they share (a hairpin), still sharing pavement past
  it give the overlap to the junction it touches or their node's (`absorb_shared`). M13's
  grading still holds a junction's height at most 0.45 of a leg out (`Local.cuts`; M18
  levels junctions).
- **Checks** (`network_checks.py`, 4 more, 90 in all, 95 on the deck sample): `road_dead_ends` (every dead end tagged, the tag
  true of where it is, a cul-de-sac with its bulb) and `road_overlaps` (rights of way of two
  roads within 4 m in height overlapping more than 25 m2 outside every junction polygon, the
  run-through's measure on the 1 cm grid: GEOS's floating overlay takes two corridors meeting
  end to end on a 45 degree line for overlapping) with the street checks; `bridge_clash`
  (road, pedestrian and transit bridges apart in plan or by the lower one's clearance plus the
  upper deck) and `road_building_clash` (no road right of way over a building mass at its own
  height, 5 m of headroom) after the building checks. Heights over the ground on a terrain
  city; M10's regeneration runs them through `check_all`; a held road is never extended, cut
  or dropped (`_held`), a new street meets an old road only at its nodes (a facing join onto a
  held road's end at an old node is one). Under a regeneration's frame
  `local.join_walk_islands` lays the old city's walkway-island links away from the district
  again as they were (`Frame.islands`) and links a group the new streets cut off at its
  nearest point within `ISLAND_SEAM_M` 40 m of the district (else as before), so a
  regeneration moves no walkway far from it; a fresh build is unchanged.
Sample builds, the run-through's measures before and after: `docs/progress/M17/`.

M18 (junctions and ramps, from the first run-through) is in place:
- **Grades** (spec `highways.grades`, `spec.Grades`; `elevated.grades(gr)` sets the module's
  values for one road stage, `roads.build_roads` wraps it): viaduct runs 6% design and 7% at
  most (`RUN_GRADE`, `RUN_MAX_GRADE`), ramps, loops, flyovers and stack ramps 7% and 8%
  (`GRADE`, `MAX_GRADE`), bridge approaches 6.5% (`APPROACH_GRADE`), 30 m vertical curves
  (`CURVE_M`); a ramp's search still runs as long, and a loop is as big, as M7's at 5%
  (`SEARCH_GRADE`: the steeper ramp descends sooner within it), and `_ramp` takes a longer
  span where the shortest runs into another ramp (`clear`). A two-way highway one direction
  of which no lane can enter (a trumpet's stem past the flyover's landing where no near ramp
  arrives) carries the other only (`junctions.one_way_stranded`).
- **Junction levels** (`junctions.level_legs`, in M2 after the polygons and `absorb_shared`):
  every leg of a junction held at its node's height out to where it leaves the polygon (the
  farther of its run to the cut and its exit, `leg_exit`) and `LEVEL_OUT_M` 10 m beyond, at
  most half of it, then back onto its own profile at `catch_grade` (a run's maximum on primary
  roads, a ramp's on ramps and local streets): the profile clamped between cones from the held
  stretches (`_levelled`), never moving a locked stretch (bridge spans, roads crossing over or
  under it, `_locks`); where it would, the junction is raised to its highest leg at its run
  (at most `RAISE_MAX_M` 2.5 m, M7's 3 m for a local junction, never under another road),
  else it keeps the slope. A leg's far end always keeps its node's height. Tunnels,
  viaducts, a deck's streets and ramps, footbridges and held roads keep their profiles. On a
  terrain city the grade lines hold primary roads too, at most `terrain.LEVEL_GRADE` 2% over
  their junction and 10 m past it, where the natural ground there is no steeper than
  `LEVEL_SLOPE_MAX` 4%; local roads keep M13's runs (to the polygon's edge, none at a
  junction with a primary road: longer, a hillside's short streets went flat and Cragmouth's
  fills passed 18 m). The grade-line solver's edges are directed (`terrain.grade`: the ground
  rises from one station to the next by at most the class's grade, or the z profile's own
  where steeper, less what the z profile climbs), so a steep ramp or approach no longer
  leaves its stretch no room (a symmetric cap of zero there chained hillsides flat).
- **Surfaces** (`junctions.surfaces`, after the grading): `Junction.edge_z`, the height of
  every exterior vertex over the node's ground, on every junction not flat at its node's
  height: a vertex on a leg's cut line (square to the leg where it leaves) at the leg's height
  there, the curb between two legs linear along the ring (`surface`, `anchors_of`). The
  blockout draws such a junction as a face through its vertices (a drape part; on a terrain
  city every junction, over sea level) and cuts its roads back to where they leave it
  (`blockout._trimmed`); AG7's junction piece takes its vertex heights from it.
- **Embankments** (`elevated.road_embankments`, before the road columns): retained fill
  (structure `embankment`, `<road>.emb<k>`, `attrs.road_id`, `s0_m`, `s1_m`, `width_m`)
  under every raised road over land lower than `EMBANKMENT_M` 4.5 m; columns only where it is
  higher (`SUPPORT_MIN_UNDER_M`). The blockout fills under it in the road's `<road>.deck`
  object; AG7's road piece covers it and fills under those stretches.
- **Crossings by need** (`junctions.plan_signals`, `plan_crossings`; per district
  `junctions.signals` and `junctions.crosswalks`: auto, fewer, none): signals where two
  primary roads meet; where a street meets a primary road (or a four-way street crossing in
  the corporate core, transit hub and midtown) only with no signalized junction within
  `SIGNAL_SPACING_M` 120 m along either road (`straight_on`; 200 m in the old town and
  entertainment market, `SPARSE_ARCH`; twice that for "fewer"), greedily from the west, both
  ways round; crosswalks on every approach of a signalized junction and across an
  unsignalized junction's avenue where none is within the spacing; widths by class (street
  3 m, avenue and highway 4 m, 5 m on a downtown avenue, none on alleys and service roads,
  `crosswalk_w`); unmarked crossings elsewhere.
- **Checks** (98 in all with M21's two and M16's three, 103 with decks): `ramp_grades`
  (ramps 8%, runs and approaches 7%; `road_grades` caps every road at 8%), `junction_levels`
  (every leg meets its junction's surface within 2 cm where it leaves, the surface level
  across it within its class's cross slope, 2.5% primary, 3% else, the curb between two legs
  running evenly from one's height to the other's), `crossing_spacing` (signals and marked
  crossings only where called for and spaced, crosswalk widths); `ground_grades` lets a road
  be as steep as its own z profile; the reports give each city try's failing checks
  (`city_tries[].failed`) and the stats `elevated.grades`, `embankments`, `junction_levels`.
- **Found on the new layouts:** M9's pedestrian underpasses keep their passage off column
  footings (`tunnels._underpasses`: a transit column in a highway's median); AG7's junction
  piece leaves out a sidewalk corner pad that would fold over an earlier one
  (`walks._corners`); AG3's `Band.rehome` drops the ground windows a moved door takes the
  place of (it looked for kind `window`, the windows are `win`, so a rehomed door never
  found room among them: the small test city's new layout left a villa's entrance with no
  door; `GEN_VERSION` ag5.2); M10's override edits drop the walkways that hang on a building
  or skybridge they remove (`overrides._drop`: door, lobby and elevator links, the deck), and
  in a regeneration a junction its held roads meet at one height takes it
  (`junctions._held_heights`: the old build raised it, M1b gives the node back lower);
  lights and furniture stand on an embankment (the props' headroom reads
  `vegetation.overhead(..., fill=False)`, their ground structures leave it out: its road's
  own keep-outs cover it) while trees keep off it (`overhead` with `fill`, as the
  tree-clearance check), and M2's crossing locks and overhead test measure on plain arithmetic
  (`junctions._crossings`, `_overhead`: `terrain.crossings` projects with GEOS and runs
  after M2). On the merged layout a deck's skybridges clear its ramps (`Ctx.sky_roads`, from
  the deck top) and every level's keep out of the district's buildings on its other levels
  (`skybridges.Space(..., others)`). `GEN_VERSION` m18.2 (on M21's m21.1 and the assetgen
  fixes' agfix.1); AG13's ground scatter keeps clear of a neighbouring piece's desire line
  that reaches across its tile's seam (`ground.gather` `desire_near`, as the clearance check
  does). Merged with M21, M16, the assetgen fixes and AG13.
Sample builds: `docs/progress/M18/`.

M19 (transit structures, from the first run-through) is in place, in `citygen/transit.py`
(checks in `transit_checks.py`):
- **Portals only at stations:** a sky tube through towers picks each stop's host tower
  before its route (`_hosts`: a portal-sized tower in the stop's zone that a straight tube
  through its middle leaves with `HOST_RAY_M` clear on both sides, nearest the line's way);
  the stop moves into it (`tower_id`, its clear headings in `Line.heads`) and only hosts are
  portals in the costs (`Line.hosts`; `sky_pass` takes the set), so every other tower is
  climbed or gone round. A tube that can neither is routed again taking the removable
  towers in its way out (`Line.cut`, `TOWER_CUT_W`; Vesper Bay's Crown Loop, whose two stops
  are walls of 130 to 216 m towers). Lines are routed apart, so a tube whose host another
  line takes out is routed again with those towers barred as hosts (`_reroute_hosts`,
  `Line.no_hosts`). A tube whose track still turns tighter than its radius as
  `transit_curves` measures it (`_fails`) is routed again with each tower `_hosts` chose
  (`Line.chosen`) barred in turn, the best kept (`_rehost`, issue #143: the stack demo's
  Crown Line left its Corporate Core tower on a 25 m hook toward a Stacks tower passed only
  east to west); a line that passes is never touched. A tower hosts one station
  (`Builder.hosted`); a pylon station slides along its line until its elevator core is
  clear of other lines
  (`_core_spot`, round a loop's seam).
- **Clearances:** `SIDE_PAD_M` 6 m (2 before) from buildings in plan, or their clearance
  in height; roof items a line passes too close over go (`_roof_hits`); the profile never
  under `floor_z` (8 m over the roads under the deck and its cap beams), `over_deck` (6.5 m
  over a raised road, plus a cap beam and a meter so a frame may straddle it), 6.5 m between
  a line and the lines before it (`_line_crossings`, over or under, `track_rec` with the
  platforms' width), the same under a road deck passed under. Default altitudes up
  (elevated rail 14 to 20 m, monorail 16 to 26; allowed 8 to 26 and 10 to 32).
- **Supports** (`Builder.supports_of`, `Keep` the vectorized keep-outs): evenly spaced
  between fixed points (an open line's ends, each platform's ends) and carriers (portal
  towers, ground stretches, a nexus platform, a sky station's elevator core) at the mode's
  span (`support_spacing_m` is now (span, longest): rail 30/45, monorail 25/40, maglev 50/80,
  sky tube 420/600), each moved at most `SPAN_MOVE` (15%) to free ground: a column under
  the line (`form` column; a sky tube's a plain pylon, `mast` with the sky tube fixes'
  `supports: mast`), a pier in the water within `pier_reach` of
  the shore (the navigable channel down the middle, `CHANNEL_M` wide at most; the open sea
  has none), else a portal frame (`leg<n>a/b` columns either side within `FRAME_REACH_M`, a
  `beam` structure `cap<n>` under the deck, `attrs.frame`) or a cantilever bent (one column
  within `CANT_REACH_M`, its arm past the deck); then any gap over the longest span filled
  wherever a support stands; M18's embankments (`elevated.road_embankments`, built after the
  transit from the same roads) are ground no support stands on. Before the stations, a dry
  run (`_support_room`, `_Dry`) takes out the low removable buildings that alone keep a
  support off a gap. A gap still longer is a cable-stayed main span over a navigable channel
  or a raised road (`MAIN_SPAN_M`: rail 400, monorail 250, maglev 300), else a note; the
  line's `attrs.spans` lists its truss, cable and gap spans; sky tube masts (`mast` only)
  carry `mast_top_m` and their `stays`.
- **Checks:** `transit_supports` (lone columns within 0.5 m of the line, frames' beams under
  it at the deck's underside, none on a road embankment, piers clear of the channel, spans
  within the longest, an end overhanging half of it at most), `transit_clearance` (3D along
  the line: masses and roof items, a portal only with a station in it, other lines' tracks
  and structures, the roads, raised decks, beams over roads), `transit_altitude` knows the
  new needs.
- **Blockout and stage 2:** beams in `transit_support`, masts (two legs, stays) and pier
  footings (`_mast`, `_pier_cap`); AG14 draws them all (`transit_column`, `transit_beam`).
  New structure kind `beam` in the model.
- **Sky tube fixes** (issues #94 and #97, after run-through 2): spec
  `transit.sky_tube.supports` and `lit_rings_every` (defaults for every sky tube line; a
  line's own `supports` and `lit_rings_every` win; `TransitLine` validates them on sky tubes
  only, `Transit.sky_tube_style`; mode defaults `presets.SKY_TUBE_SUPPORTS` "pylon",
  `SKY_TUBE_LIT_RINGS_EVERY` 1; left out of the filled spec, so `spec_sha256` and every city
  without sky tubes keep their bytes). With `pylon` every sky tube support is a plain pylon
  at M19's positions (`_column`'s form `column`, `_masts` not run), drawn as before M19 (a
  shaft and a cradle across the tube, blockout and AG7); `mast` gives M19's masts back
  record for record. A tube's rings (`tube_rings`: n evenly spaced along the whole line
  near `RING_M` 10 m, n a multiple of the frequency, a loop's from its seam, an open line's
  half a spacing in; ring k lit when k is a multiple of it) are cut into the 400 m tube
  pieces (`attrs.rings`: [distance along the piece's own line, lit] for its stretch
  [s, e) of the line); the line's `attrs.support_style` and `attrs.rings` (count, lit,
  every, spacing_m). AG7 draws the ribs there with an LED band on each lit one.
Sample builds: `docs/progress/M19/`; the sky tube fixes: `docs/progress/sky_tubes/`.

M21 (cyberpunk massing) is in place, in `citygen/forms.py` (with `massing.Plate`, and the
neighbor rule in `buildout.select_forms`):
- **Model:** a form is prism masses, so every check and consumer reads it as it is. A tower's
  shaft stands on its podium on a base plate (`massing.Plate`: a rectangle with sharp, cut
  or rounded corners, a circle, a four-centre oval); a band of a twisted, tapered or leaning
  shaft (role `band`) is that plate turned by `Mass.turn_deg` and scaled by `Mass.scale`
  about the form's pivot, then moved by `Mass.shift_m`. `Building.form` names the form
  (`kind`), its `crown`, whether it is a `tower` (podium towers, towers and landmarks 40 m
  and taller) and its height `band` (`buildings.TOWER_BANDS_M`: 40, 56, 78, 110, 154, 215,
  300 m), the `pivot`, the shaft's `masses` (bottom up) and its `params` (twist per floor,
  taper, lean, chamfer, ...). New fields are left out of the JSON at their defaults.
- **True arcs:** `Mass.arcs` (center and radius to the millimeter, start and sweep in
  degrees); the footprint is cut by `massing.arc_steps` (a step of 2 sqrt(2 SAG / r), plain
  arithmetic) so no chord sags over 1 cm, 2 cm at most once on the grid (`MS.circle`,
  `ellipse`, `sector`; no more 12, 20 or 32-gons, megasite tanks and pads included).
- **Forms** (`forms.SHAFTS`): box, chamfer, rounded, setback, round (in drums), oval, taper
  (bands of 2 or 3 floors), twist (a band a floor, two over 48 floors, at most 3 degrees a
  floor, 180 in all), lean, stack (3 to 5 turned and offset blocks, each over 35% on the one
  under it), cantilever (blocks reaching out over the podium), split (two shafts, a slot and
  links), garden (sky gardens: a core and corner columns, a green area `sky_garden`), gate (a
  void through the upper floors), exo (columns standing off the facade, belts), pods (capsule
  pods on a core); towers on odd plates (no rectangle fits) box, setback, taper, terrace or
  wedge (`tower_poly`). Crowns: flat, tiers, sloped, cut, halo (a ring on struts), mast,
  spire. Complexes' towers take box, chamfer, rounded or setback (`COMPLEX_FORMS`: their
  skybridges need facing facades), and a complex avoids the forms of the complex towers built
  before it near it (`Ctx.placed`). Slabs: curved (`MS.sector`) or stepped
  (`forms.slab_form`); megabuilding towers with cut or rounded corners on some.
- **Variety:** spec `District.variety` (presets: corporate core 0.9, midtown 0.75, transit
  hub 0.6, entertainment 0.55, research 0.5, megablock 0.35, spaceport 0.3, residential 0.2,
  old town 0.15, industrial 0.1) sets the draw weights (`forms.weights`: box and the mild
  forms where low, bold forms from their `BOLD_MIN`) and how far twist, taper and lean go.
- **Neighbor rule:** a lot tower draws its order of forms from its own generator (`_forms`,
  salts by `FORM_INDEX`) and, in phase b, every form that fits (`forms_ok`) and the heights
  in the bands beside its own (`band_heights`; under 40 m from the first band). Then the
  parent (`select_forms`, tallest first, the complexes' and landmarks' towers and in a
  regeneration the old towers outside the district fixed, `Frame.old_towers`, and a new tower
  on an old one's lot given its old form and height, so the city outside comes back as it
  was) gives each the first form no tower of another property within 151 m has in its band,
  else a band beside;
  the lots that change are built again in their chunks (`rebuild`, `force`).
- **Checks** (two more): `building_forms` (arcs within 2.1 cm of their footprint, twist at
  most 3 degrees a floor, every mass above the building's floor resting on or fixed to
  another of its masses: it found M3's megabuilding decks hanging past a mid setback, now
  placed only where both towers reach them, `_deck_held`, and a cluster's tower beside its
  podium piece, now the piece under it), `tower_neighbors` (towers of different owners
  within 150 m, by footprint centroid, never share a form and a band). Skybridges keep stage
  2's corridor margins clear of every mass (0.2 m beside, 0.3 m over: `CORRIDOR_SIDE_M`,
  `CORRIDOR_TOP_M`) and a bridge through a traced or pinned building (placed after the
  bridges) is taken out (`buildout.bridges_clear_of`); a sky tube portal stays under a
  tower's shaft, not its mast or spire (`transit.Bld.body`, `THIN_ROLES`).
- **Blockout:** a mass with arcs drawn smooth along them (`set_sharp_from_angle`, 25
  degrees); accents for mast, halo, strut, frame, link. **Exporter:** a building's form in
  the manifest (`form`) and tagged `cg.form=`. **assetgen:** the brief carries arcs, plates
  and the form; `shell._simple_mass` draws bands and masses curved all round simply (the
  plate extruded, a spandrel and a ribbon of glass a floor) until AG15; skybridges never land
  on bands, frames, pods, columns, halos or masts; a sky station's platform floor is under the
  tube's lowest point over it (`connections.station`, as `_beside`: a rerouted Delta line put
  a station on a 7.5% grade, and the level floor from the tube's first point met the tube);
  a punched concrete wall under a patchwork body keeps its own wall where the patchwork
  finish has no patch genes in its group (`shell._finish`; it raised `KeyError`); no
  balcony hangs under a floating block (`shell._hangs`); `GEN_VERSION` m21.1. Odd-lot tiers
  are kept neat (`forms.neat`: no corner under 40 degrees, no edge under 1 m).
Sample builds: `docs/progress/M21/`.

M20 (props, plants and signs, from the first run-through) is in place:
- **Under structures** (`vegetation.Overhead`): everything over the ground a plant could grow
  into or a prop stand under, its underside measured along the structure where the thing
  stands (a raised road's or ramp's surface less `ROAD_DECK_M` 1.8 m at the thing's station,
  over its crown; transit decks, tubes and beams by their line less `deck_m`; canopies,
  portals, M14's slabs, skybridges and masses over the ground; M18's embankments a fill from
  the ground up, and a road under 0.5 m of underside a fill over its own width); heights over
  the ground at the point (masses and skybridges from their base, roof plants in their
  building's frame, `roof_lift`). Every plant (roof plants too) keeps `HEADROOM_M` 1 m under
  it (`fit_crowns`), every prop standing too (`props._headroom`; a street light becomes a lamp
  hung at the underside right over it, z its underside). No street tree on a raised deck.
- **On their surfaces**: a thing on a road's sidewalk or carriageway (`Cand.on`) stands on
  that road's surface at its station (`Ctx.settle`; a raised road's deck; one off a raised
  road's deck, a signal beside a ramp's crossing, is left out); the quay deck is the ground
  (railings and benches at z 0: a quay's `deck_z_m` is its height over the water, AG7 paves
  it at the ground, one height), boats float on the water (`Ctx.water_z`: -1.5 on a flat
  city, M13's level on terrain); wall mounts at a height their wall has there and under
  anything over the spot (`Ctx.mount_top`: shop signs smaller and lower under low eaves,
  awnings under an overhang, wall lights, overhead cables tied under both walls' tops), AC
  units and facade greenery on the facade of their floor, an overhanging floor's own
  (`Ctx.facade_spot`).
- **Signs** (`citygen/signage.py`, called from `gameplay.build_sign_slots`): spec
  `District.signage` (`density`, `kinds` of billboard, banner, holo; archetype defaults
  `presets.ArchetypePreset.signage`, `signage_kinds`: corporate core 0.85, entertainment
  0.95, midtown and transit hub 0.8, old town 0.6, megablock 0.45, spaceport 0.4, research
  0.25, industrial 0.15, residential 0.12; not filled into the spec, so earlier stages keep
  their bytes). Facades: edges of prism masses of plane faces (not M21's bands, frames,
  columns, struts, halos, masts, pods or links; off arcs), facing a highway, avenue, street,
  pedestrian street or plaza (`FACE_REACH_M`), open in front (`Obstacles`: nothing within
  `OPEN_M` 3 m over the ad's height, the building's own masses too), above the shop signs and
  10 m up, apart per facade plane, off skybridge landings and the neon band. Neon billboards
  (kind `billboard`, mount `facade`, `attrs.orientation` landscape or portrait, a level every
  `LEVEL_M` 30 m of facade, `BILLBOARD_P` 0.7 times density and facing), neon banners (kind
  `banner`: 3 to 10 floors at a facade corner, a pair `.a`/`.b` naming each other in
  `attrs.wrap` where the facade round the corner is open), holo-boards over tower roofs (50 m
  and taller, over the roof under a mast or spire, `roof_of`) and in front of facades (mount
  `front`, `HOLO_OFF_M` 3 m out, high up, `HOLO_CLEAR_M` round the image); every billboard
  and banner `attrs.lit` neon, M3's roof billboards too. Ids from the building, kind, cell and
  height (`<bld>.slot.billboard.e123n45.z30`).
- **Checks** (two more, 100 in all on a flat sample, 105 with decks): `prop_support` (every prop, plant and roof item on a surface at its
  height within 2 cm: the ground, a road whose corridor holds it, the water, a roof, a wall
  that spans it, a deck's underside it hangs from; none on the ground in a fill; every prop
  standing 1 m under what is over it) and `plant_headroom`; `tree_clearance` keeps its
  facade, sight line and feet rules; `sign_slots` covers the new kinds (lit, orientation,
  plane facades, open in front, a wrapped pair meeting at its corner, holo-boards in front
  of a facade and clear round their image).
- **Blockout**: the large ads as instanced prototypes (`sign_billboard`, `sign_banner`,
  `sign_holo`; `sign.<kind>.<tile>`, materials `sign_ad`, `sign_banner`, `sign_rim`,
  `sign_holo`), on terrain lifted by their building's base; props and plants on a roof lifted
  by their building's base. **Exporter**: through M15's instancing (emissive in
  `unreal.EMISSIVE`). **assetgen**: AG8 draws banners as neon bands with a brand's name
  (AG6: tall, neon), holo-boards in front of a facade with a projector on an arm off the wall,
  billboards lit as neon with a tube round the face, and replaces the blockout's sign
  prototypes; the brief leaves holo-boards in front of a facade off its walls; `GEN_VERSION`
  m20.1 (on the fast import's m18.3).
- **With M18 and M13** (found on the merged builds): the one `Overhead` replaces M18's
  `overhead(..., fill=False)`: a prop on a low road's sidewalk stands on that road (`own`)
  over its embankment, a tree never does; nothing stands on the ground inside a fill
  (`props._off_fills`: signals, scaffolding, market gates; Vesper Bay had taken five more
  tries over them), median barriers fit under what is over them as `prop_support` measures
  (`_barriers_clear`); `Ctx.facade_spot` takes heights in the building's frame and returns
  the lift at its spot (AC units and ivy on a slope), shop signs and awnings measure their
  wall's top where they hang (`Ctx.reframe`), overhead cables find their walls 5 cm inside
  the check's reach (`CABLE_SLACK_M`).
  A building's ads stay apart across close parallel planes as `sign_slots` measures them
  (`signage._apart`: a setback's face and its mass's; the stack demo's banners).
Delta on main (M19, M18, M21, M16): props off their surface 5,260 to 0 (2,903 quay
railings, 730 AC units, 299 street lights, 186 shop signs, 171 ivy, 151 signals, 146
benches, 72 boats, ...), plants reaching what is over them 7 to 0; facade billboards 214
to 2,750 (1,154 landscape, 1,596 portrait) and 939 banners, holo-boards 57 to 201 (112
over roofs, 89 in front of facades), the 963 roof billboards lit; shop signs 52 fewer
(walls too low for any). Every sample, the pinned, stack and deck demos and Cragmouth
pass every check (100, 105 with decks).
Sample builds: `docs/progress/M20/`.

The park paths fix (between milestones, from PR #67's open items) is in place:
- **Park paths** (`citygen/parkpaths.py`, called from `local._build_local` after the blocks):
  a path from each park's, plaza's, pocket park's, market's, garden's, promenade's or
  beach's middle to the nearest point of each ground walkway within 30 m (the walkway split
  there, `split_edges`), up to four 25 m apart, those after the first at most `PATH_OUT_M`
  20 m outside it; straight where it keeps `PATH_CLEAR_M` 0.75 m
  off every lot, the water and the megasite reserves, else the shortest bending at the open
  space's own corners (taken in by as much, `route`), else one that may run along a lot's
  edge but never along the line between two lots (`Blocked`, `BETWEEN_M`). Lots come from
  M2, so a path off the lots is off M3's buildings.
- **Passages** (`passage`, `_carve`): an open space no path reaches gets a strip
  `PASSAGE_W_M` 3 m wide along the shortest run of lot boundaries between two lots (within
  150 m) to a point a straight path reaches a walkway from, cut from those lots (each kept
  whole, with 65% of its area and its frontage; never a complex's, a traced or a held lot,
  lot attrs `passage`) and joined to the open space (attrs `access` passage, `passage` the
  run); one still without a way in says why (`access` none, `no_access`).
- **Sidewalk corners** (`junctions._corner_point`): where the two sidewalk lines cross under
  180 degrees, else on the gap's bisector, moved toward the node until it lies on a leg's
  strip or the junction's right of way (`_on_row`, `_jrow`); the middle of the two sidewalk
  points at the cuts, which it was, lay in the block's corner once the cuts outgrew the road
  (no sidewalk, M17's long cuts). `_walk_offset`: a road with no sidewalk is walked 1 m in
  from its edge.
- **Every ground walkway off the lots** (`keep_off`, after the island links): a stretch that
  cuts into a lot is led round it past the lots' corners (0.3 m out); a deck's walkways off
  its upper lots too.
- **Entrances** (`buildout.link_entrances`): an entrance whose straight link to its nearest
  walkway cuts into a building mass at its level (`_Masses`, 0.1 m in, masses under 2.5 m
  over the building's floor) links to the nearest one it reaches clear (`_Level.reachable`,
  searched to `RELINK_M` 60 m past the nearest walkway, `reach`; on another landmass where
  its own has none), else moves along its own facade to where it does (`_move_entrance`),
  else is led round the buildings (`_Masses.round`, `parkpaths._detour`: a door path of its
  own, which it then names); a megasite building's entrance joins its site's own paths or a
  gate (`_site_door`, the site walk split there, `_cut_at`); one with no way out says so
  (`Building.attrs.walled_in`, the door path `walled_in`). Every entrance names the piece of
  a split walkway its link meets (`_piece_of_foot`). A lobby path is led round the buildings
  where its straight line is not clear; a megasite gate moves along its reserve's edge to
  where a straight link is clear (`_move_gate`); transit station links
  (`transit.Builder.foot`) take the nearest walkway they reach clear, else a path round, and
  an elevator core standing in a building leaves through it (`attrs.building`).
- **Checks** (`network_checks.py`): `walkway_building_clash` (no walkway but elevators and
  skybridge decks through a building mass standing on its floor at the walkway's height over
  the ground, a 5 cm graze passing; a door, lobby or station path may enter its own building,
  a station's or a gate's walkways its megasite's; no entrance's straight link to its walkway
  or that walkway's later pieces through a ground mass of its level, as `_Masses` tests;
  walled-in entrances and station stairs, M19's, counted in notes until the access fixes,
  which fail them) with the finished checks, and `park_access` (every such open space has a
  park path or a walkway within 3.5 m, or said why until the access fixes; park paths start
  inside it and stay off the lots; islet parks, land without a district, in a note) with the
  street checks: 102 checks on a flat sample, 107 with decks.
- **Stats** (`report.json`): `open_paths_bent`, `passages`, `passage_m2`, `open_no_access`,
  `walkways_led_round_lots`, `walkways_in_lots`, `entrances_relinked`, `entrances_moved`,
  `entrances_led_round`, `entrances_blocked`. No exporter change: the walkway graph keeps its
  format.
Sample builds, the measures before and after: `docs/progress/fix_paths/`.

The access fixes (issues #86, #87 and #91, after run-through 2) are in place:
- **Ways into open space** (`parkpaths.open_paths`, a second pass over the open spaces the
  park paths and passages leave without a way in, so a city with none keeps its bytes): a
  path to a neighbor open space's park path within 30 m, joined at its nearer end (that
  open space's middle or its foot, so no park path is split; `Attach(W, parks=True)`,
  attrs `access` via_open_space), else one to a walkway up to `UNDER_REACH_M` 90 m away passing
  under the raised roads between (`low_roads`: every carriageway lower than `UNDER_DECK_M`
  5 m, over M18's embankments, and the junctions of nodes that low are blocked, a covered
  tunnel's lid is not; `under_paths`, joining only a walkway whose road is at grade at its
  foot, `foot_z`, as a raised road's sidewalks are at z 0 in the walk graph; `access`
  under_road, the path `attrs.under_road`, which M7's road columns keep off,
  `elevated.column_free`; `access` path where it crosses no road); both new kinds block the
  carriageways at grade. A park with no street (`blocks` makes a roadless piece over
  1500 m2 a park) still without a way in (an interchange's infield, a strip between the sea
  and a megasite) becomes a green verge (kind `green`, `attrs.verge` the reason), as the
  smaller roadless pieces are; any other open space left says why and fails `park_access`.
- **Walled-in entrances** (`buildout.link_entrances`, after M3's moves and ways round): an
  entrance its own complex walls in (towers on one podium) reaches the nearest walkway
  through the complex (`_through_complex`: a door path with `attrs.through` the property,
  which the check lets enter that property's buildings), else a gateway `GATE_W_M` 3 m wide
  is cut through the low buildings (`GATE_MAX_H_M` 30 m, no landmark, traced, held or formed
  building, no portal; `_gate_ok`) on its straight link to one of the nearest walkways
  (`_gateway`, `_cut_gate`): each mass standing on the ground there keeps its legs beside
  the gateway and a mass over it from `GATE_CLEAR_M` 4.5 m up to its top (the first leg keeps
  the mass's index, the rest go last; the footprint stays the outline;
  `Building.attrs.passage_cut` the link). Stats `entrances_through_complex`,
  `entrances_gateways`.
- **Station stairs** (`transit.Builder._elevated`, `_metro`): an elevated platform end whose
  sidewalk is reached only round the buildings gets an elevator and a path led round, not a
  stair straight through them; a metro stair stepped along its concourse that would pass
  under a building's ground floor becomes an elevator straight down from the sidewalk.
- **Checks:** `walkway_building_clash` fails a walled-in entrance and station stairs through
  a building (both were notes) and notes the gateways; `park_access` fails an open space
  with no way in and notes the long paths and the verges (islet parks stay a note).
- **Deck columns** (#91, `decks.supports`): the fill-in's last resort, the nearest point of
  the thin allowed strip, was tested with `thin.contains`, which leaves out the strip's own
  boundary where that point lies, so a column there was kept or dropped by the grid's
  rounding; it is tested against the allowed zone (0.1 m round it). Vesper Bay Decks builds
  on its first full-city try (3 before).
No exporter change. Sample builds and the numbers before and after:
`docs/progress/fix_access/`.

M22 (the pavement map, from run-through 2's road recheck; design in `docs/assetgen_scope.md`
14.18) is in place, in `citygen/pavement.py` (exact integer triangulation `pavetri.py`,
checks `pavement_checks.py`, preview `preview_pavement.py`):
- **Model:** `pavement` (faces, id `<owner>.pv.<band>`, `owner_id` a road segment or a
  junction, `kind` carriageway, median, curb, sidewalk, walk, bend, junction, corner, bulb,
  `band`, `layer` g0 to g3 by M7's level, d1 a deck, u1 tunnels, `rings` as edge ids, interior
  `samples` where the boundary is not one plane) and `pavement_net` (vertices on the 1 mm grid,
  id their cell, one height each over the finished ground; edges stored once: port, band,
  curb, outer, seam).
- **Cuts** (`junctions.py`, in M2): one cut per road end, where every band, sidewalk,
  crosswalk and lane ends (`cutbacks(..., one=True)`): past every overlap of the legs' rights
  of way that reaches the node however far, to the end of its run from the node along each
  leg (`overlap_cuts(..., cap=False)`, `_run_end`: a loop ramp's foot passing under the deck
  it climbs to is a crossing, not the junction's), past a fold or a corner's inner mitre near
  it (`fold_cuts`, until stable), clear of a lock (`lock_cuts`). Each junction keeps its legs'
  cuts (`attrs.cuts`: [road, `a` its start or `b` its end, cut]; `pavement.road_cuts`), so a
  regeneration's seam junction leaves the held roads as they were. A road whose two cuts leave
  under `pavement.MIN_ROAD_M` joins its junctions into one, a cluster (`plan_units`: junction
  `attrs.nodes`, `inner`; nodes within `CLUSTER_DZ_M` in height). M13's grade lines keep
  M17's runs (`runs17`). M2 lays no local junction within `streets.APPROACH_PAD_M` 60 m of a
  primary road's stretch over M7's 3 m, where no one surface could carry it.
- **Faces:** ribbons by the cross-section between the cuts, one mitred frame per station;
  bend faces where a band would fold (`Road.folds`, `fold_poly`: never a mitre's spike); a
  junction's carriageway (core, legs' stubs, inner roads, a bulb) less the ribbons where they
  are at its level (`level_stretch`), corner pads the right of way less the carriageway;
  overlaps cut by priority (`KIND_RANK`, ties by the owners' places, never their ids) up to
  `RESOLVE_M` past `SAME_Z_M` (the map's heights there are estimates), slivers under `GAP_M2`
  filled, every vertex within `TOL_MM` of an edge put into it, so every interior edge is
  shared exactly. The map made again from a finished model's rows (`build.pavement_of`) is
  the one M2 made (a row's missing cross-section field reads as the model's default).
- **Heights:** a road's at each vertex's station (a ribbon vertex a junction face shares at
  its port's height); a port line where two roads go on as each other one height; a junction's
  curbs between its ports by length along its outline (a cluster's long curbs along its inner
  roads), corner pads likewise; interior samples on a 2 m grid by mean value coordinates
  (`mvc`).
- **Buildable junctions** (`junctions.buildable`, after M18's levelling): each junction's
  ports within its grade of each other (M13's class grades, at least M18's ramp maximum) and
  its faces drawn within it: node, port and plain node heights fitted on one graph (M13's
  min-plus fit; bounds from fixed roads, locked stretches, exits, roads overhead and M7's local
  junction limit; ports beside a cluster's inner road tied to it), roads run again
  (`_conform`). A junction no height fits is kept as M18 left it with `attrs.unbuildable` the
  two bounds that clash (`why_text`); one the map draws steeper than the fit foresaw (a gore
  inside a cluster) is kept with its drawn grade (`build.add_local`, `pavement_checks.
  drawn_steep`). Both are noted by the checks and listed in the report (`held_junctions`).
- **Checks** (four, 106 on a flat sample, 111 with decks; run again on the finished city,
  so their notes name its stable ids): `pavement_edges`, `pavement_tiling` (faces on one layer
  within `SAME_Z_M` 4.5 m of each other never overlap, every face on its owner's right of
  way), `pavement_heights` (a bend face across a fold noted), `pavement_junctions`;
  `road_overlaps`, `junction_surface`, the crosswalk, signal and dead end checks, column
  placement, props (railings and median barriers 3 cm clear of a junction's outline,
  `props.ROAD_IN_M`) and decks read clusters.
- **Stage 2 today:** a junction's `polygon` is its carriageway face's outline, `edge_z` the
  map's heights there, so AG7 draws today's pieces on the map until AG17.
- **Blockout:** roads, junctions, pads, medians and sidewalks drawn from the faces into the
  objects they were in (keys unchanged; a band's side from its name before a split suffix,
  `blockout._side`), curbs as walls; `preview_pavement.png`.
- **With M10, M13, M14:** ids from owners, the splice makes the map again on the spliced city
  (`build.pavement_of`); in a regeneration a junction whose roads are all held takes back its
  old cuts, cluster and tag (`junctions.held_units`, `streets.Frame.old_junctions`: its roads
  come back with the old city's levelled heights, which the cut, cluster and fit rules would
  read otherwise), and a held node that was no junction stays none; heights over M13's
  ground; a deck's streets on layer d1.
Sample builds: `docs/progress/M22/`.

The pavement map fixes (issue #147, after AG17) are in place, in `citygen/pavement.py` and
`citygen/junctions.py`:
- **Footbridges in the map:** `Plan` lays a footbridge as any road (its walk face between
  its cuts, on stations that take its profile's knots, `Path.knots`, so its faces turn where
  its stairs do) with ports on its junctions: its cut no farther out than its stairs' foot
  (`junctions.stair_foot`, `foot_cuts`; M2 starts most stairs at the node), so its port is at
  the junction's level and the stairs rise past it, in a slot of the junction's region
  (`unit_regions` keeps footbridge legs; its faces over every other, `FOOT_RANK`). Its faces
  meet another owner's only on its port lines (`Assembly._apart`, `_on_foot_port` in
  `_levels`: a vertex put into a port line between its port points is on it; the stairs'
  sides and the slot's are outer edges, walls, at two heights), and a junction vertex beside
  the stairs keeps the slot's height. The blockout draws footbridges from their faces again
  (`<segment>.deck`; on M22 they had no faces and were left out).
- **Folds** (`Assembly._unfold`): where the curb rule (heights by length along a ring from
  port to port) folds a junction (a gore's narrow neck between a road and its ramp in a
  cluster no height fits: a free vertex and another vertex of one face, or a point every
  `EDGE_STEP_M` along one of its edges, 0.25 to 4 m apart across it, more than `FOLD_TOL`
  steeper than the junction's ports allow), the free vertices there take the inverse
  distance weighted height of the vertices and edge points left as they are, within the
  ports' envelopes and the two heights the curb rule ran it between (`Assembly.bracket`: a
  curb stays between its legs' heights, as `junction_levels` holds it), grown while folds
  remain (`UNFOLD_ROUNDS`); kept when the faces it
  changes are drawn less steep at the steepest of them (`_drawn_faces`). Delta Megacity's
  `jn.e170s444` is drawn at 0.225 (0.896 on M22; five vertices move by the gore).
Every sample has new goldens (footbridges' faces). Outputs: `docs/progress/fix_pavement_map/`.

The Corporate Core regeneration fix (issue #126) is in place, in `citygen/streets.py`, for a
district regeneration only (a fresh build is unchanged):
- **Held runs** (`held_runs`, before the noding): a held street of the regenerated district (a
  boundary street, a pinned one) whose end lies inside a held segment of the old city that
  goes on past it is laid on along that segment to its end, as the old city's M17 run-on had
  it. Nexus City's Corporate Core boundary street ran on to the end of an avenue; the
  district's new streets no longer reached its group, so it was taken for an island and made
  pedestrian before the run-on, and the avenue was left a dead end with no bulb.
- **Hooks come loose** (`Builder.attach`, `_hooked_at`, `_unhook`, `HOOK_M` 3 m): new
  streets of the district hooked onto another new street's free end (the fill left two of
  them ending side by side) no longer keep it from bending onto a road it may meet only at an
  old node (`_attach_to`'s `keep`); where it bends, they let go and are joined later as any
  dead end. The two had made a corner beside a held boundary street, its right of way 103 m2
  into the street's, which `_overlaps` could not drop (the held road, nor a street leaving
  the map); the street now bends onto the old node, as the old city's did.
Outputs: `docs/progress/fix_core_regen/`.

The sky tube profile fix (issue #124) is in place, in `citygen/transit.py` (`_curved`,
`_window`, `_box`), `presets.py` and `transit_checks.py`: sky tubes climb and descend in long
ramps and vertical curves, not in steps and humps.
- **Per mode** (`ModePreset.design_grade`, `curve_m`, `fill_m`): sky tubes 3.5%, 300 m and
  500 m, `max_grade` (8%) kept as the limit. The other modes have none, so their profiles are
  as before.
- **Profile** (`_profile_pass`, then `_curved`): every need and cap is held level for half a
  curve and a vertex either side, then lifted and lowered at the design grade. Only where the
  two meet does it climb steeper, up to the limit grade (0.95 of `max_grade`). A closing by a
  level stretch of `fill_m` fills a sag between crests closer than that at the lower crest's
  height, and leaves a wider one a floor at least that long. A moving average over `curve_m`
  (M7's way) makes every grade change a parabolic vertical curve. Held level that long, the
  average stays over every need and under every cap; it is last clamped between the needs
  and caps lifted and lowered at the limit grade, as before.
- **Check** `transit_profile_smooth` (one more on every city with transit lines: 107 on a
  flat sample, 112 with decks): measured every 10 m, a sky tube's grade changes no faster
  than a 300 m curve allows (two limit grades over it), and no sag is narrower than 200 m
  (the fill length less a curve).
Outputs: `docs/progress/fix_sky_tube_profile/`.

The support and elevator fixes (issues #108 and #109) are in place, in `citygen/transit.py`:
- **Bents beside the line** (#108, `_bent_room`, from `_support_room`): where the dry run
  still leaves a gap once the low buildings under the track are out (a line over dense
  streets, every spot under it a lane, a sidewalk's clear path or a building that is not
  low), at each spot a span apart along it the nearest spot beside the line for a cantilever
  bent's column (within `CANT_REACH_M`, as `_frame` searches) that only low removable
  buildings keep it off (their tops 2 m under its arm), the rest of the spot and the arm
  clear, has those buildings taken out. A city whose dry run leaves no gap is unchanged.
  #108's layout (Vesper Bay Decks' second) no longer reproduces the gap on main.
- **One elevator an end** (#109, `Builder._elevated`): the platform's own elevator at its
  first end is added only where that end has none yet (the sidewalk right under it had one
  added already).
Outputs: `docs/progress/fix_pylons_elevators/`.

The water coverage fixes (issue #140 and #144's Nexus `water_gaps`) are in place, in
`citygen/build.py` and `assetgen/water/`:
- **Every part of the map's water a body's** (`build.water_pieces`, in `assemble`): the model
  kept only the largest part of each body's polygon on the map's water and none of the land
  the hydrology's opening took between the bodies or beside one, so that water was no
  body's. The blockout's sea sheet (its whole tile, under the ground) showed there, but AG12
  takes every sea sheet and drew nothing: Nexus City's Kurosawa River leaves the map at its
  east edge and comes back, and its first stretch in the north-east was a hole to the sky
  between the land and an islet. Now every part of the water outside the sea and every
  body's main piece (down to slivers along a shore; crumbs under `WATER_CRUMB_M2`, 0.01 m2,
  are the grid's) joins the water whose piece it touches (the one holding most of it, ties
  by id; again while parts join); a part touching none goes to the water holding most of
  it, else the nearest, ties by id (the road stage's rule, `roads.Net`), as a further piece
  of the body, a row of its own (`attrs.part` 2, 3, ...; its stretch of the centerline,
  `build.piece_line`; cut off by the map's edge, `mouth` edge and no `flows_into`), named
  `rv.<name>.part<k>` or `ch.<name>.part<k>` (`ids.base`; an unnamed channel by its own
  anchor). The road stage still takes parts under 50 m2 as land, and M17's `water_end` reads
  the hydrology's bodies.
- **Coverage** (`water_coverage`, `checks.uncovered`): the water a blockout sea sheet showed
  (the map less its ground) must be a body's or under a bank's band wherever AG12 takes the
  sheet; a part of 1 m2 or more left over fails, named by its tile.
- **Bed seams** (#144, `grid._Sides`): where the region's edge touches a lattice line at a
  vertex without crossing it (a bank's dry strip ending on it), the whole cell beside it
  takes that vertex too; it met the clipped cell across a T-junction, a crack of 0.15 m in
  Nexus City's bed by `sep.e126n468.bank.w5n461`.
- **Plate rings** (`massing.Plate.ring`, `_unstep`): two arcs meeting tangent each give their
  shared end, which may round to grid points a step apart, the second behind the first; a
  ring that would cross itself drops such steps (a valid ring stays as it was). The small
  city's `water_required` layout, moved by the water, had a circle plate turned 45 degrees
  cross itself and a sloped crown's overlay fail.
- **Junction faces in `ground_cover`** (`water_checks._junction_faces`, `_bare`): M16's
  right of way takes a junction's carriageway only, so a cul-de-sac's ring of sidewalk round
  its bulb (a corner pad of M22's map) lies outside it. The generator covers it (meadow) where
  it measures 3 m wide as a piece, and left it out on that layout, where a hairline joins it
  to a curb strip; the check counted it as open land left bare. A part of open land that
  fails is now cut by the junctions' faces on the ground first (only then: cut first, a
  narrow part could split into a wide one). No city's model moves.
Outputs: `docs/progress/fix_nexus_water/`.

### Rules for sessions building citygen milestones (local; no cloud credits)

- **Validation:** as in "Validation" above; nothing beyond it.
- **Work-in-progress images:** after each major sub-step (and at least every hour or so), build
  the sample cities, commit their preview images to `docs/progress/<milestone>/wip/<NN>_<step>/`
  and push to the session branch, so Swagnik can watch progress on GitHub before the PR exists.
  Keep only images and short notes there; overwrite nothing from earlier milestones.
- **Root `README.md`** is organized by stage (see "Layout by stage"). When a milestone PR is
  ready: set its row in the stage's Milestones table (a few words, status), put its full entry
  in the stage's milestone log (`docs/citygen_milestones.md`), and point the stage's images at
  the newest builds. Keep the README short: one-line captions, no before and after pairs, a
  new image only for something new the milestone adds, details in the log. Every 3D render
  shown in the root README is 8K: `citygen rerender <blockout_dir> iso_city ... --to
  docs/progress/<M>/<city>` (7680 px wide by default, a few seconds each; fall back to 3840 or
  2048 only if 8K fails). Always include the whole-city isometric views
  (`render_iso_city.jpg`) in the stage's Cities gallery. Write the README for someone who
  wants to use the generators: what they make and how to run them, not how they are verified
  (no goldens, hashes, "byte for byte", identical builds across machines, check counts or
  sweep tallies; those belong in the milestone log).

## Asset generator (assetgen)

`docs/assetgen_scope.md` is the spec for stage 2 (milestones AG0 to AG17, section 14; AG16,
performance, section 14.17, and AG17, road surfaces by construction from stage 1's M22
pavement map, section 14.18, are done), its log
`docs/assetgen_milestones.md`. Package `assetgen/` beside `citygen/`, which it imports read
only (`model`, `dmath`, `geom`; AG17's street stage also `pavement` for the cuts and stations); tests in `tests/assetgen/` (`test_ag_*.py`, helpers in
`agtools.py`, never a second `conftest.py`, which would shadow `tests/conftest.py`).

AG0 (contract and spike) is in place:
- **Asset spec** (`assetgen/spec.py`, era presets in `presets.py`): `.venv/bin/python -m
  assetgen spec validate SPEC [--build BUILD] [--filled OUT]` and `... spec schema`; skill
  `.claude/skills/assetgen/SKILL.md`; sample `cities/vesper_bay/asset_spec.json`. Section 13's
  decisions are provisional (2026-10-27) and set as the spec's defaults.
- **Briefs** (`brief.py`): `assetgen brief BUILD [--spec S] [--overrides O]` writes
  `BUILD/assets/briefs.json` (canonical JSON, a sha256 per building), `brief_report.json` and
  `preview_edges.png` (`preview_edges.py`). Each brief is in the building's frame (origin
  the middle of its footprint's box, mm): its record, masses with floors, every mass edge
  split into facade regions (s along the edge by z) classed front, street, alley, canal,
  plaza, park, courtyard, atrium, party (other building within 0.5 m), blind (3 m), open,
  upper (above the neighbors that cover below) or hidden (another own mass), neighbors,
  skybridges, sign slots, mounted props (`on_wall` when the mount point is within 0.5 m of a
  wall that spans its height), plants, green roofs, POIs, lot, property, district and the
  spec's sections. What an edge faces comes from probes 0.75 to 60 m out (road corridor,
  water, open space, another mass at eye height). Schema `assetgen brief schema`
  (`briefmodel.py`); `assetgen brief diff A B` (`briefdiff.py`, also `seam`: the check that a
  district regeneration changes only its district's and seam's briefs).
- **Geometry**: `triangulate.py` (exact integer ear clipping with holes), `mesh.py` (integer
  mm faces, flat normals, UV0 in meters, UV1 per face, COLOR_0 a multiplier as glTF
  defines), `gltf.py` (deterministic GLB: glTF frame (x, z, -y), fixed attribute order,
  optional KHR_mesh_quantization and EXT_mesh_gpu_instancing).
- **Spike** (`spike.py`, `assetgen spike OUT`): tower (975k triangles), shopfront row,
  shanty stack and a foliage test tree, with `unreal_contribution.json` (assetgen's
  manifest entries); Blender preview `assetgen/blender/spike_preview.py`; Unreal
  `assetgen/ue/spike_import.py`, `spike_shots.py`, driver `unreal_spike.py`. Results:
  `docs/progress/AG0/` and scope section 11.
- **Determinism**: `tests/assetgen/data/golden_hashes.json` (small test city, Vesper Bay
  buildings, the five samples' briefs, small spike buildings, a triangulation), Mac = x86
  (`citygen-x86`). Write them again with `.venv/bin/python tests/assetgen/goldens.py
  [--builds DIR]` after a citygen change moves a model, and say why in the PR.

AG1 (building shells) is in place:
- **Genome** (`assetgen/buildings/genome.py`): blake2b draws from the brief alone: the era's
  palette with the spec's district and owner additions, a property family's shared genes
  (complexes), per mass group (`base`, `body`, `top`) a facade system and its window type,
  rhythm, bay, window share, sill, head, reveal, corner pier, cornice, parapet and bands,
  per building colors, wear and finishes. `effective` keeps the genes a shell used (the
  uniqueness vector). Every era maps onto AG1's six systems (`systems.FALLBACK`); building
  types fix some (`TYPE_SYSTEM`).
- **Grammar and shell** (`buildings/shell.py`): per mass the floor rows (sill and head per
  floor, shared by all its facades so corners match; ground, louver, lantern and parking
  rows), per facade bays between corner piers (only at real corners), openings by window
  type and the brief's region class (none on party or hidden walls), storefronts per unit,
  a panel wherever a mount would fall on glass; the wall a grid welded on its plane (pier
  cells, zipper strips between rows), a reveal pocket and pane per opening, caps on the
  ring's corners (`triangulate(..., keep_straight=True)`), ring strips (`buildings/rings.py`:
  parapets, cornices, slab bands, beveled past 1.5 offsets), roof equipment blocks until
  AG4. Every part is closed on integer millimeters (`meshbuf.check`); spiked rings and
  courts pinched onto the exterior are cleaned first. UV1 and vertex colors only on glass.
  On M13's slopes the pivot is the building's `base_m` and every mass on the base gets a
  plinth down into the lowest ground under the footprint (`shell.plinth_mm`, also in the
  proxy, collision and envelope; AG5 steps it).
- **Proxies, collision** (`buildings/proxy.py`, `collision.py`): masses as prisms (at most
  500 triangles), convex pieces per mass (boxes where rectangles).
- **`assetgen build BUILD [--spec S] [--workers N] [--no-streets]`** (`assetgen/build.py`,
  at most 4 workers by default): briefs (kept when model, spec and overrides are unchanged),
  genomes, asset hash per building (brief, `GEN_VERSION`, material library), 256 m tile
  packs `tiles/<tile>.glb` and `proxies/<tile>.glb` made in workers only where a tile's
  hashes changed, `manifest.json` (`assetgen/manifest.py`: other stages' sections kept),
  `asset_report.json`/`.txt`, `unreal_contribution.buildings.json`
  (`assetgen/contribution.py`); every file written only when its bytes change, so an
  unchanged rebuild writes none. Bump `GEN_VERSION` whenever pack bytes change. Checks
  (`assetgen/asset_checks.py`): `asset_coverage`, `asset_envelope`
  (`buildings/envelope.py`), `asset_meshes`, `asset_unique` ($k$ genes or distance), and
  `asset_budget` (section 11's estimate); then AG7's street stage, the same bytes as
  `assetgen streets` (its report written only when another of its files changed, so an
  unchanged rebuild still writes no file); exit 1 on a failure of either.
- **`assetgen preview BUILD [--blockout DIR]`** (`assetgen/previews.py`,
  `assetgen/blender/preview_assets.py`): on the blockout's city.blend without its building
  boxes, the whole city from proxies (`city_full` with every shell), each district and the
  blockout's street cameras at full detail, contact sheets per type; materials per slot
  tinted from the glTF node extras.
- **Exporter** (after M15): `citygen unreal` reads every `BUILD/assets/
  unreal_contribution.*.json` as layer 2 over the blockout (`unreal.stage2`, the manifest's
  `stage2`; a key in one file only): an actor per entry at its pivot in place of the
  blockout actors of its key and `replaces`, packs imported in their nodes' frames, stage 2
  masters and an instance per part and slot reading the CPD tints, building collision as
  convex hulls (GeometryScript), HISM parts, proxies imported only; `--blockout-only`, or no
  assets, gives exactly the blockout's manifest. Results: `docs/progress/AG1/` and
  `docs/progress/AG1/unreal/`.

AG7 (street elements) is in place, in `assetgen/streets/` (tests
`tests/assetgen/test_ag_streets.py`):
- **`assetgen streets BUILD [--spec S] [--workers N]`** (`build.py`): every street element as
  a piece keyed by its citygen id, gathered from the model (`ctx.py`: indexes, M13's ground,
  the blockout objects each piece replaces, from citygen's own blockout code) into `inputs`
  that hold everything its generator reads, hashed (`pieces.py`). Pieces: road segments
  (`roads.py`: carriageway between the junctions' cut edges, markings from the model's
  lanes, stop lines, arrows, patches, manholes, drains, medians, decks with parapets, joints
  and underside lights, embankments), sidewalks, crosswalks and junctions with their
  sidewalk corners (`walks.py`), bridges by kind, road columns, tunnels, portals, approach
  trenches, underpass stairs, vents (`structures.py`), guideways, sky tubes (glass as a
  non-Nanite LOD chain), transit columns and station structures, M13's retaining walls
  (`transit.py`), quays (stairs down to the water every 60 m, each flight a closed solid from
  the wall's foot, #131) and canal walls (`water.py`), megasite elements with containers as
  instanced parts (`sites.py`). Meshes on integer millimeters in each piece's frame
  (`kit.py`: grids, sweeps, exact polygons; folds dropped); lean glTF.
- **Outputs**: `BUILD/assets/streets/<tile>.glb` (a node per piece, the blockout's tile of
  the object it replaces), `streets/parts.glb`, `streets/manifest.json`,
  `unreal_contribution.streets.json` (`docs/unreal_export.md`, AG7 section) and
  `streets_report.json/.txt` (`checks.py`: coverage, meshes, replaces, budgets). A tile is
  made again only when its pieces' hashes or the code's hash change; an unchanged city writes
  no pack. Up to 4 workers, the same bytes for any count.
- **Ground**: a road's surface is its M13 grade line plus its z profile; sidewalks and
  crosswalks follow their road (on a deck too, writing the corrected walkway lines), road
  tunnels their road's grade line, everything else the terrain at its point; 0 on a flat
  city (Cragmouth is the hilly sample).
- **`assetgen streets seam BASE REGEN [--district NAME]`** (`seam.py`): which pieces and
  tiles a district regeneration changed and why (own entity, or an input entity changed).
- **Previews**: `preview.py` (top-down, from the packs) and
  `assetgen/blender/streets_preview.py` (the blockout's `city.blend` with the replaced
  objects removed and the packs imported; its views or custom cameras).
- Goldens in their own file, `tests/assetgen/data/golden_streets.json`
  (`tests/assetgen/streets_goldens.py [--builds DIR]`), Mac = x86. Bump nothing for a
  generator change: the code hash is in every tile's hash.
- **Barriers** (issue #95, `barriers.py`): a road's median barrier, guard walls, parapets,
  a deck ramp's barriers and parapets and a footbridge's railings are runs (`runs_of`,
  `rail_runs`) over spans its gather works out (`road_runs`, the inputs' `barriers`,
  `rails`): cut to cut, less where a run comes within `CLEAR_M` (0.15 m) of a junction at
  its ends that does not carry it on, of another leg's carriageway there, of another
  junction (its outline and corner pad sectors, `junction_area`) at its height, or within
  `XWALK_CLEAR_M` (1 m) of a crosswalk. A raised road's parapet ends on its cut edge, or on
  a sidewalk where its junction's corner pad begins (`corner_points`); ends are `join`,
  `stop` (a jersey slopes down to `TOE_F` of its height over `END_M` 3 m, a parapet is
  capped: `draw_run`, `cap`), `open` (no junction: the next road goes on). A junction
  (`junction_plan`) carries a parapet round each corner of a raised junction (along its
  drawn pads' property line, else its outline), a guard wall along an at-grade corner
  between two guard-walled highways, and a median across where two median legs face each
  other with no connector lane across (`median_end`); each clipped clear of its legs'
  drawn carriageways (`leg_ends`), its lanes, the crosswalks, other roads, junctions and
  building masses near it at its height (`near_of_junction`, `Keepout`, `clip_line`).

AG2 (facades) is in place (tests `tests/assetgen/test_ag_facades.py`):
- **Parts** (`buildings/parts.py`): windows by frame style (with sills and lintels),
  mullion caps, spandrel panels, balconies (solid, rail, glass, enclosed), louver panels,
  fins, sunshades, shutters, grilles, boards, infills, screen blades, egg crates, add-on
  boxes, structural members (columns, beams, diagonals), capsule pods, AC units, dishes,
  arcade columns, balconettes, podium canopies, masts and spires; each in its own frame
  (x along the facade, y into the wall, z up, mm) from parameters in whole centimeters and
  5 degree steps, named `part.<family>.<style>.h<hash>` (a name may not end in digits:
  Blender reads them as a copy number). A part placed 8 times or more in a building is an
  instance, else merged into the shell (`merge_into`) unless a thin triangle would fold
  when turned and rounded (`survives`); every family has a reach for the envelope check
  (`REACH`: flush, strip, deep, roof). Per tile `parts/<tile>.glb` holds the tile's
  instanced part meshes; the records and the contribution hold the transforms.
- **Systems** (`systems.py`): all 19 of the presets' systems are built (`FALLBACK` empty;
  `FLOORS` keeps some to a size of building; `TYPE_SYSTEM` may be weights), each with its
  frame styles, sills, balconies and feature (`FEATURE_GENES`); new wall and part slots,
  tints only from the six CPD channels the exporter reads.
- **Articulation** (`buildings/articulate.py`, by era: `systems.ARTICULATION`): corner
  chamfers and rounds, setback ledges, stepped and halo crowns, arcades under a
  cantilevered first floor; the shell adds masts and spires, podium canopies, eaves and
  ribs. Split masses keep the brief's mass index; cut and offset edges are `deriv`;
  `Facade.soff` maps a facade's s onto its brief edge; `Facade.room` is how far a balcony
  or canopy may reach (street or avenue sidewalk 1.2 to 1.5 m, open ground 1.5 to 2 m,
  never over an alley, a service road or a highway).
- **Grammar** (`shell.py`): punched windows take their width from the genome's bay (one
  size across the facades, 5 cm steps); door rows where balconies go (spandrel panels in
  the other bays); pockets at convex corners start a reveal plus 6 cm from the corner;
  irregularity by `irreg` (grime times low wealth): boards, infills, replaced frames, AC
  units, grilles, dishes, closed-in balconies, add-on boxes; a shed of one tall floor with
  a blank ground gets a clerestory; industrial walls on the ground a block or concrete dado
  (`dado`, `dado_m`) and industrial roofs a palette of their own (`ROOFS_INDUSTRIAL`), so
  plain sheds differ in their thumbnails.
- **Checks**: `asset_unique` also compares contact-sheet thumbnails (`buildings/thumb.py`:
  a 64 px z-buffered rasterizer, a 1,504-bit hash of 16 x 16 blocks: a difference
  hash and each block's tone in four steps, at least 8 bits apart; a
  building filling under 10% of its thumbnail, a long thin shed, is told by genes alone), `asset_budget` per
  building class (`asset_checks.CLASSES`) and per city (section 11's estimate plus 40% for
  parts, 3 instances per bay), `asset_meshes` every part mesh, `asset_envelope` every
  instanced part's box.
- **Previews**: parts drawn by one geometry-node instancer per pack that picks each
  point's mesh from the pack's collection (tints as point attributes, materials
  `ag_<slot>.inst`; a node group per part mesh, or the glTF importer's per-mesh deletions,
  are quadratic in Blender: the importer's temporary objects go in one batch); whole cities
  at 16 samples; `--views towers` (the tallest building of each era up close);
  `--no-parts`. Results: `docs/progress/AG2/`.

AG8 (props, plants and signs) is in place, in `assetgen/props/` (tests
`tests/assetgen/test_ag_props.py`):
- **`assetgen props BUILD [--spec S] [--workers N] [--sheets DIR]`** (`build.py`; also the
  last stage of `assetgen build`, `--no-props` skips it): every M6 prop kind a family of 4
  to 12 variants per district style (`styles.py`: sleek, civic, heavy, neon, old from the
  era; `variants.py`), every plant species 6 or 8 (`trees.py`: space colonization, palms,
  pines, shrubs, sedum, scrub, ivy), each placement's variant a hash of its id
  (`gather.py`); awnings and ivy in segments, facade props off their wall (the briefs'
  `gap_m`) on brackets; cables, scaffolding and market gates exact meshes per tile; M6's
  highway median barriers dropped where AG7's road piece has its barrier. On M13 a
  placement stands on its building's `base_m` (facade, roof) else the ground at its point.
- **Signs** (`signs.py`): an asset per M11 sign slot (lightbox, LED panel, neon and
  channel shop signs, blade signs, billboards, holo-ads as non-Nanite LOD chains, neon
  bands). One sign path with AG6: its `signs.json` gives each slot's text, script, colors
  and page cell; a flat face is a quad on its page cell (slots `page.<page>`,
  `holopage.<page>`), neon tubes and channel letters follow AG6's glyph strokes
  (`assetgen.materials.glyphs`). Without the library, lit flat strokes. Node names never end
  in a dot and digits (Blender's glTF import overflows).
- **Textures**: every slot mapped to an AG6 master and library set (`catalog.prop_set`;
  bark, leaf clump, plastic, car paint, galvanized and rusty metal sets), UV0 in meters on
  every variant; leaf clumps are two crossed alpha-cut cards on the `leaves` master (still
  Nanite `Voxelize`); AG6's texel density check reads the props packs. `assetgen build`
  runs AG6's signage before the props and its materials stage after them.
- **Outputs**: `assets/props/variants/<kind>.glb`, `plants/<species>.glb`,
  `tiles/<tile>.glb`, `signs/<tile>.glb`, `props/manifest.json`,
  `unreal_contribution.props.json` and `.signs.json` (entries keyed by M15's prototype
  actors, parts with `[x, y, z, yaw, sx, sy, sz]` and ids), `props_report.json/.txt`
  (checks `props_coverage`, `props_families`, `props_replaces`, `props_meshes`,
  `props_budgets`). A tile is made again only when its inputs or the code change.
- **Previews**: `assetgen/blender/props_preview.py` (the blockout with AG1's shells, AG7's
  streets and AG8's instances through geometry nodes; `--night` adds lamp and sign lights)
  and `props_sheet.py` (variant sheets, `--materials` textured); `assetgen materials
  preview` draws them textured. Golden: `tests/assetgen/data/golden_props.json`
  (`tests/assetgen/props_goldens.py`).

AG6 (materials and textures) is in place, in `assetgen/materials/` (tests
`tests/assetgen/test_ag_materials.py`):
- **Library** (`library.py`, `surfaces.py`, `noise.py`, `pbr.py`, `atlases.py`,
  `interiors.py`; `assetgen library [OUT] [--density 512]`): tileable sets per era (walls
  and roofs in each era's look) and shared ones (building parts, street surfaces, AG8's
  props and plants), each base
  color with height, OpenGL normal, occlusion-roughness-metallic with the tint mask, at 512
  px/m within reach of the street (256 above); trim sheets per era, decal, road, interior
  (day and night, one-point room images per use) and macro atlases. Integer-hash noise and
  elementwise float32 arithmetic, numpy and PIL only; made once into
  `~/.cache/cybergen/assetgen_library/d<density>` (or `$ASSETGEN_LIBRARY`), kept while its
  code hash is unchanged, linked from `BUILD/assets/library`; not in git.
- **City** (`signage.py`, `glyphs.py`): sign pages from M11's names and unit uses in each
  district's scripts (an in-repo stroke font for Latin and Cyrillic, stroke-built kana and
  Hangul, Hanzi-like and Devanagari-like signs), brand logos, ads and holo-ads,
  `BUILD/assets/textures/` and `signs.json` (every sign slot's page and cell).
- **Materials** (`catalog.py`, `params.py`, `contrib.py`): slot to master and set; wall and
  roof slots per era (`<slot>@<era>`, a building entry's `materials`); 7 more Custom
  Primitive Data floats (room grid, interior row, streaks, top, blinds, era); the
  contributions' `textures` and material parameters, `unreal_contribution.materials.json`.
  Window interiors are mapped from UV0 and the building's room grid, nothing per pane.
- **Checks** (`checks.py`): texel density from the packs' UVs (99.5 % of each part's area
  at three quarters of the spec's density or more), texture budgets; `materials_report.*`.
- **Previews**: `assetgen materials preview BUILD [--night]` and `assetgen materials board
  OUT` (`assetgen/blender/ag6_materials.py`, node for node the Unreal masters;
  `ag6_preview.py`, `ag6_board.py`). `assetgen build --no-textures` gives AG1's flat
  materials. Exporter: `docs/unreal_export.md`, AG6 section. Results: `docs/progress/AG6/`.

AG3 (street fronts) is in place, in `assetgen/buildings/fronts.py` and `frontparts.py` (tests
`tests/assetgen/test_ag_fronts.py`):
- **Band**: every prism mass on the ground (or an M14 deck's top) has a ground band (its
  foot to its first floor line, at most 7.5 m) built apart as the building's second mesh,
  `<id>.front` (layer 1 of
  `meshbuf.Buf`, `meshbuf.split`); zones as polygons with notches and holes, pockets, caps
  that close both meshes; collision hulls start at its top (`band_m`), the front collides as
  drawn in Unreal.
- **Openings**: a shopfront per unit by use (`part.shopfront.<use>`), a door at every other
  entrance (`part.door.<main|service|dock|rollup|garage|gate>`), the ground row's windows; a
  door shifts, then cuts into corner piers, else hangs flush; units and entrances on a wall
  a neighbor stands against move to an open facade of the mass (`Band.rehome`) or the
  building (`leftovers`), `moved`. Door records (id `<building>.door.e<k>|u<k>`, kind,
  walkway, position, normal, size) go to the contribution and the exporter's `doors` graph.
- **Mounts, walls, decals**: panels under awnings too, plates, trellises and scaffold ties
  (`hardware`), downpipes and murals on blind and fire walls (`walls`), decals of AG6's atlas
  on the band (`_decals`; one mesh per tile, `decals.<tile>`, mesh decals in Unreal).
  AG8 keeps every object it draws; AG3 gives the wall its fascia, panel, pier or plate.
- **Checks**: `asset_access` (a door per entrance and unit, open to a walkway; facing a
  neighbor, with no walkway ahead, or ahead only inside another building (M17: a park path
  citygen runs through it) reported, not failed) and `asset_mounts` (never on glass); budget
  allowances per unit and per front.
- **Previews**: AG6's `assetgen materials preview` now draws fronts, decals and AG2's parts
  beside AG8's props. Exporter: `docs/unreal_export.md`, "From AG3". Shell vertex-color
  grime and trim-sheet UVs are not done (open). Results: `docs/progress/AG3/`.

AG4 (roofs and connections) is in place (tests `tests/assetgen/test_ag_roofs.py`):
- **Roofs** (`buildings/roofs.py`): roof forms in the top floor, never over the model's mass
  (hip, gable, pagoda, mansard by crown and era; sheds' sawtooth, gable, barrel by gene;
  `plan` before the masses), finishes and copings on flat roofs, green roofs (bed, border,
  path), an asset for every roof item (`items`; equipment lowered under a corridor over it),
  access huts, vents, skylights, the billboard frame crown.
- **Parts** (`buildings/roofparts.py`): roof equipment (`ROOF`) always instanced
  (`parts.INSTANCE_ALWAYS`) on untinted slots; penthouses, billboard frames, fire escapes,
  ducts, vents, conduits, cameras, landing doors. Facade details in `buildings/details.py`
  (each placed only where `envelope.fits`; the line with AG3 and AG8 in its docstring).
- **Connections** (`buildings/connections.py`): skybridges by kind (`skybridge`), landing
  doors in the facade grammar, portals cut through towers by the tube's corridor with sky
  station platforms and mouth frames, decks, courts. The brief's `clearances` (skybridge,
  guideway, sky tube corridors) and portal tube lines (`BRIEF_VERSION` 2).
- **Skybridge stage** (`assetgen/skybridges.py`): `connections/<tile>.glb`, the manifest's
  `skybridges`, `unreal_contribution.connections.json` (an entry per skybridge by id,
  `links`). Roof equipment is one entry per tile (`roofs.<tile>`) in the buildings'
  contribution; buildings replace the blockout green roof objects they build
  (`contribution.green_replaces`).
- **Checks**: `asset_clearance`, `asset_roofs`, `asset_landings`, `asset_skybridges`; mounts
  in a landing door counted apart. Exporter: `links` as `cg.link=` tags
  (`docs/unreal_export.md`, "From AG4"). `assetgen materials preview --views city_full`.
  Results: `docs/progress/AG4/`.

AG5 (types, landmarks and slopes) is in place (tests `tests/assetgen/test_ag_types.py`):
- **Types** (`assetgen/buildings/types.py`, parts `typeparts.py`): a generator per M3 type
  where the general grammar falls short (`types.GENERATORS`: shanty stacks, megablocks,
  warehouses, sheds open on columns, yards, hangar doors, labs, villas, terraced rows,
  temple halls, pagodas, gate houses, vaulted terminals and stations, control tower cabs,
  parking ramps, straddle girders), at three points of the shell builder (`pre`, `mass`,
  `post`); every part through `types.put` (`envelope.fits`, off the corridors). Dormers on
  gable, hip and mansard roofs by era; the mechanical penthouse by era
  (`roofs.PENTHOUSE_STYLE`).
- **Heroes** (`buildings/heroes.py`): every landmark (megatower, spire, arcology) and the
  wheel built by kind (light seams, halos, needles, terraces, atrium frames, rims, spokes,
  gondolas, lattice legs), the landmark's palette and accent; a U2 mask per hero (grime,
  leaks, wear, 512 px, `assets/textures/hero/<id>.png`) on UV1 in the hero UV, read by
  per-hero materials (`contribution.heroes`, `HeroMask`); budget class `hero`.
- **Slopes** (`buildings/slopes.py`; briefs carry `terrain`, the ground along every base
  edge): stepped plinths, lower-storey windows, retaining skirts, doors and shopfronts at
  grade (lowered, raised or narrowed).
- **Collision**: hulls notched at skybridge landing doors (`collision.VESTIBULE_MM`).
- **Sky stations beside a tower** (the tube meets no mass there): a platform deck to the
  wall or onto a roof under it (`connections._beside`).
- **Checks**: `asset_types`, `asset_families` (twin towers one design), `asset_slopes`.
- **Art direction**: `assetgen review BUILD --spec S [--prev P]` (`review.md`), `assetgen
  spec diff A B`; rounds in the skill. Results: `docs/progress/AG5/`.

AG10 (layered districts) is in place (tests `tests/assetgen/test_ag_decks.py`, the small city
with a deck over Core, `agtools.deck_build`):
- **Deck pieces** (`assetgen/streets/decks.py`, in AG7's stage; `ctx._blockout_keys` runs the
  blockout's `_decks`): the slab per deck and tile keyed by the blockout's own object
  (`<deck>.slab.<tile>`; holes under 2 m2 filled, `slab_of`), with a coffered (planned eras)
  or ribbed soffit stopping round the undercity buildings, a fascia with upstand and drip
  edge on its real edges only, grime streaks and a stained soffit band, a rail (glass in the
  wealthy eras; none at a building on the deck, a ramp or its junction, a stair or
  elevator landing), soffit lights in two rows every 8 m over the ground streets, a
  colonnade (edge beam, columns every 7.5 m off the paths) over parks and plazas, a collar
  round a building it is cut round (`through`); columns (pier cap, shaft, capital, drop
  panel; the shaft alone in an undercity building), switchback stairs and elevators (doors
  at both levels, a landing or bridge to the slab's edge), each replacing its blockout
  object. On M13's terrain the slab is measured from the ground the deck stands on
  (`decks.Ref`: flat where level, else 8 m cells over the ground or the bases of the
  buildings on and under it).
- **Deck streets** (`roads.deck_kind`: `slab`, `ramp`): on the slab, no girder; a ramp solid
  with a walkway and parapet on each side (its walkways in `graphs.walkways`); a deck
  junction's own slab only past the deck (`walks._off_deck`).
- **Buildings** (`assetgen/buildings/decks.py`): the brief's `deck` record (role `on`,
  `under`, `near`, `through`; top, soffit and the slab's plan near it; only on such
  buildings, so other briefs and packs keep their bytes). Under a slab: a roof within
  1.2 m closed up to it by a louvered plenum band, parapets 0.3 m under it, no roof form,
  roof equipment, type features, masts, ducts and barrels kept under it (`roofs.Clear`'s
  ceiling), grime and lit ratio raised (`genome`).
- **Checks**, on a city with decks only: `street_decks` (pieces, 5.5 m over the ground
  streets, stairs and elevators reach both levels) and `asset_decks` (nothing of a building
  inside the slab where its role forbids, deck doors on deck walkways, no roof items under
  a slab). `asset_access` lets a door's path graze its own wall (`GRAZE_M`).
- **Previews**: `assetgen materials preview --views deck` (the section across the biggest
  deck, its near clip on the cut).
- **Exporter**: no code change (each deck piece takes its level from the blockout object
  it replaces); `docs/unreal_export.md`, "From AG10"; `test_stage2_takes_assetgen_decks`.
  Results: `docs/progress/AG10/`.

AG13 (ground cover and grass) is in place, in `assetgen/ground/` (tests
`tests/assetgen/test_ag_ground.py`, golden `tests/assetgen/data/golden_ground.json` by
`tests/assetgen/ground_goldens.py`):
- **`assetgen ground BUILD [--spec S] [--workers N] [--force]`** (`build.py`; also the stage
  of `assetgen build` after AG8's props and before AG6's materials, `--no-ground` skips it):
  per 256 m tile (`gather.py`: a job holding every input of its tile, its hash the tile's)
  M16's ground cover pieces meeting it, M6's median lawns (verges: grass on AG7's lawn island
  top, a lawn strip on a highway median clear of the barrier, nothing where AG7 tops the
  island with concrete), M14's decks, trees, the water within 60 m, M16's shade raster and
  M13's ground grid; a tile made again only when its job's hash or the code changes.
- **Surfaces** (`kinds.py`): per cover kind three AG6 sets, base, worn and shade
  (`materials/library.GROUND_SETS`: `ground_lawn`, `_meadow`, `_wild`, `_dirt`, `_mud`,
  `_gravel`, `_sand`, `_moss`, `_rubble`; generators at the end of `surfaces.py`); paving
  and overgrown paving on AG7's paving sets by what they pave. The mask per tile
  (`tile.py`, `ground/masks/<tile>.png`, 512 px, row 0 the south edge): R wear (desire lines,
  the piece's wear), G shade (M16's raster bilinear, tree crowns, 1 under a deck), B edge,
  A moisture; the ground master blends the sets by it.
- **Ground mesh**: each piece clipped to its tile on the 1 cm grid, triangulated exactly on
  its millimeters (`triangulate.py`), 0.1 m over the ground (on M13's terrain cut by its 4 m
  cells, vertices and normals on the ground grid), a primitive per surface and tile
  (`ground.<surface>.<tile>`), UV0 the plan position; `ground/tiles/<tile>.glb`.
- **Grass** (`clumps.py`, `tile.py`): clump kinds lawn, clover, flowers (a family per
  district palette: its era's palette pushed to petal colors), meadow, meadow_dry, reeds,
  cattails, weeds, fern and AG8's scrub and sedum (`props.trees` at ground cover scale), 3
  or 4 variants each, at most 400 triangles, COLOR_0 (height share, tone, dryness) for the
  grass master, in `ground/clumps.glb`. A candidate per mask pixel (0.5 m) in a grass-bearing
  piece, jittered and kept by splitmix64 hashes of its world cell with probability
  density x wear x shade x moisture x slope x the tile's cap (`kinds.GRASS`, 0.04 to 1.8 per
  m2; `TILE_INSTANCES` 40,000, the kept clumps scaled up by the cap's inverse square root,
  at most 1.5; a tile over the cap by chance drops the clumps kept by the least margin);
  the mix leans to ferns in deep shade and under crowns, reeds on wet ground, weeds where
  neglected; a clump stands only where its footprint lies in grass-bearing land clear of
  desire lines, decks and trunks. Transforms per tile in `ground/grass/<tile>.json`.
- **Checks** (`checks.py`, `ground_report.json/.txt`): `ground_coverage` (every piece drawn
  whole, every blockout cover object and median lawn replaced), `ground_grass_clear` (no
  footprint on a road, building, water, paving, deck or desire line, every clump on grass;
  on the model's own geometry), `ground_meshes`, `ground_budgets` (clumps per tile and city,
  3 million; triangles per clump, of all clumps, of the ground per tile and city;
  instanced triangles per tile). `ground/preview.png`: the city from above and the busiest
  tile up close (`preview.py`).
- **Exporter**: `unreal_contribution.ground.json` (`docs/unreal_export.md`, AG13): a ground
  actor per tile replacing the blockout's `<district>.cover_<kind>.<tile>` and
  `<district>.lawn.<tile>` objects (a `drop` where its tile draws none), the grass as
  instanced parts whose transforms stay in their tile's file (`xforms_file`), not Nanite,
  no collision, no shadow, culled at 60 to 100 m (`cull_m`), out of the HLODs; masters
  `M_CgGround` and `M_CgGrass` (sway by world position offset, `MPC_CityGen`'s new `Wind`).
- **Previews**: `assetgen materials preview` draws the ground tiles with AG6's materials
  (`ag6_materials.ground`, `grass`) and the clumps within 140 m of a street view's eye
  through AG8's geometry-nodes instancer. Results: `docs/progress/AG13/`.
AG12 (water) is in place, in `assetgen/water/` (tests `tests/assetgen/test_ag_water.py`,
goldens `tests/assetgen/data/golden_water.json` by `tests/assetgen/water_goldens.py`):
- **`assetgen water BUILD [--spec S] [--workers N] [--no-textures]`** (`build.py`; also a
  stage of `assetgen build` after the streets, `--no-water` skips it): pieces gathered from
  M16's data (`pieces.py`), each made from its own inputs and kept by hash as AG7's. Per water
  body and 256 m tile (`<body>@<tile>`, the body's own water: its polygon less the bodies
  before it in M16's order) a bed and a surface; per bank AG12 draws a piece by its id.
- **Fields** (`fields.py`, from a piece's inputs alone): M16's depth exactly
  (`Beds.depth_many`'s arithmetic on the body's banks within reach of the tile), the bottom
  AG12 draws (`bottom`: M16's bed raised to every sloped bank's slope carried on under the
  water, at a wall's toe up to its face, never within 5 cm of the surface), the level
  (flat: `surface_m`; M13's along a river), the current (along the flow line, the sea's
  tide along its shore, slower over shallows), foam (walls, waterlines, bridge piers from
  AG7's notes) and the sea's wave weight (M16's exposure on a blurred 16 m raster).
- **Meshes** (`grid.py`, `makers.py`): a region on a lattice, inside cells as two triangles,
  edge cells clipped on the millimeter grid and triangulated exactly (a piece the ear clipper
  cannot take split in halves), vertices shared by position. Bed (Nanite): 8 m on the sea,
  else 4 m, leaving out each sloped bank's dry strip (line to waterline), so the bank and bed
  meet along the waterline; a slot by M16's material, the underwater bank zone by the bank's
  (riprap stone, beach sand, marsh mud); steep triangles UV'd on their vertical plane;
  skirts 13 m down along edges shared with other water. Surface: LOD chains (sea 2, 4, 8,
  16 m; inland 4, 8, 16 m), UV1 the current, COLOR_0 foam, depth, wave weight. Banks: the dry
  strip on a 2 m lattice at the bank's slope, riprap stones as instanced parts (six meshes in
  `water/parts.glb`), stone walls along rivers and the sea.
- **AG7**: `Ground.water_level` is M16's surface on a flat city; quay and canal walls reach
  M16's toe and 0.5 m into the bed (`notes.foot`); canal walls follow the waterway's
  `canal_wall` banks (no longer across its mouth into other water); bridge piers and arch and
  pylon footings stand 0.5 m into M16's bed (`inputs.bed`), their footprints in
  `notes.piers`.
- **AG6**: sets `bed_mud`, `bed_silt`, `bed_sand`, `bed_gravel`, `bed_stone` (upper band),
  `bank_soil`, `bank_rubble`, `bank_rock` (`WATER_SETS`; generators in
  `materials/water_surfaces.py`), the `water` atlas (ripple normals, foam, caustics),
  `catalog.WATER` (per water kind sea, river, canal, ornamental, marsh: scattering,
  absorption, shallow and deep color, clarity, flow, foam, waves) and `WATER_SLOT`; masters
  `water` and `bed`; the texel check reads the water packs (beds at the upper density).
- **Checks** (`checks.py`, on the packs read back against the model): `water_coverage`,
  `water_levels` (surfaces at their level, beds at AG12's bottom, never deeper than M16's),
  `water_gaps` (bank waterlines on the bed, AG12's and AG7's wall feet in it, skirts),
  `water_meshes`, `water_budgets` (400k triangles and 60k stones a tile, 9M a city),
  `water_replaces`. `water_report.txt`; `water/preview.png` (`preview.py`).
- **Exporter**: `unreal_contribution.water.json` (surfaces non-Nanite LOD chains, beds and
  banks Nanite, the drop of the blockout's water, `underwater` per body), `M_CgWater` (Single
  Layer Water, flow-mapped ripples, depth and mask foam, the sea's Gerstner waves by world
  position offset: decision 13.10 (a)), `M_CgBed` (caustics), a post-process volume per swim
  box (`docs/unreal_export.md`, AG12). **Blender**: `ag6_materials.water` and `caustics`;
  `assetgen materials preview --views water` (a canal and a river bank up close, the harbor
  from above). Results: `docs/progress/AG12/`.

AG14 (fit and finish, from the first run-through) is in place (tests
`tests/assetgen/test_ag_fit.py`):
- **Fit checks** (`assetgen/fit/`: `glb.py` reads the packs back in world space, `index.py`
  a plan index of triangles, `build.py` the stage; `assetgen fit BUILD`, also the last stage
  of `assetgen build`, `--no-fit` skips it, as do `--no-streets` and `--no-props`;
  `fit_report.json/.txt`): `asset_grounded` (every
  standing prop and plant, roof item and dunnage, road, transit and deck column rests on a
  surface under it within 2 cm: five points of its feet, three of them on a surface no more
  than 0.6 m over them (a dunnage frame its height), surfaces the up-facing triangles of
  every pack and the blockout's land; and every road's carriageway meets its junctions'
  surfaces within 2 cm near its cut) and `asset_clash` (road carriageways in building
  masses; building vertices past their masses by 0.3 m over a carriageway under 4.5 m;
  bridge and raised road deck tops over each other; transit in a mass outside its portal
  band, tracks in a platform). What fails: roof items, dunnage and street pieces off
  their surface, any junction step over 2 cm and floating quay railings and shrubs
  (since #89), any clash; reported only: other props and plants (at the model's
  heights, M20's `prop_support`). Since issue #95
  `asset_clash` also checks barriers and props at junctions (`fit/barriers.py`): any
  barrier (AG7's `concrete.barrier`, a footbridge's railings, a deck's rails, a trench's
  walls) standing on another road's carriageway, on a junction's surface (a junction's own
  barriers in one of its connector lanes), on a crosswalk, or through another piece's
  barrier (two pieces at a node they share may overlap where they join, `JOIN_M2`), more
  than `INSET_M` (0.1 m) in; any standing prop's low footprint (AG8's variant, 2 m up) on a
  vehicle carriageway, a junction or a crosswalk (parked vehicles, a signal at its
  crosswalk's end excepted) or through a barrier. AG8 draws a prop's hashed variant, else the
  next of its family in turn, that keeps clear of them, else leaves the prop out (`props/gather._Fit`), and M6's
  quay railings and median barriers stand at most 5 cm onto a junction a vehicle road meets
  and keep 1 m off a crosswalk, railings also off any road's carriageway but a pedestrian
  street's (footbridge decks too), at their height (`props._clear_of_roads`).
- **Streets** (AG7): M19's supports (`transit_column` 2: frame legs flat under their beam,
  piers on footings down to M16's bed, sky tube masts with crosshead, legs, tie and stays
  where the model has them (`supports: mast`; plain pylons with their cradle by default,
  issue #94);
  `transit_beam` 2: haunched cap beams, tapered cantilever arms); road columns in the water on
  footings (`column` 2, `structures.footing`); a bridge whose segment ids are empty finds the
  raised segments that carry it (`structures._carriers`) and draws no deck of its own;
  footbridge edge beams outside the girder (`bridge` 2); M18's embankments carry the deck's
  low stretches, the girder only between them, their faces across where it goes on (`road`
  2, `roads._spans`); a road's skewed cut at its corners' own heights (`Road.z_at`);
  junctions without a model surface anchored to their legs' heights along the outline, a
  leg's square-cut corners inserted on it (`junction` 3, `walks._with_corners`), every
  outline vertex on a leg's cut (within its half width across it, 1 m along it) at the
  leg's height (`_cut_run`).
- **Buildings**: roof items on the roof the shell built (`roofs._seat`, `_top_of`, `_pull_in`,
  `_onto_top`; a halo's open roof, a stepped tier, a mansard's flat top), dunnage legs to the
  form under the frame's corners, moved onto the form where a frame would pass the roof's
  edge, a mansard's surface by distance to its eave ring (concave rings); curved walls
  (`shell.arc_of`: a chord of a mass's M21 arc) with the curve's normals
  (`meshbuf.Buf.arc`, `_arc_normals`) and glazed joint to joint; briefs give every edge its
  nearest lane (`lane_m`, `lane_s`, `lane_z_m`, `brief.lane_gaps`, `BRIEF_VERSION` 3) and
  nothing that leaves a wall reaches it under `parts.ROAD_CLEAR` (4.6 m) over it
  (`Facade.on_road`, `room`, `_low`, `_edge_ok`; cameras, ducts and fire escapes;
  `envelope` `over_road`); canopies stop short of an inside corner. `GEN_VERSION` ag14.3.
- **Exporter**: no code change (`docs/unreal_export.md`, "From AG14"); the packs' normals
  are kept on both import paths (`test_stage2_packs_keep_their_normals`).
- **Sky tube rings** (issue #97, after run-through 2): `sky_tube` 2 draws the ribs at the
  model's rings (`attrs.rings`, the line's evenly spaced rings in the piece's stretch; a
  model without them every 10 m from 5 m in), each lit ring with an LED band on the rib's
  outer face (`RIB_N` 12 beams, `LED_W` 0.2 m along the line) in the line's color at full
  brightness (`streets.materials.led_slot`: slot `led.<hex>`, made on demand by
  `slot_spec`, master `emissive`; AG6's catalog puts `led.` on `neon`, brighter by
  `MPC_CityGen`'s `Night` in Unreal and in the Blender night previews).
- **Junctions** (issues #82, #89, after #95; `walks.py`): of two junctions whose outlines
  overlap at one height the larger draws the overlap, the other its outline less it at the
  owner's heights on the seam (`_overlaps`, `_carriageway`; Delta's `jn.e217s328` and
  `jn.e170s444` each held the whole ramp between them); the outline beside a leg run on
  inside its junction past 40 m takes the leg's height (`_along_legs`); the slab under a
  raised junction follows its surface (`_draped`); corner sectors follow a leg that bends
  (`_along`, `_meet_along`), none between twin legs (`_twins`); pads keep off other
  junctions, roads, sidewalks and the connector lanes, whose runs off the outline round the
  corners are paved (notes `paved`) off the roads in every corner, a leg's own past its
  cut too (#114: `_roads_near`, `barriers.junction_area(..., every=True)`), and stand on the
  curb's height (`_edge_z`); a
  cul-de-sac gets a sidewalk round its bulb (`_bulb`); sidewalks and medians are not drawn
  over a carriageway at their height (`_clip_rings`, `roads._median_clip`,
  `_clear_spans`), a sidewalk's stretch a carriageway reaches over only in part drawn flat
  on the rest of its width (`_fills`, `_fill`); drawn outlines lose the needles an overlay
  leaves (`_despike`) and are paved through holes under 4 m2; a draped slab that would fold
  is left out; an outline vertex on a leg's cut takes the height of the road row it
  lies on, and road rows just past the cut (to the far cut on a road under 12 m) that fall
  on the outline become its vertices (`_run_z`, `_road_rows`, `_with_corners`, leg `far`).
  AG8 seats a standing prop on a raised junction's corner pad at the pad's surface
  (`_RaisedCorners.pad_top`), leaves one out on a corner or its legs' rights of way inside
  the cuts with no pad, carriageway or sidewalk under it (notes `raised`, `rows`) and keeps
  props off the paved lanes; on a terrain city quay railings stand with their foot on the
  quay as AG7 draws it (`_quay_tops`: AG7's quay piece made again, paving and coping,
  `_Tops`) and ground plants with their foot's middle 5 cm into the ground (`_seat`).
  `asset_clash` also fails on a sidewalk, junction corner or median over a carriageway at
  its height (`fit/strips.py`).
- **Grounded rule** (#105): a thing rests on three of its five feet (`fit.build.rest_gaps`,
  the third smallest gap; a frame's own top never holds it up); #89's railings and shrubs
  fail with no foot on their surface, reported on fewer than three. AG4 seats every roof
  part on all its feet on the roof the shell drew (`roofs.Stand`: items laid out and tested
  with their frames, `_lay`, moved in 0.25 m at a time up to 6 m, `_inward`; huts, vents and
  skylights only where they stand). `GEN_VERSION` fix105.1.
- **One-building fixes** (#144): `rings.tidy` closes a spike the way that keeps nearest the
  outline; open sheds roofed and columned in their cladding, thumbnails drawing pillars and
  roof equipment; type clutter off the corridors; a skybridge end over 1.5 m from every wall
  lands on a roof (`connections.wall_of`, `on_roof`) or none. `GEN_VERSION` fix144.1.
Results: `docs/progress/AG14/`; the sky tube fixes: `docs/progress/sky_tubes/`; the junctions
fix: `docs/progress/fix_junctions/`; the grounded rule: `docs/progress/fix_grounded/`; the
one-building fixes: `docs/progress/fix_one_building/`.

AG15 (cyberpunk facades and night, from the first run-through) is in place (tests
`tests/assetgen/test_ag_night.py`):
- **Facades** (`buildings/skins.py`): seven systems (`systems.AG15_SYSTEMS`: `led_grid`
  LED-strip mullions, `hex_skin` honeycomb panels, `folded_glass`, `mesh_screen`,
  `media_facade` a screen over a block of floors, `diagonal_glazing`, `slit_panel` with the
  `slits` window), their parts (`skins.FAMILIES`: led, hex, fold, mesh, media, frit, logo;
  slots `led_<accent>`, `screen_media_*` emissive); window patterns per group (gene
  `{g}.wpattern`, `systems.PATTERNS`: stagger, mixed, stepped, checker, scatter, alternate,
  applied row by row in `skins.pattern_ops`, not on door rows); a skin over any glazed
  system (`skin`: LED strips or fritted glass); colored glass; M21's bands and curved shafts
  get mullions, fins or LED strips at their joints and bay, their own sills by pattern
  (`shell._simple_facades`). `genome.reach_of` (`systems.REACH` by archetype: corporate
  core 1, midtown 0.85, ...) weights AG15's systems, patterns past the grid, colored glass,
  skins, crown lights and logos.
- **Neighbor rule** (`buildings/neighbors.py`): towers (`genome.is_tower`, M21's) within
  150 m outside one family differ in system, (window, pattern), (wall, glass) and (light,
  accent), and no two vacant towers side by side: units (a family or a tower) tallest first
  draw again with what their earlier neighbors took (`genome.make(brief, avoid)`); what a
  tower avoided is in its asset hash. `asset_unique` gains `neighbors` (also day and night
  thumbnails `THUMB_MIN` apart).
- **Night** (`buildings/night.py`): the genome's `extra.night` (schedule by use, a share of
  towers vacant by danger and wealth; light color temperature; spread; an office's band of
  floors), Custom Primitive Data 30 to 35 (`materials/params.py`); the lit share by schedule
  and hour band (`HOURS`, `MPC_CityGen`'s `Hour`); crown and edge LED strips and a lit logo
  on towers (`crown_light`, `logo`, `skins.lights`); night thumbnails (`thumb.render(...,
  night)`, record `ag15`). `GEN_VERSION` ag15.1.
- **Blender**: the glass and proxies light by schedule (`ag6_materials._night_rooms`,
  `set_hour`); spot lamps and sign washes by night; `assetgen materials preview --views core`
  (the corporate core from the air and a street through it), `--hour`.
- **Exporter**: `M_CgGlass` by schedule and Hour (`STAGE2_VERSION` 8); the play features'
  spot lights under the 192 nearest lamps, `M_CgLightPool` decals under 768 more, sign
  washes (`docs/unreal_export.md`, "From AG15").
Results: `docs/progress/AG15/`.
The asset fixes (issues #83, #85, #88, #90, after run-through 2) are in place:
- **AC units and ivy in the building's frame** (`brief.frame_z`, `FLOOR_MOUNTS`): M20 hangs
  them on a floor's facade at a height over the ground where they hang
  (`props.Ctx.facade_spot`); the briefs give them their height over the building's base (AG3's
  panels and trellises and the mount check read it there), AG8 lifts them by the ground where
  they hang (`props.gather.over`), and M20 puts none on a wall the ground buries at its spot.
  The ground floor's shop signs, awnings, wall lights and cables keep their heights over the
  base, under which AG3 and AG5 build the shopfronts.
- **Doors**: a unit whose nearest wall faces another building sits on a facade within
  `brief.UNIT_REACH_M` 2 m more facing its own street (`unit_loc`); a moved main entrance
  with no room for its door shares a shopfront's (`fronts.Band._share_shop`, stat
  `entrances_shared`); `asset_access` lets a path graze a neighbor's wall (`GRAZE_M`).
- **Neighbor rule**: a hero's or type's weighted system draws past its neighbors' within its
  weights (`genome.make`); in a city a regeneration made (`city_state.json`'s edits) the
  towers outside the last edit's district keep their records' genomes
  (`neighbors.held_towers`, records `ag15.avoided`, `ag15.held`; the old manifest in the
  build folder); `assetgen brief seam BASE REGEN --district NAME` (`briefdiff.genome_seam`).
- **Fins round a corner** (`shell._corner_road`): no fin near a facade's end reaches in front
  of the next edge where that faces a road with no sidewalk, under the headroom.
- **Exporter**: roof traces count 3 m over the building's pivot (#83); `import_city.unstage`
  resets an actor going back to the blockout, `CITYGEN_UE_DIGEST_ROWS` (#85); sign washes
  over the building's base (#90); the small city's import test streams at 600 m.
  `GEN_VERSION` fixassets.4. Results: `docs/progress/fix_assets/`.

AG17 (road surfaces by construction, after M22; scope 14.18) is in place, in
`assetgen/streets/pave.py` (tests `tests/assetgen/test_ag_junctions.py`, `test_ag_triangulate.py`):
- **Faces:** AG7's road, junction and sidewalk pieces draw M22's pavement map (keys as before):
  a road piece its carriageway faces, bends, walking surface and median (and a side's sidewalk
  bands where no sidewalk piece draws them), a sidewalk piece its side's curb band, furniture
  zone and clear path, a junction piece its carriageway, corner pads and bulb (a cluster's whole
  surface, unbuildable ones as they are). Each face on its stored vertices in order, never split;
  its interior by `triangulate.triangulate_face` (exact ear clipping keeping every boundary
  vertex, the shortest diagonal first so a long ribbon is a strip, `_clip_best`; holes that
  touch at a vertex joined; the face's samples as Steiner points strictly inside; Delaunay
  flips across every edge that is not boundary). UV0 along the road from the map's rows
  (`roads.row_uvs`: a vertex's station and offset), bends and junctions in plan.
- **Heights** (`Index`, built once on `Ctx.pave`; a piece's inputs carry every vertex as
  [x, y, top, z, z over ground] in mm): a vertex's height over sea level (the map's z plus
  `Ctx.ground`) plus its face's lift: carriageway, junction, bulb, bend and walk 50 mm
  (`ROAD_DZ_MM`); curb band, sidewalk and corner pad 200, 70 at a curb ramp (`Index.ramps`: the
  curb band's vertices beside a crosswalk's end or a garage, loading or gate entrance, at least
  the one nearest each); an avenue's, street's or service road's median of 1 m or more an
  island at 200, level with the road under a crosswalk and from it on to a road end within
  40 m (`mdrop`, its cut-through concrete). A bend face's asphalt follows its lanes, its sidewalk
  part paving; a junction's carriageway part apart from its main one asphalt only along its
  connector lanes, paving elsewhere. Marks and details
  lie on the faces as drawn (`Surface`; lane rows at the map's stations, `roads.map_stations`).
- **Curbs and walls:** where two faces meet at different lifts the higher face's piece draws
  the wall between them, the same stored polyline at two heights (`walls`); outer edges walled
  down (`bottoms`: into the ground, a raised road's 0.45 m fascia, an embankment's fill, a deck
  street onto its slab); walls of several faces meeting at a vertex the faces only touch at
  take a vertex on that edge (`draw_walls`, `Mesh.wall_mm`'s split). A raised road's girder
  runs between its cuts only, capped on its port lines; a raised junction stands on a slab of
  its own (`deck_d`, down to the ground where low, 0.1 m under it in a cut), its edge on its
  ports from 0.45 m under the seam.
- **Barriers** (`barriers.py` reworked): spans between the cuts less crosswalks, every end at a
  cut on the road's port line (`Road.port_frame`, `port_lines`): `join`, `open`, `stop`; a
  junction's corner parapets (raised) and guard walls (at grade) along its faces' boundary
  (`_loops`) between two legs' outer port vertices (on the port line where it is straight,
  else square and a section's width short), out of its connector lanes (`_off_lanes`), split
  where the edge turns back (`_split_sharp`); the median across between port middles where
  no lane crosses or runs along it (`junction_plan`). Spans keep to the road's own faces
  and off every crosswalk; a road with no faces has none.
- **Checks:** `street_watertight` (`streets/watertight.py`, on the packs read back): every
  segment of every edge two faces share drawn by both faces' pieces on the same millimeters, in
  exactly two triangles (a face's and its neighbor's, or its curb's). AG14's step check
  (`fit.seams`) compares a road's and its junction's pieces at the map's port vertices exactly.
- **Retired:** `path.first_exit`, `Road._edge`, `CUT_TOL_M`, `_with_corners`, `_cut_run`,
  `_run_z`, `_surface`, the duplicate `_corner`, `_fills`, `_overlaps`, `_carriageway`,
  `_clear_spans`, `Keepout`, `clip_line`, `roads._median_clip`, `_make`'s tidied line.
- **Footbridges** (faces of M22's map since #147): the road piece draws a footbridge's walk
  faces as any road's, from its stairs' feet at its ports, and its girder under them between
  its cuts; the bridge piece's railings run along them, `barriers.FOOT_CLEAR_M` off the
  junctions; `street_watertight` covers their seams.
- **AG8:** props keep off the map's carriageway faces (`_Fit`) and stand on a raised junction's
  pads as AG7 draws them (`_RaisedCorners`), both from the map. No exporter change.
Results: `docs/progress/AG17/`.

AG16 (performance) is in place (scope 14.17, issue #96; `docs/unreal_export.md`, "From AG16"):
- **Benchmark** (`citygen unreal BUILD UPROJECT --bench` or `--bench-only`, `--bench-runs`,
  `--bench-label`, `--bench-passes`; `citygen/bench.py`, the driver `UCityGenBench` in the
  play plugin, started by `-CityGenBench=<job>`): a route from the build alone (three
  sidewalk walks, a drive along the lanes, a flight at 150 m, a teleport) in a standalone
  `-game` process at 2560 x 1440 (windowed fullscreen, kept DPI-aware), day and night,
  native and 67% TSR, after warm-up flights; per frame the frame, game, render, RHI and GPU
  times, draw calls, streaming, VRAM and RAM, beside the engine's CSV profile; JSON, a table,
  graphs and the last run's shots in `docs/progress/AG16/bench/<city>/<label>`; it waits while
  other heavy processes run (`bench.busy`), samples their CPU through each run and names a
  CPU-starved run (`bench.starved`: a first run after an import is one). `bench.side_by_side`
  pairs two benchmarks' shots.
- **Exporter fixes**: a part or sign node of one name imported once for every tile
  (`unreal.share_meshes`); records as components (`unreal.group_actors`, the manifest's
  `groups` and `holder`: an entry's parts on its actor or a `BP_CityGenGroup`, a street front
  on its building, a tile's signs, street, water and cover pieces on a group per kind and 64
  m cell; `CITYGEN_UE_GROUP=0` keeps an actor each), the group Blueprint's root static
  (`CORE_VERSION` 3); props no one touches without collision (`NO_COLLISION`); the masters
  read Custom Primitive Data through per-instance custom data (`per_instance`,
  `STAGE2_VERSION` 10: the instanced HLODs keep each building's look); World Partition's main
  cells 128 m (`MAIN_CELL_M`) loaded 768 m around the player (`VIEW_M`); `r.TextureStreaming=0`
  and the Nanite pool from the city (`nanite_pool_mb`, `PROJECT_SETTINGS`) in the project; the
  play actor enables an underwater volume only near the view (`UpdateUnderwater`); stage 2's
  packs imported, saved and let go of 150 at a time (`CITYGEN_UE_PACK_CHUNK`, the `Meshes`
  map, #84; offloads by actor guid, an actor whose class changes destroyed and saved
  first, `clear_moved`). Delta Megacity: 73,772 actors to 13,644, 53,911 distinct Nanite
  meshes to 44,667, the 95th percentile frame from 27 to 49 ms to about 8 to 13 ms.
- **Budgets** (`assetgen/scene.py`, in `asset_budget` at the end of `assetgen build`, with
  `assets/scene_budget.json`): the scene as the exporter's own manifest makes it (actors,
  components, distinct Nanite meshes, instances, root pages against the pool) per city and
  per 256 m tile (`CITY`, `TILE`).
- **Left**: garbage collection in an uncooked game, 70 to 350 ms about every 40 s while
  streaming; UE 5.8's experimental async physics bodies and incremental collection made no
  gain or worse.
Results: `docs/progress/AG16/`.

AG18 (hero vehicles, scope 14.19) is in progress, and is not a generator: vehicles designed
one by one as Blender scripts in `vehicles/` (kit `carkit.py`, a script per car in `cars/`,
brand book `BRANDS.md`: seven made-up makers whose language is geometry and texture, never
color; design brief `BRIEF.md`; guide `README.md`), one multi-view sheet a car in
`docs/progress/AG18/<car>/`, the roster in `docs/progress/AG18/README.md`. Phase 1 is built
(21 vehicles, 2026-11-10; line-up `vehicles/lineup.py`, `docs/progress/AG18/lineup.jpg`) and
waits for Swagnik's review.
- Every Blender run for a vehicle goes through `vehicles/blender.sh`, which queues runs
  across sessions on one lock.
- The owner's concept images are in `reference/car_concepts/` (gitignored, inspiration
  only, never copied); `.blend` and `.glb` files of vehicles are not committed.
- No tests and no goldens: a car is checked by building it and looking at its sheet.
- **In Unreal** (2026-11-11, `citygen/unreal_vehicles.py`; `docs/unreal_export.md`, "AG18's
  vehicles"): the packs as a library under `/Game/CityGen/Vehicles/<car>` (a mesh a part
  with the pack's four LODs, no Nanite, `M_CgVehicle` recoloring by per-instance custom
  data, thin translucent glass), placed by contribution entries of kind `vehicles` (one
  instanced component per model and part); `--check-vehicles`; shots in
  `docs/progress/AG18/unreal/`.
- **Game packs** (phase 3, scope steps F and G, PRs #194 to #199): `vehicles/game.py`, its
  contract `vehicles/GAME.md`; `vehicles/blender.sh vehicles/game.py --car NAME [--docs]
  [--test]` turns a car's script, unchanged, into a pack in
  `~/.cache/cybergen/vehicles/game/<car>/` (never committed: four LOD glTFs, baked atlases
  with the paint as a mask, collision hulls, `pack.json`); `--docs` writes its proof
  `game.jpg` and `game_report.json` into `docs/progress/AG18/<car>/`. The built packs are a
  GitHub release of this repo (`vehicles/packs.py`: `fetch` on a machine without them, every
  file checked against the committed `vehicles/packs.json`; `publish` after rebuilding
  packs, committing `packs.json` in the same PR; `status`). Size classes standard
  and large (55 m2 of exterior or more: LOD3 8,000 triangles, texel floor 240 px/m against
  5,000 and 300). Built for 18 vehicles, every check passing (the faults of the first run
  fixed in `game.py` and nine packs rebuilt, 2026-11-12; the other nine are as first built).
  A pack is the car parked and shut (`CYBERGEN_SHUT`, `SHUT_ENV` in `game.py`).
  `CYBERGEN_GAME_DEBUG=1` logs each far LOD wreck.
- **Vex** (vex_wraith, vex_halo, vex_strix) is to be redesigned (Swagnik, 2026-11-10): no
  packs, out of every later step until redone. **The Aurels** (aurel_prelate, aurel_regent,
  aurel_zenith) likewise since the play fixes (Swagnik, 2026-11-12: "they look terrible"):
  their scripts stay, their packs are no longer shared (out of `packs.json`), and nothing
  places or imports them (`assetgen/parked/table.EXCLUDED`, `citygen/unreal_vehicles.EXCLUDED`,
  `vehicles/packs.py` and `survey.py`'s `EXCLUDED`). 15 cars are in the cities.
- **In the cities** (step H, 2026-11-11; `assetgen/parked/`, tests
  `tests/assetgen/test_ag_vehicles.py`): `assetgen vehicles BUILD` (also in `assetgen build`
  after the props, `--no-vehicles`) makes every M6 parked car AG8 draws a pack vehicle: a model
  by its district's weights (`parked/table.py`: a row per archetype scaled by wealth and danger
  through the model's class; the spec's `vehicles.weights`), the first in that hashed order
  whose plan box lies on its own road's carriageway faces of M22's map, off the crosswalks,
  0.5 m from its neighbors and never the third of one model in a row (the play fixes: the
  model before it on the curb is tried last, so two running happen only where nothing else
  fits: Delta 1 of 2,848 curb neighbors, 10.7% before; `vehicles_variety` fails on three in a
  row or a share of 5%), else left out with a reason; paint per placement from its role's palette and the district's colors; hover cars
  set down on their lowest point. `unreal_contribution.vehicles.json` (a placement entry per
  tile replacing `prop.parked_vehicle.<tile>`; the exporter drops what a placement replaces
  from stage 2, `unreal_vehicles.without_replaced`), `vehicles_report.txt` (checks
  `vehicles_coverage`, `_clear`, `_variety`, `_replaces`, `_library`); AG16's scene count and
  the textured previews (`assetgen materials preview`) take them. The library: the spec's
  `vehicles.library`, `$ASSETGEN_VEHICLES` (`off` for none; `tests/conftest.py` sets it off),
  `$CITYGEN_VEHICLES`, the packs' cache; without one, or with `vehicles.parked: variants`,
  nothing is written and AG8's variants stay (the props package and its goldens untouched).
  Proof on Vesper Bay: `docs/progress/AG18/city/`.
- **The kit's tools** (step A, 2026-11-12; `vehicles/README.md`): `--clay`, `--zebra` and
  `--turntable` on any car script (the form without paint, surfaces by their stripes, the
  car from all round); `--check` (`vehicles/carcheck.py`: tire clearances and steering
  room, ground clearance, symmetry, open panel edges and cutter holes, cabin parts in the
  open, a 400,000 triangle budget; `ok`, `look` or `fail`, `K.meant(...)` in a script for
  what is meant); `python vehicles/survey.py [--docs]` runs checks and renders on every
  non-Vex car (`docs/progress/AG18/checks.md`, each car's `check.json`, `clay.jpg`,
  `zebra.jpg`). Brand helpers are in `vehicles/brands/<brand>.py` (the cars keep their own
  copies until a step edits them).
- **Changing `carkit.py`:** `python vehicles/survey.py --sign DIR` before and after, then
  `--compare A B` (`vehicles/signature.py`: every object's geometry, the materials, the
  studio and the cameras of every car, Vex included). The same fingerprints mean the same
  sheets and packs; a car that moves is named in the PR and its sheet and pack left to the
  step that changes it.
- **Step B** (lamps, cut lines and glass; started 2026-11-12, `vehicles/README.md`,
  "build_body"): `build_body(cutters=fn)` lays cutters on the uncut hull (`groove()` shut
  lines and light channels, `pocket()` housings and recesses; `"skin"` makes the skin cut
  away a lens or a flap with the gap all round), `Lamp` (projectors, reflectors, guides),
  frit glass and mirrored trim frames (`glass` modes `"frit"`, `"frame"`), even cap bands,
  `wiper()`, lazy materials (`need()`: lenses, chrome, frit). The game pack leaves lenses out
  (`game.LENS_MATS`), baking the lamp behind them. Done: the kit and the Vanta-R (its pack
  rebuilt), then the Dart, Lumen, Hauler and Mino as brand pilots. The Aurels are set aside
  (Swagnik, 2026-11-12; the Prelate's attempt on branch `claude/ag18-prelate-step-b-wip`).
  The Sable, Ridge, Meridian, Atlas, Pebble and Aria followed (2026-11-13; the Orrins keep 2.4 mm shut lines, which tore their far LODs at 3.5 mm). Next: the other four non-Aurel cars, each switching to its `vehicles/brands/` module.
- The other phases (improvements, AG8's parked vehicles and
  stage 4's fleet drawing on them) are listed in the scope with their plan.

Progress output: `assetgen build`, `preview`, `materials preview|board`, `library`, `streets`,
`water`, `props` and `ground` print a line per stage, a bar (n of N, time left) where the count is known and
the time per stage on stderr (`assetgen/progress.py`, stage 1's `Progress` interface; one
redrawn line on a terminal, plain lines when piped; workers never print, the parent advances;
Blender scripts print `CGPROGRESS start|done <name>`, read by `assetgen/blenderrun.py`);
`--quiet` or `CYBERGEN_QUIET=1` silences it. A new long stage takes a `progress=None`
parameter and wraps its work in `P.stage(...)`, but never inside a package whose code hash
an output records (`streets/`, `props/`, the library's `CODE`): wrap those from the caller,
or the goldens move.

## Light and atmosphere generator (atmosgen)

`docs/atmosgen_scope.md` is the spec for stage 3 (milestones AT0 to AT7, all done, section 13;
Swagnik's decisions of 2026-11-10 in section 12), its log `docs/atmosgen_milestones.md`: a
generator of light and air, not of geometry. A deterministic plan per city (every light
that casts light, fog and smog volumes, steam emitters, rain shadow and wetness masks, sky
glow, schedules by hour) keyed by M10's ids, checked (light on every walkway and
carriageway) and previewed in Blender; layer 3 of the manifest; a C++ runtime plugin,
`CityGenAtmos`, beside `CityGenPlay`, that renders it (lights per tile, time of day,
weather, effects, post) and takes over the play features' lamps, pools, washes, moon and
night exposure. AG16's benchmark by night is its baseline; the night pass stays at or under
16.7 ms p95 at native 1440p on the PC (decision 12.6). **Benchmarks** (Swagnik, 2026-11-12):
the lean route (`--bench-route lean`, the default with `--bench-atmos`: one walk, the drive,
the flight, no teleport, a short warm-up), only `night_plan_all` and the passes the change
touches (`dusk_plan` only where it differs by dusk), one run (a second only within 0.3 ms of
16.7 ms or when the run was flagged: foreground lost, CPU starved), no "before" run (the
previous milestone's "after"); tune with quick GPU profiles at fixed viewpoints, not route
runs. Package `atmosgen/` beside the
others, which it reads only (citygen's model JSON, assetgen's `signs.json`); tests in
`tests/atmosgen/` (`test_at_*.py`, no `conftest.py`).

AT0 (contract and spike) is in place:
- **Spec and presets** (`atmosgen/spec.py`, `presets.py`; `python -m atmosgen spec
  validate|schema`): looks (`neon_rain` the default, `clear_night`, `smog_dusk`,
  `overcast_day`), weather states, light temperatures, photometric classes (cobra head,
  post top, wall pack, high mast, soffit, sign face, neon band, holo face, shop sign, shop
  spill; physical units: candela, nits), schedules for every hour (24 values), tiers and
  budgets; every district's mood from its archetype pulled by wealth and danger
  (`spec.mood`: clean where wealthy and safe, gritty where poor and dangerous).
- **Plan** (`planmodel.py`, schemas in `atmosgen/schemas/`; `atmosgen plan BUILD [--spec S]
  [--out DIR]`, `plan.py`): `BUILD/atmos/atmos_plan.json`, `lights/<tile>.json` (citygen's
  256 m tiles; a light per M6 street and wall light at its lamp head, per sign slot face as
  a rect light in its sign's color, per M3 unit's shopfront; id `<owner>.light`, a hash per
  record, schedule, flicker and broken by mood), `unreal_contribution.atmos.json` (layer 3's
  format), `atmos_report.json/.txt`; only changed files written. `atmosgen lux BUILD`:
  `preview_lux.png` (the plan's illuminance round the core, no occlusion until AT1) and
  `preview_plan.png`.
- **Emitter asks of assetgen** (`emitters.py`, assetgen scope 4.6): a lamp variant's
  emitter (class, lens, normal, size) and a sign's lit face and emitted color; derived from
  citygen until then (`Light.source`).
- **Runtime** (`citygen/ue/CityGenAtmos`, built with CityGenPlay by
  `unreal_play.build_plugin`; assets by `citygen/unreal_atmos.make_assets`,
  `citygen/ue/atmos_assets.py`): the controller reads a plan, keeps a live set by tier, fog,
  rain cards, a wet decal, MegaLights by a post-process volume; console commands
  `CityGenAtmos.*`; spawned by `-CityGenAtmosPlan=<dir>` (AT1 places it at import).
  `CityGen.PlayLamps` turns the play features' lamps off. The benchmark's
  `--bench-atmos DIR`, `--bench-rt` and `bench.ATMOS_PASSES` (`docs/unreal_export.md`,
  "atmosgen's runtime (AT0)").
- **Blender night preview** (`atmosgen preview BUILD`, `preview.py`): AG15's night preview
  (`assetgen.materials.preview.make_job`) lit by the plan's lights in Cycles, with the
  weather's haze and wet streets (`ag6_preview.py`'s `atmos_lights`, `haze`, `wet`).
- The spike's measurements and recommendations: `docs/progress/AT0/README.md`.

AT1 (streets at night) is in place:
- **Lights by photometric class** (`presets.PHOTOMETRY`, Unreal's own profile: a spot's
  peak flat to its inner cone, falling as $t^2$ to its outer, a point's all round, a face's
  by its cosine, each in the engine's reach window): cobra heads 1200 cd to 62 degrees (AT0's
  6000 cd in 45 lit 52 lx under the heads and the junctions dark), post tops, wall packs,
  highway columns, soffit, tunnel and platform classes.
- **New lights** (`atmosgen/plan.py`): a mast arm on every traffic signal over its junction
  (`signals`); highway and ramp columns (a twin arm in a median, else staggered at the edges),
  service roads, footbridge posts (`roads`); wall packs along alleys spaced by the mood's
  alley darkness (`alleys`); AG10's soffit lights under M14's decks (`decks`, AG10's own
  `_ground_streets` and `_lights`); AG7's tunnel and underpass strips (`tunnels`); platform
  downlights in elevated and underground stations (`stations`); corner poles at the
  junctions the lux check finds dark (`corners`: at the junction ends of its legs'
  sidewalks and its crosswalks, the one leaving fewest points dark first, at most
  `CORNER_MAX`). Each light's `mount` says what it hangs on; `pole`, `mast_arm`, `wall`
  and `canopy` are fixtures asked of stage 2 (`emitters.py`'s third ask, assetgen scope 4.6).
- **The lux check** (`atmosgen/lux.py`, scope 8): every walkway and lane every 2 m by class
  (sidewalk, crosswalk, carriageway, under_deck, alley; park paths reported), with occlusion
  against the building masses and deck slabs (`Occluders`, a 1 m raster of lowest bottom and
  highest top, marched every meter), at 23:00; a class passes on its city average, at most 5%
  under its minimum, no alley point dark, and per district half the average and 15%
  (`presets.UNDER_MIN_SHARE`, ...). The plan's `checks.lux`; `atmosgen plan` exits 1 when it
  fails, and the exporter leaves such a plan out. `preview_lux.png` with occlusion.
- **Exporter** (`citygen/unreal_atmos.write_atmos`, the manifest's `atmos`, `atmos.json`):
  the `CityGenAtmos` controller (key `atmos`, always loaded, the plan's settings) and a
  `CityGenAtmosCell` data actor per 128 m cell (`atmos.lights.<tile>.<quarter>`, spatially
  loaded, its lights packed: 16 floats and 2 ints each) placed by the import (`--atmos DIR`,
  default BUILD/atmos; `--no-atmos`); a cell registers its lights with the controller as it
  streams in, the controller's pooled live set (512 within 300 m, 16 shadowed) renders them
  by night (`MPC_CityGen`'s `Night`). `-CityGenAtmosPlan` and the subsystem are gone; the play
  features lose AG15's spot lamps and washes (`play.json` 3), keeping the light pools as the
  far tier; `--bench-atmos` is a flag. `docs/unreal_export.md`, "From AT1".
- **Exposure:** the night looks' `reference_ev100` is matched to the plan's street levels
  (neon rain 1.5, clear night 1.0; AT0's 3 went with its 52 lx streets), so the runtime's
  $2^{-3 - EV_{ref}}$ scale shows the streets as AT0's did until AT3 moves the exposure.
- **Lit faces' stand-ins** (sign, shop sign and shopfront spill lights) cast no specular
  highlight (`Light.specular` 0, packed flag bit 5): glossy surfaces reflect the face itself;
  the rule holds for AT2's sign lights. **Every import** makes the game DPI-aware
  (`unreal.set_project_ini`: `bAllowHighDPIInGameMode=True`), so it runs at the monitor's
  resolution (2560 x 1440 on the PC's 125%-scaled screen, 2048 x 1152 before).
- **Reaches** are what each light needs (cobra 30 m, highway 45, post top 18 and never
  shadowed, wall pack 18, shop spill 12): a live light's shading cost is the screen its reach
  covers (AT1's first reaches cost Delta's night 2 ms).
- **Benchmark:** the game is opted out of Windows' power throttling and run above normal
  priority (`bench.unthrottle`; a window that lost the foreground ran on the 12700K's
  efficiency cores, its threads twice as slow), each sample records the foreground (`front`).
- Results (Delta's night 16.4 ms p95 over the route with everything on, 14.4 with AT1's lights
  alone), the check's night views: `docs/progress/AT1/README.md`.
- **Packaged games** (a fix after AT1; `docs/unreal_export.md`, "A packaged game"): every
  import lists the folders the runtimes load assets from by path (`unreal.ALWAYS_COOK`:
  `/Game/CityGen/Core/Atmos`, `/Engine/BasicShapes`) as `+DirectoriesToAlwaysCook` in the
  project's DefaultGame.ini, so a cook takes them (keep anything loaded by path in one of
  them); the play module opens a game with no saved resolution windowed fullscreen at the
  monitor's native resolution; the Tab menu has Fog, Rain, Wet streets and hour rows driving
  the atmos controller (found by class name, no link between the plugins).

AT2 to AT6 are in place (neon and signs as light, sky and time, air, weather, looks; the
visible lights after AT4: a walker's live set the lights it sees within 1,200 m through the
plan's sight raster); each milestone's record is in `docs/atmosgen_milestones.md` and
`docs/unreal_export.md` ("From AT2" to "From AT6", "Visible lights").

AT7 (far city and release) is in place, which completes stage 3:
- **Far cards** (`atmosgen/far.py`, the plan's `far`, `far/<tile>.json`, `presets.FAR`): past
  the live set every light the far view sees as cards by photometric class: a glow at its lens
  turned to the eye (aviation lights blinking), a pool on the surface a light aimed down
  lights (the lux check's walkway and lane points under it, else the ground), a wash on the
  facade a flood lights; signs, neon and windows need none (the instanced HLODs keep their
  emissive, AG16), the cloud glow is AT3's. The far check (`checks.far`: every street lamp
  with its pool or a reason, every aviation light with its glow, 3,000 cards a tile);
  `preview_far.png`.
- **Budgets across cities:** `atmosgen budgets PLAN... --out DIR` (`atmosgen/budgets.py`:
  plan time, checks, tiers, the most per tile against each budget, the most near the view
  against the live caps). Every sample and demo plans with every check passing
  (`docs/progress/AT7/plans/budgets.md`). AT4's mist stands on M13's water level on a
  terrain city (`air._surface_of`: M16 leaves `surface_m` unset there).
- **Exporter and runtime:** packing version 5 (a cell's far cards), `ATMOS_VERSION` atmos7,
  the controller's `bFar`, `FarGain`, `FarPx`, `FarFade`; the cards instanced per 1 km block
  in `M_CgFarGlow` and `M_CgFarFlat` (atmos assets 19), fading in where each tier's live
  lights fade out (`MPC_CityGenAtmos`'s `FarMidM`, `FarHighM`, `FarFixM`), collapsed to a
  point where they do not show; they replace the play features' light pools; console
  `CityGenAtmos.Far`, `.FarGain`; the check's `*_nofar` views, the benchmark's
  `night_plan_nofar`. `docs/unreal_export.md`, "From AT7".
- Delta's night after AT7: 15.0 ms p95 on the lean route. Results: `docs/progress/AT7/`. A smoke or test
  launch of a package leaves no `Saved/` folder in it (`-userdir=` outside the package, or
  delete it after the run): a saved resolution there stops the native start for the player.

AT2 (neon and signs as light) is in place:
- **Lit faces** (`plan.signs`): billboards, banners and holo-boards as rect lights the size
  of their face, stood off it (`out_m` 0.65 m past the 0.3 m frame: the light's plane in front
  of everything stage 2 hangs on a facade, 0.91 m), a share of the face's luminance as light
  (`light`) times its page cell's brightness (`emitters.SignColors.emit`: mean luminance
  over `SIGN_LUMA_REF`), in its page's color scaled to full; a holo-board in front of a
  facade lights only away from it. The faces check (`lux.face_check`, the plan's
  `checks.faces`): each lit face's light on its own wall and what stands out of it at most
  `FACE_WALL_MAX_LX` (the exporter leaves a failing plan out), and what it throws on the
  facade opposite reported.
- **Neon spill:** neon bands and facade shop signs a small colored spot stood off the sign,
  aimed out and down (`neon_spill`, `shop_neon`), a blade sign a point at its middle
  (`blade_neon`), near tier only; no specular for any sign light (AT1's rule).
- **Buildings** (`floods`, `aviation`, `searchlights`, with `Shape`, `sides`, `corners`):
  crown floods below a tower's crown (4 m off the facade or on the setback under it, aimed up
  into it, cone, intensity and reach from the geometry) on every landmark, every tower AG15
  gave crown LEDs (in their accent, read from assetgen's manifest: `City.ag15`) and a share
  of the others by the mood (`floods`), never a vacant one; uplights on landmarks and some
  towers; aviation lights on anything 60 m tall (40 m in a spaceport's district), red,
  flashing at the top (a mast's tip, else the roof's corners) all of a building together,
  steady every 90 m under it; searchlights on landmarks (by kind) and the mood's number on a
  district's tallest towers, two to a roof, sweeping.
- **Megasites** (`megasites`): a freight terminal's yard under 30 m high masts every 90 m,
  its cranes' boom floods; a spaceport's apron with high masts along its long sides and blue
  edge lights, its pads' rims green and white, each pad flooded from its launch tower.
- **Moods** (`spec.mood`, `presets.PALETTES`, `FLOODS`): a palette per archetype (the city's
  in the spec for districts without their own), floods' white and share, searchlights;
  grit mixes a gritty district's lamp temperatures and dims some (`MIX_*`); flicker and
  broken by kind (`FLICKER_BY_KIND`, neon most), a broken sign flickers deep instead of going
  dark (its face stays lit), safety lights never fail.
- **Tiers:** a `high` tier (floods, searchlights, high masts) of its own, 48 within 750 m.
- **Exporter and runtime** (`docs/unreal_export.md`, "From AT2"): packing version 2 (19
  floats: a blink's or sweep's period, amount and phase; flags: bit 6 high, bits 28-29 the
  animation), `ATMOS_VERSION` atmos2; the controller's high pool (`MaxHigh`, `HighRangeM`,
  `CityGenAtmos.High`), blinks and sweeps from the world's time, the fixtures' stand-ins
  (`M_CgBeacon` red glows per aviation light, `M_CgBeam` cones per searchlight;
  `CityGenAtmos.Fixtures`), atmos assets version 3.
- **The emitter asks** (`emitters.py`): the second ask read where met (a slot record with
  its `face`, a cell's `emit`; `Light.source` assetgen), a fourth for AT2's fixtures (`roof`,
  `beacon`, `mast`, `ground` mounts).
Results: `docs/progress/AT2/`.

AT3 (sky and time) is in place:
- **The plan's sky** (`atmosgen/sky.py`, `planmodel.Sky`, spec `sky`: latitude, day of the
  year, moon phase, day hour, the look's moon, stars and cloud deck overridden): the sun's
  and the moon's places by the hour (solar time; the moon trails the sun by its phase),
  curves over the sun's elevation (`presets.SUN_CURVE`: the exposure from the night's held
  -3 EV100 to the day's `DAY_EV100`, darker under a closed deck, MPC_CityGen's Night, the
  sun's light, the sky light, the stars), the named hours (day, dusk where the sun stands at
  -3 degrees, night), a row per hour; `dusk_dawn` and `tunnel` schedules set by the sun
  (`sky.schedules`; the lux check reads the plan's schedules).
- **The sky glow** (`sky.glow`): every light's upward flux (direct, and bounced off the
  ground, each the share that leaves the street canyons, `ESCAPE`) on a 64 m raster, lit
  onto the cloud deck's underside by a Lambertian footprint, CLOUD_ALBEDO E / pi times the
  look's `cloud_glow`; `BUILD/atmos/sky_glow.png` (square-root encoded linear RGB, row 0 the
  north) and the plan's `sky.glow` (bounds, `max_nits`, peak, mean); Delta's core glows at
  0.6 cd/m2, 0.12 over the city. `atmosgen lux` adds `preview_sky.png`.
- **Exporter and runtime** (`docs/unreal_export.md`, "From AT3"): the controller's sky
  settings (`unreal_atmos.sky_settings`) and the glow as a texture per city
  (`Atmos/T_<City>_SkyGlow`), `ATMOS_VERSION` atmos3; `ACityGenAtmos::ApplyTime` drives the
  importer's sun (the sun, then the moon), sky light, the exposure (held per hour), Night and
  Hour, every light's schedule interpolated between the hours; a sky dome (`M_CgSky`, atmos
  assets version 8: the sky atmosphere, the sun's disk, stars, the moon with its phase, the
  cloud deck at its height lit by the sun or moon and by the city's glow); `TimeSpeed`;
  console `CityGenAtmos.Hour day|dusk|night`, `.Sky`, `.Exposure`, `.TimeSpeed`, `.Cover`.
- **Play features:** `SetNight` sets the controller's day or night hour, the Tab menu's time
  row a slider (`SetTimeOfDay`, `ClickMenuRow("hour=H")`); their own night switch serves only
  a level without atmosgen's controller.
- **Benchmark and check:** passes `dusk_plan(_all)`, `day_plan(_all)`, `night_plan_nosky`;
  the check reads the sky by night, dusk and day and renders `dusk_*` and `t<HHMM>_*` views.
- **Blender:** `atmosgen preview --hour H` at a twilight hour renders a dusk sky
  (`ag6_preview.dusk_world`), the windows at the plan's Night, the lights dimmed by the
  exposure's step.
- **Benchmark harness:** `bench.busy` counts a game or a screen recorder (`GAMES`: javaw,
  ow-obs, obs); each sample names the process holding the foreground when the game does not
  (`front_owner`, `lost_to`) and the driver takes it back every 2 s (`take_front`, `retaken`).
Results (Delta's night 14.4 ms p95, dusk 14.3, day 11.1; with AT0's prototypes 16.4, 16.8
walking): `docs/progress/AT3/`.

AT4 (air) is in place:
- **The plan's air** (`atmosgen/air.py`, `planmodel.Air`, `FogVolume`, `Emitter`;
  `presets.AIR_LOOK`, `SCATTER`, `VOLUMES`, `EMITTERS`, `AIR_SCHEDULES`, `AIR_CVARS`): the
  height fog of the look and weather (`density`, `extinction`, `falloff` per look: neon rain's
  haze keeps to the street canyons), thicker by night (`fog_hours` from the sky's Night), its
  volumetric fog to `view_m`; light shafts as each light kind's volumetric scattering (street
  lights, high masts, floods; none from the neon spill, shop signs and shopfronts; none from
  searchlights, which keep AT2's beam meshes, brighter in fog); volumes (ellipsoids: mist along
  canals, basins and rivers after dusk, smog over industrial and spaceport districts and their
  megasites, haze under decks and in road tunnels, each times its district's haze and danger,
  with a `glow` of the city's light); emitters (steam from AG7's manholes and drains read from
  the street packs, `air.street_details`, road pieces only; M9's vents; exhaust from M3's roof
  mechanical units; cooking from M6's stalls and kiosks; smoke from chimneys on industrial
  roofs and stove pipes on shanty stacks, the fifth emitter ask), the share that steams by grit;
  the air check (`checks.air`: emitters on their sources and out of the masses, volumes over
  their water, district or deck, budgets per tile), a plan failing it not delivered;
  `atmosgen lux` adds `preview_air.png`.
- **Exporter and runtime** (`docs/unreal_export.md`, "From AT4"): packing version 3 (a cell's
  volumes and emitters, `pack_volume`, `pack_emitter`; cells wherever any lie),
  `unreal_atmos.air_settings`, `ATMOS_VERSION` atmos4; the controller's air (`bAir`, fog by
  the hour, `KindScatter`, a pool of local fog volumes, the nearest 24, with a glow by night;
  per cell an instanced component of plume cards in `M_CgSteam`, atmos assets version 12;
  `TunedSettings` applied while it runs); console `.Air`, `.Tuned`, `.VolumeGain`,
  `.VolumeGlow`, `.SteamGain`, `.FogSet`, `.FogView`, `.PlumeDebug`; the check's `*_noair`
  views and `$CITYGEN_UE_ATMOS_CMDS`; bench passes `night_plan_air`, `dusk_plan_air`,
  `day_plan_air`, `night_plan_proto`, the exploring `x_*` (`bench.TUNABLE`). Parked cars: cull
  distances by part, wheels without shadows (`VEHICLE_CULL_M`, `VEHICLE_ACTOR_VERSION` 3).
Results: `docs/progress/AT4/`.

The visible lights are in place (an atmosgen runtime change after AT4, Swagnik's walk of the
packaged Delta, 2026-11-12; `docs/unreal_export.md`, "Visible lights"):
- **On foot, the lights the walker sees:** round the play features' `CityGenWalker` (by its
  class's name; console variable `CityGenAtmos.Sight` -1 by the pawn, 0 the circle, 1 by
  sight) the live set is every light within `SightRangeM` (1,200 m, the plan's
  `tiers.sight_m`, four times the mid tier's) seen from the camera, at the light or where its
  light lands (a spot's pool, a face's patch, the floor under a point): the street's
  `SightMax` (512) by distance over reach, the high tier's `MaxHigh` by distance, shadows for
  the nearest seen within 60 m; near lights out of sight leave it. The fly pawn and the free
  camera keep AT1's circle. Every light fades in and out over `FadeS` (0.5 s) as it joins and
  leaves the set, in both modes.
- **The sight raster** (`atmosgen/sight.py`, the plan's `sight`, `sight.png`): the lux check's
  occluders (`lux.Occluders`) on 2 m cells, each blocking what all four of its 1 m cells block,
  every rounding toward seeing (red top, green bottom over the ground, blue ground; row 0 the
  north). The exporter puts it on the controller as runs (`unreal_atmos.sight_settings`,
  `SightRuns` and the raster's bounds, cell, steps, skips), `ATMOS_VERSION` `atmos5`.
- **The sweep** (`FCityGenSight::Visible`, `LaunchSight`, `TakeSight`): every 0.2 s on a
  worker thread (`Async` on the thread pool) a cell walk through the raster per light; a light
  stays seen `SightHoldS` (0.6 s) after the last sweep that saw it. Chosen over line traces
  (no collision past World Partition's loading range, and a trace per light per sweep on the
  game thread) and the engine's occlusion queries (a light has no primitive to query, a sign's
  face is its building's mesh, and a query answers only for what is on screen and loaded).
- **Cells always loaded** (their lights reach past the 768 m loading range); a cell's beacons,
  beams and plumes are made only within `FixtureRangeM` (832 m) of the view.
- **Benchmark and check:** each bench segment sets the mode (`bench.SIGHT`: by sight on the
  walks and the drive, the circle in the flights; the segment's `commands`); the check's
  `*_sight` and `*_circle` views.
- **Player start** (`unreal.player_start`, `_start_spot`): the fast-travel point nearest the
  middle moved to the nearest open (nothing raised within 10 m), lit (a street or wall light
  within 20 m) sidewalk point, facing along it toward the middle.
Results: `docs/progress/atmos_visible_lights/`.

AT5 (weather) is in place:
- **The plan's weather** (`atmosgen/weather.py`, `planmodel.Weather`, `Mask`, `Drip`,
  `TileDrips`; `presets.WEATHER_LOOK`, `WEATHER_TIMES`, `WIND`, `MASK`, `SURFACE_GLOSS`,
  `PUDDLE`, `DRIPS`, `WEATHER_LIVE`; the spec's `wind_deg`): the rain shadow of every cover
  within `cover_max_m` (25 m) of the ground (M14's slabs, M3's masses where they hang over no
  mass of their own building that reaches up to them, skybridges, M6's awnings and bus
  shelters, canopies, transit decks and cap beams, the raised roads as `sight.road_decks` takes
  them, road tunnels' lids), each moved downwind by its height times the rain's `lean` (at most
  3 m); masks per 256 m tile (`masks/<tile>.png`, 0.5 m, RGBA: red the cover's underside in
  the plan's `cover` datum and steps, green the puddles, blue the drip band past the low covers'
  dripping edges, alpha the gloss when wet by surface: the pavement map's faces, M16's ground
  cover, roofs, raised decks, water none); puddles where a value noise, the gutter along the
  curb, a road's sags and AG7's drains (read from the street packs, `City._street_details`)
  pass a threshold lowered by the district's grit (decision 12.5), never under a cover, on a
  roof, curb, deck or the water; drip lines in 8 m pieces (`drips/<tile>.json`: awnings' street
  edges, deck slabs, raised roads' sides, canopies, bus shelters); the five states with their
  rain, streaks, puddles, wetness, clouds, fog (the look's), fog volumes' gain, wind and gusts,
  the rain's age (`transition_s`, `wet_s`, `dry_s`, `fill_s`, `drain_s`); the plan's
  `weather_plan` and `masks`; the weather check (`checks.weather`: every tile's mask, every low
  cover in its shadow, no puddle under a cover, in a building or on the water, the drips'
  budget), a plan failing it not delivered; `atmosgen lux` adds `preview_weather.png` and
  `preview_weather_detail.png`.
- **Exporter and runtime** (`docs/unreal_export.md`, "From AT5"): packing version 4 (a cell's
  drip lines, `pack_drip`), `unreal_atmos.weather_settings`, the masks stitched city-wide at
  1 m (`wet_textures`: `atmos_wet_cover.png` grey, `atmos_wet_surface.png` RGB; imported as
  `T_<City>_WetCover`, `_WetSurface`), `ATMOS_VERSION` atmos6; the controller's states blended
  over `TransitionS`, the rain's age (`WetNow`, `PuddleNow`), the wind with gusts into
  `MPC_CityGenAtmos` (`Rain`, `Wetness`, `Puddles`, `WindMS`, `WindX`, `WindY`, `Streak`,
  `Drops`) and `MPC_CityGen`'s `Wind`, the fog, clouds (and the sun under them by day) and fog
  volumes by state; wet streets as two DBuffer decals (`M_CgWetColor` darkens, `M_CgWetGloss`
  roughness and normal, puddles with rain rings), the rain cut under the covers and leaning in
  the wind, splashes where traces from the sky land, drips along the drip lines, rain rings on
  `M_CgWater` (its tag `.rain2`; masters rebuilt from nothing, `clear_material`), the trees' sway built but off (`LEAF_SWAY`: 4.5 ms on a tree-lined street); atmos
  assets version 15; console `.Weather NAME [now]`, `.WeatherSpeed`, `.Wetness`; the Tab
  menu's Weather row (`weather+`, `weather-`, `weather=NAME`); the check's `*__<state>` and
  `*__<a>2<b>_<n>s` views; bench passes `night_plan_drizzle`, `_clear`, `_fogstate`, `_smog`,
  every atmos pass setting its state at once.
Results: `docs/progress/AT5/`.

AT6 (looks and art direction) is in place:
- **The look** (`atmosgen/look.py`, `planmodel.Post`; `presets.POST`, `POST_KEYS`,
  `DISTRICT_TINT`, `DISTRICT_POST`, `POST_EXPOSURE`, `DAY_EV100`, `OVERCAST_TAKE`, `SKY_SHARE`,
  `POST_CELL_M`, `POST_BLEND_M`, `POST_EASE_S`; the spec's `post` and districts' `shadows`,
  `highlights`, `tint`): per look a post set by night and one by day (bloom, lens flares and
  their threshold, film grain, chromatic aberration and its start, vignette, sharpening, the
  grade's saturation and contrast, shadow and highlight tints as gains over the mean of their
  linear rgb, `tint_gain`, the highlights' saturation, a black lift, local exposure's shadow
  and highlight contrast); neon rain teal in the shadows, magenta in the highlights; each
  district's sets the look's pulled by its grit (`mul`, `add`: clean is crisp, gritty grainy,
  fringed, flared, with lifted blacks and muted color but for the neon) and tinted by its
  archetype; the district raster (`post_districts.png`, 32 m, water and the edge the nearest
  district's); the exposure (the day's a clear day's, `DAY_EV100`, plus `day_bias`; by day
  moved by `overcast_comp` of the light the weather's clouds take, `overcast_shift`); `grade`
  (Unreal's ColorCorrectAll in numpy) for `preview_post.png` (`atmosgen lux`). The plumes:
  `STEAM_GLOW`, `STEAM_FAR` (the air's `steam_glow`, `steam_far`); a stall's cooking 6 cards.
- **Review and skill:** `atmosgen review BUILD [--plan] [--spec] [--prev] [--shots]
  [--prev-shots]` (`atmosgen/review.py`: `review.md`, `review.json`, `review_shots.jpg` in the
  plan's folder; checks, numbers, every shot's exposure in stops from middle grey, `LEVERS`),
  `atmosgen spec diff A B`; the skill is `atmosgen/skill/SKILL.md` (sessions cannot write
  `.claude/`: Swagnik copies it into `.claude/skills/atmosgen/`).
- **Exporter and runtime** (`docs/unreal_export.md`, "From AT6"): `unreal_atmos.post_settings`
  (`POST_FLOATS`, 20 a set; the raster as runs; the day's exposure replacing the sky's), the
  manifest's `atmos.post`, no new `ATMOS_VERSION`; the controller's `UpdatePost` (the raster
  sampled on a 5 x 5 grid over 90 m round the view, eased over 1.5 s, night and day by Night)
  into its own post-process volume (one volume, not one per district: AG16's game-thread cost
  of many), `OvercastShift`; `M_CgSteam` lit by night and kept opaque far off, the wet decals'
  normal from fine derivatives (AT5's curb sawtooth), atmos assets version 17; console
  `.Post`, `.PostDistricts`, `.PostSet KEY [VALUE]`, `.DayEV`, `.SteamGlow`; the check's
  `*_nopost` views and `post_views`; bench `Post 1` in every atmos pass, `ATMOS_OFF` `Post 0`,
  `night_plan_nopost`, `day_plan_nopost`; `unreal.ALWAYS_COOK` adds the engine's film grains.
Results: `docs/progress/AT6/`.

## Life generator (lifegen)

`docs/lifegen_scope.md` (draft v0, its decisions in section 12 still open) is the plan for
stage 4: a deterministic plan per city (population by district and hour, trips, fleet,
signal phases, timetables, air and boat lanes, place slots) keyed by M10's ids and
checked; a library of people (bodies, garments from sewing patterns draped in Blender,
generated textiles, accessories and cyberware, animation, crowd stand-ins) and vehicles,
built once per project; layer 4 of the manifest; a C++ runtime plugin, `CityGenLife`, that
simulates it on Unreal's Mass, ZoneGraph, Smart Objects and StateTree. Nothing third-party
goes in the repo unless its license lets anyone use it. Milestones LG0 to LG8, after AG16;
only LG8 waits for atmosgen's hour and weather.

## Gallery site (GitHub Pages)

`site/` is the public gallery at https://gotwic.github.io/CyberGen/ (served at
swagnik.org/CyberGen/). Two pages: the landing page, a showcase (`index.html`): a curated
few pictures, each with a title of its own, a one-line caption and a Stage 1 or Stage 2
label (no dates), day and night pairs (Vesper Bay, Delta's core) behind a slider; and the
build log (`log.html`, a tab): a timeline of pictures from `docs/progress/`, grouped by stage. `site/gallery.json`
holds the log's entries (`id`, `date` the first commit of the step's first picture, `git log
--follow --diff-filter=A --format=%as -- <path> | tail -1`, kept when a picture is rendered
again (new renders go in `docs/progress/gallery_refresh/`), `stage` 1, 2 or `ue`, `milestone`,
`milestone_name`, `title`, `image` a repo path, `caption` a one-liner where possible, not
necessarily a full sentence, saying only what is needed to explain the picture: no extra
detail, no hashes, goldens, check counts or test talk) and the showcase's `items`
(`entry`, or `entries` and `labels` for a pair, by log id, `title`, `caption`, `wide` for
the full width, `crop` [left, top, right, bottom] fractions to show a cut of the entry's
image). The showcase names no city, district or line, in its text or its pictures (a preview's
title band and legend cropped off; a new viewer has no context for the names); the log keeps
them. `site/index.html` and `site/log.html` are the templates `site/build.py`
fills in, beside `style.css` (the Neon Terminal look with glass panels, dark only) and
`app.js`. `.github/workflows/pages.yml` runs on changes to `site/` only:
it checks out `site/` and the listed images, resizes them (`build.py`: 2000 px and 640 px
JPEGs) and deploys; resized images are never committed. Preview with `.venv/bin/python
site/build.py --out <folder outside the repo>`. Add or change entries only when Swagnik asks:
no refresh on every push or milestone.

**Usage panel** (top of the showcase): `site/usage.py` (stdlib only) reads this machine's
Claude Code session logs (`~/.claude/projects`), keeps the sessions that ran in this repo
(worktree sessions, their subagents and an earlier location of the repo included), merges
their API responses into the device's ledger (`site/usage/ledger/<device>/<YYYY-MM>.csv`: one
row per response, hashed ids, time, model, token counts and `lines`, how many log lines carry
it, nothing of the conversation; rows are never removed, so logs Claude Code deletes still
count) and writes `site/usage/<device>.json` from the whole ledger (`mac` or `windows` by
platform: tokens by model and type, sessions, a per-day series, the time it ran) in two counts.
**Stats** (`stats`), what Claude Code's own `/usage` stats show: every log line, and Claude
Code logs a response once per content block with the whole response's usage on each line, so
about twice the billed count. **Billed** (`totals`, `models`, `days`): each request once, as
Anthropic bills it. `build.py` adds the device files up and shows both: "Claude stats tokens",
"Billable tokens" and "API cost" (the billable tokens at API prices, `PRICES`) at the top, the
chart a column a day in the stats count, both counts and the cost per model and type behind
"By model" and per device (with sessions, days and last update) behind "By device". A device file or ledger row from before the stats count counts once per
request in it until that device's next run fills in its line counts (said in the panel). Each
machine writes only its own file.
**After every PR is closed (merged or not), on every machine:** the session that closed it
(or merged it) runs `python site/usage.py` on its own machine (`.venv/bin/python` on the Mac,
`.venv\Scripts\python` on Windows), commits only `site/usage/<device>.json` and its ledger folder to main
("Usage: <device> after #N"), pulling first, and pushes. This is the one exception to "no
refresh on every push": it needs no ask. Never write another device's file; a usage commit
needs no further usage update. `site/usage/cloud.json` is entered by hand (`manual`, a
`cost_usd` with no tokens or sessions: the cloud sessions' credit spent, whose logs stay on
Anthropic's servers); `usage.py` never writes it, and it changes only when Swagnik asks.

## Working preferences

- Execute tasks end to end and ask for the access you need, rather than handing back scripts to run.
- No em dashes in any output.
- No backup copies before edits (the folder is under git).
- Write math as rendered LaTeX.
- Summary/deck bullets: noun-phrase topics rather than verb-led phrasing.
