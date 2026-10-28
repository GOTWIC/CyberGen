# M13: terrain

M13 gives citygen ground that is not flat (`citygen/terrain.py`, checks in
`citygen/terrain_checks.py`, preview `citygen/preview_terrain.py`):

- **A height field from the spec:** hills, ridges, cliffs (a district on a plateau),
  flat districts, a smooth random relief and a rise inland.
- **Water at its own level:** the sea at 0; rivers falling to the mouth; canals, basins and
  marinas at the level of the water they join.
- **Roads that follow the ground within their grade:**
  - every road's grade line is fitted on one graph of the whole network;
  - cuts and fills sit between retaining walls;
  - a primary road deep in a hill is bored through it;
  - a primary road high over a valley stands on a terrain viaduct.
- **Highways routed round steep ground.**
- **Lots and buildings on slopes:**
  - lots too steep to build become hillside greens;
  - buildings stand on their entrance ground over stepped plinths.
- **Terrain-aware props and plants:** no parked cars on steep streets, no benches or stalls
  on steep ground, no trees on cliff faces, nothing on the ground under a terrain viaduct.
- **The ground in the blockout:** a 4 m heightfield, with everything draped on it.
- **Five new checks**, 86 in all (with M12's two).

The hilly sample is **Cragmouth** (`cities/cragmouth`). A spec without `terrain` builds exactly
the city it built before: the five samples, the pinned demo and the M12 stack demo are
byte-identical to M10 (on M12, M9 and M11), the code M13 is merged with.

## Art direction: Cragmouth

A cliffside port climbing out of a small bay, on a 3.4 x 3.0 km map with the bay to the south,
so that the iso camera looks up the slopes:

| District | Ground |
|---|---|
| Low Harbor (industrial port) | levelled flat at 5.9 m: cranes, container stacks, slips |
| Lantern Steps (entertainment market) | the slope west of the river mouth, up to about 25 m |
| Crown Heights (corporate core) | a plateau 34 m over the bay with a 40 m hill on it; a cliff 110 m wide faces the bay (`facing` south), the other sides rise over 450 m |
| Old Quarter (old town) | a 75 m hill (radius 950 m): the crooked streets climb a dome |
| Ridgeback (megablock residential) | a 70 m ridge running north: towers on terraces among hillside greens |
| Hollow (midtown mixed) | the valley of the Cragwater, with a levelled central park |

Choices made along the way:

- **The Crown cliff faces the bay only.** A cliff all round put the plateau's edge on the
  river. Every road across the gorge then needed 20 to 26 m of fill at its junctions, more
  than any wall or terrain viaduct could carry. `Cliff.facing` keeps the cliff to the bay;
  the river side rises as a broad escarpment.
- **No M7 viaducts** (`elevated_share` 0). On hills an M7 viaduct's ramps use up the grade, so
  the grade line under them cannot follow the ground, and the East Exit stood 15 m over the
  valley for 800 m. In a hill town the highways cut and bore instead.
- **Steeper than the first draft.** At 55 m hills and a 28 m cliff the relief hardly showed
  at city scale under the buildings. The final spec has 75 m and 70 m hills, a 34 m plateau
  and 8 m of relief.

## How the ground is made

**Natural ground** (`terrain.field`, at the start of each road attempt, on a 4 m grid):

$$H = s + i\,d_{sea} + \sum_{hills} h\,(1 - r^2/R^2)^2 + \sum_{ridges} h\,(1 - d^2/w^2)^2 + \text{relief}$$

- Banks are then carved down to the water: $H \le \ell + 1.5 + g\,d$, where $\ell$ is the
  water's level and $g$ is 10% (12% from the sea).
- Cliff districts are lifted onto their plateaus with a smoothstep over `width_m` on the sides
  they face and over `slope_m` elsewhere.
- Flat districts and every megasite are levelled to their mean.
- The ground in the water sits at the water's level; the land beside it stays 0.3 m higher.

All of this is numpy elementwise arithmetic (each step correctly rounded) and GEOS distances,
with no numpy reductions, and the values land on the 1 cm grid.

**Grade lines** (`terrain.grade`, after M2):

- Every road is one chain of stations 10 m apart. Nodes are shared, and so are crossings
  without a node (an M7 overpass, an M9 lid), so grade separations keep their clearances.
- Each edge may climb at most the class's grade times its length, less what the road's own z
  profile climbs there.
- In integer centimeters, two multi-source Dijkstra runs give the highest and lowest profiles
  within the caps:

$$U(v) = \min_u \big(H_u + d(u, v)\big), \qquad L(v) = \max_u \big(H_u - d(u, v)\big)$$

- The grade line is $(U + L)/2$: the closest to the ground in the largest deviation, and it
  meets the ground wherever the ground is within grade.

**Finished ground:**

- Each road corridor (its full width plus 1.5 m) lies on its grade line.
- A step of up to 1.5 m blends over 6 m.
- Any larger step a road makes is a **retaining wall**, traced on the grid where the graded
  ground steps more than 1.5 m between two grid points and the natural ground does not.
- A primary road at least 14 m under the natural ground for 40 m is a **bored tunnel**; the
  hill stays over it.
- A primary road at least 15 m over the ground for 20 m stands on a **terrain viaduct**
  (a deck, and columns every 32 m).
- **Lots** whose ground falls more than 15 m become hillside greens. They count as lots in the
  open-space share, since they are terrain and not planned open space.

**After M3:**

- Each building's `base_m` is at its main entrance; buildings joined by skybridges share a
  floor grid. Its `plinth_m` is the lowest ground under the footprint.
- The metro is graded on ground + z.
- Props and plants are filtered to the ground.

**Frames.** Every z in the model outside the terrain stays measured from the finished ground
where it stands:

- a road's z from its `ground` profile;
- a node's from `ground_m`;
- a building's from `base_m`;
- a skybridge's from its `base_m`.

So M7, M9 and M5 clearances need no change, and grades are measured on ground + z.

## Checks (82 to 86)

| Check | What it asks |
|---|---|
| `ground_grades` | every road at most its class's grade on the ground: highways and ramps 6%, avenues 8%, streets and service roads 12%, alleys and pedestrian ways 15% |
| `cut_fill` | open cuts at most 20 m, fills at most 18 m; deeper cuts bored with 1 m of rock over the roof, higher fills on terrain viaducts |
| `retaining_walls` | no step graded steeper than 1:1.5 without a retaining wall, a portal, a building or the water there |
| `building_seats` | every building's base within half a floor of its entrance ground, at most 16 m of plinth under it and 16 m of ground over it; every skybridge on a base |
| `water_levels` | the sea at 0, rivers never rising downstream, waterways at the level of what they join, the ground in the water at its level |

`transit_grades`, and the metro in `tunnel_grades`, now measure on ground + z. A flat city
passes the five new checks with nothing to check.

## Builds

M13 is built on M10 (stable ids, edit, lock), M12, M9 and M11. All eight cities pass all 86
checks. Each `city_model.json` and `report.json` is byte-identical on the M4 Mac (arm64) and
on x86_64 Linux (docker `citygen-x86`, `linux/amd64`, the worktree mounted read-only,
`CITYGEN_WORKERS=3`), and the stage traces match entry for entry (`citygen trace diff`):

| City | Full-city tries | sha256 of `city_model.json` (both machines) | vs M10 | Release lock |
|---|---|---|---|---|
| cragmouth | 1 | `1175f1f22e0800fabae9bd1a436dec96c6313072dc71f25b4c304d1106c9e6f4` | new (the hilly sample) | [`city.lock.json`](cragmouth/city.lock.json) |
| archipelago_free_port | 1 | `edf4e11cc92ee86892ec615fb7c1028ddbc1208e69a9f4489c7b5910ec549b18` | identical | [`city.lock.json`](archipelago_free_port/city.lock.json) |
| delta_megacity | 1 | `228fdb26390bacedf84da87dd39daa6fd40d3fdb3fd9159837ab61a7419c4538` | identical | [`city.lock.json`](delta_megacity/city.lock.json) |
| nexus_city | 1 | `9928e4ece1cca83cd7401543ed11dfa2f2fbeedc7a50570c4cad0648b92ca4b8` | identical | [`city.lock.json`](nexus_city/city.lock.json) |
| peninsula_city | 1 | `b3cc9920e125f4e4cb996fd442bad66051e21dd5b72024b9e87e9c36230b2e91` | identical | [`city.lock.json`](peninsula_city/city.lock.json) |
| vesper_bay | 1 | `3bd79ca0fb90f712c665051464feaaed718e31e2b52b514b524149673eda0da2` | identical | [`city.lock.json`](vesper_bay/city.lock.json) |
| vesper_bay_pinned | 2 | `2d362ab49246119ff9b576ecf74a1ac0ed5dbf9d582a02d2798446d95b773508` | identical | [`city.lock.json`](vesper_bay_pinned/city.lock.json) |
| vesper_bay_stacks | 1 | `2e16890979a5bbbc90cb57c243205c967cd72a4f0011c00004449ef204d0cee5` | identical | [`city.lock.json`](vesper_bay_stacks/city.lock.json) |

The flat cities' blockout plans are M10's too (`blockout_plans` in
`tests/data/golden_hashes.json`), so their 8K renders are M10's
(`docs/progress/M10/<city>/render_iso_city.jpg`). Their reports gain the five terrain checks
(passing with nothing to check); every stage hash of their traces is M10's.

**Cragmouth** in numbers (`report.txt`):

- **Ground:** from 0 to 95 m.
- **Grade lines:** cuts to 18.7 m and fills to 18.7 m.
- **Retaining walls:** 1280, the highest 19.7 m.
- **Bored tunnels:** seven, 56 to 137 m long, with 7 to 9 m of rock over their roofs. The
  three Crown Heights Boulevard tunnels run under Crown Hill; the four Ridgeback tunnels run
  through the ridge.
- **Terrain viaduct:** one.
- **Hillside greens:** 181.
- **Plinths:** the highest is 13.1 m.
- **Dressing:** 592 parked cars left off streets steeper than 10%, and 165 benches and stalls
  off steep ground (on M12: 566 and 164; the props now draw on M10's stable ids, the ground
  and the roads are the same).
- **Water:** the Cragwater falls along its 457 stations to the bay.
- **Tries:** it builds on its first full-city try.

Each city folder has every generator preview, the build report, the stage trace and the
release lock. Cragmouth also has its blockout report, `render_top.jpg`, the 8K
`render_iso_city.jpg`, `preview_terrain.png` and the 8K `render_hillside.jpg`.

## With M10: ids, regeneration, locks

**Stable ids.** M13's entities are named from what and where they are, like everything else
(`ids.py` derives them from the build-order ids M13 gives them):

| Entity | Id | Example (Cragmouth) |
|---|---|---|
| retaining wall | its road segment, `wall` and its cell (`wall.<cell>` where no segment) | `rs.w997n776.wall.w1032n756` |
| terrain viaduct deck, column | its road segment, `viaduct` or `tvcol` and the cell | `rs.e814n566.viaduct.e814n566`, `rs.e814n566.tvcol.e766n565` |
| bored tunnel | `bore` and its cell | `bore.w487n577` |
| hillside green | district, `os.slope` and its cell | `d03.os.slope.w598n231` |

The renaming pass also renames the water body each `terrain.water_levels` row names. No new
collection or id field: walls and viaducts name their segment in `supports` and
`attrs.segment` (already in `REFS` and `edit.ATTR_REFS`), bored tunnels in `segment_ids`.
`tests/test_terrain.py` scans the hilly test city for build counters (M10's pattern plus
`rw`, `tb`, `tv`, `wall`, `bore`, `viaduct`, `tvcol`, `slope`) and dangling references.

**District regeneration on a hilly city.** The grade fit is one graph of the whole network, so
new streets in a district could pull the grade lines of held roads around it. In a
regeneration `add_local` passes every held road's old grade line to `terrain.grade` (`held`):
its stations are fixed at it, and the free vertices are fitted between the bounds those set:

$$\tilde U = \max\Big(U,\ \max_f \big(z_f - d(f, v)\big)\Big), \qquad \tilde L = \min\Big(L,\ \min_f \big(z_f + d(f, v)\big)\Big)$$

(a fixed vertex takes no bound from its neighbors, so without the clamp the envelopes would
break the grade beside it). The splice takes the finished ground (`terrain`) and the retaining
walls from the new build (it differs from the old only around the district's new streets).

Three fixes came out of regenerating the hilly test city:

- `junctions.one_way_loops` reversed a street but not its z profile, so a one-way street that
  ramps up to a raised avenue had its ramp at the wrong end (`level_continuity`). It is a bug
  on main that no sample hits (their models are unchanged).
- `edit._close`: a building's gameplay rows (its points of interest) follow it when the new
  build changed the building (they stayed old and named units it no longer had).
- `edit._ground_cover`: old lots and open spaces under a changed new lot, open space or
  building go (an old park stayed under a new lot of a seam block).

Every district of the small hilly test city regenerates with every check passing and every
held road back as it was, grade line included (`test_hilly_regeneration_holds_every_road`).

On the samples (`citygen build SPEC OUT --base BUILD --district NAME`, Mac shared with the
sweep and pytest; reports and diff maps in [`regenerated/`](regenerated/)):

| City, district | Time | Held roads back as they were | Outside the district changed (through references) | Checks |
|---|---|---|---|---|
| Cragmouth, Old Quarter (on its 75 m hill) | 70 s | 1674 of 1674 | 15027 (14083) | all 86 pass |
| Vesper Bay, Old Town (flat) | 41 s | 1553 of 1553 | 225 (4) | all 86 pass |
| Cragmouth, Crown Heights | 62 s | 3065 of 3076 | 6068 (5251) | 12 fail |
| Cragmouth, Low Harbor | 74 s | 3131 of 3158 | 4341 (3942) | 14 fail |
| Cragmouth, Lantern Steps | 74 s | 2308 of 2309 | 22613 (21827) | 3 fail |
| Cragmouth, Ridgeback | 77 s | 3007 of 3038 | 5298 (4287) | 17 fail |
| Cragmouth, Hollow | 74 s | 2937 of 2939 | 1850 (497) | 4 fail |

Vesper Bay's Old Town is as on M10 (1553 of 1553, 225 (4)). Of Cragmouth's six districts only
the Old Quarter regenerates cleanly. The others are not terrain: the same spec without its
`terrain` block (`regenerated/cragmouth_flat_city_spec.json`, a flat city of the same layout
whose M1 routes without the slope cost) fails the same way (Low Harbor 12 checks and 3212 of
3240 held roads, Lantern Steps 6 and 2373 of 2388, Crown Heights 1 and 3122 of 3125;
`regenerated/cragmouth_flat__*_report.txt`), and every failure is M10's frame:

- a new street meets a held road at a new point instead of an old node (Crown Heights: the
  waterfront avenue split at a new node), or a held node comes back doubled 1 cm apart;
- a neighbor district laid after the regenerated one comes back with its grid at other
  offsets (Hollow beside Crown Heights), so the splice holds both its old streets and new
  ones beside them (duplicates, 0 degree junctions, buildings on the new streets);
- M3 draws each lot by its index in its district's build-order lot list, so a seam block of
  a neighbor split 1 m differently reseeds the whole neighbor district's buildings; the
  splice then takes them all through references (Old Quarter: 1180 buildings of Lantern
  Steps, every check passing). Keying M3's draws on stable lot ids would fix this but moves
  every city's buildings.

These are open items for M10 (below); M2 never reads the terrain.

**Locks.** Every sample has a release lock (`citygen lock <build> --release 1.0`, from the
builds above, code `a0a252eb2ed6`). `citygen lock --verify` rebuilds two of them byte for
byte:

| Release | `citygen lock --verify` |
|---|---|
| Cragmouth 1.0 | PASS, the same `city_model.json` byte for byte, 80 s |
| Saltreach Free Port 1.0 | PASS, byte for byte, 33 s |

A lock names its code, so these go stale with any change to `citygen/*.py`.

## Sweep

`citygen sweep --suite m8a --workers 3` on M13 on M10 (`sweep.md`, `sweep.json`), against
M10's sweep (`docs/progress/M10/sweep.json`):

| | M10 | M13 |
|---|---|---|
| builds passing every check | 58 of 68 | 58 of 68 |
| builds newly failing | | 0 |
| failing builds with other failing checks | | 0 |
| builds with other bytes | | 6, all passing or failing as on M10 |
| full-city tries beyond the first, all 68 builds | 111 | 105 |
| build time, all 68 (the Mac shared with the x86 run, pytest and regenerations) | 8346 s | 7421 s |

The six builds with other bytes (archipelago_free_port s404, delta_megacity s5077, vesper_bay
s404 and s3141, test_pinned s404, test_delta s404) now pass on an earlier full-city try: on
M10 a try failed `level_continuity` because `junctions.one_way_loops` reversed a street but not
its z profile (checked on main's code: archipelago_free_port s404 fails `level_continuity` on
its first try there and passes on its second; here it passes on its first). vesper_bay s3141
fails `open_space_share` on its last try as on M10 (Launch Key 67% open, 71% on M10).
The other 62 builds are byte for byte M10's.

**Cragmouth at eight seeds** (`citygen sweep cities/cragmouth/city_spec.json --seeds
6133,11,404,1999,3141,5077,8128,27182 --workers 3`, in `sweep_cragmouth.md` and `.json`, on
M13 on M10): **6 of 8 pass**, the same seeds with the same failures and full-city tries as on
M12.

| Seed | Result |
|---|---|
| 6133 (its own), 404, 3141, 5077, 8128, 27182 | pass |
| 11 | fails `cut_fill`: a street on 18.5 m of fill |
| 1999 | fails `cut_fill`: a street in a 20.1 m cut |

Both failures are local streets. Only primary roads are bored or put on viaducts, so a street
laid straight across the steepest ground (the Crown escarpment) can still cut or fill past the
limits; see the open items.

## Tests

The full pytest passes on M13 on M10 (480 passed, 2 skipped, 54 min with the Mac shared with
the sweep; the tests that read `docs/progress` run again after main's folder renames).
`tests/test_terrain.py` covers:

- flat models carrying no terrain;
- the spec's terrain references;
- the Lipschitz fit;
- a small hilly city: all checks passing, grade lines on the 1 cm grid meeting their nodes,
  buildings seated, the sea at 0, the ground rising where asked and the harbor levelled;
- each terrain check failing on a broken copy;
- Cragmouth's build, its tunnels' names, the Crown plateau over the harbor and its tallest
  tower;
- Cragmouth's golden model and blockout plan hashes, with grid and drape parts and retaining
  walls in the plan.
- with M10: the held vertices bounding the fit (`test_held_vertices_bound_the_fit`), the hilly
  test city's ids from what and where (no build counter, every reference and water level
  naming an entity), and a regeneration of its Old Quarter holding every road outside it,
  grade line included, with every check passing.

## Blockout

- **Ground:** a 4 m heightfield per tile (new part kind `grid`, built in Blender from a
  z list), the water bed 2 m under the level.
- **Draped parts:** flats (junctions, parks, plazas, lawns) are draped on the ground, cell by
  cell where they are large (new part kind `drape`: polygons with a z per vertex).
- **Roads** lie on their grade lines; **water** at its level.
- **Buildings** stand on their bases, over stepped plinths (8 m cells, each from the lowest
  ground at its corners).
- **Retaining walls** are slabs from under the lower ground to a parapet over the upper.
- **Everything else** stands on the finished ground at its point.
- **Cameras:** the district boxes run from the lowest ground to the highest, and the street
  views stand on the ground.
- `render_hillside.jpg` (8K) looks up the Old Quarter hill from the river:
  `citygen rerender <dir> --eye -760 170 80 --target -1200 900 62 --lens 26 --name hillside`.

## Open items

- **Terrain-aware layout:**
  - M2 lays its street patterns without the ground, so steep districts get straight grids
    up the slope (streets up to 12%, many walls) where a hill town would wind along the
    contours.
  - Lots too steep to build become greens instead of being shaped into terraces.
- **Streets on the steepest ground:** a street that M2 lays straight across an escarpment
  can cut or fill past the limits (Cragmouth seeds 11 and 1999). Stairs (a pedestrian street)
  or a winding route would carry it.
- **Junction cuts and fills:** the grade fit spreads a misfit evenly, so where an unclimbable
  step meets a junction both the junction and its roads take part of it. The fill and cut
  limits (18 and 20 m) are large for a city; a fit that weights junctions, or a layout that
  keeps junctions off steep ground, would bring them down.
- **Viaducts and terrain:**
  - M7 viaducts on hills lock their grade lines.
  - Terrain viaducts only stand where no junction lies on them.
  - A street under a terrain viaduct is tied to the viaduct at their crossing only when M2
    made a node there.
- **Retaining walls** are traced on the 4 m grid, so they run in steps; merging them into
  straight walls along the corridors is left.
- **Transit:** only the metro is graded on the ground. Elevated rail, monorail, maglev and
  sky tubes keep their M5 profiles over the finished ground, so on hills their grades follow
  the ground's. Cragmouth has only a metro.
- **Skybridges** join buildings on a common floor grid; a building far down the slope from its
  partner may sit up to half a floor off its entrance ground.
- **Metro stair foot:** an M8c metro stair stepped 12 m along its concourse can end between
  two concourse vertices and miss the walkway graph. Terrain cities insert the vertex. Flat
  cities keep their M8c bytes, and so the bug, until a milestone may change their goldens.
- **District regeneration on Cragmouth (M10's frame, found here, not terrain):** five of
  its six districts fail checks after `--district`, as they do on the same spec without
  terrain: a new street can split a held road at a new point, a held node can come back
  doubled 1 cm apart, a neighbor laid later can come back with its grid at other offsets
  (the splice then keeps both grids), and M3's lot draws by build-order index reseed a
  neighbor whose seam block splits differently. Fixing the last moves every city's
  buildings (new goldens), so it belongs to its own change. Fixed after M15, all but the
  lot draws: every district regenerates with every check passing
  ([`stage1_fixes`](../stage1_fixes/)).
- **Rivers** fall in one profile along their centerline. There are no weirs or rapids, and no
  lakes at their own level in the spec yet.
