# AG18: hero vehicles

Twenty-one vehicles designed by hand, one Blender script each (`vehicles/cars/`), on a shared
kit (`vehicles/carkit.py`). Seven made-up brands, three models each; a brand is a design
language in geometry and texture, never in color (`vehicles/BRANDS.md`). Scope and the plan
for what comes next: `docs/assetgen_scope.md`, 14.19. Each folder holds one 4K multi-view
sheet and the car's notes, and, for the 18 cars with a game pack, its proof (`game.jpg`) and
report (`game_report.json`); the pack itself is built by `vehicles/game.py` outside git
(format: `vehicles/GAME.md`).

![line-up](lineup.jpg)

The whole roster at one scale (`vehicles/blender.sh vehicles/lineup.py`).

| Brand | Model | Type | Seats | Length | Sheet | Game pack |
|---|---|---|---|---|---|---|
| Halcyon | Vanta-R | mid-engined supercar | 2 | 4.69 m | [vanta_r](vanta_r/sheet.jpg) | [proof](vanta_r/game.jpg) |
| Halcyon | Sable | four-door fastback grand tourer | 4 | 5.11 m | [halcyon_sable](halcyon_sable/sheet.jpg) | [proof](halcyon_sable/game.jpg) |
| Halcyon | Ridge | performance crossover | 4 | 4.75 m | [halcyon_ridge](halcyon_ridge/sheet.jpg) | [proof](halcyon_ridge/game.jpg) |
| Kestrel Aerodyne | Dart | hover coupe | 2 | 4.66 m | [kestrel_dart](kestrel_dart/sheet.jpg) | [proof](kestrel_dart/game.jpg) |
| Kestrel Aerodyne | Meridian | hover sedan | 4 | 5.32 m | [kestrel_meridian](kestrel_meridian/sheet.jpg) | [proof](kestrel_meridian/game.jpg) |
| Kestrel Aerodyne | Atlas | hover hauler with a load bed | 2 | 5.91 m | [kestrel_atlas](kestrel_atlas/sheet.jpg) | [proof](kestrel_atlas/game.jpg) |
| Orrin | Lumen | sedan under one leaf of glass | 4 | 5.03 m | [orrin_lumen](orrin_lumen/sheet.jpg) | [proof](orrin_lumen/game.jpg) |
| Orrin | Pebble | city pod, the dome lifts as the door | 2 | 2.82 m | [orrin_pebble](orrin_pebble/sheet.jpg) | [proof](orrin_pebble/game.jpg) |
| Orrin | Aria | hypercar with channels through the body | 2 | 4.74 m | [orrin_aria](orrin_aria/sheet.jpg) | [proof](orrin_aria/game.jpg) |
| Brakk Industrial | Hauler | crew cab pickup, exposed wheels | 4 | 5.69 m | [brakk_hauler](brakk_hauler/sheet.jpg) | [proof](brakk_hauler/game.jpg) |
| Brakk Industrial | Bastion | armored utility vehicle | 4 | 5.11 m | [brakk_bastion](brakk_bastion/sheet.jpg) | [proof](brakk_bastion/game.jpg) |
| Brakk Industrial | Mule | six-wheel cargo van | 2 | 6.65 m | [brakk_mule](brakk_mule/sheet.jpg) | [proof](brakk_mule/game.jpg) |
| Aurel | Prelate | formal coupe | 2 + 2 | 5.19 m | [aurel_prelate](aurel_prelate/sheet.jpg) | [proof](aurel_prelate/game.jpg) |
| Aurel | Regent | limousine | 4 | 5.92 m | [aurel_regent](aurel_regent/sheet.jpg) | [proof](aurel_regent/game.jpg) |
| Aurel | Zenith | hover grand tourer on a skirt of light | 4 | 5.42 m | [aurel_zenith](aurel_zenith/sheet.jpg) | [proof](aurel_zenith/game.jpg) |
| Vex | Wraith | open-wheel speedster of four pods | 2 | 4.37 m | [vex_wraith](vex_wraith/sheet.jpg) | to be redesigned, no pack |
| Vex | Halo | roadster on four hubless ring wheels | 2 | 4.31 m | [vex_halo](vex_halo/sheet.jpg) | to be redesigned, no pack |
| Vex | Strix | tandem track hypercar, floating fenders | 2 | 4.97 m | [vex_strix](vex_strix/sheet.jpg) | to be redesigned, no pack |
| Tanager | Mino | city car | 4 | 3.43 m | [tanager_mino](tanager_mino/sheet.jpg) | [proof](tanager_mino/game.jpg) |
| Tanager | Cab | driverless taxi with a sliding door | 4 | 4.55 m | [tanager_cab](tanager_cab/sheet.jpg) | [proof](tanager_cab/game.jpg) |
| Tanager | Porter | parcel-locker delivery van | 2 | 5.30 m | [tanager_porter](tanager_porter/sheet.jpg) | [proof](tanager_porter/game.jpg) |

**In the cities** (step H): `assetgen vehicles BUILD` (also part of `assetgen build`) parks
the packs in a generated city in place of AG8's parked car variants: a model by its
district's archetype, wealth and danger, painted per placement, wherever its footprint fits
its parking lane (`assetgen/parked/`). Vesper Bay, its 912 parked cars as 17 models, in
Blender and Unreal: [`city/`](city/README.md).

**Lamps, cut lines and glass** (step B, in progress): lamps in channels and housings under
lenses, shut lines, handles and flaps cut through the skin, black frit borders on the glass;
the Vanta-R first ([`vanta_r`](vanta_r/README.md)), then the [Dart](kestrel_dart/README.md), [Lumen](orrin_lumen/README.md), [Hauler](brakk_hauler/README.md) and [Mino](tanager_mino/README.md), the [Sable](halcyon_sable/README.md) and [Ridge](halcyon_ridge/README.md); the other eight next (the Aurels are set aside for now).

**What the kit's checks find** (step A): [`checks.md`](checks.md), a table of every car's
tire and ground clearances, symmetry, panel edges, cabin parts in the open and triangles,
and each car's `clay.jpg` and `zebra.jpg` beside its sheet (`python vehicles/survey.py
--docs`).

Each car's own README lists its size, its design, its brand's cues, what its designer would
improve and what the kit lacked for it. The packs' numbers per car (triangles per LOD, size
class, pack size, checks): `docs/assetgen_milestones.md`, AG18, phase 3.
