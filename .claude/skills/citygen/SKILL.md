---
name: citygen
description: Turn a city prompt (and an optional concept image) into a validated citygen city_spec.json, render its schematic, and report. Use when asked to make, generate, design or revise a city or city layout with citygen, or to write or fix a city spec.
---

# citygen: prompt (+ image) to city spec

You are the prompt-to-spec step of citygen (`docs/citygen_scope.md`, section 4.1). You read the
prompt (and the image, if any), write `city_spec.json`, validate it until it passes, render the
schematic, look at it, and report. Everything after the spec is deterministic offline code.

## Hard rules

- **No API calls and no network calls.** Do not call any LLM API, web service or URL, and do not
  add `anthropic`, `openai`, HTTP clients or similar to citygen. You are the model step. You may
  start subagents or other Claude Code sessions to help (for example one per city, or a reviewer
  that compares the schematic with the prompt), but never through an API.
- **Change the spec, never the code.** If validation fails, fix the spec. If you believe citygen
  itself is wrong, say so in the report instead of editing it.
- Names come from the prompt or the image. Do not copy third-party trademarks or franchise names
  (for example Cyberpunk 2077 corporations); rename or drop them and say so in `source.notes`.
- Follow `CLAUDE.md` working preferences (no em dashes, LaTeX for math).

## Setup (once per machine or cloud session)

Skip this if `.venv/` already exists. Installing packages is a one-time developer setup, not
part of the spec step; citygen itself never touches the network.

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Run citygen as `.venv/bin/python -m citygen ...` (below written as `citygen ...`). Installing
with `pip install -e .` also gives a `citygen` command.

## Files

Put each city in `cities/<slug>/` (slug: lowercase, underscores), unless the user names another
place:

- `prompt.md`: the prompt verbatim, the image path if any, and your interpretation (a short list
  of what you inferred and every default you chose on purpose).
- `city_spec.json`: the spec.
- `schematic.png`: the rendered schematic.

Start the spec with `"$schema": "<relative path to>/citygen/schemas/city_spec.schema.json"` so
editors can check it. Full schema: `citygen spec schema` (or that file).

## Steps

### 1. Read the inputs

- Read the prompt twice. List every district, water feature, transit line, megasite, landmark,
  named place and bridge it mentions, plus moods (grime, neon, greenery) and scale words.
- If there is an image, look at it (the Read tool shows images; for `.webp` convert first:
  `.venv/bin/python -c "from PIL import Image; Image.open('in.webp').convert('RGB').save('/tmp/x.png')"`,
  using your scratchpad for the output). Read it for **layout hints only**, see section 4 below.

### 2. Write the spec

Water first, then districts, then transit. Keep it sparse: leave out what the prompt does not
decide and let the presets fill it (`citygen spec validate --filled out.json` shows the result).

**City.** `name`; `seed` (any integer, keep it stable across revisions); `size_km` default
`[3, 3]`, aim for 6 to 12 km² total ($w \cdot h$). Words like "megacity" or "sprawling" mean
the top of that range (about 3.5 x 3.5); go beyond 12 km² only when the prompt gives a size.
Put the prompt in `source.prompt`, the image path in `source.image`, and judgment calls in
`source.notes`.

**Water** (`water`):
- `coast.form`: `bay`, `peninsula`, `delta`, `archipelago`, `crescent` or `straight`;
  `coast.side`: compass side where the open sea is (`north` ... `north_west`). Optional `name`
  and `sea_share` (fraction of the map that is sea; defaults by form, about 0.2 to 0.55).
- `rivers`: `name`, `from` (edge where it enters), `to` (`sea`, `bay`, an edge, or another river's
  name for a tributary), `width_m` [min, max] (rivers 40 to 150), `meander` 0 to 1,
  `delta_branches` 0 to 6 with optional `branch_names`. `delta_branches` counts the **extra**
  channels besides the main one, so "splits into four channels" is `3`. `kind: "channel"` for a wide sea channel
  or strait. Leaving `rivers` out gives one default river; `[]` means no rivers.
- `islands`: `name`, `position` (direction from the center) and `setting` (`offshore`,
  `nearshore`, `mid_river`, `delta`; mid_river and delta need `river`), `area_km2`. Shorthand:
  `"position": "south_west_offshore"`. In the schematic, `delta` islands sit near the river
  mouth and `mid_river` islands at `center` halfway along the river, whatever the direction, so
  use at most one of each per river.
- `district_separation`: `water_preferred` (default), `water_required` or `none`.
- `bridges`: `density`, `footbridge_density`, `transit_crossing` (`own_bridge`, `shared_deck`,
  `auto`), `named` (each `name`, `kind` road/rail/road_rail/pedestrian, `connects` two of
  district/island/place/megasite/`<direction>_exit`, optional `crosses`).

**Highways** (`highways`): `pattern` (`ring`, `ring_plus_spine`, `spine`, `grid`, `radial`,
`coastal`, `none`), `exits` (default: land edges), `elevated_share`, `named` routes.

**Districts** (`districts`, usually 6 to 10). Each needs `name` and `archetype`:

| Prompt words | archetype | preset heights (m) |
|---|---|---|
| corporate core, CBD, financial, megatower | corporate_core | 80 to 320 |
| megablocks, arcology housing, stacked housing | megablock_residential | 120 to 250 |
| midtown, downtown mix, culture, central park | midtown_mixed | 30 to 150 |
| nightlife, entertainment, market, clubs, red light | entertainment_market | 10 to 60 |
| old town, historic, slums, canals, temples, shanties | old_town | 6 to 30 |
| port, docks, industrial, warehouses, container | industrial_port | 8 to 25 |
| suburbs, gated, rich hills, residential | residential_heights | 10 to 60 |
| research, campus, university, medical, labs | research_campus | 15 to 90 |
| station district, transit hub, interchange | transit_hub | 20 to 120 |
| spaceport, launch site | spaceport | 10 to 60 (height limited) |

Then, only where the prompt or image says so:
- `area_share`: fraction of the **land**. Give all (summing to 1) or some (the rest is split by
  archetype weight) or none.
- `placement`: `<direction>_of` (one name or a list), `adjacent_to`, `edge` (a direction or
  `center`), `coast` (true/false), `along_river`, `on_island`, `separated_by` (`water`, `river`,
  `channel`, `canal`, `sea`, `highway`, `ring_road`, `rail`, `wall`, or a river name). Prefer a
  few strong constraints (an edge, the coast, one or two relations to a central anchor district)
  over many weak ones. References can be districts, places, megasites or islands, not rivers:
  for "the east bank" use `along_river` plus a relation to a district on the other bank or in
  the middle. `on_island` stands alone: do not combine it with `edge` or `coast: false`.
- `grid_angle_deg`, `street_pattern`, `block_size_m`, `height_m`: only when the prompt implies
  them (for example "45 degree grid").
- `waterways`: `style` (`canal_grid`, `organic_canals`, `creeks`, `inlets`, `harbor_basins`,
  `marina`, one or a list), `density`, `named`.
- `landmarks`: `"megatower"` or `{"kind": ..., "name": ..., "height_m": ...}` (kind is any
  snake_case word; megatower, spire, arcology, observation_tower, ferris_wheel, monument, temple
  have default heights).
- `places`: `{"name", "kind", "position"}` with kind `plaza`, `park`, `garden`, `street`,
  `pedestrian_street`, `market`, `canal`, `creek`, `waterfront`, `promenade`, `pier`, `docks`,
  `marina`, `beach`, `gate`, `neighborhood`, `monument`, `station`. A place with a megasite kind
  (for example `temple_complex`) becomes a named megasite.
- `complexes`: `twin_towers`, `tower_cluster`, `megabuilding_campus`, `bridged_pair`,
  `straddle_building`, `campus` (string or `{"kind", "count"}`); left out = preset, `[]` = none.
- `megasites`: `spaceport`, `skyport`, `transit_nexus`, `freight_terminal`, `stadium`,
  `arcology`, `temple_complex`, `central_park`, `grand_plaza`, `attraction` (string or object with
  `name`, `area_km2`, `edge`, `coast`, `height_limit_m`); left out = preset (spaceport, transit hub,
  industrial port and midtown archetypes bring one), `[]` = none.
- `skybridge_density`, `grime`, `neon`, `greenery` (0 to 1): only for explicit mood words.

**Transit** (`transit`): `hubs` (districts, places or megasites where lines meet; default: transit
hub districts and transit_nexus sites) and `lines`, each `mode`, `name`, `route` (two or more
stops: districts, places, megasites, islands, hubs or `<direction>_exit`; repeat the first stop at
the end for a loop), optional `altitude_m`, `color`, `through_towers` (sky_tube only).

| mode | altitude_m allowed (default) | use for |
|---|---|---|
| metro | -60 to 0 (-20 to -12) | subway, underground |
| elevated_rail | 8 to 20 (10 to 16) | el train, skytrain, commuter rail on viaduct |
| monorail | 10 to 30 (12 to 22) | monorail, people mover |
| maglev | 15 to 60 (25 to 45) | maglev, bullet train, high speed |
| sky_tube | 40 to 150 (70 to 120) | sky tube, pneumatic tube, vacuum tube, tower-to-tower |

Megasite links (validation warns when missing): a spaceport on a maglev or sky_tube line; a
freight terminal on an elevated_rail, metro or monorail line; a transit nexus on a metro, maglev
or sky_tube line; every hub on two or more lines.

**When the water cannot do what the prompt asks** (for example "every district on its own
landmass" with one river): first try what the spec can say (more `delta_branches`, a second
river or `channel`, islands with `on_island`) as long as it still matches the prompt's
hydrology; otherwise accept shared land and say so in the report. Validation does not check
`water_required` against geometry in M0 (it cannot without the M1 generator); the schematic is
where you see it.

### 3. Validate until it passes

```bash
citygen spec validate cities/<slug>/city_spec.json
```

Exit 0 means valid; exit 1 prints one line per problem as `error: <path>: <message>`, where the
path names the field (for example `districts[3] "Old Town".placement.south_of`) and many
messages end in `(did you mean '...'?)`. Fix the spec and rerun until it exits 0. Then read the
warnings: fix the ones that show a real mismatch with the prompt (a spaceport with no maglev,
megasites that do not fit), and list the rest in the report.

### 4. Reading a concept image (layout hints only)

Geometry is generated, never traced, so a decorative or inconsistent image is fine. Take from it:
- Orientation: north is up unless a compass rose says otherwise.
- Districts (labels, color zones) and their **relative** positions: turn these into `edge`,
  `coast` and `<direction>_of` relations around a central anchor district. Do not convert pixel
  positions into coordinates.
- Coast: which side the open sea is on, and the form (a bay, a peninsula, islands).
- Rivers and channels: where they enter and where they reach the sea; which districts they
  separate (`separated_by`); canals inside districts (`waterways`).
- Islands and what sits on them (`on_island`).
- Transit: map legend colors to modes, and follow each line through the districts it touches.
- Named places, landmarks and bridges: keep their names (minus trademarks).
- Scale bars on AI images are often wrong; keep the city within about 6 to 12 km² unless the
  prompt asks otherwise, and note the choice in `source.notes`.

### 5. Render and look

```bash
citygen spec render cities/<slug>/city_spec.json cities/<slug>/schematic.png
```

Open the PNG. It is a rough schematic (districts grown from the placement constraints on a coarse
grid), so judge topology, not shapes: are districts on the right sides of each other and of the
water, do the rivers and islands sit where asked, do the transit lines visit the right districts,
are the megasites and places in the right districts? If not, adjust the spec (placement
relations, `sea_share`, river `from`/`to`, island `position`) and rerun steps 3 and 5, at most
three rounds. Unassigned land (dark gray) means the districts' shares did not reach it, usually
land cut off by a river; that is fine for a schematic.

### 6. Build (placeholder, from M1 on)

> **PLACEHOLDER: not available in M0.** From milestone M1 the skill continues here with
> `citygen build cities/<slug>/city_spec.json cities/<slug>/out/`, then reads the generated
> previews and the validation report (scope section 9), and may run the optional art-direction
> pass (adjust spec parameters only, never code, at most N rounds). Until then, stop after step 5.

### 7. Report

Reply with:
- the files written;
- a one-paragraph summary of the city (water, districts, transit, megasites);
- what you inferred or defaulted on purpose, and anything from the prompt or image you could not
  express in the spec;
- the remaining validation warnings, if any;
- the schematic (attach or link the PNG).

## Minimal example

```json
{
  "name": "Harborlight",
  "seed": 42,
  "water": {"coast": {"form": "straight", "side": "south"},
            "rivers": [{"name": "Grey River", "from": "north", "to": "sea"}]},
  "transit": {"lines": [{"mode": "metro", "name": "Line 1",
                         "route": ["Harbor", "Core", "Uptown"]}]},
  "districts": [
    {"name": "Core", "archetype": "corporate_core", "placement": {"edge": "center"}},
    {"name": "Harbor", "archetype": "industrial_port", "placement": {"coast": true, "south_of": "Core"}},
    {"name": "Uptown", "archetype": "residential_heights", "placement": {"north_of": "Core"}}
  ]
}
```

Worked examples (prompts, specs and schematics): `docs/progress/M0/`.
