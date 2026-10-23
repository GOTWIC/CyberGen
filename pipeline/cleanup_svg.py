"""
Corporate Core SVG cleanup (repeatable, idempotent).

Usage:  python3 cleanup_svg.py input.svg output.svg

What it does (each run, on whatever is in the file):
  Buildings (building + landmark layers)
    - open 3-point paths (two traced base edges)  -> exact rectangle
    - closed 4-point paths                         -> exact rectangle (best fit)
    - rectangle angles within SNAP_TOL of a multiple of SNAP_STEP are snapped
    - any other shape is left untouched
  Megatower
    - the path with id "megatower" (or listed in MEGATOWER_IDS) is rebuilt as a
      perfectly symmetric three-armed shape: equal arms at 120 degrees, straight
      cut ends, identical concave circular edges. Size, arm width, edge depth and
      position are re-fitted from the current shape, so editing it in Inkscape
      and re-running keeps your changes but restores the symmetry.
    - it is moved to the landmark layer and given a height label if it has none.
Everything else in the file (layers, reference image, styles, ids, labels) is
preserved, so the output opens and edits in Inkscape exactly like the input.
"""
import math, re, sys
from lxml import etree
from svgelements import Path
from shapely.geometry import Polygon, LineString, Point

SVG = "http://www.w3.org/2000/svg"
INK = "http://www.inkscape.org/namespaces/inkscape"
SNAP_STEP, SNAP_TOL = 45.0, 6.0          # degrees
MEGATOWER_IDS = ["megatower", "path65"]  # path65 = first traced version
MEGATOWER_HEIGHT = "480"
MEGA_ORIENT_STEP, MEGA_ORIENT_TOL = 15.0, 6.0

def norm(s): return re.sub(r"[^a-z]", "", (s or "").lower())

def layer_map(root):
    out = {}
    for g in root.iter(f"{{{SVG}}}g"):
        if g.get(f"{{{INK}}}groupmode") == "layer":
            out[norm(g.get(f"{{{INK}}}label"))] = g
    return out

def path_points(d):
    """Returns (points, closed, has_curves) for single-subpath paths, else None."""
    p = Path(d)
    subs = list(p.as_subpaths())
    if len(subs) != 1:
        return None
    pts, closed, curves = [], False, False
    for seg in Path(subs[0]).segments():
        n = type(seg).__name__
        if n in ("Move", "Line"):
            pts.append((seg.end.x, seg.end.y))
        elif n == "Close":
            closed = True
        else:
            curves = True
    clean = [pts[0]]
    for q in pts[1:]:
        if math.dist(q, clean[-1]) > 1e-6:
            clean.append(q)
    if closed and len(clean) > 2 and math.dist(clean[0], clean[-1]) < 1e-6:
        clean.pop()
    return clean, closed, curves

def fmt(v): return f"{v:.3f}".rstrip("0").rstrip(".")

def snap_angle(a_deg, step, tol):
    k = round(a_deg / step) * step
    return (k, True) if abs(a_deg - k) <= tol else (a_deg, False)

# ---------------------------------------------------------------- rectangles
def fit_rectangle(quad):
    """Best-fit rectangle for 4 roughly-rectangular corners (in order)."""
    # dominant direction: circular mean of edge angles modulo 90
    sx = sy = 0.0
    for i in range(4):
        (x1, y1), (x2, y2) = quad[i], quad[(i + 1) % 4]
        a = math.atan2(y2 - y1, x2 - x1)
        L = math.hypot(x2 - x1, y2 - y1)
        sx += L * math.cos(4 * a); sy += L * math.sin(4 * a)
    a_deg = math.degrees(math.atan2(sy, sx) / 4) % 90
    a_deg, snapped = snap_angle(a_deg, SNAP_STEP, SNAP_TOL)
    a = math.radians(a_deg)
    c, s = math.cos(a), math.sin(a)
    rot = [(x * c + y * s, -x * s + y * c) for x, y in quad]          # into rectangle frame
    xs = sorted(p[0] for p in rot); ys = sorted(p[1] for p in rot)
    x0, x1 = (xs[0] + xs[1]) / 2, (xs[2] + xs[3]) / 2
    y0, y1 = (ys[0] + ys[1]) / 2, (ys[2] + ys[3]) / 2
    rect = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    back = [(u * c - v * s, u * s + v * c) for u, v in rect]
    # keep the start corner nearest the original first point for stable node order
    k = min(range(4), key=lambda i: math.dist(back[i], quad[0]))
    back = back[k:] + back[:k]
    shift = max(min(math.dist(b, q) for q in quad) for b in back)
    return back, snapped, shift

def rect_d(pts):
    return "M " + " L ".join(f"{fmt(x)},{fmt(y)}" for x, y in pts) + " Z"

# ---------------------------------------------------------------- megatower
def fit_megatower(d):
    p = Path(d)
    lines = []
    for seg in p.segments():
        if type(seg).__name__ == "Line":
            L = math.dist((seg.start.x, seg.start.y), (seg.end.x, seg.end.y))
            if L > 1:
                lines.append((L, (seg.start.x, seg.start.y), (seg.end.x, seg.end.y)))
    lines = sorted(lines, reverse=True)[:3]
    if len(lines) < 3:
        raise ValueError("megatower: could not find three straight arm ends")
    mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for _, a, b in lines]
    cx = sum(m[0] for m in mids) / 3; cy = sum(m[1] for m in mids) / 3
    R = sum(math.dist(m, (cx, cy)) for m in mids) / 3
    W = sum(L for L, _, _ in lines) / 3
    # orientation: circular mean of arm angles modulo 120 (svg coords, y down)
    angs = [math.atan2(m[1] - cy, m[0] - cx) for m in mids]
    sx = sum(math.cos(3 * a) for a in angs); sy = sum(math.sin(3 * a) for a in angs)
    base = math.degrees(math.atan2(sy, sx) / 3)
    base, _ = snap_angle(base, MEGA_ORIENT_STEP, MEGA_ORIENT_TOL)
    # inner radius: where each bisector ray hits the outline
    pts = [(seg.point(t).x, seg.point(t).y) for seg in p.segments()
           if type(seg).__name__ not in ("Move", "Close") for t in [i / 16 for i in range(17)]]
    outline = Polygon(pts).buffer(0).exterior
    arm_angles = sorted(((base + 120 * k) % 360) for k in range(3))
    r_in = []
    for k in range(3):
        b = math.radians(arm_angles[k] + 60)
        ray = LineString([(cx, cy), (cx + 2000 * math.cos(b), cy + 2000 * math.sin(b))])
        hit = ray.intersection(outline)
        hp = [hit] if hit.geom_type == "Point" else list(getattr(hit, "geoms", []))
        if hp:
            r_in.append(min(Point(cx, cy).distance(q) for q in hp))
    rin = sum(r_in) / len(r_in)
    return dict(cx=cx, cy=cy, R=R, W=W, base=base, r_in=rin)

def megatower_d(cx, cy, R, W, base, r_in):
    corners = []   # per arm: (left corner, right corner) going counter-clockwise in svg angle order
    for k in range(3):
        a = math.radians(base + 120 * k)
        tx, ty = cx + R * math.cos(a), cy + R * math.sin(a)
        px, py = -math.sin(a), math.cos(a)
        corners.append(((tx - px * W / 2, ty - py * W / 2), (tx + px * W / 2, ty + py * W / 2)))
    parts = [f"M {fmt(corners[0][0][0])},{fmt(corners[0][0][1])}"]
    for k in range(3):
        a_end = corners[k][1]
        b_start = corners[(k + 1) % 3][0]
        parts.append(f"L {fmt(a_end[0])},{fmt(a_end[1])}")
        # circular arc a_end -> b_start passing through the bisector point at r_in
        bis = math.radians(base + 120 * k + 60)
        mx, my = cx + r_in * math.cos(bis), cy + r_in * math.sin(bis)
        chord = math.dist(a_end, b_start) / 2
        mid = ((a_end[0] + b_start[0]) / 2, (a_end[1] + b_start[1]) / 2)
        sag = math.dist(mid, (mx, my))
        r = (chord ** 2 + sag ** 2) / (2 * sag)
        # pick the sweep whose arc passes through (mx, my)
        best = None
        for sweep in (0, 1):
            test = Path(f"M {a_end[0]},{a_end[1]} A {r},{r} 0 0 {sweep} {b_start[0]},{b_start[1]}")
            q = test.point(0.5)
            err = math.dist((q.x, q.y), (mx, my))
            if best is None or err < best[0]:
                best = (err, sweep)
        parts.append(f"A {fmt(r)},{fmt(r)} 0 0 {best[1]} {fmt(b_start[0])},{fmt(b_start[1])}")
    parts[-1] = parts[-1]  # last arc ends at the start corner
    return " ".join(parts) + " Z"

# ---------------------------------------------------------------- main
def cleanup(src, dst):
    parser = etree.XMLParser(huge_tree=True, remove_blank_text=False)
    tree = etree.parse(src, parser)
    root = tree.getroot()
    layers = layer_map(root)
    report = dict(rect_from_3pt=0, rect_from_quad=0, snapped=0, untouched=[], max_shift=0.0, megatower=None)

    # megatower first (so it isn't treated as a generic building)
    mega_el = None
    for el in root.iter(f"{{{SVG}}}path"):
        if el.get("id") in MEGATOWER_IDS or "megatower" in norm(el.get(f"{{{INK}}}label")):
            mega_el = el
            break
    if mega_el is not None:
        prm = fit_megatower(mega_el.get("d"))
        mega_el.set("d", megatower_d(**prm))
        mega_el.set("id", "megatower")
        if not re.fullmatch(r"\s*\d+(\.\d+)?\s*m?\s*", mega_el.get(f"{{{INK}}}label") or ""):
            mega_el.set(f"{{{INK}}}label", MEGATOWER_HEIGHT)
        lm = layers.get("landmark")
        if lm is not None and mega_el.getparent() is not lm:
            mega_el.getparent().remove(mega_el)
            lm.append(mega_el)
        report["megatower"] = {k: round(v, 2) for k, v in prm.items()}

    for key in ("building", "landmark"):
        g = layers.get(key)
        if g is None:
            continue
        for el in g.iter(f"{{{SVG}}}path"):
            if el is mega_el:
                continue
            info = path_points(el.get("d"))
            if info is None:
                report["untouched"].append(el.get("id")); continue
            pts, closed, curves = info
            if curves:
                report["untouched"].append(el.get("id")); continue
            if len(pts) == 3 and not closed:
                p1, p2, p3 = pts
                quad = [p1, p2, p3, (p1[0] + p3[0] - p2[0], p1[1] + p3[1] - p2[1])]
                kind = "rect_from_3pt"
            elif len(pts) == 4 and closed:
                quad, kind = pts, "rect_from_quad"
            else:
                report["untouched"].append(el.get("id")); continue
            rect, snapped, shift = fit_rectangle(quad)
            if kind == "rect_from_quad" and shift < 0.01:
                report["already_clean"] = report.get("already_clean", 0) + 1
                continue                                   # already a rectangle: leave the file untouched
            el.set("d", rect_d(rect))
            report[kind] += 1
            report["snapped"] += int(snapped)
            report["max_shift"] = max(report["max_shift"], shift)

    tree.write(dst, xml_declaration=True, encoding="UTF-8", standalone=False)
    report["max_shift"] = round(report["max_shift"], 2)
    return report

if __name__ == "__main__":
    r = cleanup(sys.argv[1], sys.argv[2])
    for k, v in r.items():
        print(f"{k}: {v}")
