"""AG8, props, plants and signs (scope 5.4, 5.5 and 14.9).

- **Props**: for every M6 prop kind a family of 4 to 12 generated variants per district style
  (`styles.py`: sleek, civic, heavy, neon, old), each placement picking its variant from a
  hash of its id; instanced in Unreal in place of M15's prototypes. Cables, scaffolding and
  market gates follow their M6 geometry exactly and are meshes per tile.
- **Plants**: trees by species grown by space colonization (Runions 2007), palms, conifers,
  shrubs, sedum, scrub and ivy, 6 or 8 variants per species, each instance scaled to its
  plant's height and crown; leaves on alpha-cut cards of AG6's leaf clumps.
- **Signs**: an asset for every M11 sign slot, one path with AG6's signage: AG6 decides the
  text, script, style and colors and draws the flat faces on its sign pages; AG8 makes the
  signs: lightboxes and LED panels whose faces show their page cells, neon tubes swept along
  AG6's glyph strokes, channel letters, billboards with frames, lamps and the ad's cell,
  holo-ads (translucent, non-Nanite, LOD chains) and neon bands.

`assetgen props BUILD [--spec S]` (`build.build`) writes `BUILD/assets/props/`, the props
and signs contributions and the report; `assetgen build` runs it after the streets. Pure
Python on integer millimeters, like the rest of assetgen.
"""

from .build import PROPS_VERSION  # noqa: F401
