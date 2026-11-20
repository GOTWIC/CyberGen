# Station shafts (station_shafts)

Built on the Windows PC (2026-11-20), from #252's open items (`docs/progress/station_stairs`):
where no clear ground was within reach of a platform or concourse end, an elevator still went
straight down from the end into a road, sidewalk or junction (`attrs.clear` false: Delta 4,
Vesper Bay 12, Cragmouth 6, 46 across the seven built cities); metro wells opened the
blockout's ground but not M22's pavement map nor M13's heightfield; a stair tower's height was
its platform's z over the ground at the tower. Delta was built again on the branch
(`C:/Users/swagn/CityGen/builds/delta_shafts`, the same steps as `delta_stairs`: `citygen
build --blockout --no-render`, `assetgen build --workers 2`, `atmosgen plan`, `lifegen plan
--atmos`).

| Part | Where | What |
|---|---|---|
| No shaft in the street | `citygen/transit.py` (`Builder._elevated`, `_metro`, `_niche`, `_niche_ok`, `_passage_ok`, `_ground_ok`, `_stair_blocked`; `ACCESS_FAR_M`, `ACCESS_BRIDGE_FAR_M`, `ACCESS_PASSAGE_FAR_M`, `NICHE_*`, `PASSAGE_*`) | #252's straight-down elevator (`_lift_here`) is gone: a tower, well or shaft farther off with a longer bridge or passage, else a station entrance cut into a building's ground floor, else nothing at that end (noted) |
| Clear ground off the pavement | `transit.Builder._clear_index`, `pavement_checks.face_polygons` | every face of M22's map kept off, corner pads and bulb rings too |
| Terrain | `transit.Builder._gz`, `_rel`, `stair_plan(..., fit=)`, `_ramp_ok`; `blockout._terrain`, `_ground_grid`, `_well_cells` | towers and wells on the ground where they stand; the heightfield cut open over every well |
| Check | `citygen/transit_checks.py` (`check_station_stairs`) | a shaft on a road, junction, crosswalk, pavement face or water, or in a building mass within its height, fails (it was a note) |
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
(`_dyn(under=False)`); a path from a stair's foot to the sidewalk may be led round the
buildings as `foot` leads one (`_ground_ok`).

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
same flights and footprint (`stair_plan(..., fit=(n, run))`, else planned again,
`TERRAIN_TRIES`). Its walkway's points are over the ground at each point, its structure's
heights (footprint, line, z0, z1) over the ground at its middle; the blockout lifts a station
stair or shaft as one piece by the ground there (`_terrain`), as AG7 seats it
(`ground_c`). The check measures the flights over sea level. Cragmouth (the hilly sample, metro
only) builds every one of its 16 concourse ends a well or shaft.

TODO_RESULTS
