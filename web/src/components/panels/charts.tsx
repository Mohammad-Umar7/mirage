"use client";

import { motion } from "framer-motion";
import { useMemo } from "react";
import type { EvidenceDetail } from "@/lib/protocol";

const RED = "#FF3B30";
const GOLD = "#F5B94A";

// ---------------------------------------------------------------- timeline
export function ActivityTimeline({ data, swarm }: { data: EvidenceDetail["timeline"]; swarm: boolean }) {
  const W = 392, H = 118, pad = 6;
  const { cluster, baseline } = data;
  const max = Math.max(1e-6, ...cluster, ...baseline) * 1.08;
  const toPath = (vals: number[]) =>
    vals.map((v, i) => `${i ? "L" : "M"} ${pad + (i / (vals.length - 1)) * (W - pad * 2)} ${H - pad - (v / max) * (H - pad * 2)}`).join(" ");
  const area = (vals: number[]) => `${toPath(vals)} L ${W - pad} ${H - pad} L ${pad} ${H - pad} Z`;
  const main = swarm ? RED : GOLD;
  return (
    <svg viewBox={`0 0 ${W} ${H + 16}`} className="w-full">
      <defs>
        <linearGradient id="tl-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={main} stopOpacity={0.45} />
          <stop offset="100%" stopColor={main} stopOpacity={0} />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((f) => (
        <line key={f} x1={pad} x2={W - pad} y1={H * f} y2={H * f} stroke="rgba(243,233,216,0.06)" />
      ))}
      <motion.path d={toPath(baseline)} fill="none" stroke={GOLD} strokeOpacity={0.7} strokeWidth={1.1} strokeDasharray="3 3"
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.1, ease: "easeOut" }} />
      <motion.path d={area(cluster)} fill="url(#tl-fill)" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5, duration: 0.8 }} />
      <motion.path d={toPath(cluster)} fill="none" stroke={main} strokeWidth={1.6}
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.4, ease: "easeOut", delay: 0.15 }} />
      {["−48h", "−36h", "−24h", "−12h", "now"].map((lbl, i) => (
        <text key={lbl} x={pad + (i / 4) * (W - pad * 2)} y={H + 12} fontSize={8} fill="rgba(243,233,216,0.4)"
          textAnchor={i === 0 ? "start" : i === 4 ? "end" : "middle"} className="hud-value">
          {lbl}
        </text>
      ))}
    </svg>
  );
}

// ------------------------------------------------------------ funding tree
type TreeNode = EvidenceDetail["funding"]["nodes"][number] & { x: number; y: number };

export function FundingTree({ data, swarm }: { data: EvidenceDetail["funding"]; swarm: boolean }) {
  const W = 392, H = 176;
  const layout = useMemo(() => {
    const nodes = new Map<number, TreeNode>();
    const maxDepth = Math.max(1, data.max_depth);
    for (const n of data.nodes) nodes.set(n.id, { ...n, x: 0, y: 0 });
    const children = new Map<number, number[]>();
    for (const [src, dst] of data.edges) {
      if (!children.has(src)) children.set(src, []);
      children.get(src)!.push(dst);
    }
    const accounts = [...nodes.values()].filter((n) => n.kind === "account");
    accounts.forEach((n, i) => {
      n.x = 14 + (i / Math.max(1, accounts.length - 1)) * (W - 28);
      n.y = H - 12;
    });
    // parents sit above the mean of their children, level by level
    for (let d = 1; d <= maxDepth; d++) {
      for (const n of nodes.values()) {
        if (n.depth !== d || n.kind === "account") continue;
        const kids = (children.get(n.id) ?? []).map((k) => nodes.get(k)).filter(Boolean) as TreeNode[];
        n.x = kids.length ? kids.reduce((s, k) => s + k.x, 0) / kids.length : W / 2;
        n.y = H - 12 - (d / maxDepth) * (H - 40);
      }
    }
    // hubs (exchanges) float at the top
    for (const n of nodes.values()) if (n.kind === "hub") n.y = 16;
    return nodes;
  }, [data]);

  const edgeColor = swarm ? "rgba(255,90,70,0.55)" : "rgba(245,185,74,0.45)";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {data.edges.map(([src, dst], i) => {
        const a = layout.get(src), b = layout.get(dst);
        if (!a || !b) return null;
        const my = (a.y + b.y) / 2;
        return (
          <motion.path
            key={`${src}-${dst}`}
            d={`M ${b.x} ${b.y} C ${b.x} ${my}, ${a.x} ${my}, ${a.x} ${a.y}`}
            fill="none"
            stroke={edgeColor}
            strokeWidth={0.9}
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 0.9, delay: 0.2 + (b.depth ?? 0) * 0.35 + (i % 7) * 0.02, ease: "easeOut" }}
          />
        );
      })}
      {[...layout.values()].map((n) => {
        const root = n.kind === "root";
        const hub = n.kind === "hub";
        const r = n.kind === "account" ? 2.2 : root ? 5.5 : hub ? 5 : 3;
        const fill = n.kind === "account" ? (swarm ? RED : GOLD) : root ? (swarm ? RED : GOLD) : hub ? "#9aa0a6" : "#FFB347";
        return (
          <motion.g key={n.id} initial={{ opacity: 0, scale: 0.4 }} animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.1 + n.depth * 0.35, duration: 0.4 }} style={{ transformOrigin: `${n.x}px ${n.y}px` }}>
            {(root || hub) && <circle cx={n.x} cy={n.y} r={r + 5} fill="none" stroke={fill} strokeOpacity={0.35} />}
            <circle cx={n.x} cy={n.y} r={r} fill={fill} style={{ filter: root ? `drop-shadow(0 0 6px ${fill})` : undefined }} />
            {(root || hub) && (
              <text x={n.x} y={n.y - r - 8} textAnchor="middle" fontSize={7.5} fill="rgba(243,233,216,0.75)" className="hud-value">
                {n.label}
              </text>
            )}
          </motion.g>
        );
      })}
    </svg>
  );
}

// --------------------------------------------------------------- heatmap
function heat(v: number, swarm: boolean) {
  const t = Math.min(1, Math.max(0, v / 0.85));
  if (swarm) {
    const r = Math.round(18 + t * (255 - 18)), g = Math.round(10 + t * t * 70), b = Math.round(6 + t * t * 50);
    return `rgb(${r},${g},${b})`;
  }
  const r = Math.round(18 + t * (245 - 18)), g = Math.round(10 + t * (185 - 10)), b = Math.round(6 + t * (74 - 6));
  return `rgb(${r},${g},${b})`;
}

export function SimilarityHeatmap({ data, swarm }: { data: EvidenceDetail["heatmap"]; swarm: boolean }) {
  const n = data.size;
  const cell = 392 / Math.max(1, n) / 1.25;
  const size = cell * n;
  return (
    <div className="flex items-center gap-4">
      <svg viewBox={`0 0 ${size} ${size}`} style={{ width: size, height: size }}>
        {data.values.map((v, k) => {
          const i = Math.floor(k / n), j = k % n;
          return (
            <motion.rect key={k} x={j * cell} y={i * cell} width={cell - 0.6} height={cell - 0.6} fill={heat(v, swarm)}
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 + (i + j) * 0.018, duration: 0.3 }} />
          );
        })}
        <line x1={data.split * cell} x2={data.split * cell} y1={0} y2={size} stroke="rgba(243,233,216,0.5)" strokeDasharray="2 2" />
        <line y1={data.split * cell} y2={data.split * cell} x1={0} x2={size} stroke="rgba(243,233,216,0.5)" strokeDasharray="2 2" />
      </svg>
      <div className="space-y-2 text-[10px] leading-snug text-[var(--ink-dim)]">
        <div>
          <span className="hud-label !text-[8px] block">top-left</span>
          {data.split} cluster members vs each other
        </div>
        <div>
          <span className="hud-label !text-[8px] block">bottom-right</span>
          {n - data.split} typical accounts
        </div>
        <div className="flex items-center gap-1.5 pt-1">
          <span className="h-2 w-10" style={{ background: `linear-gradient(90deg, ${heat(0, swarm)}, ${heat(0.85, swarm)})` }} />
          <span className="hud-label !text-[7.5px]">similarity</span>
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------- confidence arc
export function ConfidenceArc({ value, swarm }: { value: number; swarm: boolean }) {
  const r = 30, c = Math.PI * r;
  const color = swarm ? RED : GOLD;
  return (
    <svg viewBox="-36 -36 72 42" className="h-[52px] w-[88px]">
      <path d={`M ${-r} 0 A ${r} ${r} 0 0 1 ${r} 0`} fill="none" stroke="rgba(243,233,216,0.1)" strokeWidth={4} />
      <motion.path d={`M ${-r} 0 A ${r} ${r} 0 0 1 ${r} 0`} fill="none" stroke={color} strokeWidth={4} strokeDasharray={c}
        initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - value) }} transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
        style={{ filter: `drop-shadow(0 0 4px ${color})` }} />
      <text x={0} y={-4} textAnchor="middle" fontSize={13} fill="#F3E9D8" className="hud-value">
        {value.toFixed(2)}
      </text>
    </svg>
  );
}
