# Tanager Cab

![sheet](sheet.jpg)

- **Brand, model, type:** Tanager Cab, driverless city taxi, a one-box people carrier (all names made up). 4 passenger seats in two pairs facing each other, no driver's seat: a sensor bar over the windshield drives it.
- **Size:** 4.55 m long over the bumper pads (4.50 m body), 1.85 m wide over the arch trims (1.99 m over the corner cameras, 2.15 m with the step out), 1.78 m to the roof, 1.95 m over the roof sign, wheelbase 3.0 m, wheels 0.66 m, ground clearance 0.225 m, cabin floor 0.30 m off the road.
- **Triangles:** 347,270 in 227 objects (body at subdivision 3; 283,699 before the full cabin).
- **Build:** `vehicles/blender.sh vehicles/cars/tanager_cab.py --out docs/progress/AG18/tanager_cab --sheet` (`CAB_SHUT=1` builds it with both doors closed, `CAB_HULL=1` with `--preview` shows the bare hull; close-ups: `--views door,tail,nose,sign`).

## The design

- **One box, no hood.** The Mino's soft tall box grown to a people carrier and its hood taken away: a short brow over the visor, a windshield 31 degrees off upright, a flat cap roof, the Mino's leaning tail plane. Ten lines over fourteen stations, nothing sharp but the cladding's step.
- **The door.** One sliding door each side, 1.26 m wide, on a track let into the rear quarter under the windows. The left one is built open (its panels, glass, cladding, bump strip, checker and lettering are objects of their own, slid back 1.27 m and 9 cm out), over a fold-out step with a lit edge; the right one is shut (the small tile). Behind it a low flat ribbed floor, tread plate thresholds with yellow nosings, a yellow grab post each side of each doorway and a rail along the ceiling.
- **The cabin.** Two pairs of seats facing each other, the front pair riding backward, a tower with a screen between each pair, a luggage bay behind the rear seats under a hatch in the tail, a low dash under the windshield (see Cabin below).
- **Taxi gear.** A roof sign that is a hollow dot-matrix band all round on the roof rails (FREE to the front and back, CAB 31 to the sides), a destination strip under the windshield's header, the next stop on the rear visor's display, a payment pad on the pillar ahead of each door, the checker twice: molded into the cladding and as a band in the fleet's lettering color under the belt.
- **Driverless.** A gloss sensor bar over the windshield with a lidar puck on each end, lenses and a lit strip; a third puck at the back of the roof; cameras on stalks where mirrors would be; a radar plate in the bumper.
- **Family cues, all seven of the Mino's:** the visor with one light bar between two lamp rings and a display on the car's left, holes for windows with flat glass and fat seals, the cap roof with its gear on two rails, squircle arches, stepped grained cladding with a bump strip and rubber guards, steel wheels under slotted covers, the roundel (31), small print and the round T badge.
- **Show color:** hot magenta under a white cap roof.

## Cabin

![cabin](cabin.jpg)

The full interior from `vehicles/cabin.py` (`style="tanager"`), in place of the box seats and bulkheads: `cab_fwd` (from the rear left seat, looking at the pair across), `cab_side`, `cab_back` (from the front left seat, looking back over the rear pair) and `cab_in` (through the open doorway) above, 96 samples.

- **What a robotaxi's cabin is here.** A riders' lounge: two pairs of comfort seats facing each other across a flat floor (the front pair rides backward), seat belts on the seats' own shoulders, no wheel, no pedals and no service wheel (nobody drives it, and a fold-away wheel would say otherwise). Between each pair a tower: an armrest with a red help button and a tap pad for paying, rising between the backs to a portrait screen with the route for the pair across, CAB 31 lit over it. A low dash under the windshield with the route on a wide screen (seen from the rear pair and through the windshield), a cover over the bay behind the front seats, a luggage cover behind the rear seats, a surround round the rear window, door and quarter cards with a soft rail, light panels and a rail along the ceiling, yellow grab posts at both doorways, a ribbed mat. Warm beige seats with magenta piping, the paint's magenta as the dash's inlay, pink ambient strips. The destination strip, thresholds, step and welcome strip are as they were.
- **The sliding door.** The lining and the card are built with the door shut; the left door's part of the lining (cut on the door's edges) and its card go with the door when it slides, so the doorway is open and the door's inside is lined; jambs carry the lining's cut edges out to the skin. With `CAB_SHUT=1` (the game pack) everything stays where it was built.
- **The lining's ends.** The spine runs to 15 cm from each end (`cap=0.15`; the module's 0.45 m left the windows' edges ragged in the poles' fans, 4 cm left the lining 5 cm through the cowl at the windshield's lower corners), the grid is 35 mm (`cab.step`), the car's `zone()` keeps the headliner over the trim 0.9 m up (behind the cards) and the cowl dark, and the faces behind the wheel wells are carpet.
- **Triangles.** Cabin 6,810 before, 70,381 now (lining 24,804, four seats 7,588 each); the whole car 283,699 before, 347,270 now.
- **Check.** `--check` says `fail`, all of it from before the cabin: the tires (a pose of the rear bumper's guards, 0 to 1.4 mm, steering 0 degrees) and the panels' open edges round the open doorway (the doorway itself; the jambs now stand beside most of it). Symmetry `look` (the open door's parts, as before; the cabin's one-sided parts told as meant), through `ok` (the slid door's lining and card and the jambs told as meant), ground and triangles `ok`. The log's "through the shell" names 48 lining faces at the windshield's header (12 mm, under the glass's seal, unseen from outside in the sheet's views), the well covers' lips (the module's known case) and one jamb face (5 mm).
- **Exterior.** Signed before and after: only `interior.*` objects, cabin materials and the studio's `cab*` lamps differ.
- **Weakest from a seat.** The towers are plain prisms; the seats' belts come off their own shoulders, which reads well only on the rear-facing pair; the lining shows small steps round the side windows' rear corners.

## What I would improve

- The doorway's edges are the panels' own thin rims: real jambs with seals, a striker and the upper and lower tracks would make the open door read as engineered.
- The front end is calm to the point of plain between the visor and the bumper; a service flap with a shut line and washer jets would help.
- The side tile shows the far door's card through the doorway rather than the seats; a three-quarter tile from the door's side (view `door`) would show the cabin better than the pure side.
- The white roof wraps down the tail's top corners as on the Mino; on this taller tail it reads as two ears from straight behind.

## Kit wishes

- **Where a panel edge ends up.** A station's edge is drawn toward its neighbors by subdivision ((previous + 4 x + next) / 6 along an uncreased line): the door's edges, set at 0.64 and -0.62 in the cage, were built at 0.57 and -0.56 and the door's own parts stood proud of it. `build_body` could take stations by where their edges should be built, or the README could give the rule.
- **Opening parts.** A way to ask `build_body` for one side's panel as its own object (here `split_left` cuts a mirrored panel in two after the build), and a group to hang parts on so a door, hatch or hood can be moved or swung as one.
- **Family helpers in the kit or a brand module:** `Win`, `pad`, `bar_on`, `dots`, `banner` with its 5 x 7 glyphs, `text_proj`, `grain` and the slotted wheel cover are now copied in two Tanager scripts and will be in a third (a `vehicles/tanager.py` would do).
- **A cabin light.** A palette key for a dome light: here three area lamps are added to the studio collection so the cabin reads through the glass and the doorway.
- **Lit lettering on planes** (`dots_flat` here): a dot-matrix text on any plane, for signs and screens.
