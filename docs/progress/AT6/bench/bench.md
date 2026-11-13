**Delta Megacity**, at6: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 2189 | 13.5 | 15.2 (15.2 to 15.2) | 23.7 | 78 | 14.7 | 14.5 | 13.6 | game | 1114 | 1 / 0 | 0.0% | 8751 | 13552 | 43008 |
| night_plan_all | drive | 3531 | 13.5 | 15.2 (15.2 to 15.2) | 19.4 | 68 | 12.3 | 14.7 | 13.6 | render | 1096 | 2 / 0 | 0.0% | 8755 | 13503 | 43008 |
| night_plan_all | fly | 5901 | 11.7 | 15.8 (15.8 to 15.8) | 22.3 | 76 | 15.0 | 13.0 | 11.9 | game | 1697 | 6 / 0 | 0.0% | 8724 | 13421 | 43008 |
| night_plan_all | all | 11621 | 12.8 | 15.4 (15.4 to 15.4) | 22.1 | 78 | 14.1 | 14.3 | 13.4 | render | 1307 | 9 / 0 | 0.0% | 8755 | 13552 | 43008 |
| dusk_plan_all | walk | 2248 | 13.2 | 15.6 (15.6 to 15.6) | 23.5 | 83 | 15.2 | 14.3 | 13.4 | game | 1063 | 1 / 0 | 0.0% | 8792 | 13468 | 43008 |
| dusk_plan_all | drive | 3650 | 12.9 | 15.0 (15.0 to 15.0) | 20.8 | 84 | 13.1 | 14.3 | 13.2 | render | 1034 | 3 / 0 | 0.0% | 8795 | 13476 | 43008 |
| dusk_plan_all | fly | 5964 | 11.6 | 15.3 (15.3 to 15.3) | 22.6 | 81 | 14.1 | 12.9 | 11.7 | game | 1666 | 6 / 0 | 0.0% | 8763 | 12100 | 43008 |
| dusk_plan_all | all | 11862 | 12.4 | 15.2 (15.2 to 15.2) | 22.4 | 84 | 13.9 | 14.0 | 13.1 | render | 1275 | 10 / 0 | 0.0% | 8795 | 13476 | 43008 |
| day_plan_all | walk | 2823 | 10.2 | 13.5 (13.5 to 13.5) | 21.5 | 73 | 13.5 | 10.9 | 9.7 | game | 364 | 1 / 0 | 0.0% | 8765 | 12153 | 43008 |
| day_plan_all | drive | 4601 | 10.2 | 12.0 (12.0 to 12.0) | 19.2 | 62 | 11.1 | 10.9 | 9.8 | game | 484 | 3 / 0 | 0.0% | 8579 | 12166 | 43008 |
| day_plan_all | fly | 6139 | 11.4 | 14.9 (14.9 to 14.9) | 22.1 | 77 | 13.3 | 12.6 | 11.6 | game | 2680 | 6 / 0 | 0.0% | 8579 | 12089 | 43008 |
| day_plan_all | all | 13563 | 10.3 | 13.8 (13.8 to 13.8) | 21.1 | 77 | 12.5 | 12.4 | 11.4 | game | 930 | 10 / 0 | 0.0% | 8765 | 12166 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 5.93; dusk_plan_all 8.6; day_plan_all 8.14

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 1.03 / 1.34 (claude 0.68, Notepad 0.11, zenserver 0.07)

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: none; VRAM over 10 GB: none
