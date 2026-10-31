# citygen: prompt-to-city layout generator (scope, v1)

Stage 1 (layoutgen) of CyberGen's five stages. One text prompt in; a complete, playable-scale cyberpunk city
layout out, built as a blockout scene in Blender plus structured data for later stages and Unreal.

```
 prompt (+ optional concept image)
        │
        v
 [Claude Code session, citygen skill]  ──>  city_spec.json
        │
        v
 [citygen, offline deterministic Python]  ──>  city model (JSON)
        │
        ├──> Blender blockout scene (.blend, per tile)
        ├──> 2D maps + previews (PNG/SVG, review)
        └──> exports for stage 2/3 and Unreal (USD/glTF, instance data, graphs)

 stage 2 (assetgen, CyberGen): unique models and textures
 stages 3 to 5 (atmosgen, lifegen, storygen): looks, life, story
```

## 1. Goal

- Input: a prompt such as "coastal megacity on a bay, districts split by a river delta, canal-laced
  old town, corporate core with a megatower, spaceport on the northwest coast, maglev and sky-tube
  lines linking the districts, container port in the southeast". Nothing traced, nothing drawn.
- Output: the coastline, rivers, channels, canals and islands; every road (highway to alley),
  bridge, elevated road and ramp; every transit line from metro to sky tube, with stations;
  parks and plazas; large sites such as spaceports; every block, lot and building (with type,
  height and ground-floor stores); street props (light poles, trash cans, trash, bus shelters,
  overhead cables, canopies); and vegetation (street trees, park trees, palms, shrubs, hedges,
  lawns, green roofs). Everything has a semantic type, so stage 2 can replace each blockout
  with real assets.
- No human input required after the prompt. Optional overrides exist (section 4.3) but nothing
  depends on them.

## 2. Design principles

1. **No API calls, anywhere.** citygen never calls an LLM API or any other network service, in
   development or in the final product, and has no LLM SDK dependency. The only model steps
   (prompt -> spec, and the optional art-direction review) are done by a Claude Code session
   following the repo's `citygen` skill (section 4.1); that session may start other Claude
   sessions or subagents to help. Everything after the spec is seeded, deterministic, offline
   code: same spec + seed = same city, byte for byte.
2. **Generation core outside Blender.** Pure Python (shapely, networkx, numpy, scipy), testable
   without Blender and runnable in cloud sessions. Blender is a builder and renderer only.
3. **One canonical city model.** All outputs (Blender, 2D maps, Unreal exports) are views of the
   same JSON model. Nothing is generated inside a builder.
4. **Semantic everything.** Every object has a type, an id, and attributes (`prop.trash_can`,
   `building.podium_tower`, `road.avenue`). Blockout geometry is a placeholder for stage 2.
5. **Local regeneration.** Seeds are per stage and per district, so changing one district does
   not reshuffle the others.
6. **Validated, not eyeballed.** Every run ends with automatic checks (section 9); previews exist
   for art direction, not for catching bugs.
7. **Water first.** The water network (sea, bays, rivers, delta channels, islands) is generated
   before anything else and decides the landmasses; districts, roads and bridges follow from it.
   This is how both Night City and the Nexus City concept read: a coastal city whose districts
   are split by rivers, with smaller waterways reaching into them.
8. **Flat ground (v1).** Land at z = 0, sea below. Verticality comes from structures (elevated
   roads, sky transit, walkways, megabuildings, skybridges).

## 3. Pipeline stages

| # | Stage | Produces | Method (references in section 14) |
|---|---|---|---|
| 0 | Prompt -> spec | `city_spec.json` | a Claude Code session following the `citygen` skill writes the spec, runs `citygen spec validate` and fixes errors until it passes; optional concept image read for layout hints; unspecified values filled from archetype presets; no API call |
| 1 | Coast and hydrology | sea, coastline, bays, rivers, delta channels, islands, landmasses | coast shape from spec form (bay, peninsula, delta, archipelago, crescent); rivers routed from inland edges to mouths as sine-generated meander curves that widen downstream, with fan-shaped deltas that split well inland; islands placed offshore; land minus water = landmasses |
| 2 | Districts | district polygons with archetype | districts assigned to landmasses by area share and placement constraints; large landmasses split by a domain-warped weighted Voronoi (power diagram), Lloyd relaxed, so boundaries are curved and some districts concave; boundaries follow water where the spec asks for water separation, otherwise highways, ring roads, rail or walls |
| 3 | Inner waterways | canals, creeks, inlets, harbor basins, marinas, quays | per-district waterway style and density; every waterway connects to a river, channel or the sea (except declared ornamental basins) |
| 4 | Primary network | highways, arterials, ring roads, axis boulevards, bridges, off-map exits | graph over district centers, hubs and exit portals (Delaunay, pruned, MST plus loops), fitted with minimum curve radii; bridges wherever it crosses water, with clearance by waterway class |
| 5 | Local network | streets, alleys, pedestrian streets, service lanes, footbridges | tensor-field streamlines per district (grid at angle, radial or ring around hubs and landmarks, water-following along rivers and canals); L-system growth for organic districts; alleys from block-interior splits |
| 6 | Junctions and cross-sections | intersection polygons, sidewalks, curbs, medians, crosswalks, lane graph, sidewalk graph | road graph buffered by cross-section; corner radii; signal placement by junction class |
| 7 | Elevated roads | elevated highways, ramps, interchanges, overpasses, viaducts, support columns, elevated walkways, covered sections | road levels plus z-profiles; interchange templates (diamond, partial cloverleaf, trumpet); grade and clearance solver (section 5.2) |
| 8 | Transit | metro, elevated rail, monorail, maglev, sky tubes; stations, sky stations, hubs, bus stops, ferry piers | lines routed as graph paths through district centers, hubs and megasites; mode-specific altitude, grade, curve radius and support rules (section 5.3) |
| 9 | Megasites | spaceport, transit nexus, freight terminal, stadium, arcology, temple complex, research campus | site generators placed per spec constraints, run before blocks so the street network flows around them (section 5.7) |
| 10 | Blocks, lots, open space | blocks, lots, parks, plazas, pocket parks, waterfront promenades, courtyards | polygonize the network; open-space quota per district; lot subdivision by OBB splits and straight-skeleton strips (Vanegas et al. 2012) |
| 11 | Buildings | building masses, heights, uses, ground-floor units, entrances, rooftop elements, landmarks, complexes, skybridges | per-lot archetype grammar (section 5.5); complexes placed first on merged lots; height field from district profile, distance to center, noise; height limits from megasite flight zones; skybridges matched between facing facades |
| 12 | Props and vegetation | street furniture, ground clutter, overhead elements, trees, palms, shrubs, hedges, lawns, green roofs | rule-based placement along sidewalk zones, medians, alleys, plazas, quays, parks, rooftops; Poisson-disk scatter with keep-out zones (sections 5.6, 5.8) |
| 13 | Validate | report + pass/fail | section 9 |
| 14 | Build and export | `.blend`, previews, USD/glTF tiles, instance data, graphs, legacy `plan.json` | section 8 |

(Stage 9 is listed after transit for readability; in the run order megasites are reserved right
after districts so roads and transit can connect to them.)

## 4. Inputs

### 4.1 Prompt and optional concept image
- Free text, one line or a page. Can name districts, sub-areas, water features, landmarks,
  transit lines, moods.
- Optional concept image (for example an AI-generated city map like the Nexus City concept).
  The spec stage reads it with Claude's vision for layout hints only: which districts exist,
  their relative positions, where the coast and rivers run, which districts water separates,
  transit routes and landmarks. Geometry is still generated, not traced, so a decorative or
  inconsistent image is fine.
- How a city is requested: open Claude Code in this repo and ask for a city (or run the
  `citygen` skill) with the prompt, optionally attaching an image. The skill has the session
  write `city_spec.json`, run `citygen spec validate` until it passes, run `citygen build`,
  look at the previews, and report. No API key, no network.

### 4.2 City spec (generated from the prompt; human-readable, never required to edit)

```json
{
  "name": "Vesper Bay", "seed": 1207, "size_km": [3.4, 3.4],
  "water": {
    "coast": {"form": "bay", "side": "south_west"},
    "rivers": [{"name": "Sentinel", "from": "north_east", "to": "bay", "width_m": [60, 120],
                "meander": 0.4, "delta_branches": 2}],
    "islands": [{"name": "Silver Island", "position": "south_west_offshore", "area_km2": 0.5}],
    "district_separation": "water_preferred"
  },
  "highways": {"pattern": "ring_plus_spine", "exits": ["north", "east"]},
  "transit": {
    "hubs": ["Transit Nexus"],
    "lines": [
      {"mode": "metro", "name": "Blue Line", "route": ["Corporate Core", "Transit Nexus", "Midtown"]},
      {"mode": "maglev", "name": "Magenta Line", "altitude_m": [25, 45],
       "route": ["Neon Market", "Transit Nexus", "Midtown", "east_exit"]},
      {"mode": "sky_tube", "name": "Spire Loop", "altitude_m": [70, 120], "through_towers": true,
       "route": ["Corporate Core", "Aurora Spaceport", "Transit Nexus", "Corporate Core"]}
    ]
  },
  "districts": [
    {"name": "Corporate Core", "archetype": "corporate_core", "area_share": 0.12,
     "placement": {"north_of": "Transit Nexus"}, "grid_angle_deg": 45, "height_m": [80, 320],
     "landmarks": ["megatower"], "places": [{"name": "Sky Garden Plaza", "kind": "plaza"}],
     "complexes": ["twin_towers", "tower_cluster"], "skybridge_density": 0.6,
     "grime": 0.1, "neon": 0.4, "greenery": 0.3},
    {"name": "Old Town", "archetype": "old_town", "area_share": 0.14,
     "placement": {"coast": true, "south_west_of": "Transit Nexus", "separated_by": "river"},
     "waterways": {"style": "organic_canals", "density": 0.6},
     "places": [{"name": "Jade Canal", "kind": "canal"}, {"name": "Temple District", "kind": "temple_complex"}],
     "grime": 0.7, "neon": 0.6},
    {"name": "Aurora Spaceport", "archetype": "spaceport", "area_share": 0.08,
     "placement": {"coast": true, "edge": "north_west"}, "megasites": ["spaceport"]}
  ]
}
```

What the spec can express about water, so prompts like "districts split by rivers, canals
running into the old town" always have somewhere to land:
- coast form and side: bay, peninsula (one rounded tip, or fanning out into headlands with
  coves between them), delta, archipelago, crescent, straight coast
- rivers: count, names, entry and mouth, width range, meander, delta branches
- islands: count, names, position, size, which district sits on each
- district separation: by water (preferred, required, none) per district or for the whole city
- inner waterways per district: style (canal grid, organic canals, creeks, inlets, harbor
  basins, marina), density, named canals
- bridges: density per crossing, named landmark bridges, rail and pedestrian bridges

### 4.3 Optional overrides (never required)
- Pinned geometry: import an existing SVG/JSON district (e.g. today's traced
  `maps/corporate_core_v*.svg`) as fixed; the generator builds around it.
- Per-district parameter tweaks, landmark positions, a different seed per district.

### 4.4 District archetypes (presets; the spec session picks and tunes them)

| Archetype | Street pattern | Blocks (m) | Heights (m) | Character |
|---|---|---|---|---|
| corporate_core | rotated grid, axis boulevard, wide avenues | 120 to 200 | 80 to 320, landmark 450+ | plazas, podium towers, skybridges, sky stations, clean |
| megablock_residential | superblocks | 150 to 250 | 120 to 250 | megabuildings with atriums, elevated decks |
| midtown_mixed | grid with ring road and central park | 80 to 140 | 30 to 150 | culture, living, commerce, big central plaza |
| entertainment_market | dense organic, canals | 30 to 80 | 10 to 60 | clubs, covered alleys, stalls, billboards, heavy neon |
| old_town | organic, many dead ends, canals and creeks | 20 to 60 | 6 to 30 | markets, food, heritage, temples, stacked shanties, grime |
| industrial_port | large grid, rail spurs | 150 to 300 | 8 to 25 | warehouses, container yards, cranes, berths, freight terminal |
| residential_heights | curvilinear, gated | 80 to 150 | 10 to 60 | lower density, parks, walls, guard gates |
| research_campus | campus loops on an island | 100 to 200 | 15 to 90 | labs, medical, R&D, landscaped grounds |
| transit_hub | radial and ring around a central station | 60 to 120 | 20 to 120 | multi-level station, bus bays, maglev and metro interchange |
| spaceport | service roads around pads | site-driven | 10 to 60, height-limited zone | launch pads, terminal, hangars, cargo (section 5.7) |

## 5. Feature catalog

### 5.1 Roads (cross-sections, defaults per class)

| Class | Lanes | Lane (m) | Median | Parking | Sidewalk (m) | Total (m) |
|---|---|---|---|---|---|---|
| highway | 2 x 3 | 3.6 | barrier, shoulders | no | none | 26 to 32 |
| avenue | 2 x 2 or 2 x 3 | 3.3 | 2 to 6 m, trees | sometimes | 4 to 6 | 26 to 40 |
| street | 2 x 1 | 3.2 | no | one or both sides | 2.5 to 4 | 12 to 20 |
| alley / service | shared 1 | 4 to 6 | no | no | none | 4 to 6 |
| pedestrian street | none | | | | full width | 6 to 15 |

Curbs 0.15 m. Corner radii by class. One-way flags for narrow streets. Every road has a level
(0 = ground, 1, 2, ...) and a z-profile. Ring roads and axis boulevards are explicit patterns.

### 5.2 Elevated roads, ramps and interchanges
- Levels: ground; level 1 deck top about 8 to 10 m; level 2 about 16 to 20 m; sky level
  (transit only) 25 to 150 m.
- Clearance under any road deck at least 5.5 m; deck thickness 1.5 to 2 m.
- Ramp length from rise and maximum grade, $L = \dfrac{\Delta h}{g}$; for example rising
  $\Delta h = 9\,\text{m}$ at $g = 0.06$ needs $L = 150\,\text{m}$ of run, plus vertical curves.
- Max grade 6% for roads; pedestrians use stairs, escalators or elevators.
- Interchanges from templates (diamond, partial cloverleaf, trumpet; stack is v2), fitted where
  highways meet highways or arterials. Free-form solving is out of scope.
- Supports: columns every 25 to 40 m, never inside a lane, sidewalk clear path or navigable channel.
- Covered sections: canopies over walkways and roads under decks (cyberpunk "underpass streets").

### 5.3 Transit, including sky lines

| Mode | Altitude | Structure (blockout) | Stations | Grade, curves |
|---|---|---|---|---|
| metro | underground | none, line as data | entrance kiosks + concourse box; spacing 600 to 1000 m | n/a |
| elevated rail | 8 to 20 m | viaduct deck on columns every 25 to 40 m | platforms on the deck, stairs and elevators | at most 4%, radius at least 150 m |
| monorail | 10 to 30 m | single beam on T-pylons every 20 to 30 m | compact platforms | at most 6%, radius at least 100 m |
| maglev | 15 to 60 m | high guideway on pylons every 30 to 60 m, long sweeping curves | large hub stations, often in a terminal building | at most 10%, radius at least 500 m |
| sky tube | 40 to 150 m | enclosed tube (cylinder or rounded box) on tall pylons, or hung between towers on trusses | sky stations inside towers, reached by elevator cores | at most 8%, radius at least 300 m |

- Sky lines either clear everything below by at least 10 m or pass through a tower via a
  declared portal (the building gets a matching void and, where it stops, a sky station floor).
- Every elevated or sky station has vertical access to the street (stairs, escalators, elevator
  core) and is placed next to a walkway or plaza.
- Lines cross water on their own bridges or share road bridges as a second deck.
- Bus stops every 300 to 400 m on avenues; ferry piers and water-taxi stops on rivers and canals.

### 5.4 Water and waterfront
- Sea, coastline, bays, harbor basins, breakwaters, piers and docks.
- Rivers 40 to 150 m wide, meandering, with delta channels that separate districts.
- Islands offshore or mid-river, each linked by at least one bridge.
- Inner waterways reaching into districts from rivers or the sea:
  - canal grids (straight, 10 to 30 m, stone quays)
  - organic canals and creeks (old town)
  - inlets, harbor basins and marinas (port, waterfront districts)
- Bridges at every road or rail crossing; navigable clearance by waterway class: sea channel
  and port approach 25 m+, river 10 to 15 m, canal 3 to 4 m. High clearance means long
  approach ramps, so major bridges are few and named; canals get many low footbridges.
- Quays and promenades along waterways, with stairs down to the water and boat moorings.
- Street-level pools, fountains, reflecting basins in plazas.
- M16: each water body's depth, bed profile and flow, the sea's exposure, and a
  bank kind for every water edge (quay, canal wall, embankment, natural bank, beach, marsh
  edge, riprap), for stage 2's water (AG12).

### 5.5 Open space and buildings
Open space: parks (lawns, path network, tree clusters), plazas (paving, fountain, seating),
pocket parks in leftover lots, podium-roof plazas linked by skybridges, waterfront promenades.

Each building is a list of masses (extruded polygons with $z_0, z_1$) plus attributes:
archetype, use (office, residential, retail, hotel, industrial, parking, civic), floor height,
style tags (grime, neon, era) for stage 2.

| Archetype | Shape |
|---|---|
| podium_tower | 2 to 6 floor podium on the lot, setback tower(s) on top |
| slab | long bar, 8 to 30 floors |
| courtyard_block | perimeter block with inner courtyard |
| megabuilding | block-filling, 150 m+, internal atrium void, elevated decks |
| terraced | stacked setback tiers |
| shopfront_row | narrow lots, 2 to 6 floors, continuous street wall |
| shanty_stack | irregular stacked boxes, overhangs, balconies |
| warehouse / shed | large low box, loading docks |
| parking_structure | open-deck box with ramp |
| station | per transit rules, including sky-station floors inside towers |
| landmark | spec-defined generator (e.g. the three-armed megatower) |

**Complexes (one property, several buildings).** A `property` groups buildings that belong
together, on one lot or on lots across a street:

| Complex | Shape |
|---|---|
| twin_towers | two mirrored towers on a shared podium, linked by one or more skybridges (e.g. the Petronas Towers, linked at floors 41 and 42) |
| tower_cluster | three or more towers of stepped heights on a shared podium, bridges between neighbors |
| megabuilding_campus | megabuilding with satellite towers, linked by decks and bridges |
| bridged_pair | two buildings of one owner on facing lots, joined by skybridges across the street |
| straddle_building | a building whose upper floors span a street on a bridge structure (clearance at least 5.5 m) |
| campus | low buildings around landscaped grounds, joined by covered walkways (research, civic) |

**Skybridges** connect buildings across streets, alleys, canals and plazas, whether or not they
share an owner:
- Endpoints on facing facades of two masses that both reach that height; ends land on a floor
  (z matches the floor grid of both buildings).
- Clearance over roads at least 5.5 m, over waterways at least the waterway class clearance.
- Length 8 to 80 m, roughly perpendicular to both facades; never through another building, a
  sky line or a sky tube corridor.
- Kinds: enclosed walkway, open deck, multi-level stack, and in grimy districts improvised
  catwalks and cable bridges between shanties at low height.
- Density per district (corporate and megablock high, old town low and improvised).
- Every skybridge joins the pedestrian graph, so crowds can use it later.

Ground floors: street-facing edges split into units (4 to 12 m) with use tags (food,
convenience, bar, clinic, cyberware, pawn, club, arcade, laundromat), entrance positions,
awning and sign blocks. Rooftops: AC units, water tanks, antennas, billboards, helipads and
AV landing pads (more in corporate and hub districts).

### 5.6 Props (blockout primitives, all instanced)

| Type | Blockout | Placement rule |
|---|---|---|
| street_light | box pole 8 m + arm + head (light emitter tag) | furniture zone, every 25 to 35 m, staggered |
| traffic_signal | pole + box heads | signalized junction corners |
| trash_can | cylinder r 0.3, h 0.9 | near crossings, shop entrances, bus stops |
| trash_scatter | small spheres (bags), boxes and planes (cardboard), tiny cylinders (cans) | Poisson scatter; density by grime; gutters, alleys, corners |
| dumpster | box 2 x 1.2 x 1.3 | alleys, service lanes, building backs |
| bench | box | parks, plazas, bus stops, quays |
| bus_shelter | frame boxes + roof plane | bus stops |
| vending_machine / kiosk | box (emitter) | shopfronts, stations, plazas |
| food_stall | box + awning plane | markets, plazas, under decks, quays |
| bollard / hydrant | cylinders | corners, pedestrian streets, every 100 m |
| planter | box with shrub spheres | plazas, shopfronts, podium roofs (trees and other plants: section 5.8) |
| parked_vehicle | box + upper box | parking lanes, lots |
| boat | box hull + small box cabin | moorings, marinas, harbor berths |
| barrier / railing | jersey prism, fence and railing segments | highways, quay edges, bridges, gated districts |
| overhead_cable | thin cylinders between facades | alleys and narrow streets, density by grime |
| sign / billboard | planes on facades and roofs (emitter) | density by neon |
| ac_unit | box on facades and roofs | buildings |
| shipping_container / crane | boxes | port, freight terminal |
| scaffolding | box frames | random buildings |
| arch / gate | boxes with opening | market entrances, temple gates, enclave gates |
| canopy / bridge_cover | roof plane on posts | walkways, stall rows, station approaches, covered bridges |
| column / pylon | cylinder or box, up to 150 m for sky lines | under every elevated deck and line |
| stairs / elevator_core | stepped boxes / tall box | stations, quays, elevated walkways, sky stations |

Keep-outs: crosswalks, driveways, entrances, sidewalk clear path (at least 1.8 m), lanes,
quay edges, fire-hydrant clearance. Props never overlap each other or buildings.

### 5.7 Megasites (site generators)

| Site | Contents (blockout) | Placement and rules |
|---|---|---|
| spaceport | circular launch pads, launch towers, terminal, hangars, control tower, cargo yard, fuel tanks | coast or city edge, large flat area, linked to a highway and a maglev or sky line; flight cone over the pads limits building heights nearby |
| skyport / AV hub | VTOL pads on a raised deck, terminal | corporate and hub districts, rooftops of tall podiums |
| transit nexus | multi-level station building, ring roads, bus bays, maglev, metro and sky-tube platforms | city center or district junction; all lines meet here |
| freight terminal / container port | berths, gantry cranes, container stacks, rail yard, truck gates | coast or river mouth, deep basin, linked to highway and rail |
| stadium / arena | bowl, plaza, parking | large lot, near transit |
| arcology / landmark tower | spec-defined generator (e.g. megatower) | district focus, axis boulevard |
| temple complex | courtyards, gates, walls, halls | old town, waterside |
| central park / grand plaza | lawns, water, paths, radial walkways | midtown, corporate core |
| attraction | Ferris wheel, observation tower | entertainment districts, waterfront |

Named places from the spec (e.g. "Club Row", "Nightfall Plaza", "Freight Terminal") become
labeled sub-areas with their own features and appear on the 2D map.

### 5.8 Vegetation (blockout primitives, all instanced)

| Type | Blockout | Placement rule |
|---|---|---|
| street_tree | cylinder trunk + sphere or ellipsoid crown | tree pits every 8 to 15 m along wide sidewalks, avenue medians, promenades |
| park_tree | same, larger, size-varied | clustered Poisson scatter in parks and courtyards, open clearings kept |
| conifer | cylinder trunk + cone crown | parks, residential heights, campus grounds |
| palm | tall thin cylinder + flattened spheres or cones for fronds | waterfront, boulevards, spaceport and corporate frontage, beaches |
| shrub / bush | spheres and ellipsoids | park edges, planters, building setbacks, median ends |
| hedge | long box | park borders, enclave walls, plaza edges |
| lawn / ground cover | flat polygon (area, not instance) | parks, medians, courtyards, verges |
| green_roof / roof_garden | flat polygon + small shrubs and trees | podium roofs, terraces, megabuilding decks |
| facade_greenery / hanging_plants | thin boxes or planes on facades | old town, residential, terraced buildings |
| overgrowth | low spheres and planes scatter | vacant lots, under decks, grimy districts |

- Each plant carries a class, height, crown size and a species tag for stage 2.
- A `greenery` value per district (0 to 1) scales density; parks and archetypes set the base.
- Keep-outs: trunks off roads, the sidewalk clear path, quays and junction sight lines; crowns
  at least 1 m from facades and at least 1 m below any deck overhead; no trees over metro
  entrances, stairs or bus stops.
- M16: a ground cover kind for every piece of open land (lawn, meadow, marsh,
  wasteland, dirt, gravel, sand, planted bed, overgrown paving) with its maintenance, wear
  (desire lines), shade, moisture and slope, for stage 2's ground cover and grass (AG13).

## 6. City model (canonical output data)

One JSON document per city (split per district if large), versioned schema. Entities:
`land`, `landmass`, `island`, `sea`, `river`, `channel`, `waterway` (canal, creek, inlet,
basin), `quay`, `bridge` (class, clearance, deck levels), `district`, `place`, `road_node`,
`road_segment` (class, lanes, level, z-profile, cross-section), `junction`, `lane` (lane graph,
for traffic), `walkway` (pedestrian graph, for crowds), `structure` (deck, ramp, column, pylon,
tube, canopy), `transit_line` (mode, altitude profile), `station` (ground, elevated,
sky, underground), `megasite`, `block`, `lot`, `open_space`, `property` (owner tag, member buildings, complex type),
`building` (masses, units, roof items, portals), `skybridge` (end buildings, z, width, levels,
kind), `plant` (class, position, height, crown, species tag), `green_area` (lawn, hedge line,
green roof), `prop` (type, position, yaw, scale), `tile` (256 m grid for later World
Partition streaming).

Ids are stable and readable: `d03.blk017.lot004.bld`, `d03.prop.street_light.0213`.
Coordinates: meters, x east, y north, z up, origin at city center (matches today's `plan.json`).

## 7. Interfaces to later stages
- Stage 2 (assets): every object's semantic type, footprint, bounds, id, style tags and material
  slot names; it swaps blockouts for real meshes without touching layout.
- Stage 3 (looks): light emitter points (street lights, signs, vending machines, windows, transit
  lines), neon and grime fields per district, sky exposure of streets under decks, water surfaces.
- Unreal: lane graph and pedestrian graph (for ZoneGraph and Mass traffic/crowds later), transit
  line splines, tiles for World Partition, prop instances as transforms (for instanced meshes or
  PCG points).

## 8. Builders and outputs
- **Blender blockout** (`blender -b -P citygen/blender/build.py -- city.json`, Blender 5.2):
  collections per district and category; meshes built with bmesh; props as geometry-nodes
  instances on point clouds (one object per prop type per tile, so 100k+ props stay fast);
  flat-color materials by category; custom properties carry type, id and attributes;
  saved `.blend` per city plus optional per-tile files.
- **Previews:** top-down orthographic map, isometric render per district, street-level views
  from a few generated camera points.
- **2D maps:** layered SVG (same layer names as today, plus water, transit and megasite layers)
  and PNG, with district and place labels and a legend, for review and for the old workflow.
- **Exports:** USD (preferred for Unreal) or glTF per tile; prop instances as JSON/CSV;
  lane, walkway and transit graphs as JSON; legacy `corporate_core_plan.json` format for the
  existing Unreal greybox script.

## 9. Validation (runs every time; a failure means the city is not delivered)
- Water: every waterway connects to a river, channel or the sea (except declared basins);
  every district's landmass is reachable by road (bridges); bridge clearance meets the waterway
  class; no columns or pylons inside navigable channels.
- Road graph connected (one component per level system, ramps linking levels).
- Every lot touches a street or alley; every building has an entrance on a walkway.
- No overlaps: building/road, building/water, prop/prop, prop/building, column/lane.
- Elevated roads: grades at most the class maximum, clearances at least 5.5 m, ramps land on roads.
- Transit: grades and curve radii within mode limits; sky lines clear buildings by 10 m or pass
  through a declared portal; every station has street access; every hub is served by its lines.
- Megasites: nothing inside a spaceport flight cone above its height limit; each site linked to
  the transit and road connections its rules require.
- Skybridges and straddle buildings: both ends on floors of buildings tall enough, clearances
  met, no intersection with other buildings or sky lines, length within limits.
- Sidewalk clear path at least 1.8 m everywhere; crosswalks at every signalized junction.
- District area shares within 15% of spec; height ranges within archetype bounds.
- Stats report: road km by class, bridge count, waterway km, transit km by mode, building count,
  floor area, prop counts, open-space and water share.
- Vegetation: plants off roads, clear paths, quays and sight lines; crown clearances to facades
  and decks met.
- Optional art-direction pass: the Claude Code session reviews the previews against the spec
  (and the concept image, if given), adjusts spec parameters (never code), and reruns, at most
  N rounds. No API call.

## 10. Scale and performance targets
- Default city 6 to 12 km², 6 to 10 districts (configurable; one district is about today's
  1 km² Corporate Core).
- Rough counts at that size: 3k to 8k buildings, 200 to 400 km of road edges, 100 to 300 bridges,
  a few hundred thousand prop instances.
- Generation under 10 minutes on the M4 Mac; Blender build under 10 minutes; one district
  regenerates in under a minute.

## 11. Out of scope (v1)
- Textures, detailed models, facades, interiors, materials beyond flat category colors.
- Lighting, atmospherics, post-processing (stage 3).
- (Tunnels and underground metro geometry, terrain relief, stack interchanges and districts on
  several street levels, once listed here, are now milestones M9, M12, M13 and M14 below.)
- Gameplay, AI, traffic simulation (stage 4, lifegen). Unreal-side import tooling is milestone
  M15 below.
- Free-form interchange design (templates only).
- Moving parts (trains, ships, AVs); their routes are exported as data only.

## 12. Milestones (each ends with tests passing, previews committed, and a short report)

| M | Deliverable | Done when |
|---|---|---|
| M0 | Spec schema (water, transit modes, megasites, places), archetype presets, `citygen spec validate` CLI, `citygen` Claude Code skill for prompt (+ image) -> spec, city model schema, 2D debug renderer | 3 different prompts and `reference/nexus_city_concept.webp` produce valid specs |
| M1 | Coast, rivers, delta channels, islands, landmasses, districts, inner waterways, highways, arterials, bridges | water-split cities that read like the concept at macro scale; water and connectivity checks pass |
| M2 | Local streets, alleys, footbridges, junctions, sidewalks, quays, blocks, lots, open space | lots and blocks valid; access checks pass |
| M3 | Buildings (archetypes, heights, ground-floor units, rooftops), complexes (twin towers, clusters, bridged pairs, straddle buildings), skybridges, landmarks, megasites (spaceport, transit nexus, freight terminal, others) | building, skybridge and megasite checks pass; districts read differently in previews |
| M4 | Blender builder, previews, labeled 2D map, USD/glTF tile export, legacy plan.json | full city opens in Blender 5.2 and renders; core pipeline complete |
| M5 | Transit: metro stations, elevated rail, monorail, maglev, sky tubes with tower portals and sky stations; elevated walkways, canopies; skybridges rerouted around sky lines | grade, curve, clearance, portal and access checks pass |
| M6 | Props, vegetation and ground clutter | keep-out, clearance and overlap checks pass; 100k+ instances build fast |
| M7 | Elevated highways with ramps and interchange templates; art-direction loop; Corporate Core pinned import | full validation suite passes on 3 prompts |

M0 to M4 is the core ("prompt -> full blockout city in Blender"). M7 carries the most technical
risk, so it is last: if the budget runs out there, elevated highways fall back to straight
viaducts with simple end ramps from M5.

### After v1

Stage 1 of CyberGen (layoutgen) ended with M15; M16 added the water and ground data stage 2's
water and grass need, and M17 to M21 fix what the first run-through found
(`docs/run_through_1.md`); M17 and M18 are done, the rest planned. The run-through's come first: M17 then M18 (both
change the road network and its junctions), M19 and M21 beside them, M20 after M18 (it fills
under M18's embankments). The later stages are assetgen (unique 3D models and textures for
every building and street element), atmosgen (lighting, sky and atmospherics in Unreal),
lifegen (generated traffic, trains, crowds and animation) and storygen (story, characters,
cutscenes); stages 1 and 2 are reusable generators, not tied to one city.

| M | Deliverable | Done when | Status |
|---|---|---|---|
| M8a | Robustness sweep (`citygen sweep`) and fixes of what it finds | sweep pass rate up, no crashes | done |
| M8b | Transit loops as one simple ring, lines independent of each other, `transit_self_crossing` check | loops simple in every sample; Mac = x86 | done |
| M8c | Transit that passes on a city's first layout (Delta Megacity: 9 tries) and the sweep's remaining transit failures | Delta in at most 2 tries; sweep above 51 of 68 | done (Delta 1 try; sweep 58 of 68) |
| M8d | Trumpet interchange with one loop and one flyover (two-loop fallback) | samples pass; Mac = x86; sweep breaks nothing | done |
| M9 | Tunnels: road tunnels (cut-and-cover under districts and plazas, immersed tubes under rivers, channels and the bay where a bridge does not fit or the spec asks for one) with portals, approach ramps and ventilation buildings; metro tunnel geometry between the station boxes; pedestrian underpasses. Spec: `highways.tunnels` and a per-crossing `tunnel` preference. Checks: grades within the class maximum, cover under ground and under the water bed, portal clearance, no clash with the metro, foundations or basements. Blockout: tube and box geometry, portals, a cutaway render | samples with tunnel crossings pass the full suite; Mac = x86 | done (Nexus City cut-and-cover under Midtown, Greyhook immersed tube; sweep 58 of 68; Mac = x86) |
| M10 | Edit, lock and regenerate: stable ids derived from what an entity is and where it sits (not build order), so unchanged parts keep their ids when another district changes; `citygen build --district NAME` regenerates one district with its border roads fixed (under a minute, scope section 10); pins and overrides for any generated element (keep, move, replace a tower, a plaza, a road); `citygen lock` freezes a city as a versioned release and `citygen model diff A B` lists the entities that changed | a district regenerates alone in under a minute and every entity outside it keeps its id and geometry; a generator change leaves the ids of untouched entities alone; locked cities rebuild byte for byte; Mac = x86 | done (`ids.py`, `edit.py`, `overrides.py`, `lock.py`, `diff.py`; docs/progress/M10) |
| M11 | Gameplay layer: points of interest (bars, clinics, vendors, fixers, hideouts, apartments) chosen from building use, ground-floor units and district archetype, each a named place with its entrances; zones (faction or gang territory, police presence, wealth and danger fields); traffic, crowd and spawn density per street and hour band for lifegen; parking (lots, garages), taxi stands, fast-travel points; sign and ad slots (billboards, holo-ads, neon) on facades and roofs for stages 2 and 3; checks that every point of interest is reachable on foot and by car | every sample city carries the layer, its checks pass, previews show it; the data is in the city model and the exports; Mac = x86 | done (`gameplay.py`, 9 checks, `gameplay.json`; docs/progress/M11) |
| M12 | Stack interchanges: four-level highway-highway crossings (both highways, two levels of directional flyovers at about 18 and 27 m, no loops), plus the turbine variant; chosen where two highways cross and the stack's footprint fits; columns placed among all levels | samples with a highway-highway crossing build a stack; grades, clearances and column checks pass; Mac = x86 | done (no sample had room; the stack demo, the pinned demo with two crosstowns, has one) |
| M13 | Terrain: a height field per city (spec: hills, ridges, cliffs, flat districts), water bodies at their own levels, roads that follow the ground within their grade (cuts, fills, retaining walls, tunnels from M9 through hills), lots and building bases on slopes (terraces, stepped podiums), terrain-aware props and plants, a ground mesh in the blockout | hilly sample cities pass the full suite with every grade and clearance check measured from the ground; Mac = x86 | done (Cragmouth; grade lines on a road graph, retaining walls, bored tunnels, terrain viaducts, seated buildings, draped blockout) |
| M14 | Layered districts: districts stacked on several street levels (an upper deck city over a lower one, Night City style): deck slabs on columns, upper streets, lots and buildings on decks, ramps, stairs and elevators between levels, light wells, a level on every street, lot, walkway and prop, per-level lane and walkway graphs, per-level previews | a layered sample district passes the full suite on every level; walkways connect all levels; Mac = x86 | done (Vesper Bay Decks: a deck over Highcrest, five deck checks; Mac = x86 waits for the deferred determinism check) |
| M15 | Unreal export tool, the last milestone of stage 1 (layoutgen): `citygen unreal <build_dir> <uproject>` imports a built city into an Unreal 5.8 project through editor Python (headless) and the Unreal MCP plugin: a World Partition level from the 256 m tiles, static meshes with collision and per-category materials, props and plants as instanced meshes, citygen ids and types as actor tags, the lane, walkway and transit graphs as data assets for stage 4, a player start; re-importing a build updates it by id (the stable ids of M10). It grows as later stages come online (stage 2 assets replacing the blockout meshes, stage 3 lighting, stage 4 traffic and crowds) | every sample city imports, streams and can be walked (collision) on the Mac; a second import of the same build changes nothing; a regenerated city updates in place | done (headless editor Python, the MCP plugin as the interactive route; every sample imported and checked in play-in-editor; the same build twice writes nothing; a district regenerated with M10 updates only the actors of what changed; docs/progress/M15) |
| M16 | Water and ground detail, for stage 2's real water (AG12) and ground cover (AG13). **Water:** each water body gets `depth_m` and a bed profile (canals flat between their walls, rivers deepest along the centerline, the sea shelving away from the coast; consistent with the bed depths M9's tunnels assume), a flow direction and speed (toward `flows_into` or the mouth, by kind and width; still water for basins and ornamental pools) and, for the sea, an exposure (open water or a sheltered harbor, which sets wave height later); every water edge is split into typed bank segments (quay, canal wall, road embankment, natural bank, beach, marsh edge, riprap) with their heights and widths. **Ground cover:** every piece of open land that is not a building, road, sidewalk or water gets a cover kind (mown lawn, park lawn, meadow, marsh, wasteland and scrub, bare dirt, gravel, sand, planted bed, overgrown paving) with attributes: maintenance (district wealth and archetype), wear (desire lines where the walkway graph and M11's crowds cut across a lawn), shade (buildings, M14's decks), moisture (nearness to water) and slope (M13). **Checks:** every piece of open land covered once, none under a building, road or water; banks cover every water edge; beds clear of tunnels and bridge foundations; M10's regeneration locality. **Blockout:** beds and banks, cover kinds in colors of their own, `preview_water.png`, `preview_ground.png`. **Unreal:** a swim volume per water body (the player swims in a canal instead of falling through it), a material per cover kind | every sample's water and open land carry the new data, its checks pass, the previews show it; a city without water or open land builds as before; Mac = x86 | done (beds, flow and exposure on every water body, typed banks, eleven cover kinds with `paving` added for plazas and yards; the deepest water stops at M9's bed, so 1.5, 5.5 and 10.5 m under the 1.5 m freeboard of a flat city; Mac = x86 waits for the deferred determinism check; `docs/progress/M16`) |
| M17 | Road network repair, from the first run-through (`docs/run_through_1.md`). **Dead ends:** every dead end is deliberate and says so (`attrs.dead_end`: a cul-de-sac with a turning head, the map edge, a quay or water end with a turnaround, a park or plaza gate, the end of a path), or it goes: a street that stops short of a road straight ahead (within 60 m, clear of buildings, water and the lots it would cut) is extended to it and noded, else cut back to its last junction; a clean-up in `streets.py` that removes a piece of a street (for a crossing, its length or its angle) reconnects or removes the rest of it. **Overlaps:** two roads at the same level (within 4 m in height) overlap only inside a junction polygon: a parallel pair is merged or moved apart by their half widths, a side road that runs into an avenue's or a highway's corridor ends at a junction. **Bridges:** road, pedestrian and transit bridges keep their decks, parapets and approaches apart in plan, or their clearance apart in height. **Buildings:** no road, sidewalk, ramp, embankment or deck street corridor overlaps a building mass at the road's own height. **Checks:** `road_dead_ends`, `road_overlaps`, `bridge_clash`, `road_building_clash` (in 3D) | every sample passes the new checks (Delta: 206 dead ends with a road within 60 m ahead, 149 overlapping pairs now); the sweep's pass rate does not drop; Mac = x86 | done (Delta: 239 dead ends inside the map, none tagged, to 68 all tagged, 149 overlapping pairs to 0; every sample passes the 90 checks; sweep 9 of 10 as before; M1b unchanged; Mac = x86 waits for the deferred determinism check) |
| M18 | Junctions and ramps, from the first run-through. **Junction levels:** a junction is one surface that meets every leg where the leg leaves its polygon. Legs are graded to arrive level where their grade allows (at most 2% across the polygon and 10 m out on each leg: M13's `Local.cuts` extended to primary roads, bridge approaches, ramp feet and M7's raised joins); where a leg cannot, the model carries the surface (`Junction.edge_z`: the height of every polygon vertex, from the legs' heights at their cut edges and the curb lines between), so the blockout and AG7 draw the same surface with no step at a leg. **Ramps:** steeper and shorter, leaving less dead space under them: ramps and flyovers at 7% design and 8% at most (5% and 6% now), viaduct runs at 6% and 7%, bridge approaches at 6.5% (5.5% now), M12's stack ramps alike, vertical curves shortened to match; spec knobs `highways.grades`. Under a ramp or approach lower than 4.5 m the model builds an embankment (retained fill, structure `embankment`), not open ground. **Crossings by need:** signals where an avenue or a highway meets a road; at a street crossing in the dense archetypes only where no junction within 120 m along either road is signalized (200 m in the old town and slum archetypes, where most junctions stay unsignalized and unmarked); crosswalks on the approaches of signalized junctions and across avenues, elsewhere unmarked crossings in the walkway graph; widths by class (street 3 m, avenue 4 m, 5 m on a downtown avenue, none on alleys; 4 m on every crosswalk now); per district `junctions.signals` (auto, fewer, none) and `junctions.crosswalks`. **Checks:** `junction_levels` (every leg meets the surface within 2 cm, the surface within its class's cross slope), `ramp_grades`, `crossing_spacing`. **Blockout:** junctions from `edge_z`, embankments | every check passes on the samples, Cragmouth and the stack demo; Delta's 78 junctions with a leg arriving at another height draw without a step; Old Town keeps at most half of its signals and crosswalks; Mac = x86 | done (Delta: Old Town's signalized junctions 117 to 18, with crosswalks 122 to 19; every junction meets its legs with no step, 50 carrying a surface; ramps at 8% at most, runs and approaches 7%; every sample, Cragmouth and the stack demo pass the 93 checks, the deck demo its 98; Mac = x86 waits for the deferred determinism check) |
| M19 | Transit structures, from the first run-through. **Clear of buildings:** a line passes through a tower only at a sky station inside it (a platform AG4 builds as a cut through the floors), else it climbs over or goes round; every transit structure keeps 6 m from buildings, other lines' structures, platforms and canopies in plan, or its clearance in height, measured in 3D along the whole line. **Supports under the structure:** a column stands under the deck or tube (its middle within 0.5 m of the line); where the line runs over a road off its middle, a portal frame (a column at each curb and a cap beam under the deck) or a cantilever bent drawn as one, never a lone column at a curb. **Even spans:** each mode has a span and a longest span (elevated rail 30 and 45 m, monorail 25 and 40 m, maglev 50 and 80 m, sky tube 360 to 480 m, 6 to 8 times fewer pylons than its 60 m now, and 600 m at most as cable-stayed masts); supports are spaced evenly between the fixed points (stations, portals, ends), each moved at most 15% of its span to free ground; where land is not free a longer span drawn as a truss or a cable span, and where the longest span would be passed over water, piers in the water clear of the navigable channel; no gap over the longest span. **Breathing room:** default altitudes up (elevated rail 14 to 20 m, monorail 16 to 26 m, from 10 to 16 and 12 to 22), 8 m clear over a road or sidewalk (5.5 m now) and 6.5 m over a raised road's deck. **Checks:** `transit_supports` (under the structure, spans within the longest), `transit_clearance` with the new distances. **Blockout:** cap beams, masts and piers | every sample passes; on Delta no column stands off its structure (53 monorail columns more than 2 m off now, up to 13.5 m) and no sky tube runs 600 m without a pylon (971 m now); Mac = x86 | planned |
| M20 | Props, plants and signs, from the first run-through. **Under structures:** nothing grows or stands under a raised road, ramp, flyover, guideway, deck or skybridge higher than its underside less 1 m, measured along the structure (the 114 plants that grow into a raised road on Delta: `vegetation.overhead` skips low ramp pieces as embankments that M18 now builds, and no keep-out stops a trunk under them). **On their surfaces:** every prop, plant and roof item stands on a surface the model defines at its height (ground, quay deck, road deck, roof, wall mount) within 2 cm; a quay has one height that the model and AG7 share (railings stand on the model's 1.5 m quay deck while AG7 paves the quay at the ground). **Signs:** far more large ads on the sides and tops of buildings (shop signs and the neon bands over shops stay as they are): large neon billboards on the facades at least 7 times today's (Delta: 252 facade billboards, so 1,800 or more), on mid-rises and towers facing streets, avenues and plazas as well as highways, landscape and portrait, as vertical banners spanning floors and wrapping corners, and the roof billboards lit as neon; holo-boards 2 to 4 times today's (Delta: 63 holo-ads, all over tower roofs, so 130 to 250), projected in front of facades as well as over roofs; placed per district by a spec `signage` (density and kinds; archetype defaults: dense in the corporate core, midtown, markets and entertainment districts, sparse in residential and industrial ones). **Checks:** `prop_support`, `plant_headroom`, M11's sign checks for the new kinds. **Unreal:** the new kinds through M15's prototypes until AG15's assets | every sample passes; Delta has at least 7 times its large facade billboards and 2 to 4 times its holo-boards; Mac = x86 | planned |
| M21 | Cyberpunk massing, from the first run-through: building forms that are not prisms on a podium, so no district (the corporate core above all) repeats itself. Towers twisted (floor plates turning up to 3 degrees a floor), tapered, leaning, stacked as offset boxes, with cantilevered blocks, split and bridged shafts, voids and sky gardens cut through, exoskeleton frames, clustered pods, sloped and cut crowns, masts and halos. Curves as true arcs in the model (`Mass.shape` arcs with center and radius instead of 12, 20 or 32-gons: round and elliptical towers, rounded corners, curved slabs), so stage 2 can draw them smooth. A per district `variety` (how far its towers depart from boxes: high in the corporate core, low in residential districts) and a rule that towers within 150 m never share a form and height band. M3's checks cover the new forms (footprints, clearances, flight cones, skybridge landings, portals); the blockout draws them | Delta's and Vesper Bay's corporate cores have no two neighboring towers of one form; every check passes; Mac = x86 | done (Delta and Vesper Bay corporate cores: 641 and 345 same-form neighbor pairs to 0; Mac = x86 waits for the determinism check) |

## 13. Running it with cloud sessions
- Push this repo to a private GitHub repository (cloud sessions start from it).
- One milestone per cloud session (two for M1, M2 and M7). Brief: "Read docs/citygen_scope.md,
  implement milestone Mn, run tests and validation, commit previews to `docs/progress/Mn/`,
  open a PR with the report."
- Blender may not be available in the cloud; M0 to M3 do not need it. M4+ Blender work is
  verified on the Mac (Blender 5.2) or with a Linux Blender build if the cloud environment
  allows the download.
- Budget control: check spend after M0 and M1, extrapolate, and cut from the end of the list.

## 14. References
- Parish and Müller, "Procedural Modeling of Cities", SIGGRAPH 2001 (L-system road networks with
  global goals and local constraints, land and water maps as input): https://history.siggraph.org/?p=116923
- Chen et al., "Interactive Procedural Street Modeling", SIGGRAPH 2008 (tensor-field streets):
  https://www.sci.utah.edu/~chengu/street_sig08/street_project.htm
- ProbableTrain City Generator (open-source tensor-field city maps with coastlines and rivers,
  SVG/STL export): https://probabletrain.itch.io/city-generator and its algorithm overview
  https://probabletrain.itch.io/city-generator/devlog/140896/algorithm-overview
- Vanegas et al., "Procedural Generation of Parcels in Urban Modeling", Eurographics 2012
  (OBB and straight-skeleton lot subdivision): https://www.cs.purdue.edu/cgvlab/papers/aliaga/eg2012.pdf
- Purdue SIGGRAPH 2011 course, urban layouts: https://www.cs.purdue.edu/cgvlab/urban/sg_2011_course/umc_SG11_02_urban_layouts.pdf
- Epic City Sample, Houdini city and freeway generation (zones, freeway network, data for Mass
  traffic): https://dev.epicgames.com/documentation/unreal-engine/city-sample-quick-start-for-generating-a-city-and-freeway-using-houdini
- Infinigen Indoors (Blender-based procedural generator, constraint placement, USD export):
  https://arxiv.org/pdf/2406.11824
- CityCraft (LLM land-use planning + layout + Blender assembly): https://arxiv.org/abs/2406.04983
- SceneCraft (LLM agent writing Blender code for scenes): https://arxiv.org/abs/2403.01248
- Buildify (geometry-nodes building kit, Blender): https://www.cgchannel.com/2022/07/download-free-blender-3d-building-generator-buildify/
- Visual reference: the Nexus City concept map, `reference/nexus_city_concept.webp` (AI-generated, layout inspiration only), and
  Cyberpunk 2077's Night City (coastal, districts split by water, layered transit).
