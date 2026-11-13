---
name: atmosgen
description: Turn a city prompt (and optional concept images) into a validated atmosgen atmos_spec.json (the look, the hour and weather, the palette, a mood per district, light levels, landmarks' lights, the sky, the post and grade), check it against the built city, make the atmos plan (every light, the sky, the air, the weather, the look per district) with its checks and previews, import it into an Unreal 5.8 project when asked, shoot it by night, dusk and day, and run art-direction rounds with `atmosgen review`. Use when asked to light, art-direct or revise the night, the weather, the haze or the look of a citygen city with atmosgen, or to write or fix an atmos spec.
---

# atmosgen: prompt to atmos spec

You are the prompt-to-spec step of atmosgen (`docs/atmosgen_scope.md`, section 5). You read
the city's prompt (and images, if any) and its built city, write `atmos_spec.json`, validate
it against the city until it passes, make the plan, look at its previews (and, when asked,
the city in Unreal), run up to three art-direction rounds, and report. Everything after the
spec is deterministic offline code.

## Hard rules

- **No API calls and no network calls.** Do not call any LLM API, web service or URL, and do
  not add `anthropic`, `openai`, HTTP clients or similar to atmosgen. You are the model step.
  You may start subagents or other Claude Code sessions to help, never through an API.
- **Change the spec, never the code.** If validation or a check fails, fix the spec. If you
  believe atmosgen is wrong, say so in the report instead of editing it.
- **Never required.** An empty spec (`{}`) is valid: the `neon_rain` look with every
  district's mood from its archetype, wealth and danger (decision 12.5: clean where wealthy
  and safe, gritty in markets, old towns and poor districts). Write only what the prompt
  decides.
- **Unreal:** only into a throwaway project of the exporter's own (`--new-project`) or the
  project the user names; never into any other project unasked.
- Follow `CLAUDE.md` working preferences (no em dashes, LaTeX for math).

## Inputs

- `cities/<slug>/prompt.md` (the prompt and the citygen session's interpretation),
  `cities/<slug>/city_spec.json` and, if there is one, `cities/<slug>/asset_spec.json`.
- A built city with its assets (`citygen build SPEC OUT --blockout`, `assetgen build OUT`;
  the plan reads assetgen's `signs.json` and street packs where they are, and derives what
  they lack). The names the spec may use:
  ```bash
  .venv/bin/python -c "import json; m=json.load(open('OUT/city_model.json')); \
  print([(d['name'], d['archetype'], (d.get('params') or {}).get('wealth'), \
  (d.get('params') or {}).get('danger')) for d in m['districts']]); \
  print([b['name'] for b in m['buildings'] if b.get('landmark') and b.get('name')])"
  ```
- Concept images, if the user gives any (read them for the light's colors, the haze, the
  wetness and the grade only).

## What the spec decides

| Field | What | Default |
|---|---|---|
| `preset` | the look: `neon_rain`, `clear_night`, `smog_dusk`, `overcast_day` | `neon_rain` (decision 12.4) |
| `hour`, `weather` | the start hour (0 to 24) and weather (`clear`, `drizzle`, `rain`, `fog`, `smog`) | the look's |
| `wind_deg` | where the wind blows to (degrees counterclockwise from east): the rain's lean and its shadow | 40 (from the south-west) |
| `palette.neon`, `palette.temps` | the city's neon colors and weights (`#rrggbb`); light temperatures' weights (`sodium`, `warm`, `neutral`, `cool`, `led_cool`) | AG15's six accents |
| `districts.<name>` | a district's mood: `lamp` (`cobra_head`, `post_top`, `wall_pack`, `high_mast`), `temp`, `spill`, `neon` (0 to 3), `palette`, `flicker`, `broken`, `alleys` (0 lit to 1 dark), `haze` (0 to 3), `grit` (0 clean to 1 gritty), `flood`, `floods`, `searchlights`; AT6: `shadows`, `highlights` (its grade's tints) and `tint` (their strength, 0 to 3) | its archetype's (`atmosgen/presets.py`: `MOOD`, `PALETTES`, `FLOODS`, `DISTRICT_TINT`), pulled by its wealth and danger |
| `light_levels` | `[average, minimum]` lux by class (`sidewalk`, `crosswalk`, `carriageway`, `under_deck`, `alley`), `night_ev100` | scope 8: 10/2, 10/2, 7/1, 5/1, 2/0.5 |
| `landmarks.<name>` | `floods`, `crown`, `edges`, `searchlights`, `color` | by its kind |
| `sky` | `latitude_deg`, `day_of_year`, `moon_phase`, `day_hour`, `moon`, `stars`, `cloud_deck_m`, `cloud_cover`, `cloud_glow` | the look's and `presets.SKY` |
| `post` (AT6) | `bloom`, `flare`, `grain`, `chromatic`, `vignette`, `saturation`, `contrast`, `tint` (multipliers, 0 to 3), `shadows`, `highlights` (the grade's tints), `day_ev_bias` (EV, under 0 brighter), `overcast_comp` (0 to 1: how much of the sun a rainy day's clouds take the exposure gives back), `districts` (false: one post for the city) | the look's (`presets.POST`, `POST_EXPOSURE`) |
| `budgets` | `night_p95_ms`, `live`, `shadowed`, `lights_per_cell` | decision 12.6 |
| `notes` | what you inferred and every judgment call | |

Full schema: `atmosgen spec schema` (or `atmosgen/schemas/atmos_spec.schema.json`).

What the looks are: `neon_rain` a low glowing cloud deck, rain and wet streets, haze in the
canyons, a teal and magenta grade; `clear_night` a clear sky with the moon and stars, dry
streets, a cool and warm grade; `smog_dusk` brown smog at dusk; `overcast_day` a grey day.

## Steps

### 1. Read

Read the prompt twice. List what it says of the light and air: the hour and weather, the
mood of each district (rich or poor, clean or gritty, neon or dark, warm or cold light),
colors it names, the haze, the sky, landmarks lit or not, the feel of the image as a whole
(near-photoreal, filmic, grainy).

### 2. Write the spec

Put it in `cities/<slug>/atmos_spec.json`, starting with
`"$schema": "../../atmosgen/schemas/atmos_spec.schema.json"`. Keep it sparse:

- **The look:** `preset` only when the prompt is not a rainy neon night; `hour` and
  `weather` when it names them.
- **Districts:** one whose mood the prompt sets apart from its archetype (a gritty strip in a
  rich district, a sodium-lit market, a dark residential quarter) gets an entry by its exact
  name in the build: `grit` first (it moves the grain, fringes, flicker, broken lights and
  dark alleys together), then the lamps, the neon and the haze, then its tints.
- **Post:** only where the prompt asks for a grade the look does not have ("bleach bypass",
  "warmer", "less grain"); `day_ev_bias` and `overcast_comp` after looking at the day.
- **Landmarks:** a landmark the prompt says is lit (or dark) by its name.
- **notes:** what you inferred and every default you kept on purpose.

### 3. Validate

```bash
.venv/bin/python -m atmosgen spec validate cities/<slug>/atmos_spec.json --build OUT
```

Fix every error (a district or landmark name the build does not have, a color not
`#rrggbb`, a value out of range). `--filled FILE` writes the spec resolved for the city
(every district's mood).

### 4. Plan

```bash
.venv/bin/python -m atmosgen plan OUT --spec cities/<slug>/atmos_spec.json
.venv/bin/python -m atmosgen lux OUT
```

`atmosgen plan` writes `OUT/atmos/` (`atmos_plan.json`, lights, masks, drips, the sky's glow,
the sight raster, the post's district raster, `atmos_report.txt`) and exits 1 when a check
fails (lux on every walkway and carriageway, lit faces against their walls, the air's
placement, the weather's covers and puddles): a plan that fails is not delivered, so fix
it first (light levels, a district's `alleys`, `broken` or `lamp`). `atmosgen lux` writes the
previews: `preview_lux.png` (the light on the ground round the core), `preview_plan.png`,
`preview_sky.png`, `preview_air.png`, `preview_weather.png` and `preview_post.png` (each
district's post by grit, and its grade on a test chart by night and by day). Read the
report's district moods and post lines: every district should read as the prompt says.

### 5. Unreal (when asked)

```bash
.venv/bin/python -m citygen unreal OUT PROJECT.uproject --atmos OUT/atmos --no-hlod
.venv/bin/python -m citygen unreal OUT PROJECT.uproject --check-only --shots SHOTS \
  --view night_core EX EY EZ TX TY TZ 24 --view dusk_core ... --view pday_core ...
```

Name views `night_*` (the night), `dusk_*` (the plan's dusk), `pday_*` (the day), `t<HHMM>_*`
(an hour); end a name with `__<state>` for a weather state (`__clear`, `__fog`), `_nopost` for
the view without AT6's post, `_noair` without the air. Shoot the same views every round: a
street in each kind of district, one from the air, one by day in rain. In the game the
console's `CityGenAtmos.Post 0|1`, `.PostDistricts 0|1`, `.PostSet KEY VALUE`, `.DayEV EV`,
`.Hour H`, `.Weather NAME now` try a change live before it goes into the spec.

### 6. Art-direction rounds (AT6)

At most three rounds, changing only the spec (never code):

```bash
.venv/bin/python -m atmosgen review OUT --spec cities/<slug>/atmos_spec.json --shots SHOTS
# change the spec, copy OUT/atmos to OUT/atmos_r1, plan again, import, shoot into SHOTS2, then
.venv/bin/python -m atmosgen review OUT --spec cities/<slug>/atmos_spec.json \
  --prev OUT/atmos_r1 --shots SHOTS2 --prev-shots SHOTS
.venv/bin/python -m atmosgen spec diff OLD_SPEC NEW_SPEC
```

`review.md` (in the plan's folder) lists the checks, the city's numbers (lights, the light
on each walkway class, the exposure by night and day, the deck's glow, the air, the weather,
the look's post), each district's (mood, light, post, tints), every shot's exposure as the
eye reads it (stops from middle grey: a night street near -4 to -2.5, a day street near -2
to -1; the share clipped and crushed; the saturation) beside the last round's, a contact
sheet (`review_shots.jpg`, the last round's beside), the previews to open, and a table of
what to change for what you see. Look at the shots against the prompt (and its images),
write down what reads wrong, change the spec, plan again; stop when nothing reads wrong or
after the third round, and say what is still off.

### 7. Report

Report the spec's path, what it sets and why (one line per entry), the validation result, the
plan's checks and counts (lights, volumes, plumes, covers), the post per district, the
rounds and what each changed, the shots, and anything in the prompt the spec could not
express (it goes to the scope's open items).

## Notes for sessions that build atmosgen milestones

These are for sessions changing atmosgen's code, not for the spec loop above:
- The benchmark is the lean route by night (`--bench-atmos`: `night_plan_all` and the passes
  the change touches, one run; decision 12.6); tune by GPU profiles at fixed viewpoints.
- A new controller property set by the importer is named as Unreal's Python names it (a bool
  `bName` is `name`; it must not clash with another property's name).
- Plan files are written only when their bytes change; an unchanged plan imports nothing.
