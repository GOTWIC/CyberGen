# M10: edit, lock and regenerate

M10 makes a built city editable without starting over. Every entity gets a stable id from
what it is and where it sits; one district can be built again on its own while the rest of
the city stays as it was; pins and overrides keep or change single elements; a lock freezes
a city as a release that rebuilds byte for byte; and `citygen model diff` lists what changed
between two builds.

| Command | What it does |
|---|---|
| `citygen build SPEC OUT` | as before; also writes `OUT/city_state.json` (what a later edit needs) and reads `overrides.json` beside the spec |
| `citygen build SPEC OUT --district NAME [--seed N] [--base DIR] [--overrides FILE]` | regenerates one district of the build in OUT (or in `--base`, written to OUT): a new seed when its spec entry is unchanged, else its new fields |
| `citygen model diff A B [--all] [--json FILE] [--png FILE]` | entities added, removed and changed by id, per collection (the changed fields named), and a map of them |
| `citygen lock OUT [--release 1.0]` | writes `OUT/city.lock.json` |
| `citygen lock --verify LOCK [--out DIR]` | builds the city again from the lock alone and compares the bytes |

RESULTS_TABLE

## Stable ids

Before M10 the stages numbered what they made in build order (`rs00012`,
`d03.blk017.lot004`, `d03.prop.bench.00213`), so one more street in one district renumbered
the roads, blocks, lots and props of every district after it. Now every id comes from what
the entity is and where it sits:

| Kind of entity | Id | Example |
|---|---|---|
| has a name of its own (rivers, islands, places, megasites, transit lines, stations, channels) | kind and name | `rv.great_river`, `d02.pl.freeport_plaza`, `stn.crown_exchange` |
| stands somewhere (roads, nodes, blocks, lots, open space, props, plants, walkways, ...) | district (if any), kind and the 1 m grid cell of its bounding box's middle, as compass offsets from the city center | `rs.e1234n567` (1234 m east, 567 m north), `d03.lot.e512n88`, `d03.prop.bench.w41s1210` |
| belongs to a parent | the parent's id and a suffix | building `d03.lot.e512n88.bld`, sidewalks `rs.e1234n567.swl`, lanes `rs.e1234n567.f0`, a lane's connectors `rs.e1234n567.f0.c1`, junction `jn.e1240n570` (after its node) |
| M11 gameplay rows | as M11 named them, under the renamed parent | `d03.lot.e512n88.bld.u03.bar`, `rs.e1234n567.density` |
| districts, `land`, `sea`, fields, factions, tiles | unchanged | `d01`, `field.wealth` |

Two entities with the same id get `.2`, `.3` in the order of their contents (the entity as
JSON with every reference rewritten), never the build order. In a district regeneration an
entity with the kind and geometry of an old one takes the old id first (a held road's node
keeps its id when a new node lands in the same 1 m cell).

**Design: one renaming pass over the finished model** (`citygen/ids.py`), not new id code in
every stage. The stages keep their build-order ids internally: their orders, hash keys and
groups depend on them, and changing those would have moved every city. The pass has one
reference table (`REFS`, the typed id fields of `model.py`) and renames every string in
`attrs` that is an old id or starts with one; a test scans built models for any reference
the pass misses and for any id that still looks like a build counter. It runs twice per
build: once after the transit and road supports, before the props (so the props, plants and
gameplay layer key their random draws and names on stable ids, not on build order: a new
bench in one district no longer shifts the trees of another), and once at the end for what
came after. Ids use no Python `hash()`, no set or dict order of strings and no GEOS output:
the anchors are plain IEEE arithmetic on grid coordinates, ties go by sorted JSON.

Two generator changes were needed for ids (and geometry) to stay put when something far
away changes, and they move every city slightly (new goldens):

- `blocks.build_blocks` takes the road pieces that touch a district's clip
  (`predicate="intersects"`), not every piece in its bounding box, and `_district_lots`
  unions them with `geom.union_local`, a merge tree along a Z-order curve from a fixed
  origin: with snap-rounded overlays the order of a union decides the last centimeter, and a
  plain sequential union let a road 2 km away move a block corner by 1 cm.
- the props, plants and gameplay layer hash stable ids (above).

## District regeneration

`citygen build SPEC OUT --district NAME` (`citygen/edit.py`):

1. **M1 replayed.** Water, districts, megasite reserves and primary roads are built again
   from the city's base spec at the choices its search made (hydrology variant, road
   variant, layout salt, saved in `city_state.json`): `build.replay`, no search, the same
   bytes. M1 does not change: the district keeps its outline and its primary roads.
2. **M2 to M11 for the whole city, with a frame.** The local streets, blocks, lots,
   buildings, transit, props, plants and gameplay layer run for every district on that M1,
   the district with its new spec entry, under a `streets.Frame` built from the old city:
   - every road segment that is not inside the district (its border roads, everything
     outside it, the primary roads that leave it) is *held*: it comes back as it was, with
     all its nodes (`Frame.restore` copies class, lanes, cross-section, profile, direction
     and role);
   - the district's new streets meet a held road only at one of its old nodes within 25 m
     of where they would have met it (`Frame.meet`), and stop on both sides of a held road
     they cross elsewhere; every clean-up (sharp angles, duplicates, unnoded crossings,
     dead stubs) removes the new street, never the held one; a held group cut off from the
     network by the district's new streets is linked back to them (`_reconnect`);
   - held footbridges on a canal that reaches the district are put back as they were when
     the footbridges are placed (they are placed one after another along a canal, so a new
     one in the district would move those beyond it), and new ones go only in the district;
   - transit lines are held (track and heights; a building of the new district in a line's
     way goes, as it would in a full build).
   Everything else runs as in a full build: the other districts' streets grow from the same
   seeds and come out the same.
3. **The splice** (`edit.splice`): every entity of the district, and of its seam, comes from
   the new build; everything else from the old city, byte for byte. The seam is where the
   new district meets the held city: the nodes where its streets (old or new) meet held
   roads, their junctions, crosswalks and lane connectors, the lanes and sidewalks of roads
   that end there, the walkways along those sidewalks, the blocks of other districts those
   junctions cut by 1 m2 or more (and what stands on them), and the props and plants within
   4 m of a new one (14 m for tree crowns). A closure then follows the references both ways:
   an old entity that names one that is gone, or that the new build changed because of the
   district, comes from the new build too, so the seam grows only as far as the district
   reaches. The gameplay fields keep their old cells outside the district, the factions
   their old territories, and a new name that an old place already has gets a number.
4. **Pins and overrides** are applied, then every check runs on the result.

**Design: rebuild everything after M1, then splice**, rather than building one district
alone. The stages after M1 are global (the lane and walkway graphs, transit, the props'
occupancy grid, the gameplay fields, the checks), so a district built alone would need a
second code path for each of them. Running the normal stages under a frame keeps one code
path; the generators are deterministic and, with the two fixes above, local, so the old
city comes back the same, and the splice guarantees it byte for byte where a stage is not
perfectly local. Skipping the M1 search (the slow part of a full build) keeps a sample
district under a minute.

REGEN_TABLE

## Pins and overrides

`overrides.json` beside the spec (or `--overrides FILE`) is read by every build and
regeneration and kept in the build state and the lock (`citygen/overrides.py`):

```json
{"version": 1,
 "pins": ["d03.lot.e512n88.bld", "d03.os.e600n120", "rs.e1234n567"],
 "edits": [
   {"op": "move", "id": "d03.lot.e512n88.bld", "by": [4.0, -2.5]},
   {"op": "replace", "id": "d03.lot.e512n88.bld", "height_m": 240.0},
   {"op": "replace", "id": "d03.os.e600n120", "kind": "garden", "name": "Jade Garden"},
   {"op": "replace", "id": "rs.e1234n567", "name": "Neon Mile"},
   {"op": "plaza", "id": "d03.lot.e700n90", "name": "Lantern Square"},
   {"op": "remove", "id": "d03.prop.kiosk.e705n92"}]}
```

- **Pins** survive a district regeneration: a pinned road is held like a border road; a
  pinned building or open space keeps its ground (new streets keep 15 m from it, new lots
  leave it out). A pinned building stands on a lot of its own, like a traced building of a
  pinned island, and goes back on it as it was before the props and the gameplay layer are
  made, so they see it (its units and entrances face the nearest road, its entrances join
  the new walkways). A pinned open space comes back after the splice; new buildings, props
  and plants on it go.
- **Edits** run on the finished city in their order after every build and regeneration:
  `move` (a building with its masses, entrances, units, roof items and what hangs on it, a
  prop, a plant, an open space, a site element), `replace` (a building's height, its masses
  scaled to it; an open space's kind or name; a road's or a place's name; any field with
  `set`, validated with the model), `plaza` (a lot becomes a plaza, its buildings and what
  hangs on them go) and `remove` (a building, prop, plant, sign slot, skybridge, open space
  or site element and what hangs on it).

**Design:** edits are a short list of operations on stable ids, applied last, not a patch of
the model: they survive a rebuild with other code as long as the ids exist, and a skipped
edit (an id that is gone) is a note, not an error. Roads cannot be moved or removed by an
edit (the lane, walkway and transit graphs hang on them): pin them, or change the district
and regenerate it. Every check runs after the edits; an edit that breaks one shows in the
report like any failure.

## Lock

`citygen lock OUT --release 1.0` writes `city.lock.json`: the spec, the overrides each step
used, the district regenerations in their order (each with the district's spec entry and
seed), the search's choices, the citygen version, the sha256 of its source code
(`citygen/*.py`) and of `city_model.json`. It refuses a build whose model does not match its
state (edited by hand). `citygen lock --verify LOCK` runs the full build (search and all)
from the spec, applies the overrides, then each regeneration in turn, and compares the
bytes; with other code it still rebuilds but says so (a lock is a promise of the code it
names).

LOCK_TABLE

## Model diff

`citygen model diff A B` prints, per collection, the entities added, removed and changed
(with the fields that differ), and the model fields that differ; `--json` writes it all,
`--png` draws it (`citygen/preview_diff.py`: what is the same in grey, removed in red, added
in green, moved or reshaped in yellow, with a close-up of the area that changed).

DIFF_SECTION

SWEEP_SECTION

## Tests

`tests/test_edit.py` (15 tests on the small test city):

- ids: every id from its kind and place (no build counter left), every reference names an
  entity, renaming a renamed model changes nothing, collisions go by content, and a
  generator change local to one stage (no benches) leaves every other id and entity alone;
- regeneration: a district with a new seed and a district with new spec fields
  (`height_m`): every road outside it back as it was (id, geometry and all), every entity
  more than 250 m from it unchanged, every check passing; regeneration is deterministic;
- pins (a building and a road survive a regeneration, nothing new on the pinned ground) and
  every override operation;
- a locked city with a regeneration rebuilds byte for byte; a lock refuses a hand-edited
  model; the diff; the CLI (`build --district`, `lock`, `lock --verify`, `model diff`).

The goldens (`tests/data/golden_hashes.json`) are the M10 builds; the check count is
unchanged (75).

## Open items

OPEN_ITEMS

## Files

| File | What |
|---|---|
| `citygen/ids.py` | the renaming pass, reference table, collisions, priors |
| `citygen/edit.py` | build state, district regeneration, the splice |
| `citygen/overrides.py` | pins and edits |
| `citygen/lock.py` | lock and verify |
| `citygen/diff.py`, `citygen/preview_diff.py` | model diff and its map |
| `citygen/streets.py` | `Frame` and its hooks in the street builder |
| `citygen/build.py` | `replay`, `choices`, `stable`, `check_all` |
| `<city>/` | sample builds (previews, reports, traces, renders, `city_state.json`, `city.lock.json`) |
| `regenerated/` | a regenerated Vesper Bay district: before, after, diff |
| `sweep.md`, `sweep.json` | the m8a sweep |
