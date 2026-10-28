# AG2: facades

Every opening of every building is now filled with parts (window frames by style with
sills and lintels, mullion caps, spandrel panels, balconies, louvers, fins, sunshades,
shutters, grilles, screens, capsule pods, structural members), every facade system of the
scope is built (nineteen in all), masses are articulated (corner chamfers and rounds,
setback ledges, stepped and halo crowns, masts and spires, arcades, podium canopies), and
grime and low wealth add boards, infills, replaced frames, AC units, grilles and dishes. A
part a building repeats 8 times or more is an instance of one mesh per tile; the rest are
merged into the shell. The uniqueness check also compares contact-sheet thumbnails, and
budgets hold per building class.

| Command | What it does |
|---|---|
| `assetgen build BUILD [--spec S] [--workers N]` | as AG1, plus `BUILD/assets/parts/<tile>.glb` (the tile's instanced part meshes) and the parts in the manifest, report and `unreal_contribution.buildings.json` |
| `assetgen preview BUILD [--views ... towers] [--no-parts]` | as AG1, with the parts drawn as instances; `towers`: the tallest building of each era up close |

TABLE

Build times are `assetgen build` with 4 workers on the shared M4 Pro (buildings only; the
street stage adds 5 to 10 s). Unique triangles are the shells plus one copy of each part
mesh, against the budget (section 11's estimate for the city's bays and roofs, plus 40%
for parts); drawn triangles count every instance. Nearest thumbnails: the fewest bits of
1,504 by which two buildings outside one family differ (at least 8 asked).

## What AG2 adds

**Parts** (`assetgen/buildings/parts.py`). Each part is generated in its own frame (x along
the facade, y into the wall, z up, millimeters) from quantized parameters (whole
centimeters, 5 degree steps, discrete styles) and named by the hash of its type and
parameters, so every placement with the same parameters is one mesh:

| Family | Types |
|---|---|
| window | a frame by style (unit, fixed, casement, sash, awning, industrial, lattice, ribbon) with its sill and lintel by the genome |
| cap, spandrel | mullion and transom caps on curtain walls; spandrel panels under windows and in door rows |
| balcony, balconette | rail, solid, glass and enclosed balconies on door rows (residential and hotel uses only, as deep as the facade has room for); French rails |
| louver, fin, shade | louver panels in mechanical rows and louvered walls; vertical fins and crown fins; sunshade blades |
| shutter, grille, panel | open shutters; bars on low windows; boards, infills, screen blades, egg crates and add-on boxes |
| member, pod | exoskeleton columns and beams, diagrid diagonals cut level at their nodes; capsule pods with round windows |
| ac, dish, column, canopy, mast | window AC units, dishes, arcade columns, podium canopies, crown masts and spires |

A part placed fewer than 8 times in a building is merged into its shell by slot (unless
turning it to its facade and rounding to the millimeter would fold a thin triangle: then
it stays an instance). Every part mesh is closed, as the shells are.

**Facade systems** (`systems.py`): the six of AG1 and spandrel ribbon, fin wall, diagrid,
exoskeleton, board-marked concrete, stucco with shutters, timber infill, tiled eaves,
standing seam, louvered industrial, capsule stack, perforated (clean-tech) skin and hangar
cladding. Each era draws its own (no fallbacks any more); some keep to a size of building
(a diagrid from 10 floors, a capsule stack 4 to 40, tiled eaves 1 to 6, with a stand-in
outside). Industrial walls on the ground take a block or concrete dado and industrial roofs
a palette of their own (galvanized and coated metal, white membrane, tar).

**Massing articulation** (`articulate.py`): corners of 60 to 120 degrees between free
facades chamfered or rounded on every mass that has them; towers of 14 floors and more
stepped in at a setback ledge; stepped and halo crowns, masts and spires; arcades (the
ground floor set back behind columns, the floors above cantilevered over it); podium
canopies over the ground floor; mechanical louver bands in towers (AG1). Each era weighs
them (`systems.ARTICULATION`).

**Irregularity** by `irreg`, from the building's grime, its district's wealth and a rate
of its own: boarded and infilled windows, replaced frames, AC units, grilles, dishes,
closed-in balconies, add-on boxes and open shutters.

## Previews

**Whole cities** (`city_full`, 8K; open one for full size):

| Vesper Bay | Nexus City |
|---|---|
| <img src="vesper_bay/city_full.jpg" width="420"> | <img src="nexus_city/city_full.jpg" width="420"> |

| Delta Megacity | Saltreach Free Port |
|---|---|
| <img src="delta_megacity/city_full.jpg" width="420"> | <img src="archipelago_free_port/city_full.jpg" width="420"> |

| Greyhook | Vesper Bay Pinned |
|---|---|
| <img src="peninsula_city/city_full.jpg" width="420"> | <img src="vesper_bay_pinned/city_full.jpg" width="420"> |

| Vesper Bay Stacks | Cragmouth |
|---|---|
| <img src="vesper_bay_stacks/city_full.jpg" width="420"> | <img src="cragmouth/city_full.jpg" width="420"> |

**Towers of each era** (the tallest building of each era that is not a landmark, from
Nexus City, which has nine of the ten, and Vesper Bay's brutalist; 8K):

<img src="towers.jpg" width="840">

**Contact sheet**: 64 Vesper Bay buildings drawn at random, each framed alone (8K, 960 px
cells):

<img src="vesper_bay/contact_sheet.jpg" width="840">

**Vesper Bay's districts at full detail** (2400 px renders, 1600 px here):

| d01 Corporate Core | d02 The Stacks |
|---|---|
| <img src="vesper_bay/iso_d01.jpg" width="420"> | <img src="vesper_bay/iso_d02.jpg" width="420"> |

| d03 Highcrest | d04 Old Town |
|---|---|
| <img src="vesper_bay/iso_d03.jpg" width="420"> | <img src="vesper_bay/iso_d04.jpg" width="420"> |

| d05 Neon Strand | d06 Vess Docks |
|---|---|
| <img src="vesper_bay/iso_d05.jpg" width="420"> | <img src="vesper_bay/iso_d06.jpg" width="420"> |

| d07 Launch Key | d08 Scholar Isle |
|---|---|
| <img src="vesper_bay/iso_d07.jpg" width="420"> | <img src="vesper_bay/iso_d08.jpg" width="420"> |

**Street level** (the blockout's five street cameras, 1600 px here; street_5 at 8K in
`vesper_bay/detail/`):

| street_1, Corporate Core | street_2, The Stacks |
|---|---|
| <img src="vesper_bay/street_1.jpg" width="420"> | <img src="vesper_bay/street_2.jpg" width="420"> |

| street_3, Scholar Isle | street_4, Corporate Core under the viaduct |
|---|---|
| <img src="vesper_bay/street_3.jpg" width="420"> | <img src="vesper_bay/street_4.jpg" width="420"> |

street_5, Old Town:

<img src="vesper_bay/street_5.jpg" width="420">

## Checks

All five pass on every sample:

| Check | What AG2 adds to it |
|---|---|
| `asset_coverage` | (as AG1) |
| `asset_envelope` | every instanced part's box at each placement and every merged part by its slot's reach: flush parts (frames, sills, caps, shutters, grilles, members, columns) up to 0.16 m out at any height, strips (fins, sunshades, louvers, pods, screens, AC units, dishes) as AG1's cornices, deep parts (balconies, canopies) up to 1.81 m out at least 3 m up; masts and spires within $\max(12, 0.2 h) + 1.5$ m over the highest roof |
| `asset_meshes` | every part mesh closed, as the shells |
| `asset_unique` | also every two buildings outside one family 8 bits apart of their 1,504 bit thumbnail hash (a 64 px z-buffered drawing from the contact sheet's view, shaded by slot tint; over 16 x 16 blocks, a difference hash for its structure and each block's mean shade in four steps for its tone); a building filling under 10% of its thumbnail (a long thin shed, drawn as a line in any contact sheet) is told apart by its genes alone |
| `asset_budget` | per building class (low under 12 m, mid under 40 m, high under 100 m, tower, and mega for megabuildings, straddle buildings and landmarks): unique triangles at most $k$ times section 11's estimate for the building's bays and roof plus a base, instances at most $i$ per bay plus a base; the city's part meshes within 40% of its shell estimate and its instances within 3 per bay |

UNIQUE

## The exporter

No exporter code changes here. Each building entry of `unreal_contribution.buildings.json`
lists its instanced parts (kind, type, glb, node, asset, count, triangles, transforms and the
building's id) and its instance count; `docs/unreal_export.md` ("From AG2") has the format.
The exporter's stage 2 import (merged while AG2 was built) takes them as they are: an
instanced actor per building and part kind, keyed `<key>.<kind>`, with the building's pivot
and Custom Primitive Data, its mesh from the tile's part pack.
`tests/test_unreal.py::test_stage2_takes_assetgen_parts` checks this on the small city;
for Vesper Bay, `unreal.build_manifest` gives 14,280 instanced actors for its buildings'
parts, all 1,306,362 instances of its contribution. Unreal check: the coordinating
session's call.

## Goldens

`tests/assetgen/data/golden_hashes.json` written again on the Mac: AG2 changes every shell
(window widths, articulation, dado, merged parts) and adds the part packs, so the small
city's manifest and files and the nine Vesper Bay buildings move; the briefs, the spike and
the triangulation are unchanged.

## For later milestones

- **AG3**: storefronts and doors are still AG1's (glass per unit, door gaps); arcades and
  podium canopies leave the ground floor's frontage free for them, and the dado sits where
  loading docks go.
- **AG4**: roof equipment is still blocks; shed roof forms (sawtooth, pitched, barrel)
  would tell plain sheds apart better than their walls.
- **AG5**: shanty stacks, megabuildings and industrial sheds use the general grammar with
  their systems; the thumbnail check's slivers are long sheds; plinths on slopes still
  plain.
- **AG6**: AG2's new slots (walls, parts, the dado) and their tints are part of the material
  contract; parts take their building's CPD.
- **Mac = x86** waits for `docs/determinism_check.md`.
