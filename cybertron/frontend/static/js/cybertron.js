
// ─── Pixel Art Engine ───────────────────────────────────────────────────────
function plot(ctx, x, y, color, alpha) {
  ctx.fillStyle = color;
  ctx.globalAlpha = alpha === undefined ? 1 : alpha;
  ctx.fillRect(x, y, 1, 1);
  ctx.globalAlpha = 1;
}

function rampColor(t) {
  const stops = [
    [0.00, [255, 215, 0]], [0.35, [255, 191, 0]],
    [0.65, [77, 208, 225]], [1.00, [40, 40, 90]]
  ];
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, c0] = stops[i]; const [t1, c1] = stops[i + 1];
    if (t >= t0 && t <= t1) {
      const f = (t - t0) / (t1 - t0);
      const c = c0.map((v, i2) => Math.round(v + (c1[i2] - v) * f));
      return `rgb(${c[0]},${c[1]},${c[2]})`;
    }
  }
  return 'rgb(40,40,90)';
}

function drawSpiral(ctx, N, rotOffset) {
  ctx.clearRect(0, 0, N, N);
  const cx = N / 2, cy = N / 2, arms = 2, tightness = 2.4;
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const dx = x - cx + 0.5, dy = y - cy + 0.5;
      const r = Math.sqrt(dx * dx + dy * dy);
      if (r > N / 2) continue;
      const theta = Math.atan2(dy, dx) + rotOffset;
      const spiral = Math.cos(arms * theta - tightness * r);
      const density = (spiral + 1) / 2 * (1 - r / (N / 2));
      if (density > 0.42 || r < 1.6) plot(ctx, x, y, rampColor(Math.min(r / (N / 2), 1)));
    }
  }
}

function drawPlanet(ctx, N, ringAngle, pulse) {
  ctx.clearRect(0, 0, N, N);
  const cx = N / 2, cy = N / 2, pr = N * 0.2 * (1 + pulse * 0.05);
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const dx = x - cx, dy = y - cy;
      const r = Math.sqrt(dx * dx + dy * dy);
      if (r <= pr) plot(ctx, x, y, rampColor((r / pr) * 0.6));
    }
  }
  const cosA = Math.cos(ringAngle), sinA = Math.sin(ringAngle);
  for (let a = 0; a < 360; a += 4) {
    const rad = (a * Math.PI) / 180;
    const ex = Math.cos(rad) * pr * 1.8;
    const ey = Math.sin(rad) * pr * 0.35;
    const rx = ex * cosA - ey * sinA;
    const ry = ex * sinA + ey * cosA;
    const x = Math.round(cx + rx), y = Math.round(cy + ry);
    if (x >= 0 && x < N && y >= 0 && y < N) plot(ctx, x, y, '#FFBF00');
  }
}

function drawBurst(ctx, N, progress) {
  ctx.clearRect(0, 0, N, N);
  const cx = N / 2, cy = N / 2, rays = 10;
  const maxLen = N * 0.46;
  const len = maxLen * Math.min(progress * 2, 1);
  const fade = progress > 0.5 ? 1 - (progress - 0.5) * 2 : 1;
  for (let i = 0; i < rays; i++) {
    const angle = (i / rays) * Math.PI * 2;
    for (let d = 0; d < len; d++) {
      const x = Math.round(cx + Math.cos(angle) * d);
      const y = Math.round(cy + Math.sin(angle) * d);
      if (x >= 0 && x < N && y >= 0 && y < N) plot(ctx, x, y, rampColor(d / maxLen), fade);
    }
  }
  for (let yy = -1; yy <= 1; yy++) for (let xx = -1; xx <= 1; xx++) plot(ctx, cx + xx, cy + yy, '#FFD700', fade);
}

// ─── App State ──────────────────────────────────────────────────────────────
const WS_URL = 'ws://127.0.0.1:8765';
let ws = null;
let token = '';
let animRaf = null;
let animT = 0;
let currentState = 'idle';
let sessions = [];
let serverView = false;
let toolsView = false;
let marketplaceView = false;
let pendingApproval = null;
let pendingDownload = null;
let sessionStartTime = 0;
let timerInterval = null;
let currentSessionId = '';
let authed = false;
let installedTools = new Set();
let splitPaneActive = false;
let dryRunMode = false;
let sanitizeEnabled = true;
let rateLimit = 30;
let currentTheme = 'dark';
let streamBuffer = '';
let streamElement = null;
let planSteps = [];
let bbMode = false;
let currentTarget = '';

const floatCanvas = document.getElementById('floatCanvas');
const floatCtx = floatCanvas.getContext('2d');
const floatLabel = document.getElementById('floatLabel');
const floatDetail = document.getElementById('floatDetail');
const chatTranscript = document.getElementById('chatTranscript');
const connDot = document.getElementById('connDot');
const connText = document.getElementById('connText');
const sendBtn = document.getElementById('sendBtn');
const goalInput = document.getElementById('goalInput');
const sidebarTitle = document.getElementById('sidebarTitle');
const sidebarList = document.getElementById('sidebarList');
const serverToggle = document.getElementById('serverToggle');
const toolsToggle = document.getElementById('toolsToggle');
const marketToggle = document.getElementById('marketToggle');

function newSessionId() {
  return 'web-' + Date.now() + '-' + Math.random().toString(36).substr(2, 6);
}

// ─── Auth ───────────────────────────────────────────────────────────────────
function doAuth() {
  token = document.getElementById('tokenInput').value.trim();
  const err = document.getElementById('authError');
  const status = document.getElementById('authStatus');
  const btn = document.getElementById('connectBtn');
  if (!token) { err.textContent = 'Token required'; return; }
  btn.disabled = true;
  status.textContent = 'Connecting to gateway...';
  err.textContent = '';
  connectWS();
}

const urlParams = new URLSearchParams(window.location.search);
const urlToken = urlParams.get('token');
if (urlToken) {
  token = urlToken;
  document.getElementById('authGate').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  connectWS();
}

// ─── WebSocket ──────────────────────────────────────────────────────────────
function connectWS() {
  if (ws) { try { ws.close(); } catch(e){} }
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    updateConn('connecting');
    ws.send(JSON.stringify({ type: 'auth', token }));
  };

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    handleMessage(msg);
  };

  ws.onclose = () => {
    updateConn('disconnected');
    sendBtn.disabled = true;
    authed = false;
    addSystemMsg('Disconnected from gateway — reconnecting...');
    setTimeout(connectWS, 3000);
  };

  ws.onerror = (e) => {
    updateConn('disconnected');
    const err = document.getElementById('authError');
    if (document.getElementById('authGate').style.display !== 'none') {
      err.textContent = 'Connection failed. Check gateway and token.';
      document.getElementById('connectBtn').disabled = false;
    }
  };
}

function updateConn(state) {
  connDot.className = 'status-dot ' + state;
  connText.textContent = state === 'connected' ? 'Online' : state === 'connecting' ? 'Connecting...' : 'Offline';
}

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

// ─── Message Handling ─────────────────────────────────────────────────────────
function handleMessage(msg) {
  switch (msg.type) {
    case 'stream_token':
      appendStreamToken(msg.token || msg.text || '');
      return;
    case 'agent_plan':
      renderPlan(msg.steps || []);
      return;
    case 'dry_run_result':
      addSystemMsg(`[DRY RUN] ${msg.plan || 'Agent would execute:'}\n${(msg.steps || []).join('\n')}`);
      return;
    case 'auth_result':
      authed = msg.ok;
      if (authed) {
        updateConn('connected');
        document.getElementById('authGate').style.display = 'none';
        document.getElementById('app').style.display = 'flex';
        sendBtn.disabled = false;
        addSystemMsg('Connected to Cybertron gateway');
        send({ type: 'get_tools' });
        send({ type: 'get_marketplace' });
      } else {
        const err = document.getElementById('authError');
        err.textContent = 'Auth rejected — token may be stale';
        document.getElementById('connectBtn').disabled = false;
      }
      break;
    case 'agent_status':
      if (msg.sessionId === currentSessionId) {
        setAgentState(msg.state, msg.detail || '');
      }
      break;
    case 'sessions_snapshot':
      sessions = msg.sessions || [];
      if (serverView) renderSessions();
      break;
    case 'tool_call_request':
      if (msg.sessionId === currentSessionId) {
        showApproval(msg);
      }
      break;
    case 'tool_call_result':
      if (msg.sessionId === currentSessionId) {
        addToolResultMsg(msg);
      }
      break;
    case 'session_started':
      addSystemMsg(`Session started: ${msg.sessionId}`);
      break;
    case 'config_state':
      if (!msg.nimApiKeySet) {
        addSystemMsg('NIM API key not set — agent will not respond. Configure in Control Center.');
      }
      break;
    case 'tools_catalog':
      const impl = msg.tools.filter(t => t.implemented).length;
      addSystemMsg(`${impl} of ${msg.tools.length} tools have real handlers`);
      break;
    case 'github_tool_status':
      const success = msg.success;
      const message = msg.message || '';
      const tool = msg.tool;
      if (success && tool) {
        installedTools.add(tool.id);
        addSystemMsg(`[github] ${message} — ${tool.id} ${tool.version}`);
        if (toolsView) renderTools();
        if (marketplaceView) renderMarketplace();
      } else {
        addSystemMsg(`[github] ${message}`);
      }
      break;
    case 'marketplace_catalog':
      marketplaceData = msg.marketplace || [];
      if (marketplaceView) renderMarketplace();
      break;
  }
}

function setAgentState(state, detail) {
  currentState = state;
  floatLabel.textContent = state.toUpperCase();
  floatDetail.textContent = detail || state;

  if (animRaf) cancelAnimationFrame(animRaf);
  animT = 0;

  if (state === 'thinking' || state === 'running_tool' || state === 'awaiting_approval') {
    animatePlanet();
  } else if (state === 'done') {
    animateSpiral();
  } else if (state === 'error') {
    drawPlanet(floatCtx, 28, 0, 0);
  } else {
    drawPlanet(floatCtx, 28, 0, 0);
    stopTimer();
  }
}

// ─── Animations ─────────────────────────────────────────────────────────────
function animatePlanet() {
  animT += 0.02;
  drawPlanet(floatCtx, 28, animT * 0.6, (Math.sin(animT * 1.5) + 1) / 2);
  animRaf = requestAnimationFrame(animatePlanet);
}

function animateSpiral() {
  animT += 0.02;
  drawSpiral(floatCtx, 28, animT * 0.8);
  animRaf = requestAnimationFrame(animateSpiral);
}

function animateBurst() {
  animT += 0.03;
  const progress = Math.min(animT, 1);
  drawBurst(floatCtx, 28, progress);
  if (progress < 1) {
    animRaf = requestAnimationFrame(animateBurst);
  } else {
    setTimeout(() => setAgentState('idle', 'Session complete.'), 500);
  }
}

// ─── Timer ──────────────────────────────────────────────────────────────────
function startTimer() {
  stopTimer();
  timerInterval = setInterval(() => {
    const elapsed = ((Date.now() - sessionStartTime) / 1000).toFixed(1);
    floatDetail.textContent = `T+${elapsed}s`;
  }, 100);
}

function stopTimer() {
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
}

// ─── Chat Messages ──────────────────────────────────────────────────────────
function addUserMsg(text) {
  const el = document.createElement('div');
  el.className = 'chat-msg msg-user';
  el.innerHTML = `<div class="msg-label">You</div><div>${escapeHtml(text)}</div><div class="msg-time">${timeNow()}</div>`;
  chatTranscript.appendChild(el);
  scrollToBottom();
}

function addAgentMsg(text) {
  const el = document.createElement('div');
  el.className = 'chat-msg msg-agent';
  el.innerHTML = `<div class="msg-label">Cybertron</div><div>${escapeHtml(text)}</div><div class="msg-time">${timeNow()}</div>`;
  chatTranscript.appendChild(el);
  scrollToBottom();
}

function addSystemMsg(text) {
  const el = document.createElement('div');
  el.className = 'chat-msg msg-system';
  el.textContent = text;
  chatTranscript.appendChild(el);
  scrollToBottom();
}

function addToolCallMsg(tool, args) {
  const el = document.createElement('div');
  el.className = 'chat-msg msg-tool';
  el.innerHTML = `<div class="msg-label">TOOL: ${escapeHtml(tool)}</div><div>Executing...</div><pre>${escapeHtml(JSON.stringify(args, null, 2))}</pre><div class="msg-time">${timeNow()}</div>`;
  chatTranscript.appendChild(el);
  scrollToBottom();
}

function addToolResultMsg(result) {
  const el = document.createElement('div');
  const ok = result.ok;
  const toolId = result.toolId || '?';
  const output = result.output || '';
  const error = result.error || '';
  const duration = result.durationMs || 0;

  if (ok) {
    el.className = 'chat-msg msg-result';
    el.innerHTML = `<div class="msg-label">RESULT: ${escapeHtml(toolId)} (${duration}ms)</div><pre>${escapeHtml(output)}</pre><div class="msg-time">${timeNow()}</div>`;
  } else {
    el.className = 'chat-msg msg-error';
    el.innerHTML = `<div class="msg-label">ERROR: ${escapeHtml(toolId)} (${duration}ms)</div><div>${escapeHtml(error)}</div><div class="msg-time">${timeNow()}</div>`;
  }
  chatTranscript.appendChild(el);
  scrollToBottom();
}

function timeNow() {
  return new Date().toLocaleTimeString('en-US', { hour12: false });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function scrollToBottom() {
  chatTranscript.scrollTop = chatTranscript.scrollHeight;
}

// ─── Sidebar Views ──────────────────────────────────────────────────────────
let marketplaceData = [];

function renderSessions() {
  sidebarTitle.textContent = 'Sessions';
  sidebarList.innerHTML = '';
  if (!sessions.length) {
    sidebarList.innerHTML = '<div style="padding:20px;color:var(--text-muted);font-size:12px;text-align:center;">No active sessions</div>';
    return;
  }
  sessions.forEach(s => {
    const el = document.createElement('div');
    el.className = 'session-item';
    const stateClass = `state-${s.state}`;
    const elapsed = s.finishedAt ? ((s.finishedAt - s.startedAt)/1000).toFixed(1) + 's' : 'active';
    el.innerHTML = `
      <div class="session-id">${s.id}</div>
      <div class="session-goal">${escapeHtml(s.goal)}</div>
      <div class="session-meta">
        <span class="session-state ${stateClass}">${s.state}</span>
        <span>${elapsed}</span>
        <span>calls:${s.toolCallCount || 0}</span>
      </div>
    `;
    sidebarList.appendChild(el);
  });
}

function renderTools() {
  sidebarTitle.textContent = 'Tool Registry';
  sidebarList.innerHTML = '';
  // Request tools from gateway (or show cached)
  send({ type: 'get_tools' });
  sidebarList.innerHTML = '<div style="padding:20px;color:var(--text-muted);font-size:12px;text-align:center;">Loading tools...</div>';
}

function renderMarketplace() {
  sidebarTitle.textContent = 'Marketplace';
  sidebarList.innerHTML = '';
  if (!marketplaceData.length) {
    sidebarList.innerHTML = '<div style="padding:20px;color:var(--text-muted);font-size:12px;text-align:center;">Loading marketplace...</div>';
    send({ type: 'get_marketplace' });
    return;
  }
  marketplaceData.forEach(item => {
    const el = document.createElement('div');
    el.className = 'market-item';
    const isInstalled = installedTools.has(item.name);
    el.innerHTML = `
      <div class="market-name">
        ${escapeHtml(item.name)}
        ${isInstalled ? '<span class="market-installed">✓ installed</span>' : ''}
      </div>
      <div class="market-desc">${escapeHtml(item.description || '')}</div>
      <div class="market-meta">
        <span class="market-category">${item.category}</span>
        ${!isInstalled ? `<button class="market-install" onclick="installMarketTool('${item.repo}', '${item.category}')">Install</button>` : ''}
      </div>
    `;
    sidebarList.appendChild(el);
  });
}

// ─── Streaming ─────────────────────────────────────────────────────────────
function appendStreamToken(token) {
  if (!streamElement) {
    streamElement = document.createElement('div');
    streamElement.className = 'chat-msg msg-agent';
    streamElement.innerHTML = '<div class="msg-label">Cybertron <span style="color:var(--teal);font-size:9px;">(thinking...)</span></div><div class="stream-text"></div>';
    chatTranscript.appendChild(streamElement);
    scrollToBottom();
  }
  const textDiv = streamElement.querySelector('.stream-text');
  textDiv.textContent += token;
  scrollToBottom();
}

function finalizeStream() {
  if (streamElement) {
    const textDiv = streamElement.querySelector('.stream-text');
    const text = textDiv.textContent;
    streamElement.innerHTML = `<div class="msg-label">Cybertron</div><div>${escapeHtml(text)}</div><div class="msg-time">${timeNow()}</div>`;
    streamElement = null;
    streamBuffer = '';
  }
}

// ─── Multi-step Planning ─────────────────────────────────────────────────────
function renderPlan(steps) {
  planSteps = steps;
  const el = document.createElement('div');
  el.className = 'plan-box';
  el.id = 'activePlan';
  let html = '<div class="plan-label">Execution Plan</div>';
  steps.forEach((step, i) => {
    html += `<div class="plan-step" id="plan-step-${i}"><div class="plan-step-num">${i + 1}</div><div>${escapeHtml(step)}</div></div>`;
  });
  el.innerHTML = html;
  chatTranscript.appendChild(el);
  scrollToBottom();
}

function updatePlanStep(index, status) {
  const step = document.getElementById(`plan-step-${index}`);
  if (!step) return;
  step.classList.remove('active', 'done');
  if (status === 'active') step.classList.add('active');
  if (status === 'done') step.classList.add('done');
}

// ─── Split Pane ──────────────────────────────────────────────────────────────
function toggleSplitPane() {
  splitPaneActive = !splitPaneActive;
  document.getElementById('splitRight').classList.toggle('active', splitPaneActive);
  document.getElementById('splitToggle').classList.toggle('on', splitPaneActive);
}

function appendToSplitPane(text) {
  const content = document.getElementById('splitContent');
  if (!content) return;
  content.textContent += text + '\n';
  content.scrollTop = content.scrollHeight;
}

function clearSplitPane() {
  const content = document.getElementById('splitContent');
  if (content) content.textContent = '';
}

// ─── Theme ───────────────────────────────────────────────────────────────────
function setTheme(theme) {
  currentTheme = theme;
  document.documentElement.setAttribute('data-theme', theme);
  document.getElementById('themeDark').classList.toggle('active', theme === 'dark');
  document.getElementById('themeLight').classList.toggle('active', theme === 'light');
  localStorage.setItem('cybertron-theme', theme);
}

// Load saved theme
const savedTheme = localStorage.getItem('cybertron-theme');
if (savedTheme) setTheme(savedTheme);

// ─── Control Center ──────────────────────────────────────────────────────────
function showControlCenter() {
  document.getElementById('controlCenter').style.display = 'flex';
}
function hideControlCenter() {
  document.getElementById('controlCenter').style.display = 'none';
}
function updateConfig(key, value) {
  if (key === 'systemPrompt' && value === 'custom') {
    const custom = prompt('Enter custom system prompt:');
    if (custom) value = custom;
  }
  send({ type: 'set_config', key, value });
}
function saveConfig() {
  const apiKey = document.getElementById('nimApiKey').value;
  const model = document.getElementById('modelSelect').value;
  const prompt = document.getElementById('systemPrompt').value;
  send({ type: 'set_config', config: { nimApiKey: apiKey, model, systemPrompt: prompt, dryRun: dryRunMode, sanitize: sanitizeEnabled, rateLimit } });
  addSystemMsg('Configuration saved');
  hideControlCenter();
}
function toggleDryRun() {
  dryRunMode = !dryRunMode;
  document.getElementById('dryRunToggle').classList.toggle('on', dryRunMode);
  addSystemMsg(dryRunMode ? 'Dry-run mode enabled — agent will plan but not execute' : 'Dry-run mode disabled');
}
function toggleSanitize() {
  sanitizeEnabled = !sanitizeEnabled;
  document.getElementById('sanitizeToggle').classList.toggle('on', sanitizeEnabled);
}

// ─── UI Actions ─────────────────────────────────────────────────────────────
function startSession() {
  const goal = goalInput.value.trim();
  if (!goal) return;
  goalInput.value = '';

  // Slash commands
  if (goal.startsWith('/')) {
    handleSlashCommand(goal);
    return;
  }

  sendBtn.disabled = true;
  addUserMsg(goal);
  addSystemMsg('Starting reconnaissance session...');
  currentSessionId = newSessionId();
  send({ type: 'session_start', sessionId: currentSessionId, goal, origin: 'web' });
  sessionStartTime = Date.now();
  startTimer();
  setTimeout(() => sendBtn.disabled = false, 500);
}

function handleSlashCommand(buf) {
  const parts = buf.split(/\s+/);
  const cmd = parts[0].toLowerCase();

  if (cmd === '/add-tool') {
    if (parts.length < 2) {
      addSystemMsg('Usage: /add-tool <github-url-or-repo> [category]');
      return;
    }
    let url = parts[1];
    const category = parts[2] || 'recon';
    if (!url.includes('github.com')) url = 'https://github.com/' + url;
    const repo = url.replace(/.*github\.com\//, '').replace(/\.git$/, '').replace(/\/$/, '');
    if (!repo || !repo.includes('/')) {
      addSystemMsg('Could not parse owner/repo from URL');
      return;
    }
    pendingDownload = { url, repo, category };
    document.getElementById('downloadRepo').textContent = repo;
    document.getElementById('downloadCategory').textContent = category;
    document.getElementById('downloadModal').style.display = 'flex';
    return;
  }

  if (cmd === '/tools') {
    toggleToolsView();
    return;
  }
  if (cmd === '/marketplace') {
    toggleMarketplaceView();
    return;
  }
  if (cmd === '/remove-tool') {
    if (parts.length < 2) {
      addSystemMsg('Usage: /remove-tool <tool-id>');
      return;
    }
    send({ type: 'remove_tool', toolId: parts[1] });
    return;
  }
  if (cmd === '/dry-run') {
    toggleDryRun();
    return;
  }
  if (cmd === '/config') {
    showControlCenter();
    return;
  }
  if (cmd === '/split') {
    toggleSplitPane();
    return;
  }
  if (cmd === '/bb' || cmd === '/bounty') {
    bbMode = !bbMode;
    addSystemMsg(`Bug Bounty mode: ${bbMode ? 'ON' : 'OFF'}`);
    if (bbMode) {
      addSystemMsg('Commands: /target <name>  /recon  /brute <type>  /report  /submit  /sync-h1 <handle>  /targets');
    }
    return;
  }

  if (cmd === '/target') {
    if (parts.length < 2) {
      addSystemMsg('Usage: /target <target-name>');
      return;
    }
    currentTarget = parts[1];
    addSystemMsg(`Target set: ${parts[1]}`);
    return;
  }

  if (cmd === '/recon') {
    if (!currentTarget) {
      addSystemMsg('No target set. Use /target <name> first.');
      return;
    }
    addSystemMsg(`Starting reconnaissance on ${currentTarget}...`);
    send({ type: 'execute_recon', target: currentTarget, scope_name: currentTarget });
    return;
  }

  if (cmd === '/brute') {
    if (parts.length < 2) {
      addSystemMsg('Usage: /brute <dirs|subdomains|params|vhosts|api|idor> [wordlist]');
      return;
    }
    if (!currentTarget) {
      addSystemMsg('No target set. Use /target <name> first.');
      return;
    }
    const attackType = parts[1];
    const wl = parts[2] || 'common';
    addSystemMsg(`Starting ${attackType} brute force on ${currentTarget}...`);
    send({ type: 'execute_brute', target: currentTarget, attack_type: attackType, wordlist: wl, scope_name: currentTarget });
    return;
  }

  if (cmd === '/report') {
    if (!currentTarget) {
      addSystemMsg('No target set. Use /target <name> first.');
      return;
    }
    addSystemMsg(`Generating report for ${currentTarget}...`);
    send({ type: 'generate_report', program: currentTarget, handle: currentTarget });
    return;
  }

  if (cmd === '/submit') {
    if (!currentTarget) {
      addSystemMsg('No target set. Use /target <name> first.');
      return;
    }
    addSystemMsg(`Submitting findings to HackerOne for ${currentTarget}...`);
    send({ type: 'submit_hackerone', target: currentTarget });
    return;
  }

  if (cmd === '/sync-h1') {
    if (parts.length < 2) {
      addSystemMsg('Usage: /sync-h1 <program-handle>');
      return;
    }
    addSystemMsg(`Syncing HackerOne program: ${parts[1]}...`);
    send({ type: 'sync_hackerone', handle: parts[1] });
    return;
  }

  if (cmd === '/targets') {
    send({ type: 'list_targets' });
    return;
  }

  if (cmd === '/export') {
    if (parts.length < 2) {
      addSystemMsg('Usage: /export markdown | json | audit | list');
      return;
    }
    const fmt = parts[1].toLowerCase();
    if (fmt === 'audit') {
      addSystemMsg('Audit log viewer — check ~/.cybertron/audit.log');
      return;
    }
    if (fmt === 'list') {
      addSystemMsg('Export list — check ~/.cybertron/exports/');
      return;
    }
    if (fmt === 'markdown' || fmt === 'md') {
      addSystemMsg('Session exported to ~/.cybertron/exports/ (Markdown)');
      return;
    }
    if (fmt === 'json') {
      addSystemMsg('Session exported to ~/.cybertron/exports/ (JSON)');
      return;
    }
    addSystemMsg('Usage: /export markdown | json | audit | list');
    return;
  }
  if (cmd === '/help' || cmd === '/?') {
    addSystemMsg('Commands: /add-tool <url> [cat]  /tools  /marketplace  /remove-tool <id>');
    addSystemMsg('          /export <fmt>  /dry-run  /config  /split  /bb  /target <name>');
    addSystemMsg('          /recon  /brute <type>  /report  /submit  /sync-h1 <handle>  /targets');
    addSystemMsg('          /help');
    return;
  }
  addSystemMsg(`Unknown command: ${cmd}. Use /help for available commands.`);
}

function installMarketTool(repo, category) {
  if (!repo) return;
  const url = 'https://github.com/' + repo;
  pendingDownload = { url, repo, category: category || 'recon' };
  document.getElementById('downloadRepo').textContent = repo;
  document.getElementById('downloadCategory').textContent = category || 'recon';
  document.getElementById('downloadModal').style.display = 'flex';
}

function toggleServerView() {
  serverView = !serverView;
  toolsView = false;
  marketplaceView = false;
  updateToggles();
  if (serverView) {
    send({ type: 'list_sessions' });
    renderSessions();
  }
}

function toggleToolsView() {
  toolsView = !toolsView;
  serverView = false;
  marketplaceView = false;
  updateToggles();
  if (toolsView) renderTools();
}

function toggleMarketplaceView() {
  marketplaceView = !marketplaceView;
  serverView = false;
  toolsView = false;
  updateToggles();
  if (marketplaceView) renderMarketplace();
}

function updateToggles() {
  serverToggle.classList.toggle('active', serverView);
  toolsToggle.classList.toggle('active', toolsView);
  marketToggle.classList.toggle('active', marketplaceView);
  if (!serverView && !toolsView && !marketplaceView) {
    sidebarTitle.textContent = 'Sessions';
    sidebarList.innerHTML = '<div style="padding:20px;color:var(--text-muted);font-size:12px;text-align:center;">Select a view above</div>';
  }
}

function showApproval(msg) {
  pendingApproval = { sessionId: msg.sessionId, requestId: msg.requestId, toolId: msg.toolId };
  document.getElementById('approvalTool').textContent = msg.toolId;
  document.getElementById('approvalArgs').textContent = JSON.stringify(msg.args, null, 2);
  document.getElementById('approvalModal').style.display = 'flex';
  addSystemMsg(`Approval required for tool: ${msg.toolId}`);
}

function sendApproval(approved) {
  if (!pendingApproval) return;
  send({
    type: 'tool_call_approval',
    sessionId: pendingApproval.sessionId,
    requestId: pendingApproval.requestId,
    approved
  });
  document.getElementById('approvalModal').style.display = 'none';
  addSystemMsg(approved ? `Approved: ${pendingApproval.toolId}` : `Denied: ${pendingApproval.toolId}`);
  pendingApproval = null;
}

function sendDownloadApproval(approved) {
  if (!pendingDownload) {
    document.getElementById('downloadModal').style.display = 'none';
    return;
  }
  if (!approved) {
    addSystemMsg('Download cancelled.');
    pendingDownload = null;
    document.getElementById('downloadModal').style.display = 'none';
    return;
  }
  const dd = pendingDownload;
  pendingDownload = null;
  document.getElementById('downloadModal').style.display = 'none';
  addSystemMsg(`Downloading ${dd.repo}...`);
  send({ type: 'register_github_tool', url: dd.url, category: dd.category });
}

// ─── Keyboard Shortcuts ─────────────────────────────────────────────────────
function handleComposerKey(e) {
  if (e.key === 'Enter') startSession();
}

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') {
    if (e.key === 'Escape') {
      e.target.blur();
      return;
    }
    return;
  }

  if (e.key === '?') {
    e.preventDefault();
    showShortcuts();
  }
  if (e.key === '/') {
    e.preventDefault();
    goalInput.focus();
  }
  if (e.key.toLowerCase() === 's') {
    toggleServerView();
  }
  if (e.key.toLowerCase() === 't') {
    toggleToolsView();
  }
  if (e.key.toLowerCase() === 'm') {
    toggleMarketplaceView();
  }
  if (e.key.toLowerCase() === 'p') {
    toggleSplitPane();
  }
  if (e.key.toLowerCase() === 'c') {
    showControlCenter();
  }
  if (e.key.toLowerCase() === 'y') {
    if (pendingApproval) sendApproval(true);
    else if (pendingDownload) sendDownloadApproval(true);
  }
  if (e.key.toLowerCase() === 'n') {
    if (pendingApproval) sendApproval(false);
    else if (pendingDownload) sendDownloadApproval(false);
  }
  if (e.key === 'Escape') {
    hideControlCenter();
    hideShortcuts();
  }
});

function showShortcuts() {
  document.getElementById('shortcutsOverlay').style.display = 'flex';
}
function hideShortcuts() {
  document.getElementById('shortcutsOverlay').style.display = 'none';
}

// Initial draw
drawPlanet(floatCtx, 28, 0, 0);
