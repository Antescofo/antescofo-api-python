"""Keep published connection details limited to public and example destinations."""

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_HOSTS = {
    "api.platform.metronaut.app",
    "platform.antescofo.com",
    "github.com",
    "docs.astral.sh",
    "pypi.org",
    "files.pythonhosted.org",
    "localhost",
    "127.0.0.1",
    "::1",
}


def test_published_files_reference_only_approved_hosts():
    files = [*ROOT.glob("*.md"), ROOT / "pyproject.toml", ROOT / ".env.example"]
    if (ROOT / "uv.lock").exists():
        files.append(ROOT / "uv.lock")
    for directory in ("src", "examples", "tests", ".github"):
        files.extend(
            path
            for path in (ROOT / directory).rglob("*")
            if path.is_file() and path.suffix in {".py", ".yml", ".yaml"}
        )
    for path in files:
        for url in re.findall(r"https?://[^\s\"'`<>]+", path.read_text(encoding="utf-8")):
            host = urlsplit(url).hostname
            assert approved_host(host), f"Unapproved URL host in {path.relative_to(ROOT)}"


@pytest.mark.parametrize("host", ["api.example", "storage.example", "localhost", "::1"])
def test_documentation_and_loopback_examples_are_allowed(host):
    assert approved_host(host)


@pytest.mark.parametrize("host", [None, "unapproved.invalid", "github.com.unapproved.invalid"])
def test_unknown_hosts_require_review(host):
    assert not approved_host(host)


def approved_host(host):
    return host is not None and (host in PUBLIC_HOSTS or host.endswith(".example"))
