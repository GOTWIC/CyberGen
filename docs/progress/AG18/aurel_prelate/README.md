# Aurel Prelate

![sheet](sheet.jpg)

- **Brand, model, type:** Aurel Prelate, formal coupe, 2 + 2 seats (all names made up). The first Aurel: it sets the family's cues.
- **Size:** 5.19 m long, 1.96 m wide over the body (2.02 m over the mirror cameras), 1.31 m high; wheelbase 3.20 m (stretched from 3.1 to shorten the overhangs); wheels 0.80 m in diameter; ground clearance 0.15 m.
- **Triangles:** 215,832 in 95 objects.
- **Build:** `vehicles/blender.sh vehicles/cars/aurel_prelate.py --out docs/progress/AG18/aurel_prelate --sheet`

## The design

- A monolith on a plinth: a slab nose and a slab tail that both lean out over a dark fluted base, a hood 2.3 m long, the cabin set far back, a deck of 0.4 m.
- Ten lines over twelve stations, three of them sharp: the razor shoulder (with a narrow machined chamfer above it, nose to tail), the sill line and the plinth's foot. The flanks between are one quiet, slightly convex surface. The hood and the deck are clamshells whose cuts hide in the shoulder crease.
- No grille opening: 51 slots of light let into the nose slab hang from its top edge, the middle one longest, and go on over the edge along the hood. From the front it is a downward point, from above a lozenge folded over the edge. The tail repeats it smaller, in red.
- The glass is one folded black canopy (windshield, roof and rear glass in three flat facets) over upright side glass in a polished frame; the only body color above the shoulder is one leaning pillar each side, a band of one width that carries the crest.
- Show color: black cherry lacquer, polished trim, parchment seats, warm white light.

## Aurel's signature cues (for the Regent and the Zenith to repeat)

Geometry and texture only, none of it depends on the color:

1. **Slab and plinth.** Flat ends, top edge ahead of the foot at both ends. The whole car stands on a recessed band of fine vertical flutes (22 mm pitch, dark machined metal) with one polished strip along its top: the sill line. On the hover car the plinth runs round unbroken.
2. **The folded lozenge.** Light only as slots let into the paint (8 mm wide, 30 mm apart, two bright hairline flutes between each pair), hanging from a slab's top edge in a point and folding over the edge onto the hood or deck. Never a frame, never an opening.
3. **Blades.** A slim vertical light in a dark slot with two bright edges at each corner of each slab, from sill to shoulder, and a hairline of light round the corner on the flank.
4. **Razor and chamfer.** One shoulder crease from blade to blade with a narrow flat chamfer above it; panel cuts hide in it.
5. **Folded canopy, leaning pillar.** Flat glass facets with sharp folds, black frames on top, a polished frame round the side glass, side glass no more than 23 degrees from upright, one body-color pillar leaning with the rear glass.
6. **Pleated discs.** A shallow dished disc of 96 fine radial pleats inside a polished ring, a dark cap with the crest.
7. **Crest and wordmark.** The crest is a tall lozenge with a dark lozenge inside and a bright bar down the middle: behind the point of light on the hood (a hairline spear runs back from it), on each pillar, on each wheel cap; its outline is also the charge flap. The wordmark is wide-spaced serif capitals (Didot), once on the tail, the model name small beside it and low on the fender.

The script's helpers for these (`Slab`, `lozenge`, `blade`, `crest`, `build_plinth`, the disc in `build_wheel`) can be copied into the next Aurel's script as they are.

## What I would improve

- The light slots are inlays 4 mm proud of the paint; real channels sunk in the slab would glow from inside. On the hood they read as ivory lines at the hero's shallow angle.
- The dark lacquer mirrors the bright floor on the nose slab, so the nose looks paler than the flanks.
- Where the canopy's dark frame and the side glass's polished frame meet at the foot of the windshield pillar the corner is untidy.
- The plinth across the two ends is laid on the flat cap; on the flanks it is truly stepped back.
- The cabin is blocks (seats, dash, console, a pillar to pillar screen); from behind, the hood's slots show through both screens.
- The door's rear cut runs 6 cm ahead of the rear wheel arch; a rear-hinged door would suit the car better.

## Kit wishes

- **A light hook.** From the hero's side the top soft box is mirrored whole in a windshield raked 35 to 45 degrees: a white pane over the cabin. This script wraps `K.build_studio` and takes the canopy out of that light with Cycles light linking; a kit option (`unlit={"top": ["body.canopy"]}`) would do it for every car.
- **Light strength in the palette** (`led_front_strength`, ...): fine slots of light clip to white at the kit's 60; this script remakes `led_front` and `led_rear` dimmer.
- **Fonts:** a `font=` argument on `text_flat` and `text_on_body` (this script sets `K._FONT[0]` to a serif).
- **End caps:** a frame for building on a flat cap (this script's `Slab`: a point at height z, a box on the plane), and a flat cap that can step back (a plinth, a bumper line).
- **Rows of ribs:** a helper that lays flutes or ribs along a run of the surface; three brands now build them by hand.
- **Floor brightness:** a darker floor (or a palette key for it) for very dark gloss paint.
