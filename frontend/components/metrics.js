// ============================================================
// METRIC CARDS COMPONENT
// ============================================================

/**
 * Render a grid of metric cards
 * @param {Array} metrics - Array of { label, value, sub, color, change, changeDir }
 */
export function renderMetrics(metrics) {
  return `
    <div class="metrics-grid">
      ${metrics.map(m => `
        <div class="metric-card bg-${m.color || 'white'}">
          <div class="metric-card-top">
            <div class="metric-label">${m.label}</div>
            <div class="metric-accent-dot bg-${m.dotColor}"></div>
          </div>
          <div class="metric-value-row">
            <div class="metric-value color-${m.valueColor || 'black'}" ${m.id ? `data-metric-value="${m.id}"` : ''}>${m.value}</div>
          </div>
          <div class="metric-sub" ${m.id ? `data-metric-sub="${m.id}"` : ''}>
            ${m.sub}
          </div>
          ${m.change ? `<div class="metric-change-block ${m.changeDir === 'up' ? 'up' : 'down'}">${m.changeDir === 'down' ? '↓' : '↑'} ${m.change}</div>` : ''}
          <div class="metric-corner-tag">${m.tag}</div>
        </div>
      `).join('')}
    </div>
  `;
}
