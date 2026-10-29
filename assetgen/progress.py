"""Progress of assetgen's long commands on stderr (stdlib only), the interface stage 1 uses for
`citygen build` and `citygen unreal` (`citygen.progress.Progress`; when that lands this module
becomes an import of it):

    p = Progress(quiet=None)                 # None: quiet when CYBERGEN_QUIET=1
    with p.stage("shells", total=None) as s:  # a start line; on exit "shells: done in 12.3 s"
        s.set_total(n)                       # a known count: n of N, percent, time left
        s.advance()                          # or s.update(done)
        s.note("tile e3n2 rebuilt")          # an extra plain line (a few per stage at most)
    p.summary()                              # the time of each stage

On a terminal the stage is one line redrawn in place (`\\r` and spaces, no escape codes, so
it works in Windows PowerShell and the Mac terminal):

    shells [#######.............] 1234/5678 22% 3m10s left

Piped or redirected, plain lines: the start, at 0, 25, 50, 75 and 100 percent or every 30 s,
whichever comes first, and the end. Worker processes never print: the parent advances as
their results come back. Nothing here touches an output file.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from contextlib import contextmanager

QUIET_ENV = "CYBERGEN_QUIET"
BAR = 20                    # bar width in characters
REDRAW_S = 0.1              # a terminal line is redrawn at most this often
PIPE_EVERY_S = 30.0         # piped: a line at least this often
MARKS = (0, 25, 50, 75, 100)
MAX_NOTES = 12              # per stage; more are counted and told at its end


def duration(s: float) -> str:
    """12.3 s, 3m10s, 1h02m."""
    if s < 60:
        return f"{s:.1f} s"
    s = int(round(s))
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{s % 3600 // 60:02d}m"


def _left(s: float) -> str:
    s = int(round(s))
    if s < 60:
        return f"{s}s"
    return duration(s)


class Stage:
    def __init__(self, prog: "Progress", label: str, total: int | None):
        self.p = prog
        self.label = label
        self.total = total
        self.done = 0
        self.t0 = time.monotonic()
        self.notes = 0
        self.dropped = 0
        self._drawn = 0.0           # last terminal redraw
        self._said = self.t0        # last piped line
        self._mark = -1             # last piped percent mark

    # -- the interface

    def set_total(self, n: int) -> None:
        with self.p.lock:
            self.total = max(0, int(n))
            self._show(force=True)

    def advance(self, k: int = 1) -> None:
        with self.p.lock:
            self.done += k
            self._show()

    def update(self, done: int) -> None:
        with self.p.lock:
            self.done = int(done)
            self._show()

    def note(self, text: str) -> None:
        if self.p.quiet:
            return
        with self.p.lock:
            if self.notes >= MAX_NOTES:
                self.dropped += 1
                return
            self.notes += 1
            self.p._line(f"  {text}")
            if self.p.tty:
                self._draw()

    # -- drawing

    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def status(self) -> str:
        """`1234/5678 22% 3m10s left` (or the count and the time so far)."""
        el = self.elapsed()
        if self.total:
            d = min(self.done, self.total)
            pct = 100 * d // self.total
            s = f"{d}/{self.total} {pct}%"
            if 0 < d < self.total and el > 1.0:
                s += f" {_left(el * (self.total - d) / d)} left"
            return s
        if self.done:
            return f"{self.done} done, {duration(el)}"
        return duration(el)

    def _bar(self) -> str:
        if not self.total:
            return f"{self.label} ... {self.status()}"
        n = BAR * min(self.done, self.total) // self.total
        return f"{self.label} [{'#' * n}{'.' * (BAR - n)}] {self.status()}"

    def _draw(self) -> None:
        self._drawn = time.monotonic()
        self.p._redraw(self._bar())

    def _show(self, force: bool = False) -> None:
        if self.p.quiet:
            return
        if self.p.tty:
            if force or time.monotonic() - self._drawn >= REDRAW_S or \
                    (self.total and self.done >= self.total):
                self._draw()
            return
        if self.total:
            pct = 100 * min(self.done, self.total) // self.total
            m = max(x for x in MARKS if x <= pct)
            if m > self._mark:
                self._mark = m
                self._say()

    def _say(self) -> None:
        self._said = time.monotonic()
        self.p._line(f"{self.label}: {self.status()}")

    def _tick(self) -> None:
        """The clock: a terminal line's time goes on; piped, a line every PIPE_EVERY_S."""
        if self.p.tty:
            self._draw()
        elif time.monotonic() - self._said >= PIPE_EVERY_S:
            self._say()


class Progress:
    def __init__(self, quiet: bool | None = None, stream=None):
        if quiet is None:
            quiet = os.environ.get(QUIET_ENV, "") == "1"
        self.quiet = bool(quiet)
        self.out = stream if stream is not None else sys.stderr
        try:
            self.tty = bool(self.out.isatty())
        except (AttributeError, ValueError, OSError):
            self.tty = False
        self.lock = threading.RLock()
        self.times: list[tuple[str, float]] = []
        self.t0 = time.monotonic()
        self._cur: Stage | None = None
        self._width = 0             # characters on the terminal line now

    @contextmanager
    def stage(self, label: str, total: int | None = None):
        s = Stage(self, label, total)
        with self.lock:
            self._cur = s
            if not self.quiet:
                if self.tty:
                    s._draw()
                else:
                    self._line(f"{label} ...")
                    if total:
                        s._show(force=True)
        stop = threading.Event()
        clock = None
        if not self.quiet:
            clock = threading.Thread(target=self._clock, args=(s, stop), daemon=True)
            clock.start()
        ok = False
        try:
            yield s
            ok = True
        finally:
            stop.set()
            if clock is not None:
                clock.join()
            el = s.elapsed()
            with self.lock:
                self._cur = None
                self.times.append((label, el))
                if not self.quiet:
                    if ok and s.total and not self.tty and s._mark < 100 and \
                            s.done >= s.total:
                        s._say()
                    more = f" ({s.dropped} more notes)" if s.dropped else ""
                    self._line(f"{label}: {'done in' if ok else 'failed after'} "
                               f"{duration(el)}{more}")

    def summary(self) -> None:
        if self.quiet or not self.times:
            return
        w = max(len(k) for k, _ in self.times)
        with self.lock:
            self._line("time per stage:")
            for k, s in self.times:
                self._line(f"  {k.ljust(w)}  {duration(s):>8}")
            self._line(f"  {'total'.ljust(w)}  {duration(time.monotonic() - self.t0):>8}")

    # -- output

    def _clock(self, s: Stage, stop: threading.Event) -> None:
        while not stop.wait(1.0):
            with self.lock:
                if self._cur is s:
                    s._tick()

    def _write(self, text: str) -> None:
        try:
            self.out.write(text)
            self.out.flush()
        except (OSError, ValueError):
            pass

    def _redraw(self, text: str) -> None:
        cols = shutil.get_terminal_size((100, 20)).columns - 1
        text = text[:max(10, cols)]
        pad = " " * max(0, self._width - len(text))
        self._write(f"\r{text}{pad}")
        self._width = len(text)

    def _line(self, text: str) -> None:
        """A whole line; on a terminal it replaces the bar, which the next draw puts back."""
        if self.tty and self._width:
            self._write("\r" + " " * self._width + "\r")
            self._width = 0
        self._write(text + "\n")
