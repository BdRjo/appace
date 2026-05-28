/**
 * ARS — Client-side i18n helper (minimal)
 * Language is now managed server-side via Flask session.
 * This file only handles: clock, ticker, RTL/LTR layout sync.
 */

// Read lang from <html> tag (set by Flask/Jinja)
const ARS_LANG = document.documentElement.lang || 'ar';

// ── Clock — drives both desktop and mobile elements ───────────────────────────
function _startClock() {
  const el  = document.getElementById('topbarClock');
  const el2 = document.getElementById('topbarClockMobile');
  if (!el && !el2) return;
  function tick() {
    const now  = new Date();
    const loc  = ARS_LANG === 'ar' ? 'ar-SA' : 'en-US';
    const date = now.toLocaleDateString(loc, {weekday:'short', month:'short', day:'numeric'});
    const time = now.toLocaleTimeString(loc, {hour:'2-digit', minute:'2-digit'});
    const full = date + '  ' + time;
    const short = now.toLocaleDateString(loc, {month:'short', day:'numeric'}) + '\n' + time;
    if (el)  el.textContent  = full;
    if (el2) el2.textContent = short;
  }
  tick();
  setInterval(tick, 1000);
}

// ── Ticker ────────────────────────────────────────────────────────────────────
function _applyTicker(data) {
  const anim = ARS_LANG === 'ar' ? 'tickerScrollRTL' : 'tickerScrollLTR';
  [
    { t: 'tickerText',       r: 'tickerTrack' },
    { t: 'tickerTextMobile', r: 'tickerTrackMobile' },
  ].forEach(({t, r}) => {
    const text  = document.getElementById(t);
    const track = document.getElementById(r);
    if (!text || !track) return;
    if (data.text) text.textContent = data.text;
    if (data.fg)   text.style.color = data.fg;
    if (data.font) text.style.fontFamily = data.font;
    if (data.size) text.style.fontSize = data.size + 'px';
    const dur = data.speed ? data.speed + 's' : Math.max(20, text.textContent.length * 0.22) + 's';
    track.style.animationDuration = dur;
    track.style.animationName = anim;
  });
}

function loadTicker() {
  if (!document.getElementById('tickerText')) return;
  // Apply cached data instantly (no flicker on navigation)
  const cached = sessionStorage.getItem('ars_ticker_' + ARS_LANG);
  if (cached) { try { _applyTicker(JSON.parse(cached)); } catch(e){} }
  // Fetch fresh data and update cache
  fetch('/admin/api/ticker?lang=' + ARS_LANG)
    .then(r => r.json())
    .then(data => {
      sessionStorage.setItem('ars_ticker_' + ARS_LANG, JSON.stringify(data));
      _applyTicker(data);
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
