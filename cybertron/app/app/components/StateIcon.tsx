"use client";

import { useEffect, useRef } from "react";

/**
 * The three animations from the preview demo, ported into a real component.
 *
 * Mapping (see README for the reasoning — "star burst = something useful"
 * was ambiguous, so this is the interpretation that shipped):
 *   thinking / running_tool / awaiting_approval -> rotating ringed planet
 *   done                                        -> swirling spiral, ~2s, then settles back to planet
 *   error                                        -> static planet, tinted danger-red
 *   idle                                         -> static planet
 *   a successful tool_call_result (independent of the above)
 *                                                 -> one-shot star-burst overlay, ~900ms, then reverts
 */

export type IconMainState = "idle" | "thinking" | "running_tool" | "awaiting_approval" | "done" | "error";

interface Props {
  state: IconMainState;
  /** increment this every time a tool result lands successfully, to trigger the burst overlay */
  burstKey: number;
  /** grid resolution (pixel-art detail) — keep this the same across uses for a consistent look */
  size?: number;
  /** rendered size in CSS px — independent of `size`, for compact inline use vs a large demo card */
  displayPx?: number;
}

function plot(ctx: CanvasRenderingContext2D, x: number, y: number, color: string, alpha = 1) {
  ctx.globalAlpha = alpha;
  ctx.fillStyle = color;
  ctx.fillRect(x, y, 1, 1);
  ctx.globalAlpha = 1;
}

function rampColor(t: number): [number, number, number] {
  const stops: [number, [number, number, number]][] = [
    [0.0, [255, 215, 0]],
    [0.35, [255, 191, 0]],
    [0.65, [77, 208, 225]],
    [1.0, [40, 40, 90]],
  ];
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, c0] = stops[i];
    const [t1, c1] = stops[i + 1];
    if (t >= t0 && t <= t1) {
      const f = (t - t0) / (t1 - t0);
      return [
        Math.round(c0[0] + (c1[0] - c0[0]) * f),
        Math.round(c0[1] + (c1[1] - c0[1]) * f),
        Math.round(c0[2] + (c1[2] - c0[2]) * f),
      ];
    }
  }
  return [40, 40, 90];
}
const rgb = (c: [number, number, number]) => `rgb(${c[0]},${c[1]},${c[2]})`;

function drawSpiral(ctx: CanvasRenderingContext2D, N: number, rotOffset: number) {
  ctx.clearRect(0, 0, N, N);
  const cx = N / 2, cy = N / 2, arms = 2, tightness = 2.4;
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const dx = x - cx + 0.5, dy = y - cy + 0.5;
      const r = Math.sqrt(dx * dx + dy * dy);
      if (r > N / 2) continue;
      const theta = Math.atan2(dy, dx) + rotOffset;
      const spiral = Math.cos(arms * theta - tightness * r);
      const density = ((spiral + 1) / 2) * (1 - r / (N / 2));
      if (density > 0.42 || r < 1.6) plot(ctx, x, y, rgb(rampColor(Math.min(r / (N / 2), 1))));
    }
  }
}

function drawPlanet(ctx: CanvasRenderingContext2D, N: number, ringAngle: number, pulse: number, tint: "normal" | "danger" = "normal") {
  ctx.clearRect(0, 0, N, N);
  const cx = N / 2, cy = N / 2, pr = N * 0.2 * (1 + pulse * 0.05);
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const dx = x - cx, dy = y - cy;
      const r = Math.sqrt(dx * dx + dy * dy);
      if (r <= pr) {
        if (tint === "danger") plot(ctx, x, y, "#ef5350", 0.85);
        else plot(ctx, x, y, rgb(rampColor((r / pr) * 0.6)));
      }
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
    if (x >= 0 && x < N && y >= 0 && y < N) plot(ctx, x, y, tint === "danger" ? "#ef5350" : "#FFBF00");
  }
}

function drawBurst(ctx: CanvasRenderingContext2D, N: number, progress: number) {
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
      if (x >= 0 && x < N && y >= 0 && y < N) plot(ctx, x, y, rgb(rampColor(d / maxLen)), fade);
    }
  }
  for (let yy = -1; yy <= 1; yy++) for (let xx = -1; xx <= 1; xx++) plot(ctx, cx + xx, cy + yy, "#FFD700", fade);
}

export function StateIcon({ state, burstKey, size = 28, displayPx }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>();
  const burstStartRef = useRef<number | null>(null);
  const prevBurstKey = useRef(burstKey);

  useEffect(() => {
    if (burstKey !== prevBurstKey.current) {
      burstStartRef.current = performance.now();
      prevBurstKey.current = burstKey;
    }
  }, [burstKey]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    canvas.width = size;
    canvas.height = size;

    function frame(now: number) {
      if (burstStartRef.current !== null) {
        const elapsed = now - burstStartRef.current;
        if (elapsed < 900) {
          drawBurst(ctx!, size, Math.min(elapsed / 700, 1));
          rafRef.current = requestAnimationFrame(frame);
          return;
        }
        burstStartRef.current = null;
      }
      if (state === "thinking" || state === "running_tool" || state === "awaiting_approval") {
        drawPlanet(ctx!, size, now * 0.0006, (Math.sin(now * 0.0015) + 1) / 2);
      } else if (state === "done") {
        drawSpiral(ctx!, size, now * 0.0008);
      } else if (state === "error") {
        drawPlanet(ctx!, size, 0, 0, "danger");
      } else {
        drawPlanet(ctx!, size, 0, 0);
      }
      rafRef.current = requestAnimationFrame(frame);
    }
    rafRef.current = requestAnimationFrame(frame);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [state, size]);

  const shownPx = displayPx ?? size * 4;
  return (
    <canvas
      ref={canvasRef}
      style={{ width: shownPx, height: shownPx, imageRendering: "pixelated" }}
    />
  );
}
