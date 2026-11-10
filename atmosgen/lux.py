"""`atmosgen lux BUILD`: the plan's illuminance on the ground round the corporate core
(`preview_lux.png`), a first look at AT1's check (scope 8) without its occlusion test:

$$E(p) = \\sum_i \\frac{I_i(\\gamma_i)\\,\\cos\\theta_i}{d_i^2}\\,w_i(d_i)$$

with $I_i(\\gamma)$ the light's intensity toward $p$ (a spot's peak inside its inner cone,
falling smoothly to 0 at its outer; a point's alike all round; a lit face's times the cosine
off its normal, nothing behind it), $\\theta_i$ the angle of incidence on the ground, $d_i$
the distance and $w_i = \\mathrm{clamp}(1 - (d/R)^4)^2$ Unreal's window at the light's reach
$R$. The ground is flat at its height there (0 on a flat city). Every light is on at the hour
by its schedule (times its share), broken ones dark. With the image, the average and the
share under the minimum of the class's targets (`presets.LIGHT_LEVELS`) on the sidewalks,
crosswalks, alleys and the lanes inside the square: without occlusion these are upper
bounds, so a street dark here is dark in Unreal (the run-through's dark carriageways).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import presets as P

CLASS = {"sidewalk": "sidewalk", "crosswalk": "crosswalk", "crossing": "crosswalk",
         "alley": "alley", "pedestrian_street": "sidewalk", "promenade": "sidewalk"}


def _core(m: dict) -> tuple[float, float, str]:
    """The middle of the corporate core (else the city's first district's), and its name."""
    from shapely.geometry import Polygon
    ds = sorted(m["districts"], key=lambda d: (d.get("archetype") != "corporate_core", d["id"]))
    d = ds[0]
    g = Polygon(d["polygon"]["exterior"])
    c = g.representative_point()
    return c.x, c.y, d.get("name") or d["id"]


def illuminance(lights: list[dict], x0: float, y0: float, n: int, cell: float, hour: float,
                schedules: dict) -> np.ndarray:
    """E (lux) on an n x n raster from (x0, y0), rows from the south, at z 0."""
    E = np.zeros((n, n), dtype=np.float64)
    h = int(math.floor(hour)) % 24
    xs = x0 + (np.arange(n) + 0.5) * cell
    for L in lights:
        if not L["on"]:
            continue
        k = schedules.get(L["schedule"], [1.0] * 24)[h]
        if k < 0.05:
            continue
        lx, ly, lz = L["pos"]
        R = float(L["reach_m"])
        if lz <= 0.05:
            continue
        i0 = max(0, int((lx - R - x0) / cell))
        i1 = min(n, int((lx + R - x0) / cell) + 1)
        j0 = max(0, int((ly - R - y0) / cell))
        j1 = min(n, int((ly + R - y0) / cell) + 1)
        if i0 >= i1 or j0 >= j1:
            continue
        gx = (xs[i0:i1] - lx)[None, :]
        gy = (y0 + (np.arange(j0, j1) + 0.5) * cell - ly)[:, None]
        dz = -lz
        d2 = gx * gx + gy * gy + dz * dz
        d = np.sqrt(d2)
        cos_in = lz / d                          # incidence on the ground (normal up)
        yaw, pitch = math.radians(L["aim"][0]), math.radians(L["aim"][1])
        ax, ay, az = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw),
                      math.sin(pitch))
        cos_g = (gx * ax + gy * ay + dz * az) / d    # off the light's aim
        if L["shape"] == "spot":
            ci, co = (math.cos(math.radians(a)) for a in L["cone"])
            t = np.clip((cos_g - co) / max(ci - co, 1e-6), 0.0, 1.0)
            I = L["cd"] * t * t * (3.0 - 2.0 * t)
        elif L["shape"] == "rect":
            I = L["cd"] * np.clip(cos_g, 0.0, 1.0)
        else:
            I = np.full_like(d, L["cd"])
        win = np.clip(1.0 - (d / R) ** 4, 0.0, 1.0) ** 2
        E[j0:j1, i0:i1] += k * I * cos_in / d2 * win
    return E


def lux_preview(build, plan=None, out=None, size_m: float = 600.0, cell_m: float = 1.0,
                hour: float = 23.0) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    build = Path(build)
    pdir = Path(plan) if plan else build / "atmos"
    pl = json.loads((pdir / "atmos_plan.json").read_text(encoding="utf-8"))
    m = json.loads((build / "city_model.json").read_text(encoding="utf-8"))
    cx, cy, name = _core(m)
    x0, y0 = cx - size_m / 2.0, cy - size_m / 2.0
    n = int(round(size_m / cell_m))
    lights = []
    for t in pl["tiles"]:
        ix, iy = int(t["tile"][1:4]), int(t["tile"][4:7])
        if (ix + 1) * 256.0 < x0 - 150 or ix * 256.0 > x0 + size_m + 150 or \
                (iy + 1) * 256.0 < y0 - 150 or iy * 256.0 > y0 + size_m + 150:
            continue
        lights += json.loads((pdir / t["file"]).read_text(encoding="utf-8"))["lights"]
    E = illuminance(lights, x0, y0, n, cell_m, hour, pl["schedules"])

    def at(x, y):
        i, j = int((x - x0) / cell_m), int((y - y0) / cell_m)
        return float(E[j, i]) if 0 <= i < n and 0 <= j < n else None

    def along(line, step=2.0):
        """A line's points every `step` m (its vertices alone sit at its ends, at the
        junctions)."""
        for a, b in zip(line, line[1:]):
            L = math.dist(a[:2], b[:2])
            k = max(1, int(L / step))
            for s in range(k):
                f = (s + 0.5) / k
                yield [a[c] + (b[c] - a[c]) * f for c in range(3)]

    stats: dict[str, list[float]] = {}
    junction: list[float] = []
    for w in m.get("walkways", []):
        c = CLASS.get(w.get("kind"))
        if c is None or (w.get("attrs") or {}).get("level"):
            continue
        for p in along(w["line"]):
            v = at(p[0], p[1])
            if v is not None:
                stats.setdefault(c, []).append(v)
    for ln in m.get("lanes", []):
        for p in along(ln.get("centerline") or []):
            v = at(p[0], p[1])
            if v is not None and abs(p[2]) < 1.0:
                (junction if ln.get("node_id") else
                 stats.setdefault("carriageway", [])).append(v)
    summary = {}
    for c, vs in sorted(stats.items()):
        avg_t, min_t = P.LIGHT_LEVELS[c]
        summary[c] = {"points": len(vs), "average_lx": round(sum(vs) / len(vs), 1),
                      "target_average_lx": avg_t, "target_min_lx": min_t,
                      "under_min": round(sum(1 for v in vs if v < min_t) / len(vs), 3)}
    if junction:
        # (the connector lanes through the junctions: M6 keeps the lamps off them)
        summary["junction"] = {"points": len(junction),
                               "average_lx": round(sum(junction) / len(junction), 1),
                               "target_average_lx": P.LIGHT_LEVELS["carriageway"][0],
                               "target_min_lx": P.LIGHT_LEVELS["carriageway"][1],
                               "under_min": round(sum(1 for v in junction if v <
                                                      P.LIGHT_LEVELS["carriageway"][1])
                                                  / len(junction), 3)}
    fig = plt.figure(figsize=(10, 10.6), dpi=150)
    ax = fig.add_axes([0.04, 0.08, 0.92, 0.86])
    im = ax.imshow(np.maximum(E, 0.05), origin="lower", cmap="inferno",
                   norm=LogNorm(vmin=0.1, vmax=200.0),
                   extent=[x0, x0 + size_m, y0, y0 + size_m])
    from shapely.geometry import Polygon
    for b in m.get("buildings", []):
        fp = b.get("footprint") or {}
        ex = fp.get("exterior") or []
        if len(ex) < 3:
            continue
        xs = [p[0] for p in ex]
        ys = [p[1] for p in ex]
        if max(xs) < x0 or min(xs) > x0 + size_m or max(ys) < y0 or min(ys) > y0 + size_m:
            continue
        ax.fill(xs, ys, color="#1c2333", lw=0)
    ax.contour(np.linspace(x0, x0 + size_m, n), np.linspace(y0, y0 + size_m, n), E,
               levels=[2.0, 10.0], colors=["#5ad0ff", "#ffffff"], linewidths=0.4)
    ax.set_xlim(x0, x0 + size_m)
    ax.set_ylim(y0, y0 + size_m)
    ax.set_title(f"{pl['city']}: the plan's light on the ground round {name} at "
                 f"{hour:g}:00, lux, no occlusion (contours 2 and 10 lx)", fontsize=9)
    cb = fig.add_axes([0.2, 0.035, 0.6, 0.015])
    fig.colorbar(im, cax=cb, orientation="horizontal")
    txt = "; ".join(f"{c} avg {s['average_lx']:g} lx (target {s['target_average_lx']:g}), "
                    f"{100 * s['under_min']:.0f}% under {s['target_min_lx']:g}"
                    for c, s in summary.items())
    fig.text(0.5, 0.005, txt, ha="center", fontsize=6.5)
    dest = Path(out) if out else pdir / "preview_lux.png"
    fig.savefig(dest)
    plt.close(fig)
    return {"image": str(dest), "district": name, "center": [round(cx, 1), round(cy, 1)],
            "size_m": size_m, "cell_m": cell_m, "lights": len(lights), "hour": hour,
            "max_lx": round(float(E.max()), 1), "classes": summary}


KIND_COLORS = {"street_light": "#ffd27a", "wall_light": "#ff9a3d", "sign": "#ff2a6d",
               "shop_sign": "#b967ff", "spill": "#05d9e8"}


def plan_map(build, plan=None, out=None) -> dict:
    """`preview_plan.png`: every light of the plan over the districts, by kind (broken ones
    grey), the city at a glance."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    build = Path(build)
    pdir = Path(plan) if plan else build / "atmos"
    pl = json.loads((pdir / "atmos_plan.json").read_text(encoding="utf-8"))
    m = json.loads((build / "city_model.json").read_text(encoding="utf-8"))
    pts: dict[str, list] = {}
    for t in pl["tiles"]:
        for L in json.loads((pdir / t["file"]).read_text(encoding="utf-8"))["lights"]:
            pts.setdefault(L["kind"] if L["on"] else "broken", []).append(L["pos"][:2])
    x0, y0, x1, y1 = m["bounds"]
    fig = plt.figure(figsize=(10, 10.4), dpi=200)
    ax = fig.add_axes([0.02, 0.05, 0.96, 0.9])
    ax.set_facecolor("#05070d")
    for d in m["districts"]:
        ex = d["polygon"]["exterior"]
        ax.fill([p[0] for p in ex], [p[1] for p in ex], color="#111827", lw=0.4,
                ec="#2a3550")
    order = ("spill", "shop_sign", "sign", "wall_light", "street_light", "broken")
    for k in order:
        if k not in pts:
            continue
        a = np.array(pts[k])
        ax.scatter(a[:, 0], a[:, 1], s=0.15 if k in ("spill", "shop_sign") else 0.35,
                   c=KIND_COLORS.get(k, "#555555"), lw=0,
                   label=f"{k.replace('_', ' ')} ({len(a)})")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    leg = ax.legend(loc="lower left", fontsize=7, markerscale=12, facecolor="#0b0f1a",
                    labelcolor="#d8deea", framealpha=0.9)
    leg.get_frame().set_edgecolor("#2a3550")
    ax.set_title(f"{pl['city']}: the atmos plan's {pl['counts']['all']} lights by kind "
                 f"({pl['preset']}, {pl['hour']:g}:00)", fontsize=9, color="#d8deea")
    dest = Path(out) if out else pdir / "preview_plan.png"
    fig.savefig(dest, facecolor="#05070d")
    plt.close(fig)
    return {"image": str(dest), "kinds": {k: len(v) for k, v in pts.items()}}
