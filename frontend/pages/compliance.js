// ============================================================
// COMPLIANCE PAGE — Employee expenses & policy compliance
// ============================================================

import { renderMetrics } from '../components/metrics.js';
import { renderTable, badge, formatCurrency } from '../components/tables.js';
import { createDoughnutChart } from '../components/charts.js';
import { fetchComplianceTransactions, fetchEmployees } from '../lib/api.js';
import { renderAlert, bindAlertActions } from '../components/alerts.js';

export function renderCompliance() {
  const metricsHTML = renderMetrics([
    { id: 'totalExpenses',   label: 'Total Expenses',  value: '—', sub: 'This month',       color: 'white'  },
    { id: 'autoApproved',    label: 'Auto-Approved',   value: '—', sub: 'Policy compliant', color: 'green'  },
    { id: 'flaggedExpenses', label: 'Flagged',         value: '—', sub: 'Policy violations',color: 'red'    },
    { id: 'pendingExpenses', label: 'Pending Review',  value: '—', sub: 'Awaiting decision',color: 'orange' },
  ]);

  const alertHTML = renderAlert({
    type: 'info',
    title: 'Checking what needs you…',
    desc: '',
    action: 'Show pending',
    command: 'show pending',
  });

  return `
    <div class="page" id="page-compliance">
      ${alertHTML}
      ${metricsHTML}

      <div class="charts-grid">
        <div class="chart-card">
          <div class="chart-header">
            <div class="chart-title orange">EXPENSES BY MERCHANT</div>
          </div>
          <div class="chart-body donut">
            <canvas id="chart-expense-category"></canvas>
          </div>
        </div>

        <div class="chart-card">
          <div class="chart-header">
            <div class="chart-title green">APPROVAL BREAKDOWN</div>
          </div>
          <div class="chart-body donut">
            <canvas id="chart-approval-breakdown"></canvas>
          </div>
        </div>
      </div>

      <div id="compliance-table"></div>
    </div>
  `;
}

export function initComplianceCharts() {
  bindAlertActions();
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
        title: 'Recent Expenses', titleColor: 'orange', id: 'table-expenses',
        columns: [
          { key: 'employee_id', label: 'Employee', render: v => {
            const emp = empMap[v] || { name: 'Unknown', role: '—' };
            const initials = emp.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
            return `<div style="display:flex;align-items:center;gap:8px">
              <div style="width:28px;height:28px;border-radius:50%;background:var(--bg-elevated);border:1px solid var(--border-default);display:flex;align-items:center;justify-content:center;font-size:0.625rem;font-weight:600;color:var(--text-secondary)">${initials}</div>
              <div>
                <div style="font-weight:600;font-size:0.8125rem">${emp.name}</div>
                <div style="font-size:0.6875rem;color:var(--text-tertiary)">${emp.role}</div>
              </div>
            </div>`;
          }},
          { key: 'merchant',     label: 'Merchant' },
          { key: 'memo',         label: 'Note',     render: v => `<span class="text-muted">${v || '—'}</span>` },
          { key: 'amount',       label: 'Amount',   align: 'right', render: v => formatCurrency(v) },
          { key: 'date',         label: 'Date',     render: v => new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) },
          { key: 'policyCheck',  label: 'Policy',   render: v => `<span class="badge ${policyMap[v]}">${v === 'pass' ? 'Pass' : v === 'review' ? 'Review' : 'Fail'}</span>` },
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
    createDoughnutChart(
      'chart-expense-category',
      Object.keys(merchants),
      Object.values(merchants).map(Math.round),
      ['#f59e0b', '#3b82f6', '#a855f7', '#22c55e', '#06b6d4', '#ef4444', '#eab308']
    );

    // ── Approval breakdown donut ──────────────────────────────
    createDoughnutChart(
      'chart-approval-breakdown',
      ['Approved', 'Flagged', 'Pending'],
      [autoApproved, flagged, pending],
      ['#22c55e', '#ef4444', '#f59e0b']
    );
  });
}
