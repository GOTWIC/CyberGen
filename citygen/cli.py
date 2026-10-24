"""Command line: `citygen spec validate|render|schema`, `citygen build`, `citygen model schema`.

Exit codes: 0 valid (build: every check passed), 1 invalid spec or a failed build check,
2 usage or file error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__

MAX_VARIANTS = 20  # same as citygen.build.MAX_VARIANTS (kept here so `spec` stays light)
from .validate import Result, SpecError, dump_spec, load_spec

EXIT_OK, EXIT_INVALID, EXIT_USAGE = 0, 1, 2


def _print_issues(result: Result, quiet: bool = False) -> None:
    for issue in result.errors:
        print(issue, file=sys.stderr)
    if not quiet:
        for issue in result.warnings:
            print(issue, file=sys.stderr)


def _load(path: str) -> Result | int:
    if not Path(path).is_file():
        print(f"error: {path}: file not found", file=sys.stderr)
        return EXIT_USAGE
    try:
        return load_spec(path)
    except SpecError as e:
        for issue in e.issues:
            print(issue, file=sys.stderr)
        return EXIT_INVALID


def _summary(result: Result) -> str:
    s = result.filled
    lines = s.transit.lines
    modes = sorted({line.mode for line in lines})
    sites = sum(len(d.megasites or []) for d in s.districts)
    return (f"OK: {s.name}: seed {s.seed}, {s.size_km[0]:g} x {s.size_km[1]:g} km, "
            f"{len(s.districts)} districts, {len(s.water.rivers)} rivers, "
            f"{len(s.water.islands)} islands, {len(lines)} transit lines "
            f"({', '.join(modes) or 'none'}), {sites} megasites, "
            f"{len(result.warnings)} warnings")


def cmd_validate(args: argparse.Namespace) -> int:
    result = _load(args.spec)
    if isinstance(result, int):
        return result
    _print_issues(result, args.quiet)
    if not result.ok:
        print(f"INVALID: {args.spec}: {len(result.errors)} error(s)", file=sys.stderr)
        return EXIT_INVALID
    if args.filled:
        Path(args.filled).parent.mkdir(parents=True, exist_ok=True)
        Path(args.filled).write_text(dump_spec(result.filled), encoding="utf-8")
    print(_summary(result))
    return EXIT_OK


def cmd_render(args: argparse.Namespace) -> int:
    result = _load(args.spec)
    if isinstance(result, int):
        return result
    _print_issues(result, quiet=True)
    if not result.ok:
        print(f"INVALID: {args.spec}: {len(result.errors)} error(s); nothing rendered",
              file=sys.stderr)
        return EXIT_INVALID
    from .schematic import render  # matplotlib is only needed here

    render(result.filled, args.out, dpi=args.dpi)
    print(f"wrote {args.out}")
    return EXIT_OK


def cmd_build(args: argparse.Namespace) -> int:
    result = _load(args.spec)
    if isinstance(result, int):
        return result
    _print_issues(result, quiet=True)
    if not result.ok:
        print(f"INVALID: {args.spec}: {len(result.errors)} error(s); nothing built",
              file=sys.stderr)
        return EXIT_INVALID
    from .build import build_city, write_outputs  # shapely, matplotlib only here

    built = build_city(result, max_variants=args.variants)
    paths = write_outputs(built, args.out_dir, dpi=args.dpi)
    for p in paths:
        print(f"wrote {p}")
    failed = [c for c in built.checks if not c.passed]
    if failed:
        for c in failed:
            for f in c.failures:
                print(f"check failed: {c.id}: {f}", file=sys.stderr)
        print(f"FAIL: {built.spec.name}: {len(failed)} check(s) failed; see "
              f"{Path(args.out_dir) / 'report.txt'}", file=sys.stderr)
        return EXIT_INVALID
    print(f"PASS: {built.spec.name}: all {len(built.checks)} checks passed")
    return EXIT_OK


def _write_json(data: dict, out: str | None) -> int:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        sys.stdout.write(text)
    return EXIT_OK


def cmd_spec_schema(args: argparse.Namespace) -> int:
    from .spec import json_schema

    return _write_json(json_schema(), args.out)


def cmd_model_schema(args: argparse.Namespace) -> int:
    from .model import json_schema

    return _write_json(json_schema(), args.out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="citygen", description="Offline prompt-to-city generator.")
    p.add_argument("--version", action="version", version=f"citygen {__version__}")
    sub = p.add_subparsers(dest="group", required=True)

    spec = sub.add_parser("spec", help="city spec tools")
    ssub = spec.add_subparsers(dest="command", required=True)
    v = ssub.add_parser("validate", help="validate a spec and fill defaults")
    v.add_argument("spec")
    v.add_argument("--filled", metavar="OUT.json", help="also write the filled spec")
    v.add_argument("-q", "--quiet", action="store_true", help="hide warnings")
    v.set_defaults(func=cmd_validate)
    r = ssub.add_parser("render", help="2D debug schematic of a spec (PNG)")
    r.add_argument("spec")
    r.add_argument("out")
    r.add_argument("--dpi", type=int, default=110)
    r.set_defaults(func=cmd_render)
    sc = ssub.add_parser("schema", help="print or write the spec JSON Schema")
    sc.add_argument("out", nargs="?")
    sc.set_defaults(func=cmd_spec_schema)

    b = sub.add_parser("build", help="build the city model, checks and preview (M1a2: water, "
                                     "districts, waterways)")
    b.add_argument("spec")
    b.add_argument("out_dir")
    b.add_argument("--dpi", type=int, default=110)
    b.add_argument("--variants", type=int, default=MAX_VARIANTS,
                   help=f"hydrology variants to try at most (default {MAX_VARIANTS})")
    b.set_defaults(func=cmd_build)

    model = sub.add_parser("model", help="city model tools")
    msub = model.add_subparsers(dest="command", required=True)
    ms = msub.add_parser("schema", help="print or write the city model JSON Schema")
    ms.add_argument("out", nargs="?")
    ms.set_defaults(func=cmd_model_schema)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:  # argparse exits 2 on usage errors, 0 on --help
        return int(e.code or 0)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
