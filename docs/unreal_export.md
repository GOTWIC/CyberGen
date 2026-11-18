# Unreal exporter

One exporter takes every stage's output into Unreal Engine 5.8. It is not a stage and has no
milestones of its own: stage 1 introduces it (M15), and every later milestone, in any stage,
updates it in the same PR for what that milestone adds or changes, so the level it builds
always matches the generators. This page is its spec and the record of what each milestone
changed in it. (`unreal/` at the repo root is the earlier hand-tracing pipeline's greybox
script, not this exporter.)

## Where it lives

- **M15** introduces it as `citygen unreal BUILD UPROJECT [--check] [--shots DIR]
  [--new-project]` (and the play options below): `citygen/unreal.py` on the venv side (manifest, glTF prototypes, flat
  graphs, engine discovery, project preparation, editor runs; no Unreal needed, tested in
  pytest) and `citygen/ue/import_city.py`, `citygen/ue/check_city.py` inside the editor
  (stdlib and `unreal` only). Details: `docs/progress/M15/README.md`. The play features
  (below) add `citygen/unreal_play.py` (venv side) and the C++ plugin
  `citygen/ue/CityGenPlay`, built into the project.
- **After M15 merges**, a small refactor moves it into a package of its own beside the
  generators, split into a core (the manifest format, layering, project and editor
  handling, the import and check scripts, the shared engine assets) and stage 1's
  contribution (the blockout). `citygen unreal` stays as the command. Each later stage's
  contribution lives in its own package and only writes manifest entries; changes to the
  core go with the milestone that needs them.

## What it builds (M15)

| What | In the project |
|---|---|
| a World Partition level per city | `/Game/CityGen/<City>/Maps/<City>` |
| a static mesh actor per blockout object (buildings, skybridges, decks, megasite elements, streets and ground joined per category and 256 m tile), Nanite on, complex collision | `/Game/CityGen/<City>/Meshes/<tile>/` |
| a material instance per blockout material, parent `M_CityGen` | `/Game/CityGen/<City>/Materials/` |
| props and plants as hierarchical instanced meshes, one actor per kind and tile, with the instances' ids | `BP_CityGenInstances` actors |
| the lane, walkway and transit graphs as data assets | `BP_CityGenGraph` assets |
| M16: a water physics volume per box of a water body and tile (the player swims in a canal, a river or the sea instead of falling through it) | `PhysicsVolume` actors, `CityGen/swim` |
| M20: the large ads (neon billboards and banners on the facades, holo-boards over roofs and in front of facades) as hierarchical instances of a unit prototype per kind (`sign_billboard`, `sign_banner`, `sign_holo`), one actor per kind and tile (`sign.<kind>.<tile>`), scaled to each slot's width and height | `BP_CityGenInstances` actors |
| a player start, a sun, a sky light and the sky atmosphere | always loaded |
| the walker (the play plugin's first-person character wearing the project's own character's body) and its game mode, the level's game mode override with `--play walk` (the default) | `/Game/CityGen/Core/BP_CityGenWalker`, `GM_CityGenWalk` |
| a fly pawn and its game mode, the level's game mode override with `--play fly` | `/Game/CityGen/Core/BP_CityGenFlyPawn`, `GM_CityGenFly` |
| the far view: the level's instanced HLODs, built after the import | World Partition HLOD actors |
| with stage 2 (AG1, AG7): a static mesh actor per building shell and street piece at its own pivot, in place of the blockout actors it replaces; parts as hierarchical instances per entry and kind; AG4's skybridges by id and roof equipment instanced per tile | `/Game/CityGen/<City>/Assets/<Part>/<tile>/` |
| stage 2's masters and an instance per part and slot | `/Game/CityGen/Core/M_Cg*`, `/Game/CityGen/<City>/Assets/Materials/` |
| with AG6: textures (the shared library, imported once per project; a city's sign pages), textured masters, `Night` in a parameter collection, an instance per material key (era variants of the wall and roof slots) | `/Game/CityGen/Core/Textures/`, `Core/MPC_CityGen`, `/Game/CityGen/<City>/Assets/Textures/` |

Actors carry `cg.city`, `cg.key`, `cg.hash`, `cg.id`, `cg.type`, `cg.category`, `cg.tile` and
`cg.district` tags. Frames: citygen's (x east, y north, z up, meters) to Unreal's at
(100 x, -100 y, 100 z) centimeters, a citygen yaw to Unreal yaw -yaw.

## Import, open and play

```bash
.venv/bin/python -m citygen build cities/vesper_bay/city_spec.json out/vesper_bay --blockout
.venv/bin/python -m citygen unreal out/vesper_bay ~/CityTest/CityTest.uproject --new-project
```

On Windows (PowerShell) it is the same with the venv's Python and Windows paths:

```powershell
.venv\Scripts\python -m citygen unreal out\vesper_bay "$HOME\Documents\Unreal Projects\CityTest\CityTest.uproject" --new-project
```

`--new-project` makes the project from the engine's First Person template the first time and
uses it as it is after that. The importer runs Unreal itself, headless, so close the project
in the editor before importing. It uses the newest UE 5.x in the usual place
(`C:\Program Files\Epic Games\UE_5.8` on Windows, `/Users/Shared/Epic Games/UE_5.8` on a
Mac); `--engine` or `CITYGEN_UE_ROOT` names another.

While it runs, `citygen unreal` shows on stderr where it is: one line per stage (the
editor starting, materials and textures, the blockout meshes, stage 2's packs and meshes
with how many were built and how many with Nanite, the level, the actors, saving, pruning,
the editor shutting down, the HLOD build, and with `--check` its loading, shots, walk and
flight), a bar with the count and the time left where a stage has a count, and on a first
import an estimate of the time left in all (from this Mac's times, corrected as the stages
go). In a terminal the line redraws in place; piped to a file it writes a few plain lines per
stage. At the end it lists each stage's time. `--quiet` (or `CYBERGEN_QUIET=1`) turns it off.

Then open the project: the editor opens on the city, and Play (Alt+P) puts you in it.

- **Startup map.** Each import makes the city the project's `EditorStartupMap` and
  `GameDefaultMap` (`Config/DefaultEngine.ini`). With several cities in one project the last
  import wins; File > Open Level opens another (`/Game/CityGen/<City>/Maps/<City>`), and
  `--no-startup` leaves the project's maps as they are.
- **Walking** (the default, `--play walk`; since the play fixes of 2026-11-12, flying
  before): a person in first person, with a body you see when you look down (the play
  plugin's `ACityGenWalker`, made into `/Game/CityGen/Core/BP_CityGenWalker` wearing the
  body of the project's own character: its default game mode's pawn's character mesh, its
  animation and placement; the First Person template's world body, SKM_Manny_Simple with
  ABP_Unarmed, which that template hides from its own player and shows only arms). The
  eyes sit 1.64 m up, a little forward of the neck (further forward looking down); in the
  player's own view the head is hidden (`HiddenBone`, `neck_02`) while a second copy of
  the body, drawn into shadows only, casts the whole figure's shadow; seen from the free
  camera the head is back. The body turns with the view. W, A, S and D (or the arrow keys) walk,
  the mouse looks, Shift runs, Space jumps; a gamepad's left stick walks. It collides with
  the city and steps up curbs and stairs (45 cm). The play features' `.` swaps it for the
  free camera and back (it waits where you left it). The console's `ghost` (through
  walls), `fly` (flying, with collision) and `walk` work as usual. Where the play plugin
  cannot be built, walking is the project's own game mode and character.
- **Flying** (`--play fly`): a free camera with no collision, at 50 m/s
  (`--fly-speed`). W, A, S and D (or the arrow keys) move, the mouse looks, E or Space
  rises, Q or C sinks; a gamepad works too. The speed is set at import; in the editor it is
  the Max Speed of `/Game/CityGen/Core/BP_CityGenFlyPawn`'s movement component (in
  centimeters per second) until the next import sets it again.
- **The project's own** (`--play project`): its own game mode and character, as the project
  sets them (the First Person template's with `--new-project`: arms only).
- **Switching without importing again:** the level's World Settings, GameMode Override:
  `GM_CityGenWalk` walks, `GM_CityGenFly` flies, None is the project's own. Shift+F1 frees
  the mouse while playing, Esc stops.
- **A packaged game's proof:** `-CityGenSelfie=SECONDS` on the game's command line takes a
  screenshot looking down at the body and one looking ahead that long after the walker
  spawns, logs `CITYGEN_WALKER` lines (its class, body, place, whether it stands on the
  ground) and quits. Launch it with `-userdir=` a folder outside the package, so the run leaves
  no `Saved/` in it (its saved window size would stick for the next player).
- **Streaming.** The city loads in 128 m cells within 768 m of you (`--view-range`; 256 m cells to 1,500
  m before AG16, which loaded most of a sample city at once and streamed it all the time).
  Beyond that you see the far view, World Partition's HLODs (the city's own meshes and
  materials, instanced in 256 m cells, out to the whole city, each building with its own
  Custom Primitive Data, so it looks as the city does up close), which each import builds
  after the city: about 2 minutes for a blockout city and 10 with stage 2's buildings on a
  Mac the first time, under a minute when nothing changed (only the cells whose actors
  changed are built again).
  `--no-hlod` skips them, and the city then ends at the view range. A sample city is about
  3.5 km across: `--view-range 3000` loads most of it around you, for more memory and
  streaming (AG16's benchmark: the 95th percentile frame went from 27 to 49 ms to 9 to 13 ms
  on Delta Megacity with the shorter range and AG16's other fixes).
- **`--check`** plays the level twice in the editor, without saving it: walking with the
  walker whatever `--play` set (the project's character where the importer made no walker:
  where it spawned and what it stands on, whether it has a body it sees, streaming,
  collision, a walk along a sidewalk, off a curb onto the road and back up; with `--shots`
  `unreal_walk_body.png` and `unreal_walk_ahead.png` by day, standing at the eye of a `--view
  walk_spot ...` and facing its target when one is given; `walk_spot__clear` in that
  weather state, and at `CITYGEN_UE_VIEW_RES`'s size as the play views), then flying with the fly pawn (its speed, no collision, the city loaded where it ends).
  The walk and the flight report how long their frames took (median, 95%, longest). With
  `--shots DIR` it renders views of the city (each once small first, so its Nanite pages
  have streamed in) and two from the fly pawn. The views load the whole city in the editor,
  or for a city with more than 42,000 meshes (the manifest's, by actor key) the actors
  nearest its middle up to 42,000 of them, for every view (`SHOT_MESHES`): every Nanite
  mesh in memory takes a root page, the pool stops at 49,152 on the Mac (2 GB), where the
  editor quits on a fatal error, and an actor unloaded between views keeps its meshes'.
- **Roof traces** (#83): the collision check's trace down onto a building counts when it
  stops 3 m over the ground the building stands on, the bottom of its actor's bounds or,
  for a stage 2 building, its pivot (its base) where that is lower: a stage 2 shell starts
  at its street front's top (7.5 m up on a one-storey shed or yard, its roof 2.5 m over
  that) or is an open shed's roof slab alone, so Delta's Industrial Port sheds and yards
  missed with their hulls in place (31 of 36 roofs in run-through 2).
- **Nanite's root pages** bound how big a city can be on this route: Cragmouth's 63,700
  Nanite meshes (stage 2 and blockout) overrun them in play, and the editor quits before
  the first frame (the far view's instanced HLODs and the view range make no difference;
  the AG5 Unreal check, `docs/progress/AG5/unreal/`), and so do Vesper Bay Decks' 50,008
  (the AG10 check). Greyhook (34,000) and Vesper Bay play.
- **A smaller streaming pool for a big city** (run-through 2): the root pages share one
  GPU buffer of at most 2,048 MB with Nanite's streaming pool (512 MB by default), so there
  are 49,152 of them. Delta Megacity with AG15's parts places 53,790 Nanite meshes, and its
  first Play on the Windows PC quit on "Cannot allocate more root pages 49152/49152".
  Since AG16 every import sets the pool from the city (`unreal.nanite_pool_mb`,
  `set_nanite_pool`, in the project's `[SystemSettings]`): what its distinct Nanite meshes'
  root pages (`unreal.nanite_meshes`, counted as the check counts them, times
  `ROOT_MARGIN` 1.1: a mesh keeps its root page while it stays loaded, and over a route
  nearly every one does, 52,224 in use of Delta's 53,911 in AG16's benchmark) leave of the
  2,048 MB, in 64 MB steps, from 256 MB (57,344 root pages: a city with more meshes is over
  `asset_budget`) to 1,024 MB. Delta with AG16's shared meshes (44,667) gets the engine's
  512 MB; before, 256 MB (`NANITE_MANY` 42,000 then set 256 MB). The check's editor views still
  load up to 42,000 meshes that keep their root pages into the walk, so on such a city
  `CITYGEN_UE_PLAY_SHOTS_ONLY=1` leaves them out (only the play window's shots and the
  `pday_*` and `night_*` views, rendered from the free camera in the play world, by day and
  by night, 1920 x 1080).
- **Memory on the import**: the actors are saved and unloaded every 2,000
  (`CITYGEN_UE_OFFLOAD`); Delta's first import on the Windows PC (32 GB, other apps open)
  ran out of memory at 61,000 of its 73,293 actors ("The paging file is too small"), and
  `CITYGEN_UE_OFFLOAD=500` imported the rest.
- **Back to the blockout** (#85): `--blockout-only` over a stage 2 import updates in place
  the actors whose keys both layers have (the same class, so `manifest_changes` counts them
  as updated); each is given the blockout's settings again (`import_city.unstage`: its
  rotation, no slot materials, collision profile `BlockAll`, cull distances, shadow, HLOD),
  as a freshly spawned one has them. `CITYGEN_UE_DIGEST_ROWS=1` writes what an import's
  digests hash (each actor's tags, mesh, location and yaw; each asset's hash) to
  `unreal/digest_rows.json`, to tell two imports apart.
- **Nanite in the editor on the Mac**: UE 5.8 renders these levels with Nanite off
  (`UseNanite(METAL_SM6) returned false`), so every Nanite mesh draws its fallback; an
  entry whose small parts must show and collide asks for a full one (`fallback_full`:
  AG3's fronts, AG10's deck pieces). A mesh imported again whose entry no longer asks for
  it goes back to the automatic fallback.

| Flag | Default | |
|---|---|---|
| `--play walk`, `fly` or `project` | `walk` | what Play puts you in |
| `--fly-speed M_PER_S` | 50 | the fly pawn's top speed |
| `--view-range M` | 768 | how far around you the city streams in (AG16; 1500 before) |
| `--no-hlod` | off | skip building the far view (HLODs) after the import |
| `--no-startup` | off | leave the project's startup and default map as they are |
| `--new-project` | off | make the project from the First Person template if it is missing |
| `--blockout-only` | off | leave out stage 2's buildings and streets |
| `--check`, `--check-only`, `--shots DIR`, `--view ...` | | play and check the level, render views |
| `--no-play` | off | leave out the play features (below) |
| `--dlss DIR` | `$CITYGEN_DLSS` | NVIDIA's DLSS plugin, extracted from its zip: copied into the project and set up ("DLSS" below) |
| `--quiet` | off | no progress on stderr |

### The fast import

A first import with stage 2's assets spends most of its time importing and building the
packs' meshes and spawning the actors. By default the importer takes the fast path
(`citygen/ue/import_city.py`, notes and measurements in `docs/progress/exp_fast_import/`):

- **Packs at once:** every stage 2 pack to import is queued as one async Interchange import
  and waited for once, so packs import side by side and their meshes build on every core.
- **Each mesh built once:** a Python Interchange pipeline step (`CgPackStep`) sets each
  mesh's Nanite settings (on or off, shape preservation, the full fallback) on its factory
  node before the build, and leaves the meshes the city does not place (the family packs'
  other variants) unmade; textures get their color space, compression, group and green
  channel the same way (`CgTextureStep`). AG12's water packs keep their water pipeline.
- **Saves in batches:** stage 2's meshes saved in one call; the actors saved and unloaded
  every 2,000 made (`CITYGEN_UE_OFFLOAD`, 0 for never), since each spawn scans every loaded
  actor's label, and loaded again at the end.
- **The import's editor:** started with `-fastexit` (it ends once the script has saved
  everything, not after minutes of teardown) and with mesh distance fields and Lumen cards
  off for that process only (`-ini:` overrides; every imported mesh has none anyway, and
  their task queue could race the LOD chains). The project's own settings are untouched.

The result is the same level: the same actors, assets and hashes as the one-at-a-time path,
and an import over it updates by key and hash as always. `CITYGEN_UE_FAST=0` in the
environment takes the one-at-a-time path instead (each pack imported, each mesh built and
then set, saved one by one, the editor's own shutdown), for comparison or if an engine
version's Interchange misbehaves with concurrent imports; it needs a little less memory.

### Opening a big city

- **The first Play** of a large city takes minutes, not seconds: Unreal shows nothing until
  every cell within `--view-range` of the player has loaded (Delta Megacity's middle: about
  46,000 meshes), and Windows marks the editor "Not Responding" meanwhile. It is loading, not
  frozen; later Plays in the same editor session are much faster. The 768 m default (AG16)
  loads a quarter of what 1,500 m did.
- **On Windows**, add the project folder and the engine folder to Windows Security's
  exclusions (Virus & threat protection, Manage settings, Exclusions): Defender otherwise
  scans each of the level's files (one per actor, over 100,000 for a big city) as Unreal
  opens it.
- **In the editor** (not playing), a World Partition level loads nothing until asked ("no
  regions loaded"): Window > World Partition > World Partition Editor, drag a box over an
  area, right-click, Load Region From Selection. Keep the boxes small.
- **"Texture streaming pool memory has been exhausted"** in red over the play window: a
  stage 2 city's textures (AG6's library at 512 px/m) want more than the GPU's pool (70% of
  its memory by default), so the farthest stream at a lower resolution. It is the
  engine's on-screen debug text, drawn over the minimap: the developer menu's "Engine
  messages" row (or the console's `DisableAllScreenMessages`) hides it.
- **The engine** is found where the Epic Games Launcher put it (its
  `LauncherInstalled.dat`), the usual `C:\Program Files\Epic Games\UE_5.*` or
  `/Users/Shared/Epic Games/UE_5.*` too; `--engine` or `CITYGEN_UE_ROOT` names another.

### DLSS

NVIDIA's DLSS renders the city at a lower resolution and upscales it to the window with a
neural network (Super Resolution), and can add a generated frame between every two it renders
(Frame Generation, RTX 40 series and newer). It is NVIDIA's plugin under NVIDIA's license, so
it is not part of CyberGen: you download it yourself and the exporter puts it in your
project.

1. **Get the plugin:** NVIDIA's DLSS page for Unreal Engine (developer.nvidia.com/rtx/dlss,
   "Unreal Engine Plugin"), the build for UE 5.8 (tested: `DLSS4.5Plugin_v8.9.0`, 2026-10-16).
   Accept NVIDIA's license there.
2. **Put it anywhere outside the repository and the engine** and extract it, for example
   `C:\Users\you\CityGen\downloads\dlss\` (the zip's root holds `Plugins/`, `Documentation/`
   and NVIDIA's guides; the folder is about 4 GB).
3. **Import with it:**

   ```powershell
   .venv\Scripts\python -m citygen unreal out\delta_megacity "...\CityTest.uproject" --dlss C:\Users\you\CityGen\downloads\dlss
   ```

   or set `CITYGEN_DLSS` to that folder once. The importer copies the five plugins DLSS needs
   into the project's `Plugins/` (`DLSS`, `StreamlineCore`, `StreamlineDLSSG`,
   `StreamlineReflex`, `StreamlineNGXCommon`; not NIS, RTX Dynamic Vibrance, the Movie Render
   Queue support or the deprecated `Streamline`), again only when the download changes,
   enables them in the .uproject, sets their project settings (DLSS's on-screen debug messages
   and Frame Generation's debug overlay off; the engine's anti-aliasing TSR, which DLSS takes
   the place of when it is on) and builds them with the play features. Without `--dlss`
   nothing of this happens: a project keeps whatever plugins it has.
4. **In the game:** Tab, the developer menu's **Upscaler** row: `<` and `>` (or a click) step
   through Native (100%), TSR 67%, DLSS Quality (67%), DLSS Balanced (58%) and DLSS
   Performance (50%); the output stays at the window's size (the monitor's native resolution
   in a packaged game). Until you pick one the row says Default: the engine's own automatic
   screen percentage, as every import before. The DLSS modes appear only where the plugin is
   in the game and runs on the machine (an NVIDIA RTX GPU, a recent driver). The **Frame
   generation** row (On or Off) appears where the plugin is in the game; it says n/a where
   Frame Generation does not run (it needs an RTX 40 series or newer, DirectX 12 and Windows'
   hardware-accelerated GPU scheduling). The console's `CityGen.MenuRow upscaler=dlss_quality`
   (`native`, `tsr`, `dlss_balanced`, `dlss_performance`, `default`) and `CityGen.MenuRow
   framegen=1` do the same; `CityGen.Status` gives the `upscaler` (mode, screen percentage,
   whether DLSS and Frame Generation are there and supported, Frame Generation's shown frame
   rate and Reflex's latency).
5. **Packaging:** the plugins are the project's own, so a packaged game builds, cooks and
   stages them with it (their DLLs, `nvngx_dlss.dll` and Streamline's, under the package's
   `CityAG16/Plugins/`), and the game logs `NVIDIA NGX DLSS supported 1`.

The menu reaches DLSS without linking it: CityGenPlay sets the plugin's console variables
(`r.NGX.DLSS.Enable`, `r.ScreenPercentage`, `r.Streamline.DLSSG.Enable`) and calls its
Blueprint libraries (`UDLSSLibrary`, `UStreamlineLibraryDLSSG`, `UStreamlineLibraryReflex`) by
name, so the play features build and run the same in a project without it. The benchmark's
`night_plan_all_dlss_q`, `_dlss_b`, `_dlss_p` and their `_fg` passes (with `--bench-atmos`)
run the night as delivered with each (its frames also record Frame Generation's shown frame
rate and Reflex's latency where it is on); the numbers on Delta Megacity are in
`docs/progress/dlss_lamps_flicker/README.md`.

## Play features

Every import gives the level a minimap, a map you can teleport with, a free camera and a
developer menu with the time of day, unless `--no-play`:

| Key | What it does |
|---|---|
| (always) | the minimap, top left: the city around you, north up, your heading as an arrow, the city's name, the time of day (day or night without an atmos plan), the keys |
| M | the map, full screen: the whole city with district names; the wheel zooms about the cursor, the right button drags it, the left button teleports you there (a walking player onto the nearest walkway, held until the city has streamed in around it; a flying one at its height, at least 30 m over the walkway there); M or Esc closes it |
| . | the free camera: in the game (not the editor's eject), a spectator pawn with no collision, flown with W A S D, E or Space up, Q or C down, the mouse; the wheel sets its speed (2 to 500 m/s); `.` again goes back to the player, who waited where they were |
| Tab | the developer menu: the time of day (AT3, with an atmos plan: the hour, `<` and `>` step it an hour, a click on the row swaps day and night, and a slider under it, dragged, sets any hour to the quarter; without one a day or night switch), the free camera, the minimap, the engine's on-screen messages, the upscaler (Native, TSR 67%, and with NVIDIA's plugin DLSS Quality, Balanced and Performance; "DLSS" above) and Frame Generation where the plugin offers it, and with an atmos plan atmosgen's weather prototypes (fog, rain, wet streets) and its steam and smoke (cars_steam, off by default); click a row to change it; Tab or Esc closes it |

By night (`MPC_CityGen`'s `Night` 1) the windows' rooms light up (AG6's night interiors,
lit by each building's own night since AG15: its schedule at `MPC_CityGen`'s `Hour`, its
light's color temperature; see "From AG15"), neon, LED strips, logos and signs glow
brighter, and the sky, the sun and the moon, the sky light and the exposure follow the hour
(AT3, "From AT3" below: atmosgen's sky and time; the exposure held per hour, or the eye would
adapt until the night looked like the day), and the streets are lit:

- **by atmosgen** (AT1, "From AT1" below) when the city was imported with its atmos plan:
  the street and wall lights, the junctions' mast arms and corner poles, the highways, the
  alleys, the shopfronts, the signs, the decks, tunnels and stations, each as its plan says,
  the nearest 512 within 300 m live, 16 of them shadowed;
- under the lamps past atmosgen's live range (and under the nearest, without an atmos plan)
  a **light-pool decal** (`/Game/CityGen/Core/M_CgLightPool`: a deferred decal, a warm
  emissive disc fading from its middle, by `Night`, 7 m across a street light, 4 m a wall
  light, under 768 lamps), so the far streets read lit: atmosgen's far tier until AT7.

AG15's spot lights under the 192 nearest lamps and its sign washes (a point light before
each of the 32 nearest large signs) are gone since AT1 (decision 12.2 of atmosgen's scope:
the lamps, washes, moon and night exposure move to atmosgen); a city imported without an atmos
plan has the light pools alone by night (run `atmosgen plan` before `citygen unreal`).
With an atmos plan (AT3) day and night are the plan's day and night hours on atmosgen's
controller, which drives the sun, the moon, the sky and `MPC_CityGen`'s `Night` and `Hour`;
the play features' own night switch (the sun turned into a dim blue moon high in the sky, the
sky light dimmed, `NightHour` 21, the exposure held at `NightExposureEV100` -3) serves only a
level imported without one. The console variable `CityGen.PlayLamps` (1 by default) places
the pools from the view out, 2 only past `CityGen.PlayPoolsFromM` (atmosgen's controller sets
2 while its lights show), 0 none; the pools show while `Night` is over 0.02.

**How it is built.** The play features are game logic (input, a drawn overlay, possession,
teleporting), which Unreal's Python cannot write into a Blueprint's graph, so they are a
small C++ runtime plugin, `CityGenPlay` (`citygen/ue/CityGenPlay`), that `citygen unreal`
copies into the project (`Plugins/CityGenPlay`, enabled in the .uproject) and builds with
UnrealBuildTool for the editor before the import (`unreal_play.build_plugin`, about 20 s
the first time, skipped when its source is unchanged). It needs a C++ compiler UE 5.8
accepts: on Windows Visual Studio 2022 17.14 or later with its MSVC 14.44 (UE 5.8 bans
14.39 to 14.43 and 14.44 before build 35211), on a Mac Xcode. Where it cannot be built, the
city imports without the play features (the summary line says why): a plugin never built
is taken out of the project again, one built before stays as it was built (the level's
play actor keeps its class, so the import can delete it). The build passes `-NoHotReloadFromIDE`, so an editor open on
another project with Live Coding does not block it; the project being imported must be
closed, as for any import. A project named like one of the engine's modules cannot build it:
UnrealBuildTool compares module names without case, so a project `Proj` meets the
GeoReferencing plugin's `PROJ` ("Expecting to find a type ... named 'PROJ'"); the city then
imports without the play features.

- **The actor**: `CityGenPlay` (key `play`, always loaded, `cg.type=play`): the map texture
  (`Play/T_<City>_Map`, imported again only when its pixels change) and the world
  rectangle of its corners, the walkway points, the lamp heads and kinds, the sign wash
  points and colors, district label points, `MPC_CityGen`, `M_CgLightPool`; settings
  (minimap radius 250 m, free camera speed 30 m/s; AG15: `LampLights` 192 spot lights of
  `StreetLampCandela` 120 cd and `WallLampCandela` 32, `ShadowedLamps` 8,
  `LampRadiusM` 30, `LampDropCm` 45, cones `LampInnerConeDeg` 50 and `LampOuterConeDeg` 78,
  `LampPools` 768 decals of `PoolRadiusM` 7, `WashLights` 32 of `WashCandela` 120 and
  `WashRadiusM` 25, `NightHour` 21; night exposure -3 EV100, the moon at 3% of the sun,
  start at night, show the minimap) are its properties, editable on the actor in the level.
  `CityGen.Status` also gives `lamps_shadowed` and `light_pools`.
- **The data** (`citygen/unreal_play.py`, written beside the manifest, the manifest's `play`
  names them with their hash): `unreal/map.png`, the city from above drawn from the
  blockout plan (sea, land, water, parks, plazas, sidewalks, streets by class, highways in
  amber, bridges, the transit tubes, buildings in their district's hue, landmarks lighter;
  4,096 pixels on its long side; drawn again only when the plan changes) and
  `unreal/play.json` (the map's bounds and size; the walkway graph's lines sampled every
  5 m and thinned to one point per 3 m cell and level, stairs, lifts, skybridges, elevated
  and underpass walkways left out; each street and wall light's lamp head, its prototype's
  `prop_light` part placed by the instance's transform; AG15: a point 1.5 m in front of each
  of M20's large facade signs and its neon color by its id, from `gameplay.json`'s sign
  slots (`washes`, `wash_colors`; `version` 2), its height over the building's base on
  M13's terrain as the blockout lifts the signs (#90: it was over 0, metres under the sign on
  a hill); a point inside each district from
  `city_model.json`, else the gameplay layer's zones).
- **Console commands** (in the play window): `CityGen.Map [0|1]`, `CityGen.FreeCam
  [0|1]`, `CityGen.Menu [0|1]`, `CityGen.Night [0|1]` (each toggles without an argument),
  `CityGen.MenuRow ROW` (a click on a developer menu row, "A packaged game" below; AT3's
  `hour=H`, a number of hours or `day`, `dusk`, `night`, is the time slider),
  `CityGen.Teleport X Y` (citygen meters), `CityGen.Status` (the state as one JSON line).
  The actor's functions are callable from Python too (`set_night`, `set_map_open`,
  `set_free_cam`, `teleport_player_to_citygen`, `get_status`; AT3 `set_time_of_day`,
  `click_menu_row`).
- **The check** (`--check`): with the walking pawn, the overlay up, the map and the menu
  open and close, night lights lamps near the player, the free camera there and back to the
  same pawn, a teleport across the city that waits for streaming and lands on the ground;
  with `--shots` the minimap, the map, the menu and the night as the play window shows them
  (`unreal_play_*.png`, the editor's own `shot showui`).

**Plan for more** (each in the actor and the overlay, the data from the venv side):
markers on the map from the gameplay layer (points of interest, fast travel and taxi
points, transit stations, faction turfs as a toggle), a waypoint set by a click with its
route along the walkway or lane graph, weather states once stage 3 has them (the time-of-day
slider came with AT3), a speed and field-of-view slider for the free camera, a photo mode (UI hidden, a
high resolution shot), and showing the lane and walkway graphs over the city for stage 4.

## Contract for every stage

- **Keys.** Every entry is keyed by an M10 stable id (or, for joined pieces, the blockout's
  object name) and carries the hash of what it was made from.
- **Layering.** Contributions are applied in stage order: a later stage's entry replaces an
  earlier one's for the same key; a key it has no entry for keeps the earlier one, so a
  stage can land a piece at a time. An entry may list `replaces` (earlier keys it
  supersedes), for example assetgen's per-segment road meshes replacing M15's joined pieces.
- **Re-import by key and hash.** Unchanged keys are not touched; a regenerated district
  changes only its own actors; importing the same build twice writes no file.
- **Entry kinds.** Static mesh actors (from the stage's glTF packs, with pivot, material
  slots, collision, Nanite and LOD settings), instanced kinds (a mesh and its instances with
  ids), materials (a master and its parameters and textures), data assets, and level actors
  (lights, volumes, sky).

## What each stage adds

| Stage | Contribution |
|---|---|
| 1 citygen | the blockout, props and plants, graphs, player start, a default sun and sky (M15); terrain: the ground per tile, walls, bores, terrain viaducts and columns by id (M13); decks: the slab, deck streets and the buildings on them tagged with their level, the manifest's decks, levels in the graphs (M14); water and ground: swim volumes per water body and tile, water at its surface, beds, banks by kind and the ground cover by kind with a material each (M16) |
| 2 assetgen | buildings replacing their blockout boxes by id (own pivots, parts as instances, simple collision), textured master materials with per-actor parameters, street meshes replacing the joined pieces, prop and plant variants, signs, LODs for the pieces Nanite does not take, HLOD and Lumen settings (per milestone: `docs/assetgen_scope.md` section 14) |
| 3 atmosgen | lights (street and wall lights, shopfronts, signs as lit faces, floods), sky, time, weather, fog and post volumes, replacing M15's default sun and sky; rendered by its runtime plugin `CityGenAtmos` (AT0: the plugin's skeleton, its assets, the plan's contribution format; "atmosgen's runtime (AT0)" below) |
| 4 lifegen | people, traffic, transit, air and water on the graphs, spawners, place slots; moved by its runtime plugin `CityGenLife` (LG0: the plugin's skeleton, ZoneGraph lanes from the graphs, the spike's stand-ins and cars; "lifegen's runtime (LG0)" below; LG1: the people library, MetaHumans made by script into the project, near, mid and far tiers; "From LG1: people"; LG3: the city's crowd on every walkway round the view, doors, signals, groups, avoidance; "From LG3: crowds on the streets") |
| 5 storygen | story actors, triggers, sequences |

## assetgen's contribution (AG0)

assetgen writes its entries as `unreal_contribution.json` beside its glTF packs (AG0: the
spike's, `assetgen spike OUT`; from AG1: `BUILD/assets/`), layer 2 over stage 1's blockout:

```json
{"version": 1, "stage": "assetgen", "layer": 2,
 "masters": ["facade", "glass", "metal", "neon", "foliage"],
 "materials": {"glass": {"master": "glass", "color": [0.011, 0.017, 0.028],
                         "roughness": 0.08, "metallic": 0.0}, "...": {}},
 "entries": [{
   "key": "d03.lot.e512n88.bld", "kind": "building", "hash": "<brief hash, 16 hex>",
   "replaces": [], "glb": "tiles/<tile>.glb", "node": "<key>.shell", "asset": "<key, dots to _>",
   "pivot": [512.0, 88.0, 0.0], "yaw_deg": 0.0, "nanite": true, "triangles": 975476,
   "slots": ["concrete", "glass", "metal", "roof", "shopglass", "spandrel"],
   "collision": {"simple": [{"center": [0, 0, 7.5], "extent": [36, 30, 7.5], "yaw_deg": 0}]},
   "cpd": [0.82, 0.86, 0.9, 0.15, 6.0, 0.4, 0.55, 0.37],
   "parts": [{"kind": "part.window.frame", "node": "<key>.part.window.frame", "asset": "...",
              "count": 14720, "triangles": 120, "xforms": [[x, y, z, yaw_deg], "..."]}]}]}
```

- **Keys**: a building's key is its M10 id, which is also the name of its blockout object
  (`citygen/blockout.py`), so the entry replaces that actor; `replaces` lists other blockout
  keys it supersedes (AG7's per-segment street meshes over M15's joined pieces).
- **Pivot**: the building's own origin (scope section 6), not the world origin as the
  blockout's meshes; the actor sits at `pivot` (Unreal 100 x, -100 y, 100 z).
- **Materials**: one material instance per slot, parent by `master`; the masters read the
  vertex color as a multiplier (grime) and its alpha as a per-window id, and Custom Primitive
  Data `cpd` per actor: 0 to 2 tint, 3 wear, 4 dirt height (m), 5 neon, 6 lit-window ratio,
  7 seed.
- **Collision**: simple boxes per mass (`extent` is half the size, meters) in the mesh's
  frame; Nanite on, simple collision used as complex until AG3 adds the ground band.
- **Parts**: one static mesh per part kind and a hierarchical instanced component per
  building and kind (transforms relative to the pivot, yaw about z), carrying the same
  Custom Primitive Data.

The spike measured how Unreal takes this (`docs/progress/AG0/README.md`): Interchange reads
`KHR_mesh_quantization`, not `EXT_mesh_gpu_instancing` (parts come in as one prototype mesh,
so instances must come from the manifest, as above); simple collision boxes can be written
into a mesh's body setup from Python.

### From AG1: real buildings

`assetgen build BUILD` writes the contribution as one file per part of stage 2, beside the
packs it points at: `BUILD/assets/unreal_contribution.buildings.json` (AG1; AG7 adds
`unreal_contribution.streets.json`). Each key is in one file only. What changed from AG0's
format:

```json
{"version": 1, "stage": "assetgen", "part": "buildings", "layer": 2,
 "city": "Vesper Bay", "model_sha256": "...", "cpd_layout": {"0-2": "wall tint", "...": ""},
 "materials": {"brick": {"master": "facade", "color": [0.196, 0.067, 0.036],
                         "roughness": 0.9, "metallic": 0.0, "tint_cpd": 0}, "...": {}},
 "entries": [{
   "key": "d03.lot.e512n88.bld", "kind": "building", "hash": "<asset hash, 16 hex>",
   "replaces": [], "glb": "tiles/t+02+00.glb", "node": "<key>.shell", "asset": "<key, _>",
   "pivot": [512.34, 88.1, 0.0], "yaw_deg": 0.0,
   "nanite": true, "distance_field": false, "lumen_cards": false,
   "triangles": 12840, "slots": ["brick", "glass", "roof", "structure", "trim"],
   "collision": {"simple": [{"center": [0, 0, 7.5], "extent": [6, 9, 7.5], "yaw_deg": 45}],
                 "convex": [{"z": [0, 15], "ring": [[-6, -9], [6, -9], [6, 4], [0, 9]]}]},
   "cpd": [0.33, 0.12, 0.07, 0.8, 4.5, 0.3, 0.35, 0.4127, "... 23 floats"],
   "proxy": {"glb": "proxies/t+02+00.glb", "node": "<key>.proxy", "asset": "<key, _>_proxy",
             "triangles": 34},
   "parts": [], "tags": {"cg.type": "building.villa", "cg.district": "d03",
                         "cg.tile": "t+02+00"}}]}
```

- **Packs**: `tiles/<tile>.glb` holds every building of a 256 m tile (citygen's tile names,
  by the building's origin): a root node per building named by its key at its pivot, a
  child `<key>.shell` with the shell mesh (one primitive per material slot). The vertices
  are in the building's frame, so the static mesh asset is made from the child alone and the
  actor placed at `pivot`. `proxies/<tile>.glb` holds the far proxies the same way
  (`<key>.proxy`, its node at the pivot). On M13's terrain the pivot's z is the building's
  `base_m` (its ground floor over sea level), and the shell, proxy and collision reach down
  below it to the lowest ground under the footprint (a plinth); on flat ground z is 0.
- **Materials**: one material instance per slot for the whole city, its parent the slot's
  `master`, `color`, `roughness` and `metallic` as its parameters. A slot with `tint_cpd`
  takes its base color from the actor's Custom Primitive Data at that index (three floats,
  linear RGB): the building's wall, trim, glass, roof, spandrel or patch tint; one master
  serves every building. UV1 and vertex colors exist only on the glass slots (`glass`,
  `storefront`): UV1 0 to 1 over each pane, vertex alpha a per-window id for the interior
  mapping master.
- **Custom Primitive Data**: 23 floats per actor (`cpd_layout`): AG0's 0 to 7 (tint 0 to 2
  is now the wall tint, wear, dirt height, neon, lit-window ratio, seed), then the trim,
  glass, roof, spandrel and patch tints.
- **Collision**: `simple` boxes (a mass piece that is a rectangle) and `convex` prisms (any
  other convex piece of a mass footprint, its ring and z range), building frame, meters:
  `KBoxElem` and `KConvexElem` (the ring at both heights). Simple collision is used as
  complex until AG3 adds the ground band.
- **Proxy**: the building's far proxy, its masses as prisms (7 to 500 triangles), a Nanite
  fallback and HLOD input (AG9 sets up the HLOD layers); as a static mesh of its own.
- **Parts**: AG2's instanced parts (next section); empty in AG1.
- **Hash**: the asset hash (brief, generator version, material library); unchanged hash,
  unchanged packs, so a re-import may skip the key.

**What the exporter does with it** (done after M15 merged, in the exporter PR for AG1 and
AG7; `citygen/unreal.py` `stage2`, `citygen/ue/import_city.py`):
- **Layering**: every `BUILD/assets/unreal_contribution.*.json` is read in sorted file
  order as layer 2 over the blockout manifest (the manifest's `stage2`); a key in two files
  is refused, as is a file of another version or layer. `--blockout-only` (or no assets
  folder) gives exactly the blockout's manifest; imported over stage 2 it takes stage 2's
  actors out and leaves its meshes and materials in the project, unused, for the next
  import with stage 2 (Unreal takes about an hour to delete tens of thousands of meshes).
- **Replacing**: the blockout actor of every entry's key and of every key in its
  `replaces` is dropped (`stage2.replaced`); the rest stay. The new actors and their hashes
  are in `actor_hashes`, so `manifest_changes` is exactly what an import does (a building
  key is "updated" from its blockout box to its shell; a joined street object "deleted";
  a street piece "created").
- **Meshes**: the packs go through Interchange with the meshes kept in their nodes' frame
  (`bake_meshes` off) and their own flat normals (`recompute_normals` off), one static
  mesh per `<key>.shell` and `<key>.proxy` node under `Assets/Buildings/<tile>` and
  `Assets/BuildingsProxies/<tile>`, named as Interchange names the node (the
  contribution's `asset`, `<key>_shell`); each actor stands at `pivot` (Unreal
  100 x, -100 y, 100 z; yaw -yaw) with the blockout actor's category, district and level,
  the entry's type and tile, and `cg.stage=2`.
- **Masters**: `/Game/CityGen/Core/M_CgFacade`, `M_CgGlass` (interior mapping on UV1, a
  room per pane from the window id in the vertex alpha, lit rooms by Custom Primitive Data
  6 times `LitScale`; off by default, `Interior` 0, until AG6: in Unreal curtain wall panes
  that share corners come out with their window ids and UV1 blended per triangle, see
  `docs/progress/AG1/unreal/`), `M_CgMetal` and the street masters; one instance per part and slot
  (`Assets/Materials/MI_buildings_<slot>`). A material's `tint_cpd` (one of 0, 8, 11, 14,
  17, 20) is its `TintChannel`: the master reads a Custom Primitive Data color at each of
  those indices and the instance picks one; `tint_scale` and `tint_times_color` (the patch
  slots: 3.1 times the slot's own color) scale it.
- **Custom Primitive Data**: the 23 floats on every building actor's component, as its
  saved defaults (`SetDefaultCustomPrimitiveDataFloatArray`; `SetCustomPrimitiveDataFloat`,
  which AG0's spike used inside one editor run, sets only run-time values that the level
  does not save).
- **Collision**: the boxes and convex prisms as exact convex hulls in each shell's body
  setup, used as complex: Python cannot write `KConvexElem`'s vertices, so the importer
  extrudes each piece into a GeometryScript dynamic mesh and lets
  `SetStaticMeshCollisionFromMesh` make one hull per piece (boxes come out as boxes); the
  project gets the `GeometryScripting` plugin with the other two.
- **Nanite** on, distance fields and Lumen cards off for every shell.
- **Parts**: a `BP_CityGenInstances` actor (HISM) per entry and part kind, keyed
  `<key>.<kind>`, the transforms relative to the pivot, the entry's Custom Primitive Data
  on the component (AG1's lists are empty; AG7's container stacks use it).
- **Proxies**: imported as static meshes (Nanite off, no collision), not spawned: ready
  for HLOD (AG9).

### From AG2: facade parts

`assetgen build` (AG2) fills each building entry's `parts` with its instanced facade parts
and writes their meshes beside the shells, one pack per tile: `parts/<tile>.glb`, a root
node per part mesh at the origin, named by the hash of the part's type and parameters
(`part.window.casement.h29779f5c63`), so every building of the tile whose part has the same
parameters uses the same mesh. A part a building places fewer than 8 times is merged into
its shell instead and not listed (as is one that would fold a thin triangle when turned to
its facade and rounded to the millimeter).

```json
{"key": "d03.lot.e512n88.bld", "...": "...", "instances": 412,
 "parts": [{"kind": "part.window.casement.h29779f5c63", "type": "part.window.casement",
            "glb": "parts/t+02+00.glb", "node": "part.window.casement.h29779f5c63",
            "asset": "part_window_casement_h29779f5c63", "count": 96, "triangles": 80,
            "xforms": [[-6.12, 4.5, 3.35, 135.0], "..."], "building": "d03.lot.e512n88.bld"}]}
```

- **Kinds**: `kind` is the part's node name, unique within the entry (a building can have
  several window sizes of one type); `type` the semantic type for tags and stage 3 and 4
  (`part.window.<style>`, `part.cap.mullion`, `part.spandrel.panel`, `part.balcony.<style>`,
  `part.louver.panel`, `part.fin.vertical`, `part.fin.crown`, `part.shade.blade`,
  `part.shutter.open`, `part.grille.bars`, `part.panel.<board|infill|screen|eggcrate|addon>`,
  `part.member.<column|beam|diagonal>`, `part.pod.capsule`, `part.ac.window`,
  `part.dish.satellite`, `part.column.arcade`, `part.balconette.rail`,
  `part.canopy.podium`, `part.mast.<mast|spire>`).
- **Transforms**: `xforms` are `[x, y, z, yaw]` in the building frame (meters relative to
  the entry's `pivot`, yaw in degrees counterclockwise about z), as AG7's container parts:
  an HISM instance at `pivot + (x, y, z)` turned by yaw (Unreal: `(100 x, -100 y, 100 z)`,
  yaw `-yaw`). A part's own frame: x along its facade, y into the wall, z up.
- **Material and CPD**: the parts' slots are in the contribution's `materials` like the
  shells' (tints only from the six channels of `cpd_layout`); the HISM carries the
  building's 23 CPD floats, so a part takes its building's colors.
- **Building ids**: `building` names the entry each instance belongs to (one HISM per
  building and kind, keyed `<key>.<kind>`, its `Ids` the building's key).
- **Collision**: none needed from the parts (the building's simple collision covers its
  masses; AG3 adds the ground band); Nanite on, distance fields and Lumen cards off.
- **Re-import**: a part's mesh is named by its parameters' hash and its pack changes only
  when the tile's buildings change, so an unchanged building's HISMs change nothing.

### From AG3: street fronts, doors and decals

`assetgen build` (AG3) cuts every building's ground band (from its foot to its first floor
line, at most 7.5 m) out of the shell into a mesh of its own: shopfronts, doors, docks,
garage mouths, gates, steps, recesses, risers, fascias and the band's own windows. It is
a second node beside the shell in the tile's pack (`<id>.front`) and its own entry:

```json
{"key": "d03.lot.e512n88.bld.front", "kind": "building.front", "hash": "...",
 "glb": "tiles/t+02+00.glb", "node": "d03.lot.e512n88.bld.front",
 "asset": "d03_lot_e512n88_bld_front", "pivot": [512.4, 88.1, 0.0], "yaw_deg": 0.0,
 "nanite": true, "fallback_full": true, "collision": {"complex": true},
 "cpd": ["... 30 floats"], "ids": ["d03.lot.e512n88.bld"], "band_m": 4.2,
 "doors": [{"id": "d03.lot.e512n88.bld.door.e0", "kind": "main", "entrance": 0,
            "unit": null, "use": null, "walkway_id": "wk.e510n80",
            "walkway_from": "model", "position": [3.1, -7.9, 0.0],
            "normal": [0.0, -1.0], "width_m": 2.0, "height_m": 2.4, "flush": false}],
 "tags": {"cg.type": "building.front", "cg.district": "d03", "cg.tile": "t+02+00"}}
```

- **Where**: at its building's pivot, with its building's CPD and materials (its era's walls:
  `materials` as the building's); its building's id in `ids`, so the actor's `cg.id` is the
  building's; `level` 1 for a building on an M14 deck.
- **A front its building's whole height** (a one-floor gate house): the shell has no
  triangles, so its node carries no mesh (glTF has no mesh without primitives) and the
  building's entry has `node` and `asset` null (no shell mesh, no shell actor; its proxy
  and parts as usual); the front's `replaces` names the building's key, so the front's
  actor takes the place of the building's blockout actor.
- **Collision**: complex (its own triangles: doorways, steps, posts and recesses collide as
  drawn). The building's convex hulls now start at the band's top (`band_m`); a mass the
  band takes whole (a one-floor shop) has none. `fallback_full`: the Nanite fallback keeps
  every triangle (`PercentTriangles` 1.0, relative error 0), since complex collision is
  built from it.
- **Doors** (for stage 4): one per entrance and per ground-floor unit, in the building
  frame: kind (`main`, `service`, `dock`, `rollup`, `garage`, `gate`, `shop`), the model's
  entrance or unit index and use, the walkway it opens to (`walkway_id`: the model's when
  the access check reaches it, else the ground walkway in front of the door; `walkway_from`
  `model`, `front` or `none`),
  the threshold's middle and outward normal, size, and `flush` (a door drawn on the wall,
  where no recess fits). A door the model put on a wall a neighbor stands against is moved
  to the nearest open facade of its building.
- **Decals** (with AG6's library): a tile's decals on the street bands (grime at the foot,
  leaks under windows, rust beside metal doors, graffiti, posters, cracks, moss) are one
  mesh of quads in the tile's pack (`decals.<tile>`, 1 cm off the walls, at the tile's
  middle), its own entry keyed `decals.<tile>`: Nanite off, `collision: {"none": true}`,
  a slot per atlas cell (`decal.<cell>`), each a `decal` material with its `Cell` index
  (`Cols` and `Rows` 4) over the decal atlas: mesh decals.

**What the exporter does with them** (`citygen/unreal.py`, `citygen/ue/import_city.py`):
- the front's actor like any entry's, its mesh's record with `fallback_full` (in the mesh's
  hash), which the importer applies to the Nanite settings;
- a `cg.door=<door id>@<walkway id>` tag per door on the front's actor;
- the manifest's flat graphs gain `doors` (`doors_of`): one element per door, kind (the
  door's, `shop.<use>` for a unit's), ref its walkway, width, its world point (pivot plus
  position), attrs (building, entrance or unit, outward yaw, height, flush, walkway source),
  level; a `BP_CityGenGraph` data asset like the others;
- the decal meshes as non-Nanite static mesh actors without collision, their slots the
  decal instances (`M_CgDecal`, deferred decal domain: a mesh decal over the wall behind).

### From AG4: roofs, roof equipment and skybridges

`assetgen build` (AG4) adds roof forms, finishes, copings, green roofs, facade details,
portals and sky stations to the shells (no new entry: they are in each building's shell,
front and parts), and three things the exporter takes:

- **Roof equipment** (AC units, water tanks, antennas, helipads and AV pads, access huts,
  dunnage, roof vents, skylights; `roofparts.ROOF`, always instanced) leaves the
  buildings' `parts` for one entry per tile in `unreal_contribution.buildings.json`:

  ```json
  {"key": "roofs.t+02+00", "kind": "roof_equipment", "hash": "...", "replaces": [],
   "pivot": [0.0, 0.0, 0.0], "yaw_deg": 0.0, "nanite": true, "triangles": 0,
   "slots": [], "collision": {"none": true}, "cpd": [], "instances": 412,
   "parts": [{"kind": "part.ac_unit.box.h957c3355d6", "type": "part.ac_unit.box",
              "glb": "parts/t+02+00.glb", "node": "part.ac_unit.box.h957c3355d6",
              "asset": "part_ac_unit_box_h957c3355d6", "count": 96, "triangles": 220,
              "collision": {"none": true}, "xforms": [[512.4, 88.1, 31.2, 90.0]],
              "ids": ["d03.lot.e512n88.bld"]}],
   "tags": {"cg.type": "roof_equipment", "cg.district": "", "cg.tile": "t+02+00"}}
  ```

  Transforms in the city frame (x, y, z in meters, yaw in degrees), one building id per
  transform; the meshes are nodes of the tile's part pack. No collision, as AG2's
  building parts (a body per instance; the building's own collision covers its roof).
  Their slots take no tint (no building's Custom Primitive Data reaches a tile's
  instances) and none is era-varied (no `<slot>@<era>`, so no `materials` map). Merged roof parts
  (penthouses, billboard frames) stay in their building's shell.
- **Green roofs**: a building entry's `replaces` lists the blockout's joined green-roof
  objects (`d03.green_roof.<tile>`) whose every green area is a green roof its shells
  built (each object given to the smallest building id among them); an object that also
  draws a lawn, or a green roof too small to build, stays.
- **Skybridges** (and M3p's podium decks, open-deck skybridges): a part of their own,
  `unreal_contribution.connections.json`, packs `connections/<tile>.glb` (a node per
  skybridge at its middle, turned to its line), an entry per skybridge keyed by its id, so
  it replaces the blockout's skybridge object of that name:

  ```json
  {"key": "d03.sb.e183n553", "kind": "skybridge", "hash": "...", "replaces": [],
   "glb": "connections/t+00+02.glb", "node": "d03.sb.e183n553",
   "asset": "d03_sb_e183n553", "pivot": [183.1, 553.4, 0.0], "yaw_deg": 92.6,
   "nanite": true, "collision": {"complex": true}, "cpd": [], "ids": ["d03.sb.e183n553"],
   "links": ["building:d03.lot.e164n586.bld", "building:d03.lot.e180n524.bld",
             "walkway:wk.e183n553"],
   "tags": {"cg.type": "skybridge.enclosed", "cg.district": "", "cg.tile": "t+00+02"}}
  ```

  Complex collision (its floor is walked), untinted materials (`bridge_*`, planters,
  lamps) on the building table of AG6's catalog, `links`: the two buildings it joins and
  its walkways, for stage 4.

**What the exporter does with them** (`citygen/unreal.py`, `citygen/ue/import_city.py`):
- the roof entries as any parts-only entry: an instanced actor per mesh (`roofs.<tile>.
  <kind>`), its ids per instance, `NoCollision` from the parts' own `collision`
  (`test_stage2_takes_assetgen_roofs_and_skybridges`);
- a stage 2 entry's `links` reach its actor (in its hash) and the importer tags each one
  `cg.link=<link>` (`test_stage2_skybridge_links`);
- the connections part like any other: its folder `Assets/Connections/<tile>/`, its
  materials `connections.<slot>`.

### From AG5: heroes, types and slopes

`assetgen build` (AG5) adds the type generators, the landmark heroes, buildings on M13's
slopes and complex families to the shells (no new entry, no new part). Three things reach
the exporter:

- **Heroes** (every landmark and M3's megasite wheel): the building entry carries
  `hero` (`kind`: megatower, spire, arcology, ferris_wheel; `accent`) and a `materials`
  map of its own. Every slot of a textured opaque master (`facade`, `metal`, `concrete`)
  takes the material `<slot or era material>#<id>`, the slot's record with the hero's U2
  mask: texture `city.hero.<id>` (`textures/hero/<id>.png`, 512 px, kind `mask`, not sRGB:
  R grime, G leaks, B wear) as `HeroMask`, and `HeroMaskOn` 1. The hero's shell and front
  carry TEXCOORD_1 on every non-glass slot in the hero UV (u the UV0's u over its longest
  perimeter, v the height over the building's), where the mask is baked. Its light slots
  (`hero_light`, `halo_light`) take its accent colour (`<slot>#<id>` again, with or without
  the library):

  ```json
  {"key": "d01.lm.e152n1064.bld", "kind": "building", "hero": {"kind": "megatower",
   "accent": "#39ff8a"}, "materials": {"wall": "wall@corporate_glass#d01.lm.e152n1064.bld",
   "hero_light": "hero_light#d01.lm.e152n1064.bld"}, "...": "..."}
  ```
- **Plinths**: a building on M13's slopes carries `plinth_m`, how far its stepped plinth
  reaches under its pivot (its base, `floor_grid.base_m`) to meet the ground; the plinth is
  in the shell and the street front, stepped to the terrain along every wall (retaining
  skirts where the hill stands against it).
- **Collision**: a mass a skybridge lands on is cut into storeys at each landing door's
  floor and head, and in the door's storey its hull has a notch the door's width and 2.5 m
  deep, so a walk across the bridge steps through the door (`collision.VESTIBULE_MM`).

**What the exporter does with them** (`citygen/unreal.py`, `citygen/ue/import_city.py`):
- an entry's `hero` and `plinth_m` reach its actor (in its hash), tagged `cg.hero=<kind>`
  and `cg.plinth=<m>`; `stage2.counts.heroes`;
- the hero's materials and mask texture as any other (the mask among the city's textures,
  `Assets/Textures`); the textured masters (`facade`, `metal`, `concrete`, `foliage`,
  `road`) gain `HeroMask` (sampled on UV1) and `HeroMaskOn` (default 0) after their surface
  (`HERO_CODE`: grime darkens, leaks stain, wear lightens); `STAGE2_VERSION` 6 rebuilds
  them. Tested without Unreal by `test_stage2_heroes_and_plinths`.

### From AG10: layered districts

`assetgen build` (AG10) gives M14's decks their assets. On a city without decks no entry,
key or byte of any contribution changes. On a city with decks:

- **Deck pieces** in `unreal_contribution.streets.json` (kinds `street.deck.slab`,
  `street.deck.column`, `street.deck.stair`, `street.deck.elevator`; meshes in the street
  packs, complex collision, Nanite; the slabs, stairs and elevators with a full fallback,
  `fallback_full`, since the AG10 Unreal check):
  - **Slabs**: one entry per deck and tile keyed by the blockout's own slab object
    (`<deck>.slab.<tile>`, its `replaces` that key). So the slab actor keeps its key and
    the manifest's `decks` still name it.
  - **Columns**: one entry per column by its id, replacing the joined
    `<district>.deck_column.<tile>`.
  - **Stairs and elevators**: one entry each by id, replacing the blockout object of that
    name.
  - **The rest of the deck**: the deck's streets, junctions and sidewalks lie on the slab
    (no viaduct girder or parapet under them) and replace the joined `deck_road`,
    `deck_junction` and `deck_sidewalk` objects as before. A ramp's entry (`<segment>`)
    replaces `<segment>.ramp`, now a solid ramp with a walkway on each side.
- **Levels**: an entry takes the level of the blockout actor it takes the place of (as
  every stage 2 entry does), so the slabs, the deck's streets and ramps keep `cg.level=1`
  and the columns, stairs and elevators stand on the ground. Buildings on a deck carry
  `level` 1 in their entries (AG3).
- **Graphs**: `graphs.walkways` adds the walkways beside each ramp, put on the ramp's
  walkway decks (z over the ground, as the model's).
- **Buildings**: no new field. The undercity buildings' tops meet the soffit, and the
  buildings on a deck stand on its top (the shells, `asset_decks`); their entries are as
  before.

**What the exporter does with them**: no code change. `stage2` drops every deck object a
deck entry names, and each deck actor's level comes from the replaced object's category
(`DECK_LEVEL`). Tested without Unreal by `test_stage2_takes_assetgen_decks`: the small city
with a deck, its street stage over its blockout, every deck object replaced, the slab
actors on level 1 and the manifest's `decks` naming them, the columns, stairs and
elevators on the ground, the ramp walkways on their ramp.

### From AG14: fit and finish

AG14 (`assetgen build`, then `assetgen fit`) changes what the packs hold, not how they are
imported: every entry keeps its key, kind, `replaces` and level, and no new entry, part or
master is added.

- **Normals**: the shells carry the curve's own normal along M21's curved walls (radial in
  plan on every face of a chord of an arc, `meshbuf.Buf.arc`). The importer already keeps
  the packs' normals on both paths (stage 2's packs are imported with `bake=False`, which
  sets `recompute_normals` off: the fast pack import and `CITYGEN_UE_FAST=0`'s one at a
  time), so the curve shades smooth in Unreal as in Blender; the test
  `test_stage2_packs_keep_their_normals` holds both call sites to it.
- **Street pieces drawn anew under the same keys**: transit columns and pylons (M19's
  frame legs, piers on footings down to the bed, sky tube masts with crossheads, legs, ties
  and stays), cap beams (haunched, or tapered cantilever arms), road columns in the water
  on footings, junctions that meet their legs at their own heights, raised roads on M18's
  embankments (no girder through the fill), and footbridges whose edge beam stands outside
  the road's deck. A bridge whose road segments carry it no longer draws a deck of its own
  (it was drawn twice); its entry keeps its key and replaces what it did.
- **Buildings**: roof equipment on the roof the shell built (on a form, on dunnage, moved
  onto the roof where its point fell off a crown's tier); nothing that leaves a wall hangs
  over a lane under 4.6 m (`parts.ROAD_CLEAR`). Entries as before.
- **`fit_report.json`** (`asset_grounded`, `asset_clash`) beside the packs is for the
  generator only; the exporter does not read it.

**What the exporter does with them**: no code change; the packs' hashes move, so an import
over an earlier one updates the actors and meshes whose entries changed.

### From AG17: road surfaces from the pavement map

AG17 draws AG7's road, junction and sidewalk pieces from M22's pavement map (each face on
its stored vertices at their stored heights, a curb's wall between faces at two heights, a
raised junction on its own slab, barriers ending on the roads' port lines). It changes what
the street packs hold, not how they are imported:

- **Keys and kinds as before**: one entry per road segment (`street.road`), junction
  (`street.junction`), sidewalk (`street.sidewalk`) and crosswalk (`street.crosswalk`), keyed
  by the same citygen id, with the same `replaces` (the blockout objects they stand for) and
  level. A road or sidewalk with no faces of the map (a cluster's inner road, wholly inside
  its junction) has no mesh and is declared covered, as a road inside its junctions was.
- **Slots**: no new slot or master. The faces use the street slots they used (asphalt by
  class, the district's paving and curb stone, a median's lawn or concrete, the deck's
  concrete for a raised road's fascia and girder and a raised junction's slab).
- **Seams**: two pieces that meet share their edge's vertices exactly, so in Unreal they
  meet within float32 rounding (under 0.1 mm at tile scale) with no step; the import keeps
  the packs' normals as before (`test_stage2_packs_keep_their_normals`).

**What the exporter does with them**: no code change; the street packs' hashes move, so an
import over an earlier one updates the street actors and meshes in place.

### From AG15: cyberpunk facades and night

- **New parts and slots**, through AG2's instancing as before (instanced kinds, or merged
  into the shell under 8 placements): LED strips (`part.led.v`, `part.led.h`: mullions,
  convex corners, crown bands), honeycomb panels (`part.hex.honeycomb`), folded glass bays
  (`part.fold.glass`), mesh screens (`part.mesh.screen`), media screens (`part.media.screen`),
  fritted glass (`part.frit.glass`), logos (`part.logo.<ring|bars|chevron>`). Slots
  `led_<accent>` (six accents) and `screen_media_a` to `_d` are the `neon` master (emissive,
  stronger by `Night`), `fold_glass` the glass master, `hex`, `mesh`, `media_frame`,
  `logo_back` metal and `frit` facade (AG6's catalog).
- **Custom Primitive Data 30 to 35** of every building actor (after AG6's 23 to 29; Unreal's
  36 floats are all in use): the night's light color (linear RGB, a color temperature),
  its schedule (0 default, 1 office, 2 home, 3 hotel, 4 shop, 5 industrial, 6 vacant), how
  far its rooms' color temperatures spread, an office's band of floors. AG1's 6 (the lit
  share) is the evening's share.
- **`M_CgGlass`** (`STAGE2_VERSION` 8, rebuilt in place): the room's lit state from the
  schedule's share in `MPC_CityGen`'s new **`Hour`** (0 to 24; 21 by default; the hour
  bands of `model.HOUR_BANDS`: night, morning, day, evening, late) times the lit share, an
  office's whole band of floors on or off, shops brighter on their low floors, a vacant tower
  a few security lights; a lit room's color the building's light pulled warm or cool by a
  hash times its spread (`CgRoom` returns the blind and that draw in its w); `NightGain`
  (1) scales the rooms against the night exposure. The Blender previews draw the same
  (`ag6_materials._night_rooms`).
- **Play features** (the plugin's source changed, so `citygen unreal` builds it again):
  spot lights under the lamps, light-pool decals and sign washes ("Play features" above);
  `unreal/play.json` version 2 with `washes` and `wash_colors`; the importer sets the
  actor's `LightPoolMaterial` (`M_CgLightPool`, made once, `cg.pool` 1), `NightHour`,
  `WashPoints` and `WashColors` (a plugin built before AG15 has none of them: the city
  imports with its lamps as they were).
- **Tuning**: the lamps' candelas, the pools' strength (`PoolStrength` on the material) and
  `NightGain` were first values set against the night's fixed exposure (-3 EV100) without
  Unreal. The second run-through (`docs/progress/run_through_2/`) found the lamps, pools
  and washes drew nothing at all: `ACityGenPlay` is an `AInfo`, hidden in the game, and a
  hidden actor's components do not render; the actor now sets `SetHidden(false)`. Lit, the
  first values blew the streets out under that exposure, so they are a quarter: 1,500 cd
  for a street light, 400 for a wall light, `WashCandela` 600, `PoolStrength` 1.0
  (`LIGHT_POOL_VERSION` 2). `NightGain` stays 1. Seen in Unreal (2026-11-09), those still
  left near-white pools on the roads and clipped every sign to white, its text unreadable,
  so the lamps are 0.08 of those (120 cd, 32 for a wall light, chosen by Swagnik from night
  views at several strengths), `WashCandela` 120, `PoolStrength` 0.08 (`LIGHT_POOL_VERSION`
  4), and what glows is set for the exposure in
  `citygen/unreal.py`: the blockout's `EMISSIVE` and stage 2's `EMISSIVE2` (neon 1, the
  plain emissive 2, holo-ads 0.6) and, scaling assetgen's own strengths so its bytes stay,
  `SIGN_GLOW` (0.125: a sign page's `SignStrength` 4 to 0.5, an ad page's 2 to 0.25) and
  `HOLO_GLOW` (0.2: a holo-ad's `Emissive` 3 to 0.6). `CITYGEN_UE_LAMP_DEBUG=1` with
  `--check --shots` and `night_*` views logs the lamps near each view and shoots it again
  at the scales in `CITYGEN_UE_LAMP_SCALES` (comma separated), skipping the walk's checks.

### From AG16: performance

**The benchmark** (`citygen unreal BUILD UPROJECT --bench`, or `--bench-only` on a city
imported before; `citygen/bench.py`, the driver `UCityGenBench` in the play plugin):

- **Route** (`bench.route`, from the build alone, so before and after a change it is the
  same route): a 150 m sidewalk walk at 5 m/s in each of the three districts with the most
  stage 2 actors (from the walkway point nearest the actor nearest the district's middle,
  sidewalks first, never up an elevator or stairs), a 1.2 km drive at 25 m/s along the lanes
  4 m over the road from the lane nearest the city's middle (on into the lane that turns
  least), a flight at 150 m and 50 m/s across the diagonal of the stage 2 buildings' middle
  90% (4 km at most, looking 15 degrees down), and a teleport back to the first walk's
  start, held 6 s once streamed in. Each path starts with a teleport onto it and a wait
  until the World Partition cells within 150 m are activated (a load), then 1.5 s.
- **Passes**: by day and by night (the play actor's `SetNight`), at the native 1440p and at
  a 67% screen percentage with TSR (`r.ScreenPercentage` 100 or 67, `r.AntiAliasingMethod`
  4, the default screen percentage mode manual), in that order; before them two warm-up
  passes (the flight by day, then by night: the first use of most of the city's materials
  and lights, recorded and left out). `--bench-passes` picks passes by name.
- **The game**: `UnrealEditor PROJECT MAP -game -windowed -ResX -ResY -CityGenBench=<job>
  -csvGpuStats ...` (a standalone game process on the uncooked project, not play-in-editor),
  switched to windowed fullscreen at 2560 x 1440 (`r.SetRes 2560x1440wf`: a 1440p window
  with its borders would not fit a 1440p screen), `r.VSync 0`, `t.MaxFPS 0`. The pawn the
  level's game mode gives is moved by the route (its collision and movement off), the view
  turning smoothly toward the path 1.2 s ahead.
- **What it records**, every frame (`frames.csv`): the frame time, the game, render and RHI
  threads' times and the GPU's (`GGameThreadTime`, `GRenderThreadTime`, `GRHIThreadTime`,
  `RHIGetGPUFrameCycles`), draw calls and primitives (`GNumDrawCallsRHI`), whether the cells
  within 100 m of the player are activated (every 5th frame) and World Partition's
  streaming performance, VRAM in use (`RHIGetMemoryStats`, every 15th frame) and RAM
  (the process's physical use); beside it the engine's CSV profile (`csvGpuStats`: the
  GPU's passes; `NaniteStreaming/RootAllocationMB`, the Nanite root pages in use), its
  segments marked by events (`cg:<pass>:<segment>`), and `bench_events.json` (passes,
  segments, loads, the viewport, the adapter, the scalability levels, the Nanite pools).
- **Results** (`bench.summarize`, `combine`): per pass the moving frames of the walks, the
  drive and the flight, the teleport's, and all moving frames together: frame time p50,
  p95, p99 and max, the threads' p95, the thread that sets the frame at its p95, draw
  calls, hitches over 50 and 100 ms, the share of frames not streamed around the player,
  VRAM and RAM at most, root pages at most, the GPU's costliest passes, and the loads'
  seconds; over `--bench-runs` runs (3 by default) the median of each figure and the
  spread of p50 and p95 (min to max). Written as `bench.json`, `bench.md` (the table and the
  targets met or missed) and the last run's frame-time graph per pass along the route
  (`frame_times_<pass>.png`) in `docs/progress/AG16/bench/<city>/<label>` (`--bench-label`,
  default `bench`), with the last run's screenshot of each segment's start in each pass
  once loaded (`shots/<pass>_<segment>.jpg`, 1600 px wide: the same views before and after
  a change); the raw files of each run in `BUILD/unreal/bench/<label>/run<k>`. The first
  run right after an import is starved of CPU throughout: its render, game and RHI threads
  about twice as slow at the same GPU time, with half the frames, as the uncooked game
  builds the meshes' derived data on the CPU's cores while it plays (Vesper Bay's and
  Delta's: about five times the waits for static meshes of the later runs). What warms up
  between runs is the derived data cache, the pipeline state cache and the OS file cache;
  a player's first launch after an import sees it too, a cooked build carries the derived
  data. The median of three leaves such a run out, and the table names it (below). With
  each shot the game log gets the play actor's lamps nearest the view (lamp,
  distance, light, candela, shadows: `ACityGenPlay::GetLampReport`), for a night view's
  light.
- **Hygiene**: before each run it waits while another Unreal editor, Blender, a citygen
  build or sweep, assetgen or pytest runs (`bench.busy`, Windows), so the numbers are the
  city's alone; the play plugin is built first if its source changed. The game is kept
  DPI-aware (`bAllowHighDPIInGameMode`, `bAllowHighDpiWhenUnattended`: on a 1440p screen
  at 125% scaling a DPI-unaware game gets a 2048 x 1152 window), and a run that rendered at
  another size says so (`resolution_mismatch`). While a run plays, the CPU every other
  process takes is sampled every 30 s (`SAMPLE_S`; the game's own shader compilers and the
  driver left out) into `others.json` beside the run, its mean, most and busiest in the
  run's summary; and a run whose game or render thread median is 1.5 times the fastest
  run's while its GPU median stays within 15% (`bench.starved`: a first run after an
  import, or other work on the PC) is named under the table with the cores other processes
  took meanwhile. Since AT1 the game is opted out of Windows' power throttling and run
  above normal priority (`bench.unthrottle`): on the PC's hybrid CPU a game window that lost
  the foreground to the desktop was moved to the efficiency cores, its game and render
  threads twice as slow for minutes at the same GPU time (AT1's first after runs); each
  sample also says whether the game had the foreground (`in_front`, the summary's `front`).

**What the benchmark found on Delta Megacity** (`docs/progress/AG16/`): bound by the game
thread, not the GPU. Every frame spent its async loading time, physics waited on bodies
made and dropped as cells streamed, and the render thread waited on the visibility of the
primitives loaded: with a 1,500 m loading range most of the city's 73,772 actors were
loaded at once (43,000 to 67,000), each its own package to load in an uncooked game (what
play-in-editor and `-game` run). So the fixes cut what the level holds and streams:

- **Meshes shared across tiles** (`unreal.share_meshes`): an AG2 part or AG8 sign node of
  one name in several tiles' packs is the same content (named by its parameters' hash or its
  inputs' digest), imported once from the first pack by folder; the other packs leave it out
  (the pack step skips what a pack's plan does not name) and their actors point at it.
  Delta: 9,244 of 58,882 meshes, 53,911 distinct Nanite meshes to 44,667.
- **Records as components** (`unreal.group_actors`, the manifest's `groups` and each
  record's `holder`; `CITYGEN_UE_GROUP=0` keeps an actor per record): an entry's instanced
  parts are components of its own actor (else of a group actor at the entry's pivot, class
  `BP_CityGenGroup`), a building's street front (AG3) a component of the building's actor
  (its doors tagged on the building), and a tile's signs, street pieces, water pieces and
  ground cover (`tile_group`) components of one group actor per kind and 64 m cell of the
  tile (`group.<kind>.<tile>.c<i><j>`: the engine takes a streamed-out actor's components
  away in one step, so a group stays small). Each component keeps its mesh, transform,
  Custom Primitive Data, materials and collision, and carries its record's tags
  (`cg.member`, `cg.key=`, `cg.type=`, `cg.category=`, `cg.kind=` for a part, `cg.id=` per
  citygen id, `cg.door=`); stage 4 finds a sign, a street piece or a part by its component's
  `cg.key`. A holder's hash covers its members', so an import over another updates it when
  any changes. Instanced parts of a Nanite mesh are instanced static mesh components (Nanite
  culls them per instance), the rest hierarchical ones. `BP_CityGenGroup`'s root is static
  in the Blueprint itself (`blueprint(..., static_root=True)`, `CORE_VERSION` 3): set on the
  placed actor alone it is still movable while the level loads and its static members fail
  to attach, each failure a log line (160,000 in a game of Delta, 72 ms of `AddToWorld` in
  its slow frames; the Blueprint's recompile saves its placed actors again).
- **The instanced HLODs keep each building's look** (`per_instance`, `STAGE2_VERSION` 10):
  the HLOD builder moves each source's Custom Primitive Data into its instance's custom
  data (`FISMComponentBatcher`), and the masters read only Custom Primitive Data, so past
  the loading range every tint, night schedule and seed was lost (a dark, untinted far
  city, plain beyond 768 m, as it was beyond 1,500 m). Each read is now a per-instance
  custom data node whose default is the Custom Primitive Data parameter: an actor reads its
  own as before, an HLOD instance the data it carries.
- **No collision on props no one touches** (`unreal.NO_COLLISION`): awnings, facade AC
  units, wall lights and litter (Delta: 39,500 of its 71,000 prop instance bodies).
- **Underwater volumes switched by distance** (the play actor, `UpdateUnderwater`): the
  engine weighs every enabled post-process volume against the view each frame by its
  brush's distance, a physics query per volume, and AG12's 660 underwater volumes of Delta
  took 1.3 to 1.5 ms of the game thread every frame. Every 0.25 s the play actor enables
  only the volumes (`cg.type=underwater`) within their blend radius and 1 m of the view;
  the engine skips a disabled one at once. Without the play plugin they all stay enabled,
  as before.
- **The Nanite pool from the city** (`nanite_pool_mb`, above).
- **The import's memory** (#84): stage 2's packs imported, finished and saved 150 at a time
  (`CITYGEN_UE_PACK_CHUNK`, 0 for all at once), and the meshes let go of between chunks
  (and every fourth actor offload): the importer holds asset paths (`Meshes`) and loads a
  mesh when an actor asks for it. Delta's first import had held every one of its 58,501
  meshes to the end, 39 GB committed in the editor. An offload takes the actors it saves
  and unloads by their own guids (`actor_guids`), no longer by label: an actor whose class
  changes (AG8's cables and scaffolding over M15's instanced prototypes) is destroyed and
  made again under its key's label, and with the collections between offloads the
  destroyed one, taken by its label, came back from disk (the small city's stage 2 import
  test: 30 actors twice). Such class changes are now made first: right after the level
  loads, every actor whose key gets another class is destroyed and the level saved
  (`Importer.clear_moved`); destroyed later, among new actors under the same labels,
  offloads and collections, some kept their packages on disk all the same and came back
  with the next import. An actor that holds no records any more (an import back to the
  blockout, or one without groups over one with them) has its member components taken off
  (`Importer.drop_members`), and the import digest lists each actor's members. An import
  over an earlier level still loads all its actors first (to compare hashes and delete the
  old ones): Delta's import of the fixes over the "before" level peaked near 37 GB
  committed.
- **Streaming** (`import_city.MAIN_CELL_M`, `VIEW_M`): World Partition's main cells 128 m
  (256 m before), loaded 768 m around the player (1,500 m before). Each main cell has its
  HLOD actor, and when the cell goes its HLOD actor's components take their render state in
  one frame: a dense 256 m cell's 1,400 made 50 to 64 ms frames. Past the range the
  instanced HLODs draw the same meshes and materials, each building's Custom Primitive Data
  with it (above), so the city looks the same (the benchmark's shots, before and after side
  by side).
- **Texture streaming off** (`unreal.PROJECT_SETTINGS`, `r.TextureStreaming=0` in the
  project's `[SystemSettings]`, written with the Nanite pool by every import): the render
  asset streaming manager keeps a manager per streamed level and processes every component a
  level adds; with the cells and their HLODs coming and going it made 36 to 48 ms frames at
  256 m cells and 1 to 2.8 s frames at 128 m. A city's textures (AG6's library sets and its
  sign pages, a few hundred) fit whole: Delta's VRAM stayed at 7 GB.
- **The game at the monitor's resolution** (AT1, `unreal.set_project_ini`:
  `bAllowHighDPIInGameMode=True` in the project's `[/Script/Engine.UserInterfaceSettings]`,
  written by every import): the game is DPI-aware, so a 2560 x 1440 monitor scaled 125% gives
  it a 2560 x 1440 window (DPI-unaware it got 2048 x 1152, stretched by Windows, and the neon
  strips shimmered). Unreal's automatic screen percentage is left as it is; the benchmark keeps
  its own overrides. A packaged game with no saved settings still picked its window before
  it was DPI-aware: the play features now put it at the monitor's native resolution ("A
  packaged game" below).
- **Tried and left out**: UE 5.8's experimental switches for physics bodies made off the
  game thread (`p.Chaos.EnableAsyncInitBody`) and incremental garbage collection
  (`gc.AllowIncrementalReachability`, `gc.AllowIncrementalGather`), no forced collection
  after a level streams out (`s.ForceGCAfterLevelStreamedOut=0`) and actor clustering for
  garbage collection: none helped, and the garbage collection ones made it far worse
  (collections of 0.7 to 2.9 s).
- **What is left** (`stat dumphitches` on a day pass): garbage collection, the engine's
  reachability analysis over every object of an uncooked game, 70 to 350 ms about every 40
  s while the city streams (a cooked game marks far fewer objects); at most one moving
  frame over 100 ms in a pass.

### HLOD streaming (fix_hlod_streaming)

**What made the walk's slow frames** (an Unreal Insights trace of the lean route's walk and
drive on Delta; `docs/progress/fix_hlod_streaming/`): World Partition hides an HLOD actor
while the main cell it stands for is shown and shows it again when the cell goes (the HLOD
runtime subsystem's `OnCellShown` and `OnCellHidden`, `AWorldPartitionHLOD::SetVisibility`,
each of its components' `SetVisibility`). Two things in the engine made each flip expensive:

- **A flip recreates the render state.** `USceneComponent::OnVisibilityChanged` marks it dirty,
  so at the end of the frame each instanced HLOD component gets a new scene proxy: its
  instances sent to the GPU again and its materials gathered (`UStaticMesh::GetUsedMaterials`,
  about 5 microseconds a call) on the game thread.
- **The root's flip dirties the rest.** The HLOD builder makes one of an HLOD actor's
  components its root and attaches the others to it, and a component whose visibility
  changes marks the render state of everything attached to it dirty
  (`EVisibilityPropagation::DirtyOnly`), so every component of the actor was made anew
  whatever its own flip did.

An HLOD actor stands for one 128 m main cell and holds a component per distinct mesh (each
building's, street piece's and part's), up to several hundred; a step across a cell boundary
shows a row of cells ahead and hides a row behind (about 12 each at 768 m), and those frames
updated 800 to 2,400 HLOD components at 70 ms or more.

**The fix** (`UCityGenHLODComponent` in the play plugin, `CityGenHLODComponent.h`): the
instanced HLODs' component class is the play plugin's. It leaves its HLOD actor's root as it
begins to play (in a game only: each component flips its own visibility anyway), and a flip
keeps the scene proxy and only changes whether the scene draws it, on the render thread
(`FSceneInterface::UpdatePrimitivesIsDrawn_RenderThread`, the engine's FastGeo streaming's
way: Nanite, the shadows and the GPU scene read the drawn flag), a render command per
component. A component hidden when its render state was made (no proxy) is made anew once when
first shown, as before. Console: `CityGen.HLODFastVisibility 0|1` (0 the engine's way, for a
comparison; the bench pass `night_plan_all_hlodslow`), `CityGen.HLODStatus` (the flips in
place and recreated since the start, and why).

**How every import sets it up** (`unreal.set_hlod_class`, `hlod_class`, `HLOD_VERSION`):
when the play plugin is built, `[/Script/Engine.HLODBuilder]
HLODInstancedStaticMeshComponentClass=/Script/CityGenPlay.CityGenHLODComponent` in the
project's DefaultEditor.ini, else the key is taken out (the engine's class). The HLOD
builder's defaults read that config when the engine starts, before the plugin's classes
exist, so the plugin's module reads them again as it starts (editor builds only).
`build_hlods` records what the level's HLODs were built with in the project
(`Saved/CityGenHLOD/<level>.txt`: the class and `HLOD_VERSION`) and builds them all again
(`-SetupHLODs -RebuildHLODs`) when that changes, since the builder's own hash leaves the class
out; the result's `forced` and `component_class` say so. Delta's 763 HLOD actors built again
in 6.5 minutes.

**What it gave, and what made the rest** (Delta, the lean route): in the measured walk and
drive the HLOD flips are now in place (none recreated; before, 40 walk frames updated 200 or
more HLOD components), and the fly's p95 fell 0.7 ms against the same run's
`night_plan_all_hlodslow`. But most of the HLOD flood had been in the warm-up flight and
right after teleports; the walk's slow frames that remained are World Partition's cells
being added to the world (their actors' components registered, `AddToWorld`, a fixed 5 ms a
frame on top of a 13 ms frame), their packages loaded and the garbage collector after a cell
goes. So every import also turns on the engine's **adaptive AddToWorld time slice**
(`unreal.STREAMING_SETTINGS` in `PROJECT_SETTINGS`: `s.AdaptiveAddToWorld.Enabled=1` in the
project's `[SystemSettings]`): 1 to 6 ms a frame by how much is in flight, so walking adds a
little each frame and a teleport still gets its cells in (Delta's loads after a teleport 7.6
to 7.9 s, 7.9 before). A fixed 2 ms for both registration and loading
(`night_plan_all_stream2`) was as good on the walk but made the drive hitch (42 frames over
50 ms) and the teleports twice as slow (15 to 21 s); the bench's exploring passes keep both
for comparison. Delta's `night_plan_all` p95: 20.6 to 18.8 and 18.7 ms (two runs), the walk
22.9 to 20.5 and 21.7, the drive 20.7 to 19.6 and 19.0, the fly 19.9 to 16.4
(`docs/progress/fix_hlod_streaming/`).

## assetgen's street contribution (AG7)

`assetgen streets BUILD` writes `BUILD/assets/unreal_contribution.streets.json` beside its
packs (`BUILD/assets/streets/<tile>.glb`, one per 256 m tile, a node per piece named by its
citygen id; `streets/parts.glb`, the instanced parts), in AG0's format with `"part":
"streets"`, layer 2:

```json
{"version": 1, "stage": "assetgen", "part": "streets", "layer": 2,
 "masters": ["road", "opaque", "metal", "emissive", "translucent", "foliage"],
 "materials": {"asphalt.avenue": {"master": "road", "color": [0.17, 0.18, 0.2],
                                  "roughness": 0.85, "metallic": 0.0}, "...": {}},
 "entries": [
  {"key": "rs.e1234n567", "kind": "street.road", "hash": "<piece hash, 16 hex>",
   "replaces": ["d03.road_street.t+04+02"], "glb": "streets/t+04+02.glb",
   "node": "rs.e1234n567", "asset": "rs_e1234n567", "pivot": [1234.5, 567.2, 0.0],
   "yaw_deg": 0.0, "nanite": true, "triangles": 412, "slots": ["asphalt.street", "..."],
   "collision": {"complex": true}, "tile": "t+04+02"},
  {"key": "tl.crown_loop.tb.e579n728.glass", "kind": "street.transit.tube.glass",
   "nanite": false, "collision": {"none": true}, "node": "tl.crown_loop.tb.e579n728.glass.lod0",
   "lods": [{"node": "....glass.lod0", "screen_size": 1.0, "triangles": 1104},
            {"node": "....glass.lod1", "screen_size": 0.25, "triangles": 276},
            {"node": "....glass.lod2", "screen_size": 0.06, "triangles": 69}], "...": "..."},
  {"key": "d06.lot.w245s1218.el.w256s1089", "kind": "street.site.container_stack",
   "parts": [{"kind": "part.container.c3", "glb": "streets/parts.glb",
              "node": "part.container.c3", "asset": "part_container_c3", "count": 4,
              "triangles": 132, "xforms": [[-2.4, 1.1, 0.03, 23.5], "..."]}], "...": "..."}],
 "graphs": {"walkways": {"wk.e385n1069": [[364.0, 1146.48, 9.2], "..."]}}}
```

- **Keys and `replaces`**: every street element of the model is a piece keyed by its id
  (road segments, junctions, crosswalks, sidewalks, bridges, structures, tunnels, quays,
  waterways, site elements). `replaces` names the blockout objects the piece supersedes,
  taken from citygen's own blockout code: the joined objects per district, category and
  tile (`<district>.road_<class>.<tile>`, `.junction.`, `.crosswalk.`, `.sidewalk.`,
  `.quay.`, a megasite's `<owner>.<kind>.<tile>`), a raised road's `<id>.deck`, a tunnel's
  `<id>.tunnel` and its roads' `<id>.tunnel_road`. A structure's blockout object has the
  structure's id as its name, so its entry replaces it by key; M13's retaining walls too,
  since M15 draws one blockout object per wall (AG7 was made on one joined
  `city.retaining_wall.<tile>` per tile). Each joined object a piece replaces has every
  member covered (the report's `street_replaces` check), so dropping it loses nothing. The blockout's ground, water,
  open space, green areas, buildings, props and plants stay.
- **Pivot**: each piece's node sits at the middle of what it covers (0.01 m grid, z 0);
  vertices are relative to it. Z is absolute (M13's ground already added).
- **Materials**: one instance per slot (`materials`), parent by `master`; flat colors
  until AG6. The packs are lean (no UV1, no vertex colors); UV0 is in meters (along and
  across a road, or plan x and y).
- **Collision**: complex (the mesh itself): streets are walked and driven on.
- **Sky tube glass**: a separate entry (`<id>.glass`), non-Nanite, translucent, with three
  LOD meshes (24, 12 and 6 sides) and their screen sizes; the tube's frame and floor are
  the Nanite entry under the tube's own id.
- **Sky tube rings** (issue #97): the tube's Nanite entry holds its ribs at the model's
  rings and, on each lit one, an LED band in slot `led.<hex>` (the line's color at full
  brightness; master `emissive` in the contribution, `neon` once AG6 has run, so it glows
  more by `MPC_CityGen`'s `Night`). A slot of the same kind as `light`: no new master,
  entry or key.
- **Parts**: container stacks as instances of six container meshes in `streets/parts.glb`
  (transforms relative to the pivot: x, y, z, yaw).
- **Graphs**: `graphs.walkways` gives the line of every walkway of a raised road's sidewalks
  put on its deck (the model has them at z 0 under it, an M15 open item); z over the ground,
  as the model's.

**What the exporter does with streets** (done after M15 merged, with the buildings'):
`unreal_contribution.streets.json` is the second layer-2 contribution (sorted after the
buildings'), every blockout actor named in a `replaces` dropped; the masters `M_CgRoad`,
`M_CgOpaque`, `M_CgMetal`, `M_CgEmissive` (emissive strength 4), `M_CgTranslucent`
(blended, two-sided, opacity 0.35) and `M_CgFoliage` (two-sided), one instance per slot
(`MI_streets_<slot>`; AG7 writes its colors as sRGB, the exporter makes them linear); a
static mesh per piece under `Assets/Streets/<tile>`, complex collision, Nanite on; the sky
tube glass's LOD nodes imported (Nanite off), the chain made as the entry's `asset` from
them (`SetLodFromStaticMesh`, `SetLodScreenSizes`), its actor without collision; a
`BP_CityGenInstances` actor per entry and part kind from `parts` (`streets/parts.glb` under
`Assets/StreetsParts/parts`); the walkway graph data assets take `graphs.walkways` lines
instead of graphs.json's (on a terrain city the ground under them, graphs.json's z there,
is added); the new keys in the re-import digests.

## assetgen's water contribution (AG12)

`assetgen water BUILD` (and `assetgen build`, after the streets) writes
`BUILD/assets/unreal_contribution.water.json` beside its packs (`BUILD/assets/water/<tile>.glb`,
one per 256 m tile; `water/parts.glb`, the riprap stones), in AG0's format with `"part":
"water"`, layer 2:

```json
{"version": 1, "stage": "assetgen", "part": "water", "layer": 2,
 "masters": ["bed", "concrete", "water"],
 "materials": {"water.sea": {"master": "water", "textures": {"NormalTex":
                "atlas.water.normal", "FoamTex": "atlas.water.foam"},
                "scalars": {"Clarity": 6.0, "FlowScale": 1.0, "FoamAmount": 1.0,
                            "WaveHeight": 0.55, "WaveLength": 26.0, "RippleTileM": 8.0},
                "vectors": {"Scatter": [0.02, 0.07, 0.08], "Absorb": [0.45, 0.11, 0.08],
                            "Shallow": ["..."], "Deep": ["..."]}, "...": "..."},
               "bed.sand": {"master": "bed", "textures": {"BaseTex": "set.bed_sand.base",
                            "Caustics": "atlas.water.caustics", "...": "..."}}, "...": {}},
 "entries": [
  {"key": "sea.water.t-03+01", "kind": "water.surface.sea", "replaces": ["city.sea.t-03+01"],
   "glb": "water/t-03+01.glb", "node": "sea.water.t-03+01.lod0", "nanite": false,
   "collision": {"none": true}, "ids": ["sea"], "pivot": [-640.0, 384.0, 0.0],
   "lods": [{"node": "sea.water.t-03+01.lod0", "screen_size": 1.0, "triangles": 33012},
            {"node": "...lod1", "screen_size": 0.4}, {"node": "...lod2", "screen_size": 0.15},
            {"node": "...lod3", "screen_size": 0.05}], "...": "..."},
  {"key": "sea.bed.t-03+01", "kind": "water.bed", "replaces": ["city.bed.t-03+01"],
   "nanite": true, "collision": {"complex": true}, "...": "..."},
  {"key": "sea.bank.w568n284", "kind": "water.bank.riprap",
   "replaces": ["d02.bank_riprap.t-03+01"], "nanite": true, "collision": {"complex": true},
   "parts": [{"kind": "part.riprap.r3", "glb": "water/parts.glb", "node": "part.riprap.r3",
              "collision": {"none": true},
              "xforms": [[-2.4, 1.1, -1.62, 213.4, 0.92, 0.81, 0.69], "..."]}], "...": "..."},
  {"key": "water.blockout", "kind": "water.drop", "drop": true,
   "replaces": ["city.sea.t+05+05", "d04.bank_quay.t+03-05", "..."]}],
 "underwater": {"sea": {"water": "sea", "tint": [0.35, 0.62, 0.7], "fog": 0.06}, "...": {}}}
```

- **Keys**: per water body and tile, the surface `<body>.water.<tile>` and the bed
  `<body>.bed.<tile>` (a body's own water: its polygon less the bodies before it in M16's
  order, so no two overlap); per bank AG12 draws (natural, beach, marsh edge, riprap, road
  embankment, and canal walls along rivers and the sea) its id. `replaces`: a surface the
  tile's `city.sea.<tile>` (the sea) or `city.water.<tile>` (inland water), a bed the
  tile's `city.bed.<tile>`, a bank its joined `<district>.bank_<kind>.<tile>`. The drop
  entry (`water.blockout`) takes away the blockout's water objects no piece replaces: sea
  sheets of tiles with no sea (they lie under the land, and under inland water 5 cm under
  its surface they would show through the water), and the `bank_quay` and the waterways'
  `bank_canal_wall` bands, which AG7's quay and canal wall pieces draw.
- **Surfaces**: non-Nanite (Nanite does not take Single Layer Water), no collision (M16's
  swim volumes are the water), a LOD chain on coarser lattices (the sea 2, 4, 8 and 16 m,
  inland water 4, 8 and 16 m; screen sizes 1.0, 0.4, 0.15, 0.05). Vertex data the master
  reads: UV0 the plan in meters (x east, y north), UV1 the current in m/s (x east, y
  north: Unreal's y is citygen's -y, the master turns it over), COLOR_0 R the foam mask
  (walls, waterlines, bridge piers), G the depth over 12 m, B the sea's wave weight (M16's
  exposure, open 1, sheltered 0.5, harbor 0.15, nothing at the waterline). The packs keep
  their vertex colors and full-precision UVs, with no lightmap UVs over UV1 (the importer's
  water pipeline).
- **Beds**: Nanite, complex collision (the floor under a swimmer), UV0 the plan in meters
  (a steep step's triangles on vertices of their own, UV0 on the vertical plane they face),
  UV1.x the depth (the caustics' strength). On a terrain city the bed lies 0.1 m over M13's
  ground grid, which carries M16's beds under the water too.
- **Banks**: Nanite, complex collision; riprap stones as an instanced actor per bank and
  stone kind (six meshes in `water/parts.glb`; x, y, z, yaw, sx, sy, sz relative to the
  pivot), no collision.
- **Underwater**: per body its water kind's post-process tint and fog density; the
  exporter puts a post-process volume beside each of M16's swim boxes of that body.

**What the exporter does with water** (in this milestone): the third layer-2 part read
like the streets' (AG12 writes its colors as sRGB: `SRGB_PARTS`), its packs imported with
the water pipeline (vertex colors replaced, full-precision UVs, no lightmap UVs), the
surfaces' LOD chains made from their LOD nodes as the sky tube glass's; the masters:
- `M_CgWater` (`water_master`): the Single Layer Water shading model (its output node's
  scattering and absorption coefficients from the water kind's `Scatter` and `Absorb`, so
  the color deepens with the depth the shading model measures behind the surface; phase
  0.1), ripple normals from the water atlas sampled twice along the current (UV1, a flow
  map's two phases blended by their distance from the phase's middle, scaled by
  `FlowScale`, tiled every `RippleTileM`), foam from the vertex mask and the shallows (the
  vertex depth under 0.6 m) over the atlas's foam lace, drawn over the water by Opacity
  (white, rough), and the sea's waves by world position offset: four Gerstner waves on
  absolute world position (`WaveHeight`, `WaveLength`, the vertex's wave weight), faded out
  between 150 and 350 m from the camera, so a coarser LOD's edges never meet a finer one's
  moving, their slope added to the normal. Decision 13.10 (a): no Water plugin; an engine
  whose Python lacks the shading model's output node gets opaque reflective water instead
  (logged).
- `M_CgBed`: the textured surface (`textured_surface`, the bed's set by M16's material:
  mud, silt, sand, gravel, stone) with caustics as emission: the water atlas's two
  networks scrolled across each other on the world plan (`CausticTileM`), only under the
  water (UV1.x over 0.08 m), fading to nothing at 9 m and by night (`MPC_CityGen.Night`).
- An unbound-off `PostProcessVolume` per swim box of a body (`underwater.<water>.<tile>.<k>`,
  in `CityGen/underwater`, the swim box's size): the water kind's scene color tint,
  saturation 0.75, a vignette and the focal distance of its fog; tags as the swim volumes'
  (`cg.type=underwater`). `actor_hashes`, `actor_kinds` (`underwater`) and
  `manifest_changes` take them, `stage2.counts.underwater_volumes`.
`STAGE2_VERSION` 7 rebuilds the masters.

## assetgen's props and signs contributions (AG8)

`assetgen props BUILD` (and `assetgen build`, last) writes two layer-2 contributions beside
its packs: `unreal_contribution.props.json` (`"part": "props"`) and
`unreal_contribution.signs.json` (`"part": "signs"`), in AG0's format:

```json
{"version": 1, "stage": "assetgen", "part": "props", "layer": 2,
 "masters": ["opaque", "metal", "foliage", "emissive", "neon", "translucent", "holo"],
 "materials": {"metal.dark": {"master": "metal", "color": [0.023, 0.026, 0.03],
                              "roughness": 0.5, "metallic": 0.8},
               "leaf.oak": {"master": "foliage", "two_sided": true, "...": "..."}},
 "entries": [
  {"key": "prop.street_light.t+01+00", "kind": "prop.street_light", "hash": "<16 hex>",
   "replaces": [], "pivot": [384.0, 128.0, 0.0], "yaw_deg": 0.0, "tile": "t+01+00",
   "parts": [{"kind": "prop.street_light.civic.v3", "glb": "props/variants/street_light.glb",
              "node": "prop.street_light.civic.v3", "asset": "prop_street_light_civic_v3",
              "count": 2, "triangles": 214,
              "xforms": [[-12.4, 40.1, 0.0, 87.5, 1.0, 1.0, 1.0], "..."],
              "ids": ["d03.prop.street_light.e372n168", "..."]}]},
  {"key": "plant.street_tree.t+01+00", "parts": [{"kind": "plant.ginkgo.v5",
   "glb": "props/plants/ginkgo.glb", "nanite": true, "shape_preservation": "voxelize",
   "collision": {"none": true}, "xforms": [[x, y, z, yaw, 1.07, 1.07, 0.91]], "...": "..."}]},
  {"key": "prop.overhead_cable.t-03+05", "glb": "props/tiles/t-03+05.glb",
   "node": "prop.overhead_cable.t-03+05", "collision": {"none": true}, "...": "..."},
  {"key": "prop.barrier.t+00+02", "drop": true, "replaces": [], "...": "..."}]}
```

```json
{"version": 1, "stage": "assetgen", "part": "signs", "layer": 2,
 "entries": [
  {"key": "d05.prop.sign.w744n1012.slot", "kind": "sign.shop_sign", "hash": "<16 hex>",
   "replaces": ["prop.sign.t-03+03"], "glb": "props/signs/t-03+03.glb",
   "node": "sign.h1c0f9e2b7a4d3e51", "asset": "sign_h1c0f9e2b7a4d3e51",
   "pivot": [-744.2, 1012.4, 6.04], "yaw_deg": 49.2, "nanite": true, "triangles": 612,
   "slots": ["neon.ff2a6d", "sign.frame"], "collision": {"none": true}, "tile": "t-03+03"},
  {"key": "d01.lot.e1052n46.bld.slot.holo_ad.holo", "kind": "sign.holo_ad.holo",
   "nanite": false, "node": "d01.lot.e1052n46.bld.slot.holo_ad.holo.lod0",
   "lods": [{"node": "....holo.lod0", "screen_size": 1.0, "triangles": 134},
            {"node": "....holo.lod1", "screen_size": 0.3, "triangles": 116},
            {"node": "....holo.lod2", "screen_size": 0.08, "triangles": 2}], "...": "..."}]}
```

- **Props and plants replace M15's prototypes**: M15 draws each prop and plant kind of a
  tile as one instanced actor of a prototype (`prop.<kind>.<tile>`, `plant.<type>.<tile>`);
  AG8's entry has that actor's key and holds the variants as parts: per part kind the
  family pack's node (`props/variants/<kind>.glb`, `props/plants/<species>.glb`, every
  variant at the origin), its instances' transforms from the entry's pivot (the tile's
  middle: x, y, z in meters, yaw in degrees, then the scale) and the citygen id of each.
  Plants: Nanite with `ShapePreservation` `Voxelize` (AG0's finding; 5.8, experimental),
  no collision. The exact props (cables, scaffolding, market gates) are one mesh per kind
  and tile in `props/tiles/<tile>.glb`, an actor in place of the same key. M6's highway
  median barriers, which AG7's road pieces draw as one continuous barrier, are left out; a
  prototype actor with nothing left gets a `drop` entry.
- **Signs**: an actor per M11 sign slot at the slot's position and yaw (x the way the face
  looks); a tile's distinct sign meshes in `props/signs/<tile>.glb`, shared by the slots
  that draw the same sign; shop signs name their tile's sign prototype actor
  (`prop.sign.<tile>`) in `replaces`, M20's large ads their kind's (`sign.billboard.<tile>`,
  `sign.banner.<tile>`, `sign.holo.<tile>`). A holo-ad is two entries: the projector on the
  roof (Nanite; for M20's holo-boards in front of a facade, on an arm off the wall) under the
  slot's key, the image `<slot>.holo`, non-Nanite, a LOD chain of three (the planes, text,
  frame and scan bands; the text; one plane) on the `holo` master. M20's billboards lit as
  neon have a neon tube round the face in place of the lamps; its banners are drawn as the
  neon bands are, a brand's name stacked in tubes (AG15 draws the large ads whole).
- **Materials**: linear colors (no conversion, unlike AG7's); `neon` (emissive 8), `emissive`
  (lamps, screens, lit faces; 4), `holo` (translucent, two-sided, emissive 3), `foliage`
  (two-sided). With AG6's library (after AG6, `materials/contrib.props`) every slot takes
  its catalog master and set (`catalog.PROP`), tinted by its color, with `textures`,
  `scalars` and `vectors` as AG6's records and the contribution's `textures` table: painted,
  galvanized and rusty metal, plastic, car paint, timber, fabric, bark (`bark_furrowed`,
  `bark_smooth`, `bark_ringed`); leaf cards (`leaf.<species>`) on the `leaves` master with a
  leaf clump set (`leaves_broad`, `_lobed`, `_fan`, `_needle`, `_small`; UV0 spans the whole
  tile on each card); solid foliage (`foliage.<species>`: palms, sedum, scrub, a shrub's
  body) on `foliage` with `grass`.
- **One sign path with AG6**: AG6's signage gives every slot its text, script, style and
  colors and draws the flat faces on the city's sign pages; AG8's sign faces are quads whose
  UV0 is the slot's page cell, slot `page.<page>` (master `sign`, `SignTex` the page's
  texture `city.<page>`, the same record as in `unreal_contribution.materials.json`) and a
  holo-ad's screen `holopage.ads_1` (master `holo` with `SignTex`, `Textured` 1); neon tubes
  and channel letters spell the same text in AG6's strokes. AG6's own sign quads are only a
  preview of where AG8 has not run.
- **Collision**: none on plants, signs and exact props (they stand off the walkways or over
  head); complex on prop variants.

**What the exporter does with props and signs** (AG8): `stage2` looks a key up among M15's
prototype actors too, so an entry keyed by one, or naming one in `replaces`, drops it; a
`drop` entry only drops; a part may carry `ids` (the instance actor's `Ids` then hold one
id per transform), `collision`, `nanite` and `shape_preservation` (on its mesh record, in
its hash); transforms may carry a scale (`[x, y, z, yaw, sx, sy, sz]`); `EMISSIVE2` gains
`holo`. The importer skips the replaced prototype actors, applies the scale and ids, sets
`NaniteShapePreservation.VOXELIZE` on a mesh whose record asks for it, and makes `M_CgHolo`
(the translucent master with an emissive strength). A part with `collision: {"none": true}`
(plants) makes its instanced actor `no_collision` (the HISM's profile `NoCollision`; fixed in
AG8's Unreal check, `docs/progress/AG8/unreal/`). With AG6's materials (`STAGE2_VERSION` 5):
`M_CgLeaves` (the leaf tile on UV0 / TileM, the tint over its leaves, the opacity mask its
tint mask, masked and two-sided, Nanite `Voxelize` at distance as before) and `M_CgHolo`
reading `SignTex` (the holo ad page as emission, the opacity by its brightness, where
`Textured`).

## assetgen's ground contribution (AG13)

`assetgen ground BUILD` (and `assetgen build`, after the props) writes
`unreal_contribution.ground.json` (`"part": "ground"`) beside its packs:

```json
{"version": 1, "stage": "assetgen", "part": "ground", "layer": 2,
 "masters": ["grass", "ground"],
 "materials": {
  "ground.lawn.t+01+05": {"master": "ground", "color": [0.08, 0.2, 0.04],
   "textures": {"BaseTex": "set.ground_lawn.base", "NormalTex": "...", "OrmTex": "...",
                "WornBaseTex": "set.ground_dirt.base", "...": "...",
                "ShadeBaseTex": "set.ground_moss.base", "...": "...",
                "Mask": "city.ground.t+01+05", "Macro": "atlas.macro.macro"},
   "scalars": {"TileM": 2.0, "WornTileM": 2.0, "ShadeTileM": 1.0, "MaskX0": 256.0,
               "MaskY0": 1280.0, "MaskSize": 256.0, "WearK": 1.0, "MossK": 0.6,
               "EdgeK": 0.5, "WetK": 0.6, "Tinted": 1.0, "Textured": 1.0},
   "vectors": {"RefColor": [...], "WornRefColor": [...], "BaseFlat": [...], "...": "..."}},
  "grass.meadow": {"master": "grass", "color": [0.15, 0.27, 0.04], "roughness": 0.8,
                   "scalars": {"Wind": 1.0}, "vectors": {"DryColor": [0.46, 0.37, 0.11]}}},
 "textures": {"city.ground.t+01+05": {"file": "ground/masks/t+01+05.png", "kind": "mask",
                                      "srgb": false, "size": [512, 512], "...": "..."}},
 "entries": [
  {"key": "ground.t+01+05", "kind": "ground.cover", "glb": "ground/tiles/t+01+05.glb",
   "node": "ground.t+01+05", "pivot": [384.0, 1408.0, 0.0], "nanite": true,
   "triangles": 1498, "slots": ["ground.lawn.t+01+05", "..."],
   "replaces": ["d03.cover_mown_lawn.t+01+05", "d03.lawn.t+01+05", "..."]},
  {"key": "grass.t+01+05", "kind": "ground.grass", "pivot": [384.0, 1408.0, 0.0],
   "parts": [{"kind": "clump.meadow.v2", "glb": "ground/clumps.glb",
              "node": "clump.meadow.v2", "count": 3120, "triangles": 185,
              "xforms_file": "ground/grass/t+01+05.json", "nanite": false,
              "collision": {"none": true}, "cull_m": [60.0, 100.0], "shadow": false}]},
  {"key": "d07.cover_paving.t-02+04", "kind": "ground.drop", "drop": true}]}
```

- **Ground**: one actor per tile in place of the blockout's ground cover objects of that
  tile (`<district>.cover_<kind>.<tile>`, M16) and its median lawns
  (`<district>.lawn.<tile>`, M6's verges, which nothing replaced before); a blockout object
  whose pieces lie wholly in the tiles beside its own gets a `drop` entry (those tiles draw
  them). Nanite, complex collision (the lawns are walked on), 0.1 m over the ground as the
  blockout's flats were. The mesh's slots are per surface and tile: the tile's mask
  (`ground/masks/<tile>.png`, 512 px for its 256 m, linear, row 0 its south edge: R wear, G
  shade, B edge, A moisture) is a texture per tile, so its material is too.
- **Grass**: decision 13.9 (a), baked per tile. An entry per tile with a part per clump
  variant; the transforms (`[x, y, z, yaw, s, s, s]` from the pivot, the tile's middle) are
  in `ground/grass/<tile>.json` under the part's node (`xforms_file`), not in the
  contribution (a city has one to two million clumps). Not Nanite (the master sways by world
  position offset), no collision, no shadows, culled between 60 and 100 m (`cull_m`), out of
  the HLODs.
- **Materials**: `ground` (`M_CgGround`): its three sets (base, worn, shade) on UV0 (the plan
  position in meters) over their TileM, the mask on world x, y (`MaskX0`, `MaskY0`,
  `MaskSize`); worn over base by the wear and the edges (`WearK`, `EdgeK`), the edge broken
  up by the base set's height; the shade set where shade and moisture meet (`MossK`); darker
  and smoother where wet (`WetK`); the base set tinted over its tinted pixels where `Tinted`
  (the instance's `BaseColor`: a lawn's green). Without AG6's library (`Textured` 0) flat
  colors (`BaseFlat`, `WornFlat`, `ShadeFlat`). `grass` (`M_CgGrass`): untextured, the
  slot's color toward `DryColor` by the vertex colors (R height share, G tone, B dryness),
  darker at the root, two-sided, masked, dithered out with the instance's fade
  (`PerInstanceFadeAmount`), swaying by world position offset: the vertex's height share
  squared times `MPC_CityGen`'s `Wind` (a new scalar, default 0.35, which stage 3 drives)
  times the slot's own `Wind` (sedum 0.05 to plumes 1.4), two waves along the world phased
  per instance.

**What the exporter does with the ground** (AG13): a part may give `xforms_file` (relative to
`assets/`) instead of `xforms`: the instance actor's record then holds `xforms_file`,
`xforms_key` (the node), `count` and the file's sha256 (`xforms_sha`, in its hash), and the
importer reads the transforms from the file (one file at a time, as the actors come tile by
tile); a part's `cull_m` becomes the HISM's cull distances (`set_cull_distances`, start and
end in centimeters), `shadow: false` turns its shadow off, and an instance actor with
`cull_m` is left out of the HLODs (`enable_auto_lod_generation` off on its component and
actor). `MPC_CityGen` gains `Wind` (a collection without it gets it, keeping `Night`).
Masters `M_CgGround` and `M_CgGrass` (`stage2_master`).

## assetgen's materials (AG6)

`assetgen build` now textures what the contributions name (`assetgen/materials/contrib.py`;
spec of the library and masters: `assetgen/materials/catalog.py`):

```json
{"textures": {"set.brick_heritage.base": {"file": "library/sets/brick_heritage_base.png",
                                          "pixels_sha256": "...", "size": [1024, 1024],
                                          "srgb": true, "kind": "color"},
              "set.brick_heritage.normal": {"...": "...", "srgb": false, "kind": "normal"},
              "atlas.interiors.night": {"file": "library/atlases/interiors_night.png", "...": ""}},
 "materials": {"brick@heritage": {"master": "facade", "slot": "brick", "tint_cpd": 0, "...": "",
                                  "textures": {"BaseTex": "set.brick_heritage.base",
                                               "NormalTex": "...", "OrmTex": "...",
                                               "Macro": "atlas.macro.macro",
                                               "Decals": "atlas.decals.base"},
                                  "scalars": {"TileM": 2.0, "Textured": 1.0, "Streaks": 1.0},
                                  "vectors": {"RefColor": [0.17, 0.06, 0.03]}}},
 "entries": [{"key": "d04.lot.e512n88.bld", "materials": {"brick": "brick@heritage"},
              "cpd": ["... 30 floats"], "...": ""}],
 "library": {"version": "ag6.1", "hash": "...", "density_px_m": 512}}
```

- **Textures**: each contribution lists the textures its materials read: the shared library's
  sets (`set.<set>.base|normal|orm`) and atlases (`atlas.<atlas>.<map>`), whose files are
  under `BUILD/assets/library` (a link `assetgen build` makes to the library folder,
  `~/.cache/cybergen/assetgen_library/d<density>` or `$ASSETGEN_LIBRARY`), and the city's
  pages (`city.<page>`, `BUILD/assets/textures/`). `kind`: `color` (sRGB), `normal` (OpenGL:
  green up; flipped on import), `mask` (linear: occlusion, roughness, metallic and the tint
  mask in alpha). The pixel hash is the texture's identity: the same name with other pixels
  in two contributions is refused.
- **Materials**: AG1's and AG7's fields stay; `textures` (parameter to texture), `scalars`
  and `vectors` (`RefColor`, linear: the set's mean color where it takes the tint, which the
  tint replaces) are new. Masters: `facade`, `metal`, `concrete`, `road`, `foliage` (textured
  surface: base color, normal, ORM, tint over the tinted pixels, macro map, grime from the
  ground, rain streaks under the top, the road's atlas stains), `glass` (interior mapping),
  `neon`, `sign`, `decal`, and AG1's and AG7's `opaque`, `emissive`, `translucent`.
- **Era materials**: a wall or roof slot (`concrete`, `plaster`, `brick`, `panel`,
  `cladding`, `roof`) has one material per era, `<slot>@<era>`, with `slot` naming the mesh
  slot; a building's entry maps its slots to its era's (`materials`); the mesh's own slot
  keeps the slot's base material (the `mixed_modern` sets).
- **Custom Primitive Data**: 30 floats: AG1's 23, then the room width and floor height (the
  interior grid), the interior atlas row, rain streaks, the building's top over its pivot,
  the share of blinds down and the era's index (`cpd_layout`).
- **Window interiors**: the glass master finds each window's room from UV0 (meters along the
  facade and up from the base) and the building's room width and floor height: rooms are
  cells of that grid, the view goes into the cell's box in the facade's tangent frame, its
  hit is projected onto the interior atlas's one-point image of a room (row by use, column
  by a hash of the cell, lit by the lit-window ratio, blinds by their share). Nothing per
  pane or per vertex: the panes AG1's packs give UV1 and a window id in the vertex alpha
  are not read any more (AG2 or AG9 may drop them from the glass slots, for lean meshes).
  This is what AG1's Unreal check needed: curtain wall panes that share corners came out per
  triangle there, which data that is a function of position cannot.
- **`unreal_contribution.materials.json`** (part `materials`): no entries; a `sign`
  material per sign, ad and logo page and the `decal` material with their textures, for
  AG3's and AG8's sign meshes and decals (`signs.json` maps every sign slot to its page and
  cell).

**What the exporter does with them** (`citygen/unreal.py` `stage2`,
`citygen/ue/import_city.py`):
- the manifest's `stage2.textures`: per texture its file (from BUILD), pixel hash, kind,
  color space and folder: the library's under `/Game/CityGen/Core/Textures` (once per
  project, shared by every city), the city's under `<city>/Assets/Textures`; a material's
  record carries each texture's hash, so new pixels update the instances that read them and
  no actor; an actor's record carries its era materials (`materials`, slot to instance), so
  another era updates only that actor;
- `textures2`: each texture imported (`AssetImportTask`) when missing or of another hash,
  with its color space, compression (`TC_NormalMap` with the green channel flipped,
  `TC_Masks`, default) and texture group; the city's pages it no longer has deleted;
- `/Game/CityGen/Core/MPC_CityGen` with `Night` (0 by day; stage 3 drives it): the rooms
  light, neon and signs glow with it;
- the masters rebuilt (`STAGE2_VERSION` 4) with Custom HLSL nodes for the surface, the
  room, the glass and the stains, their sample parameters defaulting to a texture of the
  build of each kind; the instances get their textures, scalars and vectors; each actor its
  era instances as override materials on its component (by slot name).

## atmosgen's runtime (AT0)

Stage 3 (`docs/atmosgen_scope.md`) renders its plan in Unreal through a C++ runtime plugin
of its own, `CityGenAtmos` (`citygen/ue/CityGenAtmos`), as the play features do theirs:

- **Built with the play features:** `unreal_play.PLUGINS` is both plugins; `citygen unreal`
  (and `--bench`) copies both into the project (`Plugins/CityGenPlay`,
  `Plugins/CityGenAtmos`), enables both in the .uproject and builds them in one
  UnrealBuildTool run, one stamp for both (`plugin_hash` covers both sources). A project
  without a compiler imports without either, as before.
- **Its assets from code** (`citygen/unreal_atmos.make_assets`, the editor script
  `citygen/ue/atmos_assets.py`, a headless run skipped when the project's
  `Saved/citygen_atmos_assets.txt` names this version): `/Game/CityGen/Core/Atmos/`
  `MPC_CityGenAtmos` (`Rain`, `Wetness`, `FogDensity`, `WindMS`: a collection of its own, so
  making it recompiles none of the city's materials), `M_CgRain` (streak cards, translucent
  and lit by the translucency volume, falling by world position offset with a phase per
  instance and drifting with the wind) and `M_CgWet` (a DBuffer decal: darker and glossier
  surfaces, puddles by a value noise on the plan). Niagara is not used: UE 5.8 has no API to
  author an emitter from code (scope 4.2).
- **The controller** (`ACityGenAtmos`, an `AInfo` always loaded, not hidden): reads a plan
  (`BUILD/atmos`: `atmos_plan.json`, `lights/<tile>.json`) into a 64 m spatial index; every
  0.2 s keeps the `MaxLive` lights nearest the view within `MidRangeM` live (512 within
  300 m by default, the plan's tiers; near-tier lights, the shop signs, only within
  `NearRangeM` 60 m), the nearest `MaxShadowed` (16) of those that may cast shadows with
  shadows, the farthest fifth fading out; pools of spot, point and rect light components
  reused (rect lights in nits, the rest in candela); each light scaled by its schedule at
  `Hour` and by $2^{EV_{scene} - EV_{plan}}$ (the scene's -3 EV100 night against the plan's
  `night_ev100`), flickering ones dropping by a hash of their seed and the 1/12 s step. It
  sets `CityGen.PlayLamps` 0 while its lights are on (the play features' lamps, pools and
  washes go dark, decision 12.2). It also holds AT0's prototypes of the air and weather: an
  exponential height fog with volumetric fog by the plan's weather, the rain cards round the
  view (4,000, 25 m round it, 24 m tall), the wet decal (600 m square, 1.4 m deep round the
  street level, following the view in 40 m steps), and MegaLights by a post-process volume
  of its own.
- **Console commands:** `CityGenAtmos.Lights`, `.Fog`, `.Rain`, `.Wet`, `.MegaLights`,
  `.FarPools [0|1]`, `.Tiers LIVE RANGE_M SHADOWED`, `.Hour H`, `.Gain G`, `.Scattering S`,
  `.Status` (one JSON line: the cells and lights registered, live by shape and by kind,
  shadowed, candidates, the live set's update time, the scale, the effects, `r.RayTracing`,
  whether the lights show). AT0's `.Load DIR` is gone with `-CityGenAtmosPlan` (AT1).
- **AT0 placed nothing in the level** (a game started with `-CityGenAtmosPlan=<dir>` got the
  controller from a world subsystem). Since AT1 the import places the controller and the
  plan's cells ("From AT1" below); the subsystem and the command line are gone.
- **The benchmark:** `--bench-atmos` (a plan's folder in AT0, a flag since AT1: the level has
  the plan) makes the assets first and adds atmosgen's passes to `--bench-passes`
  (`bench.ATMOS_PASSES`: `night_plan`,
  `night_plan_fog`, `night_plan_all` with rain and wet streets, `night_plan_256` and
  `night_plan_1024` for the live set's size, `night_play_air` the effects over the play
  features' lamps, `night_plan_mega` and `night_plan_mega_2048` with MegaLights); a pass's
  `commands` run at its start (`UCityGenBench`), every other pass switches atmosgen off, the
  night's warm-up has all of it on. `--bench-rt` starts the game with hardware ray tracing
  (`bench.RT_INI`, for MegaLights), the project's settings untouched. `bench.busy` also waits
  for another benchmark's game (a packaged one too: `-CityGenBench=` on its command line)
  and its driver.

### From AT1: streets at night

The city's atmos plan comes with the import (`citygen unreal BUILD UPROJECT`, the plan in
`BUILD/atmos` or `--atmos DIR`; `--no-atmos` leaves it out, and its actors from an earlier
import go):

- **Layer 3 of the manifest** (`citygen/unreal_atmos.write_atmos`, the manifest's `atmos`):
  the controller's key (`atmos`) and hash, and a cell per 128 m cell of World Partition's
  main grid that holds lights (`atmos.lights.<tile>.<quarter>`: citygen's 256 m tile and its
  quarter, `sw`, `se`, `nw`, `ne`), its middle, light count and hash (of its lights' records
  and the packing's version); `counts.atmos_cells`, `counts.atmos_lights`; `actor_hashes`,
  `actor_kinds` (`atmos`, `atmos_cell`) and `manifest_changes` take them as actors. The
  records themselves go to `BUILD/unreal/atmos.json` (`controller`: the city, the plan's
  hash, the schedules' names and their 24 hourly values, the light kinds, the plan's night
  exposure, hour, weather and tiers; `cells`: each cell's lights packed, `pack`). **A plan
  whose lux check did not pass is not delivered** (scope 8): the manifest names it
  (`atmos.skipped`) and the city imports without it; an AT0 plan, which has no check, too.
- **Packed lights** (`CityGenAtmosCell.h`, `CityGenAtmosPack`): 16 floats a light in
  Unreal's frame (position in cm, pitch and yaw, a rect's width and height, the source
  radius, the intensity in candela, or nits for a rect, the linear color, the reach, a
  spot's cones or a rect's barn door angle, the flicker depth) and 2 ints (flags: shape,
  may cast shadows, near tier only, on or broken, no specular, schedule, kind and mount
  indices; a seed from its record's hash).
- **The importer** (`Importer.atmos_cells`, `atmos_controller`): a `CityGenAtmosCell`
  actor per cell at its middle, spatially loaded (no primitive: World Partition streams it
  by its location, in the main grid's 128 m cell holding it), its `LightFloats` and
  `LightInts`, tags `cg.key`, `cg.hash`, `cg.type=atmos_lights`, `cg.category=atmos`,
  `cg.tile`, folder `CityGen/Atmos`, made among the offloaded actors; then the
  `CityGenAtmos` controller, always loaded, with the plan's settings (`cg.type=atmos`).
  Both carry their own actor version (`ATMOS_VERSION`), so a new packing re-imports only
  them. atmosgen's assets (`MPC_CityGenAtmos`, `M_CgRain`, `M_CgWet`) are made first when
  the project lacks them (`unreal_atmos.make_assets`).
- **The runtime** (`CityGenAtmos`): a cell registers its lights with the controller when it
  begins play (the controller takes those already in when it begins) and takes them out at
  its end play, as its World Partition cell streams; the controller keeps them by cell and
  every 0.2 s picks the live set from the cells within the mid range of the view (the
  nearest 512 within 300 m, 16 shadowed within 60 m: AT0's measured tiers), from pools of
  spot, point and rect light components. Its lights show by night (`MPC_CityGen`'s
  `Night`, the play features' switch until AT3), cost nothing by day, and while they show
  the play features' light pools stand only past the live range (`CityGen.PlayLamps` 2).
  The fog, rain and wet streets stay off until AT4 and AT5 (the benchmark's passes and the
  console commands switch them).
- **The play features** lose AG15's spot lamps and sign washes (their properties,
  `play.json` version 3 without `washes`; `GetStatus` without `lamps_lit`); the light pools
  stay.
- **The check** (`check_city.py`): by night the controller's status (cells registered,
  lights live by kind, shadowed) is part of the play features' check, which needs its
  lights live near the player when the city has a plan (else the light pools); the night
  views log the live set. `CITYGEN_UE_LAMP_DEBUG=1` still skips the walk's checks, straight
  to the play features and their views.
- **No highlight from a lit face's stand-in**: the lights standing in for a sign's or a
  shopfront's lit face (kinds `sign`, `shop_sign`, `spill`) have specular scale 0 (the plan's
  `specular`, flag bit 5 of the packed record): a glossy surface reflects the face itself,
  through Lumen, and a light's highlight on it is a bright ball (the play features' sign washes
  put one in nearly every billboard). The same rule holds for AT2's sign lights.
- **A city without an atmos plan** imports as before (no controller, no cells), its night
  lit by the light pools alone.

### From AT2: neon and signs as light

The plan's AT2 lights (`docs/atmosgen_scope.md` 6.1: lit faces stood off their walls, neon
spill, crown floods and uplights, aviation lights, searchlights, a port's and a spaceport's
lights) come through the same cells; what changed in the exporter and the runtime:

- **Packing version 2** (`unreal_atmos.PACK_VERSION`, `CityGenAtmosPack`): 19 floats a light,
  AT1's 16 then an animation's period (s), amount (a blink's on share, a sweep's swing in
  degrees either way) and phase (0 to 1); the flags' bit 6 the high tier, bits 28-29 the
  animation (0 none, 1 blink, 2 sweep). The importer's `ATMOS_VERSION` is `atmos2`, so an
  import over an AT1 level re-packs every cell and the controller, and nothing else.
- **The high tier** (the plan's `tiers.high_m`, `high_max`; the controller's `MaxHigh`,
  `HighRangeM`, 48 within 750 m by default, `max_high` and `high_range_m` in `atmos.json`):
  crown floods, uplights, searchlights and high masts are a pool of their own, the nearest
  within World Partition's loading range, so they never take a street light's place in the
  mid set nor it theirs; never shadowed, the farthest fifth of the range fading.
  `CityGenAtmos.High LIVE RANGE_M` sets it.
- **Animation:** a blinking light (aviation) is on for its share of each period from the
  world's time; a sweeping one (a searchlight) swings its yaw by its amount and its pitch a
  little, out of step; both with the flicker in one per-frame pass over the live set (which
  now keeps each light's fade, so a flickering light no longer pops to full at the live
  range's edge).
- **The fixtures' stand-ins** (until stage 2 draws them, the plan's fourth ask): per cell an
  instanced component of red glows, one per aviation light (`/Engine/BasicShapes/Sphere`
  0.9 m across in `M_CgBeacon`, blinking from per-instance data with its light), and per
  searchlight a beam (`/Engine/BasicShapes/Cone`, 400 m long, its apex at the light, in
  `M_CgBeam`: additive, fading along it and at its silhouette, depth-faded where it meets a
  surface; its color, glow and half length in custom primitive data), turned with its sweep
  every frame. Made as a cell registers and destroyed as it streams out, shown only while
  the lights show (by night). `CityGenAtmos.Fixtures [0|1]` switches them; the controller's
  `BeaconGlow` and `BeamGlow` scale them.
- **Assets** (`atmos_assets.py` version 3): `M_CgBeacon` and `M_CgBeam` beside AT0's,
  under `/Game/CityGen/Core/Atmos` (cooked always, as `unreal.ALWAYS_COOK` already lists the
  folder and `/Engine/BasicShapes`).
- **Not delivered when a lit face floods its wall:** a plan whose faces check failed is left
  out as one whose lux check failed (`atmos.skipped`).
- **Status and the check:** `CityGenAtmos.Status` adds `high`, `max_high`, `high_m`,
  `candidates_high`, `animated`, `beacons`, `beams` and `fixtures`; the check's night line
  and its night views log them.
- **The lit faces' stand-ins** (billboards, banners, holo-boards, neon bands, shop signs) keep
  AT1's rule: no specular highlight.

### From AT3: sky and time

The plan's `sky` (`docs/atmosgen_scope.md` 6.2, `atmosgen/sky.py`) comes with the
controller; atmosgen now drives the level's sun, sky light, exposure and sky by the hour,
which the play features did with their night switch (decision 12.2):

- **The controller's sky and time** (`unreal_atmos.sky_settings`, in `atmos.json`'s
  `controller` and so in its hash): the city's latitude and the sun's declination that day,
  the moon (how far it trails the sun, its declination, lit fraction, its light's share of the
  sun's and color, its disk's luminance and size, where its light fades in, how much the deck
  takes), the sun's light by day (`SunLux` 10, the importer's sun), the night's and the day's
  exposure (`SceneEV100` -3, `DayEV100`), the curves over the sun's elevation (`CurveElev`
  with `CurveEV`, `CurveNight`, `CurveSun`, `CurveSky`, `CurveStars`), the stars, the cloud
  deck (`CloudDeckM`, `CloudCover`), the named hours (`DayHour`, `DuskHour`, `NightHour`) and
  the deck's glow (`GlowBounds` in Unreal's frame, `GlowMaxNits`). `ATMOS_VERSION` is
  `atmos3`: an import over an AT2 level sets the controller and re-packs its cells (their
  records unchanged) and touches nothing else.
- **The glow texture** (`Importer.atmos_glow`): the plan's `sky_glow.png`, copied beside the
  manifest (`unreal/atmos_sky_glow.png`, the manifest's `atmos.glow` with its sha256), imported
  as `/Game/CityGen/<City>/Atmos/T_<City>_SkyGlow` (linear, clamped, never streamed; again only
  when its bytes change) and set as the controller's `SkyGlow`.
- **Time of day** (`ACityGenAtmos::ApplyTime`, on every `SetHour` and 15 times a second while
  `TimeSpeed` runs the hour): the sun's and the moon's places from the latitude, declination
  and hour as `atmosgen/sky.py` computes them; the importer's `lighting.sun` is the sun while
  `CurveSun` gives it light (its intensity `SunLux` times the curve; from under the horizon it
  still lights the sky atmosphere's twilight, not the ground), then the moon (its light faded in
  from the sun at -12 degrees to -16, by its rise, phase and the deck's cover, in its blue);
  `lighting.sky` at its intensity times `CurveSky` (its real-time capture takes the sky dome,
  so a glowing deck tints the city's ambient); the exposure held at the hour's (the
  controller's post-process volume: min and max brightness both the exposure, no bias,
  adaptation 20 a second: no pumping) from the night's -3 EV100 to the day's by `CurveEV`;
  `MPC_CityGen`'s `Night` (`CurveNight`) and `Hour`. The plan's lights show while `Night` is
  over 0.02 and keep the night's scale, $2^{EV_{night} - EV_{plan}}$, at every hour (at dusk,
  under a brighter exposure, they read dimmer); each light's schedule is interpolated between
  the hours, so the street lights (`dusk_dawn`, set by the sun) come on as it sets.
- **The sky dome** (`M_CgSky`, `atmos_assets.py` version 8: unlit, `is_sky`, on the engine's
  sphere scaled to 50 km round the view, no shadow, collision, distance fields or ray
  tracing): the sky atmosphere in the view direction (`SkyAtmosphereViewLuminance`) with the
  sun's disk while the light is the sun, the stars (a hashed lattice on the view direction,
  twinkling, by `Stars` times `CurveStars` and the gaps in the deck), the moon (a disk at its
  place lit from the sun's: its phase, mottled maria, a halo), and the cloud deck: a plane
  `CloudDeckM` up met along the view ray (parallax as the camera moves), its cover a
  value-noise fbm drifting with the wind, lit by the atmosphere's light at the deck
  (`SkyAtmosphereLightIlluminance`: the sun by day, the moon by night) and the sky under it,
  and from below by the city's glow (the texture by world X and Y, squared, times
  `GlowMaxNits` and the lights' scale and `Night`), fading into the haze with distance. A
  dynamic instance per controller; the controller sets its parameters with the hour.
- **The play features** (CityGenPlay): `SetNight` sets the controller's day or night hour
  (`SetNamedHour`) when the level has one, else their own night switch as before; `IsNight`
  is the controller's `Night` over a half (`GetNight`), and the light pools show while it is
  over 0.02. The Tab menu's time row shows the hour, its arrows step it, a click swaps day and
  night, and a slider under it sets any hour to the quarter (`SetTimeOfDay`; `ClickMenuRow`
  and `CityGen.MenuRow` take `hour=H`, a number or `day`, `dusk`, `night`); the minimap's
  line shows the time.
- **Console commands:** `CityGenAtmos.Hour` also takes `day`, `dusk` and `night`;
  `CityGenAtmos.Sky [0|1]` (the sky and time: off hides the dome and leaves the level's
  lighting and exposure as the last hour set them), `.Exposure [0|1]` (the exposure held, or the engine's),
  `.TimeSpeed H` (game hours a real second), `.Cover C` (the deck's cover for the session).
  `.Status` adds `sky`, `night_now`, `ev100`, `sun_elev`, `moon_elev`, `moon_lux`,
  `time_speed`, `dome`, `deck_m`, `cover`, `glow` and the named hours.
- **The check:** by day, at dusk and by night the controller's status (the sun's elevation,
  `Night`, the exposure, the lights live); the play features' check needs the night held dark
  (`Night` 1, the night's exposure), the day lit with no light live and dusk between them,
  the exposure rising night to dusk to day. With `--shots` the `--view`s named `dusk_*` render
  at the plan's dusk and `t<HHMM>_*` at that hour, beside `pday_*` by day and `night_*` by
  night.
- **The benchmark** (`bench.ATMOS_PASSES`): `dusk_plan`, `dusk_plan_all` (the plan's dusk),
  `day_plan`, `day_plan_all` (its day hour) and `night_plan_nosky` (the night without the
  sky dome: what it costs); every other atmos pass, and `ATMOS_OFF`, sets
  `CityGenAtmos.Sky 1`, and each its hour last (a game with an earlier plugin warns of the
  unknown command).
- **A plan without a sky** (an AT2 plan): the controller keeps the level's lighting and reads
  `MPC_CityGen`'s `Night` as before, the play features keep their switch.

### From AT4: air

The plan's air (`docs/atmosgen_scope.md` 6.3, `atmosgen/air.py`: the plan's `air`, `volumes`
and `emitters`) comes with the cells and the controller:

- **Packing version 3** (`unreal_atmos.PACK_VERSION`, `CityGenAtmosPack::VolFloats`,
  `EmitFloats`): a cell also holds the fog volumes whose middle lies in it (13 floats: the
  middle in cm, the yaw, the half sizes along it, across and up in cm, the density, the floor
  share, the phase g, the albedo; an int: schedule and kind) and the plumes whose foot lies in
  it (9 floats: the foot, the width and rise in cm, the opacity, the albedo; two ints: schedule,
  kind and mount, a seed), as the cell actor's `VolumeFloats`, `VolumeInts`, `EmitterFloats`
  and `EmitterInts`; a cell is made wherever any of the three lie (its key still
  `atmos.lights.<tile>.<quarter>`, its hash over all three). The manifest's `atmos` counts
  `volumes` and `emitters`. `ATMOS_VERSION` is `atmos4`: an import over an AT3 level re-packs
  the cells and sets the controller, and touches nothing else.
- **The controller's air** (`unreal_atmos.air_settings`, in its hash): the height fog's
  density, falloff and start, the volumetric fog's albedo, extinction, reach (`FogViewM`) and
  phase g (`FogPhaseG`), the fog by the hour (`FogHours`, 24 shares: thicker by night), each
  light kind's volumetric scattering (`KindScatter`, by `KindNames`: light shafts from the
  street lights, high masts and floods; none from the neon spill, shop signs and shopfronts),
  the searchlight beams' fog gain (`BeamFogGain`), the live sets (`MaxVolumes` within
  `VolumeRangeM`, plumes within `EmitterRangeM`), cards per plume by kind (`Puffs`,
  `EmitterKinds`) and the engine settings it runs with (`TunedSettings`, "name=value"). With an
  air the import turns the fog and the air on (`bFog`, `bAir`); a plan without one (AT3's)
  keeps the fog off, as before.
- **The runtime** (`ACityGenAtmos`): the height fog follows the hour (its density times
  `FogHours`, its inscattering the night's dark haze or the overcast's grey by the controller's
  `Night`), its volumetric fog to `FogViewM`; every live light scatters in it by its kind's
  share. **Fog volumes:** every 0.2 s the nearest `MaxVolumes` (24; Unreal draws at most 32
  local fog volumes a view, `r.LocalFogVolume.TileMaxInstanceCount`) within `VolumeRangeM` (by
  the distance to their bound) are local fog volume components from a pool: an ellipsoid
  (the component's 5 m unit sphere scaled by the half sizes), radial fog for the volume's
  density less its floor share, height fog for the floor share (mist dense on the water,
  thinning up), its phase g and albedo, each times its schedule's share at the hour (mist
  only after dusk), the farthest fifth fading; by day and by night. **Plumes:** per cell an
  instanced component of cards (`/Engine/BasicShapes/Plane` in `M_CgSteam`), `Puffs` a plume,
  each card's custom data its plume's foot, phase, period (its rise over 1.2 m/s, smoke 2
  m/s), rise, width, opacity (times its schedule at the hour, again when the hour moves a
  tenth) and albedo; the material turns each card to the eye and lifts it along its life
  (rising, slowing, widening, drifting with `MPC_CityGenAtmos`'s `WindMS`), soft and faded in
  and out, lit by the translucency volume (the street's and the neon's colors); culled past
  `EmitterRangeM`. **Searchlights** keep AT2's beams (decision: a beam reaches 400 m into the
  sky, the volumetric fog `FogViewM`; its spot light scatters none), their glow times
  1 + `BeamFogGain` times the fog's share. **Engine settings:** `TunedSettings` applied at begin
  play (each one's value before kept and put back at its end, `CityGenAtmos.Tuned 0`).
- **Assets** (`atmos_assets.py` version 9): `M_CgSteam` beside AT0 to AT3's (under
  `/Game/CityGen/Core/Atmos`, cooked always). The fog volumes are the engine's local fog
  volumes, no asset.
- **Console commands:** `CityGenAtmos.Air [0|1]` (the fog volumes and plumes),
  `.Tuned [0|1]` (the plan's engine settings or the project's), `.VolumeGain G`,
  `.FogView M`; `.Fog` is the height and volumetric fog. `.Status` adds `air`, `volumes`,
  `volumes_live`, `candidates_volumes`, `emitters`, `plume_cards`, `plumes_shown`,
  `fog_share`, `fog_view_m`, `tuned`, `cvars`.
- **The check:** by night the controller's air (the fog on, volumes registered, plumes made)
  is part of the play features' check where the plan has volumes; a `--view` named
  `*_noair` renders with the fog and the air off (a before for a pair), the level's after it;
  the night views log the live fog volumes and plume cards.
- **The benchmark** (`bench.ATMOS_PASSES`): `night_plan_air` (the night as delivered: the
  plan's lights, the fog, the air, the plan's engine settings), `dusk_plan_air`,
  `day_plan_air`, `night_plan_all` (with AT0's rain and wet streets too, since AT4 with the
  air), `night_plan_proto` (AT3's `night_plan_all`: AT0's prototypes, no air, untuned),
  `night_plan_all_untuned`, and the exploring passes `x_*` (`bench._x`: the settings in
  `bench.TUNABLE` set by hand); `ATMOS_OFF` switches the air and the engine settings off too.
  The lean route (`--bench-route lean`, `bench.route(..., lean=True)`, the default with
  `--bench-atmos`, one run unless `--bench-runs`): the first walk, the drive and the flight,
  no teleport, the warm-up passes flying a third of the flight (segment `warm_fly`, group
  `warm`) and the measured passes the rest.

### Visible lights (after AT4)

Swagnik's walk of the packaged Delta (2026-11-12): round a walker every light in a circle was
live, those behind the next block as much as those down the street, and none past 300 m. On
foot the live set is now the lights the walker sees, out to four times the circle's radius;
the fly pawn and the free camera keep the circle.

- **The plan's sight raster** (`atmosgen/sight.py`, the plan's `sight`, `BUILD/atmos/sight.png`):
  the lux check's occluders (`lux.Occluders`: the building masses taken 0.5 m inside their
  footprints and M14's deck slabs, on a 1 m grid) on 2 m cells, a cell blocking the height span
  all four of its 1 m cells block (the lowest top over the highest bottom), so a line of sight
  grazing a facade, or reaching a sign stood 0.9 m off it, stays clear. Red the top (absolute,
  2 m steps rounded down, 0 nothing), green the bottom over the ground (1 m steps rounded up, 0
  on the ground: a slab's underside or a mass over a passage otherwise), blue the ground (M13's,
  the lowest of the cell's corners, 1 m steps; 0 on a flat city); row 0 the north edge. Every
  rounding leans to seeing. Delta's: 1,750 x 1,750 cells, 18% occupied, 182 KB, 145,000 runs.
  The plan's tiers gain `sight_m` (1,200 m, `presets.TIERS["sight"]`) and `sight_max` (512).
- **The exporter** (`unreal_atmos.sight_settings`, in the controller's hash): the raster as
  runs over its rows from the north edge (`sight_runs`: count and value pairs, the value
  red | green << 8 | blue << 16), its bounds in Unreal's frame (cm, Y south: row 0 is the
  minimum Y), cell, size, the channels' steps and the march's skips, the tiers' range and size;
  the importer sets them on the controller (`SightRuns`, `SightBounds`, `SightCellM`,
  `SightWidth`, `SightHeight`, `SightTopStepM`, `SightBottomStepM`, `SightGroundStepM`,
  `SightSkipEyeM`, `SightSkipLightM`, `SightRangeM`, `SightMax`). The manifest's `atmos` names
  the raster (`sight`: size, cell, runs, sha256). **The cells are always loaded**
  (`ATMOS_VERSION` `atmos5`; 518 data actors on Delta, a few MB): a walker's lights reach past
  World Partition's loading range (768 m). The controller makes a cell's beacons, beams and
  plumes only while its middle is within `FixtureRangeM` (832 m: the loading range and half a
  cell) of the view, and drops them a cell past it, as when the cells streamed.
- **The runtime** (`ACityGenAtmos`): the mode is the console variable `CityGenAtmos.Sight`
  (-1, the default: by sight while the player's pawn is the play features' `CityGenWalker`,
  found by its class's name; 0 the circle; 1 by sight whatever the pawn). By sight, every 0.2 s
  a sweep runs on a worker thread (`Async` on the thread pool): the lights on within
  `SightRangeM` (a near-only light within `NearRangeM`) gathered from the cells round the view,
  each tested from the camera at the light and, failing that, where its light lands (a spot
  aimed down: its pool on the ground, at most 0.8 of its reach out; a point: the floor under it;
  a face, an uplight or a flood: a patch along its aim, 6 or 15 m out), so a lamp round a corner
  whose pool shows stays. `FCityGenSight::Visible` walks the 2 m cells the segment crosses in
  plan, the segment's height span in each against the cell's, the eye's own cell, the first
  0.5 m and the last 1 m left out (a camera in a doorway, a light's own wall). A sweep that comes
  back marks what it saw seen now, and a light stays in sight `SightHoldS` (0.6 s) after the
  last sweep that saw it. The street's pool is the `SightMax` seen lights with the smallest
  distance over reach (the nearest, and the ones whose pools reach farthest), the high tier's
  the `MaxHigh` nearest seen high lights (a searchlight first), both out to `SightRangeM`, the
  farthest fifth of it fading; shadows for the nearest `MaxShadowed` seen within `NearRangeM`.
  Until the first sweep after the mode changes, the circle. The play features' light pools
  stand past the live range: 1,200 m by sight (`CityGen.PlayPoolsFromM`), so a lamp within it
  out of sight is dark, pool and all.
- **Fades in time** (both modes): a light joining the live set fades in over `FadeS` (0.5 s),
  one leaving it fades out and goes back to its pool at 0 (it keeps flickering, blinking or
  sweeping while it fades); the fade by distance at the range's edge stays.
- **Console:** `CityGenAtmos.Sight -1|0|1`, `CityGenAtmos.SightRange M [MAX] [FADE_S]`;
  `.Status` adds `sight` (picked by sight now), `sight_wanted`, `sight_raster`, `sight_m`,
  `sight_max`, `sight_seen`, `sight_picked`, `sight_tested`, `sight_rays`, `sight_ms` (the
  last sweep on its thread), `sight_ms_max`, `sight_launch_ms` (gathering it on the game
  thread), `sight_sweeps`, `walker`, `fading`, `fade_s`, `fixture_cells`.
- **The benchmark** (`bench.job`): with atmosgen's passes each segment carries console
  commands its start runs (`commands`, `UCityGenBench::StartSegment`): `CityGenAtmos.Sight 1`
  on the walks, the drive and the teleport (`bench.SIGHT`), 0 on the flights and the warm-up
  (the route moves the walker through the sky as well). The route is unchanged.
- **The check:** a `--view` named `*_sight` renders with the live set by sight, `*_circle` by
  the circle (the same view's before), the pawn's mode after it; their states in the result's
  `sight_views`.
- **The player start** (`unreal.player_start`, `_start_spot`): the fast-travel point nearest
  the city's middle moved to the nearest sidewalk point (sidewalks, promenades, pedestrian
  streets, plazas; every 5 m, within 400 m) that is open (no raised road stretch over 3 m, transit
  deck, tube, beam or canopy, deck slab or skybridge within 10 m) and lit (a street or wall light
  within 20 m), facing along the sidewalk the way that looks more toward the middle (`spot`
  `open_lit`, `moved_m`); where there is none, as before. Delta's start stood under the Industrial
  Port's elevated rail (dark even by day); it is 108 m along the sidewalk past it.

### From AT5: weather

The plan's weather (`docs/atmosgen_scope.md` 6.4, `atmosgen/weather.py`: the plan's
`weather_plan`, `masks` and drip lines) comes with the cells and the controller; AT0's rain
cards and wet decal become the real thing:

- **Packing version 4** (`unreal_atmos.PACK_VERSION`, `CityGenAtmosPack::DripFloats`): a cell
  also holds the drip lines whose middle lies in it (7 floats: the ends' x and y in cm, the
  edge's and the ground's z in cm, the rate plus 8 times the kind's index), the cell actor's
  `DripFloats`; a cell is made wherever any of the four lie. `ATMOS_VERSION` is `atmos6`: an
  import over an earlier level re-packs the cells and sets the controller, and touches nothing
  else but the water master (below).
- **The masks city-wide** (`unreal_atmos.wet_textures`): the plan's 0.5 m tile masks stitched
  at `WET_TEXEL_M` (1 m: a power of two a side, Delta's 4,096, about 22 MB of video memory with
  their mips, against 89 at 0.5 m) into `BUILD/unreal/atmos_wet_cover.png` (grey: the cover,
  the lowest underside of a texel's covered masks where two or more of its four are covered)
  and `atmos_wet_surface.png` (red the gloss when wet, green the puddles, their means; blue the
  drips, their most), written only when their bytes change; the manifest's `atmos.weather`
  names them (`wet`: files, sha256, size, bounds). The import makes them
  `Atmos/T_<City>_WetCover` (uncompressed grayscale: the heights exact) and `_WetSurface`
  (compressed), linear, clamped, never streamed, again only when their bytes change
  (`Importer.atmos_wet`).
- **The controller's weather** (`unreal_atmos.weather_settings`, in its hash): the states
  (`WeatherNames`) and their values (`WeatherValues`, `WEATHER_KEYS` per state: rain, streak,
  drops, wetness, puddles, cloud cover, the fog volumes' gain, gusts, the wind's speed, the
  fog's density, falloff, extinction and albedo), the start state (`WeatherStart`), the rain's
  age (`TransitionS`, `WetS`, `DryS`, `FillS`, `DrainS`), the wind (`WindHeadingDeg`,
  `RainLean`, `GaleMS`), the cover's datum and step (`CoverZ0Cm`, `CoverStepCm`), the textures
  and their bounds (`WetCover`, `WetSurface`, `WetBounds`), what it keeps near the view
  (`MaxSplashes`, `SplashRangeM`, `MaxDrips`, `DripRangeM`, `DripStepM`, `RainCards`). With a
  weather the import turns the rain and the wet streets on (`bRain`, `bWet`): each shows as
  the state has it.
- **States and transitions** (`ACityGenAtmos::SetWeatherState`, `UpdateWeather`): a state
  change blends every value over `TransitionS` (20 s, smoothstep); the fog follows (the
  height fog's density, falloff, volumetric extinction and albedo), the cloud deck's cover (a
  clear night opens it for the moon and the stars; `CityGenAtmos.Cover` holds till the next
  change), the fog volumes' gain (mist and smog thicker in fog and smog), the wind with its
  gusts. The rain's age runs in the runtime's own seconds (`WeatherSpeed` times real time):
  the open surfaces wet toward the state's wetness over `WetS` at full rain (slower in
  drizzle) and dry over `DryS`; the puddles fill over `FillS` and drain over `DrainS`, so a
  clear night after rain keeps its wet streets and puddles a while. Every value goes to
  `MPC_CityGenAtmos` 15 times a second (`Rain`, `Wetness`, `Puddles`, `WindMS` with its gust,
  `WindX` and `WindY` the heading in Unreal's frame, `Streak`, `Drops`), and the wind to
  `MPC_CityGen`'s `Wind` (its speed over `GaleMS`: AG13's grass sways with the weather).
- **Wet streets** (`M_CgWetColor` and `M_CgWetGloss`, two DBuffer decals round the view, 1.2 km
  square, recentred every 100 m, 50 m deep either side of 30 m over the ground under the view):
  per pixel the texel's cover against the pixel's height (under its cover dry: the street under
  a viaduct, the sidewalk under an awning or an overhang; a deck's or a viaduct's top over it
  wet), the face's normal from the depth (its derivatives, turned to the eye: floors full,
  walls `WallShare` 0.35, undersides none), the surface's gloss (asphalt mirrors, grass does
  not, the water none: its own master), the drip band wetter, and the puddle (the texel's
  depth against `Puddles`, its edge broken by a fine noise). The first decal darkens (the
  DBuffer's color: black at an opacity, so a surface is its own color times one less it and
  the lane markings stay, darker); the second makes glossy (roughness and a world-space normal
  at an opacity: wet asphalt 0.16, a puddle a 0.03 mirror) with the rain's rings in the
  puddles and fainter on the wet floor near the eye (`RingM` 30 m). One decal could not do
  both: the DBuffer's color, normal and roughness share one opacity. Past the textures the
  ground is `FarGloss` wet with no shelter or puddle.
- **Rain** (`M_CgRain`): the cards (6,000 within 25 m) cut where the pixel is under its
  texel's cover (`WetCover` on the rain's own instance), the share that falls (`Drops`), the
  streaks' length (`Streak`: drizzle short and slower), each card leaning downwind and
  drifting as it falls (`WindX`, `WindY`, `WindMS`); shown only while the state rains.
- **Splashes** (`M_CgSplash`, `UpdateSplashes`): `MaxSplashes` cards within `SplashRangeM`
  of the view, each at a spot a trace down from 40 m over a random point finds (`ECC_Visibility`,
  the pawn left out; a spot whose surface does not face up has none): the rain's own landing
  spots, so none under a cover and on an awning's top its own; a few re-traced every tick,
  round robin. Each a crown of droplets thrown up over a short life, turned to the eye.
- **Drips** (`M_CgDrip`, `UpdateDrips`): along the plan's drip lines within `DripRangeM`, a
  card every `DripStepM` (jittered and phased by a hash), the nearest `MaxDrips`, again every
  half second once the view has moved 4 m; each a streak falling from the edge to the ground
  under gravity, drifting downwind; dripping while it rains and a while after (the wetness).
- **Rain on the water** (`M_CgWater`, the importer's stage 2 master): rings spreading from
  drops (hashed points in two layers of 35 cm cells) added to its normal by
  `MPC_CityGenAtmos`'s `Rain`, within 40 m of the eye. The master's version tag gains `.rain2`
  (`import_city.master_tag`) where the project has atmosgen's collection, so an import with
  an atmos plan rebuilds the water master alone (its instances and every other master kept).
  atmosgen's assets keep the collection's parameters (their ids) when they add new ones, so
  that reference never goes stale.
- **Masters rebuilt from nothing** (`import_city.clear_material`, `atmos_assets.clear_material`):
  `delete_all_material_expressions` left about half of a material's nodes, so a rebuilt master
  kept its old graph beside its new one; harmless until two Single Layer Water outputs or a
  stale custom node stopped `M_CgWater` and `M_CgLeaves` from compiling (the default material
  in the game). Both now delete until none is left; `M_CgLeaves`' tag is `.still1` (rebuilt once).
- **Wind**: the steam and smoke plumes (`M_CgSteam`) drift along the wind's heading, the rain
  leans in it, the drips drift with it, AG13's grass sways with `MPC_CityGen`'s `Wind`. The trees'
  sway is built into `M_CgLeaves` (`import_city.LEAF_SWAY`, tag `.wind1`) but off: it cost a
  tree-lined street 4.5 ms of GPU a frame (Nanite's voxelized leaves with a world position
  offset). The trees and flags: `docs/progress/AT5`'s open items.
- **Assets** (`atmos_assets.py` version 15): `M_CgWetColor`, `M_CgWetGloss`, `M_CgSplash`,
  `M_CgDrip` and the new `M_CgRain`; AT0's `M_CgWet` is deleted; `MPC_CityGenAtmos` gains
  `Puddles`, `WindX`, `WindY`, `Streak` and `Drops`. All under `/Game/CityGen/Core/Atmos`
  (cooked always).
- **Console commands:** `CityGenAtmos.Weather NAME [now]` (a state, blended or at once; `+`
  and `-` step it), `.WeatherSpeed S` (the rain's age), `.Wetness W [P]` (the wetness and the
  puddles held, for shots; -1 by the age again); `.Rain` and `.Wet` switch the weather's rain
  (streaks, splashes, drips) and the wet streets. `.Status` adds `weather`, `weather_now`
  (`a > b` while it turns), `weather_target`, `transition`, `rain_now`, `drops`, `streak`,
  `wetness`, `puddles`, `wind_ms`, `cloud_cover`, `volume_gain`, `fog_density`, `rain_shown`,
  `wet_shown`, `splashes`, `splashes_live`, `drips`, `drip_lines`, `wet_textures`,
  `weather_speed`.
- **The play features' menu:** with a weather, the Tab menu's AT0 rows (Fog, Rain, Wet
  streets) are one Weather row: the state's name (`a > b` while it turns), its arrows the
  previous and the next state, a click the next (`ClickMenuRow` `weather+`, `weather-`,
  `weather=NAME`, `weather=NAME!` at once; the controller found by its class name, its
  `StepWeather`, `SetWeatherState`, `GetWeatherLabel`); `CityGen.Status` gives `weather`.
- **The check:** by night the controller's weather (its textures set, the start state's rain
  falling and streets wet where it rains); a `--view` named `*__<state>` renders in that state
  settled, `*__<a>2<b>_<n>s` in state a turning to b for n seconds (a frame of the
  transition), the start state again after it; their states in the result's `weather_views`.
- **The benchmark** (`bench.ATMOS_PASSES`): every atmos pass sets a state at once
  (`CityGenAtmos.Weather <state> now`, rain by default, so none leaks into the next);
  `night_plan_all` is the rain (streaks, splashes, drips, the wet streets with their puddles,
  the rain's fog), `night_plan_drizzle`, `night_plan_clear`, `night_plan_fogstate` and
  `night_plan_smog` the other states with everything on.
- **A plan whose weather check failed** is not delivered (`atmos.skipped`); a plan without a
  weather (AT4's) keeps AT0's prototypes' switches and the menu's rows.

### From AT6: looks

The plan's look (`docs/atmosgen_scope.md` 6.5, `atmosgen/look.py`: the plan's `post`) rides
on the controller; the controller's own post-process volume (unbound, priority 50, the one
that holds the exposure since AT3) shows it:

- **The controller's look** (`unreal_atmos.post_settings`, in its hash; no new
  `ATMOS_VERSION`: an import over AT5's level updates the controller and nothing else):
  `PostBase` (the look's night and day sets, `POST_FLOATS` = 20 floats each: bloom, lens
  flares and their threshold, film grain, chromatic aberration and its start, vignette,
  sharpening, the grade's saturation and contrast, the highlights' saturation, the shadows'
  lift, local exposure's shadow and highlight contrast, the shadows' and highlights' gains),
  `PostDistricts` (each district's two sets, in `PostNames` order), the district raster
  (`PostRuns`: [count, index] runs over its rows from the north edge, `PostBounds` in Unreal's
  frame, `PostCellM`, `PostWidth`, `PostHeight`), `PostBlendM` and `PostEaseS`, and the day's
  exposure (`DayEV100`: a clear day's now, replacing the sky's; `OvercastComp`,
  `OvercastTake`, `SkyShare`, `RefCover`); the manifest's `atmos.post` (the districts' count,
  the raster's size and sha256). The air gains `SteamGlow`, `SteamFar`, `SteamFarM`.
- **Runtime** (`ACityGenAtmos::UpdatePost`, every tick): the district raster sampled on a
  5 x 5 grid over a disc `PostBlendM` (90 m) wide round the view, a tent from its middle, a
  few times a second; each district's weight eased toward it over `PostEaseS` (1.5 s); the
  sets blended by those weights and, night against day, by the sky's Night (dusk between);
  written into the volume's settings only when a value moved (`ApplyPostSettings`). One
  volume driven from the view, not a volume per district: AG16 found every enabled volume
  costs the game thread a physics query a frame.
- **Exposure:** still held per hour (AT3, no eye adaptation pumping); by day it moves by
  `OvercastComp` of the light the weather's clouds take off the sun (`OvercastShift`: the
  sun's share less `OvercastTake` past half cover, `SkyShare` of the light kept), so a rainy
  day is a little darker than a clear one, not three stops (AT5's open item).
- **Plumes** (`M_CgSteam`, `atmos_assets.py` version 17): lit by the city by night
  (`MPC_CityGenAtmos`'s `SteamGlow`, the plan's glow times Night) and kept opaque far off
  (`SteamFar` from 30 m to `SteamFarM`); a stall's cooking 6 cards (the plan's `puffs`).
- **The wet decals' face normal** from fine derivatives (`ddx_fine`, `ddy_fine`: a pixel and
  its own neighbor, not its 2 x 2 quad), so a curb's edge is no longer half floor and half
  wall by quads (AT5's white sawtooth along a curb).
- **Console commands:** `CityGenAtmos.Post [0|1]` (the look's post; off: the engine's own,
  the exposure still held), `.PostDistricts [0|1]`, `.PostSet KEY [VALUE]` (a key held over
  every set for the session, `clear` lets them go: art direction), `.DayEV EV`,
  `.SteamGlow G [FAR]`. `.Status` adds `post`, `post_districts`, `post_where` (the district
  with the most weight), `post_bloom`, `post_grain`, `post_fringe`, `post_saturation`,
  `post_contrast`, `post_sharpen` and `overcast_shift`.
- **The check:** by night the look applied (`post`, a district under the view); a `--view`
  named `*_nopost` renders without it (the same view's before); each view's district,
  exposure and post in the result's `post_views`.
- **The benchmark** (`bench.ATMOS_PASSES`): every atmos pass sets `CityGenAtmos.Post 1`
  (so none leaks), `ATMOS_OFF` `Post 0`; `night_plan_nopost` and `day_plan_nopost` without it.

### From AT7: the far city

The plan's far cards (`docs/atmosgen_scope.md` 6.6, `atmosgen/far.py`: the plan's `far`,
`far/<tile>.json`) ride in the cells; the controller draws them past the live set, where a
light is no light at all, so the far city's streets, aviation lights and lit crowns show by
night to the horizon. What glows already (lit windows, signs, neon, LED strips, logos) needs
nothing: the instanced HLODs past World Partition's loading range draw the city's own meshes
and materials with each building's Custom Primitive Data as per-instance data (AG16), so the
far skyline keeps its emissive; and the cloud deck glows from the plan's upward light (AT3).

- **Packing version 5** (`unreal_atmos.PACK_VERSION`, `pack_far`, `CityGenAtmosPack::
  FarFloats`): a cell also holds the far cards whose middle lies in it, 12 floats each (the
  middle in cm; the color times the value: a glow's intensity in cd, a pool's or wash's
  luminance at its middle in nits, the plan's frame; the size in cm: a glow's near size, a
  pool's radius, a wash's half width; a pool's falloff or a wash's half height in cm; a wash's
  yaw; a blink's period, on share and phase) and an int (flags: the type, glow 0, pool 1, wash
  2; the tier << 2, mid 0, high 1, fixture 2; blinking << 4; the schedule << 8), as the cell
  actor's `FarFloats` and `FarInts`; a cell is made wherever any lie. `ATMOS_VERSION` is
  `atmos7`: an import over AT6's level re-packs the cells and sets the controller, and touches
  nothing else. The manifest's `atmos.far` (cards, gain, least width). A plan whose far check
  failed is not delivered.
- **The controller's far city** (`unreal_atmos.far_settings`, in its hash): `bFar`,
  `FarGain` (art direction), `FarPx` (a glow's least width, 2 pixels), `FarFade` (0.2: the
  share of each live range the cards fade in over, as the live lights fade out there),
  `FarSpread` (a glow's gaussian over its square).
- **Runtime** (`ACityGenAtmos::RebuildFar`, `UpdateFarParams`, `UpdateFarLevels`): once the
  cells rest (they are always loaded since the visible lights) every card goes into an
  instanced component per 1 km block, the glows in `M_CgFarGlow`, the pools and washes in
  `M_CgFarFlat`, on the engine's plane (a pool lying on its surface scaled to its disc, a wash
  standing on its facade turned to its yaw), each instance's per-instance data its middle,
  color, size, tier and level; Delta's 22,600 cards in 13 blocks build in about 27 ms. They
  show while the plan's lights do (by night); each instance's level is its schedule's share at
  the hour (set when the hour moves a twentieth of an hour); `MPC_CityGenAtmos` gets
  `FarScale` (the lights' own scale, $2^{EV_{scene} - EV_{plan}}$ times the gains, 0 by day),
  `FarMidM` (the live range now: a walker's 1,200 m by sight, else the circle's 300 m),
  `FarHighM` (the high tier's: 1,200 m by sight, else 750 m), `FarFixM` (the beacons' 832 m
  while they are drawn), `FarFade`, `FarPx` (two pixels' width per distance at the camera's
  field of view and the viewport's width) and `FarSpread`. With the cards on, the play
  features' light pools go (`CityGen.PlayLamps 0` past the live range): the cards are the far
  tier.
- **The materials** (`atmos_assets.py` versions 18 and 19): additive and unlit, on instanced
  static meshes. Each fades in over the farthest `FarFade` of its tier's range ($f = \mathrm{sat}((d -
  S(1 - F)) / (S F))$) and, faded out, off by its schedule or by day, collapses its quad to a
  point by world position offset, so it costs no pixel. `M_CgFarGlow` turns its quad to the eye
  at its middle pulled toward the eye by half its size (clear of its own fixture and wall),
  $s = \max(s_0, d\,p)$ wide, a gaussian $e^{-8r^2}$ whose peak luminance is $I / (0.0982\,s^2)$
  (its intensity held as it grows), blinking from its per-instance data as its light does.
  `M_CgFarFlat` draws a pool's falloff, $L_0 (1 + (r/h)^2)^{-3/2}$ to its radius, or a wash
  soft to its edges, $(1 - u^2)^2 (1 - v^2)^2$ over its half width and height (version 18's
  $(1 - u^4)^2$ a side drew the far crowns as blocks).
- **Console commands:** `CityGenAtmos.Far [0|1]` (off: the play features' light pools past the
  live range, as before AT7), `.FarGain G [PX]`. `.Status` adds `far`, `far_cards`,
  `far_glows`, `far_flats`, `far_blocks`, `far_shown`, `far_build_ms`, `far_px`, `far_gain`,
  `far_mid_m`, `far_high_m`, `far_fix_m`.
- **The check:** by night every card drawn and shown, none by day; a `--view` named `*_nofar`
  renders without them (the same view's before); each view's far city in the result's
  `far_views`. `CITYGEN_UE_VIEW_RES` sets the play views' size (`HighResShot`, 1920x1080 by
  default; 7680x4320 for an 8K shot, the copy waiting until the file stops growing).
- **The benchmark** (`bench.ATMOS_PASSES`): every atmos pass sets `CityGenAtmos.Far 1` (so
  none leaks), `ATMOS_OFF` `Far 0`; `night_plan_nofar` without them (the play features' pools
  instead: what the cards cost).

### The lights' fixtures (dlss_lamps_flicker)

Swagnik, walking Delta: "quite a few ghost lamps, ie the light is there but theres no
lamppost there". AT1's and AT2's lights on fixtures they asked of stage 2 (a junction's corner
poles, the signals' mast arms, highway and ramp columns, service road, pedestrian street and
footbridge posts, alley wall packs, high masts, crown floods out from their facades) had none
drawn. The atmos plan now draws one under each from AG8's own prop variants, in the
district's style (`atmosgen/fixtures.py`): a street light at the pole's foot, its arm toward
the head (a mast arm: at its signal's foot, reaching over the junction), a wall light on the
facade behind an alley's wall pack (else a post just off the alley), AG8's heavy mast form
for a high mast, a flood head (tilted up) on its setback or on an outrigger (AG8's bracket)
from its facade. Each light moves onto its fixture's lens; a fixture keeps off carriageways,
junctions and crosswalks as AG8's props do. The plan's `fixtures.json` lists them and its
`unreal_contribution.fixtures.json` places them: an entry per 128 m cell
(`atmos.fixtures.<tile>.<quarter>`, kind `prop.fixture`) whose instanced parts are AG8's
variant nodes in AG8's `props` part, so the exporter imports AG8's meshes and materials once
for both. `citygen unreal` layers it with stage 2's contributions where the plan is delivered
(`unreal_atmos.fixtures_contribution`; a plan whose new fixtures check fails is not), so it
needs stage 2's props (AG8) in the build; a blockout import has no fixtures. The plan's
`checks.fixtures` holds every light to something at its height: stage 2's own fixture, its
fixture's lens, a structure (roof, facade, crane, station roof or deck slab) or the ground.

### Steam and smoke off by default (cars_steam, issue #223)

AT4's steam and smoke plumes (manholes, drains, vents, food stalls, chimneys) are off until
they look real: the atmos spec's `steam` (default false, `presets.STEAM_ON`) is the plan's
`air.steam` and the controller's `bSteam` (set by the import); the plan places the emitters
either way. In the game the Tab menu's **Steam and smoke** row (shown when the controller has
`bSteam`) and `CityGenAtmos.Steam [0|1]` switch them (`ACityGenAtmos::SetSteam`); the fog
volumes stay with `CityGenAtmos.Air`. The menu's **Clothing** row, under it, switches
lifegen's people's clothes (`CityGenLife.Clothing`, "From LG3: crowds on the streets").

### A packaged game

A project a city was imported into packages as any Unreal project (UAT's `BuildCookRun`,
for example Development Win64 with `-cook -stage -pak -archive` and `-map=` the city's
level). **A smoke or test launch of a package leaves no `Saved/` folder in it:** launch it
with `-userdir=` a folder outside the package, or delete `<archive>/Windows/<Project>/Saved`
after the run. A run's `Saved/Config/Windows/GameUserSettings.ini` keeps its window size
(the play fixes' smoke run at `-ResX=1920 -ResY=1080` left 1920 x 1080 there), and the
native start below then never applies for the player who opens it next. Three fixes made Delta Megacity's packaged game (after AT1) play as the editor's
`-game` does:

- **What the runtimes load by path is cooked.** A cook takes only what the maps reference.
  The atmos controller loads `MPC_CityGenAtmos`, `M_CgRain` and `M_CgWet` by path (and the
  rain cards' `/Engine/BasicShapes/Plane`), so the packaged game logged "SkipPackage ... does
  not exist" and `CityGenAtmos.Rain` and `.Wet` did nothing. Every import writes
  `unreal.ALWAYS_COOK` (`/Game/CityGen/Core/Atmos`, `/Engine/BasicShapes`) as
  `+DirectoriesToAlwaysCook` in the project's `Config/DefaultGame.ini`
  (`[/Script/UnrealEd.ProjectPackagingSettings]`; `unreal.set_project_ini`, the section's
  other lines kept). Whatever a runtime loads by path belongs in one of those folders (a
  test reads the plugins' sources for `/Game` and `/Engine` paths); the rest of
  `/Game/CityGen/Core` (the masters, `MPC_CityGen`, the textures) the level references
  through its materials and the play actor. CityGenPlay loads nothing by path.
- **The monitor's native resolution.** The game is DPI-aware (AT1, above), but a game with no
  saved settings picks its window before that, from the desktop as a DPI-unaware process
  sees it: 2048 x 1152 on a 1440p screen at 125%. At game start (not in the editor), once the
  engine is up, the play plugin's module sets windowed fullscreen at the primary monitor's
  native resolution (`FCityGenPlayModule`, `NativeResolution`), unless the player's saved
  `GameUserSettings.ini` has a resolution or the command line sets the window (`-ResX`,
  `-ResY`, `-windowed`, `-fullscreen`, the benchmark's `-CityGenBench=`). It saves nothing,
  so every start does the same; Unreal's automatic screen percentage is left as it is. The
  log says `CityGen play: window 2048x1152 -> 2560x1440 windowed fullscreen`.
- **Weather in the developer menu.** With an atmos controller in the level, the Tab menu has
  rows for AT0's prototypes, Fog, Rain and Wet streets (the controller's `SetFog`,
  `SetRain`, `SetWet`), and the hour (`SetHour`, a step of an hour: the schedules of its
  lights and the windows by night). The play features find the controller by its class name
  and drive it through its UFUNCTIONs and properties (`ACityGenPlay::GetAtmos`,
  `SetAtmosFlag`, `SetAtmosHour`), so CityGenPlay does not link CityGenAtmos; without a
  controller the rows are hidden. Every row's click is `ACityGenPlay::ClickMenuRow(row)`
  (`night`, `freecam`, `minimap`, `messages`, `fog`, `rain`, `wet`, `hour+`, `hour-`),
  also the console's `CityGen.MenuRow ROW`, so a script or the benchmark's pass commands
  drive the menu as a click does; `CityGen.Status` gives `atmos`, `fog`, `rain`, `wet` and
  `hour`. AT5's weather row replaces the Fog, Rain and Wet streets rows where the plan has a
  weather ("From AT5" above).

## AG18's vehicles

AG18's hero vehicles come into Unreal as a library of their game packs (the contract in
`vehicles/GAME.md`), imported once a project and shared by every city, and placed by entries
of layer 2 (`citygen/unreal_vehicles.py` on the venv side; `Importer.vehicles`,
`Importer.vehicle_actors` and the masters in `citygen/ue/import_city.py`).

**The library.** A folder of packs, one per car (`<car>/pack.json`, `lod0.glb` to `lod3.glb`,
`collision.glb`, five textures per baked slot): by default the packs' cache
`~/.cache/cybergen/vehicles/game`, else `$CITYGEN_VEHICLES` or `citygen unreal --vehicles DIR`.
A machine that has not built the packs fetches them from the repo's release with
`python vehicles/packs.py fetch` (`vehicles/GAME.md`, "Sharing packs between machines").
`--all-vehicles` imports every car of it, placed or not; otherwise only the cars the
placements name. What a pack must hold: `pack.json` of format `cybergen.vehicle_pack` version
1 with four LODs, the files it names (`read_pack` refuses a pack missing one), parts with
their pivots, the `body` slot's five textures (and the `wheels` slot's unless it is a hover
car, whose `wheels` is null), the glass parameters, the show colors, `dimensions`, and the
hulls in `collision.glb` as `UCX_body_<nn>` nodes.

**The manifest's `vehicles`** (only when a contribution places a vehicle, or with
`--all-vehicles`; a city without either exports byte for byte as before): `library`,
`folder` (`/Game/CityGen/Vehicles`), `paint_cpd` (9), per car (`cars`) its title, kind, size
class, folder, the pack's directory, every file's sha256, its textures (slot, map, sRGB,
kind), LODs (file, triangles per part, `screen_size`, whether the file carries tangents),
parts (kind, pivot, material, a wheel's radius, side, axle, `steers`, `spins`,
`uv_shared_with`), the body and wheels slots' parameters, the glass parameters, the show
colors, `emissive_strength`, `micro_detail`, `dimensions` and the hulls (read from
`collision.glb`, welded by position, in the car's frame: vertices and triangles), and a
`hash` of all that and the import's version (not of the folder it was read from); the
placements with their hashes, the keys they replace (`replaced`) and counts. `actor_hashes`,
`actor_kinds` (`vehicles`) and `manifest_changes` take each placement as an actor, a
replaced key as gone.

**The placement format** (any `unreal_contribution.*.json`, an entry of kind `vehicles`; the
other entries of its file go to stage 2 as before, a file of placements alone does not reach
stage 2):

```json
{"key": "vehicles.parked.t+01+00", "kind": "vehicles", "hash": "<16 hex>",
 "tile": "t+01+00", "pivot": [384.0, 128.0, 0.0], "replaces": ["prop.parked_car.t+01+00"],
 "vehicles": [{"car": "tanager_mino", "id": "d03.prop.parked_car.e372n168",
               "xform": [-12.4, 40.1, 0.0, 87.5],
               "paint": [[0.7, 0.05, 0.03], [0.8, 0.78, 0.72], [0.95, 0.62, 0.03]],
               "steer_deg": 0.0}]}
```

`xform` is x, y, z (meters) and yaw (degrees) from the entry's pivot in citygen's frame, the
car's x forward; `paint` the primary, secondary and accent colors, linear, in the pack's
channels (left out: the pack's show colors); `steer_deg` turns the wheels and brakes that
steer about their own z; `id` the vehicle's citygen id. A key may not be another actor's;
`replaces` drops the actors of those keys (M15's parked car prototypes, AG8's variants).

**What the importer makes of a car** (`/Game/CityGen/Vehicles/<car>`, made again only when its
hash changes, by `VEHICLE_MESH_VERSION` or the masters' `VEHICLE_VERSION`):

- **Textures** `Textures/T_<car>_<slot>_<map>`: base color and emissive sRGB (default
  compression; the emissive's alpha is the specular level), the normal map linear with its
  green channel flipped (the packs' are OpenGL's), ORM and mask linear in BC7 (both alphas
  are data: the clear coat weight, the shade on the paint); texture group Vehicle.
- **Meshes** `SM_<car>_<part>`, one per part (`body`, `glass`, `wheel_<tag>`, `brake_<tag>`),
  each the pack's LOD0 node with LOD1 to LOD3 from the other files as its engine LODs (screen
  sizes 1.0, 0.35, 0.15, 0.05: LOD0 within about 8 m of a standard car, LOD3 past about 60 m;
  a large vehicle's bigger bounds switch farther out), imported through Interchange in the
  node's frame (a wheel's origin is its axle's middle, so it spins about its local y and
  steers about its local z; a brake shares its wheel's pivot), the pack's normals kept, UVs at
  full precision (half floats are off by up to two texels of the 4,096 atlas), tangents
  computed by Unreal (MikkTSpace on the file's normals and UVs, as the bake's). **No Nanite**:
  the glass is translucent (Nanite draws no translucency), the LODs are the pack's own (the
  glass dark and opaque from `opaque_from_lod`, LOD3's remade wheels with their rim faces),
  which Nanite would replace with its own clusters, and the Mac's editor renders with Nanite
  off (a Nanite mesh draws its coarse fallback). The glass mesh has a second slot,
  `MI_<car>_glass_dark`, that its LODs from `opaque_from_lod` draw with. The body's simple
  collision is the pack's hulls, one convex element each (GeometryScript), used for complex
  traces too; wheels, brakes and glass have none (wheels are the engine's raycasts). Each
  mesh carries `cg.hash`, `cg.car`, `cg.part`, `cg.kind` and `cg.pivot` (its pivot in the car's
  frame, JSON) as metadata. The LOD source meshes are deleted once the chains are made.
- **`/Game/CityGen/Core/M_CgVehicle`** (body and wheels; an instance a car and slot,
  `Materials/MI_<car>_<slot>`): the contract's albedo,
  $\text{base}\,(1 - w) + (R\,P_1 + G\,P_2 + B\,P_3)\,A$ with $w = R + G + B$ from the mask and
  `Paint1` to `Paint3` (vector parameters on Custom Primitive Data 0, 3 and 6, each read
  through a per-instance custom data node with the parameter as its default, AG16's
  `per_instance`; the instance's defaults are the pack's show colors), roughness, metallic
  and occlusion from ORM, shading model Clear Coat with ORM's alpha as the coat and
  `CoatRoughness` the pack's `coat_roughness` (through material attributes: the clear coat
  inputs are not material properties Python can connect), specular from the emissive's
  alpha, the normal map, the paint's flake (the contract's `micro_detail`: 2,600 cells a meter,
  a hashed tilt of 0.06 on the painted share in the mesh's own space, faded out by 3 m),
  emission $E \cdot S / 15 \cdot \mathrm{lerp}(\text{GlowDay}, \text{GlowNight}, \text{Night})$
  with $S$ the pack's `emissive_strength` (`EmissiveStrength`), `GlowDay` 8 and `GlowNight` 2
  (`MPC_CityGen`'s Night, as the other emissive masters: the night's fixed exposure).
- **`M_CgVehicleGlass`** (`MI_<car>_glass`): thin translucent (Surface per-pixel lighting),
  black with a coverage of the share the glass does not transmit (the pack's transmission
  times `TransmissionScale` 0.65, plus 4%), more toward grazing angles (`GrazingCover` 0.6
  of $(1 - N \cdot V)^4$), its specular from the IOR but at least `MinF0` 6% (a coated
  glass: the domes' IOR of 1.12 to 1.14 reflected almost nothing), its roughness, and the
  glass color pulled toward a dark teal (`GlassTint`, `TintMix` 0.6) and squared as the
  transmittance (the packs' glass is thick: two sheets a few mm apart, and the proof's ray
  is tinted at both). The material is two-sided. A face is left out when, its normal turned
  outward from `GlassCenter` (the middle of the car's box, set per car), the eye is behind
  it: from outside that is the far side's glass seen through the near side, drawn in the
  same mesh in triangle order, not by depth, which composited over the near glass in black
  and bright patches. Before the play fixes the test was the normal pointing toward
  `GlassCenter` on a one-sided material, so glass that is one sheet facing in (the
  Tanager Cab's front side windows) drew no glass at all from outside: its near faces were culled and its far
  faces left out. From inside the cabin every face is drawn, while the eye is inside the
  cabin's box (`CabinCenter`, `CabinHalf`, set per car: the glass's own box from the pack's
  LOD0, the record's `glass_box`, taken down to the car's floor; the eye in the mesh's own
  space is the pixel's local position plus the way to the camera turned as the normal is); a
  record without a glass box never counts the eye inside. Since the play fixes (2026-11-12;
  `VEHICLE_VERSION` 10) the glass reads as glass: the cabin is a dim shape behind
  reflections, the shading model's own Fresnel darkening and mirroring it toward grazing
  angles.
  **`M_CgVehicleGlassDark`** (`MI_<car>_glass_dark`): opaque, the glass
  color times 0.06, as the proof draws LOD2 and LOD3.

**What the importer makes of a placement**: a `BP_CityGenGroup` actor at the entry's pivot
(key the entry's, `cg.type=vehicles`, `cg.category=vehicle`, `cg.tile=`, `cg.id=` per vehicle,
`cg.vehicle=` per model; folder `CityGen/vehicle`) holding, per model and part, a hierarchical
instanced static mesh component (`cg.member`, `cg.key=<entry>.<car>.<part>`, `cg.vehicle=`,
`cg.part=`, `cg.id=` per vehicle in instance order) with an instance per vehicle (its transform
composed with the part's pivot; a steering wheel turned by `steer_deg`) and nine floats of
per-instance custom data (the paint): a tile's parked cars of one model are one component a
part. The body collides (`BlockAll`), the rest not; the glass casts no shadow (each sheet of the
thick glass shadowed the other in blocky patches). A car made again in an import updates the
placements that show it. A later stage that moves a vehicle places one static mesh component
per part instead, with the paint as its Custom Primitive Data 0 to 8 (the masters read it
there when there is no per-instance data) and the glass's Cast Shadow off.

**Parked in the cities (AG18 step H).** assetgen's parked vehicles stage (`assetgen vehicles`,
in `assetgen build` after the props; `assetgen/parked/`) writes
`BUILD/assets/unreal_contribution.vehicles.json`: a placement entry per tile in which AG8
draws parked cars (`vehicles.parked.<tile>`), replacing AG8's entry of that tile
(`prop.parked_vehicle.<tile>`, also M15's prototype actor's key), with the `library` it drew on
and the cars it placed (`cars`: title, kind, the sha256 of each `pack.json`). The exporter
leaves the stage 2 entries a placement replaces out of stage 2
(`unreal_vehicles.without_replaced`), so AG8's variants go with the blockout's prototype; and
when neither `--vehicles` nor `$CITYGEN_VEHICLES` names a library it reads the one the
placements' contribution names, where that folder is there (`named_library`), else the packs'
cache. A build without the vehicle library on its machine (or with the asset spec's
`vehicles.parked` set to `variants`) has no such file and exports exactly as before. AG16's
scene count (`assetgen/scene.py`) adds a placement's actor, its components (one per model and
part) and instances (one per vehicle and part) to its tile, and the city's `vehicles` (cars,
models, components, instances, meshes, triangles at LOD0); the vehicles' meshes are not
Nanite, so they take no root pages. Results: `docs/progress/AG18/city/`.

**The check** (`citygen unreal BUILD UPROJECT --check-vehicles [--shots DIR]`,
`unreal_vehicles.check`, `citygen/ue/check_vehicles.py` in the full editor): each mesh's LOD
count and triangles against the pack (Unreal's build drops a few degenerate triangles: within
2%), no Nanite, the glass's dark slot from `opaque_from_lod`, the hulls; each placement's
components, instance counts, ids and every instance at its pivot (1 cm); traces down and across
onto every placed body, hitting it and never a wheel or the glass; a wheel spun and steered by
script about its pivot; with `--shots`, by day and by night, each car from its pack's hero
camera (the proof's), one car at each LOD forced, the wheel turned, the hulls in place of a
body, and the line-up of the AG18 check where the build has one. Results and shots:
`docs/progress/AG18/unreal/`.

## lifegen's runtime (LG0)

Stage 4's plan (`lifegen plan BUILD`, `BUILD/life/`, or `citygen unreal --life DIR`) is layer 4
of the manifest, its `life`: one actor, the `CityGenLife` controller (key `life`, class
`CityGenLife`, always loaded, folder `CityGen/Life`), placed by the import with the plan's
spike packed in `BUILD/unreal/life.json` (`citygen/unreal_life.py`). A plan whose checks
failed is named (`life.skipped`) and left out; `--no-life` leaves it out (its actor from an
earlier import goes); a build without a plan gets no section and exports as before.

**The plugin** (`citygen/ue/CityGenLife`, C++, built by UnrealBuildTool in the same run as
`CityGenPlay` and `CityGenAtmos`: `unreal_play.PLUGINS`, one stamp for the three; it enables
the engine's ZoneGraph plugin and uses the engine's Mass modules, so the project needs no
MassGameplay plugin). At BeginPlay the controller:

- builds **ZoneGraph lanes from the city's graphs**: an `AZoneGraphData` of its own
  (transient, registered with the world's ZoneGraph subsystem) whose storage it fills from
  the packed lanes, one zone and one lane per walkway (tag bit 1, walked both ways: a link is
  Outgoing where the other walkway meets this one's end, Incoming at its start) and per lane
  or junction connector of the lane graph (tag bit 2, directed: successors Outgoing,
  predecessors Incoming), points, tangents, up vectors, progressions and the zones' BV-tree
  (built in the plugin: `FZoneGraphBVTree::Build` is not exported from the module in 5.8). No
  hand-drawn shapes;
- makes the spike's **people and cars Mass entities** of the world's entity manager (one
  fragment each, `FCgLifeWalker`, `FCgLifeCar`) and runs two dynamic Mass processors every
  tick (`UCityGenLifeWalkProcessor`: along a walkway lane at the person's pace and side,
  onto a linked walkway at its end, back at a dead end or the live region's edge;
  `UCityGenLifeDriveProcessor`: along the lane graph at a cruise speed, slowing behind the car
  ahead on its lane and its next one, a car meeting the region's edge or a dead end started
  again on a lane of the region);
- draws them as **instanced static meshes** updated every frame: the stand-ins a body and a
  head (`/Engine/BasicShapes` cylinder and sphere) in `/Game/CityGen/Core/Life/M_CgLifeStandIn`
  (base color from per-instance custom data: the person's style's color, a skin tone), the
  cars every part of AG18's packs already in the project (`/Game/CityGen/Vehicles/<car>/
  SM_<car>_<part>`, the parked cars' meshes and materials, paint in nine floats of
  per-instance custom data as the parked cars', glass and wheels casting no shadow);
- finds the ground under 96 entities a frame (a line trace each, round robin: curbs, decks
  and terrain);
- keeps its instanced people and cars **out of Lumen's scene and the distance fields**
  (`bInLumen` false: they take Lumen's light but give none back, as characters in games) and
  moves them through the components' instance data without recreating their render state
  each frame (`bRebuildRenderState` false). The spike measured both: recreating the render
  state every frame put the moving instances through Lumen's scene update, 9 ms of GPU a
  frame walking among them (`docs/progress/LG0/README.md`).

Every reference (meshes, material) is a property of the actor, so a cook takes them.

| Property (set by the import) | What |
|---|---|
| `City`, `PlanHash`, `DistrictId` | the plan |
| `People`, `Cars`, `Center`, `RadiusM` | the spike's counts, its middle (citygen m) and live radius |
| `WalkSpeed`, `DriveSpeed`, `CarGapM` | m/s ranges, the gap kept behind a car |
| `WalkPoints`, `WalkStarts`, `WalkWidths`, `WalkLinks`, `WalkLinkStarts` | the walkway lanes (flat, citygen m; a link `2 * lane + 1` at this lane's end) |
| `DrivePoints`, `DriveStarts`, `DriveWidths`, `DriveLinks`, `DriveLinkStarts`, `DriveStartable` | the drive lanes, successors, which a car may start on |
| `DriveVmax`, `DriveCruise`, `DriveVary` | (cars_steam) each drive lane point's speed (m/s), each lane's cruise speed, a car's share of it |
| `BodyMesh`, `HeadMesh`, `StandInMaterial`, `Palette` | the stand-ins |
| `CarPartMeshes`, `CarPartModels`, `CarPartPivots`, `CarPartShadows`, `CarModels`, `CarPaints`, `PaintFloats` | the cars |

Console commands: `CityGenLife.Enable [0|1]`, `CityGenLife.Shadows [0|1]`,
`CityGenLife.Lumen [0|1]`, `CityGenLife.Rebuild [0|1]`, `CityGenLife.Respawn PEOPLE CARS`,
`CityGenLife.Status` (one JSON line, `CITYGEN_LIFE_STATUS`, also logged at the 300th tick and
every 6,000th: lanes, entities, people placed, instances drawn, the first person's and car's
places, the actor's game thread time per frame, mean and most). The benchmark's `night_life*`
passes (`bench.LIFE_PASSES`, with `--bench-atmos`) switch them over the night as delivered. The import's summary line says what it placed
(`Life (stage 4): ...`) and `import_result.json`'s `life` the lanes, models and any car mesh
missing from the project. LG0's spike and its cost: `docs/progress/LG0/README.md`.

### Cars by road class, on smooth lanes (cars_steam)

`citygen/unreal_life.py` (`PACK_VERSION` 2) packs every drive lane as a smooth curve and its
speeds:

- **Smooth lanes** (`smooth`): a centripetal Catmull-Rom spline through the lane's points,
  sampled at most `SMOOTH_STEP_M` 1.5 m apart, every original point kept, the neighbor lanes'
  points past its ends as the spline's end controls (so a connector leaves and joins its roads
  on their tangents); a run turning under `SMOOTH_TURN_DEG` at both ends stays a chord, and z
  follows the chord (the spline is for the plan's turns, not the grade). The runtime's ZoneGraph
  lanes take these points; a car's heading is the lane's tangent interpolated between points
  (`FZoneGraphLaneLocation::Tangent`), not its segment's, so it turns as it moves.
- **Speeds** (the life plan's `spike.drive_speeds`, `drive`, `road_classes`, from
  `lifegen/presets.py` `DRIVE_SPEEDS` and `DRIVE`): a lane's cruise speed by its road's class
  (highway 22, avenue 14, street 9.5, service 7, alley 4.5 m/s: 80, 50, 35, 25 and 15 km/h);
  a junction connector `junction` (0.7) of its slower road's; at each point at most
  $\sqrt{a_{lat} R}$ ($a_{lat}$ = `lateral`, 2 m/s$^2$; $R$ from the turn at the point), never
  under `crawl` (2 m/s, a turning bulb's hairpin); a lane's end at most its successors'
  starts, braking back from every slow point at `brake` (2.5 m/s$^2$). Each car drives at its
  own share of that (`vary`, 0.9 to 1.08), the lowest speed from where it is to a few meters
  on (`CgLife::SpeedAhead`), still slowing behind the car ahead as in LG0. A plan before
  cars_steam (no speeds) drives at LG0's `DriveSpeed`.
- **The roads' own curves** were as coarse as M22's pavement map and AG17 drew them (a bend's
  few stations), so on a tight bend a car's line and the asphalt's polygon could part by a few
  centimeters (`docs/progress/cars_steam/README.md`). Since the road curves fix the roads
  are arcs within 2 cm of chord sag, their local corners rounded on arcs, and the lanes built
  on them follow (`docs/progress/fix_road_curves/README.md`). No exporter change.

### From LG1: people

`citygen unreal BUILD UPROJECT --people [--gas UPROJECT]` makes lifegen's **people library** in
the project before the import (`citygen/unreal_people.py`, `ensure_library`), and the life
controller draws the spike's people from it in place of LG0's stand-ins. MetaHumans, their
assets and Epic's animations are made or copied into the project only, never the repo
(decision 5); the repo holds the scripts, the seeds and the plan.

- **The library's spec** (`lifegen/library.py`): `CHARACTERS` (24) characters, each a
  MetaHuman from the engine's presets (MetaHumanCharacter's optional content): its first
  preset duplicated (its hair, eyebrows and plain wardrobe kept), its face model's
  coefficients blended toward a second preset of the same body (`FACE_BLEND`), its height and
  build (`HEIGHT`, `BUILD`: the creator's body constraints), its skin tone (`SKIN_U`,
  `SKIN_V`); the clips (`CLIPS`: two walks, two idles of Epic's Game Animation Sample); the far
  stand-ins (`FAR_LOD`, `FAR_FPS`, `IMPOSTOR_*`); the runtime's tiers (`TIERS`). Its hash
  (`library_hash`: the spec, `CODE_FILES`, the engine's version) names the cache.
- **The build** (`citygen/ue/people_library.py`, in the project's full editor off screen:
  the creator's assembly bakes its textures through texture graphs, which a commandlet does
  not run; `-NoMetaHumanAccountPortalLoginFallback`, so no sign-in ever opens):
  1. *characters*: made by script (`MetaHumanCharacterEditorSubsystem`), rigged (joints only)
     and given their skin's texture sources (2k) by Epic's MetaHuman cloud service on the
     editor's saved sign-in, assembled by the creator's Optimized build at Medium
     (`/Game/CityGen/People/Built/<id>`: body 3 LODs, face 3, outfit 4, groom cards and
     helmets);
  2. *clips*: the sample's walks and idles, copied into the project first (below), retargeted
     onto each body skeleton by IK Rig's batch retarget (rigs generated by script, the pelvis
     the retarget root), notifies stripped, made in place (`in_place`: the root still, the
     pelvis taking the root's height, the travel dropped), each walk's speed measured from the
     sample's root motion;
  3. *mid*: the character as one static mesh (body and face at LOD 1 less the face's
     see-through shells and eyelashes, `SHELLS`; outfit LOD 2; the hair's helmet;
     GeometryScript, `assemble_static`), its first walk baked into bone textures by
     AnimToTexture (bone mode, 16 bits, four influences, the body as the driver, four triangles
     a vertex, 15 fps), each slot on `People/Materials/M_CgPersonMid` (the slot's base color
     as a plain 512 px copy of the creator's virtual texture, `mid_texture`, and its tint: the
     baked skin's `Basecolor Baked`, a hair color by the character on the helmet's slots, the
     garments white with `UseInstanceTint` 1, so each person's outfit tint from per-instance
     custom data 4 to 6 colors them; AnimToTexture's `MF_BoneAnimation`, auto play from
     per-instance custom data 0 to 3);
  4. *far*: an impostor sheet (`People/Far/T_<id>_Sheet`, 8 views round the person by 8 frames
     of one stride, 128 x 256 a cell) and its coverage (`T_<id>_Mask`), drawn by orthographic
     scene captures of the mid mesh pinned to each frame (`MI_<id>_Pose_<i>`: auto play off,
     the frame a parameter): the color lit by a light turned with the camera, the coverage
     with lighting off; on `People/Materials/M_CgPersonCard_<hash>` (a new material per
     library; its samplers' gamma that of the sheets; world position offset turning
     `/Engine/BasicShapes/Plane` to the view about its up axis, the cell by the view's side of
     the person and the walk's frame, masked by the coverage, the garments' white tinted by
     the person's tint from per-instance custom data 2 to 4);
  5. *manifest*: `Saved/CityGenPeople/library.json` (per character its near meshes and hair,
     mid mesh and frames, card material; the clips per body skeleton).
- **Epic's animations** (`migrate`): the clips' hard references in the user's Game Animation
  Sample (`citygen/ue/people_gas.py`, its editor run read only with `-userdir=` outside it;
  the clips' notify Blueprints and pose search databases left behind) copied into the
  project at their own paths (`/Game/Characters/UEFN_Mannequin/...`).
- **The cache** (`~/.cache/cybergen/people/<hash>/`, or `$CITYGEN_PEOPLE_CACHE`): the built
  library's assets but the MetaHuman Character sources (`CACHE_SKIP`) and its manifest. A
  project whose stamp (`Saved/CityGenPeople.stamp`) names the hash has the library; another
  gets it copied from the cache; only a library never built needs the sample and the cloud.
  The plugins it needs are enabled in the project (`unreal_people.PLUGINS`: MetaHumanCharacter,
  AnimToTexture, IKRig, HairStrands, RigLogic, GeometryScripting).
- **The manifest's `life`** (`unreal_life.persons`, `people_library`; the controller's
  properties): each person's draws from the plan (`PersonChar`, `PersonScale`, `PersonGait`,
  `PersonPace`, `PersonTint`, `PersonSeed`) and the library's assets (`NearMeshes`,
  `NearMeshStarts`, `NearHair`, `CharClipGroup`, `Gaits`, `WalkClips`, `WalkClipSpeeds`,
  `IdleClips`, `MidMeshes`, `MidFrames`, `CardMesh`, `CardMaterials`, the tiers `NearM`,
  `NearMax`, `MidM`, `FarM`); without a library (or a library of another size than the plan
  draws from) the stand-ins, said in `life.library`. `LIFE_VERSION` life2.
- **The runtime** (`CityGenLifePeople.cpp`): every person stays a Mass entity on its walkway
  lane (LG0's walk processor, at the person's pace); each frame it is drawn by its distance
  from the view: the `NearMax` nearest within `NearM` as a pooled slot of skeletal mesh
  components (the body leading the face and outfit, the groom's cards on the face's head bone
  at the bone's reference pose; the gait's clip in single node mode at pace over the clip's
  speed; the pose ticked only when rendered, update rate optimizations, no post-process
  Blueprints; the outfit's garment materials as dynamic instances with the person's tint in
  `diffuse_color_1`), a slot keeping its person out to 1.15 `NearM`; within `MidM` an
  instance of the character's mid mesh (one instanced component per character; custom data:
  time offset, play rate, first and last frame, tint), within `FarM` an instance of its card
  (custom data: time offset, strides a second, tint); the walk keeps its phase from tier to
  tier. None of them in
  Lumen's scene or the distance fields. Console `CityGenLife.Tiers NEAR_M NEAR_MAX MID_M
  FAR_M`; `CityGenLife.Status` adds `library` (characters, how many near, mid and far now,
  slots, the game thread's time drawing them). The benchmark's `night_life_near0` and
  `night_life_near80` passes; every life pass sets the tiers.

### From LG3: crowds on the streets

A life plan with a `crowd` (`lifegen plan` since LG3) replaces the spike's people with the
city's crowd: every walkway of the city, every kind and level, at its street's density by hour,
simulated only round the view (`citygen/unreal_life.py` `pack_crowd`, `PACK_VERSION` 3;
`import_city.crowd_props`, `LIFE_VERSION` life3; `CityGenLifeCrowd.cpp`). The spike keeps its
drive lanes and cars until LG5. A plan before LG3 packs and walks LG1's spike as before.

- **The pack** (`BUILD/unreal/life.json`, the controller's properties): the whole walkway graph
  as lanes (`pack_walks`, LG0's links); per walkway its kind (`WalkKinds`, lifegen's
  `WALK_KIND_CODES`), district (`WalkDistrict`), people per hour band (`WalkPeople`, 5 a
  walkway: M11's band densities, the district's busy and the crowd's scale in) and signal
  window (`WalkSignal`, an index into `SignalWindows`: cycle, offset, walk from, walk to, s);
  per district its day (`DistrictShape`, 24 floats), danger (`DistrictDanger`) and clothes'
  colors (`DistrictPalettes`, `PaletteSize` linear RGB colors); the doors (`DoorLanes`,
  `DoorDistsM`, `DoorPoints`, `DoorRates`: every spawn point of the plan, AG3's doors, station
  stairs, garages and taxi stands, on its walkway at its distance along it, its people a hour
  out at the crowd's hour); the pool (`People` its size, `PersonChar` ... as LG1's, its tint
  an index into its district's palette, `PersonTintIndex`); the settings (`Hour`, `LiveM`,
  `TripS`, `GroupShares`, `GroupGapM`, `Jaywalk`, `ReachM`, `PersonalM`, `PlayerM`, `AvoidM`,
  `StairsShare`, `Escalator`, `ElevatorMS`). The import's `life.crowd` says the doors,
  signals, hour and pool.
- **Live round the view** (`UpdateLive`, every 0.25 s): a walkway within `LiveM` (340 m, 3D,
  from its bounding box) of the view is live; one coming alive gets its people at the hour
  (`WalkPeople` of the hour's band times its district's `DistrictShape` at the hour) times the
  scale that keeps the live people at most 92% of the pool (`LiveScale`, in the status), in
  groups at random places along it; one going past `LiveM` and 40 m loses its people; a person
  walking toward a walkway that is not live turns back there. All of it past the far tier's
  300 m, so out of sight; a jump of the view (a teleport, the benchmark's segments) fills the
  walkways round the new view at once. The rest of the city is a number per walkway: no
  entity, no cost.
- **A fixed pool** (`SpawnPool`): `People` Mass entities made at BeginPlay (one fragment,
  `FCgLifeWalker`, with LG3's state), free until used; no entity is made or destroyed while
  the game runs. The mid and far tiers' instances stay one per pool slot (LG1's), a free slot
  hidden.
- **Trips** (`DoorSpawns`, `CgLife::StepCity`): the live doors send people out at their rates
  (as many as go in over a trip, `TripS` 600 s on average, more while the live people are
  under their number), one after another out of the door onto its walkway; a person whose trip
  is over goes in at the next door ahead of it on its walkway (`Enter`: from where it walks to
  0.6 m inside the door), or, long over and drawn by no tier, leaves where nobody sees.
- **Groups and pace:** people come out and come alive in groups of 1 to 5 (`GroupShares`),
  in pairs side by side `GroupGapM` apart, at the group's slowest pace; a group shares its
  seed, so its members choose the same ways and doors; a follower may still start crossing up
  to 4 s after the walk signal ends, so the hand does not cut a group in two.
- **Signals:** a signalized crosswalk's people wait at its curb (its second point walked
  forward, its last but one back, 0.3 to 1.5 m short of it, `HoldA`, `HoldB`) until its
  phase's walk window (the cycle's time from the game's clock and the junction's offset); a
  share crosses against it (`Jaywalk`, 1% at danger 0 to 30% at danger 1, by its district).
- **Avoidance** (the walk processor's first pass, only for people within `AvoidM` 90 m of the
  view): sorted by walkway and distance along it, each reacts to those ahead of it within
  `ReachM`: a slower or waiting one in its way is passed on the left or followed at its pace;
  one coming the other way makes both step to their own right; a group's members leave each
  other be. Each person keeps to its side (75% right) plus that push, moving across at most
  0.7 m/s; within `PlayerM` of the player's pawn (3D) people step aside and slow.
- **Stairs, escalators, elevators:** every kind of walkway is walked, stairs at 0.6 of the
  pace, escalators at 0.3 of it plus 0.5 m/s, elevators at 0.6 m/s along their shaft with
  nobody drawn inside; people take elevators, skybridges and paths less often than streets.
- **Cheaper far away:** the far people step every second frame, the people drawn by no tier
  every fourth (with the time they missed); the far cards' instances are sent every second
  frame per character, and a character with nobody drawn in a tier is not sent at all; the
  ground is traced only under people drawn near or mid.
- **The tiers:** LG1's, with a person standing (waiting, or held behind someone) on its idle
  clip near, the walk's passing pose mid and far (lifegen_people_fixes, below); a person in an
  elevator is drawn by none.
- **Console:** `CityGenLife.Hour H` (the crowd at another hour, every live walkway filled
  again; until LG8 reads atmosgen's), `CityGenLife.Crowd SCALE [TRIP_S]` (the density times SCALE,
  within the pool, trips TRIP_S long); `CityGenLife.Respawn PEOPLE CARS` takes a smaller pool; `CityGenLife.Status`
  adds `crowd` (hour, pool, live walkways, the live people wanted and the scale, active, free,
  waiting, standing, in elevators, spawned, out of doors, in at doors, gone with their
  walkway, jaywalked, groups, doors live, signals). The check logs it at each play view.
- **Clothing switch** (lifegen_clothing_toggle, a debug switch until LG2's garments; on by
  default): the Tab menu's **Clothing** row (shown when the level has a life controller with
  `bClothing`, found by its class name; `CityGen.MenuRow clothing`, `clothing=0|1`) and
  `CityGenLife.Clothing [0|1]` (`ACityGenLife::SetClothing`). The creator's assembled bodies,
  and the mid meshes baked from them, have no triangles under the garments, so off: near, each
  person's body and outfit are hidden and MetaHuman's whole template body
  (`/MetaHumanCharacter/Body/IdentityTemplate/SKM_Body`, the controller's `WholeBody`, read by
  path from the engine's MetaHuman plugin) follows its pose in the character's own skin
  material, face and hair kept, and the near tier reaches out to `MidM` (at most `NearMax`);
  mid, past that cap, the baked mesh's garment slots (the outfit's materials) are drawn with
  `Core/Life/M_CgLifeHidden` (masked, draws nothing; `HiddenMaterial`), which leaves holes;
  far, the cards keep the clothes their sheets were captured in. `LIFE_VERSION` life4; the
  status's `library` adds `clothing`, `hidden_material`, `whole_body`; the check shoots a view
  named `*_noclothes` twice, clothed (`*_clothes`) and not, the world's time held between.

### People turning, standing and walking far off (lifegen_people_fixes)

A runtime update and a people library rebuild (no exporter or pack change;
`CityGenLifeProcessors.cpp` `CgLife::PathAt`, `TurnTo`; `CityGenLifePeople.cpp`
`MakeMidLoops`, `LookData`; `citygen/ue/people_library.py` `mid_mesh`):

- **The mid tier's bone textures:** LG1's build baked each character's walk into its three
  bone textures (AnimToTexture) and saved the data asset and the mid material instances, but
  never the textures, so once the editor that baked them closed, every mid material sampled
  the engine's default texture: mid people (30 to 90 m) stood crouched, sunk to the knees,
  arms out, in every project and package since LG1 (the impostor sheets, captured in the
  baking session, were right). The build now saves the textures before the data asset and
  the materials that name them, and bakes again a mid mesh whose data asset names none
  (`library.json` is otherwise as before; the library's hash moves, so `--people` rebuilds the
  clips, mid meshes and sheets in a project, the characters kept).

- **Rounded corners:** a person walks its walkway's line with every corner rounded, inside a
  walkway (between two of its stretches) and between walkways (the next one chosen
  `CornerM` plus 0.5 m before its walkway ends, `FCgLifeWalker::Next`, and the heading it left
  the last one on kept, `PrevHead`): a quadratic curve over at most `CornerM` (1.5 m) each
  way, 0.45 of the shorter leg, and cutting the corner by at most half the narrower
  walkway's half width, so a person on its side of a walkway stays on it; a turn back (over
  about 150 degrees) is not rounded. Its side offset is on the curve's own right (and kept on
  the walker's right across walkways that run the other way), so it no longer jumps across
  the walkway at a corner.
- **Turning:** every person's yaw turns toward where it goes (along the curve, and toward the
  side it steps to) at most `TurnDegS` (270 degrees a second), at a door too; a new person
  faces its way at once. The yaw is what all three tiers draw.
- **The mid walk's loop:** AnimToTexture's bake samples the clip's own frame count (its 30 fps
  keys) at the bake's 15 fps, so a library's mid walk ran twice the clip's length and its
  second half held the clip's last pose: mid people walked half the time and slid, frozen,
  the rest. The build bakes one loop of the clip (its custom range) and the runtime plays
  each character's loop as the clip's length at the bake's rate from its first frame
  (`MidFirst`, `MidLast`; logged once per clip), so a library baked before plays right too.
- **Standing mid and far:** LG3 froze a standing person's walk (a rate of 0: the loop's first
  frame, mid stride, and the card's first cell). A standing person now holds the walk's passing pose
  (the frame where both thighs are nearest their mean, found from the clip at BeginPlay,
  `MidStand`) at its walking rate, and its card the sheet's cell nearest that pose (a stride
  rate of 1e-5, its offset putting the cell's middle at now; `CardFrames` 8, the library's).

### From LG2: clothing

The people library's unit becomes a **look**: one of a character's `garments.LOOKS` (6) whole
outfits, each of a fashion group (`lifegen/garments.py`), so the library holds 144 looks of
its 24 characters (`LIB_VERSION` lg2.1). The runtime draws a look where LG1 drew a character:
its character's body and face (the assembled MetaHuman, the plain outfit no longer drawn), the
look's garments, its hair unless the look covers it, its mid mesh and card.
(`citygen/unreal_people.py`, `citygen/ue/people_library.py`; `unreal_life.PACK_VERSION` 5;
`import_city.LIFE_VERSION` life6.)

- **The library's build** runs the editor twice with Blender between (`ensure_library`):
  - *bodies* (editor): each character's assembled body, plain outfit and face at LOD 0 in the
    reference pose, with its bones, as JSON (`<log>/bodies/<id>.json`);
  - *dress* (`dress`, Blender, `BLENDER_JOBS` 4 at once): the textiles drawn
    (`lifegen/textiles.py`) and each character's garments cut, built and draped on its body
    (`lifegen/blender/garments.py`), each look written as its near mesh (LOD 0 and 1) and mid
    mesh (`<cache>/garments/<id>/<look>.{near,lod1,mid}.json`); a character whose job and
    script are unchanged is kept (`done.json`);
  - *looks* (editor): the textiles imported (`People/Textiles`, the normal map's green
    flipped), `M_CgGarment_<hash>` and an instance per textile (`People/Materials/Garments/
    MI_<textile>`), each look's garments one skeletal mesh on the body's skeleton
    (`People/Looks/<id>/SKM_<look>`, LOD 0 and 1, `GeometryScript`'s
    `create_new_skeletal_mesh_asset_from_mesh_lods`, the body's bone proportions): weights
    transferred from the plain outfit where it is nearer than the body (the body has no skin
    under it) and from the body elsewhere, accessories and a raised hood held to their bone;
    since the clothing fixes (`LIB_VERSION` lg2.2) a vertex of an inner layer close under an
    outer garment (within 4 cm on the body's middle, `garments.follow_pairs`: the JSON's
    `follow`, `[inner, outer, weight]` in the outer layers' order first) takes that garment's
    nearest vertex's weights, wholly within 2 cm, and a vertex `manifold` copied takes its
    source's after (its `copies`), so the layers move as one and cannot pass through
    each other (a coat's waist over trousers had);
  - *mid* per look: the body and face at a low LOD, the look's mid mesh (one cloth and one
    glow slot on `M_CgPersonMidCloth`, `_Glow`: vertex colors times the person's dye colors
    from per-instance custom data 4 to 12), the hair's helmet unless the look covers the hair;
    the walk baked as LG1's;
  - *far* per look: the sheet (cells 64 x 128) and a dye mask (a capture with `DyeMode` 1: the
    garments' dye channels red, green and blue, skin and hair black, its alpha the coverage);
  - the manifest's `characters` are the looks (`looks` true, `people` 24, each with its
    `character`, `group`, near meshes `[body, face, look]` and hair or none).
  Editor runs end every 60 looks made (`looks_per_run`) or 72 mid or far (`mid_per_run`,
  `far_per_run`) and the next goes on. `$CITYGEN_PEOPLE_HASH` pins a library while its code is
  worked on, `$CITYGEN_PEOPLE_KEEP_DRESS` keeps the dressed characters.
- **The pack**: `PersonChar` is the person's look (`persons.look`), `PersonGroup` its group;
  `OutfitPalettes` (per district, group and `OutfitColors` colors, linear RGB),
  `OutfitGroupCount`, `DistrictGroups` (per district its people by group) and `DistrictWear`.
- **The runtime**: a person spawned in a district takes a free pool slot of a group drawn by
  the district's people by group (`TakeSlot`: the slot freed last of that group, else any of a
  group the district has, else any), its three dye colors from that group's colors in that
  district and a wear about the district's (`DressSlot`); `PersonTint` holds 9 floats a person.
  Mid instances carry 14 custom floats (the walk's 4, the three colors, wear), far cards 12
  (the walk's 2, the three colors, wear); the card tints its sheet by its dye mask. Near, each
  garment slot gets a dynamic instance with `Tint0` to `Tint2` and `Wear`. The clothing switch
  (`CityGenLife.Clothing`, the Tab menu's row) is unchanged: off hides the look's garments and
  draws MetaHuman's whole body.
- **Cloth near the view:** not set up. Chaos Cloth's clothing data is made by
  `UClothingAssetFactoryBase::CreateFromSkeletalMesh`, a C++ virtual with no Python or Blueprint
  route; the garments move with the body's weights at every tier.

### From LG5: traffic

A life plan with `traffic` (`lifegen plan` since LG5) replaces the spike's cars with the city's
traffic: every lane and junction connector of the lane graph, at its road's density by hour,
simulated only round the view (`citygen/unreal_life.py` `pack_traffic`, `PACK_VERSION` 4;
`import_city.traffic_props`, `LIFE_VERSION` life5; `CityGenLifeTraffic.cpp`). A plan before
LG5 drives the spike's cars as before.

- **The pack** (`BUILD/unreal/life.json`, the controller's properties): the whole lane graph
  as drive lanes (`pack_drive_lanes`: cars_steam's smoothed curves and point speeds); per
  drive lane its cars per hour band (`DriveCars`, 5 a lane: M11's vehicles per 100 m over its
  segment's lanes by length, the fleet's busy and the traffic's scale in; none on a
  connector), district (`DriveDistrict`, the crowd's order, so `DistrictShape` gives its
  day), whether it is on the lane graph's largest strongly connected part (`DriveMain`: cars
  drive only there and never reach a dead end), the signal window it stops at (`DriveSignal`,
  an index into `DriveWindows`: cycle, offset, green from, green to, amber to, s; LG3's
  derived phases) and where (`DriveStopBack`, m back from its end, the plan's: 1.2 m short of
  the crosswalk across it), the connectors it may not be driven at once with
  (`DriveConflicts`, `DriveConflictStarts`: `conflicts`, connectors whose lines come within
  2.2 m in plan and 3 m in height, by GEOS's tree: crossing, merging or leaving one lane);
  the pool's slots by model (`TrafficSlots`), each district's fleet (`TrafficWeights`, a weight
  per model) and paints (`TrafficPaints`, `PaintsPer` paints of 9 floats per model: AG18's
  step H draw by the district's archetype), each model's length (`CarLengths`), each part's
  wheel radius (`CarPartSpin`) and draw distance (`CarPartCull`, `unreal_life.TRAFFIC_CULL_M`:
  body 900 m, glass 300, wheels 150); the settings (`TrafficPool`, `TrafficLiveM`, ...). The
  models are the plan's the project has (AG18's packs imported with the parked cars; never a
  Vex or an Aurel). The import's `life.traffic` says the lanes, pool, radius, signal lanes and
  models; its summary line names them.
- **Live round the view** (`UpdateTraffic`, every 0.25 s): a drive lane within `TrafficLiveM`
  (800 m, 3D, from its bounding box) of the view is live; one coming alive gets its cars at the
  hour (`DriveCars` of the hour's band times its district's day, the scale keeping the live
  cars within 92% of the pool) at random places clear of the cars there; one going past
  `TrafficLiveM` and 60 m loses its cars; a car driving onto a lane that is not live leaves
  there. While the live cars are under their number, new ones come in on live lanes past
  `TrafficRefillM` (450 m) of the view, by their want, over about 4 s. A jump of the view
  fills the lanes round the new view at once. The rest of the city is a number per lane.
- **A fixed pool** (`SpawnCarPool`): `TrafficPool` Mass entities (`FCgLifeCar` with LG5's
  state) made at BeginPlay, each slot a model of the fleet (an instance of each of its parts,
  drawn at no size while free); a car coming out takes a free slot of a model drawn by its
  district's fleet among the models with one free, and one of its district's paints for that
  model (per-instance custom data, as the parked cars').
- **Driving** (the drive processor's `ExecuteTraffic`, every frame; cars past 450 m every
  second): the live cars sorted by lane and distance; each accelerates by the intelligent
  driver model (`TrafficAccel` 1.8 m/s2, `TrafficBrake` 2.6, at most `TrafficBrakeMax` 8,
  `TrafficGapM` 2.2 m standing, `TrafficHeadwayS` 1.2 s, `TrafficDelta` 4) toward its lane's
  speed (cars_steam's: its road's class, bends, junctions, its own share) against the nearest
  of:
  - the car in front, on its lane, its next lane or the one after (no car drives through
    another);
  - its signal's stop line on red, and on amber where it can stop braking at most
    `AmberBrake` (3.5 m/s2); past the line it goes on;
  - the end of its lane while the junction ahead is not its own: a car within its braking
    distance and 6 m of a connector holds it (`FCgLifeCar::Reserved`) only while no
    connector crossing it is driven or held, nor claimed by a car that has waited longer (a
    car waiting `StarveS`, 6 s, claims its connector, so the crossing ones wait for it), and
    only with room past the junction for its length and gap (no car blocks a box); a car
    queued behind a stopped one waits at the edge without holding; past `ForceS` (25 s) of
    waiting it goes (a guard against a jam);
  - anyone in its way: within `YieldM` (180 m) of the view, a car looks ahead along its lanes
    (its stopping distance and `LookS` of its speed, 8 to 45 m) for the crowd's people
    (`WalkPos`, where they are and `PredictS` 1 s on at their pace) and the pawns (every pawn
    but the free camera: the walker, the fly pawn at the road's height) within `LateralM`
    (1.45 m) of its line and 2.5 m in height, and stops `YieldMarginM` (2 m) short of them;
    a car stopped `ForceS` for a person standing still in its way goes on, never for the
    player.
  Each car's wheels roll by its travel over their radius (`CarPartSpin`).
- **Drawn** (`UpdateCarInstances`): an instanced component per model and part, an instance per
  slot of that model; a part drawn as far as the cars live (a body) is sent over its model's
  instances in use (a free slot is taken lowest first), a nearer part (glass, wheels, trims:
  `CarPartCull`) only for the cars within its draw distance and 30 m, each by itself, hidden
  once as its car leaves, and its component not drawn while no car is near (no draw calls).
  The status's `instances_sent`, `draw_ms`, `live_ms` (the live update, half a step off the
  crowd's so the two never land on one frame).
- **Night:** the packs' head, tail and marker lamps are emissive (`M_CgVehicle`'s emission by
  `MPC_CityGen`'s Night, as the parked cars'); no light of their own.
- **Console:** `CityGenLife.Traffic [0|1] [SCALE]` (the traffic on or off, at SCALE times the
  plan's density, filled again), the play menu's **Traffic** row (`traffic`, `traffic=0|1`;
  `ACityGenPlay::HasLifeTraffic`); `CityGenLife.Hour H` fills the lanes again too;
  `CityGenLife.Status` adds `traffic` (hour, pool, live lanes, the cars wanted and the scale,
  active, moving, how many slow for the car in front, a red light, a person, the player, a
  junction, no room past it, spawned, refilled, left at the edge, lost with their lane,
  forced, conflicts, signal lanes, the cars' step and draw ms). For the check's shots,
  `CityGenLife.TrafficShow red|person|player|moving` moves the camera to the nearest car
  stopped at a red light with a queue behind it (most queued first), stopped for a person, for
  the player, or moving (`CITYGEN_LIFE_SHOW`), `CityGenLife.BlockPlayer` stands the walker in
  the lane of the nearest moving car 45 m ahead of it, and `CityGenLife.Jaywalk A B` sets
  LG3's share crossing against the signal.
- **Check** (`citygen/ue/check_city.py`): a view's commands (`$CITYGEN_UE_VIEW_CMDS`) take
  `wait S`, `dilate X` and `until S COMMAND` (again every half second until the traffic shows
  what it was asked, the status's `traffic.show`), and `<name>@late` runs right before the
  view's shot; the result's `traffic_views`.
- **Benchmark:** every life pass sets `CityGenLife.Traffic 1 1`, the pass `night_traffic_off`
  the night with the people and no traffic, `night_traffic_half` half the cars
  (`bench.LIFE_PASSES`). Delta: `night_plan_all` 21.2 ms p95 native, traffic off 18.9
  (`docs/progress/LG5/README.md`).

### From LG4: life at places

A life plan with `places` (`lifegen plan` since LG4) adds life at places to LG3's crowd and
LG5's traffic: the place slots people use, the shops by their hours, gangs on their turf and
police patrols on foot and in cars, all over the city wherever the plan puts them
(`citygen/unreal_life.py` `pack_places`, `PACK_VERSION` 6; `import_city.places_props`,
`LIFE_VERSION` life7; `CityGenLifePlaces.cpp`, `CityGenLifePlaces.h`). A plan before LG4 packs
none of it and its crowd and traffic run as before.

- **The pack** (`BUILD/unreal/life.json`, the controller's properties):
  - every slot (`SlotKinds`, an index into `SlotKindNames` with its `SlotKindBehaviors`: bench
    sit, bus stop wait, kiosk and vending buy, stall eat, taxi stand and club queue queue, bar
    smokers smoke, gang spot talk), its walkway lane (`SlotLanes`) and distance along it
    (`SlotDists`, m), its use points (`SlotPointStarts`, `SlotPoints`: x, y, z, the way its user
    faces, citygen's frame), its users per hour band (`SlotUse`), stay (`SlotDwell`, s), role
    (`SlotRoles`: the crowd, or a gang's members), turf (`SlotTurfs`), clip (`SlotAnims`: idle,
    sit, talk) and, for a club's queue, the door it goes in at (`SlotDoors`);
  - per walkway lane its gang turf (`WalkTurf`), gang members and police walking per band
    (`WalkGang`, `WalkPolice`) and whether police patrol it (`WalkPatrol`);
  - per turf its faction (`TurfFaction`), per faction its members' dye colors
    (`FactionPalettes`, `FactionColors` linear colors: its own first); the gangs' group sizes
    (`GangGroups`);
  - per pool slot its role (`PersonRole`: 0 the crowd, 1 a gang member, 2 police: the plan's
    slots kept for them, in their group's looks);
  - per door (as `DoorLanes`) its people out a hour every hour (`DoorRatesH`, 24: LG3's
    `DoorRates` at the plan's hour only), its place's open hours (`DoorOpen`, 24 bits), a
    passer-by's visit chance per band (`DoorVisit`), a visit's stay (`DoorDwell`) and whether
    it is a precinct station's (`DoorPolice`);
  - patrol cars per drive lane and band (`DrivePolice`), the traffic pool's patrol car slots
    (`TrafficPolice`, the plan's `police_slots`, a model the project has) and their livery
    (`PolicePaint`, 9 floats as AG18's paints);
  - the places' clips (`SitClips` per clip group, `TalkClips` and `TalkCount` per group): the
    Game Animation Sample's bench sitting loop and three standing idle breaks, retargeted onto
    the library's bodies by `unreal_people.ensure_place_clips` (below).
- **The places' clips** (`citygen/unreal_people.py` `ensure_place_clips`,
  `citygen/ue/people_places.py`, run by `citygen unreal ... --people` after the library):
  `lifegen.presets.PLACE_CLIPS` copied from the user's Game Animation Sample (its closure,
  `gas_closure`, `migrate`), retargeted with the library's own retargeter
  (`<content>/Anim/<group>/RTG_GasToBody_<library hash>`) onto each clip group's body in the
  project's editor off screen, notifies stripped, made in place; their manifest
  `Saved/CityGenPeople/places.json` (per group, per clip, its path) with a hash of its own (the
  library's hash, the clips, the script), kept while it is the same. The library's own assets,
  manifest and hash are untouched (its cache stays valid). Without them the people at places
  stand.
- **Smart Objects** (the `SmartObjects` plugin, a dependency of `CityGenLife`): every use point
  of a live slot is a Smart Object of the world's `USmartObjectSubsystem`, made by
  `CreateSmartObject` (no actor) when its walkway comes alive and destroyed when it goes, one
  slot each, its definition one per slot kind made at BeginPlay (`USmartObjectDefinition` with
  one slot at its own transform and a `UCgPlaceBehaviorDefinition` naming the kind, behavior
  and clip; set through reflection: the engine keeps a definition's slots to the editor). A
  person claims a point (`MarkSlotAsClaimed`), occupies it on arrival (`MarkSlotAsOccupied`)
  and frees it when it leaves (`MarkSlotAsFree`); a point another user holds
  (`CanBeClaimed` false: the game's own AI) is passed over. The behaviors themselves run in the
  walk processor, not StateTree (below).
- **The runtime** (`CityGenLifePlaces.cpp`, the walk processor's `StepSlot`):
  - *A walkway coming alive* (LG3's live region) gets, besides its crowd, its gang members in
    groups (in their faction's colors, `DressFaction`), its police in pairs and its slots alive
    with their users at once (sitting, standing, talking there, part way through their stay).
    The pool's role slots are kept in lists of their own (`FreeGang`, `FreePolice`); each role
    is scaled down evenly within its own slots (`gang_scale`, `police_scale`).
  - *Using a slot:* a person walking past a live slot on its walkway that wants another user
    (its users at the hour, the scale keeping the pool's people within it) claims a free point
    (a queue from its front), walks to it (`ToSlot`), sits, waits, queues, buys, eats, smokes
    or talks there for its stay (`AtSlot`, facing the point's way) and walks back to where it
    left its walkway (`FromSlot`); a club's queue goes in at its door instead (the trip's end).
    Crowd groups keep together (only people alone use slots); a gang's members break off to
    their own turf's spots.
  - *Places by their hours* (`ApplyHour`, at BeginPlay and with `CityGenLife.Hour`): a door
    closed at the hour sends no one out and takes no one in at a trip's end; an open shop takes
    a passer-by in for a visit by its chance (`Inside`, not drawn) and lets them out again
    after it.
  - *Gangs* walk only their turf's walkways (`WalkTurf`) and stay out for good; *police* walk
    only the patrol walkways (`WalkPatrol`) at a constable's pace, go back in at their station's
    doors at a trip's end, and the station's live doors send pairs out while the police round
    the view are under their number (`PoliceFromStations`).
  - *Patrol cars* are the traffic pool's police slots (`FreePoliceCars`), filled on a lane
    coming alive by `DrivePolice` and made up for far from the view like the rest, in the
    livery; they drive by LG5's rules.
- **Drawn:** a person at a slot plays its clip near (`WalkAnim`: the bench loop sitting, its
  root `SitOffset` off its point; one of the talk clips by its seed; the idle standing), each
  at its own place in the loop; someone sitting stays near out to the mid tier (`MidM`, within
  `NearMax`: the baked walk has no sitting pose); mid and far people at a slot hold the walk's
  passing pose (LG3's standing person). The ground under a person at a slot is its walkway's
  (no trace at a bench, which would find its seat).
- **Why not StateTree:** the behaviors are five states of the person the walk processor already
  steps (walk, to a slot, at it, back, inside a shop), on the game thread with the rest of its
  step; StateTree on Mass needs MassGameplay's and MassAI's processors (LG0 kept the plugin
  free of them) and a tree instance per entity, for what is here a timer and two lerps.
- **Console:** `CityGenLife.Places [0|1]`, `CityGenLife.Gangs [0|1]`, `CityGenLife.Police
  [0|1]` (each on or off, the live walkways filled again), the play menu's **Places, gangs,
  police** row (`places`, `places=0|1`; `ACityGenPlay::HasLifePlaces`), `CityGenLife.SitOffset
  FORWARD_CM UP_CM`, and for the check's shots `CityGenLife.PlaceShow sit|queue|stall|smoke|
  gang|gangwalk|police|patrol` (the camera to the nearest person sitting, queueing, at a stall,
  smoking at a bar, a gang at its spot or walking, a police pair, a patrol car: the status's
  `traffic.show`, so the check's `until` waits for it). `CityGenLife.Status` adds `places`
  (slots, live, Smart Objects, users by kind, taken, left, claims refused, visits, doors open,
  gang members and police live, free and wanted, their scales, patrol cars).
- **Benchmark:** every life pass sets `CityGenLife.Places`, `.Gangs` and `.Police` (1), the
  pass `night_life_noplaces` turns the three off (`bench.LIFE_PASSES`).

### From LG6: transit

A life plan with `transit` (`lifegen plan` since LG6, its `timetables.json`) adds every transit
line's trains to LG3's crowd, LG4's places and LG5's traffic: the trains run their lines to
their timetables over the whole city, stop at the stations with their doors open, and the crowd
leaves and boards them at the stops round the view (`citygen/unreal_life.py` `pack_transit`,
`TRANSIT_MODELS`, `PACK_VERSION` 7; `import_city.transit_props`, `transit_material`,
`LIFE_VERSION` life8; `CityGenLifeTransit.cpp`). A plan before LG6 packs none of it and the rest
runs as before.

- **The pack** (`BUILD/unreal/life.json`, the controller's properties):
  - per line its mode (`TransitLineMode`, an index of `TransitModes`: the modes the city has),
    color (`TransitLineColor`, linear), loop (`TransitLineLoop`), id (`TransitLineIds`), the
    train as run and drawn (`TransitLineCar`, 12 floats: cars, car length, gap, width, height,
    floor, base over the line's z, track off the line's middle, doors a side, door width, sides
    open (1 its right, 2 both), boarding at the walkway's level), the turn points
    (`TransitLineTurn`, m along the track), the cycle (`TransitLineCycle`, s) and its samples'
    step (`TransitLineDt`), the trains per hour band (`TransitLineTrains`);
  - per line its track (`TransitPointStarts`, `TransitPoints`: citygen m; a loop closes on its
    first point), the cycle's samples (`TransitSampleStarts`, `TransitSamples`: m along the
    cycle, out and then back for an open line), its stop events (`TransitEventStarts`,
    `TransitEvents`, 4 floats: arrive and depart (s into the cycle), the stop (-1 a turn
    without one), the way) and stops (`TransitStopStarts`);
  - per stop its platform walkway (`TransitStopLane`, a walkway lane), where along the track
    (`TransitStopS`), people leaving and boarding a train per band (`TransitStopAlight`,
    `TransitStopBoard`), the height they board at (`TransitStopZ`) and whether at the doors'
    level (`TransitStopLevel`; 0: a metro's concourse over the track, a pylon sky station's
    platforms over its tube, where people go at the point over a door);
  - the stand-ins (`TransitMeshes`: `/Engine/BasicShapes/Cube` and `Cylinder`;
    `TransitPartStarts`, `TransitParts`, 8 floats a part: mesh, kind (body, window, accent,
    dark), middle in the car's frame, size; `TransitMaterial`: `Core/Life/M_CgTransit`, base
    color and emission from per-instance custom data, emission by `MPC_CityGen`'s Night);
  - per walkway lane how far off its middle people keep (`WalkClear`, m: M5's platform walkway
    runs down its tracks' middle, its deck flanks them) and, for a platform, its width widened
    to its deck's; per door (as `DoorLanes`) whether it is a served station's street access
    (`DoorTransit`).
- **The model table** (`unreal_life.TRANSIT_MODELS`, per mode a car's parts: decision 6 leaves
  the trains to the Mac's designs, lifegen generates no vehicle geometry): stand-ins of the
  engine's basic shapes (a body lightened toward the line's color, a band of lit windows, an
  accent band in the line's color glowing by night, roof gear, bogies under a metro or rail
  car, a maglev's skirt, a monorail's arms over its beam, a sky pod's roof light). A mode's
  game pack, when the Mac's designs are in, replaces its parts here (its meshes, scale 1); the
  runtime is the same.
- **The runtime** (`CityGenLifeTransit.cpp`, built at BeginPlay after the crowd and the
  traffic):
  - *By the world's time:* a train's place along its line's cycle is the sampled cycle at (the
    world's time + its phase) modulo the cycle, the phases spread evenly by the hour band's
    trains (`TransitLineTrains`); nothing is simulated, so a far train costs a lookup and every
    line runs city-wide. A band's change of trains (`CityGenLife.Hour`) moves them at once.
  - *On the track:* each car by the track's points at its two ends (its heading, its pitch),
    on its way's own track (its right: `track` off the middle; a loop's one way), crossing to
    the other way's over `TransitCrossM` (90 m) before an open line's turn, so it stands at the
    end on the track it leaves on.
  - *At a stop:* the doors open `TransitDoorOpenS` (2 s) after it halts and shut
    `TransitDoorCloseS` (4 s) before it leaves, sliding over `TransitDoorSlideS`; door leaves
    and a lit doorway between them are drawn for trains within `TransitDoorsM` (300 m) standing
    at a stop (a cube's instances taken as needed). On the right only where the train runs off
    the middle (its platform the side one), both sides where it runs on it.
  - *Boarding and leaving* where the stop's platform walkway is live (LG3's live region): as
    the train halts, the stop's people a train at the hour (`TransitStopAlight`, times the
    crowd's scale) come out of its doors in turn (pool slots spawned at the doors, walking onto
    the platform beside them: the walk processor's `FromSlot` with no slot) and walk on, and
    as many of the crowd on the platform walkway as board (`TransitStopBoard`), the nearest a
    door on their side who reach it before the doors shut, walk into the doors and are gone
    (`CgWalk::Board`, their slot freed). While transit runs, a served station's street
    accesses send no one out (`DoorTransit`): its people come off the trains.
  - *The platforms' keep-out:* people on a platform walkway keep `WalkClear` off its middle,
    on the side they walk (the walk processor's goal pushed out), so they walk the side
    platforms, not the tracks.
  - *Drawn:* one instanced component per basic shape (`TransitMesh0`, `1`), a run of instances
    per train; the trains past `TransitFarM` (1.5 km) have their instances sent every fourth
    frame, the rest every frame; no collision, out of Lumen's scene; the door leaves in
    `TransitDoors`.
- **Console:** `CityGenLife.Transit [0|1]` (toggling without an argument), the play menu's
  **Transit** row (`transit`, `transit=0|1`; `ACityGenPlay::HasLifeTransit`), and for the
  check's shots `CityGenLife.TransitShow board|dwell|moving|metro|monorail|maglev|sky_tube|
  elevated_rail` (the camera to the nearest train within 2 km standing at a stop with people
  boarding or leaving, standing with its doors open, moving, or moving on a line of a mode:
  the status's `transit.show`, which the check's `until` waits for). `CityGenLife.Status` adds
  `transit` (lines, trains, running, moving, standing, near, arrivals, boarded, boarding,
  alighted, instances, door instances, its time a frame).
- **Benchmark:** every life pass sets `CityGenLife.Transit` (1); the pass `night_life_notransit`
  turns it off (`bench.LIFE_PASSES`).

### From LG7: air and water

A plan with `airwater` (`lifegen/airwater.py`, the plan's `airwater.json`) brings what flies
and what floats over the whole city: flying cars between M3's pads and round circuits over the
avenues and highways, drones, police and media fliers, aircraft over the map, a spaceport's
shuttles, boats on every river, channel and canal, water taxis between piers, ferries across
the rivers and ships at the port. A plan before LG7 exports and runs as before (none of these
properties set).

- **The pack** (`unreal_life.pack_airwater`, `PACK_VERSION` 8; `import_city.airwater_props`,
  `LIFE_VERSION` life9): per route its kind (`AwRouteKind`, of `AwKinds`: car, drone, police,
  media, aircraft, shuttle, boat, taxi, ferry, ship), model (`AwRouteModel`, of `AwModels`),
  color (linear), cycle and its samples' step, vehicles per hour band (`AwRouteCount`), points
  with the heading the vehicle faces there (`AwPoints`, 4 floats: citygen m, absolute z;
  degrees counterclockwise from east), samples (`AwSamples`: m along the path), dwells
  (`AwEvents`, 3 floats: arrive, depart, what: 0 pad, 1 roof, 2 pier, 3 berth, 4 launch pad)
  and its vehicles' paints (`AwPaints`, 9 floats each, a hover car's); per model its parts
  (`AwParts`, 9 floats: mesh, kind, middle, size, cull distance), the meshes (`AwMeshes`: the
  engine's basic shapes, AG18's hover cars' parts) and how many custom floats each carries
  (`AwMeshFloats`: 9 painted, 6 a stand-in's in `AwMaterial`, the trains' `M_CgTransit`).
- **The models** (decision 6: the Mac designs the missing kinds; lifegen generates no vehicle
  geometry): flying cars are AG18's hover cars (Kestrel's Dart, Meridian and Atlas, by the
  districts' fleets, in their districts' paints as LG5's traffic paints a car) where the
  project has them, with nav lights (red left, green right, a white strobe, a lamp ahead);
  police fliers the Meridian in LG4's police livery with a flashing red and blue bar; every
  other kind a stand-in of the per kind model table (`unreal_life.AIRWATER_MODELS`: a drone's
  body, arms, rotors and parcel, a media flier's four ducted fans and camera, an airliner, a
  shuttle, a boat, a yellow water taxi with its sign, a double-ended ferry, a container ship),
  its part kinds colored by the runtime (`AW_PART_KINDS`: body, window, accent, dark, nav red,
  nav green, strobe, police red and blue, lamp, hull, beacon). A kind's game pack replaces its
  parts there (meshes, scale 1); the runtime is the same.
- **The runtime** (`CityGenLifeAir.cpp`, built at BeginPlay after transit):
  - *By the world's time,* as LG6's trains: a vehicle's place along its route is the sampled
    cycle at (time + its phase) modulo the cycle, the band's vehicles evenly round it; nothing
    is simulated, every route runs city-wide, a far vehicle costs a lookup and its instances
    are placed every fourth frame past `AwFarM` (1.5 km); a component is sent to the engine
    every frame only while a vehicle within `AwNearM` (600 m) moved in it, else every fourth
    frame, the components taking turns (the engine's cost is per moving component).
  - *Heading:* the route's at that point, interpolated (so a double-ended ferry, or a ship
    backing out of its berth, runs stern first); a flier banks by its turn rate and speed (at
    most 10 to 25 degrees by kind) and pitches with its climb in plan; a boat rolls and bobs.
  - *Lights:* the stand-ins' lamps, windows, nav lights and accents glow by night through
    `M_CgTransit` (MPC_CityGen's `Night`); strobes, beacons and police bars flash (drawn only
    while lit); the hover cars' own lamps are their packs' emissive. No flier casts light.
  - *Drawn:* one instanced component per mesh and cull distance (`AirWater0`, ...), each
    vehicle's parts an instance in theirs; no collision, no shadows, out of Lumen's scene; a
    drone's small parts culled past 250 to 600 m.
- **Console:** `CityGenLife.Air [0|1]` and `CityGenLife.Water [0|1]` (toggling without an
  argument), the play menu's **Air traffic** and **Boats** rows (`air`, `water`, `air=0|1`,
  `water=0|1`; `ACityGenPlay::HasLifeAirWater`), and for the check's shots
  `CityGenLife.AirShow car|landing|layers|drone|police|media|aircraft|shuttle|boat|taxi|ferry|
  ship|pier` (the camera beside the nearest vehicle of a kind within 3 km, a car 4 to 25 s
  from landing on its pad seen from the pad's roof, the cars' layers from behind and over a car
  on a circuit, a taxi or ferry at a pier: the status's `airwater.show`, which the check's
  `until` waits for). `CityGenLife.Status` adds `airwater` (routes, vehicles, fliers and boats
  running, dwelling, near, components, instances, its time a frame).
- **Benchmark:** every life pass sets `CityGenLife.Air` and `CityGenLife.Water` (1); the pass
  `night_life_noairwater` turns both off (`bench.LIFE_PASSES`).

### From LG8: the hour, the weather and reactions

A life plan with `weather` (`lifegen plan` since LG8) makes the city's life follow atmosgen's
hour and weather, shelter from the rain, crowd round the bars by night and react to the player
and to danger (`citygen/unreal_life.py` `pack_weather`, the walkways' `walk_cover` and
`walk_night`, `PACK_VERSION` 9; `import_city.weather_props`, `LIFE_VERSION` life10;
`CityGenLifeWeather.cpp`, the walk processor's `StepCity`, the drive processor). A plan before
LG8 exports and runs as before, at the plan's hour (it still follows atmosgen's hour).

- **The pack** (`BUILD/unreal/life.json`, the controller's properties): the weather's table
  (`WeatherNames`, `WeatherKeys`: out, pace, rain_looks, umbrella, shelter, cars, speed,
  headway_s; `WeatherLife`, a row per state; `WeatherRain`, each state's rain rate), the plan's
  own state (`WeatherPlan`, for a level without atmosgen's controller), the rain looks' group
  (`RainGroup`; `DistrictGroups` are now the clear weather's), each walkway's stretches out of
  the rain (`WalkCoverStarts`, `WalkCover`: from, to, m along it) and its nightlife per band
  (`WalkNight`, 5 a walkway, or none), the umbrellas (`UmbrellaColors`, `UmbrellaLit`,
  `Umbrella`: lit share, canopy width and height, height in the person's heights, right,
  forward, tilt, shaft; `UmbrellaCanopy` and `UmbrellaShaft`, `/Engine/BasicShapes/Cone` and
  `Cylinder` in `M_CgTransit`), the shelter's stand (`ShelterS`), the reactions (`bLook`,
  `bFlee`, `bGather`, `LookM`, `FleeM`, `FleeS`, `FleePace`, `GatherM`, `GatherS`,
  `GatherShare`, `RingM`, `StayS`), stuck cars (`StuckS`, `StuckFarM`) and the places' run clip
  (`RunClips` per clip group, `RunClipSpeed`: the Game Animation Sample's
  `M_Neutral_Run_Loop_F`, retargeted and made in place with LG4's place clips, its speed from
  its root's travel). The import's `life.weather` says the states, the plan's state, the
  stretches and whether there is nightlife.
- **The hour:** every half second the controller reads atmosgen's controller (found by its
  class's name, `CityGenAtmos`; its `Hour`): a step of one hour (time running,
  `CityGenAtmos.TimeSpeed`) moves the doors' and places' rates (`ApplyHour`) and the live
  walkways' and lanes' numbers, people coming out of and going in at doors over their trips; a
  jump (the play menu's day, dusk or night, `CityGenAtmos.Hour`) fills every live walkway and
  lane again at the new hour. Transit's trains and what flies and floats take their hour band
  from it too. `CityGenLife.Hour H` holds life at H (and stops following, the status's
  `weather.follow`); `CityGenLife.FollowAtmos [0|1]`.
- **The weather:** the state atmosgen turns to (`GetWeatherLabel`, after its `>`) and its rain
  (`RainRate` while `bRain`): a rain state's values are the clear weather's moved toward its
  own by its rain now over its rain rate, so they follow a change as atmosgen's rain does; fog
  and smog at once. `OutNow` scales every walkway's want (fewer out: past a tenth over, people
  walking head in at the next door, `ThinOut`), `PaceNow` every walker's pace and walk clip,
  `RainLooksNow` the share of people coming out in the rain looks (a district's groups blended
  toward the rain group), `UmbrellaNow` the share of the others holding an umbrella (by each
  person's hash; none in the rain looks, none for gangs or police), `ShelterNow` a passer-by's
  chance to stop under a stretch out of the rain its walkway passes (sidewalks, paths, alleys,
  promenades, pedestrian streets, underpasses, concourses; singles, crowd role, 3 m stretches
  or longer), standing at the walkway's side for `ShelterS` facing out, walking on soon after
  the rain stops; `CarsNow` the lanes' cars, `SpeedNow` every lane's speed, `HeadwayNow` the
  car following's time headway. `CityGenLife.Weather STATE|auto|off` holds a state, follows
  atmosgen's again, or takes none (clear whatever the sky shows).
- **Umbrellas:** two instanced components (`Umbrellas`, `UmbrellaShafts`: a flattened cone and
  a thin cylinder per person of the pool) over the right shoulder of everyone near or mid who
  holds one and is not under a cover, sitting or running, tilted forward; a canopy color by the
  person's hash, a share with a lit shaft and a faint glow (the city's LED umbrellas). No
  shadow, culled past the mid tier. Sent only while one is drawn.
- **Nightlife:** `WalkNight` adds the bars', clubs' and arcades' people (LG4's places and M11's
  POIs, by their busy and hours) to their door walkways' want.
- **Reactions:** people standing still near the player (`LookM`: waiting at a signal, at a
  slot, under a cover, looking at a danger) turn to face it (sitters keep to their benches);
  stepping aside is LG3's. A danger (`ACityGenLife::Panic(Where, RadiusM, Seconds)`, a
  BlueprintCallable for storygen, `CityGenLife.Panic [R] [S] [X Y Z]`, the play menu's **Scare
  the crowd** row at the player): everyone within its reach but the police leaves where it is
  and runs away along its walkways (each turn the way farthest from it, ignoring the signals) at
  `FleePace` times its pace, near the view on the run clip; after `FleeS` they calm down, and
  for `GatherS` a `GatherShare` of those within `GatherM` (and of the passers-by there) walk
  back toward it, the way nearest it at each turn, and stand on a ring `RingM` off it looking
  at it for `StayS`.
- **Traffic:** every exit of a junction is tested for room past it (LG5 tested only exits
  twice a car's length and gap): an exit shorter than the car and its gap only while it is
  empty and the lanes after it start clear by what the car would stick out (Old Town's 5.8 m
  lanes between the junctions of a cluster held cars inside one junction waiting at the next:
  gridlock); a car waiting for that room claims no connector and is never forced into the box;
  a car standing `StuckS` in a queue past `StuckFarM` of the view leaves (its lane refilled as
  any). Cars stopped for the player on foot wait (no horn: lifegen has no sound, scope 11).
- **Performance** (LG8's pass, `docs/progress/LG8/README.md`): every moving instanced component
  of the controller is a `UCgLifeISM` with fixed bounds (`CityGenLife.Bounds 1`, the default:
  the lanes' box, 1.5 km round it, never measured; every component drawn in every view, twice
  LG7's draw calls, which the render thread and GPU carry while the game thread, the bound,
  saves the measure; 2 lifegen's own measure, each shown instance's place grown by the mesh's
  radius, hidden instances left out; 0 the engine's, every instance's box), the near people's
  garment material instances made once per slot and parent and reused (no garbage as people come and go), the
  near skeletal meshes' bounds fixed (the leader's physics asset, the followers' the leader's),
  the ground traced under near people only and cars within 150 m, the far cards sent every
  third frame, cars past 250 m stepped every second frame and past 550 m every fourth, a
  model's bodies with no car within 300 m sent every third frame.
- **Console:** `CityGenLife.FollowAtmos`, `.Weather`, `.Panic`, and for the check's shots
  `CityGenLife.WeatherShow umbrella|shelter|look|flee|gather|moving` (the camera at the nearest
  person holding an umbrella, under a cover, waiting (4 m in front of them, so they look at it),
  running, looking at the danger: the status's `weather.show`, which the check's `until` waits
  for). `CityGenLife.Status` adds `weather` (following, atmosgen's hour, steps and jumps, the
  state, rain and every value now, umbrellas drawn, people sheltering, looking, fleeing,
  gathering, dangers, people sent in, the stretches) and `traffic.stuck`.
- **Benchmark:** every life pass sets `CityGenLife.FollowAtmos 1` and `CityGenLife.Weather
  auto` and `CityGenLife.Bounds 1`; `night_life_noweather` the night's rain without its
  effect on life; `night_life_ownbounds` and `night_life_enginebounds` the other two bounds.

### People idling and sitting down (people_idles)

People standing or sitting still look alive at every distance, and a sitter sits down and
stands up (`citygen/ue/people_places.py`, `citygen/unreal_people.py` `ensure_place_clips`,
`IDLE_BAKE`; `citygen/unreal_life.py` `idle_data`; `import_city.people_assets` and
`places_props`, `LIFE_VERSION` life11; `CityGenLifePeople.cpp`, `CityGenLifePlaces.cpp`, the
walk processor's `StepSlot`). The people library (its hash, cache and assets) is untouched:
everything is made beside it by the places' clips step, which `--people` runs. A project whose
places' manifest has none of it imports and plays as before.

- **The bench's transitions** (`lifegen.presets.PLACE_CLIPS`, `SIT_IN`): the Game Animation
  Sample's bench sit-downs from five sides (`into_F`, `into_L_090`, `into_R_090`,
  `into_BL`, `into_BR`, the left foot leading) and its stand-up (`out_to_walk`), copied from
  the user's sample (read only) and retargeted with the library's retargeter as LG4's place
  clips, then made in the seat's frame (`seat_frame`: the root still where the clip sits, in
  plan, its height kept; the pelvis carrying the clip's travel and turn), so they chain with
  the sitting loop. The manifest gives each its root's other end in the seat's frame (cm in
  the mesh's axes, its turn) and the stretch a person plays (`start_s`, `end_s`): the sample's
  sit-downs walk up from 4 to 4.7 m off and its stand-up walks 5.9 m away, so only the part
  within `TRIM_CM` (1.3 m) of the seat is played (sit-downs 9 to 9.9 s from 1.8 to 2.3 s into
  the clip, the stand-up its first 2 s), the person walking the rest itself, never from or
  into a road in front of the bench. The controller's `SitInStart` is where in the clip that
  stretch starts.
- **The walk processor:** a person going to a bench point (`ToSlot`) picks the sit-down whose
  start lies most nearly the way it comes from (not one starting behind the bench: a wall or
  building may stand there; `PickSitDown`), walks to that start, turning to its facing over the
  last meter, then stands on the seat (its point, facing the seat's way) while the sit-down
  plays (`W.T` from its start; its stay at least the clip and 2 s); when its stay is over it
  stays on the seat for the stand-up's length, then walks off from where the stand-up ends.
  `WalkAnim` says which: `CgAnim::SitDown` + the sit-down (8 on), `StandUp` (5), `Sit`;
  `CgAnim::IsSit` is any of them (the umbrellas, shelter, the near ring and the shots read it).
  `SitIn`, `SitOut` and `SitInCount` (the controller's, per clip group; the processor takes
  the first group's, `MakeSitFrames`, turned by `MeshYaw` into the seat's frame).
- **Near:** a sit-down or the stand-up plays once from where the processor's clock has it
  (`PersonAnimT`: the time the person's `WalkAnim` last changed), rooted at the seat as the
  sitting loop; the sitting loop after a sit-down from its first frame (where the sit-down
  ends), else from the person's own place in it.
- **Mid:** per look a second AnimToTexture bake (`<content>/MidIdle/<look>`: the library's
  walk as its own bake has it, then the library's `idle_relaxed` and the bench's sitting loop,
  each over the stretch of 4 to 8 s that loops best, `loop_window`; the library's data
  asset's settings, its mesh not saved) and a material instance per mid mesh slot (a child of
  the library's, reading the new bone textures). The controller's `MidStillFrames` (per look
  the idle's and the sitting loop's first and last frame), `MidIdleMaterials` and
  `MidIdleStarts` (set on each look's mid component, `MidSlotMaterial`; the clothing switch
  puts them back). A mid person standing still plays the idle, one sitting (or sitting down
  or standing up) the sitting loop, each from its own time offset and at 0.85 to 1.15 of the
  clip's pace; with them a sitter is drawn by its tier (LG4 kept sitters near out to `MidM`).
- **Far:** per look a still sheet (`<content>/FarIdle`: 8 views of 16 rows, the walk's 8 frames
  as the library's sheet, 4 poses through the sitting loop, 4 through the idle) on
  `M_CgPersonCardIdle_<key>_<CARD_V>`, the library's card with its cell from per-instance
  custom data 12 and 13 (first cell, cells: the walk's 0 and 8; a still person one cell of its
  own, by its seed); the far instances carry 14 floats. The library's card drew every cell
  upside down (the plane's v runs against the card's height; unnoticed at 90 to 300 m, plain
  in LG2's all-far shot): this card reads them upright, and replaces it for every far person. `CardCells` (6: walk, sit, idle, a first cell and
  cells each); `CardMaterials` the still sheets' cards.
- **Console and status:** `CityGenLife.PlaceShow sitdown|standup|sitmid|sitfar|idlemid|idlefar`
  (the camera at someone sitting down or standing up, close; at someone sitting or standing at
  a slot from 55 m or 150 m, the view's own lens); the status's `places` adds `sit_downs`,
  `mid_idles` and `still_cards`.

### Slots on their surface (delta_rebuild)

A slot's points stood at their walkway lane's height where the slot leaves it (LG4,
`BuildPlaces`), plus the ground offset its user last traced walking: a point off its walkway
on another surface (a raised road's sidewalk beside a door path at the ground, the ground by a
door beside an embankment's sidewalk) stood its people in it or over it. The plan now stands
every ground level slot's points on the surface stage 2 draws under them (`lifegen.places.
Surface`: M22's pavement faces on the ground layer at their vertices' heights, lifted as AG17
lifts them, else AG13's ground cover or the bare ground; over the datum, as the lanes), says
so per slot (`seated`) and checks it (`slot_heights`). The exporter packs it per slot
(`slot_seated`, `PACK_VERSION` 10; `import_city.places_props`, `LIFE_VERSION` life12); the
controller puts a seated slot's points at their own z (`SlotSeated`, `PointSeatedG`) and a
person there stands on it without its walking ground offset (`CgLife::PointAt`, `FillSlot`).
A deck's slots keep their walkway's height. A plan before it packs no `slot_seated`: its slots
stand as before.

### People on their surfaces (people_surfaces)

**Walkways on the surface.** The model keeps a walkway's height at its vertices only, and a
raised road's sidewalks, crossings and the paths to them at the ground (M7); AG7 put a raised
road's sidewalk lines on its deck at the same vertices (`graphs.walkways` of the streets'
contribution). A lane drawn from a line ran straight between its points, so over a road's hump
(Old Town's avenue rises 4.5 m to a bridge over a canal) mid people, which keep the ground offset they last
traced near, walked inside the embankment, up to 4.5 m under the sidewalk, and a raised road's
crossings and crosswalks ran under it. `citygen/walksurf.py` drapes every walkway drawn on the
pavement map (sidewalks, crossings, crosswalks, alleys, promenades, pedestrian streets,
footbridges, paths; not stairs, elevators, skybridges, platforms or underpasses) on the surface
stage 2 draws: M22's faces at their vertices' heights by mean value coordinates
(`pavement.mvc`), lifted as AG17 lifts them (curb, sidewalk, corner pad, median 0.2 m, the
rest 0.05 m; a crosswalk crosses a median at the road's 0.05 m). Where faces overlap in plan a
walkway along a road takes the face nearest its road's own surface at its station plus 0.2 m,
any other the face nearest its own height, both within `REACH_M` (1.5 m); off the faces a
road's walkway stands on its road's profile, any other at its own height. The rest follow the
walkways they join (in rounds: their own height moved by the difference at their ends, an end
on none not moved), and ends that meet take one height. Each line is sampled every meter and
kept where its profile bends by more than 2 cm (Douglas and Peucker in its profile; every
vertex kept in place). `exports.graphs` writes the draped lines into `graphs.json` (with the
ground added on a terrain city, as before) and `walk_surface` 1; `unreal.flat_graphs` then
takes them over stage 2's lines, which give their heights at the model's vertices only and,
at a vertex off their own sidewalk's faces (a junction's corner pad), their road's profile
carried on (121 of 2,418 vertices on Delta 0.3 m or more off the pad drawn there). Every
consumer of the flat graphs (the data assets, the life packs, the check's walk, the player
start, the benchmark's route) gets them; a graphs.json from before keeps the old rule. A
lifegen plan checks them (`walk_heights`: the lines sampled every 0.5 m within 5 cm of the
surface outside steps such as a curb, which a line rounds off over a meter; failing past
0.25 m). On Delta: 19,642 walkways, 81,343 points to 92,742; 8 within 15 cm, the rest within
5 cm.

**Sitters rising without a pop.** Near people play their clips through `UCgPersonAnim`
(`CityGenLifeAnim.h`, `.cpp`), a native animation instance in place of LG1's single node: one
clip looping or once at a rate from a position, crossfading from the clip before over a blend
(eased), the clip before carried on its root bone from where the body stood (`RootFix`: a
sit-down and the stand-up play in the seat's frame, so the mesh moves to the seat as one
begins). `ClipBlendS` (0.3 s) between walking, standing, talking, running and into a
sit-down; `SitBlendS` (0.5 s) from a sit-down into the sitting loop and from the loop into the
stand-up, where the sitting pose met the stand-up's first frame with no blend; none for a
person just come near. The leader's anim ticks after the controller (a tick prerequisite), so
a clip asked for and the move to a seat show in the same frame. Console `CityGenLife.Blend
CLIP_S [SIT_S]` (`0 0` as before).

**Mid and far in step with near.** A mid or far sitter showed the sitting loop from the moment
it reached the seat, while near it walks in and sits down over the sit-down's 9 to 10 s, and
showed it until the stand-up was over. `MakeSitFrames` now finds when each sit-down has the
person seated and when the stand-up has it up, half way between the clip's two pelvis heights
over the stretch played (`SitSeatedS`, `SitRiseS`, logged); mid and far stand at the
sit-down's start until seated, sit, and stand at the stand-up's end once up
(`UpdatePeople`).

### Umbrellas held (umbrella_hold)

Results: `docs/progress/umbrella_hold/README.md`. LG8's umbrellas stood over the right shoulder,
no arm held; now they are held in the right hand, the arm up. The places' step
(`unreal_people.ensure_place_clips`, `people_places.py` `hold_pose`) poses each clip group's arm
on its standing idle's first frame by two-bone IK (`unreal_people.UMB_HOLD`: the hand about 28 cm
ahead of the shoulder joint, 2 cm out and 22 cm down on a 54 cm arm, the elbow back, out and
down, the wrist straight), writes it as a clip (`Anim/<group>/A_umb_hold`, the idle with the
upper arm, forearm and hand held) and bakes two more loops into each look's second mid bake (the
walk and the idle with the arm held: `A_umb_walk_<walk>`); the mid bakes keep a key of their own
(`unreal_people.mid_key`), the still sheets `idle_key`. The exporter packs per group the held
clip and the grip in the mesh's frame and per look the held loops' frames (`umb_hold_clips`,
`umb_grip`, `mid_umb_frames`; `PACK_VERSION` 11, `LIFE_VERSION` life13). Near, `UCgPersonAnim`
layers the held arm's three rotations over whatever clip plays (walk, idle, talk), weighted in
and out over `UmbHoldS` (0.35 s) as the umbrella opens or folds; the umbrella stands in the drawn
hand (`hand_r` on along its forearm), its shaft leaning back by the tilt, its canopy no lower
than LG8's; under a cover the arm comes down and the umbrella hangs furled from the hand. Mid,
the instance plays the held walk or idle (`CgLook::Umb`) and the umbrella stands at the bake's
grip; folded, it is not drawn. Far cards are unchanged. Without the held arm's data the
umbrellas are LG8's. The weather status adds `umbrellas_folded`, `umbrella_held`,
`umbrella_mid_held`, `umbrella_hold_groups`; `CityGenLife.WeatherShow umbrella_still` and
`umbrella_folded` frame someone standing with an umbrella open or holding one folded.

## Milestones and checks

- **Every milestone** updates the exporter in its own PR for what it adds or changes (a new
  kind of output, a changed field, a stage's first contribution) and keeps the exporter's
  pytest tests passing. It does not have to run Unreal.
- **Unreal checks** are the coordinating session's call. When a milestone is done, it decides
  whether the change needs one (a new kind of thing in the level, a change to the import or
  the manifest format, a release) and, if so, dispatches a separate local session that makes
  a throwaway project of its own (`--new-project`), imports the cities the milestone
  touches, imports them again (nothing may change), runs `--check` with `--shots`, puts the
  results in `docs/progress/<milestone>/unreal/` and reports back.
- **One Unreal editor at a time** on the Mac; heavy scenes go to the Windows PC. For scale,
  M15 imports a sample city in 33 to 79 s and checks it in 68 to 112 s on the Mac; with
  stage 2 (AG1's shells and AG7's streets) a first import takes 5 to 14 minutes, most of it
  building the Nanite meshes, and an import of an unchanged build 20 to 40 s. With every
  stage 2 part (AG1 to AG4, AG6 to AG8) a first import takes 19 minutes (Greyhook) to an hour
  (Vesper Bay), an unchanged one 1 to 3.5 minutes (2 to 7 with the HLOD pass), and a check
  20 to 30 minutes.

## Record

| Milestone | Change to the exporter | Unreal check |
|---|---|---|
| M15 | Introduced: manifest by key and hash, glTF tiles through Interchange with Nanite, `M_CityGen` material instances, instanced props and plants, graphs as data assets, player start, default sun and sky, re-import by key and hash (`unreal.manifest_changes` says what an import will do), `--check` and `--shots` | the six samples, imported, imported again and checked; a district regenerated with M10 imported over its base and back, exactly the changed actors each way |
| M13 (merged into M15) | Terrain: the ground a heightfield mesh per 256 m tile (`city.ground.<tile>`, draped, complex collision), water at its own levels, roads on their grade lines, buildings on their bases with stepped plinths (in the building's actor, material `plinth`), retaining walls one actor each by id (`rs.w997n776.wall.w1032n756`; the blockout now draws one object per wall), bored tunnels (`bore.w487n577.tunnel`), terrain viaducts and their columns (`rs.e814n566.viaduct.e814n566`, `rs.e814n566.tvcol.e766n565`), hillside greens in the joined open-space pieces (tagged `d03.os.slope.<cell>`, as every open space); the graphs with absolute heights on a terrain city (`graphs.json` `"heights": "absolute"`: sidewalks and lanes over their road's grade line, the rest over the finished ground), so the data assets, the player start and the check's walk stand on the ground; the walk's fall measured from the path, not the start; a facade trace that misses from the building's bottom is tried again from over the ground at its spot; `--view` adds shots | Cragmouth imported (11933 actors, 126 s), imported again (nothing changed, 20 s) and checked (507 of 507 traces down, 36 of 36 roofs and facades, 150 m walked) with 8K shots, two of hillsides (`docs/progress/M15/cragmouth/`) |
| AG0 | No code change (M15 was not on main yet): assetgen's contribution format defined (above, written by `assetgen spike`), with the list of what the exporter needs to take it; the spike ran on M15's project setup from its branch | the spike: three generated buildings and a test tree in a throwaway project (`docs/progress/AG0/unreal/`) |
| AG1 | No code change (M15 was still not on main): `assetgen build` writes the first real contribution, `unreal_contribution.buildings.json` (a shell, pivot, slots, box and convex collision, 23 CPD floats and a proxy per building; one file per stage 2 part); the exporter work it needs listed above | none yet (the coordinating session's call) |
| AG7 | No code change (the AG1 session owns the exporter): the street contribution defined (above, written by `assetgen streets`): per-piece entries replacing the blockout's joined street objects, sky tube glass as non-Nanite LOD chains, container parts, walkways on raised decks; what the exporter needs to take it listed there | the coordinating session's call |
| M14 | Layered districts: a deck's slab one actor per deck and tile (`<deck>.slab.<tile>`, with its railing), its streets, junctions, crosswalks and sidewalks in joined actors of their own (`d03.deck_road.<tile>`, `d03.deck_junction.<tile>` and so on; `city.deck_road.<tile>` and `city.deck_sidewalk.<tile>` with no district until the stage 1 fixes), its ramps one actor each (`<segment>.ramp`), columns joined per tile (`deck_column`), stair flights and elevator shafts one actor each by id, the buildings under a slab (material `bld_undercity`) and on it; actors on a deck (its slab, streets and ramps, the buildings on it) tagged `cg.level=1` (the manifest's `level`, absent on the ground, so a city without decks imports exactly as before; a road's own level, M7's viaducts and M9's tunnels, does not count: fixed in the Unreal check); the manifest's `decks` (id, level, top, district, slab keys); `graphs.json` lanes and walkways with their `level` off the ground and the flat graphs a `levels` array (the data assets' `Levels`, `CORE_VERSION` 2, empty on a city without decks); the check's walk never takes an elevator, and its traces cover each deck (a spot in the middle of its busiest slab tile) | Vesper Bay Decks imported (10477 actors, 64 s), imported again (nothing changed, 24 s) and checked (676 of 676 traces down, 66 of them on the deck itself; 48 of 48 roofs and facades; 260 m walked) with shots of a street on the deck, the same street under the slab and the deck's edge; Vesper Bay imported over its M15 import after the core assets went to `CORE_VERSION` 2 (`docs/progress/M14/unreal/`) |
| Stage 1 fixes | No code change. Keys: a deck's streets and sidewalks are joined per district like the ground's (`d03.deck_road.<tile>`, `d03.deck_sidewalk.<tile>`, with `cg.district=d03`; they were `city.deck_road.<tile>`, `city.deck_sidewalk.<tile>` with an empty `cg.district`), so importing Vesper Bay Decks over an M14 import replaces those actors under their new keys; its ramps keep theirs (`<segment>.ramp`). Cragmouth's local junctions are level out to their corners (more retaining wall actors on its hills, keys by wall id as before) | Not run (the coordinating session's call; `docs/progress/stage1_fixes/`) |
| AG1 and AG7 (after M15) | Stage 2 taken as layer 2: every `assets/unreal_contribution.*.json` read in sorted order (`unreal.stage2`, the manifest's `stage2`; a key in two files refused), the blockout actors of each entry's key and `replaces` dropped, an actor per shell and street piece at its pivot (`cg.stage=2`), the packs through Interchange in their nodes' frames with their own normals, stage 2 masters (`M_CgFacade`, `M_CgGlass`, `M_CgMetal`, `M_CgRoad`, `M_CgOpaque`, `M_CgEmissive`, `M_CgTranslucent`, `M_CgFoliage`) and an instance per part and slot reading the actor's Custom Primitive Data tint, the 23 floats as the components' saved defaults, building collision as convex hulls through GeometryScript (`GeometryScripting` plugin), complex collision for streets, the sky tube glass as a non-Nanite LOD chain, container stacks as instanced actors per entry and kind, proxies imported only, `graphs.walkways` lines in the walkway data assets; `--blockout-only`; the check's walk keeps to walkable walkways (no leg over 30%, no step over 0.6 m, not under the terrain) and tries up to eight starts; the buildings contribution's `asset` is the shell node's Interchange name and its patch slots spell out their tint rule | the small test city, Greyhook and Cragmouth: blockout alone, then stage 2 over it (exactly the actors `manifest_changes` names), imported again (nothing changed), checked (507 of 507 traces down, 36 of 36 roofs and facades, 248, 130 and 81 m walked) with shots; first imports with stage 2 5 to 14 minutes, most of it Nanite builds (`docs/progress/AG1/unreal/`) |
| AG13 | Ground cover and grass taken: `unreal_contribution.ground.json` (above); a part's transforms from a file of its tile's (`xforms_file`, its sha256 in the actor's hash), its cull distances (`cull_m`), no shadow and no HLOD; `M_CgGround` (three sets blended by a tile's mask) and `M_CgGrass` (vertex-colored clumps swaying in `MPC_CityGen`'s new `Wind`, dithered out with the instance fade); the blockout's ground cover objects and M6's median lawns replaced by key (a `drop` where their tile draws none of them); tests without Unreal (`test_stage2_takes_assetgen_ground`) | Not run (the coordinating session's call) |
| AG8 | Props, plants and signs taken: `unreal_contribution.props.json` and `.signs.json` (above); `stage2` replaces M15's prop and plant prototype actors by key (entries keyed by them, or `replaces`, or `drop`), parts with per-instance ids, scales, collision, Nanite and `shape_preservation`; the importer skips the replaced prototypes, scales instances, sets voxel Nanite foliage, makes `M_CgHolo`; tests without Unreal (`test_stage2_props_replace_prototypes`, and `test_stage2_from_assetgen` now with every prototype replaced) | Greyhook and Vesper Bay imported with their props (25,837 and 46,354 actors, 785 and 1,818 s), imported again (nothing changed, 69 and 74 s) and checked (507 of 507 traces down, 36 of 36 roofs and facades, 134 and 253 m walked): the HISM counts per kind equal `props_report.txt`, no M15 prototype left, every instance at its model position, plants Nanite with `Voxelize`, holo-ads translucent 3-LOD chains, neon and lit faces emissive; shots of props by day and a neon street at night (`docs/progress/AG8/unreal/`) |
| Play-ready (after AG1 and AG7) | Open into the city and play it: each import makes the city the project's `EditorStartupMap` and `GameDefaultMap` (`unreal.set_startup_map`, the rest of `Config/DefaultEngine.ini` as it was; `--no-startup`); `Core/BP_CityGenFlyPawn` (a SpectatorPawn, its built-in bindings, no collision, `--fly-speed` 50 m/s) and `Core/GM_CityGenFly`, the level's game mode override with `--play fly` (the default), none with `--play walk`; World Partition for flying: the main grid 256 m cells loaded `--view-range` (1500 m) around the player, the instanced HLOD layer in 512 m cells out to the city's diagonal (its merged parent layer cut off), set by the partitions' C++ property names; the HLODs built after the import (`unreal.build_hlods`, the WorldPartitionHLODsBuilder commandlet, only what changed; `--no-hlod`); every master `used_with_instanced_static_meshes` (without it the far view drew the default material, flat gray); `--check` walks with the project's own pawn whatever `--play` set, runs `ghost`, `fly` and `walk`, then flies with the fly pawn (its speed on the game's clock, through a building, the city loaded where it ends) and with `--shots` takes two views from it; an unchanged build imported again saves nothing; `unreal.manifest_changes` counts a key whose actor changes class (AG8's exact props over M15's instanced ones) as deleted and created, as the importer does | Vesper Bay (blockout only) and Greyhook (with stage 2) imported over their earlier imports, imported again, HLODs built (244 and 285), checked in both modes (507 of 507 traces down, 36 of 36 roofs and facades, 253 and 129 m walked, the console commands, 50 m/s flights) with shots from the fly pawn (`docs/progress/unreal_play/`) |
| AG8 Unreal check | Plants' instanced actors without collision (a part's `collision: {"none": true}` now makes its HISM `NoCollision`; it reached only the mesh record before); the check tries a missed trace down again for up to 30 s (`TRACE_RETRY_S`) and counts those hits as late (the first play session after an import traced before the streamed cells' collision was in place: 346 of 507) (its streaming step's read of actors that had streamed out, which stopped Vesper Bay's first check, was fixed the same way by the play-ready exporter); `test_stage2_from_assetgen` expects the exact props' keys, whose actor changes class, as deleted and created (`manifest_changes` since the play-ready exporter) | as AG8's row |
| AG2 | No code change: each building entry's `parts` (kind, type, glb, node, asset, count, triangles, xforms, building) and `instances`, the part meshes one pack per tile (`parts/<tile>.glb`, above), AG2's new material slots (the new walls, the parts, the industrial dado) tinted only from the six CPD channels; the stage 2 import (AG1 and AG7 row) takes them as instanced actors per entry and kind, tested by `test_stage2_takes_assetgen_parts` on the small city | Greyhook and Vesper Bay with AG6 (`docs/progress/AG6/unreal/`): one instanced actor per building and part kind (11,207 and 17,227), every instance count its entry's (833,694 and 1,320,908 instances), the parts on their walls, nothing floating or doubled; the era walls on the parts and no collision for them came with the AG2 and AG6 Unreal check (below) |
| AG3 | Street fronts: each building's ground band its own entry and node (`<id>.front`, kind `building.front`) with complex collision and `fallback_full` (the mesh record and its hash; the importer sets the Nanite fallback to every triangle), its building's id, CPD and materials; doors tagged on the front's actor (`cg.door=<id>@<walkway>`) and gathered into a fourth flat graph, `doors` (`doors_of`); a stage 2 entry's own `ids` and `level` reach its actor; the tiles' decal meshes as entries (`decals.<tile>`, no Nanite, no collision, `decal.<cell>` slots with their cell index); tests without Unreal (`test_stage2_takes_assetgen_fronts`; `test_stage2_from_assetgen` and `test_stage2_takes_assetgen_parts` read the new entries) | With AG4, in the AG3 and AG4 Unreal check (below; `docs/progress/AG4/unreal/`): Greyhook's 2,671 and Vesper Bay's 5,793 fronts at their shells' pivots with their CPD and era walls, complex collision, the Nanite fallback keeping every triangle; 10,388 and 20,991 `cg.door` tags and door data asset elements; the decal actors on `M_CgDecal` without Nanite or collision; traces and a capsule into the doorways (into the recess, to the door), the hull starting at the band line; shopfronts, neon and lit menus by day and night |
| AG6 | Textures: the contributions' `textures` (the shared library through `assets/library`, the city's sign pages), materials with texture, scalar and vector parameters and era variants (`<slot>@<era>`), building entries' `materials` maps and 30 Custom Primitive Data floats, `unreal_contribution.materials.json` (sign pages, decals); `stage2.textures` with pixel hashes in the materials' and actors' digests; the importer's texture import by hash (library under `Core/Textures`, city pages under `Assets/Textures`), `MPC_CityGen` (`Night`), textured masters (`M_CgFacade`, `M_CgMetal`, `M_CgConcrete`, `M_CgRoad`, `M_CgFoliage`, `M_CgGlass` with interior mapping on the room grid from UV0, `M_CgNeon`, `M_CgSign`, `M_CgDecal`; `STAGE2_VERSION` 4), instance parameters, per-actor era overrides | Greyhook and Vesper Bay imported into one project (36,454 and 60,634 actors, 824 and 2,543 s; Greyhook's 237 textures in 13 s, Vesper Bay reusing 217 of them from `Core/Textures`), imported again (nothing changed, 34 and 69 s), read back and checked (Greyhook 507 of 507 traces down; Vesper Bay's play session too slow until the fixes below), shot by day and with `MPC_CityGen.Night` at 1: every pane one whole room the right way up near and far, about the lit ratio of rooms lit at night, shops in the storefronts, brick courses level with the tint on the bricks, normals right, the era instances on every actor, 30 CPD floats on every building, HLODs textured; textures 539 MB at full size, 65 MB resident (`docs/progress/AG6/unreal/`) |
| Progress output | `citygen unreal` (and `citygen build`, `citygen blockout`) report where they are on stderr through `citygen/progress.py` (stdlib; assetgen uses it too): the importer and the check print `CYBERGEN_PROGRESS {json}` lines (a stage per group of phases, counts at most once a second, a first `plan` line with the import's counts), which `run_editor` relays while it writes the editor's output to the log byte for byte; the HLOD stage counts the builder's own lines (`World contains N HLOD actors`, a `final decision` per actor); a first import's overall estimate from this Mac's per-item times (`FIRST_IMPORT_S`), corrected by the stages done; `--quiet`, `CYBERGEN_QUIET=1`. Nothing the import makes changes | Greyhook imported with stage 2 into a new project, and with the blockout alone and `--check` (below) |
| AG8 on AG6 | Props, plants and signs textured from the library: their contributions carry AG6's material records (catalog master and set per slot, `textures`, `scalars`, `vectors`, the `textures` table); master `M_CgLeaves` (leaf cards: the tint mask as an opacity mask, masked, two-sided, Nanite `Voxelize` kept); `M_CgHolo` reads `SignTex` (`Textured`); sign faces on page materials (`page.<page>` on `M_CgSign`, `holopage.<page>` on `M_CgHolo`, the city's sign page textures); `STAGE2_VERSION` 5 rebuilds the masters; test `test_stage2_textured_props_and_signs` | Greyhook rebuilt with it and imported over its AG6 import (16,054 sign, prop and plant actors updated, no shell or street actor; 4,329 new sign meshes, 8,150 renamed away; 39 new library textures), imported again (nothing changed, no HLOD rebuilt) and checked with shots: leaf cards masked up close, crowns full at 250 and 600 m, sign faces upright on their page cells, bark, painted cars and banded bollards; the holo-ads' faces on their page instances, blown out to white by day (a night shot is open); the prune of the renamed meshes stalled until the AG2 and AG6 Unreal check's fix (`docs/progress/AG6/unreal/`) |
| AG2 and AG6 Unreal check | A building entry's `materials` reach its part instancers (the era walls on AG2's panels, concrete and plaster parts, per slot on the HISM); AG2's building parts get no collision (`collision: {"none": true}`, their instancers `NoCollision`: the building's simple collision covers its masses, and a body per instance, 1.3 million in Vesper Bay, stalled play; containers keep complex collision); every opaque or masked surface master is made with `used_with_nanite` as well as `used_with_instanced_static_meshes` (`usage_flags`; without it, instanced Nanite meshes drew the default material in play and recompiled at each launch, 272 warnings in Vesper Bay); `prune_meshes` keeps `Assets/Materials/` and `Assets/Textures/` (it deleted the city's sign pages after every import, under the instances that use them), and an instance whose texture parameters are empty is rebuilt (`own_textures`); a prune of more than 500 assets (`PRUNE_FILES`) deletes their package files itself on an empty level (`/Engine/Maps/Entry`): the stale packages unloaded, their files deleted, their folders scanned again by the asset registry, the city loaded again for the digests (`delete_files`; the editor's delete took over 90 minutes for the 8,435 meshes AG8 on AG6 renamed, 5 s now) | Greyhook imported again with these (10,617 part instancers updated to `NoCollision`, the 8,435 stale meshes deleted by their files in 5 s; then nothing changed, no HLOD rebuilt) and checked: 507 of 507 traces down, 35 of 36 roofs, 36 of 36 facades, 129 m walked, no usage flag warning in the log; Vesper Bay not imported again with them (its check before them failed: play at 12 to 14 s a frame, 157 of 507 traces down), an open item with the commands in `docs/progress/AG6/unreal/README.md` |
| Play features (an exporter update on its own) | The play features above: `citygen/unreal_play.py` (the map image and play data, the plugin's install and build), the C++ plugin `citygen/ue/CityGenPlay` (the `CityGenPlay` actor, its overlay, free camera and console commands), the manifest's `play` and the play actor (key `play`, in `actor_hashes`), `--no-play`; the engine found through the Epic Games Launcher's install list (`unreal.launcher_engines`); a building whose street front takes it whole has no shell mesh (AG3's gate houses: the entry's `node` null, the front's `replaces` its key); tests `test_unreal_play.py`, `test_manifest_play` | Testport into a throwaway project (`CityDev`): import, `--check` with the play features, shots; Delta Megacity into another (`CityDelta`): import, HLODs, `--check`, shots (`docs/progress/play_features/`) |
| AG4 | Roofs and connections: roof equipment one entry per tile (`roofs.<tile>`, parts only, an instanced actor per mesh with a building id per instance, no collision as the AG2 and AG6 check's building parts); buildings' `replaces` the blockout green-roof objects their shells build; skybridges a part of their own (`unreal_contribution.connections.json`, `connections/<tile>.glb`, an entry per skybridge by id with complex collision); a stage 2 entry's `links` carried to its actor (in its hash) and tagged `cg.link=<link>` by the importer; tests without Unreal (`test_stage2_skybridge_links`, `test_stage2_takes_assetgen_roofs_and_skybridges`) | In the AG3 and AG4 Unreal check (below; `docs/progress/AG4/unreal/`): Greyhook's 170 and Vesper Bay's 258 skybridges at their pivots and yaws with their `cg.link` tags, their floors walkable, reaching 0.15 m into both facades, whose hulls close the landing doors; roof equipment 997 and 1,867 instanced actors, every count its entry's, `NoCollision`, nothing floating; the replaced green roofs gone; every new slot on its master; the sky tube through its portal, the platforms at the tube's floor but inside the tower's hull |
| AG3 and AG4 Unreal check | A shell node with no triangles in its pack (a one-floor building its street front takes whole; the entry's `triangles` counts the front's too) makes no mesh and no actor but still takes the blockout building's place (`glb_triangles`; the empty mesh Unreal refused, "Bad MeshDescription", failed Vesper Bay's HLOD build); the check's streaming wait lists the city's actors once the streaming query says done and then every 2 s, for up to 180 s (`settle`, `COUNT_EVERY_S`, `LOAD_WAIT_S`; listed every frame, 45,000 of them took Vesper Bay's game thread 6.5 s a frame and the far spots never streamed in: the 157 and 169 of 507 traces of the AG2 and AG6 check); roofs and facades traced on shells, not part instancers or fronts; each editor shot rendered once small first (a first render of a new view drew coarse Nanite clusters as flat triangles over the walls); the walk's and flight's frame times in the result; `PRUNE_FILES` 50 (a first import's unused variants by their files); tests `test_stage2_empty_shell`, `test_check_frame_times_and_warm_shots` | Greyhook (40,049 actors, 1,142 s, HLODs 192 s) and Vesper Bay (67,904 actors, 3,524 s; HLODs 167 s) imported into a new project, imported again (Vesper Bay: the empty shell's actor gone, then nothing changed), read back, traced and checked: 507 of 507 traces down in both, 36 of 36 roofs and facades in Vesper Bay, 130 and 253 m walked; Vesper Bay with #54's fixes walks at 0.019 s a frame (median; 0.079 s at 95%), no usage flag warning, its part and roof instancers `NoCollision`, free memory down to 11%; holo-ads show their page by night (`docs/progress/AG4/unreal/`) |
| AG5 | Heroes, types and slopes: a hero's entry carries `hero` (kind, accent) and its own materials (`<slot>#<id>`: the U2 mask `city.hero.<id>` as `HeroMask` with `HeroMaskOn` 1 on the textured opaque masters, its accent on its lights), its shell's UV1 the hero UV; an entry's `hero` and `plinth_m` reach its actor (in its hash), tagged `cg.hero=` and `cg.plinth=`, `stage2.counts.heroes`; the textured masters sample `HeroMask` on UV1 (`STAGE2_VERSION` 6); the buildings' hulls notched at skybridge landing doors; test without Unreal (`test_stage2_heroes_and_plinths`) | In the AG5 Unreal check (below; `docs/progress/AG5/unreal/`): Cragmouth and Greyhook imported and imported again (nothing changed); the megatower and the wheel tagged `cg.hero=`, two UV channels, `HeroMask` (`T_city_hero_<id>`) with `HeroMaskOn` 1 on 14 of 20 and 4 of 5 slots, every master at 6, no other building with it on; 119 Cragmouth buildings tagged `cg.plinth=`, their plinths at the terrain at 732 of 976 corners, buried uphill at 210, floating over a lower street at 30; landing doors open 2.5 m in (332 of 340 in Greyhook) |
| AG5 Unreal check | The check's shots stay under Nanite's root pages: they load every actor but the HLODs, or for a city with more than 42,000 meshes (the manifest's mesh of each actor key, `mesh_of`) the actors nearest its middle up to 42,000 meshes, one set for every view (`SHOT_MESHES`, `view_load`; all 75,155 of Cragmouth's actors stopped the editor on "Cannot allocate more root pages 49152/49152", and loaded per view it stopped at the fourth: an actor unloaded between views keeps its meshes'); in assetgen, an open shed collides only from its roof's underside (its hull blocked the walk under the roof; `GEN_VERSION` ag5.1, no exporter change); test `test_check_shots_stay_under_nanites_root_pages` | Greyhook checked with shots (31,379 of 40,099 actors streamed in at the start, 507 of 507 traces down, 36 of 36 roofs and facades, 130 m walked, 378 m flown; open sheds walked under at 40 of 40 sides); Cragmouth's four check views rendered, but play stops on the root pages before its first frame (its 63,700 Nanite meshes; with the HLODs off and a 700 m loading range as well), an open item for the exporter; slopes traced in the editor (doors behind M13's retaining walls, 325 of 710 within 0.2 m of the ground outside against Greyhook's 1,989 of 2,000), `docs/progress/AG5/unreal/` |
| AG10 | Layered districts: no code change. M14's decks as street pieces in `unreal_contribution.streets.json` (kinds `street.deck.slab`, `.column`, `.stair`, `.elevator`): a slab entry per deck and tile keyed by the blockout's own slab object (`<deck>.slab.<tile>`, so the manifest's `decks` still name it), a column, stair and elevator entry each by id, replacing the joined `deck_column` objects and the flights and shafts; the deck's streets on the slab and its ramps solid with a walkway each side (`graphs.walkways`); an entry's level that of the actor it replaces (`DECK_LEVEL`), so slabs, deck streets and ramps keep `cg.level=1`; test without Unreal (`test_stage2_takes_assetgen_decks`) | In the AG10 Unreal check (below; `docs/progress/AG10/unreal/`): Vesper Bay Decks imported and imported again (nothing changed); its 8 slab actors by their blockout keys at `cg.level=1`, 570 columns, 2 stairs and 2 elevators on no level, 69 deck roads (both ramps), 41 junctions and 136 sidewalks at level 1, the data assets' `Levels` as `graphs.json` (399 lanes, 265 walkways); traces onto the deck at 971 of 971 grid points, the deck's walkways, ramps and stairs walkable |
| AG10 Unreal check | The deck's slab, stair and elevator entries carry `fallback_full` (assetgen's street stage, `FULL_FALLBACK`): complex collision is built from the Nanite fallback, whose automatic one kept 1,370 of a slab tile's 17,597 triangles and lost the rail (a walker's capsule stopped at 33 of 143 points along the deck's edge, 78 with it), and the Mac editor, which renders with Nanite off, drew no soffit lights; a mesh imported again whose entry no longer asks for `fallback_full` goes back to the automatic fallback (`import_city`, it kept the full one); tests `test_deck_pieces_keep_a_full_fallback`, `test_import_resets_a_stale_fallback`, `test_stage2_takes_assetgen_decks` | Vesper Bay Decks imported again with the fix (the 12 deck meshes updated, 8 HLODs rebuilt); traced and shot in the editor by day and night (the soffit lights over the ground streets, the lit undercity, the light wells' stairs and elevators, the ramps, the deck's rail); the check's shots render (42,000 of its 50,008 meshes), but play stops on Nanite's root pages, an open item with Cragmouth's (`docs/progress/AG10/unreal/`) |
| M17 | No code change: the repaired road network reaches Unreal through the blockout's joined objects as before (bend junctions and turning bulbs in the `junction` objects, street links in the roads); the dead-end tags are on the model's road nodes, which the exporter does not carry | Not run (the coordinating session's call) |
| M18 | No code change in the exporter: a junction not flat at its node's height (`Junction.edge_z`) reaches Unreal as a face through its vertices in the joined `junction` objects (on a terrain city every junction), its roads cut back to where they leave it; the embankments under the low raised roads are in their road's `<road>.deck` actor (no actor of their own); crosswalks at their new widths in the `crosswalk` objects; the signals and the walkway graph's crossings follow the model. In stage 2, AG7's road pieces cover the embankments (`covers`, filled under those stretches) and its junction pieces take their vertex heights from `edge_z` | Not run (the coordinating session's call) |
| M19 | No code change. Transit supports change shape: a lone column or pylon under the line, portal frames and cantilever bents as two or one columns (`<line>.leg.<anchor>`) and a new structure kind `beam` (`<line>.cap.<anchor>`, its line on the columns' tops), piers in the water and sky tube masts (`attrs.form`); the blockout draws each as an object of its own by id as before (a pier with its footing, a mast with its legs and stays, a beam in `transit_support`), so the manifest takes them by key and hash, and AG7's contribution gains a `street.transit.beam` piece per beam. Re-importing an M19 build over an older one replaces the transit supports (their ids are new) | the coordinating session's call |
| M21 | Cyberpunk massing: no new actor kind. A building's masses are still one blockout object and one actor (more and finer prisms now: bands of twisted, tapered and leaning shafts, blocks, links, frames, pods, halos; curved masses cut at 1 cm chord sag, so a round tower's glTF has about 112 sides instead of 32); a mass with arcs is drawn smooth in the blockout (`set_sharp_from_angle`, 25 degrees), so its glTF carries smooth normals along the curve and sharp ones at corners; a building's form in its manifest object (`form`, from the blockout object's `form` prop) and tagged `cg.form=<kind>` on its actor (`import_city.tags`; the hash moves with the plan entry, so an import over an older one updates every building actor); stage 2's buildings as before (AG15 will draw the forms whole) | Not run (the coordinating session's call) |
| M16 | Water and ground detail. The blockout (`blockout_plan.json`) gains a `swim` list: every water body cut into boxes per 256 m tile (16 m cells that reach the water, merged in runs along x, then runs alike in y; `blockout.swim_volumes`), each with its key (`swim.<water id>.<tile>.<k>`), the body's id, its plan box and z from 1 m under the body's deepest bed to its surface; the manifest copies it with a hash per box (`swim`, `counts.swim_volumes`), `actor_hashes`, `actor_kinds` (`swim`) and `manifest_changes` take the boxes as actors, and the importer makes a `PhysicsVolume` per box (`Importer.swim`: spawned from its class, so the editor gives it its cube brush, 200 uu; scaled to the box; `water_volume` on, `fluid_friction` 0.3; tags `cg.key`, `cg.hash`, `cg.id=<water id>`, `cg.type=swim_volume`, `cg.category=swim`, `cg.tile`); a box over a sloped bank lies under the ground there, so walking on the land never enters one. New blockout objects, each with a material of its own (`M_CityGen` instances like every blockout material): the beds of a flat city one heightfield per tile (`city.bed.<tile>`, materials `bed_shallow`, `bed_mid` and `bed_deep` by depth; on a terrain city the ground grid carries the beds under the water), the banks joined per district, kind and tile (`d03.bank_quay.<tile>`, `bank_canal_wall`, `bank_road_embankment`, `bank_natural_bank`, `bank_beach`, `bank_marsh_edge`, `bank_riprap`), the ground cover joined per district, kind and tile (`d03.cover_park_lawn.<tile>` and the other ten kinds: a material per cover kind, `cover_<kind>`), in place of the open spaces at the ground (`open_<kind>` objects remain only for podium roofs and decks). On a flat city the water and the sea stand at -1.5 m (the quay deck height under the ground, M16's freeboard; they were -0.9 and -1.2) and bridge piers start at the bed. A city without M16's data exports as before. Tests without Unreal (`tests/test_water_ground.py`: the plan's boxes, the manifest's swim volumes and cover materials, an unchanged re-import) | Not run (the coordinating session's call) |
| AG12 | Water: `unreal_contribution.water.json` (above) as the third layer-2 part: per body and tile a surface entry (non-Nanite, no collision, a LOD chain on coarser lattices; vertex colors and full-precision UVs kept, no lightmap UVs: the importer's water pipeline) replacing `city.sea.<tile>` or `city.water.<tile>`, a bed entry (Nanite, complex collision) replacing `city.bed.<tile>`, bank entries replacing the joined `bank_<kind>` objects with riprap stones as instanced parts, a drop entry for the blockout water objects no piece replaces; masters `M_CgWater` (Single Layer Water, flow-mapped ripples on UV1's current, vertex and shallow foam by Opacity, the sea's Gerstner waves by world position offset faded out from 150 to 350 m: decision 13.10 (a)) and `M_CgBed` (caustics under the water); a post-process volume per M16 swim box of a body (`underwater.*`, the water kind's tint and fog; `actor_hashes`, `actor_kinds`, `counts.underwater_volumes`); `SRGB_PARTS` gains `water`; `STAGE2_VERSION` 7; test without Unreal (`test_exporter_takes_the_water`) | Not run (the coordinating session's call) |
| Fast import (an exporter update on its own) | The fast path the importer's default ("The fast import" above): stage 2's packs queued as one async Interchange import with the pack step (`CgPackStep`: per mesh Nanite settings before the build, unplaced variants not made; AG12's water pipeline on water packs), textures queued with `CgTextureStep`, finished meshes saved in one batch, actors saved and unloaded every `CITYGEN_UE_OFFLOAD` (2,000) spawned and loaded again at the end, the editor run with `-fastexit` and `FAST_INI` (no distance field or card tasks); main's reset of a stale full fallback on both paths; an entry of a building with no shell node (assetgen's packs since `GEN_VERSION` m18.3) takes the blockout's place as an empty shell does; `CITYGEN_UE_FAST=0` the one-at-a-time path. Same actor and asset digests on both paths (the Mac's A/B) | Greyhook on Windows: first import 73m41s in the editor, a second import changing nothing, `--check --shots` passing (`docs/progress/exp_fast_import/`) |
| M20 | Props, plants and signs. No importer change: the large ads come through M15's instancing as prototypes of their own (`blockout.PROTOTYPES` `sign_billboard`, `sign_banner`, `sign_holo`, a unit face the instance scale stretches to the slot; materials `sign_ad`, `sign_banner`, `sign_rim` and `sign_holo`, emissive 6, 6, 8 and 4 in `unreal.EMISSIVE`), one `BP_CityGenInstances` actor per kind and tile keyed `sign.<kind>.<tile>`, the slots' ids as its instances' ids, on a terrain city lifted by their building's base (the masses' frame). AG8's sign entries for those slots name the actor in `replaces`. Props and plants keep their prototypes; on a terrain city the blockout lifts what stands on a roof by its building's base, as AG8 does (it took the ground at the point). | not run |
| AG14 | No code change: the packs' content changes under the same keys ("From AG14" above): curved walls with the curve's own normals (the importer keeps the packs' normals on both paths, held by `test_stage2_packs_keep_their_normals`), M19's frames, piers, footings and masts drawn, junctions meeting their legs, embankments under low decks, a bridge's deck drawn once, roof equipment on its roofs, nothing over a lane under 4.6 m | Not run (the coordinating session's call) |
| AG15 | Cyberpunk facades and night ("From AG15" above; "Play features"): new part kinds and slots through AG2's instancing (LED strips, honeycombs, folded glass, mesh and media screens, fritted glass, logos; `led_<accent>` and `screen_media_*` on `M_CgNeon`); Custom Primitive Data 30 to 35 (the night's light color, schedule, spread, band); `MPC_CityGen`'s `Hour`; `M_CgGlass` lights each room by its building's schedule at the hour and in its light's color temperature (`STAGE2_VERSION` 8); the play features light the streets: spot lights under the 192 lamps nearest the view (8 with shadows), light-pool decals (`M_CgLightPool`) under 768 more, sign washes before the 32 nearest large signs (`play.json` version 2, `washes`); `check_city` reports `lamps_shadowed` and `light_pools` | Not run here (the coordinating session dispatches it; the candelas, `PoolStrength` and `NightGain` are first values for it to set) |
| Sky tube fixes (#94, #97) | No code change. Sky tube supports are plain pylons by default: the blockout draws them as before M19 (a prism by id, no mast legs or stays: their plan entries and so their actors' hashes move, the keys stay) and AG7 a shaft with its cradle (the `transit_column` pieces' packs move); `transit.sky_tube.supports: mast` gives M19's masts back. AG7's tube pieces gain ribs at the model's rings and LED bands on the lit ones in `led.<hex>` slots (an instance per slot, `M_CgNeon` with AG6, `M_CgEmissive` without), under the tubes' keys | Not run (the coordinating session's call) |
| #93 (a fix on its own) | Water drew as the default checkerboard in UE 5.8 (run-through 2): the Single Layer Water output's inputs are named by their properties (`ScatteringCoefficients`, `AbsorptionCoefficients`, `PhaseG`; the editor's graph shows them with spaces), so `M_CgWater` connected none, fell back to opaque water and left the unconnected output node in the graph, which failed the compile ("No inputs to Single Layer Water Material"). The water links by those names (`link` matches an input name with spaces and case aside), the fallback deletes the output node, `STAGE2_VERSION` 9 rebuilds the masters; test `test_water_master_links_single_layer_water_by_ue58_names` | Not run here: import over CityRunThrough2 to see it |
| #95 (a fix on its own) | No code change: the packs' content changes under the same keys. AG7's road pieces end their median barriers, guard walls, parapets and deck ramp barriers at their junctions (ramped or capped ends), a junction piece carries its corner parapets, guard walls and a median across, a footbridge's railings end short of its junctions; AG8 leaves out a prop no variant of which keeps clear of the carriageways (its group's instance lists shorter), and M6's quay railings and median barrier prototypes keep off junctions and crosswalks in the blockout. No new kind, part, slot or master | None needed (no importer change) |
| #82, #89 (a fix on its own) | No code change: the packs' content changes under the same keys. AG7's junction pieces draw an overlap only once (a junction wholly inside a larger one it overlaps has no mesh, declared as covered like a road inside its junctions, its blockout object still replaced), pave the turning lanes round their corners, follow their surface with the slab under a raised junction and draw a cul-de-sac's sidewalk; sidewalk and road pieces leave out the stretches over a junction's carriageway (a sidewalk wholly inside its junctions has no mesh, declared); AG8 leaves out a prop with no pad under it on a raised junction's corner and seats a terrain city's quay railings and plants on the surfaces drawn. No new kind, part, slot or master | None needed (no importer change) |
| #83, #85, #88, #90 (a fix on its own) | The collision check's roof traces count 3 m over the ground a building stands on (a stage 2 building's pivot where its shell's bounds start higher: one-storey sheds and yards over their street fronts, open sheds' roof slabs; Delta's Industrial Port missed 5 of 36 roofs with their hulls in place). An import back to the blockout gives the actors stage 2 had updated in place the blockout's settings again (`unstage`: rotation, slot materials, collision profile, cull distances, shadow, HLOD); `CITYGEN_UE_DIGEST_ROWS=1` writes the digests' rows. The play features' sign washes stand over their building's base on a terrain city (`unreal/play.json`'s `washes`). No version bump: an import's output changes only where an actor goes back to the blockout (which was wrong) and on terrain cities' play data (its own hash). The small city's import test streams at 600 m (`SMALL_VIEW_M`), smaller than the city | The test suite's small terrain and deck cities imported (blockout) into throwaway projects and checked with night views (`docs/progress/fix_assets/`): 36 of 36 and 48 of 48 roofs, 191 lamps lit and 768 light pools each, the washes at their buildings' height; both fail only on streaming (smaller than the view range). `test_unreal_import_small_city` and `test_unreal_import_stage2_small_city` pass. Delta's `--check` was not run: its stage 2 import goes past the PC's memory (#84) |
| M22 | No code change. The blockout draws a city's roads, junctions, corner pads, medians, curbs and sidewalks from the pavement map's faces into the objects they were in (keys unchanged: `<district>.road_<class>.<tile>`, `.junction`, `.sidewalk`, `<segment>.deck`, `.ramp`, `.tunnel_road`, the deck objects), so their plan entries and their actors' hashes move and an import over an earlier one updates them in place. A junction's `polygon` is its carriageway face's outline and its `edge_z` the map's heights there, which the blockout draws as before; `graphs.json` keeps its format. The map itself (`pavement`, `pavement_net`) stays in `city_model.json` for stage 2 (AG17); the exporter does not read it. | Not needed (no new kind of actor, no manifest change) |
| AG17 | No code change: the street packs' content changes under the same keys ("From AG17" above). AG7's road, junction and sidewalk pieces are drawn from M22's pavement map (stored vertices and heights, curbs as walls between faces, a raised junction on its own slab with no girder under it, barriers ending on the roads' port lines), so pieces meet exactly; a road or sidewalk with no faces (a cluster's inner road) has no mesh, declared as before. No new kind, part, slot or master | Not run here (the coordinating session's call; the check's walk should cross junctions with no step) |
| Night lights (a fix on its own, 2026-11-09) | The lamps 0.08 of what they were (`StreetLampCandela` 120, `WallLampCandela` 32), `WashCandela` 120, `PoolStrength` 0.08 (`LIGHT_POOL_VERSION` 4); what glows set for the night's fixed exposure (-3 EV100): `EMISSIVE` and `EMISSIVE2` (neon 8 to 1, emissive 4 to 2, holo 3 to 0.6), assetgen's `SignStrength` times `SIGN_GLOW` 0.125 and a holo-ad's `Emissive` times `HOLO_GLOW` 0.2 in the manifest (`unreal._glow`; stage 2's bytes unchanged). An import over an earlier one makes the light pool's master and the glowing materials' instances again and builds the plugin again | Delta Megacity imported over its AG17 import (CityM22Check); the lamps' strength chosen from night views of a Midtown and an Old Town avenue and the core from the air at several strengths (`CITYGEN_UE_LAMP_SCALES`); the city walked in the editor. The tests were not run (numbers only) |
| #147 (a fix on its own) | No code change. Footbridges are faces of the pavement map, so the blockout draws each again (on M22 they had no faces and the blockout left them out): one object per footbridge, `<segment>.deck` (category `bridge`, collection `Waterfront`: its walk face, the slab under it, piers in the water), so an import over an earlier one creates their actors; AG7's footbridge road pieces now replace those keys (`replaces`), drawn from the map's faces under the same keys. A junction a footbridge meets has a slot where its stairs start, and the few junctions the unfold mends (`pavement.Assembly._unfold`) change shape in height: their plan entries and their actors' hashes move, updated in place. No new kind, part, slot or master | Not run here (the coordinating session's call) |
| AG16 | Performance ("From AG16" above): the benchmark (`--bench`, `--bench-only`, `citygen/bench.py`, `UCityGenBench` in the play plugin, a world subsystem started by `-CityGenBench=<job>`; the last run's shots and graphs, other processes' CPU sampled through each run, CPU-starved runs named, `bench.starved`; the play actor's lamps logged with each shot); meshes shared across tiles (`share_meshes`, the manifest's `counts.shared_meshes`); records as components (`group_actors`, the manifest's `groups` and each record's `holder`; `BP_CityGenGroup`, its root static in the Blueprint, `CORE_VERSION` 3; `actor_hashes`, `actor_kinds` and `manifest_changes` count group actors and holders, not the records they hold; the check's shots count an actor's own and its parts' meshes); `NO_COLLISION` props; the masters read Custom Primitive Data through per-instance custom data (`STAGE2_VERSION` 10); main cells 128 m (`MAIN_CELL_M`), `VIEW_M` 768; the project's `r.TextureStreaming=0` and the Nanite pool from the city (`nanite_pool_mb`, `PROJECT_SETTINGS`); the play actor's underwater volumes enabled by distance; packs imported in chunks of 150 and let go of (`PACK_CHUNK`, `Meshes`, #84); offloads take their actors by guid (`actor_guids`), an actor whose class changes is destroyed and the level saved before anything is made (`clear_moved`), an actor that holds no records loses its members (`drop_members`), an entry with parts of its own keeps its actor; pruned meshes counted by their files | Delta Megacity on the Windows PC (`docs/progress/AG16/`): the before import (73,772 actors, 30 min, 39 GB committed), the fixes imported over it (13,644 actors with the final code), the benchmark before and after three runs each, hitch dumps; Vesper Bay imported and benchmarked with one command |
| AT0 | atmosgen's runtime ("atmosgen's runtime (AT0)" above): the `CityGenAtmos` plugin installed and built with CityGenPlay (`unreal_play.PLUGINS`, one stamp), its assets made from code (`unreal_atmos.make_assets`, `ue/atmos_assets.py`: `MPC_CityGenAtmos`, `M_CgRain`, `M_CgWet`), the controller spawned by `-CityGenAtmosPlan`; `CityGen.PlayLamps` in the play features; the benchmark's `--bench-atmos`, `--bench-rt`, `ATMOS_PASSES` and commands per pass, `busy()` seeing any other benchmark; the plan's contribution format (layer 3). No change to the import: AT1 places the controller and the tiles' lights | the spike on Delta in CityAG16 by AG16's benchmark: night native 12.6 ms p95 before, 15.8 ms with the plan's lights, fog, rain and wet streets; MegaLights with hardware ray tracing 17.4 ms (`docs/progress/AT0/`) |
| AG18 (vehicle packs) | AG18's vehicles ("AG18's vehicles" above): `citygen/unreal_vehicles.py` (the library: `--vehicles`, `$CITYGEN_VEHICLES`, the packs' cache; `--all-vehicles`; placement entries of kind `vehicles` in any contribution, the manifest's `vehicles`, `actor_hashes`, `actor_kinds`, `manifest_changes`), the importer's `vehicles` step (textures, `M_CgVehicle`, `M_CgVehicleGlass`, `M_CgVehicleGlassDark`, a mesh per car and part with the pack's four LODs, no Nanite, the hulls as the body's collision) and `vehicle_actors` (a `BP_CityGenGroup` per placement, a hierarchical instanced component per model and part, the paint in per-instance custom data), `--check-vehicles` (`check_vehicles.py`); tests `tests/test_unreal_vehicles.py`. A city without placements exports as before | Seven packs (vanta_r, brakk_mule, kestrel_dart, tanager_mino, aurel_prelate, orrin_aria, halcyon_ridge) in a line-up of their own in a throwaway project: imported, imported again (nothing changed), checked (every check passing) and shot by day and night (`docs/progress/AG18/unreal/`) |
| AG18 step H (parked vehicles) | "Parked in the cities" above: assetgen's `unreal_contribution.vehicles.json` (a placement per tile replacing AG8's `prop.parked_vehicle.<tile>`, its `library`); `unreal_vehicles.without_replaced` (stage 2's entries a placement replaces left out of stage 2) and `named_library` (the placements' own library when neither `--vehicles` nor `$CITYGEN_VEHICLES` names one); AG16's scene count takes the placements; `CityGenAtmos` builds under the Mac's Clang again (two loops that returned at once, `-Wunreachable-code-loop-increment`). A city without placements exports as before | Vesper Bay in a throwaway project (`docs/progress/AG18/city/`): 912 parked cars as 17 models in 22 placements, imported (23 min), imported again (nothing changed), the city check and the vehicle check passing, shots by day and night |
| AG18 pack faults (cabin glass) | "AG18's vehicles" above: a car's record gains `glass_box` (the glass's box at LOD0 in the car's frame, from the glTF's accessor bounds; `unreal_vehicles.glass_box`); `M_CgVehicleGlass` draws the inner sheet while the eye is inside that box taken down to the car's floor (`CabinCenter`, `CabinHalf` on each car's instance; the eye in the mesh's space from the pixel's local position and the way to the camera), `VEHICLE_VERSION` 7; `--check-vehicles` shoots each car from inside its cabin (`cabin_<car>`); `tests/test_unreal_vehicles.py` checks the box | The vehicle line-up in its throwaway project (`docs/progress/AG18/unreal/`): imported over the earlier import (the masters and the seven cars' instances made anew, 12 placements updated), the vehicle check passing, the glass there from the seats in the cabin shots, the heroes from outside as before |
| AT1 | Layer 3 ("From AT1" above): the manifest's `atmos` (`unreal_atmos.write_atmos`: the controller's key and hash, a cell per 128 m cell, `counts.atmos_cells` and `atmos_lights`; the records in `unreal/atmos.json`; a plan whose lux check failed is named and left out, `--atmos DIR` naming a folder without a plan is an error); `actor_hashes`, `actor_kinds` (`atmos`, `atmos_cell`); the importer's `atmos_cells` (a `CityGenAtmosCell` data actor per cell, spatially loaded, among the offloaded actors) and `atmos_controller` (`CityGenAtmos`, always loaded, the plan's settings), `ATMOS_VERSION`; atmosgen's assets made before the import (`make_assets`); the plugin: cells register their lights as they stream, the controller's pooled live set shows them by night (`MPC_CityGen`'s `Night`), its subsystem and `-CityGenAtmosPlan` gone; the play features without AG15's spot lamps and sign washes (`play.json` 3; `GetStatus` without `lamps_lit`), their pools past the live range; the check reads the controller's status by night; `--atmos`, `--no-atmos`, `--bench-atmos` a flag | Delta in CityAG16 (`docs/progress/AT1/`): imported over AG16's import (the controller and 500 cells created, nothing else touched, under 3 min), the check passing by night with views, the night benchmark before and after (three runs each) |
| Packaged game (a fix on its own, 2026-11-10) | "A packaged game" above: `unreal.ALWAYS_COOK` written to the project's DefaultGame.ini by every import (`set_project_ini`, `set_engine_ini(..., file, entries)`), so the atmos assets loaded by path are cooked; the play module puts a game with no saved resolution at the monitor's native resolution, windowed fullscreen; the Tab menu's Fog, Rain, Wet streets and hour rows drive the atmos controller. | Delta imported again into the AT1 project, packaged (Development Win64) and played: no missing CityGen package, a 2560 x 1440 window, the weather rows by night. |
| Play fixes (2026-11-12, after the packaged Delta) | Play's default is walking (`--play walk`; `fly` and `project` the others): the play plugin's `ACityGenWalker` (`CityGenWalker.h`, a character with a camera in front of the face and a body its player sees, keys bound on its own input component, `-CityGenSelfie=SECONDS` for a packaged game's proof), made into `Core/BP_CityGenWalker` wearing the project's own character's body (`import_city.project_body`) and spawned by `Core/GM_CityGenWalk` (`walk_classes`), the level's game mode override; `--check` walks with it (its spawn and body, a curb climbed: checks `spawn` and `curb`); `M_CgVehicleGlass` darker, coated and covered toward grazing angles (`VEHICLE_VERSION` 10, every car made again; two-sided, the far side's faces left out); the Aurels never imported (`unreal_vehicles.EXCLUDED`, a placement naming one refused) | Delta Megacity imported into CityAG16 and checked, a packaged game (`docs/progress/fix_play_cars/`) |
| LG4 | Life at places ("From LG4: life at places" above): `unreal_life.pack_places` and the door, drive and pool fields LG4 adds (`PACK_VERSION` 6), `import_city.places_props` (`LIFE_VERSION` life7), the places' clips made in the project after the people library (`unreal_people.ensure_place_clips`, `ue/people_places.py`, `Saved/CityGenPeople/places.json`), the `SmartObjects` plugin a dependency of `CityGenLife`, slots' use points as Smart Objects of the world's subsystem while their walkways are live, gangs, police pairs and patrol cars in a livery; console `CityGenLife.Places`, `.Gangs`, `.Police`, `.PlaceShow`, `.SitOffset`, the play menu's Places row, the status's `places`; bench pass `night_life_noplaces`. A plan without `places` exports and runs as before. |
| LG6 | Transit ("From LG6: transit" above): `unreal_life.pack_transit` and the stand-ins' model table `TRANSIT_MODELS` (`PACK_VERSION` 7), `import_city.transit_props` and `M_CgTransit` (`LIFE_VERSION` life8), every line's trains by the world's time on their timetables, doors at the stops, people leaving and boarding at the live stops, a served station's street accesses quiet while transit runs, the platforms' keep-out (`WalkClear`); console `CityGenLife.Transit`, `.TransitShow`, the play menu's Transit row, the status's `transit`; bench pass `night_life_notransit`. A plan without `transit` exports and runs as before. | Delta imported into CityAG16, checked with shots of trains at the stations and running (`docs/progress/LG6/`) |
| LG7 | Air and water ("From LG7: air and water" above): `unreal_life.pack_airwater` and the stand-ins' per kind model table `AIRWATER_MODELS` with AG18's hover cars (`PACK_VERSION` 8), `import_city.airwater_props` (`LIFE_VERSION` life9), every route of what flies and floats by the world's time (flying cars between pads and on circuits, drones, police and media fliers, aircraft, shuttles, boats, water taxis, ferries, ships), banking and bobbing, flashing lights; console `CityGenLife.Air`, `.Water`, `.AirShow`, the play menu's Air traffic and Boats rows, the status's `airwater`; bench pass `night_life_noairwater`. A plan without `airwater` exports and runs as before. | Delta imported into CityAG16, checked with shots of fliers in their layers, a landing, drones, police, boats, a ferry at its pier and a ship (`docs/progress/LG7/`) |
| LG8 | The hour, the weather and reactions ("From LG8" above): `unreal_life.pack_weather`, the walk rows' `walk_cover`, `walk_night` and `walk_road_side`, the run clip (`PACK_VERSION` 9), `import_city.weather_props` (`LIFE_VERSION` life10); the controller follows atmosgen's hour and weather state (people out, pace, raincoats, umbrellas, shelter, nightlife, the cars' share, speed and headway), people look at the player and flee a danger (`Panic`), then gather; every junction exit tested for room, stuck cars far off leave; lifegen's instanced components (`UCgLifeISM`, `CityGenLife.Bounds`); console `CityGenLife.FollowAtmos`, `.Weather`, `.Panic`, `.WeatherShow`, `.Bounds`, the play menu's Scare the crowd row, the status's `weather`; bench passes `night_life_noweather`, `night_life_ownbounds`, `night_life_enginebounds`. A plan without `weather` exports and runs as before (at the plan's hour). | Delta imported into CityAG16 and Vesper Bay into a throwaway project, checked with shots of rain, umbrellas, shelter, people looking and fleeing (`docs/progress/LG8/`) |
| HLOD streaming (fix_hlod_streaming) | "HLOD streaming" above: the instanced HLODs' component the play plugin's `UCityGenHLODComponent` (`unreal.set_hlod_class`, DefaultEditor.ini's `[/Script/Engine.HLODBuilder]` when the plugin is built; its module reads the builder's config again once its classes exist): in a game it leaves its HLOD actor's root and a visibility flip keeps its proxy, only the drawn flag changed on the render thread; `build_hlods` builds every HLOD again when the class or `HLOD_VERSION` changes (`hlod_stamp`, `-SetupHLODs -RebuildHLODs`); the adaptive AddToWorld time slice in every project (`STREAMING_SETTINGS`); console `CityGen.HLODFastVisibility`, `CityGen.HLODStatus`; bench passes `night_plan_all_hlodslow`, `night_plan_all_stream2`, `night_plan_all_adaptive` | Delta imported again into CityAG16, its 763 HLOD actors built again, checked with shots (151,671 flips in place, 672 recreated); benchmark and package (`docs/progress/fix_hlod_streaming/`) |
| People idling and sitting down (people_idles) | "People idling and sitting down" above: the places' clips step makes the bench's five sit-downs and its stand-up (in the seat's frame, the stretch near the seat), per look a second mid bake (the walk, a standing idle, the sitting loop) with its material instances and a still sheet on an upright card (`ensure_place_clips`, `IDLE_BAKE`, `idle_key`); `unreal_life.idle_data`; `import_city.people_assets` and `places_props` (`LIFE_VERSION` life11: `MidStillFrames`, `MidIdleMaterials`, `MidIdleStarts`, `CardCells`, `SitInClips`, `SitInCount`, `SitIn`, `SitInStart`, `SitOutClips`, `SitOut`); the walk processor walks a sitter to its sit-down's start and holds it on the seat through the sit-down and stand-up (`CgAnim::SitDown`, `StandUp`), near plays them, mid the baked idle and sitting loop, far a still cell; console `CityGenLife.PlaceShow` sitdown, standup, sitmid, sitfar, idlemid, idlefar | Delta imported again into CityAG16 with `--people`, checked with shots three times, benchmarked and packaged (`docs/progress/people_idles/`) |
| Slots on their surface (delta_rebuild) | "Slots on their surface" above: the plan seats every ground level slot's points on the drawn surface and says so (`seated`); `unreal_life.pack_places` packs `slot_seated` (`PACK_VERSION` 10), `import_city.places_props` sets `SlotSeated` (`LIFE_VERSION` life12); the controller stands a seated slot's people at its points' own z. A plan without `seated` runs as before. | Delta (rebuilt on main) imported into CityAG16 and checked, with shots of curved roads by day and night (`docs/progress/delta_rebuild/`) |
| People on their surfaces (people_surfaces) | "People on their surfaces" above: `exports.graphs` drapes the walkways on the pavement map's surface (`walksurf.drape`, `walk_surface` 1) and `flat_graphs` takes those lines over stage 2's; the life plugin's `UCgPersonAnim` (a near body's clips crossfaded, `ClipBlendS`, `SitBlendS`, `CityGenLife.Blend`), its leader ticking after the controller; `MakeSitFrames`' `SitSeatedS`, `SitRiseS` for the mid and far looks. No pack or importer version moves; a graphs.json from before exports as it did. | Delta's graphs and life plan made again, imported into CityAG16, checked with shots of people over a road's hump and sitters rising, benchmarked and packaged (`docs/progress/people_surfaces/`) |
