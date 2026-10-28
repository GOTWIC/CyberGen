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
| AG2 | Facades: windows, balconies, fins and panels as parts instanced within a building, every facade system, massing articulation, wear by grime and wealth, thumbnail uniqueness and budgets per building class | Done | [`docs/progress/AG2`](progress/AG2) |
| AG3 | Street fronts: a shopfront per unit by use, doors, lobbies, docks, garages, awnings, sign boxes, mounts, party and blind walls; walkable doorways in Unreal | Planned | |
| AG4 | Roofs and connections: roof equipment for every roof item, helipads, green roofs, facade details, skybridges, sky tube portals and stations | Planned | |
| AG5 | Types, landmarks and slopes: per-type generators, complex families, hero landmarks, buildings on M13's slopes, the art-direction loop | Planned | |
| AG6 | Materials and textures: the shared library per era, trim sheets, decals, window interiors, signage atlases, per-building parameters; textured master materials in Unreal | Planned | |
| AG7 | Street elements: roads with markings, sidewalks, bridges, viaducts, interchanges, tunnels, quays, transit structures, megasite elements | Done | [`docs/progress/AG7`](progress/AG7) |
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
  equipment blocks; spiked rings and pinched courts cleaned; every part closed; on M13's
  slopes the pivot at the building's `base_m` and a plinth under every mass on the base,
  down into the lowest ground under the footprint (`shell.plinth_mm`; AG5 steps it);
- **proxies** (`proxy.py`, at most 500 triangles) and **collision** (`collision.py`: convex
  pieces per mass, boxes where rectangles);
- **`assetgen build`** (`assetgen/build.py`, `manifest.py`, `asset_checks.py`,
  `contribution.py`, `buildings/envelope.py`): briefs kept when their inputs are, asset hash
  per building, 256 m tile packs made in up to 4 worker processes where hashes changed,
  manifest, report, `unreal_contribution.buildings.json`, files written only when their
  bytes change; checks `asset_coverage`, `asset_envelope`, `asset_meshes`, `asset_unique`,
  `asset_budget`; then AG7's street stage (`--no-streets` skips it; its report written only
  when another of its files changed, so an unchanged rebuild writes no file), one verdict
  for both;
- **`assetgen preview`** (`previews.py`, `blender/preview_assets.py`): the city from proxies
  (and with every shell), districts and the blockout's street cameras at full detail,
  contact sheets per type and one of 64 buildings across the city, on the blockout's
  city.blend without its building boxes;
- tests `tests/assetgen/test_ag_shell.py`, `test_ag_build.py`; goldens under `ag1` (the small
  city's manifest and asset files, nine Vesper Bay shells as GLB).

**Samples** (all five checks pass in each; 4 workers on the shared Mac):

| City | Buildings | Shell triangles | Of section 11's estimate | Packs | Build |
|---|---|---|---|---|---|
| Vesper Bay | 5,793 | 21.8 M | 0.59 | 1.29 GB | 50 to 119 s |
| Saltreach Free Port | 3,135 | 15.4 M | 0.76 | 0.91 GB | 46 s |
| Delta Megacity | 5,417 | 24.0 M | 0.65 | 1.41 GB | 75 s |
| Nexus City | 6,519 | 21.5 M | 0.59 | 1.27 GB | 71 s |
| Greyhook | 2,460 | 9.8 M | 0.48 | 0.58 GB | 23 s |
| Vesper Bay Pinned | 6,658 | 20.6 M | 0.54 | 1.22 GB | 62 s |
| Vesper Bay Stacks | 6,686 | 20.1 M | 0.55 | 1.19 GB | 63 s |
| Cragmouth | 6,800 | 22.7 M | 0.57 | 1.33 GB | 74 s (3 workers), streets 7 s more |

About 58 bytes of glTF per shell triangle (positions, normals and UV0 everywhere; UV1 and
colors on glass only); proxies 7 to 498 triangles (median 23 to 40). A second build writes
no file (3 to 14 s). Uniqueness: nearest pair outside a family 4.4 to 6.1 apart (k = 4).
Cragmouth (M13, merged after AG1's first builds): 4,359 plinths.

**Mac = x86** (run before the validation rule deferred it to `docs/determinism_check.md`):
whole-city builds of Vesper Bay and Greyhook byte-identical in `citygen-x86` (279 and 171
files); AG1's tests passed there, the small city's goldens included.

**Exporter**: M15 was not on main, so only the contribution file
(`unreal_contribution.buildings.json`); `unreal_export.md` ("From AG1") lists the exporter
work. No Unreal check yet (the coordinating session's call).

**For later milestones**: AG2 gets about 40% of section 11's triangle estimate for parts
(reveals are in the shells for now), the other facade systems (`systems.FALLBACK`), massing
articulation, wear and the thumbnail hash; AG3 storefront detail and doors (mount panels
already keep mounts off the glass); AG4 roof equipment (blocks now), skybridge landings and
portals; AG5 per-type and landmark generators; AG6 reads the slots, tints, UVs and CPD
layout as the material contract; citygen: footprints with zero-width spikes, self-crossing
rings and pinched courts (`rings.tidy` cleans them).

## AG2: facades

**Built.** Facade parts, the remaining facade systems, massing articulation, irregularity,
the thumbnail half of the uniqueness check and budgets per building class
(`assetgen/buildings/`):
- **parts** (`parts.py`): windows (frame by style, sill, lintel), mullion and transom caps,
  spandrel panels, balconies (rail, solid, enclosed, glass), louver panels, fins and crown
  fins, sunshade blades, shutters, grilles, boards, infills, screen blades, egg crates and
  add-on boxes, structural members (columns, beams, diagonals cut level at their nodes),
  capsule pods, window AC units, dishes, arcade columns, balconettes, podium canopies, masts
  and spires. Each is made in its own frame from quantized parameters (whole centimeters,
  5 degree steps), named `part.<type>.<style>.h<hash>` by its parameters (the `h` keeps
  Blender from reading a trailing number as a copy suffix), and closed (the mesh check runs
  on every part mesh). Within a building a part placed 8 times or more is instanced
  (`INSTANCE_MIN`), else merged into the shell by slot (unless turning it to its facade and
  rounding to the millimeter would fold a triangle: `survives`);
- **systems** (`systems.py`): the thirteen remaining facade systems of 5.1.2 (spandrel
  ribbon, fin wall, diagrid, exoskeleton, board-marked concrete, stucco with shutters,
  timber infill, tiled eaves, standing seam, louvered industrial, capsule stack, the
  perforated clean-tech skin, hangar cladding), so `FALLBACK` is empty and every era
  draws its own systems; floor ranges per system (`FLOORS`, with a stand-in outside them),
  frames, sills, balconies and the system's feature per entry; industrial systems a roof
  palette of their own (galvanized and coated metal, white membrane, tar) and a dado (a
  block or concrete base band 1.2 to 3.6 m high) on their ground walls;
- **genome** (`genome.py`, `GENOME_VERSION` 2): per group frame, sills, balcony type and
  pattern (residential and hotel uses only), the system's feature genes and part sizes; per
  building corner cut, setback, canopy, arcade and their sizes by the era's weights
  (`systems.ARTICULATION`), the dado, and `irreg`, quantized from grime, the district's
  wealth and a building's own rate; `effective` keeps every gene a shell used (part
  families, articulation, crown, irregularity);
- **articulation** (`articulate.py`): chamfered and rounded corners (convex, 60 to 120
  degrees, between free facades, on every mass with a vertex there), setback ledges on
  towers of 14 floors and more, stepped and halo crowns, masts and spires, arcades with
  the floors above cantilevered over them, podium canopies over the ground floor, the
  mechanical louver bands of AG1;
- **grammar** (`shell.py`): punched window widths from the genome's bay snapped to 5 cm,
  so frames repeat across facades; door rows and balconies only where the facade has room
  over a sidewalk, lot or park (`Facade.room`), once per bay; ribbons for spandrel ribbon
  walls; caps, fins, members and timber on the bay lines; eaves and ribs as strips;
  irregularity (boards, infills, replaced frames, AC units, grilles, dishes, add-on boxes,
  shutters left open) by `irreg`; pockets at a convex corner keep clear of it;
- **envelope** (`envelope.py`): parts by reach (flush up to 0.16 m out, strips as AG1's,
  deep up to 1.81 m out at 3 m and higher; masts and spires within `mast_cap` over the
  highest roof), instanced parts by the corners of their boxes;
- **thumbnails** (`thumb.py`): each building drawn as the contact sheet frames it, 64 px,
  by a small z-buffered rasterizer (shell triangles and the boxes of parts that stand out),
  shaded by slot tint; a 480 bit difference hash over 16 x 16 blocks;
- **checks** (`asset_checks.py`): `asset_unique` also asks every pair of buildings outside
  a family to differ by 8 bits of their thumbnails (a building filling under 10% of its
  thumbnail, a long thin shed, is told apart by its genes alone); `asset_budget` per class
  (low, mid, high, tower, mega by height and type): unique triangles at most k times section
  11's estimate for the building's bays and roof plus a base, instances at most i per bay
  plus a base, and the city's part meshes within 40% of its shell estimate;
  `asset_meshes` covers the part packs;
- **build** (`build.py`, `GEN_VERSION` ag2.7): a part pack per tile, `parts/<tile>.glb`,
  one root node per part mesh; the building record's `parts`, `instances`,
  `part_triangles`, `thumb`, `thumb_fill` and `class`; the report's parts line and
  instances by part;
- **previews** (`previews.py`, `blender/preview_assets.py`): parts as one geometry-node
  instancer per pack picking each point's mesh from the pack's collection, with their
  building's tints (`--no-parts` leaves them out; a node group per part mesh and the glTF
  importer's per-mesh deletions made a whole city quadratic to load, so the importer's
  temporary objects now go in one batch), proxies only where a view needs them, whole
  cities at 16 samples, towers of each era (`--views towers`), contact sheets with every
  building's parts;
- **exporter** (`contribution.py`): each building entry's `parts` (kind, type, glb, node,
  asset, count, triangles, xforms, building) and `instances` (`unreal_export.md`, "From
  AG2");
- tests `tests/assetgen/test_ag_facades.py` (new), `test_ag_shell.py`, `test_ag_build.py`;
  goldens regenerated (below).

**Samples** (every check passes in each; 4 workers on the shared Mac):

TABLE

**Goldens**: written again on the Mac (`tests/assetgen/goldens.py --builds`): AG2 changes
every shell (punched widths, articulation, dado, merged parts) and adds the part packs, so
the small city's manifest and files and the nine Vesper Bay buildings move; the briefs, the
spike and the triangulation do not.

**Found in the sample builds**: plain industrial sheds of one size drew the same thumbnail
in Nexus City and Delta Megacity (3 to 7 bits apart; their metal walls and dark roofs left
nothing for 4 px blocks to tell apart), hence the dado and the industrial roofs (13 to 81
bits after); three long warehouses in Delta filling 5 to 8% of their thumbnails, hence the
sliver line at 10% (under 0.4% of any city's buildings); a bay with paired windows placed
its balcony twice (now once per bay, `test_no_part_is_placed_twice`); diagrid pockets at a
convex corner met (now kept a reveal plus 6 cm from it).

**Exporter**: no code change; the parts are in the contribution in the format of
`unreal_export.md` ("From AG2"). The exporter's parts import was in its own open PR (`claude/ag-unreal-layer`), so no test of the
exporter's manifest with AG2's parts here; its `build_manifest` took Vesper Bay's
contribution (EXPORT). Unreal check: the coordinating session's call.

**For later milestones**: AG3 storefronts, doors, lobbies and docks (the ground band is
still AG1's storefront glass and door gaps; the arcade and canopy leave room for them); AG4
roof equipment (blocks), shed roof forms, skybridge landings and portals; AG5 per-type
generators (shanty and industrial sheds share the generic grammar; the thumbnail check's
slivers are long sheds), landmarks and stepped plinths on slopes; AG6 materials per slot
(the slots and tints are the contract; parts carry their building's CPD); the determinism
check (Mac = x86) waits for `docs/determinism_check.md`.

## AG7: street elements

**Built.** Package `assetgen/streets/` (CLI `assetgen streets BUILD [--spec S] [--workers N]
[--force]`, the short form of `assetgen streets make`; `assetgen streets seam BASE REGEN
--district NAME`):
- **Pieces** (`pieces.py`, `build.py`): one per citygen id (road segment, sidewalk, crosswalk,
  junction, bridge, column, tunnel, open approach, portal, vent, quay, waterway, transit
  structure, station structure, megasite element group, M13 retaining wall), gathered into the
  canonical inputs its maker reads (the entity, the neighbors it meets, its district's style,
  the ground under it); its hash is digest(maker, version, inputs). A tile's hash is that of
  its pieces' hashes, `STREETS_VERSION` and a hash of the street code itself, so a code change
  remakes every tile and an unchanged tile is neither made nor written. Up to 4 worker
  processes (`ASSETGEN_WORKERS`), tiles assembled in sorted order.
- **Mesh kit** (`kit.py`): integer millimeters in each piece's frame (origin the middle of its
  box on the 0.01 m grid, z 0), grids along a road (`grid`), polygons (`poly`, `poly_map`,
  triangulated by AG0's exact triangulator), swept cross-sections (`sweep`, the profile
  clockwise for outward faces), walls, boxes, oriented boxes, beams and cylinders; every
  triangle with an expected facing drops when it folds over (a sharp bend's inner edge) and
  when it is degenerate; normals summed from exact integer cross products; `check` per slot
  (degenerate, duplicate, winding: no directed edge used twice and explicit normals that agree
  with their face, indices, UV and normal ranges). Lean glTF (POSITION, NORMAL, UV0 in meters
  along the road, no UV1 or COLOR_0).
- **Roads** (`roads.py`): the carriageway between its junctions' cut edges (the first crossing
  of the centerline with the junction polygon; the cut edge's ends map onto the carriageway's
  corners), asphalt by class, lane lines, center lines, edge lines, stop lines 1.2 m before a
  crosswalk (else 1.5 m from the cut) and arrows from the model's lanes; manholes, drains and patches by the district's
  grime and wear; medians (curbed islands with lawn, highway barriers and outer guard walls);
  decks (a box girder sweep, parapets, expansion joints every 45 m, underside lights over 4 m)
  and embankments, chosen as the blockout chooses them (`deck_kind`).
- **Sidewalks, crosswalks, junctions** (`walks.py`): the slab in the district's paving family
  (`materials.PAVING`), granite or concrete curbs by era, the curb face, a back face to the
  lot (to the deck on a raised road), dropped curbs at crosswalks and at garage, loading and
  gate entrances (and parking), grates under the street trees; zebra or ladder crosswalks with
  tactile paving on the dropped curb; the junction polygon (holes under 4 m2 or touching the
  outline dropped, the height blended from each leg's cut edge by inverse distance, a deck slab
  under a raised junction) and the sidewalk corners between legs: the sector between two legs'
  sidewalk edges and M2's property-line fillet (`_corner`, replicated), less the junction
  polygon and the corners already made, by citygen's snapped overlays; walls only on edges used
  once. Vesper Bay: 4,370 corners, 13 left out (7 with no sidewalk on a leg, 5 with two legs
  cut by one edge, 1 whose fillet would not chain).
- **Structures** (`structures.py`): bridges by kind (girder with wall piers every 40 m over
  the water and abutments; named crossings an arch, or cable-stayed over a 250 m span with H
  pylons and stay fans; footbridges stone with an arch ring in heritage districts, else steel
  with railings; steps where their ramps are stairs; a named footbridge with no road gets a
  deck from its line); columns with pier caps; road tunnels (tile-lined walls, roof, soffit,
  light strips), portals (headwall, reveals, coping), open approaches (walls to a parapet over
  the terrain), metro and pedestrian tunnels (lined boxes with track or walkway), underpass
  stair wells, ventilation buildings.
- **Water** (`water.py`): quays (paving, coping, wall to the water, bollards every 12 m,
  stairs every 60 m), canal, basin, inlet and marina walls with copings; creeks keep their
  natural banks (declared, not missing).
- **Transit** (`transit.py`): elevated rail troughs with slab tracks and rails, monorail beams,
  maglev T guideways; sky tubes (floor and ribs Nanite, glass a separate non-Nanite entry
  `<id>.glass` with a LOD chain of 24, 12 and 6 sides at screen sizes 1.0, 0.25, 0.06);
  transit columns; station platforms, skywalks, canopies, covered walkways, elevator cores and
  concourses; M13's retaining walls.
- **Megasites** (`sites.py`): container stacks as instances of six liveries
  (`streets/parts.glb`, transforms in the contribution), gantry cranes, fuel tanks, launch
  pads and lattice towers, berths, rail tracks, truck gates, aprons and flats.
- **Exact replaces** (`ctx._blockout_keys`): citygen's own blockout functions (`_streets`,
  `_open_space`, `_sites`, `_tunnels`, and `_terrain` on an M13 model) run read only under
  `G.canonical()`, so each piece names the very objects M15 imports, and goes into the tile
  of the first of them.
- **Outputs**: `assets/streets/<tile>.glb` (a node per piece named by its id), `parts.glb`,
  `manifest.json`, `assets/unreal_contribution.streets.json` (AG0's format: one entry per
  piece with `replaces`, pivot, materials, Nanite, LODs, parts; `graphs.walkways` with the
  corrected z of every walkway on a raised road), `streets_report.json` and `.txt` (checks
  `street_coverage`, `street_meshes`, `street_replaces`, `street_budgets`, and stats);
  `preview_streets.png` (`preview.py`, drawn from the packs); street views in Blender
  (`assetgen/blender/streets_preview.py`: the blockout's `city.blend` with the replaced
  objects removed and the packs imported, its street cameras or `--eye/--target`).

**Ground (M13).** Written against M13's contract: a road on its `ground` grade line plus
its z profile, a junction at its node's `ground_m`, road tunnels and their portals and
approaches on their road's grade line, everything else on the finished terrain (bilinear as
M13's `Field.at`), ground 0 where the model has none. M13 merged into main near AG7's end
(main merged in; until then tested on its branch merged locally): Cragmouth builds with 12,729
pieces, every check passing, 1,280 retaining walls, 7 bored tunnels; a test lifts the small
city on a synthetic terrain; the flat samples are unchanged by M13.

**Samples** (M10 code, 4 workers on the shared Mac, stage time after loading the model):

| City | Pieces | Tiles | Triangles | Disk | Time |
|---|---|---|---|---|---|
| Vesper Bay | 10,955 | 148 | 1,187,649 | 74.8 MB | 6.2 s |
| Saltreach Free Port | 6,383 | 105 | 670,763 | 42.3 MB | 3.7 s |
| Delta Megacity | 10,489 | 137 | 1,185,401 | 76.1 MB | 6.9 s |
| Nexus City | 11,126 | 155 | 1,170,152 | 74.3 MB | 5.7 s |
| Greyhook | 4,590 | 90 | 605,711 | 37.1 MB | 3.1 s |
| Vesper Bay Pinned | 11,161 | 156 | 1,177,214 | 75.0 MB | 6.8 s |
| Vesper Bay Stacks | 11,540 | 157 | 1,227,541 | 77.5 MB | 7.4 s |
| Cragmouth | 12,729 | 130 | 1,226,030 | 83.6 MB | 8.5 s |

All four checks pass in every city; a rebuild with nothing changed takes 2 to 3 s and writes
no pack. Sidewalks are the largest share (Vesper Bay 441 k triangles), then roads (261 k),
junctions (180 k) and guideways (123 k). The scope's estimate of 10 to 20 M street triangles
per city was ten times what the packs need with markings as geometry only where they are.

**Regenerations.** M10's eight district regenerations over copies of their base packs write
17 to 34 tiles of 90 to 157; every changed piece is explained by its own entity or one it
reads (a junction, crosswalk, tree or door) changing in either build, the farthest 20 to
87 m outside the district, and no tile without a changed piece is written
(`docs/progress/AG7/regenerated/seam.json`).

**Determinism.** Same bytes for 1 and 3 workers and under another `PYTHONHASHSEED`; Vesper
Bay's, Nexus City's and Vesper Bay Stacks's packs, parts and contribution byte-identical on
the Mac and in `citygen-x86`, where the small test city's tests and golden pass too. Goldens
in their own file, `tests/assetgen/data/golden_streets.json` (the small test city and Vesper
Bay, its six heaviest tiles named), written by `tests/assetgen/streets_goldens.py
[--builds DIR]`. Tests: `tests/assetgen/test_ag_streets.py` (10).

**Unreal.** No exporter code changed (AG1 owns it). `unreal_export.md` gains the street
contribution's format and what the exporter still needs: read it as a second layer-2 file and
drop every actor a `replaces` names; the masters road, opaque, metal, emissive, translucent
(two-sided, blended) and foliage; complex collision; non-Nanite meshes with LOD chains;
hierarchical instances for parts; walkway z from `graphs.walkways`; the new keys in the
re-import digests. Not run in Unreal.

**Wiring.** `assetgen build` (AG1) is not on main yet: whichever of AG1 and AG7 merges second
makes it call `assetgen.streets.build.build(model, model_sha, BUILD/assets, spec, workers)`.

**Open.** Open spaces, green areas, ground and water stay the blockout's; markings and grates
are geometry a few millimeters over the asphalt until AG6's decals; river and sea banks have
no walls; the ramps of a named footbridge with no road are not in the model; M6's
`prop.barrier` blocks in highway medians stand on the road pieces' continuous barrier (AG8
should drop them where a road piece has one); the blockout's sea plane runs under the ground
over every tile and shows through the open approaches of road tunnels (a stage 1 fix; the
previews hide it with `--hide city.sea.`).

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
.venv/bin/python -m assetgen streets BUILD [--spec SPEC] [--workers 4]   # street packs (AG7)
.venv/bin/python -m assetgen streets seam BASE REGEN --district NAME    # what a regeneration changed (AG7)
.venv/bin/python -m assetgen review BUILD --prev P                      # art-direction round (AG5)
.venv/bin/python -m citygen unreal BUILD PROJECT                        # the city with its assets in Unreal
.venv/bin/python -m assetgen sweep --suite m8a --out DIR                # (AG9)
.venv/bin/python -m assetgen lock BUILD --release 1.0                   # (AG9)
```
