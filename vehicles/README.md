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
| `--clay` | `clay.jpg`: the preview's four views with every part in one matte clay, about 10 s |
| `--zebra` | `zebra.jpg`: the same views mirroring zebra stripes, about 6 s |
| `--turntable [N]` | `turntable.jpg` and `.gif`: N views round the car (12) at one distance; with `--clay` or `--zebra`, in that look (`turntable_clay.jpg`) |
| `--check` | the kit's checks: a table in the log and `check.json` |

`BLENDER=/path/to/blender` picks another Blender. `--sheet` and `--preview` put their tiles
together with `post.py`, run by the repo's `.venv` Python (`CYBERGEN_PYTHON` overrides).

## Judging the form: clay, zebra, turntable

Paint, glass and lights flatter a car. Before the details, and again before the sheet, look
at it without them:

```
vehicles/blender.sh vehicles/cars/NAME.py --out DIR --clay --zebra      # clay.jpg, zebra.jpg
vehicles/blender.sh vehicles/cars/NAME.py --out DIR --clay --turntable  # turntable_clay.jpg, .gif
```

- **Clay** puts every part in one matte clay under the studio's lights: proportions, stance
  and the fall of light on the volumes, with nothing to hide a dent or a flat spot.
- **Zebra** makes every point black or white by where its mirror image of the view comes
  from, as if the car stood in a tunnel of light tubes along its length (across it for the
  front and back views). Read the stripes: they flow evenly over a fair surface, bend
  sharply and stay joined at a crease, and wobble, pinch, fork or break where the cage is too
  coarse, where a soft crease dies badly or where two panels do not meet in one surface. Add
  a station where they wobble; a kink across a panel gap means the panels' edges differ.
- **Turntable**: the car from all round at one scale, twelve frames in one image (and a
  small looping `.gif`). A silhouette that only works from the hero's side shows here.
- With a look, `--views a,b` renders `car_<view>_clay.jpg` (or `_zebra`) instead of the
  painted frames.

## Checks

```
vehicles/blender.sh vehicles/cars/NAME.py --out DIR --check      # 2 s: a table, DIR/check.json
python vehicles/survey.py [--docs]                               # every car: checks, clay, zebra
```

`--check` (or `K.check()`) measures the car as built (`carcheck.py`); nothing is changed.
Each check says `ok`, `look` (worth a look at the place it names; often meant) or `fail`.

| Check | What it measures | Says |
|---|---|---|
| `tires` | each tire's nearest point of anything that is not its own wheel; the front pair turned about its upright axis in 5 degree steps until it touches; each tire's foot on the ground | `fail` under 4 mm (the tire is in the body), `look` under 25 mm or when the front wheels turn less than 20 degrees |
| `ground` | the lowest point of everything that is not a wheel | `fail` under the floor, `look` under 90 mm on a wheeled car; a hover car is told as standing or floating |
| `symmetry` | every object's mirror image in y = 0 against the car | `look` for each object more than 3 mm off (lettering, a steering wheel and one-sided parts are meant; a stray part or a kit fault is not) |
| `panels` | the edges of the body's panels: an edge with nothing beside it is open; a hole a cutter leaves inside one panel | `fail` for open edges on a closed hull (a tear, or an open doorway), `look` for cutter holes (a lid cut on purpose, or a wheel well breaking through a low hood) |
| `through` | cabin parts (seat, interior and screen materials, `interior.*`): points of them that see the open air in a quarter of all directions with the skin, the glass and the wheels in the way | `look`: a tub in a wheel well or under the floor, a liner through a brow, a seat by an open doorway |
| `triangles` | the car against 400,000 triangles, and where they are | `look` over the budget |

`K.meant("panels", "body.roof", "body.clad")` in a car's script says a finding is meant (a
taxi's open doorway; names may end in `*`; `"tires"` takes wheel tags, the others object
names): it is still listed, marked, and no longer counts. `survey.py` runs the checks and
the clay and zebra renders on every car and, with `--docs`, writes each car's `check.json`,
`clay.jpg` and `zebra.jpg` and the table `docs/progress/AG18/checks.md`.

**Changing the kit.** `python vehicles/survey.py --sign DIR` writes a fingerprint of every
car as built (`signature.py`: geometry, materials, studio, cameras); sign before and after
a change to `carkit.py` and `--compare A B` says which cars it moved. The same fingerprints
mean the same sheets and the same game packs.

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
- **Parked and shut.** A pack is built with `CYBERGEN_SHUT=1` set: a script that poses an
  opening part for its sheet builds it closed then (`K.Group` poses are per view and never
  reach a pack).
- **Baked down.** Lettering, ribbons and other flat relief go onto the surface under them;
  dense arrays (honeycombs) become cards; dense tires become lathes with the tread and
  sidewall marks baked on; over budget, taller relief such as bolt rows, then a collapse of
  every part alike (never glass, lamps or wheels). Under budget, fine relief (flutes, slots,
  small lettering no atlas draws as lines) also stays as geometry at LOD0. Faces nothing can
  see are removed; a
  face seen better from behind is turned round. Islands under baked lettering get more
  texels, thin islands at least two texels across.
- **LODs.** Small parts and the cabin left out first, flat faces merged, then a collapse
  with a floor per panel and lamp; every LOD takes its UVs and shading normals from LOD0,
  island by island, so it shades as LOD0 does and no texture tears. The far LOD (LOD3)
  also leaves out what the opaque glass hides, welds panels that meet, drops parts that
  would float, turns parts the collapse wrecks into their convex hulls, and makes each
  wheel anew: a round tire and a disc wearing the rim face baked for it from the side. Each
  LOD is measured against LOD0 (normals, textures) and fails when crumpled. `--keep-work`
  then `--lods-only` remakes only the LODs in seconds.
- **Size class.** Large vehicles (55 m2 of body exterior or more: trucks, vans) get an
  8,000 triangle LOD3 (5,000 otherwise) and a lower texel floor.
- **Shared wheels.** A wheel that is another one moved or mirrored shares its texels
  (never mirrored when lettering is baked onto it).
- **Proof.** `game.jpg`: the pack alone in the studio as the car's script set it up next to the procedural original
  from the hero view, a recolored copy, the textures and the four LODs. `--views a,b`
  compares more of the car's views (`proof/original_<view>.jpg` and `baked_<view>.jpg`);
  look at them at full size.
- **Checks.** Budgets, UV overlap, texel density, files, wheel pivots, LOD bounds, LOD
  fidelity, hull count (`game_report.json`); the run fails when one fails.
- **Time.** About 8 to 14 minutes a car at full size, up to 27 for the largest (most of it
  the bakes, the LOD fits and the proof); `--lods` alone 1 to 4 minutes. Packs are 20 to
  51 MB and never go in git.
- **On another machine.** The built packs are a GitHub release of this repo:
  `python vehicles/packs.py fetch` downloads the 15 (about 550 MB) into the packs' cache and
  checks every file against `vehicles/packs.json`; `publish` uploads new ones (`GAME.md`,
  "Sharing packs between machines").
- **Out of the cities until redesigned.** The three Vex cars (no packs) and the three Aurels
  (Swagnik, 2026-11-12: "they look terrible"; their packs were built, but are no longer
  shared). Their scripts stay in `cars/` and they stay in the line-up; nothing places or
  imports them: `assetgen/parked/table.EXCLUDED`, `citygen/unreal_vehicles.EXCLUDED`,
  `packs.py` and `survey.py`'s `EXCLUDED`. A car comes back by taking it out of those lists
  once it is redesigned and its pack rebuilt.

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
| `materials(**palette)` | the library in `K.MAT`. Palette keys: `paint`, `paint_finish` (`metallic`, `pearl`, `gloss`, `satin`, `matte`, `chrome`, `lacquer` (a thin coat: black stays black under the top box), `skin` (matte with little specular), or `(metallic, roughness, coat[, specular])`), `paint2`, `paint2_finish`, `dust`, `dust_amount`, `dust_z` (`(0.12, 0.55)`: the paint is all dust at the first height and below, clean from the second up; raise both for a truck or a hover car), `cladding`, `glass`, `glass_ior` (1.5; 1.1 to 1.2 is a coated glass that does not mirror the lights), `carbon_coat` (1; 0 is a dry weave), `led_front`, `led_rear`, `led_accent`, `led_wheel`, their strengths `led_front_strength` (60), `led_rear_strength` (40), `led_accent_strength` (30), `led_wheel_strength` (30), `screen_strength` (2), `lamp_strength` (25), `ember_strength` (1.6) (fine slots of light clip to white at the defaults, and the red goes pale: lower them), `caliper`, `seat`, `interior`, `screen`, `rim`, `rim_bright`, `decal`, `ember`, `floor` (the studio's floor; darker for very dark gloss paint). Names: `paint`, `paint2` (flake, dust, crease grime), `carbon` (weave), `gloss_black`, `cladding`, `underbody`, `void`, `well`, `grille`, `glass`, `rubber`, `rim`, `rim_bright`, `disc`, `caliper`, `interior`, `seat`, `screen`, `decal`, `led_*`, `lamp`, `ember` |
| `pbr(name, color, metallic, rough, **inputs)`, `emit(name, color, strength)`, `paint(name, color, finish, dust, dust_amount, flake, dust_z)`, `carbon(name, dark, light, coat)`, `glass(name, color, ior, rough)` (a smoked or coated glass of the car's own; name it `glass...`), `lens(name, color, ior, rough)` (a lamp's lens: a shadow passes through it tinted, so what is behind it is lit; name it `lens...`), `void(name)` | a car's own materials |
| `need(*names)` | the kit's later materials, made the first time a car names one (in `pmat`, in `Geo.obj` or here), so a car that uses none builds exactly as before: `lamp_housing` (dark plastic), `chrome`, `lens_clear`, `lens_smoke`, `lens_red`, `lens_amber`, `optic` (a frosted light guide sleeve), `frit` (the black border printed on glass), `mirror`, `seal` (rubber seals) |
| `Geo()` | collects closed solids: `box(center, size, rot)`, `hexa(8 points)`, `prism(polygon, vector)`, `prism_on(plane, polygon, at, depth)` (a polygon drawn in `'xy'`, `'xz'` or `'yz'`), `lathe(profile, n, a0, a1, xf, axis=, at=)` about y, or about any axis (`'x'`, `'z'`, a vector) through a point, `ring(center, axis, R, r=, sec=)` a round or flat ring about any axis, `cyl(base, h, r, axis=)` an upright cylinder, `sweep(path, section, up, closed)`, `pipe(path, r)` a round bar along a path, `tube(a, b, r, n)` a straight round bar between two points, `louvers(a, b, c, d, n, w, th, tilt, out)`, `honeycomb(polygon, x, R, wall, depth, sgn, keep, frame=)` (`frame=(origin, u, v)`: on any plane), `add(verts, faces)`; then `obj(name, mat, bevel, segs, angle, mirror, sharp, flip_y, loc, rot)` (`rot`: an Euler, three angles or a matrix, about the object's origin at `loc`) |
| `finish(ob, bevel, segs, angle, mirror, wn, sharp)` | mirror, bevel and shading on any mesh object |
| `fill(stations)`, `table(names, lines, S)` | `None` points interpolated; `PT[station][line]` |
| `build_body(stations, panel_of, pmat, line_crease, station_crease, name, front, rear, recesses, glass, cutters, subdiv, mirror, wrap, gap, thick, glass_thick, project, bevel, bevel_segs, lens_thick)` | one body piece (below); returns `.parts[panel]` objects and `.caps["front"/"rear"]` inner rings |
| `groove(g, pts, proj, width, depth, proud, closed, step, mirror, up=, round=)`, `pocket(g, pts, proj, depth, proud, dir, back, step, mirror)`, `trace(pts, proj, closed, step)`, `chaikin(pts, rounds, closed)`, `rounded(cx, cy, w, h, r)`, `ngon(cx, cy, r, n, rot)` | cutters laid on the uncut hull, inside a `cutters` function (below): a cut line (a shut line, a flush handle's outline; wider, a light channel), a pocket (a lamp housing, a handle recess, a slot) returning a `Pocket` (`on(a, b)`, `at(a, b)`, `deep(a, b)`: where the skin and the floor are); the path on the surface they follow, a polyline's corners cut round, outlines to draw them with |
| `Lamp(name, lit, housing, chrome, glass, optic)` | the inside of a lamp, by material: `projector(at, dir, r, depth)`, `reflector(at, dir, r, depth)`, `leds(a, b, n, dir)`, `guide(path, r, sleeve)`, `bar(path, w, h)`, `fins(a, b, c, d, n, w, th, tilt, out)`, the Geos `housing`, `chrome`, `glass`, `optic`, `emit(lit)`; `obj(mirror)` makes `<name>.housing`, `.chrome`, `.glass`, `.optic`, `.lit` |
| `wiper(arm, blade, pivot, a, b)` | a wiper at rest on the glass: a boss, a tapered arm, a yoke, the blade's spine and rubber from a to b |
| `well_cutter(g, cx, cz, r, y0, angles)` | a wheel well solid for `cutters` |
| `arch_trim(g, cx, cz, r, y_in, y_out, angles)`, `arch_bolts(g, cx, cz, r, y, angles)` | faceted arch trim and its bolts |
| `on_body(u, v, proj, objs, tol=)` | surface point and normal of the body as built, seen along `'y'` (left side, u = x, v = z), `'Y'` (right), `'x'` (front, u = y, v = z), `'X'` (back), `'z'` (top, u = x, v = y); over all body pieces, or over `objs` (an object or a list: pods, a wing, one panel), with nothing to set or reset. `tol=0.003`: a ray that slips through a panel gap looks again beside it |
| `snap(p, objs, out)` | the nearest point of the body as built to any 3D point, and its normal: for what no axis projection reaches (round a nose, over a shoulder, on a dome) |
| `strip(g, ctrl, w, lift, sink, taper, objs=)`, `spline(ctrl, n)` | a band on the surface along a smooth 3D curve through points near it, its ends drawn to points: light strips, trims, seams |
| `ribbon(g, pts, proj, w, objs=)`, `rib(g, pts, proj, w, h, objs=)`, `flutes(g, run, lo, hi, pitch, proj=)`, `bolt_row(g, pts, pitch, proj=, objs=)`, `stud(g, loc, n, profile, seg)` | on the surface along a path given in projection: a flat strip, a raised rib, a row of flutes (bars from one height to another, every pitch along a run), a row of bolt heads (also along 3D points), one stud |
| `plate(g, base, along, up, poly, th0, th1)`, `chine(x, objs)`, `walk(path, step, closed)` | a flat blade (a fin, a strake) in its own plane; the widest point of the body as built at x; points every step along an outline with tangent and outward normal (a row of anything round a plan) |
| `text_on_body(g, txt, size, x0, z0, side, proj=, turn=, objs=, font=, align=, tol=)`, `text_flat(g, txt, size, origin, right, up, font=, align=)`, `text_mesh(txt, size, spacing, font, align)` | lettering. `text_on_body` writes on the flank; with `proj='z'` on a roof, hood or deck, its middle at x = `x0`, y = `z0`, read from the left side (`side=1`) or the right (`-1`), turned by `turn` degrees (90: read from behind); with `proj='x'` on the nose and `'X'` on the tail (middle at y = `x0`, z = `z0`). `font`: `"din"` (the default), `"condensed"`, `"serif"`, `"mono"` (`K.FONT_SETS`) or a font file. Text is centered on its origin in both directions; `align="baseline"` puts the origin on the baseline. A word with a point off the surface is not laid, and the log says so |
| `built_at(xs, i)`, `solve_stations(xs, want)` | where subdivision builds a station's edge, and the stations moved so that chosen edges are built where they should be (below) |
| `body_bvh(objs, default)` | the projector's tree, returned; `body_bvh()` alone makes the body pieces the default target again |
| `band_point(p, center, w, out)`, `shr(quad, k, lift, out)`, `my(p)` | a point inside a cap's lip; a quad shrunk and lifted; a point mirrored |
| `build_wheel(tag, cx, R, w, Rr, out_y, side, cz, spokes, style, ring, caliper, rim, bright, tire, loc, rot, tread)` | a wheel: tire radius, width, rim radius, outer face y; `style` `twin`, `blade` or `disc`; `ring` and `caliper` are material names or `None`; `cz` lifts the axle. `tread`: `"road"`, `"all_terrain"` or `"lug"` (`K.TREADS`, or a dict of your own). `tire=None` leaves the tire out, `rim=None` the rim and its hub (`bright=None` the hub alone), for a car that brings its own; `rim` may be the car's own builder, `rim(tag, w, Rr, flip, loc, rot)`, making `rim.<tag>`; `loc` and `rot` put the wheel anywhere, turned: a spare |
| `VIEWS` | the views by name (`hero`, `rear`, `rear_l`, `side`, `front`, `back`, `top`, `under`, `low`): `dir`, `lens`, then `dist` or a fit (`fit` prefixes, `margin`), `focus`, `fstop`, and optionally `target`, `no_floor`, `center` and `ortho` (below). Change or add entries before `shoot()` |
| `shoot(sheet=(4 views), preview=(4 views), extra=None)` | the end of every script: stats, studio, renders, exports. `extra`: the sheet's small tiles, a view name, `dict(view=, size=(840, 400), corner="tl", margin=)`, or a list of them (each in its own corner) |
| `unlit(lights, *objs)`, `cabin_light(loc, power, size, color, target)`, `after_studio(fn)`, `LIGHTS` | the studio's hooks (below): a light kept off some objects, a dome light in the cabin, a function called once the studio stands; where every light stands |
| `on_view(fn)`, `Group(name, objs, pivot)` | a state of the car's own for some views: `fn(view, True)` before a view renders and `fn(view, False)` after; a group of parts that moves as one (a door, a hatch, a canopy): `pose(loc, rot)`, `rest()`, `pose_for(views, loc, rot)` |
| `check()`, `meant(check, *names)`, `wear(look)`, `render_turntable(n)` | the checks and the findings a car says are meant; the clay and zebra looks; the turntable |
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
  **`glass`** `(panel, inset[, trim])`: a trim frame with sharp corners. Two later forms,
  both made on the left half before the mirror, so the frame is the same on both sides and
  faces out (the first form's frames are mirrored 4 to 14 mm off at their corners and face
  into the car, step A's finding; the cars that use it keep it until they are redone):
  `(panel, inset, trim, "frame")` a trim frame with the body's gap round it, and
  `(panel, inset, trim, "frit")` the frame as part of the glass, no gap between them, the
  glass's thickness, for a trim panel in `frit`: the black border printed on real glass.
  A frit pane and its border are drawn sharp at their rims (smooth, the reflections at the
  pane's edge break into shards).
- **`cutters`** `(Geo, panel)`: solids cut out (wheel wells, a tunnel through the body).
  None for a hover car or an open-wheel car. `(Geo, panel, "drop")` drops the cut faces: a
  hole with no walls (a window, an open locker), or with `groove()` a shut line. A cutter
  that stands on one side only cuts that side (`well_cutter(..., sides=(1,))`).
  `(Geo, housing, "skin", P)` keeps the cut faces as `housing` and makes the skin the
  cutter took away a panel `P` of its own, with the gap all round: a lamp's lens over its
  housing (a `lens...` material makes it a thin lens, `lens_thick` 3 mm), a flap over its
  recess. `(Geo, P, "cover")` makes the skin `P` and drops the cut faces.
- **Cut lines and lamps** (step B). `cutters` may be a function: `build_body` calls it once
  the cage stands, uncut and subdivided, and `on_body()`, `snap()` and `trace()` then see
  that hull, so `groove()` and `pocket()` lay their cutters on the surface as it will be
  built; it returns the list. A shut line is `groove()` with its defaults (0.6 mm, 6 mm deep:
  with a gap of 1.75 mm it is 4 mm wide, the scope's 3 to 4 mm); a closed outline is a
  flush handle or a flap. A light channel is a groove 25 to 40 mm wide and deep, cut as
  `"skin"` with a lens: the lamp stands in it, built along the path the groove returns
  (`[(point, way out)]`) with a `Lamp`. A wide channel that turns a corner tighter than it
  is wide would fold: `round=3` rounds the path's corners first (the groove also drops
  sections that would fold, at a cost in symmetry). A rounded path is snapped onto the
  hull, so keep it away from a mouth's inner frame: the Vanta-R's front channel could not
  be rounded. The checks know these cuts (`Body.cuts`): their edges are not open edges.
- **Even bands.** A cap's band is drawn toward the cap's center, so it is narrow where the
  lip runs past the center; `even=True` makes it `band` wide all round, square to the lip:
  room for a lamp channel along it (`_even_band`). `caps[key + ".band"]` holds its pairs of
  points.
- **Bevels**: `bevel=None` gives paint panels 4.5 mm and the rest 3 mm; a number is for
  every panel, a dict `{panel: width}` for some (0 for none); `bevel_segs` (2) its segments.
- **More pieces**: call it again with another `name` (a cab and a bed, a canopy, pods).
  A piece whose first and last lines are not on y = 0 mirrors into a left and a right
  copy: with `wrap=True` (last line joined to the first) that is a pair of closed tubes,
  such as pontoon fenders or hover pods.
- **Where an edge is built.** Subdivision draws a station's edge toward its neighbors: along
  a line that is not creased there it is built at (previous + 4 x + next) / 6
  (`K.built_at`). A door whose shut lines must stand at 0.64 and -0.62 needs its stations
  elsewhere: `xs = K.solve_stations(xs, {2: 0.64, 3: -0.62})` moves them. The same pull makes
  an uncreased line between unevenly spaced neighbors drift toward the far one, and an
  uncreased flat cap shrink a great deal (its one face pulls the ring inward): crease the
  ring, or give the cap an inner ring station.
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
  views of upright glass). Where each light stands (`K.LIGHTS`):

  | Light | Stands at | Aims at | Size | Note |
  |---|---|---|---|---|
  | `top` | (0.2, 0, 5.5) | the middle of the floor | 7.5 m across the car (y) by 2.8 m along it | the soft box glass mirrors when it leans in more than about 25 degrees or looks at the sky |
  | `key` | (5.0, 5.5, 3.2) | (0.5, 0, 0.5) | 4.0 by 2.5 m | front left, warm |
  | `rim` | (-6.0, -5.0, 5.0) | (0, 0, 0.6) | 5.0 by 1.2 m | rear right, cool |
  | `fill` | (5.5, -4.5, 1.6) | (0.5, 0, 0.5) | 3.0 by 2.0 m | front right, low |
  | `strip`, `strip2` | (0, 6.5, 1.3), (0, -6.5, 1.3) | (0, 0, 0.6) | 9.0 by 0.45 m | along each flank |

- **Light hooks.** `K.unlit("top", "body.canopy")` keeps a light off some objects (light
  linking; names may end in `*`): the top box is no longer mirrored whole in a raked
  windshield, and the paint still takes it. `K.cabin_light((x, y, z))` hangs a soft lamp in
  the cabin, so a tall glass car shows its seats in side views (it belongs to the studio,
  not to the car). `K.after_studio(fn)` runs a car's own change once the studio stands. A
  coated glass (`glass_ior=1.15`) is the other cure for white windows. All before `shoot()`.
- **Centered and orthographic views.** `K.VIEWS["hero"]["center"] = True` moves a fitted
  view's target until the silhouette sits in the middle of its frame (a tall car's hero
  otherwise sits to one side). `K.VIEWS["side"]["ortho"] = True` draws a view without
  perspective, whatever the studio's depth: a 6.6 m truck's side at the scale of a coupe's.
- **States for some views.** `K.Group("door", parts, pivot)` hangs parts on one pivot;
  `door.pose_for(("hero", "side"), loc=(-0.9, 0.06, 0))` slides it open in those views and
  leaves it shut in the others (and in the game pack). `K.on_view(fn)` is the bare hook.
- **`under`** looks up from below with the studio hidden (`no_floor=True`): the under-floor
  view of a hover car, lit by its own emitters and the grey world.
- **The small tiles.** `K.shoot(extra="top")` (or `--extra top`) lays one more small view
  into a corner of the hero, over it: the hero keeps its size. Top left by default, the
  empty wall over the nose; `extra=dict(view="under", corner="br", size=(840, 400))` picks
  another corner or size, and a list lays several (`extra=["top", dict(view="open",
  corner="tr")]`). Check on the sheet that the corners are free of the car.

## Brand modules

`vehicles/brands/<brand>.py` holds the helpers a brand's three scripts each carried a copy
of (`from brands import brakk`): the Brakk plates, pylons, stencils and wheel; the Aurel
slabs, lozenge, blades, crest, wheel and studio; the Halcyon cap light band; the Kestrel
pods, fins and chine; the Orrin lids, strips, pebbles, dot fields and turbine disc; the
Tanager windows, pads, dot-matrix banners, door and wheel. A helper that read a car's own
globals takes them as keyword arguments, bound once with `functools.partial`. Each module's
docstring says what was lifted, how the copies differed and what the kit itself now covers.
The 18 cars still carry their own copies: a car switches to its module in the step that
next edits it (each was converted in a scratch copy and built the same, by `signature.py`).
A new car of a brand starts from the module.

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
- **Lights under the skin.** Panels have no thickness behind their rim: a light strip sunk
  under the skin shines into the shell. Keep emitters a hair over it (`K.strip`'s default).
- **Look without the paint.** `--clay` and `--zebra` before the details and before the
  sheet, `--check` before you call it done.
- **Dust.** A tall or floating vehicle wants its dust line higher: `dust_z` in the palette.
- **Lettering** uses the DIN font on macOS (`carkit.FONTS`).
- **Names.** Every maker, model and word on a car is made up. Never name a real maker, a
  real model or any game, in text on the car, in file names or in comments.
- **Panel names** are yours, but every one must be in `pmat`, including the defaults a
  feature uses (`vent` for recesses, `trim` for glass) and the cutters' panels.
- **Under the floor.** `stats()` prints any object reaching below z = 0; wheels stand on it.
- **One job at a time.** Use `blender.sh` for every run, also quick ones.
