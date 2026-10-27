"""Stable entity ids (M10): one canonical renaming pass over a finished city model.

The stages number what they make in build order (`rs00012`, `d03.blk017.lot004`,
`d03.prop.bench.00213`), and they keep using those numbers among themselves (orders, hash
keys, groups). This pass, run once on the finished model, gives every entity an id that comes
from what it is and where it sits, so an entity that did not change keeps its id however much
the build order around it moved:

- a name where the entity has one of its own (rivers, islands, places, megasites, transit
  lines, stations): `rv.great_river`, `d02.pl.freeport_plaza`, `stn.crown_exchange`;
- else its kind and a grid-snapped anchor, the middle of its bounding box on the 1 m grid,
  written as compass offsets from the city center (`e1234n567` is 1234 m east and 567 m north
  of it, `w20s3` west and south): `rs.e1234n567` (road segment), `d03.lot.e512n88`,
  `d03.prop.bench.w41s1210`;
- under its parent where it belongs to one: the building of a lot `d03.lot.e512n88.bld`, a
  road's sidewalks and lanes `rs.e1234n567.swl`, `rs.e1234n567.f0`, a lane's connectors
  `rs.e1234n567.f0.c1`, a junction after its node `jn.e1240n570`; a counter the stage put
  under the parent (`.col009`, `.gr1`) becomes an anchor too, M11's own suffixes (unit
  indices, `.turf1`, `.apt012`) stay;
- district ids (`d01` in spec order), `land`, `sea`, the gameplay fields, factions and tiles
  keep theirs.

Two entities with the same id are told apart by `.2`, `.3`, in the order of their contents
(the entity as JSON with every reference rewritten), so the suffix does not depend on the
build order either. A district regeneration passes the old city's ids (`priors`): an
entity of the same kind and geometry as one of the old city takes its id first, so a held
road's node keeps its id when a new node of the district lands in the same 1 m cell. Every reference is rewritten through `REFS` (the typed id fields of
`model.py`) and through every string in `attrs` that is an old id or starts with one
(`attrs.stop`, `removed_buildings`); a test scans built models for references this misses.
Notes and check failures that name an old id get the new one (`text`).

Ids never use Python's `hash()`, set or dict order of strings, or GEOS output: anchors are
plain IEEE arithmetic on the model's coordinates, ties are broken by sorted JSON.
"""

from __future__ import annotations

import json
import re

ORDINAL = re.compile(r"^([a-z_]*?)(\d+)[a-z]?$")
TOKEN = re.compile(r"[a-z0-9_]+(?:\.[a-z0-9_]+)*")

# id fields of each collection outside `attrs` (paths: `a.b`, `a[]` a list, `a[].b` in a list
# of sub-models); `attrs` is handled as a whole
REFS: dict[str, tuple[str, ...]] = {
    "landmasses": ("district_ids[]",),
    "islands": ("landmass_id",),
    "rivers": ("flows_into",),
    "channels": ("river_id", "flows_into"),
    "waterways": ("district_id", "connects_to"),
    "quays": ("waterway_id",),
    "bridges": ("crosses", "segment_ids[]"),
    "districts": ("landmass_id",),
    "places": ("district_id", "feature_ids[]"),
    "road_segments": ("start", "end", "bridge_ids[]", "district_ids[]", "tunnel_ids[]"),
    "junctions": ("node_id", "crosswalk_ids[]"),
    "crosswalks": ("junction_id", "segment_id"),
    "sidewalks": ("segment_id",),
    "lanes": ("segment_id", "node_id", "successors[]", "adjacent_ids[]"),
    "walkways": ("neighbors[]",),
    "structures": ("supports[]",),
    "tunnels": ("segment_ids[]", "district_ids[]", "portals[].segment_id", "crosses"),
    "transit_lines": ("station_ids[]",),
    "stations": ("line_ids[]", "building_id", "access_ids[]"),
    "megasites": ("district_id", "member_ids[]"),
    "blocks": ("district_id", "frontage_ids[]"),
    "lots": ("block_id", "district_id", "frontage[].segment_id", "frontage_ids[]",
             "merged_group_id"),
    "open_spaces": ("district_id",),
    "properties": ("building_ids[]", "district_id", "lot_ids[]"),
    "buildings": ("lot_id", "property_id", "district_id", "megasite_id",
                  "entrances[].segment_id", "entrances[].walkway_id", "units[].segment_id",
                  "portals[].line_id"),
    "skybridges": ("building_ids[]", "crosses[]", "walkway_ids[]", "property_id"),
    "site_elements": ("megasite_id", "lot_id"),
    "green_areas": ("building_id",),
    "factions": ("home_district_id", "zone_ids[]"),
    "zones": ("district_id", "faction_id", "block_ids[]"),
    "pois": ("district_id", "building_id", "host_id", "entrances[].walkway_id",
             "entrances[].lane_id", "zone_id", "faction_id"),
    "densities": ("segment_id", "district_id"),
    "parking": ("district_id", "building_id", "lot_id", "segment_id",
                "entrances[].walkway_id", "entrances[].lane_id"),
    "travel_points": ("district_id", "access.walkway_id", "access.lane_id", "near_id"),
    "sign_slots": ("building_id", "prop_id", "segment_id"),
}

KEEP = ("land", "seas", "districts", "fields", "tiles", "factions")
# collections whose ids M11 already derives from their parents: only the parent part changes
DERIVED = ("zones", "pois", "densities", "parking", "travel_points", "sign_slots")
# the order the collections are named in: every parent before its children
ORDER = ("land", "seas", "districts", "fields", "tiles", "factions", "landmasses", "islands",
         "rivers", "channels", "waterways", "quays", "megasites", "places", "open_spaces",
         "bridges", "road_nodes", "road_segments", "junctions", "crosswalks", "sidewalks",
         "lanes", "walkways", "tunnels", "transit_lines", "stations", "blocks", "lots",
         "properties", "buildings", "skybridges", "structures", "site_elements",
         "green_areas", "plants", "props") + DERIVED
NAMED = {"islands": "isl", "rivers": "rv", "transit_lines": "tl", "stations": "stn"}


def tok(x: float, y: float) -> str:
    """The 1 m grid cell of a point as compass offsets from the city center."""
    ix, iy = int(_round(x)), int(_round(y))
    return f"{'e' if ix >= 0 else 'w'}{abs(ix)}{'n' if iy >= 0 else 's'}{abs(iy)}"


def _round(v: float) -> float:
    import math

    return math.floor(v + 0.5)


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "x"


def _pts(e: dict) -> list:
    """The points an entity's anchor is taken from: its position, outline or line."""
    for key in ("position", "polygon", "footprint", "polygons", "centerline", "line",
                "path", "masses", "label_at", "bounds", "edge"):
        v = e.get(key)
        if not v:
            continue
        if key == "position" or key == "label_at":
            return [v]
        if key == "bounds":
            return [(v[0], v[1]), (v[2], v[3])]
        if key == "polygons":
            return v[0]["exterior"]
        if key == "masses":
            return v[0]["footprint"]["exterior"]
        if isinstance(v, dict):
            return v["exterior"]
        return v
    return []


def anchor(e: dict) -> str:
    pts = _pts(e)
    if not pts:
        return "e0n0"
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return tok((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


SUFFIX = re.compile(r"^(.*)\.(\d+)$")


def signature(coll: str, e: dict) -> str:
    """An entity's kind and geometry, as a key."""
    return json.dumps([coll, e.get("type"), _pts(e)], separators=(",", ":"))


def priors(data: dict) -> dict[str, list[tuple[str, str]]]:
    """The ids of a model by the id they would have without a collision suffix:
    base -> [(id, signature)]."""
    out: dict[str, list[tuple[str, str]]] = {}
    for c in ORDER:
        for e in data.get(c, []):
            m = SUFFIX.match(e["id"])
            out.setdefault(m.group(1) if m else e["id"], []).append(
                (e["id"], signature(c, e)))
    return out


class Renamer:
    def __init__(self, data: dict, keep: set[str] | frozenset = frozenset(),
                 prior: dict | None = None):
        self.d = data
        self.prior = prior or {}
        self.new: dict[str, str] = {}
        self.old_ids: set[str] = {e["id"] for c in ORDER for e in data.get(c, [])}
        # ids that are stable already (named by an earlier pass): they stay
        self.keep = keep & self.old_ids
        self.new.update((k, k) for k in self.keep)
        self.taken: set[str] = set(self.keep)

    # --- references ---------------------------------------------------------------------

    def ref(self, v):
        """An old id, or a string that starts with one (`sw000008.57`), as it is called now;
        anything else unchanged."""
        if not isinstance(v, str):
            return v
        n = self.new.get(v)
        if n is not None:
            return n
        if "." in v and v[0].isalnum():
            parts = v.split(".")
            for k in range(len(parts) - 1, 0, -1):
                n = self.new.get(".".join(parts[:k]))
                if n is not None:
                    return ".".join([n] + parts[k:])
        return v

    def _attrs(self, a):
        if isinstance(a, dict):
            return {k: self._attrs(v) for k, v in a.items()}
        if isinstance(a, list):
            return [self._attrs(v) for v in a]
        return self.ref(a)

    def rewrite(self, coll: str, e: dict) -> None:
        for path in REFS.get(coll, ()):
            _apply(e, path.split("."), self.ref)
        if e.get("attrs"):
            e["attrs"] = self._attrs(e["attrs"])

    # --- names --------------------------------------------------------------------------

    def derived(self, old: str, anchored: bool, e: dict) -> str:
        """old id with its longest prefix that names an entity (or a group) renamed; with
        `anchored`, a trailing counter (`col009`, `00213`) becomes the entity's anchor."""
        parts = old.split(".")
        base, rest = None, parts
        for k in range(len(parts) - 1, 0, -1):
            n = self.new.get(".".join(parts[:k]))
            if n is not None:
                base, rest = n, parts[k:]
                break
        if anchored:
            m = ORDINAL.match(rest[-1])
            if m:
                rest = rest[:-1] + ([m.group(1)] if m.group(1) else []) + [anchor(e)]
        return ".".join(([base] if base else []) + rest)

    def base(self, coll: str, e: dict) -> str:
        old = e["id"]
        if coll in KEEP:
            return old
        if coll in NAMED and e.get("name"):
            return f"{NAMED[coll]}.{slug(e['name'])}"
        if coll == "channels" and e.get("name"):
            return f"ch.{slug(e['name'])}"
        if coll == "megasites":
            return f"{e['district_id']}.ms.{slug(e['name'])}"
        if coll == "places":
            return f"{e['district_id']}.pl.{slug(e['name'])}"
        if coll == "road_nodes":
            lv = e.get("level") or 0
            return f"rn.{anchor(e)}" + (f".l{lv}" if lv else "")
        if coll == "junctions":
            return "jn." + self.new[e["node_id"]].split(".", 1)[1]
        if coll == "sidewalks":
            return f"{self.new[e['segment_id']]}.sw{'l' if e['side'] == 'left' else 'r'}"
        if coll == "lanes" and e.get("kind", "lane") == "lane":
            return f"{self.new[e['segment_id']]}.{'f' if e['forward'] else 'b'}{e['index']}"
        if coll == "lots":
            return f"{e['district_id']}.lot.{anchor(e)}"
        return self.derived(old, coll not in DERIVED, e)

    def _key(self, e: dict) -> str:
        """An entity's contents with every old id as it is called now (or '?' where its
        new name is not known yet): ties between equal ids sort by it."""
        def fix(v):
            if isinstance(v, dict):
                return {k: fix(x) for k, x in v.items() if k != "id"}
            if isinstance(v, list):
                return [fix(x) for x in v]
            if isinstance(v, str) and v in self.old_ids:
                return self.new.get(v, "?")
            return v
        return json.dumps(fix(e), sort_keys=True, ensure_ascii=False, allow_nan=False)

    def name(self, coll: str, items: list[dict], bases: list[str]) -> None:
        groups: dict[str, list[int]] = {}
        for i, b in enumerate(bases):
            if items[i]["id"] in self.keep:
                continue
            groups.setdefault(b, []).append(i)
        for b in sorted(groups):
            idx = groups[b]
            if len(idx) > 1:
                idx = sorted(idx, key=lambda i: self._key(items[i]))
            if b in self.prior:
                # an entity the old city had (same kind and geometry) keeps its old id
                olds: dict[str, list[str]] = {}
                for nid, sig in self.prior[b]:
                    olds.setdefault(sig, []).append(nid)
                rest = []
                for i in idx:
                    nid = next((x for x in olds.get(signature(coll, items[i]), ())
                                if x not in self.taken), None)
                    if nid is None:
                        rest.append(i)
                    else:
                        self.taken.add(nid)
                        self.new[items[i]["id"]] = nid
                idx = rest
            k = 1
            for i in idx:
                nid = b
                while nid in self.taken:
                    k += 1
                    nid = f"{b}.{k}"
                self.taken.add(nid)
                self.new[items[i]["id"]] = nid

    def groups(self) -> None:
        """Lot groups (`d03.mg01`) and landmarks (`d03.lm01`) are not entities but their
        buildings, properties and structures carry them: named by their district, word and
        the anchor of the lots (else buildings) they are built from."""
        lots: dict[str, list] = {}
        for lt in self.d.get("lots", []):
            g = lt.get("merged_group_id")
            if g:
                lots.setdefault(g, []).extend(lt["polygon"]["exterior"])
        feet: dict[str, list] = {}
        for c in ("buildings", "properties", "structures", "site_elements", "green_areas"):
            for e in self.d.get(c, []):
                parts = e["id"].split(".")
                for k in range(2, len(parts)):
                    g = ".".join(parts[:k])
                    if g in self.old_ids or g in self.new:
                        break
                    if k == 2 and parts[0] in self.new and ORDINAL.match(parts[1]):
                        if c == "buildings":
                            feet.setdefault(g, []).extend(_pts(e))
                        else:
                            feet.setdefault(g, [])
                        break
        out = {}
        for g in sorted(set(lots) | set(feet)):
            pts = lots.get(g) or feet.get(g)
            d, word = g.split(".")[:2]
            word = ORDINAL.match(word).group(1) if ORDINAL.match(word) else word
            out[g] = f"{self.new.get(d, d)}.{word}.{anchor({'line': pts}) if pts else 'e0n0'}"
        taken = set()
        for g in sorted(out):
            nid, k = out[g], 1
            while nid in taken or nid in self.taken:
                k += 1
                nid = f"{out[g]}.{k}"
            taken.add(nid)
            self.new[g] = nid

    def run(self) -> dict[str, str]:
        for coll in ORDER:
            items = self.d.get(coll, [])
            if coll == "properties":
                self.groups()
            if not items:
                continue
            if all(e["id"] in self.keep for e in items):
                continue
            if coll == "lanes":
                lanes = [e for e in items if e.get("kind", "lane") == "lane"]
                self.name(coll, lanes, [self.base(coll, e) for e in lanes])
                conns = [e for e in items if e.get("kind", "lane") != "lane"]
                by_from: dict[str, list[dict]] = {}
                for e in conns:
                    by_from.setdefault(self.new[e["attrs"]["from"]], []).append(e)
                bases = []
                order = []
                for f in sorted(by_from):
                    cs = sorted(by_from[f], key=lambda e: (
                        [self.new.get(s, s) for s in e["successors"]], self._key(e)))
                    for k, e in enumerate(cs):
                        order.append(e)
                        bases.append(f"{f}.c{k + 1}")
                self.name(coll, order, bases)
                continue
            self.name(coll, items, [self.base(coll, e) for e in items])
        for coll in ORDER:
            for e in self.d.get(coll, []):
                self.rewrite(coll, e)
                e["id"] = self.new[e["id"]]
        return self.new


def _apply(obj, path: list[str], fn) -> None:
    key = path[0]
    lst = key.endswith("[]")
    key = key[:-2] if lst else key
    if not isinstance(obj, dict) or obj.get(key) is None:
        return
    v = obj[key]
    if len(path) == 1:
        obj[key] = [fn(x) for x in v] if lst else fn(v)
        return
    for x in (v if lst else [v]):
        _apply(x, path[1:], fn)


def rename_data(data: dict, keep: set[str] | frozenset = frozenset(),
                prior: dict | None = None) -> dict[str, str]:
    """Renames the entities of a model dict in place; returns old id -> new id. Ids in
    `keep` are stable already and stay; `prior` (`priors`) are an older city's."""
    return Renamer(data, keep, prior).run()


def rename(model, keep: set[str] | frozenset = frozenset(), prior: dict | None = None):
    """(the model with stable ids, old id -> new id)."""
    from .model import CityModel

    data = model.model_dump(mode="json")
    mapping = rename_data(data, keep, prior)
    return CityModel.model_validate(data), mapping


def remap(obj, mapping: dict[str, str]):
    """Report data (stats) with old ids as keys or values renamed."""
    if isinstance(obj, dict):
        return {mapping.get(k, k) if isinstance(k, str) else k: remap(v, mapping)
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [remap(v, mapping) for v in obj]
    if isinstance(obj, tuple):
        return tuple(remap(v, mapping) for v in obj)
    if isinstance(obj, str):
        return mapping.get(obj, obj)
    return obj


def text(s: str, mapping: dict[str, str]) -> str:
    """A note or check failure with the old ids it names replaced."""
    return TOKEN.sub(lambda m: mapping.get(m.group(0), m.group(0)), s)
