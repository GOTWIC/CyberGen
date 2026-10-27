# Stage 2 milestone log (assetgen)

The full record of every stage 2 milestone, for the sessions that build and validate them. The
root [README](../README.md) has the short version. Spec: [`assetgen_scope.md`](assetgen_scope.md)
(what each milestone adds and when it is done: section 14). Nothing is built yet; each
milestone's entry grows here as it lands, as in [`citygen_milestones.md`](citygen_milestones.md).

## Milestones

| Milestone | What it adds | Status | Outputs |
|---|---|---|---|
| AG0 | Contract and spike: package `assetgen/`, asset spec and skill, a brief and hash per building, manifest in M15's format, glTF writer, triangulator; three generated buildings in Unreal 5.8 to measure Nanite size, import time and Lumen cost | Planned | |
| AG1 | Building shells: genomes, the facade grammar with six facade systems, walls with window openings, slabs, parapets, proxies; `assetgen build` keeps unchanged assets; Blender previews | Planned | |
| AG2 | Facades: windows, balconies, fins and panels as parts instanced within a building, every facade system, massing articulation, wear by grime and wealth | Planned | |
| AG3 | Street fronts: a shopfront per unit by use, doors, lobbies, docks, garages, awnings, sign boxes, mounts, party and blind walls | Planned | |
| AG4 | Roofs and connections: roof equipment for every roof item, helipads, green roofs, facade details, skybridges, sky tube portals and stations | Planned | |
| AG5 | Types, landmarks and slopes: per-type generators, complex families, hero landmarks, buildings on M13's slopes, the art-direction loop | Planned | |
| AG6 | Materials and textures: the shared library per era, trim sheets, decals, window interiors, signage atlases, per-building parameters | Planned | |
| AG7 | Street elements: roads with markings, sidewalks, bridges, viaducts, interchanges, tunnels, quays, transit structures, megasite elements | Planned | |
| AG8 | Props, plants and signs: prop variants per district style, trees by species, neon signs, billboards, holo-ads | Planned | |
| AG9 | Unreal: the modelled city through M15's import with pivots, textured materials, simple collision, LODs, HLOD; a regenerated district end to end | Planned | |
| AG10 | Scale and release: every sample modelled, `assetgen sweep`, the Windows check, `assetgen lock` | Planned | |
| AG11 | Layered districts: buildings and streets on M14's decks | Planned (after M14) | |
| AG12 | Interiors for M11's places | Only if decision 13.6 asks | |

## Order

```
 AG0 ─┬─> AG1 ─> AG2 ─> AG3 ─> AG4 ─> AG5 ──┐
      │     └──> AG6 ───────────────────────┤
      ├─> AG7 ──────────────────────────────┼─> AG10 ─> AG11 (after M14), AG12 (if asked)
      └─> AG8 ──────────────────────────────┤
          AG3 + AG6 + M15 ──> AG9 ──────────┘
```

The building line (AG1 to AG5) is one session at a time; AG6, AG7 and AG8 can run beside it
as separate local sessions. AG0 only reads citygen, so it can start while M13 and M15 are
still open. Section 14.13 of the scope has the rules.

## Outputs

Each milestone's builds, previews and report go in `docs/progress/AG<n>/`; while a session
runs, it pushes snapshot images to its branch under `docs/progress/AG<n>/wip/`. Generated
assets are not in git.

## Commands (planned)

```
.venv/bin/python -m assetgen spec validate SPEC                          # asset spec (AG0)
.venv/bin/python -m assetgen brief BUILD [--diff OLD_BUILD]             # briefs and hashes (AG0)
.venv/bin/python -m assetgen build BUILD [--spec asset_spec.json]       # assets (AG1 on)
.venv/bin/python -m assetgen review BUILD --prev P                      # art-direction round (AG5)
.venv/bin/python -m citygen unreal BUILD PROJECT                        # imports the assets too (AG9)
.venv/bin/python -m assetgen sweep --suite m8a --out DIR                # (AG10)
.venv/bin/python -m assetgen lock BUILD --release 1.0                   # (AG10)
```
