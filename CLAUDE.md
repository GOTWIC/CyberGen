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
high-level milestone table). Stage 1's milestones are M0 to M15, built in
`docs/progress/M*`; later stages give their milestones a prefix of their own (set in their
scope doc) so their progress folders never clash with stage 1's.

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

**Validation (every stage, every PR; Swagnik's rule, 2026-10-27).** Before pushing a PR, make
sure the outputs look good and nothing breaks: build the cities the change touches, every check
passes, look at their previews and renders, and the test suite passes (recorded hashes
regenerated on this Mac where a change moves a model on purpose, saying why). Nothing more:
no x86, Docker, Windows or other cross-platform comparisons, no stage-trace diffs, no
`lock --verify` runs, no seed sweeps (unless the work is about robustness), no repeated
validation runs, and the coordinating session does not validate a PR again (it reviews the
outputs and the diff, and has the PR merge the latest main first when they overlap). Where a
scope's "done when" asks for Mac = x86, that part waits for the deferred determinism check in
`docs/determinism_check.md`, which runs only when Swagnik asks for it.

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
  (RTX 4070 Ti, 12 GB).
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
Samples: Nexus City's ring highway dips under Midtown in a cut-and-cover tunnel, Peninsula
City's spine crosses its river in an immersed tube (Vesper Bay keeps its trumpet: a tunnel on
its ring takes the flyover's stem). Sample builds: `docs/progress/M9/`.

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
  mean of the two. `RoadSegment.ground`, `RoadNode.ground_m`. The finished ground
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
so walls, bored tunnels and terrain viaduct columns are keyed by their ids. citygen makes no
network call; the
official Unreal MCP plugin (`Experimental/ModelContextProtocol`, an HTTP server in the
editor) is the interactive route for a Claude session. Testing is always in a throwaway
project of the exporter's own (`--new-project` makes one from the First Person template,
outside the repo); never import into any other project unasked. Spec and record:
`docs/unreal_export.md`. Sample imports: `docs/progress/M15/`.

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

`docs/assetgen_scope.md` is the spec for stage 2 (milestones AG0 to AG11, section 14), its log
`docs/assetgen_milestones.md`. Package `assetgen/` beside `citygen/`, which it imports read
only (`model`, `dmath`, `geom`); tests in `tests/assetgen/` (`test_ag_*.py`, helpers in
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

## Working preferences

- Execute tasks end to end and ask for the access you need, rather than handing back scripts to run.
- No em dashes in any output.
- No backup copies before edits (the folder is under git).
- Write math as rendered LaTeX.
- Summary/deck bullets: noun-phrase topics rather than verb-led phrasing.
