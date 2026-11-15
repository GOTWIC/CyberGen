**Delta Megacity**, lg5_tune3: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_life | walk | 1766 | 15.7 | 23.6 (23.6 to 23.6) | 31.8 | 498 | 22.7 | 13.3 | 15.4 | game | 1937 | 4 / 2 | 0.0% | 10278 | 15114 | 43008 |
| night_life | drive | 3064 | 15.0 | 20.8 (20.8 to 20.8) | 27.4 | 405 | 16.5 | 15.3 | 15.1 | game | 1616 | 7 / 2 | 0.0% | 10347 | 15663 | 43008 |
| night_life | fly | 5326 | 12.4 | 19.9 (19.9 to 19.9) | 26.6 | 455 | 18.0 | 13.9 | 12.9 | game | 1618 | 7 / 1 | 0.0% | 10223 | 15544 | 43008 |
| night_life | all | 10156 | 14.0 | 20.8 (20.8 to 20.8) | 28.3 | 498 | 18.6 | 14.2 | 14.9 | game | 1664 | 18 / 5 | 0.0% | 10347 | 15663 | 43008 |
| night_life_noshadow | walk | 1833 | 15.2 | 23.7 (23.7 to 23.7) | 30.2 | 470 | 22.6 | 10.9 | 15.0 | game | 1412 | 2 / 1 | 0.0% | 10297 | 13002 | 43008 |
| night_life_noshadow | drive | 3140 | 14.7 | 20.4 (20.4 to 20.4) | 27.0 | 401 | 17.0 | 14.8 | 14.6 | game | 1119 | 5 / 1 | 0.0% | 10235 | 13302 | 43008 |
| night_life_noshadow | fly | 5379 | 12.3 | 19.3 (19.3 to 19.3) | 26.2 | 454 | 17.3 | 13.9 | 12.8 | game | 1532 | 7 / 1 | 0.0% | 10237 | 13257 | 43008 |
| night_life_noshadow | all | 10352 | 13.8 | 20.5 (20.5 to 20.5) | 28.0 | 470 | 18.4 | 14.0 | 14.5 | game | 1316 | 14 / 3 | 0.0% | 10297 | 13302 | 43008 |
| night_traffic_half | walk | 1818 | 15.6 | 23.4 (23.4 to 23.4) | 30.1 | 463 | 22.5 | 14.4 | 15.3 | game | 1973 | 2 / 1 | 0.0% | 10300 | 13449 | 43008 |
| night_traffic_half | drive | 3140 | 14.7 | 20.2 (20.2 to 20.2) | 27.0 | 401 | 16.2 | 15.3 | 14.8 | game | 1548 | 6 / 1 | 0.0% | 10301 | 13460 | 43008 |
| night_traffic_half | fly | 5410 | 12.2 | 19.1 (19.1 to 19.1) | 26.9 | 465 | 16.7 | 13.8 | 12.7 | game | 1587 | 8 / 1 | 0.0% | 10144 | 13020 | 43008 |
| night_traffic_half | all | 10368 | 13.8 | 20.1 (20.1 to 20.1) | 28.3 | 465 | 17.6 | 14.3 | 14.8 | game | 1631 | 16 / 3 | 0.0% | 10301 | 13460 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_life 7.45; night_life_noshadow 10.98; night_traffic_half 10.89

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.59 / 0.93 (claude 0.35, zenserver 0.06, NVIDIA Overlay 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: night_life/walk 23.6 ms, night_life/drive 20.8 ms, night_life/fly 19.9 ms, night_life_noshadow/walk 23.7 ms, night_life_noshadow/drive 20.4 ms, night_life_noshadow/fly 19.3 ms, night_traffic_half/walk 23.4 ms, night_traffic_half/drive 20.2 ms, night_traffic_half/fly 19.1 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_life/walk 2 a run (at most 2), night_life/drive 2 a run (at most 2), night_life/fly 1 a run (at most 1), night_life_noshadow/walk 1 a run (at most 1), night_life_noshadow/drive 1 a run (at most 1), night_life_noshadow/fly 1 a run (at most 1), night_traffic_half/walk 1 a run (at most 1), night_traffic_half/drive 1 a run (at most 1), night_traffic_half/fly 1 a run (at most 1); VRAM over 10 GB: night_life/walk 10278 MB, night_life/drive 10347 MB, night_life_noshadow/walk 10297 MB, night_traffic_half/walk 10300 MB, night_traffic_half/drive 10301 MB
