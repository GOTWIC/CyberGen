# Cars by road class, smooth turns, steam off (after dlss_lamps_flicker)

Three fixes from Swagnik's drive through the packaged Delta Megacity (`Delta_dlss`), on the
Windows PC (RTX 4070 Ti, 32 GB, UE 5.8), 2026-11-14, on `claude/dlss-lamps-flicker` (#224):
LG0's cars drive slower on smaller roads, turn on smooth curves, and AT4's steam and smoke
plumes are off by default.

## 1. Slower on smaller roads

LG0 gave every car one cruise speed, drawn from 7 to 11 m/s (25 to 40 km/h), on every lane:
as fast in an alley as on an avenue, and through a junction's turn as on the straight.

**Fix.** Each drive lane gets a cruise speed by its road's class, a city's speeds
(`lifegen/presets.py` `DRIVE_SPEEDS`, the life plan's `spike.drive_speeds`):

| Class | m/s | km/h |
|---|---|---|
| highway | 22 | 80 |
| avenue | 14 | 50 |
| street | 9.5 | 35 |
| service | 7 | 25 |
| alley | 4.5 | 15 |

and slower still where it turns (`DRIVE`):

- **Junctions:** a connector through a junction 0.7 of its slower road's speed (a street's
  connector 6.65 m/s, 24 km/h; an alley's 3.15).
- **Bends:** at each point of a lane at most $\sqrt{a_{lat} R}$, $a_{lat}$ = 2 m/s$^2$ of
  sideways pull and $R$ the bend's radius there (a right turn at 10 m: 4.5 m/s, 16 km/h), never
  under 2 m/s (a turning bulb's hairpin connector is tighter than any car turns).
- **Braking:** a lane's end at most its successors' start, and every point at most what
  braking at 2.5 m/s$^2$ from the slow points ahead allows, so a car slows before a bend or a
  junction, not in it.
- **Each car** drives at its own share of that (0.9 to 1.08, by its draw), the lowest point
  speed from where it is to a few meters on (`CgLife::SpeedAhead`), and still slows behind the
  car ahead as in LG0.

On Delta's spike (Old Town, 5,509 drive lanes within its reach):

| Lanes | Count | Cruise (m/s) |
|---|---|---|
| avenue | 251 | 14 |
| street | 1,066 | 9.5 |
| service | 6 | 7 |
| alley | 476 | 4.5 |
| junction connectors | 3,710 | 9.8 (avenue), 6.65 (street), 4.9 (service), 3.15 (alley) |

With the bends and the braking, the speed a car may drive at its lane's points is 2.9 m/s at
the 5th percentile, 4.5 at the median (Old Town is mostly streets and alleys, and half its lane
points lie in junctions) and 9.5 at the 95th (LG0: 7 to 11 everywhere).

## 2. Smooth turns

> "the cars dont turn smoothly"

**Cause.** The lane graph's polylines (M2's lanes and junction connectors, drawn on M22's
pavement map) turn at single points: a connector through a junction is often three points
with a corner at the middle one. LG0 built its ZoneGraph lanes on those points and took a car's
heading from the segment it was on, so a car turned at once at each corner.

**Fix** (`citygen/unreal_life.py`, `PACK_VERSION` 2):

- **Fillets** (`fillet`): every inner point turning more than 12 degrees is rounded off by a
  circular arc tangent to both legs, its tangent at most 0.45 of each leg and the corner cut by
  at most 2 m (a right angle between legs of 7 m or more: an arc of 4.8 m radius).
- **Spline** (`smooth`): a centripetal Catmull-Rom spline through the result, sampled at most
  1.5 m apart, the neighbor lanes' points past each end as the spline's end controls, so a
  connector leaves and joins its roads on their tangents; straight runs stay chords, z follows
  the chord.
- **Heading on the tangent:** the runtime's lanes take these points, and a car's heading is the
  lane's tangent interpolated between points (`FZoneGraphLaneLocation::Tangent`), so it turns as
  it moves; its speed through the bend is limited by the curvature (above).

On the same lanes as `pack_lanes` packs them, the heading change (degrees) from one point to
the next:

| | Points | Median | 95th | 99th | Points turning over 20 degrees |
|---|---|---|---|---|---|
| LG0 (the graph's polylines) | 32,602 | 9.2 | 27.2 | 56.7 | 2,628 |
| cars_steam (fillets and spline) | 82,994 | 2.4 | 9.7 | 18.1 | 595 |

The points still turning over 20 degrees are on short connectors whose legs leave room only
for an arc of 2 to 3 m (a right turn between two 6 m legs; a car takes it at the 2 m/s floor to
2.5 m/s), and the U-turns in turning bulbs; there the heading still turns over the arc's few
points, never at one.

**The roads' own curves** stay as coarse as M22's pavement map and AG17 draw them: a bend is a
few stations, a junction's corner a few vertices. The fix rounds the cars' lanes, not the
asphalt under them, so on a tight corner a car's line can run up to the fillet's cut inside the
lane's drawn corner. Smoother road geometry (more stations on a bend, arcs in the pavement
map's junction faces) is a later issue for M22 and AG17.

## 3. Steam and smoke off by default (issue #223)

AT4's plumes (manholes, drains, vents, food stalls, chimneys) do not look real yet (#223), so
they are off until they do: the atmos spec's `steam` (default false, `presets.STEAM_ON`), the
plan's `air.steam`, the controller's `bSteam` set by the import. The plan still places every
emitter. In the game the Tab menu's **Steam and smoke** row and `CityGenAtmos.Steam [0|1]` turn
them on and off; the fog volumes stay with `CityGenAtmos.Air`.

## Delta in Unreal

Delta's atmos and life plans made again (the atmos plan's checks all pass; its only change is
`air.steam`), imported over its import in a throwaway project with NVIDIA's DLSS plugin: the
life and atmos controllers updated (2 actors of 14,689), the plugins rebuilt.

- **The check by night passes** (walk, curb, flight, sky and time, air, weather, look, far
  city, play features; the controller's 731 plumes registered, hidden).
- **Shots** (`shots/`, the play window's free camera 14 m over a leg of four Old Town junctions
  near the spike's middle, 400 cars respawned with `CityGenLife.Respawn 2000 400` since the
  plan's 40 are few to the eye): by day [`pday_cars_turn_0`](shots/pday_cars_turn_0.jpg) to
  [`3`](shots/pday_cars_turn_3.jpg), by night [`night_cars_turn_0`](shots/night_cars_turn_0.jpg)
  to [`3`](shots/night_cars_turn_3.jpg): cars at their street's speed and angled through the
  junctions (a still shows a car's pose, not its motion: the smoothness is the lanes' numbers
  above). The Tab menu with its **Steam and smoke: Off** row:
  [`play_menu`](shots/play_menu.jpg).
- **The lean benchmark** (`bench/native`, the night as delivered at native 2560 x 1440, one
  run): 18.7 ms p95 over the route (walk 19.0, drive 18.9, fly 18.6), game-thread bound, within
  the 20 ms budget (dlss_lamps_flicker: 18.8 to 20.0 ms on the same route).

## The packaged game

`builds/packaged/Delta_cars/Windows/CityAG16.exe` (Development, Win64, 3.3 GB, outside the
repo), cooked from a mirror of the project in 11.5 minutes. A smoke launch with a user folder of
its own ran 120 s with no fatal error: DLSS and Streamline supported, the world up, the play
features ready by night, the life controller placing its 2,000 people and 40 cars on d04's 5,509
drive lanes (1.0 to 1.1 ms of game thread a frame).
