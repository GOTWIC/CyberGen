**Delta Megacity**, dlss_night: 1 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| night_plan_all | walk | 1922 | 14.8 | 21.0 (21.0 to 21.0) | 31.4 | 482 | 20.6 | 14.0 | 14.5 | game | 924 | 4 / 1 | 0.0% | 8720 | 5824 | 43008 |
| night_plan_all | drive | 3198 | 14.1 | 19.6 (19.6 to 19.6) | 27.1 | 401 | 16.4 | 14.7 | 14.0 | game | 719 | 14 / 7 | 0.0% | 8788 | 5894 | 43008 |
| night_plan_all | fly | 5298 | 12.2 | 19.8 (19.8 to 19.8) | 28.4 | 465 | 18.2 | 13.8 | 12.7 | game | 1309 | 21 / 11 | 0.0% | 8695 | 5888 | 43008 |
| night_plan_all | all | 10418 | 13.5 | 20.0 (20.0 to 20.0) | 28.8 | 482 | 17.9 | 14.1 | 14.0 | game | 870 | 39 / 19 | 0.0% | 8788 | 5894 | 43008 |
| night_plan_all_tsr67 | walk | 2758 | 9.9 | 17.7 (17.7 to 17.7) | 24.8 | 452 | 17.3 | 10.7 | 9.4 | game | 892 | 2 / 1 | 0.0% | 8204 | 5882 | 43008 |
| night_plan_all_tsr67 | drive | 4629 | 9.8 | 14.2 (14.2 to 14.2) | 21.6 | 379 | 13.7 | 10.6 | 8.9 | game | 718 | 4 / 1 | 0.0% | 8176 | 5922 | 43008 |
| night_plan_all_tsr67 | fly | 6731 | 9.6 | 16.6 (16.6 to 16.6) | 23.1 | 446 | 15.4 | 10.8 | 8.7 | game | 1315 | 7 / 1 | 0.0% | 8177 | 5895 | 43008 |
| night_plan_all_tsr67 | all | 14118 | 9.8 | 16.2 (16.2 to 16.2) | 23.1 | 452 | 15.2 | 10.7 | 9.0 | game | 851 | 13 / 3 | 0.0% | 8204 | 5922 | 43008 |
| night_plan_all_dlss_q | walk | 2930 | 9.4 | 16.2 (16.2 to 16.2) | 23.4 | 460 | 16.0 | 10.2 | 9.0 | game | 976 | 2 / 1 | 0.0% | 8087 | 5861 | 43008 |
| night_plan_all_dlss_q | drive | 4705 | 9.5 | 14.1 (14.1 to 14.1) | 22.0 | 382 | 13.6 | 10.7 | 8.5 | game | 727 | 4 / 1 | 0.0% | 8056 | 5895 | 43008 |
| night_plan_all_dlss_q | fly | 6771 | 9.5 | 16.8 (16.8 to 16.8) | 23.7 | 440 | 15.5 | 10.8 | 8.2 | game | 1316 | 7 / 1 | 0.0% | 8057 | 5832 | 43008 |
| night_plan_all_dlss_q | all | 14406 | 9.5 | 16.1 (16.1 to 16.1) | 23.1 | 460 | 15.1 | 10.7 | 8.6 | game | 889 | 13 / 3 | 0.0% | 8087 | 5895 | 43008 |
| night_plan_all_dlss_b | walk | 3086 | 8.8 | 16.2 (16.2 to 16.2) | 23.6 | 455 | 16.1 | 9.6 | 7.9 | game | 940 | 2 / 1 | 0.0% | 8036 | 5938 | 43008 |
| night_plan_all_dlss_b | drive | 4849 | 9.2 | 13.9 (13.9 to 13.9) | 21.6 | 372 | 13.7 | 10.4 | 7.6 | game | 723 | 4 / 1 | 0.0% | 7888 | 5962 | 43008 |
| night_plan_all_dlss_b | fly | 6756 | 9.6 | 16.7 (16.7 to 16.7) | 23.9 | 450 | 15.5 | 10.7 | 7.7 | game | 1314 | 7 / 1 | 0.0% | 7888 | 5881 | 43008 |
| night_plan_all_dlss_b | all | 14691 | 9.2 | 15.9 (15.9 to 15.9) | 23.4 | 455 | 15.2 | 10.6 | 7.8 | game | 862 | 13 / 3 | 0.0% | 8036 | 5962 | 43008 |
| night_plan_all_dlss_p | walk | 3141 | 8.6 | 16.0 (16.0 to 16.0) | 24.7 | 450 | 15.9 | 9.5 | 7.4 | game | 1013 | 2 / 1 | 0.0% | 8059 | 5941 | 43008 |
| night_plan_all_dlss_p | drive | 4856 | 9.2 | 13.8 (13.8 to 13.8) | 21.8 | 381 | 13.5 | 10.2 | 7.3 | game | 730 | 4 / 1 | 0.0% | 7910 | 5965 | 43008 |
| night_plan_all_dlss_p | fly | 6852 | 9.5 | 16.3 (16.3 to 16.3) | 22.9 | 435 | 15.2 | 10.5 | 7.5 | game | 1321 | 7 / 1 | 0.0% | 7910 | 5890 | 43008 |
| night_plan_all_dlss_p | all | 14849 | 9.1 | 15.8 (15.8 to 15.8) | 23.0 | 450 | 14.8 | 10.4 | 7.4 | game | 917 | 13 / 3 | 0.0% | 8059 | 5965 | 43008 |
| night_plan_all_dlss_q_fg | walk | 2278 | 12.2 | 18.9 (18.9 to 18.9) | 27.1 | 495 | 17.9 | 12.3 | 8.9 | game | 1020 | 5 / 1 | 0.0% | 8835 | 6030 | 43008 |
| night_plan_all_dlss_q_fg | drive | 3728 | 12.3 | 17.5 (17.5 to 17.5) | 25.5 | 391 | 15.0 | 13.1 | 9.0 | game | 732 | 9 / 1 | 0.0% | 8620 | 6050 | 43008 |
| night_plan_all_dlss_q_fg | fly | 5660 | 11.5 | 18.1 (18.1 to 18.1) | 26.1 | 443 | 16.5 | 12.7 | 8.6 | game | 1328 | 11 / 1 | 0.0% | 8620 | 5928 | 43008 |
| night_plan_all_dlss_q_fg | all | 11666 | 12.0 | 18.1 (18.1 to 18.1) | 26.3 | 495 | 16.4 | 12.8 | 8.9 | game | 914 | 25 / 3 | 0.0% | 8835 | 6050 | 43008 |
| night_plan_all_dlss_b_fg | walk | 2400 | 11.6 | 17.9 (17.9 to 17.9) | 26.4 | 461 | 17.6 | 12.0 | 8.3 | game | 982 | 5 / 1 | 0.0% | 8644 | 5984 | 43008 |
| night_plan_all_dlss_b_fg | drive | 3950 | 11.5 | 16.2 (16.2 to 16.2) | 24.7 | 386 | 14.6 | 12.4 | 8.2 | game | 736 | 10 / 1 | 0.0% | 8435 | 5987 | 43008 |
| night_plan_all_dlss_b_fg | fly | 5867 | 11.0 | 18.2 (18.2 to 18.2) | 25.5 | 443 | 16.5 | 12.2 | 8.0 | game | 1329 | 15 / 1 | 0.0% | 8435 | 5921 | 43008 |
| night_plan_all_dlss_b_fg | all | 12217 | 11.3 | 17.6 (17.6 to 17.6) | 25.6 | 461 | 16.2 | 12.2 | 8.2 | game | 877 | 30 / 3 | 0.0% | 8644 | 5987 | 43008 |
| night_plan_all_dlss_p_fg | walk | 2489 | 11.2 | 17.9 (17.9 to 17.9) | 25.2 | 461 | 17.2 | 11.7 | 7.8 | game | 989 | 3 / 1 | 0.0% | 8639 | 5999 | 43008 |
| night_plan_all_dlss_p_fg | drive | 4085 | 11.1 | 16.2 (16.2 to 16.2) | 23.8 | 390 | 14.7 | 11.9 | 7.7 | game | 731 | 6 / 1 | 0.0% | 8445 | 6008 | 43008 |
| night_plan_all_dlss_p_fg | fly | 5953 | 10.8 | 17.8 (17.8 to 17.8) | 25.4 | 450 | 16.2 | 11.9 | 7.8 | game | 1337 | 13 / 1 | 0.0% | 8445 | 5882 | 43008 |
| night_plan_all_dlss_p_fg | all | 12527 | 11.0 | 17.3 (17.3 to 17.3) | 24.8 | 461 | 16.0 | 11.9 | 7.8 | game | 884 | 22 / 3 | 0.0% | 8639 | 6008 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): night_plan_all 7.29; night_plan_all_tsr67 10.19; night_plan_all_dlss_q 9.83; night_plan_all_dlss_b 9.5; night_plan_all_dlss_p 9.52; night_plan_all_dlss_q_fg 9.9; night_plan_all_dlss_b_fg 9.68; night_plan_all_dlss_p_fg 9.33

Other processes' CPU during the runs (cores, mean and most; the busiest): run 1 1.41 / 6.72 (claude 0.59, CityAG16 0.34, OneDrive.Sync.Service 0.21)

Targets: 60 fps (p95 16.7 ms) missed by: night_plan_all/walk 21.0 ms, night_plan_all/drive 19.6 ms, night_plan_all/fly 19.8 ms, night_plan_all_tsr67/walk 17.7 ms, night_plan_all_dlss_q/fly 16.8 ms, night_plan_all_dlss_q_fg/walk 18.9 ms, night_plan_all_dlss_q_fg/drive 17.5 ms, night_plan_all_dlss_q_fg/fly 18.1 ms, night_plan_all_dlss_b_fg/walk 17.9 ms, night_plan_all_dlss_b_fg/fly 18.2 ms, night_plan_all_dlss_p_fg/walk 17.9 ms, night_plan_all_dlss_p_fg/fly 17.8 ms; 40 fps (25 ms) missed by: none; hitches over 100 ms: night_plan_all/walk 1 a run (at most 1), night_plan_all/drive 7 a run (at most 7), night_plan_all/fly 11 a run (at most 11), night_plan_all_tsr67/walk 1 a run (at most 1), night_plan_all_tsr67/drive 1 a run (at most 1), night_plan_all_tsr67/fly 1 a run (at most 1), night_plan_all_dlss_q/walk 1 a run (at most 1), night_plan_all_dlss_q/drive 1 a run (at most 1), night_plan_all_dlss_q/fly 1 a run (at most 1), night_plan_all_dlss_b/walk 1 a run (at most 1), night_plan_all_dlss_b/drive 1 a run (at most 1), night_plan_all_dlss_b/fly 1 a run (at most 1), night_plan_all_dlss_p/walk 1 a run (at most 1), night_plan_all_dlss_p/drive 1 a run (at most 1), night_plan_all_dlss_p/fly 1 a run (at most 1), night_plan_all_dlss_q_fg/walk 1 a run (at most 1), night_plan_all_dlss_q_fg/drive 1 a run (at most 1), night_plan_all_dlss_q_fg/fly 1 a run (at most 1), night_plan_all_dlss_b_fg/walk 1 a run (at most 1), night_plan_all_dlss_b_fg/drive 1 a run (at most 1), night_plan_all_dlss_b_fg/fly 1 a run (at most 1), night_plan_all_dlss_p_fg/walk 1 a run (at most 1), night_plan_all_dlss_p_fg/drive 1 a run (at most 1), night_plan_all_dlss_p_fg/fly 1 a run (at most 1); VRAM over 10 GB: none
