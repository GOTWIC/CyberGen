"""AT7: the plans' budgets across cities (scope 8 and 9): `atmosgen budgets PLAN...`.

For each plan folder (`atmosgen plan`'s output, beside its `atmos_report.json`):

- the plan's time and its checks (lux, faces, air, weather, far; the look's post present);
- its lights by tier and the far city's cards;
- per 256 m tile the most lights (`presets.BUDGETS["lights_per_cell"]`), fog volumes and
  emitters (`AIR_BUDGETS`), drip lines (`WEATHER_BUDGETS`) and far cards (`FAR_BUDGETS`) any
  tile holds;
- near the view, what the runtime's live sets choose from: the most lights on within each
  tier's range of any point of the city (on a 32 m grid), against what it keeps live (the mid
  tier's 512 within 300 m, the shadowed 16 within 60 m, the high tier's 48 within 750 m, a
  walker's 512 within 1,200 m by sight), and the share of the city where the cap binds (the
  set is the nearest that many; past them a light shows as its far card).

Writes `budgets.md` (the table) and `budgets.json`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import presets as P

GRID_M = 32.0


def _lights(pdir: Path, plan: dict) -> list[dict]:
    out = []
    for t in plan.get("tiles") or []:
        f = pdir / t["file"]
        if f.is_file():
            out += json.loads(f.read_text(encoding="utf-8"))["lights"]
    return out


def _disc_counts(xy: np.ndarray, x0: float, y0: float, w: int, h: int, r_m: float):
    """Lights within `r_m` of each grid point (GRID_M cells): counts per cell, summed over a
    disc of cells (each light at its cell's middle: within a cell of exact)."""
    if not len(xy):
        return np.zeros((h, w))
    i = np.clip(((xy[:, 0] - x0) / GRID_M).astype(int), 0, w - 1)
    j = np.clip(((xy[:, 1] - y0) / GRID_M).astype(int), 0, h - 1)
    cnt = np.zeros((h, w))
    np.add.at(cnt, (j, i), 1.0)
    k = int(math.ceil(r_m / GRID_M))
    # (a summed-area table, and the disc as rows of runs)
    sat = np.zeros((h + 1, w + 1))
    sat[1:, 1:] = cnt.cumsum(0).cumsum(1)
    out = np.zeros((h, w))
    jj, ii = np.mgrid[0:h, 0:w]
    for dj in range(-k, k + 1):
        half = int(math.floor(math.sqrt(max(0.0, (r_m / GRID_M) ** 2 - dj * dj))))
        r0 = np.clip(jj + dj, 0, h - 1)
        valid = (jj + dj >= 0) & (jj + dj < h)
        c0 = np.clip(ii - half, 0, w)
        c1 = np.clip(ii + half + 1, 0, w)
        row = sat[r0 + 1, c1] - sat[r0 + 1, c0] - sat[r0, c1] + sat[r0, c0]
        out += np.where(valid, row, 0.0)
    return out


def near_view(lights: list[dict], tiers: dict, bounds) -> dict:
    """The most lights on (not broken) within each tier's range of any point of the city,
    and the share of points where it is over the tier's size."""
    x0, y0, x1, y1 = bounds
    w = max(1, int(math.ceil((x1 - x0) / GRID_M)))
    h = max(1, int(math.ceil((y1 - y0) / GRID_M)))
    on = [L for L in lights if L.get("on", True)]
    sel = {
        "mid": ([L for L in on if L["tier"] in ("near", "mid")],
                float(tiers.get("mid_m", 300.0)), int(tiers.get("mid_max", 512))),
        "shadowed": ([L for L in on if L.get("shadow")],
                     float(tiers.get("near_m", 60.0)), int(tiers.get("near_max", 16))),
        "high": ([L for L in on if L["tier"] == "high"],
                 float(tiers.get("high_m", 750.0)), int(tiers.get("high_max", 48))),
        "sight": ([L for L in on if L["tier"] != "high"],
                  float(tiers.get("sight_m", 1200.0)), int(tiers.get("sight_max", 512))),
    }
    out = {}
    for name, (ls, r, cap) in sel.items():
        xy = np.array([L["pos"][:2] for L in ls], dtype=np.float64).reshape(-1, 2)
        c = _disc_counts(xy, x0, y0, w, h, r)
        # (only the points near some light: the city, not the open sea round it)
        any_near = _disc_counts(np.array([L["pos"][:2] for L in on], dtype=np.float64)
                                .reshape(-1, 2), x0, y0, w, h, 300.0) > 0
        vals = c[any_near] if any_near.any() else c.ravel()
        out[name] = {"range_m": r, "cap": cap, "max": int(vals.max()) if vals.size else 0,
                     "p50": int(np.percentile(vals, 50)) if vals.size else 0,
                     "over_share": round(float((vals > cap).mean()), 3) if vals.size else 0.0}
    return out


def summary(pdir: Path) -> dict:
    pdir = Path(pdir)
    plan = json.loads((pdir / "atmos_plan.json").read_text(encoding="utf-8"))
    rep = json.loads((pdir / "atmos_report.json").read_text(encoding="utf-8"))
    ck = plan.get("checks") or {}
    lights = _lights(pdir, plan)
    xs = [L["pos"][0] for L in lights] or [0.0]
    ys = [L["pos"][1] for L in lights] or [0.0]
    bounds = (min(xs) - 300.0, min(ys) - 300.0, max(xs) + 300.0, max(ys) + 300.0)
    air = ck.get("air") or {}
    we = ck.get("weather") or {}
    far = ck.get("far") or {}
    per_tile = {t["tile"]: t["count"] for t in plan.get("tiles") or []}
    return {
        "city": plan["city"], "plan": str(pdir), "seconds": rep.get("seconds"),
        "checks": {k: bool((ck.get(k) or {}).get("ok")) for k in
                   ("lux", "faces", "air", "weather", "far") if k in ck},
        "post": plan.get("post") is not None,
        "lights": len(lights), "on": sum(1 for L in lights if L.get("on", True)),
        "tiers": rep.get("tiers") or {},
        "far": (plan.get("far") or {}).get("counts") or {},
        "tiles": len(per_tile),
        "per_tile": {
            "lights": [max(per_tile.values()) if per_tile else 0,
                       int(P.BUDGETS["lights_per_cell"])],
            "volumes": [air.get("max_volumes_per_tile", 0),
                        (air.get("budgets") or {}).get("volumes_per_tile",
                                                       P.AIR_BUDGETS["volumes_per_tile"])],
            "emitters": [air.get("max_emitters_per_tile", 0),
                         (air.get("budgets") or {}).get("emitters_per_tile",
                                                        P.AIR_BUDGETS["emitters_per_tile"])],
            "drips": [we.get("max_drips_per_tile", 0), P.WEATHER_BUDGETS["drips_per_tile"]],
            "far": [far.get("max_per_tile", 0), P.FAR_BUDGETS["cards_per_tile"]]},
        "near_view": near_view(lights, plan.get("tiers") or {}, bounds),
    }


def table(rows: list[dict]) -> str:
    out = ["| City | Plan (s) | Checks | Lights (near / mid / high) | Far cards (glow / pool / "
           "wash) | Most a tile: lights, volumes, emitters, drips, far cards | Most near the "
           "view: mid 300 m, shadow 60 m, high 750 m, sight 1,200 m |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        ck = ", ".join(f"{k} {'pass' if v else 'FAIL'}" for k, v in r["checks"].items())
        ck += ", post" if r["post"] else ""
        t = r["tiers"]
        f = r["far"]
        pt = r["per_tile"]
        tiles = ", ".join(f"{pt[k][0]:,} / {pt[k][1]:,}" for k in
                          ("lights", "volumes", "emitters", "drips", "far"))
        nv = r["near_view"]

        def cell(k):
            v = nv[k]
            return f"{v['max']:,} / {v['cap']:,}" + (
                f" ({100.0 * v['over_share']:.0f}% over)" if v["over_share"] > 0 else "")
        near = ", ".join(cell(k) for k in ("mid", "shadowed", "high", "sight"))
        out.append(f"| {r['city']} | {r['seconds']:.0f} | {ck} | {r['lights']:,} "
                   f"({t.get('near', 0):,} / {t.get('mid', 0):,} / {t.get('high', 0):,}) | "
                   f"{f.get('all', 0):,} ({f.get('glow', 0):,} / {f.get('pool', 0):,} / "
                   f"{f.get('wash', 0):,}) | {tiles} | {near} |")
    return "\n".join(out) + "\n"


def write(plans: list[str | Path], out: str | Path) -> dict:
    rows = [summary(Path(p)) for p in plans]
    od = Path(out)
    od.mkdir(parents=True, exist_ok=True)
    (od / "budgets.json").write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n",
                                     encoding="utf-8", newline="\n")
    (od / "budgets.md").write_text(table(rows), encoding="utf-8", newline="\n")
    return {"rows": rows, "out": str(od)}
