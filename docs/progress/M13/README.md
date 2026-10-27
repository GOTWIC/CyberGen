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
- **Five new checks**, 84 in all.

The hilly sample is **Cragmouth** (`cities/cragmouth`). A spec without `terrain` builds exactly
the city it built before: the five samples and the pinned demo are byte-identical to M11 on M9.

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

## Checks (80 to 84)

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

SWEEP_AND_BUILDS

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
- **Rivers** fall in one profile along their centerline. There are no weirs or rapids, and no
  lakes at their own level in the spec yet.
