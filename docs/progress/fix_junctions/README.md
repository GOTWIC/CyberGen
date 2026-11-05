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

NUMBERS_TABLE

## Renders

RENDERS

## Left open

OPEN
