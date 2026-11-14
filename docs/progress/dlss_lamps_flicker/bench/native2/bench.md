**Delta Megacity**, dlss_native2: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1982 | 14.6 | 18.1 (18.1 to 18.1) | 27.1 | 463 | 17.1 | 13.7 | 14.4 | game | 934 | 2 / 1 | 0.0% | 8731 | 8988 | 43008 |
| night_plan_all | drive | 3307 | 14.1 | 19.0 (19.0 to 19.0) | 25.5 | 398 | 14.8 | 14.3 | 13.9 | game | 725 | 3 / 1 | 0.0% | 8703 | 8937 | 43008 |
| night_plan_all | fly | 5505 | 12.1 | 18.9 (18.9 to 18.9) | 25.6 | 461 | 16.9 | 13.7 | 12.6 | game | 1311 | 7 / 1 | 0.0% | 8704 | 8852 | 43008 |
| night_plan_all | all | 10794 | 13.3 | 18.8 (18.8 to 18.8) | 25.8 | 463 | 16.4 | 13.8 | 13.9 | game | 868 | 12 / 3 | 0.0% | 8731 | 8988 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 6.81

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.64 / 0.9 (claude 0.36, zenserver 0.08, NVIDIA Overlay 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 18.1 ms, night_plan_all/drive 19.0 ms, night_plan_all/fly 18.9 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 1 a run (at most 1), night_plan_all/drive 1 a run (at most 1), night_plan_all/fly 1 a run (at most 1); VRAM over 10 GB: none
