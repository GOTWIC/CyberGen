# DLSS, ghost lamps and fewer flickers (after LG0)

Three fixes from Swagnik's walk of the packaged Delta Megacity, in one pass on the Windows PC
(RTX 4070 Ti, 32 GB, UE 5.8), 2026-11-14, on main after LG0 (#222): NVIDIA's DLSS as an option
of the exporter and a row of the play features' menu, a fixture under every light that had none
("ghost lamps"), and ten times fewer flickering lights.

## 1. Ghost lamps

> "there seem to be quite a few ghost lamps, ie the light is there but theres no lamppost
> there"

**Cause.** AT1 and AT2 light what M6 leaves dark on fixtures they asked of stage 2
(`emitters.py`'s third and fourth asks, `Light.mount`): corner poles at dark junctions, the
signals' mast arms, highway, ramp, service road, pedestrian street and footbridge posts, alley
wall packs, port and apron high masts, crown floods out from their facades. Stage 2 never drew
them: 9,841 of Delta's lights hung in the air. The new check also found 380 of AT2's beacons and
searchlights off their buildings: they stood on the corners of a curved or odd footprint's
oriented box, metres off the footprint itself.

**Fix** (`atmosgen/fixtures.py`). The atmos plan draws a fixture under every such light from
AG8's own prop variants, so the style is the district's (sleek in the Corporate Core, old in Old
Town):

| Mount | Fixture | Delta |
|---|---|---|
| `pole` (corner poles, road, highway and ramp columns, service roads, pedestrian streets, footbridges, fill lights) | an AG8 street light at the pole's foot, turned so its arm reaches toward the head, scaled to the head's height (0.45 to 1.9), its arm stretched at most 1.6 times; a post top where the head is over its foot; a twin column in a median two back to back | 3,593 |
| `mast_arm` (a signal's) | an AG8 street light at the signal's own foot (AG8 draws the signal), its arm over the junction | 902 |
| `wall` (alley wall packs) | an AG8 wall light on the facade within 1.2 m behind the light, else a pole just off the alley with its arm over to it | 1,036 (798 on walls, 238 poles) |
| `mast` (high masts) | AG8's heavy street light's mast form, scaled to 30 m | 29 |
| `roof` (crown floods, uplights) | AG8's heavy wall light's flood form tilted up, on its setback, podium or the ground, or on an outrigger (AG8's bracket) from its facade | 1,515 (1,254 outriggers) |

Each light moves onto its fixture's lens (median 0.02 m; mast arms 3.3 m back toward their
signal, where AG8's arm, stretched, still falls short of the plan's 6 m one), and the lux check
runs on the moved lights (it passes: sidewalks 24.0 lx, 1.4% under their minimum; carriageways
14.3 lx, 0.8%; alleys 12.1 lx, none dark). A fixture keeps off every vehicle carriageway,
junction and crosswalk at its height as AG8's props do (`gather._Fit` on the pavement map),
pushed back from the road a quarter metre at a time and turned up to 90 degrees either way, out
to 4 m; 43 lights whose pole finds no clear spot are left out. Lights on what stage 2 draws need
nothing: M6's lamps, signs, shopfronts, AG10's soffits, AG7's tunnel strips, a station's roof, a
deck's slab, a crane's boom. AT2's beacons and searchlights now stand on their footprints
(`plan.corners_on`).

**Which stage: atmosgen's (layer 3).** The lights exist only in its plan, and stage 3 reads stage
2, not the other way: assetgen drawing them would make stage 2 read stage 3's plan. The fixtures
are only AG8's meshes placed again: the plan writes `fixtures.json` and
`unreal_contribution.fixtures.json` (an entry per 128 m cell, `atmos.fixtures.<tile>.<quarter>`,
instanced parts in AG8's `props` part, so the exporter imports AG8's meshes and materials once
for both), which `citygen unreal` layers with stage 2's contributions where the plan is delivered.

**Check** (`checks.fixtures`): every light on something at its height (its fixture's lens within
2 cm, stage 2's own fixture, a structure within 2 m, the ground) and every fixture clear of the
carriageways; a failing plan is not delivered. Delta: 50,257 lights, 7,075 on their fixtures,
40,969 on stage 2's, 2,213 on structures, none on nothing, none on a carriageway; 8,329 fixtures
(4,762 street lights, 2,313 wall lights and flood heads, 1,254 outrigger brackets).

| Before: the junction from 12 m, no pole under the mast arms' lights | After: AG8's street lights at the signals |
|---|---|
| ![](shots/night_ghost_junction_high_before.jpg) | ![](shots/night_ghost_junction_high_after.jpg) |
| **Before: an Old Town alley** | **After: its wall packs on poles and walls** |
| ![](shots/night_ghost_alley_before.jpg) | ![](shots/night_ghost_alley_after.jpg) |

![The junction at street level, after](shots/night_ghost_junction_low_after.jpg)

## 2. Fewer flickers

> "there are quite a few places where lights flicker. they seem intentional, so if they are,
> please reduce the rate by which they occur by 10x."

They were intentional (AT2's moods: flicker shares by archetype, pulled up by danger, by kind;
broken signs dying in a deep flicker).

- **Ten times fewer** (`presets.FLICKER_SCALE` 0.1): the moods' flicker shares times 0.1, still
  times (0.5 + danger), and a broken sign dies flickering at that share (the rest burn steady,
  as their faces do).
- **Spaced out:** a flickering light flickered a third of every second, every second
  (independent 1/12 s steps). The runtime now flickers it in bursts (`ACityGenAtmos::InBurst`):
  a burst of 0.35 to 1 s once every 9 to 26 s, a dying tube's 0.8 to 2 s every 4 to 10 s, each
  light's own from its seed; steady between. Stateless, the same at any frame rate.

| Delta | Before (AT7's plan) | After |
|---|---|---|
| Flickering lights | 8,585 | 890 |
| shop signs / spill / signs / roads / wall lights / street lights / alleys / neon | 5,002 / 1,212 / 615 / 422 / 385 / 332 / 297 / 235 | 545 / 115 / 68 / 39 / 39 / 31 / 24 / 20 |
| Flickering 0.8 deep and more (mostly dying signs) | 2,171 | 234 |
| Broken (dark) lights | 2,008 | 2,005 |

## 3. DLSS

BENCH_PLACEHOLDER

## Validation

- `tests/atmosgen/test_at_streets.py` (a new fixtures test), `test_at_signs.py` (the flicker
  test at the new shares), `test_at_plan.py`, `tests/test_unreal_dlss.py` (new: the plugin's
  install, the build stamp, the bench passes and frame generation's columns, the launcher's
  download as busy, the fixtures' contribution only from a delivered plan): all pass.
- Delta's atmos plan with every check (lux, faces, air, weather, far, fixtures) passing.
- Delta imported over its AT7 and LG0 import in CityAG16 with `--dlss` (493 actors created, 505
  updated, 13 meshes imported, HLODs rebuilt), the check by night passing with the views above.
- Packaged (Development, Win64) with DLSS; PACKAGE_PLACEHOLDER

## Open items

OPEN_PLACEHOLDER
