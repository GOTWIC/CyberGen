"""
Inkscape SVG -> city plan.

Reads layers by name (coast, highway, avenue, street, elevated road, building, landmark,
water, park, plaza, pier). 1 SVG unit = 1 meter. Outputs:
  geometry.json  : polygons + building prisms (for 2D map / 3D render)
  plan.json      : box/cylinder primitives for the Unreal greybox script
"""
import json, math, re, sys, random
import xml.etree.ElementTree as ET
from svgelements import Path
from shapely.geometry import Polygon, LineString, MultiPolygon, Point, box as sbox
from shapely.ops import unary_union

SVG_NS = "{http://www.w3.org/2000/svg}"
INK = "{http://www.inkscape.org/namespaces/inkscape}"
CANVAS = 1200.0

def norm(label):
    return re.sub(r"[^a-z]", "", (label or "").lower())

LAYER_KEYS = {"coast": "coast", "highway": "highway", "avenue": "avenue", "street": "street",
              "elevatedroad": "elevated", "elevated": "elevated", "building": "building",
              "landmark": "landmark", "water": "water", "park": "park", "plaza": "plaza", "pier": "pier"}
ROAD_LAYERS = ("highway", "avenue", "street", "elevated")
DEFAULT_WIDTH = {"highway": 24, "avenue": 18, "street": 11, "elevated": 20}

def to_plan(x, y):  # svg (x right, y down) -> plan meters (x east, y north), origin at canvas center
    return (x - CANVAS / 2, CANVAS / 2 - y)

def sample_subpaths(d, per_curve=10):
    out = []
    for sp in Path(d).as_subpaths():
        sp = Path(sp)
        pts, closed = [], False
        for seg in sp.segments():
            name = type(seg).__name__
            if name == "Move":
                pts.append(to_plan(seg.end.x, seg.end.y))
            elif name == "Close":
                closed = True
            elif name == "Line":
                pts.append(to_plan(seg.end.x, seg.end.y))
            else:
                for i in range(1, per_curve + 1):
                    p = seg.point(i / per_curve)
                    pts.append(to_plan(p.x, p.y))
        dedup = [pts[0]] if pts else []
        for p in pts[1:]:
            if math.dist(p, dedup[-1]) > 1e-6:
                dedup.append(p)
        if closed and len(dedup) > 2 and math.dist(dedup[0], dedup[-1]) < 1e-6:
            dedup.pop()
        out.append((dedup, closed))
    return out

def style_value(el, key):
    m = re.search(key + r"\s*:\s*([^;]+)", el.get("style", ""))
    return m.group(1).strip() if m else el.get(key)

def read_layers(svg_path):
    root = ET.parse(svg_path).getroot()
    layers = {}
    for g in root.iter(SVG_NS + "g"):
        if g.get(INK + "groupmode") != "layer":
            continue
        key = LAYER_KEYS.get(norm(g.get(INK + "label")))
        if not key:
            continue
        items = layers.setdefault(key, [])
        for el in g.iter():
            tag = el.tag.replace(SVG_NS, "")
            d = None
            if tag == "path":
                d = el.get("d")
            elif tag == "rect":
                x, y, w, h = (float(el.get(k, 0)) for k in ("x", "y", "width", "height"))
                d = f"M {x},{y} h {w} v {h} h {-w} Z"
            elif tag in ("circle", "ellipse"):
                cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
                rx = float(el.get("r", el.get("rx", 0))); ry = float(el.get("r", el.get("ry", rx)))
                d = f"M {cx-rx},{cy} A {rx},{ry} 0 1 0 {cx+rx},{cy} A {rx},{ry} 0 1 0 {cx-rx},{cy} Z"
            if not d:
                continue
            sw = style_value(el, "stroke-width")
            items.append(dict(id=el.get("id"), label=el.get(INK + "label"), d=d,
                              stroke_width=float(sw) if sw else None))
    return layers

# ---------------------------------------------------------------- buildings
def complete_rect(p1, p2, p3, square_tol_deg=12):
    """p2 is the visible corner; returns 4 corners."""
    ux, uy = p1[0] - p2[0], p1[1] - p2[1]
    vx, vy = p3[0] - p2[0], p3[1] - p2[1]
    L1, L2 = math.hypot(ux, uy), math.hypot(vx, vy)
    a1, a2 = math.atan2(uy, ux), math.atan2(vy, vx)
    diff = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi        # signed angle u -> v
    err = abs(diff) - math.pi / 2
    if abs(math.degrees(err)) <= square_tol_deg:
        s = 1 if diff > 0 else -1
        a1n = a1 + s * err / 2                                     # rotate both edges half the error
        a2n = a1n + s * math.pi / 2
        u = (math.cos(a1n) * L1, math.sin(a1n) * L1)
        v = (math.cos(a2n) * L2, math.sin(a2n) * L2)
    else:
        u, v = (ux, uy), (vx, vy)
    return [p2, (p2[0] + u[0], p2[1] + u[1]), (p2[0] + u[0] + v[0], p2[1] + u[1] + v[1]), (p2[0] + v[0], p2[1] + v[1])]

def auto_height(poly, bid, focus=(0.0, 140.0)):
    rnd = random.Random(bid)
    d = Point(focus).distance(poly.centroid)
    size = min(1.4, max(0.6, math.sqrt(poly.area) / 32))
    h = (45 + 230 * math.exp(-d / 330)) * size * rnd.uniform(0.8, 1.2)
    return float(round(max(25, min(h, 320)) / 5) * 5)

def parse_height(label):
    if not label:
        return None
    m = re.fullmatch(r"\s*(\d+(\.\d+)?)\s*m?\s*", label)
    return float(m.group(1)) if m else None

# ---------------------------------------------------------------- main
def convert(svg_path, out_dir):
    layers = read_layers(svg_path)
    warnings = []

    # land
    land = None
    for item in layers.get("coast", []):
        rings = [Polygon(p).buffer(0) for p, _ in sample_subpaths(item["d"]) if len(p) >= 3]
        if not rings:
            continue
        rings.sort(key=lambda g: g.area, reverse=True)
        shape = rings[0]
        for r in rings[1:]:
            shape = shape.difference(r) if shape.contains(r.representative_point()) else shape.union(r)
        land = shape if land is None else land.union(shape)
    if land is None:
        sys.exit("No coast found")

    # roads
    roads = []
    for cat in ROAD_LAYERS:
        for item in layers.get(cat, []):
            w = item["stroke_width"] or DEFAULT_WIDTH[cat]
            for pts, closed in sample_subpaths(item["d"], per_curve=12):
                if len(pts) < 2:
                    continue
                if closed:
                    pts = pts + [pts[0]]
                roads.append(dict(cat=cat, id=item["id"], width=w, points=pts))

    # buildings + landmarks
    buildings = []
    for cat in ("building", "landmark"):
        for item in layers.get(cat, []):
            for pts, closed in sample_subpaths(item["d"]):
                if len(pts) == 3 and not closed:
                    corners = complete_rect(*pts)
                elif len(pts) >= 3:
                    corners = pts
                else:
                    warnings.append(f"{item['id']}: fewer than 3 points, skipped")
                    continue
                poly = Polygon(corners).buffer(0)
                if poly.is_empty or poly.area < 4:
                    warnings.append(f"{item['id']}: degenerate footprint, skipped")
                    continue
                if poly.geom_type != "Polygon":
                    poly = max(poly.geoms, key=lambda g: g.area)
                h = parse_height(item["label"])
                buildings.append(dict(id=item["id"], cat=cat, height=h if h else auto_height(poly, item["id"]),
                                      height_source="label" if h else "auto",
                                      footprint=[list(map(lambda v: round(v, 2), c)) for c in poly.exterior.coords[:-1]]))
                if not land.buffer(1).contains(poly):
                    warnings.append(f"{item['id']}: footprint extends off the island")

    # simple filled areas
    areas = []
    for cat in ("water", "park", "plaza", "pier"):
        for item in layers.get(cat, []):
            for pts, closed in sample_subpaths(item["d"]):
                if len(pts) >= 3:
                    areas.append(dict(cat=cat, id=item["id"], points=pts))

    def poly_json(g):
        polys = [g] if g.geom_type == "Polygon" else list(g.geoms)
        return [dict(exterior=[list(c) for c in p.exterior.coords[:-1]],
                     holes=[[list(c) for c in r.coords[:-1]] for r in p.interiors]) for p in polys]

    geometry = dict(land=poly_json(land), roads=roads, buildings=buildings, areas=areas,
                    stats=dict(land_area_m2=round(land.area), island_width_m=round(land.bounds[2] - land.bounds[0]),
                               island_height_m=round(land.bounds[3] - land.bounds[1]),
                               roads=len(roads), buildings=len(buildings)),
                    warnings=warnings)
    json.dump(geometry, open(f"{out_dir}/geometry.json", "w"), indent=1)

    # ---------- Unreal primitives (same format as the first greybox script)
    prims = []
    def add(kind, cat, c, s, yaw=0.0):
        prims.append(dict(kind=kind, cat=cat, center=[round(v, 3) for v in c], size=[round(v, 3) for v in s], yaw=round(yaw, 2)))

    add("box", "water", (0, 0, -3.0), (3200, 3200, 1.0))
    STRIP = 4.0
    y = land.bounds[1]
    while y < land.bounds[3]:
        band = land.intersection(sbox(-3000, y, 3000, y + STRIP))
        parts = [] if band.is_empty else ([band] if band.geom_type == "Polygon" else [g for g in getattr(band, "geoms", []) if g.area > 0])
        for part in parts:
            x0, _, x1, _ = part.bounds
            add("box", "ground", ((x0 + x1) / 2, y + STRIP / 2, -1.0), (x1 - x0, STRIP, 2.0))
        y += STRIP

    land_buf = land.buffer(0.5)
    ztop = {"highway": 0.06, "avenue": 0.05, "street": 0.04, "elevated": 0.06}
    for r in roads:
        pts, w = r["points"], r["width"]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            L = math.hypot(x2 - x1, y2 - y1)
            if L < 0.05:
                continue
            mid = ((x1 + x2) / 2, (y1 + y2) / 2)
            on_land = land_buf.contains(LineString([(x1, y1), (x2, y2)]))
            cat = r["cat"] if on_land else "bridge"
            th = 0.1 if on_land else 1.5
            top = ztop.get(r["cat"], 0.05)
            add("box", cat, (mid[0], mid[1], top - th / 2), (L, w, th), math.degrees(math.atan2(y2 - y1, x2 - x1)))
        for (x, yy) in pts[1:-1]:
            on_land = land_buf.contains(Point(x, yy))
            th = 0.1 if on_land else 1.5
            add("cyl", r["cat"] if on_land else "bridge", (x, yy, ztop.get(r["cat"], 0.05) - th / 2), (w, w, th))

    for b in buildings:  # oriented bounding box -> box primitive (Unreal greybox uses boxes)
        poly = Polygon(b["footprint"])
        mrr = poly.minimum_rotated_rectangle
        c = list(mrr.exterior.coords)[:4]
        e1 = (c[1][0] - c[0][0], c[1][1] - c[0][1]); e2 = (c[2][0] - c[1][0], c[2][1] - c[1][1])
        L1, L2 = math.hypot(*e1), math.hypot(*e2)
        cx, cy = mrr.centroid.x, mrr.centroid.y
        add("box", "landmark" if b["cat"] == "landmark" else "tower", (cx, cy, b["height"] / 2),
            (L1, L2, b["height"]), math.degrees(math.atan2(e1[1], e1[0])))

    plan = dict(meta=dict(name="Corporate Core (traced)", units="meters", axes="x=east, y=north, z=up",
                          source=svg_path.split("/")[-1], player_start=[0, -300, 1.2], player_start_facing="north"),
                primitives=prims)
    json.dump(plan, open(f"{out_dir}/corporate_core_plan.json", "w"), indent=1)
    return geometry

if __name__ == "__main__":
    g = convert(sys.argv[1], sys.argv[2])
    print(json.dumps(g["stats"]), "\n".join(g["warnings"]) or "no warnings")
