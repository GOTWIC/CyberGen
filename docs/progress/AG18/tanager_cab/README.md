# Tanager Cab

![sheet](sheet.jpg)

- **Brand, model, type:** Tanager Cab, driverless city taxi, a one-box people carrier (all names made up). 4 passenger seats in two pairs facing each other, no driver's seat: a sensor bar over the windshield drives it.
- **Size:** 4.55 m long over the bumper pads (4.50 m body), 1.85 m wide over the arch trims (1.99 m over the corner cameras, 2.15 m with the step out), 1.78 m to the roof, 1.95 m over the roof sign, wheelbase 3.0 m, wheels 0.66 m, ground clearance 0.225 m, cabin floor 0.30 m off the road.
- **Triangles:** 352,028 in 203 objects (body at subdivision 3; 285,996 before step B).
- **Build:** `vehicles/blender.sh vehicles/cars/tanager_cab.py --out docs/progress/AG18/tanager_cab --sheet` (`CAB_SHUT=1` keeps both doors shut in every view, `CAB_HULL=1` with `--preview` shows the bare hull; close-ups: `--views door,tail,nose,sign`).

## The design

- **One box, no hood.** The Mino's soft tall box grown to a people carrier and its hood taken away: a short brow over the visor, a windshield 31 degrees off upright, a flat cap roof, the Mino's leaning tail plane. Ten lines over fourteen stations, nothing sharp but the cladding's step.
- **The door.** One sliding door each side, 1.26 m wide, on a track let into the rear quarter under the windows. The left one is built open (its panels, glass, cladding, bump strip, checker and lettering are objects of their own, slid back 1.27 m and 9 cm out), over a fold-out step with a lit edge; the right one is shut (the small tile). Behind it a low flat ribbed floor, tread plate thresholds with yellow nosings, a yellow grab post each side of each doorway and a rail along the ceiling.
- **The cabin.** Two pairs of seats facing each other, the front pair riding backward, armrests, belts, a screen on each bulkhead, a luggage bay behind the rear seats under a hatch in the tail, a shelf with the computer's hump under the windshield.
- **Taxi gear.** A roof sign that is a hollow dot-matrix band all round on the roof rails (FREE to the front and back, CAB 31 to the sides), a destination strip under the windshield's header, the next stop on the rear visor's display, a payment pad on the pillar ahead of each door, the checker twice: molded into the cladding and as a band in the fleet's lettering color under the belt.
- **Driverless.** A gloss sensor bar over the windshield with a lidar puck on each end, lenses and a lit strip; a third puck at the back of the roof; cameras on stalks where mirrors would be; a radar plate in the bumper.
- **Family cues, all seven of the Mino's:** the visor with one light bar between two lamp rings and a display on the car's left, holes for windows with flat glass and fat seals, the cap roof with its gear on two rails, squircle arches, stepped grained cladding with a bump strip and rubber guards, steel wheels under slotted covers, the roundel (31), small print and the round T badge.
- **Show color:** hot magenta under a white cap roof.

## Step B: lamps, cut lines, glass (2026-11-13)

On step B's kit and `vehicles/brands/tanager.py` (rpoly, rect, rrect, skin, pad, bar_on,
tile, text_proj, GLYPH, banner, dots, dots_flat, Win, sheet, grain, door_obj, split_left,
plate, badge, arch_pts and the wheel; the Cab's own window cutter planes kept in a
subclass, `CabWin`, with the Mino's frit panes). The brand module is unchanged. The sheet,
clay, zebra and check above are of this build.

- **Visors** as the Mino's, at the Cab's size: each a hole across the nose and the tail face
  (the paint's 14 mm rim its walls, a gloss black back plate 14 mm in) with a gloss black
  surround 9.5 mm proud and a clear lens in it; at each end a lamp larger than the Mino's (a
  chrome plate, a lit ring of light guide in a frosted sleeve, red behind, and three LED cups
  on a dark tray), the light bar a guide on a chrome strip, the display (charge in front, the
  next stop behind) a screen with its dots under a smoked lens of its own. Lit faces 2 to
  4 mm proud of the skin, no small rings (the Mino's lesson for LOD3). The nose and tail
  faces flat shaded in their plane and the folded slivers taken out (`flatten`, `unfold`).
- **Other lamps:** the fog and reverse lamps LED cups under blocks of clear lens on dark
  housings on the bumper pads; the high stop lamp a lit bar on a chrome strip under a red
  lens; the side repeaters ahead of the front arches amber cells in holes under flush amber
  lenses; the rear corner markers amber bars under lenses on dark plates (on the skin: the
  tail's corner rolls away there).
- **Cut lines:** 3.5 mm shut lines (the body's gap 1.75 mm; the far LODs did not tear); the
  charge door cut through the left fender (a drawn outline before); the luggage hatch's top
  and foot cut across the tail face, its sides the face's own shut lines at its edges (a line
  cut beside them on the rounded edge left stars in the paint); a cup cut 14 mm into each
  sliding door under its upright pull (it slides with the door) and one under the hatch's
  pull, each pull's ends on the skin past its cup.
- **Glass:** every pane has a frit border (40 mm, 50 mm on the windshield and the rear
  window), the glass's own thickness, inside the fat seal. The destination strip behind the
  windshield moved 60 mm down, clear of the frit.
- **The open door** is now a pose: the car stands with both doors shut (the checks and the
  game pack see it so, as `CAB_SHUT` did), and the left door, its panels split off the body,
  slides open on a `K.Group` in the hero, side, top, door and low views. A fold-out step under
  each door, stowed under the sill; the left one comes out with its door. The right door's
  inner card is its own object, the mirror of the left's.
- **Street distances:** the wells' inner walls moved in from 0.60 to 0.48 m inside the skin
  and the cabin tub's floor and low bulkheads over the arches drawn in to them: 0.0 mm to the
  rear bumper guards and no steering before, 60 mm to the wells and 35 degrees each way now
  (the guards' corner had reached the front wells through a ray that slipped past the tail's
  edge; the script's `skin()` looks beside such a far hit, as the Mino's). The tires stood
  7 mm in the ground (the kit's road tread on a 0.205 m tire): the brand's `NARROW` tread.
- **Checks:** every check `ok` (tires, panels FAIL and symmetry, through `look` before); the
  one-sided parts (charge door, displays, permit, tow eye, radar, wipers, antenna, screens)
  told as meant. 352,028 triangles (285,996).
- **Game pack** (rebuilt locally, not published): every check passing; 149,242, 59,995,
  20,038 and 4,756 triangles (144,473, 59,991, 20,411, 4,982 before), standard class,
  texels 383 px/m (5th percentile); LOD3 17.3 of 40 degrees, 0.033 of 0.10 bent, 0.032 of
  0.04 texture (main 16.5, 0.030, 0.017). The visors' lamps, bars and displays bake lit and
  stay lit at LOD3, whose nose corner no longer crumples as main's did; the pack is the car
  shut, its step stowed. Left: at LOD3 the windows' frit and seal rims read a little ragged
  (the texture share up from 0.017), and a dark patch on the cladding behind the front arch
  is as on main.

## What I would improve

- The seats are plain blocks: shaped bolsters, stitched panels and seat bases with legs would lift the open doorway, which is the picture's centre.
- The doorway's edges are the panels' own thin rims: real jambs with seals, a striker and the upper and lower tracks would make the open door read as engineered.
- The luggage hatch has no side shut lines of its own (the tail face's edges serve); a hull with a finer cage at the tail's corners would let them be cut.
- The front end is calm to the point of plain between the visor and the bumper; a service flap with a shut line and washer jets would help.
- The side tile shows the far door's card through the doorway rather than the seats; a three-quarter tile from the door's side (view `door`) would show the cabin better than the pure side.
- The white roof wraps down the tail's top corners as on the Mino; on this taller tail it reads as two ears from straight behind.

## Kit wishes

- **Where a panel edge ends up.** A station's edge is drawn toward its neighbors by subdivision ((previous + 4 x + next) / 6 along an uncreased line): the door's edges, set at 0.64 and -0.62 in the cage, were built at 0.57 and -0.56 and the door's own parts stood proud of it. `build_body` could take stations by where their edges should be built, or the README could give the rule.
- **Opening parts.** A way to ask `build_body` for one side's panel as its own object (here `split_left` cuts a mirrored panel in two after the build), and a group to hang parts on so a door, hatch or hood can be moved or swung as one.
- **Family helpers in the kit or a brand module:** `Win`, `pad`, `bar_on`, `dots`, `banner` with its 5 x 7 glyphs, `text_proj`, `grain` and the slotted wheel cover are now copied in two Tanager scripts and will be in a third (a `vehicles/tanager.py` would do).
- **A cabin light.** A palette key for a dome light: here three area lamps are added to the studio collection so the cabin reads through the glass and the doorway.
- **Lit lettering on planes** (`dots_flat` here): a dot-matrix text on any plane, for signs and screens.
