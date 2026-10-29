"""Plant variants (scope 5.4): trees by species grown by space colonization, palms,
conifers, shrubs, sedum, scrub and ivy, each in its own frame at a base size that the
instance scales to its plant's crown radius and height.

**Space colonization** (Runions, Lane, Prusinkiewicz 2007): attraction points fill the
species' crown envelope; each round every point within the influence radius of the tree
pulls its nearest node, each pulled node grows one step toward the mean of its points, and
points within the kill radius of a node are removed, until none is left or none can be
reached. Branch radii follow the pipe model ($r^2 = \\sum r_{child}^2$) from a tip radius,
scaled so the trunk has the species' base radius. Chains of nodes become tubes (6 sides on
the trunk and limbs, 4 on branches, none under 1.5 cm), leaves are alpha-cut cards along
the twigs (two crossed quads each, showing a whole tile of AG6's leaf clumps of the
species' leaf shape: `leaves_<shape>`), as are pine needles, the loose leaves of shrubs and
ivy; palms, sedum, scrub and the body of a shrub are solid foliage.

Determinism: the attraction points and every draw come from blake2b hashes of (species,
variant, purpose); the distances are numpy elementwise products and sums of three terms in a
fixed order, `argmin` picks the nearest node (ties to the lower index); the growth
directions are summed in a Python loop in point order; angles come from `dmath`.

Base sizes (`BASE`, crown radius and height in meters) per species: the instance's scale
is (crown / r0, crown / r0, height / h0), as the blockout scales its prototypes.
"""

from __future__ import annotations

import math

import numpy as np

from citygen import dmath as M

from . import styles as ST
from .shapes import Mesh, add, cross, fan, lathe, mul, norm, quad_out, ring, sub, tube

# crown radius, height (m) of each species' variants before the instance scales them
BASE = {"plane": (4.0, 12.0), "maple": (3.5, 10.0), "ginkgo": (2.6, 11.0),
        "birch": (2.8, 12.0), "linden": (3.5, 11.0), "elm": (4.2, 13.0), "oak": (4.5, 12.0),
        "ficus": (3.6, 9.0), "pine": (2.8, 12.0), "fan_palm": (2.2, 10.0),
        "date_palm": (3.0, 10.0), "boxwood": (0.8, 1.2), "sedum": (0.6, 0.6),
        "scrub": (0.8, 0.8), "ivy": (0.75, 2.0)}

# envelope: (kind, crown bottom as a share of height, width share, points, trunk radius,
# leaf slot, bark slot, leaf size m, leaves per twig, droop)
TREES = {
    "plane": ("round", 0.3, 1.0, 420, 0.24, "leaf.plane", "bark.plane", 0.32, 4, 0.0),
    "maple": ("round", 0.25, 1.0, 380, 0.2, "leaf.maple", "bark.grey", 0.28, 4, 0.0),
    "ginkgo": ("cone", 0.22, 0.85, 320, 0.18, "leaf.ginkgo", "bark.ginkgo", 0.24, 3, 0.0),
    "birch": ("oval", 0.3, 0.8, 340, 0.15, "leaf.birch", "bark.birch", 0.2, 4, 0.35),
    "linden": ("oval", 0.25, 1.0, 400, 0.22, "leaf.linden", "bark.dark", 0.28, 4, 0.0),
    "elm": ("vase", 0.3, 1.0, 400, 0.24, "leaf.elm", "bark.dark", 0.26, 4, 0.15),
    "oak": ("spread", 0.25, 1.0, 440, 0.3, "leaf.oak", "bark.dark", 0.3, 4, 0.0),
    "ficus": ("dome", 0.2, 1.0, 420, 0.26, "leaf.ficus", "bark.grey", 0.22, 5, 0.0),
}
TIP_R = 0.012
STEP = 0.45            # growth step, as a share of 1 m at the base size
INFLUENCE = 2.4
KILL = 0.7


def make(species: str, k: int) -> Mesh:
    m = Mesh((0.0, 0.0))
    key = ("ag8", "plant", species, k)
    if species in TREES:
        broadleaf(m, species, key)
    elif species == "pine":
        pine(m, key)
    elif species in ("fan_palm", "date_palm"):
        palm(m, species, key)
    elif species == "boxwood":
        shrub(m, key)
    elif species == "sedum":
        sedum(m, key)
    elif species == "scrub":
        scrub(m, key)
    elif species == "ivy":
        ivy(m, key)
    else:
        raise KeyError(species)
    return m


def _u(key, *p) -> float:
    return ST.u(*key, *p)


# ---------------------------------------------------------------------------------------
# space colonization
# ---------------------------------------------------------------------------------------

def _envelope(kind: str, r0: float, h0: float, bottom: float, width: float, n: int,
              key) -> list[tuple[float, float, float]]:
    """n attraction points inside the crown envelope (rejection sampling by hash)."""
    pts = []
    zc0 = h0 * bottom
    span = h0 - zc0
    R = r0 * width
    i = 0
    while len(pts) < n and i < n * 12:
        x = (2.0 * _u(key, "ax", i) - 1.0) * R
        y = (2.0 * _u(key, "ay", i) - 1.0) * R
        t = _u(key, "az", i)
        z = zc0 + span * t
        i += 1
        q = (x * x + y * y) / (R * R)
        if kind == "round":
            ok = q + (2.0 * t - 1.0) ** 2 <= 1.0
        elif kind == "oval":
            ok = q / (0.75 + 0.25 * M.sin(M.PI * t)) + (2.0 * t - 1.0) ** 2 <= 1.0
        elif kind == "cone":
            w = 1.0 - 0.85 * t
            ok = q <= w * w and t > 0.02
        elif kind == "vase":
            w = 0.35 + 0.65 * min(1.0, t * 1.4)
            ok = q <= w * w and (t < 0.8 or q + ((t - 0.8) / 0.2) ** 2 <= 1.0)
        elif kind == "spread":
            ok = q + ((2.0 * t - 1.0) * 1.25) ** 2 <= 1.0 and t > 0.08
        else:  # dome
            ok = q + t * t <= 1.0
        # a little noise in the outline, so variants differ in silhouette
        if ok and _u(key, "hole", int(x * 0.8) + 7, int(y * 0.8) + 7, int(z * 0.8)) < 0.12:
            ok = False
        if ok:
            pts.append((x, y, z))
    return pts


def colonize(points, root, trunk_top: float, step: float, influence: float, kill: float,
             max_iter: int = 90):
    """Grow a skeleton toward the points: (positions, parents)."""
    nodes = [root]
    parents = [-1]
    # the trunk up to the crown
    z = root[2]
    while z + step < trunk_top:
        z += step
        nodes.append((root[0], root[1], z))
        parents.append(len(nodes) - 2)
    pts = list(points)
    kids: dict[int, list] = {}
    grew = False
    for _ in range(max_iter):
        if not pts:
            break
        P = np.array(pts, dtype=np.float64)
        N = np.array(nodes, dtype=np.float64)
        dx = P[:, None, 0] - N[None, :, 0]
        dy = P[:, None, 1] - N[None, :, 1]
        dz = P[:, None, 2] - N[None, :, 2]
        d2 = dx * dx + dy * dy + dz * dz
        near = np.argmin(d2, axis=1)
        dmin = d2[np.arange(len(pts)), near]
        pull: dict[int, list[float]] = {}
        for i in range(len(pts)):
            if dmin[i] > influence * influence:
                continue
            j = int(near[i])
            v = sub(pts[i], nodes[j])
            L = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
            if L == 0.0:
                continue
            acc = pull.setdefault(j, [0.0, 0.0, 0.0])
            acc[0] += v[0] / L
            acc[1] += v[1] / L
            acc[2] += v[2] / L
        if not pull:
            if grew or nodes[-1][2] > trunk_top + 6.0 * step:
                break
            # nothing in reach yet: the trunk goes on up
            top = nodes[len(nodes) - 1]
            nodes.append((top[0], top[1], top[2] + step))
            parents.append(len(nodes) - 2)
            continue
        grown = 0
        for j in sorted(pull):
            d = norm(tuple(pull[j]))
            p = add(nodes[j], mul(d, step))
            # a node pulled the same way again (its points not yet reached) grows no twin
            if any(abs(p[0] - q[0]) + abs(p[1] - q[1]) + abs(p[2] - q[2]) < 0.02
                   for q in kids.get(j, ())):
                continue
            kids.setdefault(j, []).append(p)
            nodes.append(p)
            parents.append(j)
            grown += 1
        if grown == 0:
            break
        grew = True
        N = np.array(nodes, dtype=np.float64)
        P = np.array(pts, dtype=np.float64)
        dx = P[:, None, 0] - N[None, :, 0]
        dy = P[:, None, 1] - N[None, :, 1]
        dz = P[:, None, 2] - N[None, :, 2]
        d2 = dx * dx + dy * dy + dz * dz
        alive = np.min(d2, axis=1) > kill * kill
        pts = [pts[i] for i in range(len(pts)) if alive[i]]
    return nodes, parents


def _radii(parents, tip: float, base: float) -> list[float]:
    """Pipe model radii, scaled so the root has the base radius."""
    n = len(parents)
    kids: list[list[int]] = [[] for _ in range(n)]
    for i, p in enumerate(parents):
        if p >= 0:
            kids[p].append(i)
    r2 = [0.0] * n
    for i in range(n - 1, -1, -1):
        if kids[i]:
            r2[i] = sum(r2[c] for c in kids[i])
        else:
            r2[i] = tip * tip
    root = math.sqrt(r2[0]) if r2[0] > 0 else tip
    k = base / root
    # thin the twigs less than the trunk: r = tip + (sqrt(r2) - tip) * k
    return [tip + (math.sqrt(v) - tip) * k if k < 1.0 else math.sqrt(v) * k for v in r2]


def _chains(parents, radii) -> list[list[int]]:
    """Chains of nodes: each follows its thickest child; the others start chains."""
    n = len(parents)
    kids: list[list[int]] = [[] for _ in range(n)]
    for i, p in enumerate(parents):
        if p >= 0:
            kids[p].append(i)
    out = []
    starts = [0]
    while starts:
        s = starts.pop()
        chain = [s] if parents[s] < 0 else [parents[s], s]
        cur = s
        while kids[cur]:
            best = max(kids[cur], key=lambda c: (radii[c], -c))
            for c in kids[cur]:
                if c != best:
                    starts.append(c)
            chain.append(best)
            cur = best
        out.append(chain)
    return out


def broadleaf(m: Mesh, species: str, key) -> None:
    kind, bottom, width, npts, trunk_r, leaf, bark, lsize, per, droop = TREES[species]
    r0, h0 = BASE[species]
    trunk_r *= 0.85 + 0.3 * _u(key, "trunk")
    lean = (0.25 * (_u(key, "lx") - 0.5), 0.25 * (_u(key, "ly") - 0.5))
    pts = _envelope(kind, r0, h0, bottom, width, npts, key)
    pts = [(x + lean[0] * z / h0 * 2.0, y + lean[1] * z / h0 * 2.0, z) for x, y, z in pts]
    nodes, parents = colonize(pts, (0.0, 0.0, 0.0), h0 * bottom * (0.7 + 0.2 * _u(key, "tt")),
                              STEP, INFLUENCE, KILL)
    if droop > 0.0:
        # drooping twigs: outer nodes pulled down by their distance from the trunk
        nodes = [(x, y, z - droop * max(0.0, math.sqrt(x * x + y * y) - r0 * 0.4) * 0.5)
                 for x, y, z in nodes]
    radii = _radii(parents, TIP_R, trunk_r)
    _skeleton_mesh(m, nodes, parents, radii, bark, key)
    _leaves(m, nodes, parents, radii, leaf, lsize, per, key)
    # a flare at the trunk's foot
    lathe(m, bark, [(trunk_r * 1.5, -0.05), (trunk_r * 1.15, 0.25), (trunk_r, 0.6)], 8,
          caps=False)


def _skeleton_mesh(m: Mesh, nodes, parents, radii, bark: str, key) -> None:
    for ci, ch in enumerate(_chains(parents, radii)):
        # drop the twig ends too thin to draw; never shorter than two points
        keep = [i for i in ch if radii[i] >= 0.015]
        if len(keep) < 2:
            continue
        pts = [nodes[i] for i in keep]
        rr = [radii[i] for i in keep]
        if parents[keep[0]] >= 0 and keep[0] != 0:
            # a side branch starts a little out of its parent, so its first ring sits clear
            d = norm(sub(pts[1], pts[0]))
            pts[0] = add(pts[0], mul(d, min(rr[0], 0.05)))
        sides = 6 if rr[0] > 0.06 else 4
        tube(m, bark, pts, rr, sides, caps=True, phase=0.37 * ci)


CARD = 0.65            # a card's half side, as a share of its clump's size
CARD_UV = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))   # the whole leaf tile (1 m)


def _card(m: Mesh, slot: str, c, a, b, n3, ha: float, hb: float) -> None:
    quad_out(m, slot, add(c, add(mul(a, -ha), mul(b, -hb))), add(c, add(mul(a, ha), mul(b, -hb))),
             add(c, add(mul(a, ha), mul(b, hb))), add(c, add(mul(a, -ha), mul(b, hb))), n3,
             CARD_UV)


def _clump(m: Mesh, slot: str, c, n3, size: float, key) -> None:
    """A clump of leaves round c facing n3: two crossed alpha-cut cards (the second tipped
    60 degrees about the first's axis), turned by a hash in their plane."""
    n3 = norm(n3)
    a = norm(cross(n3, (0.0, 0.0, 1.0) if abs(n3[2]) < 0.95 else (1.0, 0.0, 0.0)))
    b = cross(n3, a)
    t = 2.0 * M.PI * _u(key, "t")
    ct, st = M.cos(t), M.sin(t)
    a, b = add(mul(a, ct), mul(b, st)), add(mul(b, ct), mul(a, -st))
    h = size * CARD
    _card(m, slot, c, a, b, n3, h, h)
    b2 = add(mul(b, 0.5), mul(n3, 0.866))
    _card(m, slot, c, a, b2, cross(a, b2), h, h * 0.8)


def _leaves(m: Mesh, nodes, parents, radii, slot: str, size: float, per: int, key) -> None:
    """Leaf clumps round the twigs: `per` per twig node, pushed out from the trunk's axis,
    facing outward and up; the inner ones in the darker tone of the species."""
    n = len(nodes)
    for i in range(1, n):
        if radii[i] > 0.045:
            continue
        p = nodes[i]
        q = nodes[parents[i]]
        d0 = norm(sub(p, q))
        rad = math.sqrt(p[0] * p[0] + p[1] * p[1])
        out = norm((p[0], p[1], 0.0)) if rad > 0.05 else (1.0, 0.0, 0.0)
        for j in range(per):
            a = 2.0 * M.PI * _u(key, "la", i, j)
            off = size * (0.6 + 0.9 * _u(key, "lo", i, j))
            c = add(add(q, mul(sub(p, q), _u(key, "lp", i, j))),
                    (off * M.cos(a), off * M.sin(a), off * (0.5 * _u(key, "lz", i, j) - 0.15)))
            facing = norm(add(add(mul(out, 0.8), (0.0, 0.0, 0.9)),
                              (M.cos(a) * 0.7, M.sin(a) * 0.7, _u(key, "lf", i, j) - 0.5)))
            facing = add(facing, mul(d0, 0.3))
            sz = size * (1.6 + 1.2 * _u(key, "ls", i, j))
            tone = slot if (rad > 0.55 * size * 6 or _u(key, "tone", i, j) < 0.55) else slot + ".d"
            _clump(m, tone, c, facing, sz, (*key, "c", i, j))


# ---------------------------------------------------------------------------------------
# conifers, palms
# ---------------------------------------------------------------------------------------

def pine(m: Mesh, key) -> None:
    r0, h0 = BASE["pine"]
    lathe(m, "bark.dark", [(0.26, 0.0), (0.2, 0.6), (0.06, h0 * 0.95), (0.0, h0)], 7)
    z = h0 * (0.18 + 0.08 * _u(key, "z0"))
    whorl = 0
    while z < h0 * 0.94:
        t = (z - h0 * 0.15) / (h0 * 0.85)
        reach = r0 * (1.0 - t) * (0.85 + 0.3 * _u(key, "wr", whorl)) + 0.25
        nb = 5 + int(3 * _u(key, "nb", whorl))
        for b in range(nb):
            a = 2.0 * M.PI * (b + _u(key, "ba", whorl, b)) / nb
            c, s = M.cos(a), M.sin(a)
            tip = (reach * c, reach * s, z - 0.25 * reach)
            mid = (reach * 0.5 * c, reach * 0.5 * s, z - 0.02)
            if reach > 0.8:
                tube(m, "bark.dark", [(0.0, 0.0, z), mid, tip], [0.045, 0.03, 0.012], 4,
                     phase=0.3 * b)
            # needle sprays: flat elongated tufts along the branch, two crossed
            for f in range(4):
                at = (reach * (0.2 + 0.25 * f) * c, reach * (0.2 + 0.25 * f) * s,
                      z - 0.08 * reach * f)
                L = 1.1 * (1.0 - 0.15 * f) * (0.8 + 0.4 * (1.0 - t))
                d = norm((c, s, -0.35))
                for up in ((0.0, 0.0, 1.0), (-s, c, 0.0)):
                    _spray(m, "leaf.pine" if f % 2 else "leaf.pine.d", at, d, up, L, 0.45 * L,
                           True)
        z += 0.55 + 0.35 * _u(key, "dz", whorl)
        whorl += 1
    # the leader
    _spray(m, "leaf.pine", (0.0, 0.0, h0 * 0.92), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), 0.9, 0.3,
           True)
    _spray(m, "leaf.pine", (0.0, 0.0, h0 * 0.92), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0), 0.9, 0.3,
           True)


def _spray(m: Mesh, slot: str, base, d, up, L: float, w: float, card: bool = False) -> None:
    """A flat tuft from `base` along d (L long, w wide): a solid outline (palm leaflets),
    or with `card` an alpha-cut card of needles."""
    s = norm(cross(d, up))
    n = cross(s, d)
    if card:
        _card(m, slot, add(base, mul(d, L / 2.0)), d, s, n, L / 2.0, w / 2.0)
        return
    pts = [add(base, add(mul(d, u), mul(s, v))) for u, v in
           ((0.0, 0.0), (L * 0.3, -w * 0.5), (L * 0.8, -w * 0.35), (L, 0.0), (L * 0.8, w * 0.35),
            (L * 0.3, w * 0.5))]
    fan(m, slot, add(base, mul(d, L * 0.45)), pts[1:] + pts[:1], n)


def palm(m: Mesh, species: str, key) -> None:
    r0, h0 = BASE[species]
    fan_kind = species == "fan_palm"
    rb = 0.2 if fan_kind else 0.32
    bend = (0.6 * (_u(key, "bx") - 0.5), 0.6 * (_u(key, "by") - 0.5))
    pts, rr = [], []
    nseg = 10
    top = h0 * 0.86
    for i in range(nseg + 1):
        t = i / nseg
        pts.append((bend[0] * t * t * h0 * 0.1, bend[1] * t * t * h0 * 0.1, top * t))
        rr.append(rb * (1.0 - 0.3 * t) * (1.0 + (0.08 if i % 2 else 0.0)))
    tube(m, "bark.palm", pts, rr, 7)
    crown = pts[-1]
    nf = (16 if fan_kind else 14) + int(4 * _u(key, "nf"))
    for f in range(nf):
        a = 2.0 * M.PI * (f + 0.5 * _u(key, "fa", f)) / nf
        c, s = M.cos(a), M.sin(a)
        up_t = 0.15 + 0.9 * _u(key, "fu", f)          # from drooping to rising
        L = r0 * (0.9 + 0.25 * _u(key, "fl", f))
        if fan_kind:
            stalk_end = add(crown, (c * L * 0.45, s * L * 0.45, L * 0.35 * (up_t - 0.3)))
            tube(m, "bark.palm", [crown, stalk_end], [0.04, 0.02], 4)
            d = norm((c, s, up_t - 0.35))
            side = (-s, c, 0.0)
            # the fan faces out along its stalk, pleated (ridges and valleys alternate)
            w = norm(cross(side, d))
            if w[2] < 0.0:
                w = mul(w, -1.0)
            blade = []
            for j in range(13):
                b = -1.35 + 2.7 * j / 12
                rad = L * 0.55 * (0.8 + 0.2 * _u(key, "fr", f, j))
                pleat = (0.07 if j % 2 else -0.05) * rad
                blade.append(add(stalk_end, add(add(mul(w, rad * M.cos(b) * 0.9),
                                                    mul(side, rad * M.sin(b))),
                                                mul(d, pleat + 0.15 * rad * (1.0 - M.cos(b))))))
            fan(m, "foliage.palm" if f % 3 else "foliage.palm.d", stalk_end, blade, d)
        else:
            # a pinnate frond: an arching rachis with leaflets on both sides
            rach = []
            for j in range(7):
                t = j / 6
                rach.append(add(crown, (c * L * t, s * L * t,
                                        L * (0.5 * t * (up_t + 0.2) - 0.55 * t * t * (1.2 - up_t)))))
            tube(m, "bark.palm", rach, [0.035, 0.03, 0.025, 0.02, 0.015, 0.012, 0.01], 4)
            side = (-s, c, 0.0)
            for j in range(1, 7):
                p0, p1 = rach[j - 1], rach[j]
                d = norm(sub(p1, p0))
                for sg in (-1.0, 1.0):
                    ll = L * 0.42 * (1.0 - 0.6 * (j / 6) ** 2)
                    dd = norm(add(mul(side, sg), mul(d, 0.5)))
                    dd = (dd[0], dd[1], dd[2] - 0.35)
                    _spray(m, "foliage.palm" if j % 2 else "foliage.palm.d", p0, norm(dd),
                           (0.0, 0.0, 1.0), ll, 0.22)
    # dead frond skirt and the crown shaft
    lathe(m, "bark.palm", [(rb * 0.75, top - 0.6), (rb * 1.25, top - 0.2), (rb * 0.6, top + 0.1)],
          7, crown[0], crown[1], caps=False)


# ---------------------------------------------------------------------------------------
# shrubs, sedum, scrub, ivy
# ---------------------------------------------------------------------------------------

def _blob(m: Mesh, slot: str, c, r: float, h: float, key, n: int = 9) -> None:
    prof = []
    for i in range(6):
        a = M.PI / 2.0 * i / 5
        rr = r * M.cos(a) * (0.85 + 0.3 * _u(key, "b", i))
        prof.append((rr if i < 5 else 0.0, c[2] + h * M.sin(a)))
    prof = [(r * 0.75, c[2])] + prof[1:]
    lathe(m, slot, prof, n, c[0], c[1])


def shrub(m: Mesh, key) -> None:
    r0, h0 = BASE["boxwood"]
    lobes = 3 + int(3 * _u(key, "n"))
    for i in range(lobes):
        a = 2.0 * M.PI * (i + _u(key, "a", i)) / lobes
        d = r0 * 0.45 * _u(key, "d", i)
        c = (d * M.cos(a), d * M.sin(a), 0.0)
        _blob(m, "foliage.boxwood", c, r0 * (0.45 + 0.3 * _u(key, "r", i)),
              h0 * (0.55 + 0.4 * _u(key, "h", i)), (*key, i))
    # leaf cards over the lobes so the outline is not smooth
    for j in range(16):
        a = 2.0 * M.PI * _u(key, "la", j)
        rr = r0 * (0.4 + 0.5 * _u(key, "lr", j))
        z = h0 * (0.35 + 0.6 * _u(key, "lz", j)) * (1.0 - 0.45 * (rr / r0) ** 2)
        c = (rr * M.cos(a), rr * M.sin(a), z)
        _clump(m, "leaf.boxwood", c, (M.cos(a), M.sin(a), 0.7), 0.42, (*key, "lc", j))


def sedum(m: Mesh, key) -> None:
    r0, h0 = BASE["sedum"]
    slot = "foliage.sedum" if _u(key, "col") < 0.65 else "foliage.sedum_red"
    pts = [(r0 * (0.85 + 0.25 * _u(key, "o", i)) * c, r0 * (0.85 + 0.25 * _u(key, "o", i)) * s,
            0.02) for i, (c, s) in enumerate(ring(10))]
    fan(m, slot, (0.0, 0.0, 0.06), pts, (0.0, 0.0, 1.0))
    for j in range(14):
        a = 2.0 * M.PI * _u(key, "ra", j)
        rr = r0 * 0.8 * math.sqrt(_u(key, "rr", j))
        c = (rr * M.cos(a), rr * M.sin(a), 0.03)
        petals = [(c[0] + 0.07 * cc, c[1] + 0.07 * ss, c[2] + 0.03) for cc, ss in ring(5, 0.4 * j)]
        fan(m, slot, (c[0], c[1], c[2] + 0.09), petals, (0.0, 0.0, 1.0))


def scrub(m: Mesh, key) -> None:
    r0, h0 = BASE["scrub"]
    slot = "foliage.scrub" if _u(key, "dry") < 0.7 else "foliage.dry"
    for j in range(36):
        a = 2.0 * M.PI * _u(key, "a", j)
        rr = r0 * math.sqrt(_u(key, "r", j))
        b = (rr * M.cos(a), rr * M.sin(a), 0.0)
        h = h0 * (0.4 + 0.8 * _u(key, "h", j))
        lean = 0.35 * _u(key, "l", j)
        tip = (b[0] + lean * M.cos(a), b[1] + lean * M.sin(a), h)
        w = 0.05
        side = (-M.sin(a) * w, M.cos(a) * w, 0.0)
        nrm = norm(cross(side, sub(tip, b)))
        fan(m, slot, add(b, mul(sub(tip, b), 0.3)), [sub(b, side), add(b, side), tip],
            nrm if nrm[2] >= 0 else mul(nrm, -1.0))
    for i in range(2):
        a = 2.0 * M.PI * _u(key, "ba", i)
        _blob(m, slot, (0.3 * M.cos(a), 0.3 * M.sin(a), 0.0), r0 * 0.35, h0 * 0.5, (*key, "bb", i), 7)


def ivy(m: Mesh, key) -> None:
    """A patch of ivy on a facade: 1.5 m along x, 2 m up (z 0 at the plant's position), on
    the wall plane 0.25 m behind it (y = 0 is the facade side M6 puts it on: the leaves face
    out of the wall, toward -y and +y both, as M6 does not record which)."""
    w, h0 = 1.5, BASE["ivy"][1]
    stems = 3 + int(2 * _u(key, "s"))
    for i in range(stems):
        x0 = -w / 2.0 + w * (i + 0.5) / stems
        pts = []
        for j in range(7):
            t = j / 6
            pts.append((x0 + 0.15 * M.sin(3.0 * t + 6.0 * _u(key, "p", i)), 0.0, h0 * t * (0.7 + 0.3 * _u(key, "hh", i))))
        tube(m, "bark.dark", pts, 0.012, 3)
    # leaf cards flat on the wall on both sides, overlapping, turned by a hash
    for j in range(14):
        x = -w / 2.0 + w * (0.08 + 0.84 * _u(key, "x", j))
        z = h0 * (0.12 + 0.8 * _u(key, "z", j) ** 0.8)
        side = 1.0 if j % 2 else -1.0
        t = 2.0 * M.PI * _u(key, "a", j)
        a = (M.cos(t), 0.0, M.sin(t))
        b = (-M.sin(t), 0.0, M.cos(t))
        h = 0.32 + 0.12 * _u(key, "sz", j)
        _card(m, "leaf.ivy", (x, side * (0.03 + 0.03 * _u(key, "y", j)), z), a, b,
              (0.0, side, 0.0), h, h)
