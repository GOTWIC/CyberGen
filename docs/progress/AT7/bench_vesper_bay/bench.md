**Vesper Bay**, at7_vesper_bay: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 2440 | 11.9 | 13.3 (13.3 to 13.3) | 21.0 | 74 | 12.8 | 13.0 | 12.3 | render | 508 | 1 / 0 | 0.0% | 6703 | 12103 | 42496 |
| night_plan_all | drive | 3462 | 13.7 | 15.6 (15.6 to 15.6) | 19.3 | 92 | 11.8 | 15.0 | 14.2 | render | 713 | 3 / 0 | 0.0% | 6738 | 12049 | 42496 |
| night_plan_all | fly | 7459 | 11.1 | 12.4 (12.4 to 12.4) | 16.1 | 67 | 10.1 | 12.2 | 11.4 | render | 1006 | 7 / 0 | 0.0% | 6739 | 11990 | 42496 |
| night_plan_all | all | 13361 | 11.8 | 14.6 (14.6 to 14.6) | 18.1 | 92 | 10.7 | 14.3 | 13.6 | render | 803 | 11 / 0 | 0.0% | 6739 | 12103 | 42496 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 11.79

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.26 / 0.75 (zenserver 0.08, claude 0.04, NVIDIA Overlay 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: none; VRAM over 10 GB: none
