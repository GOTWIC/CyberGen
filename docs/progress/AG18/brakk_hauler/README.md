# Brakk Hauler

![sheet](sheet.jpg)

- **Brand, model, type:** Brakk Industrial Hauler, crew cab pickup truck with an open load bed (all names made up).
- **Seats:** 4 (two buckets, a rear bench), four doors.
- **Size:** 5.69 m long, 2.20 m wide over the tires, 1.95 m high at the roof bar (2.08 m with the antenna); wheelbase 3.50 m; tires 0.90 m in diameter, 0.32 m wide; hull floor at 0.48 m, lowest point (rear axle housing) 0.31 m.
- **Triangles:** 230,460 in 123 objects.
- **Build:** `vehicles/blender.sh vehicles/cars/brakk_hauler.py --out docs/progress/AG18/brakk_hauler --sheet`

## The design

- A narrow monolith: nose, hood and cab are one hull of flat plates, every edge sharp, every top edge a 45 degree chamfer; the bed is a second, narrower tub behind it.
- The wheels stand outside the hull, in the open, each under a bolted three-facet fender plate (slope, flat, slope) with a folded outer edge, ribs on top and gussets to the body. Wishbones, half shafts, dampers and red springs show in the gap; a beam axle with links at the rear.
- The face: a dark slab with four body-color ribs and a stencilled badge plate between two light pylons on the chamfered corners; a winch bumper with rising ends, shackles and hazard stripes under it.
- Behind the cab a sail frame (bar frame, plate web, a crossbar with two work lamps) runs down to the bed rail; the bed has corrugated sides, a tread plate floor, tie-down rings, rack rails, a strapped spare and a stencilled tailgate.
- Upright glass in thick frames, a plate gusset for an A-pillar, external hinges, bar handles, rub strips, side steps, tube-frame mirrors.
- Lugged tires with side biters and raised sidewall lettering on dished steel rims with a bolted bead ring.
- Show color: signal ochre, with graphite plates and red recovery points.

## Brakk family cues (for the Bastion and the Mule)

Geometry and texture only, none of it depends on the color:

1. **Plate and chamfer.** Flat plates, all edges sharp, one chamfer size (about 0.12 m, 45 degrees) on every top edge and on the nose and tail corners in plan. Wide panel gaps (8 mm) and a broad edge bevel.
2. **Wheels outside the hull** under separate three-facet fender plates with a folded edge and two rows of bolt heads; never a well cut into the body.
3. **Light pylons:** a tall housing with a vertical bar and an amber cell at its foot, standing on each chamfered corner (white in front, red behind), and one full-width bar of eight cells over the windshield with amber end lamps.
4. **The ribbed slab** as a face: horizontal trapezoid ribs in body color on a dark plate, the name on a bolted plate above them. Cargo walls take the same rib upright (corrugation); doors take it lying as rub strips.
5. **Fasteners in rows:** hex heads every 0.10 to 0.15 m along plate edges, sills, pillars and rails.
6. **Hardware you can name:** winch and fairlead, shackles, hitch, side steps, tie-down rings, rack rails, a sail or roll frame with work lamps, external hinges, bar handles.
7. **Stencils:** large capitals cut by bridges, a unit number on the doors, hood, fender slopes and frame (`27`, `B-27`), small print under the model name, hazard stripes on the bumpers.
8. **The Brakk wheel:** lugged tire, raised sidewall text, dished steel disc with eight round windows, bolted bead ring, eight lug nuts.

The script's helpers for these (`plate`, `pylon`, `bolt`, `stencil`, `chevrons`, `build_wheel`, `tube`, `coil`) can be copied into the next Brakk's script as they are.

## What I would improve

- A see-through rear window in the cab's back wall (it is a dark pane in a frame now) and a fuller cabin: door cards, pedals, belts.
- The front suspension is hidden from most angles by the bumper ends and the fender slopes; a higher, shorter bumper would show the wishbones.
- Tread as real carved blocks with sipes rather than blocks set on a carcass; mud on the tires and plates.
- Fender plates on stays that move with the wheel, a tailgate with hinges and chains, a cable on the winch drum.

## Kit wishes

- **View fitting:** fit to the car's silhouette (vertices), not to the corners of every object's box. For a tall, long car the hero and the end views come out small (this script sets negative margins), and the side tile of the sheet put the camera 24 m away, behind the studio's wall at 16 m, so the tile was empty: a shorter default lens for the side view, a larger cove or a warning.
- **Studio:** the two low strip lights are seen straight through both side windows in the side view (white windows). This script switches off their camera and transmission visibility after `build_studio()`.
- **Wheels:** a tire style for off-road tread, a way to skip the kit's tire or rim, and a rotation for a wheel that is not on an axle (a spare).
- **Body:** a flat end cap that can hold a glass panel (an upright cab back with a window); the bevel width and the gap as they are now can only be changed after the build; the paint's dust height range as a palette key.
- **Helpers worth sharing:** a straight tube or bar between two points, a bolt row along a path, stencil lettering laid out letter by letter, hazard stripes, a rotation argument on `Geo.obj`.
