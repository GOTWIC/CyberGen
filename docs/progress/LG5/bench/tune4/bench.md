**Delta Megacity**, lg5_tune4: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1740 | 15.7 | 25.5 (25.5 to 25.5) | 34.4 | 486 | 24.7 | 13.0 | 15.1 | game | 2060 | 4 / 1 | 0.0% | 10311 | 13053 | 43008 |
| night_plan_all | drive | 3066 | 15.0 | 20.7 (20.7 to 20.7) | 28.2 | 385 | 16.8 | 15.5 | 15.2 | game | 1664 | 6 / 1 | 0.0% | 10352 | 13198 | 43008 |
| night_plan_all | fly | 5331 | 12.4 | 19.7 (19.7 to 19.7) | 26.9 | 463 | 18.1 | 13.9 | 12.8 | game | 1590 | 7 / 1 | 0.0% | 10225 | 12302 | 43008 |
| night_plan_all | all | 10137 | 14.0 | 21.2 (21.2 to 21.2) | 29.3 | 486 | 19.1 | 14.3 | 14.8 | game | 1705 | 17 / 3 | 0.0% | 10352 | 13198 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 8.18

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.53 / 0.92 (claude 0.25, zenserver 0.08, NVIDIA Overlay 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 25.5 ms, night_plan_all/drive 20.7 ms, night_plan_all/fly 19.7 ms; 40 fps (25 ms) missed by: night_plan_all/walk 25.5 ms; hitches over 100 ms: night_plan_all/walk 1 a run (at most 1), night_plan_all/drive 1 a run (at most 1), night_plan_all/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10311 MB, night_plan_all/drive 10352 MB
