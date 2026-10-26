# citygen sweep before M8a (main with PR 14)

33 of 68 builds pass (49%)

| spec | pass | builds |
|---|---|---|
| archipelago_free_port | 4 | 8 |
| delta_megacity | 3 | 8 |
| nexus_city | 1 | 8 |
| nyxllor | 5 | 8 |
| nyxllor_pinned | 3 | 8 |
| peninsula_city | 5 | 8 |
| test_delta | 5 | 5 |
| test_minimal | 0 | 5 |
| test_pinned | 3 | 5 |
| test_small | 4 | 5 |

| failing check | builds |
|---|---|
| curve_radius | 12 |
| placement | 10 |
| transit_curves | 9 |
| megasite_contents | 7 |
| named_bridges | 6 |
| level_continuity | 4 |
| district_shares | 3 |
| island_sizes | 3 |
| transit_stops | 3 |
| bridge_clearance | 3 |
| open_space_share | 3 |
| road_graph | 3 |
| transit_altitude | 2 |
| building_clear_zones | 2 |
| districts_served | 1 |
| lot_block_sizes | 1 |
| (crash) | 1 |
| road_avoidance | 1 |
| road_duplicates | 1 |

| spec | seed | result | failing checks (first failure) | retries | s |
|---|---|---|---|---|---|
| archipelago_free_port | 11 | fail | district_shares (3): 'Crown Island': share 0.439 vs 0.340 (spec), +29%<br>placement (1): 'Crown Island' is not on island 'Crown Island'<br>island_sizes (1): island 'Crown Island' was not built<br>named_bridges (1): named bridge 'Crown Causeway' (road_rail, Crown Island to north_exit) was not built<br>curve_radius (1): segment rs00001..rs00002 (highway): radius 58 m near (-1663, 1687), minimum 150 m | hv0 rv0 city x1 (14) | 260.3 |
| archipelago_free_port | 404 | fail | curve_radius (1): segment rs00120..rs00128 (avenue): radius 12 m near (682, -12), minimum 40 m<br>level_continuity (1): rs01556 meets node rn00769 at 0 m, the node is at 1.1 m | hv0 rv0 city x1 (3) | 110.0 |
| archipelago_free_port | 1999 | pass |  | hv0 rv0 city x1 (2) | 42.1 |
| archipelago_free_port | 3141 | fail | district_shares (3): 'Crown Island': share 0.439 vs 0.340 (spec), +29%<br>placement (1): 'Crown Island' is not on island 'Crown Island'<br>island_sizes (1): island 'Crown Island' was not built<br>named_bridges (1): named bridge 'Crown Causeway' (road_rail, Crown Island to north_exit) was not built<br>curve_radius (3): segment rs00001 (highway): radius 58 m near (-1663, 1687), minimum 150 m | hv0 rv0 | 183.4 |
| archipelago_free_port | 3301 | pass |  | hv0 rv0 | 18.3 |
| archipelago_free_port | 5077 | pass |  | hv0 rv0 | 19.1 |
| archipelago_free_port | 8128 | fail | district_shares (5): 'Crown Island': share 0.260 vs 0.340 (spec), -23%<br>placement (1): 'Kettle Island' is not on island 'Kettle Island'<br>island_sizes (1): island 'Kettle Island' was not built<br>named_bridges (1): named bridge 'Kettle Span' (road_rail, Crown Island to Kettle Island) was not built<br>curve_radius (1): segment rs00003 (highway): radius 37 m near (-92, 203), minimum 150 m | hv0 rv0 | 118.5 |
| archipelago_free_port | 27182 | pass |  | hv0 rv0 city x1 (2) | 79.2 |
| delta_megacity | 11 | fail | megasite_contents (1): d05.ms01 'Freight Terminal' (freight_terminal): no rail_track<br>transit_curves (1): Delta Loop (sky_tube): radius 16 m (minimum 300) | hv3 rv3 city x1 (4) | 439.1 |
| delta_megacity | 404 | pass |  | hv0 rv1 city x1 (2) | 251.8 |
| delta_megacity | 1999 | pass |  | hv9 rv1 city x1 (6) | 144.6 |
| delta_megacity | 3141 | fail | level_continuity (1): rs01025 meets node rn01139 at 4.25 m, the node is at 0.01 m<br>transit_stops (1): Delta Loop: no station serves 'Old Town' (nearest 354 m away)<br>transit_curves (1): Delta Loop (sky_tube): radius 104 m (minimum 300) | hv0 rv1 city x1 (10) | 233.2 |
| delta_megacity | 4412 | pass |  | hv0 rv3 city x1 (2) | 177.1 |
| delta_megacity | 5077 | fail | curve_radius (2): segment rs00022 (highway): radius 119 m near (-130, 1748), minimum 150 m<br>transit_stops (2): Delta Loop: no station serves 'Old Town' (nearest 88 m away)<br>transit_curves (1): Delta Loop (sky_tube): radius 136 m (minimum 300) | hv0 rv0 city x1 (6) | 332.6 |
| delta_megacity | 8128 | fail | megasite_contents (1): d05.ms01 'Freight Terminal' (freight_terminal): no rail_track<br>transit_curves (1): Delta Loop (sky_tube): radius 103 m (minimum 300) | hv3 rv3 city x1 (3) | 225.0 |
| delta_megacity | 27182 | fail | megasite_contents (1): d05.ms01 'Freight Terminal' (freight_terminal): no rail_track<br>transit_altitude (1): Delta Loop (sky_tube): z 150.06 m at (669.29, -719.69) outside 40 to 150.0 m | hv3 rv0 city x1 (4) | 235.0 |
| nexus_city | 11 | fail | placement (1): 'Neon Market' is not west_of 'Transit Nexus' (bearing 20 deg)<br>named_bridges (1): named bridge 'Horizon Bridge' (road_rail, Transit Nexus to Harbor Industrial) was not built<br>curve_radius (1): segment rs00010 (highway): radius 133 m near (-337, -266), minimum 150 m | hv5 rv0 | 228.2 |
| nexus_city | 404 | fail | districts_served (1): 'Silver Island' is not served by an avenue<br>bridge_clearance (1): junction rn00018 is out on the water (on a bridge)<br>open_space_share (1): 'Silver Island' (research_campus): 100% open (target 15% to 55%) | hv13 rv0 city x1 (4) | 206.2 |
| nexus_city | 1207 | pass |  | hv1 rv1 | 59.2 |
| nexus_city | 1999 | fail | named_bridges (1): named bridge 'Silver Span' (road, Old Town to Silver Island) was not built<br>transit_curves (1): Magenta Line (maglev): radius 328 m (minimum 500) | hv1 rv3 | 201.8 |
| nexus_city | 3141 | fail | transit_curves (1): Spire Line (sky_tube): radius 200 m (minimum 300) | hv12 rv1 city x1 (4) | 192.7 |
| nexus_city | 5077 | fail | road_graph (1): exit 'west' was not built<br>named_bridges (2): named bridge 'Baylink Bridge' (road, Neon Market to west_exit) was not built<br>lot_block_sizes (1): district d09: median block size 580 m (range 100 to 200)<br>open_space_share (2): 'Harbor Industrial' (industrial_port): 56% open (target 0% to 10%) | hv4 rv0 | 238.5 |
| nexus_city | 8128 | crash | crash: KeyError: -1 |  | 30.2 |
| nexus_city | 27182 | fail | curve_radius (1): segment rs00031 (highway): radius 23 m near (740, -774), minimum 150 m<br>level_continuity (1): rs02519 meets node rn00673 at 0 m, the node is at 3.16 m | hv1 rv2 | 193.6 |
| nyxllor | 11 | fail | megasite_contents (1): d06.ms01 'Vess Freight Terminal' (freight_terminal): no rail_track | hv1 rv0 city x1 (2) | 222.6 |
| nyxllor | 404 | pass |  | hv1 rv3 | 49.7 |
| nyxllor | 1999 | fail | transit_curves (1): Halo Line (elevated_rail): radius 88 m (minimum 150) | hv1 rv1 city x1 (2) | 231.2 |
| nyxllor | 2077 | pass |  | hv18 rv0 city x1 (3) | 247.7 |
| nyxllor | 3141 | fail | open_space_share (1): 'Launch Key' (spaceport): 71% open (target 0% to 50%) | hv7 rv1 city x1 (2) | 250.6 |
| nyxllor | 5077 | pass |  | hv1 rv1 city x1 (1) | 148.8 |
| nyxllor | 8128 | pass |  | hv19 rv1 city x1 (3) | 245.4 |
| nyxllor | 27182 | pass |  | hv1 rv0 | 62.9 |
| nyxllor_pinned | 11 | fail | bridge_clearance (1): junction rn00270 is out on the water (on a bridge)<br>road_avoidance (1): segment rs00032 (highway) runs 44 m through flight cone of 'Launch Key Spaceport'<br>curve_radius (1): segment rs00030 (highway): radius 111 m near (-351, -1168), minimum 150 m<br>building_clear_zones (1): d01.pin.path38: tower mass on road rs00304 (454.5 m2) | hv5 rv1 city x1 (5) | 218.7 |
| nyxllor_pinned | 404 | pass |  | hv4 rv3 city x1 (2) | 198.6 |
| nyxllor_pinned | 1999 | fail | curve_radius (1): segment rs00022 (highway): radius 51 m near (-1174, 132), minimum 150 m<br>megasite_contents (1): d06.ms01 'Vess Freight Terminal' (freight_terminal): no rail_track | hv10 rv0 city x1 (3) | 232.7 |
| nyxllor_pinned | 2078 | pass |  | hv4 rv3 city x1 (2) | 201.4 |
| nyxllor_pinned | 3141 | pass |  | hv4 rv1 city x1 (4) | 123.1 |
| nyxllor_pinned | 5077 | fail | placement (1): 'Neon Strand' should be on the coast<br>level_continuity (1): rs02132 meets node rn00150 at 11.87 m, the node is at 7.69 m | hv17 rv0 | 213.2 |
| nyxllor_pinned | 8128 | fail | placement (1): 'Highcrest' is not east_of 'The Stacks' (bearing 21 deg) | hv3 rv1 | 220.8 |
| nyxllor_pinned | 27182 | fail | building_clear_zones (1): d01.mg02.bld3: podium mass on open d01.os011 (0.5 m2)<br>transit_stops (1): Crown Line: no station serves 'Highcrest' (nearest 20 m away) | hv19 rv1 | 269.5 |
| peninsula_city | 11 | fail | road_duplicates (1): segments rs00053..rs00098 and rs00054..rs00079 run within 25 m of each other for 286 m | hv13 rv0 city x1 (5) | 108.7 |
| peninsula_city | 404 | pass |  | hv2 rv0 city x1 (2) | 128.0 |
| peninsula_city | 1999 | pass |  | hv11 rv0 city x1 (2) | 58.2 |
| peninsula_city | 3141 | pass |  | hv10 rv0 | 26.2 |
| peninsula_city | 5077 | pass |  | hv13 rv0 | 32.8 |
| peninsula_city | 8128 | fail | transit_curves (1): East Shore Line (elevated_rail): radius 105 m (minimum 150) | hv2 rv0 | 109.3 |
| peninsula_city | 9081 | pass |  | hv0 rv0 | 15.4 |
| peninsula_city | 27182 | fail | transit_curves (1): East Shore Line (elevated_rail): radius 110 m (minimum 150)<br>transit_altitude (1): East Shore Line (elevated_rail): z 20.27 m at (375.33, -1038.78) outside 8 to 20.0 m | hv2 rv0 | 132.0 |
| test_delta | 11 | pass |  | hv0 rv2 city x1 (1) | 66.6 |
| test_delta | 12 | pass |  | hv0 rv3 | 42.1 |
| test_delta | 404 | pass |  | hv0 rv2 city x1 (1) | 85.1 |
| test_delta | 1999 | pass |  | hv3 rv3 | 34.4 |
| test_delta | 3141 | pass |  | hv3 rv3 city x1 (5) | 69.9 |
| test_minimal | 11 | fail | megasite_contents (1): d02.ms01 'Harbor Freight Terminal' (freight_terminal): no rail_track | hv18 rv0 | 59.0 |
| test_minimal | 42 | fail | placement (1): 'Uptown' is not north_of 'Core' (bearing 87 deg) | hv11 rv0 city x1 (2) | 68.9 |
| test_minimal | 404 | fail | placement (1): 'Uptown' is not north_of 'Core' (bearing 79 deg)<br>road_graph (1): exit 'west' was not built<br>curve_radius (1): segment rs00009 (highway): radius 54 m near (330, 1475), minimum 150 m | hv16 rv1 | 55.9 |
| test_minimal | 1999 | fail | placement (1): 'Core' is not at edge 'center' | hv15 rv1 city x1 (2) | 72.5 |
| test_minimal | 3141 | fail | placement (1): 'Uptown' is not north_of 'Core' (bearing 284 deg)<br>road_graph (1): exit 'west' was not built<br>megasite_contents (1): d02.ms01 'Harbor Freight Terminal' (freight_terminal): no rail_track | hv5 rv1 | 51.4 |
| test_pinned | 11 | fail | curve_radius (1): segment rs00022 (highway): radius 23 m near (15, 1289), minimum 150 m | hv0 rv0 city x1 (2) | 135.9 |
| test_pinned | 17 | pass |  | hv0 rv0 | 26.1 |
| test_pinned | 404 | pass |  | hv0 rv0 | 26.6 |
| test_pinned | 1999 | pass |  | hv0 rv0 | 26.2 |
| test_pinned | 3141 | fail | curve_radius (1): segment rs00028 (highway): radius 23 m near (15, 1289), minimum 150 m | hv0 rv0 | 133.4 |
| test_small | 7 | pass |  | hv1 rv0 | 15.7 |
| test_small | 11 | pass |  | hv1 rv0 city x1 (1) | 27.0 |
| test_small | 404 | fail | bridge_clearance (2): segment rs01055 runs 11 m over water without a bridge | hv1 rv1 | 70.9 |
| test_small | 1999 | pass |  | hv1 rv1 | 15.0 |
| test_small | 3141 | pass |  | hv16 rv0 city x1 (1) | 30.0 |
