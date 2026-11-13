# Tanager Mino

![sheet](sheet.jpg)

- **Brand, model, type:** Tanager Mino, city car, 4 seats (all names made up). The first Tanager: it sets the family's cues.
- **Size:** 3.43 m long, 1.57 m wide over the arch trims (1.87 m over the mirrors), 1.55 m to the roof, 1.61 m over the rack and 1.64 m over the sensor puck, wheelbase 2.45 m, wheels 0.56 m, ground clearance 0.20 m.
- **Triangles:** 276,187 in 141 objects (body at subdivision 3; 223,689 in 110 before step B).
- **Build:** `vehicles/blender.sh vehicles/cars/tanager_mino.py --out docs/progress/AG18/tanager_mino --sheet` (`MINO_HULL=1` with `--preview` shows the bare hull).

## The design

- A soft tall box: ten lines over sixteen stations, nothing sharp but the cladding's step. A short sloping hood, a windshield 27 degrees off upright, a flat roof, a tail that is one plane leaning six degrees; the wheels fill the corners.
- Flat glass all round in eight rounded openings, a cabin you can read through them: four oat seats, a dash with two screens, a wheel, a parking permit behind the windshield.
- A share car in service: fleet roundel 07 on the doors and the roof, zone and unit lettering, tire pressures over the arches, jack point arrows, a charge door with a lit bolt, a tow eye, one big wiper.
- Show color: scarlet coral under a white cap roof, white wheel covers, charcoal plastic.

## Step B: lamps, cut lines, glass (2026-11-12)

The Tanager pilot on step B's kit (`docs/assetgen_milestones.md`, AG18, step B), and the
first car on `vehicles/brands/tanager.py` (rpoly, rect, rrect, skin, pad, bar_on, text_proj,
GLYPH, banner, dots, Win, sheet, grain, plate, badge, arch_pts and the wheel; the Mino's own
window cutter planes kept in a subclass, `MinoWin`). The sheet, clay, zebra and check above
are of this build.

- **Visors:** each is now a hole across the nose and the tail face (the paint's own 14 mm
  rim its walls, a gloss black back plate closing it 14 mm in) with a gloss black surround
  standing 9.5 mm proud round its edge (about the old visor pad's 4 mm and its lamps' 9.5 mm)
  and a clear lens in it, all laid on the skin as it stood uncut (the body's own skin cut
  out as the lens kept the boolean's slivers on the face's rounded ends and its reflections
  zigzagged). In it, at each end a lamp of a chrome plate, a lit ring of light guide in a
  frosted sleeve (red in the tail) and a row of three LED cups on a dark tray; between them
  the light bar, a guide in its sleeve on a chrome strip; the display on the car's left a
  dark screen with its lit dots under a smoked lens of its own. The lit faces stand 2 to
  4 mm proud of the skin under the lens: in the game pack's LOD3 the nose's flat face is
  drawn across the hole, and a first build with them deeper (a pocket's cup) lost them
  there under a dark lid. Nothing in the lamps is a small ring (a bezel), which LOD3 fills
  into a lid.
- **Other lamps:** the fog and reverse lamps a dark housing plate on the bumper pads, a
  chrome back, two or three LED cups and a block of clear lens; the high stop lamp over the
  rear window a lit bar on a chrome strip in a block of red lens (a pocket there, where the
  tail rolls into the roof, left stars in the paint); the side repeaters on the front
  fenders amber cells in holes under flush amber lenses.
- **Cut lines:** the charge door cut through the fender (it was a drawn outline), the door
  pulls in cups cut 14 mm into the doors with the pulls' ends on the skin past them, 3.5 mm
  shut lines (2.4 mm before). Washer jets in front of the windshield. The hood's service flap
  was cut and taken out again: on the hood's gentle curve its outline left stars in the
  paint's shading.
- **Shading of the cut faces:** the nose and tail faces are flat; a cut through them left
  long thin triangles from the cut to the face's corners, and smooth shading carried the cut's
  rim normals along them in stars. The faces lying in the face's plane are flat shaded now,
  and the few faces the cut folded back over their neighbors are taken out (`flatten`,
  `unfold` in the script).
- **Glass:** every pane has a frit border (40 mm from its edge, 50 mm on the windshield and
  the rear window), the glass's own thickness, inside the fat seal.
- **Street distances:** the wells' inner walls moved in from 0.50 to 0.45 m inside the skin
  (the silhouette is the same) and the cabin tub shaped round the wells (floor, dash, boot
  wall and door cards only in the middle over them): 0.0 mm to the tub and no steering
  before, 51.9 mm to the cladding and 35 degrees each way now. The tires stood 7 mm in the
  ground: the kit's road tread on a 0.165 m tire put its grooves outside the crown, the
  profile folded and the blocks stood out of the tire; the brand's `NARROW` tread has its
  grooves on the crown (the Cab and the Porter have the same fault and keep their tread
  until they are redone). A ray of a bumper pad slipping through the wider shut line at the
  tail's edge put a corner of the rear bumper inside the car; the script's `skin()` now looks
  beside such a hit too.
- **Checks:** tires `ok` (FAIL before), panels, ground, through and triangles `ok`, symmetry
  `look` as before: the one-sided parts (driver's wheel and screens, wipers, antenna, tow
  eye, permit, displays, charge door) are told as meant, and `body.screen`, 3.8 mm off at
  the windshield's top corner (the boolean's triangles at the window's hole), is left.
- **Game pack** (rebuilt locally, not published): every check passing; 143,087, 59,994,
  20,076 and 5,361 triangles, standard class, texels 489 px/m (5th percentile). The lamps,
  bar and displays bake lit, and LOD3 keeps the visors' lamp rings and bars lit and the
  glass dark gray.

## Tanager's signature cues (for the Cab and the Porter to repeat)

1. **The visor.** A gloss black rounded band across each end (since step B a pocket under one flush clear lens, the lamps inside it). In it one unbroken light bar between two rounded-rectangle lamp rings with a small lit core (the eyes), and under the bar on the car's left a dot-matrix display (5 x 7 glyphs: charge in front, hire state behind). White in front, red behind, same layout.
2. **Holes for windows.** Every window is a rounded-rectangle hole in the skin with flat glass set behind it and a fat black seal round it; pillars stay body color. Leading and trailing edges lean with the windshield and the tail.
3. **Cap roof.** The roof is a separate color down to the glass header and carries the job's gear on the same two rails: here cross bars and a sensor puck with a lit band.
4. **Squircle arches.** Wheel openings are flattened superellipses with a broad plain trim in the cladding's plastic. No bolts, no flares.
5. **Stepped cladding.** Grained plastic below a step that stands 13 mm out of the paint, one bump strip with two rubber lines along the doors, bumper pads with rubber corner guards on body-color faces.
6. **Steel wheels, slotted covers.** A flat cover with six rounded-rectangle slots, one groove and a cap in body color.
7. **Roundel and small print.** Fleet number in a round field on the front door and large on the roof, the model name in capitals, one line of service lettering, a round T badge on the hood's lip and the tailgate.

## What I would improve

- The hood is plain (a service flap's cut left stars in its shading; it wants a finer hull there). The mirrors are simple blocks.
- Side glass reads dark in the pure side view; a lighter headliner or more cabin light would show the seats there too.
- The bumper pads end in a small step where they meet the corner cladding; they deserve wrapped corners of their own.
- No belts, no pedals; the wheel wells are plain cavities.

## Kit wishes

- Windows as holes: `build_body` could take cutters whose cut faces are dropped (here the `wincut` panel is deleted after the build), and the kit could carry this car's `Win` (cutter, flat pane and seal on the skin as built).
- `pad()`, `bar_on()` and `dots()` (a plate, a bar and a dot matrix lying on the skin) and a `text_on_body` for the nose and tail (`proj='x'`, `'X'`) are general.
- `on_body` rays slip through panel gaps now and then (`skin()` here looks beside a miss); a tolerance in the kit would spare every car that.
- Flat end caps: a note in the README that an uncreased cap shrinks a great deal (its one face pulls the ring inward) and that an inner ring station keeps the face full size; and that an uncreased line between unevenly spaced neighbors drifts toward the far one (the cladding's edge rose 10 cm across the tail until it was creased).
- A palette key for the cabin light, or a kit dome light, so tall glass cars show their cabins in side views.
