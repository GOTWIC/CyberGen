**Delta Megacity**, at1_after: 3 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_native | walk | 8613 | 9.9 | 11.3 (11.2 to 19.8) | 20.1 | 1585 | 9.1 | 10.6 | 9.6 | render | 850 | 10 / 4 | 0.0% | 7537 | 12796 | 43008 |
| night_native | drive | 5163 | 9.1 | 10.3 (10.3 to 14.6) | 17.3 | 64 | 9.2 | 9.8 | 8.5 | render | 947 | 2 / 0 | 0.0% | 7560 | 12280 | 43008 |
| night_native | fly | 6913 | 10.1 | 12.6 (12.3 to 17.7) | 19.6 | 72 | 11.0 | 11.2 | 10.0 | render | 1109 | 5 / 0 | 0.0% | 7433 | 12091 | 43008 |
| night_native | teleport | 842 | 10.1 | 22.2 (22.1 to 22.8) | 26.6 | 74 | 22.2 | 9.3 | 8.1 | game | 853 | 1 / 0 | 35.2% | 7433 | 12160 | 43008 |
| night_native | all | 20716 | 9.5 | 11.6 (11.6 to 16.8) | 19.0 | 1585 | 10.0 | 11.0 | 9.8 | render | 906 | 17 / 4 | 0.0% | 7580 | 12796 | 43008 |
| night_plan | walk | 6962 | 12.9 | 14.6 (14.6 to 23.1) | 15.4 | 91 | 6.6 | 14.6 | 13.7 | render | 1022 | 2 / 0 | 0.0% | 7493 | 12186 | 43008 |
| night_plan | drive | 4171 | 11.4 | 12.9 (12.8 to 22.9) | 17.7 | 63 | 9.7 | 12.6 | 11.6 | render | 1060 | 2 / 0 | 0.0% | 7436 | 11524 | 43008 |
| night_plan | fly | 6745 | 10.4 | 12.9 (12.8 to 16.1) | 19.3 | 67 | 11.2 | 11.4 | 10.2 | render | 1273 | 5 / 0 | 0.0% | 7463 | 11404 | 43008 |
| night_plan | teleport | 791 | 12.4 | 23.0 (21.7 to 23.4) | 26.8 | 80 | 23.0 | 12.0 | 10.9 | game | 1040 | 1 / 0 | 38.6% | 7463 | 11438 | 43008 |
| night_plan | all | 17878 | 11.4 | 14.4 (14.3 to 22.8) | 17.6 | 91 | 9.5 | 14.1 | 13.3 | render | 1065 | 9 / 0 | 0.0% | 7493 | 12186 | 43008 |
| night_plan_all | walk | 5999 | 15.0 | 16.8 (16.8 to 30.7) | 17.5 | 76 | 7.5 | 16.8 | 15.9 | render | 1026 | 2 / 0 | 0.0% | 7680 | 10435 | 43008 |
| night_plan_all | drive | 3427 | 14.0 | 15.3 (15.2 to 23.1) | 18.3 | 68 | 10.7 | 15.2 | 14.3 | render | 1064 | 2 / 0 | 0.0% | 7557 | 10472 | 43008 |
| night_plan_all | fly | 6018 | 11.6 | 13.7 (13.7 to 21.8) | 20.3 | 70 | 12.0 | 12.9 | 11.9 | render | 1285 | 5 / 0 | 0.0% | 7557 | 10363 | 43008 |
| night_plan_all | teleport | 746 | 13.8 | 22.9 (22.9 to 23.6) | 28.3 | 75 | 22.8 | 14.3 | 13.5 | game | 1044 | 1 / 0 | 39.5% | 7588 | 10314 | 43008 |
| night_plan_all | all | 15444 | 13.7 | 16.4 (16.4 to 23.4) | 18.3 | 76 | 10.4 | 16.2 | 15.4 | render | 1070 | 9 / 0 | 0.0% | 7680 | 10472 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_native 20.91; night_plan 13.05; night_plan_all 13.62

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 1.02 / 1.3 (claude 0.68, prismlauncher 0.06, NVIDIA Overlay 0.04); run 2 1.07 / 1.42 (claude 0.7, prismlauncher 0.06, zenserver 0.04); run 3 0.68 / 0.87 (claude 0.33, prismlauncher 0.06, zenserver 0.04)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 16.8 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_native/walk 4 a run (at most 4); VRAM over 10 GB: none
