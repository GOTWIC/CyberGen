# citygen sweep after M8a

49 of 68 builds pass (72%)

The 47 builds that passed with the fixes before the last one (further hydrology variants when no road network passes) come from that run; the 21 that failed were built again with the final code. The last fix changes only builds whose road stage fails on every first variant, and none of the 47 does (each was checked with a roads-only build of the final code).

| spec | pass | builds |
|---|---|---|
| archipelago_free_port | 6 | 8 |
| delta_megacity | 3 | 8 |
| nexus_city | 6 | 8 |
| nyxllor | 7 | 8 |
| nyxllor_pinned | 4 | 8 |
| peninsula_city | 6 | 8 |
| test_delta | 5 | 5 |
| test_minimal | 2 | 5 |
| test_pinned | 5 | 5 |
| test_small | 5 | 5 |

| failing check | builds |
|---|---|
| transit_curves | 9 |
| placement | 5 |
| road_graph | 3 |
| open_space_share | 3 |
| curve_radius | 3 |
| transit_stops | 2 |
| level_continuity | 2 |
| districts_served | 1 |
| bridge_clearance | 1 |
| transit_altitude | 1 |
| walkway_graph | 1 |
| lot_block_sizes | 1 |
| megasite_access | 1 |

| spec | seed | result | failing checks (first failure) | retries | s |
|---|---|---|---|---|---|
| archipelago_free_port | 11 | pass |  | hv0 rv0 city x2 (1,1) | 65.1 |
| archipelago_free_port | 404 | pass |  | hv0 rv0 city x1 (2) | 45.0 |
| archipelago_free_port | 1999 | fail | road_graph (1): landmass lm05 (Palm Key) is not reached by the road network<br>districts_served (1): 'Palm Key' is not served by an avenue<br>open_space_share (1): 'Palm Key' (residential_heights): 100% open (target 8% to 40%)<br>transit_curves (1): Island Hopper (monorail): radius 66 m (minimum 100) | hv0 rv0 city x8 (4,4,9,6,4,4,4,4) | 348.7 |
| archipelago_free_port | 3141 | pass |  | hv0 rv0 city x1 (2) | 62.2 |
| archipelago_free_port | 3301 | pass |  | hv0 rv0 | 18.1 |
| archipelago_free_port | 5077 | pass |  | hv0 rv0 | 20.2 |
| archipelago_free_port | 8128 | pass |  | hv0 rv0 city x3 (1,3,1) | 79.9 |
| archipelago_free_port | 27182 | fail | transit_curves (1): Island Hopper (monorail): radius 12 m (minimum 100) | hv0 rv0 city x8 (1,1,1,1,1,1,1,1) | 245.8 |
| delta_megacity | 11 | fail | transit_curves (1): Delta Loop (sky_tube): radius 187 m (minimum 300) | hv13 rv0 city x8 (1,3,1,1,1,6,2,2) | 381.0 |
| delta_megacity | 404 | pass |  | hv0 rv1 | 48.3 |
| delta_megacity | 1999 | pass |  | hv9 rv1 | 37.1 |
| delta_megacity | 3141 | fail | transit_stops (1): Delta Loop: no station serves 'Old Town' (nearest 347 m away)<br>transit_curves (1): Delta Loop (sky_tube): radius 108 m (minimum 300) | hv0 rv0 city x8 (11,7,2,3,7,5,6,7) | 442.3 |
| delta_megacity | 4412 | pass |  | hv0 rv3 city x8 (8,2,4,3,3,2,4,2) | 562.4 |
| delta_megacity | 5077 | fail | transit_curves (1): Delta Loop (sky_tube): radius 15 m (minimum 300) | hv0 rv0 city x8 (7,9,1,8,7,7,2,1) | 616.8 |
| delta_megacity | 8128 | fail | transit_stops (1): Delta Loop: no station serves 'Research Campus' (nearest 210 m away)<br>transit_curves (1): Delta Loop (sky_tube): radius 148 m (minimum 300) | hv3 rv2 city x8 (6,3,4,5,3,2,3,6) | 409.3 |
| delta_megacity | 27182 | fail | transit_curves (1): Delta Loop (sky_tube): radius 50 m (minimum 300) | hv12 rv1 city x8 (2,2,1,10,3,1,2,5) | 424.8 |
| nexus_city | 11 | fail | placement (1): 'Neon Market' is not west_of 'Transit Nexus' (bearing 20 deg)<br>curve_radius (1): segment rs00011 (highway): radius 133 m near (-337, -266), minimum 150 m | hv5 rv2 city x8 (2,2,3,2,3,2,3,4) | 405.6 |
| nexus_city | 404 | pass |  | hv13 rv0 city x1 (1) | 83.7 |
| nexus_city | 1207 | pass |  | hv11 rv0 city x2 (6,3) | 123.2 |
| nexus_city | 1999 | pass |  | hv1 rv1 | 44.9 |
| nexus_city | 3141 | pass |  | hv12 rv1 city x4 (2,3,3,4) | 190.9 |
| nexus_city | 5077 | fail | level_continuity (2): rs01448 meets node rn01616 at 8.22 m, the node is at 0 m | hv6 rv1 city x8 (3,4,3,5,6,4,2,3) | 329.3 |
| nexus_city | 8128 | pass |  | hv6 rv0 city x1 (3) | 89.0 |
| nexus_city | 27182 | pass |  | hv1 rv0 city x1 (2) | 84.4 |
| nyxllor | 11 | pass |  | hv10 rv0 | 42.7 |
| nyxllor | 404 | pass |  | hv1 rv3 city x4 (3,1,1,1) | 218.6 |
| nyxllor | 1999 | pass |  | hv1 rv1 city x1 (2) | 98.0 |
| nyxllor | 2077 | pass |  | hv18 rv1 city x7 (2,2,5,2,1,2,1) | 429.3 |
| nyxllor | 3141 | fail | open_space_share (1): 'Launch Key' (spaceport): 74% open (target 0% to 50%) | hv7 rv1 city x8 (4,1,1,4,5,3,1,4) | 428.5 |
| nyxllor | 5077 | pass |  | hv1 rv1 city x2 (1,6) | 114.0 |
| nyxllor | 8128 | pass |  | hv19 rv1 city x4 (1,2,1,2) | 249.3 |
| nyxllor | 27182 | pass |  | hv1 rv0 | 68.4 |
| nyxllor_pinned | 11 | fail | bridge_clearance (1): junction rn00274 is out on the water (on a bridge)<br>curve_radius (1): segment rs00030 (highway): radius 111 m near (-351, -1168), minimum 150 m | hv5 rv0 city x8 (2,3,8,6,4,2,4,3) | 396.5 |
| nyxllor_pinned | 404 | pass |  | hv4 rv1 | 42.5 |
| nyxllor_pinned | 1999 | fail | curve_radius (1): segment rs00021 (highway): radius 51 m near (-1174, 132), minimum 150 m | hv10 rv0 city x8 (5,1,3,2,1,2,3,5) | 427.8 |
| nyxllor_pinned | 2078 | pass |  | hv4 rv0 city x1 (2) | 86.2 |
| nyxllor_pinned | 3141 | pass |  | hv4 rv0 city x2 (1,3) | 122.8 |
| nyxllor_pinned | 5077 | fail | placement (1): 'Neon Strand' should be on the coast<br>level_continuity (1): rs02261 meets node rn00157 at 11.87 m, the node is at 7.69 m | hv17 rv0 city x8 (3,3,4,4,2,7,3,5) | 417.1 |
| nyxllor_pinned | 8128 | fail | placement (1): 'Highcrest' is not east_of 'The Stacks' (bearing 21 deg) | hv3 rv0 city x8 (1,1,2,2,2,3,1,1) | 354.6 |
| nyxllor_pinned | 27182 | pass |  | hv19 rv2 city x5 (2,1,2,2,2) | 406.5 |
| peninsula_city | 11 | pass |  | hv13 rv0 city x2 (3,2) | 69.1 |
| peninsula_city | 404 | pass |  | hv2 rv0 city x3 (2,2,2) | 123.3 |
| peninsula_city | 1999 | pass |  | hv11 rv0 city x1 (2) | 59.9 |
| peninsula_city | 3141 | pass |  | hv10 rv0 | 24.4 |
| peninsula_city | 5077 | pass |  | hv13 rv0 | 35.5 |
| peninsula_city | 8128 | fail | transit_curves (1): East Shore Line (elevated_rail): radius 107 m (minimum 150) | hv2 rv0 city x8 (1,2,2,2,1,2,2,2) | 181.3 |
| peninsula_city | 9081 | pass |  | hv0 rv0 | 15.7 |
| peninsula_city | 27182 | fail | transit_curves (1): East Shore Line (elevated_rail): radius 41 m (minimum 150)<br>transit_altitude (1): East Shore Line (elevated_rail): z 20.15 m at (377.77, -1004.8) outside 8 to 20.0 m | hv2 rv0 city x8 (4,3,2,2,4,3,2,2) | 220.0 |
| test_delta | 11 | pass |  | hv0 rv1 | 34.2 |
| test_delta | 12 | pass |  | hv18 rv3 | 50.6 |
| test_delta | 404 | pass |  | hv14 rv2 city x1 (4) | 75.6 |
| test_delta | 1999 | pass |  | hv3 rv2 | 35.4 |
| test_delta | 3141 | pass |  | hv3 rv3 city x1 (5) | 71.6 |
| test_minimal | 11 | pass |  | hv18 rv0 | 22.7 |
| test_minimal | 42 | fail | placement (1): 'Core' is not at edge 'center' | hv11 rv0 city x8 (2,2,1,1,1,1,1,1) | 125.9 |
| test_minimal | 404 | fail | road_graph (1): exit 'west' was not built<br>walkway_graph (1): landmass lm04: 2 walkway components (walk nodes 118, 1) | hv5 rv3 city x8 (2,2,2,2,2,2,2,2) | 99.0 |
| test_minimal | 1999 | pass |  | hv6 rv0 | 16.6 |
| test_minimal | 3141 | fail | placement (1): 'Core' is not at edge 'center'<br>road_graph (1): exit 'west' was not built<br>lot_block_sizes (1): district d04: median block size 77 m (range 200 to 400)<br>open_space_share (1): 'Launch' (spaceport): 66% open (target 0% to 50%)<br>megasite_access (1): d04.ms01 'Launch Spaceport': no road within 40 m | hv5 rv0 city x8 (5,5,5,6,5,6,6,6) | 92.0 |
| test_pinned | 11 | pass |  | hv0 rv0 city x1 (1) | 56.6 |
| test_pinned | 17 | pass |  | hv0 rv0 | 26.8 |
| test_pinned | 404 | pass |  | hv0 rv0 city x1 (2) | 56.0 |
| test_pinned | 1999 | pass |  | hv0 rv0 | 28.9 |
| test_pinned | 3141 | pass |  | hv0 rv0 city x1 (2) | 52.6 |
| test_small | 7 | pass |  | hv1 rv0 | 16.3 |
| test_small | 11 | pass |  | hv1 rv1 | 16.2 |
| test_small | 404 | pass |  | hv1 rv1 | 16.5 |
| test_small | 1999 | pass |  | hv1 rv1 | 18.0 |
| test_small | 3141 | pass |  | hv16 rv0 city x1 (1) | 31.4 |
