"""Share AG18's game packs between machines through a GitHub release.

Packs are not in git (`GAME.md`); building all of them takes hours. This tool zips each
car's pack, uploads the zips as assets of a release of this repo, and records what it
uploaded in `vehicles/packs.json` (committed): the release's tag, each zip's sha256 and
size, the sha256 of every file in it, and the sources the pack was built from. Another
machine fetches the zips, checks every hash and unpacks them into its packs' cache.

    python vehicles/packs.py status                  # local packs against packs.json
    python vehicles/packs.py fetch [CAR ...]         # download what is missing or differs
    python vehicles/packs.py fetch --from DIR        # from zips already downloaded
    python vehicles/packs.py publish [CAR ...]       # zip, upload, rewrite packs.json

The packs' folder is `--dir`, else `$CITYGEN_VEHICLES`, else
`~/.cache/cybergen/vehicles/game` (where `game.py` writes and the exporter and the parked
cars read). A zip holds the pack's top-level files only (`pack.json`, the LOD and collision
glTFs, the textures, `game_report.json`): not `work/`, `proof/` or `game.jpg`, which is in
`docs/progress/AG18/<car>/`. `fetch` downloads over plain HTTPS (the repo is public; no
token, no `gh`); `publish` needs the GitHub CLI signed in with write access. Standard
library only, any Python 3.10 or later, on macOS, Linux or Windows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "vehicles" / "packs.json"
REPO = "GOTWIC/CyberGen"
FORMAT = "cybergen.vehicle_packs"
VERSION = 1
SKIP = {"game.jpg"}
EXCLUDED = ("vex_",)  # to be redesigned: never shared
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
SOURCES = {"script_sha256": None, "carkit_sha256": "vehicles/carkit.py",
           "game_sha256": "vehicles/game.py"}


def packs_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser()
    env = os.environ.get("CITYGEN_VEHICLES")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".cache" / "cybergen" / "vehicles" / "game"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def shipped(folder: Path) -> list[Path]:
    """The files of a pack that go in its zip, sorted by name."""
    return sorted((p for p in folder.iterdir() if p.is_file() and p.name not in SKIP
                   and not p.name.startswith(".")), key=lambda p: p.name)


def local_cars(base: Path) -> list[str]:
    if not base.is_dir():
        return []
    return sorted(d.name for d in base.iterdir()
                  if (d / "pack.json").is_file() and not d.name.startswith(EXCLUDED))


def load_manifest() -> dict:
    if MANIFEST.is_file():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"format": FORMAT, "version": VERSION, "repo": REPO, "tag": None, "cars": {}}


def file_hashes(folder: Path) -> dict[str, str]:
    return {p.name: sha256(p) for p in shipped(folder)}


def source_of(folder: Path) -> dict:
    pk = json.loads((folder / "pack.json").read_text(encoding="utf-8"))
    src = pk.get("source") or {}
    return {k: src.get(k) for k in ("script", *SOURCES)}


def stale(source: dict) -> list[str]:
    """Which of the pack's sources differ from this checkout (the car's script, the kit,
    the tool): such a pack still works but a rebuild would differ."""
    out = []
    for key, rel in SOURCES.items():
        rel = rel or source.get("script")
        if not rel or not source.get(key):
            continue
        p = ROOT / rel
        if p.is_file() and sha256(p) != source[key]:
            out.append(Path(rel).name)
    return out


def human(n: int) -> str:
    return f"{n / 1e6:.1f} MB"


# ---------------------------------------------------------------- status

def cmd_status(a) -> int:
    base = packs_dir(a.dir)
    man = load_manifest()
    cars = sorted(set(man["cars"]) | set(local_cars(base)))
    print(f"packs: {base}")
    print(f"release: {man.get('tag') or 'none yet'} ({man.get('repo', REPO)})")
    bad = 0
    for car in cars:
        entry = man["cars"].get(car)
        folder = base / car
        if not (folder / "pack.json").is_file():
            state = "missing (fetch gets it)"
            bad += 1
        elif not entry:
            state = "local only (not in the release)"
        elif file_hashes(folder) == entry["files"]:
            state = "as released"
        else:
            state = "differs from the release"
            bad += 1
        notes = ""
        src = entry["source"] if entry else (source_of(folder) if folder.is_dir() else None)
        if src:
            changed = stale(src)
            if changed:
                notes = f"; built before the current {', '.join(changed)}"
        print(f"  {car:18s} {state}{notes}")
    return 1 if bad and a.strict else 0


# ---------------------------------------------------------------- publish

def zip_pack(folder: Path, out: Path) -> None:
    """A zip of the pack's shipped files under `<car>/`, the same bytes for the same files."""
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in shipped(folder):
            info = zipfile.ZipInfo(f"{folder.name}/{p.name}", date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(p, "rb") as f:
                z.writestr(info, f.read(), compresslevel=6)


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], check=check, text=True, capture_output=True)


def cmd_publish(a) -> int:
    base = packs_dir(a.dir)
    cars = a.cars or local_cars(base)
    cars = [c for c in cars if not c.startswith(EXCLUDED)]
    missing = [c for c in cars if not (base / c / "pack.json").is_file()]
    if missing:
        print(f"no pack for: {', '.join(missing)}", file=sys.stderr)
        return 1
    man = load_manifest()
    tag = a.tag or time.strftime("vehicle-packs-%Y-%m-%d")
    if man.get("tag") and man["tag"] != tag and a.cars:
        print(f"publishing some cars under a new tag {tag}: the others in packs.json stay on "
              f"{man['tag']}, which fetch cannot reach from one tag; publish them all",
              file=sys.stderr)
        return 1
    work = Path(tempfile.mkdtemp(prefix="cg_packs_"))
    try:
        entries = {}
        for car in cars:
            folder = base / car
            z = work / f"{car}.zip"
            zip_pack(folder, z)
            entries[car] = {"asset": z.name, "sha256": sha256(z), "bytes": z.stat().st_size,
                            "files": file_hashes(folder), "source": source_of(folder)}
            print(f"  zipped {car:18s} {human(entries[car]['bytes'])}", flush=True)
        if a.dry_run:
            total = sum(e["bytes"] for e in entries.values())
            print(f"dry run: {len(cars)} zips, {human(total)}, nothing uploaded")
            return 0
        if gh("release", "view", tag, "-R", REPO, check=False).returncode != 0:
            notes = ("AG18's vehicle game packs (`vehicles/GAME.md`), one zip per car. "
                     "Fetch them with `python vehicles/packs.py fetch`, which checks every "
                     "hash against `vehicles/packs.json` and unpacks them into "
                     "`~/.cache/cybergen/vehicles/game/`.")
            gh("release", "create", tag, "-R", REPO, "--title", f"Vehicle packs {tag[14:]}",
               "--notes", notes, "--latest=false")
            print(f"  release {tag} created", flush=True)
        for car in cars:
            t0 = time.time()
            gh("release", "upload", tag, str(work / f"{car}.zip"), "-R", REPO, "--clobber")
            print(f"  uploaded {car:18s} {time.time() - t0:5.0f} s", flush=True)
        if man.get("tag") != tag:
            man["cars"] = {}
        man.update({"format": FORMAT, "version": VERSION, "repo": REPO, "tag": tag})
        man["cars"].update(entries)
        man["cars"] = dict(sorted(man["cars"].items()))
        MANIFEST.write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
        total = sum(e["bytes"] for e in man["cars"].values())
        print(f"{len(cars)} packs uploaded to {tag}; {len(man['cars'])} in all, {human(total)}; "
              f"commit {MANIFEST.relative_to(ROOT)}")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- fetch

def download(url: str, out: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "cybergen-packs"})
    with urllib.request.urlopen(req, timeout=60) as r, open(out, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)


def unpack(z: Path, car: str, base: Path, entry: dict) -> None:
    """Unpack into a fresh folder beside the pack, check every file, then swap it in (the
    old folder's `work/` and `proof/` are kept)."""
    dest = base / car
    tmp = base / f".{car}.fetch"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with zipfile.ZipFile(z) as zf:
        for info in zf.infolist():
            name = info.filename
            if info.is_dir():
                continue
            if not name.startswith(f"{car}/") or "/" in name[len(car) + 1:] or ".." in name:
                raise ValueError(f"{z.name}: unexpected entry {name}")
            (tmp / name[len(car) + 1:]).write_bytes(zf.read(info))
    got = file_hashes(tmp)
    if got != entry["files"]:
        bad = sorted(set(got) ^ set(entry["files"]) |
                     {k for k in got if entry["files"].get(k) not in (None, got[k])})
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError(f"{car}: files do not match packs.json: {', '.join(bad)}")
    dest.mkdir(parents=True, exist_ok=True)
    for p in shipped(dest):
        p.unlink()
    for p in tmp.iterdir():
        os.replace(p, dest / p.name)
    tmp.rmdir()


def cmd_fetch(a) -> int:
    base = packs_dir(a.dir)
    man = load_manifest()
    if not man.get("tag") or not man["cars"]:
        print("packs.json names no release yet", file=sys.stderr)
        return 1
    cars = a.cars or sorted(man["cars"])
    unknown = [c for c in cars if c not in man["cars"]]
    if unknown:
        print(f"not in the release: {', '.join(unknown)}", file=sys.stderr)
        return 1
    base.mkdir(parents=True, exist_ok=True)
    src = Path(a.from_dir).expanduser() if a.from_dir else None
    url = f"https://github.com/{man.get('repo', REPO)}/releases/download/{man['tag']}/"
    print(f"packs: {base}\nrelease: {man['tag']}")
    work = Path(tempfile.mkdtemp(prefix="cg_packs_"))
    failed = 0
    try:
        for car in cars:
            entry = man["cars"][car]
            folder = base / car
            if not a.force and (folder / "pack.json").is_file() and \
                    file_hashes(folder) == entry["files"]:
                print(f"  {car:18s} as released, kept")
                continue
            t0 = time.time()
            try:
                if src:
                    z = src / entry["asset"]
                    if not z.is_file():
                        raise FileNotFoundError(f"{z} not found")
                else:
                    z = work / entry["asset"]
                    download(url + entry["asset"], z)
                if sha256(z) != entry["sha256"]:
                    raise ValueError(f"{entry['asset']}: sha256 does not match packs.json")
                unpack(z, car, base, entry)
                if not src:
                    z.unlink()
                print(f"  {car:18s} {human(entry['bytes'])} in {time.time() - t0:.0f} s",
                      flush=True)
            except Exception as e:  # report and go on with the others
                failed += 1
                print(f"  {car:18s} FAILED: {e}", flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"{len(cars) - failed} of {len(cars)} packs ready" +
          (f", {failed} failed" if failed else ""))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", help="the packs' folder (default: $CITYGEN_VEHICLES, else "
                    "~/.cache/cybergen/vehicles/game)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status", help="local packs against packs.json")
    s.add_argument("--strict", action="store_true", help="exit 1 when a pack is missing or differs")
    f = sub.add_parser("fetch", help="download and unpack the released packs")
    f.add_argument("cars", nargs="*")
    f.add_argument("--from", dest="from_dir", help="a folder of zips already downloaded")
    f.add_argument("--force", action="store_true", help="fetch even packs that match")
    p = sub.add_parser("publish", help="zip and upload the local packs, rewrite packs.json")
    p.add_argument("cars", nargs="*")
    p.add_argument("--tag", help="the release's tag (default vehicle-packs-<today>)")
    p.add_argument("--dry-run", action="store_true", help="zip only, upload nothing")
    a = ap.parse_args(argv)
    return {"status": cmd_status, "fetch": cmd_fetch, "publish": cmd_publish}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
