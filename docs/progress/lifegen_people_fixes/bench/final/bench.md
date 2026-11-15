**Delta Megacity**, people_fixes_final: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1834 | 15.3 | 23.1 (23.1 to 23.1) | 31.4 | 472 | 22.7 | 15.1 | 14.7 | game | 1617 | 3 / 1 | 0.0% | 10181 | 14246 | 43008 |
| night_plan_all | drive | 3237 | 14.3 | 19.4 (19.4 to 19.4) | 26.2 | 405 | 15.4 | 14.8 | 14.1 | game | 851 | 6 / 1 | 0.0% | 10254 | 13990 | 43008 |
| night_plan_all | fly | 5536 | 12.0 | 18.3 (18.3 to 18.3) | 25.2 | 461 | 16.6 | 13.5 | 12.4 | game | 1312 | 7 / 1 | 0.0% | 10193 | 13651 | 43008 |
| night_plan_all | all | 10607 | 13.4 | 19.5 (19.5 to 19.5) | 27.2 | 472 | 17.4 | 14.3 | 14.2 | game | 1204 | 16 / 3 | 0.0% | 10254 | 14246 | 43008 |
| night_life | walk | 1888 | 15.1 | 21.2 (21.2 to 21.2) | 27.8 | 472 | 20.5 | 12.9 | 14.7 | game | 1605 | 2 / 1 | 0.0% | 10193 | 12390 | 43008 |
| night_life | drive | 3254 | 14.2 | 19.1 (19.1 to 19.1) | 26.7 | 394 | 15.2 | 14.7 | 14.1 | game | 830 | 6 / 1 | 0.0% | 10259 | 12223 | 43008 |
| night_life | fly | 5554 | 12.1 | 18.3 (18.3 to 18.3) | 24.9 | 458 | 15.8 | 13.6 | 12.4 | game | 1317 | 7 / 1 | 0.0% | 10168 | 12190 | 43008 |
| night_life | all | 10696 | 13.4 | 19.1 (19.1 to 19.1) | 26.5 | 472 | 16.8 | 13.9 | 14.2 | game | 1205 | 15 / 3 | 0.0% | 10259 | 12390 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 7.33; night_life 10.61

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.74 / 1 (claude 0.44, zenserver 0.06, audiodg 0.04)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 23.1 ms, night_plan_all/drive 19.4 ms, night_plan_all/fly 18.3 ms, night_life/walk 21.2 ms, night_life/drive 19.1 ms, night_life/fly 18.3 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 1 a run (at most 1), night_plan_all/drive 1 a run (at most 1), night_plan_all/fly 1 a run (at most 1), night_life/walk 1 a run (at most 1), night_life/drive 1 a run (at most 1), night_life/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/drive 10254 MB, night_life/drive 10259 MB
