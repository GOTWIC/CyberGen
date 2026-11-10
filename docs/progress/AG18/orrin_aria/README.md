# Orrin Aria

![sheet](sheet.jpg)

- **Brand, model, type:** Orrin Aria, hypercar, 2 seats side by side (all names made up). The wild one of the family, after the Lumen and the Pebble.
- **Size:** 4.74 m long, 2.06 m wide, 1.12 m high, wheelbase 2.75 m, wheels 0.76 m, ground clearance 0.13 m.
- **Triangles:** 501,460 in 53 objects (core and pods at subdivision 4).
- **Build:** `vehicles/blender.sh vehicles/cars/orrin_aria.py --out docs/progress/AG18/orrin_aria --sheet`

## The design

- Five poured drops and no crease anywhere: a core (the low nose and the cabin, one teardrop from the nose pole to the tail pole), a front fender pod each side and a rear hip each side. Every drop is a ring cage that closes on a pole at both ends, as the Lumen's hull does.
- The voids are the design. Ahead of the front axle the fender pods stand free of the nose (two slots, with a blade under the nose as the floor of the through-duct). Behind the doors the cabin draws in to a slim tail and the hips stand clear of it: a channel each side with no floor, from the door back to the tail, crossed only by three faired arms at the rear axle.
- The yoke: one hoop laid over the glass behind the heads whose two legs fly back over the channels and sink into the hips' crests. They are the flying buttresses, and the hoop is the roll bar the glass roof needs.
- The canopy is one teardrop of coated glass from pole to pole, with petal door hairlines over it; a dark gloss liner, two seats of three stones each and a strip screen under it.
- The ribbons trace the voids. White: from behind each front wheel over its lid, round the pod's tip, back up the slot and out along the nose to the lit pebble on the nose pole. Red: down each buttress from the roof, along the hip's crest, round its tip and across the tail blade to the pebble on the tail pole.
- The Orrin cues: lidded wheels on turbine discs (60 vanes, two light rings), paired crescents (the intakes on the hips, one in each front wheel's wake, a pair under the nose pole), dot lenses on the pods' fronts and the hips' tails, `aria` low on the door, `orrin` on the hoop and lit under the nose glass, a hair of light round both tongues of the canopy, a ring of light for the charge port on each hip's nose.
- Show color: obsidian black in a satin pearl, with ice blue light and cognac seats. The sheet's two small tiles are the rear three-quarter and the plan, where the channels show best.

## What I would improve

- The drops meet as plain intersections (pod to core, buttress to hip); a poured car wants a fillet there, which needs the bodies built as one cage or a blend pass.
- The front wheels have little room to steer inside their pods, and the three arms across each channel stand in for a whole suspension.
- The hips' inner walls mirror the studio lights in the back view and read as bright metal; a satin finish in the channels would calm it.
- The doors are hairlines over the glass and a pull; hinges, a seal and an open state would explain the way in.
- Half a million triangles: the pods would do at subdivision 3.

## Kit wishes

- A sheet with more than one small tile (`extra` as a list with a corner each): this script lays its second tile into the finished sheet itself (`second_tile`).
- As the Lumen and the Pebble asked: a nearest-point `on_body`, and `strip()`, `pebble()`, `lune()` and the turbine disc in the kit; three Orrins now carry copies.
- `build_body`: pole closure as an option (`front=dict(kind="pole", at=...)`), and a tube whose first ring lies on y = 0 documented as the way to carry a piece across the centerline (the yoke relies on it).
- A blend between two body pieces (a fillet along their intersection), or a boolean union of pieces before the panels are split.
- A coated glass in the palette (`glass_ior`), and `emit()` strengths in the palette: the kit's red goes pale under AgX.
