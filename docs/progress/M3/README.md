# M3: buildings, complexes, skybridges, landmarks, megasites

M3 adds scope stages 9 (site generators) and 11 (buildings) to `citygen build`. Every M2 lot
gets a building from its district's program, merged lot groups become complexes, the spec's
landmarks take whole blocks near their district's focus, skybridges join tall buildings, and
every megasite reserve is filled by its generator. The model gains `buildings`,
`properties`, `skybridges`, `site_elements`, green roofs in `green_areas`, campus walkways and
bus-bay canopies in `structures`, and the walkway graph gains skybridge decks, elevators, lobby
paths and site paths.

There are 13 new checks, so 44 in all, and every sample passes every one. Each city folder
holds the following; `city_model.json` is not committed, because a build regenerates it byte
for byte:
- `preview_heights.png`: footprints shaded by building height (one blue ramp, square-root
  scale), skybridges in gold, landmarks labeled;
- `preview_massing.png`: isometric massing of the whole city from the south-south-west, walls
  tinted by district archetype, landmarks white, plus four district close-ups;
- `preview_map.png` and `preview_detail.png`: the M2 map and street-level insets (unchanged
  drawing, rebuilt);
- `report.json` and `report.txt`: the checks plus a stats table (now with buildings);
- `trace.json`: stage hashes.

The specs are unchanged (`docs/progress/M1a2/`, Nyxllor in `cities/nyxllor/`).

STATS_TABLE

## How a lot gets its building (`citygen/buildings.py`)

- **Frame and front.** The facade sits on the lot's main frontage: `frontage[0]` (the longest
  road edge), unless a frontage of a better class (avenue over street over pedestrian street
  over alley and service lane) is at least half as long, and never a highway when the lot has
  another frontage. The longest straight edge of that line sets the building's local frame
  (u along the street, v into the lot).
- **Buildable area.** The lot minus the side setback and minus a strip along every frontage as
  deep as that road class asks, per archetype (corporate core: avenue 5 m, street 3.5 m,
  pedestrian 2 m, alley 0; old town and markets build to the street line; port 8 m for truck
  aprons; residential heights 5 to 6 m front yards and 3 m side yards, less on narrow lots),
  minus junction corners, crosswalks and open space that some M2 lots graze. Of several pieces
  the one on the street is kept.
- **Program.** Each archetype has a mix of building archetypes, a floor height, podium floors,
  tower sizes, unit widths and uses, awning and sign rates, a roof kit and green-roof chance:

  | Archetype | Buildings | Floors |
  |---|---|---|
  | corporate_core | podium towers (podium 3 to 5 floors, 6 on avenues; tower 20 to 46 m wide with setback crowns, spires on the tallest), slabs, terraced towers, parking structures | 4.0 m |
  | megablock_residential | megabuildings (block-filling, atrium void, decks across it, stepped tiers), slabs (with a second bar and a connecting wing on deep lots), courtyard blocks, podium towers | 3.2 m |
  | midtown_mixed | perimeter buildings (street wall 14 to 20 m deep around the M2 courtyards), podium towers, terraced | 3.5 m |
  | entertainment_market | shopfront rows, shanty stacks, small podium towers | 3.5 m |
  | old_town | shopfront rows (some with a top floor set back), shanty stacks (recessed ground floor, two or three stacks of different heights, rooftop shacks), small courtyard houses | 3.0 m |
  | industrial_port | warehouses with loading docks, open sheds, container yards (office plus stacks) | single volume |
  | residential_heights | villas, terraced, slabs, courtyard blocks | 3.4 m |
  | research_campus | labs (courtyard labs when large), terraced, slabs | 4.0 m |
  | transit_hub | podium towers, slabs, parking, perimeter | 3.5 m |
  | spaceport | hangars, slabs, parking, sheds | 4.0 m |

- **Heights.** A height field per district: closeness to the district focus (the megatower
  when there is one), smooth value noise, lot size, an avenue bonus and a small draw, skewed
  so that few buildings reach the top of the archetype range; floors on the building's grid,
  kept within the district's `height_m`. Near a spaceport the flight cone caps heights: its
  limit over the cone's ground footprint, rising 1 m per 1 m away (measured from the nearest
  point of the lot).
- **Ground floor.** Facade runs are the footprint edges that face a frontage (within its
  setback plus 4.6 m and parallel to it). Runs on avenues, streets and pedestrian streets are
  split into units of 4 to 12 m with uses by archetype (food, convenience, bar, clinic,
  cyberware, pawn, club, arcade, laundromat, lobby), awnings and signs; the main entrance is
  on the best run, alleys and service lanes get service entrances, warehouses loading
  entrances and docks, parking structures garage entrances. Each entrance records its nearest
  ground walkway. A box- or slab-type building that ends up with no street facade (curved
  frontage, a deep or odd lot) is rebuilt to follow the frontage line.
- **Rooftops.** Mechanical penthouses, helipads (corporate towers of 150 m and more), AV pads
  (transit hubs, corporate), antennas, water tanks, billboards (by neon), AC units on roofs and
  podiums, each placed only where the roof holds its footprint; podium roofs become roof
  plazas (corporate core, transit hub) or roof gardens, low flat roofs green roofs by
  greenery.

## Complexes and landmarks (`citygen/complexes.py`)

- **Twin towers:** two mirrored towers on a shared podium (split between the two buildings),
  same height and crown, a two-level stack skybridge at about 45% of the height.
- **Tower clusters:** three or four towers of stepped heights (100, 84, 70, 58%) in a row on a
  shared podium, bridges between neighbors.
- **Megabuilding campuses:** a megabuilding on the largest lot, satellite towers in its frame
  on the sides that face it, an open deck at a third and an enclosed bridge at two thirds of
  the lower height.
- **Campuses:** labs around a lawn on the union of the lots, a covered walkway loop
  (`structures`, canopy).
- **Bridged pairs:** two slabs facing each other across the street the lots share, one or two
  skybridges over it.
- **Straddle buildings:** two legs facing the shared street and a span over it, 3 floors deep,
  its underside at least 5.5 m (plus a 1 m structure) above the road, clear of junctions and
  other roads.
- A merged group whose lots cannot hold its complex moves to the nearest block of free lots
  (or the nearest other pair of lots facing each other across a street); the report notes it.
- **Landmarks** take a whole block near the district focus (several landmarks of a district
  spread at least 140 m apart): the megatower as three arms 120 degrees apart on a hexagonal
  core, in four setback tiers with a crown and a spire; spires as octagons in tapering tiers;
  an arcology as a stepped ziggurat with an atrium; observation towers, monuments, temples,
  and any other kind as a tapering tower. A ferris wheel (or the attraction megasite's wheel)
  is a vertical ring: only the part of its rim lower than 6.5 m must stand on its site, the
  rest may pass over streets and roofs, and the lots under it stay lower than the rim (a lot
  where the rim comes down to its roofs stays open).

## Skybridges (`citygen/skybridges.py`)

Between facing (antiparallel) facades of two masses that both reach the deck: 8 to 80 m,
within 14 degrees of perpendicular to both, the deck on a common multiple of both floor
heights, at least 5.5 m (plus the deck structure) over every road and the navigable clearance
over water, through no building mass and no other deck at the same level. Complexes ask for
their bridges first; then each district adds bridges between its tall buildings by
`skybridge_density`, shortest first, at most two or three per building: enclosed walkways in
the corporate core, midtown, transit hub and campus, open decks in the megablocks and markets,
low catwalks and cable bridges between shanties in a grimy old town. Every skybridge joins the
walkway graph: its deck, an elevator at each end, a lobby path to the building's main entrance
and a path from that entrance to the nearest ground walkway (split there).

## Megasites (`citygen/sites.py`)

SITES_TABLE

Every generator works in the reserve's own frame (long side, centered), keeps a 4 m margin,
avoids the roads and junctions that enter the reserve, and places nothing on top of anything
else. Site buildings and park paths join the walkway graph.

## Checks added (scope section 9, M3 parts)

| Check | Rule |
|---|---|
| building_footprints | masses below 5.5 m inside the property's lots (megasite buildings: the reserve; landmarks: also their host open space; wheels: the rim below 6.5 m); straddle spans only over a street, clear of junctions, 5.5 m above it |
| building_clear_zones | no ground mass on a road, junction, sidewalk, crosswalk, water, open space, or another megasite's reserve or flight cone |
| building_overlaps | no two buildings, site elements or skybridge decks overlap in plan and height (wheels by the true height of their rim) |
| building_heights | heights within the district's archetype range (under a flight-cone cap where one applies, one floor of slack under it; parking only under the top); landmarks and megasites aside |
| building_entrances | a main entrance on the facade, within 20 m of a ground walkway or a shared alley, service lane or pedestrian street; megasite buildings and landmarks joined to the walkway graph by a path |
| ground_floor_units | units 4 to 12 m wide, on the ground facade, facing one of the lot's frontage roads |
| roof_items | every roof item stands on a mass top of its building that holds its footprint |
| complexes | every merged lot group built as its complex (count per district) and each complex by its rules (two equal bridged towers, three stepped bridged towers, satellites bridged to the megabuilding, three labs and a covered walkway, a skybridge across a street, a span) |
| skybridges | 8 to 80 m, ends on facades of masses that reach the deck, level on both floor grids, within 15 degrees of perpendicular, 5.5 m over roads, navigable clearance over water, 2.5 m over the ground, joined to the ground walkways |
| landmarks | every landmark of the spec built in its district with its kind and height (or its recorded flight-cone cap), the megatower with three arms |
| megasite_contents | every reserve filled, with the parts its kind needs, all inside the reserve |
| megasite_heights | nothing inside a flight cone above its limit, nothing near one above the 45 degree surface |
| megasite_access | every megasite within 40 m of a road, site paths joined to the walkways (transit links: M5) |

## Speed

DETERMINISM_AND_SPEED

## Still weak

GAPS
