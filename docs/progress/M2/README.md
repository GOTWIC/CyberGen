# M2: local streets, junctions, sidewalks, blocks, lots, open space

M2 adds scope stages 5, 6 and 10 to `citygen build`. The build now lays local streets by
archetype on the M1b primary network, with alleys, service lanes, promenades and footbridges.
It then builds junction polygons with sidewalks, medians, signals and crosswalks, plus a lane
graph and a walkway graph. Last come blocks, lots with recorded frontage, and open space. The
model gains `crosswalks` and `sidewalks`. Junctions, lanes, walkways, blocks, lots, open spaces
and places are filled in.

There are 13 new checks, so 31 in all, and every sample passes every one. Each city folder holds
the following; `city_model.json` is not committed, because a build regenerates it byte for byte:
- `preview_map.png`: the whole map with blocks, lots, streets to scale, crosswalks and open space;
- `preview_detail.png`: four 400 m street-level insets;
- `report.json` and `report.txt`: the checks plus a stats table;
- `trace.json`: stage hashes.

The specs are unchanged (`docs/progress/M1a2/`, Nyxllor in `cities/nyxllor/`).

| City | Street / alley / service / pedestrian km | Footbridges | Junctions (signalized) | Crosswalks | Lanes / connectors | Walkway km | Blocks | Lots | Open space | Places |
|---|---|---|---|---|---|---|---|---|---|---|
| Nyxllor | 94.6 / 24.4 / 12.3 / 9.9 | 7 | 1688 (345) | 1155 | 6174 / 12185 | 450 | 1030 | 5881 | 11.4% | 3 |
| Saltreach Free Port | 50.4 / 9.8 / 6.2 / 16.9 | 5 | 1006 (213) | 726 | 3171 / 6263 | 257 | 599 | 3279 | 13.6% | 2 |
| Delta Megacity | 86.8 / 21.1 / 7.4 / 16.4 | 11 | 1580 (365) | 1271 | 5536 / 11232 | 396 | 984 | 5453 | 11.0% | 4 |
| Nexus City | 98.1 / 20.9 / 5.8 / 20.3 | 12 | 1774 (423) | 1425 | 6380 / 12396 | 451 | 1058 | 6404 | 14.1% | 7 |
| Greyhook (peninsula) | 50.5 / 7.5 / 12.0 / 9.4 | 6 | 720 (143) | 453 | 2443 / 4598 | 236 | 410 | 2459 | 12.4% | 1 |

| City | Lots by archetype: median m2 (median frontage m) |
|---|---|
| Nyxllor | corporate core 2636 (61); entertainment market 228 (16); industrial port 6215 (112); megablock residential 4996 (91); old town 162 (14); research campus 3874 (88); residential heights 804 (29); spaceport 14352 (106) |
| Saltreach Free Port | corporate core 2485 (58); industrial port 6274 (170); old town 164 (14); research campus 5131 (125); residential heights 761 (26) |
| Delta Megacity | corporate core 2679 (62); industrial port 7054 (131); midtown mixed 892 (30); old town 161 (14); research campus 4275 (78); transit hub 1420 (49) |
| Nexus City | corporate core 2730 (57); entertainment market 222 (16); industrial port 7757 (138); midtown mixed 869 (30); old town 162 (14); research campus 5732 (132); residential heights 791 (29); spaceport 8120 (99); transit hub 1440 (51) |
| Greyhook (peninsula) | entertainment market 228 (16); industrial port 8481 (152); megablock residential 5032 (97); residential heights 820 (28); spaceport 9626 (92); transit hub 1637 (45) |

Build times on the cloud container (4 CPUs, one city at a time):

| City | `build_city` | CLI with previews and `--trace` |
|---|---|---|
| Nexus City | 52 s | 59 s (54 s without the trace) |
| Delta Megacity | 46 s | 52 s |
| Nyxllor | 38 s | 46 s |
| Saltreach Free Port | 19 s | 23 s |
| Greyhook | 16 s | 21 s |

Lots are built in worker processes, by district and in chunks of 250 blocks.

## How the local streets are built (`citygen/streets.py`)

Each district gets a street pattern from its archetype, laid inside the land left after the M1b
primary roads (right of way plus a verge), the megasite reserves, water and open land:

| Archetype | Pattern |
|---|---|
| corporate_core | rotated grid at the district's `grid_angle_deg`, through alleys in 20% of large blocks |
| megablock_residential | superblocks with internal U-shaped service lanes |
| midtown_mixed | grid plus a ring street around the central park, perimeter blocks with courtyards |
| old_town, entertainment_market | organic network grown from the district edge (Parish and Mueller 2001) and steered by a cross field that turns parallel to the banks (Chen et al. 2008): dead ends, bent alleys, one-way block loops |
| industrial_port | large grid with long, rail-ready blocks along the main axis, quay roads, service lanes |
| residential_heights | curvilinear loops at lot depth with connectors and cul-de-sacs |
| research_campus | campus loop around a landscaped core, service drives |
| transit_hub | radial and ring streets around the station |
| spaceport | service roads around the reserve, joined to the M1b dead ends at its gates |

Every district gets a frame first: frontage streets beside highways (5 m verge), district
boundary streets, quay promenades and quay roads, reserve service rings. Then the pattern, then
infill streets and alleys where a block is still deeper than the archetype's lot depth allows
(perimeter blocks: $w = \max(2.3\,d, \ell_{max})$, otherwise $2.3\,d$, with $d$ the lot depth).
Footbridges cross canals and channels every 150 to 300 m along the water-following streets.

Every new street end is attached by one rule set (`Builder.attach`): no junction on a highway,
bridge or ramp, none within 30 m of a primary node, merges with a junction within 20 m, minimum
junction angle 60 degrees in grids and 35 in organic districts. Grid dead ends run straight on to
the next road (up to 150 m); port and spaceport stubs stay as yard spurs. Then the graph is noded
exactly (integer centimeter intersections with `Fraction`), cleaned (short stubs trimmed, sharp
approaches cut back, near-duplicate streets removed, islands joined or dropped) and written as
`road_nodes` and `road_segments` next to the primary network.

## Junctions, sidewalks and graphs (`citygen/junctions.py`)

- Junction polygons: each leg's cross-section gives curb lines; neighbor curbs meet in a fillet
  with the archetype's corner radius (old town 4 m to port 15 m, the smaller over the legs),
  cut back where legs are short; the union of the leg mouths and fillets is the junction.
- Signals by junction class: two major roads (avenue or highway) meeting, a major road crossed
  by a street (four vehicle legs), and four-way street crossings in the corporate core, midtown and transit hub;
  crosswalks on every approach of a signalized junction and on the side streets of unsignalized
  avenue junctions; none at highway-only junctions (interchanges in M7).
- Sidewalks from the scope 5.1 widths with a furniture zone and curb; medians on avenues.
- Lane graph: one record per travel lane (one-way flags from the segment), cubic Bezier
  connectors through each junction for every allowed turn, `adjacent_ids` for lane changes.
  Strong connectivity is checked with Tarjan's algorithm.
- Walkway graph: sidewalk chains between corner nodes, crosswalks and unmarked crossings,
  pedestrian streets, alleys, promenades, footbridges and paths into every park and plaza;
  walkway islands on a landmass join by a link up to 150 m or a path beside the roads.

## Blocks, lots, open space (`citygen/blocks.py`)

- Blocks: land minus the right of way of every road (the full graph), opened by 1 m to remove
  spikes, split by district.
- Lots: oriented bounding box splits (Vanegas et al. 2012): split across the longer axis of the
  OBB until a lot is within the archetype area, keeping frontage on every piece (cuts run across
  the frontage axis); perimeter blocks get strip lots around a courtyard; deep blocks get back
  gardens; small or frontage-less pieces merge into a neighbor (merged group id).
- Frontage: every lot records the road segments it faces (`frontage`: segment id, road class,
  length and the lot edge along the road, longest first; `frontage_ids`), its block, district and
  merged group.
- Open space: leftover blocks (too small, too narrow, odd shapes) become plazas, pocket parks and
  parks by size; archetype quotas take more blocks where the share is low; named places of the
  spec (markets, plazas, parks) take the best block near their anchor; quay promenades; every
  park and plaza joins the walkway graph.

## Checks added (scope section 9, M2 parts)

| Check | Rule |
|---|---|
| street_graph | every vehicle road in one network; pedestrian streets and footbridges joined to it |
| lane_graph | lane graph strongly connected; every vehicle road has lanes |
| walkway_graph | walkway graph connected on every landmass with districts |
| lot_frontage | every lot fronts a street, alley, service lane or pedestrian street (2 m+) and records frontage and district |
| lot_block_sizes | lot areas within 0.75 x min to 1.6 x max of the archetype; median block size within 0.5 x lo to 1.8 x hi |
| lot_slivers | no lot narrower than 3 m, no block narrower than 6 m |
| sidewalk_clear_path | clear path at least 1.8 m |
| crosswalks | every approach of every signalized junction; side streets of unsignalized avenue junctions |
| junction_placement | no local junction on a bridge or ramp |
| junction_angles | 60 degrees in grid districts, 35 in organic ones |
| street_duplicates | no local roads with right of way within 4 m over 50 m |
| open_space_share | open space share of net land within the archetype target |
| places_built | every named place built in its district |

## Determinism

The M2 stages run inside `geom.canonical()`: every GEOS result is rounded point by point to the
0.01 m grid and made valid again, overlays use fixed precision (`grid_size=0.01`), buffers are
snapped before any union, rings are normalized, and decisions compare exact measures
(`area1`, `length1`). Noding uses exact integer centimeter arithmetic. Lots are computed in
worker processes per district and per chunk of blocks; the output does not depend on the worker
count. `tests/test_streets.py` injects ULP noise into the inputs of the M2 stages and expects the
same model; every stage writes trace entries (`streets`, `junctions`, `lanes`, `blocks`,
`walkways`).

## Cross-machine check (ARM)

All five sample cities were rebuilt from the final code under emulated aarch64 Linux: qemu-user,
Python 3.13.7, and the same pinned numpy 2.5.4 and shapely 2.2.0 with GEOS 3.14.1, from the
aarch64 wheels on PyPI. The run used one worker process.

Every `city_model.json` is byte-identical to the x86_64 build (Python 3.13.17, 4 workers). So
is every stage trace: `citygen trace diff` reports no difference in 53 (Saltreach), 244
(Greyhook), 2766 (Delta), 5897 (Nyxllor) and 8544 (Nexus) entries.

| City | sha256 (both machines) |
|---|---|
| Nyxllor | `9930f72c750e3e41...` |
| Saltreach Free Port | `41227c37a60e0a8f...` |
| Delta Megacity | `48df64bb0a20f3c7...` |
| Nexus City | `498393da84634d0f...` |
| Greyhook | `84cfa61bda09be48...` |

Emulated build times were 25 min (Greyhook) to 113 min (Nexus).

During this pass a second source of drift turned up and was fixed. Junction classes of equal
rank (pedestrian, footbridge) came out of a Python set of strings, and string hashes change with
every process (`PYTHONHASHSEED`). The same machine could therefore write different bytes on two
runs. Classes are now sorted by rank, then name. `test_same_model_across_hash_seeds` builds
under two seeds, and all five samples were also rebuilt under two seeds with the same bytes.

## Still weak

- **Yard spurs.** Port and spaceport districts keep dead-end yard spurs. Extending them made
  slivers between reserves and quays.
- **Corporate core leftovers.** Rotated grids leave triangular blocks and short comb-like stubs
  where they meet curved district edges. The leftover triangles mostly become plazas.
- **Cut-backs.** The junction angle rule is enforced by cutting a road back, not by re-routing
  it: 29 to 82 local roads per city are shortened.
- **Dropped segments.** 3.5 to 8.5 km of local segments per city end up outside the network and are
  dropped. 9 to 65 lanes per city are reached only over pedestrian streets, so they become
  pedestrian.
- **Unconnected loops.** A few residential loops find no connector to the frame; the reports
  note them. The island pass joins each such loop within 40 m of a road; any loop still left
  out is among the dropped segments.
- **Big-block archetypes.** These districts come out with smaller blocks than the spec asks.
  Corporate core medians are 96 to 104 m against 120 to 200 m; megablock, port and spaceport
  medians are 10 to 40% under their ranges. Frontage streets, boundary streets and infill cut
  edge leftovers into small blocks, and the median counts those. `lot_block_sizes` allows
  0.5 x lo. Research Campus in Delta is over its range (226 m against 200 m) because campus
  grounds stay open.
- **Lot subdivision.** Only the OBB splitter is implemented, not the straight-skeleton strips
  (the second Vanegas method). Perimeter-block strips approximate it.
- **Primary-only junctions.** Junctions with no local leg are not angle-checked; sharp
  primary-on-primary angles and primary junctions inside ramp lengths are left to M7
  interchanges.
- **Footbridges and walkways.** Footbridges have stairs, not ramps. Landmasses with no
  pedestrian bridge keep their own walkway graph (3 components in Nyxllor).
- **Build time.** Nexus City is 6 s under the 60 s budget without the trace. `--trace` adds
  about 4 s on M2 data, because it hashes about 18,000 lanes recursively.

## What M3 needs from lots and frontage

- **Placement.** M3 uses the lot polygon and `frontage[0].line`, the longest road edge: the
  facade sits on it, and its direction sets the building's orientation. `frontage[*].road_class`
  sets the setback and podium rules: avenue frontage gets taller podiums, alleys get service
  entrances.
- **Complexes.** `merged_group_id` marks lots that become one complex (twin towers, clusters).
  `block_id` and `archetype` carry density presets.
- **Clear zones.** Sidewalk polygons and junction polygons stay clear. Open space with
  `open_space.*` types is not built on, and megasite reserves are left for M3's megasite
  builders.
- **Heights.** Lots carry no height or density yet. M3 takes them from the archetype and the
  frontage class.
