"use client";

import { useSyncExternalStore } from "react";

/** SSR-safe media query (false on the server and during hydration's first paint of the snapshot). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(query);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}
