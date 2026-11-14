**Delta Megacity**, lg1_people: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1730 | 15.8 | 25.6 (25.6 to 25.6) | 34.2 | 504 | 24.5 | 15.1 | 15.3 | game | 3044 | 8 / 2 | 0.0% | 10309 | 12978 | 43008 |
| night_plan_all | drive | 3298 | 14.0 | 19.2 (19.2 to 19.2) | 25.4 | 389 | 15.6 | 14.5 | 13.9 | game | 675 | 3 / 1 | 0.0% | 10089 | 13012 | 43008 |
| night_plan_all | fly | 5481 | 12.1 | 19.3 (19.3 to 19.3) | 25.1 | 445 | 17.5 | 13.5 | 12.4 | game | 1266 | 7 / 1 | 0.0% | 9738 | 10222 | 43008 |
| night_plan_all | all | 10509 | 13.4 | 20.5 (20.5 to 20.5) | 28.3 | 504 | 18.5 | 14.0 | 14.5 | game | 1120 | 18 / 4 | 0.0% | 10309 | 13012 | 43008 |
| night_plan_all_dlss_q | walk | 2491 | 10.7 | 20.8 (20.8 to 20.8) | 28.6 | 461 | 20.5 | 11.7 | 10.3 | game | 2986 | 2 / 1 | 0.0% | 9766 | 10428 | 43008 |
| night_plan_all_dlss_q | drive | 4705 | 9.5 | 14.4 (14.4 to 14.4) | 21.4 | 371 | 14.0 | 10.7 | 8.4 | game | 677 | 4 / 1 | 0.0% | 9562 | 10325 | 43008 |
| night_plan_all_dlss_q | fly | 6695 | 9.6 | 17.1 (17.1 to 17.1) | 23.7 | 475 | 15.9 | 10.8 | 8.0 | game | 1270 | 7 / 1 | 0.0% | 9131 | 10185 | 43008 |
| night_plan_all_dlss_q | all | 13891 | 9.8 | 17.1 (17.1 to 17.1) | 24.8 | 475 | 16.0 | 11.0 | 9.5 | game | 956 | 13 / 3 | 0.0% | 9766 | 10428 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 8.11; night_plan_all_dlss_q 10.94

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.56 / 0.84 (claude 0.34, zenserver 0.07, NVIDIA Overlay 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 25.6 ms, night_plan_all/drive 19.2 ms, night_plan_all/fly 19.3 ms, night_plan_all_dlss_q/walk 20.8 ms, night_plan_all_dlss_q/fly 17.1 ms; 40 fps (25 ms) missed by: night_plan_all/walk 25.6 ms; hitches over 100 ms: night_plan_all/walk 2 a run (at most 2), night_plan_all/drive 1 a run (at most 1), night_plan_all/fly 1 a run (at most 1), night_plan_all_dlss_q/walk 1 a run (at most 1), night_plan_all_dlss_q/drive 1 a run (at most 1), night_plan_all_dlss_q/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10309 MB
