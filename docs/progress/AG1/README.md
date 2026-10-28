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

SAMPLES_TABLE

Times are `assetgen build` from the city model to the last file with 4 worker processes on
the M4 Pro shared with three other sessions (load 10 to 15), briefs included (13 to 19 s of
it). A second build of the same city writes no file and takes 5 to 7 s (the briefs and
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
the glass slots, as AG0 measured. Footprints citygen leaves with a spike of no width or a
court pinched onto the exterior are cleaned before building (8 to 12 spikes per city).

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

UNIQUE_LINE

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

FOLLOWUPS
