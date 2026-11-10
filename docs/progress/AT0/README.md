# AT0: contract and spike (atmosgen)

Stage 3's first milestone (`docs/atmosgen_scope.md` section 13): the contract (spec, presets,
plan schema, the emitter asks of assetgen, the `CityGenAtmos` plugin's skeleton built by the
exporter) and a spike on Delta Megacity at night against AG16's benchmark. Swagnik's
decisions of 2026-11-10 (section 12) set the frame: a generator of light and air with a
runtime plugin; atmosgen takes over the play features' lights; data for every hour, night
first; `neon_rain` the default look; near-photorealistic, clean or gritty by place; the
night pass at or under 16.7 ms p95 at native 1440p on the PC.

## What AT0 built

| Part | Where | What |
|---|---|---|
| Atmos spec and presets | `atmosgen/spec.py`, `presets.py`, `schemas/atmos_spec.schema.json` | looks (`neon_rain`, `clear_night`, `smog_dusk`, `overcast_day`), weather states, temperatures, photometric classes in physical units, schedules for every hour, tiers, budgets; district moods from archetype, wealth and danger |
| Plan schema | `atmosgen/planmodel.py`, `schemas/atmos_plan.schema.json`, `tile_lights.schema.json`, `contribution.schema.json` | `atmos_plan.json`, `lights/<tile>.json`, `unreal_contribution.atmos.json` (layer 3), volumes, emitters and masks set for AT4 and AT5 |
| Emitter asks of assetgen | `atmosgen/emitters.py`, assetgen scope 4.6 | a lamp variant's emitter (class, lens, normal, size); a sign's lit face and emitted color; derived from citygen until met |
| The plan | `atmosgen plan BUILD`, `plan.py` | lamps by class at their heads, sign faces as rect lights in their sign's color, shopfront spill, schedule, flicker and broken lights by mood |
| Previews | `atmosgen lux`, `atmosgen preview` | the plan's map, its lux map round the core, a Blender night render lit by the plan |
| Runtime plugin | `citygen/ue/CityGenAtmos`, `citygen/ue/atmos_assets.py`, `citygen/unreal_atmos.py` | the controller (lights by tile, a live set by tier, fog, rain, wet streets, MegaLights), its materials made from code; built by the exporter with CityGenPlay |
| Benchmark | `citygen/bench.py` (`--bench-atmos`, `--bench-rt`, `ATMOS_PASSES`), `UCityGenBench` | the spike's passes, console commands per pass, a waiting rule that sees any other benchmark |

## The plan on Delta

`atmosgen plan` on AG16's Delta build, an empty spec (`neon_rain`, 23:00): 47,837 lights in
129 tiles in 6 s, at most 1,731 in a tile (budget 6,000).

| Kind | Lights | Class |
|---|---|---|
| street lights | 3,277 | cobra heads (6,000 cd peak, tilted 15 degrees over the carriageway); post tops on pedestrian streets and in residential heights and campuses |
| wall lights | 1,117 | wall packs |
| sign faces | 5,953 | billboards, banners, neon bands and holo-boards as rect lights their size, in their sign's color (a shop cell's own, else the mean of the ad's bright pixels) |
| shop sign faces | 19,984 | small rect lights, near tier only (blade signs both faces) |
| shopfront spill | 17,506 | a rect light per unit, by use (bars magenta, cyberware and clinics cyan) and its hours |

District moods (decision 12.5): the Corporate Core clean (cool white cobra heads, grit 0, no
flicker, nothing broken); Old Town and the Industrial Port gritty (sodium, grit 0.96 and 1.0,
a third of the lights flickering, 12% broken).

The lux map round the Corporate Core (`wip/01_plan/preview_lux.png`, no occlusion): the
streets are lit between the lamps (carriageway lane points average 52 lx, sidewalks 46 lx,
both over their 7 and 10 lx targets: the cobra heads can come down), but the junctions are
not: 54% of their connector lanes' points fall under 1 lx and 25% of the crosswalks' under
2 lx, since M6 keeps the lamps off the junctions. AT1 has to light them (signal mast arms,
corner lights), and its lux check would have failed this plan.

## The spike: Delta at night in Unreal

**Setup.** Delta Megacity as AG16 left it (`C:/Users/swagn/CityGen/builds/ag16/delta_megacity`,
imported into the CityAG16 project by AG16's final exporter; the build predates #159's water
pieces, which touch no light), on the Windows PC (RTX 4070 Ti, 32 GB), AG16's benchmark
route (three sidewalk walks in Old Town, Midtown and the Corporate Core, a 1.2 km drive, a
flight at 150 m, a teleport) in a standalone game at 2560 x 1440, native (decision 12.6),
three runs each, the median. The atmos plan is read by the `CityGenAtmos` controller in the
game (`-CityGenAtmosPlan`); each pass switches it by console commands (`bench.ATMOS_PASSES`).
The PC ran nothing else heavy (each run's `others` under 1.2 cores, all of it the desktop).

**Before** (`bench/before`, no atmosgen in the game): night, native 1440p, p95 of the
moving frames **12.6 ms** (walk 12.8, drive 11.9, fly 12.6), AG16's figure.

**After** (`bench/after`, one game process per run, every pass on the same route):

| Pass | What is on | p95 all | walk | drive | fly | GPU p95 | over the baseline |
|---|---|---|---|---|---|---|---|
| `night_native` | the play features' night (192 spot lamps, 8 shadowed, 768 light pools, 32 sign washes) | 12.7 | 12.8 | 12.0 | 12.6 | 11.1 | |
| `night_plan` | the plan's lights: 512 live within 300 m, 16 shadowed within 60 m, the play features' pools past 300 m | 13.8 | 14.2 | 11.9 | 12.5 | 12.5 | +1.1 (walk +1.4) |
| `night_plan_fog` | + exponential height fog with volumetric fog (200 m) | 14.7 | 15.1 | 12.8 | 13.0 | 13.5 | +2.0 (walk +2.3) |
| `night_plan_all` | + rain (4,000 lit streak cards) and wet streets (a DBuffer decal) | **15.8** | **16.2** | 14.1 | 13.4 | 14.7 | **+3.1 (walk +3.4)** |
| `night_plan_256` | all, 256 live within 250 m, 8 shadowed | 15.7 | 16.1 | 14.0 | 13.3 | 14.5 | +3.0 |
| `night_plan_1024` | all, 1,024 live within 400 m | 16.1 | 16.5 | 14.1 | 14.1 | 14.9 | +3.4 |

(ms; the spread of the three runs' p95 within 0.2 ms everywhere; no frame over 100 ms in a
pass with atmosgen on but one walk's; loads unchanged.) Every pass stays under 16.7 ms p95,
the budget of decision 12.6, walking too, but walking with everything on leaves 0.5 ms.

**Where the time goes** (the GPU's passes, walking, ms a frame: `bench.json`'s
`gpu_passes_ms`):

| GPU pass | `night_native` | `night_plan` | `night_plan_fog` | `night_plan_all` |
|---|---|---|---|---|
| Lights (deferred direct lighting) | 1.93 | 3.01 | 3.01 | 2.64 |
| Lumen reflections | 0.68 | 0.89 | 0.89 | **2.47** |
| Volumetric fog | 0 | 0 | 0.90 | 0.83 |
| Shadow depths | 1.14 | 1.26 | 1.27 | 1.30 |
| Nanite base pass | 0.75 | 0.92 | 0.92 | 0.93 |

- **The lights** cost about 1.1 ms of deferred lighting for 512 live (most of them rect
  lights: the signs' faces and shopfronts), and the live set's size hardly matters: 256 to
  1,024 live moves the frame 0.4 ms. The game thread pays nothing measurable: the live set's
  update takes 0.2 to 1.1 ms every 0.2 s (7 ms the first time it fills its pools), and the
  game thread's p95 fell (10.3 to 9.2 ms: the play features' 768 decals and their sort went).
- **Volumetric fog** costs 0.9 ms with every live light scattering in it.
- **Wet streets** cost 1.6 ms, nearly all of it in Lumen's reflections: the decal makes the
  ground glossy (roughness 0 to 0.3), so Lumen traces reflections across every pixel of
  street; the decal itself and the rain's 4,000 cards are below the profile's resolution.

**What it looks like** (`bench/after/shots`, the last run's view at each segment's start,
the same views in every pass): at street level the plan lights the city as its fixtures
would; the Corporate Core's plaza lit cool white, Old Town's street sodium with magenta and
green neon spilling from its shopfronts and signs onto wet cobbles that mirror them, rain
falling through the light. The README pairs (`street_old_town_*.jpg`, `street_core_*.jpg`,
2560 px) set each street's `night_native` beside its `night_plan_all`. Three things to fix,
each for its milestone:

- **Junctions stay dark** (left of the Corporate Core shot), as the lux map said: AT1.
- **A neon band floods its own wall** (Old Town's green sign): a rect light flush against
  its wall lights the wall at its full luminance; AT2's sign lights need a standoff or a
  barn door aimed off the wall, and less of a band's luminance as light.
- **The wet decal paints over** lane markings and reads as blotches on big paved yards from
  the air (puddles by noise, not by the low spots): AT5's wetness belongs in the masters
  (`MPC_CityGenAtmos`'s `Wetness` read by the road and paving masters, markings kept), its
  puddles from the grade lines.

From the air the plan's lights reach 300 m round the camera; past that the play features'
light pools keep the far streets reading lit (`CityGen.PlayLamps 2`, added after the smoke
run showed the far city dark without them). The far tier proper (light cards and the
HLODs' emissive, scope 6.6) is AT7's; the pools are a stopgap that costs nothing measurable.
