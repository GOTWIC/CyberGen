**Delta Megacity**, lg8: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1762 | 14.6 | 24.4 (24.4 to 24.4) | 33.2 | 1722 | 23.4 | 14.4 | 13.4 | game | 3240 | 3 / 3 | 0.0% | 10323 | 7414 | 43008 |
| night_plan_all | drive | 2896 | 15.6 | 22.8 (22.8 to 22.8) | 31.9 | 426 | 19.2 | 16.2 | 15.6 | game | 3742 | 15 / 5 | 0.0% | 10204 | 7600 | 43008 |
| night_plan_all | fly | 4876 | 13.2 | 22.5 (22.5 to 22.5) | 30.3 | 503 | 21.0 | 15.0 | 13.6 | game | 3688 | 11 / 3 | 0.0% | 10144 | 7364 | 43008 |
| night_plan_all | all | 9534 | 14.4 | 23.0 (23.0 to 23.0) | 32.0 | 1722 | 21.0 | 15.4 | 15.2 | game | 3632 | 29 / 11 | 0.0% | 10323 | 7600 | 43008 |
| night_life_noweather | walk | 1887 | 14.3 | 25.1 (25.1 to 25.1) | 31.9 | 488 | 24.4 | 14.1 | 13.1 | game | 3300 | 3 / 1 | 0.0% | 10177 | 6846 | 43008 |
| night_life_noweather | drive | 2936 | 15.5 | 22.2 (22.2 to 22.2) | 29.2 | 404 | 18.5 | 16.1 | 15.8 | game | 3692 | 7 / 4 | 0.0% | 10279 | 6843 | 43008 |
| night_life_noweather | fly | 5049 | 13.0 | 20.4 (20.4 to 20.4) | 27.6 | 506 | 18.8 | 14.9 | 13.6 | game | 3658 | 7 / 1 | 0.0% | 10152 | 5937 | 43008 |
| night_life_noweather | all | 9872 | 14.2 | 22.1 (22.1 to 22.1) | 29.4 | 506 | 19.9 | 15.1 | 15.2 | game | 3591 | 17 / 6 | 0.0% | 10279 | 6846 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 20.04; night_life_noweather 20.04

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 3.36 / 4.06 (python 2.8, du 0.16, zenserver 0.05)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 24.4 ms, night_plan_all/drive 22.8 ms, night_plan_all/fly 22.5 ms, night_life_noweather/walk 25.1 ms, night_life_noweather/drive 22.2 ms, night_life_noweather/fly 20.4 ms; 40 fps (25 ms) missed by: night_life_noweather/walk 25.1 ms; hitches over 100 ms: night_plan_all/walk 3 a run (at most 3), night_plan_all/drive 5 a run (at most 5), night_plan_all/fly 3 a run (at most 3), night_life_noweather/walk 1 a run (at most 1), night_life_noweather/drive 4 a run (at most 4), night_life_noweather/fly 1 a run (at most 1); VRAM over 10 GB: night_plan_all/walk 10323 MB, night_life_noweather/drive 10279 MB
