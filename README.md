# CyberGen

Offline generators for cyberpunk open cities, in five stages: from one text prompt to a city
that is laid out, modelled, lit, populated and given a story. Describe a city to Claude Code,
the `citygen` skill turns the description into a spec, and the generators build the rest on
your machine.

| Stage | Generator | What it makes | Status |
|---|---|---|---|
| 1 | [layoutgen](#stage-1-layoutgen) (`citygen`) | The city's layout: water, districts, roads, buildings, transit, props and gameplay data, as a Blender blockout and an Unreal Engine level | M0 to M15 done |
| 2 | [assetgen](#stage-2-assetgen) | A unique 3D model for every building, plus street elements and textures | AG0, AG1, AG6, AG7 and AG8 done, the rest to come |
| 3 | [atmosgen](#stages-3-to-5) | Lighting, sky, weather and atmospherics | Planned |
| 4 | [lifegen](#stages-3-to-5) | Traffic, crowds, trains and aircraft, generated | Planned |
| 5 | [storygen](#stages-3-to-5) | Story, characters and cutscenes | Planned |

---

## Stage 1: layoutgen

`citygen` turns a prompt (and an optional concept image) into a complete city layout, then
builds a 3D blockout of it in Blender and puts it into Unreal Engine 5.8 as a level that
streams and can be walked.

Spec: [`docs/citygen_scope.md`](docs/citygen_scope.md) · Full milestone log:
[`docs/citygen_milestones.md`](docs/citygen_milestones.md) · Builds:
[`docs/progress/`](docs/progress)

### Cities

Whole cities in the Blender blockout, seen from the south (8K; open one for full size).

| Vesper Bay | Nexus City |
|---|---|
| <img src="docs/progress/M10/vesper_bay/render_iso_city.jpg" width="420"> | <img src="docs/progress/M10/nexus_city/render_iso_city.jpg" width="420"> |

| Delta Megacity | Saltreach Free Port |
|---|---|
| <img src="docs/progress/M10/delta_megacity/render_iso_city.jpg" width="420"> | <img src="docs/progress/M10/archipelago_free_port/render_iso_city.jpg" width="420"> |

| Greyhook | Vesper Bay with the hand-traced Corporate Core |
|---|---|
| <img src="docs/progress/greyhook_reshape/peninsula_city/render_iso_city.jpg" width="420"> | <img src="docs/progress/M10/vesper_bay_pinned/render_iso_city.jpg" width="420"> |

| Vesper Bay Stacks (stack interchange demo) | The traced Corporate Core up close |
|---|---|
| <img src="docs/progress/M10/vesper_bay_stacks/render_iso_city.jpg" width="420"> | <img src="docs/progress/M8c/vesper_bay_pinned/render_iso_d01.jpg" width="420"> |

| Cragmouth (hills and cliffs) | Vesper Bay Decks (a deck city over Highcrest) |
|---|---|
| <img src="docs/progress/stage1_fixes/cragmouth/render_iso_city.jpg" width="420"> | <img src="docs/progress/M14/vesper_bay_decks/render_iso_city.jpg" width="420"> |

### Layers

| Districts, water, roads and lots | Buildings |
|---|---|
| <img src="docs/progress/M13/vesper_bay/preview_map.png" width="420"> | <img src="docs/progress/M13/vesper_bay/preview_massing.png" width="420"> |

| Street level: lanes, sidewalks, crosswalks | Props and plants |
|---|---|
| <img src="docs/progress/M13/vesper_bay/preview_detail.png" width="420"> | <img src="docs/progress/M13/vesper_bay/preview_props.png" width="420"> |

| Vesper Bay imported into Unreal 5.8 (8K) | Cragmouth's terraced hills in Unreal (8K) |
|---|---|
| <img src="docs/progress/M15/vesper_bay/unreal_iso_city.jpg" width="420"> | <img src="docs/progress/M15/cragmouth/unreal_hillside.jpg" width="420"> |

Gameplay layer: faction turf, places to go, wealth and danger, traffic and crowds by hour.

<img src="docs/progress/M13/vesper_bay/preview_gameplay.png" width="840">

| Gameplay, Nexus City | Gameplay, Delta Megacity |
|---|---|
| <img src="docs/progress/M13/nexus_city/preview_gameplay.png" width="420"> | <img src="docs/progress/M13/delta_megacity/preview_gameplay.png" width="420"> |

| Road levels: viaducts, ramps, interchanges | Stack interchange levels and ramp profiles |
|---|---|
| <img src="docs/progress/M13/vesper_bay/preview_elevated.png" width="420"> | <img src="docs/progress/M13/vesper_bay_stacks/preview_elevated.png" width="420"> |

| Terrain: grades, walls, bored tunnels | Old quarter's hill (8K) |
|---|---|
| <img src="docs/progress/stage1_fixes/cragmouth/preview_terrain.png" width="420"> | <img src="docs/progress/stage1_fixes/cragmouth/render_hillside.jpg" width="420"> |

| Decks: the ground under the slab, the deck, a section | A deck's edge: the undercity under the slab, the city on it (8K) |
|---|---|
| <img src="docs/progress/M14/vesper_bay_decks/preview_decks.png" width="420"> | <img src="docs/progress/M14/vesper_bay_decks/render_deck_edge.jpg" width="420"> |

| Stack interchange (8K) | Trumpet interchange (8K) |
|---|---|
| <img src="docs/progress/M12/vesper_bay_stacks/render_stack.jpg" width="420"> | <img src="docs/progress/M8c/vesper_bay/render_trumpet.jpg" width="420"> |

| Tunnel under a district (Nexus City) | Cutaway along the tunnel (8K) |
|---|---|
| <img src="docs/progress/M9/nexus_city/preview_tunnels.png" width="420"> | <img src="docs/progress/M9/nexus_city/render_cutaway.jpg" width="420"> |

| Transit, Delta Megacity | Transit, Nexus City | Transit, Vesper Bay |
|---|---|---|
| <img src="docs/progress/M13/delta_megacity/preview_transit.png" width="280"> | <img src="docs/progress/M13/nexus_city/preview_transit.png" width="280"> | <img src="docs/progress/M13/vesper_bay/preview_transit.png" width="280"> |

| Street level beside a viaduct (Delta Megacity) | Street level in the Corporate Core (Vesper Bay) |
|---|---|
| <img src="docs/progress/M8c/delta_megacity/render_street_4.jpg" width="420"> | <img src="docs/progress/M8c/vesper_bay/render_street_4.jpg" width="420"> |

### Milestones

| | Milestone | What it adds | Status |
|---|---|---|---|
| M0 | City spec | Spec format, district presets, the prompt-to-spec skill | ✅ Done |
| M1 | Water, districts, main roads | Coasts, rivers, deltas, islands, districts, highways, avenues, bridges | ✅ Done |
| M2 | Streets and lots | Local streets, junctions, sidewalks, crosswalks, blocks, lots, open space | ✅ Done |
| M3 | Buildings | Towers, megablocks, landmarks, complexes, skybridges, megasites | ✅ Done |
| M4 | Blockout | Blender model, renders, 2D map, USD and glTF exports | ✅ Done |
| M5 | Transit | Metro, elevated rail, monorail, maglev, sky tubes, stations | ✅ Done |
| M6 | Props and plants | Street furniture, parked cars, signs, trees, greenery | ✅ Done |
| M7 | Elevated highways | Viaducts, ramps, interchanges; importing a hand-traced district | ✅ Done |
| M8 | Reliability | A working city from any seed; better transit and interchanges | ✅ Done |
| M9 | Tunnels | Road tunnels under districts and water, metro tunnels, pedestrian underpasses | ✅ Done |
| M10 | Editing | Regenerate one district, keep or change single buildings, freeze a version | ✅ Done |
| M11 | Gameplay layer | Places, factions, wealth and danger, traffic and crowd data, parking, fast travel | ✅ Done |
| M12 | Stack interchanges | Four-level highway crossings | ✅ Done |
| M13 | Terrain | Hills, cliffs and plateaus; roads and buildings on slopes | ✅ Done |
| M14 | Layered districts | Deck cities over the streets: upper streets, lots and buildings, ramps, stairs, elevators, light wells | ✅ Done |
| M15 | Unreal export | The city as an Unreal Engine 5.8 level (end of stage 1) | ✅ Done |

### Run it

```
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m citygen build cities/vesper_bay/city_spec.json out/vesper_bay --blockout
.venv/bin/python -m pytest -q
```

`--blockout` needs Blender 5.2. `citygen unreal out/vesper_bay <Project>.uproject` imports
the city into an Unreal 5.8 project. To make a new city, open Claude Code in this repo and
ask for one (the `citygen` skill takes it from there). Editing, locking and the other
commands: [`docs/citygen_milestones.md`](docs/citygen_milestones.md).

---

## Stage 2: assetgen

A unique 3D model for every building in a stage 1 city, generated from its footprint, massing
and use, plus roads, sidewalks, street furniture and textures. Each milestone's assets go
into Unreal through the same exporter as stage 1's city, replacing the blockout piece by piece.

Spec: [`docs/assetgen_scope.md`](docs/assetgen_scope.md) · Full milestone log:
[`docs/assetgen_milestones.md`](docs/assetgen_milestones.md) · Builds:
[`docs/progress/AG1`](docs/progress/AG1), [`AG6`](docs/progress/AG6), [`AG7`](docs/progress/AG7)

### Cities

Every building modelled: walls with window openings, storefronts, slab bands, parapets and
cornices, in one of six facade styles chosen per district, owner and building (8K; open one
for full size).

| Vesper Bay | Nexus City |
|---|---|
| <img src="docs/progress/AG1/vesper_bay/city_full.jpg" width="420"> | <img src="docs/progress/AG1/nexus_city/city_full.jpg" width="420"> |

| Delta Megacity | Saltreach Free Port |
|---|---|
| <img src="docs/progress/AG1/delta_megacity/city_full.jpg" width="420"> | <img src="docs/progress/AG1/archipelago_free_port/city_full.jpg" width="420"> |

| Greyhook | Vesper Bay with the hand-traced Corporate Core |
|---|---|
| <img src="docs/progress/AG1/peninsula_city/city_full.jpg" width="420"> | <img src="docs/progress/AG1/vesper_bay_pinned/city_full.jpg" width="420"> |

| Vesper Bay Stacks | Cragmouth (buildings on its slopes) |
|---|---|
| <img src="docs/progress/AG1/vesper_bay_stacks/city_full.jpg" width="420"> | <img src="docs/progress/AG1/cragmouth/city_full.jpg" width="420"> |

### Up close

| Corporate Core, every building at full detail (8K) | A street in Old Town (8K) |
|---|---|
| <img src="docs/progress/AG1/vesper_bay/detail/iso_d01.jpg" width="420"> | <img src="docs/progress/AG1/vesper_bay/detail/street_5.jpg" width="420"> |

<img src="docs/progress/AG1/vesper_bay/contact_sheet.jpg" width="840">

64 Vesper Bay buildings drawn at random, each framed alone (8K).

```bash
.venv/bin/python -m assetgen spec validate cities/vesper_bay/asset_spec.json --build out/vesper_bay
.venv/bin/python -m assetgen build out/vesper_bay --spec cities/vesper_bay/asset_spec.json
.venv/bin/python -m citygen blockout out/vesper_bay/city_model.json out/vesper_bay/blockout
.venv/bin/python -m assetgen preview out/vesper_bay --blockout out/vesper_bay/blockout
```

The asset spec (art direction per era, district, owner and landmark) is written from the
city prompt by a Claude Code session through the repo's `assetgen` skill. `assetgen build`
writes `out/<city>/assets/`: a glTF pack per 256 m tile with every building's model, far
proxies, a manifest keyed by building id and the entries the Unreal exporter reads, then the
street packs (below); it rebuilds only what changed, so a regenerated district rebuilds only
its own. On hilly cities buildings stand on plinths down to the ground. `assetgen preview`
renders the city, its districts and street views in Blender.

<img src="docs/progress/AG0/vesper_bay/preview_edges.png" width="840">

What every facade faces, which decides its windows: the main street (red), other streets,
alleys, water, plazas and parks, party walls (black, no windows), blind walls, yards, and
walls above their neighbors.

<img src="docs/progress/AG7/vesper_bay_stacks/streets_interchange.jpg" width="840">

The street elements around Vesper Bay Stacks's stack interchange (8K): ramps on four levels
with parapets, columns and pier caps, lane markings, sidewalks, crosswalks and the sky tube
(buildings are still the blockout's).

```bash
.venv/bin/python -m assetgen streets out/vesper_bay
```

`assetgen build` also runs it, after the buildings (`--no-streets` skips it). The street
stage writes `out/<city>/assets/streets/`, one glTF pack per 256 m tile with a mesh for
every road, sidewalk, crosswalk, junction, bridge, viaduct, tunnel, quay, transit structure
and megasite element, each named by its citygen id and replacing the blockout's street
pieces in Unreal; a regenerated district rewrites only the tiles it touches. Street views:
[`docs/progress/AG7`](docs/progress/AG7).

<img src="docs/progress/AG8/vesper_bay/neon_strand_night_8k.jpg" width="840">

An alley in Neon Strand at night (8K): shop signs with their names in neon, lightboxes and
blade signs, awnings, AC units and bollards, among the building shells and streets.

<img src="docs/progress/AG8/sheets/sheet_neon_8k.jpg" width="840">

The neon district style's props (8K): street lights, signals, shelters, benches, stalls,
kiosks, barriers, railings, dumpsters, parked cars, boats and sample signs.

```bash
.venv/bin/python -m assetgen props out/vesper_bay --sheets out/vesper_bay/sheets
```

`assetgen build` also runs it, last (`--no-props` skips it). The props stage writes
`out/<city>/assets/props/`: 4 to 12 variants of every street prop kind in each of five
district styles, 15 plant species grown as branching trees, palms, pines, shrubs and ivy,
and a sign for every sign slot with the shop's name in Latin, Cyrillic or generated East
Asian and Indic scripts. Each prop and plant picks its variant from its id, and in Unreal the
variants replace the blockout's stand-ins as instances. Sheets of every style and the
plants, and street views: [`docs/progress/AG8`](docs/progress/AG8).

| A street in The Stacks, Vesper Bay (8K) | The same street by night (8K) |
|---|---|
| <img src="docs/progress/AG6/vesper_bay/8k/street_2.jpg" width="420"> | <img src="docs/progress/AG6/vesper_bay/8k/street_2_night.jpg" width="420"> |

Every building and street piece textured: a library of tileable surfaces in each era's look
(concrete, plaster, brick, panels, cladding, roofs, asphalt, paving, metals), a room behind
every window by day and lit by night, rain streaks and grime, and each city's own shop, bar
and clinic signs in its districts' scripts, brand logos and ads.

```bash
.venv/bin/python -m assetgen library
.venv/bin/python -m assetgen materials preview out/vesper_bay --night
```

`assetgen build` makes the library the first time (about a minute and a half, 655 MB, kept in
`~/.cache/cybergen/assetgen_library`) and the city's sign pages, and gives every building and
street piece its textured materials, which the Unreal exporter imports with the city.
`assetgen materials preview` renders them in Blender, `assetgen materials board` a board of
each era's surfaces. More: [`docs/progress/AG6`](docs/progress/AG6).

<img src="docs/progress/AG1/unreal/cragmouth/unreal_district_old_quarter_8k.jpg" width="840">

Cragmouth's Old Quarter in Unreal 5.8, every building and street from stage 2 (8K).

`citygen unreal out/<city> <Project>.uproject` brings the buildings and streets into Unreal
over the blockout, each replacing its blockout piece, with tinted materials and collision;
`--blockout-only` leaves them out. More views: [`docs/progress/AG1/unreal`](docs/progress/AG1/unreal).

### Milestones

| | Milestone | What it adds | Status |
|---|---|---|---|
| AG0 | Groundwork | Art direction spec and skill, a brief of what every building is made from (facade edges by what they face), glTF writer, three test buildings in Unreal | Done |
| AG1 | Building shells | A model for every building: walls with window openings, storefronts, slabs, parapets and cornices in six facade styles; far models for distant views | Done |
| AG2 | Facades | Windows, balconies, fins and facade styles per era; massing details | Planned |
| AG3 | Street fronts | Shopfronts, doors, lobbies, loading docks, awnings, sign boxes | Planned |
| AG4 | Roofs and connections | Roof equipment, helipads, green roofs, skybridges, sky tube portals | Planned |
| AG5 | Building types and landmarks | Megabuildings, shanties, industrial and civic types, landmarks, buildings on slopes | Planned |
| AG6 | Materials and textures | Texture library per era, trim sheets, decals, window interiors, signs in each district's scripts, textured materials in Blender and Unreal | Done |
| AG7 | Street elements | Roads with markings, sidewalks and junctions, bridges, viaducts and interchanges, tunnels, quays, transit structures, megasite elements, per 256 m tile | Done |
| AG8 | Props, plants and signs | Street furniture and parked cars in variants per district style, trees by species, shrubs and ivy, shop signs with their text, neon, billboards, holo-ads | Done |
| AG9 | Every city modelled | All sample cities with their assets, in Blender and Unreal; frozen releases | Planned |
| AG10 | Layered districts | Buildings and streets on stacked decks | Planned |
| AG11 | Interiors | Enterable bars, clinics, shops and apartments | Maybe |

---

## Stages 3 to 5

- **atmosgen:** lighting, shadows, sky, clouds and weather in Unreal.
- **lifegen:** cars, crowds, trains and aircraft placed and driven procedurally on stage 1's
  lane, walkway and transit graphs.
- **storygen:** story, characters and cutscenes.

---

## Repo layout

- `citygen/`: the stage 1 generator. Tests in `tests/`, prompt-to-spec skill in
  `.claude/skills/citygen/`.
- `cities/`: city specs (Vesper Bay and its two demos; the other samples' specs are in
  `docs/progress/M1a2/<city>/`).
- `docs/`: each stage's spec (`<generator>_scope.md`) and full milestone log
  (`<generator>_milestones.md`); `docs/progress/<milestone>/` holds each milestone's builds
  and images; `docs/unreal_export.md` describes the Unreal exporter every stage shares.
- `maps/`, `pipeline/`, `reference/`, `unreal/`, `out/`: an earlier hand-tracing pipeline; its
  traced Corporate Core map is the pinned demo's input.

Each later stage adds its own package, spec, milestone log and README section the same way.
