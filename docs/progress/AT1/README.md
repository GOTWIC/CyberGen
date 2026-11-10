# AT1: streets at night (atmosgen)

Stage 3's second milestone (`docs/atmosgen_scope.md` section 13): the streets lit by night as
a lighting engineer would light them, checked before Unreal, and rendered in Unreal from the
level itself. Built on the Windows PC (RTX 4070 Ti, 32 GB), 2026-11-10, on main after AT0
(#185). AT0's report (`docs/progress/AT0/README.md`) set the starting point: tiles as data
actors with a pooled live set, the junctions lit, the cobra heads brought down, the play
features' lamps and washes retired, their pools kept as the far tier.

## What AT1 built

| Part | Where | What |
|---|---|---|
| Photometric classes | `atmosgen/presets.py` `PHOTOMETRY` | cobra head, post top, wall pack, high mast, highway, soffit, tunnel, platform; each light's profile Unreal's own (a spot flat to its inner cone, falling as $t^2$ to its outer; a point all round; a face by its cosine and barn doors; the engine's reach window), so the check and the runtime agree |
| Street and wall lights | `plan.lamps` | M6's lamps by class at their heads: cobra heads 1200 cd to 62 degrees (AT0: 6000 cd in 45), post tops 600 cd, wall packs 420 cd |
| Junctions | `plan.signals`, `plan.corners` | a mast arm light on every traffic signal reaching into its junction; corner poles where the check finds a junction dark (at its legs' sidewalk ends and its crosswalks' ends, else its outline's corners; the one leaving fewest points dark first, at most 6) |
| Roads M6 leaves unlit | `plan.roads`, `plan.alleys` | highway and ramp columns every 42 m (a twin arm in a median, else staggered), service roads, posts every 16 m on pedestrian streets and promenades, posts on footbridges, wall packs along alleys (closer in lighter moods) |
| Structures | `plan.decks`, `plan.tunnels`, `plan.stations` | AG10's soffit lights under M14's decks (at AG10's own fixtures), AG7's road tunnel wall strips and underpass ceiling strips, platform downlights in elevated and underground stations |
| Fill | `plan.fill` | a light at the darkest point of each walkway or road the check still finds dark (a wall pack, a curb post, a road-edge pole), a round at a time |
| Shop spill, signs | `plan.spill`, `plan.signs` | as AT0 placed them (AT2 takes the signs further) |
| The lux check and map | `atmosgen/lux.py` | every walkway and lane every 2 m by class, occlusion against masses and deck slabs, targets by class (scope 8), per city and per district; `checks.lux` in the plan; `atmosgen plan` exits 1 and the exporter leaves a failed plan out; `preview_lux.png` with occlusion |
| What a light hangs on | `Light.mount` | the city's own fixture, or a pole, mast arm, wall pack or canopy downlight asked of stage 2 (`emitters.py`'s third ask, assetgen scope 4.6) |
| Exporter | `citygen/unreal_atmos.py`, `ue/import_city.py`, `ue/CityGenAtmos` | layer 3 of the manifest: the controller and a data actor per 128 m cell placed by the import, the cells registering with the controller as they stream; no more `-CityGenAtmosPlan`; the play features' spot lamps and washes gone, their pools the far tier |

## The plans and the lux check

`atmosgen plan` on AG16's builds (an empty spec: `neon_rain`, checked at 23:00), every city
passing (sidewalk 10 lx average and 2 lx minimum, crosswalk 10 and 2, carriageway 7 and 1,
under a deck 5 and 1, alley 2 and 0.5 and never dark; at most 5% of a class's points under its
minimum over the city, 15% in a district):

| City | Lights | Sidewalk avg / under min | Crosswalk | Carriageway | Alley | Under a deck | Junctions dark before corners | Fill lights | On asked fixtures | Check |
|---|---|---|---|---|---|---|---|---|---|---|
| Delta Megacity | 53,062 | 27.2 / 0.8% | 26.2 / 1.1% | 16.9 / 0.1% | 13.5 / 0.3% | - | 325 of 1238, 441 poles | 608 | 5,225 | PASS |
| Vesper Bay | 52,186 | 27.8 / 0.8% | 26.2 / 0.9% | 17.2 / 0.1% | 13.4 / 0.3% | - | 425 of 1348, 512 poles | 669 | 4,938 | PASS |
| Vesper Bay Decks | 56,977 | 28.0 / 0.8% | 26.4 / 0.9% | 17.4 / 0.1% | 13.4 / 0.3% | 45.2 / 0.0% | 420 of 1391, 501 poles | 666 | 4,945 | PASS |
| Nexus City | 60,600 | 28.6 / 1.1% | 27.9 / 0.9% | 17.6 / 0.8% | 13.6 / 0.2% | - | 382 of 1426, 491 poles | 655 | 5,570 | PASS |
| Greyhook | 30,009 | 22.9 / 0.4% | 24.2 / 0.7% | 15.1 / 0.0% | 12.2 / 0.2% | - | 213 of 680, 290 poles | 454 | 3,670 | PASS |
| Saltreach Free Port | 28,376 | 22.9 / 0.9% | 24.9 / 0.8% | 16.0 / 0.4% | 13.8 / 0.4% | - | 238 of 716, 344 poles | 455 | 3,241 | PASS |
| Cragmouth | 64,531 | 31.6 / 0.7% | 27.3 / 1.1% | 18.2 / 0.1% | 13.1 / 0.3% | - | 412 of 1577, 494 poles | 709 | 5,498 | PASS |
| Vesper Bay Pinned | 55,480 | 29.5 / 1.0% | 27.5 / 0.9% | 17.8 / 0.4% | 13.7 / 0.3% | - | 451 of 1572, 516 poles | 661 | 5,228 | PASS |
| Vesper Bay Stacks | 55,931 | 29.5 / 1.1% | 28.4 / 0.9% | 18.0 / 0.4% | 13.5 / 0.3% | - | 447 of 1570, 525 poles | 701 | 5,236 | PASS |

(lux, average over the class's points / share under its minimum.) Each plan takes 20 to 45 s
on the PC, the check's illuminance with occlusion about 5 s of it on Delta.

**How the first plan on Delta failed, and what fixed it** (the check doing its job):

| Step | Sidewalk under 2 lx | Crosswalk under 2 lx | Carriageway under 1 lx | Alley under 0.5 lx (dark points) |
|---|---|---|---|---|
| AT0's photometry, junctions unlit (AT0's lux map, no occlusion) | | 25% (junction lanes 54% under 1 lx) | | |
| AT1's classes, mast arms, highway columns, alley packs, corner poles | 8.0% | 7.8% | 3.0% | 32.5% (5,995) |
| occlusion taken 0.5 m inside the footprints, packs inside the alley's edge | 7.6% | 5.1% | 2.3% | 13.1% (1,701) |
| posts on pedestrian streets and promenades (M6 lights none of their 347 segments), corner spots on junction outlines | 3.9% | 2.6% | 1.5% | 5.3% (456) |
| the fill at the darkest points | 0.8% | 1.1% | 0.1% | 0.3% (0) |

On the pinned demo the check also found two places where the walk graph's heights disagree
with the road they lie on: a quay road's walk kept at 11.6 m where the road climbs from 0, and
a raised bridge-head junction's crosswalks kept on the ground. The check now puts a walkway
that runs along its road on the road's own profile, and a raised junction's crossings at its
node's height (the walk graph's raised sidewalks are a known stage 1 open item).

The carriageways average 15 to 18 lx (AT0's 52 lx): the cobra heads came down to a fifth and
spread wider, and the junctions are lit (AT0's junction lanes were 54% under 1 lx; AT1's 0.3%
on Delta).

![Delta, lux round the Corporate Core](wip/01_plan/delta_preview_lux.png)

## Unreal

(the import, the check by night and the benchmark follow below)
