# AT0 WIP 02: the first night in Unreal

One run (a smoke test) on Delta in CityAG16: the play features' night (`night_native_*`)
and the plan's lights with volumetric fog, rain and wet streets (`night_plan_all_*`).
At street level in the Corporate Core the plaza is lit, puddles mirror the neon and the
signs' colors spill onto the sidewalk. From the air the plan lights only within 300 m of
the view, so the far streets went dark where the play features' light pools had lit them:
since this run the play features keep their pools past the plan's live range
(`CityGen.PlayLamps 2`, AT0's far tier), and the puddles are fewer and smaller.

The run itself was starved of CPU (the derived data cache's maintenance scanned 417,717
files for 16 minutes during it, 172 textures were built again): every pass alike, so its
frame times are not the benchmark's (that is `docs/progress/AT0/bench`).
