# AG14: fit and finish

The four sample cities built with citygen on main (with the park paths fix, 3b03dba), then
`assetgen build --workers 2` with main's code (before) and with AG14's (after); the fit
checks (`assetgen fit`, the same code) run on both sets of packs.

## Fit checks, main and AG14

Things not resting on a surface (`asset_grounded`; in brackets the failing ones, what
assetgen seats itself: roof items, dunnage, street pieces; the rest are props and plants at
the model's heights, listed), roads with a step over 2 cm where they meet a junction (a
step over 0.15 m fails), and clashes (`asset_clash`).

| City | Not resting, main | AG14 (failing) | Junction steps, main | AG14 (largest) | Clashes, main | AG14 |
|---|---|---|---|---|---|---|
| Delta Megacity | 108 | 6 (0) | 7 | 1 (0.022 m) | 653 | 0 |
| Vesper Bay | 80 | 2 (0) | 5 | 2 (0.102 m) | 910 | 0 |
| Cragmouth | 564 | 535 (0) | 15 | 8 (0.125 m) | 1235 | 0 |
| Vesper Bay Decks | 88 | 3 (0) | 3 | 2 (0.102 m) | 981 | 0 |

What main had and AG14 has not: roof AC units, antennas and pads off their roofs (Delta 69,
Vesper Bay 20, Cragmouth 29, Vesper Bay Decks 44), transit columns and pylons short of the
ground or bed (Delta 33, Vesper Bay 49, Vesper Bay Decks 32), road columns in the water
with no footing (Vesper Bay 8, Vesper Bay Decks 9), building parts over the lanes (653 to
1235 a city), a transit line through a building (Vesper Bay).

Every check passes on Delta Megacity and Vesper Bay. Cragmouth fails, on main as with
AG14, `asset_mounts` (64 mounts off their walls, one on glass) and `asset_access` (a door
blocked); Vesper Bay Decks fails, on main as with AG14, `asset_envelope` on one building
(`d05.lot.w576n1053.bld`). The fit checks pass on all four.

Listed, open:

- Trash cans at raised junction corners where AG7 leaves out a corner pad that would fold
  (Delta 4, Vesper Bay 2, Vesper Bay Decks 3); a trash can 2.2 m over a sidewalk and a
  street light 3.9 cm over one (Delta).
- Cragmouth: 315 quay railings and 214 shrubs on slopes stand at the model's heights, not
  on AG7's quay and ground (M16 and M20 on terrain).
- Steps of 0.10 to 0.13 m: Vesper Bay's level 1 junction `jn.e1151n648.l1`, two steep
  Cragmouth junctions.

## Images

Vesper Bay on the AG14 code (`assetgen materials preview`, custom cameras):

- `vesper_bay_transit_frame.jpg`: a portal frame's leg and haunched cap beam under the Halo
  Line (the camera close beside the other leg).
- `vesper_bay_round_tower.jpg`: a round tower's curved wall, smooth and glazed bay by bay.
- `vesper_bay_quay.jpg`: a quay with its railings, benches and trash cans on the quay deck,
  the river bank and its waterline.
- `vesper_bay_transit_masts.jpg`: road columns, the sky tube's masts with their crossheads
  and stays.

`wip/01_small_city/`: the small test city on the AG14 code (roof items on a mansard's flat
top, a halo crown's helipad inside its screen, a round tower glazed round its curve).
