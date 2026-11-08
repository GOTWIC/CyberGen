# AG17: road surfaces by construction

From run-through 2's road recheck: AG7's road, junction and sidewalk pieces each found their
own edges, so they overlapped, left gaps and stepped where they met (#105). Stage 1's M22
keeps one exact map of every road surface in the model; AG17 draws the street pieces from it
(design: `docs/assetgen_scope.md` 14.18), so two pieces meet on the same vertices at the
same heights by construction. The full record is in `docs/assetgen_milestones.md`, AG17.

## What the street pieces draw now

- **Faces of the map**, on their stored vertices and heights: a road piece its carriageway,
  bends, walking surface and median; a sidewalk piece its side's curb band, furniture zone
  and clear path; a junction piece its carriageway, corner pads and a cul-de-sac's bulb (a
  cluster's whole surface). Piece ids and keys are as before, so the Unreal exporter needs
  no change.
- **Curbs** as walls between faces at two heights (the same stored polyline at both),
  curb ramps beside crosswalks and driveways, medians as raised islands cut through at
  their crosswalks.
- **Decks**: a raised road's girder only between its cuts; a raised junction on a slab of
  its own, no girder under it.
- **Barriers** along the road between its cuts, ending on its port lines, a junction's
  corner parapets and guard walls along its own edge from one leg's port to the next.
- **Marks** on the faces as drawn.

## Checks

`street_watertight` (new): every segment of every edge two faces share is drawn by both
faces' pieces between the same two vertices, in exactly two triangles (the two faces', or a
face's and its curb's), read back from the packs on integer millimeters. AG14's step check
compares a road's and its junction's pieces exactly at the map's ports.

CITY_TABLE

## Before and after

Delta Megacity, the street pieces among the blockout's buildings (`assetgen streets`, then
`assetgen/blender/streets_preview.py`); before (main after M22) on the left, after on the
right. Full size in `before/` and `after/`.

The twin-ramp cluster `jn.e170s444` (it holds `jn.e217s328` now) from the road: the strips
across the carriageway (barriers and pads from roads inside the cluster) are gone.

<img src="before_after/jn_e170s444_low.jpg" width="900">

And from above.

<img src="before_after/jn_e170s444.jpg" width="900">

A cul-de-sac (`jn.e1743n682`): no wedge where the bulb meets its road.

<img src="before_after/cul_de_sac.jpg" width="900">

A hairpin (`rs.w881n1363`, a bend face): no bulge, one rounded bend.

<img src="before_after/hairpin.jpg" width="900">

A raised junction (`jn.w867s227`, 18 m up) from below: its slab under its faces, no girder
running under it.

<img src="before_after/raised_junction.jpg" width="900">

A corner with its pad and crosswalks (`jn.w563n1125`, one of the junctions M22 keeps as M18
left it): no slivers or strips.

<img src="before_after/corner_pad.jpg" width="900">

## Unreal

`unreal_before/`: M22's Delta imported with full stage 2 by the coordinating session
(`unreal_pday_jn_e170s444_low.jpg`: the strips crossing the carriageway and the concrete
wedge at the gore that AG17 removes). The same check after AG17 is the coordinating
session's to run.

Work in progress: `wip/`.
