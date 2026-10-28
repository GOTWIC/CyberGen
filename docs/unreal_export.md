# Unreal exporter

One exporter takes every stage's output into Unreal Engine 5.8. It is not a stage and has no
milestones of its own: stage 1 introduces it (M15), and every later milestone, in any stage,
updates it in the same PR for what that milestone adds or changes, so the level it builds
always matches the generators. This page is its spec and the record of what each milestone
changed in it. (`unreal/` at the repo root is the earlier hand-tracing pipeline's greybox
script, not this exporter.)

## Where it lives

- **M15** introduces it as `citygen unreal BUILD UPROJECT [--check] [--shots DIR]
  [--new-project]`: `citygen/unreal.py` on the venv side (manifest, glTF prototypes, flat
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
| with stage 2 (AG1, AG7): a static mesh actor per building shell and street piece at its own pivot, in place of the blockout actors it replaces; parts as hierarchical instances per entry and kind | `/Game/CityGen/<City>/Assets/<Part>/<tile>/` |
| stage 2's masters and an instance per part and slot | `/Game/CityGen/Core/M_Cg*`, `/Game/CityGen/<City>/Assets/Materials/` |
| with AG6: textures (the shared library, imported once per project; a city's sign pages), textured masters, `Night` in a parameter collection, an instance per material key (era variants of the wall and roof slots) | `/Game/CityGen/Core/Textures/`, `Core/MPC_CityGen`, `/Game/CityGen/<City>/Assets/Textures/` |

Actors carry `cg.city`, `cg.key`, `cg.hash`, `cg.id`, `cg.type`, `cg.category`, `cg.tile` and
`cg.district` tags. Frames: citygen's (x east, y north, z up, meters) to Unreal's at
(100 x, -100 y, 100 z) centimeters, a citygen yaw to Unreal yaw -yaw.

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
- **Parts**: empty until AG2 (hierarchical instanced meshes per building and kind).
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
  (two-sided). Flat colors until AG6's library: bark, leaves, painted metal, sign faces and
  billboard content are what AG6 or a later pass textures.
- **Collision**: none on plants, signs and exact props (they stand off the walkways or over
  head); complex on prop variants.

**What the exporter does with props and signs** (AG8): `stage2` looks a key up among M15's
prototype actors too, so an entry keyed by one, or naming one in `replaces`, drops it; a
`drop` entry only drops; a part may carry `ids` (the instance actor's `Ids` then hold one
id per transform), `collision`, `nanite` and `shape_preservation` (on its mesh record, in
its hash); transforms may carry a scale (`[x, y, z, yaw, sx, sy, sz]`); `EMISSIVE2` gains
`holo`. The importer skips the replaced prototype actors, applies the scale and ids, sets
`NaniteShapePreservation.VOXELIZE` on a mesh whose record asks for it, and makes `M_CgHolo`
(the translucent master with an emissive strength).

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
  building the Nanite meshes, and an import of an unchanged build 20 to 40 s.

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
| AG8 | Props, plants and signs taken: `unreal_contribution.props.json` and `.signs.json` (above); `stage2` replaces M15's prop and plant prototype actors by key (entries keyed by them, or `replaces`, or `drop`), parts with per-instance ids, scales, collision, Nanite and `shape_preservation`; the importer skips the replaced prototypes, scales instances, sets voxel Nanite foliage, makes `M_CgHolo`; tests without Unreal (`test_stage2_props_replace_prototypes`, and `test_stage2_from_assetgen` now with every prototype replaced) | the coordinating session's call |
| AG6 | Textures: the contributions' `textures` (the shared library through `assets/library`, the city's sign pages), materials with texture, scalar and vector parameters and era variants (`<slot>@<era>`), building entries' `materials` maps and 30 Custom Primitive Data floats, `unreal_contribution.materials.json` (sign pages, decals); `stage2.textures` with pixel hashes in the materials' and actors' digests; the importer's texture import by hash (library under `Core/Textures`, city pages under `Assets/Textures`), `MPC_CityGen` (`Night`), textured masters (`M_CgFacade`, `M_CgMetal`, `M_CgConcrete`, `M_CgRoad`, `M_CgFoliage`, `M_CgGlass` with interior mapping on the room grid from UV0, `M_CgNeon`, `M_CgSign`, `M_CgDecal`; `STAGE2_VERSION` 4), instance parameters, per-actor era overrides | Not run (the coordinating session's call; what to look for: `docs/progress/AG6/README.md`) |
