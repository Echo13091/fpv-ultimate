import time

try:
    from gps import gps, WATCH_ENABLE, WATCH_NEWSTYLE
except Exception:
    gps = None
    WATCH_ENABLE = 0
    WATCH_NEWSTYLE = 0

_last_fix = None


def _mph(mps):
    return None if mps is None else round(float(mps) * 2.236936, 2)


def _ft(meters):
    return None if meters is None else round(float(meters) * 3.28084, 2)


def read_gps(timeout_sec=2):
    global _last_fix

    if gps is None:
        return {
            "enabled": False,
            "healthy": False,
            "device": "/dev/ttyACM0",
            "error": "python gps module not available",
        }

    try:
        session = gps(mode=WATCH_ENABLE | WATCH_NEWSTYLE)
        start = time.time()

        while time.time() - start < timeout_sec:
            report = session.next()

            if getattr(report, "class", None) != "TPV":
                continue

            mode = getattr(report, "mode", 0)
            lat = getattr(report, "lat", None)
            lon = getattr(report, "lon", None)

            fix = {
                "enabled": True,
                "healthy": mode >= 2 and lat is not None and lon is not None,
                "device": getattr(report, "device", "/dev/ttyACM0"),
                "mode": mode,
                "fix": "3D" if mode == 3 else "2D" if mode == 2 else "NO_FIX",
                "time": getattr(report, "time", None),
                "latitude": lat,
                "longitude": lon,
                "speed_mph": _mph(getattr(report, "speed", None)),
                "heading_deg": getattr(report, "track", None),
                "altitude_ft": _ft(getattr(report, "alt", None)),
                "last_read_epoch": time.time(),
            }

            _last_fix = fix
            return fix

        return {
            "enabled": True,
            "healthy": False,
            "device": "/dev/ttyACM0",
            "fix": "TIMEOUT",
            "last_known": _last_fix,
        }

    except Exception as exc:
        return {
            "enabled": True,
            "healthy": False,
            "device": "/dev/ttyACM0",
            "fix": "ERROR",
            "error": str(exc),
            "last_known": _last_fix,
        }
