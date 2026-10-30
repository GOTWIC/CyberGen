# M16: water and ground detail

Stage 1's data for stage 2's real water (AG12) and ground cover and grass (AG13). Code:
`citygen/water.py` (beds, flow, exposure, banks), `citygen/cover.py` (ground cover),
`citygen/water_checks.py`, `citygen/preview_water.py`, `citygen/preview_ground.py`; the stage
runs last in a build (`build.water_ground`, after the gameplay layer). Design notes: `CLAUDE.md`
(M16 paragraph) and the PR.

## What each sample carries

Builds on the Windows PC (`CITYGEN_WORKERS=6`), every check passing on the tries each took
before M16. Every model is its M15 model byte for byte apart from M16's fields (`depth_m`,
`bed`, `flow`, the sea's `exposure`) and its two collections (`banks`, `ground_cover`).

| City | Tries (before, after) | Checks | Water bodies | Banks | Ground cover pieces | Desire lines |
|---|---|---|---|---|---|---|
| Vesper Bay | 1, 1 | 89 | 10 | 65 | 4425 | 746 |
| Delta Megacity | 1, 1 | 89 | 13 | 130 | 4624 | 250 |
| Saltreach Free Port | 1, 1 | 89 | 12 | 70 | 2633 | 219 |
| Nexus City | 1, 1 | 89 | 18 | 80 | 5423 | 748 |
| Greyhook | 1, 1 | 89 | 6 | 76 | 2619 | 580 |
| Vesper Bay Pinned | 2, 2 | 89 | 15 | 89 | 4943 | 640 |
| Vesper Bay Stacks | 1, 1 | 89 | 15 | 70 | 4990 | 816 |
| Vesper Bay Decks | 2, 2 | 94 | 10 | 80 | 4467 | 745 |
| Cragmouth | 1, 1 | 89 | 8 | 31 | 5173 | 291 |

Banks by kind (count, km):

| City | Quay | Canal wall | Road embankment | Natural bank | Beach | Marsh edge | Riprap |
|---|---|---|---|---|---|---|---|
| Vesper Bay | 6, 4.54 | 8, 1.10 | 16, 0.70 | 19, 8.70 | | 6, 5.86 | 10, 5.64 |
| Delta Megacity | 15, 8.75 | 27, 3.33 | 26, 1.27 | 45, 12.92 | | 3, 2.94 | 14, 3.71 |
| Saltreach Free Port | 17, 7.68 | 8, 2.57 | 8, 0.31 | 28, 10.55 | 5, 3.53 | | 4, 3.33 |
| Nexus City | 8, 7.43 | 10, 1.70 | 14, 0.48 | 34, 14.73 | | 6, 2.78 | 8, 2.60 |
| Greyhook | 5, 3.06 | 19, 1.07 | 4, 0.16 | 26, 13.12 | 2, 1.95 | | 20, 6.23 |
| Vesper Bay Pinned | 11, 8.17 | 5, 0.48 | 17, 1.00 | 22, 7.10 | 10, 2.26 | 8, 2.73 | 16, 6.47 |
| Vesper Bay Stacks | 11, 8.17 | 2, 0.26 | 18, 0.82 | 13, 9.11 | 10, 2.26 | 8, 2.73 | 8, 4.86 |
| Vesper Bay Decks | 6, 4.54 | 9, 1.31 | 16, 0.70 | 24, 7.82 | | 6, 5.86 | 19, 6.32 |
| Cragmouth | 6, 5.05 | 5, 0.31 | 2, 0.08 | 13, 5.34 | | | 5, 1.92 |

Ground cover by kind (km2):

| City | Mown lawn | Park lawn | Meadow | Marsh | Wasteland | Bare dirt | Gravel | Sand | Planted bed | Overgrown paving | Paving |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Vesper Bay | 0.542 | 0.360 | 0.160 | 0.661 | 0.100 | 0.028 | 0.644 | | 0.008 | 0.154 | 0.647 |
| Delta Megacity | 0.268 | 0.177 | 0.052 | 0.497 | 0.039 | 0.026 | 0.684 | | 0.025 | 0.005 | 0.897 |
| Saltreach Free Port | 0.364 | 0.115 | 2.384 | 0.000 | 0.005 | 0.015 | 0.280 | 0.115 | 0.018 | 0.004 | 0.472 |
| Nexus City | 0.600 | 0.329 | 0.081 | 0.217 | 0.025 | 0.032 | 0.776 | | 0.022 | 0.015 | 0.987 |
| Greyhook | 0.469 | 0.442 | 0.026 | | 0.005 | 0.008 | 0.546 | | | 0.200 | 0.536 |
| Vesper Bay Pinned | 0.653 | 0.395 | 0.084 | 0.209 | 0.059 | 0.034 | 0.645 | | 0.024 | 0.205 | 1.028 |
| Vesper Bay Stacks | 0.596 | 0.453 | 0.104 | 0.209 | 0.106 | 0.033 | 0.698 | | 0.014 | 0.207 | 0.989 |
| Vesper Bay Decks | 0.455 | 0.359 | 0.121 | 0.661 | 0.140 | 0.030 | 0.619 | | 0.017 | 0.155 | 0.674 |
| Cragmouth | 0.383 | 0.177 | 0.734 | 0.000 | 0.000 | 0.036 | 0.338 | | 0.003 | 0.079 | 0.508 |

Saltreach's meadow is the wild land of its islands outside every district.

## District regeneration

`regenerated/vesper_bay_old_town/`: `citygen build cities/vesper_bay/city_spec.json OUT
--district "Old Town"` on the Vesper Bay build, its first seed as before M16 (117 s, all 90
checks passing with `regen_locality`). Of 65 banks, the 10 that changed or are new are all
in Old Town; of the ground cover, 3766 pieces changed or are new in Old Town, none on its
seam, and 3 far from it (their wear follows crowd densities the splice changed there, which
`regen_locality` allows: an M16 row may change outside the district only within 60 m of a
changed input). No water body's depth, bed, flow or exposure changed.

## Files

Each city folder: `preview_water.png` (beds by depth, the sea's exposure, banks by kind, flow,
a 600 m window with the banks drawn to their waterline, a river's cross-section),
`preview_ground.png` (the cover by kind with desire lines, a 500 m window, shade and
maintenance maps), `report.txt`, `report.json`, `render_iso_city.jpg` (8K). Vesper Bay also
`render_drained.jpg` (8K: the harbor with the water hidden, its basins, the sea's bed by depth,
the banks, the marsh and its edge). `wip/`: the first previews, on the base builds.
