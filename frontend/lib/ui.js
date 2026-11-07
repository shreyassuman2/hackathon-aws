// Shared UI helpers: escaping, vendor logos, formatting, the one count-up.

/** Escape text before it goes into innerHTML. Merchant names, memos and alert text are data. */
export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Real logos fetched by the taste skill's icons.mjs into public/icons (credits: public/icons/icons-credits.json).
const LOGOS = {
  anthropic: 'anthropic', openai: 'openai', cursor: 'cursor', notion: 'notion', figma: 'figma',
  linear: 'linear', slack: 'slack', vercel: 'vercel', github: 'github', zoom: 'zoom',
  midjourney: 'midjourney', datadog: 'datadog', sentry: 'sentry', intercom: 'intercom',
  mailchimp: 'mailchimp', aws: 'aws', 'amazon web services': 'aws', twilio: 'twilio',
  mixpanel: 'mixpanel', amplitude: 'amplitude', posthog: 'posthog', loom: 'loom', evernote: 'evernote',
};

/** The logo key for a vendor/merchant name, found anywhere in the text (e.g. an alert message). */
export function vendorKey(text) {
  const low = String(text || '').toLowerCase();
  let best = null;
  let at = Infinity;
  for (const name of Object.keys(LOGOS)) {
    const i = low.search(new RegExp(`(^|[^a-z])${name.replace(/ /g, '\\s')}([^a-z]|$)`));
    if (i >= 0 && i < at) { at = i; best = LOGOS[name]; }
  }
  return best;
}

/** A logo tile for a vendor; a neutral initial tile when no real logo exists (never a drawn look-alike). */
export function vendorTile(name, { size = '', text = name } = {}) {
  const key = vendorKey(text);
  const cls = `vendor-tile ${size}`.trim();
  if (key) return `<span class="${cls}"><img src="/icons/${key}.svg" alt="" loading="lazy" decoding="async"></span>`;
  const initial = escapeHtml(String(name || '?').trim().charAt(0).toUpperCase() || '?');
  return `<span class="${cls} initial" aria-hidden="true">${initial}</span>`;
}

export const money = (n, digits = 0) =>
  `$${Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;

export const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * The page's one count (motion.md: once, on load, ~1000ms, final figure always reachable).
 * Under reduced motion the final text is set at once.
 */
export function countUp(el, to, format = money, ms = 1000) {
  if (!el) return;
  if (reducedMotion()) { el.textContent = format(to); return; }
  const start = performance.now();
  const ease = (t) => 1 - Math.pow(1 - t, 3);
  const step = (now) => {
    const t = Math.min(1, (now - start) / ms);
    el.textContent = format(Math.round(to * ease(t)));
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/** Read a CSS custom property off :root (series colours follow the light/dark grade). */
export const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/** '#2a78d6' + alpha -> 'rgba(42,120,214,a)'. Canvas can't parse CSS color-mix(), so charts use this. */
export function rgba(hex, a) {
  const h = String(hex).trim().replace('#', '');
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h.slice(0, 6);
  const n = parseInt(full, 16);
  if (Number.isNaN(n)) return `rgba(0,0,0,${a})`;
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/** Place a sliding indicator under the active item of a group (nav tabs, segmented controls). */
export function placeIndicator(indicator, active, { inset = 0 } = {}) {
  if (!indicator || !active) return;
  const parent = indicator.parentElement.getBoundingClientRect();
  const box = active.getBoundingClientRect();
  indicator.style.setProperty('--x', `${box.left - parent.left + inset}px`);
  indicator.style.setProperty('--w', `${box.width - inset * 2}px`);
}

export const ICON_ARROW = '<svg class="ico ico--arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>';
export const ICON_GO = '<svg class="metric-go" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 7h10v10"/><path d="M7 17 17 7"/></svg>';
export const ICON_SUN = '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2m-7.07-14.93 1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41m11.32-11.32 1.41-1.41"/></svg>';
export const ICON_MOON = '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>';
