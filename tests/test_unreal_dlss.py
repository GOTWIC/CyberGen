"""dlss_lamps_flicker: NVIDIA's DLSS plugin into an Unreal project (`citygen unreal --dlss`),
the fixtures' contribution layered with stage 2's, and the benchmark's DLSS passes; on a stand-in
plugin tree (nothing of NVIDIA's is in the repository)."""

import json

import pytest

from citygen import bench as B
from citygen import unreal_dlss as UD
from citygen import unreal_play as UP


def _fake(root):
    """A tree shaped as NVIDIA's zip: Plugins/<name>/<name>.uplugin, binaries, intermediates."""
    for n in UD.PLUGINS:
        d = root / "Plugins" / n
        (d / "Binaries" / "ThirdParty" / "Win64").mkdir(parents=True)
        (d / "Intermediate" / "Build").mkdir(parents=True)
        (d / f"{n}.uplugin").write_text(json.dumps({"VersionName": "8.9.0-test",
                                                   "FileVersion": 3}))
        (d / "Binaries" / "ThirdParty" / "Win64" / "runtime.dll").write_bytes(b"x" * 10)
        (d / "Intermediate" / "Build" / "big.obj").write_bytes(b"y" * 10)
    return root


def _project(tmp_path):
    p = tmp_path / "proj"
    (p / "Config").mkdir(parents=True)
    up = p / "Proj.uproject"
    up.write_text(json.dumps({"FileVersion": 3, "Plugins": [{"Name": "CityGenPlay",
                                                             "Enabled": True}]}))
    (p / "Config" / "DefaultEngine.ini").write_text("[/Script/Engine.RendererSettings]\n"
                                                    "r.Shadow.Virtual.Enable=1\n")
    return up


def test_source_finds_the_plugins_or_none(tmp_path, monkeypatch):
    monkeypatch.delenv(UD.ENV, raising=False)
    assert UD.source(None) is None
    src = _fake(tmp_path / "dl")
    assert UD.source(src) == src / "Plugins"
    assert UD.source(src / "Plugins") == src / "Plugins"
    monkeypatch.setenv(UD.ENV, str(src))
    assert UD.source(None) == src / "Plugins"
    with pytest.raises(FileNotFoundError):
        UD.source(tmp_path)


def test_install_copies_enables_and_sets_once(tmp_path):
    src = UD.source(_fake(tmp_path / "dl"))
    up = _project(tmp_path)
    r = UD.install(src, up)
    assert r["copied"] and r["version"] == "8.9.0-test" and set(r["enabled"]) == set(UD.PLUGINS)
    for n in UD.PLUGINS:
        d = up.parent / "Plugins" / n
        assert (d / f"{n}.uplugin").is_file()
        assert (d / "Binaries" / "ThirdParty" / "Win64" / "runtime.dll").is_file()
        assert not (d / "Intermediate").exists()          # (not NVIDIA's build intermediates)
    names = [p["Name"] for p in json.loads(up.read_text())["Plugins"]]
    assert names[0] == "CityGenPlay" and set(UD.PLUGINS) <= set(names)
    ini = (up.parent / "Config" / "DefaultEngine.ini").read_text()
    assert "bShowDLSSSDebugOnScreenMessages=False" in ini and "r.AntiAliasingMethod=4" in ini
    assert "r.Shadow.Virtual.Enable=1" in ini
    assert UD.installed(up) == r["stamp"]
    # again: nothing copied, nothing changed
    r2 = UD.install(src, up)
    assert not r2["copied"] and not r2["enabled"] and not r2["settings_changed"]


def test_play_plugin_stamp_names_dlss_only_when_installed(tmp_path):
    up = _project(tmp_path)
    assert UD.installed(up) == ""
    UD.install(UD.source(_fake(tmp_path / "dl")), up)
    assert UD.installed(up).startswith("8.9.0-test ")
    # (build_plugin's want: the source hash, the engine, and DLSS where installed)
    assert "installed(uproject)" in (UP.Path(UP.__file__)).read_text(encoding="utf-8")


def test_benchmark_dlss_passes():
    passes = {p[0]: p for p in B.ATMOS_PASSES}
    for m, pct in B.DLSS_PERCENT.items():
        p = passes[f"night_plan_all_dlss_{m}"]
        assert p[2] == pct and "r.NGX.DLSS.Enable 1" in p[3]
        assert "r.Streamline.DLSSG.Enable 0" in p[3]
        assert "r.Streamline.DLSSG.Enable 1" in passes[f"night_plan_all_dlss_{m}_fg"][3]
    # every other atmos pass switches both off, so none leaks into the next
    assert "r.NGX.DLSS.Enable 0" in passes["night_plan_all"][3]
    assert "r.Streamline.DLSSG.Enable 0" in passes["night_plan_all_tsr67"][3]
    assert passes["night_plan_all"][3][-1].startswith("CityGenAtmos.Hour")


def test_frame_generation_stats(tmp_path):
    fs = [{"frame_ms": 10.0, "game_ms": 5.0, "render_ms": 5.0, "rhi_ms": 5.0, "gpu_ms": 9.0,
           "draws": 1.0, "prims": 1.0, "streamed": 1.0, "perf": 0.0, "vram_mb": 1.0,
           "ram_mb": 1.0, "fg_hz": 180.0 + i, "fg_presented": 2.0, "latency_ms": 20.0}
          for i in range(20)]
    g = B._group(fs, None, 0, set())
    assert g["fg_hz"]["p50"] >= 180.0 and g["fg_presented"] == 2.0
    assert g["latency_ms"]["p50"] == 20.0
    # a run before has none of the columns
    for f in fs:
        del f["fg_hz"], f["fg_presented"], f["latency_ms"]
    assert "fg_hz" not in B._group(fs, None, 0, set())


def test_downloading_launcher_is_busy(monkeypatch):
    seq = iter([{1: ("EpicGamesLauncher", 10.0), 2: ("explorer", 1.0)},
                {1: ("EpicGamesLauncher", 12.0), 2: ("explorer", 1.0)}])
    monkeypatch.setattr(B, "cpu_times", lambda: next(seq))
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    hit = B.downloading()
    assert len(hit) == 1 and hit[0].startswith("EpicGamesLauncher.exe 1 (downloading")
    seq2 = iter([{1: ("EpicGamesLauncher", 10.0)}, {1: ("EpicGamesLauncher", 10.1)}])
    monkeypatch.setattr(B, "cpu_times", lambda: next(seq2))
    assert B.downloading() == []


def test_fixtures_contribution_only_from_a_delivered_plan(tmp_path):
    from citygen import unreal_atmos as UA
    pdir = tmp_path / "atmos"
    pdir.mkdir()
    plan = {"checks": {"lux": {"ok": True}, "fixtures": {"ok": True}}}
    (pdir / "atmos_plan.json").write_text(json.dumps(plan))
    c = {"version": 1, "layer": 3, "part": "props", "entries": [
        {"key": "atmos.fixtures.t+00+00.sw", "kind": "prop.fixture", "parts": []}]}
    assert UA.fixtures_contribution(tmp_path, pdir) is None          # (no file yet)
    (pdir / UA.FIXTURES).write_text(json.dumps(c))
    rel, got, sha = UA.fixtures_contribution(tmp_path, pdir)
    assert got == c and rel.endswith(UA.FIXTURES) and len(sha) == 64
    plan["checks"]["fixtures"]["ok"] = False
    (pdir / "atmos_plan.json").write_text(json.dumps(plan))
    assert UA.fixtures_contribution(tmp_path, pdir) is None
    assert "fixtures check failed" in UA.undelivered(plan)
