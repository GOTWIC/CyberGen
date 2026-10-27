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

Every sample passes all 75 checks on the same number of full-city tries as on M11, and each
`city_model.json` is byte-identical on the M4 Mac (arm64) and on x86_64 Linux (docker image
`citygen-x86`, `linux/amd64`, `CITYGEN_WORKERS=3`), stage traces included. Ids are longer, so
the models grow by about 4% (Vesper Bay 55.5 to 57.8 MB); apart from ids, the block fix
moves a few blocks by a centimeter or so, so a few lots split differently: building and lot
counts move by 0.16% at most (Delta Megacity 5410 to 5417 buildings, Greyhook 2458 to 2462,
Saltreach and Nexus City unchanged).

| City | Tries (M11, M10) | Entities | Release lock | sha256 of `city_model.json` (both machines) |
|---|---|---|---|---|
| archipelago_free_port | 1, 1 | 90849 | [`city.lock.json`](archipelago_free_port/city.lock.json) | `2cb91e663fe3f1aba5184efe0ad2cd5168b1f26721e6e8df9acddda0dbb8f525` |
| delta_megacity | 1, 1 | 157688 | [`city.lock.json`](delta_megacity/city.lock.json) | `49fa43f9631e8512a705dd8a008f5114610468d41b8722d94797ab6cd7c55abe` |
| nexus_city | 3, 3 | 175968 | [`city.lock.json`](nexus_city/city.lock.json) | `696007837a246fb07489e67d4898889891068166f14651ec9811149965d77d2d` |
| peninsula_city | 1, 1 | 75884 | [`city.lock.json`](peninsula_city/city.lock.json) | `0ca27090773e437f5387065311e29b36eec5464f30785ca90f43bd7dd5e98e0e` |
| vesper_bay | 1, 1 | 162098 | [`city.lock.json`](vesper_bay/city.lock.json) | `3ee6a070f70534d98989183345036fd5c5512422a06c42a9a9ef09c78fb7202b` |
| vesper_bay_pinned | 2, 2 | 169484 | [`city.lock.json`](vesper_bay_pinned/city.lock.json) | `d39673465d54fe981d59ed983118982a74655a11f3c18098e7edbf67b2e2cb6f` |

<img src="regenerated/vesper_bay__neon_strand_diff.png" width="840">

Vesper Bay with Neon Strand regenerated on a new seed: the whole city and a close-up, what
is the same in grey, removed in red, added in green, moved or reshaped in yellow. The yellow
along the district's east edge is the seam: blocks of The Stacks that a seam junction's
corner cut, with what stands on them, and two parks on them planted again.

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

One district of every sample regenerated on a new seed (`citygen build SPEC OUT --base
BUILD --district NAME`, `CITYGEN_WORKERS=4`, the Mac shared with a sweep and the test suite
of other sessions); every check passes on every result:

TIMING_TABLE

"Outside" counts the entities that are not the district's own and differ from the old
city; the farthest is measured from the district's outline to the entity's shape. Maps and
reports: [`regenerated/`](regenerated/).

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

| Release | Regenerations | `citygen lock --verify` |
|---|---|---|
| Saltreach Free Port 1.0 ([`city.lock.json`](archipelago_free_port/city.lock.json)) | none | PASS, the same `city_model.json` byte for byte, 28 s |
| Vesper Bay 1.1 ([`regenerated/vesper_bay_neon_strand.lock.json`](regenerated/vesper_bay_neon_strand.lock.json)) | Neon Strand on a new seed | PASS, byte for byte (the full build with its search, then the regeneration), 106 s |

The tests lock the test city after a regeneration and rebuild it byte for byte, and check
that a lock refuses a model edited by hand.

## Model diff

`citygen model diff A B` prints, per collection, the entities added, removed and changed
(with the fields that differ), and the model fields that differ; `--json` writes it all,
`--png` draws it (`citygen/preview_diff.py`: what is the same in grey, removed in red, added
in green, moved or reshaped in yellow, with a close-up of the area that changed).

`citygen model diff` on the Vesper Bay regeneration above: 42134 entities added, 41240
removed, 1153 changed, nearly all in Neon Strand; `regenerated/` has the map and the report
of every regeneration in the table.

## Sweep

`citygen sweep --suite m8a --workers 3` ([`sweep.md`](sweep.md), `sweep.json`), next to
M11's ([`../M11/sweep.md`](../M11/sweep.md)):

| | M11 | M10 |
|---|---|---|
| builds passing every check | 58 of 68 | 58 of 68 |
| builds newly failing | | 0 |
| builds whose pass, failing checks, retries, hydrology or road variant differ from M11 (ids in the messages aside) | | 1 |
| full-city tries beyond the first, all 68 builds | 110 | 111 |
| crashes | 0 | 0 |
| build time, all 68 builds (one process each, the Mac shared with the x86 run and another session) | 6551 s | 7215 s |

The one difference: Delta Megacity s3141 passes on its third full-city try instead of its
second (first tries with 11 and 1 failures instead of 9); the block fix moves a few blocks,
so its first layouts come out a little differently. The ten builds that fail fail the same
checks as on M11 (placement, road graph, open space share, curve radius and the rest; M8a's
open items). The salt column now shows the layout salt of a whole-city retry (`salt 2`): the
build stats did not keep it before, so M11's table showed none (and a district
regeneration of such a city would have started from another layout; fixed and tested).

## Tests

`tests/test_edit.py` (16 tests on the small test city):

- ids: every id from its kind and place (no build counter left), every reference names an
  entity, renaming a renamed model changes nothing, collisions go by content, and a
  generator change local to one stage (no benches) leaves every other id and entity alone;
- regeneration: a district with a new seed and a district with new spec fields
  (`height_m`): every road outside it back as it was (id, geometry and all), every entity
  more than 250 m from it unchanged, every check passing; regeneration is deterministic; a
  whole-city retry's layout salt is kept for the replay;
- pins (a building and a road survive a regeneration, nothing new on the pinned ground) and
  every override operation;
- a locked city with a regeneration rebuilds byte for byte; a lock refuses a hand-edited
  model; the diff; the CLI (`build --district`, `lock`, `lock --verify`, `model diff`).

The goldens (`tests/data/golden_hashes.json`) are the M10 builds; the check count is
unchanged (75). `test_gameplay.py::test_check_travel_fails` now removes the fast-travel
points of the core district: it took the district of the first point, and with stable ids
the rows come in another order, so that was Test Isle, which has no drive lane and needs no
point.

## Open items

- **The seam can be wide on megablocks.** A block of a neighbor district that a seam
  junction's corner cuts by 1 m2 or more is built again with what stands on it; in The
  Stacks (megablock residential) that is a whole megablock and its towers, and a park on
  such a block is planted again (Vesper Bay, Neon Strand: changes up to 170 m from the
  district, all on blocks and walkways along its border). Keeping the old buildings on a cut
  block when they still fit it would narrow this.
- **What M1 decides stays.** `--district` keeps the district's outline, its primary roads
  and megasites; fields that M1 reads (`area_share`, `placement`, relations, megasites, the
  highway pattern) need a full build. M1 is not cached either: every regeneration replays
  it (5 to 7 s).
- **Time.** The regeneration itself takes 22 to 56 s with 3 or 4 workers on the shared Mac;
  loading the old model and writing the new one, the report and the eight previews add 7
  to 15 s. With the default 8 workers on a quiet machine it is faster.
- **Roads in overrides.** An edit cannot move or remove a road (the lane, walkway and
  transit graphs hang on it): pin it, or change and regenerate the district.
- **Ids move with geometry.** An id names where an entity sits, so an entity that moves (a
  seam junction, a prop the seam re-placed) gets a new id. Overrides that name such an
  entity are skipped with a note.
- **Locks name their code.** `code_sha256` covers `citygen/*.py`; after any code change a
  lock still rebuilds but says the code differs, so the sample locks committed here go stale
  with the next commit (rebuild and lock again for a new release).
- **M9 tunnels.** `ids.REFS` has `tunnels` from M9's model on its branch; check it, and its
  place in `ids.ORDER`, after merging.

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
