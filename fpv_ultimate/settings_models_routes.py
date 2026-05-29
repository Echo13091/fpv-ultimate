from flask import jsonify, request


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

            settings.update({k: v for k, v in incoming.items() if k in default_settings})
            saved = save_settings_to_disk(settings)
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
        idx = int(payload.get("index", -1))
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
        idx = int(payload.get("index", -1))

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
        idx = int(payload.get("index", -1))
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
