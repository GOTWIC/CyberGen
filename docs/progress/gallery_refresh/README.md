# Gallery refresh (#113)

Pictures on the gallery (https://swagnik.org/CyberGen/) rendered again on main, after M21's
tower forms, AG15's facades and night lighting, M20's signs, AG14's fit and finish and the
sky tube fixes. The old pictures stay where they are, as their milestones' record; the
gallery's entries keep their steps' dates.

All from full builds on main (`citygen build SPEC OUT --blockout`, then `assetgen build OUT`)
with `assetgen materials preview OUT ...` (8K, 7680 px wide).

- [`landmarks_8k.jpg`](landmarks_8k.jpg): the landmarks (as AG5's `landmarks_8k.jpg`), four
  views of 3840 by 2160 by night (`--only-night`), AG15's crown and edge lights on:
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
- [`crown_loop_night.jpg`](crown_loop_night.jpg): the Crown Loop's lit rings winding through
  the Corporate Core at night, its towers behind (`--only-night --eye 1440 600 140 --target
  1150 0 100 --lens 28`).
- The canal by night is the moorings fix's 8K render
  ([`../fix_moorings/vesper_bay/8k/water_canal_night_after.jpg`](../fix_moorings/vesper_bay/8k/water_canal_night_after.jpg),
  AG12's `--views water --night` camera): the boats float clear of the quay walls.
- [`street_the_stacks_night.jpg`](street_the_stacks_night.jpg): a street in The Stacks at
  night, lit by AG15's schedules (`--views street_2 --only-night`; the layout has moved since
  AG6's `street_2_night.jpg`, so the camera stands elsewhere in the same district).

**Preview fix.** The whole-city views (`city`, `city_full`) drew AG7's streets, AG12's water
and AG13's ground only on the tiles with a building, while the blockout's pieces they replace
were taken out everywhere: open sea came out as a checkerboard of missing tiles, the delta's
marsh and a bridge over the sea were gone. Both views now draw every street, skybridge, water
and ground tile (`whole` in `previews.plan_views`, read in `materials/preview.py`; test
`test_whole_city_views_take_every_water_and_ground_tile`).
