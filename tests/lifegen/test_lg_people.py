"""LG1: the people library's spec (`lifegen/library.py`), the plan's person draws, and the
exporter's packing of people (`citygen/unreal_life.py`) and of the library in the project
(`citygen/unreal_people.py`; people_idles: the places' idles and transitions), without Unreal."""

import json
from pathlib import Path

from lifegen import library as L
from lifegen import presets as P

ROOT = Path(__file__).resolve().parents[2]


def test_characters_are_deterministic_and_plausible():
    a, b = L.characters(), L.characters()
    assert a == b and len(a) == L.CHARACTERS
    ids = [c["id"] for c in a]
    assert len(set(ids)) == len(ids)
    for c in a:
        assert L.HEIGHT_RANGE[0] <= c["height_cm"] <= L.HEIGHT_RANGE[1]
        assert c["preset"] != c["face_with"]
        # (a face is blended within its body)
        body = dict(L.PRESETS)
        assert body[c["preset"]] == body[c["face_with"]] == c["body"]
        assert L.FACE_BLEND[0] <= c["face_blend"] <= L.FACE_BLEND[1]
        assert all(abs(v) <= L.BUILD[k] for k, v in c["build"].items())
        assert L.SKIN_U[0] <= c["skin"][0] <= L.SKIN_U[1]
    # (the presets' hair and wardrobe go round in turn)
    assert len({c["preset"] for c in a}) == min(L.CHARACTERS, len(L.PRESETS))


def test_library_hash_follows_spec_and_engine():
    h = L.library_hash()
    assert h == L.library_hash() and len(h) == 16
    assert L.library_hash(engine="5.8.4") != h
    assert L.library_hash(L.CHARACTERS - 1) != h


def test_person_draws():
    pal = ["#112233", "#445566", "#778899"]
    ps = [L.person(("lg1.person", "d04", k), L.CHARACTERS, palette=pal) for k in range(2000)]
    assert ps[0] == L.person(("lg1.person", "d04", 0), L.CHARACTERS, palette=pal)
    chars = [p["character"] for p in ps]
    assert set(chars) == set(range(L.CHARACTERS))
    assert max(chars.count(k) for k in set(chars)) / len(ps) < 0.12
    for p in ps[:200]:
        assert L.PACE[0] <= p["pace"] <= L.PACE[1]
        assert L.PERSON_SCALE[0] <= p["scale"] <= L.PERSON_SCALE[1]
        assert 0 <= p["gait"] < len(L.WALKS) and 0 <= p["tint"] < len(pal)
        assert 0 <= p["seed"] < 2 ** 32
    assert len({p["seed"] for p in ps}) > 1990


def test_crowd_draws_heavy_builds_rarely():
    """lifegen_people_fixes: the plan draws a person's character by its preset's body weight
    (`presets.BODY_WEIGHT`): heavy builds about 5% of a crowd, every character still drawn,
    the other draws `library.person`'s; the library's hash does not move with it."""
    from lifegen import plan as PL
    from lifegen import presets as P
    n = L.CHARACTERS
    ps = [PL.draw_person(("lg3.person", k), n, palette=[0] * 4) for k in range(4000)]
    assert ps[7] == PL.draw_person(("lg3.person", 7), n, palette=[0] * 4)
    base = L.person(("lg3.person", 7), n, palette=[0] * 4)
    assert {k: v for k, v in ps[7].items() if k != "character"} == \
        {k: v for k, v in base.items() if k != "character"}
    chars = [p["character"] for p in ps]
    assert set(chars) == set(range(n))
    heavy = {k for k in range(n) if L.character(k)["preset"] in P.BODY_WEIGHT}
    assert len(heavy) == 6
    share = sum(1 for c in chars if c in heavy) / len(chars)
    assert 0.02 < share < 0.08
    assert max(chars.count(k) for k in range(n)) / len(chars) < PL.PEOPLE_SHARE_MAX
    w = PL.character_weights(n)
    assert sum(1 for v in w if v < 1.0) == 6 and min(w) > 0.0


def _lib(n):
    return {"hash": "abc", "walks": list(L.WALKS), "idles": ["idle_neutral"],
            "clips": {"walk_neutral": {"anim": "/Game/CityGen/People/Anim/A_walk_neutral",
                                       "speed": 1.4},
                      "walk_relaxed": {"anim": "/Game/CityGen/People/Anim/A_walk_relaxed",
                                       "speed": 1.2},
                      "idle_neutral": {"anim": "/Game/CityGen/People/Anim/A_idle_neutral",
                                       "speed": 0.0}},
            "far": {"card": "/Game/CityGen/People/Far/SM_Card", "size": [1.0, 2.0]},
            "tiers": dict(L.TIERS),
            "characters": [{"id": f"p{k:02d}",
                            "near": {"meshes": [f"/Game/B/{k}/body", f"/Game/B/{k}/face"]},
                            "mid": {"mesh": f"/Game/M/SM_{k}", "start": 0, "end": 29, "fps": 15.0,
                                    "cycle_s": 2.0},
                            "far": {"material": f"/Game/F/MI_{k}"}} for k in range(n)]}


def test_exporter_packs_persons_and_library():
    from citygen import unreal_life as UL
    spike = {"palette": ["#ff0000", "#00ff00"],
             "library": {"characters": 3, "walks": list(L.WALKS), "tiers": {"near_max": 99}},
             "persons": {"seed": [1, 2 ** 32 - 1], "character": [0, 2], "scale": [1.0, 0.98],
                         "gait": [0, 1], "pace": [1.3, 1.4], "tint": [1, 0]}}
    p = UL.persons(spike)
    assert p["person_char"] == [0, 2] and p["person_seed"] == [1, -1]
    assert p["person_tint"][:3] == [0.0, 1.0, 0.0] and len(p["person_tint"]) == 6
    lib = UL.people_library(_lib(3), spike)
    assert lib["near_mesh_starts"] == [0, 2, 4, 6] and len(lib["near_meshes"]) == 6
    assert lib["mid_frames"][:4] == [0.0, 29.0, 15.0, 2.0]
    assert lib["walk_clip_speeds"] == [1.4, 1.2] and lib["tiers"]["near_max"] == 99
    # (a library whose characters are not the plan's: the stand-ins, and why)
    assert "people_skipped" in UL.people_library(_lib(2), spike)
    assert UL.people_library(None, spike) == {} and UL.persons({}) == {}
    # (LG2: a library of looks; the plan's persons wear looks, the unit the runtime draws)
    lib3 = {**_lib(3), "looks": True}
    spike2 = {**spike, "library": {**spike["library"], "characters": 1, "looks": 3},
              "persons": {**spike["persons"], "look": [2, 1], "group": [0, 3]}}
    p2 = UL.persons(spike2)
    assert p2["person_char"] == [2, 1] and p2["person_group"] == [0, 3]
    assert UL.people_library(lib3, spike2)["near_mesh_starts"] == [0, 2, 4, 6]


def _places(n, looks=True):
    """A places' manifest (`unreal_people.ensure_place_clips`) for `_lib(n)`'s one group."""
    g = {"sit": {"anim": "/Game/A/A_place_sit", "length_s": 25.0},
         "run": {"anim": "/Game/A/A_place_run", "travel_cm": [0.0, 1167.0], "length_s": 2.5}}
    for k, c in enumerate(P.SIT_IN):
        g[c] = {"anim": f"/Game/A/A_place_{c}", "other_cm": [10.0 * k, -80.0],
                "other_yaw": 180.0 - 30.0 * k, "length_s": 2.0 + 0.1 * k}
    g["sit_out"] = {"anim": "/Game/A/A_place_sit_out", "other_cm": [0.0, 120.0],
                    "other_yaw": 5.0, "length_s": 2.4}
    man = {"hash": "pl", "lib_hash": "abc", "clips": list(P.PLACE_CLIPS), "groups": {"s0": g}}
    if looks:
        man["idles"] = {"key": "k1", "card": {"views": 8, "rows": 16, "walk": [0, 8],
                                              "sit": [8, 4], "idle": [12, 4]},
                        "looks": {f"p{k:02d}": {
                            "mid": {"materials": [f"/Game/I/MI_{k}_0", f"/Game/I/MI_{k}_1"],
                                    "walk": [0, 59], "idle": [60, 149], "sit": [150, 269]},
                            "far": {"material": f"/Game/I/MI_{k}_CardIdle"}} for k in range(n)}}
    return man


def test_exporter_packs_the_idles():
    """people_idles: the places' second mid bakes, still cards and the bench's transitions
    reach the life controller's data; a manifest without them (or not for every look) leaves
    the library's walk and cards as they were."""
    from citygen import unreal_life as UL
    spike = {"library": {"characters": 3, "walks": list(L.WALKS)},
             "persons": {"seed": [1], "character": [0], "scale": [1.0], "gait": [0],
                         "pace": [1.3], "tint": [0]}}
    lib = UL.people_library({**_lib(3), "place_clips": _places(3)}, spike)
    assert lib["mid_still_frames"] == [60.0, 149.0, 150.0, 269.0] * 3
    assert lib["mid_idle_starts"] == [0, 2, 4, 6] and len(lib["mid_idle_materials"]) == 6
    assert lib["card_materials"] == [f"/Game/I/MI_{k}_CardIdle" for k in range(3)]
    assert lib["card_cells"] == [0.0, 8.0, 8.0, 4.0, 12.0, 4.0]
    assert lib["sit_in_count"] == len(P.SIT_IN) and len(lib["sit_in_clips"]) == len(P.SIT_IN)
    assert lib["sit_in"][:4] == [0.0, -80.0, 180.0, 2.0] and len(lib["sit_in"]) == 4 * 5
    assert lib["sit_out"] == [0.0, 120.0, 5.0, 2.4] and lib["sit_in_start"] == [0.0] * 5
    assert lib["sit_clips"] == ["/Game/A/A_place_sit"]
    # (a transition played only near its seat: the stretch from `start_s` to `end_s`)
    pt = _places(3)
    pt["groups"]["s0"]["sit_in_f"].update(start_s=7.5, end_s=10.0)
    pt["groups"]["s0"]["sit_out"].update(start_s=0.0, end_s=1.5)
    trim = UL.people_library({**_lib(3), "place_clips": pt}, spike)
    assert trim["sit_in"][3] == 2.5 and trim["sit_in_start"][0] == 7.5
    assert trim["sit_out"][3] == 1.5
    # (one look without its bake: the library's mid and cards, the transitions kept)
    pl = _places(3)
    pl["idles"]["looks"].pop("p01")
    part = UL.people_library({**_lib(3), "place_clips": pl}, spike)
    assert "mid_still_frames" not in part and part["card_materials"] == [f"/Game/F/MI_{k}"
                                                                          for k in range(3)]
    assert part["sit_in_count"] == len(P.SIT_IN)
    # (a manifest before people_idles: none of it)
    old = UL.people_library({**_lib(3), "place_clips": _places(3, looks=False)}, spike)
    assert "mid_still_frames" not in old and "card_cells" not in old
    pg = _places(3, looks=False)
    for c in P.SIT_IN:
        pg["groups"]["s0"].pop(c)
    assert "sit_in_clips" not in UL.people_library({**_lib(3), "place_clips": pg}, spike)


def test_places_hash_and_idle_key(monkeypatch):
    """The places' hash follows the clips, the script and the idles' bake; the bakes' own key
    only the library and the bake's settings, so editing the script keeps the bakes."""
    from citygen import unreal_people as UP
    h, k = UP.places_hash("abc"), UP.idle_key("abc")
    assert h != UP.places_hash("abd") and k != UP.idle_key("abd")
    monkeypatch.setattr(UP, "IDLE_BAKE", {**UP.IDLE_BAKE, "version": "x"})
    assert UP.places_hash("abc") != h and UP.idle_key("abc") != k
    b = UP.idle_bake({"hash": "abc", "far": {"size": [1.1, 2.2], "views": 8}})
    assert b["rows"] == b["walk_frames"] + b["sit_cells"] + b["idle_cells"] == 16
    assert b["card_cm"] == [110.0, 220.0] and b["key"] == UP.idle_key("abc")
    assert list(b["cell"]) == list(L.IMPOSTOR_CELL)


def test_exporter_packs_the_umbrella_hold():
    """umbrella_hold: the held arm's clip and grip per group and each look's held walk and idle
    in its second bake reach the controller; a manifest without them, or without them for every
    look, leaves the umbrellas as LG8's (none of it)."""
    from citygen import unreal_life as UL
    spike = {"library": {"characters": 3, "walks": list(L.WALKS)},
             "persons": {"seed": [1], "character": [0], "scale": [1.0], "gait": [0],
                         "pace": [1.3], "tint": [0]}}
    pl = _places(3)
    pl["idles"]["mid_key"] = "m1"
    pl["idles"]["umbrella"] = {"s0": {"anim": "/Game/A/A_umb_hold",
                                      "grip_cm": [-24.5, 31.0, 122.25]}}
    for lk in pl["idles"]["looks"].values():
        lk["mid"].update(umb_walk=[270, 329], umb_idle=[330, 419])
    lib = UL.people_library({**_lib(3), "place_clips": pl}, spike)
    assert lib["umb_hold_clips"] == ["/Game/A/A_umb_hold"]
    assert lib["umb_grip"] == [-24.5, 31.0, 122.25] and lib["umb_key"] == "m1"
    assert lib["mid_umb_frames"] == [270.0, 330.0, 419.0, 1.0] * 3
    # (the idles' own data as before)
    assert lib["mid_still_frames"] == [60.0, 149.0, 150.0, 269.0] * 3
    pl["idles"]["looks"]["p01"]["mid"].pop("umb_walk")
    part = UL.people_library({**_lib(3), "place_clips": pl}, spike)
    assert "umb_grip" not in part and "mid_umb_frames" not in part
    assert "umb_grip" not in UL.people_library({**_lib(3), "place_clips": _places(3)}, spike)


def test_mid_key_follows_the_hold(monkeypatch):
    """umbrella_hold: the mid bakes' key follows the hold's settings and the idles' key; the
    still sheets' key (idle_key) does not move with the hold."""
    from citygen import unreal_people as UP
    k, m = UP.idle_key("abc"), UP.mid_key("abc")
    assert m != k and m != UP.mid_key("abd")
    monkeypatch.setattr(UP, "UMB_HOLD", {**UP.UMB_HOLD, "fwd": 0.5})
    assert UP.mid_key("abc") != m and UP.idle_key("abc") == k
    b = UP.idle_bake({"hash": "abc", "far": {"size": [1.1, 2.2], "views": 8}})
    assert b["key"] == k and b["mid_key"] == UP.mid_key("abc")
    assert b["umbrella"]["fwd"] == 0.5 and len(b["umbrella"]["pole"]) == 3


def test_places_need_a_library(tmp_path):
    from citygen import unreal_people as UP
    up = tmp_path / "proj" / "Proj.uproject"
    up.parent.mkdir()
    up.write_text(json.dumps({"FileVersion": 3, "Plugins": []}), encoding="utf-8")
    r = UP.ensure_place_clips(tmp_path / "engine", up)
    assert not r["ok"] and r["how"] == "none"


def test_library_in_a_project_from_the_cache(tmp_path, monkeypatch):
    """A project gets a library built before from the cache, with its manifest and stamp;
    the next call finds it stamped; the plugins it needs are enabled."""
    from citygen import unreal_people as UP
    monkeypatch.setenv("CITYGEN_PEOPLE_CACHE", str(tmp_path / "cache"))
    up = tmp_path / "proj" / "Proj.uproject"
    up.parent.mkdir()
    up.write_text(json.dumps({"FileVersion": 3, "Plugins": []}), encoding="utf-8")
    root = tmp_path / "engine"
    h = L.library_hash(engine=UP._engine_version(root))
    c = UP.cache_dir(h)
    f = c / "Content" / "CityGen" / "People" / "Mid" / "SM_p00.uasset"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"x")
    (c / UP.MANIFEST).write_text(json.dumps(_lib(1)), encoding="utf-8")
    r = UP.ensure_library(root, up)
    assert r["ok"] and r["how"] == "cache" and r["copied"] == 1
    assert (up.parent / "Content" / "CityGen" / "People" / "Mid" / "SM_p00.uasset").is_file()
    names = {p["Name"] for p in json.loads(up.read_text(encoding="utf-8"))["Plugins"]}
    assert set(UP.PLUGINS) <= names
    again = UP.ensure_library(root, up)
    assert again["how"] == "stamped" and UP.read_manifest(up)["hash"] == "abc"


def test_library_build_needs_the_sample(tmp_path, monkeypatch):
    from citygen import unreal_people as UP
    monkeypatch.setenv("CITYGEN_PEOPLE_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("CITYGEN_GAS", str(tmp_path / "nowhere.uproject"))
    up = tmp_path / "proj" / "Proj.uproject"
    up.parent.mkdir()
    up.write_text(json.dumps({"FileVersion": 3, "Plugins": []}), encoding="utf-8")
    r = UP.ensure_library(tmp_path / "engine", up)
    assert not r["ok"] and "Game Animation Sample" in r["error"]


def test_no_epic_content_in_the_repo():
    """Decision 5: MetaHumans, their assets and Epic's animations never go in the repo."""
    import subprocess
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.split()
    assert not [f for f in files if f.endswith((".uasset", ".umap", ".dna"))]
