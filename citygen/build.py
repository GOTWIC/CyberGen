"""`citygen build`: spec -> city model (M1a: water, districts, inner waterways), checks, preview.

The free hydrology parameters (where an unpinned river enters, how its course bulges, where a
delta splits) are tried in a few seeded variants; each variant is built and checked, and the
first one that passes every check with (worst share error + share of land without a district)
under 5% wins, else the best one (fewest failures, then that quality figure). Variant 0 uses
the defaults, so the search only matters when the default does not fit.
Same spec + seed = byte-identical `city_model.json`.
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
from . import waterways as W
from .model import CityModel
from .spec import CitySpec
from .validate import Result, dump_spec

MAX_VARIANTS = 12
GOOD_QUALITY = 0.05


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

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def report(self) -> dict:
        return C.report_dict(self.spec, self.checks, self.stats, self.notes, self.variant)


def _district_ids(spec: CitySpec) -> dict[str, str]:
    return {d.name: f"d{i + 1:02d}" for i, d in enumerate(spec.districts)}


def assemble(spec: CitySpec, h: H.Hydro, lay: D.Layout, ww: W.Waterways,
             explicit: set[str]) -> CityModel:
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
                "attrs": {k: v for k, v in b.attrs.items() if k != "coast_target"}}
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
    }
    return CityModel.model_validate(data)


def build_variant(spec: CitySpec, explicit: set[str], index: int) -> Built:
    canvas = G.canvas_for(spec.size_km)
    h = H.build_hydro(spec, canvas, H.Variant.make(spec, index))
    lay = D.layout_districts(spec, h, explicit)
    D.finalize(spec, h, lay)
    did = _district_ids(spec)
    ww = W.build_waterways(spec, h, lay.polygons, did)
    model = assemble(spec, h, lay, ww, explicit)
    checks, st = C.run_checks(spec, model)
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


def build_city(result: Result, max_variants: int = MAX_VARIANTS) -> Built:
    spec = result.filled
    explicit = {d.name for d in result.spec.districts if d.area_share is not None}
    best: Built | None = None
    for index in range(max_variants):
        b = build_variant(spec, explicit, index)
        if best is None or _score(b) < _score(best):
            best = b
        if b.passed and _score(b)[1] <= GOOD_QUALITY:
            break
    return best


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
