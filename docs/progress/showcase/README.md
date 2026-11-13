# Showcase shots

Sixteen 8K shots (7680 x 4320, JPEG quality 90) of Delta Megacity in Unreal Engine 5.8 for
the root README's Showcase section, 2026-11-13, on the Windows PC (RTX 4070 Ti). The city
is CityAG16's import with everything on: stage 2's buildings, streets, props, ground and
water, AG18's parked cars, and atmosgen AT0 to AT7 (the default look, neon rain at 23:00,
unless a shot says otherwise). Nothing was imported again.

| File | Caption | Hour and weather | Eye (x, y, z) to target, lens |
|---|---|---|---|
| `city_night_air.jpg` | The whole city from the air by night | 23:00, rain | (300, 1650, 250) to (1000, 0, 60), 30 mm |
| `core_dusk_water.jpg` | The downtown skyline across the water at dusk | 19:20, clear | (1150, -750, 25) to (1000, 120, 170), 45 mm |
| `core_night_water.jpg` | The skyline from the sea at night | 23:00, clear | as above |
| `city_day_air.jpg` | The city by day, from over the port | 16:00, clear | (-1200, -200, 150) to (1022, 79, 60), 24 mm |
| `core_street_rain.jpg` | A downtown street in the rain | 23:00, rain | (1120, 76.2, 1.8) to (1064.8, 131.3, 5), 24 mm |
| `core_street_night.jpg` | The same street at night, dry (the stage 2 section's street) | 23:00, clear | as above |
| `oldtown_puddles.jpg` | Neon and puddles in the old town | 23:00, rain | (-1232.2, 1384, 0.6) to (-1400, 1376, 0.2), 24 mm |
| `market_night.jpg` | A night market in the haze | 23:00, rain | (-1078, 1168, 1.7) to (-1090, 1215, 2.5), 24 mm |
| `canal_mist.jpg` | Mist over a canal lined with neon signs | 23:00, rain | (-1301.1, 1019.8, 1.7) to (-1294.7, 1045.2, -1.5), 24 mm |
| `port_smog.jpg` | Sodium lamps in the port's smog | 23:00, smog | (-1694.5, 33.6, 1.7) to (-1693.8, 13.6, 2.5), 20 mm |
| `monorail_walk.jpg` | A riverside walk under the monorail | 23:00, rain | (334.5, 441.6, 1.7) to (353.3, 490.5, 9), 20 mm |
| `steam_street.jpg` | Steam rising from the street between parked cars | 23:00, rain | (610, 1429.4, 1.7) to (611.6, 1439.3, 3), 20 mm |
| `searchlights.jpg` | Searchlights sweeping over the tower crowns | 23:00, fog | (560, -260, 180) to (960, 120, 180), 24 mm |
| `hero_cars.jpg` | Parked cars up close on a wet crossing | 23:00, rain | (925, 84, 1) to (945, 66, 0.9), 35 mm |
| `junction_dusk_rain.jpg` | A junction at dusk in the rain | 19:00, rain | (790, 1582, 1.7) to (720, 1590, 4), 24 mm |
| `walker_shadow.jpg` | Looking down at yourself and your shadow on foot | 16:00, clear | the walker at (543.3, 1576, 0.2) facing east |

## How they were taken

By the check's play views at 8K (AT7's `CITYGEN_UE_VIEW_RES`), one run per round of views:

```bash
CITYGEN_UE_PLAY_SHOTS_ONLY=1 CITYGEN_UE_VIEW_RES=7680x4320 \
  .venv/Scripts/python.exe -m citygen unreal BUILD CityAG16.uproject --engine C:/Games/UE_5.8 \
  --check-only --shots OUT --view t1900_junction__rain 790 1582 1.7 720 1590 4 24 ...
```

A view's prefix sets the hour (`night_` 23:00, `dusk_` the plan's dusk, `t<HHMM>_` that hour,
`pday_` 16:00) and its `__<state>` suffix the weather, as AT3 and AT5 set them. The walker's
shot is the check's `walk_body` from a `--view walk_spot__clear ...`: this branch lets that
view take a weather state and takes the walk shots at `CITYGEN_UE_VIEW_RES` too (after 8 s
for the exposure to settle). Three rounds (25, 20 and 10 views, about 25 minutes each with
the walk) gave 55 candidates; the 16 above were kept.

## What did not come out well

- **The map's edge.** Every view from high over the city's sides shows where the generated
  map ends: the sea stops at a straight line and land is cut square at the map's border.
  The views kept look inward or along the city (the whole city from the north over its
  densest district, the day view over the port toward the core).
- **Under a viaduct.** Delta's raised highways cross local streets only at interchanges and
  in the dark port, and it has no deck; the monorail along the river's quay gave the
  strongest "under a structure" street.
- **Steam** reads only from close: plumes are a few meters tall, so from 20 m they are small
  puffs; the steam shot stands 10 m from its manhole.
- **The walker's shot** is dim: the sun is behind the walker, so the body is in its own
  shade, and the exposure settles on the dark body filling half the frame. The shadow reads
  well.
- **Fog** barely shows round the searchlights from 180 m up; the beams carry the shot.
