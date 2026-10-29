"""Progress on stderr (`assetgen/progress.py`, `assetgen/blenderrun.py`): plain lines when piped,
one redrawn line on a terminal, nothing with --quiet or CYBERGEN_QUIET=1; `assetgen build`
with it writes the same files (an unchanged rebuild writes none)."""

import io
import os
import re
import shutil
import subprocess
import sys

from assetgen import progress as PG
from assetgen.blenderrun import run as run_blender

from agtools import ROOT, copy_model, small_assets


class Tty(io.StringIO):
    def isatty(self):
        return True


def _stages(p):
    with p.stage("briefs") as s:
        s.note("12 briefs")
    with p.stage("shells", total=8) as s:
        for _ in range(8):
            s.advance()
    with p.stage("tiles", total=None) as s:
        s.set_total(4)
        s.update(4)
    p.summary()


def test_piped_output_is_plain_lines():
    out = io.StringIO()
    _stages(PG.Progress(quiet=False, stream=out))
    text = out.getvalue()
    assert "\r" not in text
    lines = text.splitlines()
    assert lines[:3] == ["briefs ...", "  12 briefs", lines[2]] and \
        lines[2].startswith("briefs: done in ")
    shells = [ln for ln in lines if ln.startswith("shells")]
    assert shells[0] == "shells ..." and shells[-1].startswith("shells: done in ")
    assert [ln.split()[1] for ln in shells[1:-1]] == ["0/8", "2/8", "4/8", "6/8", "8/8"]
    assert "tiles: 4/4 100%" in lines
    assert lines[-5] == "time per stage:" and lines[-1].split()[0] == "total"


def test_terminal_redraws_one_line():
    out = Tty()
    p = PG.Progress(quiet=False, stream=out)
    assert p.tty
    with p.stage("shells", total=40) as s:
        for _ in range(40):
            s.advance()
    text = out.getvalue()
    assert "\rshells [####################] 40/40 100%" in text
    assert text.endswith("shells: done in " + text.rsplit("shells: done in ", 1)[1])
    assert text.count("\n") == 1                     # only the closing line ends a line


def test_quiet_prints_nothing(monkeypatch):
    out = io.StringIO()
    _stages(PG.Progress(quiet=True, stream=out))
    assert out.getvalue() == ""
    monkeypatch.setenv("CYBERGEN_QUIET", "1")
    p = PG.Progress(stream=out)
    assert p.quiet
    _stages(p)
    assert out.getvalue() == "" and [k for k, _ in p.times] == ["briefs", "shells", "tiles"]


def test_notes_do_not_flood():
    out = io.StringIO()
    p = PG.Progress(quiet=False, stream=out)
    with p.stage("blender") as s:
        for k in range(100):
            s.note(f"view {k}")
    lines = out.getvalue().splitlines()
    assert len(lines) == 2 + PG.MAX_NOTES
    assert lines[-1].endswith(f"({100 - PG.MAX_NOTES} more notes)")


def test_blender_lines_drive_the_bar():
    """A stand-in for Blender printing its marks: each done advances, each start is a note;
    stderr is kept for the error message."""
    code = ("import sys\n"
            "for v in ('iso_d01', 'street_1'):\n"
            "    print('CGPROGRESS start', v, flush=True)\n"
            "    print('Fra:1 Mem:12M', flush=True)\n"
            "    print('CGPROGRESS done', v, flush=True)\n"
            "print('[ag6 1.0s] done', flush=True)\n"
            "print('a warning', file=sys.stderr)\n")
    out = io.StringIO()
    p = PG.Progress(quiet=False, stream=out)
    kept = []
    with p.stage("blender", total=2) as s:
        rc, so, se = run_blender([sys.executable, "-c", code], s, keep="[ag6", log=kept.append)
        assert s.done == 2
    assert rc == 0 and "Fra:1" in so and se.strip() == "a warning"
    assert kept == ["[ag6 1.0s] done"]
    assert "  iso_d01: rendering" in out.getvalue().splitlines()


def _cli(d, *extra):
    env = {k: v for k, v in os.environ.items() if k != "CYBERGEN_QUIET"}
    return subprocess.run([sys.executable, "-m", "assetgen", "build", str(d), "--workers", "2",
                           *extra], cwd=ROOT, env=env, capture_output=True, text=True)


def test_build_cli_quiet_and_piped(tmp_path):
    """`assetgen build` on a copy of the small city: --quiet prints nothing on stderr; piped,
    stderr is plain lines with each stage and the time per stage; the files are unchanged
    (the second run writes none), so no golden moves with progress on."""
    base = small_assets()
    d = copy_model(base, tmp_path / "p")
    shutil.copytree(base / "assets", d / "assets", symlinks=True)
    q = _cli(d, "--quiet")
    assert q.returncode == 0, q.stdout[-2000:] + q.stderr[-2000:]
    assert q.stderr == ""
    r = _cli(d)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "files written: 0" in r.stdout
    err = r.stderr
    assert "\r" not in err
    for stage in ("load", "briefs", "genomes", "shells and parts", "building checks",
                  "streets", "signage", "props", "materials: texel density"):
        assert f"{stage} ...\n" in err and f"{stage}: done in " in err, stage
    assert any(ln.startswith("genomes: ") and ln.endswith(" 100%") for ln in err.splitlines())
    tail = err.splitlines()[err.splitlines().index("time per stage:"):]
    assert tail[-1].split()[0] == "total" and len(tail) >= 12
    # stdout is the same report either way (but for its timings)
    assert re.sub(r"[0-9.]+", "#", r.stdout) == re.sub(r"[0-9.]+", "#", q.stdout)
