# M8b: transit loops

M8b polishes how citygen routes transit loops (M5, `citygen/transit.py`). A loop line is now
one simple closed ring through its stops in route order. Its stations follow that order, and
a line's track no longer depends on the other lines. The new check `transit_self_crossing`
(66 checks in all) and red crosses on `preview_transit.png` show any place where a line
meets itself.

Every build below passes all 66 checks. Each `city_model.json` is byte-identical on the M4
Mac (arm64) and on x86_64 Linux (docker, `linux/amd64`, `CITYGEN_WORKERS=4`):

| City | sha256 of `city_model.json` (both machines) |
|---|---|
| archipelago_free_port | `8b0d4841ba5de81b65129cd10b8958c3c7fc05a24dbcbbc18d9c21d08124bc40` |
| delta_megacity | `fabc65e73cf2389cddd80b6b83a9398498da24bd7bb90e68223c7e247ae93e5f` |
| nexus_city | `621756ff6d71ed4109eb37e2b79cdde04ef2dc20bec21d802bc81e5589bda410` |
| nyxllor | `70bc3e8353f426be20bc219ff7394deae753769a9f318e01315c460d59789fb3` |
| peninsula_city | `e6ebad53f3dc66f0dca74a6dc3e7e60017b5d9cabef0e224bce02091af00b774` |
| nyxllor_pinned (M7b demo, round 3 order) | `d5c9335841f68954dff464e6419ba4b7b04841c729bb367a80a323d8df79e7d4` |
| nyxllor_pinned_round1 (round 1 maglev) | `e3bcc9d140efa5ce9513b1e0e6cfdcc186a0dc2de81aed7a009ea2a716576a63` |
| nyxllor_pinned_round2 (round 2 order) | `e29f8fea3cfc81b4a7cadc2b8891bd4d86fa24c294f5c598845ae56f1dabfa6b` |

The PR has two parts: the loop rings (first review) and a polish round after it (fast lines
on their first layout, transit time, Greyhook's East Shore Line), described in
[Polish round](#polish-round). The images and figures below are from the final code.

## Before and after

In each pair, "before" is the same spec built with the code before M8b (commit `510dc70`,
which reproduces the M7b golden hashes). The "before" maps are in each folder as
`before_transit.png`.

### The pinned demo, Halo Line in its round 2 order

Neon Strand, The Stacks, Highcrest, Old Town, Neon Strand
(`nyxllor_pinned_round2/city_spec.json`):

| Before: doubles back through The Stacks, meets itself in 31 places | After: one ring, stations in route order |
|---|---|
| <img src="nyxllor_pinned_round2/before_transit.png" width="420"> | <img src="nyxllor_pinned_round2/preview_transit.png" width="420"> |

### The pinned demo, round 3 order

Neon Strand, Highcrest, Old Town, The Stacks, Neon Strand (the M7b demo spec):

| Before: closes, but winds round Highcrest and crosses itself (13 places) | After |
|---|---|
| <img src="nyxllor_pinned/before_transit.png" width="420"> | <img src="nyxllor_pinned/preview_transit.png" width="420"> |

### Nyxllor sample

Its Halo Line is in the round 2 order:

| Before: 17 places | After |
|---|---|
| <img src="nyxllor/before_transit.png" width="420"> | <img src="nyxllor/preview_transit.png" width="420"> |

### Delta Megacity, Nexus City and Saltreach (archipelago)

| Delta Megacity before | Delta Megacity after |
|---|---|
| <img src="delta_megacity/before_transit.png" width="420"> | <img src="delta_megacity/preview_transit.png" width="420"> |

| Nexus City before | Nexus City after |
|---|---|
| <img src="nexus_city/before_transit.png" width="420"> | <img src="nexus_city/preview_transit.png" width="420"> |

| Saltreach before: Lumen Key as a spur, back over the same bridge | Saltreach after |
|---|---|
| <img src="archipelago_free_port/before_transit.png" width="420"> | <img src="archipelago_free_port/preview_transit.png" width="420"> |

Greyhook (peninsula) has no loop. Its open lines changed in the polish round (see below).

### Per line

Each figure is the number of places where the line meets itself at the same level (the
`transit_self_crossing` rule), then the length.

| City | Line | Before | After |
|---|---|---|---|
| pinned, round 2 | Halo Line (loop) | 31, 8.3 km | 0, 5.0 km |
| pinned, round 3 | Halo Line (loop) | 13, 10.3 km | 0, 6.3 km |
| nyxllor | Halo Line (loop) | 17, 6.7 km | 0, 7.6 km |
| nyxllor | Crown Loop (sky tube loop) | 0, 3.7 km | 0, 4.7 km |
| delta_megacity | Skyline Loop, Delta Loop (sky tube loops) | 0, 4.7 and 4.8 km | 0, 4.9 and 4.3 km |
| nexus_city | Blue Line (metro loop) | 0, 4.3 km | 0, 4.1 km |
| archipelago_free_port | Island Hopper (monorail) | 3, 9.8 km | 0, 5.9 km |
| peninsula_city | East Shore Line (elevated rail, open) | 0, 5.3 km | 0, 3.9 km |
| peninsula_city | Spine Tube (sky tube, open) | 0, 2.8 km | 0, 2.2 km |

In M7b, a loop's last stop shared the vertex of its first, so the stops of the delta and
nexus loops read as out of order. In M8b a loop's track starts at its first stop and ends
back there.

## Causes

1. **Stops at the district middles.** A district stop of a loop sat at the avenue junction
   nearest its district's middle. (Lines move a middle stop toward the chord between its
   neighbors, but loops were left out, because that chord crosses the loop.) Taken in the
   round 2 order, those middles make a polygon that crosses itself: The Stacks' middle lies
   south, outside the turn from Neon Strand to Highcrest.
2. **Legs that turn back.** Each leg ran on the road graph from one exact junction to the
   next, and a train may not turn more than 120 degrees at a node. A stop at a road's end
   (The Stacks' junction ended a road; at Highcrest a leg arrived on a 17 m link off an
   overpass) forced the next leg round the blocks: 2.2 to 6.5 km legs for 1 km chords. A
   leg could run along or across the line's own earlier legs. Its only penalty was 2x the
   cost on a reused road edge.
3. **One bridge both ways.** On the pinned map the road graph crosses the river between the
   north and south landmasses in one place. A road-only ring had to use it twice.
4. **Curves cutting the spurs.** The arc fitting removes a vertex where the route turns back.
   It cut whole excursions, the stop included, and left the track crossing itself.
5. **Stations by distance alone.** Each stop's station was the track vertex nearest the stop
   point, so in a district the line passes twice (The Stacks), stations came out of route
   order (vertices `[481, 136, 505, 960, 481]` in round 2). With them, the mid stations
   between stops went wrong too.
6. **Coupled lines: whole-city retries.** `build_city` draws the whole city again (a new
   layout salt, then the next road network) whenever the full city fails any check. Round
   1's maglev (`east_exit`, Corporate Core, Launch Key) turns back and failed
   `transit_curves` and `transit_altitude`, so round 1 kept retrying. It ended on a
   different layout from round 2, with different buildings, so every line moved. Within one
   build, the lines never depended on each other's tracks. (Both rounds also fail
   `level_continuity` on their first layout, `rs01479` at 0.16 m, an M8a matter, so both
   retry once.)

## Fixes (in `citygen/transit.py`)

- **Ring placement (`_loop_points`).** A loop's district stops move to junctions of their
  districts that come in route order around the middle of the stops, within one turn. Such
  a star-shaped polygon is simple. A dynamic program over one junction per 10 degree sector
  tries both ways round and keeps the stops near one circle and evenly spaced. A stop that
  is a nexus platform, site or place stays put.
- **Stops deep enough for the curves (`_deepen`).** Where the 1.15 r_min curve at a stop's
  corner would cut out of its district (it cuts the corner by
  $r\,(1/\cos(\theta/2) - 1)$ for a turn $\theta$), the stop moves to a junction where the
  apex stays 30 m inside. A loop routed off the roads that still misses a stop tries again
  with that stop 60 m deeper (up to three tries).
- **Legs keep off the line (`_keep_off`).** Every leg keeps off the line's earlier legs,
  except within 60 m of its own start and, when it closes a loop, of the loop's start. On
  the roads, such edges are left out (`RoadGraph.touching`). On the raster, such cells are
  forbidden.
- **Road legs end near the stop (`RoadGraph.targets`).** A road leg may end at any junction
  within 150 m of a district stop, inside the district, and the next leg starts there. A
  loop's last leg must arrive in a direction its first leg can continue from.
- **Off the roads where needed.** A road leg the roads cannot keep off the line (one bridge
  both ways) runs on the raster instead, with its own viaduct and avenues still cheapest.
  So does a leg that winds round the blocks (longer than 1.5 times its chord plus 300 m)
  when the raster leg is 1.3 times shorter. A road-mode loop is also routed fully off the
  roads (`_off_roads`). That route is kept when it serves more stops or meets itself less,
  or when the road ring is 1.35 times longer.
- **Guide ring (`_guide_loop`).** A loop off the roads is also drawn along its guide ring:
  the ordered stop polygon with arcs, with waypoints every 120 m on the raster. The better
  of the two is kept, judged in order by stops served in order, places where it meets
  itself, then curves too tight. The hull fallback now only runs for a curve the check
  would fail, or for a loop that meets itself. It must keep the route's direction round,
  and it widens from 1.1 to 1.25 r_min when still tight.
- **Stations in route order (`ordered_stops`).** A loop's track starts at its first stop.
  Each stop's station is the nearest vertex in its district after the previous stop's.
- **Heights round the seam (`_graded`).** A loop's height envelopes are graded round the
  seam, so the track has no step where it closes. The altitude check grades the same way.
- **Station names.** A mid station that lands outside every district (a bank between two
  river arms) takes the nearest district's name instead of the line's.
- **Check `transit_self_crossing`** (in `transit_checks.py`). Two parts of a line more than
  100 m apart along it stay its structure width apart in plan, or pass at least 5.5 m plus
  the structure apart in height. A loop closes, and its stop vertices come in route order.
- **Preview.** A red cross marks a place where a line meets itself, and a loop's stops are
  numbered in route order.
- **Tests** (`tests/test_transit.py`):
  - a four-stop elevated loop in the test city (Harbor, Old Quarter, Uptown, Core), checked
    for one simple ring, stations in order inside their districts and no step at the seam;
  - failing cases for the new check (a line back along itself, a loop left open, stations
    reversed) and a passing case (12 m over itself);
  - each line built alone gives the same track as with all lines;
  - `self_meets` on a figure eight and a circle, and the seam grading.

The determinism rules hold. Every angle comes from `dmath`. Junction and edge sets are only
used for membership tests, tree hits are sorted, and no GEOS output order reaches a
decision (the ULP noise test still passes).

## Polish round

After the first review, three items from the open list: fast lines that pass on the first
layout (so a spec edit to one line no longer retries the whole city), the transit stage's
time, and Greyhook's East Shore Line. All in `citygen/transit.py`; `build.py` is unchanged.

### Fast lines on their first layout

In the first review, delta_megacity's maglev failed on its first layout and passed only
through `build_city`'s whole-city retry, and round 1 of the pinned demo (its maglev ordered
`east_exit`, Corporate Core, Launch Key) failed `transit_curves` and `transit_altitude` and
moved to another layout, so every line in it moved. Causes:

- **A middle stop off the way.** A maglev's middle stop sat at the avenue junction of its
  district nearest the chord between its neighbors, even where the 575 m curve there cut
  out of the district (delta's Midtown stop, 250 m inset). The raster route then had to
  bend through it and the fitting kept a 130 m curve.
- **Turning back at a stop.** Where the stops make a sharp turn (round 1: in from the east,
  out to Launch Key in the north-west), no junction of Corporate Core leaves room for the
  curve inside the district.

Fixes:

- **`_fast_point`.** For a fast line (maglev, sky tube: r_min at least 300 m) a middle stop
  takes the junction nearest the chord where the curve's apex stays inside the district
  (`_apex_in`) and the curve is clear. Failing that, it takes a corner on a 60 m grid within
  two radii of the district, nearest the way, whose guide (the straight runs and the
  curve) is clear and runs a station length 40 m inside the district; the station goes in
  the middle of that stretch, and the line turns beside the district (over the water, say).
- **`_guide_line`.** A fast open line is also drawn along its guide line: the stops with
  arcs at those corners, densified, split at the stations, with waypoints every 120 m on
  the raster. Its stations are pinned so the fitting cannot cut them away. It is kept when
  better by `_line_key` (stops in order, places where it meets itself, curves too tight,
  corridor conflicts); the report notes "drawn along its stops with 500 m curves".

| City | Line | Base code (`510dc70`) | First review | Now |
|---|---|---|---|---|
| delta_megacity | Maglev Line | city passes on layout salt 2 | 130 m curve on layout 1; passes on salt 1 | 539 m on layout 1 |
| nyxllor | Launch Express | city passes on layout salt 3 | 508 m on layout 1 | 611 m on layout 1 |
| pinned, round 1 | Launch Express | 548 m, but the city passes on layout salt 4 (Halo Line meets itself in 6 places) | fails `transit_curves` and `transit_altitude`; city moves to another layout | 550 m, same layout as rounds 2 and 3 |

No sample city retries for transit now. delta_megacity, nyxllor and the three other samples
build on their first layout. The pinned demo still retries once, in all three rounds, for
`level_continuity` (`rs01479` at 0.16 m, M8a's area), so all three end on the same layout.

**Rounds 1 and 2 of the pinned demo now differ only in the maglev.** Their roads, districts,
lots, buildings and the Halo, Spine and Crown lines are identical, in plan and in height.
What differs is Launch Express itself (track, its two stations, their walkways and
supports), the 6 buildings its corridor removes (and their green areas, plants and props),
the corridor marks on 6 lots, and the walkway ids listed on three Crown Line stations (the
walkways are numbered in one sequence).

| Round 1: maglev `east_exit`, Corporate Core, Launch Key | Round 2 |
|---|---|
| <img src="nyxllor_pinned_round1/preview_transit.png" width="420"> | <img src="nyxllor_pinned_round2/preview_transit.png" width="420"> |

Before, round 1 for comparison: `nyxllor_pinned_round1/before_transit.png`.

### Transit stage time

Profiled on the pickled models just before transit (same layout for each column), seconds
for `transit.build`:

| City | Base code (`510dc70`) | First review | Now |
|---|---|---|---|
| pinned, round 2 | 6.3 | 34.6 | 8.6 |
| pinned, round 1 (layout 1) | 48.7 | 79.6 | 9.5 |
| delta_megacity | 22.4 | 22.6 | 7.1 |
| nyxllor | 53.3 | 66.7 | 9.1 |
| peninsula_city | 2.8 | 6.3 | 2.9 |
| archipelago_free_port | 2.0 | 6.5 | 3.5 |

Where the time went: the raster A* (`search`). Its states were tuples in dicts, and its
heuristic, the straight distance times the cheapest cell cost, is far below the real cost
over built-up ground, so a long leg expanded most of the map. A leg whose end could not be
reached (keep-off cells closing it in) searched every state before giving up. The first
review's loops search many such legs: on and off the roads, the guide ring, the hull and
the deeper stops.

The search now uses integer states (flat arrays for a long search, a sparse table for a
short one); over 600 m its heuristic is the exact turn-free cost to go (`_togo`, a numpy
relaxation, admissible since turns only add cost), and after 20000 steps a flood fill
(`reachable`) stops it at once when the end cannot be reached. The paths have the same
cost as before (`test_search_cost_to_go`); only ties may go another way.

The 8.6 s on the pinned demo against 6.3 s before: about 1.5 s builds the context
(rasters, road graph), about 0.3 s per long search computes `_togo`, and the rest is the
loop's extra routes (off the roads, along the guide ring) that the first part of M8b added.
Those are what draw a simple ring, so I kept them.

### Greyhook's East Shore Line

The line wound round the south of the peninsula because its end stop, Hook Spaceport, sat
at the site's middle, inside the terminal, which the line cannot cross: the route went
round the site to reach a point it could not get to. A line that ends at a megasite now ends
where the site's zone begins (`_site_point`: the passable cell 30 m inside the zone nearest
the neighbor stop; on the roads, `RoadGraph.targets` takes any major junction in that
zone). East Shore Line: 5.3 to 3.9 km; Spine Tube, which also ends there: 2.8 to 2.2 km.

The turn round Neckgate stays: Neckgate is the transit nexus, and its platform is at the
east end of the neck, so a line from Wallgate Heights to Eastside Docks has to go east to it
and come back. That is the spec's order, not the routing.

## Coupling, what is left

Within one build, a line's track (in plan) does not depend on the other lines (a test checks
this). Its heights do see the buildings other lines remove from its corridor, which is a
physical dependence. A spec edit that makes any line fail a check still moves every line,
through the whole-city retry; with every sample line now passing on its first layout, that
no longer happens for the sample specs and the demo rounds.

## Open items

- **Retry coupling, in general.** A future spec whose line fails a check still retries the
  whole city. Options: pin the previous round's layout salt and road variant in the
  art-direction loop (`citygen review`), or retry only the transit stage for transit-only
  failures (now possible without breaking the samples).
- **A road-mode loop off the roads.** When the roads cannot make a ring (the pinned Halo
  Line), the ring runs across blocks and the river on its own viaducts. More buildings come
  out of its corridor than along the avenues.
- **The guide ring's stops.** A loop's station sits where the ring passes through the
  district, often near its edge.
- **A fast line's corner beside a district.** Round 1's Corporate Core maglev station is at
  the island's north-east edge, where the guide corner leaves room for the curve.
- **Other seeds.** M8a's sweep found transit failures at other seeds (Delta Loop radius and
  service, nyxllor Halo radius at seed 1999, maglev and sky tube radii). I did not rerun
  that sweep on this branch.

## Files

`<city>/` holds the previews (`preview_transit.png` first), `before_transit.png`,
`report.txt` and `report.json`, `trace.json` (and `city_spec.json` for the two extra demo
rounds) and, for the five samples and the demo,
`blockout_report.txt` and the blockout renders. The 8K renders are `render_iso_city.jpg` for
every blockout city, plus `nyxllor_pinned/render_iso_d01.jpg` and `render_street_4.jpg` for
delta_megacity and nyxllor. Work in progress: `wip/`.
