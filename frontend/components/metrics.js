// ============================================================
// METRIC CARDS — a label, one big mono number, one quiet line.
// A card that leads somewhere is a link and lifts on hover; the rest stay still.
// ============================================================

import { ICON_GO } from '../lib/ui.js';

/**
 * @param {Array} metrics - { id, label, value, sub, dot?, href? }
 *   dot: a CSS colour for the small identity mark (a series colour), optional
 *   href: '#ai-spend' etc. — makes the card a link
 */
export function renderMetrics(metrics) {
  return `
    <div class="metrics-grid">
      ${metrics.map((m) => {
        const tag = m.href ? 'a' : 'div';
        const attrs = m.href ? `href="${m.href}"` : '';
        return `
          <${tag} class="metric-card" ${attrs}>
            <div class="metric-label">
              ${m.dot ? `<span class="metric-dot" style="background:${m.dot}"></span>` : ''}${m.label}
            </div>
            ${m.href ? ICON_GO : ''}
            <div class="metric-value" ${m.id ? `data-metric-value="${m.id}"` : ''}>${m.value}</div>
            <div class="metric-sub" ${m.id ? `data-metric-sub="${m.id}"` : ''}>${m.sub}</div>
          </${tag}>`;
      }).join('')}
    </div>
  `;
}
