"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { audio } from "@/lib/audio";
import { isFresh } from "@/lib/lock";
import { useMirage } from "@/lib/store";

// Reacts to stream events with sound and a brief screen flash; drives the
// acquisition riser from the top swarm cluster's rising confidence.
export function FxDirector() {
  const fx = useMirage((s) => s.fx);
  const sound = useMirage((s) => s.sound);
  const detection = useMirage((s) => s.detection);
  const locked = useMirage((s) => s.lockedCluster);
  const acquired = useMirage((s) => s.acquired);
  const seen = useRef(0);
  const [flash, setFlash] = useState(0);

  useEffect(() => {
    if (sound) audio.enable();
    else audio.disable();
  }, [sound]);

  useEffect(() => {
    const fresh = fx.filter((e) => e.at > seen.current);
    if (!fresh.length) return;
    seen.current = Math.max(...fresh.map((e) => e.at));
    for (const e of fresh) {
      if (e.kind === "lock") {
        audio.pulse();
        audio.lock();
        setFlash((f) => f + 1);
      } else if (e.kind === "launch") audio.launch();
      else if (e.kind === "flip") audio.flip();
    }
  }, [fx]);

  useEffect(() => {
    const top = detection?.clusters.find((c) => (c.verdict === "SWARM" || c.watch) && isFresh(c.members, acquired));
    const acquiring = top && locked === null ? Math.min(1, Math.max(0, (top.confidence - 0.25) / 0.6)) : 0;
    audio.tension(acquiring);
  }, [detection, locked, acquired]);

  return (
    <AnimatePresence>
      {flash > 0 && (
        <motion.div
          key={flash}
          className="pointer-events-none absolute inset-0 z-[35]"
          style={{ background: "radial-gradient(circle at 50% 50%, rgba(255,80,60,0.22), transparent 60%)" }}
          initial={{ opacity: 1 }}
          animate={{ opacity: 0 }}
          transition={{ duration: 1.2, ease: "easeOut" }}
        />
      )}
    </AnimatePresence>
  );
}
