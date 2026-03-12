/**
 * ARS — Client-side i18n helper (minimal)
 * Language is now managed server-side via Flask session.
 * This file only handles: clock, ticker, RTL/LTR layout sync.
 */

// Read lang from <html> tag (set by Flask/Jinja)
const ARS_LANG = document.documentElement.lang || 'ar';

// ── Clock ─────────────────────────────────────────────────────────────────────
function _startClock() {
  const el = document.getElementById('topbarClock');
  if (!el) return;
  function tick() {
    const now  = new Date();
    const loc  = ARS_LANG === 'ar' ? 'ar-SA' : 'en-US';
    const date = now.toLocaleDateString(loc, {weekday:'short', month:'short', day:'numeric'});
    const time = now.toLocaleTimeString(loc, {hour:'2-digit', minute:'2-digit'});
    el.textContent = date + '  ' + time;
  }
  tick();
  setInterval(tick, 1000);
}

// ── Ticker ────────────────────────────────────────────────────────────────────
function loadTicker() {
  const tickerText  = document.getElementById('tickerText');
  const tickerTrack = document.getElementById('tickerTrack');
  const tickerWrap  = document.getElementById('tickerWrap');
  if (!tickerText || !tickerTrack) return;
  fetch('/admin/api/ticker?lang=' + ARS_LANG)
    .then(r => r.json())
    .then(data => {
      if (data.text) tickerText.textContent = data.text;
      if (data.fg)   tickerText.style.color = data.fg;
      if (data.font) tickerText.style.fontFamily = data.font;
      if (data.size) tickerText.style.fontSize = data.size + 'px';
      const len = tickerText.textContent.length;
      const dur = data.speed ? data.speed + 's' : Math.max(20, len * 0.22) + 's';
      const anim = ARS_LANG === 'ar' ? 'tickerScrollRTL' : 'tickerScrollLTR';
      tickerTrack.style.animationDuration = dur;
      tickerTrack.style.animationName = anim;
      if (tickerWrap && data.bg) {
        const hex = data.bg.replace('#','');
        const r = parseInt(hex.slice(0,2),16);
        const g = parseInt(hex.slice(2,4),16);
        const b = parseInt(hex.slice(4,6),16);
        const a = (data.opacity || 100) / 100;
        tickerWrap.style.background = `rgba(${r},${g},${b},${a})`;
      }
    }).catch(() => {});
}

// ── Auto-logout (10 min inactivity) ──────────────────────────────────────────
let _idleTimer, _warnTimer, _countTimer, _countSec = 60;
const IDLE_MS = 10 * 60 * 1000;
const WARN_MS = 60 * 1000;

function _resetIdle() {
  clearTimeout(_idleTimer);
  clearTimeout(_warnTimer);
  clearInterval(_countTimer);
  const modal = document.getElementById('idleModal');
  if (modal) { modal.style.display = 'none'; }
  _idleTimer = setTimeout(_showWarn, IDLE_MS - WARN_MS);
}

function _showWarn() {
  const modal = document.getElementById('idleModal');
  if (modal) {
    modal.style.display = 'flex';
    _countSec = 60;
    const el = document.getElementById('idleCount');
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

['mousemove','keydown','click','touchstart'].forEach(ev =>
  document.addEventListener(ev, _resetIdle, {passive:true})
);

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  _startClock();
  loadTicker();
  _resetIdle();
});
