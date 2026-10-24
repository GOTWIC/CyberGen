"""Schema validation: good specs pass, bad specs fail with readable, located messages."""

import json

import pytest

from citygen.validate import validate_spec

from conftest import EXAMPLES, ROOT


def errors(data) -> list[str]:
    return [str(i) for i in validate_spec(data).errors]


def assert_error(data, *fragments: str) -> None:
    errs = errors(data)
    assert errs, "expected the spec to be invalid"
    joined = "\n".join(errs)
    for frag in fragments:
        assert frag in joined, f"{frag!r} not in:\n{joined}"


def test_four_examples_exist():
    assert len(EXAMPLES) == 4, [str(p) for p in EXAMPLES]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.parent.name)
def test_examples_valid(path):
    result = validate_spec(json.loads(path.read_text()))
    assert result.ok, "\n".join(str(i) for i in result.errors)


def test_minimal_valid(minimal):
    result = validate_spec(minimal)
    assert result.ok, result.errors


def test_scope_example_parses_but_has_dangling_names():
    """The section 4.2 example is an excerpt: its shape is valid, its references are not."""
    data = json.loads((ROOT / "tests" / "data" / "scope_example.json").read_text())
    result = validate_spec(data)
    assert result.spec is not None  # structure is fine (shorthands included)
    joined = "\n".join(str(i) for i in result.errors)
    assert "'Transit Nexus' is not a district, place or megasite" in joined
    assert "'Midtown' is not a district" in joined
    assert "area_share values sum to 0.340" in joined


def test_unknown_field_suggests(minimal):
    minimal["districts"][0]["grid_angle"] = 45
    assert_error(minimal, 'districts[0] "Core"', "unknown field 'grid_angle'",
                 "did you mean 'grid_angle_deg'")


def test_bad_enum_suggests(minimal):
    minimal["districts"][1]["archetype"] = "industrial_prot"
    assert_error(minimal, 'districts[1] "Harbor".archetype', "'industrial_prot' is not allowed",
                 "did you mean 'industrial_port'")


def test_missing_required(minimal):
    del minimal["districts"][2]["archetype"]
    assert_error(minimal, "missing required field 'archetype'")


def test_ranges(minimal):
    minimal["districts"][0]["grime"] = 1.5
    minimal["districts"][0]["height_m"] = [300, 100]
    assert_error(minimal, "grime", "less than or equal to 1", "min <= max")


def test_transit_altitude_outside_mode(minimal):
    minimal["transit"]["lines"][1]["altitude_m"] = [20, 90]
    assert_error(minimal, "outside the maglev range 15 to 60 m")


def test_through_towers_only_sky_tube(minimal):
    minimal["transit"]["lines"][1]["through_towers"] = True
    assert_error(minimal, "through_towers only applies to sky_tube lines")


def test_unknown_reference_suggests(minimal):
    minimal["transit"]["lines"][0]["route"] = ["Harbour", "Core"]
    assert_error(minimal, 'transit.lines[0] "Line 1".route', "'Harbour' is not",
                 "did you mean 'Harbor'")


def test_contradictory_placement(minimal):
    minimal["districts"][1]["placement"]["north_of"] = "Core"
    assert_error(minimal, "'Core' is in both north_of and south_of")


def test_placement_cycle(minimal):
    minimal["districts"][0]["placement"]["north_of"] = "Uptown"
    assert_error(minimal, "placement relations form a loop on the north-south axis")


def test_self_reference(minimal):
    minimal["districts"][0]["placement"]["west_of"] = "Core"
    assert_error(minimal, "cannot be placed relative to itself")


def test_shares_over_one(minimal):
    for d in minimal["districts"]:
        d["area_share"] = 0.4
    assert_error(minimal, "area_share values sum to 1.600")


def test_shares_leave_no_room(minimal):
    minimal["districts"][0]["area_share"] = 0.8
    assert_error(minimal, "leaving no land for the 2 district(s) without a share")


def test_spaceport_needs_coast_or_edge(minimal):
    minimal["districts"][3]["placement"] = {"coast": False}
    assert_error(minimal, "spaceport must be on the coast or a city edge")


def test_megasite_too_big(minimal):
    minimal["districts"][3]["megasites"] = [{"kind": "spaceport", "area_km2": 5}]
    assert_error(minimal, "megasites need 5.00 km2")


def test_duplicate_names(minimal):
    minimal["districts"][2]["name"] = "core"
    minimal["transit"]["lines"][0]["route"] = ["Harbor", "Core"]
    assert_error(minimal, "name 'core' is already used")


def test_reserved_name(minimal):
    minimal["districts"][2]["name"] = "north_exit"
    assert_error(minimal, "'north_exit' is reserved")


def test_river_errors(minimal):
    minimal["water"]["rivers"] = [
        {"name": "A", "from": "north", "to": "B"},
        {"name": "B", "from": "west", "to": "A"},
        {"name": "C", "from": "east", "to": "east"},
    ]
    assert_error(minimal, "tributary loop", "enters and leaves on the same edge")


def test_island_rules(minimal):
    minimal["water"]["islands"] = [{"name": "Isle", "position": "north", "setting": "mid_river"}]
    assert_error(minimal, "setting 'mid_river' needs 'river'")
    minimal["water"]["islands"] = [{"name": "Isle", "position": "south_offshore"}]
    minimal["districts"][1]["placement"] = {"on_island": "Isle", "coast": False}
    assert_error(minimal, "on_island contradicts coast: false")


def test_bad_json_shapes():
    assert_error([], "Input should be a valid dictionary")
    assert_error({"name": "X", "districts": []}, "districts", "at least 1 item")


def test_warnings_do_not_fail(minimal):
    minimal["transit"]["lines"] = [minimal["transit"]["lines"][0]]  # spaceport loses its maglev
    result = validate_spec(minimal)
    assert result.ok
    assert any("spaceport" in str(w) and "maglev or sky_tube" in str(w) for w in result.warnings)
