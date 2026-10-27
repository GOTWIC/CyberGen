# assetgen: unique building models, street elements and textures (scope, draft v0)

Stage 2 (assetgen) of CyberGen's five stages. A built citygen city in; a 3D model of its own
for every building, plus the street elements, props, plants and texture library the city
needs, out, ready for M15's Unreal import. Like citygen it is city-agnostic, offline and
deterministic. The decisions that need Swagnik before A1 starts are in section 13.

```
 citygen build (+ M10 lock)  ──>  city_model.json, city.lock.json
        │
        v
 [assetgen brief]   per building: everything it reads, hashed  ──>  briefs.json
        │                (unchanged hash = asset kept, so a regenerated
        │                 district rebuilds only its own assets and seam)
        v
 [assetgen build, offline deterministic Python]
        ├──> building assets (shell + generated parts + instances, proxy, collision)
        ├──> street assets per tile (roads, curbs, bridges, decks, quays, transit)
        ├──> prop and plant variant families
        ├──> texture and material library (shared by every city)
        └──> asset manifest (keyed by citygen id, content hashes)
        │
        ├──> Blender previews (district renders, street views, contact sheets)
        └──> M15 `citygen unreal`: replaces blockout meshes by id, Nanite on

 asset_spec.json (art direction, written by a Claude Code session through the
 `assetgen` skill from the city prompt; no API call)
```

## 1. Goal

- Input: a citygen build (the city model of M3 to M11, with M10's stable ids) and an
  optional asset spec (art direction per district, era, owner). Nothing modeled by hand.
- Output: for each of a city's roughly 6,000 buildings a model of its own, generated from its
  masses, floors, ground-floor units, entrances, roof items, skybridges, portals and its
  district's style: its own massing articulation, facade layout and rhythm, shopfronts,
  roofscape and wear. Plus road surfaces with markings, curbs, sidewalks, bridges, decks,
  ramps, columns, tunnels, quays and transit structures per tile; variant families for every
  M6 prop kind and every plant species; signs for every M11 sign slot; and the textures and
  materials all of them use.
- "Unique" means generated per building, not assembled from a fixed kit: the kit is code
  (part generators with parameters), not a set of meshes. How far uniqueness goes (shared
  tileable textures or unique ones, shared parts when their parameters coincide or none) is
  decision 13.2.
- Regenerating one district (M10's `citygen build --district`) regenerates only the assets of
  the buildings and street pieces whose inputs changed; everything else keeps its files and
  hashes byte for byte, and M15 re-imports only what changed.

## 2. Design principles

1. **No API calls, anywhere.** As in citygen: no network call in development or in the
   product, no LLM SDK. Model steps (prompt to asset spec, art-direction review) are done by
   a Claude Code session through the repo's `assetgen` skill. Third-party content (fonts,
   CC0 textures, model weights), if any is allowed (decisions 13.1 and 13.3), is vendored
   once by hand and read as data; a build never fetches anything.
2. **Generation core outside Blender.** Pure Python (numpy for array work under the
   determinism rules of section 10), testable in pytest without Blender. Blender 5.2 renders
   previews and contact sheets and may bake textures; it never decides geometry. Unreal only
   imports.
3. **The city model is the contract.** assetgen reads the city model (and M10's lock),
   never the blockout plan, and never writes back. What it needs and citygen does not yet
   record, it derives in its brief stage; requests for new model fields are listed in 4.5
   and land in citygen sessions, not here.
4. **Keyed by stable id, rebuilt by hash.** Every asset is keyed by its citygen id (M10) and
   carries the hash of everything it was made from (its brief). Same brief, same bytes.
5. **Unique by generation, repetition only where real buildings repeat.** A building repeats
   its own window, balcony and panel types across its facades, as real buildings do; two
   buildings share nothing they would not share in a real city (a material, a standard
   railing, a street light model).
6. **Semantic all the way down.** Every generated part keeps a type (`part.window.casement`,
   `part.shopfront.bar`, `part.roof.water_tank`), its building id and its material slot, so
   stages 3 and 4 can find windows to light, doors to open and surfaces to wet.
7. **Budgets are checks.** Triangle, instance, texture and disk budgets per building, tile and
   city are validated every run (section 9), like citygen's checks.
8. **Engine-agnostic files, Unreal-ready conventions.** glTF 2.0 (and USD where useful) with
   meters, citygen's frame and Unreal-friendly naming; Unreal specifics (Nanite flags,
   master materials, HLOD layers) live in the manifest, applied by M15's importer.

## 3. Pipeline stages

| # | Stage | Produces | Method |
|---|---|---|---|
| 0 | Prompt -> asset spec | `asset_spec.json` | a Claude Code session following the `assetgen` skill picks era palettes, facade systems, materials, signage scripts and brand styles per district and owner from the city prompt (and concept images); `assetgen spec validate`; unspecified values from era presets; no API call |
| 1 | Brief | `briefs.json`, brief hash per asset | per building: its record, lot frontage, neighbors within 3 m (party walls, blind walls), skybridges, portals, sign slots, mounted props (AC units, signs, awnings, wall lights, cables), facade plants, green roofs, M11 POIs inside, district style, spec section, overrides; each mass edge classified (section 5.1.2); floor grid; canonical JSON, sha256 |
| 2 | Genome | style genome per building | draws from the district's era palette, the property's owner brand and the building's id hash (section 5.1.1); complexes share one family genome |
| 3 | Massing articulation | refined envelope | chamfers, rounded corners, setback ledges, cantilevers inside the lot, fins, exoskeletons, crowns, podium canopies, atrium voids, portals; never outside the envelope rules (section 9) |
| 4 | Facades | shell mesh + part placements | split grammar: mass -> edge -> floor band -> bay -> opening; facade system per edge class; irregularity by grime and wealth |
| 5 | Ground floor | shopfront, lobby, garage and dock parts | one generated shopfront per M3 unit by use, doors at every entrance, awnings, sign boxes at sign slots, shutters, grilles |
| 6 | Roofs and details | roof parts | parapets, roof finishes, generated roof equipment for every roof item, helipad and AV pad markings, green roofs, downpipes, fire escapes, vents, cables, cameras |
| 7 | Parts and dedupe | part meshes, instances | each part generated in its own frame, quantized, hashed; identical parts within a building become instances; across buildings only when parameters coincide (section 5.1.4) |
| 8 | Street elements | per-tile street meshes | roads, markings, curbs, sidewalks, junctions, medians, bridges, decks, ramps, columns, tunnels, quays, transit structures, megasite elements (section 5.3) |
| 9 | Props, plants, signs | variant families, sign assets | per kind and district family; trees per species; signs and neon from sign slots (sections 5.4, 5.5) |
| 10 | Materials and textures | library + per-asset material parameters | tileable sets, trim sheets, decals, window interiors, signage atlases (section 5.2) |
| 11 | LODs and collision | proxies, collision, LOD chains for non-Nanite parts | section 8 |
| 12 | Validate | `asset_report.json`, `.txt` | section 9 |
| 13 | Write and preview | glTF packs per tile, part packs, manifest, lock, Blender previews | sections 6 and 8 |

## 4. Inputs

### 4.1 City model contract

assetgen reads `city_model.json` (model version 1) and, when present, `city.lock.json`
(M10). Per building it uses:

| Field (model.py) | Used for |
|---|---|
| `id` (M10 stable: `d03.lot.e512n88.bld`) | asset key, seed of the genome |
| `type`, `use`, `landmark`, `attrs` (`towers`, `docks`, `decks`, `atrium_m2`, `open_sides`, `arms`, `span_*`) | building program, which generator |
| `masses[]`: `footprint`, `z0_m`, `z1_m`, `role` (podium, tower, tier, crown, spire, mechanical, stack, shack, deck, span, leg, dock, void, ...), `shape` (prism, cylinder, dome, cone, ring) | the envelope; roles pick the facade treatment (podium vs tower vs crown) |
| `floor_height_m`, `floors`, `height_m` | floor grid |
| `units[]`: `edge`, `use`, `entrance`, `awning_m`, `sign`, `segment_id` | one shopfront per unit (16,780 in Vesper Bay) |
| `entrances[]`: `position`, `kind` (main, service, loading, garage, gate) | doors, lobbies, docks, garage mouths |
| `roof_items[]`: `kind`, `position`, `size`, `yaw_deg` | generated roof equipment (15,595 in Vesper Bay) |
| `portals[]` | sky tube voids and sky station floors |
| `style`: `grime`, `neon`, `era` | wear, signage density, palette (one era per archetype today: heritage, neon_retro, corporate_glass, brutalist, industrial, clean_tech, suburban_modern, transit_modern, mixed_modern, aerospace) |
| `property_id` -> `Property.owner`, `complex` | owner brand, complex families (twin towers mirrored, clusters as one family) |
| `lot_id` -> `Lot.frontage` | main facade (frontage[0], as M3 places it), street classes on each side |
| `district_id` -> `District.archetype`, `params` (grime, neon, greenery, wealth, danger) | palette and wear |
| `skybridges` naming it | facade openings and the skybridge assets |
| `sign_slots` with its `building_id` | sign boxes, billboard frames, neon bands, kept clear of windows |
| `props` mounted on it: scaffolding (`attrs.building`), and by position within 0.5 m of its facades ac_unit, awning, wall_light, sign and overhead_cable ends | brackets and mounts; windows avoid them |
| `plants` of type `facade_greenery`, `green_areas` (`green_roof`) on it | planters, trellises, roof build-ups |
| `pois` in it (M11) | which shopfronts are bars, clinics, vendors (names on signs); apartment floors (lit windows) |

Street elements read road segments (class, cross-section, z-profile, level, tunnel),
junctions, crosswalks, sidewalks, bridges, structures, tunnels, quays, waterways, transit
lines, stations, megasites, site elements, props, plants and green areas, each by its id.

### 4.2 Asset spec (generated from the prompt; never required to edit)

`asset_spec.json`, written by a Claude Code session through the `assetgen` skill, filled
from era presets where left out:

```json
{
  "city": "Vesper Bay", "uniqueness": "U1", "texel_density_px_m": 512,
  "eras": {
    "corporate_glass": {"systems": {"unitized_curtain_wall": 0.5, "fin_wall": 0.2,
                                    "diagrid": 0.1, "spandrel_ribbon": 0.2},
                        "palette": ["#1b2430", "#9fb4c7", "#c9d2da"], "crowns": ["lantern", "halo", "mast"]},
    "heritage": {"systems": {"punched_brick": 0.4, "stucco_shutters": 0.3, "timber_infill": 0.1,
                             "tiled_eaves": 0.2}, "signage_scripts": {"hanzi": 0.5, "latin": 0.3, "hangul": 0.2}}
  },
  "districts": {"Neon Strand": {"wear": 1.2, "ad_density": 1.5, "neon_palette": ["#ff2a6d", "#05d9e8"]}},
  "owners": {"Kessler Dynamics": {"brand_colors": ["#e8e8e8", "#c1121f"], "logo": "logos/kessler.svg",
                                  "facade_bias": {"fin_wall": 0.6}}},
  "landmarks": {"Corporate Core Megatower": {"brief": "black glass arms, red light seams, crown halo"}}
}
```

### 4.3 Overrides (never required)

`asset_overrides.json` beside the spec, on stable ids: `pin` (keep this asset as it is
even if its brief changes), `style` (force genome genes on a building or property),
`replace` (a hand-made or hero model for an id; the manifest points at it and the checks
still run its envelope), `regenerate` (a new seed for one building).

### 4.4 Regeneration by id and hash

- $\text{key}(b) = \text{id}(b)$; $h(b) = \text{sha256}\big(\text{brief}(b) \,\Vert\, v_{\text{gen}} \,\Vert\, h_{\text{lib}}\big)$,
  with $v_{\text{gen}}$ the generator version of the parts that building uses and
  $h_{\text{lib}}$ the hash of the material library entries it references.
- `assetgen build` keeps every asset whose $(\text{key}, h)$ is in the previous manifest, makes
  the rest, drops ids no longer in the model, and garbage-collects parts no asset references.
  A rebuild of an unchanged city does no work and writes no file.
- The brief includes neighbor data (party walls, skybridges, mounted props), so M10's seam
  (blocks of other districts cut by new junctions, props near new ones) rebuilds exactly the
  assets it touches.
- M10's ids come from position (the 1 m cell of an entity's middle): a building that keeps
  its cell but changes shape keeps its id and genome (same character, new geometry); a
  building whose middle moves to another cell gets a new id and a new look unless an
  override pins its genome.
- `assetgen lock` writes `assets.lock.json` (city lock hash, asset spec, overrides, assetgen
  code hash, library hash, manifest hash); `--verify` rebuilds from it byte for byte, like
  `citygen lock`.

### 4.5 Asked of citygen later (not in this branch)

Derived in the brief meanwhile; worth recording in the model in a citygen session:
- ground height under each footprint vertex and a building base level (M13 terrain, M14
  decks), so plinths, stepped podiums and retaining walls follow the ground;
- floor height per mass (a 4 m retail podium under a 3.2 m residential tower);
- the facade edge index M3 picked (`buildings.facades`) and party-wall edges;
- the building id on facade props (ac_unit, awning, wall_light, sign), which today only
  scaffolding and facade greenery carry;
- an owner brand id on properties that share an owner across districts.

## 5. Feature catalog

### 5.1 Buildings

#### 5.1.1 Genome

Three layers of draws, all from blake2b hashes of ids (as `props._u`):
- **District palette** (era plus asset spec): which facade systems, materials, colors, crown
  and roof types, signage scripts and wear levels are available, with weights.
- **Property** (owner brand, complex): a family genome shared by a complex's buildings
  (twin towers mirrored, a tower cluster in one language with stepped variations, a campus
  in one material set); corporate owners bias toward their brand colors and systems.
- **Building**: discrete genes (facade system per mass role, bay module, window type,
  spandrel, corner treatment, balcony type, crown, roof equipment style, material set,
  color scheme, signage style) and continuous ones (bay width, window-to-wall ratio, floor
  band depth, reveal depth, wear, dirt gradient, neon level), quantized to steps.

Uniqueness is measured on genomes: two buildings of a city outside one complex family must
differ in at least $k$ discrete genes or by a weighted distance $d \ge d_{\min}$, and their
contact-sheet thumbnails must differ by a perceptual hash distance (check `asset_unique`).

#### 5.1.2 Edge classes and the facade grammar

Each mass edge is classified in the brief: `front` (on the main frontage), `street` (by road
class), `alley`, `canal`, `plaza` or `park`, `courtyard` or `atrium`, `party` (another
building within 0.5 m: blank fire wall, ad or graffiti surface), `blind` (a neighbor within
3 m: few small windows, pipes), `open` (setback lawn, yard), `upper` (above every neighbor).

Split grammar (Wonka 2003, CGA, section 14), per mass:

$$\text{mass} \to \text{edges} \to \text{floor bands} \to \text{bays} \to \lbrace \text{opening}, \text{panel}, \text{pier}, \text{mount} \rbrace$$

- Floor bands from `floor_height_m`, with a ground band, a podium top, mechanical floors
  (louvers) every 15 to 25 floors in towers, a crown band.
- Bays from edge length and the genome's bay module, centered or rhythmic (A-B-A,
  doubled corners), snapped so sign slots, mounted props and skybridge ends fall on panels
  or piers, never on glass.
- Facade systems (v1 set, per era): unitized curtain wall, spandrel ribbon, fin wall,
  diagrid and exoskeleton, punched concrete, precast panel, brutalist board-marked concrete
  with deep reveals, punched brick, stucco with shutters, timber infill, corrugated and
  standing-seam cladding, louvered industrial, shanty patchwork (mixed panels, tarps,
  add-on boxes, bolted sheets), capsule stacks, clean-tech perforated skins, aerospace
  hangar cladding.
- Irregularity scaled by grime and wealth: boarded or blocked windows, added AC units and
  grilles, mismatched replacement panels, closed-in balconies, stains under sills, satellite
  dishes, cables between floors.

#### 5.1.3 Ground floors, roofs and connections

- **Shopfronts**, one per unit, generated by use: food (open counter, menu boards), bar (dark
  glazing, neon frame), club (blank wall, entrance canopy, queue rail), arcade (open front,
  screens), cyberware and clinic (clinical white, light boxes, frosted glass), pawn (grilles,
  roll-down shutter), convenience (full glazing, posters), laundromat (wide windows),
  lobby (double-height glass, revolving door); doors at the unit entrance, awnings of
  `awning_m`, sign boxes where `sign` is set.
- **Entrances**: main doors with canopies, service doors, loading docks with levelers, garage
  mouths with ramps, gates.
- **Roofs**: parapets and copings, membranes, gravel, tiles (heritage pitched roofs where the
  era allows), roof equipment generated for each roof item (AC units, water tanks, antennas,
  billboard frames, mechanical penthouses, helipads and AV pads with markings and lights),
  green roof build-ups, roof access huts.
- **Connections**: openings and frames where skybridges land; the skybridges themselves by
  kind (enclosed, open deck, stack, catwalk, cable); sky tube portals cut through the tower
  with a sky station floor; podium decks; atrium interiors.

#### 5.1.4 Parts and repetition

Every part (a window unit, a balcony, a shopfront, a roof AC unit) is generated in its own
frame from quantized parameters (1 cm lengths, 5 degree angles, discrete styles), then
hashed. Within a building, identical parts become instances of one mesh. Across buildings,
a part is shared only when two buildings drew the same parameters; the quantization steps
set how often that happens and are part of decision 13.2. The shell (walls with their
openings, slabs, reveals, cornices) is one mesh per building and never shared.

#### 5.1.5 Types, complexes and landmarks

Generators per M3 type (shopfront_row, shanty_stack, villa, podium_tower, tower, slab,
courtyard_block, perimeter, terraced, megabuilding, warehouse, shed, yard, hangar, lab,
parking_structure, temple_hall, pagoda, gate_house, terminal, control_tower, station,
straddle_building), complexes (twin_towers, tower_cluster, megabuilding_campus,
bridged_pair, straddle_building, campus) and landmarks (`building.landmark.<kind>`: the
three-armed megatower, spires, arcology, wheel) as hero generators with their own
detail budgets and optional unique texture bakes (U2).

### 5.2 Materials and textures

- **Master materials** (Unreal, mirrored in Blender for previews): opaque facade, opaque glass
  with interior mapping and per-window lighting, metal, concrete, emissive neon, sign atlas,
  deferred decals, road with markings, water edge. No translucency on Nanite meshes:
  building glass is opaque with reflections and interior mapping (section 8).
- **Per-building variation without unique textures**: material instance parameters and
  Custom Primitive Data per actor (tint, wear, dirt gradient height, rain streak strength,
  neon level, lit-window ratio, seed), vertex colors from the generator (edge wear, grime
  toward the ground and under sills, a per-window random id in a second UV set).
- **Library** (shared by every city, rebuilt only when its generator changes): tileable PBR
  sets per era (base color, normal, occlusion-roughness-metal, height), trim sheets per era
  (frames, sills, panel joints, railings), decal atlases (grime, leaks, rust, graffiti,
  posters, stickers, cracks), window interior atlases per use (office, apartment, capsule,
  shop, club, warehouse; day and night), road atlases (markings, patches, manholes, drains).
- **Per city**: signage atlases (M11 POI names and unit uses rendered in the district's
  scripts, brand logos), billboard and holo-ad content, a few hero bakes (U2).
- **Texel density**: 512 px/m on surfaces within reach of the street (ground band, props),
  256 px/m above; a check measures it from UVs.
- **How textures are made** (decisions 13.1, 13.3): procedural in numpy (integer-hash
  noise, pattern generators for brick, tiles, panels, corrugation, rust, concrete; exact
  per section 10) and Blender shader-node bakes where numpy falls short; optionally a
  vendored CC0 library or an offline local image model, whose outputs enter as data.

### 5.3 Street elements

| Element | From | Generated |
|---|---|---|
| road surface | road segments, junctions, cross-sections | asphalt by class with lane markings (lines, arrows, stop lines), patches, manholes, drains; UV along the road |
| crosswalks | crosswalks | zebra or ladder paint, tactile paving at the curb |
| sidewalks, curbs | sidewalks, cross-sections | district paving families, curb stones, tree pits, driveway drops |
| medians | cross-section `median_m`, green areas | curbed islands, lawn, barriers |
| bridges | bridges (class, clearance, named) | girder by default; arch and cable-stayed for named landmark crossings; footbridges by canal style |
| decks, ramps, viaducts, interchanges | structures, road z-profiles (M7, M8d, M12) | box-girder decks, parapets, expansion joints, underside lighting, columns and pier caps |
| tunnels | tunnels (M9) | walls, lighting strips, portals, approach trenches, vent buildings (as buildings) |
| quays, canal walls, piers | quays, waterways | stone or concrete walls, stairs to the water, bollards, moorings |
| transit | transit lines, stations, structures | guideways, beams, maglev tracks, sky tubes (glass, non-Nanite), pylons; stations as buildings |
| megasite elements | site elements | launch pads, towers, gantry cranes, container stacks (instanced), fuel tanks, berths, rail |

Street meshes are written per 256 m tile, keyed by the ids they cover, so a regenerated
district rewrites only its tiles' street packs.

### 5.4 Props and vegetation

- **Props**: for each M6 kind (street_light, traffic_signal, bus_stop, bench, kiosk,
  food_stall, vending_machine, trash_can, trash, dumpster, bollard, hydrant, planter,
  barrier, railing, overhead_cable, awning, sign, ac_unit, wall_light, scaffolding,
  parked_vehicle, boat, gate) a family of 4 to 12 generated variants per district style
  (sleek in the Corporate Core, improvised in Old Town), chosen per prop by its id hash;
  instanced (HISM), as M15 already does with the blockout prototypes. Here a family is the
  right amount of uniqueness: a city's street lights share a model.
- **Plants**: a tree generator (space colonization, Runions 2007) per species (plane, maple,
  ginkgo, birch, linden, elm, oak, ficus, pine, fan palm, date palm), 6 to 10 variants each,
  sized from each plant's height and crown; shrubs, ivy, sedum and scrub as cards and small
  meshes; Nanite foliage if 5.8 has it in a usable state (experimental in 5.7), else
  LOD chains with impostors.
- **Cables, awnings, scaffolding** follow their M6 geometry exactly (catenaries between
  facades, awning depth, scaffold bays).

### 5.5 Signs, neon and ads

Every M11 sign slot gets an asset: blade and facade shop signs (box, frame, light, the POI
or use text), neon (tubes swept along glyph outlines of the district's script, with
brackets and transformers), billboards (frame, lamps, a content texture), holo-ads
(emissive translucent planes, non-Nanite), neon bands. Text comes from M11 names and unit
uses; fonts and scripts per asset spec.

## 6. Asset outputs (canonical)

```
<build_dir>/assets/
  manifest.json            assetgen and library versions, city model and lock hashes, and per key:
                           kind, brief hash, asset hash, tile, mesh names, part instances,
                           material slots and parameters, collision, proxy, bounds, triangles
  briefs.json              the briefs (what each hash was made from)
  tiles/<tile>.glb         building shells and unique parts, street meshes, by node name = id
  parts/<pack>.glb         parts shared by instances, content-addressed, packed about 5,000 per file
  proxies/<tile>.glb       far proxies (section 8)
  props.glb, plants.glb    variant families
  signs/<tile>.glb         sign meshes; atlases under textures/
  materials.json           master material per slot, instance parameters, texture references
  textures/ -> library     the shared library (by hash) plus the city's signage and hero bakes
  asset_report.json, .txt  checks and stats
  assets.lock.json
```

- One glTF pack per tile follows M15's pattern (`tiles/<tile>.glb`, a node per object named by
  its id); thousands of single-building files would cost an import each. File granularity is
  measured in A0.
- Coordinates: citygen's frame (meters, x east, y north, z up); each building's nodes sit at
  its own origin (the middle of its footprint, on the 0.01 m grid) so vertex positions stay
  small; M15 maps to Unreal as it does today.
- Names follow M10 ids; Unreal asset names replace dots with underscores, as M15's importer
  does.

## 7. Interfaces

- **M15 (Unreal import)**: `citygen unreal <build_dir> <uproject> --assets` uses
  `assets/manifest.json` where it has an entry for a key and the blockout mesh elsewhere; parts
  as instanced static mesh components per building (or merged into the shell where a part
  repeats fewer than about 8 times), material instances of the master materials with Custom
  Primitive Data, Nanite on, simple collision from the manifest, HLOD layers. Re-import by
  key and hash, as M15 does. This importer change is a citygen session's after M15 merges.
- **Stage 3 (atmosgen)**: emissive windows with per-window ids and use (lit patterns by hour
  band from M11 densities), light emitter points on signs, wall lights and street lights,
  neon colors, wet-surface masks, under-deck surfaces.
- **Stage 4 (lifegen)**: doors at every entrance with their walkway ids, shopfront counters,
  bus shelters, taxi stands, parking entrances, sky station floors, collision that matches
  the walkway graph.
- **Later**: enterable interiors for M11 points of interest (decision 13.6).

## 8. Builders, LODs and Nanite

- **Geometry route (recommended)**: pure Python generators emit meshes as integer millimeter
  coordinates in each building's frame, triangulated by assetgen's own exact ear clipping
  (integer orientation tests), with normals, two UV sets (world-scale tiling, per-face 0 to 1)
  and vertex colors; a deterministic glTF writer packs them. Blender reads the packs for
  previews (parts as instances, as the blockout does with props) and bakes; it does not
  model. Rejected as the core:
  - Blender geometry nodes: fast and good at instancing, but not testable without Blender, not
    byte-identical across Blender versions and machines, hard to review in git, awkward for
    rule-heavy per-building logic (units, mounts, neighbors).
  - Unreal PCG (the 5.8 City Sample's route): ties stage 2 to Unreal and its determinism to
    the editor; useful later for dressing inside Unreal, not for the generator.
- **Nanite**: every opaque or masked building, street, prop and part mesh is Nanite. Glass is
  opaque (interior mapping, reflections); translucent pieces (holo-ads, sky tubes, some sign
  faces) are separate non-Nanite meshes with generated LOD chains (parts dropped by size).
- **Proxies**: one far proxy per building (its masses with roof silhouettes, 50 to 500
  triangles, facade texture by UV) for Nanite fallback, HLOD inputs and Blender whole-city
  renders; Unreal's World Partition HLOD layers (instanced, merged, approximated) are set up
  by the importer.
- **Collision**: simple collision from masses (a convex box per mass part, steps, ramps,
  awning posts), complex collision only in the ground band where players brush walls and
  doorways; checked against the walkway graph.
- **Foliage**: Nanite foliage if 5.8 makes it usable (A0 checks), else LOD chains and
  impostors.

## 9. Validation (runs every time; a failure means the assets are not delivered)

- Coverage: every building, skybridge, street element, prop kind, plant species and sign slot
  of the model has an asset (or a declared fallback); every id in the manifest is in the model.
- Envelope: a building's asset stays inside its lot and masses plus allowed overhangs
  (balconies, cornices, signs and awnings up to their M3/M6 depth, at least 3 m over a
  sidewalk, never over a lane); nothing enters skybridge, transit, sky tube or road clearance
  envelopes; portals stay open.
- Access: a door at every entrance and unit entrance, open to its walkway; skybridge ends on
  openings at their deck height; sky station floors at portals.
- Mounts: every sign slot, mounted prop and facade plant sits on a panel or pier, not glass.
- Meshes: no degenerate or duplicate triangles, consistent winding, no cracks along the shell
  (shared edges match), UVs present, texel density within bounds.
- Uniqueness: genome distance and thumbnail hash distance (section 5.1.1) except within complex
  families.
- Budgets: triangles, instances and texture memory per building class, tile and city
  (section 11); disk per city.
- Determinism: the manifest hash equals the golden for the test cities; a second build writes
  no file.
- Stats: assets by kind, unique and instanced triangles, parts and their reuse, texture sets,
  disk, timings per stage.

## 10. Determinism (Mac arm64, Windows x86_64, Linux x86_64)

Same city model, asset spec, overrides, library and assetgen code: the same manifest, mesh
bytes and pixels on every machine. citygen's rules carry over; assetgen adds:
- **Randomness**: blake2b of (salt, id, purpose) only; no Python `hash()`, no set or dict
  order of strings reaching output, no GEOS output order reaching a decision (citygen's
  `geom` helpers where shapely is needed).
- **Math**: citygen's `dmath` for transcendentals; numpy only for elementwise IEEE operations
  (add, multiply, divide, sqrt) in a fixed order, no float reductions whose order numpy may
  change (`sum` on floats, `dot`), no numpy transcendentals; no compiled geometry library in a
  decision (C++ compiled for arm64 may fuse `a*b+c` into one multiply-add where an x86-64
  build does not, so the last bit differs).
- **Geometry**: vertices as integer millimeters in the building frame before packing;
  triangulation, normals and UVs computed from those integers in a fixed order.
- **Images**: pixels from integer hash noise and fixed-order arithmetic; goldens hash decoded
  pixels, since PNG bytes depend on the zlib build.
- **Files**: `\n` line endings, `/` in manifest paths, lowercase names (Windows and macOS
  file systems ignore case), paths well under Windows' 260 characters, sorted JSON keys,
  results independent of the worker count.
- **Blender bakes** are cached by input hash and checked within a tolerance, never golden;
  a bake changes only when its inputs do.
- **Verification**: goldens (manifest hash of a small test city and a few sample buildings)
  in pytest; `assetgen verify` compares manifests across machines; Linux x86 in the
  `citygen-x86` docker image; Windows on the RTX PC (needs a Python 3.13 venv there and a
  way for a session to run on it, decision 13.5).

## 11. Scale, compute and disk budgets

Measured on the sample cities (Vesper Bay on M11's code, Nexus City on M10's):

| Quantity | Vesper Bay | Nexus City |
|---|---|---|
| buildings | 5,794 | 6,369 |
| mass side area (upper bound: party walls and hidden faces count) | 14.4 km² | 15.0 km² |
| of it 0 to 12 m / 12 to 40 m / over 40 m | 5.7 / 4.1 / 4.6 km² | 6.2 / 5.6 / 3.2 km² |
| roof area | 3.7 km² | 3.8 km² |
| window bays (3 m wide, one floor high) $N_b$ | 1.37 M | 1.41 M |
| buildings 100 m or taller | 268 | 163 |
| ground-floor units $N_u$ / roof items / sign slots | 16,780 / 15,595 / 15,460 | not counted |
| props / plants | 50,568 / 25,851 | not counted |

**Triangles (U1, the recommended level).** Unique triangles per city:

$$T_{\text{unique}} \approx N_b\, t_b + A_r\, \rho_r + N_u\, t_u + M\, t_m + T_{\text{hero}}$$

With a shell cost of $t_b \approx 24$ per bay (wall around the opening, reveals, sill and lintel),
$\rho_r \approx 1$ per m² of roof, $t_u \approx 1{,}500$ per shopfront, $M \approx 30{,}000$
distinct parts of $t_m \approx 800$, and $T_{\text{hero}} \approx 10\text{ M}$ for landmarks:

$$T_{\text{unique}} \approx 34\text{ M} + 4\text{ M} + 25\text{ M} + 24\text{ M} + 10\text{ M} \approx 100\text{ M}$$

plus about 2 to 3 M part instances (windows, balconies, equipment), about 1 billion
triangles drawn through instancing, which Nanite is built for. Street meshes add about 10 to
20 M, props and plants a few million (instanced).

**Disk.** At the commonly cited Nanite size of about 14 bytes per triangle (not in Epic's
docs; A0 measures it):

$$D_{\text{Nanite}} \approx 100\text{ M} \times 14\text{ B} \approx 1.4\text{ GB per city (cooked)}$$

Source glTF at about 40 to 60 bytes per triangle (float positions, normals, two UV sets,
colors, indices) is 4 to 6 GB per city, roughly half with quantized attributes if Unreal's
importer reads `KHR_mesh_quantization` (A0 checks). In the Unreal editor a city's assets
with their derived data are likely 8 to 15 GB (A0 measures).

Texture library, cooked (BC7 and BC5 at 1 byte per texel, BC1 at half, mips $\times\tfrac43$):
a 2K set of base color, normal and ORM is about 14 MB; 120 sets (12 per era), 20 trim
sheets, decal and interior atlases come to about 2.5 GB shared by every city, about 5 to 7 GB
as source images (regenerable, not in git). Signage per city about 0.3 GB.

| Uniqueness level | Unique triangles | Extra texture disk per city |
|---|---|---|
| U0: fixed kit (about 2,000 module meshes, City Sample style) | about 5 M | none |
| U1: generated per building, shared tileable textures, per-building parameters (recommended) | about 100 M | none |
| U2: U1 plus a unique 512 px mask texture per building (grime, leaks, wear in three channels) | about 100 M | about 2 GB |
| U3: no part shared between buildings, and a unique 2K texture set per building | about 120 M | 6,000 × 3 maps × 2048² × 1 B × $\tfrac43$ ≈ 100 GB |

**Compute targets** (M4 Pro: 10 performance cores, 24 GB; A0 measures and may revise):
- a whole city's assets in under 20 minutes with 10 workers, under 2 GB per worker;
- one district in under 3 minutes, one building in under 10 s;
- the shared library in under an hour, once per library version;
- Blender previews in under 10 minutes (districts at full detail, the whole city from proxies:
  100 M triangles do not fit Blender in 24 GB);
- Unreal import of a city's assets in under an hour (measured in A0 and A5).

**Disk targets**: source outputs per city at most 6 GB, the shared library at most 7 GB as
source, nothing generated in git except previews and small goldens. The Mac has about 90 GB
free, so it holds one or two cities' assets and one imported city at a time; the other
samples build at proxy level or on the Windows PC (decision 13.5).

## 12. Out of scope (v1)

- Enterable interiors (window interior mapping only; decision 13.6).
- Vehicles, characters, animation (stage 4), lighting setups and sky (stage 3).
- Destruction states, seasonal and weather variants beyond material parameters.
- Building geometry from AI models (section 13.1 explains why).
- Hand modeling (hero replacements come in through overrides, made elsewhere).

## 13. Decisions that need Swagnik

1. **Local AI models.**
   - (a) None: everything procedural, deterministic, no ML dependency. *Recommended for the
     generator*, and for v1.
   - (b) An offline "texture lab" outside the build: local image models (on the RTX 4070 Ti's
     12 GB) make tileable materials, posters and ad art once; the outputs are vendored as a
     library with hashes and read as data, so builds stay deterministic. Licenses vary (some
     popular models are non-commercial or exclude regions); outputs are not reproducible
     byte for byte across GPUs, so they can never be regenerated per build.
   - (c) (b) plus image-to-3D for a few hero props. Not for buildings in any option: such
     models cannot honor masses, floor grids, entrances or budgets, and give triangle soup;
     several want more than 12 GB of VRAM.
   - Claude itself (the session, through the skill) can write asset specs, brand names, ad
     copy and SVG logos, which keeps the no-API rule and needs no model weights.
2. **How unique "unique" must be.** U0 to U3 (section 11). *Recommended*: U1 for every
   building, with U2 bakes for landmarks and hero buildings (about 1% of buildings, under
   1 GB), and the uniqueness check of 5.1.1 as the measurable bar (at least $k = 4$ discrete
   genes apart outside a complex). Also: may two buildings share a part when their parameters
   coincide (smaller, more realistic) or must every part be distinct (U3-like disk)?
3. **Third-party content.** Fonts for signage scripts (Hanzi, Hangul, Latin, Cyrillic, Devanagari
   need font files; OFL fonts are free) and optionally CC0 textures (ambientCG, Poly Haven), each
   downloaded once by hand into a vendored folder, versus fonts only, versus none (signs from
   generated stroke fonts). *Recommended*: OFL fonts vendored; textures generated first, CC0
   only if A4 previews fall short.
4. **Target hardware and detail.** Which machine sets the budgets: the RTX 4070 Ti PC as the
   minimum spec at 1440p with Nanite and Lumen (recommended), or the M4 Pro Mac. This fixes
   triangle density (section 11) and texel density (512 px/m proposed).
5. **Where heavy work and storage live.** Assets are not in git. The Mac has about 90 GB free;
   is there an external drive or room on the Windows PC (how much)? Can sessions reach the
   Windows PC (SSH, or a local Claude Code there) for the Windows determinism check and full
   imports?
6. **Interiors.** Interior mapping only (recommended for v1), enterable interiors for M11
   points of interest as a stage 2 milestone (bars, clinics, apartments: large scope), or
   left to the nyxllor repo.
7. **Art direction input.** Asset spec per city written by a session from the prompt
   (recommended), with review rounds on renders; do you want to give reference images per era
   or district (mood boards) that the skill reads, as citygen reads concept maps?
8. **Geometry route.** Confirm pure Python generators with Blender for previews (section 8)
   over geometry nodes or Unreal PCG.

## 14. Milestones (each ends with tests passing, previews committed, and a short report)

| A | Deliverable | Done when |
|---|---|---|
| A0 | Contract and spike: package `assetgen/` (CLI `python -m assetgen`), `assetgen brief` and `brief diff`, manifest schema, deterministic glTF writer, exact triangulator, determinism harness (Mac, x86 docker); Unreal 5.8 spike on the M15 test project with three generated buildings (a 1 M triangle tower, a shopfront row, a shanty): Nanite on, parts as instances from the manifest, Custom Primitive Data, opaque glass with interior mapping, simple collision; Interchange support for `KHR_mesh_quantization` and `EXT_mesh_gpu_instancing`; Nanite foliage status | briefs for every building of the seven samples, Mac = x86; import time and disk per million triangles measured; section 11 revised; the decisions of section 13 answered |
| A1 | Genome and shells: era palettes, district, property and building genomes, edge classes, split grammar, v1 facade systems, shells with openings, slabs, parapets, cornices, UVs, flat preview materials; Blender preview build (district renders, the blockout's street views, contact sheets per type); checks for envelope, access, uniqueness, meshes | every sample building has a shell; checks pass; Mac = x86; whole city under 20 minutes |
| A2 | Ground floors, parts and roofs: shopfronts per unit use, doors, awnings, sign boxes, lobbies, docks, garages; window, balcony, louver and fin parts with dedupe and instances; roofs with generated equipment for every roof item; details (downpipes, fire escapes, cables, vents) | street views read as distinct buildings; triangle budget met; Mac = x86 |
| A3 | Types, complexes, landmarks: shanty stacks, megabuildings (court, towers, decks, atriums), industrial types, villas, labs, civic and religious types, stations; complex families; skybridges of all kinds; sky tube portals and sky stations; hero generators for every landmark kind; first art-direction rounds through the skill | every type, complex and landmark in the samples has an asset; reviewed renders per district |
| A4 | Materials and textures: library generator per decisions 13.1 and 13.3, trim sheets, decals, window interiors, signage atlases from M11 names, ads; per-building parameters; Blender materials matching the Unreal masters; texel density check | material renders of every sample district; library within budget; pixels Mac = x86 |
| A5 | LODs, collision, Unreal: proxies, collision, LOD chains for non-Nanite pieces, the full manifest; with a citygen session, M15's `--assets` import, master materials, HLOD layers; regeneration end to end | Vesper Bay imports with its assets, streams and can be walked; a second import changes nothing; a regenerated district rebuilds and re-imports only its changed assets; disk and time within budget |
| A6 | Street elements (section 5.3), may run beside A1 to A3 | every street element of the samples has an asset; street-level renders; Mac = x86 |
| A7 | Props, plants, signs (sections 5.4, 5.5), may run beside A1 to A3 | every prop kind, species and sign slot has an asset; instance budgets met |
| A8 | Scale and release: every sample at full detail (where disk allows), an assetgen sweep over the M8a suite cities (no crash, budgets), Windows = Mac, `assetgen lock` and `--verify`, root README with 8K renders of asset cities | sweep without crashes; three machines agree; budgets met |

A0 to A2 is the core ("every building has a model of its own"). A6 and A7 share no code with
the building generators and can run as parallel local sessions after A0.

## 15. Running it

- Local sessions only (no cloud credits); one milestone per session in its own worktree, two
  at once where they touch different files (A6 or A7 beside A1 to A3).
- Package `assetgen/` beside `citygen/`, importing citygen's model, `dmath` and `geom` read
  only; tests in `tests/assetgen/`; skill `.claude/skills/assetgen/SKILL.md`.
- Work-in-progress images in `docs/progress/A<n>/wip/` as for citygen milestones; generated
  assets never in git.
- citygen changes assetgen needs (section 4.5, M15's `--assets`) go to citygen sessions.

## 16. References

- Wonka, Wimmer, Sillion, Ribarsky, "Instant Architecture", SIGGRAPH 2003 (split grammars).
- Müller, Wonka, Haegler, Ulmer, Van Gool, "Procedural Modeling of Buildings", SIGGRAPH 2006
  (CGA shape grammar).
- Schwarz and Müller, "Advanced Procedural Modeling of Architecture", SIGGRAPH 2015 (shape
  grammars with queries on neighbors and context).
- van Dongen, "Interior Mapping: A new technique for rendering realistic buildings", CGI 2008:
  http://www.proun-game.com/Oogst3D/CODING/InteriorMapping/InteriorMapping.pdf
- Runions, Lane, Prusinkiewicz, "Modeling Trees with a Space Colonization Algorithm", 2007:
  http://algorithmicbotany.org/papers/colonization.egwnp2007.html
- Epic City Sample Buildings (24 modular kits, 44 sample buildings, over 2,000 meshes; the
  kit route): https://www.cgchannel.com/2022/04/download-epic-games-free-city-sample-assets-for-ue5
- Nanite: https://dev.epicgames.com/documentation/unreal-engine/nanite-virtualized-geometry-in-unreal-engine
- Unreal 5.7 (Nanite foliage, experimental): https://80.lv/articles/unreal-engine-5-7-is-now-availabe
- glTF 2.0: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
- Infinigen (procedural generation and materials in Blender): https://infinigen.org
- CC0 texture libraries: https://ambientcg.com, https://polyhaven.com
- Buildify (geometry-nodes building kit), CityCraft, SceneCraft: see `docs/citygen_scope.md`
  section 14.
