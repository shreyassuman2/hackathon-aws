// ============================================================
// AI SPEND PAGE — Deep dive into AI API costs
// ============================================================

import { renderAlert, bindAlertActions } from '../components/alerts.js';
import { renderMetrics } from '../components/metrics.js';
import { renderTable, formatCurrency, formatNumber } from '../components/tables.js';
import { createLineChart, createBarChart } from '../components/charts.js';
import { fetchAIUsage } from '../lib/api.js';

export function renderAISpend() {
  const metricsHTML = renderMetrics([
    { id: 'totalAISpend',      label: 'Total AI Spend',     value: '—', sub: 'This month',                    color: 'purple' },
    { id: 'aiPotentialSavings',label: 'Potential Savings',  value: '—', sub: 'Per month via model routing',   color: 'green'  },
    { id: 'wrongModelCalls',   label: 'Wrong-Model Calls',  value: '—', sub: 'Could use cheaper models',      color: 'orange' },
    { id: 'avgCostPerCall',    label: 'Avg Cost / Call',    value: '—', sub: 'Across all providers',          color: 'blue'   },
  ]);

  const alertHTML = renderAlert({
    type: 'info',
    title: 'Checking what needs you…',
    desc: '',
    action: 'Show pending',
    command: 'show pending',
  });

  return `
    <div class="page" id="page-ai-spend">
      ${alertHTML}
      ${metricsHTML}

      <div class="charts-grid">
        <div class="chart-card">
          <div class="chart-header">
            <div class="chart-title blue">AI SPEND BY PROVIDER</div>
          </div>
          <div class="chart-body">
            <canvas id="chart-ai-trend"></canvas>
          </div>
        </div>

        <div class="chart-card">
          <div class="chart-header">
            <div class="chart-title purple">COST PER PROVIDER</div>
          </div>
          <div class="chart-body">
            <canvas id="chart-ai-provider-bar"></canvas>
          </div>
        </div>
      </div>

      <div id="ai-usage-table"></div>
      <div id="ai-opportunities"></div>
    </div>
  `;
}

export function initAISpendCharts() {
  bindAlertActions();
  fetchAIUsage().then(rows => {
    if (!rows.length) return;

    // ── Aggregate by vendor+model+use_case ───────────────────
    const grouped = {};
    rows.forEach(r => {
      const key = `${r.vendor}|${r.model}|${r.use_case}`;
      if (!grouped[key]) {
        grouped[key] = {
          provider:         r.vendor,
          model:            r.model,
          pattern:          r.use_case || '—',
          calls:            0,
          cost:             0,
          recommendedModel: r.recommended_model,
          potentialSavings: 0,
        };
      }
      grouped[key].calls           += r.call_count   || 0;
      grouped[key].cost            += r.total_cost   || 0;
      grouped[key].potentialSavings+= r.potential_savings || 0;
      if (r.recommended_model) grouped[key].recommendedModel = r.recommended_model;
    });
    const aggregated = Object.values(grouped);

    // ── Step 5: Patch metric cards ────────────────────────────
    const totalCost   = aggregated.reduce((s, r) => s + r.cost, 0);
    const totalSavings= aggregated.reduce((s, r) => s + r.potentialSavings, 0);
    const wrongCalls  = aggregated.filter(r => r.potentialSavings > 0).reduce((s, r) => s + r.calls, 0);
    const totalCalls  = aggregated.reduce((s, r) => s + r.calls, 0);
    const avgCost     = totalCalls > 0 ? totalCost / totalCalls : 0;

    const patch = (id, val) => {
      const el = document.querySelector(`[data-metric-value="${id}"]`);
      if (el) el.textContent = val;
    };
    patch('totalAISpend',       `$${Math.round(totalCost).toLocaleString()}`);
    patch('aiPotentialSavings', `$${Math.round(totalSavings).toLocaleString()}`);
    patch('wrongModelCalls',    formatNumber(wrongCalls));
    patch('avgCostPerCall',     `$${avgCost.toFixed(3)}`);

    // ── Step 5: Model usage table ─────────────────────────────
    const tableEl = document.getElementById('ai-usage-table');
    if (tableEl) {
      tableEl.innerHTML = renderTable({
        title: 'Model Usage Breakdown',
        titleColor: 'purple',
        id: 'table-model-usage',
        columns: [
          { key: 'model',            label: 'Model' },
          { key: 'provider',         label: 'Provider' },
          { key: 'pattern',          label: 'Use Case' },
          { key: 'calls',            label: 'Calls',     align: 'right', render: v => formatNumber(v) },
          { key: 'cost',             label: 'Cost',      align: 'right', render: v => formatCurrency(Math.round(v)) },
          { key: 'recommendedModel', label: 'Recommended', render: v => v ? `<span class="text-green">${v}</span>` : '<span class="text-muted">Optimal</span>' },
          { key: 'potentialSavings', label: 'Savings',   align: 'right', render: v => v > 0 ? `<span class="text-green">+$${Math.round(v).toLocaleString()}/mo</span>` : '<span class="text-muted">—</span>' },
        ],
        rows: aggregated.sort((a, b) => b.cost - a.cost),
      });
    }

    // ── Step 5: Opportunity cards ─────────────────────────────
    const oppsEl = document.getElementById('ai-opportunities');
    const opportunities = aggregated.filter(r => r.potentialSavings > 0).sort((a, b) => b.potentialSavings - a.potentialSavings);
    if (oppsEl && opportunities.length) {
      oppsEl.innerHTML = `
        <div class="section-header">
          <div>
            <div class="section-title">Top Optimization Opportunities</div>
            <div class="section-subtitle">AI agent recommendations based on usage pattern analysis</div>
          </div>
        </div>
        <div class="opportunities-grid">
          ${opportunities.map(opp => `
            <div class="opportunity-card">
              <div class="opportunity-header">
                <div>
                  <div class="opportunity-title">${opp.pattern}</div>
                  <div style="font-size:0.75rem;color:var(--text-secondary);margin-top:4px">${opp.model} → ${opp.recommendedModel || '?'}</div>
                </div>
                <div class="opportunity-savings">+$${Math.round(opp.potentialSavings).toLocaleString()}<span style="font-size:0.75rem;font-weight:500">/mo</span></div>
              </div>
              <div class="opportunity-detail">
                <span class="opportunity-detail-label">Monthly calls</span>
                <span>${formatNumber(opp.calls)}</span>
              </div>
              <div class="opportunity-detail">
                <span class="opportunity-detail-label">Current cost</span>
                <span>${formatCurrency(Math.round(opp.cost))}/mo</span>
              </div>
              <div class="opportunity-bar">
                <div class="opportunity-bar-fill green" style="width:80%"></div>
              </div>
            </div>
          `).join('')}
        </div>`;
    }

    // ── Step 6: AI spend trend line (by vendor × week) ────────
    const vendors   = [...new Set(rows.map(r => r.vendor))];
    const weeks     = [...new Set(rows.map(r => r.week_start))].sort();
    const weekLabels = weeks.map(w => new Date(w).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
    const vendorColors = { anthropic: 'rgb(59,130,246)', openai: 'rgb(168,85,247)', google: 'rgb(6,182,212)', mistral: 'rgb(245,158,11)' };

    createLineChart('chart-ai-trend', weekLabels,
      vendors.map(v => ({
        label: v.charAt(0).toUpperCase() + v.slice(1),
        color: vendorColors[v] || 'rgb(100,100,100)',
        data: weeks.map(w => {
          const match = rows.filter(r => r.vendor === v && r.week_start === w);
          return Math.round(match.reduce((s, r) => s + (r.total_cost || 0), 0));
        }),
      })),
      { dollarFormat: true, fill: false }
    );

    // ── Step 6: Cost per provider bar chart ───────────────────
    const byVendor = {};
    rows.forEach(r => {
      if (!byVendor[r.vendor]) byVendor[r.vendor] = { cost: 0, savings: 0 };
      byVendor[r.vendor].cost    += r.total_cost        || 0;
      byVendor[r.vendor].savings += r.potential_savings || 0;
    });
    const vendorNames = Object.keys(byVendor).map(v => v.charAt(0).toUpperCase() + v.slice(1));
    createBarChart('chart-ai-provider-bar', vendorNames, [
      { label: 'Current Cost',       data: Object.values(byVendor).map(v => Math.round(v.cost)),            color: 'rgba(168,85,247,0.7)' },
      { label: 'After Optimization', data: Object.values(byVendor).map(v => Math.round(v.cost - v.savings)), color: 'rgba(34,197,94,0.7)'  },
    ], { dollarFormat: true });
  });
}
