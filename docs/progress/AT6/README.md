# AT6: looks and art direction (atmosgen)

Stage 3's seventh milestone (`docs/atmosgen_scope.md` sections 6.5 and 13): post and grading
per look and per district (decision 12.5: near-photorealistic cyberpunk, clean or gritty by
place), the exposure locked per look and hour with a day that reads, `atmosgen review` for
art-direction rounds and the `atmosgen` skill (prompt to atmos spec), with the art-direction
notes AT3 to AT5 left. Built on the Windows PC (RTX 4070 Ti, 32 GB), 2026-11-13, on main after
AT5 (#217).

## What AT6 built

| Part | Where | What |
|---|---|---|
| The look's post | `atmosgen/look.py`, `presets.POST`, `POST_KEYS` | per look a set by night and one by day: bloom, lens flares over a threshold, film grain, chromatic aberration from a start (the frame's middle clean), vignette, sharpening, the grade's saturation and contrast, a shadow tint and a highlight tint as gains (the tint's hue over the mean of its linear rgb, `tint_gain`), the highlights' saturation, a black lift, local exposure's shadow and highlight contrast; neon rain teal in the shadows and magenta in the highlights by night (softer by day), clear night cool and warm, smog dusk violet and amber, overcast day grey |
| A post per district | `presets.DISTRICT_POST`, `DISTRICT_TINT`, `look.district_sets` | the look's sets pulled by the district's grit (`spec.mood`: its archetype's, up with danger, down with wealth): clean is crisp (grain 0.4 times the look's, fringes half, contrast 4% up, sharpening 0.6, soft bloom), gritty is dirty glass (grain up to 2.2 times, fringes 2 times, flares, halation, lifted blacks, a heavier vignette, color muted but for the neon); and tinted by its archetype: the corporate core steel blue and icy white, research and transit cool, the residential heights warm, markets magenta, old towns a sickly sodium green with amber highlights, the megablocks and the port sodium amber |
| The district raster | `look.raster`, `post_districts.png` | each 32 m cell's district (its middle in the polygon, else the nearest: water, the map's edge), the runtime blending the districts by where the view stands |
| The exposure | `presets.DAY_EV100`, `POST_EXPOSURE`, `OVERCAST_TAKE`, `SKY_SHARE`; `look.overcast_shift`, `sky.day_ev` | still held per hour (AT3: no adaptation pumping); the day's a clear day's, measured (below: -0.8 EV100 for AT3's 1.6), moved by `overcast_comp` (0.5) of the light the weather's clouds take off the sun (AT5's overcast; the sky light dims with the deck too, `SKY_SHARE` 0.1); the sky's `ev_day` the same at the look's own cover |
| Art direction in the spec | `spec.PostSpec`, `DistrictMood` | `post`: multipliers of the bloom, flares, grain, fringes, vignette, saturation, contrast and the tints' strength, the tints' colors, `day_ev_bias`, `overcast_comp`, `districts` (one post for the city); a district's `shadows`, `highlights` and `tint` |
| Previews | `look.grade`, `look.preview` (`atmosgen lux`) | `preview_post.png`: the districts by grit over the city and every district's grade on a test chart (a grey ramp, the neon accents, a sodium lamp, wet asphalt, concrete, skin) by night and by day, through Unreal's ColorCorrectAll in numpy and a filmic curve |
| Review | `atmosgen/review.py`, `atmosgen review`, `atmosgen spec diff` | a round's `review.md`, `review.json` and `review_shots.jpg`: the plan's checks, the city's and every district's numbers (light, exposure, glow, air, weather, post), every shot's exposure as the eye reads it (the mean log luminance in stops from middle grey, the median, clipped, crushed, saturation) beside the last round's, the previews, and the spec parameters that answer what a reviewer may see |
| The skill | `atmosgen/skill/SKILL.md` | prompt to atmos spec: inputs, the spec's fields, plan, previews, Unreal shots, up to three rounds with `atmosgen review`, the report. Sessions cannot write `.claude/`: **Swagnik copies it into `.claude/skills/atmosgen/SKILL.md`** |
| Exporter | `citygen/unreal_atmos.py` (`post_settings`, `POST_FLOATS`), `ue/import_city.py` | the controller's look (the sets, 20 floats each, the districts', the raster as runs, the day's exposure replacing the sky's, the overcast's compensation) in its hash; no new `ATMOS_VERSION` (the cells kept); the manifest's `atmos.post`; `unreal.ALWAYS_COOK` adds the engine's film grain textures |
| Runtime | `ue/CityGenAtmos` (`UpdatePost`, `ApplyPostSettings`, `OvercastShift`) | the raster sampled on a 5 x 5 grid over 90 m round the view a few times a second, each district's weight eased over 1.5 s, the sets blended by those weights and by Night, written into the controller's own post-process volume only when a value moved: one volume for every district (AG16 found each enabled volume costs the game thread a physics query a frame); console `.Post`, `.PostDistricts`, `.PostSet KEY VALUE`, `.DayEV`, `.SteamGlow` |
| Plumes (AT4's note) | `presets.STEAM_GLOW`, `STEAM_FAR`, `PUFFS`, `EMITTERS`; `M_CgSteam` (atmos assets 17) | by night a plume is lit by the city round it (an emissive of its albedo times Night, about middle grey), its opacity kept with distance (twice from 30 m to 150 m), a stall's cooking 6 cards, wider and denser |
| The curb sawtooth (AT5's note) | `atmos_assets.py` (`WET`, `GLOSS_N`) | the wet decals' face normal from fine derivatives (`ddx_fine`, `ddy_fine`: a pixel and its own neighbor). The cause: the coarse derivatives are a 2 x 2 quad's, so along a curb's top edge each quad read as floor or wall as a whole and the dry wall share stepped in teeth along it |
| Check and benchmark | `ue/check_city.py`, `citygen/bench.py` | the check's look by night (`post`, a district by the player), `*_nopost` views, `post_views`; every atmos pass sets `Post 1`, `ATMOS_OFF` `Post 0`, passes `night_plan_nopost` and `day_plan_nopost` |

## The failing test on main

`tests/test_unreal.py::test_stage2_from_assetgen` found `player_start` among the updated keys
since #215. **The test was wrong, not the code:** since the visible lights the player start
reads the city model (`unreal._start_spot`: an open, lit sidewalk), and the test's blockout
folder (`_blockout_files`) held no `city_model.json` while its stage 2 copy (`staged`) did, so
the two manifests started the player in different places. A real build folder always has the
model beside its blockout; `_blockout_files` now writes it too.

## The plan on Delta

`atmosgen plan` on the play fixes' Delta build (`neon_rain`): every check passes as in AT5
(the plan's lights unchanged; 9 cells' plumes changed by the cooking). The post per district
(night; the look's: bloom 1, flare 0.45, grain 0.12, fringe 0.35, vignette 0.5, sharpen 0.2,
saturation 1.1, contrast 1.08):

| District (grit) | Bloom | Flare | Grain | Fringe | Vignette | Sharpen | Saturation | Contrast | Lift | Shadows x | Highlights x |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Corporate Core (0) | 0.85 | 0.27 | 0.05 | 0.18 | 0.50 | 0.60 | 1.13 | 1.12 | 0 | 0.82 0.98 1.21 | 1.07 0.93 1.00 |
| Research Campus (0) | 0.85 | 0.27 | 0.05 | 0.18 | 0.50 | 0.60 | 1.13 | 1.12 | 0 | 0.83 1.00 1.17 | 1.07 0.93 0.99 |
| Midtown (0.21) | 0.94 | 0.36 | 0.09 | 0.29 | 0.53 | 0.50 | 1.11 | 1.11 | 0.0005 | 0.87 0.99 1.14 | 1.08 0.93 0.99 |
| Transit Nexus (0.3) | 0.99 | 0.41 | 0.11 | 0.33 | 0.55 | 0.45 | 1.10 | 1.10 | 0.0008 | 0.81 1.00 1.20 | 1.08 0.93 0.99 |
| Old Town (0.955) | 1.28 | 0.70 | 0.25 | 0.68 | 0.64 | 0.12 | 1.03 | 1.05 | 0.0024 | 0.87 1.08 1.03 | 1.21 0.91 0.89 |
| Industrial Port (1) | 1.30 | 0.72 | 0.26 | 0.70 | 0.65 | 0.10 | 1.02 | 1.05 | 0.0025 | 0.98 0.98 1.00 | 1.28 0.89 0.84 |

![Delta: the districts by grit and each district's grade on a chart, by night and by day](delta_preview_post.png)

## The day's exposure, measured

AT3 set the day's exposure by eye (1.6 EV100, 0.8 under neon rain's deck). Read as the eye
reads it (`atmosgen.review.shot_numbers`: the mean log luminance in stops from middle grey)
the day was darker than the night: the Corporate Core street at -6.3 stops in rain and -5.3
clear, -2.6 by night; under a viaduct -6.9. Shots at fixed viewpoints in one game at -1.6 to
0.8 EV100 (`CityGenAtmos.DayEV`, `wip/02_tuning`): a clear street reads right at -0.8 (-2.1
stops), each 0.8 EV about 0.9 stops. In rain the clouds take a stop more (the same street at
the same exposure); giving back all of it made rain brighter than a clear day (the port -0.6
stops), half of it (`overcast_comp` 0.5) leaves a rainy street a little darker than a clear one.
Under the viaduct by day local exposure (shadow contrast 0.7) lifts the underside without
greying the sky.

| Shot (stops from middle grey) | Before (AT5) | After |
|---|---|---|
| Corporate Core street, day, rain | -6.27 | -1.97 |
| Corporate Core street, day, clear | -5.28 | (tuning: -2.08) |
| Old Town street, day, rain | -5.62 | -1.78 |
| Under the viaduct, day, rain | -6.94 | -2.51 |
| Corporate Core street, night | -2.61 | -3.14 |
| Old Town street, night | -2.49 | -2.84 |
| The port, night | -4.73 | -5.06 |
| Corporate Core street, dusk | -3.57 | -3.04 |

By night the look reads about a third of a stop darker (more contrast, the vignette); dusk is
brighter (the day's exposure the dusk curve blends toward is brighter).

## Unreal

Delta imported over AT5's import in CityAG16 (`citygen unreal ... --atmos DIR --no-hlod`,
`CITYGEN_UE_OFFLOAD=500`): the plugins built (15 s), atmosgen's assets made again (version 17),
the controller and 9 cells updated, nothing else touched, 3 min 14 s. The check passes
(streaming, collision, the walk, the play features, the sky, the air, the weather, and the
look: "post True, by the player Industrial Port (bloom 1.30, grain 0.26, fringe 0.70,
saturation 1.02, contrast 1.05, sharpen 0.10)"). The same viewpoints before (AT5's import, no
AT6 code) and after, from the check's free camera at 1920 x 1080:

**The Corporate Core street**: by night before, without the post, with it; at dusk before,
without, with; by day in rain before, clear before, in rain after:

![](unreal/cmp_core.jpg)

**Before and after**: Old Town by night, the port by night, under the viaduct by day in rain,
an Old Town food market's cooking by night, Old Town by day in rain:

![](unreal/cmp_misc.jpg)

| | Before (AT5) | After (AT6) |
|---|---|---|
| Corporate Core, night | ![](unreal/before/night_core.jpg) | ![](unreal/after/night_core.jpg) |
| Old Town, night | ![](unreal/before/night_oldtown.jpg) | ![](unreal/after/night_oldtown.jpg) |
| The port, night | ![](unreal/before/night_port.jpg) | ![](unreal/after/night_port.jpg) |
| The core from the air, night | ![](unreal/before/night_air.jpg) | ![](unreal/after/night_air.jpg) |
| Old Town, dusk | ![](unreal/before/dusk_oldtown.jpg) | ![](unreal/after/dusk_oldtown.jpg) |
| The port, dusk | ![](unreal/before/dusk_port.jpg) | ![](unreal/after/dusk_port.jpg) |
| Corporate Core, day in rain | ![](unreal/before/pday_core.jpg) | ![](unreal/after/pday_core.jpg) |
| Old Town, day in rain | ![](unreal/before/pday_oldtown.jpg) | ![](unreal/after/pday_oldtown.jpg) |
| Under the viaduct, day in rain | ![](unreal/before/pday_viaduct.jpg) | ![](unreal/after/pday_viaduct.jpg) |
| The port, day in rain | ![](unreal/before/pday_port.jpg) | ![](unreal/after/pday_port.jpg) |
| The core from the air, day | ![](unreal/before/pday_air.jpg) | ![](unreal/after/pday_air.jpg) |
| A food market's cooking, night | ![](unreal/before/night_stall.jpg) | ![](unreal/after/night_stall.jpg) |
| Smog and plumes over the port from 120 m | ![](unreal/before/night_portsmog.jpg) | ![](unreal/after/night_portsmog.jpg) |
| The curb by an Old Town awning in rain | ![](wip/02_tuning/curb_before.jpg) | ![](wip/02_tuning/curb_after.jpg) |

What they show:

- **Clean or gritty by place:** the Corporate Core cooler and crisper (its shadows steel blue,
  little grain, sharpened), Old Town warmer and grainier with amber highlights and fringes at
  the frame's edge, the port's sodium deeper with lifted, grainy blacks.
- **The day reads:** a rainy day is a grey, wet, readable street (four stops brighter), the
  street under the viaduct visible, a clear day a little brighter than a rainy one.
- **The cooking** over the Old Town market's stalls now shows as a plume by night.
- **The curb** by the awning is one clean edge; the sawtooth is gone.

## The review sheet

`atmosgen review` on Delta with the after shots and AT5's as the previous round's
(`review/review.md`, its contact sheet `review/review_shots.jpg`: before and after side by
side): the checks, the city's and every district's numbers, every shot's exposure in stops
beside the last round's, and the levers. The same sheet is a spec round's in the skill's loop.

## The night's frame time

The lean benchmark once (`--bench-atmos`, decision 12.6; `bench/`): the walk, the drive and
the flight at 2560 x 1440, `night_plan_all` and the dusk and day passes the post touches. Not
flagged: the game held the foreground throughout (taken once by the Claude app, given back),
the other processes 1.0 cores, none starved. No rerun: every pass is more than 0.3 ms under
the budget. **Before** is AT5's after (#217, `docs/progress/AT5/bench`).

| Pass | p95 all | walk | drive | fly | GPU p95 all |
|---|---|---|---|---|---|
| `night_plan_all` before (AT5) | 15.1 | 14.8 | 15.0 | 15.3 | 13.2 |
| **`night_plan_all`** (the look's post on, its district by the player) | **15.4** | **15.2** | **15.2** | **15.8** | **13.4** |
| `dusk_plan_all` | 15.2 | 15.6 | 15.0 | 15.3 | 13.1 |
| `day_plan_all` (rain, fog, wet streets by day) | 13.8 | 13.5 | 12.0 | 14.9 | 11.4 |

(ms.) **The night is 15.4 ms p95 over the route, 1.3 ms under decision 12.6's 16.7 ms**, 0.3
ms over AT5's. At fixed viewpoints in one game (`wip/02_tuning/viewtune.json`, GPU ms,
median, the post on against off) the look costs 0.15 ms of GPU in the Corporate Core, 0.22 in
Old Town and 0.24 at the port (bloom, flares, grain, fringes, local exposure; the grade is in
the tonemapper's LUT either way); the flight's p95 is the game thread's (15.0 ms, the
streaming), as in AT5.

## Validation

- Tests (logged, `-v -rfE --durations=25`): `tests/atmosgen/test_at_look.py` (new: the tints,
  the look's sets with the spec over them, districts clean or gritty, the raster, the grade
  against Unreal's defaults, the exposure and the overcast, the plan's and the exporter's
  records, the runtime's key order against the exporter's, the review sheet, the spec diff),
  `tests/atmosgen/test_at_sky.py` (the day's exposure), `test_at_plan.py`, `test_at_air.py`,
  `tests/test_unreal_atmos.py`, `tests/test_bench.py` (the post passes), and
  `tests/test_unreal.py` but its Unreal imports (the cook folders, `test_stage2_from_assetgen`).
- Delta's plan again (every check passes), imported over AT5's import in CityAG16 and checked
  with the views above by night, dusk and day; the post's GPU at fixed viewpoints; the lean
  benchmark once.

## The packaged game

PACKAGE

## Open items

- **The plumes take the light round them:** the market's cooking reads greenish under Old
  Town's green neon and sodium; a plume's own warm tint by kind would need the material to
  take the emitter's color over the lighting.
- **The port by night** reads a third of a stop darker with its gritty post (lifted but
  grainy blacks, a heavier vignette): a darker port is the mood, but a spec round may lift it
  (`districts.Industrial Port.grit`, `post.vignette`).
- **One weather for the day's exposure:** the overcast's compensation follows the cloud cover
  of the weather state, not the light a view actually gets; a street under a viaduct stays
  darker than an open one (local exposure softens it).
- **Blender previews** do not apply the grade (Unreal's alone); `preview_post.png` shows each
  district's grade on a chart.
- **The menu:** the Tab menu has no Look row; the console's `CityGenAtmos.Post` and
  `.PostDistricts` switch it.
- **The trees' sway** (AT5) stays off.
