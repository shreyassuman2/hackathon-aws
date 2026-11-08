// ============================================================
// RUNWAY DASHBOARD — app controller: routing, grade, page swap
// ============================================================

import './style.css';
import { renderNavbar, bindNavbarEvents } from './components/navbar.js';
import { bindAlertActions } from './components/alerts.js';
import { destroyAllCharts } from './components/charts.js';
import { initScrollFx } from './lib/scroll.js';

import { renderDashboard, initDashboardCharts } from './pages/dashboard.js';
import { renderAISpend, initAISpendCharts } from './pages/ai-spend.js';
import { renderSaaSSprawl, initSaaSSprawlCharts } from './pages/saas-sprawl.js';
import { renderCompliance, initComplianceCharts } from './pages/compliance.js';

const pages = {
  'dashboard': { render: renderDashboard, init: initDashboardCharts },
  'ai-spend': { render: renderAISpend, init: initAISpendCharts },
  'saas-sprawl': { render: renderSaaSSprawl, init: initSaaSSprawlCharts },
  'compliance': { render: renderCompliance, init: initComplianceCharts },
};

let currentTab = 'dashboard';
let firstRender = true;

// Pages register cleanup (pollers, listeners) here; it runs before the next page renders.
window.runwayCleanup = [];
function cleanup() {
  destroyAllCharts();
  for (const fn of window.runwayCleanup.splice(0)) {
    try { fn(); } catch { /* ignore */ }
  }
}

// ── Grade (light / evening): chosen by a click only ──
function toggleTheme() {
  const root = document.documentElement;
  const dark = root.dataset.theme !== 'dark';
  if (dark) root.dataset.theme = 'dark'; else delete root.dataset.theme;
  try { localStorage.setItem('runway-theme', dark ? 'dark' : 'light'); } catch { /* private mode */ }
  renderApp({ keepPosition: true }); // charts read their colours from the grade
}

function navigateTo(tabId) {
  if (tabId === currentTab || !pages[tabId]) return;
  currentTab = tabId;
  window.location.hash = tabId;
  renderApp();
}

function renderApp({ keepPosition = false } = {}) {
  const app = document.getElementById('app');
  const page = pages[currentTab];
  if (!page) return;
  cleanup();
  const y = window.scrollY;

  app.innerHTML = `
    ${renderNavbar(currentTab)}
    <main class="main-content" id="main">
      ${page.render()}
    </main>
    <footer class="app-footer">Runway · Product names and logos are trademarks of their owners.</footer>
  `;

  // A click swap fades the new page in (400ms); the first paint is in place at once.
  if (!firstRender && !keepPosition) app.querySelector('.page')?.classList.add('is-entering');
  if (keepPosition) window.scrollTo(0, y); else if (!firstRender) window.scrollTo(0, 0);
  firstRender = false;

  bindNavbarEvents(navigateTo, toggleTheme);
  bindAlertActions();
  page.init();
  window.runwayCleanup.push(initScrollFx(document));
}

function init() {
  const hash = window.location.hash.replace('#', '');
  if (pages[hash]) currentTab = hash;
  renderApp();
  window.addEventListener('hashchange', () => {
    const h = window.location.hash.replace('#', '');
    if (pages[h] && h !== currentTab) {
      currentTab = h;
      renderApp();
    }
  });
}

init();
