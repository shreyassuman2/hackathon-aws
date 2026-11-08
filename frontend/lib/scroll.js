// ============================================================
// SCROLL DYNAMICS (requested by the team; deliberately outside the taste skill's
// "nothing moves on scroll" rule). Four effects, all off under reduced motion:
//   1. reveal      — content below the fold rises 8px and fades in, once
//   2. charts      — a chart below the fold draws in when it's first seen (charts.js)
//   3. condensing bar — the top bar gains a shadow and the page title once it scrolls away
//   4. parallax    — the page header drifts slower than the page (desktop only)
// Content is never hidden without JS or under reduced motion: the hidden state is only
// applied by this file, and only to elements that start below the fold.
// ============================================================

import { reducedMotion } from './ui.js';

const REVEAL = [
  '.metrics-grid > *',
  '.charts-grid > *',
  '.activity-card',
  '.table-card',
  '.opportunity-card',
  '.section-header',
  '.timeline-card',
].join(',');

const motionOk = () => !reducedMotion();

/** Call once per page render. Returns a cleanup function. */
export function initScrollFx(root = document) {
  const cleanups = [];
  const main = root.querySelector('#main');
  if (!main) return () => {};

  // ── 1. reveal ──────────────────────────────────────────────
  if (motionOk() && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        const el = e.target;
        io.unobserve(el);
        el.classList.add('is-in');
        // Once revealed, drop the reveal classes so the hover transitions take over again.
        el.addEventListener('transitionend', () => el.classList.remove('reveal', 'is-in'), { once: true });
        setTimeout(() => el.classList.remove('reveal', 'is-in'), 1200);
      }
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });

    const seen = new WeakSet();
    const scan = () => {
      main.querySelectorAll(REVEAL).forEach((el) => {
        if (seen.has(el)) return;
        seen.add(el);
        const top = el.getBoundingClientRect().top;
        if (top < window.innerHeight * 0.92) return; // already on screen at load: shown at once, no flash
        // A light cascade across a row (metric cards, chart pairs).
        const siblings = el.parentElement ? [...el.parentElement.children].filter((c) => c.matches(REVEAL)) : [];
        el.style.setProperty('--reveal-delay', `${Math.min(siblings.indexOf(el), 3) * 70}ms`);
        el.classList.add('reveal');
        io.observe(el);
      });
    };
    scan();
    // Pages fill tables and cards in after their data arrives; reveal those too.
    const mo = new MutationObserver(scan);
    mo.observe(main, { childList: true, subtree: true });
    cleanups.push(() => { io.disconnect(); mo.disconnect(); });
  }

  // ── 3 + 4. condensing bar and parallax header: one passive scroll read per frame ──
  const bar = root.querySelector('.navbar');
  const header = main.querySelector('.page-header');
  const title = header?.querySelector('h1');
  const context = bar?.querySelector('.navbar-context');
  if (context && title) context.textContent = title.textContent;

  let ticking = false;
  const parallaxOn = () => motionOk() && window.matchMedia('(min-width: 761px)').matches;
  const update = () => {
    ticking = false;
    const y = window.scrollY;
    bar?.classList.toggle('is-scrolled', y > 4);
    if (title) {
      const gone = title.getBoundingClientRect().bottom < (bar?.offsetHeight || 64);
      bar?.classList.toggle('show-context', gone);
    }
    if (header) {
      if (parallaxOn()) {
        const h = header.offsetHeight || 1;
        const p = Math.min(y, h * 1.5);
        header.style.setProperty('--px', `${p * 0.35}px`);
        header.style.setProperty('--po', String(Math.max(0.25, 1 - p / (h * 1.6))));
      } else {
        header.style.removeProperty('--px');
        header.style.removeProperty('--po');
      }
    }
  };
  const onScroll = () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } };
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll, { passive: true });
  update();
  cleanups.push(() => {
    window.removeEventListener('scroll', onScroll);
    window.removeEventListener('resize', onScroll);
  });

  return () => cleanups.forEach((fn) => fn());
}

/**
 * 2. Run `draw` now if the element is on screen, otherwise the first time it scrolls into view.
 * Under reduced motion (or without IntersectionObserver) it draws at once.
 */
export function whenSeen(el, draw) {
  if (!el || !motionOk() || !('IntersectionObserver' in window)) { draw(); return; }
  const r = el.getBoundingClientRect();
  if (r.top < window.innerHeight && r.bottom > 0) { draw(); return; }
  const io = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) { io.disconnect(); draw(); }
  }, { threshold: 0.25 });
  io.observe(el);
  window.runwayCleanup?.push(() => io.disconnect());
}
