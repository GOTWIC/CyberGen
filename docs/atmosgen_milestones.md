# Stage 3 milestone log (atmosgen)

The full record of every stage 3 milestone, for the sessions that build and validate them. The
root [README](../README.md) has the short version. Spec: [`atmosgen_scope.md`](atmosgen_scope.md)
(what each milestone adds: section 13; Swagnik's decisions: section 12). Each milestone's entry
grows here as it lands, as in [`citygen_milestones.md`](citygen_milestones.md) and
[`assetgen_milestones.md`](assetgen_milestones.md).

## Milestones

| Milestone | What it adds | Status | Outputs |
|---|---|---|---|
| AT0 | Contract and spike: the atmos spec and presets, the plan schema, the emitter asks of assetgen, the `CityGenAtmos` plugin's skeleton built by the exporter; a spike on Delta at night against AG16's benchmark (lights per tile from a plan against the play features' 192, MegaLights against the tiers, rain, wet streets and volumetric fog, effects from code); a Blender night preview | Done | [`docs/progress/AT0`](progress/AT0) |
| AT1 | Streets at night: street and wall lights by photometric class, shop spill, deck soffits, tunnels and stations; the lux check and map; tile spawners and the live set, replacing the play features' lamps and pools | Planned | |
| AT2 | Neon and signs as light: lit faces replacing the washes, neon spill, floods, aviation lights, searchlights, port and spaceport lighting, flicker and broken lights, district palettes | Planned | |
| AT3 | Sky and time: night, dusk and day skies, the cloud deck, the moon, time of day driving `Hour`, the schedules and the exposure | Planned | |
| AT4 | Air: height and volumetric fog, mist, smog and undercity haze, light shafts, steam and smoke | Planned | |
| AT5 | Weather: rain and its shadow, wetness, puddles, drips, splashes, rings, wind, states and transitions | Planned | |
| AT6 | Looks and art direction: post and grading per look and district, `atmosgen review`, the skill | Planned | |
| AT7 | Far city and release: the skyline at night, budgets on every sample, Unreal checks | Planned | |

## AT0: contract and spike

Built on the Windows PC (2026-11-10), on main after AG16 (#163). Report, measurements and
recommendations: [`docs/progress/AT0/README.md`](progress/AT0/README.md).

- **Decisions** (scope section 12, Swagnik 2026-11-10): a generator of light and air with
  the `CityGenAtmos` plugin and presets; atmosgen takes over the play features' lamps,
  pools, washes, moon and night exposure; data for every hour, night first; `neon_rain` the
  default; no references yet, the look near-photorealistic and clean or gritty by place;
  the night pass at or under 16.7 ms p95 at native 1440p on the PC.
- **Spec and presets** (`atmosgen/spec.py`, `presets.py`): looks, weather states,
  temperatures, photometric classes in physical units, schedules for every hour, tiers,
  budgets; a district's mood from its archetype pulled by danger (grittier) and wealth
  (cleaner): `spec.mood`.
- **Plan schema** (`atmosgen/planmodel.py`, `atmosgen/schemas/`): `atmos_plan.json`,
  `lights/<tile>.json`, `unreal_contribution.atmos.json` (layer 3), with the volumes,
  emitters and masks of AT4 and AT5.
- **Emitter asks** (`atmosgen/emitters.py`, assetgen scope 4.6): a lamp variant's emitter,
  a sign's lit face and emitted color; derived from citygen until assetgen records them.
- **The plan** (`atmosgen plan`): Delta in 6 s, 47,837 lights in 129 tiles (lamps by class at
  their heads, sign faces as rect lights in their sign's color, shopfront spill); `atmosgen
  lux` (the plan's map and its lux map round the core: streets lit, junctions not).
- **Runtime** (`citygen/ue/CityGenAtmos`): the controller (a pooled live set by tier from
  the plan, fog, rain cards, a wet decal, MegaLights, console commands), its materials made
  from code (`citygen/ue/atmos_assets.py`), built by the exporter with CityGenPlay
  (`unreal_play.PLUGINS`); `CityGen.PlayLamps` (0 off, 2 only the far pools) in the play
  features.
- **Benchmark** (`citygen/bench.py`): `--bench-atmos`, `--bench-rt`, `ATMOS_PASSES`,
  commands per pass in `UCityGenBench`; `busy()` sees any other benchmark (a packaged game
  too) and never its own process tree.
- **Spike, Delta at night, native 1440p, p95:** before 12.6 ms; the plan's lights 13.8;
  with volumetric fog 14.7; with rain and wet streets 15.8 (walking 16.2), within the 16.7 ms
  budget. Lights about 1.1 ms (the live set's size hardly matters), fog 0.9 ms, wet streets
  1.6 ms (Lumen's reflections on the glossy ground). Hardware ray tracing costs 2.6 to 2.8 ms
  by itself; MegaLights then saves 1.2 ms and is flat in the light count, but ends at
  17.4 ms: the tiers win on this PC. Effects are C++ components and code-made materials
  (UE 5.8 has no API to author Niagara from code).
- **Blender night preview** (`atmosgen preview`): AG15's night scene lit by the plan in
  Cycles, with haze and wet streets.
- **Tests:** `tests/atmosgen/test_at_plan.py`; `tests/test_bench.py` (the spike's job,
  `busy`), `tests/test_unreal_play.py` (both plugins installed), `tests/test_no_network.py`
  (atmosgen too).
