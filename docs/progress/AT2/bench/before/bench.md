**Delta Megacity**, at2_before: 3 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_native | walk | 9011 | 9.6 | 11.0 (10.9 to 17.4) | 19.2 | 1620 | 9.1 | 10.6 | 9.4 | render | 854 | 9 / 5 | 0.0% | 7629 | 11868 | 43008 |
| night_native | drive | 5212 | 9.0 | 10.3 (10.2 to 14.0) | 17.1 | 59 | 9.0 | 9.7 | 8.3 | render | 946 | 2 / 0 | 0.0% | 7537 | 11042 | 43008 |
| night_native | fly | 7055 | 9.8 | 12.7 (12.3 to 16.3) | 19.2 | 63 | 11.0 | 10.9 | 9.8 | game | 1111 | 5 / 0 | 0.0% | 7426 | 10911 | 43008 |
| night_native | teleport | 842 | 11.2 | 23.1 (22.9 to 23.4) | 27.9 | 73 | 22.9 | 9.3 | 8.0 | game | 853 | 1 / 0 | 35.6% | 7445 | 10129 | 43008 |
| night_native | all | 21278 | 9.6 | 11.3 (11.3 to 16.1) | 18.8 | 1620 | 9.9 | 10.7 | 9.6 | render | 912 | 16 / 5 | 0.0% | 7629 | 11868 | 43008 |
| night_plan | walk | 7143 | 12.6 | 14.2 (14.1 to 23.0) | 15.2 | 83 | 6.8 | 14.2 | 13.3 | render | 1022 | 2 / 0 | 0.0% | 7464 | 10227 | 43008 |
| night_plan | drive | 4258 | 11.2 | 12.5 (12.5 to 22.8) | 18.4 | 62 | 9.8 | 12.2 | 11.2 | render | 1060 | 2 / 0 | 0.0% | 7558 | 10257 | 43008 |
| night_plan | fly | 6796 | 10.2 | 13.2 (12.9 to 14.8) | 19.9 | 63 | 11.7 | 11.3 | 10.0 | game | 1272 | 5 / 0 | 0.0% | 7430 | 10147 | 43008 |
| night_plan | teleport | 794 | 12.4 | 23.0 (22.3 to 23.3) | 27.0 | 78 | 22.5 | 11.7 | 10.8 | game | 1040 | 1 / 0 | 39.1% | 7449 | 10117 | 43008 |
| night_plan | all | 18234 | 11.2 | 14.0 (13.9 to 22.6) | 17.8 | 83 | 9.7 | 13.6 | 12.8 | render | 1064 | 9 / 0 | 0.0% | 7558 | 10257 | 43008 |
| night_plan_all | walk | 6183 | 14.6 | 16.3 (16.2 to 30.4) | 16.9 | 96 | 7.7 | 16.2 | 15.4 | render | 1026 | 2 / 0 | 0.0% | 7680 | 10137 | 43008 |
| night_plan_all | drive | 3543 | 13.5 | 14.7 (14.7 to 23.0) | 18.7 | 58 | 10.8 | 14.6 | 13.6 | render | 1063 | 2 / 0 | 0.0% | 7554 | 8592 | 43008 |
| night_plan_all | fly | 6110 | 11.4 | 13.9 (13.7 to 21.6) | 20.5 | 73 | 12.6 | 12.7 | 11.6 | render | 1281 | 5 / 0 | 0.0% | 7555 | 8475 | 43008 |
| night_plan_all | teleport | 744 | 13.6 | 24.0 (23.4 to 24.1) | 28.1 | 67 | 23.4 | 13.9 | 12.9 | game | 1044 | 2 / 0 | 39.1% | 7573 | 8455 | 43008 |
| night_plan_all | all | 15846 | 13.3 | 16.0 (16.0 to 23.0) | 18.6 | 96 | 10.6 | 15.7 | 14.9 | render | 1070 | 9 / 0 | 0.0% | 7680 | 10137 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_native 19.95; night_plan 13.78; night_plan_all 13.89

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.69 / 1.7 (claude 0.38, zenserver 0.05, L-Connect 3 0.04); run 2 0.66 / 1.21 (claude 0.37, zenserver 0.04, L-Connect 3 0.04); run 3 0.97 / 1.28 (claude 0.68, zenserver 0.04, NVIDIA Overlay 0.04)

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_native/walk 5 a run (at most 7); VRAM over 10 GB: none
