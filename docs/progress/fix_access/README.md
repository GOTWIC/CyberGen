# Access fixes (#86, #87, #91)

Fixes between milestones, from run-through 2: every park has a way in, every entrance reaches
a walkway, and Vesper Bay Decks builds on its first full-city try.

## What changed

**Ways into open space** (#86, `citygen/parkpaths.py`). The park paths fix gave each open
space a path to the walkways within 30 m of it, and a passage through the lots where they
enclosed it; those it could not reach said so (`access: none`). A second pass now takes those
(most cities have none, so their open spaces are as they were):

1. a path to a neighbor open space's path within 30 m (a strip park behind a park, a loop's
   infield beside the park round it), joined at that path's nearer end (the neighbor's
   middle, where its paths meet, or its walkway foot), so no park path is split and each
   still starts inside its own open space, `access: via_open_space`;
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
through them, and none of its own where that end stands over the water (Pinned's Stacks
station ran an 80 m stair from a platform end over the river through a block; its other end's
stair serves it); a metro stair
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
(600 m allowed). That is transit's, not the deck's, and is drafted as an issue (see the PR).

## Numbers

Main (on the sky tube and barriers fixes) before the slash, this branch after. Open spaces
with no way in are those that said so (`access: none`); islet parks (land without a district)
stay a note and are not counted. The last column is how the open spaces that had none are
reached now.

| City | Full-city tries | Open spaces with no way in | Walled-in entrances | Station stairs through a building | Ways in now |
|---|---|---|---|---|---|
| Saltreach Free Port | 1 / 1 | 0 / 0 | 0 / 0 | 0 / 0 | (byte-identical) |
| Delta Megacity | 2 / 2 | 0 / 0 | 0 / 0 | 0 / 0 | (byte-identical) |
| Nexus City | 1 / 1 | 0 / 0 | 0 / 0 | 0 / 0 | (byte-identical) |
| Greyhook | 2 / 2 | 1 / 0 | 0 / 0 | 0 / 0 | 1 path along the shore to a street's end |
| Vesper Bay | 1 / 1 | 1 / 0 | 2 / 0 | 0 / 0 | 1 to a neighbor's path (under the loop ramp); 1 gateway |
| Vesper Bay Pinned | 2 / 2 | 3 / 0 | 0 / 0 | 1 / 0 | 2 verges, 1 path along the shore |
| Vesper Bay Stacks | 2 / 2 | 9 / 0 | 0 / 0 | 0 / 0 | 8 verges (the stack's infields), 1 path along the shore |
| Vesper Bay Decks | 3 / 1 | 2 / 0 | 1 / 0 | 1 / 0 | 2 to a neighbor's path; 1 gateway |
| Cragmouth | 2 / 2 | 2 / 0 | 0 / 0 | 0 / 0 | 1 verge, 1 to a neighbor's path |

Vesper Bay Decks now builds on its first layout, so its cases are that layout's (the freight
terminal's gateway, a strip park and the loop's infield); main's third layout had a tower
walled in by its own complex's podium (the case `_through_complex` serves, tested in
`tests/test_park_paths.py`) and a metro stair under a building. Every city passes every check
(102, 107 with the deck). The small test city (`tests/conftest.py` SMALL) had two loop
infields with no way in; both now join their neighbor park's path under their loop ramp, so
its assetgen goldens move too.

Assets (`assetgen`, the stages each change can reach, then `assetgen fit`): Vesper Bay and
Vesper Bay Decks (buildings, streets, props, ground, materials, fit: the gateway building's
shell, front and doors, `asset_access` with every door reached), Cragmouth, Greyhook, Vesper
Bay Pinned and Vesper Bay Stacks (streets, ground, fit). Every check passes but the two
demos' `asset_grounded`, each on one raised junction's step (Pinned: 0.43 m where road
`rs.e312s524` meets junction `jn.e368s514`; Stacks: 0.35 m, `rs.e536s213` at `jn.e559s304`):
both cities' roads, nodes and junctions are main's record for record, so these predate this
change (AG7's junction drawing on raised junctions, the open junction-steps item; AG14 was
validated on the samples, not the demos).

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
- `vesper_bay_pinned/plan_station_stair_before.png`, `plan_station_stair_after.png`: the
  Stacks station's 80 m stair through a block, then none at that platform end, which stands
  over the river (the station's other end has its stair); `plan_spaceport_strip_*.png`: a strip
  between the sea and the spaceport, then its path along the shore; `plan_junction_infield_*`:
  the land between the raised ring and the water, then a verge.
- `vesper_bay_stacks/plan_stack_infields_before.png`, `plan_stack_infields_after.png`: the
  stack interchange's eight infield parks, then verges.
- `cragmouth/plan_verge_after.png`, `plan_pocket_park_after.png`;
  `peninsula_city/plan_park_after.png`.

Plan views by `plot_access.py` (open space with no way in red, masses on the ground filled,
those over it dotted, park paths red, door paths magenta, a walled-in entrance a red cross);
measures by `measure_access.py`. Every touched city's build report is in its folder.
