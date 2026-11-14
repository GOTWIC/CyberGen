"""atmosgen's side of the Unreal exporter (docs/unreal_export.md, "From AT0" and "From AT1").

- The runtime plugin `CityGenAtmos` (citygen/ue/CityGenAtmos) is installed and built with the
  play features' (`unreal_play.PLUGINS`, one UnrealBuildTool run).
- Its assets (`citygen/ue/atmos_assets.py`: MPC_CityGenAtmos, M_CgRain, M_CgWet under
  /Game/CityGen/Core/Atmos) are made in the project by a headless editor run, skipped when the
  project has this version of them (`make_assets`); `citygen unreal` runs it before an import
  with an atmos plan.
- AT1: a city's atmos plan (BUILD/atmos, or `--atmos DIR`) becomes layer 3 of the manifest
  (`write_atmos`, the manifest's `atmos`): the controller (key `atmos`, always loaded) with
  the plan's settings, and a data actor per 128 m cell of World Partition's main grid (key
  `atmos.lights.<tile>.<quarter>`), each holding its lights packed (`pack`), its hash the
  hash of its lights' records. The bulky arrays go to `BUILD/unreal/atmos.json` beside the
  manifest, which keeps the keys and hashes. A plan whose lux check did not pass (or an AT0
  plan, which has none) is not delivered (scope 8): the city imports without it.
- AT2: the packing's version 2 (`PACK_VERSION`): 19 floats a light (a blink's or a sweep's
  period, amount and phase after AT1's 16), the flags' bit 6 the high tier and bits 28-29 the
  animation; the controller's `max_high` and `high_range_m` (the plan's high tier); a plan
  whose faces check failed is not delivered either.
- AT3: the controller's sky and time (`sky_settings`: where the sun and the moon stand, the
  exposure, Night, sun, sky light and stars curves over the sun's elevation, the cloud deck,
  the named hours), and the deck's glow raster copied beside the manifest
  (`BUILD/unreal/atmos_sky_glow.png`, `GLOW`), which the import makes a texture the
  controller's sky reads; both in the controller's hash.
- AT4: the packing's version 3: a cell also holds its fog volumes (`pack_volume`) and steam
  and smoke emitters (`pack_emitter`), a cell made where any of the three lie; the
  controller's air (`air_settings`: the height and volumetric fog by the hour, each light
  kind's volumetric scattering, the live sets of volumes and plumes, the engine settings it
  runs with); a plan whose air check failed is not delivered.
- Visible lights (after AT4, Swagnik's walk of the packaged Delta, 2026-11-12): the
  controller's `sight_settings` (the plan's sight raster, `atmosgen/sight.py`, as runs of
  its cells, `sight_runs`, with its bounds in Unreal's frame, cell, steps and skips; the
  tiers' `sight_m` and `sight_max`), by which the runtime keeps live round a walker the
  lights the walker sees out to `sight_m`. The cells are always loaded (the importer's
  `atmos_cells`): their lights reach past World Partition's loading range (768 m).
- AT5 (weather): the packing's version 4: a cell also holds its drip lines (`pack_drip`, a
  cell made where any lie); the controller's weather (`weather_settings`: the states' values
  in `WEATHER_KEYS` order, the start state, the rain's age, the wind, the cover channel's
  datum and step, what the runtime keeps near the view); the plan's masks stitched into two
  city-wide textures at `WET_TEXEL_M` beside the manifest (`wet_textures`:
  `atmos_wet_cover.png`, the cover channel, and `atmos_wet_surface.png`, gloss, puddles and
  drips), which the import makes textures the wet streets' decals and the rain read; a plan
  whose weather check failed is not delivered.
- AT6 (looks): the controller's look (`post_settings`: the look's night and day post sets,
  each district's, the district raster as runs with its bounds, the blend, the day's exposure
  with its bias and the overcast's compensation), all in the controller's hash; the air's
  `steam_glow` and `steam_far` (the plumes by night and far off).
- AT7 (the far city): the packing's version 5: a cell also holds the far cards whose middle
  lies in it (`pack_far`: a glow, a pool or a wash per light the far view sees, from the
  plan's `far/<tile>.json`), a cell made where any lie; the controller's `far_settings` (the
  cards' gain, least width on screen and fade); a plan whose far check failed is not
  delivered.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

SCRIPT = Path(__file__).parent / "ue" / "atmos_assets.py"
STAMP = "citygen_atmos_assets.txt"          # in PROJECT/Saved
PLAN_DIR = "atmos"                          # BUILD/atmos: `atmosgen plan`'s default
DATA = "atmos.json"                         # BUILD/unreal/atmos.json
GLOW = "atmos_sky_glow.png"                 # BUILD/unreal/atmos_sky_glow.png (AT3)
FIXTURES = "unreal_contribution.fixtures.json"    # the plan's fixtures (dlss_lamps_flicker)
CONTROLLER_KEY = "atmos"
CELL_M = 128.0                              # World Partition's main cells (unreal.MAIN_CELL_M)
PACK_VERSION = 5                            # 2 (AT2): the high tier, a blink or a sweep;
                                            # 3 (AT4): a cell's fog volumes and emitters;
                                            # 4 (AT5): its drip lines; 5 (AT7): its far cards
DFLOATS = 7                                 # AT5: a drip line (CityGenAtmosPack::DripFloats)
FFLOATS = 12                                # AT7: a far card (CityGenAtmosPack::FarFloats)
FAR_TYPES = ("glow", "pool", "wash")
FAR_TIERS = ("mid", "high", "fixture")
DRIP_KINDS = ("awning", "deck", "road", "canopy", "shelter")
# AT5: the weather states' values as the controller holds them (`WeatherValues`: these per
# state, in `WeatherNames` order)
WEATHER_KEYS = ("rain", "streak", "drops", "wetness", "puddles", "cover", "volumes", "gust",
                "wind_m_s", "fog_density", "fog_falloff", "fog_extinction", "fog_albedo_r",
                "fog_albedo_g", "fog_albedo_b")
WET_COVER = "atmos_wet_cover.png"           # BUILD/unreal/: the cover channel, city-wide
WET_SURFACE = "atmos_wet_surface.png"       # ... gloss, puddles, drips
WET_TEXEL_M = 1.0                           # the textures' texels (the plan's 0.5 m masks,
                                            # two by two: 22 MB of video memory for Delta
                                            # against 89 at 0.5 m)
FLOATS = 19                                 # CityGenAtmosCell.h, CityGenAtmosPack
INTS = 2
VFLOATS = 14                                # AT4: a fog volume (CityGenAtmosPack::VolFloats)
VINTS = 1
EFLOATS = 9                                 # AT4: an emitter (CityGenAtmosPack::EmitFloats)
# AT6: a post set's floats (CityGenAtmosActor.h's EPostKey, PostFloats): the look's scalar
# keys (atmosgen.presets.POST_KEYS), then the shadows' and the highlights' gains
POST_FLOATS = ("bloom", "flare", "flare_threshold", "grain", "chromatic", "chromatic_start",
               "vignette", "sharpen", "saturation", "contrast", "highlight_sat", "lift",
               "local_shadows", "local_highlights", "shadows_r", "shadows_g", "shadows_b",
               "highlights_r", "highlights_g", "highlights_b")
EINTS = 2
VOLUME_KINDS = ("mist", "smog", "haze", "tunnel_haze", "steam_bank")
EMITTER_KINDS = ("steam", "smoke", "exhaust", "cooking")
EMITTER_MOUNTS = ("manhole", "drain", "vent", "roof", "stall", "chimney", "stove")
SHAPES = {"spot": 0, "point": 1, "rect": 2}
ANIMS = {"blink": 1, "sweep": 2}
QUARTERS = {(0, 0): "sw", (1, 0): "se", (0, 1): "nw", (1, 1): "ne"}


def assets_version() -> str:
    m = re.search(r'^VERSION = "([^"]+)"', SCRIPT.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "0"


def make_assets(root: Path, uproject: Path, log: Path, force: bool = False) -> dict:
    """atmosgen's runtime assets in the project (a headless editor run); skipped when the
    project's stamp names this version and engine. {ok, made, error, ...}."""
    from .unreal import run_editor
    up = Path(uproject).resolve()
    stamp = up.parent / "Saved" / STAMP
    want = f"{assets_version()} {Path(root).resolve().as_posix()}"
    if not force and stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == want:
        return {"ok": True, "made": False, "version": assets_version()}
    log.parent.mkdir(parents=True, exist_ok=True)
    job = {"result": str(log.with_name("atmos_assets_result.json"))}
    res = run_editor(Path(root), up, SCRIPT, job, log, timeout=1800.0)
    if res.get("ok"):
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(want + "\n", encoding="utf-8", newline="\n")
        res["made"] = True
    return res


# --- layer 3: the plan in the manifest ------------------------------------------------------

def _sha16(data) -> str:
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def plan_dir(build: str | Path, given: str | Path | None = None) -> Path | None:
    """The atmos plan's folder: `given`, else BUILD/atmos; None when it holds no plan."""
    d = Path(given) if given else Path(build) / PLAN_DIR
    return d if (d / "atmos_plan.json").is_file() else None


def _kinds() -> list[str]:
    from typing import get_args

    from atmosgen.planmodel import LightKind
    return list(get_args(LightKind))


def _mounts() -> list[str]:
    from typing import get_args

    from atmosgen.planmodel import Mount
    return list(get_args(Mount))


def _r(v: float, k: int = 3) -> float:
    r = round(float(v), k)
    return 0.0 if r == 0.0 else r


def pack(L: dict, schedules: list[str], kinds: list[str], mounts: list[str]):
    """A light's record as the cell actor holds it (CityGenAtmosCell.h): FLOATS floats in
    Unreal's frame (cm, X east, Y south, pitch and yaw in degrees, yaw turned: citygen's
    counterclockwise heading is Unreal's -yaw; AT2: its animation's period, amount and
    phase) and INTS ints (flags, seed)."""
    x, y, z = L["pos"]
    yaw, pitch = L["aim"]
    shape = SHAPES[L["shape"]]
    w, h = (L.get("size") or [0.0, 0.0])
    cd = float(L["cd"])
    inten = cd / max(0.01, w * h) if shape == 2 else cd
    inner, outer = (L.get("cone") or [0.0, 0.0]) if shape == 0 else \
        ([float(L.get("barn_deg") or 90.0), 0.0] if shape == 2 else [0.0, 0.0])
    col = L["color"]
    f = [_r(x * 100.0, 1), _r(-y * 100.0, 1), _r(z * 100.0, 1), _r(pitch), _r(-yaw),
         _r(w * 100.0, 1), _r(h * 100.0, 1), _r(float(L.get("source_m") or 0.0) * 100.0, 1),
         _r(inten, 2), _r(col[0], 4), _r(col[1], 4), _r(col[2], 4),
         _r(float(L["reach_m"]) * 100.0, 1), _r(inner), _r(outer), _r(L.get("flicker", 0.0))]
    an = L.get("anim") or {}
    f += [_r(an.get("period_s", 0.0)), _r(an.get("amount", 0.0)), _r(an.get("phase", 0.0))]
    flags = (shape | (4 if L.get("shadow") else 0) | (8 if L.get("tier") == "near" else 0)
             | (16 if L.get("on", True) else 0)
             | (32 if float(L.get("specular", 1.0)) < 0.5 else 0)
             | (64 if L.get("tier") == "high" else 0)
             | (schedules.index(L["schedule"]) << 8)
             | (kinds.index(L["kind"]) << 16) | (mounts.index(L.get("mount", "prop")) << 24)
             | (ANIMS.get(an.get("mode"), 0) << 28))
    seed = int(L["hash"][:8], 16)
    if seed >= 2 ** 31:
        seed -= 2 ** 32
    return f, [flags, seed]


def pack_volume(V: dict, schedules: list[str]):
    """AT4: a fog volume as the cell actor holds it (CityGenAtmosCell.h): VFLOATS floats in
    Unreal's frame (its middle in cm, its yaw, its half sizes in cm, density (1/m), floor
    share, phase g, albedo r, g, b, glow) and VINTS ints (flags: schedule index, kind index << 8)."""
    x, y, z = V["center"]
    ex, ey, ez = V["extent"]
    a = V["albedo"]
    f = [_r(x * 100.0, 1), _r(-y * 100.0, 1), _r(z * 100.0, 1), _r(-V.get("yaw_deg", 0.0)),
         _r(ex * 100.0, 1), _r(ey * 100.0, 1), _r(ez * 100.0, 1), _r(V["density"], 5),
         _r(V.get("floor", 0.0)), _r(V.get("phase_g", 0.4)), _r(a[0], 4), _r(a[1], 4),
         _r(a[2], 4), _r(V.get("glow", 0.0))]
    return f, [schedules.index(V["schedule"]) | (VOLUME_KINDS.index(V["kind"]) << 8)]


def pack_emitter(E: dict, schedules: list[str]):
    """AT4: a steam or smoke plume as the cell actor holds it: EFLOATS floats (its foot in
    cm, its width and rise in cm, its opacity, its albedo r, g, b) and EINTS ints (flags:
    schedule index, kind index << 8, mount index << 16; a seed from its record's hash)."""
    x, y, z = E["pos"]
    c = E.get("color") or [0.8, 0.8, 0.8]
    f = [_r(x * 100.0, 1), _r(-y * 100.0, 1), _r(z * 100.0, 1),
         _r(float(E.get("width_m", 1.0)) * 100.0, 1), _r(float(E.get("rise_m", 5.0)) * 100.0, 1),
         _r(E["rate"]), _r(c[0], 4), _r(c[1], 4), _r(c[2], 4)]
    flags = (schedules.index(E["schedule"]) | (EMITTER_KINDS.index(E["kind"]) << 8)
             | (EMITTER_MOUNTS.index(E.get("mount", "manhole")) << 16))
    seed = int(E["hash"][:8], 16)
    if seed >= 2 ** 31:
        seed -= 2 ** 32
    return f, [flags, seed]


def pack_drip(D: dict) -> list[float]:
    """AT5: a drip line as the cell actor holds it (CityGenAtmosCell.h): DFLOATS floats in
    Unreal's frame (its ends' x and y in cm, its edge's and the ground's z in cm, its rate
    times 8 plus its kind's index)."""
    (ax, ay), (bx, by) = D["a"], D["b"]
    return [_r(ax * 100.0, 1), _r(-ay * 100.0, 1), _r(bx * 100.0, 1), _r(-by * 100.0, 1),
            _r(D["z_m"] * 100.0, 1), _r(D["ground_m"] * 100.0, 1),
            _r(round(float(D["rate"]), 3) + 8.0 * DRIP_KINDS.index(D["kind"]), 3)]


def pack_far(C: dict, schedules: list[str]):
    """AT7: a far card as the cell actor holds it (CityGenAtmosCell.h): FFLOATS floats in
    Unreal's frame (its middle in cm; its color times its value: a glow's intensity in cd, a
    pool's or wash's luminance at its middle in cd/m2, the plan's frame; its size in cm: a
    glow's near, a pool's radius, a wash's half width; a pool's falloff or a wash's half
    height in cm; a wash's yaw in Unreal's frame; a blink's period, on share and phase) and an
    int (flags: type, tier << 2, blinking << 4, schedule index << 8)."""
    x, y, z = C["pos"]
    v = float(C["value"])
    col = C["color"]
    an = C.get("anim") or {}
    blink = an.get("mode") == "blink" and float(an.get("period_s", 0.0)) > 0.0
    f = [_r(x * 100.0, 1), _r(-y * 100.0, 1), _r(z * 100.0, 1),
         _r(col[0] * v, 4), _r(col[1] * v, 4), _r(col[2] * v, 4),
         _r(float(C["size_m"]) * 100.0, 1), _r(float(C.get("h_m") or 0.0) * 100.0, 1),
         _r(-float(C.get("yaw") or 0.0)),
         _r(an.get("period_s", 0.0) if blink else 0.0),
         _r(an.get("amount", 1.0) if blink else 1.0),
         _r(an.get("phase", 0.0) if blink else 0.0)]
    flags = (FAR_TYPES.index(C["type"]) | (FAR_TIERS.index(C["tier"]) << 2)
             | ((16 if blink else 0)) | (schedules.index(C["schedule"]) << 8))
    return f, flags


def far_settings(plan: dict) -> dict:
    """AT7: the controller's far city from the plan's `far` (a plan before AT7 has none: {}):
    the cards' gain, their least width on screen and the share of each live range they fade
    in over."""
    f = plan.get("far")
    if not f:
        return {}
    return {"far": True, "far_gain": float(f["gain"]), "far_px": float(f["px"]),
            "far_fade": float(f["fade"]), "far_spread": float(f["spread"]),
            "far_cards": int((f.get("counts") or {}).get("all", 0))}


def weather_settings(plan: dict) -> dict:
    """AT5: the controller's weather from the plan's `weather_plan` (a plan before AT5 has
    none: {}): the states' values (`WEATHER_KEYS` per state), the start state, the rain's age,
    the wind, the cover channel's datum and step (cm), what it keeps near the view."""
    w = plan.get("weather_plan")
    if not w:
        return {}
    names = list(w["states"])
    vals = []
    for n in names:
        s = w["states"][n]
        a = s["fog_albedo"]
        row = dict(s, fog_albedo_r=a[0], fog_albedo_g=a[1], fog_albedo_b=a[2])
        vals += [float(row[k]) for k in WEATHER_KEYS]
    t, wd, lv = w["times"], w["wind"], w["live"]
    return {"weather": True, "weather_names": names, "weather_values": vals,
            "weather_start": w["start"], "weather_keys": list(WEATHER_KEYS),
            "transition_s": float(t["transition_s"]), "wet_s": float(t["wet_s"]),
            "dry_s": float(t["dry_s"]), "fill_s": float(t["fill_s"]),
            "drain_s": float(t["drain_s"]), "wind_heading_deg": float(wd["heading_deg"]),
            "rain_lean": float(wd["lean"]), "gale_m_s": float(wd["gale_m_s"]),
            "cover_z0_cm": _r(float(w["cover"]["z0_m"]) * 100.0, 1),
            "cover_step_cm": _r(float(w["cover"]["step_m"]) * 100.0, 1),
            "max_splashes": int(lv["splashes"]), "splash_range_m": float(lv["splash_m"]),
            "max_drips": int(lv["drips"]), "drip_range_m": float(lv["drip_m"]),
            "drip_step_m": float(lv["drip_step_m"]), "rain_cards": int(lv["rain_cards"])}


def wet_textures(plan: dict, pdir: Path, dest: Path) -> dict | None:
    """AT5: the plan's masks stitched into two city-wide images at `WET_TEXEL_M` (a power of
    two a side, so the texture has its mips; row 0 the north edge): `atmos_wet_cover.png`
    (grey: the cover channel, the lowest of a texel's covered masks' undersides, 0 where
    fewer than two of its four are covered) and `atmos_wet_surface.png` (red the gloss, green
    the puddles, their means; blue the drips, their most), written beside the manifest only
    when their bytes change. Their bounds in Unreal's frame (cm: min X, min Y, size; row 0 the
    minimum Y, the north edge). None without masks."""
    import io

    import numpy as np
    from PIL import Image
    w = plan.get("weather_plan")
    masks = plan.get("masks") or []
    if not w or not masks:
        return None
    t = float(w["texel_m"])
    k = max(1, int(round(WET_TEXEL_M / t)))
    x0, y0, x1, y1 = (float(v) for v in w["extent"])
    span = max(x1 - x0, y1 - y0)
    n = 1
    while n * WET_TEXEL_M < span:
        n *= 2
    cover = np.zeros((n, n), dtype=np.uint8)
    surf = np.zeros((n, n, 3), dtype=np.uint8)
    top = y0 + n * WET_TEXEL_M
    for mk in masks:
        name = mk["tile"]
        ix, iy = int(name[1:4]), int(name[4:7])
        with Image.open(pdir / mk["file"]) as im:
            a = np.asarray(im.convert("RGBA"), dtype=np.uint8)
        h, wd = a.shape[0] // k, a.shape[1] // k
        b = a[:h * k, :wd * k].reshape(h, k, wd, k, 4)
        c = b[..., 0].astype(np.int32)
        cov = c > 0
        many = cov.sum(axis=(1, 3)) >= (k * k + 1) // 2
        low = np.where(cov, c, 999).min(axis=(1, 3))
        cq = np.where(many, low, 0).astype(np.uint8)
        gl = b[..., 3].astype(np.float64).mean(axis=(1, 3))
        pu = b[..., 1].astype(np.float64).mean(axis=(1, 3))
        dr = b[..., 2].max(axis=(1, 3))
        ci = int(round((ix * 256.0 - x0) / WET_TEXEL_M))
        cj = int(round((top - (iy + 1) * 256.0) / WET_TEXEL_M))
        cover[cj:cj + h, ci:ci + wd] = cq
        surf[cj:cj + h, ci:ci + wd, 0] = np.round(gl).astype(np.uint8)
        surf[cj:cj + h, ci:ci + wd, 1] = np.round(pu).astype(np.uint8)
        surf[cj:cj + h, ci:ci + wd, 2] = dr
    out = {}
    dest.mkdir(parents=True, exist_ok=True)
    for fname, arr, mode in ((WET_COVER, cover, "L"), (WET_SURFACE, surf, "RGB")):
        buf = io.BytesIO()
        Image.fromarray(np.ascontiguousarray(arr), mode).save(buf, format="PNG",
                                                             compress_level=9)
        data = buf.getvalue()
        f = dest / fname
        if not f.is_file() or f.read_bytes() != data:
            f.write_bytes(data)
        out[fname] = hashlib.sha256(data).hexdigest()
    return {"cover": {"file": f"unreal/{WET_COVER}", "sha256": out[WET_COVER]},
            "surface": {"file": f"unreal/{WET_SURFACE}", "sha256": out[WET_SURFACE]},
            "px": n, "texel_m": WET_TEXEL_M,
            "bounds": [_r(x0 * 100.0, 1), _r(-top * 100.0, 1), _r(n * WET_TEXEL_M * 100.0, 1)]}


def air_settings(plan: dict) -> dict:
    """AT4: the controller's air from the plan's `air` (an AT3 plan has none: {}): the height
    and volumetric fog of the look and weather (over the weather's own), the fog by the hour,
    each light kind's volumetric scattering (light shafts), the searchlight beams' fog gain,
    the live sets, the engine settings it runs with."""
    a = plan.get("air")
    if not a:
        return {}
    kinds = _kinds()
    return {"air": True, "fog_density": float(a["fog_density"]),
            "fog_falloff": float(a["fog_falloff"]), "fog_start_m": float(a["fog_start_m"]),
            "fog_albedo_linear": [float(v) for v in a["fog_albedo"]],
            "fog_volumetric": float(a["fog_extinction"]), "fog_view_m": float(a["fog_view_m"]),
            "fog_phase_g": float(a["phase_g"]),
            "fog_hours": [float(v) for v in a["fog_hours"]],
            "kind_scatter": [float(a["scatter"].get(k, 1.0)) for k in kinds],
            "beam_fog_gain": float(a["beam_fog_gain"]),
            "max_volumes": int(a["max_volumes"]), "volume_range_m": float(a["volume_range_m"]),
            "emitter_range_m": float(a["emitter_range_m"]),
            "emitter_kinds": list(EMITTER_KINDS),
            "puffs": [int(a["puffs"].get(k, 4)) for k in EMITTER_KINDS],
            "steam_gain": float(a.get("steam_gain", 10.0)),
            "volume_glow": float(a.get("volume_glow", 0.15)),
            # (AT6: the plumes by night and far off)
            "steam_glow": float(a.get("steam_glow", 0.0)),
            "steam_far": [float(v) for v in a.get("steam_far", [0.0, 150.0])],
            "cvars": [f"{k}={v}" for k, v in sorted(a.get("cvars", {}).items())],
            "volumes": len(plan.get("volumes") or []),
            "emitters": len(plan.get("emitters") or [])}


def sight_settings(plan: dict, pdir: Path) -> dict:
    """Visible lights: the controller's sight from the plan's `sight` (a plan before it has
    none: {}): the raster as runs over its rows from the north edge ([count, red | green << 8
    | blue << 16] pairs, `atmosgen.sight.runs`), its bounds in Unreal's frame (cm: [min X,
    min Y, max X, max Y], Y south, so row 0 is min Y), its cell (m), size, steps (top,
    bottom, ground; m), skips (eye, light; m), and the tiers' range and size."""
    s = plan.get("sight")
    if not s or not (pdir / s["file"]).is_file():
        return {}
    import numpy as np
    from PIL import Image

    from atmosgen.sight import runs
    with Image.open(pdir / s["file"]) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = s["bounds"]
    t = plan.get("tiers") or {}
    return {"sight_m": float(t.get("sight_m", 1200.0)),
            "sight_max": int(t.get("sight_max", 512)),
            "sight_bounds": [_r(x0 * 100.0, 1), _r(-y1 * 100.0, 1), _r(x1 * 100.0, 1),
                             _r(-y0 * 100.0, 1)],
            "sight_cell_m": float(s["cell_m"]), "sight_px": [int(w), int(h)],
            "sight_steps": [float(s["top_step_m"]), float(s["bottom_step_m"]),
                            float(s["ground_step_m"])],
            "sight_skips": [float(s["skip_eye_m"]), float(s["skip_light_m"])],
            "sight_sha256": s["sha256"], "sight_runs": runs(rgb)}


def _post_floats(s: dict) -> list[float]:
    return [float(s[k]) for k in POST_FLOATS[:-6]] + \
        [float(v) for v in s["shadows_gain"]] + [float(v) for v in s["highlights_gain"]]


def post_settings(plan: dict, pdir: Path) -> dict:
    """AT6: the controller's look from the plan's `post` (a plan before AT6 has none: {}):
    the look's two sets (`POST_FLOATS` each, the night's then the day's), each district's in
    the raster's order, the district raster as runs over its rows from the north edge
    ([count, index] pairs, `atmosgen.look.runs`) with its bounds in Unreal's frame (cm: [min X,
    min Y, max X, max Y], Y south, so row 0 is min Y), its cell and size, the blend, and the
    exposure (the day's EV100 with its bias, which replaces the sky's; the overcast's
    compensation)."""
    p = plan.get("post")
    if not p:
        return {}
    ex = p["exposure"]
    out = {"post": True, "post_keys": list(POST_FLOATS),
           "post_base": _post_floats(p["base"]["night"]) + _post_floats(p["base"]["day"]),
           "post_names": [p["districts"][d]["name"] or d for d in p.get("order", [])],
           "post_districts": [v for d in p.get("order", [])
                              for w in ("night", "day")
                              for v in _post_floats(p["districts"][d][w])],
           "post_blend_m": float(p["blend_m"]), "post_ease_s": float(p["ease_s"]),
           "day_ev100": float(ex["day_ev100"]), "overcast_comp": float(ex["overcast_comp"]),
           "overcast_take": [float(v) for v in ex["overcast_take"]],
           "sky_share": float(ex["sky_share"]), "ref_cover": float(ex["ref_cover"])}
    r = p.get("raster")
    if r and (pdir / r["file"]).is_file():
        from atmosgen.look import read, runs
        idx = read(pdir, r)
        x0, y0, x1, y1 = r["bounds"]
        out.update({"post_runs": runs(idx), "post_cell_m": float(r["cell_m"]),
                    "post_px": [int(idx.shape[1]), int(idx.shape[0])],
                    "post_bounds": [_r(x0 * 100.0, 1), _r(-y1 * 100.0, 1), _r(x1 * 100.0, 1),
                                    _r(-y0 * 100.0, 1)],
                    "post_sha256": r["sha256"]})
    return out


def cell_of(x: float, y: float) -> tuple[int, int]:
    return int(math.floor(x / CELL_M)), int(math.floor(y / CELL_M))


def cell_name(ix: int, iy: int) -> tuple[str, str]:
    """A 128 m cell's tile (citygen's 256 m tile) and its name `<tile>.<quarter>`."""
    tx, ty = ix // 2, iy // 2
    tile = f"t{tx:+03d}{ty:+03d}"
    return tile, f"{tile}.{QUARTERS[(ix - 2 * tx, iy - 2 * ty)]}"


def _linear(h: str) -> list[float]:
    out = []
    for k in range(3):
        c = int(h[1 + 2 * k:3 + 2 * k], 16) / 255.0
        out.append(_r(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4, 4))
    return out


def sky_settings(plan: dict) -> dict:
    """AT3: the controller's sky and time from the plan's `sky` (an AT2 plan has none: {}).
    The glow's bounds in Unreal's frame (cm: [min X, min Y, max X, max Y], Y south)."""
    s = plan.get("sky") or {}
    if "curve" not in s:
        return {}
    m, cv, g = s["moon"], s["curve"], s.get("glow") or {}
    out = {"latitude_deg": float(s["latitude_deg"]),
           "declination_deg": float(s["declination_deg"]),
           "moon_lag_h": float(m["lag_h"]), "moon_declination_deg": float(m["declination_deg"]),
           "moon_lit": float(m["lit"]), "moon_share": float(m["share"]),
           "moon_color": _linear(m["color"]), "moon_disk_nits": float(m["disk_nits"]),
           "moon_disk_deg": float(m["disk_deg"]), "moon_rise": [float(v) for v in m["rise"]],
           "moon_cloud": float(m["cloud"]), "sun_lux": float(s["sun_lux"]),
           "scene_ev100": float(s["ev_night"]), "day_ev100": float(s["ev_day"]),
           "curve_elev": [float(v) for v in cv["elev"]],
           "curve_ev": [float(v) for v in cv["ev"]],
           "curve_night": [float(v) for v in cv["night"]],
           "curve_sun": [float(v) for v in cv["sun"]],
           "curve_sky": [float(v) for v in cv["sky"]],
           "curve_stars": [float(v) for v in cv["stars"]],
           "stars": float(s["stars"]), "cloud_deck_m": float(s["cloud_deck_m"]),
           "cloud_cover": float(s["cloud_cover"]),
           "day_hour": float(s["hours"]["day"]), "dusk_hour": float(s["hours"]["dusk"]),
           "night_hour": float(s["hours"]["night"])}
    if g:
        x0, y0, x1, y1 = g["bounds"]
        out.update({"glow_bounds": [_r(x0 * 100.0, 1), _r(-y1 * 100.0, 1),
                                    _r(x1 * 100.0, 1), _r(-y0 * 100.0, 1)],
                    "glow_max_nits": float(g["max_nits"]), "glow_sha256": g["sha256"]})
    return out


def undelivered(plan: dict) -> str:
    """Why a plan is not delivered (scope 8: a check of its failed), else ""."""
    ck = plan.get("checks") or {}
    lux = ck.get("lux")
    if lux is None:
        return "the plan has no lux check (an AT0 plan: run atmosgen plan again)"
    if not lux.get("ok"):
        return "the plan's lux check failed (scope 8: not delivered)"
    why = {"faces": "the plan's faces check failed (AT2: a lit face floods its wall)",
           "air": "the plan's air check failed (AT4: an emitter off its source, a volume off "
                  "its water or district, or a tile over its budget)",
           "weather": "the plan's weather check failed (AT5: a cover out of its rain shadow, "
                      "a puddle under a cover, in a building or on the water, a tile without "
                      "its mask or over its drips' budget)",
           "far": "the plan's far check failed (AT7: a lamp without its far card, a card with "
                  "bad numbers, or a tile over its budget)",
           "fixtures": "the plan's fixtures check failed (dlss_lamps_flicker: a light standing "
                       "on nothing, or a fixture on a carriageway)"}
    for k, msg in why.items():
        c = ck.get(k)
        if c is not None and not c.get("ok"):
            return msg
    return ""


def fixtures_contribution(build: str | Path, given: str | Path | None = None):
    """dlss_lamps_flicker: the fixtures under the plan's asked lights (AG8's own variants,
    the plan's `unreal_contribution.fixtures.json`, atmosgen/fixtures.py) as one more of stage
    2's contributions: (its path, the contribution, its sha256), where the plan is delivered;
    else None."""
    pdir = plan_dir(build, given)
    if pdir is None or not (pdir / FIXTURES).is_file():
        return None
    if undelivered(json.loads((pdir / "atmos_plan.json").read_text(encoding="utf-8"))):
        return None
    data = (pdir / FIXTURES).read_bytes()
    c = json.loads(data)
    if c.get("version") != 1 or not c.get("entries"):
        return None
    return ((pdir / FIXTURES).as_posix(), c, hashlib.sha256(data).hexdigest())


def atmos_data(pdir: Path, dest: Path | None = None) -> tuple[dict | None, str]:
    """The plan in the importer's form ({controller, cells}), or (None, why not). AT5: with
    `dest` (BUILD/unreal) the weather's textures are written there (`wet_textures`) and named
    in the controller."""
    text = (pdir / "atmos_plan.json").read_text(encoding="utf-8")
    plan = json.loads(text)
    why = undelivered(plan)
    if why:
        return None, why
    schedules = sorted(plan["schedules"])
    kinds, mounts = _kinds(), _mounts()
    cells: dict[tuple[int, int], list[dict]] = {}
    vols: dict[tuple[int, int], list[dict]] = {}
    emits: dict[tuple[int, int], list[dict]] = {}
    for t in plan["tiles"]:
        for L in json.loads((pdir / t["file"]).read_text(encoding="utf-8"))["lights"]:
            cells.setdefault(cell_of(L["pos"][0], L["pos"][1]), []).append(L)
    # AT4: a cell's fog volumes (by their middle) and emitters (by their foot)
    for V in plan.get("volumes") or []:
        vols.setdefault(cell_of(V["center"][0], V["center"][1]), []).append(V)
    for E in plan.get("emitters") or []:
        emits.setdefault(cell_of(E["pos"][0], E["pos"][1]), []).append(E)
    # AT5: a cell's drip lines (by their middle)
    drips: dict[tuple[int, int], list[dict]] = {}
    for dt in ((plan.get("weather_plan") or {}).get("drip_tiles") or []):
        if not (pdir / dt["file"]).is_file():
            continue
        for D in json.loads((pdir / dt["file"]).read_text(encoding="utf-8"))["drips"]:
            mx = (D["a"][0] + D["b"][0]) / 2.0
            my = (D["a"][1] + D["b"][1]) / 2.0
            drips.setdefault(cell_of(mx, my), []).append(D)
    # AT7: a cell's far cards (by their middle)
    fars: dict[tuple[int, int], list[dict]] = {}
    for ft in ((plan.get("far") or {}).get("tiles") or []):
        if not (pdir / ft["file"]).is_file():
            continue
        for C in json.loads((pdir / ft["file"]).read_text(encoding="utf-8"))["cards"]:
            fars.setdefault(cell_of(C["pos"][0], C["pos"][1]), []).append(C)
    out = []
    for (ix, iy) in sorted(set(cells) | set(vols) | set(emits) | set(drips) | set(fars)):
        ls = sorted(cells.get((ix, iy), []), key=lambda r: r["id"])
        vs = sorted(vols.get((ix, iy), []), key=lambda r: r["id"])
        es = sorted(emits.get((ix, iy), []), key=lambda r: r["id"])
        ds = sorted(drips.get((ix, iy), []), key=lambda r: r["id"])
        fs = sorted(fars.get((ix, iy), []), key=lambda r: r["id"])
        fl, it = [], []
        for L in ls:
            f, i = pack(L, schedules, kinds, mounts)
            fl += f
            it += i
        vf, vi, ef, ei = [], [], [], []
        for V in vs:
            f, i = pack_volume(V, schedules)
            vf += f
            vi += i
        for E in es:
            f, i = pack_emitter(E, schedules)
            ef += f
            ei += i
        tile, name = cell_name(ix, iy)
        rec = {"key": f"atmos.lights.{name}", "cell": name, "tile": tile,
               "center": [(ix + 0.5) * CELL_M, (iy + 0.5) * CELL_M, 0.0],
               "count": len(ls),
               "hash": _sha16([PACK_VERSION, [L["hash"] for L in ls]] +
                              ([[V["hash"] for V in vs], [E["hash"] for E in es]]
                               if vs or es else []) +
                              ([[D["hash"] for D in ds]] if ds else []) +
                              ([["far"] + [C["hash"] for C in fs]] if fs else [])),
               "floats": fl, "ints": it}
        if vs or es:
            rec.update({"volumes": len(vs), "emitters": len(es), "volume_floats": vf,
                        "volume_ints": vi, "emitter_floats": ef, "emitter_ints": ei})
        if ds:
            rec.update({"drips": len(ds), "drip_floats": [v for D in ds for v in pack_drip(D)]})
        if fs:
            ff, fi = [], []
            for C in fs:
                f, i = pack_far(C, schedules)
                ff += f
                fi.append(i)
            rec.update({"far": len(fs), "far_floats": ff, "far_ints": fi})
        out.append(rec)
    ws = plan.get("weather_state") or {}
    tiers = plan.get("tiers") or {}
    ctl = {"city": plan["city"], "plan_hash": hashlib.sha256(text.encode("utf-8"))
           .hexdigest()[:16], "schedule_names": schedules,
           "schedule_hours": [float(v) for s in schedules for v in plan["schedules"][s]],
           "kind_names": kinds, "plan_ev100": float(plan.get("night_ev100", 3.0)),
           "hour": float(plan.get("hour", 23.0)),
           "fog_density": float(ws.get("fog_density", 0.018)),
           "fog_falloff": float(ws.get("fog_falloff", 0.08)),
           "fog_volumetric": float(ws.get("volumetric", 1.0)),
           "fog_albedo": ws.get("fog_albedo", "#8a97ad"),
           "rain_rate": float(ws.get("rain", 0.8)), "wind_ms": float(ws.get("wind_m_s", 6.0)),
           "max_live": int(tiers.get("mid_max", 512)),
           "mid_range_m": float(tiers.get("mid_m", 300.0)),
           "max_shadowed": int(tiers.get("near_max", 16)),
           "near_range_m": float(tiers.get("near_m", 60.0)),
           "max_high": int(tiers.get("high_max", 0)),
           "high_range_m": float(tiers.get("high_m", 750.0)), "cell_m": CELL_M}
    ctl.update(sky_settings(plan))
    ctl.update(air_settings(plan))
    ctl.update(sight_settings(plan, pdir))
    ctl.update(weather_settings(plan))
    ctl.update(post_settings(plan, pdir))
    ctl.update(far_settings(plan))
    if dest is not None and ctl.get("weather"):
        wt = wet_textures(plan, pdir, dest)
        if wt:
            ctl.update({"wet_bounds": wt["bounds"], "wet_px": wt["px"],
                        "wet_cover_sha256": wt["cover"]["sha256"],
                        "wet_surface_sha256": wt["surface"]["sha256"]})
    return {"version": PACK_VERSION, "controller": ctl, "cells": out}, ""


def write_atmos(build: str | Path, given: str | Path | None = None) -> dict | None:
    """The manifest's `atmos` (and BUILD/unreal/atmos.json, written only when its bytes
    change); None without a plan, {"skipped": why} for a plan not delivered."""
    pdir = plan_dir(build, given)
    if pdir is None:
        if given:
            raise FileNotFoundError(f"{given}: no atmos_plan.json (run atmosgen plan)")
        return None
    data, why = atmos_data(pdir, Path(build) / "unreal")
    if data is None:
        return {"skipped": why, "plan": str(pdir)}
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n"
    dest = Path(build) / "unreal" / DATA
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.is_file() or dest.read_text(encoding="utf-8") != text:
        dest.write_text(text, encoding="utf-8", newline="\n")
    ctl = data["controller"]
    # AT3: the deck's glow beside the manifest (the import makes it a texture)
    glow = None
    plan_sky = json.loads((pdir / "atmos_plan.json").read_text(encoding="utf-8")).get("sky") or {}
    g = plan_sky.get("glow")
    gdest = Path(build) / "unreal" / GLOW
    if g and (pdir / g["file"]).is_file():
        b = (pdir / g["file"]).read_bytes()
        if not gdest.is_file() or gdest.read_bytes() != b:
            gdest.write_bytes(b)
        glow = {"file": f"unreal/{GLOW}", "sha256": hashlib.sha256(b).hexdigest()}
    elif gdest.is_file():
        gdest.unlink()
    return {"file": f"unreal/{DATA}", "plan": str(pdir), "plan_hash": ctl["plan_hash"],
            "key": CONTROLLER_KEY, "hash": _sha16([PACK_VERSION, ctl]), "glow": glow,
            "lights": sum(c["count"] for c in data["cells"]),
            "volumes": sum(c.get("volumes", 0) for c in data["cells"]),
            "emitters": sum(c.get("emitters", 0) for c in data["cells"]),
            "sight": ({"px": ctl["sight_px"], "cell_m": ctl["sight_cell_m"],
                       "runs": len(ctl["sight_runs"]) // 2, "sha256": ctl["sight_sha256"]}
                      if ctl.get("sight_runs") is not None else None),
            # AT5: the weather's states and textures, the drip lines
            "weather": ({"states": ctl["weather_names"], "start": ctl["weather_start"],
                         "drips": sum(c.get("drips", 0) for c in data["cells"]),
                         "wet": ({"cover": {"file": f"unreal/{WET_COVER}",
                                            "sha256": ctl["wet_cover_sha256"]},
                                  "surface": {"file": f"unreal/{WET_SURFACE}",
                                              "sha256": ctl["wet_surface_sha256"]},
                                  "px": ctl["wet_px"], "bounds": ctl["wet_bounds"]}
                                 if ctl.get("wet_px") else None)}
                        if ctl.get("weather") else None),
            # AT6: the look's post, its districts and their raster
            "post": ({"districts": len(ctl["post_names"]),
                      "raster": ({"px": ctl["post_px"], "cell_m": ctl["post_cell_m"],
                                  "sha256": ctl["post_sha256"]}
                                 if ctl.get("post_runs") is not None else None)}
                     if ctl.get("post") else None),
            # AT7: the far city's cards
            "far": ({"cards": sum(c.get("far", 0) for c in data["cells"]),
                     "gain": ctl["far_gain"], "px": ctl["far_px"]}
                    if ctl.get("far") else None),
            "cells": [{k: c[k] for k in ("key", "cell", "tile", "center", "count", "hash")}
                      for c in data["cells"]]}


def actor_hashes(atmos: dict | None) -> dict[str, str]:
    """The controller's and every cell actor's key and hash (`unreal.actor_hashes`)."""
    if not atmos or not atmos.get("cells"):
        return {}
    out = {atmos["key"]: atmos["hash"]}
    out.update({c["key"]: c["hash"] for c in atmos["cells"]})
    return out
