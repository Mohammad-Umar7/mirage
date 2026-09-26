"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { useOnchainTally } from "@/lib/chain";
import { int, shortAddr, simSpan } from "@/lib/format";
import type { Proposal, Tally } from "@/lib/protocol";
import { useMirage } from "@/lib/store";
import { kickAberration } from "@/lib/viewState";
import { AnimatedNumber } from "../ui/AnimatedNumber";

const fmt1 = (v: number) => (v >= 100 ? int(v) : v.toFixed(v % 1 === 0 ? 0 : 1));

function Bar({ label, value, total, color, glow }: { label: string; value: number; total: number; color: string; glow?: boolean }) {
  const pct = total > 0 ? value / total : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="hud-label !text-[10px] !tracking-[0.3em]">{label}</span>
        <AnimatedNumber value={value} format={fmt1} duration={1.2} className="hud-value text-[30px] font-light leading-none text-ink" />
      </div>
      <div className="mt-2 h-[6px] w-full bg-[rgba(243,233,216,0.07)]">
        <motion.div
          className="h-full"
          style={{ background: color, boxShadow: glow ? `0 0 14px ${color}` : undefined }}
          animate={{ width: `${Math.max(0.4, pct * 100)}%` }}
          transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>
    </div>
  );
}

function Column({ title, subtitle, tally, weighted }: { title: string; subtitle: string; tally: Tally; weighted: boolean }) {
  const total = tally.yes + tally.no;
  const passing = tally.yes > tally.no;
  const outcomeColor = passing ? "#FF3B30" : "#F5B94A";
  return (
    <div className={`panel ${weighted && !passing ? "" : passing ? "panel-red" : ""} relative flex-1 px-7 py-6`}>
      <div className="flex items-center justify-between">
        <span className={`hud-label !text-[10px] !tracking-[0.3em] ${weighted ? "!text-gold-soft" : ""}`}>{title}</span>
        <span className="hud-label !text-[8px] !text-[var(--ink-faint)]">{subtitle}</span>
      </div>
      <div className="mt-6 space-y-5">
        <Bar label="Yes · transfer" value={tally.yes} total={total} color="#FF3B30" glow={passing} />
        <Bar label="No · keep treasury" value={tally.no} total={total} color="#F5B94A" glow={!passing} />
      </div>
      <div className="mt-6 flex items-center gap-3">
        <span className="h-px flex-1" style={{ background: `linear-gradient(90deg, ${outcomeColor}, transparent)` }} />
        <AnimatePresence mode="wait">
          <motion.span
            key={passing ? "pass" : "reject"}
            initial={{ opacity: 0, y: 8, filter: "blur(6px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -8, filter: "blur(6px)" }}
            transition={{ duration: 0.45 }}
            className={`hud-label !text-[12px] !tracking-[0.34em] ${passing ? "!text-red-glow glow-red" : "!text-gold-soft glow-gold"}`}
          >
            {passing ? "▲ attack passes" : "✓ honest result wins"}
          </motion.span>
        </AnimatePresence>
      </div>
    </div>
  );
}

// 1,000 ballots collapse into one voice once the swarm is flagged.
function Collapse({ size, collapsed }: { size: number; collapsed: boolean }) {
  const dots = useMemo(() => Array.from({ length: 120 }, (_, i) => ({ x: (i % 24) * 13, y: Math.floor(i / 24) * 13, d: (i * 37) % 11 })), []);
  return (
    <div className="flex items-center gap-10">
      <div className="relative h-[64px] w-[312px]">
        {dots.map((p, i) => (
          <motion.span
            key={i}
            className="absolute h-[5px] w-[5px] rounded-full bg-red shadow-[0_0_6px_#FF3B30]"
            initial={false}
            animate={
              collapsed
                ? { left: 154, top: 28, opacity: i === 0 ? 1 : 0, scale: i === 0 ? 2.2 : 0.4 }
                : { left: p.x, top: p.y, opacity: 0.85, scale: 1 }
            }
            transition={{ duration: 1.1, delay: collapsed ? p.d * 0.05 : 0, ease: [0.65, 0, 0.35, 1] }}
          />
        ))}
      </div>
      <div>
        <div className="hud-value text-[22px] font-light text-ink">
          {int(size)} <span className="text-[13px] text-[var(--ink-dim)]">swarm ballots</span>
          <span className="mx-3 text-gold">→</span>
          <span className={collapsed ? "text-gold-soft glow-gold" : "text-[var(--ink-faint)]"}>{collapsed ? "1 voice" : "…"}</span>
        </div>
        <div className="mt-1 hud-label !text-[8.5px] !normal-case !tracking-[0.1em]">
          a flagged cluster of n accounts carries a total weight of 1 (or ln n) — the swarm&apos;s only advantage, numbers, is gone
        </div>
      </div>
    </div>
  );
}

function pickProposal(proposals: Proposal[], chosen: number | null) {
  if (chosen !== null) {
    const p = proposals.find((x) => x.id === chosen);
    if (p) return p;
  }
  const attacks = proposals.filter((p) => p.title.startsWith("Transfer treasury"));
  return attacks[attacks.length - 1] ?? proposals[proposals.length - 1] ?? null;
}

export function GovernanceView() {
  const view = useMirage((s) => s.view);
  const proposals = useMirage((s) => s.proposals);
  const chain = useMirage((s) => s.chain);
  const t = useMirage((s) => s.t);
  const detection = useMirage((s) => s.detection);
  const [chosen, setChosen] = useState<number | null>(null);
  const active = view === "governance";
  const proposal = pickProposal(proposals, chosen);
  const onchain = useOnchainTally(proposal?.id ?? null, active);
  const chainTally = proposal && chain?.onchain?.[String(proposal.id)];

  const naive = onchain?.naive ?? chainTally?.naive ?? proposal?.naive ?? { yes: 0, no: 0 };
  const weighted = onchain?.weighted ?? chainTally?.weighted ?? proposal?.weighted ?? { yes: 0, no: 0 };
  const source = onchain ? "read on-chain via viem" : chainTally ? "on-chain (relayed)" : "off-chain tally · chain offline";
  const swarm = detection?.clusters.find((c) => c.verdict === "SWARM" && c.confidence >= 0.8);
  const flippedRef = useRef<boolean | null>(null);
  const flipped = naive.yes > naive.no && weighted.yes <= weighted.no;

  useEffect(() => {
    if (!active) return;
    if (flippedRef.current === false && flipped) kickAberration(1.6);
    flippedRef.current = flipped;
  }, [flipped, active]);

  return (
    <AnimatePresence>
      {active && proposal && (
        <motion.div
          key="gov"
          initial={{ opacity: 0, y: 24, scale: 0.985 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 24, scale: 0.985 }}
          transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
          className="pointer-events-auto absolute left-1/2 top-[118px] z-30 w-[min(1120px,calc(100vw-120px))] -translate-x-1/2"
        >
          <div className="flex items-end justify-between">
            <div>
              <div className="flex items-center gap-3">
                <span className="hud-label !text-[10px] !tracking-[0.32em] !text-gold-soft">Governance · live proposal</span>
                {proposals.length > 1 && (
                  <div className="flex gap-1">
                    {proposals.map((p) => (
                      <button
                        key={p.id}
                        onClick={() => setChosen(p.id)}
                        className={`border px-2 py-0.5 hud-value text-[10px] transition ${p.id === proposal.id ? "border-gold text-gold-soft" : "border-[rgba(243,233,216,0.15)] text-[var(--ink-dim)] hover:text-ink"}`}
                      >
                        #{p.id}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <h2 className="mt-3 text-[28px] font-light tracking-[0.04em] text-ink">
                <span className="text-gold">Proposal #{proposal.id}</span> · {proposal.title.replace("Transfer treasury to", "Transfer treasury to")}
              </h2>
              <div className="mt-2 flex gap-6 hud-label !text-[9px]">
                {proposal.amount > 0 && <span>{int(proposal.amount)} MRG</span>}
                <span>{proposal.open ? `voting open · closes in ${simSpan(proposal.closes_at - t)}` : "voting closed"}</span>
                <span>{int(proposal.votes)} ballots</span>
                {proposal.recipient && <span>recipient {shortAddr(proposal.recipient)}</span>}
              </div>
            </div>
            <div className="text-right">
              <div className="flex items-center justify-end gap-2">
                <span className={`h-2 w-2 rounded-full ${chain?.connected ? "bg-gold shadow-[0_0_10px_#F5B94A]" : "bg-[var(--ink-faint)]"}`} />
                <span className="hud-label !text-[9px]">{chain?.connected ? `chain ${chain.chain_id} · block ${int(onchain?.block ?? chain.block ?? 0)}` : "chain offline"}</span>
              </div>
              <div className="mt-1 hud-label !text-[8px] !text-[var(--ink-faint)]">{source}</div>
            </div>
          </div>

          <div className="mt-6 flex gap-5">
            <Column title="One account = one vote" subtitle="naive" tally={naive} weighted={false} />
            <Column title="MIRAGE · correlation-weighted" subtitle={`mode: ${chain?.mode === "log" ? "ln n" : "1"} per flagged cluster`} tally={weighted} weighted />
          </div>

          <div className="panel mt-5 px-7 py-5">
            <Collapse size={swarm?.size ?? 0} collapsed={!!swarm && (onchain?.epoch ?? chainTally?.epoch ?? 1) > 0} />
          </div>

          <div className="panel mt-5 px-7 py-4">
            <div className="flex items-center justify-between">
              <span className="hud-label !text-[9px]">On-chain · MirageGovernance</span>
              <span className="hud-value text-[11px] text-gold-soft">{chain?.address ?? "not deployed"}</span>
            </div>
            <div className="mt-1 flex gap-6 hud-label !text-[8.5px]">
              <span>oracle {shortAddr(chain?.oracle)}</span>
              <span>attestation epoch {onchain?.epoch ?? chainTally?.epoch ?? 0}</span>
              {onchain && <span>{int(onchain.registered)} accounts registered</span>}
              <span className="!text-[var(--ink-faint)]">oracle = trust assumption · see README</span>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-x-8 gap-y-1">
              {[
                ...(chain?.txs ?? []).filter((x) => x.kind === "oracle" || x.kind === "attest").slice(0, 4),
                ...(chain?.txs ?? []).filter((x) => x.kind === "votes" || x.kind === "proposal").slice(0, 4),
              ].map((tx) => (
                <motion.div key={tx.hash} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} className="flex items-center gap-3 text-[10.5px]">
                  <span className={`hud-label !text-[8px] w-[52px] ${tx.kind === "oracle" || tx.kind === "attest" ? "!text-gold-soft" : ""}`}>{tx.kind}</span>
                  <span className="hud-value text-[var(--ink-dim)]">{tx.hash.slice(0, 10)}…{tx.hash.slice(-6)}</span>
                  <span className="truncate text-[var(--ink-faint)]">{tx.detail}</span>
                </motion.div>
              ))}
              {!chain?.txs?.length && <span className="hud-label !text-[8.5px]">no transactions yet</span>}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
