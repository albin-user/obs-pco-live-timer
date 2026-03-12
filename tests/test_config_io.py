"""Tests for GUI config I/O — load, save, validate."""
import os

import pytest

from src.gui.config_io import load_config, save_config, validate_config


# ── load_config ─────────────────────────────────────────────────────


class TestLoadConfig:

    def test_missing_file_returns_defaults(self, tmp_path):
        config = load_config(str(tmp_path / "nonexistent.toml"))
        assert config["pco"]["app_id"] == ""
        assert config["pco"]["discovery_mode"] == "folder"
        assert config["pco"]["service_type_ids"] == []
        assert config["obs"]["port"] == 4455
        assert config["team"]["slots"] == []

    def test_loads_pco_section(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text('[pco]\napp_id = "abc"\nsecret = "xyz"\nfolder_id = "42"\n')
        config = load_config(str(p))
        assert config["pco"]["app_id"] == "abc"
        assert config["pco"]["secret"] == "xyz"
        assert config["pco"]["folder_id"] == "42"

    def test_loads_obs_section(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text('[obs]\nenabled = false\nhost = "10.0.0.1"\nport = 9999\n')
        config = load_config(str(p))
        assert config["obs"]["enabled"] is False
        assert config["obs"]["host"] == "10.0.0.1"
        assert config["obs"]["port"] == 9999

    def test_loads_team_slots(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text('[team]\nslots = ["Vocalist", "Drums"]\n')
        config = load_config(str(p))
        assert config["team"]["slots"] == ["Vocalist", "Drums"]

    def test_preserves_defaults_for_missing_keys(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text('[pco]\napp_id = "abc"\n')
        config = load_config(str(p))
        # Secret was not in file — should be default empty string
        assert config["pco"]["secret"] == ""
        # OBS section missing entirely — all defaults
        assert config["obs"]["host"] == "localhost"

    def test_ignores_unknown_keys(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text('[pco]\napp_id = "abc"\nunknown_key = "ignored"\n')
        config = load_config(str(p))
        assert config["pco"]["app_id"] == "abc"
        assert "unknown_key" not in config["pco"]


# ── save_config ─────────────────────────────────────────────────────


class TestSaveConfig:

    def test_roundtrip(self, tmp_path):
        p = str(tmp_path / "config.toml")
        original = {
            "pco": {"app_id": "myid", "secret": "mysecret", "folder_id": "123",
                    "discovery_mode": "folder", "service_type_ids": []},
            "obs": {"enabled": True, "host": "localhost", "port": 4455,
                    "password": "pw", "update_interval_ms": 1000},
            "team": {"enabled": True, "photo_cache_dir": "", "placeholder_photo": "",
                     "slots": ["Vocalist", "Drums"]},
        }
        save_config(p, original)
        loaded = load_config(p)
        assert loaded["pco"] == original["pco"]
        assert loaded["obs"] == original["obs"]
        assert loaded["team"]["slots"] == original["team"]["slots"]

    def test_roundtrip_all_mode(self, tmp_path):
        p = str(tmp_path / "config.toml")
        original = {
            "pco": {"app_id": "myid", "secret": "mysecret", "folder_id": "",
                    "discovery_mode": "all", "service_type_ids": []},
            "obs": {"enabled": True, "host": "localhost", "port": 4455,
                    "password": "", "update_interval_ms": 1000},
            "team": {"enabled": True, "photo_cache_dir": "", "placeholder_photo": "",
                     "slots": []},
        }
        save_config(p, original)
        loaded = load_config(p)
        assert loaded["pco"]["discovery_mode"] == "all"
        assert loaded["pco"]["folder_id"] == ""

    def test_roundtrip_service_types_mode(self, tmp_path):
        p = str(tmp_path / "config.toml")
        original = {
            "pco": {"app_id": "myid", "secret": "mysecret", "folder_id": "",
                    "discovery_mode": "service_types",
                    "service_type_ids": ["111", "222"]},
            "obs": {"enabled": True, "host": "localhost", "port": 4455,
                    "password": "", "update_interval_ms": 1000},
            "team": {"enabled": True, "photo_cache_dir": "", "placeholder_photo": "",
                     "slots": []},
        }
        save_config(p, original)
        loaded = load_config(p)
        assert loaded["pco"]["discovery_mode"] == "service_types"
        assert loaded["pco"]["service_type_ids"] == ["111", "222"]

    def test_creates_parent_dirs(self, tmp_path):
        p = str(tmp_path / "subdir" / "deep" / "config.toml")
        config = load_config("/nonexistent")  # defaults
        save_config(p, config)
        assert os.path.exists(p)

    def test_empty_slots(self, tmp_path):
        p = str(tmp_path / "config.toml")
        config = load_config("/nonexistent")
        config["team"]["slots"] = []
        save_config(p, config)
        loaded = load_config(p)
        assert loaded["team"]["slots"] == []

    def test_writes_comments(self, tmp_path):
        p = tmp_path / "config.toml"
        config = load_config("/nonexistent")
        save_config(str(p), config)
        text = p.read_text()
        assert "# Discovery mode" in text
        assert "# Folder ID" in text
        assert "# Leave empty if no password" in text


# ── validate_config ─────────────────────────────────────────────────


class TestValidateConfig:

    def test_valid_config(self):
        config = {
            "pco": {"app_id": "abc", "secret": "xyz", "folder_id": "42"},
            "obs": {"port": 4455},
        }
        assert validate_config(config) == []

    def test_missing_app_id(self):
        config = {
            "pco": {"app_id": "", "secret": "xyz", "folder_id": "42"},
            "obs": {"port": 4455},
        }
        errors = validate_config(config)
        assert any("app_id" in e for e in errors)

    def test_missing_secret(self):
        config = {
            "pco": {"app_id": "abc", "secret": "", "folder_id": "42"},
            "obs": {"port": 4455},
        }
        errors = validate_config(config)
        assert any("secret" in e for e in errors)

    def test_missing_folder_id(self):
        config = {
            "pco": {"app_id": "abc", "secret": "xyz", "folder_id": ""},
            "obs": {"port": 4455},
        }
        errors = validate_config(config)
        assert any("folder_id" in e for e in errors)

    def test_folder_id_not_required_when_all_mode(self):
        config = {
            "pco": {"app_id": "abc", "secret": "xyz", "folder_id": "",
                    "discovery_mode": "all"},
            "obs": {"port": 4455},
        }
        errors = validate_config(config)
        assert not any("folder_id" in e for e in errors)

    def test_invalid_port(self):
        config = {
            "pco": {"app_id": "abc", "secret": "xyz", "folder_id": "42"},
            "obs": {"port": 99999},
        }
        errors = validate_config(config)
        assert any("port" in e for e in errors)

    def test_port_zero(self):
        config = {
            "pco": {"app_id": "abc", "secret": "xyz", "folder_id": "42"},
            "obs": {"port": 0},
        }
        errors = validate_config(config)
        assert any("port" in e for e in errors)

    def test_multiple_errors(self):
        config = {
            "pco": {"app_id": "", "secret": "", "folder_id": ""},
            "obs": {"port": -1},
        }
        errors = validate_config(config)
        assert len(errors) >= 3

    def test_invalid_discovery_mode(self):
        config = {
            "pco": {"app_id": "abc", "secret": "xyz", "folder_id": "",
                    "discovery_mode": "bogus"},
            "obs": {"port": 4455},
        }
        errors = validate_config(config)
        assert any("discovery_mode" in e for e in errors)

    def test_service_types_mode_empty_list(self):
        config = {
            "pco": {"app_id": "abc", "secret": "xyz",
                    "discovery_mode": "service_types", "service_type_ids": []},
            "obs": {"port": 4455},
        }
        errors = validate_config(config)
        assert any("service_type_ids" in e for e in errors)

    def test_service_types_mode_valid(self):
        config = {
            "pco": {"app_id": "abc", "secret": "xyz",
                    "discovery_mode": "service_types",
                    "service_type_ids": ["111", "222"]},
            "obs": {"port": 4455},
        }
        assert validate_config(config) == []

    def test_all_mode_no_folder_needed(self):
        config = {
            "pco": {"app_id": "abc", "secret": "xyz", "folder_id": "",
                    "discovery_mode": "all"},
            "obs": {"port": 4455},
        }
        assert validate_config(config) == []


# ── Migration tests ────────────────────────────────────────────────


class TestMigration:

    def test_legacy_scan_all_true_migrates_to_all(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text(
            '[pco]\napp_id = "a"\nsecret = "s"\n'
            'scan_all_service_types = true\n'
        )
        config = load_config(str(p))
        assert config["pco"]["discovery_mode"] == "all"

    def test_legacy_scan_all_false_migrates_to_folder(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text(
            '[pco]\napp_id = "a"\nsecret = "s"\n'
            'folder_id = "42"\nscan_all_service_types = false\n'
        )
        config = load_config(str(p))
        assert config["pco"]["discovery_mode"] == "folder"

    def test_new_format_not_migrated(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text(
            '[pco]\napp_id = "a"\nsecret = "s"\n'
            'discovery_mode = "service_types"\n'
            'service_type_ids = ["111"]\n'
        )
        config = load_config(str(p))
        assert config["pco"]["discovery_mode"] == "service_types"
        assert config["pco"]["service_type_ids"] == ["111"]

    def test_loads_service_type_ids(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text(
            '[pco]\napp_id = "a"\nsecret = "s"\n'
            'discovery_mode = "service_types"\n'
            'service_type_ids = ["111", "222", "333"]\n'
        )
        config = load_config(str(p))
        assert config["pco"]["service_type_ids"] == ["111", "222", "333"]
