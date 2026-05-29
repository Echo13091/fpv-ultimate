#!/usr/bin/env python3
import os
import sys
import time
import json
import asyncio
import threading
import logging
import signal
import subprocess  # reboot

from flask import Flask, render_template, request, jsonify

from gpiozero import AngularServo
from gpiozero.pins.pigpio import PiGPIOFactory

from picamera2 import Picamera2
from libcamera import Transform

import av
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
    RTCRtpSender,
)

# ---------------------------------------------------------------------
# Paths & Flask
# ---------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
MODELS_PATH = os.path.join(BASE_DIR, "models.json")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR,
)

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("fpv-ultimate")

# ---------------------------------------------------------------------
# Global settings / models
# ---------------------------------------------------------------------
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

    # failsafe
    "failsafe_enabled": True,

    # camera / video
    # IMPORTANT: these names match the <select id="video-resolution"> in index.html
    "video_resolution": "1280x720",   # "640x360" | "1280x720" | "1920x1080"
    "video_fps": 30,                  # 15 | 30 | 60
    "video_quality": 70,              # 10–100 (for later encoder tuning)
    # Color order – how we interpret raw frames when feeding aiortc
    "video_color_order": "RGB",       # "RGB" | "BGR"
    "video_flip": "none",          # "none" | "h" | "v" | "hv"
    # accessories (servo PWM switches)
    # Transmission: GPIO6 (servo-style PWM)
    "trans_state": "low",          # "low" | "high"
    "trans_low_angle": 0.0,
    "trans_high_angle": 180.0,

    # Lights: GPIO21 (servo-style PWM)
    "lights_state": "off",         # "off" | "on"
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

SETTINGS = {}
SETTINGS_LOCK = threading.Lock()

# ---------------------------------------------------------------------
# Servo setup
# ---------------------------------------------------------------------
factory = PiGPIOFactory()

steer_servo = AngularServo(
    12,
    min_angle=0,
    max_angle=180,
    min_pulse_width=0.0005,
    max_pulse_width=0.0025,
    pin_factory=factory,
)

throttle_servo = AngularServo(
    13,
    min_angle=0,
    max_angle=180,
    min_pulse_width=0.0005,
    max_pulse_width=0.0025,
    pin_factory=factory,
)

# Neutral on boot# Accessories (servo-style PWM switches)
# NOTE: These use 1000–2000µs pulses (common for simple servo switch boards)
trans_servo = AngularServo(
    6,
    min_angle=0,
    max_angle=180,
    min_pulse_width=0.0010,
    max_pulse_width=0.0020,
    pin_factory=factory,
)

lights_servo = AngularServo(
    21,
    min_angle=0,
    max_angle=180,
    min_pulse_width=0.0010,
    max_pulse_width=0.0020,
    pin_factory=factory,
)


steer_servo.angle = 90
throttle_servo.angle = 90

last_control_time = time.time()
last_steer_angle = 90.0
last_throttle_angle = 90.0

# ---------------------------------------------------------------------
# Camera setup
# ---------------------------------------------------------------------
# Keys here MUST match the values used in <select id="video-resolution">
VIDEO_RESOLUTIONS = {
    "640x360": (640, 360),
    "1280x720": (1280, 720),
    "1920x1080": (1920, 1080),
}

picam2 = None
camera_lock = threading.Lock()

# ---------------------------------------------------------------------
# Helpers for settings/models
# ---------------------------------------------------------------------
def load_settings_from_disk():
    if not os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=2)
        return dict(DEFAULT_SETTINGS)

    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("settings.json must contain an object")
    except Exception as e:
        logger.error("Failed to read settings.json, using defaults: %s", e)
        return dict(DEFAULT_SETTINGS)

    merged = dict(DEFAULT_SETTINGS)
    merged.update(data)
    return merged


def save_settings_to_disk(settings):
    tmp = dict(DEFAULT_SETTINGS)
    tmp.update(settings)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(tmp, f, indent=2)
    return tmp

# ---------------------------------------------------------------------
# Accessories helpers (trans + lights)
# ---------------------------------------------------------------------
def _apply_accessories_from_settings():
    """Drive GPIO6/GPIO21 servos to match current SETTINGS."""
    with SETTINGS_LOCK:
        trans_state = (SETTINGS.get("trans_state") or "low").lower()
        lights_state = (SETTINGS.get("lights_state") or "off").lower()

        trans_low = float(SETTINGS.get("trans_low_angle", 0.0))
        trans_high = float(SETTINGS.get("trans_high_angle", 180.0))

        lights_off = float(SETTINGS.get("lights_off_angle", 0.0))
        lights_on = float(SETTINGS.get("lights_on_angle", 180.0))

    try:
        trans_servo.angle = trans_high if trans_state == "high" else trans_low
    except Exception as e:
        logger.error("Transmission servo error (GPIO6): %s", e)

    try:
        lights_servo.angle = lights_on if lights_state == "on" else lights_off
    except Exception as e:
        logger.error("Lights servo error (GPIO21): %s", e)



def load_models_from_disk():
    if not os.path.exists(MODELS_PATH):
        data = {"active_index": 0, "models": [dict(DEFAULT_MODEL)]}
        with open(MODELS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data

    try:
        with open(MODELS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("models.json must contain an object")
        if "models" not in data:
            raise ValueError("models key missing")
    except Exception as e:
        logger.error("Failed to read models.json, recreating: %s", e)
        data = {"active_index": 0, "models": [dict(DEFAULT_MODEL)]}
        with open(MODELS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data

    models = data.get("models") or []
    if not models:
        models = [dict(DEFAULT_MODEL)]
    data["models"] = models
    if "active_index" not in data:
        data["active_index"] = 0
    return data


def save_models_to_disk(data):
    with open(MODELS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def compute_alpha(speed_percent: float) -> float:
    """
    Convert "speed" (0–100%) into a smoothing factor 0–1.
    0%  -> very slow movement
    100% -> almost direct
    """
    try:
        v = float(speed_percent)
    except Exception:
        v = 100.0

    v = max(0.0, min(v, 100.0))
    alpha = 0.1 + 0.9 * (v / 100.0)  # 0.1..1.0
    return alpha

# ---------------------------------------------------------------------
# Camera configure / reconfigure
# ---------------------------------------------------------------------
def configure_camera_from_settings():
    """Stop camera (if running), configure with new settings, then start."""
    global picam2

    with SETTINGS_LOCK:
        res_name = SETTINGS.get("video_resolution", DEFAULT_SETTINGS["video_resolution"])
        fps = int(SETTINGS.get("video_fps", DEFAULT_SETTINGS["video_fps"]))

        flip = (SETTINGS.get("video_flip", "none") or "none").lower()

    size = VIDEO_RESOLUTIONS.get(res_name, VIDEO_RESOLUTIONS[DEFAULT_SETTINGS["video_resolution"]])
    fps = max(5, min(fps, 60))

    with camera_lock:
        if picam2 is None:
            picam2 = Picamera2()

        # Always stop camera before reconfiguring
        try:
            picam2.stop()
        except Exception:
            pass

        logger.info("Reconfiguring camera to size=%s fps=%d", size, fps)

        # Flip options: none | h | v | hv
        hflip = 1 if flip in ("h", "hv") else 0
        vflip = 1 if flip in ("v", "hv") else 0

        video_config = picam2.create_video_configuration(
            main={"size": size, "format": "RGB888"},
            transform=Transform(hflip=hflip, vflip=vflip),
        )
        video_config["controls"] = {"FrameRate": fps}

        logger.info("Video config: %s", video_config)

        picam2.configure(video_config)

        # Enable AF if supported (IMX708)
        try:
            picam2.set_controls({"AfMode": 0, "LensPosition": 0.65})
            logger.info("IMX708 FPV focus locked: AfMode=0 LensPosition=0.55")
        except Exception:
            logger.warning("Autofocus control not supported or failed; continuing.")

        picam2.start()
        logger.info("Camera configured successfully: %s @ %d fps", res_name, fps)


class CameraVideoTrack(VideoStreamTrack):
    """VideoStreamTrack that pulls frames from Picamera2."""

    def __init__(self):
        super().__init__()

    async def recv(self):
        global picam2
        pts, time_base = await self.next_timestamp()

        with camera_lock:
            if picam2 is None:
                raise RuntimeError("Camera not initialized")
            frame = picam2.capture_array("main")

        # Decide how to interpret the raw frame based on settings:
        with SETTINGS_LOCK:
            color_order = (SETTINGS.get("video_color_order", "RGB") or "RGB").upper()

        fmt = "bgr24" if color_order == "BGR" else "rgb24"

        video_frame = av.VideoFrame.from_ndarray(frame, format=fmt)
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

# ---------------------------------------------------------------------
# WebRTC loop
# ---------------------------------------------------------------------
webrtc_loop = asyncio.new_event_loop()
webrtc_thread = None
pcs = set()


async def handle_offer(offer_dict):
    offer = RTCSessionDescription(
        sdp=offer_dict["sdp"],
        type=offer_dict["type"],
    )

    pc = RTCPeerConnection()
    pcs.add(pc)
    logger.info("Created RTCPeerConnection (%d total)", len(pcs))

    @pc.on("connectionstatechange")
    async def on_state_change():
        logger.info("PC state: %s", pc.connectionState)
        if pc.connectionState in ("failed", "closed", "disconnected"):
            pcs.discard(pc)
            await pc.close()
            logger.info("PC closed (%d remaining)", len(pcs))

    video_track = CameraVideoTrack()
    pc.addTrack(video_track)

    await pc.setRemoteDescription(offer)

    # Prefer H.264 if available
    try:
        caps = RTCRtpSender.getCapabilities("video")
        codecs = [
            c for c in caps.codecs if c.name.upper() == "H264"
        ] + [
            c for c in caps.codecs if c.name.upper() != "H264"
        ]
        for transceiver in pc.getTransceivers():
            transceiver.setCodecPreferences(codecs)
    except Exception as e:
        logger.warning("Could not tweak codec preferences: %s", e)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return pc


def run_coro_in_webrtc_loop(coro):
    fut = asyncio.run_coroutine_threadsafe(coro, webrtc_loop)
    return fut.result(timeout=15)

# ---------------------------------------------------------------------
# Failsafe thread
# ---------------------------------------------------------------------
failsafe_stop = threading.Event()
FAILSAFE_TIMEOUT = 0.25  # seconds


def failsafe_worker():
    global last_control_time, last_steer_angle, last_throttle_angle
    logger.info("Failsafe thread started")
    while not failsafe_stop.is_set():
        time.sleep(0.02)
        with SETTINGS_LOCK:
            enabled = bool(SETTINGS.get("failsafe_enabled", True))
        if not enabled:
            continue

        now = time.time()
        if now - last_control_time > FAILSAFE_TIMEOUT:
            try:
                last_steer_angle = 90.0
                last_throttle_angle = 90.0
                steer_servo.angle = 90
                throttle_servo.angle = 90
            except Exception as e:
                logger.error("Failsafe error: %s", e)

# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ping")
def ping():
    return "pong", 200


@app.route("/offer", methods=["POST"])
def offer():
    payload = request.get_json(force=True) or {}
    if "sdp" not in payload or "type" not in payload:
        return jsonify({"error": "invalid SDP"}), 400

    try:
        pc = run_coro_in_webrtc_loop(handle_offer(payload))
    except Exception as e:
        logger.error("Error in /offer: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500

    answer = pc.localDescription
    return jsonify({"sdp": answer.sdp, "type": answer.type})


@app.route("/api/control", methods=["POST"])
def api_control():
    global last_control_time, last_steer_angle, last_throttle_angle

    data = request.get_json(force=True) or {}
    steer = data.get("steer", 90)
    throttle = data.get("throttle", 90)

    try:
        steer = float(steer)
        throttle = float(throttle)
    except Exception:
        return jsonify({"ok": False, "error": "invalid steer/throttle"}), 400

    def clamp(v, lo, hi):
        return max(lo, min(hi, v))

    steer = clamp(steer, 0.0, 180.0)
    throttle = clamp(throttle, 0.0, 180.0)

    with SETTINGS_LOCK:
        steer_speed = SETTINGS.get("steer_speed", 100.0)
        throttle_speed = SETTINGS.get("throttle_speed", 100.0)

    steer_alpha = compute_alpha(steer_speed)
    throttle_alpha = compute_alpha(throttle_speed)

    try:
        last_steer_angle = (1.0 - steer_alpha) * last_steer_angle + steer_alpha * steer
        last_throttle_angle = (1.0 - throttle_alpha) * last_throttle_angle + throttle_alpha * throttle

        steer_servo.angle = last_steer_angle
        throttle_servo.angle = last_throttle_angle

        last_control_time = time.time()
    except Exception as e:
        logger.error("Error driving servos: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True})


@app.route("/api/transmission", methods=["POST"])
def api_transmission():
    """Set or toggle transmission high/low on GPIO6 (servo PWM)."""
    payload = request.get_json(silent=True) or {}
    req_state = (payload.get("state") or "").lower().strip()

    with SETTINGS_LOCK:
        cur = (SETTINGS.get("trans_state") or "low").lower()
        if req_state in ("high", "low"):
            new_state = req_state
        else:
            new_state = "high" if cur != "high" else "low"
        SETTINGS["trans_state"] = new_state
        save_settings_to_disk(SETTINGS)

    _apply_accessories_from_settings()
    return jsonify({"ok": True, "state": new_state})


@app.route("/api/lights", methods=["POST"])
def api_lights():
    """Set or toggle lights on/off on GPIO21 (servo PWM)."""
    payload = request.get_json(silent=True) or {}
    req_state = (payload.get("state") or "").lower().strip()

    with SETTINGS_LOCK:
        cur = (SETTINGS.get("lights_state") or "off").lower()
        if req_state in ("on", "off"):
            new_state = req_state
        else:
            new_state = "on" if cur != "on" else "off"
        SETTINGS["lights_state"] = new_state
        save_settings_to_disk(SETTINGS)

    _apply_accessories_from_settings()
    return jsonify({"ok": True, "state": new_state})


@app.route("/api/accessories", methods=["GET"])
def api_accessories():
    with SETTINGS_LOCK:
        return jsonify({
            "ok": True,
            "trans_state": (SETTINGS.get("trans_state") or "low").lower(),
            "lights_state": (SETTINGS.get("lights_state") or "off").lower(),
        })



@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    global SETTINGS

    if request.method == "GET":
        with SETTINGS_LOCK:
            return jsonify(SETTINGS)

    incoming = request.get_json(force=True) or {}
    with SETTINGS_LOCK:
        old_res = SETTINGS.get("video_resolution", DEFAULT_SETTINGS["video_resolution"])
        old_fps = int(SETTINGS.get("video_fps", DEFAULT_SETTINGS["video_fps"]))
        old_flip = (SETTINGS.get("video_flip", DEFAULT_SETTINGS.get("video_flip", "none")) or "none").lower()

        SETTINGS.update({k: v for k, v in incoming.items() if k in DEFAULT_SETTINGS})
        saved = save_settings_to_disk(SETTINGS)
        SETTINGS = saved
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

    return jsonify({"ok": True, "settings": SETTINGS})


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
        models = [dict(DEFAULT_MODEL)]

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
        models[0] = dict(DEFAULT_MODEL)
        data["active_index"] = 0
    else:
        models.pop(idx)
        data["active_index"] = max(
            0, min(data.get("active_index", 0), len(models) - 1)
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

# NEW: reboot endpoint triggered by PS button hold
@app.route("/api/reboot", methods=["POST"])
def api_reboot():
    logger.warning("Reboot requested via /api/reboot (PS button hold)")

    def _do_reboot():
        try:
            subprocess.Popen(["sudo", "reboot", "now"])
        except Exception as e:
            logger.error("Reboot command failed: %s", e)

    threading.Thread(target=_do_reboot, daemon=True).start()
    return jsonify({"ok": True, "message": "Rebooting system"})

# ---------------------------------------------------------------------
# Shutdown / startup
# ---------------------------------------------------------------------
def shutdown(*_args):
    logger.info("Shutting down...")
    failsafe_stop.set()

    async def _close_all():
        for pc in list(pcs):
            try:
                await pc.close()
            except Exception:
                pass
            pcs.discard(pc)

    try:
        asyncio.run_coroutine_threadsafe(_close_all(), webrtc_loop).result(5)
    except Exception:
        pass

    with camera_lock:
        global picam2
        if picam2 is not None:
            try:
                picam2.stop()
            except Exception:
                pass
            picam2 = None

    try:
        steer_servo.close()
        throttle_servo.close()
        trans_servo.close()
        lights_servo.close()
    except Exception:
        pass

    logger.info("Shutdown complete")
    sys.exit(0)


def start_background_threads():
    global SETTINGS, webrtc_thread

    with SETTINGS_LOCK:
        SETTINGS = load_settings_from_disk()
    _apply_accessories_from_settings()


    logger.info("Initialization successful.")
    configure_camera_from_settings()
    logger.info("Camera now open.")

    webrtc_thread = threading.Thread(target=webrtc_loop.run_forever, daemon=True)
    webrtc_thread.start()

    t = threading.Thread(target=failsafe_worker, daemon=True)
    t.start()


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

start_background_threads()

if __name__ == "__main__":
    logger.info("FPV Ultimate WebRTC starting on 127.0.0.1:5000 (Tailscale Serve HTTPS)")
    app.run(host="127.0.0.1", port=5000, debug=False)

