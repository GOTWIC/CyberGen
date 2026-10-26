"""M3 driver: buildings, complexes, landmarks, skybridges (stage 11) and the megasite
generators (stage 9) on the lots, open space and reserves of M2. Returns model rows.

Districts are built in worker processes (one job per district; the result does not depend
on the worker count), megasites here. Then the walkway graph is extended: every skybridge
gets its deck, an elevator at each end and a lobby path from the elevator to the building's
main entrance, and that entrance, like the entrances of megasite buildings, a path to the
nearest ground walkway, which is split there. Every building entrance records its nearest
ground walkway (`walkway_id`, `link_m`).
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field

import numpy as np
import shapely
import shapely.ops
from shapely.geometry import LineString, Point

from . import buildings as BL
from . import dmath as M
from . import geom as G
from . import junctions as JN
from . import sites as SI
from . import streets as ST
from . import trace as T

GROUND_WALKS = ("sidewalk", "pedestrian_street", "promenade", "alley", "path", "crossing",
                "crosswalk", "footbridge")
WATER_CLEAR = {"sea": 25.0, "river": 15.0, "canal": 4.0}
HOST_KINDS = ("park", "plaza", "promenade", "beach", "green", "pocket_park")
DOOR_LINK_M = 18.0   # entrances farther than this from a walkway get a path to it


@dataclass
class Out:
    buildings: list = field(default_factory=list)
    properties: list = field(default_factory=list)
    skybridges: list = field(default_factory=list)
    site_elements: list = field(default_factory=list)
    structures: list = field(default_factory=list)
    green_areas: list = field(default_factory=list)
    walkways: list = field(default_factory=list)
    megasites: list = field(default_factory=list)
    site_walks: list = field(default_factory=list)   # (megasite id, (kind, pts, width))
    site_links: list = field(default_factory=list)   # (megasite id, point to join)
    landmasses: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    info: dict = field(default_factory=dict)


def _lot_dict(lt) -> dict:
    return {"id": lt.id, "block_id": lt.block_id, "polygon": G.from_model_poly(lt.polygon),
            "area_m2": lt.area_m2, "merged_group_id": lt.merged_group_id,
            "attrs": dict(lt.attrs),
            "frontage": [{"segment_id": f.segment_id, "road_class": f.road_class,
                          "length_m": f.length_m, "line": [tuple(p) for p in f.line]}
                         for f in lt.frontage]}


def _water(m) -> list:
    out = []
    for r in m.rivers:
        out.append((r.id, G.from_model_poly(r.polygon), WATER_CLEAR["river"]))
    for c in m.channels:
        cls = "sea" if c.kind == "sea_channel" else "river" if c.kind == "delta_branch" \
            else "canal"
        out.append((c.id, G.from_model_poly(c.polygon), WATER_CLEAR[cls]))
    for w in m.waterways:
        cls = "sea" if w.kind == "basin" else "canal"
        out.append((w.id, G.from_model_poly(w.polygon), WATER_CLEAR[cls]))
    for s in m.seas:
        for k, p in enumerate(s.polygons):
            out.append((s.id if k == 0 else f"{s.id}{k}", G.from_model_poly(p),
                        WATER_CLEAR["sea"]))
    return out


def contexts(spec, m) -> list[dict]:
    """One job per district: its lots and what its buildings need to know around them."""
    by_name = {d.name: d for d in spec.districts}
    lots_by: dict = {}
    for lt in m.lots:
        if lt.attrs.get("pinned"):
            continue      # a traced building's lot (pinned_buildings)
        lots_by.setdefault(lt.district_id, []).append(lt)
    cones = [(G.from_model_poly(s.flight_cone), float(s.height_limit_m))
             for s in m.megasites if s.flight_cone is not None and s.height_limit_m]
    water = _water(m)
    wtree = shapely.STRtree([w[1] for w in water]) if water else None
    seg_lines = [LineString(s.centerline) for s in m.road_segments]
    stree = shapely.STRtree(seg_lines)
    jpolys = [G.from_model_poly(j.polygon) for j in m.junctions]
    jtree = shapely.STRtree(jpolys) if jpolys else None
    cwpolys = list(G.snap_many(shapely.buffer(
        np.array([LineString(c.line) for c in m.crosswalks], dtype=object),
        np.array([c.width_m / 2.0 for c in m.crosswalks]), cap_style="flat",
        join_style="mitre"))) if m.crosswalks else []
    cwtree = shapely.STRtree(cwpolys) if cwpolys else None
    # sidewalks too (a sidewalk line can run past its road's end, around a corner)
    swpolys = list(G.snap_many(shapely.buffer(
        np.array([LineString(w.line) for w in m.sidewalks], dtype=object),
        np.array([w.width_m / 2.0 for w in m.sidewalks]), cap_style="flat",
        join_style="mitre"))) if m.sidewalks else []
    swtree = shapely.STRtree(swpolys) if swpolys else None
    opens_by: dict = {}
    bopen_by: dict = {}
    dopen: dict = {}
    for o in m.open_spaces:
        if o.district_id:
            dopen.setdefault(o.district_id, []).append((o.id, G.from_model_poly(o.polygon)))
    for d_id, os_ in dopen.items():
        otree = shapely.STRtree([p for _, p in os_])
        for bk in m.blocks:
            if bk.district_id != d_id:
                continue
            bp = G.qpoly(G.from_model_poly(bk.polygon).buffer(0.5, join_style="mitre"))
            ks = sorted(int(i) for i in otree.query(bp, predicate="contains"))
            if ks:
                bopen_by.setdefault(d_id, {})[bk.id] = [os_[k] for k in ks]
    for o in m.open_spaces:
        if o.district_id and o.kind in HOST_KINDS:
            p = G.from_model_poly(o.polygon)
            if G.area1(p) >= 1500.0:
                opens_by.setdefault(o.district_id, []).append((o.id, o.kind, p))
    jobs = []
    for d in m.districts:
        sd = by_name[d.name]
        poly = G.from_model_poly(d.polygon)
        zone = poly.buffer(80.0, join_style="mitre")
        ks = sorted(int(i) for i in stree.query(zone, predicate="intersects"))
        roads = []
        for k in ks:
            s = m.road_segments[k]
            # (M7: the z profile, so a clearance over it is the road's height where crossed)
            roads.append((s.id, s.road_class, [tuple(p) for p in s.centerline], s.width_m,
                          tuple((float(z.s), float(z.z)) for z in s.z_profile)))
        junctions = [jpolys[int(i)] for i in sorted(jtree.query(zone, predicate="intersects"))
                     ] if jtree is not None else []
        junctions += [cwpolys[int(i)] for i in sorted(cwtree.query(zone, predicate="intersects"))
                      ] if cwtree is not None else []
        junctions += [swpolys[int(i)] for i in sorted(swtree.query(zone, predicate="intersects"))
                      ] if swtree is not None else []
        junctions += [p for _, p in dopen.get(d.id, [])]
        wat = [water[int(i)] for i in sorted(wtree.query(zone, predicate="intersects"))] \
            if wtree is not None else []
        A = G.area1(poly)
        st = ST.style_of(d.archetype)
        lms = [{"kind": lm.kind, "name": lm.name, "height_m": float(lm.height_m)}
               for lm in sd.landmarks]
        cx = BL.Ctx(
            did=d.id, name=d.name, archetype=d.archetype, seed=int(d.seed),
            height=(float(sd.height_m[0]), float(sd.height_m[1])), grime=float(sd.grime),
            neon=float(sd.neon), greenery=float(sd.greenery),
            skybridge_density=float(sd.skybridge_density), polygon=poly,
            focus=G.centroid(poly), radius=math.sqrt(A / math.pi) * 1.1,
            lot_area=st.lot_area,
            cones=[c for c in cones if G.dist(c[0], poly) < 3000.0],
            complexes=tuple(c.kind for c in (sd.complexes or [])), landmarks=lms,
            roads=roads, junctions=junctions, water=wat, opens=opens_by.get(d.id, []),
            block_opens=bopen_by.get(d.id, {}))
        lots = sorted(lots_by.get(d.id, []), key=lambda lt: lt.id)
        jobs.append({"ctx": cx, "lots": [_lot_dict(lt) for lt in lots]})
    return jobs


CHUNK_LOTS = 300


def build(spec, b, mapper=None, submit=None, side=None) -> Out:
    """M3 rows. `submit` starts jobs without waiting (the lot chunks); `side` is work for
    this process meanwhile (the build runs it once)."""
    with G.canonical():
        return _build(spec, b, mapper, submit, side)


def _run(mapper, fn_name: str, jobs: list) -> list:
    if mapper is None:
        return [getattr(BL, fn_name)(j) for j in jobs]
    return mapper(fn_name, jobs)


def _build(spec, b, mapper=None, submit=None, side=None) -> Out:
    """Three rounds of jobs: landmarks and complexes per district, buildings on the other lots
    in chunks, then skybridges and model rows per district."""
    import time

    tick = [time.perf_counter()]
    secs: dict = {}

    def lap(name):
        now = time.perf_counter()
        secs[name] = round(now - tick[0], 2)
        tick[0] = now

    m = b.model
    jobs = contexts(spec, m)
    lap("contexts")
    ra = _run(mapper, "phase_a", jobs)
    lap("phase_a")
    chunks, owner = [], []
    for j, (job, r) in enumerate(zip(jobs, ra)):
        cx = job["ctx"]
        cx.rings = r["rings"]
        cx.focus = r["focus"]
        idx = list(enumerate(job["lots"]))
        rtree = shapely.STRtree([LineString(x[2]) for x in cx.roads]) if cx.roads else None
        jtree = shapely.STRtree(cx.junctions) if cx.junctions else None
        used = set(r["used"])
        for s0 in range(0, len(idx), CHUNK_LOTS):
            part = [(k, lot) for k, lot in idx[s0:s0 + CHUNK_LOTS] if lot["id"] not in used]
            if not part:
                continue
            area = shapely.box(*shapely.total_bounds(
                np.array([lot["polygon"] for _, lot in part], dtype=object))).buffer(60.0)
            near_r = sorted(int(i) for i in rtree.query(area)) if rtree is not None else []
            near_j = sorted(int(i) for i in jtree.query(area)) if jtree is not None else []
            ccx = dataclasses.replace(cx, roads=[cx.roads[i] for i in near_r],
                                      junctions=[cx.junctions[i] for i in near_j], water=[],
                                      opens=[], block_opens={}, notes=[])
            chunks.append({"ctx": ccx, "lots": part, "used": []})
            owner.append(j)
    if submit is not None:
        wait = submit("phase_b", chunks)
        if side is not None:
            side()
            lap("side")
        rb = wait()
    else:
        rb = _run(mapper, "phase_b", chunks)
    lap("phase_b")
    secs["phase_b_cpu"] = round(sum(r.get("seconds", 0.0) for r in rb), 2)
    secs["phase_b_max"] = round(max((r.get("seconds", 0.0) for r in rb), default=0.0), 2)
    out = Out()
    sky = [list(r["sky"]) for r in ra]
    trace = [list(r["trace"]) for r in ra]
    parts = [[r] for r in ra]
    for j, r in zip(owner, rb):
        sky[j] += r["sky"]
        trace[j] += r["trace"]
        parts[j].append(r)
    for job in jobs:
        job["ctx"].notes = []
    rc = _run(mapper, "phase_c", [{"ctx": job["ctx"], "sky": sk, "forced": r["forced"]}
                                  for job, sk, r in zip(jobs, sky, ra)])
    lap("phase_c")
    for j, job in enumerate(jobs):
        T.stage(f"buildings/{job['ctx'].did}",
                sorted(trace[j], key=lambda t: t[0]) + rc[j]["trace"])
        for r in parts[j]:
            out.notes += r["notes"]
            for key in ("buildings", "properties", "site_elements", "structures",
                        "green_areas"):
                getattr(out, key).extend(r[key])
        out.notes += rc[j]["notes"]
        out.skybridges.extend(rc[j]["skybridges"])
    T.stage("buildings", [[x.id, x.height_m] for x in out.buildings])
    site = Out()
    out.megasites = SI.build_sites(spec, m, site)
    srows = BL.to_rows({"buildings": site.buildings, "properties": site.properties,
                        "elements": site.site_elements, "structures": site.structures}, None)
    from .model import COLLECTIONS

    for key in ("buildings", "properties", "site_elements", "structures"):
        getattr(out, key).extend(COLLECTIONS[key].model_validate(r) for r in srows[key])
    out.site_walks, out.site_links = site.site_walks, site.site_links
    out.notes += site.notes
    lap("megasites")
    T.stage("megasites_m3", [[x["id"], len(x["member_ids"])] for x in out.megasites])
    pinned_buildings(spec, b, out)
    walks = [w.model_dump(mode="python") for w in m.walkways]
    out.landmasses = list(b.hydro.landmasses)
    out.walkways = link_entrances(out, walks)
    lap("walkways")
    out.info["seconds"] = secs
    T.stage("walkways_m3", [[w["id"], w["kind"], w["neighbors"]] for w in out.walkways])
    out.notes = JN_dedupe(out.notes)
    return out


PIN_FLOOR_M = 4.0               # floor height of a traced building


def _pin_height(pb, focus, lo: float, hi: float) -> float:
    """A traced building's height: its label, else the legacy pipeline's rule (tallest near
    the district's landmark, by footprint size, 20% either way by a hash of its id), within
    the district's range, in 5 m steps."""
    if pb.height_m:
        return G.q(pb.height_m)
    from .props import _u

    c = pb.footprint.centroid
    d = M.hypot(c.x - focus[0], c.y - focus[1])
    size = min(1.4, max(0.6, math.sqrt(G.area1(pb.footprint)) / 32.0))
    h = (45.0 + 230.0 * M.exp(-d / 330.0)) * size * (0.8 + 0.4 * _u("pin", pb.id))
    return G.q(round(min(max(h, lo), hi) / 5.0) * 5.0)


def pinned_buildings(spec, b, out: Out) -> None:
    """The traced buildings of every pinned island, as drawn: one prism each, its height from
    the label (or `_pin_height`), its main entrance on the facade nearest a ground walkway."""
    from . import pinned as PN
    from .model import COLLECTIONS

    pins = PN.placed_islands(spec, b.hydro)
    if not pins:
        return
    m = b.model
    did_of = {d.name: d.id for d in m.districts}
    lot_of = {(lt.district_id, lt.attrs["pinned"]): lt.id for lt in m.lots
              if lt.attrs.get("pinned")}
    ws = [LineString([p[:2] for p in w.line]) for w in m.walkways
          if w.kind in GROUND_WALKS and all(abs(p[2]) < 1e-9 for p in w.line)]
    wtree = shapely.STRtree(ws) if ws else None
    for name in sorted(pins):
        pin, dist = pins[name]
        out.notes += [f"{name}: {w}" for w in pin.warnings]
        did = did_of.get(dist)
        d = spec.district(dist) if dist else None
        lo, hi = d.height_m if d is not None else (20.0, 320.0)
        marks = [x for x in pin.buildings if x.kind == "landmark"]
        fc = (marks[0].footprint if marks else pin.land).centroid
        for pb in pin.buildings:
            foot = pb.footprint
            h = _pin_height(pb, (fc.x, fc.y), lo, hi)
            mark = pb.kind == "landmark"
            ents = []
            if wtree is not None:
                # the nearest walkway, ties to the lowest index (never GEOS's order)
                near = sorted(int(i) for i in wtree.query(foot, predicate="dwithin",
                                                          distance=2000.0))
                if near:
                    k = min(near, key=lambda i: (G.dist(foot, ws[i]), i))
                    q = shapely.ops.nearest_points(foot.exterior, ws[k])[0]
                    ents.append({"position": G.qpoint((q.x, q.y)), "kind": "main"})
            row = {"id": f"{did or 'pin'}.pin.{pb.id}", "lot_id": lot_of.get((did, pb.id)),
                   "type": "building.landmark.traced" if mark else "building.traced",
                   "district_id": did, "use": "mixed" if mark else "office",
                   "floor_height_m": PIN_FLOOR_M, "floors": max(1, int(h / PIN_FLOOR_M + 0.5)),
                   "height_m": h, "footprint": G.to_model_poly(foot),
                   "masses": [{"footprint": G.to_model_poly(foot), "z0_m": 0.0, "z1_m": h,
                               "role": "tower", "shape": "prism"}],
                   "entrances": ents, "landmark": mark,
                   "style": {"grime": 0.1, "neon": 0.4, "era": "corporate_glass"},
                   "attrs": {"pinned": {"island": name, "source": pin.source, "id": pb.id,
                                        "height": "label" if pb.height_m else "auto"}}}
            out.buildings.append(COLLECTIONS["buildings"].model_validate(row))
    out.notes.append(f"{sum(len(p.buildings) for p, _ in pins.values())} traced buildings "
                     "placed as drawn")


def JN_dedupe(notes):
    n: dict = {}
    for t in notes:
        n[t] = n.get(t, 0) + 1
    return [t if k == 1 else f"{t} ({k} times)" for t, k in n.items()]


# ---------------------------------------------------------------------------
# Walkway graph: entrances, skybridges, megasite paths
# ---------------------------------------------------------------------------

def _ground(walks) -> list[int]:
    return [i for i, w in enumerate(walks) if w["kind"] in GROUND_WALKS and
            all(abs(p[2]) < 1e-9 for p in w["line"])]


def link_entrances(out: Out, walks: list) -> list:
    """Every entrance records its nearest ground walkway; skybridges, megasite buildings and
    site paths join the walkway graph."""
    gi = _ground(walks)
    lines = [LineString([p[:2] for p in walks[i]["line"]]) for i in gi]
    tree = shapely.STRtree(lines)
    ents = []
    for rec in out.buildings:
        for e in rec.entrances:
            ents.append((rec, e))
    line_of: dict = {}
    land_of = _landmass_index(out.landmasses, [l.coords[0] for l in lines])
    if ents:
        pts = shapely.points(np.array([e.position for _, e in ents], dtype=np.float64))
        ent_land = _landmass_index(out.landmasses, [e.position for _, e in ents])
        for k, (rec, e) in enumerate(ents):
            best = _nearest_on(tree, lines, walks, gi, land_of, pts[k], ent_land[k])
            e.walkway_id = walks[gi[best]]["id"]
            e.link_m = G.q(G.dist(lines[best], pts[k]))
            line_of[id(e)] = best
    # graph links: skybridge buildings, megasite buildings and site paths
    splits: dict = {}
    new: list = []
    by_id = {r.id: r for r in out.buildings}
    linked: set = set()

    def main_entrance(rec):
        return next((x for x in rec.entrances if x.kind in ("main", "gate")),
                    rec.entrances[0] if rec.entrances else None)

    def door(rec):
        if rec.id in linked:
            return
        e = main_entrance(rec)
        if e is None:
            return
        foot = _foot(lines, walks, gi, line_of[id(e)], e.position)
        splits.setdefault(line_of[id(e)], []).append(foot)
        new.append(("path", [tuple(e.position), foot], 2.0, 0.0,
                    {"building": rec.id, "door": True}))
        linked.add(rec.id)

    for sb in out.skybridges:
        a, bb = sb["line"]
        z = sb["z_m"]
        ids = []
        new.append(("skybridge", [a, bb], sb["width_m"], z, {"skybridge": sb["id"]}))
        ids.append(len(new) - 1)
        for bid, p in zip(sb["building_ids"], (a, bb)):
            rec = by_id[bid]
            new.append(("elevator", [p, p], 2.0, (0.0, z), {"building": bid,
                                                            "skybridge": sb["id"]}))
            ids.append(len(new) - 1)
            e = main_entrance(rec)
            if e is not None and tuple(e.position) != tuple(p):
                new.append(("path", [p, tuple(e.position)], 2.0, 0.0,
                            {"building": bid, "lobby": True}))
            door(rec)
        sb["_walk"] = ids
    for rec in out.buildings:
        e = main_entrance(rec)
        if rec.megasite_id or rec.landmark or (e is not None and e.link_m > DOOR_LINK_M):
            door(rec)   # (a far entrance on a big lot gets a path, like a driveway)
    for sid, (kind, pts, width) in out.site_walks:
        new.append((kind, [tuple(p) for p in pts], width, 0.0, {"megasite": sid}))
    link_land = _landmass_index(out.landmasses, [p for _, p in out.site_links])
    for (sid, p), lm in zip(out.site_links, link_land):
        best = _nearest_on(tree, lines, walks, gi, land_of, Point(p), lm)
        foot = _foot(lines, walks, gi, best, p)
        splits.setdefault(best, []).append(foot)
        if foot != tuple(p):
            new.append(("path", [tuple(p), foot], 4.0, 0.0, {"megasite": sid, "gate": True}))
    walks = _split(walks, gi, lines, splits)
    n0 = len(walks)
    k = max((int(w["id"][2:]) for w in walks), default=0)
    first = k + 1
    for i, (kind, pts, width, z, attrs) in enumerate(new):
        k += 1
        if kind == "elevator":
            line = [(pts[0][0], pts[0][1], z[0]), (pts[0][0], pts[0][1], z[1])]
        else:
            line = [(p[0], p[1], z) for p in pts]
        walks.append({"id": f"wk{k:06d}", "type": "walkway", "kind": kind, "line": line,
                      "width_m": width, "neighbors": [], "attrs": attrs})
    for sb in out.skybridges:
        sb["walkway_ids"] = [f"wk{first + i:06d}" for i in sb.pop("_walk")]
    out.skybridges.sort(key=lambda s_: s_["id"])
    _neighbors(walks)
    out.info["walkways_added"] = len(walks) - n0 + sum(len(v) for v in splits.values())
    return walks


def _landmass_index(landmasses, pts) -> list:
    """Index of the landmass each point lies on (or within 2 m of), -1 for none."""
    out = [-1] * len(pts)
    if not pts:
        return out
    arr = shapely.points(np.array([p[:2] for p in pts], dtype=np.float64))
    for k, lm in enumerate(landmasses):
        zone = G.qpoly(lm.buffer(2.0, join_style="mitre"))
        shapely.prepare(zone)
        for i in np.nonzero(shapely.contains(zone, arr))[0].tolist():
            if out[i] < 0:
                out[i] = k
    return out


def _nearest_on(tree, lines, walks, gi, land_of, pt, land: int) -> int:
    """The nearest ground walkway to pt on the same landmass (any, when pt is on none);
    ties by walkway id."""
    hits = tree.query_nearest(pt, all_matches=True).tolist()
    if land < 0 or any(land_of[h] == land for h in hits):
        cand = [h for h in hits if land < 0 or land_of[h] == land]
    else:
        cand = []
        for r in (60.0, 200.0, 600.0, 2000.0):
            ks = [int(i) for i in tree.query(pt, predicate="dwithin", distance=r)]
            cand = [h for h in ks if land_of[h] == land]
            if cand:
                break
        cand = cand or hits
    return min(cand, key=lambda h: (G.dist(lines[h], pt), walks[gi[h]]["id"]))


def _foot(lines, walks, gi, k: int, p) -> tuple:
    """Where a path from p meets ground walkway k: the nearest point, or the walkway's end
    when it is that close to one (walkways are only split away from their ends)."""
    line = lines[k]
    d = line.project(Point(p))
    pts = walks[gi[k]]["line"]
    if d <= 0.05:
        return (pts[0][0], pts[0][1])
    if d >= line.length - 0.05:
        return (pts[-1][0], pts[-1][1])
    return G.qpoint(line.interpolate(d))


def _split(walks, gi, lines, splits) -> list:
    """Ground walkways split at the door feet (the first piece keeps the id; the others get
    new ids at the end)."""
    if not splits:
        return walks
    walks = list(walks)
    k = max(int(w["id"][2:]) for w in walks)
    extra = []
    for li in sorted(splits):
        w = walks[gi[li]]
        line = lines[li]
        ds = sorted({round(line.project(Point(p)), 6) for p in splits[li]})
        L = line.length
        ds = [d for d in ds if 0.05 < d < L - 0.05]
        z = w["line"][0][2]
        pts2 = [tuple(p[:2]) for p in w["line"]]
        if not ds:
            continue
        pieces = _cut(pts2, ds, splits[li], line)
        w = dict(w)
        w["line"] = [(x, y, z) for x, y in pieces[0]]
        walks[gi[li]] = w
        for pc in pieces[1:]:
            k += 1
            extra.append({**{kk: vv for kk, vv in w.items() if kk != "line"},
                          "id": f"wk{k:06d}", "line": [(x, y, z) for x, y in pc],
                          "attrs": {**w.get("attrs", {}), "split_of": w["id"]}})
    return walks + extra


def _cut(pts, ds, feet, line) -> list:
    """Polyline pts cut at distances ds; the cut points are the snapped feet."""
    foot_at = {}
    for p in feet:
        foot_at.setdefault(round(line.project(Point(p)), 6), tuple(p))
    out = []
    cur = [pts[0]]
    acc = 0.0
    i = 0
    targets = list(ds)
    while i < len(pts) - 1:
        a, b = pts[i], pts[i + 1]
        L = ST._dist(a, b)
        if targets and acc + L >= targets[0] - 1e-9:
            c = foot_at.get(targets[0]) or G.qpoint(line.interpolate(targets[0]))
            if c != cur[-1]:
                cur.append(c)
            out.append(cur)
            cur = [c]
            targets.pop(0)
            continue
        acc += L
        if b != cur[-1]:
            cur.append(b)
        i += 1
    out.append(cur)
    return [p for p in out if len(p) >= 2]


def _neighbors(walks) -> None:
    at: dict = {}
    for w in walks:
        a, b = tuple(w["line"][0][:2]), tuple(w["line"][-1][:2])
        at.setdefault(a, []).append(w["id"])
        at.setdefault(b, []).append(w["id"])
    for w in walks:
        a, b = tuple(w["line"][0][:2]), tuple(w["line"][-1][:2])
        w["neighbors"] = sorted(set(at[a] + at[b]) - {w["id"]})


# ---------------------------------------------------------------------------
# Model rows
# ---------------------------------------------------------------------------

def _rid(r) -> str:
    return r.id if hasattr(r, "id") else r["id"]


def rows(out: Out) -> dict:
    return {"buildings": sorted(out.buildings, key=_rid),
            "properties": sorted(out.properties, key=_rid),
            "skybridges": sorted(out.skybridges, key=_rid),
            "site_elements": sorted(out.site_elements, key=_rid),
            "structures": sorted(out.structures, key=_rid),
            "green_areas": sorted(out.green_areas, key=_rid),
            "walkways": out.walkways, "megasites": out.megasites}
