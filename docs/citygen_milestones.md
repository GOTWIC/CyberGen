# Stage 1 milestone log (layoutgen, `citygen`)

The full record of every stage 1 milestone, for the sessions that build and validate them. The
root [README](../README.md) has the short version. Spec: [`citygen_scope.md`](citygen_scope.md).
Implementation notes: `CLAUDE.md` (one section per milestone) and each
`docs/progress/<milestone>/README.md`.

## Milestones

| Milestone | What it adds | Status | Outputs |
|---|---|---|---|
| M0 | Spec format, district presets, `citygen` skill, schematic | Done | [`docs/progress/M0`](progress/M0) |
| M1a | Coast, rivers, deltas, islands, districts, canals, `citygen build` | Done | [`docs/progress/M1a`](progress/M1a) |
| M1a2 | Organic polish: curved districts, meandering water, real deltas | Done | [`docs/progress/M1a2`](progress/M1a2) |
| M1b | Highways, avenues, bridges, megasite reserves | Done | [`docs/progress/M1b`](progress/M1b) |
| M1b_det | Same city byte for byte on x86 and ARM, stage traces | Done | [`docs/progress/M1b_det`](progress/M1b_det) |
| M2 | Local streets, alleys, junctions, sidewalks, blocks, lots, open space | Done | [`docs/progress/M2`](progress/M2) |
| M3 | Buildings, complexes, skybridges, landmarks, megasites | Done | [`docs/progress/M3`](progress/M3) |
| M3p | Polish: megablocks as towers on podiums, complexes in place, canal straddles, boulevard skylines | Done | [`docs/progress/M3p`](progress/M3p) |
| M4 | Blender blockout (.blend, USD, glTF tiles), renders, labeled 2D map, Unreal and graph exports | Done | [`docs/progress/M4`](progress/M4) |
| M5 | Transit: metro, elevated rail, monorail, maglev, sky tubes through towers; stations, supports, station walkways | Done | [`docs/progress/M5`](progress/M5) |
| M6 | Props, vegetation, ground clutter (instanced in the blockout) | Done | [`docs/progress/M6`](progress/M6) |
| M7a | Elevated highways: viaducts, diamond ramps, overpasses, bridge approach grades, underpass streets, road columns | Done | [`docs/progress/M7`](progress/M7) |
| M7b | Trumpet and partial cloverleaf interchanges, art-direction loop, Corporate Core pinned import | Done | [`docs/progress/M7b`](progress/M7b) |
| M8a | Robustness sweep (`citygen sweep`, 68 builds at many seeds) and the fixes it led to: 33 to 49 of 68 builds passing (57 apart from transit), no crashes | Done | [`docs/progress/M8a`](progress/M8a) |
| M8b | Transit loops as one simple ring, stations in route order, lines independent of each other, `transit_self_crossing` check; fast lines placed so their curves fit, faster transit routing; on M8a's code the sweep passes 51 of 68 builds (M8a alone 49) | Done | [`docs/progress/M8b`](progress/M8b) |
| M8c | Transit that passes on a city's first layout: flying loops as Dubins rings, open lines off the roads or as Dubins paths where the roads fail them; Delta Megacity from 9 full-city tries to 1, the sweep 58 of 68 (M8b 51), no transit failures left in it | Done | [`docs/progress/M8c`](progress/M8c) |
| M8d | Trumpet in its textbook form: one loop and one level-2 flyover round it (crest 16.6 m in Vesper Bay, then Nyxllor), the two-loop form as the fallback; the sweep passes 51 of 68 builds as before, all five trumpets in it take the flyover, the 63 builds without one are byte-identical | Done | [`docs/progress/M8d`](progress/M8d) |
| M9 | Tunnels as level -1 of the road network: cut-and-cover tunnels under districts and immersed tubes under water (portals, walled approaches, ventilation buildings), metro tunnels lowered under foundations and road tunnels, pedestrian underpasses; four tunnel checks (70 in all), tunnel boxes and a cutaway render in the blockout; Nexus City gets the Midtown Tunnel, Greyhook the Neckwater Tube; the sweep passes 58 of 68 as on M8c | Done | [`docs/progress/M9`](progress/M9) |
| M10 | Edit, lock and regenerate: stable ids from what an entity is and where it sits, `citygen build --district` regenerates one district in under a minute with every road outside it held and everything away from its seam byte for byte, pins and overrides (`overrides.json`), `citygen lock` releases that rebuild byte for byte, `citygen model diff` with a map | Done | [`docs/progress/M10`](progress/M10) |
| M11 | Gameplay layer: named points of interest (bars, clinics, vendors, fixers, hideouts, apartments) with their doors, faction territories and police precincts, wealth, danger and police fields, traffic, crowd and spawn density per street and hour band, parking, taxi stands, fast travel, sign and ad slots; every place reachable on foot and by car (9 checks, 75 in all), `gameplay.json` | Done | [`docs/progress/M11`](progress/M11) |
| M12 | Stack interchanges: four-level highway-highway crossings (one highway lifted through the crossing, eight one-way directional ramps, the left turns as flyovers at 18 and 27 m), the turbine as their fallback, M7's crossing where neither fits; 2 checks (81 in all); a stack demo (the pinned demo with two crosstowns), the samples and the pinned demo unchanged | Done | [`docs/progress/M12`](progress/M12) |
| M13 | Terrain: hills, ridges and cliffs; roads, lots and buildings on slopes; tunnels through hills | In progress | |
| M14 | Layered districts: streets, lots and buildings stacked on several deck levels, joined by ramps, stairs and elevators | Planned | |
| M15 | Unreal export tool (end of stage 1): a built city into an Unreal 5.8 World Partition level with collision, materials, instanced props, ids and graphs; updated as later stages come online | In progress | |

## Outputs

Each M10 city folder has every generator preview, the build report, the stage trace, the 8K whole-city render and the release lock (`city.lock.json`), and `docs/progress/M10/regenerated/` a regenerated district of every sample with its diff map; each M12 city folder has every generator preview, the build report, the stage trace and the 8K whole-city render (the stack demo also its stack close-up); each M9 city folder has every generator preview (`preview_tunnels.png` where a city has tunnels), the build report, the stage trace and the 8K renders, the cutaways among them; each M11 city folder the same on M8c without tunnels; each M8c city folder has every generator preview, the transit map of M8b, the Blender
renders, the build report and the stage trace, and `docs/progress/M8c/same_layout/` the
transit of M8b and M8c on the same saved layouts; the M8d builds (the trumpet) are in
`docs/progress/M8d/`, the M8b ones in `docs/progress/M8b/`, the M8a sweep tables in
`docs/progress/M8a/`, the M7b builds in `docs/progress/M7b/`, the M7a ones in
`docs/progress/M7/`, the 2D maps in `docs/progress/M4/`. Sample specs live in
`docs/progress/M1a2/<city>/city_spec.json` and `cities/vesper_bay/city_spec.json`; the pinned
demo's in `cities/vesper_bay_pinned/city_spec.json` (first in
`docs/progress/M7b/nyxllor_pinned/`), its round 1 and round 2 transit in
`docs/progress/M8b/nyxllor_pinned_round1/` and `nyxllor_pinned_round2/`. `docs/progress/M8c/vesper_bay*/`
are the same layouts as `nyxllor*/` there, built again under the new name.

While a milestone session runs, it pushes snapshot images to its branch under
`docs/progress/<milestone>/wip/`; open the branch on GitHub (Branches tab) to see them before
the PR is up.

## Commands

```
.venv/bin/python -m citygen build SPEC OUT [--blockout] [--trace FILE]
.venv/bin/python -m citygen build SPEC OUT --district "Neon Strand"      # regenerate one district (M10)
.venv/bin/python -m citygen model diff A/city_model.json B/city_model.json --png diff.png
.venv/bin/python -m citygen lock OUT --release 1.0                       # freeze a release
.venv/bin/python -m citygen lock --verify OUT/city.lock.json             # rebuild it byte for byte
.venv/bin/python -m citygen rerender OUT iso_city --to DIR               # 8K renders
.venv/bin/python -m citygen sweep --suite m8a --out DIR                  # robustness sweep
.venv/bin/python -m citygen review OUT --spec S --prev P                 # art-direction round
```

Pins and overrides go in `overrides.json` beside the spec (see `docs/progress/M10`).
