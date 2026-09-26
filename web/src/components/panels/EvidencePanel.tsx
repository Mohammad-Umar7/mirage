"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo } from "react";
import { int } from "@/lib/format";
import { commands } from "@/lib/socket";
import { useMirage } from "@/lib/store";
import { ActivityTimeline, ConfidenceArc, FundingTree, SimilarityHeatmap } from "./charts";

const FAMILY_ICON: Record<string, string> = {
  funding: "◆",
  timing: "◷",
  content: "❝",
  style: "✎",
  voting: "▣",
  behavior: "↻",
  lifecycle: "◌",
  latency: "⚡",
  social: "⋈",
};

// Highlight the numbers inside an evidence sentence.
function Emph({ text, swarm }: { text: string; swarm: boolean }) {
  const parts = text.split(/(\d[\d,.]*\s?(?:%|h|m|ms|min|minutes|hours|days|seconds|second|wallets?|hops?|accounts)?)/g);
  return (
    <>
      {parts.map((p, i) =>
        /^\d/.test(p) ? (
          <span key={i} className={`hud-value ${swarm ? "text-red-glow" : "text-gold-soft"}`}>
            {p}
          </span>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}

function Section({ title, children, delay = 0 }: { title: string; children: React.ReactNode; delay?: number }) {
  return (
    <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.45 }} className="mt-5">
      <div className="mb-2 flex items-center gap-2">
        <span className="hud-label !text-[8.5px]">{title}</span>
        <span className="h-px flex-1 bg-gradient-to-r from-[var(--hair)] to-transparent" />
      </div>
      {children}
    </motion.section>
  );
}

export function EvidencePanel() {
  const selected = useMirage((s) => s.selected);
  const evidence = useMirage((s) => s.evidence);
  const detection = useMirage((s) => s.detection);
  const select = useMirage((s) => s.select);
  const view = useMirage((s) => s.view);

  const cluster = useMemo(() => detection?.clusters.find((c) => c.id === selected) ?? null, [detection, selected]);
  const detail = evidence && evidence.cluster.id === selected ? evidence : null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") select(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [select]);

  useEffect(() => {
    if (selected !== null && !detail) commands.evidence(selected);
  }, [selected, detail]);

  const open = selected !== null && view === "network";
  const swarm = (cluster?.verdict ?? detail?.cluster.verdict) === "SWARM";
  const info = cluster ?? detail?.cluster ?? null;
  const ev = cluster?.evidence ?? detail?.cluster.evidence ?? [];

  return (
    <AnimatePresence>
      {open && info && (
        <motion.aside
          key="evidence"
          initial={{ x: 480, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 480, opacity: 0 }}
          transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
          className={`pointer-events-auto absolute right-10 top-[112px] bottom-[128px] z-30 w-[440px] overflow-y-auto scrollbar-none panel ${swarm ? "panel-red" : ""}`}
        >
          <div className="px-6 pb-6 pt-5">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rotate-45 ${swarm ? "bg-red shadow-[0_0_10px_#FF3B30]" : "bg-gold shadow-[0_0_10px_#F5B94A]"}`} />
                  <span className={`hud-label !text-[10px] !tracking-[0.3em] ${swarm ? "!text-red-glow" : "!text-gold-soft"}`}>
                    {swarm ? "Swarm · evidence" : "Organic community · not flagged"}
                  </span>
                </div>
                <div className="mt-3 flex items-baseline gap-3">
                  <span className={`text-[34px] font-light leading-none ${swarm ? "text-red-glow glow-red" : "text-gold-soft glow-gold"}`}>
                    {int(info.size)}
                  </span>
                  <span className="hud-label">accounts · cluster #{info.id}</span>
                </div>
                {info.level_estimate != null && (
                  <div className="mt-2 hud-label !text-[9px]">
                    estimated sophistication · level <span className="hud-value text-ink">{info.level_estimate}</span>
                  </div>
                )}
              </div>
              <div className="flex flex-col items-end gap-1">
                <button onClick={() => select(null)} className="hud-label !text-[9px] hover:!text-ink">
                  close · esc
                </button>
                <ConfidenceArc value={info.confidence} swarm={swarm} />
                <span className="hud-label !text-[7.5px]">confidence</span>
              </div>
            </div>

            <Section title={swarm ? "Evidence" : "Why it was not flagged"} delay={0.1}>
              <div className="space-y-2">
                {ev.map((e, i) => (
                  <motion.div
                    key={e.title + i}
                    initial={{ opacity: 0, x: 16 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.18 + i * 0.09, duration: 0.4 }}
                    className="relative overflow-hidden border border-[rgba(243,233,216,0.08)] bg-[rgba(0,0,0,0.28)] px-3.5 py-2.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-2 hud-label !text-[8.5px]">
                        <span className={swarm ? "text-red-glow" : "text-gold"}>{FAMILY_ICON[e.family] ?? "•"}</span>
                        {e.title}
                      </span>
                      <span className="hud-value text-[9px] text-[var(--ink-faint)]">{((e.strength ?? 0) * 100).toFixed(0)}</span>
                    </div>
                    <div className="mt-1.5 text-[12px] leading-snug text-ink/85">
                      <Emph text={e.text} swarm={swarm} />
                    </div>
                    <motion.div
                      className="absolute bottom-0 left-0 h-px"
                      style={{ background: swarm ? "#FF3B30" : "#F5B94A", boxShadow: `0 0 8px ${swarm ? "#FF3B30" : "#F5B94A"}` }}
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.round((e.strength ?? 0) * 100)}%` }}
                      transition={{ delay: 0.4 + i * 0.09, duration: 0.8 }}
                    />
                  </motion.div>
                ))}
              </div>
            </Section>

            {detail ? (
              <>
                <Section title="Synchronized activity · last 48h" delay={0.35}>
                  <ActivityTimeline data={detail.timeline} swarm={swarm} />
                  <div className="mt-1 flex gap-4 hud-label !text-[8px]">
                    <span className="flex items-center gap-1.5">
                      <span className={`h-px w-4 ${swarm ? "bg-red" : "bg-gold-soft"}`} /> this cluster (per account)
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="h-px w-4 border-t border-dashed border-gold" /> typical accounts
                    </span>
                  </div>
                </Section>
                <Section title={`Funding ancestry · ${detail.funding.accounts} sampled accounts → ${detail.funding.roots} roots`} delay={0.5}>
                  <FundingTree data={detail.funding} swarm={swarm} />
                </Section>
                <Section title="Cross-signal similarity" delay={0.65}>
                  <SimilarityHeatmap data={detail.heatmap} swarm={swarm} />
                </Section>
                {detail.posts.length > 0 && (
                  <Section title="What they post" delay={0.8}>
                    <div className="space-y-2">
                      {detail.posts.slice(0, 4).map((p, i) => (
                        <div key={i} className="border-l border-[var(--hair)] pl-3 text-[11px] leading-snug text-[var(--ink-dim)]">
                          <span className={`hud-value mr-1.5 ${swarm ? "text-red-glow" : "text-gold"}`}>@{p.handle}</span>
                          {p.text}
                        </div>
                      ))}
                    </div>
                  </Section>
                )}
              </>
            ) : (
              <div className="mt-6 flex items-center gap-3 hud-label">
                <span className="h-3 w-3 animate-spin rounded-full border border-[var(--hair-strong)] border-t-transparent" />
                pulling evidence
              </div>
            )}
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
