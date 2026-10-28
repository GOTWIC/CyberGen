"""Command line: `assetgen spec validate|schema`, `assetgen brief BUILD`, `assetgen brief
diff A B`, `assetgen brief schema`, `assetgen spike OUT`, `assetgen build BUILD` (the
building shells, then the street stage), `assetgen preview BUILD`, `assetgen streets BUILD`,
`assetgen streets seam BASE REGEN`, `assetgen props BUILD`.

Exit codes: 0 valid (diff: no change; build: every check passes), 1 invalid spec (diff:
briefs differ; build: a check fails), 2 usage or file error.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__

EXIT_OK, EXIT_INVALID, EXIT_USAGE = 0, 1, 2


def _write_json(data: dict, out: str | None) -> int:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {out}")
    else:
        sys.stdout.write(text)
    return EXIT_OK


def _model_of(build: str | None):
    if build is None:
        return None
    from .brief import load_model
    return load_model(build)[0]


def cmd_spec_validate(args: argparse.Namespace) -> int:
    from . import spec as S
    if not Path(args.spec).is_file():
        print(f"error: {args.spec}: file not found", file=sys.stderr)
        return EXIT_USAGE
    model = _model_of(args.build)
    res = S.load_spec(args.spec, model)
    for issue in res.errors:
        print(issue, file=sys.stderr)
    if not args.quiet:
        for issue in res.warnings:
            print(issue, file=sys.stderr)
    if not res.ok:
        print(f"INVALID: {args.spec}: {len(res.errors)} error(s)", file=sys.stderr)
        return EXIT_INVALID
    if args.filled:
        _write_json(S.dump(res.filled), args.filled)
    s = res.filled
    print(f"OK: {s.city or '(any city)'}: {s.uniqueness}, {s.texel_density_px_m} px/m, "
          f"{len(res.spec.eras)} eras set ({len(s.eras)} with presets), "
          f"{len(s.districts)} districts, {len(s.owners)} owners, {len(s.landmarks)} "
          f"landmarks, {len(res.warnings)} warnings")
    return EXIT_OK


def cmd_spec_schema(args: argparse.Namespace) -> int:
    from .spec import json_schema
    return _write_json(json_schema(), args.out)


def cmd_brief(args: argparse.Namespace) -> int:
    from . import brief as B
    from . import spec as S
    src = Path(args.build)
    if not (src / "city_model.json").is_file() and not src.is_file():
        print(f"error: {args.build}: no city_model.json", file=sys.stderr)
        return EXIT_USAGE
    t0 = time.perf_counter()
    model, sha, bdir = B.load_model(src)
    spec = None
    if args.spec:
        res = S.load_spec(args.spec, model)
        for issue in res.issues:
            print(issue, file=sys.stderr)
        if not res.ok:
            return EXIT_INVALID
        spec = res.spec
    ov = S.overrides_by_id(S.load_overrides(args.overrides)) if args.overrides else None
    t1 = time.perf_counter()
    result = B.build_briefs(model, spec, ov)
    out = Path(args.out) if args.out else bdir / "assets"
    path = B.write_briefs(out, model, sha, result)
    st = result["stats"]
    st["seconds"]["load"] = round(t1 - t0, 2)
    (out / "brief_report.json").write_text(json.dumps(st, indent=1) + "\n", encoding="utf-8",
                                           newline="\n")
    if not args.no_preview:
        from .preview_edges import render
        render(model, result["briefs"], out / "preview_edges.png")
    print(f"wrote {path}: {st['buildings']} briefs in {time.perf_counter() - t0:.1f} s")
    print("edges: " + ", ".join(f"{k} {v}" for k, v in st["edges"].items()))
    return EXIT_OK


def cmd_brief_diff(args: argparse.Namespace) -> int:
    from . import briefdiff as D
    try:
        d = D.diff(args.a, args.b)
    except (OSError, ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    if args.json:
        Path(args.json).write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8",
                                   newline="\n")
    sys.stdout.write(D.text(d, None if args.all else 20))
    return EXIT_OK if not (d["added"] or d["removed"] or d["changed"]) else EXIT_INVALID


def cmd_brief_schema(args: argparse.Namespace) -> int:
    from .briefmodel import json_schema
    return _write_json(json_schema(), args.out)


def cmd_spike(args: argparse.Namespace) -> int:
    from . import spike
    rep = spike.write_spike(args.out, quantized=args.quantized)
    for name, r in rep["buildings"].items():
        print(f"{name}: {r['triangles']} triangles, {r['instances']} instances, "
              f"{r['bytes']} bytes, sha256 {r['sha256'][:16]}")
    return EXIT_OK


def cmd_build(args: argparse.Namespace) -> int:
    from . import build as BD
    src = Path(args.build)
    if not (src / "city_model.json").is_file() and not src.is_file():
        print(f"error: {args.build}: no city_model.json", file=sys.stderr)
        return EXIT_USAGE
    try:
        rep = BD.build(src, args.spec, args.overrides, args.workers,
                       streets=not args.no_streets, props=not args.no_props)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_INVALID
    sys.stdout.write(BD.report_text(rep))
    print(f"files written: {rep['files_written']}")
    return EXIT_OK if rep["ok"] else EXIT_INVALID


def cmd_preview(args: argparse.Namespace) -> int:
    from . import previews as PV
    return PV.main(args)


def cmd_streets(args: argparse.Namespace) -> int:
    from . import brief as B
    from . import spec as S
    from .streets.build import build as street_build, default_workers
    src = Path(args.build)
    if not (src / "city_model.json").is_file() and not src.is_file():
        print(f"error: {args.build}: no city_model.json", file=sys.stderr)
        return EXIT_USAGE
    model, sha, bdir = B.load_model(src)
    spec = None
    if args.spec:
        res = S.load_spec(args.spec, model)
        for issue in res.issues:
            print(issue, file=sys.stderr)
        if not res.ok:
            return EXIT_INVALID
        spec = res.filled
    out = Path(args.out) if args.out else bdir / "assets"
    rep = street_build(model, sha, out, spec, workers=args.workers or default_workers(),
                       force=args.force)
    st, f = rep["stats"], rep["files"]
    print(f"{rep['city']}: {st['pieces']} street pieces in {st['tiles']} tiles, "
          f"{st['triangles']} triangles, {st['disk_bytes'] / 1e6:.1f} MB; "
          f"{f['tiles_made']} tiles made, {f['tiles_written']} written "
          f"in {rep['seconds']['total']} s")
    for c in rep["checks"]:
        if not c["ok"]:
            print(f"check failed: {c['id']}: {c['detail']}", file=sys.stderr)
    print(f"{'PASS' if rep['ok'] else 'FAIL'}: see {out / 'streets_report.txt'}")
    return EXIT_OK if rep["ok"] else EXIT_INVALID


def cmd_props(args: argparse.Namespace) -> int:
    from . import brief as B
    from . import spec as S
    from .props.build import build as props_build, default_workers
    src = Path(args.build)
    if not (src / "city_model.json").is_file() and not src.is_file():
        print(f"error: {args.build}: no city_model.json", file=sys.stderr)
        return EXIT_USAGE
    model, sha, bdir = B.load_model(src)
    spec = None
    if args.spec:
        res = S.load_spec(args.spec, model)
        for issue in res.issues:
            print(issue, file=sys.stderr)
        if not res.ok:
            return EXIT_INVALID
        spec = res.filled
    out = Path(args.out) if args.out else bdir / "assets"
    rep = props_build(model, sha, out, spec, workers=args.workers or default_workers(),
                      force=args.force)
    st, f = rep["stats"], rep["files"]
    print(f"{rep['city']}: {st['variants']} variants in {st['families']} families, "
          f"{st['instances']} instances, {st['signs']} signs, {st['unique_triangles']} unique "
          f"triangles, {st['disk_bytes'] / 1e6:.1f} MB; {f['tiles_made']} tiles made, "
          f"{len(f['written'])} files written in {rep['seconds']['total']} s")
    for c in rep["checks"]:
        if not c["ok"]:
            print(f"check failed: {c['id']}: {c['detail']}", file=sys.stderr)
    print(f"{'PASS' if rep['ok'] else 'FAIL'}: see {out / 'props_report.txt'}")
    if args.sheets:
        from .props.sheets import render
        for f in render(out, Path(args.sheets)):
            print(f"wrote {f}")
    return EXIT_OK if rep["ok"] else EXIT_INVALID


def cmd_streets_seam(args: argparse.Namespace) -> int:
    from .streets.seam import seam
    try:
        r = seam(Path(args.base), Path(args.regen), args.district)
    except (OSError, ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    if args.json:
        Path(args.json).write_text(json.dumps(r, indent=1) + "\n", encoding="utf-8",
                                   newline="\n")
    print(f"{r['changed']} of {r['pieces']} pieces changed ({r['own']} themselves, "
          f"{r['seam']} through a neighbor, {len(r['unexplained'])} unexplained); "
          f"{len(r['changed_tiles'])} of {r['tiles']} tiles changed, "
          f"{len(r['tiles_without_a_changed_piece'])} without a changed piece")
    return EXIT_OK if not r["unexplained"] and not r["tiles_without_a_changed_piece"] \
        else EXIT_INVALID


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="assetgen",
                                description="Offline building, street and texture assets.")
    p.add_argument("--version", action="version", version=f"assetgen {__version__}")
    sub = p.add_subparsers(dest="group", required=True)

    spec = sub.add_parser("spec", help="asset spec tools")
    ssub = spec.add_subparsers(dest="command", required=True)
    v = ssub.add_parser("validate", help="validate an asset spec and fill the era presets")
    v.add_argument("spec")
    v.add_argument("--build", metavar="BUILD", help="check names against this city build")
    v.add_argument("--filled", metavar="OUT.json", help="also write the filled spec")
    v.add_argument("-q", "--quiet", action="store_true", help="hide warnings")
    v.set_defaults(func=cmd_spec_validate)
    sc = ssub.add_parser("schema", help="print or write the asset spec JSON Schema")
    sc.add_argument("out", nargs="?")
    sc.set_defaults(func=cmd_spec_schema)

    br = sub.add_parser("brief", help="the brief of every building (briefs.json)")
    bsub = br.add_subparsers(dest="command", required=True)
    bm = bsub.add_parser("make", help="write BUILD/assets/briefs.json (also: assetgen brief "
                                      "BUILD)")
    bm.add_argument("build", help="a citygen build directory (or its city_model.json)")
    bm.add_argument("--spec", help="asset_spec.json (default: the era presets)")
    bm.add_argument("--overrides", help="asset_overrides.json")
    bm.add_argument("--out", help="output directory (default BUILD/assets)")
    bm.add_argument("--no-preview", action="store_true", help="skip preview_edges.png")
    bm.set_defaults(func=cmd_brief)
    bd = bsub.add_parser("diff", help="briefs added, removed and changed between two builds")
    bd.add_argument("a", help="briefs.json or a build directory")
    bd.add_argument("b")
    bd.add_argument("--json", metavar="FILE", help="also write the diff as JSON")
    bd.add_argument("--all", action="store_true", help="list every id")
    bd.set_defaults(func=cmd_brief_diff)
    bs = bsub.add_parser("schema", help="print or write the brief JSON Schema")
    bs.add_argument("out", nargs="?")
    bs.set_defaults(func=cmd_brief_schema)

    sp = sub.add_parser("spike", help="AG0's three test buildings as glTF (the Unreal spike)")
    sp.add_argument("out")
    sp.add_argument("--quantized", action="store_true",
                    help="also write KHR_mesh_quantization copies")
    sp.set_defaults(func=cmd_spike)

    bu = sub.add_parser("build", help="building shells and proxies, then the street packs "
                                      "(BUILD/assets)")
    bu.add_argument("build", help="a citygen build directory (or its city_model.json)")
    bu.add_argument("--spec", help="asset_spec.json (default: the era presets)")
    bu.add_argument("--overrides", help="asset_overrides.json")
    bu.add_argument("--workers", type=int, help="worker processes (default "
                                                "ASSETGEN_WORKERS, else up to 4)")
    bu.add_argument("--no-streets", action="store_true",
                    help="the buildings only (default: then the street stage, as "
                         "`assetgen streets`)")
    bu.add_argument("--no-props", action="store_true",
                    help="no props, plants or signs (default: last, as `assetgen props`)")
    bu.set_defaults(func=cmd_build)

    pv = sub.add_parser("preview", help="Blender previews of a build's assets")
    pv.add_argument("build", help="a citygen build directory with BUILD/assets")
    pv.add_argument("--out", help="output directory (default BUILD/assets/previews)")
    pv.add_argument("--blockout", help="the build's blockout directory (city.blend), for "
                                       "ground, streets and the street cameras")
    pv.add_argument("--views", nargs="*", help="city, districts, street, sheets (default all of "
                                                  "these), city_full")
    pv.add_argument("--only", nargs="*", help="just these views and sheets (city, "
                                              "iso_<district>, street_<n>, random, <type>)")
    pv.add_argument("--width", type=int, default=2400, help="render width in pixels")
    pv.add_argument("--cell", type=int, default=480, help="contact sheet cell in pixels")
    pv.add_argument("--blender", help="the Blender executable")
    pv.set_defaults(func=cmd_preview)

    sg = sub.add_parser("streets", help="AG7: every street element as per-tile glTF packs")
    ssub2 = sg.add_subparsers(dest="command", required=True)
    st = ssub2.add_parser("make", help="write BUILD/assets/streets/ (also: assetgen streets "
                                       "BUILD)")
    st.add_argument("build", help="a citygen build directory (or its city_model.json)")
    st.add_argument("--spec", help="asset_spec.json (default: the era presets)")
    st.add_argument("--out", help="output directory (default BUILD/assets)")
    st.add_argument("--workers", type=int, help="worker processes (at most 4; default "
                                                "ASSETGEN_WORKERS or 4)")
    st.add_argument("--force", action="store_true",
                    help="make every tile again (the files are still written only if "
                         "their bytes change)")
    st.set_defaults(func=cmd_streets)
    se = ssub2.add_parser("seam", help="what a district regeneration changed in the street "
                                       "packs, and why")
    se.add_argument("base", help="the base build (its street stage run)")
    se.add_argument("regen", help="the regenerated build (its street stage run)")
    se.add_argument("--district", help="the regenerated district's name")
    se.add_argument("--json", metavar="FILE", help="also write the result as JSON")
    se.set_defaults(func=cmd_streets_seam)

    pr = sub.add_parser("props", help="AG8: prop and plant variants, exact props and signs")
    pr.add_argument("build", help="a citygen build directory (or its city_model.json)")
    pr.add_argument("--spec", help="asset_spec.json (default: the era presets)")
    pr.add_argument("--out", help="output directory (default BUILD/assets)")
    pr.add_argument("--workers", type=int, help="worker processes (at most 4; default "
                                                "ASSETGEN_WORKERS or 4)")
    pr.add_argument("--force", action="store_true",
                    help="make every family and tile again (files are still written only "
                         "if their bytes change)")
    pr.add_argument("--sheets", metavar="DIR",
                    help="also render the variant sheets (a sheet per district style, one of "
                         "the plants) in Blender into DIR")
    pr.set_defaults(func=cmd_props)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `assetgen brief BUILD` is short for `assetgen brief make BUILD`
    if len(argv) >= 2 and argv[0] == "brief" and argv[1] not in ("make", "diff", "schema",
                                                                 "-h", "--help"):
        argv.insert(1, "make")
    # `assetgen streets BUILD` is short for `assetgen streets make BUILD`
    if len(argv) >= 2 and argv[0] == "streets" and argv[1] not in ("make", "seam", "-h",
                                                                   "--help"):
        argv.insert(1, "make")
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
