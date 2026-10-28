"""The asset manifest (scope section 6) and writing files only when they change.

`BUILD/assets/manifest.json` holds assetgen's versions, the hashes of what the build read,
and one section per kind of asset, each keyed by citygen id: `buildings` (AG1 on) and the
tile packs that hold them under `tiles`. A stage that writes another section (street
elements, props) keeps the sections it does not own as they were (`merge`).

Every file assetgen writes goes through `write_if_changed`: same bytes, no write, so a
rebuild of an unchanged city writes nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

MANIFEST = "manifest.json"
MANIFEST_VERSION = 1


def dumps(doc: dict) -> str:
    """Deterministic JSON text (sorted keys, one space indent, `\\n` line ends)."""
    return json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=False,
                      allow_nan=False) + "\n"


def load(out_dir: str | Path) -> dict | None:
    p = Path(out_dir) / MANIFEST
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def merge(old: dict | None, new: dict, owned: tuple[str, ...]) -> dict:
    """The new manifest with the old one's sections this writer does not own kept."""
    out = dict(new)
    if old:
        for k, v in old.items():
            if k not in out and k not in owned:
                out[k] = v
    return out


def write_if_changed(path: str | Path, data: bytes | str) -> bool:
    """Write the file unless it already holds exactly these bytes; whether it wrote."""
    p = Path(path)
    b = data.encode("utf-8") if isinstance(data, str) else data
    if p.is_file() and p.stat().st_size == len(b) and p.read_bytes() == b:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(b)
    tmp.replace(p)
    return True
