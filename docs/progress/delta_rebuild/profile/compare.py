"""The game thread's timers per frame at each viewpoint, places on against off, from the
regions' timer statistics `profile.py` exported: python compare.py STATS_DIR OUT_MD"""

import csv
import sys
from pathlib import Path


def load(p: Path) -> tuple[int, dict]:
    rows = {}
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows[r["Name"].strip()] = (float(r["Incl"]), float(r["Excl"]), int(r["Count"]))
    frames = rows.get("FEngineLoop::Tick", (0, 0, 1))[2]
    return frames, rows


def main() -> int:
    d, out = Path(sys.argv[1]), Path(sys.argv[2])
    views = sorted({p.stem.split("__", 1)[1] for p in d.glob("*.csv")})
    lines = ["# Places on and off at fixed viewpoints (game thread, ms a frame)", ""]
    for v in views:
        fa, a = load(d / f"night_plan_all__{v}.csv")
        fb, b = load(d / f"night_life_noplaces__{v}.csv")
        ta = 1000 * a["FEngineLoop::Tick"][0] / fa
        tb = 1000 * b["FEngineLoop::Tick"][0] / fb
        lines += [f"## {v}", "",
                  f"Frames {fa} (places on) and {fb} (off); the game thread's frame "
                  f"{ta:.2f} ms against {tb:.2f} ms.", "",
                  "| timer | on incl | off incl | on excl | off excl | diff incl |",
                  "|---|---|---|---|---|---|"]
        names = set(a) | set(b)

        def ms(rows, n, k, fr):
            return 1000 * rows.get(n, (0.0, 0.0, 0))[k] / max(1, fr)

        life = sorted(n for n in names if n.startswith(("CityGenLife", "CgLife", "SmartObject",
                                                       "USmartObject")))
        top = sorted(names, key=lambda n: -abs(ms(a, n, 1, fa) - ms(b, n, 1, fb)))[:25]
        for n in life + [n for n in top if n not in life]:
            lines.append(f"| {n} | {ms(a, n, 0, fa):.3f} | {ms(b, n, 0, fb):.3f} | "
                         f"{ms(a, n, 1, fa):.3f} | {ms(b, n, 1, fb):.3f} | "
                         f"{ms(a, n, 0, fa) - ms(b, n, 0, fb):+.3f} |")
        lines.append("")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
