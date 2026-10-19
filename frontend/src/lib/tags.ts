// One central token map for role/category tags. Backend stores palette token names (delivery_roles.color,
// task_categories.color, users.tag_colors). Light: shade-100 background / shade-900 text; dark: shade-950 / shade-200.
// Contrast (>= 4.5:1) is verified for every token in e2e/tags-contrast.spec.ts.
export const PALETTE = [
  "blue", "sky", "cyan", "teal", "emerald", "green", "lime", "yellow", "amber", "orange",
  "red", "rose", "pink", "fuchsia", "purple", "violet", "indigo", "slate", "gray", "stone",
] as const;
export type TagToken = (typeof PALETTE)[number];

interface Shades {
  l: { bg: string; fg: string; dot: string };
  d: { bg: string; fg: string; dot: string };
}
const mk = (s100: string, s200: string, s400: string, s500: string, s900: string, s950: string): Shades => ({
  l: { bg: s100, fg: s900, dot: s500 },
  d: { bg: s950, fg: s200, dot: s400 },
});

export const TAG_TOKENS: Record<TagToken, Shades> = {
  blue: mk("#dbeafe", "#bfdbfe", "#60a5fa", "#3b82f6", "#1e3a8a", "#172554"),
  sky: mk("#e0f2fe", "#bae6fd", "#38bdf8", "#0ea5e9", "#0c4a6e", "#082f49"),
  cyan: mk("#cffafe", "#a5f3fc", "#22d3ee", "#06b6d4", "#164e63", "#083344"),
  teal: mk("#ccfbf1", "#99f6e4", "#2dd4bf", "#14b8a6", "#134e4a", "#042f2e"),
  emerald: mk("#d1fae5", "#a7f3d0", "#34d399", "#10b981", "#064e3b", "#022c22"),
  green: mk("#dcfce7", "#bbf7d0", "#4ade80", "#22c55e", "#14532d", "#052e16"),
  lime: mk("#ecfccb", "#d9f99d", "#a3e635", "#84cc16", "#365314", "#1a2e05"),
  yellow: mk("#fef9c3", "#fef08a", "#facc15", "#eab308", "#713f12", "#422006"),
  amber: mk("#fef3c7", "#fde68a", "#fbbf24", "#f59e0b", "#78350f", "#451a03"),
  orange: mk("#ffedd5", "#fed7aa", "#fb923c", "#f97316", "#7c2d12", "#431407"),
  red: mk("#fee2e2", "#fecaca", "#f87171", "#ef4444", "#7f1d1d", "#450a0a"),
  rose: mk("#ffe4e6", "#fecdd3", "#fb7185", "#f43f5e", "#881337", "#4c0519"),
  pink: mk("#fce7f3", "#fbcfe8", "#f472b6", "#ec4899", "#831843", "#500724"),
  fuchsia: mk("#fae8ff", "#f5d0fe", "#e879f9", "#d946ef", "#701a75", "#4a044e"),
  purple: mk("#f3e8ff", "#e9d5ff", "#c084fc", "#a855f7", "#581c87", "#3b0764"),
  violet: mk("#ede9fe", "#ddd6fe", "#a78bfa", "#8b5cf6", "#4c1d95", "#2e1065"),
  indigo: mk("#e0e7ff", "#c7d2fe", "#818cf8", "#6366f1", "#312e81", "#1e1b4b"),
  slate: mk("#f1f5f9", "#e2e8f0", "#94a3b8", "#64748b", "#0f172a", "#020617"),
  gray: mk("#f3f4f6", "#e5e7eb", "#9ca3af", "#6b7280", "#111827", "#030712"),
  stone: mk("#f5f5f4", "#e7e5e4", "#a8a29e", "#78716c", "#1c1917", "#0c0a09"),
};

export function asToken(v: string | null | undefined): TagToken {
  return (PALETTE as readonly string[]).includes(v ?? "") ? (v as TagToken) : "gray";
}

/** Solid series colour for charts (same token -> same colour as the tag). */
export function tokenHex(token: string | null | undefined, theme: "light" | "dark" = "light"): string {
  const t = TAG_TOKENS[asToken(token)];
  return (theme === "dark" ? t.d : t.l).dot;
}

function lum(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
export function contrast(a: string, b: string): number {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
