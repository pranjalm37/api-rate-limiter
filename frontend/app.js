const API_BASE = "/api";
const MAX_EVENTS = 160;

const el = (id) => document.getElementById(id);

const state = {
  total: 0,
  allowed: 0,
  blocked: 0,
  events: [], // { allowed: bool }
  autoFireTimer: null,
};

function currentClientId() {
  return el("clientId").value.trim() || "demo-client";
}

async function api(path, opts = {}) {
  const res = await fetch(API_BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

function setConnectionStatus(online) {
  el("statusDot").className = "status-dot " + (online ? "online" : "offline");
  el("statusText").textContent = online ? "connected" : "offline";
}

function syncAlgorithmFields() {
  const algo = el("algorithm").value;
  const isTokenBucket = algo === "token_bucket";
  el("refillRow").classList.toggle("hidden", !isTokenBucket);
  el("windowRow").classList.toggle("hidden", isTokenBucket);
  el("capacityHint").textContent = isTokenBucket
    ? "(bucket size, i.e. max burst)"
    : "(max requests / window)";
}

async function loadConfig() {
  const { ok, data } = await api("/config");
  setConnectionStatus(ok);
  if (!ok) return;
  el("algorithm").value = data.algorithm;
  el("backend").value = data.backend;
  el("capacity").value = data.capacity;
  el("windowSeconds").value = data.window_seconds;
  el("refillRate").value = data.refill_rate;
  syncAlgorithmFields();
}

async function applyConfig() {
  el("configError").textContent = "";
  const body = {
    algorithm: el("algorithm").value,
    backend: el("backend").value,
    capacity: Number(el("capacity").value),
    window_seconds: Number(el("windowSeconds").value),
    refill_rate: Number(el("refillRate").value),
  };
  const { ok, data } = await api("/config", { method: "POST", body: JSON.stringify(body) });
  if (!ok) {
    el("configError").textContent = (data && data.detail) || "Failed to apply configuration.";
    return;
  }
  resetStats();
  await drawChart();
}

async function resetState() {
  await api("/limiter/reset", { method: "POST" });
  resetStats();
}

function resetStats() {
  state.total = 0;
  state.allowed = 0;
  state.blocked = 0;
  state.events = [];
  renderStats();
  drawChart();
}

function renderStats() {
  el("statTotal").textContent = state.total;
  el("statAllowed").textContent = state.allowed;
  el("statBlocked").textContent = state.blocked;
  const rate = state.total ? Math.round((state.blocked / state.total) * 100) : 0;
  el("statBlockRate").textContent = rate + "%";
}

function renderRemaining(remaining, limit) {
  el("remainingText").textContent = `${remaining} / ${limit}`;
  const pct = limit > 0 ? Math.max(0, Math.min(100, (remaining / limit) * 100)) : 0;
  const fill = el("remainingFill");
  fill.style.width = pct + "%";
  fill.style.background =
    pct > 50
      ? "linear-gradient(90deg, #35d68a, #5b8cff)"
      : pct > 20
      ? "linear-gradient(90deg, #f4c25b, #ff9f5b)"
      : "linear-gradient(90deg, #ff5d6c, #ff5d6c)";
}

async function fireOnce() {
  const { ok, data } = await api("/limiter/check", {
    method: "POST",
    body: JSON.stringify({ client_id: currentClientId() }),
  });
  if (!ok) return;
  state.total += 1;
  if (data.allowed) state.allowed += 1;
  else state.blocked += 1;
  state.events.push({ allowed: data.allowed });
  if (state.events.length > MAX_EVENTS) state.events.shift();
  renderStats();
  renderRemaining(data.remaining, data.limit);
  drawChart();
}

async function fireBurst(count = 20) {
  for (let i = 0; i < count; i++) {
    await fireOnce();
  }
}

function startAutoFire() {
  stopAutoFire();
  const rate = Number(el("fireRate").value);
  const intervalMs = Math.max(1000 / rate, 20);
  state.autoFireTimer = setInterval(fireOnce, intervalMs);
}

function stopAutoFire() {
  if (state.autoFireTimer) {
    clearInterval(state.autoFireTimer);
    state.autoFireTimer = null;
  }
}

function drawChart() {
  const canvas = el("chart");
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);

  ctx.fillStyle = "#0e1119";
  ctx.fillRect(0, 0, width, height);

  const events = state.events;
  if (events.length === 0) return;

  const slotWidth = width / MAX_EVENTS;
  const baseline = height - 20;

  events.forEach((ev, i) => {
    const x = i * slotWidth;
    const barHeight = ev.allowed ? height - 50 : (height - 50) * 0.45;
    ctx.fillStyle = ev.allowed ? "#35d68a" : "#ff5d6c";
    ctx.fillRect(x + 1, baseline - barHeight, Math.max(slotWidth - 2, 1), barHeight);
  });

  ctx.strokeStyle = "#232838";
  ctx.beginPath();
  ctx.moveTo(0, baseline);
  ctx.lineTo(width, baseline);
  ctx.stroke();
}

function updateCurlSnippet() {
  const clientId = currentClientId();
  el("curlSnippet").textContent =
    `curl -H "X-Client-Id: ${clientId}" ${location.origin}/api/demo/resource`;
}

function wire() {
  el("algorithm").addEventListener("change", syncAlgorithmFields);
  el("applyConfig").addEventListener("click", applyConfig);
  el("resetState").addEventListener("click", resetState);
  el("fireOnce").addEventListener("click", fireOnce);
  el("fireBurst").addEventListener("click", () => fireBurst(20));
  el("clientId").addEventListener("input", updateCurlSnippet);

  el("autoFireToggle").addEventListener("change", (e) => {
    if (e.target.checked) startAutoFire();
    else stopAutoFire();
  });
  el("fireRate").addEventListener("input", (e) => {
    el("rateValue").textContent = e.target.value;
    if (state.autoFireTimer) startAutoFire();
  });
}

(async function init() {
  wire();
  syncAlgorithmFields();
  updateCurlSnippet();
  await loadConfig();
  drawChart();
  setInterval(() => api("/health").then(({ ok }) => setConnectionStatus(ok)), 5000);
})();
