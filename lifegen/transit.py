"""LG6: transit (scope 6.6; checks, scope 8 "Timetables"): a timetable per transit line of the
city model, the trains it needs, each station's stop on its line and the walkways people board
from, the people boarding and leaving each train by the hour.

- **The track** (`Track`): the line's path (M5, M8b, M19: its centerline with altitude), its
  length along the path in 3D; a loop closes on itself.
- **Stops** (`stops_of`): every station of the line (`station_ids`, and every station naming
  the line) stops where the middle of its platform walkway (M5's `platform`, a metro's
  `concourse`) projects onto the track; the platform's side of the track (doors open there),
  the walkway people board from, the height they board at (a sky station's platforms flank
  the tube at its floor, AG4; a metro's concourse is over the track: people go down at the
  point over a door, `board_level`).
- **Runs** (`profile`): the fastest run between stops at the mode's cruise speed, accelerating
  and braking at its rates, at most sqrt(lateral R) in a curve (R the track's radius in plan,
  over the train's length): a forward and a backward pass on a grid of `step_m`; a dwell at
  every stop.
- **The cycle** (`cycle`): a loop runs one way round (its stops in track order, the first at
  the cycle's start); an open line runs the whole track there and back, turning back at its
  ends (`turnback_s`; a terminal station within a train's length of an end is where it turns,
  with its doors open), crossing to the other way's track over the last `cross_m` before it
  turns. The cycle's coordinate c: a loop's along the track from its first stop; an open
  line's out along the track (way 0) and back (way 1). Sampled every `sample_s` s.
- **Trains** (`trains_for`): per hour band ceil(cycle / headway) trains (the spec's headway by
  line name, else the mode's, `presets.TRANSIT_HEADWAY_MIN`), evenly spaced round the cycle,
  so the headway each way is cycle / trains, at most the one asked; fewer where trains that
  close would run within a train's length and `safety_m` of each other (the headway raised,
  said in the record). Ids `train.<line id>.<n>`.
- **Boarding** (`boarding`): a station's riders are the people LG3's spawn points at its
  street accesses send out (their rates by the hour): per arrival (all lines and ways calling
  there) as many leave a train as board it, at least `board_min`, at most the mode's
  `board_max`. The runtime takes the station's street spawns over (the people leaving a train
  walk out by the platform's stairs and elevators).
- **Checks** (`checks`): `timetables` (runs and dwells feasible for the line's length, curves
  and speeds, read back from the sampled cycle; trains never closer than a train's length and
  `safety_m`, nor two in a terminal's crossover at once; a loop closes, an open line turns
  back at both ends), `transit_stops` (every station served, its stop on the track and within
  the line's run), `transit_boarding` (every stop's board walkway in the walkway graph,
  reaching the station's street accesses), `transit_budget` (trains and cars at once).
- `preview_transit.png` (`preview`): the lines, stations and trains at the crowd's hour; each
  line's trains on a time and distance graph over one cycle.
"""

from __future__ import annotations

import bisect
import math
from collections import defaultdict
from pathlib import Path

from . import presets as P


def _r(v: float, k: int = 3) -> float:
    r = round(float(v), k)
    return 0.0 if r == 0.0 else r


# ---------------------------------------------------------------------------
# The track
# ---------------------------------------------------------------------------

class Track:
    """A line's path: its points (3D, repeated ones dropped; a loop's last point dropped where
    it closes on its first), their distances along it (3D), its length."""

    def __init__(self, path, loop: bool):
        pts = [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0) for p in path]
        clean = pts[:1]
        for p in pts[1:]:
            if math.dist(p, clean[-1]) > 1e-3:
                clean.append(p)
        self.closing_gap = math.dist(clean[0], clean[-1]) if len(clean) > 1 else 0.0
        if loop and len(clean) > 3 and self.closing_gap < 1.0:
            clean.pop()
        self.loop = bool(loop)
        self.pts = clean
        self.seq = clean + ([clean[0]] if loop else [])
        cum = [0.0]
        for a, b in zip(self.seq, self.seq[1:]):
            cum.append(cum[-1] + math.dist(a, b))
        self.cum = cum
        self.L = cum[-1]

    def wrap(self, s: float) -> float:
        if self.loop and self.L > 0:
            return s % self.L
        return min(max(s, 0.0), self.L)

    def at(self, s: float) -> tuple[float, float, float]:
        s = self.wrap(s)
        k = max(0, min(len(self.cum) - 2, bisect.bisect_right(self.cum, s) - 1))
        a, b = self.seq[k], self.seq[k + 1]
        seg = self.cum[k + 1] - self.cum[k]
        t = 0.0 if seg <= 0 else (s - self.cum[k]) / seg
        return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))

    def project(self, x: float, y: float) -> tuple[float, float, float, float]:
        """(s, distance in plan, side: + left of the track's way, the track's z there) of the
        point of the track nearest (x, y) in plan."""
        best = None
        for k, (a, b) in enumerate(zip(self.seq, self.seq[1:])):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
            px, py = a[0] + dx * t, a[1] + dy * t
            d = math.hypot(x - px, y - py)
            if best is None or d < best[1] - 1e-9:
                cross = dx * (y - a[1]) - dy * (x - a[0])
                side = 1.0 if cross > 0 else (-1.0 if cross < 0 else 0.0)
                best = (self.cum[k] + (self.cum[k + 1] - self.cum[k]) * t, d, side,
                        a[2] + (b[2] - a[2]) * t)
        return best

    def radii(self) -> list[float]:
        """Per point of `seq`, the radius in plan through its neighbors two points away
        (1e9 on a straight)."""
        n = len(self.seq)
        out = []
        for i in range(n):
            if self.loop:
                a = self.pts[(i - 2) % len(self.pts)]
                b = self.pts[i % len(self.pts)]
                c = self.pts[(i + 2) % len(self.pts)]
            else:
                if i < 2 or i > n - 3:
                    out.append(1e9)
                    continue
                a, b, c = self.seq[i - 2], self.seq[i], self.seq[i + 2]
            ab = math.hypot(b[0] - a[0], b[1] - a[1])
            bc = math.hypot(c[0] - b[0], c[1] - b[1])
            ca = math.hypot(a[0] - c[0], a[1] - c[1])
            area2 = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
            out.append(1e9 if area2 < 1e-9 else ab * bc * ca / (2.0 * area2))
        return out


def train_length(mode: dict) -> float:
    return mode["cars"] * mode["car_m"] + (mode["cars"] - 1) * mode["gap_m"]


def speed_limits(track: Track, mode: dict, step: float) -> list[float]:
    """The speed limit (m/s) on a grid of `step` along the track (track coordinates): the
    mode's cruise, at most sqrt(lateral R) wherever any of the train is (R of every point
    within half a train's length and 5 m)."""
    n = int(math.ceil(track.L / step)) + 1
    lim = [mode["cruise"]] * n
    half = train_length(mode) / 2.0 + 5.0
    for s, R in zip(track.cum, track.radii()):
        v = min(mode["cruise"], math.sqrt(mode["lateral"] * R))
        if v >= mode["cruise"]:
            continue
        lo = int(math.floor((s - half) / step))
        hi = int(math.ceil((s + half) / step))
        for i in range(lo, hi + 1):
            j = i % n if track.loop else i
            if 0 <= j < n:
                lim[j] = min(lim[j], v)
    return lim


# ---------------------------------------------------------------------------
# Stops
# ---------------------------------------------------------------------------

def platform_of(model: dict, station_id: str) -> dict | None:
    """A station's platform walkway (M5's `platform`), else its concourse (a metro's)."""
    best = None
    for w in model.get("walkways", []):
        a = w.get("attrs") or {}
        if a.get("station") != station_id:
            continue
        if a.get("platform"):
            return w
        if a.get("concourse") and best is None:
            best = w
    return best


def _mid(line) -> tuple[float, float, float]:
    """The middle of a polyline by length (3D point)."""
    pts = [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0) for p in line]
    tot = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    if tot <= 0:
        return pts[0]
    run = 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        if run + d >= tot / 2.0:
            t = (tot / 2.0 - run) / d
            return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
        run += d
    return pts[-1]


def _length(line) -> float:
    return sum(math.dist(a[:2], b[:2]) for a, b in zip(line, line[1:]))


def clear_of(mode_name: str, loop: bool) -> float:
    """How far from the line's middle people on its platforms keep (m): past its trains' outer
    sides (a sky tube's tube) and a margin."""
    m = P.TRANSIT_MODES[mode_name]
    if mode_name == "sky_tube":
        return 3.8
    return (m["loop_m"] if loop else m["track_m"]) + m["width_m"] / 2.0 + 0.35


def platform_half(model: dict, station_id: str, track: Track) -> float:
    """The half width of a station's platform deck across its track (M5's `platform` deck
    footprint, the track through it: its vertices' farthest from the track in plan, at most
    15 m); 0 without one (a metro's concourse is over the track)."""
    best = 0.0
    for s in model.get("structures", []):
        a = s.get("attrs") or {}
        if a.get("station") != station_id or a.get("role") != "platform":
            continue
        for p in ((s.get("footprint") or {}).get("exterior") or []):
            best = max(best, track.project(float(p[0]), float(p[1]))[1])
    return min(best, 15.0)


def stops_of(model: dict, line: dict, track: Track, mode: dict) -> tuple[list[dict], list[dict]]:
    """The line's stops (each station's, in track order) and the stations it could not place."""
    stations = {s["id"]: s for s in model.get("stations", [])}
    walk_by = {w["id"]: w for w in model.get("walkways", [])}
    clear = clear_of(line["mode"], track.loop)
    ids = list(line.get("station_ids") or [])
    for s in sorted(stations.values(), key=lambda s: s["id"]):
        if line["id"] in (s.get("line_ids") or []) and s["id"] not in ids:
            ids.append(s["id"])
    out, bad = [], []
    for sid in ids:
        st = stations.get(sid)
        if st is None:
            bad.append({"station_id": sid, "why": "no such station"})
            continue
        w = platform_of(model, sid)
        if w is None:
            # (a station without M5's platform or concourse: its first access walkway)
            acc = [walk_by[a] for a in st.get("access_ids") or [] if a in walk_by]
            w = acc[0] if acc else None
        if w is not None and len(w["line"]) >= 2:
            px, py, pz = _mid(w["line"])
            plen = _length(w["line"])
        else:
            px, py, pz = (float(v) for v in st["position"])
            plen = 0.0
        s, d, side, tz = track.project(px, py)
        rec = {"station_id": sid, "name": st.get("name"), "kind": st.get("kind"),
               "s": _r(s, 2), "off_m": _r(d, 2), "dz_m": _r(pz - tz, 2),
               "side": side if d > 0.5 else 1.0,
               "walkway_id": w["id"] if w is not None else None,
               "platform_m": _r(plen, 1), "point": [_r(px, 2), _r(py, 2), _r(pz, 2)]}
        # (where people stand to board: the platform's level; a sky station in a tower's portal
        # has its platforms at the tube's floor (AG4), a pylon station's flank the tube at its
        # top (M5, AG7), over the pods: people board there at the point over a door, as from a
        # metro's concourse)
        portal = bool(st.get("building_id"))
        rec["board_level"] = bool(mode["board_level"] and (line["mode"] != "sky_tube" or portal))
        rec["board_z"] = _r(pz + (mode["platform_dz"] if portal else 0.0), 2)
        # (the platform deck flanks the track, the walkway down its middle: people on it keep
        # `clear_m` off the middle, out to `half_m`; none on a concourse over the track)
        half = platform_half(model, sid, track)
        rec["half_m"] = _r(half, 2)
        rec["clear_m"] = _r(clear, 2) if half > clear + 0.6 else 0.0
        tol = P.TRANSIT
        if d > tol["stop_tol_m"] or abs(pz - tz) > tol["stop_dz_m"]:
            rec["why"] = f"its platform {d:.1f} m off the track in plan, {pz - tz:+.1f} m " \
                         f"in height"
            bad.append(rec)
            continue
        out.append(rec)
    out.sort(key=lambda r: (r["s"], r["station_id"]))
    return out, bad


# ---------------------------------------------------------------------------
# Runs and the cycle
# ---------------------------------------------------------------------------

def profile(lim: list[float], stops: list[int], accel: float, brake: float,
            step: float) -> list[float]:
    """The fastest speeds on a grid (`lim` the limit at each point, 0 at `stops`), from rest
    at its first point to rest at its last: forward at `accel`, backward at `brake`."""
    v = list(lim)
    for i in stops:
        v[i] = 0.0
    v[0] = v[-1] = 0.0
    for i in range(len(v) - 1):
        v[i + 1] = min(v[i + 1], math.sqrt(v[i] * v[i] + 2.0 * accel * step))
    for i in range(len(v) - 1, 0, -1):
        v[i - 1] = min(v[i - 1], math.sqrt(v[i] * v[i] + 2.0 * brake * step))
    return v


def _knots(v: list[float], step: float, accel: float) -> list[float]:
    """The time (s) at each grid point of a speed profile from its first."""
    t = [0.0]
    for i in range(len(v) - 1):
        sv = v[i] + v[i + 1]
        dt = 2.0 * step / sv if sv > 1e-6 else 2.0 * math.sqrt(step / accel)
        t.append(t[-1] + dt)
    return t


class Way:
    """One way of a cycle: its travel coordinate x on a grid from 0 to D, the track's s at x,
    its stops (grid index, the stop's index among the line's, dwell)."""

    def __init__(self, n: int, step: float):
        self.n = n
        self.step = step


def cycle(track: Track, mode: dict, stops: list[dict]) -> dict:
    """The line's cycle (see the module docstring): knots (u, c), its length, the turn points
    (track s; a loop's start), the stop events (arrive, depart, stop index, way), each way's
    speeds on its grid (for the checks), the run times between stops."""
    T = P.TRANSIT
    step = T["step_m"]
    lim_track = speed_limits(track, mode, step)
    tl = train_length(mode)

    def lim_at(s: float) -> float:
        i = int(round(track.wrap(s) / step))
        if track.loop:
            i %= len(lim_track)
        return lim_track[min(max(i, 0), len(lim_track) - 1)]

    events, knots, ways = [], [], []
    if track.loop:
        s0 = stops[0]["s"] if stops else 0.0
        D = track.L
        n = max(2, int(math.ceil(D / step)))
        h = D / n
        xs = [(st["s"] - s0) % track.L for st in stops]
        idx = sorted({min(n, max(0, int(round(x / h)))) for x in xs} | {0, n})
        lim = [lim_at(s0 + i * h) for i in range(n + 1)]
        v = profile(lim, idx, mode["accel"], mode["brake"], h)
        t = _knots(v, h, mode["accel"])
        ways.append({"way": 0, "h": h, "v": v, "lim": lim, "D": D})
        u = 0.0
        stop_at = {}
        for k, x in enumerate(xs):
            stop_at.setdefault(min(n, max(0, int(round(x / h)))) % n, k)
        for i in range(n + 1):
            knots.append((u, i * h, v[i]))
            if i in stop_at and i < n:
                d = mode["dwell_s"]
                events.append((u, u + d, stop_at[i], 0))
                u += d
                knots.append((u, i * h, v[i]))
            if i < n:
                u += t[i + 1] - t[i]
        R = u
        turn = [_r(s0, 3), _r(s0 + D, 3)]
    else:
        L = track.L
        # (the ends: a terminal station within a train's length of an end is where it turns;
        # else half a train and 2 m in from the track's end)
        a = tl / 2.0 + 2.0
        b = L - tl / 2.0 - 2.0
        first = stops[0] if stops else None
        last = stops[-1] if stops else None
        at_a = first is not None and first["s"] <= tl + 20.0
        at_b = last is not None and last["s"] >= L - tl - 20.0
        if at_a:
            a = max(a, first["s"])
        if at_b:
            b = min(b, last["s"])
        if b - a < 2.0 * step:
            b = a + 2.0 * step
        D = b - a
        n = max(2, int(math.ceil(D / step)))
        h = D / n
        turn = [_r(a, 3), _r(b, 3)]
        u = 0.0
        for way in (0, 1):
            s_of = (lambda x: a + x) if way == 0 else (lambda x: b - x)
            stop_at = {}
            for k, st in enumerate(stops):
                x = st["s"] - a if way == 0 else b - st["s"]
                if -1e-6 <= x <= D + 1e-6:
                    stop_at[min(n, max(0, int(round(x / h))))] = k
            lim = [lim_at(s_of(i * h)) for i in range(n + 1)]
            v = profile(lim, sorted(stop_at), mode["accel"], mode["brake"], h)
            t = _knots(v, h, mode["accel"])
            ways.append({"way": way, "h": h, "v": v, "lim": lim, "D": D})
            c0 = way * D
            for i in range(n + 1):
                knots.append((u, c0 + i * h, v[i]))
                if i == 0:
                    # (the turn: a layover, its doors open where a terminal station is there)
                    d = max(T["turnback_s"], mode["dwell_s"])
                    k = stop_at.get(0)
                    events.append((u, u + d, k if k is not None else -1, way))
                    u += d
                    knots.append((u, c0, 0.0))
                elif i in stop_at and i < n:
                    d = mode["dwell_s"]
                    events.append((u, u + d, stop_at[i], way))
                    u += d
                    knots.append((u, c0 + i * h, v[i]))
                if i < n:
                    u += t[i + 1] - t[i]
        R = u
    # (the knots made monotonic in u, duplicates dropped)
    out = []
    for kn in knots:
        if out and abs(kn[0] - out[-1][0]) < 1e-9:
            out[-1] = kn
        else:
            out.append(kn)
    return {"R": R, "D": D, "turn": turn, "knots": out, "events": events, "ways": ways}


def sample(knots: list[tuple[float, float, float]], R: float, dt: float) -> list[float]:
    """c at every `dt` from 0 to R (`dt` dividing R: the last sample at R): between two knots
    (u, c, v) at the constant acceleration that takes the one's speed to the other's (each
    grid step of a profile is one: v squared is linear along it)."""
    us = [k[0] for k in knots]
    out = []
    n = int(round(R / dt)) + 1
    for j in range(n):
        u = j * dt
        k = max(0, min(len(us) - 2, bisect.bisect_right(us, u) - 1))
        (u0, c0, v0), (u1, c1, v1) = knots[k], knots[k + 1]
        tau = min(max(u - u0, 0.0), max(u1 - u0, 0.0))
        if u1 <= u0 or c1 == c0:
            out.append(c1 if u >= u1 else c0)
        elif v0 + v1 > 1e-6:
            a = (v1 - v0) / (u1 - u0)
            out.append(min(c1, c0 + v0 * tau + 0.5 * a * tau * tau))
        else:
            out.append(c0 + (c1 - c0) * tau / (u1 - u0))
    return out


def at_cycle(samples: list[float], dt: float, u: float) -> float:
    j = u / dt
    k = int(math.floor(j))
    if k >= len(samples) - 1:
        return samples[-1]
    t = j - k
    return samples[k] + (samples[k + 1] - samples[k]) * t


def position(line: dict, c: float) -> tuple[int, float]:
    """(way, track s) of cycle coordinate c."""
    a, b = line["turn"]
    if line["loop"]:
        return 0, c + a
    D = b - a
    if c <= D:
        return 0, a + c
    return 1, b - (c - D)


# ---------------------------------------------------------------------------
# Trains and boarding
# ---------------------------------------------------------------------------

def headways(filled: dict, line: dict) -> list[float]:
    """The headway asked each way per band (min): the spec's by line name, else the mode's."""
    hw = (filled.get("transit") or {}).get(line["name"])
    return [float(v) for v in (hw or P.TRANSIT_HEADWAY_MIN[line["mode"]])]


def min_gap(samples: list[float], dt: float, R: float, n: int, rec: dict) -> tuple[float, float]:
    """With n trains evenly round the cycle: the least distance along the track between a
    train and the one behind it on the same way (m), and the least time apart two trains are
    in a terminal's crossover (s; inf for a loop)."""
    if n < 2:
        return math.inf, math.inf
    H = R / n
    loop = rec["loop"]
    D = rec["D"]
    zone = P.TRANSIT["cross_m"] + rec["train_m"]
    least, cross = math.inf, math.inf
    m = len(samples)
    for j in range(0, m, 2):
        u = j * dt
        cl = at_cycle(samples, dt, u % R)
        cf = at_cycle(samples, dt, (u - H) % R)
        if loop:
            least = min(least, (cl - cf) % D)
            continue
        wl, wf = (0 if cl <= D else 1), (0 if cf <= D else 1)
        if wl == wf and cl >= cf:
            least = min(least, cl - cf)
        # (both at the same end at once, where the ways cross and the train turns: two trains
        # in a terminal's crossover or at its platform)
        for end_c in ((D,), (0.0, 2.0 * D)):
            dl = min(abs(cl - e) for e in end_c)
            df = min(abs(cf - e) for e in end_c)
            if dl < zone and df < zone:
                cross = 0.0
    return least, cross


def trains_for(rec: dict, samples: list[float], dt: float, want_min: list[float]) -> tuple[list[int], list[str]]:
    """Per band the trains round the cycle and what was raised."""
    R = rec["R"]
    need = rec["train_m"] + P.TRANSIT["safety_m"]
    out, notes = [], []
    for b, hw in enumerate(want_min):
        n = max(1, int(math.ceil(R / max(1.0, 60.0 * hw))))
        while n > 1:
            g, cr = min_gap(samples, dt, R, n, rec)
            if g >= need and cr > 0:
                break
            n -= 1
        if R / n > 60.0 * hw + 1e-6:
            notes.append(f"{P.BANDS[b]}: {hw:g} min asked, every {R / n / 60.0:.1f} min "
                         f"({n} trains: more would bring two within {need:.0f} m or into "
                         f"a terminal at once)")
        out.append(n)
    return out, notes


def station_riders(spawns: list[dict]) -> dict[str, list[float]]:
    """Per station its street accesses' people out a hour, every hour (LG3's rates)."""
    out: dict[str, list[float]] = {}
    for s in spawns:
        if s["kind"] != "station":
            continue
        r = out.setdefault(s["owner_id"], [0.0] * P.HOURS)
        for h, v in enumerate(s["rates"]):
            r[h] += float(v)
    return out


def boarding(lines: list[dict], riders: dict[str, list[float]]) -> None:
    """Per stop of every line, the people leaving and boarding a train calling there per band
    (`board`, `alight`): the station's riders a band over the trains calling there a band."""
    calls = defaultdict(lambda: [0.0] * 5)
    for ln in lines:
        per = defaultdict(int)
        for ev in ln["events"]:
            if ev[2] >= 0:
                per[ln["stops"][ev[2]]["station_id"]] += 1
        for sid, k in per.items():
            for b in range(5):
                calls[sid][b] += k * ln["trains"][b] * 3600.0 / ln["cycle_s"]
    for ln in lines:
        mode = P.TRANSIT_MODES[ln["mode"]]
        for st in ln["stops"]:
            r = riders.get(st["station_id"]) or [0.0] * P.HOURS
            per = []
            for b, (_, a, z) in enumerate(P.HOUR_BANDS):
                ph = sum(r[a:z]) / (z - a)
                c = calls[st["station_id"]][b]
                v = ph / c if c > 0 else 0.0
                per.append(_r(min(mode["board_max"], max(P.TRANSIT["board_min"][b], v)), 2))
            st["riders_h"] = [_r(sum(r[a:z]) / (z - a), 2) for _, a, z in P.HOUR_BANDS]
            st["calls_h"] = [_r(v, 2) for v in calls[st["station_id"]]]
            st["board"] = per
            st["alight"] = list(per)


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------

def transit_plan(model: dict, filled: dict, spawns: list[dict]) -> tuple[list[dict], dict]:
    """Every line's timetable (the records `timetables.json` holds) and what was left out."""
    T = P.TRANSIT
    lines, left = [], {"stations": [], "lines": []}
    for line in sorted(model.get("transit_lines", []), key=lambda t: t["id"]):
        mode = P.TRANSIT_MODES.get(line["mode"])
        if mode is None or len(line.get("path") or []) < 2:
            left["lines"].append({"line_id": line["id"], "why": "no mode or no path"})
            continue
        track = Track(line["path"], bool(line.get("loop")))
        if track.L < 4.0 * T["step_m"]:
            left["lines"].append({"line_id": line["id"], "why": "too short"})
            continue
        stops, bad = stops_of(model, line, track, mode)
        for b in bad:
            left["stations"].append({"line_id": line["id"], **b})
        cyc = cycle(track, mode, stops)
        # (the samples' step divides the cycle, so its last sample is its end)
        dt = cyc["R"] / max(1, int(math.ceil(cyc["R"] / T["sample_s"])))
        samples = sample(cyc["knots"], cyc["R"], dt)
        rec = {"id": line["id"], "name": line["name"], "mode": line["mode"],
               "color": line.get("color") or "#ffffff", "loop": track.loop,
               "length_m": _r(track.L, 2), "closing_gap_m": _r(track.closing_gap, 3),
               "turn": cyc["turn"], "D": _r(cyc["D"], 3), "cycle_s": _r(cyc["R"], 3),
               "train_m": _r(train_length(mode), 2), "cars": mode["cars"],
               # (the train as drawn and run: its track off the line's middle, each way's on
               # its own right; a loop's one way; doors on its right only where it runs off
               # the middle (the platforms flank the line), else both sides)
               "car": {"car_m": mode["car_m"], "gap_m": mode["gap_m"],
                       "width_m": mode["width_m"], "height_m": mode["height_m"],
                       "floor_m": mode["floor_m"], "base_m": mode["base_m"],
                       "track_m": mode["loop_m"] if track.loop else mode["track_m"],
                       "doors": mode["doors"], "door_m": mode["door_m"],
                       "board_level": mode["board_level"],
                       "sides": 1 if (mode["loop_m"] if track.loop else mode["track_m"]) > 0
                       else 2},
               "points": [[_r(v, 2) for v in p] for p in track.pts],
               "stops": stops}
        want = headways(filled, line)
        rec["R"] = cyc["R"]
        trains, notes = trains_for(rec, samples, dt, want)
        del rec["R"]
        rec.update({
            "headway_asked_min": [_r(v, 2) for v in want],
            "trains": trains,
            "headway_min": [_r(cyc["R"] / n / 60.0, 3) for n in trains],
            "notes": notes,
            "train_ids": [f"train.{line['id']}.{k}" for k in range(max(trains))],
            "sample_s": _r(dt, 6),
            "samples": [_r(v, 2) for v in samples],
            "events": [[_r(e[0], 3), _r(e[1], 3), e[2], e[3]] for e in cyc["events"]],
            "runs": run_times(cyc, mode),
            "_ways": cyc["ways"]})
        lines.append(rec)
    boarding(lines, station_riders(spawns))
    served = {st["station_id"] for ln in lines for st in ln["stops"]}
    for s in model.get("stations", []):
        if s["id"] not in served and not any(x["station_id"] == s["id"] for x in left["stations"]):
            left["stations"].append({"station_id": s["id"], "why": "on no line's track"})
    return lines, left


def run_times(cyc: dict, mode: dict) -> dict:
    """The cycle's running and dwelling times, its top speed and the least it could run in
    (its distance at cruise)."""
    dwell = sum(e[1] - e[0] for e in cyc["events"])
    vmax = max((max(w["v"]) for w in cyc["ways"]), default=0.0)
    dist = sum(w["D"] for w in cyc["ways"])
    return {"run_s": _r(cyc["R"] - dwell, 2), "dwell_s": _r(dwell, 2),
            "top_mps": _r(vmax, 2), "at_cruise_s": _r(dist / mode["cruise"], 2)}


def plan_record(lines: list[dict], left: dict, hour: int) -> dict:
    """The plan's `transit` (without its hash): per line its summary; totals."""
    b = P.band_of(hour)
    out = []
    for ln in lines:
        out.append({"id": ln["id"], "name": ln["name"], "mode": ln["mode"], "loop": ln["loop"],
                    "length_m": ln["length_m"], "cycle_s": ln["cycle_s"],
                    "trains": ln["trains"], "headway_min": ln["headway_min"],
                    "stops": [st["station_id"] for st in ln["stops"]],
                    "train_ids": ln["train_ids"], "notes": ln["notes"]})
    busiest = [sum(ln["trains"][k] for ln in lines) for k in range(5)]
    cars = [sum(ln["trains"][k] * ln["cars"] for ln in lines) for k in range(5)]
    return {"hour": hour, "modes": {k: v for k, v in sorted(P.TRANSIT_MODES.items())},
            "settings": dict(P.TRANSIT), "lines": out,
            "totals": {"lines": len(lines), "stops": sum(len(ln["stops"]) for ln in lines),
                       "trains_by_band": busiest, "cars_by_band": cars,
                       "trains_at_hour": busiest[b], "cars_at_hour": cars[b],
                       "boarding_at_hour": _r(sum(st["board"][b] * st["calls_h"][b]
                                                  for ln in lines for st in ln["stops"]), 1),
                       "left_out": left}}


def timetables(lines: list[dict]) -> list[dict]:
    """The records `timetables.json` holds (the ways' grids left out)."""
    return [{k: v for k, v in ln.items() if not k.startswith("_")} for ln in lines]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def checks(model: dict, lines: list[dict], left: dict, comp: dict[str, int],
           spawns: list[dict]) -> dict:
    T = P.TRANSIT
    out = {}
    bad, said = [], []
    for ln in lines:
        mode = P.TRANSIT_MODES[ln["mode"]]
        dt = ln["sample_s"]
        s = ln["samples"]
        # (the speeds and accelerations read back from the sampled cycle; within the mode's
        # and each way's limits on its grid)
        vs = [(s[j + 1] - s[j]) / dt for j in range(len(s) - 1)]
        if min(vs, default=0.0) < -1e-6:
            bad.append(f"{ln['id']}: runs backward in its cycle")
        if max(vs, default=0.0) > mode["cruise"] * 1.02 + 0.05:
            bad.append(f"{ln['id']}: {max(vs):.1f} m/s over its {mode['cruise']} m/s")
        acc = max((abs(vs[j + 1] - vs[j]) / dt for j in range(len(vs) - 1)), default=0.0)
        if acc > max(mode["accel"], mode["brake"]) * 1.35 + 0.05:
            bad.append(f"{ln['id']}: {acc:.2f} m/s2 past its rates")
        for w in ln["_ways"]:
            over = max((v - lim for v, lim in zip(w["v"], w["lim"])), default=0.0)
            if over > 1e-6:
                bad.append(f"{ln['id']}: way {w['way']} {over:.2f} m/s over a curve's limit")
        for e in ln["events"]:
            if e[2] >= 0 and e[1] - e[0] < mode["dwell_s"] - 1e-6:
                bad.append(f"{ln['id']}: a dwell of {e[1] - e[0]:.1f} s under {mode['dwell_s']}")
        r = ln["runs"]
        if r["run_s"] < r["at_cruise_s"] - 1e-6:
            bad.append(f"{ln['id']}: runs its {r['run_s']} s under the {r['at_cruise_s']} s "
                       f"its distance takes at cruise")
        # (a loop closes; an open line turns back at both ends)
        if ln["loop"]:
            if ln["closing_gap_m"] > 1.0:
                bad.append(f"{ln['id']}: a loop whose track does not close "
                           f"({ln['closing_gap_m']} m)")
            if abs(s[0]) > 0.01 or abs(s[-1] - ln["D"]) > max(0.5, mode["cruise"] * dt):
                bad.append(f"{ln['id']}: its cycle does not come round")
        else:
            turns = {e[3] for e in ln["events"] if abs(e[1] - e[0]) >=
                     max(T["turnback_s"], mode["dwell_s"]) - 1e-6}
            if turns != {0, 1} or abs(s[0]) > 0.01 or abs(s[-1] - 2 * ln["D"]) > \
                    max(0.5, mode["cruise"] * dt):
                bad.append(f"{ln['id']}: does not turn back at both ends")
        # (trains never closer than a train's length and the safety distance, nor two in a
        # terminal's crossover at once)
        rec = {"loop": ln["loop"], "D": ln["D"], "train_m": ln["train_m"]}
        for b, n in enumerate(ln["trains"]):
            g, cr = min_gap(s, dt, ln["cycle_s"], n, rec)
            if g < ln["train_m"] + T["safety_m"] - 1e-6 or cr <= 0:
                bad.append(f"{ln['id']} {P.BANDS[b]}: {n} trains come within {g:.0f} m")
        said += [f"{ln['id']} {x}" for x in ln["notes"]]
    out["timetables"] = {"ok": not bad, "detail": (
        f"{len(lines)} lines: runs within their speeds, curves, acceleration and braking, "
        f"dwells kept, loops closing and open lines turning back at both ends, trains a "
        f"train's length and {T['safety_m']:.0f} m apart at least" +
        (f"; headways raised: {'; '.join(said[:4])}" if said else "")
        if not bad else "; ".join(bad[:6]))}
    # transit_stops: every station served, its stop on its line's track and within the run
    bad = [f"{x.get('line_id', '')} {x['station_id']}: {x.get('why')}"
           for x in left["stations"]]
    for ln in lines:
        a, b = ln["turn"]
        for st in ln["stops"]:
            if not ln["loop"] and not (a - 1e-6 <= st["s"] <= b + 1e-6) and \
                    min(abs(st["s"] - a), abs(st["s"] - b)) > ln["train_m"]:
                bad.append(f"{ln['id']} {st['station_id']}: its stop at {st['s']} m is past the "
                           f"turn points {a}, {b}")
        called = {ln["stops"][e[2]]["station_id"] for e in ln["events"] if e[2] >= 0}
        for st in ln["stops"]:
            if st["station_id"] not in called:
                bad.append(f"{ln['id']} {st['station_id']}: no train calls there")
    short = [f"{st['station_id']} ({st['platform_m']:.0f} m for {ln['train_m']:.0f} m)"
             for ln in lines for st in ln["stops"]
             if st["platform_m"] and st["platform_m"] < ln["train_m"] - 0.5]
    nst = sum(len(ln["stops"]) for ln in lines)
    out["transit_stops"] = {"ok": not bad, "detail": (
        f"{len(model.get('stations', []))} stations, {nst} stops on their lines' tracks "
        f"(within {T['stop_tol_m']:.0f} m in plan and {T['stop_dz_m']:.0f} m in height)" +
        (f"; trains longer than their platforms: {', '.join(short[:5])}" if short else "")
        if not bad else "; ".join(bad[:6]))}
    # transit_boarding: every stop's board walkway in the graph, reaching its street accesses
    walk_ids = {w["id"] for w in model.get("walkways", [])}
    acc = defaultdict(set)
    for sp in spawns:
        if sp["kind"] == "station":
            acc[sp["owner_id"]].add(comp.get(sp["walkway_id"]))
    bad = []
    for ln in lines:
        for st in ln["stops"]:
            w = st["walkway_id"]
            if w is None or w not in walk_ids:
                bad.append(f"{ln['id']} {st['station_id']}: no platform walkway")
            elif acc.get(st["station_id"]) and comp.get(w) not in acc[st["station_id"]]:
                bad.append(f"{ln['id']} {st['station_id']}: its platform reaches none of its "
                           f"street accesses")
            if not all(math.isfinite(v) and v >= 0 for v in st["board"] + st["alight"]):
                bad.append(f"{ln['id']} {st['station_id']}: boarding not a number")
    out["transit_boarding"] = {"ok": not bad, "detail": (
        f"{nst} stops: each boards from its platform walkway, which reaches its station's "
        f"street accesses; people a train {min((min(st['board']) for ln in lines for st in ln['stops']), default=0):g} "
        f"to {max((max(st['board']) for ln in lines for st in ln['stops']), default=0):g}"
        if not bad else "; ".join(bad[:6]))}
    trains = [sum(ln["trains"][k] for ln in lines) for k in range(5)]
    cars = [sum(ln["trains"][k] * ln["cars"] for ln in lines) for k in range(5)]
    ok = max(trains, default=0) <= T["budget_trains"] and max(cars, default=0) <= T["budget_cars"]
    out["transit_budget"] = {"ok": ok, "detail": (
        f"at most {max(trains, default=0)} trains and {max(cars, default=0)} cars at once "
        f"(budget {T['budget_trains']} and {T['budget_cars']})")}
    return out


# ---------------------------------------------------------------------------
# The preview
# ---------------------------------------------------------------------------

def preview(model: dict, lines: list[dict], hour: int, path: Path) -> str | None:
    """The lines (their colors), stations and trains at a moment of the crowd's hour; each
    line's trains over one cycle on a time and distance graph."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    b = P.band_of(hour)
    n = max(1, len(lines))
    fig = plt.figure(figsize=(18, 9), dpi=100)
    fig.patch.set_facecolor("#0c111a")
    ax = fig.add_axes([0.02, 0.05, 0.46, 0.88])
    ax.set_facecolor("#0c111a")
    for d in model.get("districts", []):
        ring = (d.get("polygon") or {}).get("exterior") or []
        if ring:
            xs, ys = zip(*(ring + ring[:1]))
            ax.plot(xs, ys, color="#2c3443", lw=0.8)
    for ln in lines:
        pts = ln["points"] + ([ln["points"][0]] if ln["loop"] else [])
        xs, ys = zip(*[(p[0], p[1]) for p in pts])
        ax.plot(xs, ys, color=ln["color"], lw=2.0, alpha=0.9, label=f"{ln['name']} "
                f"({ln['mode']}, {ln['trains'][b]} trains at {hour}:00)")
        tr = Track(ln["points"], ln["loop"])
        for st in ln["stops"]:
            ax.plot(*st["point"][:2], "o", ms=7, mfc="#0c111a", mec=ln["color"], mew=2)
        # (the trains a moment into the hour)
        nt = ln["trains"][b]
        R = ln["cycle_s"]
        for k in range(nt):
            c = at_cycle(ln["samples"], ln["sample_s"], (k * R / nt + 37.0) % R)
            way, s = position(ln, c)
            x, y, _ = tr.at(s)
            ax.plot(x, y, "s", ms=8, color="#ffffff", mec=ln["color"], mew=2)
    bb = model.get("bounds") or [-1, -1, 1, 1]
    ax.set_xlim(bb[0], bb[2])
    ax.set_ylim(bb[1], bb[3])
    ax.set_aspect("equal")
    ax.tick_params(colors="#9aa6bd")
    for sp in ax.spines.values():
        sp.set_color("#3a4253")
    ax.set_title(f"transit lines, stations and trains at {hour}:00", color="#e6ecf7")
    ax.legend(facecolor="#141a26", labelcolor="#e6ecf7", edgecolor="#3a4253", fontsize=8,
              loc="lower left")
    for i, ln in enumerate(lines):
        h = 0.88 / n
        bx = fig.add_axes([0.54, 0.05 + (n - 1 - i) * h + 0.02, 0.44, h - 0.05])
        bx.set_facecolor("#0c111a")
        bx.tick_params(colors="#9aa6bd", labelsize=7)
        for sp in bx.spines.values():
            sp.set_color("#3a4253")
        R = ln["cycle_s"]
        nt = ln["trains"][b]
        dt = ln["sample_s"]
        us = [j * dt for j in range(len(ln["samples"]))]
        for k in range(nt):
            off = k * R / nt
            pts = sorted(((u + off) % R, position(ln, c)[1]) for u, c in zip(us, ln["samples"]))
            # (broken where it wraps)
            xs, ys = [], []
            for (u, s) in pts:
                if xs and u < xs[-1]:
                    bx.plot(xs, ys, color=ln["color"], lw=1.0)
                    xs, ys = [], []
                xs.append(u)
                ys.append(s)
            bx.plot(xs, ys, color=ln["color"], lw=1.0)
        for st in ln["stops"]:
            bx.axhline(st["s"], color="#3a4253", lw=0.6)
        bx.set_xlim(0, R)
        bx.set_title(f"{ln['name']}: {nt} trains, every {ln['headway_min'][b]:.1f} min "
                     f"each way, a {R / 60:.1f} min cycle", color="#e6ecf7", fontsize=9)
        bx.set_ylabel("m along", color="#9aa6bd", fontsize=7)
    tmp = path.with_suffix(".tmp.png")
    fig.savefig(tmp, facecolor=fig.get_facecolor())
    plt.close(fig)
    data = tmp.read_bytes()
    tmp.unlink()
    if path.is_file() and path.read_bytes() == data:
        return None
    path.write_bytes(data)
    return str(path)
