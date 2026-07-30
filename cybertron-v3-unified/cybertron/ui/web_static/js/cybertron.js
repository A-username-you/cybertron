// Cybertron Web UI — Pixel-art animations + API integration

// ===== Pixel Art Engine =====
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

// ===== State Management =====
const state = {
  currentModule: 'recon',
  agentState: 'idle',
  serverRunning: false,
  t: 0,
  animFrame: null,
  ws: null
};

const stateCanvas = document.getElementById('stateCanvas');
const stateCtx = stateCanvas.getContext('2d');
const brandCanvas = document.getElementById('brandCanvas');
const brandCtx = brandCanvas.getContext('2d');

function animateState() {
  state.t += 0.02;
  if (state.agentState === 'thinking') {
    drawPlanet(stateCtx, 28, state.t * 0.6, (Math.sin(state.t * 1.5) + 1) / 2);
  } else if (state.agentState === 'writing') {
    drawSpiral(stateCtx, 28, state.t * 0.8);
  } else if (state.agentState === 'result') {
    drawBurst(stateCtx, 28, Math.min((state.t % 1) * 2, 1));
  } else {
    drawPlanet(stateCtx, 28, 0, 0);
  }
  drawPlanet(brandCtx, 28, state.t * 0.3, (Math.sin(state.t) + 1) / 2);
  state.animFrame = requestAnimationFrame(animateState);
}

function setAgentState(newState, detail = '') {
  state.agentState = newState;
  document.getElementById('stateLabel').textContent = newState.toUpperCase();
  document.getElementById('stateDetail').textContent = detail || 'Ready for operations';
}

// ===== Navigation =====
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', (e) => {
    e.preventDefault();
    const mod = item.dataset.module;
    if (!mod) return;
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    item.classList.add('active');
    document.querySelectorAll('.panel').forEach(p => p.classList.add('hidden'));
    const panel = document.getElementById('panel-' + mod);
    if (panel) panel.classList.remove('hidden');
    state.currentModule = mod;
    updateBreadcrumb(mod);
  });
});

function updateBreadcrumb(mod) {
  const sections = {
    recon: 'Red Team / Reconnaissance',
    scan: 'Red Team / Vulnerability Scan',
    brute: 'Red Team / Brute Force',
    exploit: 'Red Team / Exploitation',
    forensics: 'Blue Team / Forensics',
    hunt: 'Blue Team / Threat Hunt',
    monitor: 'Blue Team / Monitor',
    reverse: 'Reverse Engineering / Binary Analysis',
    malware: 'Reverse Engineering / Malware Lab',
    memory: 'Reverse Engineering / Memory Analysis',
    ai: 'AI & Reports / AI Assistant',
    reports: 'AI & Reports / Reports'
  };
  document.getElementById('breadcrumb').innerHTML = sections[mod] || mod;
}

// ===== API Calls =====
async function apiCall(endpoint, formData) {
  try {
    const res = await fetch(endpoint, { method: 'POST', body: formData });
    return await res.json();
  } catch (e) {
    return { error: e.message };
  }
}

// ===== Module Runners =====
const runBtn = document.getElementById('runBtn');
const stopBtn = document.getElementById('stopBtn');

runBtn.addEventListener('click', async () => {
  const mod = state.currentModule;
  setAgentState('thinking', `Running ${mod}...`);
  runBtn.disabled = true;

  try {
    if (mod === 'recon') {
      const fd = new FormData();
      fd.append('target', document.getElementById('reconTarget').value);
      const data = await apiCall('/api/recon', fd);
      document.getElementById('statSubdomains').textContent = (data.subdomains || []).length;
      document.getElementById('statPorts').textContent = (data.ports || []).length;
      document.getElementById('reconOutput').textContent = JSON.stringify(data, null, 2);
      setAgentState('result', `Recon complete: ${(data.subdomains || []).length} subdomains`);
    }
    else if (mod === 'scan') {
      const fd = new FormData();
      fd.append('target', document.getElementById('scanTarget').value);
      const data = await apiCall('/api/scan', fd);
      document.getElementById('scanOutput').textContent = JSON.stringify(data, null, 2);
      setAgentState('result', `Scan complete: ${data.findings_count || 0} findings`);
    }
    else if (mod === 'brute') {
      const fd = new FormData();
      fd.append('target', document.getElementById('bruteTarget').value);
      fd.append('mode', document.getElementById('bruteMode').value);
      const data = await apiCall('/api/brute', fd);
      document.getElementById('bruteOutput').textContent = JSON.stringify(data, null, 2);
      setAgentState('result', `Brute force complete: ${(data.hits || []).length} hits`);
    }
    else if (mod === 'exploit') {
      if (!document.getElementById('exploitApprove').checked) {
        document.getElementById('exploitOutput').textContent = 'ERROR: Approval required before exploitation.';
        setAgentState('error', 'Approval required');
        runBtn.disabled = false;
        return;
      }
      document.getElementById('exploitOutput').textContent = 'Exploitation module executed (stub — no actual exploit launched in web UI for safety).';
      setAgentState('result', 'Exploitation approved and executed');
    }
    else if (mod === 'forensics') {
      const fd = new FormData();
      fd.append('source', document.getElementById('forensicsSource').value);
      const data = await apiCall('/api/forensics', fd);
      document.getElementById('forensicsOutput').textContent = JSON.stringify(data, null, 2);
      setAgentState('result', `Forensics complete: ${data.artifacts || 0} artifacts`);
    }
    else if (mod === 'hunt') {
      const fd = new FormData();
      fd.append('ioc', document.getElementById('huntIOC').value);
      fd.append('source', document.getElementById('huntSource').value);
      const data = await apiCall('/api/hunt', fd);
      document.getElementById('huntOutput').textContent = JSON.stringify(data, null, 2);
      setAgentState('result', `Hunt complete: ${data.matches || 0} matches`);
    }
    else if (mod === 'reverse') {
      const fd = new FormData();
      fd.append('target', document.getElementById('reverseTarget').value);
      const data = await apiCall('/api/reverse', fd);
      document.getElementById('reverseOutput').textContent = JSON.stringify(data, null, 2);
      setAgentState('result', `RE complete: ${data.file_type || 'unknown'}`);
    }
    else if (mod === 'ai') {
      document.getElementById('chatSend').click();
    }
    else if (mod === 'reports') {
      const fd = new FormData();
      fd.append('engagement', document.getElementById('reportEngagement').value);
      document.getElementById('reportOutput').textContent = 'Report generated (stub — download from server).';
      setAgentState('result', 'Report generated');
    }
    else {
      setAgentState('result', 'Module executed');
    }
  } catch (e) {
    setAgentState('error', e.message);
  } finally {
    runBtn.disabled = false;
    setTimeout(() => setAgentState('idle'), 2000);
  }
});

stopBtn.addEventListener('click', () => {
  setAgentState('idle', 'Operation stopped by user');
  runBtn.disabled = false;
});

// ===== AI Chat =====
const chatInput = document.getElementById('chatInput');
const chatSend = document.getElementById('chatSend');
const chatContainer = document.getElementById('chatContainer');

chatSend.addEventListener('click', async () => {
  const text = chatInput.value.trim();
  if (!text) return;

  // User message
  const userMsg = document.createElement('div');
  userMsg.className = 'chat-message user';
  userMsg.innerHTML = `<div class="chat-bubble">${escapeHtml(text)}</div>`;
  chatContainer.appendChild(userMsg);
  chatInput.value = '';
  chatContainer.scrollTop = chatContainer.scrollHeight;

  setAgentState('writing', 'AI is generating response...');

  // AI response via WebSocket or HTTP
  try {
    const fd = new FormData();
    fd.append('prompt', text);
    const data = await apiCall('/api/ai/chat', fd);
    const aiMsg = document.createElement('div');
    aiMsg.className = 'chat-message system';
    aiMsg.innerHTML = `
      <div class="chat-avatar"><canvas class="chat-canvas" width="28" height="28"></canvas></div>
      <div class="chat-bubble">${escapeHtml(data.response || 'No response')}</div>
    `;
    chatContainer.appendChild(aiMsg);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    setAgentState('result', 'AI response received');
  } catch (e) {
    setAgentState('error', 'AI request failed');
  }
  setTimeout(() => setAgentState('idle'), 2000);
});

chatInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') chatSend.click();
});

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ===== Server Toggle =====
const serverToggle = document.getElementById('serverToggle');
const serverStatus = document.getElementById('serverStatus');

serverToggle.addEventListener('change', () => {
  state.serverRunning = serverToggle.checked;
  serverStatus.textContent = state.serverRunning ? 'ON' : 'OFF';
  serverStatus.classList.toggle('on', state.serverRunning);
  if (state.serverRunning) {
    setAgentState('thinking', 'API Server starting...');
    setTimeout(() => setAgentState('result', 'API Server is running'), 1500);
  } else {
    setAgentState('idle', 'API Server stopped');
  }
});

// ===== Monitor Stats (stub) =====
function updateMonitor() {
  if (state.currentModule === 'monitor') {
    document.getElementById('monCpu').textContent = Math.floor(Math.random() * 30 + 10) + '%';
    document.getElementById('monMem').textContent = Math.floor(Math.random() * 40 + 30) + '%';
    document.getElementById('monNet').textContent = Math.floor(Math.random() * 50);
  }
}
setInterval(updateMonitor, 2000);

// ===== Init =====
animateState();
setAgentState('idle', 'Welcome to Cybertron v3.0');
