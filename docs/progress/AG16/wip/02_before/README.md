# AG16 WIP 02: Delta before any fix

The benchmark's results are in [`../../bench/delta_megacity/before`](../../bench/delta_megacity/before)
(three runs at 2560 x 1440, the table in `bench.md`, graphs and the first run's shots).

- **Frame time**: the median is 8 to 13 ms walking and flying, 18 to 20 ms driving; the
  95th percentile 27 to 49 ms everywhere, so 40 fps is missed in every pass and part of the
  route. Bound by the game thread in every one; the GPU's p95 is 7 to 12 ms (native by
  night the most).
- **The slow frames** (over 25 ms, about one in ten): the game thread spends about 13 ms
  waiting for physics (bodies made and dropped as cells stream: about 8 cells being taken
  out at once in those frames) and about 4 ms loading, with 160 packages queued against 4
  in the fast frames.
- **Loaded**: 54,000 to 57,000 actors at once (1,500 m range), 1.3 to 1.85 million GPU
  scene instances, 52,224 Nanite root pages (of 57,344 at the 256 MB pool).
- **Hitches over 100 ms**: 53 to 61 per pass. **VRAM** 6.7 to 7.2 GB. **RAM** 13 to 17 GB.
- **Variance**: the three runs' p95 within 1 to 5 ms of each other.
