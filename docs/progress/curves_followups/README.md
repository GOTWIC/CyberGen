# Road curves follow-ups

Three open items of the road curves fix (#239, `docs/progress/fix_road_curves/README.md`,
"Open items"), fixed in one PR.

## 1. A junction's curb raised by a road beside it (issue #241)

**Found:** the hilly test city's regeneration of Old Quarter lays a bend junction anew,
`jn.e991n180` (a street and an alley, both level at 2.59 m from well before their cuts to the
node), whose outer curb the pavement map raised up to 3.7 cm over its legs, failing
`junction_levels`.

**Cause:** the junction's outline is laid against another road's sidewalk: the street
`rs.e1019n188` passes 0.14 m from the node with no node of its own there, and the junction's
carriageway face shares three vertices with that street's sidewalk band (`cll`). In
`pavement.Assembly.heights` the road loops run first and give every ribbon vertex its road's
height, so those three vertices took `rs.e1019n188`'s grade line there (2.625 to 2.627 m), and
the curb rule (`_along_ring`) then ran the junction's outer curb from its legs' 2.59 m up to
them and back.

**Fix** (`pavement.Assembly._foreign`): a junction's, corner pad's or bulb's vertex that only
roads not its own share (none of its legs or inner roads) takes the curb rule's height, not
that road's; ports keep their road's height (a port stays level across its road). The other
road's sidewalk takes the junction's height at those vertices (a 3.7 cm dip at three vertices
of a band edge; no check reads a band's own heights against its profile). The stats count
them (`foreign_curbs`). `test_hilly_regeneration_passes_every_check` is no longer xfail.

## 2. A crosswalk walked as a 49 m diagonal (Vesper Bay `cw.e637n26`)

**Cause:** not the crossing's fallback itself but its input. The street `rs.e669s6` turns by
a hair (1 cm over 90 m on the grid) at a vertex; GEOS offsets such a line on the turn's inner
side as **two parts meeting end to end**, and `junctions._offset` kept the longer part alone.
So the street's right sidewalk walkway and its right lane both stopped 40.1 m short of the
junction, the crosswalk's right end found no sidewalk within `ATTACH_MAX_M` and fell back to
the line between the leg's corners: a 49 m diagonal along the street.

The same fault cut lanes and sidewalks short in every city (GEOS splits of
`shapely.offset_curve`, mitre joins, at the sidewalks' and lanes' offsets):

| City (on main) | Sidewalk lines split | Lanes split | Lines short by over 0.5 m | Most lost |
|---|---|---|---|---|
| Vesper Bay | 21 | 17 | 22 | 52.9 m (`rs.e1623n412`'s right sidewalk) |
| Delta Megacity (16 Nov build) | 25 | 18 | 42 | 56.7 m (`rs.e1589n153`) |
| hilly test city | 18 | 17 | 28 | 72.1 m (`rs.w140n293`) |

**Fix** (`junctions._offset`, `_joined`): the parts GEOS returns meeting end to end (within
`JOIN_GAP_M` 1.5 cm) are joined again into one line, in an order of their own coordinates;
parts apart (the loop an offset of a tight curve leaves off) stay off as before. Lanes,
sidewalk lines and records, M14's deck ramp walkways take it.

**Check** (`network_checks.walk_on_roads`): a crossing's length on one road's carriageway faces
beyond that road's carriageway width (`carriageway_w`, curb to curb) now counts past its span,
so a crossing of one stretch run along the road fails `walkway_carriageway` (main's measure
took the longest stretch as the span, and a crossing of one stretch has nothing past it).
On main's Vesper Bay it finds `cw.e637n26`'s walkway 23.8 m past its span; on the 16 Nov
Delta a dead end's crossing (`rs.e1701n1213`, whose right sidewalk the same split cut 40 m
short) 10.1 m past.

## 3. Station stairs on crosswalks (Vesper Bay `stn.the_stacks.2`)

**Cause:** `transit.Builder.foot` took the nearest ground walkway of any kind, crosswalks and
crossings included, so a metro stair's top landed mid-crosswalk (`cw.e742n634`, split there),
and an elevated station's stair (`stn.vess_docks`) on an unmarked crossing; on the new
layouts another landed on a cluster's inner sidewalk where it runs along a highway crosswalk.

**Fix** (`Builder.foot`, `_foot_ok`, `_ways`): a foot is never on a crossing or crosswalk
walkway, nor on any walkway inside a crossing zone (`network_checks.crossing_zones`: each
crosswalk record's stripe, curb to curb, and each crossing walkway's band where it lies on a
road's carriageway face); it takes the nearest walkway point off them (a walkway's end within
5 cm taken), in every branch of the search (an elevator core in a building, a link round the
buildings). An elevated platform's own elevator at its first end (#109) that would stand on a
crossing goes to its last end where that has none and stands off them, else is left out where
another end has one.

**Check:** `walkway_carriageway` fails a station's stair or elevator whose ground foot stands
in a crossing zone (`station_feet_on_crossings`). On main it finds Vesper Bay's
`stn.the_stacks.2` and `stn.vess_docks`, and the 16 Nov Delta's `stn.west_quay`.

## Results

Every city the offsets move was built again (all of them), each passing every check (108,
113 with decks):

| City | Try it builds on (main) | Crossings past their span by 5 m | Station feet on crossings |
|---|---|---|---|
| Vesper Bay | 8, layout salt 7 (8, salt 7) | 0 (1 on main, `cw.e637n26`, 23.8 m) | 0 (2 on main) |
| Vesper Bay Stacks | 3, salt 2 (3, salt 2) | 0 | 0 |
| Delta Megacity | 3, salt 2 (5, salt 4) | 0 | 0 |
| Cragmouth | 2, road variant 1 salt 1 (same) | 0 | 0 |
| Nexus City, Saltreach Free Port | 1 (1) | 0 | 0 |
| Greyhook | 3, salt 2 (same) | 0 | 0 |
| Vesper Bay Decks | 18, road variant 3 salt 1 (same) | 0 | 0 |
| Vesper Bay Pinned | 2, salt 1 (same) | 0 | 0 |

Delta Megacity's third layout, which failed `junction_levels` on main, now passes, so it
builds there. The pinned demo's layout of main (try 2) put a platform's own elevator (#109's,
at its first end) on a crossing (`stn.neon_strand_2`), which the check found: the elevator now
goes to the platform's last end where that stands off the crossings, else is left out where
another end has one (`transit.Builder._elevated`).

Close-ups (walkways over the pavement map): `vesper_bay_cw_e637n26_main.png` and `_after.png`
(the right sidewalk whole, the crosswalk straight), `vesper_bay_the_stacks_2_main.png` and
`_after.png` (the stair's foot on the sidewalk).

Goldens: every sample's model and blockout plan, Cragmouth's and Vesper Bay Decks' (all move:
the lanes and sidewalk lines GEOS had split, and everything placed along them). Tests run
(touched modules and the regeneration tests): `tests/test_crossings.py`,
`tests/test_pavement.py`, `tests/test_transit.py`, `tests/test_edit.py`,
`tests/test_terrain.py` (the hilly regeneration passes every check, no longer xfail):
TESTS.

## Open items

- Centerlines that turn back on themselves (the road curves fix's corner rounding, or M2):
  Vesper Bay's alley `rs.e1410s1021` spikes 2.8 m back at a vertex, Cragmouth's street
  `rs.w980s676` turns 179 degrees, `rs.w1252s643` has a 1 cm segment between two 83 degree
  turns; their offsets stay split (the parts do not meet), so a lane or sidewalk of those
  roads is still short.
- A metro stair of `stn.the_stacks.2` runs 61 m in plan from its sidewalk foot to the
  concourse end (on main too).
- The bend junction `jn.e991n180` stands with its node against another road's sidewalk (a
  regeneration's new street ending beside a held one): the map now draws it level, the layout
  itself is unchanged.
