# AG18's vehicle packs in Unreal Engine 5.8

The first import of the game packs (`vehicles/GAME.md`) into Unreal, on the M4 Mac
(2026-11-11), through the exporter's vehicle library and placement entries
(`docs/unreal_export.md`, "AG18's vehicles").

## What was run

- **The packs:** seven of the 18 (the cases the contract has to cover): `vanta_r` (a standard
  wheeled car with brake calipers), `brakk_mule` (a large six-wheeled truck), `kestrel_dart`
  (a hover car: no wheels), `tanager_mino` (wheel covers), `aurel_prelate` (mirror-smooth
  paint, wheel covers, a glass roof), `orrin_aria` (a glass canopy of lower IOR) and
  `halcyon_ridge`.
- **The build:** a line-up of its own (no city: one 256 m tile of flat ground and a backdrop
  wall, written without Blender through the exporter's glTF writer) with a contribution of
  placement entries: three rows of the seven in their show colors and two other paint sets
  (pearl, black and cyan; magenta, graphite and lime), four Minos in one component each in
  its own paint, a bay per car for its pack's hero camera, and a Vanta-R with its front wheels
  steered 25 degrees.
- **The project:** a throwaway one from the First Person template, outside the repo.

```bash
.venv/bin/python -m citygen unreal BUILD PROJECT.uproject --no-play --no-hlod --no-atmos
.venv/bin/python -m citygen unreal BUILD PROJECT.uproject --check-only --check-vehicles --shots DIR
```

## Results

RESULTS

## Shots

| | |
|---|---|
| ![](lineup_day.jpg) | the line-up by day: show colors at the front, then two other paint sets, from the same meshes and material instances (the paint is per-instance custom data) |
| ![](lineup_night.jpg) | the same by night (`MPC_CityGen`'s Night, a dim sun, the night's fixed exposure): lamps, light strips and wheel rings glow |
| ![](parking_one_model_four_paints.jpg) | four Minos, one instanced component per part, each instance its own paint |
| ![](hero_vanta_r_vs_proof.jpg) | the Vanta-R from its pack's hero camera beside the pack's proof (Cycles) |
| ![](hero_orrin_aria_vs_proof.jpg) | the Aria: its canopy (IOR 1.14) thin translucent |
| ![](hero_aurel_prelate_vs_proof.jpg) | the Prelate: mirror-smooth paint, its glass roof dark as in the proof |
| ![](heroes_day.jpg) | the Mule, the Dart, the Mino and the Ridge by day |
| ![](heroes_night.jpg) | four by night |
| ![](lods_orrin_aria.jpg) | the Aria at LOD0 to LOD3, each forced: from LOD2 the glass dark and opaque, no cabin |
| ![](lods_aurel_prelate.jpg) | the Prelate at LOD0 to LOD3 |
| ![](wheel_spin_steer.jpg) | a front wheel at rest and spun 40 degrees about its axle and steered 25 degrees by script: it turns about its pivot, the caliper steers with it and does not spin |
| ![](hulls_brakk_mule.jpg) | the Mule and its collision hulls, drawn from the pack's `collision.glb` in place of its body |
