const statusEl = document.getElementById("status");
const outputEl = document.getElementById("output");
const audioWidgetEl = document.getElementById("audioWidget");
const audioTextEl = document.getElementById("audioText");
const batteryTextEl = document.getElementById("batteryText");
const batteryFillEl = document.getElementById("batteryFill");
const batteryAlertEl = document.getElementById("batteryAlert");
const streamsToggleBtnEl = document.getElementById("streamsToggleBtn");
const streamsGridEl = document.getElementById("streamsGrid");
const colorStreamCardEl = document.getElementById("colorStreamCard");
const colorStreamEl = document.getElementById("colorStream");
const colorStreamPlaceholderEl = document.getElementById("colorStreamPlaceholder");
const dampBtn = document.getElementById("dampBtn");
const prepBtn = document.getElementById("prepBtn");
const speakTextEl = document.getElementById("speakText");
const speakBtn = document.getElementById("speakBtn");
const speakReadyEl = document.getElementById("speakReady");
const llmBackendEl = document.getElementById("llmBackend");
const llmModelEl = document.getElementById("llmModel");
const ttsEnabledEl = document.getElementById("ttsEnabled");
const speechBackendEl = document.getElementById("speechBackend");
const playbackTargetEl = document.getElementById("playbackTarget");
const voiceTypeEl = document.getElementById("voiceType");
const customVoiceEl = document.getElementById("customVoice");
const piperRateGroupEl = document.getElementById("piperRateGroup");
const piperRateSliderEl = document.getElementById("piperRateSlider");
const piperRateTextEl = document.getElementById("piperRateText");
const piperNoiseScaleGroupEl = document.getElementById("piperNoiseScaleGroup");
const piperNoiseScaleSliderEl = document.getElementById("piperNoiseScaleSlider");
const piperNoiseScaleTextEl = document.getElementById("piperNoiseScaleText");
const piperNoiseWGroupEl = document.getElementById("piperNoiseWGroup");
const piperNoiseWSliderEl = document.getElementById("piperNoiseWSlider");
const piperNoiseWTextEl = document.getElementById("piperNoiseWText");
const piperSentenceSilenceGroupEl = document.getElementById("piperSentenceSilenceGroup");
const piperSentenceSilenceSliderEl = document.getElementById("piperSentenceSilenceSlider");
const piperSentenceSilenceTextEl = document.getElementById("piperSentenceSilenceText");
const appleRateGroupEl = document.getElementById("appleRateGroup");
const appleRateSliderEl = document.getElementById("appleRateSlider");
const appleRateTextEl = document.getElementById("appleRateText");
const replyWindowEl = document.getElementById("replyWindow");
const replyMetaEl = document.getElementById("replyMeta");
const replyTextEl = document.getElementById("replyText");
const volumeSliderEl = document.getElementById("volumeSlider");
const volumeTextEl = document.getElementById("volumeText");
const motorsStatusEl = document.getElementById("motorsStatus");
const motorsTableBodyEl = document.getElementById("motorsTableBody");
const micSourceEl = document.getElementById("micSource");
const micToggleEl = document.getElementById("micToggle");
const micHeardMetaEl = document.getElementById("micHeardMeta");
const micHeardTextEl = document.getElementById("micHeardText");
const cmdInputEl = document.getElementById("cmdInput");
const cmdRunBtnEl = document.getElementById("cmdRunBtn");
const SPEECH_MODULE_ENABLED = true;
const MICROPHONE_MODULE_ENABLED = true;
let volumeSetTimer = null;
let volumeSetInFlight = false;
let pendingVolumePercent = null;
let micToggleSyncing = false;
let lastMicTranscriptSeen = "";
let lastMicStatus = null;
let debugCursor = 0;
let activeSpeechAudio = null;
let colorStreamAttached = false;
let streamsAvailable = false;
let streamsExpanded = false;
let preloadInFlight = false;
let preloadErrorText = null;
let preloadSequence = 0;
let voicesLoaded = false;
let speechReadyState = {
  ready: false,
  starting: true,
  error: null,
  voiceType: null,
  backend: null,
};
const DEFAULT_OPENAI_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"];
const MAC_LOCAL_VOICES_URL = "http://127.0.0.1:8000/api/voices";
const STORAGE_KEYS = {
  llmBackend: "booster.llm.backend",
  llmModelOpenai: "booster.llm.model.openai",
  llmModelOllama: "booster.llm.model.ollama",
  ttsEnabled: "booster.speech.enabled",
  speechBackend: "booster.speech.backend",
  playbackTarget: "booster.speech.playbackTarget",
  piperVoice: "booster.speech.voice.piper",
  openaiVoice: "booster.speech.voice.openai",
  appleVoice: "booster.speech.voice.apple",
  kokoroVoice: "booster.speech.voice.kokoro",
  piperCustomVoice: "booster.speech.customVoice.piper",
  openaiCustomVoice: "booster.speech.customVoice.openai",
  appleCustomVoice: "booster.speech.customVoice.apple",
  kokoroCustomVoice: "booster.speech.customVoice.kokoro",
  piperRate: "booster.speech.piperRate",
  piperNoiseScale: "booster.speech.piperNoiseScale",
  piperNoiseW: "booster.speech.piperNoiseW",
  piperSentenceSilence: "booster.speech.piperSentenceSilence",
  appleRate: "booster.speech.appleRate",
  micSource: "booster.mic.source",
};
let llmCatalog = {
  defaultBackend: "openai",
  backends: [
    { id: "openai", label: "OpenAI" },
    { id: "ollama", label: "Ollama (qwen2.5:14b)" },
  ],
  openai: { defaultModel: "gpt-4.1-mini", models: ["gpt-4.1-mini"] },
  ollama: { defaultModel: "qwen2.5:14b", models: [] },
};
let voiceCatalog = {
  defaultBackend: "piper",
  piper: {
    defaultVoice: "",
    voices: [],
    defaultRate: 1.0,
    defaultNoiseScale: 0.667,
    defaultNoiseW: 0.8,
    defaultSentenceSilence: 0.2,
    voiceDefaults: {},
  },
  openai: { defaultVoice: "alloy", voices: DEFAULT_OPENAI_VOICES },
  apple: { defaultVoice: "Daniel", voices: [], defaultRate: 1.0 },
  kokoro: { defaultVoice: "af_heart", voices: [] },
};

function isLoopbackHost(hostname) {
  const value = String(hostname || "").trim().toLowerCase();
  return value === "127.0.0.1" || value === "localhost" || value === "::1";
}

function shouldTryMacVoiceCatalog() {
  return typeof window !== "undefined" && !isLoopbackHost(window.location.hostname);
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function mergeTtsCatalog(robotData, macData) {
  if (!macData || typeof macData !== "object" || macData.ok !== true) {
    return { data: robotData, source: "robot" };
  }
  return {
    source: "mac-local",
    data: {
      ...robotData,
      voice_dir: macData.voice_dir || robotData.voice_dir,
      default_backend: macData.default_backend || robotData.default_backend,
      default_voice: macData.default_voice || robotData.default_voice,
      voices: Array.isArray(macData.voices) ? macData.voices : robotData.voices,
      backends:
        Array.isArray(macData.backends) && macData.backends.length > 0 ? macData.backends : robotData.backends,
      piper: macData.piper || robotData.piper,
      openai: macData.openai || robotData.openai,
      apple: macData.apple || robotData.apple,
      kokoro: macData.kokoro || robotData.kokoro,
    },
  };
}

function getStoredSetting(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (_err) {
    return null;
  }
}

function getSelectedMicSource() {
  return micSourceEl && micSourceEl.value === "mac" ? "mac" : "robot";
}

function getSelectedMicLabel() {
  return getSelectedMicSource() === "mac" ? "Mac mic" : "Robot mic";
}

function setStoredSetting(key, value) {
  try {
    if (value == null || value === "") {
      window.localStorage.removeItem(key);
      return;
    }
    window.localStorage.setItem(key, String(value));
  } catch (_err) {
    // ignore storage failures
  }
}

function voiceStorageKeyForBackend(backend) {
  if (backend === "openai") {
    return STORAGE_KEYS.openaiVoice;
  }
  if (backend === "apple") {
    return STORAGE_KEYS.appleVoice;
  }
  if (backend === "kokoro") {
    return STORAGE_KEYS.kokoroVoice;
  }
  return STORAGE_KEYS.piperVoice;
}

function customVoiceStorageKeyForBackend(backend) {
  if (backend === "openai") {
    return STORAGE_KEYS.openaiCustomVoice;
  }
  if (backend === "apple") {
    return STORAGE_KEYS.appleCustomVoice;
  }
  if (backend === "kokoro") {
    return STORAGE_KEYS.kokoroCustomVoice;
  }
  return STORAGE_KEYS.piperCustomVoice;
}

function formatPiperRate(rateValue) {
  const value = Number(rateValue);
  if (Number.isNaN(value) || value <= 0) {
    return "1.00x";
  }
  return `${value.toFixed(2)}x`;
}

function formatPiperValue(value) {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return "0.00";
  }
  return parsed.toFixed(2);
}

function formatPiperSeconds(value) {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return "0.00s";
  }
  return `${parsed.toFixed(2)}s`;
}

function getPiperDefaultsForVoice(voiceId) {
  const fallback = {
    rate: Number(voiceCatalog.piper.defaultRate) || 1.0,
    noise_scale: Number(voiceCatalog.piper.defaultNoiseScale) || 0.667,
    noise_w: Number(voiceCatalog.piper.defaultNoiseW) || 0.8,
    sentence_silence: Number(voiceCatalog.piper.defaultSentenceSilence) || 0.2,
  };
  if (!voiceId || voiceId === "custom") {
    return fallback;
  }
  const map = voiceCatalog.piper && voiceCatalog.piper.voiceDefaults ? voiceCatalog.piper.voiceDefaults : {};
  const selected = map[voiceId];
  if (!selected || typeof selected !== "object") {
    return fallback;
  }
  return {
    rate: Number(selected.rate) || fallback.rate,
    noise_scale: Number(selected.noise_scale) || fallback.noise_scale,
    noise_w: Number(selected.noise_w) || fallback.noise_w,
    sentence_silence:
      Number.isFinite(Number(selected.sentence_silence)) ? Number(selected.sentence_silence) : fallback.sentence_silence,
  };
}

function applyPiperDefaultsForSelectedVoice() {
  if (getSelectedSpeechBackend() !== "piper") {
    return;
  }
  const defaults = getPiperDefaultsForVoice(voiceTypeEl.value);
  piperRateSliderEl.value = `${defaults.rate}`;
  piperRateTextEl.textContent = formatPiperRate(defaults.rate);
  setStoredSetting(STORAGE_KEYS.piperRate, defaults.rate);
  piperNoiseScaleSliderEl.value = `${defaults.noise_scale}`;
  piperNoiseScaleTextEl.textContent = formatPiperValue(defaults.noise_scale);
  setStoredSetting(STORAGE_KEYS.piperNoiseScale, defaults.noise_scale);
  piperNoiseWSliderEl.value = `${defaults.noise_w}`;
  piperNoiseWTextEl.textContent = formatPiperValue(defaults.noise_w);
  setStoredSetting(STORAGE_KEYS.piperNoiseW, defaults.noise_w);
  piperSentenceSilenceSliderEl.value = `${defaults.sentence_silence}`;
  piperSentenceSilenceTextEl.textContent = formatPiperSeconds(defaults.sentence_silence);
  setStoredSetting(STORAGE_KEYS.piperSentenceSilence, defaults.sentence_silence);
}

function setLlmBackendOptions(backends, defaultBackend) {
  const normalized = Array.isArray(backends) ? backends : [];
  llmBackendEl.innerHTML = "";
  for (const item of normalized) {
    if (!item || typeof item.id !== "string") {
      continue;
    }
    const opt = document.createElement("option");
    opt.value = item.id;
    opt.textContent = typeof item.label === "string" && item.label.trim() ? item.label : item.id;
    llmBackendEl.appendChild(opt);
  }
  const stored = getStoredSetting(STORAGE_KEYS.llmBackend);
  const availableIds = normalized.map((item) => item.id);
  if (stored && availableIds.includes(stored)) {
    llmBackendEl.value = stored;
  } else if (defaultBackend && availableIds.includes(defaultBackend)) {
    llmBackendEl.value = defaultBackend;
  } else if (availableIds.includes("openai")) {
    llmBackendEl.value = "openai";
  } else if (availableIds.length > 0) {
    llmBackendEl.value = availableIds[0];
  }
  setStoredSetting(STORAGE_KEYS.llmBackend, llmBackendEl.value);
}

function llmModelStorageKeyForBackend(backend) {
  return backend === "ollama" ? STORAGE_KEYS.llmModelOllama : STORAGE_KEYS.llmModelOpenai;
}

function refreshLlmModelOptions() {
  const backend = llmBackendEl.value === "ollama" ? "ollama" : "openai";
  const catalog = backend === "ollama" ? llmCatalog.ollama : llmCatalog.openai;
  const models = Array.isArray(catalog.models) ? catalog.models.filter((m) => typeof m === "string" && m.trim()) : [];
  const defaultModel = catalog.defaultModel || (models.length > 0 ? models[0] : "");
  const stored = getStoredSetting(llmModelStorageKeyForBackend(backend));
  const previous = llmModelEl.value;

  llmModelEl.innerHTML = "";
  if (models.length === 0) {
    const opt = document.createElement("option");
    opt.value = defaultModel || "";
    opt.textContent = defaultModel || "No models available";
    llmModelEl.appendChild(opt);
    llmModelEl.disabled = backend === "ollama";
  } else {
    for (const modelId of models) {
      const opt = document.createElement("option");
      opt.value = modelId;
      opt.textContent = modelId;
      llmModelEl.appendChild(opt);
    }
    llmModelEl.disabled = false;
  }

  if (stored && models.includes(stored)) {
    llmModelEl.value = stored;
  } else if (previous && models.includes(previous)) {
    llmModelEl.value = previous;
  } else if (defaultModel) {
    llmModelEl.value = defaultModel;
  }
  setStoredSetting(llmModelStorageKeyForBackend(backend), llmModelEl.value);
}

function updatePiperRateUi() {
  const isPiper = getSelectedSpeechBackend() === "piper";
  piperRateGroupEl.hidden = !isPiper;
  piperRateSliderEl.disabled = !isPiper || speakBtn.disabled;
  piperRateTextEl.textContent = formatPiperRate(piperRateSliderEl.value);
  piperNoiseScaleGroupEl.hidden = !isPiper;
  piperNoiseScaleSliderEl.disabled = !isPiper || speakBtn.disabled;
  piperNoiseScaleTextEl.textContent = formatPiperValue(piperNoiseScaleSliderEl.value);
  piperNoiseWGroupEl.hidden = !isPiper;
  piperNoiseWSliderEl.disabled = !isPiper || speakBtn.disabled;
  piperNoiseWTextEl.textContent = formatPiperValue(piperNoiseWSliderEl.value);
  piperSentenceSilenceGroupEl.hidden = !isPiper;
  piperSentenceSilenceSliderEl.disabled = !isPiper || speakBtn.disabled;
  piperSentenceSilenceTextEl.textContent = formatPiperSeconds(piperSentenceSilenceSliderEl.value);
}

function updateAppleRateUi() {
  const isApple = getSelectedSpeechBackend() === "apple";
  appleRateGroupEl.hidden = !isApple;
  appleRateSliderEl.disabled = !isApple || speakBtn.disabled;
  appleRateTextEl.textContent = formatPiperRate(appleRateSliderEl.value);
}

function updateSpeechRateUi() {
  updatePiperRateUi();
  updateAppleRateUi();
}

function isTtsEnabled() {
  return Boolean(ttsEnabledEl.checked);
}

function updateTtsUiState() {
  const enabled = isTtsEnabled();
  const canUseSpeechControls = enabled;
  speechBackendEl.disabled = false;
  playbackTargetEl.disabled = !enabled;
  voiceTypeEl.disabled = !enabled;
  customVoiceEl.disabled = !enabled;
  piperRateSliderEl.disabled = !canUseSpeechControls || getSelectedSpeechBackend() !== "piper";
  piperNoiseScaleSliderEl.disabled = !canUseSpeechControls || getSelectedSpeechBackend() !== "piper";
  piperNoiseWSliderEl.disabled = !canUseSpeechControls || getSelectedSpeechBackend() !== "piper";
  piperSentenceSilenceSliderEl.disabled = !canUseSpeechControls || getSelectedSpeechBackend() !== "piper";
  appleRateSliderEl.disabled = !canUseSpeechControls || getSelectedSpeechBackend() !== "apple";
}

function getSelectedVoiceId() {
  if (voiceTypeEl.value === "custom") {
    return (customVoiceEl.value || "").trim();
  }
  return voiceTypeEl.value;
}

function applySpeakAvailability() {
  const ready = Boolean(speechReadyState.ready);
  const starting = Boolean(speechReadyState.starting);
  const error = speechReadyState.error;
  const voiceType = speechReadyState.voiceType;
  const backend = speechReadyState.backend;
  const canUseBase = ready || !starting;
  const canUseChat = canUseBase && !preloadInFlight && !preloadErrorText;

  speakTextEl.disabled = !canUseChat;
  speakBtn.disabled = !canUseChat;

  if (preloadInFlight) {
    speakReadyEl.textContent = "Loading selected model and voice...";
    speakReadyEl.style.color = "#b45309";
    updateTtsUiState();
    updateSpeechRateUi();
    return;
  }

  if (preloadErrorText) {
    speakReadyEl.textContent = `Model load error: ${preloadErrorText}`;
    speakReadyEl.style.color = "#b91c1c";
    updateTtsUiState();
    updateSpeechRateUi();
    return;
  }

  if (ready) {
    const parts = [];
    if (backend) {
      parts.push(backend);
    }
    if (voiceType) {
      parts.push(voiceType);
    }
    speakReadyEl.textContent = `Speech ready${parts.length ? ` (${parts.join(" / ")})` : ""}`;
    speakReadyEl.style.color = "#0f766e";
    updateTtsUiState();
    updateSpeechRateUi();
    return;
  }
  if (starting) {
    speakReadyEl.textContent = "Initializing speech engine...";
    speakReadyEl.style.color = "#b45309";
    updateTtsUiState();
    updateSpeechRateUi();
    return;
  }
  if (error) {
    speakReadyEl.textContent = `Speech init error: ${error}`;
    speakReadyEl.style.color = "#b91c1c";
    updateTtsUiState();
    updateSpeechRateUi();
    return;
  }
  if (!ready) {
    speakReadyEl.textContent = "Speech idle. Press Speak to initialize.";
    speakReadyEl.style.color = "#64748b";
    updateTtsUiState();
    updateSpeechRateUi();
    return;
  }
  speakReadyEl.textContent = "Speech not ready.";
  speakReadyEl.style.color = "#b45309";
  updateTtsUiState();
  updateSpeechRateUi();
}

function getUiVolumeLevel() {
  const value = Number(volumeSliderEl.value);
  if (Number.isNaN(value)) {
    return 0.6;
  }
  return Math.max(0, Math.min(1, value / 100));
}

function renderStreamSection() {
  colorStreamCardEl.hidden = false;
  streamsToggleBtnEl.textContent = streamsExpanded ? "−" : "+";
  streamsToggleBtnEl.setAttribute("aria-expanded", streamsExpanded ? "true" : "false");
  streamsToggleBtnEl.title = streamsAvailable ? "Collapse or expand camera panel" : "Expand camera panel";
  streamsGridEl.hidden = !streamsExpanded;
}

function updateStreamVisibility(showColorStream) {
  streamsAvailable = Boolean(showColorStream);
  renderStreamSection();
}

function setReplyWindow(userText, assistantText, voiceId) {
  const hasReply = typeof assistantText === "string" && assistantText.trim().length > 0;
  replyWindowEl.classList.toggle("has-reply", hasReply);

  if (!hasReply) {
    replyMetaEl.textContent = "No reply yet.";
    replyTextEl.textContent = "Assistant replies will appear here.";
    return;
  }

  const metaParts = [];
  if (userText) {
    metaParts.push(`You: ${userText}`);
  }
  if (voiceId) {
    metaParts.push(`Voice: ${voiceId}`);
  }
  replyMetaEl.textContent = metaParts.join("  |  ") || "Reply received.";
  replyTextEl.textContent = assistantText.trim();
}

function getSelectedSpeechBackend() {
  if (speechBackendEl.value === "openai") {
    return "openai";
  }
  if (speechBackendEl.value === "apple") {
    return "apple";
  }
  if (speechBackendEl.value === "kokoro") {
    return "kokoro";
  }
  return "piper";
}

function syncVoiceCustomVisibility() {
  if (!SPEECH_MODULE_ENABLED) {
    customVoiceEl.style.display = "none";
    return;
  }
  customVoiceEl.style.display = voiceTypeEl.value === "custom" ? "block" : "none";
  customVoiceEl.placeholder =
    getSelectedSpeechBackend() === "openai"
      ? "Custom OpenAI voice id"
      : getSelectedSpeechBackend() === "apple"
        ? "Custom Apple voice name (e.g. Daniel)"
        : getSelectedSpeechBackend() === "kokoro"
          ? "Custom Kokoro voice id (e.g. af_heart)"
        : "Custom Piper model id (e.g. en_US-lessac-medium)";
  customVoiceEl.value = getStoredSetting(customVoiceStorageKeyForBackend(getSelectedSpeechBackend())) || "";
  updateSpeechRateUi();
}

function setVoiceOptions(voices, defaultVoice) {
  const backend = getSelectedSpeechBackend();
  const previous = voiceTypeEl.value;
  const preferred = getStoredSetting(voiceStorageKeyForBackend(backend));
  voiceTypeEl.innerHTML = "";

  const normalized = Array.isArray(voices)
    ? voices.filter((v) => typeof v === "string" && v.trim().length > 0)
    : [];

  for (const voiceId of normalized) {
    const opt = document.createElement("option");
    opt.value = voiceId;
    opt.textContent = voiceId;
    voiceTypeEl.appendChild(opt);
  }

  const customOpt = document.createElement("option");
  customOpt.value = "custom";
  customOpt.textContent = "Custom voice model id...";
  voiceTypeEl.appendChild(customOpt);

  if (preferred === "custom") {
    voiceTypeEl.value = "custom";
  } else if (preferred && normalized.includes(preferred)) {
    voiceTypeEl.value = preferred;
  } else if (previous === "custom") {
    voiceTypeEl.value = "custom";
  } else if (normalized.includes(previous)) {
    voiceTypeEl.value = previous;
  } else if (defaultVoice && normalized.includes(defaultVoice)) {
    voiceTypeEl.value = defaultVoice;
  } else if (normalized.length > 0) {
    voiceTypeEl.value = normalized[0];
  } else {
    voiceTypeEl.value = "custom";
  }
  setStoredSetting(voiceStorageKeyForBackend(backend), voiceTypeEl.value);
  syncVoiceCustomVisibility();
}

async function loadVoices() {
  try {
    const robotData = await api("/api/voices");
    let data = robotData;
    let voiceSource = "robot";
    if (shouldTryMacVoiceCatalog()) {
      try {
        const macData = await fetchJson(MAC_LOCAL_VOICES_URL);
        const merged = mergeTtsCatalog(robotData, macData);
        data = merged.data;
        voiceSource = merged.source;
      } catch (voiceErr) {
        appendDebugObject("mac voices unavailable", voiceErr.message || String(voiceErr));
      }
    }
    voiceCatalog = {
      defaultBackend:
        data.default_backend === "openai" || data.default_backend === "apple" || data.default_backend === "kokoro"
          ? data.default_backend
          : "piper",
      piper: {
        defaultVoice: (data.piper && data.piper.default_voice) || data.default_voice || "",
        voices: (data.piper && data.piper.voices) || data.voices || [],
        defaultRate: Number((data.piper && data.piper.default_rate) || 1.0) || 1.0,
        defaultNoiseScale: Number((data.piper && data.piper.default_noise_scale) || 0.667) || 0.667,
        defaultNoiseW: Number((data.piper && data.piper.default_noise_w) || 0.8) || 0.8,
        defaultSentenceSilence: Number((data.piper && data.piper.default_sentence_silence) || 0.2) || 0.2,
        voiceDefaults: (data.piper && data.piper.voice_defaults) || {},
      },
      openai: {
        defaultVoice: (data.openai && data.openai.default_voice) || "alloy",
        voices: (data.openai && data.openai.voices) || DEFAULT_OPENAI_VOICES,
      },
      apple: {
        defaultVoice: (data.apple && data.apple.default_voice) || "Daniel",
        voices: (data.apple && data.apple.voices) || [],
        defaultRate: Number((data.apple && data.apple.default_rate) || 1.0) || 1.0,
      },
      kokoro: {
        defaultVoice: (data.kokoro && data.kokoro.default_voice) || "af_heart",
        voices: (data.kokoro && data.kokoro.voices) || [],
      },
    };
    llmCatalog = {
      defaultBackend: data.default_llm_backend === "ollama" ? "ollama" : "openai",
      backends: Array.isArray(data.llm_backends) && data.llm_backends.length > 0
        ? data.llm_backends
        : [
            { id: "openai", label: "OpenAI" },
            { id: "ollama", label: "Ollama (qwen2.5:14b)" },
          ],
      openai: {
        defaultModel: (data.openai_llm && data.openai_llm.default_model) || "gpt-4.1-mini",
        models: (data.openai_llm && data.openai_llm.models) || [((data.openai_llm && data.openai_llm.default_model) || "gpt-4.1-mini")],
      },
      ollama: {
        defaultModel: (data.ollama && data.ollama.default_model) || "qwen2.5:14b",
        models: (data.ollama && data.ollama.models) || [],
      },
    };
    setLlmBackendOptions(llmCatalog.backends, llmCatalog.defaultBackend);
    refreshLlmModelOptions();
    const storedTtsEnabled = getStoredSetting(STORAGE_KEYS.ttsEnabled);
    ttsEnabledEl.checked = storedTtsEnabled !== "false";
    const storedBackend = getStoredSetting(STORAGE_KEYS.speechBackend);
    speechBackendEl.value =
      storedBackend === "openai" || storedBackend === "piper" || storedBackend === "apple" || storedBackend === "kokoro"
        ? storedBackend
        : voiceCatalog.defaultBackend;
    const storedPlaybackTarget = getStoredSetting(STORAGE_KEYS.playbackTarget);
    playbackTargetEl.value = storedPlaybackTarget === "robot" ? "robot" : "browser";
    const storedMicSource = getStoredSetting(STORAGE_KEYS.micSource);
    micSourceEl.value = storedMicSource === "mac" ? "mac" : "robot";
    const storedPiperRate = Number(getStoredSetting(STORAGE_KEYS.piperRate));
    const initialPiperRate = Number.isFinite(storedPiperRate) && storedPiperRate >= 0.5 && storedPiperRate <= 2.0
      ? storedPiperRate
      : voiceCatalog.piper.defaultRate;
    piperRateSliderEl.value = `${initialPiperRate}`;
    piperRateTextEl.textContent = formatPiperRate(initialPiperRate);
    const storedPiperNoiseScale = Number(getStoredSetting(STORAGE_KEYS.piperNoiseScale));
    const initialPiperNoiseScale =
      Number.isFinite(storedPiperNoiseScale) && storedPiperNoiseScale >= 0.1 && storedPiperNoiseScale <= 2.0
        ? storedPiperNoiseScale
        : voiceCatalog.piper.defaultNoiseScale;
    piperNoiseScaleSliderEl.value = `${initialPiperNoiseScale}`;
    piperNoiseScaleTextEl.textContent = formatPiperValue(initialPiperNoiseScale);
    const storedPiperNoiseW = Number(getStoredSetting(STORAGE_KEYS.piperNoiseW));
    const initialPiperNoiseW =
      Number.isFinite(storedPiperNoiseW) && storedPiperNoiseW >= 0.1 && storedPiperNoiseW <= 2.0
        ? storedPiperNoiseW
        : voiceCatalog.piper.defaultNoiseW;
    piperNoiseWSliderEl.value = `${initialPiperNoiseW}`;
    piperNoiseWTextEl.textContent = formatPiperValue(initialPiperNoiseW);
    const storedPiperSentenceSilence = Number(getStoredSetting(STORAGE_KEYS.piperSentenceSilence));
    const initialPiperSentenceSilence =
      Number.isFinite(storedPiperSentenceSilence) && storedPiperSentenceSilence >= 0.0 && storedPiperSentenceSilence <= 2.0
        ? storedPiperSentenceSilence
        : voiceCatalog.piper.defaultSentenceSilence;
    piperSentenceSilenceSliderEl.value = `${initialPiperSentenceSilence}`;
    piperSentenceSilenceTextEl.textContent = formatPiperSeconds(initialPiperSentenceSilence);
    const storedAppleRate = Number(getStoredSetting(STORAGE_KEYS.appleRate));
    const initialAppleRate = Number.isFinite(storedAppleRate) && storedAppleRate >= 0.5 && storedAppleRate <= 2.0
      ? storedAppleRate
      : voiceCatalog.apple.defaultRate;
    appleRateSliderEl.value = `${initialAppleRate}`;
    appleRateTextEl.textContent = formatPiperRate(initialAppleRate);
    refreshVoiceOptionsForBackend();
    updateTtsUiState();
    voicesLoaded = true;
    preloadSelectedStack();
    appendDebugObject("voices", {
      source: voiceSource,
      voice_dir: data.voice_dir,
      llm_backend: llmBackendEl.value,
      llm_model: llmModelEl.value,
      piper_count: Array.isArray(voiceCatalog.piper.voices) ? voiceCatalog.piper.voices.length : 0,
      openai_count: Array.isArray(voiceCatalog.openai.voices) ? voiceCatalog.openai.voices.length : 0,
      apple_count: Array.isArray(voiceCatalog.apple.voices) ? voiceCatalog.apple.voices.length : 0,
      kokoro_count: Array.isArray(voiceCatalog.kokoro.voices) ? voiceCatalog.kokoro.voices.length : 0,
      default_backend: voiceCatalog.defaultBackend,
    });
  } catch (err) {
    llmCatalog = {
      defaultBackend: "openai",
      backends: [
        { id: "openai", label: "OpenAI" },
        { id: "ollama", label: "Ollama (qwen2.5:14b)" },
      ],
      openai: { defaultModel: "gpt-4.1-mini", models: ["gpt-4.1-mini"] },
      ollama: { defaultModel: "qwen2.5:14b", models: [] },
    };
    setLlmBackendOptions(llmCatalog.backends, llmCatalog.defaultBackend);
    refreshLlmModelOptions();
    const storedTtsEnabled = getStoredSetting(STORAGE_KEYS.ttsEnabled);
    ttsEnabledEl.checked = storedTtsEnabled !== "false";
    voiceCatalog = {
      defaultBackend: "piper",
      piper: {
        defaultVoice: "",
        voices: [],
        defaultRate: 1.0,
        defaultNoiseScale: 0.667,
        defaultNoiseW: 0.8,
        defaultSentenceSilence: 0.2,
        voiceDefaults: {},
      },
      openai: { defaultVoice: "alloy", voices: DEFAULT_OPENAI_VOICES },
      apple: { defaultVoice: "Daniel", voices: [], defaultRate: 1.0 },
      kokoro: { defaultVoice: "af_heart", voices: [] },
    };
    const storedBackend = getStoredSetting(STORAGE_KEYS.speechBackend);
    speechBackendEl.value =
      storedBackend === "openai" || storedBackend === "piper" || storedBackend === "apple" || storedBackend === "kokoro"
        ? storedBackend
        : "piper";
    const storedPlaybackTarget = getStoredSetting(STORAGE_KEYS.playbackTarget);
    playbackTargetEl.value = storedPlaybackTarget === "robot" ? "robot" : "browser";
    const storedMicSource = getStoredSetting(STORAGE_KEYS.micSource);
    micSourceEl.value = storedMicSource === "mac" ? "mac" : "robot";
    const storedPiperRate = Number(getStoredSetting(STORAGE_KEYS.piperRate));
    const initialPiperRate = Number.isFinite(storedPiperRate) && storedPiperRate >= 0.5 && storedPiperRate <= 2.0
      ? storedPiperRate
      : 1.0;
    piperRateSliderEl.value = `${initialPiperRate}`;
    piperRateTextEl.textContent = formatPiperRate(initialPiperRate);
    const storedPiperNoiseScale = Number(getStoredSetting(STORAGE_KEYS.piperNoiseScale));
    const initialPiperNoiseScale =
      Number.isFinite(storedPiperNoiseScale) && storedPiperNoiseScale >= 0.1 && storedPiperNoiseScale <= 2.0
        ? storedPiperNoiseScale
        : 0.667;
    piperNoiseScaleSliderEl.value = `${initialPiperNoiseScale}`;
    piperNoiseScaleTextEl.textContent = formatPiperValue(initialPiperNoiseScale);
    const storedPiperNoiseW = Number(getStoredSetting(STORAGE_KEYS.piperNoiseW));
    const initialPiperNoiseW =
      Number.isFinite(storedPiperNoiseW) && storedPiperNoiseW >= 0.1 && storedPiperNoiseW <= 2.0
        ? storedPiperNoiseW
        : 0.8;
    piperNoiseWSliderEl.value = `${initialPiperNoiseW}`;
    piperNoiseWTextEl.textContent = formatPiperValue(initialPiperNoiseW);
    const storedPiperSentenceSilence = Number(getStoredSetting(STORAGE_KEYS.piperSentenceSilence));
    const initialPiperSentenceSilence =
      Number.isFinite(storedPiperSentenceSilence) && storedPiperSentenceSilence >= 0.0 && storedPiperSentenceSilence <= 2.0
        ? storedPiperSentenceSilence
        : 0.2;
    piperSentenceSilenceSliderEl.value = `${initialPiperSentenceSilence}`;
    piperSentenceSilenceTextEl.textContent = formatPiperSeconds(initialPiperSentenceSilence);
    const storedAppleRate = Number(getStoredSetting(STORAGE_KEYS.appleRate));
    const initialAppleRate = Number.isFinite(storedAppleRate) && storedAppleRate >= 0.5 && storedAppleRate <= 2.0
      ? storedAppleRate
      : 1.0;
    appleRateSliderEl.value = `${initialAppleRate}`;
    appleRateTextEl.textContent = formatPiperRate(initialAppleRate);
    refreshVoiceOptionsForBackend();
    updateTtsUiState();
    voicesLoaded = true;
    preloadSelectedStack();
    appendDebugObject("voices error", err.message || String(err));
  }
}

function refreshVoiceOptionsForBackend() {
  const backend = getSelectedSpeechBackend();
  const catalog = backend === "openai"
    ? voiceCatalog.openai
    : backend === "apple"
      ? voiceCatalog.apple
      : backend === "kokoro"
        ? voiceCatalog.kokoro
        : voiceCatalog.piper;
  setVoiceOptions(catalog.voices || [], catalog.defaultVoice || "");
}

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

function appendThinkingTrace(thinkingText) {
  const text = typeof thinkingText === "string" ? thinkingText.trim() : "";
  if (!text) {
    return;
  }
  for (const line of text.split(/\r?\n/)) {
    const cleaned = line.trim();
    if (!cleaned) {
      continue;
    }
    appendDebugLine(`[thinking] ${cleaned}`);
  }
}

function updateColorStream(rosAvailable, hasColorFrame, rosError, colorTopic) {
  if (!rosAvailable) {
    updateStreamVisibility(false);
    if (colorStreamAttached) {
      colorStreamEl.removeAttribute("src");
      colorStreamAttached = false;
    }
    colorStreamEl.hidden = true;
    colorStreamPlaceholderEl.hidden = false;
    colorStreamPlaceholderEl.textContent = `Camera unavailable: ROS2 is not installed here${rosError ? ` (${rosError})` : ""}`;
    return;
  }

  if (!hasColorFrame) {
    updateStreamVisibility(false);
    if (colorStreamAttached) {
      colorStreamEl.removeAttribute("src");
      colorStreamAttached = false;
    }
    colorStreamEl.hidden = true;
    colorStreamPlaceholderEl.hidden = false;
    colorStreamPlaceholderEl.textContent = `Waiting for camera frames on ${colorTopic}`;
    return;
  }

  updateStreamVisibility(true);

  if (!colorStreamAttached) {
    colorStreamEl.src = "/stream/color";
    colorStreamAttached = true;
  }

  colorStreamEl.hidden = false;
  colorStreamPlaceholderEl.hidden = true;
}

streamsToggleBtnEl.addEventListener("click", () => {
  streamsExpanded = !streamsExpanded;
  renderStreamSection();
});

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
    updateSpeakReady(data.ai_ready, data.ai_starting, data.ai_error, data.ai_voice_type, data.ai_tts_backend);
    updateMicrophone(Boolean(data.mic_enabled), Boolean(data.ai_starting));
    if (!getStoredSetting(STORAGE_KEYS.micSource) && data && typeof data.mic_source === "string") {
      micSourceEl.value = data.mic_source === "mac" ? "mac" : "robot";
    }
    updateColorStream(Boolean(data.ros_available), Boolean(data.has_color_frame), data.ros_import_error, data.color_topic);

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
    const source = getSelectedMicSource();
    const data = await api(`/api/audio/activity?source=${encodeURIComponent(source)}`);
    const active = Boolean(data.ok) && Boolean(data.active);
    const level = Number(data.level || 0);
    audioWidgetEl.classList.toggle("active", active);
    if (active) {
      audioTextEl.textContent = `${getSelectedMicLabel()} hearing ${(level * 100).toFixed(0)}%`;
      return;
    }
    if (!data.ok) {
      if (
        lastMicStatus &&
        lastMicStatus.ok !== false &&
        Boolean(lastMicStatus.enabled) &&
        Boolean(lastMicStatus.listening) &&
        String(lastMicStatus.source || "") === source
      ) {
        audioTextEl.textContent = `${getSelectedMicLabel()} listening`;
        return;
      }
      const err = String(data.error || "");
      if (err.includes("Device or resource busy")) {
        audioTextEl.textContent = `${getSelectedMicLabel()} busy`;
      } else {
        audioTextEl.textContent = `${getSelectedMicLabel()} unavailable`;
      }
      return;
    }
    audioTextEl.textContent = `${getSelectedMicLabel()} idle`;
  } catch (err) {
    if (
      lastMicStatus &&
      lastMicStatus.ok !== false &&
      Boolean(lastMicStatus.enabled) &&
      Boolean(lastMicStatus.listening) &&
      String(lastMicStatus.source || "") === getSelectedMicSource()
    ) {
      audioTextEl.textContent = `${getSelectedMicLabel()} listening`;
      return;
    }
    audioWidgetEl.classList.remove("active");
    audioTextEl.textContent = "Mic unknown";
  }
}

async function refreshMicrophoneStatus() {
  try {
    const data = await api("/api/microphone/status");
    updateMicHeardStatus(data);
  } catch (err) {
    updateMicHeardStatus({ ok: false, error: err.message || String(err) });
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

function updateSpeakReady(isReady, isStarting, error, voiceType, backend) {
  speechReadyState = {
    ready: Boolean(isReady),
    starting: Boolean(isStarting),
    error: error || null,
    voiceType: voiceType || null,
    backend: backend || null,
  };
  if (!SPEECH_MODULE_ENABLED) {
    speakTextEl.disabled = true;
    speakBtn.disabled = true;
    speechBackendEl.disabled = true;
    voiceTypeEl.disabled = true;
    customVoiceEl.disabled = true;
    speakReadyEl.textContent = "Speech module disabled (reserved for custom implementation).";
    speakReadyEl.style.color = "#64748b";
    return;
  }
  applySpeakAvailability();
}

async function preloadSelectedStack() {
  if (!voicesLoaded || !SPEECH_MODULE_ENABLED) {
    return;
  }
  const sequence = ++preloadSequence;
  preloadInFlight = true;
  preloadErrorText = null;
  applySpeakAvailability();

  const backend = getSelectedSpeechBackend();
  const llmBackend = llmBackendEl.value === "ollama" ? "ollama" : "openai";
  const llmModel = (llmModelEl.value || "").trim();
  const ttsEnabled = isTtsEnabled();
  const selectedVoice = getSelectedVoiceId();
  const playbackTarget = playbackTargetEl.value === "robot" ? "robot" : "browser";
  const piperRate = ttsEnabled && backend === "piper" ? Number(piperRateSliderEl.value) : null;
  const piperNoiseScale = ttsEnabled && backend === "piper" ? Number(piperNoiseScaleSliderEl.value) : null;
  const piperNoiseW = ttsEnabled && backend === "piper" ? Number(piperNoiseWSliderEl.value) : null;
  const piperSentenceSilence = ttsEnabled && backend === "piper" ? Number(piperSentenceSilenceSliderEl.value) : null;
  const appleRate = ttsEnabled && backend === "apple" ? Number(appleRateSliderEl.value) : null;

  try {
    const data = await apiPost("/api/preload", {
      llm_backend: llmBackend,
      llm_model: llmModel,
      voice_type: selectedVoice || null,
      speech_backend: backend,
      tts_enabled: ttsEnabled,
      playback_target: playbackTarget,
      piper_rate: piperRate,
      piper_noise_scale: piperNoiseScale,
      piper_noise_w: piperNoiseW,
      piper_sentence_silence: piperSentenceSilence,
      apple_rate: appleRate,
    });
    if (sequence !== preloadSequence) {
      return;
    }
    appendDebugObject("preload", data);
    appendThinkingTrace(data && data.llm_thinking);
    if (data && data.tts_enabled === false) {
      appendDebugLine("[ui] model loaded (text-only mode)");
    } else if (data && typeof data.tts_text === "string" && data.tts_text.trim()) {
      appendDebugLine(`[spoken] ${data.tts_text.trim()}`);
    }
    if (data && typeof data.audio_base64 === "string" && data.audio_base64.length > 16) {
      playSpeechAudioFromBase64(data.audio_base64, data.audio_mime || "audio/wav");
    } else if (data && data.playback_mode === "robot") {
      appendDebugLine("[ui] preload playback delivered to robot speakers");
    }
  } catch (err) {
    if (sequence !== preloadSequence) {
      return;
    }
    preloadErrorText = err && err.message ? err.message : String(err);
    appendDebugObject("preload error", preloadErrorText);
  } finally {
    if (sequence === preloadSequence) {
      preloadInFlight = false;
      applySpeakAvailability();
    }
  }
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
  if (activeSpeechAudio) {
    activeSpeechAudio.volume = getUiVolumeLevel();
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
  micSourceEl.disabled = false;
  micToggleSyncing = false;
}

function updateMicHeardStatus(data) {
  lastMicStatus = data && typeof data === "object" ? data : null;
  const transcript = typeof data?.transcript === "string" ? data.transcript.trim() : "";
  const error = typeof data?.error === "string" ? data.error.trim() : "";
  const label = data?.label || getSelectedMicLabel();
  const listening = Boolean(data?.enabled) && Boolean(data?.listening);
  if (!data || data.ok === false) {
    micHeardMetaEl.textContent = `${label} unavailable`;
    micHeardTextEl.textContent = error || "Sherpa status unavailable.";
    return;
  }
  if (transcript) {
    micHeardMetaEl.textContent = `${label} heard`;
    micHeardTextEl.textContent = transcript;
    if (transcript !== lastMicTranscriptSeen) {
      lastMicTranscriptSeen = transcript;
      appendDebugLine(`[heard] ${transcript}`);
    }
    return;
  }
  if (error) {
    micHeardMetaEl.textContent = `${label} listening warning`;
    micHeardTextEl.textContent = error;
    return;
  }
  if (listening) {
    micHeardMetaEl.textContent = `${label} listening`;
    micHeardTextEl.textContent = "Waiting for speech...";
    return;
  }
  micHeardMetaEl.textContent = "Listening off.";
  micHeardTextEl.textContent = "What Sherpa hears will appear here.";
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
  const source = getSelectedMicSource();
  micToggleEl.disabled = true;
  try {
    const data = await apiPost("/api/microphone", { enabled: target, source });
    appendDebugObject("microphone", data);
    updateMicrophone(Boolean(data.enabled), false);
    await refreshMicrophoneStatus();
  } catch (err) {
    appendDebugObject("microphone error", err.message || String(err));
    micToggleEl.checked = !target;
    micToggleEl.disabled = false;
  }
});

micSourceEl.addEventListener("change", async () => {
  const source = getSelectedMicSource();
  setStoredSetting(STORAGE_KEYS.micSource, source);
  appendDebugLine(`[ui] audio capture source: ${getSelectedMicLabel()} (STT runs on Mac)`);
  if (micToggleEl.checked) {
    try {
      const data = await apiPost("/api/microphone", { enabled: true, source });
      appendDebugObject("microphone", data);
      updateMicrophone(Boolean(data.enabled), false);
    } catch (err) {
      appendDebugObject("microphone error", err.message || String(err));
    }
  }
  await refreshAudioActivity();
  await refreshMicrophoneStatus();
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
  const selected = getSelectedVoiceId();
  if (!selected) {
    appendDebugLine("[ui] speak error: voice is empty");
    return;
  }
  const backend = getSelectedSpeechBackend();
  const llmBackend = llmBackendEl.value === "ollama" ? "ollama" : "openai";
  const llmModel = (llmModelEl.value || "").trim();
  const ttsEnabled = isTtsEnabled();
  const playbackTarget = playbackTargetEl.value === "robot" ? "robot" : "browser";
  const piperRate = ttsEnabled && backend === "piper" ? Number(piperRateSliderEl.value) : null;
  const piperNoiseScale = ttsEnabled && backend === "piper" ? Number(piperNoiseScaleSliderEl.value) : null;
  const piperNoiseW = ttsEnabled && backend === "piper" ? Number(piperNoiseWSliderEl.value) : null;
  const piperSentenceSilence = ttsEnabled && backend === "piper" ? Number(piperSentenceSilenceSliderEl.value) : null;
  const appleRate = ttsEnabled && backend === "apple" ? Number(appleRateSliderEl.value) : null;
  try {
    speakBtn.disabled = true;
    updateTtsUiState();
    updateSpeechRateUi();
    setReplyWindow(text, "Waiting for assistant reply...", ttsEnabled ? `${backend}:${selected}` : "Text only");
    const data = await apiPost("/api/speak", {
      text,
      llm_backend: llmBackend,
      llm_model: llmModel,
      voice_type: selected,
      speech_backend: backend,
      tts_enabled: ttsEnabled,
      playback_target: playbackTarget,
      piper_rate: piperRate,
      piper_noise_scale: piperNoiseScale,
      piper_noise_w: piperNoiseW,
      piper_sentence_silence: piperSentenceSilence,
      apple_rate: appleRate,
    });
    appendDebugObject("speak", data);
    if (data && typeof data.assistant_text === "string" && data.assistant_text.trim()) {
      speakTextEl.value = "";
      const replyMetaVoice =
        data && data.tts_enabled === false
          ? "Text only"
          : `${data.speech_backend_used || backend}:${data.voice_used || selected}`;
      setReplyWindow(text, data.assistant_text, replyMetaVoice);
      if (data.llm_backend_used || data.llm_model_used) {
        appendDebugLine(`[llm] ${data.llm_backend_used || llmBackend}${data.llm_model_used ? ` / ${data.llm_model_used}` : ""}`);
      }
      appendThinkingTrace(data.llm_thinking);
      appendDebugLine(`[assistant] ${data.assistant_text.trim()}`);
    } else {
      setReplyWindow(
        text,
        "No assistant text returned.",
        `${data && data.speech_backend_used ? data.speech_backend_used : backend}:${data && data.voice_used ? data.voice_used : selected}`,
      );
    }
    if (data && data.tts_enabled === false) {
      appendDebugLine("[ui] tts disabled: reply shown in browser only");
    } else if (data && typeof data.tts_text === "string" && data.tts_text.trim()) {
      appendDebugLine(`[spoken] ${data.tts_text.trim()}`);
    }
    if (data && typeof data.audio_base64 === "string" && data.audio_base64.length > 16) {
      playSpeechAudioFromBase64(data.audio_base64, data.audio_mime || "audio/wav");
    } else if (data && data.playback_mode === "robot") {
      appendDebugLine("[ui] playback delivered to robot speakers");
    }
  } catch (err) {
    setReplyWindow(text, `Speak request failed: ${err.message || String(err)}`, `${backend}:${selected}`);
    appendDebugObject("speak error", err.message || String(err));
  } finally {
    speakBtn.disabled = false;
    updateTtsUiState();
    updateSpeechRateUi();
  }
}

function playSpeechAudioFromBase64(base64Data, mimeType) {
  try {
    const bytes = atob(base64Data);
    const buffer = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i += 1) {
      buffer[i] = bytes.charCodeAt(i);
    }
    const blob = new Blob([buffer], { type: mimeType || "audio/wav" });
    const url = URL.createObjectURL(blob);
    if (activeSpeechAudio) {
      activeSpeechAudio.pause();
      activeSpeechAudio = null;
    }
    const audio = new Audio(url);
    audio.volume = getUiVolumeLevel();
    activeSpeechAudio = audio;
    audio.onended = () => {
      URL.revokeObjectURL(url);
      if (activeSpeechAudio === audio) {
        activeSpeechAudio = null;
      }
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      appendDebugLine("[ui] speak playback error");
      if (activeSpeechAudio === audio) {
        activeSpeechAudio = null;
      }
    };
    const playPromise = audio.play();
    if (playPromise && typeof playPromise.catch === "function") {
      playPromise.catch((err) => {
        appendDebugObject("speak playback blocked", err && err.message ? err.message : String(err));
      });
    }
  } catch (err) {
    appendDebugObject("speak audio decode error", err && err.message ? err.message : String(err));
  }
}

speakBtn.addEventListener("click", submitSpeak);

speakTextEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitSpeak();
  }
});

llmBackendEl.addEventListener("change", () => {
  setStoredSetting(STORAGE_KEYS.llmBackend, llmBackendEl.value);
  refreshLlmModelOptions();
  preloadSelectedStack();
});

llmModelEl.addEventListener("change", () => {
  const backend = llmBackendEl.value === "ollama" ? "ollama" : "openai";
  setStoredSetting(llmModelStorageKeyForBackend(backend), llmModelEl.value);
  preloadSelectedStack();
});

voiceTypeEl.addEventListener("change", () => {
  setStoredSetting(voiceStorageKeyForBackend(getSelectedSpeechBackend()), voiceTypeEl.value);
  syncVoiceCustomVisibility();
  if (getSelectedSpeechBackend() === "piper" && voiceTypeEl.value !== "custom") {
    applyPiperDefaultsForSelectedVoice();
  }
  preloadSelectedStack();
});

speechBackendEl.addEventListener("change", () => {
  setStoredSetting(STORAGE_KEYS.speechBackend, speechBackendEl.value);
  refreshVoiceOptionsForBackend();
  if (getSelectedSpeechBackend() === "piper" && voiceTypeEl.value !== "custom") {
    applyPiperDefaultsForSelectedVoice();
  }
  updateTtsUiState();
  updateSpeechRateUi();
  preloadSelectedStack();
});

ttsEnabledEl.addEventListener("change", () => {
  setStoredSetting(STORAGE_KEYS.ttsEnabled, ttsEnabledEl.checked ? "true" : "false");
  updateTtsUiState();
  updateSpeechRateUi();
  preloadSelectedStack();
});

playbackTargetEl.addEventListener("change", () => {
  setStoredSetting(STORAGE_KEYS.playbackTarget, playbackTargetEl.value);
});

piperRateSliderEl.addEventListener("input", () => {
  piperRateTextEl.textContent = formatPiperRate(piperRateSliderEl.value);
  setStoredSetting(STORAGE_KEYS.piperRate, piperRateSliderEl.value);
});

piperNoiseScaleSliderEl.addEventListener("input", () => {
  piperNoiseScaleTextEl.textContent = formatPiperValue(piperNoiseScaleSliderEl.value);
  setStoredSetting(STORAGE_KEYS.piperNoiseScale, piperNoiseScaleSliderEl.value);
});

piperNoiseWSliderEl.addEventListener("input", () => {
  piperNoiseWTextEl.textContent = formatPiperValue(piperNoiseWSliderEl.value);
  setStoredSetting(STORAGE_KEYS.piperNoiseW, piperNoiseWSliderEl.value);
});

piperSentenceSilenceSliderEl.addEventListener("input", () => {
  piperSentenceSilenceTextEl.textContent = formatPiperSeconds(piperSentenceSilenceSliderEl.value);
  setStoredSetting(STORAGE_KEYS.piperSentenceSilence, piperSentenceSilenceSliderEl.value);
});

appleRateSliderEl.addEventListener("input", () => {
  appleRateTextEl.textContent = formatPiperRate(appleRateSliderEl.value);
  setStoredSetting(STORAGE_KEYS.appleRate, appleRateSliderEl.value);
});

customVoiceEl.addEventListener("input", () => {
  setStoredSetting(customVoiceStorageKeyForBackend(getSelectedSpeechBackend()), customVoiceEl.value.trim());
});

customVoiceEl.addEventListener("change", () => {
  preloadSelectedStack();
});

volumeSliderEl.addEventListener("input", () => {
  volumeTextEl.textContent = `${volumeSliderEl.value}%`;
  if (activeSpeechAudio) {
    activeSpeechAudio.volume = getUiVolumeLevel();
  }
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

updateSpeakReady(false, true, null, null, null);
updateTtsUiState();
updateSpeechRateUi();
updateMicrophone(false, true);
micSourceEl.value = getStoredSetting(STORAGE_KEYS.micSource) === "mac" ? "mac" : "robot";
outputEl.textContent = "";
appendDebugLine("[ui] debug stream connected");
loadVoices();
refreshHealth();
refreshMotors();
refreshDebug();
refreshAudioActivity();
refreshMicrophoneStatus();
setInterval(refreshHealth, 2000);
setInterval(refreshMotors, 3000);
setInterval(refreshDebug, 1000);
setInterval(refreshAudioActivity, 700);
setInterval(refreshMicrophoneStatus, 1000);
