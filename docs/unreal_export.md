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
  (stdlib and `unreal` only). Details: `docs/progress/M15/README.md`.
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
| a player start, a sun, a sky light and the sky atmosphere | always loaded |
| a fly pawn and its game mode, the level's game mode override unless `--play walk` | `/Game/CityGen/Core/BP_CityGenFlyPawn`, `GM_CityGenFly` |
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
- **Flying** (the default, `--play fly`): a free camera with no collision, at 50 m/s
  (`--fly-speed`). W, A, S and D (or the arrow keys) move, the mouse looks, E or Space
  rises, Q or C sinks; a gamepad works too. The speed is set at import; in the editor it is
  the Max Speed of `/Game/CityGen/Core/BP_CityGenFlyPawn`'s movement component (in
  centimeters per second) until the next import sets it again.
- **Walking** (`--play walk`): the project's own game mode and character (the First Person
  template's with `--new-project`), with collision: W, A, S, D, the mouse, Space to jump.
  The console's `ghost` (through walls), `fly` (flying, with collision) and `walk` work as
  usual.
- **Switching without importing again:** the level's World Settings, GameMode Override:
  `GM_CityGenFly` flies, None walks. Shift+F1 frees the mouse while playing, Esc stops.
- **Streaming.** The city loads in 256 m cells within 1500 m of you (`--view-range`), far
  enough ahead for flying. Beyond that you see the far view, World Partition's HLODs (the
  city's own meshes and materials, instanced in 512 m cells, out to the whole city), which
  each import builds after the city: about 2 minutes for a blockout city and 10 with stage
  2's buildings on a Mac the first time, under a minute when nothing changed (only the cells
  whose actors changed are built again).
  `--no-hlod` skips them, and the city then ends at the view range. A sample city is about
  3.5 km across: `--view-range 3000` loads most of it around you, for more memory.
- **`--check`** plays the level twice in the editor, without saving it: walking with the
  project's character whatever `--play` set (streaming, collision, a walk along a sidewalk),
  then flying with the fly pawn (its speed, no collision, the city loaded where it ends).
  The walk and the flight report how long their frames took (median, 95%, longest). With
  `--shots DIR` it renders views of the city (each once small first, so its Nanite pages
  have streamed in) and two from the fly pawn.

| Flag | Default | |
|---|---|---|
| `--play fly` or `walk` | `fly` | what Play puts you in |
| `--fly-speed M_PER_S` | 50 | the fly pawn's top speed |
| `--view-range M` | 1500 | how far around you the city streams in |
| `--no-hlod` | off | skip building the far view (HLODs) after the import |
| `--no-startup` | off | leave the project's startup and default map as they are |
| `--new-project` | off | make the project from the First Person template if it is missing |
| `--blockout-only` | off | leave out stage 2's buildings and streets |
| `--check`, `--check-only`, `--shots DIR`, `--view ...` | | play and check the level, render views |
| `--quiet` | off | no progress on stderr |

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
| 1 citygen | the blockout, props and plants, graphs, player start, a default sun and sky (M15); terrain: the ground per tile, walls, bores, terrain viaducts and columns by id (M13); decks: the slab, deck streets and the buildings on them tagged with their level, the manifest's decks, levels in the graphs (M14) |
| 2 assetgen | buildings replacing their blockout boxes by id (own pivots, parts as instances, simple collision), textured master materials with per-actor parameters, street meshes replacing the joined pieces, prop and plant variants, signs, LODs for the pieces Nanite does not take, HLOD and Lumen settings (per milestone: `docs/assetgen_scope.md` section 14) |
| 3 atmosgen | lights (windows, signs, street lights), sky, weather, fog and post volumes, replacing M15's default sun and sky |
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
  (`prop.sign.<tile>`) in `replaces`. A holo-ad is two entries: the projector on the roof
  (Nanite) under the slot's key, the image `<slot>.holo`, non-Nanite, a LOD chain of three
  (the planes, text, frame and scan bands; the text; one plane) on the `holo` master.
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
| AG8 | Props, plants and signs taken: `unreal_contribution.props.json` and `.signs.json` (above); `stage2` replaces M15's prop and plant prototype actors by key (entries keyed by them, or `replaces`, or `drop`), parts with per-instance ids, scales, collision, Nanite and `shape_preservation`; the importer skips the replaced prototypes, scales instances, sets voxel Nanite foliage, makes `M_CgHolo`; tests without Unreal (`test_stage2_props_replace_prototypes`, and `test_stage2_from_assetgen` now with every prototype replaced) | Greyhook and Vesper Bay imported with their props (25,837 and 46,354 actors, 785 and 1,818 s), imported again (nothing changed, 69 and 74 s) and checked (507 of 507 traces down, 36 of 36 roofs and facades, 134 and 253 m walked): the HISM counts per kind equal `props_report.txt`, no M15 prototype left, every instance at its model position, plants Nanite with `Voxelize`, holo-ads translucent 3-LOD chains, neon and lit faces emissive; shots of props by day and a neon street at night (`docs/progress/AG8/unreal/`) |
| Play-ready (after AG1 and AG7) | Open into the city and play it: each import makes the city the project's `EditorStartupMap` and `GameDefaultMap` (`unreal.set_startup_map`, the rest of `Config/DefaultEngine.ini` as it was; `--no-startup`); `Core/BP_CityGenFlyPawn` (a SpectatorPawn, its built-in bindings, no collision, `--fly-speed` 50 m/s) and `Core/GM_CityGenFly`, the level's game mode override with `--play fly` (the default), none with `--play walk`; World Partition for flying: the main grid 256 m cells loaded `--view-range` (1500 m) around the player, the instanced HLOD layer in 512 m cells out to the city's diagonal (its merged parent layer cut off), set by the partitions' C++ property names; the HLODs built after the import (`unreal.build_hlods`, the WorldPartitionHLODsBuilder commandlet, only what changed; `--no-hlod`); every master `used_with_instanced_static_meshes` (without it the far view drew the default material, flat gray); `--check` walks with the project's own pawn whatever `--play` set, runs `ghost`, `fly` and `walk`, then flies with the fly pawn (its speed on the game's clock, through a building, the city loaded where it ends) and with `--shots` takes two views from it; an unchanged build imported again saves nothing; `unreal.manifest_changes` counts a key whose actor changes class (AG8's exact props over M15's instanced ones) as deleted and created, as the importer does | Vesper Bay (blockout only) and Greyhook (with stage 2) imported over their earlier imports, imported again, HLODs built (244 and 285), checked in both modes (507 of 507 traces down, 36 of 36 roofs and facades, 253 and 129 m walked, the console commands, 50 m/s flights) with shots from the fly pawn (`docs/progress/unreal_play/`) |
| AG8 Unreal check | Plants' instanced actors without collision (a part's `collision: {"none": true}` now makes its HISM `NoCollision`; it reached only the mesh record before); the check tries a missed trace down again for up to 30 s (`TRACE_RETRY_S`) and counts those hits as late (the first play session after an import traced before the streamed cells' collision was in place: 346 of 507) (its streaming step's read of actors that had streamed out, which stopped Vesper Bay's first check, was fixed the same way by the play-ready exporter); `test_stage2_from_assetgen` expects the exact props' keys, whose actor changes class, as deleted and created (`manifest_changes` since the play-ready exporter) | as AG8's row |
| AG2 | No code change: each building entry's `parts` (kind, type, glb, node, asset, count, triangles, xforms, building) and `instances`, the part meshes one pack per tile (`parts/<tile>.glb`, above), AG2's new material slots (the new walls, the parts, the industrial dado) tinted only from the six CPD channels; the stage 2 import (AG1 and AG7 row) takes them as instanced actors per entry and kind, tested by `test_stage2_takes_assetgen_parts` on the small city | Greyhook and Vesper Bay with AG6 (`docs/progress/AG6/unreal/`): one instanced actor per building and part kind (11,207 and 17,227), every instance count its entry's (833,694 and 1,320,908 instances), the parts on their walls, nothing floating or doubled; the era walls on the parts and no collision for them came with the AG2 and AG6 Unreal check (below) |
| AG3 | Street fronts: each building's ground band its own entry and node (`<id>.front`, kind `building.front`) with complex collision and `fallback_full` (the mesh record and its hash; the importer sets the Nanite fallback to every triangle), its building's id, CPD and materials; doors tagged on the front's actor (`cg.door=<id>@<walkway>`) and gathered into a fourth flat graph, `doors` (`doors_of`); a stage 2 entry's own `ids` and `level` reach its actor; the tiles' decal meshes as entries (`decals.<tile>`, no Nanite, no collision, `decal.<cell>` slots with their cell index); tests without Unreal (`test_stage2_takes_assetgen_fronts`; `test_stage2_from_assetgen` and `test_stage2_takes_assetgen_parts` read the new entries) | With AG4, in the AG3 and AG4 Unreal check (below; `docs/progress/AG4/unreal/`): Greyhook's 2,671 and Vesper Bay's 5,793 fronts at their shells' pivots with their CPD and era walls, complex collision, the Nanite fallback keeping every triangle; 10,388 and 20,991 `cg.door` tags and door data asset elements; the decal actors on `M_CgDecal` without Nanite or collision; traces and a capsule into the doorways (into the recess, to the door), the hull starting at the band line; shopfronts, neon and lit menus by day and night |
| AG6 | Textures: the contributions' `textures` (the shared library through `assets/library`, the city's sign pages), materials with texture, scalar and vector parameters and era variants (`<slot>@<era>`), building entries' `materials` maps and 30 Custom Primitive Data floats, `unreal_contribution.materials.json` (sign pages, decals); `stage2.textures` with pixel hashes in the materials' and actors' digests; the importer's texture import by hash (library under `Core/Textures`, city pages under `Assets/Textures`), `MPC_CityGen` (`Night`), textured masters (`M_CgFacade`, `M_CgMetal`, `M_CgConcrete`, `M_CgRoad`, `M_CgFoliage`, `M_CgGlass` with interior mapping on the room grid from UV0, `M_CgNeon`, `M_CgSign`, `M_CgDecal`; `STAGE2_VERSION` 4), instance parameters, per-actor era overrides | Greyhook and Vesper Bay imported into one project (36,454 and 60,634 actors, 824 and 2,543 s; Greyhook's 237 textures in 13 s, Vesper Bay reusing 217 of them from `Core/Textures`), imported again (nothing changed, 34 and 69 s), read back and checked (Greyhook 507 of 507 traces down; Vesper Bay's play session too slow until the fixes below), shot by day and with `MPC_CityGen.Night` at 1: every pane one whole room the right way up near and far, about the lit ratio of rooms lit at night, shops in the storefronts, brick courses level with the tint on the bricks, normals right, the era instances on every actor, 30 CPD floats on every building, HLODs textured; textures 539 MB at full size, 65 MB resident (`docs/progress/AG6/unreal/`) |
| Progress output | `citygen unreal` (and `citygen build`, `citygen blockout`) report where they are on stderr through `citygen/progress.py` (stdlib; assetgen uses it too): the importer and the check print `CYBERGEN_PROGRESS {json}` lines (a stage per group of phases, counts at most once a second, a first `plan` line with the import's counts), which `run_editor` relays while it writes the editor's output to the log byte for byte; the HLOD stage counts the builder's own lines (`World contains N HLOD actors`, a `final decision` per actor); a first import's overall estimate from this Mac's per-item times (`FIRST_IMPORT_S`), corrected by the stages done; `--quiet`, `CYBERGEN_QUIET=1`. Nothing the import makes changes | Greyhook imported with stage 2 into a new project, and with the blockout alone and `--check` (below) |
| AG8 on AG6 | Props, plants and signs textured from the library: their contributions carry AG6's material records (catalog master and set per slot, `textures`, `scalars`, `vectors`, the `textures` table); master `M_CgLeaves` (leaf cards: the tint mask as an opacity mask, masked, two-sided, Nanite `Voxelize` kept); `M_CgHolo` reads `SignTex` (`Textured`); sign faces on page materials (`page.<page>` on `M_CgSign`, `holopage.<page>` on `M_CgHolo`, the city's sign page textures); `STAGE2_VERSION` 5 rebuilds the masters; test `test_stage2_textured_props_and_signs` | Greyhook rebuilt with it and imported over its AG6 import (16,054 sign, prop and plant actors updated, no shell or street actor; 4,329 new sign meshes, 8,150 renamed away; 39 new library textures), imported again (nothing changed, no HLOD rebuilt) and checked with shots: leaf cards masked up close, crowns full at 250 and 600 m, sign faces upright on their page cells, bark, painted cars and banded bollards; the holo-ads' faces on their page instances, blown out to white by day (a night shot is open); the prune of the renamed meshes stalled until the AG2 and AG6 Unreal check's fix (`docs/progress/AG6/unreal/`) |
| AG2 and AG6 Unreal check | A building entry's `materials` reach its part instancers (the era walls on AG2's panels, concrete and plaster parts, per slot on the HISM); AG2's building parts get no collision (`collision: {"none": true}`, their instancers `NoCollision`: the building's simple collision covers its masses, and a body per instance, 1.3 million in Vesper Bay, stalled play; containers keep complex collision); every opaque or masked surface master is made with `used_with_nanite` as well as `used_with_instanced_static_meshes` (`usage_flags`; without it, instanced Nanite meshes drew the default material in play and recompiled at each launch, 272 warnings in Vesper Bay); `prune_meshes` keeps `Assets/Materials/` and `Assets/Textures/` (it deleted the city's sign pages after every import, under the instances that use them), and an instance whose texture parameters are empty is rebuilt (`own_textures`); a prune of more than 500 assets (`PRUNE_FILES`) deletes their package files itself on an empty level (`/Engine/Maps/Entry`): the stale packages unloaded, their files deleted, their folders scanned again by the asset registry, the city loaded again for the digests (`delete_files`; the editor's delete took over 90 minutes for the 8,435 meshes AG8 on AG6 renamed, 5 s now) | Greyhook imported again with these (10,617 part instancers updated to `NoCollision`, the 8,435 stale meshes deleted by their files in 5 s; then nothing changed, no HLOD rebuilt) and checked: 507 of 507 traces down, 35 of 36 roofs, 36 of 36 facades, 129 m walked, no usage flag warning in the log; Vesper Bay not imported again with them (its check before them failed: play at 12 to 14 s a frame, 157 of 507 traces down), an open item with the commands in `docs/progress/AG6/unreal/README.md` |
| AG4 | Roofs and connections: roof equipment one entry per tile (`roofs.<tile>`, parts only, an instanced actor per mesh with a building id per instance, no collision as the AG2 and AG6 check's building parts); buildings' `replaces` the blockout green-roof objects their shells build; skybridges a part of their own (`unreal_contribution.connections.json`, `connections/<tile>.glb`, an entry per skybridge by id with complex collision); a stage 2 entry's `links` carried to its actor (in its hash) and tagged `cg.link=<link>` by the importer; tests without Unreal (`test_stage2_skybridge_links`, `test_stage2_takes_assetgen_roofs_and_skybridges`) | In the AG3 and AG4 Unreal check (below; `docs/progress/AG4/unreal/`): Greyhook's 170 and Vesper Bay's 258 skybridges at their pivots and yaws with their `cg.link` tags, their floors walkable, reaching 0.15 m into both facades, whose hulls close the landing doors; roof equipment 997 and 1,867 instanced actors, every count its entry's, `NoCollision`, nothing floating; the replaced green roofs gone; every new slot on its master; the sky tube through its portal, the platforms at the tube's floor but inside the tower's hull |
| AG3 and AG4 Unreal check | A shell node with no triangles in its pack (a one-floor building its street front takes whole; the entry's `triangles` counts the front's too) makes no mesh and no actor but still takes the blockout building's place (`glb_triangles`; the empty mesh Unreal refused, "Bad MeshDescription", failed Vesper Bay's HLOD build); the check's streaming wait lists the city's actors once the streaming query says done and then every 2 s, for up to 180 s (`settle`, `COUNT_EVERY_S`, `LOAD_WAIT_S`; listed every frame, 45,000 of them took Vesper Bay's game thread 6.5 s a frame and the far spots never streamed in: the 157 and 169 of 507 traces of the AG2 and AG6 check); roofs and facades traced on shells, not part instancers or fronts; each editor shot rendered once small first (a first render of a new view drew coarse Nanite clusters as flat triangles over the walls); the walk's and flight's frame times in the result; `PRUNE_FILES` 50 (a first import's unused variants by their files); tests `test_stage2_empty_shell`, `test_check_frame_times_and_warm_shots` | Greyhook (40,049 actors, 1,142 s, HLODs 192 s) and Vesper Bay (67,904 actors, 3,524 s; HLODs 167 s) imported into a new project, imported again (Vesper Bay: the empty shell's actor gone, then nothing changed), read back, traced and checked: 507 of 507 traces down in both, 36 of 36 roofs and facades in Vesper Bay, 130 and 253 m walked; Vesper Bay with #54's fixes walks at 0.019 s a frame (median; 0.079 s at 95%), no usage flag warning, its part and roof instancers `NoCollision`, free memory down to 11%; holo-ads show their page by night (`docs/progress/AG4/unreal/`) |
| AG5 | Heroes, types and slopes: a hero's entry carries `hero` (kind, accent) and its own materials (`<slot>#<id>`: the U2 mask `city.hero.<id>` as `HeroMask` with `HeroMaskOn` 1 on the textured opaque masters, its accent on its lights), its shell's UV1 the hero UV; an entry's `hero` and `plinth_m` reach its actor (in its hash), tagged `cg.hero=` and `cg.plinth=`, `stage2.counts.heroes`; the textured masters sample `HeroMask` on UV1 (`STAGE2_VERSION` 6); the buildings' hulls notched at skybridge landing doors; test without Unreal (`test_stage2_heroes_and_plinths`) | Not run (the coordinating session's call; what to look for: `docs/progress/AG5/README.md`) |
| M17 | No code change: the repaired road network reaches Unreal through the blockout's joined objects as before (bend junctions and turning bulbs in the `junction` objects, street links in the roads); the dead-end tags are on the model's road nodes, which the exporter does not carry | Not run (the coordinating session's call) |
