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
| AT1 | Streets at night: street and wall lights by photometric class, mast arms and corner poles at the junctions, highway, service road, pedestrian street and alley lights, deck soffits, tunnels and stations, shop spill; the lux check with occlusion and its map, a fill at the dark points; the controller and a data actor per 128 m cell placed by the import with the pooled live set, replacing the play features' lamps and washes | Done | [`docs/progress/AT1`](progress/AT1) |
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

## AT1: streets at night

Built on the Windows PC (2026-11-10), on main after AT0 (#185). Report, measurements and
images: [`docs/progress/AT1/README.md`](progress/AT1/README.md).

- **Photometric classes** (`atmosgen/presets.py` `PHOTOMETRY`): each light's profile is
  Unreal's own, so the plan's check and the runtime agree: a spot's intensity flat to its
  inner cone and falling as $t^2$ to its outer, a point's alike all round, a lit face's by its
  cosine and barn doors, each in the engine's reach window
  $\mathrm{clamp}(1 - (d/R)^4)^2$. Cobra heads 1200 cd to 62 degrees, 80 at most, tilted 15
  degrees over the road (AT0's 6000 cd in 45 degrees: 52 lx under the heads, the carriageway
  between them and the junctions dark); post tops 600 cd; wall packs 420 cd, wide; highway
  columns 2600 cd at 12 m; soffit, tunnel and platform classes.
- **New lights** (`atmosgen/plan.py`): a mast arm on every traffic signal reaching into its
  junction (`signals`); highway and ramp columns every 42 m (a twin arm in a median, else
  staggered at the edges), service roads, posts on footbridges and every 16 m along
  pedestrian streets and promenades, which M6 gives no lamps (`roads`); wall packs along
  alleys, closer where the mood's alleys are lighter (`alleys`); AG10's soffit lights under
  M14's decks at its fixtures (`decks`, AG10's own `_ground_streets` and `_lights`); AG7's
  tunnel wall strips and underpass ceiling strips (`tunnels`); platform downlights in
  elevated and underground stations (`stations`; sky stations are inside their towers,
  AT2).
- **Junctions** (`corners`): a junction whose lane points under 1 lx or crosswalk points under
  2 lx pass 5% gets corner poles one at a time, at the junction ends of its legs' sidewalks
  and its crosswalks' ends (its outline's corners when it has neither), the one leaving
  fewest of its points dark first, at most 6.
- **Fill** (`fill`): a light at the darkest point of each walkway or road (outside the
  junctions) the check still finds dark (3 points under its minimum, or an alley point at
  0), up to 4 rounds: a wall pack over an alley, a post top at a sidewalk's curb, a pole at a
  road's edge. Corner poles and fill lights are never broken.
- **What a light hangs on** (`Light.mount`): the city's own fixture (`prop`, `sign`,
  `facade`, `soffit`, `tunnel`) or one asked of stage 2 (`pole`, `mast_arm`, `wall`,
  `canopy`: `emitters.py`'s third ask, assetgen scope 4.6), counted in the report.
- **The lux check** (`atmosgen/lux.py`, scope 8): every walkway and lane every 2 m by class
  (sidewalks, promenades, pedestrian streets and footbridges `sidewalk`; crosswalks and the
  junctions' crossings `crosswalk`; every road's and junction's lanes `carriageway`; alleys;
  anything on the ground under a deck `under_deck`; park paths reported), on its road's
  surface where the walk graph keeps a raised road's walks on the ground; occlusion against
  the building masses and deck slabs (`Occluders`: a 1 m raster of the lowest bottom and
  highest top over each cell, a footprint taken 0.5 m in so a ray grazing a facade from its
  own fixture stays clear, marched every meter); at 23:00. A class passes on its city
  average, at most 5% under its minimum, no alley point dark, and in each district half its
  average with at most 15% under. The plan's `checks.lux`; `atmosgen plan` exits 1 when it
  fails and the exporter leaves that plan out. `preview_lux.png` with occlusion.
- **Exporter** (`citygen/unreal_atmos.py`, `ue/import_city.py`): layer 3 of the manifest
  (`atmos`: the controller's key and hash, a cell per 128 m cell with its key
  `atmos.lights.<tile>.<quarter>` and hash; the records in `unreal/atmos.json`); the import
  places the `CityGenAtmos` controller (always loaded, the plan's settings) and a
  `CityGenAtmosCell` data actor per cell (spatially loaded, its lights packed, 16 floats and
  2 ints each); `--atmos DIR`, `--no-atmos`. The runtime: a cell registers its lights with
  the controller when it streams in and takes them out when it goes, the controller's pooled
  live set (512 within 300 m, 16 shadowed within 60 m) renders them by night. AT0's
  `-CityGenAtmosPlan` and subsystem are gone; the play features lose AG15's spot lamps and
  sign washes (`play.json` 3) and keep the light pools as the far tier; the check reads the
  controller's status by night; `--bench-atmos` is a flag.
- **Exposure:** the night looks' `reference_ev100` matched to their streets (neon rain 3 to
  1.5, clear night 2.5 to 1.0: a road at $E$ lux shows $0.08 E / \pi$ cd/m2, middle gray at
  $\log_2(8 L)$; AT0's 3 went with its 52 lx), so the runtime's scale shows AT1's physical
  streets as bright as AT0's showed its own, until AT3.
- **Reaches sized for the frame:** the first after run had Delta's deferred light pass at
  5.2 ms walking (AT0 3.0): the live set near a walker full of large-reach spots and posts with
  cube-map shadows. Reaches are what each light needs (cobra 30 m, highway 45, post top 18 and
  never shadowed, wall pack 18, shop spill 12); the live set's screen-coverage proxy is back at
  AT0's and the pass at 3.7 ms; the check, on the same window, places more corner and fill
  lights.
- **The plans** (Delta and the samples, `docs/progress/AT1/README.md`): every city passes;
  Delta 53,559 lights (902 signal mast arms, 662 corner poles, 884 fill lights, 1,036 alley
  packs), carriageways 16.2 lx average with 0.5% under 1 lx, sidewalks 26.6 lx with 1.0% under
  2 lx, junction lanes 1% under 1 lx (AT0's 54%); 5,722 lights on fixtures asked of stage 2.
- **Unreal** (Delta in CityAG16): the import makes the controller and 500 cells in under 3 min;
  the check passes by night (127 lights live of 1,719 registered in 89 cells round the player,
  13 shadowed). **The night, native 1440p, p95** (three runs each, before AT0's plan through
  the command line, after AT1's in the level): lights 14.0 to 14.4 ms over the route, 14.4 to
  14.6 walking; with AT0's fog, rain and wet street prototypes 16.0 to 16.4 over the route,
  within 16.7, and 16.5 to 16.8 walking, 0.1 over (AT4 and AT5's: Lumen's reflections on the
  wet decal, 2.5 ms).
- **No highlight from a lit face's stand-in:** sign, shop sign and shopfront spill lights
  have specular scale 0 (`Light.specular`, `presets.NO_SPECULAR_KINDS`, flag bit 5): glossy
  surfaces reflect the face itself (the play features' washes put a bright ball in nearly every
  billboard); the rule for AT2's sign lights. Delta's night views show no point highlight.
- **The game at the monitor's resolution** (Swagnik): every import sets
  `bAllowHighDPIInGameMode=True` in the project (`unreal.set_project_ini`); Delta's game
  window measured 2560 x 1440 on the 125%-scaled 1440p monitor (2048 x 1152 before). Unreal's
  automatic screen percentage stays.
- **Benchmark:** a game window that lost the foreground ran on the 12700K's efficiency cores
  (its threads twice as slow at the same GPU time); the game is now unthrottled and above normal
  priority (`bench.unthrottle`), each sample records the foreground (`front`).
- **Tests:** `tests/atmosgen/test_at_streets.py` (photometry, the new lights, occlusion, the
  check, corner poles), `tests/test_unreal_atmos.py` (packing, cells, hashes, a failed plan
  left out); `tests/test_unreal_play.py` without the washes.
