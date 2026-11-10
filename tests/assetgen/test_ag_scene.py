"""AG16: the city's scene in Unreal as the exporter makes it, counted per tile and for the
city (`assetgen/scene.py`, `asset_budget`'s limits)."""

from assetgen import scene as SC
from citygen import unreal as U


def _man(grouped=True):
    """Two tiles: a blockout object left, a prototype instancer replaced by AG8's entry,
    a building with a front and two parts, two signs, a column; a group of props."""
    actors = [
        {"key": "bld.a", "mesh": "Assets/Buildings/t0/a", "hash": "a", "tile": "t0",
         "category": "building", "type": "tower", "pivot": [1, 1, 0], "yaw_deg": 0.0},
        {"key": "bld.a.front", "mesh": "Assets/Buildings/t0/af", "hash": "af", "tile": "t0",
         "category": "building", "type": "building.front", "pivot": [1, 1, 0],
         "yaw_deg": 0.0},
        {"key": "sign.1", "mesh": "Assets/Signs/t0/s", "hash": "s1", "tile": "t0",
         "category": "prop_sign", "type": "sign_slot.shop_sign", "pivot": [5, 5, 3],
         "yaw_deg": 0.0},
        {"key": "sign.2", "mesh": "Assets/Signs/t0/s", "hash": "s2", "tile": "t0",
         "category": "prop_sign", "type": "sign_slot.shop_sign", "pivot": [9, 5, 3],
         "yaw_deg": 0.0},
        {"key": "col.1", "mesh": "Assets/Streets/t1/c", "hash": "c", "tile": "t1",
         "category": "structure_column", "type": "column", "pivot": [300, 5, 0],
         "yaw_deg": 0.0}]
    base = {"pivot": [1, 1, 0], "yaw_deg": 0.0, "district": "", "tile": "t0"}
    insts = [
        {"key": "bld.a.part.w", "entry": "bld.a", "kind": "part.w", "hash": "p1",
         "mesh": "Assets/BuildingsParts/t0/w", "xforms": [[0, 0, 0, 0]] * 10,
         "category": "building", "type": "part.w", **base},
        {"key": "bld.a.part.f", "entry": "bld.a", "kind": "part.f", "hash": "p2",
         "mesh": "Assets/BuildingsParts/t0/f", "xforms": [[0, 0, 0, 0]] * 20,
         "category": "building", "type": "part.f", **base},
        {"key": "prop.bench.t1.v0", "entry": "prop.bench.t1", "kind": "v0", "hash": "p3",
         "mesh": "Assets/PropsParts/x/v0", "xforms": [[0, 0, 0, 0]] * 3,
         "category": "prop_bench", "type": "v0", **{**base, "tile": "t1"}}]
    s2 = {"actors": actors, "instances": insts, "replaced": ["prop.bench.t1"],
          "lod_chains": [], "packs": [], "underwater": []}
    if grouped:
        s2["groups"] = U.group_actors(actors, insts, {"tiles": [
            {"name": "t0", "bounds": [0, 0, 256, 256]},
            {"name": "t1", "bounds": [256, 0, 512, 256]}]})
    return {"tiles": [{"name": "t0", "bounds": [0, 0, 256, 256],
                       "objects": [{"key": "city.ground.t0", "asset": "g0", "hash": "g"}]},
                      {"name": "t1", "bounds": [256, 0, 512, 256], "objects": []}],
            "instances": [{"key": "prop.bench.t1", "tile": "t1", "count": 3, "hash": "i"}],
            "player_start": {"position": [0, 0, 0]}, "stage2": s2}


def test_scene_counts():
    c = SC.count(_man())
    t0, t1 = c["tiles"]["t0"], c["tiles"]["t1"]
    # t0: the ground object, the building (its front and parts its components) and the
    # tile's sign group; t1: the column and the props' group (the prototype instancer it
    # replaces left out)
    assert t0["actors"] == 3 and t1["actors"] == 2
    # components: ground 1, building's shell, front and 2 parts 4, 2 signs; column 1, props 1
    assert t0["components"] == 7 and t1["components"] == 2
    assert t0["meshes"] == 6          # g0, a, af, w, f and s (one for the two signs)
    assert t0["instances"] == 30 and t1["instances"] == 3
    city = c["city"]
    assert city["grouped"] and city["actors"] == 5 + 4    # (and the player start, the lights)
    assert city["components"] == 9 and city["instances"] == 33
    assert city["root_pages"] <= city["root_pages_max"]


def test_scene_ungrouped_counts_an_actor_per_record():
    c = SC.count(_man(grouped=False))
    assert c["tiles"]["t0"]["actors"] == 1 + 2 + 2 + 2      # ground, bld + front, 2 parts, 2 signs
    assert c["tiles"]["t0"]["components"] == 7
