# Faster first imports with stage 2 (experiment)

An experimental branch (`claude/exp-fast-import`), not for main as it is: what makes the first
`citygen unreal` import of a city with stage 2 assets slow, and what the exporter alone
(`citygen/unreal.py`, `citygen/ue/import_city.py`) can do about it. assetgen's generators and
packs are unchanged; ideas that need assetgen are at the end.

## Headline

Greyhook with stage 2 (603 glTF packs, 28,230 meshes, 276 textures, 38,988 actors), a first
import into a new project with a derived data cache of its own, `citygen unreal` from start
to end:

| Pair | Main | Experiment | Faster |
|---|---|---|---|
| 1 | 55m41s | 22m10s | 2.5x |
| 2 (with items 8 and 9 below) | 56m01s | 14m15s | 3.9x |

The import script alone (the editor's start and shutdown aside) is 3.3x faster in pair 1 and
3.7x in pair 2. Pair 2 was planned in the other order; the experiment's first run of it
crashed in the engine after 12 minutes (item 9), so main's ran next and the experiment's
again after it with the fix: main first in both pairs.

## Conditions

- The M4 Pro Mac (14 cores, 24 GB), shared with other sessions' work. **The absolute numbers
  were taken under load**; read the ratios between the two importers, each pair run back to
  back on the same city and build.
- The load average sampled every 20 s through each run, and any other Unreal editor running:

  | Run | Started | 1 min load: min, median, max | Other Unreal editors |
  |---|---|---|---|
  | Main, pair 1 | 04:24 | 11.3, 16.8, 32.5 | none |
  | Experiment, pair 1 | 05:20 | 10.9, 19.7, 24.9 | none |
  | Main, pair 2 | 06:10 | 12.7, 21.5, 38.6 | two 30 s headless runs (the variable check of item 9) |
  | Experiment, pair 2 | 07:06 | 13.0, 20.4, 33.7 | the test suite's Unreal test, busy its first 3 minutes, then blocked |

- Through all four: this session's full test suite (pytest, `CITYGEN_WORKERS=4`); other
  sessions' Blender previews (one held up to 55 GB, swap near full by the end); and the crash
  reporters of earlier crashed throwaway editors, each spinning a core in `-Unattended` mode
  (four through pair 1, five through pair 2; found after the runs).
- Each import: a new project from the First Person template (as `--new-project` makes one),
  its derived data cache overridden to the engine's shipped pak plus a file store inside the
  project (nothing from an earlier import), `--no-hlod` (the HLOD build is a commandlet of
  its own after the import, the same for both). Main is `844228b` (main's importer has not
  changed since); the experiment `346f308` in pair 1, `f8828d6` in pair 2.

## Per phase

Seconds. "Editor start" is the editor's wall time before the import script's first line,
"editor shutdown" after its last.

| Phase | Main 1 | Exp. 1 | Faster | Main 2 | Exp. 2 | Faster |
|---|---|---|---|---|---|---|
| Editor start | 26 | 28 | 0.9x | 22 | 18 | 1.3x |
| Materials and textures | 33 | 28 | 1.2x | 27 | 21 | 1.3x |
| Blockout meshes | 30 | 22 | 1.4x | 26 | 20 | 1.3x |
| **Stage 2 packs and meshes** | **1,984** | **565** | **3.5x** | **1,880** | **523** | **3.6x** |
| Level | 41 | 21 | 2.0x | 44 | 14 | 3.0x |
| **Actors** | **574** | **183** | **3.1x** | **517** | **171** | **3.0x** |
| Play settings, streaming, graphs | 23 | 9.5 | 2.4x | 23 | 5.3 | 4.3x |
| Saving | 57 | 6.0 | 9.5x | 92 | 4.6 | 20x |
| Pruning | 271 | 64 | 4.2x | 398 | 47 | 8.5x |
| Digests | 11 | 12 | 1.0x | 15 | 6.3 | 2.3x |
| **Editor shutdown** | **283** | **384** | 0.7x | **310** | **16** | **19x** |
| Import script | 3,024 | 912 | 3.3x | 3,022 | 814 | 3.7x |
| Whole command | 3,341 | 1,330 | 2.5x | 3,361 | 855 | 3.9x |

Inside the experiment's pair 2 run: stage 2's packs imported and built 364 s, finished (slots,
collision, of which the hulls 71 s) 76 s, saved 83 s, LOD chains 0.7 s; the actors spawned
in 27 s, set up in 33 s, saved and unloaded along the way in 66 s, loaded again in 37 s. The
phases the experiment leaves as they were (the level, play settings, digests) move with the
load and with what the editor holds in memory (less, with the actors offloaded).

## What changed (exporter only)

1. **Stage 2's packs imported concurrently.** Main imports one pack at a time; the experiment
   queues every pack to import as an async task (`AssetImportTask.async_`) and waits once
   (`InterchangeManager.wait_until_all_tasks_done`). Interchange runs several imports at a
   time, and the meshes of finished packs build on every core while the next packs import.
2. **Each mesh built once, with its own settings.** Main imports a pack with Nanite on or off
   for the whole pack, then sets each mesh's Nanite settings (off for proxies and sky tube
   glass, shape preservation for plants, the full fallback for street fronts), which builds
   that mesh a second time: in Greyhook 2,671 fronts, 214 meshes with Nanite off and 100
   plants. The experiment adds a Python Interchange pipeline step (`CgPackStep`, after the
   generic pipeline) that sets them on each mesh's factory node before the build.
3. **Meshes the city does not place are not made.** The family packs hold every variant of a
   kind; a city places only some (Greyhook: 299 meshes unplaced). Main imports them all and
   the prune deletes them after the save; the pack step disables their factory nodes, so
   they are never built, saved or deleted.
4. **Textures set up before they are built.** sRGB, compression, LOD group and the normal
   map's green channel go on the texture factory nodes (`CgTextureStep`), so a texture is
   compressed once, not at import and again when main sets them after.
5. **Collision hulls without a trimesh cook.** The stage 2 meshes with boxes get
   `CTF_USE_SIMPLE_AS_COMPLEX` before GeometryScript computes their hulls, so the editor does
   not first cook a complex collision mesh that the trace flag then discards.
6. **Meshes saved in one batch.** `EditorAssetLibrary.save_loaded_assets` once for all stage
   2 meshes, not one save per mesh.
7. **Actors spawned in linear time.** Spawning an actor in the editor makes its label unique
   by scanning every actor of the level (`FActorLabelUtilities::SetActorLabelUnique`,
   through `FCachedActorLabels`), so each spawn costs more than the last and the actors phase
   grows with the square of the city's actors. The experiment saves and unloads (World
   Partition) every 2,000 actors it has made and loads them all again at the end, so the
   level never holds more than about 2,000 new actors while spawning. Same labels, folders
   and tags (benchmark below).
8. **`-fastexit` for the import.** The engine's own commandlet flag: the process ends as soon
   as the import script returns. After everything is saved, the editor spent 5 to 6 minutes
   tearing down the city's objects (editor data storage, then the object system). The
   derived data cache writes each entry whole (a temp file, then a move), so an entry still
   being written when the process ends is only built again by the next user; the import's
   editor writes no asset registry cache either way. What is left of pair 2's 16 s is
   citygen's wait (`PIPE_GRACE_S`, 15 s) for a helper process holding the editor's output.
9. **No distance field or Lumen card tasks in the import's editor.** Every imported mesh has
   none (distance field resolution 0, no cards), but with the project's
   `r.GenerateMeshDistanceFields` on, each build still queues a task that builds an empty
   one. With every pack imported at once that queue falls far behind, and in pair 2's first
   run a task read a sign mesh's source model while the LOD chains were adding LODs to it:
   SIGSEGV in `FDistanceFieldAsyncQueue::Build` (an engine race main can meet too, with a
   smaller window). The import's editor now starts with
   `-ini:Engine:[/Script/Engine.RendererSettings]:r.GenerateMeshDistanceFields=False,[SystemSettings]:r.MeshCardRepresentation=0`:
   no queue at all, for that process only, the project's settings untouched. Neither
   variable is in the static mesh cache key, so the meshes built stay valid in an editor
   that has them on (which builds the empty entries when it needs them).

`CITYGEN_UE_FAST=0` turns all of it off (main's path); `CITYGEN_UE_OFFLOAD=N` sets the
offload chunk (0: none).

## The same result

- **Actors and assets:** the importer's own digests (every actor's key and hash, every
  asset's path and hash) are identical in all four projects (actor digest
  `2707575a83550e77`, asset digest `015368d72d5d87ff`, 38,988 actors, 33,273 assets).
- **A deep digest** (an editor run over each project: every actor's class, label, folder,
  tags, transform, components, mesh, mobility, collision profile, custom primitive data,
  material overrides and instances; every asset's class, hash, Nanite settings, material
  slots, collision (trace flag, boxes, hulls), LOD count, LOD screen sizes, bounds and vertex
  counts; every texture's settings and size): all 38,988 actors the same field for field in
  all four, all 33,566 assets the same but for one field of 900 or so meshes, below.
- **Vertex counts:** between any two of the four projects about 900 of the 28,230 stage 2
  meshes differ in their LOD 0 vertex count (913 between main's two imports, 942 between
  the experiment's two, 936 and 951 across), every one a Nanite mesh with the automatic
  fallback (most of them building shells, a few props and street pieces). That is the
  engine: of the 29,611 mesh build records two projects' caches share (the same key, so the
  same mesh, settings and builder), 4,868 hold different bytes; the Nanite build gives a
  slightly different fallback from one run to the next, main's included.
- **A second import changes nothing:** into the experiment's pair 2 project, with the
  experiment's importer: 38,988 actors unchanged, none created, updated or deleted; every
  blockout and stage 2 mesh, material and pack kept; no package saved; 53 s in the editor
  (a third import, before the check, the same). The one exception is the sign pages of the
  prune bug (below): imported again, deleted again.
- **`--check` passes** on that project: the level streams around the player (30,485 of the
  38,988 actors loaded at the start, 2,184 more after a teleport), 507 of 507 traces down
  hit (buildings, raised roads, junctions, ground, green roofs, plazas), 36 of 36 roofs and
  36 of 36 facades, the walk along a sidewalk reached its end with every frame on the
  ground, and the fly pawn flew 306 m.

## Spawning, without the load

The clean evidence for item 7, from two benchmarks in a new World Partition level of an
empty project (a cube mesh, a label, a folder, a transform and tags per actor):

- **Spawning into one level:** 1,500 actors at a time, the cost per actor grew with the
  actors already there: 0.17 ms with none, 0.52 ms past 1,500, 0.93 ms past 3,000. With
  $c(n) \approx a + b\,n$ per spawn, $N$ actors take $aN + bN^2/2$; at Greyhook's
  $N = 38{,}988$ that is minutes of label scans.
- **Spawning with offloads** (save and unload every 3,000): 0.16, 0.24 and 0.36 s per 1,000
  actors within each chunk, back to 0.16 after every offload, the same from the first chunk
  to the twelfth; each offload 1.9 to 2.6 s, loading all 12,000 again 1.4 s, every actor with
  its mesh after the reload.

## What is left in the exporter

- **The Nanite builds** are now most of the import (the packs' import and build: 364 s of
  pair 2's 814 s in the editor). They run on every core, so a loaded Mac shows it most.
- **Memory:** with the packs in flight at once the import's editor peaks at 42 to 43 GB (the
  engine's count of its footprint; main 38.5 GB), on this 24 GB Mac mostly in swap. A machine
  with less memory may want fewer imports in flight than Interchange's default (half the
  worker threads).
- **Hulls on the game thread** (71 to 86 s): GeometryScript's convex decomposition per
  building mesh, one at a time. Hulls in the packs would remove it (below).
- **Saving the meshes** (83 to 92 s for 28k packages) and **the actors** (World Partition
  writes a package per actor: 39k files, now saved along the way).
- **The prune** still takes most of a minute to delete 5 assets: a garbage collection over
  all the import holds, then the delete's own search for references. Those 5 are the city's
  sign pages, which it should not delete at all (below); with that fixed, a first import has
  nothing to prune.
- **A reimport's prune** with many meshes to delete can be far slower: one in another
  session on this Mac ran past 90 minutes (not profiled here).
- **A crashed editor's crash reporter** (`CrashReportClient -Unattended`) spun a core until
  stopped, hours after the crash; an import that crashes could stop it.
- **A fresh engine install compiles its shaders** the first time a project opens in the full
  editor (`--check`'s start took 10 minutes in a new project); nothing the importer does
  changes that.

## Found on the way: the prune deletes the city's sign pages (main too)

`prune_meshes` deletes every asset under `<root>/Assets` that no stage 2 entry names, except
`Assets/Materials`. AG6's city texture pages live in `Assets/Textures`
(`TEXTURE_FOLDER_CITY`), so every first import with AG6's signs force-deletes them after
importing them (Greyhook: `T_city_ads_0`, `T_city_ads_1`, `T_city_logos`,
`T_city_signs_tall_0`, `T_city_signs_wide_0`; the log's "deleting 5 stage 2 meshes"), and
the force delete clears them from the sign material instances, which are saved so. Both
importers do it (271 of 276 textures left in every project); a second import imports them
again and deletes them again. Left as it is here so the experiment matches main.

## For the assetgen coordinator (ideas that need assetgen changes)

- **Per-city packs without unplaced variants.** The family packs hold every variant of a prop
  or plant kind; Greyhook places 28,230 of their 28,529 meshes. The experiment skips the rest
  at the factory node, but Interchange still reads and translates them; packs with only what
  the city places would not be read at all.
- **Collision in the packs.** AG1 already makes convex pieces per mass
  (`buildings/collision.py`); written into the packs as `UCX_` meshes (Interchange's
  collision convention) they would replace the exporter's GeometryScript hulls (71 to 86 s
  on Greyhook, on the game thread).
- **Quantized sign packs** (`KHR_mesh_quantization`, which `assetgen/gltf.py` can already
  write), if Interchange's glTF reader takes them: smaller packs to read.
- **Fewer actors.** 38,988 actors means 38,988 actor packages to spawn, save and load. Street
  pieces and other small static pieces per tile as one instanced actor, each piece's key kept
  as an instance id (as M15 does for props), would cut the actors phase and the saves; it
  changes the manifest's actor shape, so it is a design decision, not this experiment's.
