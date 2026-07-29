function plot(ctx, x, y, color, alpha) {
  ctx.fillStyle = color; ctx.globalAlpha = alpha === undefined ? 1 : alpha;
  ctx.fillRect(x, y, 1, 1); ctx.globalAlpha = 1;
}
function rampColor(t) {
  const stops = [[0.00,[255,215,0]],[0.35,[255,191,0]],[0.65,[77,208,225]],[1.00,[40,40,90]]];
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0,c0] = stops[i], [t1,c1] = stops[i+1];
    if (t >= t0 && t <= t1) {
      const f = (t - t0) / (t1 - t0);
      const c = c0.map((v,i2) => Math.round(v + (c1[i2] - v) * f));
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
document.addEventListener('DOMContentLoaded', () => {
  const logoCanvas = document.getElementById('logoCanvas');
  if (logoCanvas) drawPlanet(logoCanvas.getContext('2d'), 28, 0.5, 0);
});
