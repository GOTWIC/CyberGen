"""lifegen's command line (`python -m lifegen ...`):

    lifegen spec validate SPEC [--build BUILD] [--filled OUT]   the life spec, against a
                                                                built city
    lifegen spec schema [OUT]                                   its JSON schema
    lifegen plan schema [--which W] [OUT]                       the plan's schemas
    lifegen plan BUILD [--spec S] [--out DIR] [--no-preview]    the life plan (BUILD/life);
                                                                exit 1 when a check fails
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
        from .plan import library_cars
        _write_json(S.fill(res.spec, model.get("districts", []), library_cars()), args.filled)
    print("ok")
    return 0


def cmd_plan(args) -> int:
    from . import planmodel as PM
    if args.build == "schema":
        model, title = PM.SCHEMAS[args.which]
        _write_json(PM.json_schema(model, title), args.out or args.out_schema)
        return 0
    from .plan import build_plan, report_text
    rep = build_plan(args.build, args.spec, args.out, preview=not args.no_preview)
    sys.stdout.write(report_text(rep))
    print(f"{len(rep['wrote'])} files written to {rep['out']} in {rep['seconds']} s")
    if not rep["ok"]:
        print("FAIL: a check failed; the plan is not delivered (the exporter leaves it out)",
              file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="lifegen", description="CyberGen stage 4: people, "
                                                             "traffic, transit and air")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("spec", help="the life spec")
    ss = sp.add_subparsers(dest="spec_cmd", required=True)
    v = ss.add_parser("validate")
    v.add_argument("spec")
    v.add_argument("--build", help="a built city (its districts' and lines' names)")
    v.add_argument("--filled", help="write the spec resolved for the city here")
    s = ss.add_parser("schema")
    s.add_argument("out", nargs="?")
    pp = sub.add_parser("plan", help="the life plan of a built city (or `plan schema`)")
    pp.add_argument("build", help="the build folder, or `schema`")
    pp.add_argument("out_schema", nargs="?", help=argparse.SUPPRESS)
    pp.add_argument("--spec", help="life_spec.json (default: every default)")
    pp.add_argument("--out", help="the plan's folder (default BUILD/life; with `schema` the "
                                  "file)")
    pp.add_argument("--which", default="life_plan", choices=("life_plan", "tile_spawns",
                                                             "contribution"))
    pp.add_argument("--no-preview", action="store_true", help="skip preview_crowds.png")
    args = ap.parse_args(argv)
    return {"spec": cmd_spec, "plan": cmd_plan}[args.cmd](args)
