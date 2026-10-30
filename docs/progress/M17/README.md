# M17: road network repair

From the first run-through (`docs/run_through_1.md`): roads that stop at random and roads that
overlap on straight stretches; bridges apart and roads clear of buildings, which were clean in
the model, now guarded by checks.

## What changed

**Dead ends** (`citygen/streets.py`, `settle_dead_ends`, the last step of the street
clean-up, on the noded network, in rounds):

- a local road's dead end runs on to the road straight ahead (within 60 m) where that road
  takes a junction, or to a junction of it within 20 m (8 m for a path), turning at most 35
  degrees and meeting it at the district's junction angle, on land, off parks, reserves and
  traced buildings, crossing no other road (a path may pass under a deck 4.5 m up, a street
  under a viaduct 7.8 m up, and go on to the road beyond); two dead ends facing each other
  within 30 m are joined;
- a dead end that stays says what it is: `RoadNode.attrs.dead_end` is `map_edge`,
  `water_end`, `park_gate`, `plaza_gate`, `site_gate` (within 8 m past its half width of the
  water, open land or a megasite reserve; 30 m for an avenue or a highway, with a promenade
  and a quay between it and the water), `path_end` (a pedestrian path), `cul_de_sac` with a
  turning bulb (`attrs.turning_head_m`: street 12 m, service lane 10 m, alley 8 m, a primary
  road its half width and 4 m; drawn by `junctions.build` as before, now wherever it fits) or
  `deck_end` (M14's deck spokes);
- anything else goes back to its last junction: a vehicle road shorter than 40 m from it, or
  one with no room for its bulb;
- a dead end reaching into another road's right of way is cut back clear of it, and a primary
  road's dead end cuts the local road it reaches into; a local road laid along another
  (rights of way overlapping by more than 10 m2 away from the nodes they share) goes, the
  lesser one; the street clean-ups' cut-backs (`fix_angles`) run again after the run-ons,
  and lanes reached only over paths become paths (`pedestrianize_islands`) after the repair;
  a cut-back never takes a primary road.

**Junctions** (`citygen/junctions.py`):

- each leg's cut-back reaches past where its right of way overlaps another leg's
  (`overlap_cuts`): acute corners, legs that bend inside the junction, gores;
- a road's two junctions share 0.9 of it by need (`share_cuts`; each end had 0.45 before), so
  a big junction next to a small one reaches past its overlaps on a short road;
- a degree-2 node where two roads meet at an angle (an avenue that ends in a street, a street
  that goes on as a promenade) is a `bend` junction (new `Junction.shape`) cut back like the
  others;
- where two legs' rights of way still overlap past their cuts (a fork, a crossing at a small
  angle, a corner with no room for its fillet) the junction polygon takes that shared
  pavement (`shared_pavement`), and two primary roads that go on sharing pavement past the
  next junction of one of them give that overlap to the junction it touches
  (`absorb_shared`).

**Checks** (`citygen/network_checks.py`, four more):

| Check | Rule |
|---|---|
| `road_dead_ends` | every dead end tagged, and the tag true of where it is (at the map edge, by the water, at an open space, plaza or megasite, on a path, a cul-de-sac with its bulb, on a deck) |
| `road_overlaps` | two roads within 4 m in height overlap by no more than 25 m2 outside every junction polygon (the run-through's measure, on the 1 cm grid) |
| `bridge_clash` | road, pedestrian and transit bridges (decks and approaches) apart in plan, or the lower one's clearance under the upper deck where they cross (5.5 m under a road or transit deck, 2.5 m under a pedestrian one, plus the upper deck: 1.5 m for a road, M7's 7 m between crossing road decks) |
| `road_building_clash` | no road right of way over a building mass at the road's own height (5 m of headroom over a vehicle road, 2.5 m over a path; a ferris wheel's rim measured where it is) |

`road_dead_ends` and `road_overlaps` run with the street checks (on the M2 model during the
build), `bridge_clash` and `road_building_clash` after the building checks; `check_all` (M10's
regeneration and overrides) runs all four. Heights are over the ground (M13): a road's surface
is its grade line plus its z profile, a building's masses stand on its base.

## Decisions

- **M1b as it was**: parting primary forks and dropping primary lenses in M1b removed the
  overlaps at their source, but it changes which road network each city's search picks
  (Delta and Vesper Bay then failed every try on their new networks: short avenue pieces, a
  waterfront avenue ending in a one-way off-ramp); the shared pavement goes into the
  junction polygons instead, and M1b's networks are byte for byte what they were.

- **The run-through's 308 dead ends**: 69 of them are local streets that run off the map
  (their nodes are `end`, not `edge`, so the run-through's script counts them); they are
  `map_edge` now. Of the 239 inside the map, 206 had a road within 60 m ahead.
- **Dead ends that stay with a road ahead**: the run-through's script counts a dead end with
  any road within 60 m straight ahead. Most left are paths and streets ending short of a deck
  they pass under or a highway, a bridge or a raised approach that takes no junction; they
  are tagged (water end, path end, cul-de-sac with its bulb).
- **Cul-de-sac or cut back**: the scope's list has the cul-de-sac with a turning head as a
  deliberate dead end, and its rule cuts back the rest. A vehicle dead end 40 m or more from
  its junction with room for its bulb is a cul-de-sac (a long dead-end street serves its
  lots); a shorter one, or one with no room, is cut back.
- **Overlap tolerance**: the check keeps the run-through's 25 m2 (two sidewalks meeting at a
  corner overlap outside the carriageway polygon).
- **GEOS**: GEOS's floating overlay (shapely 2.2, GEOS 3.14) takes two corridors that meet end
  to end on a 45 degree line for one inside the other (Cragmouth's and Vesper Bay's 45 degree
  grids); the check and the measures here use fixed-precision overlays on the 1 cm grid. The
  run-through's script uses floating overlays and can report such false pairs.
- **Clearances**: `bridge_clash` asks for the clearance the generators keep (M7's 7 m between
  crossing road decks, 5.5 m plus the deck for transit over a road); a road under a ferris
  wheel is measured under its rim, which is a circle, not the mass's lowest point.

## Before and after
