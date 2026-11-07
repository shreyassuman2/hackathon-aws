// ============================================================
// TABLE — a hairline table. Every cell is escaped unless its column
// renders its own (trusted) markup and escapes the data inside it.
// ============================================================

import { escapeHtml } from '../lib/ui.js';

/**
 * @param {Object} config - { title, columns, rows, id }
 * columns: { key, label, align?, render?(value, row) -> HTML string }
 */
export function renderTable(config) {
  const { title, columns, rows, id } = config;
  const cell = (col, row) => (col.render ? col.render(row[col.key], row) : escapeHtml(row[col.key] ?? '—'));
  return `
    <div class="table-card" id="${id || 'data-table'}">
      <div class="table-header"><div class="table-title"><h3>${escapeHtml(title)}</h3></div></div>
      <div class="table-wrapper">
        <table>
          <thead><tr>${columns.map((c) => `<th style="text-align:${c.align || 'left'}">${escapeHtml(c.label)}</th>`).join('')}</tr></thead>
          <tbody>
            ${rows.map((row) => `<tr>${columns.map((c) => `<td style="text-align:${c.align || 'left'}">${cell(c, row)}</td>`).join('')}</tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

const STATUS_LABELS = { healthy: 'Healthy', warning: 'Watch', critical: 'Act now', pending: 'Pending', approved: 'Approved', flagged: 'Flagged', review: 'Review' };

/** A status badge: a coloured dot plus a word, never colour alone. */
export function badge(status) {
  const s = String(status || 'pending').toLowerCase();
  return `<span class="badge ${escapeHtml(s)}">${escapeHtml(STATUS_LABELS[s] || s.charAt(0).toUpperCase() + s.slice(1))}</span>`;
}

export function formatCurrency(n) {
  const v = Number(n || 0);
  const cents = Number.isInteger(v) ? 0 : 2; // $89.50, never $89.5
  return '$' + v.toLocaleString('en-US', { minimumFractionDigits: cents, maximumFractionDigits: cents });
}

export function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return String(num);
}
