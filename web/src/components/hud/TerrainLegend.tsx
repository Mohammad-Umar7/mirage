"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useMirage } from "@/lib/store";

// Axis and legend for the Pulse Terrain view.
export function TerrainLegend() {
  const view = useMirage((s) => s.view);
  const terrain = useMirage((s) => s.terrain);
  const swarms = terrain?.lanes.filter((l) => l.kind === "swarm") ?? [];
  const organics = terrain?.lanes.filter((l) => l.kind === "organic") ?? [];
  return (
    <AnimatePresence>
      {view === "terrain" && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="pointer-events-none absolute inset-0 z-20"
        >
          <div className="absolute left-10 top-[132px] w-[320px]">
            <div className="hud-label !text-[10px] !tracking-[0.32em] !text-gold-soft">Pulse terrain</div>
            <div className="mt-3 text-[13px] leading-relaxed text-[var(--ink-dim)]">
              Every line is the activity of a group of accounts over the last 72 hours. Real people make{" "}
              <span className="text-gold-soft">gentle waves</span> — sleep, work, evenings, news. One operator driving a
              thousand accounts makes <span className="text-red-glow">sharp, synchronized ridges</span>.
            </div>
            <div className="mt-5 space-y-2 hud-label !text-[8.5px]">
              <div className="flex items-center gap-3">
                <span className="h-px w-8 bg-gold" /> groups of ordinary accounts
              </div>
              {organics.length > 0 && (
                <div className="flex items-center gap-3">
                  <span className="h-[2px] w-8 bg-gold-soft" /> organic communities ({organics.length})
                </div>
              )}
              {swarms.length > 0 && (
                <div className="flex items-center gap-3">
                  <span className="h-[2px] w-8 bg-red shadow-[0_0_8px_#FF3B30]" /> flagged swarm · {swarms[0].size.toLocaleString()} accounts
                </div>
              )}
            </div>
          </div>
          <div className="absolute bottom-[132px] left-1/2 flex w-[min(1100px,70vw)] -translate-x-1/2 justify-between">
            {["−72h", "−54h", "−36h", "−18h", "now"].map((t) => (
              <span key={t} className="hud-value text-[10px] text-[var(--ink-faint)]">
                {t}
              </span>
            ))}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
