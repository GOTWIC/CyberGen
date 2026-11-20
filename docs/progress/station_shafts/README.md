# Station shafts (station_shafts)

Built on the Windows PC (2026-11-20), from #252's open items (`docs/progress/station_stairs`):
where no clear ground was within reach of a platform or concourse end, an elevator still went
straight down from the end into a road, sidewalk or junction (`attrs.clear` false: Delta 4,
Vesper Bay 12, Cragmouth 6, 46 across the seven built cities); metro wells opened the
blockout's ground but not M22's pavement map nor M13's heightfield; a stair tower's height was
its platform's z over the ground at the tower. Delta was built again on the branch
(`C:/Users/swagn/CityGen/builds/delta_shafts`, the same steps as #252's build, now `delta_main`: `citygen
build --blockout --no-render`, `assetgen build --workers 2`, `atmosgen plan`, `lifegen plan
--atmos`).

| Part | Where | What |
|---|---|---|
| No shaft in the street | `citygen/transit.py` (`Builder._elevated`, `_metro`, `_niche`, `_niche_ok`, `_passage_ok`, `_ground_ok`, `_stair_blocked`; `ACCESS_FAR_M`, `ACCESS_BRIDGE_FAR_M`, `ACCESS_PASSAGE_FAR_M`, `NICHE_*`, `PASSAGE_*`) | #252's straight-down elevator (`_lift_here`) is gone: a tower, well or shaft farther off with a longer bridge or passage, else a station entrance cut into a building's ground floor, else nothing at that end (noted) |
| Clear ground off the pavement | `transit.Builder._clear_index`, `pavement_checks.face_polygons` | every face of M22's map kept off, corner pads and bulb rings too |
| Terrain | `transit.Builder._gz`, `_rel`, `stair_plan(..., fit=)`, `_ramp_ok`; `blockout._terrain`, `_ground_grid`, `_well_cells` | towers and wells on the ground where they stand; the heightfield cut open over every well |
| Checks | `citygen/transit_checks.py` (`check_station_stairs`, `check_station_access`) | a shaft on a road, junction, crosswalk, pavement face or water, or in a building mass within its height, fails (it was a note); both measure stair grades over sea level |
| Tests | `tests/test_transit.py` | shafts off the street and the check failing one moved into a road; a stair plan fitted to the ground it lands on; the heightfield's exact opening over a well |

## 1. No shaft in the street

**Cause.** #252 looked for clear ground within 36 m of an elevated end (a bridge of 40 m at
most) and 60 m of a concourse end, then put an elevator straight down from the end with its
shaft where it stood. Two faults of #252 made the clear ground look scarcer than it was: the
bridge test (`_stair_blocked`, the check's own masses) and the paths' and passages' masses
(`Builder.masses`) still counted the buildings the lines take out (every bridge from Vesper
Bay's Halo Line platforms, which stand where such buildings were, was "blocked": 9 of its 12
shafts in the street), and a passage was kept from under every building, even the low ones
whose single basement level leaves room under it.

**Fix.** Each end now tries, in order: #252's stair tower or well and shaft within reach; a
tower or well and a shaft farther off (`ACCESS_FAR_M` 90 m with a bridge up to
`ACCESS_BRIDGE_FAR_M` 90 m for an elevated end, `ACCESS_PASSAGE_FAR_M` 150 m for a concourse
end, on a 2 m grid); for a concourse end, a **station entrance cut into a building's ground
floor** (`_niche`): the elevator shaft flush with a facade inside the footprint, the masses
standing on the ground cut round it by `NICHE_PAD_M` 0.5 m and kept over it from
`GATE_CLEAR_M` 4.5 m up (the access fixes' `buildout._cut_gate`, on a building `_niche_ok`
allows: no landmark, M21 form, portal, traced or held building), a shop unit in the way giving
way (counted `NICHE_UNIT_M` 15 m farther), its top door to the street through the opening, a
passage at the concourse's depth to the concourse's end (`Building.attrs.station_entrance`, the
shaft's `attrs.entrance`). An end none of these serve gets nothing and a note; its station is
served by its other end (and an elevated station's own elevator at either end, as #252).

On the way: the taken-out buildings no longer block bridges or paths (`B.masses` and
`_stair_blocked` leave them out); a passage passes under a building whose basement
(`tunnels.foundation_m`: 4 m under 20 m tall) stops `PASSAGE_CLEAR_M` 1 m over its roof
(`PASSAGE_H_M` 3 m over its floor), and anywhere inside its own station's box
(`_passage_ok`); a metro shaft may stand over the concourse it goes down into
(`_dyn(under=False)`). A path from a stair's foot to the sidewalk stays straight and clear of
both mass tests (`_ground_ok`, as #252): led round the buildings, `foot` could take a straight
link through one, and Delta's third layout failed `walkway_building_clash` on it.

**Check.** `station_stairs` fails a shaft standing on a road's right of way, a junction, a
crosswalk, a face of the pavement map or water, or in a building mass within its height (an
entrance's floors over it pass); #252's `attrs.clear` false fails.

## 2. Nothing paves over a well

Clear ground keeps off every face of M22's pavement map (`pavement_checks.face_polygons`):
#252 took the junctions' polygons (their carriageways since M22) and the roads' rights of way,
so a stair could stand on a corner pad (Delta's Midtown stair, two of Vesper Bay's and a shaft
there). No stair or shaft meets a face now, so AG17 paves over none, and M16's ground cover
(which AG13 draws) already leaves out every stair and elevator. On a terrain city the
blockout's heightfield leaves every 4 m cell a well reaches open and drapes the rest of those
cells round the well (`blockout._well_cells`), so the ground opens exactly over it; on a flat
city the ground was already cut (`_land_and_water`).

## 3. Terrain

A walkway's z is over the ground where it stands (M13). A stair tower now rises from the
ground at its own foot to the platform's height over sea level (`_tower`: the platform's z
plus the ground at its end); a well from the ground at its head to the concourse's depth
under its foot, its passage at that depth under the ground where it runs, climbing at most
`PASSAGE_GRADE` 0.25 (`_well`, `_ramp_ok`); a bridge is level over sea level. The stair is
planned for the ground at the end, placed, then fitted to the ground where it landed with the
same flights and footprint while they stay within `STAIR_FIT_GRADE` 0.66
(`stair_plan(..., fit=(n, run))`), else planned again with more flights or longer runs
(`TERRAIN_TRIES` 4). `station_access` measures a station stair's grade over sea level, as
`station_stairs` does: on a slope the model's z is over the ground at each point, and measured
so a well's flight of 3.0 m over 4.3 m read 3.3 m (Cragmouth failed every city try on the first
version of this branch). Its walkway's points are over the ground at each point, its structure's
heights (footprint, line, z0, z1) over the ground at its middle; the blockout lifts a station
stair or shaft as one piece by the ground there (`_terrain`), as AG7 seats it
(`ground_c`). The check measures the flights over sea level. Cragmouth (the hilly sample, metro
only) builds every one of its 16 concourse ends a well or shaft.

![Delta's West Quay monorail station over the canal (19 m): #252 put its first end's elevator straight down into the pedestrian street; now a stair tower and a glass shaft on the quay across the water, each reached by a glazed bridge at the platform's height (84 m and 54 m)](render_west_quay.jpg)

![Cragmouth in plan: Hollow's metro well, the 4 m heightfield's cells it reaches left open and draped round it (the blockout's own parts); Ridgeback's station entrance cut into a tower's ground floor, its shaft under the floors kept over the opening from 4.5 m, a way out to the sidewalk and a passage 8 m down to the concourse](cragmouth_well_and_entrance.png)

## The cities on the branch

Every city builds on the same try as on main and passes every check (109, 114 with decks).
Shafts in the street: 46 on main (`attrs.clear` false; #252's README and its builds), none
now. "Ends left out" are platform or concourse ends with no stair or shaft, each in a station
its other end serves (noted in the report).

| City | Try (as main) | Stair towers | Metro wells | Flights | Shafts | Entrances in buildings | In the street (main) | Ends left out | Longest bridge, passage |
|---|---|---|---|---|---|---|---|---|---|
| Saltreach Free Port | 1 | 17 | 0 | 119 | 9 | 0 | 0 (2) | 0 | 34 m, none |
| Cragmouth | 2 | 0 | 13 | 39 | 3 | 1 | 0 (6) | 0 | none, 120 m |
| Delta Megacity | 3 | 21 | 4 | 158 | 13 | 0 | 0 (4) | 0 | 84 m, 107 m |
| Nexus City | 1 | 15 | 7 | 118 | 11 | 1 | 0 (5) | 0 | 41 m, 50 m |
| Greyhook | 3 | 9 | 13 | 88 | 6 | 0 | 0 (5) | 1 | 19 m, 62 m |
| Vesper Bay | 8 | 24 | 9 | 159 | 14 | 0 | 0 (12) | 2 | 25 m, 137 m |
| Vesper Bay Decks | 18 | 22 | 9 | 146 | 14 | 0 | 0 (12) | 3 | 35 m, 113 m |

Ends left out: Greyhook's `stn.neckgate.3` b, Vesper Bay's `stn.corporate_core.2` a (towers and
a maglev line all round it within 90 m) and `stn.launch_key` a (over the water), Vesper Bay
Decks' `stn.corporate_core.2` a, `stn.corporate_core.3` a and `stn.launch_key` a. On main the
first four had a shaft in the street, the over-water ends nothing.

Delta (`C:/Users/swagn/CityGen/builds/delta_shafts`): `citygen build` on hydrology variant 12, road
variant 3, layout salt 2 as main (tries 1 and 2 fail as on main), `assetgen build`, `atmosgen plan` and `lifegen
plan --atmos` all pass. Its every concourse end is a well (4) or a shaft on clear ground (2),
every platform end a tower (21) or a shaft (11, plus the platforms' own).

## Goldens

Every city's model and blockout plan move on purpose (`tests/data/golden_hashes.json`, from
builds of the branch in `C:/Users/swagn/CityGen/builds/goldens_station_shafts`, Delta's in
`delta_shafts`): stations' stairs and shafts placed off the pavement map and farther off where
#252 had none, their bridges, passages and paths, the props, plants and gameplay rows near them,
the cut buildings (Cragmouth, Nexus), Cragmouth's on its ground. assetgen's goldens: the five
samples' briefs (`tests/assetgen/data/golden_hashes.json`) and Vesper Bay's street tiles
(`golden_streets.json`) move with the models; the water goldens, the small city's props and
ground do not move. `test_check_supports_fails_long_span` read a station stair's `attrs.frame`
(its placement since #252, a list) as a support's frame id; it checks the type now.

## Open items

- **Ends left out:** six ends in dense cores or over the water have no clear ground within
  90 m; an elevator in a building beside the platform (a bridge into it at the platform's
  height) would serve them, tried here and left out (no sample end had a building whose masses
  rise unbroken past the platform within reach).
- **Long ways:** bridges up to 84 m and passages up to 137 m where the clear ground is far.
- **Sidewalk entrances** (a stair or shaft in a wide sidewalk's furniture zone): not built; the
  sidewalk walkway runs along the sidewalk's middle, which a shaft there would block.
