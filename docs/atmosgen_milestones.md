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
| AT2 | Neon and signs as light: billboards, banners and holo-boards as lit faces stood off their walls (a faces check), neon spill from neon bands and shop signs, crown floods in AG15's LED accents and uplights, blinking aviation lights, sweeping searchlights, port high masts and crane floods, spaceport apron and pad lights, flicker and dying signs by danger, district palettes and grit; the high tier, beacons and beams in the runtime | Done | [`docs/progress/AT2`](progress/AT2) |
| AT3 | Sky and time: the sun and the moon by latitude, day and phase; the exposure held per hour (night -3 EV100, the day's, dusk between), Night, the sun's light, the sky light and the stars by the sun's elevation; street lights set by the sun; the cloud deck lit from below by the plan's upward light (a glow raster per city); in Unreal a sky dome (sky atmosphere, sun disk, stars, the moon's phase, the deck lit by the sun, the moon and the city), one light as the sun then the moon, and the play features' time-of-day slider replacing their night switch | Done | [`docs/progress/AT3`](progress/AT3) |
| AT4 | Air: the height and volumetric fog of the look by the hour, light shafts by light kind (none from the small many, searchlights keeping AT2's beams), mist over the water at night, smog over industry and the port, haze under decks and in tunnels (thicker where danger is), steam and smoke plumes from manholes and drains (read from AG7's packs), roof units, stalls, vents and chimneys; the air check; in Unreal pooled local fog volumes and instanced plume cards; the engine settings that keep the night in budget; the parked cars' cull distances | Done | [`docs/progress/AT4`](progress/AT4) |
| AT5 | Weather: the rain shadow of every low cover (moved downwind by the rain's lean), masks per tile (cover, puddles, drip band, gloss when wet), puddles in the worn spots, gutters, sags and round the drains (more where grit is), drip lines under the low covers' edges, five states with their rain, wetness, puddles, fog, clouds and wind, the rain's age; the weather check; in Unreal the masks city-wide, two DBuffer decals for wet streets (darker, then glossy, puddles that mirror with the rain's rings, the markings kept), rain cut under the covers and leaning in the wind, splashes where traces from the sky land, drips, rings on the water, the grass and plumes in the wind, blended states and the Tab menu's weather row | Done | [`docs/progress/AT5`](progress/AT5) |
| AT6 | Looks and art direction: a post set per look by night and by day (bloom, lens flares, film grain, chromatic aberration, vignette, sharpening, a teal and magenta grade for neon rain, a black lift, local exposure), a post per district pulled by its grit and tinted by its archetype (the corporate core crisp and cool, old towns, markets and the port gritty), blended in the runtime by where the view stands; the day's exposure measured (a clear day's, moved by the weather's clouds); plumes lit by night and readable far off, a stall's cooking denser; the wet decals' curb sawtooth fixed; `atmosgen review`, `atmosgen spec diff` and the `atmosgen` skill | Done | [`docs/progress/AT6`](progress/AT6) |
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

## AT6: looks and art direction

Built on the Windows PC (2026-11-13), on main after AT5 (#217). Report, measurements and
images: [`docs/progress/AT6/README.md`](progress/AT6/README.md).

- **The look's post** (`atmosgen/look.py`, `planmodel.Post`; `presets.POST`, `POST_KEYS`): per
  look a set by night and one by day (bloom, lens flares and their threshold, film grain,
  chromatic aberration and its start, vignette, sharpening, the grade's saturation and
  contrast, shadow and highlight tints as gains, the highlights' saturation, a black lift,
  local exposure); neon rain teal and magenta by night.
- **A post per district** (`DISTRICT_POST`, `DISTRICT_TINT`): the look's pulled by grit (clean
  crisp, gritty grainy, fringed, flared, lifted) and tinted by archetype; a 32 m district
  raster (`post_districts.png`) the runtime blends them by. Delta: the Corporate Core grain
  0.05 and sharpen 0.6, Old Town and the port grain 0.25 and fringes 0.7.
- **The exposure** (`DAY_EV100`, `POST_EXPOSURE`, `overcast_shift`): held per hour; the day a
  clear day's, measured on Delta (-0.8 EV100 for AT3's 1.6: the day street had read -5 to -7
  stops from middle grey, darker than the night), moved by half the light the weather's
  clouds take; local exposure lifts a viaduct's underside by day.
- **Art direction:** the spec's `post` (multipliers, tints, `day_ev_bias`, `overcast_comp`,
  `districts`) and the districts' `shadows`, `highlights`, `tint`; `atmosgen review` (checks,
  numbers, every shot's exposure in stops, a contact sheet against the last round, levers),
  `atmosgen spec diff`; the skill `atmosgen/skill/SKILL.md` (to be copied into
  `.claude/skills/atmosgen/`).
- **Notes from AT3 to AT5:** the day's exposure (above); the plumes lit by night and kept
  opaque far off, a stall's cooking 6 cards, wider and denser; the curb sawtooth: the wet
  decals' face normal came from coarse (2 x 2 quad) derivatives, so a curb's edge read as
  floor or wall by quads; fine derivatives draw it as one edge.
- **Exporter and runtime** (`docs/unreal_export.md`, "From AT6"): `post_settings`
  (`POST_FLOATS`, 20 a set), no new `ATMOS_VERSION`; `UpdatePost` into the controller's own
  post-process volume (one volume for every district), `OvercastShift`; atmos assets 17;
  console `.Post`, `.PostDistricts`, `.PostSet`, `.DayEV`, `.SteamGlow`; the engine's film
  grains always cooked.
- **A test fixed:** `test_stage2_from_assetgen`'s blockout folder had no city model, so its
  player start (since #215 read from the model) differed from the staged copy's.
- **Benchmark** (the lean route once, AT5's after as the before): Delta's night 15.4 ms p95 over
  the route (AT5 15.1; walk 15.2, drive 15.2, fly 15.8), dusk 15.2, day 13.8; the post 0.15 to
  0.24 ms of GPU at fixed viewpoints.
- **Tests:** `tests/atmosgen/test_at_look.py`; `test_at_sky.py`, `tests/test_bench.py`,
  `tests/test_unreal.py` (cook folders, the stage 2 test).

## AT5: weather

Built on the Windows PC (2026-11-13), on main after AT4 (#211), the play fixes (#213) and the
visible lights (#215). Report, measurements and images:
[`docs/progress/AT5/README.md`](progress/AT5/README.md).

- **The rain shadow** (`atmosgen/weather.py`, `Weather.covers`): every cover within 25 m of
  the ground (deck slabs, M3's masses where they hang over no mass of their own building that
  reaches up to them, skybridges, awnings, bus shelters, canopies, transit decks and cap
  beams, raised roads, tunnel lids), moved downwind by its height times the rain's lean (0.3,
  at most 3 m; the wind's heading the spec's `wind_deg`, 40 by default). Delta: 16,600 covers,
  3% of its texels sheltered.
- **The masks** (`masks/<tile>.png`, 0.5 m, RGBA; `planmodel.Mask`): the cover's underside
  (absolute, the plan's `weather_plan.cover` datum and step), puddles, the drip band, the gloss
  when wet by surface. Delta: 196 tiles, 4.5 MB.
- **Puddles** (`presets.PUDDLE`): a worn-spot noise, the gutter along the curb, a road's sags,
  AG7's drains; the threshold lowered by grit (decision 12.5); never under a cover, on a roof,
  a curb, a deck or the water; the deepest fill first. Delta: 2% of its texels.
- **Drips** (`drips/<tile>.json`, `planmodel.Drip`): the low covers' dripping edges in 8 m
  pieces. Delta: 19,997.
- **States** (`presets.WEATHER`, `WEATHER_LOOK`, `WEATHER_TIMES`, `WIND`; the plan's
  `weather_plan`): clear, drizzle, rain, fog, smog with their rain, streaks, drops, wetness,
  puddles, clouds, fog (the look's), fog volumes' gain, wind and gusts; the rain's age.
- **The weather check** (`checks.weather`): masks, covers in their shadow, puddles in place,
  the drips' budget; a plan failing it is not delivered. `atmosgen lux` writes
  `preview_weather.png` and `preview_weather_detail.png`.
- **Exporter and runtime** (`docs/unreal_export.md`, "From AT5"): packing version 4 (drip
  lines), `ATMOS_VERSION` atmos6, the masks city-wide at 1 m as two textures; the controller's
  states blended over 20 s, the rain's age, the wind into both collections; wet streets as
  two DBuffer decals (`M_CgWetColor`, `M_CgWetGloss`: one decal's color, normal and roughness
  share an opacity, so darkening without painting the markings over and a mirror gloss need
  two); the rain cut under the covers and leaning; splashes where traces from the sky land;
  drips; rain rings on `M_CgWater`; the overcast takes the sun's direct light by day; atmos
  assets 15 (every material rebuilt from nothing, `clear_material`: a rebuild had left half the old nodes and broken `M_CgWater`); the Tab menu's Weather row. **Decision:** the wetness is decals reading the
  plan's masks, not the masters (AT0's recommendation): a per-pixel rain shadow needs the
  city's texture, which the shared masters cannot hold, and rebuilding every master recompiles
  every city material. **The trees' sway** is built but off (`LEAF_SWAY`): 4.5 ms on Midtown's
  tree-lined street.
- **Tests:** `tests/atmosgen/test_at_weather.py`; `tests/test_unreal_atmos.py`,
  `tests/test_bench.py` (the weather passes), `tests/atmosgen/test_at_plan.py`.

## AT4: air

Built on the Windows PC (2026-11-12), on main after AT3 (#207) and the parked cars (#209). Report,
measurements and images: [`docs/progress/AT4/README.md`](progress/AT4/README.md).

- **The fog of the look** (`presets.AIR_LOOK`, the plan's `air`): the weather's height fog times
  the look's density (neon rain 4.4) and falloff (0.4: the haze keeps to the street canyons),
  the volumetric extinction times 3, phase g 0.72, volumetric to 160 m; 1.25 by night, 0.8 by
  day (`fog_hours` from the sky's Night).
- **Light shafts** (`presets.SCATTER`): each light kind's volumetric scattering; none from the
  neon spill, shop signs and shopfronts, none from searchlights. **Decision:** AT2's beam
  meshes stay (400 m into the sky against the volumetric fog's 160 m), brighter in fog
  (`BEAM_FOG_GAIN`).
- **Volumes** (`atmosgen/air.py`, `planmodel.FogVolume`): mist along the canals, basins, rivers
  and channels after dusk, smog over industrial and spaceport districts and their megasites,
  haze under decks and in road tunnels and underpasses; times the district's haze and danger;
  a glow of the city's light. Delta: 169.
- **Emitters** (`planmodel.Emitter`): steam from AG7's manholes and drains read from the street
  packs (road pieces only), M9's vents; exhaust from M3's roof units; cooking from M6's stalls
  and kiosks; smoke from chimneys and stove pipes (the fifth emitter ask); the share by grit.
  Delta: 732.
- **The air check** (`checks.air`): plumes on their sources and out of the masses, volumes over
  their water, district, deck or tunnel, budgets per tile; a plan failing it is not delivered.
- **Exporter and runtime** (`docs/unreal_export.md`, "From AT4"): packing version 3,
  `ATMOS_VERSION` atmos4, the controller's air; pooled local fog volumes (24 nearest), plume
  cards (`M_CgSteam`, atmos assets 12), the engine settings the budget needs (`TunedSettings`:
  volumetric fog froxels 12 px and 96 slices, Lumen reflections at half resolution, the local
  fog volumes' density cap 0.05); the parked cars' cull distances by part.
- **Effects from code**, settled: local fog volume components and instanced cards, no Niagara.
- **Benchmark** (one run after; Swagnik, 2026-11-12: the lean route, one run, the previous
  "after" as the before): Delta's night 15.0 ms p95 over the route (15.2 walking), with AT0's
  rain and wet streets 15.6 (15.8), dusk 14.9, day 11.8; the parked cars had cost 0.6 to 1.9 ms
  (draw calls on the render thread), their cull distances gave it back; the tuned settings 1.5
  ms. The lean route (`--bench-route lean`) is the default for atmos benchmarks.
- **Tests:** `tests/atmosgen/test_at_air.py`; `tests/test_unreal_atmos.py`,
  `tests/test_bench.py` (the air passes, the lean route).

## AT3: sky and time

Built on the Windows PC (2026-11-12), on main after AT2 (#203). Report, measurements and images:
[`docs/progress/AT3/README.md`](progress/AT3/README.md).

- **The sun and the moon** (`atmosgen/sky.py`): the sun's elevation and azimuth by the hour from
  the city's latitude and the sun's declination on the day of the year (Cooper's approximation,
  solar time: the sun culminates at 12); the moon trails it by its phase (`lag_h` 24 times the
  phase, its declination the sun's mirrored by the phase, its light by its lit fraction). Spec
  `sky` (`SkySpec`): latitude (default 35), day of the year (172), moon phase (0.62, a waning
  gibbous up in the east-southeast by 23:00), the day hour (16), and the look's moon, stars and
  cloud deck overridden; `presets.SKY`, each look's `moon`, `stars`, `cloud_deck_m`,
  `cloud_cover`, `cloud_glow`.
- **Curves over the sun's elevation** (`presets.SUN_CURVE`, the same keys in the plan, the
  runtime and the Blender preview): the exposure from the night's held -3 EV100 (the play
  features' night, in Unreal's frame) to the day's (`DAY_EV100` 1.6, less `OVERCAST_EV` times a
  closed deck's cover: neon rain's day 0.8), `Night` (1 under -12 degrees, 0.42 at sunset, 0
  over +10), the sun's light (on to -8 degrees: it lights the twilight sky from under the
  horizon), the sky light and the stars. The plan's lights keep the night's scale,
  $2^{-3 - EV_{ref}}$, at every hour, so at dusk they read dimmer under the brighter exposure.
- **The named hours**: day (16:00), dusk (where the sun stands at -3 degrees in the evening:
  19:28 at 35 north on day 172), night (the look's hour when it is night, else 23); a row per
  hour in the plan (`sky.by_hour`).
- **Schedules the sun sets** (`sky.schedules`): `dusk_dawn` on from the sun at +3 degrees to -3
  (the street lights), `tunnel` 0.6 by day; the lux check and the plan read the plan's own
  schedules.
- **The sky glow** (`sky.glow`): every light's upward flux (a spot's cone above the horizontal,
  half a point's or a vertical face's, `ESCAPE` 0.04 of it leaving the street canyons, and
  `GROUND_REFLECT` 0.12 of the rest bounced with 0.07 leaving) on a 64 m raster, convolved with a
  Lambertian emitter's footprint at the deck's height, $E(r) = \Phi h^2 / (\pi (h^2 + r^2)^2)$,
  shown as `CLOUD_ALBEDO` 0.45 $E / \pi$ times the look's `cloud_glow`; `sky_glow.png` (linear RGB,
  square-root encoded, row 0 the north) and the plan's `sky.glow`. Delta: 13.8 Mlm up, the deck
  0.62 cd/m2 over the core, 0.12 over the city. `atmosgen lux` writes `preview_sky.png`.
- **Exporter** (`docs/unreal_export.md`, "From AT3"): `unreal_atmos.sky_settings` into the
  controller's record and hash, the glow beside the manifest and imported as
  `Atmos/T_<City>_SkyGlow`; `ATMOS_VERSION` atmos3.
- **Runtime** (`ACityGenAtmos::ApplyTime`, `EnsureDome`, `FindLighting`): the importer's
  `lighting.sun` as the sun, then the moon (faded in from the sun at -12 degrees to -16), the
  sky light, the exposure held by the controller's volume (no adaptation pumping), MPC_CityGen's
  `Night` and `Hour`, every light's schedule interpolated between the hours, `TimeSpeed`; the sky
  dome `M_CgSky` (atmos assets version 8): the sky atmosphere and the sun's disk, stars, the moon
  with its phase, maria and halo, the cloud deck met along the view ray at its height, lit by the
  atmosphere's light at the deck and from below by the glow texture, fading into the haze. Console
  `CityGenAtmos.Hour day|dusk|night`, `.Sky`, `.Exposure`, `.TimeSpeed`, `.Cover`.
- **Play features**: day and night are the controller's hours (`SetNamedHour`), the Tab menu's
  time row a slider (`SetTimeOfDay`, `ClickMenuRow("hour=H")`); their own night switch only
  without a controller.
- **Benchmark and check**: passes `dusk_plan(_all)`, `day_plan(_all)`, `night_plan_nosky`;
  `bench.busy` counts a game or a screen recorder (`GAMES`: javaw, ow-obs, obs); the check
  reads the sky by night, dusk and day and renders `dusk_*`, `t<HHMM>_*` and `*_clear` views.
- **Blender**: `atmosgen preview --hour H` at a twilight hour renders a dusk sky
  (`ag6_preview.dusk_world`), the windows at the plan's Night, the lights dimmed by the
  exposure's step.
- **Unreal** (Delta in CityAG16): the import updates the controller and the cells (3 min 14 s);
  the check passes with the sky by night (Night 1, -3 EV100), dusk (19:28, Night 0.81, -1.80
  EV100) and day (16:00, 0.80 EV100, no light live), and night, dusk, blue hour, day and
  clear-sky shots. Found by it: a vector parameter reaches a custom node as its RGB (the sky
  material did not compile: the glow's corners are two parameters), and the first glow washed
  the night out (`ESCAPE` 0.5 and 0.35 to 0.04 and 0.07).
- **The night's frame time** (native 1440p, 3 runs, the median; before: AT2's after benchmark):
  night_native 11.7 to 11.2 ms p95, night_plan 14.3 to 14.4, night_plan_all 16.4 to 16.4 (16.7
  to 16.8 walking, 0.1 over the budget on that route: the sky dome's base pass, about 0.1 ms; an
  open item for AT4), dusk_plan 14.3, day_plan 11.1. The first after benchmark lost the game's
  foreground in two runs with nobody at the desktop; the bench now names the window taking it
  (`lost_to`: the Claude app's) and takes it back (`take_front`).

## AT2: neon and signs as light

Built on the Windows PC (2026-11-11), on main after AT1 (#195) and the packaged game fixes
(#197). Report, measurements and images: [`docs/progress/AT2/README.md`](progress/AT2/README.md).

- **Lit faces** (`plan.signs`): billboards, banners and holo-boards as rect lights the size of
  their face (`sign_face`, `banner_face`, `holo_face`), stood off the drawn face (`out_m` 0.65 m
  past the 0.3 m frame: the light's plane 0.95 m out of the wall, past everything stage 2 hangs
  on a facade, `envelope.OVERHANG_MM` 0.91 m; AT0's light 0.15 m in front flooded its wall), a
  share of the face's luminance as light (`light`: 0.6, 0.35, 0.5) times the page cell's mean
  brightness over `SIGN_LUMA_REF` (within 0.4 to 1.4), in the page's color scaled to full; a
  front holo-board's back (facing its wall) left out; a face whose light on the facade it faces
  passes `OPPOSITE_MAX_LX` 150 lx dimmed to it (at most to 0.15). No specular (AT1's rule).
- **The faces check** (`lux.face_check`, the plan's `checks.faces`): each lit face's light on
  its own wall and on what stands out of it (fronts at 0, 0.45 and 0.9 m, sides at 0.45 m,
  1 m round the face, without barn doors: Unreal's are 20 cm) at most `FACE_WALL_MAX_LX` 1 lx;
  the facade opposite (`lux.opposite`: the first building cell straight out within reach)
  reported. A plan that fails it is not delivered (`atmosgen plan` exits 1, the exporter
  leaves it out).
- **Neon spill:** a neon band or facade shop sign a small spot 0.4 to 0.5 m off the sign, aimed
  out and 35 to 40 degrees down, its cone 76 degrees (`neon_spill`, `shop_neon`); a blade sign
  one point at its middle (`blade_neon`; AT1 two rects); near tier, no specular.
- **Buildings** (`floods`, `aviation`, `searchlights`; `Shape`, `sides`, `corners`): crown
  floods (`crown_flood`) on each side of the crown's box (two past 45 m), 4 m off the facade or
  on the setback under it, below the lit zone (`CROWN_ZONE`: 18% of the height, 8 to 40 m),
  aimed at its upper middle, the cone covering its width, the intensity $I = E d^3 / o$ for
  70 lx there (a grazing light $o$ off the facade), the reach its top; on every landmark, every
  tower AG15 gave crown LEDs (in their accent: `City.ag15` reads assetgen's manifest) and a share
  of the others (`floods`: by archetype, up with wealth, down with grit), never a vacant tower;
  uplights (`facade_flood`) from the podium or the ground on landmarks and some towers. Aviation
  lights on anything 60 m tall over its base (40 m in a spaceport's district or megasite):
  flashing 30 a minute at the top (a thin top's tip, else the roof's corners), a structure's
  together; steady every 90 m under it down to 45 m; near tier. Searchlights on landmarks (by
  kind, `LANDMARK_SEARCHLIGHTS`, or the spec's) and the mood's number on a district's tallest
  towers (else its tallest buildings: a spaceport's control tower), two to a roof, pitched 62
  to 80 degrees, sweeping 22 to 40 degrees over 14 to 26 s.
- **Megasites** (`megasites`): a freight terminal's yard, high masts every 90 m off its stacks
  and buildings, its cranes' two boom floods; a spaceport's apron, high masts along its long
  sides every 80 m and blue edge lights every 30 m, its pads' rims green and white every 6 m,
  each pad flooded from its launch tower. (citygen's spaceports have pads and an apron, no
  runway: these are its airfield lights.)
- **Moods** (`spec.mood`): a palette per archetype (`PALETTES`), the spec's city palette for
  districts without their own; floods' white and share, searchlights (`FLOODS`); grit past 0.3
  mixes a share of a district's lamps to other temperatures and dims some (`MIX_*`); flicker and
  broken by kind (`FLICKER_BY_KIND`, `BROKEN_BY_KIND`), safety and structure lights kept
  (`KEPT_KINDS`), a broken sign dying (a deep flicker, `DYING_DEPTH`) rather than dark.
- **Tiers:** `high` (floods, searchlights, high masts) 48 within 750 m, a pool of its own;
  `near` for aviation lights and the neon spill.
- **The emitter asks:** the second read where met (`SignColors.emit`, `.face`, `faces_of`;
  `Light.source` assetgen), the luminance derived from the page meanwhile; a fourth ask, the
  fixtures of AT2's lights (`roof`, `beacon`, `mast`, `ground` mounts).
- **Exporter and runtime** (`docs/unreal_export.md`, "From AT2"): packing version 2 (19 floats,
  flags bit 6 high and bits 28-29 the animation), `ATMOS_VERSION` atmos2; the controller's high
  pool (`MaxHigh`, `HighRangeM`, searchlights first), blinks and sweeps from the world's time,
  each animated light's live-set fade kept; per cell an instanced red glow per aviation light
  (`M_CgBeacon`) and a cone per searchlight (`M_CgBeam`), shown by night; atmos assets version
  3; `CityGenAtmos.High`, `.Fixtures`; the status and the check's night lines.
- **The plans:** every city passes both checks; Delta 50,304 lights (5,425 lit faces, 13,128
  neon and shop spill, 1,527 floods on 310 crowns, 217 in AG15's accents, 2,201 aviation lights,
  8 searchlights, 29 high masts), no lit face over 0 lx on its own wall, the facade opposite at a
  median 25 lx.
- **Unreal** (Delta in CityAG16): the import re-packs the 500 cells and the controller in under
  2 min; the check passes by night. **The night, native 1440p, p95** (three runs each, before
  AT1's plan, after AT2's): lights 14.0 to 14.3 ms over the route, 14.2 to 14.5 walking, the
  deferred lights pass flat (3.50 to 3.54 ms walking); with AT0's fog, rain and wet street
  prototypes 16.0 to 16.4 over the route and 16.3 to 16.7 walking, at the budget.

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
