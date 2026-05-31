#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${FPV_BASE_URL:-http://127.0.0.1:5000}"

printf '== FPV Ultimate smoke test ==\n'
printf 'Base URL: %s\n\n' "$BASE_URL"

printf '== Python syntax ==\n'
python -m py_compile app.py fpv_ultimate/*.py
printf 'Python syntax OK\n\n'

printf '== Health check ==\n'
PING_RESPONSE="$(curl -fsS "$BASE_URL/ping")"
if [ "$PING_RESPONSE" != "pong" ]; then
  printf 'ERROR: expected ping response "pong", got "%s"\n' "$PING_RESPONSE" >&2
  exit 1
fi
printf 'Ping OK\n\n'

printf '== Settings endpoint ==\n'
curl -fsS "$BASE_URL/api/settings" | python3 -m json.tool >/tmp/fpv-settings-smoke.json
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path('/tmp/fpv-settings-smoke.json').read_text())
required = [
    'steer_trim',
    'throttle_trim',
    'steer_rate',
    'throttle_rate',
    'failsafe_enabled',
    'video_resolution',
    'video_fps',
]
missing = [key for key in required if key not in data]
if missing:
    raise SystemExit(f'missing settings keys: {missing}')
print('Settings OK')
PY
printf '\n'

printf '== Models endpoint ==\n'
curl -fsS "$BASE_URL/api/models" | python3 -m json.tool >/tmp/fpv-models-smoke.json
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path('/tmp/fpv-models-smoke.json').read_text())
if 'models' not in data or not isinstance(data['models'], list):
    raise SystemExit('models response missing list field')
if 'active_index' not in data:
    raise SystemExit('models response missing active_index')
print('Models OK')
PY
printf '\n'

printf '== Accessories endpoint ==\n'
curl -fsS "$BASE_URL/api/accessories" | python3 -m json.tool >/tmp/fpv-accessories-smoke.json
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path('/tmp/fpv-accessories-smoke.json').read_text())
if data.get('ok') is not True:
    raise SystemExit('accessories response did not report ok=true')
for key in ('trans_state', 'lights_state'):
    if key not in data:
        raise SystemExit(f'accessories response missing {key}')
print('Accessories OK')
PY
printf '\n'

printf '== Control neutral command ==\n'
curl -fsS -X POST "$BASE_URL/api/control" \
  -H 'Content-Type: application/json' \
  -d '{"steer":90,"throttle":90}' | python3 -m json.tool >/tmp/fpv-control-smoke.json
python3 - <<'PY'
import json
from pathlib import Path

data = json.loads(Path('/tmp/fpv-control-smoke.json').read_text())
if data.get('ok') is not True:
    raise SystemExit('control response did not report ok=true')
print('Control neutral OK')
PY
printf '\n'


printf '== GPS status endpoint ==\n'
curl -fsS "$BASE_URL/gps/status" | python3 -m json.tool >/tmp/fpv-gps-status-smoke.json
python3 - <<'GPSSTATUSPY'
import json
from pathlib import Path

data = json.loads(Path('/tmp/fpv-gps-status-smoke.json').read_text())
for key in ('enabled', 'healthy', 'fix', 'device'):
    if key not in data:
        raise SystemExit(f'gps status response missing {key}')
print('GPS status OK')
GPSSTATUSPY
printf '\n'

printf '== GPS last-known endpoint ==\n'
curl -fsS "$BASE_URL/gps/last-known" | python3 -m json.tool >/tmp/fpv-gps-last-known-smoke.json
python3 - <<'GPSLASTPY'
import json
from pathlib import Path

data = json.loads(Path('/tmp/fpv-gps-last-known-smoke.json').read_text())
if 'available' not in data:
    raise SystemExit('gps last-known response missing available')
if 'last_known' not in data:
    raise SystemExit('gps last-known response missing last_known')
print('GPS last-known OK')
GPSLASTPY
printf '\n'

printf '== GPS history endpoint ==\n'
curl -fsS "$BASE_URL/gps/history" | python3 -m json.tool >/tmp/fpv-gps-history-smoke.json
python3 - <<'GPSHISTORYPY'
import json
from pathlib import Path

data = json.loads(Path('/tmp/fpv-gps-history-smoke.json').read_text())
if 'count' not in data:
    raise SystemExit('gps history response missing count')
if 'points' not in data or not isinstance(data['points'], list):
    raise SystemExit('gps history response missing points list')
print('GPS history OK')
GPSHISTORYPY
printf '\n'

printf 'Smoke test passed.\n'
