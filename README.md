# Nyxllor

A Cyberpunk 2077-inspired open-city game in Unreal Engine 5. The city layout comes from
**citygen**: one text prompt (plus an optional concept image) becomes a complete, water-first
coastal city, built as deterministic offline Python and later as a Blender blockout and Unreal
map. No API calls anywhere: a Claude Code session turns the prompt into a spec through the
`citygen` skill, and everything after that is code.

Full plan: [`docs/citygen_scope.md`](docs/citygen_scope.md).

## Progress

| Milestone | What it adds | Status | Outputs |
|---|---|---|---|
| M0 | Spec format, district presets, `citygen` skill, schematic | Done | [`docs/progress/M0`](docs/progress/M0) |
| M1a | Coast, rivers, deltas, islands, districts, canals, `citygen build` | Done | [`docs/progress/M1a`](docs/progress/M1a) |
| M1a2 | Organic polish: curved districts, meandering water, real deltas | Done | [`docs/progress/M1a2`](docs/progress/M1a2) |
| M1b | Highways, avenues, bridges, megasite reserves | Done | [`docs/progress/M1b`](docs/progress/M1b) |
| M1b_det | Same city byte for byte on x86 and ARM, stage traces | Done | [`docs/progress/M1b_det`](docs/progress/M1b_det) |
| M2 | Local streets, alleys, junctions, sidewalks, blocks, lots, open space | Done | [`docs/progress/M2`](docs/progress/M2) |
| M3 | Buildings, complexes, skybridges, landmarks, megasites | Done | [`docs/progress/M3`](docs/progress/M3) |
| M3p | Polish: megablocks as towers on podiums, complexes in place, canal straddles, boulevard skylines | Done | [`docs/progress/M3p`](docs/progress/M3p) |
| M4 | Blender blockout (.blend, USD, glTF tiles), renders, labeled 2D map, Unreal and graph exports | Done | [`docs/progress/M4`](docs/progress/M4) |
| M5 | Transit: metro, elevated rail, monorail, maglev, sky tubes through towers; stations, supports, station walkways | Done | [`docs/progress/M5`](docs/progress/M5) |
| M6 | Props, vegetation, ground clutter (instanced in the blockout) | Done | [`docs/progress/M6`](docs/progress/M6) |
| M7a | Elevated highways: viaducts, diamond ramps, overpasses, bridge approach grades, underpass streets, road columns | Done | [`docs/progress/M7`](docs/progress/M7) |
| M7b | Trumpet and partial cloverleaf interchanges, art-direction loop, Corporate Core pinned import | Done | [`docs/progress/M7b`](docs/progress/M7b) |
| M8a | Robustness sweep (`citygen sweep`, 68 builds at many seeds) and the fixes it led to: 33 to 49 of 68 builds passing (57 apart from transit), no crashes | Done | [`docs/progress/M8a`](docs/progress/M8a) |
| M8b | Transit loops as one simple ring, stations in route order, lines independent of each other, `transit_self_crossing` check; fast lines placed so their curves fit, faster transit routing; on M8a's code the sweep passes 51 of 68 builds (M8a alone 49) | Done | [`docs/progress/M8b`](docs/progress/M8b) |
| M8c | Transit that passes on a city's first layout (Delta Megacity), remaining sweep transit failures | In progress (paused) | |
| M8d | Trumpet interchange with one loop and one flyover | In progress (paused) | |
| M9 | Tunnels: road tunnels and underwater crossings with portals, metro tunnel geometry, pedestrian underpasses | Planned | |
| M10 | Stack interchanges: four-level highway-highway crossings with directional flyovers | Planned | |
| M11 | Terrain: hills, ridges and cliffs; roads, lots and buildings on slopes; tunnels through hills | Planned | |
| M12 | Layered districts: streets, lots and buildings stacked on several deck levels, joined by ramps, stairs and elevators | Planned | |

## Latest maps (M8b)

Five sample cities are rebuilt and checked at every milestone, so quality is judged across
different coast forms, not one map. M8a swept them and the test specs over many seeds and
fixed what failed: highways that hooked along the map edge at exits, islands that did not
fit, islands cut off from the roads, level steps on loop roads and footbridges, side-by-side
duplicate roads, a crash (see [`docs/progress/M8a`](docs/progress/M8a)). M8b makes every
transit loop one simple ring through its stops in route order, places fast lines (maglev,
sky tube) so that their curves fit, and routes transit in about 3 to 13 s per city; on M8a's
code it takes nyxllor from 8 full-city tries to 1.

Whole cities in the Blender blockout, seen isometrically from the south (8K images; open one
for full size):

| Nexus City (from the concept image) | Nyxllor (bay, river delta) |
|---|---|
| <img src="docs/progress/M8b/nexus_city/render_iso_city.jpg" width="420"> | <img src="docs/progress/M8b/nyxllor/render_iso_city.jpg" width="420"> |

| Nyxllor with the traced Corporate Core on its island | Delta Megacity |
|---|---|
| <img src="docs/progress/M8b/nyxllor_pinned/render_iso_city.jpg" width="420"> | <img src="docs/progress/M8b/delta_megacity/render_iso_city.jpg" width="420"> |

| Saltreach Free Port (archipelago) | Greyhook (peninsula) |
|---|---|
| <img src="docs/progress/M8b/archipelago_free_port/render_iso_city.jpg" width="420"> | <img src="docs/progress/M8b/peninsula_city/render_iso_city.jpg" width="420"> |

The traced Corporate Core on its island (megatower, traced towers and water pockets):

<img src="docs/progress/M8b/nyxllor_pinned/render_iso_d01.jpg" width="840">

At street level, beside the viaducts:

| Delta Megacity, beside a viaduct | Nyxllor, corporate core |
|---|---|
| <img src="docs/progress/M8b/delta_megacity/render_street_4.jpg" width="420"> | <img src="docs/progress/M8b/nyxllor/render_street_4.jpg" width="420"> |

Road levels (Nyxllor): every raised road by deck height, the interchanges (a diamond, a
partial cloverleaf and a trumpet), columns, and the profile of one viaduct:

<img src="docs/progress/M8b/nyxllor/preview_elevated.png" width="840">

Props and plants at street level (Nyxllor, 180 m insets):

<img src="docs/progress/M8b/nyxllor/preview_props.png" width="840">

Transit maps (M8b): the Halo Line of the pinned demo in its first order, before M8b (it
doubles back through The Stacks and crosses itself) and now (one ring, stops numbered in
route order):

| Before M8b | M8b |
|---|---|
| <img src="docs/progress/M8b/nyxllor_pinned_round2/before_transit.png" width="420"> | <img src="docs/progress/M8b/nyxllor_pinned_round2/preview_transit.png" width="420"> |

| Nexus City | Nyxllor |
|---|---|
| <img src="docs/progress/M8b/nexus_city/preview_transit.png" width="420"> | <img src="docs/progress/M8b/nyxllor/preview_transit.png" width="420"> |

Each M8b city folder has every generator preview, the transit map before M8b, the Blender
renders, the build report and the stage trace; the M8a sweep tables are in
`docs/progress/M8a/`, the M7b builds in `docs/progress/M7b/`, the M7a ones in
`docs/progress/M7/`, the 2D maps in `docs/progress/M4/`. Sample specs live in
`docs/progress/M1a2/<city>/city_spec.json` and `cities/nyxllor/city_spec.json`; the pinned
demo's in `docs/progress/M7b/nyxllor_pinned/city_spec.json`, its round 1 and round 2 transit
in `docs/progress/M8b/nyxllor_pinned_round1/` and `nyxllor_pinned_round2/`.

## Where things are

- **Milestone outputs:** `docs/progress/<milestone>/<city>/` (preview images, reports, traces).
- **Work in progress:** while a cloud session runs, it pushes snapshot images to its branch under
  `docs/progress/<milestone>/wip/`. Open the branch on GitHub (Branches tab) to see them before
  the PR is up.
- **Generator:** `citygen/`, tests in `tests/`, skill in `.claude/skills/citygen/`.
- **Earlier hand-traced pipeline** (Corporate Core): `maps/`, `pipeline/`, `out/`, `unreal/`.

## Run it

```
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m citygen build cities/nyxllor/city_spec.json out/nyxllor --blockout
.venv/bin/python -m pytest -q
```

`--blockout` needs Blender 5.2 (found in `/Applications/Blender*.app`, `$BLENDER` or on PATH)
and adds `city.blend`, `city.usdc`, `tiles/*.glb`, renders and the 2D map to `out/nyxllor`.

To make a new city, open Claude Code in this repo and ask for one (the `citygen` skill takes it
from there).
