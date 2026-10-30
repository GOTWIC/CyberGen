# Vesper Bay, art-direction round 2 (assets)

Round 1's spec changes built ([`round2_review.md`](round2_review.md), every check passing)
and the same views rendered again. Before (`round1_*.jpg`) and after (`round2_*.jpg`):

| View | Round 1 | Round 2 |
|---|---|---|
| Corporate Core | `round1_core.jpg` | `round2_core.jpg` |
| A street by the core | `round1_street_4.jpg` | `round2_street_4.jpg` |
| The Stacks | `round1_stacks.jpg` | `round2_stacks.jpg` |
| Old Town | `round1_old_town.jpg` | `round2_old_town.jpg` |
| Launch Key | `round1_spaceport.jpg` | `round2_spaceport.jpg` |

## What changed

- **Corporate Core and Scholar Isle**: the gold and red towers are now navy, warm grey,
  black or graphite with the brand colour on their trim; the core reads as one quiet field
  of glass under the megatower, as the prompt's notes ask. Street 4's yellow block and red
  tower went with them.
- **Launch Key**: the shore parking deck that was amber is now dark; the other orange deck
  takes its colour from the aerospace era's palette (left: it reads as the spaceport's
  service strip).
- **Old Town**: pitched crowns from 963 to 1,409 of its 2,921 buildings (most built as
  mansards, where roof items ask for a flat top); the roofscape reads warmer and less like
  flat boxes.
- **The Stacks**: wear 0.72 to 0.81 on average; the capsule share hardly moved (one tower).

## Still off (not the spec's to fix)

- **The Stacks' capsules**: capsule stacks are built only up to 40 floors
  (`systems.FLOORS`), and the megablock towers are taller, so they fall back to precast
  panels whatever the district's weight. A taller capsule system, or capsule stacks on the
  podiums and lower towers, is code (left for AG9).
- **The megatower's glass** reads grey-blue like its neighbours, not the brief's near-black:
  AG6's interior mapping and sky reflection dominate the glass tint. A hero glass with a
  darker reflection is code (AG9 or a later AG6 pass).

Two rounds as asked; the round 2 spec is now `cities/vesper_bay/asset_spec.json`.
