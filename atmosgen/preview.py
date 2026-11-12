"""`atmosgen preview BUILD`: a Blender night preview lit by the atmos plan (scope 9).

The scene is AG15's night preview (`assetgen materials preview --night`: the blockout's
city.blend with stage 2's shells, fronts, parts, streets, water, ground cover, props and
signs, AG6's materials with AG15's night rooms at the hour), its stopgap lamps and sign
washes replaced by the plan's lights near each view: spot and point lights at the lamp
heads, rect (area) lights on the sign faces and shopfronts, each in its color and by its
schedule at the hour, broken ones dark. Rendered in Cycles (its light tree takes the
thousands of lights), with the weather's haze as a volume round the view and the streets
wet (glossier, darker where they face up) by the plan's weather. Light units: a candela
is 4 pi / 683 W of a Blender point or spot (Blender gives a spot the power of the point
light it is cut from), a nit pi A / 683 W of an area light, times one `gain` for the
preview's exposure.
"""

from __future__ import annotations

import json
import math
from argparse import Namespace
from pathlib import Path

# W per candela of a Blender point or spot light, and per nit and m2 of an area light
CD_W = 4.0 * math.pi / 683.0
NIT_W = math.pi / 683.0
GAIN = 8.0             # the preview's exposure (set by eye against AG15's night materials)
NEAR_ONLY_M = 140.0    # near-tier lights (shop signs) within this of a view's eye


def _lights_near(plan_dir: Path, plan: dict, center, r: float, eye, hour: float) -> list[dict]:
    """The plan's lights within `r` of `center` (near-tier ones within NEAR_ONLY_M of `eye`),
    as Blender lights: kind, position, aim, size, power (W), color; dark by their schedule
    at `hour` or broken left out."""
    sched = plan["schedules"]
    h = int(math.floor(hour)) % 24
    out = []
    for t in plan["tiles"]:
        ix, iy = int(t["tile"][1:4]), int(t["tile"][4:7])
        x0, y0 = ix * 256.0, iy * 256.0
        dx = max(x0 - center[0], 0.0, center[0] - x0 - 256.0)
        dy = max(y0 - center[1], 0.0, center[1] - y0 - 256.0)
        if dx * dx + dy * dy > r * r:
            continue
        doc = json.loads((plan_dir / t["file"]).read_text(encoding="utf-8"))
        for L in doc["lights"]:
            if not L["on"]:
                continue
            # (AT3: between one hour's value and the next, as the runtime)
            s = sched.get(L["schedule"], [1.0] * 24)
            f = hour % 24.0 - h
            k = s[h] + (s[(h + 1) % 24] - s[h]) * f
            if k < 0.05:
                continue
            p = L["pos"]
            d = math.dist(p[:2], center[:2])
            if d > r or (L["tier"] == "near" and math.dist(p, eye) > NEAR_ONLY_M):
                continue
            if L["shape"] == "rect":
                w, hh = L["size"]
                watts = L["cd"] / max(w * hh, 0.01) * NIT_W * w * hh
            else:
                watts = L["cd"] * CD_W
            out.append({"shape": L["shape"], "pos": p, "aim": L["aim"],
                        "size": L.get("size"), "cone": L.get("cone"),
                        "radius": L.get("source_m", 0.1),
                        "watts": round(watts * k * GAIN, 3), "color": L["color"]})
    out.sort(key=lambda q: (math.dist(q["pos"], eye), q["pos"]))
    return out


def run(args) -> dict:
    from assetgen.materials import preview as MP
    from assetgen.materials.preview import _blender
    build = Path(args.build)
    plan_dir = Path(args.plan) if args.plan else build / "atmos"
    plan = json.loads((plan_dir / "atmos_plan.json").read_text(encoding="utf-8"))
    out = Path(args.out) if args.out else plan_dir / "previews"
    hour = plan["hour"] if args.hour is None else args.hour
    ns = Namespace(build=str(build), out=str(out), blockout=None, views=args.views,
                   width=args.width, eye=args.eye, target=args.target, lens=args.lens,
                   night=True, only_night=True, samples=args.samples, hour=hour,
                   blender=args.blender)
    job, od, n = MP.make_job(ns)
    w = plan["weather_state"]
    job["engine"] = args.engine
    job["fog"] = w["fog_density"] * 0.12 if args.fog is None else args.fog
    job["fog_color"] = w["fog_albedo"]
    job["wet"] = w["wetness"] if args.wet is None else args.wet
    job["exposure"] = 0.0
    # AT3: at an hour the sun is near the horizon, a twilight sky (`dusk` in the job, drawn by
    # ag6_preview's `dusk_world`), the windows and signs at the plan's Night there and the
    # plan's lights dimmed by the exposure's step up from the night's (as in the game: the
    # lights keep their physical output, the scene is exposed brighter)
    dim = 1.0
    sky = plan.get("sky") or {}
    if "curve" in sky:
        from . import sky as SK
        e, az, _ = SK.sun_at(sky, hour)
        if e > -12.0:
            dim = 2.0 ** -(SK.exposure(sky, e) - sky["ev_night"])
            job["dusk"] = {"sun_elev": round(e, 3), "sun_az": round(az, 3),
                           "night": round(SK.curve("night", e, sky["curve"]), 3),
                           "sky": round(SK.curve("sky", e, sky["curve"]), 3)}
    total = 0
    for v in job["views"]:
        center = v["target"] if v.get("far") else v["eye"]
        v["atmos_lights"] = _lights_near(plan_dir, plan, center, args.radius, v["eye"], hour)
        for L in v["atmos_lights"]:
            L["watts"] = round(L["watts"] * dim, 3)
        v["lights"], v["washes"] = [], []
        total += len(v["atmos_lights"])
    rep = _blender(job, "ag6_preview.py", args.blender, od, None, n)
    rep["out"] = str(od)
    rep["atmos_lights"] = total
    (od / "atmos_preview.json").write_text(json.dumps(
        {"plan": str(plan_dir), "hour": hour, "engine": args.engine, "fog": job["fog"],
         "wet": job["wet"], "gain": GAIN, "dusk": job.get("dusk"), "dim": round(dim, 4),
         "views": [{"name": v["name"], "lights": len(v["atmos_lights"])}
                   for v in job["views"]]}, indent=1) + "\n", encoding="utf-8")
    return rep
