"""citygen must never call an API or the network, and must not depend on an LLM SDK."""

import ast
import json
import socket
import subprocess
import sys
import tomllib

import pytest

from conftest import EXAMPLES, ROOT

# Top-level modules that are LLM SDKs, HTTP clients or network access.
FORBIDDEN = {
    "anthropic", "openai", "cohere", "mistralai", "google.generativeai", "google.genai",
    "vertexai", "langchain", "langchain_core", "langchain_openai", "langchain_anthropic",
    "llama_index", "litellm", "transformers", "huggingface_hub", "ollama", "groq",
    "requests", "httpx", "urllib3", "aiohttp", "httplib2", "pycurl", "websocket", "websockets",
    "grpc", "boto3", "botocore", "urllib.request", "http.client", "http.server", "socket",
    "ssl", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc", "socketserver",
    "asyncio.streams", "webbrowser",
}
PACKAGE_NAMES = {m.split(".")[0].replace("_", "-") for m in FORBIDDEN if "." not in m} | {
    "google-generativeai", "google-genai", "langchain-openai", "langchain-anthropic",
    "llama-index", "huggingface-hub"}

SOURCES = sorted((ROOT / "citygen").rglob("*.py"))


def _imports(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module
            for alias in node.names:
                yield f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in ("import_module", "__import__") and node.args and \
                    isinstance(node.args[0], ast.Constant):
                yield str(node.args[0].value)


def _forbidden(module: str) -> bool:
    return any(module == f or module.startswith(f + ".") for f in FORBIDDEN)


def test_sources_found():
    assert len(SOURCES) >= 7


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_forbidden_imports(path):
    bad = sorted({m for m in _imports(path) if _forbidden(m)})
    assert not bad, f"{path.relative_to(ROOT)} imports {bad}"


def test_no_forbidden_dependencies():
    deps = [line.split("==")[0].split(">=")[0].strip().lower()
            for line in (ROOT / "requirements.txt").read_text().splitlines()
            if line.strip() and not line.startswith("#")]
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    deps += [d.split(">")[0].split("=")[0].split("<")[0].strip().lower()
             for d in project.get("dependencies", [])]
    bad = sorted(set(deps) & PACKAGE_NAMES)
    assert not bad, f"forbidden dependencies: {bad}"


def test_import_pulls_in_no_llm_or_http_client():
    """Importing every citygen module (renderer included) loads no LLM SDK or HTTP client.

    `socket` itself is left out here: the standard library imports it indirectly; the runtime
    test below makes sure nothing ever opens one.
    """
    code = (
        "import sys, citygen.cli, citygen.schematic, citygen.model, citygen.validate\n"
        "print('\\n'.join(sys.modules))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=ROOT, check=True).stdout.split()
    banned = {m for m in FORBIDDEN if m not in ("socket", "ssl", "asyncio.streams")}
    bad = sorted(m for m in out if any(m == b or m.startswith(b + ".") for b in banned))
    assert not bad, f"loaded at import: {bad}"


class _NoNetwork(socket.socket):
    def connect(self, *a, **k):  # noqa: D401
        raise AssertionError("citygen tried to open a network connection")

    connect_ex = connect

    def sendto(self, *a, **k):
        raise AssertionError("citygen tried to send on the network")


def test_runtime_makes_no_connections(tmp_path, monkeypatch):
    from citygen.cli import main

    monkeypatch.setattr(socket, "socket", _NoNetwork)
    monkeypatch.setattr(socket, "create_connection",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("dns lookup")))
    spec = EXAMPLES[0]
    assert main(["spec", "validate", str(spec), "--filled", str(tmp_path / "f.json")]) == 0
    assert main(["spec", "render", str(spec), str(tmp_path / "s.png")]) == 0
    json.loads((tmp_path / "f.json").read_text())
