# Cars as one mesh (car_merge)

LG5 drew lifegen's moving traffic with one instanced component per AG18 car model and part (a
body, its glass, four to six wheels, brakes): 92 components on Delta. LG5 and LG8 found most of
the traffic's game-thread cost in the engine's handling of those moving components, not in
lifegen's own step, and LG8 left "car parts merged per model" as the next step. Each car model
is now one mesh, so the traffic draws one instanced component a model.

## What changed

- **Merged files** (`citygen/unreal_vehicles.py` `merge_cars`, `merge_lod`; called by
  `unreal.build_manifest`): per car and LOD, `BUILD/unreal/vehicles/<car>/lod<k>.glb`, every
  part's primitives moved to its pivot and grouped by the pack's material (body, glass,
  wheels), a rolling wheel's under its own material (`pack_wheels_roll`) with the middle it
  turns about in UV1. The car's own hash does not move, so the parked cars' meshes and actors
  are untouched.
- **Import** (`citygen/ue/import_city.py` `Importer.merged_car`): `SM_<car>_merged` with the
  pack's four LODs and screen sizes, the pack's material instances on its sections (the dark
  glass from `opaque_from_lod`), only the body's sections casting a shadow, no Nanite, no
  collision, no lightmap UVs. Made again only when its files, the masters or `MERGED_VERSION`
  change.
- **Rolling wheels** (`M_CgVehicleRoll`, `MI_<car>_wheels_roll`): the wheels' material with a
  world position offset that turns each wheel vertex about its middle by the car's travel over
  the wheel's radius (the instance's custom data 9, after the paint), its normal turned with
  it. Chosen over keeping wheels as separate components: one draw path for the whole car, and
  the wheels still read as rolling near the view. The runtime sends the travel only within
  `ROLL_M` (150 m, the old wheels' draw distance); past it the wheels stand still.
- **Exporter and runtime** (`unreal_life.traffic_cars`, `_hover_parts`, `PACK_VERSION` 12;
  `import_city.traffic_props` `car_part_roll`, `LIFE_VERSION` life14; `CarPartRoll` in
  `CityGenLifeActor`, `CityGenLifeTraffic.cpp`): a car with a merged mesh is one part drawn as
  far as a body (900 m); LG7's hover cars (no wheels) draw their merged mesh too. The status's
  `traffic.components` counts the components. Parked cars keep their parts (they are placed
  through stage 2's contribution, a different path).

## Components

| | before | after |
|---|---|---|
| traffic (15 models) | 92 | 15 |
| hover cars' painted meshes (3 models) | 6 | 3 |

## Traffic's cost at fixed views

Delta, night, native 2560 x 1440, the benchmark's game process held 20 s at three views over a
busy corporate core avenue (`night_plan_all` against `night_traffic_off`, same import before
and after the change; other load under 0.3 cores). Traffic's game-thread cost is the game
thread's median with traffic less without.

| view | game p50 with traffic, before | after | traffic's cost, before | after | draws added, before | after |
|---|---|---|---|---|---|---|
| street | 6.57 ms | 6.06 ms | 1.87 ms | 0.91 ms | 897 | 1,277 |
| drive | 5.86 ms | 5.84 ms | 1.18 ms | 0.97 ms | 1,115 | 1,955 |
| high | 7.02 ms | 6.06 ms | 1.83 ms | 0.13 ms | 840 | 1,125 |

The high view stands inside a building on this build (the shots there show only a wall), so
its numbers are noisy; the street and drive views look along the avenue with cars in front.
Draw calls rise: glass and wheels are now drawn out to the body's 900 m (they were culled at
300 and 150 m), each section a draw a LOD; the GPU's median moves by about 0.2 ms. The frame is
GPU bound at these views, so the frame median barely moves.

## Benchmark

One lean run (`--bench-route lean`, `night_plan_all`, native, no DLSS): **18.3 ms** p95
(walk 19.8, fly 17.0; game p95 17.6), against umbrella_hold's 18.8 (walk 20.1, fly 17.0). The
lean route on this build made no drive segment (0 frames), so no drive number.

## Shots

Night, lamps lit: cars passing a crosswalk (`night_cars_close.jpg`) and waiting at a red light
on a raised avenue (`night_cars_red.jpg`); by day, vans and a coupe with their wheels in motion
(`pday_cars_close.jpg`).

## Left

- The draw calls the merged meshes add (glass and wheels to 900 m): a per-section cull, or
  dropping the glass and wheel sections from the far LODs, would take them back.
- Parked cars still draw a component a part per tile (stage 2's path).
