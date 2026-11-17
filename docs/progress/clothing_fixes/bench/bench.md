**Delta Megacity**, clothing: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1919 | 14.0 | 22.9 (22.9 to 22.9) | 32.2 | 809 | 22.3 | 13.9 | 13.3 | game | 3227 | 3 / 2 | 0.0% | 10348 | 12127 | 43008 |
| night_plan_all | drive | 3061 | 15.1 | 20.7 (20.7 to 20.7) | 27.9 | 386 | 16.4 | 15.0 | 15.2 | game | 3598 | 4 / 1 | 0.0% | 10262 | 12226 | 43008 |
| night_plan_all | fly | 5241 | 12.4 | 19.9 (19.9 to 19.9) | 26.6 | 447 | 17.8 | 14.0 | 13.0 | game | 3547 | 13 / 3 | 0.0% | 10177 | 11964 | 43008 |
| night_plan_all | all | 10221 | 13.8 | 20.6 (20.6 to 20.6) | 28.1 | 809 | 18.2 | 14.2 | 14.7 | game | 3505 | 20 / 6 | 0.0% | 10348 | 12226 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 7.93

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 1.37 / 2.05 (python 0.97, zenserver 0.08, claude 0.04)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 22.9 ms, night_plan_all/drive 20.7 ms, night_plan_all/fly 19.9 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 2 a run (at most 2), night_plan_all/drive 1 a run (at most 1), night_plan_all/fly 3 a run (at most 3); VRAM over 10 GB: night_plan_all/walk 10348 MB, night_plan_all/drive 10262 MB
