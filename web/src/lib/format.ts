export const nf = new Intl.NumberFormat("en-US");

export function int(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return nf.format(Math.round(n));
}

export function pct(v: number | null | undefined, digits = 1): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function fixed(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}

/** Simulated minutes → "4.2 h" / "38 min" / "2.1 d". */
export function simSpan(minutes: number | null | undefined): string {
  if (minutes == null || Number.isNaN(minutes)) return "—";
  if (minutes < 90) return `${Math.round(minutes)} min`;
  if (minutes < 48 * 60) return `${(minutes / 60).toFixed(1)} h`;
  return `${(minutes / 1440).toFixed(1)} d`;
}

export function usd(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(v >= 10_000_000 ? 0 : 1)}M`;
  if (v >= 10_000) return `$${Math.round(v / 1000)}K`;
  if (v >= 1000) return `$${(v / 1000).toFixed(1)}K`;
  if (v >= 1) return `$${v.toFixed(v >= 100 ? 0 : 2)}`;
  return `$${v.toFixed(2)}`;
}

export function shortAddr(a: string | null | undefined): string {
  if (!a) return "—";
  return a.length > 12 ? `${a.slice(0, 6)}…${a.slice(-4)}` : a;
}

export function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}K`;
  return nf.format(Math.round(n));
}
