# AG18: what the kit's checks find

`python vehicles/survey.py --docs` runs `carkit`'s checks (`vehicles/carcheck.py`) and its clay and zebra renders on every car but those to be redesigned. Each car's folder holds its `check.json`, `clay.jpg` and `zebra.jpg`. A verdict is `ok`, `look` (worth a look at the place named; often meant) or `FAIL`.

| Car | Tires | Ground | Symmetry | Panels | Through | Triangles |
|---|---|---|---|---|---|---|
| [aurel_prelate](aurel_prelate/check.json) | FAIL: 0.1 mm to interior.tub, steers 5 deg | ok: 150.0 mm (body.floor) | look: 5 objects | ok: 0 open runs, 0 cutter holes | look: 1 parts | ok: 215832 |
| [aurel_regent](aurel_regent/check.json) | FAIL: 0.1 mm to interior.tub, steers 5 deg | ok: 150.0 mm (body.floor) | look: 2 objects | ok: 0 open runs, 0 cutter holes | look: 1 parts | ok: 228554 |
| [aurel_zenith](aurel_zenith/check.json) | ok: none (hover) | ok: 270.3 mm (emitter.crest) | look: 1 objects | ok: 0 open runs, 0 cutter holes | ok: 0 parts | ok: 129135 |
| [brakk_bastion](brakk_bastion/check.json) | ok: 25.8 mm to fender.gussets, steers 20 deg | ok: 280.0 mm (chassis) | look: 13 objects | ok: 0 open runs, 0 cutter holes | look: 2 parts | ok: 269389 |
| [brakk_hauler](brakk_hauler/check.json) | ok: 33.1 mm to springs, steers 20 deg | ok: 290.0 mm (chassis) | ok: 0 objects | ok: 0 open runs, 0 cutter holes | ok: 0 parts | ok: 259196 |
| [brakk_mule](brakk_mule/check.json) | look: 22.2 mm to fender.plates, steers 20 deg | ok: 280.0 mm (chassis) | look: 34 objects | ok: 0 open runs, 0 cutter holes | look: 1 parts | ok: 364552 |
| [halcyon_ridge](halcyon_ridge/check.json) | ok: 39.5 mm to body.well, steers 25 deg | ok: 237.8 mm (skid.front) | look: 1 objects | ok: 0 open runs, 0 cutter holes | ok: 0 parts | ok: 250007 |
| [halcyon_sable](halcyon_sable/check.json) | ok: 31.8 mm to interior.seats, steers 30 deg | ok: 100.0 mm (splitter) | look: 1 objects | ok: 0 open runs, 0 cutter holes | ok: 0 parts | ok: 280675 |
| [kestrel_atlas](kestrel_atlas/check.json) | ok: none (hover) | ok: 374.4 mm (pod.skid.r) | look: 19 objects | ok: 0 open runs, 0 cutter holes | look: 1 parts | ok: 151203 |
| [kestrel_dart](kestrel_dart/check.json) | ok: none (hover) | ok: 325.0 mm (keel) | look: 3 objects | ok: 0 open runs, 0 cutter holes | look: 1 parts | ok: 112558 |
| [kestrel_meridian](kestrel_meridian/check.json) | ok: none (hover) | ok: 335.0 mm (lamp.keel.glass) | look: 3 objects | ok: 0 open runs, 0 cutter holes | ok: 0 parts | ok: 119902 |
| [orrin_aria](orrin_aria/check.json) | FAIL: 0.0 mm to body.front, steers 0 deg | ok: 131.8 mm (body.floor) | look: 2 objects | look: 0 open runs, 12 cutter holes | ok: 0 parts | look: 501460 |
| [orrin_lumen](orrin_lumen/check.json) | look: 14.6 mm to body.well, steers 0 deg | ok: 130.0 mm (body.floor) | look: 2 objects | ok: 0 open runs, 0 cutter holes | ok: 0 parts | ok: 356940 |
| [orrin_pebble](orrin_pebble/check.json) | FAIL: 0.0 mm to body.well, steers 0 deg | ok: 143.3 mm (body.floor) | look: 5 objects | look: 0 open runs, 10 cutter holes | ok: 0 parts | ok: 266030 |
| [tanager_cab](tanager_cab/check.json) | FAIL: 0.0 mm to bumper.guards.rear, steers 0 deg | ok: 120.0 mm (mudflaps) | look: 39 objects | FAIL: 4 open runs, 0 cutter holes | look: 1 parts | ok: 285996 |
| [tanager_mino](tanager_mino/check.json) | ok: 51.9 mm to body.clad, steers 35 deg | ok: 110.0 mm (mudflaps) | look: 1 objects | ok: 0 open runs, 0 cutter holes | ok: 0 parts | ok: 276187 |
| [tanager_porter](tanager_porter/check.json) | FAIL: 0.0 mm to interior.tub, steers 0 deg | ok: 120.0 mm (mudflaps) | look: 87 objects | FAIL: 5 open runs, 0 cutter holes | look: 5 parts | ok: 314760 |
| [vanta_r](vanta_r/check.json) | look: 12.8 mm to body.well, steers 0 deg | ok: 95.0 mm (splitter) | look: 5 objects | ok: 0 open runs, 0 cutter holes | ok: 0 parts | ok: 304992 |

## Findings by car

**aurel_prelate** (FAIL)

- tire `fl`: 47.6 mm to `body.well`, turns 5 degrees before it touches `body.well`
- tire `rl`: 0.1 mm to `interior.tub`
- tire `fr`: 47.6 mm to `body.well`, turns 5 degrees before it touches `body.well`
- tire `rr`: 0.1 mm to `interior.tub`
- not mirrored: `interior.wheel` 189.7 mm, `cowl.slot` 19.0 mm, `body.trim_ws` 14.0 mm, `body.sill` 9.9 mm, `body.trim_b` 8.6 mm
- cabin part in the open: `interior.tub`, 8% of it, up to 38.3 mm from what would hide it, at (-0.984, 0.876, 0.175)

**aurel_regent** (FAIL)

- tire `fl`: 51.6 mm to `body.well`, turns 5 degrees before it touches `body.well`
- tire `rl`: 0.1 mm to `interior.tub`
- tire `fr`: 51.6 mm to `body.well`, turns 5 degrees before it touches `body.well`
- tire `rr`: 0.1 mm to `interior.tub`
- not mirrored: `interior.wheel` 134.1 mm, `body.trim_ws` 3.9 mm
- cabin part in the open: `interior.partition`, 50% of it, up to 15.5 mm from what would hide it, at (0.131, -0.84, 1.36)

**aurel_zenith** (look)

- not mirrored: `interior.wheel` 187.4 mm

**brakk_bastion** (look)

- not mirrored: `mast` 261.5 mm, `interior.wheel` 208.9 mm, `led.mast` 190.0 mm, `mast.eye` 174.0 mm, `interior.screens` 76.6 mm, `spare.arm` 56.6 mm, `hooks` 37.6 mm, `wipers` 23.7 mm, `port.cover` 23.3 mm, `port.bolts` 14.0 mm, `winch.rollers` 12.2 mm, `hood.louvres` 10.9 mm and 1 more
- cabin part in the open: `interior.seats`, 1% of it, up to 29.9 mm from what would hide it, at (-1.012, -0.636, 1.505)
- cabin part in the open: `interior.tub`, 5% of it, up to 9.9 mm from what would hide it, at (0.947, -0.607, 0.583)

**brakk_hauler** (ok)

- nothing

**brakk_mule** (look)

- tire `fl`: 22.2 mm to `fender.plates`, turns 20 degrees before it touches `cables`
- tire `ml`: 22.2 mm to `fender.plates`
- tire `rl`: 22.2 mm to `fender.plates`
- tire `fr`: 22.2 mm to `fender.plates`, turns 20 degrees before it touches `cables`
- tire `mr`: 22.2 mm to `fender.plates`
- tire `rr`: 22.2 mm to `fender.plates`
- not mirrored: `cargo.case` 298.0 mm, `cargo.crates` 297.5 mm, `cargo.straps` 295.0 mm, `whip` 250.2 mm, `interior.wheel` 238.6 mm, `cargo.drums` 224.1 mm, `roof.hatch` 202.4 mm, `box.platebolts` 176.0 mm, `chevrons` 169.1 mm, `markings` 162.7 mm, `placard.ink` 160.0 mm, `box.plates` 155.6 mm and 22 more
- cabin part in the open: `interior.tub`, 6% of it, up to 11.8 mm from what would hide it, at (2.998, 0.698, 1.454)

**halcyon_ridge** (look)

- not mirrored: `interior.wheel` 149.2 mm, `body.lightband` 12.5 mm, `keel.glyphs` 5.5 mm

**halcyon_sable** (look)

- not mirrored: `interior.wheel` 139.3 mm, `body.lightband` 4.2 mm

**kestrel_atlas** (look)

- not mirrored: `interior.yoke` 242.0 mm, `case.bands` 209.8 mm, `cases` 199.0 mm, `straps` 180.0 mm, `case.stencil` 175.5 mm, `case.latches` 114.0 mm, `led.beacon` 110.6 mm, `strap.ratchets` 43.4 mm, `roof.gear` 29.8 mm, `pod.f.pod_side` 11.9 mm, `pod.m.pod_top` 11.8 mm, `pod.m.pod_low` 11.4 mm and 7 more
- cabin part in the open: `interior.tub`, 35% of it, up to 125.3 mm from what would hide it, at (2.24, -0.734, 0.606)

**kestrel_dart** (look)

- not mirrored: `interior.yoke` 278.2 mm, `interior.screens` 83.7 mm, `fin.code` 3.2 mm
- cabin part in the open: `interior.tub`, 2% of it, up to 4.5 mm from what would hide it, at (0.799, -0.394, 0.475)

**kestrel_meridian** (look)

- not mirrored: `led.step` 236.8 mm, `step.tread` 234.2 mm, `interior.yoke` 219.6 mm, `step.links` 198.5 mm, `step.grip` 197.6 mm, `step.bay` 16.1 mm, `pod.f.pod_low` 11.0 mm, `led.name` 5.2 mm, `fin.code` 3.3 mm

**orrin_aria** (FAIL)

- tire `fl`: 0.0 mm to `body.front`, turns 0 degrees before it touches `pod.well`
- tire `rl`: 2.8 mm to `hip.well`
- tire `fr`: 0.0 mm to `body.front`, turns 0 degrees before it touches `pod.well`
- tire `rr`: 2.8 mm to `hip.well`
- not mirrored: `interior.fittings` 216.3 mm, `led.cabin` 6.0 mm
- open ends of open pieces (meant): `liner.liner`
- a cutter's hole inside `body.front`: 491 mm round, at (2.18, 0.215, 0.384)
- a cutter's hole inside `body.front`: 491 mm round, at (2.18, -0.215, 0.384)
- a cutter's hole inside `pod.pod`: 429 mm round, at (1.435, 0.945, 0.762)
- a cutter's hole inside `pod.pod`: 168 mm round, at (1.445, 0.929, 0.781)
- a cutter's hole inside `pod.pod`: 429 mm round, at (1.435, -0.945, 0.762)
- a cutter's hole inside `pod.pod`: 168 mm round, at (1.445, -0.929, 0.781)
- a cutter's hole inside `hip.hip`: 629 mm round, at (-0.818, -1.022, 0.452)
- a cutter's hole inside `hip.hip`: 629 mm round, at (-0.748, -1.02, 0.453)
- a cutter's hole inside `hip.hip`: 284 mm round, at (-1.293, 0.631, 0.777)
- a cutter's hole inside `hip.hip`: 629 mm round, at (-0.748, 1.02, 0.453)
- a cutter's hole inside `hip.hip`: 629 mm round, at (-0.818, 1.022, 0.452)
- a cutter's hole inside `hip.hip`: 284 mm round, at (-1.293, -0.631, 0.777)
- triangles: 501460 over the 400000 budget; most in `body` 139854, `hip` 105902, `pod` 103052, `tire` 57536

**orrin_lumen** (look)

- tire `fl`: 14.6 mm to `body.well`, turns 0 degrees before it touches `body.well`
- tire `rl`: 23.7 mm to `body.well`
- tire `fr`: 14.6 mm to `body.well`, turns 0 degrees before it touches `body.well`
- tire `rr`: 23.7 mm to `body.well`
- not mirrored: `interior.wheel` 161.6 mm, `led.cabin` 8.3 mm
- open ends of open pieces (meant): `deck.front.deck`, `deck.rear.deck`

**orrin_pebble** (FAIL)

- tire `fl`: 0.0 mm to `body.well`, turns 0 degrees before it touches `body.well`, its foot -7.0 mm off the ground
- tire `rl`: 0.0 mm to `body.well`, its foot -7.0 mm off the ground
- tire `fr`: 0.0 mm to `body.well`, turns 0 degrees before it touches `body.well`, its foot -7.0 mm off the ground
- tire `rr`: 0.0 mm to `body.well`, its foot -7.0 mm off the ground
- not mirrored: `interior.fittings` 160.0 mm, `luggage.case` 113.6 mm, `luggage.straps` 99.7 mm, `luggage.bag` 74.3 mm, `led.cabin` 5.4 mm
- open ends of open pieces (meant): `liner.liner`
- a cutter's hole inside `body.front`: 751 mm round, at (1.357, -0.332, 0.439)
- a cutter's hole inside `body.front`: 559 mm round, at (0.519, 0.772, 0.352)
- a cutter's hole inside `body.front`: 751 mm round, at (1.357, 0.332, 0.439)
- a cutter's hole inside `body.front`: 559 mm round, at (0.519, -0.772, 0.352)
- a cutter's hole inside `body.petal`: 503 mm round, at (0.18, -0.793, 0.623)
- a cutter's hole inside `body.petal`: 503 mm round, at (0.18, 0.793, 0.623)
- a cutter's hole inside `body.rear`: 751 mm round, at (-1.358, -0.331, 0.489)
- a cutter's hole inside `body.rear`: 751 mm round, at (-1.358, 0.331, 0.489)
- a cutter's hole inside `body.rear`: 559 mm round, at (-0.498, -0.771, 0.351)
- a cutter's hole inside `body.rear`: 559 mm round, at (-0.498, 0.771, 0.351)

**tanager_cab** (FAIL)

- tire `fl`: 1.4 mm to `bumper.guards.rear`, turns 0 degrees before it touches `bumper.guards.rear`, its foot -7.0 mm off the ground
- tire `rl`: 0.3 mm to `bumper.guards.rear`, its foot -7.0 mm off the ground
- tire `fr`: 1.4 mm to `bumper.guards.rear`, turns 0 degrees before it touches `bumper.guards.rear`, its foot -7.0 mm off the ground
- tire `rr`: 0.0 mm to `bumper.guards.rear`, its foot -7.0 mm off the ground
- not mirrored: `body.slider` 500.0 mm, `glass.door.r` 500.0 mm, `seal.door.r` 500.0 mm, `checker.band.door.r` 500.0 mm, `roundel.r` 458.2 mm, `roundel.number.r` 392.9 mm, `lettering.door.r` 353.0 mm, `step.light` 286.4 mm, `step` 285.1 mm, `step.ribs` 257.8 mm, `body.sclad` 230.8 mm, `checker.molded.door.r` 188.9 mm and 27 more
- open edge: `body.clad`, 1759 mm, at (0.01, 0.907, 0.42)
- open edge: `body.roof`, 1260 mm, at (0.011, 0.814, 1.653)
- open edge: `body.fender`, 1110 mm, at (0.641, 0.878, 1.055)
- open edge: `body.quarter`, 1110 mm, at (-0.621, 0.878, 1.055)
- cabin part in the open: `interior.card.l`, 21% of it, up to 37.0 mm from what would hide it, at (-0.656, 0.952, 0.326)

**tanager_mino** (look)

- not mirrored: `interior.wheel` 193.7 mm, `interior.screens` 93.6 mm, `antenna` 58.4 mm, `tow.eye` 48.6 mm, `wipers` 25.8 mm, `body.fender` 14.0 mm, `display.front` 10.0 mm, `display.rear` 10.0 mm, `permit` 10.0 mm, `permit.text` 7.2 mm, `permit.mark` 7.2 mm, `pixels.front` 4.0 mm

**tanager_porter** (FAIL)

- tire `fl`: 0.0 mm to `interior.tub`, turns 0 degrees before it touches `interior.tub`, its foot -7.0 mm off the ground
- tire `rl`: 53.0 mm to `body.well`, its foot -7.0 mm off the ground
- tire `fr`: 0.0 mm to `interior.tub`, turns 0 degrees before it touches `interior.tub`, its foot -7.0 mm off the ground
- tire `rr`: 53.0 mm to `body.well`, its foot -7.0 mm off the ground
- not mirrored: `interior.seats` 500.0 mm, `interior.belts` 386.7 mm, `seal.door.r` 356.7 mm, `roundel.r` 356.6 mm, `body.slider` 355.3 mm, `glass.door.r` 354.1 mm, `interior.wheel` 350.9 mm, `locker.hatch.open` 332.5 mm, `lettering.door.r` 312.9 mm, `locker.hatch.liner` 306.3 mm, `roundel.number.r` 294.2 mm, `body.sclad` 254.0 mm and 75 more
- open edge: `body.quarter`, 1370 mm, at (0.313, 0.918, 1.133)
- open edge: `body.fender`, 1343 mm, at (1.171, 0.918, 1.126)
- open edge: `body.roof`, 968 mm, at (0.69, 0.881, 1.906)
- open edge: `body.clad`, 265 mm, at (0.329, 0.938, 0.475)
- open edge: `body.clad`, 263 mm, at (1.171, 0.939, 0.469)
- cabin part in the open: `interior.liner`, 25% of it, up to 91.8 mm from what would hide it, at (-2.599, -0.854, 2.226)
- cabin part in the open: `interior.tub`, 9% of it, up to 63.6 mm from what would hide it, at (2.144, -0.898, 0.202)
- cabin part in the open: `interior.card.l`, 25% of it, up to 35.5 mm from what would hide it, at (0.274, 0.975, 0.336)
- cabin part in the open: `interior.rails`, 35% of it, up to 17.6 mm from what would hide it, at (0.38, 0.816, 2.0)
- cabin part in the open: `interior.mat`, 25% of it, up to 7.9 mm from what would hide it, at (-2.61, -0.85, 0.773)

**vanta_r** (look)

- tire `fl`: 12.8 mm to `body.well`, turns 0 degrees before it touches `body.well`
- tire `rl`: 17.8 mm to `body.well`
- tire `fr`: 12.8 mm to `body.well`, turns 0 degrees before it touches `body.well`
- tire `rr`: 17.8 mm to `body.well`
- not mirrored: `interior.wheel` 149.6 mm, `interior.screens` 68.8 mm, `wiper` 19.7 mm, `wiper.blade` 9.5 mm, `body.lightband` 4.5 mm


## Show colors

The palette each car's script gives the kit (a finish as a name or as metallic, roughness, coat; the second color is the kit's default red where a car sets none). A new design picks a color no car here has.

| Car | Paint | Finish | Second color | Finish |
|---|---|---|---|---|
| aurel_prelate | (0.04, 0.00, 0.01) | (0.1, 0.08, 1.0) | (0.45, 0.05, 0.03) | gloss |
| aurel_regent | (0.04, 0.01, 0.07) | (0.1, 0.08, 1.0) | (0.45, 0.05, 0.03) | gloss |
| aurel_zenith | (0.01, 0.01, 0.01) | (0.1, 0.08, 1.0) | (0.45, 0.05, 0.03) | gloss |
| brakk_bastion | (0.01, 0.04, 0.24) | (0.0, 0.4, 0.5) | (0.04, 0.04, 0.04) | (0.35, 0.52, 0.0) |
| brakk_hauler | (0.78, 0.33, 0.01) | (0.0, 0.4, 0.5) | (0.04, 0.04, 0.04) | (0.35, 0.52, 0.0) |
| brakk_mule | (0.12, 0.14, 0.04) | (0.0, 0.42, 0.4) | (0.04, 0.04, 0.04) | (0.35, 0.52, 0.0) |
| halcyon_ridge | (0.50, 0.09, 0.01) | (0.62, 0.3, 1.0) | (0.42, 0.07, 0.01) | (0.55, 0.55, 0.0) |
| halcyon_sable | (0.01, 0.04, 0.30) | (0.6, 0.3, 1.0) | (0.45, 0.05, 0.03) | gloss |
| kestrel_atlas | (0.17, 0.21, 0.06) | pearl | (0.03, 0.03, 0.04) | satin |
| kestrel_dart | (0.64, 0.67, 0.70) | pearl | (0.03, 0.03, 0.04) | satin |
| kestrel_meridian | (0.01, 0.04, 0.25) | pearl | (0.03, 0.03, 0.04) | satin |
| orrin_aria | (0.01, 0.01, 0.01) | (0.8, 0.3, 0.9) | (0.45, 0.05, 0.03) | gloss |
| orrin_lumen | (0.01, 0.09, 0.09) | (0.72, 0.36, 0.7) | (0.45, 0.05, 0.03) | gloss |
| orrin_pebble | (0.10, 0.03, 0.20) | (0.72, 0.36, 0.7) | (0.45, 0.05, 0.03) | gloss |
| tanager_cab | (0.37, 0.00, 0.16) | gloss | (0.80, 0.78, 0.72) | gloss |
| tanager_mino | (0.70, 0.05, 0.03) | gloss | (0.80, 0.78, 0.72) | gloss |
| tanager_porter | (0.07, 0.56, 0.37) | gloss | (0.80, 0.78, 0.72) | gloss |
| vanta_r | (0.15, 0.16, 0.18) | metallic | (0.45, 0.05, 0.03) | gloss |
