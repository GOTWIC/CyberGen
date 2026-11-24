# Caldera Strand (S-20)

- **Maker:** Caldera Transit Works. **Operator on the car:** Skein Metro, line 7 "Ember Line".
  Every name, station and advert on it is made up.
- **Type:** an electric multiple-unit car for elevated and underground city lines, third rail
  power, with a complete interior to walk through. Two variants from one script: the **end
  car** (a cab and a nose at +x, a gangway at -x) and the **middle car** (a gangway at both
  ends).
- **Script:** `vehicles/trains/caldera_strand.py`.

## Numbers as built

Frame: x forward, y left, z up, meters, the origin on the rail top under the car's middle.

| | |
|---|---|
| Body over its ends | 20.0 m (x -10.0 to +10.0); with the bellows 20.5 m (end car), 21.0 m (middle car) |
| Width | 3.0 m at the stripe band (z 1.78 to 1.90); 2.98 m over the door steps |
| Underframe | z 0.85 |
| Passenger floor | z 1.15, flat from end to end, cab and gangways included |
| Roof | skin crown z 3.97; with the air-conditioning units 4.40, the whip aerial 4.42 |
| Doors | three double plug doors a side, middles at x -6.667, 0, +6.667; clear opening 1.40 m wide, 2.05 m high (z 1.15 to 3.20) |
| Gangway | passage 1.20 m wide, 2.05 m high; bellows out to x -10.5 (half the 1.0 m gap) |
| Cab door | 0.68 m wide, 2.02 m high |
| Aisle | at least 0.91 m clear end to end (beside the doorway poles); 1.86 m between the benches, 1.40 m past the facing bay |
| Headroom | 2.35 m under the ceiling over the aisle (z 3.50); 2.16 m under the two hung screens; 2.05 m in doorways and gangways; 2.25 m in the cab |
| Wall | skin to lining 85 mm at the windows, 60 to 100 mm below them; floor 300 mm; roof 470 mm at the crown |
| Seats | end car 41 and 3 tip-up, one wheelchair space; middle car 49 and 3 tip-up, one wheelchair space |
| Standing | about 130 (end car) and 140 (middle car) at 4 people per square meter |
| Bogies | centers x +-6.70, axles 2.20 m apart, wheels 0.84 m, 1435 mm gauge |
| Triangles | end car 397,453; middle car 362,478 (the track is not counted) |

## The design

Outside:

- A tumblehome section, widest at a 120 mm stripe band; bare satin metal flanks with three
  rolled beads, a graphite roof, graphite doors.
- One black glazing band from the tail to the nose, where it wraps the cab as a visor: the
  side glass bends round the corner and meets the flat windshield at a black post.
- The line's color is one material, `paint2`: the stripe under the glazing band and the whole
  prow under the visor (inside: the wall rail, seat bands, pole collars, the line maps).
- A softly chamfered nose: raked 19 degrees above a beak line, undercut below it. The stripe
  band turns into a black light band round the beak: a white line along its top and, in
  openings under it, two headlamp units a side (a projector and a reflector in a housing
  behind a clear lens, the kit's `Lamp`) and a red-lensed tail marker at each corner; a
  dot-matrix destination sits in the mask over the glass.
- Door leaves with capsule windows, a light strip down each meeting edge (green while
  released), a button on each b leaf, a lamp over every doorway, a step lip under it.
- Dot-matrix destination signs on the cant panel, a running light under the cant rail, the
  car's number, the operator's mark, small print, hatches and latches on the skirt.
- Roof: two air-conditioning units with fans under guards, cable ducts, a walk strip, a fin,
  a puck and a whip aerial. No pantograph.
- Under the floor: converter with cooling fins, battery box, compressor and two air tanks,
  brake control, auxiliary supply, trunking, labels.
- Bogies: an H frame outside the wheels, rubber springs over the axle boxes with dampers,
  air springs, a motor and gearbox an axle, tread brake units, collector shoes on a beam
  each side, guard irons and a plough under the nose. A bar coupler and jumper cables at a
  gangway end.

Inside:

- Speckled non-slip floor, sill plates with tactile ribs and a yellow strip at every
  doorway; lined walls with a rail in the line's color, windows with rounded corners in
  real reveals, coves with adverts, a ceiling with two continuous light lines, vent slots,
  speakers and camera domes.
- Seating along the walls on cantilever beams with a light under them; one bay of two pairs
  facing each other (left, rear half); priority seats in their own cloth by the middle
  doorway with their sign; a wheelchair space by the middle doorway (right, front half)
  with a backrest, a belt, a wall rail, a floor mark and a help point; three tip-up seats in
  a marked bike and luggage zone.
- Draught screens of glass beside every doorway on a pole; grab rails over the bench fronts
  with hand loops; a pole in the end doorways that opens into three; two high rails over the
  middle doorway.
- Doorways: lined leaves with windows, kick plates and pull bars; open and close buttons on
  the post ahead, the emergency release in a red box on the post behind, a notice over it,
  a warning lamp on the lintel, the line's map with its stops as lamps over the doorway.
- Two screens hung over the aisle, a dot-matrix display and the car's number over each
  gangway, equipment lockers at the ends, a fire extinguisher, a first aid sign.
- End car: the cab's back wall with a screen and the line's rules, the cab door with a
  window; in the cab a wraparound desk with five screens, a master controller, switches, an
  emergency stop and a handset, the driver's seat, a tip-up seat, a locker, two blinds, a
  foot rest, a wiper outside.

## Objects and switches

- `door.<l|r><1|2|3>.<a|b>`: one object a leaf (skin, glass, lining, kick plate, light
  strips), a the front leaf and b the rear one. To open: a slides +0.705 m in x, b -0.705 m,
  both 0.055 m outward (left +y, right -y). The left doors stand open in the views `hero`,
  `side`, `door` and `doorway` (rigs `rig.door.l<k>.<a|b>`); `CYBERGEN_SHUT=1` builds every
  door shut in every view.
- `interior.*`: everything in the saloon (seats `interior.seat.NN` and hand loops
  `interior.loop.NN` are instances of one mesh each kind; print is one object a color,
  `interior.print.<material>`).
- `cab.*`: the cab's lining, back wall, door (`cab.door`, hinge in its `hinge` property),
  desk and fittings. `gangway.*`: bellows, frame and floor plates.
- `bogie.<f|r>.*`: `bogie.<f|r>.axle<1|2>` are the wheelsets, each one object with its
  origin on its axle; frame, springs, dampers, motors, brakes, shoes beside them.
- `body.*` (the skin's panels), `roof.*`, `underfloor.*`, `light.*`, `sign.*`,
  `lettering.*`, `coupler.*`, `nose.*`.
- `track.*`: 22 m of slab track with a third rail on the right, in the studio's
  collection, not the car's (the studio's floor is lowered 0.44 m under it).
- `CYBERGEN_VARIANT=mid` builds the middle car: the same body, doors, seating and running
  gear, a gangway end with lockers and four seats a side where the cab was.

## Commands

```
B=vehicles/blender.sh; T=vehicles/trains/caldera_strand.py; D=docs/progress/AG18/caldera_strand
$B $T --out $D --sheet                                   # sheet.jpg
$B $T --out $D --clay --check                            # clay.jpg, check.json
$B $T --out TMP --views aisle,vestibule,bay,cab --res 1920 1080 --samples 96
                                                         # the four tiles of interior.jpg (put together with PIL)
CYBERGEN_VARIANT=mid $B $T --out TMP --preview           # mid.jpg (TMP/preview.jpg)
```

Views of its own: `aisle`, `gangway`, `vestibule`, `bay`, `access`, `cab` (inside, lit by
the car's own lights, the studio brightened so the windows are not black), `doorway`,
`door`, `nose`, `tail`, `bogie`.

## Checks

`--check` says ok on both variants: no open panel edges, nothing through the skin, the
triangles under the kit's 400,000. Marked as meant in the script: the wheel flanges reach
29 mm under the rail top; the one-sided layout inside and under the floor; the interior
seen through the open gangway and doorways.

## What I would improve

- The lamp units are small (60 mm openings in a 120 mm band); a taller band would carry
  larger projectors. The gangway ends have reflectors only, no marker lamps.
- The plough under the nose and the tip-up seats are simple solids.
- The door windows' black borders come from the kit's frit inset on a subdivided panel:
  their inner outline is a capsule with slightly uneven corners.
- The bellows are a single folded sheet, with no inner lining panels or a second fold layer.
- The lettering is plain geometry; a wrap or a livery texture would carry finer graphics.
- No wear beyond the floor's worn patches; seats, poles and the lining are factory clean.
- The cab has no pedals beyond the foot rest and no cab-side door.

## Kit wishes

- A studio for long vehicles: lights, floor and camera limits are sized for cars (the script
  moves and resizes every light, and the hero needs `center=True` to fill its frame).
- A floor height for the studio (a track or a dock under the vehicle wants z < 0).
- A way to keep studio lights out of camera and transmission rays in inside views (the
  script sets it on every light) and a "daylight" switch for views from inside.
- `text_mesh(..., resolution=)`: lettering at the default curve resolution was more than
  half of this car's triangles; the script carries its own coarser copy.
- `join(objs)` and `split left/right` for body panels (a door leaf as one object), and a
  panel's vertex crease so two body pieces can share a boundary without matching creases.
- `build_body`'s frit borders with a corner radius, and a frit on an open sheet's edge.
- `carcheck`: a notion of rail wheels (no steering, flanges under the running surface) and
  of an interior that is meant to be seen.
