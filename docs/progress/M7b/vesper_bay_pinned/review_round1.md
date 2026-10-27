# Art direction: Vesper Bay Pinned, round 1 of at most 3

Checks: all passed.

## Spec changes since the last round

- (first round)

## City

| Number | This round | Last round |
|---|---|---|
| water_share | 0.293 | - |
| boundary_on_water | 0.531 | - |
| road_km | 181.1 | - |
| bridges | 8 | - |
| elevated_km | 1.69 | - |
| interchanges | 2 | - |
| buildings | 6433 | - |
| tallest_m | 480.0 | - |
| transit_km | 20.6 | - |
| instances | 78885 | - |

## Districts

| District | Archetype | Share (target) | Median / max height m | FAR | Open share |
|---|---|---|---|---|---|
| Corporate Core | corporate_core | 0.0936 (0.0936) | 130.0 / 480.0 | 20.8 | 0.628 |
| The Stacks | megablock_residential | 0.172 (0.169) | 150.4 / 233.6 | 10.1 | 0.0983 |
| Highcrest | residential_heights | 0.144 (0.141) | 20.4 / 37.4 | 1.93 | 0.176 |
| Old Town | old_town | 0.137 (0.141) | 15.0 / 26.6 | 3.12 | 0.0621 |
| Neon Strand | entertainment_market | 0.128 (0.127) | 24.5 / 45.5 | 4.96 | 0.062 |
| Vess Docks | industrial_port | 0.179 (0.183) | 12.7 / 16.0 | 0.34 | 0.0407 |
| Launch Key | spaceport | 0.0732 (0.0732) | 24.0 / 36.0 | 0.47 | 0.464 |
| Scholar Isle | research_campus | 0.0732 (0.0732) | 32.0 / 56.0 | 2.35 | 0.278 |

## Previews to open

- `preview_map.png`: water, districts and primary roads: placement, shares, bridges
- `preview_detail.png`: four 400 m insets: street patterns, junctions, lots
- `preview_heights.png`: footprints by height: skyline, landmarks, district grain
- `preview_massing.png`: isometric massing: complexes, megasites, skybridges
- `preview_transit.png`: transit lines, stations, supports, portals
- `preview_props.png`: street level: lights, trees, parked cars, clutter
- `preview_elevated.png`: road levels: viaducts, interchanges, columns

## If something reads wrong, change the spec (never the code)

| What you see | Spec parameters |
|---|---|
| a district on the wrong side of another or of the water | `districts[].placement (north_of, coast, along_river, on_island, separated_by)` |
| a district too big or too small | `districts[].area_share` |
| too much or too little water between districts | `water.district_separation, water.boundary_water_share, districts[].water_separation` |
| a river entering or leaving in the wrong place | `water.rivers[].from / to (with `at`), meander, width_m` |
| an island missing, too small or in the wrong spot | `water.islands[].position, setting, area_km2; water.coast.sea_share` |
| the wrong highway shape or exits | `highways.pattern, highways.exits` |
| not enough or too much viaduct | `highways.elevated_share` |
| the same street grid everywhere, or the wrong angle | `districts[].street_pattern, grid_angle_deg, block_size_m` |
| a skyline too flat or too uniform | `districts[].height_m, landmarks, complexes` |
| too few canals, or canals in the wrong district | `districts[].waterways (style, density, named)` |
| streets too clean or too gritty, too dark or too green | `districts[].grime, neon, greenery` |
| a transit line doubling back or missing a stop | `transit.lines[].route (order matters for fast modes), mode` |
| a megasite in the wrong place or the wrong size | `districts[].megasites[] (kind, area_km2, position)` |
| a traced district in the wrong spot or turned | `water.islands[].position, pinned.rotation_deg` |

Stop when the checks pass and the previews match the prompt (and the concept image), or after the last round; say what is still off.
