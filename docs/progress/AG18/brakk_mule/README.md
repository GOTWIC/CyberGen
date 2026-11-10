# Brakk Mule

![sheet](sheet.jpg)

- **Brand, model, type:** Brakk Industrial Mule, six-wheeled cargo van (all names made up).
- **Seats:** 2 (two buckets in a cab-over cab), plus a cargo box of 4.1 x 2.1 x 1.16 m inside.
- **Size:** 6.65 m long from the tow pin to the tail step, 2.30 m wide over the tires (2.35 m over the fender plates' folded edges), 2.24 m at the cab roof, 2.50 m at the box roof, 2.68 m over the cooling unit's fans, 2.76 m with the whip; three axles, 4.11 m from the front axle to the bogie's pivot, the rear pair 1.24 m apart; tires 0.95 m in diameter, 0.34 m wide; hull floor at 0.58 m, frame at 0.81 m.
- **Triangles:** 364,552 in 183 objects.
- **Build:** `vehicles/blender.sh vehicles/cars/brakk_mule.py --out docs/progress/AG18/brakk_mule --sheet`

## The design

- A narrow wedge cab that stands between its front wheels (1.6 m wide, the box behind it 2.2 m): the slab face, a 45 degree cowl, a one-piece windshield raked 27 degrees with two swept corner facets, a triangular quarter window, a roof that rises toward the box. The door is over the wheel; the bumper's rising end and the fender plate with its tread ribs are the steps up to it.
- A bellows collar on a turntable joins the cab to the box, with hoses and high voltage cables looping across the gap, so the two read as separate bodies.
- The box is a container on a frame: corrugated walls between bolted rails, corner castings with their oval holes, posts chamfered in plan, barn doors with four lock rods, cams, catches and hinges, and bolted number plates over the ribs (`63`, `MULE 63`, a hazard placard, stripes).
- The roller door on the left is shown two thirds open over a lit hold: lashing rails, strapped crates, a hazard case, drums. A ladder hangs under it.
- Hub motors at all six wheels, as on the Bastion: wishbones in front, and the rear pair on a signal orange walking beam that pivots on a trunnion between the tires. Battery cases with ribbed faces, air tanks and under-run bars fill the space between the axles.
- A sensor band in place of mirrors: camera pods on struts, a dark rear pillar with lit cells and a lens, a row of cells under the roof bar. A cooling unit hangs over the collar with louvres in front and two fans on top; two hatches and lashing rails on the roof.
- The family, kept: plates with one 45 degree chamfer, bolted three-facet fender plates, light pylons on the chamfered corners (white on the face, tall red ones on the tail posts, tall amber markers on the box beside the cab), the blade across the face, the eight-cell bar over the windshield, the ribbed slab with its badge plate, rows of bolt heads, stencils, hazard stripes, the Brakk wheel.
- Show color: olive drab, with graphite plates, white stencils and signal orange for the beam, springs, cables and hazard marks.

## What I would improve

- The walking beam shows only between the tires and from behind; a cutaway fender or a higher view of the bogie would explain it better.
- The windshield is dark from the front; a brighter cabin (lit dash, door cards, belts) would read through it.
- A tail lift folded under the frame, chains on the barn doors, a second roller door on the right, and a real hinge line in the bellows.
- The side tile takes a 64 mm lens at this length, so its perspective is stronger than the other cars' side views.

## Kit wishes

- **Brand helpers:** the third Brakk carries a third copy of `tube`, `bolt`, `plate`, `pylon`, `stencil`, `chevrons`, `coil` and the Brakk wheel; a `brands/brakk.py` beside the kit would hold them once.
- **Lettering:** `text_mesh` centers text on its origin in both directions; an option for the baseline, and a note in the guide, would save a round of misplaced numbers.
- **Geo:** prisms from a polygon in a named plane (`yz`, `xy`, `xz`), an upright cylinder, a ring about any axis, and a bolt row along a line.
- **Side view of long vehicles:** an orthographic side tile, or a deeper studio, so a 6.6 m truck is drawn with the same lens as a coupe.
- **Fifth tile:** let the hero's fit know the tile's corner, so a tall vehicle never needs its size tuned by eye.
