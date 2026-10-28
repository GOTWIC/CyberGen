"""Material slots of the props, plants and signs, and the masters they map to in Unreal.

A slot is a material instance: its master, a flat color (sRGB hex), roughness and metallic.
AG6's library gives them textures (bark, leaves, painted metal, sign faces, billboard
content); until then flat colors carry the look, emissive slots (lamps, neon, screens, lit
sign faces) glow. Neon colors are slots of their own, named by color (`neon.ff2a6d`), so a
district's neon palette in the asset spec makes the slots it needs.

Masters: `opaque`, `metal`, `foliage` (two-sided), `emissive` (lamps, screens), `neon`
(tubes and lit faces, brighter), `translucent` (bus shelter and kiosk glass where it is a
separate non-Nanite mesh) and `holo` (holo-ads: translucent, two-sided, emissive).
"""

from __future__ import annotations

MASTERS = ("opaque", "metal", "foliage", "emissive", "neon", "translucent", "holo")

SLOTS: dict[str, tuple[str, str, float, float]] = {
    # metals
    "metal.dark": ("metal", "#2a2d31", 0.5, 0.8),
    "metal.black": ("metal", "#18191b", 0.45, 0.7),
    "metal.galv": ("metal", "#8c9298", 0.45, 0.9),
    "metal.steel": ("metal", "#6a6f75", 0.4, 1.0),
    "metal.chrome": ("metal", "#c9cdd2", 0.15, 1.0),
    "metal.white": ("metal", "#d9dbdc", 0.4, 0.3),
    "metal.green": ("metal", "#24412f", 0.55, 0.6),
    "metal.rust": ("metal", "#6e3a22", 0.85, 0.4),
    "metal.yellow": ("metal", "#c99a1e", 0.55, 0.4),
    "metal.red": ("metal", "#9a2620", 0.5, 0.4),
    "metal.blue": ("metal", "#22406a", 0.5, 0.4),
    "metal.bronze": ("metal", "#6b5233", 0.5, 0.9),
    # mineral, wood, plastics
    "concrete": ("opaque", "#8f8c86", 0.9, 0.0),
    "concrete.dark": ("opaque", "#5d5a55", 0.9, 0.0),
    "stone": ("opaque", "#9a958b", 0.8, 0.0),
    "wood": ("opaque", "#6b4a32", 0.8, 0.0),
    "wood.light": ("opaque", "#a07a52", 0.8, 0.0),
    "wood.red": ("opaque", "#8a2a1e", 0.7, 0.0),
    "plastic.green": ("opaque", "#2f5f36", 0.6, 0.0),
    "plastic.blue": ("opaque", "#2a5384", 0.6, 0.0),
    "plastic.grey": ("opaque", "#5a5e63", 0.6, 0.0),
    "plastic.black": ("opaque", "#1d1e20", 0.55, 0.0),
    "plastic.orange": ("opaque", "#d8641c", 0.6, 0.0),
    "plastic.white": ("opaque", "#dedcd6", 0.5, 0.0),
    "plastic.red": ("opaque", "#b3261e", 0.55, 0.0),
    "plastic.yellow": ("opaque", "#e0b31c", 0.55, 0.0),
    "rubber": ("opaque", "#161616", 0.9, 0.0),
    "glass.prop": ("metal", "#5f7f8c", 0.06, 0.3),
    "glass.dark": ("metal", "#1b252c", 0.08, 0.4),
    "fabric.red": ("opaque", "#8c2321", 0.9, 0.0),
    "fabric.green": ("opaque", "#24503a", 0.9, 0.0),
    "fabric.blue": ("opaque", "#22406e", 0.9, 0.0),
    "fabric.orange": ("opaque", "#c4561e", 0.9, 0.0),
    "fabric.cream": ("opaque", "#d8cfb4", 0.9, 0.0),
    "fabric.black": ("opaque", "#1c1c1f", 0.9, 0.0),
    "fabric.purple": ("opaque", "#4f2a6b", 0.9, 0.0),
    "fabric.tarp": ("opaque", "#2f5a8a", 0.85, 0.0),
    "net.debris": ("opaque", "#3b6a5a", 0.95, 0.0),
    "bag.black": ("opaque", "#141416", 0.4, 0.0),
    "cardboard": ("opaque", "#9a7a52", 0.95, 0.0),
    "paint.white": ("opaque", "#e3e1da", 0.6, 0.0),
    # vehicles and boats
    "car.red": ("metal", "#8e1b1b", 0.3, 0.6),
    "car.white": ("metal", "#d8d8d4", 0.3, 0.5),
    "car.black": ("metal", "#121315", 0.25, 0.6),
    "car.silver": ("metal", "#8c9095", 0.3, 0.8),
    "car.blue": ("metal", "#1d3a6b", 0.3, 0.6),
    "car.yellow": ("metal", "#d9a40f", 0.35, 0.5),
    "car.teal": ("metal", "#1d6b6b", 0.3, 0.6),
    "car.olive": ("metal", "#4a5230", 0.45, 0.4),
    "hull.white": ("opaque", "#e6e6e0", 0.5, 0.0),
    "hull.blue": ("opaque", "#1f3e66", 0.5, 0.0),
    "hull.red": ("opaque", "#7a1f1a", 0.55, 0.0),
    # lights and screens
    "light.warm": ("emissive", "#fff0d2", 0.3, 0.0),
    "light.cool": ("emissive", "#d8ecff", 0.3, 0.0),
    "light.sodium": ("emissive", "#ffb04a", 0.3, 0.0),
    "light.red": ("emissive", "#ff2b1c", 0.3, 0.0),
    "light.amber": ("emissive", "#ffa31a", 0.3, 0.0),
    "light.green": ("emissive", "#2bff8a", 0.3, 0.0),
    "screen.cyan": ("emissive", "#3fd0ff", 0.2, 0.0),
    "screen.magenta": ("emissive", "#ff3fc0", 0.2, 0.0),
    "screen.white": ("emissive", "#f2f2ff", 0.2, 0.0),
    "screen.amber": ("emissive", "#ffb84a", 0.2, 0.0),
    # plants
    "bark.dark": ("opaque", "#3b2f26", 0.95, 0.0),
    "bark.grey": ("opaque", "#6b665c", 0.95, 0.0),
    "bark.plane": ("opaque", "#7f7a62", 0.95, 0.0),
    "bark.birch": ("opaque", "#dcd8cc", 0.85, 0.0),
    "bark.palm": ("opaque", "#7a6650", 0.95, 0.0),
    "bark.ginkgo": ("opaque", "#5a4d40", 0.95, 0.0),
    "leaf.plane": ("foliage", "#4d6a2c", 0.8, 0.0),
    "leaf.maple": ("foliage", "#5b7b28", 0.8, 0.0),
    "leaf.ginkgo": ("foliage", "#8a9b2a", 0.8, 0.0),
    "leaf.birch": ("foliage", "#6d8c38", 0.8, 0.0),
    "leaf.linden": ("foliage", "#4a6b2c", 0.8, 0.0),
    "leaf.elm": ("foliage", "#3e5f28", 0.8, 0.0),
    "leaf.oak": ("foliage", "#3b5824", 0.8, 0.0),
    "leaf.ficus": ("foliage", "#2c5426", 0.6, 0.0),
    "leaf.pine": ("foliage", "#28452a", 0.85, 0.0),
    "leaf.palm": ("foliage", "#4d6b2e", 0.7, 0.0),
    "leaf.boxwood": ("foliage", "#2e4e22", 0.8, 0.0),
    "leaf.sedum": ("foliage", "#7a8a36", 0.8, 0.0),
    "leaf.sedum_red": ("foliage", "#8a4a32", 0.8, 0.0),
    "leaf.ivy": ("foliage", "#2c4c20", 0.7, 0.0),
    "leaf.scrub": ("foliage", "#5e6c32", 0.9, 0.0),
    "leaf.dry": ("foliage", "#8a7a46", 0.9, 0.0),
    "soil": ("opaque", "#3a2e24", 0.95, 0.0),
    # signs
    "sign.face": ("opaque", "#1a1b20", 0.5, 0.0),
    "sign.box": ("metal", "#2a2c31", 0.45, 0.6),
    "sign.frame": ("metal", "#3a3d42", 0.4, 0.8),
    "sign.back": ("opaque", "#121316", 0.7, 0.0),
    "sign.white": ("neon", "#f4f1ea", 0.3, 0.0),
    "billboard.lamp": ("emissive", "#fff4dc", 0.3, 0.0),
    "holo.base": ("metal", "#202429", 0.35, 0.8),
}

# neon colors (decision 13.3: generated; a district's `neon_palette` adds its own)
NEON = ("#ff2a6d", "#05d9e8", "#b967ff", "#ffb000", "#39ff8a", "#ff3b30", "#2d6bff",
        "#f0f0ff", "#ff7a1a", "#ff4fd8")
NEON_ERA = {"heritage": ("#ff3b30", "#ffb000", "#39ff8a", "#ff4fd8", "#f0f0ff"),
            "neon_retro": ("#ff2a6d", "#05d9e8", "#b967ff", "#ff4fd8", "#39ff8a", "#ffb000"),
            "corporate_glass": ("#05d9e8", "#f0f0ff", "#2d6bff", "#b967ff"),
            "clean_tech": ("#05d9e8", "#f0f0ff", "#39ff8a"),
            "industrial": ("#ff7a1a", "#ffb000", "#ff3b30", "#f0f0ff"),
            "brutalist": ("#ff2a6d", "#05d9e8", "#ffb000", "#f0f0ff"),
            "transit_modern": ("#05d9e8", "#ffb000", "#f0f0ff", "#2d6bff"),
            "suburban_modern": ("#ffb000", "#f0f0ff", "#39ff8a"),
            "mixed_modern": ("#ff2a6d", "#05d9e8", "#ffb000", "#b967ff", "#39ff8a"),
            "aerospace": ("#05d9e8", "#f0f0ff", "#ff7a1a")}


def neon_slot(hexcolor: str) -> str:
    """The slot of a neon color, made on demand (`slot_spec`)."""
    return "neon." + hexcolor.lstrip("#").lower()


def holo_slot(hexcolor: str) -> str:
    return "holo." + hexcolor.lstrip("#").lower()


def face_slot(hexcolor: str) -> str:
    """A lit sign face or billboard content color (neon master, dimmer than a tube)."""
    return "lit." + hexcolor.lstrip("#").lower()


def slot_spec(name: str) -> tuple[str, str, float, float]:
    if name in SLOTS:
        return SLOTS[name]
    if name.endswith(".d") and name[:-2] in SLOTS:
        # the darker tone of a slot (inner leaves)
        master, color, rough, metal = SLOTS[name[:-2]]
        h = color.lstrip("#")
        dark = "#" + "".join(f"{int(int(h[k:k + 2], 16) * 0.62):02x}" for k in (0, 2, 4))
        return (master, dark, rough, metal)
    pre, _, h = name.partition(".")
    if pre == "neon":
        return ("neon", "#" + h, 0.3, 0.0)
    if pre == "lit":
        return ("emissive", "#" + h, 0.4, 0.0)
    if pre == "holo":
        return ("holo", "#" + h, 0.1, 0.0)
    raise KeyError(name)


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear(hexcolor: str) -> tuple[float, float, float]:
    h = hexcolor.lstrip("#")
    return tuple(round(_lin(int(h[k:k + 2], 16) / 255.0), 4) for k in (0, 2, 4))


def gltf_materials(g, names) -> dict[str, int]:
    """Add the slots used (sorted) to a glTF document (linear base colors, emissive slots
    with their color as emissiveFactor, foliage and holo two-sided, holo blended)."""
    out = {}
    for n in sorted(set(names)):
        master, color, rough, metal = slot_spec(n)
        lin = linear(color)
        i = g.material(n, lin + (1.0,), metallic=metal, roughness=rough,
                       extras={"master": master})
        mat = g.materials[i]
        if master in ("emissive", "neon", "holo"):
            mat["emissiveFactor"] = [float(v) for v in lin]
        if master in ("foliage", "holo", "translucent"):
            mat["doubleSided"] = True
        if master in ("holo", "translucent"):
            mat["alphaMode"] = "BLEND"
            mat["pbrMetallicRoughness"]["baseColorFactor"][3] = 0.45 if master == "holo" \
                else 0.3
        out[n] = i
    return out


def contribution_materials(names) -> dict:
    """The contribution's materials: linear colors (the exporter takes them as they are)."""
    out = {}
    for n in sorted(set(names)):
        master, color, rough, metal = slot_spec(n)
        out[n] = {"master": master, "color": list(linear(color)), "roughness": rough,
                  "metallic": metal}
        if master == "foliage":
            out[n]["two_sided"] = True
    return out
