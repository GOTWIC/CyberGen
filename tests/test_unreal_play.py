"""The Unreal export's play features, the venv side (citygen/unreal_play.py): the map image,
the walkway points, the lamp heads, the play data and its cache, the plugin's install and
build command, and finding the engine and Blender where their installers put them. Building
the plugin and playing it run in `citygen unreal --check` (test_unreal's import test)."""

import json
import math
import struct
import sys
from pathlib import Path

import pytest

from citygen import blockout as BO
from citygen import unreal as U
from citygen import unreal_play as P


def _plan():
    """A city 200 by 100 m: ground with a court, sea, a street, a building box and prism,
    a park, a skybridge beam, a tunnel and two street lights (one turned a quarter)."""
    return {
        "city": "Tiny", "bounds": [-100.0, -50.0, 100.0, 50.0], "tile_size_m": 256.0,
        "materials": {"bld_core": "#4f7cff", "ground": "#888888"},
        "prototypes": {
            "street_light": [{"k": "box", "m": "prop_metal", "c": [0.0, 0.0, 4.0],
                              "d": [0.2, 0.2, 8.0], "yaw": 0.0},
                             {"k": "box", "m": "prop_light", "c": [1.5, 0.0, 7.55],
                              "d": [0.7, 0.35, 0.2], "yaw": 0.0}],
            "bench": [{"k": "box", "m": "prop_metal", "c": [0.0, 0.0, 0.4],
                       "d": [1.8, 0.5, 0.8], "yaw": 0.0}]},
        "objects": [
            {"name": "ground.t0", "category": "ground", "parts": [
                {"k": "prism", "m": "ground", "z0": -4.0, "z1": 0.0,
                 "r": [[-90, -50], [100, -50], [100, 50], [-90, 50]],
                 "h": [[[-10, -10], [10, -10], [10, 10], [-10, 10]]]}]},
            {"name": "sea.t0", "category": "sea", "parts": [
                {"k": "flat", "m": "sea", "z": -1.2,
                 "r": [[-100, -50], [-90, -50], [-90, 50], [-100, 50]], "h": []}]},
            {"name": "road.t0", "category": "road_street", "parts": [
                {"k": "ribbon", "m": "road_street", "l": [[-80, 5, 0], [80, 5, 0]],
                 "rr": [[-80, -5, 0], [80, -5, 0]], "t": 0.0}]},
            {"name": "b1", "category": "building", "parts": [
                {"k": "box", "m": "bld_core", "c": [40, 30, 10], "d": [10, 6, 20], "yaw": 30.0},
                {"k": "prism", "m": "bld_core", "z0": 0, "z1": 30,
                 "r": [[50, 20], [70, 20], [70, 40], [50, 40]], "h": []}]},
            {"name": "park", "category": "open_park", "parts": [
                {"k": "flat", "m": "park", "z": 0.0,
                 "r": [[-60, 20], [-30, 20], [-30, 40], [-60, 40]], "h": []}]},
            {"name": "sky", "category": "skybridge", "parts": [
                {"k": "beam", "m": "skybridge", "a": [0, 0, 40], "b": [0, 0, 40], "w": 5, "h": 4},
                {"k": "beam", "m": "skybridge", "a": [55, 30, 40], "b": [65, 30, 40],
                 "w": 5, "h": 4}]},
            {"name": "tun", "category": "tunnel", "parts": [
                {"k": "ribbon", "m": "tunnel", "l": [[-60, -29, -9], [-40, -29, -9]],
                 "rr": [[-60, -31, -9], [-40, -31, -9]]}]},
            {"name": "lights", "category": "prop_street_light", "parts": [
                {"k": "inst", "proto": "street_light",
                 "pts": [[10, 20, 0, 0, 1, 1, 1], [-20, -30, 2, 90, 1, 1, 2]]}]}]}


def _instances(plan):
    out = []
    for o in plan["objects"]:
        p = o["parts"][0]
        if p["k"] == "inst":
            out.append({"key": o["name"], "proto": p["proto"], "xforms": p["pts"]})
    return out


def _graphs():
    """Walkways: a 22 m sidewalk (two vertices), a crossing back onto its start, an
    elevator and a skybridge (no one lands there)."""
    elems = [("sidewalk", [(0, 0, 0), (22, 0, 0)]), ("crossing", [(22, 0, 0), (0, 0, 0)]),
             ("elevator", [(5, 5, 0), (5, 5, 9)]), ("skybridge", [(30, 30, 40), (40, 30, 40)])]
    pts, start = [], [0]
    for _, line in elems:
        for p in line:
            pts += list(p)
        start.append(len(pts) // 3)
    return {"walkways": {"kinds": [k for k, _ in elems], "points": pts, "point_start": start}}


def test_shapes():
    assert P._shape({"k": "inst", "proto": "x", "pts": []}) is None
    rings = P._shape(_plan()["objects"][0]["parts"][0])
    # the court is wound against the exterior, so a nonzero fill leaves it open
    assert len(rings) == 2 and P._signed(rings[0]) * P._signed(rings[1]) < 0
    rib = P._shape(_plan()["objects"][2]["parts"][0])[0]
    assert rib == [(-80.0, 5.0), (80.0, 5.0), (80.0, -5.0), (-80.0, -5.0)]
    box = P._shape({"k": "box", "c": [0, 0, 0], "d": [2, 4, 1], "yaw": 90.0})[0]
    assert [(round(x, 6), round(y, 6)) for x, y in box] == [(2, -1), (2, 1), (-2, 1), (-2, -1)]
    assert P._shape({"k": "beam", "a": [0, 0, 0], "b": [0, 0, 0], "w": 2, "h": 1}) is None
    beam = P._shape({"k": "beam", "a": [0, 0, 5], "b": [10, 0, 5], "w": 2, "h": 1})[0]
    assert beam == [(0, 1), (10, 1), (10, -1), (0, -1)]


def test_walk_points():
    """Lines sampled every WALK_STEP_M, one point per WALK_GRID_M cell, stairs, lifts and
    skybridges left out."""
    w = P.walk_points(_graphs())
    pts = [tuple(w[i:i + 3]) for i in range(0, len(w), 3)]
    assert pts[0] == (0.0, 0.0, 0.0) and (22.0, 0.0, 0.0) in pts
    assert all(p[2] == 0.0 and p[1] == 0.0 for p in pts)      # no lift, no skybridge
    xs = sorted(p[0] for p in pts)
    assert len(xs) == len(set(math.floor(x / P.WALK_GRID_M) for x in xs))
    assert max(b - a for a, b in zip(xs, xs[1:])) <= P.WALK_STEP_M + 1e-9
    assert P.walk_points(None) == [] and P.walk_points({"lanes": {}}) == []


def test_lamp_points():
    """Each street light's lamp head: its prototype's `prop_light` part turned by the yaw,
    scaled and moved by the instance's transform; benches give none."""
    plan = _plan()
    pts, kinds = P.lamp_points(plan, _instances(plan) + [
        {"key": "z", "proto": "bench", "xforms": [[0, 0, 0, 0, 1, 1, 1]]}])
    assert kinds == [0, 0]
    assert pts[:3] == [11.5, 20.0, 7.55]
    assert pts[3:] == [-20.0, -28.5, round(2 + 7.55 * 2, 2)]
    assert P.lamp_offsets({"prototypes": {}}) == {}


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_write_play(tmp_path):
    """map.png over the plan's bounds (its aspect kept), play.json and the manifest's
    `play`; drawn again only when the plan changes, the same bytes otherwise."""
    plan = _plan()
    (tmp_path / "city_model.json").write_text(json.dumps({"districts": [
        {"name": "Core", "polygon": {"exterior": [[0, 0], [50, 0], [50, 40], [0, 40]],
                                     "holes": []}},
        {"name": "Ring", "polygon": {"exterior": [[-80, -40], [-20, -40], [-20, 0], [-80, 0]],
                                    "holes": [[[-60, -30], [-40, -30], [-40, -10], [-60, -10]]]}},
    ]}))
    info = P.write_play(tmp_path, "sha-a", plan, _instances(plan), _graphs())
    png, data_path = tmp_path / "unreal" / "map.png", tmp_path / "unreal" / "play.json"
    assert _png_size(png) == (P.MAP_PX, P.MAP_PX // 2) == tuple(info["map_size"])
    data = json.loads(data_path.read_text())
    assert data["map"]["bounds"] == plan["bounds"] and info["map_bounds"] == plan["bounds"]
    assert info["lamps"] == 2 and info["walk_points"] == len(data["walk"]) // 3 > 0
    assert [r["name"] for r in data["labels"]] == ["Core", "Ring"]
    from shapely.geometry import Point, Polygon
    ring = Polygon([[-80, -40], [-20, -40], [-20, 0], [-80, 0]],
                   [[[-60, -30], [-40, -30], [-40, -10], [-60, -10]]])
    assert ring.contains(Point(data["labels"][1]["x"], data["labels"][1]["y"]))
    # the same plan: nothing drawn again, the same files
    mtime, before = png.stat().st_mtime_ns, data_path.read_bytes()
    assert P.write_play(tmp_path, "sha-a", plan, _instances(plan), _graphs()) == info
    assert png.stat().st_mtime_ns == mtime and data_path.read_bytes() == before
    # another plan: drawn again
    plan["objects"].pop(3)
    info2 = P.write_play(tmp_path, "sha-b", plan, _instances(plan), _graphs())
    assert info2["map_sha256"] != info["map_sha256"] and info2["hash"] != info["hash"]


def test_map_colors(tmp_path):
    """The map's pixels: sea at the west edge, a street across, the building in its
    district's hue, nothing of the tunnel under the ground."""
    from PIL import Image
    plan = _plan()
    w, h = P.render_map(plan, tmp_path / "m.png", px=400)
    im = Image.open(tmp_path / "m.png").convert("RGB")
    assert (w, h) == im.size == (400, 200)

    def at(x, y):
        return im.getpixel((round((x + 100) / 200 * (w - 1)), round((50 - y) / 100 * (h - 1))))

    sea, street, land = at(-97, 30), at(0, 0), at(0, -30)
    assert sea == tuple(round(c * 255) for c in P._rgb(P.SEA))
    assert street != land and sum(street) > sum(land)
    bld, park = at(60, 30), at(-45, 30)
    assert bld[2] > bld[0] and bld != land          # tinted toward the district's blue
    assert park[1] > park[0] and park[1] > park[2]  # green
    assert at(-50, -30) == at(-50, -40) == land     # the tunnel under the ground: not drawn


def test_plugin_install(tmp_path):
    """The plugin's source copied into the project (Binaries and Intermediate left out),
    enabled in the .uproject; a second install writes nothing; files the plugin no longer
    has go; removing takes it out again."""
    up = tmp_path / "P" / "P.uproject"
    up.parent.mkdir()
    up.write_text(json.dumps({"FileVersion": 3, "Plugins": [{"Name": "X", "Enabled": True}]}))
    r = P.install_plugin(up)
    dest = Path(r["dir"])
    assert r["wrote"] == len(P.plugin_files()) > 4 and (dest / "CityGenPlay.uplugin").is_file()
    assert (dest / "Source" / "CityGenPlay" / "CityGenPlay.Build.cs").is_file()
    plugins = json.loads(up.read_text())["Plugins"]
    assert {"Name": P.PLUGIN, "Enabled": True} in plugins and {"Name": "X", "Enabled": True} in plugins
    stale = dest / "Source" / "CityGenPlay" / "Private" / "Old.cpp"
    stale.write_text("// gone")
    r2 = P.install_plugin(up)
    assert r2["wrote"] == 0 and r2["removed"] == 1 and not stale.exists()
    assert len(P.plugin_hash()) == 16
    P.remove_plugin(up)
    assert not dest.exists()
    assert json.loads(up.read_text())["Plugins"] == [{"Name": "X", "Enabled": True}]


def test_build_command(tmp_path):
    cmd = P.build_command(tmp_path / "UE_5.8", tmp_path / "P.uproject")
    assert cmd[1:3] == ["UnrealEditor", {"win32": "Win64", "darwin": "Mac"}.get(sys.platform, "Linux")]
    assert f"-Project={tmp_path / 'P.uproject'}" in cmd and "-NoHotReloadFromIDE" in cmd
    assert Path(cmd[0]).name == ("Build.bat" if sys.platform == "win32" else "Build.sh")


def test_build_plugin_failure_takes_it_out(tmp_path, monkeypatch):
    """A build that fails (no compiler) leaves the project without the plugin, and says why."""
    up = tmp_path / "P" / "P.uproject"
    up.parent.mkdir()
    up.write_text(json.dumps({"FileVersion": 3, "Plugins": []}))
    monkeypatch.setattr(P, "build_command", lambda root, uproject: [
        sys.executable, "-c", "print('error: no valid toolchain'); raise SystemExit(6)"])
    r = P.build_plugin(tmp_path / "UE", up, tmp_path / "log.txt")
    assert not r["ok"] and "no valid toolchain" in r["error"] and r["exit_code"] == 6
    assert not (up.parent / "Plugins" / P.PLUGIN).exists()
    assert json.loads(up.read_text())["Plugins"] == []
    # a build that succeeds is stamped and not run again for the same source (its log's
    # folder made if missing)
    monkeypatch.setattr(P, "build_command", lambda root, uproject: [sys.executable, "-c", "pass"])
    r = P.build_plugin(tmp_path / "UE", up, tmp_path / "logs" / "log.txt")
    assert r["ok"] and r["built"]
    r = P.build_plugin(tmp_path / "UE", up, tmp_path / "log.txt")
    assert r["ok"] and not r["built"]
    # a rebuild that fails after one that worked keeps the earlier build (an imported play
    # actor keeps its class), and says so
    monkeypatch.setattr(P, "plugin_hash", lambda: "changed")
    monkeypatch.setattr(P, "build_command", lambda root, uproject: [
        sys.executable, "-c", "raise SystemExit(6)"])
    r = P.build_plugin(tmp_path / "UE", up, tmp_path / "log.txt")
    assert not r["ok"] and r["kept_earlier_build"]
    assert (up.parent / "Plugins" / P.PLUGIN / "CityGenPlay.uplugin").is_file()
    assert {"Name": P.PLUGIN, "Enabled": True} in json.loads(up.read_text())["Plugins"]


@pytest.mark.skipif(sys.platform not in ("win32", "darwin"), reason="the Launcher's platforms")
def test_engine_from_the_launcher(tmp_path, monkeypatch):
    """An engine the Epic Games Launcher installed outside the usual place is found through
    its LauncherInstalled.dat (the newest UE_5 of those that have binaries)."""
    for v in ("UE_5.7", "UE_5.8"):
        (tmp_path / "Games" / v / "Engine" / "Binaries").mkdir(parents=True)
    dat = {"InstallationList": [
        {"AppName": "UE_5.7", "InstallLocation": str(tmp_path / "Games" / "UE_5.7")},
        {"AppName": "UE_5.8", "InstallLocation": str(tmp_path / "Games" / "UE_5.8")},
        {"AppName": "UE_5.9", "InstallLocation": str(tmp_path / "Games" / "UE_5.9")},
        {"AppName": "Fortnite", "InstallLocation": str(tmp_path / "Games" / "F")}]}
    if sys.platform == "win32":
        monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
        f = tmp_path / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat"
    else:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        f = tmp_path / "Library" / "Application Support" / "Epic" / "UnrealEngineLauncher" \
            / "LauncherInstalled.dat"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps(dat))
    monkeypatch.delenv("CITYGEN_UE_ROOT", raising=False)
    monkeypatch.setattr(U, "ENGINE_GLOBS", {})
    assert len(U.launcher_engines()) == 3
    assert U.find_engine() == tmp_path / "Games" / "UE_5.8"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' Program Files")
def test_blender_in_program_files(tmp_path, monkeypatch):
    for v in ("Blender 4.4", "Blender 5.2", "Blender 5.10"):
        d = tmp_path / "Blender Foundation" / v
        d.mkdir(parents=True)
        (d / "blender.exe").write_text("")
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.delenv("BLENDER", raising=False)
    assert BO.find_blender() == str(tmp_path / "Blender Foundation" / "Blender 5.10" / "blender.exe")
