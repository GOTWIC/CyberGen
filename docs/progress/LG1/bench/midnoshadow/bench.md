**Delta Megacity**, lg1_midnoshadow: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1827 | 15.4 | 22.8 (22.8 to 22.8) | 30.3 | 493 | 21.7 | 12.8 | 15.0 | game | 1907 | 3 / 1 | 0.0% | 10274 | 11621 | 43008 |
| night_plan_all | drive | 3311 | 14.1 | 18.7 (18.7 to 18.7) | 25.7 | 391 | 15.0 | 14.2 | 13.8 | game | 676 | 4 / 1 | 0.0% | 10058 | 11621 | 43008 |
| night_plan_all | fly | 5491 | 12.1 | 18.9 (18.9 to 18.9) | 25.3 | 459 | 17.6 | 13.4 | 12.3 | game | 1265 | 7 / 1 | 0.0% | 9739 | 11482 | 43008 |
| night_plan_all | all | 10629 | 13.4 | 19.6 (19.6 to 19.6) | 26.6 | 493 | 17.9 | 13.6 | 14.3 | game | 1137 | 14 / 3 | 0.0% | 10274 | 11621 | 43008 |
| night_life_near20m | walk | 1844 | 15.5 | 22.1 (22.1 to 22.1) | 28.0 | 467 | 21.3 | 13.7 | 15.8 | game | 1618 | 2 / 1 | 0.0% | 10286 | 11482 | 43008 |
| night_life_near20m | drive | 3293 | 14.0 | 19.3 (19.3 to 19.3) | 25.9 | 423 | 15.6 | 14.2 | 13.8 | game | 675 | 5 / 2 | 0.0% | 10066 | 10209 | 43008 |
| night_life_near20m | fly | 5542 | 12.0 | 18.7 (18.7 to 18.7) | 25.4 | 458 | 16.6 | 13.4 | 12.3 | game | 1265 | 7 / 1 | 0.0% | 9745 | 10161 | 43008 |
| night_life_near20m | all | 10679 | 13.3 | 19.5 (19.5 to 19.5) | 26.8 | 467 | 17.4 | 13.6 | 14.5 | game | 1147 | 14 / 4 | 0.0% | 10286 | 11482 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 6.76; night_life_near20m 10.64

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.63 / 1.03 (claude 0.42, zenserver 0.07, NVIDIA Overlay 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 22.8 ms, night_plan_all/drive 18.7 ms, night_plan_all/fly 18.9 ms, night_life_near20m/walk 22.1 ms, night_life_near20m/drive 19.3 ms, night_life_near20m/fly 18.7 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 1 a run (at most 1), night_plan_all/drive 1 a run (at most 1), night_plan_all/fly 1 a run (at most 1), night_life_near20m/walk 1 a run (at most 1), night_life_near20m/drive 2 a run (at most 2), night_life_near20m/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10274 MB, night_life_near20m/walk 10286 MB
