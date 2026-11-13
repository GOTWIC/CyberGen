**Delta Megacity**, at4_before: 3 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_native | walk | 8319 | 10.5 | 13.3 (13.1 to 14.3) | 18.9 | 103 | 9.6 | 12.7 | 9.8 | render | 1843 | 3 / 1 | 0.0% | 9095 | 12525 | 43008 |
| night_native | drive | 5119 | 9.2 | 10.6 (10.4 to 10.6) | 16.8 | 65 | 9.2 | 9.9 | 8.5 | render | 1240 | 2 / 0 | 0.0% | 9010 | 12562 | 43008 |
| night_native | fly | 6597 | 10.6 | 13.7 (13.1 to 14.2) | 21.1 | 68 | 11.7 | 11.6 | 10.5 | game | 1921 | 6 / 0 | 0.0% | 9011 | 12479 | 43008 |
| night_native | teleport | 842 | 10.4 | 22.6 (22.4 to 23.0) | 26.7 | 85 | 22.5 | 9.4 | 8.2 | game | 855 | 1 / 0 | 35.6% | 8982 | 12414 | 43008 |
| night_native | all | 19981 | 9.9 | 13.1 (12.8 to 13.9) | 19.1 | 104 | 10.5 | 12.3 | 10.3 | render | 1735 | 11 / 1 | 0.0% | 9095 | 12562 | 43008 |
| night_plan | walk | 6654 | 13.4 | 15.5 (15.5 to 16.0) | 17.0 | 82 | 7.0 | 15.5 | 14.0 | render | 2384 | 2 / 0 | 0.0% | 9204 | 12445 | 43008 |
| night_plan | drive | 4036 | 11.8 | 13.2 (13.1 to 13.2) | 17.7 | 66 | 9.9 | 12.8 | 11.8 | render | 1379 | 2 / 0 | 0.0% | 9281 | 8922 | 43008 |
| night_plan | fly | 6276 | 11.0 | 13.6 (13.6 to 14.9) | 20.5 | 78 | 12.0 | 12.2 | 11.1 | render | 2088 | 5 / 0 | 0.0% | 9217 | 8902 | 43008 |
| night_plan | teleport | 774 | 12.6 | 23.2 (22.6 to 23.5) | 27.3 | 81 | 23.0 | 12.5 | 11.5 | game | 1046 | 1 / 0 | 38.4% | 9185 | 8827 | 43008 |
| night_plan | all | 16877 | 12.0 | 15.3 (15.2 to 15.6) | 18.5 | 82 | 10.1 | 14.9 | 13.6 | render | 1949 | 10 / 0 | 0.0% | 9281 | 12445 | 43008 |
| night_plan_all | walk | 5814 | 15.4 | 17.4 (17.4 to 17.5) | 18.6 | 91 | 7.9 | 17.4 | 16.4 | render | 2405 | 2 / 0 | 0.0% | 9371 | 9059 | 43008 |
| night_plan_all | drive | 3286 | 14.5 | 15.7 (15.6 to 15.8) | 19.2 | 66 | 10.8 | 15.7 | 14.7 | render | 1383 | 2 / 0 | 0.0% | 9340 | 8861 | 43008 |
| night_plan_all | fly | 5638 | 12.4 | 14.8 (14.7 to 15.2) | 22.1 | 80 | 13.3 | 13.5 | 12.6 | render | 2094 | 6 / 0 | 0.0% | 9339 | 8768 | 43008 |
| night_plan_all | teleport | 738 | 14.5 | 23.4 (23.3 to 24.1) | 28.3 | 79 | 23.4 | 14.9 | 14.0 | game | 1050 | 1 / 0 | 39.9% | 9308 | 8724 | 43008 |
| night_plan_all | all | 14723 | 14.3 | 17.1 (17.0 to 17.1) | 19.7 | 92 | 11.1 | 16.8 | 15.9 | render | 1984 | 10 / 0 | 0.0% | 9436 | 9059 | 43008 |
| dusk_plan | walk | 6768 | 13.3 | 15.1 (14.9 to 15.1) | 16.3 | 93 | 7.1 | 15.0 | 14.1 | render | 1810 | 2 / 0 | 0.0% | 9242 | 8983 | 43008 |
| dusk_plan | drive | 4102 | 11.6 | 13.0 (12.9 to 13.1) | 17.7 | 65 | 9.8 | 12.7 | 11.7 | render | 1139 | 2 / 0 | 0.0% | 9306 | 8879 | 43008 |
| dusk_plan | fly | 6280 | 10.9 | 13.9 (13.8 to 15.1) | 20.6 | 74 | 12.2 | 12.3 | 11.2 | render | 2143 | 5 / 0 | 0.0% | 9274 | 8769 | 43008 |
| dusk_plan | teleport | 778 | 12.5 | 23.3 (23.2 to 23.3) | 27.1 | 82 | 23.0 | 12.4 | 11.6 | game | 1046 | 1 / 0 | 38.6% | 9188 | 8716 | 43008 |
| dusk_plan | all | 17150 | 11.8 | 14.9 (14.7 to 14.9) | 18.3 | 93 | 10.0 | 14.5 | 13.7 | render | 1786 | 9 / 0 | 0.0% | 9306 | 8983 | 43008 |
| day_plan | walk | 8883 | 10.3 | 11.2 (11.2 to 11.2) | 13.8 | 87 | 4.9 | 11.1 | 9.9 | render | 1575 | 2 / 0 | 0.0% | 9065 | 8847 | 43008 |
| day_plan | drive | 5079 | 9.3 | 10.5 (10.5 to 10.6) | 16.8 | 64 | 9.0 | 10.0 | 8.6 | render | 1580 | 2 / 0 | 0.0% | 9034 | 8885 | 43008 |
| day_plan | fly | 6342 | 10.8 | 13.5 (13.4 to 13.8) | 20.2 | 70 | 11.8 | 11.7 | 10.6 | game | 2158 | 5 / 0 | 0.0% | 9033 | 8780 | 43008 |
| day_plan | teleport | 830 | 11.6 | 22.7 (22.4 to 22.8) | 26.9 | 78 | 22.1 | 9.6 | 8.3 | game | 815 | 2 / 0 | 35.5% | 9001 | 8713 | 43008 |
| day_plan | all | 20322 | 10.0 | 11.7 (11.7 to 11.8) | 17.4 | 87 | 9.2 | 11.4 | 10.4 | render | 1674 | 10 / 0 | 0.0% | 9065 | 8885 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_native 25.32; night_plan 16.47; night_plan_all 17.08; dusk_plan 16.37; day_plan 15.83

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.99 / 1.52 (claude 0.65, zenserver 0.04, L-Connect 3 0.04); run 2 0.97 / 1.35 (claude 0.69, zenserver 0.05, L-Connect 3 0.04); run 3 0.84 / 1.19 (claude 0.57, L-Connect 3 0.05, zenserver 0.04)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 17.4 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_native/walk 1 a run (at most 1), night_native/fly 0 a run (at most 1), night_plan_all/fly 0 a run (at most 1), dusk_plan/walk 0 a run (at most 1); VRAM over 10 GB: none
