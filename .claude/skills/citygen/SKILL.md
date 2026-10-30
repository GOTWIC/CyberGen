---
name: citygen
description: Turn a city prompt (and an optional concept image) into a validated citygen city_spec.json, build its water, districts, waterways, roads, local streets, blocks, lots, open space, buildings, skybridges, landmarks and megasites, check them, build the Blender blockout (.blend, USD, glTF tiles, renders, 2D map), import it into an Unreal 5.8 project when asked, and report. Use when asked to make, generate, design or revise a city or city layout with citygen, or to write or fix a city spec.
---

# citygen: prompt (+ image) to city spec

You are the prompt-to-spec step of citygen (`docs/citygen_scope.md`, section 4.1). You read the
prompt (and the image, if any), write `city_spec.json`, validate it until it passes, render the
schematic, build the city (water, districts, waterways, primary roads and bridges, local
streets, junctions, blocks, lots and open space, buildings, complexes, skybridges, landmarks and
megasites), read the check report and previews, adjust the spec if needed, build the Blender
blockout of the passing city, and report. Everything after the spec is deterministic offline code.

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
- `out/`: the build (`city_model.json`, `preview_map.png`, `preview_detail.png`,
  `report.json`, `report.txt`); it is regenerated from the spec, so commit only what the user
  asks for.

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
  A `peninsula` may take `headlands` (2 to 5): below a shallow mainland strip it narrows to a
  short neck, then fans out into that many headlands with coves between them, instead of one
  rounded tip.
- `rivers`: `name`, `from` (edge where it enters), `to` (`sea`, `bay`, an edge, or another river's
  name for a tributary), `width_m` [min, max] (rivers 40 to 150), `meander` 0 to 1,
  `from`/`to` may pin the point along the edge: `{"edge": "east", "at": 0.3}` (0 to 1: west to
  east on north/south edges, south to north on east/west edges; on a diagonal edge 0 is the
  middle of the first-named side, 0.5 the corner, 1 the middle of the second side). For a
  `sea`/`bay` mouth, `at` runs along the sea-side edge (`{"edge": "bay", "at": 0.2}`); for a
  tributary, `to: {"edge": "<parent river>", "at": 0.3}` pins the junction along the parent
  (0 where the parent enters, 1 its mouth; unpinned, it joins a little downstream of its
  entry, at 45 degrees to the parent's flow). Leave
  `at` out unless the prompt or image places the river: unpinned ends are free parameters the
  build moves to fit the districts. A river splits the land into two banks, so where it runs
  decides how much land each bank has;
  `delta_branches` 0 to 6 with optional `branch_names`. `delta_branches` counts the **extra**
  channels besides the main one, so "splits into four channels" is `3`. `kind: "channel"` for a wide sea channel
  or strait (it counts as coast). Leaving `rivers` out gives one default river; `[]` means no
  rivers. A delta splits well inland and fans out to the coast (the coast grows a lobe for
  it); the land between its channels becomes separate landmasses: give one to a `delta`
  island, let the build place a district there, or it becomes named open land (a marsh).
- `islands`: `name`, `position` (direction from the center) and `setting` (`offshore`,
  `nearshore`, `mid_river`, `delta`; mid_river and delta need `river`), `area_km2`. A traced
  district goes in as `"pinned": {"source": "maps/corporate_core_v1.0.1.svg",
  "rotation_deg": 0}` on an offshore or nearshore island (area from the tracing; put the
  district on it with `on_island`): its coast, water pockets, roads and buildings are kept as
  drawn (heights from the object labels, else by the legacy rule within the district's
  `height_m`), the traced roads that run off the coast continue straight to the next land as
  bridges, and the generator fills the rest around them. Leave out spec `landmarks` the
  tracing already has (its megatower). Pick the newest map version (compare numerically, v1.10
  after v1.9). Shorthand:
  `"position": "south_west_offshore"`. Offshore and nearshore islands are placed from the middle
  of the sea toward `position` (the report notes an island that had no room there); a
  `mid_river` island sits on the river (`center` = nearest the
  map center) with the river splitting around it; a `delta` island is the land between two
  delta channels, sized to `area_km2`. Islands must fit: an offshore island needs open sea
  around it (raise `sea_share` or shrink it if the build says it does not fit).
- `district_separation`: `water_preferred` (default), `water_required` or `none`. The build makes
  it real: `water_required` turns every land boundary between two districts into a canal-scale
  separation channel (every district on its own landmass); `water_preferred` adds such channels
  on a budget: boundaries that run from water to water (those already near water first) until
  `boundary_water_share` (default 0.6) of the boundary between neighboring districts runs
  along water; a boundary that only reaches the map edge is a fallback, never the reason. Set
  `boundary_water_share` (0 to 1, in `water`) when the prompt says how much water splits the
  districts; `none` adds none. A district's own `water_separation` overrides the city setting.
- `bridges`: `density`, `footbridge_density`, `transit_crossing` (`own_bridge`, `shared_deck`,
  `auto`), `named` (each `name`, `kind` road/rail/road_rail/pedestrian, `connects` two of
  district/island/place/megasite/`<direction>_exit`, optional `crosses`).

**Highways** (`highways`): `pattern` (`ring`, `ring_plus_spine`, `spine`, `grid`, `radial`,
`coastal`, `none`), `exits` (default: land edges), `elevated_share` (the share of highway
length lifted onto viaducts, M7: the densest stretches with room for ramps go up first),
`named` routes, `grades` (M18; leave it out: ramps, loops and flyovers 7% design and 8% at
most, viaduct runs 6% and 7%, bridge approaches 6.5%, 30 m vertical curves; gentler grades
give longer ramps and more dead space under them).

**Crossings** (a district's `junctions`, M18; leave it out for the default by need):
`signals` `auto` (where two primary roads meet, and spaced 120 m along the roads where a
street meets one; 200 m in the old town and entertainment market), `fewer` (twice the
spacing) or `none`; `crosswalks` `auto` (on signalized approaches and spaced across avenues),
`fewer` (signalized junctions only) or `none` (unmarked crossings everywhere). Use `fewer`
or `none` for a lawless or pedestrian-hostile district.

**Terrain** (`terrain`, M13; leave it out for a flat city at sea level). Use it when the
prompt speaks of hills, slopes, cliffs, a ridge, a hill town, a city climbing from the water,
terraces or stairs:
- `hills`: each `at` (a district, a direction or `center`), `height_m` (up to 400),
  `radius_m` (default 600; the steepest slope is about 1.5 times height over radius: keep it
  under about 0.2 where people should build), optional `name`.
- `ridges`: `from` and `to` (districts, directions or `center`), `height_m`, `width_m`
  (default 500).
- `cliffs`: a `district` on a plateau `height_m` over its surroundings, its edge a cliff
  `width_m` wide (default 60); `facing` (directions) keeps the cliff to those sides and lets
  the others rise over `slope_m` (default 400). A cliff that faces a river or a neighbor
  forces big cuts and fills on every road across it: face it to the sea or the bay.
- `flat`: districts levelled to one height (ports, airports, spaceports, parks of flat
  land); megasites are always levelled.
- `shore_m` (ground over the water at a low shore, default 2), `inland_grade` (a rise away
  from the sea, e.g. 0.01), `relief_m` and `relief_scale_m` (a smooth random roll, e.g. 6 and
  500).

The build fits every road's grade line to the ground (highways 6%, avenues 8%, streets 12%,
alleys 15%), cuts and fills between retaining walls, bores tunnels where a primary road would
cut over 14 m deep, puts it on a viaduct where it would stand 15 m over the ground, turns lots
whose ground falls over 15 m into hillside greens, seats buildings on their entrances with
stepped plinths, and routes highways round steep ground. Rivers fall to the sea; canals and
basins sit at the level of what they join. Read `preview_terrain.png`. With terrain, set
`highways.elevated_share` to 0 unless the prompt asks for viaducts: on hills their ramps lock
the grade line and lift them far over the ground.

**Decks** (a district's `decks`, M14; leave it out for a city on one level). Use it when the
prompt speaks of an upper city, a deck city, a city built over the old streets, undercity,
levels or stacked streets: the district gets a slab at `height_m` (default 9, 7.5 to 16) over
`cover` of its ground (default 0.45) with streets, lots and buildings on it, ramps down to the
ground streets (`ramps`, at least one is built), light wells (`light_m`: no ground walkway
farther from the sky, default 70), stairs and elevators, columns on a `column_m` grid. What
stands on the deck is the `upper` archetype (default the district's) at `upper_height_m`;
under it the low `undercity` buildings fill the lots up to the slab. Pick a district with long
straight streets (residential heights, megablock, midtown): a ramp needs about 110 m of
street out of the deck at 12%. Organic streets (old town) seldom fit one. Read
`preview_decks.png` (the ground under the deck, the deck, a section) and `render_deck.jpg`.

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
- `area_share`: fraction of the land that holds districts. Give all (summing to 1) or some (the
  rest is split by archetype weight) or none. A district alone on an island without a stated
  share gets the island's area; a stated share is checked against the build (within 15%), so a
  stated share for an island district must match `area_km2` of its island.
- `placement`: `<direction>_of` (one name or a list), `adjacent_to`, `edge` (a direction or
  `center`), `coast` (true/false), `along_river`, `on_island`, `separated_by` (`water`, `river`,
  `channel`, `canal`, `sea`, `highway`, `ring_road`, `rail`, `wall`, or a river name). Prefer a
  few strong constraints (an edge, the coast, one or two relations to a central anchor district)
  over many weak ones. The build checks them as: direction = bearing between centroids within
  67.5 degrees of the direction; `edge` = toward that side of the land (on a sea side, toward
  the outermost shore); `center` = near the centroid of the land; `coast` = touches the sea or a
  sea channel; `along_river`, `separated_by` (water kinds or a river name) = borders that water;
  `separated_by: water` also means no land neighbor; `adjacent_to` = within 300 m;
  `highway` and `ring_road` = at least 200 m of highway (or ring road) within 60 m of the
  district's boundary; `rail` and `wall` are checked once transit (M5) and walls (M3) exist. References can be districts, places, megasites or islands, not rivers:
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
- `wealth`, `danger`, `police` (0 to 1, M11 gameplay layer): the base of the district's
  wealth, danger and police fields; archetype defaults, set only for explicit words ("rich",
  "lawless", "heavily policed"). `faction`: the gang, corporation or police that holds the
  district (districts with the same name share it); left out, a dangerous district gets a
  generated gang, corporate, campus, port and spaceport districts a corporation, the rest the
  city police. Only when the prompt names one.

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

Route order matters for the fast modes. A maglev (500 m curves) or a sky tube (300 m) cannot
turn sharply at a stop: order the stops so the line runs roughly straight through them (turns
under about 60 degrees), and leave a stop that sits off to the side to another line. (Since
M8b a fast line that must turn at a district may take the curve beside it, over the water
say, with its station on the stretch inside; the report notes "drawn along its stops".) A loop
should visit its stops in order around them, not zigzag across: the generator (M8b) places
each district stop of a loop where the stops come in route order around the loop's middle,
so any order that can go round once draws one simple ring; an order that cannot (no
station of a district lies between its neighbors) shows as a `transit_self_crossing`
failure and a red cross on the transit preview. Elevated rail and monorail follow the
avenues, so a stop off the way between its neighbors makes the line double back (a loop
leaves the roads where they would make it cross or wind round itself).

**When the water cannot do what the prompt asks** (for example "every district on its own
landmass" with one river): `water_required` makes the build add separation channels between
districts that share land, so that alone is enough. Use `water_preferred` when the prompt only
says "mostly" or "split by water"; the build then adds channels where they connect to water,
up to `boundary_water_share`.

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

### 6. Build, read the report, look at the previews

```bash
citygen build cities/<slug>/city_spec.json cities/<slug>/out/
```

The build makes the water, districts and inner waterways (coast, rivers, delta branches,
islands, landmasses, district polygons with separation channels, open land such as named
marshes and parks, canals, creeks, inlets, harbor slips and marinas with quays), reserves the
ground of every megasite (a spaceport also gets its flight cone), and lays the primary road
network: highways in the `highways.pattern` with the `exits` leaving the map, avenues
(waterfront avenues, avenues on the land boundaries between districts, axis boulevards in
rotated grids, ring roads around transit hubs and central parks, and chords at each district's
grid angle until its archetype spacing is met), and bridges wherever a road crosses water
(sea channel and port approach 25 m clearance, river 10 to 15 m, canal 3 to 4 m, with approach
ramps at 6%). Then the local network (M2): streets by archetype (rotated grids in the corporate
core, superblocks with service lanes, a grid with a park ring in midtown, organic streets with
alleys and dead ends in the old town and markets, long-block grids and quay roads in the port,
loops and cul-de-sacs in residential heights, campus loops, radial and ring streets around a
transit hub, service rings around megasite reserves), frontage streets along highways,
streets on land boundaries between districts, waterfront promenades, footbridges over canals
every 150 to 300 m; junction polygons with corner radii, sidewalks, signals and crosswalks;
the lane graph and the walkway graph; blocks, lots (narrow shopfront lots in old towns and
markets, large lots in the corporate core and port, merged lot groups for complexes), and
open space (parks, plazas, pocket parks, courtyards, the spec's named places). Then the
buildings (M3): one per lot by the district archetype (podium towers and slabs in the
corporate core, megabuildings in megablocks: a podium with a court open to the sky and
separate towers of stepped heights on it, joined by open decks, perimeter blocks in midtown,
shopfront rows and shanty stacks in the old town and markets, warehouses and container yards
in the port, villas and terraced houses in residential heights, labs on campuses, hangars at
spaceports), heights from the district's `height_m` (taller near the district focus and on
avenues and along the boulevard through the district center, capped near spaceport flight
cones), ground-floor units with uses along the street, entrances, rooftop items and green
roofs; complexes on merged lots (`complexes`; M2 tries each candidate group with the M3
builder, so complexes stand where they were grouped; straddle buildings span a street or a
canal); landmarks
(`landmarks`, e.g. the three-armed megatower); skybridges by `skybridge_density`; and every
megasite reserve filled by its generator. It writes `city_model.json`, `preview_map.png`,
`preview_detail.png`, `preview_heights.png`, `preview_massing.png`, `report.json` and
`report.txt`, and exits 0 when every check passes, 1 when one fails (2 on usage or file
errors).

1. Read `report.txt`. Each failed check names the district, island, segment or bridge and why:
   a share off by more than 15%, a relation with the actual bearing, an edge or coast not met,
   an island that does not fit, a waterway that does not connect, a sliver, invalid geometry,
   land without a district that is not open land, canals that cross too flat or run as near
   duplicates; and for roads: a landmass with a district that no road reaches, a district with
   no avenue, a named bridge not built, a bridge whose clearance does not match its water, a
   road through a megasite, a flight cone, a marsh or a park, a curve under the minimum radius
   (highway 150 m, avenue 40 m), a segment that is too short, two roads running as near
   duplicates. M2 checks: the street, lane and walkway graphs connected, every lot with street
   frontage, lot and block sizes in the archetype range, no sliver lots or blocks, sidewalk
   clear path at least 1.8 m, crosswalks at signalized junctions, no junction on a bridge or
   ramp, minimum junction angles (60 degrees in grids, 35 in organic districts), no
   near-duplicate local streets, open space share in the archetype range, every named place
   built. M3 checks: buildings inside their lots and off roads, sidewalks, water and open
   space, no overlaps, heights in the district range, an entrance near a walkway, units 4 to
   12 m on the street facade, roof items on roofs, every merged lot group built as its complex,
   skybridges (8 to 80 m, on both floor grids, 5.5 m over roads, joined to the walkways), every
   landmark built at its height, every megasite filled with its parts, nothing above a flight
   cone's limit. M5 checks: every line built along its whole route, every stop served by a
   station (in the district, within 150 m of a site, place or island), curve radii and grades
   within the mode's limits, track altitude in the line's range (higher only to clear
   navigable water or a road deck), elevated decks 2 m over the roofs under them and 5.5 m
   over road decks, sky tubes 10 m over the roofs or through a tower portal, supports off
   lanes, sidewalk clear paths, buildings and water, every station with stairs or an elevator
   joined to the street walkways, no skybridge across a track. M6 checks: props, trunks and
   shrubs out of lanes, crosswalks, junctions, buildings, water, entrances and the sidewalk
   clear path, nothing on the ground overlapping, tree crowns 1 m from facades and 1 m under
   decks, trunks off junction sight lines and station stairs, street or wall lights within
   25 m of 85% of every district's sidewalks, plants in every park, boats afloat. M7 checks:
   every road at most 6% steep, every road meeting its nodes at their height, 5.5 m clear
   under a deck where roads cross without a node (3 m over a pedestrian street), every ramp
   one-way from a viaduct deck to a ground road, columns under every raised deck over land at
   most 60 m apart and out of lanes, roads, buildings, water and transit structures. The stats
   give the boundary between districts on water (against the target),
   road km by class, bridges by class, named bridges and exits, and for M2 junctions by type,
   crosswalks, lanes, walkways, blocks, lots, the lot size distribution per archetype and the
   open space share per district, and for M3 buildings by type, heights, coverage and floor
   area per district, skybridges, units, roof items, landmarks and megasite contents, and for
   M5 transit km by mode, stations by kind, supports, tower portals and the buildings removed
   for the lines, for M6 props and plants by kind, lawns and hedges, and for M7 viaduct km,
   runs, ramps, interchanges by template, overpasses, the highest deck, other raised roads,
   underpass streets and road columns.
2. Open `preview_map.png` and compare it with the prompt (and image): districts on the right
   sides of each other and of the water, rivers entering and leaving where asked, islands
   where asked, land left without a district (hatched) only where the prompt allows it, open
   land (marsh, park) only where it makes sense. Then the roads: highways (amber) in the asked
   pattern and leaving at the asked exits (labeled at the map edge); avenues (white) reaching
   every district; bridges colored by class (pink sea, orange river, teal canal) with named
   bridges labeled where the prompt or image puts them; few long pink bridges; megasite
   reserves (cross-hatched) and flight cones (dotted) kept free of roads. Roads that end at
   the map edge continue beyond the map; they are not exits. Then the local layer: blocks
   tinted by district with lot lines, streets drawn to scale (light gray), alleys, service
   lanes (tan), promenades (pale green), footbridges (pink), open space (green parks, sand
   plazas). Each district should read differently: a regular grid at the asked angle in the
   corporate core, dense irregular blocks with many small lots in the old town and markets,
   long blocks in the port, curving loops in residential heights. Large empty areas inside a
   district, or the same grid everywhere, mean something is wrong.
3. Open `preview_detail.png`: four 400 m insets of contrasting districts at street level
   (asphalt with curbs, sidewalks, medians, lane markings, zebra crosswalks, one-way arrows,
   lots, open space). Look for believable junctions (rounded corners, crosswalks at the big
   ones), lots that face their street, shopfront rows in the old town, and no streets that
   stop just short of another.
4. Open `preview_heights.png` (footprints shaded by height) and `preview_massing.png`
   (isometric massing with four district close-ups): each district should read differently,
   towers clustered at the corporate core's focus with the landmarks above them, a fine low
   grain in the old town, large low sheds in the port, the megasites recognizable (launch
   pads, container stacks and cranes, a station with platform decks, a stadium bowl). For
   buildings: `height_m`, `landmarks` (kind, name, height), `complexes` and
   `skybridge_density` per district; a landmark that does not fit or is capped by a flight
   cone is reported in the notes.
4b. Open `preview_transit.png` (M5): every line in its color over the plan (metro dashed,
   sky tubes with a light casing), stations as rings with names, supports as dots, towers
   with a portal outlined, lots cleared for a line dotted red, a red cross where a line
   meets itself, a loop's stops numbered in route order. Each line should visit its stops
   in order without doubling back, run along the avenues (elevated rail, monorail), and
   keep its stations in the districts it names. The massing preview shows the decks,
   tubes and columns.
4c. Open `preview_props.png` (M6): four 180 m insets at street level with every prop to
   size (street lights with their glow, parked cars, bus shelters, benches, stalls,
   dumpsters, signs, awnings, cables) and the plants (crowns to scale). Street trees should
   line the wide sidewalks and medians, parks should have clusters with clearings, old towns
   wall lights, awnings and cables; density follows each district's `greenery`, `grime` and
   `neon` (set them per district to change it).
4d. Open `preview_elevated.png` (M7): every raised road colored by deck height, the
   interchanges labeled (D diamond, P partial cloverleaf, Tr trumpet, T tee stub, B direct
   branch, O overpass), columns,
   underpass streets, an interchange inset and the profile of one viaduct. Viaducts should
   run through the dense districts with ramps down to the avenues; the notes list ramps and
   underpass streets that could not be built. More viaduct: raise `highways.elevated_share`;
   none: set it to 0.
4e. Open `preview_gameplay.png` (M11): territories in faction colors (contested turfs
   hatched) with the points of interest, taxi stands and fast-travel points; the wealth and
   danger fields; evening traffic and late crowds per street; and a 300 m street inset with
   names, doors, curb points, parking and sign slots. More gangs or a calmer district:
   raise or lower its `danger` (gangs hold districts at 0.45 and up); name factions with
   `faction`.
5. If something fails or reads wrong, change the **spec**, never the code, and rebuild. Typical
   fixes: pin a river with `from`/`to` `at` so the banks get the right land; raise `sea_share`
   so an island fits; give or adjust `area_share` where a district must fill a fixed landmass
   (an island, a bank between two rivers); drop a placement rule the geometry cannot meet (for
   example `edge` toward a sea side where the land is a narrow lobe) and keep the stronger ones
   (`coast`, relations); switch `district_separation` when the prompt wants more or less water
   between districts. For roads: change `highways.pattern` or `exits` when the highways read
   wrong; name a bridge in `water.bridges.named` (with `connects` and `crosses`) to put a major
   crossing where the prompt wants it; check that each named bridge connects places that are
   really across the named water. For local streets: `street_pattern` (one of the archetype
   patterns: rotated_grid, grid, large_grid, superblocks, grid_ring_park, organic,
   curvilinear, campus_loops, radial_ring, service_roads), `grid_angle_deg` and
   `block_size_m` per district; named `places` (plaza, park, garden, market, promenade,
   waterfront, street, pedestrian_street, ...) with a `position` put them where the prompt
   wants. For transit: reorder a line's `route` when a note says the track passes a stop by
   (its curves cut the turn there) or a curve is too tight; drop a stop that sits off the
   line's way (another line can serve it); raise `altitude_m` within the mode's range when a
   line climbs over too much.
6. At most three build rounds (the art-direction loop). Build each round into its own folder
   (`out/<city>/round_01`, `round_02`, ...), then write its review sheet:
   `.venv/bin/python -m citygen review out/<city>/round_02 --spec <spec> --prev
   out/<city>/round_01`. `review.md` lists the failed checks, the numbers per district with
   last round's beside them, the spec changes since the last round
   (`citygen spec diff A B` shows them for any two specs), the previews to open and the spec
   parameters that answer what you may see. Read it with the previews and the concept image,
   change spec parameters only, and build the next round. Stop when the checks pass and the
   previews match the prompt, or after the third round; if checks still fail, report them
   with what you tried; if you believe citygen itself is wrong, say so instead of editing it.

### 6b. Blender blockout (M4)

Once the build passes:

```bash
citygen blockout cities/<slug>/out/city_model.json cities/<slug>/out/blockout/
```

(or `citygen build ... --blockout` in one go). It needs Blender 5.2 (found at
`/Applications/Blender*.app`, `$BLENDER` or `blender` on PATH; `--blender PATH` to pick one)
and takes about a minute for a 12 km2 city. It writes `city.blend` (collections per district
and category, one object per building, skybridge, bridge deck and megasite element group,
ground surfaces joined per 256 m tile, custom properties `citygen_id`, `citygen_type`,
`citygen_tile` and more), `city.usdc`, `tiles/<tile>.glb`, the renders `render_top.jpg`,
`render_iso_city.jpg` (the whole city), `render_iso_<district>.jpg` (one per district) and `render_street_<n>.jpg` (eye level),
`map_2d.svg` (Inkscape layers named like the hand-traced maps) and `map_2d.png`,
`unreal/corporate_core_plan.json` (for `unreal/build_greybox_unreal.py`), `graphs.json`
(lane and walkway graphs), `tiles.json`, `props.csv` and `blockout_report.txt`. Open the
renders: every district should read in its isometric view as it does in
`preview_massing.png`. A failed blockout check (the .blend does not reopen, an object or tile
missing, a render missing, over the 10 minute budget) is a citygen problem: report it, do not
work around it in the spec.

### 6c. Edit, pin and lock (M10)

Every entity has a stable id from what it is and where it sits (`d03.lot.e512n88.bld`,
`rs.e1234n567`, `d03.prop.bench.w41s1210`: kind, district or parent, and the 1 m grid cell of
its middle as compass offsets from the city center), so an id names the same thing after any
later edit. Every build writes `city_state.json` beside `city_model.json`: keep the build
folder, later edits start from it.

- **One district again.** Change the district's fields in the spec (its `seed`, `height_m`,
  `block_size_m`, `street_pattern`, `density`, `wealth`, places, ...) and run
  `citygen build <spec> <out> --district "<name>"` (`--base <build>` to start from another
  folder, `--seed N` to pick its seed; with nothing changed it takes a new seed). It keeps
  everything outside the district byte for byte and holds every road that is not inside it
  (border roads included); the district's new streets meet those at their old nodes. The
  seam (the junctions where the new streets meet the held roads, the lanes, sidewalks and
  walkways that end there, what stands along them, and the corners of the blocks those
  junctions cut) changes with it. It takes under a minute for a sample district and runs
  every check. M1 is not rebuilt: water, the district outlines, megasite reserves and
  primary roads stay, so a field M1 reads (`area_share`, `placement`, megasites, the
  archetype's avenue spacing) needs a full build. On a hilly city (M13) the held roads keep
  their grade lines and the district's new streets are fitted to them; the `terrain` block
  is M1's, so changing it needs a full build. Read the report: a regeneration whose checks
  fail (on some layouts a neighbor's streets come back moved, M13 README) is not a release;
  try another seed or a full build.
- **What changed:** `citygen model diff <old>/city_model.json <new>/city_model.json` lists the
  entities added, removed and changed by id, per collection (`--all`, `--json FILE`;
  `--png FILE` draws them: the same in grey, removed red, added green, moved yellow). Look at
  the map with the owner before going on.
- **Pins and overrides** go in `overrides.json` beside the spec (or `--overrides FILE`),
  read by every build and regeneration:

  ```json
  {"version": 1,
   "pins": ["d03.lot.e512n88.bld", "rs.e1234n567"],
   "edits": [{"op": "move", "id": "d03.lot.e512n88.bld", "by": [4.0, -2.5]},
             {"op": "replace", "id": "d03.lot.e512n88.bld", "height_m": 240},
             {"op": "replace", "id": "d03.os.e600n120", "kind": "garden", "name": "Jade Garden"},
             {"op": "plaza", "id": "d03.lot.e700n90", "name": "Lantern Square"},
             {"op": "remove", "id": "d03.prop.kiosk.e705n92"}]}
  ```

  Pins survive a district regeneration (a pinned road is held, a pinned building or open
  space keeps its ground). Edits run on the finished city after every build; `replace` also
  takes `set` with any fields, a road takes a new `name` only (pin it or regenerate its
  district to change it otherwise). Every check runs after the edits; an edit that breaks
  one shows in the report like any failure.
- **Release:** `citygen lock <out> --release 1.0` writes `<out>/city.lock.json` (spec,
  overrides, the regenerations in order, the search's choices, citygen version and code
  hash, model hash). `citygen lock --verify <out>/city.lock.json [--out DIR]` builds the city
  again from the lock alone and must give the same bytes; run it before handing a city on.

### 6d. Unreal import (M15)

To put a passing city into an Unreal 5.8 project (only when asked; it needs Unreal installed,
found at `/Users/Shared/Epic Games/UE_5.*`, `$CITYGEN_UE_ROOT` or `--engine`):

```bash
citygen unreal cities/<slug>/out/blockout/ "<path>/<Project>.uproject" --check --shots <folder>
```

It writes `<blockout>/unreal/manifest.json`, `prototypes.glb` and `graphs.json`, enables the
Python and editor-scripting plugins in the .uproject, then runs the editor headless: a World
Partition level `/Game/CityGen/<City>/Maps/<City>`, a static mesh actor per blockout object
(complex collision, a material instance per blockout material), props and plants as
instanced meshes, the lane, walkway and transit graphs as data assets, a player start, every
actor tagged `cg.key=`, `cg.id=`, `cg.type=` and more. `--check` then plays the level in the
editor: streaming, traces onto the ground, roofs and facades, a walk along a sidewalk;
`--shots DIR` renders views (`--view NAME EX EY EZ TX TY TZ [LENS]` adds one, say a
hillside). Running it again on the same build changes nothing; on a build
regenerated with `--district`, only what changed. `--new-project` creates the project from
the First Person template when the .uproject does not exist. The city becomes the project's
startup and default map (`--no-startup` leaves them), so opening the project and pressing
Play puts the user in it: flying by default (a free camera, `--fly-speed`), or walking with
the project's own character (`--play walk`); the far view (HLODs) is built after the
import (`--no-hlod` skips it). Never
import into a project the user did not name (their game project is theirs to choose).
Report the summary lines it prints (actors created, updated, deleted, Play, the check
lines) and attach the shots.

### 7. Report

Reply with:
- the files written;
- a one-paragraph summary of the city (water, districts, transit, megasites);
- what you inferred or defaulted on purpose, and anything from the prompt or image you could not
  express in the spec;
- the remaining validation warnings, if any;
- the schematic and the build preview (attach or link the PNGs), plus the check result and the
  stats from `report.txt` (land, water share, landmasses, waterway km, district shares, road
  km by class, bridges by class, named bridges, exits, blocks, lots, junctions, open space
  share, buildings, tallest building, skybridges, landmarks, megasites), and
  `preview_detail.png`, `preview_heights.png` and `preview_massing.png`;
- the blockout result from `blockout_report.txt` (objects, tiles, file sizes, time), with
  `render_iso_city.jpg`, `render_top.jpg`, two or three `render_iso_<district>.jpg` and a
  street view. For images meant for the README, render them again at 8K with
  `citygen rerender <blockout_dir> iso_city [iso_<district>] [street_<n>] --to <folder>`.

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

Worked examples (prompts, specs and schematics): `docs/progress/M0/`. A pinned import:
`cities/vesper_bay_pinned/city_spec.json` (Vesper Bay with the traced Corporate Core as an island in its bay). Builds of the same cities
(previews and reports): `docs/progress/M4/` with the Blender blockout renders and 2D maps,
`docs/progress/M3p/` with buildings, skybridges, landmarks and
megasites (the M3 polish; `docs/progress/M3/` before it), `docs/progress/M2/` with local streets, blocks and lots,
`docs/progress/M1b/` with primary roads (specs in `docs/progress/M1a2/`, the water and
district builds there and in `docs/progress/M1a/`).
