"""What a district regeneration (M10's `citygen build --district`) changes in the street
packs, and why: `assetgen streets seam BASE REGEN`.

Both builds' street stages must have run (`BUILD/assets/streets/manifest.json`). A piece
changed when its hash differs (or it is new or gone); it is explained when its own entity
changed in the model, or its inputs name an entity that changed (a junction it meets, a
crosswalk, a tree, a door, the road under a column); a tile changed when its pack's bytes
differ. Done when every changed piece is explained and every changed tile holds a changed
piece: then a regenerated district rewrites only its own tiles and its seam's.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .. import canon as C


def _dumps(model) -> dict[str, str]:
    return {e.id: C.digest(e.model_dump(mode="json")) for e in model.entities()}


def seam(base_dir: Path, regen_dir: Path, district: str | None = None) -> dict:
    from ..brief import load_model
    from .build import gather
    from .ctx import Ctx
    base_m, _, bdir = load_model(base_dir)
    reg_m, _, rdir = load_model(regen_dir)
    mb = json.loads((bdir / "assets" / "streets" / "manifest.json").read_text())
    mr = json.loads((rdir / "assets" / "streets" / "manifest.json").read_text())
    db, dr = _dumps(base_m), _dumps(reg_m)
    changed_ids = {i for i in set(db) | set(dr) if db.get(i) != dr.get(i)}
    pb, pr = mb["pieces"], mr["pieces"]
    pieces = {p.id: p for p in gather(Ctx(reg_m))}
    before = {p.id: p for p in gather(Ctx(base_m))}
    changed = sorted(i for i in set(pb) | set(pr)
                     if pb.get(i, {}).get("hash") != pr.get(i, {}).get("hash"))
    dpoly = None
    if district:
        d = next((d for d in reg_m.districts if d.name == district), None)
        if d is not None:
            dpoly = d.polygon.exterior
    own, seam_, unexplained = [], [], []
    far = 0.0
    for i in changed:
        if i in changed_ids:
            own.append(i)
            continue
        # what it reads now or read before (a tree gone from beside a sidewalk is named
        # only in its old inputs)
        p = pieces.get(i) or before.get(i)
        text = " ".join(C.dumps(q.inputs) for q in (pieces.get(i), before.get(i))
                        if q is not None)
        if p is not None and any(f'"{c}"' in text for c in changed_ids):
            seam_.append(i)
            if dpoly is not None:
                o = p.inputs.get("origin")
                if o:
                    far = max(far, _dist_ring(o, dpoly))
        else:
            unexplained.append(i)
    tiles_b, tiles_r = mb["tiles"], mr["tiles"]
    changed_tiles = sorted(t for t in set(tiles_b) | set(tiles_r)
                           if tiles_b.get(t, {}).get("sha256") != tiles_r.get(t, {}).get("sha256"))
    tile_of = {i: r["tile"] for i, r in pr.items()}
    tile_of.update({i: r["tile"] for i, r in pb.items() if i not in tile_of})
    with_change = {tile_of[i] for i in changed if i in tile_of} | \
        {pb[i]["tile"] for i in changed if i in pb}
    idle = [t for t in changed_tiles if t not in with_change]
    return {"base": str(base_dir), "regen": str(regen_dir), "district": district,
            "pieces": len(pr), "changed": len(changed), "own": len(own), "seam": len(seam_),
            "unexplained": sorted(unexplained), "tiles": len(tiles_r),
            "changed_tiles": changed_tiles, "tiles_without_a_changed_piece": idle,
            "farthest_seam_m": round(far, 1)}


def _dist_ring(p, ring) -> float:
    """0 inside the ring, else the distance to it."""
    from .ctx import _inside
    if _inside(ring, p[0], p[1]):
        return 0.0
    best = None
    for i in range(len(ring)):
        a, b = ring[i - 1], ring[i]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        f = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        ex, ey = p[0] - a[0] - f * dx, p[1] - a[1] - f * dy
        d = math.sqrt(ex * ex + ey * ey)
        best = d if best is None or d < best else best
    return best or 0.0
