**Delta Megacity**, people_surfaces: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1623 | 16.9 | 20.1 (20.1 to 20.1) | 24.9 | 466 | 18.9 | 15.7 | 16.8 | game | 3597 | 6 / 2 | 0.0% | 10552 | 9849 | 43520 |
| night_plan_all | drive | 3066 | 15.1 | 19.5 (19.5 to 19.5) | 25.5 | 445 | 15.4 | 15.2 | 15.2 | game | 3598 | 10 / 2 | 0.0% | 10438 | 10437 | 43520 |
| night_plan_all | fly | 5327 | 12.9 | 17.0 (17.0 to 17.0) | 20.4 | 465 | 15.3 | 14.3 | 13.4 | game | 3686 | 6 / 1 | 0.0% | 10409 | 10023 | 43520 |
| night_plan_all | all | 10016 | 14.3 | 18.8 (18.8 to 18.8) | 23.0 | 466 | 16.1 | 14.6 | 16.0 | game | 3632 | 22 / 5 | 0.0% | 10552 | 10437 | 43520 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 13.44

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 1.55 / 2.38 (python 1.11, zenserver 0.08, claude 0.07)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 20.1 ms, night_plan_all/drive 19.5 ms, night_plan_all/fly 17.0 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 2 a run (at most 2), night_plan_all/drive 2 a run (at most 2), night_plan_all/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10552 MB, night_plan_all/drive 10438 MB, night_plan_all/fly 10409 MB
