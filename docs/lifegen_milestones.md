# Stage 4 milestone log (lifegen)

The full record of every stage 4 milestone, for the sessions that build and validate them. The
root [README](../README.md) has the short version. Spec: [`lifegen_scope.md`](lifegen_scope.md)
(what each milestone adds: section 13; Swagnik's decisions: section 12). Each milestone's entry
grows here as it lands, as in [`citygen_milestones.md`](citygen_milestones.md),
[`assetgen_milestones.md`](assetgen_milestones.md) and
[`atmosgen_milestones.md`](atmosgen_milestones.md).

## Milestones

| Milestone | What it adds | Status | Outputs |
|---|---|---|---|
| LG0 | Groundwork and spike: the life spec and styles, the plan format and schemas, `lifegen plan` (people and vehicles by district and hour, spawn and sink points, place slots, the fleet from AG18's roster, the asks of citygen), the `CityGenLife` plugin's skeleton (ZoneGraph lanes built from the graphs, Mass processors) built by the exporter; plain stand-ins and a few of AG18's cars on one district of Delta, against the benchmark; probes of MetaHuman, Mutable, retargeting and the engine pieces' maturity in 5.8; a tee draped in Blender's cloth solver | Done | [`docs/progress/LG0`](progress/LG0) |
| LG1 | People: the population library (24 MetaHumans made, rigged and assembled by script into the user's project, faces blended, bodies and skin by seed), Epic's walks retargeted in place, baked walks and impostor cards for the far crowd, the plan's person draws, the exporter's `--people` and the runtime's near, mid and far tiers; Delta's Old Town walked by them | Done | [`docs/progress/LG1`](progress/LG1) |
| LG2 | Clothing: 144 looks (6 a character, by fashion group) of garments cut from pattern parameters on each character's own body and draped in Blender's cloth solver (tees, shirts, hoodies, coveralls, bombers, jackets, trench coats, raincoats, cargo pants, trousers, skirts, sneakers, boots, dress shoes), 15 generated textiles, accessories and cyberware; looks' skeletal meshes, mid meshes and cards in the people library; people spawned by their district's groups in its colors and wear; the variety check | Done | [`docs/progress/LG2`](progress/LG2) |
| LG3 | Crowds on the streets: every walkway of the city at its street's density by hour, live round the view from a fixed pool (people come alive and go past the far tier, out of sight), trips out of and into AG3's doors, stations, garages and taxi stands, groups, pace, signals with derived phases at the crosswalks, jaywalking by danger, local avoidance and stepping aside from the player, stairs and elevators; Delta walked city-wide | Done | [`docs/progress/LG3`](progress/LG3) |
| LG4 | Life at places | Planned | |
| LG5 | Traffic: every lane of the city at its street's density by hour (twice M11's by default), live round the view from a fixed pool of AG18's cars by the districts' fleets and paints; following the car in front, red lights, junctions taken in turn with room past them, stopping for people and the player; Delta driven city-wide | Done | [`docs/progress/LG5`](progress/LG5) |
| LG6 | Transit | Planned | |
| LG7 | Air and water | Planned | |
| LG8 | Weather, reactions and release | Planned | |

## LG0: groundwork and spike

Built on the Windows PC (2026-11-13), on main after AT7, the play fixes and the showcase
(#221). Report, measurements, probe findings and recommendations for LG1 to LG8:
[`docs/progress/LG0/README.md`](progress/LG0/README.md).

- **Decisions** (scope section 12, Swagnik 2026-11-13): a generator of the plan and a library
  with the `CityGenLife` plugin on Mass, ZoneGraph, Smart Objects and StateTree; MetaHuman
  bodies made by script into the project if 5.8 allows it; generated garments with a kit
  out of the repo as the fallback; Epic's Game Animation Sample near the view and free
  mocap libraries for the rest; nothing in the repo unless anyone may use it; **the fleet is
  AG18's hand-designed vehicles**, the missing kinds designed on the Mac (changed); **a
  20 ms p95 frame budget** at native 1440p, no tuning rounds unless a milestone goes over
  (changed); stepping aside and looking first, fleeing and gathering later.
- **Spec and presets** (`lifegen/spec.py`, `presets.py`, `lifegen/schemas/life_spec.schema.json`;
  `python -m lifegen spec validate|schema`): per district its people (busy, residents,
  workers and visitors, the day's shape within M11's hour bands), its style (fashion groups,
  cyberware, wear, pulled by wealth and danger), its fleet (AG18's models by the parked
  cars' table, `assetgen/parked/table.py`, times the spec's multipliers), transit headways,
  air and water, budgets, reactions, the spike.
- **Plan format** (`lifegen/planmodel.py`, `lifegen/schemas/`): `life_plan.json`,
  `spawns/<tile>.json` (spawn points with rates by hour, place slots),
  `unreal_contribution.life.json` (layer 4), each entry hashed.
- **The plan** (`lifegen plan BUILD`, `plan.py`): Delta in 2 to 3 s: 6,789 spawn points
  (building entrances, station stairs, garages, taxi stands), 688 place slots (benches, bus
  stops, kiosks, vending machines, stalls, taxi stands) in 131 tiles; 58,189 people and
  3,394 vehicles on the streets at the peak hour; checks (spawns on the graphs, every spawn
  reaching another, densities kept to M11's within 1%, slots facing, the spike within the
  budget); `preview_crowds.png`.
- **The asks of citygen** (`lifegen/asks.py`): signal phases and timing, bus routes, turn
  restrictions, lobby points, piers, air corridors; of assetgen the doors (met by AG3) and
  AG18's missing kinds. Each with the record asked for, its state on a model and what the
  plan does meanwhile.
- **Runtime** (`citygen/ue/CityGenLife`): the controller builds ZoneGraph lanes from the
  spike's walkways and lanes at BeginPlay (an `AZoneGraphData` of its own, its BV-tree built
  in the plugin), makes people and cars Mass entities and moves them with two dynamic Mass
  processors, draws stand-ins and AG18's car parts as instanced meshes; console
  `CityGenLife.Enable|Respawn|Status`.
- **Exporter** (`citygen/unreal_life.py`, `import_city.Importer.life_controller`,
  `--life DIR`, `--no-life`): the manifest's `life`, `BUILD/unreal/life.json`, the
  controller placed with the spike, the stand-in material made by the import;
  `docs/unreal_export.md`, "lifegen's runtime (LG0)".
- **Spike** (Delta's Old Town at 23:00, 2,000 stand-ins within 450 m of its middle and
  densest round it, 40 cars of nine models; 11,340 ZoneGraph lanes built in 14 to 30 ms):
  the lean benchmark's `night_plan_all` 15.1 to **16.6 ms p95** (walk 14.9 to 16.6), under
  the 20 ms budget; the game thread about +2.5 ms at the walk's p95 (the controller's own
  tick 1.0 to 1.8 ms), the GPU +0.6 ms. The first build recreated the instances' render
  state every frame and left them in Lumen's scene: walk 26.3 ms, 8 to 9 ms of it Lumen's
  scene update; both are off now (`bInLumen`, `bRebuildRenderState`), with the benchmark's
  `night_life*` passes to measure them. The package `builds/packaged/Delta_lg0` launches
  with the spike.
- **Probes** (`lifegen/probes/`): the engine pieces' maturity in 5.8 (ZoneGraph, Mass
  Gameplay, Mass Crowd, MetaHuman Crowd, AnimToTexture, Chaos Vehicles experimental; Mutable
  and MetaHuman Creator beta; Smart Objects, StateTree, Pose Search, IK Rig, Chaos Cloth
  released); MetaHuman Creator creates and edits bodies from Python but cannot build one
  without Epic's cloud rigging (sign-in and EULA) and its skin without the optional
  content; Mutable has no Python graph editing; a CMU-style clip retargets onto the
  mannequin by script (its chains set by script).
- **Garment test** (`lifegen/blender/garment_test.py`): a tee of two flat panels sewn and
  draped on a plain body headless in 13.5 s, its seams closed to 0.9 cm on average, baked
  and rendered.
- **Tests** (`tests/lifegen/test_lg_plan.py`; `test_no_network.py` reads lifegen;
  `test_unreal_play.py` the third plugin).

## LG1: people

Built on the Windows PC (2026-11-14), on main after LG0 (#222), DLSS and fixtures (#224) and
cars and steam (#225). Report, shots, benchmark and open items:
[`docs/progress/LG1/README.md`](progress/LG1/README.md).

- **Frame** (Swagnik, 2026-11-14): MetaHumans made by script on his sign-in, for rigging and
  assembly only (Epic's cloud service, as the EULA he accepted allows); Unreal's own
  animations only (his Game Animation Sample), no other mocap; MetaHuman's plain wardrobe
  (LG2 brings the garments); nothing of Epic's in the repo (decision 5).
- **The library's spec** (`lifegen/library.py`, `LIB_VERSION` lg1.1): 24 characters by seed,
  each a MetaHuman preset of the engine's optional content (its hair, eyebrows and wardrobe)
  with its face's 1,397 coefficients blended 0.15 to 0.45 toward another preset of the same
  body, its height and build (the creator's body constraints) and skin tone drawn; the clips
  (two walks, two idles); the far stand-ins (LOD 3, 15 fps, 8 views by 8 frames, 128 x 256 a
  cell); the tiers (near 30 m, at most 160; mid 90 m; far 300 m); `library_hash` (the spec,
  the build's code, the engine's version) names the cache.
- **The plan's draws** (`lifegen/plan.py`, `planmodel.py`): the spike's `library` and
  `persons` (per person its character, height scale 0.96 to 1.04, gait, pace 1.15 to
  1.55 m/s, outfit tint from its district's palette, seed), every spawn point's `seed`; check
  `people_draws` (every character drawn, none over 12% of the people).
- **The library's build** (`citygen/unreal_people.py`, `citygen/ue/people_library.py`): in
  the project's full editor off screen (`-RenderOffscreen`, the script on the editor's tick,
  `-NoMetaHumanAccountPortalLoginFallback`): characters made
  (`MetaHumanCharacterEditorSubsystem`), rigged (`request_auto_rigging`, joints only) and
  given their texture sources (`request_texture_sources`, 2k) by Epic's service on the
  editor's saved sign-in, assembled (Optimized, Medium; 60 to 125 s each; the editor
  restarted every 6 characters, whose memory otherwise grew the page file by 28 GB); the
  clips retargeted by IK Rig's batch retarget and made in place (`in_place`); the mid mesh
  (GeometryScript, the face's shells out) baked by AnimToTexture; the impostor sheets by
  scene captures; `Saved/CityGenPeople/library.json`; the cache
  `~/.cache/cybergen/people/<hash>` (3.2 GB; the MetaHuman Character sources left out), a
  project's stamp `Saved/CityGenPeople.stamp`. A commandlet cannot assemble (the texture
  graphs that bake the skin do not run in one).
- **Epic's animations** (`citygen/ue/people_gas.py`, `unreal_people.migrate`): the clips'
  14-package closure in the user's Game Animation Sample copied into the project at its own
  paths, the sample's editor run read only.
- **Exporter** (`citygen unreal ... --people [--gas UPROJECT]`; `unreal_life.persons`,
  `people_library`; `import_city.people_assets`, `LIFE_VERSION` life2): the life
  controller's people properties; `docs/unreal_export.md`, "From LG1: people".
- **Runtime** (`CityGenLifePeople.cpp`): near people as pooled skeletal slots (body leading
  face and outfit, the groom's cards on the head, the gait's clip at pace, the outfit's
  garments tinted), mid people as instances of the baked walk (no shadow), far people as
  cards; the walk's phase kept across tiers; `CityGenLife.Tiers`, the status's `library`.
- **Delta** (Old Town's spike, 2,000 people, 40 cars): imported over its earlier import (one
  actor updated); every check passes; 24 near, 229 mid and 1,050 far at once on the main
  street. Lean benchmark at 2560 x 1440: `night_plan_all` **19.6 ms p95** native (walk 22.8,
  the game thread), DLSS Quality 17.9 (walk 22.3); people off 18.1. The mid tier's shadows
  doubled the draws (3,044 to 1,907 on the walk without them).
- **Tests** (`tests/lifegen/test_lg_people.py`: characters and draws by seed, the hash, the
  exporter's packing, the cache and stamp, no Unreal or MetaHuman file in the repo;
  `test_bench.py` the tier passes).

## LG2: clothing

Built on the Windows PC (2026-11-14 and 15), on main after LG5 (#230). Report, contact sheets,
shots, benchmark and open items: [`docs/progress/LG2/README.md`](progress/LG2/README.md).

- **Looks** (`lifegen/garments.py`): 6 a character, 144 in all, each a whole outfit of a
  group (`GROUPS`: the styles' nine and `rain`; `GROUP_LOOKS` shares them out, a character one
  look a group): a base layer, an outer layer or none, a bottom, shoes and accessories, each
  garment in a textile of its group with its trims (`RECIPES`); in the library's spec and hash.
- **Garments** (`KINDS`, `draft`; `lifegen/blender/garments.py`): 15 kinds (tee, long tee,
  shirt, hoodie, coveralls, bomber, jacket, trench, raincoat, cargo, trousers, skirt, sneakers,
  boots, dress shoes) as pattern parameters cut for each body's landmarks, built on the
  mannequin (the body, its plain outfit and face as one voxel surface, labelled by part),
  offset by their ease, cut at hem, sleeve, ankle and the plain outfit's neckline, flared,
  hooded, collared, draped by Blender's cloth solver, rimmed at every open edge, UV'd as their
  pattern pieces; a look layered (each 4 mm outside those under it) with its covered faces out.
  The flat-panel sewing of the scope (LG0's test) was dropped: a panel cut for one body and
  sewn by springs crumples where it does not fit.
- **Textiles** (`lifegen/textiles.py`): 15 tileable PBR sets in AG6's style.
- **Accessories and cyberware**: visor, respirator, mask, headset, cap, beanie, hard hat,
  implant plates, arm plates, backpack, bag; rigid on their bone, arm plates on the skin.
- **The library's build** (`citygen/unreal_people.py` `dress`, `citygen/ue/people_library.py`
  steps `bodies`, `looks`; `LIB_VERSION` lg2.1): the bodies exported, every character dressed
  in Blender (4 at once), each look's garments a skeletal mesh on the body's skeleton (weights
  from the plain outfit where nearer than the body), a mid mesh and a card with a dye mask per
  look; the manifest's entries are the looks.
- **The plan** (`lifegen/plan.py`): each pool person's look and group, the districts' people by
  group (raincoats by the weather's share, clear until LG8), colors per group, wear; the check
  `variety`.
- **Exporter and runtime** (`PACK_VERSION` 5, `LIFE_VERSION` life6): a person spawned in a
  district takes a slot of the district's groups and three of its colors and a wear; garments
  tinted per person near (dynamic instances), mid (14 custom floats) and far (the cards' dye
  mask); bench pass `night_life_noclothes`. Cloth simulation near the view not set up (no
  script route to Chaos Cloth's clothing data).
- **Delta:** the library built once with the final code (`dd24b28ed929920b`, the looks, mid
  meshes and cards in 2,082 s after the dressing); every check passes; 125 of the 144 looks in
  the pool, at most 0.44 expected alike pairs within 50 m. `night_plan_all` 20.8 ms p95 native
  on the lean route (walk 23.8, drive 20.9, fly 19.7) against LG5's 21.2: clothing costs no
  frame time (more draws on the walk, 2,415 to 2,060); the clothing switch off 22.0 (MetaHuman's
  template bodies). Still over the 20 ms budget by LG5's traffic.
- **Open items:** a heavy-bodied character's long coat shows the layer under it at the waist
  while walking; jagged rims at collars and coat edges; no prints or logos on the garments
  (AG6's brand logos not used yet); raincoats (drawn only in rain, LG8) with a weak front
  skirt panel; the dyed garments glossy in the rain; cloth simulation.

## LG3: crowds on the streets

Built on the Windows PC (2026-11-14), before LG2 at Swagnik's ask (the people keep LG1's plain
outfit), on main after LG1 (#226). Report, shots, benchmark and open items:
[`docs/progress/LG3/README.md`](progress/LG3/README.md).

- **Every walkway's people** (`lifegen/plan.py` `crowd_walks`, `planmodel.Walk`, each tile
  file's `walks`): a road segment's M11 people per hour band (crowd per 100 m over its length,
  the district's busy, the spec's `crowd.scale`) on its own walkways by length; every other
  walkway (crossings, crosswalks, paths, skybridges, platforms, stairs) at its district's mean
  sidewalk density times `presets.OFFSTREET` (crossing 0.6, crosswalk 0.4, path 0.3, skybridge
  0.25, platform 0.6, stairs 0.4, elevator 0), lengths along the slope; none on a walkway no
  spawn point reaches (said in `totals.left_out`). The hours within a band follow the
  district's day.
- **Signals** (`plan.signals`, `signals.json`, `planmodel.Signals`; the ask `signal_phases`,
  derived): two phases per signalized junction from its legs' lines (within 45 degrees of the
  first leg's, `attrs.cuts`), each crosswalk walking while the leg it crosses is stopped (its
  walkways matched by their middle stretch), `presets.SIGNAL` (60 s cycle, 3 s amber, 2 s
  all-red, 12 s to start crossing), an offset per junction by its id's hash.
- **AG3's doors** (`plan.door_points`): the spawn points where the build has stage 2's
  buildings (`assets/unreal_contribution.buildings.json`), each door's position on the facade,
  outward yaw (`Spawn.yaw_deg`), walkway and weight by kind (`presets.DOOR_WEIGHT`); M3's
  entrances otherwise.
- **The crowd** (`plan.crowd_plan`, `planmodel.CrowdPlan`, the spec's `crowd`: hour, pool,
  scale, trip_s; `presets.CROWD`): a pool of 2,400 people drawn from LG1's library by their
  seeds (`lg3.person`, the tint an index into the district's palette where each comes out),
  each district's palette, the live radius (340 m), trips (600 s), groups (1 to 5: 56, 26, 11,
  5, 2%), jaywalking (1% to 30% by danger), avoidance (reach 4 m, personal 0.75 m, player
  2.5 m, within 90 m of the view), speeds (stairs 0.6 of the pace, escalators 0.3 plus
  0.5 m/s, elevators 0.6 m/s). The spike keeps its 40 cars and no people.
- **Checks** (`plan.crowd_checks`): `crowd_densities`, `crowd_levels`, `signals`,
  `crowd_budget` (the pool times (300 / 340)^2 within the 2,000 people in 300 m),
  `people_draws` on the pool, `crowd_spawns`.
- **Exporter** (`citygen/unreal_life.py` `pack_crowd`, `pack_walks`, `pack_drive`,
  `PACK_VERSION` 3; `import_city.crowd_props`, `LIFE_VERSION` life3; `unreal.life_summary`):
  the whole walkway graph as lanes with each walkway's kind, district, people per band and
  signal window; the districts' days, dangers and palettes; the doors on their walkways at
  their distance along them; the pool; `docs/unreal_export.md`, "From LG3: crowds on the
  streets". A plan before LG3 packs LG1's spike as before.
- **Runtime** (`CityGenLifeCrowd.cpp`; the walk processor's `ExecuteCity` and
  `CgLife::StepCity`; `CityGenLifePeople.cpp`): walkways live within `LiveM` of the view,
  filled as they come alive and emptied as they go (both past the far tier), people turning
  back at a walkway that is not live; a fixed pool of Mass entities (no entity made or
  destroyed while playing), the density scaled down evenly past 92% of it (`LiveScale`); doors
  sending people out at their rates and taking them in at a trip's end (0.6 m inside, then
  gone); groups sharing a seed; people waiting at a signalized crosswalk's curb for its walk
  window, a share crossing against it; avoidance (passing on the left, following a slower
  person, stepping right face to face, stepping aside from the player); stairs, escalators and
  hidden elevator rides; the idle clip near while standing, the baked walk and card frozen mid
  and far; far people stepping every second frame, untiered ones every fourth, far cards sent
  every second frame, the ground traced only near; `CityGenLife.Hour`, `CityGenLife.Crowd
  SCALE [TRIP_S]`, the status's `crowd`.
- **Check** (`citygen/ue/check_city.py`): the life status at every play view; `*_wait*` views
  wait 30 s more.
- **Delta** (imported over LG1's import, one actor updated): every check passes; 20,245
  ZoneGraph lanes; Old Town at 0.28 to 0.41 of its plan's density (6,300 to 7,900 people
  wanted round the view, 2,400 in the pool), every other district at its full density;
  doors verified with 20 s trips (4,873 in, 3,134 out over three views, the live people held
  at their number). Lean benchmark at native 2560 x 1440 (no DLSS pass: Swagnik,
  2026-11-14): `night_plan_all` **19.3 ms p95** (walk 21.4, drive 19.3, fly 18.5; LG1's spike
  19.6), people off 18.1; the drive and the flight see 500 to 1,750 people live round the view
  outside Old Town.
- **Found:** the walkway graph's crosswalk and crossing walkways run their corner tails up to
  25 m along or across the carriageway where M17's and M22's cuts reach far (922 crossings
  and 403 crosswalks over 30 m in Delta); people follow them (open item for citygen).
- **Tests** (`tests/lifegen/test_lg_plan.py`: every walkway's people, the signals' phases, a
  walkway nobody reaches, AG3's doors as spawn points, the exporter's crowd pack and summary;
  the fixture gained a signalized junction with two crosswalks).

## LG5: traffic

Built on the Windows PC (2026-11-14), before LG2 at Swagnik's ask after his walk of the
packaged Delta ("I want cars everywhere"; a car drove through him), on main after the people
fixes (#229). Report, shots, benchmark and open items:
[`docs/progress/LG5/README.md`](progress/LG5/README.md).

- **Every lane's cars** (`lifegen/plan.py` `traffic_lanes`, `planmodel.Drive`, each tile file's
  `drives`): a road segment's M11 vehicles per 100 m and hour band over its lanes by length,
  times the fleet's `busy` and the spec's `traffic.scale` (2 by default: M11's late band, 0.7
  cars per 100 m of lane, read as empty roads); none on a lane off the lane graph's largest
  strongly connected part (`citygen.unreal_life.strong_components`, `main_component`), said in
  `totals.left_out`.
- **Signals for cars** (`plan.lane_signals`): each lane ending at a signalized junction on one
  of its legs gets LG3's derived signal, its leg's phase and a stop point 1.2 m short of the
  crosswalk across it (`presets.TRAFFIC["stop_margin_m"]`).
- **The traffic** (`plan.traffic_plan`, `planmodel.TrafficPlan`, the spec's `traffic`: pool,
  live_m, scale; `presets.TRAFFIC`): a pool of 1,800 slots of AG18's models (no Vex or Aurel),
  shared out half by the city's mix at the hour and half by each model's most in any
  district; the districts' fleets and 6 paints per model; the live radius (800 m); the car
  following (the intelligent driver model), signal, junction and yielding settings. LG0's
  spike cars go (`SPIKE["cars"]` 0).
- **Checks** (`plan.traffic_checks`): `traffic_densities`, `traffic_lanes`, `traffic_signals`,
  `traffic_budget` (the pool within the 500 vehicles in 300 m: 253), `traffic_fleet`.
- **Exporter** (`citygen/unreal_life.py` `pack_traffic`, `pack_drive_lanes`, `conflicts`,
  `traffic_cars`, `PACK_VERSION` 4; `import_city.traffic_props`, `LIFE_VERSION` life5;
  `unreal.life_summary`): the whole lane graph as drive lanes with their cars per band,
  district, main part, signal window and stop; the junction connectors that may not be driven
  at once (GEOS's tree: lines within 2.2 m in plan and 3 m in height); the signals' windows for
  cars; the pool's models, fleets, paints, lengths, wheel radii and draw distances
  (`TRAFFIC_CULL_M`); `docs/unreal_export.md`, "From LG5: traffic".
- **Runtime** (`CityGenLifeTraffic.cpp`; the drive processor's `ExecuteTraffic`): the whole lane
  graph live within 800 m of the view from a fixed pool (lanes filled and emptied past where
  cars are seen, refilled past 450 m, the density scaled evenly past 92% of the pool); cars
  following the car in front by the intelligent driver model at cars_steam's speeds, stopping
  at red and amber, holding a junction connector only while no conflicting one is driven, held
  or claimed by a longer waiter and with room past the junction (forced after 25 s), stopping
  for the crowd's people and every pawn but the free camera on their line ahead; wheels
  rolling; instances sent only for slots in use and near parts only for near cars.
  `CityGenLife.Traffic [0|1] [SCALE]`, the Tab menu's Traffic row (`CityGenPlay`), the
  status's `traffic`; `CityGenLife.TrafficShow`, `BlockPlayer`, `Jaywalk` for the check's
  shots, whose view commands gained `wait`, `dilate`, `until` and `<name>@late`.
- **Delta**: 3,331 cars on 4,849 lanes at 23:00 (twice M11's), 25,548 conflicting connector
  pairs, 907 lanes stopping at 150 signals; imported over the people fixes' import (one actor
  updated); every check passes; 550 to 860 cars live round the views, every district driven;
  shots of a red light's queue, a car stopped for the walker in its lane and for people
  crossing. Lean benchmark at native 2560 x 1440: `night_plan_all` **21.2 ms p95** (walk 25.5,
  drive 20.7, fly 19.7), traffic off 18.9: over the 20 ms budget by about 1 ms after one tuning
  round (21.6 before it); the rest is the engine's cost of 92 moving instanced components
  (lifegen's tick 1.3 to 2 ms), half the cars 20.1 (an open item for the performance pass).
- **Tests** (`tests/lifegen/test_lg_plan.py`: every lane's cars, signals and stops, the pool and
  fleets, a lane off the main part, the budget check, strong components, the exporter's
  traffic pack and summary; the fixture's lanes became a ring with a signalized end;
  `tests/test_bench.py` the traffic passes).
