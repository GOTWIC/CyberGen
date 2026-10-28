# AG1: building shells

Every building of every sample city now has a model of its own: a closed shell (walls with
window openings and reveals, storefronts, slab bands, parapets, cornices, roofs, roof
equipment blocks) generated from its brief by a genome and a split grammar, a far proxy, and
simple collision, written as 256 m tile packs with a manifest and assetgen's entries for the
Unreal exporter. An unchanged city rebuilds with no work and no file written; a regenerated
district rebuilds only the tiles whose buildings changed.

| Command | What it does |
|---|---|
| `assetgen build BUILD [--spec S] [--overrides O] [--workers N]` | `BUILD/assets/`: `tiles/<tile>.glb` (shells), `proxies/<tile>.glb`, `manifest.json`, `asset_report.json` and `.txt`, `unreal_contribution.buildings.json`; exit 1 if a check fails |
| `assetgen preview BUILD [--blockout DIR] [--views ...] [--only ...] [--width W]` | Blender previews in `BUILD/assets/previews/`: the city from proxies (`city`), every shell at once (`city_full`), districts and the blockout's street cameras at full detail, contact sheets per type |

| City | Buildings | Shell triangles | Section 11 estimate | Openings | Proxy triangles (median, max) | Packs on disk | Build, 4 workers |
|---|---|---|---|---|---|---|---|
| Vesper Bay | 5,793 | 21.8 M (3,758 per building) | 36.7 M (0.59) | 1.06 M | 34, 390 | 1.26 GB + 27 MB | 119 s |
| Saltreach Free Port | 3,135 | 15.4 M (4,906 per building) | 20.3 M (0.76) | 0.82 M | 34, 367 | 0.90 GB + 15 MB | 46 s |
| Delta Megacity | 5,417 | 24.0 M (4,424 per building) | 36.9 M (0.65) | 1.22 M | 40, 268 | 1.39 GB + 27 MB | 75 s |
| Nexus City | 6,519 | 21.5 M (3,303 per building) | 36.8 M (0.59) | 1.03 M | 35, 335 | 1.24 GB + 31 MB | 71 s |
| Greyhook | 2,460 | 9.8 M (3,992 per building) | 20.4 M (0.48) | 0.49 M | 23, 498 | 0.57 GB + 11 MB | 23 s |
| Vesper Bay Pinned | 6,658 | 20.6 M (3,090 per building) | 38.4 M (0.54) | 0.92 M | 34, 336 | 1.19 GB + 31 MB | 62 s |
| Vesper Bay Stacks | 6,686 | 20.1 M (3,003 per building) | 36.6 M (0.55) | 0.89 M | 34, 334 | 1.16 GB + 31 MB | 63 s |

Times are `assetgen build` from the city model to the last file with 4 worker processes on
the M4 Pro, shared with other sessions' Blender and Python jobs (load 15 to 100 during these
runs; Vesper Bay takes 50 to 60 s at a load near 10), briefs included (5 to 28 s of it). So
a whole city builds in 1 to 2 minutes with 4 workers, far inside the 20 minute target. A second build of the same city writes no file and takes 5 to 7 s (the briefs and
records are read back, the checks run again). Section 11's estimate for the shells is its
$N_b\, t_b + A_r\, \rho_r$ with the city's own bays and roof area; AG1's shells use about
half of it, so AG2's parts have the other half.

## How a building is made

**Genome** (`assetgen/buildings/genome.py`). Three layers of blake2b draws on ids, all from
the brief: the district palette (the era's preset with the asset spec over it, the
district's added systems and wear, a landmark's own palette), the property family (the
buildings of a complex draw their discrete genes and colors from the property, and step
their continuous genes by one or two quantization steps), and the building. Per mass group
(`base`: podiums, docks, halls; `body`: towers, tiers, slabs, single masses; `top`: crowns,
roof tiers) a facade system and its window type, rhythm, bay width, window share, sill and
head, reveal depth, corner pier, cornice, parapet and slab bands; per building the ground
band, crown, corner, finish, base strip, colors (wall, trim, glass, roof from the era's
palette, an owner's brand colors over it, with value and warmth shifts), wear and dirt
height. Every era maps onto AG1's six systems (the others fall back to the nearest:
`systems.FALLBACK`), and some building types fix theirs (shanty stacks patchwork; warehouses,
sheds, hangars, yards corrugated; parking punched concrete with open bays).

**Facade systems.** Unitized curtain wall (full-height glass between thin mullions and
spandrel panels, split or banded lites, lobby glazing), punched concrete (concrete or
plaster, single, paired, tall, square or wide windows, slab bands), precast panel (panel
joints, single, wide, paired or ribbon windows), punched brick (narrow tall windows, A-B-A
rhythms, cornices), corrugated (clerestory and strip windows high on tall floors) and shanty
patchwork (patches of sheet, rust, tarp, panel and plywood per column and band, windows here
and there).

**Grammar** (`assetgen/buildings/shell.py`):

$$\text{mass} \to \text{edges} \to \text{floor rows} \to \text{bays} \to \lbrace \text{opening}, \text{panel}, \text{pier}, \text{mount} \rbrace$$

- Floor rows per mass from its floor grid: a sill and head per floor, the same on every
  facade of the mass; the ground row by the ground gene (storefront, lobby, raised, blank;
  storefronts wherever the building has units), louvered mechanical floors every 15 to 25
  floors in towers, a glazed lantern on a tower's top floor when its crown says so, open dark
  bays in parking structures, the top floor kept clear of the cornice.
- Bays per facade between corner piers (the corner gene, only at real corners) wide enough
  that every reveal stays inside the solid next to the other facade, laid even, A-B-A,
  grouped or irregular; a facade whose reveals would cross another edge of its mass (a court
  a few centimeters inside the exterior) gets none.
- An opening per bay by window type and by the brief's region class at its middle: none on
  party and hidden walls, few and small on blind ones; a storefront per ground-floor unit;
  a panel (a mount) wherever a sign slot, mounted prop, facade plant or skybridge end would
  fall on glass.

**Geometry.** Integer millimeters in the building's frame, every part closed:
- the mass envelope: each facade a grid welded on its plane (pier cells per row, zipper
  strips between rows, so no T-junction anywhere and the corners match), a reveal pocket per
  opening (sill, head and jambs in the wall's finish, the pane at its back), the roof and
  bottom caps on the ring's corners (the triangulator now keeps straight vertices);
- ring strips extruded (`assetgen/buildings/rings.py`): parapets on roof edges no other
  mass stands on, cornices and slab bands only above 3 m and never on party, hidden or blind
  stretches, mitered corners beveled past 1.5 offsets;
- roof equipment blocks for the brief's roof items (AG4 replaces them).

UV0 is meters along each face (world-scale tiling, continuous around a mass); UV1 (0 to 1
over a pane) and vertex colors (a window id in alpha, for interior mapping) exist only on
the glass slots, as AG0 measured. Footprints citygen leaves with a spike of no width, a ring
that crosses itself or a court pinched onto the exterior are tidied before building
(`rings.tidy`: 22 to 73 rings per city, one court filled in Nexus City).

**Proxies** (`buildings/proxy.py`): the masses as prisms with their roofs (no openings, no
bottoms), at most 500 triangles (rings thinned while they stay simple), UV0 in meters so the
preview material draws a window grid from the building's bay and floor height.
**Collision** (`buildings/collision.py`): every mass footprint cut into convex pieces,
boxes where a piece is a rectangle, else convex prisms.

## Previews

PREVIEWS

## Checks

All five pass on every sample:

| Check | What it asks |
|---|---|
| `asset_coverage` | every building of the model has a shell and a proxy; every key of the manifest is in the model |
| `asset_envelope` | every shell vertex inside a mass that spans its height, or a cornice or band at most 0.6 m out from its face (0.9 m at a mitered corner) at least 3 m up, or a parapet at most 1.2 m over its mass; roof equipment over a roof |
| `asset_meshes` | no degenerate or duplicate triangles; every part closed and consistently wound (each directed edge once, its reverse once), so no crack anywhere along a shell |
| `asset_unique` | every two buildings outside one complex family differ in at least $k = 4$ discrete genes or by a genome distance of at least 4 (a discrete gene counts 1, a continuous one $\min(\lvert\Delta\rvert / s, 1)$ with $s$ a clearly visible step), on the genes each shell used |
| `asset_budget` | the city's shell triangles within section 11's estimate for its bays and roofs |

Uniqueness compares 27 to 28 discrete and 32 to 39 continuous genes over 3 to 22 million
pairs per city; the nearest pair outside a family is 4.7 to 6.1 apart (median nearest 10.0
to 10.6). Mount panels: 11 to 34 thousand openings per city became a panel because a sign,
prop, plant or skybridge end would have hung on glass. Ring strips: 5 to 15 thousand per
city, 11 to 28% refused where a run would fold (they are left out, never drawn wrong).

## Rebuilds

- **Unchanged city**: the briefs are kept when the model, spec and overrides are the ones
  they were made from; every tile whose buildings all keep their asset hash keeps its files
  and records; no file is written.
- **Asset hash**: $h(b) = \text{sha256}(\text{brief}(b) \Vert v_{\text{gen}} \Vert h_{\text{lib}})$,
  with $v_{\text{gen}}$ the shell generator's version (`GEN_VERSION`, carried by the packs
  instead of the package version so a kept tile has the bytes a fresh build would write)
  and $h_{\text{lib}}$ the material slots and system tables.
- **Regenerated district** (the small test city's Old Quarter, M10): only the tiles holding
  a building whose brief changed are made again; every other tile's packs are kept byte for
  byte (`tests/assetgen/test_ag_build.py`).
- **Workers**: each tile is a pure function of its briefs, so the files do not depend on the
  worker count or the hash seed (tested with 1 and 2 workers and `PYTHONHASHSEED`).

## Mac = x86

X86_LINE

## The exporter

M15 (#31) was not on main when AG1 finished, so the exporter's code is unchanged. AG1 writes
the first real contribution, `BUILD/assets/unreal_contribution.buildings.json`: per building
its shell node and asset, its pivot (the building's origin), material slots with the CPD
index of their tint, box and convex collision from the masses, 23 Custom Primitive Data
floats, Nanite on with distance fields and Lumen cards off, its proxy, and an empty parts
list for AG2. `docs/unreal_export.md` ("From AG1") has the format and the list of what the
exporter needs to take it.

## For later milestones

- **AG2**: the shells leave about 40% of section 11's triangle estimate for parts; the
  reveals that should become instanced parts with sills, mullions and fins are in the
  shells today (about 20 triangles per opening, its share of the wall included). Massing
  articulation, the other facade systems (each era's fallbacks are in `systems.FALLBACK`)
  and wear by grime and wealth go there.
  The uniqueness check measures genomes only; AG2 adds the thumbnail hash.
- **AG3**: storefronts are glazed openings per unit (no doors, shutters or signs yet);
  mount panels already keep every sign slot, prop and skybridge end off the glass, so the
  mounts check should pass from the start. Blind walls get few, small windows; party walls
  none.
- **AG4**: roof equipment is a block per roof item; skybridge ends are blank panels on the
  facade; portals are not cut yet.
- **AG5**: shanty stacks, megabuildings, warehouses, parking structures and landmarks use the
  general grammar (with their type's system); the wheel is the blockout's rim and spokes.
- **AG6**: the slots (`systems.SLOTS`) and their tint channels, UV0 in meters, UV1 and window
  ids on glass, and the 23 CPD floats are the material contract; AG6's masters read them.
- **Exporter** (whichever PR has M15 on main first): the list in `docs/unreal_export.md`.
  Collision is mostly convex prisms (45 degree footprints rounded to the millimeter are
  rarely exact rectangles); boxes could take a small angle tolerance.
- **citygen** (scope 4.5): footprints with zero-width spikes, self-crossing rings and courts
  touching the exterior (`rings.tidy` cleans them; a citygen fix would make it a no-op).
