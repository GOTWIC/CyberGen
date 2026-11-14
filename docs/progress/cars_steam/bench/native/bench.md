**Delta Megacity**, cars_native: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1984 | 14.5 | 19.0 (19.0 to 19.0) | 28.9 | 480 | 18.4 | 14.0 | 14.1 | game | 990 | 2 / 1 | 0.0% | 8820 | 11117 | 43008 |
| night_plan_all | drive | 3338 | 13.9 | 18.9 (18.9 to 18.9) | 25.9 | 381 | 15.3 | 14.3 | 13.8 | game | 678 | 2 / 1 | 0.0% | 8697 | 11058 | 43008 |
| night_plan_all | fly | 5555 | 12.0 | 18.6 (18.6 to 18.6) | 24.8 | 466 | 16.8 | 13.5 | 12.6 | game | 1265 | 7 / 1 | 0.0% | 8698 | 10809 | 43008 |
| night_plan_all | all | 10877 | 13.3 | 18.7 (18.7 to 18.7) | 25.9 | 480 | 16.6 | 13.8 | 13.8 | game | 840 | 11 / 3 | 0.0% | 8820 | 11117 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 6.61

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.55 / 0.98 (claude 0.28, zenserver 0.08, NVIDIA Overlay 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 19.0 ms, night_plan_all/drive 18.9 ms, night_plan_all/fly 18.6 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 1 a run (at most 1), night_plan_all/drive 1 a run (at most 1), night_plan_all/fly 1 a run (at most 1); VRAM over 10 GB: none
