"""M14's decks on the building line (AG10): what a building on, under or beside a deck's slab
may do, read from its brief's `deck` record (`records`, written by `brief._brief`).

- **On a deck** (role `on`): its masses stand on the deck's top (M3) and its street front on
  the slab (AG3, `shell.ground_mm`); nothing of it reaches under the deck's top.
- **Under a deck** (`under`, M14's undercity, `attrs.deck_under`): nothing of it reaches
  over the soffit. A roof within `PLENUM_MAX_M` of it is closed up to it by a louvered
  plenum band, so its top meets the soffit; a parapet otherwise stops `CEIL_GAP_M` under it;
  no roof form; the roof's equipment, the type's roof features and masts keep under it
  (`roofs.Clear` takes the slab as a ceiling); its walls take a covered street's grime
  from the ground up and its fronts and windows are lit (`genome`).
- **Beside or through a slab** (`near`: a ground building within `NEAR_M` of it and over
  its soffit; `through`: one the slab is cut round, standing in a hole of its own with the
  slab's collar round it): nothing of it inside the slab.

`check` counts the vertices of a building's asset (shell, front, its parts' boxes) inside
the slab's volume where its role does not allow them.
"""

from __future__ import annotations

import numpy as np

from .. import canon as C
from ..planar import inside_poly

PLENUM_MAX_M = 1.2      # (within AG1's parapet allowance over a mass, `envelope.PARAPET_MM`)
CEIL_GAP_M = 0.3
NEAR_M = 2.0
CLIP_M = 3.0            # the slab's plan in a brief: within this of the building's box
TOL_MM = 20.0


def records(model, ground) -> dict[str, dict]:
    """{building id: its deck record in world coordinates} for every building on, under,
    beside or through a deck's slab: the deck, the role, its top and soffit over the
    building's pivot (M13: its base), and the slab's plan near it."""
    from shapely.geometry import box

    from citygen import geom as G

    from ..streets.decks import slab_of
    out: dict[str, dict] = {}
    if not getattr(model, "decks", None):
        return out
    for dk in sorted(model.decks, key=lambda d: d.id):
        P, through = slab_of(model, dk)
        thr = {i for i, _ in through}
        top, sd = float(dk.top_m), float(dk.slab_m)
        x0, y0, x1, y1 = P.bounds
        for b in model.buildings:
            if b.footprint is None or b.id in out:
                continue
            ext = b.footprint.exterior
            bx = (min(p[0] for p in ext), min(p[1] for p in ext), max(p[0] for p in ext),
                  max(p[1] for p in ext))
            if bx[0] > x1 + NEAR_M or bx[2] < x0 - NEAR_M or bx[1] > y1 + NEAR_M or \
                    bx[3] < y0 - NEAR_M:
                continue
            base = float(getattr(b, "base_m", None) or 0.0)
            if b.level and b.attrs.get("deck") == dk.id:
                role, off = "on", 0.0
            elif b.attrs.get("deck_under") == dk.id:
                role, off = "under", 0.0
            elif b.level or b.attrs.get("deck_under"):
                continue
            else:
                with G.canonical():
                    f = G.from_model_poly(b.footprint)
                    d = f.distance(P)
                if b.id in thr:
                    role = "through"
                elif d <= NEAR_M and b.height_m > top - sd:
                    role = "near"
                else:
                    continue
                # (the slab over the ground where it comes nearest, from the building's base)
                with G.canonical():
                    q = G.nearest(P, G.centroid(f))
                off = ground.at(q[0], q[1]) - base
            with G.canonical():
                near = G.inter(P, box(bx[0] - CLIP_M, bx[1] - CLIP_M, bx[2] + CLIP_M,
                                      bx[3] + CLIP_M))
                parts = []
                for p in G.parts(near):
                    if G.area1(p) < 0.01:
                        continue
                    parts.append({"exterior": [list(c) for c in list(p.exterior.coords)[:-1]],
                                  "holes": [[list(c) for c in list(h.coords)[:-1]]
                                            for h in p.interiors]})
            out[b.id] = {"id": dk.id, "role": role, "top_m": C.m(top + off),
                         "underside_m": C.m(top - sd + off), "slab": parts}
    return out


def framed(rec: dict, ox: float, oy: float) -> dict:
    """A deck record in a building's frame (origin (ox, oy))."""
    return {**rec, "slab": [{"exterior": [C.pt(p, ox, oy) for p in s["exterior"]],
                             "holes": [[C.pt(p, ox, oy) for p in h] for h in s["holes"]]}
                            for s in rec["slab"]]}


def role(brief: dict) -> str | None:
    return (brief.get("deck") or {}).get("role")


def ceiling_mm(brief: dict) -> int | None:
    """Under a deck: its soffit over the building's pivot (mm); else None."""
    d = brief.get("deck")
    if not d or d["role"] != "under":
        return None
    return int(round(d["underside_m"] * 1000))


def clear_seg(brief: dict):
    """Under a deck, the slab as a ceiling for AG4's `roofs.Clear`: one corridor over the
    whole building (its masses' box and a margin) from `CEIL_GAP_M` under the soffit up;
    else None."""
    d = brief.get("deck")
    if not d or d["role"] != "under":
        return None
    xs = [p[0] for m in brief["masses"] for p in m["footprint"]["exterior"]]
    ys = [p[1] for m in brief["masses"] for p in m["footprint"]["exterior"]]
    if not xs:
        return None
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    lo = (d["underside_m"] - CEIL_GAP_M) * 1000.0
    hi = (d["top_m"] + 2.0) * 1000.0
    cy = (y0 + y1) / 2.0 * 1000.0
    h = ((y1 - y0) / 2.0 + 2.0) * 1000.0
    return ([(x0 - 2.0) * 1000.0, cy, lo, hi], [(x1 + 2.0) * 1000.0, cy, lo, hi], h, "deck",
            d["id"])


def check(brief: dict, arrs: dict, parts: list | None = None) -> dict:
    """The vertices of a building's asset inside its deck's slab where its role does not
    allow them: on a deck, under the deck's top; under one, over its soffit; beside or
    through one, inside the slab (between soffit and top), all within the slab's plan."""
    d = brief.get("deck")
    out = {"role": None, "vertices": 0, "inside": 0, "ok": True}
    if not d:
        return out
    out["role"] = d["role"]
    pts = [np.unique(a["pos"], axis=0).astype(np.float64) for a in arrs.values()]
    pts += [np.asarray(p, dtype=np.float64) for p, _ in (parts or [])]
    pts = [p for p in pts if len(p)]
    if not pts or not d["slab"]:
        return out
    P = np.concatenate(pts)
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    out["vertices"] = int(len(P))
    ins = np.zeros(len(P), dtype=bool)
    for s in d["slab"]:
        ext = [(q[0] * 1000.0, q[1] * 1000.0) for q in s["exterior"]]
        holes = [[(q[0] * 1000.0, q[1] * 1000.0) for q in h] for h in s["holes"]]
        ins |= inside_poly(x, y, ext, holes)
    top, under = d["top_m"] * 1000.0, d["underside_m"] * 1000.0
    if d["role"] == "on":
        bad = ins & (z < top - TOL_MM)
    elif d["role"] == "under":
        bad = ins & (z > under + TOL_MM)
    else:
        bad = ins & (z > under + TOL_MM) & (z < top - TOL_MM)
    out["inside"] = int(bad.sum())
    if out["inside"]:
        k = int(np.argmax(bad))
        out["first"] = [C.m(x[k] / 1000.0), C.m(y[k] / 1000.0), C.m(z[k] / 1000.0)]
    out["ok"] = out["inside"] == 0
    return out


__all__ = ["records", "framed", "role", "ceiling_mm", "clear_seg", "check", "PLENUM_MAX_M",
           "CEIL_GAP_M"]
