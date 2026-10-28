"""AG0's Unreal spike, the venv side: runs `assetgen/ue/spike_import.py` (headless) and
`assetgen/ue/spike_shots.py` (with a renderer) in a throwaway Unreal 5.8 project, cooks the
imported meshes for the cooked sizes, and writes the measurements.

Not the exporter: the shared Unreal exporter (`docs/unreal_export.md`) takes assetgen's
manifest entries (`spike.contribution`) once it layers stages. This only measures what the
scope's section 11 estimated. The project is made as M15's `citygen unreal --new-project`
makes one; `new_project` here only adds the plugins the spike needs to such a project.
"""

from __future__ import annotations

import json
import re
import os
import subprocess
import sys
import time
from pathlib import Path

UE_DIR = Path(__file__).parent / "ue"
EDITOR_CMD = {"darwin": "Mac/UnrealEditor-Cmd", "win32": "Win64/UnrealEditor-Cmd.exe",
              "linux": "Linux/UnrealEditor-Cmd"}
EDITOR_GUI = {"darwin": "Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor",
              "win32": "Win64/UnrealEditor.exe", "linux": "Linux/UnrealEditor"}
PLUGINS = ["PythonScriptPlugin", "EditorScriptingUtilities", "NaniteAssemblyEditorUtils"]


def editor(root: Path, gui: bool = False) -> Path:
    rel = (EDITOR_GUI if gui else EDITOR_CMD).get(sys.platform, EDITOR_CMD["linux"])
    return root / "Engine" / "Binaries" / rel


def enable_plugins(uproject: Path) -> list[str]:
    data = json.loads(uproject.read_text(encoding="utf-8-sig"))
    have = {x.get("Name"): x for x in data.setdefault("Plugins", [])}
    added = []
    for n in PLUGINS:
        if n not in have:
            data["Plugins"].append({"Name": n, "Enabled": True})
            added.append(n)
        elif not have[n].get("Enabled", False):
            have[n]["Enabled"] = True
            added.append(n)
    if added:
        uproject.write_text(json.dumps(data, indent="\t") + "\n", encoding="utf-8")
    return added


def run_editor(root: Path, uproject: Path, script: Path, job: dict, log: Path,
               gui: bool = False, timeout: float = 7200.0) -> dict:
    job_path = log.with_suffix(".job.json")
    job_path.write_text(json.dumps(job, indent=1) + "\n", encoding="utf-8")
    res_path = Path(job["result"])
    if res_path.exists():
        res_path.unlink()
    if gui:
        cmd = [str(editor(root, True)), str(uproject), f"-ExecCmds=py {script}", "-unattended",
               "-nosplash", "-stdout", "-FullStdOutLogOutput", "-NoSound", "-RenderOffscreen"]
    else:
        cmd = [str(editor(root)), str(uproject), "-run=pythonscript", f"-script={script}",
               "-unattended", "-nosplash", "-nullrhi", "-stdout", "-FullStdOutLogOutput"]
    t = time.time()
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT,
                              env={**os.environ, "ASSETGEN_UE_JOB": str(job_path)},
                              timeout=timeout)
    res = (json.loads(res_path.read_text(encoding="utf-8")) if res_path.is_file()
           else {"ok": False, "error": "the editor wrote no result (see the log)"})
    res["exit_code"] = proc.returncode
    res["wall_s"] = round(time.time() - t, 1)
    res_path.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    return res


def cook(root: Path, uproject: Path, packages: list[str], log: Path,
         platform: str = "Mac") -> dict:
    """Cook only the given packages (no references) and measure their cooked files."""
    cmd = [str(editor(root)), str(uproject), "-run=cook", f"-targetplatform={platform}",
           "-unversioned", "-cooksinglepackagenorefs", "-unattended", "-nosplash", "-stdout",
           "-FullStdOutLogOutput"] + [f"-PACKAGE={p}" for p in packages]
    t = time.time()
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=7200)
    cooked = uproject.parent / "Saved" / "Cooked" / platform / uproject.stem / "Content"
    sizes = {}
    for p in packages:
        rel = p[len("/Game/"):]
        files = {}
        d = cooked / Path(rel).parent
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.stem == Path(rel).name:
                    files[f.name] = f.stat().st_size
        sizes[p] = files
    return {"exit_code": proc.returncode, "wall_s": round(time.time() - t, 1), "sizes": sizes}


_NANITE = re.compile(r"Input: (\d+) Clusters, (\d+) Triangles and (\d+) Vertices")
_SIZE = re.compile(r"Total GPU size: (\d+) bytes, Total disk size: (\d+) bytes")
_BUILT = re.compile(r"Built static mesh \[([\d.]+)s\] (/Game/\S+?)\.")
_DF = re.compile(r"Finished distance field build in ([\d.]+)s - (\d+)x(\d+)x(\d+) sparse "
                 r"distance field, ([\d.]+)Mb total.*?, (\S+)$")


def parse_log(path: Path) -> dict:
    """What the editor log tells and Python cannot read: per mesh shell, the Nanite build
    (input clusters and triangles, which count every level of its cluster hierarchy, GPU
    and disk size, build time); per distance field, its build time, resolution and size."""
    meshes, dfs = {}, []
    last_in = last_size = None
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = _NANITE.search(line)
        if m and "Output" not in line:
            last_in = tuple(int(v) for v in m.groups())
            continue
        m = _SIZE.search(line)
        if m:
            last_size = tuple(int(v) for v in m.groups())
            continue
        m = _BUILT.search(line)
        if m and "shell" in m.group(2) and last_size is not None:
            meshes[m.group(2)] = {"build_s": float(m.group(1)),
                                  "nanite_input": {"clusters": last_in[0], "triangles": last_in[1],
                                                   "vertices": last_in[2]} if last_in else None,
                                  "nanite_gpu_bytes": last_size[0],
                                  "nanite_disk_bytes": last_size[1]}
            continue
        m = _DF.search(line)
        if m:
            dfs.append({"mesh": m.group(6), "build_s": float(m.group(1)),
                        "resolution": [int(m.group(k)) for k in (2, 3, 4)],
                        "mb": float(m.group(5))})
    return {"meshes": meshes, "distance_fields": dfs}
