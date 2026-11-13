**Delta Megacity**, fix_play_cars: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 2133 | 14.0 | 15.6 (15.6 to 15.6) | 24.5 | 81 | 14.6 | 15.0 | 14.1 | render | 969 | 1 / 0 | 0.0% | 8618 | 15455 | 43008 |
| night_plan_all | drive | 3519 | 13.5 | 15.3 (15.3 to 15.3) | 19.7 | 59 | 12.8 | 14.7 | 13.6 | render | 1101 | 2 / 0 | 0.0% | 8623 | 15467 | 43008 |
| night_plan_all | fly | 6032 | 11.4 | 15.7 (15.7 to 15.7) | 21.8 | 90 | 15.0 | 12.8 | 11.7 | game | 1703 | 6 / 0 | 0.0% | 8624 | 15473 | 43008 |
| night_plan_all | all | 11684 | 12.7 | 15.5 (15.5 to 15.5) | 21.6 | 90 | 14.2 | 14.5 | 13.7 | render | 1179 | 9 / 0 | 0.0% | 8624 | 15473 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 6.4

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.84 / 1.2 (claude 0.47, Notepad 0.11, zenserver 0.08)

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: none; VRAM over 10 GB: none
