**Delta Megacity**, at0_before: 3 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_native | walk | 8001 | 11.0 | 12.8 (12.7 to 12.8) | 19.4 | 1564 | 9.3 | 12.3 | 11.5 | render | 887 | 7 / 2 | 0.0% | 7540 | 13172 | 43008 |
| night_native | drive | 4487 | 10.6 | 11.9 (11.8 to 11.9) | 17.2 | 67 | 9.3 | 11.6 | 10.6 | render | 1028 | 2 / 0 | 0.0% | 7453 | 12936 | 43008 |
| night_native | fly | 6931 | 10.1 | 12.6 (12.5 to 12.6) | 18.8 | 70 | 10.8 | 11.2 | 10.0 | render | 1200 | 5 / 0 | 0.0% | 7455 | 12579 | 43008 |
| night_native | teleport | 819 | 11.3 | 22.8 (21.7 to 23.1) | 26.3 | 78 | 22.4 | 10.3 | 9.0 | game | 942 | 1 / 0 | 36.1% | 7456 | 11466 | 43008 |
| night_native | all | 19419 | 10.6 | 12.6 (12.6 to 12.6) | 18.8 | 1564 | 10.1 | 12.0 | 11.1 | render | 979 | 14 / 2 | 0.0% | 7540 | 13172 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_native 21.1

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.97 / 1.19 (claude 0.4, L-Connect 3 0.12, zenserver 0.07); run 2 0.98 / 1.34 (claude 0.39, L-Connect 3 0.12, zenserver 0.07); run 3 0.58 / 0.97 (L-Connect 3 0.11, zenserver 0.06, Termius 0.05)

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_native/walk 2 a run (at most 4); VRAM over 10 GB: none
