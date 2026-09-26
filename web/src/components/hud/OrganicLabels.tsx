"use client";

import { useEffect, useMemo, useRef } from "react";
import { hudBus } from "@/lib/hudBus";
import { useMirage } from "@/lib/store";

// Small gold tags on organic communities: seen, understood, deliberately not flagged.
export function OrganicLabels() {
  const detection = useMirage((s) => s.detection);
  const view = useMirage((s) => s.view);
  const organics = useMemo(
    () =>
      (detection?.clusters ?? [])
        .filter((c) => c.verdict === "ORGANIC COMMUNITY" && c.size >= 14)
        .sort((a, b) => b.size - a.size)
        .slice(0, 6),
    [detection],
  );
  const refs = useRef(new Map<number, HTMLDivElement>());

  useEffect(() => {
    return hudBus.subscribe((list) => {
      const swarm = list.find((c) => c.verdict === "SWARM" && c.visible);
      const vw = window.innerWidth, vh = window.innerHeight;
      for (const [id, el] of refs.current) {
        const s = list.find((c) => c.id === id);
        if (!s || !s.visible || view !== "network") {
          el.style.opacity = "0";
          continue;
        }
        const x = s.x + s.r * 0.72 + 6, y = s.y - s.r * 0.72 - 14;
        // keep clear of the targeting ring and of the HUD bands
        const nearRing = swarm && Math.hypot(x - swarm.x, y - swarm.y) < Math.max(150, swarm.r * 2.4 + 60);
        const inBands = y < 110 || y > vh - 150 || x < 360 || x > vw - 160;
        // the evidence panel is translucent: never let a tag show through it
        const underPanel = useMirage.getState().selected !== null && x > vw - 520;
        el.style.opacity = nearRing || inBands || underPanel ? "0" : s.depth > 520 ? "0.35" : "1";
        el.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      }
    });
  }, [view]);

  return (
    <div className="pointer-events-none absolute inset-0 z-[14]">
      {organics.map((c) => (
        <div
          key={c.id}
          ref={(el) => {
            if (el) refs.current.set(c.id, el);
            else refs.current.delete(c.id);
          }}
          className="absolute left-0 top-0 transition-opacity duration-500"
          style={{ opacity: 0 }}
        >
          <div className="flex items-center gap-1.5">
            <span className="h-px w-4 bg-[rgba(255,213,138,0.6)]" />
            <span className="hud-label !text-[8.5px] !tracking-[0.24em] !text-gold-soft">Organic · {c.size}</span>
          </div>
          <div className="ml-[22px] hud-label !text-[7.5px] !text-[rgba(255,213,138,0.5)]">not flagged</div>
        </div>
      ))}
    </div>
  );
}
