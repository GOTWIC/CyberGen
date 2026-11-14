"""The asks of citygen (and assetgen) (scope 4.1): what lifegen needs that the model does not
record yet, the record it asks for, and what the plan does meanwhile.

Each ask's `status` is read from the model it is given: `met` once the model carries the
record (its field is there), `derived` where lifegen derives a stand-in from what the model
has, `missing` where nothing stands in yet. The milestone named in `needed_by` is the first
that cannot do without it; until then the ask is a note in the plan's report.
"""

from __future__ import annotations

ASKS = (
    {"id": "signal_phases", "of": "citygen", "needed_by": "LG3, LG5",
     "what": "signal phases and timing per signalized junction, with the crosswalks each "
             "phase serves",
     "field": ("junctions", "phases"),
     "record": {"junctions[].phases": "a list of phases: {legs: road segment ids moving, "
                                      "turns: connector lane ids green, crosswalks: crosswalk "
                                      "ids walking, green_s, amber_s, all_red_s}",
                "junctions[].cycle_s": "the cycle's length",
                "junctions[].offset_s": "its offset in a corridor's green wave"},
     "derived": "two phases from the legs' angles (opposite legs together, every crosswalk "
                "across the legs that stop), a 60 s cycle; M18's `signalized` and crosswalk "
                "ids say which junctions",
     "missing": ""},
    {"id": "bus_routes", "of": "citygen", "needed_by": "LG5",
     "what": "bus routes and their stops",
     "field": ("", "bus_routes"),
     "record": {"bus_routes[]": "{id, name, lane_ids in order (a loop or there and back), "
                                "stop_ids: M6's bus stop props in order, headway_min by hour "
                                "band}"},
     "derived": "",
     "missing": "M6's bus stops are there (`prop.bus_stop`, attrs.stop the sidewalk point); "
                "no route joins them. LG5 could route between stops over the avenues itself, "
                "but a route is the city's, as transit lines are"},
    {"id": "turn_restrictions", "of": "citygen", "needed_by": "LG5",
     "what": "turn restrictions where a junction needs them (no left turn across a median, "
             "no U-turns)",
     "field": ("lanes", "restricted"),
     "record": {"lanes[].restricted": "true on a connector lane no vehicle may take"},
     "derived": "every connector lane M2 lays is allowed",
     "missing": ""},
    {"id": "lobby_points", "of": "citygen", "needed_by": "LG3",
     "what": "lobby points behind main doors, where a person going in stops being drawn",
     "field": ("buildings", "lobbies"),
     "record": {"buildings[].lobbies": "[{entrance index, position 2 to 4 m inside, "
                                       "level}]"},
     "derived": "a person goes in at the door's threshold (AG3's door record), 1.5 m inside "
                "along its normal",
     "missing": ""},
    {"id": "piers", "of": "citygen", "needed_by": "LG7",
     "what": "piers for ferries and water taxis",
     "field": ("", "piers"),
     "record": {"piers[]": "{id, quay_id or bank_id, position, yaw, berth length, walkway "
                           "id, water body id, depth at the berth}"},
     "derived": "",
     "missing": "M16's quays and AG7's quay stairs (every 60 m) are there; no berth is named"},
    {"id": "air_corridors", "of": "citygen", "needed_by": "LG7",
     "what": "air corridors where a city wants them (else lifegen draws its own over the "
             "roads)",
     "field": ("", "air_corridors"),
     "record": {"air_corridors[]": "{id, polyline (x, y), floor_m, ceiling_m, kind "
                                   "(traffic, police, spaceport)}"},
     "derived": "LG7 draws layers over the avenues and highways, clear of the towers by "
                "their margins (scope 8)",
     "missing": ""},
    {"id": "doors", "of": "assetgen", "needed_by": "LG3",
     "what": "every door with its walkway (AG3's door records, the exporter's doors graph)",
     "field": ("@assetgen", "doors"),
     "record": {"doors": "AG3: id, kind, walkway id, position, normal, size"},
     "derived": "M3's entrances (position, walkway id) until the build's assets are read",
     "missing": ""},
    {"id": "fleet_kinds", "of": "assetgen", "needed_by": "LG5, LG7",
     "what": "AG18's missing kinds: buses, trucks, motorbikes, bikes, flying cars, drones, "
             "boats (decision 6: designed on the Mac as the cars are)",
     "field": ("@vehicles", "kinds"),
     "record": {"vehicles/cars/<name>.py": "one script a vehicle, a game pack each "
                                           "(vehicles/GAME.md); its kind in the pack"},
     "derived": "cars, taxis, vans and pickups from the 15 packs in the cities",
     "missing": ""},
)


def _has(model: dict, coll: str, fld: str) -> bool:
    if coll == "":
        return bool(model.get(fld))
    rows = model.get(coll) or []
    return any(isinstance(r, dict) and r.get(fld) is not None for r in rows[:5000])


def status(model: dict, assets: dict | None = None) -> list[dict]:
    """Every ask with its state for this model (and, for assetgen's, what the build has:
    `assets` {"doors": bool})."""
    out = []
    for a in ASKS:
        coll, fld = a["field"]
        if coll == "@assetgen":
            met = bool((assets or {}).get(fld))
        elif coll == "@vehicles":
            met = False
        else:
            met = _has(model, coll, fld)
        st = "met" if met else ("derived" if a["derived"] else "missing")
        out.append({"id": a["id"], "of": a["of"], "what": a["what"], "record": a["record"],
                    "status": st,
                    "meanwhile": "" if met else (a["derived"] or a["missing"]),
                    "needed_by": a["needed_by"]})
    return out
