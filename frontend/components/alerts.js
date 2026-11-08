// ============================================================
// ALERT BANNER COMPONENT
// ============================================================

import { fetchPendingAlerts, sendCommand } from '../lib/api.js';
import { ICON_ARROW } from '../lib/ui.js';

const BANNER_LABELS = { warning: 'Needs a decision', critical: 'Urgent', info: 'All clear' };

/** Fill the page's banner from the live pending alerts (text set via textContent: alert text is data). */
export async function hydrateAlertBanner() {
  const pending = await fetchPendingAlerts();
  const banner = document.getElementById('alert-banner');
  if (!banner) return; // navigated away while loading
  const urgent = pending.filter((a) => a.tier === 'urgent');
  const lead = urgent[0] || pending[0];
  const type = urgent.length ? 'critical' : pending.length ? 'warning' : 'info';

  const set = (sel, text) => {
    const el = banner.querySelector(sel);
    if (el) el.textContent = text;
  };
  banner.querySelector('.alert-banner-icon')?.setAttribute('class', `alert-banner-icon ${type}`);
  set('.alert-banner-meta', BANNER_LABELS[type]);
  set(
    '.alert-banner-title',
    pending.length
      ? `${pending.length} need${pending.length === 1 ? 's' : ''} you${urgent.length ? ` · ${urgent.length} urgent` : ''}`
      : 'Nothing needs you right now',
  );
  set('.alert-banner-desc', lead ? lead.message : 'Runway will text you when something needs a decision.');
}

/**
 * Render an alert banner
 * @param {Object} alert - { type: 'warning'|'critical'|'info', title, desc, action, command }
 */
export function renderAlert(alert) {
  const labels = { warning: 'Needs a decision', critical: 'Urgent', info: 'All clear' };
  const actionId = `alert-action-${Math.random().toString(36).slice(2, 8)}`;
  return `
    <div class="alert-banner" id="alert-banner" role="status">
      <div class="alert-banner-icon ${alert.type}"><span></span></div>
      <div class="alert-banner-content">
        <div class="alert-banner-meta">${labels[alert.type] || 'Update'}</div>
        <div class="alert-banner-title">${alert.title}</div>
        <div class="alert-banner-desc">${alert.desc}</div>
      </div>
      ${alert.action ? `<button class="btn" id="${actionId}" data-banner-action ${alert.navigate ? `data-navigate="${alert.navigate}"` : `data-command="${alert.command || alert.action.toLowerCase()}"`}>${alert.action}${ICON_ARROW}</button>` : ''}
    </div>
  `;
}

export function bindAlertActions() {
  hydrateAlertBanner();
  document.querySelectorAll('[data-banner-action]').forEach(btn => {
    // app.js and each page both call this; bind once or a click sends the command twice.
    if (btn.dataset.bound) return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', async () => {
      if (btn.dataset.navigate) {
        window.location.hash = btn.dataset.navigate;
        return;
      }
      const command = btn.dataset.command;
      const original = btn.innerHTML;
      btn.textContent = 'Asking…';
      btn.disabled = true;

      try {
        const reply = await sendCommand(command);
        btn.innerHTML = original;
        btn.disabled = false;
        // Show reply as a toast or update the desc
        const banner = btn.closest('.alert-banner');
        if (banner) {
          const desc = banner.querySelector('.alert-banner-desc');
          if (desc) { desc.textContent = reply; desc.classList.add('is-reply'); }
        }
      } catch {
        btn.innerHTML = original;
        btn.disabled = false;
      }
    });
  });
}
