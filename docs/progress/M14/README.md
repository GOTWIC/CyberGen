# M14: layered districts

A district with `decks` in its spec gets a deck city at level 1 over its ground streets: a
slab on round columns, upper streets with their junctions, sidewalks, lanes and walkways,
ramps down to the ground network, light wells with stairs and elevators, lots and buildings
on the deck, and a low undercity under the slab. Everything carries a level (0 the ground,
1 a deck). A city without decks builds exactly as before.

## Spec

```json
"decks": {"height_m": 9, "cover": 0.45, "column_m": 18, "light_m": 70, "ramps": 2,
          "upper": "midtown_mixed", "upper_height_m": [12, 40]}
```

All fields have defaults (`"decks": {}` is enough). Districts with long, regular street
faces suit decks best (residential heights, midtown, megablocks); a ramp needs about 110 m
of straight street at 12%. On a city with terrain, a district with decks is levelled like a
`flat` district.

## How it is built

- **Plan** (M2, after the local streets): the faces of the at-grade street graph; a cluster
  grown from the face nearest the district's middle across interior streets until `cover`
  of the district, keeping off roads raised over 3 m (and, in a regeneration, held transit
  lines too low over it). Interior streets get an upper twin (`l1.<street>`, nodes
  `<node>.l1`); spokes out of the cluster end short of the edge or become two-lane ramps
  (12%, 10 m top and 12 m foot runs, 15 m vertical curves).
- **Per level**: the lane and walkway graphs per level, joined by the ramps, stairs and
  elevators.
- **Finish** (after the blocks): the slab (the lots under the deck, the twins' corridors,
  the upper junctions, and a 4 m colonnade over parks and plazas its streets pass); light
  wells until every ground walkway under it is within `light_m` of the sky (at least two),
  each with a switchback stair and an elevator; upper lots (`<lot>.l1`).
- **Buildings**: the `undercity` program under the slab up to its underside; the `upper`
  archetype on the deck from its top.
- **Columns** (after transit and tunnels): in the furniture zones of the streets under the
  slab, on a grid in the lots, then filled in (the nearest allowed point of a thin strip)
  wherever the slab is out of reach of one; never in a lane, crosswalk, junction, clear
  path, door, tunnel or structure.
- **Props and plants**: per level (no tree under a slab; lights hung from it).

## Checks

Five, run only on a city with decks: `deck_columns`, `deck_headroom`, `deck_light`,
`deck_links` (two stairs and an elevator, one walkway component with the ground's, a ramp,
the deck's lanes in the largest strongly connected part) and `deck_levels`. The prop checks
run on every level. Vesper Bay Decks passes all 91.

## Sample: Vesper Bay Decks

`cities/vesper_bay_decks`: Vesper Bay with a deck over Highcrest (21.9 ha at 9 m, 70 deck
streets and ramps, 163 deck lots, 158 buildings on the deck, 2 light wells, 570 columns).
A separate city, so Vesper Bay and its seeds stay as they were.

| | |
|---|---|
| ![](vesper_bay_decks/preview_decks.png) | ![](vesper_bay_decks/render_deck_edge.jpg) |
| The ground under the deck, the deck, a section | The slab's edge from above (8K) |

`vesper_bay_decks/` also has every generator preview, the build and blockout reports,
`render_iso_city.jpg` (8K) and `render_deck.jpg` (the build's deck view, 8K).

## Regenerating a layered district

`citygen build cities/vesper_bay_decks/city_spec.json OUT --district Highcrest --base BUILD`
builds a new deck in 34 s and passes all 91 checks; all 2642 held road segments come back
unchanged (`regenerated/`: report, model diff and map, the new deck's preview).

## Terrain

`cragmouth_decks/` is a test, not a sample: Cragmouth with decks on Hollow and Ridgeback.
Both districts are levelled; it passes all 91 checks with two decks.

## Downstream

- **assetgen**: the brief of a building on a deck has `floor_grid.level` and `deck_m`.
- **Unreal exporter**: actors on a deck tagged `cg.level=1`, the manifest's `decks`, lanes
  and walkways with their level in `graphs.json` and the graph data assets
  (`docs/unreal_export.md`).

## Fixes since the first sample build

- The deck checks run only on a finished city: `checks.run_checks` also serves the build's
  early checks on the M2 model, before the columns exist.
- A deck building's neon band starts 8 m over the deck, not over the ground.
- A regenerated deck keeps off held transit lines too low over it; the slab runs over parks
  its streets pass on a colonnade; the column fill-in reaches thin strips.

## Open items

- One deck level per district (level 1); a second deck over the first is not built.
- On terrain, deck districts are levelled rather than terraced.
- No Unreal check yet: the coordinating session's call.
