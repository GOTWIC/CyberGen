# Stage 1 fixes (after M15)

Three generator items left open by M13, M14 and M15, fixed together:

1. **District regeneration on Cragmouth.** `citygen build SPEC OUT --district NAME` failed
   checks for five of Cragmouth's six districts (M13's open item). Now every district
   regenerates on its first seed with all 86 checks passing, and every road outside it comes
   back as it was in five of the six.
2. **Junction corners on a hill.** M15's walk on Cragmouth was held 4 m short at a corner whose
   two sidewalks stood 1.8 m apart. A junction of local roads is now level out to its corners,
   so its roads meet at one height there.
3. **Deck streets without a district.** M14's deck streets and ramps had empty `district_ids`,
   so the blockout joined them as `city.deck_road.<tile>` and `city.deck_sidewalk.<tile>`
   with no district. They now carry it: `d03.deck_road.<tile>`, `d03.deck_sidewalk.<tile>`.

Vesper Bay and every other city without terrain or decks builds byte for byte as before.
Cragmouth and Vesper Bay Decks have new goldens (`tests/data/golden_hashes.json`, see its
`about`).

## 1. District regeneration (M10's frame)

M10 rebuilds the whole city's streets under a `streets.Frame` and trusts that every district
other than the regenerated one comes back as it was. Regenerating each Cragmouth district on
main found five ways that trust fails; each fix applies only in a regeneration.

| What changed a held road | Fix |
|---|---|
| **A district laid after the regenerated one** (spec order) laid its streets against the district's *new* streets: a grid piece trimmed where a new street ran alongside, an end joined to a new street. Hollow came back with other streets when Ridgeback or Crown Heights was regenerated, Low Harbor's two neighbors when it was. | `streets._Ghosts`: at the district's turn its *old* fill is replayed on a copy of the lines (its old spec entry, no frame). While the districts after it are laid again, the lines before it look as the old fill left them, its new streets are hidden and its old ones stand in. Then the new streets come back, what the later districts added to earlier lines is kept, and the old streets go. Every district other than the regenerated one is laid without the frame, exactly as in the old city. |
| **The shared frame** (frontage streets, promenades, quay roads, boundary streets) was laid with the regenerated district's frame streets snapped to old nodes, which moved a neighbor's cells. | The frame is laid as in the old city, unless the district's archetype changed. |
| **A held road joined a new street in a later pass**, or was split where the old city had no node: a dead end run on to a new street, a link onto a held road at a fresh point, a highway access for a cut-off group (Hollow: Low Harbor's frontage street onto the spine highway). | In the later passes a held street never joins a street the district laid anew (its frame streets are as they were). A held group's link starts only at an old node or vertex and lands on a held road only at one. A highway access is made only at an old node. An avenue's dead end keeps the held link the old city had, even where a new street now ends beside it (Ridgeback: the link onto Low Harbor's reserve ring). |
| **A group of held roads that reached the network only through the district's old streets** (a frontage street, a boundary street and a connector by Hollow's border) was left cut off, or was joined at a 33 degree junction, or was made pedestrian before `_reconnect` ran. | `_reconnect` also runs before the clean-up, on the vehicle network (a held street that cars could reach stays a street). Its link meets the roads at both ends at the district's junction angle, shortest first, trying points along each nearby new street, not only the nearest one. A new street that meets an old node where a held road bends makes the angle with both of its legs. |
| **The splice:** a neighbor's seam block that the new build replaced was in no territory; a cut-off walkway group's link was dropped; a sign stayed on a facade whose building the new build replaced. | Each territory holds its district's blocks as spliced (a new block goes to the turf of the nearest seed, as `gameplay` assigns them). Walkway-island links come from the new build. A sign slot that goes takes its sign with it. |

Two things a regeneration now does that the old city did not need:

- **No new junction on an old bored stretch.** Ridgeback's new grid met the chord avenue where
  the old city bored through the ridge. That left two 31 to 33 m pieces, too short to bore
  (40 m), as 22 to 24 m open cuts. In a regeneration the district's new streets keep off the
  old city's bored stretches and 20 m past their ends (`Frame.bored_spans`, `Line.bored`),
  as every street keeps off a bridge or an M9 tunnel.
- **A layout that fails a check is drawn again.** When the regeneration picks the seed
  itself, a failing layout is drawn again with the next derived seed, up to 4 seeds, and the
  try with the fewest failures wins (as `build_city` draws a failing city's local layout
  again). No Cragmouth district needs it now. Before the bore rule, Ridgeback's four seeds
  all failed `cut_fill`.

Regenerating every district of Cragmouth (`citygen build cities/cragmouth/city_spec.json OUT
--base BUILD --district NAME`, six at once on the M4 Mac, reports and two diff maps in
[`regenerated/`](regenerated/)):

| District | Held roads back as they were | Outside the district changed (through references) | Checks |
|---|---|---|---|
| Low Harbor | 3158 of 3158 | 579 (228) | all 86 pass |
| Lantern Steps | 2308 of 2309 | 22627 (21839) | all 86 pass |
| Crown Heights | 3076 of 3076 | 1070 (280) | all 86 pass |
| Old Quarter | 1674 of 1674 | 15012 (14078) | all 86 pass |
| Ridgeback | 3038 of 3038 | 1199 (237) | all 86 pass |
| Hollow | 2939 of 2939 | 1665 (307) | all 86 pass |

Each took 86 to 92 s (six at once; one alone takes about 55 s). On M13's code the same table
read 12, 14, 3, 17 and 4 failing checks for all but the Old Quarter.

- **Lantern Steps' one road:** an Old Quarter lane that, in the old city, a later pass ran on
  27 m onto a lane of Lantern Steps' old layout. That lane is gone, so the held lane stops at
  its own end. The walkways beyond it reach the network through the new build's walkway-island
  link.
- **The large through-reference counts** for Lantern Steps and the Old Quarter are M3 drawing
  each lot by its index in its district's lot list (M13's open item): a seam block of a
  neighbor that splits a meter differently reseeds that neighbor's buildings. Every check
  passes; keying the draws on stable lot ids would move every city's buildings, so it is left
  as an open item.

## 2. Junction corners on a hill (M13)

The step at M15's corner (-55, -7) was not a step at the node: there `rs.w15n19` and
`rs.w109n31` both meet at 55.14 m. Every road starts climbing at its own grade at its node,
and a sidewalk follows its own road's grade line. So the two sidewalks of a corner, which meet
at one point about 10 m out on each leg, stood at 54.55 and 56.34 m. On Cragmouth 1223 of
3556 sidewalk corners stepped more than 0.45 m (a step a walking character can climb), the
worst by 4.1 m.

`terrain.grade` now takes each junction's run on every leg: along the leg's centerline out
to the edge of the junction polygon, past its curb and sidewalk corners (`junctions.cutbacks`,
`run_along`, `Local.cuts`; longer than the cut where a leg bends inside the junction), at
most 0.45 of the leg (a short leg between two junctions keeps the rest to climb). At a
junction of local roads it holds the node's height over that run, so the roads meet at one height at the corners and the grade is taken up
between junctions. At M15's corner both legs are level at 54.87 m out to 14.6 m.

| Cragmouth | Before | Level local junctions | Every junction level (rejected) |
|---|---|---|---|
| deepest cut, highest fill | 18.7 m, 18.7 m | 18.7 m, 18.7 m | 24.1 m, 24.1 m (`cut_fill` fails) |
| retaining walls | 1280, 84 km | 1805, 133 km | 1776, 176 km |
| bored tunnels | 7 | 9 | 17 |
| corners stepping over 0.45 m | 1223 | 451 | |

A junction with an avenue, a highway or a ramp keeps its grade. Levelled, the primary roads'
fills and cuts pass the 18 and 20 m limits on every layout tried (24 m with highways left
out). So 449 corners at such junctions still step more than 0.45 m. Meeting them needs road
surfaces that warp across their width near a junction (the minor road's edges rising to the
major road's), which a grade line along the centerline cannot hold: an open item.

The extra walls are terraces round the hill districts' level junctions (Crown Heights,
Ridgeback, Hollow, Lantern Steps). The levelled junctions move the finished ground, so some
lots become or stop being hillside greens, and the buildings of those districts are drawn
again. [`cragmouth/`](cragmouth/) has the build and blockout reports, `preview_terrain.png`
and the 8K `render_iso_city.jpg` and `render_hillside.jpg` (`citygen rerender <dir> --eye -760
170 80 --target -1200 900 62 --lens 26 --name hillside`). A test checks that every leg of a
local junction of the hilly test city holds its node's height to where it leaves the junction
(`test_junction_legs_meet_at_one_height`).

## 3. Deck streets' district (M14)

`decks._twin` and `decks._ramp` give the deck's upper streets and ramps the deck's district in
`district_ids`. The blockout now joins their streets and sidewalks per district like the
ground's (`d03.deck_road.<tile>`, `d03.deck_sidewalk.<tile>`, 8 of each on Vesper Bay Decks),
so their Unreal actors carry `cg.district=d03`. Street parking on the deck names its district,
and the fast-travel fallback can use the deck's lanes. Vesper Bay Decks passes all 91 checks
([`vesper_bay_decks/report.txt`](vesper_bay_decks/report.txt)).

The ground's local streets have empty `district_ids` too, so every city's ground streets are
joined as `city.road_<class>.<tile>`. Giving them their district would move every city's
model and blockout plan, so it is left as an open item.

## Open items

- Corners at junctions with a primary road still step on a hill (above).
- M3's lot draws by build-order index (above, and M13's open item).
- Ground local streets without `district_ids` (above).
- assetgen's street pieces (AG7) take a sidewalk's height from its road's grade line, as the
  blockout does, and pick up the level local junctions on their own. A stage 2 session should
  check its Cragmouth tiles.
- M15's Unreal shots of Cragmouth (`docs/progress/M15/cragmouth/`) are from the earlier
  model. An Unreal check of the new one is the coordinating session's call.
