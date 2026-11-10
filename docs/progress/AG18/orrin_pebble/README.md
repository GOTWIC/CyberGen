# Orrin Pebble

![sheet](sheet.jpg)

- **Brand, model, type:** Orrin Pebble, city pod, 2 seats side by side (all names made up). The Lumen's little sibling.
- **Size:** 2.82 m long, 1.61 m wide, 1.52 m high, wheelbase 1.78 m, wheels 0.59 m, ground clearance 0.14 m.
- **Triangles:** 266,030 in 48 objects (body at subdivision 4).
- **Build:** `vehicles/blender.sh vehicles/cars/orrin_pebble.py --out docs/progress/AG18/orrin_pebble --sheet`

## The design

- A river stone held in four soft paws: nine lines over eleven ring stations, no crease anywhere, the rings closing on a pole at the nose and at the tail as on the Lumen. Nearly the same front to back; only the lights say which way it faces.
- The glass is one dome from pole to pole. Its edge dips to the waist at the doors (the sill you step over) and the four fenders rise round it like claws round a gem.
- The dome forward of the hinge ring (a hairline and two metal knuckles over the rear axle) is one leaf that lifts as the door, with a crescent grab recess under its lowest point; the small tile shows it lifted. The glass behind the hinge is fixed over a luggage shelf with a strapped case, a soft bag and a rail.
- One ribbon all the way round the waist: white from one flank pebble round the nose to the other, red round the tail, a lit pebble on each pole and on each flank (the left one, in its flap ring, is the charge port).
- The Orrin cues: wheels under eyelid openings that hide the top half of the turbine discs (44 vanes, two light rings), paired crescents under each pole and beside each lid, dot lenses under both poles and on the rear paws, petal shut lines, `pebble` low on the petal, `orrin` on the tail and lit under the nose glass, a hair of light round both tongues of the dome.
- Seats made of three smooth stones each. Show color: a damson violet satin pearl with amber light, oat seats and a tan case.

## What I would improve

- The front wheels have no room to steer far inside their cavities, and the tires stand a little ahead of the chin when seen from low in front.
- The leaf has no seal, struts or latch; the sill at the dip could carry a bright step plate.
- A few small teeth remain where the paint's rim meets the glass tongue beside each pole pebble.
- The dash is one stone with a strip screen; it deserves controls, and the cabin belts.

## Kit wishes

- A per-view hook in `shoot()` or `render_view()` (a function called before and after a view renders), for a state of the car's own such as a lifted canopy; this script wraps `K.render_view` to do it.
- A second corner tile on the sheet (`extra` as a list), for an open state and a detail view together.
- A glass with a coating in the kit (`materials(glass_ior=...)`): the kit's glass at IOR 1.5 mirrors the studio lights over most of a dome, so this car brings its own at 1.14.
- `emit()` strengths in the palette (`led_rear_strength`): AgX turns the kit's red and amber pale at their default strengths, so this car defines a dimmer red and amber of its own.
- `stats()` and `car_size()` measured from the ground, not from the lowest object: a hull probed without wheels reports its height short by its ground clearance.
- As the Lumen asked: a nearest-point `on_body`, `strip()` and `pebble()` in the kit, and a wheel builder that takes a car's own rim.
