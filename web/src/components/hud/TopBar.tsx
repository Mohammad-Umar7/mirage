"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { int } from "@/lib/format";
import { useMirage, type View } from "@/lib/store";
import { AnimatedNumber } from "../ui/AnimatedNumber";

const VIEWS: { id: View; label: string; key: string }[] = [
  { id: "network", label: "Network", key: "1" },
  { id: "terrain", label: "Pulse terrain", key: "2" },
  { id: "governance", label: "Governance", key: "3" },
];

function Wordmark() {
  return (
    <div className="select-none">
      <div className="flex items-end gap-3">
        <h1
          className="text-[30px] leading-none font-light tracking-[0.42em] text-transparent bg-clip-text bg-gradient-to-b from-[#FFE2A8] via-[#F5B94A] to-[#B8741C] glow-gold"
          style={{ fontFamily: "var(--font-sans)" }}
        >
          MIRAGE
        </h1>
        <span className="hud-label mb-[3px] text-[8.5px] !text-[rgba(245,185,74,0.7)]">v1 · live</span>
      </div>
      <div className="hud-label mt-2 !text-[9px] !tracking-[0.26em]">Sybil resistance under agent swarms</div>
    </div>
  );
}

function AccountCounter() {
  const n = useMirage((s) => s.nAccounts);
  const base = useMirage((s) => s.baselineAccounts);
  const launches = useMirage((s) => s.launches);
  const [flash, setFlash] = useState(false);
  const prev = useRef(n);
  useEffect(() => {
    // flash only when accounts pour in, not when the first snapshot arrives
    if (prev.current > 0 && n - prev.current > 20) {
      setFlash(true);
      const t = setTimeout(() => setFlash(false), 900);
      prev.current = n;
      return () => clearTimeout(t);
    }
    prev.current = n;
  }, [n]);
  const grew = launches.length > 0 && n > base;
  return (
    <div className="flex items-baseline gap-2">
      <span className="hud-label">Accounts</span>
      {grew && (
        <>
          <span className="hud-value text-[15px] text-[var(--ink-dim)]">{int(base)}</span>
          <span className="hud-value text-[13px] text-[var(--ink-faint)]">→</span>
        </>
      )}
      <AnimatedNumber
        value={n}
        format={int}
        duration={0.8}
        className={`hud-value text-[17px] transition-colors duration-500 ${flash ? "text-red glow-red" : "text-ink"}`}
      />
    </div>
  );
}

export function TopBar() {
  const clock = useMirage((s) => s.clock);
  const view = useMirage((s) => s.view);
  const setView = useMirage((s) => s.setView);
  const rate = useMirage((s) => s.rate);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      const v = VIEWS.find((x) => x.key === e.key);
      if (v) setView(v.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setView]);

  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-start justify-between px-10 pt-9">
      <div className="pointer-events-auto">
        <Wordmark />
      </div>

      <div className="absolute left-1/2 top-9 -translate-x-1/2 flex flex-col items-center gap-2">
        <div className="flex items-center gap-3">
          <span className="h-px w-10 bg-gradient-to-r from-transparent to-[var(--hair-strong)]" />
          <AnimatePresence mode="popLayout">
            <motion.span
              key={clock}
              initial={{ opacity: 0.4, y: -3 }}
              animate={{ opacity: 1, y: 0 }}
              className="hud-value text-[13px] tracking-[0.28em] text-gold-soft"
            >
              {clock}
            </motion.span>
          </AnimatePresence>
          <span className="h-px w-10 bg-gradient-to-l from-transparent to-[var(--hair-strong)]" />
        </div>
        <div className="flex items-center gap-6">
          <AccountCounter />
          <span className="hud-label">{rate > 0 ? `${rate.toFixed(rate < 1 ? 1 : 0)} sim-hour / s` : "paused"}</span>
        </div>
      </div>

      <nav className="pointer-events-auto flex items-center gap-1">
        {VIEWS.map((v) => {
          const active = view === v.id;
          return (
            <button
              key={v.id}
              onClick={() => setView(v.id)}
              className={`group relative px-4 py-2 hud-label !text-[9.5px] transition-colors ${active ? "!text-gold-soft" : "hover:!text-ink"}`}
            >
              <span className="mr-2 text-[var(--ink-faint)]">{v.key}</span>
              {v.label}
              {active && (
                <motion.span layoutId="view-underline" className="absolute inset-x-3 -bottom-px h-px bg-gold shadow-[0_0_12px_#F5B94A]" />
              )}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
