"""AG15: every building lit its own way at night (scope 14.16).

The genome's `extra.night` holds a building's schedule (by use: offices, homes, hotels,
shops, industrial, a share of towers vacant), its light's color temperature (`color`, linear
RGB), how far its rooms' temperatures spread (`spread`) and an office's band of floors
(`band`); `extra.lit` is its lit share in the evening. The masters (Unreal's `M_CgGlass`,
Blender's `glass`) light each room of the building's room grid from these, Custom Primitive
Data 30 to 35 (`CPD`), at `MPC_CityGen`'s Hour:

$$\\text{lit}(c) = [h(c) < s \\cdot k_{\\text{sched}}(\\text{band}(\\text{Hour}))]$$

with h a hash of the room (an office's of its band of floors, then its room), s the lit
share and k the schedule's share by hour band (`HOURS`, `model.HOUR_BANDS`: night 0 to 6,
morning 6 to 10, day 10 to 16, evening 16 to 20, late 20 to 24). A lit room's color is the
building's light pulled toward warm or cool by a hash times `spread`; hotels warm, offices
in bands of floors, homes scattered, shops brighter low down, vacant towers a few security
lights. `lit_cells` is the same rule in Python for the night thumbnails (`thumb.py`).
"""

from __future__ import annotations

import hashlib

# per schedule (systems.SCHEDULES' codes) the share of the evening's lit rooms lit in each
# hour band: night, morning, day, evening, late
HOURS = {0: (0.5, 0.6, 0.3, 1.0, 0.8), 1: (0.12, 0.7, 0.9, 1.0, 0.35),
         2: (0.15, 0.6, 0.25, 0.9, 1.0), 3: (0.45, 0.6, 0.35, 0.9, 1.0),
         4: (0.2, 0.6, 0.9, 1.0, 0.8), 5: (0.6, 0.8, 0.9, 0.9, 0.7),
         6: (0.5, 0.5, 0.5, 0.5, 0.5)}
HOUR_DEFAULT = 21.0           # MPC_CityGen's Hour by default: the late band
CPD = {"color": 30, "schedule": 33, "spread": 34, "band": 35}
CPD_LAYOUT = {"30-32": "night light color (linear RGB)",
              "33": "night schedule (0 default, 1 office, 2 home, 3 hotel, 4 shop, "
                    "5 industrial, 6 vacant)",
              "34": "color temperature spread", "35": "office band of floors"}
WARM = (1.0, 0.62, 0.32)
COOL = (0.7, 0.85, 1.0)


def band_of(hour: float) -> int:
    h = hour % 24.0
    return 0 if h < 6 else (1 if h < 10 else (2 if h < 16 else (3 if h < 20 else 4)))


def cpd(gm: dict) -> list[float]:
    """Custom Primitive Data 30 to 35 of a building (its night)."""
    from . import systems as SY
    n = (gm.get("extra") or {}).get("night")
    if not n:
        return [1.0, 0.88, 0.74, 0.0, 0.3, 3.0]
    return [float(n["color"][0]), float(n["color"][1]), float(n["color"][2]),
            float(SY.SCHEDULES[n["schedule"]]), float(n["spread"]), float(n["band"])]


def _h(seed: float, a: int, b: int, salt: str) -> float:
    d = hashlib.blake2b(f"{seed:.4f}|{a}|{b}|{salt}".encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(d, "little") / 2.0 ** 64


def lit(seed: float, share: float, sched: int, band: int, col: int, floor: int,
        hour: float = HOUR_DEFAULT) -> float:
    """How bright room (col, floor) of a building is lit (0 dark, else 0.35 to 1)."""
    k = HOURS.get(sched, HOURS[0])[band_of(hour)]
    s = share * k
    if sched == 6:                                  # vacant: a few security lights
        s = 0.04
    if sched == 1:                                  # offices: a band of floors on or off
        hb = _h(seed, 0, floor // max(band, 1), "band")
        if hb >= min(s * 1.25, 1.0):
            return 0.0
        h = _h(seed, col, floor, "room")
        return 0.0 if h >= 0.85 else 0.55 + 0.45 * _h(seed, col, floor, "lamp")
    if sched == 4 and floor <= 2:                   # shops: the low floors lit
        s = min(1.0, s * 1.6)
    h = _h(seed, col, floor, "room")
    if h >= s:
        return 0.0
    return 0.35 + 0.65 * _h(seed, col, floor, "lamp")
