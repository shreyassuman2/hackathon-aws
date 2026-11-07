// ============================================================
// NAVBAR — brand, tabs with one sliding indicator, grade toggle
// ============================================================

import { placeIndicator, ICON_SUN, ICON_MOON } from '../lib/ui.js';

const TABS = [
  { id: 'dashboard', label: 'Overview' },
  { id: 'ai-spend', label: 'AI spend' },
  { id: 'saas-sprawl', label: 'SaaS' },
  { id: 'compliance', label: 'Expenses' },
];

// Where the indicator sat on the previous page, so it slides from there to the new tab.
let lastIndicator = null;

export function renderNavbar(activeTab) {
  const dark = document.documentElement.dataset.theme === 'dark';
  return `
    <header class="navbar" id="navbar">
      <a href="#main" class="skip-link">Skip to content</a>
      <a href="#dashboard" class="navbar-brand" aria-label="Runway overview">
        <svg class="navbar-logo" viewBox="0 0 32 32" aria-hidden="true">
          <rect width="32" height="32" rx="7" fill="currentColor"/>
          <path d="M8 22 L16 9 L24 22" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span class="navbar-title">Runway</span>
      </a>

      <nav class="navbar-nav" id="navbar-nav" aria-label="Sections">
        ${TABS.map((t) => `
          <button class="nav-tab ${t.id === activeTab ? 'active' : ''}" data-tab="${t.id}" id="nav-${t.id}"
            ${t.id === activeTab ? 'aria-current="page"' : ''}>${t.label}</button>`).join('')}
        <span class="nav-indicator" aria-hidden="true"></span>
      </nav>

      <div class="navbar-actions">
        <span class="live-status">Watching your spend</span>
        <button class="btn icon-btn" id="theme-toggle" aria-label="Switch to ${dark ? 'light' : 'dark'} mode">
          ${dark ? ICON_SUN : ICON_MOON}
        </button>
      </div>
    </header>
  `;
}

export function bindNavbarEvents(onTabChange, onThemeToggle) {
  const ind = document.querySelector('.nav-indicator');
  const active = document.querySelector('.nav-tab.active');
  if (ind && active) {
    // Start where the previous page's indicator was, then slide to the active tab.
    if (lastIndicator) {
      ind.style.transition = 'none';
      ind.style.setProperty('--x', lastIndicator.x);
      ind.style.setProperty('--w', lastIndicator.w);
      ind.getBoundingClientRect();
      ind.style.transition = '';
    }
    requestAnimationFrame(() => {
      placeIndicator(ind, active);
      lastIndicator = { x: ind.style.getPropertyValue('--x'), w: ind.style.getPropertyValue('--w') };
    });
    document.fonts?.ready.then(() => placeIndicator(ind, active));
    const onResize = () => placeIndicator(ind, active);
    window.addEventListener('resize', onResize);
    window.runwayCleanup?.push(() => window.removeEventListener('resize', onResize));
  }

  document.querySelectorAll('.nav-tab').forEach((tab) => {
    tab.addEventListener('click', () => onTabChange(tab.dataset.tab));
  });
  document.getElementById('theme-toggle')?.addEventListener('click', onThemeToggle);
}
