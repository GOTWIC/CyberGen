"""Asset spec: structure, era presets, names against a city, schemas, CLI."""

import json

from assetgen import presets as P
from assetgen import spec as S
from assetgen.cli import EXIT_INVALID, EXIT_OK, EXIT_USAGE, main

from agtools import ROOT, write


def test_empty_spec_is_all_presets():
    res = S.validate_spec({})
    assert res.ok
    f = res.filled
    assert sorted(f.eras) == sorted(P.ERAS)
    for era in P.ERAS:
        assert f.eras[era].systems == P.ERA_PRESETS[era]["systems"]
    assert f.uniqueness == "U1" and f.hero_uniqueness == "U2"
    assert f.min_gene_distance == 4 and f.share_parts and f.texel_density_px_m == 512


def test_every_preset_system_is_known():
    for era, p in P.ERA_PRESETS.items():
        assert set(p["systems"]) <= set(P.FACADE_SYSTEMS), era
        assert set(p["crowns"]) <= set(P.CROWNS), era
        assert set(p["signage_scripts"]) <= set(P.SCRIPTS), era


def test_scope_example_validates_and_fills():
    data = {"city": "Vesper Bay", "uniqueness": "U1", "texel_density_px_m": 512,
            "eras": {"corporate_glass": {"systems": {"unitized_curtain_wall": 0.5,
                                                     "fin_wall": 0.2, "diagrid": 0.1,
                                                     "spandrel_ribbon": 0.2},
                                         "palette": ["#1b2430", "#9fb4c7", "#c9d2da"],
                                         "crowns": ["lantern", "halo", "mast"]},
                     "heritage": {"systems": {"punched_brick": 0.4, "stucco_shutters": 0.3,
                                              "timber_infill": 0.1, "tiled_eaves": 0.2},
                                  "signage_scripts": {"hanzi": 0.5, "latin": 0.3,
                                                      "hangul": 0.2}}},
            "districts": {"Neon Strand": {"wear": 1.2, "ad_density": 1.5,
                                          "neon_palette": ["#ff2a6d", "#05d9e8"]}},
            "owners": {"Kessler Dynamics": {"brand_colors": ["#e8e8e8", "#c1121f"],
                                            "logo": "logos/kessler.svg",
                                            "facade_bias": {"fin_wall": 0.6}}},
            "landmarks": {"Corporate Core Megatower": {
                "brief": "black glass arms, red light seams, crown halo"}}}
    res = S.validate_spec(data)
    assert res.ok, [str(i) for i in res.issues]
    # a field given replaces the preset's, the rest stays
    assert res.filled.eras["heritage"].palette == P.ERA_PRESETS["heritage"]["palette"]
    assert res.filled.eras["corporate_glass"].crowns == ["lantern", "halo", "mast"]


def test_structural_errors():
    res = S.validate_spec({"eras": {"heritag": {}}, "districts": {"A": {"wear": 9}},
                           "owners": {"X": {"brand_colors": ["red"]}},
                           "eras2": 1})
    assert not res.ok
    text = "\n".join(str(i) for i in res.issues)
    assert "eras.heritag (key)" in text
    assert "districts.A.wear" in text
    assert "owners.X.brand_colors[0]" in text
    assert "eras2" in text


def test_weights_and_ranges():
    assert not S.validate_spec({"eras": {"heritage": {"systems": {"punched_brick": 0}}}}).ok
    assert not S.validate_spec({"eras": {"heritage": {"window_to_wall": [0.5, 0.2]}}}).ok
    assert S.validate_spec({"eras": {"heritage": {"window_to_wall": [0.2, 0.5]}}}).ok


class _Fake:
    """The few model fields the name checks read."""
    class D:
        def __init__(self, n):
            self.name = n

    class Pr:
        def __init__(self, o):
            self.owner = o

    class B:
        def __init__(self, n):
            self.name, self.landmark = n, True

    def __init__(self):
        self.name = "Vesper Bay"
        self.districts = [self.D("Neon Strand"), self.D("Old Town")]
        self.properties = [self.Pr("tessera")]
        self.buildings = [self.B("Corporate Core Megatower")]


def test_names_against_a_city():
    m = _Fake()
    ok = S.validate_spec({"city": "Vesper Bay", "districts": {"Old Town": {}},
                          "owners": {"tessera": {}},
                          "landmarks": {"Corporate Core Megatower": {}}}, m)
    assert ok.ok and not ok.issues
    bad = S.validate_spec({"city": "Other", "districts": {"Old Twn": {}},
                           "owners": {"nobody": {}}}, m)
    assert not bad.ok
    text = "\n".join(str(i) for i in bad.issues)
    assert "did you mean 'Old Town'" in text
    assert "owners.nobody" in text
    assert "warning: city" in text


def test_overrides_by_id():
    ov = S.AssetOverrides.model_validate({"pin": ["a.bld"], "style": {"a.bld": {"crown": "halo"}},
                                          "regenerate": {"b.bld": 7}})
    assert S.overrides_by_id(ov) == {"a.bld": {"pin": True, "style": {"crown": "halo"}},
                                     "b.bld": {"regenerate": 7}}


def test_committed_schemas_are_current():
    """assetgen/schemas/*.json must match the models (regenerate with `assetgen spec schema
    assetgen/schemas/asset_spec.schema.json` and `assetgen brief schema
    assetgen/schemas/brief.schema.json`)."""
    from assetgen.briefmodel import json_schema as brief_schema
    sdir = ROOT / "assetgen" / "schemas"
    assert json.loads((sdir / "asset_spec.schema.json").read_text()) == S.json_schema()
    assert json.loads((sdir / "brief.schema.json").read_text()) == brief_schema()


def test_cli(tmp_path, capsys):
    p = write(tmp_path, {"districts": {"Neon Strand": {"wear": 1.2}}}, "s.json")
    out = tmp_path / "filled.json"
    assert main(["spec", "validate", str(p), "--filled", str(out)]) == EXIT_OK
    assert json.loads(out.read_text())["eras"]["heritage"]["systems"]
    assert "OK:" in capsys.readouterr().out
    bad = write(tmp_path, {"uniqueness": "U9"}, "b.json")
    assert main(["spec", "validate", str(bad)]) == EXIT_INVALID
    assert main(["spec", "validate", str(tmp_path / "nope.json")]) == EXIT_USAGE
    assert main(["spec", "schema", str(tmp_path / "s.schema.json")]) == EXIT_OK
    assert main(["nothing"]) == EXIT_USAGE
