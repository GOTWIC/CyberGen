# First run-through (2026-10-29)

Swagnik's first walk and flight through a whole city in Unreal: Delta Megacity built from
scratch (`citygen build --blockout`, `assetgen build`) and imported with its stage 2 assets.
The issues probably show in every city. Each one below has what the code does today, what
Delta's `city_model.json` measures, and the milestone that fixes it (citygen scope section
12, assetgen scope section 14).

## Roads

| Issue | Found | Milestone |
|---|---|---|
| Roads that stop at random | 308 dead ends that are not at the map edge (152 streets, 81 alleys, 65 pedestrian, 5 service, 3 highway, 2 avenue); 206 of them have another road within 60 m straight ahead. They are left by the street clean-ups (a piece removed for a crossing, length or angle leaves the rest of its street) | M17 |
| Overlapping roads on straight stretches | 149 pairs of roads at the same level whose corridors overlap by more than 25 m2 outside any junction (avenue and street 47, street and street 44, highway and avenue 32, avenue and avenue 16) | M17 |
| Intersections with a vertical gap, worst where roads are not flat | In the model every leg ends at its node's height, but 78 of Delta's 1,580 junctions have a leg that reaches the junction polygon at another height (bridge approaches, ramps, M7's local streets joining a raised road); Delta is flat, so a terrain city has far more. AG7 draws the junction with an inverse-distance blend of the node and the legs' mid-edges, which does not pass through a leg's height at its cut edge: a step at every such leg | M18 (model), AG14 (mesh) |
| Roads going into buildings | No road corridor overlaps a building mass at the road's height in the model, so the clash is in the meshes (a building's parts or front reaching over the road, or a street piece reaching past its corridor) | M17 (check), AG14 |
| Trees poking through raised roads | 114 plants under a raised road reach its deck. `vegetation.overhead` treats a 20 m piece of a ramp whose underside is under 3.8 m as an embankment and skips it, but nothing builds an embankment there and no keep-out stops a trunk | M18 (embankments), M20 |
| Shallow ramps leave dead space under them | Ramps and runs at 5% (6% at most), bridge approaches at 5.5% | M18 |

## Structures and obstacles

| Issue | Found | Milestone |
|---|---|---|
| Overlapping bridges | None of Delta's 32 bridges (15 road, 17 pedestrian) overlaps another in plan in the model, so the overlap is in the meshes (likely a bridge drawn twice, by its bridge piece and its road's deck) | M17 (check), AG14 |
| Floating railings by the river | The model stands quay railings on the quay deck (`deck_z_m` 1.5 m); AG7 paves the quay at the ground, so they float 1.5 m | M20, AG14 |
| AC units floating over roofs | The model's roof items sit on their masses' roofs (6 of 16,114 do not), so the gap is in AG4's roof meshes (roof forms, finishes or equipment bases) | AG14 |
| Sky tubes and trains through buildings and platforms | Only sky tubes pass through masses (22 tube pieces, all through towers with a declared M5 portal); in the run-through they read as tubes through buildings | M19, AG14 |
| Supports not under the line | `transit._column_spots` moves a support to the median or the curbs of the road under it. The monorail puts its one column at a curb: 53 of its 94 columns stand more than 2 m off the beam (up to 13.5 m); sky tube pylons up to 13 m off | M19 |
| Uneven support spacing, long gaps over water | Supports every 25 to 69 m (median), skipped wherever no spot within 12 m is free, never in water: gaps up to 971 m (sky tube), 531 m (monorail), 270 m (maglev). Sky tubes should have 6 to 8 times fewer pylons, evenly spaced | M19 |
| Train lines too close to the roads under them | 5.5 m clear over a road deck; elevated rail at 10 to 16 m, monorail at 12 to 22 m | M19 |

## Aesthetics

| Issue | Found | Milestone |
|---|---|---|
| Buildings look the same, above all in the corporate core, and are lit alike at night | Towers are prisms on podiums (M3); AG2's 19 facade systems are mostly grids of rectangular windows; the night look is one interior atlas and one Night switch for every building | M21 (forms), AG15 (facades, night) |
| Far too few ads on the facades | Delta's sign slots: 444 neon bands and 252 facade billboards, 63 holo-ads (plus 13,208 shop signs and 1,016 roof billboards). Asked for: at least 7 times the facade neon, 2 to 4 times the holo-ads | M20 (slots), AG15 (assets) |
| Curved buildings look low-poly | `massing.circle` makes round masses 12, 20 or 32-gons (a 30 m radius is 15 cm off the circle between corners) and assetgen draws them with flat normals | M21 (arcs), AG14 (smooth walls) |
| Streets black at night; lamps light nothing on the ground | The blockout and assets have no light sources; the play features (PR #57) give the 48 lamps nearest the camera a point light at the lamp head by night, which does not reach the ground (likely the lamp mesh's own shadow, too few lights, or the night exposure) | AG15 (exporter) |
| A crosswalk and signals at every junction, far too many where junctions are close; some crosswalks too wide | Old Town: 117 of its 1,137 junctions signalized, each with crosswalks on every approach; 116 of Delta's 358 junctions with crosswalks are within 40 m of another; every crosswalk is 4 m wide, whatever the road | M18 |
