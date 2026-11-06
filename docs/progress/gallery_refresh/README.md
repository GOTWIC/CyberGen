# Gallery refresh (#113)

Pictures on the gallery (https://swagnik.org/CyberGen/) rendered again on main, after M21's
tower forms, AG15's facades and night lighting, M20's signs, AG14's fit and finish and the
sky tube fixes. The old pictures stay where they are, as their milestones' record; the
gallery's entries keep their steps' dates.

All from full builds on main (`citygen build SPEC OUT --blockout`, then `assetgen build OUT`)
with `assetgen materials preview OUT ...` (8K, 7680 px wide).

- [`landmarks_8k.jpg`](landmarks_8k.jpg): the landmarks (as AG5's `landmarks_8k.jpg`), four
  views of 3840 by 2160 by night (`--only-night`), AG15's crown and edge lights on, with no
  labels (the showcase names no city):
  - Vesper Bay's megatower over the Corporate Core: `--eye 1450 650 180 --target 815 267 220
    --lens 28`;
  - Nexus City's megatower and spires: `--eye -750 900 170 --target 180 1040 200 --lens 32`;
  - the arcology (Vesper Bay with The Stacks' `landmarks` set to `["arcology"]`, as AG5 built
    it): `--eye 820 1250 210 --target 280 904 200 --lens 28`;
  - Greyhook's wheel over the Lantern Strip: `--eye -1400 -150 70 --target -1070 -44 65
    --lens 32`.
- [`vesper_bay_city_full.jpg`](vesper_bay_city_full.jpg): the whole of Vesper Bay with every
  building, street, water and ground piece (`--views city_full`), and
  [`vesper_bay_city_full_night.jpg`](vesper_bay_city_full_night.jpg) the same by night
  (`--only-night`, AG15's lighting schedules), a day and night pair on the showcase.
- [`sky_tube_night.jpg`](sky_tube_night.jpg): Delta Megacity's Skyline Loop on a level stretch,
  curving in toward the Corporate Core's towers at night (`--only-night --eye 1150 1000 130
  --target 850 250 70 --lens 28`). It replaces
  [`crown_loop_night.jpg`](crown_loop_night.jpg) (the Crown Loop through Vesper Bay's Corporate
  Core, `--eye 1440 600 140 --target 1150 0 100 --lens 28`), whose tube climbs in steps and
  humps there (#124).
- [`canal_night.jpg`](canal_night.jpg): a canal in Neon Strand by night, looking north up the
  canal so buildings fill the middle (`--only-night --eye -408 850 1.1 --target -410 915 -0.9
  --lens 24`), drawn without its moored boats (a view of the build whose props contribution
  keeps the boat entries with no placements): one boat lay across a quay stair, and the
  boats read poorly at this size. The camera stands just past a quay stair whose open top
  end would show the water through it (#131).
- [`street_the_stacks_night.jpg`](street_the_stacks_night.jpg): a street in The Stacks at
  night, lit by AG15's schedules (`--views street_2 --only-night`; the layout has moved since
  AG6's `street_2_night.jpg`, so the camera stands elsewhere in the same district).

## The rest of #113

Builds on main at `c256b13` (#125's asset fixes in), every city passing all its city and asset
checks. A view of one's own is `assetgen materials preview OUT --views none --eye X Y Z
--target X Y Z --lens L` (`--views none` keeps the default district and street views out),
`--night` adds each view by night, `--only-night` gives only that.

- **Cities** ([`cities/<city>/city_full.jpg`](cities/)): the whole of each sample city at 8K,
  `assetgen materials preview OUT --views city_full --width 7680`, for the README's stage 2
  Cities gallery (Vesper Bay's is [`vesper_bay_city_full.jpg`](vesper_bay_city_full.jpg)
  above). About 25 minutes a city alone on the M4 Mac, an hour for the bigger ones; one at a
  time. EEVEE renders on the GPU, and at 8K a city of more than about 80 million drawn
  triangles needs more GPU-wired memory than the Mac allows (Nexus City asked for 21 GB of
  its 19 GB, and macOS killed Blender), so Nexus City, Delta Megacity, Vesper Bay Pinned,
  Cragmouth and Vesper Bay Decks are at 3840 px (`--width 3840`); Greyhook, Saltreach Free
  Port and Vesper Bay Stacks are at 8K.
- **Shopping street in Unreal** ([`unreal/shopping_street_day.jpg`](unreal/shopping_street_day.jpg),
  [`unreal/shopping_street_night.jpg`](unreal/shopping_street_night.jpg)): Greyhook's Lantern
  Strip looking west from its east end, the wheel over the roofs, by day and by night (the
  play features' lamps, light pools and sign washes). A throwaway project of the exporter's
  own: `citygen unreal OUT CgGallery.uproject --new-project --no-hlod --check --shots DIR
  --view pday_wheel_e -985 -107 3.0 -1070 -52 32 24 --view night_wheel_e -985 -107 3.0 -1070
  -52 32 24` (views named `pday_*` and `night_*` are shot from the free camera in the play
  world, 1920 by 1080; an editor view at `--shot-width 7680` has no night). Built on main at
  `21528ae`, before #125.
- **Ramps on four levels** ([`stack_interchange.jpg`](stack_interchange.jpg)): Vesper Bay Stacks'
  stack interchange by day from the northwest, every stage 2 asset on (`--eye 644 714 160
  --target 937 562 5 --lens 28`); the night version left out, its roads too dark from the air.
- **A sky station inside a tower** ([`sky_station_night.jpg`](sky_station_night.jpg)): on the
  Corporate Core station's platform inside its traced tower in Vesper Bay Stacks, at the
  tube's end, looking out of the portal along the lit rings (`--only-night --eye -675.65
  -690.64 91.7 --target -623.8 -662.1 95 --lens 20`), and
  [`sky_tube_into_tower_night.jpg`](sky_tube_into_tower_night.jpg) the tube entering that
  portal from outside (`--eye -480 -560 115 --target -665 -680 95`). Vesper Bay's own Crown
  Loop has no station in a tower on main (its tube runs on pylons past the towers).
- **The tallest building of each era** ([`towers_by_era.jpg`](towers_by_era.jpg)): AG2's
  `tower_views` rule (the tallest building of each era, landmarks and megasite structures
  left out) across the sample cities, also leaving out shanty stacks and traced buildings, each
  from a three-quarter view onto its main front (`buildings.thumb.front_dir` turned 28
  degrees), pitched 12 degrees for a tower and 30 for a low building, framed to its height,
  rendered 3648 px wide with `--lens 40` and cropped square, labelled with era, facade
  system, form, height and city.
- **64 buildings drawn at random** ([`contact_sheet_greyhook.jpg`](contact_sheet_greyhook.jpg)):
  `assetgen preview OUT --views sheets --only random` on Greyhook, whose draw has the fewest
  shanty stacks (16% of its buildings, about 30% in the other cities).

**Preview fix.** The whole-city views (`city`, `city_full`) drew AG7's streets, AG12's water
and AG13's ground only on the tiles with a building, while the blockout's pieces they replace
were taken out everywhere: open sea came out as a checkerboard of missing tiles, the delta's
marsh and a bridge over the sea were gone. Both views now draw every street, skybridge, water
and ground tile (`whole` in `previews.plan_views`, read in `materials/preview.py`; test
`test_whole_city_views_take_every_water_and_ground_tile`).
