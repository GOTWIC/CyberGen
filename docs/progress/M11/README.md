# M11: gameplay layer

M11 adds the gameplay layer to every city: named points of interest with their doors, faction
territories and police precincts, wealth, danger and police fields, traffic, crowd and spawn
density per street and hour band for lifegen, parking, taxi stands and fast-travel points,
and sign and ad slots for stages 2 and 3. It runs last, on the finished city
(`citygen/gameplay.py`, after props), and adds nine checks (`citygen/gameplay_checks.py`,
75 in all). The data is in `city_model.json` (eight new collections) and in a new export,
`gameplay.json`, beside the blockout exports.

__RESULTS__

## What the stage builds

| collection | what | from |
|---|---|---|
| `factions` | gangs, corporations, the city police (`faction.<kind>`, name, color, home district, zones) | a gang per district with `danger` 0.45 or more (or the spec's `faction`), a corporation for corporate, campus, port, transit hub and spaceport districts, else the police |
| `zones` | territories (`zone.territory`: polygons, blocks, faction, how firmly held, contested or not) and police precincts (`zone.police`: the district, presence, station building) | 1 to 4 turfs per district (one per 0.6 km2), seeds by farthest-point sampling over the block centers, cells cut by straight bisectors; a rival gang takes the turf nearest its home district (within 3 km) |
| `fields` | `field.wealth`, `field.danger`, `field.police`: 32 m rasters over the bounds, values 0 to 1 | the district values blended with an integer box blur (3 cells), then: police up near stations, precinct stations and avenues; wealth up near parks, plazas and water and landmarks, down under raised highways and in alleys; danger up in alleys and under raised highways, down where police and wealth rise |
| `pois` | `poi.bar` (bar, club, arcade), `poi.clinic` (clinic, ripperdoc), `poi.vendor` (food, convenience, pawn), `poi.apartment` (capsule, studio, apartment, penthouse by wealth; a floor), `poi.hideout` (warehouse, squat, back room), `poi.fixer` (a table in a bar) | ground-floor units of M3 by use, a budget per km2 by archetype and spacing (bars 60 m, clinics 120 m, vendors 50 m apart), ranked by a hash of the unit, the street class and the danger or wealth at the door; apartments in residential, mixed and hotel buildings; a hideout in each gang turf (two over 0.8 km2), warehouses and stacks first; one or two fixers per district in its most dangerous bars |
| `densities` | per road segment: speed, and per hour band (night 0-6, morning 6-10, day 10-16, evening 16-20, late 20-24) traffic (vehicles per hour), vehicles, pedestrians, gang members and police per 100 m | lanes times a per-lane capacity and peak use by class, an hour profile by archetype, the shops on the segment, stations within 150 m, the danger and police fields, whether a gang holds the turf |
| `parking` | `parking.garage` (parking structures; underground garages under big towers), `parking.lot` (deep front setbacks of warehouses, sheds, hangars, labs and terminals), `parking.street` (curb parking lanes) | capacities from floor area (28 to 30 m2 a space), lot area (25 m2) and curb length (6.5 m) |
| `travel_points` | `travel.taxi_stand` at stations, hotels, landmarks and bars of nightlife districts (250 m apart, one per road segment); `travel.fast_travel`, one to four per district (stations, places, landmarks, signalized junctions; 350 m apart) | |
| `sign_slots` | `shop_sign` (one per M6 sign prop, blade or flat), `billboard` (M3 roof billboards, and facade panels facing highways and avenues), `holo_ad` (over tower roofs without pads), `neon` (vertical bands at a corner of mid-rise facades) | sizes, facing direction, content (shop use, ad, corporate, district) and the evening audience of the street it faces; new slots start above the building's shop signs and keep 3 m from skybridge ends |

Every point of interest, parking entrance and travel point carries an `Access`: the door, the
ground walkway it opens on (within 40 m, in the walkway component of its landmass), the drive
lane a car stops on (a ground lane of a local road in the lane graph's largest strongly
connected part, within 60 m on the road the door faces, else 150 m) and the curb point on
that lane, which must lie on the door's walkway component. A candidate without one is not
placed, so the two reachability checks hold by construction and the layer never makes a city
retry.

Names come from fixed word lists by hash and are unique in the city (no two generated
factions share a word). Ids come from what a place is and where it sits: `<building>.u03.bar`,
`<building>.apt012`, `<building>.hideout`, `<segment>.density`, `<segment>.taxi`,
`<prop>.slot`, `<district>.turf2`; no build counters.

## Spec

`districts[].wealth`, `danger`, `police` (0 to 1; archetype defaults in `presets.py`) and
`faction` (a name; districts with the same name share the faction). Existing specs need no
edits; the filled spec gains the three values per district.

## Checks

| check | what |
|---|---|
| `poi_reachable_foot` | every door on a ground walkway within 40 m in the main walkway component of its landmass; the curb on the same component |
| `poi_reachable_car` | every curb lane a ground drive lane of a local road in the lane graph's largest strongly connected part; the curb on the lane within 150 m of the door |
| `poi_places` | names present and unique (with travel points), doors within 1.5 m of the building's facade, units of the right use, fixers in an existing venue, hours and zones valid |
| `territories` | each district's territories cover it without overlap and hold each block once; a police precinct per district; factions and zones refer to each other |
| `gameplay_fields` | the three rasters cover the bounds, values 0 to 1 |
| `street_density` | a row per road segment with five bands, nothing negative, traffic within the lanes' capacity, no cars on pedestrian ways |
| `parking` | capacity, garages in their building, lots clear of buildings and carriageways, curb parking where the road has parking and drive lanes |
| `travel_points` | a fast-travel point in every district with streets, taxi stands 250 m apart, each on its sidewalk |
| `sign_slots` | one slot per sign prop and roof billboard, facade slots on a facade of their building above its shop signs and apart from each other, holo-ads over their roof |

__SECTIONS__
