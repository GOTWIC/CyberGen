**Delta Megacity**, lg2_final: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1743 | 16.2 | 23.8 (23.8 to 23.8) | 34.0 | 476 | 23.2 | 13.2 | 16.0 | game | 2415 | 2 / 1 | 0.0% | 10294 | 10346 | 43008 |
| night_plan_all | drive | 3021 | 15.1 | 20.9 (20.9 to 20.9) | 29.5 | 408 | 16.4 | 15.2 | 15.1 | game | 1651 | 9 / 3 | 0.0% | 10309 | 10861 | 43008 |
| night_plan_all | fly | 5311 | 12.4 | 19.7 (19.7 to 19.7) | 26.3 | 455 | 17.7 | 13.9 | 12.9 | game | 1676 | 7 / 1 | 0.0% | 10186 | 10732 | 43008 |
| night_plan_all | all | 10075 | 14.1 | 20.8 (20.8 to 20.8) | 29.1 | 476 | 18.1 | 14.1 | 15.3 | game | 1734 | 18 / 5 | 0.0% | 10309 | 10861 | 43008 |
| night_life_noclothes | walk | 1554 | 17.3 | 29.2 (29.2 to 29.2) | 35.7 | 465 | 29.1 | 10.6 | 16.3 | game | 2071 | 3 / 1 | 0.0% | 10123 | 11000 | 43008 |
| night_life_noclothes | drive | 2998 | 15.5 | 20.9 (20.9 to 20.9) | 27.1 | 394 | 17.0 | 15.1 | 15.2 | game | 1646 | 4 / 2 | 0.0% | 10029 | 11028 | 43008 |
| night_life_noclothes | fly | 5322 | 12.4 | 19.6 (19.6 to 19.6) | 25.9 | 453 | 17.1 | 13.9 | 12.9 | game | 1676 | 8 / 2 | 0.0% | 9777 | 10176 | 43008 |
| night_life_noclothes | all | 9874 | 14.2 | 22.0 (22.0 to 22.0) | 30.5 | 465 | 20.3 | 14.0 | 15.6 | game | 1725 | 15 / 5 | 0.0% | 10123 | 11028 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 7.49; night_life_noclothes 14.56

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.66 / 1.08 (claude 0.4, zenserver 0.06, RSI Launcher 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 23.8 ms, night_plan_all/drive 20.9 ms, night_plan_all/fly 19.7 ms, night_life_noclothes/walk 29.2 ms, night_life_noclothes/drive 20.9 ms, night_life_noclothes/fly 19.6 ms; 40 fps (25 ms) missed by: night_life_noclothes/walk 29.2 ms; hitches over 100 ms: night_plan_all/walk 1 a run (at most 1), night_plan_all/drive 3 a run (at most 3), night_plan_all/fly 1 a run (at most 1), night_life_noclothes/walk 1 a run (at most 1), night_life_noclothes/drive 2 a run (at most 2), night_life_noclothes/fly 2 a run (at most 2); VRAM over 10 GB: night_plan_all/walk 10294 MB, night_plan_all/drive 10309 MB
