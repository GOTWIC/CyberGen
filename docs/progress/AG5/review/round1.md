# Vesper Bay, art-direction round 1 (assets)

The art director's stand-in: a Claude session reading `assetgen review`'s sheet
([`round1_review.md`](round1_review.md)) and the textured previews against
`cities/vesper_bay/prompt.md` and the spec's notes (Corporate Core cleaner and quieter than
its era, Highcrest cleanest, Neon Strand worn and dense with ads, Old Town markets and
temples, The Stacks brutalist megablocks with capsule stacks). Every check passed.

## What reads wrong

1. **Corporate Core** (`round1_core.jpg`, `round1_street.jpg`): a few towers stand in solid
   gold (Aurum Bank) and red (Sable Systems) walls; the core reads as toy blocks instead of
   quiet glass. An owner's first two brand colours can become a building's walls
   (`genome`: half its buildings), and these owners list their accent second.
2. **Launch Key** (`round1_spaceport.jpg`): the long parking decks along the shore are
   amber (Orbis Logistics' second colour), louder than the hangars and the terminal.
3. **The Stacks** (`round1_stacks.jpg`): beige precast and board-marked towers, all alike;
   the capsule stacks the spec asks for are under 1% of the bodies (the sheet's systems
   column: precast 43%, board-marked 34%, punched concrete 22%).
4. **Old Town** (`round1_old_town.jpg`): dense and varied, temples in their plaza, but
   nearly every roof flat; the heritage era's pitched roofs (one crown in three) lose to
   the roof items that ask for a flat top.

What reads right: the megatower (near-black glass, red seams, the halo and needle) over the
core, Highcrest's villas with green roofs, the docks' sheds and yards, the spaceport's
vaulted hangars, control tower and terminal, Scholar Isle's labs.

## Spec changes for round 2 (`assetgen spec diff`)

```
districts.The Stacks.systems.capsule_stack: 0.2 -> 0.45
districts.The Stacks.wear: 1.1 -> 1.3
eras.heritage.crowns: added ["pitched", "pitched", "pagoda_roof", "parapet"]
owners.aurum_bank.brand_colors: ["#2b2d42", "#d4af37"] -> ["#2b2d42", "#5c5446", "#d4af37"]
owners.orbis_logistics.brand_colors: ["#1d3557", "#f1a208"] -> ["#1d3557", "#4a5568", "#f1a208"]
owners.sable_systems.brand_colors: ["#0b0b0f", "#c1121f"] -> ["#0b0b0f", "#3a3d44", "#c1121f"]
```

The owners' accents move to third place (trim only: walls draw from the first two), The
Stacks take more capsule stacks and more wear, the heritage era weights pitched roofs two
in four. Between the rounds three AG5 fixes also landed in code (terrace planters the
envelope had refused, light seams over glass, a hero's unsupported masses); they show on the
megatower's setbacks, not in what the rounds compare.
