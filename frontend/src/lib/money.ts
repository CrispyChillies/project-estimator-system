// Money: canonical storage is whole VND; USD is a display/input conversion at the workspace rate.
export type CurrencyCode = "VND" | "USD";

export const VND_STEP = 1000;

const vndFull = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND", maximumFractionDigits: 0 });
const usdFull = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const usdCompact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });
const viNumber = (digits: number) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: digits, minimumFractionDigits: 0 });

export function vndToUsd(vnd: number, rate: number): number {
  return vnd / rate;
}

/** Amount typed in `currency` -> whole VND rounded to the nearest 1.000 (convert once, at the edge). */
export function toVnd(amount: number, currency: CurrencyCode, rate: number): number {
  const vnd = currency === "USD" ? amount * rate : amount;
  return Math.round(vnd / VND_STEP) * VND_STEP;
}

export function fromVnd(vnd: number, currency: CurrencyCode, rate: number): number {
  return currency === "USD" ? vndToUsd(vnd, rate) : vnd;
}

/** Full value: `1.250.000 ₫` (vi-VN) or `$12,400.00` (en-US). */
export function formatMoney(vnd: number | null | undefined, currency: CurrencyCode, rate: number): string {
  if (vnd === null || vnd === undefined || Number.isNaN(vnd)) return "—";
  return currency === "USD" ? usdFull.format(vndToUsd(vnd, rate)) : vndFull.format(Math.round(vnd));
}

/** Compact for KPI cards and chart ticks: `350 triệu`, `1,25 tỷ` (VND) or `$12.4K` (USD). Full value belongs in a tooltip. */
export function formatCompact(vnd: number | null | undefined, currency: CurrencyCode, rate: number): string {
  if (vnd === null || vnd === undefined || Number.isNaN(vnd)) return "—";
  if (currency === "USD") return usdCompact.format(vndToUsd(vnd, rate));
  const a = Math.abs(vnd);
  if (a >= 1e9) return `${viNumber(2).format(vnd / 1e9)} tỷ`;
  if (a >= 1e8) return `${viNumber(0).format(vnd / 1e6)} triệu`;
  if (a >= 1e6) return `${viNumber(1).format(vnd / 1e6)} triệu`;
  return vndFull.format(Math.round(vnd));
}

export function parseAmount(text: string): number | null {
  const t = text.trim().replace(/[^\d.,-]/g, "");
  if (!t) return null;
  // treat a single separator followed by exactly three digits as thousands ("1.250.000", "5,000")
  const normalized = /^\d{1,3}([.,]\d{3})+$/.test(t) ? t.replace(/[.,]/g, "") : t.replace(",", ".");
  const n = Number(normalized);
  return Number.isFinite(n) ? n : null;
}

export function fxLine(rate: number, updatedAt: string | null | undefined): string {
  const d = updatedAt ? new Date(updatedAt) : null;
  const when = d ? ` · updated ${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}` : "";
  return `1 USD = ${viNumber(0).format(rate)} ₫${when}`;
}
