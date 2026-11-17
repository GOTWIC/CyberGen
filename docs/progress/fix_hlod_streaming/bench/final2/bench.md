**Delta Megacity**, final2: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1914 | 14.1 | 21.7 (21.7 to 21.7) | 26.3 | 526 | 21.6 | 14.0 | 13.3 | game | 3103 | 3 / 1 | 0.0% | 10372 | 11378 | 43008 |
| night_plan_all | drive | 3108 | 15.1 | 19.0 (19.0 to 19.0) | 22.3 | 398 | 15.3 | 14.9 | 15.3 | gpu | 3582 | 3 / 1 | 0.0% | 10381 | 11392 | 43008 |
| night_plan_all | fly | 5351 | 12.9 | 16.4 (16.4 to 16.4) | 19.8 | 476 | 15.1 | 14.2 | 13.1 | game | 3622 | 6 / 1 | 0.0% | 10227 | 7357 | 43008 |
| night_plan_all | all | 10373 | 13.9 | 18.7 (18.7 to 18.7) | 23.0 | 526 | 17.4 | 14.3 | 14.7 | game | 3531 | 12 / 3 | 0.0% | 10381 | 11392 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 7.91

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 2.25 / 2.84 (python 1.82, zenserver 0.09, claude 0.07)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 21.7 ms, night_plan_all/drive 19.0 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 1 a run (at most 1), night_plan_all/drive 1 a run (at most 1), night_plan_all/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10372 MB, night_plan_all/drive 10381 MB
