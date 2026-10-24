# Greyhook (peninsula)

## Prompt

> A narrow peninsula city pointing south into a cold grey sea. A spaceport at the tip. Megablock
> towers stacked along the spine. A dense entertainment strip on the western shore with a Ferris
> wheel. Walled residential heights in the north where the peninsula meets the mainland. A single
> river cuts across the neck. Sky tubes run down the spine through the megablocks, an elevated
> rail line follows the east shore, and a stadium sits near the neck.

## Interpretation

- Coast form `peninsula`, sea to the south, map 3.0 x 3.6 km (taller than wide).
- Districts named by the prompt: Wallgate Heights (residential, north edge, walled, inland), The
  Stacks (megablocks on the spine), Lantern Strip (entertainment, west shore, Ferris wheel
  landmark), Hook Spaceport (south edge, coast). Added because the prompt implies them: Neckgate
  (transit hub at the neck, where the lines meet, holding the stadium) and Eastside Docks (east
  shore, for the elevated rail to follow).
- Neckwater river from the west edge to the east edge, separating Neckgate from the peninsula
  body. The spec can only say which map edge a river enters from, so the schematic draws it
  across the middle of the map rather than exactly at the neck (noted for M1).
- Lines: Spine Tube sky tube through the megablocks to the spaceport (`through_towers`), East
  Shore Line elevated rail, plus a Strip Line metro (not in the prompt) so the entertainment
  strip and the mainland exit have transit.
- Mood: cold and grey, so more grime and less greenery than the presets in The Stacks and
  Wallgate Heights.

## Result

`citygen spec validate`: OK, 0 warnings. Schematic: `schematic.png`.
