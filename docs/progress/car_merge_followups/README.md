# The car merge's follow-ups (car_merge_followups)

car_merge (PR #248) drew each AG18 car of the moving traffic as one merged mesh, and left three
things: the merged mesh's glass and wheels drawn as far as its body (900 m), adding draw calls;
the parked cars still drawn a component per part per tile; and the lean benchmark route's
drive segment missing on Delta.

## What changed

- **Fewer sections far off** (`citygen/unreal_vehicles.py` `flat_of`, `merge_lod(..., flat)`,
  `MERGE_VERSION` 2; `citygen/ue/import_city.py` M_CgVehicle's `FLAT_VERSION` 1). Every
  section of every LOD of an instanced component is a draw in each pass (depth, base,
  velocity, every shadow view) of every view the component is in, and the traffic's components
  are the whole city's box (LG8), so the merged mesh's glass and wheels sections at every LOD
  were car_merge's added draws. Now the merged mesh's last LOD (the pack's LOD3, from about
  90 m) is one section, the body's: the glass, the wheels and the brakes are folded into it,
  the glass already from the pack's `opaque_from_lod` (LOD2, where it is dark and opaque
  anyway). Their vertices carry UV1 (gray, -1 - roughness) (glass 0.06 of its color as
  M_CgVehicleGlassDark draws it, roughness 0.05; wheels 0.03, 0.7), which M_CgVehicle draws
  flat (no paint, texture, flake, emission or clear coat); every other vertex's UV1 height is
  0 or more and is drawn as before. A primitive with no material takes its part's (three
  packs' LOD3 bodies had a few such triangles, a section of their own). Sections per model,
  LOD0 to 3: 3+3+3+3 (4 with brakes) before, 3+3+2+1 now.
- **Parked cars from the merged mesh** (`Importer.parked_parts`, `still_wheels`,
  `VEHICLE_ACTOR_VERSION` 4, `MERGED_VERSION` 2): a placement's cars of one model are one
  instanced component of `SM_<car>_merged`, which now carries the body's convex hulls (it
  collides as the body part did), culled at the body's 450 m; its rolling wheels' slot takes
  the plain `MI_<car>_wheels` (no world position offset: they stand still). A model one of
  whose cars steers keeps its parts (Delta's parked cars steer none). `check_vehicles` and
  AG16's scene count (`assetgen/scene.py`) know the merged component.
- **The lean route's drive** (`citygen/bench.py` `_drive`): the lane point nearest Delta's
  middle is its lane's last, so the drive began with one point, had no heading and ended
  there; the route had no drive segment. It now starts from the point before it.
- Tried first and dropped: two more LODs past the pack's, without the wheels from 150 m and
  without the glass from 300 m (the parts' old cull distances). They added draws (three
  sections a model in every pass) and saved almost no GPU time: traffic's draws at the fixed
  views went from car_merge's 1,277 / 1,955 / 1,125 to 1,580 / 2,746 / 1,450.

## Components and sections

| | car_merge | now |
|---|---|---|
| parked car components (Delta, 61 tiles, 3,557 cars) | 4,288 | 661 |
| traffic components (15 models) | 15 | 15 |
| sections a model, LOD0 to LOD3 | 12 to 16 | 9 to 12 |

## At car_merge's fixed views

Delta, night, native 2560 x 1440, car_merge's three held views over a corporate core avenue
(`night_plan_all` and `night_traffic_off`), medians. Another session's builds and tests took
2 to 4 cores throughout (car_merge's under 0.3), so the game thread's numbers are not
comparable; draws and GPU are.

| view | draws with traffic: before the merge | car_merge | now | traffic's draws: before | car_merge | now |
|---|---|---|---|---|---|---|
| street | 3,944 | 4,345 | 3,817 | 897 | 1,277 | 939 |
| drive | 4,374 | 5,226 | 4,457 | 1,115 | 1,955 | 1,140 |
| high | 3,544 | 3,818 | 3,410 | 840 | 1,125 | 807 |

Traffic's draws are back to what the parts drew before the merge. The GPU's median with
traffic: street 14.02 / 14.19 / 14.35 ms (before / car_merge / now), drive 13.94 / 14.17 /
14.12, high 10.78 / 10.81 / 10.76; traffic's share of it moves by 0.1 to 0.3 ms between runs
with the cars' places, within the views' noise. The high view stands inside a building on
this build (car_merge's note).

## Benchmark

One lean run (`--bench-route lean`, `night_plan_all`, native, no DLSS), now with its drive:
**18.1 ms** p95 over walk, drive and flight (walk 19.7, drive 18.2, fly 16.5; game p95 17.0),
against car_merge's 18.3 (walk 19.8, fly 17.0, no drive), under 3.2 cores of other load on
average. Draws (median) walk 3,483 to 3,207, fly 3,732 to 3,253. Parked cars have no pass of
their own; they are in every pass.

## Checks

Delta imported over CityAG16 (merged meshes made again, M_CgVehicle rebuilt, the 61 parked car
actors updated, their 61 HLOD cells built again); `--check` passes (spawn, streaming,
collision, walk, curb, console, sky, air, weather, look, far city, play features, fly). The
unit tests of the changed files pass (`tests/test_unreal_vehicles.py`, `tests/test_bench.py`,
`tests/assetgen/test_ag_vehicles.py`); `tests/test_unreal.py` has two failures in code this
change does not touch (`test_terrain_city`'s graph heights, `test_stage2_from_assetgen`'s
texture library files).

Packaged as `builds/packaged/Delta_carfix` (`package_carfix.cmd`), smoke launched with its
user folder outside the package (`smoke_carfix.ps1`): the map loads, life and traffic start.

## Shots

Night, Old Town: traffic and parked cars along the street (`night_street_cars.jpg`); the lean
route's drive along a raised road, a van far ahead (`night_lean_drive.jpg`).

## Left

- The GPU's traffic share at the fixed views is not measured apart from the run's noise; a
  quiet machine would tell whether the rolling wheels' material (car_merge) costs anything.
