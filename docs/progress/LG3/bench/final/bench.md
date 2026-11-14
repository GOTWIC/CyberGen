**Delta Megacity**, lg3_final: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1892 | 15.0 | 21.4 (21.4 to 21.4) | 30.6 | 476 | 20.5 | 14.4 | 14.9 | game | 1618 | 2 / 1 | 0.0% | 10242 | 12126 | 43008 |
| night_plan_all | drive | 3221 | 14.3 | 19.3 (19.3 to 19.3) | 27.0 | 398 | 15.3 | 14.7 | 14.1 | game | 860 | 5 / 3 | 0.0% | 10219 | 12264 | 43008 |
| night_plan_all | fly | 5523 | 12.1 | 18.5 (18.5 to 18.5) | 25.4 | 475 | 16.6 | 13.5 | 12.4 | game | 1315 | 7 / 1 | 0.0% | 10223 | 11962 | 43008 |
| night_plan_all | all | 10636 | 13.4 | 19.3 (19.3 to 19.3) | 27.2 | 476 | 16.9 | 14.0 | 14.2 | game | 1210 | 14 / 5 | 0.0% | 10242 | 12264 | 43008 |
| night_life | walk | 1896 | 15.0 | 21.6 (21.6 to 21.6) | 28.9 | 463 | 21.0 | 12.8 | 14.8 | game | 1700 | 2 / 1 | 0.0% | 10256 | 11576 | 43008 |
| night_life | drive | 3240 | 14.3 | 19.3 (19.3 to 19.3) | 26.9 | 402 | 14.7 | 14.5 | 14.1 | game | 796 | 6 / 1 | 0.0% | 10260 | 10769 | 43008 |
| night_life | fly | 5532 | 12.0 | 18.5 (18.5 to 18.5) | 25.0 | 457 | 15.7 | 13.6 | 12.4 | game | 1316 | 8 / 1 | 0.0% | 10198 | 10529 | 43008 |
| night_life | all | 10668 | 13.4 | 19.4 (19.4 to 19.4) | 26.8 | 463 | 16.4 | 13.8 | 14.2 | game | 1208 | 16 / 3 | 0.0% | 10260 | 11576 | 43008 |
| night_life_off | walk | 2082 | 13.9 | 17.5 (17.5 to 17.5) | 24.5 | 493 | 16.2 | 12.1 | 13.8 | game | 468 | 2 / 1 | 0.0% | 9779 | 10612 | 43008 |
| night_life_off | drive | 3303 | 14.1 | 18.6 (18.6 to 18.6) | 26.2 | 392 | 13.7 | 14.3 | 13.9 | render | 627 | 4 / 1 | 0.0% | 9716 | 10499 | 43008 |
| night_life_off | fly | 5573 | 12.0 | 17.9 (17.9 to 17.9) | 25.3 | 454 | 14.5 | 13.5 | 12.3 | game | 1269 | 7 / 2 | 0.0% | 9684 | 10316 | 43008 |
| night_life_off | all | 10958 | 13.2 | 18.1 (18.1 to 18.1) | 25.3 | 493 | 14.6 | 13.6 | 13.6 | game | 696 | 13 / 4 | 0.0% | 9779 | 10612 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 7.28; night_life 10.35; night_life_off 8.99

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.7 / 0.88 (claude 0.45, zenserver 0.05, NVIDIA Overlay 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 21.4 ms, night_plan_all/drive 19.3 ms, night_plan_all/fly 18.5 ms, night_life/walk 21.6 ms, night_life/drive 19.3 ms, night_life/fly 18.5 ms, night_life_off/walk 17.5 ms, night_life_off/drive 18.6 ms, night_life_off/fly 17.9 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 1 a run (at most 1), night_plan_all/drive 3 a run (at most 3), night_plan_all/fly 1 a run (at most 1), night_life/walk 1 a run (at most 1), night_life/drive 1 a run (at most 1), night_life/fly 1 a run (at most 1), night_life_off/walk 1 a run (at most 1), night_life_off/drive 1 a run (at most 1), night_life_off/fly 2 a run (at most 2); VRAM over 10 GB: night_plan_all/walk 10242 MB, night_life/walk 10256 MB, night_life/drive 10260 MB
