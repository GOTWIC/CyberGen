"""Halcyon's shared helpers: the light strips that run round the nose and tail caps' bands
(the front strip under the nose lip, the tail's bar or closed ring), and the spine's edge.

The Vanta R, the Sable and the Ridge share little code: their parts are each car's own.
What they repeated:

- cap_band (was written out in each car's front and rear): a light strip swept along a
  cap's band (carkit's band_point) through given body points, the front strip's section
  STRIP, the rear's STRIP_REAR; with mid, a left half carried on through the centerline
  point mid and mirrored round the right side (the tail bar; with closed, the ring).
- on_spine_edge (the Sable and the Ridge): y of the spine's edge (the P line) at x. The
  car's PT and ORDER are arguments; inset moves the point in from the edge (the Sable
  0.028) and miss is what it gives off the spine (the Sable 0.1, the Ridge 0.2).

On step B the Vanta-R and the Sable cut their strips as light channels under lenses
(carkit's groove and Lamp), each car's own; cap_band is the strip as it was before.

Left in the cars: the hulls (stations, panels, creases), the Ridge's slab, honey_on,
tow_eye, armor_ring and tire (one car each), each car's sill strips.
"""
from carkit import band_point, my

STRIP = [(-0.009, -0.004), (0.009, -0.004), (0.009, 0.006), (-0.009, 0.006)]
STRIP_REAR = [(-0.008, -0.006), (0.008, -0.006), (0.008, 0.004), (-0.008, 0.004)]


def cap_band(g, pts, center, band_w, mid=None, rear=False, closed=False, sec=None, up=None):
    """A light strip in the band round a cap (center its middle, band_w the band's width,
    as given to build_body) through pts, points of the body on the band's line. With mid
    the strip goes on from the last point through mid (on the centerline) and back round
    the other side, mirrored. rear: the tail's section and facing (STRIP_REAR, aft), else
    the nose's (STRIP, forward); sec and up override them."""
    path = [band_point(p, center, band_w * 0.5, 0.0) for p in pts]
    if mid is not None:
        path = (path + [band_point(mid, center, band_w * 0.5, 0.0)]
                + [my(p) for p in path[::-1]])
    if sec is None:
        sec = STRIP_REAR if rear else STRIP
    if up is None:
        up = (-1, 0, 0) if rear else (1, 0, 0)
    g.sweep(path, sec, up=up, closed=closed)


def on_spine_edge(x, *, pt, order, inset=0.0, miss=0.2):
    """y of the spine's edge at x (the P line as drawn, through the stations order of the
    car's table pt), inset in from it; miss off the spine's length."""
    pts = [pt[s]["P"] for s in order]
    for a, b in zip(pts, pts[1:]):
        if b.x <= x <= a.x:
            t = (a.x - x) / max(a.x - b.x, 1e-6)
            return a.y + (b.y - a.y) * t - inset
    return miss

