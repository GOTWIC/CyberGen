"""Progress on stderr for the long commands (`citygen build`, `citygen blockout`, `citygen
unreal`; assetgen uses it too). Stdlib only.

    from citygen.progress import Progress

    p = Progress(quiet=None)            # quiet=None reads $CYBERGEN_QUIET=1; writes to stderr
    with p.stage("shells", total=None) as s:   # start line; on exit "shells: done in 12.3 s"
        s.set_total(n)                  # a known count: a bar with n of N, percent, time left
        s.advance(k=1)                  # or s.update(done)
        s.note("tile e3n2 rebuilt")     # an extra plain line, never floods
    p.summary()                         # elapsed per stage at the end

On a terminal one line is redrawn in place (`label [#######.....] 1234/5678 22% 3m10s left`,
ASCII and a carriage return, so the Mac terminal and Windows PowerShell draw it alike). Piped
to a file or another program it writes plain lines: at 0, 25, 50, 75 and 100 percent, or
every 30 s, whichever comes first. Worker processes never print: the parent advances as their
results come back. Nothing here touches an output file.

Library code reports through `active()`, which is silent unless a command made a Progress
the active one (`use`). Programs that run elsewhere (the Unreal importer, the Blender
builder) print `MARKER {json}` lines that `Relay` turns into the same calls.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from contextlib import contextmanager

MARKER = "CYBERGEN_PROGRESS"     # lines from Unreal or Blender: MARKER {"op": ..., ...}
QUARTERS = (0, 25, 50, 75, 100)
PLAIN_EVERY_S = 30.0             # a plain line at least this often while a stage runs
REDRAW_S = 0.1                   # at most ten redraws a second on a terminal
TICK_S = 1.0                     # the elapsed time on a terminal moves on its own
NOTES_PER_STAGE = 12             # notes after these are counted, not printed
BAR = 20


def fmt_s(s: float) -> str:
    """12.3 s, 3m10s, 1h05m."""
    if s < 60:
        return f"{s:.1f} s"
    s = int(round(s))
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


class Stage:
    def __init__(self, progress: "Progress", label: str, total: int | None):
        self.p = progress
        self.label = label
        self.total = total
        self.done = 0
        self.t0 = time.monotonic()
        self.last_line = self.t0
        self.quarter = -1
        self.notes = 0
        self.closed = False
        self.detail = ""
        # where the rate is measured from: when the count became known (a stage can spend a
        # while setting up before it knows how much there is)
        self.rate0 = (self.t0, 0) if total else None

    # -- the interface --

    def set_total(self, n: int | None) -> None:
        with self.p.lock:
            self.total = None if n is None else max(0, int(n))
            self._known()
            self.p._changed(self)

    def _known(self) -> None:
        if self.total and self.rate0 is None:
            self.rate0 = (time.monotonic(), self.done)

    def advance(self, k: int = 1) -> None:
        with self.p.lock:
            self.done += k
            self.p._changed(self)

    def update(self, done: int, total: int | None = None, detail: str | None = None) -> None:
        with self.p.lock:
            restart = total is not None and self.total and int(total) != self.total
            if total is not None:
                self.total = max(0, int(total))
                self._known()
            if detail is not None:
                self.detail = detail
            self.done = int(done)
            if restart:
                # (the stage counts something else now: its rate starts again)
                self.rate0 = (time.monotonic(), self.done)
            self.p._changed(self)

    def note(self, text: str) -> None:
        with self.p.lock:
            self.notes += 1
            if self.notes <= NOTES_PER_STAGE:
                self.p._line(f"{self.label}: {text}")
            elif self.notes == NOTES_PER_STAGE + 1:
                self.p._line(f"{self.label}: (more notes not shown)")

    # -- additions --

    def finish(self, ok: bool = True) -> float:
        """Close the stage (what leaving the `with` does); its elapsed seconds."""
        with self.p.lock:
            if self.closed:
                return self.elapsed()
            self.closed = True
            dt = self.elapsed()
            self.p._close(self, dt, ok)
            return dt

    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def left_s(self) -> float | None:
        """Seconds left at the rate since the count was known (None before there is one)."""
        if not self.total or self.rate0 is None:
            return None
        dt = time.monotonic() - self.rate0[0]
        n = self.done - self.rate0[1]
        if n <= 0 or dt < 1.0:
            return None
        return max(0.0, (self.total - self.done) * dt / n)

    def text(self, width: int | None = None) -> str:
        dt = self.elapsed()
        if self.total:
            frac = min(1.0, self.done / self.total)
            fill = int(round(frac * BAR))
            left = self.left_s()
            s = (f"{self.label} [{'#' * fill}{'.' * (BAR - fill)}] {self.done}/{self.total} "
                 f"{int(frac * 100)}%" + (f" {fmt_s(left)} left" if left is not None else ""))
        else:
            s = f"{self.label} ... {fmt_s(dt)}" + (f" ({self.done})" if self.done else "")
        if self.detail:
            s += f", {self.detail}"
        extra = self.p.extra() if callable(self.p.extra) else self.p.extra
        if extra:
            s += f" | {extra}"
        if width:
            s = s[:max(10, width - 1)]
        return s


class Progress:
    def __init__(self, quiet: bool | None = None, stream=None):
        if quiet is None:
            quiet = os.environ.get("CYBERGEN_QUIET", "").strip() == "1"
        self.quiet = bool(quiet)
        self.stream = stream if stream is not None else sys.stderr
        isatty = getattr(self.stream, "isatty", None)
        self.tty = (not self.quiet) and bool(isatty and isatty())
        self.lock = threading.RLock()
        self.current: Stage | None = None
        self.times: list[tuple[str, float, bool]] = []
        self.t0 = time.monotonic()
        self.drawn = 0           # length of the line drawn in place (a terminal)
        self.last_draw = 0.0
        self.extra = ""          # appended to the drawn line (an overall estimate, say)
        self._ticker: threading.Thread | None = None

    # -- the interface --

    @contextmanager
    def stage(self, label: str, total: int | None = None):
        s = self.begin(label, total)
        try:
            yield s
        except BaseException:
            s.finish(ok=False)
            raise
        s.finish()

    def summary(self) -> None:
        """Elapsed per stage (a stage run more than once: its sum and count), the total."""
        if self.quiet or not self.times:
            return
        with self.lock:
            sums: dict[str, list] = {}
            for label, dt, _ in self.times:
                sums.setdefault(label, [0.0, 0])
                sums[label][0] += dt
                sums[label][1] += 1
            w = max(len(k) for k in sums)
            lines = ["times:"]
            for k, (dt, n) in sums.items():
                lines.append(f"  {k.ljust(w)}  {fmt_s(dt).rjust(8)}" + (f"  ({n} runs)"
                                                                         if n > 1 else ""))
            lines.append(f"  {'total'.ljust(w)}  {fmt_s(time.monotonic() - self.t0).rjust(8)}")
            for ln in lines:
                self._line(ln)

    # -- additions --

    def begin(self, label: str, total: int | None = None) -> Stage:
        """A stage without a `with` (one an Unreal or Blender marker opens)."""
        with self.lock:
            if self.current is not None and not self.current.closed:
                self.current.finish()
            s = Stage(self, label, total)
            self.current = s
            if not self.quiet:
                if self.tty:
                    self._draw(s, force=True)
                else:
                    self._line(f"{label}: started" + (f" ({total})" if total else ""))
                    s.quarter = 0 if total else -1
                self._start_ticker()
            return s

    def note(self, text: str) -> None:
        """A plain line outside any stage."""
        with self.lock:
            self._line(text)

    def set_extra(self, text) -> None:
        """Text (or a function giving it) shown after the stage's own: an overall estimate."""
        with self.lock:
            self.extra = text

    # -- drawing --

    def _width(self) -> int:
        return shutil.get_terminal_size((100, 24)).columns

    def _write(self, text: str) -> None:
        try:
            self.stream.write(text)
            self.stream.flush()
        except (OSError, ValueError, UnicodeEncodeError):
            pass

    def _clear(self) -> None:
        if self.tty and self.drawn:
            self._write("\r" + " " * self.drawn + "\r")
            self.drawn = 0

    def _line(self, text: str) -> None:
        if self.quiet:
            return
        self._clear()
        self._write(text + "\n")
        if self.tty and self.current is not None and not self.current.closed:
            self._draw(self.current, force=True)

    def _draw(self, s: Stage, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last_draw < REDRAW_S:
            return
        self.last_draw = now
        text = s.text(self._width())
        self._write("\r" + text + " " * max(0, self.drawn - len(text)))
        self.drawn = max(len(text), self.drawn)

    def _changed(self, s: Stage) -> None:
        if self.quiet or s.closed:
            return
        if self.tty:
            self._draw(s)
            return
        now = time.monotonic()
        q = -1
        if s.total:
            pct = 100 * min(s.done, s.total) // s.total
            q = max(x for x in QUARTERS if x <= pct)
        if (q > s.quarter and q < 100) or now - s.last_line >= PLAIN_EVERY_S:
            s.quarter = max(s.quarter, q)
            s.last_line = now
            self._write(s.text() + "\n")

    def _tick(self) -> None:
        """A terminal's elapsed time and a pipe's 30 s lines while nothing reports."""
        with self.lock:
            s = self.current
            if s is None or s.closed or self.quiet:
                return
            if self.tty:
                self._draw(s, force=True)
            elif time.monotonic() - s.last_line >= PLAIN_EVERY_S:
                s.last_line = time.monotonic()
                self._write(s.text() + "\n")

    def _start_ticker(self) -> None:
        if self._ticker is not None:
            return

        def run():
            while True:
                time.sleep(TICK_S)
                self._tick()

        self._ticker = threading.Thread(target=run, name="progress", daemon=True)
        self._ticker.start()

    def _close(self, s: Stage, dt: float, ok: bool) -> None:
        self.times.append((s.label, dt, ok))
        if self.current is s:
            self.current = None
        if self.quiet:
            return
        self._clear()
        what = f"done in {fmt_s(dt)}" if ok else f"stopped after {fmt_s(dt)}"
        count = f" ({s.done} of {s.total})" if s.total and s.done < s.total and ok else \
            (f" ({s.total})" if s.total else "")
        self._write(f"{s.label}: {what}{count}\n")


class _Null:
    """What `active()` hands out when no command asked for progress: does nothing."""

    quiet = True

    @contextmanager
    def stage(self, label, total=None):
        yield _NullStage()

    def begin(self, label, total=None):
        return _NullStage()

    def note(self, text):
        pass

    def summary(self):
        pass

    def set_extra(self, text):
        pass


class _NullStage:
    total = None
    done = 0

    def set_total(self, n):
        pass

    def advance(self, k=1):
        pass

    def update(self, done, total=None, detail=None):
        pass

    def note(self, text):
        pass

    def finish(self, ok=True):
        return 0.0


_ACTIVE: list = [None]


def active():
    """The command's Progress, else one that prints nothing (library calls, tests, worker
    processes: a spawned worker starts with none)."""
    return _ACTIVE[0] if _ACTIVE[0] is not None else _Null()


@contextmanager
def use(p: Progress):
    """Make `p` the active Progress for the library code a command runs."""
    prev = _ACTIVE[0]
    _ACTIVE[0] = p
    try:
        yield p
    finally:
        _ACTIVE[0] = prev


def marker(op: str, **fields) -> str:
    """The line a program outside this process prints (`Relay` reads it)."""
    return f"{MARKER} " + json.dumps({"op": op, **fields}, separators=(",", ":"))


class Relay:
    """Turns MARKER lines of another program's output into stage calls on `progress`:
    {"op": "begin", "label", "total"}, {"op": "update", "done", "total"}, {"op": "advance",
    "k"}, {"op": "note", "text"}, {"op": "end"}. `labels` renames the program's stage keys;
    `on_begin(key, stage)` and `on_end(key, seconds)` let the caller keep an overall
    estimate."""

    def __init__(self, progress, labels: dict | None = None, on_begin=None, on_end=None,
                 on_other=None):
        self.p = progress
        self.labels = labels or {}
        self.stage = None
        self.key = None
        self.on_begin = on_begin
        self.on_end = on_end
        self.on_other = on_other     # on_other(msg): an op this class does not know

    def open(self, key: str, total: int | None = None) -> None:
        """A stage of this side's own (the program's start, say) that the next marker
        closes."""
        self.close()
        self.key = key
        self.stage = self.p.begin(self.labels.get(key, key), total)
        if self.on_begin:
            self.on_begin(key, self.stage)

    def feed(self, line: str) -> bool:
        """One line of the program's output; True when it was a marker."""
        i = line.find(MARKER + " ")
        if i < 0:
            return False
        try:
            msg = json.loads(line[i + len(MARKER) + 1:].strip())
        except ValueError:
            return False
        op = msg.get("op")
        if op == "begin":
            self.open(msg.get("label", ""), msg.get("total"))
        elif op not in ("update", "advance", "note", "end"):
            if self.on_other:
                self.on_other(msg)
        elif self.stage is None:
            if op == "note":
                self.p.note(msg.get("text", ""))
        elif op == "update":
            self.stage.update(msg.get("done", 0), msg.get("total"), msg.get("detail"))
        elif op == "advance":
            self.stage.advance(msg.get("k", 1))
        elif op == "note":
            self.stage.note(msg.get("text", ""))
        elif op == "end":
            self.close()
        return True

    def close(self, ok: bool = True) -> None:
        if self.stage is not None:
            dt = self.stage.finish(ok)
            if self.on_end:
                self.on_end(self.key, dt)
        self.stage = None
        self.key = None
