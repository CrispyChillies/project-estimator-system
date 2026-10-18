export function hours(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 })} h`;
}

export function num(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function pct(v: number | null | undefined, digits = 0, fromFraction = true): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(fromFraction ? v * 100 : v).toFixed(digits)}%`;
}

export function money(v: number | null | undefined, currency = "EUR"): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString(undefined, { style: "currency", currency, maximumFractionDigits: 0 });
}

export function date(v: string | null | undefined): string {
  if (!v) return "—";
  return new Date(v).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function dateTime(v: string | null | undefined): string {
  if (!v) return "—";
  return new Date(v).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function factor(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `×${v.toFixed(2)}`;
}
