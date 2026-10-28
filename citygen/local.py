"""M2 driver: local streets (stage 5), junctions and cross-sections (stage 6), blocks, lots and
open space (stage 10), on the primary network that M1b chose. Returns model rows."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from . import blocks as BK
from . import decks as DK
from . import geom as G
from . import junctions as JN
from . import streets as STR
from . import trace as T

PATH_KINDS = ("park", "plaza", "pocket_park", "market", "garden", "promenade", "beach")
PATH_REACH_M = 30.0


@dataclass
class Local:
    nodes: list = field(default_factory=list)
    segments: list = field(default_factory=list)
    bridges: list = field(default_factory=list)
    junctions: list = field(default_factory=list)
    crosswalks: list = field(default_factory=list)
    sidewalks: list = field(default_factory=list)
    lanes: list = field(default_factory=list)
    walkways: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    lots: list = field(default_factory=list)
    open_spaces: list = field(default_factory=list)
    places: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    info: dict = field(default_factory=dict)
    terrain: dict | None = None    # M13: finished ground, walls, bores, stats
    decks: list = field(default_factory=list)        # M14: deck rows
    structures: list = field(default_factory=list)   # M14: stairs and elevator shafts
    plan: object = None                              # M14: the deck plan (DK.Plan)


def open_paths(W: JN.WalkGraph, opens: list[dict]) -> int:
    """Open space joins the walkway graph: paths from a point inside each park, plaza or
    promenade to the walkway nodes within 30 m of it (up to four, nearest first)."""
    pts = sorted(W.nodes)
    if not pts:
        return 0
    arr = shapely.points(np.array(pts, dtype=np.float64))
    tree = shapely.STRtree(arr)
    n = 0
    for o in opens:
        if o["kind"] not in PATH_KINDS:
            continue
        poly = o["polygon"]
        if poly.geom_type != "Polygon" or poly.is_empty:
            continue
        c = G.qpoint(poly.representative_point())
        idx = sorted(int(i) for i in tree.query(poly, predicate="dwithin",
                                                distance=PATH_REACH_M))
        if not idx:
            continue
        cand = sorted(idx, key=lambda i: (G.dist(poly, arr[i]), pts[i]))
        used = []
        for i in cand:
            p = pts[i]
            if any(STR._dist(p, u) < 25.0 for u in used):
                continue
            used.append(p)
            W.add("path", [c, p], 3.0, open_space=o.get("id"))
            n += 1
            if len(used) >= 4:
                break
    return n


def join_walk_islands(W: JN.WalkGraph, landmasses: list, segments: list) -> int:
    """Walkway groups cut off on their landmass (streets reached only past a highway) join
    the main group by the shortest link up to 150 m: a pedestrian overpass where it crosses
    a highway or avenue, else a path."""
    roots = JN.walk_components([(e["pts"][0], e["pts"][-1]) for e in W.edges])
    if not roots:
        return 0
    big = [LineString(s["centerline"]) for s in segments
           if s["road_class"] in ("highway", "avenue")]
    big_u = shapely.union_all(big) if big else None
    pts = sorted(roots)
    arr = shapely.points(np.array(pts, dtype=np.float64))
    n = 0
    for lm in landmasses:
        inside = np.nonzero(shapely.contains(G.qpoly(lm.buffer(-1.0, join_style="mitre")),
                                             arr))[0].tolist()
        groups: dict = {}
        for i in inside:
            groups.setdefault(roots[pts[i]], []).append(i)
        if len(groups) < 2:
            continue
        main = max(sorted(groups), key=lambda r: len(groups[r]))
        tree = shapely.STRtree(arr[groups[main]])
        for r in sorted(groups):
            if r == main:
                continue
            best = None
            for i in groups[r]:
                # every equally near point, the lowest wins (the tree's own pick among
                # ties follows its std::sort order, which differs between C++ libraries)
                ks = tree.query_nearest(arr[i], all_matches=True).tolist()
                j = min((groups[main][int(k)] for k in ks), key=lambda j: pts[j])
                d = STR._dist(pts[i], pts[j])
                if best is None or (round(d, 6), pts[i]) < (round(best[0], 6), best[1]):
                    best = (d, pts[i], pts[j])
            if best is None or best[0] > 150.0:
                if _path_along_roads(W, [pts[i] for i in groups[r]],
                                     [pts[i] for i in groups[main]], segments):
                    n += 1
                continue
            link = LineString([best[1], best[2]])
            over = big_u is not None and link.crosses(big_u)
            W.add("elevated" if over else "path", [best[1], best[2]], 3.0,
                  z=6.5 if over else 0.0, joins="walkway island")
            n += 1
    return n


def _path_along_roads(W: JN.WalkGraph, island: list, main: list, segments: list) -> bool:
    """A path beside the roads (a highway shoulder path, say) from a cut-off walkway group to
    the main one: the shortest road route between road nodes within 40 m of each group."""
    import heapq

    ends: dict = {}
    adj: dict = {}
    for s in segments:
        a, b = tuple(s["centerline"][0]), tuple(s["centerline"][-1])
        L = s["attrs"]["length_m"]
        adj.setdefault(a, []).append((b, L, s["id"], False))
        adj.setdefault(b, []).append((a, L, s["id"], True))
        ends[s["id"]] = s["centerline"]
    rnodes = sorted(adj)
    if not rnodes:
        return False
    rarr = shapely.points(np.array(rnodes, dtype=np.float64))
    rtree = shapely.STRtree(rarr)

    def near(group):
        out = {}
        garr = shapely.points(np.array(group, dtype=np.float64))
        gi, ri = rtree.query(garr, predicate="dwithin", distance=40.0)
        for g, k in zip(gi.tolist(), ri.tolist()):
            d = STR._dist(group[g], rnodes[k])
            key = rnodes[k]
            if key not in out or (round(d, 6), group[g]) < out[key]:
                out[key] = (round(d, 6), group[g])
        return out

    src, dst = near(island), near(main)
    if not src or not dst:
        return False
    dist = {k: 0.0 for k in src}
    prev: dict = {}
    heap = [(0.0, k) for k in sorted(src)]
    hit = None
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, math.inf):
            continue
        if u in dst:
            hit = u
            break
        for v, L, sid, rev in adj.get(u, []):
            nd = d + L
            if nd < dist.get(v, math.inf) - 1e-9:
                dist[v] = nd
                prev[v] = (u, sid, rev)
                heapq.heappush(heap, (nd, v))
    if hit is None:
        return False
    chain = []
    v = hit
    while v in prev:
        u, sid, rev = prev[v]
        line = ends[sid] if not rev else ends[sid][::-1]
        chain = [tuple(p) for p in line] + chain[1:]
        v = u
    start, goal = v, hit
    pts = [src[start][1]] + ([tuple(p) for p in chain] if chain else [start]) + [dst[goal][1]]
    W.add("path", pts, 2.0, joins="walkway island", beside="roads")
    return True


def _dedupe(notes: list[str]) -> list[str]:
    """Repeated notes once each, in first-seen order, with a count."""
    n: dict = {}
    for t in notes:
        n[t] = n.get(t, 0) + 1
    return [t if k == 1 else f"{t} ({k} times)" for t, k in n.items()]


def build_local(spec, b, did: dict, mapper=None) -> Local:
    with G.canonical():
        return _build_local(spec, b, did, mapper)


def _build_local(spec, b, did: dict, mapper=None) -> Local:
    opens = [G.from_model_poly(o.polygon) for o in b.model.open_spaces]
    net = STR.build_streets(spec, b.hydro, b.layout.polygons, did, b.waterways, b.sites,
                            b.roads, opens, getattr(b, "frame", None))
    # M14: the decks of layered districts (upper twins of their interior streets, ramps)
    pl = DK.plan(spec, net, net.builder, did)
    darch = {did[d.name]: d.archetype for d in spec.districts}
    jx = JN.build(net, darch, did, spec.seed or 0)
    T.stage("junctions", [jx["junctions"], jx["crosswalks"], jx["sidewalks"]])
    T.stage("lanes", jx["lanes"])
    gnet, gjx = DK.ground_view(net, jx, pl)
    blk = BK.build_blocks(spec, net.builder, gnet, gjx, mapper)
    dko = DK.finish(pl, net, jx, blk)
    DK.link_walks(pl, jx, dko["links"])
    out = Local(notes=_dedupe(list(net.notes) + list(blk["notes"]) + pl.notes +
                              [f"{dk.name}: {t}" for dk in pl.decks for t in dk.notes]))
    P = G.to_model_poly
    # open space (named places first, then by district)
    k_by: dict = {}
    well_os: dict = {}
    for o in blk["open"]:
        d = o["district_id"]
        k_by[d] = k_by.get(d, 0) + 1
        o["id"] = f"{d}.os{k_by[d]:03d}"
        poly = o["polygon"]
        if poly.geom_type != "Polygon":
            ps = G.parts(poly)
            if not ps:
                continue
            o["polygon"] = poly = ps[0]
        attrs = {"area_m2": G.q(G.area1(poly)), "m2": True}
        if o.get("light_well"):
            attrs["light_well"] = o["light_well"]
            well_os[o["lot"]] = o["id"]
        out.open_spaces.append({"id": o["id"], "type": f"open_space.{o['kind']}",
                                "kind": o["kind"], "polygon": P(poly), "name": o["name"],
                                "district_id": d, "attrs": attrs})
    n_paths = open_paths(jx["walk"], blk["open"])
    n_links = join_walk_islands(jx["walk"], b.hydro.landmasses, gnet.segments)
    walk = JN.walkways(jx["walk"])
    if pl.decks:
        walk = _deck_walks(pl, net, jx, dko, walk)
    T.stage("walkways", walk)
    out.nodes, out.segments, out.bridges = net.nodes, net.segments, net.bridges
    for j in jx["junctions"]:
        a = j["attrs"]
        out.junctions.append({
            "id": j["id"], "type": f"junction.{a['type']}", "node_id": j["node_id"],
            "polygon": P(j["polygon"]) if not j["polygon"].is_empty else None,
            "shape": a["shape"] if a["shape"] in ("T", "X", "multi", "cul_de_sac") else "multi",
            "legs": a["legs"], "signalized": j["signalized"],
            "corner_radius_m": a["corner_radius_m"], "crosswalk_ids": j["crosswalk_ids"],
            "attrs": {"classes": a["classes"], "archetype": a["archetype"]}})
    out.junctions = [j for j in out.junctions if j["polygon"] is not None]
    out.crosswalks = jx["crosswalks"]
    out.sidewalks = jx["sidewalks"]
    for r in jx["lanes"]:
        r["node_id"] = r.pop("junction_id")
    out.lanes = jx["lanes"]
    out.walkways = walk
    if pl.decks:
        _deck_levels(out, net)
    for bk in blk["blocks"]:
        out.blocks.append({"id": bk["id"], "district_id": bk["district_id"],
                           "archetype": bk["archetype"], "polygon": P(bk["polygon"]),
                           "area_m2": bk["area_m2"], "frontage_ids": bk["frontage_ids"],
                           "attrs": bk["attrs"]})
    for lt in blk["lots"] + dko["upper_lots"]:
        rec = {"id": lt["id"], "block_id": lt["block"],
               "district_id": lt["district_id"], "archetype": lt["archetype"],
               "polygon": P(lt["polygon"]), "area_m2": lt["area_m2"],
               "frontage": lt["frontage"], "frontage_ids": lt["frontage_ids"],
               "merged_group_id": lt.get("merged_group_id"),
               "attrs": lt.get("attrs", {})}
        if lt.get("level"):
            rec["level"] = lt["level"]
        out.lots.append(rec)
    if pl.decks:
        out.decks, out.structures = DK.rows(pl, net, dko, well_os)
        out.plan = pl
    for k, pl in enumerate(blk["places"]):
        out.places.append({"id": f"pl{k + 1:02d}", "type": f"place.{pl['kind']}",
                           "name": pl["name"], "kind": pl["kind"],
                           "district_id": pl["district_id"],
                           "polygon": P(pl["polygon"]) if pl["polygon"] is not None and
                           not pl["polygon"].is_empty else None,
                           "label_at": pl["label_at"], "feature_ids": pl["feature_ids"],
                           "attrs": {k2: v for k2, v in pl["attrs"].items() if v is not None}})
    T.stage("blocks", [out.blocks, out.lots, out.open_spaces, out.places])
    out.info = {"one_way_loops": jx["one_way"], "open_paths": n_paths,
                "walkway_links": n_links,
                "angles": {did[n]: a for n, a in net.angles.items()}}
    if pl.decks:
        out.info["decks"] = DK.info(pl, dko)
    return out


def _deck_walks(pl, net, jx: dict, dko: dict, walk: list) -> list:
    """M14: the decks' walkways (their own walk graph, at the deck top) and the stairs and
    elevators between the levels."""
    tops = {dk.id: dk.top for dk in pl.decks}
    seg_deck = {s["id"]: s["attrs"]["deck"] for s in net.segments if "deck" in s["attrs"]}
    node_deck = {n["id"]: n["attrs"]["deck"] for n in net.nodes if "deck" in n["attrs"]}
    j_deck = {j["id"]: node_deck[j["node_id"]] for j in jx["junctions"]
              if j["node_id"] in node_deck}
    first = pl.decks[0].id

    def deck_of(a):
        if a.get("segment") in seg_deck:
            return seg_deck[a["segment"]]
        if a.get("junction") in j_deck:
            return j_deck[a["junction"]]
        return first

    return DK.walk_rows(jx, dko["links"], walk, tops, deck_of, DK.ramp_walks(pl, net, jx))


def _deck_levels(out: Local, net) -> None:
    """M14: level 1 on the deck's junctions, crosswalks, sidewalks and lanes (its ramps'
    lanes too)."""
    seg = {s["id"] for s in net.segments if "deck" in s["attrs"]}
    node = {n["id"] for n in net.nodes if "deck" in n["attrs"]}
    jn = set()
    for j in out.junctions:
        if j["node_id"] in node:
            j["level"] = 1
            jn.add(j["id"])
    for c in out.crosswalks:
        if c["junction_id"] in jn:
            c["level"] = 1
    for w in out.sidewalks:
        if w["segment_id"] in seg:
            w["level"] = 1
    for r in out.lanes:
        if (r["segment_id"] in seg) if r["kind"] == "lane" else (r["node_id"] in node):
            r["level"] = 1
