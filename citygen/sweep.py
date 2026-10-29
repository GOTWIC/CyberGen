"""`citygen sweep`: build many specs at many seeds (no blockout) and tabulate the results.

Each build runs in its own worker process (one build per process, `CITYGEN_WORKERS=1` inside
it, so `--workers` is the whole CPU budget) and records: pass or fail, the failing check ids
with their first failure, the retries the build used (hydrology variant, road variant, the
full-city retries with their failure counts, the layout salt), the build time, the sha256 of
`city_model.json`, and a traceback when it crashed. The table goes to `sweep.md` and
`sweep.json` in the output folder, rewritten after every build; each build's report and
previews go to `<out>/<label>_s<seed>/`.

The `m8a` suite is the five sample cities and the pinned demo, each at its own seed and at
the extra seeds, and the test specs (`SMALL`, `MINIMAL`, `PINNED`, `DELTA`) at their own seed
and the first few extra seeds.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import multiprocessing
import os
import re
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = [ROOT / "docs" / "progress" / "M1a2" / n / "city_spec.json"
           for n in ("archipelago_free_port", "delta_megacity", "nexus_city", "peninsula_city")
           ] + [ROOT / "cities" / "vesper_bay" / "city_spec.json",
                ROOT / "cities" / "vesper_bay_pinned" / "city_spec.json"]
EXTRA_SEEDS = [11, 404, 1999, 3141, 5077, 8128, 27182]
TEST_SPECS = [("conftest", "SMALL"), ("conftest", "MINIMAL"), ("test_pinned", "PINNED"),
              ("test_quality", "DELTA")]
TEST_EXTRA = 4          # extra seeds for the test specs
RETRY_NOTE = re.compile(r"left (\d+) check failures in the full city")


def _test_spec(module: str, name: str) -> dict:
    tests = ROOT / "tests"
    if str(tests) not in sys.path:
        sys.path.insert(0, str(tests))
    spec = importlib.util.spec_from_file_location(f"_sweep_{module}", tests / f"{module}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return copy.deepcopy(getattr(mod, name))


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def suite_jobs(name: str, extra: list[int]) -> list[tuple[str, dict, int]]:
    """(label, spec data, seed) for every build of a suite."""
    if name != "m8a":
        raise ValueError(f"unknown suite {name!r}")
    jobs = []
    for p in SAMPLES:
        data = json.loads(p.read_text(encoding="utf-8"))
        label = p.parent.name
        for s in [data["seed"]] + [s for s in extra if s != data["seed"]]:
            jobs.append((label, data, s))
    for module, var in TEST_SPECS:
        data = _test_spec(module, var)
        for s in [data["seed"]] + [s for s in extra[:TEST_EXTRA] if s != data["seed"]]:
            jobs.append((f"test_{var.lower()}", data, s))
    return jobs


def spec_jobs(paths: list[str], seeds: list[int] | None, extra: list[int]):
    jobs = []
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        label = Path(p).parent.name if Path(p).name == "city_spec.json" else Path(p).stem
        own = data.get("seed")
        ss = seeds if seeds else ([own] if own is not None else []) + \
            [s for s in extra if s != own]
        jobs.extend((label, data, s) for s in ss)
    return jobs


def _retries(b) -> dict:
    tries = b.stats.get("city_tries")
    fails = [t["failures"] for t in tries[:-1]] if tries else \
        [int(m.group(1)) for n in b.notes for m in [RETRY_NOTE.search(n)] if m]
    return {"hydro_variant": b.variant, "road_variant": b.stats.get("road_variant"),
            "city_retries": len(fails), "retry_fails": fails,
            "layout_salt": b.stats.get("layout_salt", 0)}


def run_job(label: str, data: dict, seed: int, out: str, upto: str, previews: bool,
            keep_model: bool) -> dict:
    """One build in this (worker) process; never raises."""
    os.environ["CITYGEN_WORKERS"] = "1"
    row = {"label": label, "seed": seed, "status": "crash", "failed": [], "seconds": None}
    t0 = time.perf_counter()
    d = Path(out) / f"{label}_s{seed}"
    try:
        from .build import build_city, write_outputs
        from .validate import validate_spec

        spec = copy.deepcopy(data)
        spec["seed"] = seed
        res = validate_spec(spec)
        if not res.ok:
            row["status"] = "invalid"
            row["error"] = "; ".join(str(i) for i in res.errors)
            return row
        b = build_city(res, workers=1, local=upto != "roads", buildings=upto == "full")
        row["seconds"] = round(time.perf_counter() - t0, 1)
        row["failed"] = [{"id": c.id, "count": len(c.failures), "first": c.failures[0]}
                         for c in b.checks if not c.passed]
        row["status"] = "pass" if b.passed else "fail"
        row.update(_retries(b))
        js = b.model.to_json() + "\n"
        row["sha256"] = hashlib.sha256(js.encode("utf-8")).hexdigest()
        if previews:
            write_outputs(b, d)
            if not keep_model:
                (d / "city_model.json").unlink()
        else:
            d.mkdir(parents=True, exist_ok=True)
            (d / "report.json").write_text(json.dumps(b.report(), indent=2) + "\n",
                                           encoding="utf-8", newline="\n")
    except BaseException:
        row["traceback"] = traceback.format_exc()
        row["seconds"] = round(time.perf_counter() - t0, 1)
        d.mkdir(parents=True, exist_ok=True)
        (d / "traceback.txt").write_text(row["traceback"], encoding="utf-8", newline="\n")
    return row


def _retry_text(r: dict) -> str:
    if "hydro_variant" not in r:
        return ""
    s = f"hv{r['hydro_variant']} rv{r['road_variant']}"
    if r["city_retries"]:
        s += f" city x{r['city_retries']} ({','.join(map(str, r['retry_fails']))})"
    if r["layout_salt"]:
        s += f" salt {r['layout_salt']}"
    return s


def _cell(s: str, n: int = 160) -> str:
    s = s.replace("|", "/").replace("\n", " ")
    return s if len(s) <= n else s[:n - 3] + "..."


def table(rows: list[dict], title: str = "citygen sweep") -> str:
    rows = sorted(rows, key=lambda r: (r["label"], r["seed"]))
    n = len(rows)
    ok = sum(r["status"] == "pass" for r in rows)
    lines = [f"# {title}", "",
             f"{ok} of {n} builds pass ({100 * ok / n:.0f}%)" if n else "no builds", ""]
    by_label: dict[str, list] = {}
    for r in rows:
        by_label.setdefault(r["label"], []).append(r)
    lines += ["| spec | pass | builds |", "|---|---|---|"]
    lines += [f"| {k} | {sum(r['status'] == 'pass' for r in v)} | {len(v)} |"
              for k, v in by_label.items()]
    counts: dict[str, int] = {}
    for r in rows:
        for f in r["failed"]:
            counts[f["id"]] = counts.get(f["id"], 0) + 1
        if r["status"] == "crash":
            counts["(crash)"] = counts.get("(crash)", 0) + 1
    if counts:
        lines += ["", "| failing check | builds |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    lines += ["", "| spec | seed | result | failing checks (first failure) | retries | s |",
              "|---|---|---|---|---|---|"]
    for r in rows:
        if r["status"] == "crash":
            tb = r.get("traceback", "").strip().splitlines()
            what = "crash: " + _cell(tb[-1] if tb else "?")
        elif r["status"] == "invalid":
            what = "invalid spec: " + _cell(r.get("error", ""))
        else:
            what = "<br>".join(f"{f['id']} ({f['count']}): {_cell(f['first'])}"
                               for f in r["failed"])
        lines.append(f"| {r['label']} | {r['seed']} | {r['status']} | {what} | "
                     f"{_retry_text(r)} | {r['seconds']} |")
    return "\n".join(lines) + "\n"


def sweep(jobs: list[tuple[str, dict, int]], out: str | Path, workers: int = 4,
          upto: str = "full", previews: bool = True, keep_model: bool = False,
          log=print) -> list[dict]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    def save():
        (out / "sweep.json").write_text(json.dumps(rows, indent=1) + "\n",
                                        encoding="utf-8", newline="\n")
        (out / "sweep.md").write_text(table(rows), encoding="utf-8", newline="\n")

    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max(1, workers), mp_context=ctx, max_tasks_per_child=1) as pool:
        futs = {pool.submit(run_job, lab, data, s, str(out), upto, previews, keep_model):
                (lab, s) for lab, data, s in jobs}
        for fut in as_completed(futs):
            lab, s = futs[fut]
            try:
                r = fut.result()
            except BaseException:      # the worker died (memory, signal)
                r = {"label": lab, "seed": s, "status": "crash", "failed": [],
                     "seconds": None, "traceback": traceback.format_exc()}
            rows.append(r)
            save()
            log(f"[{len(rows)}/{len(jobs)}] {lab} s{s}: {r['status']} "
                f"{' '.join(f['id'] for f in r['failed'])} ({r['seconds']} s)", flush=True)
    save()
    return rows
