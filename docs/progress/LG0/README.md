# LG0: groundwork and spike (lifegen)

Stage 4's first milestone (`docs/lifegen_scope.md` section 13): the contract (the life spec
and styles, the plan's format, the asks of citygen, the `CityGenLife` plugin's skeleton built
by the exporter, ZoneGraph lanes built from the city's own graphs), a spike on one district
of Delta Megacity measured against the benchmark, probes of what Unreal 5.8 lets a script do
for people (MetaHuman, Mutable, retargeting, the engine pieces' maturity) and a garment
draped in Blender's cloth solver. Built on the Windows PC (RTX 4070 Ti, 32 GB, UE 5.8) on
2026-11-13, on main after AT7, the play fixes and the showcase (#221).

Swagnik's decisions of 2026-11-13 (scope section 12) set the frame: a generator of the plan
and a library with the `CityGenLife` plugin on Mass, ZoneGraph, Smart Objects and StateTree;
MetaHuman bodies if 5.8 can be driven from a script; generated garments with a kit out of the
repo as the fallback; Epic's Game Animation Sample near the view and free mocap for the rest;
nothing in the repo unless anyone may use it; **the fleet is AG18's hand-designed vehicles**;
**a 20 ms p95 frame budget** with no tuning rounds unless a milestone goes over it; stepping
aside and looking first.

## What LG0 built

| Part | Where | What |
|---|---|---|
| Life spec and presets | `lifegen/spec.py`, `presets.py`, `schemas/life_spec.schema.json` | per district its people (busy, residents, workers, visitors, the day's shape within M11's hour bands), style (fashion groups, their colors, cyberware, wear by wealth and danger), fleet (AG18's models by the parked cars' table); transit, air, water, budgets (20 ms p95, 2,000 people and 500 vehicles within 300 m), reactions, the spike |
| Plan format | `lifegen/planmodel.py`, `schemas/life_plan.schema.json`, `tile_spawns.schema.json`, `contribution.schema.json` | `life_plan.json`, `spawns/<tile>.json`, `unreal_contribution.life.json` (layer 4), every entry hashed |
| The plan | `lifegen plan BUILD`, `lifegen/plan.py` | people, vehicles, gang members and police per district and hour; spawn and sink points with rates by hour; place slots; the spike; checks; `preview_crowds.png` |
| Asks of citygen | `lifegen/asks.py` | signal phases and timing, bus routes, turn restrictions, lobby points, piers, air corridors (and of assetgen: doors, met; AG18's missing kinds) |
| Runtime plugin | `citygen/ue/CityGenLife` | the controller: ZoneGraph lanes from the graphs, people and cars as Mass entities moved by two Mass processors, instanced stand-ins and AG18's car parts |
| Exporter | `citygen/unreal_life.py`, `import_city.Importer.life_controller`, `--life`, `--no-life` | the manifest's `life`, `BUILD/unreal/life.json`, the controller placed with the spike, the stand-in material |
| Probes | `lifegen/probes/plugins.py`, `ue_probe.py`, `cmu_style.py` | the engine pieces' maturity; MetaHuman Creator, Mutable and retargeting from Python |
| Garment test | `lifegen/blender/garment_test.py` | a tee of two flat panels sewn and draped on a plain body, headless, baked, rendered |

## The plan on Delta

`lifegen plan` on Delta (the play fixes' build), an empty spec: 2 to 3 s, 131 tiles.

<!-- PLAN_TABLE -->

## The spike: Delta's Old Town in Unreal

<!-- SPIKE -->

## Probes

<!-- PROBES -->

## Garment test

<!-- GARMENT -->

## Recommendations for LG1 to LG8

<!-- RECS -->
