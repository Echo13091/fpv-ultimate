def compute_alpha(speed_percent: float) -> float:
    """
    Convert "speed" (0–100%) into a smoothing factor 0–1.

    0%   -> very slow movement
    100% -> almost direct
    """
    try:
        value = float(speed_percent)
    except Exception:
        value = 100.0

    value = max(0.0, min(value, 100.0))
    return 0.1 + 0.9 * (value / 100.0)
