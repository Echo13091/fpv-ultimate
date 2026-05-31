import time

try:
    from gps import gps, WATCH_ENABLE, WATCH_NEWSTYLE
except Exception:
    gps = None
    WATCH_ENABLE = 0
    WATCH_NEWSTYLE = 0

_last_fix = None
_gps_history = []
MAX_GPS_HISTORY = 100


def _mph(mps):
    return None if mps is None else round(float(mps) * 2.236936, 2)


def _ft(meters):
    return None if meters is None else round(float(meters) * 3.28084, 2)



def _remember_fix(fix):
    """Store a compact rolling GPS breadcrumb history in memory."""
    if not fix or not fix.get("healthy"):
        return

    point = {
        "time": fix.get("time"),
        "latitude": fix.get("latitude"),
        "longitude": fix.get("longitude"),
        "speed_mph": fix.get("speed_mph"),
        "heading_deg": fix.get("heading_deg"),
        "altitude_ft": fix.get("altitude_ft"),
        "satellites_used": fix.get("satellites_used"),
        "satellites_seen": fix.get("satellites_seen"),
    }

    if point["latitude"] is None or point["longitude"] is None:
        return

    if float(point["latitude"]) == 0.0 and float(point["longitude"]) == 0.0:
        return

    if fix.get("mode", 0) < 2:
        return

    if (fix.get("satellites_used") or 0) < 4:
        return

    if _gps_history and _gps_history[-1].get("time") == point.get("time"):
        _gps_history[-1] = point
    else:
        _gps_history.append(point)

    del _gps_history[:-MAX_GPS_HISTORY]


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
        sky = {}
        candidate_fix = None

        while time.time() - start < timeout_sec:
            report = session.next()
            report_class = getattr(report, "class", None)

            if report_class == "SKY":
                sky = {
                    "satellites_seen": getattr(report, "nSat", None),
                    "satellites_used": getattr(report, "uSat", None),
                    "hdop": getattr(report, "hdop", None),
                    "pdop": getattr(report, "pdop", None),
                }
                continue

            if report_class != "TPV":
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
                **sky,
                "last_read_epoch": time.time(),
            }

            candidate_fix = fix
            _last_fix = fix
            _remember_fix(fix)
            if sky:
                return fix

        if candidate_fix is not None:
            return candidate_fix

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

def get_last_known_fix():
    """Return the most recent GPS fix captured by read_gps."""
    return {"available": _last_fix is not None, "last_known": _last_fix}

def get_gps_history():
    """Return recent in-memory GPS breadcrumb points."""
    return {
        "count": len(_gps_history),
        "points": list(_gps_history),
    }

