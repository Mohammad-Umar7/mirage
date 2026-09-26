"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef } from "react";
import { fixed, int, simSpan } from "@/lib/format";
import { hudBus } from "@/lib/hudBus";
import { isFresh, LOCK_CONFIDENCE } from "@/lib/lock";
import { commands } from "@/lib/socket";
import { useMirage } from "@/lib/store";

function Ticks({ r, count, major, len, majorLen, color }: { r: number; count: number; major: number; len: number; majorLen: number; color: string }) {
  const lines = [];
  for (let k = 0; k < count; k++) {
    const a = (k / count) * Math.PI * 2;
    const l = k % major === 0 ? majorLen : len;
    const x1 = Math.cos(a) * r, y1 = Math.sin(a) * r;
    const x2 = Math.cos(a) * (r + l), y2 = Math.sin(a) * (r + l);
    lines.push(<line key={k} x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth={k % major === 0 ? 0.9 : 0.5} />);
  }
  return <>{lines}</>;
}

function Bracket({ x, y, sx, sy, color }: { x: number; y: number; sx: number; sy: number; color: string }) {
  const L = 13;
  return (
    <path
      d={`M ${x + sx * L} ${y} L ${x} ${y} L ${x} ${y + sy * L}`}
      fill="none"
      stroke={color}
      strokeWidth={2.4}
      strokeLinecap="square"
    />
  );
}

function Readout({ locked, cluster }: { locked: boolean; cluster: NonNullable<ReturnType<typeof useTarget>> }) {
  const m = cluster.metrics;
  const rows: [string, string][] = [];
  if (m.fund_roots90 != null) rows.push(["Funding roots", `${m.fund_roots90} wallet${Number(m.fund_roots90) === 1 ? "" : "s"} · ${m.fund_max_hops ?? "?"} hops`]);
  else if (m.fund_top_hub_frac != null) rows.push(["Funding", `${Math.round(Number(m.fund_top_hub_frac) * 100)}% one exchange burst`]);
  if (m.sync != null) rows.push(["Activity sync", fixed(Number(m.sync), 2)]);
  if (m.style != null) rows.push(["Style match", fixed(Number(m.style), 2)]);
  if (m.vote_window != null) rows.push(["Vote window", simSpan(Number(m.vote_window))]);
  if (m.created_window != null) rows.push(["Created within", simSpan(Number(m.created_window))]);
  const color = locked ? "#FF6B5B" : "#FFB347";
  return (
    <div className="w-[270px]">
      <div className="flex items-center gap-2">
        <span className={`inline-block h-1.5 w-1.5 rotate-45 ${locked ? "bg-red shadow-[0_0_10px_#FF3B30]" : "bg-amber blink"}`} />
        <span className="hud-label !text-[10px] !tracking-[0.3em]" style={{ color }}>
          {locked ? "Swarm detected" : "Acquiring target"}
        </span>
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className={`text-[26px] font-light leading-none ${locked ? "text-red-glow glow-red" : "text-amber"}`}>{int(cluster.size)}</span>
        <span className="hud-label !text-[9px]">accounts</span>
      </div>
      <div className="mt-1.5 hud-value whitespace-nowrap text-[11.5px] text-ink/90">
        confidence <span className="text-gold-soft">{fixed(cluster.confidence, 2)}</span>
        {cluster.level_estimate != null && (
          <>
            <span className="text-[var(--ink-faint)]"> · </span>est. level <span className="text-gold-soft">{cluster.level_estimate}</span>
          </>
        )}
      </div>
      <div className="my-2 h-px" style={{ background: `linear-gradient(90deg, ${color}, transparent)` }} />
      <div className="space-y-1">
        {rows.slice(0, 4).map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4">
            <span className="hud-label !text-[8.5px]">{k}</span>
            <span className="hud-value text-[11px] text-ink/90">{v}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 hud-label !text-[8px] !text-[var(--ink-faint)]">open evidence ›</div>
    </div>
  );
}

function useTarget() {
  const detection = useMirage((s) => s.detection);
  const locked = useMirage((s) => s.lockedCluster);
  const acquired = useMirage((s) => s.acquired);
  return useMemo(() => {
    if (!detection) return null;
    // swarms acquired before the latest launch stay red in the scene but lose the ring
    const fresh = detection.clusters.filter((c) => c.verdict === "SWARM" && isFresh(c.members, acquired));
    if (locked !== null) return detection.clusters.find((c) => c.id === locked && c.verdict === "SWARM") ?? fresh[0] ?? null;
    return fresh[0] ?? null;
  }, [detection, locked, acquired]);
}

export function TargetRing() {
  const cluster = useTarget();
  const view = useMirage((s) => s.view);
  const selected = useMirage((s) => s.selected);
  const root = useRef<HTMLDivElement>(null);
  const ringBox = useRef<HTMLDivElement>(null);
  const readout = useRef<HTMLDivElement>(null);
  const leader = useRef<SVGLineElement>(null);
  const locked = !!cluster && cluster.confidence >= LOCK_CONFIDENCE;
  // a fresh key per acquisition replays the snap-in and the flash
  const lockKey = locked ? `lock-${cluster.id}` : "acq";

  // keyed on the id: detection updates every second must not re-subscribe
  // (that would blank the published readout rect for a frame each time)
  const targetId = cluster?.id ?? null;
  useEffect(() => {
    if (targetId === null) return;
    const id = targetId;
    const off = hudBus.subscribe((list) => {
      const s = list.find((c) => c.id === id);
      const el = root.current;
      if (!el) return;
      if (!s || !s.visible) {
        el.style.opacity = "0";
        hudBus.readout = null;
        return;
      }
      const vw = window.innerWidth, vh = window.innerHeight;
      const R = Math.max(118, Math.min(s.r * 2.1 + 30, Math.min(vw, vh) * 0.36));
      el.style.opacity = "1";
      el.style.transform = `translate3d(${s.x}px, ${s.y}px, 0)`;
      if (ringBox.current) {
        ringBox.current.style.width = `${R * 2}px`;
        ringBox.current.style.height = `${R * 2}px`;
        ringBox.current.style.transform = `translate(${-R}px, ${-R}px)`;
      }
      // readout sits on whichever side has more room
      const right = s.x < vw * 0.62;
      if (readout.current) {
        const dx = right ? R + 70 : -R - 70 - 270;
        readout.current.style.transform = `translate(${dx}px, ${-R * 0.7 - 20}px)`;
        const x0 = s.x + dx, y0 = s.y - R * 0.7 - 20;
        hudBus.readout = useMirage.getState().selected === null ? { x0, y0, x1: x0 + 310, y1: y0 + 225 } : null;
      }
      if (leader.current) {
        const a = right ? -0.72 : Math.PI + 0.72;
        const x1 = Math.cos(a) * R * 0.98, y1 = Math.sin(a) * R * 0.98;
        const x2 = right ? R + 64 : -R - 64;
        const y2 = -R * 0.7 - 6;
        leader.current.setAttribute("x1", `${x1}`);
        leader.current.setAttribute("y1", `${y1}`);
        leader.current.setAttribute("x2", `${x2}`);
        leader.current.setAttribute("y2", `${y2}`);
      }
    });
    return () => {
      off();
      hudBus.readout = null;
    };
  }, [targetId]);

  const color = locked ? "#FF4D40" : "#FFB347";
  const faint = locked ? "rgba(255,77,64,0.45)" : "rgba(255,179,71,0.45)";

  return (
    <AnimatePresence>
      {cluster && view === "network" && (
        <motion.div
          key={cluster.id}
          ref={root}
          className="pointer-events-none absolute left-0 top-0 z-[15]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          style={{ willChange: "transform" }}
        >
          <svg className="absolute overflow-visible" style={{ left: 0, top: 0 }} width="1" height="1">
            <line ref={leader} stroke={faint} strokeWidth={1} />
          </svg>
          <div ref={ringBox} className="absolute left-0 top-0">
            <svg
              viewBox="-110 -110 220 220"
              className="h-full w-full overflow-visible"
              style={{ filter: `drop-shadow(0 0 3px ${locked ? "rgba(255,59,48,0.9)" : "rgba(255,159,28,0.8)"})` }}
            >
              <defs>
                <radialGradient id="ringGlow">
                  <stop offset="60%" stopColor={color} stopOpacity="0" />
                  <stop offset="100%" stopColor={color} stopOpacity={locked ? 0.14 : 0.06} />
                </radialGradient>
              </defs>
              <circle r="100" fill="url(#ringGlow)" />
              <g style={{ animation: "spin 48s linear infinite", transformOrigin: "0 0" }}>
                <circle r="92" fill="none" stroke={faint} strokeWidth={0.9} />
                <Ticks r={92} count={72} major={6} len={3} majorLen={7} color={faint} />
              </g>
              <g style={{ animation: "spin-rev 26s linear infinite", transformOrigin: "0 0" }}>
                <circle r="80" fill="none" stroke={color} strokeOpacity={0.7} strokeWidth={1.2} strokeDasharray="1.5 5.5" />
              </g>
              {[0, 1, 2, 3].map((q) => (
                <path
                  key={q}
                  d={describeArc(0, 0, 66, q * 90 + 10, q * 90 + 80)}
                  fill="none"
                  stroke={color}
                  strokeOpacity={0.85}
                  strokeWidth={1.5}
                />
              ))}
              {[0, 90, 180, 270].map((a) => (
                <line
                  key={a}
                  x1={Math.cos((a * Math.PI) / 180) * 98}
                  y1={Math.sin((a * Math.PI) / 180) * 98}
                  x2={Math.cos((a * Math.PI) / 180) * 108}
                  y2={Math.sin((a * Math.PI) / 180) * 108}
                  stroke={color}
                  strokeWidth={1.2}
                />
              ))}
              {!locked && (
                <g style={{ animation: "spin 2.4s linear infinite", transformOrigin: "0 0" }}>
                  <path d={describeArc(0, 0, 86, 0, 38)} fill="none" stroke={color} strokeWidth={2.2} strokeOpacity={0.85} />
                </g>
              )}
              <motion.g
                key={lockKey}
                initial={{ scale: locked ? 1.9 : 1.35, opacity: 0 }}
                animate={{ scale: locked ? [1.9, 0.93, 1] : 1.35, opacity: 1 }}
                transition={{ duration: locked ? 0.55 : 0.4, ease: [0.16, 1, 0.3, 1] }}
              >
                <Bracket x={-74} y={-74} sx={1} sy={1} color={color} />
                <Bracket x={74} y={-74} sx={-1} sy={1} color={color} />
                <Bracket x={-74} y={74} sx={1} sy={-1} color={color} />
                <Bracket x={74} y={74} sx={-1} sy={-1} color={color} />
              </motion.g>
              {locked && (
                <motion.circle
                  key={`flash-${lockKey}`}
                  r={70}
                  fill="none"
                  stroke="#FFD2C8"
                  initial={{ r: 40, opacity: 0.9, strokeWidth: 3 }}
                  animate={{ r: 108, opacity: 0, strokeWidth: 0.5 }}
                  transition={{ duration: 0.9, ease: "easeOut" }}
                />
              )}
              <text x={0} y={-115} textAnchor="middle" className="hud-value" fontSize={4.6} fill={color} letterSpacing={2.4}>
                {locked ? "TARGET LOCKED" : "TRACKING"}
              </text>
            </svg>
          </div>
          <div ref={readout} className="absolute left-0 top-0" style={{ visibility: selected === null ? "visible" : "hidden" }}>
            <motion.button
              type="button"
              onClick={() => {
                useMirage.getState().select(cluster.id);
                commands.evidence(cluster.id);
              }}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.15, duration: 0.5 }}
              className={`pointer-events-auto block text-left panel ${locked ? "panel-red" : ""} px-4 py-3 transition hover:brightness-125`}
            >
              <Readout locked={locked} cluster={cluster} />
            </motion.button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function polar(cx: number, cy: number, r: number, deg: number) {
  const a = ((deg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
}

function describeArc(cx: number, cy: number, r: number, start: number, end: number) {
  const s = polar(cx, cy, r, end);
  const e = polar(cx, cy, r, start);
  const large = end - start <= 180 ? 0 : 1;
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 0 ${e.x} ${e.y}`;
}
