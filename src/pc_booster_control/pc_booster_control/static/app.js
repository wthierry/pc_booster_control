const statusEl = document.getElementById("status");
const outputEl = document.getElementById("output");
const audioWidgetEl = document.getElementById("audioWidget");
const audioTextEl = document.getElementById("audioText");
const batteryTextEl = document.getElementById("batteryText");
const batteryFillEl = document.getElementById("batteryFill");
const batteryAlertEl = document.getElementById("batteryAlert");
const dampBtn = document.getElementById("dampBtn");
const prepBtn = document.getElementById("prepBtn");
const speakTextEl = document.getElementById("speakText");
const speakBtn = document.getElementById("speakBtn");
const speakReadyEl = document.getElementById("speakReady");
const voiceTypeEl = document.getElementById("voiceType");
const customVoiceEl = document.getElementById("customVoice");
const volumeSliderEl = document.getElementById("volumeSlider");
const volumeTextEl = document.getElementById("volumeText");
const motorsStatusEl = document.getElementById("motorsStatus");
const motorsTableBodyEl = document.getElementById("motorsTableBody");
const micToggleEl = document.getElementById("micToggle");
const cmdInputEl = document.getElementById("cmdInput");
const cmdRunBtnEl = document.getElementById("cmdRunBtn");
const SPEECH_MODULE_ENABLED = true;
const MICROPHONE_MODULE_ENABLED = false;
let volumeSetTimer = null;
let volumeSetInFlight = false;
let pendingVolumePercent = null;
let micToggleSyncing = false;
let debugCursor = 0;

function appendDebugLine(line) {
  const atBottom = outputEl.scrollTop + outputEl.clientHeight >= outputEl.scrollHeight - 20;
  if (outputEl.textContent) {
    outputEl.textContent += `\n${line}`;
  } else {
    outputEl.textContent = line;
  }
  if (atBottom) {
    outputEl.scrollTop = outputEl.scrollHeight;
  }
}

function appendDebugObject(prefix, data) {
  const text = typeof data === "string" ? data : JSON.stringify(data);
  appendDebugLine(`[ui] ${prefix}: ${text}`);
}

async function api(path) {
  const response = await fetch(path);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || JSON.stringify(data));
  }
  return data;
}

async function apiPost(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : "{}",
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || JSON.stringify(data));
  }
  return data;
}

async function refreshHealth() {
  try {
    const data = await api("/api/health");
    updateBattery(data.battery_percent, data.battery_status);
    updateVolume(data.volume_percent);
    updateModeButtons(data.mode_ui_state || "damp");
    updateSpeakReady(data.ai_ready, data.ai_starting, data.ai_error, data.ai_voice_type);
    updateMicrophone(Boolean(data.mic_enabled), Boolean(data.ai_starting));

    if (!data.ros_available) {
      statusEl.textContent = `Backend running, ROS2 unavailable on this machine: ${data.ros_import_error}`;
      statusEl.style.color = "#b91c1c";
      return;
    }

    if (data.has_color_frame) {
      statusEl.textContent = "Camera stream active";
      statusEl.style.color = "#0f766e";
      return;
    }

    statusEl.textContent = `Waiting for camera frames on ${data.color_topic}`;
    statusEl.style.color = "#b45309";
  } catch (err) {
    statusEl.textContent = `Backend error: ${err.message}`;
    statusEl.style.color = "#b91c1c";
    appendDebugObject("health error", err.message || String(err));
  }
}

async function refreshDebug() {
  try {
    const data = await api(`/api/debug?since=${debugCursor}&limit=250`);
    if (Array.isArray(data.lines)) {
      for (const line of data.lines) {
        appendDebugLine(line);
      }
    }
    if (typeof data.next === "number") {
      debugCursor = data.next;
    }
  } catch (err) {
    appendDebugObject("debug stream error", err.message || String(err));
  }
}

async function refreshAudioActivity() {
  try {
    const data = await api("/api/audio/activity");
    const active = Boolean(data.ok) && Boolean(data.active);
    const level = Number(data.level || 0);
    audioWidgetEl.classList.toggle("active", active);
    if (active) {
      audioTextEl.textContent = `Hearing ${(level * 100).toFixed(0)}%`;
      return;
    }
    if (!data.ok) {
      const err = String(data.error || "");
      if (err.includes("Device or resource busy")) {
        audioTextEl.textContent = "Mic busy";
      } else {
        audioTextEl.textContent = "Mic unavailable";
      }
      return;
    }
    audioTextEl.textContent = "Mic idle";
  } catch (err) {
    audioWidgetEl.classList.remove("active");
    audioTextEl.textContent = "Mic unknown";
  }
}

async function submitCommand() {
  const cmd = (cmdInputEl.value || "").trim();
  if (!cmd) {
    appendDebugLine("[ui] command error: empty command");
    return;
  }
  cmdRunBtnEl.disabled = true;
  cmdInputEl.disabled = true;
  appendDebugLine(`[ui] run command: ${cmd}`);
  try {
    const data = await apiPost("/api/command", { cmd, timeout_sec: 15 });
    appendDebugObject("command result", data);
  } catch (err) {
    appendDebugObject("command error", err.message || String(err));
  } finally {
    cmdRunBtnEl.disabled = false;
    cmdInputEl.disabled = false;
    cmdInputEl.focus();
    cmdInputEl.select();
  }
}

async function refreshMotors() {
  try {
    const data = await api("/api/motors");
    renderMotors(data.motors || []);
    const count = Number(data.count || 0);
    motorsStatusEl.textContent = count > 0 ? `Motors online: ${count}` : "No motors parsed yet";
    motorsStatusEl.style.color = count > 0 ? "#0f766e" : "#b45309";
    if (data.error) {
      motorsStatusEl.textContent = `Motor read warning: ${data.error}`;
      motorsStatusEl.style.color = "#b45309";
    }
  } catch (err) {
    motorsStatusEl.textContent = `Motor telemetry error: ${err.message}`;
    motorsStatusEl.style.color = "#b91c1c";
  }
}

function renderMotors(motors) {
  motorsTableBodyEl.innerHTML = "";
  if (!Array.isArray(motors) || motors.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td colspan='3'>No motor data</td>";
    motorsTableBodyEl.appendChild(tr);
    return;
  }

  for (const m of motors) {
    const tr = document.createElement("tr");
    const position = m.position_rad == null ? "--" : Number(m.position_rad).toFixed(3);
    const temp = m.temperature_c == null ? "--" : `${m.temperature_c}`;
    tr.innerHTML = `<td>${m.name || "--"}</td><td>${position}</td><td>${temp}</td>`;
    motorsTableBodyEl.appendChild(tr);
  }
}

function updateBattery(percent, status) {
  if (percent == null || Number.isNaN(Number(percent))) {
    batteryTextEl.textContent = "--%";
    batteryFillEl.style.width = "0%";
    batteryFillEl.style.background = "#6b7280";
    batteryAlertEl.textContent = "";
    return;
  }

  const p = Math.max(0, Math.min(100, Number(percent)));
  batteryTextEl.textContent = `${p.toFixed(0)}%${status ? ` (${status})` : ""}`;
  batteryFillEl.style.width = `${p}%`;

  if (p <= 10) {
    batteryFillEl.style.background = "#991b1b";
    batteryAlertEl.textContent = "SHUTDOWN IMMINENT (10%): recharge immediately.";
  } else if (p <= 15) {
    batteryFillEl.style.background = "#dc2626";
    batteryAlertEl.textContent = "CRITICAL BATTERY (15%): recharge now.";
  } else if (p <= 35) {
    batteryFillEl.style.background = "#d97706";
    batteryAlertEl.textContent = "";
  } else {
    batteryFillEl.style.background = "#16a34a";
    batteryAlertEl.textContent = "";
  }
}

function updateModeButtons(modeState) {
  const damp = (modeState || "").toLowerCase() === "damp";
  dampBtn.disabled = damp;
  prepBtn.disabled = !damp;
}

function updateSpeakReady(isReady, isStarting, error, voiceType) {
  if (!SPEECH_MODULE_ENABLED) {
    speakTextEl.disabled = true;
    speakBtn.disabled = true;
    voiceTypeEl.disabled = true;
    customVoiceEl.disabled = true;
    speakReadyEl.textContent = "Speech module disabled (reserved for custom implementation).";
    speakReadyEl.style.color = "#64748b";
    return;
  }
  const ready = Boolean(isReady);
  const starting = Boolean(isStarting);
  const canUse = ready || !starting;
  speakTextEl.disabled = !canUse;
  speakBtn.disabled = !canUse;
  voiceTypeEl.disabled = !canUse;
  customVoiceEl.disabled = !canUse;

  if (ready) {
    speakReadyEl.textContent = `Speech ready${voiceType ? ` (${voiceType})` : ""}`;
    speakReadyEl.style.color = "#0f766e";
    return;
  }
  if (isStarting) {
    speakReadyEl.textContent = "Initializing speech engine...";
    speakReadyEl.style.color = "#b45309";
    return;
  }
  if (error) {
    speakReadyEl.textContent = `Speech init error: ${error}`;
    speakReadyEl.style.color = "#b91c1c";
    return;
  }
  if (!ready) {
    speakReadyEl.textContent = "Speech idle. Press Speak to initialize.";
    speakReadyEl.style.color = "#64748b";
    return;
  }
  speakReadyEl.textContent = "Speech not ready.";
  speakReadyEl.style.color = "#b45309";
}

function updateVolume(percent) {
  if (percent == null || Number.isNaN(Number(percent))) {
    volumeTextEl.textContent = "--%";
    return;
  }
  const p = Math.max(0, Math.min(100, Number(percent)));
  volumeTextEl.textContent = `${p.toFixed(0)}%`;
  if (!volumeSliderEl.matches(":active")) {
    volumeSliderEl.value = `${p.toFixed(0)}`;
  }
}

function updateMicrophone(enabled, aiStarting) {
  if (!MICROPHONE_MODULE_ENABLED) {
    micToggleSyncing = true;
    micToggleEl.checked = false;
    micToggleEl.disabled = true;
    micToggleSyncing = false;
    return;
  }
  micToggleSyncing = true;
  micToggleEl.checked = Boolean(enabled);
  micToggleEl.disabled = Boolean(aiStarting);
  micToggleSyncing = false;
}

async function setVolume(percent) {
  if (volumeSetInFlight) {
    pendingVolumePercent = percent;
    return;
  }
  try {
    volumeSetInFlight = true;
    const data = await apiPost("/api/volume", { percent: Number(percent) });
    if (data && data.percent != null) {
      updateVolume(data.percent);
    }
    appendDebugObject("volume", data);
  } catch (err) {
    appendDebugObject("volume error", err.message || String(err));
  } finally {
    volumeSetInFlight = false;
    if (pendingVolumePercent != null) {
      const next = pendingVolumePercent;
      pendingVolumePercent = null;
      setVolume(next);
    }
  }
}

micToggleEl.addEventListener("change", async () => {
  if (!MICROPHONE_MODULE_ENABLED) {
    micToggleEl.checked = false;
    appendDebugLine("[ui] microphone disabled in this build");
    return;
  }
  if (micToggleSyncing) {
    return;
  }
  const target = micToggleEl.checked;
  micToggleEl.disabled = true;
  try {
    const data = await apiPost("/api/microphone", { enabled: target });
    appendDebugObject("microphone", data);
    updateMicrophone(Boolean(data.enabled), false);
  } catch (err) {
    appendDebugObject("microphone error", err.message || String(err));
    micToggleEl.checked = !target;
    micToggleEl.disabled = false;
  }
});

dampBtn.addEventListener("click", async () => {
  try {
    const data = await apiPost("/api/mode/damp");
    appendDebugObject("mode damp", data);
    updateModeButtons(data.mode_ui_state || "damp");
  } catch (err) {
    appendDebugObject("mode damp error", err.message || String(err));
  }
});

prepBtn.addEventListener("click", async () => {
  try {
    const data = await apiPost("/api/mode/prep");
    appendDebugObject("mode prep", data);
    updateModeButtons(data.mode_ui_state || "damp");
  } catch (err) {
    appendDebugObject("mode prep error", err.message || String(err));
  }
});

async function submitSpeak() {
  if (!SPEECH_MODULE_ENABLED) {
    appendDebugLine("[ui] speak disabled: speech module removed");
    return;
  }
  if (speakBtn.disabled) {
    appendDebugLine("[ui] speak blocked: AI chat is not ready yet");
    return;
  }
  const text = (speakTextEl.value || "").trim();
  if (!text) {
    appendDebugLine("[ui] speak error: text is empty");
    return;
  }
  const selected = voiceTypeEl.value === "custom" ? (customVoiceEl.value || "").trim() : voiceTypeEl.value;
  if (!selected) {
    appendDebugLine("[ui] speak error: voice is empty");
    return;
  }
  try {
    speakBtn.disabled = true;
    const data = await apiPost("/api/speak", { text, voice_type: selected });
    appendDebugObject("speak", data);
  } catch (err) {
    appendDebugObject("speak error", err.message || String(err));
  } finally {
    speakBtn.disabled = false;
  }
}

speakBtn.addEventListener("click", submitSpeak);

speakTextEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitSpeak();
  }
});

voiceTypeEl.addEventListener("change", () => {
  if (!SPEECH_MODULE_ENABLED) {
    customVoiceEl.style.display = "none";
    return;
  }
  customVoiceEl.style.display = voiceTypeEl.value === "custom" ? "block" : "none";
});

volumeSliderEl.addEventListener("input", () => {
  volumeTextEl.textContent = `${volumeSliderEl.value}%`;
  if (volumeSetTimer) {
    clearTimeout(volumeSetTimer);
  }
  volumeSetTimer = setTimeout(() => {
    setVolume(Number(volumeSliderEl.value));
  }, 250);
});

volumeSliderEl.addEventListener("change", () => {
  setVolume(Number(volumeSliderEl.value));
});

cmdRunBtnEl.addEventListener("click", submitCommand);
cmdInputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    submitCommand();
  }
});

updateSpeakReady(false, true, null, null);
updateMicrophone(false, true);
outputEl.textContent = "";
appendDebugLine("[ui] debug stream connected");
refreshHealth();
refreshMotors();
refreshDebug();
refreshAudioActivity();
setInterval(refreshHealth, 2000);
setInterval(refreshMotors, 3000);
setInterval(refreshDebug, 1000);
setInterval(refreshAudioActivity, 700);
