# LG8: weather, reactions and release (lifegen)

Stage 4's last milestone (`docs/lifegen_scope.md` 6.8, section 8, section 13): the city's life
by atmosgen's hour and weather (nightlife, umbrellas, shelter from the rain, fewer people out
and faster in rain, slower traffic), reactions to the player and to danger, the crowd and
traffic performance pass, every sample city planned with every check passing, Unreal checks on
the PC. City-wide: every behavior runs wherever the view is. Built on the Windows PC (RTX 4070
Ti, 12700K, UE 5.8.4) on 2026-11-16 and 17, on main after LG7 (#236).

## What LG8 built

| Part | Where | What |
|---|---|---|
| The weather's table | `lifegen/presets.py` `WEATHER_LIFE`, `WEATHER_KEYS`, `WEATHER_RAIN`; `lifegen/weather.py` `weather_record` | per atmosgen state (clear, drizzle, rain, fog, smog) the share of people out, their pace, the share in the rain looks (LG2's `WEATHER_OUTFITS`), the share of the others holding an umbrella, a passer-by's chance to shelter, the cars' share, speed and added headway; a rain state's values reached by its rain, so life follows atmosgen's change of state as its rain does |
| Shelter | `weather.walk_cover`, `Masks` | each walkway's stretches out of the rain, read from atmosgen's rain shadow (AT5's masks: something at least 2.1 m over it on the ground level), underground (a meter under the datum) or enclosed (skybridges, elevators, escalators, concourses); stretches 3 m or longer, gaps under 1.5 m joined; the walk rows' `cover` |
| Nightlife | `weather.nightlife`, `night_places` | people round the open bars, clubs and arcades (LG4's places, M11's POIs that are no place) on their door walkways by their busy and hours (3, 7 and 2 people at full busy), on top of M11's density; the walk rows' `night` |
| The pool's rain looks | `plan.crowd_plan`, `outfit_groups(rain=...)` | the pool's mix drawn at 0.6 of the rainiest state's rain looks, so the runtime's rain finds raincoats; the outfits' `district_groups_clear` and `rain_group` for the runtime's blend |
| Checks | `weather.checks` | `weather` (every state's shares and paces in reason, the reactions' settings), `shelter` (every stretch within its walkway, sorted, apart, long enough), `nightlife` (people only on an open nightlife place's door walkway, only in its open bands) |
| Vesper Bay's two failures | `places.gang_spots`, `transit.stops_of` | a gang spot whose ring runs past its turf's edge along the sidewalk is no spot of the turf's (LG4's `gang_turf`); a metro's concourse over a track lowered deep under foundations or the water bed is on its line where the track is at the station's own `track_z_m` (LG6's `transit_stops`: Corporate Core's concourse 16.2 m over its track) |
| Exporter | `citygen/unreal_life.py` `pack_weather`, `walk_cover`, `walk_night`, `run_clips` (`PACK_VERSION` 9); `import_city.weather_props` (`LIFE_VERSION` life10); `lifegen.presets.PLACE_CLIPS["run"]` | the table, the stretches, nightlife, umbrellas, reactions, stuck cars, the run clip (the Game Animation Sample's `M_Neutral_Run_Loop_F`, retargeted and made in place with LG4's place clips) and its speed |
| Runtime | `CityGenLifeWeather.cpp`; the walk processor (`StepCity`); the drive processor; `CityGenLifePeople.cpp` | below |
| Console, menu, check, bench | `CityGenLifeModule.cpp`; `CityGenPlay` (the Tab menu's Scare the crowd row); `check_city.py` (`until` reads `weather.show`); `bench.py` | `CityGenLife.FollowAtmos`, `.Weather`, `.Panic`, `.WeatherShow`; the status's `weather`; every life pass follows atmosgen's hour and weather, pass `night_life_noweather` |
