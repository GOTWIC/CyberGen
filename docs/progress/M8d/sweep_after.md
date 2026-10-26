# citygen sweep

51 of 68 builds pass (75%)

| spec | pass | builds |
|---|---|---|
| archipelago_free_port | 5 | 8 |
| delta_megacity | 4 | 8 |
| nexus_city | 7 | 8 |
| nyxllor | 7 | 8 |
| nyxllor_pinned | 4 | 8 |
| peninsula_city | 7 | 8 |
| test_delta | 5 | 5 |
| test_minimal | 2 | 5 |
| test_pinned | 5 | 5 |
| test_small | 5 | 5 |

| failing check | builds |
|---|---|
| transit_curves | 6 |
| placement | 5 |
| road_graph | 3 |
| open_space_share | 3 |
| curve_radius | 3 |
| districts_served | 1 |
| bridge_clearance | 1 |
| level_continuity | 1 |
| building_overlaps | 1 |
| walkway_graph | 1 |
| lot_block_sizes | 1 |
| megasite_access | 1 |

| spec | seed | result | failing checks (first failure) | retries | s |
|---|---|---|---|---|---|
| archipelago_free_port | 11 | pass |  | hv0 rv0 | 102.5 |
| archipelago_free_port | 404 | pass |  | hv0 rv0 city x1 (2) | 224.1 |
| archipelago_free_port | 1999 | fail | road_graph (1): landmass lm05 (Palm Key) is not reached by the road network<br>districts_served (1): 'Palm Key' is not served by an avenue<br>open_space_share (1): 'Palm Key' (residential_heights): 100% open (target 8% to 40%) | hv0 rv0 city x8 (3,3,7,5,3,3,3,3) | 1051.4 |
| archipelago_free_port | 3141 | fail | transit_curves (1): Island Hopper (monorail): radius 26 m (minimum 100) | hv0 rv0 city x8 (1,2,3,1,1,2,3,1) | 908.0 |
| archipelago_free_port | 3301 | pass |  | hv0 rv0 | 99.6 |
| archipelago_free_port | 5077 | pass |  | hv0 rv0 | 111.5 |
| archipelago_free_port | 8128 | pass |  | hv0 rv0 city x2 (1,2) | 269.1 |
| archipelago_free_port | 27182 | fail | transit_curves (1): Island Hopper (monorail): radius 32 m (minimum 100) | hv0 rv0 city x8 (1,1,1,1,1,1,1,1) | 1070.2 |
| delta_megacity | 11 | pass |  | hv13 rv0 | 169.3 |
| delta_megacity | 404 | pass |  | hv0 rv1 | 162.9 |
| delta_megacity | 1999 | pass |  | hv9 rv1 city x7 (1,5,2,2,2,3,5) | 1194.2 |
| delta_megacity | 3141 | fail | transit_curves (1): Maglev Line (maglev): radius 484 m (minimum 500) | hv0 rv0 city x8 (9,2,2,1,6,4,5,2) | 1223.3 |
| delta_megacity | 4412 | pass |  | hv0 rv3 city x8 (2,1,2,1,1,1,3,3) | 1436.0 |
| delta_megacity | 5077 | fail | transit_curves (1): Delta Loop (sky_tube): radius 168 m (minimum 300) | hv0 rv0 city x8 (8,7,1,3,4,1,1,3) | 1345.3 |
| delta_megacity | 8128 | fail | transit_curves (1): Delta Loop (sky_tube): radius 83 m (minimum 300) | hv3 rv1 city x8 (5,1,4,2,1,1,1,5) | 1009.6 |
| delta_megacity | 27182 | fail | transit_curves (1): Delta Loop (sky_tube): radius 46 m (minimum 300) | hv12 rv1 city x8 (1,2,2,6,1,2,2,1) | 947.9 |
| nexus_city | 11 | fail | placement (1): 'Neon Market' is not west_of 'Transit Nexus' (bearing 20 deg)<br>curve_radius (1): segment rs00011 (highway): radius 133 m near (-337, -266), minimum 150 m | hv5 rv2 city x8 (2,2,3,2,3,2,2,4) | 1033.6 |
| nexus_city | 404 | pass |  | hv13 rv0 | 128.6 |
| nexus_city | 1207 | pass |  | hv11 rv0 city x3 (4,4,1) | 440.7 |
| nexus_city | 1999 | pass |  | hv1 rv1 | 118.1 |
| nexus_city | 3141 | pass |  | hv12 rv0 | 152.4 |
| nexus_city | 5077 | pass |  | hv6 rv0 | 147.9 |
| nexus_city | 8128 | pass |  | hv6 rv0 city x1 (3) | 250.4 |
| nexus_city | 27182 | pass |  | hv1 rv0 city x4 (1,1,1,3) | 527.6 |
| nyxllor | 11 | pass |  | hv10 rv0 | 127.1 |
| nyxllor | 404 | pass |  | hv1 rv1 city x1 (2) | 236.1 |
| nyxllor | 1999 | pass |  | hv1 rv1 city x1 (2) | 252.4 |
| nyxllor | 2077 | pass |  | hv18 rv0 | 121.8 |
| nyxllor | 3141 | fail | open_space_share (1): 'Launch Key' (spaceport): 71% open (target 0% to 50%) | hv7 rv2 city x8 (4,2,2,2,5,3,1,3) | 1055.6 |
| nyxllor | 5077 | pass |  | hv1 rv1 city x3 (1,5,1) | 496.1 |
| nyxllor | 8128 | pass |  | hv19 rv0 | 146.5 |
| nyxllor | 27182 | pass |  | hv1 rv0 | 147.3 |
| nyxllor_pinned | 11 | fail | bridge_clearance (1): junction rn00283 is out on the water (on a bridge)<br>curve_radius (1): segment rs00031 (highway): radius 111 m near (-351, -1168), minimum 150 m | hv5 rv0 city x8 (3,3,6,6,2,2,3,3) | 1167.9 |
| nyxllor_pinned | 404 | pass |  | hv1 rv0 city x6 (1,2,1,2,1,1) | 846.3 |
| nyxllor_pinned | 1999 | fail | curve_radius (1): segment rs00021 (highway): radius 51 m near (-1174, 132), minimum 150 m | hv10 rv0 city x8 (1,1,2,1,1,1,4,5) | 1224.9 |
| nyxllor_pinned | 2078 | pass |  | hv4 rv0 city x1 (1) | 237.8 |
| nyxllor_pinned | 3141 | pass |  | hv4 rv0 city x2 (1,2) | 357.5 |
| nyxllor_pinned | 5077 | fail | placement (1): 'Neon Strand' should be on the coast<br>level_continuity (1): rs02321 meets node rn00160 at 11.88 m, the node is at 7.69 m | hv17 rv0 city x8 (3,3,3,2,2,3,2,4) | 1216.0 |
| nyxllor_pinned | 8128 | fail | placement (1): 'Highcrest' is not east_of 'The Stacks' (bearing 21 deg) | hv3 rv0 city x8 (1,1,2,3,2,3,1,1) | 1104.2 |
| nyxllor_pinned | 27182 | pass |  | hv19 rv2 city x5 (1,1,1,2,2) | 760.6 |
| peninsula_city | 11 | fail | building_overlaps (1): d04.lm01.bld (wheel) and d04.mg01.bld2 (leg) overlap by 45.9 m2 between 4.0 and 24.5 m | hv13 rv0 city x8 (1,3,1,5,1,3,1,5) | 520.6 |
| peninsula_city | 404 | pass |  | hv2 rv0 | 51.0 |
| peninsula_city | 1999 | pass |  | hv11 rv0 | 71.6 |
| peninsula_city | 3141 | pass |  | hv10 rv0 | 65.1 |
| peninsula_city | 5077 | pass |  | hv13 rv0 | 86.2 |
| peninsula_city | 8128 | pass |  | hv2 rv0 city x3 (1,2,1) | 183.6 |
| peninsula_city | 9081 | pass |  | hv0 rv0 | 43.8 |
| peninsula_city | 27182 | pass |  | hv2 rv0 city x3 (2,1,2) | 173.7 |
| test_delta | 11 | pass |  | hv0 rv1 | 95.2 |
| test_delta | 12 | pass |  | hv18 rv3 | 141.0 |
| test_delta | 404 | pass |  | hv14 rv2 city x1 (4) | 210.2 |
| test_delta | 1999 | pass |  | hv3 rv2 | 94.4 |
| test_delta | 3141 | pass |  | hv3 rv3 city x1 (5) | 202.4 |
| test_minimal | 11 | pass |  | hv18 rv0 | 65.2 |
| test_minimal | 42 | fail | placement (1): 'Core' is not at edge 'center' | hv11 rv0 city x8 (1,1,1,1,1,1,2,1) | 360.6 |
| test_minimal | 404 | fail | road_graph (1): exit 'west' was not built<br>walkway_graph (1): landmass lm04: 2 walkway components (walk nodes 116, 1) | hv5 rv3 city x8 (2,2,2,2,2,2,2,2) | 299.6 |
| test_minimal | 1999 | pass |  | hv6 rv0 | 47.5 |
| test_minimal | 3141 | fail | placement (1): 'Core' is not at edge 'center'<br>road_graph (1): exit 'west' was not built<br>lot_block_sizes (1): district d04: median block size 77 m (range 200 to 400)<br>open_space_share (1): 'Launch' (spaceport): 66% open (target 0% to 50%)<br>megasite_access (1): d04.ms01 'Launch Spaceport': no road within 40 m | hv5 rv0 city x8 (5,5,5,5,5,5,5,5) | 283.1 |
| test_pinned | 11 | pass |  | hv0 rv0 city x1 (1) | 153.3 |
| test_pinned | 17 | pass |  | hv0 rv0 | 76.0 |
| test_pinned | 404 | pass |  | hv0 rv0 city x1 (2) | 157.5 |
| test_pinned | 1999 | pass |  | hv0 rv0 | 75.1 |
| test_pinned | 3141 | pass |  | hv0 rv0 | 78.4 |
| test_small | 7 | pass |  | hv1 rv0 | 43.8 |
| test_small | 11 | pass |  | hv1 rv1 | 42.4 |
| test_small | 404 | pass |  | hv1 rv1 | 45.7 |
| test_small | 1999 | pass |  | hv1 rv1 | 41.8 |
| test_small | 3141 | pass |  | hv16 rv0 city x1 (1) | 85.7 |
