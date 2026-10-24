"""
Versioned map files: maps/corporate_core_v<major>.<minor>[.<patch>...].svg

Usage:  python3 map_version.py latest MAPS_DIR   -> path of the highest version
        python3 map_version.py next FILE.svg     -> same name with the patch number bumped
                                                    (v1.0 -> v1.0.1, v1.0.1 -> v1.0.2)
Versions compare numerically, so v1.10 is newer than v1.9.
"""
import re, sys
from pathlib import Path

PATTERN = re.compile(r"^(?P<stem>.+)_v(?P<ver>\d+(?:\.\d+)*)\.svg$")

def version(path):
    m = PATTERN.match(Path(path).name)
    return tuple(int(v) for v in m.group("ver").split(".")) if m else None

def latest(maps_dir, stem="corporate_core"):
    files = [p for p in Path(maps_dir).glob(f"{stem}_v*.svg") if version(p)]
    if not files:
        sys.exit(f"no {stem}_v*.svg in {maps_dir}")
    return max(files, key=version)

def next_version(path):
    path = Path(path)
    m = PATTERN.match(path.name)
    if not m:
        sys.exit(f"{path.name} has no _v<version> suffix")
    v = list(version(path)) + [0] * max(0, 3 - len(version(path)))
    v[-1] += 1
    return path.with_name(f"{m.group('stem')}_v{'.'.join(map(str, v))}.svg")

if __name__ == "__main__":
    cmd, arg = sys.argv[1], sys.argv[2]
    print(latest(arg) if cmd == "latest" else next_version(arg))
