// FPV Ultimate client: WebRTC + gamepad + settings + models

let pc = null;
let remoteVideo = null;

let currentSettings = null;
let modelsState = { active_index: 0, models: [] };

let gamepadIndex = null;
let sendLoopHandle = null;
let lastSendTime = 0;

let lastPingMs = null;
let pingTimer = null;

let fpsState = {
    frames: 0,
    lastTime: performance.now(),
    value: 0.0,
};

// Recording state
let mediaRecorder = null;
let recordedChunks = [];
let isRecording = false;

// D-pad edges
let lastDpadRightPressed = false;
let lastDpadUpPressed = false;

// PS button hold state for reboot
let psHoldStart = null;
let psHoldFired = false;

// Fullscreen button (Triangle) edge detection
let lastFullscreenButtonPressed = false;


// Square (lights) / Circle (trans) edge detection
let lastSquareButtonPressed = false;
let lastCircleButtonPressed = false;
// Trim combo edges
let lastTrimLeftPressed = false;
let lastTrimRightPressed = false;
let lastTrimUpPressed = false;
let lastTrimDownPressed = false;

function $(id) {
    return document.getElementById(id);
}

// ------------------------------------------------------------
// Small UI helpers
// ------------------------------------------------------------

function setStatusDot(id, ok) {
    const el = $(id);
    if (!el) return;
    el.classList.remove("ok", "bad");
    if (ok === true) el.classList.add("ok");
    if (ok === false) el.classList.add("bad");
}

function setWebRTCState(text) {
    const el = $("webrtc-state");
    if (el) el.textContent = text;
}

// Recording indicator helper
function setRecordingIndicator(active) {
    const el = $("record-indicator");
    if (!el) return;
    el.style.display = active ? "inline-flex" : "none";

    const status = $("record-status");
    if (status) status.textContent = active ? "Recording" : "Idle";
}

// Trim HUD helper
function updateTrimHud() {
    const el = $("trim-hud-values");
    if (!el || !currentSettings) return;
    const st = Math.round(currentSettings.steer_trim || 0);
    const th = Math.round(currentSettings.throttle_trim || 0);
    const fmt = (v) => (v >= 0 ? `+${v}` : `${v}`);
    el.textContent = `ST:${fmt(st)} TH:${fmt(th)}`;

    const stLabel = $("steer-trim-label");
    const thLabel = $("throttle-trim-label");
    if (stLabel) stLabel.textContent = fmt(st);
    if (thLabel) thLabel.textContent = fmt(th);
}

// ------------------------------------------------------------
// WebRTC video
// ------------------------------------------------------------

async function startWebRTC() {
    if (pc) {
        console.log("WebRTC already running");
        return;
    }

    remoteVideo = $("remoteVideo");
    if (!remoteVideo) {
        console.error("remoteVideo element not found");
        return;
    }

    setWebRTCState("Connecting...");
    setStatusDot("dot-webrtc", false);

    $("btn-connect-video").disabled = true;
    $("btn-disconnect-video").disabled = false;

    pc = new RTCPeerConnection({ iceServers: [] });

    pc.ontrack = (ev) => {
        console.log("Got remote track", ev.streams);
        if (ev.streams && ev.streams[0]) {
            remoteVideo.srcObject = ev.streams[0];
            setupFpsTracking();
            setWebRTCState("Receiving video");
            setStatusDot("dot-webrtc", true);
        }
    };

    pc.oniceconnectionstatechange = () => {
        if (!pc) return;
        const state = pc.iceConnectionState;
        console.log("ICE connection state:", state);
        if (state === "connected") {
            setWebRTCState("Connected");
            setStatusDot("dot-webrtc", true);
        } else if (state === "failed" || state === "disconnected" || state === "closed") {
            setWebRTCState("Disconnected");
            setStatusDot("dot-webrtc", false);
            // Stop recording if connection drops
            stopRecording();
        }
    };

    try {
        const offer = await pc.createOffer({
            offerToReceiveAudio: false,
            offerToReceiveVideo: true,
        });
        await pc.setLocalDescription(offer);

        const resp = await fetch("/offer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                sdp: offer.sdp,
                type: offer.type,
            }),
        });
        if (!resp.ok) {
            const msg = await resp.text();
            console.error("Offer failed:", msg);
            setWebRTCState("Error");
            setStatusDot("dot-webrtc", false);
            return;
        }
        const answer = await resp.json();
        await pc.setRemoteDescription(answer);
        console.log("WebRTC answer set");
        setWebRTCState("Connected");
        setStatusDot("dot-webrtc", true);
    } catch (err) {
        console.error("startWebRTC error:", err);
        setWebRTCState("Error");
        setStatusDot("dot-webrtc", false);
        $("btn-connect-video").disabled = false;
        $("btn-disconnect-video").disabled = true;
        if (pc) {
            pc.close();
            pc = null;
        }
    }
}

async function stopWebRTC() {
    stopRecording();

    if (pc) {
        try {
            pc.ontrack = null;
            pc.oniceconnectionstatechange = null;
            pc.close();
        } catch (e) {
            console.warn("Error closing RTCPeerConnection:", e);
        }
        pc = null;
    }

    if (remoteVideo) {
        remoteVideo.srcObject = null;
    }

    setWebRTCState("Idle");
    setStatusDot("dot-webrtc", false);
    $("btn-connect-video").disabled = false;
    $("btn-disconnect-video").disabled = true;
}

// ------------------------------------------------------------
// FPS tracking
// ------------------------------------------------------------

function setupFpsTracking() {
    fpsState.frames = 0;
    fpsState.lastTime = performance.now();
    fpsState.value = 0.0;
    updateFpsDisplay();

    if (!remoteVideo) return;

    if ("requestVideoFrameCallback" in remoteVideo) {
        const tick = () => {
            bumpFps();
            remoteVideo.requestVideoFrameCallback(tick);
        };
        remoteVideo.requestVideoFrameCallback(tick);
    } else {
        const onTimeUpdate = () => bumpFps();
        remoteVideo.addEventListener("timeupdate", onTimeUpdate);
    }
}

function bumpFps() {
    fpsState.frames += 1;
    const now = performance.now();
    if (now - fpsState.lastTime >= 500) {
        const dt = (now - fpsState.lastTime) / 1000.0;
        fpsState.value = fpsState.frames / dt;
        fpsState.frames = 0;
        fpsState.lastTime = now;
        updateFpsDisplay();
    }
}

function updateFpsDisplay() {
    const valueStr = fpsState.value.toFixed(1);
    const el = $("fps-value");
    const elFull = $("fps-value-full");
    if (el) el.textContent = valueStr;
    if (elFull) elFull.textContent = valueStr;
}

// ------------------------------------------------------------
// Ping / latency
// ------------------------------------------------------------

async function doPing() {
    const start = performance.now();
    try {
        const resp = await fetch("/ping", { cache: "no-store" });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        await resp.text();
        lastPingMs = performance.now() - start;
    } catch (err) {
        console.error("ping error:", err);
        lastPingMs = null;
    }
    updatePingDisplay();
}

function updatePingDisplay() {
    const el = $("ping-value");
    const elFull = $("ping-value-full");

    if (lastPingMs == null) {
        if (el) {
            el.textContent = "–";
            el.style.color = "";
        }
        if (elFull) {
            elFull.textContent = "–";
        }
        return;
    }

    const txt = lastPingMs.toFixed(0);

    if (el) {
        el.textContent = txt;
        if (lastPingMs < 60) {
            el.style.color = "#4caf50";
        } else if (lastPingMs < 120) {
            el.style.color = "#ff9800";
        } else {
            el.style.color = "#f44336";
        }
    }

    if (elFull) {
        elFull.textContent = txt;
    }
}

// ------------------------------------------------------------
// Settings
// ------------------------------------------------------------

async function loadSettings() {
    try {
        const resp = await fetch("/api/settings");
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        currentSettings = await resp.json();
        applySettingsToUI();
    } catch (err) {
        console.error("loadSettings error:", err);
    }
}

function applySettingsToUI() {
    if (!currentSettings) return;

    $("steer-trim").value = currentSettings.steer_trim ?? 0;
    $("throttle-trim").value = currentSettings.throttle_trim ?? 0;
    $("steer-rate").value = currentSettings.steer_rate ?? 100;
    $("throttle-rate").value = currentSettings.throttle_rate ?? 100;
    $("steer-speed").value = currentSettings.steer_speed ?? 100;
    $("throttle-speed").value = currentSettings.throttle_speed ?? 100;
    $("steer-reverse").checked = !!currentSettings.steer_reverse;
    $("throttle-reverse").checked = !!currentSettings.throttle_reverse;
    $("failsafe-enabled").checked = !!currentSettings.failsafe_enabled;

    $("video-resolution").value = currentSettings.video_resolution ?? "1280x720";
    $("video-fps").value = String(currentSettings.video_fps ?? 30);
    $("video-quality").value = String(currentSettings.video_quality ?? 70);
    $("video-color-order").value = currentSettings.video_color_order ?? "RGB";
    $("video-flip").value = currentSettings.video_flip ?? "none";

    const res = $("video-resolution").value;
    const fps = $("video-fps").value;
    const q = $("video-quality").value;
    const color = $("video-color-order").value;
    const flip = $("video-flip").value;
    const flipLabel = flip === "none" ? "NoFlip" : (flip === "h" ? "HFlip" : (flip === "v" ? "VFlip" : "HVFlip"));
    $("res-value").textContent = `${res} @ ${fps}fps Q${q} ${color} ${flipLabel}`;

    // Accessories
    const transSel = $("trans-select");
    if (transSel) transSel.value = (currentSettings.trans_state || "low");

    const rcLightsSel = $("rc-lights-select");
    const accLightsSel = $("lights-select");
    const lightsVal = (currentSettings.lights_state || "off");
    if (rcLightsSel) rcLightsSel.value = lightsVal;
    if (accLightsSel) accLightsSel.value = lightsVal;


    setStatusDot("dot-failsafe", $("failsafe-enabled").checked);
    updateTrimHud();
}

function readSettingsFromUI() {
    if (!currentSettings) currentSettings = {};
    currentSettings.steer_trim = parseFloat($("steer-trim").value || "0");
    currentSettings.throttle_trim = parseFloat($("throttle-trim").value || "0");
    currentSettings.steer_rate = parseFloat($("steer-rate").value || "100");
    currentSettings.throttle_rate = parseFloat($("throttle-rate").value || "100");
    currentSettings.steer_speed = parseFloat($("steer-speed").value || "100");
    currentSettings.throttle_speed = parseFloat($("throttle-speed").value || "100");
    currentSettings.steer_reverse = $("steer-reverse").checked;
    currentSettings.throttle_reverse = $("throttle-reverse").checked;
    currentSettings.failsafe_enabled = $("failsafe-enabled").checked;

    currentSettings.video_resolution = $("video-resolution").value;
    currentSettings.video_fps = parseInt($("video-fps").value || "30", 10);
    currentSettings.video_quality = parseFloat($("video-quality").value || "70");
    currentSettings.video_color_order = $("video-color-order").value || "RGB";
    currentSettings.video_flip = $("video-flip").value || "none";

    // Accessories
    const transSel = $("trans-select");
    if (transSel) currentSettings.trans_state = (transSel.value || "low");

    // Lights: keep both selects (if present) in sync, but store one state
    const rcLightsSel = $("rc-lights-select");
    const accLightsSel = $("lights-select");
    const lightsVal = (rcLightsSel && rcLightsSel.value) || (accLightsSel && accLightsSel.value) || "off";
    currentSettings.lights_state = lightsVal;

    // Sync both selects to the chosen state
    if (rcLightsSel) rcLightsSel.value = lightsVal;
    if (accLightsSel) accLightsSel.value = lightsVal;

}

async function saveRadioSettings() {
    if (!currentSettings) return;
    readSettingsFromUI();
    try {
        const resp = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(currentSettings),
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        currentSettings = data.settings;
        applySettingsToUI();
    } catch (err) {
        console.error("saveRadioSettings error:", err);
    }
}

async function saveVideoSettings() {
    if (!currentSettings) return;
    readSettingsFromUI();
    try {
        const resp = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(currentSettings),
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        currentSettings = data.settings;
        applySettingsToUI();
    } catch (err) {
        console.error("saveVideoSettings error:", err);
    }
}

// ------------------------------------------------------------
// Models
// ------------------------------------------------------------

async function loadModels() {
    try {
        const resp = await fetch("/api/models");
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        modelsState = await resp.json();
        renderModelsList();
    } catch (err) {
        console.error("loadModels error:", err);
    }
}

function renderModelsList() {
    const container = $("models-container");
    if (!container) return;
    container.innerHTML = "";

    const models = modelsState.models || [];
    const activeIndex = modelsState.active_index ?? 0;

    models.forEach((model, idx) => {
        const pill = document.createElement("div");
        pill.className = "model-pill" + (idx === activeIndex ? " active" : "");

        const nameSpan = document.createElement("span");
        nameSpan.textContent = model.name || `Model ${idx + 1}`;
        pill.appendChild(nameSpan);

        pill.addEventListener("click", () => {
            modelsState.active_index = idx;
            applyModelToSettings(models[idx]);
            renderModelsList();
        });

        container.appendChild(pill);
    });

    const active = models[activeIndex];
    $("model-name").value = active && active.name ? active.name : "";
}

function applyModelToSettings(model) {
    if (!currentSettings || !model) return;

    currentSettings.steer_trim = model.steer_trim ?? currentSettings.steer_trim ?? 0;
    currentSettings.throttle_trim = model.throttle_trim ?? currentSettings.throttle_trim ?? 0;
    currentSettings.steer_rate = model.steer_rate ?? currentSettings.steer_rate ?? 100;
    currentSettings.throttle_rate = model.throttle_rate ?? currentSettings.throttle_rate ?? 100;
    currentSettings.steer_speed = model.steer_speed ?? currentSettings.steer_speed ?? 100;
    currentSettings.throttle_speed = model.throttle_speed ?? currentSettings.throttle_speed ?? 100;
    currentSettings.steer_reverse = model.steer_reverse ?? currentSettings.steer_reverse ?? false;
    currentSettings.throttle_reverse = model.throttle_reverse ?? currentSettings.throttle_reverse ?? false;

    applySettingsToUI();
}

async function saveModelToSlot() {
    if (!currentSettings) return;
    readSettingsFromUI();

    const nameRaw = $("model-name").value || "";
    const name = nameRaw.trim() || "Model";
    const index = modelsState.active_index ?? -1;

    const model = {
        name,
        steer_trim: currentSettings.steer_trim,
        throttle_trim: currentSettings.throttle_trim,
        steer_rate: currentSettings.steer_rate,
        throttle_rate: currentSettings.throttle_rate,
        steer_speed: currentSettings.steer_speed,
        throttle_speed: currentSettings.throttle_speed,
        steer_reverse: currentSettings.steer_reverse,
        throttle_reverse: currentSettings.throttle_reverse,
    };

    try {
        const resp = await fetch("/api/models/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ index, model }),
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        modelsState.active_index = data.index;
        await loadModels();
    } catch (err) {
        console.error("saveModelToSlot error:", err);
    }
}

async function deleteModelSlot() {
    const idx = modelsState.active_index ?? 0;
    try {
        const resp = await fetch("/api/models/delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ index: idx }),
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        modelsState.active_index = data.active_index;
        await loadModels();
    } catch (err) {
        console.error("deleteModelSlot error:", err);
    }
}

async function renameModelSlot() {
    const idx = modelsState.active_index ?? 0;
    const nameRaw = $("model-name").value || "";
    const name = nameRaw.trim();
    if (!name) return;
    try {
        const resp = await fetch("/api/models/rename", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ index: idx, name }),
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        await loadModels();
    } catch (err) {
        console.error("renameModelSlot error:", err);
    }
}

// ------------------------------------------------------------
// Gamepad + control
// ------------------------------------------------------------

function chooseGamepad() {
    if (!navigator.getGamepads) {
        $("gamepad-label").textContent = "Not supported";
        setStatusDot("dot-gamepad", false);
        return;
    }

    const pads = navigator.getGamepads();
    for (let i = 0; i < pads.length; i++) {
        const gp = pads[i];
        if (gp && gp.connected) {
            gamepadIndex = gp.index;
            $("gamepad-label").textContent = gp.id;
            setStatusDot("dot-gamepad", true);
            console.log("Using gamepad:", gp.id);
            return;
        }
    }

    gamepadIndex = null;
    $("gamepad-label").textContent = "Not connected";
    setStatusDot("dot-gamepad", false);
}

function startSendLoop() {
    if (sendLoopHandle) return;
    const loop = () => {
        readGamepadAndSend();
        sendLoopHandle = requestAnimationFrame(loop);
    };
    sendLoopHandle = requestAnimationFrame(loop);
}

function stopSendLoop() {
    if (sendLoopHandle) {
        cancelAnimationFrame(sendLoopHandle);
        sendLoopHandle = null;
    }
}

async function triggerSystemReboot() {
    console.warn("PS button held 3s: requesting system reboot");
    try {
        await fetch("/api/reboot", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}",
        });
    } catch (err) {
        console.error("Reboot request failed:", err);
    }
}

function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
}

function adjustSteerTrim(delta) {
    if (!currentSettings) return;
    const cur = currentSettings.steer_trim || 0;
    const next = clamp(cur + delta, -30, 30);
    currentSettings.steer_trim = next;

    const slider = $("steer-trim");
    if (slider) slider.value = String(next);

    updateTrimHud();
    saveRadioSettings();
    console.log("Steering trim:", next);
}

function adjustThrottleTrim(delta) {
    if (!currentSettings) return;
    const cur = currentSettings.throttle_trim || 0;
    const next = clamp(cur + delta, -30, 30);
    currentSettings.throttle_trim = next;

    const slider = $("throttle-trim");
    if (slider) slider.value = String(next);

    updateTrimHud();
    saveRadioSettings();
    console.log("Throttle trim:", next);
}

function readGamepadAndSend() {
    if (!currentSettings) return;
    if (!navigator.getGamepads || gamepadIndex == null) {
        chooseGamepad();
        return;
    }

    const pads = navigator.getGamepads();
    const gp = pads[gamepadIndex];
    if (!gp || !gp.connected) {
        chooseGamepad();
        return;
    }

    const now = performance.now();

    // PS button hold → reboot (button 16)
    const psButtonPressed = gp.buttons[16]?.pressed || false;
    if (psButtonPressed) {
        if (psHoldStart === null) {
            psHoldStart = now;
        } else if (!psHoldFired && now - psHoldStart >= 3000) {
            psHoldFired = true;
            triggerSystemReboot();
        }
    } else {
        psHoldStart = null;
        psHoldFired = false;
    }

    // Triangle single-tap → fullscreen toggle (button 3)
    const fullscreenBtnPressed = gp.buttons[3]?.pressed || false;
    if (fullscreenBtnPressed && !lastFullscreenButtonPressed) {
        toggleFullscreen();
    }
    lastFullscreenButtonPressed = fullscreenBtnPressed;


    // Square single-tap → lights toggle (button 2)
    const squarePressed = gp.buttons[2]?.pressed || false;
    if (squarePressed && !lastSquareButtonPressed) {
        toggleLights();
    }
    lastSquareButtonPressed = squarePressed;

    // Circle single-tap → transmission high/low toggle (button 1)
    const circlePressed = gp.buttons[1]?.pressed || false;
    if (circlePressed && !lastCircleButtonPressed) {
        toggleTransmission();
    }
    lastCircleButtonPressed = circlePressed;

    const l1Pressed = gp.buttons[4]?.pressed || false;

    const dpadUp = gp.buttons[12]?.pressed || false;
    const dpadDown = gp.buttons[13]?.pressed || false;
    const dpadLeft = gp.buttons[14]?.pressed || false;
    const dpadRight = gp.buttons[15]?.pressed || false;

    if (l1Pressed) {
        // Trims when L1 held
        if (dpadLeft && !lastTrimLeftPressed) {
            adjustSteerTrim(-1);
        }
        if (dpadRight && !lastTrimRightPressed) {
            adjustSteerTrim(+1);
        }
        if (dpadDown && !lastTrimDownPressed) {
            adjustThrottleTrim(-1);
        }
        if (dpadUp && !lastTrimUpPressed) {
            adjustThrottleTrim(+1);
        }

        lastTrimLeftPressed = dpadLeft;
        lastTrimRightPressed = dpadRight;
        lastTrimDownPressed = dpadDown;
        lastTrimUpPressed = dpadUp;

        // prevent connect/record triggers while trimming
        lastDpadRightPressed = dpadRight;
        lastDpadUpPressed = dpadUp;
    } else {
        lastTrimLeftPressed = false;
        lastTrimRightPressed = false;
        lastTrimDownPressed = false;
        lastTrimUpPressed = false;

        // D-pad up → connect video
        if (dpadUp && !lastDpadUpPressed) {
            startWebRTC();
        }
        lastDpadUpPressed = dpadUp;

        // D-pad right → record toggle
        if (dpadRight && !lastDpadRightPressed) {
            toggleRecording();
        }
        lastDpadRightPressed = dpadRight;
    }

    // Steering: left stick X
    const steerAxis = gp.axes[0] || 0.0;

    // Throttle: R2 - L2
    let l2 = 0.0;
    let r2 = 0.0;

    if (gp.axes.length >= 6) {
        let aL2 = gp.axes[2];
        let aR2 = gp.axes[5];

        if (typeof aL2 === "number") {
            if (aL2 < 0) aL2 = aL2 + 1;
            l2 = Math.min(Math.max(aL2, 0), 1);
        }
        if (typeof aR2 === "number") {
            if (aR2 < 0) aR2 = aR2 + 1;
            r2 = Math.min(Math.max(aR2, 0), 1);
        }
    }

    if (gp.buttons.length >= 8) {
        if (gp.buttons[6]?.pressed) {
            l2 = Math.max(l2, gp.buttons[6].value || 1);
        }
        if (gp.buttons[7]?.pressed) {
            r2 = Math.max(r2, gp.buttons[7].value || 1);
        }
    }

    let throttleAxis = r2 - l2;

    const steerTrim = currentSettings.steer_trim || 0.0;
    const throttleTrim = currentSettings.throttle_trim || 0.0;
    const steerRate = (currentSettings.steer_rate || 100.0) / 100.0;
    const throttleRate = (currentSettings.throttle_rate || 100.0) / 100.0;
    const steerRev = !!currentSettings.steer_reverse;
    const throttleRev = !!currentSettings.throttle_reverse;

    let steerNorm = steerAxis;
    let throttleNorm = throttleAxis;

    if (steerRev) steerNorm *= -1;
    if (throttleRev) throttleNorm *= -1;

    steerNorm *= steerRate;
    throttleNorm *= throttleRate;

    let steerDeg = 90 + steerNorm * 90 + steerTrim;
    let throttleDeg = 90 + throttleNorm * 90 + throttleTrim;

    steerDeg = clamp(steerDeg, 0, 180);
    throttleDeg = clamp(throttleDeg, 0, 180);

    if (now - lastSendTime < 20) {
        return;
    }
    lastSendTime = now;

    sendControl(steerDeg, throttleDeg);
}


// ------------------------------------------------------------
// Accessories (Lights + Transmission)
// ------------------------------------------------------------
async function setLightsState(state) {
    if (!currentSettings) return;
    const next = (state || "").toLowerCase() === "on" ? "on" : "off";
    currentSettings.lights_state = next;

    const sel1 = $("rc-lights-select");
    const sel2 = $("lights-select");
    if (sel1) sel1.value = next;
    if (sel2) sel2.value = next;

    try {
        await fetch("/api/lights", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ state: next }),
        });
    } catch (err) {
        console.error("setLightsState error:", err);
    }
}

async function setTransmissionState(state) {
    if (!currentSettings) return;
    const next = (state || "").toLowerCase() === "high" ? "high" : "low";
    currentSettings.trans_state = next;

    const sel = $("trans-select");
    if (sel) sel.value = next;

    try {
        await fetch("/api/transmission", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ state: next }),
        });
    } catch (err) {
        console.error("setTransmissionState error:", err);
    }
}

function toggleLights() {
    const cur = (currentSettings && currentSettings.lights_state) ? String(currentSettings.lights_state).toLowerCase() : "off";
    const next = cur === "on" ? "off" : "on";
    // fire-and-forget
    setLightsState(next);
}

function toggleTransmission() {
    const cur = (currentSettings && currentSettings.trans_state) ? String(currentSettings.trans_state).toLowerCase() : "low";
    const next = cur === "high" ? "low" : "high";
    setTransmissionState(next);
}

async function sendControl(steer, throttle) {
    try {
        await fetch("/api/control", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ steer, throttle }),
        });
    } catch (err) {
        console.error("sendControl error:", err);
    }
}

// ------------------------------------------------------------
// Fullscreen
// ------------------------------------------------------------

function toggleFullscreen() {
    const wrapper = $("video-wrapper");
    const target = wrapper || document.documentElement;

    if (!document.fullscreenElement) {
        target.requestFullscreen().catch((err) =>
            console.error("fullscreen error:", err)
        );
    } else {
        document.exitFullscreen().catch((err) =>
            console.error("exit fullscreen error:", err)
        );
    }
}

function onFullscreenChange() {
    const btn = $("btn-fullscreen");
    const wrapper = $("video-wrapper");
    const isFs = !!document.fullscreenElement;

    if (btn) {
        btn.textContent = isFs ? "Exit fullscreen" : "Fullscreen";
    }

    if (wrapper) {
        if (isFs && document.fullscreenElement === wrapper) {
            wrapper.classList.add("fullscreen-active");
        } else {
            wrapper.classList.remove("fullscreen-active");
        }
    }
}

// click on video → exit fullscreen (only if already fullscreen)
function onVideoClick() {
    if (document.fullscreenElement) {
        document.exitFullscreen().catch((err) =>
            console.error("exit fullscreen error:", err)
        );
    }
}

// ------------------------------------------------------------
// Recording
// ------------------------------------------------------------

function toggleRecording() {
    if (isRecording) {
        stopRecording();
    } else {
        startRecording();
    }
}

function startRecording() {
    if (isRecording) return;
    if (!remoteVideo || !remoteVideo.srcObject) {
        console.warn("No video stream to record");
        return;
    }

    try {
        mediaRecorder = new MediaRecorder(remoteVideo.srcObject);
    } catch (err) {
        console.error("Unable to start MediaRecorder:", err);
        return;
    }

    recordedChunks = [];

    mediaRecorder.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) {
            recordedChunks.push(ev.data);
        }
    };

    mediaRecorder.onstop = () => {
        if (!recordedChunks.length) return;

        const blob = new Blob(recordedChunks, { type: "video/webm" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        const ts = new Date().toISOString().replace(/[:.]/g, "-");
        a.href = url;
        a.download = `fpv-recording-${ts}.webm`;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 0);
    };

    mediaRecorder.start(1000);
    isRecording = true;
    const btn = $("btn-record");
    if (btn) btn.textContent = "Stop Rec";
    setRecordingIndicator(true);
    console.log("Recording started");
}

function stopRecording() {
    if (!isRecording) return;

    try {
        if (mediaRecorder && mediaRecorder.state !== "inactive") {
            mediaRecorder.stop();
        }
    } catch (err) {
        console.warn("Error stopping MediaRecorder:", err);
    }

    isRecording = false;
    const btn = $("btn-record");
    if (btn) btn.textContent = "Record";
    setRecordingIndicator(false);
    console.log("Recording stopped");
}

// ------------------------------------------------------------
// Init
// ------------------------------------------------------------

function init() {
    remoteVideo = $("remoteVideo");

    $("btn-connect-video").addEventListener("click", startWebRTC);
    $("btn-disconnect-video").addEventListener("click", stopWebRTC);
    $("btn-fullscreen").addEventListener("click", toggleFullscreen);
    $("btn-record").addEventListener("click", toggleRecording);

    // click on video = exit fullscreen
    if (remoteVideo) {
        remoteVideo.addEventListener("click", onVideoClick);
    }

    $("btn-save-settings").addEventListener("click", saveRadioSettings);
    $("btn-save-video").addEventListener("click", saveVideoSettings);

    $("btn-save-model").addEventListener("click", saveModelToSlot);
    $("btn-new-model").addEventListener("click", () => {
        modelsState.active_index = (modelsState.models || []).length;
        $("model-name").value = "";
        saveModelToSlot();
    });
    $("btn-delete-model").addEventListener("click", deleteModelSlot);
    $("model-name").addEventListener("change", renameModelSlot);

    const updateResLabel = () => {
        const res = $("video-resolution").value;
        const fps = $("video-fps").value;
        const q = $("video-quality").value;
        const color = $("video-color-order").value;
        $("res-value").textContent = `${res} @ ${fps}fps Q${q} ${color}`;
    };
    $("video-resolution").addEventListener("change", updateResLabel);
    $("video-fps").addEventListener("change", updateResLabel);
    $("video-quality").addEventListener("change", updateResLabel);
    $("video-color-order").addEventListener("change", updateResLabel);


    // Accessories selects → drive hardware immediately (no index.html changes)
    const transSel = $("trans-select");
    if (transSel) {
        transSel.addEventListener("change", () => setTransmissionState(transSel.value));
    }

    const rcLightsSel = $("rc-lights-select");
    if (rcLightsSel) {
        rcLightsSel.addEventListener("change", () => setLightsState(rcLightsSel.value));
    }

    const accLightsSel = $("lights-select");
    if (accLightsSel) {
        accLightsSel.addEventListener("change", () => setLightsState(accLightsSel.value));
    }

    // Trim sliders update HUD when moved by mouse/touch
    $("steer-trim").addEventListener("input", () => {
        if (!currentSettings) return;
        currentSettings.steer_trim = parseFloat($("steer-trim").value || "0");
        updateTrimHud();
    });
    $("throttle-trim").addEventListener("input", () => {
        if (!currentSettings) return;
        currentSettings.throttle_trim = parseFloat($("throttle-trim").value || "0");
        updateTrimHud();
    });

    window.addEventListener("gamepadconnected", () => chooseGamepad());
    window.addEventListener("gamepaddisconnected", () => chooseGamepad());

    document.addEventListener("fullscreenchange", onFullscreenChange);

    setRecordingIndicator(false);

    loadSettings().then(loadModels);
    chooseGamepad();
    startSendLoop();

    doPing();
    pingTimer = setInterval(doPing, 2000);
}

window.addEventListener("load", init);
