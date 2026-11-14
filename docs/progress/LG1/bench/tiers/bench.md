**Delta Megacity**, lg1_tiers: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_life_off | walk | 2072 | 13.9 | 17.3 (17.3 to 17.3) | 27.0 | 471 | 15.8 | 13.6 | 13.7 | game | 471 | 2 / 1 | 0.0% | 9724 | 12242 | 43008 |
| night_life_off | drive | 3324 | 14.1 | 18.6 (18.6 to 18.6) | 24.6 | 385 | 13.1 | 14.4 | 13.8 | render | 625 | 4 / 1 | 0.0% | 9823 | 10523 | 43008 |
| night_life_off | fly | 5577 | 12.1 | 17.8 (17.8 to 17.8) | 25.2 | 451 | 15.3 | 13.5 | 12.3 | game | 1268 | 7 / 1 | 0.0% | 9697 | 10359 | 43008 |
| night_life_off | all | 10973 | 13.2 | 18.1 (18.1 to 18.1) | 25.3 | 471 | 14.8 | 13.7 | 13.6 | game | 700 | 13 / 3 | 0.0% | 9823 | 12242 | 43008 |
| night_life | walk | 1796 | 15.7 | 23.7 (23.7 to 23.7) | 30.3 | 486 | 22.8 | 14.9 | 15.4 | game | 3057 | 2 / 1 | 0.0% | 10317 | 11100 | 43008 |
| night_life | drive | 3284 | 14.1 | 19.0 (19.0 to 19.0) | 26.0 | 393 | 15.3 | 14.6 | 13.9 | game | 680 | 5 / 1 | 0.0% | 10128 | 11165 | 43008 |
| night_life | fly | 5500 | 12.1 | 19.1 (19.1 to 19.1) | 25.7 | 453 | 16.9 | 13.5 | 12.4 | game | 1269 | 8 / 1 | 0.0% | 9807 | 11154 | 43008 |
| night_life | all | 10580 | 13.4 | 19.8 (19.8 to 19.8) | 27.4 | 486 | 17.6 | 13.9 | 14.7 | game | 1139 | 15 / 3 | 0.0% | 10317 | 11165 | 43008 |
| night_life_near80 | walk | 1778 | 15.7 | 23.9 (23.9 to 23.9) | 31.2 | 468 | 23.4 | 14.3 | 15.4 | game | 3006 | 3 / 2 | 0.0% | 10260 | 10607 | 43008 |
| night_life_near80 | drive | 3282 | 14.1 | 19.4 (19.4 to 19.4) | 26.2 | 394 | 15.6 | 14.5 | 13.9 | game | 676 | 4 / 2 | 0.0% | 10198 | 10670 | 43008 |
| night_life_near80 | fly | 5507 | 12.0 | 19.0 (19.0 to 19.0) | 26.1 | 457 | 16.9 | 13.5 | 12.4 | game | 1267 | 7 / 1 | 0.0% | 9844 | 10555 | 43008 |
| night_life_near80 | all | 10567 | 13.4 | 20.2 (20.2 to 20.2) | 27.4 | 468 | 17.8 | 13.8 | 14.6 | game | 1136 | 14 / 5 | 0.0% | 10260 | 10670 | 43008 |
| night_life_near0 | walk | 1926 | 15.1 | 20.0 (20.0 to 20.0) | 27.7 | 472 | 19.1 | 13.2 | 14.8 | game | 2414 | 2 / 1 | 0.0% | 10006 | 10415 | 43008 |
| night_life_near0 | drive | 3293 | 14.0 | 19.1 (19.1 to 19.1) | 26.1 | 391 | 15.3 | 14.3 | 13.9 | game | 679 | 4 / 1 | 0.0% | 9813 | 10499 | 43008 |
| night_life_near0 | fly | 5503 | 12.1 | 18.9 (18.9 to 18.9) | 24.9 | 451 | 16.8 | 13.6 | 12.5 | game | 1265 | 7 / 1 | 0.0% | 9814 | 10411 | 43008 |
| night_life_near0 | all | 10722 | 13.4 | 19.1 (19.1 to 19.1) | 26.0 | 472 | 16.8 | 13.7 | 14.2 | game | 1153 | 13 / 3 | 0.0% | 10006 | 10499 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_life_off 7; night_life 11.63; night_life_near80 10.59; night_life_near0 10.16

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.64 / 0.86 (claude 0.41, zenserver 0.05, NVIDIA Overlay 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: night_life_off/walk 17.3 ms, night_life_off/drive 18.6 ms, night_life_off/fly 17.8 ms, night_life/walk 23.7 ms, night_life/drive 19.0 ms, night_life/fly 19.1 ms, night_life_near80/walk 23.9 ms, night_life_near80/drive 19.4 ms, night_life_near80/fly 19.0 ms, night_life_near0/walk 20.0 ms, night_life_near0/drive 19.1 ms, night_life_near0/fly 18.9 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_life_off/walk 1 a run (at most 1), night_life_off/drive 1 a run (at most 1), night_life_off/fly 1 a run (at most 1), night_life/walk 1 a run (at most 1), night_life/drive 1 a run (at most 1), night_life/fly 1 a run (at most 1), night_life_near80/walk 2 a run (at most 2), night_life_near80/drive 2 a run (at most 2), night_life_near80/fly 1 a run (at most 1), night_life_near0/walk 1 a run (at most 1), night_life_near0/drive 1 a run (at most 1), night_life_near0/fly 1 a run (at most 1); VRAM over 10 GB: night_life/walk 10317 MB, night_life_near80/walk 10260 MB
