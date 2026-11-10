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
                      "yaw": math.degrees(a) + 180.0, "size": [w, h]})
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

    def color(self, slot_id: str) -> str | None:
        cell_id = (self.data.get("slots") or {}).get(slot_id)
        if cell_id is None:
            return None
        if cell_id in self.cache:
            return self.cache[cell_id]
        cell = (self.data.get("cells") or {}).get(cell_id) or {}
        col = cell.get("color")
        if col is None and cell.get("page"):
            img = self._page(cell["page"])
            if img is not None:
                col = _mean_bright(img, cell["uv"])
                self.from_pages += 1
        self.cache[cell_id] = col
        return col


def _mean_bright(img, uv) -> str | None:
    """The mean color of a page cell's brightest quarter of pixels (what glows), as
    #rrggbb, integer arithmetic only."""
    W, H = img.size
    x0, y0 = int(uv[0] * W), int(uv[1] * H)
    x1, y1 = max(x0 + 1, int(uv[2] * W)), max(y0 + 1, int(uv[3] * H))
    px = list(img.crop((x0, y0, x1, y1)).getdata())
    if not px:
        return None
    lum = sorted(((2126 * r + 7152 * g + 722 * b), r, g, b) for r, g, b in px)
    top = lum[len(lum) * 3 // 4:] or lum
    n = len(top)
    r = sum(t[1] for t in top) // n
    g = sum(t[2] for t in top) // n
    b = sum(t[3] for t in top) // n
    return f"#{r:02x}{g:02x}{b:02x}"
