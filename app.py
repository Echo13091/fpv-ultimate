#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import threading
import logging
import signal

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

from fpv_ultimate.accessories import apply_accessories_from_settings
from fpv_ultimate.control_service import ControlService
from fpv_ultimate.accessory_routes import register_accessory_routes
from fpv_ultimate.control_math import clamp, compute_alpha
from fpv_ultimate.video_config import VIDEO_RESOLUTIONS, clamp_fps, get_video_size
from fpv_ultimate.health import ping_response
from fpv_ultimate.gps_service import read_gps
from fpv_ultimate.pages import index_template
from fpv_ultimate.settings_models_routes import register_settings_model_routes
from fpv_ultimate.system_actions import request_reboot
from fpv_ultimate.storage import (
    DEFAULT_MODEL,
    DEFAULT_SETTINGS,
    load_models_from_disk as storage_load_models_from_disk,
    load_settings_from_disk as storage_load_settings_from_disk,
    save_models_to_disk as storage_save_models_to_disk,
    save_settings_to_disk as storage_save_settings_to_disk,
)

# ---------------------------------------------------------------------
# Paths & Flask
# ---------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, os.environ.get("FPV_DATA_DIR", "data"))
os.makedirs(DATA_DIR, exist_ok=True)

SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
MODELS_PATH = os.path.join(DATA_DIR, "models.json")
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
SETTINGS = {}
SETTINGS_LOCK = threading.Lock()


def get_settings():
    return SETTINGS


def set_settings(settings):
    global SETTINGS
    SETTINGS = settings

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

# Neutral on boot

# Accessories (servo-style PWM switches)
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

control_service = ControlService(
    steer_servo=steer_servo,
    throttle_servo=throttle_servo,
    neutral_angle=90.0,
    failsafe_timeout=0.25,
)

# ---------------------------------------------------------------------
# Camera setup
# ---------------------------------------------------------------------
picam2 = None
camera_lock = threading.Lock()

# ---------------------------------------------------------------------
# Helpers for settings/models
# ---------------------------------------------------------------------
def load_settings_from_disk():
    return storage_load_settings_from_disk(SETTINGS_PATH)


def save_settings_to_disk(settings):
    return storage_save_settings_to_disk(SETTINGS_PATH, settings)


# ---------------------------------------------------------------------
# Accessories helpers (trans + lights)
# ---------------------------------------------------------------------
def _apply_accessories_from_settings():
    """Drive GPIO6/GPIO21 servos to match current SETTINGS."""
    with SETTINGS_LOCK:
        settings_snapshot = dict(SETTINGS)

    apply_accessories_from_settings(settings_snapshot, trans_servo, lights_servo)

def load_models_from_disk():
    return storage_load_models_from_disk(MODELS_PATH)


def save_models_to_disk(data):
    return storage_save_models_to_disk(MODELS_PATH, data)


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

    size = get_video_size(res_name, DEFAULT_SETTINGS["video_resolution"])
    fps = clamp_fps(fps)

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


def failsafe_worker():
    logger.info("Failsafe thread started")
    while not failsafe_stop.is_set():
        failsafe_stop.wait(0.02)
        with SETTINGS_LOCK:
            enabled = bool(SETTINGS.get("failsafe_enabled", True))

        try:
            control_service.apply_failsafe_if_needed(enabled=enabled)
        except Exception as e:
            logger.error("Failsafe error: %s", e)

# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@app.route("/")
def index():
    return render_template(index_template())


@app.route("/ping")
def ping():
    return ping_response()



@app.route("/gps/status")
def gps_status():
    return jsonify(read_gps())


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
    data = request.get_json(force=True) or {}
    steer = data.get("steer", 90)
    throttle = data.get("throttle", 90)

    try:
        steer = float(steer)
        throttle = float(throttle)
    except Exception:
        return jsonify({"ok": False, "error": "invalid steer/throttle"}), 400

    with SETTINGS_LOCK:
        steer_speed = SETTINGS.get("steer_speed", 100.0)
        throttle_speed = SETTINGS.get("throttle_speed", 100.0)

    try:
        control_service.apply_control(
            steer=steer,
            throttle=throttle,
            steer_speed=steer_speed,
            throttle_speed=throttle_speed,
        )
    except Exception as e:
        logger.error("Error driving servos: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True})


register_accessory_routes(
    app,
    settings_lock=SETTINGS_LOCK,
    get_settings=get_settings,
    set_settings=set_settings,
    save_settings_to_disk=save_settings_to_disk,
    apply_accessories_from_settings=_apply_accessories_from_settings,
)


register_settings_model_routes(
    app,
    settings_lock=SETTINGS_LOCK,
    get_settings=get_settings,
    set_settings=set_settings,
    default_settings=DEFAULT_SETTINGS,
    default_model=DEFAULT_MODEL,
    load_models_from_disk=load_models_from_disk,
    save_models_to_disk=save_models_to_disk,
    save_settings_to_disk=save_settings_to_disk,
    configure_camera_from_settings=configure_camera_from_settings,
    logger=logger,
)

@app.route("/api/reboot", methods=["POST"])
def api_reboot():
    with SETTINGS_LOCK:
        remote_reboot_enabled = bool(SETTINGS.get("remote_reboot_enabled", False))

    if not remote_reboot_enabled:
        logger.warning("Remote reboot blocked because remote_reboot_enabled is false")
        return jsonify({
            "ok": False,
            "error": "remote reboot disabled",
        }), 403

    logger.warning("Reboot requested via /api/reboot")
    try:
        control_service.neutralize()
    except Exception as e:
        logger.error("Failed to neutralize before reboot: %s", e)
        return jsonify({"ok": False, "error": "failed to neutralize outputs"}), 500

    request_reboot()
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
    host = os.environ.get("FPV_HOST", "127.0.0.1")
    port = int(os.environ.get("FPV_PORT", "5000"))
    logger.info("FPV Ultimate WebRTC starting on %s:%d", host, port)
    app.run(host=host, port=port, debug=False)
