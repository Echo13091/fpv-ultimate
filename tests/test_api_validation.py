from fpv_ultimate.api_validation import bool_value, clamp_number, parse_model_index
from fpv_ultimate.settings_models_routes import _normalize_settings
from fpv_ultimate.storage import DEFAULT_SETTINGS


def test_parse_model_index_handles_bad_values():
    assert parse_model_index({"index": "2"}) == 2
    assert parse_model_index({"index": "bad"}) == -1
    assert parse_model_index({"index": None}) == -1
    assert parse_model_index(None) == -1


def test_clamp_number_bounds_bad_values():
    assert clamp_number(-100, 50, 0, 100) == 0
    assert clamp_number(25, 50, 0, 100) == 25
    assert clamp_number(250, 50, 0, 100) == 100
    assert clamp_number("bad", 50, 0, 100) == 50


def test_bool_value_normalizes_strings():
    assert bool_value("true", False) is True
    assert bool_value("yes", False) is True
    assert bool_value("false", True) is False
    assert bool_value("off", True) is False
    assert bool_value("bad", True) is True


def test_normalize_settings_clamps_runtime_values():
    normalized = _normalize_settings(
        {
            "steer_trim": 999,
            "throttle_trim": -999,
            "steer_rate": 150,
            "throttle_rate": -5,
            "video_resolution": "invalid",
            "video_fps": 999,
            "video_quality": -1,
            "video_color_order": "bgr",
            "video_flip": "bad",
            "trans_state": "bad",
            "lights_state": "bad",
            "trans_low_angle": -20,
            "lights_on_angle": 999,
            "remote_reboot_enabled": "true",
        },
        DEFAULT_SETTINGS,
    )

    assert normalized["steer_trim"] == 30
    assert normalized["throttle_trim"] == -30
    assert normalized["steer_rate"] == 100
    assert normalized["throttle_rate"] == 0
    assert normalized["video_resolution"] == DEFAULT_SETTINGS["video_resolution"]
    assert normalized["video_fps"] == 60
    assert normalized["video_quality"] == 1
    assert normalized["video_color_order"] == "BGR"
    assert normalized["video_flip"] == DEFAULT_SETTINGS["video_flip"]
    assert normalized["trans_state"] == DEFAULT_SETTINGS["trans_state"]
    assert normalized["lights_state"] == DEFAULT_SETTINGS["lights_state"]
    assert normalized["trans_low_angle"] == 0
    assert normalized["lights_on_angle"] == 180
    assert normalized["remote_reboot_enabled"] is True
