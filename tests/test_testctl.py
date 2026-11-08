"""tests/testctl.py: a run stopped and resumed, a run paused and resumed (Swagnik, 2026-11-08:
every test run can be paused)."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import testctl  # noqa: E402

STOPPING = '''
import os
import pathlib


def test_a():
    pass


def test_b():
    # asks the run to stop, as `testctl stop` does
    runs = sorted(pathlib.Path(os.environ["RUNS"]).iterdir())
    (runs[-1] / "stop").write_text("now")


def test_c():
    pass


def test_d():
    assert os.environ.get("FAIL_D") != "1"
'''

TICKING = '''
import os
import pathlib
import subprocess
import sys
import time

CHILD = """
import pathlib, sys, time
p = pathlib.Path(sys.argv[1])
for _ in range(600):
    with open(p, "a") as f:
        f.write("x")
    time.sleep(0.05)
"""


def test_ticks():
    ticks = pathlib.Path(os.environ["TICKS"])
    child = subprocess.Popen([sys.executable, "-c", CHILD, str(ticks) + ".child"])
    try:
        end = time.time() + 30
        while time.time() < end and not pathlib.Path(str(ticks) + ".done").exists():
            with open(ticks, "a") as f:
                f.write("x")
            time.sleep(0.05)
    finally:
        child.kill()
        child.wait()
'''


def _env(tmp: Path, **kw) -> dict:
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONPATH"] = str(HERE)
    env["RUNS"] = str(tmp / testctl.RUNS_DIR)
    env.update(kw)
    return env


def _cmd(tmp: Path, *args) -> list:
    return [sys.executable, "-m", "pytest", "-p", "testctl", "-p", "no:cacheprovider",
            "--rootdir", str(tmp), "-q", *args]


def _run(tmp: Path, *args, **env) -> subprocess.CompletedProcess:
    return subprocess.run(_cmd(tmp, *args), cwd=tmp, env=_env(tmp, **env),
                          capture_output=True, text=True, timeout=300)


def test_stop_then_resume_runs_only_what_is_left(tmp_path):
    (tmp_path / "test_stopping.py").write_text(STOPPING, encoding="utf-8")
    first = _run(tmp_path, "test_stopping.py")
    assert "2 passed" in first.stdout, first.stdout
    assert "--resume" in first.stdout          # the summary says how to continue
    (run,) = testctl.runs(tmp_path)
    info = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert info["state"] == "stopped" and info["selected"] == 4 and info["left"] == 2
    assert testctl.journal(run) == {"test_stopping.py::test_a": "passed",
                                    "test_stopping.py::test_b": "passed"}

    # the rest, one of them failing: the passed ones are left out
    second = _run(tmp_path, "test_stopping.py", "--resume", FAIL_D="1")
    assert "1 failed, 1 passed, 2 deselected" in second.stdout, second.stdout
    assert "1 failed, 3 passed in all over 2 parts" in second.stdout
    assert testctl.runs(tmp_path) == [run]     # the same run, its journal appended
    # a failure runs again on the next resume
    third = _run(tmp_path, "test_stopping.py", "--resume", run.name)
    assert "1 passed, 3 deselected" in third.stdout, third.stdout
    info = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert info["state"] == "finished" and info["left"] == 0 and info["resumes"] == 2
    assert info["args"] == _cmd(tmp_path, "test_stopping.py")[3:]   # without --resume
    assert info["tally"] == {"passed": 4}


def test_collect_only_starts_no_run(tmp_path):
    (tmp_path / "test_stopping.py").write_text(STOPPING, encoding="utf-8")
    out = _run(tmp_path, "test_stopping.py", "--collect-only")
    assert out.returncode == 0, out.stdout
    assert testctl.runs(tmp_path) == []


def _size(p: Path) -> int:
    return p.stat().st_size if p.exists() else 0


def _grows(p: Path, s: float = 1.5) -> bool:
    a = _size(p)
    time.sleep(s)
    return _size(p) > a


def test_pause_freezes_the_run_and_its_children(tmp_path, capsys):
    (tmp_path / "test_ticking.py").write_text(TICKING, encoding="utf-8")
    ticks = tmp_path / "ticks"
    child = Path(str(ticks) + ".child")
    proc = subprocess.Popen(_cmd(tmp_path, "test_ticking.py"), cwd=tmp_path,
                            env=_env(tmp_path, TICKS=str(ticks)), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        end = time.time() + 60
        while time.time() < end and not (_size(ticks) and _size(child)):
            time.sleep(0.2)
        assert _grows(ticks, 0.5) and _grows(child, 0.5)

        assert testctl.main(["--root", str(tmp_path), "pause"]) == 0
        time.sleep(0.5)                        # writes already under way land
        assert not _grows(ticks) and not _grows(child)
        testctl.main(["--root", str(tmp_path), "status"])
        assert "paused" in capsys.readouterr().out

        assert testctl.main(["--root", str(tmp_path), "resume"]) == 0
        assert _grows(ticks) and _grows(child)
    finally:
        Path(str(ticks) + ".done").write_text("done")
        out, _ = proc.communicate(timeout=120)
    assert proc.returncode == 0, out
    assert "1 passed" in out
