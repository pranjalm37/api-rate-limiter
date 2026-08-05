const MAX_EVENTS = 160;

const el = (id) => document.getElementById(id);

const state = {
  limiter: null,
  total: 0,
  allowed: 0,
  blocked: 0,
  events: [],
  autoFireTimer: null,
};

function syncAlgorithmFields() {
  const algo = el("algorithm").value;
  const isTokenBucket = algo === "token_bucket";
  el("refillRow").classList.toggle("hidden", !isTokenBucket);
  el("windowRow").classList.toggle("hidden", isTokenBucket);
  el("capacityHint").textContent = isTokenBucket
    ? "(bucket size, i.e. max burst)"
    : "(max requests / window)";
}

function buildLimiter() {
  const algo = el("algorithm").value;
  const capacity = Number(el("capacity").value);
  const windowSeconds = Number(el("windowSeconds").value);
  const refillRate = Number(el("refillRate").value);
  const spec = ALGORITHMS[algo];

  if (spec.usesRefill) {
    return new spec.ctor(capacity, refillRate);
  }
  return new spec.ctor(capacity, windowSeconds);
}

function applyConfig() {
  state.limiter = buildLimiter();
  resetStats();
}

function resetState() {
  state.limiter = buildLimiter();
  resetStats();
}

function resetStats() {
  state.total = 0;
  state.allowed = 0;
  state.blocked = 0;
  state.events = [];
  renderStats();
  renderRemaining(null, null);
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
  if (remaining === null) {
    el("remainingText").textContent = "-- / --";
    el("remainingFill").style.width = "100%";
    return;
  }
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

function fireOnce() {
  if (!state.limiter) return;
  const result = state.limiter.check();

  state.total += 1;
  if (result.allowed) state.allowed += 1;
  else state.blocked += 1;

  state.events.push({ allowed: result.allowed });
  if (state.events.length > MAX_EVENTS) state.events.shift();

  renderStats();
  renderRemaining(result.remaining, result.limit);
  drawChart();
}

function fireBurst(count = 20) {
  for (let i = 0; i < count; i++) fireOnce();
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

function wire() {
  el("algorithm").addEventListener("change", () => {
    syncAlgorithmFields();
  });
  el("applyConfig").addEventListener("click", applyConfig);
  el("resetState").addEventListener("click", resetState);
  el("fireOnce").addEventListener("click", fireOnce);
  el("fireBurst").addEventListener("click", () => fireBurst(20));

  el("autoFireToggle").addEventListener("change", (e) => {
    if (e.target.checked) startAutoFire();
    else stopAutoFire();
  });
  el("fireRate").addEventListener("input", (e) => {
    el("rateValue").textContent = e.target.value;
    if (state.autoFireTimer) startAutoFire();
  });
}

(function init() {
  wire();
  syncAlgorithmFields();
  state.limiter = buildLimiter();
  drawChart();
})();
