"""M3p (polish of M3): megablocks as separate towers on podiums, complexes built on their own
merged groups, straddle buildings over canals, the boulevard ridge, and the M1b
`_merge_degree2` regression."""

import json

import pytest
from shapely.geometry import LineString

from citygen import buildings as BL
from citygen import geom as G
from citygen import massing as MS
from citygen import roads as RD
from citygen.build import build_city
from citygen.validate import load_spec

from conftest import CITIES, ROOT, ROUND_TIP, built_sample
from test_buildings import _mutate, _rerun

GREYHOOK = ROOT / "docs" / "progress" / "M1a2" / "peninsula_city" / "city_spec.json"


def _spec_data(path):
    return json.loads(path.read_text())


# --- megablocks --------------------------------------------------------------------------

def test_megablocks_are_towers_on_podiums():
    """Greyhook's The Stacks: megabuildings are a low podium with separate towers on it,
    at least 16 m apart, of stepped heights; the district has strong height contrast."""
    b, _, _ = built_sample(GREYHOOK)
    m = b.model
    did = next(d.id for d in m.districts if d.archetype == "megablock_residential")
    mega = [x for x in m.buildings if x.district_id == did and x.type == "building.megabuilding"]
    assert len(mega) >= 50
    stepped = 0
    for x in mega:
        pods = [ms for ms in x.masses if ms.role == "podium"]
        towers = [ms for ms in x.masses if ms.role == "tower" and pods and
                  ms.z0_m == pods[0].z1_m]
        assert pods and towers, x.id
        assert pods[0].z1_m <= 30.0 and x.height_m >= 120.0
        polys = [G.from_model_poly(t.footprint) for t in towers]
        for i, a in enumerate(polys):
            for c in polys[i + 1:]:
                assert G.dist(a, c) >= BL.MEGA_GAP_M - 0.6, x.id
        tops = {round(max(ms.z1_m for ms in x.masses if ms.role in ("tower", "crown") and
                          G.from_model_poly(ms.footprint).intersects(p)), 2) for p in polys}
        stepped += len(tops) > 1
    assert stepped >= 0.3 * len(mega)
    hs = sorted(x.height_m for x in m.buildings if x.district_id == did)
    assert hs[-1] - hs[len(hs) // 2] >= 60.0


def test_megablock_podium_decks():
    """Open decks join neighboring podiums at street scale (below the podium tops)."""
    b, _, _ = built_sample(GREYHOOK)
    m = b.model
    did = next(d.id for d in m.districts if d.archetype == "megablock_residential")
    bld = {x.id: x for x in m.buildings}
    low = [s for s in m.skybridges if s.kind == "open_deck" and s.z_m <= 30.0 and
           all(bld[i].district_id == did for i in s.building_ids)]
    assert len(low) >= 20


# --- complexes ---------------------------------------------------------------------------

def test_complexes_built_in_place():
    """Every merged lot group of the five samples is built where M2 grouped it (no complex
    moved to another block)."""
    total = moved = 0
    for path in CITIES:
        b, _, _ = built_sample(path)
        total += sum(1 for p in b.model.properties
                     if p.complex not in ("single", "landmark", "megasite"))
        moved += sum(1 for n in b.notes if "the merged group did not fit" in n)
    assert total >= 20
    assert moved <= 0.1 * total, f"{moved} of {total} complexes moved"


def test_straddle_over_a_canal():
    """Greyhook's straddle building spans a canal and its quay roads, at the canal's
    navigable clearance and 5.5 m over the roads (plus the 1 m structure)."""
    b, _, _ = built_sample(GREYHOOK)
    m = b.model
    ww = {w.id: w for w in m.waterways}
    spans = [(x, ms) for x in m.buildings for ms in x.masses if ms.role == "span"]
    assert spans
    x, span = next((x, ms) for x, ms in spans if x.attrs["span_over"] in ww)
    assert ww[x.attrs["span_over"]].kind == "canal"
    assert span.z0_m - 1.0 >= 5.5
    roads = [r for r in x.attrs["span_crosses"] if r.startswith("rs")]
    assert len(roads) == 2


def test_check_span_over_canal_fails_when_low():
    b, _, _ = built_sample(GREYHOOK)
    ww = {w.id for w in b.model.waterways}

    def fn(d):
        for x in d["buildings"]:
            if x["attrs"].get("span_over") in ww:
                for ms in x["masses"]:
                    if ms["role"] == "span":
                        h = ms["z1_m"] - ms["z0_m"]
                        ms["z0_m"], ms["z1_m"] = 3.0, 3.0 + h
                return

    assert not _rerun(_spec_data(GREYHOOK), _mutate(b.model, fn))["building_footprints"].passed


def test_check_span_fails_on_an_unlisted_road():
    b, _, _ = built_sample(GREYHOOK)

    def fn(d):
        for x in d["buildings"]:
            if "span_crosses" in x["attrs"]:
                x["attrs"]["span_crosses"] = [x["attrs"]["span_over"]]
                return

    assert not _rerun(_spec_data(GREYHOOK), _mutate(b.model, fn))["building_footprints"].passed


# --- boulevard ridge ---------------------------------------------------------------------

def test_boulevard_ridge():
    """Corporate towers near the boulevard (the avenue through the district center and its
    straight continuations) stand taller than the rest of the district."""
    path = ROOT / "docs" / "progress" / "M1a2" / "nexus_city" / "city_spec.json"
    b, _, _ = built_sample(path)
    m = b.model
    from citygen import buildout as BO

    job = next(j for j in BO.contexts(b.spec, m) if j["ctx"].archetype == "corporate_core")
    cx = job["ctx"]
    with G.canonical():
        axis = BL.boulevards(cx)
    assert axis
    near, far = [], []
    for x in m.buildings:
        if x.district_id != cx.did or x.landmark or x.footprint is None:
            continue
        c = G.centroid(G.from_model_poly(x.footprint))
        d = min(MS.line_dist(c, pts)[0] for pts in axis)
        (near if d < 60.0 else far).append(x.height_m)
    near.sort()
    far.sort()
    assert near and near[len(near) // 2] > far[len(far) // 2] * 1.3


# --- M1b regression: _merge_degree2 ----------------------------------------------------------

class _NoShortcut(RD.Fitter):
    """A fitter whose shortcuts never pass (so a sharp joint keeps its corner vertex)."""

    def __init__(self):
        pass

    def valid_shortcut(self, *a, **k):
        return False


def test_merge_degree2_keeps_a_collapsed_joint():
    """Two noding pieces a few cm long meeting at a sharp angle: the fillet of their joint
    shrinks under the 5 cm cleanup to an empty line, and the next pass used to read its
    first point (IndexError). The plain joint is kept instead."""
    la = LineString([(0.0, 0.0), (0.03, 0.0)])
    lb = LineString([(0.03, 0.0), (0.03, 0.03)])
    pieces = [(la, RD.Road("avenue", la, "r")), (lb, RD.Road("avenue", lb, "r"))]
    assert RD._smooth_joint(_NoShortcut(), list(la.coords), list(lb.coords), "avenue").is_empty
    out = RD._merge_degree2(pieces, _NoShortcut())
    assert len(out) == 1
    assert list(out[0][0].coords) == [(0.0, 0.0), (0.03, 0.0), (0.03, 0.03)]


def test_on_ends_snaps_a_drifted_end():
    """A smoothed joint that ends 3 cm off its node (the arc cleanup dropped the true end)
    is put back on the node; one that collapsed is refused."""
    ln = LineString([(987.5, -537.5), (412.64, -537.55), (412.53, -537.53), (412.42, -537.54)])
    out = RD._on_ends(ln, (987.5, -537.5), (412.39, -537.55))
    assert list(out.coords)[0] == (987.5, -537.5) and list(out.coords)[-1] == (412.39, -537.55)
    assert RD._on_ends(LineString(), (0, 0), (1, 1)) is None


def test_merge_degree2_smooths_a_normal_joint():
    """A joint of ordinary pieces is still refitted as a curve that ends on both nodes."""
    la = LineString([(0.0, 0.0), (200.0, 0.0)])
    lb = LineString([(200.0, 0.0), (200.0, 200.0)])
    pieces = [(la, RD.Road("avenue", la, "r")), (lb, RD.Road("avenue", lb, "r"))]

    class Ok(_NoShortcut):
        def valid_shortcut(self, *a, **k):
            return True

    (line, _), = RD._merge_degree2(pieces, Ok())
    assert len(line.coords) > 3
    assert G.qpoint(line.coords[0]) == (0.0, 0.0) and G.qpoint(line.coords[-1]) == (200.0, 200.0)


def test_merge_degree2_keeps_nodes_on_greyhook_seed_5(monkeypatch):
    """Greyhook's earlier layout with seed 5 (found by building the samples' roads over seeds
    and road variants): a smoothed joint used to end 3 cm off its node, so merging made a new
    dead end there (later dropped as a dangle, taking a road piece with it). Merging must keep
    every other node with its degree."""
    from citygen import build as B
    from citygen import megasites as MSI
    from citygen.validate import validate_spec

    data = _spec_data(ROUND_TIP)
    data["seed"] = 5
    real = RD._merge_degree2
    moved = []

    def checked(pieces, fitter=None):
        before = RD._endpoints(pieces)
        out = real(pieces, fitter)
        moved.extend(c for c, d in RD._endpoints(out).items() if before.get(c) != d)
        return out

    monkeypatch.setattr(RD, "_merge_degree2", checked)
    b = B.build_city(validate_spec(data), max_variants=2, roads=False, workers=1)
    s = b.spec
    did = B._district_ids(s)
    sites, _ = MSI.place_megasites(s, b.layout.polygons, b.hydro, b.waterways, did)
    opens = [G.from_model_poly(o.polygon) for o in b.model.open_spaces]
    net = RD.build_roads(s, b.hydro, b.layout.polygons, did, b.waterways, sites, opens,
                         variant=0)
    assert net.segments
    assert not moved, moved
