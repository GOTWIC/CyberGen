**Delta Megacity**, delta_main: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1749 | 14.6 | 25.9 (25.9 to 25.9) | 36.2 | 1237 | 25.1 | 14.1 | 13.6 | game | 2346 | 6 / 4 | 0.0% | 10343 | 12159 | 43008 |
| night_plan_all | drive | 3014 | 15.1 | 21.1 (21.1 to 21.1) | 28.0 | 392 | 16.8 | 15.5 | 15.4 | game | 1627 | 9 / 4 | 0.0% | 10265 | 13005 | 43008 |
| night_plan_all | fly | 5178 | 12.7 | 20.6 (20.6 to 20.6) | 27.1 | 454 | 18.5 | 14.2 | 13.2 | game | 1687 | 7 / 1 | 0.0% | 10083 | 12672 | 43008 |
| night_plan_all | all | 9941 | 14.0 | 21.5 (21.5 to 21.5) | 29.8 | 1237 | 19.2 | 14.5 | 14.7 | game | 1720 | 22 / 9 | 0.0% | 10343 | 13005 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 7.51

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 2 / 3.7 (python 1.57, zenserver 0.08, claude 0.07)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 25.9 ms, night_plan_all/drive 21.1 ms, night_plan_all/fly 20.6 ms; 40 fps (25 ms) missed by: night_plan_all/walk 25.9 ms; hitches over 100 ms: night_plan_all/walk 4 a run (at most 4), night_plan_all/drive 4 a run (at most 4), night_plan_all/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10343 MB, night_plan_all/drive 10265 MB
