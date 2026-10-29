"""AG6's stage of `assetgen build` (scope 5.2): the shared library, then the city's
materials.

1. `library_for(spec)`: the library at the spec's texel densities (`library.generate`,
   kept when its generator is unchanged), linked as `BUILD/assets/library`.
2. After the buildings and the streets: the city's sign, ad and logo pages (`signage`,
   `BUILD/assets/textures/`, `signs.json`), which AG8's sign meshes then show.
3. After AG8's props (`stage`): `materials.json` (every material of the city's
   contributions with its master, textures and parameters, and the texture table),
   `unreal_contribution.materials.json` (`contrib.materials_part`), the checks (texel
   density from the packs' UVs, AG8's props and plants among them, texture budgets) and
   `materials_report.json` / `.txt` (written only when another file changed, so an
   unchanged rebuild writes none).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from .. import manifest as MF
from . import checks as CK
from . import contrib as CO
from . import library as LB
from . import signage as SG
from .atlases import ATLASES

LINK = "library"


def library_for(spec_doc: dict | None, out: Path | None = None, workers: int | None = None,
                log=print, progress=None) -> dict:
    """The library at the spec's density (made or kept), linked from BUILD/assets/library
    when `out` (the assets folder) is given."""
    density = int((spec_doc or {}).get("texel_density_px_m", LB.DENSITY))
    lib = LB.load(None, density)
    want = LB.code_hash()
    if lib is None or lib.get("code_hash") != want or not _complete(lib):
        lib = generate(None, density, workers, log=log, progress=progress)
    if out is not None:
        link(out, Path(lib["dir"]))
    return lib


def generate(out=None, density: int = LB.DENSITY, workers: int | None = None,
             only: list[str] | None = None, log=print, progress=None) -> dict:
    """`library.generate` with a progress stage (`assetgen/progress.py`) driven by its log
    lines: the count to make, then a line per set or atlas made. (The library's own code
    stays as it is: it is in the library's code hash, which the contributions record.)"""
    if progress is None:
        return LB.generate(out, density, workers, only, log=log)
    with progress.stage("library") as st:
        def line(text: str) -> None:
            m = re.match(r"library: (\d+) sets and (\d+) atlases to make", text)
            if m:
                st.set_total(int(m.group(1)) + int(m.group(2)))
                st.note(text)
            elif text.startswith(("  set ", "  atlas ")):
                st.advance()
        return LB.generate(out, density, workers, only, log=line)


def _complete(lib: dict) -> bool:
    d = Path(lib["dir"])
    names = set(LB.sets())
    if set(lib["sets"]) != names or set(lib["atlases"]) != set(ATLASES):
        return False
    return all((d / f["file"]).is_file() for g in ("sets", "atlases")
               for r in lib[g].values() for f in r["files"].values())


def link(out: Path, target: Path) -> None:
    """BUILD/assets/library -> the library folder (a symbolic link; replaced when it points
    elsewhere). On Windows without the symlink privilege (WinError 1314) it is a directory
    junction, which needs none."""
    p = out / LINK
    out.mkdir(parents=True, exist_ok=True)
    if p.is_symlink():
        if Path(os.readlink(p)) == target:
            return
        p.unlink()
    elif p.is_junction():
        if p.resolve() == target.resolve():
            return
        p.rmdir()                                 # the junction only, not the library
    elif p.exists():
        return
    try:
        p.symlink_to(target, target_is_directory=True)
    except OSError as e:
        if getattr(e, "winerror", None) != 1314:
            raise
        import _winapi

        _winapi.CreateJunction(str(target.resolve()), str(p))


def signage(model, out: Path, spec_doc: dict, log=print) -> dict:
    """The city's sign pages and signs.json (`signage.build`; "wrote": files written)."""
    density = int(spec_doc.get("texel_density_px_m", LB.DENSITY))
    return SG.build(model, spec_doc, out / "textures", density, log)


def stage(model, model_sha: str, out: Path, spec_doc: dict, lib: dict, log=print,
          signs: dict | None = None, progress=None) -> dict:
    """`signs`: the pages already made this build (`signage`), else made here. `progress`:
    stage lines and a bar over the packs the density check reads (`assetgen/progress.py`)."""
    from ..progress import Progress
    P = progress if progress is not None else Progress(quiet=True)
    t0 = time.perf_counter()
    density = int(spec_doc.get("texel_density_px_m", LB.DENSITY))
    upper = int(spec_doc.get("texel_density_upper_px_m", LB.UPPER))
    if signs is None:
        with P.stage("signage") as st:
            signs = signage(model, out, spec_doc, log if progress is None else st.note)
    wrote = signs.pop("wrote")
    t1 = time.perf_counter()
    con = CO.materials_part(model.name, model_sha, lib, signs)
    wrote += int(MF.write_if_changed(out / "unreal_contribution.materials.json",
                                     MF.dumps(con)))
    doc = {"version": 1, "city": model.name, "library": con["library"],
           "parts": {}, "textures": {}}
    for part in ("buildings", "streets", "props", "signs", "materials"):
        p = out / f"unreal_contribution.{part}.json"
        if not p.is_file():
            continue
        c = json.loads(p.read_text(encoding="utf-8"))
        doc["parts"][part] = {k: {kk: vv for kk, vv in v.items()}
                              for k, v in sorted(c.get("materials", {}).items())}
        doc["textures"].update(c.get("textures") or {})
    doc["textures"] = dict(sorted(doc["textures"].items()))
    wrote += int(MF.write_if_changed(out / "materials.json", MF.dumps(doc)))
    t2 = time.perf_counter()
    with P.stage("materials: texel density", total=len(CK.packs(out))) as st:
        dens = CK.texel_density(out, lib, density, upper, step=st.advance)
    t3 = time.perf_counter()
    bud = CK.budget(LB.disk(lib), signs, out)
    checks = [dens, bud]
    rep = {"city": model.name, "library": {**con["library"], "dir": lib["dir"],
                                           "sets": len(lib["sets"]),
                                           "atlases": len(lib["atlases"]),
                                           **LB.disk(lib)},
           "signs": signs["counts"], "materials": {k: len(v) for k, v in doc["parts"].items()},
           "textures": len(doc["textures"]),
           "checks": {c["name"]: c for c in checks}, "ok": all(c["ok"] for c in checks),
           "seconds": {"signage": round(t1 - t0, 2), "materials": round(t2 - t1, 2),
                       "texel_density": round(t3 - t2, 2),
                       "total": round(time.perf_counter() - t0, 2)}}
    if wrote or not (out / "materials_report.json").is_file():
        wrote += int(MF.write_if_changed(out / "materials_report.json", MF.dumps(rep)))
        wrote += int(MF.write_if_changed(out / "materials_report.txt", report_text(rep)))
    rep["files_written"] = wrote
    if progress is None:
        log(f"materials: {rep['textures']} textures, {signs['counts']['texts']} sign texts, "
            f"texel density {'ok' if dens['ok'] else 'FAILS'} over {dens['triangles']:,} "
            f"triangles, {wrote} files written")
    return rep


def report_text(rep: dict) -> str:
    lib = rep["library"]
    lines = [f"assetgen materials (AG6): {rep['city']}",
             f"{'all checks pass' if rep['ok'] else 'CHECKS FAIL'}",
             f"library {lib['version']} {lib['hash']} at {lib['density_px_m']} px/m: "
             f"{lib['sets']} sets, {lib['atlases']} atlases, "
             f"{lib['source_bytes'] / 1e6:.0f} MB source, {lib['cooked_bytes'] / 1e6:.0f} MB "
             f"cooked (estimate)",
             f"signs: {rep['signs']}", f"materials per part: {rep['materials']}, "
             f"{rep['textures']} textures", ""]
    for name, c in rep["checks"].items():
        extra = {k: v for k, v in c.items() if k not in ("name", "ok", "first", "slots")}
        lines.append(f"{'PASS' if c['ok'] else 'FAIL'} {name}: {extra}")
        if c.get("first"):
            lines.append(f"     first: {c['first']}")
        for s, r in (c.get("slots") or {}).items():
            lines.append(f"     {s}: {r}")
    lines.append(f"seconds: {rep['seconds']}")
    return "\n".join(lines) + "\n"
