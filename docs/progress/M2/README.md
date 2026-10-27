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

The specs are unchanged (`docs/progress/M1a2/`, Vesper Bay in `cities/vesper_bay/`).

| City | Street / alley / service / pedestrian km | Footbridges | Junctions (signalized) | Crosswalks | Lanes / connectors | Walkway km | Blocks | Lots | Open space | Places |
|---|---|---|---|---|---|---|---|---|---|---|
| Vesper Bay | 94.6 / 24.4 / 12.3 / 9.9 | 7 | 1688 (345) | 1155 | 6174 / 12185 | 450 | 1030 | 5877 | 11.4% | 3 |
| Saltreach Free Port | 50.4 / 9.8 / 6.2 / 16.9 | 5 | 1006 (213) | 726 | 3171 / 6263 | 256 | 598 | 3282 | 13.6% | 2 |
| Delta Megacity | 86.8 / 21.1 / 7.4 / 16.4 | 11 | 1581 (365) | 1271 | 5538 / 11232 | 396 | 984 | 5454 | 11.0% | 4 |
| Nexus City | 98.1 / 20.9 / 5.8 / 20.3 | 12 | 1774 (423) | 1425 | 6380 / 12396 | 451 | 1058 | 6412 | 14.1% | 7 |
| Greyhook (peninsula) | 50.5 / 7.5 / 12.0 / 9.4 | 6 | 720 (143) | 453 | 2443 / 4598 | 236 | 410 | 2459 | 12.4% | 1 |

| City | Lots by archetype: median m2 (median frontage m) |
|---|---|
| Vesper Bay | corporate core 2636 (61); entertainment market 228 (16); industrial port 6215 (112); megablock residential 4996 (91); old town 163 (14); research campus 3874 (88); residential heights 803 (29); spaceport 14352 (106) |
| Saltreach Free Port | corporate core 2485 (58); industrial port 6274 (170); old town 164 (14); research campus 5131 (125); residential heights 761 (26) |
| Delta Megacity | corporate core 2679 (62); industrial port 7054 (131); midtown mixed 890 (30); old town 161 (14); research campus 4275 (78); transit hub 1420 (49) |
| Nexus City | corporate core 2730 (57); entertainment market 222 (16); industrial port 7757 (138); midtown mixed 869 (30); old town 162 (14); research campus 5732 (132); residential heights 791 (29); spaceport 8120 (99); transit hub 1440 (51) |
| Greyhook (peninsula) | entertainment market 228 (16); industrial port 8481 (152); megablock residential 5032 (97); residential heights 820 (28); spaceport 9626 (92); transit hub 1637 (45) |

Build times on the cloud container (4 CPUs, one city at a time, CLI with previews and
`--trace`): Nexus City 48 s, Delta Megacity 42 s, Vesper Bay 36 s, Saltreach Free Port 19 s,
Greyhook 17 s.

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
0.01 m grid and made valid again, overlays use fixed precision (`grid_size=0.01`), a union of
many pieces merges them in an order fixed by `geom.union` (see below), buffers are snapped
before any union, rings are normalized, and decisions compare exact measures
(`area1`, `length1`). Noding uses exact integer centimeter arithmetic. Lots are computed in
worker processes per district and per chunk of blocks; the output does not depend on the worker
count. `tests/test_streets.py` injects ULP noise into the inputs of the M2 stages and expects the
same model; every stage writes trace entries (`streets`, `junctions`, `lanes`, `blocks`,
`walkways`).

## Cross-machine check: the Mac failure and its fix

### What the Mac showed

At `48eaba0` the owner ran `pytest -q` on the M4 Mac (macOS arm64, Python 3.13, the pinned
requirements): 211 passed, 1 skipped, 1 failed. `test_golden_hashes` failed at
`delta_megacity`; Saltreach, compared first, matched, and the test stopped there. The run also
printed 3732 warnings from shapely `oriented_envelope`.

### Why the emulated ARM check missed it

The earlier check built the samples under emulated aarch64 Linux and got the x86 bytes. That
compares two Linux builds of numpy and GEOS (gcc, glibc, libstdc++), so it covers fused
multiply-adds and SIMD paths, but not what is different on macOS: clang, Apple's libm and
libc++. Fused multiply-adds inside GEOS were ruled out from its source: GEOS compiles with
`-ffp-contract=off` on every compiler.

### Finding the cause without a Mac

Each candidate was emulated on x86 and Delta Megacity rebuilt with `--trace`:

| Candidate | Emulated by | Delta model |
|---|---|---|
| numpy draws fused by clang ($\ell + (h - \ell)\,u$ as one rounding) | the draws computed with `math.fma` | unchanged |
| libm `pow` behind Python's `x ** 2` (glibc's differs from $x \cdot x$ in about 0.07% of cases) | `x * x` | unchanged |
| worker count (8 on the M4, 4 in the cloud) | `CITYGEN_WORKERS=8` | unchanged |
| C++ standard library (libc++ on macOS, libstdc++ on Linux) | GEOS 3.14.1 rebuilt with clang and libc++ (Ubuntu's source of the same release), swapped into the shapely 2.2.0 wheel | **different** |

With the libc++ GEOS the Mac's pattern came back: Saltreach and Greyhook identical, Delta
Megacity, Vesper Bay and Nexus City different. In each, every M1 stage, the streets, junctions,
lanes and the first district's blocks were identical, and the first different entry was the
blocks of the next district (`blocks/d02` in Delta and Vesper Bay, `blocks/d05` in Nexus).

Replaying that district's block job under both GEOS builds, with a hash of every shapely call,
gave the first call whose output differed for identical input:
`union_all(<553 right-of-way polygons>, grid_size=0.01)` in `geom.union`. GEOS merges the
pieces pairwise in the order of an STRtree it builds for them, and the tree sorts the pieces by
their envelopes with `std::sort`. That sort is not stable, and libc++ and libstdc++ leave tied
keys in different orders. Snap rounding is not associative, so another merge order gives
another union (here 0.17 m2 of slivers along nearly coincident curbs), so other blocks, and
from there other lots.

### The fix

- **`geom.union` in the M2 stages** sorts the pieces by the Z-order (Morton) code of their
  bounding box centers in integer grid units, ties by input position, and merges them
  pairwise, level by level, with binary snap-rounded unions (one vectorized call per level).
  A binary overlay has one result whatever order GEOS keeps internally, so the union no
  longer depends on the C++ library. Build times did not grow.
- **GEOS order in other decisions**, hardened although it did not change the five samples:
  STRtree pair queries are sorted before use (`streets._pairs`); the walkway island link
  takes the lowest of all equally near nodes (`query_nearest(all_matches=True)`) instead of
  the tree's pick; `blocks._fast_lines` and `geom.line_union` return normalized linework (the
  frontage axis of a lot split takes the first of equally long edges).
- **Robust anyway, kept:** M2 draws use `streets.uniform` (plain Python operations on
  `rng.random()`, the same bits as `rng.uniform` on x86, so the samples did not change), and
  float squares are `x * x` instead of `x ** 2` (libm `pow`).
- **Warnings:** `_obb` calls `minimum_rotated_rectangle` under
  `np.errstate(divide="ignore", invalid="ignore")`. x86 prints none of them. numpy checks the
  IEEE flags after the ufunc: GEOS's rotating calipers divide by zero and compare a NaN for a
  degenerate caliper (the result uses neither), and arm64 raises the flags where x86 does
  not. Confirmed on the M4 Mac: with only `invalid` silenced it still printed about 360
  "divide by zero encountered in oriented_envelope" warnings per five builds.
- **Tests:** `test_golden_hashes` builds every sample and names all that differ;
  `test_canonical_union_ignores_input_order` checks that permuted pieces give the same union
  bytes.

### Verification

All five samples were rebuilt from the final code three ways: x86_64 Linux (the golden
hashes; Python 3.13.17, 4 workers), x86_64 with the libc++ GEOS, and emulated aarch64 Linux
(qemu-user, conda-forge Python 3.13.17 for aarch64, the PyPI aarch64 wheels of numpy 2.5.4
and shapely 2.2.0 with GEOS 3.14.1, worker processes emulated too, 4 workers).

Every model and every stage trace is identical across the three (`citygen trace diff`: no
difference in any entry). Emulated build times were 7 to 18 minutes per city.

| City | Trace entries | x86_64 (libstdc++ GEOS) | x86_64, libc++ GEOS | emulated aarch64 | M4 Mac (macOS arm64) |
|---|---|---|---|---|---|
| Vesper Bay | 5897 | `f6a35536c06a9d17dfa754aedcca4477428169e881202f30e5c3dadde0a9006d` | same | same | same |
| Saltreach Free Port | 53 | `6b2701d4107a1b05f08676e6b9bcb00c369b1b60e4f0bfa25676dee7eaa90b23` | same | same | same |
| Delta Megacity | 2766 | `4bfce90b33071689b89ed332b360b15889ebcc5de73c757af3a0ae6ca3edafe8` | same | same | same |
| Nexus City | 8544 | `d2fe5ce9c22aa448e23e5a0e2bd0f9eb04553612a3df0fd8e1ef0107f16698b2` | same | same | same |
| Greyhook | 244 | `ef0fa87de02cfc3c76dd18cc709ff43c3527b8e3e368ffeaf7bfb1ad42600072` | same | same | same |

The M4 Mac column was run on the owner's machine (macOS arm64, Python 3.13, the pinned
wheels, 4 workers) against a local x86_64 reference (Docker `linux/amd64` under Rosetta,
`python:3.13-slim` plus `requirements.txt`, which reproduces the golden hashes): models and
stage traces identical, all 31 checks pass on both, and pytest passes on both.

Before the fix (`48eaba0`), the libc++ GEOS gave `d86b5839...` for Delta Megacity, `48597f0a...`
for Vesper Bay and `d9774745...` for Nexus City instead of the x86 models.

Not covered here: Apple's libm. No M2 decision calls libm directly (angles come from `dmath`,
squares are products), and GEOS uses it only for round buffer joins, whose vertices are
snapped, so a difference would have to land on a half-grid value. The Mac run above found no
such case.

### String hash order (fixed before the Mac run)

The first ARM pass found another source of drift. Junction classes of equal
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
  pedestrian bridge keep their own walkway graph (3 components in Vesper Bay).
- **Build time.** Nexus City, the slowest, takes 48 s of the 60 s budget with previews and
  `--trace` on the 4-CPU container; the trace hashes about 18,000 lanes recursively.

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
