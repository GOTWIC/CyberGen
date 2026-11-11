# Game packs: the format

`vehicles/game.py` turns any car of `vehicles/cars/` into a game-ready pack. This file is the
contract other tools (the Unreal exporter, AG8's families, stage 4's fleet) read.

```
vehicles/blender.sh vehicles/game.py --car vanta_r [--out DIR] [--docs]
vehicles/blender.sh vehicles/game.py --car vanta_r --test          # 1024 / 512, a minute
```

| Argument | What |
|---|---|
| `--car NAME` | a car of `vehicles/cars/` (file name without `.py`) |
| `--out DIR` | the pack's folder (default `~/.cache/cybergen/vehicles/game/<car>/`; never in git) |
| `--body-size N`, `--wheel-size N` | atlas sizes (4096, 2048) |
| `--lods A B C D` | triangle budgets (default by the size class: 150000 60000 20000 5000, large 150000 60000 20000 8000) |
| `--samples K` | scales every bake and render sample count (1) |
| `--test` | 1024 / 512 textures, a quarter of the samples, half-size renders |
| `--docs` | also writes `docs/progress/AG18/<car>/game.jpg` and `game_report.json` |
| `--views a,b` | more views compared in `proof/` (the car's own, e.g. `nose,tail,wheel`) |
| `--keep-work` | keeps the raw bakes and LOD0's parts (`work/lod_input.blend`) in `work/` |
| `--lods-only` | the LODs again from an earlier `--keep-work` run (seconds, plus the proof's LOD views and the checks), for work on the LODs |

The car's script is not changed and gives no hints: everything is decided by rules on the
built objects (below). One run is one job under `blender.sh`'s lock; it runs a second
Blender (the proof) and the repo's venv Python (textures, checks) as children.

## Files

| File | What |
|---|---|
| `pack.json` | everything below, in the car's frame |
| `lod0.glb` ... `lod3.glb` | one glTF binary per LOD, the same node names in each |
| `collision.glb` | the convex hulls, nodes `UCX_body_00` ... |
| `body_*.png`, `wheels_*.png` | five textures a slot (below) |
| `game_report.json` | the checks and the numbers; the run fails when a check fails |
| `game.jpg` | the proof image |
| `proof/` | its renders (original, baked, recolored, LODs) |

## Frame

`pack.json` is in the designs' frame: x forward, y left, z up, meters, origin on the ground
under the middle of the car. The glTF files use glTF's own axes (+Y up, Blender's exporter
maps (x, y, z) to (x, z, -y)); importers convert back.

## Nodes (the same in every LOD file)

Each GLB has one empty root `car` at the origin with these children, one mesh and one
material each:

- `body`: everything rigid and opaque, hover pods, spares and skids included; material `pack_body`.
- `glass`: every transmissive surface; material `pack_glass`.
- `wheel_<tag>` (`fl`, `fr`, `rl`, `rr`, ...): tire, rim, hub, light ring, disc, drum. The
  node's translation is the axle's middle, its rotation identity, so it spins about its
  local y and steers about its local z; material `pack_wheels`.
- `brake_<tag>`: the caliper, on the same pivot; it steers with its wheel but does not spin.

A hover car has no wheel nodes. A wheel is found by rule: an object `tire.<tag>` whose axle
lies along y and which stands on the ground, with every object whose name ends in `.<tag>`
(`rim.<tag>`, `cover.slots.<tag>`) that shares its origin (the kit's `build_wheel` names
them so; a car that brings its own wheel or wheel covers under such names is found the
same way). A tire on a turned axle or off the ground (a spare) stays with the body.

A wheel that is another wheel moved along the same side (a truck's alike wheels) is built
as a copy of it, and one that is a wheel of the other side mirrored is built as that mirror
(never when lettering is baked onto it: the text would read backwards); either shares its
source's UVs (`uv_shared_with` in `pack.json`), so they use one set of texels. Glass carries
UVs of its own (one unit square, no textures yet).

## Textures

Two baked slots, `body` (4096) and `wheels` (2048), PNG, each with five textures. The
wheels slot also holds each source wheel's rim face (below, LOD3), an island of its own
that no LOD0 face uses:

| Texture | Space | Channels |
|---|---|---|
| `<slot>_base_color.png` | sRGB | RGB: the color of everything that is not tinted, and on the tinted surfaces what lies on the paint (dust times crease grime). A: 1 |
| `<slot>_normal.png` | linear | RGB: tangent space normal, **OpenGL convention** (+Y, glTF's and the repo's material library's); flip green for DirectX (Unreal's importer has the switch). Tangents are in the glTF (MikkTSpace) |
| `<slot>_orm.png` | linear | R: ambient occlusion, G: roughness, B: metallic, A: clear coat weight |
| `<slot>_mask.png` | linear | R: primary paint weight, G: secondary paint weight, B: accent weight, A: shade on the tinted color (1 clean, lower in creases) |
| `<slot>_emissive.png` | sRGB | RGB: emission color times its strength over `emissive_strength`, at most 1 (an emitter seen only through glass and stronger than the scale is clipped keeping its hue, `emissive_clipped`). A: specular level (0.5 standard, 0 on voids) |

Glass is a parameter-only slot (`materials.glass.params`: the material most of the glass
wears (`material`, a car's own such as a dome's lower IOR, else the kit's `glass`), its
color, roughness, IOR, transmission; `opaque_from_lod` 2: LOD2 and LOD3 carry no cabin, draw the glass dark and
opaque there).

### Color as a parameter

No paint hue is baked. An engine material recombines:

$$w = R + G + B,\qquad \text{albedo} = \text{base}\,(1 - w) + (R\,P_1 + G\,P_2 + B\,P_3)\,A$$

with $R, G, B, A$ from the mask and $P_1, P_2, P_3$ the deployed colors (Custom Primitive
Data in Unreal). Where dust lies on the paint, $w$ falls below 1 and the base color (the
dust) shows. Roughness, metallic and coat stay baked (the finish is part of the design).
`colors` in `pack.json` holds the show colors (and the finish values) as defaults:
`primary` (the kit's `paint`), `secondary` (`paint2`), `accent` (`caliper`). Any other
material in exactly one of those colors follows its channel too (`tinted_materials`).

Coat roughness is constant per slot (`params.coat_roughness`). Detail finer than a texel is
not baked (the bake holds its mean): the paint's flake and textures such as the carbon
weave are listed in `micro_detail` for the engine's detail maps.

## What is baked down

So that LOD0 is near 150,000 triangles without decimating the silhouette:

- **Always**: relief no taller than 3.2 mm over another object's surface (a lamp only
  when 70% of it lies on one other piece: a band between flutes would bake in patches) (lettering,
  ribbons, decals, glyphs, studs) is removed and baked onto the surface under it (color,
  normal, occlusion, emission); dense arrays of small parts lying in a slab (at least 8
  parts, 1,500 triangles, 15,000 triangles a square meter of outline, under 45 mm deep:
  honeycombs, mesh grilles) become one flat card in the slab's back face (what stands inside its depth stays in front), the array
  baked onto it, a black void behind its holes; tires over 6,000 triangles are rebuilt as a
  lathe of their cross section's outer envelope (64 segments), the tread pockets and
  sidewall lettering baked onto it.
- **Over the budget, in this order**: relief up to 12.5 mm (bolt rows, badges, lenses),
  most triangles first; then every part of 600 triangles or more alike, body panels too
  (glass, lamps and wheels never), at most halved a round, four rounds. Collapsed parts
  have their originals baked onto them.
- **Never seen**: faces no ray from outside reaches (through glass counts, for the cabin)
  are removed (a lamp's never: a light band behind a row of flutes, seen only through the
  gaps, is its own class), and coincident faces (one of two facing the same way, both of
  two facing apart). Faces seen only through glass are the cabin class, only from below the
  underside class. A face never seen from its front but seen from its back (a design
  face turned the wrong way, which Blender draws and an engine culls) is turned round, and
  so is a face seen better from its back than its front (exterior over cabin over
  underside).

`baked_down` in `pack.json` lists every piece and what became of it.

## UVs

Smart projection per slot (66 degrees; the islands that end up covering texels another
island covers, over 0.1% of the atlas, as a lip curling under its frame does, are projected
again at 34 degrees, those still lying over themselves once more at 20), each island scaled to one texel density times its class's
weight (exterior 1, cabin 0.4, underside 0.35, a lamp seen only in gaps 0.35, a rim face
0.5), then a skyline packer at the largest
common scale, each lying flat or stood up, a smaller one first in a gap a taller one left
under the skyline, with 8 px between islands at 4096 (bake margins 8 px; whole texels
between islands down to the 512 mip); an island narrower than 16 px has half its width
round it, 2 px at least (it is under a texel by that mip). On the body, an island thinner
than 2 texels (2 area / perimeter: a letter's strokes, a hairline lamp) is scaled up to
that, 8 times at most, while that grows the atlas by 10% at most (else 1.5, then 1
texel), so it covers texel centers and bakes. The body's islands
that carry baked-down relief (lettering, decals, small lamps) get up to twice the density,
less where that would grow the atlas by more than 20% or take the exterior's 5th
percentile under 3% over the floor (`uv.detail_boost`). Baked-down detail is carried out
into the margins round its islands, so a seam across it does not show the surface under
it. Measured density (px/m, area weighted median and 5th percentile, per class) is in
`uv.texel_px_per_m`.

## Size class

A vehicle whose body has 55 m2 of exterior or more (faces of class exterior after the
unseen ones are removed: trucks, vans, the hauler class) is **large**, else **standard**.
The class sets the LOD budgets (LOD3 8,000 triangles large, 5,000 standard) and the texel
floor of `texel_density` (large: 240 px/m, standard: 300 px/m; set so that the Mule, the
largest, passes with a few percent to spare, and never under 220 px/m). The lower floor is
what the check asks only: the unwrap's detail boost keeps the standard floor's margin in
every class. `pack.json`'s `size_class` records the class, the exterior it was measured
on, the rule, the budgets and the floor; the report and the proof's footer repeat them.

## LODs

LOD0 the parts as above. LOD1 to LOD3 are made from LOD0 to their budgets (60,000, 20,000,
5,000, or 8,000 for a large vehicle), each at most 60% of the LOD before it (a car under
budget still steps down), and share LOD0's textures. Per part, in this order:

1. **Left out.** From LOD2 the cabin's faces; from LOD2 every piece no larger than 5 cm
   in any direction (bolts, sensors, small vents; lamps never); at LOD3 the faces seen only
   from below, and every face no ray from outside reaches once the glass is opaque (the
   inner sheet of thick glass, the backs of panels seen only through the glass; lamps
   kept). At LOD3 the units are loose parts (a piece's connected faces: one object's
   mirrored bolts are many parts): a part no larger than 12 cm goes, or with no more than
   0.02 m2 of area unless it is slender (two sides of 5 cm at most: a cable, a rod, a
   handle; what hangs on it would hang in the air); a part on the edge of the mesh's box
   never goes (the LOD keeps LOD0's size). Then a part no larger than 60 cm that no chain
   of parts touching (within 4 mm) joins to the largest part any more goes too (a hook whose
   cable went); a lamp never does: the parts left out that hold it up stay.
2. **Welded** (LOD3). Pieces that meet edge to edge (panels, a lamp in its bezel) are
   welded where their vertices coincide (1.5 mm), so the collapse moves their shared border
   as one and opens no gap between them.
3. **Coplanar faces merged.** Faces within 0.5 degrees of one plane (LOD2 1, LOD3 2) are
   merged and triangulated again, so a flat door is a few long triangles and the budget goes
   to the curves; never across a UV island's border, a face class's or a piece's, and never
   a face LOD0 shades curved (its normals off its plane: a bevel, glass drawn smooth over
   flat facets).
4. **Collapsed** (Blender's collapse, body symmetric in y) at one ratio for every part to
   the budget. A piece the collapse takes under its floor (LOD2: 8 triangles and 150 a
   square meter of its area, LOD3: 6 and 120, less when that would take over 60% of the
   budget; a lamp keeps half (LOD2) or a quarter (LOD3) of its own) is collapsed again alone
   to that floor, so no panel or light strip vanishes (the floors are lowered with the
   rest where they alone would pass the budget). Glass LOD0 draws through its normals
   (a coarse sheet shaded smooth: over 10% of its corners 15 degrees off their face) is not
   collapsed while it is under 30% of the LOD (LOD3: 20%); over that its grid is
   unsubdivided instead (every kept corner where LOD0 had it), and collapsed only if still
   over. Other glass is kept as merged at LOD3 while under 12% of the LOD (flat panes a few
   triangles each: a pane collapsed further pulls away from its frame), else collapsed as
   any part.
5. **Wrecks put right** (LOD3, body). A loose part the collapse took off its own shape (a
   point of the collapsed part, its faces' and edges' middles, more than 1 cm or 12% of its
   size from the part as prepared, or the part's 95th percentile that far from the
   collapse; a part over 60 cm: 3 cm or 2% of its size, at the 98th percentile: a drum's
   flanges folded through it, a step or a tow hook flattened into a spike) is put right,
   the cheapest first while the fixes cost no more than 20% of the LOD over the collapse
   (halved while the collapse alone cannot pay): a part no larger than 60 cm becomes its
   convex hull (26 corners at most, closed and clean) where the hull keeps within that
   distance of it both ways (its faces on the part or on what the part stands against, whose
   faces there were removed as unseen) or the part is on the edge of the box; a larger one
   becomes its hull where that is within 3 cm of it (a cable coiled on a drum), else, as a
   lamp, is collapsed again alone at twice its triangles. A small wreck past the budget
   goes. Every vertex is then kept inside the part's own LOD0 box (the collapse places some
   past the surface).
6. **Wheels at LOD3** are made anew: a round tube of 20 segments through LOD0's tire
   envelope (bead, sidewall, tread edges) with its own round normals, and a flat disc
   across each bead ring (20 triangles). The outer disc wears the wheel's rim face: when
   the textures are baked, a disc on the source wheel's outside, just past its outermost
   point, is unwrapped with the wheels as an island of its own and baked from all the
   wheel's objects along the axle (what the wheel shows from the side: spokes, the dark
   between them, the brake behind; colors, normals, occlusion, emission), and its UVs are
   an affine map of the wheel's own x and z (`cg_disc_uv`, the same for a wheel's twins), so
   a far wheel shows its rim as LOD0 does, never black. The inner disc wears the same.
7. **UVs and normals laid on from LOD0.** Every corner takes the UV and the shading normal
   LOD0 draws at the point of the face's own UV island straight under it (along the face
   normal, else the nearest; a point a little inside the face, so the two sides of a crease
   keep theirs). A face reads only its own island, so a texture cannot tear across an
   island's border however the collapse moved it, and the LOD shades as LOD0 does
   (recomputed normals on a coarse mesh ripple in every reflection).

A LOD whose box falls short of LOD0's (or passes it) by more than `lod_bounds` allows (a
glass crown collapsed away) has the parts that reach that side collapsed again at twice
their ratio, the others a little more to hold the budget.

Each LOD is measured against LOD0 (`lods[k].fidelity` in `pack.json`, check
`lod_fidelity`): at points spread over the body's exterior (one per 40 cm2 at least), LOD0's
surface nearest along the normal line (within 3 cm) that faces the same way (not a thin
plate's far side), the angle between the two shading
normals and, through the two UVs, the bake's base color and paint weights (at 1024 px):
the area weighted 95th percentile angle (`normal_p95_deg`), the share over 25 degrees
(`bent_share`), the share with a channel off by 0.25 (`texture_share`, a torn or smeared
texture) and the share with no LOD0 within reach (`miss_share`, reported only).

## Collision

4 to 12 convex hulls of body and glass (wheels are the engine's raycasts): slabs along x,
each split at its beltline where what stands above is narrower; each hull at most 128
corners (the farthest points along 128 directions). `collision.glb`, nodes
`UCX_body_<nn>` (Unreal's convention), listed under `collision.hulls`.

## pack.json

| Key | What |
|---|---|
| `format`, `version` | `cybergen.vehicle_pack`, 1 |
| `car`, `title` | file name, the script's first line |
| `source` | the script's, `carkit.py`'s and `game.py`'s sha256; the original's triangles and objects |
| `kind` | `wheeled` or `hover` |
| `dimensions` | length, width, height, min and max (LOD0, wheels included) |
| `wheelbase`, `track`, `ride_height` | axle to axle; per axle (0 the front) left to right; the body's lowest point |
| `lods` | per LOD: file, triangles, budget, triangles per part; from LOD1 `fidelity` (see LODs) |
| `parts` | per node: name, kind (`body`, `glass`, `wheel`, `brake`), material, pivot; wheels and brakes also radius, width, side, axle, `steers`, `spins`, `follows`, `uv_shared_with` |
| `materials` | per slot: textures (file, size, color space, channels) and params |
| `colors`, `tinted_materials` | show colors per channel; the materials that follow them |
| `emissive_strength`, `emissive_clipped` | the emissive texture's 1.0 in Blender's strength (day values): the strongest emitter seen from outside; the cabin-only emitters stronger than that, clipped to it (their true strength is in `lights`) |
| `micro_detail` | detail left to the engine's detail maps |
| `lights` | every emissive surface grouped into lamps: role (`head`, `tail`, `marker`, `wheel`, `cabin`, `glow`, `lamp`, `emitter`), part, position, size, facing, area, color, strength |
| `collision` | file and hulls |
| `views`, `cameras` | the hero view, the studio as the car's script set it up (`views.studio`: per light its energy and color, and `unlit`, the parts a light was linked off), and the cameras of the proof renders |
| `baked_down` | what was removed or replaced, and how |
| `size_class` | `name` (`standard` or `large`), `exterior_m2`, `rule`, `lod_budgets`, `texel_floor_px_per_m` |
| `uv` | islands, measured texel density, its floor, the density factor of the islands under baked-down detail (`detail_boost`) |
| `build` | test or full, samples, seconds per stage |

## Checks (`game_report.json`; the run fails when one fails)

- `files`: every file present and readable, textures at their sizes.
- `budgets`: LOD0 within its budget, the others within 10% of theirs.
- `uv_overlap`: at most 0.5% of the covered texels covered twice (LOD0, a shared pair once),
  nothing outside the unit square.
- `texel_density`: the exterior's 5th percentile at least the size class's floor (300 px/m,
  large 240; body at 4096, wheels at 2048; scaled with the size).
- `wheel_pivots`: every wheel's tread centered on its node's pivot (3 mm), its radius as
  `pack.json` says, the axle no lower than the radius less 12 mm.
- `lod_bounds`: every LOD's box within 2 cm (or 1.5% of the size) of LOD0's.
- `lod_fidelity`: every LOD drawn as LOD0 (above): `normal_p95_deg` at most 12, 25 and 36
  degrees (LOD1, 2, 3; rivets and bevels a collapse rounds off count there), `bent_share`
  at most 2%, 5%, 10%, `texture_share` at most 1%, 2.5%, 4%. A crumpled or torn LOD fails;
  a small part torn at LOD3 (a winch drum) can still pass, so the LOD row is still looked
  at.
- `collision`: 4 to 12 hulls.

## Proof

`proof/` and `game.jpg`: the pack alone (the GLBs and PNGs, through the formula above, in a
fresh Blender, in the kit's studio as the car's own script set it up: its light energies
and colors, and a light linked off some of the car's objects kept off the parts they make
up, at 30% of a part's area or more, from `views.studio`; a view from under the car without
its floor, as the car's own) next to the procedural original from the same camera,
a recolored copy, the textures, and the four LODs (from `opaque_from_lod` the glass dark
and opaque, as an engine draws it).
