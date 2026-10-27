# citygen sweep

58 of 68 builds pass (85%)

| spec | pass | builds |
|---|---|---|
| archipelago_free_port | 7 | 8 |
| delta_megacity | 8 | 8 |
| nexus_city | 7 | 8 |
| peninsula_city | 8 | 8 |
| test_delta | 5 | 5 |
| test_minimal | 2 | 5 |
| test_pinned | 5 | 5 |
| test_small | 5 | 5 |
| vesper_bay | 7 | 8 |
| vesper_bay_pinned | 4 | 8 |

| failing check | builds |
|---|---|
| placement | 5 |
| road_graph | 3 |
| open_space_share | 3 |
| curve_radius | 3 |
| districts_served | 1 |
| walkway_graph | 1 |
| lot_block_sizes | 1 |
| megasite_access | 1 |
| bridge_clearance | 1 |
| level_continuity | 1 |

| spec | seed | result | failing checks (first failure) | retries | s |
|---|---|---|---|---|---|
| archipelago_free_port | 11 | pass |  | hv0 rv0 | 21.3 |
| archipelago_free_port | 404 | pass |  | hv0 rv0 city x1 (2) | 55.0 |
| archipelago_free_port | 1999 | fail | road_graph (1): landmass lm05 (Palm Key) is not reached by the road network<br>districts_served (1): 'Palm Key' is not served by an avenue<br>open_space_share (1): 'Palm Key' (residential_heights): 100% open (target 8% to 40%) | hv0 rv0 city x8 (3,3,7,5,3,3,3,3) | 274.7 |
| archipelago_free_port | 3141 | pass |  | hv0 rv0 | 29.0 |
| archipelago_free_port | 3301 | pass |  | hv0 rv0 | 21.1 |
| archipelago_free_port | 5077 | pass |  | hv0 rv0 | 30.8 |
| archipelago_free_port | 8128 | pass |  | hv0 rv0 | 48.5 |
| archipelago_free_port | 27182 | pass |  | hv0 rv0 | 34.4 |
| delta_megacity | 11 | pass |  | hv13 rv0 | 52.9 |
| delta_megacity | 404 | pass |  | hv0 rv1 | 44.2 |
| delta_megacity | 1999 | pass |  | hv9 rv1 | 40.3 |
| delta_megacity | 3141 | pass |  | hv0 rv0 city x1 (9) | 71.5 |
| delta_megacity | 4412 | pass |  | hv12 rv3 | 58.6 |
| delta_megacity | 5077 | pass |  | hv0 rv0 city x2 (4,2) | 109.5 |
| delta_megacity | 8128 | pass |  | hv3 rv1 | 48.3 |
| delta_megacity | 27182 | pass |  | hv12 rv1 | 43.3 |
| nexus_city | 11 | fail | placement (1): 'Neon Market' is not west_of 'Transit Nexus' (bearing 20 deg)<br>curve_radius (1): segment rs00011 (highway): radius 133 m near (-337, -266), minimum 150 m | hv5 rv2 city x8 (2,2,2,2,3,2,2,4) | 408.2 |
| nexus_city | 404 | pass |  | hv13 rv0 | 50.1 |
| nexus_city | 1207 | pass |  | hv11 rv0 city x2 (4,2) | 149.1 |
| nexus_city | 1999 | pass |  | hv1 rv1 | 45.0 |
| nexus_city | 3141 | pass |  | hv12 rv0 | 56.7 |
| nexus_city | 5077 | pass |  | hv6 rv0 | 55.1 |
| nexus_city | 8128 | pass |  | hv6 rv0 city x1 (1) | 97.0 |
| nexus_city | 27182 | pass |  | hv1 rv0 city x1 (1) | 96.3 |
| peninsula_city | 11 | pass |  | hv13 rv0 city x2 (1,1) | 77.1 |
| peninsula_city | 404 | pass |  | hv2 rv0 | 20.3 |
| peninsula_city | 1999 | pass |  | hv11 rv0 | 29.8 |
| peninsula_city | 3141 | pass |  | hv10 rv0 | 27.3 |
| peninsula_city | 5077 | pass |  | hv13 rv0 | 37.6 |
| peninsula_city | 8128 | pass |  | hv2 rv0 | 23.7 |
| peninsula_city | 9081 | pass |  | hv0 rv0 | 17.9 |
| peninsula_city | 27182 | pass |  | hv2 rv0 city x3 (1,1,2) | 67.6 |
| test_delta | 11 | pass |  | hv0 rv1 | 36.8 |
| test_delta | 12 | pass |  | hv18 rv3 | 53.6 |
| test_delta | 404 | pass |  | hv14 rv2 city x1 (4) | 82.9 |
| test_delta | 1999 | pass |  | hv3 rv2 | 38.3 |
| test_delta | 3141 | pass |  | hv3 rv3 city x1 (5) | 79.1 |
| test_minimal | 11 | pass |  | hv18 rv0 | 26.0 |
| test_minimal | 42 | fail | placement (1): 'Core' is not at edge 'center' | hv11 rv0 city x8 (1,1,1,1,1,1,1,1) | 146.4 |
| test_minimal | 404 | fail | road_graph (1): exit 'west' was not built<br>walkway_graph (1): landmass lm04: 2 walkway components (walk nodes 116, 1) | hv5 rv3 city x8 (2,2,2,2,2,2,2,2) | 115.9 |
| test_minimal | 1999 | pass |  | hv6 rv0 | 18.8 |
| test_minimal | 3141 | fail | placement (1): 'Core' is not at edge 'center'<br>road_graph (1): exit 'west' was not built<br>lot_block_sizes (1): district d04: median block size 77 m (range 200 to 400)<br>open_space_share (1): 'Launch' (spaceport): 66% open (target 0% to 50%)<br>megasite_access (1): d04.ms01 'Launch Spaceport': no road within 40 m | hv5 rv0 city x8 (5,5,5,5,5,5,5,5) | 109.0 |
| test_pinned | 11 | pass |  | hv0 rv0 city x1 (1) | 58.3 |
| test_pinned | 17 | pass |  | hv0 rv0 | 29.2 |
| test_pinned | 404 | pass |  | hv0 rv0 city x1 (2) | 59.0 |
| test_pinned | 1999 | pass |  | hv0 rv0 | 28.5 |
| test_pinned | 3141 | pass |  | hv0 rv0 city x1 (2) | 57.7 |
| test_small | 7 | pass |  | hv1 rv0 | 16.8 |
| test_small | 11 | pass |  | hv1 rv1 | 16.6 |
| test_small | 404 | pass |  | hv1 rv1 | 18.1 |
| test_small | 1999 | pass |  | hv1 rv1 | 21.8 |
| test_small | 3141 | pass |  | hv16 rv0 city x1 (1) | 44.0 |
| vesper_bay | 11 | pass |  | hv10 rv0 | 47.6 |
| vesper_bay | 404 | pass |  | hv1 rv1 city x1 (2) | 89.2 |
| vesper_bay | 1999 | pass |  | hv1 rv1 | 48.2 |
| vesper_bay | 2077 | pass |  | hv18 rv0 | 48.6 |
| vesper_bay | 3141 | fail | open_space_share (1): 'Launch Key' (spaceport): 71% open (target 0% to 50%) | hv7 rv2 city x8 (3,2,2,2,5,2,1,3) | 387.1 |
| vesper_bay | 5077 | pass |  | hv1 rv1 | 49.1 |
| vesper_bay | 8128 | pass |  | hv19 rv0 | 52.4 |
| vesper_bay | 27182 | pass |  | hv1 rv0 | 52.0 |
| vesper_bay_pinned | 11 | fail | bridge_clearance (1): junction rn00274 is out on the water (on a bridge)<br>curve_radius (1): segment rs00030 (highway): radius 111 m near (-351, -1168), minimum 150 m | hv5 rv0 city x8 (2,3,6,6,2,2,3,3) | 423.1 |
| vesper_bay_pinned | 404 | pass |  | hv1 rv0 city x6 (1,2,1,2,1,1) | 307.5 |
| vesper_bay_pinned | 1999 | fail | curve_radius (1): segment rs00021 (highway): radius 51 m near (-1174, 132), minimum 150 m | hv10 rv0 city x8 (1,1,2,1,1,1,3,4) | 454.7 |
| vesper_bay_pinned | 2078 | pass |  | hv4 rv0 city x1 (1) | 86.3 |
| vesper_bay_pinned | 3141 | pass |  | hv4 rv0 city x2 (1,2) | 131.4 |
| vesper_bay_pinned | 5077 | fail | placement (1): 'Neon Strand' should be on the coast<br>level_continuity (1): rs02321 meets node rn00160 at 11.88 m, the node is at 7.69 m | hv17 rv0 city x8 (3,3,3,2,2,3,2,4) | 488.0 |
| vesper_bay_pinned | 8128 | fail | placement (1): 'Highcrest' is not east_of 'The Stacks' (bearing 21 deg) | hv3 rv0 city x8 (1,1,2,3,2,3,1,1) | 460.6 |
| vesper_bay_pinned | 27182 | pass |  | hv19 rv1 city x1 (1) | 125.8 |
