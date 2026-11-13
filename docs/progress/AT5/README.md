# AT5: weather (atmosgen)

Stage 3's sixth milestone (`docs/atmosgen_scope.md` sections 6.4 and 13): rain kept out of what
is covered, wet streets and puddles, drips, splashes and rings on the water, the wind, and five
weather states that blend into each other. Built on the Windows PC (RTX 4070 Ti, 32 GB),
2026-11-13, on main after AT4 (#211), the play fixes (#213) and the visible lights (#215).

## What AT5 built

| Part | Where | What |
|---|---|---|
| The rain shadow | `atmosgen/weather.py` (`Weather.covers`) | every cover within 25 m of the ground: M14's deck slabs, M3's masses where they hang over no mass of their own building that reaches up to them (a tower on its podium covers the podium's roof, not the street), skybridges, M6's awnings and bus shelters, canopies, transit decks and cap beams, the raised roads (as the sight raster takes them), road tunnels' lids; each moved downwind by its height times the rain's lean (0.3, at most 3 m: the lee of an awning dry, its windward edge wet) |
| The masks | `masks/<tile>.png` (scope 4.2) | per 256 m tile, 0.5 m texels, RGBA: the cover's underside (the plan's datum and steps: a surface under it is dry, one over it, a deck's or a viaduct's top, wet), the puddles, the drip band, the gloss when wet by surface (asphalt mirrors, paving and sidewalks a little less, soil and grass little, roofs between, the water none) |
| Puddles | `Weather.masks_of`, `presets.PUDDLE` | water stands in the worn spots (a value noise on the plan, 5.5 m and 1.8 m), in the gutter along the curb (the crown sheds the rain to it), at a road's sags (the low points of its grade line: M13's ground plus its own profile) and round AG7's drains (read from the street packs; clogged in gritty districts); the threshold lowered by the district's grit (decision 12.5: the clean Corporate Core few, Old Town and the port many); never under a cover, on a roof, a curb, a raised deck or the water; each as deep as it passes the threshold, so a drizzle fills only the deepest |
| Drips | `drips/<tile>.json`, `planmodel.Drip` | a line under each low cover's dripping edge (an awning's street edge, a deck slab's rim, a raised road's sides, canopies, bus shelters) in 8 m pieces, the edge's height and the ground under it |
| States | `presets.WEATHER`, `WEATHER_LOOK`, `WEATHER_TIMES`, `WIND`; the plan's `weather_plan` | clear, drizzle, rain, fog, smog: each its rain, streak length, share of the drops, wetness, puddle fill, the cloud deck's cover, the fog (the look's, as AT4's air makes it), the fog volumes' gain, the wind and its gusts; the rain's age (a change blends over 20 s; the streets wet over 45 s at full rain and dry over 300 s; the puddles fill over 120 s and drain over 900 s); the wind's heading (the spec's `wind_deg`, from the south-west by default) |
| The weather check | `Weather.check`, the plan's `checks.weather` | every tile's mask; every low cover's middle in its rain shadow (1% may miss by a texel); no puddle under a cover, inside a building or on the water (a bridge's deck excepted); the drips' budget per tile; a plan failing it is not delivered |
| Previews | `atmosgen lux` | `preview_weather.png` (the city: the shadow blue, puddles cyan, drip bands yellow) and `preview_weather_detail.png` (the busiest tile at 0.25 m a pixel with its drip lines) |
| Exporter | `citygen/unreal_atmos.py`, `ue/import_city.py` | packing version 4 (a cell's drip lines); the controller's weather; the masks stitched city-wide at 1 m into two textures (`T_<City>_WetCover` exact grey, `_WetSurface` compressed); `ATMOS_VERSION` atmos6 |
| Runtime | `ue/CityGenAtmos` | the states blended, the rain's age, the wind and gusts into `MPC_CityGenAtmos` and `MPC_CityGen`'s `Wind`; the fog, clouds (and the sun under them by day) and fog volumes by state; the wet streets (two DBuffer decals), the rain cut under the covers and leaning in the wind, splashes, drips; console `.Weather`, `.WeatherSpeed`, `.Wetness` |
| Water and trees | `ue/import_city.py` | rain rings on `M_CgWater` (its tag `.rain1`, rebuilt alone); the trees' crowns swaying in `MPC_CityGen`'s `Wind` built (`M_CgLeaves`, `.wind1`) but off (`LEAF_SWAY`): it cost Midtown's tree-lined street 4.5 ms of GPU a frame (open items) |
| Play features | `ue/CityGenPlay` | the Tab menu's Weather row (the state, `a > b` while it turns; its arrows the previous and the next) in place of AT0's Fog, Rain and Wet streets rows |
| Benchmark | `citygen/bench.py` | every atmos pass sets its weather state at once; `night_plan_drizzle`, `_clear`, `_fogstate`, `_smog` |
| Check | `ue/check_city.py` | the weather by night; `*__<state>` views, `*__<a>2<b>_<n>s` transitions |
