**Delta Megacity**, final: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1932 | 14.1 | 20.5 (20.5 to 20.5) | 26.3 | 476 | 20.3 | 14.0 | 13.2 | game | 3241 | 2 / 1 | 0.0% | 10377 | 9301 | 43008 |
| night_plan_all | drive | 3054 | 15.1 | 19.6 (19.6 to 19.6) | 24.5 | 392 | 14.7 | 15.6 | 15.5 | render | 3608 | 11 / 3 | 0.0% | 10355 | 9990 | 43008 |
| night_plan_all | fly | 5342 | 12.9 | 16.4 (16.4 to 16.4) | 19.8 | 469 | 15.3 | 14.3 | 13.1 | game | 3619 | 6 / 1 | 0.0% | 10202 | 9945 | 43008 |
| night_plan_all | all | 10328 | 13.9 | 18.8 (18.8 to 18.8) | 23.4 | 476 | 17.4 | 14.5 | 14.7 | game | 3538 | 19 / 5 | 0.0% | 10377 | 9990 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 7.56

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 2.44 / 3.31 (python 1.99, zenserver 0.08, claude 0.06)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 20.5 ms, night_plan_all/drive 19.6 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 1 a run (at most 1), night_plan_all/drive 3 a run (at most 3), night_plan_all/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10377 MB, night_plan_all/drive 10355 MB
