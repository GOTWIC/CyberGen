**Delta Megacity**, at0_rt: 2 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_native | walk | 4701 | 22.1 | 31.7 (15.3 to 48.1) | 40.1 | 347 | 20.5 | 31.6 | 14.0 | render | 916 | 54 / 1.5 | 0.0% | 9224.5 | 11828.5 | 43008.0 |
| night_native | drive | 2675 | 20.5 | 26.5 (14.2 to 38.8) | 34.5 | 1127 | 21.1 | 25.5 | 12.6 | render | 1024 | 6 / 0.5 | 0.0% | 8763.0 | 11844.5 | 43008.0 |
| night_native | fly | 4005 | 20.4 | 29.3 (15.7 to 42.9) | 40.2 | 126 | 24.3 | 27.0 | 11.8 | render | 1199 | 27.5 / 1 | 0.0% | 9260.5 | 11882.5 | 43008.0 |
| night_native | teleport | 992 | 23.3 | 35.6 (25.1 to 46.1) | 41.9 | 67 | 31.3 | 29.9 | 11.2 | render | 941 | 15 / 0.5 | 57.9% | 9213.0 | 11854.0 | 43008.0 |
| night_native | all | 11381 | 21.1 | 30.1 (15.3 to 44.9) | 39.2 | 1138 | 22.3 | 29.2 | 13.5 | render | 978 | 87.5 / 3 | 0.0% | 9274.5 | 11939.0 | 43008.0 |
| night_plan_all | walk | 4016 | 25.0 | 31.9 (18.9 to 45.0) | 36.8 | 143 | 20.5 | 31.6 | 17.9 | render | 1052 | 26.5 / 1.5 | 0.0% | 9318.5 | 11957.0 | 43008.0 |
| night_plan_all | drive | 2390 | 22.0 | 28.6 (16.1 to 41.1) | 35.6 | 92 | 23.2 | 27.3 | 15.2 | render | 1026 | 9 / 0.5 | 0.0% | 8967.0 | 11540.0 | 43008.0 |
| night_plan_all | fly | 3662 | 22.0 | 30.4 (16.3 to 44.6) | 40.6 | 115 | 25.0 | 28.1 | 13.4 | render | 1265 | 27 / 1 | 0.0% | 9383.5 | 11413.5 | 43008.0 |
| night_plan_all | teleport | 940 | 25.6 | 37.2 (25.5 to 48.9) | 44.9 | 2402 | 31.3 | 32.3 | 14.2 | render | 1054 | 23.5 / 1 | 59.1% | 9320.0 | 11430.5 | 43008.0 |
| night_plan_all | all | 10069 | 23.2 | 31.4 (18.6 to 44.2) | 37.8 | 143 | 23.3 | 30.4 | 17.0 | render | 1076 | 62.5 / 3 | 0.0% | 9383.5 | 11957.0 | 43008.0 |
| night_plan_mega | walk | 4023 | 23.7 | 30.3 (17.5 to 43.1) | 36.1 | 2670 | 20.6 | 29.8 | 16.5 | render | 844 | 23 / 2 | 0.0% | 9604.5 | 11575.5 | 43008.0 |
| night_plan_mega | drive | 2354 | 22.2 | 28.3 (16.1 to 40.5) | 36.5 | 95 | 23.0 | 27.5 | 15.0 | render | 966 | 10.5 / 0.5 | 0.0% | 9029.5 | 11580.5 | 43008.0 |
| night_plan_mega | fly | 3328 | 23.1 | 31.1 (16.8 to 45.4) | 41.6 | 3388 | 27.0 | 29.7 | 15.1 | render | 1228 | 28.5 / 1.5 | 0.0% | 9542.0 | 11303.0 | 43008.0 |
| night_plan_mega | teleport | 1004 | 24.1 | 37.3 (25.7 to 48.9) | 50.8 | 172 | 33.0 | 31.9 | 14.4 | render | 817 | 29 / 1 | 58.1% | 9574.5 | 11305.5 | 43008.0 |
| night_plan_mega | all | 9706 | 23.0 | 30.5 (17.4 to 43.7) | 38.2 | 3398 | 23.8 | 29.6 | 16.2 | render | 925 | 62 / 4 | 0.0% | 9604.5 | 11612.0 | 43008.0 |
| night_plan_mega_2048 | walk | 4050 | 24.4 | 30.9 (17.4 to 44.3) | 36.6 | 2621 | 20.9 | 30.6 | 16.4 | render | 860 | 27.5 / 1.5 | 0.0% | 9607.0 | 11405.0 | 43008.0 |
| night_plan_mega_2048 | drive | 2395 | 22.4 | 28.4 (15.4 to 41.4) | 35.3 | 74 | 22.1 | 27.6 | 14.6 | render | 1042 | 11 / 0 | 0.0% | 9015.0 | 11431.0 | 43008.0 |
| night_plan_mega_2048 | fly | 3376 | 23.4 | 31.6 (16.4 to 46.9) | 41.4 | 339 | 26.8 | 30.5 | 15.1 | render | 1201 | 35 / 1.5 | 0.0% | 9527.0 | 11318.5 | 43008.0 |
| night_plan_mega_2048 | teleport | 999 | 24.4 | 36.3 (24.8 to 47.8) | 43.9 | 70 | 31.6 | 30.9 | 14.4 | render | 805 | 24 / 0.5 | 57.1% | 9607.0 | 11220.5 | 43008.0 |
| night_plan_mega_2048 | all | 9821 | 23.5 | 31.1 (17.2 to 45.0) | 38.4 | 2621 | 23.7 | 30.3 | 16.1 | render | 971 | 73.5 / 3 | 0.0% | 9607.0 | 11436.5 | 43008.0 |

Loads (s, after each teleport onto a segment's start, all segments): night_native 94.69; night_plan_all 57.75; night_plan_mega 56.71; night_plan_mega_2048 59.52

CPU-starved runs (a thread's median at least 1.5 times the fastest run's at the same GPU time; a first run after an import builds the meshes' derived data, or other work on the PC; the median of the runs leaves one out): run 1 (night_native, night_plan_all, night_plan_mega, night_plan_mega_2048; up to 4.35x; other processes 0.65 cores on average)

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.65 / 2.39 (claude 0.23, backgroundTaskHost 0.09, prismlauncher 0.05); run 2 1.81 / 2.94 (Everything 0.59, claude 0.34, python 0.19)

Targets: 60 fps (p95 16.7 ms) missed by: night_native/walk 31.7 ms, night_native/drive 26.5 ms, night_native/fly 29.3 ms, night_plan_all/walk 31.9 ms, night_plan_all/drive 28.6 ms, night_plan_all/fly 30.4 ms, night_plan_mega/walk 30.3 ms, night_plan_mega/drive 28.3 ms, night_plan_mega/fly 31.1 ms, night_plan_mega_2048/walk 30.9 ms, night_plan_mega_2048/drive 28.4 ms, night_plan_mega_2048/fly 31.6 ms; 40 fps (25 ms) missed by: night_native/walk 31.7 ms, night_native/drive 26.5 ms, night_native/fly 29.3 ms, night_plan_all/walk 31.9 ms, night_plan_all/drive 28.6 ms, night_plan_all/fly 30.4 ms, night_plan_mega/walk 30.3 ms, night_plan_mega/drive 28.3 ms, night_plan_mega/fly 31.1 ms, night_plan_mega_2048/walk 30.9 ms, night_plan_mega_2048/drive 28.4 ms, night_plan_mega_2048/fly 31.6 ms; hitches over 100 ms: night_native/walk 1.5 a run (at most 3), night_native/drive 0.5 a run (at most 1), night_native/fly 1 a run (at most 2), night_plan_all/walk 1.5 a run (at most 2), night_plan_all/drive 0.5 a run (at most 1), night_plan_all/fly 1 a run (at most 2), night_plan_mega/walk 2 a run (at most 4), night_plan_mega/drive 0.5 a run (at most 1), night_plan_mega/fly 1.5 a run (at most 3), night_plan_mega_2048/walk 1.5 a run (at most 2), night_plan_mega_2048/fly 1.5 a run (at most 3); VRAM over 10 GB: none
