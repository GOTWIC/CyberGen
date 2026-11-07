# M22: the pavement map

From run-through 2's road recheck: AG7 drew each road, junction, sidewalk and median as a
piece of its own, so pieces overlapped, left gaps and stepped where they met. M22 makes one
exact map of every road surface in stage 1 (design in `docs/assetgen_scope.md` 14.18), which
AG17 will draw from.

## What the model holds

- `pavement`: the faces of the map, each owned by a road segment (its carriageway, median,
  curbs, sidewalks or walk bands; a bend face where a band would fold) or a junction (its
  carriageway, corner pads, a cul-de-sac's bulb), on a layer: the ground's roads g0, raised
  networks g1 to g3 by M7's level, a deck d1, tunnels u1.
- `pavement_net`: the vertices (on the 1 mm grid, one height each over the finished ground)
  and the edges between faces (port, band, curb, outer, seam), each stored once.
- Junctions: one cut per road end, kept on the junction (`attrs.cuts`); clusters, where a
  road between two junctions is too short for a face of its own (`attrs.nodes`, `inner`); the
  junction's `polygon` is its carriageway face's outline, `edge_z` the map's heights there.

`preview_pavement.png` (each city's folder): the map by kind, the junctions kept as M18 left
them outlined, and four windows at street scale (the largest cluster, a cul-de-sac's bulb,
the largest bend face, the highest junction by height).

## Junctions one surface cannot carry

After M18's levelling, every junction's ports should lie within its grade of each other and
its faces be drawn within it (invariant 5). A fit of node, port and road heights on the
whole network levels most of those that do not. A junction no height fits without moving a
bridge span, a fixed road or M7's 3 m limit for a local junction, or that the map draws
steeper than the fit foresaw, is kept as M18 left it, tagged `attrs.unbuildable` with what
holds it, and noted by the checks (not failed).

| City | Checks (layout tries) | Over invariant 5 after M18 (ports + faces) | Levelled further | Kept as M18 left them | Map |
|---|---|---|---|---|---|
| Delta Megacity | all 106 pass (1) | 11 + 4 | 6 | 13: 5 M7's 3 m limit beside a bridge span, 4 drawn steep, 3 bridge spans or a fixed road, 1 its roads' grade | 18,208 faces, 137 clusters, 74 bends |
| Vesper Bay | all 106 pass (1) | 14 + 2 | 12 | 6: 4 bridge spans, 2 drawn steep | 19,645 faces, 124 clusters, 81 bends |
| Saltreach Free Port | all 106 pass (1) | 13 | 6 | 7: 3 bridge spans, 3 M7's limit beside a bridge span, 1 its roads' grade | 10,391 faces, 112 clusters, 44 bends |
| Nexus City | all 106 pass (1) | 12 + 1 | 8 | 7: 3 its roads' grade, 2 drawn steep, 1 bridge span, 1 M7's limit beside a bridge span | 20,838 faces, 172 clusters, 80 bends |
| Greyhook | all 106 pass (2) | 4 | 4 | 0 | 9,971 faces, 57 clusters, 25 bends |
| Vesper Bay Pinned | all 106 pass (2) | 16 + 3 | 16 | 5: 2 drawn steep, 2 bridge spans, 1 M7's limit beside a bridge span | 21,996 faces, 135 clusters, 80 bends |
| Vesper Bay Stacks | 105 of 106 (9): `transit_curves` | 15 + 1 | 14 | 1: a bridge span | 22,305 faces, 155 clusters, 80 bends |
| Vesper Bay Decks | all 111 pass (1) | 14 + 3 | 12 | 7: 4 bridge spans, 2 drawn steep, 1 fixed road | 20,400 faces, 127 clusters, 82 bends |
| Cragmouth | all 106 pass (2) | 6 | 6 | 0, and 248 hillside junctions drawn steeper than their class grade | 22,625 faces, 145 clusters, 71 bends |

Delta's two junctions from the run-through: `jn.e217s328` and `jn.e170s444` are one cluster
now (the twin ramp between them, a highway and an avenue laid 11 m apart, is its inner
roads); its ports fit, but where the avenue leaves the top beside the ramp at another grade
the map draws a 90% gore, so it is kept and noted. Beside it `jn.e8s46` lies between two
bridge decks whose locked spans are 1.27 m apart in height: no surface joins them without
moving a bridge. Cragmouth's hillside junctions are on ground steeper than 4%, where a
primary road keeps its grade through its junctions (M18).

Delta Megacity is the review city: `delta_megacity/render_jn_e170s444.jpg` (the twin-ramp
cluster that holds `jn.e217s328`, its steep gore beside the ramp) and `render_jn_e8s46.jpg`
(the junction between two bridge decks) show them in the blockout up close.

## Open

- Vesper Bay Stacks fails `transit_curves` on every layout: its Crown Line sky tube leaves its
  first station, in a traced Corporate Core tower, on a 25 m hook (M19's routing at a portal
  station; the same line passes in Vesper Bay Pinned).
- The junctions kept as M18 left them are not repaired at layout (moving a junction off a
  bridge head in M1b, or passing its roads at two levels).
- AG7 still draws today's junction pieces from `polygon` and `edge_z`; a cluster's corner
  pads between legs at two of its nodes are left out until AG17 draws the map's own.

Sample builds: the five samples, the pinned, stack and deck demos and Cragmouth, each with
`report.txt` and `preview_pavement.png` (the five samples also `report.json` and the
gameplay and transit previews the tests compare); 8K whole-city renders
(`render_iso_city.jpg`). Work in progress: `wip/`.
