"use client";

import { Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { asToken, PALETTE, TAG_TOKENS } from "@/lib/tags";

/** Palette swatch menu; `value` is a palette token. Colour is never the only signal: tags always carry their label. */
export function ColorPicker({ value, onPick, label }: { value: string; onPick: (token: string) => void; label: string }) {
  const cur = asToken(value);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button size="icon-xs" variant="outline" aria-label={`Colour for ${label}: ${cur}`} data-testid="color-picker" />}
      >
        <span className="size-3 rounded-full" style={{ background: TAG_TOKENS[cur].l.dot }} aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44 p-2">
        <div className="grid grid-cols-5 gap-1.5" role="listbox" aria-label={`Colours for ${label}`}>
          {PALETTE.map((t) => (
            <button
              key={t}
              type="button"
              role="option"
              aria-selected={t === cur}
              aria-label={t}
              title={t}
              onClick={() => onPick(t)}
              className="flex size-6 items-center justify-center rounded-full ring-offset-1 ring-offset-popover hover:ring-2 hover:ring-ring focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              style={{ background: TAG_TOKENS[t].l.dot }}
            >
              {t === cur && <Check className="size-3.5 text-white mix-blend-difference" aria-hidden />}
            </button>
          ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
