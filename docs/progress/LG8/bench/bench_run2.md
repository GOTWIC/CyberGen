**Delta Megacity**, lg8b: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1822 | 14.3 | 24.3 (24.3 to 24.3) | 31.5 | 953 | 23.6 | 13.5 | 13.7 | game | 1846 | 7 / 5 | 0.0% | 10351 | 10771 | 43008 |
| night_plan_all | drive | 2931 | 15.5 | 21.9 (21.9 to 21.9) | 29.4 | 405 | 18.0 | 15.7 | 15.9 | game | 1660 | 10 / 2 | 0.0% | 10269 | 10761 | 43008 |
| night_plan_all | fly | 5039 | 12.7 | 22.1 (22.1 to 22.1) | 30.1 | 468 | 20.4 | 14.5 | 13.4 | game | 1678 | 11 / 1 | 0.0% | 10084 | 10592 | 43008 |
| night_plan_all | all | 9792 | 14.1 | 22.6 (22.6 to 22.6) | 30.4 | 953 | 20.5 | 14.7 | 15.2 | game | 1705 | 28 / 8 | 0.0% | 10351 | 10771 | 43008 |
| night_life_citybox | walk | 1914 | 14.1 | 24.7 (24.7 to 24.7) | 31.9 | 465 | 24.0 | 13.8 | 13.3 | game | 3330 | 5 / 2 | 0.0% | 10213 | 6772 | 43008 |
| night_life_citybox | drive | 2938 | 15.6 | 21.9 (21.9 to 21.9) | 30.0 | 401 | 17.1 | 15.8 | 15.7 | game | 3657 | 7 / 1 | 0.0% | 10312 | 7585 | 43008 |
| night_life_citybox | fly | 5072 | 12.9 | 20.6 (20.6 to 20.6) | 27.5 | 465 | 17.8 | 14.7 | 13.6 | game | 3651 | 7 / 1 | 0.0% | 10154 | 7251 | 43008 |
| night_life_citybox | all | 9924 | 14.2 | 21.8 (21.8 to 21.8) | 29.3 | 465 | 18.8 | 14.8 | 15.2 | game | 3588 | 19 / 4 | 0.0% | 10312 | 7585 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 8.69; night_life_citybox 13.01

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 1.65 / 3 (python 1.12, du 0.15, zenserver 0.05)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 24.3 ms, night_plan_all/drive 21.9 ms, night_plan_all/fly 22.1 ms, night_life_citybox/walk 24.7 ms, night_life_citybox/drive 21.9 ms, night_life_citybox/fly 20.6 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 5 a run (at most 5), night_plan_all/drive 2 a run (at most 2), night_plan_all/fly 1 a run (at most 1), night_life_citybox/walk 2 a run (at most 2), night_life_citybox/drive 1 a run (at most 1), night_life_citybox/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10351 MB, night_plan_all/drive 10269 MB, night_life_citybox/drive 10312 MB
