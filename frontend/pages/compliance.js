// ============================================================
// COMPLIANCE PAGE — Employee expenses & policy compliance
// ============================================================

import { renderMetrics } from '../components/metrics.js';
import { renderTable, badge, formatCurrency } from '../components/tables.js';
import { createDoughnutChart, seriesColors } from '../components/charts.js';
import { cssVar, escapeHtml, vendorTile } from '../lib/ui.js';
import { topTwoAndOther } from './saas-sprawl.js';
import { fetchComplianceTransactions, fetchEmployees } from '../lib/api.js';
import { renderAlert } from '../components/alerts.js';

export function renderCompliance() {
  const metricsHTML = renderMetrics([
    { id: 'totalExpenses', label: 'Team expenses', value: '—', sub: 'on employee cards' },
    { id: 'autoApproved', label: 'Approved', value: '—', sub: 'inside policy' },
    { id: 'flaggedExpenses', label: 'Flagged', value: '—', sub: 'outside policy' },
    { id: 'pendingExpenses', label: 'Pending', value: '—', sub: 'waiting on a decision' },
  ]);

  return `
    <div class="page" id="page-compliance">
      <div class="page-header">
        <div>
          <h1>Expenses</h1>
          <p>Every swipe on a team card, checked against your policy. Quiet when clean.</p>
        </div>
      </div>
      ${renderAlert({ type: 'info', title: 'Checking what needs you…', desc: '', action: 'Show pending', command: 'show pending' })}
      ${metricsHTML}

      <div class="charts-grid even">
        <div class="chart-card">
          <div class="chart-header"><div><div class="chart-title">Where the money went</div><div class="chart-sub">By merchant</div></div></div>
          <div class="chart-body donut">
            <div class="donut-canvas"><canvas id="chart-expense-category" role="img" aria-label="Expenses by merchant"></canvas></div>
            <ul class="legend" id="legend-expense-category"></ul>
          </div>
        </div>
        <div class="chart-card">
          <div class="chart-header"><div><div class="chart-title">Policy outcome</div><div class="chart-sub">Number of expenses</div></div></div>
          <div class="chart-body donut">
            <div class="donut-canvas"><canvas id="chart-approval-breakdown" role="img" aria-label="Policy outcome"></canvas></div>
            <ul class="legend" id="legend-approval-breakdown"></ul>
          </div>
        </div>
      </div>

      <div id="compliance-table"></div>
    </div>
  `;
}

export function initComplianceCharts() {
  const [s1, s2, s3] = seriesColors();
  Promise.all([fetchComplianceTransactions(), fetchEmployees()]).then(([txns, emps]) => {
    if (!txns.length) return;

    // ── Employee lookup map ───────────────────────────────────
    const empMap = {};
    emps.forEach(e => { empMap[e.id] = e; });

    // ── Derive status → policy check ──────────────────────────
    // DB uses: resolved = approved, flagged = fail, pending = review
    const policyCheck = status =>
      status === 'resolved' ? 'pass' : status === 'flagged' ? 'fail' : 'review';
    const displayStatus = status =>
      status === 'resolved' ? 'approved' : status;

    const rows = txns.map(t => ({
      ...t,
      date:        t.created_at,
      policyCheck: policyCheck(t.status),
      displayStatus: displayStatus(t.status),
    }));

    // ── Patch metric cards ────────────────────────────────────
    const totalExpenses = txns.reduce((s, t) => s + (t.amount || 0), 0);
    const autoApproved  = txns.filter(t => t.status === 'resolved').length;
    const flagged       = txns.filter(t => t.status === 'flagged').length;
    const pending       = txns.filter(t => t.status === 'pending').length;

    const patch = (id, val) => {
      const el = document.querySelector(`[data-metric-value="${id}"]`);
      if (el) el.textContent = val;
    };
    patch('totalExpenses',   `$${Math.round(totalExpenses).toLocaleString()}`);
    patch('autoApproved',    autoApproved.toString());
    patch('flaggedExpenses', flagged.toString());
    patch('pendingExpenses', pending.toString());

    // ── Expenses table ────────────────────────────────────────
    const policyMap = { pass: 'healthy', review: 'warning', fail: 'critical' };
    const tableEl = document.getElementById('compliance-table');
    if (tableEl) {
      tableEl.innerHTML = renderTable({
        title: 'Recent expenses', id: 'table-expenses',
        columns: [
          { key: 'employee_id', label: 'Person', render: v => {
            const emp = empMap[v] || { name: 'Unknown', role: '' };
            const initials = escapeHtml(String(emp.name).split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase());
            return `<div class="person"><span class="person-avatar">${initials}</span>
              <div><div class="person-name">${escapeHtml(emp.name)}</div><div class="person-role">${escapeHtml(emp.role || '')}</div></div></div>`;
          }},
          { key: 'merchant',     label: 'Merchant', render: v => `<span class="vendor">${vendorTile(v, { size: 'sm' })}${escapeHtml(v)}</span>` },
          { key: 'memo',         label: 'Note',     render: v => `<span class="text-muted">${escapeHtml(v || '—')}</span>` },
          { key: 'amount',       label: 'Amount',   align: 'right', render: v => formatCurrency(v) },
          { key: 'date',         label: 'Date',     render: v => new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) },
          { key: 'displayStatus',label: 'Status',   render: v => badge(v) },
        ],
        rows,
      });
    }

    // ── Expenses by merchant donut ────────────────────────────
    const merchants = {};
    txns.forEach(t => {
      merchants[t.merchant] = (merchants[t.merchant] || 0) + (t.amount || 0);
    });
    const [mLabels, mValues] = topTwoAndOther(merchants);
    createDoughnutChart('chart-expense-category', mLabels, mValues, [s1, s2, s3].slice(0, mLabels.length), { legendId: 'legend-expense-category' });

    // ── Approval breakdown donut ──────────────────────────────
    // Status colours (reserved for state), always shown with their label in the legend.
    createDoughnutChart('chart-approval-breakdown', ['Approved', 'Flagged', 'Pending'], [autoApproved, flagged, pending],
      [cssVar('--good'), cssVar('--critical'), cssVar('--warning')], { legendId: 'legend-approval-breakdown', count: true });
  });
}
