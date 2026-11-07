// ============================================================
// RUNWAY DASHBOARD — App Controller
// Client-side routing and tab management
// ============================================================

import './style.css';
import { renderNavbar, bindNavbarEvents } from './components/navbar.js';
import { bindAlertActions } from './components/alerts.js';
import { destroyAllCharts } from './components/charts.js';

// Page imports
import { renderDashboard, initDashboardCharts } from './pages/dashboard.js';
import { renderAISpend, initAISpendCharts } from './pages/ai-spend.js';
import { renderSaaSSprawl, initSaaSSprawlCharts } from './pages/saas-sprawl.js';
import { renderCompliance, initComplianceCharts } from './pages/compliance.js';

// ── State ──
let currentTab = 'dashboard';
let currentTheme = localStorage.getItem('theme') || 'brutalist';

// ── Theme handler ──
function toggleTheme() {
  currentTheme = currentTheme === 'brutalist' ? 'minimal' : 'brutalist';
  localStorage.setItem('theme', currentTheme);
  applyTheme();
}

function applyTheme() {
  if (currentTheme === 'minimal') {
    document.body.classList.add('theme-minimal');
  } else {
    document.body.classList.remove('theme-minimal');
  }
}

// ── Page registry ──
const pages = {
  'dashboard': { render: renderDashboard, init: initDashboardCharts },
  'ai-spend': { render: renderAISpend, init: initAISpendCharts },
  'saas-sprawl': { render: renderSaaSSprawl, init: initSaaSSprawlCharts },
  'compliance': { render: renderCompliance, init: initComplianceCharts },
};

// ── Navigation handler ──
function navigateTo(tabId) {
  if (tabId === currentTab) return;
  currentTab = tabId;
  renderApp();
  
  // Update URL hash
  window.location.hash = tabId;
}

// ── Render ──
function renderApp() {
  const app = document.getElementById('app');

  // Destroy existing charts and timers before re-rendering
  destroyAllCharts();
  if (window.dashboardClock) {
    clearInterval(window.dashboardClock);
    window.dashboardClock = null;
  }

  const page = pages[currentTab];
  if (!page) return;

  app.innerHTML = `
    ${renderNavbar(currentTab, navigateTo)}
    <main class="main-content">
      ${page.render()}
    </main>
  `;

  // Bind nav events
  bindNavbarEvents(navigateTo, toggleTheme);

  // Apply theme class to current page
  applyTheme();

  // Bind alert action buttons
  bindAlertActions();

  // Initialize page-specific charts
  page.init();
}

// ── Init ──
function init() {
  // Read initial tab from URL hash
  const hash = window.location.hash.replace('#', '');
  if (pages[hash]) {
    currentTab = hash;
  }

  renderApp();

  // Handle back/forward navigation
  window.addEventListener('hashchange', () => {
    const hash = window.location.hash.replace('#', '');
    if (pages[hash] && hash !== currentTab) {
      currentTab = hash;
      renderApp();
    }
  });
}

// Boot
init();
