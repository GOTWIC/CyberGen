"""Progress on stderr (citygen/progress.py): plain lines when piped, nothing when quiet, the
relay of Unreal's and Blender's progress lines, the import's overall estimate."""

import io

from citygen import progress as PG


class Pipe(io.StringIO):
    def isatty(self):
        return False


def lines(buf):
    return [ln for ln in buf.getvalue().splitlines() if ln]


def test_piped_stage_writes_a_few_plain_lines():
    buf = Pipe()
    p = PG.Progress(quiet=False, stream=buf)
    with p.stage("lots", total=8) as s:
        for _ in range(8):
            s.advance()
        s.note("chunk 3 rebuilt")
    out = lines(buf)
    assert out[0] == "lots: started (8)"
    assert [ln.split("] ")[1].split()[0] for ln in out if "[" in ln] == ["2/8", "4/8", "6/8"]
    assert "lots: chunk 3 rebuilt" in out
    assert out[-1].startswith("lots: done in ") and out[-1].endswith("(8)")
    assert "\r" not in buf.getvalue()


def test_stage_without_count_and_summary():
    buf = Pipe()
    p = PG.Progress(quiet=False, stream=buf)
    with p.stage("shells") as s:
        s.set_total(None)
    with p.stage("shells"):
        pass
    p.summary()
    out = lines(buf)
    assert out[0] == "shells: started" and out[1].startswith("shells: done in")
    assert out[-3] == "times:"
    row = out[-2]
    assert "(2 runs)" in row
    assert out[-1].strip().startswith("total")


def test_notes_never_flood():
    buf = Pipe()
    p = PG.Progress(quiet=False, stream=buf)
    with p.stage("roads") as s:
        for i in range(100):
            s.note(f"variant {i}")
    assert len(lines(buf)) == 2 + PG.NOTES_PER_STAGE + 1


def test_quiet_and_env(monkeypatch):
    buf = Pipe()
    p = PG.Progress(quiet=True, stream=buf)
    with p.stage("x", total=3) as s:
        s.advance(3)
    p.summary()
    assert buf.getvalue() == ""
    monkeypatch.setenv("CYBERGEN_QUIET", "1")
    assert PG.Progress(stream=Pipe()).quiet
    monkeypatch.setenv("CYBERGEN_QUIET", "0")
    assert not PG.Progress(stream=Pipe()).quiet


def test_failed_stage_says_so():
    buf = Pipe()
    p = PG.Progress(quiet=False, stream=buf)
    try:
        with p.stage("blender"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert lines(buf)[-1].startswith("blender: stopped after")


def test_active_is_silent_unless_used():
    assert isinstance(PG.active(), PG._Null)
    with PG.active().stage("x", total=2) as s:     # library code with no command: nothing
        s.advance()
    buf = Pipe()
    p = PG.Progress(quiet=False, stream=buf)
    with PG.use(p):
        assert PG.active() is p
    assert isinstance(PG.active(), PG._Null)


def test_relay_reads_marker_lines():
    buf = Pipe()
    p = PG.Progress(quiet=False, stream=buf)
    other = []
    r = PG.Relay(p, {"meshes2": "stage 2 packs and meshes"}, on_other=other.append)
    r.open("start")
    feed = ["[2026.10.29-06.18.29:709][  0]LogPython: plain editor line",
            "LogPython: " + PG.marker("plan", first=True, actors=10),
            "LogPython: " + PG.marker("begin", label="meshes2", total=4),
            "LogPython: " + PG.marker("update", done=2, detail="2 meshes built"),
            "LogPython: " + PG.marker("note", text="deleting 3 meshes"),
            "LogPython: " + PG.marker("update", done=4),
            "LogPython: " + PG.marker("end")]
    assert [r.feed(ln) for ln in feed] == [False, True, True, True, True, True, True]
    r.close()
    out = lines(buf)
    assert out[0] == "start: started" and out[1].startswith("start: done in")
    assert out[2] == "stage 2 packs and meshes: started (4)"
    assert any("2/4" in ln and "2 meshes built" in ln for ln in out)
    assert "stage 2 packs and meshes: deleting 3 meshes" in out
    assert out[-1].startswith("stage 2 packs and meshes: done in")
    assert other == [{"op": "plan", "first": True, "actors": 10}]


def test_pump_keeps_the_log_byte_for_byte():
    from citygen import unreal as U

    text = (b"LogInit: start\r\n" + (PG.marker("begin", label="actors", total=2) + "\n").encode()
            + b"LogPython: \xc3\xa9t\xc3\xa9\n" + b"CITYGEN_UE_DONE {\"ok\": true}\n")

    class Proc:
        stdout = io.BytesIO(text)

    log = io.BytesIO()
    p = PG.Progress(quiet=False, stream=Pipe())
    r = PG.Relay(p, U.STAGE_LABELS)
    U._pump(Proc(), log, r)
    r.close()
    assert log.getvalue() == text
    assert [x[0] for x in p.times] == ["actors", "editor shutdown"]


def test_import_estimate():
    from citygen import unreal as U

    p = PG.Progress(quiet=True, stream=Pipe())
    e = U.ImportEstimate(p)
    e.plan({"op": "plan", "first": False, "actors": 1000})
    assert e.prior is None and e.text() == ""
    counts = {"op": "plan", "first": True, "objects": 4587, "tiles": 256, "actors": 38988,
              "packs": 603, "meshes2": 28230, "textures": 276}
    e.plan(counts)
    full = sum(f(counts) for f in U.FIRST_IMPORT_S.values())
    assert abs(e.left() - full) < 1e-6
    # the editor's start says nothing of the machine's speed
    e.begin("start", None)
    e.end("start", 5.0)
    assert abs(e.left() - (full - U.FIRST_IMPORT_S["start"](counts))) < 1e-6
    # a stage twice as fast as its estimate: the rest faster, but damped
    prior = U.FIRST_IMPORT_S["meshes2"](counts)
    e.begin("meshes2", None)
    e.end("meshes2", prior / 2)
    speed = (prior / 2 + U.SPEED_DAMP_S) / (prior + U.SPEED_DAMP_S)
    rest = sum(f(counts) for k, f in U.FIRST_IMPORT_S.items() if k not in ("start", "meshes2"))
    assert abs(e.left() - rest * speed) < 1e-6
    assert 0.5 < speed < 1.0


def test_import_estimate_with_no_progress():
    # a library call (no command, so no Progress): the estimate's stages are null stages
    from citygen import unreal as U

    p = PG.active()
    e = U.ImportEstimate(p)
    r = PG.Relay(p, U.STAGE_LABELS, on_begin=e.begin, on_end=e.end, on_other=e.plan)
    r.open("start")
    for op, f in (("plan", {"first": True, "objects": 10, "tiles": 2, "actors": 20,
                            "packs": 1, "meshes2": 5, "textures": 0}),
                  ("begin", {"label": "meshes2", "total": 5}), ("update", {"done": 2}),
                  ("end", {})):
        assert r.feed("LogPython: " + PG.marker(op, **f))
    assert e.text().startswith("about ")
    r.close()


def test_copy_keeps_copying_when_progress_fails(capsys):
    from citygen import unreal as U

    text = b"".join(f"line {i}\n".encode() for i in range(5000))

    class Proc:
        stdout = io.BytesIO(text)

    seen = []

    def on_line(line):
        seen.append(line)
        raise AttributeError("boom")

    log = io.BytesIO()
    U._copy(Proc(), log, on_line)
    assert log.getvalue() == text and len(seen) == 1
    assert "no longer shown" in capsys.readouterr().err


def test_runner_ticks_per_job():
    from citygen import build as B

    ticks = []
    run = B._Runner(1)
    out = run.map(lambda x, worker: x * 2, [(1,), (2,), (3,)], lambda: ticks.append(1))
    assert out == [2, 4, 6] and len(ticks) == 3
    wait = run.submit(lambda x, worker: x + 1, [(1,), (2,)], lambda: ticks.append(1))
    assert wait() == [2, 3] and len(ticks) == 5


def test_streamed_does_not_wait_for_a_child_holding_the_pipe(tmp_path, monkeypatch):
    import sys
    import time

    from citygen import unreal as U

    monkeypatch.setattr(U, "PIPE_GRACE_S", 0.5)
    code = ("import subprocess, sys; "
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)']); "
            f"print({PG.marker('begin', label='actors', total=1)!r}, flush=True); "
            "print('done', flush=True)")
    seen = []
    t = time.time()
    rc = U._streamed([sys.executable, "-c", code], tmp_path / "log.txt", seen.append, 30)
    assert rc == 0 and time.time() - t < 10
    assert any(PG.MARKER in ln for ln in seen)
    # (the copy is byte for byte: a child's print ends its lines with \r\n on Windows)
    assert (tmp_path / "log.txt").read_bytes().endswith((b"done\n", b"done\r\n"))


def test_time_left_from_when_the_count_is_known(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(PG.time, "monotonic", lambda: now[0])
    p = PG.Progress(quiet=True, stream=Pipe())
    s = p.begin("HLOD build")
    now[0] += 120.0                 # setting up, no count yet
    s.set_total(100)
    now[0] += 10.0
    s.update(10)
    assert abs(s.left_s() - 90.0) < 1e-9      # 10 per 10 s since the count, not since start
    s.finish()
