import importlib.util

import pytest
from catalog_tree import SKILLS


@pytest.fixture
def translator():
    path = SKILLS / "dbt-sf-to-bq-translator/scripts/dbt_translator.py"
    spec = importlib.util.spec_from_file_location("dbt_translator_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_metadata_copies_regular_files(translator, tmp_path):
    source = tmp_path / "metadata"
    source.mkdir()
    (source / "tables.csv").write_text("table\norders\n")
    (source / "extra.txt").write_text("inside marker\n")
    destination = tmp_path / "staging"
    assert translator.preprocess_metadata(str(source), str(destination), set(), {}) is True
    assert (destination / "extra.txt").read_text() == "inside marker\n"


@pytest.mark.parametrize("name", ["tables.csv", "extra.txt"])
def test_metadata_rejects_outside_file_symlinks(translator, tmp_path, name):
    source = tmp_path / "metadata"
    source.mkdir()
    (source / "tables.csv").write_text("table\norders\n")
    outside = tmp_path / "outside.csv"
    outside.write_text("table\noutside_marker\n")
    target = source / name
    if target.exists():
        target.unlink()
    target.symlink_to(outside)
    with pytest.raises(ValueError, match="outside"):
        translator.preprocess_metadata(str(source), str(tmp_path / "staging"), set(), {})


def test_metadata_keeps_inside_file_symlinks(translator, tmp_path):
    source = tmp_path / "metadata"
    source.mkdir()
    (source / "tables.csv").write_text("table\norders\n")
    target = source / "inside.txt"
    target.write_text("inside marker\n")
    (source / "alias.txt").symlink_to(target)
    destination = tmp_path / "staging"
    assert translator.preprocess_metadata(str(source), str(destination), set(), {}) is True
    assert (destination / "alias.txt").read_text() == "inside marker\n"


@pytest.mark.parametrize("extension", ["sql", "yml", "yaml"])
def test_resource_discovery_rejects_outside_symlinks(translator, tmp_path, extension):
    source = tmp_path / "project"
    source.mkdir()
    outside = tmp_path / f"outside.{extension}"
    outside.write_text("SELECT 1;" if extension == "sql" else "sources: []\n")
    (source / f"escape.{extension}").symlink_to(outside)
    with pytest.raises(ValueError, match="outside"):
        translator.discover_dbt_resources(str(source))


def test_translation_rejects_outside_sql_before_cloud_calls(translator, tmp_path, monkeypatch):
    source = tmp_path / "project"
    source.mkdir()
    outside = tmp_path / "outside.sql"
    outside.write_text("SELECT 'outside marker';\n")
    (source / "escape.sql").symlink_to(outside)
    monkeypatch.chdir(tmp_path)

    def unexpected_cloud_call(*args, **kwargs):
        pytest.fail("outside source reached cloud upload")

    monkeypatch.setattr(translator.subprocess, "run", unexpected_cloud_call)
    with pytest.raises(ValueError, match="outside"):
        translator.run_bulk_translation(str(source), str(tmp_path / "output"), "test-bucket", "test-location")
