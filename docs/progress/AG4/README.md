# AG4: roofs and connections

Builds of the samples with roofs, roof equipment, green roofs, facade details, skybridges,
portals and sky stations (`assetgen build`, then `assetgen materials preview` with AG6's
materials and AG8's props), every assetgen check passing in each. The full record is in
[`docs/assetgen_milestones.md`](../../assetgen_milestones.md), "AG4".

## Builds

Vesper Bay with its asset spec, Greyhook, Cragmouth and Vesper Bay Decks (built for the
checks only), each from main's city model, 4 workers. Every assetgen check passes in each
(the eleven building checks, AG7's streets, AG8's props, AG6's materials).

| | Vesper Bay | Greyhook | Cragmouth | Vesper Bay Decks |
|---|---|---|---|---|
| Buildings | 5,793 | 2,671 | 6,777 | 5,856 |
| Shell triangles | 31.97 M | 17.58 M | 34.07 M | 32.32 M |
| Roof forms | 1,115 | 293 | 1,269 | 1,024 |
| mansard, pagoda, hip, gable | 969, 38, 24, 26 | 258, 0, 0, 8 | 1,124, 59, 25, 32 | 917, 26, 23, 23 |
| sawtooth, barrel | 50, 8 | 18, 9 | 29, 0 | 28, 7 |
| Roof items | 15,597 | 7,789 | 18,553 | 15,850 |
| AC units, water tanks, antennas | 12,110, 1,100, 818 | 6,176, 672, 75 | 13,974, 1,229, 1,109 | 12,267, 1,109, 836 |
| penthouses, helipads, AV pads | 222, 19, 42 | 308, 0, 11 | 556, 11, 34 | 249, 16, 36 |
| billboards (AG8's signs) | 1,286 | 547 | 1,640 | 1,337 |
| Green roofs built | 494 of 494 | 430 of 430 | 338 of 338 | 494 of 494 |
| Access huts, skylights, roof vents | 149, 874, 6,344 | 3, 452, 3,924 | 144, 1,047, 8,357 | 160, 1,344, 7,156 |
| Fire escapes, kitchen ducts | 143, 622 | 20, 322 | 147, 834 | 132, 553 |
| Cameras, wall vents | 880, 2,998 | 431, 763 | 831, 4,114 | 726, 2,763 |
| Skybridges | 258 | 170 | 279 | 266 |
| enclosed, stack, open deck | 60, 1, 77 | 43, 0, 127 | 75, 0, 54 | 57, 1, 81 |
| catwalk, cable | 86, 34 | 0, 0 | 99, 51 | 84, 43 |
| Landing doors | 513 of 516 | 338 of 340 | 533 of 558 | 531 of 532 |
| landings off a floor line | 3 | 2 | 24 | 1 |
| Portals (cut, passing) | 20 (14, 6) | 14 (8, 6) | none | 21 (10, 11) |
| Sky stations with platforms | 2 | 1 | none | 2 |
| `assetgen build` | 4:45 | 1:56 | 7:00 | 6:48 |

A landing off a floor line is a skybridge whose deck meets the building between two of its
floors (M3's floor grids apart, or on Cragmouth's slopes two buildings seated at different
heights); it is reported, not failed. Cragmouth has one more landing at a ground floor,
where the street front meets the bridge. A passing portal is one where the tube runs
between a megabuilding's towers over its podium and meets no wall.

## Images

Whole cities (8K, every shell, part, skybridge and street piece textured; AG8's props
are drawn only near a perspective camera, so the parks read bare from this far):

- [`vesper_bay/8k/city_full.jpg`](vesper_bay/8k/city_full.jpg): Vesper Bay.
- [`greyhook/8k/city_full.jpg`](greyhook/8k/city_full.jpg): Greyhook.
- [`cragmouth/8k/city_full.jpg`](cragmouth/8k/city_full.jpg): Cragmouth.

Up close (Vesper Bay unless named):

- [`vesper_bay/8k/roofs.jpg`](vesper_bay/8k/roofs.jpg): an aerial over Old Town's roofs
  (8K): mansards, gables, hips and pagodas, water tanks on dunnage, AC units, antennas,
  access huts, billboard frames, green roofs with their gravel border.
- [`vesper_bay/stack_bridge.jpg`](vesper_bay/stack_bridge.jpg): the two-level stacked
  skybridge high in the Corporate Core, landing doors in both towers.
- [`vesper_bay/catwalk_alley.jpg`](vesper_bay/catwalk_alley.jpg): an Old Town alley under
  its catwalks and cable bridges, fire escapes on the shopfront rows.
- [`vesper_bay/tube_into_tower.jpg`](vesper_bay/tube_into_tower.jpg): the sky tube entering
  its tower in the Corporate Core through the portal, the lit frame at its mouth.
- [`vesper_bay/8k/sky_station.jpg`](vesper_bay/8k/sky_station.jpg): inside that portal
  (8K): the sky station's platform beside the tube, the portal's ceiling over it.
- [`cragmouth/old_quarter.jpg`](cragmouth/old_quarter.jpg): Cragmouth's Old Quarter: mansard
  roofs, AC units, water tanks, antennas and billboards over the shopfront streets.

Work in progress: [`wip/01_greyhook/`](wip/01_greyhook/) (the first full build: roofs,
an enclosed skybridge, a portal in The Stacks) and [`wip/02_vesper_bay/`](wip/02_vesper_bay/)
(after the fixes it found).

## What an Unreal check should look at

- **Skybridges**: every blockout skybridge replaced by its AG4 actor (`cg.type=skybridge.*`,
  `Assets/Connections/<tile>/`), at its pivot and yaw, meeting both facades; its floor
  walkable (complex collision); `cg.link=building:...` and `cg.link=walkway:...` tags.
- **Landing doors**: an opening in both buildings where each bridge lands (they are part of
  the shells, so the shell's convex hulls must not close them: the collision of a building
  is its masses' hulls, which a player in a bridge would meet at the facade; worth a walk
  through one).
- **Roof equipment**: one instanced actor per mesh and tile (`roofs.<tile>.<kind>`), the
  HISM counts equal the manifest's roof parts, every instance on its roof (none floating
  over a pitched roof: those stand on their dunnage), `NoCollision` like AG2's parts.
- **Portals and sky stations**: the sky tube's glass (AG7) passing through each portal
  without touching the lining; the station platforms either side at the tube's floor.
- **Green roofs**: the blockout green-roof objects in `replaces` gone; where an object also
  draws a lawn it stays, its flat plate under AG4's gravel border (no flicker).
- **Materials**: the new slots (roof finishes, copings, equipment, bridges, portal lining,
  lamps) on their masters; the roof equipment untinted, penthouses in their building's
  wall tint.
