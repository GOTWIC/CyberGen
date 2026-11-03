# AG15: cyberpunk facades and night

The four cities built with citygen on main (3b03dba; AG14 and AG15 change no citygen code,
so the citygen outputs are AG14's), then `assetgen build --workers 2` with AG14's code
(before, AG14's `after` builds) and with AG15's (after). The neighbor rule's numbers are
measured on both sets of records the same way (`neighbors.pairs`: towers within 150 m,
outside one complex family).

## The neighbor rule, AG14 and AG15

Pairs of neighboring towers sharing each kind (a pair can share several); "lit alike" on
AG14 is a pair of the same use, since AG14 lit every building by one night look (AG6's
interior atlas, one warm color, its use's lit share).

| City | Towers | Pairs | Same system, AG14 | AG15 | Same window pattern, AG14 | AG15 | Same palette, AG14 | AG15 | Lit alike, AG14 | AG15 | Failing pairs, AG15 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Delta Megacity | 359 | 1,402 | 306 | 0 | 268 | 0 | 49 | 0 | 1,385 | 0 | 0 |
| Vesper Bay | 175 | 661 | 156 | 0 | 141 | 0 | 23 | 0 | 658 | 0 | 0 |
| Vesper Bay Decks | 196 | 857 | 254 | 0 | 215 | 0 | 18 | 0 | 846 | 0 | 0 |
| Cragmouth | 228 | 767 | 177 | 0 | 152 | 0 | 25 | 0 | 755 | 0 | 0 |

AG15's day and night thumbnails of every neighboring pair differ by 8 bits or more (none
failing in any city).

## Delta Megacity

- **Towers**: 15 body systems among the 359 (unitized curtain wall 50, mesh screen 36,
  diagonal glazing 34, LED grid 32, hex skin 30, spandrel ribbon 29, slit panel 27, folded
  glass 24, ...); window patterns grid 133, stagger 44, alternate 42, scatter 38, stepped 38,
  mixed 33, checker 31; wall and skin finishes per tower: one 6, two 80, three 171, four or
  more 102.
- **Night**: schedules office 273, home 44, shop 27, vacant 15 (no two side by side);
  5,522 crown and edge LED strips, 82 logos, 16 media screens; M21's bands and curved
  shafts carry 79,712 mullions and LED strips.
- **Signs**: every one of M20's slots had its emissive asset before AG15 (AG8: billboard
  facade 2,750, billboard roof 963, banner 939, holo-ad front 89, holo-ad roof 112); AG15
  adds their wash on the facade (3,778 wash points in `play.json`, the 32 nearest lit).
- **Lamps**: 4,731 street and wall lights; AG14 lit the 48 nearest with a point light at
  the lamp head (inside the lamp's own shadow, nothing on the ground); AG15 a spot light
  45 cm under each of the 192 nearest (8 with shadows) and a light pool under 768 more.
- **Budgets**: 31.7 M unique triangles (AG14 32.4 M; the bands drawn with mullion parts
  instead of glass ribbons cut by floor), 1.12 M part instances (AG14 0.99 M), within
  section 11's budget (ratio 0.32).

## Checks

Every check passes on Delta Megacity and Vesper Bay. Vesper Bay Decks fails
`asset_envelope` on one building (`d05.lot.w576n1053.bld`) and Cragmouth `asset_mounts`
(64 mounts off their walls, one on glass) and `asset_access` (a door blocked), exactly as
on AG14 and main.

## Images

`wip/01_vesper_bay/`: the first AG15 build of Vesper Bay's core by day and night (1600 px).
`renders/`: the shows at 8K (see the root README).
