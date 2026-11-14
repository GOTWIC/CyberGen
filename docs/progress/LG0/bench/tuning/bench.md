**Delta Megacity**, lg0_tuning: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_life_off | walk | 2204 | 13.4 | 15.2 (15.2 to 15.2) | 23.8 | 59 | 13.9 | 14.4 | 13.6 | render | 1112 | 1 / 0 | 0.0% | 8622 | 9375 | 43008 |
| night_life_off | drive | 3531 | 13.5 | 15.2 (15.2 to 15.2) | 19.6 | 62 | 12.4 | 14.7 | 13.6 | render | 1095 | 2 / 0 | 0.0% | 8628 | 9226 | 43008 |
| night_life_off | fly | 5836 | 11.8 | 16.5 (16.5 to 16.5) | 23.2 | 71 | 15.5 | 13.1 | 12.0 | game | 1697 | 6 / 0 | 0.0% | 8628 | 9095 | 43008 |
| night_life_off | all | 11571 | 12.8 | 15.5 (15.5 to 15.5) | 22.7 | 71 | 14.4 | 14.3 | 13.4 | game | 1302 | 9 / 0 | 0.0% | 8628 | 9375 | 43008 |
| night_life_rebuild | walk | 1252 | 23.9 | 26.4 (26.4 to 26.4) | 29.7 | 80 | 21.2 | 26.2 | 25.1 | render | 1784 | 1 / 0 | 0.0% | 8779 | 8979 | 43008 |
| night_life_rebuild | drive | 3446 | 13.6 | 16.6 (16.6 to 16.6) | 22.8 | 78 | 15.3 | 14.8 | 13.8 | game | 1153 | 3 / 0 | 0.0% | 8654 | 8974 | 43008 |
| night_life_rebuild | fly | 5609 | 11.9 | 18.1 (18.1 to 18.1) | 25.0 | 85 | 17.1 | 13.7 | 12.8 | game | 1701 | 6 / 0 | 0.0% | 8624 | 8974 | 43008 |
| night_life_rebuild | all | 10307 | 13.1 | 24.5 (24.5 to 24.5) | 26.7 | 85 | 17.5 | 24.1 | 23.2 | render | 1421 | 10 / 0 | 0.0% | 8779 | 8979 | 43008 |
| night_life | walk | 1856 | 15.9 | 19.1 (19.1 to 19.1) | 25.1 | 84 | 18.6 | 17.4 | 16.5 | game | 1507 | 1 / 0 | 0.0% | 8688 | 8988 | 43008 |
| night_life | drive | 3464 | 13.6 | 16.2 (16.2 to 16.2) | 23.3 | 69 | 14.7 | 14.8 | 13.8 | render | 1155 | 3 / 0 | 0.0% | 8658 | 8994 | 43008 |
| night_life | fly | 5724 | 11.8 | 17.5 (17.5 to 17.5) | 24.1 | 69 | 16.0 | 13.6 | 12.8 | game | 1703 | 6 / 0 | 0.0% | 8627 | 8952 | 43008 |
| night_life | all | 11044 | 13.2 | 17.8 (17.8 to 17.8) | 24.1 | 84 | 16.3 | 16.3 | 15.5 | render | 1409 | 10 / 0 | 0.0% | 8688 | 8994 | 43008 |
| night_life_noshadow | walk | 1889 | 15.6 | 18.8 (18.8 to 18.8) | 26.9 | 86 | 18.8 | 16.7 | 15.7 | game | 1451 | 1 / 0 | 0.0% | 8658 | 8160 | 43008 |
| night_life_noshadow | drive | 3471 | 13.6 | 15.8 (15.8 to 15.8) | 22.1 | 78 | 14.5 | 14.8 | 13.8 | render | 1158 | 3 / 0 | 0.0% | 8755 | 8197 | 43008 |
| night_life_noshadow | fly | 5732 | 11.8 | 17.3 (17.3 to 17.3) | 24.2 | 81 | 16.1 | 13.6 | 12.8 | game | 1706 | 6 / 0 | 0.0% | 8628 | 8131 | 43008 |
| night_life_noshadow | all | 11092 | 13.2 | 17.4 (17.4 to 17.4) | 24.0 | 86 | 16.2 | 15.9 | 15.1 | game | 1398 | 10 / 0 | 0.0% | 8755 | 8197 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_life_off 5.72; night_life_rebuild 13.3; night_life 10.02; night_life_noshadow 9.99

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.95 / 1.34 (claude 0.74, zenserver 0.05, NVIDIA Overlay 0.04)

Targets: 60 fps (p95 16.7 ms) missed by: night_life_rebuild/walk 26.4 ms, night_life_rebuild/fly 18.1 ms, night_life/walk 19.1 ms, night_life/fly 17.5 ms, night_life_noshadow/walk 18.8 ms, night_life_noshadow/fly 17.3 ms; 40 fps (25 ms) missed by: night_life_rebuild/walk 26.4 ms; hitches over 100 ms: none; VRAM over 10 GB: none
