const FIELD_MAP = {
  retriever_top_k: "retrieverTopK",
  rerank_weight: "rerankWeight",
  response_tokens: "responseTokens"
};

const selectors = {
  retriever: document.getElementById("retriever"),
  rerank: document.getElementById("rerank"),
  tokens: document.getElementById("tokens"),
  presetButtons: document.querySelectorAll(".preset-button"),
  latencyBar: document.querySelector("[data-field='latencyBar']"),
  latencyDisplay: document.querySelector("[data-field='latencyDisplay']"),
  costBar: document.querySelector("[data-field='costBar']"),
  costDisplay: document.querySelector("[data-field='costDisplay']"),
  qualityBar: document.querySelector("[data-field='qualityBar']"),
  qualityDisplay: document.querySelector("[data-field='qualityDisplay']"),
  yamlSnapshot: document.querySelector("[data-field='yamlSnapshot']"),
  copyYaml: document.getElementById("copyYaml"),
  retrieverReadout: document.querySelector("[data-out='retrieverValue']"),
  rerankReadout: document.querySelector("[data-out='rerankValue']"),
  tokensReadout: document.querySelector("[data-out='tokensValue']"),
  svgRetrieverValue: document.querySelector("[data-field='retrieverValue']"),
  svgRetrieverOhms: document.querySelector("[data-field='retrieverOhms']"),
  svgRerankValue: document.querySelector("[data-field='rerankValue']"),
  svgRerankGain: document.querySelector("[data-field='rerankGain']"),
  svgTokensValue: document.querySelector("[data-field='tokensValue']"),
  svgTokensFarads: document.querySelector("[data-field='tokensFarads']"),
  componentRetriever: document.querySelector("[data-component='retriever']"),
  componentRerank: document.querySelector("[data-component='rerank']"),
  componentTokens: document.querySelector("[data-component='tokens']"),
  constraintLatency: document.querySelector('[data-constraint="latency"]'),
  constraintCost: document.querySelector('[data-constraint="cost"]'),
  constraintRerank: document.querySelector('[data-constraint="rerank"]')
};

const defaultState = {
  retrieverTopK: Number(selectors.retriever.value),
  rerankWeight: Number(selectors.rerank.value),
  responseTokens: Number(selectors.tokens.value)
};

let state = { ...defaultState };
let presets = {
  baseline: { ...defaultState, description: "Balanced campus orientation preset." },
  "latency-spike": {
    retrieverTopK: 48,
    rerankWeight: 0.35,
    responseTokens: 384,
    description: "Midweek surge—latency pressure rises."
  },
  "budget-shift": {
    retrieverTopK: 24,
    rerankWeight: 0.55,
    responseTokens: 512,
    description: "Budget relief allows richer answers."
  }
};

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function formatCurrency(value) {
  return `$${value.toFixed(2)}`;
}

function formatNumber(value) {
  return Number(value).toFixed(0);
}

function computeMetrics({ retrieverTopK, rerankWeight, responseTokens }) {
  const latency =
    480 +
    retrieverTopK * 3 +
    responseTokens * 0.45 -
    rerankWeight * 50;
  const cost = 0.00018 * retrieverTopK + 0.00052 * responseTokens + 0.005;
  const normalizedLatency = clamp(latency / 800, 0, 1);
  const qualityBase = 70 + rerankWeight * 45 + (retrieverTopK / 64) * 12;
  const qualityPenalty = normalizedLatency > 1 ? (normalizedLatency - 1) * 35 : normalizedLatency * 12;
  const quality = clamp(qualityBase - qualityPenalty, 20, 99);
  const throughput = (5 / (retrieverTopK / 16 + responseTokens / 128 + 1.2)).toFixed(2);
  return {
    latency,
    cost,
    quality,
    throughput
  };
}

function updateMeters(metrics) {
  const latencyPercent = clamp(metrics.latency / 1000, 0, 1) * 100;
  const costPercent = clamp(metrics.cost / 0.2, 0, 1) * 100;
  const qualityPercent = clamp(metrics.quality / 100, 0, 1) * 100;

  selectors.latencyBar.style.width = `${latencyPercent}%`;
  selectors.costBar.style.width = `${costPercent}%`;
  selectors.qualityBar.style.width = `${qualityPercent}%`;

  selectors.latencyDisplay.textContent = `${metrics.latency.toFixed(0)} ms`;
  selectors.costDisplay.textContent = formatCurrency(metrics.cost);
  selectors.qualityDisplay.textContent = metrics.quality.toFixed(0);
}

function updateConstraints(metrics) {
  const latencyOk = metrics.latency <= 800;
  const latencyClass = latencyOk ? "ok" : metrics.latency <= 900 ? "warn" : "bad";
  selectors.constraintLatency.className = latencyClass;
  selectors.constraintLatency.querySelector("span").textContent = latencyOk
    ? "Within guardrail"
    : `Exceeded by ${(metrics.latency - 800).toFixed(0)} ms`;

  const costOk = metrics.cost <= 0.12;
  const costClass = costOk ? "ok" : metrics.cost <= 0.15 ? "warn" : "bad";
  selectors.constraintCost.className = costClass;
  selectors.constraintCost.querySelector("span").textContent = costOk
    ? "On budget"
    : `Exceeded by ${(metrics.cost - 0.12).toFixed(3)}`;

  const rerankGuard = !(state.retrieverTopK >= 40 && state.rerankWeight < 0.3);
  const rerankClass = rerankGuard ? "ok" : "bad";
  selectors.constraintRerank.className = rerankClass;
  selectors.constraintRerank.querySelector("span").textContent = rerankGuard
    ? "Aligned with policy"
    : "Raise rerank weight to ≥ 0.3";

  selectors.componentRetriever.dataset.health = latencyOk ? "" : metrics.latency <= 900 ? "warning" : "violation";
  selectors.componentRerank.dataset.health = rerankGuard ? "" : "violation";
  selectors.componentTokens.dataset.health = costOk ? "" : costClass === "warn" ? "warning" : "violation";
}

function buildYamlSnapshot() {
  const yaml = [
    "configuration_space:",
    "  retriever_top_k:",
    "    type: int",
    `    value: ${state.retrieverTopK}`,
    "  rerank_weight:",
    "    type: float",
    `    value: ${state.rerankWeight.toFixed(2)}`,
    "  response_tokens:",
    "    type: int",
    `    value: ${state.responseTokens}`,
    "objectives:",
    "  latency_ms: \"minimize\"",
    "  cost_usd: \"minimize\"",
    "  quality_score: \"maximize\""
  ];
  return yaml.join("\n");
}

function updateSnapshot(metrics) {
  selectors.yamlSnapshot.textContent = buildYamlSnapshot();
}

function updateSvg() {
  const { retrieverTopK, rerankWeight, responseTokens } = state;
  const intakeOhms = retrieverTopK;
  const rerankGain = (1 + rerankWeight * 3.5).toFixed(2);
  const outputFarads = (responseTokens / 1024).toFixed(2);

  const retrieverText = `${formatNumber(retrieverTopK)}`;
  selectors.retrieverReadout.textContent = retrieverText;
  selectors.svgRetrieverValue.textContent = retrieverText;
  selectors.svgRetrieverOhms.textContent = `${intakeOhms} Ω`;

  const rerankText = rerankWeight.toFixed(2);
  selectors.rerankReadout.textContent = rerankText;
  selectors.svgRerankValue.textContent = rerankText;
  selectors.svgRerankGain.textContent = `Gain ×${rerankGain}`;

  const tokensText = `${formatNumber(responseTokens)}`;
  selectors.tokensReadout.textContent = tokensText;
  selectors.svgTokensValue.textContent = tokensText;
  selectors.svgTokensFarads.textContent = `${outputFarads} F`;
}

function updateUI() {
  const metrics = computeMetrics(state);
  updateMeters(metrics);
  updateConstraints(metrics);
  updateSvg();
  updateSnapshot(metrics);
}

function applyState(partial) {
  state = { ...state, ...partial };
  selectors.retriever.value = state.retrieverTopK;
  selectors.rerank.value = state.rerankWeight;
  selectors.tokens.value = state.responseTokens;
  updateUI();
}

function handleSliderChange() {
  state = {
    retrieverTopK: Number(selectors.retriever.value),
    rerankWeight: Number(selectors.rerank.value),
    responseTokens: Number(selectors.tokens.value)
  };
  clearPresetSelection();
  updateUI();
}

function clearPresetSelection() {
  selectors.presetButtons.forEach((button) => {
    button.classList.remove("active");
    button.removeAttribute("aria-pressed");
  });
}

function selectPreset(key) {
  const preset = presets[key];
  if (!preset) return false;
  applyState(preset);
  clearPresetSelection();
  const button = document.querySelector(`.preset-button[data-preset="${key}"]`);
  if (button) {
    button.classList.add("active");
    button.setAttribute("aria-pressed", "true");
  }
  return true;
}

function handlePresetClick(event) {
  const key = event.currentTarget.dataset.preset;
  selectPreset(key);
}

function normalizePreset(raw) {
  const normalized = {};
  Object.keys(raw || {}).forEach((key) => {
    const targetKey = FIELD_MAP[key] || key;
    normalized[targetKey] = raw[key];
  });
  return normalized;
}

function configureSliders(config) {
  if (!config) return;
  const sliderConfigs = {
    retrieverTopK: selectors.retriever,
    rerankWeight: selectors.rerank,
    responseTokens: selectors.tokens
  };
  Object.entries(config).forEach(([key, value]) => {
    const targetKey = FIELD_MAP[key] || key;
    const element = sliderConfigs[targetKey];
    if (!element || typeof value !== "object") return;
    if (value.min !== undefined) element.min = value.min;
    if (value.max !== undefined) element.max = value.max;
    if (value.step !== undefined) element.step = value.step;
  });
}

async function loadPresets() {
  try {
    const response = await fetch("./microsim_presets.json", { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    configureSliders(data.sliders);

    if (data.presets) {
      const mapped = Object.fromEntries(
        Object.entries(data.presets).map(([name, preset]) => [name, normalizePreset(preset)])
      );
      presets = { ...presets, ...mapped };
    }
    if (data.defaults) {
      const defaults = normalizePreset(data.defaults);
      applyState({
        retrieverTopK: defaults.retrieverTopK ?? state.retrieverTopK,
        rerankWeight: defaults.rerankWeight ?? state.rerankWeight,
        responseTokens: defaults.responseTokens ?? state.responseTokens
      });
    }
  } catch (error) {
    console.warn("Unable to load custom presets:", error);
  }
}

function copyYamlToClipboard() {
  const text = selectors.yamlSnapshot.textContent;
  if (!navigator.clipboard) {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
    return;
  }
  navigator.clipboard.writeText(text).catch((err) => {
    console.error("Clipboard copy failed:", err);
  });
}

selectors.retriever.addEventListener("input", handleSliderChange);
selectors.rerank.addEventListener("input", handleSliderChange);
selectors.tokens.addEventListener("input", handleSliderChange);

selectors.presetButtons.forEach((button) => {
  button.addEventListener("click", handlePresetClick);
});

if (selectors.copyYaml) {
  selectors.copyYaml.addEventListener("click", copyYamlToClipboard);
}

function applyInitialPreset() {
  const hash = window.location.hash.replace("#", "").trim();
  if (hash && selectPreset(hash)) {
    return;
  }
  updateUI();
}

loadPresets().finally(() => {
  applyInitialPreset();
});
