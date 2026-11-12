# CyberGen

Offline generators for cyberpunk open cities, in five stages: from one text prompt to a city
that is laid out, modelled, lit, populated and given a story. Describe a city to Claude Code,
the `citygen` skill turns the description into a spec, and the generators build the rest on
your machine.

**Gallery:** the build so far, step by step in pictures, at https://gotwic.github.io/CyberGen/

| Stage | Generator | What it makes | Status |
|---|---|---|---|
| 1 | [layoutgen](#stage-1-layoutgen) (`citygen`) | The city's layout: water, districts, roads, buildings, transit, props and gameplay data, as a Blender blockout and an Unreal Engine level | M0 to M22 done |
| 2 | [assetgen](#stage-2-assetgen) | A unique 3D model for every building, plus street elements and textures | AG0 to AG8, AG10, AG12 to AG17 done, the rest to come |
| 3 | [atmosgen](#stage-3-atmosgen) | Lighting, sky, weather and atmospherics | AT0 to AT2 done, the rest to come |
| 4 | [lifegen](#stage-4-lifegen) | Traffic, crowds, trains and aircraft, generated | Planned ([draft plan](docs/lifegen_scope.md)) |
| 5 | [storygen](#stage-5-storygen) | Story, characters and cutscenes | Planned |

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
| <img src="docs/progress/M22/vesper_bay/render_iso_city.jpg" width="420"> | <img src="docs/progress/M22/nexus_city/render_iso_city.jpg" width="420"> |

| Delta Megacity | Saltreach Free Port |
|---|---|
| <img src="docs/progress/M22/delta_megacity/render_iso_city.jpg" width="420"> | <img src="docs/progress/M22/archipelago_free_port/render_iso_city.jpg" width="420"> |

| Greyhook | Vesper Bay with the hand-traced Corporate Core |
|---|---|
| <img src="docs/progress/M22/peninsula_city/render_iso_city.jpg" width="420"> | <img src="docs/progress/M22/vesper_bay_pinned/render_iso_city.jpg" width="420"> |

| Vesper Bay Stacks (stack interchange demo) | The traced Corporate Core up close |
|---|---|
| <img src="docs/progress/M20/vesper_bay_stacks/render_iso_city.jpg" width="420"> | <img src="docs/progress/M8c/vesper_bay_pinned/render_iso_d01.jpg" width="420"> |

| Cragmouth (hills and cliffs) | Vesper Bay Decks (a deck city over Highcrest) |
|---|---|
| <img src="docs/progress/M22/cragmouth/render_iso_city.jpg" width="420"> | <img src="docs/progress/M22/vesper_bay_decks/render_iso_city.jpg" width="420"> |

### Layers

| Districts, water, roads and lots | Buildings |
|---|---|
| <img src="docs/progress/M18/vesper_bay/preview_map.png" width="420"> | <img src="docs/progress/M21/vesper_bay/preview_massing.png" width="420"> |

| Towers: twisted, tapered, leaning, stacked, split, framed, podded, with halos and cut crowns | Looking up a Corporate Core street |
|---|---|
| <img src="docs/progress/M21/vesper_bay/render_iso_d01.jpg" width="420"> | <img src="docs/progress/M21/vesper_bay/render_street_up.jpg" width="420"> |

| Street level: lanes, sidewalks, crosswalks | Props and plants |
|---|---|
| <img src="docs/progress/M18/vesper_bay/preview_detail.png" width="420"> | <img src="docs/progress/M20/vesper_bay/preview_props.png" width="420"> |

The pavement map: every road, junction, corner pad and sidewalk surface as faces that share their edges, with clusters, turning bulbs and bends up close.

<img src="docs/progress/M22/vesper_bay/preview_pavement.png" width="840">

Neon billboards and banners on the Corporate Core's facades, from the street (8K).

<img src="docs/progress/M20/vesper_bay/render_street_1.jpg" width="840">

| Vesper Bay imported into Unreal 5.8 (8K) | Cragmouth's terraced hills in Unreal (8K) |
|---|---|
| <img src="docs/progress/M15/vesper_bay/unreal_iso_city.jpg" width="420"> | <img src="docs/progress/M15/cragmouth/unreal_hillside.jpg" width="420"> |

Gameplay layer: faction turf, places to go, wealth and danger, traffic and crowds by hour, and the slots for signs and large neon ads.

<img src="docs/progress/M20/vesper_bay/preview_gameplay.png" width="840">

| Gameplay, Nexus City | Gameplay, Delta Megacity |
|---|---|
| <img src="docs/progress/M20/nexus_city/preview_gameplay.png" width="420"> | <img src="docs/progress/M20/delta_megacity/preview_gameplay.png" width="420"> |

| Road levels: viaducts, ramps, interchanges, embankments | Stack interchange levels and ramp profiles |
|---|---|
| <img src="docs/progress/M18/vesper_bay/preview_elevated.png" width="420"> | <img src="docs/progress/M18/vesper_bay_stacks/preview_elevated.png" width="420"> |

| A viaduct's end on its embankment (8K) | A junction on a slope meeting every road (Cragmouth, 8K) |
|---|---|
| <img src="docs/progress/M18/delta_megacity/render_ramp_embankment.jpg" width="420"> | <img src="docs/progress/M18/cragmouth/render_junction_slope.jpg" width="420"> |

| Water: depth, banks by kind, flow, the sea's exposure | Ground cover: lawn, meadow, marsh, paving, dirt, desire lines |
|---|---|
| <img src="docs/progress/M16/vesper_bay/preview_water.png" width="420"> | <img src="docs/progress/M16/vesper_bay/preview_ground.png" width="420"> |

The harbor drained: basins, the sea's bed by depth, banks, the marsh and its edge (8K).

<img src="docs/progress/M16/vesper_bay/render_drained.jpg" width="840">

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
| <img src="docs/progress/M19/delta_megacity/preview_transit.png" width="280"> | <img src="docs/progress/M19/nexus_city/preview_transit.png" width="280"> | <img src="docs/progress/M19/vesper_bay/preview_transit.png" width="280"> |

| Sky tubes on cable-stayed masts (8K) | A monorail on portal frames over a street (8K) |
|---|---|
| <img src="docs/progress/M19/delta_megacity/render_sky_tube_masts.jpg" width="420"> | <img src="docs/progress/M19/delta_megacity/render_monorail_frames.jpg" width="420"> |

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
| M16 | Water and ground detail | How deep each body of water is and which way it flows, what lines its edges, and what covers every piece of open land (lawn, meadow, marsh, wasteland, sand) | ✅ Done |
| M17 | Road network repair | Every dead end on purpose (a cul-de-sac with its turning circle, a quay, a park gate, a path's end), no overlapping roads or bridges, roads clear of buildings | ✅ Done |
| M18 | Junctions and ramps | Junctions that meet every road at its height, steeper and shorter ramps on embankments, crosswalks and signals only where they are needed | ✅ Done |
| M19 | Transit structures | Lines clear of buildings, supports under the track at even spans (columns, portal frames, piers, sky tube masts), more room over the streets | ✅ Done |
| M20 | Props, plants and signs | Nothing floating or growing through a road: every lamp, bench, railing, sign and tree on the ground, a road deck, a quay, a roof or its wall; many more large neon billboards, banners and holo-boards on the sides and tops of buildings, set per district (`signage`) | ✅ Done |
| M21 | Cyberpunk massing | Towers twisted, tapered, leaning, stacked, cantilevered, split, cut through by sky gardens, in exoskeletons or covered in pods, with sloped, cut and halo crowns; curved slabs; true curves; no two neighboring towers alike; a `variety` per district | ✅ Done |
| M22 | Pavement map | One exact map of every road, junction, sidewalk and median surface, with shared edges and one height per point, so roads and junctions meet with no gap or step | ✅ Done |

### Run it

```
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m citygen build cities/vesper_bay/city_spec.json out/vesper_bay --blockout
.venv/bin/python -m pytest -q
```

`--blockout` needs Blender 5.2. While a build runs it prints each stage on stderr (water
and districts, roads, local streets, buildings, transit, tunnels, props, gameplay, water
and ground, the blockout and its Blender steps) with its time, the layout search's tries as they happen, and a
bar with the time left where a stage has a count; `--quiet` turns it off. To make a new city,
open Claude Code in this repo and ask for one (the `citygen` skill takes it from there). Editing, locking and the other commands:
[`docs/citygen_milestones.md`](docs/citygen_milestones.md).

To see the city in Unreal Engine 5.8, import it into a project (on Windows:
`.venv\Scripts\python` and Windows paths):

```
.venv/bin/python -m citygen unreal out/vesper_bay ~/CityTest/CityTest.uproject --new-project
```

Open the project and press Play: you fly over the city with a free camera (W, A, S, D to
move, the mouse to look, E or Space up, Q or C down). `--play walk` walks it with the
project's own character instead (it swims in the canals, rivers and the sea), and
`--fly-speed` sets how fast you fly. Each import makes the city the project's startup map (`--no-startup` leaves it
alone). The import shows the same kind of progress: each stage in Unreal (packs and meshes,
actors, saving, pruning, the HLOD build, `--check`) with a bar, the time left, and on a first
import an estimate of the time left in all. Controls, flags and streaming:
[`docs/unreal_export.md`](docs/unreal_export.md).

While playing:

| Key | |
|---|---|
| (minimap) | top left, the city around you with your heading |
| M | the map: wheel to zoom, right drag to pan, left click to teleport there |
| . | a free camera (W A S D, E and Q up and down, wheel for speed); `.` again goes back |
| Tab | the developer menu: day or night (by night the windows, neon, signs and street lights come on) |

These come from a small C++ plugin that `citygen unreal` builds into the project, so they
need a compiler Unreal 5.8 accepts (Visual Studio 2022 17.14 on Windows, Xcode on a Mac);
without one, or with `--no-play`, the city imports without them. A big city's first Play
takes a few minutes to load: [opening a big city](docs/unreal_export.md#opening-a-big-city).

---

## Stage 2: assetgen

A unique 3D model for every building in a stage 1 city, generated from its footprint, massing
and use, plus roads, sidewalks, street furniture and textures. Each milestone's assets go
into Unreal through the same exporter as stage 1's city, replacing the blockout piece by piece.

Spec: [`docs/assetgen_scope.md`](docs/assetgen_scope.md) · Full milestone log:
[`docs/assetgen_milestones.md`](docs/assetgen_milestones.md) · Builds:
[`docs/progress/AG1`](docs/progress/AG1), [`AG2`](docs/progress/AG2), [`AG3`](docs/progress/AG3), [`AG4`](docs/progress/AG4), [`AG5`](docs/progress/AG5), [`AG6`](docs/progress/AG6), [`AG7`](docs/progress/AG7), [`AG10`](docs/progress/AG10), [`AG12`](docs/progress/AG12), [`AG13`](docs/progress/AG13), [`AG15`](docs/progress/AG15), [`AG17`](docs/progress/AG17)

### Cities

Every building modelled and textured, in one of twenty-six facade styles per district, owner
and building, with its roof, roof equipment and skybridges, on textured streets, bridges and
transit structures; Vesper Bay Decks adds a deck city over Highcrest (8K, the five largest
at 4K; open one for full size).

| Vesper Bay | Nexus City |
|---|---|
| <img src="docs/progress/gallery_refresh/vesper_bay_city_full.jpg" width="420"> | <img src="docs/progress/gallery_refresh/cities/nexus_city/city_full.jpg" width="420"> |

| Delta Megacity | Saltreach Free Port |
|---|---|
| <img src="docs/progress/gallery_refresh/cities/delta_megacity/city_full.jpg" width="420"> | <img src="docs/progress/gallery_refresh/cities/archipelago_free_port/city_full.jpg" width="420"> |

| Greyhook | Vesper Bay with the hand-traced Corporate Core |
|---|---|
| <img src="docs/progress/gallery_refresh/cities/greyhook/city_full.jpg" width="420"> | <img src="docs/progress/gallery_refresh/cities/vesper_bay_pinned/city_full.jpg" width="420"> |

| Vesper Bay Stacks | Cragmouth (buildings on its slopes) |
|---|---|
| <img src="docs/progress/gallery_refresh/cities/vesper_bay_stacks/city_full.jpg" width="420"> | <img src="docs/progress/gallery_refresh/cities/cragmouth/city_full.jpg" width="420"> |

| Vesper Bay Decks (a deck over Highcrest) | |
|---|---|
| <img src="docs/progress/gallery_refresh/cities/vesper_bay_decks/city_full.jpg" width="420"> | |

### Up close

**Corporate cores by day and by night.** Neighboring towers never share a facade style,
window pattern, palette or night look: LED-strip mullions, honeycomb panels, folded and
colored glass, mesh and media screens, diagonal glazing and slit windows, windows staggered,
stepped and mixed in size; at night each building lights its own way (offices in bands of
floors, homes scattered, hotels warm, a few towers dark), with crown and edge lights and
logos (8K).

| Delta Megacity | |
|---|---|
| <img src="docs/progress/AG15/delta_megacity/core.jpg" width="420"> | <img src="docs/progress/AG15/delta_megacity/core_night.jpg" width="420"> |

| Vesper Bay | |
|---|---|
| <img src="docs/progress/AG15/vesper_bay/core.jpg" width="420"> | <img src="docs/progress/AG15/vesper_bay/core_night.jpg" width="420"> |

<img src="docs/progress/AG15/delta_megacity/core_street_night.jpg" width="840">

A street in Delta Megacity's core at night under its lamps (8K).
`assetgen materials preview out/<city> --views core --night` renders these. More:
[`docs/progress/AG15`](docs/progress/AG15).

<img src="docs/progress/AG2/towers.jpg" width="840">

The tallest building of every era, each in its own facade style (8K).

<img src="docs/progress/AG2/vesper_bay/contact_sheet.jpg" width="840">

64 Vesper Bay buildings drawn at random, each framed alone (8K).

<img src="docs/progress/AG2/vesper_bay/detail/street_5.jpg" width="840">

A street in Old Town at eye level: sash and lattice windows with sills and lintels, grilles, window AC units and patchwork walls (8K).

```bash
.venv/bin/python -m assetgen spec validate cities/vesper_bay/asset_spec.json --build out/vesper_bay
.venv/bin/python -m assetgen build out/vesper_bay --spec cities/vesper_bay/asset_spec.json
.venv/bin/python -m citygen blockout out/vesper_bay/city_model.json out/vesper_bay/blockout
.venv/bin/python -m assetgen preview out/vesper_bay --blockout out/vesper_bay/blockout
```

The asset spec (art direction per era, district, owner and landmark) is written from the
city prompt by a Claude Code session through the repo's `assetgen` skill. `assetgen build`
writes `out/<city>/assets/`: a glTF pack per 256 m tile with every building's model, a pack
per tile of the facade parts its buildings repeat (windows, balconies, fins and the like,
placed as instances), far proxies, a manifest keyed by building id and the entries the
Unreal exporter reads, then the street packs (below); it rebuilds only what changed, so a
regenerated district rebuilds only its own. On hilly cities buildings stand on plinths down
to the ground. `assetgen preview` renders the city, its districts, street views and the
tallest tower of each era in Blender.

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

| A street in The Stacks, Vesper Bay (8K) | Another street in The Stacks by night (8K) |
|---|---|
| <img src="docs/progress/AG6/vesper_bay/8k/street_2.jpg" width="420"> | <img src="docs/progress/gallery_refresh/street_the_stacks_night.jpg" width="420"> |

Every building and street piece textured: a library of tileable surfaces in each era's look
(concrete, plaster, brick, panels, cladding, roofs, asphalt, paving, metals), a room behind
every window by day and lit by night, rain streaks and grime, and each city's own shop, bar
and clinic signs in its districts' scripts, brand logos and ads.

```bash
.venv/bin/python -m assetgen library
.venv/bin/python -m assetgen materials preview out/vesper_bay --night
```

`assetgen build` makes the library the first time (about a minute, 658 MB, kept in
`~/.cache/cybergen/assetgen_library`) and the city's sign pages, and gives every building and
street piece its textured materials, which the Unreal exporter imports with the city.
`assetgen materials preview` renders them in Blender, `assetgen materials board` a board of
each era's surfaces. More: [`docs/progress/AG6`](docs/progress/AG6).

| Shopfronts in Greyhook's old town (8K) | The same street by night (8K) |
|---|---|
| <img src="docs/progress/AG3/greyhook/8k/shopfronts.jpg" width="420"> | <img src="docs/progress/AG3/greyhook/8k/shopfronts_night.jpg" width="420"> |

Every building's street front: a shopfront for each shop by what it sells (bars, food,
clinics, arcades, clubs, laundromats), recessed with its door, transom, riser and fascia, a
shutter or grille where the district is rough; lobby doors with steps and canopies, loading
docks, roll-up doors, garage mouths and yard gates at the other entrances; solid wall under
every sign, awning, AC unit and lamp; fire walls with downpipes and murals; grime, leaks,
rust, posters and graffiti. In Unreal the street front collides as drawn, so doorways and
steps can be walked, and every door is listed with the walkway it opens to. More:
[`docs/progress/AG3`](docs/progress/AG3).

| Roofs over Vesper Bay's Old Town (8K) | A sky station in the Corporate Core (8K) |
|---|---|
| <img src="docs/progress/AG4/vesper_bay/8k/roofs.jpg" width="420"> | <img src="docs/progress/AG4/vesper_bay/8k/sky_station.jpg" width="420"> |

Every roof finished: gabled, hipped, mansard and pagoda roofs where the era has them,
sawtooth and vaulted sheds, gravel, pavers or membrane on flat roofs with metal or stone
copings, green roofs with their beds and paths, and an AC unit, water tank, antenna,
helipad or penthouse for every one the city places, with access huts, vents and skylights;
fire escapes, kitchen ducts, cables and cameras on the walls. Skybridges by kind (glazed,
stacked, open decks, catwalks, cable bridges) land in doors on both buildings, and sky
tubes pass through towers in portals, with platforms where a station stands. In Unreal
each skybridge replaces its blockout piece and the roof equipment is instanced per tile.
More: [`docs/progress/AG4`](docs/progress/AG4).

<img src="docs/progress/gallery_refresh/landmarks_8k.jpg" width="840">

Landmarks as hero buildings by night (8K): the megatower over Vesper Bay's Corporate Core, Nexus
City's spires, an arcology and Greyhook's wheel.

Every landmark is a hero building, built by kind: the megatower's three arms with light seams
up their tips, sky gardens on the setbacks, a halo crown and a needle; spires with collars, a
needle and a beacon; the arcology's planted terraces and glazed atrium roof; the wheel with
its twin rims, spokes, gondolas and lattice legs. Each has weathering of its own (grime
washed down under the setbacks, leaks under the sills, worn corners). The other building
types are built their own way: shanty stacks with lean-to roofs, tarps and fire escapes,
megablocks with antenna farms, sheds open on steel columns, hangars with sliding doors,
temples and pagodas with colonnades and eaves, control towers with their cabs, vaulted
terminals and stations, parking ramps, and twin towers as one design. Pitched roofs get
dormers, and penthouses follow the era.

<img src="docs/progress/AG5/cragmouth/slopes_8k.jpg" width="840">

Cragmouth's Old Quarter on its hill (8K). On slopes, every building stands on a stepped
stone plinth, with doors and shopfronts brought down or up to the street and retaining
walls where the hill stands against a wall. `assetgen review` writes an art-direction sheet
for a round of changes to the asset spec. More: [`docs/progress/AG5`](docs/progress/AG5).

<img src="docs/progress/AG10/vesper_bay_decks/8k/deck_section.jpg" width="840">

A section across the deck over Vesper Bay Decks' Highcrest (8K): the deck's street on the
slab, the undercity and a ground street under it.

| | |
|---|---|
| <img src="docs/progress/AG10/vesper_bay_decks/8k/under_slab.jpg" width="420"> | <img src="docs/progress/AG10/vesper_bay_decks/8k/under_slab_night.jpg" width="420"> |
| A ground street under the slab (8K) | By night |

A district with a deck gets the slab itself: a coffered or ribbed soffit with lights over
the streets below, an edge fascia with grime streaks and a rail, colonnades where it
passes over a park, columns with capitals, and light wells with switchback stairs and glass
elevators. The deck's streets lie on the slab and climb to it on solid ramps; the
undercity's roofs close up to the soffit, its fronts lit and grimy as a covered street.
More: [`docs/progress/AG10`](docs/progress/AG10).

<img src="docs/progress/gallery_refresh/canal_night.jpg" width="840">

A quayed canal in Vesper Bay's Neon Strand by night (8K): the neon and lit windows on its
water, the quay walls with their stairs down to it.

| | |
|---|---|
| <img src="docs/progress/AG12/vesper_bay/8k/water_bank.jpg" width="420"> | <img src="docs/progress/AG12/vesper_bay/8k/water_harbor.jpg" width="420"> |
| The Vess River's natural bank (8K) | The harbor basins from above (8K) |

Every river, canal, harbor and the sea gets real water: a surface that carries the current,
foam along walls, waterlines and bridge piers and, at sea, a swell by how open the water
is; a bed of mud, silt, sand, gravel or stone at its depth, seen through clear water with
caustics; and banks by kind, grassy natural banks, beaches, marsh mud, riprap with its
stones, stone revetments and walls, meeting the quays and canal walls. In Unreal the water
is Single Layer Water with flowing ripples, foam and waves, and an underwater look.

```bash
.venv/bin/python -m assetgen water out/vesper_bay
```

`assetgen build` also runs it, after the streets (`--no-water` skips it). The water stage
writes `out/<city>/assets/water/`, one glTF pack per 256 m tile with each water body's
surface (a chain of finer to coarser meshes) and bed, and each bank, replacing the
blockout's water in Unreal; a regenerated district rewrites only the water near it. More:
[`docs/progress/AG12`](docs/progress/AG12).

<img src="docs/progress/AG13/vesper_bay/8k/park.jpg" width="840">

A park on Vesper Bay's Scholar Isle at street level (8K): lawn grass, clover and flowers in
the district's colors under the trees.

| | |
|---|---|
| <img src="docs/progress/AG13/vesper_bay/8k/lawn_edge_path.jpg" width="420"> | <img src="docs/progress/AG13/vesper_bay/8k/wasteland_lot.jpg" width="420"> |
| A lawn's edge and the worn path leaving the street (8K) | A vacant lot in The Stacks (8K) |

Every piece of open land gets its ground: lawns, meadows, marsh, wasteland, dirt, gravel,
sand, planted beds and paving, each textured by what covers it and worn where people walk,
mossy in deep shade, darker where it is wet. Grass and small plants grow on it by kind:
short lawn grass, clover, flowers in each district's palette, long meadow grass, reeds and
cattails by the water, weeds and scrub on vacant lots, ferns under the trees; none on paths,
paving or under decks. In Unreal the grass sways in the wind and fades out past 60 to 100 m.
`assetgen ground out/<city>` makes them (also part of `assetgen build`). More:
[`docs/progress/AG13`](docs/progress/AG13).

<img src="docs/progress/AG4/unreal/greyhook/8k/shopfront_street.jpg" width="840">

A shopping street in Greyhook in Unreal 5.8: street fronts, signs, props, roads and
textured buildings, all from stage 2 (8K).

`citygen unreal out/<city> <Project>.uproject` brings the buildings and streets into Unreal
over the blockout, each replacing its blockout piece, with tinted materials and collision;
`--blockout-only` leaves them out. More views: [`docs/progress/AG4/unreal`](docs/progress/AG4/unreal),
[`docs/progress/AG1/unreal`](docs/progress/AG1/unreal).

### Vehicles

<img src="docs/progress/AG18/lineup.jpg" width="840">

Twenty-one vehicles designed by hand in Blender, seven made-up brands of three: wheeled and
hovering, coupes, sedans, pickups, vans and a limousine. One sheet each in
[`docs/progress/AG18`](docs/progress/AG18); the scripts and the kit are in [`vehicles/`](vehicles).
Eighteen of them come as game packs for an engine (four LODs, baked textures with the paint
color set in the engine, wheels on their axles, collision): `vehicles/blender.sh
vehicles/game.py --car vanta_r`, format in [`vehicles/GAME.md`](vehicles/GAME.md). Not in
the cities yet.

### Milestones

| | Milestone | What it adds | Status |
|---|---|---|---|
| AG0 | Groundwork | Art direction spec and skill, a brief of what every building is made from (facade edges by what they face), glTF writer, three test buildings in Unreal | Done |
| AG1 | Building shells | A model for every building: walls with window openings, storefronts, slabs, parapets and cornices in six facade styles; far models for distant views | Done |
| AG2 | Facades | Windows, balconies, fins, louvers and frames as instanced parts; nineteen facade styles; corner cuts, setbacks, crowns and arcades; wear by district | Done |
| AG3 | Street fronts | A shopfront for every shop by its use, doors at every entrance, lobbies, loading docks, garages, shutters and grilles, mounts for signs and awnings, fire walls, grime and graffiti; walkable doorways in Unreal | Done |
| AG4 | Roofs and connections | Pitched, sawtooth and vaulted roofs, roof finishes, AC units, water tanks, antennas, helipads and penthouses on every roof, green roofs, fire escapes, ducts and cameras, skybridges with landing doors, sky tube portals through towers and sky stations | Done |
| AG5 | Building types and landmarks | Shanty stacks, megablocks, sheds, hangars, temples, pagodas, control towers, terminals and the other building types each built their own way; twin towers and campuses as one design; the megatower, spires, arcology and wheel as hero landmarks with their own weathering; stepped plinths and doors at grade on slopes; art-direction rounds | Done |
| AG6 | Materials and textures | Texture library per era, trim sheets, decals, window interiors, signs in each district's scripts, textured materials in Blender and Unreal | Done |
| AG7 | Street elements | Roads with markings, sidewalks and junctions, bridges, viaducts and interchanges, tunnels, quays, transit structures, megasite elements, per 256 m tile | Done |
| AG8 | Props, plants and signs | Street furniture and parked cars in variants per district style, trees by species, shrubs and ivy, shop signs with their text, neon, billboards, holo-ads | Done |
| AG9 | Every city modelled | All sample cities with their assets, in Blender and Unreal; frozen releases | Planned |
| AG10 | Layered districts | Deck slabs with coffered or ribbed soffits, edge fascias, rails, lights over the streets below and colonnades over parks; columns, light-well stairs and elevators; the deck's streets on the slab and solid ramps; undercity roofs that meet the slab | Done |
| AG11 | Interiors | Enterable bars, clinics, shops and apartments | Planned |
| AG12 | Water | Water that flows, foams and (at sea) swells, beds of mud, sand and stone, natural banks, beaches, marsh edges and riprap, Single Layer Water and an underwater look in Unreal | Done |
| AG13 | Ground cover and grass | Textured ground with worn paths for every piece of open land, grass and small plants by kind that sway in the wind and fade with distance | Done |
| AG14 | Fit and finish | Junctions that meet their roads, smooth glazed curved walls, roof equipment on its roofs, transit frames, piers and cable-stayed masts, embankments under low decks, bridges drawn once, nothing hanging over the lanes; checks that everything rests on something and nothing passes through anything else | Done |
| AG15 | Cyberpunk facades and night | Seven new facade styles and window patterns beyond grids, two or three finishes a building, neighboring towers never alike; every building lit its own way at night with crown lights and logos; lamps that light the streets in Unreal | Done |
| AG16 | Performance | A benchmark through each city in Unreal (`citygen unreal --bench`), and the fixes that make a whole city run smoothly walking, driving and flying, by day and night: meshes shared, far fewer actors, streaming and HLODs tuned, the far city as it looks up close | Done |
| AG17 | Road surfaces | Roads, junctions, sidewalks, medians and barriers drawn from the pavement map, joined seamlessly | Done |
| AG18 | Hero vehicles | Cars, trucks and hover vehicles designed by hand in Blender, seven made-up brands; not a generator | In progress: 21 designs done, game packs for 18 (the three Vex to be redesigned); into the cities next |

---

## Stage 3: atmosgen

The city's light and air at every hour and in every weather: every lamp, shopfront and
sign lighting the streets around it, haze and steam that catch the light, rain and wet
streets that mirror the neon, a low sky lit from below by the city, and time of day moving
every light and window through the night. It is planned as a generator like the first two:
it works out where every light, fog pocket, steam vent and puddle goes from the city and
its assets, checks that every street is lit, previews the night in Blender, and hands the
plan to Unreal through the same exporter.

The look: near-photorealistic cyberpunk, clean or gritty by place (a spotless corporate
core, gritty markets, old towns and poor districts), with rain and wet streets by default.

The streets at night are in place. From a built city it plans every light that lights a
street: each street and wall lamp by its kind (cobra heads over the road, post tops, wall
packs), a light on the mast arm of every traffic signal, corner lights where a junction
would be dark, columns along the highways, posts along pedestrian streets and promenades,
wall packs down the alleys, the light under decks, in tunnels and on station platforms,
every shopfront's spill and every sign's lit face, each with its photometry, color, hours
and its district's mood (cool white and steady in a wealthy core, sodium, flickering and
some broken in an old town). Then it checks the plan as a lighting engineer would: the
light on every sidewalk, crosswalk, road and alley, buildings casting their shadows,
against a target for each (a plan with dark streets is not delivered):

```bash
.venv/bin/python -m atmosgen plan out/vesper_bay              # BUILD/atmos: the plan and its light check
.venv/bin/python -m atmosgen lux out/vesper_bay               # the light map and the lux map round the core
.venv/bin/python -m atmosgen preview out/vesper_bay           # a Blender night render lit by the plan
```

| The plan's lights, Delta Megacity | Light on the ground round the Corporate Core |
|---|---|
| <img src="docs/progress/AT1/wip/01_plan/delta_preview_plan.png" width="420"> | <img src="docs/progress/AT1/wip/01_plan/delta_preview_lux.png" width="420"> |

`citygen unreal` takes the plan into the Unreal level with the city: its lights travel with
the level's streamed cells, and atmosgen's runtime plugin (`CityGenAtmos`, built with the
play features) lights the nearest of them by night. Haze, rain and wet streets are prototypes
for now (AT0):

| A Corporate Core junction by night | An Old Town street in rain |
|---|---|
| <img src="docs/progress/AT1/unreal/night_core_junction.jpg" width="420"> | <img src="docs/progress/AT1/bench/after/shots/night_plan_all_walk_d04.jpg" width="420"> |
| An Old Town alley | A highway through the port |
| <img src="docs/progress/AT1/unreal/night_oldtown_alley.jpg" width="420"> | <img src="docs/progress/AT1/unreal/night_highway.jpg" width="420"> |

Signs and neon light the city too: every billboard, banner and holo-board lights the street
and the facade across from it in its own colors (never washing its own wall), neon bands and
shop signs spill color onto the sidewalks, tower crowns are floodlit in the color of their LED
trim, searchlights sweep the sky from the landmarks, red aviation lights blink on every tall
roof, and the port's yards and the spaceport's apron have their high masts. Each district has
its palette, clean or gritty by place: neon flickers and dies more where it is dangerous.

| The Corporate Core: lit crowns, searchlights, aviation lights | Neon spill on an Old Town street |
|---|---|
| <img src="docs/progress/AT2/unreal/night_core_towers_air.jpg" width="420"> | <img src="docs/progress/AT2/unreal/night_signs_oldtown_a.jpg" width="420"> |
| The megatower's searchlights | The port's yard under its high masts |
| <img src="docs/progress/AT2/unreal/night_megatower_searchlights.jpg" width="420"> | <img src="docs/progress/AT2/unreal/night_port_yard.jpg" width="420"> |

Its Blender preview renders the same night in Cycles, lit by the plan's lights:

| The Corporate Core by night, Blender preview (8K) | A Corporate Core street in rain (8K) |
|---|---|
| <img src="docs/progress/AT0/core_night.jpg" width="420"> | <img src="docs/progress/AT0/core_street_night.jpg" width="420"> |

Plan: [`docs/atmosgen_scope.md`](docs/atmosgen_scope.md); what each milestone did:
[`docs/atmosgen_milestones.md`](docs/atmosgen_milestones.md).

### Milestones

| | Milestone | What it adds | Status |
|---|---|---|---|
| AT0 | Groundwork | Look presets and art direction spec, the plan's format, lights for every lamp, sign and shopfront, the runtime plugin's start, a night test of Delta Megacity in Unreal (lights, haze, rain, wet streets), a Blender night preview | Done |
| AT1 | Streets at night | Street and wall lights that light sidewalks and roads, lit junctions, highways and alleys, shop light spilling onto the street, deck, tunnel and station lights, a check that every street is lit, the lights in the Unreal level | Done |
| AT2 | Neon and signs as light | Billboards, banners and holo-boards lighting the street and facades they face, neon spill, crown floods, aviation lights, searchlights, port and spaceport lights, flicker, district palettes | Done |
| AT3 | Sky and time | Night, dusk and day skies, a cloud deck lit by the city, the moon, time of day driving every light and window | Planned |
| AT4 | Air | Fog, haze, smog and mist over the water, light shafts, steam from manholes and vents | Planned |
| AT5 | Weather | Rain kept out from under decks and awnings, wet streets and puddles, drips and splashes, wind, changing weather | Planned |
| AT6 | Looks and art direction | Color grading and post per look and district, art-direction rounds, the prompt-to-look skill | Planned |
| AT7 | Far city and release | The skyline glittering at night to the horizon, every sample city lit, checked in Unreal | Planned |

---

## Stage 4: lifegen

The city's people and traffic: crowds of varied, realistic people on every sidewalk,
stair and deck, going in and out of shops, bars and homes by their hours; cars, buses,
taxis and bikes on the roads, stopping at the signals; trains, metro, monorail, maglev and
sky tube pods running their lines; flying cars between the towers, drones, aircraft over
the spaceport and boats on the water. It is planned as a generator like the others: from
stage 1's walkway, lane and transit graphs, its crowd and traffic densities by street and
hour, its places and its districts' wealth and danger, it works out who is where, how many
and doing what, and hands that to Unreal's crowd and traffic simulation through the same
exporter.

Plan (draft): [`docs/lifegen_scope.md`](docs/lifegen_scope.md). It starts after AG16
(performance).

### Milestones

| | Milestone | What it adds | Status |
|---|---|---|---|
| LG0 | Groundwork | A spec of who lives in each district (wealth, danger, archetype, time of day), the plan's format, the walkway and lane graphs as Unreal crowd and traffic lanes, people walking one district in Unreal as a test | Planned |
| LG1 | People | A generated population: realistic bodies, faces, skin and hair, every person different, walking, waiting, talking and sitting, with cheaper stand-ins for crowds far away | Planned |
| LG2 | Clothing | Garments generated from sewing patterns and draped on each body, generated fabrics, prints and wear, accessories and cyberware; outfits by district, gang, job, wealth and weather; long coats that move near the view | Planned |
| LG3 | Crowds on the streets | People walking every sidewalk, crossing at crosswalks with the signals, taking stairs and elevators between levels, in groups and at their own pace, as many as each street has at each hour | Planned |
| LG4 | Life at places | People at benches, stalls, vending machines and bus stops, queueing at shop doors, going in and out of buildings, bars and clinics by their opening hours; gangs on their turf and police patrols | Planned |
| LG5 | Traffic | Cars, trucks, buses, taxis and bikes on the lanes, stopping at signals and turning by the rules, parking and leaving, rush hour and night traffic; their lights by night | Planned |
| LG6 | Transit | Trains, metro, monorail, maglev and sky tube pods running their lines to timetables, stopping at stations, people boarding and leaving | Planned |
| LG7 | Air and water | Flying cars on air lanes between towers and landing pads, drones, aircraft and shuttles over the spaceport, helicopters at helipads, boats and ferries on the water | Planned |
| LG8 | Weather, reactions and release | People and traffic that follow the hour and the weather (umbrellas and shelter in rain, nightlife), step aside for the player and react to what happens near them; a performance pass for crowds and traffic; every sample city alive, checked in Unreal | Planned |

---

## Stage 5: storygen

Story, characters and cutscenes.

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
