**Delta Megacity**, at3_after_sky: 3 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan | walk | 6624 | 12.7 | 15.2 (14.9 to 15.2) | 21.2 | 1610 | 13.2 | 14.7 | 13.8 | render | 1063 | 11 / 4 | 0.0% | 7501 | 10481 | 43008 |
| night_plan | drive | 4041 | 11.8 | 13.2 (13.0 to 13.2) | 18.8 | 66 | 10.0 | 12.9 | 11.8 | render | 1079 | 2 / 0 | 0.0% | 6782 | 9741 | 43008 |
| night_plan | fly | 6554 | 10.6 | 13.4 (13.3 to 13.4) | 20.0 | 75 | 12.0 | 11.6 | 10.4 | game | 1336 | 5 / 0 | 0.0% | 6665 | 9408 | 43008 |
| night_plan | teleport | 776 | 12.7 | 23.3 (23.3 to 23.5) | 28.2 | 73 | 23.2 | 12.6 | 11.5 | game | 1044 | 1 / 0 | 39.3% | 6690 | 9420 | 43008 |
| night_plan | all | 17219 | 11.7 | 14.7 (14.6 to 14.7) | 20.2 | 1610 | 11.7 | 14.0 | 13.1 | render | 1106 | 18 / 4 | 0.0% | 7501 | 10481 | 43008 |
| night_plan_all | walk | 5910 | 15.1 | 17.1 (16.9 to 17.2) | 17.7 | 85 | 7.7 | 17.0 | 16.1 | render | 1068 | 2 / 0 | 0.0% | 6828 | 9476 | 43008 |
| night_plan_all | drive | 3290 | 14.5 | 15.8 (15.5 to 15.9) | 19.8 | 61 | 11.0 | 15.7 | 14.8 | render | 1082 | 2 / 0 | 0.0% | 6829 | 9507 | 43008 |
| night_plan_all | fly | 5890 | 11.8 | 14.1 (14.1 to 14.2) | 20.5 | 70 | 12.8 | 13.1 | 12.1 | render | 1341 | 5 / 0 | 0.0% | 6818 | 9393 | 43008 |
| night_plan_all | teleport | 747 | 14.3 | 23.6 (22.8 to 23.8) | 28.5 | 67 | 23.4 | 14.9 | 14.0 | game | 1049 | 1 / 0 | 40.1% | 6822 | 9505 | 43008 |
| night_plan_all | all | 15090 | 14.2 | 16.7 (16.6 to 16.8) | 19.0 | 85 | 10.8 | 16.4 | 15.6 | render | 1112 | 9 / 0 | 0.0% | 6916 | 9507 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan 22.31; night_plan_all 14.2

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.99 / 1.24 (claude 0.63, zenserver 0.05, L-Connect 3 0.04); run 2 0.93 / 1.24 (claude 0.62, zenserver 0.05, L-Connect 3 0.05); run 3 0.97 / 1.48 (claude 0.64, zenserver 0.05, L-Connect 3 0.04)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 17.1 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan/walk 4 a run (at most 7), night_plan_all/walk 0 a run (at most 1); VRAM over 10 GB: none
