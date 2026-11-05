# Sky tube fixes: plain pylons and lit rings (issues #94, #97)

Two fixes between milestones, asked for after the second run-through of Delta Megacity in
Unreal: the sky tubes (hyperloops) stand on plain pylons again instead of M19's cable-stayed
masts (#94), and their rings light up at night, every ring or every second, third, ... one
(#97).

## What changed

- **Spec** (`citygen/spec.py`): `transit.sky_tube` sets the defaults for every sky tube line,
  and each line may set its own:

  ```json
  "transit": {
    "sky_tube": {"supports": "pylon", "lit_rings_every": 1},
    "lines": [{"mode": "sky_tube", "name": "Crown Loop", "lit_rings_every": 3, ...}]
  }
  ```

  `supports` is `pylon` (the default) or `mast`; `lit_rings_every` is 1 (the default: every
  ring lit), 2, 3, ... Both apply to sky tube lines only (a validation error on another
  mode). Left out, the mode's defaults apply (`presets.SKY_TUBE_SUPPORTS`,
  `SKY_TUBE_LIT_RINGS_EVERY`); neither is written into the filled spec, so a spec that does
  not set them hashes as before and a city without sky tubes builds the same bytes.
- **Pylons** (`citygen/transit.py`): with `pylon` every sky tube support is a plain pylon
  under the tube at M19's positions and spacing (`Builder._column` gives it the form
  `column`, `_masts` does not run: no `mast_top_m`, no `stays`). Portal frames, cantilever
  bents and piers are as M19 builds them; a sky tube never had a cable span (its longest span
  is its main span, 600 m), so nothing there changes. The blockout and AG7 draw a pylon as
  they drew the sky tubes' columns before M19 (a shaft by id; AG7 a shaft and a cradle across
  the tube). With `mast` the supports are M19's, record for record.
- **Rings** (`transit.tube_rings`): a tube's rings run along the whole line, not per 400 m
  piece: n of them evenly spaced near 10 m apart (`RING_M`), n a multiple of the frequency;
  a loop's start at its seam (so the pattern runs on round it), an open line's half a spacing
  in from each end; ring k is lit when k is a multiple of the frequency. Each tube piece
  carries its stretch of them (`attrs.rings`: [distance along the piece's own line, lit] for
  the rings in its stretch [s, e) of the line), and the line its summary
  (`attrs.rings`: count, lit, every, spacing_m; `attrs.support_style`).
- **AG7** (`assetgen/streets/transit.py`, `sky_tube` 2): the ribs stand at the model's rings
  (a model without them keeps one every 10 m from 5 m in), and each lit one carries an LED
  band on the rib's outer face, 0.2 m wide along the line, in the line's color at full
  brightness (`streets.materials.led_slot`: slot `led.<hex>`, master `emissive`; AG6's
  catalog puts it on `neon`, which glows more by `MPC_CityGen`'s `Night` in Unreal and in the
  Blender night previews).
- **Exporter**: no code change (`docs/unreal_export.md`, record row "Sky tube fixes").
