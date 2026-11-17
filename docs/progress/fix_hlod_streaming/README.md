# HLOD streaming (fix_hlod_streaming)

Delta's night frame time while walking: LG8's profile put its slow frames on World
Partition's instanced HLOD components, which sent their instance data again as cells
streamed. An exporter and play plugin change, no milestone. Spec: `docs/unreal_export.md`,
"HLOD streaming".

## Why each HLOD flip was expensive

A quick Unreal Insights trace of the lean route's walk and drive under `night_plan_all`
(game thread, `-statnamedevents`), and a run logging each HLOD component's visibility flip
(`CityGen.HLODStatus`), found two engine behaviors behind the flood:

- **A flip recreates the render state.** World Partition hides an HLOD actor while its main
  cell is shown and shows it when the cell goes (`AWorldPartitionHLOD::SetVisibility`, each
  component's `SetVisibility`). `USceneComponent::OnVisibilityChanged` marks the render state
  dirty, so at the end of the frame each component gets a new scene proxy: instances sent
  again, materials gathered (`UStaticMesh::GetUsedMaterials`).
- **The root's flip dirties the rest.** The HLOD builder attaches all of an HLOD actor's
  components to one of them, and a component whose visibility changes marks everything
  attached to it dirty (`EVisibilityPropagation::DirtyOnly`). With only the first change made
  (the drawn flag flipped in place), 65,184 of 65,357 flips still found their component
  already dirty ([`profile/flips_attached.txt`](profile/flips_attached.txt)); with each
  component taken off the root as it begins to play, none did
  ([`profile/flips_detached.txt`](profile/flips_detached.txt): 58,854 in place, 7,365 made
  anew, every one a component first shown without a proxy).

In the whole trace (warm-up flight included), 278 frames updated 200 or more HLOD components,
834 on average, at 72 ms a frame; after the fix 72 such frames are left, all at the start and
after the warm-up's teleport, where an uncooked game's texture compiles recreate whatever uses
a newly compiled texture ([`profile/before_summary.json`](profile/before_summary.json),
[`profile/after_summary.json`](profile/after_summary.json)).

## What the walk's slow frames were made of

In the measured walk itself the HLOD flips were fewer than LG8's whole-route figure suggested:
40 walk frames with 200 or more HLOD updates before, none after
([`profile/segments.json`](profile/segments.json)), and the walk's p95 did not move with them.
Its slowest tenth of frames (31.6 ms against 13.6 for the middle half) spent the difference in
World Partition's cells being added to the world (`AddToWorld`, the cells' components
registered, 6.4 ms more), their packages' game thread loading (5.1 ms), the garbage
collector after a cell goes (4.3 ms) and the rest of the frame's streaming
([`profile/after_walk_slow_frames.json`](profile/after_walk_slow_frames.json)). The
`GetUsedMaterials` calls left on the walk (about 220 a frame, 0.7 ms) are lifegen's mid people
rebuilding their render data and the cells' own primitives being added
([`profile/after_walk_deferred_updates.txt`](profile/after_walk_deferred_updates.txt)).
Registration ran at the engine's fixed 5 ms a frame on top of a 13 ms frame.

## What changed

- **`UCityGenHLODComponent`** (play plugin): the instanced HLODs' component class, set by
  every import in the project's DefaultEditor.ini when the plugin is built. In a game it
  leaves its HLOD actor's root as it begins to play, and a visibility flip keeps its scene
  proxy and only flips the drawn flag on the render thread
  (`FSceneInterface::UpdatePrimitivesIsDrawn_RenderThread`, as the engine's FastGeo streaming
  does). The plugin's module reads the HLOD builder's config again at start (the builder's
  defaults are read before the plugin's classes exist). `build_hlods` builds all HLODs again
  when the class or `HLOD_VERSION` changes. Console `CityGen.HLODFastVisibility`,
  `CityGen.HLODStatus`.
- **The adaptive AddToWorld time slice** (`unreal.STREAMING_SETTINGS`,
  `s.AdaptiveAddToWorld.Enabled=1` in the project's `[SystemSettings]`, every import): a
  cell's actors registered 1 to 6 ms a frame by the work in flight instead of a fixed 5 ms.
- **Bench passes**: `night_plan_all_hlodslow` (the engine's flip, for a comparison) and the
  exploring `night_plan_all_stream2` (registration and loading at a fixed 2 ms) and
  `night_plan_all_adaptive`.

## Benchmark (Delta Megacity, lean route, native 2560 x 1440, RTX 4070 Ti)

`night_plan_all` p95 in ms. Before: the clothing fixes' run
([`../clothing_fixes/bench/bench.md`](../clothing_fixes/bench/bench.md)). After: the HLOD
component and the adaptive time slice, `night_plan_all` the first pass after the warm-up, two
runs (the first lost the foreground for a moment, so it ran again); about 2.3 cores of another
session's Python builds ran beside both.

| run | all | walk | drive | fly | game p95 | hitches > 50 / > 100 ms | loads (s) |
|---|---|---|---|---|---|---|---|
| before (clothing fixes) | 20.6 | 22.9 | 20.7 | 19.9 | 18.2 | 20 / 6 | 7.9 |
| **after, run 1** ([`bench/final`](bench/final/bench.md)) | **18.8** | 20.5 | 19.6 | 16.4 | 17.4 | 19 / 5 | 7.6 |
| **after, run 2** ([`bench/final2`](bench/final2/bench.md)) | **18.7** | 21.7 | 19.0 | 16.4 | 17.4 | 12 / 3 | 7.9 |

The exploring runs, each pass after the warm-up and the ones before it in the same game:

| run, pass | all | walk | drive | fly | loads (s) |
|---|---|---|---|---|---|
| [after](bench/after/bench.md), `night_plan_all` (HLOD component only, first) | 20.2 | 24.8 | 20.2 | 18.7 | 6.7 |
| after, `night_plan_all_hlodslow` (the engine's flip, second) | 20.1 | 22.4 | 20.0 | 19.4 | 11.1 |
| after, `night_plan_all_stream2` (third) | 17.9 | 18.6 | 18.3 | 16.6 | 21.0 |
| [stream](bench/stream/bench.md), `night_plan_all_stream2` (first) | 18.4 | 20.1 | 20.1 | 16.4 | 15.1 |
| stream, `night_plan_all_adaptive` (second) | 17.4 | 16.8 | 18.3 | 16.2 | 22.1 |

The HLOD component alone took the HLOD flips off the frames that streamed (the fly 0.7 ms
faster than the engine's flip in the same game) but not the walk's p95; the time slice did
that. A fixed 2 ms made the drive hitch (42 frames over 50 ms, p99 88 ms) and the teleports
two to three times slower; the adaptive slice alone (loading at the engine's 5 ms) kept the
teleports' loads and took the night under the budget. The walk is still over 20 ms at its
95th percentile (20.5 and 21.7): the cells' package loading and the garbage collector in an
uncooked game.

Frame times along the route: [`bench/final2/frame_times_night_plan_all.png`](bench/final2/frame_times_night_plan_all.png)
(and each exploring pass's beside its table). The same views before and after:
[`side_by_side/`](side_by_side/) (the city looks the same; the far city is the HLODs).

## Check

`citygen unreal --check` on Delta after the HLODs were built again: PASS (spawn, streaming,
507 traces down with 505 hits, 36 of 36 roofs, the walk, the flight, the play features), with
151,671 HLOD flips in place and 672 made anew (components first shown without a proxy) over the
check's views; 68,934 HLOD components left their roots.

## Package

Delta cooked and packaged (Development, Win64) from `CityAG16` as LG8's and the clothing
fixes', staged only and moved to `builds/packaged/Delta_hlod` (5.1 GB) in 13.4 minutes. The
smoke launch (its user folder outside the package, no `Saved` folder left in it, the game
process closed after) loads Delta in 15.8 s with the life controller ready (2,400 people, 1,800
cars, five lines, 19 trains) and no missing class (the cooked HLOD actors' components are the
play plugin's). `builds/packaged/Delta_clothing` and `CityAG16`'s `Saved/Cooked` and
`Saved/StagedBuilds` were deleted after it. The packaged game was not benchmarked.

## Tests

What changed (logs in `builds/fix_hlod` on the PC): `tests/test_unreal_hlod.py` (new),
`tests/test_bench.py`, and the cases of `tests/test_unreal.py` that cover the project
settings and flags (`test_nanite_pool`, `test_project_runs_at_the_monitors_resolution`,
`test_project_cooks_what_the_runtimes_load_by_path`, `test_play_flags`): 25 passed.

## Left

- The walk's p95 (20.5 to 21.7 ms): package loading and garbage collection while cells
  stream in an uncooked game; a packaged game does both differently (cooked packages, no
  Python plugin's collection hook, no texture compiles) and was not benchmarked here.
- Components hidden when their HLOD actor starts (around the start and after a teleport)
  are made anew once when first shown (about 7,000 at Delta's start).
