**Delta Megacity**, lg0_before: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 2229 | 13.3 | 14.9 (14.9 to 14.9) | 23.1 | 60 | 13.8 | 14.3 | 13.5 | render | 492 | 1 / 0 | 0.0% | 8779 | 12380 | 43008 |
| night_plan_all | drive | 3569 | 13.3 | 14.9 (14.9 to 14.9) | 19.5 | 68 | 12.3 | 14.5 | 13.5 | render | 671 | 2 / 0 | 0.0% | 8851 | 12352 | 43008 |
| night_plan_all | fly | 5945 | 11.7 | 15.5 (15.5 to 15.5) | 22.0 | 80 | 14.4 | 12.9 | 12.0 | game | 1311 | 6 / 0 | 0.0% | 8756 | 12183 | 43008 |
| night_plan_all | all | 11743 | 12.7 | 15.1 (15.1 to 15.1) | 21.4 | 80 | 13.7 | 14.1 | 13.3 | render | 745 | 9 / 0 | 0.0% | 8851 | 12380 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 5.95

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.43 / 1.58 (claude 0.1, zenserver 0.09, OneDrive.Sync.Service 0.05)

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: none; VRAM over 10 GB: none
