// ============================================================
// DASHBOARD PAGE — Main Overview
// ============================================================

import { renderMetrics } from '../components/metrics.js';
import { createLineChart, createDoughnutChart } from '../components/charts.js';
import { metrics, spendTrend, activities } from '../data.js';
import { fetchMetrics, fetchAlerts, fetchSpendTrend } from '../lib/api.js';
import { renderAlert, bindAlertActions } from '../components/alerts.js';

export function renderDashboard() {
  const alertHTML = renderAlert({
    type: 'info',
    title: 'Checking what needs you…',
    desc: '',
    action: 'Show pending',
    command: 'show pending',
  });

  const metricsHTML = renderMetrics([
    {
      id: 'totalMonthlySpend',
      label: 'TOTAL MONTHLY SPEND',
      value: `$${metrics.totalMonthlySpend.toLocaleString()}`,
      sub: 'Across all SaaS + AI',
      color: 'white',
      dotColor: 'red',
      tag: 'TOT',
      change: '12%',
      changeDir: 'up',
    },
    {
      id: 'identifiedSavings',
      label: 'IDENTIFIED SAVINGS',
      value: `$${metrics.identifiedSavings.toLocaleString()}`,
      sub: 'Per month recoverable',
      color: 'yellow',
      dotColor: 'green',
      tag: 'IDS',
      change: '$2,840 NEW',
      changeDir: 'down',
    },
    {
      id: 'activeSubscriptions',
      label: 'ACTIVE SUBSCRIPTIONS',
      value: metrics.activeSubscriptions.toString(),
      sub: `${metrics.ghostSeats} ghost seats detected`,
      color: 'white',
      valueColor: 'blue',
      dotColor: 'blue',
      tag: 'ACT',
    },
    {
      id: 'complianceFlags',
      label: 'COMPLIANCE FLAGS',
      value: metrics.complianceFlags.toString(),
      sub: `${metrics.pendingReview} pending review`,
      color: 'white',
      valueColor: 'red',
      dotColor: 'yellow',
      tag: 'CMP',
    },
  ]);

  const activityHTML = activities.map(a => `
    <div class="activity-item">
      <div class="activity-icon ${a.color}">${a.icon}</div>
      <div class="activity-content">
        <div class="activity-text">${a.text}</div>
        <div class="activity-time">${a.time}</div>
      </div>
      <div class="activity-amount ${a.amount.startsWith('+') ? 'savings' : a.amount.startsWith('-') ? 'cost' : ''}">${a.amount}</div>
    </div>
  `).join('');

  return `
    <div class="page" id="page-dashboard">
      <div class="dashboard-header-block">
        <div class="dashboard-title-box">
          <h1>Command console</h1>
          <p>the fiscal pulse of your company, in real time</p>
        </div>
        <div class="dashboard-time-box">
          <div class="sync-block" id="sync-time">SYNC --:--<br>---</div>
          <div class="time-block" id="current-time">--:--:--</div>
        </div>
      </div>

      ${alertHTML}
      ${metricsHTML}

      <div class="charts-grid">
        <div class="chart-card chart-card-trend">
          <div class="chart-header">
            <div class="chart-title blue">SPEND TREND - 30 DAYS</div>
            <div class="chart-tabs">
              <button class="chart-tab active" data-trend="total">Total</button>
              <button class="chart-tab" data-trend="ai">AI</button>
              <button class="chart-tab" data-trend="saas">SaaS</button>
            </div>
          </div>
          <div class="chart-body">
            <canvas id="chart-spend-trend"></canvas>
          </div>
          <div class="chart-fig-label">FIG. 01</div>
        </div>

        <div class="chart-card chart-card-donut">
          <div class="chart-header">
            <div class="chart-title red">SPEND BY CATEGORY</div>
          </div>
          <div class="chart-body donut">
            <canvas id="chart-spend-category"></canvas>
          </div>
          <div class="chart-fig-label">FIG. 02</div>
        </div>
      </div>

      <div class="activity-card">
        <div class="activity-header">
          <div class="chart-title yellow" style="color: black;">RECENT ACTIVITY</div>
        </div>
        <div id="activity-feed">${activityHTML}</div>
      </div>
    </div>
  `;
}

export function initDashboardCharts() {
  const colorMap = { total: 'rgb(34, 197, 94)', ai: 'rgb(168, 85, 247)', saas: 'rgb(59, 130, 246)' };
  const labelMap = { total: 'Total Spend', ai: 'AI Spend', saas: 'SaaS Spend' };
  const bgMap    = { total: '#EBE1FB', ai: '#FEF08A', saas: '#BFDBFE' };

  // ── Step 1: Live metric cards ──────────────────────────────
  fetchMetrics().then(data => {
    const patch = (attr, val) => {
      const el = document.querySelector(`[${attr}]`);
      if (el) el.textContent = val;
    };
    patch('data-metric-value="totalMonthlySpend"', `$${data.totalMonthlySpend.toLocaleString()}`);
    patch('data-metric-value="identifiedSavings"',  `$${data.identifiedSavings.toLocaleString()}`);
    patch('data-metric-value="activeSubscriptions"', data.activeSubscriptions.toString());
    patch('data-metric-value="complianceFlags"',     data.complianceFlags.toString());
    patch('data-metric-sub="activeSubscriptions"',  `${data.ghostSeats} ghost seats detected`);
  });

  // ── Step 2: Live activity feed + alert banner ─────────────
  bindAlertActions(); // Binds click handlers to the top banner

  fetchAlerts().then(alerts => {
const feed = document.getElementById('activity-feed');
    if (!feed || !alerts.length) return;
    const pillarMeta = {
      ai_spend:    { color: 'purple', label: 'AI SPEND' },
      saas_sprawl: { color: 'blue',   label: 'SAAS' },
      compliance:  { color: 'orange', label: 'COMPLIANCE' },
    };
    const timeAgo = iso => {
      const m = Math.floor((Date.now() - new Date(iso)) / 60000);
      if (m < 60) return `${m}m ago`;
      const h = Math.floor(m / 60);
      if (h < 24) return `${h}h ago`;
      return `${Math.floor(h / 24)}d ago`;
    };
    feed.innerHTML = alerts.map((a, index) => {
      const meta = pillarMeta[a.pillar] || { color: 'red', label: 'ALERT' };
      const bauhausClasses = ['purple', 'blue', 'orange'];
      const iconClass = bauhausClasses[index % bauhausClasses.length];
      
      const badge = a.requires_action
        ? `<span class="activity-badge" style="color:var(--orange);">ACTION NEEDED</span>` : '';
      return `
        <div class="activity-item">
          <div class="activity-icon ${iconClass}"></div>
          <div class="activity-content">
            <div class="activity-text">${a.message}</div>
            <div class="activity-time">${timeAgo(a.created_at)} · ${meta.label} ${badge}</div>
          </div>
        </div>`;
    }).join('');
  });

  // ── Steps 3 & 4: Live spend trend chart + donut ───────────
  fetchSpendTrend().then(trend => {
    // Step 3: trend line
    createLineChart('chart-spend-trend', trend.labels, [
      { label: 'Total Spend', data: trend.datasets.total, color: colorMap.total, backgroundColor: bgMap.total },
    ], { dollarFormat: true });

    // Step 4: donut — sum each pillar dataset
    const sum = arr => arr.reduce((a, b) => a + b, 0);
    createDoughnutChart(
      'chart-spend-category',
      ['AI APIs', 'SaaS Tools', 'Expenses'],
      [sum(trend.datasets.ai), sum(trend.datasets.saas), sum(trend.datasets.expenses)],
      ['#a855f7', '#3b82f6', '#f59e0b']
    );

    // Step 3: tab switching also uses live data
    const trendTabs = document.querySelectorAll('[data-trend]');
    trendTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        trendTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const key = tab.dataset.trend;
        createLineChart('chart-spend-trend', trend.labels, [
          { label: labelMap[key], data: trend.datasets[key], color: colorMap[key], backgroundColor: bgMap[key] },
        ], { dollarFormat: true });
      });
    });
  });
  // Initialize live clock
  const updateClock = () => {
    const now = new Date();
    
    // Timezone 3-letter code (crude but works for demo)
    const tz = now.toLocaleTimeString('en-us', {timeZoneName:'short'}).split(' ').pop();
    
    const syncEl = document.getElementById('sync-time');
    const timeEl = document.getElementById('current-time');
    
    if (syncEl) {
      const hours = now.getHours().toString().padStart(2, '0');
      const minutes = now.getMinutes().toString().padStart(2, '0');
      syncEl.innerHTML = `SYNC ${hours}:${minutes}<br>${tz}`;
    }
    
    if (timeEl) {
      timeEl.innerText = now.toLocaleTimeString('en-US', { 
        hour12: false, 
        hour: '2-digit', 
        minute: '2-digit', 
        second: '2-digit' 
      });
    }
  };

  updateClock();
  const clockInterval = setInterval(updateClock, 1000);

  // Store interval on the window or a global to clear it if needed
  window.dashboardClock = clockInterval;
}
