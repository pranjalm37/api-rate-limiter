const API = "/api";
const WINDOW_SECONDS = 30;
const SAMPLE_MS = 200; // quota poll interval (a network round trip, unlike the static demo)
const MAX_LOG_ROWS = 200;

const el = (id) => document.getElementById(id);

const ALGO_LABELS = {
  token_bucket: "Token bucket",
  fixed_window: "Fixed window",
  sliding_window_log: "Sliding window log",
  sliding_window_counter: "Sliding window counter",
};

const state = {
  capacity: 10,
  samples: [],
  events: [],
  total: 0,
  allowed: 0,
  blocked: 0,
  autoTimer: null,
  hoverX: null,
};

/* ---------------------------------------------------------------- api */

async function api(path, opts = {}) {
  try {
    const res = await fetch(API + path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
  } catch {
    return { ok: false, status: 0, data: {} };
  }
}

function setConnected(online) {
  el("connectionStatus").textContent = online ? "connected" : "offline";
}

function clientId() {
  return el("clientId").value.trim() || "demo-client";
}

/* ---------------------------------------------------------------- config */

function syncAlgorithmFields() {
  const isBucket = el("algorithm").value === "token_bucket";
  el("refillField").classList.toggle("hidden", !isBucket);
  el("windowField").classList.toggle("hidden", isBucket);
  el("capacityLabel").textContent = isBucket ? "Bucket size" : "Limit";
  el("chartAlgoName").textContent = ALGO_LABELS[el("algorithm").value];
}

async function loadConfig() {
  const { ok, data } = await api("/config");
  setConnected(ok);
  if (!ok) return;
  el("algorithm").value = data.algorithm;
  el("backend").value = data.backend;
  el("capacity").value = data.capacity;
  el("windowSeconds").value = data.window_seconds;
  el("refillRate").value = data.refill_rate;
  state.capacity = data.capacity;
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
    el("configError").textContent =
      typeof data.detail === "string" ? data.detail : "Could not apply configuration.";
    return;
  }
  state.capacity = data.capacity;
  syncAlgorithmFields();
  await resetAll();
}

async function resetAll() {
  await api("/limiter/reset", { method: "POST" });
  const t = Date.now() / 1000;
  state.samples = [];
  for (let dt = WINDOW_SECONDS; dt >= 0; dt -= SAMPLE_MS / 1000) {
    state.samples.push({ t: t - dt, remaining: state.capacity });
  }
  state.events = [];
  state.total = 0;
  state.allowed = 0;
  state.blocked = 0;
  renderStats();
  renderTable();
  draw();
}

/* ---------------------------------------------------------------- traffic */

async function fireOnce() {
  const { ok, data } = await api("/limiter/check", {
    method: "POST",
    body: JSON.stringify({ client_id: clientId() }),
  });
  setConnected(ok);
  if (!ok) return;

  state.total += 1;
  if (data.allowed) state.allowed += 1;
  else state.blocked += 1;

  state.events.push({ t: Date.now() / 1000, allowed: data.allowed, remaining: data.remaining });
  if (state.events.length > 4000) state.events.splice(0, 2000);
  state.capacity = data.limit;

  renderStats();
  renderTable();
}

async function fireBurst(n) {
  // Fired concurrently: this is the server's real concurrency path, which the
  // atomic storage layer exists to make correct.
  await Promise.all(Array.from({ length: n }, fireOnce));
}

function startAuto() {
  stopAuto();
  const rate = Number(el("fireRate").value);
  state.autoTimer = setInterval(fireOnce, Math.max(1000 / rate, 25));
}

function stopAuto() {
  if (state.autoTimer) clearInterval(state.autoTimer);
  state.autoTimer = null;
}

/* ---------------------------------------------------------------- readouts */

function renderStats() {
  el("statTotal").textContent = state.total.toLocaleString();
  el("statAllowed").textContent = state.allowed.toLocaleString();
  el("statBlocked").textContent = state.blocked.toLocaleString();
  el("statBlockRate").textContent = state.total
    ? Math.round((state.blocked / state.total) * 100)
    : 0;
}

function renderTable() {
  if (el("tableWrap").hidden) return;
  const now = Date.now() / 1000;
  el("tableBody").innerHTML = state.events
    .slice(-MAX_LOG_ROWS)
    .reverse()
    .map((ev) => {
      const cls = ev.allowed ? "outcome-allowed" : "outcome-blocked";
      const label = ev.allowed ? "Allowed" : "Rejected";
      return `<tr><td>${(now - ev.t).toFixed(1)}s ago</td><td class="${cls}">${label}</td><td>${ev.remaining}</td></tr>`;
    })
    .join("");
}

function updateSnippet() {
  el("curlSnippet").textContent =
    `curl -i -H "X-Client-Id: ${clientId()}" ${location.origin}/api/demo/resource`;
}

/* ---------------------------------------------------------------- chart */

const canvas = el("chart");
const ctx = canvas.getContext("2d");
let cssWidth = 0;
let cssHeight = 0;

function palette() {
  const s = getComputedStyle(document.documentElement);
  const get = (n) => s.getPropertyValue(n).trim();
  return {
    accent: get("--accent"),
    good: get("--good"),
    critical: get("--critical"),
    grid: get("--grid"),
    rule: get("--rule-strong"),
    muted: get("--ink-muted"),
  };
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  cssWidth = rect.width;
  cssHeight = rect.height;
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function geometry() {
  const padL = 34;
  const padR = 6;
  const padT = 12;
  const xAxisH = 20;
  const eventHalf = 17;
  const gap = 14;
  return {
    padL,
    padR,
    plotTop: padT,
    plotBottom: cssHeight - xAxisH - eventHalf * 2 - gap,
    plotW: Math.max(cssWidth - padL - padR, 10),
    eventBaseline: cssHeight - xAxisH - eventHalf,
    eventHalf,
  };
}

function drawChart() {
  const p = palette();
  const g = geometry();
  const now = Date.now() / 1000;
  const t0 = now - WINDOW_SECONDS;
  const cap = Math.max(state.capacity, 1);

  const xFor = (t) => g.padL + ((t - t0) / WINDOW_SECONDS) * g.plotW;
  const yFor = (v) => g.plotBottom - (v / cap) * (g.plotBottom - g.plotTop);

  ctx.clearRect(0, 0, cssWidth, cssHeight);

  const font = getComputedStyle(document.body).fontFamily;
  const ticks = cap <= 2 ? [0, cap] : [0, Math.round(cap / 2), cap];
  ctx.lineWidth = 1;
  ctx.font = "500 10.5px " + font;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";

  ticks.forEach((v) => {
    const y = Math.round(yFor(v)) + 0.5;
    ctx.strokeStyle = p.grid;
    ctx.beginPath();
    ctx.moveTo(g.padL, y);
    ctx.lineTo(g.padL + g.plotW, y);
    ctx.stroke();
    ctx.fillStyle = p.muted;
    ctx.fillText(String(v), g.padL - 8, y);
  });

  const samples = state.samples.filter((s) => s.t >= t0);
  if (samples.length > 1) {
    const trace = () => {
      ctx.beginPath();
      samples.forEach((s, i) => {
        const x = xFor(s.t);
        const y = yFor(s.remaining);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
    };

    trace();
    ctx.save();
    ctx.lineTo(xFor(samples[samples.length - 1].t), g.plotBottom);
    ctx.lineTo(xFor(samples[0].t), g.plotBottom);
    ctx.closePath();
    ctx.globalAlpha = 0.09;
    ctx.fillStyle = p.accent;
    ctx.fill();
    ctx.restore();

    trace();
    ctx.strokeStyle = p.accent;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();
  }

  const baseY = Math.round(g.eventBaseline) + 0.5;
  ctx.strokeStyle = p.rule;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(g.padL, baseY);
  ctx.lineTo(g.padL + g.plotW, baseY);
  ctx.stroke();

  ctx.lineWidth = 2;
  ctx.lineCap = "butt";
  state.events.forEach((ev) => {
    if (ev.t < t0) return;
    const x = Math.round(xFor(ev.t)) + 0.5;
    ctx.strokeStyle = ev.allowed ? p.good : p.critical;
    ctx.beginPath();
    ctx.moveTo(x, baseY);
    ctx.lineTo(x, ev.allowed ? baseY - g.eventHalf : baseY + g.eventHalf);
    ctx.stroke();
  });

  ctx.fillStyle = p.muted;
  ctx.textBaseline = "alphabetic";
  const labelY = cssHeight - 5;
  [
    { t: t0, text: `${WINDOW_SECONDS}s ago`, align: "left" },
    { t: now - WINDOW_SECONDS / 2, text: `${WINDOW_SECONDS / 2}s`, align: "center" },
    { t: now, text: "now", align: "right" },
  ].forEach(({ t, text, align }) => {
    ctx.textAlign = align;
    ctx.fillText(text, xFor(t), labelY);
  });

  if (state.hoverX !== null) {
    const x = Math.round(state.hoverX) + 0.5;
    if (x >= g.padL && x <= g.padL + g.plotW) {
      ctx.strokeStyle = p.rule;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, g.plotTop);
      ctx.lineTo(x, baseY + g.eventHalf);
      ctx.stroke();
    }
  }
}

function draw() {
  if (cssWidth === 0) resizeCanvas();
  drawChart();
}

/* ---------------------------------------------------------------- tooltip */

function updateTooltip(clientX, clientY) {
  const tip = el("tooltip");
  const rect = canvas.getBoundingClientRect();
  const g = geometry();
  const x = clientX - rect.left;

  if (x < g.padL || x > g.padL + g.plotW || state.samples.length === 0) {
    tip.classList.remove("visible");
    state.hoverX = null;
    return;
  }

  const now = Date.now() / 1000;
  const t = now - WINDOW_SECONDS + ((x - g.padL) / g.plotW) * WINDOW_SECONDS;

  let nearest = null;
  let best = Infinity;
  for (const s of state.samples) {
    const d = Math.abs(s.t - t);
    if (d < best) {
      best = d;
      nearest = s;
    }
  }
  if (!nearest) return;

  const span = (WINDOW_SECONDS / g.plotW) * 4;
  const near = state.events.filter((ev) => Math.abs(ev.t - t) <= span);
  const allowedCount = near.filter((ev) => ev.allowed).length;
  const blockedCount = near.length - allowedCount;

  let html = `<div class="tt-time">${(now - t).toFixed(1)}s ago</div>`;
  html += `<div class="tt-row"><i class="swatch line"></i>Quota <span class="tt-val">${nearest.remaining}</span></div>`;
  if (allowedCount) html += `<div class="tt-row"><i class="swatch up"></i>Allowed <span class="tt-val">${allowedCount}</span></div>`;
  if (blockedCount) html += `<div class="tt-row"><i class="swatch down"></i>Rejected <span class="tt-val">${blockedCount}</span></div>`;
  tip.innerHTML = html;
  tip.classList.add("visible");

  tip.style.left = `${Math.min(Math.max(x + 12, 0), rect.width - tip.offsetWidth - 2)}px`;
  tip.style.top = `${Math.max(clientY - rect.top - 10, 4)}px`;
  state.hoverX = x;
}

/* ---------------------------------------------------------------- loop */

async function sample() {
  const { ok, data } = await api(`/limiter/peek?client_id=${encodeURIComponent(clientId())}`);
  setConnected(ok);
  if (!ok) return;

  const t = Date.now() / 1000;
  state.capacity = data.limit;
  state.samples.push({ t, remaining: data.remaining });

  const cutoff = t - WINDOW_SECONDS - 1;
  while (state.samples.length && state.samples[0].t < cutoff) state.samples.shift();
  while (state.events.length && state.events[0].t < cutoff - 60) state.events.shift();
}

function tick() {
  draw();
  requestAnimationFrame(tick);
}

/* ---------------------------------------------------------------- wiring */

function wire() {
  el("algorithm").addEventListener("change", syncAlgorithmFields);
  el("applyConfig").addEventListener("click", applyConfig);
  el("resetState").addEventListener("click", resetAll);
  el("fireOnce").addEventListener("click", fireOnce);
  el("fireBurst").addEventListener("click", () => fireBurst(20));
  el("clientId").addEventListener("input", updateSnippet);

  el("autoFireToggle").addEventListener("change", (e) => {
    if (e.target.checked) startAuto();
    else stopAuto();
  });

  el("fireRate").addEventListener("input", (e) => {
    el("rateValue").textContent = e.target.value;
    if (state.autoTimer) startAuto();
  });

  el("tableToggle").addEventListener("click", () => {
    const wrap = el("tableWrap");
    const nowHidden = !wrap.hidden;
    wrap.hidden = nowHidden;
    el("tableToggle").setAttribute("aria-expanded", String(!nowHidden));
    el("tableToggle").textContent = nowHidden ? "Show request log" : "Hide request log";
    renderTable();
  });

  canvas.addEventListener("mousemove", (e) => updateTooltip(e.clientX, e.clientY));
  canvas.addEventListener("mouseleave", () => {
    el("tooltip").classList.remove("visible");
    state.hoverX = null;
  });

  new ResizeObserver(() => {
    resizeCanvas();
    draw();
  }).observe(canvas);

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);
}

(async function init() {
  wire();
  updateSnippet();
  resizeCanvas();
  await loadConfig();
  await resetAll();
  setInterval(sample, SAMPLE_MS);
  requestAnimationFrame(tick);
})();
