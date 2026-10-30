# AG5: types, landmarks and slopes

Builds with `assetgen build` (3 or 4 workers) and textured renders with `assetgen materials
preview` (Blender 5.2, EEVEE). Full record: [`docs/assetgen_milestones.md`](../../assetgen_milestones.md),
AG5.

## Images

- [`landmarks_8k.jpg`](landmarks_8k.jpg): the heroes (8K): Vesper Bay's megatower over the
  Corporate Core, Nexus City's spires, the arcology (Vesper Bay with The Stacks' landmark an
  arcology, built for this image) and Greyhook's wheel.
- [`cragmouth/slopes_8k.jpg`](cragmouth/slopes_8k.jpg): Cragmouth's Old Quarter on its hill
  (8K): stepped plinths, doors and shopfronts at grade, retaining skirts.
- [`eras.jpg`](eras.jpg): one district per era, textured (Vesper Bay's eight districts, Nexus
  City's Transit Nexus and Midtown).
- [`review/`](review): the two art-direction rounds (below).
- [`wip/`](wip): work in progress (untextured shells: the wheel, Nexus City's heroes, type
  generators, dormers, a slope).

## Art-direction rounds on Vesper Bay

[`review/`](review): the two rounds' sheets (`review.md`), notes and before and after
images.

## Numbers per city

Each from main's city model; every assetgen check passes in each (the fourteen building
checks, AG7's streets, AG8's props, AG6's materials). Vesper Bay with its asset spec (round
2), Vesper Bay Decks with Vesper Bay's, built for the checks only; the others with the era
presets.

| | Vesper Bay | Greyhook | Cragmouth | Delta Megacity | Nexus City | Vesper Bay Decks |
|---|---|---|---|---|---|---|
| Buildings | 5,793 | 2,671 | 6,777 | 5,417 | 6,519 | 5,856 |
| Shell triangles | 34.52 M | 19.05 M | 37.23 M | 35.21 M | 35.35 M | 34.78 M |
| Instanced parts | 1.30 M | 0.83 M | 0.96 M | 1.23 M | 1.11 M | 1.23 M |
| Built by a type generator | 2,598 (17 generators) | 1,426 (14 generators) | 2,520 (10 generators) | 2,099 (10 generators) | 2,757 (19 generators) | 2,546 (17 generators) |
| Type features | 8,170 | 4,227 | 11,882 | 10,155 | 11,107 | 9,373 |
| Heroes | megatower | wheel | megatower | megatower | megatower, spire x3, wheel | megatower |
| Families | 8 | 7 | 4 | 7 | 12 | 8 |
| twin towers, clusters, campuses, bridged pairs | 1, 1, 1, 0 | 0, 1, 0, 0 | 0, 0, 0, 1 | 1, 1, 1, 1 | 1, 2, 1, 1 | 1, 1, 1, 0 |
| megabuilding campuses, megasites, straddles | 1, 3, 1 | 3, 2, 1 | 0, 2, 1 | 0, 3, 0 | 0, 6, 1 | 1, 3, 1 |
| Dormers | 331 | 401 | 157 | 154 | 340 | 280 |
| Landing doors (left open in the collision) | 513 of 516 | 338 of 340 | 533 of 558 | 647 of 652 | 468 of 474 | 531 of 532 |
| Sky platforms beside a tower | 0 | 0 | 0 | 2 | 0 | 0 |
| On a stepped plinth | flat | flat | 4,724 | flat | flat | flat |
| stepped facades, retaining skirts |  |  | 33,923, 30,123 |  |  |  |
| doors and shopfronts lowered, raised, narrowed |  |  | 5,589, 4,502, 634 |  |  |  |
| buried by the hill (counted) |  |  | 2,196 |  |  |  |
| `assetgen build` | 2m29s | 1m19s | 4m31s | 3m02s | 3m09s | 4m20s |

## What the Unreal check should look at

- **Heroes**: the megatowers (Vesper Bay, Nexus City, Cragmouth, Delta Megacity), Nexus
  City's three spires and Greyhook's and Nexus City's wheels: actors tagged `cg.hero=<kind>`,
  their materials `MI_buildings_<slot>_<era>_<id>` reading `T_city_hero_<id>` on UV1
  (grime at the foot and washed down under every setback, leaks under the sills, wear at
  the corners), the light seams and halo in the accent colour; the masters rebuilt
  (`STAGE2_VERSION` 6) and every other building unchanged by `HeroMaskOn` 0.
- **Slopes** (Cragmouth): buildings tagged `cg.plinth=<m>`; the stepped plinth meeting the
  terrain heightfield with no gap and no floating corner (traces at a plinth's corners and
  steps), shopfronts and doors at grade on the downhill side, retaining skirts uphill.
- **Landing doors**: walk across a skybridge into its landing door (the hull notched 2.5 m
  at the door, `collision.VESTIBULE_MM`); Vesper Bay has 513 landing doors.
- **Sky stations beside a tower** (Delta Megacity, Corporate Core and Midtown): the platform
  deck beside the tube, reaching the tower's wall (part of the building's shell).
- **Types**: open sheds (walk under the roof between the columns), temple colonnades,
  control tower cabs and vaulted terminals in the spaceports, hangar doors, parking ramps,
  shanty lean-tos and fire escapes in The Stacks: collision as before (hulls of the
  masses; the parts have none).
