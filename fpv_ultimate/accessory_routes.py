from flask import jsonify, request


def register_accessory_routes(
    app,
    *,
    settings_lock,
    get_settings,
    set_settings,
    save_settings_to_disk,
    apply_accessories_from_settings,
):
    @app.route("/api/transmission", methods=["POST"])
    def api_transmission():
        """Set or toggle transmission high/low on GPIO6."""
        payload = request.get_json(silent=True) or {}
        req_state = (payload.get("state") or "").lower().strip()

        with settings_lock:
            settings = dict(get_settings())
            cur = (settings.get("trans_state") or "low").lower()

            if req_state in ("high", "low"):
                new_state = req_state
            else:
                new_state = "high" if cur != "high" else "low"

            settings["trans_state"] = new_state
            saved = save_settings_to_disk(settings)
            set_settings(saved)

        apply_accessories_from_settings()
        return jsonify({"ok": True, "state": new_state})

    @app.route("/api/lights", methods=["POST"])
    def api_lights():
        """Set or toggle lights on/off on GPIO21."""
        payload = request.get_json(silent=True) or {}
        req_state = (payload.get("state") or "").lower().strip()

        with settings_lock:
            settings = dict(get_settings())
            cur = (settings.get("lights_state") or "off").lower()

            if req_state in ("on", "off"):
                new_state = req_state
            else:
                new_state = "on" if cur != "on" else "off"

            settings["lights_state"] = new_state
            saved = save_settings_to_disk(settings)
            set_settings(saved)

        apply_accessories_from_settings()
        return jsonify({"ok": True, "state": new_state})

    @app.route("/api/accessories", methods=["GET"])
    def api_accessories():
        with settings_lock:
            settings = get_settings()
            return jsonify({
                "ok": True,
                "trans_state": (settings.get("trans_state") or "low").lower(),
                "lights_state": (settings.get("lights_state") or "off").lower(),
            })
