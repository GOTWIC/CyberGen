"""AG8, props, plants and signs (scope 5.4, 5.5 and 14.9).

- **Props**: for every M6 prop kind a family of 4 to 12 generated variants per district style
  (`styles.py`: sleek, civic, heavy, neon, old), each placement picking its variant from a
  hash of its id; instanced in Unreal in place of M15's prototypes. Cables, scaffolding and
  market gates follow their M6 geometry exactly and are meshes per tile.
- **Plants**: trees by species grown by space colonization (Runions 2007), palms, conifers,
  shrubs, sedum, scrub and ivy, 6 to 10 variants per species, each instance scaled to its
  plant's height and crown.
- **Signs**: an asset for every M11 sign slot: box and neon shop signs with their text (POI
  names, else generated shop names and uses), neon tubes swept along the glyph strokes of an
  in-repo stroke font (`glyphs.py`; generated glyphs for the scripts decision 13.3 leaves
  without fonts), billboards with frames, lamps and a lit face, holo-ads (translucent,
  non-Nanite, LOD chains) and neon bands.

`assetgen props BUILD [--spec S]` (`build.build`) writes `BUILD/assets/props/`, the props
and signs contributions and the report; `assetgen build` runs it after the streets. Pure
Python on integer millimeters, like the rest of assetgen.
"""

from .build import PROPS_VERSION  # noqa: F401
