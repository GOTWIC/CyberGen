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
| archipelago_free_port | `e2135d8becbdd12e5600d051b79c05d741cdfb42b003bbaac2b36ff27fa013b7` |
| delta_megacity | `b34e4cc17013fa73d11ac47bab1f350aee67ddbfdba1c25e9c7928ba4ca91e82` |
| nexus_city | `250a633b745196ab1890dcbb75ef0efd3ac9339f72b2cacaeed90aa9b04217e7` |
| nyxllor | `abd43ef913358ed25ba44066952fe70e8fdd72c3e16cc6566eae45ff676b169b` |
| peninsula_city | `06c8c7ddeae8ee780f98526197b864f45c7a13598ed470bb0c6e73af75c91cee` |
| nyxllor_pinned (M7b demo, round 3 order) | `2421a4388e3c1426338ae8cb5e0db0961db94cca411088787c5235a016340eb3` |
| nyxllor_pinned_round2 (round 2 order) | `c9ece132e88e07f139e222698ccedde5a6f8293e1612c05ec74e1e77445a152b` |

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

Greyhook (peninsula) has no loop; its transit is unchanged.

### Per line

Each figure is the number of places where the line meets itself at the same level (the
`transit_self_crossing` rule), then the length.

| City | Line | Before | After |
|---|---|---|---|
| pinned, round 2 | Halo Line (loop) | 31, 8.3 km | 0, 6.6 km |
| pinned, round 3 | Halo Line (loop) | 13, 10.3 km | 0, 5.6 km |
| nyxllor | Halo Line (loop) | 17, 6.7 km | 0, 7.6 km |
| nyxllor | Crown Loop (sky tube loop) | 0, 3.7 km | 0, 4.7 km |
| delta_megacity | Skyline Loop, Delta Loop (sky tube loops) | 0, 4.7 and 4.8 km | 0, 4.7 and 4.4 km |
| nexus_city | Blue Line (metro loop) | 0, 4.3 km | 0, 4.1 km |
| archipelago_free_port | Island Hopper (monorail) | 3, 9.8 km | 0, 5.9 km |

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

## Coupling, what is left

Within one build, a line's track (in plan) does not depend on the other lines (a test checks
this). Its heights do see the buildings other lines remove from its corridor, which is a
physical dependence. Rounds 2 and 3 of the pinned demo differ only in the Halo Line's
route. Built now, the Spine Line, Launch Express and Crown Line come out identical in plan
and height.

The whole-city retry is still there. I tried stopping transit-only failures from triggering
a retry (in `build_city`), but delta_megacity and nyxllor pass only thanks to that retry.
Their maglev lines fail `transit_curves` on the first layout: nyxllor's maglev turns back
at Corporate Core (a spec matter, by M5's own rule), and delta's maglev has a 130 m curve.
So the change went back. A spec edit that makes any line fail a check can still move every
line through a retry.

## Open items

- **Retry coupling.** Options: pin the previous round's layout salt and road variant in the
  art-direction loop (`citygen review`), or retry only the transit stage for transit-only
  failures once the maglev lines pass on their first layout.
- **Maglev curves.** delta_megacity's Maglev Line has a 130 m curve on its first layout. The
  retry finds a layout that passes, as in M7b.
- **A road-mode loop off the roads.** When the roads cannot make a ring (the pinned Halo
  Line), the ring runs across blocks and the river on its own viaducts. More buildings come
  out of its corridor than along the avenues.
- **The guide ring's stops.** A loop's station sits where the ring passes through the
  district, often near its edge (the round 3 Old Town station sits on the river bank).
- **Open lines.** Greyhook's East Shore Line (unchanged) still winds round Neckgate and Hook
  Spaceport. Open lines get the keep-off rule and the winding check, but no ring placement.
- **Other seeds.** M8a's sweep found transit failures at other seeds (Delta Loop radius and
  service, nyxllor Halo radius at seed 1999, maglev and sky tube radii). I did not rerun
  that sweep on this branch.
- **Transit time.** The transit stage takes longer on cities with road-mode loops: about
  25 to 50 s on the pinned demo, against about 7 s before, because those loops are routed
  both on and off the roads.

## Files

`<city>/` holds the previews (`preview_transit.png` first), `before_transit.png`,
`report.txt` and `report.json`, `trace.json` and, for the five samples and the demo,
`blockout_report.txt` and the blockout renders. The 8K renders are `render_iso_city.jpg` for
every blockout city, plus `nyxllor_pinned/render_iso_d01.jpg` and `render_street_4.jpg` for
delta_megacity and nyxllor. Work in progress: `wip/`.
