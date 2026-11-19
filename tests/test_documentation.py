import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_readme_promotes_platform_and_developer_resources():
    introduction = (ROOT / "README.md").read_text().split("## Installation")[0]
    assert "**Website: [platform.antescofo.com](https://platform.antescofo.com/)**" in introduction
    assert "https://platform.antescofo.com/api-docs/" in introduction
    assert "https://platform.antescofo.com/licensing/#contact" in introduction


def test_readme_recommends_uv_with_an_optional_pip_fallback():
    readme = (ROOT / "README.md").read_text()
    installation = readme.split("## Installation")[1].split("## Configuration")[0]
    assert "uv init --python 3.12 antescofo-analysis" in installation
    assert (
        'uv add "antescofo-api @ git+https://github.com/Antescofo/antescofo-api-python.git@main"'
        in installation
    )
    assert installation.index("uv add") < installation.index("python -m pip install")
    assert "<summary>Using pip in an existing Python environment</summary>" in installation
    assert "uv run python examples/resume.py JOB_UUID" in readme


@pytest.mark.parametrize("filename", ["README.md", "CONTRIBUTING.md", "SECURITY.md"])
def test_relative_documentation_links_resolve(filename):
    document = ROOT / filename
    for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
        if ":" in target or target.startswith("#"):
            continue
        assert (document.parent / target.split("#")[0]).exists(), f"Broken link: {target}"


def test_license_uses_the_declared_spdx_identifier():
    license_text = (ROOT / "LICENSE").read_text()
    assert license_text.startswith("MIT License\n")
    assert "Copyright (c) 2026 Antescofo" in license_text
    assert "Permission is hereby granted, free of charge" in license_text
    assert 'license = "MIT"' in (ROOT / "pyproject.toml").read_text()


def test_environment_example_does_not_preset_connection_details():
    configuration = dict(
        line.split("=", 1)
        for line in (ROOT / ".env.example").read_text().splitlines()
        if line and not line.startswith("#")
    )
    assert "ANTESCOFO_API_BASE_URL" not in configuration
    assert configuration["ANTESCOFO_API_KEY"] == ""


def test_primary_readme_setup_requires_only_an_api_key():
    readme = (ROOT / "README.md").read_text()
    configuration = readme.split("## Configuration")[1].split("## Analyze A Performance")[0]
    basic = configuration.split("<details>")[0]
    assert "ANTESCOFO_API_KEY" in basic
    assert "ANTESCOFO_API_BASE_URL" not in basic
    assert "base_url=" not in basic
    assert "optional" in configuration.lower()


def test_readme_does_not_ask_clients_to_supply_duration():
    readme = (ROOT / "README.md").read_text()
    assert "do not accept a duration" in readme
    assert "or send `file_duration`" in readme
    assert "audio_duration_seconds=" not in readme
