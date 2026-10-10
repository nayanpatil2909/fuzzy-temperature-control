/**
 * script.js — Fuzzy Smart Temperature Control Dashboard
 * =======================================================
 * Handles all API communication, chart rendering, gauge drawing,
 * membership bar updates, rule matrix, and educational tabs.
 */

'use strict';

// ─── Configuration ─────────────────────────────────────────────────────────
const API_BASE = 'http://localhost:8000';

// Cooling-level colour map (consistent with CSS variables)
const LEVEL_COLORS = {
  'Very Low':  { fill: 'rgba(6,182,212,0.7)',   border: '#06b6d4' },
  'Low':       { fill: 'rgba(59,130,246,0.7)',  border: '#3b82f6' },
  'Medium':    { fill: 'rgba(139,92,246,0.7)',  border: '#8b5cf6' },
  'High':      { fill: 'rgba(245,158,11,0.7)',  border: '#f59e0b' },
  'Very High': { fill: 'rgba(239,68,68,0.7)',   border: '#ef4444' },
};

// Output MF colours
const MF_COLORS = {
  VL: 'rgba(6,182,212,0.75)',
  L:  'rgba(59,130,246,0.75)',
  M:  'rgba(139,92,246,0.75)',
  H:  'rgba(245,158,11,0.75)',
  VH: 'rgba(239,68,68,0.75)',
};

// Error / Delta MF colours
const E_COLORS = ['#ef4444','#f97316','#8b5cf6','#3b82f6','#06b6d4'];
const H_COLORS = ['#06b6d4','#8b5cf6','#ef4444'];

// Chart defaults
Chart.defaults.color = '#8892a4';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;

// ─── State ─────────────────────────────────────────────────────────────────
let lastResult       = null;
let lastSimResult    = null;
let previousError    = 0;

// Chart instances
let aggregatedChart  = null;
let simTempChart     = null;
let simCoolingChart  = null;
let compTempChart    = null;
let compCoolingChart = null;
let mfErrorChart     = null;
let mfDeltaChart     = null;
let mfHumidChart     = null;
let mfCoolingChart   = null;

// ─── DOM Helpers ───────────────────────────────────────────────────────────
const $  = id => document.getElementById(id);
const qsa = sel => document.querySelectorAll(sel);

// ─── Clock ─────────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  $('clockDisplay').textContent =
    `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}
setInterval(updateClock, 1000);
updateClock();

// ─── Toast notification ────────────────────────────────────────────────────
let toastTimer = null;
function showToast(msg, duration = 3000) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), duration);
}

// ─── Slider live display ───────────────────────────────────────────────────
function bindSliders() {
  $('targetTemp').addEventListener('input', e => {
    $('targetVal').textContent = `${parseFloat(e.target.value).toFixed(1)} °C`;
    updateDerivedDisplay();
  });
  $('currentTemp').addEventListener('input', e => {
    $('currentVal').textContent = `${parseFloat(e.target.value).toFixed(1)} °C`;
    updateDerivedDisplay();
  });
  $('humidity').addEventListener('input', e => {
    $('humidityVal').textContent = `${e.target.value} %`;
  });
}

function updateDerivedDisplay() {
  const tgt = parseFloat($('targetTemp').value);
  const cur = parseFloat($('currentTemp').value);
  const e   = tgt - cur;
  const de  = e - previousError;
  $('errorDisplay').textContent  = `${e >= 0 ? '+' : ''}${e.toFixed(1)} °C`;
  $('deltaDisplay').textContent  = `${de >= 0 ? '+' : ''}${de.toFixed(1)} °C/s`;
}

// ─── API call helper ───────────────────────────────────────────────────────
async function apiPost(endpoint, body) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

async function apiGet(endpoint) {
  const res = await fetch(`${API_BASE}${endpoint}`);
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

// ─── Run Predict ──────────────────────────────────────────────────────────
async function runPredict() {
  const btn = $('predictBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Computing…';

  try {
    const tgt = parseFloat($('targetTemp').value);
    const cur = parseFloat($('currentTemp').value);
    const hum = parseFloat($('humidity').value);

    const result = await apiPost('/predict', {
      target_temperature:  tgt,
      current_temperature: cur,
      humidity:            hum,
      previous_error:      previousError,
    });

    lastResult    = result;
    previousError = result.temperature_error;

    updateMembershipBars(result);
    updateRulesList(result);
    updateGauge(result.cooling_power, result.cooling_level);
    updateOutputMeta(result);
    updateExplanation(result);
    updateAggregatedChart(result);
    updateStatusBadge(result.cooling_level, result.cooling_power);
    updateDerivedDisplay();
    highlightRuleMatrix(result.activated_rules);

    showToast(`✅ Inference complete — ${result.cooling_power.toFixed(1)}% cooling`);
  } catch (err) {
    showToast(`❌ Error: ${err.message}`, 5000);
    console.error(err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '⚡ Run Fuzzy Inference';
  }
}

// ─── Membership Bars ──────────────────────────────────────────────────────
function updateMembershipBars(result) {
  const mv = result.membership_values;

  // Error
  for (const lbl of ['NB', 'NS', 'ZE', 'PS', 'PB']) {
    const val = mv.error[lbl] || 0;
    $(`e-${lbl}`).style.width = `${val * 100}%`;
    $(`ev-${lbl}`).textContent = val.toFixed(3);
  }

  // Delta error
  for (const lbl of ['NB', 'NS', 'ZE', 'PS', 'PB']) {
    const val = mv.delta_error[lbl] || 0;
    $(`de-${lbl}`).style.width = `${val * 100}%`;
    $(`dev-${lbl}`).textContent = val.toFixed(3);
  }

  // Humidity
  for (const lbl of ['Low', 'Medium', 'High']) {
    const val = mv.humidity[lbl] || 0;
    $(`h-${lbl}`).style.width  = `${val * 100}%`;
    $(`hv-${lbl}`).textContent = val.toFixed(3);
  }

  // Humidity modifier display
  $('humidModDisplay').textContent = `×${result.humidity_modifier.toFixed(3)}`;
}

// ─── Activated Rules List ─────────────────────────────────────────────────
function updateRulesList(result) {
  const list   = $('rulesList');
  const fired  = result.activated_rules;
  const label  = $('rulesCountLabel');

  label.textContent = `Activated Rules (${fired.length} / 25 fired)`;
  list.innerHTML = '';

  if (fired.length === 0) {
    list.innerHTML = '<div style="font-size:11px;color:var(--text-muted);text-align:center;padding:12px;">No rules fired</div>';
    return;
  }

  // Sort by descending strength
  const sorted = [...fired].sort((a, b) => b.strength - a.strength);
  const maxStr = sorted[0].strength;

  sorted.forEach((r, idx) => {
    const div = document.createElement('div');
    div.className = `rule-item ${idx === 0 ? 'top-rule' : ''}`;

    const levelColor = {
      VL: 'var(--cl-vl)', L: 'var(--cl-l)', M: 'var(--cl-m)',
      H: 'var(--cl-h)', VH: 'var(--cl-vh)'
    }[r.consequent] || 'var(--text-accent)';

    div.innerHTML = `
      <span class="rule-antecedent">#${r.rule_id} · ${r.antecedent}</span>
      <span class="rule-consequent" style="color:${levelColor}">${r.consequent}</span>
      <span class="rule-strength">${r.strength.toFixed(3)}</span>
    `;
    list.appendChild(div);
  });
}

// ─── Output Metadata ──────────────────────────────────────────────────────
function updateOutputMeta(result) {
  $('rawOutput').textContent   = `${result.raw_cooling_power.toFixed(1)}%`;
  $('finalOutput').textContent = `${result.cooling_power.toFixed(1)}%`;
  $('humModMeta').textContent  = `×${result.humidity_modifier.toFixed(3)}`;
  $('rulesFired').textContent  = `${result.activated_rules.length}`;
}

// ─── HTML Viva Explanation ────────────────────────────────────────────────
function updateExplanation(result) {
  const mv  = result.membership_values;
  const S   = STATUS_STYLES[result.cooling_level] || STATUS_STYLES['Medium'];

  // Helper: render a key-value row
  const kv = (k, v, color) =>
    `<div class="viva-kv"><span class="viva-k">${k}</span><span class="viva-v" style="color:${color||'var(--text-primary)'}">${v}</span></div>`;

  // ── Step 1: Fuzzification ──────────────────────────────────────────────
  const mu_e  = mv.error;
  const mu_de = mv.delta_error;
  const mu_h  = mv.humidity;

  const activeE  = Object.entries(mu_e ).filter(([,v]) => v > 0.001).map(([k,v]) => `${k}=${v.toFixed(3)}`).join('  ');
  const activeDe = Object.entries(mu_de).filter(([,v]) => v > 0.001).map(([k,v]) => `${k}=${v.toFixed(3)}`).join('  ');
  const activeH  = Object.entries(mu_h ).filter(([,v]) => v > 0.001).map(([k,v]) => `${k}=${v.toFixed(3)}`).join('  ');

  // ── Step 2: Fired rules ────────────────────────────────────────────────
  const sorted = [...result.activated_rules].sort((a, b) => b.strength - a.strength);
  const ruleRows = sorted.map(r => {
    const c = { VL:'var(--cl-vl)', L:'var(--cl-l)', M:'var(--cl-m)', H:'var(--cl-h)', VH:'var(--cl-vh)' }[r.consequent] || 'var(--cyan)';
    return `<div class="viva-rule">
      <span style="color:var(--text-muted);min-width:28px;">#${r.rule_id}</span>
      <span style="flex:1;color:var(--text-secondary);">${r.antecedent}</span>
      <span style="color:${c};font-weight:700;min-width:22px;">${r.consequent}</span>
      <div class="strength-bar"><div class="strength-fill" style="width:${r.strength*100}%"></div></div>
      <span style="color:var(--yellow);min-width:36px;text-align:right;">${r.strength.toFixed(3)}</span>
    </div>`;
  }).join('');

  // ── Assemble HTML ──────────────────────────────────────────────────────
  const html = `
  <div class="viva-pipeline">
    <div class="viva-step">
      <div class="viva-step-hdr" style="background:rgba(0,212,255,0.07);color:var(--cyan);">
        <span>1</span><span>Fuzzification — Crisp inputs → Membership degrees</span>
      </div>
      <div class="viva-step-body">
        ${kv('Error  e = T_t − T_c', result.temperature_error.toFixed(2) + ' °C', result.temperature_error < 0 ? 'var(--red)' : 'var(--green)')}
        ${kv('Rate  Δe = e(t)−e(t−1)', result.delta_error !== undefined ? (result.delta_error.toFixed(2) + ' °C/step') : '—', 'var(--purple)')}
        <div class="viva-kv" style="grid-column:1/-1">
          <span class="viva-k">μ(e)</span>
          <span class="viva-v mono" style="color:var(--cyan); font-size:10px;">${activeE || '—'}</span>
        </div>
        <div class="viva-kv" style="grid-column:1/-1">
          <span class="viva-k">μ(Δe)</span>
          <span class="viva-v mono" style="color:var(--purple); font-size:10px;">${activeDe || '—'}</span>
        </div>
        <div class="viva-kv" style="grid-column:1/-1">
          <span class="viva-k">μ(H=${result.membership_values.humidity ? Object.entries(mu_h).find(([,v])=>v>0.5)?.[0]||'—' : '—'})</span>
          <span class="viva-v mono" style="color:var(--yellow); font-size:10px;">${activeH || '—'}</span>
        </div>
      </div>
    </div>

    <div class="viva-step">
      <div class="viva-step-hdr" style="background:rgba(139,92,246,0.07);color:var(--purple);">
        <span>2</span><span>Rule Evaluation — IF e=__ AND Δe=__ THEN Cooling=__</span>
      </div>
      <div class="viva-step-body">
        <div class="viva-kv" style="grid-column:1/-1">
          <span class="viva-k">AND operator</span>
          <span class="viva-v">min(μ_e, μ_Δe) per rule</span>
        </div>
        <div class="viva-kv" style="grid-column:1/-1">
          <span class="viva-k">${sorted.length} rule(s) fired</span>
          <span class="viva-v" style="color:var(--yellow);">dominant: ${sorted[0]?.antecedent || '—'} → ${sorted[0]?.consequent || '—'}</span>
        </div>
        <div class="viva-rule-list">${ruleRows || '<span style="color:var(--text-muted);font-size:11px;">No rules fired</span>'}</div>
      </div>
    </div>

    <div class="viva-step">
      <div class="viva-step-hdr" style="background:rgba(245,158,11,0.07);color:var(--yellow);">
        <span>3–4</span><span>Implication + Aggregation — Clip output MFs, then max</span>
      </div>
      <div class="viva-step-body">
        ${kv('Implication', 'Clip each output MF at rule strength (min)', 'var(--text-secondary)')}
        ${kv('Aggregation', 'μ_agg(u) = max over all clipped MFs', 'var(--text-secondary)')}
      </div>
    </div>

    <div class="viva-step">
      <div class="viva-step-hdr" style="background:rgba(16,185,129,0.07);color:var(--green);">
        <span>5</span><span>Defuzzification — u* = Σ(u·μ) / Σ(μ)</span>
      </div>
      <div class="viva-step-body">
        ${kv('Method', 'Centroid (Center of Gravity)', 'var(--text-secondary)')}
        ${kv('Universe', '[0, 100], 201 points', 'var(--text-secondary)')}
        ${kv('Raw output u*', result.raw_cooling_power.toFixed(2) + '%', 'var(--orange)')}
      </div>
    </div>

    <div class="viva-step">
      <div class="viva-step-hdr" style="background:rgba(249,115,22,0.07);color:var(--orange);">
        <span>6</span><span>Humidity Modifier — Final = clip(u* × m, 0, 100)</span>
      </div>
      <div class="viva-step-body">
        ${kv('Modifier m', '×' + result.humidity_modifier.toFixed(3), result.humidity_modifier > 1 ? 'var(--red)' : result.humidity_modifier < 1 ? 'var(--cl-vl)' : 'var(--green)')}
        ${kv('Calculation', result.raw_cooling_power.toFixed(1) + '% × ' + result.humidity_modifier.toFixed(3), 'var(--text-secondary)')}
        <div class="viva-final-row">
          <div class="viva-final-badge" style="background:${S.bg};border-color:${S.border};color:${S.color};">
            ${result.cooling_power.toFixed(1)}% · ${result.cooling_level.toUpperCase()}
          </div>
        </div>
      </div>
    </div>
  </div>`;

  $('explanationBox').innerHTML = html;
}

// ─── Status Badge ─────────────────────────────────────────────────────────
const STATUS_STYLES = {
  'Very Low':  { bg: 'rgba(6,182,212,0.12)',  border: 'rgba(6,182,212,0.4)',  color: '#06b6d4' },
  'Low':       { bg: 'rgba(59,130,246,0.12)', border: 'rgba(59,130,246,0.4)', color: '#3b82f6' },
  'Medium':    { bg: 'rgba(139,92,246,0.12)', border: 'rgba(139,92,246,0.4)', color: '#8b5cf6' },
  'High':      { bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.4)', color: '#f59e0b' },
  'Very High': { bg: 'rgba(239,68,68,0.12)',  border: 'rgba(239,68,68,0.4)',  color: '#ef4444' },
};

function updateStatusBadge(level, power) {
  const badge  = $('statusBadge');
  const sText  = $('statusText');
  const s      = STATUS_STYLES[level] || STATUS_STYLES['Medium'];
  badge.style.background   = s.bg;
  badge.style.borderColor  = s.border;
  badge.style.color        = s.color;
  sText.textContent        = `COOLING: ${level.toUpperCase()}  (${power.toFixed(0)}%)`;

  const lBadge = $('coolingBadge');
  lBadge.textContent            = level.toUpperCase();
  lBadge.style.background       = s.bg;
  lBadge.style.borderColor      = s.border;
  lBadge.style.color            = s.color;
}

// ─── Gauge (Canvas Arc) ───────────────────────────────────────────────────
function drawGauge(value, level) {
  const canvas  = $('gaugeCanvas');
  const ctx     = canvas.getContext('2d');
  const W       = canvas.width;
  const H       = canvas.height;
  const cx      = W / 2;
  const cy      = H - 20;
  const R       = 110;

  ctx.clearRect(0, 0, W, H);

  // Tick marks
  for (let i = 0; i <= 10; i++) {
    const angle = Math.PI + (i / 10) * Math.PI;
    const ix1 = cx + (R - 8) * Math.cos(angle);
    const iy1 = cy + (R - 8) * Math.sin(angle);
    const ix2 = cx + (R - 18) * Math.cos(angle);
    const iy2 = cy + (R - 18) * Math.sin(angle);
    ctx.beginPath();
    ctx.moveTo(ix1, iy1);
    ctx.lineTo(ix2, iy2);
    ctx.strokeStyle = 'rgba(255,255,255,0.12)';
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  // Background arc
  ctx.beginPath();
  ctx.arc(cx, cy, R, Math.PI, 2 * Math.PI);
  ctx.strokeStyle = 'rgba(255,255,255,0.07)';
  ctx.lineWidth = 22;
  ctx.lineCap = 'round';
  ctx.stroke();

  // Coloured value arc
  const clampedVal = Math.max(0, Math.min(100, value));
  const endAngle   = Math.PI + (clampedVal / 100) * Math.PI;
  const s = STATUS_STYLES[level] || STATUS_STYLES['Medium'];

  // Gradient
  const grad = ctx.createLinearGradient(cx - R, cy, cx + R, cy);
  grad.addColorStop(0, '#06b6d4');
  grad.addColorStop(0.5, '#8b5cf6');
  grad.addColorStop(1, s.color);

  ctx.beginPath();
  ctx.arc(cx, cy, R, Math.PI, endAngle);
  ctx.strokeStyle = grad;
  ctx.lineWidth = 22;
  ctx.lineCap = 'round';
  ctx.stroke();

  // Glow effect
  ctx.beginPath();
  ctx.arc(cx, cy, R, Math.PI, endAngle);
  ctx.strokeStyle = s.color;
  ctx.lineWidth = 4;
  ctx.globalAlpha = 0.3;
  ctx.filter = 'blur(6px)';
  ctx.stroke();
  ctx.globalAlpha = 1;
  ctx.filter = 'none';

  // Centre value text
  ctx.textAlign = 'center';
  ctx.fillStyle = '#e2e8f0';
  ctx.font = 'bold 38px "JetBrains Mono", monospace';
  ctx.fillText(`${Math.round(clampedVal)}%`, cx, cy - 10);

  ctx.fillStyle = '#8892a4';
  ctx.font = '11px Inter';
  ctx.fillText('COOLING POWER', cx, cy + 12);

  // Min / max labels
  ctx.fillStyle = 'rgba(255,255,255,0.3)';
  ctx.font = '10px Inter';
  ctx.textAlign = 'left';
  ctx.fillText('0%', cx - R - 8, cy + 6);
  ctx.textAlign = 'right';
  ctx.fillText('100%', cx + R + 8, cy + 6);
}

function updateGauge(power, level) {
  drawGauge(power, level);
}

// ─── Aggregated Output Chart ──────────────────────────────────────────────
function initAggregatedChart() {
  const ctx = $('aggregatedChart').getContext('2d');
  aggregatedChart = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [
        {
          label: 'Aggregated μ(u)',
          data: [],
          borderColor: '#00d4ff',
          backgroundColor: 'rgba(0,212,255,0.12)',
          fill: true,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
        },
      ],
    },
    options: {
      animation: { duration: 400 },
      scales: {
        x: {
          type: 'linear',
          min: 0, max: 100,
          title: { display: true, text: 'Cooling Power (%)' },
          grid: { color: 'rgba(255,255,255,0.05)' },
        },
        y: {
          min: 0, max: 1.05,
          title: { display: true, text: 'Membership μ' },
          grid: { color: 'rgba(255,255,255,0.05)' },
        },
      },
      plugins: {
        legend: { display: false },
        annotation: {
          annotations: {},
        },
      },
    },
  });
}

function updateAggregatedChart(result) {
  if (!aggregatedChart) return;
  const xs = result.aggregated_output.x;
  const ys = result.aggregated_output.y;
  aggregatedChart.data.datasets[0].data = xs.map((x, i) => ({ x, y: ys[i] }));

  // Centroid line
  aggregatedChart.options.plugins.annotation.annotations = {
    centroid: {
      type: 'line',
      xMin: result.raw_cooling_power,
      xMax: result.raw_cooling_power,
      borderColor: '#f59e0b',
      borderWidth: 2,
      borderDash: [5, 3],
      label: {
        display: true,
        content: `Centroid: ${result.raw_cooling_power.toFixed(1)}%`,
        position: 'start',
        backgroundColor: 'rgba(245,158,11,0.15)',
        color: '#f59e0b',
        font: { size: 10, family: "'JetBrains Mono', monospace" },
      },
    },
    finalLine: {
      type: 'line',
      xMin: result.cooling_power,
      xMax: result.cooling_power,
      borderColor: '#10b981',
      borderWidth: 2,
      borderDash: [3, 3],
      label: {
        display: true,
        content: `Final: ${result.cooling_power.toFixed(1)}%`,
        position: 'end',
        backgroundColor: 'rgba(16,185,129,0.15)',
        color: '#10b981',
        font: { size: 10, family: "'JetBrains Mono', monospace" },
      },
    },
  };

  aggregatedChart.update();
}

// ─── Simulation ───────────────────────────────────────────────────────────
function initSimCharts() {
  const chartOpts = (titleY, label, color) => ({
    type: 'line',
    data: { datasets: [] },
    options: {
      animation: false,
      scales: {
        x: {
          type: 'linear',
          title: { display: true, text: 'Time Step' },
          grid: { color: 'rgba(255,255,255,0.05)' },
        },
        y: {
          title: { display: true, text: titleY },
          grid: { color: 'rgba(255,255,255,0.05)' },
        },
      },
      plugins: {
        legend: { position: 'top', labels: { boxWidth: 10 } },
        annotation: { annotations: {} },
      },
      elements: { point: { radius: 0 } },
    },
  });

  simTempChart    = new Chart($('simTempChart').getContext('2d'),    chartOpts('Temperature (°C)', 'Temp', '#00d4ff'));
  simCoolingChart = new Chart($('simCoolingChart').getContext('2d'), chartOpts('Cooling Power (%)', 'Cooling', '#8b5cf6'));
  compTempChart    = new Chart($('compTempChart').getContext('2d'),    chartOpts('Temperature (°C)', 'Temp', '#00d4ff'));
  compCoolingChart = new Chart($('compCoolingChart').getContext('2d'), chartOpts('Cooling Power (%)', 'Cooling', '#8b5cf6'));
}

function recordsToXY(records, key) {
  return records.map(r => ({ x: r.step, y: r[key] }));
}

function updateSimCharts(records, distStep) {
  const steps   = records.map(r => r.step);
  const target  = records[0].target_temperature;

  // Temperature chart
  simTempChart.data.datasets = [
    {
      label: 'Actual Temp',
      data: recordsToXY(records, 'temperature'),
      borderColor: '#00d4ff',
      backgroundColor: 'transparent',
      borderWidth: 2,
      tension: 0.3,
    },
    {
      label: 'Target Temp',
      data: records.map(r => ({ x: r.step, y: r.target_temperature })),
      borderColor: '#10b981',
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      borderDash: [6, 3],
      tension: 0,
    },
  ];

  simTempChart.options.plugins.annotation.annotations = {
    distLine: {
      type: 'line',
      xMin: distStep, xMax: distStep,
      borderColor: '#ef4444',
      borderWidth: 1.5,
      borderDash: [4, 4],
      label: {
        display: true,
        content: '🔥 Disturbance',
        position: 'start',
        backgroundColor: 'rgba(239,68,68,0.15)',
        color: '#ef4444',
        font: { size: 10 },
      },
    },
  };

  simTempChart.update();

  // Cooling chart
  simCoolingChart.data.datasets = [
    {
      label: 'Cooling Power',
      data: recordsToXY(records, 'cooling_power'),
      borderColor: '#8b5cf6',
      backgroundColor: 'rgba(139,92,246,0.1)',
      fill: true,
      borderWidth: 2,
      tension: 0.3,
    },
  ];

  simCoolingChart.options.plugins.annotation.annotations = {
    distLine: {
      type: 'line',
      xMin: distStep, xMax: distStep,
      borderColor: '#ef4444',
      borderWidth: 1.5,
      borderDash: [4, 4],
    },
  };

  simCoolingChart.update();
}

async function runSimulation() {
  const btn = $('simBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Simulating…';

  try {
    const body = {
      initial_temperature:   parseFloat($('simInitTemp').value),
      target_temperature:    parseFloat($('simTargetTemp').value),
      humidity:              parseFloat($('simHumidity').value),
      n_steps:               100,
      enable_noise:          $('simNoise').checked,
      disturbance_at_step:   parseInt($('simDistStep').value),
      disturbance_magnitude: parseFloat($('simDistMag').value),
      controller_type:       'fuzzy',
      noise_filter:          $('simFilter').value,
    };

    const res = await apiPost('/simulate', body);
    lastSimResult = res;
    updateSimCharts(res.records, body.disturbance_at_step);
    showToast('✅ Simulation complete');
  } catch (err) {
    showToast(`❌ Simulation failed: ${err.message}`, 5000);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '▶ Run Simulation';
  }
}

// ─── Comparison ───────────────────────────────────────────────────────────
async function runComparison() {
  const btn = $('compareBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Running…';

  try {
    const body = {
      initial_temperature:   parseFloat($('simInitTemp').value),
      target_temperature:    parseFloat($('simTargetTemp').value),
      humidity:              parseFloat($('simHumidity').value),
      n_steps:               100,
      disturbance_at_step:   parseInt($('simDistStep').value),
      disturbance_magnitude: parseFloat($('simDistMag').value),
    };

    const res = await apiPost('/compare', body);

    const distStep = body.disturbance_at_step;

    // Temperature chart (both controllers)
    compTempChart.data.datasets = [
      {
        label: '🔵 Fuzzy Controller',
        data: recordsToXY(res.fuzzy.records, 'temperature'),
        borderColor: '#00d4ff',
        backgroundColor: 'transparent',
        borderWidth: 2,
        tension: 0.3,
      },
      {
        label: '🟣 Threshold Controller',
        data: recordsToXY(res.threshold.records, 'temperature'),
        borderColor: '#c4b5fd',
        backgroundColor: 'transparent',
        borderWidth: 2,
        tension: 0.3,
      },
      {
        label: 'Target',
        data: res.fuzzy.records.map(r => ({ x: r.step, y: r.target_temperature })),
        borderColor: '#10b981',
        borderWidth: 1.5,
        borderDash: [5, 3],
        tension: 0,
      },
    ];

    compTempChart.options.plugins.annotation.annotations = {
      distLine: {
        type: 'line',
        xMin: distStep, xMax: distStep,
        borderColor: '#ef4444',
        borderWidth: 1.5,
        borderDash: [4, 4],
        label: { display: true, content: '🔥 Dist.', position: 'start', backgroundColor: 'rgba(239,68,68,0.15)', color: '#ef4444', font: { size: 10 } },
      },
    };
    compTempChart.update();

    // Cooling chart
    compCoolingChart.data.datasets = [
      {
        label: '🔵 Fuzzy',
        data: recordsToXY(res.fuzzy.records, 'cooling_power'),
        borderColor: '#00d4ff',
        backgroundColor: 'rgba(0,212,255,0.07)',
        fill: true,
        borderWidth: 2,
        tension: 0.3,
      },
      {
        label: '🟣 Threshold',
        data: recordsToXY(res.threshold.records, 'cooling_power'),
        borderColor: '#c4b5fd',
        backgroundColor: 'rgba(196,181,253,0.07)',
        fill: true,
        borderWidth: 2,
        tension: 0.1,
      },
    ];
    compCoolingChart.options.plugins.annotation.annotations = {
      distLine: { type: 'line', xMin: distStep, xMax: distStep, borderColor: '#ef4444', borderWidth: 1.5, borderDash: [4, 4] },
    };
    compCoolingChart.update();

    // Metrics table + experiment results
    updateMetricsTable(res.fuzzy.metrics, res.threshold.metrics);
    updateExperimentResults(res.fuzzy.metrics, res.threshold.metrics, body);
    showToast('✅ Comparison complete');
  } catch (err) {
    showToast(`❌ Comparison failed: ${err.message}`, 5000);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '▶ Run Comparison';
  }
}

function updateMetricsTable(fuzzy, threshold) {
  const tbody = $('metricsBody');
  const rows = [
    { label: 'Settling Time (steps)',  fKey: 'settling_time_steps',  tKey: 'settling_time_steps',  lowerIsBetter: true  },
    { label: 'Overshoot (°C)',          fKey: 'overshoot_deg',         tKey: 'overshoot_deg',         lowerIsBetter: true  },
    { label: 'Steady-State Error (°C)', fKey: 'steady_state_error',    tKey: 'steady_state_error',    lowerIsBetter: true  },
    { label: 'Integral Abs. Error',     fKey: 'integral_abs_error',    tKey: 'integral_abs_error',    lowerIsBetter: true  },
    { label: 'Mean Squared Error',      fKey: 'mean_squared_error',    tKey: 'mean_squared_error',    lowerIsBetter: true  },
    { label: 'Mean Control Effort (%)', fKey: 'mean_control_effort',   tKey: 'mean_control_effort',   lowerIsBetter: false },
    { label: 'Control Variation (std)', fKey: 'control_variation',     tKey: 'control_variation',     lowerIsBetter: true  },
    { label: 'Temp Std Dev (last 20s)', fKey: 'temperature_std',       tKey: 'temperature_std',       lowerIsBetter: true  },
  ];

  tbody.innerHTML = rows.map(r => {
    const fv = fuzzy[r.fKey];
    const tv = threshold[r.tKey];
    const fBetter = r.lowerIsBetter ? fv <= tv : fv >= tv;
    const fc = fBetter ? 'better' : 'worse';
    const tc = !fBetter ? 'better' : 'worse';
    return `
      <tr>
        <td>${r.label}</td>
        <td class="${fc}">${typeof fv === 'number' ? fv.toFixed(3) : fv}</td>
        <td class="${tc}">${typeof tv === 'number' ? tv.toFixed(3) : tv}</td>
      </tr>`;
  }).join('');
}

// ─── Experiment Results Summary ─────────────────────────────────────────
function updateExperimentResults(fuzzy, threshold, params) {
  const box = $('experimentResultsBox');
  if (!box) return;
  box.style.display = 'block';

  const METRICS = [
    { label: 'Settling Time',    fk: 'settling_time_steps',  unit: ' steps', li: true },
    { label: 'Overshoot',        fk: 'overshoot_deg',         unit: ' °C',    li: true },
    { label: 'Steady-State Err', fk: 'steady_state_error',    unit: ' °C',    li: true },
    { label: 'Integral Abs Err', fk: 'integral_abs_error',    unit: '',       li: true },
    { label: 'Control Variation',fk: 'control_variation',     unit: '',       li: true },
    { label: 'Temp Stability',   fk: 'temperature_std',       unit: ' °C',    li: true },
  ];

  $('expSummaryGrid').innerHTML = METRICS.map(m => {
    const fv = fuzzy[m.fk];
    const tv = threshold[m.fk];
    const fBetter = m.li ? fv <= tv : fv >= tv;
    return `
      <div class="exp-metric">
        <div class="exp-metric-label">${m.label}</div>
        <div class="exp-metric-vals">
          <span class="exp-val-fuzzy" title="Fuzzy">${typeof fv==='number'?fv.toFixed(2):fv}${m.unit}</span>
          <span class="exp-val-thresh" title="Threshold">vs ${typeof tv==='number'?tv.toFixed(2):tv}${m.unit}</span>
          <span style="font-size:14px;">${fBetter ? '✅' : '🔶'}</span>
        </div>
      </div>`;
  }).join('');

  // Generate a plain-language verdict from real data
  const fStl = fuzzy.settling_time_steps;
  const tStl = threshold.settling_time_steps;
  const fVar = fuzzy.control_variation;
  const tVar = threshold.control_variation;
  const fSSE = fuzzy.steady_state_error;
  const tSSE = threshold.steady_state_error;
  const scenario = `Initial ${params.initial_temperature}°C → Target ${params.target_temperature}°C, Humidity ${params.humidity}%`;

  const parts = [];
  if (fStl < tStl) parts.push(`settled ${tStl - fStl} steps faster`);
  else if (tStl < fStl) parts.push(`threshold settled ${fStl - tStl} steps faster`);
  if (fVar < tVar * 0.7) parts.push(`used ${((1 - fVar/tVar)*100).toFixed(0)}% less control variation (smoother output)`);
  if (fSSE < tSSE) parts.push(`achieved lower steady-state error (${fSSE.toFixed(2)}°C vs ${tSSE.toFixed(2)}°C)`);

  const verdict = parts.length
    ? `Scenario: ${scenario}.\nFuzzy controller ${parts.join(', ')}. The gradual proportional output avoids the on/off oscillation of the threshold controller.`
    : `Scenario: ${scenario}.\nBoth controllers performed similarly. Fuzzy advantage is most visible during disturbance recovery and high-humidity conditions.`;

  $('expVerdict').textContent = verdict;
}

// ─── Rule Matrix ─────────────────────────────────────────────────────────
let activeRuleIds = new Set();

function buildRuleMatrix(ruleData) {
  const grid     = $('ruleMatrixGrid');
  const eLabels  = ruleData.error_labels;
  const deLabels = ruleData.delta_error_labels;
  const matrix   = ruleData.matrix;
  grid.innerHTML = '';

  // Corner
  const corner = document.createElement('div');
  corner.className = 'rule-cell header-cell';
  corner.textContent = 'e \\ Δe';
  grid.appendChild(corner);

  // Header row
  for (const de of deLabels) {
    const cell = document.createElement('div');
    cell.className = 'rule-cell header-cell';
    cell.textContent = de;
    grid.appendChild(cell);
  }

  // Data rows
  for (let i = 0; i < eLabels.length; i++) {
    const eCell = document.createElement('div');
    eCell.className = 'rule-cell header-cell';
    eCell.textContent = eLabels[i];
    grid.appendChild(eCell);

    for (let j = 0; j < deLabels.length; j++) {
      const out  = matrix[i][j];
      const ruleId = i * 5 + j + 1;
      const cell = document.createElement('div');
      cell.className = `rule-cell ${out}`;
      cell.id        = `ruleCell-${ruleId}`;
      cell.textContent = out;
      cell.title    = `IF e=${eLabels[i]} AND Δe=${deLabels[j]} → ${out}`;
      grid.appendChild(cell);
    }
  }
}

function highlightRuleMatrix(activatedRules) {
  // Clear previous highlights
  activeRuleIds.forEach(id => {
    const cell = $(`ruleCell-${id}`);
    if (cell) cell.classList.remove('active');
  });
  activeRuleIds.clear();

  activatedRules.forEach(r => {
    const cell = $(`ruleCell-${r.rule_id}`);
    if (cell) {
      cell.classList.add('active');
      activeRuleIds.add(r.rule_id);
    }
  });
}

// ─── MF Charts ────────────────────────────────────────────────────────────
function initMFCharts(mfData) {
  const darkGrid = { color: 'rgba(255,255,255,0.05)' };
  const baseOpts = {
    animation: false,
    scales: {
      x: { type: 'linear', grid: darkGrid, title: { display: true, text: '' } },
      y: { min: 0, max: 1.05, grid: darkGrid, title: { display: true, text: 'μ' } },
    },
    plugins: {
      legend: { position: 'top', labels: { boxWidth: 10, font: { size: 10 } } },
      annotation: { annotations: {} },
    },
    elements: { point: { radius: 0 } },
  };

  function buildDatasets(sets, universe, colors) {
    return Object.entries(sets).map(([label, ys], idx) => ({
      label,
      data: universe.map((x, i) => ({ x, y: ys[i] })),
      borderColor: colors[idx % colors.length],
      backgroundColor: colors[idx % colors.length].replace('0.75', '0.08'),
      fill: true,
      borderWidth: 1.5,
      tension: 0.3,
    }));
  }

  // Error MF
  const errOpts = JSON.parse(JSON.stringify(baseOpts));
  errOpts.scales.x.title.text = 'Error e (°C)';
  mfErrorChart = new Chart($('mfErrorChart').getContext('2d'), {
    type: 'line',
    data: { datasets: buildDatasets(mfData.error.sets, mfData.error.universe, E_COLORS) },
    options: errOpts,
  });

  // Delta error MF
  const deOpts = JSON.parse(JSON.stringify(baseOpts));
  deOpts.scales.x.title.text = 'Rate of Change Δe (°C/step)';
  mfDeltaChart = new Chart($('mfDeltaChart').getContext('2d'), {
    type: 'line',
    data: { datasets: buildDatasets(mfData.delta_error.sets, mfData.delta_error.universe, E_COLORS) },
    options: deOpts,
  });

  // Humidity MF
  const hOpts = JSON.parse(JSON.stringify(baseOpts));
  hOpts.scales.x.title.text = 'Humidity (%)';
  mfHumidChart = new Chart($('mfHumidChart').getContext('2d'), {
    type: 'line',
    data: { datasets: buildDatasets(mfData.humidity.sets, mfData.humidity.universe, H_COLORS) },
    options: hOpts,
  });

  // Cooling output MF
  const cOpts = JSON.parse(JSON.stringify(baseOpts));
  cOpts.scales.x.title.text = 'Cooling Power (%)';
  const coolingColors = Object.values(MF_COLORS);
  mfCoolingChart = new Chart($('mfCoolingChart').getContext('2d'), {
    type: 'line',
    data: { datasets: buildDatasets(mfData.cooling.sets, mfData.cooling.universe, coolingColors) },
    options: cOpts,
  });
}

// ─── Scenario Presets ─────────────────────────────────────────────────────
const SCENARIOS = {
  hot:         { target: 22, current: 38, humidity: 55,  label: 'Hot Room (38°C → cool to 22°C)',            simInit: 38, simTarget: 22, simHumidity: 55,  simDist: 5  },
  comfortable: { target: 24, current: 24, humidity: 50,  label: 'Comfortable (at setpoint, stable)',          simInit: 28, simTarget: 24, simHumidity: 50,  simDist: 3  },
  cold:        { target: 26, current: 18, humidity: 40,  label: 'Cold Room (18°C, minimal cooling needed)',   simInit: 18, simTarget: 26, simHumidity: 40,  simDist: 0  },
  disturbance: { target: 24, current: 28, humidity: 60,  label: 'Heat Disturbance (sudden +6°C spike)',       simInit: 28, simTarget: 24, simHumidity: 60,  simDist: 6  },
  humid:       { target: 24, current: 30, humidity: 88,  label: 'High Humidity (88% — modifier ×1.15)',       simInit: 30, simTarget: 24, simHumidity: 88,  simDist: 4  },
};

function applyScenario(name) {
  const s = SCENARIOS[name];
  if (!s) return;

  // Inference sliders
  const tgt = $('targetTemp');
  const cur = $('currentTemp');
  const hum = $('humidity');
  tgt.value = s.target;  $('targetVal').textContent  = `${s.target.toFixed(1)} °C`;
  cur.value = s.current; $('currentVal').textContent  = `${s.current.toFixed(1)} °C`;
  hum.value = s.humidity;$('humidityVal').textContent = `${s.humidity} %`;

  // Simulation inputs
  $('simInitTemp').value   = s.simInit;
  $('simTargetTemp').value = s.simTarget;
  $('simHumidity').value   = s.simHumidity;
  $('simDistMag').value    = s.simDist;

  // Reset previousError so delta is computed fresh
  previousError = 0;
  updateDerivedDisplay();

  showToast(`📋 Scenario: ${s.label}`);
}

// ─── Educational Tabs ─────────────────────────────────────────────────────
function showEduTab(name, btn) {
  qsa('.edu-panel').forEach(p => p.classList.remove('active'));
  qsa('.edu-tab').forEach(b => b.classList.remove('active'));
  $(`tab-${name}`).classList.add('active');
  btn.classList.add('active');
}

// ─── Initialisation ───────────────────────────────────────────────────────
async function init() {
  bindSliders();
  updateDerivedDisplay();
  initAggregatedChart();
  initSimCharts();

  // Initial gauge (blank)
  drawGauge(0, 'Very Low');

  // Load rules & MF data from backend
  try {
    const [ruleData, mfData] = await Promise.all([
      apiGet('/rules'),
      apiGet('/membership-functions'),
    ]);
    buildRuleMatrix(ruleData);
    initMFCharts(mfData);
    showToast('✅ Connected to backend');
  } catch (err) {
    showToast('⚠ Could not reach backend — start uvicorn', 6000);
    console.warn('Backend not reachable:', err.message);
    buildRuleMatrix(FALLBACK_RULES);
  }
}

// ─── Fallback rule matrix (used if backend is unreachable) ────────────────
const FALLBACK_RULES = {
  error_labels:       ['NB', 'NS', 'ZE', 'PS', 'PB'],
  delta_error_labels: ['NB', 'NS', 'ZE', 'PS', 'PB'],
  matrix: [
    ['VH','VH','VH','H', 'H' ],
    ['VH','H', 'H', 'M', 'L' ],
    ['H', 'M', 'M', 'L', 'VL'],
    ['M', 'L', 'L', 'VL','VL'],
    ['L', 'VL','VL','VL','VL'],
  ],
};

// ─── Bootstrap ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
