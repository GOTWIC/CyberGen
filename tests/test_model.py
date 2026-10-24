"""City model schema: types, ids, semantic types and JSON round trip."""

import pytest
from pydantic import ValidationError

from citygen.model import COLLECTIONS, CityModel

SQUARE = {"exterior": [[0, 0], [10, 0], [10, 10], [0, 10]]}


def tiny() -> dict:
    return {
        "name": "Tiny", "seed": 1, "bounds": [-100, -100, 100, 100],
        "districts": [{"id": "d01", "name": "Core", "archetype": "corporate_core",
                       "polygon": SQUARE, "seed": 5}],
        "road_nodes": [{"id": "d01.n001", "position": [0, 0, 0]},
                       {"id": "d01.n002", "position": [50, 0, 0]}],
        "road_segments": [{"id": "d01.road.0001", "type": "road.avenue", "start": "d01.n001",
                           "end": "d01.n002", "centerline": [[0, 0], [50, 0]],
                           "cross_section": {"total_width_m": 30, "lane_width_m": 3.3,
                                             "lanes_forward": 2, "lanes_backward": 2}}],
        "buildings": [{"id": "d01.blk001.lot001.bld", "type": "building.podium_tower",
                       "use": "office",
                       "masses": [{"footprint": SQUARE, "z0_m": 0, "z1_m": 20, "role": "podium"},
                                  {"footprint": SQUARE, "z0_m": 20, "z1_m": 180, "role": "tower"}]}],
        "props": [{"id": "d01.prop.street_light.0001", "type": "prop.street_light",
                   "position": [1, 2, 0]}],
        "tiles": [{"id": "tile.0_0", "ix": 0, "iy": 0, "bounds": [0, 0, 256, 256]}],
    }


def test_round_trip_is_byte_stable():
    m = CityModel.model_validate(tiny())
    text = m.to_json()
    again = CityModel.from_json(text)
    assert again == m
    assert again.to_json() == text


def test_default_type_is_prefix():
    m = CityModel.model_validate(tiny())
    assert m.districts[0].type == "district"
    assert m.road_segments[0].type == "road.avenue"
    assert m.index()["d01.blk001.lot001.bld"].type == "building.podium_tower"


def test_type_prefix_enforced():
    data = tiny()
    data["props"][0]["type"] = "building.street_light"
    with pytest.raises(ValidationError, match="must be 'prop' or start with 'prop.'"):
        CityModel.model_validate(data)


def test_duplicate_ids_rejected():
    data = tiny()
    data["props"][0]["id"] = "d01"
    with pytest.raises(ValidationError, match="duplicate id 'd01'"):
        CityModel.model_validate(data)


def test_id_pattern():
    data = tiny()
    data["districts"][0]["id"] = "D 01"
    with pytest.raises(ValidationError):
        CityModel.model_validate(data)


def test_all_scope_entities_present():
    """Section 6 entity list."""
    expected = {"land", "landmasses", "islands", "seas", "rivers", "channels", "waterways",
                "quays", "bridges", "districts", "places", "road_nodes", "road_segments",
                "junctions", "lanes", "walkways", "structures", "transit_lines", "stations",
                "megasites", "blocks", "lots", "open_spaces", "properties", "buildings",
                "skybridges", "plants", "green_areas", "props", "tiles"}
    assert set(COLLECTIONS) == expected
