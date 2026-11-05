# Moorings fix (#113)

A fix between milestones, from issue #113: moored boats lay inside the quay wall. The night
canal shot (`docs/progress/AG12/vesper_bay/8k/water_canal_night.jpg`) shows one in the
right quay.

## What was wrong

A quay (`citygen/waterways.py`, `_quays`) is a line on the waterway's edge and a band
`width_m` wide centered on it (canal 5, inlet 6, marina 8, basin 15 m), so half the band
lies over the water. The blockout draws it that way (`ribbon(qy.line, qy.width_m)`), and so
does AG7 (`assetgen/streets/water.py`, `make_quay`: the quay wall stands `width_m / 2` out
over the water). M6 moored each boat with its middle `beam / 2 + 1 m` off the line, so its
hull started 1 m out: inside the band on every quay. A canal boat's hull (1.0 to 3.4 m out)
cut 1.5 m into the 2.5 m of quay over the water, and a basin boat (1.0 to 4.0 m out) lay
wholly under its 7.5 m. `boats_afloat` only checked that the hull lay in the waterway's
polygon, which the band does not change.

## What changed

- **Moorings** (`citygen/props.py`, `quay_props`): a boat's middle is `width_m / 2 +
  MOOR_GAP_M + beam / 2` off the line on the water side (`MOOR_GAP_M` 0.4 m, its fenders), so
  its hull lies just past the quay wall.
- **Clearances** (`boats_in_water`): a boat's hull (`boat_hull`, KINDS' 8 x 3 m scaled as
  placed) must keep clear of every quay's band (`Moorings.quay_hit`, any quay, not only its
  own) and keep `SHORE_CLEAR_M` (1 m, the thickest wall M16 stands at the water's edge:
  `water.WALL_W`, a canal wall 0.6 m, a quay 1 m) off its waterway's shore, besides the old
  rules (in its waterway, clear of bridges, apart from the others). The hull is tested where
  the model will have it, on the 1 cm grid. A boat with no room for that is left out.
- **Check** (`citygen/prop_checks.py`, `boats_afloat`): also fails a hull that reaches into
  any quay's band, or into one of M16's banks of its own water (from the bank's line out to
  its waterline: a canal wall's thickness, a quay's 1 m); on a city without M16's banks, the
  shore by `SHORE_CLEAR_M`. It notes the boat count.
- **AG8**: no change. Every boat variant (`assetgen/props/variants.py`, `boat`) fits the
  same 8 x 3 m footprint at its base size and is scaled as M6 scales it, so the drawn boats
  are the hulls the check tests.

Nothing else in a model moves: Vesper Bay's model on main and on this branch differ only in
their boat rows (46,545 other props, the same records).

## Numbers

Boats on main, then this branch. On main every boat's hull reached into its quay's band (by
construction; measured on Vesper Bay, 49 of 49, its 16 basin boats wholly under the band);
on this branch none does. Every city builds on main's full-city tries and passes every
check (102, 107 with the deck).

| City | Boats | Full-city tries |
|---|---|---|
| Saltreach Free Port | 34 / 33 | 1 |
| Delta Megacity | 72 / 71 | 2 |
| Nexus City | 65 / 63 | 1 |
| Greyhook | 30 / 29 | 2 |
| Vesper Bay | 49 / 46 | 1 |
| Vesper Bay Pinned | 74 / 56 | 2 |
| Vesper Bay Stacks | 77 / 59 | 2 |
| Vesper Bay Decks | 49 / 46 | 1 |
| Cragmouth | 47 / 47 | 2 |

The pinned and stack demos lose the most: the traced district's water pockets are basins
with a 15 m quay, and many are too small to take a boat past 7.5 m of quay on each side.

Assets: Vesper Bay's full `assetgen build` (buildings, streets, water, props, ground,
materials, fit) passes every check on both. Between the two, only the props contribution
changes for the boats; the building, street, water and ground packs are the same bytes, and
the contributions differ only by the model's sha256 they record.

## Goldens

Written again on the M4 Mac from these builds: `tests/data/golden_hashes.json` (every
sample's model and blockout plan: the boats move); `tests/assetgen/data/golden_hashes.json`
(the briefs record the model's sha256: the five samples' and the small test city's briefs,
the small city's asset manifest, files and materials); `golden_props.json` (the small test
city's boats, 47 to 43) and `golden_ground.json` (its contribution records the model's
sha256). `golden_water.json` and the building goldens do not move.

`golden_props.json` did not match main before this change (main's small city gave 109
files, the golden said 98); it is written again here anyway, as the boats move it. After
main's median fix (#117) was merged in, the small city's materials digest (`ag6`'s
`testport_materials`, which hashes its streets contribution) was written again on both
changes; #117's street goldens hold with the moved boats.

## Images

- `vesper_bay/water_canal_night_before.jpg`, `water_canal_night_after.jpg` (and at 7680 px
  in `vesper_bay/8k/`): `assetgen materials preview --views water --night`, the canal view
  by night on main and on this branch. On main the boat on the right lies in the quay wall.
- `vesper_bay/water_canal_before.jpg`, `water_canal_after.jpg`: the same by day.
- `vesper_bay/basin_before.jpg`, `basin_after.jpg`: the east quay of a harbor basin
  (`d06.ww.w503s1220`) from over its water, 16 m up (`--eye -470 -1365 16 --target -433
  -1325 -1 --lens 35`), by day. On main its barges lie under the 15 m quay, their
  containers showing through the paving; with the fix they float beside the quay wall. (AG12's `water_harbor` view from above draws the props only within
  320 m of its eye, `PROPS_R`, so it shows none of the basin boats on either.)
- `vesper_bay/plan_canal.png`, `plan_harbor.png`: plans of the canal in that view and of the
  harbor basins, main beside this branch: water, quay bands, boat hulls (red where a hull
  reaches into a quay's band).
- `<city>/report.txt`: each city's build report on this branch.
