# Stage 2 milestone log (assetgen)

The full record of every stage 2 milestone, for the sessions that build and validate them. The
root [README](../README.md) has the short version. Spec: [`assetgen_scope.md`](assetgen_scope.md)
(what each milestone adds and when it is done: section 14). Each milestone's entry grows here
as it lands, as in [`citygen_milestones.md`](citygen_milestones.md).

## Milestones

| Milestone | What it adds | Status | Outputs |
|---|---|---|---|
| AG0 | Contract and spike: package `assetgen/`, asset spec and skill, a brief and hash per building, glTF writer, triangulator, assetgen's part of the Unreal exporter; three generated buildings in Unreal 5.8 to measure Nanite size, import time and Lumen cost | Done | [`docs/progress/AG0`](progress/AG0) |
| AG1 | Building shells: genomes, the facade grammar with six facade systems, walls with window openings, slabs, parapets, proxies; `assetgen build` keeps unchanged assets; Blender previews; the contribution for the first assets in Unreal | Done | [`docs/progress/AG1`](progress/AG1) |
| AG2 | Facades: windows, balconies, fins and panels as parts instanced within a building, every facade system, massing articulation, wear by grime and wealth | Planned | |
| AG3 | Street fronts: a shopfront per unit by use, doors, lobbies, docks, garages, awnings, sign boxes, mounts, party and blind walls; walkable doorways in Unreal | Planned | |
| AG4 | Roofs and connections: roof equipment for every roof item, helipads, green roofs, facade details, skybridges, sky tube portals and stations | Planned | |
| AG5 | Types, landmarks and slopes: per-type generators, complex families, hero landmarks, buildings on M13's slopes, the art-direction loop | Planned | |
| AG6 | Materials and textures: the shared library per era, trim sheets, decals, window interiors, signage atlases, per-building parameters; textured master materials in Unreal | Planned | |
| AG7 | Street elements: roads with markings, sidewalks, bridges, viaducts, interchanges, tunnels, quays, transit structures, megasite elements | Planned | |
| AG8 | Props, plants and signs: prop variants per district style, trees by species, neon signs, billboards, holo-ads | Planned | |
| AG9 | Scale and release: every sample modelled, `assetgen sweep`, the Windows check, `assetgen lock`, HLOD and Lumen settings at city scale | Planned | |
| AG10 | Layered districts: buildings and streets on M14's decks | Planned (after M14) | |
| AG11 | Interiors for M11's places | Only if decision 13.6 asks | |

## AG0: contract and spike

**Built.** Package `assetgen/` (CLI `python -m assetgen`, tests in `tests/assetgen/`):
- the asset spec with era presets for the ten eras (`spec.py`, `presets.py`; `assetgen spec
  validate|schema`), the `assetgen` skill (prompt to asset spec, no API call) and a sample,
  `cities/vesper_bay/asset_spec.json`;
- `assetgen brief BUILD` (`brief.py`): `assets/briefs.json`, one brief and sha256 per
  building in its own frame: its record, masses and floor grid, every mass edge split into
  facade regions classed by what they face (front, street, alley, canal, plaza, park,
  courtyard, atrium, party, blind, open, upper, hidden), neighbors within 3 m, skybridges,
  portals, sign slots, mounted props, facade plants, green roofs, POIs, lot, property,
  district style, M13's `base_m` and `plinth_m` where present, and the spec's sections for
  it; `preview_edges.png`; the brief schema (`assetgen brief schema`); `assetgen brief diff`;
- the exact integer triangulator with holes (`triangulate.py`), the mesh builder on integer
  millimeters (`mesh.py`) and the deterministic glTF writer (`gltf.py`, with
  `KHR_mesh_quantization` and `EXT_mesh_gpu_instancing` as options);
- the determinism harness: goldens for the small test city, seven Vesper Bay buildings, the five
  samples' briefs, two spike buildings and a triangulation, Mac = x86 (`citygen-x86`);
- the spike (`spike.py`): a 975k-triangle tower, a shopfront row, a shanty stack and a test
  tree, with assetgen's entries for the Unreal exporter (`unreal_contribution.json`), shown in
  Blender (`assetgen/blender/spike_preview.py`) and imported into a throwaway Unreal 5.8
  project (`assetgen/ue/spike_import.py`, `spike_shots.py`, `unreal_spike.py`).

**Briefs of the samples** (M10 code): every building of the seven sample builds has a
brief (2,460 to 6,686 per city, 7 to 22 s each); M10's eight district regenerations change
only briefs of their district and seam (none unexplained; seam 0 to 32 buildings).

**Measured** (scope section 11 has the numbers): Nanite costs about 70 bytes per source
triangle cooked as the spike writes meshes, 46 without UV1 and vertex colors (the scope
assumed 14); 23 to 72 s of Nanite build per million triangles on the shared Mac; distance
fields and Lumen cards 2 to 4 MB and 4 to 15 s per mesh whatever its size; Interchange reads
`KHR_mesh_quantization` (source files only, 24% smaller) and not `EXT_mesh_gpu_instancing`;
simple collision boxes per mass work by `UBX_` mesh names and from Python; Custom Primitive
Data per component works; 5.8 has Nanite foliage (voxel shape preservation, settable from
Python) and experimental Nanite Assemblies (built in 1.7 s for 14,738 parts, but cooked to
125 MB).

**Decisions:** section 13's recommendations taken as provisional answers (2026-10-27, until
Swagnik overrides), set as the asset spec's defaults.

**For later milestones:** AG1 welds vertices on a face plane and keeps UV1 and vertex colors
only where needed (glass, signs); COLOR_0 is a base-color multiplier in glTF (grime as a
gray; per-window ids in alpha); parts come from the manifest as hierarchical instanced
meshes, not glTF instancing or assemblies; distance fields and Lumen cards stay off for
buildings (hardware ray-traced Lumen on the PC); AG8 tries voxel Nanite foliage for trees;
the exporter work AG0 could not do (M15 not on main) is listed in `unreal_export.md`; asks of
citygen (scope 4.5) gained the facade props M6 hangs where no wall spans their height
(Vesper Bay: 1,419 AC units, 573 signs, 484 awnings off a wall).

## AG1: building shells

**Built.** The building line's first generators (`assetgen/buildings/`) and the build:
- **genome** (`genome.py`): district palette (era preset with the spec over it, district
  additions, a landmark's palette), property family (a complex's buildings share discrete
  genes and colors, step continuous ones), building genes per mass group (`base`, `body`,
  `top`: system, window type, rhythm, bay, window share, sill, head, reveal, corner pier,
  cornice, parapet, bands) and per building (ground band, crown, corner, finish, base strip,
  colors, wear, dirt height), all blake2b of ids, quantized; `effective` gives the genes a
  shell used;
- **facade systems** (`systems.py`): unitized curtain wall, punched concrete, precast panel,
  punched brick, corrugated, shanty patchwork; every other system falls back to the nearest
  (`FALLBACK`), types with a fixed system (`TYPE_SYSTEM`), roles to mass groups, material
  slots with their tint channel, the 23 CPD floats;
- **grammar and shell** (`shell.py`, `meshbuf.py`, `rings.py`): floor rows per mass (ground,
  louver, lantern, parking rows), bays between corner piers at real corners, openings by
  window type and region class, storefronts per unit, mount panels; walls welded per plane
  with zipper strips, reveal pockets and panes, caps (`triangulate(..., keep_straight=True)`),
  ring strips for parapets, cornices and bands (mitered, beveled past 1.5 offsets), roof
  equipment blocks; spiked rings and pinched courts cleaned; every part closed;
- **proxies** (`proxy.py`, at most 500 triangles) and **collision** (`collision.py`: convex
  pieces per mass, boxes where rectangles);
- **`assetgen build`** (`assetgen/build.py`, `manifest.py`, `asset_checks.py`,
  `contribution.py`, `buildings/envelope.py`): briefs kept when their inputs are, asset hash
  per building, 256 m tile packs made in up to 4 worker processes where hashes changed,
  manifest, report, `unreal_contribution.buildings.json`, files written only when their
  bytes change; checks `asset_coverage`, `asset_envelope`, `asset_meshes`, `asset_unique`,
  `asset_budget`;
- **`assetgen preview`** (`previews.py`, `blender/preview_assets.py`): the city from proxies
  (and with every shell), districts and the blockout's street cameras at full detail,
  contact sheets per type and one of 64 buildings across the city, on the blockout's
  city.blend without its building boxes;
- tests `tests/assetgen/test_ag_shell.py`, `test_ag_build.py`; goldens under `ag1` (the small
  city's manifest and asset files, nine Vesper Bay shells as GLB).

AG1_NUMBERS

## Order

```
 AG0 ─┬─> AG1 ─> AG2 ─> AG3 ─> AG4 ─> AG5 ──┐
      │     └──> AG6 ───────────────────────┤
      ├─> AG7 ──────────────────────────────┼─> AG9 ─> AG10 (after M14), AG11 (if asked)
      └─> AG8 ──────────────────────────────┘
```

The building line (AG1 to AG5) is one session at a time; AG6, AG7 and AG8 can run beside it
as separate local sessions. AG0's briefs only read citygen; its Unreal part waits for M15
and the exporter's move to its own package. Section 14.12 of the scope has the rules.

## Unreal

Every milestone updates the shared Unreal exporter for what it adds (scope section 14, the
**Unreal** line of each; [`unreal_export.md`](unreal_export.md)). A milestone session does not
have to run Unreal: when it is done, the coordinating session decides whether an Unreal check
is needed and runs it in a separate session; its results go in `docs/progress/AG<n>/unreal/`
and its entry here notes it.

## Outputs

Each milestone's builds, previews and report go in `docs/progress/AG<n>/`; while a session
runs, it pushes snapshot images to its branch under `docs/progress/AG<n>/wip/`. Generated
assets are not in git.

## Commands

```
.venv/bin/python -m assetgen spec validate SPEC [--build BUILD]          # asset spec (AG0)
.venv/bin/python -m assetgen brief BUILD [--spec SPEC]                  # briefs and hashes (AG0)
.venv/bin/python -m assetgen brief diff A B                             # what changed (AG0)
.venv/bin/python -m assetgen spike OUT --quantized                      # the spike buildings (AG0)
.venv/bin/python -m assetgen build BUILD [--spec asset_spec.json]       # assets (AG1 on)
.venv/bin/python -m assetgen review BUILD --prev P                      # art-direction round (AG5)
.venv/bin/python -m citygen unreal BUILD PROJECT                        # the city with its assets in Unreal
.venv/bin/python -m assetgen sweep --suite m8a --out DIR                # (AG9)
.venv/bin/python -m assetgen lock BUILD --release 1.0                   # (AG9)
```
