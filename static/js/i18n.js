/**
 * ARS — Client-side i18n helper (minimal)
 * Language is now managed server-side via Flask session.
 * This file only handles: clock, ticker, RTL/LTR layout sync.
 */

// Read lang from <html> tag (set by Flask/Jinja)
const ARS_LANG = document.documentElement.lang || 'ar';

// ── Clock — desktop full, mobile time-only ───────────────────────────────────
function _startClock() {
  const el  = document.getElementById('topbarClock');
  const el2 = document.getElementById('topbarClockMobile');
  if (!el && !el2) return;
  function tick() {
    const now = new Date();
    const loc = ARS_LANG === 'ar' ? 'ar-SA' : 'en-US';
    // Desktop: full date + time
    const date = now.toLocaleDateString(loc, {weekday:'short', month:'short', day:'numeric'});
    const time = now.toLocaleTimeString(loc, {hour:'2-digit', minute:'2-digit'});
    if (el) el.textContent = date + '  ' + time;
    // Mobile clock (topbar): 24h format only — no AM/PM, no date
    if (el2) {
      const h = String(now.getHours()).padStart(2,'0');
      const m = String(now.getMinutes()).padStart(2,'0');
      el2.textContent = h + ':' + m;
    }
  }
  tick();
  setInterval(tick, 1000);
}

// ── Ticker: rendered server-side, no AJAX needed ─────────────────────────────
// (ticker text/styles are injected directly into HTML by Flask context processor)

// ── Auto-logout (10 min inactivity) ──────────────────────────────────────────
let _idleTimer, _warnTimer, _countTimer, _countSec = 60;
const IDLE_MS = 10 * 60 * 1000;
const WARN_MS = 60 * 1000;

function _resetIdle() {
  clearTimeout(_idleTimer);
  clearTimeout(_warnTimer);
  clearInterval(_countTimer);
  const modal = document.getElementById('autoLogoutModal');
  if (modal) { modal.style.display = 'none'; }
  _idleTimer = setTimeout(_showWarn, IDLE_MS - WARN_MS);
}

function _showWarn() {
  const modal = document.getElementById('autoLogoutModal');
  if (modal) {
    modal.style.display = 'flex';
    _countSec = 60;
    const el = document.getElementById('alCountdown');
    if (el) el.textContent = _countSec;
    _countTimer = setInterval(() => {
      _countSec--;
      if (el) el.textContent = _countSec;
      if (_countSec <= 0) {
        clearInterval(_countTimer);
        window.location.href = '/auth/logout?reason=timeout';
      }
    }, 1000);
  } else {
    window.location.href = '/auth/logout?reason=timeout';
  }
}

function keepSession() {
  fetch('/auth/keep-alive', {method:'POST'}).catch(()=>{});
  _resetIdle();
}

['mousemove','keydown','click','touchstart','scroll'].forEach(ev =>
  document.addEventListener(ev, _resetIdle, {passive:true})
);

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  _startClock();
  _resetIdle();
});

// Re-init clock after HTMX swaps content (clock element stays in DOM)
document.addEventListener('htmx:afterSettle', () => {
  _startClock();
});
