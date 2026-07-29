class CybertronApp {
  constructor() {
    this.sessionId = 'session_' + Math.random().toString(36).slice(2, 10);
    this.ws = null; this.reconnectAttempts = 0; this.maxReconnect = 5;
    this.currentState = 'idle'; this.animationFrame = null; this.animationTime = 0;
    this.init();
  }
  init() {
    this.initBackground(); this.initWebSocket(); this.initNavigation(); this.initChat(); this.initDashboard(); this.startLogoAnimation();
  }
  initBackground() {
    const canvas = document.getElementById('bgCanvas'); if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
    resize(); window.addEventListener('resize', resize);
    const stars = Array.from({length: 120}, () => ({x: Math.random(), y: Math.random(), size: Math.random() * 1.5 + 0.3, speed: Math.random() * 0.02 + 0.005, brightness: Math.random(), twinkleSpeed: Math.random() * 0.03 + 0.01}));
    const connections = [];
    for (let i = 0; i < stars.length; i++) for (let j = i + 1; j < stars.length; j++) { const dx = stars[i].x - stars[j].x, dy = stars[i].y - stars[j].y; if (Math.sqrt(dx*dx + dy*dy) < 0.15) connections.push([i, j]); }
    let t = 0;
    const draw = () => {
      t += 0.005; ctx.clearRect(0, 0, canvas.width, canvas.height);
      const grad = ctx.createRadialGradient(canvas.width * 0.7, canvas.height * 0.3, 0, canvas.width * 0.7, canvas.height * 0.3, canvas.width * 0.5);
      grad.addColorStop(0, 'rgba(77, 208, 225, 0.03)'); grad.addColorStop(0.5, 'rgba(255, 191, 0, 0.01)'); grad.addColorStop(1, 'transparent');
      ctx.fillStyle = grad; ctx.fillRect(0, 0, canvas.width, canvas.height);
      stars.forEach(star => {
        const x = star.x * canvas.width, y = star.y * canvas.height;
        const twinkle = Math.sin(t * star.twinkleSpeed * 100) * 0.4 + 0.6;
        ctx.beginPath(); ctx.arc(x, y, star.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255, 248, 220, ${star.brightness * twinkle * 0.8})`; ctx.fill();
      });
      ctx.strokeStyle = 'rgba(205, 127, 50, 0.06)'; ctx.lineWidth = 0.5;
      connections.forEach(([a, b]) => { ctx.beginPath(); ctx.moveTo(stars[a].x * canvas.width, stars[a].y * canvas.height); ctx.lineTo(stars[b].x * canvas.width, stars[b].y * canvas.height); ctx.stroke(); });
      requestAnimationFrame(draw);
    }; draw();
  }
  initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/live`;
    const connect = () => {
      this.ws = new WebSocket(wsUrl);
      this.ws.onopen = () => { this.reconnectAttempts = 0; this.updateWsStatus('connected'); this.ws.send(JSON.stringify({type: 'subscribe', channel: 'global'})); };
      this.ws.onmessage = (e) => { const msg = JSON.parse(e.data); this.handleWsMessage(msg); };
      this.ws.onclose = () => { this.updateWsStatus('disconnected'); if (this.reconnectAttempts < this.maxReconnect) { this.reconnectAttempts++; setTimeout(connect, 2000 * this.reconnectAttempts); } };
      this.ws.onerror = () => { this.updateWsStatus('error'); };
    }; connect();
  }
  updateWsStatus(status) {
    const el = document.getElementById('wsStatus'); if (!el) return;
    const texts = {connected: 'Live', disconnected: 'Reconnecting...', error: 'Error'};
    el.querySelector('.ws-text').textContent = texts[status] || status;
    el.className = 'ws-status ' + (status === 'connected' ? 'connected' : '');
  }
  handleWsMessage(msg) { if (msg.type === 'finding') { this.addMiniFinding(msg.data); this.addActivity(`New ${msg.data.severity} finding: ${msg.data.title}`); } }
  initNavigation() {
    document.querySelectorAll('.nav-item').forEach(btn => {
      btn.addEventListener('click', () => {
        this.switchView(btn.dataset.view);
        document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      });
    });
  }
  switchView(viewName) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    const target = document.getElementById('view-' + viewName);
    if (target) target.classList.add('active');
    if (viewName === 'dashboard') this.refreshDashboard();
  }
  initChat() {
    const input = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.sendMessage(); } });
    sendBtn.addEventListener('click', () => this.sendMessage());
    document.querySelectorAll('.cmd-chip').forEach(chip => { chip.addEventListener('click', () => { input.value = chip.dataset.cmd; input.focus(); }); });
    input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 200) + 'px'; });
  }
  async sendMessage() {
    const input = document.getElementById('chatInput');
    const text = input.value.trim(); if (!text) return;
    input.value = ''; input.style.height = 'auto';
    this.addMessage('user', text); this.setAgentState('thinking');
    try {
      const res = await fetch('/api/chat/message', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text, session_id: this.sessionId }) });
      const data = await res.json();
      this.setAgentState('writing'); await this.typewriterResponse(data.response);
      if (data.intent) { document.getElementById('ctxTarget').textContent = data.intent.target || '—'; document.getElementById('ctxPlugins').textContent = (data.intent.plugins || []).join(', ') || '—'; }
      if (data.findings && data.findings.length > 0) data.findings.forEach(f => this.addMiniFinding(f));
      this.setAgentState('idle');
    } catch (err) {
      this.addMessage('assistant', '⚠️ Connection error. Please check the backend is running.');
      this.setAgentState('idle');
    }
  }
  addMessage(role, content) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div'); div.className = `message ${role}`;
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    let html = content.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`(.+?)`/g, '<code style="background:rgba(255,215,0,0.1);padding:1px 4px;border-radius:3px;font-family:var(--font-mono);font-size:12px;">$1</code>').replace(/\n/g, '<br>');
    div.innerHTML = `<div class="message-content">${html}</div><div class="message-meta"><span class="message-time">${time}</span></div>`;
    container.appendChild(div); container.scrollTop = container.scrollHeight;
  }
  async typewriterResponse(text) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div'); div.className = 'message assistant';
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    div.innerHTML = `<div class="message-content"><span class="typewriter-text"></span></div><div class="message-meta"><span class="message-time">${time}</span></div>`;
    container.appendChild(div);
    const span = div.querySelector('.typewriter-text');
    for (let i = 0; i < text.length; i++) {
      span.textContent += text[i];
      if (text[i] === '\n') span.innerHTML += '<br>';
      container.scrollTop = container.scrollHeight;
      await new Promise(r => setTimeout(r, 8));
    }
    span.innerHTML = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`(.+?)`/g, '<code style="background:rgba(255,215,0,0.1);padding:1px 4px;border-radius:3px;font-family:var(--font-mono);font-size:12px;">$1</code>').replace(/\n/g, '<br>');
  }
  setAgentState(state) {
    this.currentState = state;
    const statusEl = document.getElementById('agentStatus');
    const floatEl = document.getElementById('stateIconFloat');
    const canvas = document.getElementById('stateCanvas');
    const ctx = canvas?.getContext('2d');
    if (!statusEl || !ctx) return;
    const dot = statusEl.querySelector('.status-dot');
    const text = statusEl.querySelector('.status-text');
    dot.className = 'status-dot ' + state; text.textContent = state;
    if (this.animationFrame) cancelAnimationFrame(this.animationFrame);
    this.animationTime = 0;
    if (state === 'idle') { floatEl.classList.remove('visible'); drawPlanet(ctx, 28, 0, 0); }
    else {
      floatEl.classList.add('visible');
      const loop = () => {
        this.animationTime += 0.02;
        if (state === 'thinking') drawPlanet(ctx, 28, this.animationTime * 0.6, (Math.sin(this.animationTime * 1.5) + 1) / 2);
        else if (state === 'writing') drawSpiral(ctx, 28, this.animationTime * 0.8);
        this.animationFrame = requestAnimationFrame(loop);
      }; loop();
    }
  }
  initDashboard() {
    document.getElementById('newScanBtn')?.addEventListener('click', () => {
      this.switchView('chat');
      document.querySelector('.nav-item[data-view="chat"]')?.classList.add('active');
      document.querySelector('.nav-item[data-view="dashboard"]')?.classList.remove('active');
    });
  }
  async refreshDashboard() {
    try {
      const [health, stats, findings] = await Promise.all([
        fetch('/api/health').then(r => r.json()),
        fetch('/api/stats').then(r => r.json()),
        fetch('/api/findings/').then(r => r.json())
      ]);
      document.getElementById('statScans').textContent = stats.total_scans || 0;
      document.getElementById('statFindings').textContent = stats.total_findings || 0;
      document.getElementById('statEngagements').textContent = stats.active_engagements || 0;
      document.getElementById('statPlugins').textContent = stats.plugins_available || 0;
      const dist = findings.distribution || {}; const total = Math.max(findings.total || 1, 1);
      const sevs = ['critical', 'high', 'medium', 'low', 'info'];
      sevs.forEach((sev, i) => {
        const count = dist[sev] || 0; const pct = (count / total * 100);
        const row = document.querySelectorAll('.sev-row')[i];
        if (row) { row.querySelector('.sev-fill').style.width = pct + '%'; row.querySelector('.sev-count').textContent = count; }
      });
    } catch (e) { console.log('Dashboard refresh failed:', e); }
  }
  addMiniFinding(finding) {
    const container = document.getElementById('miniFindings'); if (!container) return;
    const empty = container.querySelector('.empty-state'); if (empty) empty.remove();
    const div = document.createElement('div'); div.className = `mini-finding ${finding.severity}`;
    const colorMap = {critical: 'var(--danger)', high: 'var(--warning)', medium: 'var(--accent-amber)', low: 'var(--positive)', info: 'var(--info)'};
    div.innerHTML = `<div class="mini-finding-title">${finding.title}</div><div class="mini-finding-sev" style="color:${colorMap[finding.severity] || colorMap.info}">${finding.severity}</div>`;
    container.insertBefore(div, container.firstChild);
    while (container.children.length > 5) container.removeChild(container.lastChild);
  }
  addActivity(text) {
    const list = document.getElementById('activityList'); if (!list) return;
    const empty = list.querySelector('.empty-state'); if (empty) empty.remove();
    const item = document.createElement('div'); item.className = 'activity-item';
    const colors = ['#ef5350', '#ffa726', '#4dd0e1', '#4caf50', '#FFD700'];
    item.innerHTML = `<span class="activity-icon" style="background:${colors[Math.floor(Math.random()*colors.length)]}"></span><span class="activity-text">${text}</span><span class="activity-time">${new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</span>`;
    list.insertBefore(item, list.firstChild);
    while (list.children.length > 10) list.removeChild(list.lastChild);
  }
  startLogoAnimation() {
    const canvas = document.getElementById('logoCanvas'); if (!canvas) return;
    const ctx = canvas.getContext('2d'); let t = 0;
    const animate = () => { t += 0.015; drawPlanet(ctx, 28, t * 0.4, (Math.sin(t) + 1) / 2 * 0.3); requestAnimationFrame(animate); };
    animate();
  }
}
document.addEventListener('DOMContentLoaded', () => { window.cybertron = new CybertronApp(); });
