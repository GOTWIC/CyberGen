"""M1a/M1a2/M1b/M2/M3 build: samples, determinism, each check with a failing case, coast forms, river
`at`, water separation, CLI. Road-specific tests are in test_roads.py."""

import copy
import json
import os
import subprocess
import sys

import pytest
import shapely
from shapely import affinity
from shapely.geometry import Point, Polygon, box

from citygen import checks as C
from citygen import geom as G
from citygen import hydro as H
from citygen.build import build_city, build_variant
from citygen.cli import EXIT_INVALID, EXIT_OK, main
from citygen.model import CityModel
from citygen.validate import validate_spec

from conftest import CITIES, ROOT, SMALL, built_sample, write


def _build(data):
    result = validate_spec(data)
    assert result.ok, [str(i) for i in result.errors]
    return build_city(result)


@pytest.fixture(scope="module")
def small_built():
    return _build(copy.deepcopy(SMALL))


def _rerun(spec_data, model: CityModel) -> dict[str, C.Check]:
    spec = validate_spec(spec_data).filled
    checks, _ = C.run_checks(spec, model)
    return {c.id: c for c in checks}


def _mutate(model: CityModel, fn) -> CityModel:
    data = json.loads(model.to_json())
    fn(data)
    return CityModel.model_validate(data)


def _poly(p: Polygon) -> dict:
    return G.to_model_poly(p)


# --- samples -----------------------------------------------------------------------

def test_five_sample_cities():
    assert len(CITIES) == 5, CITIES


@pytest.mark.parametrize("path", CITIES, ids=lambda p: p.parent.name)
def test_sample_city_builds_and_passes(path):
    built, took, _ = built_sample(path)
    failed = [f for c in built.checks for f in c.failures]
    assert not failed, failed
    # M8a: 300 -> 600 s (Delta Megacity and Vesper Bay passed on their
    # 9th and 8th full-city try); M8c: back to 300 s, every sample passes on its first to
    # third try
    assert took < 300, f"{path.parent.name} took {took:.1f} s"
    # Every polygon in the model is valid (also a check; asserted directly here).
    for e in built.model.entities():
        for attr in ("polygon",):
            if getattr(e, attr, None) is not None:
                assert G.from_model_poly(getattr(e, attr)).is_valid, e.id


def test_committed_reports_match(tmp_path):
    """docs/progress/M18/<city>/report.json is committed, passes and matches a fresh
    build."""
    for path in CITIES:
        slug = path.parent.name
        folder = ROOT / "docs" / "progress" / "M18" / slug
        committed = folder / "report.json"
        assert committed.is_file(), committed
        rep = json.loads(committed.read_text())
        assert rep["passed"], slug
        assert (folder / "preview_gameplay.png").is_file()
        assert (folder / "preview_transit.png").is_file()
        built, _, _ = built_sample(path)
        assert rep == json.loads(json.dumps(built.report())), slug


# --- determinism ---------------------------------------------------------------------

def test_same_spec_same_json(small_built):
    again = _build(copy.deepcopy(SMALL))
    assert again.model.to_json() == small_built.model.to_json()


def test_byte_identical_across_processes(tmp_path):
    """Two CLI runs with different hash seeds write byte-identical city_model.json."""
    spec = write(tmp_path, SMALL)
    outs = []
    for k, hs in enumerate(("1", "4242")):
        out = tmp_path / f"out{k}"
        env = {**os.environ, "PYTHONHASHSEED": hs}
        proc = subprocess.run([sys.executable, "-m", "citygen", "build", str(spec), str(out)],
                              cwd=ROOT, env=env, capture_output=True, text=True)
        assert proc.returncode == EXIT_OK, proc.stderr
        outs.append((out / "city_model.json").read_bytes())
    assert outs[0] == outs[1]


def test_seed_changes_city(small_built):
    data = copy.deepcopy(SMALL)
    data["seed"] = 8
    assert _build(data).model.to_json() != small_built.model.to_json()


# --- checks: pass on the small city, fail when broken ----------------------------------

def test_small_city_passes(small_built):
    assert small_built.passed, [f for c in small_built.checks for f in c.failures]
    ids = {c.id for c in small_built.checks}
    assert ids == {"geometry_valid", "waterways_connected", "district_shares", "placement",
                   "water_required", "district_pieces", "island_sizes", "no_slivers",
                   "land_use", "canal_quality", "road_graph", "districts_served",
                   "named_bridges", "bridge_clearance", "road_avoidance", "curve_radius",
                   "segment_length", "road_duplicates",
                   # M2
                   "street_graph", "lane_graph", "walkway_graph", "lot_frontage",
                   "lot_block_sizes", "lot_slivers", "sidewalk_clear_path", "crosswalks",
                   "junction_placement", "junction_angles", "street_duplicates",
                   "open_space_share", "places_built",
                   # M3
                   "building_footprints", "building_clear_zones", "building_overlaps",
                   "building_heights", "building_entrances", "ground_floor_units",
                   "roof_items", "complexes", "skybridges", "landmarks", "megasite_contents",
                   "megasite_heights", "megasite_access",
                   # M21
                   "building_forms", "tower_neighbors",
                   # M6 (no transit lines in the small city, so no M5 checks)
                   "props_keepout", "props_overlap", "tree_clearance", "street_lighting",
                   "park_planting", "boats_afloat",
                   # M7
                   "road_grades", "level_continuity", "deck_clearance", "ramps_land",
                   "road_supports",
                   # M9
                   "tunnel_grades", "tunnel_cover", "tunnel_portals", "tunnel_clash",
                   # M12
                   "stack_ramps", "stack_levels",
                   # M11
                   "poi_reachable_foot", "poi_reachable_car", "poi_places", "territories",
                   "gameplay_fields", "street_density", "parking", "travel_points",
                   "sign_slots",
                   # M13
                   "ground_grades", "cut_fill", "retaining_walls", "building_seats",
                   "water_levels",
                   # M17
                   "road_dead_ends", "road_overlaps", "bridge_clash", "road_building_clash",
                   # M18
                   "ramp_grades", "junction_levels", "crossing_spacing"}


def test_check_geometry_invalid(small_built):
    bowtie = {"exterior": [[0, 0], [100, 100], [100, 0], [0, 100]], "holes": []}
    m = _mutate(small_built.model, lambda d: d["districts"][0].update(polygon=bowtie))
    assert not _rerun(SMALL, m)["geometry_valid"].passed


def test_check_geometry_overlap(small_built):
    p = G.from_model_poly(small_built.model.districts[0].polygon)
    m = _mutate(small_built.model,
                lambda d: d["districts"][0].update(polygon=_poly(p.buffer(80))))
    failures = _rerun(SMALL, m)["geometry_valid"].failures
    assert any("overlap" in f or "covers" in f for f in failures), failures


def test_check_waterway_not_connected(small_built):
    m = small_built.model
    core = next(d for d in m.districts if d.name == "Core")
    inner = G.from_model_poly(core.polygon).buffer(-250).representative_point()
    lonely = box(inner.x - 15, inner.y - 15, inner.x + 15, inner.y + 15)

    def add(d):
        d["waterways"].append({"id": "d01.ww99", "kind": "canal", "district_id": core.id,
                               "polygon": _poly(lonely), "connects_to": None})
    broken = _mutate(m, add)
    failures = _rerun(SMALL, broken)["waterways_connected"].failures
    assert any("d01.ww99" in f for f in failures), failures
    # A declared ornamental basin may float.
    ok = _mutate(m, lambda d: (add(d), d["waterways"][-1].update(ornamental=True)))
    assert _rerun(SMALL, ok)["waterways_connected"].passed


def test_check_shares(small_built):
    m = _mutate(small_built.model,
                lambda d: d["districts"][1]["attrs"].update(area_share_target=0.05))
    failures = _rerun(SMALL, m)["district_shares"].failures
    assert failures and "+" in failures[0]


def test_check_placement_direction():
    data = copy.deepcopy(SMALL)
    built = _build(data)
    data["districts"][3]["placement"] = {"south_of": "Core"}  # Uptown was built to the north
    failures = _rerun(data, built.model)["placement"].failures
    assert any("'Uptown' is not south_of 'Core'" in f for f in failures), failures


def test_check_placement_edge_coast_island(small_built):
    data = copy.deepcopy(SMALL)
    data["districts"][3]["placement"] = {"north_of": "Core", "coast": True, "edge": "south"}
    data["districts"][1]["placement"] = {"west_of": "Core", "on_island": "Test Isle"}
    failures = "\n".join(_rerun(data, small_built.model)["placement"].failures)
    assert "'Uptown' should be on the coast" in failures
    assert "'Uptown' is not at edge 'south'" in failures
    assert "'Harbor' is not on island 'Test Isle'" in failures


def test_check_water_required(small_built):
    m = small_built.model
    a, b = m.districts[0], m.districts[1]
    shared = _mutate(m, lambda d: d["districts"][1].update(landmass_id=a.landmass_id))
    data = copy.deepcopy(SMALL)
    data["water"]["district_separation"] = "water_required"
    failures = _rerun(data, shared)["water_required"].failures
    assert any(b.name in f or a.name in f for f in failures), failures


def test_check_pieces(small_built):
    m = small_built.model
    other = next(lm.id for lm in m.landmasses if lm.id != m.districts[0].landmass_id)
    moved = _mutate(m, lambda d: d["districts"][0].update(landmass_id=other))
    assert not _rerun(SMALL, moved)["district_pieces"].passed


def test_check_island_size(small_built):
    def shrink(d):
        isl = d["islands"][0]
        p = Polygon(isl["polygon"]["exterior"])
        isl["polygon"] = _poly(affinity.scale(p, 0.8, 0.8))
    m = _mutate(small_built.model, shrink)
    failures = _rerun(SMALL, m)["island_sizes"].failures
    assert failures and "Test Isle" in failures[0]


def test_check_slivers(small_built):
    m = small_built.model
    core = next(d for d in m.districts if d.name == "Core")
    p = G.from_model_poly(core.polygon)
    c = p.centroid
    spike = box(c.x, c.y - 6, c.x + 4000, c.y + 6)  # 12 m wide strip
    m2 = _mutate(m, lambda d: next(x for x in d["districts"] if x["name"] == "Core").update(
        polygon=_poly(G.polygonal(p.union(spike.intersection(shapely.box(*m.bounds)))))))
    failures = _rerun(SMALL, m2)["no_slivers"].failures
    assert any("'Core'" in f for f in failures), failures


# --- coast forms ---------------------------------------------------------------------

@pytest.mark.parametrize("form", ["bay", "peninsula", "delta", "archipelago", "crescent",
                                  "straight"])
def test_coast_forms(form):
    data = copy.deepcopy(SMALL)
    data["size_km"] = [3.0, 3.0]
    data["water"] = {"coast": {"form": form, "side": "west", "sea_share": 0.35},
                     "rivers": [{"name": "R", "from": "east",
                                 "to": "bay" if form in ("bay", "crescent") else "sea"}]}
    data["districts"] = [{"name": "A", "archetype": "corporate_core"},
                         {"name": "B", "archetype": "old_town"}]
    spec = validate_spec(data).filled
    canvas = G.canvas_for(spec.size_km)
    h = H.build_hydro(spec, canvas, H.Variant())
    share = h.sea.area / canvas.area
    assert abs(share - 0.35) < 0.03, share
    assert h.sea.centroid.x < -300  # the sea is on the west side
    assert h.sea.is_valid and h.land.is_valid and not h.land.is_empty
    # Smooth enough for a city: no land narrower than the 40 m sliver width.
    assert C.slivers(h.land) == []
    if form == "archipelago":
        assert sum(1 for i in h.islands if i.filler) >= 1


def test_peninsula_has_land_tongue():
    data = copy.deepcopy(SMALL)
    data["water"] = {"coast": {"form": "peninsula", "side": "south", "sea_share": 0.5},
                     "rivers": []}
    spec = validate_spec(data).filled
    canvas = G.canvas_for(spec.size_km)
    h = H.build_hydro(spec, canvas, H.Variant())
    # Land reaches far south through the middle while both southern corners are sea.
    assert h.land.intersects(Point(0, -600))
    assert not h.land.intersects(Point(-1100, -1100))
    assert not h.land.intersects(Point(1100, -1100))


@pytest.mark.parametrize("seed", [9081, 404, 1999])
def test_peninsula_headlands_fan_out(seed):
    """coast.headlands: below the mainland strip the land narrows to a neck, then fans out
    into that many headlands; the sea keeps its share, no cove is left as a closed pond."""
    data = json.loads((ROOT / "docs" / "progress" / "M1a2" / "peninsula_city" /
                       "city_spec.json").read_text())
    data["seed"] = seed
    spec = validate_spec(data).filled
    assert spec.water.coast.headlands == 3
    canvas = G.canvas_for(spec.size_km)
    sea = H.build_sea(spec, canvas, None)
    assert abs(sea.area / canvas.area - 0.55) < 0.002
    assert all(p.distance(canvas.exterior) < 1.0 for p in G.parts(sea))
    land = G.diff(canvas, G.qpoly(sea))
    top = 1800.0 - H.FAN["main"] * 3600.0   # the mainland coast
    lam = top + 1800.0                      # from there to the map's south edge
    neck = land.intersection(box(-1800, top - 0.16 * lam, 1800, top - 0.11 * lam))  # the waist
    lower = land.intersection(box(-1800, -1800, 1800, top - 0.45 * lam))
    assert G.qbounds(neck)[2] - G.qbounds(neck)[0] < 1000.0
    assert len(G.parts(lower)) == 3


# --- rivers ----------------------------------------------------------------------------

def test_river_at_pins_entry_and_mouth():
    data = copy.deepcopy(SMALL)
    data["water"] = {"coast": {"form": "straight", "side": "east", "sea_share": 0.2},
                     "rivers": [{"name": "Pinned", "from": {"edge": "north", "at": 0.25},
                                 "to": {"edge": "south", "at": 0.7}, "meander": 0.3}]}
    spec = validate_spec(data).filled
    canvas = G.canvas_for(spec.size_km)
    h = H.build_hydro(spec, canvas, H.Variant())
    river = next(b for b in h.bodies if b.name == "Pinned")
    x0, y0 = river.centerline.coords[0]
    x1, y1 = river.centerline.coords[-1]
    assert abs(x0 - (-1200 + 0.25 * 2400)) < 1.0 and y0 > 1200
    assert abs(x1 - (-1200 + 0.7 * 2400)) < 1.0 and y1 < -1200
    # Variants never move a pinned end.
    h2 = H.build_hydro(spec, canvas, H.Variant.make(spec, 3))
    r2 = next(b for b in h2.bodies if b.name == "Pinned")
    assert r2.centerline.coords[0] == river.centerline.coords[0]


def test_river_at_spec_round_trip_and_errors():
    data = copy.deepcopy(SMALL)
    data["water"]["rivers"][0]["from"] = {"edge": "north", "at": 0.3}
    r = validate_spec(data)
    assert r.ok and r.filled.water.rivers[0].from_at == 0.3
    from citygen.validate import dump_spec
    again = json.loads(dump_spec(r.filled))
    assert again["water"]["rivers"][0]["from"] == {"edge": "north", "at": 0.3}
    data["water"]["rivers"][0]["from"] = {"edge": "north", "at": 1.5}
    assert any("from.at must be a number from 0 to 1" in str(i)
               for i in validate_spec(data).errors)
    data["water"]["rivers"][0]["from"] = "north"
    data["water"]["rivers"].append({"name": "Trib", "from": "east",
                                    "to": {"edge": "Test River", "at": 0.5}})
    r = validate_spec(data)  # a tributary's to.at runs along its parent
    assert r.ok, [str(i) for i in r.errors]
    assert r.filled.water.rivers[1].to == "Test River" and r.filled.water.rivers[1].to_at == 0.5


def test_tributary_and_delta_branches():
    data = copy.deepcopy(SMALL)
    data["size_km"] = [3.0, 3.0]
    data["water"] = {"coast": {"form": "delta", "side": "south"},
                     "rivers": [{"name": "Main", "from": "north", "to": "sea",
                                 "delta_branches": 2},
                                {"name": "Side", "from": "east", "to": "Main"}]}
    spec = validate_spec(data).filled
    canvas = G.canvas_for(spec.size_km)
    h = H.build_hydro(spec, canvas, H.Variant())
    main = next(b for b in h.bodies if b.name == "Main")
    side = next(b for b in h.bodies if b.name == "Side")
    branches = [b for b in h.bodies if b.kind == "delta_branch"]
    assert side.flows_into == main.id and side.polygon.intersects(main.polygon)
    assert len(branches) == 2 and all(b.polygon.intersects(h.sea) for b in branches)
    # Branches really split the land near the mouth: more landmasses than banks alone.
    assert len(h.landmasses) >= 4


# --- water separation -----------------------------------------------------------------

def test_water_required_adds_channels():
    data = copy.deepcopy(SMALL)
    data["water"]["district_separation"] = "water_required"
    built = _build(data)
    assert built.passed, [f for c in built.checks for f in c.failures]
    seps = [c for c in built.model.channels if c.kind == "separation"]
    assert seps
    for lm in built.model.landmasses:
        assert len(lm.district_ids) <= 1, lm
    for c in seps:
        assert len(c.attrs["separates"]) == 2


def test_separated_by_named_river(small_built):
    data = copy.deepcopy(SMALL)
    data["districts"][1]["placement"]["separated_by"] = "Test River"
    built = _build(data)
    assert built.passed, [f for c in built.checks for f in c.failures]
    data["districts"][4]["placement"]["separated_by"] = "Test River"  # an offshore island
    failures = _rerun(data, small_built.model)["placement"].failures
    assert any("'Test Isle' does not border 'Test River'" in f for f in failures), failures


# --- CLI --------------------------------------------------------------------------------

def test_cli_build_writes_outputs(tmp_path):
    spec = write(tmp_path, SMALL)
    out = tmp_path / "out"
    assert main(["build", str(spec), str(out)]) == EXIT_OK
    for name in ("city_model.json", "preview_map.png", "report.json", "report.txt"):
        assert (out / name).is_file(), name
    rep = json.loads((out / "report.json").read_text())
    assert rep["passed"] and rep["stats"]["landmasses"] >= 3
    assert "district" in (out / "report.txt").read_text()
    CityModel.from_json((out / "city_model.json").read_text())


def test_cli_build_fails_on_failed_check(tmp_path, capsys):
    data = copy.deepcopy(SMALL)
    data["water"]["islands"][0]["area_km2"] = 3.0  # cannot fit in the sea
    spec = write(tmp_path, data)
    out = tmp_path / "out"
    assert main(["build", str(spec), str(out), "--variants", "1"]) == EXIT_INVALID
    assert "island_sizes" in capsys.readouterr().err
    assert json.loads((out / "report.json").read_text())["passed"] is False


def test_variant_zero_is_default():
    spec = validate_spec(copy.deepcopy(SMALL)).filled
    assert build_variant(spec, set(), 0).variant == 0
