"use client";

import { useTheme } from "next-themes";

import { useCategories, useRoles } from "@/hooks/queries";
import { asToken, TAG_TOKENS, tokenHex } from "@/lib/tags";
import { cn } from "@/lib/utils";

/** Soft tinted tag: dot + label (colour is never the only signal), truncates with a tooltip. */
export function TagBadge({ label, token, className, kind }: { label: string; token: string; className?: string; kind?: string }) {
  const t = TAG_TOKENS[asToken(token)];
  const style = {
    "--tbg-l": t.l.bg, "--tfg-l": t.l.fg, "--tdot-l": t.l.dot,
    "--tbg-d": t.d.bg, "--tfg-d": t.d.fg, "--tdot-d": t.d.dot,
  } as React.CSSProperties;
  return (
    <span
      data-tag={kind}
      data-token={asToken(token)}
      title={label}
      style={style}
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-md bg-(--tbg-l) px-1.5 py-0.5 text-xs leading-4 font-medium text-(--tfg-l) dark:bg-(--tbg-d) dark:text-(--tfg-d)",
        className,
      )}
    >
      <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-(--tdot-l) dark:bg-(--tdot-d)" />
      <span className="truncate">{label}</span>
    </span>
  );
}

export function useRoleLookup() {
  const { data: roles } = useRoles();
  return (key: string | null | undefined) => roles?.find((r) => r.id === key || r.name === key);
}

export function useCategoryLookup() {
  const { data: cats } = useCategories();
  return (key: string | null | undefined) => cats?.find((c) => c.id === key || c.key === key || c.name === key);
}

export function RoleTag({ id, name, className }: { id?: string | null; name?: string | null; className?: string }) {
  const find = useRoleLookup();
  const r = find(id ?? name);
  const label = r?.name ?? name;
  if (!label) return <span className="text-muted-foreground">—</span>;
  return <TagBadge kind="role" label={label} token={r?.color ?? "gray"} className={className} />;
}

export function CategoryTag({ id, name, className }: { id?: string | null; name?: string | null; className?: string }) {
  const find = useCategoryLookup();
  const c = find(id ?? name);
  const label = c?.name ?? name;
  if (!label) return <span className="text-muted-foreground">—</span>;
  return <TagBadge kind="category" label={label} token={c?.color ?? "gray"} className={className} />;
}

/** Chart series colours: the same role/category -> the same colour as its tag (theme aware). */
export function useTagHex() {
  const { resolvedTheme } = useTheme();
  const theme = resolvedTheme === "dark" ? "dark" : "light";
  const role = useRoleLookup();
  const cat = useCategoryLookup();
  return {
    role: (nameOrId: string) => tokenHex(role(nameOrId)?.color, theme),
    category: (nameOrKey: string) => tokenHex(cat(nameOrKey)?.color, theme),
  };
}
