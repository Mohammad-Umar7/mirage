"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useMirage } from "@/lib/store";

// A thin live ticker of real posts from the network. Tags come from the
// detector's output (never from labels).
export function Feed() {
  const feed = useMirage((s) => s.feed);
  const view = useMirage((s) => s.view);
  const items = feed.slice(0, 5);
  if (view === "governance") return null;
  return (
    <div className="pointer-events-none absolute bottom-[118px] left-10 z-20 w-[330px]">
      <div className="mb-2 flex items-center gap-2">
        <span className="h-px w-5 bg-[var(--hair-strong)]" />
        <span className="hud-label !text-[8.5px]">Live feed</span>
      </div>
      <div className="space-y-1.5 [mask-image:linear-gradient(180deg,#000_55%,transparent)]">
        {/* no exit animation: exiting rows overlapping entering rows read as garbled text */}
        <AnimatePresence initial={false} mode="popLayout">
          {items.map((f) => (
            <motion.div
              key={f.post}
              layout="position"
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, transition: { duration: 0 } }}
              transition={{ duration: 0.35 }}
              className="line-clamp-2 text-[10.5px] leading-snug"
            >
              <span className={`hud-value mr-1.5 ${f.verdict === "SWARM" ? "text-red-glow" : "text-gold"}`}>@{f.handle}</span>
              {f.verdict === "SWARM" && (
                <span className="mr-1.5 border border-[rgba(255,59,48,0.6)] px-1 hud-label !text-[7px] !text-red-glow">swarm</span>
              )}
              {f.verdict === "ORGANIC COMMUNITY" && (
                <span className="mr-1.5 border border-[rgba(255,213,138,0.5)] px-1 hud-label !text-[7px] !text-gold-soft">organic</span>
              )}
              <span className="text-[var(--ink-dim)]">{f.text}</span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
