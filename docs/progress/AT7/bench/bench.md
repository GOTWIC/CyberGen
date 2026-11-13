**Delta Megacity**, at7: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 2230 | 13.3 | 14.8 (14.8 to 14.8) | 22.6 | 69 | 12.3 | 14.2 | 13.4 | render | 493 | 1 / 0 | 0.0% | 8783 | 15007 | 43008 |
| night_plan_all | drive | 3574 | 13.3 | 14.9 (14.9 to 14.9) | 19.6 | 66 | 12.2 | 14.5 | 13.5 | render | 670 | 2 / 0 | 0.0% | 8755 | 14952 | 43008 |
| night_plan_all | fly | 5975 | 11.6 | 15.2 (15.2 to 15.2) | 21.8 | 85 | 14.4 | 12.9 | 11.9 | game | 1314 | 6 / 0 | 0.0% | 8756 | 14753 | 43008 |
| night_plan_all | all | 11779 | 12.7 | 15.0 (15.0 to 15.0) | 21.6 | 85 | 13.6 | 14.1 | 13.3 | render | 746 | 9 / 0 | 0.0% | 8783 | 15007 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 6.01

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.28 / 0.96 (zenserver 0.08, claude 0.05, NVIDIA Overlay 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: none; VRAM over 10 GB: none
