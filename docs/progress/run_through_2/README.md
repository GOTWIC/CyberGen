# Second run-through: Delta Megacity in Unreal on main (2026-11-03)

The second walk and flight through Delta Megacity, the first run-through's city
(`docs/run_through_1.md`), on main at f326c95: M17 to M21, the park paths fix and AG12 to
AG15. Each of the first run-through's 17 rows is measured again on the model and the packs
and shot in Unreal 5.8 on the Windows PC (RTX 4070 Ti, 32 GB).

## What was run

- **City:** `citygen build docs/progress/M1a2/delta_megacity/city_spec.json DIR --blockout`
  on main 7f0c243, all 102 checks passing (`C:/Users/swagn/CityGen/builds/RT2/delta`). It was
  not built again: AG15 changed only the Unreal exporter, never the citygen build, so it is
  the same city a build on f326c95 makes. Its layout is the second full-city try (the first
  failed `transit_clearance`, as on M19's main).
- **Assets:** `assetgen build DELTA --workers 2` on f326c95: 10 min 7 s, every check passes
  (buildings, streets, water, props, ground, materials, and AG14's fit checks:
  `asset_grounded` 54,532 things, 6 props reported off their surface, none failing; 1 road
  with a junction step over 2 cm, 0.022 m; `asset_clash` 0).
- **Import:** `citygen unreal DELTA C:/Users/swagn/CityGen/UnrealProjects/CityRunThrough2/
  CityRunThrough2.uproject --new-project --engine C:/Games/UE_5.8`, with the HLOD build.
- **Check:** `citygen unreal ... --check-only --shots DIR --view ...` with 34 views (below).

## The 17 rows

Run-through 1 measured Delta on M15's layout; "now" is this build. The road, bridge and
building numbers are the run-through's own script (`measure_runthrough.py`) on the new
`city_model.json`; the stage 2 ones are AG14's fit report; the transit ones the model's
supports by line (a frame or a cantilever counts once).

### Roads

| Issue | Status | Run-through 1 | Now | Shots |
|---|---|---|---|---|
| Roads that stop at random | Fixed | 308 dead ends, none tagged, 239 inside the map; 206 with a road within 60 m ahead | 158 dead ends (excluding highway exits), every one tagged: 77 local streets at the map edge, 29 cul-de-sacs with their bulbs, 23 path ends, 22 water ends, 7 site gates. 56 with a road within 60 m ahead (37 paths, 16 streets), all tagged: the run-on was turned down there (no junction ahead, or it would cross water, a lot or a park). `road_dead_ends` passes | [cul-de-sac](shots/r1_dead_end_culdesac.jpg) |
| Overlapping roads on straight stretches | Fixed | 149 pairs over 25 m2 outside junctions | 0 pairs; `road_overlaps` passes | [Midtown from the air](shots/r2_overlaps_midtown_aerial.jpg) |
| Intersections with a vertical gap | Fixed in the model and the meshes; one new mesh fault | 78 of 1,580 junctions with a leg at another height at the polygon; AG7's blend missed every leg's height | 74 of 1,526 junctions have such a leg, now all drawn through M18's surfaces (50 junctions with a surface, `junction_levels` passes); AG14: 1 road of 3,367 legs steps over 2 cm (0.022 m at `jn.w251n1343`), none over 0.15 m. But the five-leg raised junction `jn.e217s328` (11.4 m between its legs) shows sidewalk and median strips crossing its carriageway (new issue 3) | [raised X](shots/r3_raised_junction_x.jpg), [raised multi](shots/r3_raised_junction_multi.jpg) |
| Roads going into buildings | Fixed | in the meshes only (parts and fronts over the road) | `road_building_clash` passes; AG14's `asset_clash`: 0 road carriageways in a mass, 0 building vertices over a lane under 4.5 m | [core street](shots/r4_core_street_buildings.jpg), [core street](shots/a1_core_street_day.jpg) |
| Trees poking through raised roads | Fixed | 114 plants reaching a raised road's deck | 0 (the script); 124 embankments (6.2 km) under low raised stretches, no plant on them; `plant_headroom` passes | [under a viaduct](shots/r5_trees_under_viaduct.jpg), [embankment](shots/r5_embankment.jpg) |
| Shallow ramps leave dead space | Fixed (Delta has no highway ramps) | ramps and runs 5% (6% at most), approaches 5.5% | bridge approaches up to 7% (85, median 6.96%), local streets up to a raised junction 8%, the two viaduct runs 6%; `ramp_grades` passes. Delta's layout has no interchange ramps to measure | [sea bridge](shots/r6_ramp_sea_bridge.jpg), [river bridge](shots/r6_ramp_river_bridge.jpg) |

### Structures and obstacles

| Issue | Status | Run-through 1 | Now | Shots |
|---|---|---|---|---|
| Overlapping bridges | Fixed | 0 in the model; drawn twice in the meshes | 30 bridges (15 road, 15 pedestrian), 0 pairs over each other in plan; AG14 `bridge_twice` 0 (a bridge carried by its road's segments draws no deck of its own); `bridge_clash` passes | [river bridges](shots/s1_bridges_river.jpg) |
| Floating railings by the river | Fixed | railings at the quay deck's 1.5 m over a ground-level pavement | railings at z 0 on the paving (M20); AG14 reports no railing off its surface | [quay](shots/s2_quay_railings.jpg) |
| AC units floating over roofs | Fixed | AG1's placeholder blocks | 11,481 AC units among 15,476 roof items; AG14 `asset_grounded` fails none (roof items and dunnage all on the roof the shell built) | [Old Town roofs](shots/s3_roofs_oldtown.jpg), [Midtown roofs](shots/s3_roofs_midtown.jpg) |
| Sky tubes and trains through buildings and platforms | Fixed | 22 tube pieces through towers with portals | 1 portal, at a station (`d02.lot.e1060n1114.bld`); AG14 `transit_through_building` 0, `transit_through_platform` 0; `transit_clearance` passes | [portal tower](shots/s4_sky_tube_portal.jpg), [core sky station](shots/s4_sky_station_core.jpg) |
| Supports not under the line | Fixed | monorail 53 of 94 columns over 2 m off the beam (to 13.5 m); sky tube pylons to 13 m off | every lone column within 0.01 m of its line; the rest are frames (15) and cantilever bents (27) whose beams carry the deck (`transit_supports` passes) | [monorail frame](shots/s5_monorail_frame.jpg), [sky tube mast](shots/s5_sky_tube_mast.jpg) |
| Uneven support spacing, long gaps over water | Fixed | gaps to 971 m (sky tube), 531 m (monorail), 270 m (maglev) | monorail 93 supports (36 columns, 25 piers, 11 frames, 21 cantilevers), gaps median 25 m, longest 62 m (a cable span); maglev 53, median 50 m, longest 168 m (truss spans); Delta Loop 13 (10 masts), longest 472 m; Skyline Loop 6, longest 511 m between supports plus its portal tower | [monorail over the water](shots/s6_spacing_monorail_water.jpg), [sky tubes](shots/s6_spacing_sky_tubes.jpg) |
| Train lines too close to the roads | Fixed | 5.5 m over a road deck; rail 10 to 16 m, monorail 12 to 22 m | monorail 19 to 21.6 m, maglev 31 m, sky tubes 92.5 to 110 m; `transit_clearance` (8 m over roads, 6.5 m over raised decks) passes | [monorail frame over a street](shots/s5_monorail_frame.jpg) |

### Aesthetics

| Issue | Status | Run-through 1 | Now | Shots |
|---|---|---|---|---|
| Buildings look the same, lit alike at night | Fixed | prisms on podiums, grids of windows, one night look | 21 tower forms (34 twist, 29 exo, 29 stack, 28 oval, 13 round, ...); 359 towers, 1,402 neighbor pairs within 150 m, 0 sharing a system, pattern, palette or night look (`asset_unique`); each building's own night schedule and light color | [core by day](shots/a1_core_day.jpg), [core by night](shots/night_a1_core.jpg), [window patterns](shots/a1_mixed_windows_midtown.jpg) |
| Too few large billboards and holo-boards | Fixed | 252 facade billboards, 63 holo-ads (roof only) | 2,750 facade billboards (10.9 times) and 939 banners; 201 holo-boards (3.2 times: 112 over roofs, 89 in front of facades); 963 lit roof billboards | [Midtown avenue](shots/a2_billboards_midtown_avenue.jpg), [holo-board](shots/a2_holo_front.jpg), [core](shots/a2_billboards_core_wide.jpg), [core by night](shots/night_a2_billboards_core_wide.jpg) |
| Curved buildings look low-poly | Fixed | 12 to 32-gons, flat normals | true arcs (no chord over 1 cm off), the curve's normals in the packs (kept by the importer), glazed joint to joint | [round tower](shots/a3_curved_round_tower.jpg), [twisted tower](shots/a3_curved_twist_tower.jpg) |
| Streets black at night | Fixed in this PR | lamps lit nothing on the ground | AG15's spot lights, light pools and sign washes drew nothing at all in Unreal (new issue 1): the play actor is an `AInfo`, hidden in the game, so its components never render. Fixed (`SetHidden(false)`); then the first values blew out under the night's exposure, so they are now a quarter (below). 191 lamps lit and 768 pools around the view | [core street](shots/night_a4_core_street.jpg), [Midtown](shots/night_a4_midtown_street.jpg), [Old Town canal](shots/night_a4_oldtown_canal.jpg), [Industrial Port](shots/night_a4_player_start_street.jpg), [from above](shots/play_free_cam_night.jpg); before the fix: [core street](shots/before_fix_night_a4_core_street.jpg), [from above](shots/before_fix_play_free_cam_night.jpg) |
| A crosswalk and signals at every junction | Fixed | Old Town 117 of 1,137 junctions signalized; 116 of 358 junctions with crosswalks within 40 m of another; every crosswalk 4 m | Old Town 19 of 1,085 signalized; 156 of 1,526 junctions in the city; 162 junctions with crosswalks, 0 within 40 m of another; widths 3 m (244), 4 m (202), 5 m (105); `crossing_spacing` passes | [Old Town from the air](shots/a5_crosswalks_oldtown.jpg), [raised X with signals](shots/r3_raised_junction_x.jpg) |

## The Unreal check

The final check (`--check-only`, play views only, on the project with the Nanite fix):

- streaming: 30,875 of 73,293 actors loaded at the start, 41,858 after a teleport across
  the city (26,302 new). Passes.
- collision: 486 of 507 traces down hit, 35 of 36 facades, **31 of 36 roofs**: fails the
  check's 90% for roofs. The five missed are all Industrial Port sheds and yards near the
  player start (`d05.lot.w222s330.bld`, `w259s291`, `w372s375`, `w200s121`, `w277s90`:
  AG5's open types whose only collision hull is their roof slab or canopy). New issue 4.
- walk: 158 m along a 160 m sidewalk, 100% of frames on the ground, frames 0.014 s
  (median), 0.024 s (95%). Passes.
- console cheats (ghost, fly, walk): pass.
- play features: map, menu, night (191 lamps lit, 8 with shadows, 768 light pools), free
  camera and back, a 1,932 m teleport onto the ground. Pass.
- flight: the fly pawn at 50 m/s flew 418 m in 8.4 s, 44,562 actors loaded where it ended,
  frames 0.030 s (median), 0.066 s (95%). Passes.

Times on the Windows PC:

| Step | Time |
|---|---|
| `assetgen build` (2 workers) | 10 min 7 s |
| Plugin build (CityGenPlay, VS 2022) | 50 s the first time, 14 to 16 s after a change |
| First import, try 1 | 29 min 50 s, then out of memory at 61,000 of 73,293 actors (below) |
| First import, try 2 (`CITYGEN_UE_OFFLOAD=500`) | 12 min 18 s (the 13,293 actors left; meshes kept) and the HLOD build 6 min 5 s (231 HLOD actors): 18 min 33 s |
| Import again, nothing changed | 9 min (5 min 15 s of it the HLOD builder finding nothing to build) |
| Check with play views (33 views) | 35 min (the walk's part 30 min: 26 day and night views from the free camera) |

Shots: editor views at 3840 x 2160 and play-world views at 1920 x 1080, here at 1600 px
(`shots/`); full size in `C:/Users/swagn/CityGen/builds/RT2/shots*`.

## New issues

1. **The lamps, light pools and sign washes drew nothing** (fixed here). AG15's lights
   are components of the `CityGenPlay` actor, an `AInfo`, which is hidden in the game; a
   hidden actor's components are not rendered. The check's status said 191 lamps lit, the
   lights were at the right places pointing down at 6,000 cd, and the street was as dark at
   20 times their candelas. `ACityGenPlay` now calls `SetHidden(false)` in its constructor.
2. **Delta's first Play crashed on Nanite root pages** (fixed here): "Cannot allocate more
   root pages 49152/49152. Pool resource has grown to maximum size of 2048MB. 512MB is spent
   on streaming data". AG15's parts brought Delta to 53,790 distinct Nanite meshes; the
   1,500 m view range around the player start loads more than 49,152. Pressing Play in this
   project would have quit the editor. The importer now sets
   `r.Nanite.Streaming.StreamingPoolSize=256` in `[SystemSettings]` for a city of more than
   42,000 Nanite meshes (57,344 root pages); the walk, the play features and the flight
   then run. The check's own editor views (up to 42,000 meshes, whose root pages stay)
   still overrun it before the walk, hence `CITYGEN_UE_PLAY_SHOTS_ONLY=1` and the play views.
3. **A raised five-leg junction draws strips across its carriageway**: `jn.e217s328`
   (Research Campus side of the river bridges, legs 11.4 m apart in height) shows thin
   sidewalk and median strips crossing the junction surface and a triangle of sidewalk on
   it ([shot](shots/r3_raised_junction_multi.jpg)). The fit checks do not see it (no
   carriageway step, no clash). AG7's junction piece or its sidewalk corners on a junction
   whose legs climb through it.
4. **Five Industrial Port sheds and yards have no roof the check's traces hit** (above);
   the check fails on 31 of 36 roofs. Likely the hulls of AG5's open types (roof slab only),
   or the check's points missing a canopy; not looked into.
5. **The import ran out of memory** on the PC: try 1 stopped at 61,000 of 73,293 actors,
   "Ran out of memory ... The paging file is too small" (`import_log.txt`), with the editor
   at about 20 GB and 0.8 GB free. `CITYGEN_UE_OFFLOAD=500` (actors saved and unloaded every
   500, not 2,000) imported the rest on the same project.
6. **Sign washes and pools by night**: at the first values the washes painted whole
   facades in their neon color and the pools merged into white sheets seen from above;
   now a quarter. The street lamps light only the sidewalks near them; the carriageway
   between stays dark (a 30 m reach, 78 degree cones).

## Changes in this PR

- `citygen/ue/CityGenPlay` (plugin): `SetHidden(false)`; `StreetLampCandela` 1,500,
  `WallLampCandela` 400, `WashCandela` 600 (were 6,000, 1,500, 1,500).
- `citygen/ue/import_city.py`: `PoolStrength` 1.0 (was 2.5), `LIGHT_POOL_VERSION` 2.
- `citygen/unreal.py`: `set_engine_ini` (from `set_startup_map`), `nanite_meshes`,
  `set_nanite_pool` (`NANITE_MANY` 42,000, `NANITE_POOL_MB` 256), called after every import;
  the import result gains `nanite_meshes` and `nanite_pool_changed`. Test
  `test_nanite_pool`.
- `citygen/ue/check_city.py`: `--view`s named `pday_*` and `night_*` are rendered from the
  free camera in the play world, by day and by night (the city streamed in around each,
  1920 x 1080 HighResShot); `CITYGEN_UE_PLAY_SHOTS_ONLY=1` leaves out the editor views;
  `CITYGEN_UE_LAMP_DEBUG=1` and `CITYGEN_UE_LAMP_SCALES` for tuning the lamps.
- `docs/unreal_export.md`: the lamps' values, the fix, the Nanite pool, the offload.

## How to open and play

1. Close any Unreal editor open on this project. Open
   `C:\Users\swagn\CityGen\UnrealProjects\CityRunThrough2\CityRunThrough2.uproject`:
   double-click it, or start `C:\Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe` and
   pick it under Recent Projects. Add the project folder and `C:\Games\UE_5.8` to Windows
   Security's exclusions first if you can: Defender otherwise scans each of the level's
   files as it opens.
2. The editor opens on **DeltaMegacity** (`/Game/CityGen/DeltaMegacity/Maps/DeltaMegacity`,
   the project's startup and default map). In the editor it loads nothing until you play
   (World Partition).
3. **Play** (Alt+P, or the green Play button). The first Play takes minutes: every cell
   within 1.5 km of the player loads first, and Windows may say "Not Responding"
   meanwhile. You start flying at the player start (Industrial Port, near the river).
4. **Flying** (the default): W A S D or the arrow keys move, the mouse looks, E or Space
   rises, Q or C sinks, 50 m/s. Shift+F1 frees the mouse, Esc stops playing. To walk with the
   First Person character instead: World Settings, GameMode Override: None.
5. **Keys:**
   - **M**: the map, the whole city with district names; the wheel zooms, the right button
     drags, the left button teleports you there; M or Esc closes it.
   - **.** (period): the free camera, W A S D, E or Space up, Q or C down, the wheel sets
     its speed; `.` again goes back to the player.
   - **Tab**: the developer menu: Time of day (Day or Night), free camera, minimap, engine
     messages; click a row; Tab or Esc closes it.
   - The minimap is top left at all times.
6. **Console** (the `` ` `` key in the play window): `CityGen.Night 1` (or `0`, or no
   argument to toggle), `CityGen.Map`, `CityGen.FreeCam`, `CityGen.Menu`,
   `CityGen.Teleport X Y` (citygen meters, e.g. `CityGen.Teleport 1050 180` for the
   corporate core), `CityGen.Status`.
7. By night the lamps nearest you light the sidewalks, the pools mark the lamps beyond them,
   and the large signs nearest you wash their facades. The lamp values are on the
   `CityGenPlay` actor in the level (Outliner, CityGen folder): `StreetLampCandela`,
   `WallLampCandela`, `WashCandela`, `NightExposureEV100`.

The check exercised every one of these through the actor's functions (`set_night`,
`set_map_open`, `set_dev_menu_open`, `set_free_cam`, `teleport_player_to_citygen`,
`get_status`); the keys and console commands are the plugin's (`CityGenPlayActor.cpp`,
`docs/unreal_export.md`, "Play features") and were not pressed by hand.
