# M16: water and ground detail

Stage 1's data for stage 2's real water (AG12) and ground cover and grass (AG13). Code:
`citygen/water.py` (beds, flow, exposure, banks), `citygen/cover.py` (ground cover),
`citygen/water_checks.py`, `citygen/preview_water.py`, `citygen/preview_ground.py`; the stage
runs last in a build (`build.water_ground`, after the gameplay layer). Design notes: `CLAUDE.md`
(M16 paragraph) and the PR.

## What each sample carries

Builds on the Windows PC (`CITYGEN_WORKERS=6`), every check passing on the tries each took
before M16 (on M17's code: M17's own builds). Every model is its M17 model byte for byte apart from M16's fields (`depth_m`,
`bed`, `flow`, the sea's `exposure`) and its two collections (`banks`, `ground_cover`).

| City | Tries (before, after) | Checks | Water bodies | Banks | Ground cover pieces | Desire lines |
|---|---|---|---|---|---|---|
| Vesper Bay | 1, 1 | 93 | 10 | 79 | 4486 | 641 |
| Delta Megacity | 1, 1 | 93 | 13 | 139 | 4779 | 219 |
| Saltreach Free Port | 1, 1 | 93 | 12 | 62 | 2626 | 176 |
| Nexus City | 1, 1 | 93 | 18 | 92 | 5464 | 537 |
| Greyhook | 2, 2 | 93 | 6 | 63 | 2574 | 475 |
| Vesper Bay Pinned | 2, 2 | 93 | 15 | 87 | 4985 | 630 |
| Vesper Bay Stacks | 2, 2 | 93 | 15 | 83 | 4998 | 689 |
| Vesper Bay Decks | 6, 6 | 98 | 10 | 81 | 4491 | 670 |
| Cragmouth | 2, 2 | 93 | 8 | 36 | 5381 | 278 |

Banks by kind (count, km):

| City | Quay | Canal wall | Road embankment | Natural bank | Beach | Marsh edge | Riprap |
|---|---|---|---|---|---|---|---|
| Vesper Bay | 6, 4.54 | 16, 1.63 | 16, 0.70 | 25, 8.33 |  | 6, 5.86 | 10, 5.49 |
| Delta Megacity | 15, 8.75 | 32, 3.20 | 26, 1.28 | 47, 12.19 | 1, 0.14 | 3, 2.94 | 15, 4.42 |
| Saltreach Free Port | 17, 7.68 | 9, 1.20 | 8, 0.31 | 23, 12.28 | 2, 3.19 |  | 3, 3.32 |
| Nexus City | 8, 7.43 | 18, 1.98 | 14, 0.48 | 38, 14.45 |  | 6, 2.78 | 8, 2.60 |
| Greyhook | 5, 3.06 | 9, 0.11 | 4, 0.16 | 24, 14.50 | 2, 1.95 |  | 19, 5.80 |
| Vesper Bay Pinned | 11, 8.17 | 4, 0.14 | 17, 1.00 | 22, 7.54 | 10, 2.26 | 8, 2.73 | 15, 6.37 |
| Vesper Bay Stacks | 11, 8.17 | 2, 0.16 | 18, 0.82 | 18, 7.40 | 10, 2.26 | 8, 2.73 | 16, 6.67 |
| Vesper Bay Decks | 6, 4.54 | 10, 1.04 | 10, 0.48 | 32, 8.60 |  | 6, 5.86 | 17, 6.02 |
| Cragmouth | 6, 5.05 | 8, 0.54 | 2, 0.08 | 15, 5.10 |  |  | 5, 1.92 |

Ground cover by kind (km2):

| City | Mown lawn | Park lawn | Meadow | Marsh | Wasteland | Bare dirt | Gravel | Sand | Planted bed | Overgrown paving | Paving |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Vesper Bay | 0.548 | 0.360 | 0.160 | 0.661 | 0.122 | 0.027 | 0.643 |  | 0.009 | 0.157 | 0.672 |
| Delta Megacity | 0.265 | 0.197 | 0.050 | 0.497 | 0.030 | 0.027 | 0.686 |  | 0.030 | 0.006 | 0.920 |
| Saltreach Free Port | 0.369 | 0.125 | 2.380 | 0.000 | 0.005 | 0.015 | 0.282 | 0.115 | 0.024 | 0.004 | 0.480 |
| Nexus City | 0.590 | 0.334 | 0.100 | 0.217 | 0.038 | 0.033 | 0.750 |  | 0.009 | 0.007 | 1.054 |
| Greyhook | 0.453 | 0.448 | 0.021 |  | 0.036 | 0.008 | 0.540 |  |  | 0.186 | 0.505 |
| Vesper Bay Pinned | 0.675 | 0.398 | 0.073 | 0.209 | 0.055 | 0.033 | 0.708 |  | 0.021 | 0.210 | 1.028 |
| Vesper Bay Stacks | 0.617 | 0.455 | 0.097 | 0.209 | 0.074 | 0.032 | 0.746 |  | 0.031 | 0.229 | 1.010 |
| Vesper Bay Decks | 0.446 | 0.369 | 0.158 | 0.661 | 0.145 | 0.031 | 0.600 |  | 0.017 | 0.150 | 0.661 |
| Cragmouth | 0.428 | 0.161 | 0.749 |  | 0.000 | 0.038 | 0.327 |  | 0.005 | 0.079 | 0.533 |

Saltreach's meadow is the wild land of its islands outside every district.

## District regeneration

`regenerated/vesper_bay_old_town/`: `citygen build cities/vesper_bay/city_spec.json OUT
--district "Old Town"` on the Vesper Bay build: its second seed (the first fails M17's
`road_overlaps`, on main as here; every M16 check, `regen_locality` with them, passes on
it), 366 s on the shared PC, all 94 checks passing. The 22 bank ids that changed, went or
are new are all in Old Town; 3816 ground cover pieces changed, went or are new in Old Town,
none on its seam, and 3 far from it (their wear follows crowd densities the splice changed
there, which `regen_locality` allows: an M16 row may change outside the district only
within 60 m of a changed input). No water body's depth, bed, flow or exposure changed.

## Files

Each city folder: `preview_water.png` (beds by depth, the sea's exposure, banks by kind, flow,
a 600 m window with the banks drawn to their waterline, a river's cross-section),
`preview_ground.png` (the cover by kind with desire lines, a 500 m window, shade and
maintenance maps), `report.txt`, `report.json`, `render_iso_city.jpg` (8K). Vesper Bay also
`render_drained.jpg` (8K: the harbor with the water hidden, its basins, the sea's bed by depth,
the banks, the marsh and its edge). `wip/`: the first previews, on the base builds.
