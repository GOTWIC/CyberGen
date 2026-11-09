# Crown Line fix (#143)

A fix between milestones, from issue #143 (an open item of M22): on M22's layouts the stack
demo `cities/vesper_bay_stacks` failed `transit_curves` on every layout it tried, its Crown
Line sky tube (Corporate Core, The Stacks, Highcrest, through towers) leaving its first
station on a 25 m hook.

## What was wrong

M19 picks each stop's station tower (its host) before the line is routed (`_hosts`): a
portal-sized tower in the stop's zone that a straight tube through its middle leaves with
240 m clear on both sides in some heading, the one whose clear heading lies closest to the
line's way first, then the nearest to the way. Each host is chosen alone, and the raster
route that follows does not know the clear headings (only M8c's Dubins track does).

On the demo's second layout (salt 1, the first one with no other failure) the Stacks stop
took `d02.lot.e1667s6.bld` (stable id; the stage's own is `d02.blk020.lot002.bld`), a tower
near the district's east edge that is clear only east to west, about 1.1 km off the chord
from Corporate Core to Highcrest. From Corporate Core's host (traced `path30`,
`d01.pin.path.w679s686`, clear 22.5 degrees off each axis) the raster legs to it and on to
Highcrest wound between the towers. Rerouted round the buildings in its corridor three
times, the line left `path30` west and turned north within 25 m (fitted radius 10 m, 25 m as
the check measures it). Neither `_straighter` nor M8c's Dubins track from stop to stop found
anything better (no clean Dubins track through both hosts' headings), so the hook stayed.
The first layout (salt 0) gave the Stacks stop no host at all and routed cleanly, but failed
`complexes` and `prop_support`.

## What changed

`citygen/transit.py`:

- `_fails`: what the transit checks will find of a routed line: (a leg without a route,
  stops missed, where it meets itself), a curve under the mode's radius measured as
  `transit_curves` measures it (`RADIUS_TOL`, now in `transit.py`, imported by the check),
  buildings in its corridor it cannot pass.
- `_rehost`: a sky tube through towers whose track is still too tight by that measure after
  every route is routed again with each tower `_hosts` chose (`Line.chosen`) barred in turn
  (`Line.no_hosts`: the stop takes its next tower, else a pylon). The best is kept (fewer
  flaws, then more stations in towers, then stop order; the first clean one ends the
  search), and the search runs again from it while it is still too tight (`REHOST_ROUNDS`,
  2). When no barred tower helps, the line stays as it was. The kept line notes which tower
  it barred.
- `_routed` is M19's route and its cut alternative (now `_route_cut`), then `_rehost` only
  for a line that would fail `transit_curves`. A line that passes takes exactly the path it
  took before.

## Result

Vesper Bay Stacks builds on its second full-city try (salt 1) with all 106 checks passing
(before: 9 tries, 105 of 106 at best). Barring `path30` moves the Corporate Core station
into traced `path24` (`d01.pin.path.w660s960`) on the island's east side, clear at 45 and
67.5 degrees. From there the tube runs straight across the water and over Vess Docks, takes
one 345 m curve north through The Stacks and ends at Highcrest (3.4 km; the Stacks host is
passed beside, so that station stands on a pylon, as on the first layout). Its supports:
longest span 487 m (600 m allowed).

Delta Megacity builds on its first full-city try, passes all 106 checks, never calls
`_rehost` and keeps its golden hash. Vesper Bay Pinned, with the same district and line,
builds on its second try as before with all 106 checks passing and the same report as M22's
line for line: `_rehost` ran once, on its first layout, whose Crown Line it routed without
`path30` too (that layout's failures 9 to 4: `complexes`, `junction_placement`,
`road_overlaps`, `walkway_building_clash`, none of them transit). A city whose lines all
pass on the try it keeps never reaches the new code, so no recorded hash moves.

`vesper_bay_stacks/`: the build report, `preview_transit.png`, the whole-city render and the
Corporate Core district render (the tube leaving its tower to the east).
