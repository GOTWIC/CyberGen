**Delta Megacity**, lg5_tune1: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1738 | 15.9 | 25.2 (25.2 to 25.2) | 33.8 | 475 | 24.0 | 14.7 | 15.2 | game | 1994 | 6 / 2 | 0.0% | 10342 | 14179 | 43008 |
| night_plan_all | drive | 3043 | 15.0 | 20.9 (20.9 to 20.9) | 29.2 | 411 | 16.7 | 15.3 | 15.2 | game | 1618 | 7 / 3 | 0.0% | 10255 | 14043 | 43008 |
| night_plan_all | fly | 5322 | 12.4 | 19.5 (19.5 to 19.5) | 27.0 | 493 | 17.9 | 14.0 | 12.8 | game | 1602 | 7 / 1 | 0.0% | 10232 | 11874 | 43008 |
| night_plan_all | all | 10103 | 14.0 | 21.1 (21.1 to 21.1) | 29.2 | 493 | 19.0 | 14.4 | 14.9 | game | 1682 | 20 / 6 | 0.0% | 10342 | 14179 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 7.21

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.52 / 0.94 (claude 0.26, zenserver 0.08, NVIDIA Overlay 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 25.2 ms, night_plan_all/drive 20.9 ms, night_plan_all/fly 19.5 ms; 40 fps (25 ms) missed by: night_plan_all/walk 25.2 ms; hitches over 100 ms: night_plan_all/walk 2 a run (at most 2), night_plan_all/drive 3 a run (at most 3), night_plan_all/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10342 MB, night_plan_all/drive 10255 MB
