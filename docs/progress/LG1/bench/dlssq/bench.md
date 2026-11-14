**Delta Megacity**, lg1_dlssq: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all_dlss_q | walk | 2337 | 10.8 | 22.3 (22.3 to 22.3) | 30.1 | 457 | 21.7 | 11.1 | 9.8 | game | 1938 | 3 / 1 | 0.0% | 9618 | 12814 | 43008 |
| night_plan_all_dlss_q | drive | 4656 | 9.6 | 14.7 (14.7 to 14.7) | 21.3 | 382 | 14.1 | 10.6 | 8.4 | game | 677 | 3 / 1 | 0.0% | 9446 | 12192 | 43008 |
| night_plan_all_dlss_q | fly | 6539 | 9.8 | 17.6 (17.6 to 17.6) | 23.7 | 444 | 16.7 | 10.6 | 8.0 | game | 1269 | 7 / 1 | 0.0% | 9080 | 11483 | 43008 |
| night_plan_all_dlss_q | all | 13532 | 9.9 | 17.9 (17.9 to 17.9) | 25.3 | 457 | 17.1 | 10.7 | 9.2 | game | 886 | 13 / 3 | 0.0% | 9618 | 12814 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all_dlss_q 7.11

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.51 / 0.75 (claude 0.27, zenserver 0.08, NVIDIA Overlay 0.03)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all_dlss_q/walk 22.3 ms, night_plan_all_dlss_q/fly 17.6 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all_dlss_q/walk 1 a run (at most 1), night_plan_all_dlss_q/drive 1 a run (at most 1), night_plan_all_dlss_q/fly 1 a run (at most 1); VRAM over 10 GB: none
