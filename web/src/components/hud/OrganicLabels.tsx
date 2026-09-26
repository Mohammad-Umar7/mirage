"use client";

import { useEffect, useMemo, useRef } from "react";
import { hudBus } from "@/lib/hudBus";
import { useMirage } from "@/lib/store";

// Small gold tags on organic communities: seen, understood, deliberately not flagged.
export function OrganicLabels() {
  const detection = useMirage((s) => s.detection);
  const view = useMirage((s) => s.view);
  const organics = useMemo(
    () => (detection?.clusters ?? []).filter((c) => c.verdict === "ORGANIC COMMUNITY").sort((a, b) => b.size - a.size).slice(0, 8),
    [detection],
  );
  const refs = useRef(new Map<number, HTMLDivElement>());

  useEffect(() => {
    return hudBus.subscribe((list) => {
      for (const [id, el] of refs.current) {
        const s = list.find((c) => c.id === id);
        if (!s || !s.visible || view !== "network") {
          el.style.opacity = "0";
          continue;
        }
        el.style.opacity = s.depth > 520 ? "0.35" : "1";
        el.style.transform = `translate3d(${s.x + s.r * 0.72 + 6}px, ${s.y - s.r * 0.72 - 14}px, 0)`;
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
