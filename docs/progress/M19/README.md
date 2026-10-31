# M19: transit structures

From the first run-through (`docs/run_through_1.md`): supports that stood beside the line
instead of under it, long unsupported gaps (971 m on a sky tube over Delta Megacity's river),
sky tubes through towers that hosted no station, and lines too close to the roads, buildings
and each other. Spec: `docs/citygen_scope.md`, section 12, M19.

| Delta Megacity: transit (8K renders below) | Vesper Bay: transit |
|---|---|
| <img src="delta_megacity/preview_transit.png" width="420"> | <img src="vesper_bay/preview_transit.png" width="420"> |

| Sky tube masts with their stays (Delta Megacity, 8K) | Monorail on portal frames over a raised road (8K) |
|---|---|
| <img src="delta_megacity/render_sky_tube_masts.jpg" width="420"> | <img src="delta_megacity/render_monorail_frames.jpg" width="420"> |

## What changed

- **Supports under the structure.** Each line's supports are spaced evenly between its fixed
  points (an open line's ends, each platform's ends) and what carries it (a tower it passes
  through, a transit nexus platform, a sky station's elevator core, the ground), at the
  mode's span: elevated rail 30 m (longest 45), monorail 25 (40), maglev 50 (80), sky tube
  420 (600). Each moves at most 15% of its span to free ground and stands as, in turn:
  - a column under the line (its middle within 0.01 m of it in every sample);
  - a pier in the water, clear of the navigable channel (down the middle of a river or channel,
    at most half its width and 40 m wide, 120 m for a sea channel; the open sea has none);
  - a portal frame: a column each side within 30 m and a cap beam under the deck (a new
    structure kind, `beam`);
  - a cantilever bent: one column within 15 m, its arm reaching past the deck.
  Any gap still over the longest span is filled wherever a support stands; before the
  stations, a dry run takes out the low buildings that alone keep a support off a gap.
- **Sky tube masts.** Every sky tube pylon is a cable-stayed mast: two legs either side of the
  tube rising 12% of its longer span over it, stays fanned to 40% of each span.
- **Main spans.** Where nothing may stand, a navigable channel or a raised road (an
  interchange), a span may pass the longest, cable-stayed, up to 300 m (elevated rail), 250
  (monorail), 300 (maglev). Each line lists its truss and cable spans (`attrs.spans`).
- **Portals only at stations.** A sky tube through towers picks each stop's host tower
  before its route: a portal-sized tower in the stop's zone that a straight tube leaves with
  240 m clear on both sides (an edge tower of a dense core), along the line's way. Only hosts
  take a portal; every other tower is climbed over or gone round. Where neither works (Vesper
  Bay's Crown Loop, whose Corporate Core and The Stacks are walls of 130 to 216 m towers), the
  tube takes the removable towers in its way out, as elevated lines take out what they cannot
  clear. Lines are routed apart, so where another line takes out a tower a tube chose as a
  host (Delta's Maglev Line through the Skyline Loop's Corporate Core tower, on main's
  layouts), the tube is routed again with those towers barred as hosts.
- **Clearances.** 6 m from buildings in plan (2 m before), or under the line by its
  clearance; the roof items a line passes too close over go. 8 m over a road or sidewalk
  under the deck and its cap beams (5.5 m before); 6.5 m over a raised road's deck (with room
  for a frame's cap beam over it) and between two lines; a line passing under a road deck
  keeps 6.5 m under it for its trains. Default altitudes: elevated rail 14 to 20 m (10 to
  16), monorail 16 to 26 m (12 to 22). Lines are profiled in order: each passes over or under
  the lines before it.
- **Checks.** `transit_supports` (a lone column within 0.5 m of its line, a frame's beam under
  it at the deck's underside, piers clear of the channel, no span over the longest but a
  main span, an end overhanging half of it at most) and `transit_clearance` (in 3D along the
  line: building masses and roof items, a portal only with a station in it, other lines'
  tracks, platforms, supports and canopies, the roads, raised decks, navigable water).
- **Blockout and stage 2.** Cap beams, masts with stays, pier footings; AG7 draws a beam as a
  plain box until AG14 draws the frames.

## Delta Megacity, before and after

Before is main with M17 and M21 (road repair, cyberpunk massing) and without M19; now is M19
on that main. Measured on the built models (`citygen.transit_checks.check_supports`; a frame
or a cantilever counts as one support, its columns not as columns off the line):

| Line | Supports before | Now | A column off its line, before | Now | Longest span, before | Now |
|---|---|---|---|---|---|---|
| Maglev Line | 33 | 53 (34 columns, 6 piers, 7 frames, 6 cantilevers) | 14.3 m (1 over 2 m) | 0.01 m | 377 m | 78 m |
| Skyline Loop (sky tube) | 13 | 11 (8 masts, 1 pier, 2 cantilevers) | 2.2 m (1) | 0.01 m | 671 m | 489 m |
| Delta Loop (sky tube) | 42 | 12 (7 masts, 3 piers, 1 frame, 1 cantilever) | 9.5 m (2) | 0.01 m | 975 m | 505 m |
| Waterfront Monorail | 141 | 196 (93 columns, 20 piers, 41 frames, 42 cantilevers) | 15.6 m (27) | 0.01 m | 400 m | 102 m (a cable span) |

The run-through's script (`measure_runthrough.py`) counts every column, so on the new model
it reports the frames' and cantilevers' columns as off the line (by design: they stand at the
curbs under their beam): its largest gaps go from 360, 720, 975 and 400 m to 162, 503, 506
and 102 m, its columns over 2 m off the line from 1, 1, 2 and 27 to 19, 0, 3 and 104.

## Every sample

All checks pass on every sample (92; 97 on Vesper Bay Decks). Full-city tries, main (M21 on
M17) then M19 on it:

| City | Tries before | Now | Longest spans now (per line) |
|---|---|---|---|
| Delta Megacity | 1 | 1 | maglev 78, sky tubes 489 and 505, monorail 102 (cable) |
| Vesper Bay | 1 | 1 | elevated rail 169 (cable), maglev 78, sky tube 560 |
| Nexus City | 2 | 1 | maglev 58, elevated rail 62 (cable), sky tube 336 |
| Greyhook (peninsula_city) | 2 | 2 | sky tube 375, elevated rail 50 |
| Saltreach Free Port (archipelago) | 1 | 1 | monorail 102 (cable), maglev 57 |
| Vesper Bay Pinned | 2 | 2 | elevated rail 61, maglev 57, sky tube 393 |
| Vesper Bay Stacks | 2 | 2 | elevated rail 59, maglev 57, sky tube 453 |
| Vesper Bay Decks | 4 | 2 | elevated rail 147 (cable), maglev 58, sky tube 479 |
| Cragmouth (a metro only) | 2 | 2 (its model gains only its line's empty `attrs.spans`) | |

## Open items

- **Longer sky loops.** Keeping off every tower that hosts no station makes some sky tube
  loops longer and less round: Delta's Skyline Loop is now a 4.8 km figure-eight (a 2.6 km
  ring on main, through 13 towers without a station), Vesper Bay's Crown Loop a 6.4 km
  figure-eight (2.3 km on main). Greyhook's Spine Tube is 1.5 km as on main, Nexus City's
  Spire Line 0.8 km (1.2).
- **Two lines along one street** stack 8 m apart and the upper one's columns cannot stand
  beside the lower deck; where they share a stop for long, a frame wide enough to straddle
  both is needed (seen on the test city, not on the samples).
- **Supports in a regenerated district** (`citygen build --district`) are planned again along
  the whole line; outside the district they come back where they were when nothing near them
  changed, but a seam can shift a few supports next to it. Regenerating Delta's Midtown (the
  Skyline Loop's host tower stood in it on M15's layout) passed all 86 checks.
- AG14 draws the frames, masts, piers, trusses and cable spans as assets; AG7 draws beams as
  plain boxes and masts and piers as columns until then.
