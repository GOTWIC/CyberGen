# AG5: types, landmarks and slopes

Builds with `assetgen build` (4 workers) and textured renders with `assetgen materials
preview` (Blender 5.2, EEVEE). Full record: [`docs/assetgen_milestones.md`](../../assetgen_milestones.md),
AG5.

## Images

CITY_IMAGES

## Art-direction rounds on Vesper Bay

[`review/`](review): the two rounds' sheets (`review.md`), notes and before and after
images.

## Numbers per city

NUMBERS

## What the Unreal check should look at

- **Heroes**: the megatowers (Vesper Bay, Nexus City, Cragmouth, Delta Megacity), Nexus
  City's three spires and Greyhook's and Nexus City's wheels: actors tagged `cg.hero=<kind>`,
  their materials `MI_buildings_<slot>_<era>_<id>` reading `T_city_hero_<id>` on UV1
  (grime at the foot and washed down under every setback, leaks under the sills, wear at
  the corners), the light seams and halo in the accent colour; the masters rebuilt
  (`STAGE2_VERSION` 6) and every other building unchanged by `HeroMaskOn` 0.
- **Slopes** (Cragmouth): buildings tagged `cg.plinth=<m>`; the stepped plinth meeting the
  terrain heightfield with no gap and no floating corner (traces at a plinth's corners and
  steps), shopfronts and doors at grade on the downhill side, retaining skirts uphill.
- **Landing doors**: walk across a skybridge into its landing door (the hull notched 2.5 m
  at the door, `collision.VESTIBULE_MM`); Vesper Bay has 513 landing doors.
- **Types**: open sheds (walk under the roof between the columns), temple colonnades,
  control tower cabs and vaulted terminals in the spaceports, hangar doors, parking ramps,
  shanty lean-tos and fire escapes in The Stacks: collision as before (hulls of the
  masses; the parts have none).
