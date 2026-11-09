# AG16 WIP 01: the benchmark's first run (smoke)

Delta Megacity as main builds it (65d5ba8, model sha256 `6a0ffbba...`), imported into a
throwaway project, one run of the day pass at a 67% screen percentage. The window was
2048 x 1152, not 1440p (the game was DPI-unaware: fixed after this run), so these are not
the "before" numbers, only the first look:

- **Bound by the game thread everywhere**; the GPU's p95 is 8 to 10 ms.
- **The game thread's frame**: about 6 ms of async loading every frame (World Partition
  loads 4 cells at all times, 43,000 to 67,000 actors loaded with the 1,500 m range), 3 to
  12 ms waiting for physics (body creation as cells stream; 12 ms while driving), and 5 to
  7 ms waiting for the render thread, which waits 6 to 12 ms on visibility.
- **The drive** at 25 m/s outruns streaming: 72% of its frames have cells within 100 m not
  yet in, p95 130 ms.
- **Loads**: 262 s in all for the six segment starts.
- **Nanite root pages**: 52,224 in use of 57,344 (pool 256 MB).
- **Memory**: the game process holds about 16 GB of RAM and 33 GB committed.

`frame_times_day_tsr67.png`: frame, game and GPU times along the route.
