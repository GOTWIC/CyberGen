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
