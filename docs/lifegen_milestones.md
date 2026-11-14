# Stage 4 milestone log (lifegen)

The full record of every stage 4 milestone, for the sessions that build and validate them. The
root [README](../README.md) has the short version. Spec: [`lifegen_scope.md`](lifegen_scope.md)
(what each milestone adds: section 13; Swagnik's decisions: section 12). Each milestone's entry
grows here as it lands, as in [`citygen_milestones.md`](citygen_milestones.md),
[`assetgen_milestones.md`](assetgen_milestones.md) and
[`atmosgen_milestones.md`](atmosgen_milestones.md).

## Milestones

| Milestone | What it adds | Status | Outputs |
|---|---|---|---|
| LG0 | Groundwork and spike: the life spec and styles, the plan format and schemas, `lifegen plan` (people and vehicles by district and hour, spawn and sink points, place slots, the fleet from AG18's roster, the asks of citygen), the `CityGenLife` plugin's skeleton (ZoneGraph lanes built from the graphs, Mass processors) built by the exporter; plain stand-ins and a few of AG18's cars on one district of Delta, against the benchmark; probes of MetaHuman, Mutable, retargeting and the engine pieces' maturity in 5.8; a tee draped in Blender's cloth solver | Done | [`docs/progress/LG0`](progress/LG0) |
| LG1 | People | Planned | |
| LG2 | Clothing | Planned | |
| LG3 | Crowds on the streets | Planned | |
| LG4 | Life at places | Planned | |
| LG5 | Traffic | Planned | |
| LG6 | Transit | Planned | |
| LG7 | Air and water | Planned | |
| LG8 | Weather, reactions and release | Planned | |

## LG0: groundwork and spike

Built on the Windows PC (2026-11-13), on main after AT7, the play fixes and the showcase
(#221). Report, measurements, probe findings and recommendations for LG1 to LG8:
[`docs/progress/LG0/README.md`](progress/LG0/README.md).

- **Decisions** (scope section 12, Swagnik 2026-11-13): a generator of the plan and a library
  with the `CityGenLife` plugin on Mass, ZoneGraph, Smart Objects and StateTree; MetaHuman
  bodies made by script into the project if 5.8 allows it; generated garments with a kit
  out of the repo as the fallback; Epic's Game Animation Sample near the view and free
  mocap libraries for the rest; nothing in the repo unless anyone may use it; **the fleet is
  AG18's hand-designed vehicles**, the missing kinds designed on the Mac (changed); **a
  20 ms p95 frame budget** at native 1440p, no tuning rounds unless a milestone goes over
  (changed); stepping aside and looking first, fleeing and gathering later.
- **Spec and presets** (`lifegen/spec.py`, `presets.py`, `lifegen/schemas/life_spec.schema.json`;
  `python -m lifegen spec validate|schema`): per district its people (busy, residents,
  workers and visitors, the day's shape within M11's hour bands), its style (fashion groups,
  cyberware, wear, pulled by wealth and danger), its fleet (AG18's models by the parked
  cars' table, `assetgen/parked/table.py`, times the spec's multipliers), transit headways,
  air and water, budgets, reactions, the spike.
- **Plan format** (`lifegen/planmodel.py`, `lifegen/schemas/`): `life_plan.json`,
  `spawns/<tile>.json` (spawn points with rates by hour, place slots),
  `unreal_contribution.life.json` (layer 4), each entry hashed.
- **The plan** (`lifegen plan BUILD`, `plan.py`): Delta in 2 to 3 s: 6,789 spawn points
  (building entrances, station stairs, garages, taxi stands), 688 place slots (benches, bus
  stops, kiosks, vending machines, stalls, taxi stands) in 131 tiles; 58,189 people and
  3,394 vehicles on the streets at the peak hour; checks (spawns on the graphs, every spawn
  reaching another, densities kept to M11's within 1%, slots facing, the spike within the
  budget); `preview_crowds.png`.
- **The asks of citygen** (`lifegen/asks.py`): signal phases and timing, bus routes, turn
  restrictions, lobby points, piers, air corridors; of assetgen the doors (met by AG3) and
  AG18's missing kinds. Each with the record asked for, its state on a model and what the
  plan does meanwhile.
- **Runtime** (`citygen/ue/CityGenLife`): the controller builds ZoneGraph lanes from the
  spike's walkways and lanes at BeginPlay (an `AZoneGraphData` of its own, its BV-tree built
  in the plugin), makes people and cars Mass entities and moves them with two dynamic Mass
  processors, draws stand-ins and AG18's car parts as instanced meshes; console
  `CityGenLife.Enable|Respawn|Status`.
- **Exporter** (`citygen/unreal_life.py`, `import_city.Importer.life_controller`,
  `--life DIR`, `--no-life`): the manifest's `life`, `BUILD/unreal/life.json`, the
  controller placed with the spike, the stand-in material made by the import;
  `docs/unreal_export.md`, "lifegen's runtime (LG0)".
- **Spike** (Delta's Old Town at 23:00, 2,000 stand-ins within 450 m of its middle and
  densest round it, 40 cars of nine models; 11,340 ZoneGraph lanes built in 14 to 30 ms):
  the lean benchmark's `night_plan_all` 15.1 to **16.6 ms p95** (walk 14.9 to 16.6), under
  the 20 ms budget; the game thread about +2.5 ms at the walk's p95 (the controller's own
  tick 1.0 to 1.8 ms), the GPU +0.6 ms. The first build recreated the instances' render
  state every frame and left them in Lumen's scene: walk 26.3 ms, 8 to 9 ms of it Lumen's
  scene update; both are off now (`bInLumen`, `bRebuildRenderState`), with the benchmark's
  `night_life*` passes to measure them. The package `builds/packaged/Delta_lg0` launches
  with the spike.
- **Probes** (`lifegen/probes/`): the engine pieces' maturity in 5.8 (ZoneGraph, Mass
  Gameplay, Mass Crowd, MetaHuman Crowd, AnimToTexture, Chaos Vehicles experimental; Mutable
  and MetaHuman Creator beta; Smart Objects, StateTree, Pose Search, IK Rig, Chaos Cloth
  released); MetaHuman Creator creates and edits bodies from Python but cannot build one
  without Epic's cloud rigging (sign-in and EULA) and its skin without the optional
  content; Mutable has no Python graph editing; a CMU-style clip retargets onto the
  mannequin by script (its chains set by script).
- **Garment test** (`lifegen/blender/garment_test.py`): a tee of two flat panels sewn and
  draped on a plain body headless in 13.5 s, its seams closed to 0.9 cm on average, baked
  and rendered.
- **Tests** (`tests/lifegen/test_lg_plan.py`; `test_no_network.py` reads lifegen;
  `test_unreal_play.py` the third plugin).
