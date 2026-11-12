**Delta Megacity**, at3_after: 3 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_native | walk | 9086 | 9.8 | 10.8 (10.8 to 10.9) | 17.6 | 92 | 8.1 | 10.4 | 9.3 | render | 860 | 3 / 0 | 0.0% | 6791 | 8593 | 43008 |
| night_native | drive | 5219 | 9.0 | 10.2 (10.2 to 10.3) | 17.1 | 58 | 9.0 | 9.7 | 8.4 | render | 951 | 2 / 0 | 0.0% | 6796 | 8621 | 43008 |
| night_native | fly | 7076 | 9.8 | 12.5 (12.1 to 12.7) | 19.0 | 70 | 11.0 | 10.9 | 9.9 | render | 1112 | 5 / 0 | 0.0% | 6669 | 8542 | 43008 |
| night_native | teleport | 842 | 10.5 | 22.5 (22.2 to 22.9) | 27.6 | 74 | 22.6 | 9.1 | 8.1 | game | 855 | 1 / 0 | 35.2% | 6701 | 8575 | 43008 |
| night_native | all | 21378 | 9.5 | 11.2 (11.2 to 11.4) | 18.0 | 92 | 9.7 | 10.7 | 9.7 | render | 913 | 10 / 0 | 0.0% | 6796 | 8621 | 43008 |
| night_plan | walk | 6954 | 12.9 | 14.6 (14.6 to 14.6) | 15.3 | 85 | 6.9 | 14.5 | 13.7 | render | 1063 | 2 / 0 | 0.0% | 6705 | 8673 | 43008 |
| night_plan | drive | 4080 | 11.7 | 13.0 (12.9 to 13.0) | 17.8 | 58 | 9.9 | 12.7 | 11.7 | render | 1078 | 2 / 0 | 0.0% | 6834 | 8636 | 43008 |
| night_plan | fly | 6626 | 10.5 | 13.2 (13.0 to 13.2) | 19.6 | 70 | 11.8 | 11.5 | 10.4 | game | 1332 | 5 / 0 | 0.0% | 6675 | 8541 | 43008 |
| night_plan | teleport | 773 | 12.6 | 23.1 (22.9 to 24.0) | 27.5 | 70 | 22.9 | 12.3 | 11.4 | game | 1044 | 2 / 0 | 38.7% | 6708 | 8507 | 43008 |
| night_plan | all | 17666 | 11.7 | 14.4 (14.4 to 14.4) | 17.6 | 85 | 9.8 | 14.0 | 13.2 | render | 1106 | 9 / 0 | 0.0% | 6834 | 8673 | 43008 |
| night_plan_all | walk | 5998 | 14.9 | 16.8 (16.8 to 16.8) | 17.4 | 97 | 7.7 | 16.7 | 15.9 | render | 1067 | 2 / 0 | 0.0% | 6924 | 8703 | 43008 |
| night_plan_all | drive | 3347 | 14.3 | 15.4 (15.4 to 15.5) | 18.9 | 66 | 11.0 | 15.3 | 14.3 | render | 1083 | 2 / 0 | 0.0% | 6831 | 8691 | 43008 |
| night_plan_all | fly | 5948 | 11.7 | 13.9 (13.8 to 14.2) | 20.7 | 71 | 12.7 | 12.9 | 11.9 | render | 1340 | 5 / 0 | 0.0% | 6797 | 8559 | 43008 |
| night_plan_all | teleport | 735 | 14.2 | 22.3 (22.1 to 23.8) | 28.2 | 73 | 22.3 | 14.7 | 13.8 | game | 1049 | 2 / 0 | 39.5% | 6829 | 8585 | 43008 |
| night_plan_all | all | 15287 | 14.0 | 16.4 (16.4 to 16.4) | 18.7 | 97 | 10.8 | 16.1 | 15.3 | render | 1112 | 9 / 0 | 0.0% | 6925 | 8703 | 43008 |
| dusk_plan | walk | 6956 | 12.9 | 14.5 (14.5 to 14.5) | 15.6 | 90 | 6.9 | 14.4 | 13.6 | render | 1063 | 2 / 0 | 0.0% | 6736 | 8698 | 43008 |
| dusk_plan | drive | 4132 | 11.5 | 12.8 (12.8 to 12.9) | 17.9 | 63 | 9.9 | 12.5 | 11.6 | render | 1079 | 2 / 0 | 0.0% | 6710 | 8694 | 43008 |
| dusk_plan | fly | 6677 | 10.4 | 13.1 (13.1 to 13.3) | 19.5 | 70 | 11.5 | 11.5 | 10.4 | game | 1338 | 5 / 0 | 0.0% | 6712 | 7719 | 43008 |
| dusk_plan | teleport | 780 | 12.6 | 23.4 (22.8 to 23.6) | 27.6 | 73 | 23.2 | 12.3 | 11.5 | game | 1044 | 2 / 0 | 38.5% | 6710 | 7536 | 43008 |
| dusk_plan | all | 17770 | 11.6 | 14.3 (14.3 to 14.3) | 17.7 | 90 | 9.8 | 14.0 | 13.2 | render | 1106 | 9 / 0 | 0.0% | 6743 | 8698 | 43008 |
| day_plan | walk | 9203 | 9.9 | 10.7 (10.6 to 10.7) | 13.2 | 83 | 4.6 | 10.6 | 9.5 | render | 726 | 2 / 0 | 0.0% | 6710 | 7598 | 43008 |
| day_plan | drive | 5154 | 9.1 | 10.4 (10.3 to 10.5) | 17.0 | 63 | 9.0 | 9.8 | 8.5 | render | 1571 | 2 / 0 | 0.0% | 6806 | 7640 | 43008 |
| day_plan | fly | 7001 | 9.9 | 12.5 (12.3 to 12.6) | 19.1 | 74 | 10.8 | 11.1 | 10.0 | render | 681 | 5 / 0 | 0.0% | 6678 | 7543 | 43008 |
| day_plan | teleport | 840 | 11.5 | 22.5 (22.0 to 23.1) | 26.3 | 65 | 22.0 | 9.4 | 8.2 | game | 815 | 2 / 0 | 35.5% | 6680 | 7439 | 43008 |
| day_plan | all | 21357 | 9.6 | 11.1 (11.1 to 11.1) | 16.6 | 90 | 8.9 | 10.8 | 9.8 | render | 828 | 9 / 0 | 0.0% | 6806 | 7640 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_native 19.63; night_plan 13.54; night_plan_all 13.8; dusk_plan 13.62; day_plan 13.17

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.41 / 1.05 (claude 0.09, L-Connect 3 0.04, NVIDIA Overlay 0.04); run 2 0.41 / 0.93 (claude 0.08, NVIDIA Overlay 0.04, L-Connect 3 0.04); run 3 0.39 / 1.06 (claude 0.08, NVIDIA Overlay 0.04, L-Connect 3 0.04)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 16.8 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 0 a run (at most 1); VRAM over 10 GB: none
