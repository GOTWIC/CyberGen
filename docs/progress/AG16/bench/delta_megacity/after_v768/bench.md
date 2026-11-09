**Delta Megacity**, after_v768: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| day_native | walk | 2214 | 28.7 | 99.3 (99.3 to 99.3) | 169.4 | 2630 | 99.6 | 35.2 | 14.6 | game | 372 | 494 / 110 | 0.0% | 6917 | 8638 | 43008 |
| day_native | drive | 983 | 33.6 | 142.7 (142.7 to 142.7) | 239.6 | 360 | 137.4 | 29.8 | 17.7 | game | 368 | 270 / 101 | 0.0% | 6982 | 8689 | 43008 |
| day_native | fly | 989 | 45.0 | 201.2 (201.2 to 201.2) | 291.3 | 675 | 195.7 | 33.3 | 21.9 | game | 565 | 441 / 201 | 47.0% | 6982 | 9054 | 43008 |
| day_native | teleport | 789 | 26.7 | 260.9 (260.9 to 260.9) | 377.4 | 515 | 261.0 | 29.2 | 23.0 | game | 227 | 266 / 155 | 92.5% | 6983 | 9063 | 43008 |
| day_native | all | 4186 | 33.4 | 141.7 (141.7 to 141.7) | 245.8 | 2630 | 141.8 | 33.3 | 17.9 | game | 378 | 1205 / 412 | 11.1% | 6982 | 9054 | 43008 |
| day_tsr67 | walk | 1454 | 44.5 | 180.8 (180.8 to 180.8) | 274.3 | 345 | 179.7 | 25.8 | 18.9 | game | 370 | 634 / 239 | 0.0% | 6485 | 8996 | 43008 |
| day_tsr67 | drive | 792 | 40.3 | 179.9 (179.9 to 179.9) | 326.9 | 578 | 174.7 | 26.5 | 17.0 | game | 365 | 313 / 113 | 0.0% | 6552 | 9017 | 43008 |
| day_tsr67 | fly | 797 | 50.3 | 282.8 (282.8 to 282.8) | 427.9 | 1041 | 290.3 | 29.3 | 46.7 | game | 530 | 400 / 206 | 58.7% | 6553 | 9258 | 43008 |
| day_tsr67 | teleport | 701 | 27.1 | 360.0 (360.0 to 360.0) | 512.4 | 686 | 358.1 | 28.0 | 40.5 | game | 227 | 258 / 172 | 92.3% | 6559 | 9292 | 43008 |
| day_tsr67 | all | 3043 | 44.5 | 209.9 (209.9 to 209.9) | 331.7 | 1041 | 210.0 | 27.3 | 26.1 | game | 375 | 1347 / 558 | 15.4% | 6553 | 9258 | 43008 |
| night_native | walk | 1065 | 58.3 | 253.6 (253.6 to 253.6) | 385.1 | 485 | 254.5 | 29.4 | 24.3 | game | 880 | 612 / 288 | 0.0% | 7070 | 9205 | 43008 |
| night_native | drive | 647 | 48.8 | 229.3 (229.3 to 229.3) | 440.6 | 764 | 228.4 | 31.6 | 22.1 | game | 1013 | 311 / 119 | 0.0% | 7070 | 9146 | 43008 |
| night_native | fly | 610 | 70.2 | 363.7 (363.7 to 363.7) | 516.6 | 1349 | 366.4 | 34.0 | 34.0 | game | 1080 | 395 / 211 | 73.8% | 7072 | 9221 | 43008 |
| night_native | teleport | 474 | 67.9 | 490.6 (490.6 to 490.6) | 649.3 | 846 | 491.5 | 32.0 | 74.4 | game | 910 | 269 / 188 | 91.8% | 7029 | 9315 | 43008 |
| night_native | all | 2322 | 58.5 | 275.9 (275.9 to 275.9) | 454.5 | 1349 | 276.3 | 31.2 | 26.1 | game | 955 | 1318 / 618 | 19.4% | 7072 | 9221 | 43008 |
| night_tsr67 | walk | 957 | 60.3 | 301.4 (301.4 to 301.4) | 473.3 | 872 | 302.5 | 27.3 | 43.6 | game | 864 | 541 / 290 | 0.0% | 7195 | 9540 | 43008 |
| night_tsr67 | drive | 591 | 53.4 | 247.9 (247.9 to 247.9) | 484.6 | 929 | 254.8 | 27.4 | 19.4 | game | 1014 | 312 / 126 | 0.0% | 6570 | 8723 | 43008 |
| night_tsr67 | fly | 677 | 40.1 | 396.4 (396.4 to 396.4) | 631.0 | 1556 | 400.3 | 34.1 | 50.6 | game | 1031 | 301 / 193 | 68.7% | 6571 | 8671 | 43008 |
| night_tsr67 | teleport | 765 | 27.0 | 520.9 (520.9 to 520.9) | 749.8 | 1035 | 521.1 | 30.4 | 46.4 | game | 838 | 262 / 199 | 94.8% | 6539 | 8560 | 43008 |
| night_tsr67 | all | 2225 | 53.4 | 311.0 (311.0 to 311.0) | 528.9 | 1556 | 311.0 | 29.5 | 45.8 | game | 949 | 1154 / 609 | 20.9% | 7195 | 9540 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): day_native 138.92; day_tsr67 136.55; night_native 162.05; night_tsr67 205.74

Targets: 60 fps (p95 16.7 ms) missed by: day_native/walk 99.3 ms, day_native/drive 142.7 ms, day_native/fly 201.2 ms, day_tsr67/walk 180.8 ms, day_tsr67/drive 179.9 ms, day_tsr67/fly 282.8 ms, night_native/walk 253.6 ms, night_native/drive 229.3 ms, night_native/fly 363.7 ms, night_tsr67/walk 301.4 ms, night_tsr67/drive 247.9 ms, night_tsr67/fly 396.4 ms; 40 fps (25 ms) missed by: day_native/walk 99.3 ms, day_native/drive 142.7 ms, day_native/fly 201.2 ms, day_tsr67/walk 180.8 ms, day_tsr67/drive 179.9 ms, day_tsr67/fly 282.8 ms, night_native/walk 253.6 ms, night_native/drive 229.3 ms, night_native/fly 363.7 ms, night_tsr67/walk 301.4 ms, night_tsr67/drive 247.9 ms, night_tsr67/fly 396.4 ms; hitches over 100 ms: day_native/walk 110, day_native/drive 101, day_native/fly 201, day_tsr67/walk 239, day_tsr67/drive 113, day_tsr67/fly 206, night_native/walk 288, night_native/drive 119, night_native/fly 211, night_tsr67/walk 290, night_tsr67/drive 126, night_tsr67/fly 193; VRAM over 10 GB: none
