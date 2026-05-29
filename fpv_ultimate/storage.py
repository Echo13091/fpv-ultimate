import json
import logging
import os
import tempfile

logger = logging.getLogger("fpv-ultimate.storage")

DEFAULT_SETTINGS = {
    # trims (deg added around 90 center)
    "steer_trim": 0.0,
    "throttle_trim": 0.0,

    # dual rate (%) 0–100
    "steer_rate": 100.0,
    "throttle_rate": 100.0,

    # per-channel response speed (0–100)
    "steer_speed": 100.0,
    "throttle_speed": 100.0,

    # channel reversing
    "steer_reverse": False,
    "throttle_reverse": False,

    # failsafe / safety gates
    "failsafe_enabled": True,
    "remote_reboot_enabled": False,

    # camera / video
    "video_resolution": "1280x720",
    "video_fps": 30,
    "video_quality": 70,
    "video_color_order": "RGB",
    "video_flip": "none",

    # accessories (servo PWM switches)
    # Transmission: GPIO6
    "trans_state": "low",
    "trans_low_angle": 0.0,
    "trans_high_angle": 180.0,

    # Lights: GPIO21
    "lights_state": "off",
    "lights_off_angle": 0.0,
    "lights_on_angle": 180.0,
}

DEFAULT_MODEL = {
    "name": "Model 1",
    "steer_trim": 0.0,
    "throttle_trim": 0.0,
    "steer_rate": 100.0,
    "throttle_rate": 100.0,
    "steer_speed": 100.0,
    "throttle_speed": 100.0,
    "steer_reverse": False,
    "throttle_reverse": False,
}


def _atomic_json_write(path: str, data: dict) -> None:
    """Write JSON through a temp file, then atomically replace the target."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}.",
        suffix=".tmp",
        dir=directory,
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_settings_from_disk(settings_path: str) -> dict:
    if not os.path.exists(settings_path):
        _atomic_json_write(settings_path, DEFAULT_SETTINGS)
        return dict(DEFAULT_SETTINGS)

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("settings.json must contain an object")
    except Exception as e:
        logger.error("Failed to read settings.json, using defaults: %s", e)
        return dict(DEFAULT_SETTINGS)

    merged = dict(DEFAULT_SETTINGS)
    merged.update(data)
    return merged


def save_settings_to_disk(settings_path: str, settings: dict) -> dict:
    tmp = dict(DEFAULT_SETTINGS)
    tmp.update(settings)
    _atomic_json_write(settings_path, tmp)
    return tmp


def load_models_from_disk(models_path: str) -> dict:
    if not os.path.exists(models_path):
        data = {"active_index": 0, "models": [dict(DEFAULT_MODEL)]}
        _atomic_json_write(models_path, data)
        return data

    try:
        with open(models_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("models.json must contain an object")
        if "models" not in data:
            raise ValueError("models key missing")
    except Exception as e:
        logger.error("Failed to read models.json, recreating: %s", e)
        data = {"active_index": 0, "models": [dict(DEFAULT_MODEL)]}
        _atomic_json_write(models_path, data)
        return data

    models = data.get("models") or []
    if not models:
        models = [dict(DEFAULT_MODEL)]
    data["models"] = models
    if "active_index" not in data:
        data["active_index"] = 0
    return data


def save_models_to_disk(models_path: str, data: dict) -> None:
    _atomic_json_write(models_path, data)
