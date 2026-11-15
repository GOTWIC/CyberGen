**Delta Megacity**, lg5_final: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1705 | 16.1 | 26.0 (26.0 to 26.0) | 34.7 | 486 | 25.3 | 11.9 | 15.5 | game | 2055 | 4 / 1 | 0.0% | 10341 | 12422 | 43008 |
| night_plan_all | drive | 3073 | 15.0 | 20.7 (20.7 to 20.7) | 26.5 | 393 | 17.8 | 14.9 | 15.2 | game | 1914 | 3 / 1 | 0.0% | 10286 | 12531 | 43008 |
| night_plan_all | fly | 5176 | 12.8 | 20.8 (20.8 to 20.8) | 26.9 | 457 | 19.2 | 14.0 | 13.0 | game | 2182 | 7 / 1 | 0.0% | 10163 | 12396 | 43008 |
| night_plan_all | all | 9954 | 14.2 | 21.6 (21.6 to 21.6) | 29.5 | 486 | 20.1 | 14.1 | 15.0 | game | 2020 | 14 / 3 | 0.0% | 10341 | 12531 | 43008 |
| night_traffic_off | walk | 1923 | 14.8 | 20.8 (20.8 to 20.8) | 28.3 | 494 | 20.1 | 12.6 | 14.4 | game | 1178 | 2 / 2 | 0.0% | 10322 | 12374 | 43008 |
| night_traffic_off | drive | 3272 | 14.2 | 19.0 (19.0 to 19.0) | 26.0 | 388 | 14.7 | 14.6 | 14.0 | game | 777 | 5 / 1 | 0.0% | 10228 | 12323 | 43008 |
| night_traffic_off | fly | 5588 | 11.9 | 18.0 (18.0 to 18.0) | 25.1 | 453 | 15.0 | 13.4 | 12.3 | game | 1312 | 7 / 1 | 0.0% | 10136 | 11815 | 43008 |
| night_traffic_off | all | 10783 | 13.3 | 18.9 (18.9 to 18.9) | 26.2 | 494 | 16.2 | 13.7 | 14.1 | game | 1023 | 14 / 4 | 0.0% | 10322 | 12374 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 8.53; night_traffic_off 10.31

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.63 / 1.14 (claude 0.32, zenserver 0.06, audiodg 0.04)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 26.0 ms, night_plan_all/drive 20.7 ms, night_plan_all/fly 20.8 ms, night_traffic_off/walk 20.8 ms, night_traffic_off/drive 19.0 ms, night_traffic_off/fly 18.0 ms; 40 fps (25 ms) missed by: night_plan_all/walk 26.0 ms; hitches over 100 ms: night_plan_all/walk 1 a run (at most 1), night_plan_all/drive 1 a run (at most 1), night_plan_all/fly 1 a run (at most 1), night_traffic_off/walk 2 a run (at most 2), night_traffic_off/drive 1 a run (at most 1), night_traffic_off/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10341 MB, night_plan_all/drive 10286 MB, night_traffic_off/walk 10322 MB
