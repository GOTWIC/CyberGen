# Support and elevator fixes (#108, #109)

Two fixes between milestones, found by the access fixes (#106).

## #108: a sky tube with no support spot over a dense core

On Vesper Bay Decks' second full-city layout (hydrology variant 18, road variant 0, layout
salt 1, at `f857ac7`), `transit_supports` failed. The Crown Loop ran 772 m without a support
(600 m allowed) over the corporate core's streets. Every evenly spaced spot and its 15% moves
fell on a lane, a sidewalk's clear path or a building that was not low, and no main span is
allowed there.

**On today's main the layout no longer fails.** Replayed through `citygen.build.replay`:
- `transit_supports` passes. The Crown Loop is 3,770 m on this layout, with no stretch over
  the longest span (its line takes out 20 buildings).
- It also passes with #153's profile switched off (single process, the sky tube preset back to
  no design grade, curves or fill). The dry run then leaves no gap at all, so the layout's
  streets and buildings have changed since `f857ac7` (M22, #143, #147, #126 and others).

The issue's point stands, though: a sky tube over dense streets whose every spot under it is
taken would fail the same way. Of its three options:
- **A cantilever bent beside the line, its column where a low building stood** (`_bent_room`,
  called from `_support_room`). Where the dry run still leaves a gap once the low buildings
  under the track are out:
  - at each spot a span apart along the gap, it takes the nearest spot beside the line for a
    cantilever bent's column, within `CANT_REACH_M` (15 m), as `_frame` searches it;
  - that spot must be one that only low removable buildings keep the column off (their tops
    2 m under the bent's arm), with the rest of the spot and the arm clear;
  - those buildings are taken out, as `_support_room` takes out the ones under the track.

  The real pass then finds the bent. This is the issue's first option, applied beside the
  line, since a line over a street has no building under it to take out.
- **Not a pylon in a raised road's median or a furniture zone.** A median of an at-grade
  avenue already takes a column where the line runs over it (`Keep.free` only keeps lanes'
  widths clear). A raised road's median is under its own deck. A 3.5 m pylon needs 5.3 m of
  sidewalk to leave the 1.8 m clear path, which the core's 2.5 to 5 m sidewalks do not have.
- **Not a new route.** The loop's route serves its stops; moving it would move every city's
  sky tubes.

It acts only where a city would otherwise fail `transit_supports`, so a city that builds
today does not move by it: in the seven cities with recorded hashes, every line takes out the
same buildings as on main. Test
`test_bent_room_takes_out_a_low_building_beside_the_line`: a sky tube 1.2 km over a street
whose lanes take every spot under it, low buildings 9 to 30 m off it. The dry run leaves it
without a support; with the fallback the supports leave no stretch over the longest span. The
test fails without the fallback.

## #109: two elevator walkways at an elevated platform's first end

`transit.Builder._elevated` adds an elevator at an elevated platform end whose sidewalk is
right under it (`d < 1`). It then always added the platform's own elevator at its first end,
so where that was the same end, the station had two elevator walkways at one point. The
platform's own elevator is now added only where its first end has none yet.

Stations with two elevators at one point on main (none now):
- Vesper Bay: `stn.the_stacks.3`;
- Delta Megacity: `stn.transit_nexus.5`;
- Greyhook: `stn.neckgate_2`;
- Saltreach Free Port: `stn.westreef_2`, `stn.crown_island`;
- Vesper Bay Pinned and Vesper Bay Stacks (the issue's: `stn.neon_strand_2`,
  `stn.corporate_core.2` and three more).

Vesper Bay Decks has none on main any more (the issue's `stn.neon_strand` and
`stn.vess_docks` were on an earlier layout). Test `test_one_elevator_a_platform_end`.

## Results

Every city with transit, built on the final code, one at a time:

| City | Checks | Try | Model |
|---|---|---|---|
| Vesper Bay | 107 | 1 | moves (#109) |
| Delta Megacity | 107 | 1 | moves (#109) |
| Nexus City | 107 | 1 | the same bytes |
| Greyhook | 107 | 2 | moves (#109) |
| Saltreach Free Port | 107 | 1 | moves (#109) |
| Cragmouth | 107 | 2 | the same bytes |
| Vesper Bay Decks | 112 | 1 | the same bytes |
| Vesper Bay Pinned | 107 | 2 | no recorded hash |
| Vesper Bay Stacks | 107 | 2 | no recorded hash |

Each builds on the same try as on main. The four that move differ from main's builds only in
their walkways and stations (one elevator walkway less at each station listed above); their
blockout plans keep their bytes, and so does the small test city.
