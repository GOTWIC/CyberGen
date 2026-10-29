"""Run a Blender script in the background with its progress on a stage of `assetgen/progress.py`.

The scripts print one line per view, sheet cell or board (`mark` in each script):

    CGPROGRESS start <name>
    CGPROGRESS done <name>

`run` reads Blender's stdout as it comes: a start is a note on the stage, a done advances its
bar; stderr is collected on a thread, so neither pipe fills up. The rest of the output comes
back as it did from `subprocess.run`, for the callers' error messages.
"""

from __future__ import annotations

import subprocess
import threading

MARK = "CGPROGRESS "


def run(cmd: list[str], stage, keep: str | None = None, log=None) -> tuple[int, str, str]:
    """(returncode, stdout, stderr) of `cmd`; lines starting with `keep` go to `log`."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace", bufsize=1)
    err: list[str] = []
    t = threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True)
    t.start()
    out: list[str] = []
    for line in proc.stdout:
        out.append(line)
        if line.startswith(MARK):
            what, _, name = line[len(MARK):].strip().partition(" ")
            if what == "start":
                stage.note(f"{name}: rendering")
            elif what == "done":
                stage.advance()
        elif keep and log is not None and line.startswith(keep):
            log(line.rstrip("\n"))
    proc.wait()
    t.join()
    return proc.returncode, "".join(out), "".join(err)
