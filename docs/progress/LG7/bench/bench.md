**Delta Megacity**, final: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1865 | 14.6 | 24.6 (24.6 to 24.6) | 34.2 | 498 | 23.8 | 14.5 | 13.4 | game | 2394 | 3 / 1 | 0.0% | 10327 | 9949 | 43008 |
| night_plan_all | drive | 2947 | 15.4 | 22.4 (22.4 to 22.4) | 30.3 | 394 | 19.0 | 15.8 | 15.6 | game | 1706 | 11 / 3 | 0.0% | 10242 | 9238 | 43008 |
| night_plan_all | fly | 4983 | 13.0 | 22.0 (22.0 to 22.0) | 29.5 | 452 | 20.4 | 14.6 | 13.5 | game | 1740 | 8 / 2 | 0.0% | 10215 | 9049 | 43008 |
| night_plan_all | all | 9795 | 14.2 | 22.6 (22.6 to 22.6) | 30.8 | 498 | 20.4 | 14.9 | 15.0 | game | 1814 | 22 / 6 | 0.0% | 10327 | 9949 | 43008 |
| night_life_noairwater | walk | 1906 | 14.2 | 24.8 (24.8 to 24.8) | 32.8 | 473 | 24.7 | 14.1 | 13.1 | game | 2499 | 4 / 1 | 0.0% | 10184 | 6871 | 43008 |
| night_life_noairwater | drive | 2946 | 15.5 | 21.7 (21.7 to 21.7) | 30.8 | 398 | 17.8 | 15.6 | 15.5 | game | 1734 | 10 / 2 | 0.0% | 10248 | 7689 | 43008 |
| night_life_noairwater | fly | 5133 | 12.8 | 20.3 (20.3 to 20.3) | 26.6 | 488 | 18.4 | 14.7 | 13.6 | game | 1725 | 7 / 1 | 0.0% | 10092 | 7604 | 43008 |
| night_life_noairwater | all | 9985 | 14.1 | 21.7 (21.7 to 21.7) | 30.0 | 488 | 19.3 | 14.8 | 15.0 | game | 1824 | 21 / 4 | 0.0% | 10248 | 7689 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 15.77; night_life_noairwater 14.12

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 3.29 / 4.59 (python 2.88, zenserver 0.06, claude 0.04)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 24.6 ms, night_plan_all/drive 22.4 ms, night_plan_all/fly 22.0 ms, night_life_noairwater/walk 24.8 ms, night_life_noairwater/drive 21.7 ms, night_life_noairwater/fly 20.3 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 1 a run (at most 1), night_plan_all/drive 3 a run (at most 3), night_plan_all/fly 2 a run (at most 2), night_life_noairwater/walk 1 a run (at most 1), night_life_noairwater/drive 2 a run (at most 2), night_life_noairwater/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10327 MB, night_plan_all/drive 10242 MB, night_life_noairwater/drive 10248 MB
