from importlib.metadata import metadata

from antescofo_api import __version__


def test_installed_distribution_matches_import_version():
    distribution = metadata("antescofo-api")
    assert distribution["Name"] == "antescofo-api"
    assert distribution["Version"] == __version__
    assert distribution["License-Expression"] == "MIT"
