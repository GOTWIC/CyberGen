"""Pause, stop and resume pytest runs (Swagnik, 2026-11-08: every test run can be paused).

Two halves, stdlib only:

- **The plugin** (its hooks are imported into `tests/conftest.py`, so every pytest run in the
  repo has it): each run gets a folder `.pytest_runs/<run id>/` at the checkout's root with
  `run.json` (pid, arguments, tests selected, state), `current.txt` (the test running now)
  and `journal.jsonl` (one line per finished test and its outcome, flushed as it goes, so it
  survives a crash, a kill or a reboot). `pytest ... --resume [RUN]` runs the same selection
  again leaving out every test the journal has passed or skipped (failures and errors run
  again), appends to the same journal and ends with the whole run's tally.
- **The command** (`python tests/testctl.py ...`, from the checkout whose tests run):
  - `status [RUN]`: the runs, how far each got, what runs now, the command to continue;
  - `pause [RUN]`: freezes the run now, pytest and every process it started (build workers,
    Blender, Unreal): no CPU, the memory kept (Windows pages it out when it needs it);
  - `resume [RUN]`: unfreezes it, where it was;
  - `stop [RUN]`: ends it cleanly after the test that runs now (also thaws a paused run);
    then `pytest <same arguments> --resume` continues it, even after a restart.

A frozen run does not survive a restart, and a test that times a child process can see the
pause as time spent: for a long break or a restart use `stop`. RUN defaults to the newest
run of the checkout (`--root DIR` for another checkout, `.` by default).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RUNS_DIR = ".pytest_runs"
KEEP_RUNS = 20
DONE = ("passed", "skipped")


# ---------------------------------------------------------------- run folders


def runs_root(root: Path) -> Path:
    return Path(root) / RUNS_DIR


def _read(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(p: Path, data: dict) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def runs(root: Path) -> list[Path]:
    """The checkout's run folders, oldest first (ids sort by start time)."""
    base = runs_root(root)
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if (p / "run.json").is_file())


def find_run(root: Path, run: str | None) -> Path:
    found = runs(root)
    if not found:
        raise SystemExit(f"no test runs under {runs_root(root)}")
    if run is None:
        return found[-1]
    for p in found:
        if p.name == run or p.name.startswith(run):
            return p
    raise SystemExit(f"no run {run!r} under {runs_root(root)}")


def journal(run_dir: Path) -> dict[str, str]:
    """The last outcome of each finished test."""
    out: dict[str, str] = {}
    p = run_dir / "journal.jsonl"
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:          # a line cut short by a crash
            continue
        out[row["nodeid"]] = row["outcome"]
    return out


def tally(outcomes: dict[str, str]) -> dict[str, int]:
    t: dict[str, int] = {}
    for o in outcomes.values():
        t[o] = t.get(o, 0) + 1
    return t


def _prune(root: Path, keep: int = KEEP_RUNS) -> None:
    import shutil
    old = runs(root)[:-keep] if keep else runs(root)
    for p in old:
        if _read(p / "run.json").get("state") in ("finished", "stopped", "interrupted"):
            shutil.rmtree(p, ignore_errors=True)


# ---------------------------------------------------------------- the plugin


class _Run:
    def __init__(self, session, run_dir: Path, info: dict, done: dict[str, str]):
        self.session, self.dir, self.info, self.done = session, run_dir, info, done
        self.outcomes: dict[str, str] = {}
        self.fh = open(run_dir / "journal.jsonl", "a", encoding="utf-8")

    def save(self, **kw) -> None:
        """(never fails the run: a reader holding run.json for a moment is waited out, then
        the write is left for the next one)"""
        self.info.update(kw)
        for _ in range(5):
            try:
                _write(self.dir / "run.json", self.info)
                return
            except OSError:
                time.sleep(0.2)


_RUN: _Run | None = None


def pytest_addoption(parser):
    g = parser.getgroup("testctl", "pause, stop and resume (tests/testctl.py)")
    g.addoption("--resume", action="store", nargs="?", const="latest", default=None,
                metavar="RUN",
                help="continue a stopped or broken run (default the newest): leave out "
                     "the tests its journal has passed or skipped")


def _active(config) -> bool:
    o = config.option
    return not (getattr(o, "collectonly", False) or getattr(o, "help", False)
                or getattr(o, "version", False) or getattr(o, "showfixtures", False)
                or getattr(o, "markers", False))


def pytest_sessionstart(session):
    global _RUN
    config = session.config
    if not _active(config) or hasattr(config, "workerinput"):
        return
    root = Path(config.rootpath)
    want = config.getoption("resume")
    args, drop = [], False
    for a in map(str, config.invocation_params.args):
        if drop:
            drop = False
            if a == want:
                continue
        if a == "--resume":
            drop = True
            continue
        if a.startswith("--resume="):
            continue
        args.append(a)
    if want:
        run_dir = find_run(root, None if want == "latest" else want)
        info = _read(run_dir / "run.json")
        done = {k: v for k, v in journal(run_dir).items() if v in DONE}
        info["resumes"] = info.get("resumes", 0) + 1
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        run_dir = runs_root(root) / f"{stamp}-{os.getpid()}"
        run_dir.mkdir(parents=True, exist_ok=True)
        info = {"id": run_dir.name, "args": args, "cwd": str(Path.cwd()),
                "started": time.strftime("%Y-%m-%d %H:%M:%S"), "resumes": 0}
        done = {}
    info.update(pid=os.getpid(), state="running", python=sys.executable)
    info.pop("frozen", None)
    for flag in ("stop", "frozen"):
        (run_dir / flag).unlink(missing_ok=True)
    _RUN = _Run(session, run_dir, info, done)
    _RUN.save()
    try:
        _prune(root)
    except OSError:
        pass


def pytest_collection_modifyitems(session, config, items):
    if _RUN is None:
        return
    keep, skip = [], []
    for it in items:
        (skip if _RUN.done.get(it.nodeid) in DONE else keep).append(it)
    if skip:
        config.hook.pytest_deselected(items=skip)
        items[:] = keep
    total = _RUN.info.get("selected") if _RUN.info.get("resumes") else None
    _RUN.save(selected=total or len(items) + len(skip), to_run=len(items), skipped_done=len(skip))


def pytest_runtest_logstart(nodeid, location):
    if _RUN is None:
        return
    if (_RUN.dir / "stop").exists():
        return
    (_RUN.dir / "current.txt").write_text(nodeid + "\n", encoding="utf-8")


def pytest_runtest_logreport(report):
    if _RUN is None:
        return
    prev = _RUN.outcomes.get(report.nodeid)
    if report.failed:
        out = "failed" if report.when == "call" else "error"
    elif report.skipped:
        out = "skipped"
    else:
        out = "passed"
    if prev in ("failed", "error") or (prev == "skipped" and out == "passed"):
        out = prev
    _RUN.outcomes[report.nodeid] = out


def pytest_runtest_logfinish(nodeid, location):
    if _RUN is None:
        return
    out = _RUN.outcomes.get(nodeid, "error")
    _RUN.fh.write(json.dumps({"nodeid": nodeid, "outcome": out,
                              "at": time.strftime("%H:%M:%S")}) + "\n")
    _RUN.fh.flush()
    # `testctl stop`: pytest looks at shouldstop once a test's protocol returns, so the run
    # ends right after this test
    if (_RUN.dir / "stop").exists():
        _RUN.session.shouldstop = "stopped by tests/testctl.py stop"


def pytest_sessionfinish(session, exitstatus):
    if _RUN is None:
        return
    _RUN.fh.close()
    stopped = (_RUN.dir / "stop").exists()
    (_RUN.dir / "stop").unlink(missing_ok=True)
    every = journal(_RUN.dir)
    left = _RUN.info.get("selected", 0) - sum(1 for v in every.values() if v in DONE)
    state = "stopped" if stopped else ("interrupted" if exitstatus == 2 else "finished")
    _RUN.save(state=state, ended=time.strftime("%Y-%m-%d %H:%M:%S"), tally=tally(every),
              left=max(left, 0))


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if _RUN is None:
        return
    every = journal(_RUN.dir)
    t = tally(every)
    tr = terminalreporter
    tr.write_sep("-", "testctl")
    tr.write_line(f"run {_RUN.dir.name} ({_RUN.dir}): "
                  + ", ".join(f"{n} {k}" for k, n in sorted(t.items())) + " in all"
                  + (f" over {_RUN.info.get('resumes', 0) + 1} parts"
                     if _RUN.info.get("resumes") else ""))
    if _RUN.info.get("resumes"):
        bad = sorted(k for k, v in every.items() if v in ("failed", "error"))
        for k in bad:
            tr.write_line(f"  {every[k].upper()} {k}")
    sel = _RUN.info.get("selected", 0)
    finished = sum(1 for v in every.values() if v in DONE)
    if (_RUN.dir / "stop").exists() or finished < sel:
        tr.write_line(f"{sel - finished} of {sel} tests still to pass; continue with: "
                      + continue_command(_RUN.info))


def continue_command(info: dict) -> str:
    args = " ".join(_quote(a) for a in info.get("args", []))
    return f"python -m pytest {args} --resume {info.get('id', '')}".replace("  ", " ")


def _quote(a: str) -> str:
    return f'"{a}"' if (" " in a or not a) else a


# ---------------------------------------------------------------- processes


def _tree_posix(pid: int) -> list[int]:
    out = subprocess.run(["ps", "-A", "-o", "pid=", "-o", "ppid="], capture_output=True,
                         text=True, check=True).stdout
    kids: dict[int, list[int]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2:
            kids.setdefault(int(parts[1]), []).append(int(parts[0]))
    tree, todo = [], [pid]
    while todo:
        p = todo.pop()
        tree.append(p)
        todo.extend(kids.get(p, []))
    return tree


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes as _wt

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll")
    _k32.CreateToolhelp32Snapshot.restype = _wt.HANDLE
    _k32.CreateToolhelp32Snapshot.argtypes = [_wt.DWORD, _wt.DWORD]
    _k32.OpenProcess.restype = _wt.HANDLE
    _k32.OpenProcess.argtypes = [_wt.DWORD, _wt.BOOL, _wt.DWORD]
    _k32.CloseHandle.argtypes = [_wt.HANDLE]
    _k32.GetProcessTimes.argtypes = [_wt.HANDLE] + [ctypes.POINTER(_wt.FILETIME)] * 4
    _ntdll.NtSuspendProcess.argtypes = [_wt.HANDLE]
    _ntdll.NtResumeProcess.argtypes = [_wt.HANDLE]

    class _Entry(ctypes.Structure):
        _fields_ = [("dwSize", _wt.DWORD), ("cntUsage", _wt.DWORD),
                    ("th32ProcessID", _wt.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", _wt.DWORD), ("cntThreads", _wt.DWORD),
                    ("th32ParentProcessID", _wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", _wt.DWORD), ("szExeFile", _wt.WCHAR * 260)]

    _k32.Process32FirstW.argtypes = [_wt.HANDLE, ctypes.POINTER(_Entry)]
    _k32.Process32NextW.argtypes = [_wt.HANDLE, ctypes.POINTER(_Entry)]
    _QUERY, _SUSPEND = 0x1000, 0x0800

    def _created(pid: int) -> int | None:
        """A live process's creation time; None for no such process or one that has ended
        (still open somewhere, its exit time is set)."""
        h = _k32.OpenProcess(_QUERY, False, pid)
        if not h:
            return None
        try:
            c, e, k, u = (_wt.FILETIME() for _ in range(4))
            if not _k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k),
                                        ctypes.byref(u)):
                return None
            if e.dwHighDateTime or e.dwLowDateTime:
                return None
            return (c.dwHighDateTime << 32) | c.dwLowDateTime
        finally:
            _k32.CloseHandle(h)

    def _tree_win(pid: int) -> list[int]:
        snap = _k32.CreateToolhelp32Snapshot(0x2, 0)
        if snap is None or snap == _wt.HANDLE(-1).value:
            raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot")
        kids: dict[int, list[int]] = {}
        try:
            e = _Entry()
            e.dwSize = ctypes.sizeof(_Entry)
            ok = _k32.Process32FirstW(snap, ctypes.byref(e))
            while ok:
                kids.setdefault(e.th32ParentProcessID, []).append(e.th32ProcessID)
                ok = _k32.Process32NextW(snap, ctypes.byref(e))
        finally:
            _k32.CloseHandle(snap)
        # (a parent id can be reused after its process ends: a child counts only when it was
        # created after its parent)
        tree, todo = [], [(pid, _created(pid))]
        while todo:
            p, born = todo.pop()
            if born is None:
                continue
            tree.append(p)
            for c in kids.get(p, []):
                cb = _created(c)
                if c != p and cb is not None and cb >= born:
                    todo.append((c, cb))
        return tree

    def _signal(pids: list[int], freeze: bool) -> list[int]:
        done = []
        for p in pids:
            h = _k32.OpenProcess(_SUSPEND, False, p)
            if not h:
                continue
            try:
                st = (_ntdll.NtSuspendProcess if freeze else _ntdll.NtResumeProcess)(h)
                if st == 0:
                    done.append(p)
            finally:
                _k32.CloseHandle(h)
        return done


def process_tree(pid: int) -> list[int]:
    """The process and every process it started, the process first."""
    return _tree_win(pid) if sys.platform == "win32" else _tree_posix(pid)


def freeze(pid: int) -> list[int]:
    """Suspends the tree (the parent first, so it starts nothing more; then a second look for
    children started meanwhile)."""
    hit: list[int] = []
    for _ in range(2):
        todo = [p for p in process_tree(pid) if p not in hit]
        if sys.platform == "win32":
            hit += _signal(todo, True)
        else:
            import signal
            for p in todo:
                try:
                    os.kill(p, signal.SIGSTOP)
                    hit.append(p)
                except OSError:
                    pass
    return hit


def thaw(pids: list[int]) -> list[int]:
    if sys.platform == "win32":
        return _signal(list(reversed(pids)), False)
    import signal
    done = []
    for p in reversed(pids):
        try:
            os.kill(p, signal.SIGCONT)
            done.append(p)
        except OSError:
            pass
    return done


def alive(pid: int) -> bool:
    if sys.platform == "win32":
        return _created(pid) is not None
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- the command


def _state(run_dir: Path) -> tuple[dict, str]:
    info = _read(run_dir / "run.json")
    state = info.get("state", "?")
    if state == "running":
        if (run_dir / "frozen").exists():
            state = "paused"
        elif not alive(int(info.get("pid", 0))):
            state = "broken off (its process is gone)"
    return info, state


def cmd_status(root: Path, run: str | None) -> int:
    targets = [find_run(root, run)] if run else runs(root)[::-1][:5]   # newest first
    if not targets:
        print(f"no test runs under {runs_root(root)}")
        return 0
    for d in targets:
        info, state = _state(d)
        j = journal(d)
        t = tally(j)
        sel = info.get("selected", 0)
        fin = sum(1 for v in j.values() if v in DONE)
        print(f"{d.name}: {state}; {len(j)} of {sel} tests run ("
              + (", ".join(f"{n} {k}" for k, n in sorted(t.items())) or "none") + ")"
              + f"; started {info.get('started', '?')}"
              + ({0: "", 1: ", resumed once"}.get(info.get("resumes", 0),
                                                  f", resumed {info.get('resumes')} times")))
        print(f"  pytest {' '.join(info.get('args', []))}  (pid {info.get('pid')})")
        cur = d / "current.txt"
        if state in ("running", "paused") and cur.is_file():
            print(f"  now: {cur.read_text(encoding='utf-8').strip()}")
        bad = [k for k, v in j.items() if v in ("failed", "error")]
        for k in bad[:10]:
            print(f"  {j[k]}: {k}")
        if state not in ("running", "paused") and fin < sel:
            print(f"  continue: {continue_command(info)}")
    return 0


def cmd_pause(root: Path, run: str | None) -> int:
    d = find_run(root, run)
    info, state = _state(d)
    if state == "paused":
        print(f"{d.name} is already paused")
        return 0
    if state != "running":
        print(f"{d.name} is not running ({state})")
        return 1
    pids = freeze(int(info["pid"]))
    _write(d / "frozen", {"pids": pids, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    cur = (d / "current.txt").read_text(encoding="utf-8").strip() if (d / "current.txt").is_file() else "?"
    print(f"paused {d.name}: {len(pids)} processes frozen, in {cur}")
    print(f"resume with: python tests/testctl.py resume {d.name}")
    return 0


def cmd_resume(root: Path, run: str | None) -> int:
    d = find_run(root, run)
    fz = d / "frozen"
    if not fz.exists():
        info, state = _state(d)
        print(f"{d.name} is not paused ({state})")
        if state not in ("running",) and info.get("selected", 0) > sum(
                1 for v in journal(d).values() if v in DONE):
            print(f"to continue it: {continue_command(info)}")
        return 1
    pids = _read(fz).get("pids", [])
    thawed = thaw(pids)
    fz.unlink(missing_ok=True)
    print(f"resumed {d.name}: {len(thawed)} of {len(pids)} processes")
    return 0


def cmd_stop(root: Path, run: str | None) -> int:
    d = find_run(root, run)
    info, state = _state(d)
    if state not in ("running", "paused"):
        print(f"{d.name} is not running ({state})")
        return 1
    (d / "stop").write_text(time.strftime("%Y-%m-%d %H:%M:%S") + "\n", encoding="utf-8")
    if state == "paused":
        cmd_resume(root, d.name)
    print(f"{d.name} stops after the test running now; continue later with:")
    print(f"  {continue_command(info)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tests/testctl.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=".", help="the checkout whose runs to control (default .)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, hlp in (("status", "the runs and how far each got"),
                      ("pause", "freeze a run now (pytest and everything it started)"),
                      ("resume", "unfreeze a paused run"),
                      ("stop", "end a run after the test running now")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("run", nargs="?", help="run id or its start (default the newest)")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    return {"status": cmd_status, "pause": cmd_pause, "resume": cmd_resume,
            "stop": cmd_stop}[a.cmd](root, a.run)


if __name__ == "__main__":
    sys.exit(main())
