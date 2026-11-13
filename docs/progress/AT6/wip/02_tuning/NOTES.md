# AT6 WIP 02: tuning at fixed viewpoints

One standalone game at 2560 x 1440 (`builds/at6/viewtune.py`), each view a short walk after
its console commands, a shot at its end (labels: stops from middle grey).

- `t1_day.jpg`: the day's exposure (`CityGenAtmos.DayEV`) clear and in rain, by day under a
  viaduct, in Old Town, the port, the core. A clear day reads right at -0.8 EV100 (-2.1 stops
  in the core); rain with half of its overcast given back (`overcast_comp` 0.5).
- `t1_night.jpg`: the look's post off (left) and on (right) by night: the core cool and
  crisp, Old Town warmer and grainier, the port darker and grainier.
- `t1_misc.jpg`: the curb by the awning without and with the wet decals (no sawtooth), a
  food stall's cooking (6 cards, lit by night), dusk.
- `curb_before.jpg` (AT5) and `curb_after.jpg`: the decals' face normal from fine derivatives.
- `viewtune.json`: GPU per view; the post costs 0.15 to 0.24 ms (core, Old Town, port).
