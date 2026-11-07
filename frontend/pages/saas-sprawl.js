// ============================================================
// SAAS SPRAWL PAGE — Ghost seats, zombie subscriptions, renewals
// ============================================================

import { renderMetrics } from '../components/metrics.js';
import { renderTable, badge, formatCurrency } from '../components/tables.js';
import { createBarChart, createDoughnutChart } from '../components/charts.js';
import { fetchSubscriptions, fetchSeatUsage } from '../lib/api.js';
import { renderAlert, bindAlertActions } from '../components/alerts.js';

export function renderSaaSSprawl() {
  const metricsHTML = renderMetrics([
    { id: 'totalSaaSSpend',       label: 'Total SaaS Spend',       value: '—', sub: 'Per month',       color: 'blue'   },
    { id: 'saasGhostSeats',       label: 'Ghost Seats',             value: '—', sub: 'Across all tools',color: 'purple' },
    { id: 'upcomingRenewals',     label: 'Upcoming Renewals',       value: '—', sub: 'Next 14 days',    color: 'orange' },
    { id: 'zombieSubscriptions',  label: 'Zombie Subscriptions',    value: '—', sub: 'Near-zero usage', color: 'red'    },
  ]);

  const alertHTML = renderAlert({
    type: 'info',
    title: 'Checking what needs you…',
    desc: '',
    action: 'Show pending',
    command: 'show pending',
  });

  return `
    <div class="page" id="page-saas-sprawl">
      ${alertHTML}
      ${metricsHTML}

      <div class="charts-grid">
        <div class="chart-card" style="grid-column: 1 / -1;">
          <div class="chart-header">
            <div class="chart-title purple">SEAT UTILIZATION BY TOOL</div>
          </div>
          <div class="chart-body">
            <canvas id="chart-seat-utilization"></canvas>
          </div>
        </div>
      </div>

      <div id="saas-table"></div>

      <div class="charts-grid" id="saas-bottom-grid">
        <div class="timeline-card" id="saas-timeline">
          <div class="chart-header">
            <div class="chart-title orange">UPCOMING RENEWALS</div>
          </div>
        </div>
        <div class="chart-card">
          <div class="chart-header">
            <div class="chart-title blue">SPEND BY PLAN TIER</div>
          </div>
          <div class="chart-body donut">
            <canvas id="chart-saas-category"></canvas>
          </div>
        </div>
      </div>
    </div>
  `;
}

export function initSaaSSprawlCharts() {
  bindAlertActions();
  Promise.all([fetchSubscriptions(), fetchSeatUsage()]).then(([subs, seats]) => {
    if (!subs.length) return;

    // ── Build seat counts per tool from seat_usage rows ───────
    const seatCounts = {};
    seats.forEach(s => {
      if (!seatCounts[s.tool]) seatCounts[s.tool] = { paid: 0, active: 0 };
      seatCounts[s.tool].paid++;
      if (!s.is_dormant) seatCounts[s.tool].active++;
    });

    // ── Merge subscriptions with seat counts ──────────────────
    const rows = subs.map(s => {
      const counts   = seatCounts[s.vendor] || null;
      const seatsPaid   = counts ? counts.paid   : null;
      const seatsActive = counts ? counts.active : null;
      const utilization = counts && counts.paid > 0
        ? Math.round((counts.active / counts.paid) * 100) : null;
      const status = utilization === null ? 'healthy'
        : utilization < 50 ? 'critical'
        : utilization < 80 ? 'warning' : 'healthy';
      return { vendor: s.vendor, category: s.plan_tier || '—', seatsPaid, seatsActive,
               utilization, monthlyCost: s.monthly_cost, renewal: s.renewal_date, status };
    });

    // ── Patch metric cards ────────────────────────────────────
    const today    = new Date();
    const in14Days = new Date(today.getTime() + 14 * 86400000);
    const totalSaaSSpend      = subs.reduce((s, r) => s + (r.monthly_cost || 0), 0);
    const ghostSeats          = seats.filter(s => s.is_dormant).length;
    const upcomingRenewals    = subs.filter(s => s.renewal_date && new Date(s.renewal_date) >= today && new Date(s.renewal_date) <= in14Days).length;
    const zombieSubscriptions = rows.filter(r => r.seatsActive === 0 && r.seatsPaid > 0).length;

    const patch = (id, val) => {
      const el = document.querySelector(`[data-metric-value="${id}"]`);
      if (el) el.textContent = val;
    };
    patch('totalSaaSSpend',      `$${Math.round(totalSaaSSpend).toLocaleString()}`);
    patch('saasGhostSeats',      ghostSeats.toString());
    patch('upcomingRenewals',    upcomingRenewals.toString());
    patch('zombieSubscriptions', zombieSubscriptions.toString());

    // ── Subscription table ────────────────────────────────────
    const tableEl = document.getElementById('saas-table');
    if (tableEl) {
      tableEl.innerHTML = renderTable({
        title: 'Subscription Inventory', titleColor: 'blue', id: 'table-subscriptions',
        columns: [
          { key: 'vendor',      label: 'Vendor',        render: v => `<strong>${v}</strong>` },
          { key: 'category',    label: 'Plan',          render: v => `<span class="text-muted">${v}</span>` },
          { key: 'seatsPaid',   label: 'Seats Paid',    align: 'right', render: v => v ?? '<span class="text-muted">N/A</span>' },
          { key: 'seatsActive', label: 'Seats Active',  align: 'right', render: v => v ?? '<span class="text-muted">N/A</span>' },
          { key: 'utilization', label: 'Utilization',   align: 'right', render: v => {
            if (v === null) return '<span class="text-muted">N/A</span>';
            const c = v >= 80 ? 'healthy' : v >= 50 ? 'warning' : 'critical';
            return `<span class="badge ${c}">${v}%</span>`;
          }},
          { key: 'monthlyCost', label: 'Monthly Cost',  align: 'right', render: v => formatCurrency(v) },
          { key: 'renewal',     label: 'Renewal',       render: v => v ? new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '<span class="text-muted">—</span>' },
          { key: 'status',      label: 'Status',        render: v => badge(v) },
        ],
        rows,
      });
    }

    // ── Renewals timeline ─────────────────────────────────────
    const timelineEl = document.getElementById('saas-timeline');
    const upcoming = rows
      .filter(r => r.renewal && new Date(r.renewal) >= today)
      .sort((a, b) => new Date(a.renewal) - new Date(b.renewal))
      .slice(0, 6);
    if (timelineEl && upcoming.length) {
      timelineEl.innerHTML += upcoming.map(r => {
        const days = Math.ceil((new Date(r.renewal) - today) / (1000 * 60 * 60 * 24));
        const dot  = days <= 5 ? 'red' : days <= 10 ? 'orange' : 'green';
        const seats = r.seatsPaid ? `${r.seatsActive}/${r.seatsPaid} seats active` : 'Usage-based';
        return `
          <div class="timeline-item">
            <div class="timeline-date">${new Date(r.renewal).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</div>
            <div class="timeline-dot ${dot}"></div>
            <div class="timeline-info">
              <div class="timeline-vendor">${r.vendor}</div>
              <div class="timeline-detail">${seats} · ${days} day${days !== 1 ? 's' : ''} away</div>
            </div>
            <div class="timeline-cost">${formatCurrency(r.monthlyCost)}/mo</div>
          </div>`;
      }).join('');
    }

    // ── Seat utilization bar chart ─────────────────────────────
    const seatRows = rows.filter(r => r.seatsPaid !== null);
    if (seatRows.length) {
      createBarChart('chart-seat-utilization', seatRows.map(r => r.vendor), [
        { label: 'Seats Paid',   data: seatRows.map(r => r.seatsPaid),   color: 'rgba(168,85,247,0.5)' },
        { label: 'Seats Active', data: seatRows.map(r => r.seatsActive), color: 'rgba(34,197,94,0.7)'  },
      ]);
    }

    // ── Spend by plan tier donut ──────────────────────────────
    const tiers = {};
    subs.forEach(s => {
      const tier = s.plan_tier || 'Other';
      tiers[tier] = (tiers[tier] || 0) + (s.monthly_cost || 0);
    });
    createDoughnutChart(
      'chart-saas-category',
      Object.keys(tiers),
      Object.values(tiers),
      ['#a855f7', '#3b82f6', '#22c55e', '#f59e0b', '#06b6d4', '#ef4444']
    );
  });
}
