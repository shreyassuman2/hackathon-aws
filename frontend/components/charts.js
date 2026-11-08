// ============================================================
// CHARTS — Chart.js with the dataviz skill's rules:
// validated series colours (read from CSS, so they follow the grade),
// 2px lines, rounded bar ends on the baseline, 2px surface gaps,
// recessive grid, crosshair tooltip, a legend with values, one draw-in.
// ============================================================

import { Chart, registerables } from 'chart.js';
import { cssVar, escapeHtml, reducedMotion, rgba } from '../lib/ui.js';
import { whenSeen } from '../lib/scroll.js';

Chart.register(...registerables);

const charts = {};
// Each canvas draws in once (600–1200ms, settled by 1.5s); later updates swap without the entrance.
const drawn = new Set();

export function seriesColors() {
  return [cssVar('--s1'), cssVar('--s2'), cssVar('--s3')];
}

function theme() {
  const ink = cssVar('--ink');
  return {
    ink, muted: cssVar('--muted'), line: rgba(ink, 0.13), lineStrong: rgba(ink, 0.3),
    card: cssVar('--card'), mono: cssVar('--font-mono') || 'monospace', text: cssVar('--font-text') || 'sans-serif',
  };
}

function base(id) {
  const t = theme();
  const first = !drawn.has(id) && !reducedMotion();
  drawn.add(id);
  return {
    t,
    common: {
      responsive: true,
      maintainAspectRatio: false,
      animation: first ? { duration: 900, easing: 'easeOutQuart' } : { duration: reducedMotion() ? 0 : 400, easing: 'easeOutQuart' },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: t.card, titleColor: t.ink, bodyColor: t.ink,
          borderColor: t.line, borderWidth: 1, padding: 12, cornerRadius: 6,
          titleFont: { family: t.text, size: 13, weight: '500' },
          bodyFont: { family: t.mono, size: 12 },
          boxWidth: 8, boxHeight: 8, boxPadding: 6, usePointStyle: true,
        },
      },
    },
  };
}

function axes(t, { dollars = false, stacked = false } = {}) {
  const tick = { color: t.muted, font: { family: t.mono, size: 11 } };
  return {
    x: { stacked, grid: { display: false }, border: { color: t.line }, ticks: { ...tick, maxRotation: 0, autoSkipPadding: 16 } },
    y: {
      stacked, beginAtZero: true,
      grid: { color: t.line, drawTicks: false }, border: { display: false },
      ticks: { ...tick, padding: 8, maxTicksLimit: 5, callback: (v) => (dollars ? `$${Number(v).toLocaleString()}` : v) },
    },
  };
}

function mount(id, config) {
  requestAnimationFrame(() => {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    // A chart below the fold waits until it's scrolled into view, so its draw-in is seen.
    whenSeen(canvas.closest('.chart-card') || canvas, () => {
      if (!canvas.isConnected) return;
      charts[id]?.destroy();
      charts[id] = new Chart(canvas.getContext('2d'), config);
    });
  });
}

/** Line chart. datasets: { label, data, color } */
export function createLineChart(id, labels, datasets, options = {}) {
  const { t, common } = base(id);
  const area = options.fill !== false && datasets.length === 1;
  mount(id, {
    type: 'line',
    data: {
      labels,
      datasets: datasets.map((d) => ({
        label: d.label, data: d.data,
        borderColor: d.color, borderWidth: 2, tension: 0.3,
        pointRadius: 0, pointHoverRadius: 5, pointHitRadius: 16,
        pointHoverBackgroundColor: d.color, pointHoverBorderColor: t.card, pointHoverBorderWidth: 2,
        fill: area,
        backgroundColor: (ctx) => {
          if (!area || !ctx.chart.chartArea) return 'transparent';
          const { top, bottom } = ctx.chart.chartArea;
          const g = ctx.chart.ctx.createLinearGradient(0, top, 0, bottom);
          g.addColorStop(0, rgba(d.color, 0.22));
          g.addColorStop(1, rgba(d.color, 0));
          return g;
        },
      })),
    },
    options: {
      ...common,
      interaction: { mode: 'index', intersect: false },
      scales: axes(t, { dollars: options.dollarFormat }),
      plugins: {
        ...common.plugins,
        tooltip: {
          ...common.plugins.tooltip,
          callbacks: { label: (c) => ` ${c.dataset.label}  ${options.dollarFormat ? '$' + c.parsed.y.toLocaleString() : c.parsed.y.toLocaleString()}` },
        },
      },
    },
    plugins: [crosshair],
  });
}

/** Bar chart. datasets: { label, data, color } */
export function createBarChart(id, labels, datasets, options = {}) {
  const { t, common } = base(id);
  mount(id, {
    type: 'bar',
    data: {
      labels,
      datasets: datasets.map((d) => ({
        label: d.label, data: d.data, backgroundColor: d.color, hoverBackgroundColor: d.color,
        borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: 'bottom',
        borderColor: t.card, borderWidth: { left: 1, right: 1 }, // the 2px surface gap between adjacent bars
        barPercentage: 0.8, categoryPercentage: 0.66, maxBarThickness: 28,
      })),
    },
    options: {
      ...common,
      interaction: { mode: 'index', intersect: false },
      scales: axes(t, { dollars: options.dollarFormat }),
      plugins: {
        ...common.plugins,
        tooltip: {
          ...common.plugins.tooltip,
          callbacks: { label: (c) => ` ${c.dataset.label}  ${options.dollarFormat ? '$' + c.parsed.y.toLocaleString() : c.parsed.y}` },
        },
      },
    },
  });
}

/** Doughnut chart; pass a legendId to render the legend with values beside it. */
export function createDoughnutChart(id, labels, data, colors, options = {}) {
  const { t, common } = base(id);
  const total = data.reduce((a, b) => a + b, 0) || 1;
  const fmt = options.count ? (v) => v.toLocaleString() : (v) => '$' + Math.round(v).toLocaleString();
  mount(id, {
    type: 'doughnut',
    data: { labels, datasets: [{ data, backgroundColor: colors, borderColor: t.card, borderWidth: 2, hoverOffset: 4, borderRadius: 3 }] },
    options: {
      ...common,
      cutout: '68%',
      animation: common.animation.duration > 400 ? { ...common.animation, animateRotate: true } : common.animation,
      plugins: {
        ...common.plugins,
        tooltip: { ...common.plugins.tooltip, callbacks: { label: (c) => ` ${c.label}  ${fmt(c.parsed)} · ${Math.round((c.parsed / total) * 100)}%` } },
      },
    },
  });
  const legend = options.legendId && document.getElementById(options.legendId);
  if (legend) {
    legend.innerHTML = labels.map((l, i) => `
      <li><span class="legend-swatch" style="background:${colors[i]}"></span>
        <span>${escapeHtml(l)} <span class="legend-share">${Math.round((data[i] / total) * 100)}%</span></span>
        <span class="legend-value">${fmt(data[i])}</span></li>`).join('');
  }
}

/** A legend row for line/bar charts (>= 2 series always carry one). */
export function renderLegendRow(items) {
  return `<ul class="legend row">${items.map((it) => `<li><span class="legend-swatch" style="background:${it.color}"></span><span>${escapeHtml(it.label)}</span></li>`).join('')}</ul>`;
}

// A thin vertical rule under the pointer on line charts.
const crosshair = {
  id: 'crosshair',
  afterDatasetsDraw(chart) {
    const active = chart.tooltip?.getActiveElements?.();
    if (!active?.length) return;
    const x = active[0].element.x;
    const { top, bottom } = chart.chartArea;
    const c = chart.ctx;
    c.save();
    c.strokeStyle = rgba(cssVar('--ink'), 0.3);
    c.lineWidth = 1;
    c.beginPath(); c.moveTo(x, top); c.lineTo(x, bottom); c.stroke();
    c.restore();
  },
};

export function destroyAllCharts() {
  Object.keys(charts).forEach((id) => { charts[id].destroy(); delete charts[id]; });
}
