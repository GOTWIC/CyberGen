---
name: assetgen
description: Turn a city prompt (and optional concept images) into a validated assetgen asset_spec.json (art direction per era, district, owner and landmark), check it against the built city, write the brief of every building (briefs.json, edge classes, preview_edges.png), build every building's shell and proxy with Blender previews, and report. Use when asked to art-direct, style or revise the buildings, materials or signage of a citygen city with assetgen, or to write or fix an asset spec.
---

# assetgen: prompt to asset spec

You are the prompt-to-spec step of assetgen (`docs/assetgen_scope.md`, section 3, stage 0, and
section 4.2). You read the city's prompt (and images, if any) and its built city, write
`asset_spec.json`, validate it against the city until it passes, run the brief stage on it,
look at the edge preview, and report. Everything after the spec is deterministic offline code.

## Hard rules

- **No API calls and no network calls.** Do not call any LLM API, web service or URL, and do
  not add `anthropic`, `openai`, HTTP clients or similar to assetgen. You are the model step.
  You may start subagents or other Claude Code sessions to help, never through an API.
- **Change the spec, never the code.** If validation fails, fix the spec. If you believe
  assetgen is wrong, say so in the report instead of editing it.
- **Never required.** An empty spec (`{}`) is valid: every era comes from its preset
  (`assetgen/presets.py`). Write only what the prompt decides.
- Names come from the prompt and the built city. Do not copy third-party trademarks, brands
  or franchise names; invent your own and say so in `notes`. Logos you draw yourself as SVG
  (a session may write them); never download one.
- Follow `CLAUDE.md` working preferences (no em dashes, LaTeX for math).

## Inputs

- `cities/<slug>/prompt.md` (the prompt and the citygen session's interpretation) and
  `cities/<slug>/city_spec.json`.
- A citygen build of the city (`citygen build SPEC OUT`), for the names the spec may use:
  ```bash
  .venv/bin/python -c "import json,collections; m=json.load(open('OUT/city_model.json')); \
  print([(d['name'], d['archetype']) for d in m['districts']]); \
  print(collections.Counter(p['owner'] for p in m['properties']).most_common(12)); \
  print([b['name'] for b in m['buildings'] if b['landmark']]); \
  print(collections.Counter((b['district_id'], b['style']['era']) for b in m['buildings']))"
  ```
- Concept images, if the user gives any (read them for mood, materials and colors only).

## What the spec decides

| Field | What | Default |
|---|---|---|
| `uniqueness` | U0 to U3 (scope section 11) | `U1` (decision 13.2) |
| `hero_uniqueness` | landmarks and hero buildings | `U2` |
| `min_gene_distance` | $k$: discrete genes two buildings outside one complex differ in | 4 |
| `share_parts` | share a part between buildings whose quantized parameters coincide | true |
| `texel_density_px_m`, `texel_density_upper_px_m` | street band and above | 512, 256 |
| `eras.<era>` | `systems` (facade system weights), `palette` (`#rrggbb`), `crowns`, `signage_scripts` (weights), `window_to_wall` and `bay_m` ranges, `wear` (0 to 2); any field left out keeps the preset's | `assetgen/presets.py` |
| `districts.<name>` | `era` (one era for the whole district), `wear` and `ad_density` multipliers (0 to 3), `neon_palette`, `systems` (weights added to the era's), `signage_scripts` (replace the era's) | none |
| `owners.<owner>` | `brand_colors`, `logo` (repo path of an SVG), `facade_bias` (system weights added) | none |
| `landmarks.<name>` | `brief` (words for the hero generator), `palette`, `crown` | none |
| `notes` | what you inferred and every judgment call | |

Eras (one per district archetype in citygen): `heritage` (old town), `neon_retro`
(entertainment market), `corporate_glass` (corporate core), `brutalist` (megablocks),
`industrial` (port), `clean_tech` (research campus), `suburban_modern` (residential heights),
`transit_modern` (transit hub), `mixed_modern` (midtown), `aerospace` (spaceport).

Facade systems: `unitized_curtain_wall`, `spandrel_ribbon`, `fin_wall`, `diagrid`,
`exoskeleton`, `punched_concrete`, `precast_panel`, `board_marked_concrete`, `punched_brick`,
`stucco_shutters`, `timber_infill`, `tiled_eaves`, `corrugated`, `standing_seam`,
`louvered_industrial`, `shanty_patchwork`, `capsule_stack`, `perforated_skin`,
`hangar_cladding`. Crowns: `flat`, `parapet`, `lantern`, `halo`, `mast`, `spire`, `stepped`,
`pitched`, `pagoda_roof`, `sawtooth`, `dome`, `billboard_frame`. Scripts: `latin`, `hanzi`,
`hangul`, `kana`, `cyrillic`, `devanagari`.

Full schema: `assetgen spec schema` (or `assetgen/schemas/asset_spec.schema.json`).

## Steps

### 1. Read

Read the prompt twice. List the moods it gives each district (wealth, grime, neon, greenery,
culture, age), any materials or colors it names, signage languages, corporations and
landmarks. Read the citygen interpretation in `prompt.md` and the district list of the build.

### 2. Write the spec

Put it in `cities/<slug>/asset_spec.json`, starting with
`"$schema": "../../assetgen/schemas/asset_spec.schema.json"`. Keep it sparse:

- **Eras**: only where the prompt says something an era preset does not (for example "red
  brick and green tile" for an old town: heritage `palette`; "Korean and Chinese signage":
  `signage_scripts`).
- **Districts**: a district that the prompt sets apart from its era (a richer or dirtier
  strip, a different signage language, its own neon colors) gets an entry by its exact name
  in the build. Use `era` only when the prompt asks for a different period than its
  archetype gives.
- **Owners**: the corporations the prompt names, renamed where they are someone else's
  brands; otherwise the three to five owners with most buildings in the build, with brand
  colors that fit their names.
- **Landmarks**: every landmark of the build by its name, with a `brief` of one or two
  sentences.
- **notes**: what you inferred and every default you kept on purpose.

### 3. Validate

```bash
.venv/bin/python -m assetgen spec validate cities/<slug>/asset_spec.json --build OUT
```

Fix every error (a district, owner or landmark name the build does not have; weights all 0;
a color not `#rrggbb`) and read the warnings. `--filled FILE` writes the spec with every era
filled from its preset.

### 4. Briefs

```bash
.venv/bin/python -m assetgen brief OUT --spec cities/<slug>/asset_spec.json
```

writes `OUT/assets/briefs.json` (one brief and hash per building), `brief_report.json` and
`preview_edges.png`. Look at the preview: front edges (red) on the main streets, party walls
(black) inside dense blocks, canal edges (blue) on the water. A change to one district's
entry changes only that district's briefs (`assetgen brief diff A B` shows which).

### 5. Assets (AG1 on)

```bash
.venv/bin/python -m assetgen build OUT --spec cities/<slug>/asset_spec.json
.venv/bin/python -m citygen blockout OUT/city_model.json OUT/blockout --no-export
.venv/bin/python -m assetgen preview OUT --blockout OUT/blockout
```

`assetgen build` makes every building's shell and far proxy (`OUT/assets/tiles/`,
`proxies/`, `manifest.json`, `asset_report.txt`, `unreal_contribution.buildings.json`; on a
hilly city each on a plinth down to the ground) with its facade parts (AG2: windows,
balconies, fins, louvers, members, shutters and the rest, merged into the shell or
instanced from `OUT/assets/parts/`), then the street packs as `assetgen streets`
does (`OUT/assets/streets/`, `streets_report.txt`, `unreal_contribution.streets.json`;
`--no-streets` skips them), and exits 1 if a check of either fails; a second run with
nothing changed writes no file. `assetgen
preview` renders the whole city from proxies, each district and the blockout's street
cameras at full detail, and contact sheets per building type (`OUT/assets/previews/`). The
spec steers what the previews show: an era's `systems` pick the facade systems (all of
`presets.FACADE_SYSTEMS` are built; a few need a size of building, `systems.FLOORS`), its
`palette` the wall and trim colors, `crowns` the tower tops (AG2 builds flat, parapet,
lantern, stepped, halo, mast and spire; pitched, pagoda, sawtooth, dome and billboard
crowns are AG4's roofs), `bay_m` and `window_to_wall` the facade rhythm, a district's
`wear` the grime (with the district's wealth it sets how many windows are boarded, fitted
with AC units or grilles), an owner's `brand_colors` and `facade_bias` its buildings. The
massing articulation (corner cuts, setback ledges, podium canopies, arcades) follows the era
(`systems.ARTICULATION`). `assetgen preview ... --views towers` adds the tallest building of
every era up close.

### 6. Report

Report the spec's path, what it sets and why (one line per entry), the validation result, the
brief counts and edge classes from the brief report, the asset report's checks and triangle
counts when assets were built, and anything in the prompt the spec could not express (it goes
to the scope's open items).
