"""The emitter asks of assetgen (scope 4.1), and what atmosgen derives until they are met.

What atmosgen needs and the other stages do not record yet:

1. **A lamp's photometric class by variant.** AG8 draws 4 to 12 variants of each lamp kind
   per district style; each should record its head's lens (the point and normal where the
   light leaves the head, the lens's size) and its class (`cobra_head`, `post_top`,
   `wall_pack`, `high_mast`, `soffit`), in the props manifest's variant record:
   `"emitter": {"cls": "cobra_head", "lens": [x, y, z], "normal": [x, y, z], "size": [w, h]}`
   in the variant's own frame. Until then (`lamp_head`): the blockout prototype's
   `prop_light` box (M6's lamp: its lens the box's underside), placed by the prop's
   transform as the play features do, and the class from the district's mood and the road.
2. **A sign's lit face as a rectangle.** AG8 and AG6 draw each sign slot's face; each should
   record the face's middle, normal, width and height as drawn (a billboard's face stands
   0.3 m off the wall on its frame, a blade sign's two faces either side of it) and its
   emitted color and luminance (a sign page cell's mean lit color, which AG6 knows when it
   draws the page): `signs.json`'s slot record `"face": {"c": [...], "n": [...],
   "size": [w, h], "two_sided": bool}`, its cell's `"emit": {"color": "#rrggbb",
   "nits": n}`. Until then (`sign_face`): M20's slot (position, yaw, width, height) with the
   blockout prototype's 0.3 m frame, the color of its cell (AG6's shop and POI cells name
   theirs; an ad cell's is the mean of its bright pixels on the page).

3. **Fixtures for the lights the city has none for** (AT1; AG7, AG8): the plan lights what
   M6 leaves dark (junction corners, highways and ramps, service roads, footbridges, alleys,
   station platforms) on fixtures stage 2 does not draw yet, named by `Light.mount`: `pole`,
   `mast_arm` (on a traffic signal's pole, over its junction), `wall` (a wall pack over an
   alley), `canopy` (a platform's downlight). A fixture drawn at each such light's lens
   (its `pos` plus its class's `drop_m`), headed its aim's way, would meet the ask; the
   plan's report counts them (`mounts`, `asked`).

4. **Fixtures for AT2's lights** (AG4, AG7, AG8): `roof` (a crown flood on its setback or an
   outrigger 4 m off the facade, a searchlight on a roof), `beacon` (an aviation light's red
   lens at a roof corner or a mast's tip: until drawn, the runtime shows each as a small red
   glow of its own, blinking with its light), `mast` (a port yard's or an apron's 30 m high
   mast, a crane boom's floods), `ground` (an apron's edge light or a launch pad's rim light
   in the pavement). As the third ask: a fixture at the light's `pos`, headed its aim's way.

5. **Flues for AT4's smoke** (AG4, AG5): a chimney on an industrial roof (warehouses, sheds,
   yards and labs in the industrial, spaceport, megablock and old-town districts) and a
   stove pipe on a shanty stack, at the plume's foot (`Emitter.pos`, mount `chimney`,
   `stove`; a flue `presets.CHIMNEY_M` wide and tall under it). AT4's steam needs no ask:
   AG7's manholes and drains are read from the street packs where drawn (`Emitter.source`
   "assetgen", `air.street_details`), M3's roof mechanical units are AG4's roof equipment,
   M6's stalls and M9's vents are drawn already.

AT2 reads the second ask where assetgen meets it (`SignColors.face`, `.emit`: a slot record
of `signs.json` that is an object with `cell` and `face`, or a top-level `faces` map by slot
id; a cell's `emit`), so the light sits on the drawn face in its drawn color and luminance
(`Light.source` "assetgen"), and derives them otherwise: the face from M20's slot and the
prototype's frame, the color from the cell (its own, else the mean of its bright pixels), and
now the luminance too, the page cell's mean brightness against a typical page's
(`presets.SIGN_LUMA_REF`), so a dark ad with a thin neon line lights less than a bright one.

Each derived light says so (`Light.source` "derived"); `plan.counts` and `sources` count
them, so the asks' progress shows in every plan.
"""

from __future__ import annotations

import math
from pathlib import Path

# M6's blockout prototypes (citygen/blockout.py PROTOTYPES): the lamp head's box, its lens
# the box's underside, in the prop's frame (x along its yaw, z up from its position)
LAMP_HEAD = {"street_light": (1.5, 0.0, 7.55), "wall_light": (0.35, 0.0, -0.35)}
# M20's facade signs stand out from the wall on a 0.3 m frame (the blockout's sign
# prototypes); a blade sign hangs square to its wall, its faces either side of its middle
FRAME_M = {"billboard": 0.3, "banner": 0.32, "neon": 0.1, "holo_ad": 0.0, "shop_sign": 0.12}


def lamp_head(kind: str, pos, yaw_deg: float, scale) -> tuple[float, float, float]:
    """The lens of an M6 lamp (its head's underside), in the city's frame, over the prop's
    own z (relative to the ground at its foot)."""
    ox, oy, oz = LAMP_HEAD[kind]
    a = math.radians(yaw_deg)
    c, s = math.cos(a), math.sin(a)
    px, py = ox * scale[0], oy * scale[1]
    return (pos[0] + px * c - py * s, pos[1] + px * s + py * c, pos[2] + oz * scale[2])


def sign_face(slot: dict) -> list[dict]:
    """A sign slot's lit faces: [{c: middle (x, y, z over the slot's frame), yaw: its
    normal's heading, size: [w, h]}]; a two-sided slot's second face looks the other way."""
    kind = slot.get("kind")
    a = math.radians(float(slot.get("yaw_deg", 0.0)))
    x, y, z = slot["position"]
    w, h = float(slot.get("width_m", 1.0)), float(slot.get("height_m", 1.0))
    out_m = FRAME_M.get(kind, 0.1)
    faces = []
    if slot.get("mount") == "blade":
        # (a blade sign stands square to its wall along its yaw: its faces look either way
        # across it, the yaw's left and right)
        for turn in (90.0, -90.0):
            b = a + math.radians(turn)
            faces.append({"c": [x + 0.08 * math.cos(b), y + 0.08 * math.sin(b), z],
                          "yaw": math.degrees(b), "size": [w, h]})
        return faces
    faces.append({"c": [x + out_m * math.cos(a), y + out_m * math.sin(a), z],
                  "yaw": math.degrees(a), "size": [w, h]})
    if slot.get("two_sided"):
        faces.append({"c": [x - 0.02 * math.cos(a), y - 0.02 * math.sin(a), z],
                      "yaw": math.degrees(a) + 180.0, "size": [w, h], "back": True})
    return faces


class SignColors:
    """A sign slot's emitted color from assetgen's signs.json: the cell's own `color` where
    AG6 names it (shop and POI signs), else the mean of the cell's bright pixels on its page
    (ads, banners), read once per cell; None without signs.json (the plan then takes a neon
    color by the slot's id)."""

    def __init__(self, assets: Path):
        import json
        p = assets / "signs.json"
        self.ok = p.is_file()
        self.data = json.loads(p.read_text(encoding="utf-8")) if self.ok else {}
        self.assets = assets
        self.pages: dict = {}
        self.cache: dict = {}
        self.from_pages = 0

    def _page(self, name: str):
        if name not in self.pages:
            from PIL import Image
            f = (self.data.get("files") or {}).get(name)
            img = None
            if f is not None and (self.assets / f["file"]).is_file():
                with Image.open(self.assets / f["file"]) as im:
                    img = im.convert("RGB")
                    # (a quarter size is plenty for a mean color: integer box reduction)
                    img = img.reduce(4)
            self.pages[name] = img
        return self.pages[name]

    def _cell_id(self, slot_id: str) -> str | None:
        rec = (self.data.get("slots") or {}).get(slot_id)
        if isinstance(rec, dict):              # (the ask met: {cell, face})
            return rec.get("cell")
        return rec

    def color(self, slot_id: str) -> str | None:
        return self.emit(slot_id)[0]

    def emit(self, slot_id: str) -> tuple[str | None, float | None, bool]:
        """(color, luminance scale, from assetgen) of a slot's cell: the ask's `emit` where
        AG6 records it (its nits over the class's), else the cell's own color or the mean of
        its bright pixels, and its page's mean brightness over `presets.SIGN_LUMA_REF`
        (None without a page); (None, None, False) without signs.json or a cell."""
        cell_id = self._cell_id(slot_id)
        if cell_id is None:
            return None, None, False
        if cell_id in self.cache:
            return self.cache[cell_id]
        cell = (self.data.get("cells") or {}).get(cell_id) or {}
        em = cell.get("emit")
        if isinstance(em, dict) and em.get("color"):
            out = (em["color"], (float(em["nits"]) if em.get("nits") is not None else None),
                   True)
            self.cache[cell_id] = out
            return out
        col = cell.get("color")
        luma = None
        if cell.get("page"):
            img = self._page(cell["page"])
            if img is not None:
                top, luma = _mean_bright(img, cell["uv"])
                if col is None:
                    col = top
                    self.from_pages += 1
        out = (col, luma, False)
        self.cache[cell_id] = out
        return out

    def face(self, slot_id: str) -> dict | None:
        """The ask's drawn face of a slot ({c, n, size, two_sided}), when assetgen records
        it (in the slot's record, or a top-level `faces` map)."""
        rec = (self.data.get("slots") or {}).get(slot_id)
        if isinstance(rec, dict) and isinstance(rec.get("face"), dict):
            return rec["face"]
        f = (self.data.get("faces") or {}).get(slot_id)
        return f if isinstance(f, dict) else None


def faces_of(face: dict) -> list[dict]:
    """The second ask's face record as `sign_face` returns faces (its normal's heading; a
    two-sided face's back the other way)."""
    n = face["n"]
    yaw = math.degrees(math.atan2(float(n[1]), float(n[0])))
    c = [float(v) for v in face["c"]]
    out = [{"c": c, "yaw": yaw, "size": [float(v) for v in face["size"]]}]
    if face.get("two_sided"):
        out.append({"c": c, "yaw": yaw + 180.0, "size": out[0]["size"], "back": True})
    return out


def _mean_bright(img, uv) -> tuple[str | None, float]:
    """The mean color of a page cell's brightest quarter of pixels (what glows), as
    #rrggbb, and the cell's mean relative luminance (0 to 1, linear), integer arithmetic for
    the color."""
    W, H = img.size
    x0, y0 = int(uv[0] * W), int(uv[1] * H)
    x1, y1 = max(x0 + 1, int(uv[2] * W)), max(y0 + 1, int(uv[3] * H))
    import numpy as np
    px = np.asarray(img.crop((x0, y0, x1, y1)), dtype=np.int64).reshape(-1, 3)
    if not len(px):
        return None, 0.0
    r_, g_, b_ = px[:, 0], px[:, 1], px[:, 2]
    # (sorted by luminance, then r, g, b: as sorting the tuples)
    order = np.lexsort((b_, g_, r_, 2126 * r_ + 7152 * g_ + 722 * b_))
    top = px[order[len(px) * 3 // 4:]] if len(px) * 3 // 4 < len(px) else px
    n = len(top)
    r, g, b = (int(top[:, k].sum()) // n for k in range(3))
    # (the mean of the pixels' linear luminance: a lookup of the sRGB curve per 8 bits)
    lin = np.array([((c / 255.0) / 12.92 if c <= 10 else ((c / 255.0 + 0.055) / 1.055) ** 2.4)
                    for c in range(256)])
    # (an exact sum, not numpy's reduction: the same on every machine)
    y = math.fsum((0.2126 * lin[r_] + 0.7152 * lin[g_] + 0.0722 * lin[b_]).tolist()) / len(px)
    return f"#{r:02x}{g:02x}{b:02x}", round(y, 4)
