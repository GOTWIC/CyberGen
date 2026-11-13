"""atmosgen's command line (`python -m atmosgen ...`):

    atmosgen spec validate SPEC [--build BUILD]     the atmos spec, against a built city
    atmosgen spec schema [OUT]                      its JSON schema
    atmosgen plan schema [--which W] [OUT]          the plan's schemas
    atmosgen plan BUILD [--spec S] [--out DIR]      the atmos plan (BUILD/atmos) and its lux
                                                    check (exit 1 when it fails: the plan is
                                                    not delivered)
    atmosgen lux BUILD [--plan DIR]                 the lux map of the core (preview_lux.png),
                                                    the plan's map (preview_plan.png), the sky
                                                    (preview_sky.png), the air (AT4,
                                                    preview_air.png) and the weather (AT5,
                                                    preview_weather.png)
    atmosgen preview BUILD [--plan DIR] ...         a Blender night preview from the plan
    atmosgen review BUILD [--spec S] [--prev P] [--shots DIR] [--prev-shots DIR]
                                                    AT6: an art-direction round's review.md
                                                    (checks, numbers, previews, shots)
    atmosgen spec diff A B                          AT6: what two atmos specs differ in
    atmosgen budgets PLAN... --out DIR              AT7: the plans' budgets across cities
                                                    (budgets.md, budgets.json)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _write_json(data: dict, out: str | None) -> None:
    text = json.dumps(data, indent=1, sort_keys=True) + "\n"
    if out:
        Path(out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {out}")
    else:
        sys.stdout.write(text)


def cmd_spec(args) -> int:
    from . import spec as S
    if args.spec_cmd == "diff":
        from .review import spec_diff
        a = json.loads(Path(args.a).read_text(encoding="utf-8"))
        b = json.loads(Path(args.b).read_text(encoding="utf-8"))
        for line in spec_diff(a, b) or ["(no differences)"]:
            print(line)
        return 0
    if args.spec_cmd == "schema":
        _write_json(S.json_schema(), args.out)
        return 0
    model = None
    if args.build:
        model = json.loads((Path(args.build) / "city_model.json").read_text(encoding="utf-8"))
    res = S.load_spec(args.spec, model)
    for i in res.issues:
        print(i)
    if not res.ok:
        return 1
    if args.filled and model is not None:
        _write_json(S.fill(res.spec, model.get("districts", [])), args.filled)
    print("ok")
    return 0


def cmd_plan(args) -> int:
    from . import planmodel as PM
    if args.build == "schema":
        model, title = PM.SCHEMAS[args.which]
        _write_json(PM.json_schema(model, title), args.out)
        return 0
    from .plan import build_plan, report_text
    rep = build_plan(args.build, args.spec, args.out)
    sys.stdout.write(report_text(rep))
    print(f"{len(rep['wrote'])} files written to {rep['out']} in {rep['seconds']} s")
    if not rep["ok"]:
        print("FAIL: a check failed (lux, faces, air, weather or far); the plan is not "
              "delivered (the exporter leaves it out)", file=sys.stderr)
        return 1
    return 0


def cmd_lux(args) -> int:
    from .lux import lux_preview, plan_map
    rep = lux_preview(args.build, args.plan, args.out, size_m=args.size, cell_m=args.cell,
                      hour=args.hour)
    rep["plan_map"] = plan_map(args.build, args.plan)["image"]
    # AT3: the deck's glow over the city and the sun, the moon and the exposure by the hour
    from pathlib import Path

    from .sky import preview as sky_preview
    pdir = Path(args.plan) if args.plan else Path(args.build) / "atmos"
    rep["sky"] = sky_preview(json.loads((pdir / "atmos_plan.json").read_text(encoding="utf-8")),
                             pdir, json.loads((Path(args.build) / "city_model.json")
                                              .read_text(encoding="utf-8")))["image"]
    # AT4: the air's volumes and emitters over the city
    from .air import air_map
    rep["air"] = air_map(args.build, args.plan)["image"]
    # AT5: the weather's masks over the city and its busiest tile up close
    from .weather import preview as weather_preview
    pl = json.loads((pdir / "atmos_plan.json").read_text(encoding="utf-8"))
    if pl.get("weather_plan"):
        rep["weather"] = weather_preview(pdir, pl)
    # AT6: the districts' post and every district's grade on a test chart
    if pl.get("post"):
        from .look import preview as post_preview
        rep["post"] = post_preview(pl, pdir, json.loads(
            (Path(args.build) / "city_model.json").read_text(encoding="utf-8")))["image"]
    # AT7: the far city's cards from above and from 150 m over its corner
    if pl.get("far"):
        from .far import preview as far_preview
        rep["far"] = far_preview(pdir, pl, json.loads(
            (Path(args.build) / "city_model.json").read_text(encoding="utf-8")))["image"]
    print(json.dumps({k: v for k, v in rep.items() if k != "grid"}, indent=1))
    return 0


def cmd_review(args) -> int:
    from .review import review
    rec = review(args.build, args.spec, args.prev, plan=args.plan, shots=args.shots,
                 prev_shots=args.prev_shots)
    print(f"round {rec['round']}: {'checks passed' if rec['passed'] else 'checks failed'}; "
          f"wrote {rec['out']}")
    return 0


def cmd_preview(args) -> int:
    from .preview import run
    rep = run(args)
    print(f"rendered {len(rep.get('files', []))} images to {rep.get('out')}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="atmosgen", description="CyberGen stage 3: light, sky, "
                                                              "air and weather")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("spec", help="the atmos spec")
    ss = sp.add_subparsers(dest="spec_cmd", required=True)
    v = ss.add_parser("validate")
    v.add_argument("spec")
    v.add_argument("--build", help="a built city (its districts' and landmarks' names)")
    v.add_argument("--filled", help="write the spec resolved for the city here")
    s = ss.add_parser("schema")
    s.add_argument("out", nargs="?")
    df = ss.add_parser("diff", help="AT6: the parameters two atmos specs differ in")
    df.add_argument("a")
    df.add_argument("b")
    rv = sub.add_parser("review", help="AT6: an art-direction round's review sheet "
                                       "(review.md) from the plan, its previews and shots")
    rv.add_argument("build")
    rv.add_argument("--plan", help="the plan's folder (default BUILD/atmos)")
    rv.add_argument("--spec", help="the round's atmos spec (copied beside the review)")
    rv.add_argument("--prev", help="the previous round's plan folder (its review.json)")
    rv.add_argument("--shots", help="a folder of the round's Unreal shots (`citygen unreal "
                                    "--check --shots`)")
    rv.add_argument("--prev-shots", help="the previous round's shots, side by side")
    pp = sub.add_parser("plan", help="the atmos plan of a built city (or `plan schema`)")
    pp.add_argument("build", help="the build folder, or `schema`")
    pp.add_argument("out_schema", nargs="?", help=argparse.SUPPRESS)
    pp.add_argument("--spec", help="atmos_spec.json (default: every default)")
    pp.add_argument("--out", help="the plan's folder (default BUILD/atmos; with `schema` the "
                                  "file)")
    pp.add_argument("--which", default="atmos_plan",
                    choices=("atmos_plan", "tile_lights", "tile_drips", "tile_far",
                             "contribution"))
    lx = sub.add_parser("lux", help="the plan's lux map round the corporate core, with "
                                    "occlusion")
    lx.add_argument("build")
    lx.add_argument("--plan", help="the plan's folder (default BUILD/atmos)")
    lx.add_argument("--out", help="the image (default PLAN/preview_lux.png)")
    lx.add_argument("--size", type=float, default=600.0, help="the square's side (m)")
    lx.add_argument("--cell", type=float, default=1.0, help="the raster's cell (m)")
    lx.add_argument("--hour", type=float, default=23.0)
    pv = sub.add_parser("preview", help="a Blender night preview: AG15's night materials lit "
                                        "by the plan's lights")
    pv.add_argument("build")
    pv.add_argument("--plan", help="the plan's folder (default BUILD/atmos)")
    pv.add_argument("--out", help="the images' folder (default PLAN/previews)")
    pv.add_argument("--views", nargs="*", default=["core"], help="AG15's `core` views (the "
                    "corporate core from the air and a street through it), or names")
    pv.add_argument("--width", type=int, default=3840)
    pv.add_argument("--samples", type=int, default=64)
    pv.add_argument("--engine", choices=("cycles", "eevee"), default="cycles")
    pv.add_argument("--hour", type=float, default=None)
    pv.add_argument("--radius", type=float, default=450.0,
                    help="the plan's lights within this of a view's middle (m)")
    pv.add_argument("--fog", type=float, default=None, help="the haze's density (default "
                                                            "the plan's weather)")
    pv.add_argument("--wet", type=float, default=None, help="the streets' wetness 0 to 1 "
                                                            "(default the plan's weather)")
    pv.add_argument("--blender")
    pv.add_argument("--eye", nargs=3, type=float, action="append", default=[])
    pv.add_argument("--target", nargs=3, type=float, action="append", default=[])
    pv.add_argument("--lens", type=float, default=28.0)
    bg = sub.add_parser("budgets", help="AT7: the plans' budgets across cities (budgets.md, "
                                        "budgets.json)")
    bg.add_argument("plans", nargs="+", help="plan folders (`atmosgen plan`'s output)")
    bg.add_argument("--out", required=True, help="the table's folder")
    args = ap.parse_args(argv)
    if args.cmd == "plan" and args.build == "schema" and args.out is None:
        args.out = args.out_schema
    return {"spec": cmd_spec, "plan": cmd_plan, "lux": cmd_lux, "review": cmd_review,
            "preview": cmd_preview, "budgets": cmd_budgets}[args.cmd](args)


def cmd_budgets(args) -> int:
    from .budgets import write
    rep = write(args.plans, args.out)
    print((Path(args.out) / "budgets.md").read_text(encoding="utf-8"))
    bad = [r["city"] for r in rep["rows"] if not all(r["checks"].values())]
    if bad:
        print("FAIL: a check failed in " + ", ".join(bad), file=sys.stderr)
        return 1
    return 0
