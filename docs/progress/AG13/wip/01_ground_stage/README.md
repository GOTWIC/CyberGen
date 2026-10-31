# AG13 WIP 01: the ground stage

First run of `assetgen ground` on M16's builds (main at 280eb35), Windows PC, 3 workers.

- `<city>_ground.jpg`: `ground/preview.png`: the open land from above at 2 m a pixel (each
  piece in its surface's color, desire lines worn, a dot per second clump in its kind's
  color), and the tile with the most clumps at 0.25 m a pixel with its mask's wear and
  shade over the surfaces and each clump drawn to its footprint.
- `vesper_bay_wasteland_first.jpg`: the first textured street-level render (`assetgen
  materials preview`, a camera of its own): a vacant lot in The Stacks, its wild meadow set
  worn to dirt, weeds, dry grass and scrub clumps; the clumps were made fuller after it.

| City | Pieces | Tiles | Clumps | Ground triangles | Checks |
|---|---|---|---|---|---|
| Vesper Bay | 4486 | 160 | 1,795,886 | 61,744 | all pass |
| Delta Megacity | 4780 | 145 | 1,004,355 | 65,852 | all pass |
| Saltreach Free Port | 2627 | 158 | 2,283,062 | 36,475 | all pass |
