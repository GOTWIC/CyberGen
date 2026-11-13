**Delta Megacity**, atmos_visible_lights: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 2251 | 13.1 | 14.6 (14.6 to 14.6) | 23.7 | 79 | 13.1 | 14.1 | 13.3 | render | 1092 | 2 / 0 | 0.0% | 8751 | 14978 | 43008 |
| night_plan_all | drive | 3546 | 13.4 | 14.9 (14.9 to 14.9) | 19.8 | 64 | 12.4 | 14.5 | 13.6 | render | 1075 | 2 / 0 | 0.0% | 8756 | 15007 | 43008 |
| night_plan_all | fly | 6150 | 11.2 | 15.1 (15.1 to 15.1) | 21.6 | 68 | 14.0 | 12.5 | 11.6 | game | 1675 | 6 / 0 | 0.0% | 8756 | 14979 | 43008 |
| night_plan_all | all | 11947 | 12.4 | 14.9 (14.9 to 14.9) | 21.6 | 79 | 13.4 | 14.1 | 13.3 | render | 1290 | 10 / 0 | 0.0% | 8756 | 15007 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 6

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.41 / 1.11 (Notepad 0.11, zenserver 0.08, claude 0.06)

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: none; VRAM over 10 GB: none
