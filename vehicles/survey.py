"""survey.py: the kit's checks and its clay and zebra renders on every car of the roster.

    python vehicles/survey.py                    # every car, into the cache (vehicles/survey)
    python vehicles/survey.py --only vanta_r,orrin_aria --no-render
    python vehicles/survey.py --docs             # also into docs/progress/AG18/
    python vehicles/survey.py --sign DIR         # a fingerprint of every car as built
    python vehicles/survey.py --compare A B      # two folders of fingerprints, car by car

One Blender run a car, through blender.sh (one job at a time on this machine), about 25
seconds each with the renders. With --docs each car's folder gets check.json, clay.jpg and
zebra.jpg, and docs/progress/AG18/checks.md the table of what the checks found. Cars to be
redesigned (EXCLUDED) are left out of the checks. --sign and --compare are for changes to
the kit (signature.py): sign every car before and after, and the same fingerprints mean the
same cars. Stdlib only.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = Path.home() / ".cache" / "cybergen" / "vehicles" / "survey"
DOCS = ROOT / "docs" / "progress" / "AG18"
EXCLUDED = ("vex_", "aurel_")  # to be redesigned (the Aurels: Swagnik, 2026-11-12)
CHECKS = ("tires", "ground", "symmetry", "panels", "through", "triangles")
MARK = {"ok": "ok", "look": "look", "fail": "FAIL"}


def cars(only, every=False):
    names = sorted(p.stem for p in (HERE / "cars").glob("*.py"))
    names = [n for n in names if every or not n.startswith(EXCLUDED)]
    if only:
        want = [n.strip() for n in only.split(",") if n.strip()]
        missing = [n for n in want if n not in names]
        if missing:
            sys.exit("no such car (or one left out): %s" % ", ".join(missing))
        names = want
    return names


def run(car, out, render):
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(HERE / "blender.sh"), str(HERE / "cars" / (car + ".py")), "--out", str(out),
           "--check"] + (["--clay", "--zebra"] if render else [])
    t0 = time.time()
    with open(out / "log.txt", "w") as log:
        rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode
    print("%-18s %s in %3.0f s (log %s)" % (car, "done" if rc == 0 else "FAILED",
                                           time.time() - t0, out / "log.txt"), flush=True)
    return rc == 0 and (out / "check.json").exists()


def sign(only, out):
    """A fingerprint of every car as built (the cars to be redesigned too: the kit is
    theirs as well), into out/<car>.json."""
    out.mkdir(parents=True, exist_ok=True)
    ok = True
    for car in cars(only, every=True):
        cmd = [str(HERE / "blender.sh"), str(HERE / "signature.py"),
               str(HERE / "cars" / (car + ".py")), str(out / (car + ".json"))]
        with open(out / (car + ".log"), "w") as log:
            rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode
        print("%-18s %s" % (car, "signed" if rc == 0 else "FAILED (%s)" % (out / (car + ".log"))),
              flush=True)
        ok = ok and rc == 0
    return ok


def compare(a, b):
    """Two folders of fingerprints car by car: same, or what differs. Returns how many
    cars differ."""
    bad = 0
    for f in sorted(x for x in Path(a).glob("*.json") if x.is_file()):
        g = Path(b) / f.name
        if not g.exists():
            print("%-18s missing in %s" % (f.stem, b))
            bad += 1
            continue
        x, y = json.loads(f.read_text()), json.loads(g.read_text())
        diffs = []
        for k in sorted(set(x) | set(y)):
            if x.get(k) == y.get(k):
                continue
            if isinstance(x.get(k), dict) and isinstance(y.get(k), dict):
                ks = sorted(n for n in set(x[k]) | set(y[k]) if x[k].get(n) != y[k].get(n))
                diffs.append("%s: %d differ (%s%s)" % (k, len(ks), ", ".join(ks[:6]),
                                                       ", ..." if len(ks) > 6 else ""))
            else:
                diffs.append("%s: %r -> %r" % (k, x.get(k), y.get(k)))
        print("%-18s %s" % (f.stem, "same" if not diffs else "; ".join(diffs)))
        bad += bool(diffs)
    print("cars that differ: %d" % bad)
    return bad


def tires_text(c):
    ws = c["tires"]["wheels"]
    if not ws:
        return "none (hover)"
    near = min(ws, key=lambda w: w["clearance_mm"] if w["clearance_mm"] is not None else 1e9)
    steer = [w["steer_deg"] for w in ws if "steer_deg" in w]
    text = "%s mm to %s" % (near["clearance_mm"], near["nearest"])
    if steer:
        text += ", steers %d deg" % min(steer)
    return text


def table(rows):
    """checks.md: what the checks found, car by car."""
    out = ["# AG18: what the kit's checks find", "",
           "`python vehicles/survey.py --docs` runs `carkit`'s checks (`vehicles/carcheck.py`) "
           "and its clay and zebra renders on every car but those to be redesigned. Each "
           "car's folder holds its `check.json`, `clay.jpg` and `zebra.jpg`. A verdict is "
           "`ok`, `look` (worth a look at the place named; often meant) or `FAIL`.", "",
           "| Car | Tires | Ground | Symmetry | Panels | Through | Triangles |",
           "|---|---|---|---|---|---|---|"]
    for car, c in rows:
        g, s, p, th, tr = c["ground"], c["symmetry"], c["panels"], c["through"], c["triangles"]
        real = [r for r in p["open_edges"] if not r["meant"]]
        cells = [
            "%s: %s" % (MARK[c["tires"]["verdict"]], tires_text(c)),
            "%s: %s mm (%s)" % (MARK[g["verdict"]], g["clearance_mm"], g["lowest"]),
            "%s: %d objects" % (MARK[s["verdict"]], s["objects"]),
            "%s: %d open runs, %d cutter holes" % (MARK[p["verdict"]], len(real),
                                                   len(p["cutter_holes"])),
            "%s: %d parts" % (MARK[th["verdict"]], th.get("count", 0)),
            "%s: %d" % (MARK[tr["verdict"]], tr["total"]),
        ]
        out.append("| [%s](%s/check.json) | %s |" % (car, car, " | ".join(cells)))
    out += ["", "## Findings by car", ""]
    for car, c in rows:
        lines = []
        for w in c["tires"]["wheels"]:
            if w["verdict"] != "ok":
                bits = ["%s mm to `%s`" % (w["clearance_mm"], w["nearest"])]
                if "steer_deg" in w:
                    bits.append("turns %d degrees before it touches `%s`"
                                % (w["steer_deg"], w.get("steer_hits")) if "steer_hits" in w
                                else "turns %d degrees" % w["steer_deg"])
                if abs(w["foot_mm"]) > 6:
                    bits.append("its foot %s mm off the ground" % w["foot_mm"])
                lines.append("tire `%s`: %s" % (w["tag"], ", ".join(bits)))
        g = c["ground"]
        if g["verdict"] != "ok":
            lines.append("ground: `%s` %s mm over the floor%s" % (
                g["lowest"], g["clearance_mm"],
                "; under it: " + ", ".join("`%s` %s m" % (n, z) for z, n in g["under_floor"])
                if g["under_floor"] else ""))
        s = c["symmetry"]
        if s["objects"]:
            lines.append("not mirrored: " + ", ".join(
                "`%s` %s mm" % (r["object"], r["off_mm"]) for r in s["asymmetric"][:12])
                + (" and %d more" % (s["objects"] - 12) if s["objects"] > 12 else ""))
        p = c["panels"]
        for r in p["open_edges"]:
            if not r["meant"]:
                lines.append("open edge: `%s`, %d mm, at %s" % (r["panel"], r["length_mm"],
                                                              tuple(r["at"])))
        meant = [r for r in p["open_edges"] if r["meant"]]
        if meant:
            lines.append("open ends of open pieces (meant): " + ", ".join(sorted(
                {"`%s`" % r["panel"] for r in meant})))
        for r in p["cutter_holes"]:
            lines.append("a cutter's hole inside `%s`: %d mm round, at %s" % (
                r["panel"], r["length_mm"], tuple(r["at"])))
        for r in c["through"]["parts"]:
            lines.append("cabin part in the open: `%s`, %d%% of it, up to %s mm from what "
                         "would hide it, at %s" % (r["object"], round(100 * r["share"]),
                                                   r["out_mm"], tuple(r["at"])))
        tr = c["triangles"]
        if tr["verdict"] != "ok":
            lines.append("triangles: %d over the %d budget; most in %s" % (
                tr["total"], tr["budget"], ", ".join("`%s` %d" % (n, k)
                                                     for n, k in tr["groups"][:4])))
        out += ["**%s** (%s)" % (car, MARK[c["verdict"]]), ""]
        out += ["- " + ln for ln in lines] or ["- nothing"]
        out.append("")
    return "\n".join(out)


def colors(rows):
    out = ["The palette each car's script gives the kit (a finish as a name or as metallic, "
           "roughness, coat; the second color is the kit's default red where a car sets "
           "none). A new design picks a color no car here has.", "",
           "| Car | Paint | Finish | Second color | Finish |", "|---|---|---|---|---|"]
    for car, c in rows:
        p = c.get("palette", {})

        def rgb(v):
            return "(%.2f, %.2f, %.2f)" % tuple(v) if v else ""
        fin = [p.get("paint_finish", ""), p.get("paint2_finish", "")]
        fin = [f if isinstance(f, str) else str(tuple(f)) for f in fin]
        out.append("| %s | %s | %s | %s | %s |" % (car, rgb(p.get("paint")), fin[0],
                                                   rgb(p.get("paint2")), fin[1]))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", default="", help="some cars, comma separated")
    ap.add_argument("--out", default=str(CACHE), help="where each car's folder goes")
    ap.add_argument("--no-render", action="store_true", help="the checks alone (2 s a car)")
    ap.add_argument("--docs", action="store_true",
                    help="copy the results into docs/progress/AG18 and write checks.md")
    ap.add_argument("--table", action="store_true",
                    help="no Blender: the tables again from an earlier run's check.json files")
    ap.add_argument("--sign", metavar="DIR", help="a fingerprint of every car as built")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"),
                    help="two folders of fingerprints, car by car")
    a = ap.parse_args()
    if a.compare:
        sys.exit(1 if compare(*a.compare) else 0)
    if a.sign:
        sys.exit(0 if sign(a.only, Path(a.sign)) else 1)
    out = Path(a.out)
    rows = []
    for car in cars(a.only):
        if a.table or run(car, out / car, not a.no_render):
            if (out / car / "check.json").exists():
                rows.append((car, json.loads((out / car / "check.json").read_text())))
    for car, c in rows:
        print("%-18s %-5s %s" % (car, c["verdict"], "  ".join(
            "%s %s" % (n, c[n]["verdict"]) for n in CHECKS)))
    if a.docs:
        for car, _ in rows:
            (DOCS / car).mkdir(parents=True, exist_ok=True)
            for f in ("check.json", "clay.jpg", "zebra.jpg"):
                if (out / car / f).exists():
                    shutil.copyfile(out / car / f, DOCS / car / f)
        if not a.only:
            (DOCS / "checks.md").write_text(table(rows) + "\n\n## Show colors\n\n" + colors(rows)
                                            + "\n")
            print("wrote", DOCS / "checks.md")


if __name__ == "__main__":
    main()
