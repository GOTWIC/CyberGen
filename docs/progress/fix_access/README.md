# Access fixes (#86, #87, #91)

Fixes between milestones, from run-through 2: every park has a way in, every entrance reaches
a walkway, and Vesper Bay Decks builds on its first full-city try.

## What changed

**Ways into open space** (#86, `citygen/parkpaths.py`). The park paths fix gave each open
space a path to the walkways within 30 m of it, and a passage through the lots where they
enclosed it; those it could not reach said so (`access: none`). A second pass now takes those
(most cities have none, so their open spaces are as they were):

1. a path to a neighbor open space's path within 30 m (a strip park behind a park, a loop's
   infield beside the park round it), `access: via_open_space`;
2. else a path to a walkway up to 90 m away that passes under the raised roads between:
   every carriageway lower than 5 m (so over M18's embankments, which fill under 4.5 m) and
   every junction that low is blocked, and the walkway it joins must be at grade at its foot
   (a raised road's sidewalks sit at z 0 in the walk graph, so a path would otherwise join a
   sidewalk 7.5 m up), `access: under_road` (`path` where it crosses no road); M7's road
   columns keep off such a path;
3. else a park with no street, which M2 makes of every roadless piece over 1,500 m2, becomes
   a green verge (`kind: green`, `attrs.verge` the reason), as the smaller roadless pieces
   already were: the infields of a stack interchange and of a raised junction, a strip
   between the sea and the spaceport's fence;
4. any other open space left says why, and `park_access` now fails it.

Choices: a footbridge or an underpass to an interchange's infield reads wrongly (no city
puts a park between a stack's ramps; real infields are landscaping), so those are verges. A
path under a viaduct needs no new structure and is how people reach the land beside one.
Both new kinds of path block the carriageways at grade, so none crosses a road on foot.

**Walled-in entrances** (#87, `citygen/buildout.py`). After M3's relinks, moves and ways
round, an entrance still walled in:

1. leaves through its own complex (towers on one podium whose podiums close round it): a
   door path through the complex, `attrs.through` the property, which the check lets enter
   that property's buildings (the lobby), `entrances_through_complex`;
2. else gets a gateway, 3 m wide, cut through the low buildings on its straight link to one
   of its eight nearest walkways (no tower over 30 m, landmark, traced, held or formed
   building, no portal, none of the cut building's own doors or units in the way): each mass
   standing on the ground there keeps its legs beside the gateway and a mass over it from
   4.5 m up to its top, so the roof and the floors above run on and the footprint stays the
   outline (`attrs.passage_cut`), `entrances_gateways`. Vesper Bay's freight terminal sits
   behind a 383 m shed that stands on the strip lot round the site; its gate house and office
   now leave through one gateway (the office's entrance moves along its facade to use it).

Station stairs (M19, `citygen/transit.py`): an elevated platform end whose sidewalk is only
reached round the buildings gets an elevator and a path led round, not a stair straight
through them (Pinned's Stacks station ran an 80 m stair through a block); a metro stair
stepped along its concourse that would pass under a building's ground floor becomes an
elevator straight down from the sidewalk. `walkway_building_clash` now fails walled-in
entrances and station stairs through a building (both were notes).

**Deck columns** (#91, `citygen/decks.py`). Vesper Bay Decks' first layout failed
`deck_columns` by 0.8 m: two slab points over a junction 24 m from a column. The fill-in
had a spot 6.5 m away on the thin strip between a small park's paths, but its last resort
takes the nearest point of that strip (the allowed zone taken in by 0.1 m), which lies on
the strip's boundary, and tested it with `thin.contains`, which leaves the boundary out: the
column was kept or dropped by the grid's rounding. It is now tested against the allowed zone
itself. With that and the park fixes, the first layout passes every check.

The second layout (`layout_salt` 1, no longer reached) fails `transit_supports`: the Crown
Loop sky tube runs 772 m over the corporate core's streets with no free spot for a pylon
(600 m allowed). That is transit's, not the deck's, and is left as an issue.

## Numbers

FILL_TABLE

## Images

- `vesper_bay/plan_gateway_before.png`, `plan_gateway_after.png`, `render_gateway.jpg`: the
  freight terminal's walled-in gate house and office, then the gateway through the shed.
- `vesper_bay/plan_loop_park_before.png`, `plan_loop_park_after.png`,
  `render_park_under_ramp.jpg`: a cloverleaf loop's infield park, then its path under the
  loop ramp to the next park's path.
- `vesper_bay_decks/plan_deck_columns_before.png`, `plan_deck_columns_after.png`: the
  first layout's slab points (crosses) out of a column's reach on main, and the column the
  fill-in now places on the thin strip.
- `vesper_bay_decks/plan_strip_park_before.png`, `plan_strip_park_after.png`: a strip park
  with no way in (red), then its path to its neighbor's.
- FILL_IMAGES

Plan views by `plot_access.py` (open space with no way in red, masses on the ground filled,
those over it dotted, park paths red, door paths magenta, a walled-in entrance a red cross);
measures by `measure_access.py`. Every touched city's build report is in its folder.
