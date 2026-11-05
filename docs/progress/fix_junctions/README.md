# Junction surfaces, corners and leftovers (issues #82, #89)

A fix between milestones, on #95's barriers (#103). Delta's raised five-leg junction
`jn.e217s328` drew sidewalk and slab strips across its carriageway, and AG14's fit checks
missed it (#82). AG14 also left trash cans at raised corners, Cragmouth's quay railings and
slope shrubs off their surfaces, and steps of 0.10 to 0.43 m where roads meet junctions
(#89). Code: `assetgen/streets/walks.py` (AG7's junctions and sidewalks),
`assetgen/streets/roads.py` (medians), `assetgen/fit/strips.py` (AG14's new check),
`assetgen/fit/build.py`, `assetgen/props/gather.py` (AG8). Log:
`docs/assetgen_milestones.md`, "Fix: junction surfaces, corners and leftovers".

## What was wrong at `jn.e217s328`

A highway and an avenue run side by side for 125 m between `jn.e217s328` (8.9 m up) and
`jn.e170s444` (0.8 m), up a ramp. M17 joins the pavement two roads share to the junctions
it runs out of, so each junction's outline held the whole ramp (they overlap by
2,851 m2), and:

- each drew the ramp at its own heights (M18's curb runs evenly round each outline from one
  leg's cut to the next), 1 to 2 m apart where they crossed;
- each drew corner pads in sectors 125 m long, straight on from the node past the curving
  avenue, so pads lay over the other junction's carriageway;
- the slab under a raised junction was a flat prism at its node's height: its walls stood
  through the lower half of the ramp (the light strips in the run-through's shot);
- the avenue's sidewalks (M2 lays them along the whole road where its two cuts overlap)
  lay on the ramp.

| Main | This fix |
|---|---|
| ![](delta_e217_3d_before.png) | ![](delta_e217_3d_after.png) |
| ![](delta_e217_plan_before.png) | ![](delta_e217_plan_after.png) |

Plans and views drawn from the pieces AG7 makes (gray carriageway, orange corner pads,
yellow sidewalks, magenta the connector lanes, blue the model's outlines).

The same causes, smaller, ran through every sample: sidewalks M2 laid into M17's long
junctions, cul-de-sac bulbs and skewed cuts; pads reaching a neighboring junction or a road;
connector lanes M2 laid over the corner pads past the curb (`jn.e179n1530`).

| | Main | This fix |
|---|---|---|
| Connector lanes over the corners (`jn.e179n1530`): the lanes' runs are paved, the pads keep off them | ![](delta_e179_plan_before.png) | ![](delta_e179_plan_after.png) |
| A raised corner of `jn.e217s328`, 8.3 m up: on main no pad was drawn there and its trash can (`d06.prop.trash_can.e248s333`, the red cross) stood over nothing; now the corner's pad follows the bending leg and holds it | ![](delta_raised_corner_plan_before.png) | ![](delta_raised_corner_plan_after.png) |
| A cul-de-sac: a sidewalk round its bulb, the legs' sidewalks off its carriageway | ![](delta_cul_de_sac_plan_before.png) | ![](delta_cul_de_sac_plan_after.png) |
| A sidewalk's end beside two junctions: drawn off their carriageways on the rest of its width | ![](delta_sidewalk_end_plan_before.png) | ![](delta_sidewalk_end_plan_after.png) |

## Numbers

Main's street packs measured with the new checks, against this fix's packs (`assetgen
streets`, `props`, `ground`, `fit` on the same city models; every check of those stages
passes on every city).

| City | Roads with a step over 2 cm onto their junction (largest) | Sidewalks, corners and medians over a junction's or a road's carriageway | Things off their surface (AG14, this fix) |
|---|---|---|---|
| Delta Megacity | 1 (0.022 m) to 0 (0.002 m) | 415 and 8 to 0 | 6 (5 trash cans, a street light) to 1 (the street light, 3.9 cm, reported) |
| Vesper Bay | 2 (0.102 m) to 0 (0.006 m) | 416 and 11 to 0 | 0 |
| Vesper Bay Decks | 2 (0.102 m) to 0 (0.006 m) | 413 and 3 to 0 | 0 |
| Vesper Bay Pinned | 2 (0.430 m, `jn.e368s514`) to 0 (0.004 m) | 432 and 5 to 0 | 0 |
| Vesper Bay Stacks | 2 (0.349 m, `jn.e559s304`) to 0 (0.003 m) | 408 and 6 to 0 | 1 (a traffic signal at a highway junction 22.5 m up, over nothing on main too, reported) |
| Cragmouth | 8 (0.125 m) to 0 (0.015 m) | 345 and 2 to 0 | 533 (313 quay railings, 214 shrubs, 4 trash cans, a signal, a conifer) to 0 |

Things off their surface on main were measured on Delta and Cragmouth only. Delta's
sidewalks left open beside their junctions by the clip (before the fill): 459 m2 over 522
sidewalks; with it, 9.7 m2 over 95 in slivers under 10 cm wide or 0.05 m2. Delta's five
trash cans at raised corners with no pad on main all stand on a pad now; AG8 would leave
out a standing prop in a raised junction's corner or legs with nothing under it (one on
Vesper Bay Pinned, between two twin legs).

## Renders

Delta Megacity, `assetgen materials preview` with the same four cameras on main's packs and
this fix's (3840 px).

| Main | This fix |
|---|---|
| ![](delta_e217_ramp_before.jpg) | ![](delta_e217_ramp_after.jpg) |
| ![](delta_e179_corners_before.jpg) | ![](delta_e179_corners_after.jpg) |
| ![](delta_raised_corner_before.jpg) | ![](delta_raised_corner_after.jpg) |
| ![](delta_cul_de_sac_before.jpg) | ![](delta_cul_de_sac_after.jpg) |

1. The ramp between `jn.e170s444` and `jn.e217s328`, from the south: on main the slab's
   walls and both junctions' pads covered it; now it is one carriageway with its
   crosswalks and the avenue's sidewalk beside it. At the top, where `jn.e217s328`'s five
   legs meet between 0.8 and 12.3 m, its corner pads and slab edges still stand at odd
   angles: the junction's surface is M18's curb run evenly round its outline, which no
   surface between legs that far apart can follow (left for the road recheck).
2. `jn.e179n1530`: the connector lanes' runs are paved and the corner pads keep off them.
3. A raised corner 12.5 m up: on main its pad stopped short, the trash can
   (`d04.prop.trash_can.w1n1381`, the wire basket) stood at its edge over nothing and #95's
   parapet zigzagged round it; now the pad reaches the crosswalk's end, the basket stands on
   it and the parapet runs straight. The short concrete block in front of the crosswalk on
   main is not drawn now.
4. A cul-de-sac: its sidewalk round the bulb, the legs' sidewalks no longer over it.

## Left open

Filed as #105; none fails a check.

- A cul-de-sac's road ends square on its cut and its bulb's outline starts on the curve, so a
  wedge of carriageway between them is drawn by neither (also on main; Delta's
  `rs.e898n497` at `jn.e928n528`, in the cul-de-sac plans above).
- AG7's mitre bulge at a sharp alley hairpin (Vesper Bay Decks' `rs.e1681s1093`, about
  2.5 m past the edge at a turn of 110 degrees): the mitre is in `streets/path.py`, whose
  bytes are also in AG12's and AG13's code hashes.
- Sidewalk slivers under 10 cm wide or 0.05 m2 (above).
- Stacks' traffic signal 22.5 m up at `jn.w338s983` and Delta's street light 3.9 cm off a
  sloped sidewalk (both on main too, reported).
- AG14's grounded rule takes a thing as resting when one of its five feet is (the smallest
  gap where fewer than three are within 2 cm).
- The top of `jn.e217s328` (render 1): a junction whose legs meet it between 0.8 and
  12.3 m keeps M18's curb-run surface, and its pads and slab edges follow it.
- Left for the road recheck, as asked: M17's long junctions and the deck girders under
  junctions.
