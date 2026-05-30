from flask import jsonify, request

from fpv_ultimate.api_validation import bool_value, clamp_number, parse_model_index
from fpv_ultimate.video_config import VIDEO_RESOLUTIONS, clamp_fps


def _choice(value, allowed, default):
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in allowed:
            return normalized
    return default


def _normalize_settings(settings, default_settings):
    normalized = dict(default_settings)
    normalized.update({k: v for k, v in settings.items() if k in default_settings})

    normalized["steer_trim"] = clamp_number(normalized.get("steer_trim"), default_settings["steer_trim"], -30, 30)
    normalized["throttle_trim"] = clamp_number(normalized.get("throttle_trim"), default_settings["throttle_trim"], -30, 30)
    normalized["steer_rate"] = clamp_number(normalized.get("steer_rate"), default_settings["steer_rate"], 0, 100)
    normalized["throttle_rate"] = clamp_number(normalized.get("throttle_rate"), default_settings["throttle_rate"], 0, 100)
    normalized["steer_speed"] = clamp_number(normalized.get("steer_speed"), default_settings["steer_speed"], 0, 100)
    normalized["throttle_speed"] = clamp_number(normalized.get("throttle_speed"), default_settings["throttle_speed"], 0, 100)

    normalized["steer_reverse"] = bool_value(normalized.get("steer_reverse"), default_settings["steer_reverse"])
    normalized["throttle_reverse"] = bool_value(normalized.get("throttle_reverse"), default_settings["throttle_reverse"])
    normalized["failsafe_enabled"] = bool_value(normalized.get("failsafe_enabled"), default_settings["failsafe_enabled"])
    normalized["remote_reboot_enabled"] = bool_value(
        normalized.get("remote_reboot_enabled"),
        default_settings.get("remote_reboot_enabled", False),
    )

    if normalized.get("video_resolution") not in VIDEO_RESOLUTIONS:
        normalized["video_resolution"] = default_settings["video_resolution"]
    try:
        normalized["video_fps"] = clamp_fps(int(normalized.get("video_fps", default_settings["video_fps"])))
    except (TypeError, ValueError):
        normalized["video_fps"] = default_settings["video_fps"]
    normalized["video_quality"] = clamp_number(normalized.get("video_quality"), default_settings["video_quality"], 1, 100)

    color_order = str(normalized.get("video_color_order", default_settings["video_color_order"])).upper()
    normalized["video_color_order"] = color_order if color_order in ("RGB", "BGR") else default_settings["video_color_order"]
    normalized["video_flip"] = _choice(normalized.get("video_flip"), ("none", "h", "v", "hv"), default_settings.get("video_flip", "none"))

    normalized["trans_state"] = _choice(normalized.get("trans_state"), ("low", "high"), default_settings["trans_state"])
    normalized["lights_state"] = _choice(normalized.get("lights_state"), ("off", "on"), default_settings["lights_state"])
    normalized["trans_low_angle"] = clamp_number(normalized.get("trans_low_angle"), default_settings["trans_low_angle"], 0, 180)
    normalized["trans_high_angle"] = clamp_number(normalized.get("trans_high_angle"), default_settings["trans_high_angle"], 0, 180)
    normalized["lights_off_angle"] = clamp_number(normalized.get("lights_off_angle"), default_settings["lights_off_angle"], 0, 180)
    normalized["lights_on_angle"] = clamp_number(normalized.get("lights_on_angle"), default_settings["lights_on_angle"], 0, 180)

    return normalized


def register_settings_model_routes(
    app,
    *,
    settings_lock,
    get_settings,
    set_settings,
    default_settings,
    default_model,
    load_models_from_disk,
    save_models_to_disk,
    save_settings_to_disk,
    configure_camera_from_settings,
    logger,
):
    @app.route("/api/settings", methods=["GET", "POST"])
    def api_settings():
        if request.method == "GET":
            with settings_lock:
                return jsonify(get_settings())

        incoming = request.get_json(force=True) or {}

        with settings_lock:
            settings = get_settings()

            old_res = settings.get(
                "video_resolution",
                default_settings["video_resolution"],
            )
            old_fps = int(settings.get("video_fps", default_settings["video_fps"]))
            old_flip = (
                settings.get(
                    "video_flip",
                    default_settings.get("video_flip", "none"),
                )
                or "none"
            ).lower()

            merged = dict(settings)
            merged.update({k: v for k, v in incoming.items() if k in default_settings})
            normalized = _normalize_settings(merged, default_settings)
            saved = save_settings_to_disk(normalized)
            set_settings(saved)

            new_res = saved.get("video_resolution", old_res)
            try:
                new_fps = int(saved.get("video_fps", old_fps))
            except Exception:
                new_fps = old_fps

            new_flip = (saved.get("video_flip", old_flip) or "none").lower()

        if old_res != new_res or old_fps != new_fps or old_flip != new_flip:
            logger.info(
                "Video settings changed: %s @ %d (%s) -> %s @ %d (%s)",
                old_res,
                old_fps,
                old_flip,
                new_res,
                new_fps,
                new_flip,
            )
            try:
                configure_camera_from_settings()
            except Exception as e:
                logger.error("Failed to reconfigure camera: %s", e)

        return jsonify({"ok": True, "settings": get_settings()})

    @app.route("/api/models", methods=["GET"])
    def api_models_list():
        data = load_models_from_disk()
        return jsonify(data)

    @app.route("/api/models/save", methods=["POST"])
    def api_models_save():
        payload = request.get_json(force=True) or {}
        idx = parse_model_index(payload)
        model = payload.get("model")

        if not isinstance(model, dict):
            return jsonify({"ok": False, "error": "model must be object"}), 400

        data = load_models_from_disk()
        models = data.get("models", [])

        if not models:
            models = [dict(default_model)]

        if idx < 0 or idx >= len(models):
            models.append(model)
            idx = len(models) - 1
        else:
            models[idx] = model

        data["models"] = models
        data["active_index"] = idx
        save_models_to_disk(data)
        return jsonify({"ok": True, "index": idx})

    @app.route("/api/models/delete", methods=["POST"])
    def api_models_delete():
        payload = request.get_json(force=True) or {}
        idx = parse_model_index(payload)

        data = load_models_from_disk()
        models = data.get("models", [])

        if idx < 0 or idx >= len(models):
            return jsonify({"ok": False, "error": "invalid index"}), 400

        if len(models) == 1:
            models[0] = dict(default_model)
            data["active_index"] = 0
        else:
            models.pop(idx)
            data["active_index"] = max(
                0,
                min(data.get("active_index", 0), len(models) - 1),
            )

        data["models"] = models
        save_models_to_disk(data)
        return jsonify({"ok": True, "active_index": data["active_index"]})

    @app.route("/api/models/rename", methods=["POST"])
    def api_models_rename():
        payload = request.get_json(force=True) or {}
        idx = parse_model_index(payload)
        new_name = (payload.get("name") or "").strip()

        if not new_name:
            return jsonify({"ok": False, "error": "name required"}), 400

        data = load_models_from_disk()
        models = data.get("models", [])

        if idx < 0 or idx >= len(models):
            return jsonify({"ok": False, "error": "invalid index"}), 400

        model = models[idx]
        if not isinstance(model, dict):
            model = {}
            models[idx] = model

        model["name"] = new_name
        data["models"] = models
        save_models_to_disk(data)
        return jsonify({"ok": True})
