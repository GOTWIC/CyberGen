**Vesper Bay**, after: 3 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| day_native | walk | 9549 | 9.1 | 10.8 (10.6 to 27.2) | 16.5 | 89 | 7.3 | 10.6 | 9.6 | render | 565 | 3 / 0 | 0.0% | 7448 | 11992 | 41984 |
| day_native | drive | 5032 | 9.4 | 10.7 (10.6 to 31.1) | 15.6 | 64 | 8.1 | 10.4 | 9.5 | render | 462 | 2 / 0 | 0.0% | 7454 | 10366 | 41984 |
| day_native | fly | 8494 | 9.9 | 10.9 (10.9 to 30.4) | 14.3 | 65 | 8.4 | 10.8 | 9.8 | render | 941 | 6 / 0 | 0.0% | 7420 | 10461 | 41984 |
| day_native | teleport | 830 | 9.0 | 21.0 (20.8 to 34.2) | 25.1 | 68 | 20.6 | 9.1 | 8.0 | game | 696 | 1 / 0 | 31.9% | 7420 | 10465 | 41984 |
| day_native | all | 23075 | 9.4 | 10.8 (10.8 to 29.4) | 15.2 | 89 | 8.0 | 10.7 | 9.7 | render | 608 | 12 / 0 | 0.0% | 7454 | 11992 | 41984 |
| day_tsr67 | walk | 13253 | 6.7 | 8.0 (8.0 to 26.2) | 9.9 | 88 | 3.8 | 7.8 | 6.1 | render | 576 | 2 / 0 | 0.0% | 6953 | 10407 | 41984 |
| day_tsr67 | drive | 6793 | 6.8 | 8.5 (8.2 to 30.0) | 14.4 | 66 | 7.8 | 8.0 | 6.1 | game | 459 | 2 / 0 | 0.0% | 6967 | 10413 | 41984 |
| day_tsr67 | fly | 10775 | 7.2 | 9.3 (9.2 to 30.4) | 13.9 | 65 | 8.2 | 8.9 | 6.7 | render | 937 | 7 / 0 | 0.0% | 6920 | 10003 | 41984 |
| day_tsr67 | teleport | 918 | 7.3 | 19.9 (19.9 to 31.2) | 24.8 | 53 | 19.5 | 8.1 | 5.3 | game | 696 | 1 / 0 | 27.3% | 6920 | 10007 | 41984 |
| day_tsr67 | all | 30821 | 6.9 | 8.8 (8.8 to 29.1) | 13.0 | 88 | 7.3 | 8.5 | 6.6 | render | 607 | 11 / 0 | 0.0% | 7003 | 10413 | 41984 |
| night_native | walk | 8195 | 11.5 | 13.2 (13.1 to 29.4) | 13.9 | 87 | 4.2 | 13.1 | 12.3 | render | 1143 | 2 / 0 | 0.0% | 7472 | 10218 | 41984 |
| night_native | drive | 4499 | 10.6 | 12.1 (12.0 to 33.6) | 16.1 | 65 | 8.5 | 11.9 | 11.0 | render | 1348 | 2 / 0 | 0.0% | 7491 | 10244 | 41984 |
| night_native | fly | 8352 | 10.0 | 11.2 (11.1 to 33.6) | 14.4 | 65 | 8.5 | 11.1 | 9.9 | render | 1660 | 7 / 0 | 0.0% | 7495 | 10122 | 41984 |
| night_native | teleport | 823 | 9.4 | 21.0 (20.9 to 40.7) | 25.5 | 78 | 20.1 | 9.6 | 8.4 | game | 1171 | 1 / 0 | 32.2% | 7443 | 9860 | 41984 |
| night_native | all | 21046 | 10.4 | 12.8 (12.8 to 32.3) | 14.2 | 87 | 7.9 | 12.6 | 11.8 | render | 1251 | 11 / 0 | 0.0% | 7511 | 10244 | 41984 |
| night_tsr67 | walk | 11682 | 7.6 | 8.9 (8.9 to 39.6) | 10.6 | 78 | 4.3 | 8.7 | 7.5 | render | 1142 | 2 / 0 | 0.0% | 6972 | 9938 | 41984 |
| night_tsr67 | drive | 5937 | 7.8 | 9.8 (9.4 to 45.8) | 15.6 | 65 | 8.2 | 9.4 | 7.0 | render | 1342 | 2 / 0 | 0.0% | 6989 | 9963 | 41984 |
| night_tsr67 | fly | 10175 | 7.8 | 9.8 (9.7 to 42.1) | 14.0 | 63 | 8.3 | 9.5 | 6.9 | render | 1656 | 7 / 0 | 0.0% | 6957 | 10127 | 41984 |
| night_tsr67 | teleport | 898 | 7.8 | 21.5 (21.4 to 41.8) | 25.9 | 66 | 20.6 | 9.2 | 5.6 | game | 1171 | 1 / 0 | 30.1% | 6941 | 10136 | 41984 |
| night_tsr67 | all | 27870 | 7.7 | 9.5 (9.4 to 41.9) | 13.2 | 78 | 7.4 | 9.2 | 7.3 | render | 1233 | 11 / 0 | 0.0% | 6989 | 10127 | 41984 |

Loads (s, after each teleport onto a segment's start, all segments): day_native 19.85; day_tsr67 12.21; night_native 12.97; night_tsr67 12.82

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: day_native/walk 0 a run (at most 3), day_native/drive 0 a run (at most 1), day_native/fly 0 a run (at most 1), day_tsr67/walk 0 a run (at most 3), day_tsr67/drive 0 a run (at most 1), day_tsr67/fly 0 a run (at most 2), night_native/walk 0 a run (at most 3), night_native/drive 0 a run (at most 1), night_native/fly 0 a run (at most 1), night_tsr67/walk 0 a run (at most 2), night_tsr67/drive 0 a run (at most 4), night_tsr67/fly 0 a run (at most 1); VRAM over 10 GB: none
