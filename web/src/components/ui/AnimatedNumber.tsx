"use client";

import { animate } from "framer-motion";
import { useEffect, useRef } from "react";

type Props = {
  value: number | null | undefined;
  format: (v: number) => string;
  duration?: number;
  className?: string;
  fallback?: string;
};

// Counts smoothly to the new value instead of jumping; writes the DOM directly.
export function AnimatedNumber({ value, format, duration = 0.9, className, fallback = "—" }: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const current = useRef<number | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (value == null || Number.isNaN(value)) {
      el.textContent = fallback;
      current.current = null;
      return;
    }
    const from = current.current ?? value;
    const controls = animate(from, value, {
      duration: from === value ? 0 : duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        el.textContent = format(v);
        current.current = v;
      },
    });
    return () => controls.stop();
  }, [value, format, duration, fallback]);

  return (
    <span ref={ref} className={className}>
      {value == null || Number.isNaN(value) ? fallback : format(value)}
    </span>
  );
}
