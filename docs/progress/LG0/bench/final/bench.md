**Delta Megacity**, lg0_final: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 2100 | 14.1 | 16.6 (16.6 to 16.6) | 25.8 | 81 | 16.5 | 15.0 | 14.2 | game | 1519 | 1 / 0 | 0.0% | 8651 | 10308 | 43008 |
| night_plan_all | drive | 3521 | 13.4 | 15.4 (15.4 to 15.4) | 21.4 | 66 | 14.0 | 14.6 | 13.7 | render | 1149 | 2 / 0 | 0.0% | 8623 | 10217 | 43008 |
| night_plan_all | fly | 5839 | 11.6 | 17.3 (17.3 to 17.3) | 23.3 | 78 | 16.5 | 13.1 | 12.3 | game | 1697 | 6 / 0 | 0.0% | 8623 | 10017 | 43008 |
| night_plan_all | all | 11460 | 12.9 | 16.6 (16.6 to 16.6) | 23.3 | 81 | 15.8 | 14.6 | 13.8 | game | 1438 | 9 / 0 | 0.0% | 8651 | 10308 | 43008 |
| night_life_off | walk | 2220 | 13.4 | 15.6 (15.6 to 15.6) | 23.6 | 83 | 15.2 | 14.4 | 13.6 | game | 1099 | 1 / 0 | 0.0% | 8631 | 10134 | 43008 |
| night_life_off | drive | 3539 | 13.4 | 15.1 (15.1 to 15.1) | 19.9 | 75 | 12.2 | 14.6 | 13.6 | render | 1093 | 3 / 0 | 0.0% | 8634 | 10154 | 43008 |
| night_life_off | fly | 5966 | 11.6 | 15.2 (15.2 to 15.2) | 22.0 | 70 | 13.8 | 13.0 | 12.1 | game | 1704 | 6 / 0 | 0.0% | 8634 | 10072 | 43008 |
| night_life_off | all | 11725 | 12.7 | 15.2 (15.2 to 15.2) | 21.9 | 83 | 13.6 | 14.2 | 13.4 | render | 1305 | 10 / 0 | 0.0% | 8634 | 10154 | 43008 |
| night_life_lumen | walk | 1334 | 23.1 | 25.2 (25.2 to 25.2) | 28.8 | 84 | 21.3 | 24.8 | 23.9 | render | 1702 | 1 / 0 | 0.0% | 8685 | 10233 | 43008 |
| night_life_lumen | drive | 3461 | 13.6 | 16.2 (16.2 to 16.2) | 22.7 | 72 | 14.8 | 14.8 | 13.8 | game | 1158 | 3 / 0 | 0.0% | 8654 | 10254 | 43008 |
| night_life_lumen | fly | 5643 | 11.9 | 18.1 (18.1 to 18.1) | 24.3 | 82 | 16.9 | 13.6 | 12.8 | game | 1703 | 6 / 0 | 0.0% | 8654 | 10165 | 43008 |
| night_life_lumen | all | 10438 | 13.1 | 23.6 (23.6 to 23.6) | 25.8 | 84 | 17.0 | 23.3 | 22.5 | render | 1399 | 10 / 0 | 0.0% | 8685 | 10254 | 43008 |
| night_life | walk | 2113 | 13.9 | 18.1 (18.1 to 18.1) | 25.6 | 81 | 17.7 | 15.2 | 14.3 | game | 1593 | 1 / 0 | 0.0% | 8686 | 10229 | 43008 |
| night_life | drive | 3512 | 13.5 | 15.5 (15.5 to 15.5) | 21.8 | 67 | 14.0 | 14.7 | 13.7 | render | 1156 | 3 / 0 | 0.0% | 8655 | 10237 | 43008 |
| night_life | fly | 5849 | 11.7 | 17.0 (17.0 to 17.0) | 23.5 | 85 | 15.5 | 13.2 | 12.4 | game | 1703 | 6 / 0 | 0.0% | 8656 | 10172 | 43008 |
| night_life | all | 11474 | 12.9 | 16.8 (16.8 to 16.8) | 23.4 | 85 | 15.5 | 14.6 | 13.7 | game | 1426 | 10 / 0 | 0.0% | 8686 | 10237 | 43008 |
| night_life_noshadow | walk | 2164 | 13.7 | 18.0 (18.0 to 18.0) | 23.6 | 61 | 17.8 | 14.6 | 13.8 | game | 1333 | 1 / 0 | 0.0% | 8656 | 10235 | 43008 |
| night_life_noshadow | drive | 3505 | 13.5 | 15.7 (15.7 to 15.7) | 21.7 | 76 | 14.1 | 14.6 | 13.7 | render | 1160 | 3 / 0 | 0.0% | 8754 | 10249 | 43008 |
| night_life_noshadow | fly | 5854 | 11.6 | 17.0 (17.0 to 17.0) | 24.0 | 66 | 15.8 | 13.2 | 12.4 | game | 1703 | 5 / 0 | 0.0% | 8658 | 10187 | 43008 |
| night_life_noshadow | all | 11523 | 12.8 | 16.7 (16.7 to 16.7) | 23.4 | 76 | 15.7 | 14.4 | 13.5 | game | 1353 | 9 / 0 | 0.0% | 8754 | 10249 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 6.54; night_life_off 8.61; night_life_lumen 12.61; night_life 9.49; night_life_noshadow 9.15

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 0.33 / 1 (opera 0.06, zenserver 0.04, NVIDIA Overlay 0.04)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/fly 17.3 ms, night_life_lumen/walk 25.2 ms, night_life_lumen/fly 18.1 ms, night_life/walk 18.1 ms, night_life/fly 17.0 ms, night_life_noshadow/walk 18.0 ms, night_life_noshadow/fly 17.0 ms; 40 fps (25 ms) missed by: night_life_lumen/walk 25.2 ms; hitches over 100 ms: none; VRAM over 10 GB: none
