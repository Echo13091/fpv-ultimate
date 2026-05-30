def parse_model_index(payload, default=-1):
    if not isinstance(payload, dict):
        return default
    try:
        return int(payload.get("index", default))
    except (TypeError, ValueError):
        return default


def clamp_number(value, default, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return max(float(minimum), min(float(maximum), number))


def bool_value(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
    return bool(default)
