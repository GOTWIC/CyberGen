**Delta Megacity**, after: 3 runs at 2560x1440 (NVIDIA GeForce RTX 4070 Ti, D3D12); frame times in ms, median of the runs (p95's spread min to max)

| pass | route | frames | p50 | p95 (spread) | p99 | max | game p95 | render p95 | GPU p95 | bound | draws p50 | hitches >50 / >100 ms | unstreamed | VRAM MB | RAM MB | root pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| day_native | walk | 8963 | 9.9 | 11.0 (10.8 to 33.9) | 17.8 | 90 | 8.2 | 10.7 | 9.5 | render | 374 | 3 / 0 | 0.0% | 7461 | 10304 | 43008 |
| day_native | drive | 5207 | 9.1 | 10.2 (10.2 to 37.5) | 16.5 | 66 | 8.9 | 9.7 | 8.4 | render | 397 | 2 / 0 | 0.0% | 7460 | 10003 | 43008 |
| day_native | fly | 7001 | 9.9 | 12.4 (12.2 to 37.2) | 18.8 | 74 | 10.8 | 11.1 | 9.9 | render | 676 | 5 / 0 | 0.0% | 7456 | 9891 | 43008 |
| day_native | teleport | 840 | 10.5 | 22.6 (22.6 to 37.4) | 27.1 | 82 | 22.5 | 9.6 | 8.3 | game | 325 | 1 / 0 | 35.7% | 7464 | 9778 | 43008 |
| day_native | all | 21171 | 9.6 | 11.4 (11.1 to 36.2) | 18.0 | 90 | 9.5 | 10.9 | 9.7 | render | 403 | 10 / 0 | 0.0% | 7492 | 10304 | 43008 |
| day_tsr67 | walk | 12588 | 7.0 | 8.3 (8.2 to 32.2) | 10.8 | 89 | 4.2 | 8.2 | 6.0 | render | 374 | 1 / 0 | 0.0% | 6964 | 9826 | 43008 |
| day_tsr67 | drive | 6365 | 7.2 | 9.4 (9.2 to 33.0) | 16.7 | 59 | 8.7 | 8.3 | 5.7 | game | 399 | 2 / 0 | 0.0% | 7061 | 9849 | 43008 |
| day_tsr67 | fly | 8784 | 7.4 | 10.9 (10.7 to 35.8) | 18.2 | 70 | 10.1 | 9.2 | 7.0 | game | 679 | 5 / 0 | 0.0% | 6994 | 9802 | 43008 |
| day_tsr67 | teleport | 885 | 9.7 | 22.4 (21.9 to 36.4) | 26.9 | 67 | 22.4 | 9.3 | 5.5 | game | 325 | 2 / 0 | 34.0% | 6962 | 9808 | 43008 |
| day_tsr67 | all | 27803 | 7.2 | 9.3 (9.3 to 33.8) | 15.7 | 89 | 8.1 | 8.8 | 6.8 | render | 403 | 8 / 0 | 0.0% | 7062 | 9849 | 43008 |
| night_native | walk | 8133 | 11.2 | 12.7 (12.7 to 33.5) | 13.9 | 90 | 4.9 | 12.6 | 11.8 | render | 890 | 2 / 0 | 0.0% | 7566 | 9973 | 43008 |
| night_native | drive | 4149 | 10.8 | 12.3 (12.0 to 36.0) | 18.8 | 1500 | 10.0 | 11.8 | 10.7 | render | 1025 | 6 / 2 | 0.0% | 7461 | 9750 | 43008 |
| night_native | fly | 6727 | 10.1 | 13.0 (12.9 to 37.7) | 19.7 | 400 | 11.6 | 11.3 | 10.1 | game | 1199 | 9 / 3 | 0.0% | 7474 | 9824 | 43008 |
| night_native | teleport | 833 | 11.4 | 23.3 (22.4 to 39.1) | 26.8 | 74 | 22.9 | 10.5 | 9.1 | game | 942 | 1 / 0 | 37.4% | 7440 | 9659 | 43008 |
| night_native | all | 19009 | 10.7 | 12.7 (12.6 to 35.8) | 17.6 | 1845 | 9.4 | 12.3 | 11.4 | render | 973 | 17 / 8 | 0.0% | 7566 | 9973 | 43008 |
| night_tsr67 | walk | 11159 | 7.9 | 9.6 (9.5 to 34.1) | 12.4 | 98 | 4.6 | 9.4 | 7.2 | render | 896 | 3 / 0 | 0.0% | 6969 | 9734 | 43008 |
| night_tsr67 | drive | 5610 | 8.2 | 10.5 (10.1 to 39.5) | 20.7 | 119 | 9.2 | 9.6 | 7.0 | render | 1034 | 4 / 1 | 0.0% | 6971 | 9685 | 43008 |
| night_tsr67 | fly | 8163 | 8.0 | 11.7 (11.3 to 38.9) | 18.6 | 77 | 10.6 | 10.0 | 7.2 | game | 1201 | 6 / 0 | 0.0% | 6963 | 9277 | 43008 |
| night_tsr67 | teleport | 871 | 10.6 | 22.8 (22.4 to 40.7) | 26.8 | 70 | 22.6 | 10.2 | 6.1 | game | 942 | 1 / 0 | 36.2% | 6970 | 9279 | 43008 |
| night_tsr67 | all | 24940 | 8.0 | 10.3 (10.1 to 37.1) | 16.7 | 119 | 8.7 | 9.7 | 7.2 | render | 972 | 12 / 1 | 0.0% | 7004 | 9777 | 43008 |

Loads (s, after each teleport onto a segment's start, all segments): day_native 20.02; day_tsr67 12.92; night_native 27.86; night_tsr67 13.23

Targets: 60 fps (p95 16.7 ms) missed by: none; 40 fps (25 ms) missed by: none; hitches over 100 ms: day_native/walk 0 a run (at most 2), day_native/drive 0 a run (at most 2), day_native/fly 0 a run (at most 2), day_tsr67/walk 0 a run (at most 3), day_tsr67/drive 0 a run (at most 2), day_tsr67/fly 0 a run (at most 11), night_native/walk 0 a run (at most 3), night_native/drive 2 a run (at most 4), night_native/fly 3 a run (at most 4), night_tsr67/walk 0 a run (at most 3), night_tsr67/drive 1 a run (at most 3), night_tsr67/fly 0 a run (at most 3); VRAM over 10 GB: none
