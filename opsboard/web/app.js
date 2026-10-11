/* opsboard kiosk frontend. Vanilla JS, no deps. */
(function () {
  'use strict';
  const $ = (s) => document.querySelector(s);

  // ---------- token ----------
  let token = localStorage.getItem('board_token') || '';
  try {
    const u = new URL(location.href);
    if (u.searchParams.get('token')) {
      token = u.searchParams.get('token');
      localStorage.setItem('board_token', token);
      u.searchParams.delete('token');
      history.replaceState(null, '', u.pathname + (u.search || '') + u.hash);
    }
  } catch (e) {}

  const api = async (path, body, method) => {
    const r = await fetch('/api' + path, {
      method: method || (body === undefined ? 'GET' : 'POST'),
      headers: { 'Content-Type': 'application/json', 'X-Board-Token': token },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let j = null; try { j = await r.json(); } catch (e) {}
    if (!r.ok) throw new Error((j && (j.detail || j.error)) || ('HTTP ' + r.status));
    return j;
  };

  // ---------- state ----------
  const S = { tiles: {}, cards: {}, decks: [], activeDeck: 0, boardName: 'Ops Board', connected: false };

  // ---------- audio / speech ----------
  let audioCtx = null, soundOn = true, unlocked = false;
  const speechQ = []; let speaking = false;
  function unlockAudio() {
    unlocked = true;
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      if (audioCtx.state === 'suspended') audioCtx.resume();
      const o = audioCtx.createOscillator(), g = audioCtx.createGain();
      g.gain.value = 0.0001; o.connect(g); g.connect(audioCtx.destination); o.start(); o.stop(audioCtx.currentTime + 0.05);
    } catch (e) {}
    if ('speechSynthesis' in window) { try { const u = new SpeechSynthesisUtterance(''); speechSynthesis.speak(u); } catch (e) {} }
    $('#unlock').classList.add('hidden');
    pumpSpeech();
  }
  function beep(level) {
    if (!soundOn || !audioCtx) return;
    try {
      const now = audioCtx.currentTime;
      const notes = level === 'crit' ? [880, 660, 880] : level === 'warn' ? [660, 520] : [740];
      notes.forEach((f, i) => {
        const o = audioCtx.createOscillator(), g = audioCtx.createGain();
        o.type = 'square'; o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, now + i * 0.18);
        g.gain.exponentialRampToValueAtTime(0.25, now + i * 0.18 + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.18 + 0.16);
        o.connect(g); g.connect(audioCtx.destination);
        o.start(now + i * 0.18); o.stop(now + i * 0.18 + 0.17);
      });
    } catch (e) {}
  }
  function say(text) {
    if (!text) return;
    speechQ.push(String(text));
    pumpSpeech();
  }
  function pumpSpeech() {
    if (speaking || !unlocked || !soundOn || !speechQ.length || !('speechSynthesis' in window)) return;
    const text = speechQ.shift();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.0; u.lang = 'en-US';
    speaking = true;
    const done = () => { speaking = false; setTimeout(pumpSpeech, 150); };
    u.onend = done; u.onerror = done;
    setTimeout(() => { if (speaking) done(); }, 20000 + text.length * 80);
    speechSynthesis.speak(u);
  }
  $('#unlock').addEventListener('click', unlockAudio);
  $('#snd').addEventListener('click', () => {
    soundOn = !soundOn; $('#snd').textContent = soundOn ? '🔈' : '🔇'; $('#snd').classList.toggle('off', !soundOn);
    if (!soundOn && 'speechSynthesis' in window) speechSynthesis.cancel();
    toast(soundOn ? 'Sound on' : 'Sound muted');
  });

  // ---------- toast ----------
  let toastT;
  function toast(msg, err) {
    const t = $('#toast'); t.textContent = msg; t.className = err ? 'err' : ''; clearTimeout(toastT);
    toastT = setTimeout(() => t.classList.add('hidden'), 3500);
  }

  // ---------- clock ----------
  function tickClock() {
    const d = new Date();
    $('#clock').textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  setInterval(tickClock, 1000); tickClock();

  // ---------- tiles ----------
  const tileOrder = (t) => (t.kind === 'summary' || !t.kind) && !t.id.startsWith('cam_') ? 0 : t.kind === 'camera' ? 3 : t.kind === 'relay' ? 1 : 2;
  function age(ts) {
    if (!ts) return ''; const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
    return s < 60 ? s + 's ago' : s < 3600 ? Math.round(s / 60) + 'm ago' : Math.round(s / 3600) + 'h ago';
  }
  function renderTiles() {
    const wrap = $('#tiles');
    const list = Object.values(S.tiles).sort((a, b) => tileOrder(a) - tileOrder(b) || a.title.localeCompare(b.title));
    const seen = new Set();
    list.forEach((t) => {
      seen.add(t.id);
      let el = wrap.querySelector('[data-id="' + CSS.escape(t.id) + '"]');
      if (!el) {
        el = document.createElement('div'); el.dataset.id = t.id;
        el.addEventListener('click', () => openTile(t.id));
        wrap.appendChild(el);
      }
      const kind = t.kind || (t.id.startsWith('cam_') ? 'camera' : 'summary');
      el.className = 'tile ' + (t.status || 'unknown') + ' ' + kind;
      if (kind === 'camera') {
        const cam = t.cam || t.id.replace(/^cam_/, '');
        if (!el.querySelector('img')) {
          el.innerHTML = '<img alt=""><div class="cap"><span class="t"></span><span class="v"></span></div>';
          el.querySelector('img').dataset.cam = cam;
          refreshImg(el.querySelector('img'));
        }
        el.querySelector('.t').textContent = t.title;
        el.querySelector('.v').textContent = t.value;
      } else {
        el.innerHTML = '<div class="t"></div><div><div class="v"></div><div class="age"></div></div>';
        el.querySelector('.t').textContent = t.title;
        el.querySelector('.v').textContent = t.value || '—';
        el.querySelector('.age').textContent = age(t.updated);
      }
    });
    wrap.querySelectorAll('.tile').forEach((el) => { if (!seen.has(el.dataset.id)) el.remove(); });
    // reorder
    list.forEach((t) => { const el = wrap.querySelector('[data-id="' + CSS.escape(t.id) + '"]'); if (el) wrap.appendChild(el); });
    const crit = list.filter((t) => t.status === 'crit').length, warn = list.filter((t) => t.status === 'warn').length;
    $('#summary').textContent = crit ? crit + ' critical' + (warn ? ', ' + warn + ' warn' : '') : warn ? warn + ' warn' : 'all clear';
    renderButtons();
  }
  function refreshImg(img) {
    if (!img || !img.isConnected && img !== modalImg) return;
    img.src = '/api/cam/' + encodeURIComponent(img.dataset.cam) + '.jpg?t=' + Date.now();
  }
  let modalImg = null;
  setInterval(() => { document.querySelectorAll('.tile.camera img').forEach(refreshImg); if (modalImg) refreshImg(modalImg); }, 10000);
  setInterval(() => document.querySelectorAll('.tile .age').forEach((a) => { const id = a.closest('.tile').dataset.id; if (S.tiles[id]) a.textContent = age(S.tiles[id].updated); }), 15000);

  function openTile(id) {
    const t = S.tiles[id]; if (!t) return;
    $('#modal-title').textContent = t.title + ' — ' + (t.value || '');
    const body = $('#modal-body'); body.innerHTML = '';
    const kind = t.kind || (id.startsWith('cam_') ? 'camera' : '');
    if (kind === 'camera') {
      const img = document.createElement('img'); img.dataset.cam = t.cam || id.replace(/^cam_/, ''); modalImg = img; refreshImg(img); body.appendChild(img);
    }
    const d = document.createElement('div'); d.textContent = t.detail || '(no detail)'; body.appendChild(d);
    const kv = document.createElement('div'); kv.className = 'kv'; kv.textContent = 'id: ' + id + ' • status: ' + t.status + ' • updated ' + age(t.updated); body.appendChild(kv);
    $('#modal').classList.remove('hidden');
  }
  const closeModal = () => { $('#modal').classList.add('hidden'); modalImg = null; };
  $('#modal-close').addEventListener('click', closeModal);
  $('#modal').addEventListener('click', (e) => { if (e.target === $('#modal')) closeModal(); });

  // ---------- cards ----------
  const cardTimers = {};
  function addCard(c, fresh) {
    if (S.cards[c.id]) return;
    S.cards[c.id] = c;
    const wrap = $('#cards');
    const el = document.createElement('div'); el.className = 'card ' + c.level; el.dataset.id = c.id;
    el.innerHTML = '<div><div class="ct"></div><div class="cb"></div></div><button class="cx">✕</button>';
    el.querySelector('.ct').textContent = c.title; el.querySelector('.cb').textContent = c.body || '';
    if (!c.body) el.querySelector('.cb').remove();
    el.querySelector('.cx').addEventListener('click', () => removeCard(c.id));
    wrap.prepend(el);
    const remain = Math.max(1000, (c.created + c.ttl) * 1000 - Date.now());
    cardTimers[c.id] = setTimeout(() => removeCard(c.id), remain);
    if (fresh) { if (c.level !== 'info') beep(c.level); if (c.speak) say(c.speak_text || (c.title + '. ' + (c.body || ''))); }
  }
  function removeCard(id) {
    delete S.cards[id]; clearTimeout(cardTimers[id]);
    const el = $('#cards').querySelector('[data-id="' + CSS.escape(id) + '"]'); if (el) el.remove();
  }

  // ---------- deck ----------
  function renderDeck() {
    const tabs = $('#deck-tabs'); tabs.innerHTML = '';
    S.decks.forEach((d, i) => {
      const b = document.createElement('button'); b.className = 'tab' + (i === S.activeDeck ? ' active' : ''); b.textContent = d.name;
      b.addEventListener('click', () => { S.activeDeck = i; localStorage.setItem('board_deck', i); renderDeck(); });
      tabs.appendChild(b);
    });
    renderButtons(true);
  }
  function renderButtons(rebuild) {
    const wrap = $('#deck-buttons'); const deck = S.decks[S.activeDeck];
    if (!deck) { wrap.innerHTML = '<div style="color:var(--muted);padding:20px;grid-column:1/-1">No decks configured. See config.example.yaml.</div>'; return; }
    if (rebuild || wrap.children.length !== deck.buttons.length) {
      wrap.innerHTML = '';
      deck.buttons.forEach((btn) => wrap.appendChild(makeButton(btn)));
    }
    deck.buttons.forEach((btn, i) => {
      const el = wrap.children[i]; if (!el) return;
      el.classList.remove('ok', 'warn', 'crit', 'unknown');
      const st = el.querySelector('.st');
      if (btn.tile && S.tiles[btn.tile]) { const t = S.tiles[btn.tile]; el.classList.add(t.status); st.textContent = t.value; }
      else st.textContent = btn.confirm ? 'hold 1.5s' : '';
    });
  }
  function makeButton(btn) {
    const el = document.createElement('button'); el.className = 'btn' + (btn.confirm ? ' confirm' : '');
    el.innerHTML = '<div class="ring"></div><div class="ic"></div><div class="lb"></div><div class="st"></div>';
    el.querySelector('.ic').textContent = btn.icon || '▶'; el.querySelector('.lb').textContent = btn.label;
    let holdT = null, holdStart = 0, raf = null, fired = false;
    const run = async () => {
      if (el.classList.contains('busy')) return;
      el.classList.add('busy'); toast('Running: ' + btn.label);
      try {
        const r = await api('/action/' + encodeURIComponent(btn.action), {});
        if (r.ok) toast('✓ ' + btn.label + (typeof r.result === 'string' ? ': ' + r.result.slice(0, 80) : ''));
        else toast('✗ ' + btn.label + ': ' + (r.error || ('HTTP ' + r.status)), true);
      } catch (e) { toast('✗ ' + btn.label + ': ' + e.message, true); }
      el.classList.remove('busy');
    };
    const cancel = () => { clearTimeout(holdT); cancelAnimationFrame(raf); el.classList.remove('holding'); el.style.setProperty('--p', '0%'); };
    const down = (e) => {
      e.preventDefault(); fired = false;
      if (!btn.confirm) { run(); return; }
      holdStart = Date.now(); el.classList.add('holding');
      const step = () => { const p = Math.min(100, (Date.now() - holdStart) / 15); el.style.setProperty('--p', p + '%'); if (p < 100) raf = requestAnimationFrame(step); };
      raf = requestAnimationFrame(step);
      holdT = setTimeout(() => { fired = true; cancel(); beep('info'); run(); }, 1500);
    };
    const up = () => { if (btn.confirm && !fired && el.classList.contains('holding')) toast('Hold 1.5s to confirm'); cancel(); };
    el.addEventListener('pointerdown', down); el.addEventListener('pointerup', up);
    el.addEventListener('pointerleave', cancel); el.addEventListener('pointercancel', cancel);
    el.addEventListener('contextmenu', (e) => e.preventDefault());
    return el;
  }

  // ---------- push to talk ----------
  (function setupPTT() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const b = $('#ptt');
    if (!SR) return; // hidden by default
    b.classList.remove('hidden');
    let rec = null, transcript = '', active = false;
    const start = (e) => {
      e.preventDefault(); if (active) return; active = true; transcript = '';
      try {
        rec = new SR(); rec.continuous = true; rec.interimResults = true; rec.lang = 'en-US';
        rec.onresult = (ev) => { let t = ''; for (let i = 0; i < ev.results.length; i++) t += ev.results[i][0].transcript; transcript = t; b.querySelector('span').textContent = t.slice(-40) || 'Listening…'; };
        rec.onerror = (ev) => { toast('Mic: ' + ev.error, true); };
        rec.onend = () => { if (active) { active = false; b.classList.remove('listening'); b.querySelector('span').textContent = 'Hold to talk'; send(); } };
        rec.start(); b.classList.add('listening'); b.querySelector('span').textContent = 'Listening…';
      } catch (err) { active = false; toast('Mic unavailable: ' + err.message, true); }
    };
    const stop = () => { if (!active) return; active = false; b.classList.remove('listening'); b.querySelector('span').textContent = 'Hold to talk'; try { rec && rec.stop(); } catch (e) {} setTimeout(send, 400); };
    let sent = false;
    const send = async () => {
      if (sent) return; sent = true; setTimeout(() => (sent = false), 500);
      const t = transcript.trim(); if (!t) { toast('Nothing heard'); return; }
      try { await api('/ask', { text: t }); } catch (e) { toast('ask failed: ' + e.message, true); }
    };
    b.addEventListener('pointerdown', start); b.addEventListener('pointerup', stop); b.addEventListener('pointercancel', stop);
    b.addEventListener('contextmenu', (e) => e.preventDefault());
  })();

  // ---------- websocket ----------
  let ws = null, backoff = 1000, pingT = null;
  function setConn(on) {
    S.connected = on; const d = $('#conn'); d.className = 'dot ' + (on ? 'green' : 'red'); d.title = on ? 'connected' : 'disconnected';
  }
  function applyState(m) {
    S.boardName = m.board_name || 'Ops Board'; $('#boardname').textContent = S.boardName + (m.demo ? ' (demo)' : ''); document.title = S.boardName;
    S.tiles = {}; (m.tiles || []).forEach((t) => (S.tiles[t.id] = t));
    S.decks = m.decks || []; const saved = parseInt(localStorage.getItem('board_deck') || '0', 10); S.activeDeck = Math.min(saved || 0, Math.max(0, S.decks.length - 1));
    $('#tiles').innerHTML = '';
    Object.keys(S.cards).forEach(removeCard);
    renderTiles(); renderDeck();
    (m.cards || []).slice().reverse().forEach((c) => addCard(c, false));
  }
  function handle(m) {
    switch (m.type) {
      case 'state': applyState(m); break;
      case 'tile': { const fresh = S.tiles[m.tile.id]; S.tiles[m.tile.id] = m.tile; renderTiles();
        if (fresh && fresh.status !== m.tile.status) { const el = $('#tiles').querySelector('[data-id="' + CSS.escape(m.tile.id) + '"]'); if (el) { el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 900); } } break; }
      case 'tile_removed': delete S.tiles[m.id]; renderTiles(); break;
      case 'card': addCard(m.card, true); break;
      case 'card_removed': removeCard(m.id); break;
      case 'say': say(m.text); break;
      case 'ping': try { ws.send(JSON.stringify({ type: 'pong' })); } catch (e) {} break;
    }
  }
  function connect() {
    const proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
    try { ws = new WebSocket(proto + location.host + '/api/ws?token=' + encodeURIComponent(token)); } catch (e) { return retry(); }
    ws.onopen = () => { setConn(true); backoff = 1000; };
    ws.onmessage = (ev) => { try { handle(JSON.parse(ev.data)); } catch (e) { console.error(e); } };
    ws.onclose = (ev) => { setConn(false); if (ev.code === 4401) { toast('Bad token — open the board with ?token=…', true); backoff = 10000; } retry(); };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  }
  function retry() { clearTimeout(pingT); pingT = setTimeout(connect, backoff); backoff = Math.min(backoff * 1.7, 15000); }
  connect();
  // watchdog: if no message in 60s, force reconnect
  let lastMsg = Date.now();
  const _h = handle; handle = (m) => { lastMsg = Date.now(); _h(m); };
  setInterval(() => { if (S.connected && Date.now() - lastMsg > 60000) { try { ws.close(); } catch (e) {} } }, 10000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && (!ws || ws.readyState !== 1)) connect(); });
})();
