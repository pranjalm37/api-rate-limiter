const WINDOW_SECONDS = 30; // visible time span of the chart
const SAMPLE_MS = 50; // how often available quota is sampled via peek()
const MAX_LOG_ROWS = 200;

const el = (id) => document.getElementById(id);

const state = {
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

/* ---------------------------------------------------------------- config */

function currentAlgorithmKey() {
  return el("algorithm").value;
}

function syncAlgorithmFields() {
  const spec = ALGORITHMS[currentAlgorithmKey()];
  el("refillField").classList.toggle("hidden", !spec.usesRefill);
  el("windowField").classList.toggle("hidden", spec.usesRefill);
  el("capacityLabel").textContent = spec.usesRefill ? "Bucket size" : "Limit";
  el("chartAlgoName").textContent = spec.label;
  el("chartSub").textContent = spec.usesRefill
    ? `Last ${WINDOW_SECONDS} seconds. Tokens refill continuously; each request is a tick — up if allowed, down if rejected.`
    : `Last ${WINDOW_SECONDS} seconds. Each request is a tick — up if allowed, down if rejected.`;
  highlightReferenceRow();
}

function buildLimiter() {
  const spec = ALGORITHMS[currentAlgorithmKey()];
  const capacity = Math.max(1, Number(el("capacity").value) || 1);
  state.capacity = capacity;
  return spec.usesRefill
    ? new spec.ctor(capacity, Math.max(0.1, Number(el("refillRate").value) || 1))
    : new spec.ctor(capacity, Math.max(1, Number(el("windowSeconds").value) || 1));
}

function resetAll() {
  state.limiter = buildLimiter();
  // Seed the trace so the line spans the full window immediately: a fresh
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

/* ---------------------------------------------------------------- traffic */

function fireOnce() {
  if (!state.limiter) return;
  const result = state.limiter.check();
  const t = Date.now() / 1000;

  state.total += 1;
  if (result.allowed) state.allowed += 1;
  else state.blocked += 1;

  state.events.push({ t, allowed: result.allowed, remaining: result.remaining });
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
  const rows = state.events.slice(-MAX_LOG_ROWS).reverse();
  const now = Date.now() / 1000;
  el("tableBody").innerHTML = rows
    .map((ev) => {
      const ago = (now - ev.t).toFixed(1);
      const cls = ev.allowed ? "outcome-allowed" : "outcome-blocked";
      const label = ev.allowed ? "Allowed" : "Rejected";
      return `<tr><td>${ago}s ago</td><td class="${cls}">${label}</td><td>${ev.remaining}</td></tr>`;
    })
    .join("");
}

function highlightReferenceRow() {
  const active = currentAlgorithmKey();
  document.querySelectorAll("#referenceBody tr").forEach((tr) => {
    tr.dataset.active = String(tr.dataset.key === active);
  });
}

function buildReferenceTable() {
  const meta = {
    token_bucket: { accuracy: "Exact", cost: "O(1)" },
    fixed_window: { accuracy: "Loose at edges", cost: "O(1)" },
    sliding_window_log: { accuracy: "Exact", cost: "O(requests)" },
    sliding_window_counter: { accuracy: "Approximate", cost: "O(1)" },
  };
  const order = ["token_bucket", "fixed_window", "sliding_window_log", "sliding_window_counter"];
  el("referenceBody").innerHTML = order
    .map((key) => {
      const spec = ALGORITHMS[key];
      const m = meta[key];
      return `<tr data-key="${key}"><td>${spec.label}</td><td>${m.accuracy}</td><td>${m.cost}</td><td>${spec.blurb}</td></tr>`;
    })
    .join("");
  highlightReferenceRow();
}

/* ---------------------------------------------------------------- chart */

const canvas = el("chart");
const ctx = canvas.getContext("2d");
let cssWidth = 0;
let cssHeight = 0;

function palette() {
  const s = getComputedStyle(document.documentElement);
  const get = (name) => s.getPropertyValue(name).trim();
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
  const padL = 34;
  const padR = 6;
  const padT = 12;
  const xAxisH = 20;
  const eventHalf = 17; // tick reach above/below the event baseline
  const gap = 14;

  const plotTop = padT;
  const plotBottom = cssHeight - xAxisH - eventHalf * 2 - gap;
  const eventBaseline = cssHeight - xAxisH - eventHalf;

  return {
    padL,
    padR,
    plotTop,
    plotBottom,
    plotW: Math.max(cssWidth - padL - padR, 10),
    eventBaseline,
    eventHalf,
  };
}

function drawChart() {
  const p = palette();
  const g = geometry();
  const now = Date.now() / 1000;
  const t0 = now - WINDOW_SECONDS;
  const cap = state.capacity;

  const xFor = (t) => g.padL + ((t - t0) / WINDOW_SECONDS) * g.plotW;
  const yFor = (v) => g.plotBottom - (v / cap) * (g.plotBottom - g.plotTop);

  ctx.clearRect(0, 0, cssWidth, cssHeight);

  // --- horizontal gridlines + y ticks (0, half, capacity) ---
  const ticks = cap <= 2 ? [0, cap] : [0, Math.round(cap / 2), cap];
  ctx.lineWidth = 1;
  ctx.font = "500 10.5px " + getComputedStyle(document.body).fontFamily;
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

  // --- quota trace ---
  const samples = state.samples.filter((s) => s.t >= t0);
  if (samples.length > 1) {
    ctx.beginPath();
    samples.forEach((s, i) => {
      const x = xFor(s.t);
      const y = yFor(s.remaining);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });

    // soft fill beneath the line, then the line itself
    const lastX = xFor(samples[samples.length - 1].t);
    const firstX = xFor(samples[0].t);
    ctx.save();
    ctx.lineTo(lastX, g.plotBottom);
    ctx.lineTo(firstX, g.plotBottom);
    ctx.closePath();
    ctx.globalAlpha = 0.09;
    ctx.fillStyle = p.accent;
    ctx.fill();
    ctx.restore();

    ctx.beginPath();
    samples.forEach((s, i) => {
      const x = xFor(s.t);
      const y = yFor(s.remaining);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = p.accent;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();
  }

  // --- event baseline ---
  const baseY = Math.round(g.eventBaseline) + 0.5;
  ctx.strokeStyle = p.rule;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(g.padL, baseY);
  ctx.lineTo(g.padL + g.plotW, baseY);
  ctx.stroke();

  // --- event ticks: allowed rise, rejected fall (position, not colour alone) ---
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

  // --- x axis labels ---
  ctx.fillStyle = p.muted;
  ctx.font = "500 10.5px " + getComputedStyle(document.body).fontFamily;
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

  // --- hover crosshair ---
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

  if (x < g.padL || x > g.padL + g.plotW) {
    tip.classList.remove("visible");
    state.hoverX = null;
    return;
  }

  const now = Date.now() / 1000;
  const t0 = now - WINDOW_SECONDS;
  const t = t0 + ((x - g.padL) / g.plotW) * WINDOW_SECONDS;

  let nearest = null;
  let bestDelta = Infinity;
  for (const s of state.samples) {
    const d = Math.abs(s.t - t);
    if (d < bestDelta) {
      bestDelta = d;
      nearest = s;
    }
  }
  if (!nearest) {
    tip.classList.remove("visible");
    state.hoverX = null;
    return;
  }

  const span = (WINDOW_SECONDS / g.plotW) * 4; // events within ~4px of the cursor
  const near = state.events.filter((ev) => Math.abs(ev.t - t) <= span);
  const allowedCount = near.filter((ev) => ev.allowed).length;
  const blockedCount = near.length - allowedCount;

  const p = palette();
  let html = `<div class="tt-time">${(now - t).toFixed(1)}s ago</div>`;
  html += `<div class="tt-row"><i class="swatch line"></i>Quota <span class="tt-val">${nearest.remaining}</span></div>`;
  if (allowedCount) {
    html += `<div class="tt-row"><i class="swatch up"></i>Allowed <span class="tt-val">${allowedCount}</span></div>`;
  }
  if (blockedCount) {
    html += `<div class="tt-row"><i class="swatch down"></i>Rejected <span class="tt-val">${blockedCount}</span></div>`;
  }
  tip.innerHTML = html;
  tip.classList.add("visible");

  const tipW = tip.offsetWidth;
  const left = Math.min(Math.max(x + 12, 0), rect.width - tipW - 2);
  tip.style.left = `${left}px`;
  tip.style.top = `${Math.max(clientY - rect.top - 10, 4)}px`;

  state.hoverX = x;
}

/* ---------------------------------------------------------------- loop */

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

/* ---------------------------------------------------------------- wiring */

function wire() {
  el("algorithm").addEventListener("change", () => {
    syncAlgorithmFields();
    resetAll();
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

(function init() {
  buildReferenceTable();
  wire();
  syncAlgorithmFields();
  resizeCanvas();
  resetAll();
  setInterval(sample, SAMPLE_MS);
  requestAnimationFrame(tick);
})();
