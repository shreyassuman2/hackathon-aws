// ============================================================
// TABLE COMPONENT
// ============================================================

/**
 * Render a data table with header
 * @param {Object} config - { title, titleColor, columns, rows, id }
 * columns: Array of { key, label, align?, render? }
 * rows: Array of objects
 */
export function renderTable(config) {
  const { title, titleColor = 'green', columns, rows, id } = config;

  return `
    <div class="table-card" id="${id || 'data-table'}">
      <div class="table-header">
        <div class="table-title">
          <div class="table-title-bar ${titleColor}"></div>
          <h3>${title}</h3>
        </div>
      </div>
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              ${columns.map(col => `<th style="text-align: ${col.align || 'left'}">${col.label}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                ${columns.map(col => `
                  <td style="text-align: ${col.align || 'left'}">
                    ${col.render ? col.render(row[col.key], row) : row[col.key]}
                  </td>
                `).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

/**
 * Render a status badge
 */
export function badge(status) {
  if (!status) return `<span class="badge pending">Pending</span>`;
  const label = status.charAt(0).toUpperCase() + status.slice(1);
  return `<span class="badge ${status}">${label}</span>`;
}

/**
 * Format currency
 */
export function formatCurrency(cents) {
  return '$' + (cents).toLocaleString();
}

/**
 * Format large numbers
 */
export function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toString();
}
