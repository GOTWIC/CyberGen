**Delta Megacity**, final: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1935 | 13.9 | 21.1 (21.1 to 21.1) | 29.0 | 482 | 20.7 | 14.9 | 13.1 | game | 3178 | 7 / 2 | 0.0% | 10684 | 11971 | 43008 |
| night_plan_all | drive | 2955 | 15.1 | 20.4 (20.4 to 20.4) | 38.2 | 396 | 15.9 | 16.0 | 15.4 | render | 3580 | 19 / 7 | 0.0% | 10569 | 10865 | 43008 |
| night_plan_all | fly | 5261 | 12.9 | 17.0 (17.0 to 17.0) | 20.7 | 504 | 16.3 | 14.5 | 13.1 | game | 3607 | 10 / 2 | 0.0% | 10388 | 10661 | 43008 |
| night_plan_all | all | 10151 | 13.9 | 19.2 (19.2 to 19.2) | 28.2 | 504 | 17.7 | 15.1 | 14.7 | game | 3515 | 36 / 11 | 0.0% | 10684 | 11971 | 43008 |
| night_life_noplaces | walk | 2081 | 13.5 | 18.3 (18.3 to 18.3) | 24.8 | 454 | 17.9 | 14.1 | 13.2 | game | 3171 | 4 / 3 | 0.0% | 10550 | 9954 | 43008 |
| night_life_noplaces | drive | 3048 | 15.1 | 19.5 (19.5 to 19.5) | 27.6 | 384 | 14.2 | 15.4 | 15.4 | gpu | 3572 | 10 / 3 | 0.0% | 10519 | 10706 | 43008 |
| night_life_noplaces | fly | 5357 | 12.8 | 16.4 (16.4 to 16.4) | 19.8 | 459 | 14.8 | 14.4 | 13.2 | game | 3595 | 6 / 1 | 0.0% | 10266 | 10437 | 43008 |
| night_life_noplaces | all | 10486 | 13.7 | 18.0 (18.0 to 18.0) | 22.9 | 459 | 15.2 | 14.5 | 14.7 | game | 3503 | 20 / 7 | 0.0% | 10550 | 10706 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 17.91; night_life_noplaces 15.5

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 2.52 / 5.15 (python 1.69, OneDrive.Sync.Service 0.39, claude 0.09)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 21.1 ms, night_plan_all/drive 20.4 ms, night_plan_all/fly 17.0 ms, night_life_noplaces/walk 18.3 ms, night_life_noplaces/drive 19.5 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 2 a run (at most 2), night_plan_all/drive 7 a run (at most 7), night_plan_all/fly 2 a run (at most 2), night_life_noplaces/walk 3 a run (at most 3), night_life_noplaces/drive 3 a run (at most 3), night_life_noplaces/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10684 MB, night_plan_all/drive 10569 MB, night_plan_all/fly 10388 MB, night_life_noplaces/walk 10550 MB, night_life_noplaces/drive 10519 MB, night_life_noplaces/fly 10266 MB
