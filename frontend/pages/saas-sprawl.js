// ============================================================
// SAAS SPRAWL PAGE — Ghost seats, zombie subscriptions, renewals
// ============================================================

import { renderMetrics } from '../components/metrics.js';
import { renderTable, badge, formatCurrency } from '../components/tables.js';
import { createBarChart, createDoughnutChart, renderLegendRow, seriesColors } from '../components/charts.js';
import { escapeHtml, vendorTile } from '../lib/ui.js';
import { fetchSubscriptions, fetchSeatUsage } from '../lib/api.js';
import { renderAlert } from '../components/alerts.js';

export function renderSaaSSprawl() {
  const metricsHTML = renderMetrics([
    { id: 'totalSaaSSpend', label: 'SaaS spend', value: '—', sub: 'per month, all contracts' },
    { id: 'saasGhostSeats', label: 'Seats nobody uses', value: '—', sub: 'across every tool' },
    { id: 'upcomingRenewals', label: 'Renewing soon', value: '—', sub: 'in the next 14 days' },
    { id: 'zombieSubscriptions', label: 'Unused subscriptions', value: '—', sub: 'paid seats, zero active' },
  ]);

  return `
    <div class="page" id="page-saas-sprawl">
      <div class="page-header">
        <div>
          <h1>SaaS</h1>
          <p>Every subscription, how much of it is used, and what renews next.</p>
        </div>
      </div>
      ${renderAlert({ type: 'info', title: 'Checking what needs you…', desc: '', action: 'Show pending', command: 'show pending' })}
      ${metricsHTML}

      <div class="charts-grid">
        <div class="chart-card wide">
          <div class="chart-header">
            <div><div class="chart-title">Seats paid and used</div><div class="chart-sub">Per tool, from usage signals</div></div>
            <div id="legend-seats"></div>
          </div>
          <div class="chart-body"><canvas id="chart-seat-utilization" role="img" aria-label="Seats paid and used per tool"></canvas></div>
        </div>
      </div>

      <div id="saas-table"></div>

      <div class="charts-grid" id="saas-bottom-grid">
        <div class="timeline-card" id="saas-timeline">
          <div class="chart-header"><div><div class="chart-title">Renewing next</div><div class="chart-sub">Act before the notice window closes</div></div></div>
        </div>
        <div class="chart-card">
          <div class="chart-header"><div><div class="chart-title">Spend by plan tier</div><div class="chart-sub">Monthly cost</div></div></div>
          <div class="chart-body donut">
            <div class="donut-canvas"><canvas id="chart-saas-category" role="img" aria-label="Spend by plan tier"></canvas></div>
            <ul class="legend" id="legend-saas-category"></ul>
          </div>
        </div>
      </div>
    </div>
  `;
}

export function initSaaSSprawlCharts() {
  const [s1, s2, s3] = seriesColors();
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
        title: 'Subscriptions', id: 'table-subscriptions',
        columns: [
          { key: 'vendor',      label: 'Tool',          render: v => `<span class="vendor">${vendorTile(v, { size: 'sm' })}${escapeHtml(v)}</span>` },
          { key: 'category',    label: 'Plan',          render: v => `<span class="text-muted">${escapeHtml(v)}</span>` },
          { key: 'seatsPaid',   label: 'Seats paid',    align: 'right', render: v => v ?? '<span class="text-muted">—</span>' },
          { key: 'seatsActive', label: 'Seats used',    align: 'right', render: v => v ?? '<span class="text-muted">—</span>' },
          { key: 'utilization', label: 'Used',          render: v => {
            if (v === null) return '<span class="text-muted">Usage-based</span>';
            return `<span class="meter"><span class="meter-track"><span class="meter-fill" style="width:${v}%"></span></span><span class="mono">${v}%</span></span>`;
          }},
          { key: 'monthlyCost', label: 'Per month',     align: 'right', render: v => formatCurrency(v) },
          { key: 'renewal',     label: 'Renews',        render: v => v ? new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '<span class="text-muted">—</span>' },
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
        const seats = r.seatsPaid ? `${r.seatsActive} of ${r.seatsPaid} seats used` : 'Usage-based';
        return `
          <div class="timeline-item">
            <div class="timeline-date">${new Date(r.renewal).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</div>
            ${vendorTile(r.vendor, { size: 'sm' })}
            <div class="timeline-info">
              <div class="timeline-vendor">${escapeHtml(r.vendor)}</div>
              <div class="timeline-detail ${days <= 7 ? 'timeline-soon' : ''}">${seats} · in ${days} day${days !== 1 ? 's' : ''}</div>
            </div>
            <div class="timeline-cost">${formatCurrency(r.monthlyCost)}/mo</div>
          </div>`;
      }).join('');
    }

    // ── Seat utilization bar chart ─────────────────────────────
    const seatRows = rows.filter(r => r.seatsPaid !== null);
    if (seatRows.length) {
      createBarChart('chart-seat-utilization', seatRows.map(r => r.vendor), [
        { label: 'Seats paid', data: seatRows.map(r => r.seatsPaid), color: s1 },
        { label: 'Seats used', data: seatRows.map(r => r.seatsActive), color: s3 },
      ]);
      const lg = document.getElementById('legend-seats');
      if (lg) lg.innerHTML = renderLegendRow([{ label: 'Seats paid', color: s1 }, { label: 'Seats used', color: s3 }]);
    }

    // ── Spend by plan tier donut ──────────────────────────────
    const tiers = {};
    subs.forEach(s => {
      const tier = s.plan_tier || 'Other';
      tiers[tier] = (tiers[tier] || 0) + (s.monthly_cost || 0);
    });
    // Three validated series colours: the two biggest tiers, the rest folded into "Other".
    const [labels, values] = topTwoAndOther(tiers);
    createDoughnutChart('chart-saas-category', labels, values, [s1, s2, s3].slice(0, labels.length), { legendId: 'legend-saas-category' });
  });
}

export function topTwoAndOther(totals) {
  const sorted = Object.entries(totals).sort((a, b) => b[1] - a[1]);
  const head = sorted.slice(0, 2);
  const rest = sorted.slice(2).reduce((sum, [, v]) => sum + v, 0);
  const out = rest > 0 ? [...head, ['Other', rest]] : head;
  return [out.map(([k]) => k), out.map(([, v]) => Math.round(v))];
}
