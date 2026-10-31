# AG13: ground cover and grass

Every piece of M16's open land textured by its cover kind and grass scattered on it, per
256 m tile (`assetgen ground BUILD`, also a stage of `assetgen build`). Design notes:
`CLAUDE.md` (AG13 paragraph), `docs/assetgen_milestones.md` (AG13) and the PR.

## Renders (8K, `assetgen materials preview`, Vesper Bay)

- `vesper_bay/8k/park.jpg`: Scholar Isle's park at street level.
- `vesper_bay/8k/wasteland_lot.jpg`: a vacant lot in The Stacks.
- `vesper_bay/8k/lawn_edge_path.jpg`: a lawn's edge where a worn path leaves the street.

## Samples

Builds on the Windows PC (3 workers) of M16's models (main at 280eb35), every ground check
passing; `summary.json` has the numbers below and the regeneration's tiles.

| City | Pieces | Tiles | Clumps | Most in a tile | Tiles at the cap | Instanced triangles, most in a tile | Ground triangles (most in a tile) | Clump variants (triangles) | MB | s |
|---|---|---|---|---|---|---|---|---|---|---|
| Vesper Bay | 4486 | 160 | 1,823,161 | 40,000 | 11 | 7,057,657 | 61,744 (1,498) | 61 (10,796) | 89 | 44 |
| Delta Megacity | 4780 | 145 | 1,012,038 | 40,000 | 9 | 7,082,152 | 65,852 (1,141) | 61 (10,796) | 55 | 36 |
| Saltreach Free Port | 2627 | 158 | 2,283,363 | 40,000 | 26 | 7,966,535 | 36,475 (1,346) | 55 (9,732) | 105 | 44 |
| Nexus City | 5520 | 173 | 1,374,336 | 39,840 | 8 | 7,015,648 | 72,245 (1,135) | 67 (11,860) | 73 | 38 |
| Greyhook | 2574 | 151 | 1,095,227 | 37,874 | 0 | 4,483,236 | 44,659 (1,008) | 55 (9,732) | 56 | 34 |
| Cragmouth | 5381 | 129 | 1,189,678 | 40,000 | 3 | 9,382,475 | 491,923 (8,506) | 58 (10,264) | 100 | 62 |
| Vesper Bay Decks | 4258 | 160 | 1,676,080 | 40,000 | 11 | 7,057,657 | 58,556 (1,337) | 61 (10,796) | 83 | 45 |

Budgets (decision 13.9 (a), `assetgen/ground/kinds.py`): 40,000 clumps a tile, 3 million a
city, 400 triangles a clump variant, 60,000 for all of a city's variants, 250,000 ground
triangles a tile and 12 million a city, 12 million instanced triangles a tile.

Vesper Bay's Old Town regenerated (M16's regenerated model over the same base): 27 of the
160 tiles made again, all within 55 m of the district (its pieces meet 26 tiles); the other
133 kept byte for byte.

## Files

Each city folder: `ground_preview.jpg` (`ground/preview.png`: the open land from above at 2 m
a pixel, a dot per second clump, and the tile with the most clumps at 0.25 m a pixel with
its mask's wear and shade and each clump at its footprint) and `ground_report.txt`. `wip/`:
the first previews and street-level renders.
