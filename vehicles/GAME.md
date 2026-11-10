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
| `--lods A B C D` | triangle budgets (150000 60000 20000 5000) |
| `--samples K` | scales every bake and render sample count (1) |
| `--test` | 1024 / 512 textures, a quarter of the samples, half-size renders |
| `--docs` | also writes `docs/progress/AG18/<car>/game.jpg` and `game_report.json` |
| `--views a,b` | more views compared in `proof/` (the car's own, e.g. `nose,tail,wheel`) |
| `--keep-work` | keeps the raw bakes in `work/` |

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
lies along y and which stands on the ground, with every object named `<kind>.<tag>` that
shares its origin (the kit's `build_wheel` names them so; a car that brings its own wheel
under the same names is found the same way). A tire on a turned axle or off the ground (a
spare) stays with the body.

A right wheel that is its left partner mirrored is built as that mirror and shares its UVs
(`uv_shared_with` in `pack.json`), so the pair uses one set of texels. Glass carries UVs
of its own (one unit square, no textures yet).

## Textures

Two baked slots, `body` (4096) and `wheels` (2048), PNG, each with five textures:

| Texture | Space | Channels |
|---|---|---|
| `<slot>_base_color.png` | sRGB | RGB: the color of everything that is not tinted, and on the tinted surfaces what lies on the paint (dust times crease grime). A: 1 |
| `<slot>_normal.png` | linear | RGB: tangent space normal, **OpenGL convention** (+Y, glTF's and the repo's material library's); flip green for DirectX (Unreal's importer has the switch). Tangents are in the glTF (MikkTSpace) |
| `<slot>_orm.png` | linear | R: ambient occlusion, G: roughness, B: metallic, A: clear coat weight |
| `<slot>_mask.png` | linear | R: primary paint weight, G: secondary paint weight, B: accent weight, A: shade on the tinted color (1 clean, lower in creases) |
| `<slot>_emissive.png` | sRGB | RGB: emission color times its strength over `emissive_strength`. A: specular level (0.5 standard, 0 on voids) |

Glass is a parameter-only slot (`materials.glass.params`: color, roughness, IOR,
transmission; `opaque_from_lod` 2: LOD2 and LOD3 carry no cabin, draw the glass dark and
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

- **Always**: relief no taller than 3.2 mm over another object's surface (lettering,
  ribbons, decals, glyphs, studs) is removed and baked onto the surface under it (color,
  normal, occlusion, emission); dense arrays of small parts lying in a slab (at least 8
  parts, 1,500 triangles, 15,000 triangles a square meter of outline, under 45 mm deep:
  honeycombs, mesh grilles) become one flat card in the slab's back face (what stands inside its depth stays in front), the array
  baked onto it, a black void behind its holes; tires over 6,000 triangles are rebuilt as a
  lathe of their cross section's outer envelope (64 segments), the tread pockets and
  sidewall lettering baked onto it.
- **Over the budget, in this order**: relief up to 12.5 mm (bolt rows, badges, lenses),
  most triangles first; then the densest small parts (never body panels or glass) are
  collapsed, their originals baked onto them.
- **Never seen**: faces no ray from outside reaches (through glass counts, for the cabin)
  are removed, and coincident faces (one of two facing the same way, both of two facing
  apart). Faces seen only through glass are the cabin class, only from below the
  underside class.

`baked_down` in `pack.json` lists every piece and what became of it.

## UVs

Smart projection per slot, each island scaled to one texel density times its class's
weight (exterior 1, cabin 0.4, underside 0.35), then a skyline packer at the largest
common scale, each lying flat or stood up, with 8 px between islands at 4096 (bake margins 8 px; whole texels between islands down to the 512 mip). Measured density
(px/m, area weighted median and 5th percentile, per class) is in `uv.texel_px_per_m`.

## LODs

LOD0 the parts as above. LOD1 to LOD3 are collapses of LOD0 (body and glass symmetric in
y) to their budgets (60,000, 20,000, 5,000), each at most 60% of the LOD before it (a car
under budget still steps down), sharing LOD0's UVs and textures; LOD2 and LOD3 drop the
cabin's faces.

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
| `lods` | per LOD: file, triangles, budget, triangles per part |
| `parts` | per node: name, kind (`body`, `glass`, `wheel`, `brake`), material, pivot; wheels and brakes also radius, width, side, axle, `steers`, `spins`, `follows`, `uv_shared_with` |
| `materials` | per slot: textures (file, size, color space, channels) and params |
| `colors`, `tinted_materials` | show colors per channel; the materials that follow them |
| `emissive_strength` | the emissive texture's 1.0 in Blender's strength (day values) |
| `micro_detail` | detail left to the engine's detail maps |
| `lights` | every emissive surface grouped into lamps: role (`head`, `tail`, `marker`, `wheel`, `cabin`, `glow`, `lamp`, `emitter`), part, position, size, facing, area, color, strength |
| `collision` | file and hulls |
| `views`, `cameras` | the hero view and the cameras of the proof renders |
| `baked_down` | what was removed or replaced, and how |
| `uv` | islands, measured texel density, its floor |
| `build` | test or full, samples, seconds per stage |

## Checks (`game_report.json`; the run fails when one fails)

- `files`: every file present and readable, textures at their sizes.
- `budgets`: LOD0 within its budget, the others within 10% of theirs.
- `uv_overlap`: at most 0.5% of the covered texels covered twice (LOD0, a shared pair once),
  nothing outside the unit square.
- `texel_density`: the exterior's 5th percentile at least 300 px/m (body at 4096, wheels
  at 2048; scaled with the size).
- `wheel_pivots`: every wheel's tread centered on its node's pivot (3 mm), its radius as
  `pack.json` says, the axle no lower than the radius less 12 mm.
- `lod_bounds`: every LOD's box within 2 cm (or 1.5% of the size) of LOD0's.
- `collision`: 4 to 12 hulls.

## Proof

`proof/` and `game.jpg`: the pack alone (the GLBs and PNGs, through the formula above, in a
fresh Blender, in the kit's studio) next to the procedural original from the same camera,
a recolored copy, the textures, and the four LODs.
