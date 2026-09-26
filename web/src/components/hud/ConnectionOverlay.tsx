"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useMirage } from "@/lib/store";

// Graceful failure: the last frame stays on screen, a quiet overlay explains.
export function ConnectionOverlay() {
  const status = useMirage((s) => s.status);
  const progress = useMirage((s) => s.progress);
  const world = useMirage((s) => s.world);
  const show = status !== "live";
  const first = world === 0;

  const title =
    status === "warming" ? "Warming up the network" : status === "error" ? "Backend error" : first ? "Connecting to MIRAGE" : "Signal lost · reconnecting";
  const sub =
    status === "warming"
      ? "simulating 72 hours of history so the detector can learn what normal looks like"
      : status === "error"
        ? "check the backend console"
        : "start the backend with  npm run dev  (or python -m mirage.server)";

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.8 } }}
          className={`absolute inset-0 z-40 flex items-center justify-center ${first ? "bg-void" : "bg-[rgba(5,4,3,0.45)]"}`}
        >
          <div className="flex flex-col items-center gap-5">
            <div className="relative h-24 w-24">
              <svg viewBox="-50 -50 100 100" className="absolute inset-0">
                <circle r="44" fill="none" stroke="rgba(245,185,74,0.2)" strokeWidth="0.8" />
                <g style={{ animation: "spin 3s linear infinite", transformOrigin: "0 0" }}>
                  <path d="M 0 -44 A 44 44 0 0 1 38 -22" fill="none" stroke="#F5B94A" strokeWidth="1.6" />
                </g>
                <g style={{ animation: "spin-rev 7s linear infinite", transformOrigin: "0 0" }}>
                  <circle r="34" fill="none" stroke="rgba(245,185,74,0.5)" strokeWidth="0.6" strokeDasharray="1 5" />
                </g>
                {status === "warming" && (
                  <circle
                    r="40"
                    fill="none"
                    stroke="#FFD58A"
                    strokeWidth="1"
                    strokeDasharray={`${progress * 251} 251`}
                    transform="rotate(-90)"
                  />
                )}
              </svg>
              <div className="absolute inset-0 flex items-center justify-center hud-value text-[12px] text-gold-soft">
                {status === "warming" ? `${Math.round(progress * 100)}%` : ""}
              </div>
            </div>
            <div className="text-center">
              <div className={`hud-label !text-[11px] !tracking-[0.34em] ${status === "error" ? "!text-red-glow" : "!text-gold-soft"}`}>{title}</div>
              <div className="mt-2 hud-label !text-[8.5px] !normal-case !tracking-[0.12em]">{sub}</div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
