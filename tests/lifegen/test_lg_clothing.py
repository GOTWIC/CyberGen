"""LG2: the looks, the garments' drafts, the textiles, the plan's outfits and variety check."""

import json

import numpy as np

from lifegen import garments as G
from lifegen import library as L
from lifegen import plan as PL
from lifegen import presets as P
from lifegen import textiles as TX


def _body(height=1.70):
    """A plain body's bones as the editor exports them (cm, Unreal's frame)."""
    s = height / 1.70
    bones = {"root": (0, 0, 0), "pelvis": (0, 2, 87), "spine_01": (0, 2, 88.5),
             "spine_02": (0, 2.5, 92), "spine_03": (0, 3, 97), "spine_04": (0, 2.5, 105),
             "spine_05": (0, 0, 117.5), "neck_01": (0, -2.5, 131.5), "neck_02": (0, -1.5, 136),
             "head": (0, -0.5, 141), "thigh_l": (9, 1.6, 83.5), "thigh_r": (-9, 1.6, 83.5),
             "calf_l": (11, 0.8, 44), "calf_r": (-11, 0.8, 44), "foot_l": (12.6, -0.7, 7),
             "foot_r": (-12.6, -0.7, 7), "upperarm_l": (13.4, -2.7, 124),
             "upperarm_r": (-13.4, -2.7, 124), "lowerarm_l": (28.6, -2, 104),
             "lowerarm_r": (-28.6, -2, 104), "hand_l": (40, 12, 90.5), "hand_r": (-40, 12, 90.5)}
    return {"body": {"bones": [{"name": k, "t": [v[0] * s, v[1] * s, v[2] * s]}
                               for k, v in bones.items()]}}


def test_every_character_has_its_looks_one_group_each():
    chars = L.characters()
    groups = G.look_groups(len(chars))
    assert all(len(g) == G.LOOKS and len(set(g)) == G.LOOKS for g in groups)
    flat = [g for gs in groups for g in gs]
    for g, n in G.GROUP_LOOKS.items():
        assert flat.count(g) == n
    assert set(P.GROUPS) <= set(G.GROUPS)


def test_looks_are_deterministic_and_whole():
    chars = L.characters()
    a, b = G.spec(chars), G.spec(chars)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    kinds = set()
    for c, looks in zip(chars, a["looks"]):
        for lk in looks:
            layers = [G.KINDS[g["kind"]]["layer"] for g in lk["garments"]]
            kinds |= {g["kind"] for g in lk["garments"]}
            assert layers.count("base") == 1 and layers.count("shoes") == 1
            assert layers.count("outer") <= 1 and layers.count("bottom") <= 1
            # (coveralls are their own bottom; every other look has one)
            if not any(g["kind"] == "coveralls" for g in lk["garments"]):
                assert layers.count("bottom") == 1
            if c["body"] == "m" and lk["group"] != "nightlife":
                assert all(g["kind"] != "skirt" for g in lk["garments"])
            acc = [x["kind"] for x in lk["accessories"]]
            # (arm plates only on bare forearms; one hat at most; a hood or hat hides the hair)
            if "armplates" in acc:
                assert all(G.KINDS[g["kind"]].get("sleeve", 0) < 0.5 for g in lk["garments"]
                           if G.KINDS[g["kind"]]["layer"] in ("base", "outer"))
            assert sum(acc.count(h) for h in G.HIDES_HAIR) <= 1
            assert lk["hide_hair"] == (any(g.get("hood") == "up" for g in lk["garments"]) or
                                       any(h in acc for h in G.HIDES_HAIR))
            for g in lk["garments"]:
                assert g["textile"] in TX.TEXTILES
    # (the scope's garments all made)
    assert {"tee", "shirt", "hoodie", "bomber", "jacket", "trench", "cargo", "trousers",
            "skirt", "coveralls", "sneakers", "boots"} <= kinds


def test_drafts_are_cut_for_the_body_and_layered():
    m1, m2 = G.measure(_body(1.60)), G.measure(_body(1.85))
    assert m2["hip"] > m1["hip"] and m2["waist"] > m1["waist"]
    for kind in G.KINDS:
        rec = {"kind": kind, "textile": "knit", "channel": 0, "fit": 0.5, "length": 0.5}
        d1, d2 = G.draft(rec, m1, "a"), G.draft(rec, m2, "a")
        layer = G.KINDS[kind]["layer"]
        if layer == "shoes":
            assert m1["ankle"] < d1["top_z"] < m1["knee"]
            continue
        assert all(v > 0 for v in d1["ease"].values())
        zs1 = [c["z"] for c in d1["cuts"] if c["kind"] == "z"]
        zs2 = [c["z"] for c in d2["cuts"] if c["kind"] == "z"]
        # (cut by the body: a taller body's lines are higher)
        assert all(b > a for a, b in zip(zs1, zs2))
        if layer in ("base", "outer") and kind != "coveralls":
            assert d1["z"]["hem"] < m1["waist"]          # a top reaches past the waist
        if layer == "bottom":
            top = max(c["z"] for c in d1["cuts"] if c.get("keep") == "below")
            assert top > m1["waist"]                     # a bottom's waistband over it
    # (an outer layer is cut looser than any base layer it goes over)
    base_max = max(G.draft({"kind": k, "textile": "knit", "fit": 1.0}, m1, "b")["ease"]["torso"]
                   for k in ("tee", "longtee", "shirt"))
    outer_min = min(G.draft({"kind": k, "textile": "nylon", "fit": 0.0}, m1, "o")["ease"]["torso"]
                    for k in ("bomber", "jacket", "trench", "raincoat"))
    assert outer_min > base_max


def test_blender_job_drapes_each_garment_once():
    chars = L.characters()
    looks = G.spec(chars)["looks"][0]
    job = G.blender_job(chars[0], looks, "body.json", "out", _body())
    ids = [g["id"] for g in job["garments"]]
    assert len(ids) == len(set(ids))
    used = {gid for lk in job["looks"] for gid in lk["garments"]}
    assert used == set(ids)
    assert [lk["id"] for lk in job["looks"]] == [lk["id"] for lk in looks]
    assert set(job["glow"]) <= set(TX.TEXTILES)


def test_textiles_tile_and_are_deterministic():
    for name in TX.TEXTILES:
        s = TX.surface(name, 64)
        assert np.array_equal(s.color, TX.surface(name, 64).color)
        # (tileable: no edge across the seam sharper than the weave's own sharpest, either way)
        for a in (s.height, s.height.T):
            seam = float(np.abs(a[:, 0] - a[:, -1]).mean())
            inner = float(np.abs(np.diff(a, axis=1)).mean(axis=0).max())
            assert seam <= inner + 1e-3, name
    rec = TX.record()
    for name, t in rec["textiles"].items():
        if t["dyed"]:
            assert min(t["mean"]) > 0.5          # a dyed weave is light: the dye colors it


def test_plan_outfits_by_district_and_weather():
    filled = {"crowd": {"weather": "clear"},
              "districts": {"d1": {"style": {"groups": {"street": 0.5, "corporate": 0.5}}},
                            "d2": {"style": {"groups": {"industrial": 1.0}}}}}
    g = PL.outfit_groups(filled)
    assert abs(sum(g["d1"]) - 1.0) < 1e-6 and g["d1"][G.GROUPS.index("rain")] == 0.0
    filled["crowd"]["weather"] = "rain"
    g = PL.outfit_groups(filled)
    assert abs(g["d2"][G.GROUPS.index("rain")] - P.WEATHER_OUTFITS["rain"]) < 1e-6
    pal = PL.outfit_palettes({"factions": [{"kind": "gang", "home_district_id": "d1",
                                            "color": "#00ff00"}]}, filled)
    for d, rows in pal.items():
        assert len(rows) == len(G.GROUPS)
        for cols in rows:
            assert len(cols) == len(set(cols))           # distinct colors
    assert pal["d1"][G.GROUPS.index("gang")][0] == "#00ff00"


def test_looks_assigned_by_group_and_variety_check():
    n = L.CHARACTERS
    persons = {k: [] for k in PL.CROWD_COLUMNS}
    for k in range(600):
        p = PL.draw_person(("t", k), n, palette=[0] * 4)
        for c in PL.CROWD_COLUMNS:
            persons[c].append(p[c])
    mix = [1.0 if g in ("street", "industrial") else 0.0 for g in G.GROUPS]
    looks, groups = PL.assign_looks(persons, mix)
    spec = G.spec(L.characters(n))["looks"]
    for lk, gi, c in zip(looks, groups, persons["character"]):
        assert lk // G.LOOKS == c
        assert spec[c][lk % G.LOOKS]["group"] == G.GROUPS[gi]
    # (with a character holding neither group, any of its looks)
    assert sum(1 for gi in groups if G.GROUPS[gi] in ("street", "industrial")) > 0.8 * len(groups)
    persons["look"], persons["group"] = looks, groups
    filled = {"crowd": {"weather": "clear"},
              "districts": {"d1": {"style": {"groups": {"street": 1.0}}}}}
    crowd = {"persons": persons, "pool": 600, "live_m": 340.0,
             "outfits": {"groups": list(G.GROUPS), "district_groups": PL.outfit_groups(filled),
                         "palettes": PL.outfit_palettes({}, filled)}}
    rows = [{"district_id": "d1", "tile": "t0", "people": [5.0] * 5}]
    ok = PL.variety_checks(rows, crowd)["variety"]
    assert ok["ok"], ok
    rows = [{"district_id": "d1", "tile": "t0", "people": [5e5] * 5}]
    crowd["pool"] = 10 ** 6
    assert not PL.variety_checks(rows, crowd)["variety"]["ok"]


def test_library_hash_covers_the_clothing():
    spec = L.spec()
    assert spec["version"].startswith("lg2")
    assert len(spec["looks"]) == L.CHARACTERS
    assert all(len(ls) == G.LOOKS for ls in spec["looks"])
    assert "lifegen/garments.py" in L.CODE_FILES and "lifegen/blender/garments.py" in L.CODE_FILES
