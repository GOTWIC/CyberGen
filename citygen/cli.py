"""Command line: `citygen spec validate|render|schema|diff`, `citygen build` (M10: `--district`),
`citygen blockout`, `citygen rerender`, `citygen review`, `citygen model schema|diff`,
`citygen lock`, `citygen trace diff`, `citygen unreal` (M15).

Exit codes: 0 valid (build: every check passed), 1 invalid spec or a failed build check,
2 usage or file error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
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
        Path(args.filled).write_text(dump_spec(result.filled), encoding="utf-8", newline="\n")
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
    from . import edit as E
    from . import lock as LK
    from . import overrides as OV
    from . import trace
    from .build import build_city, write_outputs  # shapely, matplotlib only here

    spec_data = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    ov_path = Path(args.overrides) if args.overrides else \
        Path(args.spec).parent / OV.OVERRIDES_FILE
    ov = None
    if args.overrides or ov_path.is_file():
        try:
            ov = OV.load(ov_path)
        except (OSError, ValueError) as e:
            print(f"error: {ov_path}: {e}", file=sys.stderr)
            return EXIT_USAGE
        print(f"overrides: {ov_path} ({len(ov['pins'])} pins, {len(ov['edits'])} edits)")
    if args.district:
        return _regenerate(args, spec_data, ov)
    if args.trace:
        trace.start()
    built = build_city(result, max_variants=args.variants)
    built = LK.finish(built, result, ov)
    entries = trace.stop() if args.trace else None
    from . import progress as PG

    with PG.active().stage("previews and outputs"):
        paths = write_outputs(built, args.out_dir, dpi=args.dpi)
    paths.append(E.write_state(args.out_dir, E.new_state(spec_data, built, ov)))
    if args.trace:
        import hashlib

        sha = hashlib.sha256((built.model.to_json() + "\n").encode("utf-8")).hexdigest()
        trace.write(args.trace, built.spec.name, sha, entries)
        paths.append(Path(args.trace))
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
    if args.blockout:
        return _blockout(Path(args.out_dir) / "city_model.json", args.out_dir, args)
    return EXIT_OK


def _failed(built, out_dir) -> int:
    failed = [c for c in built.checks if not c.passed]
    for c in failed:
        for f in c.failures:
            print(f"check failed: {c.id}: {f}", file=sys.stderr)
    if failed:
        print(f"FAIL: {built.spec.name}: {len(failed)} check(s) failed; see "
              f"{Path(out_dir) / 'report.txt'}", file=sys.stderr)
        return EXIT_INVALID
    print(f"PASS: {built.spec.name}: all {len(built.checks)} checks passed")
    return EXIT_OK


def _regenerate(args: argparse.Namespace, spec_data: dict, ov) -> int:
    """M10: `citygen build SPEC OUT --district NAME`: one district of the build in OUT (or
    --base) regenerated; everything else stays."""
    from . import edit as E

    with E.no_gc():
        return _regenerate_in(args, spec_data, ov)


def _regenerate_in(args: argparse.Namespace, spec_data: dict, ov) -> int:
    import hashlib
    import time

    from . import edit as E
    from .build import write_outputs
    from .model import CityModel

    src = Path(args.base or args.out_dir)
    try:
        state = E.read_state(src)
        text = (src / "city_model.json").read_text(encoding="utf-8")
        old = CityModel.from_json(text)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    # (the file as written: its bytes are the model's JSON)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    del text
    if sha != state["model_sha256"]:
        print(f"error: {src / 'city_model.json'} is not the model of its build state",
              file=sys.stderr)
        return EXIT_USAGE
    now = E.code_version()
    if now["code_sha256"] != state["code_sha256"]:
        print(f"note: the city was built with other code ({state['code_sha256'][:12]}, now "
              f"{now['code_sha256'][:12]})")
    if ov is not None:
        state = {**state, "overrides": ov}
    t0 = time.time()
    try:
        built, rec = E.regenerate(state, old, args.district, spec_data=spec_data,
                                  seed=args.seed)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    dt = time.time() - t0
    state = {**state, **now, "edits": state.get("edits", []) + [rec],
             "overrides": rec["overrides"], "model_sha256": rec["model_sha256"]}
    paths = write_outputs(built, args.out_dir, dpi=args.dpi)
    paths.append(E.write_state(args.out_dir, state))
    for p in paths:
        print(f"wrote {p}")
    for n in built.notes[-4:]:
        if "regenerated" in n or "pin" in n or "names" in n:
            print(n)
    print(f"regenerated {args.district} (seed {rec['seed']}) in {dt:.1f} s")
    return _failed(built, args.out_dir)


def _blockout(model: Path, out_dir: str, args: argparse.Namespace) -> int:
    from .blockout import run_blockout

    rep = run_blockout(model, out_dir, blender=args.blender, render=not args.no_render,
                       export=not args.no_export, res=args.res, samples=args.samples)
    for c in rep["checks"]:
        if not c["passed"]:
            print(f"blockout check failed: {c['id']}: {c['detail']}", file=sys.stderr)
    out = Path(out_dir)
    b = rep.get("blender") or {}
    for f in ["blockout_plan.json", "map_2d.svg", "map_2d.png", "graphs.json", "tiles.json",
              "props.csv", "gameplay.json", "unreal/corporate_core_plan.json"]:
        if (out / f).exists():
            print(f"wrote {out / f}")
    for k, v in (b.get("files") or {}).items():
        print(f"wrote {out / v}" if isinstance(v, str) else f"wrote {len(v)} {k} in {out}")
    if not rep["passed"]:
        print(f"FAIL: blockout of {rep['city']}; see {out / 'blockout_report.txt'}",
              file=sys.stderr)
        return EXIT_INVALID
    print(f"PASS: blockout of {rep['city']}: {rep['plan']['objects']} objects, "
          f"{rep['plan']['tiles']} tiles, {rep['timings']['total_s']} s")
    return EXIT_OK


def cmd_blockout(args: argparse.Namespace) -> int:
    if not Path(args.model).is_file():
        print(f"error: {args.model}: file not found", file=sys.stderr)
        return EXIT_USAGE
    return _blockout(Path(args.model), args.out_dir, args)


def cmd_rerender(args: argparse.Namespace) -> int:
    from .blockout import rerender

    src = Path(args.blockout_dir)
    if not (src / "city.blend").is_file() or not (src / "blockout_plan.json").is_file():
        print(f"error: {src}: no city.blend and blockout_plan.json (run citygen blockout)",
              file=sys.stderr)
        return EXIT_USAGE
    try:
        if not args.views and args.eye is None:
            print("error: name a view or give --eye and --target", file=sys.stderr)
            return EXIT_USAGE
        files = rerender(src, args.to or src, args.views, width=args.width,
                         blender=args.blender, samples=args.samples, eye=args.eye,
                         target=args.target, lens=args.lens, name=args.name)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    for f in files:
        print(f"wrote {f}")
    return EXIT_OK


def cmd_unreal(args: argparse.Namespace) -> int:
    """M15: import a blockout output into an Unreal project (headless), optionally check it
    in play-in-editor."""
    from . import unreal as U

    build = Path(args.build_dir)
    if not (build / "blockout_plan.json").is_file():
        print(f"error: {build}: no blockout_plan.json (run citygen build --blockout or "
              "citygen blockout)", file=sys.stderr)
        return EXIT_USAGE
    if args.manifest_only:
        path = U.write_manifest(build, args.name, not args.blockout_only)
        print(f"wrote {path}")
        return EXIT_OK
    if args.uproject and args.new_project and not Path(args.uproject).is_file():
        up = Path(args.uproject)
        try:
            made = U.new_project(up.parent, U.find_engine(args.engine))
        except (RuntimeError, FileNotFoundError) as e:
            print(f"error: {e}", file=sys.stderr)
            return EXIT_USAGE
        print(f"created {made} from the First Person template")
        args.uproject = str(made)
    if not args.uproject or not Path(args.uproject).is_file():
        print(f"error: {args.uproject}: no such .uproject (--new-project makes one)",
              file=sys.stderr)
        return EXIT_USAGE
    try:
        res = U.import_city(build, args.uproject, engine=args.engine, name=args.name,
                            timeout=args.timeout, assets=not args.blockout_only,
                            play=args.play, fly_speed=args.fly_speed,
                            startup=not args.no_startup, view_m=args.view_range) \
            if not args.check_only else None
        if res is not None:
            print(U.import_summary(res))
            if not res.get("ok"):
                print(res.get("error", ""), file=sys.stderr)
                return EXIT_INVALID
            print(U.play_summary(res))
        if not args.no_hlod and res is not None:
            hl = U.build_hlods(build, args.uproject, engine=args.engine, timeout=args.timeout)
            print(U.hlod_summary(hl))
            if not hl.get("ok"):
                return EXIT_INVALID
        if args.check or args.check_only:
            if any(len(v) not in (7, 8) for v in args.view):
                print("error: --view NAME EX EY EZ TX TY TZ [LENS]", file=sys.stderr)
                return EXIT_USAGE
            views = [{"name": v[0], "eye": [float(x) for x in v[1:4]],
                      "target": [float(x) for x in v[4:7]],
                      "lens_mm": float(v[7]) if len(v) == 8 else 28.0} for v in args.view]
            chk = U.check_city(build, args.uproject, engine=args.engine, shots=args.shots,
                               timeout=args.timeout, width=args.shot_width, views=views)
            print(U.check_summary(chk))
            if not chk.get("ok"):
                print(chk.get("error", ""), file=sys.stderr)
                return EXIT_INVALID
    except (RuntimeError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    return EXIT_OK


def _progress_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-q", "--quiet", dest="quiet_progress", action="store_true",
                   help="no progress on stderr (the stages, a bar with the time left, the "
                        "times at the end; also $CYBERGEN_QUIET=1)")
    p.set_defaults(progress=True)


def _blockout_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--blender", help="Blender executable (default: $BLENDER, the newest "
                                     "/Applications/Blender*.app, or blender on PATH)")
    p.add_argument("--no-render", action="store_true", help="skip the preview renders")
    p.add_argument("--no-export", action="store_true", help="skip USD and glTF tiles")
    p.add_argument("--res", type=int, default=1600, help="render width in pixels")
    p.add_argument("--samples", type=int, default=16, help="EEVEE render samples")


def _write_json(data: dict, out: str | None) -> int:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if out:
        Path(out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {out}")
    else:
        sys.stdout.write(text)
    return EXIT_OK


def cmd_spec_schema(args: argparse.Namespace) -> int:
    from .spec import json_schema

    return _write_json(json_schema(), args.out)


def cmd_trace_diff(args: argparse.Namespace) -> int:
    from . import trace

    try:
        a, b = (json.loads(Path(x).read_text(encoding="utf-8")) for x in (args.a, args.b))
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    lines = trace.diff(a, b)
    if not lines:
        print(f"identical: {len(a['entries'])} entries, model {a.get('model_sha256')}")
        return EXIT_OK
    print("\n".join(lines))
    return EXIT_INVALID


def cmd_spec_diff(args: argparse.Namespace) -> int:
    from .review import spec_diff

    try:
        a, b = (json.loads(Path(x).read_text(encoding="utf-8")) for x in (args.a, args.b))
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    lines = spec_diff(a, b)
    print("\n".join(lines) if lines else "no changes")
    return EXIT_OK


def cmd_review(args: argparse.Namespace) -> int:
    from .review import review

    if not (Path(args.out_dir) / "report.json").is_file():
        print(f"error: {args.out_dir}: no report.json (build first)", file=sys.stderr)
        return EXIT_USAGE
    rec = review(args.out_dir, args.spec, args.prev)
    print(f"wrote {Path(args.out_dir) / 'review.md'} (round {rec['round']} of at most "
          f"{rec['max_rounds']}; checks {'PASS' if rec['passed'] else 'FAIL'}; "
          f"{len(rec['spec_changes'])} spec changes)")
    return EXIT_OK if rec["passed"] else EXIT_INVALID


def cmd_sweep(args: argparse.Namespace) -> int:
    from . import sweep as SW

    extra = SW.EXTRA_SEEDS[:args.extra] if args.extra is not None else SW.EXTRA_SEEDS
    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else None
    jobs = SW.spec_jobs(args.specs, seeds, extra) if args.specs else \
        SW.suite_jobs(args.suite, extra)
    if seeds and not args.specs:
        jobs = [(lab, data, s) for lab, data in {(j[0]): j[1] for j in jobs}.items()
                for s in seeds]
    if args.only:
        jobs = [j for j in jobs if args.only in j[0]]
    rows = SW.sweep(jobs, args.out, workers=args.workers, upto=args.upto,
                    previews=not args.no_previews, keep_model=args.keep_model)
    print(f"wrote {Path(args.out) / 'sweep.md'}")
    return EXIT_OK if all(r["status"] == "pass" for r in rows) else EXIT_INVALID


def cmd_model_schema(args: argparse.Namespace) -> int:
    from .model import json_schema

    return _write_json(json_schema(), args.out)


def cmd_model_diff(args: argparse.Namespace) -> int:
    from . import diff as DF

    try:
        a, b = (json.loads(Path(x).read_text(encoding="utf-8")) for x in (args.a, args.b))
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    d = DF.diff(a, b)
    if args.json:
        Path(args.json).write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8", newline="\n")
    if args.png:
        from .preview_diff import render  # matplotlib only here

        render(a, b, d, args.png)
        print(f"wrote {args.png}")
    sys.stdout.write(DF.text(d, None if args.all else args.limit))
    return EXIT_OK if not d else EXIT_INVALID


def cmd_lock(args: argparse.Namespace) -> int:
    from . import edit as E
    from . import lock as LK

    if args.verify:
        try:
            lk = json.loads(Path(args.target).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return EXIT_USAGE
        ok, lines, built = LK.verify(lk)
        if args.out:
            from .build import write_outputs

            write_outputs(built, args.out)
            print(f"wrote the rebuilt city to {args.out}")
        print("\n".join(lines))
        return EXIT_OK if ok else EXIT_INVALID
    try:
        lk = LK.make(args.target, args.release)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    out = LK.write(lk, args.out or Path(args.target) / LK.LOCK_FILE)
    print(f"wrote {out}: {lk['name']} release {lk['release']}, {len(lk['edits'])} district "
          f"regenerations, model {lk['model_sha256'][:16]}, code {lk['code_sha256'][:12]}")
    return EXIT_OK


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
    sd = ssub.add_parser("diff", help="parameter changes between two specs")
    sd.add_argument("a")
    sd.add_argument("b")
    sd.set_defaults(func=cmd_spec_diff)

    b = sub.add_parser("build", help="build the city model, checks and previews (water, "
                                     "districts, roads, streets, lots, buildings)")
    b.add_argument("spec")
    b.add_argument("out_dir")
    b.add_argument("--dpi", type=int, default=110)
    b.add_argument("--variants", type=int, default=MAX_VARIANTS,
                   help=f"hydrology variants to try at most (default {MAX_VARIANTS})")
    b.add_argument("--trace", metavar="FILE.json",
                   help="also write a sha256 of every stage output and of the district "
                        "search intermediates (compare machines with `citygen trace diff`)")
    b.add_argument("--blockout", action="store_true",
                   help="after a passing build, also build the Blender blockout (M4)")
    b.add_argument("--district", metavar="NAME",
                   help="M10: regenerate this district of the build in OUT_DIR (its entry "
                        "from SPEC; a new seed when unchanged); the rest stays as it was")
    b.add_argument("--seed", type=int, help="with --district: the district's new seed")
    b.add_argument("--base", metavar="BUILD_DIR",
                   help="with --district: the build to start from (default OUT_DIR)")
    b.add_argument("--overrides", metavar="FILE.json",
                   help="pins and overrides (default: overrides.json beside the spec)")
    _blockout_args(b)
    _progress_args(b)
    b.set_defaults(func=cmd_build)

    bo = sub.add_parser("blockout", help="Blender blockout of a built city: .blend, USD, "
                                         "glTF tiles, renders, 2D map, exports")
    bo.add_argument("model", help="city_model.json from `citygen build`")
    bo.add_argument("out_dir")
    _blockout_args(bo)
    _progress_args(bo)
    bo.set_defaults(func=cmd_blockout)

    rr = sub.add_parser("rerender", help="render chosen blockout views again from city.blend "
                                         "at another width (README images: 8K)")
    rr.add_argument("blockout_dir", help="a citygen blockout output (city.blend, "
                                         "blockout_plan.json)")
    rr.add_argument("views", nargs="*", help="top, iso_city, iso_<district> or street_<n>")
    rr.add_argument("--eye", type=float, nargs=3, metavar=("X", "Y", "Z"),
                    help="a perspective view of one's own: camera position (plan meters)")
    rr.add_argument("--target", type=float, nargs=3, metavar=("X", "Y", "Z"),
                    help="the point that view looks at")
    rr.add_argument("--lens", type=float, default=35.0, help="its lens in mm (default 35)")
    rr.add_argument("--name", default="custom", help="its file: render_<name>.jpg")
    rr.add_argument("--to", help="output folder (default: blockout_dir)")
    rr.add_argument("--width", type=int, default=7680, help="width in pixels (default 7680)")
    rr.add_argument("--samples", type=int, default=16, help="EEVEE render samples")
    rr.add_argument("--blender", help="Blender executable")
    rr.set_defaults(func=cmd_rerender)

    rv = sub.add_parser("review", help="art-direction review sheet of a build (review.md): "
                                       "checks, numbers, changes since the last round")
    rv.add_argument("out_dir", help="a `citygen build` output folder")
    rv.add_argument("--spec", help="the spec it was built from (kept for the next round)")
    rv.add_argument("--prev", metavar="PREV_OUT_DIR", help="the previous round's folder")
    rv.set_defaults(func=cmd_review)

    tr = sub.add_parser("trace", help="build trace tools")
    tsub = tr.add_subparsers(dest="command", required=True)
    td = tsub.add_parser("diff", help="first entry where two build traces differ "
                                      "(exit 0 identical, 1 different)")
    td.add_argument("a")
    td.add_argument("b")
    td.set_defaults(func=cmd_trace_diff)

    sw = sub.add_parser("sweep", help="build many specs at many seeds (no blockout) and "
                                      "tabulate passes, failing checks, retries and crashes")
    sw.add_argument("specs", nargs="*", help="spec files (default: the --suite)")
    sw.add_argument("--suite", default="m8a",
                    help="built-in set of specs and seeds when no spec is given (m8a: the "
                         "samples, the pinned demo and the test specs)")
    sw.add_argument("--seeds", help="comma-separated seeds instead of each spec's own seed "
                                    "plus the extra seeds")
    sw.add_argument("--extra", type=int, default=None,
                    help="how many of the built-in extra seeds to add (default all)")
    sw.add_argument("--only", help="keep only builds whose label contains this text")
    sw.add_argument("--out", default="out/sweep", help="output folder (default out/sweep)")
    sw.add_argument("--workers", type=int, default=4,
                    help="builds at once, one process each (default 4)")
    sw.add_argument("--upto", choices=["roads", "local", "full"], default="full",
                    help="last stage to build (default full)")
    sw.add_argument("--no-previews", action="store_true", help="reports only, no previews")
    sw.add_argument("--keep-model", action="store_true", help="keep city_model.json")
    sw.set_defaults(func=cmd_sweep)

    ue = sub.add_parser("unreal", help="import a blockout into an Unreal 5.8 project "
                                       "(World Partition level, meshes with collision, "
                                       "instanced props, graphs as data assets); importing "
                                       "again updates by id",
                        description="Import a built city into an Unreal 5.8 project. The "
                                    "city becomes the project's startup and default map "
                                    "(the last import wins; --no-startup opts out), so "
                                    "opening the project and pressing Play puts you in it: "
                                    "flying by default (WASD to move, E or Space up, Q or C "
                                    "down, the mouse to look, no collision), or walking "
                                    "with --play walk (the project's own character).")
    ue.add_argument("build_dir", help="a `citygen build --blockout` or `citygen blockout` "
                                      "output")
    ue.add_argument("uproject", nargs="?", help="the project's .uproject")
    ue.add_argument("--engine", help="engine root or editor binary (default: "
                                     "$CITYGEN_UE_ROOT or the newest installed UE_5.*)")
    ue.add_argument("--name", help="city name for the content folder (default: the plan's)")
    ue.add_argument("--new-project", action="store_true",
                    help="create the project (FOLDER/FOLDER.uproject) from the engine's "
                         "First Person template when it does not exist")
    ue.add_argument("--manifest-only", action="store_true",
                    help="write BUILD_DIR/unreal/manifest.json and stop (no Unreal needed)")
    ue.add_argument("--blockout-only", action="store_true",
                    help="leave out stage 2 (assetgen's BUILD_DIR/assets/"
                         "unreal_contribution.*.json): the blockout's actors alone (stage "
                         "2's meshes stay in the project for the next import with it)")
    ue.add_argument("--play", choices=("fly", "walk"), default="fly",
                    help="what Play puts you in: fly (default), a free camera with no "
                         "collision; walk, the project's own game mode and pawn (the First "
                         "Person character in a --new-project project)")
    ue.add_argument("--fly-speed", type=float, default=50.0, metavar="M_PER_S",
                    help="the fly pawn's top speed in m/s (default 50)")
    ue.add_argument("--view-range", type=float, default=1500.0, metavar="M",
                    help="how far around the player the level streams in, in meters "
                         "(default 1500)")
    ue.add_argument("--no-hlod", action="store_true",
                    help="skip building the level's HLODs after the import (default: built, "
                         "the far view beyond --view-range while flying; minutes for a "
                         "whole city, an import over it rebuilds only what changed)")
    ue.add_argument("--no-startup", action="store_true",
                    help="leave the project's startup and default map as they are (default: "
                         "the imported city becomes both in Config/DefaultEngine.ini; with "
                         "several cities in one project the last import wins)")
    ue.add_argument("--check", action="store_true",
                    help="after the import, play the level in the editor: streaming, "
                         "ground traces, a walk along a sidewalk (always the walking "
                         "character, whatever --play is), then a flight with the fly pawn")
    ue.add_argument("--check-only", action="store_true", help="the check without importing")
    ue.add_argument("--shots", metavar="DIR", help="with --check: rendered views into DIR")
    ue.add_argument("--view", nargs="+", action="append", default=[],
                    metavar="NAME EX EY EZ TX TY TZ [LENS]",
                    help="with --shots: one more view, eye and target in citygen meters "
                         "(z over sea level, a terrain city's ground included), lens in mm "
                         "(default 28); repeatable")
    ue.add_argument("--shot-width", type=int, default=3840,
                    help="width of the rendered views in pixels (default 3840; 7680 for 8K)")
    ue.add_argument("--timeout", type=float, default=7200.0,
                    help="seconds per editor run (default 7200)")
    _progress_args(ue)
    ue.set_defaults(func=cmd_unreal)

    model = sub.add_parser("model", help="city model tools")
    msub = model.add_subparsers(dest="command", required=True)
    ms = msub.add_parser("schema", help="print or write the city model JSON Schema")
    ms.add_argument("out", nargs="?")
    ms.set_defaults(func=cmd_model_schema)
    md = msub.add_parser("diff", help="entities two city models add, remove and change, by "
                                      "id (exit 0 identical, 1 different)")
    md.add_argument("a")
    md.add_argument("b")
    md.add_argument("--limit", type=int, default=20, help="ids listed per kind (default 20)")
    md.add_argument("--all", action="store_true", help="list every id")
    md.add_argument("--json", metavar="OUT.json", help="also write the whole diff as JSON")
    md.add_argument("--png", metavar="OUT.png", help="also draw a map of what changed")
    md.set_defaults(func=cmd_model_diff)

    lk = sub.add_parser("lock", help="freeze a build as a versioned release (city.lock.json), "
                                     "or --verify a lock by building it again")
    lk.add_argument("target", help="a build folder (or, with --verify, a lock file)")
    lk.add_argument("--release", help="release name (default: one more than the edits)")
    lk.add_argument("--out", help="lock file to write (default BUILD_DIR/city.lock.json); "
                                  "with --verify, a folder for the rebuilt city")
    lk.add_argument("--verify", action="store_true",
                    help="rebuild the locked city and compare it byte for byte")
    lk.set_defaults(func=cmd_lock)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:  # argparse exits 2 on usage errors, 0 on --help
        return int(e.code or 0)
    if not getattr(args, "progress", False):
        return args.func(args)
    # the long commands: their stages on stderr (citygen.progress), the times at the end
    from . import progress as PG

    p = PG.Progress(quiet=True if args.quiet_progress else None)
    with PG.use(p):
        try:
            return args.func(args)
        finally:
            p.summary()


if __name__ == "__main__":
    sys.exit(main())
