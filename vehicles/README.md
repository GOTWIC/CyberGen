# Vehicles: a designer's guide

Hand-designed vehicles, each one Blender 5.2 script in `cars/` built on the shared kit
`carkit.py`. A car script holds only its own design (stations, panels, details); the kit
holds the materials, the geometry helpers, the body builder, the wheel, the studio, the
cameras and the renders. `cars/vanta_r.py` is the reference car: read it once.

Frame: x forward, y left, z up, meters, origin on the ground under the car's middle.

## Run

Always through the wrapper. It holds a machine-wide lock, so several sessions never render
at once; a second call waits its turn.

```
vehicles/blender.sh vehicles/cars/NAME.py --out DIR              # build and count only (1 s)
vehicles/blender.sh vehicles/cars/NAME.py --out DIR --preview    # DIR/preview.jpg, about 10 s
vehicles/blender.sh vehicles/cars/NAME.py --out DIR --sheet      # DIR/sheet.jpg, about 2 min
```

| Argument | What |
|---|---|
| `--out DIR` | where files go (made absolute; default `~/.cache/cybergen/vehicles/NAME`) |
| `--preview` | four small views (hero, rear three-quarter, side, top) in one 1920 x 1080 image, 24 samples. The image to look at while designing |
| `--sheet` | the one deliverable: hero on top (3840 x 1536), front, side and back below, each rendered at its tile's size, with a light bloom; 3840 x 2160, 160 samples |
| `--extra VIEW` | a fifth small tile on the sheet (`top`, `under`, a view of the car's own), laid into a corner of the hero; a car sets its own with `K.shoot(extra=...)` |
| `--night` | the night studio (wet floor, teal and magenta rims), for any mode |
| `--views a,b` `--res W H` | full frames `car_<view>.jpg` of single views (close-ups), 1600 x 900 unless `--res` |
| `--samples N` | overrides a mode's samples |
| `--blend`, `--glb` | `car.blend`, `car.glb` (never commit them) |

`BLENDER=/path/to/blender` picks another Blender. `--sheet` and `--preview` put their tiles
together with `post.py`, run by the repo's `.venv` Python (`CYBERGEN_PYTHON` overrides).

## The line-up

`lineup.py` puts every car of `cars/` into one scene at one scale and renders it:

```
vehicles/blender.sh vehicles/lineup.py            # docs/progress/AG18/lineup.jpg, 3840 px wide
vehicles/blender.sh vehicles/lineup.py --test     # 1920 px, 24 samples, into the cache
```

- **Cars.** Found by listing `cars/*.py`, so a new car joins with nothing to edit. Each is
  built once by its own script with `--blend` into `~/.cache/cybergen/vehicles/lineup/<car>/`
  (never in the repo) and built again only when its script or `carkit.py` is newer; its `CAR`
  collection is then appended under an empty of its name. A car that fails to build or
  append is left out with a message (`BUILD FAILED`, `SKIPPED`, `LEFT OUT` in the log, the
  build's own output in `<car>/build.log`).
- **Layout.** A column per brand in `BRANDS.md`'s order (a car's brand is the one whose
  table lists its model, else the first word of its file name), its cars one behind
  another, lowest in front, each row a little to the right of the one before. Rows are
  spaced by the height of the cars in front, so none hides the one behind, and every car is
  turned to show the camera the same three-quarter view of its nose and left flank. The
  brand's name lies on the floor in front of its column. The frame's shape follows the
  layout, between 2.7:1 and 16:9.
- **Studio.** Its own floor and cove, as wide as the camera's distance asks (the camera
  stands about 100 m off with a 105 mm lens), a pool of soft light over the cars; each car
  keeps its own lights, and the image gets the sheets' bloom.
- **Time.** About 1.5 minutes for 19 cars (4.5 million triangles): 25 s to build the cars
  the first time, 3 s to append them, a minute to render 3840 x 1422 at 128 samples. A
  `--test` takes 12 s once the cars are cached.
- **Arguments.** `--out FILE`, `--cache DIR`, `--width N`, `--samples N`, `--only a,b` (some
  cars), `--rebuild` (every car again), `--blend` (the scene as `lineup.blend` in the cache).

The spacing, the camera's height and the turn are the constants at the top of `lineup.py`.

## Game packs

`game.py` turns any car into a game-ready pack for an engine: a few named parts (body,
glass, a node per wheel and brake about its axle), an atlas per material slot with baked
textures (base color, normal, occlusion-roughness-metallic-coat, a paint mask, emissive),
four LODs, convex collision hulls, the lights as data and a proof image. The paint's hue is
not baked: an engine material recolors the car through its mask with any color. The
format is the contract in `GAME.md`.

```
vehicles/blender.sh vehicles/game.py --car vanta_r                  # ~/.cache/cybergen/vehicles/game/vanta_r/
vehicles/blender.sh vehicles/game.py --car vanta_r --docs           # also docs/progress/AG18/vanta_r/game.jpg
vehicles/blender.sh vehicles/game.py --car vanta_r --test           # 1024 / 512 textures, about a minute
```

- **No hints from the car.** The script runs unchanged; wheels, glass, paint channels and
  what to bake down are found by rules on the built objects (`GAME.md` lists them). Fix the
  tool, not the car.
- **Baked down.** Lettering, ribbons and other flat relief go onto the surface under them;
  dense arrays (honeycombs) become cards; dense tires become lathes with the tread and
  sidewall marks baked on; over budget, taller relief such as bolt rows, then a collapse of
  every part alike (never glass, lamps or wheels). Faces nothing can see are removed; a
  face seen better from behind is turned round. Islands under baked lettering get more
  texels, thin islands at least two texels across.
- **Proof.** `game.jpg`: the pack alone in the kit's studio next to the procedural original
  from the hero view, a recolored copy, the textures and the four LODs. `--views a,b`
  compares more of the car's views (`proof/original_<view>.jpg` and `baked_<view>.jpg`);
  look at them at full size.
- **Checks.** Budgets, UV overlap, texel density, files, wheel pivots, LOD bounds, hull
  count (`game_report.json`); the run fails when one fails.
- **Time.** About 4 to 6 minutes a car at full size (most of it the bakes and the proof);
  packs are 18 to 31 MB and never go in git.

## Workflow

1. **Stations and lines.** Draw the body as character lines (top centerline, hood crease,
   shoulder, widest line, rocker, floor edge, floor centerline, ...) crossing stations
   (nose, axles, windshield base, roof, tail, ...). Every station gives one 3D point per
   line; `None` is filled in between its neighbors. That grid is a quad cage.
2. **Creases and panels.** Say which cage edges are sharp, and name the panel of every
   quad. Run `--preview`, look, move points, repeat. Get the stance and the silhouette
   right before any detail.
3. **Cuts and caps.** Wheel wells (if the car has any), mouth and tail, glass, recesses.
4. **Details** on the cage's points (`PT[station][line]`) and on the surface as built
   (`on_body`, `ribbon`, `text_on_body`): lights, vents, trims, wing, interior, wheels.
5. **Final sheet.** `--sheet` once, into `docs/progress/AG18/<car>/`. Look at it at full
   size before you call it done.

## A minimal car

```python
"""Maker Model: one line about it (made-up names only)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import carkit as K                                  # noqa: E402
from carkit import Geo, V3                          # noqa: E402

K.materials(paint=(0.02, 0.10, 0.22), paint_finish="pearl", paint2=(0.80, 0.42, 0.04),
            led_front=(1.0, 0.85, 0.5))

LINES = "CSUFB"         # top center, shoulder, widest, floor edge, floor center
ORDER = ["N", "A", "W", "R", "D", "T"]
S = K.fill([
    [(2.10, 0, .55), (2.08, .60, .52), (2.05, .82, .40), (2.08, .70, .22), (2.10, 0, .20)],
    [(1.40, 0, .78), (1.40, .66, .76), (1.40, .92, .52), (1.40, .80, .20), (1.40, 0, .18)],
    [(0.70, 0, .90), (0.70, .70, .88), None, None, None],
    [(-.30, 0, 1.32), (-.30, .58, 1.28), (-.30, .95, .60), (-.30, .82, .20), (-.30, 0, .18)],
    [(-1.3, 0, 1.25), (-1.3, .60, 1.20), (-1.3, .94, .62), (-1.3, .80, .22), (-1.3, 0, .20)],
    [(-2.1, 0, .95), (-2.1, .62, .92), (-2.08, .86, .60), (-2.1, .72, .30), (-2.1, 0, .28)],
])
PT = K.table(ORDER, LINES, S)       # PT["A"]["U"]: a point to hang details on


def panel_of(i, j):                 # quad between stations i, i + 1 and lines j, j + 1
    if j == 3:
        return "floor"
    if j == 0:
        return ("hood", "hood", "glass", "roof", "deck")[i]
    return "side" if j == 1 else "sill"


PMAT = dict(hood="paint2", roof="paint2", deck="paint", side="paint", sill="cladding",
            floor="underbody", glass="glass", trim="gloss_black", tail="void", well="well")
ARCH = (-20, 20, 60, 100, 140, 180, 200)
wells = Geo()
K.well_cutter(wells, 1.35, 0.36, 0.43, 0.60, ARCH)
K.well_cutter(wells, -1.30, 0.36, 0.43, 0.60, ARCH)
K.build_body(S, panel_of, PMAT,
             line_crease={(i, j): 1.0 for i in range(5) for j in (1, 3)},
             station_crease=lambda i, j: 1.0 if i in (0, 5) else 0.0,
             front=dict(kind="flat", panel="sill"), rear=dict(kind="flat", panel="tail"),
             glass=[("glass", 0.03)], cutters=[(wells, "well")])

g = Geo()
g.sweep([PT["N"]["S"] + V3((0.01, 0, 0)), PT["N"]["U"] + V3((0.01, 0, 0))],
        [(-0.01, -0.006), (0.01, -0.006), (0.01, 0.006), (-0.01, 0.006)], up=(1, 0, 0))
g.obj("led.front", "led_front", mirror=True)

for side, s in ((1, "l"), (-1, "r")):
    K.build_wheel("f" + s, 1.35, 0.36, 0.26, 0.26, 0.94, side)
    K.build_wheel("r" + s, -1.30, 0.36, 0.30, 0.27, 0.95, side, spokes=5, style="blade")

K.VIEWS["hero"].update(dir=(1.0, 0.9, 0.35))      # a car may choose its hero direction
K.shoot()                                         # K.shoot(extra="top"): a fifth tile
```

## The kit

Importing `carkit` reads the arguments (`K.ARGS`), empties the scene and makes the
collections `K.CAR` and `K.STUDIO`. Everything is helper level: raw geometry is always
allowed (`Geo.add(verts, faces)`, or bmesh and bpy directly, linked into `K.CAR`).

| Name | What |
|---|---|
| `materials(**palette)` | the library in `K.MAT`. Palette keys: `paint`, `paint_finish` (`metallic`, `pearl`, `gloss`, `satin`, `matte`, `chrome`, or `(metallic, roughness, coat)`), `paint2`, `paint2_finish`, `dust`, `dust_amount`, `dust_z` (`(0.12, 0.55)`: the paint is all dust at the first height and below, clean from the second up; raise both for a truck or a hover car), `cladding`, `glass`, `led_front`, `led_rear`, `led_accent`, `led_wheel`, `caliper`, `seat`, `interior`, `screen`, `rim`, `rim_bright`, `decal`, `ember`. Names: `paint`, `paint2` (flake, dust, crease grime), `carbon` (weave), `gloss_black`, `cladding`, `underbody`, `void`, `well`, `grille`, `glass`, `rubber`, `rim`, `rim_bright`, `disc`, `caliper`, `interior`, `seat`, `screen`, `decal`, `led_*`, `lamp`, `ember` |
| `pbr(name, color, metallic, rough, **inputs)`, `emit(name, color, strength)`, `paint(name, color, finish, dust, dust_amount, flake, dust_z)`, `carbon(name, dark, light)`, `void(name)` | a car's own materials |
| `Geo()` | collects closed solids: `box(center, size, rot)`, `hexa(8 points)`, `prism(polygon, vector)`, `lathe(profile, n, a0, a1, xf)` about y, `sweep(path, section, up, closed)`, `tube(a, b, r, n)` a straight round bar between two points, `louvers(a, b, c, d, n, w, th, tilt, out)`, `honeycomb(polygon, x, R, wall, depth, sgn, keep)`, `add(verts, faces)`; then `obj(name, mat, bevel, segs, angle, mirror, sharp, flip_y, loc, rot)` (`rot`: an Euler, three angles or a matrix, about the object's origin at `loc`) |
| `finish(ob, bevel, segs, angle, mirror, wn, sharp)` | mirror, bevel and shading on any mesh object |
| `fill(stations)`, `table(names, lines, S)` | `None` points interpolated; `PT[station][line]` |
| `build_body(stations, panel_of, pmat, line_crease, station_crease, name, front, rear, recesses, glass, cutters, subdiv, mirror, wrap, gap, thick, glass_thick, project, bevel, bevel_segs)` | one body piece (below); returns `.parts[panel]` objects and `.caps["front"/"rear"]` inner rings |
| `well_cutter(g, cx, cz, r, y0, angles)` | a wheel well solid for `cutters` |
| `arch_trim(g, cx, cz, r, y_in, y_out, angles)`, `arch_bolts(g, cx, cz, r, y, angles)` | faceted arch trim and its bolts |
| `on_body(u, v, proj, objs)` | surface point and normal of the body as built, seen along `'y'` (left side, u = x, v = z), `'Y'` (right), `'x'` (front, u = y, v = z), `'X'` (back), `'z'` (top, u = x, v = y); over all body pieces, or over `objs` (an object or a list: pods, a wing, one panel), with nothing to set or reset |
| `ribbon(g, pts, proj, w, objs=)`, `text_on_body(g, txt, size, x0, z0, side, proj=, turn=, objs=)`, `text_flat(g, txt, size, origin, right, up)`, `stud(g, loc, n, profile, seg)` | strips, lettering and studs on the surface. `text_on_body` writes on the flank; with `proj='z'` on a roof, hood or deck, its middle at x = `x0`, y = `z0`, read from the left side (`side=1`) or the right (`-1`), turned by `turn` degrees (90: read from behind) |
| `body_bvh(objs, default)` | the projector's tree, returned; `body_bvh()` alone makes the body pieces the default target again |
| `band_point(p, center, w, out)`, `shr(quad, k, lift, out)`, `my(p)` | a point inside a cap's lip; a quad shrunk and lifted; a point mirrored |
| `build_wheel(tag, cx, R, w, Rr, out_y, side, cz, spokes, style, ring, caliper, rim, bright, tire, loc, rot)` | a wheel: tire radius, width, rim radius, outer face y; `style` `twin`, `blade` or `disc`; `ring` and `caliper` are material names or `None`; `cz` lifts the axle. `tire=None` leaves the tire out, `rim=None` the rim and its hub (`bright=None` the hub alone), for a car that brings its own; `loc` and `rot` put the wheel anywhere, turned: a spare |
| `VIEWS` | the views by name (`hero`, `rear`, `rear_l`, `side`, `front`, `back`, `top`, `under`, `low`): `dir`, `lens`, then `dist` or a fit (`fit` prefixes, `margin`), `focus`, `fstop`, and optionally `target` and `no_floor` (below). Change or add entries before `shoot()` |
| `shoot(sheet=(4 views), preview=(4 views), extra=None)` | the end of every script: stats, studio, renders, exports. `extra`: the sheet's fifth tile, a view name or `dict(view=, size=(840, 400), corner="tl", margin=)` |
| `build_studio()`, `add_camera(name, view)`, `view_target(view)`, `car_points(prefixes)`, `in_studio(p)`, `setup_render()`, `render_view(name, path, res, samples)`, `render_sheet()`, `render_preview()`, `stats()`, `tri_count()`, `export_glb(path)`, `log(msg)` | what `shoot()` is made of |

### build_body

A cage of `len(stations)` by `len(lines)` points becomes quads; creases are set; it is
mirrored, subdivided, cut, split by panel with real gaps, and each panel gets a rim and
bevelled edges.

- **Stations** run front to rear. With `mirror=True` (default) the lines run from the top
  centerline (y = 0) down the left side to the floor centerline (y = 0), and the mirror
  closes the hull.
- **`panel_of(i, j)`** names each quad; **`pmat`** maps every panel name to a material.
  Panels on `glass*` materials become thin glass, on `void*` stay unbevelled, on `paint*`
  get the wider bevel.
- **Creases**: `line_crease` (edge along line j from station i to i + 1) and
  `station_crease` (edge on station i between lines j and j + 1) are each a function
  `(i, j)`, a number, a dict `{(i, j): w}` or a table `[i][j]`.
- **Caps**: `front`, `rear`: `None` leaves the end open; `dict(kind="flat", panel=P)` is a
  flat face; `dict(center=, depth=, inner=P, frame=P, band=0.05, band_panel=P,
  band_lines=N)` is a recessed mouth with a band round its lip. `body.caps["front"]` gives
  the inner ring, for a grille polygon.
- **`recesses`** `(i, j, thickness, depth[, inner, wall])`: a sunk vent in quad (i, j).
  **`glass`** `(panel, inset[, trim])`: a trim frame with sharp corners.
- **`cutters`** `(Geo, panel)`: solids cut out (wheel wells, a tunnel through the body).
  None for a hover car or an open-wheel car.
- **Bevels**: `bevel=None` gives paint panels 4.5 mm and the rest 3 mm; a number is for
  every panel, a dict `{panel: width}` for some (0 for none); `bevel_segs` (2) its segments.
- **More pieces**: call it again with another `name` (a cab and a bed, a canopy, pods).
  A piece whose first and last lines are not on y = 0 mirrors into a left and a right
  copy: with `wrap=True` (last line joined to the first) that is a pair of closed tubes,
  such as pontoon fenders or hover pods.
- **Open shells**: `mirror=False` builds the cage as given, `wrap=False` leaves it a
  sheet. Crease its outline (line creases on the first and last line, station creases on
  the first and last station) or subdivision rounds its corners away. Do not cut an open
  shell with `cutters`: the boolean needs a closed hull.

### Views, the fit and the studio

- **Target.** A view with no `target` aims at the middle of what it fits: for the whole car
  the middle of its length and of its own height, on the centerline. A hover car or a tall
  truck is framed like a low coupe with nothing to set. Give a view a `target` to aim it
  yourself (close-ups, a hero that should sit lower in its frame).
- **Fit.** A view without `dist` stands where the car's silhouette just fills the frame less
  its `margin` (0.05 of the frame on each side; the sheet uses 0.025 for the hero and 0.04
  below). The silhouette is the convex hull of the car's vertices as built (`car_points`),
  not the objects' boxes, so the margin is what you see. Negative margins are never needed.
- **Studio limits.** The floor is flat to 16 m from the middle, then the cove rises to a
  wall 25 m out and 22 m high. No camera leaves it: it stays 0.5 m clear of the cove and
  under 21 m. A fitted view that would stand farther is held there and takes a shorter lens
  that still shows the whole car (the log says so: `view side: its camera is held ...`); a
  `dist` view is pulled in. That happens to side views of long, tall vehicles in the sheet's
  wide tile (the 5.7 m pickup: 85 mm for 110; a van 7.3 m long and 3.2 m tall: 53 mm) and
  to top views of vehicles over about 6 m; every sheet and preview view of that van is whole.
- **Lights.** The two low strip lights at the sides light the flanks and show in the paint,
  but not to the camera or through glass (they used to show as white windows in side
  views of upright glass).
- **`under`** looks up from below with the studio hidden (`no_floor=True`): the under-floor
  view of a hover car, lit by its own emitters and the grey world.
- **The fifth tile.** `K.shoot(extra="top")` (or `--extra top`) lays one more small view
  into a corner of the hero, over it: the hero keeps its size. Top left by default, the
  empty wall over the nose; `extra=dict(view="under", corner="br", size=(840, 400))` picks
  another corner or size. Check on the sheet that the corner is free of the car.

## Lessons learned

- **A quad cage, not a loft.** Design the body as quads with creases and let subdivision
  smooth it. A faceted, triangulated loft looked like papercraft.
- **Creases.** 1.0 gives a sharp character line, a partial crease (0.5 to 0.7) a soft one,
  0 a smooth surface. A vertex where three or more sharp edges meet becomes a corner.
- **bmesh layers** (crease, ids) must be created before the vertices, or the vertices made
  earlier become invalid.
- **The cage shrinks** under subdivision: the surface lies inside the cage wherever it is
  not creased. Check clearances (tire to arch, a detail to the surface) on the result, with
  `on_body`, not on the cage's points.
- **Cutters and thin places.** A boolean cutter that reaches through a thin part of the
  hull punches a hole. Keep cutters inside the body's thickness or go all the way through
  on purpose.
- **Voids.** A black "void" material needs zero specular (`K.void()`), or it goes grey
  under the lights.
- **Reflections.** Glossy flat surfaces mirror the studio lights at grazing angles. Judge
  a material from several views, never from one.
- **Leaning glass.** Flat glass that leans in more than about 25 degrees from upright
  mirrors the top light in side views: the window goes white. Keep side glass more upright
  than that, give it a little crown, or break it with a fold.
- **Projecting on other pieces.** `on_body`, `ribbon` and `text_on_body` take `objs` (pods,
  a wing, a single panel). Never set `K._BVH` yourself.
- **Dust.** A tall or floating vehicle wants its dust line higher: `dust_z` in the palette.
- **Lettering** uses the DIN font on macOS (`carkit.FONTS`).
- **Names.** Every maker, model and word on a car is made up. Never name a real maker, a
  real model or any game, in text on the car, in file names or in comments.
- **Panel names** are yours, but every one must be in `pmat`, including the defaults a
  feature uses (`vent` for recesses, `trim` for glass) and the cutters' panels.
- **Under the floor.** `stats()` prints any object reaching below z = 0; wheels stand on it.
- **One job at a time.** Use `blender.sh` for every run, also quick ones.
