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

## Renders

Vesper Bay's Crown Loop (a 6.5 km sky tube loop, 654 rings) from the north over Highcrest,
looking at the Corporate Core: `assetgen materials preview` (AG6's textured Blender preview,
32 samples) on the full `assetgen build`, the same camera each time
(`--eye 1300 1830 72 --target 1215 1688 92 --lens 32`). Three tube piece boundaries are in
the view (800, 1200 and 1600 m along the line, each within 20 m of one of the three pylons
under the near arm); the pattern runs on across them.

| File | What |
|---|---|
| `night_rings_every1.jpg` | by night, every ring lit (the default) |
| `night_rings_every2.jpg` | `lit_rings_every: 2` |
| `night_rings_every3.jpg` | `lit_rings_every: 3` |
| `day_pylons.jpg` | by day, the plain pylons with their cradles under the tube |
| `day_pylons_wide.jpg`, `night_rings_wide.jpg` | farther out (350 m north of the nearest pylon, `--eye 1331 2020 35 --target 1240 1682 62 --lens 30`), the loop round the core by day and by night |

## Results

Each city's folder here has its build report (`report.json`, `report.txt`) and
`preview_transit.png`; the five samples' also `preview_gameplay.png` (their reports are the
ones `tests/test_build.py::test_committed_reports_match` compares with a fresh build).

Every city the change touches, built on this branch (`citygen build`, the blockout for the
samples and demos), against main's full-city tries (in brackets, from
`docs/progress/fix_paths/`):

| City | Checks | Tries | Sky tubes |
|---|---|---|---|
| Vesper Bay | 102/102 | 1 (1) | Crown Loop (loop, 6.54 km): 16 supports (15 plain pylons, 1 cantilever), 654 rings 10.00 m apart on 17 pieces |
| Delta Megacity | 102/102 | 2 (2) | Skyline Loop (loop, 3.29 km): 6 supports (4 plain pylons, 1 pier, 1 cantilever), 329 rings 9.99 m apart on 9 pieces; Delta Loop (loop, 4.97 km): 14 supports (10 plain pylons, 2 frames, 1 pier, 1 cantilever), 497 rings 10.01 m apart on 13 pieces |
| Nexus City | 102/102 | 1 (1) | Spire Line (open, 0.78 km): 3 supports (2 plain pylons, 1 cantilever), 78 rings 9.96 m apart on 2 pieces |
| Greyhook | 102/102 | 2 (2) | Spine Tube (open, 1.70 km): 5 plain pylons, 170 rings 10.00 m apart on 5 pieces |
| Vesper Bay Pinned | 102/102 | 2 (2) | Crown Line (open, 2.61 km): 7 supports (5 plain pylons, 2 piers), 261 rings 10.02 m apart on 7 pieces |
| Vesper Bay Stacks | 102/102 | 2 (2) | Crown Line (open, 3.00 km): 6 supports (3 plain pylons, 2 piers, 1 cantilever), 300 rings 10.01 m apart on 8 pieces |
| Vesper Bay Decks | 107/107 | 3 (3) | Crown Loop (loop, 4.39 km): 10 supports (9 plain pylons, 1 pier), 439 rings 9.99 m apart on 11 pieces |
| Saltreach Free Port | 102/102 | 1 (1) | none (model byte-identical to main's) |
| Cragmouth | 102/102 | 2 (2) | none (model byte-identical to main's) |

- **Against main** (Vesper Bay, main built from origin/main): with the defaults the model
  differs only in the Crown Loop's 15 lone pylons (form `column` for `mast`, no `mast_top_m`
  or `stays`), its 17 tube pieces (`attrs.rings`) and its line (`attrs.rings`,
  `attrs.support_style`); the blockout plan differs only in those 15 pylon objects (no mast
  legs or stays).
- **`supports: mast`** (Vesper Bay with `transit.sky_tube.supports: "mast"`): all 406 transit
  supports (columns, pylons, beams) are main's record for record, 15 of them masts with
  `mast_top_m` and `stays`; the blockout plan is main's byte for byte (the blockout does not
  draw rings).
- **Frequencies** (Vesper Bay with `lit_rings_every` 2 and 3): the same 654 rings at the same
  places (654 is a multiple of 1, 2 and 3 here), 327 and 218 lit; the patterns alternate
  unbroken across every piece boundary; AG7 differs from the default only in the 17 tube
  pieces.
- **`assetgen build`** (`--workers 2`; Vesper Bay with `cities/vesper_bay/asset_spec.json`):
  every check passes on Vesper Bay, Delta Megacity and Greyhook (buildings, streets, water,
  props, ground, materials, fit). Nexus City passes every street, water, props, ground,
  materials and fit check and fails two building checks exactly as main does: `asset_unique`
  (one pair of neighboring towers, `d01.lm.w98n1260.bld` and `d01.lot.e26n1332.bld`, share a
  facade system) and `asset_access` (2 blocked doors). Its 6,459 building briefs are main's
  (main's Nexus City model, built from origin/main, is its golden; `assetgen build
  --no-streets` on main's code fails the same two checks with the same numbers). An LED band is 96 triangles a lit ring:
  Vesper Bay's tubes 133,662 triangles with every ring lit, 102,270 with every second,
  91,806 with every third.
- **Found on the way**: M19 routes a sky tube that takes out towers (`_routed`'s cut pass)
  or loses a host (`_reroute_hosts`) again as a fresh `Line`, so a style set when the line
  was made was lost on Vesper Bay's Crown Loop; the style is now set once every line is
  routed (`test_sky_tube_masts_and_lit_ring_frequency` makes every line afresh to hold it).
