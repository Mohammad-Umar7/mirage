"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useMirage } from "@/lib/store";

// Cinematic captions for Demo Mode: lower-third lines, a title intro and an end card.
export function Captions() {
  const demo = useMirage((s) => s.demo);
  const view = useMirage((s) => s.view);
  const intro = demo.active && demo.sub === "intro";
  const finale = demo.active && demo.step === 8;
  const lower = demo.active && !intro && !finale && demo.caption;

  return (
    <>
      <AnimatePresence>
        {intro && (
          <motion.div
            key="intro"
            className="pointer-events-none absolute inset-0 z-[36] flex flex-col items-center justify-center bg-[radial-gradient(ellipse_at_center,rgba(5,4,3,0.35),rgba(5,4,3,0.9))]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 1.2 } }}
          >
            <motion.div
              initial={{ letterSpacing: "0.9em", opacity: 0, filter: "blur(10px)" }}
              animate={{ letterSpacing: "0.5em", opacity: 1, filter: "blur(0px)" }}
              transition={{ duration: 2.2, ease: [0.16, 1, 0.3, 1] }}
              className="bg-gradient-to-b from-[#FFE7B5] via-[#F5B94A] to-[#9B5E12] bg-clip-text pl-[0.5em] text-[88px] font-light leading-none text-transparent glow-gold"
            >
              MIRAGE
            </motion.div>
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 1.1, duration: 1 }}
              className="mt-6 hud-label !text-[11px] !tracking-[0.42em] !text-gold-soft"
            >
              Sybil resistance under agent swarms
            </motion.div>
            <motion.div
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ delay: 0.6, duration: 1.8, ease: [0.16, 1, 0.3, 1] }}
              className="mt-7 h-px w-[420px] bg-gradient-to-r from-transparent via-[#F5B94A] to-transparent"
            />
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {lower && (
          <motion.div
            key={demo.caption}
            className={`pointer-events-none absolute left-1/2 z-[36] w-[min(1100px,80vw)] -translate-x-1/2 text-center ${view === "terrain" ? "bottom-[178px]" : "bottom-[150px]"}`}
            initial={{ opacity: 0, y: 14, filter: "blur(8px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -8, filter: "blur(8px)" }}
            transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          >
            {/* a soft pool of shadow so the line reads over any part of the scene */}
            <div className="absolute -inset-x-24 -inset-y-10 -z-10 bg-[radial-gradient(ellipse_at_center,rgba(5,4,3,0.72),rgba(5,4,3,0.35)_45%,transparent_72%)]" />
            <div className="text-[32px] font-light leading-tight tracking-[0.02em] text-ink [text-shadow:0_2px_24px_rgba(0,0,0,0.9)]">
              {demo.caption}
            </div>
            {demo.sub && (
              <div className="mt-3 hud-label !text-[10.5px] !tracking-[0.22em] !text-gold-soft [text-shadow:0_1px_12px_rgba(0,0,0,0.9)]">
                {demo.sub}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {finale && (
          <motion.div
            key="finale"
            className="pointer-events-none absolute inset-0 z-[36] flex flex-col items-center justify-center bg-[radial-gradient(ellipse_at_center,rgba(5,4,3,0.55),rgba(5,4,3,0.95))]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 1.2 } }}
            transition={{ duration: 1.2 }}
          >
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 1 }}
              className="text-[46px] font-light tracking-[0.02em] text-ink"
            >
              {demo.caption}
            </motion.div>
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 1.6, duration: 1.1 }}
              className="mt-4 bg-gradient-to-b from-[#FFE7B5] to-[#F5B94A] bg-clip-text text-[46px] font-light tracking-[0.02em] text-transparent glow-gold"
            >
              {demo.sub}
            </motion.div>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 3, duration: 1 }}
              className="mt-10 hud-label !text-[10px] !tracking-[0.5em] !text-gold"
            >
              MIRAGE
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
