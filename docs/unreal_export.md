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
  walk_spot ...` and facing its target when one is given), then flying with the fly pawn (its speed, no collision, the city loaded where it ends).
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

## Play features

Every import gives the level a minimap, a map you can teleport with, a free camera and a
developer menu with the time of day, unless `--no-play`:

| Key | What it does |
|---|---|
| (always) | the minimap, top left: the city around you, north up, your heading as an arrow, the city's name, the time of day (day or night without an atmos plan), the keys |
| M | the map, full screen: the whole city with district names; the wheel zooms about the cursor, the right button drags it, the left button teleports you there (a walking player onto the nearest walkway, held until the city has streamed in around it; a flying one at its height, at least 30 m over the walkway there); M or Esc closes it |
| . | the free camera: in the game (not the editor's eject), a spectator pawn with no collision, flown with W A S D, E or Space up, Q or C down, the mouse; the wheel sets its speed (2 to 500 m/s); `.` again goes back to the player, who waited where they were |
| Tab | the developer menu: the time of day (AT3, with an atmos plan: the hour, `<` and `>` step it an hour, a click on the row swaps day and night, and a slider under it, dragged, sets any hour to the quarter; without one a day or night switch), the free camera, the minimap, the engine's on-screen messages, and with an atmos plan atmosgen's weather prototypes (fog, rain, wet streets); click a row to change it; Tab or Esc closes it |

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
| 4 lifegen | traffic, crowd and transit systems on the graphs, spawners |
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
  `hour`. AT5's weather states replace these rows.

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
