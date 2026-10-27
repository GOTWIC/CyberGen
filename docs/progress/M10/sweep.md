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
| archipelago_free_port | 11 | pass |  | hv0 rv0 | 24.6 |
| archipelago_free_port | 404 | pass |  | hv0 rv0 city x1 (2) salt 1 | 59.4 |
| archipelago_free_port | 1999 | fail | road_graph (1): landmass lm.e866n638 (Palm Key) is not reached by the road network<br>districts_served (1): 'Palm Key' is not served by an avenue<br>open_space_share (1): 'Palm Key' (residential_heights): 100% open (target 8% to 40%) | hv0 rv0 city x8 (3,3,7,5,3,3,3,3) | 292.3 |
| archipelago_free_port | 3141 | pass |  | hv0 rv0 | 32.6 |
| archipelago_free_port | 3301 | pass |  | hv0 rv0 | 24.4 |
| archipelago_free_port | 5077 | pass |  | hv0 rv0 | 34.1 |
| archipelago_free_port | 8128 | pass |  | hv0 rv0 | 51.3 |
| archipelago_free_port | 27182 | pass |  | hv0 rv0 | 38.7 |
| delta_megacity | 11 | pass |  | hv13 rv0 | 58.7 |
| delta_megacity | 404 | pass |  | hv0 rv1 | 51.3 |
| delta_megacity | 1999 | pass |  | hv9 rv1 | 46.8 |
| delta_megacity | 3141 | pass |  | hv0 rv0 city x2 (11,1) salt 2 | 122.8 |
| delta_megacity | 4412 | pass |  | hv12 rv3 | 64.8 |
| delta_megacity | 5077 | pass |  | hv0 rv0 city x2 (4,2) salt 2 | 124.5 |
| delta_megacity | 8128 | pass |  | hv3 rv1 | 55.8 |
| delta_megacity | 27182 | pass |  | hv12 rv1 | 49.3 |
| nexus_city | 11 | fail | placement (1): 'Neon Market' is not west_of 'Transit Nexus' (bearing 20 deg)<br>curve_radius (1): segment rs.w383s267 (highway): radius 133 m near (-337, -266), minimum 150 m | hv5 rv2 city x8 (2,2,2,2,3,2,2,4) | 454.2 |
| nexus_city | 404 | pass |  | hv13 rv0 | 59.3 |
| nexus_city | 1207 | pass |  | hv11 rv0 city x2 (4,2) salt 2 | 166.3 |
| nexus_city | 1999 | pass |  | hv1 rv1 | 53.1 |
| nexus_city | 3141 | pass |  | hv12 rv0 | 64.0 |
| nexus_city | 5077 | pass |  | hv6 rv0 | 63.5 |
| nexus_city | 8128 | pass |  | hv6 rv0 city x1 (1) salt 1 | 110.2 |
| nexus_city | 27182 | pass |  | hv1 rv0 city x1 (1) salt 1 | 108.1 |
| peninsula_city | 11 | pass |  | hv13 rv0 city x2 (1,1) salt 2 | 85.3 |
| peninsula_city | 404 | pass |  | hv2 rv0 | 23.7 |
| peninsula_city | 1999 | pass |  | hv11 rv0 | 33.9 |
| peninsula_city | 3141 | pass |  | hv10 rv0 | 30.9 |
| peninsula_city | 5077 | pass |  | hv13 rv0 | 40.8 |
| peninsula_city | 8128 | pass |  | hv2 rv0 | 26.8 |
| peninsula_city | 9081 | pass |  | hv0 rv0 | 21.3 |
| peninsula_city | 27182 | pass |  | hv2 rv0 city x3 (1,1,2) salt 3 | 76.4 |
| test_delta | 11 | pass |  | hv0 rv1 | 43.7 |
| test_delta | 12 | pass |  | hv18 rv3 | 62.1 |
| test_delta | 404 | pass |  | hv14 rv2 city x1 (4) salt 1 | 90.3 |
| test_delta | 1999 | pass |  | hv3 rv2 | 43.4 |
| test_delta | 3141 | pass |  | hv3 rv3 city x1 (5) salt 1 | 87.0 |
| test_minimal | 11 | pass |  | hv18 rv0 | 27.2 |
| test_minimal | 42 | fail | placement (1): 'Core' is not at edge 'center' | hv11 rv0 city x8 (1,1,1,1,1,1,1,1) | 153.8 |
| test_minimal | 404 | fail | road_graph (1): exit 'west' was not built<br>walkway_graph (1): landmass lm.e1068s65: 2 walkway components (walk nodes 116, 1) | hv5 rv3 city x8 (2,2,2,2,2,2,2,2) | 121.1 |
| test_minimal | 1999 | pass |  | hv6 rv0 | 20.4 |
| test_minimal | 3141 | fail | placement (1): 'Core' is not at edge 'center'<br>road_graph (1): exit 'west' was not built<br>lot_block_sizes (1): district d04: median block size 77 m (range 200 to 400)<br>open_space_share (1): 'Launch' (spaceport): 66% open (target 0% to 50%)<br>megasite_access (1): d04.ms.launch_spaceport 'Launch Spaceport': no road within 40 m | hv5 rv0 city x8 (5,5,5,5,5,5,5,5) | 113.1 |
| test_pinned | 11 | pass |  | hv0 rv0 city x1 (1) salt 1 | 65.3 |
| test_pinned | 17 | pass |  | hv0 rv0 | 33.5 |
| test_pinned | 404 | pass |  | hv0 rv0 city x1 (2) salt 1 | 66.1 |
| test_pinned | 1999 | pass |  | hv0 rv0 | 34.3 |
| test_pinned | 3141 | pass |  | hv0 rv0 city x1 (2) salt 1 | 65.1 |
| test_small | 7 | pass |  | hv1 rv0 | 19.2 |
| test_small | 11 | pass |  | hv1 rv1 | 19.4 |
| test_small | 404 | pass |  | hv1 rv1 | 21.5 |
| test_small | 1999 | pass |  | hv1 rv1 | 20.5 |
| test_small | 3141 | pass |  | hv16 rv0 city x1 (1) salt 1 | 39.6 |
| vesper_bay | 11 | pass |  | hv10 rv0 | 57.4 |
| vesper_bay | 404 | pass |  | hv1 rv1 city x1 (2) salt 1 | 102.3 |
| vesper_bay | 1999 | pass |  | hv1 rv1 | 56.5 |
| vesper_bay | 2077 | pass |  | hv18 rv0 | 56.7 |
| vesper_bay | 3141 | fail | open_space_share (1): 'Launch Key' (spaceport): 71% open (target 0% to 50%) | hv7 rv2 city x8 (3,2,2,2,5,2,1,3) salt 2 | 431.7 |
| vesper_bay | 5077 | pass |  | hv1 rv1 | 57.0 |
| vesper_bay | 8128 | pass |  | hv19 rv0 | 62.1 |
| vesper_bay | 27182 | pass |  | hv1 rv0 | 61.5 |
| vesper_bay_pinned | 11 | fail | bridge_clearance (1): junction rn.w262s827 is out on the water (on a bridge)<br>curve_radius (1): segment rs.w345s1098 (highway): radius 111 m near (-351, -1168), minimum 150 m | hv5 rv0 city x8 (2,3,6,6,2,2,3,3) | 470.9 |
| vesper_bay_pinned | 404 | pass |  | hv1 rv0 city x6 (1,2,1,2,1,1) salt 2 | 345.4 |
| vesper_bay_pinned | 1999 | fail | curve_radius (1): segment rs.w1205n265 (highway): radius 51 m near (-1174, 132), minimum 150 m | hv10 rv0 city x8 (1,1,2,1,1,1,3,4) | 499.5 |
| vesper_bay_pinned | 2078 | pass |  | hv4 rv0 city x1 (1) salt 1 | 101.5 |
| vesper_bay_pinned | 3141 | pass |  | hv4 rv0 city x2 (1,2) salt 2 | 149.7 |
| vesper_bay_pinned | 5077 | fail | placement (1): 'Neon Strand' should be on the coast<br>level_continuity (1): rs.w78s851 meets node rn.w37s896 at 11.88 m, the node is at 7.69 m | hv17 rv0 city x8 (3,3,3,2,2,3,2,4) salt 3 | 491.9 |
| vesper_bay_pinned | 8128 | fail | placement (1): 'Highcrest' is not east_of 'The Stacks' (bearing 21 deg) | hv3 rv0 city x8 (1,1,2,3,2,3,1,1) | 459.0 |
| vesper_bay_pinned | 27182 | pass |  | hv19 rv1 city x1 (1) salt 1 | 116.1 |
