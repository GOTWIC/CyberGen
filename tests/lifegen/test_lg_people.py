"""LG1: the people library's spec (`lifegen/library.py`), the plan's person draws, and the
exporter's packing of people (`citygen/unreal_life.py`) and of the library in the project
(`citygen/unreal_people.py`), without Unreal."""

import json
from pathlib import Path

from lifegen import library as L

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
