"""fix_hlod_streaming on the venv side (citygen/unreal.py): the instanced HLODs' component
class the play plugin's in the project's DefaultEditor.ini when the plugin is built
(`set_hlod_class`), and HLODs built with another class or HLOD version built again whole
(`build_hlods`, `hlod_stamp`). No Unreal: the builder's command is captured."""

import json
import re
from pathlib import Path

from citygen import unreal as U


def _project(tmp_path):
    up = tmp_path / "P" / "P.uproject"
    (tmp_path / "P" / "Config").mkdir(parents=True)
    return up, tmp_path / "P" / "Config" / "DefaultEditor.ini"


def test_hlod_class_follows_the_play_plugin(tmp_path):
    """Built: the plugin's class under the HLOD builder's section, the rest of the file as
    it was (line endings too), a second import changing nothing; not built: the key out
    again (the engine's class), the section's other lines kept."""
    up, ini = _project(tmp_path)
    assert U.hlod_class(up) == ""
    ini.write_bytes(b"[/Script/UnrealEd.EditorEngine]\r\nA=1\r\n\r\n"
                    b"[/Script/Engine.HLODBuilder]\r\nOther=2\r\n")
    assert U.set_hlod_class(up, True)
    assert U.hlod_class(up) == U.HLOD_ISM_CLASS
    assert ini.read_bytes() == (b"[/Script/UnrealEd.EditorEngine]\r\nA=1\r\n\r\n"
                                b"[/Script/Engine.HLODBuilder]\r\n"
                                b"HLODInstancedStaticMeshComponentClass="
                                b"/Script/CityGenPlay.CityGenHLODComponent\r\nOther=2\r\n")
    assert not U.set_hlod_class(up, True)
    assert U.set_hlod_class(up, False)
    assert U.hlod_class(up) == ""
    assert ini.read_bytes() == (b"[/Script/UnrealEd.EditorEngine]\r\nA=1\r\n\r\n"
                                b"[/Script/Engine.HLODBuilder]\r\nOther=2\r\n")
    assert not U.set_hlod_class(up, False)
    # a project with no such file is left without one when the plugin is not built
    up2 = tmp_path / "Q" / "Q.uproject"
    assert not U.set_hlod_class(up2, False)
    assert not (tmp_path / "Q" / "Config" / "DefaultEditor.ini").exists()
    assert U.set_hlod_class(up2, True)
    assert U.hlod_class(up2) == U.HLOD_ISM_CLASS


def test_build_hlods_builds_all_again_for_a_new_class(tmp_path, monkeypatch):
    """The first build, and the first after the class or `HLOD_VERSION` changes, sets up and
    builds every HLOD actor (-SetupHLODs -RebuildHLODs); a build with the class it was last
    built with rebuilds only what changed (no flag); a failed build leaves the stamp as it
    was."""
    up, ini = _project(tmp_path)
    build = tmp_path / "B"
    (build / U.OUT_DIR).mkdir(parents=True)
    (build / U.OUT_DIR / "manifest.json").write_text(json.dumps(
        {"content_root": "/Game/CityGen/Town", "folder": "Town"}), encoding="utf-8")
    cmds, code = [], [0]

    def streamed(cmd, log, on_line, timeout, env=None):
        cmds.append(cmd)
        Path(log).write_text("World contains 3 HLOD actors\n", encoding="utf-8")
        return code[0]

    monkeypatch.setattr(U, "find_engine", lambda e=None: tmp_path)
    monkeypatch.setattr(U, "editor_binary", lambda root, gui=False: Path("UnrealEditor-Cmd"))
    monkeypatch.setattr(U, "_streamed", streamed)
    forced = lambda: "-RebuildHLODs" in cmds[-1] and "-SetupHLODs" in cmds[-1]  # noqa: E731
    U.set_hlod_class(up, True)
    r = U.build_hlods(build, up)
    assert r["ok"] and r["forced"] and forced()
    assert r["component_class"] == U.HLOD_ISM_CLASS
    stamp = U.hlod_stamp(up.resolve(), "/Game/CityGen/Town/Maps/Town")
    assert stamp.read_text(encoding="utf-8") == f"{U.HLOD_ISM_CLASS} {U.HLOD_VERSION}\n"
    assert "all built again" in U.hlod_summary(r)
    r = U.build_hlods(build, up)
    assert not r["forced"] and not forced()
    # the plugin not built: the engine's class, every HLOD built again
    U.set_hlod_class(up, False)
    code[0] = 1
    r = U.build_hlods(build, up)
    assert not r["ok"] and forced()
    assert stamp.read_text(encoding="utf-8").startswith(U.HLOD_ISM_CLASS)
    code[0] = 0
    r = U.build_hlods(build, up)
    assert r["forced"] and r["component_class"] == "engine"
    assert U.build_hlods(build, up)["forced"] is False
    monkeypatch.setattr(U, "HLOD_VERSION", U.HLOD_VERSION + "x")
    assert U.build_hlods(build, up)["forced"]


def test_the_plugin_has_the_hlod_class():
    """`HLOD_ISM_CLASS` names a class of the play plugin, an instanced HLOD component whose
    visibility flip keeps its proxy (the render-thread flip, not a new render state) and
    which leaves its HLOD actor's root as it begins to play (the root's flip dirtied every
    component attached to it)."""
    mod, cls = re.fullmatch(r"/Script/(\w+)\.(\w+)", U.HLOD_ISM_CLASS).groups()
    src = Path(U.__file__).parent / "ue" / mod / "Source" / mod
    head = (src / "Public" / f"{cls}.h").read_text(encoding="utf-8")
    assert re.search(rf"class {mod.upper()}_API U{cls} : public "
                     r"UHLODInstancedStaticMeshComponent", head)
    body = (src / "Private" / f"{cls}.cpp").read_text(encoding="utf-8")
    assert "UpdatePrimitivesIsDrawn_RenderThread" in body
    assert "OnVisibilityChanged" in body
    assert "DetachFromComponent" in body and "::BeginPlay()" in body
    # the HLOD builder's defaults read again once the class exists (they are read at start)
    mod_src = (src / "Private" / f"{mod}Module.cpp").read_text(encoding="utf-8")
    assert "/Script/Engine.HLODBuilder" in mod_src and "ReloadConfig" in mod_src
