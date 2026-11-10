**Delta Megacity**, at1_before: 3 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_native | walk | 8025 | 11.1 | 12.9 (12.7 to 12.9) | 20.2 | 1732 | 10.3 | 12.5 | 11.6 | render | 885 | 8 / 4 | 0.0% | 7692 | 13167 | 43008 |
| night_native | drive | 4452 | 10.7 | 12.1 (11.9 to 12.2) | 18.0 | 61 | 9.9 | 11.7 | 10.7 | render | 1028 | 2 / 0 | 0.0% | 7459 | 13127 | 43008 |
| night_native | fly | 6880 | 10.0 | 13.1 (12.7 to 13.1) | 19.5 | 69 | 11.4 | 11.3 | 10.0 | game | 1198 | 5 / 0 | 0.0% | 7424 | 12804 | 43008 |
| night_native | teleport | 819 | 12.1 | 22.2 (21.6 to 22.8) | 26.1 | 72 | 21.6 | 10.5 | 9.1 | game | 942 | 1 / 0 | 36.6% | 7456 | 12507 | 43008 |
| night_native | all | 19362 | 10.6 | 12.8 (12.6 to 12.8) | 19.3 | 1732 | 10.8 | 12.1 | 11.2 | render | 978 | 15 / 4 | 0.0% | 7692 | 13167 | 43008 |
| night_plan | walk | 7337 | 12.3 | 14.4 (14.3 to 14.5) | 15.6 | 90 | 5.5 | 14.3 | 13.4 | render | 1044 | 2 / 0 | 0.0% | 7494 | 12585 | 43008 |
| night_plan | drive | 4419 | 10.8 | 12.0 (11.9 to 12.1) | 17.2 | 59 | 9.4 | 11.8 | 10.8 | render | 1022 | 2 / 0 | 0.0% | 7560 | 12612 | 43008 |
| night_plan | fly | 6829 | 10.2 | 12.6 (12.5 to 12.6) | 19.1 | 70 | 11.0 | 11.3 | 10.1 | render | 1254 | 5 / 0 | 0.0% | 7462 | 12492 | 43008 |
| night_plan | teleport | 808 | 12.0 | 22.5 (22.5 to 22.9) | 27.1 | 84 | 22.2 | 11.4 | 9.9 | game | 1051 | 1 / 0 | 38.2% | 7464 | 12462 | 43008 |
| night_plan | all | 18585 | 11.0 | 14.0 (13.9 to 14.0) | 17.3 | 90 | 9.3 | 13.5 | 12.6 | render | 1069 | 9 / 0 | 0.0% | 7582 | 12612 | 43008 |
| night_plan_all | walk | 6302 | 14.4 | 16.5 (16.3 to 16.5) | 17.5 | 96 | 7.3 | 16.4 | 15.6 | render | 1047 | 2 / 0 | 0.0% | 7617 | 12490 | 43008 |
| night_plan_all | drive | 3651 | 13.2 | 14.3 (14.0 to 14.3) | 18.0 | 61 | 10.4 | 14.2 | 13.2 | render | 1027 | 2 / 0 | 0.0% | 7585 | 11812 | 43008 |
| night_plan_all | fly | 6112 | 11.5 | 13.6 (13.3 to 13.8) | 19.6 | 79 | 12.1 | 12.6 | 11.7 | render | 1259 | 6 / 0 | 0.0% | 7586 | 11691 | 43008 |
| night_plan_all | teleport | 760 | 13.1 | 22.4 (21.9 to 23.0) | 26.6 | 75 | 22.6 | 13.2 | 12.3 | game | 1055 | 1 / 0 | 38.2% | 7586 | 11729 | 43008 |
| night_plan_all | all | 16065 | 12.9 | 16.0 (15.8 to 16.1) | 18.0 | 96 | 10.2 | 15.6 | 14.8 | render | 1076 | 10 / 0 | 0.0% | 7617 | 12490 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_native 23.83; night_plan 13.47; night_plan_all 13.48

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 1.31 / 1.62 (claude 0.72, L-Connect 3 0.12, Termius 0.08); run 2 1.41 / 2.33 (claude 0.75, L-Connect 3 0.12, Termius 0.08); run 3 0.69 / 1.34 (L-Connect 3 0.12, Termius 0.08, prismlauncher 0.06)

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_native/walk 4 a run (at most 9); VRAM over 10 GB: none
