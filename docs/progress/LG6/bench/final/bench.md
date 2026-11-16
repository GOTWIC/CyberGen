**Delta Megacity**, final: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1758 | 15.2 | 26.8 (26.8 to 26.8) | 35.6 | 898 | 26.1 | 14.7 | 13.3 | game | 2410 | 5 / 2 | 0.0% | 10245 | 16660 | 43008 |
| night_plan_all | drive | 3002 | 15.2 | 21.4 (21.4 to 21.4) | 28.5 | 403 | 18.4 | 16.1 | 15.5 | game | 1674 | 7 / 3 | 0.0% | 10267 | 16756 | 43008 |
| night_plan_all | fly | 5119 | 12.8 | 21.0 (21.0 to 21.0) | 27.9 | 494 | 19.6 | 14.4 | 13.2 | game | 1672 | 7 / 2 | 0.0% | 10111 | 16170 | 43008 |
| night_plan_all | all | 9879 | 14.1 | 22.1 (22.1 to 22.1) | 30.2 | 898 | 20.3 | 15.1 | 14.8 | game | 1735 | 19 / 7 | 0.0% | 10267 | 16756 | 43008 |
| night_life_notransit | walk | 1853 | 14.5 | 25.7 (25.7 to 25.7) | 32.9 | 485 | 25.0 | 14.0 | 13.1 | game | 2379 | 2 / 2 | 0.0% | 10142 | 14860 | 43008 |
| night_life_notransit | drive | 3021 | 15.1 | 21.6 (21.6 to 21.6) | 28.5 | 427 | 18.4 | 15.8 | 15.3 | game | 1680 | 9 / 4 | 0.0% | 10210 | 14707 | 43008 |
| night_life_notransit | fly | 5171 | 12.6 | 20.8 (20.8 to 20.8) | 27.6 | 506 | 19.4 | 14.4 | 13.2 | game | 1667 | 7 / 1 | 0.0% | 10086 | 14284 | 43008 |
| night_life_notransit | all | 10045 | 13.9 | 22.0 (22.0 to 22.0) | 29.6 | 506 | 20.5 | 14.9 | 14.7 | game | 1741 | 18 / 7 | 0.0% | 10210 | 14860 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 8.13; night_life_notransit 18.2

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 3.02 / 5.23 (python 2.64, zenserver 0.07, claude 0.06)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 26.8 ms, night_plan_all/drive 21.4 ms, night_plan_all/fly 21.0 ms, night_life_notransit/walk 25.7 ms, night_life_notransit/drive 21.6 ms, night_life_notransit/fly 20.8 ms; 40 fps (25 ms) missed by: night_plan_all/walk 26.8 ms, night_life_notransit/walk 25.7 ms; hitches over 100 ms: night_plan_all/walk 2 a run (at most 2), night_plan_all/drive 3 a run (at most 3), night_plan_all/fly 2 a run (at most 2), night_life_notransit/walk 2 a run (at most 2), night_life_notransit/drive 4 a run (at most 4), night_life_notransit/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10245 MB, night_plan_all/drive 10267 MB
