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
| LG4 | Life at places: every bench, bus shelter, kiosk, vending machine, food stall and taxi stand of the city a place slot (its use points Smart Objects of the world's subsystem while its walkway is live), clubs' queues and bars' smokers at their doors; people walking by sit, wait, buy, eat, queue, smoke or talk there and walk on; AG3's shop doors as places by their hours (closed doors send no one, open shops take visitors in and let them out); gang members on their own turf's walkways and spots in their faction's colors; police pairs on the patrol walkways out of their stations and patrol cars in a police livery; the Game Animation Sample's bench loop and idle breaks retargeted onto the library's bodies; Delta city-wide | Done | [`docs/progress/LG4`](progress/LG4) |
| LG5 | Traffic: every lane of the city at its street's density by hour (twice M11's by default), live round the view from a fixed pool of AG18's cars by the districts' fleets and paints; following the car in front, red lights, junctions taken in turn with room past them, stopping for people and the player; Delta driven city-wide | Done | [`docs/progress/LG5`](progress/LG5) |
| LG6 | Transit: a timetable per line from the model's tracks and stations (the fastest runs by the mode's speeds, rates and the track's curves, dwells, turns at an open line's ends), its trains per hour band evenly round its cycle, each station's stop and board walkway, people boarding and leaving by the station's riders; the trains (stand-ins of the exporter's per mode model table until the Mac's designs) running every line city-wide by the world's time, doors open at the stops, the crowd leaving and boarding them round the view; Delta's five lines | Done | [`docs/progress/LG6`](progress/LG6) |
| LG7 | Air and water: routes for everything that flies and floats, city-wide, each a closed path run to a timetable by the world's time (as LG6's trains): flying cars between M3's pads (landing and taking off vertically) and round circuits over the avenues and highways on layers by heading, clear of every mass, tube, line, skybridge and sign; delivery drones from roof to roof; police orbits by danger; media fliers round the landmarks; aircraft high over the map; a spaceport's shuttles down onto their launch pads; boats keeping right on every river, channel and canal; water taxis between piers derived from M16's quays; double-ended ferries across the rivers; ships at the port's berths and one offshore. AG18's hover cars as the flying cars and police fliers, stand-ins for the rest; Delta city-wide | Done | [`docs/progress/LG7`](progress/LG7) |
| LG8 | Weather, reactions and release: life by atmosgen's hour and weather state (people out, pace, raincoats and umbrellas, shelter under the covers of atmosgen's rain shadow, nightlife round the open bars, clubs and arcades, the cars' speed and headway), reactions (people near the player look at it; a danger sends them running, then draws a crowd to look), the junction room fix and stuck cars, the crowd and traffic performance pass, every sample city planned with every check passing, Unreal checks of Delta and Vesper Bay, the release package | Done | [`docs/progress/LG8`](progress/LG8) |

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

## LG4: life at places

Built on the Windows PC (2026-11-15), on main after LG2 (#231). Report, shots, benchmark and
open items: [`docs/progress/LG4/README.md`](progress/LG4/README.md).

- **Slots** (`lifegen/places.py` `make_slots`, `presets.SLOT_KINDS`, `planmodel.Slot`, each tile
  file's `slots`): every M6 bench, bus shelter, kiosk, vending machine and food stall, M11's
  taxi stands (projected onto their walkway, facing the curb), a club's queue at its door and a
  share of bars' smokers beside theirs; per slot its use points in the object's frame (x, y, z,
  the way its user faces), its walkway within `SLOT_REACH_M` 15 m, its behavior and clip (idle,
  sit, talk), its stay and its users per hour band (the walkway's crowd times the kind's share,
  at most its points). Points in a building or on a carriageway (lanes, ground-level
  junctions: `Carriageway`, `Footprints.blocked`) are dropped, a slot with none left out.
- **Places by their hours** (`make_places`, `apply_hours`, `presets.PLACE_KINDS`): every AG3
  shop door a place with its hours (M11's POI's own where the door is a POI's unit, else by its
  use; a food place's drawn among four), open per hour, busy by band (bars fill at night), a
  visit's chance and stay; the doors' rates by the hours, renormalized per district and hour so
  a closed door's people leave by the district's open ones.
- **Gangs** (`gang_turfs`, `gang_walks`, `gang_spots`, `faction_colors`; `presets.GANG`): per
  gang turf (M11's territories of a gang faction) its walkways, M11's gang members on them by
  band (walking, and a loitering share at its spots: its hideouts' doors and its busiest
  corners, a ring of points on the sidewalk walked in from its end until clear of the
  carriageway), its faction's dye colors; M11's members outside every gang turf left out.
- **Police** (`police_plan`, `presets.POLICE`): per district its police on foot on the patrol
  walkways (the police field at least 0.25) and patrol cars on its main lanes (`DrivePolice`,
  a share of M11's police in cars, two to a car), its precinct's station doors; an AG18 model in
  a white livery by paint (`halcyon_sable`).
- **The pool's roles** (`assign_roles`, `CrowdPlan.role`, `TrafficPlan.police_slots`): gang
  members and police keep slots of the crowd's pool in their group's looks (each role's most
  near the view times a margin, within a share of the pool), patrol cars slots of the traffic
  pool.
- **Checks** (`plan.places_checks`): `slots_placed` (on its walkway, out of every building and
  carriageway, each user facing its object), `slot_use`, `places_hours`, `gang_turf` (members
  only on their own turf's walkways and spots), `police_patrols` (within the police field),
  `places_budget`; `preview_places.png`; asks `slot_points` and `police_vehicles` of assetgen.
- **Exporter and runtime** (`unreal_life.pack_places`, `PACK_VERSION` 6;
  `import_city.places_props`, `LIFE_VERSION` life7; `CityGenLifePlaces.cpp`): the places' clips
  (the Game Animation Sample's bench loop and three idle breaks) retargeted onto the library's
  bodies in the project (`unreal_people.ensure_place_clips`, `ue/people_places.py`; the
  library untouched); a live slot's points Smart Objects of the world's subsystem (claimed,
  occupied, freed; definitions per kind set by reflection); the behaviors five states of the
  walk processor (`ToSlot`, `AtSlot`, `FromSlot`, `Inside`), not StateTree (MassAI's processors
  and a tree per entity for a timer and two lerps); gangs on their turf's walkways in their
  colors, police pairs on the patrol walkways out of and back into their stations, patrol cars
  in the livery by LG5's rules; sitting people near out to the mid tier; console
  `CityGenLife.Places`, `.Gangs`, `.Police`, `.PlaceShow`, `.SitOffset`, the Tab menu's Places
  row, the status's `places`; bench pass `night_life_noplaces`.
- **Delta**: 1,641 slots, 16,125 places, 5 gang turfs, 303 police on foot and 81 patrol cars
  at 23:00 over six precincts; every plan check and both Unreal checks pass; round the views
  up to 162 slots live with 146 users, 129 gang members, 48 police on foot and 20 patrol cars,
  558 Smart Objects, over 1,000 shop visits; shots of people sitting, queueing, smoking, gangs
  at their corners, police pairs and patrol cars. Lifegen's
  tick 2.2 to 3.1 ms round the views against LG5's 1.3 to 2; the lean benchmark
  `night_plan_all` 21.2 ms p95 native (walk 26.2), places off 20.9 (walk 23.5).
- **Tests** (`tests/lifegen/test_lg_places.py`: open hours, slot points and facings, faction
  colors and reserves, the plan on a small city with a gang turf, hideout, precinct, station and
  shop doors, the checks catching members off their turf and police off their walkways, the
  exporter's pack; `tests/test_bench.py` the places pass).

## LG6: transit

Built on the Windows PC (2026-11-16), on main after the crossings fix's Unreal run (#234).
Report, shots, benchmark, decisions and open items:
[`docs/progress/LG6/README.md`](progress/LG6/README.md).

- **Timetables** (`lifegen/transit.py`, `presets.TRANSIT_MODES`, `TRANSIT_HEADWAY_MIN`,
  `TRANSIT`; `timetables.json`, `planmodel.Timetables`): per line of the model its track (M5's
  path in 3D; a loop closing on itself), its stops (each station's platform walkway, M5's
  `platform`, a metro's `concourse`, else its first access, projected onto the track within
  25 m in plan and 12 m in height), the fastest runs between them (a forward and a backward
  pass on a 2 m grid at the mode's cruise, acceleration and braking, at most sqrt(lateral R)
  wherever the train is, R the track's radius in plan), dwells by mode, the cycle (a loop one
  way round from its first stop; an open line the whole track there and back, turning at its
  ends with a 60 s layover, a terminal station within a train's length of an end the turn
  point, the train crossing to the other way's track over the 90 m before it), sampled every
  half second at constant acceleration per grid step; per hour band ceil(cycle / headway)
  trains evenly round it (the spec's `transit.headway_min` by line name, else the mode's),
  fewer where two would come within a train's length and 60 m or into a terminal at once (the
  raised headway in `notes`); ids `train.<line id>.<n>`, a layer 4 entry each.
- **Boarding** (`boarding`, `station_riders`): a station's riders are its street accesses'
  people (LG3's spawn rates by hour); per stop and band as many leave each train calling there
  as board it, those riders over the trains calling there (every line and way), at least
  `board_min`, at most the mode's `board_max`. The platform deck's half width across the track
  (M5's `platform` deck) and the keep-out `clear_m` its people keep off the line's middle (its
  trains); where people board (the doors' level; from a metro's concourse 8 m over the track
  and a pylon sky station's platforms level with the tube's axis, at the point over a door).
- **Checks:** `timetables` (speeds, curve limits, acceleration and braking read back from the
  samples; dwells kept; a run no shorter than its distance at cruise; a loop closing, an open
  line turning back at both ends; trains a train's length and 60 m apart, none two in a
  terminal at once), `transit_stops` (every station on its line's track, within the run, a
  train calling there; trains longer than their platforms noted), `transit_boarding` (every
  stop's board walkway in the walkway graph and reaching its station's street accesses),
  `transit_budget` (120 trains and 600 cars at once); `preview_transit.png` (the lines,
  stations and trains at the crowd's hour; each line's trains over one cycle on a time and
  distance graph); the ask `train_models` of assetgen.
- **Exporter and runtime** (`unreal_life.pack_transit`, the stand-ins' per mode model table
  `TRANSIT_MODELS`, `PACK_VERSION` 7; `import_city.transit_props`, `M_CgTransit`,
  `LIFE_VERSION` life8; `CityGenLifeTransit.cpp`; the walk processor's `CgWalk::Board` and the
  platforms' keep-out `WalkClear`): every line's trains placed each frame by the world's time
  from the sampled cycle (nothing simulated: every line runs city-wide, a far train costs a
  lookup, its instances sent every fourth frame past 1.5 km); each car by the track's points at
  its ends, on its way's own track; doors opening at the stops (leaves and lit doorways near
  the view); at a stop whose platform walkway is live the stop's people come out of the doors
  and walk on (`FromSlot` with no slot) and the crowd on the platform walks into the doors and
  is gone; a served station's street accesses send no one while transit runs. Console
  `CityGenLife.Transit`, `.TransitShow`; the Tab menu's Transit row; the status's `transit`;
  the check's `until` reads `transit.show`; bench pass `night_life_notransit`.
- **Delta:** five lines (Metro Line, Maglev Line, Waterfront Monorail, Skyline Loop and Delta
  Loop, both sky tube loops), 20 stops, 14 trains (53 cars) at 23:00, 19 at the busiest
  bands; every plan check and the Unreal check pass; shots of trains at the stations with
  their doors open and people boarding, and running on the maglev, the monorail, the sky tubes
  and in the metro's tunnel.
- **Tests** (`tests/lifegen/test_lg_transit.py`: the timetable on the small city's metro, a sky
  tube loop, speeds kept to a tight curve and the rates, a headway too close raised, the checks
  catching a bad timetable, too many trains, a station off its track, boarding by the riders,
  the exporter's pack; `tests/test_bench.py` the transit pass; LG0's small city's metro has a
  track now).

## LG7: air and water

Built on the Windows PC (2026-11-16), on main after LG6 (#235). Report, shots, benchmark,
decisions and open items: [`docs/progress/LG7/README.md`](progress/LG7/README.md).

- **Routes** (`lifegen/airwater.py`, `presets.AW_VEHICLES`, `AIR`, `WATER`, `AW_BUDGET`; the
  spec's `air` and `water` with `busy` and per kind `kinds` multipliers): everything that flies
  or floats runs a closed route, its points carrying the heading the vehicle faces there, its
  speed profile on a 4 m grid (the kind's cruise, acceleration and braking, at most
  sqrt(lateral R) in a turn, its climb rate on a vertical stretch), dwells where it lands or
  berths, the cycle sampled every second; per hour band its vehicles evenly round the cycle,
  fewer where two would come within the kind's spacing. Ids from what a route serves
  (`air.car.<pad>`, `air.lane.<node>`, `air.drone.<hub>.<drop>`, `air.police.<district>.<k>`,
  `water.boat.<water>`, `water.taxi.<pier>`, `water.ferry.<pier>`, `water.ship.<berth>`), a
  layer 4 entry each.
- **The airspace** (`AirSpace`, `obstacles`): building masses and roof items, skybridges,
  structures (sky tubes, decks, beams, pylons, columns), transit lines, megasite masses and signs
  in front of a facade or over a roof, widened 3 m in plan and 3 m in height, on a 4 m raster of
  63 height slabs of 8 m; a kind's cells at a height grown by its own margin (cars 8 m, police
  10, media 12) and, for cars, police and media, on 8 m cells. Routes by a windowed A* costing
  1 over the avenues and highways and 2.2 elsewhere (between the towers, over lower roofs),
  pulled straight on cells no dearer than the path crossed, corners rounded by the kind's
  turn radius where clear.
- **Fliers:** flying cars between M3's pads (paired 500 to 2,200 m apart; a pad something
  stands over left out with what), up from one pad, across on the layer of the leg's heading
  (`car_layers` 48 to 450 m: east-bound the even layers, west-bound the odd, at least
  `pad_over_m` over both roofs), down onto the other, a dwell, back on the other heading's
  layer; circuits round three avenue or highway nodes of each district (the change of layer at
  each corner along `ramp_m`), as many as its cars per km2 by band need (`car_density` times its
  busy, the spec's and 0.5 plus its wealth, at most `per_circuit` a circuit); AG18's hover cars
  (Kestrel's three) by the district's fleet. Delivery drones from a hub roof to a drop roof on
  `drone_layers` and 4 m cells, hovering down onto each. Police orbits (110 to 330 m) over
  each district by its danger, more by night; media fliers round the tallest landmarks;
  aircraft crossing the map at 760 and 820 m, turning off it; a spaceport's shuttle per launch
  pad, in along its flight cone and down onto it.
- **The water** (`WaterSpace`, `piers`, `_water_route`, `ship_routes`): M16's bodies (not the
  ornamental ones) on a 4 m raster with a surface and a depth per cell (M16's bed rule, linear
  from the nearest bank's toe); a kind's water as exact geometry (shrunk by its half beam and
  margin, less the banks' slopes, quays' bands, M6's moored boats, columns and AG7's bridge
  piers grown by as much), its draft under it, a bridge too low for its height out. Boats up and
  down every river, channel and canal keeping right (each way offset from the middle by the
  most both ways fit, a half turn at each end; a body cut by bridge piers its longest stretch
  from an end); water taxis on tours of up to four piers (one beside each quay's middle, clear
  of the moored boats); double-ended ferries across the rivers between piers where walkways
  reach both shores; ships in to the port's berths on water deep and wide enough, else lying
  at them, and one offshore between two far points of the map's edge.
- **Checks:** `air_lanes` (each flier's path read back every 4 m against the airspace at its
  kind's margin; a pad's column at the drones'), `air_pads`, `water_lanes` (every boat within
  1 m of its kind's water, exactly, and at the surface), `airwater_timing` (speeds, turns,
  climbs, acceleration and braking read back, dwells, routes closed, vehicles apart),
  `airwater_budget` (500 fliers, 300 drones, 160 boats at once); `preview_airwater.png`; the
  asks `piers` and `air_corridors` derived, `fleet_kinds` naming the kinds still to design.
- **Exporter and runtime** (`unreal_life.pack_airwater`, the per kind model table
  `AIRWATER_MODELS`, `PACK_VERSION` 8; `import_city.airwater_props`, `LIFE_VERSION` life9;
  `CityGenLifeAir.cpp`): every vehicle by the world's time from its route's samples, its
  heading interpolated, fliers banking and pitching, boats rolling and bobbing; AG18's hover
  cars with nav lights and, police fliers, a flashing bar in LG4's livery; stand-ins for the
  rest, lit by night, strobes and beacons flashing. Console `CityGenLife.Air`, `.Water`,
  `.AirShow`; the Tab menu's Air traffic and Boats rows; the status's `airwater`; bench pass
  `night_life_noairwater`.
- **Delta:** 134 routes: 53 for flying cars (27 pad pairs, 26 circuits), 50 drones, 9 police
  orbits, 2 media fliers, 2 aircraft; 9 boats, 3 water taxi tours, 3 ferries, 3 ships (two
  lying in the harbor basins, one offshore); 201 fliers and 20 boats at 23:00, 253 fliers at
  the busiest band. 54 of the 70 pads flown (16 under their own building's crown mast), 17
  piers derived and called at. Every plan check and the Unreal check pass; shots of a flying
  car landing on its pad, cars on their layers over Midtown and the Corporate Core, a police
  flier, a drone, boats on the river, the ferry at its pier, a ship at its berth. Air and
  water's own step 0.17 to 0.22 ms; `night_plan_all` 22.6 ms p95 native, air and water off
  21.7 (after one short tuning round: components sent every frame only while a vehicle within
  600 m moved in them; both under about 3.3 cores of other load). The package
  (`builds/packaged/Delta_lg7`) runs them.
- **Tests** (`tests/lifegen/test_lg_airwater.py`: a small city with two roof pads and a tower
  between them, a river, a canal with quays and a moored boat, the sea and a basin, a
  spaceport; the airspace by height, A* round a wall, the pad flight clear of the tower on
  layers by heading, circuits, police, aircraft, the shuttle on its launch pad, boats keeping
  right and turning at their ends, piers and the double-ended ferry, ships, the checks failing
  where they should, vehicles kept apart, the spec's kinds, the plan's file, contribution and
  the exporter's pack with and without AG18's hover cars).

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

## LG8: weather, reactions and release

Built on the Windows PC (2026-11-16 and 17), on main after LG7 (#236); stage 4's last
milestone. Report, shots, benchmark, decisions and open items:
[`docs/progress/LG8/README.md`](progress/LG8/README.md).

- **The hour:** the runtime follows atmosgen's controller's hour (read every half second by its
  class's name): an hour's step as time runs moves the doors' and places' rates and the live
  walkways' and lanes' numbers (people coming out and going in over their trips), a jump (the
  play menu's day, dusk or night) fills them again; transit and what flies and floats take
  their band from it. `CityGenLife.Hour H` holds life at H; `CityGenLife.FollowAtmos`.
- **The weather** (`lifegen/weather.py`, `presets.WEATHER_LIFE`, `WEATHER_RAIN`): per atmosgen
  state the share of people out (rain 0.6: past a tenth too many, people walking head in at the
  next door), their pace (rain 1.15), the rain looks (LG2's raincoats, the pool drawn at 0.6 of
  the rainiest state's share), umbrellas (rain 0.6 of the others), a passer-by's chance to
  shelter (rain 0.22), the cars' share, speed (rain 0.88) and added headway (0.45 s); a rain
  state's values reached by atmosgen's rain over its own rain rate, so life follows a change of
  state as the rain does. `CityGenLife.Weather STATE|auto|off`.
- **Umbrellas:** a canopy and a shaft (the engine's basic shapes in `M_CgTransit`) over the
  right shoulder of the near and mid people who hold one, by each person's hash, in ten canopy
  colors, a share with a lit shaft (the city's LED umbrellas); folded under a cover, sitting
  or running.
- **Shelter** (`weather.walk_cover`, `Masks`): each walkway's stretches out of the rain from
  atmosgen's rain shadow (AT5's masks: a cover 2.1 m or more over it), underground or enclosed
  (walk rows' `cover`); in rain a passer-by stops under one by the state's chance and stands at
  the walkway's side facing out for 25 to 140 s, out soon after the rain stops.
- **Nightlife** (`weather.nightlife`): the open bars', clubs' and arcades' people (3, 7 and 2 at
  full busy, LG4's places and M11's POIs) on their door walkways by band (walk rows' `night`),
  on top of M11's density.
- **Reactions:** people standing still near the player (6 m) turn to look at it; a danger
  (`ACityGenLife::Panic`, storygen's hook; `CityGenLife.Panic`, the Tab menu's Scare the crowd
  row) sends everyone within 35 m but the police running away along their walkways (the way
  farthest from it at each turn, signals ignored) at 2.9 times their pace for 14 s, near the
  view on the Game Animation Sample's run (a place clip, retargeted and made in place); after
  it, for 90 s, half of the people within 80 m come back and stand 8 to 20 m off it looking at
  it. Cars stop for the player on foot (no horn: no sound in lifegen).
- **Traffic:** every junction exit tested for room (LG5 tested exits twice a car's length
  only): a short exit (Old Town's 5.8 m lanes between a cluster's junctions) only while empty
  and the lanes after it clear by what the car would stick out; a car waiting for room claims
  nothing and is never forced into the box; a car standing 75 s in a queue past 150 m of the
  view leaves.
- **Every sample city:** the five samples, the pinned, stack and deck demos and Cragmouth
  planned with every check passing; fixed on the way: a gang spot whose ring ran past its
  turf's edge (Vesper Bay's `gang_turf`), a deep metro's concourse 16.2 m over its track
  (Vesper Bay's `transit_stops`: the station's own `track_z_m`), a sky tube terminal nearer its
  track's end than the turn point (Nexus City's `transit_stops`: called at the turn), a media
  flier's orbit grazing a tower between the points it was tested at (Nexus City's
  `air_lanes`: the finished route read back as the check reads it).
- **Checks** (`weather.checks`): `weather`, `shelter`, `nightlife`.
- **Exporter and runtime** (`unreal_life.pack_weather`, `walk_cover`, `walk_night`, `run_clips`,
  `PACK_VERSION` 9; `import_city.weather_props`, `LIFE_VERSION` life10;
  `CityGenLifeWeather.cpp`; the processors; `CityGenPlay`'s Scare the crowd row).
- **Performance pass** (an Unreal Insights trace of the lean route, the controller's steps in
  trace scopes): lifegen's instanced components with fixed bounds (`UCgLifeISM`, the lanes'
  box; `CityGenLife.Bounds` 0 and 2 the engine's and lifegen's own measures), the near
  garments' material instances kept per slot (the garbage collector had purged them), fixed
  skeletal bounds near, fewer ground traces, far cards, far cars and idle models' bodies sent
  less often. The walk's slowest frames are World Partition's instanced HLOD components
  re-sending their instance data as cells stream (2,362 updates in such a frame), not lifegen's
  step (1.7 ms median, 2.7 at the 95th percentile).
- **Delta:** every plan check and the Unreal check pass (Vesper Bay's too, blockout only, in a
  throwaway project); `night_plan_all` 21.8 ms p95 native on the lean route (walk 24.7), 23.0
  under 3.4 cores of other load, against LG7's 22.6: over the 20 ms budget.
