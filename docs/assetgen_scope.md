# assetgen: unique building models, street elements and textures (scope, draft v0)

Stage 2 (assetgen) of CyberGen's five stages. A built citygen city in; a 3D model of its own
for every building, plus the street elements, props, plants and texture library the city
needs, out, and into Unreal through the shared exporter (`docs/unreal_export.md`), which
every assetgen milestone updates for what it adds. Like citygen it is city-agnostic, offline and
deterministic. Its milestones carry the prefix AG (AG0 to AG15, section 14), so their
folders in `docs/progress/` never clash with stage 1's M folders or a later stage's; their
full record is `docs/assetgen_milestones.md`. The decisions that need Swagnik before AG1
starts are in section 13.

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
        └──> Unreal exporter: assetgen's entries replace blockout meshes by id

 asset_spec.json (art direction, written by a Claude Code session through the
 `assetgen` skill from the city prompt; no API call)
```

## 1. Goal

- Input: a citygen build (the city model with M10's stable ids, M13's terrain and M14's
  deck levels where a city has them) and an optional asset spec (art direction per district, era, owner). Nothing modeled by hand.
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
   master materials, HLOD layers) live in the manifest, applied by the shared Unreal
   exporter.

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

The ground comes with stage 1's own milestones: M13 (terrain, in progress) gives each
building `base_m` (its ground floor over sea level, at the main entrance) and `plinth_m`
(the lowest ground under its footprint, from which a stepped plinth fills up to `base_m`),
roads their grade lines and the city a terrain grid; M14 (layered districts) will give the
deck levels buildings stand on. assetgen reads them where present and assumes flat ground
at z 0 where not.

Derived in the brief meanwhile; worth recording in the model in a citygen session:
- floor height per mass (a 4 m retail podium under a 3.2 m residential tower);
- the facade edge index M3 picked (`buildings.facades`) and party-wall edges;
- the building id on facade props (ac_unit, awning, wall_light, sign), which today only
  scaffolding and facade greenery carry;
- an owner brand id on properties that share an owner across districts;
- sidewalks and walkways of a raised road segment at its height (an M15 open item: today
  they sit at z 0 under the deck); AG7 puts them on the deck from the road's profile until
  citygen does.

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
  meshes; Nanite with `ShapePreservation` `Voxelize` (5.8, experimental; AG0's test tree
  builds with it), else LOD chains with impostors.
- **Cables, awnings, scaffolding** follow their M6 geometry exactly (catenaries between
  facades, awning depth, scaffold bays).

### 5.5 Signs, neon and ads

Every M11 sign slot gets an asset: blade and facade shop signs (box, frame, light, the POI
or use text), neon (tubes swept along glyph outlines of the district's script, with
brackets and transformers), billboards (frame, lamps, a content texture), holo-ads
(emissive translucent planes, non-Nanite), neon bands. Text comes from M11 names and unit
uses; fonts and scripts per asset spec.

### 5.6 Water and ground cover

Today both are the blockout's flat sheets with a color: blue for the sea and the water
bodies, green for lawns, parks and verges. AG12 and AG13 (14.13, 14.14) replace them, from
M16's data (citygen scope, section 12):

- **Water** (AG12): per water body and tile a surface mesh carrying its flow and a foam
  mask, a bed at its depth (mud, sand, stone) and its banks (natural slopes, beaches,
  riprap) meeting AG7's quays and canal walls; drawn in Unreal with Single Layer Water.
- **Ground cover** (AG13): every piece of open land textured by its cover kind (lawn,
  meadow, marsh, wasteland, dirt, gravel, sand, planted bed, overgrown paving), blended by
  its wear, shade and edges; grass and small plants (lawn, meadow, reeds, weeds, clover,
  flowers, ferns) scattered on it by density, swaying in the wind. AG8's ground plants
  (sedum, scrub) join it.

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
  measured in AG0.
- Coordinates: citygen's frame (meters, x east, y north, z up); each building's nodes sit at
  its own origin (the middle of its footprint, on the 0.01 m grid) so vertex positions stay
  small; the Unreal exporter maps them to Unreal's frame as it does the blockout.
- Names follow M10 ids; Unreal asset names replace dots with underscores, as the exporter
  does.

## 7. Interfaces

- **Unreal exporter** (`docs/unreal_export.md`): one exporter for every stage, introduced by
  M15 (`citygen unreal`), which imports the blockout by key and hash (`cg.key`, `cg.hash`
  actor tags; a second import changes nothing, a regenerated district changes only its
  actors). assetgen contributes entries in its manifest format, keyed by the same ids and
  layered over stage 1's: its own entry for every key it has an asset for, the blockout's
  for the rest, `replaces` where its pieces supersede joined ones (street meshes); parts and
  prop variants as instanced kinds per tile, or merged into the shell where a part repeats
  fewer than about 8 times. What the exporter lacks for assets arrives with the milestone
  that needs it (section 14, the **Unreal** line of each): per-building pivots (the
  blockout's meshes sit in world space), textured master materials with Custom Primitive
  Data, simple collision, LOD chains on non-Nanite pieces, distance field and Lumen card
  settings (M15 leaves them off), HLOD layers.
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
- **Foliage**: Nanite with `ShapePreservation` `Voxelize` (in 5.8, still experimental;
  AG0's test tree builds with it from Python), else LOD chains and impostors.

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

**Measured in AG0's spike** (Unreal 5.8.4 on the M4 Pro Mac, shared with other sessions at
a load of 15 to 25; `docs/progress/AG0/README.md`). The tower: 975,476 source triangles,
flat-shaded faces (no vertex shared between faces of different planes), UV0, UV1 and vertex
colors; "lean" is the same tower without UV1 and colors. Sizes per million source triangles:

| Quantity | Tower | Lean tower | Small buildings (shopfront row 1.3 k, shanty 10.6 k triangles) |
|---|---|---|---|
| source glTF | 89 MB (68 MB with `KHR_mesh_quantization`) | 68 MB | 111 and 97 MB |
| Nanite build in the editor (Interchange import) | 72 s | 23 s | 0.3 s and 2.9 s per building |
| editor package (`.uasset`, the source mesh) | 6.6 MB | 6.5 MB | 158 and 21 MB (fixed overhead dominates) |
| Nanite, GPU when resident | 73.5 MB | 48.4 MB | |
| **cooked** (Mac, loose `.uasset`, `.uexp`, `.ubulk`) | **69.6 MB** | **46.3 MB** | 85 and 139 MB |
| distance field and Lumen cards (per mesh, not per triangle) | +4.3 MB cooked, 10 to 15 s | | +1.8 and +3.3 MB cooked, 4.5 to 6.5 s |

So Nanite costs about 70 bytes per source triangle as the spike writes meshes (46 without
UV1 and colors), not 14: its cluster hierarchy holds about twice the source triangles (the
build log's input counts), and faces that share no vertices and carry two UV sets and colors
cost the most. `KHR_mesh_quantization` shrinks only the source files (Interchange
dequantizes; positions within one quantization step, 2 mm on the tower). Distance fields are
capped at 126 voxels a side, so they cost about the same for a shed as for a tower: 1.6 to
3.1 MB each.

$$D_{\text{Nanite}} \approx 100\text{ M} \times (46 \text{ to } 70)\text{ B} \approx 4.6 \text{ to } 7\text{ GB per city (cooked)}$$

What this changes, for AG1 onward: weld identical vertices on a face plane and keep UV1 and
vertex colors only on the slots that need them (glass for interior mapping, signs), which
brings shells toward the lean figure; push repeated detail (reveals, sills, fins) into
instanced parts rather than unique shell triangles; leave distance fields and Lumen cards off
for buildings (about 6,000 × 2 to 4 MB = 12 to 26 GB and hours of build per city) and use
hardware ray-traced Lumen on the RTX PC (decision 13.4), screen-space GI on the Mac.

Parts: Interchange does not read `EXT_mesh_gpu_instancing` (it imports the prototype once and
a level import places one actor per node), so instances come from the manifest as
hierarchical instanced meshes: the tower's 14,738 window frames cost one 12.7 KB prototype
plus their transforms. Nanite Assemblies (experimental editor plugin in 5.8) build the same
parts into one mesh in 1.7 s, but that mesh cooked to 125 MB, all inline, so they are not the
route for parts in 5.8.

Source glTF per city: about 89 bytes per triangle as written (68 quantized, 68 lean; lean and
quantized not measured, about 47 by the same per-vertex savings), so 5 to 9 GB for 100 M
triangles; the 6 GB target needs the lean attributes and quantization. In the editor a city's assets are about 0.7 GB of packages
plus their derived data (Nanite and the rest, about the cooked size) in the DDC: 5 to 8 GB.

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

**Compute targets** (M4 Pro: 10 performance cores, 24 GB; AG0 measures and may revise):
- a whole city's assets in under 20 minutes with 10 workers, under 2 GB per worker;
- one district in under 3 minutes, one building in under 10 s;
- the shared library in under an hour, once per library version;
- Blender previews in under 10 minutes (districts at full detail, the whole city from proxies:
  100 M triangles do not fit Blender in 24 GB);
- Unreal import of a city's assets in under an hour. AG0 measured 23 to 72 s of Nanite
  build per million triangles (lean and full attributes) and 0.1 to 0.3 s per small
  building on the shared Mac: 100 M triangles take 40 minutes to 2 hours, so the target
  holds only with lean meshes, or on the RTX PC, or with imports run in parallel (AG9).
  For scale, M15 imports Vesper Bay's 8,544 blockout meshes in 79 s on the Mac and deletes
  meshes at about 50 ms each on a re-import; distance fields and Lumen cards stay off (AG0:
  4 to 15 s and 2 to 4 MB per mesh).

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

**Provisional answers (2026-10-27, until Swagnik overrides).** AG0 took each recommendation
below as its answer so that AG1 can start; any of them can still change.

| | Provisional answer | Where it is set |
|---|---|---|
| 13.1 | No AI models: everything procedural | |
| 13.2 | U1 for every building, U2 for landmarks and heroes; $k = 4$ discrete genes apart outside a complex; parts shared between buildings when their quantized parameters coincide | asset spec defaults `uniqueness`, `hero_uniqueness`, `min_gene_distance`, `share_parts` |
| 13.3 | Textures generated; fonts decided later (AG8) | |
| 13.4 | The RTX 4070 Ti PC at 1440p with Nanite and Lumen sets the budgets; 512 px/m in the street band (256 px/m above) | `texel_density_px_m`, `texel_density_upper_px_m` |
| 13.5 | The Mac for now (one city's assets and one imported city at a time) | |
| 13.6 | Interior mapping only (the spike's glass master does it) | |
| 13.7 | The asset spec written by a session from the prompt through the `assetgen` skill; no mood boards | `.claude/skills/assetgen/SKILL.md` |
| 13.8 | Pure Python generators, Blender for previews only | |
| 13.9 | Open: before AG13 starts (grass in Unreal) | |
| 13.10 | Open: before AG12 starts (sea waves) | |

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
   only if AG6 previews fall short.
4. **Target hardware and detail.** Which machine sets the budgets: the RTX 4070 Ti PC as the
   minimum spec at 1440p with Nanite and Lumen (recommended), or the M4 Pro Mac. This fixes
   triangle density (section 11) and texel density (512 px/m proposed).
5. **Where heavy work and storage live.** Assets are not in git. The Mac has about 90 GB free;
   is there an external drive or room on the Windows PC (how much)? Can sessions reach the
   Windows PC (SSH, or a local Claude Code there) for the Windows determinism check and full
   imports?
6. **Interiors.** Interior mapping only (recommended for v1), enterable interiors for M11
   points of interest as a stage 2 milestone (AG11: bars, clinics, apartments; large
   scope), or left to the projects that use the cities.
7. **Art direction input.** Asset spec per city written by a session from the prompt
   (recommended), with review rounds on renders; do you want to give reference images per era
   or district (mood boards) that the skill reads, as citygen reads concept maps?
8. **Geometry route.** Confirm pure Python generators with Blender for previews (section 8)
   over geometry nodes or Unreal PCG.
9. **Grass in Unreal** (AG13).
   - (a) Baked per tile: assetgen scatters the clumps, the exporter places them as instanced
     meshes per tile that fade out at 60 to 100 m. Deterministic, testable, the same in the
     Blender previews, streamed with the tile by World Partition; heavy at city scale (Delta
     Megacity's open land at one clump per 0.25 m2 is several million instances), so a
     per-tile cap. *Recommended* first.
   - (b) Generated around the player at run time by Unreal's PCG (GPU runtime generation from
     the ground pieces and AG13's density textures): light on disk and memory, but more engine
     machinery, seeded rather than baked, and nothing to match in the Blender previews. If
     (a) misses its budgets.
10. **Sea waves** (AG12).
   - (a) In the water master: waves by world position offset on a finer sea surface, keyed
     by id like every other piece, no physics. *Recommended*.
   - (b) Unreal's Water plugin ocean: better waves, buoyancy and an underwater view built in,
     but built around Landscape (the cities' ground is heightfield meshes), with a water
     zone and render mesh of its own, less mature, and harder to key by id. Only if stage 4's
     boats need its buoyancy.

## 14. Milestones

Stage 2's milestones carry the prefix AG. Each is one local session in its own worktree and
ends with tests passing, the sample cities built with its assets, previews in
`docs/progress/AG<n>/` (snapshots in `wip/` while it runs), its entry in
`docs/assetgen_milestones.md`, its row and images in the README's stage 2 section, and the
Unreal exporter updated for what it adds (its **Unreal** line below; CLAUDE.md, "Unreal
exporter"). A milestone session need not run Unreal: when it is done, the coordinating
session decides whether to run an Unreal check in a separate session. "Mac = x86" means the
manifest (from AG6 also the decoded pixels) is the same on the Mac and in the x86 Linux
docker image; Windows joins in AG9.

| AG | Milestone | Needs | Can run beside |
|---|---|---|---|
| AG0 | Contract and spike | M10; M15 | M13 |
| AG1 | Building shells | AG0; decisions 13.2, 13.8 | AG7, AG8 |
| AG2 | Facades | AG1 | AG6, AG7, AG8 |
| AG3 | Street fronts | AG2 | AG6, AG7, AG8 |
| AG4 | Roofs and connections | AG3 | AG6, AG7, AG8 |
| AG5 | Types, landmarks and slopes | AG4; M13 | AG6, AG7, AG8 |
| AG6 | Materials and textures | AG1; decisions 13.1, 13.3 | AG2 to AG5, AG7, AG8 |
| AG7 | Street elements | AG0; M13 for grades | AG1 to AG6 |
| AG8 | Props, plants and signs | AG0; decision 13.3 | AG1 to AG6 |
| AG9 | Scale and release | AG5 to AG8, AG12 to AG15; decision 13.5 | |
| AG10 | Layered districts | AG9; M14 | AG11 |
| AG11 | Interiors (only if decision 13.6 asks) | AG9 | AG10 |
| AG12 | Water (14.13) | M16; AG6, AG7; decision 13.10 | AG4, AG5, AG13 |
| AG13 | Ground cover and grass (14.14) | M16; AG6, AG8; decision 13.9 | AG4, AG5, AG12 |
| AG14 | Fit and finish (14.15) | AG4, AG7, AG8; M17 to M21 | AG12, AG13 |
| AG15 | Cyberpunk facades and night (14.16) | AG14, AG6; M20, M21 | AG12, AG13 |

### 14.1 AG0: Contract and spike

- **Adds:** package `assetgen/` (CLI `python -m assetgen`); the asset spec schema with era
  presets (`assetgen spec validate|schema`) and a first `assetgen` skill; `assetgen brief`
  (`briefs.json` and a brief hash per building: edge classes, floor grid, neighbors, mounted
  props, sign slots, M13 bases where present) and `assetgen brief diff`; a deterministic
  glTF writer; the exact integer triangulator; the determinism harness (Mac and the x86
  docker image).
- **Unreal:** assetgen's contribution to the exporter (entries keyed by id, layered over
  the blockout, `replaces`), on the exporter's own package once M15's move is done. The
  spike, in a throwaway Unreal 5.8 project of assetgen's own, imports three generated
  buildings through it (a 1 M triangle tower, a shopfront row, a shanty stack) with Nanite,
  parts as instances, Custom Primitive Data, opaque glass with interior mapping and simple
  collision, and measures import time, editor disk and cooked size per million triangles,
  distance field and Lumen card cost, whether Interchange reads `KHR_mesh_quantization` and
  `EXT_mesh_gpu_instancing`, and the state of Nanite foliage in 5.8.
- **Done when:** every building of every sample has a brief, Mac = x86; M10's regenerated
  districts change only the briefs of their district and seam; the spike's numbers replace
  the estimates of section 11; the decisions of section 13 are answered.
- **Shows:** `preview_edges.png` (every facade edge colored by class: front, street, alley,
  canal, party, blind); the three spike buildings in Blender and in Unreal.

### 14.2 AG1: Building shells

- **Adds:** the genome (5.1.1: district palette, property family, building genes); the split
  grammar (5.1.2) with six facade systems that cover every era (unitized curtain wall,
  punched concrete, precast panel, punched brick, corrugated industrial, shanty patchwork);
  shells with window openings and reveals, slabs, parapets and cornices, two UV sets, vertex
  colors, a flat preview material per slot; far proxies (section 8); `assetgen build`,
  which keeps every asset whose key and hash are unchanged; Blender previews (districts and
  the blockout's street cameras at full detail, the whole city from proxies, contact sheets
  per type); checks for coverage, envelope, meshes and uniqueness on genomes.
- **Unreal:** shells replace their blockout boxes by id, with per-building pivots, a
  material instance per slot, simple collision from the masses and the proxies as Nanite
  fallback meshes; the first assets in the level.
- **Done when:** every sample building has a shell and a proxy; the checks pass; a whole city
  builds in under 20 minutes and a second build writes no file; Mac = x86.
- **Shows:** the first modelled whole-city render, a district up close, a contact sheet.

### 14.3 AG2: Facades

- **Adds:** windows, mullions, spandrels, balconies, louvers, fins and panels as parts
  (5.1.4: generated in their own frame, quantized, hashed, instanced within a building); the
  rest of 5.1.2's facade systems (spandrel ribbon, fin wall, diagrid and exoskeleton,
  board-marked brutalist concrete, stucco with shutters, timber infill, standing seam,
  louvered industrial, capsule stacks, clean-tech skins, hangar cladding); massing
  articulation (pipeline stage 3: chamfers, rounded corners, setback ledges, cantilevers,
  crowns, mechanical bands, podium canopies); irregularity by grime and wealth.
- **Unreal:** parts as instanced kinds (or merged into the shell where a part repeats fewer
  than about 8 times), with the instances' building ids.
- **Done when:** the uniqueness check (genes and thumbnail hashes) passes in every sample;
  triangle and instance budgets per building class are met; Mac = x86.
- **Shows:** towers of each era up close; a contact sheet of 64 buildings drawn at random.

### 14.4 AG3: Street fronts

- **Adds:** a shopfront per ground-floor unit by its use (5.1.3); doors at every entrance;
  lobbies, loading docks, garage mouths and gates; awnings, sign boxes at the sign slots,
  shutters and grilles; mounts for AC units, wall lights, scaffolding, cables and facade
  greenery; party walls (fire walls, ad and graffiti surfaces) and blind walls; the access
  check (a door at every entrance, open to its walkway) and the mounts check (on a panel or
  pier, never on glass).
- **Unreal:** complex collision in the ground band, so doorways, steps and awning posts
  collide as drawn; doors tagged with their entrance and walkway ids for stage 4.
- **Done when:** the access and mounts checks pass; the blockout's street cameras show
  buildings that read as distinct (reviewed with Swagnik); Mac = x86.
- **Shows:** street-level renders from the blockout's cameras.

### 14.5 AG4: Roofs and connections

- **Adds:** parapets and roof finishes, pitched roofs where the era has them, equipment
  generated for every roof item (AC units, water tanks, antennas, billboard frames,
  penthouses, helipads and AV pads with markings), green roofs, access huts; facade details
  (downpipes, fire escapes, vents, cables, cameras); skybridges by kind with their landing
  openings; sky tube portals and sky stations; podium decks and atrium interiors.
- **Unreal:** skybridges replace their blockout pieces by id; roof equipment as instanced
  kinds.
- **Done when:** every roof item, skybridge and portal has an asset; the envelope check keeps
  skybridge, transit and sky tube clearances; Mac = x86.
- **Shows:** an aerial view over a dense district's roofs; a skybridge and a sky tube portal
  up close.

### 14.6 AG5: Types, landmarks and slopes

- **Adds:** generators per M3 type where the general one falls short (shanty stacks,
  megabuildings with their courts, towers and decks, warehouses, sheds, yards, hangars,
  labs, villas, terraced rows, temple halls, pagodas, gate houses, terminals, control
  towers, stations, parking structures, straddle buildings); complex families (twin towers
  mirrored, clusters, campuses, bridged pairs); a hero generator for every landmark kind
  (three-armed megatower, spire, arcology, wheel) with U2 bakes; buildings on M13's slopes
  (stepped plinths from `plinth_m` up to `base_m`, retaining walls, entrances at grade); the
  art-direction loop (`assetgen review` and asset spec rounds through the skill, as
  citygen's).
- **Unreal:** hero bakes as per-building textures; plinths meeting M13's terrain.
- **Done when:** every type, complex and landmark of the samples and of M13's hilly sample
  has its generator; two art-direction rounds on Vesper Bay; Mac = x86.
- **Shows:** the landmarks at 8K; one district per era; buildings on a slope.

### 14.7 AG6: Materials and textures

- **Adds:** the library generator (5.2, as decisions 13.1 and 13.3 settle it): tileable sets
  per era, trim sheets, decal atlases, window interior atlases, road atlases; per city,
  signage atlases from M11's names and unit uses, brand logos and ad content; per-building
  material parameters and vertex colors; Blender materials that match the Unreal masters;
  the texel density check.
- **Unreal:** the textured master materials (facade, opaque glass with interior mapping,
  metal, concrete, neon, signs, decals, road), texture import, material instances with
  their parameters and Custom Primitive Data per actor.
- **Done when:** the library is within its budget (section 11); textured renders of every
  sample district; decoded pixels Mac = x86.
- **Shows:** a material board per era; textured street views by day and by night.

### 14.8 AG7: Street elements

- **Adds:** everything in 5.3: road surfaces with markings, crosswalks, sidewalks and curbs,
  medians and junctions; bridges by kind; decks, ramps, viaducts and interchanges (M7, M8d,
  M12) with parapets, joints and columns; tunnels (M9); quays, canal walls and piers;
  transit guideways, beams, maglev tracks, sky tubes and pylons; megasite elements; all on
  M13's grade lines with embankments and retaining walls where a city has terrain. Written
  per 256 m tile and keyed by ids.
- **Unreal:** street meshes per segment and junction that `replaces` M15's joined pieces;
  sky tubes as non-Nanite meshes with LOD chains.
- **Done when:** every street element of the samples has an asset; a regenerated district
  rewrites only its tiles' street packs; Mac = x86.
- **Shows:** an interchange at 8K; street views with the new streets.

### 14.9 AG8: Props, plants and signs

- **Adds:** 4 to 12 generated variants per M6 prop kind and district style; trees by
  species (space colonization), shrubs, ivy and ground cover; an asset for every M11 sign
  slot (shop signs with their text, neon tubes along glyph outlines, billboards, holo-ads,
  neon bands), in the fonts decision 13.3 allows.
- **Unreal:** the variants as instanced kinds replacing M15's prototypes; signs as actors
  per slot; holo-ads and translucent sign faces as non-Nanite meshes with LOD chains;
  Nanite `Voxelize` for trees (AG0), LOD chains where it falls short.
- **Done when:** every prop kind, plant species and sign slot has an asset; instance budgets
  are met; Mac = x86.
- **Shows:** variant sheets per district style; a neon street at night.

### 14.10 AG9: Scale and release

- **Adds:** every sample at full detail where disk allows (the rest at proxy level, or on
  the Windows PC); `assetgen sweep` over the M8a suite's cities (no crash, budgets); the
  determinism check on Windows; `assetgen lock` and `--verify`.
- **Unreal:** HLOD layers, distance field and Lumen card settings at city scale, import time
  and disk per city within section 11.
- **Done when:** the sweep runs without a crash; the Mac, x86 Linux and Windows agree;
  budgets are met (AG12's water, AG13's grass and AG15's lights included); the README's stage 2 section
  shows every sample city.
- **Shows:** whole-city renders of every sample at 8K, in Blender and in Unreal.

### 14.11 AG10 and AG11: after v1

- **AG10, layered districts** (after M14): buildings that stand on M14's deck levels
  (facades from their deck, deck undersides, supports, stair and elevator cores) and street
  elements on the decks, with their entries in the exporter; done when M14's samples pass
  every assetgen check.
- **AG11, interiors** (only if decision 13.6 asks for them): enterable interiors for M11's
  points of interest (bars, clinics, vendors, apartments), generated from the unit's
  footprint and use.

### 14.12 Order and sessions

```
 AG0 ─┬─> AG1 ─> AG2 ─> AG3 ─> AG4 ─> AG5 ──┐
      │     └──> AG6 ───────────────────────┤
      ├─> AG7 ──────────────────────────────┼─> AG9 ─> AG10 (after M14), AG11 (if asked)
      └─> AG8 ──────────────────────────────┤
 M17 to M21 ─> AG14 (fit) ─> AG15 (night) ──┤
 M16 ─┬─> AG12 (water) ─────────────────────┤
      └─> AG13 (ground cover, grass) ───────┘
```

- **The building line** (AG1 to AG5) runs one session at a time: each builds on the last
  one's generators.
- **Side lines:** AG6, AG7 and AG8 share no generator code with the building line
  (materials, streets and props live in their own modules), so each can run beside it as a
  separate local session once its prerequisite is merged (AG0; for AG6, AG1, which fixes the
  material slots). At most two assetgen sessions at a time, since citygen sessions share
  the Mac; shared files (CLI, manifest, report, the exporter's core) change in one session
  at a time.
- **Unreal throughout:** the first assets reach the level with AG1, and every milestone
  after it brings what it adds. After each one the coordinating session decides whether to
  run an Unreal check in a separate session (likely after AG1, AG3, AG6, AG7, AG8 and AG9,
  which change what the level holds or how it imports).
- **The core** is AG0 to AG3: every building has a model of its own that reads as its own
  from the street.
- **Water and grass** (AG12, AG13) come after stage 1's M16 and before AG9, so the release
  has real water and ground; they share no generator code with each other or with the
  building line, so each can run beside AG4 and AG5 as a separate session.
- **The first run-through's fixes** (AG14, AG15; `docs/run_through_1.md`) come first: AG14
  after stage 1's M17 to M21 (it draws what they add), AG15 after AG14 (both change the
  shell), before AG5, AG12 and AG13.
- **Stage 1 milestones assetgen waits on:** M15 and the exporter's move to its own package
  before AG0's Unreal part, M13 for AG5's slopes and AG7's grades (until then flat ground at
  z 0), M14 for AG10. The asks of section 4.5 go to citygen sessions; each milestone derives
  what it needs in the brief meanwhile.

### 14.13 AG12: Water

- **Adds:** per water body and 256 m tile, keyed by the body's id: a surface mesh at its
  level (M13's profile along a river), finer on the sea, carrying the flow direction and
  speed (M16) and a foam mask along walls, banks and bridge piers; a bed at M16's depth
  and profile (mud, sand or stone by kind); banks by M16's bank kind (natural slopes,
  beaches, riprap stones as instanced parts, marsh edges) meeting AG7's quays and canal
  walls without a gap; for AG6: water normal and foam maps, caustics, bed sets, and a
  catalog entry per water kind (sea, river, canal, ornamental basin, marsh water: color,
  clarity, flow speed, foam).
- **Unreal:** an `M_CgWater` master in the Single Layer Water shading model (color deepening
  with depth, flow-mapped ripples, depth foam; the sea's waves by decision 13.10); the
  surfaces as non-Nanite meshes with LOD chains (Nanite does not take the shading model);
  the pieces replacing the blockout's `sea` and `water` objects by key; an underwater
  post-process volume per body beside M16's swim volume.
- **Blender:** a water shader in the previews that matches the master.
- **Done when:** every water body of the samples has its surface, bed and banks; each
  surface at its level, each bed at its depth below it, no gap between bank, bed and wall
  (a check); budgets met; a regenerated district rewrites only its tiles' water; Mac = x86.
- **Shows:** a canal and a river bank up close by day and by night; the harbor from above.
- **Later stages:** wind, rain and fog on the water and the underwater look (stage 3);
  boats moving with buoyancy and wakes, ferries (stage 4).

### 14.14 AG13: Ground cover and grass

- **Adds:** for AG6, tileable sets for lawn, meadow, dirt, mud, gravel, sand, moss and
  rubble; per tile, the ground pieces of every piece of open land (M16's cover kinds),
  their sets blended by M16's wear (paths and desire lines), shade and edges; grass and
  small plants as generated clump meshes per cover kind (short lawn, long meadow, reeds
  and cattails, weeds, clover, flowers in the district's palette, ferns under trees), a
  few variants each, scattered deterministically by density (none on paths, desire lines
  or under decks, sparse in deep shade, thicker near water); AG8's ground plants (sedum,
  scrub) folded in.
- **Unreal:** the ground pieces replacing the blockout's lawns, parks, greens and verges by
  key; the grass as decision 13.9 settles it (instanced per tile fading out at 60 to 100 m,
  no collision, or generated around the player at run time); an `M_CgGrass` master that
  sways in the wind, reading a `Wind` value in `MPC_CityGen` that stage 3 drives later.
- **Blender:** the grass through the geometry-nodes instancing AG8 uses.
- **Done when:** every piece of open land of the samples has its ground and cover; no grass
  through paving, a building or water (a check); instance and triangle budgets met per tile
  and city; a regenerated district rewrites only its tiles; Mac = x86.
- **Shows:** a park and a wasteland lot at street level; a lawn edge with a worn path.
- **Later stages:** wind and seasons (stage 3); people on the lawns (stage 4).

### 14.15 AG14: Fit and finish

From the first run-through (`docs/run_through_1.md`): the stage 2 side of M17 to M21, and
checks on the generated meshes.

- **Adds:** junction pieces drawn from M18's `edge_z`, meeting every leg at its cut edge
  (now an inverse-distance blend that misses a leg's height there, a step at every sloped
  leg); quays, their railings and props at one height (M20); roof equipment seated on the
  roof surface under it (dunnage on a pitched form; no AC unit floating over a roof); curved
  walls tessellated from M21's arcs by chord sag (2 cm at most) with smooth normals across
  the curve, bays and windows following it; M19's cap beams, masts and piers; M18's
  embankments; crosswalk widths from the model. Two checks on the meshes: `asset_grounded`
  (every part, prop, plant, roof item and street piece rests on a surface under it within
  2 cm) and `asset_clash` (street pieces against building meshes and their parts: no road,
  ramp or embankment into a building; bridge pieces against each other; transit structures
  against buildings except through a cut portal). The run-through's model checks found no
  road in a building mass and no overlapping bridges on Delta, so those came from the meshes
  (a part or front over the road, a piece reaching past its corridor, a bridge drawn twice):
  the clash check finds them, the fix follows.
- **Unreal:** nothing new; the pieces replace their blockout objects as before.
- **Done when:** both checks pass on every sample; a sloped junction, a quay and a round tower
  read clean up close; budgets met; Mac = x86.
- **Shows:** a junction at a bridge approach, a quay with its railing, a round tower up close.

### 14.16 AG15: Cyberpunk facades and night

- **Adds:** facades that are not rows of rectangles: ribbon and slit glazing, diagonal and
  diagrid glazing, honeycomb and hexagonal panels, punched windows of mixed sizes, staggered
  and stepped bays, angled and folded glass, fritted and colored glass, perforated metal and
  mesh screens, LED-strip mullions and fins, pod and capsule windows, media facades; two or
  three finishes per building, colored glass, emissive strips; genomes that reach further
  in the corporate core and midtown, and `asset_unique` by neighbors (towers within 150 m
  differ in system, window pattern and palette, by day and in night thumbnails). **Night:**
  every building lit its own way: the lit share of its windows by use and hour band
  (offices in bands of floors, homes scattered, hotels warm, vacant towers dark), mixed
  color temperatures, crown and edge lighting, vertical LED strips, logo signs; assets for
  M20's new sign kinds, emissive, with real lights where they wash a facade.
- **Unreal:** the night patterns in the facade master (Custom Primitive Data per building:
  lit share, color, pattern seed, schedule) driven by `MPC_CityGen`'s Night and hour; street
  lights that light the ground: a downward spot light under each lamp head, outside the lamp
  mesh's shadow, the 128 to 256 lamps nearest the player lit (shadowless past the closest
  few) and light-pool decals under the rest (the run-through's streets were black at night);
  emissive windows and signs tuned against the night exposure.
- **Blender:** night previews with the patterns.
- **Done when:** the uniqueness check passes with the neighbor rule; no two neighboring
  towers of a sample's corporate core look or light alike (reviewed with Swagnik); streets
  under their lamps read lit at night in Unreal; budgets met; Mac = x86.
- **Shows:** the corporate core by day and by night; a street at night under its lamps.
- **Later stages:** the full night (fog, rain, reflections, light shafts) is stage 3's.

## 15. Running it

- Local sessions only (no cloud credits); one milestone per session in its own worktree
  (14.12 for which can run at once).
- Package `assetgen/` beside `citygen/`, importing citygen's model, `dmath` and `geom`
  (read only; never edited from an assetgen session); tests in `tests/assetgen/`; skill
  `.claude/skills/assetgen/SKILL.md`.
- Per CLAUDE.md's layout by stage: this spec, the milestone log
  `docs/assetgen_milestones.md`, and the README's stage 2 section (a row per milestone,
  images of the newest builds, every 3D render at 8K, written for people who use the
  generator, not about how it is verified).
- Progress in `docs/progress/AG<n>/`, with snapshot images in `wip/<NN>_<step>/` pushed to
  the session branch at least every hour or so; generated assets never in git (previews,
  reports and small goldens only).
- Unreal: every milestone updates the exporter for what it adds; Unreal checks run in a
  separate session the coordinating session dispatches, in a throwaway project of its own
  (UE 5.8 at `/Users/Shared/Epic Games/UE_5.8` on the Mac), results in
  `docs/progress/AG<n>/unreal/` (`docs/unreal_export.md`); heavy scenes on the Windows PC.
- citygen changes assetgen needs (section 4.5) go to citygen sessions.

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
