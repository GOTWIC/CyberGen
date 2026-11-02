# AG14: fit and finish

The four sample cities built with citygen on main (M20 merged, 9c41a07), then `assetgen
build --workers 2` with main's code (before) and with AG14's (after); the fit checks
(`assetgen fit`, the same code) run on both sets of packs.

## Fit checks, main and AG14

Things not resting on a surface (`asset_grounded`; "failing" are the ones assetgen seats
itself: roof items, dunnage, street pieces), roads with a step over 2 cm at a junction, and
clashes (`asset_clash`; "reported" a building's own shell within 0.5 m of its footprint
over a lane).

| City | Not resting, main | AG14 (failing) | Junction steps, main | AG14 (largest) | Clashes, main | AG14 (reported) |
|---|---|---|---|---|---|---|
| Delta Megacity | 114 | 5 (0) | 7 | 1 (0.061 m) | 652 | 0 |
| Vesper Bay | 86 | 3 (0) | 5 | 2 (0.102 m) | 912 | 1 (1) |
| Cragmouth | 560 | 530 (0) | 15 | 9 (0.764 m) | 1233 | 9 (8) |
| Vesper Bay Decks | 87 | 3 (0) | 5 | 2 (0.102 m) | 912 | 1 (1) |

What main had and AG14 has not: roof AC units, antennas, pads and dunnage off their roofs
(Delta 76, Vesper Bay 26, Cragmouth 30), transit columns and pylons short of the ground or
bed (Delta 33, Vesper Bay 49), road columns in the water with no footing (Vesper Bay 8),
building parts over the lanes (652 to 1233 a city), a transit line through a building
(Vesper Bay).

What is left (open items):

- Trash cans at raised junction corners where AG7 leaves out a corner pad that would fold
  (Delta 4, Vesper Bay 3); a street light 3.9 cm over its sidewalk (Delta).
- Cragmouth: 315 quay railings and 209 shrubs on slopes stand at the model's heights, not
  on AG7's quay and ground (M16 and M20 on terrain); a 0.76 m step where a road meets
  `jn.w765s203` (terrain grading); one shell 0.56 m past its footprint over a lane. Main
  already fails `asset_mounts` there (65 mounts off their walls, one on glass).
- Vesper Bay's level 1 junction `jn.e1151n648.l1` meets a road 0.10 m off.

Every other check passes on Delta, Vesper Bay and Vesper Bay Decks (exit 0); Cragmouth
exits 1 on main and on AG14 (`asset_mounts`, and AG14's step and shell above).

## Images

`wip/01_small_city/`: the small test city on the AG14 code (roof items on a mansard's flat
top, a halo crown's helipad inside its screen, a round tower glazed round its curve).
