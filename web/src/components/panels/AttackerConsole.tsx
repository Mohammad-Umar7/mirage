"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";
import { int, usd } from "@/lib/format";
import { LEVEL_COLORS } from "@/lib/palette";
import { commands } from "@/lib/socket";
import { useMirage } from "@/lib/store";

const MIN = 100;
const MAX = 10000;
const toSize = (x: number) => Math.round(MIN * Math.pow(MAX / MIN, x) / 50) * 50 || MIN;
const toX = (size: number) => Math.log(size / MIN) / Math.log(MAX / MIN);

const SHORT = ["Naive", "Basic", "Smart", "Advanced", "Independent"];

function CostMeter({ cost }: { cost: number }) {
  // log scale $0.01 → $100
  const x = Math.min(1, Math.max(0, (Math.log10(cost) + 2) / 4));
  const cells = 24;
  return (
    <div className="flex gap-[3px]">
      {Array.from({ length: cells }, (_, k) => {
        const on = k / cells < x;
        const hot = k / cells;
        return (
          <motion.span
            key={k}
            className="h-3 flex-1"
            animate={{
              backgroundColor: on ? `rgba(255, ${Math.round(185 - hot * 140)}, ${Math.round(74 - hot * 40)}, ${0.35 + hot * 0.6})` : "rgba(243,233,216,0.07)",
              boxShadow: on && hot > 0.6 ? "0 0 8px rgba(255,59,48,0.55)" : "0 0 0 rgba(0,0,0,0)",
            }}
            transition={{ duration: 0.35, delay: k * 0.012 }}
          />
        );
      })}
    </div>
  );
}

export function AttackerConsole() {
  const levels = useMirage((s) => s.levels);
  const launches = useMirage((s) => s.launches);
  const demo = useMirage((s) => s.demo.active);
  const view = useMirage((s) => s.view);
  const [x, setX] = useState(toX(1000));
  const [level, setLevel] = useState(3);
  const [open, setOpen] = useState(true);
  const size = toSize(x);
  const spec = useMemo(() => levels.find((l) => l.level === level), [levels, level]);
  const cost = spec?.cost_per_identity ?? 1;

  if (view === "governance") return null;
  return (
    <div className="pointer-events-auto absolute left-10 top-[132px] z-20 w-[300px]">
      <button onClick={() => setOpen((o) => !o)} className="group flex w-full items-center justify-between pb-2">
        <span className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rotate-45 bg-red shadow-[0_0_8px_#FF3B30]" />
          <span className="hud-label !text-[10px] !tracking-[0.3em] !text-red-glow">Attacker console</span>
        </span>
        <span className="hud-label !text-[9px] group-hover:!text-ink">{open ? "–" : "+"}</span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="panel panel-red px-5 py-4">
              <div className="hud-label !normal-case !tracking-[0.08em] !text-[10px] !text-[var(--ink-faint)]">
                play the operator: spin up agents that each look like an ordinary person
              </div>

              <div className="mt-4 flex items-baseline justify-between">
                <span className="hud-label">Swarm size</span>
                <span className="hud-value text-[18px] text-ink">
                  {int(size)} <span className="text-[11px] text-[var(--ink-dim)]">agents</span>
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.001}
                value={x}
                onChange={(e) => setX(parseFloat(e.target.value))}
                className="hud-range mt-1"
                style={{ ["--fill" as string]: `${x * 100}%` }}
              />
              <div className="flex justify-between hud-label !text-[8px] !text-[var(--ink-faint)]">
                <span>100</span>
                <span>1K</span>
                <span>10K</span>
              </div>

              <div className="mt-4 hud-label">Sophistication</div>
              <div className="mt-2 grid grid-cols-5 gap-1">
                {[1, 2, 3, 4, 5].map((l) => {
                  const active = l === level;
                  return (
                    <button
                      key={l}
                      onClick={() => setLevel(l)}
                      className="relative h-11 border transition-colors"
                      style={{
                        borderColor: active ? LEVEL_COLORS[l - 1] : "rgba(243,233,216,0.12)",
                        background: active ? `${LEVEL_COLORS[l - 1]}22` : "rgba(0,0,0,0.25)",
                        boxShadow: active ? `0 0 16px ${LEVEL_COLORS[l - 1]}55, inset 0 0 12px ${LEVEL_COLORS[l - 1]}22` : "none",
                      }}
                    >
                      <div className="hud-value text-[15px]" style={{ color: active ? LEVEL_COLORS[l - 1] : "rgba(243,233,216,0.6)" }}>
                        {l}
                      </div>
                      <div className="hud-label !text-[6.5px] !tracking-[0.12em]">{SHORT[l - 1]}</div>
                    </button>
                  );
                })}
              </div>
              <AnimatePresence mode="wait">
                <motion.div
                  key={level}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.2 }}
                  className="mt-2 min-h-[34px] text-[11px] leading-snug text-[var(--ink-dim)]"
                >
                  <span style={{ color: LEVEL_COLORS[level - 1] }} className="font-semibold">
                    {spec?.name ?? SHORT[level - 1]}.
                  </span>{" "}
                  {spec?.summary}
                </motion.div>
              </AnimatePresence>

              <div className="mt-4 flex items-baseline justify-between">
                <span className="hud-label">Cost per identity</span>
                <span className="hud-value text-[16px] text-gold-soft">{usd(cost)}</span>
              </div>
              <div className="mt-2">
                <CostMeter cost={cost} />
              </div>
              <div className="mt-2 flex justify-between hud-label !text-[8px]">
                <span className="!text-[var(--ink-faint)]">modeled estimate · see README</span>
                <span>
                  total <span className="hud-value !text-[10px] text-ink">{usd(cost * size)}</span>
                </span>
              </div>

              <div className="mt-5 grid grid-cols-[1fr_auto] gap-2">
                <button
                  disabled={demo}
                  onClick={() => commands.launch(size, level)}
                  className="group relative h-11 overflow-hidden border border-[rgba(255,107,91,0.7)] bg-[rgba(255,59,48,0.14)] transition hover:bg-[rgba(255,59,48,0.26)] disabled:opacity-40"
                >
                  <span className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-[rgba(255,107,91,0.35)] to-transparent transition-transform duration-700 group-hover:translate-x-full" />
                  <span className="relative hud-label !text-[11px] !tracking-[0.42em] !text-red-glow glow-red">Launch swarm</span>
                </button>
                <button
                  disabled={demo}
                  onClick={() => commands.reset()}
                  className="h-11 border border-[rgba(243,233,216,0.18)] px-4 hud-label !text-[9.5px] transition hover:!text-ink hover:border-[rgba(243,233,216,0.4)] disabled:opacity-40"
                >
                  Reset
                </button>
              </div>

              {launches.length > 0 && (
                <div className="mt-4 space-y-1 border-t border-[rgba(255,107,91,0.18)] pt-3">
                  {launches.slice(-3).map((l) => (
                    <div key={l.swarm} className="flex justify-between hud-value text-[10px] text-[var(--ink-dim)]">
                      <span>
                        <span style={{ color: LEVEL_COLORS[l.level - 1] }}>L{l.level}</span> · {int(l.size)} agents
                      </span>
                      <span>{l.clock}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
