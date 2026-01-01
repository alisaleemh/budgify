from pathlib import Path

from webapp import config_manager


def test_ensure_config_file_creates_defaults(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    linked_path = tmp_path / "linked-config.yaml"

    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config_manager, "LINKED_CONFIG_PATH", linked_path)

    config = config_manager.ensure_config_file()

    assert config_path.exists()
    assert linked_path.is_symlink()
    assert linked_path.resolve() == config_path
    assert "categories" in config
    assert config["categories"]


def test_category_mutations(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    linked_path = tmp_path / "linked-config.yaml"

    monkeypatch.setattr(config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config_manager, "LINKED_CONFIG_PATH", linked_path)

    config_manager.ensure_config_file()

    config_manager.add_category("travel")
    config = config_manager.load_config()
    assert "travel" in config["categories"]

    config_manager.rename_category("travel", "trips")
    config = config_manager.load_config()
    assert "trips" in config["categories"]
    assert "travel" not in config["categories"]

    config_manager.delete_category("trips")
    config = config_manager.load_config()
    assert "trips" not in config["categories"]
