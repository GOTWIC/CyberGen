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
| `--night` | the night studio (wet floor, teal and magenta rims), for any mode |
| `--views a,b` `--res W H` | full frames `car_<view>.jpg` of single views (close-ups), 1600 x 900 unless `--res` |
| `--samples N` | overrides a mode's samples |
| `--blend`, `--glb` | `car.blend`, `car.glb` (never commit them) |

`BLENDER=/path/to/blender` picks another Blender. `--sheet` and `--preview` put their tiles
together with `post.py`, run by the repo's `.venv` Python (`CYBERGEN_PYTHON` overrides).

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
K.shoot()
```

## The kit

Importing `carkit` reads the arguments (`K.ARGS`), empties the scene and makes the
collections `K.CAR` and `K.STUDIO`. Everything is helper level: raw geometry is always
allowed (`Geo.add(verts, faces)`, or bmesh and bpy directly, linked into `K.CAR`).

| Name | What |
|---|---|
| `materials(**palette)` | the library in `K.MAT`. Palette keys: `paint`, `paint_finish` (`metallic`, `pearl`, `gloss`, `satin`, `matte`, `chrome`, or `(metallic, roughness, coat)`), `paint2`, `paint2_finish`, `dust`, `dust_amount`, `cladding`, `glass`, `led_front`, `led_rear`, `led_accent`, `led_wheel`, `caliper`, `seat`, `interior`, `screen`, `rim`, `rim_bright`, `decal`, `ember`. Names: `paint`, `paint2` (flake, dust, crease grime), `carbon` (weave), `gloss_black`, `cladding`, `underbody`, `void`, `well`, `grille`, `glass`, `rubber`, `rim`, `rim_bright`, `disc`, `caliper`, `interior`, `seat`, `screen`, `decal`, `led_*`, `lamp`, `ember` |
| `pbr(name, color, metallic, rough, **inputs)`, `emit(name, color, strength)`, `paint(name, color, finish)`, `carbon(name, dark, light)`, `void(name)` | a car's own materials |
| `Geo()` | collects closed solids: `box(center, size, rot)`, `hexa(8 points)`, `prism(polygon, vector)`, `lathe(profile, n, a0, a1, xf)` about y, `sweep(path, section, up, closed)`, `louvers(a, b, c, d, n, w, th, tilt, out)`, `honeycomb(polygon, x, R, wall, depth, sgn, keep)`, `add(verts, faces)`; then `obj(name, mat, bevel, segs, angle, mirror, sharp, flip_y, loc)` |
| `finish(ob, bevel, segs, angle, mirror, wn, sharp)` | mirror, bevel and shading on any mesh object |
| `fill(stations)`, `table(names, lines, S)` | `None` points interpolated; `PT[station][line]` |
| `build_body(stations, panel_of, pmat, line_crease, station_crease, name, front, rear, recesses, glass, cutters, subdiv, mirror, wrap, gap, thick, glass_thick, project)` | one body piece (below); returns `.parts[panel]` objects and `.caps["front"/"rear"]` inner rings |
| `well_cutter(g, cx, cz, r, y0, angles)` | a wheel well solid for `cutters` |
| `arch_trim(g, cx, cz, r, y_in, y_out, angles)`, `arch_bolts(g, cx, cz, r, y, angles)` | faceted arch trim and its bolts |
| `on_body(u, v, proj)` | surface point and normal of the body as built, seen along `'y'` (left side, u = x, v = z), `'Y'` (right), `'x'` (front, u = y, v = z), `'X'` (back), `'z'` (top, u = x, v = y); over all body pieces |
| `ribbon(g, pts, proj, w)`, `text_on_body(g, txt, size, x0, z0, side)`, `text_flat(g, txt, size, origin, right, up)`, `stud(g, loc, n, profile, seg)` | strips, lettering and studs on the surface |
| `band_point(p, center, w, out)`, `shr(quad, k, lift, out)`, `my(p)` | a point inside a cap's lip; a quad shrunk and lifted; a point mirrored |
| `build_wheel(tag, cx, R, w, Rr, out_y, side, cz, spokes, style, ring, caliper, rim, bright, tire)` | a wheel: tire radius, width, rim radius, outer face y; `style` `twin`, `blade` or `disc`; `ring` and `caliper` are material names or `None`; `cz` lifts the axle |
| `VIEWS` | the views by name (`hero`, `rear`, `rear_l`, `side`, `front`, `back`, `top`, `low`): `dir`, `lens`, `target`, then `dist` or a fit (`fit` prefixes, `margin`), `focus`, `fstop`. Change or add entries before `shoot()` |
| `shoot(sheet=(4 views), preview=(4 views))` | the end of every script: stats, studio, renders, exports |
| `build_studio()`, `add_camera(name, view)`, `setup_render()`, `render_view(name, path, res, samples)`, `render_sheet()`, `render_preview()`, `stats()`, `tri_count()`, `export_glb(path)`, `log(msg)` | what `shoot()` is made of |

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
- **More pieces**: call it again with another `name` (a cab and a bed, a canopy, pods).
  A piece whose first and last lines are not on y = 0 mirrors into a left and a right
  copy: with `wrap=True` (last line joined to the first) that is a pair of closed tubes,
  such as pontoon fenders or hover pods.
- **Open shells**: `mirror=False` builds the cage as given, `wrap=False` leaves it a
  sheet. Crease its outline (line creases on the first and last line, station creases on
  the first and last station) or subdivision rounds its corners away. Do not cut an open
  shell with `cutters`: the boolean needs a closed hull.

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
- **Lettering** uses the DIN font on macOS (`carkit.FONTS`).
- **Names.** Every maker, model and word on a car is made up. Never name a real maker, a
  real model or any game, in text on the car, in file names or in comments.
- **Panel names** are yours, but every one must be in `pmat`, including the defaults a
  feature uses (`vent` for recesses, `trim` for glass) and the cutters' panels.
- **Under the floor.** `stats()` prints any object reaching below z = 0; wheels stand on it.
- **One job at a time.** Use `blender.sh` for every run, also quick ones.
