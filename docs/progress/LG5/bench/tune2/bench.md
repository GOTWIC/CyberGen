**Delta Megacity**, lg5_tune2: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1711 | 16.1 | 26.3 (26.3 to 26.3) | 35.0 | 483 | 25.0 | 15.2 | 15.7 | game | 1999 | 5 / 2 | 0.0% | 10343 | 14129 | 43008 |
| night_plan_all | drive | 3047 | 15.1 | 21.0 (21.0 to 21.0) | 28.6 | 395 | 17.5 | 15.3 | 15.0 | game | 1643 | 7 / 2 | 0.0% | 10323 | 12770 | 43008 |
| night_plan_all | fly | 5314 | 12.4 | 20.0 (20.0 to 20.0) | 26.2 | 447 | 18.6 | 13.9 | 12.8 | game | 1608 | 7 / 1 | 0.0% | 10167 | 12684 | 43008 |
| night_plan_all | all | 10072 | 14.0 | 21.4 (21.4 to 21.4) | 29.5 | 483 | 19.6 | 14.4 | 15.0 | game | 1697 | 19 / 5 | 0.0% | 10343 | 14129 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 7.87

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.76 / 1.11 (claude 0.33, nvcontainer 0.11, zenserver 0.08)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 26.3 ms, night_plan_all/drive 21.0 ms, night_plan_all/fly 20.0 ms; 40 fps (25 ms) missed by: night_plan_all/walk 26.3 ms; hitches over 100 ms: night_plan_all/walk 2 a run (at most 2), night_plan_all/drive 2 a run (at most 2), night_plan_all/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10343 MB, night_plan_all/drive 10323 MB
