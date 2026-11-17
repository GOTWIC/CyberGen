**Delta Megacity**, stream: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all_stream2 | walk | 2024 | 13.7 | 20.1 (20.1 to 20.1) | 25.6 | 462 | 19.8 | 14.0 | 13.2 | game | 3260 | 3 / 1 | 0.0% | 10396 | 9096 | 43008 |
| night_plan_all_stream2 | drive | 2862 | 15.0 | 20.1 (20.1 to 20.1) | 88.4 | 409 | 14.5 | 14.1 | 15.4 | gpu | 3590 | 42 / 25 | 0.0% | 10387 | 8670 | 43008 |
| night_plan_all_stream2 | fly | 5399 | 12.6 | 16.4 (16.4 to 16.4) | 21.4 | 450 | 13.9 | 13.9 | 13.1 | game | 3600 | 5 / 2 | 0.0% | 10201 | 8623 | 43008 |
| night_plan_all_stream2 | all | 10285 | 13.6 | 18.4 (18.4 to 18.4) | 24.5 | 462 | 15.7 | 14.0 | 14.6 | game | 3534 | 50 / 28 | 0.0% | 10396 | 9096 | 43008 |
| night_plan_all_adaptive | walk | 2125 | 13.6 | 16.8 (16.8 to 16.8) | 19.7 | 455 | 16.5 | 13.8 | 12.9 | game | 3240 | 3 / 1 | 0.0% | 10268 | 8345 | 43008 |
| night_plan_all_adaptive | drive | 3124 | 14.9 | 18.3 (18.3 to 18.3) | 22.0 | 427 | 13.4 | 14.4 | 15.3 | gpu | 3554 | 5 / 2 | 0.0% | 10332 | 8384 | 43008 |
| night_plan_all_adaptive | fly | 5397 | 12.5 | 16.2 (16.2 to 16.2) | 20.2 | 455 | 13.1 | 13.9 | 13.1 | render | 3602 | 7 / 1 | 0.0% | 10207 | 8360 | 43008 |
| night_plan_all_adaptive | all | 10646 | 13.6 | 17.4 (17.4 to 17.4) | 20.8 | 455 | 14.5 | 14.0 | 14.7 | gpu | 3517 | 15 / 4 | 0.0% | 10332 | 8384 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all_stream2 15.05; night_plan_all_adaptive 22.06

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 1.37 / 3.19 (python 0.93, claude 0.09, zenserver 0.06)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all_stream2/walk 20.1 ms, night_plan_all_stream2/drive 20.1 ms, night_plan_all_adaptive/walk 16.8 ms, night_plan_all_adaptive/drive 18.3 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all_stream2/walk 1 a run (at most 1), night_plan_all_stream2/drive 25 a run (at most 25), night_plan_all_stream2/fly 2 a run (at most 2), night_plan_all_adaptive/walk 1 a run (at most 1), night_plan_all_adaptive/drive 2 a run (at most 2), night_plan_all_adaptive/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all_stream2/walk 10396 MB, night_plan_all_stream2/drive 10387 MB, night_plan_all_adaptive/walk 10268 MB, night_plan_all_adaptive/drive 10332 MB
