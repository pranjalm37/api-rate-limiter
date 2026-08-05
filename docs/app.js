const WINDOW_SECONDS = 30; // visible span of the chart
const SAMPLE_MS = 50; // how often available quota is sampled via peek()
const MAX_LOG_ROWS = 200;

const el = (id) => document.getElementById(id);

const state = {
  algorithm: "token_bucket",
  limiter: null,
  capacity: 10,
  samples: [], // { t, remaining } — continuous quota trace
  events: [], // { t, allowed, remaining }
  total: 0,
  allowed: 0,
  blocked: 0,
  autoTimer: null,
  hoverX: null,
};

/* ------------------------------------------------------------- config */

function syncAlgorithmUI() {
  const spec = ALGORITHMS[state.algorithm];

  document.querySelectorAll(".segmented button").forEach((b) => {
    b.setAttribute("aria-selected", String(b.dataset.algo === state.algorithm));
  });

  el("refillParam").classList.toggle("hidden", !spec.usesRefill);
  el("windowParam").classList.toggle("hidden", spec.usesRefill);
  el("capacityLabel").textContent = spec.usesRefill ? "bucket" : "limit";

  document.querySelectorAll("#referenceBody .ref-row").forEach((row) => {
    row.dataset.active = String(row.dataset.key === state.algorithm);
  });
}

function buildLimiter() {
  const spec = ALGORITHMS[state.algorithm];
  const capacity = Math.max(1, Number(el("capacity").value) || 1);
  state.capacity = capacity;
  return spec.usesRefill
    ? new spec.ctor(capacity, Math.max(0.1, Number(el("refillRate").value) || 1))
    : new spec.ctor(capacity, Math.max(1, Number(el("windowSeconds").value) || 1));
}

function resetAll() {
  state.limiter = buildLimiter();

  // Seed the trace so the line spans the full window straight away: a fresh
  // limiter has been sitting at full quota with nothing consuming from it.
  const t = Date.now() / 1000;
  const full = state.limiter.peek();
  state.samples = [];
  for (let dt = WINDOW_SECONDS; dt >= 0; dt -= SAMPLE_MS / 1000) {
    state.samples.push({ t: t - dt, remaining: full });
  }

  state.events = [];
  state.total = 0;
  state.allowed = 0;
  state.blocked = 0;
  renderStats();
  renderTable();
  draw();
}

/* ------------------------------------------------------------- traffic */

function fireOnce() {
  if (!state.limiter) return;
  const result = state.limiter.check();

  state.total += 1;
  if (result.allowed) state.allowed += 1;
  else state.blocked += 1;

  state.events.push({ t: Date.now() / 1000, allowed: result.allowed, remaining: result.remaining });
  if (state.events.length > 4000) state.events.splice(0, 2000);

  renderStats();
  renderTable();
}

function fireBurst(n) {
  for (let i = 0; i < n; i++) fireOnce();
}

function startAuto() {
  stopAuto();
  const rate = Number(el("fireRate").value);
  state.autoTimer = setInterval(fireOnce, Math.max(1000 / rate, 25));
  el("liveIndicator").classList.add("on");
}

function stopAuto() {
  if (state.autoTimer) clearInterval(state.autoTimer);
  state.autoTimer = null;
  el("liveIndicator").classList.remove("on");
}

/* ------------------------------------------------------------- readouts */

function renderStats() {
  el("statTotal").textContent = state.total.toLocaleString();
  el("statAllowed").textContent = state.allowed.toLocaleString();
  el("statBlocked").textContent = state.blocked.toLocaleString();
  const pct = state.total ? Math.round((state.blocked / state.total) * 100) : 0;
  el("statBlockRate").textContent = pct + "%";
}

function renderTable() {
  if (el("tableWrap").hidden) return;
  const now = Date.now() / 1000;
  el("tableBody").innerHTML = state.events
    .slice(-MAX_LOG_ROWS)
    .reverse()
    .map((ev) => {
      const cls = ev.allowed ? "allowed" : "rejected";
      const label = ev.allowed ? "allowed" : "rejected";
      return `<tr><td>${(now - ev.t).toFixed(1)}s ago</td><td class="${cls}">${label}</td><td>${ev.remaining}</td></tr>`;
    })
    .join("");
}

function buildReference() {
  const meta = {
    token_bucket: { accuracy: "exact", cost: "O(1)" },
    fixed_window: { accuracy: "loose at edges", cost: "O(1)" },
    sliding_window_log: { accuracy: "exact", cost: "O(requests)" },
    sliding_window_counter: { accuracy: "approximate", cost: "O(1)" },
  };
  const order = ["token_bucket", "fixed_window", "sliding_window_log", "sliding_window_counter"];
  el("referenceBody").innerHTML = order
    .map((key) => {
      const spec = ALGORITHMS[key];
      const m = meta[key];
      return `<div class="ref-row" data-key="${key}">
        <h4>${spec.label}</h4>
        <div class="meta"><i>${m.accuracy}</i><br>${m.cost} per key</div>
        <p>${spec.blurb}</p>
      </div>`;
    })
    .join("");
}

/* ------------------------------------------------------------- chart */

const canvas = el("chart");
const ctx = canvas.getContext("2d");
let cssWidth = 0;
let cssHeight = 0;

const MONO = '"Geist Mono", ui-monospace, SFMono-Regular, Menlo, monospace';

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
    surface: get("--surface"),
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
  const padL = 30;
  const padR = 34; // room for the direct end-label
  const padT = 14;
  const xAxisH = 18;
  const eventHalf = 16;
  const gap = 13;
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

  // gridlines + y ticks
  const ticks = cap <= 2 ? [0, cap] : [0, Math.round(cap / 2), cap];
  ctx.lineWidth = 1;
  ctx.font = "500 10px " + MONO;
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
    ctx.fillText(String(v), g.padL - 7, y);
  });

  // quota trace
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
    ctx.globalAlpha = 0.07;
    ctx.fillStyle = p.accent;
    ctx.fill();
    ctx.restore();

    trace();
    ctx.strokeStyle = p.accent;
    ctx.lineWidth = 1.75;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();

    // direct label at the live end of the line, instead of labelling every point
    const last = samples[samples.length - 1];
    const lx = xFor(last.t);
    const ly = yFor(last.remaining);
    ctx.fillStyle = p.accent;
    ctx.beginPath();
    ctx.arc(lx, ly, 2.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.font = "560 11px " + MONO;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(String(last.remaining), lx + 7, ly);
  }

  // event baseline
  const baseY = Math.round(g.eventBaseline) + 0.5;
  ctx.strokeStyle = p.rule;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(g.padL, baseY);
  ctx.lineTo(g.padL + g.plotW, baseY);
  ctx.stroke();

  // request ticks: allowed rise, rejected fall (direction, not colour alone)
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

  // x axis
  ctx.fillStyle = p.muted;
  ctx.font = "500 10px " + MONO;
  ctx.textBaseline = "alphabetic";
  const labelY = cssHeight - 4;
  [
    { t: t0, text: "-30s", align: "left" },
    { t: now - WINDOW_SECONDS / 2, text: "-15s", align: "center" },
    { t: now, text: "now", align: "right" },
  ].forEach(({ t, text, align }) => {
    ctx.textAlign = align;
    ctx.fillText(text, xFor(t), labelY);
  });

  // hover crosshair
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

/* ------------------------------------------------------------- tooltip */

function updateTooltip(clientX, clientY) {
  const tip = el("tooltip");
  const rect = canvas.getBoundingClientRect();
  const g = geometry();
  const x = clientX - rect.left;

  if (x < g.padL || x > g.padL + g.plotW || !state.samples.length) {
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
  html += `<div class="tt-row"><i class="swatch line"></i>quota<span class="tt-val">${nearest.remaining}</span></div>`;
  if (allowedCount) html += `<div class="tt-row"><i class="swatch up"></i>allowed<span class="tt-val">${allowedCount}</span></div>`;
  if (blockedCount) html += `<div class="tt-row"><i class="swatch down"></i>rejected<span class="tt-val">${blockedCount}</span></div>`;
  tip.innerHTML = html;
  tip.classList.add("visible");

  const shell = canvas.parentElement.getBoundingClientRect();
  const offsetX = rect.left - shell.left;
  tip.style.left = `${Math.min(Math.max(x + offsetX + 12, 0), shell.width - tip.offsetWidth - 2)}px`;
  tip.style.top = `${Math.max(clientY - rect.top - 10, 4)}px`;
  state.hoverX = x;
}

/* ------------------------------------------------------------- loop */

function sample() {
  if (!state.limiter) return;
  const t = Date.now() / 1000;
  state.samples.push({ t, remaining: state.limiter.peek() });
  const cutoff = t - WINDOW_SECONDS - 1;
  while (state.samples.length && state.samples[0].t < cutoff) state.samples.shift();
  while (state.events.length && state.events[0].t < cutoff - 60) state.events.shift();
}

function tick() {
  draw(); // sampling runs on its own fixed interval, independent of frame rate
  requestAnimationFrame(tick);
}

/* ------------------------------------------------------------- wiring */

function wire() {
  document.querySelectorAll(".segmented button").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.algorithm = btn.dataset.algo;
      syncAlgorithmUI();
      resetAll();
    });
  });

  ["capacity", "windowSeconds", "refillRate"].forEach((id) => {
    el(id).addEventListener("change", resetAll);
  });

  el("resetState").addEventListener("click", resetAll);
  el("fireOnce").addEventListener("click", fireOnce);
  el("fireBurst").addEventListener("click", () => fireBurst(20));

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
    const opening = wrap.hidden;
    wrap.hidden = !opening;
    el("tableToggle").setAttribute("aria-expanded", String(opening));
    el("tableToggle").textContent = opening ? "Hide request log" : "Show request log";
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

(function init() {
  buildReference();
  wire();
  syncAlgorithmUI();
  resizeCanvas();
  resetAll();
  setInterval(sample, SAMPLE_MS);
  // The log shows ages relative to now, so refresh it on a timer as well as on
  // each request -- otherwise every row sits frozen at "0.0s ago".
  setInterval(renderTable, 500);
  requestAnimationFrame(tick);

  // Canvas text is rasterised at draw time, so it silently falls back to a
  // system font unless we redraw once the webfont is actually available.
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(draw);
})();
