# AT5: weather (atmosgen)

Stage 3's sixth milestone (`docs/atmosgen_scope.md` sections 6.4 and 13): rain kept out of what
is covered, wet streets and puddles, drips, splashes and rings on the water, the wind, and five
weather states that blend into each other. Built on the Windows PC (RTX 4070 Ti, 32 GB),
2026-11-13, on main after AT4 (#211), the play fixes (#213) and the visible lights (#215).

## What AT5 built

| Part | Where | What |
|---|---|---|
| The rain shadow | `atmosgen/weather.py` (`Weather.covers`) | every cover within 25 m of the ground: M14's deck slabs, M3's masses where they hang over no mass of their own building that reaches up to them (a tower on its podium covers the podium's roof, not the street), skybridges, M6's awnings and bus shelters, canopies, transit decks and cap beams, the raised roads (as the sight raster takes them), road tunnels' lids; each moved downwind by its height times the rain's lean (0.3, at most 3 m: the lee of an awning dry, its windward edge wet) |
| The masks | `masks/<tile>.png` (scope 4.2) | per 256 m tile, 0.5 m texels, RGBA: the cover's underside (the plan's datum and steps: a surface under it is dry, one over it, a deck's or a viaduct's top, wet), the puddles, the drip band, the gloss when wet by surface (asphalt mirrors, paving and sidewalks a little less, soil and grass little, roofs between, the water none) |
| Puddles | `Weather.masks_of`, `presets.PUDDLE` | water stands in the worn spots (a value noise on the plan, 5.5 m and 1.8 m), in the gutter along the curb (the crown sheds the rain to it), at a road's sags (the low points of its grade line: M13's ground plus its own profile) and round AG7's drains (read from the street packs; clogged in gritty districts); the threshold lowered by the district's grit (decision 12.5: the clean Corporate Core few, Old Town and the port many); never under a cover, on a roof, a curb, a raised deck or the water; each as deep as it passes the threshold, so a drizzle fills only the deepest |
| Drips | `drips/<tile>.json`, `planmodel.Drip` | a line under each low cover's dripping edge (an awning's street edge, a deck slab's rim, a raised road's sides, canopies, bus shelters) in 8 m pieces, the edge's height and the ground under it |
| States | `presets.WEATHER`, `WEATHER_LOOK`, `WEATHER_TIMES`, `WIND`; the plan's `weather_plan` | clear, drizzle, rain, fog, smog: each its rain, streak length, share of the drops, wetness, puddle fill, the cloud deck's cover, the fog (the look's, as AT4's air makes it), the fog volumes' gain, the wind and its gusts; the rain's age (a change blends over 20 s; the streets wet over 45 s at full rain and dry over 300 s; the puddles fill over 120 s and drain over 900 s); the wind's heading (the spec's `wind_deg`, from the south-west by default) |
| The weather check | `Weather.check`, the plan's `checks.weather` | every tile's mask; every low cover's middle in its rain shadow (1% may miss by a texel); no puddle under a cover, inside a building or on the water (a bridge's deck excepted); the drips' budget per tile; a plan failing it is not delivered |
| Previews | `atmosgen lux` | `preview_weather.png` (the city: the shadow blue, puddles cyan, drip bands yellow) and `preview_weather_detail.png` (the busiest tile at 0.25 m a pixel with its drip lines) |
| Exporter | `citygen/unreal_atmos.py`, `ue/import_city.py` | packing version 4 (a cell's drip lines); the controller's weather; the masks stitched city-wide at 1 m into two textures (`T_<City>_WetCover` exact grey, `_WetSurface` compressed); `ATMOS_VERSION` atmos6 |
| Runtime | `ue/CityGenAtmos` | the states blended, the rain's age, the wind and gusts into `MPC_CityGenAtmos` and `MPC_CityGen`'s `Wind`; the fog, clouds (and the sun under them by day) and fog volumes by state; the wet streets (two DBuffer decals), the rain cut under the covers and leaning in the wind, splashes, drips; console `.Weather`, `.WeatherSpeed`, `.Wetness` |
| Water and trees | `ue/import_city.py` | rain rings on `M_CgWater` (its tag `.rain2`, rebuilt alone, from nothing: `clear_material`); the trees' crowns swaying in `MPC_CityGen`'s `Wind` built (`M_CgLeaves`, `.wind1`) but off (`LEAF_SWAY`): it cost Midtown's tree-lined street 4.5 ms of GPU a frame (open items) |
| Play features | `ue/CityGenPlay` | the Tab menu's Weather row (the state, `a > b` while it turns; its arrows the previous and the next) in place of AT0's Fog, Rain and Wet streets rows |
| Benchmark | `citygen/bench.py` | every atmos pass sets its weather state at once; `night_plan_drizzle`, `_clear`, `_fogstate`, `_smog` |
| Check | `ue/check_city.py` | the weather by night; `*__<state>` views, `*__<a>2<b>_<n>s` transitions |

## Decisions

- **Wet streets are decals reading the plan's masks, not inputs on the masters** (AT0 recommended
  the masters). A rain shadow per pixel needs the city's own texture, which the shared masters
  cannot hold (every city's materials are the same masters), and rebuilding every master
  recompiles every material of the city. Two decals round the view instead: one darkens (the
  DBuffer's color, black at an opacity, so a surface keeps its own color times one less it and
  the lane markings stay, darker: AT0's decal painted them over), one makes glossy (roughness and
  a world-space normal). One decal cannot do both: the DBuffer's color, normal and roughness
  share one opacity, and a mirror's roughness needs a much higher one than a wet street's
  darkening. The face's normal comes from the depth (the derivatives of the pixel's position),
  so floors, walls and undersides each get their share.
- **The masks reach Unreal city-wide** at 1 m (two textures, 22 MB of video memory with their
  mips for Delta's 4,096 m square) rather than the plan's 0.5 m per tile (89 MB): a puddle's edge
  is drawn finer by a noise in the decal.
- **Splashes come from traces, not the masks**: a trace down from 40 m over a random point near
  the view finds where that drop lands (an awning's top, a deck's, the street), so the splashes
  keep out of what is covered without knowing heights.
- **Effects from code**, as AT4 settled: instanced cards (rain, splashes, drips) and decals.
- **The trees' sway is off.** `M_CgLeaves` with a world position offset (a sway growing with a
  vertex's height in its tree, within 120 m) cost Midtown's tree-lined street 4.5 ms of GPU a
  frame and the Corporate Core 0.8 ms (viewpoint profiles below): Nanite's voxelized leaf cards
  with a world position offset. It is built (`import_city.LEAF_SWAY`) and off.

## The plan on Delta

`atmosgen plan` on the play fixes' Delta build (`neon_rain`, the wind from the south-west): the
lux, faces and air checks as before, and the weather check passes. 16,598 covers (10,965
awnings, 4,160 overhanging masses, 1,106 pieces of raised road, 240 skybridges low enough, 86
bus shelters, 39 transit decks and cap beams, 2 canopies); 3% of the city's texels under a
cover, 2% puddled, 0.5% drip band; 19,997 drip lines (12,135 under awnings, 7,604 along raised
roads), at most 722 in a tile (budget 4,000); 196 masks (4.5 MB). The weather adds 50 s to the
plan (70 s in all), nearly all of it drawing the masks.

| The city: the rain shadow blue, puddles cyan, drip bands yellow | Old Town at 0.25 m a pixel, its drip lines magenta |
|---|---|
| ![](preview_weather.jpg) | ![](preview_weather_detail.jpg) |

Old Town and the Industrial Port, gritty, hold the most water; the Corporate Core and the
Research Campus, clean, least (decision 12.5). The shadows lie a little north-east of every
awning and slab: the rain leans with the wind.

## Unreal

Delta imported over the visible lights' import in CityAG16 (`citygen unreal ... --atmos DIR
--no-hlod`, `CITYGEN_UE_OFFLOAD=500`): the plugins built, atmosgen's assets made again
(version 15), the controller and the 518 cells re-packed, the two masks' textures imported, the
water master rebuilt alone, nothing else touched, about 3 minutes. The check passes (streaming,
collision, the walk, the play features, the sky, the air, and the weather: the rain falling and
the streets wet at the start, 479 splash cards on their spots, 180 drip cards, the textures
set). Shots by the check (`--view NAME__<state>`, 1920 x 1080):

| Rain on an Old Town street | Low along it: puddles mirroring the neon and the lamps, the rain's rings |
|---|---|
| ![](unreal/night_oldtown__rain.jpg) | ![](unreal/night_oldtown_low__rain.jpg) |
| **The street under a viaduct dry, its approach wet with puddles** | **Drips and the dry strip under an Old Town awning** |
| ![](unreal/night_viaduct__rain.jpg) | ![](unreal/night_awning__rain.jpg) |
| **Rain on an Old Town canal** | **A Corporate Core street in rain** |
| ![](unreal/night_canal__rain.jpg) | ![](unreal/night_core__rain.jpg) |

Each state, settled, on the same Old Town street:

| Clear (the deck open: stars) | Drizzle (damp, fine streaks, few puddles) | Rain |
|---|---|---|
| ![](unreal/night_oldtown__clear.jpg) | ![](unreal/night_oldtown__drizzle.jpg) | ![](unreal/night_oldtown__rain.jpg) |
| **Fog** | **Smog** | **Midtown in rain** |
| ![](unreal/night_oldtown__fog.jpg) | ![](unreal/night_oldtown__smog.jpg) | ![](unreal/night_midtown__rain.jpg) |

Transitions (the state changed when the view had streamed in, the shot taken after):

| Clear to rain, 25 s: the rain in, the streets starting to wet | 60 s: wet, the puddles filling | Rain to clear, 30 s: the rain gone, the streets still wet |
|---|---|---|
| ![](unreal/night_oldtown__clear2rain_25s.jpg) | ![](unreal/night_oldtown__clear2rain_60s.jpg) | ![](unreal/night_oldtown__rain2clear_30s.jpg) |

By day (16:00, the overcast takes the sun's direct light in rain):

| Rain by day | Clear by day |
|---|---|
| ![](unreal/pday_oldtown__rain.jpg) | ![](unreal/pday_oldtown__clear.jpg) |

The Tab menu's weather row (its arrows step the state, a click the next):

![](unreal/play_menu.jpg)

## The night's frame time

The lean benchmark once (`--bench-atmos`, decision 12.6; `bench/`): the walk, the drive and the
flight at 2560 x 1440, the walk and the drive by sight. Not flagged: the game held the
foreground, the other processes 0.4 cores. No rerun: every pass is over 0.3 ms under the
budget. **Before** is the visible lights' after (#215, `docs/progress/atmos_visible_lights`:
`night_plan_all` with AT0's rain cards and wet decal).

| Pass | What is on | p95 all | walk | drive | fly | GPU p95 |
|---|---|---|---|---|---|---|
| `night_plan_all` before (#215) | AT0's rain cards and wet decal | 14.9 | 14.6 | 14.9 | 15.1 | 13.3 |
| **`night_plan_all`** | **the rain: streaks, splashes, drips, the wet streets with full puddles and rings, rings on the water, the rain's fog** | **15.1** | **14.8** | **15.0** | **15.3** | **13.2** |
| `night_plan_drizzle` | drizzle: finer streaks, damp streets, a third of the puddles | 14.9 | 15.5 | 14.8 | 14.8 | 13.0 |
| `night_plan_clear` | clear: no rain, the streets dry (the decals hidden), the deck open | 14.5 | 14.9 | 14.4 | 14.6 | 12.8 |

(ms.) **The rain's night is 15.1 ms p95 over the route, 1.6 ms under decision 12.6's 16.7 ms**,
0.2 ms over #215's with AT0's prototypes; against a clear night the rain's effects cost 0.6 ms
over the route (the GPU 0.4). The drizzle's walk was bound by the game thread (its p95 15.1 ms,
the GPU's 13.3): the walk's spread, not the drizzle.

**Viewpoint profiles** (`builds/at5/viewprof.py`: one standalone game at 2560 x 1440 by night,
each view a 3 m walk at 0.5 m/s by sight in each mode; GPU ms, median): the rain with
everything, the same without the rain and the wet streets (dry), and the drizzle. The first
round (a) with the trees' sway off; the second (b) with it on (and the splash cards sent in
batches):

| View | rain (a) | dry (a) | drizzle (a) | rain (b) | dry (b) |
|---|---|---|---|---|---|
| Old Town street | 11.45 | 10.96 | 11.16 | 11.68 | 11.16 |
| Corporate Core street | 12.99 | 12.18 | 12.39 | 13.80 | 13.00 |
| Midtown street (tree-lined) | 13.53 | 12.38 | 12.83 | 18.07 | 16.95 |
| Avenue west through Old Town | 10.94 | 10.25 | 10.65 | 11.22 | 10.60 |
| Old Town canal | 11.02 | 10.49 | 10.79 | 11.11 | 10.67 |

- **The rain and wet streets cost 0.5 to 1.2 ms of GPU** at street level (the two decals over
  the screen, the glossier ground's reflections, the cards); the drizzle about half.
- **The trees' sway cost 4.5 ms** on Midtown's tree-lined street (dry b against dry a) and 0.8
  ms in the Corporate Core: it is off (`LEAF_SWAY`).
- **The splashes' data every frame** hitched the frame (a's canal: frame p95 19.5 ms against a
  GPU's 11.2: the instanced component's render state made again each frame); they are re-traced
  in batches five times a second and their instances updated in place (`MarkRenderInstancesDirty`).
- (These profiles ran before the water master's fix: `M_CgWater` drew the default material;
  the benchmark above ran after it.)

## Validation

- Tests (logged, `-v -rfE --durations=25`): `tests/atmosgen/test_at_weather.py` (new: covers and
  their shadow downwind, the masks' channels, gritty streets holding more water, the drips, the
  states, the check finding a misplaced puddle, the wind from the spec, the plan's record and
  the previews), `tests/atmosgen/test_at_plan.py`, `tests/atmosgen/test_at_air.py`,
  `tests/test_unreal_atmos.py` (the weather on the controller, the textures, the drips' packing,
  a failed weather check not delivered), `tests/test_bench.py` (the weather passes),
  `tests/test_unreal_play.py`, `tests/test_unreal.py` but its Unreal imports.
- Delta's plan again (every check passes), imported over the visible lights' import in
  CityAG16 and checked by night, dusk and day with the views above; the benchmark once.

## Open items

- **The trees' sway is off** (`LEAF_SWAY`): 4.5 ms on a tree-lined street. A sway only near the
  view needs each tree component's world position offset disable distance (the stage 2 actors
  re-placed), or a cheaper sway; AT6 or AT7.
- **Flags:** citygen has no flag props for the wind to move; a flag (or banner cloth) kind is a
  fixture to ask of stages 1 and 2.
- **The masks know one wind:** the rain shadow is moved downwind by the plan's heading and one
  lean; the runtime's gusts and states change the rain's lean but not where the shadow lies.
- **Rain on the water ignores the covers:** the rings in `M_CgWater` fall under a bridge too
  (the water master is shared and cannot read the city's cover texture).
- **Puddles on a flat city** come from the worn-spot noise, the gutters and the drains: Delta's
  roads have no grade-line sags (4 sags in all, on its raised roads). Cragmouth (terrain) would
  show the sags.
- **Day under rain is dark:** the overcast takes 0.75 of the sun's direct light at a rain's
  cover; under a viaduct by day the street is very dark. The day's exposure under an overcast is
  AT6's art direction.
- **A puddle's edge** follows the 1 m texture with a 45 cm noise: at the eye's feet the edge of a
  dry strip under a viaduct reads as a soft, slightly wavy line.
- **The wet decals apply to everything near the ground**, the parked cars and the walker's body
  too (their up-facing parts wet, which reads right in rain).
