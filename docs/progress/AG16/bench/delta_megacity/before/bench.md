**Delta Megacity**, before: 3 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| day_native | walk | 5477 | 10.9 | 36.2 (35.0 to 37.1) | 74.6 | 261 | 33.6 | 10.4 | 9.8 | game | 394 | 138 / 29 | 0.0% | 7098 | 16928 | 52224 |
| day_native | drive | 2490 | 18.4 | 40.4 (35.5 to 43.5) | 72.4 | 207 | 40.6 | 9.1 | 8.4 | game | 391 | 76 / 11 | 0.0% | 7227 | 16931 | 52224 |
| day_native | fly | 5254 | 9.9 | 30.0 (28.4 to 30.0) | 62.1 | 175 | 29.1 | 11.0 | 9.7 | game | 729 | 86 / 16 | 0.0% | 7227 | 14988 | 52224 |
| day_native | teleport | 337 | 21.6 | 42.1 (33.4 to 43.7) | 55.5 | 83 | 44.6 | 10.3 | 8.5 | game | 428 | 7 / 0 | 24.4% | 7227 | 14700 | 52224 |
| day_native | all | 13158 | 10.9 | 34.5 (34.1 to 36.6) | 67.9 | 261 | 33.4 | 10.6 | 9.6 | game | 436 | 298 / 55 | 0.0% | 7227 | 16931 | 52224 |
| day_tsr67 | walk | 6909 | 7.8 | 30.5 (28.6 to 30.6) | 65.6 | 206 | 28.4 | 8.5 | 7.7 | game | 387 | 121 / 26 | 0.0% | 6726 | 14897 | 52224 |
| day_tsr67 | drive | 2173 | 19.4 | 47.0 (46.3 to 50.0) | 81.0 | 216 | 48.7 | 8.8 | 9.0 | game | 409 | 100 / 13 | 0.0% | 6723 | 14622 | 52224 |
| day_tsr67 | fly | 5769 | 8.4 | 27.4 (27.0 to 28.9) | 56.8 | 182 | 27.4 | 10.0 | 7.2 | game | 716 | 83 / 16 | 0.0% | 6724 | 14549 | 52224 |
| day_tsr67 | teleport | 922 | 17.9 | 34.8 (33.2 to 43.8) | 52.4 | 72 | 36.1 | 9.7 | 7.3 | game | 332 | 13 / 0 | 63.9% | 6727 | 13015 | 52224 |
| day_tsr67 | all | 14960 | 8.8 | 33.1 (33.0 to 34.4) | 65.6 | 216 | 32.0 | 9.3 | 7.6 | game | 440 | 301 / 53 | 0.0% | 6726 | 15503 | 52224 |
| night_native | walk | 5516 | 12.0 | 34.4 (33.4 to 37.9) | 76.7 | 218 | 32.7 | 12.5 | 11.8 | game | 912 | 137 / 27 | 0.0% | 7232 | 13380 | 52224 |
| night_native | drive | 2136 | 19.0 | 48.1 (46.3 to 53.2) | 81.8 | 232 | 51.1 | 11.8 | 11.2 | game | 1041 | 99 / 16 | 0.0% | 7232 | 13561 | 52224 |
| night_native | fly | 4205 | 12.3 | 37.2 (31.7 to 39.1) | 75.7 | 204 | 35.4 | 11.6 | 10.0 | game | 1219 | 110 / 18 | 0.0% | 7204 | 13496 | 52224 |
| night_native | teleport | 538 | 21.3 | 42.4 (34.1 to 44.0) | 53.6 | 64 | 44.6 | 11.5 | 9.1 | game | 972 | 13 / 0 | 42.8% | 7232 | 13212 | 52224 |
| night_native | all | 11991 | 12.7 | 40.2 (38.7 to 40.8) | 78.0 | 237 | 39.0 | 12.3 | 11.6 | game | 1016 | 362 / 61 | 0.0% | 7232 | 13561 | 52224 |
| night_tsr67 | walk | 6373 | 9.0 | 32.4 (32.4 to 33.1) | 67.7 | 229 | 30.2 | 9.7 | 8.0 | game | 911 | 134 / 30 | 0.0% | 6730 | 13207 | 52224 |
| night_tsr67 | drive | 2021 | 20.1 | 48.9 (47.5 to 49.6) | 87.2 | 206 | 50.3 | 10.6 | 9.0 | game | 1045 | 98 / 13 | 0.0% | 6730 | 13453 | 52224 |
| night_tsr67 | fly | 5388 | 9.0 | 29.1 (27.9 to 30.5) | 62.8 | 182 | 28.6 | 11.4 | 7.4 | game | 1262 | 90 / 13 | 0.0% | 6700 | 13396 | 52224 |
| night_tsr67 | teleport | 899 | 17.7 | 34.6 (33.9 to 45.5) | 54.9 | 185 | 35.5 | 10.9 | 8.1 | game | 947 | 12 / 1 | 62.8% | 6731 | 13046 | 52224 |
| night_tsr67 | all | 13810 | 9.8 | 35.3 (34.8 to 36.2) | 69.7 | 233 | 34.0 | 10.6 | 7.7 | game | 1033 | 312 / 56 | 0.0% | 6730 | 13453 | 52224 |

Loads (s, after each teleport onto a segment's start, all segments): day_native 31.45; day_tsr67 26.35; night_native 11.07; night_tsr67 18.39

Targets: 60 fps (p95 16.7 ms) missed by: day_native/walk 36.2 ms, day_native/drive 40.4 ms, day_native/fly 30.0 ms, day_tsr67/walk 30.5 ms, day_tsr67/drive 47.0 ms, day_tsr67/fly 27.4 ms, night_native/walk 34.4 ms, night_native/drive 48.1 ms, night_native/fly 37.2 ms, night_tsr67/walk 32.4 ms, night_tsr67/drive 48.9 ms, night_tsr67/fly 29.1 ms; 40 fps (25 ms) missed by: day_native/walk 36.2 ms, day_native/drive 40.4 ms, day_native/fly 30.0 ms, day_tsr67/walk 30.5 ms, day_tsr67/drive 47.0 ms, day_tsr67/fly 27.4 ms, night_native/walk 34.4 ms, night_native/drive 48.1 ms, night_native/fly 37.2 ms, night_tsr67/walk 32.4 ms, night_tsr67/drive 48.9 ms, night_tsr67/fly 29.1 ms; hitches over 100 ms: day_native/walk 29, day_native/drive 11, day_native/fly 16, day_tsr67/walk 26, day_tsr67/drive 13, day_tsr67/fly 16, night_native/walk 27, night_native/drive 16, night_native/fly 18, night_tsr67/walk 30, night_tsr67/drive 13, night_tsr67/fly 13; VRAM over 10 GB: none
