"""CLI exit codes and outputs."""

import json
import subprocess
import sys

from citygen.cli import EXIT_INVALID, EXIT_OK, EXIT_USAGE, main
from citygen.model import json_schema as model_schema
from citygen.spec import json_schema as spec_schema

from conftest import ROOT, write


def test_validate_ok(tmp_path, minimal, capsys):
    p = write(tmp_path, minimal)
    assert main(["spec", "validate", str(p)]) == EXIT_OK
    assert capsys.readouterr().out.startswith("OK: Harborlight")


def test_validate_writes_filled(tmp_path, minimal):
    p = write(tmp_path, minimal)
    out = tmp_path / "filled.json"
    assert main(["spec", "validate", str(p), "--filled", str(out)]) == EXIT_OK
    filled = json.loads(out.read_text())
    assert filled["districts"][0]["height_m"] == [80.0, 320.0]
    assert main(["spec", "validate", str(out)]) == EXIT_OK


def test_validate_invalid(tmp_path, minimal, capsys):
    minimal["districts"][0]["archetype"] = "corporate"
    p = write(tmp_path, minimal)
    assert main(["spec", "validate", str(p)]) == EXIT_INVALID
    err = capsys.readouterr().err
    assert "error: districts[0] \"Core\".archetype: 'corporate' is not allowed" in err
    assert "INVALID" in err


def test_validate_bad_json(tmp_path, capsys):
    p = write(tmp_path, '{"name": "X",,}')
    assert main(["spec", "validate", str(p)]) == EXIT_INVALID
    assert "not valid JSON" in capsys.readouterr().err


def test_missing_file_and_usage(tmp_path, capsys):
    assert main(["spec", "validate", str(tmp_path / "nope.json")]) == EXIT_USAGE
    assert main(["spec", "frobnicate"]) == EXIT_USAGE
    assert main([]) == EXIT_USAGE


def test_render(tmp_path, minimal):
    p = write(tmp_path, minimal)
    out = tmp_path / "s.png"
    assert main(["spec", "render", str(p), str(out)]) == EXIT_OK
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_invalid(tmp_path, minimal):
    minimal["districts"] = []
    p = write(tmp_path, minimal)
    out = tmp_path / "s.png"
    assert main(["spec", "render", str(p), str(out)]) == EXIT_INVALID
    assert not out.exists()


def test_module_entry_point_exit_code(tmp_path, minimal):
    minimal["seed"] = -1
    p = write(tmp_path, minimal)
    proc = subprocess.run([sys.executable, "-m", "citygen", "spec", "validate", str(p)],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == EXIT_INVALID
    assert "seed" in proc.stderr


def test_committed_schemas_are_current(tmp_path):
    """citygen/schemas/*.json must match the models (regenerate with `citygen spec schema`)."""
    spec_file = ROOT / "citygen" / "schemas" / "city_spec.schema.json"
    model_file = ROOT / "citygen" / "schemas" / "city_model.schema.json"
    assert json.loads(spec_file.read_text()) == spec_schema()
    assert json.loads(model_file.read_text()) == model_schema()
    out = tmp_path / "s.json"
    assert main(["spec", "schema", str(out)]) == EXIT_OK
    assert json.loads(out.read_text()) == spec_schema()
