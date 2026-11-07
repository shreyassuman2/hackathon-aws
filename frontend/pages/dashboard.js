// ============================================================
// OVERVIEW — headline spend, what needs you, trend, mix, live activity
// ============================================================

import { renderMetrics } from '../components/metrics.js';
import { createLineChart, createDoughnutChart, seriesColors } from '../components/charts.js';
import { fetchMetrics, fetchAlerts, fetchSpendTrend, subscribeToAlerts } from '../lib/api.js';
import { renderAlert } from '../components/alerts.js';
import { countUp, cssVar, escapeHtml, money, placeIndicator, vendorKey, vendorTile } from '../lib/ui.js';

const PILLARS = {
  ai_spend: { label: 'AI spend', series: '--s1' },
  saas_sprawl: { label: 'SaaS', series: '--s2' },
  compliance: { label: 'Expenses', series: '--s3' },
};

// The headline counts up once per visit to the app, not on every tab switch.
let counted = false;

export function renderDashboard() {
  const [s1, s2, s3] = seriesColors();
  return `
    <div class="page" id="page-dashboard">
      <div class="page-header">
        <div>
          <h1>Overview</h1>
          <p>What Runway found across AI, SaaS and team expenses, and what it needs from you.</p>
        </div>
        <div class="page-stat">
          <div class="page-stat-label">Spend, last 30 days</div>
          <div class="page-stat-value" id="headline-spend">—</div>
        </div>
      </div>

      ${renderAlert({ type: 'info', title: 'Checking what needs you…', desc: '', action: 'Show pending', command: 'show pending' })}

      ${renderMetrics([
        { id: 'identifiedSavings', label: 'Savings found', value: '—', sub: 'per month, if you act', href: '#saas-sprawl' },
        { id: 'aiShare', label: 'AI spend', value: '—', sub: 'last 30 days', dot: s1, href: '#ai-spend' },
        { id: 'activeSubscriptions', label: 'Subscriptions', value: '—', sub: '—', dot: s2, href: '#saas-sprawl' },
        { id: 'complianceFlags', label: 'Waiting on you', value: '—', sub: 'decisions to make', dot: s3, href: '#compliance' },
      ])}

      <div class="charts-grid">
        <div class="chart-card">
          <div class="chart-header">
            <div>
              <div class="chart-title">Spend trend</div>
              <div class="chart-sub">Last 14 days, in 2-day buckets</div>
            </div>
            <div class="chart-tabs" role="tablist" aria-label="Series">
              <button class="chart-tab active" role="tab" aria-selected="true" data-trend="total">Total</button>
              <button class="chart-tab" role="tab" aria-selected="false" data-trend="ai">AI</button>
              <button class="chart-tab" role="tab" aria-selected="false" data-trend="saas">SaaS</button>
              <button class="chart-tab" role="tab" aria-selected="false" data-trend="expenses">Expenses</button>
              <span class="chart-tabs-ind" aria-hidden="true"></span>
            </div>
          </div>
          <div class="chart-body"><canvas id="chart-spend-trend" aria-label="Spend trend chart" role="img"></canvas></div>
        </div>

        <div class="chart-card">
          <div class="chart-header">
            <div>
              <div class="chart-title">Where it goes</div>
              <div class="chart-sub">Share of the last 14 days</div>
            </div>
          </div>
          <div class="chart-body donut">
            <div class="donut-canvas"><canvas id="chart-spend-category" aria-label="Spend by category" role="img"></canvas></div>
            <ul class="legend" id="legend-spend-category"></ul>
          </div>
        </div>
      </div>

      <div class="activity-card">
        <div class="activity-header">
          <div>
            <div class="chart-title">Activity</div>
            <div class="chart-sub">Everything Runway noticed, newest first</div>
          </div>
        </div>
        <div id="activity-feed"><div class="feed-empty">Loading activity…</div></div>
      </div>
    </div>
  `;
}

function timeAgo(iso) {
  const m = Math.max(0, Math.floor((Date.now() - new Date(iso)) / 60000));
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function feedItem(a, isNew = false) {
  const p = PILLARS[a.pillar] || { label: 'Unsorted', series: '--muted' };
  const needs = a.requires_action && !a.resolved;
  return `
    <div class="activity-item${isNew ? ' is-new' : ''}">
      ${vendorKey(`${a.metadata?.vendor || ''} ${a.message || ''}`)
        ? vendorTile(a.metadata?.vendor || '', { text: `${a.metadata?.vendor || ''} ${a.message || ''}` })
        : `<span class="vendor-tile mark" style="--pc:${cssVar(p.series)}" aria-hidden="true"></span>`}
      <div class="activity-content">
        <div class="activity-text">${escapeHtml(a.message)}</div>
        <div class="activity-time">
          <span>${timeAgo(a.created_at)}</span>
          <span class="activity-pillar" style="--pc:${cssVar(p.series)}">${p.label}</span>
        </div>
      </div>
      ${needs ? '<span class="tag">Needs you</span>' : '<span></span>'}
    </div>`;
}

export function initDashboardCharts() {
  const [s1, s2, s3] = seriesColors();
  const ink = cssVar('--ink');

  // ── Headline + metric cards ──
  fetchMetrics().then((m) => {
    const set = (id, v) => { const el = document.querySelector(`[data-metric-value="${id}"]`); if (el) el.textContent = v; };
    const sub = (id, v) => { const el = document.querySelector(`[data-metric-sub="${id}"]`); if (el) el.textContent = v; };
    const head = document.getElementById('headline-spend');
    const total = m.totalMonthlySpend ?? m.spend_total ?? 0;
    if (head) {
      if (counted) head.textContent = money(total);
      else { countUp(head, total); counted = true; }
    }
    set('identifiedSavings', money(m.identifiedSavings));
    set('aiShare', money(m.spend_by_pillar?.ai_spend ?? 0));
    set('activeSubscriptions', String(m.activeSubscriptions ?? '—'));
    sub('activeSubscriptions', `${m.ghostSeats ?? 0} seats nobody uses`);
    set('complianceFlags', String(m.complianceFlags ?? m.pending_alerts ?? 0));
  });

  // ── Activity feed, then live: new alerts enter at the top ──
  const feed = document.getElementById('activity-feed');
  fetchAlerts(30).then((alerts) => {
    if (!feed) return;
    feed.innerHTML = alerts.length ? alerts.map((a) => feedItem(a)).join('') : '<div class="feed-empty">Nothing yet. Runway posts here as charges come in.</div>';
    const stop = subscribeToAlerts((a) => {
      const f = document.getElementById('activity-feed');
      if (!f) return;
      f.querySelector('.feed-empty')?.remove();
      f.insertAdjacentHTML('afterbegin', feedItem(a, true));
    });
    window.runwayCleanup?.push(stop);
  });

  // ── Trend + mix ──
  fetchSpendTrend().then((trend) => {
    const series = {
      total: { label: 'Total', color: ink },
      ai: { label: 'AI spend', color: s1 },
      saas: { label: 'SaaS', color: s2 },
      expenses: { label: 'Expenses', color: s3 },
    };
    const draw = (key) => createLineChart('chart-spend-trend', trend.labels, [{ ...series[key], data: trend.datasets[key] }], { dollarFormat: true });
    draw('total');

    const sum = (arr) => arr.reduce((a, b) => a + b, 0);
    createDoughnutChart('chart-spend-category', ['AI spend', 'SaaS', 'Expenses'],
      [sum(trend.datasets.ai), sum(trend.datasets.saas), sum(trend.datasets.expenses)],
      [s1, s2, s3], { legendId: 'legend-spend-category' });

    // Segmented control: one indicator slides to the clicked tab (click only, never timed).
    const tabs = document.querySelectorAll('[data-trend]');
    const ind = document.querySelector('.chart-tabs-ind');
    const place = () => placeIndicator(ind, document.querySelector('[data-trend].active'));
    place();
    document.fonts?.ready.then(place);
    tabs.forEach((tab) => tab.addEventListener('click', () => {
      tabs.forEach((t) => { t.classList.toggle('active', t === tab); t.setAttribute('aria-selected', String(t === tab)); });
      place();
      draw(tab.dataset.trend);
    }));
  });
}
