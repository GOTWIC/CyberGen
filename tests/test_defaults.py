"""Fill-defaults expands a sparse spec from the archetype presets, deterministically."""

import copy

from citygen import presets
from citygen.defaults import fill_defaults
from citygen.spec import CitySpec
from citygen.validate import dump_spec, validate_spec

SPARSE = {"name": "Sparse", "districts": [
    {"name": "Core", "archetype": "corporate_core"},
    {"name": "Docks", "archetype": "industrial_port", "area_share": 0.3},
    {"name": "Old Quarter", "archetype": "old_town",
     "places": [{"name": "Lotus Temple", "kind": "temple_complex"}]},
]}


def filled(data=SPARSE) -> CitySpec:
    result = validate_spec(copy.deepcopy(data))
    assert result.ok, result.errors
    return result.filled


def test_every_optional_is_filled():
    s = filled()
    assert s.seed is not None
    assert s.water.coast is not None and s.water.coast.sea_share is not None
    assert s.highways.exits
    for d in s.districts:
        for attr in ("area_share", "seed", "street_pattern", "grid_angle_deg", "block_size_m",
                     "height_m", "water_separation", "waterways", "complexes", "megasites",
                     "skybridge_density", "grime", "neon", "greenery"):
            assert getattr(d, attr) is not None, (d.name, attr)


def test_preset_values():
    core = filled().district("Core")
    p = presets.ARCHETYPES["corporate_core"]
    assert core.height_m == p.height_m
    assert core.grid_angle_deg == 45
    assert [c.kind for c in core.complexes] == ["twin_towers", "tower_cluster"]
    assert filled().district("Docks").megasites[0].kind == "freight_terminal"


def test_area_shares_sum_to_one_and_keep_explicit():
    s = filled()
    assert abs(sum(d.area_share for d in s.districts) - 1.0) < 1e-9
    assert s.district("Docks").area_share == 0.3
    # The two districts without a share split the remaining 0.7 by archetype weight.
    w_core = presets.ARCHETYPES["corporate_core"].area_weight
    w_old = presets.ARCHETYPES["old_town"].area_weight
    assert abs(s.district("Core").area_share - 0.7 * w_core / (w_core + w_old)) < 1e-3


def test_megasite_kind_place_becomes_megasite():
    old = filled().district("Old Quarter")
    assert [p.name for p in old.places] == []
    assert [(m.kind, m.name) for m in old.megasites] == [("temple_complex", "Lotus Temple")]


def test_explicit_empty_list_means_none():
    data = copy.deepcopy(SPARSE)
    data["districts"][0]["complexes"] = []
    data["districts"][1]["megasites"] = []
    s = filled(data)
    assert s.district("Core").complexes == []
    assert s.district("Docks").megasites == []


def test_water_and_highway_defaults():
    s = filled()
    assert s.water.coast.form == "bay" and s.water.coast.side == "south"
    assert len(s.water.rivers) == 1 and s.water.rivers[0].from_ == "north"
    assert s.water.rivers[0].width_m == presets.RIVER_WIDTH_DEFAULT_M
    assert set(s.highways.exits) == {"north", "east", "west"}


def test_transit_defaults():
    data = copy.deepcopy(SPARSE)
    data["districts"].append({"name": "Hub", "archetype": "transit_hub"})
    data["transit"] = {"lines": [{"mode": "sky_tube", "name": "T1", "route": ["Core", "Hub"]},
                                 {"mode": "sky_tube", "name": "T2", "route": ["Hub", "Docks"]}]}
    s = filled(data)
    assert s.transit.hubs == ["Hub"]
    t1, t2 = s.transit.lines
    assert t1.altitude_m == presets.TRANSIT_MODES["sky_tube"].default_altitude_m
    assert t1.color != t2.color


def test_deterministic_and_idempotent():
    a, b = filled(), filled()
    assert dump_spec(a) == dump_spec(b)
    again = fill_defaults(a)
    assert dump_spec(again) == dump_spec(a)
    # The filled spec is itself a valid spec that fills to the same thing.
    import json
    assert dump_spec(filled(json.loads(dump_spec(a)))) == dump_spec(a)


def test_district_seeds_are_local():
    """Adding a district does not change the other districts' seeds (scope principle 5)."""
    data = copy.deepcopy(SPARSE)
    data["seed"] = 7
    before = {d.name: d.seed for d in filled(data).districts}
    data["districts"].append({"name": "Extra", "archetype": "midtown_mixed"})
    after = {d.name: d.seed for d in filled(data).districts}
    assert all(after[n] == s for n, s in before.items())
