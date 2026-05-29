#!/usr/bin/env bash
set -euo pipefail

APP_NAME="fpv-ultimate"
APP_USER="${APP_USER:-$USER}"
APP_DIR="${APP_DIR:-$HOME/fpv-ultimate}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SERVICE_NAME="${SERVICE_NAME:-fpv-ultimate.service}"

echo "== FPV Ultimate Raspberry Pi installer =="
echo "App user: $APP_USER"
echo "App dir:  $APP_DIR"

if [ ! -d "$APP_DIR" ]; then
  echo "ERROR: app directory does not exist: $APP_DIR"
  echo "Clone the repo first, then run this script from the project folder."
  exit 1
fi

cd "$APP_DIR"

echo
echo "== Installing Raspberry Pi OS packages =="
sudo apt update
sudo apt install -y \
  python3-venv \
  python3-pip \
  python3-libcamera \
  python3-picamera2 \
  python3-kms++ \
  python3-prctl \
  libcamera-apps \
  pigpio \
  python3-pigpio \
  git

echo
echo "== Enabling pigpio daemon =="
sudo systemctl enable --now pigpiod

echo
echo "== Creating Python virtual environment with system site packages =="
if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv --system-site-packages .venv
else
  echo ".venv already exists; keeping it."
fi

echo
echo "== Installing Python requirements =="
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo
echo "== Verifying Python imports =="
python - <<'PY'
import flask
import gpiozero
import pigpio
import aiortc
import av
import libcamera
from picamera2 import Picamera2
print("Python dependency check passed")
PY

echo
echo "== Verifying project syntax =="
python -m py_compile app.py fpv_ultimate/*.py

echo
echo "== Ensuring runtime folders exist =="
mkdir -p data docs

if [ ! -f "data/settings.json" ]; then
  echo "WARNING: data/settings.json is missing. The app will create defaults on first run."
fi

if [ ! -f "data/models.json" ]; then
  echo "WARNING: data/models.json is missing. The app will create defaults on first run."
fi

echo
echo "== systemd notes =="
echo "Live service should be installed at:"
echo "  /etc/systemd/system/$SERVICE_NAME"
echo
echo "Reference service config is stored at:"
echo "  systemd/fpv-ultimate.service.reference"
echo
echo "To restart the app:"
echo "  sudo systemctl restart fpv-ultimate"
echo
echo "To view logs:"
echo "  sudo journalctl -u fpv-ultimate -n 80 --no-pager -l"

echo
echo "Install check complete."
