"""M10: pins and overrides (scope 4.3, the optional overrides): an `overrides.json` beside
the spec (or `--overrides FILE`), read by every build and every district regeneration and
kept in the build state and the lock. Entities are named by their stable ids (`ids.py`).

    {"version": 1,
     "pins": ["d03.lot.e512n88.bld", "d03.os.e600n120", "rs.e1234n567"],
     "edits": [
       {"op": "move", "id": "d03.lot.e512n88.bld", "by": [4.0, -2.5]},
       {"op": "replace", "id": "d03.lot.e512n88.bld", "height_m": 240.0},
       {"op": "replace", "id": "d03.os.e600n120", "kind": "garden", "name": "Jade Garden"},
       {"op": "replace", "id": "rs.e1234n567", "name": "Neon Mile"},
       {"op": "plaza", "id": "d03.lot.e700n90", "name": "Lantern Square"},
       {"op": "remove", "id": "d03.prop.kiosk.e705n92"}]}

- **pins** survive a district regeneration (`edit.py`): a pinned road is held like the
  district's border roads; a pinned building or open space keeps its ground (the new streets
  keep 15 m from it, the new lots leave it out). A pinned building stands on a lot of its
  own, like a traced building (`blocks._frame_lots`), and goes back on it as it was before
  the props and the gameplay layer are made (`buildout.frame_pins`: its units and entrances
  face the nearest road, its entrances join the new walkways); a pinned open space comes
  back after the splice, and new buildings, props and plants on it go.
- **edits** run on the finished city in their order, after every build and regeneration:
  `move` shifts a building (its masses, entrances, units, roof items and what hangs on it:
  green roofs, props, plants, sign slots, points of interest, garages), a prop, a plant, an
  open space or a site element; `replace` sets a building's height (its masses scale to it),
  an open space's kind or name, a road's or a place's name, or any field of an entity with
  `set` (validated with the model); `plaza` turns a lot into a plaza (its buildings and what
  hangs on them go); `remove` takes out a building, prop, plant, sign slot, skybridge, open
  space or site element and what hangs on it. Roads cannot be moved or removed (the lane and
  walkway graphs hang on them): pin them, or regenerate the district.
Every check runs on the edited city.
"""

from __future__ import annotations

import json
from pathlib import Path

import shapely
from shapely.geometry import LineString, Point

from . import geom as G
from .model import COLLECTIONS, CityModel

OVERRIDES_FILE = "overrides.json"
VERSION = 1
OPS = ("move", "replace", "remove", "plaza")
NOT_MOVABLE = ("road_segments", "road_nodes", "lanes", "walkways", "sidewalks", "junctions",
               "crosswalks", "blocks", "lots", "districts", "landmasses", "land", "seas")


class OverrideError(ValueError):
    pass


def load(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate(data)


def validate(data: dict) -> dict:
    if not isinstance(data, dict):
        raise OverrideError("overrides: an object with 'pins' and 'edits'")
    extra = set(data) - {"version", "pins", "edits"}
    if extra:
        raise OverrideError(f"overrides: unknown keys {sorted(extra)}")
    if data.get("version", VERSION) != VERSION:
        raise OverrideError(f"overrides: version {data.get('version')} (this citygen reads "
                            f"{VERSION})")
    pins = data.get("pins", [])
    if not all(isinstance(p, str) for p in pins):
        raise OverrideError("overrides: 'pins' is a list of entity ids")
    for k, e in enumerate(data.get("edits", [])):
        if not isinstance(e, dict) or e.get("op") not in OPS or not isinstance(e.get("id"), str):
            raise OverrideError(f"overrides: edits[{k}] needs 'op' ({', '.join(OPS)}) and 'id'")
        if e["op"] == "move" and not (isinstance(e.get("by"), list) and len(e["by"]) == 2):
            raise OverrideError(f"overrides: edits[{k}] (move) needs 'by': [dx, dy]")
    return {"version": VERSION, "pins": list(pins), "edits": list(data.get("edits", []))}


# --- dependents ---------------------------------------------------------------------

def _hangs_on(d: dict, ids: set[str]) -> dict[str, set[str]]:
    """Per collection, the entities that hang on any of `ids` (a building's green roofs,
    props, plants, sign slots, points of interest and garages; a prop's sign slot)."""
    out: dict[str, set[str]] = {}
    for c in ("green_areas", "props", "plants", "sign_slots", "pois", "parking"):
        for e in d.get(c, []):
            a = e.get("attrs") or {}
            if e.get("building_id") in ids or a.get("building") in ids or \
                    a.get("roof") in ids or e.get("prop_id") in ids or e.get("host_id") in ids:
                out.setdefault(c, set()).add(e["id"])
    if out.get("props"):
        more = _hangs_on(d, out["props"]).get("sign_slots", set())
        out.setdefault("sign_slots", set()).update(more)
    if out.get("pois"):
        more = _hangs_on(d, out["pois"]).get("pois", set())
        out["pois"].update(more)
    return out


def _drop(d: dict, ids: dict[str, set[str]]) -> None:
    gone = set().union(*ids.values()) if ids else set()
    for c, s in ids.items():
        d[c] = [e for e in d.get(c, []) if e["id"] not in s]
    if not gone:
        return
    for p in d.get("properties", []):
        p["building_ids"] = [b for b in p["building_ids"] if b not in gone]
    d["properties"] = [p for p in d.get("properties", []) if p["building_ids"]]
    for m in d.get("megasites", []):
        m["member_ids"] = [x for x in m["member_ids"] if x not in gone]
    bridges = {s["id"] for s in d.get("skybridges", []) if set(s["building_ids"]) & gone}
    d["skybridges"] = [s for s in d.get("skybridges", []) if s["id"] not in bridges]
    # the walkways of what went (a building's door and lobby paths and elevators, a bridge's
    # deck), and the neighbors that named them
    gone |= bridges
    walks = d.get("walkways", [])
    drop = {w["id"] for w in walks if (w.get("attrs") or {}).get("building") in gone or
            (w.get("attrs") or {}).get("skybridge") in gone}
    if drop:
        d["walkways"] = [w for w in walks if w["id"] not in drop]
        for w in d["walkways"]:
            if any(n in drop for n in w.get("neighbors", [])):
                w["neighbors"] = [n for n in w["neighbors"] if n not in drop]


# --- geometry -----------------------------------------------------------------------

def _shift(v, dx: float, dy: float):
    """Every (x, y[, z]) point in a nested structure, shifted."""
    if isinstance(v, (list, tuple)) and v and all(isinstance(x, (int, float)) for x in v) \
            and len(v) in (2, 3):
        p = [G.q(v[0] + dx), G.q(v[1] + dy)] + list(v[2:])
        return p
    if isinstance(v, list):
        return [_shift(x, dx, dy) for x in v]
    if isinstance(v, dict):
        return {k: (_shift(x, dx, dy) if k in GEOM_KEYS or isinstance(x, (dict, list))
                    and k not in NOT_GEOM else x) for k, x in v.items()}
    return v


GEOM_KEYS = ("position", "polygon", "footprint", "exterior", "holes", "line", "edge",
             "entrance", "centerline", "label_at", "polygons", "masses", "entrances",
             "units", "roof_items", "curb")
NOT_GEOM = ("attrs", "style", "size", "scale", "values", "hours", "neighbors", "successors",
            "building_ids", "lot_ids", "member_ids", "zone_ids", "block_ids", "frontage_ids",
            "crosses", "walkway_ids", "line_ids", "access_ids", "station_ids", "portals",
            "frontage")


def _move_entity(e: dict, dx: float, dy: float) -> dict:
    out = {}
    for k, v in e.items():
        if k in GEOM_KEYS:
            out[k] = _shift(v, dx, dy)
        else:
            out[k] = v
    return out


def _scale_height(b: dict, h: float) -> dict:
    """A building at a new height: every mass, roof item and portal scaled in z."""
    old = b.get("height_m") or max(m["z1_m"] for m in b["masses"])
    if old <= 0:
        raise OverrideError(f"{b['id']}: no height to scale")
    f = h / old
    b = dict(b)
    b["masses"] = [{**m, "z0_m": G.q(m["z0_m"] * f), "z1_m": G.q(m["z1_m"] * f)}
                   for m in b["masses"]]
    b["roof_items"] = [{**r, "position": [r["position"][0], r["position"][1],
                                          G.q(r["position"][2] * f)]}
                       for r in b.get("roof_items", [])]
    b["portals"] = [{**p, "z0_m": G.q(p["z0_m"] * f), "z1_m": G.q(p["z1_m"] * f)}
                    for p in b.get("portals", [])]
    b["height_m"] = G.q(h)
    b["floors"] = max(1, int(round(max(m["z1_m"] for m in b["masses"]) /
                                   max(b.get("floor_height_m") or 3.5, 1.0))))
    return b


# --- applying ------------------------------------------------------------------------

def apply(model: CityModel, ov: dict, old: CityModel | None = None,
          district: str | None = None) -> tuple[CityModel, list[str]]:
    """The model with the edits applied (and, after a regeneration of `district`, the pins
    restored from `old`). Returns (model, notes)."""
    ov = validate(ov)
    d = model.model_dump(mode="json")
    notes = []
    if old is not None and district is not None and ov["pins"]:
        notes += _restore_pins(d, old.model_dump(mode="json"), ov["pins"], district)
    for k, e in enumerate(ov["edits"]):
        try:
            notes += _edit(d, e)
        except OverrideError as err:
            notes.append(f"override edits[{k}] skipped: {err}")
    out = CityModel.model_validate(d)
    if out.banks or out.ground_cover:
        # M16: the banks and the ground cover follow the edited buildings, plazas and lots
        from .build import water_ground

        out, _ = water_ground(out)
    return out, notes


def _where(d: dict, i: str) -> tuple[str, int]:
    for c in COLLECTIONS:
        for k, e in enumerate(d.get(c, [])):
            if e["id"] == i:
                return c, k
    raise OverrideError(f"no entity {i!r}")


def _edit(d: dict, e: dict) -> list[str]:
    op, i = e["op"], e["id"]
    c, k = _where(d, i)
    ent = d[c][k]
    if op == "move":
        if c in NOT_MOVABLE:
            raise OverrideError(f"{i}: {c} cannot be moved")
        dx, dy = float(e["by"][0]), float(e["by"][1])
        d[c][k] = _move_entity(ent, dx, dy)
        dep = _hangs_on(d, {i})
        for cc, ids in dep.items():
            d[cc] = [_move_entity(x, dx, dy) if x["id"] in ids else x for x in d[cc]]
        return [f"moved {i} by ({dx:g}, {dy:g}) m"]
    if op == "remove":
        if c in NOT_MOVABLE or c in ("transit_lines", "stations", "structures"):
            raise OverrideError(f"{i}: {c} cannot be removed")
        dep = _hangs_on(d, {i})
        dep.setdefault(c, set()).add(i)
        _drop(d, dep)
        return [f"removed {i} ({sum(len(v) for v in dep.values())} entities)"]
    if op == "plaza":
        if c != "lots":
            raise OverrideError(f"{i}: a plaza replaces a lot")
        blds = {b["id"] for b in d.get("buildings", []) if b.get("lot_id") == i}
        dep = _hangs_on(d, blds)
        dep.setdefault("buildings", set()).update(blds)
        _drop(d, dep)
        d[c] = [x for x in d[c] if x["id"] != i]
        d["open_spaces"] = d.get("open_spaces", []) + [{
            "id": f"{i}.plaza", "type": "open_space.plaza", "kind": "plaza",
            "polygon": ent["polygon"], "z_m": 0.0, "name": e.get("name"),
            "district_id": ent["district_id"],
            "attrs": {"area_m2": ent["area_m2"], "override": "plaza", "was_lot": i}}]
        return [f"lot {i} became a plaza ({len(blds)} buildings removed)"]
    # replace
    new = dict(ent)
    if "set" in e:
        new.update(e["set"])
    if c == "buildings" and "height_m" in e:
        new = _scale_height(new, float(e["height_m"]))
    for key in ("name", "kind"):
        if key in e:
            if key not in ent:
                raise OverrideError(f"{i}: {c} have no {key}")
            if key == "kind" and c == "open_spaces":
                new["type"] = f"open_space.{e[key]}"
            new[key] = e[key]
    if c in ("road_segments",) and set(e) - {"op", "id", "name"}:
        raise OverrideError(f"{i}: a road's name only (its class and width carry the lane "
                            "and walkway graphs)")
    try:
        COLLECTIONS[c].model_validate(new)
    except Exception as err:  # pydantic's message, shortened
        raise OverrideError(f"{i}: {str(err).splitlines()[0]}")
    d[c][k] = new
    return [f"replaced {i} ({', '.join(sorted(set(e) - {'op', 'id'}))})"]


def _restore_pins(d: dict, old: dict, pins: list[str], did: str) -> list[str]:
    """Pinned buildings and open spaces of the regenerated district as they were; new
    buildings, props and plants on their ground go; their entrances join the new walkways."""
    oidx = {e["id"]: (c, e) for c in COLLECTIONS for e in old.get(c, [])}
    have = {e["id"] for c in COLLECTIONS for e in d.get(c, [])}
    notes = []
    for pid in pins:
        if pid not in oidx:
            notes.append(f"pin {pid}: not in the old city")
            continue
        c, e = oidx[pid]
        if c == "road_segments":
            if pid not in have:
                notes.append(f"pin {pid}: the road did not come back")
            continue
        if c not in ("buildings", "open_spaces"):
            continue
        if e.get("district_id") != did:
            continue
        if c == "buildings" and pid in have:
            # put back by the build itself (`buildout.frame_pins`): its green roofs too
            for g in old.get("green_areas", []):
                if g.get("building_id") == pid and g["id"] not in have:
                    d["green_areas"].append(g)
            notes.append(f"pin {pid} kept")
            continue
        foot = G.from_model_poly(e["footprint"] if c == "buildings" and e.get("footprint")
                                 else (e["masses"][0]["footprint"] if c == "buildings"
                                       else e["polygon"]))
        shapely.prepare(foot)
        # what the new build put on its ground
        hit = {b["id"] for b in d.get("buildings", []) if b["id"] != pid and _hits(b, foot)}
        dep = _hangs_on(d, hit)
        dep.setdefault("buildings", set()).update(hit)
        for cc in ("props", "plants"):
            for x in d.get(cc, []):
                if shapely.contains_xy(foot, x["position"][0], x["position"][1]):
                    dep.setdefault(cc, set()).add(x["id"])
        if c == "open_spaces":
            dep.setdefault("open_spaces", set()).update(
                o["id"] for o in d.get("open_spaces", []) if o["id"] != pid and
                G.area(G.inter(G.from_model_poly(o["polygon"]), foot)) > 1.0)
        _drop(d, dep)
        rows = [x for x in d[c] if x["id"] != pid]
        if c == "buildings":
            e = _relink(d, dict(e))
            e["lot_id"] = None
            e["property_id"] = None
            rows.append(e)
            for g in old.get("green_areas", []):
                if g.get("building_id") == pid and g["id"] not in have:
                    d["green_areas"].append(g)
        else:
            rows.append(e)
        d[c] = rows
        notes.append(f"pin {pid} kept ({sum(len(v) for v in dep.values())} new entities on "
                     "its ground removed)")
    return notes


def _hits(b: dict, foot) -> bool:
    fp = b.get("footprint") or b["masses"][0]["footprint"]
    return G.area(G.inter(G.from_model_poly(fp), foot)) > 1.0


def _relink(d: dict, b: dict) -> dict:
    """A kept building's entrances and units on the new streets: the nearest ground walkway
    and road segment."""
    walks = [w for w in d.get("walkways", []) if all(abs(p[2]) < 0.01 for p in w["line"])]
    segs = d.get("road_segments", [])
    wl = [LineString([p[:2] for p in w["line"]]) for w in walks]
    sl = [LineString(s["centerline"]) for s in segs]
    wt = shapely.STRtree(wl) if wl else None
    st = shapely.STRtree(sl) if sl else None

    def nearest(tree, lines, rows, p):
        if tree is None:
            return None, None
        ks = tree.query_nearest(Point(p), all_matches=True).tolist()
        k = min(ks, key=lambda k: (lines[k].distance(Point(p)), rows[k]["id"]))
        return rows[k]["id"], G.q(lines[k].distance(Point(p)))

    ents = []
    for en in b.get("entrances", []):
        wid, dist = nearest(wt, wl, walks, en["position"])
        sid, _ = nearest(st, sl, segs, en["position"])
        ents.append({**en, "walkway_id": wid, "link_m": dist, "segment_id": sid})
    units = []
    for u in b.get("units", []):
        p = u.get("entrance") or u["edge"][0]
        sid, _ = nearest(st, sl, segs, p)
        units.append({**u, "segment_id": sid})
    return {**b, "entrances": ents, "units": units}
