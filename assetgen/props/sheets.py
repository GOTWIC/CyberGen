"""Variant sheets (scope 14.9, "Shows"): one per district style with every prop kind's
variants and sample signs of that style (facade lightbox, panel and neon shop signs, blade
signs, a neon band, a billboard and a holo-ad), and one of the plant species; rendered by
`assetgen/blender/props_sheet.py` from a build's family packs.

`assetgen props BUILD --sheets DIR` writes `sheet_<style>.jpg` and `sheet_plants.jpg`.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .. import __version__
from ..gltf import Gltf, quat_z
from . import materials as MT
from . import signs as SG
from . import styles as ST

PROP_ORDER = ("street_light", "wall_light", "traffic_signal", "bus_stop", "bench", "trash_can",
              "hydrant", "bollard", "kiosk", "vending_machine", "food_stall", "planter",
              "barrier", "railing", "awning", "ac_unit", "dumpster", "trash", "parked_vehicle",
              "boat", "bracket")


def sign_samples(style: str) -> list[tuple[str, dict, float]]:
    """(node name, inputs, yaw so the face looks south at the sheet's camera) of a style's
    sample signs, four of each look."""
    pal = list(MT.NEON_ERA[{"sleek": "corporate_glass", "civic": "mixed_modern",
                            "heavy": "industrial", "neon": "neon_retro",
                            "old": "heritage"}[style]])
    script = {"sleek": "kana", "civic": "hanzi", "heavy": "hangul", "neon": "kana",
              "old": "hanzi"}[style]
    uses = ("food", "bar", "cyberware", "pawn")
    out = []
    for k in range(4):
        c1, c2 = pal[k % len(pal)], pal[(k + 1) % len(pal)]
        base = {"colors": [c1, c2], "face": c2 if k % 2 else SG.FACE_COLORS[k],
                "style": style}
        text = SG.shop_text(uses[k], None, "sheet", style, k)
        for look in ("lightbox", "panel", "neon"):
            out.append((f"sign.{style}.facade_{look}.v{k}",
                        {**base, "kind": "shop_sign", "mount": "facade", "w": 3.6, "h": 0.9,
                         "text": text, "script": script, "glyphs": 3, "look": look}, -90.0))
        for look in ("lightbox", "neon"):
            out.append((f"sign.{style}.blade_{look}.v{k}",
                        {**base, "kind": "shop_sign", "mount": "blade", "w": 1.2, "h": 3.2,
                         "text": text.split()[-1], "script": script, "glyphs": 3,
                         "look": look}, 0.0))
        out.append((f"sign.{style}.band.v{k}",
                    {**base, "kind": "neon", "mount": "facade", "w": 1.2, "h": 8.0,
                     "text": SG.BAND_WORDS[k + 2 * len(style)], "script": "latin"}, -90.0))
        out.append((f"sign.{style}.billboard.v{k}",
                    {**base, "kind": "billboard", "mount": "roof", "w": 7.0, "h": 3.2,
                     "text": "NIMBUS" if k % 2 else "ORISON SKY", "sub": "DRINK NOVA",
                     "two_sided": True, "script": "latin", "logo_right": bool(k % 2)}, -90.0))
    return out


def signs_glb(style: str) -> bytes:
    meshes = []
    for name, inp, yaw in sign_samples(style):
        m, extra = SG.make(inp)
        for ex in extra:
            m2 = ex["lods"][0]
            meshes.append((name + ".holo", m2, yaw))
        meshes.append((name, m, yaw))
    g = Gltf(generator=f"assetgen {__version__} props sheet")
    slots = set()
    for _, m, _ in meshes:
        slots |= set(m.slots)
    mats = MT.gltf_materials(g, slots)
    for name, m, yaw in meshes:
        g.node(name, g.mesh(name, m.finish(mats)), rotation=quat_z(yaw), root=True)
    return g.to_glb()


def render(assets: Path, out: Path, blender: str | None = None, width: int = 2400) -> list:
    from citygen.blockout import find_blender
    exe = find_blender(blender)
    if exe is None:
        raise RuntimeError("no Blender (set BLENDER)")
    script = Path(__file__).resolve().parent.parent / "blender" / "props_sheet.py"
    out.mkdir(parents=True, exist_ok=True)
    variants = sorted((assets / "props" / "variants").glob("*.glb"))
    plants = sorted((assets / "props" / "plants").glob("*.glb"))
    done = []
    with tempfile.TemporaryDirectory(prefix="ag8_sheet_") as tmp:
        for st in ST.STYLES:
            sg = Path(tmp) / f"signs_{st}.glb"
            sg.write_bytes(signs_glb(st))
            match = []
            for k in PROP_ORDER:
                match += ["--match", f"prop.{k}.{st}."]
            for look in ("facade_lightbox", "facade_panel", "facade_neon", "blade_lightbox",
                         "blade_neon", "band", "billboard"):
                match += ["--match", f"sign.{st}.{look}"]
            path = out / f"sheet_{st}.jpg"
            subprocess.run([str(exe), "-b", "--factory-startup", "-P", str(script), "--",
                            str(path)] + [str(v) for v in variants] + [str(sg)] + match +
                           ["--width", str(width)],
                           check=True, capture_output=True)
            done.append(path)
        path = out / "sheet_plants.jpg"
        subprocess.run([str(exe), "-b", "--factory-startup", "-P", str(script), "--", str(path)]
                       + [str(p) for p in plants] + ["--width", str(width)],
                       check=True, capture_output=True)
        done.append(path)
    return done
