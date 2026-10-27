# M10 WIP 02: samples and regenerations

All five samples and the pinned demo build with stable ids and pass all 75 checks. One
district of each regenerated with a new seed (`citygen build SPEC OUT --base BUILD --district
NAME`), every held road back byte for byte:

| City, district | Regeneration | Whole command | Held roads unchanged | Seam outside the district |
|---|---|---|---|---|
| Saltreach Free Port, Westreef | 29.0 s | 37.5 s | 441 of 441 | 77 |
| Delta Megacity, Midtown | 52.6 s | 66.2 s | 2480 of 2480 | 297 |
| Greyhook, Lantern Strip | 22.3 s | 28.9 s | 668 of 668 | 126 |
| Vesper Bay, Neon Strand | 51.7 s | 65.2 s | 2136 of 2136 | 1155 |
| Vesper Bay, Old Town | 50.5 s | 64.2 s | 1553 of 1553 | 247 |

Nexus City and the pinned demo were built on a whole-city retry with a salted local layout,
and the salt was not kept in the build state, so their regeneration started from another
city: fixed (`build.add_local`/`add_buildings` keep `layout_salt`), being rebuilt.
