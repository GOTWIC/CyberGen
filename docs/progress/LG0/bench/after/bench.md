**Delta Megacity**, lg0_after: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1277 | 23.4 | 26.3 (26.3 to 26.3) | 30.8 | 87 | 20.2 | 25.8 | 24.9 | render | 1751 | 2 / 0 | 0.0% | 8672 | 8965 | 43008 |
| night_plan_all | drive | 3489 | 13.5 | 16.6 (16.6 to 16.6) | 22.1 | 70 | 15.2 | 14.6 | 13.7 | game | 1154 | 2 / 0 | 0.0% | 8644 | 8953 | 43008 |
| night_plan_all | fly | 5655 | 11.8 | 18.4 (18.4 to 18.4) | 24.2 | 77 | 17.6 | 13.5 | 12.7 | game | 1699 | 6 / 0 | 0.0% | 8647 | 8847 | 43008 |
| night_plan_all | all | 10421 | 13.0 | 24.0 (24.0 to 24.0) | 26.4 | 87 | 17.4 | 23.6 | 22.9 | render | 1416 | 10 / 0 | 0.0% | 8672 | 8965 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 6.76

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.37 / 1.05 (zenserver 0.08, claude 0.06, audiodg 0.04)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 26.3 ms, night_plan_all/fly 18.4 ms; 40 fps (25 ms) missed by: night_plan_all/walk 26.3 ms; hitches over 100 ms: none; VRAM over 10 GB: none
