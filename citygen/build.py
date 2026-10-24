"""`citygen build`: spec -> city model (water, districts, inner waterways, megasite reserves,
primary roads and bridges), checks, preview.

The free hydrology parameters (where an unpinned river enters, how its course bulges, where a
delta splits) are tried in a few seeded variants; each variant is built and checked, and the
first one that passes every check with (worst share error + share of land without a district)
under 10% wins, else the best one (fewest failures, then that quality figure). Variant 0 uses
the defaults, so the search only matters when the default does not fit.
Megasite reserves and the primary road network (M1b) are built once, on the chosen variant.
Same spec + seed = byte-identical `city_model.json`, on any machine: the generator uses
deterministic elementary functions (`dmath`) and every stage hands the next one coordinates on
the 0.01 m grid.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from shapely.ops import unary_union

from . import checks as C
from . import districts as D
from . import geom as G
from . import hydro as H
from . import megasites as MS
from . import roads as RD
from . import waterways as W
from .model import CityModel
from .spec import CitySpec
from .validate import Result, dump_spec

MAX_VARIANTS = 20
GOOD_QUALITY = 0.10


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

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def report(self) -> dict:
        return C.report_dict(self.spec, self.checks, self.stats, self.notes, self.variant)


def _district_ids(spec: CitySpec) -> dict[str, str]:
    return {d.name: f"d{i + 1:02d}" for i, d in enumerate(spec.districts)}


def assemble(spec: CitySpec, h: H.Hydro, lay: D.Layout, ww: W.Waterways,
             explicit: set[str], sites: list | None = None,
             roads: RD.RoadNet | None = None) -> CityModel:
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
            a = b["attrs"]
            b["water_class"] = a.pop("water_class")
            b["span_m"] = a.pop("span_m")
            b["ramp_length_m"] = a.pop("ramp_length_m")
            b.pop("road_class", None)
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
    canvas = G.canvas_for(spec.size_km)
    h = H.build_hydro(spec, canvas, H.Variant.make(spec, index))
    lay = D.layout_districts(spec, h, explicit)
    D.finalize(spec, h, lay)
    did = _district_ids(spec)
    ww = W.build_waterways(spec, h, lay.polygons, did)
    model = assemble(spec, h, lay, ww, explicit)
    checks, st = C.run_checks(spec, model, roads=False)
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


def build_city(result: Result, max_variants: int = MAX_VARIANTS, roads: bool = True) -> Built:
    spec = result.filled
    explicit = {d.name for d in result.spec.districts if d.area_share is not None}
    best: Built | None = None
    for index in range(max_variants):
        b = build_variant(spec, explicit, index)
        if best is None or _score(b) < _score(best):
            best = b
        if b.passed and _score(b)[1] <= GOOD_QUALITY:
            break
    if roads:
        add_roads(best, explicit)
    return best


def add_roads(b: Built, explicit: set[str]) -> Built:
    """Megasite reserves and the primary road network on the chosen variant, then every check
    again (water, districts and roads)."""
    spec = b.spec
    did = _district_ids(spec)
    sites, site_notes = MS.place_megasites(spec, b.layout.polygons, b.hydro, b.waterways, did)
    opens = [G.from_model_poly(o.polygon) for o in b.model.open_spaces]
    best = None
    for k in range(len(RD.ROAD_VARIANTS)):
        net = RD.build_roads(spec, b.hydro, b.layout.polygons, did, b.waterways, sites, opens,
                             variant=k)
        model = assemble(spec, b.hydro, b.layout, b.waterways, explicit, sites, net)
        checks, st = C.run_checks(spec, model, roads=True)
        fails = sum(len(c.failures) for c in checks)
        if best is None or fails < best[0]:
            best = (fails, net, model, checks, st)
        if fails == 0:
            break
    _, net, model, checks, st = best
    b.sites, b.roads, b.model, b.checks = sites, net, model, checks
    st["separation_budget"] = b.stats.get("separation_budget")
    st["road_variant"] = net.variant
    b.stats = st
    b.notes = b.notes + site_notes + net.notes
    return b


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
    render(b, paths[3], dpi=dpi)
    return paths
