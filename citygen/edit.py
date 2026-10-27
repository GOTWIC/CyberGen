"""M10: edit a built city. `citygen build SPEC OUT --district NAME` regenerates one district
of the build in OUT; the build state (`city_state.json`, written by every build) records
what a later regeneration, a lock (`lock.py`) and a rebuild need.

A district regeneration:

1. M1 (water, districts, megasite reserves, primary roads) is built again from the city's
   base spec at the choices its search made (`build.replay`, no search): the same bytes.
2. The stages from the local streets on (M2 to M11) run for the whole city on that M1 with
   the district's new spec entry (its fields from the spec given, else a new seed), with
   the old city's roads held (`streets.Frame`: every segment not inside the district comes
   back as it was, and the district's new streets meet those only at their old nodes) and
   its transit lines held (track and heights; buildings now in a line's way go).
3. The splice: every entity of the district (and of the seam on its border: the nodes
   where its streets meet the held roads, their junctions, crosswalks and connectors, the
   lanes and sidewalks of the roads that end there, and what hangs on those) comes from the
   new build, everything else from the old city, byte for byte. A closure then follows the
   references: a kept entity that names one that is gone, or that the new build changed
   because of the district, comes from the new build too (the seam grows only where the
   district reaches). The gameplay fields keep their old cells outside the district, the
   factions their old zones, new names that clash with old ones get a number.
4. Pins (`overrides.py`) are applied again and every check runs on the result.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import shapely

from . import __version__
from . import geom as G
from . import ids as ID
from .model import COLLECTIONS, CityModel

STATE_FILE = "city_state.json"
STATE_VERSION = 1

# attrs keys that name a live entity (the closure follows them)
ATTR_REFS = ("sidewalk", "junction", "segment", "street", "building", "open_space",
             "skybridge", "station", "walkway", "lot", "roof", "median", "path", "quay",
             "waterway", "place", "from", "split_of", "line_id", "road_id", "zone_id",
             "station_building_id", "block_id", "landmass_id", "megasite")


# --- build state ----------------------------------------------------------------------

def code_version() -> dict:
    """citygen's version and the sha256 of its source files: the generator a build came
    from."""
    root = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(root).as_posix().encode() + b"\0")
        h.update(p.read_bytes() + b"\0")
    return {"citygen": __version__, "code_sha256": h.hexdigest()}


def model_sha(model: CityModel) -> str:
    return hashlib.sha256((model.to_json() + "\n").encode("utf-8")).hexdigest()


def new_state(spec_data: dict, built, overrides: dict | None = None) -> dict:
    from .build import choices

    return {"state_version": STATE_VERSION, **code_version(), "spec": spec_data,
            "choices": choices(built), "edits": [], "overrides": overrides,
            "base_overrides": overrides, "model_sha256": model_sha(built.model)}


def write_state(out_dir, state: dict) -> Path:
    p = Path(out_dir) / STATE_FILE
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def read_state(build_dir) -> dict:
    p = Path(build_dir) / STATE_FILE
    if not p.is_file():
        raise FileNotFoundError(f"{p}: no build state (build the city with this citygen)")
    return json.loads(p.read_text(encoding="utf-8"))


def current_spec(state: dict):
    """(the base spec as a validate.Result, the filled spec with every district edit of the
    state applied)."""
    from .validate import validate_spec

    base = validate_spec(state["spec"])
    if not base.ok:
        raise ValueError("the build state's spec does not validate")
    spec = base.filled
    for e in state.get("edits", []):
        spec = with_district(spec, e["district"], e["entry"])
    return base, spec


def with_district(spec, name: str, entry: dict):
    from .spec import District

    d = District.model_validate(entry)
    return spec.model_copy(update={"districts": [d if x.name == name else x
                                                 for x in spec.districts]})


def entry_of(d) -> dict:
    return d.model_dump(mode="json", by_alias=True, exclude_none=True)


# --- regeneration ---------------------------------------------------------------------

def regenerate(state: dict, old: CityModel, district: str, spec_data: dict | None = None,
               seed: int | None = None, workers: int | None = None,
               entry: dict | None = None):
    """(the built city with the district regenerated, the edit record for the state). The
    district's new spec entry: `entry` as it is (a rebuild), else its entry in `spec_data`,
    else its current one; a new seed when that is unchanged and none is given."""
    from . import build as B
    from . import overrides as OV
    from . import streets as ST
    from .defaults import derive_seed
    from .validate import validate_spec

    base, cur = current_spec(state)
    d_old = cur.district(district)
    if d_old is None:
        raise ValueError(f"no district {district!r} in this city")
    nd = d_old
    if entry is not None:
        nd = with_district(cur, district, entry).district(district)
    elif spec_data is not None:
        res = validate_spec(spec_data)
        if not res.ok:
            raise ValueError("the spec given does not validate")
        nd = res.filled.district(district)
        if nd is None:
            raise ValueError(f"no district {district!r} in the spec given")
    same = entry_of(nd) == entry_of(d_old)
    if seed is None and same and entry is None:
        k = sum(1 for e in state.get("edits", []) if e["district"] == district) + 1
        seed = derive_seed(int(d_old.seed), "regenerate", k)
    if seed is not None:
        nd = nd.model_copy(update={"seed": int(seed)})
    spec = cur.model_copy(update={"districts": [nd if d.name == district else d
                                                for d in cur.districts]})
    dd = next(d for d in old.districts if d.name == district)
    poly = G.from_model_poly(dd.polygon)
    ov = state.get("overrides") or {}
    pins = set(ov.get("pins", []))
    ground = [G.from_model_poly(b.footprint or b.masses[0].footprint) for b in old.buildings
              if b.id in pins and b.district_id == dd.id] + \
        [G.from_model_poly(o.polygon) for o in old.open_spaces
         if o.id in pins and o.district_id == dd.id]
    frame = ST.Frame(old, district, dd.id, poly, {d.name: d.archetype for d in cur.districts},
                     pins=pins, keep_out=G.union(ground) if ground else None)
    held = {ln.name: ln.model_dump(mode="json") for ln in old.transit_lines}
    new = B.replay(base, state["choices"], workers, spec=spec, frame=frame, held_lines=held)
    model, info = splice(old, new.model, dd.id, poly, frame)
    if ov:
        model, notes = OV.apply(model, ov, old=old, district=dd.id)
        info["notes"] += notes
    checks, stats = B.check_all(spec, model)
    out = copy.copy(new)
    out.model, out.checks = model, checks
    stats["regenerated"] = {k: v for k, v in info.items() if k != "notes"}
    out.stats = {**new.stats, **stats}
    out.notes = new.notes + info["notes"]
    edit = {"district": district, "entry": entry_of(nd), "seed": int(nd.seed),
            "overrides": state.get("overrides"), "model_sha256": model_sha(model)}
    return out, edit


# --- the splice -----------------------------------------------------------------------

def _anchor(e: dict):
    pts = ID._pts(e)
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0


class _Owner:
    """Which entities of one model belong to the regenerated district ("x"), to its seam
    ("seam") or to the rest of the city ("out")."""

    def __init__(self, m: dict, did: str, zone, frame, seam_nodes: set):
        self.m, self.did, self.zone, self.frame = m, did, zone, frame
        self.cls: dict[str, str] = {}
        segs = m.get("road_segments", [])
        x_seg = {s["id"] for s in segs if self._inside_row(s)}
        seam_seg = {s["id"] for s in segs if s["id"] not in x_seg and
                    (s["start"] in seam_nodes or s["end"] in seam_nodes)}
        for s in segs:
            self.cls[s["id"]] = "x" if s["id"] in x_seg else \
                "seam" if s["id"] in seam_seg else "out"
        ends: dict[str, set] = {}
        for s in segs:
            for n in (s["start"], s["end"]):
                ends.setdefault(n, set()).add(self.cls[s["id"]] == "x")
        for n in m.get("road_nodes", []):
            c = ends.get(n["id"], {False})
            self.cls[n["id"]] = "seam" if n["id"] in seam_nodes else (
                "x" if c == {True} else "out")
        order = ["districts", "junctions", "crosswalks", "sidewalks", "lanes", "bridges",
                 "blocks", "lots", "open_spaces", "places", "megasites", "waterways",
                 "properties", "buildings", "skybridges", "site_elements", "green_areas",
                 "stations", "walkways", "structures", "transit_lines", "plants", "props",
                 "zones", "pois", "densities", "parking", "travel_points", "sign_slots"]
        for coll in order:
            for e in m.get(coll, []):
                self.cls[e["id"]] = self._of(coll, e)

    def _inside_row(self, s: dict) -> bool:
        from types import SimpleNamespace

        return self.frame.inside_row(SimpleNamespace(id=s["id"], attrs=s["attrs"],
                                                     centerline=s["centerline"]))

    def by(self, i) -> str | None:
        return self.cls.get(i) if isinstance(i, str) else None

    def geo(self, e: dict) -> str:
        a = _anchor(e)
        return "x" if a is not None and self.zone.contains(shapely.points(a)) else "out"

    def _of(self, coll: str, e: dict) -> str:
        did = self.did
        a = e.get("attrs") or {}
        if coll == "districts":
            return "x" if e["id"] == did else "out"
        if coll == "junctions":
            return self.by(e["node_id"]) or "out"
        if coll == "crosswalks":
            return self.by(e["junction_id"]) or "out"
        if coll in ("sidewalks", "densities"):
            return self.by(e["segment_id"]) or "out"
        if coll == "lanes":
            return self.by(e.get("segment_id") or e.get("node_id")) or "out"
        if coll == "bridges":
            ss = [self.by(s) for s in e.get("segment_ids", [])]
            return "x" if a.get("footbridge") and ss and all(c == "x" for c in ss) else \
                "seam" if a.get("footbridge") and "x" in ss else "out"
        if coll == "transit_lines":
            return "seam"
        if coll == "stations":
            return self.geo({"position": e["position"]})
        if e.get("district_id") is not None and coll not in ("megasites", "waterways"):
            return "x" if e["district_id"] == did else "out"
        if coll in ("megasites", "waterways"):
            return "out"   # M1: the same in both builds
        if e["id"].startswith(did + "."):
            return "x"
        for k in ("building_id", "prop_id", "lot_id", "megasite_id"):
            c = self.by(e.get(k))
            if c is not None:
                return c
        for k in ATTR_REFS:
            if k in ("line_id", "station"):
                continue   # transit: by where it stands
            c = self.by(a.get(k))
            if c in ("x", "seam"):
                return c
        if coll in ("walkways", "structures") or e["id"].startswith("city."):
            return self.geo(e)
        return "out"


def _refs(coll: str, e: dict):
    """(path, id) of every live reference of an entity."""
    for path in ID.REFS.get(coll, ()):
        yield from _get(e, path.split("."))
    a = e.get("attrs") or {}
    for k in ATTR_REFS:
        v = a.get(k)
        if isinstance(v, str):
            yield v
        elif isinstance(v, list):
            yield from (x for x in v if isinstance(x, str))
    for k in ("grade_separated_with", "portals"):
        v = a.get(k)
        if isinstance(v, list):
            yield from (x for x in v if isinstance(x, str))


def _get(obj, path):
    key = path[0]
    lst = key.endswith("[]")
    key = key[:-2] if lst else key
    if not isinstance(obj, dict) or obj.get(key) is None:
        return
    v = obj[key]
    if len(path) == 1:
        if lst:
            yield from (x for x in v if isinstance(x, str))
        elif isinstance(v, str):
            yield v
        return
    for x in (v if lst else [v]):
        yield from _get(x, path[1:])


def splice(old: CityModel, new: CityModel, did: str, poly, frame) -> tuple[CityModel, dict]:
    O = old.model_dump(mode="json")
    N = new.model_dump(mode="json")
    zone = G.qpoly(poly.buffer(1.0, join_style="mitre"))
    shapely.prepare(zone)
    # the seam nodes: where the district's streets (old or new) meet a held road
    seam_nodes = set()
    for side in (O, N):
        ends: dict[str, set] = {}
        for s in side["road_segments"]:
            from types import SimpleNamespace
            x = frame.inside_row(SimpleNamespace(id=s["id"], attrs=s["attrs"],
                                              centerline=s["centerline"]))
            for n in (s["start"], s["end"]):
                ends.setdefault(n, set()).add(x)
        seam_nodes |= {n for n, v in ends.items() if v == {True, False}}
    own_o = _Owner(O, did, zone, frame, seam_nodes)
    own_n = _Owner(N, did, zone, frame, seam_nodes)
    io = {c: {e["id"]: e for e in O.get(c, [])} for c in COLLECTIONS}
    inn = {c: {e["id"]: e for e in N.get(c, [])} for c in COLLECTIONS}
    coll_of = {}
    for c in COLLECTIONS:
        for i in io[c]:
            coll_of[i] = c
        for i in inn[c]:
            coll_of.setdefault(i, c)
    # R: the old city outside, the new district and seam
    src: dict[str, str] = {}
    for c in COLLECTIONS:
        if c in ("fields", "factions"):
            for i in io[c]:
                src[i] = "o"
            for i in inn[c]:
                src.setdefault(i, "n")
            continue
        for i, e in io[c].items():
            if own_o.cls.get(i, "out") == "out" and own_n.cls.get(i, "out") == "out":
                src[i] = "o"
        for i, e in inn[c].items():
            if own_n.cls.get(i, "out") != "out" or (i in io[c] and
                                                    own_o.cls.get(i, "out") != "out"):
                src[i] = "n"
    first = {k: v for k, v in src.items()}
    dangling = _close(src, io, inn, coll_of)
    # rows: the old order for the old ones, then the new ones in the new build's order
    out = {k: v for k, v in O.items() if k not in COLLECTIONS}
    for c in COLLECTIONS:
        rows = [e for i, e in io[c].items() if src.get(i) == "o"]
        rows += [e for i, e in inn[c].items() if src.get(i) == "n"]
        out[c] = rows
    for k in ("spec_sha256",):
        out[k] = N.get(k)
    _fields(out, O, N, did, zone)
    _factions(out, io["factions"], inn["factions"])
    renamed = _names(out, src)
    model = CityModel.model_validate(out)
    seam = sorted(i for i, s in src.items() if s == "n" and own_n.cls.get(i) != "x"
                  and own_o.cls.get(i) != "x")
    grown = sorted(i for i in seam if first.get(i) != "n")
    held = sum(1 for s in O["road_segments"] if not own_o.cls.get(s["id"]) == "x"
               and inn["road_segments"].get(s["id"]) == s)
    n_held = sum(1 for s in O["road_segments"] if own_o.cls.get(s["id"]) != "x")
    notes = [f"district {did} regenerated: {held} of {n_held} held road segments came back "
             f"unchanged; {len(seam)} entities outside it changed on its seam "
             f"({len(grown)} through references)"]
    if dangling:
        notes.append(f"{len(dangling)} references of the new district to entities that are "
                     f"not in the city (first: {dangling[0][0]} -> {dangling[0][1]})")
    if renamed:
        notes.append(f"{renamed} new names that an old place had already got a number")
    info = {"district_id": did, "held_segments": n_held, "held_unchanged": held,
            "seam": len(seam), "seam_by_reference": len(grown), "dangling": len(dangling),
            "notes": notes}
    return model, info


def _close(src: dict, io: dict, inn: dict, coll_of: dict) -> list:
    """The closure of the splice (in place): an entity taken from the new build brings the
    entities it names that the new build changed, and the entities that name it (from the
    new build, or dropped where the new build has none); an old entity that names something
    gone comes from the new build too, or goes. Entities the two builds agree on stop it.
    Props and plants also follow their neighbors on the ground (the occupancy grid ties
    them without a reference). Returns the references left dangling."""
    from collections import deque

    def ent(i, side):
        c = coll_of.get(i)
        return None if c is None else (io if side == "o" else inn)[c].get(i)

    def changed(i):
        n, o = ent(i, "n"), ent(i, "o")
        return n is not None and n != o

    rev = {"o": {}, "n": {}}
    for side, idx in (("o", io), ("n", inn)):
        r = rev[side]
        for c, es in idx.items():
            for i, e in es.items():
                for t in _refs(c, e):
                    r.setdefault(t, []).append(i)
    dangling = []
    work = deque(sorted(i for i, v in src.items() if v == "n"))
    gone = deque(sorted(i for c in io for i in io[c] if i not in src))

    def take(i):
        if src.get(i) != "n":
            src[i] = "n"
            work.append(i)

    def old_referrers(i):
        for j in rev["o"].get(i, ()):
            if src.get(j) != "o":
                continue
            if ent(j, "n") is None:
                del src[j]
                gone.append(j)
            elif changed(j):
                take(j)

    rounds = 0
    while (work or gone) and rounds < 2_000_000:
        rounds += 1
        if gone:
            old_referrers(gone.popleft())
            continue
        i = work.popleft()
        if src.get(i) != "n":
            continue
        c = coll_of[i]
        for r in _refs(c, inn[c][i]):
            if r not in coll_of:
                continue
            if r not in src:
                if ent(r, "n") is not None:
                    take(r)
                else:
                    dangling.append((i, r))
            elif src[r] == "o" and changed(r):
                take(r)
        if changed(i):
            for j in rev["n"].get(i, ()):
                if j not in src or (src[j] == "o" and changed(j)):
                    take(j)
            old_referrers(i)
        if not work and not gone:
            _ground_neighbors(src, io, inn, take, gone, changed)
    return dangling


GROUND_M = 4.0     # props and plants this close to a new one follow the new build
CROWN_M = 14.0     # plants this close to a new building do too (crowns fit its facades)


def _ground_neighbors(src, io, inn, take, gone, changed) -> None:
    """Old props and plants next to what the new build changed on the ground."""
    olds = [(c, i) for c in ("props", "plants") for i in io[c] if src.get(i) == "o"]
    if not olds:
        return
    pts = shapely.points(np.array([io[c][i]["position"][:2] for c, i in olds],
                                  dtype=np.float64))
    tree = shapely.STRtree(pts)
    probes, reach = [], []
    for c in ("props", "plants", "buildings"):
        for i, e in inn[c].items():
            if src.get(i) != "n" or not changed(i):
                continue
            if c == "buildings":
                fp = e.get("footprint") or e["masses"][0]["footprint"]
                probes.append(G.from_model_poly(fp))
                reach.append(CROWN_M)
            else:
                probes.append(shapely.points(e["position"][:2]))
                reach.append(GROUND_M)
    if not probes:
        return
    hit = set()
    for g, r in zip(probes, reach):
        hit.update(int(k) for k in tree.query(g, predicate="dwithin", distance=r))
    for k in sorted(hit):
        c, i = olds[k]
        if src.get(i) != "o":
            continue
        if inn[c].get(i) is None:
            del src[i]
            gone.append(i)
        elif changed(i):
            take(i)


def _fields(out: dict, O: dict, N: dict, did: str, zone) -> None:
    """The gameplay rasters: the new values inside the district, the old ones elsewhere."""
    newf = {f["id"]: f for f in N.get("fields", [])}
    rows = []
    for f in O.get("fields", []):
        g = newf.get(f["id"])
        if g is None or (g["nx"], g["ny"], g["cell_m"], g["origin"]) != \
                (f["nx"], f["ny"], f["cell_m"], f["origin"]):
            rows.append(f)
            continue
        nx, ny, cm = f["nx"], f["ny"], f["cell_m"]
        ox, oy = f["origin"]
        xs = ox + (np.arange(nx) + 0.5) * cm
        ys = oy + (np.arange(ny) + 0.5) * cm
        gx, gy = np.meshgrid(xs, ys)
        inside = shapely.contains_xy(zone, gx.ravel(), gy.ravel())
        vals = [g["values"][k] if inside[k] else f["values"][k] for k in range(nx * ny)]
        rows.append({**f, "values": vals})
    out["fields"] = rows


def _factions(out: dict, of: dict, nf: dict) -> None:
    """Factions keep their old zones (in their order) and gain the district's new ones;
    a faction with no zone left goes."""
    zones = {z["id"]: z for z in out.get("zones", [])}
    rows = []
    for fid in list(of) + [k for k in nf if k not in of]:
        base = of.get(fid) or nf[fid]
        ids = [z for z in (of.get(fid, {}).get("zone_ids", [])) if z in zones and
               zones[z].get("faction_id") == fid]
        ids += [z for z in nf.get(fid, {}).get("zone_ids", []) if z in zones and
                z not in ids and zones[z].get("faction_id") == fid]
        if not ids and base["kind"] != "police":
            continue
        rows.append({**base, "zone_ids": ids})
    out["factions"] = rows


def _names(out: dict, src: dict) -> int:
    """A new name that an old place has: the next free number after it."""
    taken = set()
    for c in ("pois", "travel_points"):
        for e in out.get(c, []):
            if src.get(e["id"]) == "o":
                taken.add(e["name"])
    n = 0
    for c in ("pois", "travel_points"):
        for e in out.get(c, []):
            if src.get(e["id"]) != "n":
                continue
            name, k = e["name"], 2
            while name in taken:
                name = f"{e['name']} {k}"
                k += 1
            if name != e["name"]:
                e["name"] = name
                n += 1
            taken.add(name)
    return n
