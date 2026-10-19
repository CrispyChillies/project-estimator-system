import type { MetadataRoute } from "next";

import { HELP_PAGES } from "@/lib/help";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = process.env.PUBLIC_APP_URL ?? "http://localhost:3000";
  return [
    { url: `${base}/`, changeFrequency: "monthly", priority: 1 },
    { url: `${base}/help`, changeFrequency: "monthly", priority: 0.6 },
    ...HELP_PAGES.map((p) => ({ url: `${base}/help/${p.slug}`, changeFrequency: "monthly" as const, priority: 0.5 })),
  ];
}
