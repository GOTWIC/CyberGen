**Delta Megacity**, lg4_final: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1635 | 16.3 | 26.2 (26.2 to 26.2) | 34.2 | 884 | 24.6 | 15.3 | 16.1 | game | 2405 | 8 / 4 | 0.0% | 10290 | 16746 | 43008 |
| night_plan_all | drive | 2984 | 15.5 | 21.2 (21.2 to 21.2) | 27.2 | 494 | 16.6 | 15.3 | 15.7 | game | 1690 | 3 / 1 | 0.0% | 10311 | 16844 | 43008 |
| night_plan_all | fly | 5172 | 12.7 | 20.1 (20.1 to 20.1) | 26.7 | 458 | 18.1 | 14.1 | 13.3 | game | 1695 | 8 / 1 | 0.0% | 10155 | 16403 | 43008 |
| night_plan_all | all | 9791 | 14.5 | 21.2 (21.2 to 21.2) | 29.0 | 884 | 18.8 | 14.3 | 15.5 | game | 1754 | 19 / 6 | 0.0% | 10311 | 16844 | 43008 |
| night_life_noplaces | walk | 1740 | 16.3 | 23.5 (23.5 to 23.5) | 30.8 | 478 | 22.7 | 11.9 | 16.5 | game | 2379 | 2 / 1 | 0.0% | 10318 | 15842 | 43008 |
| night_life_noplaces | drive | 2978 | 15.5 | 21.1 (21.1 to 21.1) | 29.4 | 402 | 16.5 | 15.5 | 15.7 | game | 1640 | 6 / 1 | 0.0% | 10194 | 15835 | 43008 |
| night_life_noplaces | fly | 5215 | 12.6 | 19.8 (19.8 to 19.8) | 27.2 | 442 | 17.3 | 14.1 | 13.3 | game | 1679 | 7 / 1 | 0.0% | 10100 | 11205 | 43008 |
| night_life_noplaces | all | 9933 | 14.4 | 20.9 (20.9 to 20.9) | 29.3 | 478 | 18.0 | 14.4 | 15.6 | game | 1768 | 15 / 3 | 0.0% | 10318 | 15842 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 11.68; night_life_noplaces 10.96

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.51 / 0.81 (claude 0.21, zenserver 0.05, audiodg 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 26.2 ms, night_plan_all/drive 21.2 ms, night_plan_all/fly 20.1 ms, night_life_noplaces/walk 23.5 ms, night_life_noplaces/drive 21.1 ms, night_life_noplaces/fly 19.8 ms; 40 fps (25 ms) missed by: night_plan_all/walk 26.2 ms; hitches over 100 ms: night_plan_all/walk 4 a run (at most 4), night_plan_all/drive 1 a run (at most 1), night_plan_all/fly 1 a run (at most 1), night_life_noplaces/walk 1 a run (at most 1), night_life_noplaces/drive 1 a run (at most 1), night_life_noplaces/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10290 MB, night_plan_all/drive 10311 MB, night_life_noplaces/walk 10318 MB
