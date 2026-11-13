# atmosgen: light, sky, air and weather (scope, v2: decided 2026-11-10, AT0 to AT5 done)

Stage 3 (atmosgen) of CyberGen's five stages. It takes a built city with its assets and
makes the city's light and air: every light source that casts light, the sky, fog, smog,
steam, rain and wet streets, time of day and the post-processing look. All of it goes into
Unreal through the shared exporter (`docs/unreal_export.md`). Like stages 1 and 2 it is
city-agnostic, offline and deterministic. Its milestones carry the prefix AT (AT0 to AT7,
section 13). It starts after AG16 (performance), whose benchmark is its baseline. The
decisions Swagnik took before AT0 are in section 12.

```
 citygen build  ──>  city_model.json          assetgen build  ──>  assets/ (manifest,
        │                                              │             emitter points, signs.json)
        └──────────────────────┬───────────────────────┘
                               v
 [atmosgen plan, offline deterministic Python]
        ├──> light plan per tile (every light: kind, position, aim, photometry, color,
        │     schedule, tier), keyed by the id of what it hangs on
        ├──> air and weather plan (fog and smog volumes, steam and smoke emitters, rain
        │     shadow, wetness and puddle masks, wind)
        ├──> sky and time (sky glow from the plan's upward light, moon, cloud deck,
        │     the hour schedules of lights)
        └──> look (grading, bloom, exposure, per-district moods), from the atmos spec
        │
        ├──> checks (light on every walkway, budgets per cell, nothing lit inside a mesh)
        ├──> previews (a lux map, Blender night renders)
        └──> Unreal exporter: layer 3 of the manifest, and the CityGenAtmos runtime
             plugin that renders it (lights by tile, time, weather, effects, post)

 atmos_spec.json (a look preset plus art direction per district, written by a Claude
 Code session through an `atmosgen` skill from the city prompt; no API call)
```

## 1. Goal

A dense neon city at night: wet streets that mirror signs in magenta, cyan and amber; haze
that catches every light; towers whose crowns and edges are lit, their windows each lit in
its own pattern; a low cloud deck glowing orange and violet from the city under it; steam
from manholes and vents; alleys dark between bright shopfronts; the undercity under the
decks in its own sodium and fluorescent light. Also the same city by day, at dusk, in smog
and in clear weather, from the same data.

Done, as the user sees it: walk any street at night and it reads lit by its lamps, shops
and signs, not by a global fill; fly over it and the skyline glitters to the horizon under
a glowing sky; change the hour and the weather and everything follows (lights by their
hours, wetness by the rain, fog by the weather).

## 2. What atmosgen is

**A generator, but of light and air, not of geometry.** It keeps the contract of the other
stages (a spec in, a deterministic plan out keyed by M10's stable ids, checks, previews, a
layer of the manifest, district regeneration by hash). It differs in where its value
lands: most of what it makes is data the engine renders at runtime, not meshes. So it has
three parts:

| Part | What it is | Per city? | Where it lives |
|---|---|---|---|
| The plan | where every light, fog volume, steam vent, rain shadow and puddle goes, with its parameters and schedule | yes, generated from the city | `atmosgen/`, written to `BUILD/atmos/` |
| The runtime | a C++ runtime plugin, `CityGenAtmos`, that renders a plan: lights spawned per tile as their cells stream in, the live set near the view, time of day, weather, the effects, the post volumes; plus the materials and material parameters the importer makes | no, shared by every city (as assetgen's texture library and masters are) | `citygen/ue/CityGenAtmos` beside `CityGenPlay`, built and copied by the exporter |
| The looks | named presets (neon rain, clear night, smog dusk, overcast day) and per-district moods | chosen per city in the atmos spec | `atmosgen/presets.py`, `atmos_spec.json` |

Options weighed:

- **A look pack in the exporter only.** That is what the play features do today for the
  lamps, pools and washes (section 3): every lamp head in one always-loaded actor, the 192
  nearest lit, candelas set by eye. It made the streets read at night, but it cannot be
  checked or previewed without Unreal, it knows a lamp only as a point, and its tuning
  is the same everywhere. Kept only as the stopgap it is.
- **More assetgen milestones** (the night is partly materials). AG15 did the surfaces;
  light transport, weather, sky and time are not asset work. Rejected, with the line in 4.3.
- **A generator of light and air** (this scope). The placement problem is large and
  city-specific: tens of thousands of lights (Delta alone has 2,750 facade billboards, 939
  banners and 201 holo-boards since M20, plus every lamp and shopfront), each where its
  fixture is, and the air shaped by water, decks, industry and danger. Done offline it can
  be checked (light on every walkway, as a lighting engineer would) and previewed, and it
  regenerates with its district.

## 3. Where it starts (main, 2026-11-04)

What stage 3 inherits, and what the second run-through found by night
(`docs/progress/run_through_2/`, Delta on the Windows PC):

| Already there | From | State |
|---|---|---|
| `MPC_CityGen` with `Night`, `Hour` and `Wind` | AG6, AG15, AG13 | the switch, the hour and the wind every master reads; nothing drives them over time |
| Every building's own night: a schedule by use and hour band, lit share, light color, vacant towers, crown and edge LEDs, logos, media facades | AG15 | done, in the glass master by `Hour`; atmosgen drives the hour |
| Glowing surfaces: neon, LED strips, sign faces, holo-ads, lamp lenses | AG8, AG15, M20 | done, emissive by `Night` |
| A night switch: the sun as a dim moon (3%), the sky light down, the exposure held at -3 EV100, `NightHour` 21 | play features (`CityGenPlay`) | a developer's day or night toggle, no dusk or hours between |
| Street and wall lamps as light: a spot light 45 cm under each of the 192 lamps nearest the view (8 shadowed), light-pool decals under 768 more | AG15 in the play features | **not finished:** the lamps light only the sidewalks near them and the carriageway between stays dark (30 m reach, straight down, 78 degree cones); one actor holds the whole city's lamps |
| Sign washes: a point light 1.5 m before each of the 32 nearest large signs, in its neon color | AG15 in the play features | **not finished:** at first they painted whole facades in their color; now at a quarter, still a point light, not a lit face |
| Water with Single Layer Water (`M_CgWater`), grass swaying by `Wind` | AG12, AG13 | done; no rain, ripples or mist on them |
| No fog, haze, clouds, rain, wetness, steam, sky glow, grading | | atmosgen's |

The lamps and the sign washes stay in AT1 and AT2 as full milestones: what is there is a
first pass to replace, not a part done.

## 4. How it fits

### 4.1 Inputs it reads (read only, as assetgen reads citygen)

- **citygen model:** props (`street_light`, `wall_light`, signals, kiosks, stalls,
  `vending_machine`), M11's and M20's sign slots (kind, size, facing, audience), points of
  interest (`hours`), wealth, danger and police fields, densities per hour band
  (`HOUR_BANDS`), M14's decks (soffits, light wells), M9's tunnels and vents, M5's stations
  and guideways, M16's water (depth, flow, exposure), banks and ground cover, M13's ground,
  megasites (port, spaceport), landmarks, skybridges.
- **assetgen outputs:** the manifest and contributions (pivots, ids, materials); emitter
  points: each lamp variant's head and lens (today the prototype's `prop_light` part, which
  the play features place by the instance's transform), each sign asset's lit face and
  colors (`signs.json`), AG10's soffit lights, AG7's tunnel lights; each building's night
  record (AG15: schedule, light color, crown lights); the surfaces that take wetness;
  drains and manholes (AG7), roof vents (AG4).
- **atmos spec:** the preset and art direction (section 5).

What it needs and the others do not yet record goes into asks, as assetgen's section 4.5
does: a lamp's photometric class by variant (cobra head, post top, wall pack, high mast)
and each sign's lit face as a rectangle, not a point. AT0 set them down
(`atmosgen/emitters.py`): AG8's variant record gains `emitter` (class, lens point, normal
and size in the variant's frame) and `signs.json`'s slot record gains `face` (middle,
normal, size, two-sided) and its cell `emit` (color, nits). Until assetgen writes them the
plan derives both from citygen (M6's prototype lamp head, M20's slot with the prototype's
frame, the cell's own color or the mean of its bright pixels on the page), and every light
says which (`Light.source`, the plan's `sources`). AT2 reads the second ask where it is met
and derives a sign's luminance from its page cell's brightness until then; it adds a fourth
ask, the fixtures of its own lights (`roof`, `beacon`, `mast`, `ground`: assetgen scope 4.6).

### 4.2 Outputs and the exporter

- `BUILD/atmos/`: `atmos_plan.json` (canonical JSON, a hash per entry), `lights/<tile>.json`
  (lights by tier; the Blender previews read these directly: glTF's `KHR_lights_punctual`
  has no area light, and the signs and shopfronts are rect lights, so AT0 drops the planned
  `lights/<tile>.glb`),
  `masks/<tile>.png` (rain shadow, wetness, puddles, at 0.5 m), `atmos_report.json/.txt`,
  `preview_lux.png`, `unreal_contribution.atmos.json`. An unchanged rebuild writes no file;
  a district regeneration changes only its district's and seam's entries.
- **Layer 3 of the manifest:** new keys for lights, volumes and emitters
  (`light.<prop id>`, `fog.<water id>`, `steam.<manhole id>`), and entries that replace
  M15's default `lighting.sun`, `lighting.sky` and `lighting.atmosphere` by key, as the
  manifest's layering already allows.
- **The runtime plugin** (`CityGenAtmos`): C++, as the play features are, because Unreal's
  Python cannot write Blueprint or effect graphs. The exporter copies it into the project
  and builds it with UnrealBuildTool as it does `CityGenPlay`. It holds the tile light
  spawners (a tile's lights load and unload with its World Partition cell, not one actor
  for the city), the live set near the view by tier, the time and weather controller
  driving `MPC_CityGen` (`Night`, `Hour`, `Wind`, and new `Wetness`, `Rain`, `FogDensity`),
  the effects and the post volumes. The play features keep input, map, menu and free
  camera; their lamps, pools, washes, moon and exposure move to atmosgen, and their menu's
  day or night row becomes a time-of-day slider and a weather row (the exporter's "Plan for
  more" already says so).
- **Effects without hand-made assets:** the repo makes every Unreal asset from code, and
  Niagara systems are graphs. Rain, splashes, drips and steam are therefore C++ components
  and materials (instanced streak and splash cards, ripple and wetness inputs on the
  masters, local fog volumes for steam), unless AT0 finds a way to build Niagara systems
  from code that holds up. AT0 found none: UE 5.8 exposes no API to author a Niagara
  emitter from code (only an engine template could be duplicated and fed user parameters),
  so effects are C++ components and code-made materials (AT0's rain cards and wet decal,
  `docs/progress/AT0/`). AT4 settled it for the air: the fog volumes are the engine's local
  fog volume components, pooled by the controller, and the steam and smoke plumes instanced
  cards in a code-made material (`M_CgSteam`) rising by world position offset; no Niagara.

### 4.3 The line with assetgen

| assetgen owns (surfaces) | atmosgen owns (light and air) |
|---|---|
| What glows and how it looks: emissive windows and their schedules (AG15), neon tubes, LED strips, logos, sign faces, holo-ads, lamp lenses | Every light that casts light: street and wall lights, shop spill, sign and billboard wash, facade uplights, crown floods, aviation lights, searchlights |
| Materials that can be wet (a wetness input in the masters), puddle-ready road surfaces | How wet, where: rain shadow, wetness, puddles, drips |
| Water surfaces (AG12), grass that sways (AG13) | The wind, rain, ripples and mist over them |
| The masters' `Night`, `Hour` and `Wind` inputs | Driving them: time of day, the night gain, schedules, weather |

AG15 kept to the surfaces; its lamps, pools and washes went into the play features as a
stopgap, and the exporter's doc already hands them to stage 3. Decision 12.2 confirms it.

### 4.4 Later stages

- **lifegen:** vehicle head and tail lights, flying vehicles' lights, train and tram
  lights, people under umbrellas in rain. atmosgen gives it the weather and the hour.
- **storygen:** per-scene overrides of the look (a preset, the hour, the weather) through
  the same controller.

## 5. The atmos spec

Written from the city prompt by a Claude Code session (an `atmosgen` skill, as the other
stages have); never required to edit. Fields, all with defaults:

- `preset`: `neon_rain` (default), `clear_night`, `smog_dusk`, `overcast_day`, or a
  custom one; `hour` (default 23) and `weather` (rain, drizzle, fog, smog, clear) as the
  start state.
- `palette`: the city's neon colors and their weights; light color temperatures (sodium,
  warm, neutral, cool LED, mixed), agreeing with AG15's building light colors.
- `districts[]`: a mood per district (palette, haze, neon density, flicker, how dark the
  alleys are), defaulting from archetype, wealth and danger: wealthy and corporate cool
  white with lit crowns; markets and old towns warm with dense neon; poor districts sodium,
  mixed, flickering; ports sodium high masts; the undercity fluorescent.
- `light_levels`: illuminance targets by walkway class (section 8), the night exposure.
- `landmarks[]`: floods, crown and edge lighting, searchlights by landmark.

## 6. Feature catalog

### 6.1 Lights

- **Street and wall lights:** a light per lamp head at its lens, outside the head's mesh,
  with a photometric profile per lamp style (a cobra head throws across the carriageway, a
  post top round itself, a wall pack down the wall, a high mast over a yard), its reach and
  spacing such that the carriageway between lamps is lit too; color by district mood
  (sodium, LED). Light pools only where a lamp is beyond the live set.
- **Shop spill:** a rect light per lit storefront facing out across the sidewalk, color
  from the shop's use, by its hours (M11).
- **Signs as light** (AT1's rule for every light standing in for a lit face, a sign's or a
  shopfront's: no specular highlight, the glossy surfaces reflect the face itself; a point
  light before a billboard put a bright ball in it):
  a billboard, banner or holo-board lights what it faces as a lit
  face would (a rect light the size of its face, its color from the sign page, falling off
  over the street and the facade opposite), not a point that floods its own wall; neon
  bands and shop signs as small colored lights near; some flicker, some broken, more where
  danger is high.
- **Buildings at night:** facade uplights, crown and edge floods on towers and landmarks
  (casting what AG15's crown LEDs show), aviation warning lights (blinking red) above a
  height, lobby glow.
- **Structures:** deck soffit lights (AG10's points), tunnel and underpass lights, station
  and platform lights, guideway underlights, bridge cable lights.
- **Megasites:** port high masts, spaceport runway and apron lights, searchlights.
- **Tiers:** near (shadowed), mid (unshadowed), far (no light: emissive points or light
  cards). The tier is the plan's; how many of each the runtime keeps live near the view is
  set from the budgets (section 9).
- **Visible lights** (Swagnik, 2026-11-12, after walking the packaged Delta): round a
  walker the live set is the lights the walker sees, not a circle: every light within
  `sight_m` (1,200 m, four times the mid tier's radius) that a line of sight reaches, at the
  light or where its light lands, through the plan's sight raster (`atmosgen/sight.py`: the
  lux check's occluders on 2 m cells, every rounding toward seeing), each pool at its size
  (the street's `sight_max`, the high tier's `high_max`), shadows for the nearest seen; lights
  near but out of sight leave the set, far ones in sight join it, each fading in and out. The
  fly pawn and the free camera keep the circle. Docs: `docs/unreal_export.md`, "Visible
  lights"; results `docs/progress/atmos_visible_lights/`.

### 6.2 Sky and time

- Night sky with a moon and few stars; a low cloud deck lit from below by the city, its
  glow from the plan's upward light flux per area (bright over the core and the port);
  dusk and day skies for the other presets.
- Time of day: sun and moon, the night gain, `Hour` moving through the day so AG15's
  window schedules and every light's schedule follow (offices dark late, bars open, shops
  closing), the exposure by hour.
- AT3 built it (`atmosgen/sky.py`, `docs/progress/AT3/`): the sun and the moon from the
  latitude, the day of the year and the moon's phase; curves over the sun's elevation for the
  exposure (held: the night at -3 EV100 in Unreal's frame, the day's, dusk between), `Night`,
  the sun's light, the sky light and the stars; the street lights' schedule set by the sun;
  the deck's glow as a raster of the plan's upward flux on its underside; in Unreal one
  directional light as the sun and then the moon, a sky dome material (the sky atmosphere,
  stars, the moon with its phase, the deck lit by the sun, the moon and the city), the
  exposure held per hour, and the play features' time-of-day slider.

### 6.3 Air

- Height fog and volumetric fog per preset; light shafts from strong lights through haze.
- Fog and smog volumes: mist over canals and rivers at night (M16 water), smog over
  industry and the port, haze under decks (M14), haze in tunnels, thicker where danger is.
- Emitters: steam from manholes and drains (AG7), roof vents and exhausts (AG4), food
  stalls (M6), tunnel ventilation buildings (M9); smoke from chimneys.
- AT4 built it (`atmosgen/air.py`, `docs/progress/AT4/`): the plan's `air` (the height and
  volumetric fog of the look and weather by the hour, thicker by night; each light kind's
  volumetric scattering, the light shafts: the street lights, high masts and floods, none from
  the many small neon and shop lights; the live sets; the engine settings the night's budget
  needs), `volumes` (ellipsoids: mist along the canals, basins and rivers after dusk, smog over
  the industrial and spaceport districts and their megasites, haze under the decks and in the
  road tunnels and underpasses, each times its district's haze and danger) and `emitters`
  (steam from AG7's manholes and drains read from the street packs, M9's vents, exhaust from
  M3's roof mechanical units, cooking from M6's food stalls and kiosks, smoke from chimneys on
  industrial roofs and stove pipes on shanty stacks, a fixture asked of stage 2; the share
  that steams by the district's grit), and the air check (scope 8). In Unreal the nearest
  volumes are local fog volumes, the plumes rising cards in `M_CgSteam`; the searchlights keep
  AT2's beams (brighter in fog), their spot lights scattering none.

### 6.4 Weather

- Rain and drizzle kept out of what is covered: a rain shadow raster per tile from decks,
  skybridges, awnings, arcades, overhangs and tunnels.
- Wetness from the rain shadow and the rain's age; puddles in low spots of the streets (the
  grade lines, the road crown, near drains), drips at slab edges and awnings, splashes,
  rings on AG12's water.
- Wind for the rain's angle, steam, flags, AG13's grass and the trees.
- Weather states and their transitions (clear, drizzle, rain, fog, smog).
- AT5 built it (`atmosgen/weather.py`, `docs/progress/AT5/`): the rain shadow of every cover
  within 25 m of the ground (deck slabs, overhanging masses, skybridges, awnings, bus
  shelters, canopies, transit decks, raised roads, tunnel lids) moved downwind by its height
  times the rain's lean; masks per tile (`masks/<tile>.png`, 0.5 m: the cover's underside,
  puddles, the drip band, the gloss when wet by surface), the puddles from a worn-spot noise,
  the gutters along the curbs, the roads' sags and AG7's drains, more where grit is; drip lines
  under the low covers' edges (`drips/<tile>.json`); the five states (rain, streaks, puddles,
  wetness, clouds, fog, fog volumes, wind and gusts) and the rain's age; the weather check
  (scope 8). In Unreal the masks city-wide as two textures, the wet streets as two DBuffer
  decals (darker, then glossy with puddles that mirror and the rain's rings in them, the
  markings kept), the rain cut under the covers and leaning in the wind, splashes where a
  trace from the sky lands, drips along the drip lines, rings on the water, the trees and the
  grass in the wind, and the states blending into each other (the Tab menu's weather row).

### 6.5 Look

- Exposure locked per preset and hour (no pumping at night), bloom, lens flares, a little
  grain and chromatic aberration, a grading table per preset (teal and magenta for neon
  rain), a post volume per district for its mood.

### 6.6 Far city

- The skyline at night: HLODs that keep their emissive, far lights as light cards from the
  plan, the cloud glow. The far city must glitter, not go gray.

## 7. Outputs (canonical)

As in 4.2. Every plan entry carries the id of what it belongs to, its tile and the hash of
its inputs.

## 8. Checks (every run; a failure means the plan is not delivered)

- **Light on the walkways and carriageways** at night, computed from the plan with a simple
  occlusion test against the building masses:

  $$E(p) = \sum_i \frac{I_i(\gamma_i)\,\cos\theta_i}{d_i^2}\,V_i(p)$$

  where $I_i(\gamma)$ is light $i$'s intensity toward $p$ (candela), $\theta_i$ the angle
  of incidence on the ground, $d_i$ the distance and $V_i \in \{0, 1\}$ whether the light
  sees $p$. Targets by class (defaults, set in the spec): main sidewalks and crosswalks an
  average of 10 lx and a minimum of 2 lx; carriageways 7 lx; under decks 5 lx; alleys
  allowed as dark as 0.5 lx, never 0. The lux map is also a preview. (This is the check the
  run-through's dark carriageways would have failed before Unreal.) AT1 set how a class
  passes: its average over the city at its target, at most 5% of its points under its
  minimum (broken lights and the dark stretches a gritty mood asks for), no alley point at
  0, and in every district at least half the average with at most 15% under the minimum
  (`atmosgen/lux.py`, `presets.UNDER_MIN_SHARE` and its neighbors); park paths are reported,
  not judged.
- **Budgets:** live and shadowed lights per 256 m cell and within the view range; volume
  and emitter counts per cell; the night's frame time against AG16's benchmark.
- **Placement:** every light outside the meshes of its fixture and of every building; every
  steam emitter on its manhole or vent; every fog volume over its water or district.
- **Coverage:** every lamp, sign face, storefront and soffit point with its light (or a
  reason it has none), every schedule from a use, every district with a mood.

## 9. Unreal, hardware and performance

- **Where it runs:** Unreal checks and the look's sign-off on the Windows PC (RTX 4070 Ti,
  32 GB, decision 13.4 of the assetgen scope), as the second run-through did; the runtime
  plugin builds there with Visual Studio 2022 as `CityGenPlay` does. The Mac builds the
  plan, runs the checks and the Blender previews; its editor renders with Nanite off and
  big cities overrun Nanite's root pages there.
- **Baseline:** AG16's benchmark (`citygen unreal ... --bench`: a fixed route by day and by
  night, frame times p50, p95 and p99, hitches, GPU and VRAM) before AT0 and after every
  AT milestone (since AT4 the lean route, one run: decision 12.6). AG16's proposed targets for Delta at 1440p are 16.7 ms p50 and 25 ms p95
  walking; atmosgen's lights, shadows, fog and volumetrics live within what is left.
- **Many lights:** a night city wants thousands of lights near the view. MegaLights (if it
  is production-ready in 5.8) or the tiers of 6.1, measured in AT0: MegaLights is still
  experimental in 5.8 and needs hardware ray tracing, which costs Delta 2.6 to 2.8 ms by
  itself; MegaLights then saves 1.2 ms over the tiers and is flat in the light count, but
  the tiers without ray tracing are faster (15.8 against 17.4 ms p95 with everything on)
  and only they keep the 16.7 ms budget. The tiers it is: 512 live within 300 m, 16
  shadowed within 60 m (`docs/progress/AT0/README.md`). On foot since the visible lights:
  the 512 the walker sees within 1,200 m (6.1), picked by a line of sight through the plan's
  sight raster, swept on a worker thread every 0.2 s (`docs/progress/atmos_visible_lights/`).
- **Blender:** night previews with Cycles' light tree (many lights) from the plan's glTF
  lights, over AG15's night materials, at 4K for review and 8K for the README.

## 10. Determinism and scale

As stages 1 and 2: blake2b draws from ids, integer or grid-snapped geometry, numpy
elementwise only, canonical JSON. A city's plan holds tens of thousands of lights, well
under a megabyte per tile. The plan stage should take minutes; the illuminance check is
the costly part (a raster per tile, lights culled by range).

## 11. Out of scope

Sound (rain, traffic, crowd ambience); vehicles and crowds and their lights (lifegen);
story lighting (storygen); seasons and snow; interiors (AG11).

## 12. Decisions (Swagnik, 2026-11-10)

All six were answered on 2026-11-10, before AT0.

1. **The shape:** a generator of light and air (section 2), with the `CityGenAtmos` runtime
   plugin and presets. Decided as recommended.
2. **The play features' lights:** atmosgen takes over the lamps, light pools, sign washes,
   moon and night exposure from `CityGenPlay` (AT1 to AT3), which keeps input, map, menu
   and free camera. Decided as recommended. (AT0: the console variable `CityGen.PlayLamps`
   turns the play features' lamps, pools and washes off while the plan's lights are on.)
3. **Time:** the data for every hour from AT0, art direction on night first. Decided as
   recommended (the plan's schedules hold 24 values each).
4. **Weather:** rain and wet streets as the default look (`neon_rain`), with clear, fog and
   smog as states. Decided as recommended.
5. **References:** none yet; Swagnik may add some later. The look: near-photorealistic
   cyberpunk and futurism, clean or gritty by place: a clean corporate core; gritty
   markets, old towns and poor districts. Driven by each district's archetype, wealth and
   danger (`spec.mood`: grit, flicker, broken lights and dark alleys pulled up by danger and
   down by wealth from the archetype's mood in `presets.MOOD`).
6. **The night's frame budget:** the night pass stays at or under 16.7 ms p95 at native
   1440p on the PC, by AG16's benchmark (Delta's night was 12.6 ms p95 after AG16, so about
   4 ms for atmosgen), run by night after every AT milestone. How (Swagnik, 2026-11-12: the
   benchmarks were too slow): the lean route (`--bench-route lean`, the default with
   `--bench-atmos`: one walk, the drive, the flight, no teleport, a short warm-up), only the
   worst condition (`night_plan_all`) and the passes the change touches (`dusk_plan` only
   where the change differs by dusk), one run (a second only when the result is within
   0.3 ms of 16.7 ms or the run was flagged: the foreground lost, the CPU starved), no
   "before" run (the previous milestone's "after" is it); tuning by quick GPU profiles at
   fixed viewpoints, not route runs.

## 13. Milestones

| | Milestone | Adds | Needs |
|---|---|---|---|
| AT0 | Contract and spike | atmos spec and presets, plan schema, the emitter asks of assetgen; the `CityGenAtmos` plugin's skeleton; a spike on Delta's core at night on the PC, against AG16's benchmark: lights per tile from a plan against the play features' nearest 192, MegaLights or tiers, rain, wet streets and volumetric fog prototyped, effects built from code or not; a Blender night preview | AG16 |
| AT1 | Streets at night | street and wall lights by photometric class (carriageways lit between lamps), shop spill, deck soffits, tunnels and stations; the lux check and map; tile spawners and the live set, replacing the play features' lamps and pools | AT0 |
| AT2 | Neon and signs as light | billboards, banners and holo-boards lighting what they face as lit faces, replacing the play features' washes; neon spill, facade and crown floods, aviation lights, searchlights, port and spaceport lighting, flicker and broken lights; district palettes | AT1 |
| AT3 | Sky and time | night, dusk and day skies, the cloud deck lit by the city, the moon; time of day driving `Hour`, every light's schedule and the exposure, replacing the play features' moon and night switch (the menu's time-of-day slider) | AT1 |
| AT4 | Air | height and volumetric fog, mist, smog and undercity haze volumes, light shafts, steam and smoke emitters | AT3 |
| AT5 | Weather | rain and its shadow, wetness, puddles, drips, splashes and rings on the water, wind, weather states and transitions (the menu's weather row) | AT4 |
| AT6 | Looks and art direction | post and grading per preset and district, `atmosgen review`, the `atmosgen` skill (prompt to atmos spec) | AT2 to AT5 |
| AT7 | Far city and release | the skyline at night (HLOD emissive, light cards, cloud glow), budgets on every sample, Unreal checks on the PC, README | AT6 |

Each milestone updates the exporter and the plugin in its own PR and runs AG16's benchmark
by night after it (the lean route, `night_plan_all` and the passes it touches, one run, the
previous milestone's "after" as its before: decision 12.6), as stages 1 and 2 update the
exporter. AT2 and AT3 can run side by side after
AT1.
