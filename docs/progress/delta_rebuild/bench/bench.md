**Delta Megacity**, final: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1761 | 15.7 | 19.3 (19.3 to 19.3) | 23.8 | 498 | 18.7 | 13.3 | 15.4 | game | 3557 | 3 / 2 | 0.0% | 10524 | 9823 | 43520 |
| night_plan_all | drive | 3144 | 14.9 | 18.7 (18.7 to 18.7) | 22.9 | 412 | 15.1 | 14.9 | 14.9 | game | 3638 | 6 / 1 | 0.0% | 10497 | 10090 | 43520 |
| night_plan_all | fly | 5373 | 12.8 | 16.6 (16.6 to 16.6) | 19.8 | 475 | 15.2 | 14.3 | 13.3 | game | 3694 | 6 / 1 | 0.0% | 10344 | 9484 | 43520 |
| night_plan_all | all | 10278 | 14.2 | 18.0 (18.0 to 18.0) | 21.9 | 498 | 15.9 | 14.4 | 15.0 | game | 3661 | 15 / 4 | 0.0% | 10524 | 10090 | 43520 |
| night_life_noplaces | walk | 1762 | 15.6 | 19.8 (19.8 to 19.8) | 26.0 | 487 | 18.9 | 13.6 | 15.4 | game | 3753 | 4 / 2 | 0.0% | 10381 | 9704 | 43520 |
| night_life_noplaces | drive | 3117 | 14.8 | 18.8 (18.8 to 18.8) | 25.5 | 425 | 14.5 | 15.2 | 15.0 | render | 3617 | 12 / 3 | 0.0% | 10476 | 10855 | 43520 |
| night_life_noplaces | fly | 5381 | 12.7 | 16.8 (16.8 to 16.8) | 20.6 | 504 | 14.6 | 14.4 | 13.3 | game | 3665 | 7 / 1 | 0.0% | 10255 | 10006 | 43520 |
| night_life_noplaces | all | 10260 | 14.1 | 18.1 (18.1 to 18.1) | 22.8 | 504 | 15.2 | 14.6 | 14.9 | game | 3655 | 23 / 6 | 0.0% | 10476 | 10855 | 43520 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 14.17; night_life_noplaces 12.82

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 1.51 / 2.73 (python 1.07, claude 0.07, zenserver 0.06)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 19.3 ms, night_plan_all/drive 18.7 ms, night_life_noplaces/walk 19.8 ms, night_life_noplaces/drive 18.8 ms, night_life_noplaces/fly 16.8 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 2 a run (at most 2), night_plan_all/drive 1 a run (at most 1), night_plan_all/fly 1 a run (at most 1), night_life_noplaces/walk 2 a run (at most 2), night_life_noplaces/drive 3 a run (at most 3), night_life_noplaces/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10524 MB, night_plan_all/drive 10497 MB, night_plan_all/fly 10344 MB, night_life_noplaces/walk 10381 MB, night_life_noplaces/drive 10476 MB, night_life_noplaces/fly 10255 MB
