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
| AG3 | Street fronts: a shopfront per unit by use, doors, lobbies, docks, garages, awnings, sign boxes, mounts, party and blind walls; walkable doorways in Unreal | Done | [`docs/progress/AG3`](progress/AG3) |
| AG4 | Roofs and connections: roof forms and finishes, roof equipment for every roof item, helipads, green roofs, facade details, skybridges with landing doors, sky tube portals and stations | Done | [`docs/progress/AG4`](progress/AG4) |
| AG5 | Types, landmarks and slopes: per-type generators, complex families, hero landmarks, buildings on M13's slopes, the art-direction loop | Done | [`docs/progress/AG5`](progress/AG5) |
| AG6 | Materials and textures: the shared library per era, trim sheets, decals, window interiors, signage atlases, per-building parameters; textured master materials in Unreal | Done | [`docs/progress/AG6`](progress/AG6) |
| AG7 | Street elements: roads with markings, sidewalks, bridges, viaducts, interchanges, tunnels, quays, transit structures, megasite elements | Done | [`docs/progress/AG7`](progress/AG7) |
| AG8 | Props, plants and signs: prop variants per district style, trees by species, neon signs, billboards, holo-ads | Done | [`docs/progress/AG8`](progress/AG8) |
| AG9 | Scale and release: every sample modelled, `assetgen sweep`, the Windows check, `assetgen lock`, HLOD and Lumen settings at city scale | Planned | |
| AG10 | Layered districts: M14's slabs per tile with soffits, fascias, rails, lights and colonnades, their columns, stairs and elevators; the deck's streets on the slab and solid ramps; undercity roofs meeting the soffit; `asset_decks` and `street_decks` | Done | [`docs/progress/AG10`](progress/AG10) |
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
| Greyhook | 2,671 | 11.4 M | 0.49 | 0.67 GB | 26 s |
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
work. After M15 merged, a PR of its own did it: `citygen unreal` layers every
`assets/unreal_contribution.*.json` over the blockout, each shell an actor at its pivot in
place of its blockout box, with stage 2's masters reading the tints from Custom Primitive
Data (saved as the components' defaults) and convex hull collision; the contribution's
`asset` became the shell node's Interchange name (`<key>_shell`) and the patch slots spell
out their tint rule (the small city's `testport_files` golden moved with them). Greyhook
and Cragmouth imported, imported again and checked (`docs/progress/AG1/unreal/`).

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
  shaded by slot tint; over 16 x 16 blocks a difference hash (480 bits: the drawing's
  structure) and each block's mean shade in four steps (1,024 bits: its tone);
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

| City | Buildings | Shell triangles | Part meshes (triangles) | Part instances | Merged | Unique triangles (of budget) | Drawn | Nearest thumbnails (bits) | Packs (shells + parts) | Build |
|---|---|---|---|---|---|---|---|---|---|---|
| Vesper Bay | 5,793 | 26.2 M | 13,875 (0.8 M) | 1.3 M | 131,282 | 27.0 M (0.53) | 88.0 M | 24 | 1.54 GB + 67 MB | 396 s |
| Saltreach Free Port | 3,135 | 16.0 M | 9,068 (0.5 M) | 0.9 M | 65,477 | 16.5 M (0.58) | 58.0 M | 20 | 0.94 GB + 41 MB | 43 s |
| Delta Megacity | 5,417 | 27.2 M | 13,366 (0.7 M) | 1.3 M | 125,209 | 27.9 M (0.54) | 84.9 M | 21 | 1.59 GB + 57 MB | 93 s |
| Nexus City | 6,519 | 26.4 M | 14,443 (0.8 M) | 1.1 M | 145,183 | 27.2 M (0.53) | 79.9 M | 13 | 1.55 GB + 63 MB | 155 s |
| Greyhook | 2,671 | 13.9 M | 10,244 (0.6 M) | 0.8 M | 62,490 | 14.5 M (0.45) | 53.3 M | 30 | 0.82 GB + 49 MB | 57 s |
| Vesper Bay Pinned | 6,658 | 26.5 M | 14,673 (0.9 M) | 1.2 M | 152,488 | 27.3 M (0.51) | 83.7 M | 25 | 1.56 GB + 72 MB | 88 s |
| Vesper Bay Stacks | 6,686 | 25.8 M | 14,421 (0.8 M) | 1.1 M | 151,018 | 26.6 M (0.52) | 79.8 M | 17 | 1.52 GB + 70 MB | 96 s |
| Cragmouth | 6,777 | 27.3 M | 13,165 (0.7 M) | 1.0 M | 159,127 | 28.0 M (0.52) | 73.9 M | 30 | 1.60 GB + 60 MB | 88 s |
| Vesper Bay Decks (checks only) | 5,856 | 25.8 M | 13,834 (0.8 M) | 1.2 M | 132,424 | 26.6 M (0.51) | 84.1 M | 16 | 1.51 GB + 66 MB | 102 s |

Build: the building stage of `assetgen build` with 4 workers on the M4 Pro, shared
with other sessions' Unreal, Blender and test runs while these ran (load 10 to 50):
43 to 155 s, Vesper Bay's 396 s under the heaviest load.

**Goldens**: written again on the Mac (`tests/assetgen/goldens.py --builds`): AG2 changes
every shell (punched widths, articulation, dado, merged parts) and adds the part packs, so
the small city's manifest and files and the nine Vesper Bay buildings move; the briefs, the
spike and the triangulation do not.

**Found in the sample builds**: plain industrial sheds of one size drew the same thumbnail
in Nexus City and Delta Megacity (3 to 7 bits apart; their metal walls and dark roofs left
nothing for 4 px blocks to tell apart), hence the dado and the industrial roofs; then
sheds whose roofs differed only in tone (a white membrane and galvanized metal, tar and
dark grey) were still 5 to 7 bits apart, since a difference hash keeps only the signs of
gradients, hence the tone bits (23 to 70 bits after); three long warehouses in Delta filling 5 to 8% of their thumbnails, hence the
sliver line at 10% (under 0.4% of any city's buildings); a bay with paired windows placed
its balcony twice (now once per bay, `test_no_part_is_placed_twice`); diagrid pockets at a
convex corner met (now kept a reveal plus 6 cm from it); a terraced tower over 100 m on
Vesper Bay Decks with paired windows (two openings a bay, about 56 shell triangles a bay)
came to 1.03 of the tower class's budget at $k = 1.8$, hence $k = 2.0$ for towers, as for
high and mega buildings.

**Exporter**: no code change; the parts are in the contribution in the format of
`unreal_export.md` ("From AG2"), and the exporter's stage 2 import (merged while AG2 was
built) takes them: `tests/test_unreal.py::test_stage2_takes_assetgen_parts` (every listed
part an instanced actor `<key>.<kind>` with the entry's pivot, Custom Primitive Data and
transforms, its mesh a node of the tile's part pack, AG2's slots as materials); Vesper
Bay's manifest has 14,280 instanced actors for its buildings' parts, all 1,306,362
instances of its contribution. Unreal check: the coordinating session's call.

**For later milestones**: AG3 storefronts, doors, lobbies and docks (the ground band is
still AG1's storefront glass and door gaps; the arcade and canopy leave room for them); AG4
roof equipment (blocks), shed roof forms, skybridge landings and portals; AG5 per-type
generators (shanty and industrial sheds share the generic grammar; the thumbnail check's
slivers are long sheds), landmarks and stepped plinths on slopes; AG6 materials per slot
(the slots and tints are the contract; parts carry their building's CPD); the determinism
check (Mac = x86) waits for `docs/determinism_check.md`.

## AG3: street fronts

**Built.** The ground band of every building (`assetgen/buildings/fronts.py`, the part kit's
street-front families in `frontparts.py`):
- **band** (`band_top`): every prism mass on the ground (for a building on an M14 deck, on
  the deck's top: `shell.ground_mm`) has a band from its foot to its first floor line (the
  whole mass when less than 1 m is left above, at most 7.5 m), built apart from the rest of
  the shell as the building's second mesh (`<id>.front`, layer 1 of the mesh buffer,
  `meshbuf.split`). Per zone (the industrial dado or the base strip, then
  the wall) the wall is one polygon with the openings as holes, or as notches where they
  reach the pavement (`_pieces`: every zone line meets the openings of the zone beside it,
  so no T-junction); each opening a pocket (head, jambs split at the zone line, sill unless
  it is a notch, the pane at the back); the cap under the mass notched at every notch, the
  cap at the top the interface with the shell above, so both meshes are closed. Upper
  regions over a party region are fire walls (`firewall`, no windows). A pocket keeps off
  the corners (`_clear`), off other edges of the mass (`_blocked`) and off the recesses
  already cut down to the pavement on the other facades (`_meets`: two recesses either side
  of an acute corner);
- **shopfronts**: one per ground-floor unit by its use (food, bar, club, arcade, cyberware,
  clinic, pawn, convenience, laundromat and the rest): frame by the genome's front genes
  (aluminum, painted, steel, timber), riser (tile, stone, dark, paint, wall), a recess of
  0.25 to 0.45 m by use, transom, mullions, a door at the unit's entrance (glass, panel, barred, revolving),
  shutters (box, half down, down) and grilles by grime and wealth, counters for food,
  frosted glass for clinics, posters, a light box, screens for arcades, a dark club front
  with its canopy and a rope queue, neon on the fascia; the fascia plate over the opening is
  where AG8's sign box and awning hang (the opening's head stops under a mount);
- **doors**: a door at every entrance the units do not take: main (one or two leaves of the
  genome's style in a recess 0.45 to 0.9 m deep, steps up inside it, a canopy over it where
  the facade has room and no podium canopy), service, loading dock (opening 1.2 m up, steel
  lip, bumpers, seal) or roll-up door, garage mouth (height bar, barrier arm, half-raised
  grille), yard gate. A door that cannot be cut where the model has it shifts up to 1.2 m
  along the facade, then into the corner piers (a short facade), else hangs flush on the
  wall (always on a band too low for a door: a platform, a dock's plinth); a main
  entrance between two units keeps room for its own door (the shopfronts stop short: a
  lobby between the shops); a unit or entrance the model put on a wall a neighbor stands
  against, or on a facade too short for it, goes to the nearest facade of its mass with room
  and not into a court (`Band.rehome`, in place of the ground windows there) else flush on
  the nearest band facade, open walls first (`leftovers`), marked `moved`. Each door's record: id (`<building>.door.e<k>` or
  `.u<k>`), kind, entrance or unit, use, walkway, position, outward normal, size, depth,
  steps, flush, moved, class;
- **mounts**: AG1's panels wherever a mount would fall on glass now also cover awnings;
  plates behind wall lights and cable ends, trellises under facade greenery, scaffold ties on
  the piers behind scaffolding (`hardware`); downpipes on blind and fire walls and murals on
  fire walls of 5 x 5 m and more (`walls`);
- **decals** (`_decals`, cells of AG6's decal atlas, at most 14 a building): grime along the
  foot of the wall, leaks under the band's windows, rust beside metal doors, graffiti on
  blank stretches by grime and the district's danger (more on alleys, blind and fire walls),
  posters and stickers on the piers between shopfronts, cracks and moss on blind walls by
  wear and greenery. A tile's decals are one mesh of quads 1 cm off the walls in its pack
  (`decals.<tile>`, a primitive per cell, UV0 0 to 1 over each quad): mesh decals in
  Unreal, alpha quads in Blender;
- **genome** (`GENOME_VERSION` 3): front frame, riser, door style, steps, fascia and paint,
  recess depth and shutter share, drawn under purposes of their own (`front.*`), so every
  earlier gene keeps its draw; `effective` adds the front genes a building used;
- **collision** (`collision.py`): a ground mass's hulls start at the band's top; the front
  collides as drawn in Unreal (complex collision);
- **checks** (`asset_checks.py`): `asset_access` (a door at every entrance and unit, each
  open to its walkway: a step out of the doorway, 1 m, else 3 or 6 m past a corner of its
  own that juts beside it, then straight to the walkway's nearest point with no building in
  between; the model's walkway when it reaches it, else the ground walkway in front of the
  door, written into the record for stage 4; a door facing a neighbor or with no walkway
  within 15 m ahead (a road without a sidewalk on its side, open ground, a canal) is
  reported, not failed: the model put the entrance there) and
  `asset_mounts` (every sign slot, mounted prop and facade plant on a panel or pier, never
  on glass, `fronts.mount_check`; one on a stretch of its edge the shells tidy away, a spike
  of the lot's ring (all of the edge or all but a stub of it, `ShellBuilder.kept`), or over
  or under every wall of its edge, a shop sign over a low building under an M14 deck, is
  reported apart); on a deck city the access check's paths are blocked only by
  buildings of the door's own level; `asset_budget` counts 1,500 triangles per ground-floor
  unit and per street front on top of section 11's estimate;
- **build** (`build.py`, `GEN_VERSION` ag3.5): the front node beside the shell in the tile
  pack, the decal mesh per tile, the record's `front` (node, triangles, slots, `band_m`),
  `doors`, `checks.mounts`, `checks.doors`, `level` on a deck, and the stats' units and
  decals; materials: every AG3 slot in AG6's catalog (doors, steps, steel, rubber, roll-up
  doors, stanchions, fascias, mounts, trellises, pipes, risers, lit faces, neon and screens,
  paints, posters, graffiti, murals; a bar's dark glazing its own interior row), decal slots
  `decal.<cell>` on the `decal` master with the cell's index;
- **previews** (`materials/preview.py`, `blender/ag6_preview.py`): AG6's textured previews
  now draw the fronts and decals with the shells, AG2's instanced parts (one geometry-node
  instancer per pack, the building's tints on each instance, the materials reading them from
  the instance), beside the props, plants and signs AG8 on AG6 draws;
- **exporter**: below;
- tests `tests/assetgen/test_ag_fronts.py` (new), `test_ag_facades.py` (the part kit has
  AG3's families; the band's top cap is a `structure` face), `tests/test_unreal.py`.

**Samples** (every check passes in each; 4 workers on the shared Mac):

| City | Buildings | Front triangles (shell) | Doors | Shop / main / service / dock / garage / gate | Flush | Moved | Facing a neighbor / nothing ahead | Mounts | Decals | Tile packs | Build |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Greyhook | 2,671 | 4.2 M (12.4 M) | 10,388 | 8,570 / 1,376 / 348 / 61 / 21 / 12 | 200 (1.9%) | 279 | 109 / 2 | 9,479 | 10,827 | 1.04 GB | 58 s |
| Cragmouth | 6,777 | 8.0 M (24.8 M) | 25,331 | 21,094 / 2,491 / 1,670 / 57 / 6 / 13 | 1,062 (4.2%) | 1,700 | 496 / 26 | 29,832 | 22,576 | 2.06 GB | 156 s |
| Vesper Bay Decks (checks only) | 5,856 | 7.3 M (23.9 M) | 22,710 | 18,989 / 2,335 / 1,280 / 82 / 11 / 13 | 992 (4.4%) | 1,510 | 466 / 12 | 26,654 | 20,341 | 1.95 GB | 130 s |

Front triangles are the street fronts' own (the shell's in brackets, without them); doors by
kind; flush doors hang on the wall (no recess fits, or the band is too low); moved doors
left a wall a neighbor stands against or a facade too short; "facing a neighbor / nothing
ahead" are the access check's reported doors (the model put the entrance there); mounts are
sign slots, wall props and facade plants checked against the band's openings. Build: the
building stage of `assetgen build` (tiles and checks), with other sessions' Unreal and
Blender runs on the machine.

**Goldens**: written again on the Mac (`tests/assetgen/goldens.py --sections ag1 ag6
vesper`, the new `vesper` section rewriting the Vesper Bay buildings alone): AG3 changes
every shell (the band cut out, its own node), adds the decal meshes to the tile packs and
the fronts and decals to the buildings' contribution, so the small city's manifest, files
and materials files and the Vesper Bay buildings move; the briefs, the spike, the
triangulation, the library pixels, the street and prop goldens do not. Written again
(`--sections ag1 ag6`) after merging AG8 on AG6 from main: the small city's files and
materials move again (AG8's textured props and the `ag6.2` library in the contributions),
its manifest is AG3's.

**Found in the sample builds**:
- M3 puts ground-floor units on walls a neighbor stands against: a shopfront row in the
  small test city had four of its six units on party walls. Their doors now move to the
  nearest open facade.
- Main entrances fall between two units, or just outside one, on facades the shops fill;
  hence the lobby room kept between the shopfronts.
- Short facades left no room inside their corner piers; hence doors into the piers.
- Shop signs hang 2 m up over narrow units; hence door heads stop under a mount.
- The access check's first straight path clipped a building's own corner where it juts out
  beside a door (Cragmouth); hence steps 3 and 6 m out.
- Some Cragmouth streets have no sidewalk on the building's side, so the only walkways
  "ahead" were across the block; hence "ahead" means within 15 m.
- On Vesper Bay Decks:
  - buildings under the slab blocked the paths of doors on it; hence buildings of the
    door's own level only;
  - shop signs at 5 to 6 m hang over 3.5 m undercity buildings, and street signs fall
    under buildings standing on the deck; these are reported apart;
  - a temple platform (1.5 m) and a loading-dock plinth (1.2 m) took a door taller than
    their band, which opened the band's top; hence no cut door in a band under 1.65 m.
- A lot ring with a 5 m spike carried a facade plant (Cragmouth); reported apart.
- Scaffolds stand 0.8 m off their walls, so none got ties until the filter allowed 1.5 m.
- Two sessions on different branches rewrite the shared texture library cache in turn
  (`~/.cache/cybergen/assetgen_library`, a few minutes each time); builds here used a
  folder of their own (`ASSETGEN_LIBRARY`).

**Exporter**: as `unreal_export.md` ("From AG3: street fronts, doors and decals"):
`citygen/unreal.py` (`fallback_full` in the mesh record and its hash, an entry's own `ids`
and `level` on its actor, door tags, `doors_of` and the `doors` flat graph) and
`citygen/ue/import_city.py` (the Nanite fallback at every triangle, `cg.door=` tags);
`tests/test_unreal.py::test_stage2_takes_assetgen_fronts`. Unreal check: with AG4's
(`docs/progress/AG4/unreal/`): fronts flush with their shells, doorways walkable into the
recess to the door, the hull from the band line, every door tagged and in the doors data
asset, decals on the walls; a one-floor building its front takes whole has an empty shell
node, which the exporter now leaves out (its entry's `triangles` counts the front's).

**Open.** Shell vertex colors for grime and edge wear are not written (the masters draw grime
from the ground by the building's dirt height, CPD, and read no vertex colors; COLOR_0 on
every slot and both masters would change), and frames, sills and seals map their sets by
UV0 in meters, not trim-sheet strips (a master path without the per-building UV offset is
needed): AG9, or a follow-up of AG6. Awnings stay AG8's props (their posts collide as AG8's
props do). Doors the city puts against a neighbor or before a road without a sidewalk are
reported, for the city to change. On a slope a building's front stands at its base (the
main entrance's ground), so on the downhill side its shopfronts sit over the blank plinth
down to the lowest ground, and AG8's awnings there hang on the plinth: AG5 steps the
plinths and the band with them. Buildings on a deck have their fronts on the slab (AG10
does the rest). Mac = x86 waits for the deferred determinism check.

## AG4: roofs and connections

**Built.** What stands on and between the buildings, in the shell builder's passes
(`assetgen/buildings/roofs.py`, `connections.py`, `details.py`, the part kit's AG4 families
in `roofparts.py`) and a stage of its own for the skybridges (`assetgen/skybridges.py`):
- **roof forms** (`roofs.plan`, before the masses are built; `build_form`): a pitched roof
  stands in the building's top floor (its attic: the mass's walls stop a floor lower), or
  for a one-floor shed in the top of its tall floor, so it never rises over the model's
  mass. Hip and gable (a rectangular top, the era's gable share), pagoda (curled corners),
  mansard (any other top, or where roof items need a flat top) by the crowns `pitched` and
  `pagoda_roof` up to 12 floors; sheds, warehouses, hangars and yards by their own gene
  (`roof_form`: sawtooth with north glazing, gable, barrel, flat); the aerospace crown
  `dome` a barrel vault. A ridge that would rise past the attic is flattened to fit, down to
  8 degrees (`FLATTEST`); a shed's own form needs a rectangle, else its roof stays flat; a
  window row that then starts on the street front's top keeps a 0.1 m sill strip.
  Eaves by the era (under 0.6 m) only on edges nothing stands against; a one-floor storey
  on another mass is all roof. AC units, tanks and antennas on a slope stand on steel
  dunnage down to it;
- **finishes and copings**: every flat roof open to the sky in its era's surface with a
  gravel field, a paver terrace or a membrane with a walkway (gene `roof_finish`); a metal
  or stone coping on every parapet (gene `coping`);
- **green roofs**: M3's green areas on the building as a planted bed 0.5 m in on its soil,
  a gravel border and a paver path through the larger ones (`green_roofs`, canonical
  geometry from citygen's `geom`, so a court touching the edge never breaks the mesh);
- **roof items** (`items`): an asset for every one: AC units (four styles), water tanks
  (timber, steel, panel), antennas (whip, dish, lattice), helipads and AV pads with their
  markings and edge lights, mechanical penthouses with exhaust stacks (merged, in the
  building's wall tint); billboards stay
  AG8's signs. An item under a corridor (a guideway or skybridge over the roof) is made
  lower: a shorter antenna, a squat panel tank, a penthouse without stacks
  (`roof_items_lowered`). Access huts on roofs of three floors or more, vents and skylights
  by roof area, the empty billboard frame crown of the neon era where no billboard stands,
  each only where `envelope.fits` (a skylight straddling a notch of the roof is moved);
- **parts** (`roofparts.py`): roof equipment (`ROOF`) is always instanced
  (`parts.INSTANCE_ALWAYS`, even once in a building), on slots that take no tint, so the
  exporter gathers it per tile; penthouses and billboard frames merge into the shell. Every
  part closed on integer millimeters, named by its parameters;
- **facade details** (`details.py`, after the grammar, on solid wall, off every mount,
  each placed only where `envelope.fits`): corner downpipes (AG3's pipe at the convex
  corners), fire escapes on three to eight floor residential, mixed and hotel buildings and
  shopfront rows (flats over the shops) of the eras that had them, kitchen exhaust ducts
  for food and bar units on a back facade,
  louvered wall vents by grime, cable conduits along a floor line by grime and low wealth,
  CCTV cameras over doors by danger. The line: AG3 keeps its street fronts, mounts and
  blind-wall downpipes; AG8 keeps every facade prop M6 places (AC units, wall lights, signs,
  awnings, scaffolding, overhead cables, ivy);
- **skybridges** (`connections.skybridge`, the skybridge stage): every model skybridge a
  piece of its own in its frame (x along its line, 0.15 m into each facade), by kind:
  enclosed (deck on a box girder, glazed walls between mullions, roof, lit soffit, collars),
  stack (a floor and a spandrel band per level), open deck (M3p's podium decks: paving,
  glass balustrades, planters), catwalk (a grating on two Warren trusses), cable (a light
  deck under two catenaries); packs `connections/<tile>.glb`, the manifest's `skybridges`,
  `unreal_contribution.connections.json`. In the briefs a skybridge's deck is in the
  building frame (M13: from each one's base);
- **landing doors** (`connections.landings_of`, `landing_ops`): the floor a skybridge lands
  on is a door row of its mass (sill 150 mm), the landing an opening of the bridge's width
  with a frame and two glazed leaves (at least 0.9 m wide for a catwalk or cable bridge,
  into a corner pier where the bridge lands there); a wall too thin for windows still takes
  the door where its mass reaches 0.5 m in behind it (`shell._depth`: a notch elsewhere in
  the footprint does not make the wall thin), and a mechanical floor a bridge lands on keeps
  its windows.
  A bridge landing at the ground floor (on M13's slopes, an open deck from a building
  standing higher) meets the street front; a deck off every floor line of its mass (M3's
  floor grids apart) is reported, not failed (`landing_records`, `why`);
- **portals and sky stations** (`connections.portals`, `station`, `mouth_frames`): where a
  sky tube passes through a tower, every mass across the portal's floors is split there and
  its portal storey cut by the tube's corridor (its top line from M5, 1 m clear round the
  7 m section, a sky station's platform footprint); the corridor's walls lined, a lit frame
  at each mouth that has room for it, the station's platforms on both sides of the tube
  with tactile edges. A tube that meets no mass at the portal's height (between a
  megabuilding's towers) has nothing to cut. No balcony or other part standing out of a
  wall comes within the tube's clear radius (`connections.in_tube`), as none enters a
  skybridge's corridor (`parts_off_portals`, `parts_off_bridges`);
- **decks and courts**: M3p's tower decks paved with glass balustrades and planters; a
  court on the ground paved, planters at its corners, galleries at the podium's floor
  lines;
- **briefs** (`BRIEF_VERSION` 2): `clearances` (the corridors of skybridges, guideways with
  their trains and sky tubes passing near the building, in its frame), portals with their
  tube's lines, diameter, station and platform.

**Checks** (`asset_checks`): `asset_clearance` (nothing a building adds inside a corridor,
every portal open; `envelope.clearances`; a tower's own sky tube is held to its portal's
test, the corridor's margin there being the lining, frame and platforms), `asset_roofs` (every roof item an asset, every
green roof of 4 m2 or more built, every portal cut or passing, every sky station with its
platforms), `asset_landings` (a door wherever a skybridge meets a floor line),
`asset_skybridges` (every skybridge a closed mesh); the envelope check knows roof
equipment (on a roof or inside the masses), courts, copings; a mount in a landing door is
counted apart (`in_landing`: M6 does not know where the bridges land). Every detail is
placed only where `envelope.fits` (its family's reach and its slots', as it may be merged),
and AG4's detail slots reach as their families. AG3 fix: a door `rehome` moves never slides
along its facade into a court (one Vesper Bay unit door, blocked by a neighbor there).

**Exporter** (`docs/unreal_export.md`, "From AG4"): roof equipment one entry per tile
(`roofs.<tile>`, parts only, a building id per instance, no collision), buildings' `replaces` the
blockout green-roof objects whose every green area they built (`green_replaces`), the
skybridges' contribution (an entry per skybridge by id, complex collision, `links`), a
stage 2 entry's `links` on its actor and tagged `cg.link=` by the importer
(`citygen/unreal.py`, `citygen/ue/import_city.py`); tests without Unreal. AG6: every new
slot in the catalog; the connections packs in the texel density check and `materials.json`.
Previews: `assetgen materials preview` draws the skybridges and leaves out the blockout's
skybridges and replaced green roofs; `--views city_full` every shell at once, textured. Its
import of a whole city was quadratic in Blender (the importer's temporary objects and the
replaced materials removed one by one, and AG6's materials set on slots linked to the mesh,
each of which walks every object of the file): they go in one batch per import now, and
the materials on the object wherever no other object draws its mesh (AG2's parts and AG8's
families go through geometry nodes, which take the mesh's materials;
`ag6_preview.import_glb`).

**Samples** (every check passes in each: the eleven building checks, AG7's streets, AG8's
props, AG6's materials; 4 workers on the shared Mac):

| City | Buildings | Shell triangles | Roof forms (mansard / pagoda / hip / gable / sawtooth / barrel) | Roof items (AC / tank / antenna / penthouse / helipad / AV pad; billboards) | Green roofs | Skybridges (enclosed / stack / open deck / catwalk / cable) | Landing doors (off a floor line) | Portals cut / passing, sky stations | Build |
|---|---|---|---|---|---|---|---|---|---|
| Vesper Bay | 5,793 | 31.97 M | 1,115 (969 / 38 / 24 / 26 / 50 / 8) | 15,597 (12,110 / 1,100 / 818 / 222 / 19 / 42; 1,286) | 494 of 494 | 258 (60 / 1 / 77 / 86 / 34) | 513 of 516 (3) | 14 / 6, 2 | 4:45 |
| Greyhook | 2,671 | 17.58 M | 293 (258 / 0 / 0 / 8 / 18 / 9) | 7,789 (6,176 / 672 / 75 / 308 / 0 / 11; 547) | 430 of 430 | 170 (43 / 0 / 127 / 0 / 0) | 338 of 340 (2) | 8 / 6, 1 | 1:56 |
| Cragmouth | 6,777 | 34.07 M | 1,269 (1,124 / 59 / 25 / 32 / 29 / 0) | 18,553 (13,974 / 1,229 / 1,109 / 556 / 11 / 34; 1,640) | 338 of 338 | 279 (75 / 0 / 54 / 99 / 51) | 533 of 558 (24, 1 at a ground floor) | none | 7:00 |
| Vesper Bay Decks (checks only) | 5,856 | 32.32 M | 1,024 (917 / 26 / 23 / 23 / 28 / 7) | 15,850 (12,267 / 1,109 / 836 / 249 / 16 / 36; 1,337) | 494 of 494 | 266 (57 / 1 / 81 / 84 / 43) | 531 of 532 (1) | 10 / 11, 2 | 6:48 |

Facade details (Vesper Bay / Greyhook / Cragmouth): fire escapes 143 / 20 / 147, kitchen
ducts 622 / 322 / 834, cameras 880 / 431 / 831, wall vents 2,998 / 763 / 4,114, conduits
1,739 / 694 / 2,026, corner downpipes 3,867 / 3,965 / 2,545; access huts 149 / 3 / 144,
skylights 874 / 452 / 1,047, roof vents 6,344 / 3,924 / 8,357. Skybridges 88,596 / 35,256 /
103,080 triangles. No sample has a roof item under a corridor (`roof_items_lowered`; the
tests build one). Builds: `assetgen build` whole (tiles, checks, streets, props, materials),
with other sessions' Blender runs on the machine. Images: `docs/progress/AG4/README.md`.

**Goldens**: written again on the Mac (`tests/assetgen/goldens.py --builds`, then
`--sections ag1 vesper ag6` after the last shell change, which moved nothing): briefs v2
change every brief (clearances, portal lines, skybridge decks in the building frame), so the
small city's briefs, the five samples' briefs and the Vesper Bay brief hashes move; AG4
changes every shell (roofs, details, landing doors), so the small city's asset digest and
the Vesper Bay buildings move; the buildings' contribution (roof equipment entries, green
roof `replaces`) and `materials.json` (AG4's slots) move AG6's digest. The props golden had
gone stale on main (main's own code writes `9ea0...` for the small city, the golden held
`3f78...`); main wrote it again meanwhile, to the same value, and AG4 changes nothing
there. AG7's streets golden is unchanged. After main's AG2 and AG6 Unreal check
(building parts without collision), the roof equipment entries and their parts say
`collision: {"none": true}` too, which moves the small city's file digest and AG6's
digest again (the buildings' contribution is in both).

**Found on the way**:
- A small-city tower whose footprint has a 1 m notch measured 0.3 m thick (the ring's
  least width), so its skybridge got no door: the door now asks how far the mass reaches
  in behind the wall it lands on (`shell._depth`).
- Vesper Bay Decks' sky tube passes megabuilding towers whose balconies reached into its
  clear radius beside the portal: such parts are dropped (`parts_off_portals`: 15 there and
  in Vesper Bay, 4 in Greyhook).
- `assetgen materials preview --views city_full` took over an hour on Vesper Bay without
  getting through the import (three quadratic steps in Blender, above).
- M6 places facade AC units where M3p's podium decks land (24 in Vesper Bay and Cragmouth,
  6 in Greyhook); the landing door wins and the mount check counts them apart, while AG8
  still draws the unit there (the city's to move).
- M5 puts a portal on megabuildings whose tube runs between the towers over the podium
  (6 in Vesper Bay and Greyhook, 11 in Vesper Bay Decks): nothing to cut, counted as
  passing.
- A few skybridge decks meet a building between two floors (M3's floor grids apart; on
  Cragmouth's slopes two buildings seated at different heights): reported, not failed.

**Exporter**: as above; `tests/test_unreal.py` (`test_stage2_skybridge_links`,
`test_stage2_takes_assetgen_roofs_and_skybridges`, and `test_stage2_from_assetgen` knowing
the roof equipment entries, which have no node). Unreal check (`docs/progress/AG4/unreal/`):
skybridges at their pivots with their links, floors walkable, reaching both facades; roof
equipment counts right, `NoCollision`, nothing floating; replaced green roofs gone. Open
from it: the hulls close the landing doors, and the sky station platforms lie inside their
tower's hull.

**Open.** For AG5: one mechanical penthouse family (variants by era), no dormers on the
pitched roofs, the plinths on slopes still one block (the landings at a ground floor and
the shopfronts over a plinth wait for the steps). In Unreal a building collides as its
masses' convex hulls, which close the landing doors: a walk across a skybridge meets the
facade (the landing floors want the street front's drawn collision, or hulls cut at the
door). Fire escapes are not
put on shanty stacks (their own clutter does the part). The blockout green-roof objects
that also draw a lawn stay in Unreal under AG4's beds (their plates sit under the gravel
border, so nothing flickers). Shell vertex colors and trim-sheet UVs stay open from AG3. The whole-city previews
draw AG8's props only near a perspective camera (AG6's preview), so parks read bare
there. Mac = x86 waits for the deferred determinism check.

## AG5: types, landmarks and slopes

**Built.** Generators per M3 type, heroes for the landmarks, buildings on M13's slopes, the
complex families' check and the art-direction loop, in the shell builder's passes
(`assetgen/buildings/types.py`, `heroes.py`, `slopes.py`, the part kit's AG5 families in
`typeparts.py`) and `assetgen/review.py`:
- **type generators** (`types.GENERATORS`; `pre` after the massing articulation, `mass` in
  the mass loop in place of the grammar, `post` after the masses): shanty stacks (lean-to
  sheet roofs over their top storeys, tarps on poles, water barrels, rough fire escapes and
  ladders up the stacks, stilt balconies), megablocks (antenna farms on the towers, service
  risers up their back walls, a neon band along the podium), warehouses and yards (canopies
  over loading doors, ridge monitors), sheds (open sides: the roof on steel columns two
  bays apart, walls only where a neighbour stands; doors recorded as open sides), hangars
  (a sliding door across the apron facade, its facade kept blank), labs (fume stacks),
  villas (a chimney through the attic, a pergola on a lower roof), terraced rows (planters
  and rails on every terrace), temple halls (a colonnade of lacquered columns on stone
  bases round the hall, the hall set back behind it, eaves over every tier, stairs cut
  into the platform, a finial), pagodas (eaves over every tier, a finial), gate houses
  (a canopy roof all round, a beacon), terminals and stations (a vaulted roof, canopies),
  control towers (the cab: a glazed band leaning out, mullions, a roof with a radome and
  antennas; a lit slot up the shaft), parking structures (ramps as sloped decks), straddle
  buildings (transfer girders under the span, lamps); the rest of M3's types stay the
  general grammar's. Everything a type adds goes through `types.put`: only where the
  envelope allows it (`envelope.fits`) and off every skybridge, guideway and sky tube
  corridor; counted (`stats.type_features`, by kind), the record's `generator` names it;
- **AG4's leftovers**: the mechanical penthouse by era (`roofs.PENTHOUSE_STYLE`: deco,
  screen, block, shed, louver); dormers on gable, hip and mansard roofs of the eras that
  pitch them (`types.dormers`: gabled or shed dormers one per 4.2 m on the long slopes,
  small gabled ones on a mansard's steep slope where the attic leaves room); shanty fire
  escapes (the shanty generator); collision that leaves the landing doors open
  (`collision.py`: a mass a skybridge lands on is cut into storeys at the door's floor and
  head, the door's storey notched the door's width and `VESTIBULE_MM` 2.5 m deep); a sky
  station whose tube passes beside its tower, not through it (M5 leaves Delta Megacity two),
  gets its platform there (`connections._beside`: the station's footprint on the tower's
  side of the tube and a deck across to the wall, `STATION_LINK` 6 m at most, cantilevered
  or resting on a roof up to 3 m under it, its floor under the tube's lowest point over the
  station; the envelope check lets the `platform` slot reach the station);
- **heroes** (`heroes.py`; every landmark and M3's megasite wheel): the general shell of
  the landmark's masses with its era system by kind (`systems.LANDMARK_SYSTEM`), its
  palette from the spec's landmark entry (walls the darkest colour, trim the lightest, the
  accent its most saturated) and per kind: the megatower's light seams up every arm tip,
  aviation lights on the tiers, sky gardens on the setbacks, a halo crown and a needle;
  the spire's seams at the octagon's corners, collars, a needle with rings and a beacon;
  the arcology's planted terraces with glass rails on every step, a glazed space frame
  over its atrium and a mast with dishes; the wheel built whole (twin rims tied by beams,
  rim lights, spokes to a hub and axle, 24 to 32 gondolas, lattice legs, a crossbeam).
  Every hero has a U2 mask (scope 13.2): 512 px, R grime (from the ground and washed down
  under every setback), G leaks (under its windows' sills), B wear (its corners and roof
  edges), integer-hash noise from AG6's library, in the hero UV (UV1 on every non-glass
  slot: u the UV0's u over its longest perimeter, v the height over the building's),
  written as `assets/textures/hero/<id>.png`; budget class `hero`;
- **slopes** (`slopes.py`; the brief's new `terrain`: the ground along every edge of a
  mass on the base, every metre, 0.3 m out): each facade's plinth in steps of about 4 m at
  their lowest ground (0.15 m risers), mitred at the corners, from 0.3 m under the step up
  to the base; doors and shopfronts at grade (lowered to the ground where it falls 0.3 m
  or more, into the plinth whole where they would end under the base, the band putting
  windows in their place; raised onto the ground where it rises 0.2 m or more, their head
  up to the band's top under what is mounted over them; narrowed to the stretch that can
  be raised where the hill climbs across a wide shopfront); lower-storey windows where a
  step is 2.7 m or more under the base; retaining skirts where the hill stands against a
  wall; the band's ground-row windows the hill would bury left out;
- **complex families**: twin towers one design to the last step (no member step on the
  continuous genes); clusters, campuses, bridged pairs and megasites share their discrete
  genes as before;
- **checks**: `asset_types` (every building by its type's generator, every hero with its
  mask; types the generators do not list counted apart), `asset_families` (the members of
  a family share the discrete genes of every group whose system they share; twins every
  gene), `asset_slopes` (every building whose plinth is 0.3 m or more stands on a stepped
  plinth; what the fronts did at grade counted);
- **art direction**: `assetgen review BUILD --spec S [--prev P]` writes `review.md` and
  `review.json` (the failed checks of every stage, numbers per district: eras, facade
  systems, type generators, wear; spec changes since the previous round; the previews to
  open; what to change in the spec for what one sees), `assetgen spec diff A B`; the
  skill's step 6 runs the rounds.

GEN_VERSION "ag5.0" (ag5.1 since the Unreal check's open shed fix), GENOME_VERSION 5;
briefs unchanged on flat ground (a hilly city's briefs gain `terrain`, BRIEF_VERSION stays
2).

**Exporter** (`docs/unreal_export.md`, "From AG5"): a hero's building entry carries `hero`
(kind, accent) and a `materials` map of its own (`<slot or era material>#<id>`: its U2 mask
`city.hero.<id>` as `HeroMask`, `HeroMaskOn` 1 on every slot of a textured opaque master;
its accent on its light slots, with or without AG6's library), its shell and front UV1 in
the hero UV; a building on M13's slopes carries `plinth_m`. `citygen/unreal.py` takes an
entry's `hero` and `plinth_m` onto its actor (in its hash; `stage2.counts.heroes`);
`citygen/ue/import_city.py` tags them (`cg.hero=<kind>`, `cg.plinth=<m>`) and gives the
textured masters `HeroMask` (sampled on UV1) and `HeroMaskOn` (0 by default) after their
surface (`HERO_CODE`: grime darkens, leaks stain, wear lightens), `STAGE2_VERSION` 6. The
buildings' hulls are notched at the landing doors (no exporter change: convex pieces as
before). Tested without Unreal by `test_stage2_heroes_and_plinths`; the Blender preview
draws the same (`ag6_materials._hero` on `UVMap.001`). Unreal check
(`docs/progress/AG5/unreal/`): Cragmouth and Greyhook imported and imported again; the
megatower and the wheel tagged `cg.hero=` with the mask on UV1 and `HeroMaskOn` 1, the
masters at `STAGE2_VERSION` 6, no other building with it on; Cragmouth's plinths meet the
terrain (732 of 976 corners at the wall, 210 buried uphill, 30 floating over a lower street);
landing doors open 2.5 m in (332 of 340 in Greyhook); open sheds' hulls blocked the walk
under the roof, fixed there (an open shed collides from its roof's underside, GEN_VERSION
ag5.1). Open from it: Cragmouth's 63,700 Nanite meshes overrun Unreal's root pages on the
Mac, so it cannot be played as exported; doors on slopes behind M13's retaining walls
(Greyhook's doors 1,989 of 2,000 at grade, Cragmouth's 325 of 710); the sky platforms beside
a tower have no collision; station platforms inside their tower's hull and garage mouths as
in AG4.

**Samples** (4 workers, 3 where the shared Mac was short of memory; every check passes in
each: the fourteen building checks, AG7's streets, AG8's props, AG6's materials):

| City | Buildings | Shell triangles | Type generators (buildings; features) | Heroes | Families (twin towers) | Dormers | Landing doors | Sky platforms beside a tower | On a plinth (stepped facades / skirts; doors lowered / raised / narrowed; buried) | Build |
|---|---|---|---|---|---|---|---|---|---|---|
| Vesper Bay | 5,793 | 34.52 M | 17 (2,598; 8,170) | megatower | 8 (1) | 331 | 513 of 516 | 0 | flat | 2m29s |
| Greyhook | 2,671 | 19.05 M | 14 (1,426; 4,227) | wheel | 7 (0) | 401 | 338 of 340 | 0 | flat | 1m19s |
| Cragmouth | 6,777 | 37.23 M | 10 (2,520; 11,882) | megatower | 4 (0) | 157 | 533 of 558 | 0 | 4,724 (33,923 / 30,123; 5,589 / 4,502 / 634; 2,196) | 4m31s |
| Delta Megacity | 5,417 | 35.21 M | 10 (2,099; 10,155) | megatower | 7 (1) | 154 | 647 of 652 | 2 | flat | 3m02s |
| Nexus City | 6,519 | 35.35 M | 19 (2,757; 11,107) | megatower, spire x3, wheel | 12 (1) | 340 | 468 of 474 | 0 | flat | 3m09s |
| Vesper Bay Decks (checks only) | 5,856 | 34.78 M | 17 (2,546; 9,373) | megatower | 8 (1) | 280 | 531 of 532 | 0 | flat | 4m20s |

On a plinth: buildings whose ground falls 0.3 m or more round their base (every one on a
stepped plinth); buried: doors and shopfronts the hill covers where it climbs past a whole
ground storey (left in place, counted). Build: the whole `assetgen build`.

**Art direction**: two rounds on Vesper Bay as the art director's stand-in
(`docs/progress/AG5/review/`: each round's `assetgen review` sheet, notes, before and
after). Round 1 found the Corporate Core's gold and red brand-coloured towers (an owner's
first two brand colours can paint whole walls), the spaceport's amber parking decks,
The Stacks without the capsule stacks the spec asks for, and Old Town's roofs nearly all
flat; round 2's spec moved the owners' accents to third place (trim only), weighted the
heritage era's pitched roofs two in four and raised The Stacks' capsule weight and wear.
The core and Scholar Isle now read as quiet glass and Old Town's pitched crowns went from
963 to 1,409; The Stacks' capsules did not come (capsule stacks are built only up to 40
floors, `systems.FLOORS`, and its towers are taller). The round 2 spec is now
`cities/vesper_bay/asset_spec.json`.

**Goldens**: written again on the Mac (`tests/assetgen/goldens.py --builds DIR --sections ag1
ag6 vesper`): every shell moves (the type generators, heroes, dormers, penthouse styles,
the collision notches at landing doors), so the small city's asset digest and the Vesper Bay
buildings move; the buildings' contribution and `materials.json` (AG5's slots, hero
materials) move AG6's digest. Briefs on flat ground are unchanged (the samples' brief
goldens hold); a hilly city's briefs gain `terrain`. AG7's streets and AG8's props goldens
are unchanged.

**Found on the way** (the city's, stage 1's to look at):
- M3's arcology leaves its top tier with no area and its crown 56 m over the last tier (the
  sample with an arcology made for the renders, Vesper Bay with The Stacks' landmark an
  arcology); AG5 leaves out a hero's unsupported masses and moves their roof items onto the
  roof under them (`hero_masses_unsupported`, `roof_items_moved`).
- M5 places two of Delta Megacity's sky stations (Corporate Core, Midtown) where the tube
  passes 1 to 3 m beside the tower at the station's height, on a track that climbs 1.5 m
  along the platform; AG4 built a platform only in a cut portal, so those stations had none
  (AG4's `asset_roofs` failed on them; Delta was not one of AG4's samples).
- M3 puts some temple halls' main entrance at a corner of the hall; behind AG5's colonnade
  the door comes onto the entrance's own wall, 2 m from the corner.

**Open.** For AG9: capsule stacks over 40 floors (The Stacks' towers); a hero glass darker
than AG6's interior-mapped glass (the megatower reads grey-blue, not the brief's
near-black); openings the hill buries where it climbs past a whole ground storey
(Cragmouth: 2,196 doors and shopfronts, left in place and counted:
`openings_buried`); an entrance on the uphill side of such a storey wants the floor above
(AG3's band is the ground floor only). The whole-city 8K renders stay AG4's (AG5 changes
read at street and district scale). Mac = x86 waits for the deferred determinism check.

## AG6: materials and textures

**Built.** Package `assetgen/materials/` (CLI `assetgen library [OUT] [--density 512]
[--workers 3] [--only ...]`, `assetgen materials preview BUILD [--views ...] [--night |
--only-night] [--width W] [--eye X Y Z --target X Y Z]`, `assetgen materials board OUT`;
`assetgen build` runs the stage after the street packs, `--no-textures` keeps AG1's flat
materials). Everything is generated in numpy and PIL (decisions 13.1, 13.3, 13.8), pixel for
pixel the same on every run:
- **Noise and surfaces** (`noise.py`, `surfaces.py`): integer-hash value noise, fbm, ridged
  noise and Worley cells (F1, F2, cell ids) on lattices that wrap at the tile's edge, warps,
  smoothsteps and wrapped blurs, all in elementwise float32 (no transcendentals, no float
  reductions). A surface is color, height, roughness, metallic, tint mask and occlusion; its
  generators: board-formed concrete, plaster and stucco, brick (running and English bond),
  precast panels, ribbed and corrugated metal, sheet, fabric, timber, paint, brushed and
  perforated metal, louvers, stone, flat roofs (membrane, gravel, tar), tiles (square,
  running, shingle, cobble), asphalt, grass and gravel; stains, rain streaks, grain, mottle and
  cracks layered on any of them. `pbr.py` packs a surface into base color (height in alpha),
  an OpenGL tangent normal and occlusion-roughness-metallic (tint mask in alpha), and gives
  each set its `ref` (the mean linear color where the mask is 1).
- **Library** (`library.py`, `atlases.py`, `interiors.py`): 113 tileable sets, 60 of them per
  era (concrete, plaster, brick, panel, cladding, roof in each of the ten eras, `ERA_LOOK`),
  the rest shared building surfaces (spandrel, trim, structure, metals, louvers, perforated,
  shanty patches, timber, shutters, sills, roof tiles, pods) and street surfaces (asphalt per
  class, patches, paint, cast iron, tactile, ten paving families, curbs, formed concrete,
  stone, glazed tiles, steel, ballast, lawn, containers, tanks, pads); 14 atlases: a trim
  sheet per era, the decal atlas (16 cells: grime, leaks, rust, cracks, graffiti, posters,
  stickers, moss), the road atlas (16 cells: oil, cracks, patches, tar snakes, skid marks,
  manhole, drain, arrows, puddle, sand, dust), the window interiors and a 64 m macro map. A set
  covers 1 to 4 m at the spec's `texel_density_px_m` (512, decision 13.4) on the street band
  and half that on flat roofs, so every map is a power of two. Made once per density in
  `~/.cache/cybergen/assetgen_library/d<density>` (or `$ASSETGEN_LIBRARY`) by up to 3 worker
  processes and kept while the generator's code hash is unchanged; `library.json` lists every
  file with its decoded-pixel sha256. At 512 px/m: 658 MB of PNG, about 969 MB cooked with
  mips and block compression, 59 to 80 s on the M4 with 3 workers (167 s while other builds
  ran).
  Not in git: each build links it as `BUILD/assets/library`.
- **Window interiors** (`interiors.py`, the redesign PR #41 asked for): rooms drawn in
  one-point perspective (the back wall at `BACK` 0.5 of the window, floor, ceiling and side
  walls) by a small ray caster, six uses (office, apartment, capsule, shop, club, warehouse)
  by eight variants, by day and lit by night, in one atlas each. The glass master needs no data
  per pane or per vertex: UV0 is meters along the facade and up from the base, so a room is a
  cell of the building's grid (its bay wide, a floor high, Custom Primitive Data 23 and 24),
  the view ray goes into the cell's box in the facade's tangent frame, and the point it hits is
  looked up in the atlas; a hash of the cell picks the variant, whether it is lit (the
  building's lit ratio, at 0.35 to 1 of full brightness) and its blinds. Shared pane corners,
  split panes and any triangulation give the same room, so the white triangles and sawtooth of
  the per-pane design are gone by construction. Storefronts always show the shop row. AG1's
  UV1 and window ids on glass are no longer read.
- **Signage** (`signage.py`, `glyphs.py`): per city, a cell for every M11 sign slot: the name
  of the place in its unit (bar, club, clinic, vendor, arcade), else a shop name from M11's word
  lists with a use word, a neon band's district name, a lobby's brand (an owner of 8 or more
  properties or a corporate faction) or building name; in a script drawn from the district's
  weights. Latin as written; Cyrillic, katakana and Hangul transliterated by syllable; Hanzi-like
  and Devanagari-like signs composed from strokes (decorative, not words); all from in-repo
  stroke shapes, as neon tubes, lightboxes or LED rows in the district's neon colors. Pages of
  4096 px (`textures/signs_wide_<k>.png`, `signs_tall_<k>.png`), a logo per brand, two ad pages
  (16 ads each, holo variants), `signs.json` (cells with their UVs in glTF's convention, slot
  to cell). Vesper Bay: 15,448 slots on 411 sign texts (165 wide, 246 tall), 15 brands.
- **Catalog and parameters** (`catalog.py`, `params.py`): every building slot (AG1's and
  AG2's) and street slot to a master and a set; walls and roofs per era (`ERA_SLOTS`, keyed
  `<slot>@<era>`, a building's entry maps its slots to its era's). Masters: `facade`, `metal`,
  `concrete`, `road`, `glass`, `neon`, `sign`, `decal`, plus AG1's and AG7's `opaque`,
  `emissive`, `translucent` and `foliage`. A tint replaces the set's `ref` where the mask is 1
  and leaves mortar, joints and rust as they are. Per building, seven channels after AG1's 23
  (`params.CPD_EXT`): room width, floor height, interior row (by use and type), streak
  strength, building top, blinds share, era index.
- **Contributions** (`contrib.py`): `unreal_contribution.buildings.json` and `.streets.json`
  gain `textures` (file under `library/` or `textures/`, pixel hash, kind color, normal or
  mask, sRGB), textured materials (master, set, textures by parameter, scalars, vectors) and
  the entries' era `materials`; `unreal_contribution.materials.json` carries the sign pages
  and the decal material. `materials.json` is the same table for the Blender previews.
- **Checks** (`checks.py`, in `materials_report.txt`): `texel_density` reads every pack's
  UV0 (the shells, AG2's part packs in their own frames, the street pieces) against the set it
  shows: per slot, at least 99.5% of the textured area at 0.75 of the
  band's density or better (buildings 100% in every sample; streets 99.5 to 99.9%, the rest
  tank cylinders, a few curb and barrier sides with plan UVs and the outer edge of tight
  curves, listed by slot); `texture_budget`: library under 2.5 GB cooked and 7 GB source, a
  city's sign pages under 0.3 GB cooked (Vesper Bay 69 MB).
- **Blender** (`assetgen/blender/ag6_materials.py`, `ag6_preview.py`, `ag6_board.py`): the
  same masters as node trees (tint over ref, macro, grime from the foot of the wall, streaks
  from the decal atlas, road stains per 8 m cell, the interior ray march, night switch), the
  previews on the blockout's `city.blend` with the shells and street packs, sign quads on the
  slots near a street camera and the street lights lit by night; boards per era.
- **Exporter** (`citygen/unreal.py`, `citygen/ue/import_city.py`, `STAGE2_VERSION` 4,
  `TEXTURE_VERSION` 1): textures imported once per pixel hash into `/Game/CityGen/Core/Textures`
  (the library, shared by every city) or `<City>/Assets/Textures` (signs), normal maps with
  green flipped; masters built from Custom HLSL nodes (`SURFACE_CODE`, `ROOM_CODE`,
  `GLASS_CODE`, ...) with `MPC_CityGen.Night`; a material instance per material with its
  textures, scalars and vectors; an actor's era slots set by name. The manifest's `stage2`
  carries `textures` (asset, folder, hash) and each material's textures with their hashes, so
  importing again changes only what moved. Test `test_stage2_textures` (no Unreal).
- **Validation**: the eight samples built (every citygen and assetgen check passes),
  previews and boards looked at, `pytest tests/assetgen` and `tests/test_unreal.py -k "not
  unreal_import"` pass. Goldens: `ag6` in `tests/assetgen/data/golden_hashes.json` (decoded
  pixels of seven maps of a 32 px/m library, the small city's material files);
  `golden_streets.json`'s contribution hashes and AG1's small-city contribution moved on
  purpose (textures, materials and CPD in the contributions); every pack is unchanged.
- **AG2** (merged before this): every slot of `systems.SLOTS` has its own catalog entry (a
  test holds it); its part packs are in the density check; the roof tile set is on the street
  band for its tiled eaves.
- **For later**: vertex colors in the shells (grime under sills, edge wear), AG3's; UV1 and window ids on glass can go; parts mapped onto the trim sheets
  (AG3); decals placed from the decal atlas (AG3). AG8's sign meshes now show AG6's pages
  and its props and plants take library sets (AG8's entry, "On AG6"). OFL fonts for
  real Hanzi, Hangul, kana and Devanagari (decision 13.3); the Unreal check of the masters
  (`docs/progress/AG6/README.md` lists what to look at).

Outputs: [`docs/progress/AG6`](progress/AG6).

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

**Greyhook after its reshape** (headlands and coves, builds on main since #35): 5,209 pieces
in 117 tiles, 666,112 triangles, 41.0 MB, 2.6 s; the table above is the earlier one-tip
shape. The reshaped coast gave an avenue two vertices 6 and 8 cm apart (5 mm off the line),
and the 9 m curb offsets swung round them, folding over each other and leaving one directed
edge in two triangles (`street_meshes`: winding 1). `roads.make` now makes a road whose mesh
fails that check again from its line without such micro-kinks (`Path.tidied`: a vertex under
0.5 m past the last kept one and within 2 cm of the line to the next one is dropped); a road
that passes keeps its bytes, so the goldens are as they were. Test
`test_road_with_a_micro_kink_is_made_again_from_a_tidied_line`.

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
[--builds DIR]`. Tests: `tests/assetgen/test_ag_streets.py` (10, and the micro-kink one above).

**Unreal.** No exporter code changed (AG1 owns it). `unreal_export.md` gains the street
contribution's format and what the exporter still needs: read it as a second layer-2 file and
drop every actor a `replaces` names; the masters road, opaque, metal, emissive, translucent
(two-sided, blended) and foliage; complex collision; non-Nanite meshes with LOD chains;
hierarchical instances for parts; walkway z from `graphs.walkways`; the new keys in the
re-import digests. Not run in Unreal. **Exporter** (after M15, with AG1's): all of it, the
street pieces as actors at their pivots in place of the joined blockout objects (complex
collision), the sky tube glass as LOD chains, container stacks as instanced actors; AG7's
sRGB slot colors made linear by the exporter. On the reshaped Greyhook one road piece fails
`street_meshes` (`rs.w1338n148`, one doubled directed edge). Results:
`docs/progress/AG1/unreal/`.

**Wiring.** `assetgen build` (AG1) is not on main yet: whichever of AG1 and AG7 merges second
makes it call `assetgen.streets.build.build(model, model_sha, BUILD/assets, spec, workers)`.

**Open.** Open spaces, green areas, ground and water stay the blockout's; markings and grates
are geometry a few millimeters over the asphalt until AG6's decals; river and sea banks have
no walls; the ramps of a named footbridge with no road are not in the model; M6's
`prop.barrier` blocks in highway medians stand on the road pieces' continuous barrier (AG8
should drop them where a road piece has one); the blockout's sea plane runs under the ground
over every tile and shows through the open approaches of road tunnels (a stage 1 fix; the
previews hide it with `--hide city.sea.`).

## AG8: props, plants and signs

**Built.** Package `assetgen/props/` (CLI `assetgen props BUILD [--spec S] [--workers N]
[--force] [--sheets DIR]`; `assetgen build` runs it after the streets, `--no-props` skips it):
- **Styles** (`styles.py`): five district styles from citygen's era per archetype, as AG7's
  paving follows it: sleek (corporate glass, clean tech, aerospace), civic (mixed, suburban
  and transit modern), heavy (brutalist, industrial), neon (neon retro) and old (heritage).
  Every draw is a blake2b hash of a key (`u`, `pick`, `choice`, `rng`), as citygen's
  `props._u`.
- **Prop variants** (`variants.py`): a generator per M6 kind, 4 to 12 variants per style
  (123 per style, 615 in all): street lights (masts, arms, heads, neon trims), wall lights,
  traffic signals, trash cans, bus shelters, hydrants, bollards, benches, kiosks, vending
  machines, food stalls with stools, planters, parked vehicles (12 per style from wedges,
  sedans, pods, hatchbacks, SUVs, taxis, vans, pickups, box trucks, kei cars and tuk-tuks),
  boats, barriers, railings, awnings, AC units, dumpsters, litter (bags, boxes and cans) and
  wall brackets, each style with its own forms, materials and colors. Meshes on integer
  millimeters with AG7's `Mesh` and props' own `shapes.py` (lathes, tubes by parallel transport,
  extrusions, catenaries); `shapes.check` as AG7's but without the shared directed edge rule
  (parts of one variant touch), and `dedupe` drops a triangle repeating another's corners.
- **Plants** (`trees.py`): 15 species, 6 or 8 variants each (108). Broadleaf trees (plane,
  maple, ginkgo, birch, linden, elm, oak, ficus) by space colonization (Runions, Lane and
  Prusinkiewicz 2007) in a species envelope: attraction points in the crown, nodes grown
  toward the mean direction of the points they are nearest (numpy elementwise distances and
  argmin), branch radii by the pipe model ($r^2 = \sum_i r_i^2$), chains swept as
  tubes, lobed leaf clumps at the twig ends in two tones. Pines by whorls with needle sprays,
  fan palms with pleated fans, date palms with leaflets, boxwood, scrub and sedum (ground
  cover), ivy in 1.5 m patches. A plant takes M6's species (else its type's), its variant
  from a hash of its id, scaled to M6's crown and height.
- **Exact props** (per tile): overhead cables (one to three catenary strands, lanterns in
  neon and old districts), scaffolding (tubes, boards and a net on the wall side) and market
  gates with their words, made in their tile's pack.
- **Signs** (`signs.py`, `glyphs.py`): an asset per M11 sign slot. Shop signs by the
  district style's looks: facade lightboxes (lit face, dark letters), panels (dark face, lit
  letters), neon (tubes along the strokes on a backboard with an outline) and channel letters
  on a raceway, on standoffs where the brief finds the wall farther; blade signs as
  lightboxes or neon skeleton frames. Billboards on facades and roofs
  (two-sided on roofs, a brand, a line and a logo), holo-ads over tower roofs (a translucent
  emissive screen, non-Nanite with a LOD chain at screen sizes 1.0, 0.3 and 0.08) and neon
  bands. Text: the POI's name where the slot's unit has one, else a shop name from the unit's
  use and citygen's name words; corporations' names on billboards. Fonts wait for decision
  13.3, so text is an in-repo stroke font: Latin and Cyrillic on a 4 by 6 grid, and generated
  glyphs for hanzi (boxes split into radicals of 2 to 4 strokes), kana, hangul (jamo blocks)
  and devanagari (under a head bar), the script drawn from the district era's weights. Neon text is four-sided tubes along
  the strokes, lightbox text flat strokes over an emissive face. Identical signs share one
  mesh (Vesper Bay: 15,448 slots, 15,439 meshes).
- **Placement** (`gather.py`): every prop's variant from its kind, its district's style and a
  hash of its id; AC units and wall lights on a bracket where the brief's mount (`gap_m`)
  is off the wall; awnings in 2 m segments turned to their wall; the M6 highway median
  barriers on an AG7 road piece with a median barrier are dropped (a `drop` entry per
  prototype); instances grouped as M15 groups its prototypes (`prop.<kind>.<tile>`,
  `plant.<type>.<tile>`), so each group replaces exactly one blockout actor. On M13's
  terrain a model z is measured from the ground where it stands, so a placement that hangs
  on a building or stands on its roof is lifted by the building's `base_m` (where AG1's
  shell stands) and anything else by the finished ground at its point, as the blockout
  lifts M15's instances (Cragmouth; a test on a synthetic terrain).
- **Outputs**: `assets/props/variants/<kind>.glb` (a family pack per kind, every style),
  `props/plants/<species>.glb`, `props/tiles/<tile>.glb` (exact props), `props/signs/<tile>.glb`
  (a node per distinct sign), `props/manifest.json`, `unreal_contribution.props.json` and
  `unreal_contribution.signs.json` (`docs/unreal_export.md`, AG8 section), `props_report.json`
  and `.txt`. A tile pack is made again only when the hash of its inputs or of the props code
  changes, a file is written only when its bytes do (an unchanged rebuild writes none), and
  the bytes do not depend on the worker count.
- **Checks** (`checks.py`): `props_coverage` (every prop, plant and sign slot has an asset
  or a drop), `props_families` (every kind and species used has its family), `props_replaces`
  (every M15 prototype actor replaced, computed with citygen's own `blockout.PROTOTYPES`),
  `props_meshes`, `props_budgets` (a variant 3,000 triangles, a plant 16,000, a sign 6,000;
  10 M unique triangles per city; 15,000 instances per tile, 300,000 per city).
- **Previews**: `assetgen props BUILD --sheets DIR` (variant sheets per style and one of the
  plants, `props_sheet.py`); `assetgen/blender/props_preview.py` (the blockout with AG1's
  shells, AG7's streets and the props as geometry nodes instances of the family packs, signs
  in place; `--night` adds lights at the lamps and glow at the signs).

**Samples** (main's specs, Greyhook reshaped, 3 workers on a Mac shared with other
sessions' builds, so the times vary; the props stage alone, after AG7's streets):

| City | Variants | Instances | Signs | Exact props | Unique triangles | Drawn triangles | Disk | Time |
|---|---|---|---|---|---|---|---|---|
| Vesper Bay | 723 | 90,048 | 15,448 | 1,902 | 7.37 M | 79.0 M | 400 MB | 18 s |
| Saltreach Free Port | 685 | 52,999 | 7,632 | 919 | 3.53 M | 41.6 M | 189 MB | 16 s |
| Delta Megacity | 715 | 92,928 | 14,983 | 1,620 | 5.98 M | 81.4 M | 342 MB | 30 s |
| Nexus City | 723 | 99,579 | 17,456 | 1,852 | 7.55 M | 97.7 M | 422 MB | 55 s |
| Greyhook | 715 | 48,162 | 8,183 | 471 | 3.68 M | 56.2 M | 209 MB | 23 s |
| Vesper Bay Pinned | 723 | 90,187 | 16,209 | 2,356 | 8.01 M | 98.5 M | 433 MB | 107 s |
| Vesper Bay Stacks | 723 | 90,742 | 16,219 | 2,337 | 8.02 M | 96.9 M | 432 MB | 48 s |
| Cragmouth | 693 | 105,364 | 19,694 | 2,462 | 8.88 M | 119.7 M | 489 MB | 37 s |
| Vesper Bay Decks | 723 | 98,688 | 17,249 | 1,948 | 7.96 M | 82.0 M | 434 MB | 96 s |

Every props check passes in every city, and every citygen build passes its checks. Signs
are most of the unique triangles (Vesper Bay 5.9 M of 7.4 M) and of the disk (they are
unique per slot); awnings, ivy, AC units and boxwood are most of the instances (Vesper Bay
29,330, 16,399, 7,468 and 4,682). Cragmouth, the largest, uses 8.9 M of the 10 M unique
triangle budget and 2,758 instances in its fullest tile. A city makes only the families it
uses (Saltreach Free Port has no food stalls or ficus, Delta Megacity no ficus, Greyhook no
ginkgo, Cragmouth no food stalls). A rebuild with nothing changed writes no file. Nexus
City's first build found two repeated triangles in one tile's meshes (`props_meshes`; that
build was gone before they were named); `pack` now drops any triangle that repeats another
in its slot, and the check names the nodes.

**Unreal exporter** (`citygen/unreal.py`, `citygen/ue/import_city.py`, surgical): M15's
prototype instancer keys are blockout keys for stage 2, so the props entries keyed by them
replace them (and `drop` entries remove them); instance transforms take a scale
(`[x, y, z, yaw, sx, sy, sz]`) and per-instance ids; a mesh record may carry
`shape_preservation` (`Voxelize` for plants, set in `finish2`, part of the mesh hash); a
`holo` master (translucent, emissive 3.0). Tests in `tests/test_unreal.py` without Unreal
(`test_stage2_props_replace_prototypes`, and `test_stage2_from_assetgen` counting the
replaced prototypes); not run in Unreal. What a check there should look at: the HISM counts
per kind against the report, plant Nanite with `Voxelize` (AG0's finding), holo-ad LODs and
translucency, the emissive neon at night, AC units and wall lights on their walls.

**Unreal check** (after the merge, a session of its own): Greyhook and Vesper Bay imported
with their props (25,837 and 46,354 actors, 785 and 1,818 s; again, nothing changed) and
checked. The HISM counts per kind and species equal the report, no M15 prototype is left, every instance stands at its model
position, plants are Nanite with `Voxelize` and read full from 600 m, holo-ads are
translucent three-LOD chains, neon and lit faces emissive (a night shot). Two fixes: plants'
instanced actors had collision (now `NoCollision`), and the check's traces down are tried
again while a freshly streamed cell's collision comes in. Results:
`docs/progress/AG8/unreal/`.

**On AG6** (after AG6 merged; one sign path, textures from the library):
- **One sign path.** AG6's signage (`signs.json`, `materials/signage.py`, `ad_slots` shared)
  decides every slot's text, script, brand, colors and page cell; AG8 builds the body. A
  flat face (lightbox, LED panel, blade box, billboard, holo-ad screen) is one quad showing
  its page cell on UV0 (upright: the cell's top on the face's top), material
  `page.<page>` (master `sign`, `SignTex` the page) or `holopage.<page>` (master `holo`);
  neon tubes and channel letters run along AG6's glyph strokes
  (`assetgen.materials.glyphs`), so AG8's own `glyphs.py` is gone and both stages write the
  same words. The look comes from the district style (neon, LED panels, channel letters on
  sleek facades, else lightboxes). AG6's preview drops its sign quads where AG8's signs
  stand, so nothing is drawn twice. Kept over the alternative (pages dropped) because a page
  cell carries the text at two triangles a face: Vesper Bay's signs fell from 5.9 M to
  1.2 M unique triangles and the props stage from 400 to 136 MB on disk. `assetgen props`
  on a build without the library (`assets/library`) still draws flat strokes on lit faces.
- **Textures.** Every prop, plant and sign slot maps to an AG6 master and library set
  (`catalog.PROP`, `PROP_PREFIX`, `prop_set`; a test holds it): painted and galvanized metal,
  rusty metal, concrete, plywood, tarp for awnings and stall roofs, pod shells for hulls,
  car paint, plastic, glass; emissive slots (neon, lit faces, lamps) have none. New library
  sets (`LIB_VERSION` ag6.2, 125 sets): `plastic`, `car_paint`, `metal_galvanized`,
  `metal_rusty`, three barks (`surfaces.bark`: furrowed plates, smooth with lenticels and
  peel for birch, ringed for palms) and five leaf clump sets (`surfaces.leaves`: broad,
  lobed, fan, needle, small; leaves on twigs from the middle, the tint mask the leaf cover).
  Every variant has UV0 in meters: lathes by arc length round the profile, tubes along
  their length, fans and roofs planar, curved awnings and shelter roofs along the arc
  (`shapes.arcs`).
- **Leaves** (the Unreal check's finding that clumps read as big flat polygons up close):
  each clump is two crossed cards (`trees._clump`, the second tipped 60 degrees), each
  showing a whole leaf tile; master `leaves` uses the set's tint mask as an opacity mask
  (masked, two-sided). Pines use cards for their needle sprays, shrubs, ivy and boxwood
  their own clumps; palms, sedum and scrub stay solid (`foliage.*` slots, grass). Plants
  stay Nanite with `Voxelize` at distance.
- **Texel density.** AG6's check reads AG8's packs too (variants and plants in their own
  frames, exact props, signs; all within reach of the street): props and signs meet 512 px/m
  on all their textured area (a leaf card counts the tile's pixels over its side).
- **Build order** (`assetgen build`): buildings, streets, AG6's signage, AG8's props (with
  the library), then AG6's materials over every part.
- **Previews.** `assetgen materials preview` draws AG8's props and plants (geometry nodes
  instances of the family packs), exact props and signs with their textures and the
  pages; `props_sheet.py --materials` textures the variant sheets.
- **Exporter** (`STAGE2_VERSION` 5): master `M_CgLeaves` (masked, two-sided, the ORM alpha
  as the opacity mask), `M_CgHolo` reads `SignTex`; page materials as AG6's sign materials.
  Test `test_stage2_textured_props_and_signs` (no Unreal).
- **Samples** (3 workers, the props stage with its textures): Vesper Bay 723 variants,
  90,048 instances, 15,448 signs (8,056 meshes; 10,794 faced with page cells, the rest
  neon or channel letters), 2.48 M unique triangles (signs 1.20 M), 49.4 M drawn, 136 MB;
  Greyhook 715 variants, 48,162 instances, 8,183 signs (4,358 meshes), 1.34 M unique
  triangles (signs 0.61 M), 40.4 M drawn, 77 MB. Every check passes in both, texel density
  included. Renders by day and night of Neon Strand and a tree-lined avenue:
  `docs/progress/AG8/textures/`.
- **Goldens** moved on purpose: `golden_props.json` (the packs), `ag6.testport_materials`
  (the props' and signs' materials, the new sets), and `golden_streets.json`'s `all` and
  `ag1.testport_files` (every contribution carries the library's version and hash); every
  street and building pack and the library's pixels are unchanged.

**Seen from below** (a fix after AG3's street close-ups: some awnings showed only their
frames). The canvas was there and opaque, but drawn as a single sheet facing up, and the
stage 2 masters are one-sided (two-sided only for foliage, leaf cards and translucent
ones), so from the street it was a back face; AG8's Blender preview, keeping the glTF
importer's one-sided materials, culled it the same way. Fixed in the meshes:
- `shapes.blk` boxes are closed (a bottom by default: flat and glass awnings, sign boxes,
  lamp heads, kiosk roofs; 3% more triangles in the variants);
- `shapes.sheet` draws a sheet and its underside 4 mm under it (moved straight down unless
  upright, so a corrugation stays closed): corrugated and tiled awnings, the sloped bus
  shelter roof, the kiosk pavilion and container stall roofs, dumpster lids, signal visors,
  scaffolding boards and the market gate's roof;
- the curved bus shelter roof had both layers facing the wrong way (its arc runs the
  other way from the barrel awning's), the cart umbrella's underside faced up, and two lamp
  shades (davit street lights, a wall light) were drawn inside out (profiles top-down).
Tests: every awning variant has a canvas over its whole footprint, seen from below and
above, in an opaque material; rays straight up under every variant meet a front face first
(boats and litter left out). Vesper Bay: 2.57 M unique props triangles (2.48 M before),
every check passing; a close-up in `docs/progress/AG8/textures/`. No exporter change.

**Open.** Plants and signs have no collision (trunk capsules later). Lawns, hedges and green
roofs stay the blockout's green areas. Sign faces are opaque emissive, so only holo-ads are
translucent. Leaf textures are one per clump set, tinted per species; real leaf atlases per
species (and wind) later. The sign packs are the largest files; quantized positions
(`KHR_mesh_quantization`) would halve them. The Unreal check of the textured props: leaves
masked and two-sided, Nanite `Voxelize` still full at distance, sign faces showing their
page cells, holo-ads textured. Mac = x86 waits for the deferred determinism check.

## AG10: layered districts

**Built.** Stage 2's side of citygen's M14: the decks, the buildings on and under them, and
the deck's streets (scope 14.11; AG9's dependency waived, AG9 waits):
- **Deck pieces** (`assetgen/streets/decks.py`, in AG7's street stage, one piece per M14
  id in place of its blockout object, `citygen/blockout.py` `_decks` now among the keys
  `ctx._blockout_keys` reads):
  - **Slab** (`<deck>.slab.<tile>`, the blockout object's own key): the deck's polygon in
    the tile (holes under 2 m2 filled), paved top and soffit; a coffered soffit in the
    planned eras, a ribbed one elsewhere (0.3 by 0.45 m ribs every 3 m on the deck's long
    axis), stopping at the fascia and round the undercity buildings.
  - **Edges**: on the slab's real edges (never a tile's), a fascia with a 0.15 m upstand
    and a 0.45 m drip edge, grime streaks down it and a stained band on the soffit inside
    it. A rail on the upstand: posts every 1.6 m with top, mid and bottom rails, glass
    panels in the wealthy eras. No rail where a building on the deck stands at the edge,
    a ramp or its junction meets it, or a stair or elevator lands.
  - **Soffit lights**: two rows every 8 m over every ground street under the slab, and one
    over each ground junction.
  - **Colonnade**: where the edge passes over a park or plaza, a 0.8 by 0.9 m edge beam
    and slim columns every 7.5 m, off the park's paths, M14's columns, props, plants and
    buildings.
  - **Collar**: a steel collar round a building the slab is cut round (a ground building
    within 0.5 m of it reaching over its soffit; the slab cut back 0.1 m from it).
  - **Columns**: a square pier cap, a round shaft, a flared capital and a drop panel (the
    shaft alone inside an undercity building), a grime band at the foot.
  - **Stairs**: two flights of steps on a sloped soffit with stringers and handrails, the
    half landing on two posts, a top landing across to the slab's edge.
  - **Elevators**: a glazed shaft on a steel frame with bands (a concrete core in the plain
    eras), a cab door at the ground and at the deck facing the street, the shaft's head
    over the deck, a bridge across to the slab's edge.
- **The deck's streets** (`roads.deck_kind`: `slab`, `ramp`): they lie on the slab. Before,
  they were drawn as viaducts, with a box girder 5 cm under the soffit, barriers and
  underside lights. A ramp (`deck_ramp`) is a solid ramp: barriers at the carriageway, a
  2 m walkway at curb height on each side (M14's walkways beside it, their lines put on it
  in `graphs.walkways`), parapets, walls down to the ground and across its raised ends. A
  deck's junction gets a slab of its own only where it reaches past the deck (at a ramp's
  top).
- **Ground** (M13): the slab is measured from the ground the deck stands on, flat where it
  is level (within 5 cm on a 4 m grid). Elsewhere it is in 8 m cells over the finished
  ground, or over the base of a building on or under the deck where one stands, so it
  meets them (`decks.Ref`). Columns, stairs and elevators run from the ground at their
  point to the slab there.
- **Buildings** (`assetgen/buildings/decks.py`): the brief's `deck` record (AG10, only on a
  building on, under, beside or in a slab): the deck, the role (`on`, `under`, `near`
  within 2 m and over its soffit, `through` for one it is cut round), top and soffit over
  the building's pivot, and the slab's plan within 3 m of its box. With it:
  - **Undercity** (`under`): a roof within 1.2 m of the soffit is closed up to it by a
    louvered plenum band (its top meets the soffit); a parapet otherwise stops 0.3 m under
    it; no roof form. The roof's equipment, the types' roof features, masts, kitchen ducts
    and shanty barrels keep under it (`roofs.Clear` takes the soffit as a ceiling). A
    covered street's grime from the ground up and fronts and windows lit (`genome`: wear,
    dirt height, lit ratio).
  - **On a deck**: nothing under the deck's top (the band and doors on the slab already,
    AG3).
- **Checks**, on a city with decks only:
  - `street_decks`: every slab object, column, stair and elevator replaced by a piece with
    a mesh; the lowest thing over a ground street clears M14's 5.5 m; every stair and
    elevator runs from the ground to the deck's top and lands on the slab's edge.
  - `asset_decks`: no vertex of a building's shell, front or parts' boxes where its role
    forbids, within the slab's plan (on: under the top; under: over the soffit; near or
    through: inside the slab). Doors of buildings on a deck on its walkways; no roof item
    or green roof under a slab.
  - `street_coverage` counts the decks.
- **Previews**: `assetgen materials preview --views deck`, the section across the biggest
  deck from the blockout's deck camera: level, 35 mm, a 2.4 to 1 frame shifted up so the
  ground at the cut sits 3 m over its bottom, the near clip on the cut
  (`ag6_preview.section`), the eye lifted by the ground there on a terrain city; custom
  views for the street under the slab (by day and night), the undercity, a light well and
  the deck's own street.

**Samples** (3 workers on the shared Mac, an Unreal import running beside):

| City | Decks | Slab pieces | Columns | Stairs, elevators | Deck triangles | Lights, ribs, colonnade columns | On, under, cut round | Plenums | Doors on the deck | Build |
|---|---|---|---|---|---|---|---|---|---|---|
| Vesper Bay Decks | 1 (Highcrest, 21.9 ha, level) | 8 | 570 | 2, 2 | 95,576 | 1,144, 1,807, 133 | 158, 164, 0 | 86 | 579 of 579 | 3m04s (every tile), 7 s streets |
| Cragmouth with decks (test) | 2 (Ridgeback 12.2 ha on its slope, Hollow 5.0 ha, level) | 14 | 495 | 4, 4 | 128,571 | 545, 194, 19 | 38, 40, 9 | 30 | 255 of 255 | 3m30s (every tile), 9 s streets |

Every check passes in both, `asset_decks` and `street_decks` included; the lowest thing
over a ground street (a light under the ribs) is 7.2 m up. A building whose brief has no
deck record makes the same bytes, so only the deck tiles' packs change (8 of 136 in
Vesper Bay Decks).

**Found on the way**:
- The slab's lights at first followed only the junctions: a polygon-only intersection
  (`geom.inter`) dropped the street lines (now `geom.line_inter`, a test counts them).
- Undercity shanty stacks put water barrels and kitchen ducts through the soffit (their
  own placements, not through `roofs.Clear`).
- On Cragmouth with decks, two shop doors that AG3 moves off a party wall onto a wall at
  the map's edge failed `asset_access` as walled off. Their way to the alley runs along
  their own wall and round its corner. The check now lets a path graze its own building
  (2 cm, `GRAZE_M`); it fails one that crosses it.
- Ridgeback's finished ground falls from 44 to 25 m under its slab. M14 levels a deck's
  district, but the streets' grade lines down the ridge stay on the slope, and the deck's
  streets follow them. Hence the draped slab (no ribs there).

**Exporter**: no code change. Slabs keep their blockout keys, so the manifest's `decks`
still name them. Every deck piece replaces its blockout object and takes its level from
it: the slab, the deck's streets and ramps on level 1 (`cg.level=1`); the columns, stairs
and elevators on the ground. Recorded in `unreal_export.md` ("From AG10"); test
`test_stage2_takes_assetgen_decks`. Not run in Unreal (the coordinating session's call).

**Tests**: `tests/assetgen/test_ag_decks.py` (6, on the small test city with a deck over
Core, `agtools.deck_build`): the pieces and what they replace, every street check, the
slab's parts and the deck's streets on it, spans and ground, the buildings on their side of
the slab, a city without decks untouched. Goldens: `ag1` (`testport_manifest`,
`testport_files`) and `ag6` (`testport_materials`) written again on this Mac, on purpose: one
door in the small test city (`d04.lot.e877n1165.bld`) keeps its model walkway now that its
path may graze its own wall (`GRAZE_M`), so the manifest and
`unreal_contribution.buildings.json` name another walkway; every pack is byte for byte as
before (the small city's 445 files built on main and on AG10: only that door, the reports'
timings and the street stage's code hash differ). The street, props, briefs and sample
goldens are unchanged.

**Asks of citygen**: level all the ground under a deck's slab, the streets' grade lines
included (Ridgeback); a column grid that keeps out of undercity buildings or says it stands
in one; the colonnade's columns in the model (AG10 places its own off the paths); the blockout's
`deck` camera over the ground at the cut on a terrain city (its eye is 12 m over sea level,
inside Ridgeback's hill; AG10's section adds the ground itself).

**Open.**
- One deck level per district (as M14).
- No ribs on a deck whose ground is not level.
- The elevator's head over the deck is the model's 3 m: a cab's overrun, not a machine
  room storey.
- Undercity buildings one floor high stay 4.3 m clear of the soffit (a clean roof, no
  plenum).
- The Unreal check of the deck city (`docs/progress/AG10/unreal/`, after the merge): the
  slabs keep their keys and `cg.level=1`, the columns, stairs and elevators stand on the
  ground, the deck's streets and ramps at level 1, the data assets' `Levels` as
  `graphs.json`; every deck grid point lands on the deck, its walkways, ramps and stairs
  walkable. Fixed there: the deck's slab, stairs and elevators keep every triangle in their
  Nanite fallback (`streets.build.FULL_FALLBACK`, `fallback_full`): complex collision is
  built from it and had lost the rail (a capsule stopped at 33 of 143 edge points, 78
  after), and the Mac editor, which renders without Nanite, drew no soffit lights. Open from
  it: Vesper Bay Decks overruns Nanite's root pages in play on the Mac (50,008 meshes), and
  the undercity's one-storey rows leave empty shell nodes in the packs.
- Mac = x86 waits for the deferred determinism check.

## Fixes after AG10: every check on the nine samples

Full `assetgen build` runs of the nine sample cities on main after M17, M21 and M16 (Saltreach
Free Port, Vesper Bay Pinned and Vesper Bay Stacks had last been built whole at AG2 or AG8,
before most of the checks) failed checks in seven of them. The failures #66's builds found in
those three had gone with M21 (its skybridges keep their corridors clear; the failing door's
building is no longer there), and others had come. Each was fixed in the generator
(`GEN_VERSION` agfix.1) but one, which is the city's and is counted apart:

- **Moved doors in place of ground windows** (`fronts.Band.rehome`): a door that has to
  move off its wall (a party wall, a facade too short) was meant to replace the ground
  windows of the nearest facade with room, but its filter named window openings `window`
  where they are `win`, so a door only fitted between windows. A villa with its entrance on
  a 0.78 m tip of its outline got no door (Pinned, `asset_access`), and a perimeter block's
  shop door went 13 m along its wall, walled off from its walkway (Delta, M21's open item).
  Doors facing a neighbor: Pinned 436 to 323, Saltreach Free Port 379 to 300.
- **No door facing its own wall** (`fronts._faces_own`): a door or shopfront whose way
  straight out meets the building's own walls within 3 m (a crack in a perimeter block's
  outline, 0.5 m wide at its mouth; Nexus City) moves, as one against a neighbor does.
- **Balconies over a turned block or a sky garden** (`shell._hangs`): M21's test of a
  first-floor balcony hanging in the air took the slab's middle only. A stacked block turned
  over the one under it, or a tower over a sky garden's open floor, left a corner 1.8 to
  2.4 m from any mass (Pinned, `asset_envelope`, three towers). It takes every corner now.
- **Mounts on their mass** (`fronts._on_mass`): the plate behind a cable end the model puts
  8 cm under an exo frame's belt, which stands 2.9 m off the tower under it, hung under the
  belt (Stacks, `asset_envelope`). Plates, ties and trellises stay within their mass's
  height.
- **A mast's foot on its roof** (`shell._mast`): a concave arc in a tower's outline pulled
  the middle of its vertices to its edge, and the mast's foot 1.1 m off the roof (Decks).
  Where the foot does not fit there, the mast stands at the middle of the area.
- **Skybridges over a lower roof** (`shell._finish_parts`, `roofs._off_bridges`): on
  Cragmouth three bridges are level with a lower roof of their building (a stacked tower's
  lower block, a pod) and cross 1.2 to 3.4 m of it before the wall they land on. Flush parts
  (mullion caps) at that facade's top and the roof's finish were in their corridors
  (`asset_clearance`). Flush parts now take the corridor's own test (its collars and the
  inside of masses spared), and a flat roof's finish is cut round the corridors over it.
- **Landing doors on simply drawn masses** (`shell._simple_landings`): M21's round,
  twisted, tapered and leaning shafts are drawn simply until AG15, with no facade grammar to
  cut a landing door, so a bridge landing on a round tower had none (Cragmouth,
  `asset_landings`). The facets where it lands take a storefront door from the floor to the
  glass ribbon's head; every facet of the ring is split at its heights, so the mesh stays
  closed.
- **The ground under the base along the walls** (`build.building_asset`, the shell's
  `walls`): a 3.5 m spike in a footprint, which the shell tidies away, still brought the
  ground at its tip (1.25 m under the base) into `grade_low_m`, so `asset_slopes` wanted a
  step where no wall stands (Cragmouth). The ground is taken along the stretches of the
  edges that walls stand on.
- **Quay UVs** (`streets/water._along`): a quay's u was the distance along its line. Round
  the traced island's basins in Pinned, its 15 m paving's mitred outer edge at a sharp
  corner, or at a jog of a few centimeters, ran meters with almost no u, and the streets
  met the texel density on 99.499 % of their area (99.5 % needed). u now runs along each
  edge line's own length (99.79 %).
- **Junction corners** (`streets/walks._onto`): a sidewalk corner cut from the earlier
  ones on the overlay's 1 cm grid kept a vertex 4.4 mm inside an earlier corner's edge, a
  sliver of both (Nexus City's `jn.e383n933`, `street_meshes`). A vertex within 7.5 mm of an
  earlier corner's edge goes.
- **The materials report** was written only when a file of its stage changed; its texel
  check reads the other stages' packs, so a fixed shell or street piece left it saying FAIL.
  It is written when its checks change too.
- **Sky stations out of reach** (`connections._beside`, `asset_roofs`): M5 portals a station
  through its building by the union of the building's masses, so a tube can pass over a
  megabuilding's podium far from its tower: the Crown Loop's station at The Stacks in Vesper
  Bay, Pinned and Stacks, 14.4 m from the tower at the tube's height with the podium roof
  64 m under it (M21's open item in Vesper Bay). With no wall within 6 m at its floor and no
  roof within 3 m under it, nothing of the building can carry a platform: counted apart
  (`stations_out_of_reach`), the city's to change. A station the building could serve still
  fails.

**Samples** (each found by a full build with the fixes before it; then every city built
again on the final code, every check of every stage passing):

| City | Found |
|---|---|
| Saltreach Free Port | nothing |
| Vesper Bay Pinned | balconies (3 towers), the villa's door, the station, the quays' texel density |
| Vesper Bay Stacks | the mount under a belt |
| Vesper Bay | the station (counted apart) |
| Delta Megacity | nothing (the perimeter block's door, fixed with `rehome`) |
| Nexus City | the door in a crack, the junction's corners |
| Greyhook | nothing |
| Cragmouth | three bridges over a lower roof, the round tower's landing, the spike |
| Vesper Bay Decks | the mast |

On the final code (4 workers on the shared Mac, 1.5 to 3 min a city; landing doors of the
skybridge ends, the rest counted apart as at the ground, off a floor line or in a portal):

| City | Buildings | Doors (facing a neighbor) | Landing doors | Stations out of reach | Streets at texel density |
|---|---|---|---|---|---|
| Saltreach Free Port | 3,186 | 11,788 (300) | 287 of 290 | 0 | 99.84 % |
| Vesper Bay Pinned | 6,766 | 21,293 (323) | 462 of 470 | 1 | 99.79 % |
| Vesper Bay Stacks | 6,620 | 20,653 (357) | 445 of 450 | 1 | 99.78 % |
| Vesper Bay | 5,809 | 19,952 (368) | 467 of 470 | 1 | 99.84 % |
| Delta Megacity | 5,516 | 21,131 (418) | 567 of 574 | 0 | 99.76 % |
| Nexus City | 6,553 | 23,123 (415) | 450 of 454 | 0 | 99.83 % |
| Greyhook | 2,617 | 10,265 (66) | 309 of 310 | 0 | 99.86 % |
| Cragmouth | 7,058 | 24,638 (363) | 455 of 470 | 0 | 99.80 % |
| Vesper Bay Decks | 5,962 | 21,756 (328) | 507 of 510 | 0 | 99.83 % |

Previews of the fixed spots: [`docs/progress/agfix/`](progress/agfix).

**Goldens** written again on this Mac: `ag1` (the small city's manifest and files, the Vesper
Bay buildings' GLBs) and `ag6` (the small city's materials), since every pack carries
`GEN_VERSION`; the street packs' (the small city, Vesper Bay and three of its six named
tiles: their quays and junction corners); and the props golden, stale since M17, M21 and M16
moved the small city (main gives the same digest, and nothing here changes the props).

**Tests**: `tests/assetgen` and `tests/test_unreal.py` (the Unreal launches deselected): 190
passed and 2 failed, the props golden (since written again) and Nexus City's sample briefs
(`test_sample_briefs_golden[nexus_city]`, which fails on main too, below); new
`test_ag_fixes.py` (4): a moved door in place of ground windows, a corner snapped onto an
earlier one, quay UVs round a sharp corner, a station counted apart.

**Asks of citygen**:
- Portal a sky station only through a building whose tower the tube passes through, or
  within 6 m of, at its height (the Crown Loop's station at The Stacks).
- Nexus City's junction `jn.e383n933`: its polygon has a 29.7 m2 hole inside highway
  `rs.e566n892`'s carriageway (unpaved in the assets), and two of its legs make a bowtie
  corner, which puts a sidewalk corner in the carriageway.
- Footprints with a spike (Cragmouth `d03.lot.w434n813.bld`, 3.5 m out and back) or a crack
  (Nexus City `d06.lot.e1045s82.bld`, 7.5 m deep, 0.5 m at its mouth).
- Skybridges level with a lower roof of the building they land on (Cragmouth): end them at
  the roof's edge, or keep their deck clear of the roof.
- Open decks that end several meters short of the wall they land on (Cragmouth, up to 27 m;
  6.5 m from a round tower, M21's shaft inside the box the deck was laid to).
- Pinned's traced Corporate Core door `d01.pin.path.w1427s613.door.e0` faces a 1.2 m court
  between two traced buildings (counted apart as facing a neighbor).
- Nexus City built from main on this Mac is not citygen's golden model (`a6ddd8fe...` in
  `tests/data/golden_hashes.json`, `f74f4ffd...` here, twice; the same tries, layout salt 1,
  and a report the same as the committed one but for its timings), so assetgen's sample
  briefs golden for it fails.

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

## Progress output

`assetgen build`, `preview`, `materials preview|board`, `library`, `streets` and `props` say
what they are doing on stderr (`assetgen/progress.py`, the interface of stage 1's
`citygen/progress.py`, which it will import once that lands): a line per stage (load, briefs,
genomes, shells and parts, the library on first use, building checks, streets, signage,
props, materials), a bar with n of N and the time left where the count is known (tiles as the
workers return them, buildings, library sets and atlases, the packs the density check reads,
Blender's views, sheet cells and boards), the time of each stage at the end. The streets and
props stages (seconds) and the library's own loop are wrapped from their callers, since
their code is in the code hashes their manifests and contributions record (`assetgen
library` drives its bar from the library's log lines, `materials/build.generate`). On a terminal
the bar is one line redrawn in place; piped, plain lines at 0, 25, 50, 75 and 100 % or every
30 s. Worker processes never print; the Blender scripts print `CGPROGRESS start|done <name>`
per view, which `assetgen/blenderrun.py` reads as Blender runs. `--quiet` (or
`CYBERGEN_QUIET=1`) turns it off. Stdout keeps the reports; no output file changes.

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
.venv/bin/python -m assetgen library [OUT] [--density 512]              # texture library (AG6)
.venv/bin/python -m assetgen materials preview BUILD [--night]          # textured renders (AG6)
.venv/bin/python -m assetgen materials board OUT                        # material boards (AG6)
.venv/bin/python -m assetgen streets seam BASE REGEN --district NAME    # what a regeneration changed (AG7)
.venv/bin/python -m assetgen review BUILD --prev P                      # art-direction round (AG5)
.venv/bin/python -m citygen unreal BUILD PROJECT                        # the city with its assets in Unreal
.venv/bin/python -m assetgen sweep --suite m8a --out DIR                # (AG9)
.venv/bin/python -m assetgen lock BUILD --release 1.0                   # (AG9)
```
