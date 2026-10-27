"""`citygen build`: spec -> city model (water, districts, inner waterways, megasite reserves,
primary roads and bridges), checks, preview.

The free hydrology parameters (where an unpinned river enters, how its course bulges, where a
delta splits) are tried in a few seeded variants; each variant is built and checked, and the
first one that passes every check with (worst share error + share of land without a district)
under 10% wins, else the best one (fewest failures, then that quality figure). Variant 0 uses
the defaults, so the search only matters when the default does not fit.
Megasite reserves and the primary road network (M1b) are built on the chosen variant; when no
road variant passes every check there, the roads fall back to the next best variants that
passed the water and district checks (at most ROAD_CANDIDATES in all).
Same spec + seed = byte-identical `city_model.json`, on any machine: the generator uses
deterministic elementary functions (`dmath`), exact measures and grid-snapped geometry
wherever a decision is made, and every stage hands the next one coordinates on the 0.01 m
grid.

Variants and road attempts run in worker processes when there are several CPUs
(`CITYGEN_WORKERS` sets how many; 1 runs everything in this process). They are evaluated in
batches in a fixed order and chosen by the same rules as one at a time, so the result does
not depend on the number of workers.
"""

from __future__ import annotations

import copy
import hashlib
import json
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from shapely.ops import unary_union

from . import checks as C
from . import districts as D
from . import geom as G
from . import hydro as H
from . import local as LC
from . import megasites as MS
from . import roads as RD
from . import trace as T
from . import waterways as W
from .model import CityModel
from .spec import CitySpec
from .validate import Result, dump_spec

MAX_VARIANTS = 20
GOOD_QUALITY = 0.10
ROAD_CANDIDATES = 3
CITY_RETRIES = 8       # M7: layouts or road networks a failing full city tries next (M8a: 4 -> 8,
                       # so the next road network gets its own layouts too)
LAYOUT_SALTS = 3       # of them, local layouts on the same roads first


@dataclass
class Built:
    spec: CitySpec
    model: CityModel
    hydro: H.Hydro
    layout: D.Layout
    waterways: W.Waterways
    checks: list[C.Check]
    stats: dict
    variant: int
    notes: list[str]
    sites: list = None
    roads: object = None
    local: object = None
    m3: object = None

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def report(self) -> dict:
        return C.report_dict(self.spec, self.checks, self.stats, self.notes, self.variant)


def _district_ids(spec: CitySpec) -> dict[str, str]:
    return {d.name: f"d{i + 1:02d}" for i, d in enumerate(spec.districts)}


def assemble(spec: CitySpec, h: H.Hydro, lay: D.Layout, ww: W.Waterways,
             explicit: set[str], sites: list | None = None,
             roads: RD.RoadNet | None = None, local: LC.Local | None = None,
             m3: dict | None = None) -> CityModel:
    P = G.to_model_poly
    did = _district_ids(spec)
    lm_ids = {k: f"lm{k + 1:02d}" for k in range(len(h.landmasses))}
    on_lm: dict[int, list[str]] = {}
    for d in spec.districts:
        k = lay.landmass_of.get(d.name)
        if k is not None and d.name in lay.polygons:
            on_lm.setdefault(k, []).append(did[d.name])
    isl_lm = {}
    for isl in h.islands:
        isl_lm[isl.name] = D.island_landmass(h, isl.name)
    landmasses = []
    for k, lm in enumerate(h.landmasses):
        isl = next((n for n, j in isl_lm.items() if j == k), None)
        landmasses.append({"id": lm_ids[k], "polygon": P(lm), "district_ids": on_lm.get(k, []),
                           "attrs": {"area_m2": round(lm.area, 1), "island": isl}})
    islands = []
    for i, isl in enumerate(h.islands):
        if isl.polygon is None:
            continue
        k = isl_lm[isl.name]
        islands.append({"id": f"isl{i + 1:02d}", "type": "island.filler" if isl.filler else None,
                        "name": isl.name, "polygon": P(isl.polygon), "setting": isl.setting,
                        "landmass_id": lm_ids.get(k),
                        "attrs": {"target_area_m2": round(isl.target_m2, 1)}})
    sea = G.clean(h.sea.intersection(h.water))
    seas = [{"id": "sea", "name": spec.water.coast.name, "polygons": G.to_model_polys(sea)}] \
        if not sea.is_empty else []
    rivers, channels = [], []
    for b in h.bodies:
        poly = b.polygon
        if b.kind != "separation":
            poly = unary_union([poly] + [r for r in G.parts(h.rings) if r.intersects(poly)])
        poly = G.clean(poly.intersection(h.water).difference(sea))
        part = G.parts(poly)
        if not part:
            continue
        line = G.line_coords(b.centerline)
        widths = list(b.widths)[:len(line)] + [b.widths[-1]] * max(0, len(line) - len(b.widths))
        base = {"id": b.id, "centerline": line, "width_m": widths, "polygon": P(part[0]),
                "attrs": {k: v for k, v in b.attrs.items() if not k.startswith("_")}}
        if b.kind == "river":
            rivers.append({**base, "name": b.name, "mouth": b.mouth, "flows_into": b.flows_into})
        else:
            channels.append({**base, "name": b.name, "kind": b.kind,
                             "type": f"channel.{b.kind}",
                             "river_id": b.parent_id, "flows_into": b.flows_into})
    waterways = [{"id": w.id, "type": f"waterway.{w.style}", "kind": w.kind, "name": w.name,
                  "district_id": did[w.district],
                  "centerline": G.line_coords(w.centerline) if w.centerline is not None else [],
                  "polygon": P(w.polygon), "connects_to": w.connects_to,
                  "ornamental": w.ornamental} for w in ww.items]
    quays = [{"id": q.id, "waterway_id": q.waterway_id, "line": G.line_coords(q.line),
              "width_m": q.width_m} for q in ww.quays]
    open_spaces = open_land(spec, h, lay, landmasses, islands, lm_ids)
    districts = []
    for d in spec.districts:
        poly = lay.polygons.get(d.name)
        if poly is None or poly.is_empty:
            continue
        params = d.model_dump(mode="json", by_alias=True, exclude_none=True,
                              exclude={"name", "archetype", "seed"})
        source = lay.share_source.get(d.name, "spec")
        districts.append({
            "id": did[d.name], "name": d.name, "archetype": d.archetype,
            "type": f"district.{d.archetype}", "polygon": P(poly),
            "landmass_id": lm_ids.get(lay.landmass_of.get(d.name)), "seed": d.seed,
            "params": params,
            "attrs": {"area_m2": round(poly.area, 1),
                      "area_share_target": round(lay.shares[d.name], 6),
                      "area_share_source": source}})
    data = {
        "name": spec.name, "seed": spec.seed,
        "spec_sha256": hashlib.sha256(dump_spec(spec).encode()).hexdigest(),
        "bounds": [round(v, 2) for v in h.canvas.bounds],
        "land": [{"id": "land", "polygons": G.to_model_polys(h.land)}],
        "landmasses": landmasses, "islands": islands, "seas": seas, "rivers": rivers,
        "channels": channels, "waterways": waterways, "quays": quays, "districts": districts,
        "open_spaces": open_spaces,
    }
    if sites:
        data["megasites"] = [{
            "id": s.id, "type": f"megasite.{s.kind}", "kind": s.kind, "name": s.name,
            "district_id": did[s.district], "polygon": P(s.polygon),
            "height_limit_m": s.height_limit_m,
            "flight_cone": P(s.flight_cone) if s.flight_cone is not None else None,
            "attrs": {"area_m2": round(s.polygon.area, 1), "target_area_m2": round(s.target_m2, 1),
                      "reserve": True}} for s in sites]
    if roads is not None:
        data["road_nodes"] = roads.nodes
        data["road_segments"] = roads.segments
        data["bridges"] = [{k: v for k, v in b.items() if k not in ("s0", "s1")}
                           for b in roads.bridges]
        for b in data["bridges"]:
            a = b["attrs"] = dict(b["attrs"])  # the road network keeps its own attrs
            b["water_class"] = a.pop("water_class")
            b["span_m"] = a.pop("span_m")
            b["ramp_length_m"] = a.pop("ramp_length_m")
            b.pop("road_class", None)
        data["tunnels"] = [dict(t) for t in roads.tunnels]
    if roads is not None and roads.terrain is not None:
        from . import terrain as TE

        f, lv, tst = roads.terrain
        graded = getattr(local, "terrain", None) if local is not None else None
        data["terrain"] = TE.terrain_rows(f, lv, tst if graded is None else graded["stats"],
                                          None if graded is None else graded["ground"])
    if local is not None:
        data["road_nodes"] = local.nodes
        data["road_segments"] = local.segments
        bridges = []
        for b in local.bridges:
            b = {k: v for k, v in b.items() if k not in ("s0", "s1", "road_class")}
            a = dict(b["attrs"])
            for key in ("water_class", "span_m", "ramp_length_m"):
                if key in a:
                    b[key] = a.pop(key)
            b["attrs"] = a
            bridges.append(b)
        data["bridges"] = bridges
        from . import tunnels as TN

        data["tunnels"] = TN.relink(roads.tunnels, local.segments)
        for key in ("junctions", "crosswalks", "sidewalks", "lanes", "walkways", "blocks",
                    "lots", "places"):
            data[key] = getattr(local, key)
        data["open_spaces"] = data["open_spaces"] + local.open_spaces
    if m3 is not None:
        data.update(m3)
    return CityModel.model_validate(data)


def open_land(spec: CitySpec, h: H.Hydro, lay: D.Layout, landmasses: list[dict],
              islands: list[dict], lm_ids: dict[int, str]) -> list[dict]:
    """Landmasses without a district become named open land instead of orphan wedges: a
    marsh when a delta channel bounds it (the land between distributaries), else a park.
    Filler islets stay plain islands, and when every district sits on its own island the
    remaining mainland is outside the city and stays unassigned."""
    if spec.districts and all(d.placement.on_island for d in spec.districts):
        return []
    fillers = {i["landmass_id"] for i in islands if i.get("type") == "island.filler"}
    branches = [b for b in h.bodies if b.kind == "delta_branch"]
    out = []
    for k, lm in enumerate(h.landmasses):
        lid = lm_ids[k]
        rec = landmasses[k]
        if rec["district_ids"] or lid in fillers:
            continue
        near = sorted(((b.polygon.distance(lm), b.id, b) for b in branches),
                      key=lambda x: (x[0], x[1]))
        if near and near[0][0] < 5.0:
            b = near[0][2]
            named = next((x[2] for x in near if x[0] < 5.0 and x[2].name), None)
            river = h.body(b.parent_id)
            base = named.name if named else (river.name if river else "Delta")
            kind, name = "marsh", f"{base} Marsh"
        else:
            near_d = min(((p.distance(lm), n) for n, p in lay.polygons.items()),
                         default=(0.0, spec.name))[1]
            kind, name = "park", f"{rec['attrs'].get('island') or near_d} Park"
        taken = {o["name"] for o in out}
        if name in taken:
            name = f"{name} {sum(1 for o in out if o['name'].startswith(name)) + 1}"
        out.append({"id": f"os{len(out) + 1:02d}", "type": f"open_space.{kind}", "kind": kind,
                    "name": name, "polygon": G.to_model_poly(lm),
                    "attrs": {"landmass_id": lid, "area_m2": round(lm.area, 1),
                              "reason": "delta wedge" if kind == "marsh" else
                              "land without a district"}})
    return out


def build_variant(spec: CitySpec, explicit: set[str], index: int) -> Built:
    with T.scope(f"v{index}"):
        canvas = G.canvas_for(spec.size_km)
        h = H.build_hydro(spec, canvas, H.Variant.make(spec, index))
        lay = D.layout_districts(spec, h, explicit)
        T.stage("districts", lay.polygons)
        D.finalize(spec, h, lay)
        T.stage("districts_after_channels", [lay.polygons, h.landmasses])
        did = _district_ids(spec)
        ww = W.build_waterways(spec, h, lay.polygons, did)
        T.stage("waterways", [ww.items, ww.quays])
    model = assemble(spec, h, lay, ww, explicit)
    checks, st = C.run_checks(spec, model, roads=False)
    T.stage(f"v{index}/checks", [[c.id, c.passed] for c in checks])
    st["separation_budget"] = lay.separation
    notes = h.notes + lay.notes
    return Built(spec, model, h, lay, ww, checks, st, index, notes)


def _score(b: Built) -> tuple:
    """(failed check items, quality, assignment cost); quality adds the worst share error and
    the share of land left without a district (filler islets aside)."""
    fails = sum(len(c.failures) for c in b.checks)
    errs = [abs(r["error"]) for r in b.stats["districts"] if r["error"] is not None]
    st = b.stats
    empty = st["unassigned_land_km2"] / st["land_km2"] if st["land_km2"] else 0.0
    if all(d.placement.on_island for d in b.spec.districts):
        empty = 0.0  # every district has its island; the rest of the land stays outside
    quality = max(errs, default=0.0) + empty
    return (fails, round(quality, 4), round(b.layout.assignment_cost, 4))


def default_workers() -> int:
    env = os.environ.get("CITYGEN_WORKERS", "").strip()
    if env:
        return max(1, int(env))
    return max(1, min(os.cpu_count() or 1, 8))


class _Runner:
    """Runs jobs and returns their results in order, in worker processes when there are
    several workers. A job returns (result, trace entries); the entries are recorded here in
    job order, so a trace does not depend on the number of workers either."""

    def __init__(self, workers: int):
        self.workers = max(1, workers)
        self.pool = None

    @property
    def parallel(self) -> bool:
        return self.workers > 1

    def map(self, fn, jobs: list) -> list:
        if not self.parallel or len(jobs) <= 1:
            return [fn(*job, False) for job in jobs]
        if self.pool is None:
            self.pool = ProcessPoolExecutor(self.workers,
                                            mp_context=multiprocessing.get_context("spawn"))
        return list(self.pool.map(fn, *zip(*[(*job, True) for job in jobs])))

    def submit(self, fn, jobs: list):
        """Start the jobs and return a function that waits for their results (in order); this
        process can work on something else meanwhile."""
        if not self.parallel or len(jobs) <= 1:
            return lambda: [fn(*job, False) for job in jobs]
        if self.pool is None:
            self.pool = ProcessPoolExecutor(self.workers,
                                            mp_context=multiprocessing.get_context("spawn"))
        futs = [self.pool.submit(fn, *job, True) for job in jobs]
        return lambda: [f.result() for f in futs]

    def close(self) -> None:
        if self.pool is not None:
            self.pool.shutdown()


def _collect(trace_here: bool, fn, *args):
    """(fn(*args), its trace entries): a worker process traces into its own log, which goes
    back with the result; in this process the entries go straight into the log."""
    if not trace_here:
        return fn(*args), None
    T.start()
    out = fn(*args)
    return out, T.stop()


def _variant_job(spec: CitySpec, explicit: set[str], index: int, tracing: bool, worker: bool):
    return _collect(worker and tracing, build_variant, spec, explicit, index)


def _good(b: Built) -> bool:
    return b.passed and _score(b)[1] <= GOOD_QUALITY


def build_city(result: Result, max_variants: int = MAX_VARIANTS, roads: bool = True,
               workers: int | None = None, local: bool = True,
               buildings: bool = True) -> Built:
    spec = result.filled
    explicit = {d.name for d in result.spec.districts if d.area_share is not None}
    run = _Runner(default_workers() if workers is None else workers)
    try:
        built: list[Built] = []
        for start in range(0, max_variants, run.workers):
            jobs = [(spec, explicit, i, T.on())
                    for i in range(start, min(start + run.workers, max_variants))]
            for b, entries in run.map(_variant_job, jobs):
                T.extend(entries)
                built.append(b)
                if _good(b):
                    break
            if _good(built[-1]):
                break
        ranked = sorted(built, key=lambda b: (_score(b), b.variant))
        if not roads:
            return ranked[0]
        b = add_roads(ranked, explicit, run)
        # M8a: no road network on these variants passes (an exit edge without land, say):
        # the next variants in turn, the first that passes with its roads wins; in index
        # order, so the result does not depend on the number of workers
        nxt = len(built)
        while sum(len(c.failures) for c in b.checks) and nxt < max_variants:
            jobs = [(spec, explicit, i, T.on())
                    for i in range(nxt, min(nxt + run.workers, max_variants))]
            nxt += len(jobs)
            found = None
            for v, entries in run.map(_variant_job, jobs):
                T.extend(entries)
                built.append(v)
                if v.passed:
                    t = add_roads([v], explicit, run)
                    if not sum(len(c.failures) for c in t.checks):
                        found = t
                        break
            if found is not None:
                found.notes = [f"no road network passed on the first variants; hydrology "
                               f"variant {found.variant} has one"] + found.notes
                b = found
                ranked = [x for x in built if x.variant == b.variant] + \
                    [x for x in sorted(built, key=lambda x: (_score(x), x.variant))
                     if x.variant != b.variant]
        if not local:
            return b
        # the whole city on these roads; when a later stage fails a check, again with the
        # local layout drawn again (district seeds salted, LAYOUT_SALTS times), then on the
        # next road network that passes, at most CITY_RETRIES more tries in all; the try
        # with the fewest failures wins
        tried = {(b.variant, b.stats["road_variant"])}
        base = _pristine(b)
        best = None
        salt = 0
        tries = []
        for attempt in range(CITY_RETRIES + 1):
            add_local(b, explicit, run, check=not buildings)
            if buildings:
                add_buildings(b, explicit, run)
            fails = sum(len(c.failures) for c in b.checks)
            T.stage(f"city_try{attempt}", [b.variant, b.stats.get("road_variant"), salt, fails])
            tries.append({"variant": b.variant, "road_variant": b.stats.get("road_variant"),
                          "layout_salt": salt, "failures": fails})
            if best is None or fails < best[0]:
                best = (fails, b)
            if not fails or attempt == CITY_RETRIES:
                break
            what = f"road variant {b.variant}/{b.stats.get('road_variant')}" + (
                f", layout salt {salt}" if salt else "")
            # the local layout drawn again first (the roads are the best ones), then the next
            # road network
            nxt = add_roads(ranked, explicit, run, frozenset(tried)) \
                if salt >= LAYOUT_SALTS else None
            if nxt is not None:
                tried.add((nxt.variant, nxt.stats["road_variant"]))
                salt = 0
                base = _pristine(nxt)
                b = nxt
                again = f"road variant {nxt.variant}/{nxt.stats.get('road_variant')}"
            else:
                salt += 1
                b = _pristine(base)
                b.spec = _salted(base.spec, salt)
                b.stats["layout_salt"] = salt
                again = f"the same roads with the local layout drawn again (salt {salt})"
            b.notes = [f"{what} left {fails} check failures in the full city; built again on "
                       f"{again}"] + b.notes
        best[1].stats["city_tries"] = tries
        return best[1]
    finally:
        run.close()


@dataclass
class _RoadTry:
    variant: int
    sites: list
    site_notes: list[str]
    net: object
    model: CityModel
    checks: list
    stats: dict

    @property
    def fails(self) -> int:
        return sum(len(c.failures) for c in self.checks)


def road_attempt(b: Built, explicit: set[str], k: int) -> _RoadTry:
    """Megasite reserves and road variant k on hydrology variant b, then every check again
    (water, districts and roads)."""
    spec = b.spec
    did = _district_ids(spec)
    sites, site_notes = MS.place_megasites(spec, b.layout.polygons, b.hydro, b.waterways, did)
    T.stage(f"v{b.variant}/megasites", sites)
    opens = [G.from_model_poly(o.polygon) for o in b.model.open_spaces]
    ground = None
    if spec.terrain is not None:
        from . import terrain as TE

        ground = TE.field(spec, assemble(spec, b.hydro, b.layout, b.waterways, explicit, sites))
        if T.on():
            T.stage(f"v{b.variant}/terrain", ground[0].rows())
    net = RD.build_roads(spec, b.hydro, b.layout.polygons, did, b.waterways, sites, opens,
                         variant=k, terrain=ground[0] if ground else None)
    net.terrain = ground
    model = assemble(spec, b.hydro, b.layout, b.waterways, explicit, sites, net)
    T.stage(f"v{b.variant}/roads{k}", [net.nodes, net.segments, net.bridges])
    checks, st = C.run_checks(spec, model, roads=True)
    return _RoadTry(b.variant, sites, site_notes, net, model, checks, st)


def _pristine(b: Built) -> Built:
    """A copy of a city with its roads, to build the later stages on again."""
    out = copy.copy(b)
    out.roads = copy.deepcopy(b.roads)
    out.notes = list(b.notes)
    out.stats = dict(b.stats)
    out.local = out.m3 = None
    return out


def _salted(spec: CitySpec, salt: int) -> CitySpec:
    """The spec with every district seed moved (the local layout drawn again)."""
    return spec.model_copy(update={"districts": [
        d.model_copy(update={"seed": int(d.seed) + 7919 * salt}) for d in spec.districts]})


def _road_job(b: Built, explicit: set[str], k: int, tracing: bool, worker: bool):
    return _collect(worker and tracing, road_attempt, b, explicit, k)


def add_roads(ranked: list[Built], explicit: set[str], run: _Runner | None = None,
              skip: frozenset = frozenset()) -> Built | None:
    """Roads on the best variant (ranked[0]), trying the road variants in order; if none
    passes every check, the same on the next best variants that passed the water and
    district checks. The first attempt that passes wins, else the one with the fewest
    failures (the earliest of those). `skip`: (variant, road variant) pairs already tried
    for the whole city (M7: `build_city` tries the next one when the full city fails)."""
    run = run or _Runner(1)
    cands = [ranked[0]] + [b for b in ranked[1:] if b.passed][:ROAD_CANDIDATES - 1]
    attempts = [(b, k) for b in cands for k in range(len(RD.ROAD_VARIANTS))
                if (b.variant, k) not in skip]
    if not attempts:
        return None
    by_variant = {b.variant: b for b in cands}
    best: _RoadTry | None = None
    for start in range(0, len(attempts), run.workers):
        batch = attempts[start:start + run.workers]
        for t, entries in run.map(_road_job, [(b, explicit, k, T.on()) for b, k in batch]):
            T.extend(entries)
            if best is None or t.fails < best.fails:
                best = t
            if best.fails == 0:
                break
        if best.fails == 0:
            break
    if skip and best.fails:
        return None      # a retry only takes a road network that passes
    # a copy: a later retry starts again from the variant as it was
    b = copy.copy(by_variant[best.variant])
    b.sites, b.roads, b.model, b.checks = best.sites, best.net, best.model, best.checks
    st = best.stats
    st["separation_budget"] = b.stats.get("separation_budget")
    st["road_variant"] = best.net.variant
    b.stats = st
    b.notes = b.notes + best.site_notes + best.net.notes
    return b


def _blocks_job(fn_name: str, job: dict, worker: bool = False):
    from . import blocks as BK

    return getattr(BK, fn_name)(job)


def add_local(b: Built, explicit: set[str], run: _Runner | None = None,
              check: bool = True) -> Built:
    """M2 on the chosen variant and roads: local streets, junctions, sidewalks, crosswalks,
    lanes, walkways, blocks, lots, open space and places; then every check again (unless M3
    follows, which checks everything at its end)."""
    run = run or _Runner(1)
    spec = b.spec
    did = _district_ids(spec)

    def mapper(fn, jobs):
        return run.map(_blocks_job, [(fn.__name__, j) for j in jobs])

    loc = LC.build_local(spec, b, did, mapper)
    if b.roads.terrain is not None:
        from . import terrain as TE

        nat, lv, tst = b.roads.terrain
        gr = TE.grade(spec, loc.segments, loc.nodes, nat, TE.water_union(b.model))
        TE.apply_grade(loc, gr)
        gr.stats["slope_greens"] = TE.steep_lots(loc, gr.finished)
        loc.terrain = {"ground": gr.finished, "stats": {**tst, **gr.stats},
                       "walls": gr.walls, "bores": gr.bores}
        T.stage("terrain/graded", [loc.segments, gr.walls, gr.bores])
    b.local = loc
    b.model = assemble(spec, b.hydro, b.layout, b.waterways, explicit, b.sites, b.roads, loc)
    b.notes = b.notes + loc.notes
    if not check:
        return b
    checks, st = C.run_checks(spec, b.model, roads=True)
    T.stage("checks", [[c.id, c.passed] for c in checks])
    st["separation_budget"] = b.stats.get("separation_budget")
    st["road_variant"] = b.stats.get("road_variant")
    st.setdefault("local", {})["generator"] = loc.info
    b.checks, b.stats = checks, st
    return b


def _buildings_job(fn_name: str, job: dict, worker: bool = False):
    from . import buildings as BL

    return getattr(BL, fn_name)(job)


def add_buildings(b: Built, explicit: set[str], run: _Runner | None = None) -> Built:
    """M3 on the M2 city: buildings, complexes, landmarks, skybridges and megasites; then
    every check again. The water, district, road and street checks do not depend on M3 (the
    walkway graph aside, which M3 extends), so they run on the M2 model while the workers
    build the lots; the walkway graph and the M3 checks run on the final model."""
    from types import SimpleNamespace

    from . import building_checks as BC
    from . import buildout as BO
    from . import elevated as EL
    from . import gameplay as GP
    from . import gameplay_checks as GC
    from . import street_checks as SC
    from . import prop_checks as PC
    from . import props as PR
    from . import transit as TR
    from . import transit_checks as TC

    run = run or _Runner(1)
    spec = b.spec
    early: dict = {}

    def mapper(fn_name, jobs):
        return run.map(_buildings_job, [(fn_name, j) for j in jobs])

    def submit(fn_name, jobs):
        return run.submit(_buildings_job, [(fn_name, j) for j in jobs])

    def side():
        prev = G.CANONICAL[0]
        G.CANONICAL[0] = False
        try:
            early["checks"], early["stats"] = C.run_checks(spec, b.model, roads=True)
        finally:
            G.CANONICAL[0] = prev

    out = BO.build(spec, b, mapper, submit=submit, side=side)
    if "checks" not in early:
        side()
    b.m3 = out
    m = with_rows(b.model, BO.rows(out))
    tg = b.local.terrain if b.local is not None else None
    if tg is not None:
        # M13: buildings seated on the ground, retaining walls, bored tunnels
        from . import terrain as TE

        m = with_rows(m, TE.seat(m, tg["ground"]))
        m = with_rows(m, {"structures": list(m.structures) + TE.wall_rows(tg["walls"])})
    tr = None
    if spec.transit.lines:
        tr = TR.build(spec, m)
        m = with_rows(m, tr.rows)
    # M9: tunnel parts, metro tunnels, pedestrian underpasses (before the columns and props)
    from . import tunnels as TN

    tn = TN.build(spec, m)
    m = with_rows(m, tn.rows)
    if tg is not None:
        m = with_rows(m, {"tunnels": list(m.tunnels) + TE.bore_rows(
            tg["bores"], [s.model_dump(mode="json") for s in m.road_segments],
            b.roads.terrain[0])})
    # M7: columns under the raised road decks (after the transit structures they avoid)
    m = with_rows(m, {"structures": list(m.structures) + EL.road_supports(m)})
    pr = PR.build(spec, m)
    m = with_rows(m, pr.rows)
    if tg is not None:
        rows, dst = TE.dressing(m)
        m = with_rows(m, rows)
        tg["stats"].update(dst)
    # M11: the gameplay layer on the finished city
    gp = GP.build(spec, m)
    m = with_rows(m, gp.rows)
    for key in sorted(gp.rows):
        T.stage(f"gameplay/{key}", gp.rows[key])
    b.model = m
    lms = SimpleNamespace(landmasses={lm.id: G.from_model_poly(lm.polygon)
                                      for lm in m.landmasses})
    bx = BC._B(m)
    from . import elevated_checks as EC
    from . import terrain_checks as TGC
    from . import tunnel_checks as TNC

    late = {c.id: c for c in TNC.run(spec, m) + TGC.run(spec, m)}
    checks = [SC.check_walkway_graph(m, None, lms) if c.id == "walkway_graph" else
              late.get(c.id, c) for c in early["checks"]] + BC.run(spec, m, None, bx) + \
        TC.run(spec, m) + PC.run(spec, m) + GC.run(spec, m)
    with G.canonical():
        checks.append(EC.check_supports(m))
    st = early["stats"]
    st["elevated"] = EC.stats(m)
    st["tunnels"] = TNC.stats(m)
    if m.terrain is not None:
        st["terrain"] = TGC.stats(m)
    if "local" in st:
        st["local"] = SC.stats(spec, m)
    st["buildings"] = BC.stats(spec, m, bx)
    if tr is not None:
        st["transit"] = {**TC.stats(m), "generator": tr.info}
    st["props"] = {**PC.stats(m), "generator": pr.info}
    st["gameplay"] = {**GC.stats(m), "generator": gp.info}
    T.stage("checks_m3", [[c.id, c.passed] for c in checks])
    for key in ("separation_budget", "road_variant"):
        st[key] = b.stats.get(key)
    if "local" in st and b.local is not None:
        st["local"]["generator"] = b.local.info
    # wall-clock timings stay on b.m3.info["seconds"]: the report must not depend on the run
    st.setdefault("buildings", {})["generator"] = {k: v for k, v in out.info.items()
                                                   if k != "seconds"}
    b.checks, b.stats = checks, st
    b.notes = b.notes + out.notes + (tr.notes if tr is not None else []) + tn.notes + \
        pr.notes + gp.notes
    return b


def with_rows(model: CityModel, rows: dict) -> CityModel:
    """The model with these collections replaced by validated rows (the other collections are
    validated already); ids stay unique across the model."""
    from .model import COLLECTIONS

    upd = {k: [r if isinstance(r, COLLECTIONS[k]) else COLLECTIONS[k].model_validate(r)
               for r in v] for k, v in rows.items()}
    out = model.model_copy(update=upd)
    out._unique_ids()
    return out


def write_outputs(b: Built, out_dir: str | Path, dpi: int = 110) -> list[Path]:
    from .preview import render  # matplotlib only here

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = [out / "city_model.json", out / "report.json", out / "report.txt",
             out / "preview_map.png"]
    paths[0].write_text(b.model.to_json() + "\n", encoding="utf-8")
    rep = b.report()
    paths[1].write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths[2].write_text(C.report_text(rep), encoding="utf-8")
    local = bool(b.model.blocks)
    render(b, paths[3], dpi=150 if local else dpi)
    if local:
        from .preview_detail import render as render_detail

        paths.append(out / "preview_detail.png")
        render_detail(b, paths[4], dpi=dpi)
    if b.model.buildings:
        from .preview_massing import render_heights, render_massing

        paths += [out / "preview_heights.png", out / "preview_massing.png"]
        render_heights(b, paths[-2])
        render_massing(b, paths[-1])
    if b.model.props or b.model.plants:
        from .preview_props import render_props

        paths.append(out / "preview_props.png")
        render_props(b, paths[-1])
    if b.model.transit_lines:
        from .preview_transit import render_transit

        paths.append(out / "preview_transit.png")
        render_transit(b, paths[-1])
    if any(s.attrs.get("elevated") for s in b.model.road_segments):
        from .preview_elevated import render_elevated

        paths.append(out / "preview_elevated.png")
        render_elevated(b, paths[-1])
    if b.model.terrain is not None:
        from .preview_terrain import render_terrain

        paths.append(out / "preview_terrain.png")
        render_terrain(b, paths[-1])
    if b.model.tunnels:
        from .preview_tunnels import render_tunnels

        paths.append(out / "preview_tunnels.png")
        render_tunnels(b, paths[-1])
    if b.model.pois or b.model.zones:
        from .preview_gameplay import render_gameplay

        paths.append(out / "preview_gameplay.png")
        render_gameplay(b, paths[-1])
    return paths
