**Delta Megacity**, at2_after: 3 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_native | walk | 8615 | 9.8 | 11.4 (11.2 to 20.4) | 20.0 | 1610 | 10.3 | 10.6 | 9.3 | render | 858 | 10 / 5 | 0.0% | 7500 | 12166 | 43008 |
| night_native | drive | 5207 | 9.0 | 10.5 (10.0 to 13.7) | 17.1 | 64 | 9.2 | 9.7 | 8.3 | render | 946 | 2 / 0 | 0.0% | 6838 | 9737 | 43008 |
| night_native | fly | 6968 | 9.9 | 12.7 (12.3 to 16.2) | 19.1 | 68 | 11.1 | 11.1 | 9.8 | render | 1110 | 5 / 0 | 0.0% | 6726 | 9462 | 43008 |
| night_native | teleport | 851 | 10.2 | 23.0 (22.9 to 23.5) | 27.9 | 80 | 22.8 | 9.5 | 7.9 | game | 853 | 1 / 0 | 35.9% | 6727 | 9532 | 43008 |
| night_native | all | 20790 | 9.4 | 11.7 (11.2 to 16.5) | 19.0 | 1610 | 10.3 | 10.8 | 9.6 | render | 914 | 17 / 5 | 0.0% | 7500 | 12166 | 43008 |
| night_plan | walk | 6992 | 12.9 | 14.5 (14.4 to 22.8) | 15.3 | 94 | 6.6 | 14.4 | 13.6 | render | 1061 | 2 / 0 | 0.0% | 6760 | 9586 | 43008 |
| night_plan | drive | 4097 | 11.6 | 13.0 (12.8 to 22.6) | 18.2 | 68 | 10.3 | 12.6 | 11.6 | render | 1077 | 2 / 0 | 0.0% | 6764 | 9631 | 43008 |
| night_plan | fly | 6584 | 10.5 | 13.2 (12.9 to 14.6) | 19.5 | 72 | 11.8 | 11.6 | 10.2 | game | 1332 | 5 / 0 | 0.0% | 6729 | 8685 | 43008 |
| night_plan | teleport | 784 | 12.7 | 22.8 (22.1 to 23.2) | 27.3 | 79 | 22.7 | 12.4 | 11.3 | game | 1042 | 2 / 0 | 38.9% | 6729 | 8659 | 43008 |
| night_plan | all | 17673 | 11.7 | 14.3 (14.2 to 22.4) | 17.7 | 94 | 9.9 | 13.9 | 13.1 | render | 1105 | 9 / 0 | 0.0% | 6856 | 9631 | 43008 |
| night_plan_all | walk | 6011 | 15.0 | 16.7 (16.7 to 31.1) | 17.3 | 93 | 7.8 | 16.7 | 15.8 | render | 1066 | 2 / 0 | 0.0% | 6882 | 8802 | 43008 |
| night_plan_all | drive | 3366 | 14.2 | 15.4 (15.3 to 22.9) | 19.0 | 62 | 10.9 | 15.3 | 14.3 | render | 1081 | 2 / 0 | 0.0% | 6949 | 8804 | 43008 |
| night_plan_all | fly | 5926 | 11.8 | 14.1 (13.9 to 21.2) | 20.6 | 73 | 12.9 | 12.9 | 11.9 | render | 1342 | 5 / 0 | 0.0% | 6851 | 8677 | 43008 |
| night_plan_all | teleport | 739 | 14.3 | 23.8 (22.2 to 24.6) | 27.6 | 82 | 23.4 | 14.7 | 13.7 | game | 1047 | 1 / 0 | 39.9% | 6883 | 8210 | 43008 |
| night_plan_all | all | 15312 | 14.0 | 16.4 (16.4 to 30.2) | 18.8 | 93 | 10.8 | 16.1 | 15.3 | render | 1110 | 9 / 0 | 0.0% | 6949 | 8804 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_native 20.76; night_plan 13.99; night_plan_all 13.9

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.56 / 1.25 (claude 0.26, zenserver 0.04, NVIDIA Overlay 0.04); run 2 1.16 / 2.11 (claude 0.71, OneDrive.Sync.Service 0.15, zenserver 0.04); run 3 0.91 / 2.93 (claude 0.36, OneDrive.Sync.Service 0.28, zenserver 0.05)

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_native/walk 5 a run (at most 5), night_plan/walk 0 a run (at most 1), night_plan_all/walk 0 a run (at most 1); VRAM over 10 GB: none
