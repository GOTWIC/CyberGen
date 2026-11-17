**Delta Megacity**, after: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1920 | 13.8 | 24.8 (24.8 to 24.8) | 34.1 | 497 | 23.9 | 13.6 | 13.3 | game | 3258 | 5 / 3 | 0.0% | 10371 | 9212 | 43008 |
| night_plan_all | drive | 3102 | 14.9 | 20.2 (20.2 to 20.2) | 26.4 | 406 | 16.3 | 14.9 | 15.2 | game | 3577 | 5 / 1 | 0.0% | 10416 | 9198 | 43008 |
| night_plan_all | fly | 5308 | 12.6 | 18.7 (18.7 to 18.7) | 24.1 | 469 | 16.9 | 14.1 | 13.1 | game | 3620 | 7 / 1 | 0.0% | 10229 | 8452 | 43008 |
| night_plan_all | all | 10330 | 13.7 | 20.2 (20.2 to 20.2) | 27.6 | 497 | 18.2 | 14.2 | 14.6 | game | 3495 | 17 / 5 | 0.0% | 10416 | 9212 | 43008 |
| night_plan_all_hlodslow | walk | 2032 | 13.6 | 22.4 (22.4 to 22.4) | 29.1 | 489 | 21.5 | 13.3 | 12.8 | game | 3239 | 2 / 1 | 0.0% | 10328 | 8354 | 43008 |
| night_plan_all_hlodslow | drive | 3099 | 15.0 | 20.0 (20.0 to 20.0) | 26.5 | 378 | 15.8 | 15.2 | 15.2 | game | 3586 | 4 / 1 | 0.0% | 10392 | 8336 | 43008 |
| night_plan_all_hlodslow | fly | 5311 | 12.4 | 19.4 (19.4 to 19.4) | 26.3 | 453 | 16.6 | 14.0 | 13.0 | game | 3522 | 7 / 1 | 0.0% | 10175 | 8139 | 43008 |
| night_plan_all_hlodslow | all | 10442 | 13.6 | 20.1 (20.1 to 20.1) | 27.4 | 489 | 17.6 | 14.2 | 14.6 | game | 3471 | 13 / 3 | 0.0% | 10392 | 8354 | 43008 |
| night_plan_all_stream2 | walk | 2102 | 13.4 | 18.6 (18.6 to 18.6) | 22.9 | 473 | 18.4 | 13.8 | 13.1 | game | 3188 | 2 / 1 | 0.0% | 10244 | 8103 | 43008 |
| night_plan_all_stream2 | drive | 3137 | 14.9 | 18.3 (18.3 to 18.3) | 23.5 | 387 | 13.5 | 14.1 | 15.4 | gpu | 3594 | 3 / 1 | 0.0% | 10367 | 8130 | 43008 |
| night_plan_all_stream2 | fly | 5387 | 12.5 | 16.6 (16.6 to 16.6) | 22.3 | 487 | 13.9 | 14.0 | 13.1 | render | 3614 | 8 / 1 | 0.0% | 10274 | 8030 | 43008 |
| night_plan_all_stream2 | all | 10626 | 13.6 | 17.9 (17.9 to 17.9) | 22.8 | 487 | 15.1 | 14.0 | 14.7 | game | 3532 | 13 / 3 | 0.0% | 10367 | 8130 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 6.68; night_plan_all_hlodslow 11.07; night_plan_all_stream2 21.03

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 1.29 / 1.9 (python 0.94, zenserver 0.05, claude 0.04)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 24.8 ms, night_plan_all/drive 20.2 ms, night_plan_all/fly 18.7 ms, night_plan_all_hlodslow/walk 22.4 ms, night_plan_all_hlodslow/drive 20.0 ms, night_plan_all_hlodslow/fly 19.4 ms, night_plan_all_stream2/walk 18.6 ms, night_plan_all_stream2/drive 18.3 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 3 a run (at most 3), night_plan_all/drive 1 a run (at most 1), night_plan_all/fly 1 a run (at most 1), night_plan_all_hlodslow/walk 1 a run (at most 1), night_plan_all_hlodslow/drive 1 a run (at most 1), night_plan_all_hlodslow/fly 1 a run (at most 1), night_plan_all_stream2/walk 1 a run (at most 1), night_plan_all_stream2/drive 1 a run (at most 1), night_plan_all_stream2/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10371 MB, night_plan_all/drive 10416 MB, night_plan_all_hlodslow/walk 10328 MB, night_plan_all_hlodslow/drive 10392 MB, night_plan_all_stream2/walk 10244 MB, night_plan_all_stream2/drive 10367 MB, night_plan_all_stream2/fly 10274 MB
