# Kestrel Aerodyne Meridian

![sheet](sheet.jpg)

- **Brand, model, type:** Kestrel Aerodyne Meridian, hover sedan, 4 seats, four doors. The
  second Kestrel, the calm one of the family.
- **Size:** 5.32 m long (pitot pins to fin tips; the hull 5.06 m), 2.08 m wide over the pods
  and the open step, 1.38 m high, hovering: keel light 0.335 m, emitter rings 0.38 m and belly
  0.42 m over the ground, the roof at 1.67 m.
- **Triangles:** 119,902 in 129 objects (step B; 90,334 in 110 before). Show color: pearl
  cobalt blue over the graphite lower hull, cyan emitters, tan seats.
- **Build:** `vehicles/blender.sh vehicles/cars/kestrel_meridian.py --out docs/progress/AG18/kestrel_meridian --sheet`

## The design

- **The family, kept:** the knife chine with its bright strip from prow to stern (lit white
  at the front, red at the stern), flat top facets with flush glass and the matte visor, seven
  ribs along the graphite lower hull, the eight-sided emitter pod (the Dart's `build_pod`),
  canted fins, slanted slot thrusters, the keel blade with its light, stencil registration
  (`KM-404` on the fins and the roof, `KA 4-404` by the nose, `E1` to `E4` on the pods).
- **Its own face:** a blunt axe-head prow, a shallow vee in plan. The lit chine turns the
  corner and bridges a recessed mouth as one blade of light; a body-color stem splits the
  mouth, three lamp cells under a lens and a sensor slit each side.
- **A sedan's cabin:** tall and framed. A body-color rail runs up the windshield pillar,
  along the roof and down beside the rear glass, over six upright side windows (a quarter
  light, two door glasses, a tapering rear light per side); a smoked glass roof over the
  front seats, a solid roof with the registration over the rear ones; every top facet folded
  along a center ridge.
- **Pods tucked in:** all four hang under the chine, half sunk in the lower hull, no pylons.
- **Boarding steps:** a ribbed tread with stringers folds out of the lower hull under each
  door, between the pods; out on the left side, stowed flat on the right.
- **Stern:** the thrusters in two banks of three either side of a stern post with a red
  light; low fins that start at the rear glass's corners and end past the stern.
- **Under the floor** (the sheet's fifth tile): four emitters, the keel light, cross ribs,
  conduits from the keel to each pod.

## Step B: lamps, cut lines, glass (2026-11-13)

The Dart's family of lamps on the Meridian's own hull, and the car on
`vehicles/brands/kestrel.py` (the chine, the fin plane, the pods and their ribs; its copies
were the module's). The sheet, clay, zebra and check above are of this build.

- Nose lamps: the three lit cells each side of the stem are now in a slot cut 40 mm into the
  mouth's back wall, standing 3 mm proud of the wall between bright dividers that run to the
  slot's floor, under a clear lens in a dark surround that stands 12 mm proud round the slot
  (they were boxes standing in the mouth). A lens flush with the wall was tried first: the
  game pack's LOD3 drew the wall across the slot and the lamps went dark there.
- The chine's light: the knife edge cut away for its first 0.80 m from the prow and its last
  0.29 m, a channel 18 mm up the edge and 22 mm deep under a clear (front) or red (rear) lens
  that keeps the edge's shape, a lit core and a bright liner inside; the bright blade runs
  between them, and the light blade that bridges the mouth now leaves from the lit channel.
- Stern bar: a channel 16 mm wide and 26 mm deep in the band round the top of the mouth
  under a red lens, narrowing to 9 mm past the mouth's middle; a red core and bright ribs
  behind it (it was a bar lying on the band).
- Keel blade: its foot is a lamp channel 24 mm high along 3.30 m with dark walls, a light
  guide in a frosted sleeve over a bright reflector strip and a clear lens flush with the
  foot (the keel now floats 335 mm over the ground, 327 before, the lens its lowest point).
- Thruster slots: a cross of vanes set back in each of the six slots.
- The maker's name over the stern bar is laid on the band (it floated off it), its letters
  5 mm proud: laid flat, the game pack baked them into the band's texture and lost strokes.
- Cut lines: the styling groove under the side glass, a flush release on each door and the
  six-sided charge flap are cut through the skin (they were strips lying on it); 3.5 mm shut
  lines everywhere. The hood's sensor slits stay printed.
- Glass: every pane (windshield, roof, quarter lights, door glasses, rear lights, rear
  glass) with a black frit border as part of the glass; the flat facets take it without
  shards.
- Cabin tub: step A found it 16.8 mm in the open under the rear seats' floor corner; the
  floor's rear corners are cut in and a step up carries the rear bench where the belly
  rises, the dash and the door cards are 40 mm narrower at their foot and the cards stop at
  the rear bench (`through` ok now).
- The boarding step (out on the left, stowed on the right) and the pilot's yoke are told
  as meant (`K.meant`); the pod, fin code and stern name findings of 3 to 11 mm are as
  before.
- 119,902 triangles (90,334 before; the lamps 8,200 of them, the cut hull most of the rest:
  the styling groove and the chine's channels are traced every 4 and 2 cm, which kept the
  pack's LOD3 from starving and dropping the prow's stem; the stem's foot now reaches down
  to 0.51 m, 38 mm lower, so that LOD keeps it).

Left: the pods' tip lamps are flat faces of the pod (as on the Dart); the emitters' layered
glow is step C's; the styling groove shows a thin line of the door cards through it from
close by (a cut line is a hole through the skin); the windshield's grey sheen is as before.

## What I would improve

- The step bays read as plain dark panels in the side view; a real recess with the hinge
  arms in it would say more.
- The pods meet the hull without a fairing lip, and the door cuts stop at the glass frames.
- The cut lines are holes through the skin; the shoulder groove would read better with a
  closed floor behind it.
- The windshield still carries a grey sheen of the top light on its near half in the hero.

## Kit wishes

- A coated or smoked glass in the library: the top soft box is long across the car, so flat
  glass facing the sky mirrors it white in the hero and the back view, and a clear glass roof
  floods a light cabin (here `glass_coat` and `glass_smoke`, a lower IOR and a dark tint).
- `rib`, `plate` and `chine` (copied again from the Dart) and a tilted box (`slab` here) in
  the kit; a `Geo.box` that takes a frame.
- A way to say what the under view is lit by: it is dark between the emitters.
