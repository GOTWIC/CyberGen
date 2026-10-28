# AG6: materials and textures

Every building and street piece now has textured materials: a library of tileable texture
sets in each era's look, trim sheets, decal and road atlases, window interiors that show a
room behind every window by day and light it by night, and per city the signs of its
shops, bars and clinics in their districts' scripts, brand logos and ads. Everything is
generated (decision 13.1: no AI models; 13.3: no font files yet), in numpy and PIL,
deterministic to the pixel. The same materials are built in Blender for the previews and as
Unreal masters for the exporter.

| Command | What it does |
|---|---|
| `assetgen library [OUT] [--density 512]` | the shared library (made once, kept while its generator is unchanged): `~/.cache/cybergen/assetgen_library/d512` or `$ASSETGEN_LIBRARY` |
| `assetgen build BUILD [--spec S]` | as before, then the library (made if missing) linked as `BUILD/assets/library`, the city's sign, ad and logo pages (`textures/`, `signs.json`), `materials.json`, textured contributions, `unreal_contribution.materials.json`, `materials_report.txt`; `--no-textures` keeps AG1's flat materials |
| `assetgen materials preview BUILD [--night] [--views ...]` | textured Blender renders: districts, the blockout's street cameras, cameras of one's own; by day, and by night with the windows, signs and street lights lit |
| `assetgen materials board OUT` | a material board per era, one of the building parts and one of the street surfaces |

## The library

| | |
|---|---|
| Sets | 113 (60 per era: six surfaces in ten eras; 22 shared building surfaces; 31 street surfaces) |
| Atlases | 14 (ten trim sheets, decals, road, window interiors, macro) |
| Density | 512 px/m on the street band, 256 px/m on roofs (decision 13.4); sets 1 to 4 m |
| Size | 655 MB of PNG, about 966 MB cooked with mips and block compression |
| Time | 80 s on the M4 with 3 workers (167 s while sample builds ran) |
| Where | `~/.cache/cybergen/assetgen_library/d512` (or `$ASSETGEN_LIBRARY`), linked from each build; not in git |

Each **set** is three maps: base color with height in alpha, a tangent-space normal
(OpenGL), and occlusion, roughness, metallic with the tint mask in alpha. Where the mask is
1 a building's tint replaces the set's mean color there (its `ref`); where it is 0 (mortar,
panel joints, sealant, rust) the set keeps its own color. A set covers 1 to 4 m at 512 px/m
(roofs at 256 px/m), so its size is a power of two.

- **Per era** (ten eras): concrete (board marks, form joints and tie holes, smooth or worn
  by era), plaster or stucco (coarse or fine, patched, cracked), brick (English bond and
  burnt headers in heritage districts, sooty in industrial ones), precast panels (panel size,
  joints and exposed aggregate by era), metal cladding (corrugated, trapezoid or standing
  seam) and the flat roof (tar, gravel or membrane).
- **Shared building surfaces**: spandrel enamel, painted trim, structure concrete, painted and
  dark metal, aluminum, louvers, perforated skins, standing seam, hangar ribs, the shanty
  patches (galvanized sheet, rusted corrugation, tarp, painted panel, plywood), timber,
  shutters, stone sills, roof tiles, capsule pods.
- **Street surfaces**: asphalt per road class (aggregate, wear, sealed cracks, oil), patches,
  road paint, cast iron, tactile paving, ten paving families (cobble, tiles, granite,
  concrete slabs, cast concrete, concrete tiles, resin, brick pavers, timber), granite
  curbs, smooth and formed concrete, stone blocks, glazed tunnel tiles, steel, ballast,
  lawn, containers, tanks, pads.
- **Atlases**: trim sheets per era (window frame, sill, cornice, panel joint, railing, metal
  edge, rubber seal, louver strips; for AG3's parts, whose UVs will map onto them), the
  decal atlas (grime, leaks, rust, cracks, graffiti, posters, stickers, moss: the facade
  master draws rain streaks from it, AG3 and AG8 place the rest), the road atlas (oil,
  cracks, patches, tar snakes, skid marks, a manhole, a drain, arrows, a puddle, sand, dust:
  the road master lays one stain per 8 m cell by hash), window interiors (below) and a macro
  map that breaks up tiling over 64 m.

**Material boards** (`assetgen materials board`):

| Corporate glass by day | Corporate glass by night |
|---|---|
| <img src="boards/board_corporate_glass.jpg" width="420"> | <img src="boards/board_corporate_glass_night.jpg" width="420"> |

| Heritage | Neon retro |
|---|---|
| <img src="boards/board_heritage.jpg" width="420"> | <img src="boards/board_neon_retro.jpg" width="420"> |

| Shared building surfaces | Street surfaces |
|---|---|
| <img src="boards/board_building_parts.jpg" width="420"> | <img src="boards/board_streets.jpg" width="420"> |

Every era's board: [`boards/`](boards).

## Window interiors

The glass master shows a room behind every window without any data per pane: rooms are
the cells of the building's own grid on its facades (UV0 is meters along the facade and up
from the base; a room is the building's bay wide and a floor high), the view ray goes into
the cell's box in the facade's frame, and the point it hits is looked up in an atlas of
rooms drawn in one-point perspective (six uses, office, apartment, capsule, shop, club,
warehouse, by eight variants, by day and lit by night). A room's variant, whether it is lit
(the building's lit-window ratio) and its blinds come from a hash of its cell. Storefronts
always show shops. AG1's per-pane UV1 and vertex window ids are not read any more.

## Signs

| City | Sign slots | Sign texts (wide, tall) | Brands | Textures | Sign pages, cooked |
|---|---|---|---|---|---|
| Vesper Bay | 15,448 | 411 (165, 246) | 15 | 243 | 69 MB |
| Nexus City | 17,456 | 517 (236, 281) | 16 | 238 | 71 MB |
| Delta Megacity | 14,983 | 427 (206, 221) | 15 | 189 | 69 MB |
| Saltreach Free Port | 7,632 | 222 (109, 113) | 14 | 189 | 46 MB |
| Greyhook | 8,183 | 310 (140, 170) | 14 | 207 | 69 MB |
| Vesper Bay Pinned | 16,209 | 366 (145, 221) | 6 | 231 | 69 MB |
| Vesper Bay Stacks | 16,219 | 369 (144, 225) | 5 | 234 | 69 MB |
| Cragmouth | 19,694 | 556 (250, 306) | 12 | 199 | 74 MB |

Every sign slot of M11 gets a cell of a sign page: the name of the point of interest in its
unit (a bar, club, arcade, clinic or vendor), else a shop name drawn for its district and use
from M11's word lists and a use word ("JADE KOI RAMEN"), a neon band its district's name, a
lobby its owner's brand; in a script drawn from its district's weights (Latin as written;
Cyrillic, katakana and Hangul transliterated by syllable from in-repo stroke shapes;
Hanzi-like and Devanagari-like signs composed from strokes, decorative, not words), as neon,
a lightbox or LED rows, in the district's neon colors. Billboards and holo-ads show 16 ads
each of the city's brands (their logos, a headline). AG8 builds the sign meshes on these
cells (`signs.json`); the previews put a quad on each slot.

## Vesper Bay

Every district at full detail around its middle, far buildings as proxies (1800 px each):

<img src="vesper_bay/districts.jpg" width="840">

The blockout's street cameras with the textured shells, street packs, sign quads on the sign
slots and, by night, the windows, signs and street lights lit:

| Corporate Core | Corporate Core by night |
|---|---|
| <img src="vesper_bay/street_1.jpg" width="420"> | <img src="vesper_bay/street_1_night.jpg" width="420"> |

| The Stacks | The Stacks by night |
|---|---|
| <img src="vesper_bay/street_2.jpg" width="420"> | <img src="vesper_bay/street_2_night.jpg" width="420"> |

| Scholar Isle | Scholar Isle by night |
|---|---|
| <img src="vesper_bay/street_3.jpg" width="420"> | <img src="vesper_bay/street_3_night.jpg" width="420"> |

| Under the ring viaduct | Old Town |
|---|---|
| <img src="vesper_bay/street_4.jpg" width="420"> | <img src="vesper_bay/street_5.jpg" width="420"> |

NIGHT_DISTRICTS

The Stacks at 8K by day and by night (the root README's pair):
[`vesper_bay/8k/street_2.jpg`](vesper_bay/8k/street_2.jpg),
[`vesper_bay/8k/street_2_night.jpg`](vesper_bay/8k/street_2_night.jpg).

## Every sample, textured

Every district of the other seven samples by day, at full detail around its middle (960 px
each; Greyhook from its reshaped spec):

**Nexus City**

<img src="nexus_city/districts.jpg" width="840">

**Delta Megacity**

<img src="delta_megacity/districts.jpg" width="840">

**Saltreach Free Port**

<img src="archipelago_free_port/districts.jpg" width="840">

**Greyhook**

<img src="peninsula_city/districts.jpg" width="840">

**Vesper Bay Pinned (the hand-traced Corporate Core)**

<img src="vesper_bay_pinned/districts.jpg" width="840">

**Vesper Bay Stacks**

<img src="vesper_bay_stacks/districts.jpg" width="840">

**Cragmouth (on its slopes)**

<img src="cragmouth/districts.jpg" width="840">

## Checks and budgets

Every sample builds with every check passing (citygen's and assetgen's, the materials checks
among them):

| City | Triangles measured | Buildings at density | Streets at density | Street slots below in places |
|---|---|---|---|---|
| Vesper Bay | 20,848,977 | 100.0% | 99.84% | tank |
| Nexus City | 20,663,925 | 100.0% | 99.80% | paving.concrete_cast, steel.joint, tank |
| Delta Megacity | 22,676,005 | 100.0% | 99.78% | steel.joint |
| Saltreach Free Port | 14,445,669 | 100.0% | 99.80% | paving.concrete_cast |
| Greyhook | 10,870,806 | 100.0% | 99.86% | paving.concrete_cast, tank |
| Vesper Bay Pinned | 19,905,528 | 100.0% | 99.54% | paving.concrete_cast, paving.granite, stone.coping, stone.quay, tank |
| Vesper Bay Stacks | 19,514,351 | 100.0% | 99.55% | paving.concrete_cast, paving.granite, steel.joint, stone.coping, stone.quay, tank |
| Cragmouth | 21,005,118 | 100.0% | 99.81% | asphalt.alley, concrete.deck, paving.concrete_cast |

- **Texel density**: per slot, at least 99.5% of the textured area at 0.75 of its band's
  density (512 px/m on the street band, 256 on roofs) or better. Buildings meet it
  everywhere; the street pieces below it are tank cylinders, a few curb, barrier and coping
  sides with plan-projected UVs and the outer edge of tight curves (AG7's UVs, listed in
  `materials_report.txt` with the worst piece per slot).
- **Texture budget**: the library under 2.5 GB cooked (966 MB) and 7 GB of source (655 MB);
  a city's sign pages under 0.3 GB cooked (46 to 74 MB).
- **Determinism**: decoded-pixel goldens for seven maps of a 32 px/m library and the small
  test city's material files (`tests/assetgen/data/golden_hashes.json`, `ag6`).

## Unreal check: what to look at

The exporter takes the textures and masters (`docs/unreal_export.md`, AG6), but no Unreal
ran in this session. The check should import a city (Vesper Bay or Greyhook) with stage 2 on
a project that has AG1's import, import it again, and look at:

1. **Window interiors on curtain walls** (the reason for the redesign): towers of the
   Corporate Core up close and from a distance, by day and with `MPC_CityGen.Night` at 1.
   Each window should show a whole room (back wall, floor at the bottom, ceiling at the top,
   side walls) that moves with the view; no white triangles, diamonds or sawtooth across
   panes that share corners. If rooms show upside down or slide the wrong way, the tangent
   frame's v runs the other way in Unreal: flip `v.y` (or `v.x`) in `ROOM_CODE`
   (`citygen/ue/import_city.py`). If a whole facade shows one room, UV0 did not come
   through in meters.
2. **Lit windows at night**: about the building's lit ratio of rooms lit, whole rooms, not
   per triangle; storefronts showing shops.
3. **Textures and their orientation**: brick courses horizontal, board marks and panel
   joints level, rain streaks running down from the tops of buildings, grime at the foot of
   walls; normal maps lit from the sun's side (the importer flips the green channel of the
   library's OpenGL normals; if relief looks inverted, that flip is wrong).
4. **Tints**: each building keeps its AG1 tint over its texture (a beige brick building is
   beige brick, mortar grey), and buildings of different eras show their era's walls
   (`<slot>@<era>` instances on their actors).
5. **Roads**: asphalt with aggregate and stains, markings worn, paving per district.
6. **Re-import**: a second import changes nothing (textures kept by pixel hash, the
   instances by their parameters); Core/Textures is shared by every city of the project.
7. **Cost**: import time of about 250 textures (about 1 GB cooked for the library) and the
   shader compile of the new masters; GPU memory with texture streaming.

## For later

- **AG2 or AG3**: vertex colors baked into the shells (grime under sills, edge wear), which
  waited for AG2's shell changes to merge; dropping UV1 and the window ids from the glass
  slots (unused now) for leaner meshes; part UVs onto the trim sheets.
- **AG3 and AG8**: decals placed from the decal atlas (graffiti and posters on party walls,
  leaks), sign meshes on the sign pages (`signs.json`), the logos and ads.
- **AG7**: a few street pieces whose UV0 stretches past a quarter of the density (tank
  cylinders, curb and barrier sides with plan-projected UVs, the outer edge of tight curves)
  are listed in `materials_report.txt`; 0.2 % of the street area in Vesper Bay.
- **Fonts** (decision 13.3): OFL fonts for real Hanzi, Hangul, kana and Devanagari text when
  AG8 decides; the sign pages' layout takes them.
