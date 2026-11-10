**Delta Megacity**, at0_after: 3 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_native | walk | 7886 | 11.1 | 12.8 (12.8 to 13.0) | 19.7 | 1772 | 10.0 | 12.4 | 11.6 | render | 893 | 7 / 5 | 0.0% | 7609 | 12554 | 43008 |
| night_native | drive | 4470 | 10.7 | 12.0 (11.8 to 12.2) | 17.6 | 67 | 9.4 | 11.6 | 10.6 | render | 1028 | 2 / 0 | 0.0% | 7455 | 12349 | 43008 |
| night_native | fly | 6914 | 10.0 | 12.6 (12.4 to 12.8) | 19.1 | 76 | 11.0 | 11.2 | 10.0 | render | 1201 | 5 / 0 | 0.0% | 7457 | 11669 | 43008 |
| night_native | teleport | 821 | 10.9 | 22.5 (21.9 to 22.8) | 26.2 | 75 | 22.0 | 10.2 | 9.1 | game | 942 | 1 / 0 | 35.9% | 7457 | 11724 | 43008 |
| night_native | all | 19253 | 10.5 | 12.7 (12.7 to 12.7) | 19.1 | 1772 | 10.3 | 12.0 | 11.1 | render | 980 | 15 / 5 | 0.0% | 7609 | 12554 | 43008 |
| night_plan | walk | 7414 | 12.2 | 14.2 (14.2 to 14.3) | 15.3 | 83 | 5.3 | 14.1 | 13.3 | render | 1043 | 2 / 0 | 0.0% | 7494 | 11798 | 43008 |
| night_plan | drive | 4444 | 10.8 | 11.9 (11.8 to 12.0) | 17.2 | 58 | 9.2 | 11.7 | 10.7 | render | 1022 | 2 / 0 | 0.0% | 7591 | 11817 | 43008 |
| night_plan | fly | 6840 | 10.2 | 12.5 (12.5 to 12.5) | 18.9 | 70 | 11.0 | 11.3 | 10.1 | render | 1252 | 5 / 0 | 0.0% | 7464 | 11701 | 43008 |
| night_plan | teleport | 810 | 12.1 | 22.2 (21.9 to 23.1) | 26.3 | 63 | 21.8 | 11.3 | 9.9 | game | 1051 | 1 / 0 | 37.6% | 7465 | 10296 | 43008 |
| night_plan | all | 18691 | 10.9 | 13.8 (13.8 to 13.9) | 16.9 | 83 | 9.2 | 13.4 | 12.5 | render | 1069 | 9 / 0 | 0.0% | 7593 | 11817 | 43008 |
| night_plan_fog | walk | 6904 | 13.1 | 15.1 (15.1 to 15.1) | 16.2 | 86 | 6.0 | 15.1 | 14.2 | render | 1045 | 2 / 0 | 0.0% | 7617 | 10387 | 43008 |
| night_plan_fog | drive | 4106 | 11.7 | 12.8 (12.7 to 12.8) | 17.2 | 58 | 9.6 | 12.6 | 11.7 | render | 1024 | 2 / 0 | 0.0% | 7587 | 10421 | 43008 |
| night_plan_fog | fly | 6255 | 11.2 | 13.0 (12.8 to 13.0) | 19.3 | 68 | 11.4 | 12.3 | 11.2 | render | 1264 | 5 / 0 | 0.0% | 7587 | 10311 | 43008 |
| night_plan_fog | teleport | 795 | 12.3 | 22.2 (22.0 to 23.8) | 26.5 | 76 | 22.2 | 11.8 | 10.8 | game | 1052 | 1 / 0 | 38.4% | 7588 | 10314 | 43008 |
| night_plan_fog | all | 17265 | 11.8 | 14.7 (14.7 to 14.8) | 17.1 | 86 | 9.4 | 14.3 | 13.5 | render | 1071 | 9 / 0 | 0.0% | 7618 | 10421 | 43008 |
| night_plan_all | walk | 6365 | 14.2 | 16.2 (16.2 to 16.3) | 17.3 | 94 | 7.2 | 16.2 | 15.4 | render | 1048 | 2 / 0 | 0.0% | 7619 | 10327 | 43008 |
| night_plan_all | drive | 3681 | 13.1 | 14.1 (14.0 to 14.1) | 18.0 | 59 | 10.3 | 14.0 | 13.0 | render | 1027 | 2 / 0 | 0.0% | 7588 | 9749 | 43008 |
| night_plan_all | fly | 6114 | 11.4 | 13.4 (13.2 to 13.7) | 19.9 | 72 | 12.0 | 12.7 | 11.7 | render | 1258 | 5 / 0 | 0.0% | 7587 | 9663 | 43008 |
| night_plan_all | teleport | 766 | 13.1 | 22.3 (22.2 to 22.3) | 26.6 | 77 | 22.2 | 13.2 | 12.3 | game | 1055 | 1 / 0 | 38.6% | 7619 | 9704 | 43008 |
| night_plan_all | all | 16157 | 12.8 | 15.8 (15.8 to 15.9) | 17.7 | 94 | 10.1 | 15.4 | 14.7 | render | 1075 | 9 / 0 | 0.0% | 7620 | 10327 | 43008 |
| night_plan_256 | walk | 6437 | 14.1 | 16.1 (16.0 to 16.1) | 17.1 | 97 | 7.1 | 16.0 | 15.2 | render | 933 | 2 / 0 | 0.0% | 7621 | 8595 | 43008 |
| night_plan_256 | drive | 3700 | 13.0 | 14.0 (13.9 to 14.0) | 18.0 | 66 | 10.4 | 13.9 | 13.0 | render | 1002 | 2 / 0 | 0.0% | 7717 | 8323 | 43008 |
| night_plan_256 | fly | 6177 | 11.3 | 13.3 (13.2 to 13.6) | 20.1 | 73 | 11.7 | 12.5 | 11.6 | render | 1194 | 5 / 0 | 0.0% | 7589 | 8219 | 43008 |
| night_plan_256 | teleport | 757 | 12.8 | 23.1 (22.1 to 23.2) | 26.9 | 79 | 23.0 | 12.9 | 12.1 | game | 967 | 1 / 0 | 38.2% | 7594 | 8244 | 43008 |
| night_plan_256 | all | 16309 | 12.7 | 15.7 (15.6 to 15.7) | 17.6 | 97 | 10.1 | 15.3 | 14.5 | render | 991 | 9 / 0 | 0.0% | 7717 | 8595 | 43008 |
| night_plan_1024 | walk | 6263 | 14.5 | 16.5 (16.5 to 16.6) | 17.6 | 94 | 7.4 | 16.5 | 15.6 | render | 1248 | 2 / 0 | 0.0% | 7622 | 8307 | 43008 |
| night_plan_1024 | drive | 3663 | 13.2 | 14.1 (14.1 to 14.2) | 18.6 | 60 | 10.3 | 14.1 | 13.1 | render | 1104 | 2 / 0 | 0.0% | 7590 | 8121 | 43008 |
| night_plan_1024 | fly | 5962 | 11.6 | 14.1 (14.0 to 14.2) | 20.4 | 71 | 12.4 | 12.9 | 11.7 | render | 1389 | 6 / 0 | 0.0% | 7590 | 7857 | 43008 |
| night_plan_1024 | teleport | 755 | 13.2 | 23.2 (22.3 to 23.4) | 27.3 | 82 | 23.1 | 13.4 | 12.4 | game | 1190 | 1 / 0 | 39.0% | 7622 | 7900 | 43008 |
| night_plan_1024 | all | 15889 | 13.0 | 16.1 (16.1 to 16.1) | 18.3 | 94 | 10.4 | 15.7 | 14.9 | render | 1262 | 10 / 0 | 0.0% | 7622 | 8307 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_native 21.37; night_plan 13.2; night_plan_fog 13.33; night_plan_all 13.72; night_plan_256 13.52; night_plan_1024 13.94

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 1.13 / 1.42 (claude 0.6, L-Connect 3 0.11, Termius 0.05); run 2 1.13 / 1.34 (claude 0.59, L-Connect 3 0.11, Termius 0.05); run 3 0.66 / 1.24 (L-Connect 3 0.11, claude 0.11, prismlauncher 0.06)

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_native/walk 5 a run (at most 5), night_plan_all/walk 0 a run (at most 1), night_plan_256/walk 0 a run (at most 1), night_plan_1024/walk 0 a run (at most 1); VRAM over 10 GB: none
