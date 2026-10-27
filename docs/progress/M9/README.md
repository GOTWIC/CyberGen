# M9: tunnels

M9 adds tunnels to citygen (`citygen/tunnels.py`, checks in `citygen/tunnel_checks.py`, preview
`citygen/preview_tunnels.py`):

- **Road tunnels:** immersed tubes under rivers, channels and the bay; cut-and-cover tunnels
  under districts.
- **Tunnel parts:** portals, walled open approaches and ventilation buildings.
- **Metro:** tunnels between the station boxes, the track lowered under what it must clear.
- **Pedestrian underpasses** under the at-grade highways.
- **Four new checks** (70 in all), the tunnels in the Blender blockout, and a cutaway render.

Road tunnels are level -1 of the road network, the negative counterpart of M7's viaducts.

M11 (the gameplay layer, PR #24) was merged into this branch before it landed, so the builds
here are M11 on M9: 79 checks (66 to M8c, 4 M9, 9 M11), and every city folder has
`preview_gameplay.png`. The gameplay layer runs on the tunnel cities unchanged: cars reach
places through the tunnels and over the lids on the lane graph, and people on foot through
the pedestrian underpasses on the walkway graph.

## Art direction: which samples have tunnels

| City | Spec change | What it builds |
|---|---|---|
| Nexus City | `highways.tunnels.under: ["Midtown"]` | **Midtown Tunnel**, a cut-and-cover tunnel on the ring highway. It is 496 m long, 190 m of it covered; the road runs 7.8 m down. A street crosses over the lid, and the Blue Line metro is lowered to pass under it. |
| Greyhook (Peninsula City) | `highways.tunnels.water: "prefer"` | **Neckwater Tube**, an immersed tube that replaces the spine highway's river bridge. It is 756 m long and 434 m covered, with 82 m under water. The road runs 15.8 m down, under the 7 m river bed. There is a ventilation building at each shore portal, and two avenues and a street pass over it. |

The first plan was to give Vesper Bay cut-and-cover tunnels under Corporate Core and The
Stacks. Both fit, but the tunnel on the ring takes the stem of the city's trumpet. On the road
networks that keep the tunnels, Vesper Bay then lost M8d's flyover or failed a check. Vesper Bay
therefore keeps its M8c spec and its trumpet (crest 16.6 m), and the cut-and-cover sample moved
to Nexus City.

Each of the four other cities builds no road tunnel. They still change, though:

- the metro is lowered under the tower foundations (Vesper Bay, Delta Megacity, the pinned demo);
- pedestrian underpasses (`highways.tunnels.underpasses`, default 0.5) take a sidewalk under
  each at-grade highway that has frontage streets on both sides.

## Builds

All six cities pass all 79 checks. Each `city_model.json` is byte-identical on the M4 Mac
(arm64) and on x86_64 Linux (docker `citygen-x86`, `linux/amd64`, the worktree mounted
read-only, `CITYGEN_WORKERS=3`):

| City | Full-city tries (M8c, M9) | sha256 of `city_model.json` (both machines) |
|---|---|---|
| archipelago_free_port | 1, 1 | `7ada11aae912929ad7bd853f431ab46694227844f4169ea023c464eac52b0ebc` |
| delta_megacity | 1, 1 | `da19195acc4effd30ccdb5e1163a45c0fd1f4b62f60c133610d34a89e9be6923` |
| nexus_city | 3, 1 | `c413d2db841d77bda8bb92daf2886858758f704a1cb14fdcd86de4cf4b43eb8c` |
| peninsula_city | 1, 1 | `85d49fc8492029aeddd2f6b842abd968cd84e00919b524706ac7cea6d627894c` |
| vesper_bay | 1, 1 | `c9be7637f735a2a407be0379d61dfd52cdc016151fa043a5fb8082e300ec36ef` |
| vesper_bay_pinned | 2, 2 | `31f8e633e604c651b50759625be1547e26a3dab6704018f0a85a2533dfad8686` |

Nexus City now builds on its first try: with the ring sunk under Midtown, its viaducts and
interchanges are chosen anew (a diamond and a partial cloverleaf), and that layout passes.

Each city folder has every generator preview, `preview_tunnels.png`, `preview_gameplay.png`,
the build report, the stage trace, the blockout report, `render_top.jpg`, the 8K
`render_iso_city.jpg` and, for Nexus City and Greyhook, the 8K `render_cutaway.jpg`. The
blockout plans (sha256 in `tests/data/golden_hashes.json`) are the same with and without M11,
which adds no blockout geometry, so the renders and blockout reports are those of M9 alone.

## How a road tunnel is laid

**Corridor.** A tunnel lies on a corridor: segments of one class joined straight on through
the nodes, within 35 degrees (`tunnels.Net.through`). Each node on the corridor is one of:

- **plain:** nothing else meets there;
- **cross:** one road crosses straight over at 35 degrees or more, and can pass over the tunnel;
- **tee:** one avenue meets the corridor, and ends beside the lid;
- **block:** a highway, a fork, an exit or a turn.

**Profile.** The profile along the corridor is a graded envelope of depth needs:

$$z(s) = -\max\Big(0,\ \max_i \big(d_i - g\,\mathrm{dist}(s, I_i)\big)\Big)$$

The grade is $g = 5\%$, or $5.8\%$ where that does not fit, under the class maximum of 6%.
M7's 40 m vertical curves are then applied. A need is an interval $I_i$ of the corridor with a
road depth $d_i$:

- **Under water:** the bed (canal 3 m, river 7 m, sea 12 m), 1.5 m of backfill, the tube roof
  (1.5 m) and 5.5 m of clear height, kept to 10 m past each bank.
- **Under a node inside the window:** 5.5 m clear, the roof and 1 m of cover. The node goes:
  a crossing road's two legs join into one segment that passes over (`attrs.over_tunnel_at`),
  and a tee avenue ends 8 m off the box (`ends_at_tunnel`).
- **Cut-and-cover:** the covered stretch inside the district, at that same depth.

**Fit.** The fit adds the needs of every water body and node the envelope reaches, until
nothing new comes in. It fails on any of:

- a blocking node within 20 m of the sunk stretch, or a corridor end;
- an open approach over water, or under another road;
- a bridge approach that would reach a descent: `Ctx.lifts` runs `solve_grades`' max-plus
  envelope without the tube's own bridges;
- a road network the window would cut apart.

**Network.** The window's segments join into one tunnel segment (`tunnel`, `tunnel_ids`,
level -1), and the network is renumbered the way M1b numbers it. Its profile goes through
`_envelope`, which adds any bridge approach that reaches the tunnel's end nodes (the private
`_tunnel_prof`). M7 leaves tunnel segments out of its viaducts and interchanges.

**Choosing where.** Immersed tubes replace bridges according to `highways.tunnels.water`:

- **auto** (the default): a sea crossing over 600 m of water;
- **prefer:** every river and sea crossing where a tube fits;
- **never:** bridges only.

A named crossing stays a bridge unless its `tunnel` is true. Cut-and-cover tunnels take the
longest covered stretch, between the interchanges, of a highway through each district in
`highways.tunnels.under`. Tunnels are on highways only for now.

**M2.**

- No local junction within 20 m of a sunk stretch.
- A tunnel road's right of way covers its box walls plus 2 m (`TUNNEL_SIDE_M`), so no lot,
  building or street stands on them.
- Streets cross covered lids from one frontage street to the other (role `over_tunnel`,
  M7's underpass streets turned over).

**After transit (`tunnels.build`):**

- **Parts:** the open approaches (structure `trench`) and the portals.
- **Ventilation buildings:** on the lid, 40 m inside each portal of a tunnel covered for more
  than 300 m, and every 800 m along it, at least 12 m from any road over the lid.
- **Metro:** the track is lowered at 3% (4% maximum) under the water bed, the road tunnels,
  the building foundations (4 to 18 m deep by height, `foundation_m`) and earlier metro lines.
  Its tunnels are cut between the station boxes.
- **Pedestrian underpasses:** a passage 4 m down, with stairs 6.5 m long down from a sidewalk
  on each side. The sidewalk walkways are split there, so the walkway graph runs through.

Transit columns keep off road tunnel boxes.

## Checks (67 to 70; 79 with M11)

| Check | What it asks |
|---|---|
| `tunnel_grades` | road tunnels and their open approaches at most 6%, the metro at most 4%, underpasses level |
| `tunnel_cover` | at least 1 m of ground over the roof beyond 40 m from a portal, and 1.5 m under the water bed; 0.5 m over an underpass |
| `tunnel_portals` | two portals on dry land, 5.5 m clear inside, open approaches at most 6%, no road node within 20 m of their top, no road (below a deck high over the trench), building or structure on them |
| `tunnel_clash` | no tunnel within 1 m in height, where they overlap in plan, of another tunnel, a metro station box, a building's foundations and basements, or a column footing |

`bridge_clearance` no longer counts a tunnel road under water as a road over water without a
bridge. `junction_placement` also forbids local junctions on sunk stretches, and
`curve_radius` treats `underpass_at` and `over_tunnel_at` points like M7's overpasses.

## Blockout

- **Road tunnels:** open boxes made of a floor, two walls (one closed mesh each, a new `mesh`
  part kind), a roof over the covered stretch and a lintel over each portal. Their roads are
  objects of their own (`tunnel_road`), and the ground slab is open over the approaches.
- **Metro tunnels and underpasses:** solid boxes.
- **Ventilation buildings:** prisms.
- **`render_cutaway.jpg`** (view `cutaway`, also for `citygen rerender`): the city cut along
  the longest road tunnel's chord. The camera's side is taken away down to a pit floor, an
  earth block lies under the ground, and the tunnels' inner volumes are opened in it. The
  view is from over the first open approach, down the ramp and through the portal, with a
  low fill light.

## Sweep

`citygen sweep --suite m8a --workers 3` on M11 on M9 (`sweep.md`, `sweep.json`): **58 of 68
builds pass**, as on M8c, on M9 alone and on M11 alone. Against M11's sweep, only retry counts
differ (nexus_city s1207 2 retries to 0, test_small s404 and test_pinned s1999 0 to 1 each). The ten failures are the same builds with the same failing checks as in
`docs/progress/M8c/sweep.json`, so none is newly broken:

| Build | Failing checks (M8c and M9) |
|---|---|
| archipelago_free_port s1999 | road_graph, districts_served, open_space_share |
| nexus_city s11 | placement, curve_radius |
| vesper_bay s3141 | open_space_share |
| vesper_bay_pinned s11 | bridge_clearance, curve_radius |
| vesper_bay_pinned s1999 | curve_radius |
| vesper_bay_pinned s5077 | placement, level_continuity |
| vesper_bay_pinned s8128 | placement |
| test_minimal s42 | placement |
| test_minimal s404 | road_graph, walkway_graph |
| test_minimal s3141 | placement, road_graph, lot_block_sizes, open_space_share, megasite_access |

No tunnel check fails in the sweep. An earlier sweep run found Nexus City s11 putting a
frontage street and a building on a tunnel's box walls (the box is wider than the carriageway);
that is why a tunnel road's right of way covers the walls (`TUNNEL_SIDE_M`).

The full pytest passes on M11 on M9 (418 passed, 2 skipped; 395 and 2 on M9 alone), with the
tunnel tests in `tests/test_tunnels.py`.

## Open items

- **Avenues:** tunnels are on highways only. An avenue in a tube would keep its sidewalks,
  parking and crosswalks up at the ground; that needs M2 to drop them on sunk stretches.
- **Tubes on the samples' crossings:** most crossings get no tube. A bridge's road typically
  meets a T junction or a highway node 40 to 80 m from the bank, and a tube needs 270 to
  400 m of straight approach. A tube for those crossings needs M1b to route the approach
  with room (a straight run on, the waterfront road passing over).
- **Cut-and-cover length:** the cut-and-cover tunnels are short. A tunnel cannot pass under
  a highway node or a fork, so the covered stretch lies between two interchanges. Longer
  tunnels would need interchanges underground, or ramps down into the tunnel.
- **Plazas over lids:** the lid of a cut-and-cover tunnel stays inside the road's right of
  way. No plaza or park is laid over it, and no streets join across it other than from one
  frontage street to the other.
- **Cutaway render:** the sections of the ground slab show sawtooth shading where the exact
  boolean cuts the slab. The view is fixed on the first portal of the longest tunnel.
- **Water depth:** depth is one value per water class; there is no bathymetry.
