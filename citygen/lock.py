"""M10: `citygen lock BUILD_DIR` freezes a built city as a versioned release, and `citygen
lock --verify LOCK` builds it again from the lock alone and compares.

A lock holds everything the city came from: the spec, the overrides each step used, the
district regenerations in their order (each with the district's spec entry and seed), the
choices the search made, the citygen version and the sha256 of its source code, and the
sha256 of `city_model.json`. Rebuilding runs the full build (search and all) from the spec,
applies the overrides, then each regeneration in turn, and must give the same bytes. With
other code (another `code_sha256`) the rebuild still runs but says so: a locked city is a
promise of the code it names.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import edit as E

LOCK_FILE = "city.lock.json"
LOCK_VERSION = 1


def make(build_dir, release: str | None = None) -> dict:
    """The lock of a build folder (its state and model)."""
    from .model import CityModel

    st = E.read_state(build_dir)
    mp = Path(build_dir) / "city_model.json"
    model = CityModel.from_json(mp.read_text(encoding="utf-8"))
    sha = E.model_sha(model)
    if sha != st["model_sha256"]:
        raise ValueError(f"{mp} is not the model its build state names (edited by hand?)")
    # a release names the code it ships with: only a build with this code shows it gives
    # these bytes
    now = E.code_version()
    if st["code_sha256"] != now["code_sha256"]:
        raise ValueError(f"{build_dir} was built with other citygen code "
                         f"({st['code_sha256'][:12]}, this one {now['code_sha256'][:12]}): "
                         f"build it again with this citygen to release it")
    return {"lock_version": LOCK_VERSION, "name": model.name,
            "release": release or str(len(st.get("edits", [])) + 1),
            "citygen": now["citygen"], "code_sha256": now["code_sha256"],
            "spec": st["spec"], "choices": st["choices"],
            "overrides": st.get("base_overrides", st.get("overrides")),
            "edits": st.get("edits", []), "model_sha256": sha}


def write(lock: dict, path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def rebuild(lock: dict, workers: int | None = None):
    """The city of a lock built again: (Built, state). The full build from the spec, its
    overrides, then each district regeneration of the lock in order."""
    from . import build as B
    from .validate import validate_spec

    res = validate_spec(lock["spec"])
    if not res.ok:
        raise ValueError("the lock's spec does not validate")
    built = B.build_city(res, workers=workers)
    built = finish(built, res, lock.get("overrides"))
    state = E.new_state(lock["spec"], built, lock.get("overrides"))
    for k, e in enumerate(lock.get("edits", [])):
        st = {**state, "edits": lock["edits"][:k], "overrides": e.get("overrides")}
        built, rec = E.regenerate(st, built.model, e["district"], entry=e["entry"],
                                  seed=e["seed"], workers=workers)
        state["edits"] = state["edits"] + [rec]
        state["overrides"] = rec["overrides"]
        state["model_sha256"] = rec["model_sha256"]
    return built, state


def finish(built, res, overrides: dict | None):
    """A full build with its overrides applied (and checked again)."""
    from . import build as B
    from . import overrides as OV

    if not overrides:
        return built
    model, notes = OV.apply(built.model, overrides)
    checks, stats = B.check_all(built.spec, model)
    built.model, built.checks = model, checks
    built.stats = {**built.stats, **stats}
    built.notes = built.notes + notes
    return built


def verify(lock: dict, workers: int | None = None) -> tuple[bool, list[str], object]:
    """(whether the rebuild gives the locked bytes, report lines, the rebuilt city)."""
    lines = []
    now = E.code_version()
    if now["code_sha256"] != lock["code_sha256"]:
        lines.append(f"note: this citygen ({now['citygen']}, code {now['code_sha256'][:12]}) "
                     f"is not the locked one ({lock['citygen']}, code "
                     f"{lock['code_sha256'][:12]}); the bytes may differ")
    built, _ = rebuild(lock, workers)
    sha = E.model_sha(built.model)
    ok = sha == lock["model_sha256"]
    lines.append(f"{'PASS' if ok else 'FAIL'}: {lock['name']} release {lock['release']}: "
                 f"rebuilt model {sha} {'=' if ok else '!='} locked {lock['model_sha256']}")
    return ok, lines, built
