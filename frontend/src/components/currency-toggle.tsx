"use client";

import { useCurrency } from "@/hooks/currency";
import { fxLine, type CurrencyCode } from "@/lib/money";
import { cn } from "@/lib/utils";

const OPTIONS: { code: CurrencyCode; label: string; name: string }[] = [
  { code: "VND", label: "₫", name: "₫ Vietnamese dong" },
  { code: "USD", label: "$", name: "$ US dollar" },
];

/** Quick ₫ | $ switch; persisted per user. */
export function CurrencyToggle({ className }: { className?: string }) {
  const { currency, setCurrency } = useCurrency();
  return (
    <div role="radiogroup" aria-label="Display currency" data-testid="currency-toggle" className={cn("inline-flex rounded-md border p-0.5", className)}>
      {OPTIONS.map((o) => (
        <button
          key={o.code}
          type="button"
          role="radio"
          aria-checked={currency === o.code}
          aria-label={o.name}
          data-testid={`currency-${o.code}`}
          onClick={() => currency !== o.code && setCurrency(o.code)}
          className={cn(
            "min-w-7 rounded px-2 py-0.5 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
            currency === o.code ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** "1 USD = 25.869 ₫ · updated 19/10/2026" (+ attribution when the rate comes from the public provider). */
export function FxNote({ className }: { className?: string }) {
  const { fx, rate } = useCurrency();
  return (
    <p className={cn("text-[11px] text-muted-foreground", className)} data-testid="fx-note">
      {fxLine(rate, fx?.rate_updated_at)}
      {fx?.attribution && (
        <>
          {" · "}
          <a className="underline underline-offset-2" href={fx.attribution.url} target="_blank" rel="noreferrer">
            {fx.attribution.text}
          </a>
        </>
      )}
    </p>
  );
}
