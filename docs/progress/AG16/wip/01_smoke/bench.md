**Delta Megacity**, smoke: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| day_tsr67 | walk | 3616 | 22.7 | 36.4 (36.4 to 36.4) | 65.0 | 1534 | 34.7 | 28.9 | 8.5 | game | 411 | 61 / 11 | 0.1% | 6228 | 15169 | 52224 |
| day_tsr67 | drive | 1108 | 28.4 | 130.5 (130.5 to 130.5) | 221.2 | 338 | 135.3 | 30.8 | 27.1 | game | 248 | 240 / 88 | 72.2% | 6330 | 13180 | 52224 |
| day_tsr67 | fly | 2152 | 26.8 | 54.2 (54.2 to 54.2) | 109.8 | 803 | 48.4 | 34.5 | 10.4 | game | 725 | 129 / 33 | 12.6% | 6298 | 13185 | 52224 |
| day_tsr67 | teleport | 1824 | 24.5 | 50.5 (50.5 to 50.5) | 89.0 | 679 | 45.2 | 35.6 | 8.4 | game | 256 | 92 / 13 | 85.5% | 6299 | 12867 | 52224 |
| day_tsr67 | all | 6876 | 24.6 | 58.1 (58.1 to 58.1) | 133.2 | 1534 | 49.7 | 31.0 | 9.8 | game | 422 | 430 / 132 | 15.6% | 6330 | 15169 | 52224 |

Loads (s, after each teleport onto a segment's start, all segments): day_tsr67 262.59

Targets: 60 fps (p95 16.7 ms) missed by: day_tsr67/walk 36.4 ms, day_tsr67/drive 130.5 ms, day_tsr67/fly 54.2 ms; 40 fps (25 ms) missed by: day_tsr67/walk 36.4 ms, day_tsr67/drive 130.5 ms, day_tsr67/fly 54.2 ms; hitches over 100 ms: day_tsr67/walk 11, day_tsr67/drive 88, day_tsr67/fly 33; VRAM over 10 GB: none
