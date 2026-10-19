"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { meKey, useMe, type Me } from "@/hooks/auth";
import { api } from "@/lib/api";
import { formatCompact, formatMoney, type CurrencyCode } from "@/lib/money";

export interface Fx {
  usd_vnd_rate: number;
  rate_updated_at: string | null;
  rate_source: string;
  auto_update: boolean;
  attribution: { text: string; url: string } | null;
}

export const useFx = () => useQuery({ queryKey: ["fx"], queryFn: () => api<Fx>("/fx"), staleTime: 300_000 });

/** The user's display currency (default VND), the workspace rate and formatters. Amounts are canonical VND. */
export function useCurrency() {
  const { data: me } = useMe();
  const { data: fx } = useFx();
  const qc = useQueryClient();
  const currency: CurrencyCode = me?.display_currency === "USD" ? "USD" : "VND";
  const rate = fx?.usd_vnd_rate ?? 25869;
  const set = useMutation({
    mutationFn: (c: CurrencyCode) => api("/me/preferences", { method: "PUT", json: { display_currency: c } }),
    onMutate: (c) => {
      const prev = qc.getQueryData<Me | null>(meKey);
      if (prev) qc.setQueryData(meKey, { ...prev, display_currency: c });
      return { prev };
    },
    onError: (_e, _c, ctx) => {
      if (ctx?.prev) qc.setQueryData(meKey, ctx.prev);
    },
  });
  return {
    currency,
    rate,
    fx,
    setCurrency: (c: CurrencyCode) => set.mutate(c),
    money: (vnd: number | null | undefined) => formatMoney(vnd, currency, rate),
    compact: (vnd: number | null | undefined) => formatCompact(vnd, currency, rate),
  };
}
