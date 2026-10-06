'use strict';
(()=>{
const MODELS=__MODELS__;
const BADGE=__BADGES__;
const RACE=__RACE__;
const REDUCED=matchMedia('(prefers-reduced-motion: reduce)').matches;
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const SPEEDS = [1, 5, 10, 25, 50, 100];
const VERDICT = { pass: '✓', partial: '◐', fail: '✕', mixed: '◒' };
const VWORD = { pass: 'pass', partial: 'partial', fail: 'fail', mixed: 'mixed' };
const R = { mode: 'toolsRec', speed: 10, t: 0, max: 1, playing: false, last: 0, lanes: [], feedKey: '', standKey: '', resultKey: '' };

function fmtClock(t) {
  const m = Math.floor(t / 60), s = t - m * 60;
  return String(m).padStart(2, '0') + ':' + s.toFixed(2).padStart(5, '0');
}
function fmtSec(t) { return t >= 100 ? t.toFixed(0) + ' s' : t.toFixed(1) + ' s'; }

function buildTabs() {
  $('#race-modes').innerHTML = Object.entries(RACE).map(([k, m]) =>
    `<button type="button" data-mode="${k}" aria-pressed="${k === R.mode}">${esc(m.label)}</button>`).join('');
  $('#race-speeds').innerHTML = SPEEDS.map(s =>
    `<button type="button" data-speed="${s}" aria-pressed="${s === R.speed}">×${s}</button>`).join('');
}

function setupMode(key, keepT) {
  R.mode = key;
  const mode = RACE[key];
  const N = mode.tasks.length;
  const lt = N > 15 ? 17 : 20;
  R.lanes = mode.lanes.map(l => {
    let acc = 0;
    const starts = [], ends = [];
    l.rows.forEach(r => { starts.push(acc); acc += r.s; ends.push(acc); });
    return { ...l, starts, ends, total: acc, shown: -1, el: null };
  });
  R.max = Math.max(...R.lanes.map(l => l.total));
  const x = i => ((i + 0.5) / N).toFixed(4);
  const head = `<div class="lane-head" aria-hidden="true"><div></div><div class="track">${mode.tasks.map((t, i) =>
    `<span class="st-label" style="--x:${x(i)}" title="${esc(t.id + ' ' + t.title)}">${esc(t.id.replace(/^(TC-|HA-)/, ''))}</span>`).join('')}</div><div></div></div>`;
  const lanes = R.lanes.map((l, li) => {
    const m = MODELS[l.key];
    const lights = l.rows.map((r, i) =>
      `<span class="lt${r.review ? ' rev-pending' : ''}" style="--x:${x(i)};--lt:${lt}px" data-lane="${li}" data-i="${i}" tabindex="0" aria-label="${esc(mode.tasks[i].id + ' ' + mode.tasks[i].title)}"></span>`).join('');
    return `<div class="lane" data-model="${l.key}" style="--c:${m.color}">
      <div class="lane-id"><img src="${BADGE[l.key]}" alt="${esc(m.name)}"><div><b>${esc(m.name)}</b><small class="st">On the grid</small></div></div>
      <div class="track"><div class="rail"></div><div class="rail-fill"></div><div class="finish" title="Finish"></div>${lights}
        <div class="runner-wrap"><span class="runner-tick"></span><img class="runner" src="${BADGE[l.key]}" alt=""></div></div>
      <div class="lane-score"><span class="pts">0<small></small></span><span class="tm">0.0 s</span><span class="place" hidden></span></div>
    </div>`;
  }).join('');
  $('#race-lanes').innerHTML = head + lanes;
  $('#race-lanes').querySelectorAll('.lane').forEach((el, i) => {
    const l = R.lanes[i];
    l.el = { root: el, st: el.querySelector('.st'), fill: el.querySelector('.rail-fill'), runner: el.querySelector('.runner'),
             tick: el.querySelector('.runner-tick'), lights: [...el.querySelectorAll('.lt')], pts: el.querySelector('.pts'),
             tm: el.querySelector('.tm'), place: el.querySelector('.place') };
  });
  $('#race-blurb').textContent = mode.blurb;
  $('#race-scrub').max = R.max.toFixed(2);
  $('#race-end').textContent = fmtClock(R.max);
  R.feedKey = R.standKey = R.resultKey = '';
  document.querySelectorAll('#race-modes button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === key)));
  setT(keepT ? R.max : 0);
}

function laneScore(l, done) {
  const mode = RACE[R.mode];
  let sum = 0;
  for (let i = 0; i < done; i++) sum += l.rows[i].p;
  if (mode.kind === 'tools') return { val: sum, text: String(sum), unit: '/30' };
  const v = done === l.rows.length ? l.score : sum / l.rows.length;
  return { val: v, text: v.toFixed(1), unit: '/100' };
}

function setT(t) {
  R.t = Math.max(0, Math.min(R.max, t));
  render(false);
}

function render(animate) {
  const t = R.t, mode = RACE[R.mode], N = mode.tasks.length;
  const finished = R.lanes.filter(l => l.total <= t).sort((a, b) => a.total - b.total);
  R.lanes.forEach(l => {
    let done = 0;
    while (done < N && l.ends[done] <= t) done++;
    const isDone = done === N;
    // runner position along the track (0..1)
    let pos;
    if (isDone) pos = 1;
    else {
      const prev = done === 0 ? 0 : (done - 0.5) / N;
      const target = (done + 0.5) / N;
      const frac = Math.min(1, (t - l.starts[done]) / Math.max(0.001, l.rows[done].s));
      pos = prev + (target - prev) * frac;
    }
    const pct = (pos * 100).toFixed(3) + '%';
    l.el.runner.style.left = pct;
    l.el.tick.style.left = pct;
    l.el.fill.style.width = pct;
    l.el.runner.classList.toggle('working', !isDone && t > 0 && R.playing);
    l.el.runner.classList.toggle('finished', isDone);
    // lights
    if (done !== l.shown) {
      l.el.lights.forEach((el, i) => {
        const r = l.rows[i];
        const lit = i < done;
        el.className = 'lt' + (lit ? ' ' + r.st : '') + (lit && r.review ? ' rev' : '') + (i === done && !isDone && t > 0 ? ' active' : '');
        el.textContent = lit ? VERDICT[r.st] : '';
        if (animate && lit && i >= l.shown && l.shown >= 0 && !REDUCED) { void el.offsetWidth; el.classList.add('pop'); }
      });
      l.shown = done;
    } else if (!isDone && t > 0) {
      l.el.lights[done].classList.add('active');
    }
    const sc = laneScore(l, done);
    l.el.pts.innerHTML = esc(sc.text) + '<small>' + sc.unit + '</small>';
    l.el.tm.textContent = isDone ? fmtSec(l.total) : fmtSec(Math.min(t, l.total));
    if (isDone) {
      const place = finished.indexOf(l) + 1;
      l.el.st.textContent = `Finished · ${l.total.toFixed(2)} s`;
      l.el.st.className = 'st done';
      l.el.place.hidden = false;
      l.el.place.className = 'place' + (place <= 3 ? ' p' + place : '');
      l.el.place.textContent = ['', '1ST', '2ND', '3RD'][place] || place + 'TH';
    } else if (t > 0) {
      const task = mode.tasks[done];
      l.el.st.textContent = `${task.id} · ${task.title}`;
      l.el.st.className = 'st live';
      l.el.place.hidden = true;
    } else {
      l.el.st.textContent = 'On the grid';
      l.el.st.className = 'st';
      l.el.place.hidden = true;
    }
    l._done = done; l._score = sc;
  });
  $('#race-clock').textContent = fmtClock(t);
  $('#race-scrub').value = t.toFixed(2);
  $('#race-clock-sub').textContent = `replay speed ×${R.speed} · ${finished.length}/${R.lanes.length} finished`;
  renderFeed(animate);
  renderStandings();
  renderResult();
}

function renderFeed(animate) {
  const mode = RACE[R.mode], t = R.t;
  const ev = [];
  R.lanes.forEach(l => { for (let i = 0; i < l._done; i++) ev.push({ l, i, at: l.ends[i] }); });
  ev.sort((a, b) => b.at - a.at);
  const top = ev.slice(0, 6);
  const key = R.mode + ':' + top.map(e => e.l.key + e.i).join(',');
  if (key === R.feedKey) return;
  const prevFirst = R.feedKey.split(':')[1]?.split(',')[0];
  R.feedKey = key;
  if (!top.length) { $('#race-feed').innerHTML = '<li><span class="t">—</span><span></span><span class="msg">Press play. Results appear here as each station is cleared.</span></li>'; return; }
  $('#race-feed').innerHTML = top.map((e, idx) => {
    const r = e.l.rows[e.i], task = mode.tasks[e.i], m = MODELS[e.l.key];
    const isNew = animate && idx === 0 && (e.l.key + e.i) !== prevFirst;
    return `<li class="${isNew ? 'new' : ''}"><span class="t">${fmtClock(e.at)}</span><img src="${BADGE[e.l.key]}" alt=""><span class="msg"><b>${esc(m.short)}</b> <span class="v ${r.st}">${VERDICT[r.st]} ${VWORD[r.st]}</span> ${esc(task.id)} ${esc(task.title)} · ${fmtSec(r.s)}</span></li>`;
  }).join('');
}

function renderStandings() {
  const order = R.lanes.slice().sort((a, b) => (b._score.val - a._score.val) || (b._done - a._done) || (a.total - b.total));
  const key = order.map(l => l.key + l._score.text + l._done).join('|');
  if (key === R.standKey) return;
  R.standKey = key;
  const N = RACE[R.mode].tasks.length;
  $('#race-standings').innerHTML = order.map((l, i) =>
    `<li><span class="r">${i + 1}</span><img src="${BADGE[l.key]}" alt=""><span>${esc(MODELS[l.key].short)}</span><span class="s">${l._score.text}<small>${l._score.unit} · ${l._done}/${N}</small></span></li>`).join('');
}

function renderResult() {
  const box = $('#race-result');
  const done = R.t >= R.max - 1e-6;
  const key = R.mode + done;
  if (key === R.resultKey) return;
  R.resultKey = key;
  if (!done) { box.innerHTML = ''; box.hidden = true; return; }
  box.hidden = false;
  const byTime = R.lanes.slice().sort((a, b) => a.total - b.total).slice(0, 3);
  const byPts = R.lanes.slice().sort((a, b) => (b._score.val - a._score.val) || (a.total - b.total)).slice(0, 3);
  const pod = (title, list, val) => `<div class="podium"><h4>${title}</h4><ol>${list.map((l, i) =>
    `<li><img src="${BADGE[l.key]}" alt=""><span>${esc(MODELS[l.key].short)}</span><b>${val(l)}</b><div class="step">${i + 1}</div></li>`).join('')}</ol></div>`;
  box.innerHTML = pod('First across the line', byTime, l => l.total.toFixed(2) + ' s') +
                  pod('Most points', byPts, l => l._score.text + l._score.unit);
}

function frame(ts) {
  if (!R.playing) return;
  const dt = Math.min(0.1, (ts - R.last) / 1000);
  R.last = ts;
  R.t = Math.min(R.max, R.t + dt * R.speed);
  render(true);
  if (R.t >= R.max) { pause(); return; }
  requestAnimationFrame(frame);
}
function play() {
  if (R.playing) return;
  if (R.t >= R.max) R.t = 0;
  R.playing = true; R.last = performance.now();
  $('#race-play').textContent = '❚❚ Pause';
  requestAnimationFrame(frame);
}
function pause() {
  R.playing = false;
  $('#race-play').textContent = R.t >= R.max ? '▶ Replay' : '▶ Play';
  render(false);
}
function setSpeed(s) {
  R.speed = s;
  document.querySelectorAll('#race-speeds button').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.speed === s)));
  render(false);
}

buildTabs();
setupMode('toolsRec', true);   // at rest: the finished board, so the page reads without playing
pause();

$('#race-play').addEventListener('click', () => R.playing ? pause() : play());
$('#race-finish').addEventListener('click', () => { pause(); setT(R.max); });
$('#race-restart').addEventListener('click', () => { pause(); setT(0); play(); });
$('#race-modes').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  pause(); setupMode(b.dataset.mode, false); setSpeed(RACE[b.dataset.mode].speed); play();
});
$('#race-speeds').addEventListener('click', e => { const b = e.target.closest('button'); if (b) setSpeed(+b.dataset.speed); });
$('#race-scrub').addEventListener('input', e => { if (R.playing) pause(); setT(+e.target.value); });

// Light tooltips (hover and keyboard focus)
const rtip = $('#rtip');
function showTip(el) {
  const l = R.lanes[+el.dataset.lane], i = +el.dataset.i, r = l.rows[i], task = RACE[R.mode].tasks[i];
  const lit = i < l._done;
  const pts = RACE[R.mode].kind === 'tools' ? `${r.p} / 2 pts` : `score ${r.p}`;
  rtip.innerHTML = `<b>${esc(MODELS[l.key].short)} · ${esc(task.id)} ${esc(task.title)}</b>` +
    (lit ? `<div class="meta">${VERDICT[r.st]} ${r.st} · ${pts} · ${r.s.toFixed(2)} s${r.c != null ? ' · ' + r.c + ' tool calls' : ''}</div><p>${esc(r.sum || '')}</p>${r.review ? `<p style="color:var(--cyan);margin-top:6px">${esc(r.review)}</p>` : ''}`
         : `<div class="meta">not reached yet</div>`);
  rtip.hidden = false;
  const b = el.getBoundingClientRect();
  const w = rtip.offsetWidth, h = rtip.offsetHeight;
  let x = Math.min(window.innerWidth - w - 8, Math.max(8, b.left + b.width / 2 - w / 2));
  let y = b.top - h - 10; if (y < 8) y = b.bottom + 10;
  rtip.style.left = x + 'px'; rtip.style.top = y + 'px';
}
const lanesEl = $('#race-lanes');
lanesEl.addEventListener('pointerover', e => { const el = e.target.closest('.lt'); if (el) showTip(el); });
lanesEl.addEventListener('pointerout', e => { if (e.target.closest('.lt')) rtip.hidden = true; });
lanesEl.addEventListener('focusin', e => { const el = e.target.closest('.lt'); if (el) showTip(el); });
lanesEl.addEventListener('focusout', () => { rtip.hidden = true; });
window.addEventListener('scroll', () => { rtip.hidden = true; }, { passive: true });

// Start the race the first time it scrolls into view
if (!REDUCED && 'IntersectionObserver' in window) {
  const io = new IntersectionObserver(entries => {
    if (entries.some(e => e.isIntersecting)) { io.disconnect(); setT(0); play(); }
  }, { threshold: 0.35 });
  io.observe($('#race-box'));
}

window.classicRaceState=()=>({mode:R.mode,time:R.t,duration:R.max,playing:R.playing,speed:R.speed,lanes:R.lanes.map(l=>({id:l.key,total:l.rows.length,done:l._done,score:l._score.text}))});
window.classicRaceResize=()=>{render(false)};

})();
