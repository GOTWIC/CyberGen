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

See the spike's report, [`docs/progress/AT0/README.md`](progress/AT0/README.md), for the
measurements and the recommendations for AT1 to AT7.
