// ============================================================
// AI SPEND PAGE — Deep dive into AI API costs
// ============================================================

import { renderAlert } from '../components/alerts.js';
import { renderMetrics } from '../components/metrics.js';
import { renderTable, formatCurrency, formatNumber } from '../components/tables.js';
import { createLineChart, createBarChart, renderLegendRow, seriesColors } from '../components/charts.js';
import { escapeHtml, vendorTile } from '../lib/ui.js';
import { fetchAIUsage } from '../lib/api.js';

export function renderAISpend() {
  const metricsHTML = renderMetrics([
    { id: 'totalAISpend', label: 'AI spend', value: '—', sub: 'across all weeks on record' },
    { id: 'aiPotentialSavings', label: 'Savings from routing', value: '—', sub: 'per month, cheaper models' },
    { id: 'wrongModelCalls', label: 'Calls on the wrong model', value: '—', sub: 'could run on a smaller model' },
    { id: 'avgCostPerCall', label: 'Average cost per call', value: '—', sub: 'across providers' },
  ]);

  return `
    <div class="page" id="page-ai-spend">
      <div class="page-header">
        <div>
          <h1>AI spend</h1>
          <p>Model usage by provider, and where a cheaper model would do the same job.</p>
        </div>
      </div>
      ${renderAlert({ type: 'info', title: 'Checking what needs you…', desc: '', action: 'Show pending', command: 'show pending' })}
      ${metricsHTML}

      <div class="charts-grid even">
        <div class="chart-card">
          <div class="chart-header">
            <div><div class="chart-title">Weekly cost by provider</div><div class="chart-sub">Dollars per week</div></div>
            <div id="legend-ai-trend"></div>
          </div>
          <div class="chart-body"><canvas id="chart-ai-trend" role="img" aria-label="Weekly AI cost by provider"></canvas></div>
        </div>
        <div class="chart-card">
          <div class="chart-header">
            <div><div class="chart-title">Cost before and after routing</div><div class="chart-sub">Total per provider</div></div>
            <div id="legend-ai-bar"></div>
          </div>
          <div class="chart-body"><canvas id="chart-ai-provider-bar" role="img" aria-label="Cost before and after routing"></canvas></div>
        </div>
      </div>

      <div id="ai-usage-table"></div>
      <div id="ai-opportunities"></div>
    </div>
  `;
}

export function initAISpendCharts() {
  const [s1, s2, s3] = seriesColors();
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
        title: 'Usage by model',
        id: 'table-model-usage',
        columns: [
          { key: 'model',            label: 'Model', render: v => `<span class="mono">${escapeHtml(v)}</span>` },
          { key: 'provider',         label: 'Provider', render: v => `<span class="vendor">${vendorTile(v, { size: 'sm' })}${escapeHtml(cap(v))}</span>` },
          { key: 'pattern',          label: 'Use case', render: v => escapeHtml(String(v).replace(/_/g, ' ')) },
          { key: 'calls',            label: 'Calls',     align: 'right', render: v => formatNumber(v) },
          { key: 'cost',             label: 'Cost',      align: 'right', render: v => formatCurrency(Math.round(v)) },
          { key: 'recommendedModel', label: 'Better fit', render: v => v ? `<span class="mono">${escapeHtml(v)}</span>` : '<span class="text-muted">Already right</span>' },
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
            <div class="section-title">Biggest routing savings</div>
            <div class="section-subtitle">Use cases where a smaller model does the same job</div>
          </div>
        </div>
        <div class="opportunities-grid">
          ${opportunities.map(opp => `
            <div class="opportunity-card">
              <div class="opportunity-header">
                <div class="vendor">
                  ${vendorTile(opp.provider)}
                  <div>
                    <div class="opportunity-title">${escapeHtml(String(opp.pattern).replace(/_/g, ' '))}</div>
                    <div class="opportunity-route">${escapeHtml(opp.model)} → ${escapeHtml(opp.recommendedModel || '?')}</div>
                  </div>
                </div>
                <div class="opportunity-savings">+$${Math.round(opp.potentialSavings).toLocaleString()}<small>/mo</small></div>
              </div>
              <div class="opportunity-detail"><span class="opportunity-detail-label">Calls on record</span><span class="num">${formatNumber(opp.calls)}</span></div>
              <div class="opportunity-detail"><span class="opportunity-detail-label">Cost on record</span><span class="num">${formatCurrency(Math.round(opp.cost))}</span></div>
            </div>
          `).join('')}
        </div>`;
    }

    // ── Step 6: AI spend trend line (by vendor × week) ────────
    const vendors   = [...new Set(rows.map(r => r.vendor))];
    const weeks     = [...new Set(rows.map(r => r.week_start))].sort();
    const weekLabels = weeks.map(w => new Date(w).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
    // Colour follows the vendor in fixed order (by total cost). Only three series colours pass
    // validation, so past three the smaller providers fold into "Other" (dataviz: never cycle a hue).
    const palette = [s1, s2, s3];
    const costOf = (v) => rows.filter(r => r.vendor === v).reduce((s, r) => s + (r.total_cost || 0), 0);
    const ranked = [...vendors].sort((a, b) => costOf(b) - costOf(a));
    const named = ranked.length > 3 ? ranked.slice(0, 2) : ranked;
    const others = ranked.filter(v => !named.includes(v));
    const weekCost = (vs, w) => Math.round(rows.filter(r => vs.includes(r.vendor) && r.week_start === w).reduce((s, r) => s + (r.total_cost || 0), 0));
    const trendSeries = [
      ...named.map((v, i) => ({ label: cap(v), color: palette[i], data: weeks.map(w => weekCost([v], w)) })),
      ...(others.length ? [{ label: 'Other', color: palette[named.length], data: weeks.map(w => weekCost(others, w)) }] : []),
    ];

    createLineChart('chart-ai-trend', weekLabels, trendSeries, { dollarFormat: true, fill: false });
    const legendTrend = document.getElementById('legend-ai-trend');
    if (legendTrend && trendSeries.length > 1) legendTrend.innerHTML = renderLegendRow(trendSeries);

    // ── Step 6: Cost per provider bar chart ───────────────────
    const byVendor = {};
    rows.forEach(r => {
      if (!byVendor[r.vendor]) byVendor[r.vendor] = { cost: 0, savings: 0 };
      byVendor[r.vendor].cost    += r.total_cost        || 0;
      byVendor[r.vendor].savings += r.potential_savings || 0;
    });
    const vendorNames = Object.keys(byVendor).map(cap);
    createBarChart('chart-ai-provider-bar', vendorNames, [
      { label: 'Today', data: Object.values(byVendor).map(v => Math.round(v.cost)), color: s2 },
      { label: 'After routing', data: Object.values(byVendor).map(v => Math.round(v.cost - v.savings)), color: s3 },
    ], { dollarFormat: true });
    const legendBar = document.getElementById('legend-ai-bar');
    if (legendBar) legendBar.innerHTML = renderLegendRow([{ label: 'Today', color: s2 }, { label: 'After routing', color: s3 }]);
  });
}

function cap(v) { const t = String(v || ''); return t === 'openai' ? 'OpenAI' : t.charAt(0).toUpperCase() + t.slice(1); }
