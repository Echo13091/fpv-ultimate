import logging

logger = logging.getLogger("fpv-ultimate.accessories")


def apply_accessories_from_settings(settings: dict, trans_servo, lights_servo) -> None:
    """Drive transmission/lights servos to match current settings."""
    trans_state = (settings.get("trans_state") or "low").lower()
    lights_state = (settings.get("lights_state") or "off").lower()

    trans_low = float(settings.get("trans_low_angle", 0.0))
    trans_high = float(settings.get("trans_high_angle", 180.0))

    lights_off = float(settings.get("lights_off_angle", 0.0))
    lights_on = float(settings.get("lights_on_angle", 180.0))

    try:
        trans_servo.angle = trans_high if trans_state == "high" else trans_low
    except Exception as e:
        logger.error("Transmission servo error (GPIO6): %s", e)

    try:
        lights_servo.angle = lights_on if lights_state == "on" else lights_off
    except Exception as e:
        logger.error("Lights servo error (GPIO21): %s", e)
