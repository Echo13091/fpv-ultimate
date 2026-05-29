import json

from fpv_ultimate.storage import (
    DEFAULT_SETTINGS,
    load_models_from_disk,
    load_settings_from_disk,
    save_models_to_disk,
    save_settings_to_disk,
)


def test_load_settings_creates_defaults_when_missing(tmp_path):
    settings_path = tmp_path / "settings.json"

    data = load_settings_from_disk(str(settings_path))

    assert data == DEFAULT_SETTINGS
    assert settings_path.exists()
    assert json.loads(settings_path.read_text()) == DEFAULT_SETTINGS


def test_load_settings_merges_existing_partial_file(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"steer_trim": 7.5}))

    data = load_settings_from_disk(str(settings_path))

    assert data["steer_trim"] == 7.5
    assert data["failsafe_enabled"] is True
    assert data["video_resolution"] == DEFAULT_SETTINGS["video_resolution"]


def test_save_settings_writes_complete_merged_file(tmp_path):
    settings_path = tmp_path / "settings.json"

    saved = save_settings_to_disk(str(settings_path), {"video_fps": 15})
    on_disk = json.loads(settings_path.read_text())

    assert saved["video_fps"] == 15
    assert on_disk["video_fps"] == 15
    assert on_disk["steer_rate"] == DEFAULT_SETTINGS["steer_rate"]


def test_load_models_creates_default_model_file(tmp_path):
    models_path = tmp_path / "models.json"

    data = load_models_from_disk(str(models_path))

    assert data["active_index"] == 0
    assert len(data["models"]) == 1
    assert models_path.exists()


def test_save_models_round_trip(tmp_path):
    models_path = tmp_path / "models.json"
    data = {
        "active_index": 0,
        "models": [{"name": "Crawler", "steer_rate": 80}],
    }

    save_models_to_disk(str(models_path), data)

    assert json.loads(models_path.read_text()) == data
