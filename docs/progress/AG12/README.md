# AG12: water

Every water body's surface, bed and banks (`assetgen water`, and `assetgen build` after the
streets), on the six samples as main builds them after M18 (main at f27543e), on the
Windows PC.
The full record: [`docs/assetgen_milestones.md`](../../assetgen_milestones.md), AG12.

## Views (Vesper Bay, Blender, `assetgen materials preview --views water --night`)

| | By day | By night |
|---|---|---|
| A quayed canal, along its straightest stretch from 2.6 m over the water | [`water_canal.jpg`](vesper_bay/water_canal.jpg) | [`water_canal_night.jpg`](vesper_bay/water_canal_night.jpg) |
| The Vess River's natural bank, from over the water beside it | [`water_bank.jpg`](vesper_bay/water_bank.jpg) | [`water_bank_night.jpg`](vesper_bay/water_bank_night.jpg) |
| The harbor basins from above | [`water_harbor.jpg`](vesper_bay/water_harbor.jpg) | [`water_harbor_night.jpg`](vesper_bay/water_harbor_night.jpg) |

The same at 7680 px in [`vesper_bay/8k/`](vesper_bay/8k). They were made on M16's models
before AG13 was merged in, so the ground beside the water is still the blockout's flat cover.

## Per city

`<city>/water.jpg`: the water packs from above, read back from their glTF files
(`assetgen/water/preview.py`): the beds shaded by depth, the banks by kind; insets (300 m)
of the longest quay, the longest natural or riprap bank and the biggest harbor basin with
the surfaces' foam mask (white), the current (arrows) and the riprap stones.
`<city>/water_report.txt` (and `.json`) and `streets_report.txt`: the water and street
checks and stats on M18's models. Beside them, the reports of the full `assetgen build`
before M18 (M16's models): `asset_report.txt`, `props_report.txt`, `materials_report.txt`.

| City | Water bodies | km2 | Triangles (surface, bed, banks) | Stones | MB | Checks |
|---|---|---|---|---|---|---|
| [Vesper Bay](vesper_bay) | 10 | 3.56 | 1,868,947 | 45,178 | 69.9 | all pass |
| [Delta Megacity](delta_megacity) | 13 | 4.51 | 2,283,048 | 27,797 | 85.7 | all pass |
| [Saltreach Free Port](saltreach_free_port) | 12 | 4.90 | 2,687,628 | 28,196 | 101.7 | all pass |
| [Nexus City](nexus_city) | 18 | 3.16 | 1,575,774 | 21,483 | 59.2 | all pass |
| [Greyhook](greyhook) | 6 | 7.24 | 3,886,195 | 48,496 | 146.7 | all pass |
| [Cragmouth](cragmouth) (terrain) | 8 | 3.03 | 1,609,997 | 34,044 | 60.6 | all pass |

Every street check passes in all six too. Before M18, on M16's models with the assetgen
fixes after AG10 and AG13 merged in, a full `assetgen build` of the six passed every check of
every stage (buildings, streets, water, props, AG13's ground, materials).

Vesper Bay's Old Town regenerated (M16's regeneration, on M16's models): 22 banks changed,
all in Old Town;
15 body pieces changed, each within reach of a changed bank; 14 of 114 water tiles made
again, 9 written.

## Work in progress

[`wip/`](wip): snapshots pushed while the milestone ran.
