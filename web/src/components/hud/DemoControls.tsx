"use client";

import { useEffect } from "react";
import { startDemo, stopDemo } from "@/lib/demo";
import { useMirage } from "@/lib/store";

export function DemoControls() {
  const demo = useMirage((s) => s.demo);
  const sound = useMirage((s) => s.sound);
  const set = useMirage((s) => s.set);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "d" || e.key === "D") startDemo();
      if (e.key === "m" || e.key === "M") set({ sound: !useMirage.getState().sound });
      if (e.key === "Escape" && useMirage.getState().demo.active) stopDemo();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [set]);

  return (
    <div className="pointer-events-auto absolute right-10 top-[84px] z-30 flex items-center gap-2">
      <button
        onClick={() => set({ sound: !sound })}
        className={`flex h-8 items-center gap-2 border px-3 hud-label !text-[9px] transition ${sound ? "border-[rgba(245,185,74,0.5)] !text-gold-soft" : "border-[rgba(243,233,216,0.14)] hover:!text-ink"}`}
        title="Sound (M)"
      >
        <span className="flex h-3 items-end gap-[2px]">
          {[0.5, 1, 0.7].map((h, i) => (
            <span
              key={i}
              className={`w-[2px] ${sound ? "bg-gold" : "bg-[var(--ink-faint)]"}`}
              style={{ height: `${h * 100}%`, animation: sound ? `eq 0.${7 + i}s ease-in-out ${i * 0.1}s infinite alternate` : undefined }}
            />
          ))}
        </span>
        sound
      </button>
      {demo.active ? (
        <>
          <button onClick={() => startDemo()} className="h-8 border border-[rgba(243,233,216,0.18)] px-3 hud-label !text-[9px] hover:!text-ink" title="Restart demo (D)">
            ↻ restart
          </button>
          <button onClick={() => stopDemo()} className="h-8 border border-[rgba(255,107,91,0.6)] bg-[rgba(255,59,48,0.12)] px-3 hud-label !text-[9px] !text-red-glow" title="Stop (Esc)">
            ■ stop demo
          </button>
        </>
      ) : (
        <button
          onClick={() => startDemo()}
          className="group relative h-8 overflow-hidden border border-[rgba(245,185,74,0.55)] bg-[rgba(245,185,74,0.08)] px-4 hud-label !text-[9.5px] !tracking-[0.3em] !text-gold-soft transition hover:bg-[rgba(245,185,74,0.16)]"
          title="Demo mode (D)"
        >
          <span className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-[rgba(255,213,138,0.25)] to-transparent transition-transform duration-700 group-hover:translate-x-full" />
          <span className="relative">▶ demo mode</span>
        </button>
      )}
    </div>
  );
}
