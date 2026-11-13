**Delta Megacity**, at5: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 2236 | 13.2 | 14.8 (14.8 to 14.8) | 23.2 | 55 | 13.3 | 14.3 | 13.4 | render | 1096 | 1 / 0 | 0.0% | 8752 | 13801 | 43008 |
| night_plan_all | drive | 3585 | 13.2 | 15.0 (15.0 to 15.0) | 19.5 | 68 | 12.4 | 14.4 | 13.5 | render | 1081 | 2 / 0 | 0.0% | 8756 | 13574 | 43008 |
| night_plan_all | fly | 6032 | 11.5 | 15.3 (15.3 to 15.3) | 21.6 | 67 | 14.5 | 12.7 | 11.8 | game | 1683 | 6 / 0 | 0.0% | 8726 | 13356 | 43008 |
| night_plan_all | all | 11853 | 12.6 | 15.1 (15.1 to 15.1) | 21.4 | 68 | 13.7 | 14.1 | 13.2 | render | 1288 | 9 / 0 | 0.0% | 8756 | 13801 | 43008 |
| night_plan_drizzle | walk | 2277 | 13.1 | 15.5 (15.5 to 15.5) | 23.0 | 74 | 15.1 | 14.1 | 13.3 | game | 1084 | 1 / 0 | 0.0% | 8760 | 13103 | 43008 |
| night_plan_drizzle | drive | 3661 | 12.9 | 14.8 (14.8 to 14.8) | 19.0 | 69 | 12.0 | 14.2 | 13.2 | render | 1076 | 2 / 0 | 0.0% | 8858 | 12160 | 43008 |
| night_plan_drizzle | fly | 6087 | 11.4 | 14.8 (14.8 to 14.8) | 21.9 | 79 | 13.4 | 12.6 | 11.7 | game | 1681 | 6 / 0 | 0.0% | 8731 | 12068 | 43008 |
| night_plan_drizzle | all | 12025 | 12.3 | 14.9 (14.9 to 14.9) | 21.5 | 79 | 13.4 | 13.9 | 13.0 | render | 1285 | 9 / 0 | 0.0% | 8858 | 13103 | 43008 |
| night_plan_clear | walk | 2320 | 12.8 | 14.9 (14.9 to 14.9) | 22.0 | 83 | 14.4 | 13.8 | 13.0 | game | 1079 | 1 / 0 | 0.0% | 8765 | 12143 | 43008 |
| night_plan_clear | drive | 3721 | 12.7 | 14.4 (14.4 to 14.4) | 19.4 | 72 | 11.9 | 13.9 | 13.0 | render | 1075 | 3 / 0 | 0.0% | 8766 | 12166 | 43008 |
| night_plan_clear | fly | 6137 | 11.3 | 14.6 (14.6 to 14.6) | 21.6 | 80 | 13.4 | 12.5 | 11.5 | game | 1685 | 6 / 0 | 0.0% | 8735 | 12129 | 43008 |
| night_plan_clear | all | 12178 | 12.2 | 14.5 (14.5 to 14.5) | 21.2 | 83 | 13.2 | 13.6 | 12.8 | render | 1281 | 10 / 0 | 0.0% | 8766 | 12166 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 6.35; night_plan_drizzle 8.63; night_plan_clear 8.21

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.37 / 1.05 (Notepad 0.11, claude 0.05, zenserver 0.05)

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: none; VRAM over 10 GB: none
