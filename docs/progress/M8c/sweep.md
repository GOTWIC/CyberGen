# citygen sweep

58 of 68 builds pass (85%)

| spec | pass | builds |
|---|---|---|
| archipelago_free_port | 7 | 8 |
| delta_megacity | 8 | 8 |
| nexus_city | 7 | 8 |
| nyxllor | 7 | 8 |
| nyxllor_pinned | 4 | 8 |
| peninsula_city | 8 | 8 |
| test_delta | 5 | 5 |
| test_minimal | 2 | 5 |
| test_pinned | 5 | 5 |
| test_small | 5 | 5 |

| failing check | builds |
|---|---|
| placement | 5 |
| road_graph | 3 |
| open_space_share | 3 |
| curve_radius | 3 |
| districts_served | 1 |
| bridge_clearance | 1 |
| level_continuity | 1 |
| walkway_graph | 1 |
| lot_block_sizes | 1 |
| megasite_access | 1 |

| spec | seed | result | failing checks (first failure) | retries | s |
|---|---|---|---|---|---|
| archipelago_free_port | 11 | pass |  | hv0 rv0 | 20.4 |
| archipelago_free_port | 404 | pass |  | hv0 rv0 city x1 (2) | 55.2 |
| archipelago_free_port | 1999 | fail | road_graph (1): landmass lm05 (Palm Key) is not reached by the road network<br>districts_served (1): 'Palm Key' is not served by an avenue<br>open_space_share (1): 'Palm Key' (residential_heights): 100% open (target 8% to 40%) | hv0 rv0 city x8 (3,3,7,5,3,3,3,3) | 286.7 |
| archipelago_free_port | 3141 | pass |  | hv0 rv0 | 29.8 |
| archipelago_free_port | 3301 | pass |  | hv0 rv0 | 20.5 |
| archipelago_free_port | 5077 | pass |  | hv0 rv0 | 32.0 |
| archipelago_free_port | 8128 | pass |  | hv0 rv0 | 50.3 |
| archipelago_free_port | 27182 | pass |  | hv0 rv0 | 36.2 |
| delta_megacity | 11 | pass |  | hv13 rv0 | 55.1 |
| delta_megacity | 404 | pass |  | hv0 rv1 | 46.9 |
| delta_megacity | 1999 | pass |  | hv9 rv1 | 43.5 |
| delta_megacity | 3141 | pass |  | hv0 rv0 city x1 (9) | 75.2 |
| delta_megacity | 4412 | pass |  | hv12 rv3 | 59.9 |
| delta_megacity | 5077 | pass |  | hv0 rv0 city x2 (4,2) | 114.9 |
| delta_megacity | 8128 | pass |  | hv3 rv1 | 51.2 |
| delta_megacity | 27182 | pass |  | hv12 rv1 | 44.9 |
| nexus_city | 11 | fail | placement (1): 'Neon Market' is not west_of 'Transit Nexus' (bearing 20 deg)<br>curve_radius (1): segment rs00011 (highway): radius 133 m near (-337, -266), minimum 150 m | hv5 rv2 city x8 (2,2,2,2,3,2,2,4) | 446.7 |
| nexus_city | 404 | pass |  | hv13 rv0 | 50.9 |
| nexus_city | 1207 | pass |  | hv11 rv0 city x2 (4,2) | 151.9 |
| nexus_city | 1999 | pass |  | hv1 rv1 | 45.5 |
| nexus_city | 3141 | pass |  | hv12 rv0 | 57.9 |
| nexus_city | 5077 | pass |  | hv6 rv0 | 56.9 |
| nexus_city | 8128 | pass |  | hv6 rv0 city x1 (1) | 108.2 |
| nexus_city | 27182 | pass |  | hv1 rv0 city x1 (1) | 110.0 |
| nyxllor | 11 | pass |  | hv10 rv0 | 54.8 |
| nyxllor | 404 | pass |  | hv1 rv1 city x1 (2) | 96.6 |
| nyxllor | 1999 | pass |  | hv1 rv1 | 51.8 |
| nyxllor | 2077 | pass |  | hv18 rv0 | 56.4 |
| nyxllor | 3141 | fail | open_space_share (1): 'Launch Key' (spaceport): 67% open (target 0% to 50%) | hv7 rv1 city x8 (1,1,1,1,5,3,2,3) | 424.6 |
| nyxllor | 5077 | pass |  | hv1 rv1 | 54.2 |
| nyxllor | 8128 | pass |  | hv19 rv0 | 57.4 |
| nyxllor | 27182 | pass |  | hv1 rv0 | 56.4 |
| nyxllor_pinned | 11 | fail | bridge_clearance (1): junction rn00274 is out on the water (on a bridge)<br>curve_radius (1): segment rs00030 (highway): radius 111 m near (-351, -1168), minimum 150 m | hv5 rv0 city x8 (2,3,6,6,2,2,3,3) | 623.0 |
| nyxllor_pinned | 404 | pass |  | hv1 rv0 city x6 (1,2,1,2,1,1) | 330.1 |
| nyxllor_pinned | 1999 | fail | curve_radius (1): segment rs00021 (highway): radius 51 m near (-1174, 132), minimum 150 m | hv10 rv0 city x8 (1,1,2,1,1,1,3,4) | 654.9 |
| nyxllor_pinned | 2078 | pass |  | hv4 rv0 city x1 (1) | 93.3 |
| nyxllor_pinned | 3141 | pass |  | hv4 rv0 city x2 (1,2) | 239.1 |
| nyxllor_pinned | 5077 | fail | placement (1): 'Neon Strand' should be on the coast<br>level_continuity (1): rs02321 meets node rn00160 at 11.88 m, the node is at 7.69 m | hv17 rv0 city x8 (3,3,3,2,2,3,2,4) | 647.9 |
| nyxllor_pinned | 8128 | fail | placement (1): 'Highcrest' is not east_of 'The Stacks' (bearing 21 deg) | hv3 rv0 city x8 (1,1,2,3,2,3,1,1) | 494.4 |
| nyxllor_pinned | 27182 | pass |  | hv19 rv1 city x1 (1) | 105.7 |
| peninsula_city | 11 | pass |  | hv13 rv0 city x2 (1,1) | 94.1 |
| peninsula_city | 404 | pass |  | hv2 rv0 | 23.5 |
| peninsula_city | 1999 | pass |  | hv11 rv0 | 33.6 |
| peninsula_city | 3141 | pass |  | hv10 rv0 | 30.6 |
| peninsula_city | 5077 | pass |  | hv13 rv0 | 43.0 |
| peninsula_city | 8128 | pass |  | hv2 rv0 | 26.5 |
| peninsula_city | 9081 | pass |  | hv0 rv0 | 17.2 |
| peninsula_city | 27182 | pass |  | hv2 rv0 city x3 (1,1,2) | 76.1 |
| test_delta | 11 | pass |  | hv0 rv1 | 33.9 |
| test_delta | 12 | pass |  | hv18 rv3 | 50.3 |
| test_delta | 404 | pass |  | hv14 rv2 city x1 (4) | 74.7 |
| test_delta | 1999 | pass |  | hv3 rv2 | 34.4 |
| test_delta | 3141 | pass |  | hv3 rv3 city x1 (5) | 71.6 |
| test_minimal | 11 | pass |  | hv18 rv0 | 24.4 |
| test_minimal | 42 | fail | placement (1): 'Core' is not at edge 'center' | hv11 rv0 city x8 (1,1,1,1,1,1,1,1) | 134.2 |
| test_minimal | 404 | fail | road_graph (1): exit 'west' was not built<br>walkway_graph (1): landmass lm04: 2 walkway components (walk nodes 116, 1) | hv5 rv3 city x8 (2,2,2,2,2,2,2,2) | 107.9 |
| test_minimal | 1999 | pass |  | hv6 rv0 | 17.3 |
| test_minimal | 3141 | fail | placement (1): 'Core' is not at edge 'center'<br>road_graph (1): exit 'west' was not built<br>lot_block_sizes (1): district d04: median block size 77 m (range 200 to 400)<br>open_space_share (1): 'Launch' (spaceport): 66% open (target 0% to 50%)<br>megasite_access (1): d04.ms01 'Launch Spaceport': no road within 40 m | hv5 rv0 city x8 (5,5,5,5,5,5,5,5) | 102.5 |
| test_pinned | 11 | pass |  | hv0 rv0 city x1 (1) | 53.9 |
| test_pinned | 17 | pass |  | hv0 rv0 | 27.0 |
| test_pinned | 404 | pass |  | hv0 rv0 city x1 (2) | 53.6 |
| test_pinned | 1999 | pass |  | hv0 rv0 | 26.7 |
| test_pinned | 3141 | pass |  | hv0 rv0 city x1 (2) | 52.3 |
| test_small | 7 | pass |  | hv1 rv0 | 17.4 |
| test_small | 11 | pass |  | hv1 rv1 | 17.8 |
| test_small | 404 | pass |  | hv1 rv1 | 16.7 |
| test_small | 1999 | pass |  | hv1 rv1 | 15.8 |
| test_small | 3141 | pass |  | hv16 rv0 city x1 (1) | 30.5 |
