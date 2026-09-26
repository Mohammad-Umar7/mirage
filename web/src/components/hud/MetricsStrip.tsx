"use client";

import { int, pct, simSpan } from "@/lib/format";
import { useMirage } from "@/lib/store";
import { AnimatedNumber } from "../ui/AnimatedNumber";

function Cell({ label, children, accent }: { label: string; children: React.ReactNode; accent?: "red" | "gold" }) {
  return (
    <div className="flex min-w-[92px] flex-col gap-1.5 px-4">
      <span className="hud-label !text-[8.5px]">{label}</span>
      <span className={`hud-value text-[17px] leading-none ${accent === "red" ? "text-red-glow" : accent === "gold" ? "text-gold-soft" : "text-ink"}`}>
        {children}
      </span>
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <svg width={64} height={18} />;
  const max = Math.max(1000, ...values);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 64},${18 - (v / max) * 16}`).join(" ");
  const budget = 18 - (1000 / max) * 16;
  return (
    <svg width={64} height={18} className="overflow-visible">
      <line x1={0} x2={64} y1={budget} y2={budget} stroke="rgba(255,59,48,0.35)" strokeDasharray="2 3" strokeWidth={0.8} />
      <polyline points={pts} fill="none" stroke="#F5B94A" strokeWidth={1.1} />
    </svg>
  );
}

const fmtPct = (v: number) => pct(v, 1);
const fmtF1 = (v: number) => v.toFixed(3);
const fmtMs = (v: number) => `${Math.round(v)} ms`;
const fmtInt = (v: number) => int(v);

export function MetricsStrip() {
  const m = useMirage((s) => s.metrics);
  const tick = useMirage((s) => s.tick);
  const status = useMirage((s) => s.status);
  const history = useMirage((s) => s.latencyHistory);
  const launched = useMirage((s) => s.launches.length > 0);
  const live = status === "live";

  return (
    <div className="pointer-events-auto absolute bottom-9 left-1/2 z-20 -translate-x-1/2">
      <div className="panel flex items-stretch py-3">
        <Cell label="Precision">
          <AnimatedNumber value={launched ? m?.precision : null} format={fmtPct} />
        </Cell>
        <Cell label="Recall">
          <AnimatedNumber value={launched ? m?.recall : null} format={fmtPct} />
        </Cell>
        <Cell label="F1">
          <AnimatedNumber value={launched ? m?.f1 : null} format={fmtF1} />
        </Cell>
        <Cell label="Hard-neg FP" accent={m && m.hard_negative_fp > 0 ? "red" : "gold"}>
          <AnimatedNumber value={m?.hard_negative_fp ?? 0} format={fmtInt} />
        </Cell>
        <Cell label="Detect latency">
          <span>{launched ? simSpan(m?.detection_latency_min) : "—"}</span>
        </Cell>
        <div className="mx-1 w-px bg-[var(--hair)]" />
        <Cell label="Pipeline">
          <span className="flex items-center gap-3">
            <AnimatedNumber value={m?.pipeline_latency_ms} format={fmtMs} duration={0.4} />
            <Sparkline values={history} />
          </span>
        </Cell>
        <div className="mx-1 w-px bg-[var(--hair)]" />
        <div className="flex flex-col justify-center gap-1.5 px-5">
          <span className="flex items-center gap-2">
            <span className={`relative inline-flex h-2 w-2 ${live ? "" : "opacity-40"}`}>
              {live && <span className="absolute inset-0 animate-ping rounded-full bg-red opacity-60" />}
              <span className={`relative inline-flex h-2 w-2 rounded-full ${live ? "bg-red shadow-[0_0_10px_#FF3B30]" : "bg-[var(--ink-faint)]"}`} />
            </span>
            <span className={`hud-label !text-[10px] !tracking-[0.34em] ${live ? "!text-red-glow" : ""}`}>{live ? "Live" : status}</span>
          </span>
          <span className="hud-value text-[11px] text-[var(--ink-dim)]">tick {int(tick)}</span>
        </div>
      </div>
      <div className="mt-2 text-center hud-label !text-[7.5px] !text-[var(--ink-faint)]">
        precision · recall · false positives scored against ground truth after detection — the detector never sees labels
      </div>
    </div>
  );
}
