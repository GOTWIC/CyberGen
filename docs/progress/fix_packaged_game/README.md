# Packaged game fixes (after AT1)

Delta Megacity, packaged (UAT BuildCookRun, Development Win64) from a copy of the AT1
project after a new import, and played on the PC (2560 x 1440 at 125%).
`docs/unreal_export.md`, "A packaged game", has the details.

| Problem in the AT1 package | Now |
|---|---|
| `LoadPackage: SkipPackage: /Game/CityGen/Core/Atmos/MPC_CityGenAtmos ... does not exist`, the same for `M_CgRain` and `M_CgWet`; `CityGenAtmos.Rain 1` and `.Wet 1` did nothing | the import writes `+DirectoriesToAlwaysCook` for `/Game/CityGen/Core/Atmos` and `/Engine/BasicShapes` into the project's DefaultGame.ini; the three assets and the plane are in the package, and the log has no missing package |
| a fresh package opened a 2048 x 1152 window (picked before it was DPI-aware) | `CityGen play: window 2048x1152 -> 2560x1440 windowed fullscreen (the monitor's native resolution)` at start, with no saved settings |
| weather only from the console | Tab menu rows: Fog, Rain, Wet streets, Hour (`<` `>`), hidden without an atmos controller |

The menu rows checked in the package by the benchmark's driver, one night pass, its
commands `CityGen.MenuRow fog`, `rain`, `wet`, `hour-` (what a click on each row runs):

```
before: "atmos": true, "fog": false, "rain": false, "wet": false, "hour": 23.00
after:  "atmos": true, "fog": true, "rain": true, "wet": true, "hour": 22.00
atmos:  "live": 512, "hour": 22.00, "fog": true, "rain": true, "wet": true, "showing": true
```

![Night with fog, rain and wet streets in the packaged game](night_fog_rain_wet.jpg)

Rain streaks, wet paving with puddles and the haze, by night at 22:00, the plan's lights live.
