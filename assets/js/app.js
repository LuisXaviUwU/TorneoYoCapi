/**
 * app.js — Lógica del dashboard del torneo Fortnite
 * WebSocket en tiempo real + UI dinámica
 */

const API = 'http://localhost:8000/api';
const WS_URL = 'ws://localhost:8000/ws';

// ─────────────────────────────────────────────────────────
// Estado global
// ─────────────────────────────────────────────────────────
const state = {
  ws: null,
  reconnectTimer: null,
  standings: [],
  players: [],
  activeMatch: null,
  killFeed: [],
  captureRunning: false,
  tournamentName: 'Torneo Privado Fortnite',
};

// ─────────────────────────────────────────────────────────
// WebSocket
// ─────────────────────────────────────────────────────────
function connectWS() {
  if (state.ws) {
    state.ws.close();
    state.ws = null;
  }

  const ws = new WebSocket(WS_URL);
  state.ws = ws;

  ws.onopen = () => {
    console.log('[WS] Conectado');
    updateConnectionStatus(true);
    clearTimeout(state.reconnectTimer);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleWSMessage(msg);
    } catch (e) {
      console.error('[WS] Error parseando mensaje:', e);
    }
  };

  ws.onclose = () => {
    updateConnectionStatus(false);
    state.reconnectTimer = setTimeout(connectWS, 3000);
  };

  ws.onerror = (e) => {
    console.error('[WS] Error:', e);
  };
}

function handleWSMessage(msg) {
  switch (msg.type) {
    case 'init':
      state.tournamentName = msg.data.tournament_name;
      state.activeMatch = msg.data.active_match;
      state.standings = msg.data.standings;
      document.getElementById('tournament-name-display').textContent = state.tournamentName;
      renderStandings(state.standings);
      updateMatchStatus();
      break;

    case 'elimination':
      addKillFeedEvent(msg.data);
      updateStat('stat-kills', msg.data.kills_snapshot ? Object.values(msg.data.kills_snapshot).reduce((a, b) => a + b, 0) : null, true);
      showToast(`☠️ ${msg.data.eliminator || '🌪️ Storm'} → ${msg.data.eliminated}`, 'info');
      break;

    case 'match_started':
      state.activeMatch = msg.data;
      updateMatchStatus();
      clearKillFeed();
      showToast(`🎮 Partida #${msg.data.match_number} iniciada`, 'success');
      break;

    case 'match_ended':
      state.activeMatch = null;
      state.standings = msg.data.standings;
      renderStandings(state.standings);
      updateMatchStatus();
      showToast(`🏁 Partida finalizada`, 'info');
      break;

    case 'standings_update':
      state.standings = msg.data.standings;
      renderStandings(state.standings);
      break;

    case 'elimination_corrected':
    case 'elimination_deleted':
      // Recargar feed si es necesario
      if (state.activeMatch) {
        loadMatchEliminations(state.activeMatch.id);
      }
      break;
  }
}

function updateConnectionStatus(connected) {
  const indicator = document.getElementById('ws-status');
  if (indicator) {
    indicator.textContent = connected ? '🟢 En vivo' : '🔴 Sin conexión';
    indicator.className = connected ? 'text-green' : 'text-red';
  }
}

// ─────────────────────────────────────────────────────────
// Render Standings / Leaderboard
// ─────────────────────────────────────────────────────────
let _prevRanks = {};

function renderStandings(standings) {
  const body = document.getElementById('leaderboard-body');
  if (!body) return;

  // Calcular kills de la partida actual
  const liveKills = {};
  state.killFeed.forEach(ev => {
    if (ev.eliminator) {
      liveKills[ev.eliminator] = (liveKills[ev.eliminator] || 0) + 1;
    }
  });

  // Guardar posiciones previas
  const prevRanks = { ..._prevRanks };
  const newRanks = {};
  standings.forEach((p, i) => { newRanks[p.username] = i; });

  body.innerHTML = '';

  if (standings.length === 0) {
    body.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🎮</div>
        <p>No hay jugadores registrados.<br>Agrégalos en el panel de jugadores.</p>
      </div>`;
    return;
  }

  standings.forEach((player, index) => {
    const rank = index + 1;
    const prevRank = prevRanks[player.username] !== undefined ? prevRanks[player.username] + 1 : rank;
    const moved = prevRank !== rank ? (rank < prevRank ? 'moved-up' : 'moved-down') : '';

    const rankClass = rank === 1 ? 'gold' : rank === 2 ? 'silver' : rank === 3 ? 'bronze' : 'normal';
    const rankLabel = rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : rank;

    const avatarChar = (player.display_name || player.username).charAt(0).toUpperCase();
    const matchKills = liveKills[player.username] || 0;
    
    // Sumar stats en vivo
    const displayKills = player.total_kills + matchKills;
    // Asumimos 1 punto por kill por defecto (se actualizará con config si es distinto)
    const killPoints = window.tournamentConfig ? window.tournamentConfig.kill_points : 1;
    const displayPts = player.total_points + (matchKills * killPoints);

    const row = document.createElement('div');
    row.className = `lb-row rank-${rank} ${moved}`;
    row.dataset.username = player.username;
    row.innerHTML = `
      <div class="lb-rank">
        <div class="rank-badge ${rankClass}">${rankLabel}</div>
      </div>
      <div class="lb-player">
        <div class="player-avatar" style="${getAvatarStyle(rank)}">${avatarChar}</div>
        <div>
          <div class="player-name">${escapeHtml(player.display_name || player.username)}</div>
          <div class="player-tag text-muted" style="font-size:11px">@${escapeHtml(player.username)}</div>
        </div>
      </div>
      <div class="lb-kills" title="Kills totales">${displayKills}</div>
      <div class="lb-pts-match text-secondary" title="Partidas jugadas">${player.matches_played}P</div>
      <div class="lb-pts-total">${displayPts}<span style="font-size:11px;color:var(--text-muted)">pts</span></div>
    `;
    body.appendChild(row);
  });

  _prevRanks = newRanks;

  // Actualizar stats
  updateStat('stat-players', standings.length);
  updateStat('stat-total-kills', standings.reduce((a, p) => a + p.total_kills, 0));
}

function getAvatarStyle(rank) {
  if (rank === 1) return 'background: var(--gold-gradient); color: #000;';
  if (rank === 2) return 'background: linear-gradient(135deg, #9e9e9e, #c0c0c0); color: #000;';
  if (rank === 3) return 'background: linear-gradient(135deg, #8d6e63, #cd7f32); color: #000;';
  return '';
}

// ─────────────────────────────────────────────────────────
// Kill Feed
// ─────────────────────────────────────────────────────────
function addKillFeedEvent(data) {
  state.killFeed.unshift(data);
  if (state.killFeed.length > 50) state.killFeed.pop();

  const list = document.getElementById('kill-feed-list');
  if (!list) return;

  // Quitar empty state
  const empty = list.querySelector('.empty-state');
  if (empty) empty.remove();

  const el = createKillEventEl(data);
  list.insertBefore(el, list.firstChild);

  // Limitar a 30 en el DOM
  while (list.children.length > 30) {
    list.removeChild(list.lastChild);
  }

  // Actualizar contador
  const counter = document.getElementById('kill-feed-count');
  if (counter) counter.textContent = state.killFeed.length;
}

function createKillEventEl(data) {
  const div = document.createElement('div');
  const isStorm = data.is_storm || !data.eliminator;
  const isManual = data.is_manual;

  div.className = `kill-event${isStorm ? ' storm' : ''}${isManual ? ' manual' : ''}`;
  div.dataset.id = data.id;

  const icon = isStorm ? '🌪️' : '☠️';
  const elimText = isStorm
    ? `<div class="kill-eliminator" style="color:var(--accent-purple)">Tormenta</div>`
    : `<div class="kill-eliminator">${escapeHtml(data.eliminator)}</div>`;

  const conf = data.confidence < 1 ? `<span class="kill-conf">${Math.round(data.confidence * 100)}%</span>` : '';
  const time = formatTime(data.timestamp);

  div.innerHTML = `
    <div class="kill-icon">${icon}</div>
    <div class="kill-text">
      ${elimText}
      <div class="kill-eliminated">
        <span class="arrow">▸</span>
        <span class="victim">${escapeHtml(data.eliminated)}</span>
      </div>
    </div>
    ${conf}
    <div class="kill-time">${time}</div>
  `;

  // Botón eliminar en hover
  div.title = `Raw: ${data.raw_text || '—'}`;

  return div;
}

function createKillEventEl(data) {
  const div = document.createElement('div');
  const isStorm = data.is_storm || !data.eliminator;
  const isManual = data.is_manual;

  div.className = `kill-event${isStorm ? ' storm' : ''}${isManual ? ' manual' : ''}`;
  div.dataset.id = data.id;

  const icon = isStorm ? 'ST' : 'KO';
  const elimText = isStorm
    ? `<div class="kill-eliminator" style="color:var(--accent-purple)">Tormenta</div>`
    : `<div class="kill-eliminator">${escapeHtml(data.eliminator)}</div>`;
  const detailText = data.display_text
    ? `<div class="kill-eliminated">${escapeHtml(data.display_text)}</div>`
    : `<div class="kill-eliminated"><span class="arrow">></span><span class="victim">${escapeHtml(data.eliminated)}</span></div>`;
  const conf = data.confidence < 1 ? `<span class="kill-conf">${Math.round(data.confidence * 100)}%</span>` : '';
  const time = formatTime(data.timestamp);

  div.innerHTML = `
    <div class="kill-icon">${icon}</div>
    <div class="kill-text">
      ${elimText}
      ${detailText}
    </div>
    ${conf}
    <div class="kill-time">${time}</div>
  `;
  div.title = `Raw: ${data.raw_text || data.display_text || '-'}`;

  return div;
}

function clearKillFeed() {
  state.killFeed = [];
  const list = document.getElementById('kill-feed-list');
  if (list) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🎯</div>
        <p>El kill feed aparecerá aquí<br>cuando inicie la captura</p>
      </div>`;
  }
  const counter = document.getElementById('kill-feed-count');
  if (counter) counter.textContent = '0';
}

async function loadMatchEliminations(matchId) {
  try {
    const res = await fetch(`${API}/matches/${matchId}/eliminations`);
    const data = await res.json();
    state.killFeed = data.reverse();

    const list = document.getElementById('kill-feed-list');
    if (!list) return;
    list.innerHTML = '';

    if (data.length === 0) {
      list.innerHTML = `<div class="empty-state"><div class="empty-icon">🎯</div><p>Sin eliminaciones aún</p></div>`;
      return;
    }

    data.forEach(ev => {
      const el = createKillEventEl(ev);
      list.appendChild(el);
    });
  } catch (e) {
    console.error('Error cargando eliminaciones:', e);
  }
}

// ─────────────────────────────────────────────────────────
// Match Control
// ─────────────────────────────────────────────────────────
function updateMatchStatus() {
  const badge = document.getElementById('match-badge');
  const btnStart = document.getElementById('btn-start-match');
  const btnEnd = document.getElementById('btn-end-match');
  const btnPositions = document.getElementById('btn-set-positions');
  const btnCapture = document.getElementById('btn-toggle-capture');

  if (state.activeMatch) {
    if (badge) {
      badge.textContent = `PARTIDA #${state.activeMatch.match_number} EN CURSO`;
      badge.className = 'match-badge active';
    }
    if (btnStart) btnStart.classList.add('hidden');
    if (btnEnd) btnEnd.classList.remove('hidden');
    if (btnPositions) btnPositions.classList.remove('hidden');
    if (btnCapture) btnCapture.classList.remove('hidden');

    document.getElementById('stat-match').textContent = `#${state.activeMatch.match_number}`;
  } else {
    if (badge) {
      badge.textContent = 'SIN PARTIDA ACTIVA';
      badge.className = 'match-badge idle';
    }
    if (btnStart) btnStart.classList.remove('hidden');
    if (btnEnd) btnEnd.classList.add('hidden');
    if (btnPositions) btnPositions.classList.add('hidden');
    if (btnCapture) btnCapture.classList.add('hidden');

    document.getElementById('stat-match').textContent = '—';
  }
}

async function startMatch() {
  try {
    const res = await fetch(`${API}/matches`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail, 'error');
      return;
    }
    const data = await res.json();
    state.activeMatch = data;
    clearKillFeed();
    updateMatchStatus();
  } catch (e) {
    showToast('Error al iniciar partida', 'error');
  }
}

async function endMatch() {
  if (!state.activeMatch) return;
  if (!confirm('¿Terminar la partida actual? Asegúrate de haber registrado todas las posiciones.')) return;

  try {
    await fetch(`${API}/matches/${state.activeMatch.id}/end`, { method: 'PUT' });
    state.activeMatch = null;
    updateMatchStatus();
    await loadStandings();
  } catch (e) {
    showToast('Error al terminar partida', 'error');
  }
}

async function toggleCapture() {
  try {
    const statusRes = await fetch(`${API}/capture/status`);
    const status = await statusRes.json();

    if (status.running) {
      await fetch(`${API}/capture/stop`, { method: 'POST' });
      state.captureRunning = false;
      showToast('⏹ Captura detenida', 'warning');
    } else {
      const res = await fetch(`${API}/capture/start`, { method: 'POST' });
      if (!res.ok) {
        const err = await res.json();
        showToast('Error: ' + err.detail, 'error');
        return;
      }
      state.captureRunning = true;
      showToast('▶ Captura iniciada', 'success');
    }
    updateCaptureIndicator(state.captureRunning);
  } catch (e) {
    showToast('Error de conexión con el servidor', 'error');
  }
}

function updateCaptureIndicator(running) {
  const indicator = document.getElementById('capture-indicator');
  const btn = document.getElementById('btn-toggle-capture');
  if (indicator) indicator.className = running ? 'active' : '';
  if (btn) btn.textContent = running ? '⏹ Detener Captura' : '▶ Iniciar Captura';
}

// ─────────────────────────────────────────────────────────
// Players
// ─────────────────────────────────────────────────────────
async function loadPlayers() {
  try {
    const res = await fetch(`${API}/players`);
    state.players = await res.json();
    updateStat('stat-players', state.players.length);
    renderPlayerList();
    updateManualSelects();
  } catch (e) {
    console.error('Error cargando jugadores:', e);
  }
}

function renderPlayerList() {
  const list = document.getElementById('modal-player-list');
  if (!list) return;

  list.innerHTML = '';
  if (state.players.length === 0) {
    list.innerHTML = '<p class="text-muted" style="text-align:center;padding:20px">No hay jugadores registrados</p>';
    return;
  }

  state.players.forEach(p => {
    const item = document.createElement('div');
    item.className = 'player-list-item';
    item.innerHTML = `
      <div class="player-avatar" style="width:30px;height:30px;font-size:12px">${p.display_name.charAt(0).toUpperCase()}</div>
      <span class="player-name">${escapeHtml(p.display_name)}</span>
      <span class="text-muted" style="font-size:12px">@${escapeHtml(p.username)}</span>
      <button class="btn btn-danger btn-sm btn-icon" onclick="deletePlayer(${p.id})" title="Eliminar">✕</button>
    `;
    list.appendChild(item);
  });
}

async function addPlayer() {
  const usernameInput = document.getElementById('input-username');
  const displayInput = document.getElementById('input-display');
  const username = usernameInput.value.trim();
  const display = displayInput.value.trim();

  if (!username) { showToast('El username es requerido', 'error'); return; }

  try {
    const res = await fetch(`${API}/players`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, display_name: display || null })
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail, 'error');
      return;
    }

    usernameInput.value = '';
    displayInput.value = '';
    await loadPlayers();
    showToast(`✓ Jugador "${username}" agregado`, 'success');
  } catch (e) {
    showToast('Error agregando jugador', 'error');
  }
}

async function deletePlayer(id) {
  if (!confirm('¿Eliminar este jugador del torneo?')) return;
  try {
    await fetch(`${API}/players/${id}`, { method: 'DELETE' });
    await loadPlayers();
    showToast('Jugador eliminado', 'info');
  } catch (e) {
    showToast('Error eliminando jugador', 'error');
  }
}

function updateManualSelects() {
  const selects = ['manual-eliminator', 'manual-eliminated'];
  selects.forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="">— Seleccionar —</option>';
    state.players.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.username;
      opt.textContent = `${p.display_name} (@${p.username})`;
      sel.appendChild(opt);
    });
    if (current) sel.value = current;
  });
}

// ─────────────────────────────────────────────────────────
// Manual Elimination Entry
// ─────────────────────────────────────────────────────────
async function addManualElimination() {
  const eliminator = document.getElementById('manual-eliminator').value;
  const eliminated = document.getElementById('manual-eliminated').value;

  if (!eliminated) { showToast('Debes seleccionar al eliminado', 'error'); return; }
  if (!state.activeMatch) { showToast('No hay partida activa', 'error'); return; }

  try {
    const res = await fetch(`${API}/eliminations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        eliminator: eliminator || null,
        eliminated,
      })
    });

    if (!res.ok) { showToast('Error al agregar eliminación', 'error'); return; }
    showToast('✓ Eliminación registrada', 'success');

    document.getElementById('manual-eliminator').value = '';
    document.getElementById('manual-eliminated').value = '';
  } catch (e) {
    showToast('Error de conexión', 'error');
  }
}

// ─────────────────────────────────────────────────────────
// Set Positions Modal
// ─────────────────────────────────────────────────────────
function openPositionsModal() {
  renderPositionsForm();
  openModal('modal-positions');
}

function renderPositionsForm() {
  const list = document.getElementById('positions-list');
  if (!list) return;

  list.innerHTML = '';
  state.players.forEach((p, i) => {
    const item = document.createElement('div');
    item.className = 'position-item';
    item.innerHTML = `
      <span class="position-num">#<input 
        type="number" 
        id="pos-${p.id}"
        min="1" max="100" 
        placeholder="—"
        style="width:40px;background:none;border:none;color:var(--accent-gold);font-family:'Rajdhani',sans-serif;font-weight:700;font-size:15px;outline:none"
      /></span>
      <span class="player-name">${escapeHtml(p.display_name)}</span>
      <span class="text-muted" style="font-size:11px">@${escapeHtml(p.username)}</span>
    `;
    list.appendChild(item);
  });
}

async function savePositions() {
  if (!state.activeMatch) return;

  const promises = [];
  state.players.forEach(p => {
    const input = document.getElementById(`pos-${p.id}`);
    if (!input || !input.value) return;
    const position = parseInt(input.value);
    if (isNaN(position) || position < 1) return;

    promises.push(
      fetch(`${API}/matches/${state.activeMatch.id}/results`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_id: p.id, position })
      })
    );
  });

  try {
    await Promise.all(promises);
    closeModal('modal-positions');
    await loadStandings();
    showToast('✓ Posiciones guardadas', 'success');
  } catch (e) {
    showToast('Error guardando posiciones', 'error');
  }
}

// ─────────────────────────────────────────────────────────
// Standings
// ─────────────────────────────────────────────────────────
async function loadStandings() {
  try {
    const res = await fetch(`${API}/standings`);
    state.standings = await res.json();
    renderStandings(state.standings);
  } catch (e) {
    console.error('Error cargando standings:', e);
  }
}

// ─────────────────────────────────────────────────────────
// Stats Bar
// ─────────────────────────────────────────────────────────
function updateStat(id, value, animate = false) {
  if (value === null || value === undefined) return;
  const el = document.getElementById(id);
  if (!el) return;
  if (animate) {
    el.style.transform = 'scale(1.15)';
    setTimeout(() => { el.style.transform = ''; }, 300);
  }
  el.textContent = value;
  el.style.transition = 'transform 0.3s ease';
}

// ─────────────────────────────────────────────────────────
// Modals
// ─────────────────────────────────────────────────────────
function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('open');
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('open');
}

// ─────────────────────────────────────────────────────────
// Toast Notifications
// ─────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ️'}</span><span class="toast-text">${escapeHtml(msg)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'toastIn 0.3s ease reverse';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ─────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatTime(isoString) {
  if (!isoString) return '';
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return ''; }
}

// ─────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  connectWS();
  await loadPlayers();
  await loadStandings();

  // Actualizar cada 30s si el WS falla
  setInterval(async () => {
    await loadStandings();
  }, 30000);
});
