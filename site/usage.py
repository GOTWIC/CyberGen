#!/usr/bin/env python3
"""Record this machine's Claude Code usage on CyberGen for the gallery's dashboard.

    python site/usage.py [--device mac|windows|NAME] [--logs DIR] [--dry-run]

Reads the session logs Claude Code keeps on this machine (~/.claude/projects, or
$CLAUDE_CONFIG_DIR/projects, or --logs), adds their responses to the device's ledger
and writes site/usage/<device>.json from it: token
totals, sessions, subagents, models and a per-day series, with the time it ran. Each
machine writes only its own file; site/build.py adds the files up for the showcase and
shows each device apart behind a toggle and prices every model's tokens by type
(fast mode responses are kept apart as `<model>:fast`). Python 3.9+ standard library only.

Which sessions are CyberGen's: Claude Code files a session's log under the folder it
ran in, so every worktree session (`<repo>/.claude/worktrees/<name>`) looks like a
project of its own. Every log line records its working folder (`cwd`); a session
counts when one of its lines ran in this repo or under it, or in an earlier location
of the repo: a folder that no longer exists that some log file also holding lines run
in the repo ran in (a session resumed after the repo moved or was renamed carries its
earlier lines with it). Subagent logs sit in their parent session's folder and carry
its working folder, so they count with it.
Each API response is counted once (message id and request id, as ccusage does).

The ledger, site/usage/ledger/<device>/<YYYY-MM>.csv, keeps every response ever
recorded, so a log Claude Code deletes later still counts and a session still running
adds its later responses at the next run. A row holds nothing of the conversation:
a hash of the message and request ids, the UTC time, hashes of the session and
subagent ids, whether the session ran in a worktree, the model and its five token
counts. The device's summary is made from the whole ledger.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import hashlib
import io
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
OUT = SITE / "usage"
LEDGER = OUT / "ledger"
LABELS = {"mac": "Mac", "windows": "Windows PC"}
KINDS = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")
COLUMNS = ("key", "time", "session", "agent", "worktree", "model") + KINDS


def kinds_of(u: dict) -> dict[str, int]:
    """One API response's tokens by type; cache writes split by their lifetime (a
    record without the split counts as 5-minute writes)."""
    write = int(u.get("cache_creation_input_tokens") or 0)
    split = u.get("cache_creation") or {}
    h1 = int(split.get("ephemeral_1h_input_tokens") or 0)
    return {"input": int(u.get("input_tokens") or 0), "output": int(u.get("output_tokens") or 0),
            "cache_write_5m": write - h1, "cache_write_1h": h1,
            "cache_read": int(u.get("cache_read_input_tokens") or 0)}
WORKTREES = "/.claude/worktrees/"


def norm(p: str) -> str:
    """A folder path compared across platforms: forward slashes, no trailing slash,
    lowercase on Windows (whose paths ignore case)."""
    p = p.replace("\\", "/").rstrip("/")
    return p.lower() if os.name == "nt" or (len(p) > 1 and p[1] == ":") else p


def home_of(cwd: str) -> str:
    """The repo folder a working folder belongs to: a worktree's main checkout."""
    i = cwd.find(WORKTREES)
    return cwd[:i] if i >= 0 else cwd


def under(cwd: str, root: str) -> bool:
    return cwd == root or cwd.startswith(root + "/")


def default_device() -> str:
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("win"):
        return "windows"
    return os.uname().nodename.split(".")[0].lower()


def logs_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser()
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / "projects"


def read_sessions(logs: Path) -> dict[str, dict]:
    """Every session's working folders (in order), usage rows and subagents."""
    sessions: dict[str, dict] = defaultdict(lambda: {"cwds": [], "rows": [], "agents": set()})
    files: list[set[str]] = []
    for f in sorted(glob.glob(str(logs / "**" / "*.jsonl"), recursive=True)):
        folders: set[str] = set()
        files.append(folders)
        try:
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"cwd"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                sid = o.get("sessionId")
                if not sid:
                    continue
                s = sessions[sid]
                cwd = o.get("cwd")
                if cwd:
                    c = norm(cwd)
                    folders.add(c)
                    if not s["cwds"] or s["cwds"][-1][1] != c:
                        s["cwds"].append((o.get("timestamp") or "", c))
                if o.get("agentId") and o.get("isSidechain"):
                    s["agents"].add(o["agentId"])
                m = o.get("message")
                u = m.get("usage") if isinstance(m, dict) else None
                if u and o.get("timestamp"):
                    agent = o.get("agentId") if o.get("isSidechain") else None
                    s["rows"].append(((m.get("id"), o.get("requestId")), o["timestamp"],
                                      m.get("model") or "?", u, agent))
    return sessions, files


def cybergen_sessions(sessions: dict[str, dict], files: list[set[str]], repo: str) -> list[str]:
    homes = {repo}
    # Earlier locations of the repo: a log file that holds lines run in the repo and
    # lines run in a folder that is gone now (a session resumed after the repo moved
    # carries its earlier lines with it).
    for folders in files:
        if any(under(c, repo) for c in folders):
            homes.update(h for h in map(home_of, folders)
                         if not under(h, repo) and not Path(h).exists())
    return sorted(sid for sid, s in sessions.items()
                  if any(under(c, h) for _, c in s["cwds"] for h in homes))


def local_day(ts: str) -> str:
    t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return t.astimezone().date().isoformat()


def short(text: str, n: int) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


def utc(ts: str) -> str:
    t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def weight(row: dict) -> int:
    return sum(int(row[k]) for k in KINDS)


def log_rows(sessions: dict[str, dict], ids: list[str]) -> dict[str, dict]:
    """The ledger's rows from the logs: one per API response, ids hashed, no content.
    A response logged more than once (a line per content block, a resumed session's
    copy) keeps its largest record."""
    rows: dict[str, dict] = {}
    for sid in ids:
        s = sessions[sid]
        wt = int(any(WORKTREES in c for _, c in s["cwds"]))
        for (mid, rid), ts, model, u, agent in s["rows"]:
            if model == "<synthetic>":
                continue
            if u.get("speed") == "fast":
                model += ":fast"
            n = kinds_of(u)
            key = short(f"{mid}|{rid}" if (mid or rid) else f"{sid}|{ts}|{sorted(n.items())}", 16)
            row = {"key": key, "time": utc(ts), "session": short(sid, 12),
                   "agent": short(agent, 12) if agent else "", "worktree": str(wt), "model": model,
                   **{k: str(v) for k, v in n.items()}}
            if key not in rows or weight(row) > weight(rows[key]):
                rows[key] = row
    return rows


def read_ledger(device: str) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for p in sorted((LEDGER / device).glob("*.csv")):
        with open(p, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                rows[row["key"]] = row
    return rows


def merge(old: dict[str, dict], new: dict[str, dict]) -> dict[str, dict]:
    """Every row ever recorded: a row the logs no longer hold stays; a response
    still being logged takes its largest record."""
    out = dict(old)
    for key, row in new.items():
        if key not in out or weight(row) > weight(out[key]):
            out[key] = row
    return out


def write_ledger(device: str, rows: dict[str, dict]) -> list[Path]:
    """One CSV a month (UTC), rows by time; a file is written only when it changes."""
    months: dict[str, list[dict]] = defaultdict(list)
    for row in rows.values():
        months[row["time"][:7]].append(row)
    folder = LEDGER / device
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for month, rs in sorted(months.items()):
        rs.sort(key=lambda r: (r["time"], r["key"]))
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rs)
        path = folder / f"{month}.csv"
        text = buf.getvalue()
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8", newline="")
            written.append(path)
    return written


def summarize(rows: dict[str, dict], device: str, label: str) -> dict:
    totals: Counter = Counter()
    models: dict[str, Counter] = defaultdict(Counter)
    days: dict[str, Counter] = defaultdict(Counter)
    day_sessions: dict[str, set] = defaultdict(set)
    sessions: set = set()
    worktree: set = set()
    agents: set = set()
    for row in rows.values():
        n = {k: int(row[k]) for k in KINDS}
        day = local_day(row["time"])
        totals.update(n)
        days[day].update(n)
        models[row["model"]].update(n)
        day_sessions[day].add(row["session"])
        sessions.add(row["session"])
        if row["worktree"] == "1":
            worktree.add(row["session"])
        if row["agent"]:
            agents.add(row["agent"])
    totals["total"] = sum(totals[k] for k in KINDS)
    return {
        "device": device,
        "label": label,
        "updated": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "sessions": len(sessions),
        "worktree_sessions": len(worktree),
        "subagents": len(agents),
        "totals": {k: totals[k] for k in ("total",) + KINDS},
        "models": {m: {k: c[k] for k in KINDS}
                   for m, c in sorted(models.items(), key=lambda kv: -sum(kv[1].values()))},
        "days": {d: {"total": sum(c[k] for k in KINDS), "output": c["output"],
                     "sessions": len(day_sessions[d])} for d, c in sorted(days.items())},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--device", default=default_device(), help="file name under site/usage/ (default: mac or windows)")
    ap.add_argument("--label", help="name shown on the dashboard (default: Mac, Windows PC or the device)")
    ap.add_argument("--logs", help="a projects folder of session logs (default: this machine's)")
    ap.add_argument("--dry-run", action="store_true", help="print the summary, write nothing")
    args = ap.parse_args()
    device = args.device.lower()
    logs = logs_dir(args.logs)
    if not logs.is_dir():
        sys.exit(f"no session logs at {logs}")
    sessions, files = read_sessions(logs)
    ids = cybergen_sessions(sessions, files, norm(str(ROOT)))
    old = read_ledger(device)
    rows = merge(old, log_rows(sessions, ids))
    data = summarize(rows, device, args.label or LABELS.get(device, device))
    t = data["totals"]
    print(f"{data['label']}: {data['sessions']} sessions ({data['worktree_sessions']} in worktrees), "
          f"{data['subagents']} subagents, {t['total']:,} tokens ({t['output']:,} output), "
          f"{len(data['days'])} days")
    print(f"ledger: {len(rows):,} responses ({len(rows) - len(old):,} new)")
    if args.dry_run:
        return
    for p in write_ledger(device, rows):
        print(f"wrote {p.relative_to(ROOT)}")
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{device}.json"
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
