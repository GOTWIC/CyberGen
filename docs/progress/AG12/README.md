# AG12: water

Every water body's surface, bed and banks (`assetgen water`, and `assetgen build` after the
streets), built on M16's builds of the six samples (main at 280eb35) on the Windows PC.
The full record: [`docs/assetgen_milestones.md`](../../assetgen_milestones.md), AG12.

## Views (Vesper Bay, Blender, `assetgen materials preview --views water --night`)

| | By day | By night |
|---|---|---|
| A quayed canal, along its straightest stretch from 2.6 m over the water | [`water_canal.jpg`](vesper_bay/water_canal.jpg) | [`water_canal_night.jpg`](vesper_bay/water_canal_night.jpg) |
| The Vess River's natural bank, from the land beside it | [`water_bank.jpg`](vesper_bay/water_bank.jpg) | [`water_bank_night.jpg`](vesper_bay/water_bank_night.jpg) |
| The harbor basins from above | [`water_harbor.jpg`](vesper_bay/water_harbor.jpg) | [`water_harbor_night.jpg`](vesper_bay/water_harbor_night.jpg) |

The same at 7680 px in [`vesper_bay/8k/`](vesper_bay/8k). The ground beside the water is
still the blockout's flat cover (AG13's).

## Per city

`<city>/water.jpg`: the water packs from above, read back from their glTF files
(`assetgen/water/preview.py`): the beds shaded by depth, the banks by kind; insets (300 m)
of the longest quay, the longest natural or riprap bank and the biggest harbor basin with
the surfaces' foam mask (white), the current (arrows) and the riprap stones.
`<city>/water_report.txt` (and `.json`): the water checks and stats; beside it the other
stages' reports of the same build (`asset_report.txt`, `streets_report.txt`,
`props_report.txt`, `materials_report.txt`).

| City | Water bodies | km2 | Triangles (surface, bed, banks) | Stones | MB | Checks |
|---|---|---|---|---|---|---|
| [Vesper Bay](vesper_bay) | 10 | 3.56 | 1,868,341 | 45,178 | 69.9 | all pass |
| [Delta Megacity](delta_megacity) | 13 | 4.51 | 2,286,579 | 36,400 | 85.7 | all pass |
| [Saltreach Free Port](saltreach_free_port) | 12 | 4.90 | 2,687,395 | 27,307 | 101.7 | all pass |
| [Nexus City](nexus_city) | 18 | 3.16 | 1,577,157 | 22,680 | 59.3 | all pass |
| [Greyhook](greyhook) | 6 | 7.24 | 3,888,557 | 47,768 | 146.7 | all pass |
| [Cragmouth](cragmouth) (terrain) | 8 | 3.03 | 1,610,200 | 34,044 | 60.6 | all pass |

`assetgen build` otherwise fails only what main's build of the same models fails (Vesper
Bay `asset_roofs`; Delta Megacity and Nexus City `asset_access`, Nexus City
`street_meshes`; Greyhook `asset_envelope`; Cragmouth `asset_clearance`, `asset_landings`,
`asset_slopes`); Saltreach passes every check.

Vesper Bay's Old Town regenerated (M16's regeneration): 22 banks changed, all in Old Town;
15 body pieces changed, each within reach of a changed bank; 14 of 114 water tiles made
again, 9 written.

## Work in progress

[`wip/`](wip): snapshots pushed while the milestone ran.
