# M21: cyberpunk massing

From the first run-through (`docs/run_through_1.md`, Aesthetics): the buildings all looked
the same, the corporate core above all, its towers prisms on podiums, and round masses were
12, 20 or 32-gons. M21 gives towers, slabs and mid-rises forms of their own, curves as true
arcs, a per district `variety`, and a rule that towers within 150 m never share a form and a
height band.

## Forms

A tower stands on its podium on a base plate (`massing.Plate`: a rectangle with sharp, cut or
rounded corners, a circle or a four-centre oval) in one of sixteen forms (`citygen/forms.py`):

| Form | Shaft |
|---|---|
| box | the plate extruded (M3's tower) |
| chamfer, rounded | the plate with cut or rounded corners |
| setback | three or four tiers stepping in |
| round, oval | a circle, on some in drums stepping in; a four-centre oval |
| taper | bands of two or three floors, each smaller than the one under it |
| twist | a band a floor (two over 48 floors), turned up to 3 degrees a floor from the one under it, 180 degrees at most |
| lean | bands moved further one way the higher they stand (up to 8 degrees, as far as the lot allows) |
| stack | three to five blocks of their own size, turned and offset, each over 35% on the one under it |
| cantilever | a slimmer shaft with one or two blocks reaching 5 to 15 m out over the podium |
| split | two shafts of two heights with a slot between them, bridged by links |
| garden | sky gardens cut through the shaft: a core and corner columns, open round, a green floor |
| gate | a void through the upper floors under a lintel |
| exo | the shaft in an exoskeleton: columns standing 2.2 m off the facade, belts every 8 to 12 floors, rising over the roof |
| pods | capsule pods on a rounded core, staggered floor by floor |

Towers on odd lots, where no rectangle fits, take box, setback, taper, terrace (tiers cut back
from one side) or wedge (the upper floors cut back one at a time). Crowns: flat, tiers, sloped
or cut (the top floors cut back along a side or a diagonal), halo (a ring over the roof on
struts), mast or spire. Slabs curve (an annular sector bulging to the street or bowed back)
or step down along the street; megabuilding towers get cut or rounded corners on some.

Complexes keep their skybridges: twin towers and clusters take box, chamfer, rounded or
setback (one form for both twins), and a complex avoids the forms of the complex towers built
before it near it.

## Variety

`District.variety` (0 to 1; presets: corporate core 0.9, midtown 0.75, transit hub 0.6,
entertainment 0.55, research 0.5, megablock 0.35, spaceport 0.3, residential 0.2, old town
0.15, industrial 0.1) sets the draw weights: box and the mild forms (chamfer, rounded,
setback, round, taper) where it is low, the bold ones (oval from 0.25, stack 0.3, cantilever,
garden and exo 0.35, twist and split 0.45, lean, gate and pods 0.5) where it is high, and how
far the twist, taper and lean go.

## The model

Every form is prism masses, so every check and every consumer (transit, props, gameplay,
terrain seating, decks, the blockout, assetgen, the Unreal exporter) reads it as it is.

- `Building.form`: `kind`, `crown`, `tower` (podium towers, towers and landmarks 40 m and
  taller), `band` (height bands from 40, 56, 78, 110, 154, 215 and 300 m), `pivot` (the
  base plate's center), `masses` (the shaft's, bottom up) and `params` (twist per floor and
  in all, taper, lean, chamfer, corner radius, slot, belts, pods, ...).
- A band of a twisted, tapered or leaning shaft (role `band`) is the base plate turned by
  `Mass.turn_deg` and scaled by `Mass.scale` about the pivot, then moved by `Mass.shift_m`:
  enough for stage 2 to loft one surface through them.
- `Mass.arcs`: the footprint's curved stretches (center and radius to the millimeter, start
  and sweep in degrees). The footprint is cut so no chord sags more than 1 cm (`arc_steps`:
  a step of 2 sqrt(2 SAG / r), plain arithmetic), 2 cm at most once its points are on the
  0.01 m grid: a 30 m radius tower is a 112-gon, not a 32-gon. Circles, ovals, rounded
  corners, curved slabs and halos all carry their arcs.

## The neighbor rule

Towers of different owners whose footprint centroids are within 150 m never share a form and
a height band. Each lot tower draws its order of forms from its own generator and, while the
lots are built, finds every form that fits (`forms_ok`) and the heights in the bands beside
its own. Then `buildout.select_forms` takes the towers tallest first (the complexes' and
landmarks' towers as built): each takes the first form no tower already placed within 151 m
has in its band, else the same in a band beside its own; the lots that change are built again
in their chunks. In a district regeneration the old towers outside the district are held.

| Corporate core (on M17's roads) | Towers | Forms before | Forms after | Same form and band pairs within 150 m, before | after |
|---|---|---|---|---|---|
| Vesper Bay | 156 | 1 (box) and the megatower | 18 and the megatower | 345 | 0 |
| Delta Megacity | 230 | 1 (box) and the megatower | 18 and the megatower | 641 | 0 |

City-wide: Vesper Bay 353 pairs to 0, Delta 934 to 0; every sample has none now.

## Checks

- `building_forms`: every arc lies on its footprint within 2.1 cm, a twisted shaft turns at
  most 3 degrees a floor, a form names its own masses, and every mass above the building's
  floor rests on or is fixed to another of its masses. It found M3's megabuilding open decks
  hanging in the air past a tower's mid setback (six in Vesper Bay Decks, three in Cragmouth):
  a deck is now placed only where both towers' walls reach it.
- `tower_neighbors`: the rule above, and every tower's form record names its band.

M3's checks see every new mass (footprints, overlaps, clear zones, heights, flight cones,
skybridge landings, roof items); M13 seats and M14 decks as before.

Three fixes the new forms called for elsewhere:

- **Skybridges** keep stage 2's corridor margins (0.2 m beside, 0.3 m over) clear of every
  mass: a block of a stacked tower and a pod 0.3 m over two bridges failed assetgen's
  `asset_clearance` on Vesper Bay. A bridge through a traced building (placed after the
  bridges, which did not see it) is taken out: the pinned and stack demos' first try.
- **A cluster tower** stood beside its podium piece where the piece was cut in two (the
  largest piece was taken): now the piece under it.
- **Sky tube portals** stay under a tower's shaft (`transit.Bld.body`): with masts more
  common, a Delta station portal went through a lean tower's mast over its roof, which
  assetgen could not cut (`asset_roofs`). Clearances still see the mast. The line then ran
  through a Midtown box tower with a station on a 7.5% grade, where assetgen laid the
  platform level from the tube's first point, into the tube (`asset_clearance`): AG4's
  `connections.station` now takes the floor under the tube's lowest point over the platform,
  as its `_beside` already did (`GEN_VERSION` m21.1).
- **A patchwork finish on a concrete podium** (AG2): a building whose body is patchwork takes
  its `finish` from the body's system, and its punched concrete podium read that finish
  without the patch genes its own group never drew (`KeyError`, the merged Vesper Bay): the
  podium keeps concrete in that case (`shell._finish`), every other building as before.
- **Balconies under a floating block** (AG2): a cantilevered or stacked block's first-floor
  balconies hung 0.2 m under it in the air (`asset_envelope`); a balcony whose slab no mass of
  the building spans within a deep part's reach is left out (`shell._hangs`), so balconies
  over a podium stand as before.
- **Odd-lot tiers** (citygen): a setback, taper, terrace or wedge tier inset or cut from an
  odd plate must have no corner under 40 degrees and no edge under 1 m (`forms.neat`; a
  35 degree tier gave AG1's facade grammar bad edges on Delta), else the tower takes another
  form.

## Builds

Every sample builds with every check passing (92 checks, 97 on the deck demo), on main's
code with M17 merged; tries before are main's with M17:

| City | Tries before | Tries after | Towers | Tower forms | Same form and band pairs within 150 m |
|---|---|---|---|---|---|
| Vesper Bay | 1 | 1 | 180 | 19 | 0 |
| Delta Megacity | 1 | 1 | 418 | 19 | 0 |
| Nexus City | 1 | 2 | 261 | 20 | 0 |
| Saltreach Free Port | 1 | 1 | 230 | 18 | 0 |
| Greyhook | 2 | 2 | 117 | 17 | 0 |
| Vesper Bay Pinned | 2 | 2 | 34 | 12 | 0 |
| Vesper Bay Stacks | 2 | 2 | 31 | 13 | 0 |
| Vesper Bay Decks | 6 | 4 | 186 | 19 | 0 |
| Cragmouth | 2 | 2 | 227 | 19 | 0 |

Nexus City's first try misses `transit_altitude` by 0.43 m: its Spire Line sky tube climbs
over a tower's new mast to 150.43 m (its range ends at 150 m); the next layout passes. Before
M17 (same M21 code otherwise) every sample took the tries it took on main.
(Towers: podium towers, towers and landmarks 40 m and taller; the traced towers of the pinned
and stack demos stand as drawn and are left out. Before M21 every tower was a box.)

(A first try of the pinned and stack demos found a skybridge through a traced building, which
the bridges did not see, and a cluster tower standing beside its podium piece; both are fixed,
see Checks.)

`assetgen build` on Vesper Bay and Delta: every check of every stage passes (buildings,
streets, props, materials). Drawn simply for now (`shell._simple_mass`, until AG15 draws the
forms whole): the bands of twisted, tapered and leaning shafts and the masses off the ground
curved all round (round towers and drums, ovals): the plate extruded, a spandrel and a ribbon
of glass a floor; 594 masses in Vesper Bay, 1,186 in Delta. Rounded corners, blocks, links, cores, pods and
frames take the full facade grammar, their curves as short facade edges.

Images: `vesper_bay/` and `delta_megacity/` (`preview_massing.png`; 8K renders
`render_iso_city.jpg` and the corporate cores `render_iso_d01.jpg`, `render_iso_d03.jpg`;
`render_street_up.jpg`, looking up a Vesper Bay Corporate Core street). WIP: `wip/`.

## District regeneration

`citygen build cities/vesper_bay/city_spec.json OUT --district "Corporate Core"` on the M21
build keeps the neighbor rule (179 towers, 19 forms, no pair; the old towers outside the
district are held). It fails one check, as on main with the same four seeds: `complexes`, the
district's twin towers not built (their two lots left empty; the held transit lines remove 139
buildings in the regenerated district). An open item from before M21.

## Open

- On the merged code `assetgen build` fails two checks that main with M17 fails the same way
  without M21 (checked on main's own builds of both cities): Vesper Bay `asset_roofs`
  (`d02.lot.e799n917.bld`: a sky station portal of the Crown Loop over a megabuilding's
  podium, 26 m from its tower at the tube's height, so there is nothing to cut and too far for
  a platform beside it; transit portals by the union of a building's masses) and Delta
  `asset_access` (`d02.lot.e1475n1713.bld` door `u0`, no walkway open to it, a perimeter
  block). Main with M17 also crashed on Vesper Bay (`KeyError: 'base.patch'`, fixed here) and
  failed Delta `asset_clearance` (a sloped sky station, fixed here).

- AG15 draws the forms whole (bands as one lofted surface, curved walls with their windows,
  diagonal braces of the exoskeletons from `form.params`); AG14 the arcs smooth.
- Megabuildings and perimeter blocks are not towers for the rule (their towers take cut or
  rounded corners on some, by variety).
- The rule measures footprint centroids; a leaning tower's top can stand up to 20 m from it.
- Mac = x86 for M21 waits for the deferred determinism check (`docs/determinism_check.md`).
