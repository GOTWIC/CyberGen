# AG16 WIP 03: the fixes, one run each

The same frozen Delta, imported over the "before" level with the fixes, one benchmark run
each (the final three-run "after" comes last).

- [`after_v768`](after_v768): meshes shared across tiles, records grouped into actors (73,772
  actors to 13,642), props without collision, the Nanite pool from the city (512 MB), the
  underwater volumes switched by distance, the main loading range 768 m. Far worse (p95 200
  to 500 ms): the group Blueprint's root was movable while the level loaded, so its static
  components failed to attach, 160,000 log lines in bursts (72 ms of `AddToWorld` in the
  slow frames). And past 768 m the HLODs drew the city dark and untinted
  ([`after_v768/shots/day_tsr67_fly_150m.jpg`](after_v768/shots/day_tsr67_fly_150m.jpg)):
  the masters read only Custom Primitive Data, which the HLOD builder moves into
  per-instance data. Physics waits fell from 13 ms to 0.6 ms in the slow frames even so.
- [`after_v768b`](after_v768b): the root static in the Blueprint, the masters reading
  per-instance custom data. **p95 8.7 to 13.0 ms walking, driving and flying, by day and
  night, native and at 67%** (60 fps everywhere; 27 to 49 ms before), p50 7 to 11 ms, 0 or
  1 frame over 100 ms per pass, VRAM 6.6 to 7.2 GB, RAM 9.5 to 12.5 GB (13 to 17), root
  pages 43,008 (52,224), loads 10 to 15 s a pass. [`pairs`](pairs): every view of this run
  beside the same view before, by day and night: the city looks the same, the far city
  through the HLODs included.
- [`after_v768_exp`](after_v768_exp): with UE 5.8's experimental switches on top (physics
  bodies made off the game thread, incremental garbage collection): no better (1 to 2
  frames over 100 ms a pass), and incremental GC alone made a hitch-dump run far worse; not
  used.

What the remaining frames over 100 ms are (the engine's `stat dumphitches` on one day pass:
61 frames over 60 ms): 43 an HLOD actor made visible as a main cell unloads (its 1,400
instanced components taking their render state in one frame, 50 to 64 ms), 6 the texture
streaming manager's update (36 to 48 ms), 5 garbage collection (mark or sweep, 136 to 238
ms). Next: World Partition's main cells 128 m (an HLOD actor per main cell, a quarter the
size).
