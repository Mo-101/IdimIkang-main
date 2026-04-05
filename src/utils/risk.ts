// src/utils/risk.ts
export function computeStopPctPercent(entry: number | null, stop: number | null): number | null {
  if (entry == null || stop == null) return null;
  if (!Number.isFinite(entry) || entry === 0) return null;
  const pct = Math.abs(entry - stop) / entry * 100;
  return Number.isFinite(pct) ? pct : null;
}

export function formatPctForUI(pct: number | null, decimals = 2): string {
  if (pct == null) return '—';
  return `${pct.toFixed(decimals)}%`;
}

export function formatAlphaForUI(alpha: number | null): string {
  if (alpha == null || !Number.isFinite(alpha)) return '—';
  return Number(alpha).toString();
}

export function formatPFForUI(pf: number | null, wins: number, losses: number): string {
  if (wins === 0) return 'N/A';
  if (pf == null || !Number.isFinite(pf)) return '—';
  return Number(pf).toFixed(2);
}
