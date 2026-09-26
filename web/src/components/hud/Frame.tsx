"use client";

// Viewport frame: corner brackets, edge ticks and hairline rules.
export function Frame() {
  const corner = "absolute w-7 h-7 border-[var(--hair-strong)]";
  return (
    <div className="pointer-events-none absolute inset-0 z-10">
      <div className={`${corner} left-4 top-4 border-l border-t`} />
      <div className={`${corner} right-4 top-4 border-r border-t`} />
      <div className={`${corner} left-4 bottom-4 border-l border-b`} />
      <div className={`${corner} right-4 bottom-4 border-r border-b`} />
      <div className="absolute left-14 right-14 top-4 h-px bg-gradient-to-r from-transparent via-[rgba(245,185,74,0.18)] to-transparent" />
      <div className="absolute left-14 right-14 bottom-4 h-px bg-gradient-to-r from-transparent via-[rgba(245,185,74,0.18)] to-transparent" />
      {/* edge ticks */}
      <div className="absolute left-4 top-1/2 -translate-y-1/2 flex flex-col gap-[7px]">
        {Array.from({ length: 13 }, (_, i) => (
          <div key={i} className="h-px bg-[rgba(245,185,74,0.35)]" style={{ width: i % 6 === 0 ? 12 : 5 }} />
        ))}
      </div>
      <div className="absolute right-4 top-1/2 -translate-y-1/2 flex flex-col items-end gap-[7px]">
        {Array.from({ length: 13 }, (_, i) => (
          <div key={i} className="h-px bg-[rgba(245,185,74,0.35)]" style={{ width: i % 6 === 0 ? 12 : 5 }} />
        ))}
      </div>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_55%,rgba(0,0,0,0.55)_100%)]" />
    </div>
  );
}
