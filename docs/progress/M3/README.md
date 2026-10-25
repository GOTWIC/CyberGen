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

| City | Buildings | Floor area km2 | Tallest m | Skybridges (km) | Ground-floor units | Roof items | Green roofs | Complexes | Landmarks | Megasites |
|---|---|---|---|---|---|---|---|---|---|---|
| Nyxllor | 5887 | 29.7 | 480 | 230 (2.57) | 17260 | 15997 | 503 | 5 | 1 | 3 |
| Saltreach Free Port | 3182 | 14.0 | 292 | 180 (1.95) | 10450 | 8919 | 390 | 2 | 0 | 3 |
| Delta Megacity | 5454 | 22.8 | 480 | 328 (3.78) | 18123 | 15896 | 449 | 4 | 1 | 3 |
| Nexus City | 6409 | 19.5 | 480 | 255 (3.04) | 19947 | 17390 | 622 | 6 | 4 | 7 |
| Greyhook (peninsula) | 2455 | 19.4 | 237 | 73 (1.03) | 6492 | 6811 | 326 | 5 | 1 | 3 |

Districts read differently by height, coverage and floor area ratio (FAR, floor area over lot
area):

| City | Median / p90 / max building height, coverage, FAR by district |
|---|---|
| Nyxllor | Corporate Core 132 / 192 / 480 m, 80%, 13.1; The Stacks 157 / 182 / 234 m, 53%, 20.9; Highcrest 20 / 24 / 44 m, 33%, 1.9; Old Town 15 / 21 / 27 m, 96%, 3.4; Neon Strand 21 / 31 / 42 m, 97%, 4.7; Vess Docks 12 / 15 / 16 m, 28%, 0.3; Launch Key 21 / 32 / 40 m, 14%, 0.5; Scholar Isle 28 / 40 / 72 m, 32%, 2.5 |
| Saltreach Free Port | Crown Island 128 / 172 / 292 m, 81%, 14.0; Kettle Island 11 / 16 / 16 m, 30%, 0.3; Westreef 15 / 21 / 27 m, 96%, 3.4; Lumen Key 28 / 40 / 60 m, 27%, 2.1; Palm Key 24 / 24 / 44 m, 25%, 1.6 |
| Delta Megacity | Transit Nexus 46 / 70 / 105 m, 72%, 6.1; Midtown 42 / 66 / 119 m, 68%, 7.3; Corporate Core 132 / 188 / 480 m, 83%, 15.1; Old Town 15 / 21 / 27 m, 96%, 3.5; Industrial Port 11 / 16 / 16 m, 32%, 0.3; Research Campus 28 / 40 / 64 m, 35%, 2.7 |
| Nexus City | Corporate Core 120 / 184 / 480 m, 80%, 12.3; Transit Nexus 49 / 66 / 102 m, 70%, 6.5; Aurora Spaceport 20 / 32 / 32 m, 26%, 0.5; Neon Market 21 / 32 / 46 m, 96%, 4.7; Northridge 24 / 24 / 51 m, 34%, 2.2; Midtown 38 / 63 / 119 m, 70%, 7.6; Old Town 15 / 21 / 27 m, 95%, 3.3; Harbor Industrial 12 / 16 / 16 m, 31%, 0.3; Silver Island 32 / 52 / 60 m, 32%, 2.7 |
| Greyhook (peninsula) | Wallgate Heights 20 / 24 / 48 m, 34%, 2.0; Neckgate 32 / 60 / 112 m, 72%, 5.1; The Stacks 160 / 186 / 237 m, 53%, 19.6; Lantern Strip 21 / 32 / 120 m, 97%, 4.7; Eastside Docks 11 / 16 / 16 m, 31%, 0.3; Hook Spaceport 24 / 36 / 40 m, 24%, 0.7 |

Landmarks: the megatower of Nyxllor, Delta Megacity and Nexus City (Nexus Spire, 480 m), the
three Nexus spires (Kaze Tower 300 m, Helios Tower 260 m, Mirai Tower 234 m: asked 290 m,
capped by the Aurora Spaceport flight cone, as the report notes) and the Lantern Wheel of
Greyhook (120 m). Megasites filled: three spaceports (Launch Key, Aurora, Hook), four transit
nexuses, four freight terminals, two skyports, a stadium (Neck Arena), two central parks (one of
them Nexus City's Central Plaza), two temple complexes and the Neon Wheel attraction.

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

| Site | Contents (as built in the samples) |
|---|---|
| spaceport | 1 to 4 launch pads (with launch towers) at the end toward the flight cone on a concrete apron, 1 to 3 hangars, a terminal and a control tower (all under the height limit), a cargo yard of container stacks, a farm of six fuel tanks |
| transit_nexus | a station hall (24 m) with platform decks per mode of the lines that serve it: elevated rail and monorail beside it, maglev on top, sky tube at its altitude on a station tower; metro entrances; a row of bus bays under a canopy; a drop-off loop; plazas |
| freight_terminal | berths along the quay side (the reserve's side nearest the water), 2 to 4 ship-to-shore gantry cranes per berth (legs and boom), container stacks in rows, a rail yard, a truck gate with gate house and canopy, an office, warehouses |
| stadium | a bowl of two stands and a roof ring (elliptic rings), the pitch, a plaza around it, parking structures at the ends |
| central_park / grand_plaza | a central plaza with a fountain, a ring path and six (eight) radial paths to the reserve edge joined to the sidewalks, a pond, pavilions, lawns; a grand plaza is paved, with a 30 m monument and kiosks |
| arcology | a stepped ziggurat with an atrium (the landmark generator on the reserve) |
| temple_complex | a perimeter wall with a gate (posts and lintel), a main hall on a platform under two roof tiers, two side halls, a five-tier pagoda, the courtyard |
| attraction | a ferris wheel (up to 110 m) on its platform, a plaza, kiosks |
| skyport | a 32 m deck with VTOL pads (AV pads on its roof) and a terminal on top |

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

## Determinism and speed

The M3 stages run inside `geom.canonical()` like M2. Every lot, complex and landmark draws from
its own generator (district seed, lot index), so districts and lots regenerate locally. Local
frames turn with `dmath` angles; points are computed in separate Python operations and
rounded to the 0.01 m grid; every shape decision is an exact predicate on grid geometry
(`covers`, interior `relate`) or plain arithmetic. GEOS output order never reaches a
decision: STRtree hits are sorted, ties go to the lower id, polygon parts come out of
`geom.parts` in a fixed order. Oriented bounding boxes come from `massing.obb_angle` (every
convex hull edge tried in plain arithmetic, the first of equal areas wins) instead of GEOS's
minimum rotated rectangle, whose convex hull sorts points with `std::sort`. Circles and
regular polygons are built from `dmath`, never from round buffer joins.

The lot jobs run in worker processes: landmarks and complexes per district, the other lots in
chunks of 300, then skybridges per district; the chunking does not depend on the worker
count, and every job returns validated model rows. While the workers build the lots, the main
process runs the M1 and M2 checks on the M2 model (M3 changes none of their inputs but the
walkway graph, whose check runs again on the final model). `tests/test_buildings.py` checks
that a fresh `run_checks` on the final model gives the same checks.

Verification on the final code: all five models and stage traces are identical between the
pinned x86_64 Linux wheels (libstdc++ GEOS) and GEOS 3.14.1 rebuilt with clang 18 against
libc++ (Ubuntu's source of the same release, swapped into the shapely 2.2.0 wheel), and
Greyhook gives the same bytes with one worker and another `PYTHONHASHSEED`
(`citygen trace diff`: no difference in any entry). `tests/test_buildings.py` also builds a
test city with 1 and 3 workers and with 2-ULP noise on what GEOS computes inside the M3
stages, and expects the same bytes.

| City | Trace entries | Model sha256 (x86_64, libstdc++ GEOS) | libc++ GEOS |
|---|---|---|---|
| Nyxllor | 5908 | `11586629e5b833b74fd9928a280030753c4975342d757d951391c4df1e86e333` | same |
| Saltreach Free Port | 61 | `92b71ab7985c37f6f811f92711d80ab2064b75236ce1d588ab4f630c64cc356f` | same |
| Delta Megacity | 2775 | `d7df4db62d678b96d4e86443c01a7d1509fccb2a0eafbb74cc66554bb0c39103` | same |
| Nexus City | 8556 | `cf095fc347ed855cc845a07b216dd1b6c9332eb9381db091b5fa2bd5489b7e25` | same |
| Greyhook | 253 | `13e3a3000db8c7f5843a0fe5d836c508130c48ec51ac1f8de3e2a3d5475fe2f6` | same |

Build times on the 4-core x86_64 cloud container (default workers). The CLI time includes the
four previews and `--trace`. The M3 columns are wall-clock seconds of the buildings stage
(`Built.m3.info["seconds"]`, kept out of the report so that reports stay reproducible): the lot
jobs in the workers (their summed CPU time in brackets; the M1 and M2 checks run in the main
process meanwhile and take most of that wall time), skybridges, and megasites plus walkways.

| City | CLI build | M3 lot jobs (CPU) | Skybridges | Megasites + walkways |
|---|---|---|---|---|
| Nyxllor | 64 s | 6.2 s (19.5 s) | 1.0 s | 1.0 s |
| Saltreach Free Port | 31 s | 3.6 s (11.0 s) | 0.7 s | 0.5 s |
| Delta Megacity | 66 s | 5.9 s (17.3 s) | 1.4 s | 0.8 s |
| Nexus City | 77 s | 6.6 s (21.9 s) | 1.4 s | 1.7 s |
| Greyhook | 28 s | 2.8 s (9.9 s) | 0.5 s | 0.4 s |

`build_city` alone (no previews, no trace) takes about 54 s for Nexus City, the largest
sample, under the 60 s budget that `tests/test_build.py` asserts.

## Still weak

- **Megablocks read as one wall.** Megabuildings fill their lots at 120 to 250 m (the
  archetype range) with stepped tiers and atriums; seen from afar The Stacks is still a
  single purple mass. Gaps between megabuildings, elevated decks between them and more
  height contrast would help (decks are only drawn across atriums).
- **Complexes often move.** M2's merged lot groups are adjacent lots near the district center
  whose union is often too narrow for towers, or lots across a street that are not opposite
  each other; most twin towers, clusters, bridged pairs and straddle buildings are built on a
  nearby block or pair instead (the report notes each).
- **Straddle buildings over canals** are not built (only over streets, alleys, service lanes
  and pedestrian streets).
- **Facade on the best frontage, not always `frontage[0]`.** The longest road edge is used
  unless a better road class is at least half as long, and never a highway when the lot has
  another frontage; on huge, irregular lots (spaceport and port districts) some buildings
  stand far from the street and reach it by a path (driveway) instead.
- **Rectangles.** Towers, slabs, boxes and site parts are oriented rectangles in the lot's
  frame; curved lots get a straight-fronted building with a setback that widens along the
  curve. Podiums, shopfront rows and perimeter blocks follow the lot.
- **Height field.** Heights come from the district focus, noise, lot size and avenue frontage;
  there is no skyline design per district (for example a ridge along an axis boulevard) and
  no relation to transit stations yet (M5).
- **Megasites** are templates in the reserve's frame: a shrunk reserve (the samples' spaceports
  and freight terminals are 50 to 75% of their asked area) gets fewer pads, cranes and stacks.
  Transit platforms are placeholders until M5 routes the lines; sky-tube portals through towers
  and skybridges rerouted around sky lines are M5 too.
- **Flight cones** cap heights by a 45 degree surface around the cone footprint; the Nexus City
  corporate core lies within 300 m of the Aurora Spaceport cone, so Mirai Tower is capped at
  234 m and nearby towers lose height.
- **Roof and ground items** are blockout boxes (AC units, tanks, billboards, pads); signs and
  awnings are flags on the units for M4 and M6 to build.
- **Wheels** are vertical rings: in the model a thin plan with `shape: ring`; the massing
  preview draws the rim and spokes.
