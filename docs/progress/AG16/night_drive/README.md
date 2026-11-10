# AG16: the night drive view before and after

A review of `../before_after/` saw the near lamp on the right of both night drive views
(`night_native_drive.jpg`, `night_tsr67_drive.jpg`) lose its light pool after the fixes, and
the trees and grass on the left go darker. Measured on the full-size shots (2560 x 1440):

- [`night_native_drive_diff.jpg`](night_native_drive_diff.jpg): before, after, and before
  minus after times four (grey: no change). The sidewalk and gravel under the right lamp
  are unchanged: the region's mean grey level is 33.7 before and 33.6 after, and the
  difference image is flat there. What differs: the two nearest crowns on the left, the
  grass blades' edges (the grass sways with time) and a few lit windows (schedules).
- [`night_native_drive_crowns.jpg`](night_native_drive_crowns.jpg): those crowns,
  brightened. Lit by the nearest lamps, they are about 5% darker after (mean green 35.2 to
  33.4; 35.3 to 33.6 at 67% TSR). By day they match (85.5 and 85.7). Every other view
  before and after differs by at most about one grey level on average, with mixed signs.

Not timing: the after state draws the crowns at 33.35 to 33.37 every time, at the drive's
start right after the warm-up flights, again after driving the route
([`after_visits_and_ungrouped.jpg`](after_visits_and_ungrouped.jpg)), and in every
diagnostic run. The benchmark now logs the play actor's lamps at each shot
(`ACityGenPlay::GetLampReport`): the same lamps carry the same lights (120 cd, the nearest
eight with shadows) at both visits.

Ruled out, one switch at a time on the imported Delta (the drive start shot, after the
benchmark's warm-up flights):

| switch | crowns (mean green) |
|---|---|
| before (main's exporter) | 35.2 |
| after | 33.35 |
| texture streaming on from startup (`r.TextureStreaming=1`) | 33.36 |
| the Nanite pool at 256 MB (as before) | 33.35 |
| HLODs off (`wp.Runtime.HLOD 0`) | 33.46 |
| shadow maps instead of virtual shadow maps | 34.9 |
| no dynamic shadows | 44.5 |
| Delta imported again without groups (`CITYGEN_UE_GROUP=0`) | 33.36 |

So the darker crowns are shadow from the lamps falling inside the leaves; grouping, the
texture and Nanite settings, the HLODs and the shot's timing do not change it. What is
left of AG16's changes that this view sees: the masters reading Custom Primitive Data
through per-instance custom data (the leaves' tint; the day views match) and the streaming
range. A difference of this size in one view is left as an open item.

Found on the way (fixed): an import without groups over one with them, or back to the
blockout, kept a building's parts and street front on it as components beside the actors
made for them (`Importer.drop_members`; the import digest now lists each actor's member
components); and an offload took the actors to unload by label, so an actor made again
under the same key brought the destroyed one back from disk (`actor_guids`). Delta
imported without groups over the grouped level: 73,772 actors in the level, exactly the
manifest's, after 64,500 offloads, 6,255 buildings' members dropped.
