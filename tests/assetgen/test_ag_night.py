"""AG15's facades and night on small made-up briefs: the new parts closed, window patterns
inside their bays, AG15's systems built closed and inside their envelope, genomes that reach
further in the corporate core, the neighbor rule (towers within 150 m differ in system,
pattern, palette and night look), the night by schedule (offices in bands, vacant towers
dark), day and night thumbnails, crown lights and logos on towers, and the night's Custom
Primitive Data."""

import copy

from assetgen import asset_checks as AC
from assetgen import build as BD
from assetgen.buildings import genome as GN
from assetgen.buildings import meshbuf as MB
from assetgen.buildings import neighbors as NB
from assetgen.buildings import night as NT
from assetgen.buildings import parts as PT
from assetgen.buildings import skins as SK
from assetgen.buildings import systems as SY
from assetgen.buildings import thumb as TH

from test_ag_shell import brief_of, mass, rect

SAMPLE = {
    "led": {"dir": "v", "L": 30000, "t": 60, "slot": "led_05d9e8"},
    "hex": {"w": 2400, "h": 2600, "c": 600, "t": 70, "d": 120},
    "fold": {"w": 2400, "h": 2600, "d": 450, "off": 600},
    "mesh": {"w": 2600, "h": 3100, "off": 300},
    "media": {"w": 24000, "h": 12000, "slot": "screen_media_a"},
    "frit": {"w": 2400, "h": 1000, "r": 100},
    "logo": {"w": 8000, "h": 4400, "slot": "led_ff2a6d", "style": "ring"},
}
CORP = {"systems": {"unitized_curtain_wall": 0.5, "fin_wall": 0.3, "precast_panel": 0.2},
        "palette": ["#c9ced2", "#2a3440", "#7a8590", "#1c2028"], "crowns": ["flat"],
        "window_to_wall": [0.5, 0.9], "bay_m": [2.8, 4.2], "wear": 0.2,
        "signage_scripts": {"latin": 1.0}}


def _closed(arrs):
    ck = MB.check(arrs)
    return ck["triangles"] > 0 and ck["degenerate"] == ck["duplicate"] == \
        ck["open_edges"] == ck["bad_edges"] == 0


def tower(bid="d01.lot.e0n0.bld", x=0.0, y=0.0, arch="corporate_core", use="office",
          h=96.0):
    tw = rect(-12.0, -10.0, 12.0, 10.0)
    br = brief_of([mass(rect(-20.0, -16.0, 20.0, 16.0), 0.0, 12.0, 3, role="podium"),
                   mass(tw, 12.0, h, int((h - 12.0) / 3.5), role="tower")],
                  btype="building.podium_tower", bid=bid, era=CORP)
    br["origin"] = [x, y]
    br["building"]["use"] = use
    br["building"]["style"]["era"] = "corporate_glass"
    br["building"]["form"] = {"kind": "box", "tower": True, "band": 3, "crown": "flat",
                              "masses": [1], "params": {}, "pivot": [0.0, 0.0]}
    br["spec"]["era"] = "corporate_glass"
    br["district"] = {"id": "d01", "name": "Core", "archetype": arch, "wealth": 0.8,
                      "danger": 0.2}
    return br


def test_ag15_parts_are_closed():
    assert set(SAMPLE) == set(SK.FAMILIES)
    for fam, p in SAMPLE.items():
        _, arrs = PT.mesh(fam, p)
        assert _closed(arrs), fam
        assert PT.REACH[fam] in ("flush", "strip")
    # the LED, media and logo parts glow (the neon master), so the night thumbnail sees them
    for fam in ("led", "media", "logo"):
        _, arrs = PT.mesh(fam, SAMPLE[fam])
        assert any(SY.SLOTS[s][0] == "neon" for s in arrs), fam
    # a honeycomb panel has its holes
    _, arrs = PT.mesh("hex", SAMPLE["hex"])
    assert len(SK._hexes(2400, 2600, 600, 70)) >= 6


def test_patterns_keep_to_their_bays():
    cuts = [(1000, 4000), (4000, 7000), (7000, 10000)]
    ops = [(1800, 3200, "glass", 0), (4800, 6200, "glass", 1), (7800, 9200, "glass", 2)]
    seen = {}
    for pat in SY.PATTERNS:
        for f in range(4):
            out = SK.pattern_ops(pat, ops, f, cuts, "k", False, "single")
            for a, b, back, jb in out:
                b0, b1 = cuts[jb]
                assert b0 <= a < b <= b1 and b - a >= 350, (pat, f)
            seen.setdefault(pat, set()).add(tuple(out))
    assert len(seen["grid"]) == 1
    for pat in ("stagger", "stepped", "checker", "alternate"):
        assert len(seen[pat]) > 1, pat           # floors differ: not a grid
    # a checkerboard leaves out every other opening, offset by floor
    assert len(SK.pattern_ops("checker", ops, 0, cuts, "k", False, "single")) == 2
    assert len(SK.pattern_ops("checker", ops, 1, cuts, "k", False, "single")) == 1
    # a ribbon is left as it is
    assert SK.pattern_ops("stagger", ops, 1, cuts, "k", False, "ribbon") == ops


def test_ag15_systems_build_closed_inside_their_envelope():
    for s in SY.AG15_SYSTEMS:
        br = tower()
        gm = GN.make(br)
        for g in GN.GROUPS:
            gm["genes"][f"{g}.system"] = s
            T = SY.SYSTEMS[s]
            gm["genes"][f"{g}.window"] = T["windows"][0]
            gm["genes"][f"{g}.frame"] = T["frames"][0]
        gm["genes"]["crown_light"] = "both"
        gm["genes"]["logo"] = "logo"
        sh, _, rec = BD.building_asset(br, gm)
        ck = rec["checks"]["mesh"]
        assert ck["degenerate"] == ck["duplicate"] == ck["open_edges"] == \
            ck["bad_edges"] == 0, s
        env = rec["checks"]["envelope"]
        assert env["outside"] == env["too_high"] == env["low_overhang"] == 0, (s, env)
        feat = SY.SYSTEMS[s]["feature"]
        fams = {x["family"] for x in sh["parts"]} | set(sh["arrays"])
        want = {"led": "led", "hex": "hex", "fold": "fold", "mesh": "mesh",
                "media": "media", "diag": "member"}.get(feat)
        if want is not None:
            placed = {x["family"] for x in sh["parts"]}
            merged = sh["stats"].get("parts_merged", 0)
            assert want in placed or merged > 0, s
        assert sh["stats"].get("crown_lights", 0) > 0, s
        assert rec["ag15"]["tower"] and rec["ag15"]["night_thumb"], s
        assert fams


def test_genomes_reach_further_in_the_core():
    def ag15_share(arch):
        n = 0
        for k in range(120):
            br = tower(bid=f"d01.lot.e{k}n0.bld", arch=arch)
            g = GN.make(br)["genes"]
            n += g["body.system"] in SY.AG15_SYSTEMS or g["body.wpattern"] != "grid"
        return n / 120.0
    assert ag15_share("corporate_core") > ag15_share("old_town") + 0.25
    br = tower()
    g = GN.make(br)["genes"]
    for gene in ("skin", "accent", "crown_light", "logo", "light", "body.wpattern"):
        assert gene in g
    assert GN.make(copy.deepcopy(br)) == GN.make(br)


def test_neighbor_rule_draws_neighboring_towers_apart():
    briefs = {}
    for k in range(12):
        b = tower(bid=f"d01.lot.e{k * 30}n0.bld", x=k * 30.0, y=0.0)
        briefs[b["id"]] = b
    genomes = {b: GN.make(briefs[b]) for b in sorted(briefs)}
    avoided = NB.assign(briefs, genomes)
    assert avoided                                  # (twelve towers 30 m apart: some clash)
    sig = {b: NB.signature(genomes[b]) for b in briefs}
    ids = sorted(briefs)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if abs(briefs[a]["origin"][0] - briefs[b]["origin"][0]) <= NB.RADIUS_M:
                for kind in NB.KINDS:
                    assert sig[a][kind] != sig[b][kind], (a, b, kind)
    # what a tower avoided is in its record, and the check reads the records
    recs = {}
    for b in ids:
        sh, _, rec = BD.building_asset(briefs[b], genomes[b])
        recs[b] = rec
    nb = AC.neighbor_rule(recs)
    assert nb["towers"] == 12 and nb["pairs"] > 0 and nb["failures"] == 0, (nb["same"], nb["first"])


def test_a_hero_draws_past_its_neighbors_systems():
    """#88: a landmark's (or a type's) system drawn from its kind's weights is drawn again
    past the systems its neighboring towers took, within those weights (Nexus City's spire
    went after a taller tower beside it that had its curtain wall); the rest of the rule as
    before."""
    br = tower(bid="d01.lm.w98n1260.bld", h=166.0)
    br["building"]["type"] = "building.landmark.spire"
    first = GN.make(br)["genes"]["body.system"]
    opts = set(SY.LANDMARK_SYSTEM["spire"])
    assert first in opts
    none = {k: set() for k in NB.KINDS}
    gm = GN.make(br, dict(none, system={first}, vacant=False))
    assert gm["genes"]["body.system"] in opts - {first}
    # every option taken: it keeps its own
    gm = GN.make(br, dict(none, system=set(opts), vacant=False))
    assert gm["genes"]["body.system"] == first


def test_regeneration_holds_the_towers_outside_its_district():
    """#90: in a city a district regeneration made (its build state's edits), the towers
    outside that district whose briefs are unchanged keep their genomes (drawn again past
    what their records say they avoided), and the district's new towers avoid them."""
    from assetgen import brief as B

    def city(two_salt):
        briefs = {}
        for k in range(12):
            d = ("d01", "One") if k < 6 else ("d02", "Two")
            # (the second district's towers are the taller: they go first, so what they draw
            # moves the first district's draws when nothing holds them)
            b = tower(bid=f"{d[0]}.lot.e{k * 30}n{two_salt if k >= 6 else 0}.bld",
                      x=k * 30.0, y=0.0, h=96.0 + (40.0 if k >= 6 else 0.0) + k)
            b["district"] = {"id": d[0], "name": d[1], "archetype": "corporate_core",
                             "wealth": 0.8, "danger": 0.2}
            b["building"]["district_id"] = d[0]
            briefs[b["id"]] = b
        return briefs

    old = city(0)
    og = {b: GN.make(old[b]) for b in sorted(old)}
    oav = NB.assign(old, og)
    recs = {b: {"brief": B.brief_hash(old[b]),
                "ag15": {"tower": True, "avoided": oav.get(b)}} for b in old}
    new = city(7)                                   # (Two regenerated: other towers there)
    hashes = {b: B.brief_hash(new[b]) for b in new}
    names = {"One": "d01", "Two": "d02"}
    state = {"edits": [{"district": "Two"}]}
    held = NB.held_towers(new, hashes, recs, state, names)
    assert sorted(held) == sorted(b for b in new if b.startswith("d01."))
    ng = {b: GN.make(new[b]) for b in sorted(new)}
    nav = NB.assign(new, ng, held)
    for b in held:
        assert ng[b] == og[b] and nav.get(b) == oav.get(b), b
    sig = {b: NB.signature(ng[b]) for b in new}
    ids = sorted(new)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if abs(new[a]["origin"][0] - new[b]["origin"][0]) <= NB.RADIUS_M:
                for kind in NB.KINDS:
                    assert sig[a][kind] != sig[b][kind], (a, b, kind)
    # without the hold the first district's towers would have moved
    free = {b: GN.make(new[b]) for b in sorted(new)}
    NB.assign(new, free)
    assert any(free[b] != og[b] for b in held)
    # a fresh city (no edits), a record from before the rule (no `avoided`), a changed brief
    # or the last edit's own district: nothing held
    assert NB.held_towers(new, hashes, recs, {"edits": []}, names) == {}
    bare = {b: {"brief": r["brief"], "ag15": {"tower": True}} for b, r in recs.items()}
    assert NB.held_towers(new, hashes, bare, state, names) == {}
    one = next(iter(sorted(held)))
    moved = dict(hashes, **{one: "other"})
    assert one not in NB.held_towers(new, moved, recs, state, names)
    assert NB.held_towers(new, hashes, recs, {"edits": [{"district": "One"}]}, names) == {}


def test_night_by_schedule():
    # offices: a whole band of floors on or off
    on = [[NT.lit(0.123, 0.6, 1, 3, c, f, 21.0) > 0 for c in range(40)] for f in range(30)]
    bands = [any(on[f]) for f in range(30)]
    for f in range(30):
        if not bands[f]:
            assert not any(on[f])
    assert any(bands) and not all(bands)
    # vacant towers keep a few security lights
    vac = sum(NT.lit(0.5, 0.6, 6, 3, c, f) > 0 for c in range(40) for f in range(40))
    home = sum(NT.lit(0.5, 0.6, 2, 3, c, f) > 0 for c in range(40) for f in range(40))
    assert vac < 0.08 * 1600 < home
    # by hour: offices empty out late, homes fill
    off_day = sum(NT.lit(0.2, 0.6, 1, 3, c, f, 12.0) > 0 for c in range(20) for f in range(40))
    off_late = sum(NT.lit(0.2, 0.6, 1, 3, c, f, 23.0) > 0 for c in range(20) for f in range(40))
    assert off_late < off_day
    # the CPD's night: color, schedule, spread, band
    gm = GN.make(tower(use="hotel"))
    v = NT.cpd(gm)
    assert len(v) == 6 and v[3] in (float(SY.SCHEDULES["hotel"]), float(SY.SCHEDULES["vacant"]))
    from assetgen.materials import params as MP
    rec = {"bay_m": 3.0, "floor_m": 3.5, "bounds": [[0, 0, 0], [1, 1, 96.0]]}
    ext = MP.building(tower(), gm, rec)["cpd"]
    assert len(SY.CPD_TINT) and 23 + len(ext) == 36          # (Unreal's 36 floats)


def test_night_thumbnail_differs_from_day():
    br = tower()
    gm = GN.make(br)
    sh, _, rec = BD.building_asset(br, gm)
    assert rec["ag15"]["night_thumb"] != rec["thumb"]
    night = {"seed": 0.3, "share": 0.6, "schedule": 1, "band": 3, "color": [1.0, 0.8, 0.6],
             "room_mm": 3000.0, "floor_mm": 3500.0}
    a = TH.render(br, sh["arrays"], sh["parts"], rec["tints"], night)
    night["schedule"] = 6
    b = TH.render(br, sh["arrays"], sh["parts"], rec["tints"], night)
    assert int(a.astype(int).sum()) > int(b.astype(int).sum())    # vacant: darker
